import os.path
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '../../../../../')

import torch
from torch.autograd import Variable
import numpy as np
import warnings
from pydeformetrica.src.in_out.array_readers_and_writers import *
from pydeformetrica.src.support.utilities.general_settings import Settings
from pydeformetrica.src.core.model_tools.manifolds.generic_geodesic import GenericGeodesic

class GenericSpatiotemporalReferenceFrame:
    """
    Spatiotemporal reference frame based on exp-parallelization.
    It uses a geodesic and an exponential + the parallel transport. It needs an exponential factory to construct itself.
    """

    ####################################################################################################################
    ### Constructor:
    ####################################################################################################################

    def __init__(self, exponential_factory):
        self.geodesic = GenericGeodesic(exponential_factory)
        self.exponential = exponential_factory.create()

        self.modulation_matrix_t0 = None
        self.projected_modulation_matrix_t0 = None
        self.number_of_sources = None
        self.transport_is_modified = True

        self.times = None
        self.position_t = None
        self.projected_modulation_matrix_t = None

    ####################################################################################################################
    ### Encapsulation methods:
    ####################################################################################################################

    def set_concentration_of_time_points(self, ctp):
        self.geodesic.concentration_of_time_points = ctp

    def set_number_of_time_points(self, ntp):
        self.exponential.number_of_time_points = ntp

    def set_position_t0(self, td):
        self.geodesic.set_position_t0(td)
        self.transport_is_modified = True

    def set_velocity_t0(self, v):
        self.geodesic.set_velocity_t0(v)
        self.transport_is_modified = True

    def set_momenta_t0(self, mom):
        self.geodesic.set_momenta_t0(mom)
        self.transport_is_modified = True

    def set_modulation_matrix_t0(self, mm):
        self.modulation_matrix_t0 = mm
        self.number_of_sources = mm.size()[1]
        if self.number_of_sources > 0:
            self.transport_is_modified = True

    def set_t0(self, t0):
        self.geodesic.set_t0(t0)
        self.transport_is_modified = True

    def set_tmin(self, tmin):
        self.geodesic.set_tmin(tmin)
        self.transport_is_modified = True

    def set_tmax(self, tmax):
        self.geodesic.set_tmax(tmax)
        self.transport_is_modified = True

    def get_times(self):
        return self.times

    def get_position(self, time, sources=None):

        # Case of a no transport (e.g. dimension = 1)
        if sources is None:
            return self.geodesic.get_geodesic_point(time)

        # General case
        else:
            # Assert for coherent length of attribute lists.
            assert len(self.position_t) == len(self.projected_modulation_matrix_t) == len(self.times)

            # Deal with the special case of a geodesic reduced to a single point.
            if len(self.times) == 1:
                print('>> The spatiotemporal reference frame geodesic seems to be reduced to a single point.')
                self.exponential.set_initial_position(self.position_t[0])

                # Little subtlety here (not so clean btw): closed_form exponential returns transported velocities
                # Non closed form exponential returns transported momenta.
                if self.exponential.has_closed_form:
                    self.exponential.set_initial_velocity(torch.mm(self.projected_modulation_matrix_t[0],
                                                              sources.unsqueeze(1)).view(self.geodesic.momenta_t0.size()))
                else:
                    self.exponential.set_initial_momenta(torch.mm(self.projected_modulation_matrix_t[0],
                                                                   sources.unsqueeze(1)).view(
                        self.geodesic.momenta_t0.size()))
                self.exponential.update()
                return self.exponential.get_final_position()

            # Standard case.
            index, weight_left, weight_right = self.geodesic.get_interpolation_index_and_weights(time)
            position = weight_left * self.position_t[index - 1] + weight_right * self.position_t[index]
            modulation_matrix = weight_left * self.projected_modulation_matrix_t[index - 1] \
                                + weight_right * self.projected_modulation_matrix_t[index]
            space_shift = torch.mm(modulation_matrix, sources.unsqueeze(1)).view(self.geodesic.momenta_t0.size())

            self.exponential.set_initial_position(position)
            if self.exponential.has_closed_form:
                self.exponential.set_initial_velocity(space_shift)
            else:
                self.exponential.set_initial_momenta(space_shift)
            self.exponential.update()
            return self.exponential.get_final_position()

    ####################################################################################################################
    ### Public methods:
    ####################################################################################################################

    def update(self):
        """
        Update the geodesic, and compute the parallel transport of each column of the modulation matrix along
        this geodesic, ignoring the tangential components.
        """
        # Update the geodesic.
        self.geodesic.update()

        # Convenient attributes for later use.
        self.times = self.geodesic.get_times()
        self.position_t = self.geodesic.get_geodesic_trajectory()

        if self.transport_is_modified:
            # Initializes the projected_modulation_matrix_t attribute size.
            self.projected_modulation_matrix_t = \
                [Variable(torch.zeros(self.modulation_matrix_t0.size()).type(Settings().tensor_scalar_type),
                          requires_grad=False) for _ in range(len(self.control_points_t))]

            # Transport each column, ignoring the tangential components.
            for s in range(self.number_of_sources):
                space_shift_t0 = self.modulation_matrix_t0[:, s].contiguous().view(self.geodesic.velocity.size())
                space_shift_t = self.geodesic.parallel_transport(space_shift_t0, with_tangential_component=False)

                # Set the result correctly in the projected_modulation_matrix_t attribute.
                for t, space_shift in enumerate(space_shift_t):
                    self.projected_modulation_matrix_t[t][:, s] = space_shift.view(-1)

            self.transport_is_modified = False

    ####################################################################################################################
    ### Writing methods:
    ####################################################################################################################

    def write(self, root_name, objects_name, objects_extension, template,
              write_adjoint_parameters=False, write_exponential_flow=False):
        pass
        # # Write the geodesic -------------------------------------------------------------------------------------------
        # self.geodesic.write(root_name, objects_name, objects_extension, template, write_adjoint_parameters)
        #
        # # Write the exp-parallel curves --------------------------------------------------------------------------------
        # # Initialization.
        # template_data_memory = template.get_points()
        #
        # # Core loop.
        # times = self.geodesic._get_times()
        # for t, (time, modulation_matrix) in enumerate(zip(times, self.projected_modulation_matrix_t)):
        #     for s in range(self.number_of_sources):
        #         space_shift = modulation_matrix[:, s].contiguous().view(self.geodesic.momenta_t0.size())
        #         self.exponential.set_initial_template_data(self.template_data_t[t])
        #         self.exponential.set_initial_control_points(self.control_points_t[t])
        #

        #         if self.exponential.has_closed_form:
        #             self.exponential.set_initial_velocity(space_shift)
        #         else:
        #             self.exponential.set_initial_momenta(space_shift)
        #         self.exponential.update()
        #         deformed_points = self.exponential.get_template_data()
        #
        #         names = []
        #         for k, (object_name, object_extension) in enumerate(zip(objects_name, objects_extension)):
        #             name = root_name + '__IndependentComponent_' + str(s) + '__' + object_name + '__tp_' + str(t) \
        #                    + ('__age_%.2f' % time) + object_extension
        #             names.append(name)
        #         template.set_data(deformed_points.data.numpy())
        #         template.write(names)
        #
        #         # Massive writing.
        #         if write_exponential_flow:
        #             names = []
        #             for k, (object_name, object_extension) in enumerate(zip(objects_name, objects_extension)):
        #                 name = root_name + '__IndependentComponent_' + str(s) + '__' + object_name + '__tp_' + str(t) \
        #                        + ('__age_%.2f' % time) + '__ExponentialFlow'
        #                 names.append(name)
        #             self.exponential.write_flow(names, objects_extension, template, write_adjoint_parameters)
        #
        # # Finalization.
        # template.set_data(template_data_memory)


