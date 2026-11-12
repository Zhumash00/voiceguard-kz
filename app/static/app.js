'use strict';
const $ = id => document.getElementById(id);
const state = { file: null, url: null, status: null, analyzing: false };
const MAX_FILE = 20 * 1024 * 1024;
const extensionOk = name => /\.(wav|mp3|flac|ogg|m4a|aac|opus|webm)$/i.test(name || '');

function changePanel(panel) {
  for (const item of ['result-empty','result-loading','result-ready','result-error']) {
    $(item).classList.toggle('hidden', item !== panel);
  }
}
function formatBytes(n) { return n >= 1048576 ? `${(n/1048576).toFixed(2)} МБ` : `${(n/1024).toFixed(1)} КБ`; }
function hasSelectedModel() {
  return !!state.status && ( $('model-select').value === 'aasist' ? state.status.aasist : state.status.cnn );
}
function updateButton() {
  $('analyze-btn').disabled = !state.file || !hasSelectedModel() || !state.status?.ffmpeg || state.analyzing;
  $('analyze-btn-text').textContent = state.analyzing ? 'Талдау орындалуда...' : 'Нейрожелімен тексеру';
}
function showError(msg, title='Талдау мүмкін болмады') {
  $('error-title').textContent = title;
  $('error-message').textContent = msg;
  changePanel('result-error');
}
async function loadStatus() {
  const pill = $('model-pill');
  try {
    const response = await fetch('/api/status', {cache:'no-store'});
    if (!response.ok) throw new Error();
    state.status = await response.json();
    const online = state.status.aasist && state.status.ffmpeg;
    pill.innerHTML = `<span class="dot ${online?'online':'offline'}"></span><span>${online?'AI моделі дайын':'Орнатуды аяқтау керек'}</span>`;
    if (!state.status.aasist) {
      showError('AASIST файлы әлі жүктелмеген. Терминалда «python scripts/download_model.py» орындап, бетті жаңартыңыз.', 'Нейрожелі моделі орнатылмаған');
    } else if (!state.status.ffmpeg) {
      showError('FFmpeg орнатып, оны жүйенің PATH айнымалысына қосыңыз.', 'FFmpeg табылмады');
    } else {
      changePanel('result-empty');
    }
  } catch {
    pill.innerHTML = '<span class="dot offline"></span><span>Сервер қолжетімсіз</span>';
    showError('Сервер іске қосылмаған. README.md ішіндегі start.bat немесе uvicorn командасын пайдаланыңыз.', 'Сервермен байланыс жоқ');
  }
  updateButton();
}
function clearFile() {
  state.file = null;
  $('file-input').value = '';
  $('file-preview').classList.add('hidden');
  if (state.url) URL.revokeObjectURL(state.url);
  state.url = null;
  $('audio-player').removeAttribute('src');
  updateButton();
  if (state.status?.aasist && state.status.ffmpeg) changePanel('result-empty');
}
async function drawWaveform(file) {
  const canvas = $('waveform');
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const w = canvas.width = Math.max(340, Math.round(canvas.getBoundingClientRect().width*2));
  const h = canvas.height = 86;
  ctx.clearRect(0,0,w,h);
  try {
    const buf = await file.arrayBuffer();
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const decoded = await ac.decodeAudioData(buf.slice(0));
    const data = decoded.getChannelData(0);
    const columns = Math.floor(w / 5);
    const step = Math.max(1,Math.floor(data.length/columns));
    for (let i=0;i<columns;i++) {
      let peak=0;
      for(let j=i*step;j<Math.min(data.length,(i+1)*step);j+=Math.max(1,Math.floor(step/35))){peak=Math.max(peak,Math.abs(data[j]));}
      const hh=Math.max(2, Math.min(35, peak*35));
      ctx.fillStyle = i < columns*.65 ? '#5fdac5' : '#3f7891';
      ctx.fillRect(i*5+1,h/2-hh,2.8,hh*2);
    }
    await ac.close();
  } catch {
    // If the browser cannot decode a codec, do not draw an invented waveform.
    ctx.strokeStyle = '#527b8b';
    ctx.beginPath();ctx.moveTo(0,h/2);ctx.lineTo(w,h/2);ctx.stroke();
    ctx.fillStyle = '#8faabb';ctx.font = '21px sans-serif';
    ctx.fillText('Браузер бұл аудионы көрсете алмады', 6, 23);
  }
}
function handleFile(file) {
  if (!file) return;
  if (!extensionOk(file.name)) { showError('Бұл файл форматына қолдау жоқ. WAV, MP3, FLAC, M4A, OGG не WEBM таңдаңыз.'); return; }
  if (file.size > MAX_FILE) { showError('Файл көлемі 20 МБ-тан аспауы тиіс.');return; }
  if (!file.size) {showError('Файл бос.');return;}
  clearFile();
  state.file=file;
  $('file-name').textContent=file.name;
  $('file-size').textContent=formatBytes(file.size);
  state.url=URL.createObjectURL(file);
  $('audio-player').src=state.url;
  $('file-preview').classList.remove('hidden');
  if (state.status?.aasist) changePanel('result-empty');
  drawWaveform(file);
  updateButton();
}
async function analyze() {
  if (!state.file || state.analyzing) return;
  if (!hasSelectedModel()) return showError('Бұл модель әлі орнатылмаған немесе оқытылмаған. README.md нұсқаулығын қараңыз.');
  state.analyzing = true;
  updateButton();
  changePanel('result-loading');
  try {
    const body = new FormData();
    body.append('file', state.file);
    body.append('model', $('model-select').value);
    const res = await fetch('/api/analyze', {method:'POST',body});
    let result; try {result=await res.json();} catch {result={detail:'Сервер жауабы жарамсыз.'};}
    if (!res.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Талдау кезінде сервер қатесі болды.');
    if (!Number.isFinite(result.score)) throw new Error('Модель сандық нәтиже қайтармады.');
    const synthetic = result.verdict === 'synthetic';
    $('verdict-icon').textContent = synthetic ? '!' : '✓';
    $('verdict-icon').classList.toggle('synthetic', synthetic);
    $('verdict-title').textContent = synthetic ? 'Синтетикалық дауыс белгілері' : 'Табиғи дауыс белгілері';
    $('verdict-desc').textContent = synthetic ? 'Нейрожелі жасанды сөйлеуге тән ерекшеліктер байқады.' : 'Нейрожелі табиғи сөйлеуге тән ерекшеліктер байқады.';
    $('score-number').textContent = `${(result.score*100).toFixed(1)}%`;
    $('score-fill').style.width = `${Math.min(100,Math.max(0,result.score*100))}%`;
    $('segment-count').textContent = result.segments;
    $('duration-val').textContent = `${result.analyzed_seconds.toFixed(1)} с`;
    $('model-val').textContent = result.model === 'cnn' ? 'Mel-CNN' : 'AASIST';
    renderLanguage(result.language);
    $('decision-explanation').textContent = result.explanation || 'Нейрожелінің бағасы көрсетілді.';
    renderTimeline(result.time_segments);
    renderAcoustics(result.acoustics);
    changePanel('result-ready');
  } catch(err) {showError(err.message || 'Белгісіз қате.');}
  finally {state.analyzing=false;updateButton();}
}
function readableTime(x) {
  x = Number.isFinite(Number(x)) ? Math.max(0, Number(x)) : 0;
  return `${Math.floor(x / 60).toString().padStart(2,'0')}:${(x % 60).toFixed(1).padStart(4,'0')}`;
}
function seekAudio(start) {
  const player = $('audio-player');
  if (!player.src) return;
  player.currentTime = Math.max(0, Number(start) || 0);
  player.play().catch(() => {});
}
function renderTimeline(items) {
  const root = $('time-segments'); root.replaceChildren();
  if (!Array.isArray(items) || !items.length) {
    const p = document.createElement('p');p.textContent='Уақыттық бағалар жоқ.';root.appendChild(p);return;
  }
  items.forEach((s,i)=>{
    const score = Math.max(0,Math.min(1,Number(s.synthetic_score)||0));
    const button = document.createElement('button');
    button.className = `timeline-item ${score >= 0.5?'suspect':'normal'}`;
    button.type='button';
    const label=document.createElement('span');label.className='timeline-range';
    label.textContent=`${readableTime(s.start)} – ${readableTime(s.end)}`;
    const chart=document.createElement('span');chart.className='timeline-track';
    const fill=document.createElement('span');fill.style.width=`${score*100}%`;chart.appendChild(fill);
    const badge=document.createElement('strong');badge.className='timeline-score';
    badge.textContent=`${(score*100).toFixed(1)}%`;
    button.append(label,chart,badge);
    button.title = 'Аудионы осы жерден тыңдау';
    button.addEventListener('click',()=>seekAudio(s.start));
    root.appendChild(button);
  });
}
function renderAcoustics(acoustics) {
  const root=$('acoustic-observations');root.replaceChildren();
  const items=acoustics?.observations || [];
  for (const o of items) {
    const box=document.createElement('article');box.className='acoustic-item';
    const header=document.createElement('strong');header.textContent=o.title || 'Бақылау';
    const time=document.createElement('button');time.type='button';time.className='time-jump';
    time.textContent=`${readableTime(o.start)} – ${readableTime(o.end)}`;
    time.addEventListener('click',()=>seekAudio(o.start));
    const detail=document.createElement('p');detail.textContent=o.detail || '';
    box.append(header,time,detail);root.appendChild(box);
  }
  if(!items.length){const empty=document.createElement('p');empty.textContent='Қосымша өлшемдер жоқ.';root.appendChild(empty);}
  const pauses=$('pause-segments');pauses.replaceChildren();
  const ranges=acoustics?.pauses || [];
  if(!ranges.length){const p=document.createElement('p');p.textContent='0,30 секундтан ұзақ ішкі төмен деңгейлі аралық табылмады.';pauses.appendChild(p);}
  for(const pause of ranges) {
    const jump=document.createElement('button');jump.type='button';jump.className='pause-jump';
    jump.textContent=`${readableTime(pause.start)} – ${readableTime(pause.end)} · ${pause.duration.toFixed(2)} с`;
    jump.addEventListener('click',()=>seekAudio(pause.start));pauses.appendChild(jump);
  }
}
function renderLanguage(language) {
  $('language-name').textContent = language?.name || 'Анықталмады';
  const pct = Number(language?.confidence);
  $('language-confidence').textContent = language?.status === 'ok' && Number.isFinite(pct)
     ? `Whisper Tiny бағасы: ${(pct*100).toFixed(1)}% · болжам` : (language?.note || 'Тіл белгісіз');
}

function init() {
  $('dropzone').addEventListener('click',()=>$('file-input').click());
  $('dropzone').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('file-input').click();}});
  $('file-input').addEventListener('change',e=>handleFile(e.target.files[0]));
  for (const type of ['dragover','dragenter']) $('dropzone').addEventListener(type,e=>{e.preventDefault();$('dropzone').classList.add('dragging');});
  for (const type of ['dragleave','drop']) $('dropzone').addEventListener(type,e=>{e.preventDefault();$('dropzone').classList.remove('dragging');});
  $('dropzone').addEventListener('drop',e=>handleFile(e.dataTransfer.files[0]));
  $('clear-file').addEventListener('click',clearFile);
  $('analyze-btn').addEventListener('click',analyze);
  $('model-select').addEventListener('change',()=>{updateButton();if(state.file&& !hasSelectedModel()){showError('Бұл модель әзірге орнатылмаған немесе оқытылмаған.','Модель дайын емес');}else if(state.status?.aasist){changePanel('result-empty');}});
  $('retry-btn').addEventListener('click',()=>{if(state.file && hasSelectedModel()) analyze(); else loadStatus();});
  loadStatus();
}
document.addEventListener('DOMContentLoaded',init);


/* =========================================
   VOICEGUARD KZ - AUDIO DENOISE
========================================= */

const denoiseFileInput = $("denoise-file-input");
const denoiseFileList = $("denoise-file-list");
const denoiseButton = $("denoiseButton");
const denoiseStrength = $("denoiseStrength");
const strengthValue = $("strengthValue");
const noiseSeconds = $("noiseSeconds");
const denoiseStatus = $("denoiseStatus");
const denoiseResults = $("denoiseResults");

const denoiseObjectUrls = [];

const AUDIO_EXTENSIONS = [
    ".wav", ".flac", ".mp3", ".m4a",
    ".ogg", ".aac", ".opus", ".webm"
];

/* Файл кеңейтімін анықтау */

function getExtension(filename) {
    const parts = filename.toLowerCase().split(".");
    return parts.length > 1 ? "." + parts.pop() : "";
}

function isZip(filename) {
    return getExtension(filename) === ".zip";
}

function isAudio(filename) {
    return AUDIO_EXTENSIONS.includes(getExtension(filename));
}

/* Уақытша URL мекенжайларын босату */

function clearDenoiseResults() {
    denoiseObjectUrls.forEach(url => URL.revokeObjectURL(url));
    denoiseObjectUrls.length = 0;

    denoiseResults.replaceChildren();
}

/* Файлдарды көрсету */

function updateDenoiseFileList() {

    const files = Array.from(denoiseFileInput.files || []);

    denoiseFileList.replaceChildren();

    if (!files.length) {
        denoiseFileList.textContent = "Файлдар таңдалмаған";
        return;
    }

    const title = document.createElement("strong");
    title.textContent = `Таңдалған файлдар: ${files.length}`;

    denoiseFileList.appendChild(title);

    files.forEach(file => {

        const item = document.createElement("div");

        item.style.marginTop = "8px";
        item.style.color = "#a9c4d2";

        const size = (file.size / 1048576).toFixed(2);

        item.textContent = `${file.name} (${size} МБ)`;

        denoiseFileList.appendChild(item);

    });

}

/* Шу басу күшінің көрсеткіші */

if (denoiseStrength && strengthValue) {

    denoiseStrength.addEventListener("input", () => {

        const value = Number(denoiseStrength.value);

        strengthValue.textContent =
            `${Math.round(value * 100)}%`;

    });

}

/* Файл таңдалған кезде */

if (denoiseFileInput) {

    denoiseFileInput.addEventListener("change", () => {

        updateDenoiseFileList();

        clearDenoiseResults();

        denoiseStatus.textContent = "";

    });

}

/* Сервер қатесін оқу */

async function getApiError(response, defaultMessage) {

    try {

        const data = await response.json();

        return typeof data.detail === "string"
            ? data.detail
            : defaultMessage;

    } catch {

        return defaultMessage;

    }

}

/* Бір аудионы тазарту */

async function denoiseSingleFile(file, strength, noiseSec) {

    const formData = new FormData();

    formData.append("file", file);

    const response = await fetch(
        `/api/denoise?strength=${strength}&noise_sec=${noiseSec}`,
        {
            method: "POST",
            body: formData
        }
    );

    if (!response.ok) {

        throw new Error(
            await getApiError(
                response,
                "Аудионы тазарту мүмкін болмады."
            )
        );

    }

    return await response.blob();

}

/* Бірнеше аудионы тазарту */

async function denoiseBatch(files, strength, noiseSec) {

    const formData = new FormData();

    files.forEach(file => {

        formData.append("files", file);

    });

    const response = await fetch(
        `/api/denoise/batch?strength=${strength}&noise_sec=${noiseSec}`,
        {
            method: "POST",
            body: formData
        }
    );

    if (!response.ok) {

        throw new Error(
            await getApiError(
                response,
                "Бірнеше аудионы тазарту мүмкін болмады."
            )
        );

    }

    return await response.blob();

}

/* ZIP архивін тазарту */

async function denoiseZip(file, strength, noiseSec) {

    const formData = new FormData();

    formData.append("file", file);

    const response = await fetch(
        `/api/denoise/zip?strength=${strength}&noise_sec=${noiseSec}`,
        {
            method: "POST",
            body: formData
        }
    );

    if (!response.ok) {

        throw new Error(
            await getApiError(
                response,
                "ZIP архивін өңдеу мүмкін болмады."
            )
        );

    }

    return await response.blob();

}

/* Жүктеу батырмасын жасау */

function createDownload(blob, filename, title) {

    const url = URL.createObjectURL(blob);

    denoiseObjectUrls.push(url);

    const container = document.createElement("div");
    container.className = "denoise-result";

    const heading = document.createElement("h3");
    heading.textContent = title;

    const download = document.createElement("a");

    download.href = url;
    download.download = filename;
    download.className = "download-button";
    download.textContent = "Тазартылған файлды жүктеу";

    container.append(heading, download);

    denoiseResults.appendChild(container);

}

/* Тазартылған аудионы ойнату */

function addAudioResult(originalName, blob) {

    const url = URL.createObjectURL(blob);

    denoiseObjectUrls.push(url);

    const container = document.createElement("div");

    container.className = "denoise-result";

    const title = document.createElement("h3");

    title.textContent = `${originalName} — тазартылған`;

    const audio = document.createElement("audio");

    audio.controls = true;
    audio.preload = "metadata";
    audio.src = url;

    const download = document.createElement("a");

    download.href = url;

    download.download =
        originalName.replace(/\.[^/.]+$/, "") + "_clean.wav";

    download.textContent = "Тазартылған аудионы жүктеу";

    download.className = "download-button";

    container.append(title, audio, download);

    denoiseResults.appendChild(container);

}

/* =========================================
   НЕГІЗГІ ШУДЫ ТАЗАРТУ ФУНКЦИЯСЫ
========================================= */

async function processDenoise() {

    const files = Array.from(
        denoiseFileInput.files || []
    );

    if (!files.length) {

        denoiseStatus.textContent =
            "Алдымен аудио файл немесе ZIP архивін таңдаңыз.";

        return;

    }

    const invalidFiles = files.filter(
        file => !isAudio(file.name) && !isZip(file.name)
    );

    if (invalidFiles.length) {

        denoiseStatus.textContent =
            "Қолдау көрсетілмейтін файл форматы таңдалды.";

        return;

    }

    if (files.some(file => file.size === 0)) {

        denoiseStatus.textContent =
            "Таңдалған файлдардың ішінде бос файл бар.";

        return;

    }

    const strength = Number(denoiseStrength.value);
    const noiseSec = Number(noiseSeconds.value);

    if (!Number.isFinite(strength) || strength < 0 || strength > 1) {

        denoiseStatus.textContent =
            "Шу басу күшінің мәні дұрыс емес.";

        return;

    }

    if (!Number.isFinite(noiseSec) || noiseSec < 0 || noiseSec > 10) {

        denoiseStatus.textContent =
            "Шу үлгісінің ұзақтығы 0–10 секунд аралығында болуы керек.";

        return;

    }

    const zipFiles = files.filter(file => isZip(file.name));

    const audioFiles = files.filter(file => isAudio(file.name));

    denoiseButton.disabled = true;

    clearDenoiseResults();

    denoiseStatus.textContent =
        "Аудио өңделуде. Күте тұрыңыз...";

    try {

        let completed = 0;

        const total = zipFiles.length + (audioFiles.length ? 1 : 0);

        /* ZIP архивтерін өңдеу */

        for (const zipFile of zipFiles) {

            denoiseStatus.textContent =
                `ZIP архиві өңделуде: ${zipFile.name}`;

            const result = await denoiseZip(
                zipFile,
                strength,
                noiseSec
            );

            const outputName =
                zipFile.name.replace(/\.zip$/i, "") +
                "_clean.zip";

            createDownload(
                result,
                outputName,
                `${zipFile.name} — тазартылған архив`
            );

            completed++;

        }

        /* Жеке аудиоларды өңдеу */

        if (audioFiles.length === 1) {

            denoiseStatus.textContent =
                "Аудио тазартылуда...";

            const file = audioFiles[0];

            const result = await denoiseSingleFile(
                file,
                strength,
                noiseSec
            );

            addAudioResult(file.name, result);

            completed++;

        }

        /* Бірнеше аудио файлды өңдеу */

        else if (audioFiles.length > 1) {

            denoiseStatus.textContent =
                `${audioFiles.length} аудио файл өңделуде...`;

            const result = await denoiseBatch(
                audioFiles,
                strength,
                noiseSec
            );

            createDownload(
                result,
                "voiceguard_clean_audio.zip",
                "Барлық тазартылған аудиолар"
            );

            completed++;

        }

        if (completed === total) {

            denoiseStatus.textContent =
                "Шуды тазарту сәтті аяқталды.";

        }

    } catch (error) {

        denoiseStatus.textContent =
            `Қате: ${error.message}`;

    } finally {

        denoiseButton.disabled = false;

    }

}

/* Батырмаға оқиға тіркеу */

if (denoiseButton) {

    denoiseButton.addEventListener(
        "click",
        processDenoise
    );

}