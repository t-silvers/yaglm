from sklearn.base import BaseEstimator
from sklearn.utils.validation import check_is_fitted
from sklearn.utils.extmath import safe_sparse_dot
from sklearn.utils.validation import check_array, FLOAT_DTYPES

import numpy as np
from textwrap import dedent

from ya_glm.autoassign import autoassign
from ya_glm.processing import process_X, deprocess_fit


_glm_base_params = dedent("""
    fit_intercept: bool
        Whether or not to fit an intercept.

    standardize: bool
        Whether or not to perform internal standardization before fitting the data. Here standardization means mean centering and scaling each column by its standard deviation. Putting each column on the same scale makes sense for fitting penalized models. Note the fitted coefficient/intercept is transformed to be on the original scale of the input data.

    opt_kws: dict
        Keyword arguments to the glm solver optimization algorithm.
    """)


class Glm(BaseEstimator):

    # subclass should implement
    solve_glm = None

    @autoassign
    def __init__(self, fit_intercept=True, standardize=False, opt_kws={}):
        pass

    def fit(self, X, y):
        """
        Fits the GLM.

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            The training covariate data.

        y: array-like, shape (n_samples, )
            The training response data.
        """

        X, y = self._validate_data(X, y)

        # TODO: do we want to give the user the option to not copy?
        X, y, pre_pro_out = self.preprocess(X, y, copy=True)

        coef, intercept, out_data = self.solve(X=X, y=y,
                                               **self._get_solve_kws())

        self._set_fit(fit_out={'coef': coef, 'intercept': intercept,
                               'out_data': out_data},
                      pre_pro_out=pre_pro_out)
        return self

    def _validate_data(self, X, y, accept_sparse=False):
        """
        Validates the X/y data. This should not change the raw input data, but may reformat the data (e.g. convert pandas to numpy).

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            The covariate data.

        y: array-like, shape (n_samples, ) or (n_samples, n_responses)
            The response data.
        """

        # TODO: waht to do about sparse???
        X = check_array(X, accept_sparse=accept_sparse,
                        dtype=FLOAT_DTYPES)

        # make sure y is numpy and of same dtype as X
        y = np.asarray(y, dtype=X.dtype)

        # make sure X, y have same number of samples
        if y.shape[0] != X.shape[0]:
            raise ValueError("X and y must have the same number of rows!")

        return X, y

    def preprocess(self, X, y, copy=True):
        """
        Preprocesses the data for fitting. This method may transform the data e.g. centering and scaling X.

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            The covariate data.

        y: array-like, shape (n_samples, ) or (n_samples, n_responses)
            The response data.

        copy: bool
            Whether or not to copy the X/y arrays or modify them in place.

        Output
        ------
        X_pro, y_pro, pre_pro_out

        X_pro: array-like, shape (n_samples, n_features)
            The possibly transformed covariate data.

        y_pro: array-like, shape (n_samples, )
            The possibly transformed response data.

        pro_pro_out: dict
            Data from preprocessing e.g. X_center, X_scale.
        """

        X, out = process_X(X,
                           standardize=self.standardize,
                           copy=copy,
                           check_input=False,
                           accept_sparse=False,  # TODO!
                           allow_const_cols=not self.fit_intercept)

        y, y_out = self._process_y(y, copy=copy)
        out.update(y_out)

        return X, y, out

    def _set_fit(self, fit_out, pre_pro_out):
        """
        Sets the fit.

        Parameters
        ----------
        fit_out: dict
            Contains the output of solve e.g.
            fit_out['coef'], fit_out['intercept'], fit_out['opt_data']

        pre_pro_out: None, dict
            Output of preprocess
        """
        coef = fit_out['coef']
        intercept = fit_out.pop('intercept', None)

        self.coef_, self.intercept_ = \
            deprocess_fit(coef=coef,
                          intercept=intercept,
                          pre_pro_out=pre_pro_out,
                          fit_intercept=self.fit_intercept)

        if 'opt_data' in fit_out:
            self.opt_data_ = fit_out['opt_data']

        # for classification models
        if 'classes' in pre_pro_out:
            self.classes_ = pre_pro_out['classes']

    def _decision_function(self, X):
        """
        The GLM decision function i.e. z = X.T @ coef + interept

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            The covariate data.

        Output
        ------
        z: array-like, shape (n_samples, )
            The decision function values.
        """
        check_is_fitted(self)

        X = check_array(X, accept_sparse=['csr', 'csc', 'coo'])
        z = safe_sparse_dot(X, self.coef_, dense_output=True) \
            + self.intercept_

        # if hasattr(self, 'intercept_'):
        #     z += self.intercept_

        return z

    def decision_function(self, X):
        """
        The GLM decision function i.e. z = X.T @ coef + interept

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            The covariate data.

        Output
        ------
        z: array-like, shape (n_samples, )
            The decision function values.
        """
        return self._decision_function(X)

    def _more_tags(self):
        return {'requires_y': True}

    def get_pen_val_max(self, X, y):
        """
        Returns the largest reasonable penalty parameter for the processed data.

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            The training covariate data.

        y: array-like, shape (n_samples, )
            The training response data.

        Output
        ------
        pen_val_max: float
            Largest reasonable tuning parameter value.
        """
        X_pro, y_pro, _ = self.preprocess(X, y, copy=True)
        return self._get_pen_val_max_from_pro(X_pro, y_pro)

    def _process_y(self, y, copy=True):
        """
        Parameters
        ---------
        y: array-like, shape (n_samples, ) or (n_samples, n_responses)
            The response data.

        Output
        ------
        y: array-like
            The possibly transformed response data.
        """
        raise NotImplementedError

    def _get_solve_kws(self):
        """
        solve_glm is called as solve_glm(X=X, y=y, **kws)
        """
        raise NotImplementedError

    def _get_pen_val_max_from_pro(self, X, y):
        """
        Computes the largest reasonable tuning parameter value.
        """
        raise NotImplementedError

    def get_loss_info(self):
        """
        Gets information about the loss function.

        Parameters
        ----------
        loss_func: str
            Which type of loss function.

        loss_kws: dict
            Keyword arguments for the loss function.
        """
        raise NotImplementedError


Glm.__doc__ = dedent(
    """
    Base class for Lasso generalized linear model.

    Parameters
    ----------
    {}
    """.format(_glm_base_params)
)
