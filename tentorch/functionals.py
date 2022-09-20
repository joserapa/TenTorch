#from tentorch.network_components import Node
import tentorch.network_components as nc
import torch


TN_MODE = True


class tn_mode:

    def __init__(self):
        global TN_MODE
        TN_MODE = False

    def __enter__(self):
        pass

    def __exit__(self, *args, **kws):
        global TN_MODE
        TN_MODE = True


class Foo:

    def __init__(self, func1, func2):
        print('Creating operation foo')
        self.func1 = func1
        self.func2 = func2
        return

    def __call__(self, data):
        global TN_MODE
        if TN_MODE:
            return self.func1(data)
        else:
            return self.func2(data)

    # def op(self, node1: Node, node2: Node):
    #     print('Operating node1 and node2')
    #     return


def _func1(data):
    print('Computing func1')
    a = nc.Node(tensor=torch.randn(2, 3))
    print(type(a))


def _func2(data):
    a = torch.randn(2, 3)
    print('Computing func2')
    print(type(a))


foo = Foo(_func1, _func2)


# def _func1(data):
#     print('Computing func1')
#
#
# def _func2(data):
#     print('Computing func2')
#
#
# foo = Foo(_func1, _func2)
#
#
# import torch
# import tentorch as tn
# import pytest
#
#
# def test_foo():
#     a = tn.Node(tensor=torch.randn(2, 3))
#     a.foo(0)
#     with tn_mode():
#         a.foo(0)


from abc import ABC

# TODO: usar esto para copy y permute
class Foo2(ABC):
    def foo2(self):
        cls = self.__class__
        new = cls()
        return new

class Foo2_1(Foo2):
    pass

class Foo2_2(Foo2):
    pass
