from sklearn.base import BaseEstimator, clone
from sklearn.utils.validation import check_is_fitted
from sklearn.model_selection import ParameterGrid
import numpy as np
from time import time
from numbers import Number
from textwrap import dedent

from ya_glm.autoassign import autoassign
from ya_glm.add_init_params import add_init_params
from ya_glm.utils import get_sequence_decr_max, get_enet_ratio_seq


from ya_glm.cv.cv_select import CVSlectMixin  # select_best_cv_tune_param


_cv_params = dedent(
"""
estimator: estimator object
    The base estimator to be cross-validated.

cv: int, cross-validation generator or an iterable, default=None
    Determines the cross-validation splitting strategy.

cv_select_metric: None, str
    Which metric to use for select the best tuning parameter if multiple metrics are computed.

cv_scorer: None, callable(est, X, y) -> dict or float
    A function for evaluating the cross-validation fit estimators.
    If this returns a dict of multiple scores then cv_select_metric determines which metric is used to select the tuning parameter.

cv_n_jobs: None, int
    Number of jobs to run in parallel.

cv_verbose: int
    Amount of printout during cross-validation.

cv_pre_dispatch: int, or str, default=n_jobs
    Controls the number of jobs that get dispatched during parallel execution
"""
)


class GlmCV(CVSlectMixin, BaseEstimator):

    @autoassign
    def __init__(self,
                 estimator,

                 cv=None,
                 cv_select_rule='best',
                 cv_select_metric=None,
                 cv_scorer=None,
                 cv_verbose=0, cv_n_jobs=None,
                 cv_pre_dispatch='2*n_jobs'):
        pass

    def fit(self, X, y):
        """
        Runs cross-validation then refits the GLM with the selected tuning parameter.

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            The training covariate data.

        y: array-like, shape (n_samples, )
            The training response data.
        """

        # check the input data
        self._check_base_estimator(self.estimator)
        est = clone(self.estimator)
        X, y = est._validate_data(X, y)

        # set up the tuning parameter values using the processed data
        self._set_tuning_values(X=X, y=y)

        # run cross-validation on the raw data
        start_time = time()
        self.cv_results_ = self._run_cv(X=X, y=y, cv=self.cv)
        self.cv_data_ = {'cv_runtime':  time() - start_time}

        # select best tuning parameter values
        self.best_tune_idx_, self.best_tune_params_ = \
            self._select_tune_param(self.cv_results_)

        # set best tuning params
        est.set_params(**self.best_tune_params_)

        # refit on the raw data
        start_time = time()
        self.best_estimator_ = est.fit(X, y)
        self.cv_data_['refit_runtime'] = time() - start_time

        return self

    def predict(self, X):
        check_is_fitted(self)
        return self.best_estimator_.predict(X)

    def score(self, X, y):
        check_is_fitted(self)
        return self.best_estimator_.score(X, y)

    def decision_function(self, X):
        check_is_fitted(self)
        return self.best_estimator_.decision_function(X)

    def predict_proba(self, X):
        check_is_fitted(self)
        if not hasattr(self.best_estimator_, 'predict_proba'):
            raise NotImplementedError("This method does not have a preidct_proba function")
        else:
            return self.best_estimator_.predict_proba(X)

    def predict_log_proba(self, X):
        check_is_fitted(self)
        if not hasattr(self.best_estimator_, 'predict_log_proba'):
            raise NotImplementedError("This method does not have a predict_log_proba function")
        else:
            return self.best_estimator_.predict_log_proba(X)

    def check_base_estimator(self, estimator):
        """
        Check the base estimator aggrees with the CV class
        """
        raise NotImplementedError

    def _set_tuning_values(self, X, y):
        """
        Sets the tuning parameter sequence from the transformed data.

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            The processed training covariate data.

        y: array-like, shape (n_samples, )
            The processed training response data.
        """
        # subclass should overwrite
        raise NotImplementedError


GlmCV.__doc__ = dedent(
    """
    Base class for generalized linear models tuned with cross-validation.

    Parameters
    ----------
    {}
    """.format(_cv_params)
)


_pen_seq_params = dedent("""

n_pen_vals: int
    Number of penalty values to try for automatically generated tuning parameter sequence.

pen_vals: None, array-like
    (Optional) User provided penalty value sequence. The penalty sequence should be monotonicly decreasing so the homotopy path algorithm works propertly.

pen_min_mult: float
    Determines the smallest penalty value to try. The automatically generated penalty value squence lives in the interval [pen_min_mult * pen_max_val, pen_max_val] where pen_max_val is automatically determined.

pen_spacing: str
    How the penalty values are spaced. Must be one of ['log', 'lin']
    for logarithmic and linear spacing respectively.
""")


class GlmCVSinglePen(GlmCV):

    @add_init_params(GlmCV, add_first=False)
    def __init__(self,
                 n_pen_vals=100,
                 pen_vals=None,
                 pen_min_mult=1e-3,
                 pen_spacing='log'
                 ):
        pass

    def _set_tuning_values(self, X, y):

        if self.pen_vals is None:
            pen_val_max = self.estimator.get_pen_val_max(X, y)
        else:
            pen_val_max = None

        self.pen_val_seq_ = \
            get_pen_val_seq(pen_val_max,
                            n_pen_vals=self.n_pen_vals,
                            pen_vals=self.pen_vals,
                            pen_min_mult=self.pen_min_mult,
                            pen_spacing=self.pen_spacing)

    def get_tuning_sequence(self):
        """
        Returns a list of tuning parameter values.
        Make sure the method that computes the cross-validation results
        orders the parameters in the same order as get_tuning_sequence()
        Output
        ------
        values: iterable
        """
        return list(ParameterGrid(self.get_tuning_param_grid()))

    def get_tuning_param_grid(self):
        """
        Returns tuning parameter grid.

        Output
        ------
        param_grid: dict of lists
        """
        return {'pen_val': self.pen_val_seq_}

# TODO: perhaps move this somewhere else
def get_pen_val_seq(pen_val_max,
                    n_pen_vals=100,
                    pen_vals=None,
                    pen_min_mult=1e-3,
                    pen_spacing='log'):
    """
    Gets the penalty value seqence and makes sure it is in decreasing order.
    """
    if pen_vals is None:
        pen_val_seq = get_sequence_decr_max(max_val=pen_val_max,
                                            min_val_mult=pen_min_mult,
                                            num=n_pen_vals,
                                            spacing=pen_spacing)
    else:
        pen_val_seq = np.array(pen_vals)

    pen_val_seq = np.sort(pen_val_seq)[::-1]  # ensure decreasing

    return pen_val_seq


GlmCVSinglePen.__doc__ = dedent(
    """
    Base class for penalized generalized linear model tuned with cross-validation.

    Parameters
    ----------
    {}

    {}
    """.format(_cv_params, _pen_seq_params)
)


_enet_cv_params = dedent("""

l1_ratio: float, str, list
    The l1_ratio value to use. If a float is provided then this parameter is fixed and not tuned over. If l1_ratio='tune' then the l1_ratio is tuned over using an automatically generated tuning parameter sequence. Alternatively, the user may provide a list of l1_ratio values to tune over.

n_l1_ratio_vals: int
    Number of l1_ratio values to tune over. The l1_ratio tuning sequence is a logarithmically spaced grid of values between 0 and 1 that has more values close to 1.

l1_ratio_min:
    The smallest l1_ratio value to tune over.
""")


class GlmCVENet(GlmCVSinglePen):

    @add_init_params(GlmCVSinglePen, add_first=False)
    def __init__(self,
                 # pen_min_mult=1e-4,  # make this more extreme for enet
                 l1_ratio=0.5,
                 n_l1_ratio_vals=10,
                 l1_ratio_min=0.1,
                 ):
        pass

    def _tune_l1_ratio(self):
        """
        Output
        ------
        yes_tune_l1_ratio: bool
            Whether or not we tune the l1_ratio parameter.
        """
        # Do we tune the l1_ratio
        if self.l1_ratio == 'tune' or hasattr(self.l1_ratio, '__len__'):
            return True
        else:
            return False

    def _tune_pen_val(self):
        """
        Output
        ------
        yes_tune_pen_val: bool
            Whether or not we tune the pen_val parameter.
        """

        # Do we tune the pen_vals
        if isinstance(self.pen_vals, Number):
            return False
        else:
            return True

    def _set_tuning_values(self, X, y):

        ##################################
        # setup l1_ratio tuning sequence #
        ##################################
        if self._tune_l1_ratio():
            l1_ratio_val = None

            if self.l1_ratio is not None and not self.l1_ratio == 'tune':
                # user specified values
                l1_ratio_seq = np.array(self.l1_ratio).reshape(-1)

            else:
                # otherwise set these values by default
                l1_ratio_seq = \
                    get_enet_ratio_seq(min_val=self.l1_ratio_min,
                                       num=self.n_l1_ratio_vals)

            self.l1_ratio_seq_ = l1_ratio_seq

        else:
            l1_ratio_val = self.l1_ratio
            l1_ratio_seq = None

        #################################
        # setup pen_val tuning sequence #
        #################################
        if self._tune_pen_val():

            if self.pen_vals is None:
                lasso_pen_val_max = self.estimator.get_pen_val_max(X, y)
                lasso_pen_val_max *= self.estimator.l1_ratio
            else:
                lasso_pen_val_max = None

            self.pen_val_seq_ = \
                get_enet_pen_val_seq(lasso_pen_val_max=lasso_pen_val_max,
                                     pen_vals=self.pen_vals,
                                     n_pen_vals=self.n_pen_vals,
                                     pen_min_mult=self.pen_min_mult,
                                     pen_spacing=self.pen_spacing,
                                     l1_ratio_seq=l1_ratio_seq,
                                     l1_ratio_val=l1_ratio_val)

    def get_tuning_param_grid(self):
        if self._tune_l1_ratio() and self._tune_pen_val():
            return self.get_tuning_sequence()

        elif self._tune_l1_ratio():
            return {'l1_ratio': self.l1_ratio_seq_}

        elif self._tune_pen_val():
            return {'pen_val': self.pen_val_seq_}

    def get_tuning_sequence(self):
        """
        Returns a list of tuning parameter values.

        Output
        ------
        values: iterable
        """
        if self._tune_l1_ratio() and self._tune_pen_val():
            n_l1_ratios, n_pen_vals = self.pen_val_seq_.shape

            # outer loop over l1_ratios, inner loop over pen_vals
            param_list = []
            for l1_idx in range(n_l1_ratios):
                l1_ratio_val = self.l1_ratio_seq_[l1_idx]

                for pen_idx in range(n_pen_vals):
                    pen_val = self.pen_val_seq_[l1_idx, pen_idx]

                    param_list.append({'l1_ratio': l1_ratio_val,
                                       'pen_val': pen_val})

            return param_list

        elif self._tune_l1_ratio():
            param_grid = {'l1_ratio': self.l1_ratio_seq_}
            return list(ParameterGrid(param_grid))

        elif self._tune_pen_val():
            param_grid = {'pen_val': self.pen_val_seq_}
            return list(ParameterGrid(param_grid))


GlmCVENet.__doc__ = dedent(
    """
    Elastic Net penalized generalized linear model tuned with cross-validation.

    Parameters
    ----------
    {}

    {}

    {}
    """.format(_cv_params, _pen_seq_params, _enet_cv_params)
)


def get_enet_pen_val_seq(lasso_pen_val_max,
                         pen_vals=None, n_pen_vals=100,
                         pen_min_mult=1e-3, pen_spacing='log',
                         l1_ratio_seq=None, l1_ratio_val=None):
    """
    Sets up the pen_val tuning sequence for eleastic net.
    """
    # only one of these should be not None
    assert sum((l1_ratio_val is None, l1_ratio_seq is None)) <= 2

    # formatting
    if l1_ratio_val is not None:
        tune_l1_ratio = False
        l1_ratio_min = l1_ratio_val
    else:
        tune_l1_ratio = True
        l1_ratio_min = min(l1_ratio_seq)

    if pen_vals is not None:  # user provided pen vals
        pen_vals = np.array(pen_vals)

    else:  # automatically derive tuning sequence

        if l1_ratio_min <= np.finfo(float).eps:
            raise ValueError("Unable to set pen_val_seq using default"
                             "when the l1_ratio is zero."
                             " Either change thel1_ratio, or "
                             "input a sequence of pen_vals yourself!")

        if tune_l1_ratio:
            # setup grid of pen vals for each l1 ratio

            n_l1_ratio_vals = len(l1_ratio_seq)
            pen_vals = np.zeros((n_l1_ratio_vals, n_pen_vals))
            for l1_idx in range(n_l1_ratio_vals):

                # largest pen val for ElasticNet given this l1_ratio
                max_val = lasso_pen_val_max / l1_ratio_seq[l1_idx]

                pen_vals[l1_idx, :] = \
                    get_sequence_decr_max(max_val=max_val,
                                          min_val_mult=pen_min_mult,
                                          num=n_pen_vals,
                                          spacing=pen_spacing)

        else:
            # setup pen val sequence

            max_val = lasso_pen_val_max / l1_ratio_val
            pen_vals = \
                get_sequence_decr_max(max_val=max_val,
                                      min_val_mult=pen_min_mult,
                                      num=n_pen_vals,
                                      spacing=pen_spacing)

    # ensure correct ordering
    if tune_l1_ratio:
        assert pen_vals.ndim == 2
        assert pen_vals.shape[0] == len(l1_ratio_seq)

        # make sure pen vals are always in decreasing order
        for l1_idx in range(pen_vals.shape[0]):
            pen_vals[l1_idx, :] = np.sort(pen_vals[l1_idx, :])[::-1]

    else:
        # make sure pen vals are always in decreasing order
        pen_vals = np.sort(np.array(pen_vals))[::-1]
        pen_vals = pen_vals.reshape(-1)

    return pen_vals
