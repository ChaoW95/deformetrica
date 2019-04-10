from enum import Enum

from core import default, GpuMode
from support.kernels.abstract_kernel import AbstractKernel


class Type(Enum):
    from support.kernels.torch_kernel import TorchKernel
    from support.kernels.keops_kernel import KeopsKernel

    UNDEFINED = None
    NO_KERNEL = None
    TORCH = TorchKernel
    KEOPS = KeopsKernel


instance_map = dict()


def factory(kernel_type, gpu_mode=default.gpu_mode, *args, **kwargs):
    """Return an instance of a kernel corresponding to the requested kernel_type"""
    assert isinstance(gpu_mode, GpuMode)

    # turn enum string to enum object
    if isinstance(kernel_type, str):
        try:
            for c in [' ', '-']:    # chars to be replaced for normalization
                kernel_type = kernel_type.replace(c, '_')
            kernel_type = Type[kernel_type.upper()]
        except:
            raise TypeError('kernel_type ' + kernel_type + ' could not be found')

    if not isinstance(kernel_type, Type):
        raise TypeError('kernel_type must be an instance of KernelType Enum')

    if kernel_type in [Type.UNDEFINED, Type.NO_KERNEL]:
        return None

    res = None
    hash = AbstractKernel.hash(kernel_type, gpu_mode, *args, **kwargs)
    if hash not in instance_map:
        res = kernel_type.value(gpu_mode, *args, **kwargs)    # instantiate
        instance_map[hash] = res
    else:
        res = instance_map[hash]

    assert res is not None
    return res
