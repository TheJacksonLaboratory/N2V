from typing import List, Union, Tuple, Dict
import numpy as np  # type: ignore
from numba import typed, types, njit, prange  # type: ignore
from .alias_method import alias_draw, alias_setup
import tensorflow as tf  # type: ignore
from dict_hash import sha256, Hashable  # type: ignore
from .numba_graph import NumbaGraph
from .random_walks import random_walk, random_walk_with_traps

#######################################
# Class to wrapp the NumbaGraph code  #
#######################################


class Graph(Hashable):
    def __init__(self, *args, **kwargs):
        """Create new instance of Graph."""
        self._graph = NumbaGraph(*args, **kwargs)

    def random_walk(self, number: int, length: int) -> tf.Tensor:
        """Return a list of graph walks

        Parameters
        ----------
        number: int,
            Number of walks to execute.
        length:int,
            The length of the walks in edges traversed.

        Returns
        -------
        Tensor with walks containing the numeric IDs of nodes.
        """
        if not self._graph.random_walk_preprocessing:
            raise ValueError(
                "Given graph was not properly setup for random walk.")
        if self._graph.has_traps:
            return tf.ragged.constant(random_walk_with_traps(self._graph, number, length))
        return tf.constant(random_walk(self._graph, number, length))

    @property
    def worddictionary(self) -> Dict[str, int]:
        """Return mapping for nodes to numeric node ID."""
        return self._graph._nodes_mapping

    @property
    def reverse_worddictionary(self) -> List[str]:
        """Return mapping for numeric nodes ID to nodes."""
        return self._graph._nodes_reverse_mapping

    def neighbors(self, node: int) -> List:
        """Return neighbors of given node.

        Parameters
        ---------------------
        node: int,
            The node whose neigbours are to be identified.

        Returns
        ---------------------
        List of neigbours of given node.
        """
        return self._graph.neighbors(node)

    @property
    def edges(self) -> np.ndarray:
        """Return edges of given node.

        Returns
        ---------------------
        Numpy array of edges.
        """
        return np.array(self._graph._edges_indices)

    @property
    def sources(self) -> np.ndarray:
        """Return sources of all edges

        Returns
        ---------------------
        Numpy array of surces.
        """
        return self.edges[:, 0]
    
    @property
    def destinations(self) -> np.ndarray:
        """Return destinations of all edges

        Returns
        ---------------------
        Numpy array of destinations.
        """
        return self.edges[:, 1]

    def degree(self, node: int) -> int:
        """Return degree of given node.

        Parameters
        ---------------------
        node: int,
            The node whose neigbours are to be identified.

        Returns
        ---------------------
        Number of neighbors of given node.
        """
        return self._graph.degree(node)

    def consistent_hash(self) -> str:
        """Return hash for the current instance of the graph."""
        return sha256({
            "random_walk_preprocessing": self._graph.random_walk_preprocessing,
            **(
                {
                    "edges_alias": self._graph._edges_alias,
                    "nodes_alias": self._graph._nodes_alias,
                }
                if self._graph.random_walk_preprocessing else {}
            ),
            "edges": self._graph._edges,
            "nodes_mapping": self._graph._nodes_mapping
        })
