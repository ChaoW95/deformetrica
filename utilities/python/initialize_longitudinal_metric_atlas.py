import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '../../../')

import shutil
import xml.etree.ElementTree as et

from pydeformetrica.src.in_out.xml_parameters import XmlParameters
from pydeformetrica.src.support.utilities.general_settings import Settings
from src.in_out.array_readers_and_writers import *
import xml.etree.ElementTree as et
from xml.dom.minidom import parseString
from pydeformetrica.src.launch.estimate_longitudinal_metric_model import estimate_longitudinal_metric_model
from sklearn import datasets, linear_model
from pydeformetrica.src.in_out.dataset_functions import read_and_create_scalar_dataset
from sklearn.decomposition import PCA

def _initialize_modulation_matrix(dataset, p0, v0, number_of_sources):
    unit_v0 = v0/np.linalg.norm(v0)
    vectors = []
    for elt in dataset.deformable_objects:
        for e in elt:
            e_np = e.data.numpy()
            vector_projected = e_np - np.dot(e_np, unit_v0) * unit_v0
            vectors.append(vector_projected)

    # We now do a pca on those vectors
    pca = PCA(n_components=number_of_sources)
    pca.fit(vectors)
    return np.transpose(pca.components_)

def _smart_initialization_individual_effects(dataset):
    """
    least_square regression for each subject, so that yi = ai * t + bi
    output is the list of ais and bis
    this proceeds as if the initialization for the geodesic is a straight line
    """
    print("Performing initial least square regressions on the subjects, for initialization purposes.")

    number_of_subjects = dataset.number_of_subjects
    dimension = len(dataset.deformable_objects[0][0].data.numpy())

    ais = []
    bis = []

    for i in range(number_of_subjects):

        # Special case of a single observation for the subject
        if len(dataset.times[i]) <= 1:
            ais.append(1.)
            bis.append(0.)

        least_squares = linear_model.LinearRegression()
        least_squares.fit(dataset.times[i].reshape(-1, 1), dataset.deformable_objects[i].data.numpy().reshape(-1, dimension))

        a = least_squares.coef_.reshape(dimension)
        if len(a) == 1 and a[0] < 0.001:
            a = np.array([0.001])
        ais.append(a)
        bis.append(least_squares.intercept_.reshape(dimension))


        #if the slope is negative, we change it to 0.03, arbitrarily...

    # Ideally replace this by longitudinal registrations on the initial metric ! (much more expensive though)

    return ais, bis

def _smart_initialization(dataset, number_of_sources):
    ais, bis = _smart_initialization_individual_effects(dataset)
    reference_time = np.mean([np.mean(times_i) for times_i in dataset.times])
    average_a = np.mean(ais, 0)
    average_b = np.mean(bis, 0)
    alphas = []
    onset_ages = []
    for i in range(len(ais)):
        # if len(ais[i]) == 1:
        #     alphas.append([max(0.2, min(ais[i][0] / average_a, 2.5))])
        # else:
        #     alphas.append(ais[i] / average_a)  # Arbitrary bounds for a sane initialization
        alphas.append(1.)
        onset_ages.append(reference_time)  #TODO
    # p0 = average_a * reference_time + average_b

    p0 = 0
    for i in range(dataset.number_of_subjects):
        p0 += np.mean(dataset.deformable_objects[i].data.numpy(), 0)
    p0 /= dataset.number_of_subjects

    if number_of_sources > 0:
        modulation_matrix = _initialize_modulation_matrix(dataset, p0, average_a, number_of_sources)

    else:
        modulation_matrix = None

    return reference_time, average_a, p0, np.array(onset_ages), np.array(alphas), modulation_matrix


if __name__ == '__main__':

    print('')
    print('##############################')
    print('##### PyDeformetrica 1.0 #####')
    print('##############################')

    print('')

    assert len(sys.argv) == 4, 'Usage: ' + sys.argv[0] + " <model.xml> <data_set.xml> <optimization_parameters.xml> "

    model_xml_path = sys.argv[1]
    dataset_xml_path = sys.argv[2]
    optimization_parameters_xml_path = sys.argv[3]

    preprocessings_folder = Settings().preprocessing_dir
    if not os.path.isdir(preprocessings_folder):
        os.mkdir(preprocessings_folder)

    # Read original longitudinal model xml parameters.
    xml_parameters = XmlParameters()
    xml_parameters._read_model_xml(model_xml_path)
    xml_parameters._read_dataset_xml(dataset_xml_path)
    xml_parameters._read_optimization_parameters_xml(optimization_parameters_xml_path)
    xml_parameters._further_initialization()

    """
    1) Simple heuristic for initializing everything but the sources and the modulation matrix. (Works only in 1D I think !)
    """

    smart_initialization_output_path = os.path.join(preprocessings_folder, '1_smart_initialization')
    Settings().output_dir = smart_initialization_output_path

    if not os.path.isdir(smart_initialization_output_path):
        os.mkdir(smart_initialization_output_path)

    # We call the smart initialization. We need to instantiate the dataset first.
    dataset = read_and_create_scalar_dataset(xml_parameters)

    if xml_parameters.number_of_sources is None or xml_parameters.number_of_sources == 0:
        reference_time, average_a, p0, onset_ages, alphas, modulation_matrix = _smart_initialization(dataset, 0)
    else:
        reference_time, average_a, p0, onset_ages, alphas, modulation_matrix = _smart_initialization(dataset, xml_parameters.number_of_sources)

    # We save the onset ages and alphas.
    # We then set the right path in the xml_parameters, for the proper initialization.
    write_2D_array(np.log(alphas), "SmartInitialization_log_accelerations.txt")
    write_2D_array(onset_ages, "SmartInitialization_onset_ages.txt")
    if modulation_matrix is not None:
        write_2D_array(modulation_matrix, "SmartInitialization_modulation_matrix.txt")

    xml_parameters.initial_onset_alphas = os.path.join(smart_initialization_output_path, "SmartInitialization_onset_ages.txt")
    xml_parameters.initial_log_accelerations = os.path.join(smart_initialization_output_path, "SmartInitialization_log_accelerations.txt")
    if modulation_matrix is not None:
        xml_parameters.initial_modulation_matrix = os.path.join(smart_initialization_output_path, "SmartInitialization_modulation_matrix.txt")
    xml_parameters.t0 = reference_time
    xml_parameters.v0 = average_a
    xml_parameters.p0 = p0

    """
    2) Gradient descent on the mode
    """

    mode_descent_output_path = os.path.join(preprocessings_folder, '2_gradient_descent_on_the_mode')
    # To perform this gradient descent, we use the iniialization heuristic, starting from
    # a flat metric and linear regressions one each subject

    xml_parameters.optimization_method_type = 'GradientAscent'.lower()
    xml_parameters.scale_initial_step_size = True
    xml_parameters.max_iterations = 0
    xml_parameters.save_every_n_iters = 1

    # Freezing some variances !
    xml_parameters.freeze_log_acceleration_variance = True
    xml_parameters.freeze_noise_variance = True
    xml_parameters.freeze_onset_age_variance = True

    # Freezing other variables
    xml_parameters.freeze_modulation_matrix = True
    xml_parameters.freeze_p0 = True

    xml_parameters.output_dir = mode_descent_output_path
    Settings().set_output_dir(mode_descent_output_path)

    print(" >>> Performing gradient descent on the mode.")

    estimate_longitudinal_metric_model(xml_parameters)

    # Now that this is done, we create the right xml parameters file for the actual computation.
    # We already have the dataset_xml file: it's ok.
    # We already have the optimization_parameters file.
    # We must create a model.xml file.

    model_xml = et.Element('data-set')
    model_xml.set('deformetrica-min-version', "3.0.0")

    model_type = et.SubElement(model_xml, 'model-type')
    model_type.text = "LongitudinalMetricLearning"

    dimension = et.SubElement(model_xml, 'dimension')
    dimension.text=str(Settings().dimension)

    estimated_alphas = np.loadtxt(os.path.join(mode_descent_output_path, 'LongitudinalMetricModel_alphas.txt'))
    estimated_onset_ages = np.loadtxt(os.path.join(mode_descent_output_path, 'LongitudinalMetricModel_onset_ages.txt'))

    initial_time_shift_std = et.SubElement(model_xml, 'initial-time-shift-std')
    initial_time_shift_std.text = str(np.std(estimated_onset_ages))

    initial_log_acceleration_std = et.SubElement(model_xml, 'initial-log-acceleration-std')
    initial_log_acceleration_std.text = str(np.std(np.log(estimated_alphas)))

    deformation_parameters = et.SubElement(model_xml, 'deformation-parameters')

    exponential_type = et.SubElement(deformation_parameters, 'exponential-type')
    exponential_type.text = xml_parameters.exponential_type

    if xml_parameters.exponential_type == 'parametric':
        interpolation_points = et.SubElement(deformation_parameters, 'interpolation-points-file')
        interpolation_points.text = os.path.join(mode_descent_output_path, 'LongitudinalMetricModel_interpolation_points.txt')
        kernel_width = et.SubElement(deformation_parameters, 'kernel-width')
        kernel_width.text = str(xml_parameters.deformation_kernel_width)

    concentration_of_timepoints = et.SubElement(deformation_parameters,
                                                'concentration-of-timepoints')
    concentration_of_timepoints.text = str(xml_parameters.concentration_of_time_points)

    estimated_fixed_effects = np.load(os.path.join(mode_descent_output_path,
                                                   'LongitudinalMetricModel_all_fixed_effects.npy'))[
        ()]

    if xml_parameters.exponential_type in ['parametric']: # otherwise it's not saved !
        metric_parameters_file = et.SubElement(deformation_parameters,
                                                    'metric-parameters-file')
        metric_parameters_file.text = os.path.join(mode_descent_output_path, 'LongitudinalMetricModel_metric_parameters.txt')

    if xml_parameters.number_of_sources is not None and xml_parameters.number_of_sources > 0:
        initial_sources_file = et.SubElement(model_xml, 'initial-sources')
        initial_sources_file.text = os.path.join(mode_descent_output_path, 'LongitudinalMetricModel_sources.txt')
        number_of_sources = et.SubElement(deformation_parameters, 'number-of-sources')
        number_of_sources.text = str(xml_parameters.number_of_sources)
        initial_modulation_matrix_file = et.SubElement(model_xml, 'initial-modulation-matrix')
        initial_modulation_matrix_file.text = os.path.join(mode_descent_output_path, 'LongitudinalMetricModel_modulation_matrix.txt')

    t0 = et.SubElement(deformation_parameters, 't0')
    t0.text = str(estimated_fixed_effects['reference_time'])

    v0 = et.SubElement(deformation_parameters, 'v0')
    v0.text = os.path.join(mode_descent_output_path, 'LongitudinalMetricModel_v0.txt')

    p0 = et.SubElement(deformation_parameters, 'p0')
    p0.text = os.path.join(mode_descent_output_path, 'LongitudinalMetricModel_p0.txt')

    initial_onset_ages = et.SubElement(model_xml, 'initial-onset-ages')
    initial_onset_ages.text = os.path.join(mode_descent_output_path,
                                           "LongitudinalMetricModel_onset_ages.txt")

    initial_log_accelerations = et.SubElement(model_xml, 'initial-log-accelerations')
    initial_log_accelerations.text = os.path.join(mode_descent_output_path,
                                                  "LongitudinalMetricModel_log_accelerations.txt")


    model_xml_path = 'model_after_initialization.xml'
    doc = parseString((et.tostring(model_xml).decode('utf-8').replace('\n', '').replace('\t', ''))).toprettyxml()
    np.savetxt(model_xml_path, [doc], fmt='%s')
