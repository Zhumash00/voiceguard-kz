"""Train optional Mel-CNN on manifest CSV: no evaluation data leakage."""
from __future__ import annotations
import argparse
import csv
import random
import sys
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.custom_cnn import MelCNN, mel_image
from app.engine import decode_audio, split_windows

class AudioManifest(Dataset):
    def __init__(self, csv_path):
        with open(csv_path, newline='', encoding='utf8') as f:
            self.entries = list(csv.DictReader(f))
        if not self.entries: raise ValueError('Manifest бос.')
    def __len__(self): return len(self.entries)
    def __getitem__(self, idx):
        row = self.entries[idx]
        audio = decode_audio(Path(row['path']).read_bytes())
        wave = split_windows(audio, count=1)[0]
        return torch.from_numpy(mel_image(wave)[None]), int(row['label'])

def epoch(model, loader, criterion, opt=None):
    train = opt is not None
    model.train(train)
    total_loss = 0.0
    total_ok = 0
    count = 0
    for x, y in loader:
        if train: opt.zero_grad()
        with torch.set_grad_enabled(train):
            logits = model(x)
            loss = criterion(logits, y)
            if train:
                loss.backward()
                opt.step()
        total_loss += float(loss.item()) * len(y)
        total_ok += int((logits.argmax(1) == y).sum())
        count += len(y)
    return total_loss / max(count, 1), total_ok / max(count, 1)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--train', type=Path, required=True, help='CSV: path,label (0 bona fide, 1 spoof)')
    p.add_argument('--dev', type=Path, required=True, help='Different files/speakers than training')
    p.add_argument('--epochs', type=int, default=8)
    p.add_argument('--batch', type=int, default=16)
    p.add_argument('--lr', type=float, default=1e-3)
    p.add_argument('--out', type=Path, default=ROOT/'models'/'custom_cnn.pt')
    a = p.parse_args()
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    train = AudioManifest(a.train)
    dev = AudioManifest(a.dev)
    train_paths = {Path(e['path']).resolve() for e in train.entries}
    dev_paths = {Path(e['path']).resolve() for e in dev.entries}
    overlap = train_paths & dev_paths
    if overlap: raise ValueError(f'Train/dev leakage! Бірдей файлдар: {len(overlap)}')
    loader = DataLoader(train, batch_size=a.batch, shuffle=True, num_workers=0)
    val_loader = DataLoader(dev, batch_size=a.batch, num_workers=0)
    model = MelCNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=a.lr)
    loss_fn = torch.nn.CrossEntropyLoss()
    best = -1
    a.out.parent.mkdir(exist_ok=True, parents=True)
    for i in range(a.epochs):
        tr_loss, tr_acc = epoch(model, loader, loss_fn, optimizer)
        dv_loss, dv_acc = epoch(model, val_loader, loss_fn)
        print(f'{i+1:02}/{a.epochs} train: loss={tr_loss:.3f}, acc={tr_acc:.3f} | dev: loss={dv_loss:.3f}, acc={dv_acc:.3f}')
        if dv_acc > best:
            best = dv_acc
            torch.save({'state_dict': model.state_dict(), 'epoch': i + 1, 'dev_acc': dv_acc}, a.out)
    print('CNN дайын:', a.out, '(dev accuracy =', round(best, 3), ')')
    print('Ескерту: accuracy өздігінен телефон қоңырауларындағы тиімділікті дәлелдемейді.')
