import logging
import unittest

import torch

import support.kernels as kernel_factory
from support.utilities.general_settings import Settings

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)


class KernelFactory(unittest.TestCase):

    def test_instantiate_abstract_class(self):
        with self.assertRaises(TypeError):
            kernel_factory.AbstractKernel()

    def test_unknown_kernel_string(self):
        with self.assertRaises(TypeError):
            kernel_factory.factory('unknown_type')

    def test_non_cuda_kernel_factory(self):
        for k in [kernel_factory.Type.NO_KERNEL, kernel_factory.Type.TORCH]:
            logging.debug("testing kernel=", k)
            instance = kernel_factory.factory(k, kernel_width=1.)
            self.__isKernelValid(instance)

    @unittest.skipIf(not torch.cuda.is_available(), 'cuda is not available')
    def test_cuda_kernel_factory(self):
        for k in [kernel_factory.Type.KEOPS, kernel_factory.Type.TORCH_CUDA]:
            logging.debug("testing kernel=", k)
            instance = kernel_factory.factory(k, kernel_width=1.)
            self.__isKernelValid(instance)

    def test_non_cuda_kernel_factory_from_string(self):
        for k in ['no_kernel', 'no-kernel', 'torch']:
            logging.debug("testing kernel=", k)
            instance = kernel_factory.factory(k, kernel_width=1.)
            self.__isKernelValid(instance)

    @unittest.skipIf(not torch.cuda.is_available(), 'cuda is not available')
    def test_cuda_kernel_factory_from_string(self):
        for k in ['keops']:
            logging.debug("testing kernel=", k)
            instance = kernel_factory.factory(k, kernel_width=1.)
            self.__isKernelValid(instance)

    def __isKernelValid(self, instance):
        if instance is not None:
            self.assertIsInstance(instance, kernel_factory.AbstractKernel)
            self.assertEqual(instance.kernel_width, 1.)


@unittest.skipIf(not torch.cuda.is_available(), 'cuda is not available')
class Kernel(unittest.TestCase):
    def setUp(self):
        self.test_on_device = 'cuda:0'
        self.kernel_instance = kernel_factory.factory(kernel_factory.Type.TorchCudaKernel,
                                                      kernel_width=1., device=self.test_on_device)
        super().setUp()

    def test_torch_cuda_with_move_to_device(self):
        Settings().dimension = 3

        x = torch.tensor([
            [1., 1., 1.],
            [1., 1., 1.],
            [1., 1., 1.],
            [1., 1., 1.]])
        y = x.clone()
        p = torch.ones([4, Settings().dimension])

        # test convolve method
        expected_convolve_res = torch.tensor([
            [4., 4., 4.],
            [4., 4., 4.],
            [4., 4., 4.],
            [4., 4., 4.]])

        res = self.kernel_instance.convolve(x, y, p)
        self.assertEqual(res.device, torch.device(self.test_on_device))
        # move to CPU
        res = res.to(torch.device('cpu'))
        # torch.set_printoptions(precision=25)
        # print(res)
        # print(expected_convolve_res)
        # print(res - expected_convolve_res)
        self.assertTrue(torch.equal(expected_convolve_res, res))

        # test convolve gradient method
        expected_convolve_gradient_res = torch.tensor([
            [0., 0., 0.],
            [0., 0., 0.],
            [0., 0., 0.],
            [0., 0., 0.]])

        res = self.kernel_instance.convolve_gradient(x, x)
        self.assertEqual(res.device, torch.device(self.test_on_device))
        # move to CPU
        res = res.to(torch.device('cpu'))
        # print(res)
        self.assertTrue(torch.equal(expected_convolve_gradient_res, res))

    def test_torch_cuda_without_move_to_device(self):
        Settings().dimension = 3

        x = torch.tensor([
            [1., 1., 1.],
            [1., 1., 1.],
            [1., 1., 1.],
            [1., 1., 1.]]).to(self.test_on_device)
        y = x.clone().to(self.test_on_device)
        p = torch.ones([4, Settings().dimension]).to(self.test_on_device)

        # test convolve method
        expected_convolve_res = torch.tensor([
            [4., 4., 4.],
            [4., 4., 4.],
            [4., 4., 4.],
            [4., 4., 4.]])

        res = self.kernel_instance.convolve(x, y, p)
        self.assertEqual(res.device, torch.device(self.test_on_device))
        # move to CPU
        res = res.to(torch.device('cpu'))
        # torch.set_printoptions(precision=25)
        # print(res)
        # print(expected_convolve_res)
        # print(res - expected_convolve_res)
        self.assertTrue(torch.equal(expected_convolve_res, res))

        # test convolve gradient method
        expected_convolve_gradient_res = torch.tensor([
            [0., 0., 0.],
            [0., 0., 0.],
            [0., 0., 0.],
            [0., 0., 0.]])

        res = self.kernel_instance.convolve_gradient(x, x)
        self.assertEqual(res.device, torch.device(self.test_on_device))
        # move to CPU
        res = res.to(torch.device('cpu'))
        # print(res)
        self.assertTrue(torch.equal(expected_convolve_gradient_res, res))