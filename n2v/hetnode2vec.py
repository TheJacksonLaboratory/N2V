import numpy as np
import random
import logging
import os
import time
from collections import defaultdict

log = logging.getLogger("hn2v.log")

handler = logging.handlers.WatchedFileHandler(
    os.environ.get("LOGFILE", "hn2v.log"))
formatter = logging.Formatter('%(asctime)s - %(levelname)s -%(filename)s:%(lineno)d - %(message)s')
handler.setFormatter(formatter)
log = logging.getLogger()
log.setLevel(logging.INFO)
log.addHandler(handler)
log.addHandler(logging.StreamHandler())


class Graph:
    """
    A class to represent the Graph and its associated
    functionality.

    """

    def __init__(self, csf_graph, p, q, gamma, doHN2V=True):
        """
        Note that the CSF graph is always undirected. It stores two directed edges to represent each undirected edge.
        :param csf_graph: An undirected Compressed Storage Format graph object
        :param p:
        :param q:
        :param gamma:
        :param doHN2V:
        """
        self.g = csf_graph
        self.p = p
        self.q = q
        self.gamma = gamma
        if doHN2V:
            self.__preprocess_transition_probs_hn2v()
        else:
            self.__preprocess_transition_probs()

    def node2vec_walk(self, walk_length, start_node):
        """
        Simulate a random walk starting from start node.
        """
        g = self.g
        alias_nodes = self.alias_nodes
        alias_edges = self.alias_edges

        walk = [start_node]

        while len(walk) < walk_length:
            cur = walk[-1]
            # g returns a sorted list of neighbors
            cur_nbrs = g.neighbors(cur)
            if len(cur_nbrs) > 0:
                if len(walk) == 1:
                    walk.append(cur_nbrs[self.alias_draw(alias_nodes[cur][0], alias_nodes[cur][1])])
                else:
                    prev = walk[-2]
                    next = cur_nbrs[self.alias_draw(alias_edges[(prev, cur)][0], alias_edges[(prev, cur)][1])]
                    walk.append(next)
            else:
                break

        return walk

    def simulate_walks(self, num_walks, walk_length):
        """
        Repeatedly simulate random walks from each node.
        """
        g = self.g
        walks = []
        nodes = g.nodes()  # this is a list
        log.info('Walk iteration:')
        for walk_iter in range(num_walks):
            print("{}/{}".format(walk_iter+1, num_walks))
            random.shuffle(nodes)
            for node in nodes:
                walks.append(self.node2vec_walk(walk_length=walk_length, start_node=node))

        return walks

    #def is_in_same_network_nodetype(self, src, dst):
        """
        checks if the nodes src and dst belongs to the same network or not. They are in one network if they both start
        with 'g' or 'd' or 'p'
        """
     #   if src[0] == dst[0]:
      #      return True
       # else:
        #    return False

    def get_alias_edge(self, src, dst):
        """
        Get the alias edge setup lists for a given edge.
        """
        g = self.g
        p = self.p
        q = self.q
        gamma = self.gamma
        unnormalized_probs = []
        num_same_network = 0
        num_diff_network = 0
        log.info("source node:{}".format(src))
        log.info("destination node:{}".format(dst))
        for dst_nbr in g.neighbors(dst):
            #log.info("neighbour of destination node:{}".format(dst_nbr))
            edge_weight = g.weight(dst, dst_nbr)
            if dst_nbr == src:
                unnormalized_probs.append(edge_weight / p)
            elif g.has_edge(dst_nbr, src):
                unnormalized_probs.append(edge_weight)
            else:
                unnormalized_probs.append(edge_weight / q)
        norm_const = sum(unnormalized_probs)
        normalized_probs = [float(u_prob) / norm_const for u_prob in unnormalized_probs]
        log.info("number of walks in the same network:{} ".format(num_same_network))
        log.info("number of walks in different network:{} ".format(num_diff_network))
        return self.__alias_setup(normalized_probs)

    def __preprocess_transition_probs(self):
        """
        Preprocessing of transition probabilities for guiding the random walks.
        """
        g = self.g

        alias_nodes = {}
        for node in g.nodes():
            # self.calculate_proportion_of_different_neighbors(node)
            unnormalized_probs = [g.weight(node, nbr) for nbr in g.neighbors(node)]
            log.info("unnormalized probs {}".format(unnormalized_probs))
            norm_const = sum(unnormalized_probs)
            log.info("norm_const {}".format(norm_const))
            normalized_probs = [float(u_prob) / norm_const for u_prob in unnormalized_probs]
            log.info("normalized probs {}".format(normalized_probs))
            # normalized_probs = np.true_divide(unnormalized_probs, norm_const)
            alias_nodes[node] = self.__alias_setup(normalized_probs)
            log.info("alias_nodes[node] {}".format(alias_nodes[node]))
            log.info("node {}".format(node))

        alias_edges = {}

        # Note that g.edges returns two directed edges to represent an undirected edge between any two nodes
        # We do not need to create any additional edges for the random walk as in the Stanford implementation
        for edge in g.edges():
            alias_edges[edge] = self.get_alias_edge(edge[0], edge[1])

        self.alias_nodes = alias_nodes
        self.alias_edges = alias_edges

        return

    def get_alias_edge_hn2v(self, src, dst):
        """
        Get the alias edge setup lists for a given edge.
        """
        g = self.g
        p = self.p
        q = self.q
        num_same_network = 0
        num_diff_network = 0
        log.info("source node:{}".format(src))
        log.info("destination node:{}".format(dst))
        dsttype = dst[0]
        dst2count = defaultdict(int)  # counts for going from current node ("dst") to nodes of a given type (g, p,d)
        dst2prob = defaultdict(float)  # probs calculated from own2count
        total_neighbors = 0
        # No need to explicitly sort, g returns a sorted list
        sorted_neighbors = g.neighbors(dst)
        for nbr in sorted_neighbors:
            nbrtype = nbr[0]
            dst2count[nbrtype] += 1
            total_neighbors += 1
        total_non_own_probability = 0.0
        for n, count in dst2count.items():
            if n == dsttype:
                # we need to count up the other types before we can calculate this!
                continue
            else:
                # owntype is going to a different node type
                dst2prob[n] = float(self.gamma) / float(count)
                total_non_own_probability += dst2prob[n]
        if dst2count[dsttype] == 0:
            dst2prob[dsttype] = 0
        else:
            dst2prob[dsttype] = (1 - total_non_own_probability) / float(dst2count[dsttype])
        # Now assign the final unnormalized probs
        unnormalized_probs = np.zeros(total_neighbors)
        i = 0
        for dst_nbr in sorted_neighbors:
            nbrtype = dst_nbr[0]
            prob = dst2prob[nbrtype]
            edge_weight = g.weight(dst, dst_nbr)
            if dst_nbr == src:
                unnormalized_probs[i] = prob * edge_weight / p
            elif g.has_edge(dst_nbr, src):
                unnormalized_probs[i] = prob * edge_weight
            else:
                unnormalized_probs[i] = prob * edge_weight / q
            i += 1
        norm_const = sum(unnormalized_probs)
        normalized_probs = [float(u_prob) / norm_const for u_prob in unnormalized_probs]
        log.info("number of walks in the same network:{} ".format(num_same_network))
        log.info("number of walks in different network:{} ".format(num_diff_network))
        return self.__alias_setup(normalized_probs)

    def __preprocess_transition_probs_hn2v(self):
        """
        Preprocessing of transition probabilities for guiding the random walks.
        This version uses gamma to calculate weighted skipping across a heterogeneous network
        """
        starttime = time.time()
        G = self.g

        alias_edges = {}
        alias_nodes = {}
        for node in G.nodes():
            # ASSUMPTION. The type of the node is encoded by its first character, e.g., g42 is a gene
            owntype = node[0]
            own2count = defaultdict(int)  # counts for going from current node ("own") to nodes of a given type (g, p,d)
            own2prob = defaultdict(float)  # probs calculated from own2count
            total_neighbors = 0
            # G returns a sorted list of neighbors of node
            sorted_neighbors = G.neighbors(node)
            for nbr in sorted_neighbors:
                nbrtype = nbr[0]
                own2count[nbrtype] += 1
                total_neighbors += 1
            total_non_own_probability = 0.0
            for n, count in own2count.items():
                if n == owntype:
                    # we need to count up the other types before we can calculate this!
                    continue
                else:
                    # owntype is going to a different node type
                    own2prob[n] = float(self.gamma) / float(count)
                    total_non_own_probability += own2prob[n]
            if own2count[owntype] == 0:
                own2prob[owntype] = 0
            else:
                own2prob[owntype] = (1 - total_non_own_probability) / float(own2count[owntype])
            # Now assign the final unnormalized probs
            unnormalized_probs = np.zeros(total_neighbors)
            i = 0
            for nbr in sorted_neighbors:
                nbrtype = nbr[0]
                prob = own2prob[nbrtype]
                unnormalized_probs[i] = prob * G.weight(inode, nbr)
                i += 1
            norm_const = sum(unnormalized_probs)
            log.info("norm_const {}".format(norm_const))
            normalized_probs = [float(u_prob) / norm_const for u_prob in unnormalized_probs]
            alias_nodes[node] = self.__alias_setup(normalized_probs)
        for edge in G.edges():
            alias_edges[edge] = self.get_alias_edge_hn2v(edge[0], edge[1])

        self.alias_edges = alias_edges
        self.alias_nodes = alias_nodes
        endtime = time.time()
        duration = endtime - starttime
        log.info("Setup alias probabilities for graph in {:.2f} seconds.".format(duration))
        print("Setup alias probabilities for graph in {:.2f} seconds.".format(duration))

    def retrieve_alias_nodes(self):
        return self.alias_nodes

    def retrieve_alias_edges(self):
        return self.alias_edges

    def __alias_setup(self, probs):
        """
            Compute utility lists for non-uniform sampling from discrete distributions.
            Refer to https://hips.seas.harvard.edu/blog/2013/03/03/the-alias-method-efficient-
            sampling-with-many-discrete-outcomes/ for details
            probs -- the normalized probabilities calculated by , e.g., [0.4 0.28 0.32]
        """
        k = len(probs)
        q = np.zeros(k)
        j = np.zeros(k, dtype=np.int)
        smaller = []
        larger = []
        for kk, prob in enumerate(probs):
            q[kk] = k * prob
            if q[kk] < 1.0:
                smaller.append(kk)
            else:
                larger.append(kk)

        while len(smaller) > 0 and len(larger) > 0:
            small = smaller.pop()
            large = larger.pop()

            j[small] = large
            q[large] = q[large] + q[small] - 1.0
            if q[large] < 1.0:
                smaller.append(large)
            else:
                larger.append(large)
        return j, q

    def alias_draw(self, j, q):
        """
        Draw sample from a non-uniform discrete distribution using alias sampling.
        """

        k = len(j)

        kk = int(np.floor(np.random.rand() * k))
        if np.random.rand() < q[kk]:
            return kk
        else:
            return j[kk]

# def _repr_html_(self):
#    G = self.G
#    if isinstance(G,(nx.MultiDiGraph,nx.MultiGraph)):
#      return self.multigraph_html()

#   html = '<table><caption>Heterogeneous Node2Vec Graph Summary</caption><thead><tr><th>Node A</th>'
#  html += '<th>Node B</th><th>Edge type</th><th>Edge weight</th></tr></thead>'
#  html += "<tbody>"
#  for n,nbrs in G.adj.items():
#      for nbr,eattr in nbrs.items():
#          #wt = eattr['weight']#
#          wt = eattr.get('weight', 0)
#         et = eattr.get('edgetype','n/a')
#         html += '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(n,nbr,et,wt)
# html += '</tbody></table>'
# return html
