"""
Tests for network_components
"""

import pytest

import torch
import torch.nn as nn
import tentorch as tn


class TestMPS:
    
    def test_mps1(self):
        # boundary = obc, param_bond = False
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=5, boundary='obc')

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21 # TODO: no uso permanent_nodes
        # TODO: It is equal to 13 because it counts Stacknode edges,
        #  should we have also references to the _leaf nodes??
        assert len(mps.edges) == 1
        
    def test_mps2(self):
        # boundary = obc, param_bond = False
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=0, boundary='obc')

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1
        
    def test_mps3(self):
        # boundary = obc, param_bond = False
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=1, boundary='obc')

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1
        
    def test_mps4(self):
        # boundary = obc, param_bond = False
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=9, boundary='obc')

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1
        
    def test_mps5(self):
        # boundary = obc, param_bond = False
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=10, boundary='obc')

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1
        
    def test_mps6(self):
        # boundary = obc, param_bond = True
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=5, boundary='obc', param_bond=True)

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1
        
    def test_mps7(self):
        # boundary = obc, param_bond = True
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=0, boundary='obc', param_bond=True)

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1
        
    def test_mps8(self):
        # boundary = obc, param_bond = True
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=1, boundary='obc', param_bond=True)

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1
    
    def test_mps9(self):
        # boundary = obc, param_bond = True
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=9, boundary='obc', param_bond=True)

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps10(self):
        # boundary = obc, param_bond = True
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=10, boundary='obc', param_bond=True)

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps11(self):
        # boundary = pbc, param_bond = False
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=5, boundary='pbc')

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps12(self):
        # boundary = pbc, param_bond = False
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=0, boundary='pbc')

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps13(self):
        # boundary = pbc, param_bond = False
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=1, boundary='pbc')

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps14(self):
        # boundary = pbc, param_bond = False
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=9, boundary='pbc')

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps15(self):
        # boundary = pbc, param_bond = False
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=10, boundary='pbc')

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps16(self):
        # boundary = pbc, param_bond = True
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=5, boundary='pbc', param_bond=True)

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps17(self):
        # boundary = pbc, param_bond = True
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=0, boundary='pbc', param_bond=True)

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps18(self):
        # boundary = pbc, param_bond = True
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=1, boundary='pbc', param_bond=True)

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps19(self):
        # boundary = pbc, param_bond = True
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=9, boundary='pbc', param_bond=True)

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_mps20(self):
        # boundary = pbc, param_bond = True
        mps = tn.MPS(n_sites=11, d_phys=5, n_labels=10, d_bond=2, l_position=10, boundary='pbc', param_bond=True)

        data = torch.randn(1000, 5, 10)
        result = mps.forward(data)
        mean = result.mean(0)
        mean[0].backward()
        std = result.std(0)
        assert len(mps.permanent_nodes) == 21
        assert len(mps.edges) == 1

    def test_extreme_cases(self):
        # Extreme cases
        mps = tn.MPS(n_sites=2, d_phys=5, n_labels=10, d_bond=2, l_position=0, boundary='obc', param_bond=True)

        mps = tn.MPS(n_sites=2, d_phys=5, n_labels=10, d_bond=2, l_position=1, boundary='obc', param_bond=True)

        mps = tn.MPS(n_sites=1, d_phys=5, n_labels=10, d_bond=2, l_position=0, boundary='pbc', param_bond=True)


def test_example_mps():
    mps = tn.MPS(n_sites=2, d_phys=2, n_labels=2, d_bond=2, l_position=1, boundary='obc').cuda()

    data = torch.randn(1, 2, 1).cuda()
    result = mps.forward(data)
    result[0, 0].backward()

    I = data.squeeze(2)
    A = mps.left_node.tensor
    B = mps.output_node.tensor
    grad_A1 = mps.left_node.grad
    grad_B1 = mps.output_node.grad

    grad_A2 = I.t() @ B[:, 0].view(2, 1).t()
    grad_B2 = (I @ A).t() @ torch.tensor([[1., 0.]]).cuda()

    assert torch.equal(grad_A1, grad_A2)
    assert torch.equal(grad_B1, grad_B2)


def test_example2_mps():
    mps = tn.MPS(n_sites=5, d_phys=2, n_labels=2, d_bond=2, boundary='obc')
    for node in mps.nodes.values():
        node.set_tensor(init_method='ones')

    data = torch.ones(1, 4)
    data = torch.stack([data, 1 - data], dim=1)
    result = mps.forward(data)
    result[0, 0].backward()
    result
