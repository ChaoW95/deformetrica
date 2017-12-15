import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '../../../')

import torch
import warnings
import time

from pydeformetrica.src.core.models.deterministic_atlas import DeterministicAtlas
from pydeformetrica.src.core.estimators.torch_optimize import TorchOptimize
from pydeformetrica.src.core.estimators.scipy_optimize import ScipyOptimize
from pydeformetrica.src.core.estimators.gradient_ascent import GradientAscent
from pydeformetrica.src.in_out.xml_parameters import XmlParameters
from pydeformetrica.src.support.utilities.general_settings import Settings
from pydeformetrica.src.support.kernels.kernel_functions import create_kernel
from pydeformetrica.src.in_out.dataset_functions import create_dataset
from src.in_out.utils import *

"""
Basic info printing.

"""

print('')
print('##############################')
print('##### PyDeformetrica 1.0 #####')
print('##############################')
print('')

print('[ estimate_deterministic_atlas function ]')
print('')

"""
Read command line, read xml files, set general settings.

"""

assert len(sys.argv) >= 4, "Usage: " + sys.argv[0] + " <model.xml> <data_set.xml> <optimization_parameters.xml>"
model_xml_path = sys.argv[1]
dataset_xml_path = sys.argv[2]
optimization_parameters_xml_path = sys.argv[3]

xml_parameters = XmlParameters()
xml_parameters.read_all_xmls(model_xml_path, dataset_xml_path, optimization_parameters_xml_path)

"""
Create the dataset object.

"""

dataset = create_dataset(xml_parameters.dataset_filenames, xml_parameters.visit_ages,
                         xml_parameters.subject_ids, xml_parameters.template_specifications)

assert (dataset.is_cross_sectional()), "Cannot run a deterministic atlas on a non-cross-sectional dataset."

"""
Create the model object.

"""

model = DeterministicAtlas()

model.diffeomorphism.kernel = create_kernel(xml_parameters.deformation_kernel_type,
                                            xml_parameters.deformation_kernel_width)
model.diffeomorphism.number_of_time_points = xml_parameters.number_of_time_points

if not xml_parameters.initial_control_points is None:
    control_points = read_2D_array(xml_parameters.initial_control_points)
    model.set_control_points(control_points)

if not xml_parameters.initial_momenta is None:
    momenta = read_momenta(xml_parameters.initial_momenta)
    model.set_momenta(momenta)

model.freeze_template = xml_parameters.freeze_template  # this should happen before the init of the template and the cps
model.freeze_control_points = xml_parameters.freeze_control_points

model.initialize_template_attributes(xml_parameters.template_specifications)

model.smoothing_kernel_width = xml_parameters.deformation_kernel_width * xml_parameters.sobolev_kernel_width_ratio
model.initial_cp_spacing = xml_parameters.initial_cp_spacing
model.number_of_subjects = dataset.number_of_subjects

model.update()

"""
Create the estimator object.

"""

if xml_parameters.optimization_method_type == 'GradientAscent'.lower():
    estimator = GradientAscent()
    estimator.initial_step_size = xml_parameters.initial_step_size
    estimator.max_line_search_iterations = xml_parameters.max_line_search_iterations
    estimator.line_search_shrink = xml_parameters.line_search_shrink
    estimator.line_search_expand = xml_parameters.line_search_expand

elif xml_parameters.optimization_method_type == 'TorchLBFGS'.lower():
    if not model.freeze_template and model.use_sobolev_gradient:
        model.use_sobolev_gradient = False
        msg = 'Impossible to use a Sobolev gradient for the template data with the TorchLBFGS estimator. ' \
              'Overriding the "use_sobolev_gradient" option, now set to "off".'
        warnings.warn(msg)
    estimator = TorchOptimize()

elif xml_parameters.optimization_method_type == 'ScipyLBFGS'.lower():
    if not model.freeze_template and model.use_sobolev_gradient:
        model.use_sobolev_gradient = False
        msg = 'Impossible to use a Sobolev gradient for the template data with the ScipyLBFGS estimator. ' \
              'Overriding the "use_sobolev_gradient" option, now set to "off".'
        warnings.warn(msg)
    estimator = ScipyOptimize()

else:
    estimator = GradientAscent()
    estimator.initial_step_size = xml_parameters.initial_step_size
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

"""
Launch.

"""

if not os.path.exists(Settings().output_dir):
    os.makedirs(Settings().output_dir)

model.name = 'DeterministicAtlas'

start_time = time.time()
estimator.update()
end_time = time.time()
print('>> Estimation took: ' + str(time.strftime("%H:%M:%S", time.gmtime(end_time - start_time))))
