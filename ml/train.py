"""
모델 학습 스크립트

사용법:
    python ml/train.py --model cnn_lstm --epochs 50 --batch_size 32

모델 옵션: cnn_lstm, blstm, cnn_gru, attention_blstm, transformer, resnet1d
"""

import argparse
import os
import time
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, random_split

from ml.models import MODEL_REGISTRY

# 클래스 정의 — CSI-HAR-Dataset 기준 7클래스
CLASSES = [
    "bend",
    "fall",
    "lie down",
    "run",
    "sitdown",
    "standup",
    "walk",
]
N_CLASSES = len(CLASSES)


class CSIDataset(Dataset):
    """
    전처리된 .npz 파일 로드.
    npz 파일: {"X": (N, window_size, n_features), "y": (N,)}
    """

    def __init__(self, npz_path: str):
        data = np.load(npz_path)
        self.X = torch.tensor(data["X"], dtype=torch.float32)
        self.y = torch.tensor(data["y"], dtype=torch.long)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


def train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0
    for X_batch, y_batch in loader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        optimizer.zero_grad()
        logits = model(X_batch)
        loss = criterion(logits, y_batch)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(y_batch)
        correct += (logits.argmax(dim=1) == y_batch).sum().item()
        total += len(y_batch)
    return total_loss / total, correct / total


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    for X_batch, y_batch in loader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        logits = model(X_batch)
        loss = criterion(logits, y_batch)
        total_loss += loss.item() * len(y_batch)
        correct += (logits.argmax(dim=1) == y_batch).sum().item()
        total += len(y_batch)
    return total_loss / total, correct / total


def main():
    parser = argparse.ArgumentParser(description="CSI 낙상 감지 모델 학습")
    parser.add_argument("--model", choices=list(MODEL_REGISTRY.keys()), default="cnn_lstm")
    parser.add_argument("--data", default="data/dataset.npz", help="전처리된 npz 파일 경로")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--val_ratio", type=float, default=0.2)
    parser.add_argument("--save_dir", default="models")
    parser.add_argument("--n_features", type=int, default=30)
    parser.add_argument("--window_size", type=int, default=100)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # 데이터 로드
    dataset = CSIDataset(args.data)
    n_val = int(len(dataset) * args.val_ratio)
    n_train = len(dataset) - n_val
    train_set, val_set = random_split(dataset, [n_train, n_val])
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=args.batch_size)
    print(f"Train: {n_train}  Val: {n_val}")

    # 모델 초기화
    model_cls = MODEL_REGISTRY[args.model]
    model = model_cls(input_size=args.n_features, num_classes=N_CLASSES).to(device)
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Model: {args.model}  Params: {n_params:,}")

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_val_acc = 0.0
    os.makedirs(args.save_dir, exist_ok=True)
    save_path = os.path.join(args.save_dir, f"{args.model}.pth")

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        scheduler.step()
        elapsed = time.time() - t0

        print(
            f"Epoch {epoch:3d}/{args.epochs} | "
            f"train_loss={train_loss:.4f} acc={train_acc:.4f} | "
            f"val_loss={val_loss:.4f} acc={val_acc:.4f} | "
            f"{elapsed:.1f}s"
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), save_path)
            print(f"  → 저장: {save_path} (val_acc={val_acc:.4f})")

    print(f"\n학습 완료. 최고 val_acc: {best_val_acc:.4f}")
    print(f"모델 저장 위치: {save_path}")


if __name__ == "__main__":
    main()
