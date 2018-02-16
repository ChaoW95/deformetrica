import os.path
import sys
import numpy as np
import warnings
import torch
import math

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '../../../../../')

from pydeformetrica.src.support.utilities.general_settings import Settings
import matplotlib.pyplot as plt
from torch.autograd import Variable
"""
Generic geodesic. It wraps a manifold (e.g. OneDimensionManifold) and uses 
its exponential attributes to make manipulations more convenient (e.g. backward and forward) 
"""
#


class GenericGeodesic:
    def __init__(self, exponential_factory):
        self.t0 = None
        self.tmax = None
        self.tmin = None
        self.concentration_of_time_points = 10

        self.momenta_t0 = None
        self.position_t0 = None
        self.velocity_t0 = None

        self.forward_exponential = exponential_factory.create()
        self.backward_exponential = exponential_factory.create()

        self.is_modified = True

    def set_t0(self, t0):
        self.t0 = t0
        self.is_modified = True

    def set_tmin(self, tmin):
        self.tmin = tmin
        self.is_modified = True

    def set_tmax(self, tmax):
        self.tmax = tmax
        self.is_modified = True

    def set_position_t0(self, position_t0):
        self.position_t0 = position_t0
        self.is_modified = True

    def set_momenta_t0(self, momenta_t0):
        self.momenta_t0 = momenta_t0
        self.is_modified = True

    def set_velocity_t0(self, velocity_t0):
        momenta_t0 = self.velocity_to_momenta(self.position_t0, velocity_t0)
        self.velocity_t0 = velocity_t0
        self.set_momenta_t0(momenta_t0)

    def set_concentration_of_time_points(self, ctp):
        self.concentration_of_time_points = ctp
        self.is_modified = True

    def velocity_to_momenta(self, position, velocity):
        """
        fully torch
        """
        return torch.matmul(self.forward_exponential.inverse_metric(position), velocity)

    def get_geodesic_point(self, time):
        t = (time - self.t0) * self.velocity_t0 + self.position_t0
        return t


        # assert self.tmin <= time.data.numpy()[0] <= self.tmax
        # if self.is_modified:
        #     msg = "Asking for geodesic point but the geodesic was modified and not updated"
        #     warnings.warn(msg)
        #
        # times = self._get_times()
        #
        # # Deal with the special case of a geodesic reduced to a single point.
        # if len(times) == 1:
        #     print('>> The geodesic seems to be reduced to a single point.')
        #     return self.position_t0
        #
        # # Standard case.
        # for j in range(1, len(times)):
        #     if time.data.numpy()[0] - times[j] < 0: break
        #
        # weight_left = (times[j] - time) / (times[j] - times[j - 1])
        # weight_right = (time - times[j - 1]) / (times[j] - times[j - 1])
        # geodesic_t = self._get_geodesic_trajectory()
        # geodesic_point = weight_left * geodesic_t[j - 1] + weight_right * geodesic_t[j]
        # if math.isnan(geodesic_point.data.numpy()[0]):
        #     print("nan")
        # return geodesic_point

    def update(self):
        assert self.t0 >= self.tmin, "tmin should be smaller than t0"
        assert self.t0 <= self.tmax, "tmax should be larger than t0"

        # Backward exponential -----------------------------------------------------------------------------------------
        delta_t = self.t0 - self.tmin
        self.backward_exponential.number_of_time_points = max(1, int(delta_t * self.concentration_of_time_points + 1.5))
        if self.is_modified:
            self.backward_exponential.set_initial_momenta(- self.momenta_t0 * delta_t)
            self.backward_exponential.set_initial_position(self.position_t0)
        if self.backward_exponential.number_of_time_points > 1:
            self.backward_exponential.update()
        else:
            self.backward_exponential.update_norm_squared()

        # Forward exponential ------------------------------------------------------------------------------------------
        delta_t = self.tmax - self.t0
        self.forward_exponential.number_of_time_points = max(1, int(delta_t * self.concentration_of_time_points + 1.5))
        if self.is_modified:
            self.forward_exponential.set_initial_momenta(self.momenta_t0 * delta_t)
            self.forward_exponential.set_initial_position(self.position_t0)
        if self.forward_exponential.number_of_time_points > 1:
            self.forward_exponential.update()
        else:
            self.forward_exponential.update_norm_squared()

        self.is_modified = False

    def _get_times(self):
        times_backward = [self.t0]
        if self.backward_exponential.number_of_time_points > 1:
            times_backward = np.linspace(
                self.t0, self.tmin, num=self.backward_exponential.number_of_time_points).tolist()

        times_forward = [self.t0]
        if self.forward_exponential.number_of_time_points > 1:
            times_forward = np.linspace(
                self.t0, self.tmax, num=self.forward_exponential.number_of_time_points).tolist()

        return times_backward[::-1] + times_forward[1:]

    def _get_geodesic_trajectory(self):
        if self.is_modified:
            msg = "Trying to get geodesic trajectory in non updated geodesic."
            warnings.warn(msg)

        backward_geodesic_t = [self.backward_exponential.get_initial_position()]
        if self.backward_exponential.number_of_time_points > 1:
            backward_geodesic_t = self.backward_exponential.position_t

        forward_geodesic_t = [self.forward_exponential.get_initial_position()]
        if self.forward_exponential.number_of_time_points > 1:
            forward_geodesic_t = self.forward_exponential.position_t

        return backward_geodesic_t[::-1] + forward_geodesic_t[1:]

    def set_parameters(self, extra_parameters):
        """
        Setting extra parameters for the exponentials
        e.g. parameters for the metric
        """
        self.forward_exponential.set_parameters(extra_parameters)
        self.backward_exponential.set_parameters(extra_parameters)
        self.is_modified = True

    def save_metric_plot(self):
        times = np.linspace(-0.4, 1.2, 300)
        times_torch = Variable(torch.from_numpy(times)).type(torch.DoubleTensor)
        metric_values = [self.forward_exponential.inverse_metric(t).data.numpy()[0] for t in times_torch]
        # square_root_metric_values = [np.sqrt(elt) for elt in metric_values]
        plt.plot(times, metric_values)
        plt.savefig(os.path.join(Settings().output_dir, "inverse_metric_profile.pdf"))
        plt.clf()

    def save_geodesic_plot(self):
        times = self._get_times()
        geodesic_values = [elt.data.numpy()[0] for elt in self._get_geodesic_trajectory()]
        plt.plot(times, geodesic_values)
        plt.savefig(os.path.join(Settings().output_dir, "reference_geodesic.pdf"))
        plt.clf()


    def parallel_transport(self, w):
        pass

    def _write(self):
        print("Write method not implemented for the generic geodesic !")