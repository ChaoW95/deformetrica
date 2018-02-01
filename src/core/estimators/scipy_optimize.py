import os.path
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '../../../')

import numpy as np
from scipy.optimize import minimize
import _pickle as pickle
from decimal import Decimal

from pydeformetrica.src.core.estimators.abstract_estimator import AbstractEstimator
from pydeformetrica.src.support.utilities.general_settings import Settings


class ScipyOptimize(AbstractEstimator):
    """
    ScipyOptimize object class.
    An estimator is an algorithm which updates the fixed effects of a statistical model.

    """

    ####################################################################################################################
    ### Constructor:
    ####################################################################################################################

    def __init__(self):
        AbstractEstimator.__init__(self)
        self.name = 'ScipyOptimize'
        self.method = 'L-BFGS-B'

        self.memory_length = None
        self.parameters_shape = None
        self.max_line_search_iterations = None

        self._gradient_memory = None

    ####################################################################################################################
    ### Public methods:
    ####################################################################################################################

    def update(self):
        """
        Runs the scipy optimize routine and updates the statistical model.
        """

        # Initialisation -----------------------------------------------------------------------------------------------
        # First case: we use what's stored in the state file
        if Settings().load_state:
            x0, self.current_iteration, self.parameters_shape = self._load_state_file()
            self._set_parameters(self._unvectorize_parameters(x0))  # Propagate the parameter values.
            print("State file loaded, it was at iteration", self.current_iteration)

        # Second case: we use the native initialisation of the model.
        else:
            parameters = self._get_parameters()
            self.current_iteration = 0

            self.parameters_shape = {key: value.shape for key, value in parameters.items()}
            x0 = self._vectorize_parameters(parameters)

        # Main loop ----------------------------------------------------------------------------------------------------
        print('')
        print('>> Scipy optimization method: ' + self.method)
        print('')
        self.print()
        self.current_iteration = 1

        if self.method == 'L-BFGS-B':
            result = minimize(self._cost_and_derivative, x0.astype('float64'),
                              method='L-BFGS-B', jac=True, callback=self._callback,
                              options={
                                  # No idea why the '-2' is necessary.
                                  'maxiter': self.max_iterations - 2 - (self.current_iteration - 1),
                                  'maxls': self.max_line_search_iterations,
                                  'ftol': self.convergence_tolerance,
                                  # Number of previous gradients used to approximate the Hessian.
                                  'maxcor': self.memory_length,
                                  'disp': False
                              })

        elif self.method == 'Powell':
            result = minimize(self._cost, x0.astype('float64'),
                              method='Powell', tol=self.convergence_tolerance, callback=self._callback,
                              options={
                                  'maxiter': self.max_iterations - (self.current_iteration - 1),
                                  'disp': True
                              })

        else:
            raise RuntimeError('Unknown optimization method.')

        # Finalization -------------------------------------------------------------------------------------------------
        self._set_parameters(self._unvectorize_parameters(result.x))  # Probably already done in _callback.

        if self.method == 'L-BFGS-B':
            print('>> ' + result.message.decode("utf-8"))

    def print(self):
        """
        Print information.
        """
        print('------------------------------------- Iteration: ' + str(self.current_iteration)
              + ' -------------------------------------')

        if self.method == 'Powell':
            attachment, regularity = self.statistical_model.compute_log_likelihood(
                self.dataset, self.population_RER, self.individual_RER, with_grad=False)
            print('>> Log-likelihood = %.3E \t [ attachment = %.3E ; regularity = %.3E ]' %
                  (Decimal(str(attachment + regularity)),
                   Decimal(str(attachment)),
                   Decimal(str(regularity))))

        print('')

    def write(self):
        """
        Save the results.
        """
        self.statistical_model.write(self.dataset, self.population_RER, self.individual_RER)

    ####################################################################################################################
    ### Private methods:
    ####################################################################################################################

    def _cost(self, x):
        # Propagates the parameter value to all necessary attributes.
        self._set_parameters(self._unvectorize_parameters(x))

        # Call the model method.
        try:
            attachment, regularity = self.statistical_model.compute_log_likelihood(
                self.dataset, self.population_RER, self.individual_RER, with_grad=False)

        except ValueError as error:
            print('>> ' + str(error))
            return np.float64(float('inf'))

        # Prepare the outputs: notably linearize and concatenates the gradient.
        cost = - attachment - regularity

        # Return.
        return cost.astype('float64')

    def _cost_and_derivative(self, x):
        # Propagates the parameter value to all necessary attributes.
        self._set_parameters(self._unvectorize_parameters(x))

        # Call the model method.
        try:
            attachment, regularity, gradient = self.statistical_model.compute_log_likelihood(
                self.dataset, self.population_RER, self.individual_RER, with_grad=True)

        except ValueError as error:
            print('>> ' + str(error))
            return np.float64(float('inf')), self._gradient_memory

        # Print.
        print('>> Log-likelihood = %.3E \t [ attachment = %.3E ; regularity = %.3E ]' %
              (Decimal(str(attachment + regularity)),
               Decimal(str(attachment)),
               Decimal(str(regularity))))

        # Prepare the outputs: notably linearize and concatenates the gradient.
        cost = - attachment - regularity
        gradient = - np.concatenate([value.flatten() for value in gradient.values()])

        # Memory for exception handling. 
        self._gradient_memory = gradient.astype('float64')

        # Return.
        return cost.astype('float64'), gradient.astype('float64')

    def _callback(self, x):
        # Propagate the parameters to all necessary attributes.
        self._set_parameters(self._unvectorize_parameters(x))

        # Print and save.
        if not self.current_iteration % self.print_every_n_iters: self.print()
        if not self.current_iteration % self.save_every_n_iters: self.write()
        if not self.current_iteration % self.save_every_n_iters: self._dump_state_file(x)

        self.current_iteration += 1

    def _get_parameters(self):
        """
        Return a dictionary of numpy arrays.
        """
        out = self.statistical_model.get_fixed_effects()
        out.update(self.population_RER)
        out.update(self.individual_RER)
        assert len(out) == len(self.statistical_model.get_fixed_effects()) \
                           + len(self.population_RER) + len(self.individual_RER)
        return out

    def _vectorize_parameters(self, parameters):
        """
        Returns a 1D numpy array from a dictionary of numpy arrays.
        """
        return np.concatenate([value.flatten() for value in parameters.values()])

    def _unvectorize_parameters(self, x):
        """
        Recover the structure of the parameters
        """
        parameters = {}
        cursor = 0
        for key, shape in self.parameters_shape.items():
            length = np.prod(shape)
            parameters[key] = x[cursor:cursor + length].reshape(shape)
            cursor += length
        return parameters

    def _set_parameters(self, parameters):
        """
        Updates the model and the random effect realization attributes.
        """
        fixed_effects = {key: parameters[key] for key in self.statistical_model.get_fixed_effects().keys()}
        self.statistical_model.set_fixed_effects(fixed_effects)
        self.population_RER = {key: parameters[key] for key in self.population_RER.keys()}
        self.individual_RER = {key: parameters[key] for key in self.individual_RER.keys()}

    def _load_state_file(self):
        """
        loads Settings().state_file and returns what's necessary to restart the scipy optimization.
        """
        d = pickle.load(open(Settings().state_file, 'rb'))
        return d['parameters'], d['current_iteration'], d['parameters_shape']

    def _dump_state_file(self, parameters):
        """
        Dumps the state file with the new value of $x_0$ as argument.
        """
        d = {'parameters': parameters, 'current_iteration': self.current_iteration,
             'parameters_shape': self.parameters_shape}
        pickle.dump(d, open(Settings().state_file, 'wb'))
