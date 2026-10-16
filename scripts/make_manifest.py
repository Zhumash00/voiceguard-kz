"""Turn ASVspoof 2019 LA protocol into path,label CSV for supervised train/eval."""
from __future__ import annotations
import argparse
import csv
from pathlib import Path


def make_manifest(protocol: Path, audio_dir: Path, out: Path, ext: str = '.flac') -> tuple[int, int]:
    records = []
    missing = 0
    for line in protocol.read_text(encoding='utf8').splitlines():
        tokens = line.split()
        if len(tokens) < 5 or tokens[-1] not in ('spoof', 'bonafide'):
            continue
        # ASVspoof2019.LA.cm.train.trn: speaker file - attack label
        name = tokens[1]
        fp = audio_dir / f'{name}{ext}'
        if not fp.is_file():
            missing += 1
            continue
        records.append((str(fp.resolve()), 1 if tokens[-1] == 'spoof' else 0, name))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['path', 'label', 'utterance_id'])
        writer.writerows(records)
    return len(records), missing

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--audio-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ext', default='.flac')
    a = p.parse_args()
    n, missing = make_manifest(a.protocol, a.audio_dir, a.output, a.ext)
    print(f'{n} жазба сақталды. Табылмаған аудиолар: {missing}')
