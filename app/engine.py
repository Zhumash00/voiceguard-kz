"""SpoofCeleb-trained Mel-CNN inference. An absent checkpoint never produces a prediction."""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPOOFCELEB_FILE = Path(os.getenv('VOICEGUARD_SPOOFCELEB_PATH', str(ROOT / 'models' / 'spoofceleb_cnn.pt')))
SAMPLE_RATE = 16000
WINDOW = 64600
MAX_AUDIO_SEC = 30
MAX_WINDOWS = 6
DATASET_URL = 'https://huggingface.co/datasets/jungjee/spoofceleb'

class AudioError(Exception):
    pass


def decode_audio(file_bytes: bytes) -> np.ndarray:
    """Decode user audio to float32 mono 16 kHz, without persisting to disk."""
    if not shutil.which('ffmpeg'):
        raise AudioError('FFmpeg орнатылмаған. README нұсқаулығын қараңыз.')
    cmd = ['ffmpeg', '-nostdin', '-v', 'error', '-i', 'pipe:0', '-t', str(MAX_AUDIO_SEC),
           '-ar', str(SAMPLE_RATE), '-ac', '1', '-f', 'f32le', 'pipe:1']
    try:
        p = subprocess.run(cmd, input=file_bytes, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=35, check=False)
    except subprocess.TimeoutExpired as exc:
        raise AudioError('Аудионы өңдеу уақыты асып кетті.') from exc
    if p.returncode != 0 or not p.stdout:
        raise AudioError('Аудио файлын оқу мүмкін болмады. Басқа файлды жүктеп көріңіз.')
    audio = np.frombuffer(p.stdout, dtype='<f4').copy()
    if len(audio) < int(0.35 * SAMPLE_RATE):
        raise AudioError('Аудио тым қысқа. Кемінде 0,35 секунд сөйлеу жүктеңіз.')
    if not np.isfinite(audio).all():
        raise AudioError('Аудиода жарамсыз мәндер бар.')
    if np.max(np.abs(audio)) < 1e-5:
        raise AudioError('Жазбада дыбыс анықталмады.')
    return np.clip(audio, -1.0, 1.0)


def split_windows(audio: np.ndarray, count: int = MAX_WINDOWS) -> np.ndarray:
    if len(audio) <= WINDOW:
        if len(audio) < WINDOW:
            audio = np.tile(audio, int(np.ceil(WINDOW / len(audio))))[:WINDOW]
        return np.asarray([audio], dtype=np.float32)
    total = min(count, max(2, int(np.ceil(len(audio) / WINDOW))))
    positions = np.linspace(0, len(audio) - WINDOW, total, dtype=np.int64)
    return np.ascontiguousarray(np.stack([audio[k:k + WINDOW] for k in positions]).astype(np.float32))


class Detector:
    def __init__(self):
        self._net = None
        self._threshold = 0.5
        self._metadata = {}
        self._lock = threading.Lock()

    def status(self) -> dict:
        return {
            'spoofceleb': SPOOFCELEB_FILE.is_file(),
            'model_name': 'SpoofCeleb Mel-CNN (деректермен оқытылатын)',
            'model_source': DATASET_URL,
            'model_checkpoint': SPOOFCELEB_FILE.name,
            'ffmpeg': shutil.which('ffmpeg') is not None,
            'dataset': 'SpoofCeleb',
        }

    def _load_model(self):
        if not SPOOFCELEB_FILE.is_file():
            raise FileNotFoundError(
                'SpoofCeleb моделі әлі оқытылмаған. Деректерді рұқсатпен жүктеп, '
                'scripts/train_spoofceleb.py командасын орындаңыз. README.md нұсқаулығын қараңыз.'
            )
        if self._net is None:
            with self._lock:
                if self._net is None:
                    try:
                        import torch
                    except ImportError as exc:
                        raise RuntimeError('PyTorch қажет: pip install -r requirements.txt') from exc
                    from .custom_cnn import MelCNN
                    # Only trusted local files; weights_only avoids loading pickled arbitrary objects.
                    checkpoint = torch.load(SPOOFCELEB_FILE, map_location='cpu', weights_only=True)
                    if checkpoint.get('dataset') != 'SpoofCeleb' or checkpoint.get('model_family') != 'MelCNN-v1':
                        raise RuntimeError('Checkpoint SpoofCeleb MelCNN-v1 моделіне сәйкес емес.')
                    if checkpoint.get('label_mapping') != {'bonafide': 0, 'spoof': 1}:
                        raise RuntimeError('Checkpoint класстарының реті сәйкес емес.')
                    net = MelCNN()
                    net.load_state_dict(checkpoint['state_dict'], strict=True)
                    net.eval()
                    self._net = net
                    self._threshold = float(checkpoint.get('threshold', .5))
                    self._metadata = {
                        'epochs': int(checkpoint.get('epoch', 0)),
                        'dev_f1': round(float(checkpoint.get('dev_f1', 0)), 4),
                    }
        return self._net

    def predict(self, audio: np.ndarray, model: str = 'spoofceleb') -> dict:
        if model != 'spoofceleb':
            raise ValueError('Бұл нұсқада тек SpoofCeleb негізінде оқытылған модель қолданылады.')
        net = self._load_model()
        windows = split_windows(audio)
        import torch
        from .custom_cnn import mel_image
        with torch.inference_mode():
            feats = torch.from_numpy(np.stack([mel_image(w) for w in windows]))[:, None]
            logits = net(feats)
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy().tolist()
        score = float(np.mean(probs))
        return {
            'verdict': 'synthetic' if score >= self._threshold else 'bonafide',
            'score': round(score, 4),
            'window_scores': [round(float(p), 4) for p in probs],
            'segments': len(probs),
            'analyzed_seconds': round(len(audio) / SAMPLE_RATE, 2),
            'model': 'spoofceleb',
            'model_name': 'SpoofCeleb Mel-CNN',
            'trained_on': 'SpoofCeleb',
            'threshold': self._threshold,
            'disclaimer': 'Бұл калибрленбеген модель бағасы. Алаяқтықты немесе адамның тұлғасын дәлелдемейді.',
        }


detector = Detector()
