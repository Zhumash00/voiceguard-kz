# VoiceGuard KZ — нейрожелі арқылы дауыстық дипфейкті анықтайтын сайт

**Мақсаты:** телефон алаяқтығынан қорғау контексінде табиғи (bona fide) және жасанды (spoof/deepfake) сөйлеуді зерттеу үшін дайын веб-прототип. Сайт аудио файлды қабылдап, нақты **AASIST** нейрожелісімен бағалайды. Жалған «демо анықтау» не кездейсоқ пайыз шығармайды.

> Зерттеу прототипі: телефон алаяқтығын немесе адамның шынайы тұлғасын тікелей анықтамайды. Модель қателесуі мүмкін. Өз нәтижелеріңізді тәуелсіз деректерде тексеріңіз.

## 1. Жылдам іске қосу (Windows 10/11)

1. **Python 3.10–3.12** және **FFmpeg** орнатыңыз. `python --version` және `ffmpeg -version` командалары жұмыс істеуі тиіс. FFmpeg-ті Windows PATH-қа қосыңыз.
2. ZIP архивті ашып, `install.bat` файлын іске қосыңыз. Ол `.venv` виртуалды ортасын жасап, кітапханаларды және **AASIST ONNX** нейрожелісін жүктейді (интернет керек). 1.6 МБ шамасындағы модель `models/aasist.onnx` файлына түседі.
3. `start.bat` файлын іске қосыңыз.
4. Браузерде **http://127.0.0.1:8000** ашыңыз.
5. WAV, MP3, FLAC, OGG, M4A, AAC, OPUS, WEBM жүктеп, **«Нейрожелімен тексеру»** түймесін басыңыз.

Егер `.bat` іске қосылмаса, PowerShell ішінде:

```powershell
cd voiceguard_site
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\download_model.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Басқа жүйеде `python3 -m venv .venv && source .venv/bin/activate`, әрі қарай `pip install -r requirements.txt; python scripts/download_model.py; uvicorn app.main:app ...`.

**Маңызды:** модель файлы ZIP-ке кірмейді, өйткені осы құрастыру ортасында сыртқы модель салмақтарын жүктеу мүмкін болмады. Алғашқы орнату кезінде желіден алынады. Салмақтар болмаған жағдайда сайт нәтижені **ойдан шығармайды** және «модель дайын емес» хабарламасын көрсетеді.

## 2. Іске асырылған жұмыс логикасы

```
Браузер → аудио файл → FastAPI
        → FFmpeg: mono / 16000 Hz / алғашқы 30 сек
        → 4.0375 сек ұзындықтағы 1–6 аудио фрагмент
        → AASIST ONNX (нақты нейрожелі) → [spoof, bona fide] logits
        → әр фрагменттегі softmax(spoof) бағаларының орташа мәні
        → 0.5 эксперименттік шек → «синтетикалық» / «табиғи» белгілер
```

AASIST — *Audio Anti-Spoofing using Integrated Spectro-Temporal Graph Attention Networks*. Ол raw waveform-ты өңдейді, spectro-temporal graph attention архитектурасы бар. Пайдаланылған pretrained checkpoint бастапқыда **ASVspoof 2019 LA** деректерінде оқытылған, ал ONNX нұсқасы [SpeechAntiSpoofingBenchmarks/AASIST](https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST) репозиторийінен алынады. **0.5 шегі ғылыми калибрлеуден өткен шешім емес**; көрсетілген пайыз — модельдің softmax бағасы, шынайы статистикалық ықтималдық не кепілдік емес. Бірнеше фрагмент бағасын орташалау — осы сайттың зерттеу тәсілі; ол ресми benchmark scoring процедурасын дәл қайталамайды.

Модель карточкасында өзге домендердегі қателіктер көрсетілген: ASVspoof 2019 LA EER 0.83%, ASVspoof 2021 DF EER 17.04%, InTheWild EER 43.01%. Бұл жүйенің нақты қоңырауларда автоматты сенімді екенін **дәлелдемейді**. Дереккөз: https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST.

## 3. Құжаттағы деректер базалары (dataset)

| Деректер | Сілтеме | Қолданылуы |
|---|---|---|
| **ASVspoof 2019** | https://zenodo.org/records/6906306 | AASIST pretrained baseline (LA); жеке CNN-ді train/dev оқыту |
| **ASVspoof 2021 LA** | https://zenodo.org/records/4837263 | Телефон арнасына ұқсас кодтау / LA қосымша бағалау |
| **ASVspoof 2021 PA** | https://zenodo.org/records/4834716 | Replay spoofing сценарийлері (жеке міндет) |
| **ASVspoof 2021 DF** | https://zenodo.org/records/4835108 | Deepfake **evaluation** және cross-domain тексеру |
| **SpoofCeleb** | https://huggingface.co/datasets/jungjee/spoofceleb | In-the-wild speech негізіндегі қосымша эксперимент |
| **VoxCeleb** | https://www.robots.ox.ac.uk/~vgg/data/voxceleb/ | SpoofCeleb бастапқы real-world speech деректері |

ASVspoof 2021 DF — ресми бағалау дерегі; оны AASIST 2019 LA бағасын тексеруге **тәуелсіз тест** ретінде қолданған дұрыс. Деректердің өлшемі үлкен болуы мүмкін, сайттың zip файлында олар жоқ. Дереккөздер: [ASVspoof 2021 ресми беті](https://www.asvspoof.org/index2021.html), [ASVspoof 2021 evaluation repo](https://github.com/asvspoof-challenge/2021).

## 4. Өз CNN моделіңізді деректермен оқыту (міндетті емес)

Осы сайтта жеке **Mel-spectrogram → CNN → Real/Fake** моделін үйрету құралы да бар. Ол дайын AASIST-пен салыстыру жүргізуге жарайды, бірақ сапасын өлшеу міндетті.

1. `pip install -r requirements-train.txt` (torch, librosa, scikit-learn т.б.).
2. ASVspoof 2019 LA `train` және `dev` FLAC файлдарын бөлек жүктеңіз; official protocol files-ын сақтаңыз.
3. Protocol-дан CSV жинаңыз:

```powershell
python scripts/make_manifest.py --protocol data/ASVspoof2019.LA.cm.train.trn.txt --audio-dir data/LA/ASVspoof2019_LA_train/flac --output data/train.csv
python scripts/make_manifest.py --protocol data/ASVspoof2019.LA.cm.dev.trl.txt --audio-dir data/LA/ASVspoof2019_LA_dev/flac --output data/dev.csv
```

CSV форматы: `path,label,utterance_id`; мұнда `0=bonafide`, `1=spoof` және `path` — нақты аудионың толық жолы. `--audio-dir` нақты архивтің FLAC қалтасына сәйкес келуі тиіс.

4. Жеке CNN-ді оқыту:

```powershell
python scripts/train_cnn.py --train data/train.csv --dev data/dev.csv --epochs 8
```

Нәтиже `models/custom_cnn.pt` файлына сақталады. Сайтты қайта қосқаннан кейін модель таңдау тізімінен **Mel-CNN** таңдауға болады. Бұл қарапайым baseline; ғылыми нәтижесі алдын ала белгісіз. Train/dev/test бір аудионы бөліспеуі керек; мүмкіндігінше speaker және generator бойынша leakage-ке тексеріңіз. Болашақта network codec augmentation және unseen-generator split қосуға болады.

## 5. Тәуелсіз бағалау / EER

Егер тест деректерін `data/test.csv` түрінде дайындасаңыз:

```powershell
python scripts/evaluate.py --manifest data/test.csv --model aasist --scores-out data/scores.csv
```

Скрипт **accuracy, precision, recall, F1** және екі класс болса **EER** есептейді. Оқу/валидация және тест жиындары толық бөлек болуы керек. EER бір threshold бойынша accuracy-ге тең емес.

## 6. API

- `GET /` — веб-интерфейс
- `GET /api/status` — модельдің дайындығы және FFmpeg жағдайы
- `POST /api/analyze` — `multipart/form-data`: `file` (аудио), `model` (`aasist` немесе `cnn`)
- `GET /api/docs` — Swagger интерфейсі

Файл шегі 20 МБ, алғашқы 30 секунд ғана талданады. Аудио серверде файлға жазылмайды, сұраныс кезінде жедел жадта өңделеді. Сервер интернетке аудио жібермейді. Қолданбаға сырттан қолжетімділік ашпаңыз: ол бұл нұсқада аутентификация/рейт-лимитсіз локал зерттеу жүйесі (`127.0.0.1`).

## 7. Жоба құрылымы

```
voiceguard_site/
  app/
    main.py              FastAPI endpoint
    engine.py            FFmpeg, ONNX және CNN inference
    custom_cnn.py        Optional convolutional network
    static/
      index.html         Веб-бет
      style.css          Интерфейс
      app.js             Файл жүктеу, waveform, API
  scripts/
    download_model.py    AASIST ONNX жүктеу
    make_manifest.py     ASVspoof 2019 протоколын CSV-ге айналдыру
    train_cnn.py         Жеке CNN моделін оқыту
    evaluate.py          Test көрсеткіштері/EER
  models/                Модельдер осында жүктеледі
  tests/                 Серверлік тесттер
  requirements.txt
  requirements-train.txt
  install.bat
  start.bat
```

## 8. Ғылыми дереккөздер

- Jung et al. — **AASIST**, https://arxiv.org/abs/2110.01200
- Pretrained AASIST ONNX https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST
- ASVspoof 2019 challenge https://www.asvspoof.org/index2019.html
- ASVspoof 2021 challenge https://www.asvspoof.org/index2021.html
- ASVspoof 2021 model baselines https://github.com/asvspoof-challenge/2021
- SpoofCeleb dataset https://huggingface.co/datasets/jungjee/spoofceleb

**Лицензия туралы:** AASIST моделінің дереккөзінде MIT лицензиясы көрсетілген. Dataset материалдарын қолданғанда әрқайсысының лицензиясын және дереккөзге сілтеме беру талабын сақтаңыз.
