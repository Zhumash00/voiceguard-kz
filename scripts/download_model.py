"""Download pretrained neural network ONNX file (no remote code execution)."""
from pathlib import Path
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    out = ROOT / 'models'
    out.mkdir(exist_ok=True)
    print('AASIST ONNX моделін Hugging Face қорынан жүктеу басталды...')
    fp = hf_hub_download(repo_id='SpeechAntiSpoofingBenchmarks/AASIST', filename='aasist.onnx', local_dir=str(out))
    print('Дайын:', fp)
    print('Ескерту: модель ASVspoof 2019 LA деректерімен оқытылған; телефон қоңырауларында қатесіз емес.')
