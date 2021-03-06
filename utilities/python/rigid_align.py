import os

# from launch.estimate_affine_atlas import estimate_rigid_atlas
from in_out.xml_parameters import XmlParameters
from in_out.array_readers_and_writers import *


# WORK IN PROGRESS

def estimate_rigid_align(path_to_source, path_to_target, path_to_output=None,
                         dimension=3,
                         deformation_kernel_type='torch',
                         attachment_type='varifold', attachment_kernel_type='torch', attachment_kernel_width=10):
    pass
#     """
#     Performs a registration, using the given parameters.
#     """
#     xml_parameters = XmlParameters()
#
#     # Hardcoded parameters
#     xml_parameters.use_cuda = False
#     xml_parameters.freeze_template = True
#     xml_parameters.freeze_cp = True
#     xml_parameters.use_rk2_for_shoot = True
#     xml_parameters.use_rk2_for_flow = True
#     xml_parameters.optimization_method_type = 'ScipyLBFGS'.lower()
#     xml_parameters.max_iterations = 200
#     xml_parameters.save_every_n_iters = 20
#     xml_parameters.convergence_tolerance = 1e-5
#     xml_parameters.save_every_n_iters = 10
#
#     # Argument parameters
#     xml_parameters.dimension = dimension
#     xml_parameters.deformation_kernel_width = deformation_kernel_width
#     xml_parameters.deformation_kernel_type = deformation_kernel_type
#     Settings().set_output_dir(output_dir)
#     xml_parameters.dataset_filenames = [[target_filenames_dict]]
#     xml_parameters.subject_ids = [subject_id]
#
#     xml_parameters.template_specifications = template_specs
#     xml_parameters.model_type = 'Registration'
#     xml_parameters._further_initialization()
#
#     estimate_deterministic_atlas(xml_parameters)
#
#     control_points = os.path.join(output_dir, "DeterministicAtlas__control_points.txt")
#     momenta = os.path.join(output_dir, "DeterministicAtlas__momenta.txt")
#
#     return control_points, momenta
#
#
# if __name__ == '__main__':
#     # Example on the turtle registration:
#     source = '../../examples/registration/image/2d/turtles/data/source.png'
#     target = '../../examples/registration/image/2d/turtles/data/target.png'
#     template_specs = {}
#     template_specs['turtle'] = {'deformable_object_type': 'image',
#                                 'noise_std': 0.1,
#                                 'filename': source}
#     deformation_kernel_width = 30
#     output_dir = 'output'
#     target_filenames_dict = {'turtle': target}
#     perform_registration(target_filenames_dict, 'subject_1', template_specs, deformation_kernel_width, output_dir
#                          , dimension=2)
#
#     # Example of brain_structures_shooting
#     template_file_1 = '../../examples/shooting/landmark/3d/brain_structures/data/amyg_prototype.vtk'
#     template_file_2 = '../../examples/shooting/landmark/3d/brain_structures/data/hippo_prototype.vtk'
#     cp_file = '../../examples/shooting/landmark/3d/brain_structures/data/ControlPoints.txt'
#     momenta_file = '../../examples/shooting/landmark/3d/brain_structures/data/Momenta.txt'
#
#     template_specs = {}
#     template_specs['amyg'] = {'deformable_object_type': 'surfacemesh',
#                               'noise_std': 0.1,
#                               'filename': template_file_1}  # no more info needed for shooting
#     template_specs['hippo'] = {'deformable_object_type': 'surfacemesh',
#                                'noise_std': 0.1,
#                                'filename': template_file_2}
#
#     deformation_kernel_width = 10.
#
#     perform_shooting(template_specs, cp_file, momenta_file, deformation_kernel_width)
