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

    Class for Tensor Networks:
        *TensorNetwork

    Operations:
        *contract
        *contract_between
        *batched_contract_between
"""
# TODO: gestionar bien tipos y errores viendo desde qué funciones llamo a cuáles

from typing import (overload, Union, Optional, Dict,
                    Sequence, Text, List, Tuple)
from abc import ABC, abstractmethod
import warnings

import torch
import torch.nn as nn

from tentorch.utils import tab_string, enum_repeated_names

_VALID_SUBSCRIPTS = list('abcdefghijklmnopqrstuvwxyz'
                         'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                         '0123456789')
_DEFAULT_SHIFT = -0.5
_DEFAULT_SLOPE = 20.


class Axis:
    """
    Class for axes. An axis can be denoted by a number or a name.
    """

    def __init__(self,
                 num: int,
                 name: Text,
                 node1: bool = True) -> None:
        """
        Create an axis for a node.

        Parameters
        ----------
        num: index in the node's axes list
        name: axis name
        node1: boolean indicating whether `node1` of the edge
               attached to this axis is the node that contains
               the axis. If False, node is `node2` of the edge

        Raises
        ------
        TypeError
        """

        if not isinstance(num, int):
            raise TypeError('`num` should be int type')
        if not isinstance(name, str):
            raise TypeError('`name` should be str type')
        if not isinstance(node1, bool):
            raise TypeError('`node1` should be bool type')

        self._num = num
        if ' ' in name:
            raise ValueError('`name` cannot contain blank spaces')
        self._name = name
        self._node1 = node1

    # properties
    @property
    def num(self) -> int:
        return self._num

    @property
    def name(self) -> Text:
        return self._name

    @name.setter
    def name(self, name: Text) -> None:
        """
        Set axis name. Should not contain blank spaces
        if we intend to use it as index of submodules.
        """
        if ' ' in name:
            raise ValueError('`name` cannot contain blank spaces')
        self._name = name

    @property
    def node1(self) -> bool:
        return self._node1

    # methods
    def __int__(self) -> int:
        return self.num

    def __str__(self) -> Text:
        return self.name

    def __repr__(self) -> Text:
        return f'{self.__class__.__name__}( {self.name} ({self.num}) )'


# TODO: implement objects that share parameters
# TODO: implement * as tensor product of 2 tensors
# TODO: implement einsum for Nodes, so that edge links are automatically
#  made and we can compute contractions between several nodes at the same time
# TODO: bueno, lo de contraer resultados con los nodos con los que
#  estaban conectados los nodos originales ahora funciona, pero es algo que solo
#  deberíamos permitir en nuestro caso, o tal vez en modo .train() o algo así,
#  o en un contexto. Puede que baste con que los Edges admitan una lista de
#  nodos adyacentes, sería como que con cada opción habría una TN creada,
#  pero no nos hace falta estar copiando los nodos.
class AbstractNode(ABC):
    """
    Abstract class for nodes. Should be subclassed.

    A node is the minimum element in a tensor network. It is
    made up of a tensor and edges that can be connected to
    other nodes.
    """

    def __init__(self,
                 shape: Union[int, Sequence[int], torch.Size],
                 axes_names: Optional[Sequence[Text]] = None,
                 name: Optional[Text] = None,
                 network: Optional['TensorNetwork'] = None,
                 param_edges: bool = False) -> None:
        """
        Create a node. Should be subclassed before usage and
        a limited number of abstract methods overridden.

        Parameters
        ----------
        shape: node shape (the shape of its tensor)
        axes_names: list of names for each of the node's axes
        name: node name
        network: tensor network to which the node belongs
        param_edges: boolean indicating whether node's edges
                     are parameterized (trainable) or not

        Raises
        ------
        TypeError
        ValueError
        """

        super().__init__()

        # shape
        if shape is not None:
            if not isinstance(shape, (int, tuple, list, torch.Size)):
                raise TypeError('`shape` should be int, tuple[int, ...], list[int, ...] or torch.Size type')
            if isinstance(shape, (tuple, list)):
                for i in shape:
                    if not isinstance(i, int):
                        raise TypeError('`shape` elements should be int type')

        # axes_names
        axes = list()
        if axes_names is None:
            axes = [Axis(num=i, name=f'axis_{i}')
                    for i, _ in enumerate(shape)]
        else:
            if not isinstance(axes_names, (tuple, list)):
                raise TypeError('`axes_names` should be tuple[str, ...] or list[str, ...] type')
            if len(axes_names) != len(shape):
                raise ValueError('`axes_names` length should match `shape` length')
            else:
                axes_names = enum_repeated_names(axes_names)
                axes = [Axis(num=i, name=name)
                        for i, name in enumerate(axes_names)]
        self._axes = axes

        # name
        if name is None:
            if network is None:
                name = self.__class__.__name__.lower()
        elif not isinstance(name, str):
            raise TypeError('`name` should be str type')
        self._name = name

        # network
        self._network = None
        if network is not None:
            if not isinstance(network, TensorNetwork):
                raise TypeError('`network` should be TensorNetwork type')
            network.add_node(self)

        self._tensor = torch.empty(shape)
        self._param_edges = param_edges
        self._edges = []

    # properties
    @property
    def tensor(self) -> Union[torch.Tensor, nn.Parameter]:
        return self._tensor

    @tensor.setter
    def tensor(self, tensor: torch.Tensor) -> None:
        self.set_tensor(tensor)

    @property
    def shape(self) -> torch.Size:
        return self._tensor.shape

    @property
    def rank(self) -> int:
        return len(self.shape)

    @property
    def axes(self) -> List[Axis]:
        return self._axes

    @property
    def axes_names(self) -> List[Text]:
        return list(map(lambda axis: axis.name, self.axes))

    @property
    def node1_list(self) -> List[bool]:
        return list(map(lambda axis: axis.node1, self.axes))

    @property
    def edges(self) -> List['AbstractEdge']:
        return self._edges

    @property
    def name(self) -> Text:
        return self._name

    # TODO: check if there is no repeated name in the network, if it does,
    #  add a unique id. Do this also first time name is assigned in init
    @name.setter
    def name(self, name: Text) -> None:
        pass

    @property
    def network(self) -> Optional['TensorNetwork']:
        return self._network

    # abstract methods
    @staticmethod
    @abstractmethod
    def set_tensor_format(tensor: torch.Tensor) -> Union[torch.Tensor, nn.Parameter]:
        pass

    @abstractmethod
    def parameterize(self, set_param: bool) -> 'AbstractNode':
        pass

    @abstractmethod
    def copy(self) -> 'AbstractNode':
        pass

    # methods
    # TODO: comment
    def size(self, dim: Optional[Union[int, Text, Axis]] = None) -> Union[torch.Size, int]:
        if dim is None:
            return self.shape
        axis_num = self.get_axis_number(dim)
        return self.shape[axis_num]

    def dim(self, dim: Optional[Union[int, Text, Axis]] = None) -> Union[torch.Size, int]:
        if dim is None:
            return torch.Size(list(map(lambda edge: edge.dim(), self.edges)))
        axis_num = self.get_axis_number(dim)
        return self.edges[axis_num].dim()

    def get_axis_number(self, axis: Union[int, Text, Axis]) -> int:
        if isinstance(axis, int):
            for ax in self.axes:
                if axis == ax.num:
                    return ax.num
            IndexError(f'Node {self!s} has no axis with index {axis}')
        elif isinstance(axis, str):
            for ax in self.axes:
                if axis == ax.name:
                    return ax.num
            IndexError(f'Node {self!s} has no axis with name {axis}')
        elif isinstance(axis, Axis):
            for ax in self.axes:
                if axis == ax:
                    return ax.num
            IndexError(f'Node {self!s} has no axis {axis!r}')
        else:
            TypeError('`axis` should be int, str or Axis type')

    def get_edge(self, axis: Union[int, Text, Axis]) -> 'AbstractEdge':
        axis_num = self.get_axis_number(axis)
        return self.edges[axis_num]

    def add_edge(self,
                 edge: 'AbstractEdge',
                 axis: Union[int, Text, Axis],
                 override: bool = False,
                 node1: Optional[bool] = None) -> None:
        """
        Add an edge to a given axis of the node.

        Parameters
        ----------
        edge: edge that is to be attached
        axis: axis to which the edge will be attached
        override: boolean indicating whether `edge` should override
                  an existing non-dangling edge at `axis`
        node1: boolean indicating if `self` is the node1 or node2 of `edge`
        """
        if edge.size() != self.size(axis):
            raise ValueError(f'Edge size should match node size at axis {axis!r}')
        if edge.dim() != self.dim(axis):
            raise ValueError(f'Edge dimension should match node dimension at axis {axis!r}')
        if node1 is None:
            if (edge.node1 == self) and (edge.node2 != self):
                node1 = True
            elif (edge.node1 != self) and (edge.node2 == self):
                node1 = False
            else:
                raise ValueError(f'If neither node1 nor node2 of `edge` is equal to {self!s},'
                                 f'`node1` should be provided. Otherwise `edge` cannot be attached')
        axis_num = self.get_axis_number(axis)
        if (not self.edges[axis_num].is_dangling()) and (not override):
            raise ValueError(f'Node {self!s} already has a non-dangling edge for axis {axis!r}')
        self._axes[axis_num]._node1 = node1
        self._edges[axis_num] = edge

    def param_edges(self,
                    set_param: Optional[bool] = None,
                    sizes: Optional[Sequence[int]] = None) -> Optional[bool]:
        if set_param is None:
            return self._param_edges
        else:
            if set_param:
                if not sizes:
                    sizes = self.shape
                elif len(sizes) != len(self.edges):
                    raise ValueError('`sizes` length should match the number of node\'s axes')
                for i, edge in enumerate(self.edges):
                    edge.parameterize(True, size=sizes[i])
            else:
                for param_edge in self.edges:
                    param_edge.parameterize(False)
            self._param_edges = set_param

    def reassign_edges(self,
                       axis: Optional[Union[int, Text, Axis]] = None,
                       override: bool = False) -> None:
        """
        When a node has edges that reference other, previously created edges,
        those edges might make no reference to this node. With `reassign_edges`,
        node1 or node2 of all/one of the edges is redirected to the node, according
        to each axis node1 attribute.

        Parameters
        ----------
        axis: which edge is to be reassigned
        override: if True, node1/node2 is changed in the original edge,
                  otherwise the edge will be copied and reassigned
        """
        if axis is None:
            if not override:
                for i, edge in enumerate(self.edges):
                    new_edge = edge.copy()
                    self._edges[i] = new_edge
                    if self.axes[i].node1:
                        new_edge._nodes[0] = self
                        new_edge._axes[0] = self.axes[i]
                    else:
                        new_edge._nodes[1] = self
                        new_edge._axes[1] = self.axes[i]
            else:
                for i, edge in enumerate(self.edges):
                    if self.axes[i].node1:
                        edge._nodes[0] = self
                        edge._axes[0] = self.axes[i]
                    else:
                        edge._nodes[1] = self
                        edge._axes[1] = self.axes[i]
        else:
            axis_num = self.get_axis_number(axis)
            if not override:
                new_edge = self.edges[axis_num].copy()
                self._edges[axis_num] = new_edge
                if self.axes[axis_num].node1:
                    new_edge._nodes[0] = self
                    new_edge._axes[0] = self.axes[axis_num]
                else:
                    new_edge._nodes[1] = self
                    new_edge._axes[1] = self.axes[axis_num]
            else:
                edge = self.edges[axis_num]
                if self.axes[axis_num].node1:
                    edge._nodes[0] = self
                    edge._axes[0] = self.axes[axis_num]
                else:
                    edge._nodes[1] = self
                    edge._axes[1] = self.axes[axis_num]

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
                          low: float = 0.,
                          high: float = 1.) -> torch.Tensor:
        if not isinstance(low, float):
            raise TypeError('`low` should be float type')
        if not isinstance(high, float):
            raise TypeError('`high` should be float type')
        if low >= high:
            raise ValueError('`low` should be strictly smaller than `high`')
        return torch.rand(shape) * (high - low) + low

    @staticmethod
    def _make_randn_tensor(shape: Union[int, Sequence[int], torch.Size],
                           mean: float = 0.,
                           std: float = 1.) -> torch.Tensor:
        if not isinstance(mean, float):
            raise TypeError('`mean` should be float type')
        if not isinstance(std, float):
            raise TypeError('`std` should be float type')
        if std <= 0:
            raise ValueError('`std` should be positive')
        return torch.randn(shape) * std + mean

    def make_tensor(self,
                    shape: Optional[Union[int, Sequence[int], torch.Size]] = None,
                    init_method: Text = 'zeros',
                    **kwargs: float) -> torch.Tensor:
        if shape is None:
            shape = self.shape
        if init_method == 'zeros':
            return torch.zeros(shape)
        elif init_method == 'ones':
            return torch.ones(shape)
        elif init_method == 'copy':
            return self._make_copy_tensor(shape)
        elif init_method == 'rand':
            return self._make_rand_tensor(shape, **kwargs)
        elif init_method == 'randn':
            return self._make_randn_tensor(shape, **kwargs)
        elif init_method == 'neurips':
            pass
        else:
            raise ValueError('Choose a valid `init_method`: "zeros", '
                             '"ones", "copy", "rand", "randn", "neurips"')

    def set_tensor(self,
                   tensor: Optional[torch.Tensor] = None,
                   init_method: Optional[Text] = 'zeros',
                   **kwargs: float) -> None:
        if tensor is not None:
            if not isinstance(tensor, torch.Tensor):
                raise ValueError('`tensor` should be torch.Tensor type')
            if tensor.shape != self.shape:
                raise ValueError('`tensor` shape should match node shape')
            self._tensor = self.set_tensor_format(tensor)
        elif init_method is not None:
            tensor = self.make_tensor(init_method=init_method, **kwargs)
            self._tensor = self.set_tensor_format(tensor)
        else:
            raise ValueError('One of `tensor` or `init_method` must be provided')

    def unset_tensor(self) -> None:
        self._tensor = torch.empty(self.shape)

    # TODO: set predefined init_method and **kwargs regarding to the values of `self` (the node)
    # TODO: manage case size = 0, or dim = 0. We have to make dimension 1 in that axis,
    #  not 0, in that case the tensor disappears
    def _change_axis_size(self,
                          axis: Union[int, Text, Axis],
                          size: int,
                          padding_method: Text = 'zeros',
                          **kwargs: float) -> None:
        if size <= 0:
            raise ValueError('new `size` should be greater than zero')
        axis_num = self.get_axis_number(axis)
        index = list()
        for i, dim in enumerate(self.shape):
            if i == axis_num:
                if size > dim:
                    index.append(slice(size - dim, size))
                else:
                    index.append(slice(dim - size, dim))
            else:
                index.append(slice(0, dim))

        if size < self.shape[axis_num]:
            self._tensor = self.set_tensor_format(self.tensor[index])
        elif size > self.shape[axis_num]:
            new_shape = list(self.shape)
            new_shape[axis_num] = size
            new_tensor = self.make_tensor(new_shape, padding_method, **kwargs)
            new_tensor[index] = self.tensor
            self._tensor = self.set_tensor_format(new_tensor)

    def move_to_network(self, network: 'TensorNetwork') -> None:
        if network != self.network:
            network_nodes = self.network.nodes
            self.network._nodes = dict()
            network.add_nodes_from(network_nodes)
            #for node in network_nodes:
            #    node._network = network

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

    # TODO: element-wise operations
    def __mul__(self, other: 'AbstractNode') -> 'AbstractNode':
        pass

    def __add__(self, other: 'AbstractNode') -> 'AbstractNode':
        pass

    def __sub__(self, other: 'AbstractNode') -> 'AbstractNode':
        pass

    # TODO: tensor product of two nodes
    def __mod__(self, other: 'AbstractNode') -> 'AbstractNode':
        pass

    def __str__(self) -> Text:
        return self.name

    def __repr__(self) -> Text:
        return f'{self.__class__.__name__}(\n ' \
               f'\tname: {self.name}\n' \
               f'\ttensor:\n{tab_string(repr(self.tensor.data), 2)}\n' \
               f'\taxes: {self.axes_names}\n' \
               f'\tedges:\n{tab_string(repr(self.edges), 2)})'


# TODO: implement functions like tn.ones, tn.zeros that use this functions
#  to create a node and set its tensor
# TODO: create new class methods like Node.randn() to init objects directly with those methods
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
                 name: Optional[Text] = None,
                 network: Optional['TensorNetwork'] = None,
                 param_edges: bool = False,
                 tensor: Optional[torch.Tensor] = None,
                 edges: Optional[List['AbstractEdge']] = None,
                 node1_list: Optional[List[bool]] = None,
                 init_method: Optional[Text] = None,
                 **kwargs: float) -> None:
        """
        Parameters
        ----------
        tensor: tensor "contained" in the node
        edges: list of edges to attach to the node
        node1_list: list of node1 boolean values to attach to each axis
        init_method: method to use to initialize the
                     node's tensor when it is not provided
        kwargs: keyword arguments for the init_method
        """

        # shape and tensor
        if (shape is None) == (tensor is None):
            if shape is None:
                raise ValueError('One of `shape` or `tensor` must be provided')
            else:
                raise ValueError('Only one of `shape` or `tensor` should be provided')
        elif shape is not None:
            super().__init__(shape, axes_names, name, network, param_edges)
            if init_method is not None:
                self.set_tensor(init_method=init_method, **kwargs)
        else:
            super().__init__(tensor.shape, axes_names, name, network, param_edges)
            self.set_tensor(tensor)

        # edges
        if edges is None:
            edges = [self.make_edge(ax)
                     for ax in self.axes]
        else:
            for i, axis in enumerate(self.axes):
                if not isinstance(node1_list[i], bool):
                    raise TypeError('`node1_list` should be List[bool] type')
                axis._node1 = node1_list[i]
        self._edges = edges

    # methods
    @staticmethod
    def set_tensor_format(tensor: torch.Tensor) -> torch.Tensor:
        return tensor

    # TODO: llamar a método de TensorNetwork que cambie un nodo de la red por otro
    def parameterize(self, set_param: bool) -> Union['Node', 'ParamNode']:
        if set_param:
            # TODO: can we set new tensor with the same name as other?
            #  We have to override the old one
            new_node = ParamNode(shape=self.shape if self.tensor is None else None,
                                 axes_names=self.axes_names,
                                 name=self.name,
                                 network=self.network,
                                 param_edges=self.param_edges(),
                                 tensor=self.tensor,
                                 edges=self.edges,
                                 node1_list=self.node1_list)
            new_node.reassign_edges(override=True)
            if self.network is not None:
                # TODO: cambiar al anterior nodo por este en la TN
                self.network._add_param(new_node)
            return new_node
        else:
            return self

    def copy(self) -> 'Node':
        new_node = Node(axes_names=self.axes_names,
                        name=self.name,
                        network=self.network,
                        param_edges=self.param_edges(),
                        tensor=self.tensor,
                        edges=self.edges,
                        node1_list=self.node1_list)
        new_node.reassign_edges(override=False)
        return new_node

    def make_edge(self, axis: Axis) -> Union['Edge', 'ParamEdge']:
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
                 name: Optional[Text] = None,
                 network: Optional['TensorNetwork'] = None,
                 param_edges: bool = False) -> None:

        super().__init__(shape, axes_names, name, network, param_edges, init_method='copy')

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
                 network: Optional['TensorNetwork'] = None,
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

    def make_edge(self, axis: Axis):
        if axis == self.stacked_dim:
            return Edge(node1=self, axis1=axis)
        return StackEdge(self.edges_dict[axis], node1=self, axis1=axis)


class ParamNode(AbstractNode, nn.Module):
    """
    Class for trainable nodes. Subclass of PyTorch nn.Module.
    Should be subclassed by any new class of trainable nodes.

    Used as initial nodes of a tensor network that is to be trained.
    """

    def __init__(self,
                 shape: Optional[Union[int, Sequence[int], torch.Size]] = None,
                 axes_names: Optional[Sequence[Text]] = None,
                 name: Optional[Text] = None,
                 network: Optional['TensorNetwork'] = None,
                 param_edges: bool = False,
                 tensor: Optional[torch.Tensor] = None,
                 edges: Optional[List['AbstractEdge']] = None,
                 node1_list: Optional[List[bool]] = None,
                 init_method: Optional[Text] = None,
                 **kwargs: float) -> None:
        """
        Parameters
        ----------
        tensor: tensor "contained" in the node
        edges: list of edges to attach to the node
        node1_list: list of node1 boolean values to attach to each axis
        init_method: method to use to initialize the
                     node's tensor when it is not provided
        kwargs: keyword arguments for the init_method
        """

        nn.Module.__init__(self)

        # shape and tensor
        if (shape is None) == (tensor is None):
            if shape is None:
                raise ValueError('One of `shape` or `tensor` must be provided')
            else:
                raise ValueError('Only one of `shape` or `tensor` should be provided')
        elif shape is not None:
            AbstractNode.__init__(self, shape, axes_names, name, network, param_edges)
            if init_method is not None:
                self.set_tensor(init_method=init_method, **kwargs)
        else:
            AbstractNode.__init__(self, tensor.shape, axes_names, name, network, param_edges)
            self.set_tensor(tensor)

        # edges
        if edges is None:
            edges = [self.make_edge(ax)
                     for ax in self.axes]
        else:
            for i, axis in enumerate(self.axes):
                if not isinstance(node1_list[i], bool):
                    raise TypeError('`node1_list` should be List[bool] type')
                axis._node1 = node1_list[i]
        self._edges = edges

    # properties
    @property
    def grad(self) -> Optional[torch.Tensor]:
        return self.tensor.grad

    # methods
    # TODO: what happens if tensor is None
    @staticmethod
    def set_tensor_format(tensor: torch.Tensor) -> nn.Parameter:
        """
        If we provide a nn.Parameter, the ParamNode will use such parameter
        instead of creating a new nn.Parameter object
        """
        if isinstance(tensor, nn.Parameter):
            return tensor
        return nn.Parameter(tensor)

    def parameterize(self, set_param: bool) -> Union['Node', 'ParamNode']:
        if not set_param:
            new_node = Node(shape=self.shape if self.tensor is None else None,
                            axes_names=self.axes_names,
                            name=self.name,
                            network=self.network,
                            param_edges=self.param_edges(),
                            tensor=self.tensor,
                            edges=self.edges,
                            node1_list=self.node1_list)
            new_node.reassign_edges(override=True)
            if self.network is not None:
                # TODO: cambiar en la TN antiguo nodo por este
                self.network._remove_param(self)
            return new_node
        else:
            return self

    def copy(self) -> 'ParamNode':
        new_node = ParamNode(axes_names=self.axes_names,
                             name=self.name,
                             network=self.network,
                             param_edges=self.param_edges(),
                             tensor=self.tensor,
                             edges=self.edges,
                             node1_list=self.node1_list)
        new_node.reassign_edges(override=False)
        return new_node

    def make_edge(self, axis: Axis) -> Union['ParamEdge', 'Edge']:
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
        self._axes = [axis1, axis2]

    # properties
    @property
    def node1(self) -> AbstractNode:
        return self._nodes[0]

    @property
    def node2(self) -> AbstractNode:
        return self._nodes[1]

    @property
    def axis1(self) -> Axis:
        return self._axes[0]

    @property
    def axis2(self) -> Axis:
        return self._axes[1]

    @property
    def name(self) -> Text:
        if self.is_dangling():
            return f'{self.node1.name}[{self.axis1.name}] <-> None'
        return f'{self.node1.name}[{self.axis1.name}] <-> ' \
               f'{self.node2.name}[{self.axis2.name}]'

    # abstract methods
    @abstractmethod
    def dim(self) -> int:
        pass

    @abstractmethod
    def change_size(self, size: int, padding_method: Text = 'zeros', **kwargs) -> None:
        pass

    @abstractmethod
    def parameterize(self,
                     set_param: bool,
                     size: Optional[int] = None) -> 'AbstractEdge':
        pass

    @abstractmethod
    def copy(self) -> 'AbstractEdge':
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

    Used by default to create a non-trainable node.
    """

    # methods
    def dim(self) -> int:
        return self.size()

    def change_size(self, size: int, padding_method: Text = 'zeros', **kwargs) -> None:
        if not isinstance(size, int):
            TypeError('`size` should be int type')
        if not self.is_dangling():
            self.node2._change_axis_size(self.axis2, size, padding_method, **kwargs)
        self.node1._change_axis_size(self.axis1, size, padding_method, **kwargs)

    def parameterize(self,
                     set_param: bool = True,
                     size: Optional[int] = None) -> Union['Edge', 'ParamEdge']:
        if set_param:
            dim = self.dim()
            if size is not None:
                if size > dim:
                    self.change_size(size)
                elif size < dim:
                    raise ValueError(f'`size` should be greater than current '
                                     f'dimension: {dim}, or NoneType')
            new_edge = ParamEdge(node1=self.node1, axis1=self.axis1, dim=dim,
                                 node2=self.node2, axis2=self.axis2)
            if not self.is_dangling():
                self.node2.add_edge(new_edge, self.axis2, override=True)
            self.node1.add_edge(new_edge, self.axis1, override=True)
            if self.node1.network is not None:
                self.node1.network._add_param(new_edge)
            return new_edge
        else:
            return self

    def copy(self) -> 'Edge':
        new_edge = Edge(node1=self.node1, axis1=self.axis1,
                        node2=self.node2, axis2=self.axis2)
        return new_edge

    @overload
    def __xor__(self, other: 'Edge') -> 'Edge':
        pass

    @overload
    def __xor__(self, other: 'ParamEdge') -> 'ParamEdge':
        pass

    # TODO: change types
    def __xor__(self, other: Union['Edge', 'ParamEdge']) -> Union['Edge', 'ParamEdge']:
        return connect(self, other)

    # TODO: implement this
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
    """

    def __init__(self,
                 node1: AbstractNode,
                 axis1: Axis,
                 dim: Optional[int] = None,
                 shift: Optional[Union[int, float]] = None,
                 slope: Optional[Union[int, float]] = None,
                 node2: Optional[AbstractNode] = None,
                 axis2: Optional[Axis] = None) -> None:

        nn.Module.__init__(self)
        AbstractEdge.__init__(self, node1, axis1, node2, axis2)

        # shift and slope
        if dim is not None:
            if (shift is not None) or (slope is not None):
                warnings.warn('`shift` and/or `slope` might have been ignored '
                              'when initializing the edge')
            shift, slope = self.compute_parameters(node1.size(axis1), dim)
        else:
            if shift is None:
                shift = _DEFAULT_SHIFT
            else:
                if isinstance(shift, int):
                    shift = float(shift)
                elif not isinstance(shift, float):
                    raise TypeError('`shift` should be int or float type')

            if slope is None:
                slope = _DEFAULT_SLOPE
            else:
                if isinstance(slope, int):
                    slope = float(slope)
                elif not isinstance(slope, float):
                    raise TypeError('`slope` should be int or float type')

        self._shift = nn.Parameter(torch.tensor(shift))
        self._prev_shift = shift
        self._slope = nn.Parameter(torch.tensor(slope))
        self._prev_slope = slope
        self._sigmoid = nn.Sigmoid()
        self._matrix = None
        self._dim = None
        self.set_matrix()

    # properties
    @property
    def shift(self) -> nn.Parameter:
        return self._shift

    @shift.setter
    def shift(self, shift: Union[int, float, nn.Parameter]) -> None:
        if isinstance(shift, int):
            shift = float(shift)
            self._shift = nn.Parameter(torch.tensor(shift))
            self._prev_shift = shift
        elif isinstance(shift, float):
            self._shift = nn.Parameter(torch.tensor(shift))
            self._prev_shift = shift
        elif isinstance(shift, nn.Parameter):
            self._shift = shift
            self._prev_shift = shift.item()
        else:
            raise TypeError('`shift` should be int, float or nn.Parameter type')
        self.set_matrix()

    @property
    def slope(self) -> nn.Parameter:
        return self._slope

    @slope.setter
    def slope(self, slope: Union[int, float]) -> None:
        if isinstance(slope, int):
            slope = float(slope)
            self._slope = nn.Parameter(torch.tensor(slope))
            self._prev_slope = slope
        elif isinstance(slope, float):
            self._slope = nn.Parameter(torch.tensor(slope))
            self._prev_slope = slope
        elif isinstance(slope, nn.Parameter):
            self._slope = slope
            self._prev_slope = slope.item()
        else:
            raise TypeError('`slope` should be int, float or nn.Parameter type')
        self.set_matrix()

    @property
    def matrix(self) -> torch.Tensor:
        if self.is_updated():
            return self._matrix
        self.set_matrix()
        return self._matrix

    @property
    def grad(self) -> Tuple[Optional[torch.Tensor], Optional[torch.Tensor]]:
        return self.shift.grad, self.slope.grad

    # methods
    @staticmethod
    def compute_parameters(size: int, dim: int) -> Tuple[float, float]:
        if not isinstance(size, int):
            raise TypeError('`size` should be int type')
        if not isinstance(dim, int):
            raise TypeError('`dim` should be int type')
        if dim > size:
            raise ValueError('`dim` should be smaller or equal than `size`')
        shift = (size - dim) - 0.5
        slope = _DEFAULT_SLOPE
        return shift, slope

    def is_updated(self) -> bool:
        if (self._prev_shift == self._shift.item()) and\
                (self._prev_slope == self._slope.item()):
            return True
        return False

    def sigmoid(self, x: torch.Tensor) -> torch.Tensor:
        return self._sigmoid(x)

    def make_matrix(self) -> torch.Tensor:
        matrix = torch.zeros((self.size(), self.size()))
        i = torch.arange(self.size())
        matrix[(i, i)] = self.sigmoid(self.slope * (i - self.shift))
        return matrix

    # TODO: if dim = 0 at some point, we might disconnect nodes and reduce their rank
    def set_matrix(self) -> None:
        self._matrix = self.make_matrix()
        signs = torch.sign(self._matrix.diagonal() - 0.5)
        dim = int(torch.where(signs == 1,
                              signs, torch.zeros_like(signs)).sum())
        self._dim = dim

    def dim(self) -> int:
        return self._dim

    def change_size(self, size: int, padding_method: Text = 'zeros', **kwargs) -> None:
        if not isinstance(size, int):
            TypeError('`size` should be int type')
        if not self.is_dangling():
            self.node2._change_axis_size(self.axis2, size, padding_method, **kwargs)
        self.node1._change_axis_size(self.axis1, size, padding_method, **kwargs)

        self.shift, self.slope = self.compute_parameters(size, self.dim())
        self.set_matrix()

    def parameterize(self,
                     set_param: bool = True,
                     size: Optional[int] = None) -> Union['Edge', 'ParamEdge']:
        if not set_param:
            self.change_size(self.dim())
            new_edge = Edge(node1=self.node1, axis1=self.axis1,
                            node2=self.node2, axis2=self.axis2)
            if not self.is_dangling():
                self.node2.add_edge(new_edge, self.axis2, override=True)
            self.node1.add_edge(new_edge, self.axis1, override=True)
            if self.node1.network is not None:
                self.node1.network._remove_param(self)
            return new_edge
        else:
            return self

    def copy(self) -> 'ParamEdge':
        new_edge = ParamEdge(node1=self.node1, axis1=self.axis1,
                             shift=self.shift.item(), slope=self.slope.item(),
                             node2=self.node2, axis2=self.axis2)
        return new_edge

    # TODO: check types, may be overload
    def __xor__(self, other: AbstractEdge) -> 'ParamEdge':
        return connect(self, other)

    def __or__(self):
        pass


# TODO: change output type -> Union[Edge, ParamEdge]. Do we return StackEdge or any other type?
def connect(edge1: AbstractEdge,
            edge2: AbstractEdge,
            override_network: bool = False) -> Union[Edge, ParamEdge]:
    for edge in [edge1, edge2]:
        if not edge.is_dangling():
            raise ValueError(f'Edge {edge!s} is not a dangling edge. '
                             f'This edge points to nodes: {edge.node1!s} and {edge.node2!s}')
    if edge1 is edge2:
        raise ValueError(f'Cannot connect edge {edge1!s} to itself')
    if edge1.size() != edge2.size():
        raise ValueError(f'Cannot connect edges of unequal size. '
                         f'Size of edge {edge1!s}: {edge1.size()}. '
                         f'Size of edge {edge2!s}: {edge2.size()}')
    if edge1.dim() != edge2.dim():
        raise ValueError(f'Cannot connect edges of unequal dimension. '
                         f'Dimension of edge {edge1!s}: {edge1.dim()}. '
                         f'Dimension of edge {edge2!s}: {edge2.dim()}')

    node1, axis1 = edge1.node1, edge1.axis1
    node2, axis2 = edge2.node1, edge2.axis1
    net1, net2 = node1.network, node2.network

    if net1 is not None:
        if net1 != net2:
            if (net2 is not None) and not override_network:
                raise ValueError(f'Cannot connect edges from nodes in different networks. '
                                 f'Set `override` to True if you want to override {net2!s} '
                                 f'with {net1!s} in {node1!s} and its neighbours.')
            node2.move_to_network(net1)
        net = net1
    else:
        if net2 is not None:
            node1.move_to_network(net2)
        net = net2

    if isinstance(edge1, ParamEdge) == isinstance(edge2, ParamEdge):
        if isinstance(edge1, ParamEdge):
            shift = edge1.shift.item()
            slope = edge1.slope.item()
            new_edge = ParamEdge(node1=node1, axis1=axis1,
                                 shift=shift, slope=slope,
                                 node2=node2, axis2=axis2)
            if net is not None:
                net._remove_param(edge1)
                net._remove_param(edge2)
                net._add_param(new_edge)
        else:
            new_edge = Edge(node1, axis1, node2, axis2)
    else:
        if isinstance(edge1, ParamEdge):
            shift = edge1.shift.item()
            slope = edge1.slope.item()
            if net is not None:
                net._remove_param(edge1)
        else:
            shift = edge2.shift.item()
            slope = edge2.slope.item()
            if net is not None:
                net._remove_param(edge2)
        new_edge = ParamEdge(node1=node1, axis1=axis1,
                             shift=shift, slope=slope,
                             node2=node2, axis2=axis2)
        if net is not None:
            net._add_param(new_edge)

    node1.add_edge(new_edge, axis1, override=True)
    node2.add_edge(new_edge, axis2, override=True)
    return new_edge


# TODO: parameterize and deparameterize network, return a different network so that
#  we can retrieve the original parameterized nodes/edges with their initial sizes


# TODO: names of (at least) ParamNodes and ParamEdges must be unique in a tensor network
# TODO: llevar una network auxiliar para hacer los cálculos, después hacer .clear()
# TODO: gestionar nombres de nodes y edges que se crean en la network
# TODO: add __repr__, __str__
class TensorNetwork(nn.Module):
    """
    Al contraer una red se crea una Network auxiliar formada por Nodes en lugar
    de ParamNodes y Edges en lugar de ParamEdges. Ahí se van guardando todos los
    nodos auxiliares, resultados de operaciones intermedias, se termina de contraer
    la red y se devuelve el resultado

    Formado opr AbstractNodes y AbstractEdges

        -nodes (add modules, del modules)
        -edges
        -forward (create nodes for input data and generate the final
            network to be contracted)
        -contraction of network (identify similar nodes to stack them
            and optimize)
        -to_tensornetwork (returns a dict or list with all the nodes
            with edges connected as the original network)
    """

    def __init__(self):
        nn.Module.__init__(self)
        # TODO: Contractions of the network happen in the _ops_tn, and they are in-place,
        #  so that we can keep track of the connections even after some contractions have
        #  already been computed

    def _add_param(self, param: Union[ParamNode, ParamEdge]) -> None:
        if not hasattr(self, param.name):
            self.add_module(param.name, param)
        else:
            raise ValueError(f'Network already has attribute named {param.name}')

    def _remove_param(self, param: Union[ParamNode, ParamEdge]) -> None:
        if hasattr(self, param.name):
            delattr(self, param.name)
        else:
            warnings.warn('Cannot remove a parameter that is not in the network')

    def add_node(self, node: AbstractNode) -> None:
        # TODO: check this
        if hasattr(node, '_network'):
            if node.network != self:
                node._network = self
        if isinstance(node, ParamNode):
            self.add_module(node.name, node)
        for edge in node.edges:
            if isinstance(edge, ParamEdge):
                self.add_module(edge.name, edge)
        if node.name in self.nodes:
            i = 0
            for node_name in self.nodes:
                # TODO: sure? is it the first element? [0]
                node_name = node_name.split('__')[0]
                if node.name == node_name:
                    i += 1
            node.name = f'{node.name}__{i}'
        self.nodes[node.name] = node
        # TODO: if we copy the node, the copied edges still make reference to the other
        #  "original" node, we have to copy nodes and change the reference of the copied
        #  edges to the other copied nodes (neighbours)
        self._ops_tn.nodes[node.name] = node.copy()

    def add_nodes_from(self, nodes_list: Sequence[AbstractNode]):
        for name, node in nodes_list:
            self.add_node(node)

    """
    def connect_nodes(nodes_list, axis_list):
        if len(nodes_list) == 2 and len(axis_list) == 2:
            nodes_list[0][axis_list[0]] ^ nodes_list[1][axis_list[1]]
        else:
            raise ValueError('Both nodes_list and axis_list must have length 2')

    def initialize(self, *args):
        for child in self.children():
            if isinstance(child, 'AbstractNode'):
                child.initialize(*args)
            # Los Edges se inicializan solos

    # def remove_node(self, name) -> None:
    #    delattr(self, name)
    #    self._nodes.remove(name)

    # def add_data(self, data):
    #    pass

    # @abstractmethod
    def contract_network(self):
        pass

    # def forward(self, data):
    #    aux_net = self.add_data(data)
    #    result = aux_net.contract_network()
    #    self.clear_op_network()
    #    return result
    """
