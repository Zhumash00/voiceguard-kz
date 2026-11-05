"""Transparent signal-level observations; NOT an attribution of the AASIST decision."""
from __future__ import annotations
import numpy as np

SR = 16000
HOP = 160   # 10 ms
FRAME = 400  # 25 ms
MIN_PAUSE_SEC = 0.30


def _intervals(mask: np.ndarray, seconds_per_step: float) -> list[tuple[float, float]]:
    intervals = []
    start = None
    for idx in range(len(mask) + 1):
        val = bool(mask[idx]) if idx < len(mask) else False
        if val and start is None:
            start = idx
        if not val and start is not None:
            intervals.append((start * seconds_per_step, idx * seconds_per_step))
            start = None
    return intervals


def acoustic_observations(audio: np.ndarray, rate: int = SR) -> dict:
    """Find low-energy regions (candidate pauses), dynamic level and clipping.

    Silence is an amplitude heuristic, not a speech recognizer and not proof of AI.
    No signal-based observation changes the neural model's score.
    """
    audio = np.asarray(audio, dtype=np.float32)
    duration = len(audio) / rate
    hop = max(1, round(HOP * rate / SR))
    frame = max(1, round(FRAME * rate / SR))
    # Pad just the final frame and retain a correct time axis.
    levels = []
    for start in range(0, len(audio), hop):
        chunk = audio[start:start + frame]
        levels.append(float(np.sqrt(np.mean(chunk.astype(np.float64)**2))) if chunk.size else 0.0)
    rms = np.asarray(levels, dtype=np.float64)
    if rms.size == 0:
        return {'pauses': [], 'pause_count': 0, 'pause_ratio': 0., 'clipping_ratio': 0., 'level_variation_db': 0., 'observations': []}
    reference = float(np.percentile(rms, 85))
    # Recording gain varies by device; dynamic cutoff with an absolute noise floor.
    cutoff = max(0.0025, reference * 0.17)
    low = rms < cutoff
    # Smooth isolated frame flicker without inventing pauses. 30 ms majority voting.
    if len(low) >= 3:
        low = np.convolve(low.astype(float), [1/3]*3, mode='same') >= 2/3
    raw_ranges = _intervals(low, hop / rate)
    pauses = []
    for start, end in raw_ranges:
        end = min(end, duration)
        # Reject leading/trailing gaps as speech pauses; include as silence facts if needed.
        if end - start >= MIN_PAUSE_SEC and start >= 0.1 and end <= duration - 0.1:
            pauses.append({'start': round(start, 2), 'end': round(end, 2), 'duration': round(end-start, 2),
                           'label': 'Төмен дыбыс деңгейі (ықтимал пауза)'})
    # Percentage reflects low-energy frames, not actual linguistic silence.
    pause_ratio = float(np.mean(low))
    active = rms[rms >= cutoff]
    if len(active) >= 2:
        db = 20 * np.log10(np.maximum(active, 1e-6))
        level_variation = float(np.percentile(db, 85)-np.percentile(db, 15))
    else:
        level_variation = 0.
    clipping_ratio = float(np.mean(np.abs(audio) >= 0.995))
    observations = []
    if duration >= 4.0 and len(pauses) == 0:
        observations.append({'kind':'pause','start':0.,'end':round(duration,2),
            'title':'Ұзақ айқын пауза табылмады',
            'detail':'Сигнал деңгейі бойынша 0,30 секундтан ұзақ ішкі тыныш аралық байқалмады. Бұл қалыпты жылдам сөйлеуде де болады және дипфейкті дәлелдемейді.'})
    elif pauses:
        observations.append({'kind':'pause','start':pauses[0]['start'],'end':pauses[0]['end'],
            'title': f'{len(pauses)} ықтимал пауза байқалды',
            'detail':'Төмен амплитуда аймақтары табылды. Олар тыныс, үнсіздік не жазбадағы шу деңгейінің ауысуы болуы мүмкін; тек осы белгімен дауыс түпнұсқалығы анықталмайды.'})
    if clipping_ratio >= 0.015:
        observations.append({'kind':'clipping','start':0.,'end':round(duration,2),
            'title':'Сигналдың шектелуі (clipping) байқалды',
            'detail':f'Сэмплдердің {clipping_ratio*100:.1f}%-ы шекті деңгейге жақын. Бұл жазу/өңдеу сапасына қатысты, жасанды дауыс дәлелі емес.'})
    # Compare adjacent 200 ms blocks, but only when both contain sound;
    # this may flag edits or normal speech emphasis, never AI authorship.
    if duration >= 2 and reference > 0.015:
        block = max(1, round(0.2 * rate / hop))
        events = []
        for i in range(block, len(rms) - block, block):
            left = float(np.median(rms[i-block:i]))
            right = float(np.median(rms[i:i+block]))
            if left < cutoff * 1.5 or right < cutoff * 1.5:
                continue
            difference = abs(20 * np.log10((left + 1e-8) / (right + 1e-8)))
            if difference >= 13 and (not events or i*hop/rate-events[-1][0] > 0.4):
                events.append((i * hop / rate, difference))
        for loc, change in events[:3]:
            observations.append({'kind':'level_shift',
                'start':round(max(0.,loc-0.2),2), 'end':round(min(duration,loc+0.2),2),
                'title':'Дыбыс деңгейі қысқа аралықта күрт өзгерді',
                'detail':f'Шамамен {change:.1f} дБ өзгеріс тіркелді. Бұл қалыпты екпін, монтаж немесе жазба жағдайынан болуы мүмкін, дипфейк дәлелі емес.'})
    if duration >= 2:
        observations.append({'kind':'volume','start':0.,'end':round(duration,2),
            'title':'Дыбыс деңгейінің ауытқуы өлшенді',
            'detail':f'Белсенді кадрлардағы дыбыс деңгейінің 15–85-процентиль аралығы: {level_variation:.1f} дБ. Төмен немесе жоғары ауытқу жеке өзі synthetic/real екенін көрсетпейді.'})
    return {'pauses': pauses[:25], 'pause_count': len(pauses),
            'pause_ratio': round(pause_ratio, 3), 'clipping_ratio': round(clipping_ratio, 4),
            'level_variation_db': round(level_variation, 1), 'observations': observations}
