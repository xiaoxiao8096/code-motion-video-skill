#!/usr/bin/env python3
"""按 timeline.json 合成 16 秒原创配乐（无任何采样、无 AI 生成）。

直接复用 ../code-motion-video-skill/scripts/compose.py 里的合成函数，
证明那套脚本是能跑的。

    python audio/compose_demo.py --out out/demo_mix.wav
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
ROOT = DEMO.parent

# 复用 skill 里的合成模块
sys.path.insert(0, str(ROOT / "code-motion-video-skill" / "scripts"))
import compose as cm  # noqa: E402

SR = cm.SR


# ------------------------------------------------------------------ 工具

def place(track: np.ndarray, clip: np.ndarray, at_sec: float, gain_db: float = 0.0) -> None:
    """把 clip 叠加到 track 的指定时间位置（就地写入）。"""
    start = int(round(at_sec * SR))
    if start >= track.size:
        return
    end = min(track.size, start + clip.size)
    track[start:end] += clip[: end - start] * cm.db_to_gain(gain_db)


def load_timeline() -> dict:
    with open(DEMO / "timeline.json", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ 编曲

def build(tl: dict) -> np.ndarray:
    dur = tl["tempo"]["duration_sec"]
    beat = tl["tempo"]["beat_sec"]
    bar = tl["tempo"]["bar_sec"]
    total = int(dur * SR)

    pad = np.zeros(total)
    kick_tr = np.zeros(total)
    hat_tr = np.zeros(total)
    arp_tr = np.zeros(total)
    sfx_tr = np.zeros(total)

    # ---- Pad：每小节一个和弦，3 声部失谐锯齿波
    for ch in tl["chords"]:
        t0 = (ch["bar"] - 1) * bar
        for name in ch["notes"]:
            v = cm.saw_detuned(cm.note(name), bar, voices=3, detune_cents=7, lp_hz=5200)
            place(pad, v, t0, gain_db=-18)

    # ---- 鼓：底鼓在每小节 1、3 拍；镲片每个八分音符
    n_bars = tl["tempo"]["bars"]
    for b in range(n_bars):
        t_bar = b * bar
        for beat_idx in (0, 2):
            place(kick_tr, cm.kick(), t_bar + beat_idx * beat, gain_db=-3)
        for i in range(8):
            place(hat_tr, cm.noise_perc(0.12, decay=0.045, hp_hz=8200),
                  t_bar + i * beat / 2, gain_db=-25)

    # ---- 琶音：从 S2（第 3 小节）开始进入，Karplus-Strong 拨弦
    arp_notes = tl["arp_notes"]
    k = 0
    for b in range(2, n_bars):                       # 第 3~8 小节
        for i in range(8):
            nm = arp_notes[k % len(arp_notes)]
            k += 1
            place(arp_tr, cm.karplus_strong(cm.note(nm), 0.45, damp=0.9955, bright=0.55),
                  b * bar + i * beat / 2, gain_db=-19)

    # ---- 音效：转场 riser / impact
    for tr in tl["transitions"]:
        at = tr["at_sec"] - tr.get("sfx_lead_sec", 0.0)
        sfx = tr["sfx"]
        if sfx in ("riser", "riser_impact"):
            lead = tr.get("sfx_lead_sec", 0.4)
            place(sfx_tr, cm.sweep(max(lead, 0.25), f0=220, f1=4200), at, gain_db=-14)
        if sfx in ("impact", "riser_impact"):
            place(sfx_tr, cm.noise_perc(0.5, decay=0.12, bp_hz=1200), tr["at_sec"], gain_db=-10)

    # ---- 品牌音：第 8 小节（14.0s）落版
    place(sfx_tr, cm.branded_sting("C5", dur=1.6), (n_bars - 1) * bar, gain_db=-7)

    # ---- 混音
    kick_tr = cm.normalize(kick_tr, peak_db=-3)
    pad = cm.reverb(pad, decay=0.9, mix=0.28)
    pad = cm.sidechain(pad, kick_tr, depth=0.55)
    arp_tr = cm.reverb(arp_tr, decay=0.5, mix=0.18)
    sfx_tr = cm.reverb(sfx_tr, decay=0.7, mix=0.22)

    mix = pad + kick_tr + hat_tr + arp_tr + sfx_tr
    return cm.normalize(mix, peak_db=-1.5)   # 峰值留余量，成片响度再交给 FFmpeg 统一


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEMO / "out" / "demo_mix.wav"))
    ap.add_argument("--bit-depth", type=int, default=24, choices=[16, 24, 32])
    args = ap.parse_args()

    tl = load_timeline()
    audio = build(tl)
    out = Path(args.out)
    if not out.is_absolute():
        out = DEMO / out if str(out).startswith("out") else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cm.write_wav(out, audio, bit_depth=args.bit_depth)

    rms = float(np.sqrt((audio ** 2).mean()))
    print(f"已写出 {out}")
    print(f"时长 {audio.size / SR:.2f}s | 峰值 {np.abs(audio).max():.3f} | "
          f"RMS {20 * np.log10(rms + 1e-12):.1f} dBFS | {args.bit_depth}bit {SR}Hz")


if __name__ == "__main__":
    main()
