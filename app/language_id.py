"""Local Whisper tiny language ID. Does not send audio to external services."""
from __future__ import annotations
import os
import threading
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.getenv('VOICEGUARD_LANGUAGE_PATH', str(ROOT / 'models' / 'whisper-tiny')))
NAMES = {
    'kk': 'Қазақ тілі', 'ru': 'Орыс тілі', 'en': 'Ағылшын тілі',
    'tr': 'Түрік тілі', 'uz': 'Өзбек тілі', 'uk': 'Украин тілі',
    'de': 'Неміс тілі', 'fr': 'Француз тілі', 'es': 'Испан тілі',
    'zh': 'Қытай тілі', 'ar': 'Араб тілі', 'hi': 'Хинди тілі',
    'ja': 'Жапон тілі', 'ko': 'Корей тілі', 'it': 'Итальян тілі',
    'pt': 'Португал тілі', 'pl': 'Поляк тілі', 'fa': 'Парсы тілі'
}

class LanguageIdentifier:
    def __init__(self):
        self._model = None
        self._lock = threading.Lock()

    def ready(self) -> bool:
        return (MODEL_DIR / 'model.bin').is_file() and os.getenv('VOICEGUARD_LANGUAGE_ENABLED','1') != '0'

    def _load(self):
        if not self.ready():
            raise FileNotFoundError('Whisper Tiny тілді анықтау моделі орнатылмаған.')
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from faster_whisper import WhisperModel
                    self._model = WhisperModel(str(MODEL_DIR), device='cpu', compute_type='int8',
                                               cpu_threads=2, num_workers=1, local_files_only=True)
        return self._model

    def detect(self, audio: np.ndarray, rate: int = 16000) -> dict:
        unknown = {'code':None,'name':'Анықталмады', 'confidence':None,
                   'model':'Whisper Tiny (multilingual)', 'status':'unavailable',
                   'note':'Тіл моделі қолжетімсіз.'}
        if not self.ready():
            return unknown
        if len(audio) / rate < 1.5:
            return {**unknown,'status':'insufficient_audio',
                    'note':'Тілді бағалау үшін кемінде 1,5 секунд анық сөйлеу қажет.'}
        try:
            model = self._load()
            # Faster Whisper detects a language from mel features when language=None;
            # reading info does not require generating or storing a transcript.
            _segments, info = model.transcribe(np.asarray(audio,dtype=np.float32),
                         language=None, beam_size=1, best_of=1,
                         vad_filter=False, condition_on_previous_text=False)
            conf = float(info.language_probability)
            code = str(info.language)
            if conf < 0.55:
                return {**unknown,'status':'uncertain','confidence':round(conf,3),
                        'note':'Тілдің бағасы төмен. Қысқа, шулы немесе көптілді аудиода қателік болуы мүмкін.'}
            return {'code': code, 'name':NAMES.get(code,code.upper()), 'confidence':round(conf,3),
                    'model':'Whisper Tiny (multilingual)','status':'ok',
                    'note':'Бұл — ықтимал тіл; көптілді не шулы сөйлеуде қателесуі мүмкін.'}
        except Exception as exc:
            # Classification still works if a separate language model fails.
            return {**unknown,'status':'error','note':'Тілді анықтау модулінде қате шықты; дауысты жіктеу нәтижесі сақталды.'}

language_identifier = LanguageIdentifier()
