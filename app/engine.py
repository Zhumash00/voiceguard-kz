"""Audio preprocessing and AASIST/optional CNN inference. No fake demo predictions."""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
AASIST_FILE = Path(os.getenv('VOICEGUARD_AASIST_PATH', str(ROOT / 'models' / 'aasist.onnx')))
CNN_FILE = Path(os.getenv('VOICEGUARD_CNN_PATH', str(ROOT / 'models' / 'custom_cnn.pt')))
SAMPLE_RATE = 16000
WINDOW = 64600
MAX_AUDIO_SEC = 30
MAX_WINDOWS = 8
MODEL_REPO = 'SpeechAntiSpoofingBenchmarks/AASIST'

class AudioError(Exception):
    pass


def decode_audio(file_bytes: bytes) -> np.ndarray:
    """Safely decode formats supported by ffmpeg to 16 kHz mono f32 waveform."""
    if not shutil.which('ffmpeg'):
        raise AudioError('FFmpeg орнатылмаған. README.md нұсқаулығын қараңыз.')
    cmd = ['ffmpeg', '-nostdin', '-v', 'error', '-i', 'pipe:0', '-t', str(MAX_AUDIO_SEC),
           '-ar', str(SAMPLE_RATE), '-ac', '1', '-f', 'f32le', 'pipe:1']
    try:
        p = subprocess.run(cmd, input=file_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=35, check=False)
    except subprocess.TimeoutExpired as e:
        raise AudioError('Аудионы өңдеу уақыты асып кетті.') from e
    if p.returncode != 0 or not p.stdout:
        raise AudioError('Аудио файлын оқу мүмкін емес. WAV, MP3, FLAC, M4A немесе OGG пайдаланыңыз.')
    audio = np.frombuffer(p.stdout, dtype='<f4').copy()
    if len(audio) < int(0.35 * SAMPLE_RATE):
        raise AudioError('Аудио тым қысқа. Кемінде 0,35 секунд сөйлеу жүктеңіз.')
    if not np.isfinite(audio).all():
        raise AudioError('Аудиода жарамсыз сандық мәндер бар.')
    if np.max(np.abs(audio)) < 1e-5:
        raise AudioError('Жазбада дыбыс байқалмады.')
    return np.clip(audio, -1.0, 1.0)


def window_samples_with_times(audio: np.ndarray, count: int = MAX_WINDOWS):
    """Window waveforms and exact source-time ranges; cover all the first 30 seconds.

    Every interval is based on original unpadded samples, including short clips.
    """
    if len(audio) <= WINDOW:
        padded = (np.tile(audio, int(np.ceil(WINDOW / len(audio))))[:WINDOW]
                  if len(audio) < WINDOW else audio)
        return np.ascontiguousarray(padded[None, :].astype(np.float32)), [
            {'start':0., 'end':round(len(audio)/SAMPLE_RATE,2), 'padded':len(audio)<WINDOW}]
    n = min(count, max(2, int(np.ceil(len(audio) / WINDOW))))
    positions = np.linspace(0, len(audio) - WINDOW, n, dtype=np.int64)
    windows = np.ascontiguousarray(np.stack([audio[i:i+WINDOW] for i in positions]), dtype=np.float32)
    ranges = [{'start':round(int(i)/SAMPLE_RATE,2),
               'end':round(min(int(i)+WINDOW,len(audio))/SAMPLE_RATE,2),
               'padded':False} for i in positions]
    return windows, ranges


def split_windows(audio: np.ndarray, count: int = MAX_WINDOWS) -> np.ndarray:
    """Backwards-compatible preprocessing interface for training/test scripts."""
    return window_samples_with_times(audio, count)[0]


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float64)
    logits -= logits.max(axis=-1, keepdims=True)
    e = np.exp(logits)
    return e / e.sum(axis=-1, keepdims=True)


class Detector:
    def __init__(self):
        self._aasist = None
        self._cnn = None
        self._lock = threading.Lock()

    def status(self) -> dict:
        aasist_ready = AASIST_FILE.exists()
        cnn_ready = CNN_FILE.exists()
        return {
            'aasist': aasist_ready,
            'cnn': cnn_ready,
            'model_name': 'AASIST — ASVspoof 2019 LA',
            'model_source': f'https://huggingface.co/{MODEL_REPO}',
            'ffmpeg': shutil.which('ffmpeg') is not None,
        }

    def _load_aasist(self):
        if not AASIST_FILE.exists():
            raise FileNotFoundError('AASIST моделі орнатылмаған. Алдымен python scripts/download_model.py іске қосыңыз.')
        if self._aasist is None:
            with self._lock:
                if self._aasist is None:
                    try:
                        import onnxruntime as ort
                    except ImportError as e:
                        raise RuntimeError('onnxruntime орнатылмаған: pip install -r requirements.txt') from e
                    self._aasist = ort.InferenceSession(str(AASIST_FILE), providers=['CPUExecutionProvider'])
        return self._aasist

    def _load_cnn(self):
        if not CNN_FILE.exists():
            raise FileNotFoundError('Жеке CNN моделі әлі оқытылмаған. scripts/train_cnn.py қараңыз.')
        if self._cnn is None:
            with self._lock:
                if self._cnn is None:
                    try:
                        import torch
                    except ImportError as e:
                        raise RuntimeError('CNN үшін torch керек: pip install -r requirements-train.txt') from e
                    from .custom_cnn import MelCNN
                    # Load only local checkpoint created by this package; PyTorch weights_only.
                    ckpt = torch.load(CNN_FILE, map_location='cpu', weights_only=True)
                    net = MelCNN()
                    net.load_state_dict(ckpt['state_dict'])
                    net.eval()
                    self._cnn = net
        return self._cnn

    def predict(self, audio: np.ndarray, model: str = 'aasist') -> dict:
        windows, ranges = window_samples_with_times(audio)
        if model == 'aasist':
            session = self._load_aasist()
            ins = session.get_inputs()
            if len(ins) != 1:
                raise RuntimeError('ONNX моделінің input форматы күтілгенге сәйкес емес.')
            probs = []
            # One window per call avoids high CPU RAM / batch-size constraints.
            for window in windows:
                output = session.run(None, {ins[0].name: window[None, :].astype(np.float32)})
                logits = np.asarray(output[0])
                if logits.shape != (1, 2):
                    raise RuntimeError(f'Күтпеген logits пішімі: {logits.shape}')
                # AASIST order from official implementation: [spoof, bonafide]
                probs.append(float(softmax(logits)[0, 0]))
            model_name = 'AASIST (ASVspoof 2019 LA)'
        elif model == 'cnn':
            import torch
            from .custom_cnn import mel_image
            net = self._load_cnn()
            with torch.inference_mode():
                features = torch.from_numpy(np.stack([mel_image(w) for w in windows]))[:, None]
                logits = net(features)
                probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy().tolist()
            model_name = 'Custom Mel-CNN (жергілікті оқыту)'
        else:
            raise ValueError('Белгісіз модель.')
        fake_score = float(np.mean(probs))
        time_segments = [
            {**bounds, 'synthetic_score':round(float(prob),4),
             'verdict':'synthetic' if prob >= 0.5 else 'bonafide'}
            for bounds, prob in zip(ranges, probs)
        ]
        # Explain why the output verdict was selected using actual window scores.
        # This is NOT a feature attribution of internal AASIST neurons.
        if fake_score >= 0.5:
            reason = ('Аудио үзінділерінің нейрожелілік синтетикалық бағаларының '
                      'орташа мәні 0,50 шегінен жоғары. Төмендегі уақыт аралықтары '
                      'модельдің қай жерде жоғары баға бергенін көрсетеді.')
        else:
            reason = ('Аудио үзінділерінің нейрожелілік синтетикалық бағаларының '
                      'орташа мәні 0,50 шегінен төмен. Бұл шынайылықты дәлелдемейді; '
                      'тек модель осы аудиода синтетикалық белгілерді аз бағалады.')
        from .analysis_features import acoustic_observations
        acoustics = acoustic_observations(audio)
        return {
            'verdict': 'synthetic' if fake_score >= 0.5 else 'bonafide',
            'score': round(fake_score, 4),
            'window_scores': [round(p, 4) for p in probs],
            'time_segments': time_segments,
            'explanation': reason,
            'acoustics': acoustics,
            'analysis_method': 'Нейрожелінің әр уақыттық терезе бойынша бағасы және бөлек есептелген акустикалық белгілер. Паузалар модель шешімінің дәлелді себептері емес.',
            'segments': len(probs),
            'analyzed_seconds': round(len(audio) / SAMPLE_RATE, 2),
            'model': model,
            'model_name': model_name,
            'threshold': 0.5,
            'disclaimer': 'Бұл модельдің калибрленбеген бағасы; нәтижені адамның жеке басын тексеру немесе алаяқтықты дәлелдеу үшін жеке қолданбаңыз.',
        }


detector = Detector()
