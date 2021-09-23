from copy import deepcopy

from ya_glm.solver.base import GlmSolverWithPath

from ya_glm.opt.lla import solve_lla, WeightedProblemSolver
from ya_glm.opt.penalty.from_config import get_penalty_func, wrap_intercept
from ya_glm.opt.glm_loss.from_config import get_glm_loss_func
from ya_glm.opt.utils import safe_concat


from ya_glm.autoassign import autoassign
from ya_glm.utils import is_multi_response


class WeightedGlmProblemSolver(WeightedProblemSolver):
    """
    The solver for the weighted subproblems from the LLA algorithm. Also computes the objective function.

    Parameters
    ----------
    solver: GlmSolver
        A solver that solves the weighted GLM subproblems.

    Attributes
    ----------
    sp_solver_: Solver
        The weighted sub-problem solver.

    loss_func_: ya_glm.opt.base.Func
        The loss function -- used to compute the objective function.

    penalty_func_:ya_glm.opt.base.Func
        The non-convex penalty function -- used to compute the objective function.

    is_mr_: bool
        Whether or not the coefficient is a multi-response coefficient.

    fit_intercept_: bool
        Whether or not there is an intercept in the model.
    """
    def __init__(self, solver):
        self.solver = solver

    def setup(self, X, y, loss, penalty, constraint=None,
              fit_intercept=True, sample_weight=None):
        """
        Sets up anything the solver needs.
        """

        # setup solver with base convex penalty
        kws = locals()
        kws.pop('self')

        # get base convex penalty
        # assert penalty.is_nonconvex
        base_cvx_pen_config = penalty.get_base_convex()
        base_cvx_pen_config.set_params(pen_val=1)  # ensure the multiplicative penalty value is 1
        kws['penalty'] = base_cvx_pen_config

        self.solver_ = deepcopy(self.solver)
        self.solver_.setup(**kws)

        #######################################################
        # quantities needed to compute the objective function #
        #######################################################

        # setup loss + penalty for computing loss function
        self.loss_func_ = get_glm_loss_func(X=X, y=y, config=loss,
                                            fit_intercept=fit_intercept,
                                            sample_weight=sample_weight)

        self.is_mr_ = is_multi_response(y)
        self.fit_intercept_ = fit_intercept

        self.penalty_config_ = penalty
        self.update_penalty()

    def update_penalty(self, **params):
        """
        Updates the penalty.
        """
        self.penalty_config_.set_params(**params)

        # the overall penalty function used for computing the objective function
        self.penalty_func_ = get_penalty_func(self.penalty_config_)
        self.penalty_func_ = wrap_intercept(func=self.penalty_func_,
                                            fit_intercept=self.fit_intercept_,
                                            is_mr=self.is_mr_)

    def solve(self, weights, sp_init=None,
              sp_upv_init=None, sp_other_data=None):
        """
        Solves the weighted subproblem.

        Parameters
        ----------
        weights: array-like
            Weights for the weighted sup-problem.

        sp_init: None, array-like
            (Optional) Subproblem initialization for the penalized variable.

        sp_upv_init: None, array-like
            (Optional) Subproblem initialization for the unpenalized variable.

        other_data
            (Optional) Subproblem initialization for other data e.g. dual variables.

        Output
        ------
        solution, upv_solution, other_data
        """

        # update penalty weights
        self.solver_.update_penalty(weights=weights)
        # self.solver_.update_penalty(pen_val=1) # ensure penalty val is 1

        soln, other_data, opt_info = \
            self.solver_.solve(coef_init=sp_init,
                               intercept_init=sp_upv_init,
                               other_init=sp_other_data)

        return soln['coef'], soln['intercept'], other_data

    def eval_objective(self, value, upv=None):
        """
        Parameters
        ----------
        value:
            The current value of the penalized variable.

        upv:
            (Optional) The current value of the unpenalized variable.

        Output
        ------
        obj, base_loss, pen_loss

        base_loss: float
            The base loss objective function value.

        pen_loss: float
            The penalized lsos objective function value.
        """
        if self.fit_intercept_:
            # return self.glm_loss.eval(np.concatenate([[upv], value]))
            current = safe_concat(upv, value)
        else:
            current = value

        base_loss = self.loss_func_.eval(current)
        pen_loss = self.penalty_func_.eval(current)
        obj = base_loss + pen_loss

        return obj, base_loss, pen_loss


class LLAFixedInit(GlmSolverWithPath):
    """
    Solves a concave penalized GLM problem using the LLA algorithm initialized from a specified starting point.

    Parameters
    ----------
    n_steps: int
        Number of LLA steps to take.

    xtol: float, None
        The change in x tolerance stopping criterion based on the L_infy norm.

    atol: float, None
        Absolute tolerance for loss based stopping criterion.

    rtol: float, None
        Relative tolerance for loss based stopping criterion.

    tracking_level: int
        How much optimization data to store at each step. Lower values means less informationed is stored.

    verbosity: int
        How much information to print out. Lower values means less print out.

    sp_solver: GlmSolver
        The solver to use for the penalized GLM subproblems.

    Attributes
    ----------
    sp_solver_: WeightedGlmProblemSolver
        The weighted subproblem solver.

    coef_init_lla_:
        The coefficient initializer for the LLA algorithm.

    intercept_init_lla_:
        The intercept initializer for the LLA algorithm.

    transform_: None, callable(coef) -> array-like
        (Optional) The transformation applied to the coefficient.

    transf_penalty_func_: ya_glm.opt.base.Func
        The non-convex function applied to the transformed coefficient.
    """
    @autoassign
    def __init__(self, n_steps=1, xtol=1e-4, atol=None, rtol=None,
                 tracking_level=0, verbosity=0): pass

    def set_sp_solver(self, solver):
        self.sp_solver_ = WeightedGlmProblemSolver(solver=solver)

    def update_penalty(self, **params):
        """
        Updates the penalty.
        """
        self.sp_solver_.update_penalty(**params)

    def setup(self, X, y, loss, penalty, constraint=None,
              fit_intercept=True, sample_weight=None):

        kws = locals()
        kws.pop('self')
        self.sp_solver_.setup(**kws)

        # set the coefficient transform
        self.transform_ = penalty.get_non_smooth_transforms()

        # the non-convex function applied to the transformed coefficient
        self.transf_penalty_func_ = penalty.get_transf_nonconex_penalty()

        # where we initialize the coefficient and intercept
        self.coef_init_lla_ = penalty.coef_init_
        self.intercept_init_lla_ = penalty.intercept_init_

    def solve(self, coef_init=None, intercept_init=None, other_init=None):
        """
        Solves the LLA algorithm from a fixed starting point.

        Parameters
        ----------
        coef_init, intercept_init, other_init:
            (Optional) Initialization for the first LLA subproblem. Note this is not the initialization for entire the LLA algorithm, which is set TODO.

        Output
        ------
        soln, other_data, opt_info

        soln: dict of array-like
            The coefficient/intercept solutions.

        other_data:
            Other data output by the LLA algorithm e.g. dual variables.

        opt_info: dict
            Optimization information e.g. runtime, number of steps.
        """
        # TODO-THINK-THROUGH: the initialization is a bit misleading here. For all other solvers coef_init is where we initializer the entire optimization algorithm, but here it is only the initialization for the first LLA sub-problem. The advantage of this current version is that it allows us to do warm starts for the LLA algorithm.

        # LLA intercept initializer
        if self.sp_solver_.fit_intercept_:
            init_upv = self.intercept_init_lla_
        else:
            init_upv = None

        coef, intercept, sp_other_data, opt_info = \
            solve_lla(sub_prob=self.sp_solver_,
                      penalty_func=self.transf_penalty_func_,
                      init=self.coef_init_lla_,
                      init_upv=init_upv,
                      sp_init=coef_init,
                      sp_upv_init=intercept_init,
                      sp_other_data=other_init,
                      transform=self.transform_,
                      **self.get_solve_kws())

        return {'coef': coef, 'intercept': intercept}, sp_other_data, opt_info