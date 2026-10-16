"""Evaluate offline files from a held-out CSV, compute EER and standard metrics."""
from __future__ import annotations
import argparse
import csv
import sys
from pathlib import Path
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_curve
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.engine import detector, decode_audio


def eer(y, score):
    fpr, tpr, _ = roc_curve(y, score, pos_label=1)
    fnr = 1 - tpr
    idx = np.argmin(np.abs(fpr - fnr))
    return float((fpr[idx] + fnr[idx]) / 2)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--model', choices=['spoofceleb'], default='spoofceleb')
    p.add_argument('--scores-out', type=Path)
    a = p.parse_args()
    with a.manifest.open(encoding='utf8', newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows: raise SystemExit('CSV бос.')
    true, pred, scores, output = [], [], [], []
    for i, row in enumerate(rows):
        prob = detector.predict(decode_audio(Path(row['path']).read_bytes()), a.model)['score']
        label = int(row['label'])
        true.append(label); pred.append(int(prob >= .5)); scores.append(prob)
        output.append({'path': row['path'], 'label': label, 'spoof_score': prob})
        if (i+1)%100==0: print(i+1, '/', len(rows))
    pr, rec, f1, _ = precision_recall_fscore_support(true, pred, average='binary', zero_division=0)
    print(f'n={len(true)} accuracy={accuracy_score(true, pred):.4f} precision={pr:.4f} recall={rec:.4f} F1={f1:.4f}')
    if len(set(true)) == 2: print(f'EER={eer(true, scores)*100:.2f}%')
    else: print('EER үшін екі класс та қажет.')
    if a.scores_out:
        a.scores_out.parent.mkdir(parents=True, exist_ok=True)
        with a.scores_out.open('w', encoding='utf8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['path', 'label', 'spoof_score'])
            writer.writeheader(); writer.writerows(output)
