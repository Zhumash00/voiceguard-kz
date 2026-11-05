"""Fetch the fixed multilingual Whisper tiny model for offline CPU language ID."""
from pathlib import Path
from huggingface_hub import snapshot_download

root = Path(__file__).resolve().parents[1]
dest = root / 'models' / 'whisper-tiny'
dest.mkdir(parents=True,exist_ok=True)
print('Whisper Tiny көптілді моделі жүктелуде…')
snapshot_download(repo_id='Systran/faster-whisper-tiny', local_dir=str(dest),
                  allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.*','preprocessor_config.json'])
assert (dest / 'model.bin').is_file()
print('Дайын:',dest)
