import os,sys

import torch
import math
import torch.nn as nn
import torch.nn.functional as F

from torch_connectomics.model.blocks import *
from torch_connectomics.model.utils import *


class unet_residual(nn.Module):
    """Lightweight U-net with residual blocks (based on [Lee2017]_ with modifications).

    .. [Lee2017] Lee, Kisuk, Jonathan Zung, Peter Li, Viren Jain, and 
        H. Sebastian Seung. "Superhuman accuracy on the SNEMI3D connectomics 
        challenge." arXiv preprint arXiv:1706.00120, 2017.
        
    Args:
        in_channel (int): number of input channels.
        out_channel (int): number of output channels.
        filters (list): number of filters at each u-net stage.
    """
    def __init__(self, in_channel=1, out_channel=3, filters=[28, 36, 48, 64, 80], pad_mode='rep', norm_mode='bn', act_mode='elu'):
        super().__init__()

        self.depth = len(filters)-2

        # encoding path
        self.downE = nn.Sequential(
            # anisotropic embedding
            conv3d_norm_act(in_planes=in_channel, out_planes=filters[0], 
                          kernel_size=(1,5,5), stride=1, padding=(0,2,2), pad_mode=pad_mode, norm_mode=norm_mode, act_mode=act_mode),
            # 2d residual module
            conv3d_norm_act(in_planes=filters[0], out_planes=filters[0], 
                          kernel_size=(1,3,3), stride=1, padding=(0,1,1), pad_mode=pad_mode, norm_mode=norm_mode, act_mode=act_mode),
            residual_block_2d(filters[0], filters[0], projection=False, pad_mode=pad_mode, norm_mode=norm_mode, act_mode=act_mode)
        )
        
        self.downC = nn.ModuleList(
            [nn.Sequential(
            conv3d_norm_act(in_planes=filters[x], out_planes=filters[x+1], 
                          kernel_size=(1,3,3), stride=1, padding=(0,1,1), pad_mode=pad_mode, norm_mode=norm_mode, act_mode=act_mode),
            residual_block_3d(filters[x+1], filters[x+1], projection=False, pad_mode=pad_mode, norm_mode=norm_mode, act_mode=act_mode)
            ) for x in range(self.depth)])


        # center block
        self.center = nn.Sequential(conv3d_norm_act(in_planes=filters[-2], out_planes=filters[-1], 
                          kernel_size=(1,3,3), stride=1, padding=(0,1,1), pad_mode=pad_mode, norm_mode=norm_mode, act_mode=act_mode),
            residual_block_3d(filters[-1], filters[-1], projection=True)
        )

        # decoding path
        self.upE = nn.Sequential(
            conv3d_norm_act(in_planes=filters[0], out_planes=filters[0], 
                          kernel_size=(1,3,3), stride=1, padding=(0,1,1), pad_mode=pad_mode, norm_mode=norm_mode, act_mode=act_mode),
            residual_block_2d(filters[0], filters[0], projection=False, pad_mode=pad_mode, norm_mode=norm_mode, act_mode=act_mode),
            conv3d_norm_act(in_planes=filters[0], out_planes=out_channel, 
                          kernel_size=(1,5,5), stride=1, padding=(0,2,2), pad_mode=pad_mode, norm_mode=norm_mode)
        )

        self.upC = nn.ModuleList(
            [nn.Sequential(
                conv3d_norm_act(in_planes=filters[x+1], out_planes=filters[x+1], 
                          kernel_size=(1,3,3), stride=1, padding=(0,1,1), pad_mode=pad_mode, norm_mode=norm_mode, act_mode=act_mode),
                residual_block_3d(filters[x+1], filters[x+1], projection=False)
            ) for x in range(self.depth)])

        # pooling downsample
        self.downS = nn.ModuleList([nn.MaxPool3d(kernel_size=(1,2,2), stride=(1,2,2)) for x in range(self.depth+1)])
        # conv + upsample
        self.upS = nn.ModuleList([nn.Sequential(
                    conv3d_norm_act(filters[x+1], filters[x], kernel_size=(1,1,1), padding=0, norm_mode=norm_mode, act_mode=act_mode),
                    nn.Upsample(scale_factor=(1,2,2), mode='trilinear', align_corners=False)) for x in range(self.depth+1)])

        #initialization
        ortho_init(self)

    def forward(self, x):
        # encoding path
        z = self.downE(x)
        x = self.downS[0](z)

        down_u = [None] * (self.depth)
        for i in range(self.depth):
            down_u[i] = self.downC[i](x)
            x = self.downS[i+1](down_u[i])

        x = self.center(x)

        # decoding path
        for i in range(self.depth-1,-1,-1):
            x = down_u[i] + self.upS[i+1](x)
            x = self.upC[i](x)

        x = z + self.upS[0](x)  
        x = self.upE(x)

        x = torch.sigmoid(x)
        return x

def test():
    torch.manual_seed(0)
    model = unet_residual()
    print('model type: ', model.__class__.__name__)
    num_params = sum([p.data.nelement() for p in model.parameters()])
    print('number of trainable parameters: ', num_params)
    x = torch.randn(8, 1, 4, 128, 128)
    x[:2] = 0.3
    y = model(x)
    print(x.size(), y.size(), x.mean(), y.mean())

if __name__ == '__main__':
    test()
