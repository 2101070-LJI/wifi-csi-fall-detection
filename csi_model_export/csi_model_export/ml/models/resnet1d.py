import torch
import torch.nn as nn


class ResBlock1D(nn.Module):
    def __init__(self, channels: int, kernel_size: int = 3, dropout: float = 0.2):
        super().__init__()
        pad = kernel_size // 2
        self.block = nn.Sequential(
            nn.Conv1d(channels, channels, kernel_size, padding=pad),
            nn.BatchNorm1d(channels),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Conv1d(channels, channels, kernel_size, padding=pad),
            nn.BatchNorm1d(channels),
        )
        self.relu = nn.ReLU()

    def forward(self, x):
        return self.relu(x + self.block(x))


class ResNet1D(nn.Module):
    def __init__(self, input_size: int = 30, num_classes: int = 7,
                 base_channels: int = 64, num_blocks: int = 3, dropout: float = 0.2):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv1d(input_size, base_channels, kernel_size=7, padding=3),
            nn.BatchNorm1d(base_channels),
            nn.ReLU(),
        )
        self.blocks = nn.Sequential(*[ResBlock1D(base_channels, dropout=dropout) for _ in range(num_blocks)])
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(base_channels, num_classes)

    def forward(self, x):                       # (B, T, C)
        x = x.permute(0, 2, 1)                 # (B, C, T)
        x = self.stem(x)
        x = self.blocks(x)
        x = self.pool(x).squeeze(-1)
        return self.fc(x)
