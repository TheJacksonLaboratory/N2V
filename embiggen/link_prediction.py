import sys
from typing import List, Tuple
from sklearn.calibration import CalibratedClassifierCV  # type:ignore
from sklearn.linear_model import LogisticRegression   # type: ignore
from sklearn import metrics   # type: ignore
from sklearn.ensemble import RandomForestClassifier   # type: ignore
from sklearn import svm   # type: ignore
from sklearn.metrics import roc_auc_score, average_precision_score   # type: ignore
from embiggen.utils import load_embeddings
import numpy as np  # type: ignore
from .neural_networks import MLP, FFNN, MultiModalFFNN
import csv

import logging
#import os
#handler = logging.handlers.WatchedFileHandler(os.environ.get("LOGFILE", "link_prediction.log"))
# formatter = logging.Formatter('%(asctime)s - %(levelname)s -%(filename)s:%(lineno)d - %(message)s')
# handler.setFormatter(formatter)
# log = logging.getLogger()
# log.setLevel(os.environ.get("LOGLEVEL", "DEBUG"))
# log.addHandler(handler)

class LinkPrediction(object):
    """
    Set up for predicting links from results of node2vec analysis

    Attributes:
        pos_train_graph: The training graph
        pos_validation_graph: Graph of validation edges
        pos_test_graph:  Graph of links that we want to predict
        neg_train_graph: Graph of non-existence links in training graph
        neg_validation_graph: Graph of non-existence links of the validation edges
        neg_test_graph: Graph of non-existence links that we want to predict as negative edges
        embedded_train_graph_path: The file produced by word2vec with the nodes embedded as vectors
        edge_embedding_method: The method to embed edges. It can be "hadamard", "average", "weightedL1" or
            "weightedL2"
        classifier: classification method. It can be either "LR" for logistic regression, "RF" for random forest,
            "SVM" for support vector machine, "MLP" for a multi-layer perceptron, "FFNN" for a feed forward neural network.

         skip_valid: if True, link prediction is done on train and test sets. If False, link prediction is done on
         train, validation and test sets.

    """

    def __init__(self, pos_train_graph, pos_validation_graph, pos_test_graph, neg_train_graph, neg_validation_graph,
                 neg_test_graph, embedded_train_graph_path, edge_embedding_method, classifier, skip_valid, output):
        """
        Set up for predicting links from results of node2vec analysis
        :param pos_train_graph: The training graph
        :param pos_validation_graph: The validation graph
        :param pos_test_graph:  Graph of links that we want to predict
        :param neg_train_graph: Graph of non-existence links in training graph
        :param neg_validation_graph: Graph of non-existence links in the validation graph
        :param neg_test_graph: Graph of non-existence links that we want to predict as negative edges
        :param embedded_train_graph_path: The file produced by word2vec with the nodes embedded as vectors
        :param edge_embedding_method: The method to embed edges. It can be "hadamard", "average", "weightedL1" or
            "weightedL2"
        :param classifier: classification method. It can be either "LR" for logistic regression, "RF" for random forest,
            "SVM" for support vector machine, "MLP" for a multi-layer perceptron, "FFNN" for a feed forward neural network.
        :param skip_valid: if True, link prediction is done on train and test sets. If False, link prediction is done on
         train, validation and test sets.
        :param output: output file for the results of link prediction
        """
        self.pos_train_edges = pos_train_graph.edges()
        self.pos_test_edges = pos_test_graph.edges()
        self.pos_valid_edges = pos_validation_graph.edges()
        self.neg_train_edges = neg_train_graph.edges()
        self.neg_valid_edges = neg_validation_graph.edges()
        self.neg_test_edges = neg_test_graph.edges()
        self.train_nodes = pos_train_graph.nodes()
        self.validation_nodes = pos_validation_graph.nodes()
        self.test_nodes = pos_test_graph.nodes()
        self.embedded_train_graph = embedded_train_graph_path
        self.map_node_vector = load_embeddings(self.embedded_train_graph)
        self.edge_embedding_method = edge_embedding_method
        self.train_edge_embs = []
        self.valid_edges_embs = []
        self.test_edge_embs = []
        self.train_labels = []
        self.test_labels = []
        self.valid_edge_labels = []
        self.classifier = classifier
        self.train_predictions = []
        self.validation_predictions = []
        self.test_predictions = []
        self.train_confusion_matrix = []
        self.test_confusion_matrix = []
        self.validation_confusion_matrix = []
        self.valid_edge_embs = None
        self.train_roc = None
        self.valid_roc = None
        self.train_average_precision = None
        self.valid_average_precision = None
        self.test_roc = None
        self.test_average_precision = None
        self.skip_validation = skip_valid
        self.output = output

    def read_embeddings(self):
        """
        reading the embeddings generated by the training graph
        :return:
        """
        n_lines = 0
        map_node_vector = {}  # reading the embedded graph to a map, key:node, value:vector
        with open(self.embedded_train_graph, 'r') as f:
            #next(f)#skip the header which contains 2 integers; number of nodes and dimension
            for line in f:
                fields = line.split() #the format of each line: node v_1 v_2 ... v_d where v_i's are elements of
                # the array corresponding to the embedding of the node
                embe_vec = [float(i) for i in fields[1:]]
                map_node_vector.update({fields[0]: embe_vec})#map each node to its corresponding vector
                n_lines += 1
        f.close()
        self.map_node_vector = map_node_vector
        logging.info("Finished ingesting {} lines (vectors) from {}".format(n_lines, self.embedded_train_graph))

    def prepare_edge_and_node_labels(self) -> None:
        """
        Prepare these instance variables for training, testing, and validation:
        embeddings for training src, dst, edges:
        self.train_src_embs
        self.train_dst_embs
        self.train_edge_embs
        self.train_labels - 1 for positive, 0 for negative

        embeddings for test src, dst, edges
        self.test_src_embs
        self.test_dst_embs
        self.test_edge_embs
        self.test_labels - 1 for positive, 0 for negative

        embeddings for validation src, dst, edges
        self.valid_src_embs
        self.valid_dst_embs
        self.valid_edge_embs
        self.valid_labels - 1 for positive, 0 for negative

        :return: None
        """
        pos_train = self.create_edge_embeddings(edge_list=self.pos_train_edges,
                                                node2vector_map=self.map_node_vector)
        pos_train_src_embs, pos_train_dst_embs, pos_train_edge_embs = pos_train

        neg_train = self.create_edge_embeddings(edge_list=self.neg_train_edges,
                                                node2vector_map=self.map_node_vector)
        neg_train_src_embs, neg_train_dst_embs, neg_train_edge_embs = neg_train

        self.train_src_embs = np.concatenate([pos_train_src_embs, neg_train_src_embs])
        self.train_dst_embs = np.concatenate([pos_train_dst_embs, neg_train_dst_embs])
        self.train_edge_embs = np.concatenate([pos_train_edge_embs, neg_train_edge_embs])
        # Create train-set edge labels: 1 = true edge, 0 = false edge
        self.train_labels = np.concatenate([np.ones(len(pos_train_edge_embs)),
                                            np.zeros(len(neg_train_edge_embs))])

        # Test-set edge embeddings, labels
        pos_test = self.create_edge_embeddings(edge_list=self.pos_test_edges,
                                               node2vector_map=self.map_node_vector)
        pos_test_src_embs, pos_test_dst_embs, pos_test_edge_embs = pos_test

        neg_test = self.create_edge_embeddings(edge_list=self.neg_test_edges,
                                               node2vector_map=self.map_node_vector)
        neg_test_src_embs, neg_test_dst_embs, neg_test_edge_embs = neg_test

        self.test_src_embs = np.concatenate([pos_test_src_embs, neg_test_src_embs])
        self.test_dst_embs = np.concatenate([pos_test_dst_embs, neg_test_dst_embs])
        self.test_edge_embs = np.concatenate([pos_test_edge_embs, neg_test_edge_embs])

        # Create test-set edge labels: 1 = true edge, 0 = false edge
        self.test_labels = np.concatenate([np.ones(len(pos_test_edge_embs)),
                                           np.zeros(len(neg_test_edge_embs))])
        if not self.skip_validation:
            # Validation-set edge embeddings, labels
            pos_valid = self.create_edge_embeddings(edge_list=self.pos_valid_edges,
                                                    node2vector_map=self.map_node_vector)
            pos_valid_src_embs, pos_valid_dst_embs, pos_valid_edge_embs = pos_valid

            neg_valid = self.create_edge_embeddings(edge_list=self.neg_valid_edges,
                                                    node2vector_map=self.map_node_vector)
            neg_valid_src_embs, neg_valid_dst_embs, neg_valid_edge_embs = neg_valid

            self.valid_src_embs = np.concatenate([pos_valid_src_embs,
                                                  neg_valid_src_embs])
            self.valid_dst_embs = np.concatenate([pos_valid_dst_embs,
                                                  neg_valid_dst_embs])
            self.valid_edge_embs = np.concatenate([pos_valid_edge_embs,
                                                   neg_valid_edge_embs])
            # Create validation-set edge labels: 1 = true edge, 0 = false edge
            self.valid_labels = np.concatenate([np.ones(len(pos_valid_edge_embs)),
                                                np.zeros(len(neg_valid_edge_embs))])

        logging.info("get test labels")
        logging.info("Training edges (positive): {}".format(len(self.pos_train_edges)/2))
        logging.info("Training edges (negative): {}".format(len(neg_train_edge_embs)/2))

        logging.info("Test edges (positive): {}".format(len(self.pos_test_edges)/2))
        logging.info("Test edges (negative): {}".format(len(neg_test_edge_embs)/2))

        if not self.skip_validation:
            logging.info("Validation edges (positive): {}".format(len(self.pos_valid_edges)/2))
            logging.info("Validation edges (negative): {}".format(len(neg_valid_edge_embs)/2))

    def predict_links(self):
        """
        Train  classifier on train-set edge embeddings. Classifier is one of:
        LR: logistic regression
        RF: random forest
        SVM: support vector machine
        MLP: multilayer perceptron
        FFNN: feed-forward neural network
        MMFFNN: multi-modal feed-forward neural network
        All classifiers work using default parameters.
        :return:
        """

        if self.classifier == "LR":
            edge_classifier = LogisticRegression()
        elif self.classifier == "RF":
            edge_classifier = RandomForestClassifier()
        elif self.classifier == "MLP":
            edge_classifier = MLP((self.train_edge_embs.shape[-1],))
        elif self.classifier == "FFNN":
            edge_classifier = FFNN((self.train_edge_embs.shape[-1],))
        elif self.classifier == "MultiModalFFNN":
            edge_classifier = MultiModalFFNN((self.train_src_embs.shape[-1],))
        else:
            # implement linear SVM.
            logging.info("Using SVM (default) classifier for link prediction")
            model_svc = svm.LinearSVC()
            edge_classifier = CalibratedClassifierCV(model_svc)

        if self.classifier == "MultiModalFFNN":
            # multimodalFFNN fits and predicts with different args from the other NNs
            edge_classifier.fit_multi_modal(self.train_src_embs,
                                            self.train_dst_embs,
                                            self.train_labels)
            self.train_predictions = edge_classifier.predict_multi_modal(
                                            self.train_src_embs,
                                            self.train_dst_embs)
            self.test_predictions = edge_classifier.predict_multi_modal(
                                            self.test_src_embs,
                                            self.test_dst_embs)
            if not self.skip_validation:
                self.validation_predictions = edge_classifier.predict_multi_modal(
                                            self.valid_src_embs,
                                            self.valid_dst_embs)
            # Predicted edge scores: probability of being of class "1" (real edge)
            train_preds = edge_classifier.predict_proba_multi_modal(
                                            self.train_src_embs,
                                            self.train_dst_embs)[:, 1]
            test_preds = edge_classifier.predict_proba_multi_modal(
                                            self.test_src_embs,
                                            self.test_dst_embs)[:, 1]

            if not self.skip_validation:
                validation_preds = edge_classifier.predict_proba_multi_modal(
                                            self.valid_src_embs,
                                            self.valid_dst_embs)[:, 1]

        else:
            edge_classifier.fit(self.train_edge_embs, self.train_labels)
            self.train_predictions = edge_classifier.predict(self.train_edge_embs)
            self.test_predictions = edge_classifier.predict(self.test_edge_embs)

            if not self.skip_validation:
                self.validation_predictions =\
                    edge_classifier.predict(self.valid_edge_embs)

            # Predicted edge scores: probability of being of class "1" (real edge)
            train_preds = edge_classifier.predict_proba(self.train_edge_embs)[:, 1]
            test_preds = edge_classifier.predict_proba(self.test_edge_embs)[:, 1]

            if not self.skip_validation:
                validation_preds = edge_classifier.predict_proba(self.valid_edge_embs)[:, 1]

        self.train_confusion_matrix = metrics.confusion_matrix(self.train_labels,
                                                               self.train_predictions)
        self.test_confusion_matrix = metrics.confusion_matrix(self.test_labels,
                                                              self.test_predictions)

        self.train_roc = roc_auc_score(self.train_labels, train_preds)  # get the training auc score
        self.test_roc = roc_auc_score(self.test_labels, test_preds)  # get the test auc score
        self.train_average_precision = average_precision_score(self.train_labels, train_preds)
        self.test_average_precision = average_precision_score(self.test_labels, test_preds)

        if not self.skip_validation:
            self.validation_confusion_matrix = metrics.confusion_matrix(
                self.valid_labels, self.validation_predictions)
            self.valid_roc = roc_auc_score(self.valid_labels, validation_preds)  # get the auc score of validation
            self.valid_average_precision = average_precision_score(self.valid_labels, validation_preds)

    def predicted_ppi_links(self):
        """
        :return: positive test edges and their prediction, 1: predicted correctly, 0: otherwise
        """
        logging.info("positive test edges and their prediction:")
        for i in range(len(self.pos_test_edges)):
            logging.info("edge {} prediction {}".format(self.pos_test_edges[i], self.test_predictions[i]))

        if not self.skip_validation:
            logging.info("positive validation edges and their prediction:")
            for i in range(len(self.pos_valid_edges)):
                logging.info("edge {} prediction {}".format(self.pos_valid_edges[i], self.validation_predictions[i]))

    def predicted_ppi_non_links(self):
        """
        :return: negative test edges (non-edges) and their prediction, 0: predicted correctly, 1: otherwise
        """
        logging.info("negative test edges and their prediction:")

        for i in range(len(self.neg_test_edges)):
            logging.info("edge {} prediction {}".format(self.neg_test_edges[i], self.test_predictions[i + len(self.pos_test_edges)]))

        if not self.skip_validation:
            logging.info("negative validation edges and their prediction:")

            for i in range(len(self.neg_valid_edges)):
                logging.info("edge {} prediction {}".format(self.neg_valid_edges[i],
                                                            self.validation_predictions[i + len(self.pos_valid_edges)]))

    def output_classifier_results(self):
        """
        The method prints some metrics of the performance of the logistic regression classifier. including accuracy,
        specificity and sensitivity

        Attributes used in method:
            predictions: prediction results of the logistic regression
            confusion_matrix:  confusion_matrix[0, 0]: True negatives, confusion_matrix[0, 1]: False positives,
            confusion_matrix[1, 1]: True positives and confusion_matrix[1, 0]: False negatives
            train_roc, test_roc: AUC score
            train_average_precision, test_average_precision: Average precision
         """

        train_conf_matrix = self.train_confusion_matrix
        total = sum(sum(train_conf_matrix))
        train_accuracy = (train_conf_matrix[0, 0] + train_conf_matrix[1, 1]) / total
        train_specificity = train_conf_matrix[0, 0] / (train_conf_matrix[0, 0] + train_conf_matrix[0, 1])
        train_sensitivity = train_conf_matrix[1, 1] / (train_conf_matrix[1, 0] + train_conf_matrix[1, 1])
        train_f1_score = (2.0 * train_conf_matrix[1, 1]) / (
                2.0 * train_conf_matrix[1, 1] + train_conf_matrix[0, 1] + train_conf_matrix[1, 0])
        # f1-score =2 * TP / (2 * TP + FP + FN)

        logging.info("confusion matrix.training: {}\n".format(str(train_conf_matrix)))

        if not self.skip_validation:
            valid_conf_matrix = self.validation_confusion_matrix
            total = sum(sum(valid_conf_matrix))
            valid_accuracy = (valid_conf_matrix[0, 0] + valid_conf_matrix[1, 1]) / total
            valid_specificity = valid_conf_matrix[0, 0] / (valid_conf_matrix[0, 0] + valid_conf_matrix[0, 1])
            valid_sensitivity = valid_conf_matrix[1, 1] / (valid_conf_matrix[1, 0] + valid_conf_matrix[1, 1])
            valid_f1_score = (2.0 * valid_conf_matrix[1, 1]) / (
                            2.0 * valid_conf_matrix[1, 1] + valid_conf_matrix[0, 1] + valid_conf_matrix[1, 0])
            # f1-score =2 * TP / (2 * TP + FP + FN)

        test_confusion_matrix = self.test_confusion_matrix
        total = sum(sum(test_confusion_matrix))
        test_accuracy = (test_confusion_matrix[0, 0] + test_confusion_matrix[1, 1]) * 1.0 / total
        test_specificity = test_confusion_matrix[0, 0] * 1.0 / (test_confusion_matrix[0, 0] + test_confusion_matrix[0, 1]) * 1.0
        test_sensitivity = test_confusion_matrix[1, 1] * 1.0 / (test_confusion_matrix[1, 0] + test_confusion_matrix[1, 1]) * 1.0
        test_f1_score = (2.0 * test_confusion_matrix[1, 1]) / (
                        2.0 * test_confusion_matrix[1, 1] + test_confusion_matrix[0, 1] + test_confusion_matrix[1, 0])
        # f1-score =2 * TP / (2 * TP + FP + FN)

        logging.info("confusion matrix.training: {}\n".format(str(train_conf_matrix)))
        logging.info("confusion matrix.test: {}\n".format(str(test_confusion_matrix)))
        if not self.skip_validation:
            logging.info("confusion matrix.validation: {}\n".format(str(valid_conf_matrix)))

        with open(self.output, mode='w') as csv_file:
            fieldnames = ['set', 'AUC-score', 'Sensitivity', 'Specificity', 'Accuracy', 'F1-score', 'Average-precision']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames, delimiter=' ')

            writer.writeheader()
            writer.writerow({'set': "training",'AUC-score': self.train_roc, 'Sensitivity':train_sensitivity, 'Specificity': train_specificity, 'Accuracy': train_accuracy, "F1-score": train_f1_score, "Average-precision": self.train_average_precision})

            writer.writerow({'set': "test", 'AUC-score': self.test_roc, 'Sensitivity': test_sensitivity,
                             'Specificity': test_specificity, 'Accuracy': test_accuracy, "F1-score": test_f1_score,"Average-precision": self.test_average_precision})
            if not self.skip_validation:
                writer.writerow({'set': "validation",'AUC-score': self.valid_roc, 'Sensitivity':valid_sensitivity,'Specificity': valid_specificity, 'Accuracy': valid_accuracy, "F1-score": valid_f1_score, "Average-precision": self.valid_average_precision})

    def create_edge_embeddings(self, edge_list, node2vector_map) -> \
            Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        This method finds embedding for edges of the graph. There are 4 ways to calculate edge embedding: Hadamard,
        Average, Weighted L1 and Weighted L2

        :param edge_list:
        :param node2vector_map: key:node, value: embedded vector
        # :param size_limit: Maximum number of edges that are embedded
        :return: list of embeddings for src, dst and edge itself
        """
        src_embs: List[List[float]] = []
        dst_embs: List[List[float]] = []
        edge_embs: List[List[float]] = []
        edge_embedding_method = self.edge_embedding_method
        for edge in edge_list:
            node1 = edge[0]
            node2 = edge[1]
            emb1 = node2vector_map[node1]
            emb2 = node2vector_map[node2]
            if edge_embedding_method == "hadamard":
                # Perform a Hadamard transform on the node embeddings.
                # This is a hadamard product of the node embedding for the two nodes
                edge_emb = np.multiply(emb1, emb2)
            elif edge_embedding_method == "average":
                # Perform a Average transform on the node embeddings.
                # This is a elementwise average of the node embedding for the two nodes
                edge_emb = np.add(emb1, emb2) / 2
            elif edge_embedding_method == "weightedL1":
                # Perform weightedL1 transform on the node embeddings.
                # WeightedL1 calculates the absolute value of difference of each element of the two nodes
                edge_emb = abs(emb1 - emb2)
            elif edge_embedding_method == "weightedL2":
                # Perform weightedL2 transform on the node embeddings.
                # WeightedL2 calculates the square of difference of each element of the two nodes
                edge_emb = np.power((emb1 - emb2), 2)
            else:
                logging.error("Enter hadamard, average, weightedL1, weightedL2")
                sys.exit(1)
            src_embs.append(emb1)
            dst_embs.append(emb2)
            edge_embs.append(edge_emb)
        src_embs = np.array(src_embs)
        dst_embs = np.array(dst_embs)
        edge_embs = np.array(edge_embs)
        return src_embs, dst_embs, edge_embs

    def output_edge_node_information(self):
        self.edge_node_information(self.pos_train_edges, "positive_training")
        self.edge_node_information(self.pos_test_edges, "positive_test")
        if (not self.skip_validation):
            self.edge_node_information(self.pos_valid_edges, "positive_validation")

    def edge_node_information(self, edge_list, group):
        """
        print the number of nodes and edges of each type of the graph
        :param edge_list: e.g.,  [('1','7), ('88','22'),...], either training or test
        :param group:
        :return:
        """
        num_edges = 0
        nodes = set()
        for edge in edge_list:
            num_edges += 1
            nodes.add(edge[0])
            nodes.add(edge[1])

        logging.info("##### edge/node diagnostics for {} #####".format(group))
        logging.info("{}: number of  edges : {}".format(group, num_edges))
        logging.info("{}: number of nodes : {}".format(group, len(nodes)))

