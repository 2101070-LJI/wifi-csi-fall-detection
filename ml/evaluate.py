"""
모델 평가 스크립트 — 정확도, 혼동행렬, 추론 속도

사용법:
    python ml/evaluate.py --model cnn_lstm --weights models/cnn_lstm.pth --data data/dataset.npz
    python ml/evaluate.py --compare  # 모든 모델 비교 (models/ 디렉토리 내 .pth 파일)
"""

import argparse
import os
import time
import numpy as np
import torch
from torch.utils.data import DataLoader

from ml.train import CSIDataset, CLASSES, N_CLASSES
from ml.models import MODEL_REGISTRY

FALL_INDICES = [CLASSES.index("fall")]
LIE_DOWN_IDX = CLASSES.index("lie down")


def confusion_matrix(y_true, y_pred, n_classes):
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t][p] += 1
    return cm


def print_confusion_matrix(cm, class_names):
    header = "          " + "  ".join(f"{c[:6]:>6}" for c in class_names)
    print(header)
    for i, row in enumerate(cm):
        row_str = "  ".join(f"{v:6d}" for v in row)
        print(f"{class_names[i][:10]:<10} {row_str}")


def measure_inference_speed(model, device, n_features=30, window_size=100, n_trials=100):
    """단일 샘플 추론 속도 측정 (ms)"""
    model.eval()
    dummy = torch.randn(1, window_size, n_features).to(device)
    # warmup
    with torch.no_grad():
        for _ in range(10):
            model(dummy)
    times = []
    with torch.no_grad():
        for _ in range(n_trials):
            t0 = time.perf_counter()
            model(dummy)
            times.append((time.perf_counter() - t0) * 1000)
    return np.mean(times), np.std(times)


def fall_vs_liedown_accuracy(y_true, y_pred):
    """fall vs lie_down 구분율 계산 (핵심 지표)"""
    mask = np.isin(y_true, FALL_INDICES + [LIE_DOWN_IDX])
    if mask.sum() == 0:
        return float("nan")
    y_t = y_true[mask]
    y_p = y_pred[mask]
    return (y_t == y_p).mean()


@torch.no_grad()
def run_evaluation(model, loader, device):
    model.eval()
    all_preds = []
    all_labels = []
    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        logits = model(X_batch)
        preds = logits.argmax(dim=1).cpu().numpy()
        all_preds.append(preds)
        all_labels.append(y_batch.numpy())
    return np.concatenate(all_labels), np.concatenate(all_preds)


def evaluate_model(model_name, weights_path, data_path, n_features=30, window_size=100):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    dataset = CSIDataset(data_path)
    loader = DataLoader(dataset, batch_size=64)

    model_cls = MODEL_REGISTRY[model_name]
    model = model_cls(input_size=n_features, num_classes=N_CLASSES).to(device)
    model.load_state_dict(torch.load(weights_path, map_location=device))

    y_true, y_pred = run_evaluation(model, loader, device)
    overall_acc = (y_true == y_pred).mean()
    fall_acc = fall_vs_liedown_accuracy(y_true, y_pred)
    mean_ms, std_ms = measure_inference_speed(model, device, n_features, window_size)

    cm = confusion_matrix(y_true, y_pred, N_CLASSES)

    print(f"\n{'='*60}")
    print(f"모델: {model_name}")
    print(f"{'='*60}")
    print(f"전체 정확도:               {overall_acc:.4f} ({overall_acc*100:.2f}%)")
    print(f"fall vs lie_down 구분율:      {fall_acc:.4f} ({fall_acc*100:.2f}%)")
    print(f"추론 속도 (단일 샘플):     {mean_ms:.2f} ± {std_ms:.2f} ms")
    print(f"RPi 200ms 기준 충족:       {'✓' if mean_ms < 200 else '✗'}")
    print(f"\n혼동행렬:")
    print_confusion_matrix(cm, CLASSES)

    return {
        "model": model_name,
        "overall_acc": float(overall_acc),
        "fall_vs_lie_acc": float(fall_acc) if not np.isnan(fall_acc) else 0.0,
        "inference_ms": float(mean_ms),
    }


def compare_all_models(save_dir, data_path, n_features=30):
    results = []
    for fname in sorted(os.listdir(save_dir)):
        if not fname.endswith(".pth"):
            continue
        model_name = fname[:-4]
        if model_name not in MODEL_REGISTRY:
            continue
        weights_path = os.path.join(save_dir, fname)
        r = evaluate_model(model_name, weights_path, data_path, n_features)
        results.append(r)

    if not results:
        print("평가할 .pth 파일이 없습니다.")
        return

    print(f"\n{'='*60}")
    print("모델 비교 요약")
    print(f"{'='*60}")
    header = f"{'모델':<20} {'전체 정확도':>12} {'fall 구분율':>12} {'추론(ms)':>10} {'기준 충족':>8}"
    print(header)
    print("-" * 64)
    for r in results:
        ok = "✓" if r["inference_ms"] < 200 else "✗"
        print(
            f"{r['model']:<20} {r['overall_acc']:>12.4f} "
            f"{r['fall_vs_lie_acc']:>12.4f} {r['inference_ms']:>10.2f} {ok:>8}"
        )

    # 최종 모델 선정: fall 구분율 > 95% AND 추론 < 200ms → 정확도 기준
    candidates = [r for r in results if r["fall_vs_lie_acc"] >= 0.95 and r["inference_ms"] < 200]
    if candidates:
        best = max(candidates, key=lambda r: r["overall_acc"])
        print(f"\n최종 선정 모델: {best['model']} (fall 구분율={best['fall_vs_lie_acc']:.4f}, "
              f"추론={best['inference_ms']:.2f}ms, 전체 정확도={best['overall_acc']:.4f})")
    else:
        # 속도 기준 미충족 시 경량 모델 우선
        speed_ok = [r for r in results if r["inference_ms"] < 200]
        if speed_ok:
            best = max(speed_ok, key=lambda r: r["fall_vs_lie_acc"])
        else:
            best = min(results, key=lambda r: r["inference_ms"])
        print(f"\n[경고] 두 조건 동시 충족 모델 없음. 차선책: {best['model']}")


def main():
    parser = argparse.ArgumentParser(description="CSI 낙상 감지 모델 평가")
    parser.add_argument("--model", choices=list(MODEL_REGISTRY.keys()), default=None)
    parser.add_argument("--weights", default=None, help="모델 가중치 .pth 경로")
    parser.add_argument("--data", default="data/dataset.npz")
    parser.add_argument("--compare", action="store_true", help="models/ 내 전체 모델 비교")
    parser.add_argument("--save_dir", default="models")
    parser.add_argument("--n_features", type=int, default=30)
    parser.add_argument("--window_size", type=int, default=100)
    args = parser.parse_args()

    if args.compare:
        compare_all_models(args.save_dir, args.data, args.n_features)
    elif args.model and args.weights:
        evaluate_model(args.model, args.weights, args.data, args.n_features, args.window_size)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
