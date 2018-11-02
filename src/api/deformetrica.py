import logging
import math
import os
import time
from sys import platform

import torch

from core import default
from core.default import logger_format
from core.estimators.gradient_ascent import GradientAscent
from core.estimators.mcmc_saem import McmcSaem
from core.estimators.scipy_optimize import ScipyOptimize
from core.models.affine_atlas import AffineAtlas
from core.models.bayesian_atlas import BayesianAtlas
from core.models.deterministic_atlas import DeterministicAtlas
from core.models.geodesic_regression import GeodesicRegression
from core.models.longitudinal_atlas import LongitudinalAtlas
from in_out.dataset_functions import create_dataset
from in_out.deformable_object_reader import DeformableObjectReader
from launch.compute_parallel_transport import compute_parallel_transport
from launch.compute_shooting import compute_shooting
from launch.estimate_longitudinal_registration import estimate_longitudinal_registration
from core.models.principal_geodesic_analysis import PrincipalGeodesicAnalysis
from support.probability_distributions.multi_scalar_normal_distribution import MultiScalarNormalDistribution

logger = logging.getLogger(__name__)


class Deformetrica:
    ####################################################################################################################
    # Constructor & destructor.
    ####################################################################################################################

    def __init__(self, output_dir=default.output_dir, verbosity='DEBUG'):
        self.output_dir = output_dir

        # create output dir if it does not already exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # set logging level
        try:
            log_level = logging.getLevelName(verbosity)
            logging.basicConfig(level=log_level, format=logger_format)
        except ValueError:
            logger.warning('Logging level was not recognized. Using INFO.')
            log_level = logging.INFO

        logger.debug('Using verbosity level: ' + verbosity)
        logging.basicConfig(level=log_level, format=logger_format)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        logger.debug('Deformetrica.__exit__()')
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    ####################################################################################################################
    # Main methods.
    ####################################################################################################################

    def estimate_registration(self, template_specifications, dataset_specifications,
                              model_options={}, estimator_options={}, write_output=True):
        """
        Estimate registration.
        """
        # Check and completes the input parameters.
        template_specifications, model_options, estimator_options = self.further_initialization(
            'Registration', template_specifications, model_options, dataset_specifications, estimator_options)

        # Instantiate dataset.
        dataset = create_dataset(template_specifications,
                                 dimension=model_options['dimension'], **dataset_specifications)
        assert (dataset.is_cross_sectional()), "Cannot estimate an atlas from a non-cross-sectional dataset."

        # Instantiate model.
        statistical_model = DeterministicAtlas(template_specifications, dataset.number_of_subjects, **model_options)
        statistical_model.initialize_noise_variance(dataset)

        # Instantiate estimator.
        estimator = self.__instantiate_estimator(statistical_model, dataset, estimator_options, default=ScipyOptimize)

        # Launch.
        self.__launch_estimator(estimator, write_output)

        return statistical_model

    def estimate_deterministic_atlas(self, template_specifications, dataset_specifications,
                                     model_options={}, estimator_options={}, write_output=True):
        """
        Estimate deterministic atlas.
        """

        # Check and completes the input parameters.
        template_specifications, model_options, estimator_options = self.further_initialization(
            'DeterministicAtlas', template_specifications, model_options, dataset_specifications, estimator_options)

        print(estimator_options)

        # Instantiate dataset.
        dataset = create_dataset(template_specifications,
                                 dimension=model_options['dimension'], **dataset_specifications)
        assert (dataset.is_cross_sectional()), "Cannot estimate an atlas from a non-cross-sectional dataset."

        # Instantiate model.
        statistical_model = DeterministicAtlas(template_specifications, dataset.number_of_subjects, **model_options)
        statistical_model.initialize_noise_variance(dataset)

        # Instantiate estimator.
        estimator = self.__instantiate_estimator(statistical_model, dataset, estimator_options, default=ScipyOptimize)

        # Launch.
        self.__launch_estimator(estimator, write_output)

        return statistical_model

    def estimate_bayesian_atlas(self, template_specifications, dataset_specifications,
                                model_options={}, estimator_options={}, write_output=True):
        """
        Estimate bayesian atlas.
        """
        # Check and completes the input parameters.
        template_specifications, model_options, estimator_options = self.further_initialization(
            'BayesianAtlas', template_specifications, model_options, dataset_specifications, estimator_options)

        # Instantiate dataset.
        dataset = create_dataset(template_specifications,
                                 dimension=model_options['dimension'], **dataset_specifications)
        assert (dataset.is_cross_sectional()), "Cannot estimate an atlas from a non-cross-sectional dataset."

        # Instantiate model.
        statistical_model = BayesianAtlas(template_specifications, **model_options)
        individual_RER = statistical_model.initialize_random_effects_realization(dataset.number_of_subjects,
                                                                                 **model_options)
        statistical_model.initialize_noise_variance(dataset, individual_RER)

        # Instantiate estimator.
        estimator_options['individual_RER'] = individual_RER
        estimator = self.__instantiate_estimator(statistical_model, dataset, estimator_options, default=ScipyOptimize)

        # Launch.
        self.__launch_estimator(estimator, write_output)

        return statistical_model, estimator.individual_RER

    def estimate_longitudinal_atlas(self, template_specifications, dataset_specifications,
                                    model_options={}, estimator_options={}, write_output=True):
        """
        Estimate longitudinal atlas.
        """

        # Check and completes the input parameters.
        template_specifications, model_options, estimator_options = self.further_initialization(
            'LongitudinalAtlas', template_specifications, model_options, dataset_specifications, estimator_options)

        # Instantiate dataset.
        dataset = create_dataset(template_specifications,
                                 dimension=model_options['dimension'], **dataset_specifications)
        assert (not dataset.is_cross_sectional() and not dataset.is_time_series()), \
            "Cannot estimate an atlas from a cross-sectional or time-series dataset."

        # Instantiate model.
        statistical_model = LongitudinalAtlas(template_specifications, **model_options)
        individual_RER = statistical_model.initialize_random_effects_realization(dataset.number_of_subjects,
                                                                                 **model_options)
        statistical_model.initialize_noise_variance(dataset, individual_RER)

        # Instantiate estimator.
        estimator_options['individual_RER'] = individual_RER
        estimator = self.__instantiate_estimator(statistical_model, dataset, estimator_options, default=McmcSaem)

        # Launch.
        self.__launch_estimator(estimator, write_output)

        return statistical_model

    def estimate_longitudinal_registration(self, template_specifications, dataset_specifications,
                                           model_options={}, estimator_options={},
                                           write_output=True, overwrite=True):
        """
        Estimate longitudinal registration.

        This function does not simply estimate a statistical model, but will succesively instantiate and estimate
        several, before gathering all the results in a common folder: that is why it calls a dedicated script.
        """
        """
        Estimate longitudinal registration.
        """

        # Check and completes the input parameters.
        template_specifications, model_options, estimator_options = self.further_initialization(
            'LongitudinalRegistration', template_specifications, model_options,
            dataset_specifications, estimator_options)

        # Launch the dedicated script.
        estimate_longitudinal_registration(template_specifications, dataset_specifications,
                                           model_options, estimator_options,
                                           output_dir=self.output_dir, overwrite=overwrite)

    def estimate_affine_atlas(self, template_specifications, dataset_specifications,
                              model_options={}, estimator_options={}, write_output=True):
        """
        Estimate affine atlas
        :return:
        """
        # Check and completes the input parameters.
        template_specifications, model_options, estimator_options = self.further_initialization(
            'AffineAtlas', template_specifications, model_options, dataset_specifications, estimator_options)

        # Instantiate dataset.
        dataset = create_dataset(template_specifications,
                                 dimension=model_options['dimension'], **dataset_specifications)

        # Instantiate model.
        statistical_model = AffineAtlas(dataset, template_specifications, **model_options)

        # instantiate estimator
        estimator = self.__instantiate_estimator(statistical_model, dataset, estimator_options, default=ScipyOptimize)

        self.__launch_estimator(estimator, write_output)

        return statistical_model

    def estimate_longitudinal_metric_model(self):
        """
        TODO
        :return:
        """
        raise NotImplementedError

    def estimate_longitudinal_metric_registration(self):
        """
        TODO
        :return:
        """
        raise NotImplementedError

    def estimate_geodesic_regression(self, template_specifications, dataset_specifications,
                                     model_options={}, estimator_options={}, write_output=True):
        """
        Estimate geodesic regression.
        """
        # Check and completes the input parameters.
        template_specifications, model_options, estimator_options = self.further_initialization(
            'Regression', template_specifications, model_options, dataset_specifications, estimator_options)

        # Instantiate dataset.
        dataset = create_dataset(template_specifications,
                                 dimension=model_options['dimension'], **dataset_specifications)
        assert (dataset.is_time_series()), "Cannot estimate a geodesic regression from a non-time-series dataset."

        # Instantiate model.
        statistical_model = GeodesicRegression(template_specifications, **model_options)
        statistical_model.initialize_noise_variance(dataset)

        # Instantiate estimator.
        estimator = self.__instantiate_estimator(statistical_model, dataset, estimator_options, default=ScipyOptimize)

        # Launch.
        self.__launch_estimator(estimator, write_output)

        return statistical_model

    def estimate_deep_pga(self):
        """
        TODO
        :return:
        """
        raise NotImplementedError

    def estimate_principal_geodesic_analysis(self, template_specifications, dataset_specifications,
                                           model_options={}, estimator_options={},
                                           write_output=True):
        """
        Estimate principal geodesic analysis
        """
        # Check and completes the input parameters.
        template_specifications, model_options, estimator_options = self.further_initialization(
            'LongitudinalAtlas', template_specifications, model_options, dataset_specifications, estimator_options)

        # Instantiate dataset.
        dataset = create_dataset(template_specifications,
                                 dimension=model_options['dimension'], **dataset_specifications)
        assert (dataset.is_cross_sectional()), \
            "Cannot estimate a PGA from a non cross-sectional dataset."

        # Instantiate model.
        statistical_model = PrincipalGeodesicAnalysis(template_specifications, **model_options)

        statistical_model.initialize_noise_variance(dataset)

        # Runs a tangent pca on a deterministic atlas to initialize
        individual_RER = statistical_model.initialize(dataset)

        # Instantiate estimator.
        estimator_options['individual_RER'] = individual_RER
        estimator = self.__instantiate_estimator(statistical_model, dataset, estimator_options, default=McmcSaem)

        # Launch.
        self.__launch_estimator(estimator, write_output)

        return statistical_model


        # statistical_model, individual_RER = instantiate_principal_geodesic_model(self, dataset, template_specifications,
        #                                                                          **model_options)
        #
        # # sanitize estimator_options
        # if 'output_dir' in estimator_options:
        #     raise RuntimeError('estimator_options cannot contain output_dir key')
        #
        # # instantiate estimator
        # estimator = estimator(statistical_model, dataset, output_dir=self.output_dir, individual_RER=individual_RER,
        #                       **estimator_options)
        #
        # """
        # Launch
        # """
        # self.__launch_estimator(estimator, write_output)
        #
        # return statistical_model

    def compute_parallel_transport(self, template_specifications, model_options={}, write_output=True):
        """
        Compute parallel transport.
        """

        # Check and completes the input parameters.
        template_specifications, model_options, _ = self.further_initialization(
            'ParallelTransport', template_specifications, model_options)

        # Launch.
        compute_parallel_transport(template_specifications, output_dir=self.output_dir, **model_options)

    def compute_shooting(self, template_specifications, model_options={}, write_output=True):
        """
        Compute shooting.
        """

        # Check and completes the input parameters.
        template_specifications, model_options, _ = self.further_initialization(
            'ParallelTransport', template_specifications, model_options)

        # Launch.
        compute_shooting(template_specifications, output_dir=self.output_dir, **model_options)

    ####################################################################################################################
    # Auxiliary methods.
    ####################################################################################################################

    @staticmethod
    def __launch_estimator(estimator, write_output=True):
        """
        Launch the estimator. This will iterate until a stop condition is reached.

        :param estimator:   Estimator that is to be used.
                            eg: :class:`GradientAscent <core.estimators.gradient_ascent.GradientAscent>`, :class:`ScipyOptimize <core.estimators.scipy_optimize.ScipyOptimize>`
        """
        start_time = time.time()
        logger.info('Started estimator: ' + estimator.name)
        estimator.update()
        end_time = time.time()

        if write_output:
            estimator.write()

        if end_time - start_time > 60 * 60 * 24:
            print('>> Estimation took: %s' %
                  time.strftime("%d days, %H hours, %M minutes and %S seconds", time.gmtime(end_time - start_time)))
        elif end_time - start_time > 60 * 60:
            print('>> Estimation took: %s' %
                  time.strftime("%H hours, %M minutes and %S seconds", time.gmtime(end_time - start_time)))
        elif end_time - start_time > 60:
            print('>> Estimation took: %s' %
                  time.strftime("%M minutes and %S seconds", time.gmtime(end_time - start_time)))
        else:
            print('>> Estimation took: %s' % time.strftime("%S seconds", time.gmtime(end_time - start_time)))

    def __instantiate_estimator(self, statistical_model, dataset, estimator_options, default=ScipyOptimize):
        if estimator_options['optimization_method_type'].lower() == 'GradientAscent'.lower():
            estimator = GradientAscent
        elif estimator_options['optimization_method_type'].lower() == 'ScipyLBFGS'.lower():
            estimator = ScipyOptimize
        elif estimator_options['optimization_method_type'].lower() == 'McmcSaem'.lower():
            estimator = McmcSaem
        else:
            estimator = default
        return estimator(statistical_model, dataset, output_dir=self.output_dir, **estimator_options)

    def further_initialization(self, model_type, template_specifications, model_options,
                               dataset_specifications=None, estimator_options=None):

        #
        # Consistency checks.
        #
        if dataset_specifications is None or estimator_options is None:
            assert model_type.lower() in ['Shooting'.lower(), 'ParallelTransport'.lower()], \
                'Only the "shooting" and "parallel transport" can run without a dataset and an estimator.'

        #
        # Initializes variables that will be checked.
        #
        if 'dimension' not in model_options:
            model_options['dimension'] = default.dimension
        if 'tensor_types' not in model_options:
            model_options['tensor_scalar_type'] = default.tensor_scalar_type
        if 'tensor_types' not in model_options:
            model_options['tensor_integer_type'] = default.tensor_integer_type
        if 'dense_mode' not in model_options:
            model_options['dense_mode'] = default.dense_mode
        if 'freeze_control_points' not in model_options:
            model_options['freeze_control_points'] = default.freeze_control_points
        if 'freeze_template' not in model_options:
            model_options['freeze_template'] = default.freeze_template
        if 'initial_control_points' not in model_options:
            model_options['initial_control_points'] = default.initial_control_points
        if 'initial_cp_spacing' not in model_options:
            model_options['initial_cp_spacing'] = default.initial_cp_spacing
        if 'deformation_kernel_width' not in model_options:
            model_options['deformation_kernel_width'] = default.deformation_kernel_width
        if 'deformation_kernel_type' not in model_options:
            model_options['deformation_kernel_type'] = default.deformation_kernel_type
        if 'number_of_threads' not in model_options:
            model_options['number_of_threads'] = default.number_of_threads
        if 't0' not in model_options:
            model_options['t0'] = default.t0
        if 'initial_time_shift_variance' not in model_options:
            model_options['initial_time_shift_variance'] = default.initial_time_shift_variance
        if 'initial_modulation_matrix' not in model_options:
            model_options['initial_modulation_matrix'] = default.initial_modulation_matrix
        if 'number_of_sources' not in model_options:
            model_options['number_of_sources'] = default.number_of_sources
        if 'initial_acceleration_variance' not in model_options:
            model_options['initial_acceleration_variance'] = default.initial_acceleration_variance
        if 'downsampling_factor' not in model_options:
            model_options['downsampling_factor'] = default.downsampling_factor
        if 'use_sobolev_gradient' not in model_options:
            model_options['use_sobolev_gradient'] = default.use_sobolev_gradient
        if 'sobolev_kernel_width_ratio' not in model_options:
            model_options['sobolev_kernel_width_ratio'] = default.sobolev_kernel_width_ratio

        if estimator_options is not None:
            if 'use_cuda' not in estimator_options:
                estimator_options['use_cuda'] = default.use_cuda
            if 'state_file' not in estimator_options:
                estimator_options['state_file'] = default.state_file
            if 'load_state_file' not in estimator_options:
                estimator_options['load_state_file'] = default.load_state_file
            if 'memory_length' not in estimator_options:
                estimator_options['memory_length'] = default.memory_length

        #
        # Global variables for this method.
        #

        if estimator_options is not None:
            cuda_is_used = estimator_options['use_cuda']
        else:
            cuda_is_used = False

        #
        # Check and completes the user-given parameters.
        #

        # If needed, infer the dimension from the template specifications.
        if model_options['dimension'] is None:
            model_options['dimension'] = self.__infer_dimension(template_specifications)

        # Smoothing kernel width.
        if model_options['use_sobolev_gradient']:
            model_options['smoothing_kernel_width'] = \
                model_options['deformation_kernel_width'] * model_options['sobolev_kernel_width_ratio']

        # Dense mode.
        if model_options['dense_mode']:
            print('>> Dense mode activated. No distinction will be made between template and control points.')
            assert len(template_specifications) == 1, \
                'Only a single object can be considered when using the dense mode.'
            if not model_options['freeze_control_points']:
                model_options['freeze_control_points'] = True
                msg = 'With active dense mode, the freeze_template (currently %s) and freeze_control_points ' \
                      '(currently %s) flags are redundant. Defaulting to freeze_control_poi∂nts = True.' \
                      % (str(model_options['freeze_template']), str(model_options['freeze_control_points']))
                print('>> ' + msg)
            if model_options['initial_control_points'] is not None:
                model_options['initial_control_points'] = None
                msg = 'With active dense mode, specifying initial_control_points is useless. Ignoring this xml entry.'
                print('>> ' + msg)

        if model_options['initial_cp_spacing'] is None and model_options['initial_control_points'] is None \
                and not model_options['dense_mode']:
            print('>> No initial CP spacing given: using diffeo kernel width of '
                  + str(model_options['deformation_kernel_width']))
            model_options['initial_cp_spacing'] = model_options['deformation_kernel_width']

        # We also set the type to FloatTensor if keops is used.
        def keops_is_used():
            if model_options['deformation_kernel_type'].lower() == 'keops':
                return True
            for elt in template_specifications.values():
                if 'kernel_type' in elt and elt['kernel_type'].lower() == 'keops':
                    return True
            return False

        if keops_is_used():
            assert platform not in ['darwin'], 'The "keops" kernel is not available with the Mac OS X platform.'

            print(">> KEOPS is used at least in one operation, all operations will be done with FLOAT precision.")
            model_options['tensor_scalar_type'] = torch.FloatTensor

            if torch.cuda.is_available():
                print('>> CUDA is available: the KEOPS backend will automatically be set to "gpu".')
                cuda_is_used = True
            else:
                print('>> CUDA seems to be unavailable: the KEOPS backend will automatically be set to "cpu".')

        # Setting tensor types according to CUDA availability and user choices.
        if cuda_is_used:

            if not torch.cuda.is_available():
                msg = 'CUDA seems to be unavailable. All computations will be carried out on CPU.'
                print('>> ' + msg)

            else:
                print(">> CUDA is used at least in one operation, all operations will be done with FLOAT precision.")
                if estimator_options is not None and estimator_options['use_cuda']:
                    print(">> All tensors will be CUDA tensors.")
                    model_options['tensor_scalar_type'] = torch.cuda.FloatTensor
                    model_options['tensor_integer_type'] = torch.cuda.LongTensor
                else:
                    print(">> Setting tensor type to float.")
                    model_options['tensor_scalar_type'] = torch.FloatTensor

        # Multi-threading/processing only available for the deterministic atlas for the moment.
        if model_options['number_of_threads'] > 1:

            if model_type.lower() in ['Shooting'.lower(), 'ParallelTransport'.lower(), 'Registration'.lower()]:
                model_options['number_of_threads'] = 1
                msg = 'It is not possible to estimate a "%s" model with multithreading. ' \
                      'Overriding the "number-of-threads" option, now set to 1.' % model_type
                print('>> ' + msg)

            elif model_type.lower() in ['BayesianAtlas'.lower(), 'Regression'.lower(),
                                        'LongitudinalAtlas'.lower(), 'LongitudinalRegistration'.lower()]:
                model_options['number_of_threads'] = 1
                msg = 'It is not possible at the moment to estimate a "%s" model with multithreading. ' \
                      'Overriding the "number-of-threads" option, now set to 1.' % model_type
                print('>> ' + msg)

        # Setting the number of threads in general settings
        if model_options['number_of_threads'] > 1:
            print(">> I will use", ['number_of_threads'],
                  "threads, and I set OMP_NUM_THREADS and torch_num_threads to 1.")
            os.environ['OMP_NUM_THREADS'] = "1"
            torch.set_num_threads(1)
        else:
            print('>> Setting OMP_NUM_THREADS and torch_num_threads to 4.')
            os.environ['OMP_NUM_THREADS'] = "4"
            torch.set_num_threads(4)

        # If longitudinal model and t0 is not initialized, initializes it.
        if model_type.lower() in ['Regression'.lower(),
                                  'LongitudinalAtlas'.lower(), 'LongitudinalRegistration'.lower()]:
            total_number_of_visits = 0
            mean_visit_age = 0.0
            var_visit_age = 0.0
            assert 'visit_ages' in dataset_specifications, 'Visit ages are needed to estimate a Regression, ' \
                                                           'Longitudinal Atlas or Longitudinal Registration model.'
            for i in range(len(dataset_specifications['visit_ages'])):
                for j in range(len(dataset_specifications['visit_ages'][i])):
                    total_number_of_visits += 1
                    mean_visit_age += dataset_specifications['visit_ages'][i][j]
                    var_visit_age += dataset_specifications['visit_ages'][i][j] ** 2

            if total_number_of_visits > 0:
                mean_visit_age /= float(total_number_of_visits)
                var_visit_age = (var_visit_age / float(total_number_of_visits) - mean_visit_age ** 2)

                if model_options['t0'] is None:
                    print('>> Initial t0 set to the mean visit age: %.2f' % mean_visit_age)
                    model_options['t0'] = mean_visit_age
                else:
                    print('>> Initial t0 set by the user to %.2f ; note that the mean visit age is %.2f'
                          % (model_options['t0'], mean_visit_age))

                if not model_type.lower() == 'regression':
                    if model_options['initial_time_shift_variance'] is None:
                        print('>> Initial time-shift std set to the empirical std of the visit ages: %.2f'
                              % math.sqrt(var_visit_age))
                        model_options['initial_time_shift_variance'] = var_visit_age
                    else:
                        print(('>> Initial time-shift std set by the user to %.2f ; note that the empirical std of '
                               'the visit ages is %.2f') % (math.sqrt(model_options['initial_time_shift_variance']),
                                                            math.sqrt(var_visit_age)))

        try:
            torch.multiprocessing.set_start_method("spawn")
        except RuntimeError as error:
            print('>> Warning: ' + str(error) + ' [ in xml_parameters ]. Ignoring.')

        if estimator_options is not None:
            # Initializes the state file.
            if estimator_options['state_file'] is None:
                path_to_state_file = os.path.join(self.output_dir, "deformetrica-state.p")
                print('>> No specified state-file. By default, Deformetrica state will by saved in file: %s.' %
                      path_to_state_file)
                if os.path.isfile(path_to_state_file):
                    os.remove(path_to_state_file)
                    print('>> Removing the pre-existing state file with same path.')
                estimator_options['state_file'] = path_to_state_file
            else:
                if os.path.exists(estimator_options['state_file']):
                    estimator_options['load_state_file'] = True
                    print('>> Deformetrica will attempt to resume computation from the user-specified state file: %s.'
                          % estimator_options['state_file'])
                else:
                    msg = 'The user-specified state-file does not exist: %s. State cannot be reloaded. ' \
                          'Future Deformetrica state will be saved at the given path.' % estimator_options['state_file']
                    print('>> ' + msg)

            # Warning if scipy-LBFGS with memory length > 1 and sobolev gradient.
            if estimator_options['optimization_method_type'].lower() == 'ScipyLBFGS'.lower() \
                    and estimator_options['memory_length'] > 1 \
                    and not model_options['freeze_template'] and model_options['use_sobolev_gradient']:
                print('>> Using a Sobolev gradient for the template data with the ScipyLBFGS estimator memory length '
                      'being larger than 1. Beware: that can be tricky.')

        # Freeze the fixed effects in case of a registration.
        if model_type.lower() == 'Registration'.lower():
            model_options['freeze_template'] = True

        elif model_type.lower() == 'LongitudinalRegistration'.lower():
            model_options['freeze_template'] = True
            model_options['freeze_control_points'] = True
            model_options['freeze_momenta'] = True
            model_options['freeze_modulation_matrix'] = True
            model_options['freeze_reference_time'] = True
            model_options['freeze_time_shift_variance'] = True
            model_options['freeze_acceleration_variance'] = True
            model_options['freeze_noise_variance'] = True

        # Initialize the number of sources if needed.
        if model_type.lower() == 'LongitudinalAtlas'.lower() \
                and model_options['initial_modulation_matrix'] is None and model_options['number_of_sources'] is None:
            model_options['number_of_sources'] = 4
            print('>> No initial modulation matrix given, neither a number of sources. '
                  'The latter will be ARBITRARILY defaulted to %d.' % model_options['number_of_sources'])

        # Initialize the initial_acceleration_variance if needed.
        if (model_type == 'LongitudinalAtlas'.lower() or model_type == 'LongitudinalRegistration'.lower()) \
                and model_options['initial_acceleration_variance'] is None:
            acceleration_std = 0.5
            print('>> The initial acceleration std fixed effect is ARBITRARILY set to %.2f.' % acceleration_std)
            model_options['initial_acceleration_variance'] = (acceleration_std ** 2)

        # Checking the number of image objects, and moving as desired the downsampling_factor parameter.
        count = 0
        for elt in template_specifications.values():
            if elt['deformable_object_type'].lower() == 'image':
                count += 1
                if not model_options['downsampling_factor'] == 1:
                    if 'downsampling_factor' in elt.keys():
                        print('>> Warning: the downsampling_factor option is specified twice. '
                              'Taking the value: %d.' % elt['downsampling_factor'])
                    else:
                        elt['downsampling_factor'] = model_options['downsampling_factor']
                        print('>> Setting the image grid downsampling factor to: %d.' %
                              model_options['downsampling_factor'])
        if count > 1:
            raise RuntimeError('Only a single image object can be used.')
        if count == 0 and not model_options['downsampling_factor'] == 1:
            msg = 'The "downsampling_factor" parameter is useful only for image data, ' \
                  'but none is considered here. Ignoring.'
            print('>> ' + msg)

        # Initializes the proposal distributions.
        if estimator_options is not None and \
                        estimator_options['optimization_method_type'].lower() == 'McmcSaem'.lower():

            if 'onset_age_proposal_std' not in estimator_options:
                estimator_options['onset_age_proposal_std'] = default.onset_age_proposal_std
            if 'acceleration_proposal_std' not in estimator_options:
                estimator_options['acceleration_proposal_std'] = default.acceleration_proposal_std
            if 'sources_proposal_std' not in estimator_options:
                estimator_options['sources_proposal_std'] = default.sources_proposal_std

            estimator_options['individual_proposal_distributions'] = {
                'onset_age': MultiScalarNormalDistribution(std=estimator_options['onset_age_proposal_std']),
                'acceleration': MultiScalarNormalDistribution(std=estimator_options['acceleration_proposal_std']),
                'sources': MultiScalarNormalDistribution(std=estimator_options['sources_proposal_std'])}

        return template_specifications, model_options, estimator_options

    @staticmethod
    def __infer_dimension(template_specifications):
        reader = DeformableObjectReader()
        max_dimension = 0
        for elt in template_specifications.values():
            object_filename = elt['filename']
            object_type = elt['deformable_object_type']
            o = reader.create_object(object_filename, object_type, dimension=None)
            d = o.dimension
            max_dimension = max(d, max_dimension)
        return max_dimension
