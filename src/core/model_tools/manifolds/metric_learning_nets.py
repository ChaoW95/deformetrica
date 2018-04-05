import os.path
import sys
from torch import nn
import numpy as np
import torch

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '../../../../../')
from pydeformetrica.src.support.utilities.general_settings import Settings


class AbstractNet(nn.Module):

    def __init__(self):
        super(AbstractNet, self).__init__()
        self.number_of_parameters = None

    def update(self):
        self.number_of_parameters = 0
        for elt in self.parameters():
            self.number_of_parameters += len(elt.view(-1))
        if Settings().tensor_scalar_type == torch.cuda.FloatTensor:
            print("Setting neural network type to CUDA.")
            self.cuda()
        elif Settings().tensor_scalar_type == torch.DoubleTensor:
            print("Setting neural network type to Double.")
            self.double()
        print("The nn has", self.number_of_parameters, "weights.")

    def forward(self, x):
        for layer in self.layers:
            x = layer(x)
        return x

    def get_gradient(self):
        out = np.zeros(self.number_of_parameters)
        pos = 0
        for layer in self.layers:
            try:
                if layer.weight is not None:
                    out[pos:pos+len(layer.weight.view(-1))] = layer.weight.grad.view(-1).cpu().data.numpy()
                    pos += len(layer.weight.view(-1))
            except AttributeError:
                pass
            try:
                if layer.bias is not None:
                    out[pos:pos+len(layer.bias.view(-1))] = layer.bias.grad.view(-1).cpu().data.numpy()
                    pos += len(layer.bias.view(-1))
            except AttributeError:
                pass
        return out

    def set_parameters(self, nn_parameters):
        """
        sets parameters from the given (flat) variable (should use state_dict)
        """
        pos = 0
        # print("Setting net param", nn_parameters.cpu().data.numpy()[0])
        for layer in self.layers:
            try:
                if layer.weight is not None:
                    layer.weight.data = nn_parameters[pos:pos+len(layer.weight.view(-1))].view(layer.weight.size()).data
                    pos += len(layer.weight.view(-1))
            except AttributeError:
                pass
            try:
                if layer.bias is not None:
                    layer.bias.data = nn_parameters[pos:pos+len(layer.bias.view(-1))].view(layer.bias.size()).data
                    pos += len(layer.bias.view(-1))
            except AttributeError:
                pass
        self.assert_rank_condition()

    def get_parameters(self):
        """"
        returns a numpy array with the flattened weights
        """
        out = np.zeros(self.number_of_parameters)
        pos = 0
        for layer in self.layers:
            try:
                if layer.weight is not None:
                    # print(layer, layer.weight.cpu().data.numpy().shape)
                    out[pos:pos+len(layer.weight.view(-1))] = layer.weight.view(-1).cpu().data.numpy()
                    pos += len(layer.weight.view(-1))
            except AttributeError:
                pass
            try:
                if layer.bias is not None:
                    out[pos:pos+len(layer.bias.view(-1))] = layer.bias.view(-1).cpu().data.numpy()
                    pos += len(layer.bias.view(-1))
            except AttributeError:
                pass
        return out

    def assert_rank_condition(self):
        """
        Fletcher condition on generative networks,
        so that the image is (locally) a submanifold of the space of observations
        """
        #return
        for layer in self.layers:
            try:
                if layer.weight is not None:
                    np_weight = layer.weight.data.numpy()
                    if len(np_weight.shape) == 4: # for convolution layers
                        a, b, c, d = np_weight.shape
                        np_weight = np_weight.reshape(a, b * c * d)
                    # a, b = np_weight.shape
                    # rank = np.linalg.matrix_rank(layer.weight.data.numpy())
                    # assert rank == min(a, b), "Weight of layer does not have full rank {}".format(layer)
            except AttributeError:
                pass


class ScalarNet(AbstractNet):

    def __init__(self, in_dimension=2, out_dimension=4):
        super(ScalarNet, self).__init__()
        self.layers = nn.ModuleList([nn.Linear(in_dimension, in_dimension),
            nn.Tanh(),
            nn.Linear(in_dimension, out_dimension, bias=True),
            nn.Tanh(),
            nn.Linear(out_dimension, out_dimension, bias=True),
            nn.Tanh(),
            nn.Linear(out_dimension, out_dimension, bias=True),
            nn.Tanh(),
            nn.Linear(out_dimension, out_dimension, bias=True),
            nn.ELU(),
            nn.Linear(out_dimension, out_dimension, bias=True),
            nn.ELU()
            ])
        self.update()


# This net automatically outputs 64 x 64 images. (to be improved)
class ImageNet2d(AbstractNet):

    def __init__(self, in_dimension=2):
        super(ImageNet2d, self).__init__()
        ngf = 2
        self.layers = nn.ModuleList([
            nn.Linear(in_dimension, in_dimension),
            nn.Tanh(), # was added 29/03 12h
            nn.ConvTranspose2d(in_dimension, 16 * ngf, 4, stride=4, bias=False),
            # nn.ELU(), # was removed, same day 14h
            # nn.ConvTranspose2d(32 * ngf, 16 * ngf, 2, stride=2, bias=False),
            nn.ELU(),
            nn.BatchNorm2d(num_features=16*ngf),
            nn.ConvTranspose2d(16 * ngf, 8 * ngf, 2, stride=2, bias=False),
            nn.ELU(),
            nn.BatchNorm2d(num_features=8*ngf),
            nn.ConvTranspose2d(8 * ngf, 4 * ngf, 2, stride=2, bias=False),
            nn.ELU(),
            nn.BatchNorm2d(num_features=4*ngf),
            nn.ConvTranspose2d(4 * ngf, 2 * ngf, 2, stride=2, bias=False),
            nn.ELU(),
            nn.BatchNorm2d(num_features=2*ngf),
            nn.ConvTranspose2d(2 * ngf, 1, 2, stride=2, bias=False),
            nn.ELU()
        ])
        self.update()

    def forward(self, x):
        a = x.size()
        # if len(a) == 2:
        #     x = x.unsqueeze(2).unsqueeze(3)
        # else:
        #     x = x.unsqueeze(0).unsqueeze(2).unsqueeze(3)
        for i, layer in enumerate(self.layers):
            if i == 0:
                x = layer(x)
                if len(a) == 2:
                    x = x.unsqueeze(2).unsqueeze(3)
                else:
                    x = x.unsqueeze(0).unsqueeze(2).unsqueeze(3)
            else:
                x = layer(x)
        if len(a) == 2:
            return x.squeeze(1)
        else:
            return x.squeeze(1).squeeze(0)



# This net automatically outputs 64 x 64 x 64 images. (to be improved)
class ImageNet3d(AbstractNet):

    def __init__(self, in_dimension=2):
        super(ImageNet3d, self).__init__()
        ngf = 2
        self.layers = nn.ModuleList([
            nn.ConvTranspose3d(in_dimension, 32 * ngf, 2, stride=2, bias=False),
            nn.ELU(),
            nn.ConvTranspose3d(32 * ngf, 16 * ngf, 2, stride=2, bias=False),
            nn.ELU(),
            nn.ConvTranspose3d(16 * ngf, 8 * ngf, 2, stride=2, bias=False),
            nn.ELU(),
            nn.ConvTranspose3d(8 * ngf, 4 * ngf, 2, stride=2, bias=False),
            nn.ELU(),
            nn.ConvTranspose3d(4 * ngf, 2 * ngf, 2, stride=2, bias=False),
            nn.ELU(),
            nn.ConvTranspose3d(2 * ngf, 1, 2, stride=2, bias=False),
            nn.ELU()
        ])
        self.update()

    def forward(self, x):
        a = x.size()
        if len(a) == 2:
            x = x.unsqueeze(2).unsqueeze(3).unsqueeze(4)
        else:
            x = x.unsqueeze(0).unsqueeze(2).unsqueeze(3).unsqueeze(4)
        for layer in self.layers:
            x = layer(x)
        if len(a) == 2:
            return x.squeeze(1)
        else:
            return x.squeeze(1).squeeze(0)

