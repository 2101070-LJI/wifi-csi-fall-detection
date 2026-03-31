import torch
import torch.nn as nn


class CNNGRU(nn.Module):
    def __init__(self, input_size: int = 30, num_classes: int = 7,
                 cnn_channels: int = 64, gru_hidden: int = 64, num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv1d(input_size, cnn_channels, kernel_size=3, padding=1),
            nn.BatchNorm1d(cnn_channels),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.gru = nn.GRU(cnn_channels, gru_hidden, num_layers=num_layers,
                          batch_first=True, dropout=dropout, bidirectional=True)
        self.fc = nn.Linear(gru_hidden * 2, num_classes)

    def forward(self, x):          # x: (B, T, C)
        x = x.permute(0, 2, 1)    # (B, C, T)
        x = self.cnn(x)            # (B, 64, T)
        x = x.permute(0, 2, 1)    # (B, T, 64)
        _, h = self.gru(x)
        h = torch.cat([h[-2], h[-1]], dim=1)  # (B, 128)
        return self.fc(h)          # (B, num_classes)
