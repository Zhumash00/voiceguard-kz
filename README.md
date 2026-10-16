---
title: VoiceGuard KZ — SpoofCeleb
emoji: 🎙️
colorFrom: teal
colorTo: gray
sdk: docker
app_port: 7860
short_description: SpoofCeleb деректерінде оқытылатын нейрожелімен дауыстық дипфейкті анықтау
---

# VoiceGuard KZ — SpoofCeleb нұсқасы

Бұл жобада веб-сайт **тек SpoofCeleb деректерінде оқытылған Mel-CNN моделін** пайдалануға бейімделген.
Аудионы WAV/MP3/FLAC/... түрінде жүктеп, табиғи (`bonafide`) немесе синтетикалық (`spoof`) белгісін
бағалауға болады. **Нақты оқытылған модель файлдары архивке кірмейді.**
Жалған жауап немесе кездейсоқ пайыз қайтарылмайды: checkpoint жоқ болса сайтта **«модель дайын емес»** деп көрсетіледі.

## 1. Неге деректер архивке енгізілмеген?

Ресми SpoofCeleb dataset: https://huggingface.co/datasets/jungjee/spoofceleb

SpoofCeleb **gated**: авторлар қолжетімділік сұранысын қабылдап, университетке тиесілі
email қолдануды сұрайды; рұқсат бірнеше күн ішінде қаралуы мүмкін.
Деректер өте үлкен. ZIP ішінде SpoofCeleb аудио жазбалары да, оның орнына
жасалған жасанды жазбалар да жоқ. Тек өзіңіз рұқсатпен алған деректерді пайдаланыңыз.

Деректер ғылыми мақала: https://doi.org/10.1109/OJSP.2025.3529377

## 2. Windows-та орнату

- Python 3.10–3.12 және `FFmpeg` (`ffmpeg -version`) орнатыңыз.
- `install.bat` іске қосыңыз. Қажетті кітапханалар (PyTorch, librosa, FastAPI) орнатылады.
- Linux/Mac: `python -m pip install -r requirements-train.txt`.
- Сайтты қазір ашуға болады (`start.bat`), бірақ **модель оқытылмайынша талдамайды**.

## 3. SpoofCeleb-ті дайындау

Рұқсатпен жүктелген деректерді шығарып, мысалы мына бумаларға орналастырыңыз:

```
data/spoofceleb/
  flac/
    train/.../*.flac
    development/.../*.flac
    evaluation/.../*.flac
  metadata/
    train.csv
    development.csv
    evaluation.csv
```

**Назар аударыңыз:** бұл — бағдарлама қабылдайтын каталог үлгісі.
Ресми файлдарда жол/баған атаулары өзгеше болса, `--metadata`, `--path-column`,
`--label-column` параметрлері арқылы нақты бағандарды көрсетіңіз.
Кестеде аудиоға апаратын `path` және `bonafide`/`spoof` белгілері болуы керек.

Теңгерімді шағын үлгі дайындау (әр кластан ең көбі 1000 аудио):

```powershell
python scripts/prepare_spoofceleb.py --root data/spoofceleb --split train --out data/train.csv --limit-per-class 1000
python scripts/prepare_spoofceleb.py --root data/spoofceleb --split development --out data/dev.csv --limit-per-class 300
python scripts/prepare_spoofceleb.py --root data/spoofceleb --split evaluation --out data/test.csv --limit-per-class 300
```

Егер metadata-да `audio_file` және `is_spoof` сияқты басқа бағандар қолданылса, тиісті
`--path-column audio_file --label-column is_spoof` беруге болады,
бірақ `is_spoof` мәндері `spoof`/`bonafide` немесе `1`/`0` болуы тиіс.
`--limit-per-class 0` — барлық файлдар (үлкен ресурстар қажет).
**Тек қолжетімді файлдар manifest-ке кіреді**; көрсетілген жолдағы файлдардың бәрі бар екенін тексеріңіз.

## 4. Нақты нейрожеліні оқыту

```powershell
python scripts/train_spoofceleb.py --train data/train.csv --dev data/dev.csv --epochs 8 --batch 16
```

Шығыс: `models/spoofceleb_cnn.pt` (PyTorch state_dict және dataset метадеректері).

- Белгі кодтары: **0 = bonafide**, **1 = spoof**.
- Модель: `16 kHz аудио → Mel-спектрограмма → CNN → 2 логит`.
- GPU болса PyTorch оны пайдаланады. CPU-да оқыту баяу болуы мүмкін.
- `train` және `development` файлдарын араластырмаңыз.
- Dev F1 мәні — **тест нәтижесі емес** және сенімділік кепілдігі емес.
- 1000+1000 шағын үлгі — кодты іске қосуға арналған ғана; толық ғылыми нәтиже үшін көбірек және әртүрлі дерек керек.
- Үлкен корпуста сөйлеуші және TTS генераторларының train/test арасында ақпарат тасымалдауын тексеріңіз.

## 5. Веб-сайтты іске қосу

```powershell
start.bat
```

Немесе:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Браузер: **http://127.0.0.1:8000**.

Сервер: FastAPI, модель: SpoofCeleb Mel-CNN, аудио өңдеу: FFmpeg.

`GET /api/status` сайттың дайындық күйін көрсетеді.
`POST /api/analyze` аудио + `model=spoofceleb` қабылдайды.

Егер checkpoint жоқ болса, сервер нәтижені ойдан шығармайды.

## 6. Тәуелсіз бағалау

```powershell
python scripts/evaluate.py --manifest data/test.csv --model spoofceleb --scores-out data/test_scores.csv
```

Есептелетін метрикалар: accuracy, precision, recall, F1 және екі класс болғанда EER.
**Evaluation файлын оқытуға немесе үздік модельді таңдау үшін пайдаланбаңыз.**
Бастапқы 0.5 шегі калибрленбеген; ол нақты пайыздық сенімділік емес.

## 7. GitHub / Render / Hugging Face Spaces

Репозиторийге кодты жариялауға болады, бірақ SpoofCeleb деректерінің өзін жарияламаңыз.
Оқытылған модель checkpoint-ін серверге жеткізбесеңіз, сайт жұмысын көрсетеді,
бірақ **дауыс талдауы қолжетімсіз болады**. `models/spoofceleb_cnn.pt` — қажет файл.

Checkpoint-ті таратуға құқық бар екеніне көз жеткізіңіз. Өз репозиторийіңізге қосқыңыз келсе:

```bash
git add -f models/spoofceleb_cnn.pt
```

Сосын Render-да Docker runtime немесе Hugging Face Docker Space арқылы жариялаңыз.
`Dockerfile` модельді **автоматты түрде жүктемейді, оқытпайды және жасанды модель құрмайды**.
PyTorch-тың CPU нұсқасы да бұлтты серверде едәуір жад алуы мүмкін.

**Қауіпсіздік:** көпшілікке арналған сайтта жүктемені шектеу, модельдің қатесін тексеру,
деректер құпиялылығы және жеке адамның келісімі ескерілуі тиіс.

## 8. Жоба файлдары

```
app/main.py                    FastAPI API
app/engine.py                  аудионы өңдеу + SpoofCeleb checkpoint inference
app/custom_cnn.py              Mel-спектрограмма және MelCNN архитектурасы
app/static/                    веб-интерфейс
scripts/prepare_spoofceleb.py  рұқсатпен алынған train/dev/eval файлдары → CSV
scripts/train_spoofceleb.py    SpoofCeleb → PyTorch checkpoint
scripts/evaluate.py            тәуелсіз test + EER
models/                        дайын модельді осында орналастыру
Dockerfile                     орналастыру
```

**Шектеу:** бұл телефон алаяқтығын немесе адамның жеке басын дәлелдейтін жүйе емес.
Бұл — аудиодағы синтетикалық белгілерді бағалайтын дипломдық зерттеу прототипі.
