from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import engine
from scripts.make_manifest import make_manifest

client = TestClient(app)

def test_home_works():
    res = client.get('/')
    assert res.status_code == 200
    assert 'VoiceGuard' in res.text
    assert 'ASVspoof 2021 DF' in res.text

def test_status_endpoint():
    res = client.get('/api/status')
    assert res.status_code == 200
    assert res.json()['service'] == 'online'
    assert 'aasist' in res.json()

def test_reject_bad_format():
    res = client.post('/api/analyze',files={'file':('test.txt',b'hi','text/plain')})
    assert res.status_code == 415

def test_reject_empty():
    res = client.post('/api/analyze',files={'file':('test.wav',b'','audio/wav')})
    assert res.status_code == 400

def test_reject_excess_size():
    res = client.post('/api/analyze',files={'file':('test.wav',b'1'*(20*1024*1024+1),'audio/wav')})
    assert res.status_code == 413

def test_short_window_repeat_padding():
    arr = np.ones(2000,dtype=np.float32)
    sliced=engine.split_windows(arr)
    assert sliced.shape == (1,64600)
    assert np.all(sliced==1)

def test_long_window_coverage():
    arr=np.linspace(0,1,16*16000,dtype=np.float32)
    sliced=engine.split_windows(arr)
    assert sliced.shape[0]>1
    assert sliced.shape[1]==64600
    assert sliced[-1,-1] == pytest.approx(arr[-1])

def test_valid_audio_decoding():
    import wave
    buf=BytesIO()
    with wave.open(buf,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
        t=np.arange(16000,dtype=np.float32)/16000
        w.writeframes((np.sin(t*440*2*np.pi)*9000).astype('<i2').tobytes())
    output=engine.decode_audio(buf.getvalue())
    assert len(output)==16000
    assert output.max()>.1

def test_result_uses_real_model_logits(monkeypatch):
    # Mock only the ONNX runtime; proves that website API does not generate random results.
    class DummySession:
        def get_inputs(self): return [SimpleNamespace(name='wav')]
        def run(self, ignored, d):
            assert d['wav'].shape==(1,64600)
            return [np.array([[2.,-2.]],dtype=np.float32)]  # spoof higher
    monkeypatch.setattr(engine.detector,'_load_aasist',lambda:DummySession())
    result=engine.detector.predict(np.ones(8000,dtype=np.float32),'aasist')
    assert result['verdict']=='synthetic'
    assert result['score'] > .9

def test_make_manifest(tmp_path):
    audio=tmp_path/'flac'
    audio.mkdir()
    (audio/'LA_T_001.flac').write_bytes(b'x')
    (audio/'LA_T_002.flac').write_bytes(b'y')
    protocol=tmp_path/'protocol.txt'
    protocol.write_text('LA_01 LA_T_001 - - spoof\nLA_01 LA_T_002 - - bonafide\n')
    count,missing=make_manifest(protocol,audio,tmp_path/'manifest.csv')
    assert (count,missing)==(2,0)
    rows=(tmp_path/'manifest.csv').read_text()
    assert 'LA_T_001' in rows and 'LA_T_002' in rows
    assert ',1,' in rows and ',0,' in rows

def test_missing_model_returns_503(monkeypatch):
    import wave
    from app import main
    audio_buf=BytesIO()
    with wave.open(audio_buf,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
        x=(np.sin(np.arange(16000)/16000*440*2*np.pi)*8000).astype('<i2')
        w.writeframes(x.tobytes())
    def raise_missing(*args,**kwargs):
        raise FileNotFoundError('AASIST model missing')
    monkeypatch.setattr(main.detector,'predict',raise_missing)
    res=client.post('/api/analyze',files={'file':('speech.wav',audio_buf.getvalue(),'audio/wav')})
    assert res.status_code==503
    assert 'missing' in res.json()['detail']


def test_analyze_success_with_stubbed_neural_backend(monkeypatch):
    import wave
    from app import main
    audio_buf=BytesIO()
    with wave.open(audio_buf,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
        x=(np.sin(np.arange(16000)/16000*440*2*np.pi)*8000).astype('<i2')
        w.writeframes(x.tobytes())
    class DummySession:
        def get_inputs(self):return [SimpleNamespace(name='wav')]
        def run(self,_,d):return [np.array([[-1.,2.]],dtype=np.float32)]
    monkeypatch.setattr(main.detector,'_load_aasist',lambda:DummySession())
    res=client.post('/api/analyze',files={'file':('speech.wav',audio_buf.getvalue(),'audio/wav')})
    assert res.status_code==200
    assert res.json()['verdict']=='bonafide'
    assert res.json()['score']<.1


def test_time_segments_cover_audio_and_boundaries(monkeypatch):
    class DummySession:
        def get_inputs(self): return [SimpleNamespace(name='wav')]
        def run(self, _, d):return [np.array([[1., 0.]],dtype=np.float32)]
    monkeypatch.setattr(engine.detector,'_load_aasist', lambda:DummySession())
    duration = 30
    audio = np.ones(duration * 16000,dtype=np.float32)*0.04
    result = engine.detector.predict(audio)
    windows = result['time_segments']
    assert windows[0]['start']==0
    assert windows[-1]['end']==30
    assert 1 < len(windows) <= engine.MAX_WINDOWS
    for idx,s in enumerate(windows):
        assert 0<=s['start']<s['end']<=30
        if idx: assert s['start']<=windows[idx-1]['end']
        assert s['synthetic_score']==result['window_scores'][idx]
    assert result['explanation']
    assert 'pauses' in result['acoustics']


def test_short_clip_timestamp_is_real_length_not_model_padding(monkeypatch):
    class DummySession:
        def get_inputs(self):return [SimpleNamespace(name='wav')]
        def run(self, _, d):return [np.array([[-1., 2.]],dtype=np.float32)]
    monkeypatch.setattr(engine.detector,'_load_aasist',lambda:DummySession())
    result=engine.detector.predict(np.ones(16000,dtype=np.float32)*.01)
    assert result['time_segments']==[{'start':0.0,'end':1.0,'padded':True,
            'synthetic_score':pytest.approx(result['score'],abs=1e-5),'verdict':'bonafide'}]


def test_pauses_timestamps_from_real_audio():
    from app.analysis_features import acoustic_observations
    audio=np.concatenate([np.ones(16000)*.08, np.zeros(8000), np.ones(16000)*.08]).astype('float32')
    result=acoustic_observations(audio)
    assert result['pause_count'] >= 1
    pause=result['pauses'][0]
    assert .9<=pause['start']<=1.2
    assert 1.3<=pause['end']<=1.6
    assert any(o['kind']=='pause' for o in result['observations'])


def test_no_long_pause_observation_is_not_proof():
    from app.analysis_features import acoustic_observations
    result=acoustic_observations(np.ones(16000*5,dtype='float32')*.05)
    assert result['pause_count']==0
    assert any('дәлелдемейді' in o['detail'] for o in result['observations'])


def test_language_unavailable_is_honest(monkeypatch):
    from app.language_id import language_identifier
    monkeypatch.setattr(language_identifier,'ready',lambda:False)
    result=language_identifier.detect(np.ones(16000*3,dtype='float32')*.04)
    assert result['code'] is None
    assert result['status']=='unavailable'


def test_language_model_info_without_transcription(monkeypatch):
    from app.language_id import language_identifier
    monkeypatch.setattr(language_identifier,'ready',lambda:True)
    class DummyLanguageModel:
        def transcribe(self, wav, **kw):
            assert kw['language'] is None
            return iter([]),SimpleNamespace(language='kk',language_probability=.91)
    monkeypatch.setattr(language_identifier,'_load',lambda:DummyLanguageModel())
    result=language_identifier.detect(np.ones(16000*3,dtype='float32')*.04)
    assert result['code']=='kk'
    assert result['name']=='Қазақ тілі'
    assert result['confidence']==.91


def test_full_analyze_response_includes_language_timeline_and_evidence(monkeypatch):
    from app import main
    monkeypatch.setattr(main.language_identifier,'detect',lambda _: {'code':'ru','name':'Орыс тілі','confidence':.7,'status':'ok'})
    class DummySession:
        def get_inputs(self):return [SimpleNamespace(name='wav')]
        def run(self,_, d):return [np.array([[2.,-2.]],dtype='float32')]
    monkeypatch.setattr(main.detector,'_load_aasist',lambda:DummySession())
    import wave
    raw=BytesIO()
    with wave.open(raw,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
        wav.writeframes(np.ones(16000*5,dtype='<i2').tobytes())
    res=client.post('/api/analyze',files={'file':('example.wav',raw.getvalue(),'audio/wav')})
    assert res.status_code==200, res.text
    data=res.json()
    assert data['language']['code']=='ru'
    assert data['time_segments'][0]['start']==0
    assert data['time_segments'][-1]['end']==5
    assert data['explanation']
    assert data['acoustics']['pause_count']==0
