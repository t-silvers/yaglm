from ya_glm.config.penalty import NoPenalty
from ya_glm.config.penalty import Ridge as RidgeConfig
from ya_glm.config.penalty import GeneralizedRidge as GeneralizedRidgeConfig
from ya_glm.config.penalty import Lasso as LassoConfig
from ya_glm.config.penalty import GroupLasso as GroupLassoConfig
from ya_glm.config.penalty import \
     ExclusiveGroupLasso as ExclusiveGroupLassoConfig
from ya_glm.config.penalty import MultiTaskLasso as MultiTaskLassoConfig
from ya_glm.config.penalty import NuclearNorm as NuclearNormConfig
from ya_glm.config.penalty import FusedLasso as FusedLassoConfig
from ya_glm.config.penalty import GeneralizedLasso as GeneralizedLassoConfig
from ya_glm.config.penalty import ElasticNet as ElasticNetConfig
from ya_glm.config.penalty import GroupElasticNet as GroupElasticNetConfig
from ya_glm.config.penalty import MultiTaskElasticNet as \
    MultiTaskElasticNetConfig
from ya_glm.config.penalty import SparseGroupLasso as SparseGroupLassoConfig
from ya_glm.config.penalty import SeparableSum as SeparableSumConfig
# from ya_glm.config.penalty import InifmalSum as InifmalSumConfig
from ya_glm.config.penalty import OverlappingSum as OverlappingSumConfig

from ya_glm.opt.base import Zero, Sum
from ya_glm.opt.BlockSeparable import BlockSeparable
from ya_glm.opt.penalty.convex import Ridge, GeneralizedRidge,\
     Lasso, GroupLasso, ExclusiveGroupLasso, \
     MultiTaskLasso, NuclearNorm, GeneralizedLasso, \
     ElasticNet, GroupElasticNet, MultiTaskElasticNet, SparseGroupLasso
from ya_glm.opt.penalty.nonconvex import get_nonconvex_func
from ya_glm.opt.penalty.composite_structured import CompositeGroup, \
    CompositeMultiTaskLasso, CompositeNuclearNorm, CompositeGeneralizedLasso
from ya_glm.opt.penalty.utils import MatWithIntercept, WithIntercept

from ya_glm.utils import is_str_and_matches
from ya_glm.trend_filtering import get_tf_mat, get_graph_tf_mat
from ya_glm.config.base_penalty import get_flavor_kind


def get_penalty_func(config, n_features=None, n_responses=None):
    """
    Gets a penalty function from a PenaltyConfig object.

    Parameters
    ----------
    config: PenaltyConfig
        The penalty congig object.

    n_features: None, int
        (Optional) Number of features the penalty will be applied to. This is only needed for the fused Lasso and the

    Output
    ------
    func: ya_glm.opt.base.Func
        The penalty function
    """

    flavor_kind = get_flavor_kind(config)

    # no penalty!
    if config is None or isinstance(config, NoPenalty):
        return Zero()

    # Ridge penalty
    elif isinstance(config, RidgeConfig):
        return Ridge(pen_val=config.pen_val, weights=config.weights)

    # Generalized ridge penalty
    elif isinstance(config, GeneralizedRidgeConfig):
        return GeneralizedRidge(pen_val=config.pen_val,
                                mat=config.mat)

    # Entrywise penalties e.g. lasso, SCAD, etc
    elif isinstance(config, LassoConfig):
        if flavor_kind == 'non_convex':
            return get_outer_nonconvex_func(config)
        else:

            return Lasso(pen_val=config.pen_val, weights=config.weights)

    # Group penalties e.g. group lasso, group scad etc
    elif isinstance(config, GroupLassoConfig):
        if flavor_kind == 'non_convex':
            # get non-convex func
            nc_func = get_outer_nonconvex_func(config)
            return CompositeGroup(groups=config.groups,
                                  func=nc_func)
        else:
            return GroupLasso(groups=config.groups,
                              pen_val=config.pen_val,
                              weights=config.weights)

    # Exclusive group lasso
    elif isinstance(config, ExclusiveGroupLassoConfig):
        if flavor_kind is not None:
            raise NotImplementedError()

        return ExclusiveGroupLasso(groups=config.groups,
                                   pen_val=config.pen_val)

    # Multitask e.g. multi-task lasso, multi-task scad etc
    elif isinstance(config, MultiTaskLassoConfig):

        if flavor_kind == 'non_convex':
            # get non-convex func
            nc_func = get_outer_nonconvex_func(config)
            return CompositeMultiTaskLasso(func=nc_func)
        else:
            return MultiTaskLasso(pen_val=config.pen_val,
                                  weights=config.weights)

    # Nuclear norm, adaptive nuclear norm or non-convex nuclear norm
    elif isinstance(config, NuclearNormConfig):
        if flavor_kind == 'non_convex':
            # get non-convex func
            nc_func = get_outer_nonconvex_func(config)
            return CompositeNuclearNorm(func=nc_func)

        else:
            return NuclearNorm(pen_val=config.pen_val,
                               weights=config.weights)

    # Generalized and fused lasso
    elif isinstance(config, (FusedLassoConfig, GeneralizedLassoConfig)):
        # TODO: perhaps add separate TV-1

        if isinstance(config, FusedLassoConfig):
            mat = get_fused_lasso_diff_mat(config=config, n_nodes=n_features)
        else:
            mat = config.mat

        if flavor_kind == 'non_convex':
            nc_func = get_outer_nonconvex_func(config)
            return CompositeGeneralizedLasso(func=nc_func, mat=mat)
        else:
            return GeneralizedLasso(pen_val=config.pen_val,
                                    mat=mat,
                                    weights=config.weights)

    # Elastic Net
    elif isinstance(config, ElasticNetConfig):

        if flavor_kind == 'non_convex':
            raise NotImplementedError("TODO: add")

        else:

            return ElasticNet(pen_val=config.pen_val,
                              mix_val=config.mix_val,
                              lasso_weights=config.lasso_weights,
                              ridge_weights=config.ridge_weights
                              )

    # Group Elastic net
    elif isinstance(config, GroupElasticNetConfig):
        if flavor_kind == 'non_convex':
            raise NotImplementedError("TODO: add")

        else:
            return GroupElasticNet(groups=config.groups,
                                   pen_val=config.pen_val,
                                   mix_val=config.mix_val,
                                   lasso_weights=config.lasso_weights,
                                   ridge_weights=config.ridge_weights
                                   )

    # Multi-task elastic net
    elif isinstance(config, MultiTaskElasticNetConfig):
        if flavor_kind == 'non_convex':
            raise NotImplementedError("TODO: add")

        else:
            return MultiTaskElasticNet(pen_val=config.pen_val,
                                       mix_val=config.mix_val,
                                       lasso_weights=config.lasso_weights,
                                       ridge_weights=config.ridge_weights
                                       )

    # Sparse group lasso
    elif isinstance(config, SparseGroupLassoConfig):

        if flavor_kind == 'non_convex':
            raise NotImplementedError("TODO")

        else:
            return SparseGroupLasso(groups=config.groups,
                                    pen_val=config.pen_val,
                                    mix_val=config.mix_val,
                                    sparse_weights=config.sparse_weights,
                                    group_weights=config.group_weights)

    # Overlapping sum
    elif isinstance(config, OverlappingSumConfig):
        funcs = [get_penalty_func(c, n_features)
                 for c in config.get_penalties().values()]
        return Sum(funcs=funcs)

    # Separable sum
    elif isinstance(config, SeparableSumConfig):
        funcs = [get_penalty_func(c, n_features)
                 for c in config.get_penalties().values()]

        groups = [grp_idxs for grp_idxs in config.get_groups().values()]

        return BlockSeparable(funcs=funcs, groups=groups)

    else:
        raise NotImplementedError("{} is not currently supported by "
                                  "ya_glm.opt.penalty".
                                  format(config))


def split_smooth_and_non_smooth(func):
    """
    Splits a penalty function into smooth and non-smooth functions.

    Parameters
    ----------
    func: Func
        The input function to split

    Output
    ------
    smooth, non_smooth
    """
    if isinstance(func, Sum):

        # pull apart smooth and non-smooth functions
        smooth_funcs = [f for f in func.funcs if f.is_smooth]
        non_smooth_funcs = [f for f in func.funcs if not f.is_smooth]

        if len(smooth_funcs) == 1:
            smooth = smooth_funcs[0]
        elif len(smooth_funcs) > 1:
            smooth = Sum(smooth_funcs)
        else:
            # smooth = Zero()
            smooth = None

        if len(smooth_funcs) == 1:
            non_smooth = non_smooth_funcs[0]

        elif len(non_smooth_funcs) >= 1:
            non_smooth = Sum(non_smooth_funcs)
        else:
            # non_smooth = Zero()
            non_smooth = None

        return smooth, non_smooth

    elif isinstance(func, BlockSeparable):
        smooth_funcs = []
        smooth_groups = []
        non_smooth_funcs = []
        non_smooth_groups = []

        # pull apart smooth and non-smooth functions
        for i, (func, group) in enumerate(zip(func.funcs, func.groups)):

            if func.is_smooth:
                smooth_funcs.append(func)
                smooth_groups.append(group)

            else:
                non_smooth_funcs.append(func)
                non_smooth_groups.append(group)

        if len(smooth_funcs) >= 1:
            smooth = BlockSeparable(funcs=smooth_funcs,
                                    groups=smooth_groups)
        else:
            # smooth = Zero()
            smooth = None

        if len(non_smooth_funcs) >= 1:
            non_smooth = BlockSeparable(funcs=non_smooth_funcs,
                                        groups=non_smooth_groups)
        else:
            # non_smooth = Zero()
            non_smooth = None

        return smooth, non_smooth

    else:
        smooth = None
        non_smooth = None
        # smooth = Zero()
        # non_smooth = Zero()

        if func.is_smooth:
            smooth = func

        return smooth, non_smooth


def get_outer_nonconvex_func(config):
    """
    Returns the non-convex function used in a non-convex penalty. If the overall penalty is a composition, p(coef) = non-convex(t(coef)), this returns the final non-convex function.

    Parameters
    ----------
    config: PenaltyConfig
        A non-convex penalty config.

    Output
    ------
    func: ya_glm.opt.base.func
        The non-convex function.
    """
    if get_flavor_kind(config) != 'non_convex':
        raise ValueError("Penalty is not non_convex")

    return get_nonconvex_func(name=config.flavor.pen_func,
                              pen_val=config.pen_val,
                              second_param=config.flavor.
                              second_param_val)


def wrap_intercept(func, fit_intercept, is_mr):
    """

    Parameters
    ----------
    config: PenaltyConfig
        The penalty congig object.
    """

    if fit_intercept:
        if is_mr:
            return MatWithIntercept(func=func)

        else:
            return WithIntercept(func=func)

    else:
        return func


def get_fused_lasso_diff_mat(config, n_nodes):
    """
    Returns the generalized lasso difference matrix for the fused lasso.

    Parameters
    ----------
    config: FusedLasso
        The fused lasso config.

    n_nodes: int
        The number of nodes in the graph.

    Output
    ------
    mat: array-like, (n_rows, n_nodes)
        The difference matrix as a sparse matrix.
    """

    assert isinstance(config, FusedLassoConfig)

    if is_str_and_matches(config.edgelist, 'chain'):
        return get_tf_mat(d=n_nodes, k=config.order)
    else:
        return get_graph_tf_mat(edgelist=config.edgelist,
                                n_nodes=n_nodes,
                                k=config.order)
