from io import BytesIO
from pathlib import Path
import csv
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import engine
from scripts.prepare_spoofceleb import build_manifest, label_to_int

client = TestClient(app)

def test_home_shows_dataset():
    r = client.get('/')
    assert r.status_code == 200
    assert 'SpoofCeleb' in r.text
    assert 'AASIST' not in r.text


def test_status_dataset_name():
    r = client.get('/api/status')
    assert r.status_code == 200
    assert r.json()['dataset'] == 'SpoofCeleb'
    assert 'spoofceleb' in r.json()


def test_wrong_model_rejected():
    r = client.post('/api/analyze', data={'model':'aasist'},
                    files={'file':('test.wav',b'data','audio/wav')})
    assert r.status_code == 400


def test_unknown_format():
    r = client.post('/api/analyze', files={'file':('danger.txt',b'data','text/plain')})
    assert r.status_code == 415


def test_empty_audio():
    r = client.post('/api/analyze', files={'file':('test.wav',b'','audio/wav')})
    assert r.status_code == 400


def test_oversized_audio():
    r = client.post('/api/analyze',files={'file':('test.wav',b'1'*(20*1024*1024+1),'audio/wav')})
    assert r.status_code == 413


def test_short_audio_repeat_window():
    arr = np.ones(1000,dtype=np.float32)
    windows = engine.split_windows(arr)
    assert windows.shape == (1,64600)
    assert np.all(windows==1)


def test_long_audio_windows():
    arr = np.linspace(0,1,16*16000,dtype=np.float32)
    windows = engine.split_windows(arr)
    assert windows.shape[1]==64600
    assert windows[-1,-1] == pytest.approx(arr[-1])


def test_correct_labels():
    assert label_to_int('bonafide') == 0
    assert label_to_int('spoof') == 1
    with pytest.raises(ValueError):
        label_to_int('maybe')


def test_manifest_reads_real_local_files(tmp_path):
    base=tmp_path/'dataset'
    aud=base/'flac'/'train'
    aud.mkdir(parents=True)
    for name in ('voice_bona.flac','voice_spoof.flac'):
        (aud/name).write_bytes(b'not a real sample')
    metadata=base/'metadata'/'train.csv'
    metadata.parent.mkdir()
    with metadata.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['path','label'])
        w.writeheader()
        w.writerows([{'path':'voice_bona.flac','label':'bonafide'},
                     {'path':'voice_spoof.flac','label':'spoof'},
                     {'path':'missing.flac','label':'spoof'}])
    out=tmp_path/'manifest.csv'
    n,missing,distribution=build_manifest(base,metadata,out,'train',limit_per_class=2)
    assert n==2
    assert missing==1
    assert distribution=={0:1,1:1}
    assert all(Path(row['path']).exists() for row in csv.DictReader(out.open()))


def test_missing_checkpoint_not_inventing_prediction(monkeypatch,tmp_path):
    monkeypatch.setattr(engine,'SPOOFCELEB_FILE',tmp_path/'missing.pt')
    engine.detector._net=None
    with pytest.raises(FileNotFoundError):
        engine.detector.predict(np.ones(8000,dtype=np.float32))


def test_inference_with_controlled_neural_logits(monkeypatch):
    import torch
    class DummyNet:
        def __call__(self,features):
            return torch.tensor([[-2.0,2.0]] * len(features))
    monkeypatch.setattr(engine.detector,'_load_model',lambda:DummyNet())
    engine.detector._threshold = .5
    r=engine.detector.predict(np.ones(8000,dtype=np.float32))
    assert r['verdict']=='synthetic'
    assert r['score']>.95
    assert r['trained_on']=='SpoofCeleb'


def test_reject_wrong_checkpoint_metadata(tmp_path,monkeypatch):
    import torch
    path=tmp_path/'wrong.pt'
    torch.save({'dataset':'ASVspoof 2019 LA','model_family':'MelCNN-v1'},path)
    monkeypatch.setattr(engine,'SPOOFCELEB_FILE',path)
    engine.detector._net=None
    with pytest.raises(RuntimeError, match='SpoofCeleb'):
        engine.detector._load_model()
