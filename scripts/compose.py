#!/usr/bin/env python3
"""纯代码音频合成骨架（48 kHz / float64 / 单声道或立体声）。

把 SKILL.md 第 5 节提到的合成技法做成可直接调用的函数，按需增删。
依赖：numpy（SciPy 可选，用于滤波器）。

用法：
    python compose.py --out audio/mix.wav
然后交给 FFmpeg 与画面合成，或先用 ffplay 试听。

注意：
- 所有函数返回 float64 一维/二维数组，取值范围约 [-1, 1]。
- 写 WAV 前务必确认位深与归一化，否则响度可能差几十 dB。
- 最终成片响度用 FFmpeg 统一（网络平台常用 -14 LUFS），峰值留余量。
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

SR = 48_000          # 采样率
RNG = np.random.default_rng(20260101)   # 固定种子，保证每次渲染一致


# ---------------------------------------------------------------- 基础工具

def sec(x: float) -> int:
    """秒 -> 采样点数。"""
    return int(round(x * SR))


def db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def fade(arr: np.ndarray, fade_in: float = 0.005, fade_out: float = 0.02) -> np.ndarray:
    """给音符加淡入淡出，消除爆音（点击声）。"""
    n = arr.size
    ni, no = min(sec(fade_in), n // 2), min(sec(fade_out), n // 2)
    if ni:
        arr[:ni] *= np.linspace(0.0, 1.0, ni)
    if no:
        arr[-no:] *= np.linspace(1.0, 0.0, no)
    return arr


def note(freq: float) -> float:
    """音名 -> 频率。支持 'A4' 'C#5' 'Eb3'；也接受直接的数字频率。"""
    if isinstance(freq, (int, float)):
        return float(freq)
    names = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    name = freq[0].upper()
    rest = freq[1:]
    semis, idx = names[name], 0
    while idx < len(rest) and rest[idx] in "#b":
        semis += 1 if rest[idx] == "#" else -1
        idx += 1
    octave = int(rest[idx:])
    midi = 12 * (octave + 1) + semis
    return 440.0 * 2 ** ((midi - 69) / 12)


# ---------------------------------------------------------------- 音色合成

def saw_detuned(freq: float, dur: float, *, voices: int = 3,
                detune_cents: float = 8.0, lp_hz: float | None = 6000.0) -> np.ndarray:
    """失谐锯齿波铺底（Pad）：多个微失谐的锯齿叠加，空间感强。"""
    t = np.arange(sec(dur)) / SR
    out = np.zeros_like(t)
    for v in range(voices):
        det = 2 ** ((detune_cents * (v - (voices - 1) / 2)) / 1200.0)
        phase = (freq * det * t) % 1.0
        out += 2.0 * phase - 1.0           # 锯齿
    out /= voices
    if lp_hz:                              # 一阶低通，压掉刺耳的高次谐波
        a = np.exp(-2 * np.pi * lp_hz / SR)
        y = np.empty_like(out)
        acc = 0.0
        for i, x in enumerate(out):
            acc = (1 - a) * x + a * acc
            y[i] = acc
        out = y
    return fade(out, 0.05, 0.15)


def fm_bell(freq: float, dur: float, *, ratio: float = 2.0,
            index: float = 5.0, decay: float = 0.35) -> np.ndarray:
    """FM 钟琴 / 电钢：调制指数随时间衰减，起始亮、尾音干净。"""
    t = np.arange(sec(dur)) / SR
    env = np.exp(-t / (dur * decay))
    mod = index * env * np.sin(2 * np.pi * freq * ratio * t)
    out = np.sin(2 * np.pi * freq * t + mod) * env
    return fade(out, 0.002, 0.05)


def karplus_strong(freq: float, dur: float, *, damp: float = 0.996,
                   bright: float = 0.5) -> np.ndarray:
    """Karplus-Strong 拨弦：适合吉他、竖琴、拨奏 Arp。"""
    n = sec(dur)
    period = max(2, int(round(SR / freq)))
    buf = RNG.uniform(-1, 1, period)
    if bright < 1.0:                        # 先做一次平滑，降低初始亮度
        buf = np.convolve(buf, np.array([bright, 1 - bright]), mode="same")
    out = np.empty(n)
    idx = 0
    for i in range(n):
        out[i] = buf[idx]
        nxt = (idx + 1) % period
        buf[idx] = damp * 0.5 * (buf[idx] + buf[nxt])
        idx = nxt
    return fade(out, 0.001, 0.05)


def noise_perc(dur: float, *, decay: float = 0.05,
               hp_hz: float | None = 7000.0, bp_hz: float | None = None) -> np.ndarray:
    """滤波噪声打击乐：镲片（高通）、拍手（带通 + 短衰减）。"""
    n = sec(dur)
    x = RNG.uniform(-1, 1, n)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    if hp_hz:
        spec[freqs < hp_hz] *= 0.02
    if bp_hz:
        band = np.exp(-0.5 * ((freqs - bp_hz) / (bp_hz * 0.35)) ** 2)
        spec *= band
    x = np.fft.irfft(spec, n)
    env = np.exp(-np.arange(n) / (SR * decay))
    return fade(x * env * 0.6, 0.0005, 0.01)


def kick(dur: float = 0.35, *, f_start: float = 120.0, f_end: float = 45.0) -> np.ndarray:
    """下滑正弦底鼓：频率指数下滑 + 快衰减。"""
    n = sec(dur)
    t = np.arange(n) / SR
    f = f_end + (f_start - f_end) * np.exp(-t / 0.035)
    phase = 2 * np.pi * np.cumsum(f) / SR
    env = np.exp(-t / 0.09)
    return fade(np.sin(phase) * env, 0.001, 0.02)


def sweep(dur: float, *, f0: float = 200.0, f1: float = 4000.0) -> np.ndarray:
    """扫频音效：转场、上升引子（riser）。"""
    n = sec(dur)
    t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / dur)
    phase = 2 * np.pi * np.cumsum(f) / SR
    env = np.linspace(0.0, 1.0, n) ** 1.5
    return fade(np.sin(phase) * env * 0.5, 0.01, 0.05)


def branded_sting(root: str = "C5", dur: float = 1.2) -> np.ndarray:
    """品牌音（2~3 个音），用在落版和结尾。root 可传音名（如 'C5'）或频率。"""
    base = note(root)
    seq = [base, base * 2 ** (7 / 12), base * 2]   # 主音 - 五度 - 八度
    step = dur / len(seq) * 0.55
    out = np.zeros(sec(dur))
    for i, f in enumerate(seq):
        start = sec(i * step)
        tone = fm_bell(f, dur - i * step, ratio=2.0, index=3.5, decay=0.5)
        out[start:start + tone.size] += tone[: out.size - start]
    return out / max(1.0, np.abs(out).max())


# ---------------------------------------------------------------- 混音处理

def sidechain(target: np.ndarray, trigger: np.ndarray, *, depth: float = 0.6,
              attack: float = 0.005, release: float = 0.18) -> np.ndarray:
    """侧链压缩：底鼓响时压低 Pad/铺底，做出"呼吸"。"""
    env = np.abs(trigger)
    a = np.exp(-1.0 / (SR * attack))
    r = np.exp(-1.0 / (SR * release))
    smoothed = np.empty_like(env)
    prev = 0.0
    for i, x in enumerate(env):
        coef = a if x > prev else r
        prev = coef * prev + (1 - coef) * x
        smoothed[i] = prev
    gain = 1.0 - depth * np.clip(smoothed / (smoothed.max() + 1e-9), 0, 1)
    return target * gain


def reverb(x: np.ndarray, *, decay: float = 0.6, mix: float = 0.2) -> np.ndarray:
    """极简混响：指数衰减噪声做 IR，FFT 卷积。"""
    ir_len = sec(decay)
    ir = RNG.uniform(-1, 1, ir_len) * np.exp(-np.arange(ir_len) / (SR * decay * 0.35))
    ir /= np.abs(ir).sum() + 1e-9
    wet = np.fft.irfft(np.fft.rfft(x, x.size + ir_len) * np.fft.rfft(ir, x.size + ir_len))
    wet = wet[: x.size]
    return (1 - mix) * x + mix * wet


def normalize(x: np.ndarray, *, peak_db: float = -1.0) -> np.ndarray:
    """峰值归一化（WAV 写出前的最后一步；成片响度再用 FFmpeg 统一）。"""
    peak = np.abs(x).max()
    if peak < 1e-9:
        return x
    return x * (db_to_gain(peak_db) / peak)


# ---------------------------------------------------------------- 导出

def write_wav(path: str | Path, data: np.ndarray, *, sr: int = SR, bit_depth: int = 16) -> None:
    """写 WAV。16/24/32 bit PCM。确认位深与归一化正确，避免响度差几十 dB。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(data, dtype=np.float64)
    if data.ndim == 1:
        data = data[:, None]
    ch = data.shape[1]
    if bit_depth == 16:
        pcm = np.clip(data, -1, 1)
        pcm = (pcm * 32767).astype("<i2")
        sampwidth, raw = 2, pcm.tobytes()
    elif bit_depth == 24:
        # 24bit 小端：每样本取 4 字节 int32 的低 3 字节
        ints = (np.clip(data, -1, 1) * 8388607).astype(np.int32).reshape(-1)
        raw = ints.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
        sampwidth = 3
    else:
        pcm = np.clip(data, -1, 1).astype("<f4")
        sampwidth, raw = 4, pcm.tobytes()

    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(sampwidth)
        w.setframerate(sr)
        w.writeframes(raw)


# ---------------------------------------------------------------- 示例

def demo(bpm: float = 120.0, bars: int = 8) -> np.ndarray:
    """示例：8 小节、120 BPM，每小节 2 秒的极简配乐（可直接替换成你的编曲）。"""
    beat = 60.0 / bpm
    total = sec(beat * 4 * bars)
    pad = np.zeros(total)
    drums = np.zeros(total)

    chord = ["C3", "E3", "G3"]                       # 换和弦只改这里
    for b in range(bars):
        start = sec(b * beat * 4)
        for n_ in chord:
            v = saw_detuned(note(n_), beat * 4, voices=3, detune_cents=7)
            pad[start:start + v.size] += v[: total - start] * db_to_gain(-16)

    for b in range(bars):                            # 底鼓在 1、3 拍
        for beat_idx in (0, 2):
            k = kick()
            s = sec(b * beat * 4 + beat_idx * beat)
            drums[s:s + k.size] += k[: total - s]
    for b in range(bars):                            # 镲片八分音符
        for i in range(8):
            h = noise_perc(0.12, decay=0.04, hp_hz=8000)
            s = sec(b * beat * 4 + i * beat / 2)
            drums[s:s + h.size] += h[: total - s] * db_to_gain(-22)

    pad = reverb(pad, decay=0.8, mix=0.25)
    pad = sidechain(pad, drums, depth=0.55)
    mix = pad + drums

    sting = branded_sting("C5")
    mix[total - sting.size:] += sting * db_to_gain(-10)
    return normalize(mix, peak_db=-1.0)


def main() -> None:
    ap = argparse.ArgumentParser(description="纯代码音频合成示例")
    ap.add_argument("--out", default="out/demo.wav", help="输出 WAV 路径")
    ap.add_argument("--bpm", type=float, default=120.0)
    ap.add_argument("--bars", type=int, default=8)
    ap.add_argument("--bit-depth", type=int, default=16, choices=[16, 24, 32])
    args = ap.parse_args()

    audio = demo(bpm=args.bpm, bars=args.bars)
    write_wav(args.out, audio, bit_depth=args.bit_depth)
    print(f"已写出 {args.out}  |  {audio.size / SR:.2f}s  |  {args.bit_depth}bit  {SR}Hz")


if __name__ == "__main__":
    main()
