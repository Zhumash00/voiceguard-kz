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
