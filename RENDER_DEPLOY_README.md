# VoiceGuard KZ v2 — Docker және Render нұсқаулығы

## 1. Docker Desktop арқылы іске қосу

1. **Docker Desktop** орнатыңыз және Docker Engine іске қосылғанына көз жеткізіңіз.
2. ZIP-ті ашыңыз; терминалда **`Dockerfile` орналасқан бумаға** кіріңіз.
3. Орындаңыз:

```bash
docker compose up --build -d
```

4. Сайтты ашыңыз: **http://localhost:8000**.
5. Серверді тексеріңіз: **http://localhost:8000/api/status**.
6. Тоқтату: `docker compose down`. Лог көру: `docker compose logs -f`.

Қажет болса Docker Compose орнына:

```bash
docker build -t voiceguard-kz:2 .
docker run --rm -p 8000:8000 -e PORT=8000 voiceguard-kz:2
```

Docker image жиналғанда интернеттен **AASIST ONNX** және **Whisper Tiny** салмақтары жүктеледі. Сондықтан бірінші құрастыруға желі қажет. Олар бастапқы ZIP-ке кірмейді. Егер жүктеу сәтсіз болса, Docker build қатемен тоқтайды — жалған нәтиже жасалмайды.

## 2. Render арқылы жариялау

1. Архивті ашып, `app/`, `scripts/`, `models/`, `Dockerfile`, `requirements.txt`, `compose.yaml` және басқа файлдарды GitHub репозиторийінің **негізгі деңгейіне** орналастырыңыз. **ZIP файлын жалғыз өзі** GitHub-қа салмаңыз.
2. Render Dashboard → **New → Web Service** → GitHub репозиторийін таңдаңыз.
3. **Language/Runtime: Docker**.
4. **Root Directory: бос** (файлдар репозиторий түбірінде болса).
5. **Dockerfile Path: `./Dockerfile`**.
6. **Start Command / Docker Command: бос**. Dockerfile ішінде `CMD` орнатылған және `${PORT}` мәнін оқиды.
7. Deploy жасап, `https://...onrender.com/api/status` ашыңыз.

Render-дің жадысы және CPU мүмкіндігі модельдердің жұмысына әсер етеді. CPU ресурсы аз болса, Whisper Tiny мен AASIST бірге баяу орындалуы немесе жад жеткіліксіз болуы мүмкін. Мұндайда ресурсы көбірек тариф немесе жеке сервер қажет.

## 3. Нені көрсетеді?

- `language.name` және `language.confidence`: **Whisper Tiny** болжаған тіл. Бұл сөзбе-сөз транскрипция емес, әрі көптілді/қысқа/шулы аудиода қателесуі мүмкін.
- `verdict`, `score`: **AASIST** (немесе қосымша оқытылған `cnn`) үзінділерінің бағаларынан есептелген жіктеу. Балл — **калибрленбеген softmax score**, шынайы ықтималдық емес.
- `time_segments[]`: `start`, `end`, `synthetic_score` — модель талдаған нақты уақыт аралықтары. 30 секундқа дейінгі аудиода 4.04 секундтық 1–8 терезе қолданылады; ұзақ файлдың тек **алғашқы 30 секунды** өңделеді. Терезелер бірін-бірі жабуы мүмкін.
- `acoustics.pauses[]`: дыбыс деңгейі төмен ықтимал пауза аралықтары. Тілдік паузаны 100% дәл білдірмейді.
- `acoustics.observations[]`: «ұзақ айқын пауза табылмады», жазбаның clipping-і, деңгей ауытқуы сияқты өлшемдер. Олар **AASIST болжамының нақты себептері емес** — модель ішіндегі себеп-салдар талдауы берілмейді.

Аудионы басқа адам жіберген жағдайда тек тиісті рұқсаты бар жазбаларды пайдаланыңыз. Файл бұл кодта дискіге жазылмайды, бірақ жалпыға жарияланған қызметке кіретін желілік сұраныстар провайдер журналына түсуі мүмкін. Қоғамдық сервиске қосымша қолжетімділікті шектеу және сұраныс лимиттерін қою ұсынылады.

## 4. API

- `GET /api/status` — `aasist`, `cnn`, `language_id`, `ffmpeg` дайындық күйлері.
- `POST /api/analyze` — multipart `file` + `model=aasist|cnn`.
- `GET /api/docs` — FastAPI Swagger.

Аудио форматтары: WAV, MP3, FLAC, OGG, M4A, AAC, OPUS, WEBM. Файл көлемі 20 МБ-тан аспауы керек.

**Нәтиже үлгісі** *(түсіндіру мақсатында көрсетілген сандар — нақты тесттен алынған емес)*:

```json
{
  "verdict": "synthetic",
  "score": 0.74,
  "language": {"code":"kk", "name":"Қазақ тілі", "confidence":0.86, "status":"ok"},
  "explanation": "Модель бағаларының орташа мәні 0,50 шегінен жоғары...",
  "time_segments": [
    {"start":0.0, "end":4.04, "synthetic_score":0.81, "verdict":"synthetic"},
    {"start":3.5, "end":7.54, "synthetic_score":0.67, "verdict":"synthetic"}
  ],
  "acoustics": {"pause_count":1, "pauses":[{"start":2.3, "end":2.8, "duration":0.5}]}
}
```

## 5. Тексеру және шектеулер

```bash
pip install -r requirements.txt
pip install pytest httpx
pytest -q tests/test_app.py
```

Тесттер аудионы декодтау, API валидациясы, нәтижелердің шын модельдің output-ына байланысы (mock session көмегімен), уақыт интервалдары және акустикалық өлшеулердің құрылымын тексереді. **Нақты AASIST және Whisper салмақтарымен жалпы өнімділік/дәлдік бұл тесттермен дәлелденбейді.**

Модель дереккөздері:
- https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST
- https://huggingface.co/Systran/faster-whisper-tiny
- https://huggingface.co/datasets/jungjee/spoofceleb (зерттеу дерегі, модельге автоматты қосылмайды)

Егер тек SpoofCeleb деректерімен оқытылған CNN керек болса, алдымен жеке модельді оқытып, `models/custom_cnn.pt` checkpoint-ін орналастыру, Docker image-ке `torch/librosa` сияқты оқыту/инференс тәуелділіктерін қосу керек. Әзіргі Docker нұсқасы дайын AASIST моделіне бағытталған.
