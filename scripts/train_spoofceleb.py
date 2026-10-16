"""Train a real two-class Mel-CNN using authorized SpoofCeleb train/development data."""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from sklearn.metrics import f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.custom_cnn import MelCNN, mel_image
from app.engine import decode_audio, split_windows


class AudioManifest(Dataset):
    def __init__(self, manifest: Path):
        with manifest.open(encoding='utf-8', newline='') as fh:
            self.entries = list(csv.DictReader(fh))
        if not self.entries:
            raise ValueError(f'Бос manifest: {manifest}')
        for row in self.entries:
            if row['label'] not in ('0','1'):
                raise ValueError(f'label 0/1 болуы керек: {row}')
            if not Path(row['path']).is_file():
                raise FileNotFoundError(f'Файл табылмады: {row["path"]}')

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, idx):
        row = self.entries[idx]
        audio = decode_audio(Path(row['path']).read_bytes())
        wave = split_windows(audio, count=1)[0]
        return torch.from_numpy(mel_image(wave)[None]), int(row['label'])


def epoch(net, loader, criterion, device, optimizer=None):
    training = optimizer is not None
    net.train(training)
    all_pred, all_true = [], []
    total_loss = 0.0
    for features, labels in loader:
        features, labels = features.to(device), labels.to(device)
        if training:
            optimizer.zero_grad()
        with torch.set_grad_enabled(training):
            logits = net(features)
            loss = criterion(logits, labels)
            if training:
                loss.backward()
                optimizer.step()
        total_loss += loss.item() * len(labels)
        all_pred.extend(logits.argmax(1).detach().cpu().tolist())
        all_true.extend(labels.detach().cpu().tolist())
    return total_loss / len(all_true), f1_score(all_true, all_pred, zero_division=0)


def train(args):
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    train_set, dev_set = AudioManifest(args.train), AudioManifest(args.dev)
    train_paths = {str(Path(r['path']).resolve()) for r in train_set.entries}
    dev_paths = {str(Path(r['path']).resolve()) for r in dev_set.entries}
    if train_paths & dev_paths:
        raise ValueError('Train/dev ішінде бірдей файлдар бар (data leakage).')
    # Show class balance clearly; original SpoofCeleb is not balanced.
    counts = np.bincount([int(r['label']) for r in train_set.entries], minlength=2)
    dev_counts = np.bincount([int(r['label']) for r in dev_set.entries], minlength=2)
    if min(counts) == 0 or min(dev_counts) == 0:
        raise ValueError('Train және dev ішінде екі класс та (0/1) болуы тиіс.')
    print('train:', counts.tolist(), 'dev:', dev_counts.tolist())
    device = torch.device('cuda' if torch.cuda.is_available() and not args.cpu else 'cpu')
    print('Есептеу құрылғысы:', device)
    loader = DataLoader(train_set, batch_size=args.batch, shuffle=True, num_workers=0)
    val_loader = DataLoader(dev_set, batch_size=args.batch, shuffle=False, num_workers=0)
    net = MelCNN().to(device)
    optimizer = torch.optim.Adam(net.parameters(), lr=args.lr)
    # Avoid rewarding the dominant spoof class only.
    weights = counts.sum() / (2 * counts.astype(float))
    criterion = torch.nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32,device=device))
    best = -1.0
    args.out.parent.mkdir(parents=True,exist_ok=True)
    for epoch_index in range(1,args.epochs+1):
        tr_loss, tr_f1 = epoch(net, loader, criterion, device, optimizer)
        dv_loss, dv_f1 = epoch(net, val_loader, criterion, device)
        print(f'{epoch_index}/{args.epochs} train loss={tr_loss:.3f} F1={tr_f1:.3f} | dev loss={dv_loss:.3f} F1={dv_f1:.3f}',flush=True)
        if dv_f1 > best:
            best = dv_f1
            ckpt = {
                'dataset': 'SpoofCeleb', 'model_family': 'MelCNN-v1',
                'label_mapping': {'bonafide':0, 'spoof':1},
                'state_dict': {k:v.cpu().detach() for k,v in net.state_dict().items()},
                'epoch': epoch_index, 'dev_f1': float(dv_f1), 'threshold':0.5,
                'train_samples':len(train_set), 'dev_samples':len(dev_set), 'seed':args.seed,
            }
            torch.save(ckpt,args.out)
            print('Checkpoint сақталды:',args.out,flush=True)
    print(f'Оқыту аяқталды. Best dev F1={best:.4f}. Бұл test нәтижесі емес.')


def main():
    p = argparse.ArgumentParser(description='SpoofCeleb train/dev -> CNN checkpoint')
    p.add_argument('--train', type=Path, default=ROOT / 'data' / 'train.csv')
    p.add_argument('--dev', type=Path, default=ROOT / 'data' / 'dev.csv')
    p.add_argument('--out', type=Path, default=ROOT/'models'/'spoofceleb_cnn.pt')
    p.add_argument('--epochs', type=int, default=8)
    p.add_argument('--batch', type=int, default=16)
    p.add_argument('--lr', type=float, default=1e-3)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--cpu', action='store_true')
    args = p.parse_args()
    if args.epochs < 1 or args.batch < 1:
        p.error('epochs and batch must be positive')
    train(args)

if __name__ == '__main__':
    main()
