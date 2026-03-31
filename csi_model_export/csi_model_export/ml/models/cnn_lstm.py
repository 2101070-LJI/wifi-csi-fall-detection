import torch
import torch.nn as nn


class CNNLSTM(nn.Module):
    def __init__(self, input_size: int = 30, num_classes: int = 7,
                 cnn_channels: int = 64, lstm_hidden: int = 128, num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv1d(input_size, cnn_channels, kernel_size=3, padding=1),
            nn.BatchNorm1d(cnn_channels),
            nn.ReLU(),
            nn.Conv1d(cnn_channels, cnn_channels, kernel_size=3, padding=1),
            nn.BatchNorm1d(cnn_channels),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.lstm = nn.LSTM(cnn_channels, lstm_hidden, num_layers=num_layers,
                            batch_first=True, dropout=dropout, bidirectional=False)
        self.fc = nn.Linear(lstm_hidden, num_classes)

    def forward(self, x):                       # (B, T, C)
        x = x.permute(0, 2, 1)                 # (B, C, T) for Conv1d
        x = self.cnn(x)                         # (B, cnn_channels, T)
        x = x.permute(0, 2, 1)                 # (B, T, cnn_channels)
        _, (h, _) = self.lstm(x)
        return self.fc(h[-1])                   # (B, num_classes)
