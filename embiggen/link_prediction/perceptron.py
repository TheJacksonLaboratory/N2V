"""Class for creating a Perceptron model for link prediction tasks."""
from tensorflow.keras.layers import Dense, Layer
from .link_prediction_model import LinkPredictionModel


class Perceptron(LinkPredictionModel):

    def _build_model_body(self, input_layer: Layer) -> Layer:
        """Build new model body for link prediction."""
        return Dense(1, activation="sigmoid")(input_layer)
