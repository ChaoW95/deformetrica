import os
import torch
import unittest
from sys import platform

from functional_tests.functional_test import FunctionalTest


class PrincipalGeodesicAnalysisDigits(FunctionalTest):
    """
    Methods with names starting by "test" will be run.
    """

    def test_configuration_1(self):
        self.run_configuration(os.path.abspath(__file__), 'output__1', 'output_saved__1',
                               'model__1.xml', 'data_set.xml', 'optimization_parameters.xml')

    @unittest.skipIf(not torch.cuda.is_available(), 'cuda is not available')
    def test_configuration_2(self):
        self.run_configuration(os.path.abspath(__file__), 'output__2', 'output_saved__2',
                               'model__2.xml', 'data_set.xml', 'optimization_parameters.xml')
