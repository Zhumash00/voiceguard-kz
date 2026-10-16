"""Prepare balanced training/dev/eval CSV manifests from locally authorized SpoofCeleb files.

Official metadata may differ by release. Use --path-column and --label-column to select
its columns explicitly if auto detection is not possible. This script never downloads audio.
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path

PATH_FIELDS = ('path','filepath','file_path','audio_path','relative_path','file','filename','file_name','utterance_path')
LABEL_FIELDS = ('label','class','target','spoof_label','cm_label')


def column(fields: list[str], explicit: str|None, fallbacks: tuple[str,...], name: str) -> str:
    if explicit:
        if explicit not in fields:
            raise ValueError(f'{name} бағаны жоқ: {explicit}; бар бағандар: {fields}')
        return explicit
    mapping = {f.lower().strip(): f for f in fields}
    for choice in fallbacks:
        if choice in mapping:
            return mapping[choice]
    raise ValueError(f'{name} бағаны анықталмады. --{name}-column жазыңыз. CSV бағандары: {fields}')


def label_to_int(value: str) -> int:
    val = value.strip().lower()
    if val in ('spoof','fake','synthetic','deepfake','1'):
        return 1
    if val in ('bonafide','bona_fide','bona fide','real','genuine','0'):
        return 0
    raise ValueError(f'Белгісіз label: {value!r}. Spoof=1, bonafide=0.')


def resolve_audio(root: Path, text: str, split: str) -> Path|None:
    val = text.strip().replace('\\','/')
    if not val:
        return None
    rel = Path(val)
    if rel.is_absolute():
        return rel if rel.is_file() else None
    candidates = [root / rel, root / 'spoofceleb' / rel, root / 'flac' / rel,
                  root / 'flac' / split / rel, root / split / rel]
    # Some metadata rows name only utterance IDs, not filenames.
    if not rel.suffix:
        candidates += [p.with_suffix('.flac') for p in candidates]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def build_manifest(root: Path, metadata: Path, out: Path, split: str,
                   limit_per_class: int|None = None, seed: int = 42,
                   path_column: str|None = None, label_column: str|None = None) -> tuple[int,int,dict]:
    with metadata.open('r', encoding='utf-8-sig', newline='') as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError('CSV тақырып жолы жоқ.')
        path_field = column(reader.fieldnames, path_column, PATH_FIELDS, 'path')
        label_field = column(reader.fieldnames, label_column, LABEL_FIELDS, 'label')
        buckets = {0: [], 1: []}
        missing = 0
        seen = set()
        for rec in reader:
            label = label_to_int(rec[label_field])
            filepath = resolve_audio(root, rec[path_field], split)
            if filepath is None:
                missing += 1
                continue
            if str(filepath) in seen:
                continue
            seen.add(str(filepath))
            buckets[label].append((str(filepath), label, filepath.stem))
    rng = random.Random(seed)
    chosen = []
    for label in (0,1):
        rng.shuffle(buckets[label])
        chosen.extend(buckets[label][:limit_per_class] if limit_per_class else buckets[label])
    if not chosen:
        raise ValueError('Аудио файлдары табылмады. --root және metadata бағандарын тексеріңіз.')
    if not buckets[0] or not buckets[1]:
        raise ValueError('SpoofCeleb моделін оқыту үшін bonafide және spoof екеуі де қажет.')
    rng.shuffle(chosen)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(('path','label','utterance_id'))
        w.writerows(chosen)
    return len(chosen), missing, dict(Counter(row[1] for row in chosen))


def main():
    parser = argparse.ArgumentParser(description='SpoofCeleb metadata CSV -> path,label manifest')
    parser.add_argument('--root', type=Path, required=True, help='Extracted SpoofCeleb root (flac/ and metadata/)')
    parser.add_argument('--split', choices=('train','development','evaluation'), default='train')
    parser.add_argument('--metadata', type=Path, help='Defaults to ROOT/metadata/SPLIT.csv')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--limit-per-class', type=int, default=1000,
                        help='0 = entire split; default=1000 for a small experimental run')
    parser.add_argument('--path-column')
    parser.add_argument('--label-column')
    args = parser.parse_args()
    if args.limit_per_class < 0:
        parser.error('--limit-per-class must be >= 0')
    root = args.root.resolve()
    metadata = args.metadata or root / 'metadata' / f'{args.split}.csv'
    if not metadata.is_file():
        parser.error(f'Metadata жоқ: {metadata}. Official SpoofCeleb split CSV беріңіз.')
    n, missing, distribution = build_manifest(root, metadata, args.out, args.split,
         args.limit_per_class or None, path_column=args.path_column, label_column=args.label_column)
    print('Сақталған:', args.out, '| жазбалар:', n, '| кластар:', distribution, '| файл жоқ:',missing)
    print('Ескерту: бұл тек деректерді дайындау. Модель әлі оқытылған жоқ.')

if __name__ == '__main__':
    main()
