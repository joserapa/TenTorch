"""
This script contains:

    Classes for Nodes and Edges:
        *Axis
        *AbstractNode:
            +Node:
                -CopyNode
                -StackNode
            +ParamNode
        *AbstractEdge:
            +Edge:
                -StackEdge
            +ParamEdge

    Operations:
        *contract
        *contract_between
        *batched_contract_between
"""

from typing import (overload, Union, Optional,
                    Sequence, Text, List)
from abc import ABC, abstractmethod
import warnings

import torch
import torch.nn as nn

from tentorch.network import TensorNetwork
from tentorch.utils import tab_string

_VALID_SUBSCRIPTS = list('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
_DEFAULT_SHIFT = -1.
_DEFAULT_SLOPE = 10.


class Axis:
    """
    Class for axes. An axis can be denoted by a number or a name.
    """

    def __init__(self,
                 num: int,
                 name: Text) -> None:
        """
        Create an axis for a node.

        Parameters
        ----------
        num: index in the node's axes list
        name: axis name

        Raises
        ------
        TypeError
        """

        if not isinstance(num, int):
            raise TypeError('`num` should be int type')
        if not isinstance(name, str):
            raise TypeError('`name` should be str type')

        self._num = num
        self.name = name

    # properties
    @property
    def num(self) -> int:
        return self._num

    # @property
    # def name(self) -> Text:
    #     return self._name

    # methods
    def __int__(self) -> int:
        return self.num

    def __str__(self) -> Text:
        return self.name

    def __repr__(self) -> Text:
        return f'{self.__class__.__name__}( {self.name} ({self.num}) )'


class AbstractNode(ABC):
    """
    Abstract class for nodes. Should be subclassed.

    A node is the minimum element in a tensor network. It is
    made up of a tensor and edges that can be connected to
    other nodes.
    """

    def __init__(self,
                 shape: Optional[Union[int, Sequence[int], torch.Size]] = None,
                 axes_names: Optional[Sequence[Text]] = None,
                 network: Optional[TensorNetwork] = None,
                 name: Optional[Text] = None,
                 tensor: Optional[torch.Tensor] = None,
                 param_edges: bool = False) -> None:
        """
        Create a node. Should be subclassed before usage and
        a limited number of abstract methods overridden.

        Parameters
        ----------
        shape: node shape (the shape of its tensor)
        axes_names: list of names for each of the node's axes
        network: tensor network to which the node belongs
        name: node name
        tensor: tensor "contained" in the node
        param_edges: boolean indicating whether node's edges
                     are parameterized (trainable) or not

        Raises
        ------
        TypeError
        ValueError
        """

        super().__init__()

        # shape and tensor
        if (shape is None) == (tensor is None):
            if shape is None:
                raise ValueError('One of `shape` or `tensor` should be provided')
            else:
                raise ValueError('Only one of `shape` or `tensor` should be provided')
        elif shape is not None:
            if not isinstance(shape, (int, tuple, list, torch.Size)):
                raise TypeError('`shape` should be int, tuple[int, ...], list[int, ...] or torch.Size type')
            if isinstance(shape, (tuple, list)):
                for i in shape:
                    if not isinstance(i, int):
                        raise TypeError('`shape` elements should be int type')
            if not isinstance(shape, torch.Size):
                empty_tensor = torch.empty(shape)
                shape = empty_tensor.shape
        else:
            if not isinstance(tensor, torch.Tensor):
                raise TypeError('`tensor` should be of torch.Tensor type')
            shape = tensor.shape

        # axes_names
        axes = list()
        if axes_names is None:
            warnings.warn('`axis_names` should be given to better tracking node edges and derived nodes')
            for i, _ in enumerate(shape):
                axes.append(Axis(num=i, name=f'__unnamed_axis__{i}'))
        else:
            if not isinstance(axes_names, (tuple, list)):
                raise TypeError('`axis_names` should be tuple[str, ...] or list[str, ...] type')
            if len(axes_names) != len(shape):
                raise ValueError('`axis_names` length should match `shape` length')
            else:
                repeated = False
                for i1, axis_name1 in enumerate(axes_names):
                    for i2, axis_name2 in enumerate(axes_names[:i1]):
                        if axis_name1 == axis_name2:
                            repeated = True
                            break
                    if repeated:
                        break
                    axes.append(Axis(num=i1, name=axis_name1))
                if repeated:
                    raise ValueError('Axes names should be unique in a node')

        # network
        if network is not None:
            if not isinstance(network, TensorNetwork):
                raise TypeError('`network` should be TensorNetwork type')
            network.add_node(self)

        # name
        if name is None:
            warnings.warn('`name` should be given to better tracking node edges and derived nodes')
            name = '__unnamed_node__'
        elif not isinstance(name, str):
            raise TypeError('`name` should be str type')

        self.name = name

        self._shape = shape
        self._axes = axes
        self._network = network
        self._tensor = self.set_tensor_format(tensor)
        self._edges = [self.create_edge(axis=ax)
                       for ax in axes]
        self._param_edges = param_edges

    # properties
    # TODO: define methods to set new properties
    #  (changing the edges, names, etc. accordingly)
    @property
    def shape(self) -> torch.Size:
        return self._shape

    @property
    def rank(self) -> int:
        return len(self.shape)

    @property
    def axes(self) -> List[Axis]:
        return self._axes

    @property
    def network(self) -> Optional[TensorNetwork]:
        return self._network

    # @property
    # def name(self) -> Text:
    #     return self._name

    @property
    def tensor(self) -> Optional[Union[torch.Tensor, nn.Parameter]]:
        if self._tensor is None:
            warnings.warn('Trying to access a tensor that has not been set yet')
        return self._tensor

    # TODO: Do we need this if we only set tensor property with self.set_tensor??
    # TODO: Do we let to set tensor None??
    @tensor.setter
    def tensor(self, tensor: Optional[torch.Tensor]) -> None:
        if tensor is not None:
            if not isinstance(tensor, torch.Tensor):
                raise ValueError('`tensor` should be torch.Tensor type')
            if tensor.shape != self.shape:
                raise ValueError('`tensor` shape should match node shape')
            self._tensor = self.set_tensor_format(tensor)
        else:
            raise ValueError('Cannot assign a NoneType object to the node\'s tensor')

    @property
    def edges(self) -> List['AbstractEdge']:
        return self._edges

    # abstract methods
    @staticmethod
    @abstractmethod
    def set_tensor_format(tensor: Optional[torch.Tensor]) -> Optional[Union[torch.Tensor, nn.Parameter]]:
        pass

    @abstractmethod
    def create_edge(self, axis: Axis) -> Union['Edge', 'ParamEdge']:
        pass

    # TODO: implement parameterize and deparameterize
    # @abstractmethod
    # def parameterize(self) -> 'ParamNode':
    #     pass

    # @abstractmethod
    # def deparameterize(self) -> 'Node':
    #     pass

    # methods
    # TODO: comment
    def size(self, dim: Optional[Union[int, Text, Axis]] = None) -> Union[torch.Size, int]:
        if dim is None:
            return self.shape
        axis_num = self.get_axis_number(dim)
        return self.shape[axis_num]

    def dimension(self, dim: Optional[Union[int, Text, Axis]] = None) -> Union[torch.Size, int]:
        if dim is None:
            return torch.Size(list(map(lambda edge: edge.dimension(), self.edges)))
        axis_num = self.get_axis_number(dim)
        return self.edges[axis_num].dimension()

    def get_axis_number(self, axis: Union[int, Text, Axis]) -> int:
        if isinstance(axis, int):
            for ax in self.axes:
                if axis == ax.num:
                    return ax.num
            ValueError(f'Node {self!s} has no axis with index {axis!r}')
        elif isinstance(axis, str):
            for ax in self.axes:
                if axis == ax.name:
                    return ax.num
            ValueError(f'Node {self!s} has no axis with name {axis!r}')
        elif isinstance(axis, Axis):
            for ax in self.axes:
                if axis == ax:
                    return ax.num
            ValueError(f'Node {self!s} has no axis with name {axis!r}')
        else:
            TypeError('`axis` should be int, str or Axis type')

    def get_edge(self, axis: Union[int, Text, Axis]) -> 'AbstractEdge':
        axis_num = self.get_axis_number(axis)
        return self.edges[axis_num]

    def add_edge(self,
                 edge: 'AbstractEdge',
                 axis: Union[int, Text, Axis],
                 override: bool = False) -> None:
        axis_num = self.get_axis_number(axis)
        if not self.edges[axis_num].is_dangling() and not override:
            raise ValueError(f'Node {self.name} already has a non-dangling edge for axis {axis!r}')
        self.edges[axis_num] = edge

    @staticmethod
    def _make_copy_tensor(shape: Union[int, Sequence[int], torch.Size]) -> torch.Tensor:
        for i in shape[1:]:
            if i != shape[0]:
                raise ValueError(f'`shape` has unequal dimensions. Copy tensors '
                                 f'have the same dimension in all their axes.')
        copy_tensor = torch.zeros(shape)
        rank = len(shape)
        i = torch.arange(shape[0])
        copy_tensor[(i,) * rank] = 1.
        return copy_tensor

    @staticmethod
    def _make_rand_tensor(shape: Union[int, Sequence[int], torch.Size],
                          low: float,
                          high: float) -> torch.Tensor:
        if not isinstance(low, float):
            raise TypeError('`low` should be float type')
        if not isinstance(high, float):
            raise TypeError('`high` should be float type')
        if low >= high:
            raise ValueError('`low` should be strictly smaller than `high`')
        return torch.rand(shape) * (high - low) + low

    @staticmethod
    def _make_randn_tensor(shape: Union[int, Sequence[int], torch.Size],
                           mean: float,
                           std: float) -> torch.Tensor:
        if not isinstance(mean, float):
            raise TypeError('`mean` should be float type')
        if not isinstance(std, float):
            raise TypeError('`std` should be float type')
        if std <= 0:
            raise ValueError('`std` should be positive')
        return torch.randn(shape) * std + mean

    # TODO: implement initialization methods for each node in the network
    def _make_tensor(self,
                     shape: Optional[Union[int, Sequence[int], torch.Size]] = None,
                     init_method: Text = 'zeros',
                     *args: float) -> torch.Tensor:
        if shape is None:
            shape = self.shape
        if init_method == 'zeros':
            return torch.zeros(shape)
        elif init_method == 'ones':
            return torch.ones(shape)
        elif init_method == 'copy':
            return self._make_copy_tensor(shape)
        elif init_method == 'rand':
            return self._make_rand_tensor(shape, *args)
        elif init_method == 'randn':
            return self._make_randn_tensor(shape, *args)
        elif init_method == 'neurips':
            pass
        else:
            raise ValueError('Choose a valid `init_method`: "zeros", '
                             '"ones", "copy", "rand", "randn", "neurips"')
        # TODO: implement functions like tn.ones, tn.zeros that use this functions
        #  to create a node and set its tensor

    def set_tensor(self, init_method: Text = 'zeros', *args: float) -> torch.Tensor:
        new_tensor = self._make_tensor()

    # TODO: do we need this? do this correctly, we don't need tensor.setter any more
    def unset_tensor(self) -> None:
        self._tensor = None

    def change_axis_size(self,
                         axis: Union[int, Text, Axis],
                         size: int,
                         init_method: Text = 'zeros',
                         *args: float) -> None:
        axis_num = self.get_axis_number(axis)
        old_shape = self.shape
        old_tensor = self.tensor

        index = list()
        for i, dim in enumerate(old_shape):
            if i == axis_num:
                index.append(slice(dim - size, dim))
            else:
                index.append(slice(0, dim))

        if size < self.shape[axis_num]:
            self.tensor = old_tensor[index]
        elif size > self.shape[axis_num]:
            new_shape = list(self.shape)
            new_shape[axis_num] = size

            old_tensor = self.tensor

            self.tensor = torch.empty(new_shape)
            self.set_tensor(init_method, *args)
            self.tensor[index] = old_tensor



    def param_edges(self, set_param: Optional[bool] = None) -> Optional[bool]:
        if set_param is None:
            return self._param_edges
        if set_param:
            for edge in self.edges:
                edge.parameterize()
        else:
            for edge in self.edges:
                edge.deparameterize()

    @overload
    def __getitem__(self, key: slice) -> List['AbstractEdge']:
        pass

    @overload
    def __getitem__(self, key: Union[int, Text, Axis]) -> 'AbstractEdge':
        pass

    def __getitem__(self, key: Union[slice, int, Text, Axis]) -> Union[List['AbstractEdge'], 'AbstractEdge']:
        if isinstance(key, slice):
            return self.edges[key]
        return self.get_edge(key)

    # TODO: implement @ (not in-place contract_between, returns new node, not affecting the network)
    def __matmul__(self, other: 'AbstractNode') -> 'AbstractNode':
        pass

    def __str__(self) -> Text:
        return self.name

    # TODO: error when tensor is none
    def __repr__(self) -> Text:
        return f'{self.__class__.__name__}(\n ' \
               f'\tname: {self.name}\n' \
               f'\ttensor:\n{tab_string(repr(self.tensor.data), 2)}\n' \
               f'\tedges:\n{tab_string(repr(self.edges), 2)})'


class Node(AbstractNode):
    """
    Base class for non-trainable nodes. Should be subclassed by
    any new class of non-trainable nodes.

    Used for fixed nodes of the network or intermediate,
    derived nodes resulting from operations between other nodes.
    """

    def __init__(self,
                 shape: Optional[Union[int, Sequence[int], torch.Size]] = None,
                 axes_names: Optional[Sequence[Text]] = None,
                 network: Optional[TensorNetwork] = None,
                 name: Optional[Text] = None,
                 tensor: Optional[torch.Tensor] = None,
                 param_edges: bool = False,
                 init_method: Optional[Text] = None,
                 *args: float) -> None:
        """

        Parameters
        ----------
        init_method: method to use to initialize the
                     node tensor when it is not provided
        args: arguments for the init_method
        """

        super().__init__(shape, axes_names, network, name, tensor, param_edges)

        if init_method is not None:
            self.set_tensor(init_method, *args)

    # methods
    # TODO: is it okay to return None tensor (and input None tensor)??
    @staticmethod
    def set_tensor_format(tensor: Optional[torch.Tensor]) -> Optional[torch.Tensor]:
        return tensor

    def create_edge(self, axis: Axis) -> Union['Edge', 'ParamEdge']:
        if self.param_edges():
            return ParamEdge(node1=self, axis1=axis)
        return Edge(node1=self, axis1=axis)


# TODO: ignore this at the moment
class CopyNode(Node):
    """
    Subclass of Node for copy nodes and its optimized operations.
    """

    # TODO: shared parameters among its edges? They have the same dimension
    #  in all edges. Or do we admit CopyNodes with different dimensions in each edge??
    # TODO: Si creamos un Node con init_method = 'copy' se convierte en CopyNode??

    def __init__(self,
                 shape: Optional[Union[int, Sequence[int], torch.Size]] = None,
                 axes_names: Optional[Sequence[Text]] = None,
                 network: Optional[TensorNetwork] = None,
                 name: Optional[Text] = None,
                 tensor: Optional[torch.Tensor] = None,
                 param_edges: bool = False,
                 *args: float) -> None:
        super().__init__(shape, axes_names, network, name, tensor, param_edges, 'copy', *args)

    # methods
    # TODO: implement optimized @
    def __matmul__(self, other: 'AbstractNode') -> 'Node':
        pass


# TODO: implement this, ignore this at the moment
class StackNode(Node):
    def __init__(self,
                 nodes_list: List[AbstractNode],
                 dim: int,
                 shape: Optional[Union[int, Sequence[int], torch.Size]] = None,
                 axis_names: Optional[Sequence[Text]] = None,
                 network: Optional[TensorNetwork] = None,
                 name: Optional[Text] = None,
                 tensor: Optional[torch.Tensor] = None,
                 param_edges: bool = True) -> None:

        tensors_list = list(map(lambda x: x.tensor, nodes_list))
        tensor = torch.stack(tensors_list, dim=dim)

        self.nodes_list = nodes_list
        self.tensor = tensor
        self.stacked_dim = dim

        self.edges_dict = dict()
        j = 0
        for node in nodes_list:
            for i, edge in enumerate(node.edges):
                if i >= self.stacked_dim:
                    j = 1
                if (i + j) in self.edges_dict:
                    self.edges_dict[(i + j)].append(edge)
                else:
                    self.edges_dict[(i + j)] = [edge]

        super().__init__(tensor=self.tensor)

    @staticmethod
    def set_tensor_format(tensor):
        return tensor

    def create_edge(self, axis=None, name=None):
        if axis == self.stacked_dim:
            return Edge(node1=self, axis1=axis, name=name)
        return StackEdge(self.edges_dict[axis], node1=self, axis1=axis, name=name)


class ParamNode(AbstractNode, nn.Module):
    """
    Class for trainable nodes. Subclass of PyTorch nn.Module.
    Should be subclassed by any new class of trainable nodes.

    Used as initial nodes of a tensor network that is to be trained.
    """

    def __init__(self,
                 shape: Optional[Union[int, Sequence[int], torch.Size]] = None,
                 axes_names: Optional[Sequence[Text]] = None,
                 network: Optional[TensorNetwork] = None,
                 name: Optional[Text] = None,
                 tensor: Optional[torch.Tensor] = None,
                 param_edges: bool = True,
                 init_method: Optional[Text] = None,
                 *args: float) -> None:

        nn.Module.__init__(self)
        AbstractNode.__init__(self, shape, axes_names, network, name, tensor, param_edges)

        if init_method is not None:
            self.set_tensor(init_method, *args)

    # properties
    @property
    def grad(self) -> Optional[torch.Tensor]:
        return self.tensor.grad

    # methods
    # TODO: what happens if tensor is None
    @staticmethod
    def set_tensor_format(tensor: Optional[torch.Tensor]) -> Optional[nn.Parameter]:
        if tensor is None:
            return None
        return nn.Parameter(tensor)

    def create_edge(self, axis: Axis) -> Union['ParamEdge', 'Edge']:
        if self.param_edges():
            return ParamEdge(node1=self, axis1=axis)
        return Edge(node1=self, axis1=axis)


class AbstractEdge(ABC):
    """
    Abstract class for edges. Should be subclassed.

    An edge is just a wrap up of references to the nodes it connects.
    """

    def __init__(self,
                 node1: AbstractNode,
                 axis1: Axis,
                 node2: Optional[AbstractNode] = None,
                 axis2: Optional[Axis] = None) -> None:
        """
        Create an edge. Should be subclassed before usage and
        a limited number of abstract methods overridden.

        Parameters
        ----------
        node1: first node to which the edge is connected
        axis1: axis of `node1` where the edge is attached
        node2: second, optional, node to which the edge is connected
        axis2: axis of `node2` where the edge is attached

        Raises
        ------
        ValueError
        TypeError
        """

        super().__init__()

        # node1 and axis1
        if not isinstance(node1, AbstractNode):
            raise TypeError('`node1` should be AbstractNode type')
        if not isinstance(axis1, Axis):
            raise TypeError('`axis1` should be Axis type')

        # node2 and axis2
        if (node2 is None) != (axis2 is None):
            raise ValueError('`node2` and `axis2` must either be both None or both not be None')
        if node2 is not None:
            if node1.shape[axis1.num] != node2.shape[axis2.num]:
                raise ValueError('Shapes of `axis1` and `axis2` should match')

        self._nodes = [node1, node2]
        self._axis = [axis1, axis2]

    # properties
    @property
    def node1(self) -> AbstractNode:
        return self._nodes[0]

    @property
    def node2(self) -> AbstractNode:
        return self._nodes[1]

    @property
    def axis1(self) -> Axis:
        return self._axis[0]

    @property
    def axis2(self) -> Axis:
        return self._axis[1]

    @property
    def name(self) -> Text:
        if self.is_dangling():
            return f'{self.node1.name}[{self.axis1.name}] <-> None'
        return f'{self.node1.name}[{self.axis1.name}] <-> ' \
               f'{self.node2.name}[{self.axis2.name}]'

    # abstract methods
    @abstractmethod
    def dimension(self) -> int:
        pass

    @abstractmethod
    def parameterize(self) -> 'ParamEdge':
        pass

    @abstractmethod
    def deparameterize(self) -> 'Edge':
        pass

    @abstractmethod
    def __xor__(self, other: 'AbstractEdge') -> 'AbstractEdge':
        pass

    # TODO: implement this, like disconnect, check types
    @abstractmethod
    def __or__(self) -> List['AbstractEdge']:
        pass

    # methods
    def is_dangling(self) -> bool:
        return self.node2 is None

    def size(self) -> int:
        return self.node1.size(self.axis1)

    # TODO: crop -> crops connected nodes to given size / dimension
    def change_size(self, size: int, init_method: Text = 'zeros') -> None:
        if not isinstance(size, int):
            TypeError('`size` should be int type')
        if not self.is_dangling():
            self.node2.change_axis_size(self.axis2, size, init_method)
        self.node1.change_axis_size(self.axis1, size, init_method)

    def __str__(self) -> Text:
        return self.name

    def __repr__(self) -> Text:
        if self.is_dangling():
            return f'{self.__class__.__name__}( {self.name} )  (Dangling Edge)'
        return f'{self.__class__.__name__}( {self.name} )'


class Edge(AbstractEdge):
    """
    Base class for non-trainable edges. Should be subclassed
    by any new class of non-trainable edges.

    Used by default for creating a non-trainable node.
    """

    # TODO: batch indicator

    # methods
    def dimension(self) -> int:
        return self.size()

    # TODO: convert to ParamEdge
    def parameterize(self, shift, slope, size) -> 'ParamEdge':  # size >= current dim
        # return ParamEdge
        pass

    def deparameterize(self) -> 'Edge':
        return self

    @overload
    def __xor__(self, other: 'Edge') -> 'Edge':
        pass

    @overload
    def __xor__(self, other: 'ParamEdge') -> 'ParamEdge':
        pass

    # TODO: change types
    def __xor__(self, other: Union['Edge', 'ParamEdge']) -> Union['Edge', 'ParamEdge']:
        return connect(self, other)

    def __or__(self):
        pass


# TODO: ignore this at the moment
class StackEdge(Edge):
    """
    Edge que es lista de varios Edges. Se usa para un StackNode

    No hacer cambios de tipos, simplemente que este Edge lleve
    parámetros adicionales de los Edges que está aglutinando
    y su vecinos y tal. Pero que no sea en sí mismo una lista
    de Edges, que eso lo lía todo.
    """

    def __init__(self,
                 edges_list: List['AbstractEdge'],
                 node1: 'AbstractNode',
                 axis1: int,
                 name: Optional[str] = None,
                 node2: Optional['AbstractNode'] = None,
                 axis2: Optional[int] = None,
                 shift: Optional[int] = None,
                 slope: Optional[int] = None) -> None:
        # TODO: edges in list must have same size and dimension
        self.edges_list = edges_list
        super().__init__(node1, axis1, name, node2, axis2, shift, slope)

    def create_parameters(self, shift, slope):
        return None, None, None

    def dim(self):
        """
        Si es ParamEdge se mide en función de sus parámetros la dimensión
        """
        return None

    def create_matrix(self, dim):
        """
        Eye for Edge, Parameter for ParamEdge
        """
        return None

    def __xor__(self, other: 'AbstractEdge') -> 'AbstractEdge':
        return None


class ParamEdge(AbstractEdge, nn.Module):
    """
    Class for trainable edges. Subclass of PyTorch nn.Module.
    Should be subclassed by any new class of trainable edges.

        -batch (bool)
        -grad -> devuelve tupla de grad de shift y slope
    """

    def __init__(self,
                 node1: AbstractNode,
                 axis1: Axis,
                 shift: Optional[Union[int, float]] = None,
                 slope: Optional[Union[int, float]] = None,
                 node2: Optional[AbstractNode] = None,
                 axis2: Optional[Axis] = None) -> None:

        nn.Module.__init__(self)
        AbstractEdge.__init__(self, node1, axis1, node2, axis2)

        # shift
        if shift is None:
            shift = _DEFAULT_SHIFT
        else:
            if isinstance(shift, int):
                shift = float(shift)
            elif not isinstance(shift, float):
                raise TypeError('`shift` should be int or float type')

        # slope
        if slope is None:
            slope = _DEFAULT_SLOPE
        else:
            if isinstance(slope, int):
                slope = float(slope)
            elif not isinstance(slope, float):
                raise TypeError('`slope` should be int or float type')

        self._shift = nn.Parameter(torch.tensor(shift))
        self._slope = nn.Parameter(torch.tensor(slope))
        self._sigmoid = nn.Sigmoid()
        self._matrix = self.set_matrix()

    # properties
    @property
    def shift(self) -> nn.Parameter:
        return self._shift

    @shift.setter
    def shift(self, shift: Union[int, float]) -> None:
        if isinstance(shift, int):
            shift = float(shift)
        elif not isinstance(shift, float):
            raise TypeError('`shift` should be int or float type')
        self._shift = nn.Parameter(torch.tensor(shift))
        self._matrix = self.set_matrix()

    @property
    def slope(self) -> nn.Parameter:
        return self._slope

    @slope.setter
    def slope(self, slope: Union[int, float]) -> None:
        if isinstance(slope, int):
            slope = float(slope)
        elif not isinstance(slope, float):
            raise TypeError('`shift` should be int or float type')
        self._slope = nn.Parameter(torch.tensor(slope))
        self._matrix = self.set_matrix()

    @property
    def matrix(self) -> torch.Tensor:
        return self._matrix

    @property
    def grad(self) -> List[Optional[torch.Tensor]]:
        return [self.shift.grad, self.slope.grad]

    # methods
    def sigmoid(self, x: torch.Tensor) -> torch.Tensor:
        return self._sigmoid(x)

    def set_matrix(self) -> torch.Tensor:
        matrix = torch.zeros((self.size(), self.size()))
        i = torch.arange(self.size())
        matrix[(i, i)] = self.sigmoid(self.slope * (i - self.shift))
        return matrix

    # methods
    def dimension(self) -> int:
        i = torch.arange(self.size())
        signs = torch.sign(self.sigmoid(self.slope * (i - self.shift)) - 0.5)
        dim = torch.where(signs == 1, signs, torch.zeros(signs.shape)).sum()
        return int(dim)

    def parameterize(self) -> 'ParamEdge':
        return self

    # TODO: convert to Edge
    def deparameterize(self) -> Edge:
        # we have to crop the node's tensors to the given dimension
        # return Edge()
        pass

    # TODO: check types, may be overload
    def __xor__(self, other: AbstractEdge) -> 'ParamEdge':
        return connect(self, other)

    def __or__(self):
        pass


# TODO: change output type -> Union[Edge, ParamEdge]. Do we return StackEdge or any other type?
def connect(edge1: AbstractEdge,
            edge2: AbstractEdge,
            override_network: bool = False) -> AbstractEdge:
    for edge in [edge1, edge2]:
        if not edge.is_dangling():
            raise ValueError(f'Edge {edge} is not a dangling edge. '
                             f'This edge points to nodes: {edge.node1} and {edge.node2}')
    if edge1 is edge2:
        raise ValueError('Cannot connect edge {edge1} to itself')
    if edge1.size() != edge2.size():
        raise ValueError(f'Cannot connect edges of unequal size. '
                         f'Size of edge {edge1}: {edge1.size()}. '
                         f'Size of edge {edge2}: {edge2.size()}')
    if edge1.dim() != edge2.dim():
        raise ValueError(f'Cannot connect edges of unequal dimension. '
                         f'Dimension of edge {edge1}: {edge1.dim()}. '
                         f'Dimension of edge {edge2}: {edge2.dim()}')

    node1, axis1 = edge1.node1, edge1.axis1
    node2, axis2 = edge2.node1, edge2.axis1
    net1, net2 = node1.network, node2.network

    if net1 is not None:
        if net1 != net2:
            if (net2 is not None) and not override_network:
                raise ValueError(f'Cannot connect edges from nodes in different networks. '
                                 f'Set `override` to True if you want to override {net2.name} '
                                 f'with {net1.name} in {node1.name} and its neighbours.')
            node2.move_to_network(net1)
        net = net1
    else:
        if net2 is not None:
            node1.move_to_network(net2)
        net = net2

    if net is None:
        if isinstance(edge1, ParamEdge) == isinstance(edge2, ParamEdge):
            if isinstance(edge1, ParamEdge):
                shift = edge1.shift.item()
                slope = edge1.slope.item()
                new_edge = ParamEdge(node1, axis1, shift, slope, node2, axis2)
            else:
                new_edge = Edge(node1, axis1, node2, axis2)
        else:
            if isinstance(edge1, ParamEdge):
                shift = edge1.shift.item()
                slope = edge1.slope.item()
            else:
                shift = edge2.shift.item()
                slope = edge2.slope.item()
            new_edge = ParamEdge(node1, axis1, shift, slope, node2, axis2)

    else:
        if isinstance(edge1, ParamEdge) == isinstance(edge2, ParamEdge):
            if isinstance(edge1, ParamEdge):
                net._remove_param_edge(edge1)
                net._remove_param_edge(edge2)
                shift = edge1.shift.item()
                slope = edge1.slope.item()
                new_edge = ParamEdge(node1, axis1, shift, slope, node2, axis2)
                net._add_param_edge(new_edge)
            else:
                new_edge = Edge(node1, axis1, node2, axis2)
        else:
            if isinstance(edge1, ParamEdge):
                net._remove_param_edge(edge1)
                shift = edge1.shift.item()
                slope = edge1.slope.item()
            else:
                net._remove_param_edge(edge2)
                shift = edge2.shift.item()
                slope = edge2.slope.item()
            new_edge = ParamEdge(node1, axis1, shift, slope, node2, axis2)
            net._add_param_edge(new_edge)

    node1.add_edge(new_edge, axis1, override=True)
    node2.add_edge(new_edge, axis2, override=True)
    return new_edge


def einsum(string: Text,
           *nodes: Sequence[Union[torch.Tensor, AbstractNode]]) -> AbstractNode:
    new_tensor = torch.einsum(string,
                              *tuple(map(lambda x: x.tensor if isinstance(x, AbstractNode) else x, nodes)))
    new_node = Node(tensor=new_tensor)

    out_string = string.split('->')[1]
    strings = string.split('->')[0].split(',')

    i = 0
    for j, string in enumerate(strings):
        if isinstance(nodes[j], AbstractNode):
            for k, char in enumerate(string):
                if i < len(out_string) and out_string[i] == char:
                    new_node.add_edge(nodes[j][k], i, override=True)
                    i += 1
    return new_node


def contract(edge: 'AbstractEdge'):
    # TODO: Podemos hacer aquí lo de añadir al string de einsum las matrices
    nodes = [edge.node1, edge.node2]
    axis = [edge.axis1, edge.axis2]
    assert edge.node1 != edge.node2

    next_subscript = 1
    input_strings = list()
    output_string = list()
    for i, node in enumerate(nodes):
        string = list()
        for j, _ in enumerate(node.shape):
            if j == axis[i]:
                string.append(_VALID_SUBSCRIPTS[0])
                if isinstance(edge, ParamEdge):
                    matrix_string = _VALID_SUBSCRIPTS[0] + _VALID_SUBSCRIPTS[0]
            else:
                string.append(_VALID_SUBSCRIPTS[next_subscript])
                output_string.append(_VALID_SUBSCRIPTS[next_subscript])
                next_subscript += 1
        input_strings.append(string)

    string1 = ''.join(input_strings[0])
    string2 = ''.join(input_strings[1])
    out_string = ''.join(output_string)

    if isinstance(edge, ParamEdge):
        einsum_string = string1 + ',' + matrix_string + ',' + string2 + '->' + out_string
        new_node = einsum(einsum_string, nodes[0], edge.matrix, nodes[1])
    else:
        einsum_string = string1 + ',' + string2 + '->' + out_string
        new_node = einsum(einsum_string, nodes[0], nodes[1])

    return new_node


def get_shared_edges(node1, node2):
    list_edges = list()
    for edge in node1.edges:
        if edge.node1 == node1 and edge.node2 == node2:
            list_edges.append(edge)
        elif edge.node1 == node2 and edge.node2 == node1:
            list_edges.append(edge)

    return list_edges


def contract_between(node1: 'AbstractNode', node2: 'AbstractNode'):
    # TODO:
    # En lugar de hacer un bucle de contract, hacer un solo string y un solo
    # einsum para qeu esté más optimizado

    # Stop computing if both nodes are the same
    if node1 is node2:
        raise ValueError(f'Cannot perform batched contraction between '
                         f'node {node1} and itself')

    # Computing shared edges
    shared_edges = get_shared_edges(node1, node2)
    # Stop computing if there are no shared edges
    if not shared_edges:  # shared_edges set is True if it has some element
        raise ValueError(f'No edges found between ndoes '
                         f'{node1} and {node2}')

    n_shared = len(shared_edges)
    # Create dictionary where each edge is a key, and each value is a letter
    shared_subscripts = dict(zip(shared_edges, _VALID_SUBSCRIPTS[:n_shared]))

    matrices_strings = []
    matrices = []
    res_string, string = [], []
    index = n_shared + 1
    # Loop in both (node1, batch_edge1) and (node2, batch_edge2)
    for node in [node1, node2]:
        # Append empty element for each loop, that is, string = [[],[]]
        string.append([])
        for edge in node.edges:
            # If edge is shared, add its letter to string
            if edge in shared_edges:
                string[-1].append(shared_subscripts[edge])
                if isinstance(edge, ParamEdge):
                    matrices_strings.append(shared_subscripts[edge] + shared_subscripts[edge])
                    matrices.append(edge.matrix)
            # If edge is neither shared or batch, add second next available new letter
            else:
                string[-1].append(_VALID_SUBSCRIPTS[index])
                res_string.append(_VALID_SUBSCRIPTS[index])
                index += 1

    string1 = ''.join(string[0])
    string2 = ''.join(string[1])
    mat_string = ','.join(matrices_strings)
    res_string = ''.join(res_string)

    # einsum_string = ''.join([string1, ',', string2, '->', res_string])
    if isinstance(edge, ParamEdge):
        einsum_string = string1 + ',' + mat_string + ',' + string2 + '->' + res_string
    else:
        einsum_string = string1 + ',' + string2 + '->' + res_string

    new_node = einsum(einsum_string, [node1] + matrices + [node2])

    return new_node


def batched_contract_between(node1: AbstractNode, node2: AbstractNode, batch_edge1: AbstractEdge,
                             batch_edge2: AbstractEdge) -> AbstractNode:
    """
    Contract between that supports one batch edge in each node.

    Uses einsum property: 'bij,bjk->bik'.

    Args:
        node1: First node to contract.
        node2: Second node to contract.
        batch_edge1: The edge of node1 that correpond to its batch index.
        batch_edge2: The edge of node2 that correpond to its batch index.

    Returns:
        new_node: Result of the contraction. This node has by default batch_edge1
        as its batch edge. Its edges are in order of the dangling edges of
        node1 followed by the dangling edges of node2.
    """

    # Stop computing if both nodes are the same
    if node1 is node2:
        raise ValueError(f'Cannot perform batched contraction between '
                         f'node {node1} and itself')

    # Computing shared edges
    shared_edges = get_shared_edges(node1, node2)
    # Stop computing if there are no shared edges
    if not shared_edges:  # shared_edges set is True if it has some element
        raise ValueError(f'No edges found between nodes '
                         f'{node1!s} and {node2!s}')

    # Stop computing if batch edges are in shared edges
    if batch_edge1 in shared_edges:
        raise ValueError(f'Batch edge {batch_edge1} is shared between the nodes')
    if batch_edge2 in shared_edges:
        raise ValueError(f'Batch edge {batch_edge2} is shared between the nodes')

    n_shared = len(shared_edges)
    # Create dictionary where each edge is a key, and each value is a letter
    shared_subscripts = dict(zip(shared_edges, _VALID_SUBSCRIPTS[:n_shared]))

    matrices_strings = []
    matrices = []
    res_string, string = [], []
    index = n_shared + 1
    # Loop in both (node1, batch_edge1) and (node2, batch_edge2)
    for node, batch_edge in zip([node1, node2], [batch_edge1, batch_edge2]):
        # Append empty element for each loop, that is, string = [[],[]]
        string.append([])
        for edge in node.edges:
            # If edge is shared, add its letter to string
            if edge in shared_edges:
                string[-1].append(shared_subscripts[edge])
                if isinstance(edge, ParamEdge):
                    matrices_strings.append(shared_subscripts[edge] + shared_subscripts[edge])
                    matrices.append(edge.matrix)
            # If edge is batch_edge, add next available letter
            elif edge is batch_edge:
                string[-1].append(_VALID_SUBSCRIPTS[n_shared])
                if node is node1:
                    res_string.append(_VALID_SUBSCRIPTS[n_shared])
            # If edge is neither shared or batch, add second next available new letter
            else:
                string[-1].append(_VALID_SUBSCRIPTS[index])
                res_string.append(_VALID_SUBSCRIPTS[index])
                index += 1

    string1 = ''.join(string[0])
    string2 = ''.join(string[1])
    mat_string = ','.join(matrices_strings)
    res_string = ''.join(res_string)

    if isinstance(edge, ParamEdge):
        einsum_string = string1 + ',' + mat_string + ',' + string2 + '->' + res_string
    else:
        einsum_string = string1 + ',' + string2 + '->' + res_string

    new_node = einsum(einsum_string, [node1] + matrices + [node2])

    return new_node


def stack():
    pass


def unbind():
    pass
