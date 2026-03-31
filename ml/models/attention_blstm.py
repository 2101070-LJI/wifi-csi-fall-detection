import torch
import torch.nn as nn
import torch.nn.functional as F


class AttentionBLSTM(nn.Module):
    def __init__(self, input_size: int = 30, num_classes: int = 7,
                 hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers=num_layers,
                            batch_first=True, dropout=dropout, bidirectional=True)
        self.attn_w = nn.Linear(hidden_size * 2, 1)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size * 2, num_classes)

    def forward(self, x):                       # (B, T, C)
        out, _ = self.lstm(x)                  # (B, T, H*2)
        scores = self.attn_w(out).squeeze(-1)  # (B, T)
        weights = F.softmax(scores, dim=1).unsqueeze(-1)  # (B, T, 1)
        context = (out * weights).sum(dim=1)   # (B, H*2)
        return self.fc(self.dropout(context))
