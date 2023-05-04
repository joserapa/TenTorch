"""
This script contains:

    Operation Class:
        * Operation
        
    Tensor-like operations:
        * permute
        * permute_           (in-place)
        * tprod
        * mul
        * add
        * sub
        
    Node-like operations:
        * split
        * split_             (in-place)
        * svd_               (in-place) (edge operation)
        * svdr_              (in-place) (edge operation)
        * qr_                (in-place) (edge operation)
        * rq_                (in-place) (edge operation)
        * contract_edges
        * contract_          (in-place) (edge operation)
        * get_shared_edges
        * contract_between
        * contract_between_  (in-place)
        * stack
        * unbind
        * einsum
        * stacked_einsum
"""

from typing import Callable, List, Optional, Sequence, Text, Tuple, Union
import types

import torch
import opt_einsum

from tensorkrowch.components import *
from tensorkrowch.utils import (inverse_permutation, is_permutation,
                                list2slice, permute_list)

from tensorkrowch import _C


Ax = Union[int, Text, Axis]


def copy_func(f):
    """Returns a function with the same code, defaults, closure and name."""
    fn = types.FunctionType(f.__code__, f.__globals__, f.__name__,
                            f.__defaults__, f.__closure__)
    
    # In case f was given attrs (note this dict is a shallow copy)
    fn.__dict__.update(f.__dict__) 
    return fn

###############################################################################
#                               OPERATION CLASS                               #
###############################################################################
class Operation:
    """
    Class for node operations. A node operation is made up of two functions,
    the one that is executed the first time the operation is called (with the
    same arguments) and the one that is executed in every other call. Both
    functions are usually similar, though the former computes extra things
    regarding the creation of the resultant nodes and some auxilliary operations
    whose result will be the same in every call (e.g. when contracting two nodes,
    maybe a permutation of the tensors should be first performed; how this
    permutation is carried out is always the same, though the tensors themselves
    are different).
    
    Parameters
    ----------
    name : str
        Name of the operation. It cannot coincide with another operation's name.
        Operation names can be checked via ``net.operations``.
    check_first : callable
        Function that checks if the operation has been called at least one time.
    func1 : callable
        Function that is called the first time the operation is performed.
    func2 : callable
        Function that is called the next times the operation is performed.
    """

    def __init__(self, name: Text, check_first, func1, func2):
        assert isinstance(check_first, Callable)
        assert isinstance(func1, Callable)
        assert isinstance(func2, Callable)
        self.func1 = func1
        self.func2 = func2
        self.check_first = check_first
        
        # Operations could be overriden
        TensorNetwork.operations[name] = self

    def __call__(self, *args, **kwargs):
        successor = self.check_first(*args, **kwargs)

        if successor is None:
            return self.func1(*args, **kwargs)
        else:
            args = [successor] + list(args)
            return self.func2(*args, **kwargs)


###############################################################################
#                           TENSOR-LIKE OPERATIONS                            #
###############################################################################

#################################   PERMUTE    ################################
def _check_first_permute(node: AbstractNode,
                         axes: Sequence[Ax]) -> Optional[Successor]:
    kwargs = {'node': node,
              'axes': axes}
    if 'permute' in node._successors:
        for succ in node._successors['permute']:
            if succ.kwargs == kwargs:
                return succ
    return None


def _permute_first(node: AbstractNode, axes: Sequence[Ax]) -> Node:
    axes_nums = []
    for axis in axes:
        axes_nums.append(node.get_axis_num(axis))

    if not is_permutation(list(range(len(axes_nums))), axes_nums):
        raise ValueError('The provided list of axis is not a permutation of the'
                         ' axes of the node')
    else:
        new_node = Node(axes_names=permute_list(node.axes_names, axes_nums),
                        name='permute',
                        network=node._network,
                        leaf=False,
                        param_edges=node.param_edges(),
                        tensor=node.tensor.permute(axes_nums),
                        edges=permute_list(node._edges, axes_nums),
                        node1_list=permute_list(node.is_node1(), axes_nums))

    # Create successor
    net = node._network
    successor = Successor(kwargs={'node': node,
                                  'axes': axes},
                          child=new_node,
                          hints=axes_nums)
    
    # Add successor to parent
    if 'permute' in node._successors:
        node._successors['permute'].append(successor)
    else:
        node._successors['permute'] = [successor]

    # Add operation to list of performed operations of TN
    net._seq_ops.append(('permute', successor.kwargs))
    
    # Record in inverse_memory while tracing
    node._record_in_inverse_memory()

    return new_node


def _permute_next(successor: Successor,
                  node: AbstractNode,
                  axes: Sequence[Ax]) -> Node:
    # All arguments are mandatory though some might not be used
    new_tensor = node.tensor.permute(successor.hints)
    child = successor.child
    child._unrestricted_set_tensor_ops(new_tensor)
    
    # Record in inverse_memory while contracting
    # (to delete memory if possible)
    node._record_in_inverse_memory()
    
    return child


permute_op = Operation('permute',
                       _check_first_permute,
                       _permute_first,
                       _permute_next)

def permute(node: AbstractNode, axes: Sequence[Ax]):
    """
    Permutes the nodes' tensor, as well as its axes and edges to match the new
    shape.
    
    See `permute <https://pytorch.org/docs/stable/generated/torch.permute.html>`_.
    
    Parameters
    ----------
    node: Node or ParamNode
        Node whose tensor is to be permuted.
    axes: list[int, str or Axis]
        List of axes in the permuted order.
    """
    return permute_op(node, axes)


permute_node = copy_func(permute)
permute_node.__doc__ = \
    """
    Permutes the nodes' tensor, as well as its axes and edges to match the new
    shape.
    
    See `permute <https://pytorch.org/docs/stable/generated/torch.permute.html>`_.
    
    Parameters
    ----------
    axes: list[int, str or Axis]
        List of axes in the permuted order.
    """

AbstractNode.permute = permute_node


def permute_(node: AbstractNode, axes: Sequence[Ax]) -> Node:
    """
    Permutes the nodes' tensor, as well as its axes and edges to match the new
    shape (in-place).
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.
    
    See `permute <https://pytorch.org/docs/stable/generated/torch.permute.html>`_.
    
    Parameters
    ----------
    node: Node or ParamNode
        Node whose tensor is to be permuted.
    axes: list[int, str or Axis]
        List of axes in the permuted order.
    """
    axes_nums = []
    for axis in axes:
        axes_nums.append(node.get_axis_num(axis))

    if not is_permutation(list(range(len(axes_nums))), axes_nums):
        raise ValueError('The provided list of axis is not a permutation of the'
                         ' axes of the node')
    else:
        new_node = Node(axes_names=permute_list(node.axes_names, axes_nums),
                        name=node._name,
                        override_node=True,
                        network=node._network,
                        param_edges=node.param_edges(),
                        override_edges=True,
                        tensor=node.tensor.permute(axes_nums).detach(),
                        edges=permute_list(node._edges, axes_nums),
                        node1_list=permute_list(node.is_node1(), axes_nums))
        
    return new_node


permute_node_ = copy_func(permute_)
permute_node_.__doc__ = \
    """
    Permutes the nodes' tensor, as well as its axes and edges to match the new
    shape (in-place).

    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    See `permute <https://pytorch.org/docs/stable/generated/torch.permute.html>`_.

    Parameters
    ----------
    axes: list[int, str or Axis]
        List of axes in the permuted order.
    """

AbstractNode.permute_ = permute_node_


##################################   TPROD    #################################
def _check_first_tprod(node1: AbstractNode,
                       node2: AbstractNode) -> Optional[Successor]:
    kwargs = {'node1': node1,
              'node2': node2}
    if 'tprod' in node1._successors:
        for succ in node1._successors['tprod']:
            if succ.kwargs == kwargs:
                return succ
    return None


def _tprod_first(node1: AbstractNode, node2: AbstractNode) -> Node:
    if node1._network != node2._network:
        raise ValueError('Nodes must be in the same network')
    if node2 in node1.neighbours():
        raise ValueError('Tensor product cannot be performed between connected'
                         ' nodes')

    new_tensor = torch.outer(node1.tensor.flatten(),
                             node2.tensor.flatten()).view(*(list(node1._shape) +
                                                            list(node2._shape)))
    new_node = Node(axes_names=node1.axes_names + node2.axes_names,
                    name='tprod',
                    network=node1._network,
                    leaf=False,
                    tensor=new_tensor,
                    edges=node1._edges + node2._edges,
                    node1_list=node1.is_node1() + node2.is_node1())

    # Create successor
    net = node1._network
    successor = Successor(kwargs={'node1': node1,
                                  'node2': node2},
                          child=new_node)
    
    # Add successor to parent
    if 'tprod' in node1._successors:
        node1._successors['tprod'].append(successor)
    else:
        node1._successors['tprod'] = [successor]

    # Add operation to list of performed operations of TN
    net._seq_ops.append(('tprod', successor.kwargs))
    
    # Record in inverse_memory while tracing
    node1._record_in_inverse_memory()
    node2._record_in_inverse_memory()

    return new_node


def _tprod_next(successor: Successor,
                node1: AbstractNode,
                node2: AbstractNode) -> Node:
    new_tensor = torch.outer(node1.tensor.flatten(),
                             node2.tensor.flatten()).view(*(list(node1._shape) +
                                                            list(node2._shape)))
    child = successor.child
    child._unrestricted_set_tensor_ops(new_tensor)
    
    # Record in inverse_memory while contracting
    # (to delete memory if possible)
    node1._record_in_inverse_memory()
    node2._record_in_inverse_memory()
    
    return child


tprod_op = Operation('tprod', _check_first_tprod, _tprod_first, _tprod_next)

def tprod(node1: AbstractNode, node2: AbstractNode) -> Node:
    """
    Tensor product between two nodes. It can also be performed using the
    operator ``%``.

    Parameters
    ----------
    node1 : Node or ParamNode
        First node to be multiplied. Its edges will appear first in the
        resultant node.
    node2 : Node or ParamNode
        Second node to be multiplied. Its edges will appear second in the
        resultant node.

    Returns
    -------
    Node
    """
    return tprod_op(node1, node2)


tprod_node = copy_func(tprod)
tprod_node.__doc__ = \
    """
    Tensor product between two nodes. It can also be performed using the
    operator ``%``.

    Parameters
    ----------
    node2 : Node or ParamNode
        Second node to be multiplied. Its edges will appear second in the
        resultant node.

    Returns
    -------
    Node
    """

AbstractNode.__mod__ = tprod_node


###################################   MUL    ##################################
def _check_first_mul(node1: AbstractNode,
                     node2: AbstractNode) -> Optional[Successor]:
    kwargs = {'node1': node1,
              'node2': node2}
    if 'mul' in node1._successors:
        for succ in node1._successors['mul']:
            if succ.kwargs == kwargs:
                return succ
    return None


def _mul_first(node1: AbstractNode, node2: AbstractNode) -> Node:
    if node1._network != node2._network:
        raise ValueError('Nodes must be in the same network')

    new_tensor = node1.tensor * node2.tensor
    new_node = Node(axes_names=node1.axes_names,
                    name='mul',
                    network=node1._network,
                    leaf=False,
                    tensor=new_tensor,
                    edges=node1._edges,
                    node1_list=node1.is_node1())
    
    # Create successor
    net = node1._network
    successor = Successor(kwargs={'node1': node1,
                                  'node2': node2},
                          child=new_node)
    
    # Add successor to parent
    if 'mul' in node1._successors:
        node1._successors['mul'].append(successor)
    else:
        node1._successors['mul'] = [successor]

    # Add operation to list of performed operations of TN
    net._seq_ops.append(('mul', successor.kwargs))
    
    # Record in inverse_memory while tracing
    node1._record_in_inverse_memory()
    node2._record_in_inverse_memory()

    return new_node


def _mul_next(successor: Successor,
              node1: AbstractNode,
              node2: AbstractNode) -> Node:
    new_tensor = node1.tensor * node2.tensor
    child = successor.child
    child._unrestricted_set_tensor_ops(new_tensor)
    
    # Record in inverse_memory while contracting
    # (to delete memory if possible)
    node1._record_in_inverse_memory()
    node2._record_in_inverse_memory()
    
    return child


mul_op = Operation('mul', _check_first_mul, _mul_first, _mul_next)

def mul(node1: AbstractNode, node2: AbstractNode) -> Node:
    """
    Element-wise product between two nodes. It can also be performed using the
    operator ``*``.

    Parameters
    ----------
    node1 : Node or ParamNode
        First node to be multiplied. Its edges will appear in the resultant node.
    node2 : Node or ParamNode
        Second node to be multiplied.

    Returns
    -------
    Node
    """
    return mul_op(node1, node2)


mul_node = copy_func(mul)
mul_node.__doc__ = \
    """
    Element-wise product between two nodes. It can also be performed using the
    operator ``*``.

    Parameters
    ----------
    node2 : Node or ParamNode
        Second node to be multiplied.

    Returns
    -------
    Node
    """

AbstractNode.__mul__ = mul_node


###################################   ADD    ##################################
def _check_first_add(node1: AbstractNode,
                     node2: AbstractNode) -> Optional[Successor]:
    kwargs = {'node1': node1,
              'node2': node2}
    if 'add' in node1._successors:
        for succ in node1._successors['add']:
            if succ.kwargs == kwargs:
                return succ
    return None


def _add_first(node1: AbstractNode, node2: AbstractNode) -> Node:
    if node1._network != node2._network:
        raise ValueError('Nodes must be in the same network')

    new_tensor = node1.tensor + node2.tensor
    new_node = Node(axes_names=node1.axes_names,
                    name='add',
                    network=node1._network,
                    leaf=False,
                    tensor=new_tensor,
                    edges=node1._edges,
                    node1_list=node1.is_node1())
    
    # Create successor
    net = node1._network
    successor = Successor(kwargs={'node1': node1,
                                  'node2': node2},
                          child=new_node)
    
    # Add successor to parent
    if 'add' in node1._successors:
        node1._successors['add'].append(successor)
    else:
        node1._successors['add'] = [successor]

    # Add operation to list of performed operations of TN
    net._seq_ops.append(('add', successor.kwargs))
    
    # Record in inverse_memory while tracing
    node1._record_in_inverse_memory()
    node2._record_in_inverse_memory()

    return new_node


def _add_next(successor: Successor,
              node1: AbstractNode,
              node2: AbstractNode) -> Node:
    new_tensor = node1.tensor + node2.tensor
    child = successor.child
    child._unrestricted_set_tensor_ops(new_tensor)
    
    # Record in inverse_memory while contracting
    # (to delete memory if possible)
    node1._record_in_inverse_memory()
    node2._record_in_inverse_memory()
    
    return child


add_op = Operation('add', _check_first_add, _add_first, _add_next)

def add(node1: AbstractNode, node2: AbstractNode) -> Node:
    """
    Element-wise addition between two nodes. It can also be performed using the
    operator ``+``.

    Parameters
    ----------
    node1 : Node or ParamNode
        First node to be added. Its edges will appear in the resultant node.
    node2 : Node or ParamNode
        Second node to be added.

    Returns
    -------
    Node
    """
    return add_op(node1, node2)


add_node = copy_func(add)
add_node.__doc__ = \
    """
    Element-wise addition between two nodes. It can also be performed using the
    operator ``+``.

    Parameters
    ----------
    node2 : Node or ParamNode
        Second node to be multiplied.

    Returns
    -------
    Node
    """

AbstractNode.__add__ = add_node


###################################   SUB    ##################################
def _check_first_sub(node1: AbstractNode,
                     node2: AbstractNode) -> Optional[Successor]:
    kwargs = {'node1': node1,
              'node2': node2}
    if 'sub' in node1._successors:
        for succ in node1._successors['sub']:
            if succ.kwargs == kwargs:
                return succ
    return None


def _sub_first(node1: AbstractNode, node2: AbstractNode) -> Node:
    if node1._network != node2._network:
        raise ValueError('Nodes must be in the same network')

    new_tensor = node1.tensor - node2.tensor
    new_node = Node(axes_names=node1.axes_names,
                    name='sub',
                    network=node1._network,
                    leaf=False,
                    tensor=new_tensor,
                    edges=node1._edges,
                    node1_list=node1.is_node1())
    
    # Create successor
    net = node1._network
    successor = Successor(kwargs={'node1': node1,
                                  'node2': node2},
                          child=new_node)
    
    # Add successor to parent
    if 'sub' in node1._successors:
        node1._successors['sub'].append(successor)
    else:
        node1._successors['sub'] = [successor]

    # Add operation to list of performed operations of TN
    net._seq_ops.append(('sub', successor.kwargs))
    
    # Record in inverse_memory while tracing
    node1._record_in_inverse_memory()
    node2._record_in_inverse_memory()

    return new_node


def _sub_next(successor: Successor,
              node1: AbstractNode,
              node2: AbstractNode) -> Node:
    new_tensor = node1.tensor - node2.tensor
    child = successor.child
    child._unrestricted_set_tensor_ops(new_tensor)
    
    # Record in inverse_memory while contracting
    # (to delete memory if possible)
    node1._record_in_inverse_memory()
    node2._record_in_inverse_memory()
    
    return child


sub_op = Operation('sub', _check_first_sub, _sub_first, _sub_next)

def sub(node1: AbstractNode, node2: AbstractNode) -> Node:
    """
    Element-wise subtraction between two nodes. It can also be performed using
    the operator ``-``.

    Parameters
    ----------
    node1 : Node or ParamNode
        First node, minuend . Its edges will appear in the resultant node.
    node2 : Node or ParamNode
        Second node, subtrahend.

    Returns
    -------
    Node
    """
    return sub_op(node1, node2)


sub_node = copy_func(sub)
sub_node.__doc__ = \
    """
    Element-wise subtraction between two nodes. It can also be performed using
    the operator ``-``.

    Parameters
    ----------
    node2 : Node or ParamNode
        Second node, subtrahend.

    Returns
    -------
    Node
    """

AbstractNode.__sub__ = sub_node


###############################################################################
#                            NODE-LIKE OPERATIONS                             #
###############################################################################

##################################   SPLIT    #################################
def _check_first_split(node: AbstractNode,
                       node1_axes: Sequence[Ax],
                       node2_axes: Sequence[Ax],
                       mode: Text = 'svd',
                       side: Optional[Text] = 'left',
                       rank: Optional[int] = None,
                       cum_percentage: Optional[float] = None,
                       cutoff: Optional[float] = None) -> Optional[Successor]:
    kwargs={'node': node,
            'node1_axes': node1_axes,
            'node2_axes': node2_axes,
            'mode': mode,
            'side': side,
            'rank': rank,
            'cum_percentage': cum_percentage,
            'cutoff': cutoff}
    if 'split' in node._successors:
        for succ in node._successors['split']:
            if succ.kwargs == kwargs:
                return succ
    return None


def _split_first(node: AbstractNode,
                 node1_axes: Sequence[Ax],
                 node2_axes: Sequence[Ax],
                 mode: Text = 'svd',
                 side: Optional[Text] = 'left',
                 rank: Optional[int] = None,
                 cum_percentage: Optional[float] = None,
                 cutoff: Optional[float] = None) -> Tuple[Node, Node]:
    if not isinstance(node1_axes, (list, tuple)):
        raise TypeError('`node1_edges` should be list or tuple type')
    if not isinstance(node2_axes, (list, tuple)):
        raise TypeError('`node2_edges` should be list or tuple type')
    
    kwargs = {'node': node,
              'node1_axes': node1_axes,
              'node2_axes': node2_axes,
              'mode': mode,
              'side': side,
              'rank': rank,
              'cum_percentage': cum_percentage,
              'cutoff': cutoff}
    
    node1_axes = [node.get_axis_num(axis) for axis in node1_axes]
    node2_axes = [node.get_axis_num(axis) for axis in node2_axes]
    
    batch_axes = []
    all_axes = node1_axes + node2_axes
    all_axes.sort()
    
    if all_axes:
        j = 0
        k = all_axes[0]
    else:
        k = node.rank
    for i in range(node.rank):
        if i < k:
            if not node._edges[i].is_batch():
                raise ValueError(f'Edge {node._edges[i]} is not a batch '
                                 'edge but it\'s not included in `node1_axes` '
                                 'neither in `node2_axes`')
            else:
                batch_axes.append(i)
        else:
            if (j + 1) == len(all_axes):
                k = node.rank
            else:
                j += 1
                k = all_axes[j]
    
    batch_shape = torch.tensor(node.shape)[batch_axes].tolist()
    node1_shape = torch.tensor(node.shape)[node1_axes]
    node2_shape = torch.tensor(node.shape)[node2_axes]
    
    permutation_dims = batch_axes + node1_axes + node2_axes
    if permutation_dims == list(range(node.rank)):
        permutation_dims = []
        
    if permutation_dims:
        node_tensor = node.tensor\
            .permute(*(batch_axes + node1_axes + node2_axes))\
            .reshape(*(batch_shape +
                       [node1_shape.prod().item()] +
                       [node2_shape.prod().item()]))
    else:
        node_tensor = node.tensor\
            .reshape(*(batch_shape +
                       [node1_shape.prod().item()] +
                       [node2_shape.prod().item()]))
        
    if (mode == 'svd') or (mode == 'svdr'):
        u, s, vh = torch.linalg.svd(node_tensor, full_matrices=False)

        if cum_percentage is not None:
            if (rank is not None) or (cutoff is not None):
                raise ValueError('Only one of `rank`, `cum_percentage` and '
                                 '`cutoff` should be provided')
                
            percentages = s.cumsum(-1) / s.sum(-1)\
                .view(*s.shape[:-1], 1).expand(s.shape)
            cum_percentage_tensor = torch.tensor(cum_percentage)\
                .repeat(percentages.shape[:-1])
            rank = 0
            for i in range(percentages.shape[-1]):
                p = percentages[..., i]
                rank += 1
                # Cut when ``cum_percentage`` is exceeded in all batches
                if torch.ge(p, cum_percentage_tensor).all():
                    break
                
        elif cutoff is not None:
            if rank is not None:
                raise ValueError('Only one of `rank`, `cum_percentage` and '
                                 '`cutoff` should be provided')
            
            cutoff_tensor = torch.tensor(cutoff).repeat(s.shape[:-1])
            rank = 0
            for i in range(s.shape[-1]):
                # Cut when ``cutoff`` is exceeded in all batches
                if torch.le(s[..., i], cutoff_tensor).all():
                    break
                rank += 1
            if rank == 0:
                rank = 1

        if rank is None:
            rank = s.shape[-1]
        else:
            if rank < s.shape[-1]:
                u = u[..., :rank]
                s = s[..., :rank]
                vh = vh[..., :rank, :]
            else:
                rank = s.shape[-1]
                
        if mode == 'svdr':
            phase = torch.sign(torch.randn(s.shape))
            phase = torch.diag_embed(phase)
            u = u @ phase
            vh = phase @ vh

        if side == 'left':
            u = u @ torch.diag_embed(s)
        elif side == 'right':
            vh = torch.diag_embed(s) @ vh
        else:
            raise ValueError('`side` can only be "left" or "right"')
        
        node1_tensor = u
        node2_tensor = vh
        
    elif mode == 'qr':
        q, r = torch.linalg.qr(node_tensor)
        rank = q.shape[-1]
        
        node1_tensor = q
        node2_tensor = r
        
    elif mode == 'rq':
        q, r = torch.linalg.qr(node_tensor.transpose(-1, -2))
        q = q.transpose(-1, -2)
        r = r.transpose(-1, -2)
        rank = r.shape[-1]
        
        node1_tensor = r
        node2_tensor = q
    
    else:
        raise ValueError('`mode` can only be "svd", "svdr", "qr" or "rq"')
    
    node1_tensor = node1_tensor.reshape(
        *(batch_shape + node1_shape.tolist() + [rank]))
    node2_tensor = node2_tensor.reshape(
        *(batch_shape + [rank] + node2_shape.tolist()))
    
    net = node._network
    
    node1_axes_names = permute_list(node.axes_names,
                                    batch_axes + node1_axes) + \
                       ['splitted']
    node1 = Node(axes_names=node1_axes_names,
                 name='split',
                 network=net,
                 leaf=False,
                 param_edges=node.param_edges(),
                 tensor=node1_tensor)
    
    node2_axes_names = permute_list(node.axes_names, batch_axes) + \
                       ['splitted'] + \
                       permute_list(node.axes_names, node2_axes)
    node2 = Node(axes_names=node2_axes_names,
                 name='split',
                 network=net,
                 leaf=False,
                 param_edges=node.param_edges(),
                 tensor=node2_tensor)
    
    n_batches = len(batch_axes)
    for edge in node1._edges[n_batches:-1]:
        net._remove_edge(edge)
    for edge in node2._edges[(n_batches + 1):]:
        net._remove_edge(edge)
    
    trace_node2_axes = []
    for i, axis1 in enumerate(node1_axes):
        edge1 = node._edges[axis1]
        
        in_node2 = False
        for j, axis2 in enumerate(node2_axes):
            edge2 = node._edges[axis2]
            if edge1 == edge2:
                in_node2 = True
                trace_node2_axes.append(axis2)
                
                node1_is_node1 = node.is_node1(axis1)
                if node1_is_node1:
                    new_edge = edge1.__class__(node1=node1,
                                               axis1=n_batches + i,
                                               node2=node2,
                                               axis2=n_batches + j + 1)
                else:
                    new_edge = edge1.__class__(node1=node2,
                                               axis1=n_batches + j + 1,
                                               node2=node1,
                                               axis2=n_batches + i)
                    
                node1._add_edge(edge=new_edge,
                                axis=n_batches + i,
                                node1=node1_is_node1)
                node2._add_edge(edge=new_edge,
                                axis=n_batches + j + 1,
                                node1=not node1_is_node1)
        
        if not in_node2:
            node1._add_edge(edge=edge1,
                            axis=n_batches + i,
                            node1=node.is_node1(axis1))
            
    for j, axis2 in enumerate(node2_axes):
        if axis2 not in trace_node2_axes:
            node2._add_edge(edge=node._edges[axis2],
                            axis=n_batches + j + 1,
                            node1=node.is_node1(axis2))
        
    splitted_edge = node1['splitted'] ^ node2['splitted']
    net._remove_edge(splitted_edge)
    
    # Create successor
    successor = Successor(kwargs=kwargs,
                          child=[node1, node2],
                          hints={'batch_axes': batch_axes,
                                 'node1_axes': node1_axes,
                                 'node2_axes': node2_axes,
                                 'permutation_dims': permutation_dims,
                                 'splitted_edge': splitted_edge})
    
    # Add successor to parent
    if 'split' in node._successors:
        node._successors['split'].append(successor)
    else:
        node._successors['split'] = [successor]

    # Add operation to list of performed operations of TN
    net._seq_ops.append(('split', successor.kwargs))
    
    # Record in inverse_memory while tracing
    node._record_in_inverse_memory()

    return node1, node2


def _split_next(successor: Successor,
                node: AbstractNode,
                node1_axes: Sequence[Ax],
                node2_axes: Sequence[Ax],
                mode: Text = 'svd',
                side: Optional[Text] = 'left',
                rank: Optional[int] = None,
                cum_percentage: Optional[float] = None,
                cutoff: Optional[float] = None) -> Tuple[Node, Node]:
    
    batch_axes = successor.hints['batch_axes']
    node1_axes = successor.hints['node1_axes']
    node2_axes = successor.hints['node2_axes']
    permutation_dims = successor.hints['permutation_dims']
    splitted_edge = successor.hints['splitted_edge']
    
    batch_shape = torch.tensor(node.shape)[batch_axes].tolist()
    node1_shape = torch.tensor(node.shape)[node1_axes]
    node2_shape = torch.tensor(node.shape)[node2_axes]
        
    if permutation_dims:
        node_tensor = node.tensor\
            .permute(*(batch_axes + node1_axes + node2_axes))\
            .reshape(*(batch_shape +
                       [node1_shape.prod().item()] +
                       [node2_shape.prod().item()]))
    else:
        node_tensor = node.tensor\
            .reshape(*(batch_shape +
                       [node1_shape.prod().item()] +
                       [node2_shape.prod().item()]))
            
    if (mode == 'svd') or (mode == 'svdr'):
        u, s, vh = torch.linalg.svd(node_tensor, full_matrices=False)

        if cum_percentage is not None:
            if (rank is not None) or (cutoff is not None):
                raise ValueError('Only one of `rank`, `cum_percentage` and '
                                 '`cutoff` should be provided')
                
            percentages = s.cumsum(-1) / s.sum(-1).view(*s.shape[:-1], 1).expand(s.shape)
            cum_percentage_tensor = torch.tensor(cum_percentage).repeat(percentages.shape[:-1])
            rank = 0
            for i in range(percentages.shape[-1]):
                p = percentages[..., i]
                rank += 1
                # Cut when ``cum_percentage`` is exceeded in all batches
                if torch.ge(p, cum_percentage_tensor).all():
                    break
                
        elif cutoff is not None:
            if rank is not None:
                raise ValueError('Only one of `rank`, `cum_percentage` and '
                                 '`cutoff` should be provided')
                
            cutoff_tensor = torch.tensor(cutoff).repeat(s.shape[:-1])
            rank = 0
            for i in range(s.shape[-1]):
                # Cut when ``cutoff`` is exceeded in all batches
                if torch.le(s[..., i], cutoff_tensor).all():
                    break
                rank += 1
            if rank == 0:
                rank = 1

        if rank is None:
            rank = s.shape[-1]
        else:
            if rank < s.shape[-1]:
                u = u[..., :rank]
                s = s[..., :rank]
                vh = vh[..., :rank, :]
            else:
                rank = s.shape[-1]
                
        if mode == 'svdr':
            phase = torch.sign(torch.randn(s.shape))
            phase = torch.diag_embed(phase)
            u = u @ phase
            vh = phase @ vh

        if side == 'left':
            u = u @ torch.diag_embed(s)
        elif side == 'right':
            vh = torch.diag_embed(s) @ vh
        else:
            raise ValueError('`side` can only be "left" or "right"')
        
        node1_tensor = u
        node2_tensor = vh
    
        splitted_edge._size = rank
        
    elif mode == 'qr':
        q, r = torch.linalg.qr(node_tensor)
        rank = q.shape[-1]
        
        node1_tensor = q
        node2_tensor = r
    
    elif mode == 'rq':
        q, r = torch.linalg.qr(node_tensor.transpose(-1, -2))
        q = q.transpose(-1, -2)
        r = r.transpose(-1, -2)
        rank = r.shape[-1]
        
        node1_tensor = r
        node2_tensor = q
    
    else:
        raise ValueError('`mode` can only be "svd", "svdr", "qr" or "rq"')
    
    node1_tensor = node1_tensor.reshape(
        *(batch_shape + node1_shape.tolist() + [rank]))
    node2_tensor = node2_tensor.reshape(
        *(batch_shape + [rank] + node2_shape.tolist()))
    
    children = successor.child
    children[0]._unrestricted_set_tensor_ops(node1_tensor)
    children[1]._unrestricted_set_tensor_ops(node2_tensor)
    
    # Record in inverse_memory while contracting
    # (to delete memory if possible)
    node._record_in_inverse_memory()
    
    return children[0], children[1]


split_op = Operation('split', _check_first_split, _split_first, _split_next)

def split(node: AbstractNode,
          node1_axes: Sequence[Ax],
          node2_axes: Sequence[Ax],
          mode: Text = 'svd',
          side: Optional[Text] = 'left',
          rank: Optional[int] = None,
          cum_percentage: Optional[float] = None,
          cutoff: Optional[float] = None) -> Tuple[Node, Node]:
    r"""
    Splits one node in two via the decomposition specified in ``mode``. To
    perform this operation the set of edges has to be split in two sets,
    corresponding to the edges of the first and second resultant nodes. Batch
    edges that don't appear in any of the lists will be repeated in both nodes.
    
    Having specified the two sets of edges, the node's tensor is reshaped as a
    batch matrix, with batch dimensions first, a single input dimension
    (adding up all edges in the first set) and a single output dimension
    (adding up all edges in the second set). With this shape, each matrix in
    the batch is decomposed according to ``mode``.
    
    * **"svd"**: Singular Value Decomposition
      
      .. math::

        M = USV^{\dagger}
        
      where :math:`U` and :math:`V` are unitary, and :math:`S` is diagonal.
    
    * **"svdr"**: Singular Value Decomposition adding a Random phases (square
      diagonal matrices with random 1's and -1's)
    
      .. math::
      
        M = UR_1SR_2V^{\dagger}
        
      where :math:`U` and :math:`V` are unitary, :math:`S` is diagonal, and
      :math:`R_1` and :math:`R_2` are square diagonal matrices with random 1's
      and -1's.
        
    * **"qr"**: QR decomposition
    
      .. math::
      
        M = QR
        
      where Q is unitary and R is an upper triangular matrix.
      
    * **"rq"**: RQ decomposition
    
      .. math::
      
        M = RQ
        
      where R is a lower triangular matrix and Q is unitary.
      
    If ``mode`` is "svd" or "svdr", ``side`` must be provided. Besides, one
    (and only one) of ``rank``, ``cum_percentage`` and ``cutoff`` is required.

    Parameters
    ----------
    node : AbstractNode
        Node that is to be splitted.
    node1_axes : list[int, str or Axis]
        First set of edges, will appear as the edges of the first (left)
        resultant node.
    node2_axes : list[int, str or Axis]
        Second set of edges, will appear as the edges of the second (right)
        resultant node.
    mode : {"svd", "svdr", "qr", "rq"}
        Decomposition to be used.
    side : str, optional
        If ``mode`` is "svd" or "svdr", indicates the side to which the diagonal
        matrix :math:`S` should be contracted. If "left", the first resultant
        node's tensor will be :math:`US`, and the other node's tensor will be
        :math:`V^{\dagger}`. If "right", their tensors will be :math:`U` and
        :math:`SV^{\dagger}`, respectively.
    rank : int, optional
        Number of singular values to keep.
    cum_percentage : float, optional
        Proportion that should be satisfied between the sum of all singular
        values kept and the total sum of all singular values.
        
        .. math::
        
            \frac{\sum_{i \in \{kept\}}{s_i}}{\sum_{i \in \{all\}}{s_i}} \ge
            cum\_percentage
    cutoff : float, optional
        Quantity that lower bounds singular values in order to be kept.

    Returns
    -------
    tuple[Node, Node]
    """
    return split_op(node, node1_axes, node2_axes,
                    mode, side, rank, cum_percentage, cutoff)


split_node = copy_func(split)
split_node.__doc__ = \
    r"""
    Splits one node in two via the decomposition specified in ``mode``. See
    :func:`split` for a more complete explanation.

    Parameters
    ----------
    node1_axes : list[int, str or Axis]
        First set of edges, will appear as the edges of the first (left)
        resultant node.
    node2_axes : list[int, str or Axis]
        Second set of edges, will appear as the edges of the second (right)
        resultant node.
    mode : {"svd", "svdr", "qr", "rq"}
        Decomposition to be used.
    side : str, optional
        If ``mode`` is "svd" or "svdr", indicates the side to which the diagonal
        matrix :math:`S` should be contracted. If "left", the first resultant
        node's tensor will be :math:`US`, and the other node's tensor will be
        :math:`V^{\dagger}`. If "right", their tensors will be :math:`U` and
        :math:`SV^{\dagger}`, respectively.
    rank : int, optional
        Number of singular values to keep.
    cum_percentage : float, optional
        Proportion that should be satisfied between the sum of all singular
        values kept and the total sum of all singular values.
        
        .. math::
        
            \frac{\sum_{i \in \{kept\}}{s_i}}{\sum_{i \in \{all\}}{s_i}} \ge
            cum\_percentage
    cutoff : float, optional
        Quantity that lower bounds singular values in order to be kept.

    Returns
    -------
    tuple[Node, Node]
    """

AbstractNode.split = split_node


def split_(node: AbstractNode,
           node1_axes: Sequence[Ax],
           node2_axes: Sequence[Ax],
           mode: Text = 'svd',
           side: Optional[Text] = 'left',
           rank: Optional[int] = None,
           cum_percentage: Optional[float] = None,
           cutoff: Optional[float] = None) -> Tuple[Node, Node]:
    r"""
    In-place version of :func:`split`.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    node : AbstractNode
        Node that is to be splitted.
    node1_axes : list[int, str or Axis]
        First set of edges, will appear as the edges of the first (left)
        resultant node.
    node2_axes : list[int, str or Axis]
        Second set of edges, will appear as the edges of the second (right)
        resultant node.
    mode : {"svd", "svdr", "qr", "rq"}
        Decomposition to be used.
    side : str, optional
        If ``mode`` is "svd" or "svdr", indicates the side to which the diagonal
        matrix :math:`S` should be contracted. If "left", the first resultant
        node's tensor will be :math:`US`, and the other node's tensor will be
        :math:`V^{\dagger}`. If "right", their tensors will be :math:`U` and
        :math:`SV^{\dagger}`, respectively.
    rank : int, optional
        Number of singular values to keep.
    cum_percentage : float, optional
        Proportion that should be satisfied between the sum of all singular
        values kept and the total sum of all singular values.
        
        .. math::
        
            \frac{\sum_{i \in \{kept\}}{s_i}}{\sum_{i \in \{all\}}{s_i}} \ge
            cum\_percentage
    cutoff : float, optional
        Quantity that lower bounds singular values in order to be kept.

    Returns
    -------
    tuple[Node, Node]
    """
    node1, node2 = split(node, node1_axes, node2_axes,
                         mode, side, rank, cum_percentage, cutoff)
    node1.reattach_edges(True)
    node2.reattach_edges(True)
    node1._unrestricted_set_tensor(node1.tensor.detach())
    node2._unrestricted_set_tensor(node2.tensor.detach())
    
    # Delete node (and its edges) from the TN
    net = node._network
    net.delete_node(node)
    
    # Add edges of result to the TN
    for res_edge in node1._edges + node2._edges:
        net._add_edge(res_edge)
    
    # Transform non-leaf to leaf nodes
    net._change_node_type(node1, 'leaf')
    net._change_node_type(node2, 'leaf')
    
    node._successors = dict()
    net._seq_ops = []
    
    # Remove non-leaf names
    node1.name = 'split_ip'
    node2.name = 'split_ip'
    
    return node1, node2


split_node_ = copy_func(split_)
split_node_.__doc__ = \
    r"""
    In-place version of :func:`~AbstractNode.split`.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    node1_axes : list[int, str or Axis]
        First set of edges, will appear as the edges of the first (left)
        resultant node.
    node2_axes : list[int, str or Axis]
        Second set of edges, will appear as the edges of the second (right)
        resultant node.
    mode : {"svd", "svdr", "qr", "rq"}
        Decomposition to be used.
    side : str, optional
        If ``mode`` is "svd" or "svdr", indicates the side to which the diagonal
        matrix :math:`S` should be contracted. If "left", the first resultant
        node's tensor will be :math:`US`, and the other node's tensor will be
        :math:`V^{\dagger}`. If "right", their tensors will be :math:`U` and
        :math:`SV^{\dagger}`, respectively.
    rank : int, optional
        Number of singular values to keep.
    cum_percentage : float, optional
        Proportion that should be satisfied between the sum of all singular
        values kept and the total sum of all singular values.
        
        .. math::
        
            \frac{\sum_{i \in \{kept\}}{s_i}}{\sum_{i \in \{all\}}{s_i}} \ge
            cum\_percentage
    cutoff : float, optional
        Quantity that lower bounds singular values in order to be kept.

    Returns
    -------
    tuple[Node, Node]
    """

AbstractNode.split_ = split_node_


def svd_(edge: AbstractEdge,
         side: Text = 'left',
         rank: Optional[int] = None,
         cum_percentage: Optional[float] = None,
         cutoff: Optional[float] = None) -> Tuple[Node, Node]:
    r"""
    Contracts an edge in-place via :func:`contract_` and splits it in-place via
    :func:`split_` using ``mode = "svd"``. See :func:`split` for a more complete
    explanation.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    edge : AbstractEdge
        Edge whose nodes are to be contracted and splitted.
    side : str, optional
        Indicates the side to which the diagonal matrix :math:`S` should be
        contracted. If "left", the first resultant node's tensor will be
        :math:`US`, and the other node's tensor will be :math:`V^{\dagger}`.
        If "right", their tensors will be :math:`U` and :math:`SV^{\dagger}`,
        respectively.
    rank : int, optional
        Number of singular values to keep.
    cum_percentage : float, optional
        Proportion that should be satisfied between the sum of all singular
        values kept and the total sum of all singular values.
        
        .. math::
        
            \frac{\sum_{i \in \{kept\}}{s_i}}{\sum_{i \in \{all\}}{s_i}} \ge
            cum\_percentage
    cutoff : float, optional
        Quantity that lower bounds singular values in order to be kept.

    Returns
    -------
    tuple[Node, Node]
    """
    if edge.is_dangling():
        raise ValueError('Edge should be connected to perform SVD')
    
    node1, node2 = edge.node1, edge.node2
    node1_name, node2_name = node1._name, node2._name
    axis1, axis2 = edge.axis1, edge.axis2
    
    batch_axes = []
    for axis in node1._axes:
        if axis.is_batch() and (axis._name in node2.axes_names):
            batch_axes.append(axis)
    
    n_batches = len(batch_axes)
    n_axes1 = len(node1._axes) - n_batches - 1
    n_axes2 = len(node2._axes) - n_batches - 1
    
    contracted = edge.contract_()
    new_node1, new_node2 = split_(node=contracted,
                                  node1_axes=list(
                                      range(n_batches,
                                            n_batches + n_axes1)),
                                  node2_axes=list(
                                      range(n_batches + n_axes1,
                                            n_batches + n_axes1 + n_axes2)),
                                  mode='svd',
                                  side=side,
                                  rank=rank,
                                  cum_percentage=cum_percentage,
                                  cutoff=cutoff)
    
    # new_node1
    prev_nums = [ax.num for ax in batch_axes]
    for i in range(new_node1.rank):
        if (i not in prev_nums) and (i != axis1._num):
            prev_nums.append(i)
    prev_nums += [axis1._num]
    
    if prev_nums != list(range(new_node1.rank)):
        permutation = inverse_permutation(prev_nums)
        new_node1 = new_node1.permute_(permutation)
        
    # new_node2 
    prev_nums = [node2.in_which_axis(node1[ax])._num for ax in batch_axes] + \
        [axis2._num]
    for i in range(new_node2.rank):
        if i not in prev_nums:
            prev_nums.append(i)
            
    if prev_nums != list(range(new_node2.rank)):
        permutation = inverse_permutation(prev_nums)
        new_node2 = new_node2.permute_(permutation)
    
    new_node1.name = node1_name
    new_node1.get_axis(axis1._num).name = axis1._name
    
    new_node2.name = node2_name
    new_node2.get_axis(axis2._num).name = axis2._name
    
    return new_node1, new_node2


svd_node_ = copy_func(svd_)
svd_node_.__doc__ = \
    r"""
    Contracts an edge in-place via :func:`~AbstractEdge.contract_` and splits
    it in-place via :func:`~AbstractNode.split_` using ``mode = "svd"``. See
    :func:`split` for a more complete explanation.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    side : str, optional
        Indicates the side to which the diagonal matrix :math:`S` should be
        contracted. If "left", the first resultant node's tensor will be
        :math:`US`, and the other node's tensor will be :math:`V^{\dagger}`.
        If "right", their tensors will be :math:`U` and :math:`SV^{\dagger}`,
        respectively.
    rank : int, optional
        Number of singular values to keep.
    cum_percentage : float, optional
        Proportion that should be satisfied between the sum of all singular
        values kept and the total sum of all singular values.
        
        .. math::
        
            \frac{\sum_{i \in \{kept\}}{s_i}}{\sum_{i \in \{all\}}{s_i}} \ge
            cum\_percentage
    cutoff : float, optional
        Quantity that lower bounds singular values in order to be kept.

    Returns
    -------
    tuple[Node, Node]
    """

AbstractEdge.svd_ = svd_node_


def svdr_(edge: AbstractEdge,
          side: Text = 'left',
          rank: Optional[int] = None,
          cum_percentage: Optional[float] = None,
          cutoff: Optional[float] = None) -> Tuple[Node, Node]:
    r"""
    Contracts an edge in-place via :func:`contract_` and splits it in-place via
    :func:`split_` using ``mode = "svdr"``. See :func:`split` for a more complete
    explanation.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    edge : AbstractEdge
        Edge whose nodes are to be contracted and splitted.
    side : str, optional
        Indicates the side to which the diagonal matrix :math:`S` should be
        contracted. If "left", the first resultant node's tensor will be
        :math:`US`, and the other node's tensor will be :math:`V^{\dagger}`.
        If "right", their tensors will be :math:`U` and :math:`SV^{\dagger}`,
        respectively.
    rank : int, optional
        Number of singular values to keep.
    cum_percentage : float, optional
        Proportion that should be satisfied between the sum of all singular
        values kept and the total sum of all singular values.
        
        .. math::
        
            \frac{\sum_{i \in \{kept\}}{s_i}}{\sum_{i \in \{all\}}{s_i}} \ge
            cum\_percentage
    cutoff : float, optional
        Quantity that lower bounds singular values in order to be kept.

    Returns
    -------
    tuple[Node, Node]
    """
    if edge.is_dangling():
        raise ValueError('Edge should be connected to perform SVD')
    
    node1, node2 = edge.node1, edge.node2
    node1_name, node2_name = node1._name, node2._name
    axis1, axis2 = edge.axis1, edge.axis2
    
    batch_axes = []
    for axis in node1._axes:
        if axis.is_batch() and (axis._name in node2.axes_names):
            batch_axes.append(axis)
    
    n_batches = len(batch_axes)
    n_axes1 = len(node1._axes) - n_batches - 1
    n_axes2 = len(node2._axes) - n_batches - 1
    
    contracted = edge.contract_()
    new_node1, new_node2 = split_(node=contracted,
                                  node1_axes=list(
                                      range(n_batches,
                                            n_batches + n_axes1)),
                                  node2_axes=list(
                                      range(n_batches + n_axes1,
                                            n_batches + n_axes1 + n_axes2)),
                                  mode='svdr',
                                  side=side,
                                  rank=rank,
                                  cum_percentage=cum_percentage,
                                  cutoff=cutoff)
    
    # new_node1
    prev_nums = [ax._num for ax in batch_axes]
    for i in range(new_node1.rank):
        if (i not in prev_nums) and (i != axis1._num):
            prev_nums.append(i)
    prev_nums += [axis1._num]
    
    if prev_nums != list(range(new_node1.rank)):
        permutation = inverse_permutation(prev_nums)
        new_node1 = new_node1.permute_(permutation)
        
    # new_node2 
    prev_nums = [node2.in_which_axis(node1[ax])._num for ax in batch_axes] + \
        [axis2._num]
    for i in range(new_node2.rank):
        if i not in prev_nums:
            prev_nums.append(i)
            
    if prev_nums != list(range(new_node2.rank)):
        permutation = inverse_permutation(prev_nums)
        new_node2 = new_node2.permute_(permutation)
    
    new_node1.name = node1_name
    new_node1.get_axis(axis1._num).name = axis1._name
    
    new_node2.name = node2_name
    new_node2.get_axis(axis2._num).name = axis2._name
    
    return new_node1, new_node2


svdr_node_ = copy_func(svdr_)
svdr_node_.__doc__ = \
    r"""
    Contracts an edge in-place via :func:`~AbstractEdge.contract_` and splits
    it in-place via :func:`~AbstractNode.split_` using ``mode = "svdr"``. See
    :func:`split` for a more complete explanation.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    side : str, optional
        Indicates the side to which the diagonal matrix :math:`S` should be
        contracted. If "left", the first resultant node's tensor will be
        :math:`US`, and the other node's tensor will be :math:`V^{\dagger}`.
        If "right", their tensors will be :math:`U` and :math:`SV^{\dagger}`,
        respectively.
    rank : int, optional
        Number of singular values to keep.
    cum_percentage : float, optional
        Proportion that should be satisfied between the sum of all singular
        values kept and the total sum of all singular values.
        
        .. math::
        
            \frac{\sum_{i \in \{kept\}}{s_i}}{\sum_{i \in \{all\}}{s_i}} \ge
            cum\_percentage
    cutoff : float, optional
        Quantity that lower bounds singular values in order to be kept.

    Returns
    -------
    tuple[Node, Node]
    """

AbstractEdge.svdr_ = svdr_node_


def qr_(edge) -> Tuple[Node, Node]:
    r"""
    Contracts an edge in-place via :func:`contract_` and splits it in-place via
    :func:`split_` using ``mode = "qr"``. See :func:`split` for a more complete
    explanation.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    edge : AbstractEdge
        Edge whose nodes are to be contracted and splitted.

    Returns
    -------
    tuple[Node, Node]
    """
    if edge.is_dangling():
        raise ValueError('Edge should be connected to perform SVD')
    
    node1, node2 = edge.node1, edge.node2
    node1_name, node2_name = node1._name, node2._name
    axis1, axis2 = edge.axis1, edge.axis2
    
    batch_axes = []
    for axis in node1._axes:
        if axis.is_batch() and (axis._name in node2.axes_names):
            batch_axes.append(axis)
    
    n_batches = len(batch_axes)
    n_axes1 = len(node1._axes) - n_batches - 1
    n_axes2 = len(node2._axes) - n_batches - 1
    
    contracted = edge.contract_()
    new_node1, new_node2 = split_(node=contracted,
                                  node1_axes=list(
                                      range(n_batches,
                                            n_batches + n_axes1)),
                                  node2_axes=list(
                                      range(n_batches + n_axes1,
                                            n_batches + n_axes1 + n_axes2)),
                                  mode='qr')
    
    # new_node1
    prev_nums = [ax._num for ax in batch_axes]
    for i in range(new_node1.rank):
        if (i not in prev_nums) and (i != axis1._num):
            prev_nums.append(i)
    prev_nums += [axis1._num]
    
    if prev_nums != list(range(new_node1.rank)):
        permutation = inverse_permutation(prev_nums)
        new_node1 = new_node1.permute_(permutation)
        
    # new_node2 
    prev_nums = [node2.in_which_axis(node1[ax])._num for ax in batch_axes] + \
        [axis2._num]
    for i in range(new_node2.rank):
        if i not in prev_nums:
            prev_nums.append(i)
            
    if prev_nums != list(range(new_node2.rank)):
        permutation = inverse_permutation(prev_nums)
        new_node2 = new_node2.permute_(permutation)
    
    new_node1.name = node1_name
    new_node1.get_axis(axis1._num).name = axis1._name
    
    new_node2.name = node2_name
    new_node2.get_axis(axis2._num).name = axis2._name
    
    return new_node1, new_node2


qr_node_ = copy_func(qr_)
qr_node_.__doc__ = \
    r"""
    Contracts an edge in-place via :func:`~AbstractEdge.contract_` and splits
    it in-place via :func:`~AbstractNode.split_` using ``mode = "qr"``. See
    :func:`split` for a more complete explanation.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Returns
    -------
    tuple[Node, Node]
    """

AbstractEdge.qr_ = qr_node_


def rq_(edge) -> Tuple[Node, Node]:
    r"""
    Contracts an edge in-place via :func:`contract_` and splits it in-place via
    :func:`split_` using ``mode = "rq"``. See :func:`split` for a more complete
    explanation.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    edge : AbstractEdge
        Edge whose nodes are to be contracted and splitted.

    Returns
    -------
    tuple[Node, Node]
    """
    if edge.is_dangling():
        raise ValueError('Edge should be connected to perform SVD')
    
    node1, node2 = edge.node1, edge.node2
    node1_name, node2_name = node1._name, node2._name
    axis1, axis2 = edge.axis1, edge.axis2
    
    batch_axes = []
    for axis in node1._axes:
        if axis.is_batch() and (axis._name in node2.axes_names):
            batch_axes.append(axis)
    
    n_batches = len(batch_axes)
    n_axes1 = len(node1._axes) - n_batches - 1
    n_axes2 = len(node2._axes) - n_batches - 1
    
    contracted = edge.contract_()
    new_node1, new_node2 = split_(node=contracted,
                                  node1_axes=list(
                                      range(n_batches,
                                            n_batches + n_axes1)),
                                  node2_axes=list(
                                      range(n_batches + n_axes1,
                                            n_batches + n_axes1 + n_axes2)),
                                  mode='rq')
    
    # new_node1
    prev_nums = [ax._num for ax in batch_axes]
    for i in range(new_node1.rank):
        if (i not in prev_nums) and (i != axis1._num):
            prev_nums.append(i)
    prev_nums += [axis1._num]
    
    if prev_nums != list(range(new_node1.rank)):
        permutation = inverse_permutation(prev_nums)
        new_node1 = new_node1.permute_(permutation)
        
    # new_node2 
    prev_nums = [node2.in_which_axis(node1[ax])._num for ax in batch_axes] + \
        [axis2._num]
    for i in range(new_node2.rank):
        if i not in prev_nums:
            prev_nums.append(i)
            
    if prev_nums != list(range(new_node2.rank)):
        permutation = inverse_permutation(prev_nums)
        new_node2 = new_node2.permute_(permutation)
    
    new_node1.name = node1_name
    new_node1.get_axis(axis1._num).name = axis1._name
    
    new_node2.name = node2_name
    new_node2.get_axis(axis2._num).name = axis2._name
    
    return new_node1, new_node2


rq_node_ = copy_func(rq_)
rq_node_.__doc__ = \
    r"""
    Contracts an edge in-place via :func:`~AbstractEdge.contract_` and splits
    it in-place via :func:`~AbstractNode.split_` using ``mode = "qr"``. See
    :func:`split` for a more complete explanation.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.
    
    Returns
    -------
    tuple[Node, Node]
    """

AbstractEdge.rq_ = rq_node_


################################   CONTRACT    ################################
def _check_first_contract_edges(edges: List[AbstractEdge],
                                node1: AbstractNode,
                                node2: AbstractNode) -> Optional[Successor]:
    kwargs = {'edges': edges,
              'node1': node1,
              'node2': node2}
    if 'contract_edges' in node1._successors:
        for succ in node1._successors['contract_edges']:
            if succ.kwargs == kwargs:
                return succ
    return None


def _contract_edges_first(edges: List[AbstractEdge],
                          node1: AbstractNode,
                          node2: AbstractNode) -> Node:
    shared_edges = get_shared_edges(node1, node2)
    if shared_edges == []:
        raise ValueError(f'No batch edges or shared edges between nodes '
                         f'{node1!s} and {node2!s} found')
    
    edges_None = False
    if edges is None:
        edges = shared_edges
        edges_None = True
    else:
        for edge in edges:
            if edge not in shared_edges:
                raise ValueError('Edges selected to be contracted must be '
                                 'shared edges between `node1` and `node2`')

    # Trace
    if node1 == node2:
        result = node1.tensor
        for j, edge in enumerate(node1._edges):
            if edge in edges:
                if isinstance(edge, ParamEdge):
                    # Obtain permutations
                    permutation_dims = [k if k < j else k + 1
                                        for k in range(node1.rank - 1)] + [j]
                    inv_permutation_dims = inverse_permutation(permutation_dims)

                    # Send multiplication dimension to the end, multiply,
                    # and recover original shape
                    result = result.permute(permutation_dims)
                    if isinstance(edge, ParamStackEdge):
                        mat = edge.matrix
                        result = result @ mat.view(
                            mat.shape[0],  # First dim is stack
                            *[1]*(len(result.shape) - 3),
                            *mat.shape[1:])
                    else:
                        result = result @ edge.matrix
                    result = result.permute(inv_permutation_dims)

        axes_nums = dict(zip(range(node1.rank), range(node1.rank)))
        for edge in edges:
            axes = node1.in_which_axis(edge)
            result = torch.diagonal(result,
                                    offset=0,
                                    dim1=axes_nums[axes[0]._num],
                                    dim2=axes_nums[axes[1]._num])
            result = result.sum(-1)
            min_axis = min(axes[0]._num, axes[1]._num)
            max_axis = max(axes[0]._num, axes[1]._num)
            for num in axes_nums:
                if num < min_axis:
                    continue
                elif num == min_axis:
                    axes_nums[num] = -1
                elif (num > min_axis) and (num < max_axis):
                    axes_nums[num] -= 1
                elif num == max_axis:
                    axes_nums[num] = -1
                elif num > max_axis:
                    axes_nums[num] -= 2

        new_axes_names = []
        new_edges = []
        new_node1_list = []
        for num in axes_nums:
            if axes_nums[num] >= 0:
                new_axes_names.append(node1._axes[num]._name)
                new_edges.append(node1._edges[num])
                new_node1_list.append(node1.is_node1(num))

        hints = {'edges': edges}
        
        # Record in inverse_memory while tracing
        node1._record_in_inverse_memory()

    else:
        nodes = [node1, node2]
        tensors = [node1.tensor, node2.tensor]
        non_contract_edges = [dict(), dict()]
        batch_edges = dict()
        contract_edges = dict()

        for i in [0, 1]:
            for j, axis in enumerate(nodes[i]._axes):
                edge = nodes[i]._edges[j]
                if edge in edges:
                    if i == 0:
                        if isinstance(edge, ParamEdge):
                            # Obtain permutations
                            permutation_dims = [k if k < j else k + 1
                                                for k in range(
                                                    nodes[i].rank - 1)] + [j]
                            inv_permutation_dims = inverse_permutation(
                                permutation_dims)

                            # Send multiplication dimension to the end,
                            # multiply, and recover original shape
                            tensors[i] = tensors[i].permute(permutation_dims)
                            if isinstance(edge, ParamStackEdge):
                                mat = edge.matrix
                                tensors[i] = tensors[i] @ mat.view(
                                    mat.shape[0],  # First dim is stack,
                                    *[1]*(len(tensors[i].shape) - 3),
                                    *mat.shape[1:])
                            else:
                                tensors[i] = tensors[i] @ edge.matrix
                            tensors[i] = tensors[i].permute(inv_permutation_dims)

                        contract_edges[edge] = []
                        
                    contract_edges[edge].append(j)

                elif axis.is_batch():
                    if i == 0:
                        batch_in_node2 = False
                        for aux_axis in nodes[1]._axes:
                            if aux_axis.is_batch() and \
                                (axis._name == aux_axis._name):
                                batch_edges[axis._name] = [j]
                                batch_in_node2 = True
                                break
                        if not batch_in_node2:
                            non_contract_edges[i][axis._name] = j
                    else:
                        if axis._name in batch_edges:
                            batch_edges[axis._name].append(j)
                        else:
                            non_contract_edges[i][axis._name] = j
                else:
                    non_contract_edges[i][axis._name] = j

        permutation_dims = [None, None]
        
        batch_edges_perm_0 = list(map(lambda l: l[0], batch_edges.values()))
        batch_edges_perm_1 = list(map(lambda l: l[1], batch_edges.values()))
        
        non_contract_edges_perm_0 = list(non_contract_edges[0].values())
        non_contract_edges_perm_1 = list(non_contract_edges[1].values())
        
        contract_edges_perm_0 = list(map(lambda l: l[0], contract_edges.values()))
        contract_edges_perm_1 = list(map(lambda l: l[1], contract_edges.values()))
        
        permutation_dims[0] = batch_edges_perm_0 + \
            non_contract_edges_perm_0 + contract_edges_perm_0
        permutation_dims[1] = batch_edges_perm_1 + \
            contract_edges_perm_1 + non_contract_edges_perm_1
            
        for i in [0, 1]:
            if permutation_dims[i] == list(range(len(permutation_dims[i]))):
                permutation_dims[i] = []
                
        shape_limits = (len(batch_edges),
                        len(non_contract_edges[0]),
                        len(contract_edges))
        
        result = _C.contract(tensors[0], tensors[1],
                             permutation_dims,
                             shape_limits)
            
        # Put batch dims at the beggining
        indices = [None, None]
        indices[0] = list(map(lambda l: l[0], batch_edges.values())) + \
            list(non_contract_edges[0].values())
        indices[1] = list(non_contract_edges[1].values())

        new_axes_names = []
        new_edges = []
        new_node1_list = []
        for i in [0, 1]:
            for idx in indices[i]:
                new_axes_names.append(nodes[i].axes_names[idx])
                new_edges.append(nodes[i][idx])
                new_node1_list.append(nodes[i].axes[idx].is_node1())

        hints = {'permutation_dims': permutation_dims,
                 'shape_limits': shape_limits,
                 'edges': edges}
        
        # Record in inverse_memory while tracing
        node1._record_in_inverse_memory()
        node2._record_in_inverse_memory()
    
        
    node1_is_stack = isinstance(node1, (StackNode, ParamStackNode))
    node2_is_stack = isinstance(node2, (StackNode, ParamStackNode))
    if node1_is_stack and node2_is_stack:
            new_node = StackNode(axes_names=new_axes_names,
                                 name='contract_edges',
                                 network=node1._network,
                                 tensor=result,
                                 edges=new_edges,
                                 node1_list=new_node1_list)
    elif node1_is_stack or node2_is_stack:
        raise TypeError('Can only contract (Param)StackNode with other '
                        '(Param)StackNode')
    else:
        new_node = Node(axes_names=new_axes_names,
                        name='contract_edges',
                        network=node1._network,
                        leaf=False,
                        param_edges=False,
                        tensor=result,
                        edges=new_edges,
                        node1_list=new_node1_list)

    # Create successor
    net = node1._network
    successor = Successor(kwargs={'edges': edges if not edges_None else None,
                                  'node1': node1,
                                  'node2': node2},
                             child=new_node,
                             hints=hints)
    
    # Add successor to parent
    if 'contract_edges' in node1._successors:
        node1._successors['contract_edges'].append(successor)
    else:
        node1._successors['contract_edges'] = [successor]

    # Add operation to list of performed operations of TN
    net._seq_ops.append(('contract_edges', successor.kwargs))

    return new_node


def _contract_edges_next(successor: Successor,
                         edges: List[AbstractEdge],
                         node1: AbstractNode,
                         node2: AbstractNode) -> Node:
    hints = successor.hints
    edges = hints['edges']
    
    if node1 == node2:
        result = node1.tensor
        for j, edge in enumerate(node1._edges):
            if edge in edges:
                if isinstance(edge, ParamEdge):
                    # Obtain permutations
                    permutation_dims = [k if k < j else k + 1
                                        for k in range(node1.rank - 1)] + [j]
                    inv_permutation_dims = inverse_permutation(permutation_dims)

                    # Send multiplication dimension to the end, multiply,
                    # and recover original shape
                    result = result.permute(permutation_dims)
                    if isinstance(edge, ParamStackEdge):
                        mat = edge.matrix
                        result = result @ mat.view(
                            mat.shape[0],  # First dim is stack
                            *[1]*(len(result.shape) - 3),
                            *mat.shape[1:])
                    else:
                        result = result @ edge.matrix
                    result = result.permute(inv_permutation_dims)

        axes_nums = dict(zip(range(node1.rank), range(node1.rank)))
        for edge in edges:
            axes = node1.in_which_axis(edge)
            result = torch.diagonal(result,
                                    offset=0,
                                    dim1=axes_nums[axes[0]._num],
                                    dim2=axes_nums[axes[1]._num])
            result = result.sum(-1)
            min_axis = min(axes[0]._num, axes[1]._num)
            max_axis = max(axes[0]._num, axes[1]._num)
            for num in axes_nums:
                if num < min_axis:
                    continue
                elif num == min_axis:
                    axes_nums[num] = -1
                elif (num > min_axis) and (num < max_axis):
                    axes_nums[num] -= 1
                elif num == max_axis:
                    axes_nums[num] = -1
                elif num > max_axis:
                    axes_nums[num] -= 2
        
        # Record in inverse_memory while contracting
        # (to delete memory if possible)
        node1._record_in_inverse_memory()

    else:
        nodes = [node1, node2]
        tensors = [node1.tensor, node2.tensor]

        for j, edge in enumerate(nodes[0]._edges):
            if edge in edges:
                if isinstance(edge, ParamEdge):
                    # Obtain permutations
                    permutation_dims = [k if k < j else k + 1
                                        for k in range(nodes[0].rank - 1)] + [j]
                    inv_permutation_dims = inverse_permutation(permutation_dims)
                   # Send multiplication dimension to the end, multiply,
                    # and recover original shape
                    tensors[0] = tensors[0].permute(permutation_dims)
                    if isinstance(edge, ParamStackEdge):
                        mat = edge.matrix
                        tensors[0] = tensors[0] @ mat.view(
                            mat.shape[0],  # First dim is stack
                            *[1]*(len(tensors[0].shape) - 3),
                            *mat.shape[1:])
                    else:
                        tensors[0] = tensors[0] @ edge.matrix
                    tensors[0] = tensors[0].permute(inv_permutation_dims)
                    
        result = _C.contract(tensors[0], tensors[1],
                             hints['permutation_dims'],
                             hints['shape_limits'])
        
        # Record in inverse_memory while contracting
        # (to delete memory if possible)
        node1._record_in_inverse_memory()
        node2._record_in_inverse_memory()
        
    child = successor.child
    child._unrestricted_set_tensor_ops(result)
    
    return child


contract_edges_op = Operation('contract_edges',
                              _check_first_contract_edges,
                              _contract_edges_first,
                              _contract_edges_next)

def contract_edges(edges: List[AbstractEdge],
                   node1: AbstractNode,
                   node2: AbstractNode) -> Node:
    """
    Contracts all selected edges between two nodes.

    Parameters
    ----------
    edges : list[AbstractEdge]
        List of edges that are to be contracted. They must be edges shared
        between ``node1`` and ``node2``. Batch contraction is automatically
        performed when both nodes have batch edges with the same names.
    node1 : AbstractNode
        First node of the contraction. Its non-contracted edges will appear
        first in the list of inherited edges of the resultant node.
    node2 : AbstractNode
        Second node of the contraction. Its non-contracted edges will appear
        last in the list of inherited edges of the resultant node.

    Returns
    -------
    Node
    """
    return contract_edges_op(edges, node1, node2)


def contract_(edge: AbstractEdge) -> Node:
    """
    Contracts in-place the nodes that are connected through the edge. See
    :func:`contract` for a more complete explanation.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    edge : AbstractEdge
        Edges that is to be contracted. Batch contraction is automatically
        performed when both nodes have batch edges with the same names.

    Returns
    -------
    Node
    """
    result = contract_edges([edge], edge.node1, edge.node2)
    result.reattach_edges(True)
    result._unrestricted_set_tensor(result.tensor.detach())
    
    # Delete nodes (and their edges) from the TN
    net = result.network
    net.delete_node(edge.node1)
    net.delete_node(edge.node2)
    
    # Add edges of result to the TN
    for res_edge in result._edges:
        net._add_edge(res_edge)
    
    # Transform non-leaf to leaf nodes
    net._change_node_type(result, 'leaf')
    
    edge.node1._successors = dict()
    edge.node2._successors = dict()
    net._seq_ops = []
    
    # Remove non-leaf name
    result.name = 'contract_edges_ip'
    
    return result

AbstractEdge.contract_ = contract_


def get_shared_edges(node1: AbstractNode,
                     node2: AbstractNode) -> List[AbstractEdge]:
    """
    Returns list of edges shared between two nodes
    """
    edges = set()
    for i1, edge1 in enumerate(node1._edges):
        for i2, edge2 in enumerate(node2._edges):
            if (edge1 == edge2) and not edge1.is_dangling():
                if node1.is_node1(i1) != node2.is_node1(i2):
                    edges.add(edge1)
    
    return list(edges)


def contract_between(node1: AbstractNode,
                     node2: AbstractNode) -> Node:
    """
    Contracts all edges shared between two nodes. Batch contraction is
    automatically performed when both nodes have batch edges with the same
    names.

    Parameters
    ----------
    node1 : AbstractNode
        First node of the contraction. Its non-contracted edges will appear
        first in the list of inherited edges of the resultant node.
    node2 : AbstractNode
        Second node of the contraction. Its non-contracted edges will appear
        last in the list of inherited edges of the resultant node.

    Returns
    -------
    Node
    """
    return contract_edges(None, node1, node2)


contract_between_node = copy_func(contract_between)
contract_between_node.__doc__ = \
    """
    Contracts all edges shared between two nodes. Batch contraction is
    automatically performed when both nodes have batch edges with the same
    names. It can also be performed using the operator ``@``.

    Parameters
    ----------
    node2 : AbstractNode
        Second node of the contraction. Its non-contracted edges will appear
        last in the list of inherited edges of the resultant node.

    Returns
    -------
    Node
    """

AbstractNode.__matmul__ = contract_between_node
AbstractNode.contract_between = contract_between_node


def contract_between_(node1: AbstractNode,
                      node2: AbstractNode) -> Node:
    """
    In-place version of :func:`contract_between`.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    node1 : AbstractNode
        First node of the contraction. Its non-contracted edges will appear
        first in the list of inherited edges of the resultant node.
    node2 : AbstractNode
        Second node of the contraction. Its non-contracted edges will appear
        last in the list of inherited edges of the resultant node.

    Returns
    -------
    Node
    """
    result = contract_between(node1, node2)
    result.reattach_edges(True)
    result._unrestricted_set_tensor(result.tensor.detach())
    
    # Delete nodes (and their edges) from the TN
    net = result.network
    net.delete_node(node1)
    net.delete_node(node2)
    
    # Add edges of result to the TN
    for res_edge in result._edges:
        net._add_edge(res_edge)
    
    # Transform non-leaf to leaf nodes
    net._change_node_type(result, 'leaf')
    
    node1._successors = dict()
    node2._successors = dict()
    net._seq_ops = []
    
    # Remove non-leaf name
    result.name = 'contract_edges_ip'
    
    return result

contract_between_node_ = copy_func(contract_between_)
contract_between_node_.__doc__ = \
    """
    In-place version of :func:`~AbstractNode.contract_between`.
    
    Following the **PyTorch** convention, names of functions ended with an
    underscore indicate **in-place** operations.

    Parameters
    ----------
    node2 : AbstractNode
        Second node of the contraction. Its non-contracted edges will appear
        last in the list of inherited edges of the resultant node.

    Returns
    -------
    Node
    """

AbstractNode.contract_between_ = contract_between_node_


#####################################   STACK   ###############################
def _check_first_stack(nodes: Sequence[AbstractNode]) -> Optional[Successor]:
    kwargs = {'nodes': nodes}
    
    if not nodes:
        raise ValueError('`nodes` should be a non-empty sequence of nodes')
    
    if 'stack' in nodes[0]._successors:
        for succ in nodes[0]._successors['stack']:
            if succ.kwargs == kwargs:
                return succ
    return None


def _stack_first(nodes: Sequence[AbstractNode]) -> StackNode:
    all_leaf = True          # Check if all the nodes are leaf
    all_non_param = True     # Check if all the nodes are non-parametric
    all_param = True         # Check if all the nodes are parametric
    all_same_ref = True      # Check if all the nodes' memories are stored in the
                             # same reference node's memory
    node_ref_is_stack = True # Chech if the shared reference node is a stack
    stack_node_ref = None    # In the case above, the reference node
    stack_indices = []       # In the case above, stack indices of each node in
                             # the reference node's memory
    
    if not isinstance(nodes, (list, tuple)):
        raise TypeError('`nodes` should be a list or tuple of nodes')
    
    net = nodes[0]._network
    for node in nodes:
        if not node._leaf:
            all_leaf = False

        if isinstance(node, ParamNode):
            all_non_param = False
        else:
            all_param = False
        
        if all_same_ref:
            if node._tensor_info['address'] is None:
                node_ref = node._tensor_info['node_ref']
                
                if stack_node_ref is None:
                    stack_node_ref = node_ref
                else:
                    if node_ref != stack_node_ref:
                        all_same_ref = False
                        continue
                        
                if not isinstance(node_ref, (StackNode, ParamStackNode)):
                    all_same_ref = False
                    node_ref_is_stack = False
                    continue

                stack_indices.append(node._tensor_info['index'][0])
                
            else:
                all_same_ref = False

    if all_param and node_ref_is_stack and net._automemory:
        stack_node = ParamStackNode(nodes=nodes,
                                    name='virtual_stack',
                                    virtual=True)
    else:
        stack_node = StackNode(nodes=nodes,
                               name='stack')

    # Both conditions can only be satisfied in index_mode
    if all_same_ref:
        # Memory of stack is just a reference to the stack_node_ref
        stack_indices = list2slice(stack_indices)
        
        del net._memory_nodes[stack_node._tensor_info['address']]
        stack_node._tensor_info['address'] = None
        stack_node._tensor_info['node_ref'] = stack_node_ref
        stack_node._tensor_info['full'] = False
        
        index = [stack_indices]
        if stack_node_ref.shape[1:] != stack_node.shape[1:]:
            for i, (max_dim, dim) in enumerate(zip(stack_node_ref._shape[1:],
                                                   stack_node._shape[1:])):
                if stack_node._axes[i + 1].is_batch():
                    # Admit any size in batch edges
                    index.append(slice(0, None))
                else:
                    index.append(slice(max_dim - dim, max_dim))
        stack_node._tensor_info['index'] = index

    else:
        if all_leaf and (all_param or all_non_param) \
            and node_ref_is_stack and net._automemory:
            # Stacked nodes' memories are replaced by a reference to a slice
            # of the resultant stack_node
            for i, node in enumerate(nodes):
                if node._tensor_info['address'] is not None:
                    del net._memory_nodes[node._tensor_info['address']]
                node._tensor_info['address'] = None
                node._tensor_info['node_ref'] = stack_node
                node._tensor_info['full'] = False
                index = [i]
                for j, (max_dim, dim) in enumerate(zip(stack_node._shape[1:],
                                                    node._shape)):
                    if node._axes[j].is_batch():
                        # Admit any size in batch edges
                        index.append(slice(0, None))
                    else:
                        index.append(slice(max_dim - dim, max_dim))
                node._tensor_info['index'] = index

                if all_param:
                    delattr(net, 'param_' + node._name)
                    
        # Record in inverse_memory while tracing
        for node in nodes:
            node._record_in_inverse_memory()

    # Create successor
    successor = Successor(kwargs={'nodes': nodes},
                          child=stack_node,
                          hints={'all_same_ref': all_same_ref,
                                 'all_leaf': all_leaf and 
                                    (all_param or all_non_param) and 
                                    node_ref_is_stack,
                                 'automemory': net._automemory})
    
    # Add successor to parent
    if 'stack' in nodes[0]._successors:
        nodes[0]._successors['stack'].append(successor)
    else:
        nodes[0]._successors['stack'] = [successor]

    # Add operation to list of performed operations of TN
    net._seq_ops.append(('stack', successor.kwargs))

    return stack_node


def _stack_next(successor: Successor,
                nodes: Sequence[AbstractNode]) -> StackNode:
    child = successor.child
    if successor.hints['all_same_ref'] or \
        (successor.hints['all_leaf'] and successor.hints['automemory']):
        return child

    stack_tensor = stack_unequal_tensors([node.tensor for node in nodes])
    child._unrestricted_set_tensor_ops(stack_tensor)
            
    # Record in inverse_memory while contracting
    # (to delete memory if possible)
    for node in nodes:
        node._record_in_inverse_memory()

    return child


stack_op = Operation('stack', _check_first_stack, _stack_first, _stack_next)

def stack(nodes: Sequence[AbstractNode]):
    """
    Creates a StackNode or ParamStackNode by stacking a collection of Nodes or
    ParamNodes, respectively. Restrictions that are applied to the nodes in
    order to be `stackable` are the same as in :class:`StackNode`.
    
    The stack dimension will be the first one in the resultant node.
    
    Parameters
    ----------
    nodes : list[AbstractNode] or tuple[AbstractNode]
        Sequence of nodes that are to be stacked. They must be of the same type,
        have the same rank and axes names, be in the same tensor network, and
        have edges with the same types.
    """
    return stack_op(nodes)


##################################   UNBIND   #################################
def _check_first_unbind(node: AbstractStackNode) -> Optional[Successor]:
    kwargs = {'node': node}
    if 'unbind' in node._successors:
        for succ in node._successors['unbind']:
            if succ.kwargs == kwargs:
                return succ
    return None


def _unbind_first(node: AbstractStackNode) -> List[Node]:
    if not isinstance(node, (StackNode, ParamStackNode)):
        raise TypeError('Cannot unbind node if it is not a (Param)StackNode')
    
    tensors = torch.unbind(node.tensor)
    new_nodes = []

    # Invert structure of node.edges_lists
    edges_lists = []
    node1_lists = []
    batch_idx = None
    for i, edge in enumerate(node._edges[1:]):
        if isinstance(edge, AbstractStackEdge):
            edges_lists.append(edge._edges)
            node1_lists.append(edge._node1_lists)
            if edge._edges[0].is_batch() and \
                ('batch' in edge._edges[0].axis1._name):
                # Save position of batch edge, whose dimension might change
                # TODO: case more than one batch edge
                batch_idx = i
        else:
            edges_lists.append([edge] * len(tensors))
            node1_lists.append([True] * len(tensors))
    lst = list(zip(tensors, list(zip(*edges_lists)),
                   list(zip(*node1_lists))))

    net = node._network
    for i, (tensor, edges, node1_list) in enumerate(lst):
        new_node = Node(axes_names=node.axes_names[1:],
                        name='unbind',
                        network=net,
                        leaf=False,
                        tensor=tensor,
                        edges=list(edges),
                        node1_list=list(node1_list))
        new_nodes.append(new_node)
        
    if net._unbind_mode:
        # Record in inverse_memory while tracing
        node._record_in_inverse_memory()
        
    else:  # index_mode
        if node._tensor_info['address'] is None:
            node_ref = node._tensor_info['node_ref']
        else:
            node_ref = node
                
        for i, new_node in enumerate(new_nodes):
            if new_node._tensor_info['address'] is not None:
                del new_node._network._memory_nodes[
                    new_node._tensor_info['address']]
            new_node._tensor_info['address'] = None
            
            new_node._tensor_info['node_ref'] = node_ref
            new_node._tensor_info['full'] = False
            
            if node_ref == node:
                index = [i]
                for j, (max_dim, dim) in enumerate(zip(node._shape[1:],
                                                       new_node._shape)):
                    if new_node._axes[j].is_batch():
                        # Admit any size in batch edges
                        index.append(slice(0, None))
                    else:
                        index.append(slice(max_dim - dim, max_dim))
                new_node._tensor_info['index'] = index
                
            else:
                node_index = node._tensor_info['index']
                aux_slice = node_index[0]
                if isinstance(aux_slice, list):
                    index = [aux_slice[i]]
                else:
                    index = [range(aux_slice.start,
                                   aux_slice.stop,
                                   aux_slice.step)[i]]
                    
                if node_index[1:]:
                    # If node is indexing from the original stack
                    for j, (aux_slice, dim) in enumerate(zip(node_index[1:],
                                                             new_node._shape)):
                        if new_node._axes[j].is_batch():
                            # Admit any size in batch edges
                            index.append(slice(0, None))
                        else:
                            index.append(slice(aux_slice.stop - dim,
                                               aux_slice.stop))
                
                else:
                    # If node has the same shape as the original stack
                    for j, (max_dim, dim) in enumerate(zip(node.shape[1:],
                                                           new_node._shape)):
                        if new_node._axes[j].is_batch():
                            # Admit any size in batch edges
                            index.append(slice(0, None))
                        else:
                            index.append(slice(max_dim - dim, max_dim))
                            
                new_node._tensor_info['index'] = index

    # Create successor
    successor = Successor(kwargs={'node': node},
                          child=new_nodes,
                          hints=batch_idx)
    
    # Add successor to parent
    if 'unbind' in node._successors:
        node._successors['unbind'].append(successor)
    else:
        node._successors['unbind'] = [successor]

    # Add operation to list of performed operations of TN
    net._seq_ops.append(('unbind', successor.kwargs))

    # Returns copy in order not to modify the successor
    # if the returned list gets modified by any means
    return new_nodes[:]


def _unbind_next(successor: Successor, node: AbstractStackNode) -> List[Node]:
    net = node._network
    if net._unbind_mode:
        tensors = torch.unbind(node.tensor)
        children = successor.child
        for tensor, child in zip(tensors, children):
            child._unrestricted_set_tensor_ops(tensor, True)
            
        # Record in inverse_memory while contracting
        # (to delete memory if possible)
        node._record_in_inverse_memory()
        return children[:]
        
    else: # index_mode
        batch_idx = successor.hints
        children = successor.child
        
        if batch_idx is None:
            return children[:]
        
        new_dim = node._shape[batch_idx + 1]
        child_dim = children[0]._shape[batch_idx]
        
        if new_dim == child_dim:
            return children[:]
        
        return successor.child[:]


unbind_op = Operation('unbind',
                      _check_first_unbind,
                      _unbind_first,
                      _unbind_next)

def unbind(node: AbstractStackNode) -> List[Node]:
    """
    Unbinds a :class:`StackNode` or :class:`ParamStackNode`, where the first
    dimension is assumed to be the stack dimension.
    
    If :meth:`~TensorNetwork.unbind_mode` is set to ``True``, each resultant
    node will store its own tensor. Otherwise, they will have only a reference
    to the corresponding slice of the ``(Param)StackNode``.
    
    Parameters
    ----------
    node : StackNode or ParamStackNode
        Node that is to be unbinded.
        
    Returns
    -------
    list[Node]
    """
    return unbind_op(node)


##################################   EINSUM   #################################
def _check_first_einsum(string: Text,
                        *nodes: AbstractNode) -> Optional[Successor]:
    kwargs = {'string': string,
              'nodes': nodes}
    
    if not nodes:
        raise ValueError('No nodes were provided')
    
    if 'einsum' in nodes[0]._successors:
        for succ in nodes[0]._successors['einsum']:
            if succ.kwargs == kwargs:
                return succ
    return None


def _einsum_first(string: Text, *nodes: AbstractNode) -> Node:
    for i in range(len(nodes[:-1])):
        if nodes[i]._network != nodes[i + 1]._network:
            raise ValueError('All `nodes` must be in the same network')
    
    if '->' not in string:
        raise ValueError('Einsum `string` should have an arrow `->` separating '
                         'inputs and output strings')
        
    input_strings = string.split('->')[0].split(',')
    if len(input_strings) != len(nodes):
        raise ValueError('Number of einsum subscripts must be equal to the '
                         'number of operands')
    if len(string.split('->')) >= 2:
        output_string = string.split('->')[1]
    else:
        output_string = ''

    # Check string and collect information from involved edges
    which_matrices = []
    matrices_strings = []
    
    # Used for counting appearances of output subscripts in the input strings
    output_dict = dict(zip(output_string, [0] * len(output_string)))
    
    output_char_index = dict(zip(output_string, range(len(output_string))))
    
    # Used for counting how many times a contracted edge's
    # subscript appears among input strings
    contracted_edges = dict()
    
    # Used for counting how many times a batch edge's
    # subscript appears among input strings
    batch_edges = dict()
    
    axes_names = dict(zip(range(len(output_string)),
                          [None] * len(output_string)))
    edges = dict(zip(range(len(output_string)),
                     [None] * len(output_string)))
    node1_list = dict(zip(range(len(output_string)),
                          [None] * len(output_string)))
    
    for i, input_string in enumerate(input_strings):
        if isinstance(nodes[i], (StackNode, ParamStackNode)):
            stack_char = input_string[0]
        for j, char in enumerate(input_string):
            if char not in output_dict:
                edge = nodes[i][j]
                if char not in contracted_edges:
                    contracted_edges[char] = [edge]
                else:
                    if len(contracted_edges[char]) >= 2:
                        raise ValueError(f'Subscript {char} appearing more than'
                                         ' once in the input should be a batch '
                                         'index, but it does not appear among '
                                         'the output subscripts')
                    if edge != contracted_edges[char][0]:
                        if isinstance(edge, AbstractStackEdge) and \
                                isinstance(contracted_edges[char][0],
                                           AbstractStackEdge):
                            edge = edge ^ contracted_edges[char][0]
                        else:
                            raise ValueError(f'Subscript {char} appears in two '
                                             'nodes that do not share a connected'
                                             ' edge at the specified axis')
                    contracted_edges[char].append(edge)
                    
                if isinstance(edge, ParamStackEdge):
                    if edge not in which_matrices:
                        matrices_strings.append(stack_char + (2 * char))
                        which_matrices.append(edge)
                        
                elif isinstance(edge, ParamEdge):
                    if edge not in which_matrices:
                        matrices_strings.append(2 * char)
                        which_matrices.append(edge)
            else:
                edge = nodes[i][j]
                if output_dict[char] == 0:
                    if edge.is_batch():
                        batch_edges[char] = 0
                    k = output_char_index[char]
                    axes_names[k] = nodes[i]._axes[j]._name
                    edges[k] = edge
                    node1_list[k] = nodes[i]._axes[j].is_node1()
                output_dict[char] += 1
                if (char in batch_edges) and edge.is_batch():
                    batch_edges[char] += 1

    for char in output_dict:
        if output_dict[char] == 0:
            raise ValueError(f'Output subscript {char} must appear among '
                             f'the input subscripts')
        if output_dict[char] > 1:
            if char in batch_edges:
                if batch_edges[char] < output_dict[char]:
                    raise ValueError(f'Subscript {char} used as batch, but some'
                                     ' of those edges are not batch edges')
            else:
                raise ValueError(f'Subscript {char} used as batch, but none '
                                 f'of those edges is a batch edge')

    for char in contracted_edges:
        if len(contracted_edges[char]) == 1:
            raise ValueError(f'Subscript {char} appears only once in the input '
                             f'but none among the output subscripts')

    input_string = ','.join(input_strings + matrices_strings)
    einsum_string = input_string + '->' + output_string
    tensors = [node.tensor for node in nodes]
    matrices = [edge.matrix for edge in which_matrices]
    path, _ = opt_einsum.contract_path(einsum_string, *(tensors + matrices))
    new_tensor = opt_einsum.contract(einsum_string, *(tensors + matrices),
                                     optimize=path)

    all_stack = True
    all_non_stack = True
    for node in nodes:
        if isinstance(node, (StackNode, ParamStackNode)):
            all_stack &= True
            all_non_stack &= False
        else:
            all_stack &= False
            all_non_stack &= True
            
    if not (all_stack or all_non_stack):
        raise TypeError('Cannot operate (Param)StackNode\'s with '
                        'other (non-stack) nodes')
        
    if all_stack:
        new_node = StackNode(axes_names=list(axes_names.values()),
                             name='einsum',
                             network=nodes[0]._network,
                             tensor=new_tensor,
                             edges=list(edges.values()),
                             node1_list=list(node1_list.values()))
    else:
        new_node = Node(axes_names=list(axes_names.values()),
                        name='einsum',
                        network=nodes[0]._network,
                        leaf=False,
                        param_edges=False,
                        tensor=new_tensor,
                        edges=list(edges.values()),
                        node1_list=list(node1_list.values()))
    
    # Create successor
    successor = Successor(kwargs = {'string': string,
                                    'nodes': nodes},
                          child=new_node,
                          hints={'einsum_string': einsum_string,
                                 'which_matrices': which_matrices,
                                 'path': path})
    
    # Add successor to parent
    if 'einsum' in nodes[0]._successors:
        nodes[0]._successors['einsum'].append(successor)
    else:
        nodes[0]._successors['einsum'] = [successor]

    # Add operation to list of performed operations of TN
    net = nodes[0]._network
    net._seq_ops.append(('einsum', successor.kwargs))
    
    # Record in inverse_memory while tracing
    for node in nodes:
        node._record_in_inverse_memory()
    
    return new_node


def _einsum_next(successor: Successor,
                 string: Text,
                 *nodes: AbstractNode) -> Node:
    hints = successor.hints
    
    tensors = [node.tensor for node in nodes]
    matrices = [edge.matrix for edge in hints['which_matrices']]
    new_tensor = opt_einsum.contract(hints['einsum_string'],
                                     *(tensors + matrices),
                                     optimize=hints['path'])
    
    child = successor.child
    child._unrestricted_set_tensor_ops(new_tensor)
    
    # Record in inverse_memory while contracting
    # (to delete memory if possible)
    for node in nodes:
        node._record_in_inverse_memory()
        
    return child


einsum_op = Operation('einsum',
                      _check_first_einsum,
                      _einsum_first,
                      _einsum_next)

def einsum(string: Text, *nodes: AbstractNode) -> Node:
    """
    Performs einsum contraction based on `opt_einsum
    <https://optimized-einsum.readthedocs.io/en/stable/autosummary/opt_einsum.contract.html>`_.
    This operation facilitates contracting several nodes at once, specifying
    directly the order of appearance of the resultant edges. Without this
    operation, several contractions and permutations would be needed.
    
    Since it adapts a tensor operation for nodes, certain nodes' properties are
    first checked. Thus, it verifies that all edges are correctly connected and
    all nodes are in the same network. It also performs batch contraction
    whenever corresponding edges are batch edges.

    Parameters
    ----------
    string : str
        Einsum-like string indicating how the contraction should be performed.
        It consists of a comma-separated list of inputs and an output separated
        by an arrow. For instance, the contraction
        
        .. math::

            T_{j,l} = \sum_{i,k,m}{A_{i,j,k}B_{k,l,m}C_{i,m}}
            
        can be expressed as::
        
            string = 'ijk,klm,im->jl'
    nodes : AbstractNode...
        Nodes that are involved in the contraction. Should appear in the same
        order as it is specified in the ``string``. They should either be all
        ``(Param)StackNode``'s or none of them be a ``(Param)StackNode``.

    Returns
    -------
    Node
    """
    return einsum_op(string, *nodes)


##############################   STACKED EINSUM   #############################
def stacked_einsum(string: Text,
                   *nodes_lists: List[AbstractNode]) -> List[Node]:
    """
    Applies the same :func:`einsum` operation (same ``string``) to a sequence
    of groups of nodes (all groups having the same amount of nodes, with the
    same properties, etc.). That is, it stacks these groups of nodes into a
    siongle collection of nodes that is then contracte via ``einsum``, and
    :func:`unbinded <unbind>` afterwards.

    Parameters
    ----------
    string : str
        Einsum-like string indicating how the contraction should be performed.
        It consists of a comma-separated list of inputs and an output separated
        by an arrow. For instance, the contraction
        
        .. math::

            T_{j,l} = \sum_{i,k,m}{A_{i,j,k}B_{k,l,m}C_{i,m}}
            
        can be expressed as::
        
            string = 'ijk,klm,im->jl'
    nodes : List[Node or ParamNode]...
        Nodes that are involved in the contraction. Should appear in the same
        order as it is specified in the ``string``.

    Returns
    -------
    list[Node]
    """
    stacks_list = []
    for nodes_list in nodes_lists:
        stacks_list.append(stack(nodes_list))

    input_strings = string.split('->')[0].split(',')
    output_string = string.split('->')[1]

    i = 0
    stack_char = opt_einsum.get_symbol(i)
    for input_string in input_strings:
        for input_char in input_string:
            if input_char == stack_char:
                i += 1
                stack_char = opt_einsum.get_symbol(i)
                
    input_strings = list(map(lambda s: stack_char + s, input_strings))
    input_string = ','.join(input_strings)
    output_string = stack_char + output_string
    string = input_string + '->' + output_string
    
    result = einsum(string, *stacks_list)
    unbinded_result = unbind(result)
    return unbinded_result
