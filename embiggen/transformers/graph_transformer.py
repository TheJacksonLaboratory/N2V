"""GraphTransformer class to convert graphs to edge embeddings."""
from typing import List, Union
import pandas as pd
import numpy as np
from ensmallen_graph import EnsmallenGraph  # pylint: disable=no-name-in-module

from .edge_transformer import EdgeTransformer


class GraphTransformer:
    """GraphTransformer class to convert graphs to edge embeddings."""

    def __init__(self, method: str = "hadamard"):
        """Create new GraphTransformer object.

        Parameters
        ------------------------
        method: str = "hadamard",
            Method to use for the embedding.
            Can either be 'hadamard', 'average', 'weightedL1', 'weightedL2' or
            a custom lambda that receives two numpy arrays with the nodes
            embedding and returns the edge embedding.
        """
        self._transformer = EdgeTransformer(method=method)

    def fit(self, embedding: pd.DataFrame):
        """Fit the model.

        Parameters
        -------------------------
        embedding: pd.DataFrame,
            Embedding to use to fit the transformer.
            This is a pandas DataFrame and NOT a numpy array because we need
            to be able to remap correctly the vector embeddings in case of
            graphs that do not respect the same internal node mapping but have
            the same node set. It is possible to remap such graphs using
            Ensmallen's remap method but it may be less intuitive to users.
        """
        self._transformer.fit(embedding)

    def transform(self, graph: Union[EnsmallenGraph, np.ndarray, List[List[str]]]) -> np.ndarray:
        """Return edge embedding for given graph using provided method.

        Parameters
        --------------------------
        graph: Union[EnsmallenGraph, np.ndarray, List[List[str]]],
            The graph whose edges are to embed.
            It can either be an EnsmallenGraph or a list of lists of edges.

        Raises
        --------------------------
        ValueError,
            If embedding is not fitted.

        Returns
        --------------------------
        Numpy array of embeddings.
        """
        if isinstance(graph, EnsmallenGraph):
            graph = graph.get_edge_names()
        if isinstance(graph, List):
            graph = np.array(graph)
        if isinstance(graph, np.ndarray):
            sources = graph[:, 0]
            destinations = graph[:, 1]
        return self._transformer.transform(sources, destinations)
