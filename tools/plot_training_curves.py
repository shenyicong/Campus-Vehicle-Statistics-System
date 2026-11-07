"""从 Ultralytics results.csv 生成训练曲线图（课程设计报告素材）。

用法:
  python tools/plot_training_curves.py
  python tools/plot_training_curves.py --csv models/train_results.csv --out docs/training_curves.png

图内文字用英文，避免 matplotlib 缺中文字体出现方块。
"""
import argparse
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description="生成训练曲线图")
    ap.add_argument("--csv", default=os.path.join(PROJECT_DIR, "models", "train_results.csv"))
    ap.add_argument("--out", default=os.path.join(PROJECT_DIR, "docs", "training_curves.png"))
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        raise SystemExit("训练记录不存在: " + args.csv)

    with open(args.csv, encoding="utf-8-sig") as f:
        rows = [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(f)]
    if not rows:
        raise SystemExit("训练记录为空")

    ep = [int(float(r["epoch"])) for r in rows]

    def col(key):
        return [float(r[key]) for r in rows if r.get(key) not in (None, "")]

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), dpi=150)
    fig.suptitle("YOLO11n training curves - 4-class campus vehicle detection",
                 fontsize=13)

    ax = axes[0][0]
    ax.plot(ep, col("metrics/mAP50(B)"), color="#185FA5", lw=1.8, label="mAP50")
    ax.plot(ep, col("metrics/mAP50-95(B)"), color="#1D9E75", lw=1.8, label="mAP50-95")
    ax.set_title("Validation mAP", fontsize=11)
    ax.set_xlabel("epoch"); ax.set_ylabel("mAP")
    ax.grid(alpha=0.3); ax.legend(fontsize=9)

    ax = axes[0][1]
    ax.plot(ep, col("metrics/precision(B)"), color="#BA7517", lw=1.8, label="precision")
    ax.plot(ep, col("metrics/recall(B)"), color="#D4537E", lw=1.8, label="recall")
    ax.set_title("Validation precision / recall", fontsize=11)
    ax.set_xlabel("epoch"); ax.set_ylabel("score")
    ax.grid(alpha=0.3); ax.legend(fontsize=9)

    ax = axes[1][0]
    for key, color, label in [("train/box_loss", "#185FA5", "box"),
                              ("train/cls_loss", "#D85A30", "cls"),
                              ("train/dfl_loss", "#7F77DD", "dfl")]:
        ax.plot(ep, col(key), color=color, lw=1.5, label=label)
    ax.set_title("Training loss", fontsize=11)
    ax.set_xlabel("epoch"); ax.set_ylabel("loss")
    ax.grid(alpha=0.3); ax.legend(fontsize=9)

    ax = axes[1][1]
    for key, color, label in [("val/box_loss", "#185FA5", "box"),
                              ("val/cls_loss", "#D85A30", "cls"),
                              ("val/dfl_loss", "#7F77DD", "dfl")]:
        ax.plot(ep, col(key), color=color, lw=1.5, label=label)
    ax.set_title("Validation loss", fontsize=11)
    ax.set_xlabel("epoch"); ax.set_ylabel("loss")
    ax.grid(alpha=0.3); ax.legend(fontsize=9)

    for ax in axes.flat:
        ax.set_xlim(ep[0], ep[-1])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    last = rows[-1]
    fig.text(0.5, 0.012,
             "final: mAP50=%s  mAP50-95=%s  precision=%s  recall=%s  |  %d epochs, 298 images" % (
                 last.get("metrics/mAP50(B)", "-"), last.get("metrics/mAP50-95(B)", "-"),
                 last.get("metrics/precision(B)", "-"), last.get("metrics/recall(B)", "-"),
                 len(rows)),
             ha="center", fontsize=9, color="#555555")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    fig.savefig(args.out, facecolor="white")
    plt.close(fig)
    print("已生成: %s" % args.out)
    print("轮数=%d  末轮 mAP50=%s  mAP50-95=%s" %
          (len(rows), last.get("metrics/mAP50(B)"), last.get("metrics/mAP50-95(B)")))


if __name__ == "__main__":
    main()
