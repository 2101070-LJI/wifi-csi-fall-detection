from .cnn_lstm import CNNLSTM
from .blstm import BLSTM
from .cnn_gru import CNNGRU
from .attention_blstm import AttentionBLSTM
from .transformer import TransformerClassifier
from .resnet1d import ResNet1D

MODEL_REGISTRY = {
    "cnn_lstm": CNNLSTM,
    "blstm": BLSTM,
    "cnn_gru": CNNGRU,
    "attention_blstm": AttentionBLSTM,
    "transformer": TransformerClassifier,
    "resnet1d": ResNet1D,
}
