"""Optional independent neural classifier, trained on user-provided manifest."""
from __future__ import annotations
import numpy as np


def mel_image(samples: np.ndarray) -> np.ndarray:
    import librosa
    x = samples.astype(np.float32)
    s = librosa.feature.melspectrogram(y=x, sr=16000, n_fft=400, hop_length=160, n_mels=64, power=2)
    s = librosa.power_to_db(s + 1e-9, ref=1.0)
    s = np.clip((s + 80) / 80, 0, 1).astype(np.float32)
    return s


# torch imports only needed when using optional custom model
try:
    import torch.nn as nn
    class MelCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Conv2d(1, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(), nn.AdaptiveAvgPool2d(1)
            )
            self.classifier = nn.Linear(64, 2)

        def forward(self, x):
            return self.classifier(self.encoder(x).flatten(1))
except ImportError:
    MelCNN = None
