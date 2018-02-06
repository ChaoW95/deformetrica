import os.path
import sys
import numpy as np
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '../../../../')
import torch
from torch.autograd import Variable

from pydeformetrica.src.core.observations.deformable_objects.landmarks.landmark import Landmark
from pydeformetrica.src.support.utilities.general_settings import Settings

class PolyLine(Landmark):
    """
    Lines in 2D or 3D space
    """

    ####################################################################################################################
    ### Constructor:
    ####################################################################################################################

    def __init__(self):
        Landmark.__init__(self)
        self.type = 'PolyLine'

        # All these attributes are torch tensors.
        self.connectivity = None
        self.centers = None
        self.normals = None

    ####################################################################################################################
    ### Public methods:
    ####################################################################################################################

    def update(self):
        self.get_centers_and_normals()
        Landmark.update(self)

    def set_connectivity(self, connectivity):
        self.connectivity = torch.from_numpy(connectivity).type(Settings().tensor_integer_type)
        self.is_modified = True

    def get_centers_and_normals(self, points=None):
        """
        Given a new set of points, use the corresponding connectivity available in the polydata
        to compute the new normals (which are tangents in this case) and centers
        It's also a lazy initialization of those attributes !
        """
        if points is None:
            if self.is_modified:
                torch_points_coordinates = Variable(
                    torch.from_numpy(self.points).type(Settings().tensor_scalar_type))
                a = torch_points_coordinates[self.connectivity[:, 0]]
                b = torch_points_coordinates[self.connectivity[:, 1]]
                centers = (a+b)/2.
                self.centers = centers
                self.normals = b - a
        else:
            a = points[self.connectivity[:, 0]]
            b = points[self.connectivity[:, 1]]
            centers = (a+b)/2.
            self.centers = centers
            self.normals = b - a
        return self.centers, self.normals
