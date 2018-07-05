import os
import time
import warnings

import support.kernels as kernel_factory
from core import default
from core.estimator_tools.samplers.srw_mhwg_sampler import SrwMhwgSampler
from core.estimators.gradient_ascent import GradientAscent
from core.estimators.mcmc_saem import McmcSaem
from core.estimators.scipy_optimize import ScipyOptimize
from core.models.bayesian_atlas import BayesianAtlas
from in_out.array_readers_and_writers import *
from in_out.dataset_functions import create_dataset
from support.probability_distributions.multi_scalar_normal_distribution import MultiScalarNormalDistribution


def instantiate_bayesian_atlas_model(dataset, template_specifications, deformation_kernel=default.deformation_kernel,
                                     number_of_time_points=default.number_of_time_points,
                                     use_rk2_for_shoot=default.use_rk2_for_shoot,
                                     use_rk2_for_flow=default.use_rk2_for_flow,
                                     freeze_template=default.freeze_template,
                                     freeze_control_points=default.freeze_control_points,
                                     use_sobolev_gradient=default.use_sobolev_gradient,
                                     smoothing_kernel_width=default.smoothing_kernel_width,
                                     initial_control_points=default.initial_control_points,
                                     initial_cp_spacing=default.initial_cp_spacing,
                                     initial_momenta=default.initial_momenta,
                                     number_of_threads=default.number_of_threads,
                                     covariance_momenta_prior_normalized_dof=default.covariance_momenta_prior_normalized_dof,
                                     **kwargs):
    if initial_cp_spacing is None:
        initial_cp_spacing = deformation_kernel.kernel_width

    model = BayesianAtlas(
        dataset,
        template_specifications,
        deformation_kernel,
        number_of_time_points=number_of_time_points,
        use_rk2_for_shoot=use_rk2_for_shoot, use_rk2_for_flow=use_rk2_for_flow,
        freeze_template=freeze_template, freeze_control_points=freeze_control_points,
        use_sobolev_gradient=use_sobolev_gradient, smoothing_kernel_width=smoothing_kernel_width,
        number_of_threads=number_of_threads)

    if initial_control_points is not None:
        control_points = read_2D_array(initial_control_points)
        model.set_control_points(control_points)
    else:
        model.initial_cp_spacing = initial_cp_spacing

    # Prior on the covariance momenta (inverse Wishart: degrees of freedom parameter).
    model.priors['covariance_momenta'].degrees_of_freedom = dataset.number_of_subjects * covariance_momenta_prior_normalized_dof

    # Prior on the noise variance (inverse Wishart: degrees of freedom parameter).
    for k, object in enumerate(template_specifications.values()):
        model.priors['noise_variance'].degrees_of_freedom.append(dataset.number_of_subjects
                                                                 * object['noise_variance_prior_normalized_dof']
                                                                 * model.objects_noise_dimension[k])

    model.update()

    # Initial random effects realizations.
    individual_RER = {}
    cp = model.get_control_points()
    if initial_momenta is not None:
        individual_RER['momenta'] = read_3D_array(initial_momenta)
    else:
        individual_RER['momenta'] = np.zeros((dataset.number_of_subjects, cp.shape[0], cp.shape[1]))


    """
    Prior on the noise variance (inverse Wishart: scale scalars parameters).
    """

    td, tp, cp = model._fixed_effects_to_torch_tensors(False)
    mom = model._individual_RER_to_torch_tensors(individual_RER, False)

    residuals_per_object = sum(model._compute_residuals(dataset, td, tp, cp, mom))
    for k, object in enumerate(template_specifications.values()):
        if object['noise_variance_prior_scale_std'] is None:
            model.priors['noise_variance'].scale_scalars.append(
                0.01 * residuals_per_object[k].detach().cpu().numpy()
                / model.priors['noise_variance'].degrees_of_freedom[k])
        else:
            model.priors['noise_variance'].scale_scalars.append(object['noise_variance_prior_scale_std'] ** 2)
    model.update()

    # Return the initialized model.
    return model, individual_RER


def estimate_bayesian_atlas(xml_parameters):
    print('')
    print('[ estimate_bayesian_atlas function ]')
    print('')

    """
    Create the dataset object.
    """

    dataset = create_dataset(xml_parameters.dataset_filenames, xml_parameters.visit_ages,
                             xml_parameters.subject_ids, xml_parameters.template_specifications)

    assert (dataset.is_cross_sectional()), "Cannot estimate an atlas from a non-cross-sectional dataset."

    """
    Create the model object.
    """

    model = BayesianAtlas()

    model.exponential.kernel = kernel_factory.factory(xml_parameters.deformation_kernel_type, xml_parameters.deformation_kernel_width)
    model.exponential.number_of_time_points = xml_parameters.number_of_time_points
    model.exponential.set_use_rk2_for_shoot(xml_parameters.use_rk2_for_shoot)
    model.exponential.set_use_rk2_for_flow(xml_parameters.use_rk2_for_flow)

    if xml_parameters.initial_control_points is not None:
        control_points = read_2D_array(xml_parameters.initial_control_points)
        model.set_control_points(control_points)
    else: model.initial_cp_spacing = xml_parameters.initial_cp_spacing

    model.freeze_template = xml_parameters.freeze_template  # this should happen before the init of the template and the cps
    model.freeze_control_points = xml_parameters.freeze_control_points

    model.initialize_template_attributes(xml_parameters.template_specifications)

    model.use_sobolev_gradient = xml_parameters.use_sobolev_gradient
    model.smoothing_kernel_width = xml_parameters.deformation_kernel_width * xml_parameters.sobolev_kernel_width_ratio

    # Prior on the covariance momenta (inverse Wishart: degrees of freedom parameter).
    model.priors['covariance_momenta'].degrees_of_freedom = dataset.number_of_subjects \
                                                            * xml_parameters.covariance_momenta_prior_normalized_dof

    # Prior on the noise variance (inverse Wishart: degrees of freedom parameter).
    for k, object in enumerate(xml_parameters.template_specifications.values()):
        model.priors['noise_variance'].degrees_of_freedom.append(dataset.number_of_subjects
                                                                 * object['noise_variance_prior_normalized_dof']
                                                                 * model.objects_noise_dimension[k])

    model.update()

    """
    Create the estimator object.
    """

    if xml_parameters.optimization_method_type == 'GradientAscent'.lower():
        estimator = GradientAscent()
        estimator.initial_step_size = xml_parameters.initial_step_size
        estimator.scale_initial_step_size = xml_parameters.scale_initial_step_size
        estimator.max_line_search_iterations = xml_parameters.max_line_search_iterations
        estimator.line_search_shrink = xml_parameters.line_search_shrink
        estimator.line_search_expand = xml_parameters.line_search_expand

    elif xml_parameters.optimization_method_type == 'ScipyLBFGS'.lower():
        msg = 'Estimating a Bayesian Atlas with the ScipyLBFGS method. Beware: the initial line search might be too ' \
              'violent. A better convergence might be achieved by the GradientAscent optimizer, ' \
              'with a "small" initial-step-size parameter.'
        warnings.warn(msg)

        estimator = ScipyOptimize()
        estimator.max_line_search_iterations = xml_parameters.max_line_search_iterations
        estimator.memory_length = xml_parameters.memory_length

        if not model.freeze_template and model.use_sobolev_gradient and estimator.memory_length > 1:
            msg = 'Using a Sobolev gradient for the template data with the ScipyLBFGS estimator memory length ' \
                  'being larger than 1. Beware: that can be tricky.'
            warnings.warn(msg)
        #     estimator.memory_length = 1
        #     msg = 'Impossible to use a Sobolev gradient for the template data with the ScipyLBFGS estimator memory ' \
        #           'length being larger than 1. Overriding the "memory_length" option, now set to "1".'
        #     warnings.warn(msg)

    elif xml_parameters.optimization_method_type == 'McmcSaem'.lower():
        sampler = SrwMhwgSampler()

        momenta_proposal_distribution = MultiScalarNormalDistribution()
        # initial_control_points = model.get_control_points()
        # momenta_proposal_distribution.set_mean(np.zeros(initial_control_points.size,))
        momenta_proposal_distribution.set_variance_sqrt(xml_parameters.momenta_proposal_std)
        sampler.individual_proposal_distributions['momenta'] = momenta_proposal_distribution

        estimator = McmcSaem()
        estimator.sampler = sampler
        estimator.sample_every_n_mcmc_iters = xml_parameters.sample_every_n_mcmc_iters

    else:
        estimator = GradientAscent()
        estimator.initial_step_size = xml_parameters.initial_step_size
        estimator.scale_initial_step_size = xml_parameters.scale_initial_step_size
        estimator.max_line_search_iterations = xml_parameters.max_line_search_iterations
        estimator.line_search_shrink = xml_parameters.line_search_shrink
        estimator.line_search_expand = xml_parameters.line_search_expand

        msg = 'Unknown optimization-method-type: \"' + xml_parameters.optimization_method_type \
              + '\". Defaulting to GradientAscent.'
        warnings.warn(msg)

    estimator.max_iterations = xml_parameters.max_iterations
    estimator.convergence_tolerance = xml_parameters.convergence_tolerance

    estimator.print_every_n_iters = xml_parameters.print_every_n_iters
    estimator.save_every_n_iters = xml_parameters.save_every_n_iters

    estimator.dataset = dataset
    estimator.statistical_model = model

    # Initial random effects realizations.
    cp = model.get_control_points()
    if xml_parameters.initial_momenta is not None: mom = read_3D_array(xml_parameters.initial_momenta)
    else: mom = np.zeros((dataset.number_of_subjects, cp.shape[0], cp.shape[1]))
    estimator.individual_RER['momenta'] = mom

    """
    Prior on the noise variance (inverse Wishart: scale scalars parameters).
    """

    td, tp, cp = model._fixed_effects_to_torch_tensors(False)
    mom = model._individual_RER_to_torch_tensors(estimator.individual_RER, False)

    residuals_per_object = sum(model._compute_residuals(dataset, td, tp, cp, mom))
    for k, object in enumerate(xml_parameters.template_specifications.values()):
        if object['noise_variance_prior_scale_std'] is None:
            model.priors['noise_variance'].scale_scalars.append(
                0.01 * residuals_per_object[k].detach().cpu().numpy()
                / model.priors['noise_variance'].degrees_of_freedom[k])
        else:
            model.priors['noise_variance'].scale_scalars.append(object['noise_variance_prior_scale_std'] ** 2)
    model.update()

    """
    Launch.
    """

    if not os.path.exists(Settings().output_dir): os.makedirs(Settings().output_dir)

    model.name = 'BayesianAtlas'

    print('')
    print('[ update method of the ' + estimator.name + ' optimizer ]')

    start_time = time.time()
    estimator.update()
    estimator.write()
    end_time = time.time()
    print('>> Estimation took: ' + str(time.strftime("%H:%M:%S", time.gmtime(end_time - start_time))))

    return model, estimator.individual_RER['momenta']
