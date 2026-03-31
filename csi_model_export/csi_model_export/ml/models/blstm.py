import torch
import torch.nn as nn


class BLSTM(nn.Module):
    def __init__(self, input_size: int = 30, num_classes: int = 7,
                 hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers=num_layers,
                            batch_first=True, dropout=dropout, bidirectional=True)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size * 2, num_classes)

    def forward(self, x):                       # (B, T, C)
        _, (h, _) = self.lstm(x)
        h = torch.cat([h[-2], h[-1]], dim=1)   # 양방향 마지막 hidden
        return self.fc(self.dropout(h))
