#!/usr/bin/env python3
"""按 timeline.json 逐帧渲染画面（纯代码，无素材）。

    python video/render_frames.py --format preview   # 960x540@30
    python video/render_frames.py --format final     # 1920x1080@60

输出 PNG 序列到 out/frames_<format>/，再用 FFmpeg 合成（见 demo/README 或 plan_v1.md）。
"""

from __future__ import annotations

import argparse
import json
import math
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent

SS = 2          # 超采样倍数，用于抗锯齿


# ---------------------------------------------------------------- 缓动

def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_out_cubic(x: float) -> float:
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def ease_in_out_cubic(x: float) -> float:
    x = clamp01(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_in_out_quart(x: float) -> float:
    x = clamp01(x)
    return 8 * x ** 4 if x < 0.5 else 1 - (-2 * x + 2) ** 4 / 2


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix_rgb(c1, c2, t: float):
    return tuple(int(round(lerp(a, b, t))) for a, b in zip(c1, c2))


# ---------------------------------------------------------------- 音频包络

def load_env(wav_path: Path, fps: float, total_frames: int, n_bars: int = 88,
             window_sec: float = 0.04) -> np.ndarray:
    """返回 (total_frames, n_bars) 的 RMS 包络，供波形场景使用。

    第 j 根柱子对应当前时刻往前第 (n_bars-1-j) 个窗口，因此画面从右往左滚动。
    """
    with wave.open(str(wav_path), "rb") as w:
        sr, n, sw, ch = w.getframerate(), w.getnframes(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(n)
    if sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768
    elif sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        i = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        i = np.where(i >= 1 << 23, i - (1 << 24), i)
        a = i.astype(np.float64) / (1 << 23)
    else:
        a = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)

    win = max(1, int(window_sec * sr))
    step = win // 2
    env = np.zeros((total_frames, n_bars))
    peak = 0.0
    for f in range(total_frames):
        t_cur = f / fps
        idx = int(t_cur * sr)
        for j in range(n_bars):
            end = idx - (n_bars - 1 - j) * step
            start = end - win
            if start < 0 or end <= 0:
                continue
            seg = a[max(0, start):end]
            if seg.size:
                env[f, j] = math.sqrt(float((seg ** 2).mean()))
    peak = env.max() or 1.0
    return env / peak


# ---------------------------------------------------------------- 字体

class Fonts:
    def __init__(self, cfg_fonts: dict, scale: float):
        base = DEMO
        self.regular_path = str(base / cfg_fonts["regular"])
        self.bold_path = str(base / cfg_fonts["bold"])
        self.scale = scale
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def get(self, weight: str, size: int) -> ImageFont.FreeTypeFont:
        path = self.bold_path if weight == "bold" else self.regular_path
        key = (weight, size)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(path, int(size * self.scale))
        return self._cache[key]


def draw_center_text(d: ImageDraw.ImageDraw, cx: float, y: float, text: str,
                     font: ImageFont.FreeTypeFont, fill, alpha: float = 1.0) -> None:
    if alpha <= 0.003:
        return
    if alpha < 0.999:
        fill = (*fill[:3], int(255 * alpha)) if len(fill) == 3 else (*fill[:3], int(fill[3] * alpha))
    bbox = d.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    d.text((cx - w / 2 - bbox[0], y - bbox[1]), text, font=font, fill=fill)


# ---------------------------------------------------------------- 背景

def draw_bg(img: Image.Image, d: ImageDraw.ImageDraw, W: int, H: int,
            palette: dict, beat_pulse: float, t: float) -> None:
    c1, c2 = hex_rgb(palette["bg_from"]), hex_rgb(palette["bg_to"])
    # 竖直渐变
    for y in range(H):
        d.line([(0, y), (W, y)], fill=mix_rgb(c1, c2, y / max(1, H - 1)))
    # 32px 网格（超采样后 32*SS）
    gs = 32 * SS
    alpha = int(8 + 10 * beat_pulse)
    grid = (*hex_rgb(palette["accent"]), alpha)
    for x in range(0, W, gs):
        d.line([(x, 0), (x, H)], fill=grid)
    for y in range(0, H, gs):
        d.line([(0, y), (W, y)], fill=grid)
    # 径向暗角
    vig = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vig)
    cx, cy = W / 2, H / 2
    maxr = math.hypot(cx, cy)
    steps = 60
    for i in range(steps, 0, -1):
        r = maxr * i / steps
        a = int(150 * (i / steps) ** 2.4)
        vd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255 - a)
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), vig)


# ---------------------------------------------------------------- 各场景

def scene_s1(d, W, H, F: Fonts, pal, t_local: float, beat_phase: float, s: float):
    title = "CODE MOTION VIDEO"
    sub = "纯代码 · 画面与配乐都写在代码里"
    f_title = F.get("bold", 108)
    f_sub = F.get("regular", 38)
    cx, cy = W / 2, H * 0.44

    # 逐字入场（垂直按文字实际高度居中，避免超出画幅）
    bbox = d.textbbox((0, 0), title, font=f_title)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x0 = cx - tw / 2
    y_top = cy - th / 2
    per = 0.045                        # 每字入场间隔（秒）
    acc = hex_rgb(pal["accent"])
    tp = hex_rgb(pal["text_primary"])

    cursor = x0
    for i, ch in enumerate(title):
        cw = d.textlength(ch, font=f_title)
        appear = ease_out_cubic((t_local - 0.10 - i * per) / 0.45)
        if appear > 0:
            dy = (1 - appear) * 40 * s
            col = mix_rgb(acc, tp, appear)
            d.text((cursor, y_top + dy - bbox[1]), ch, font=f_title, fill=col)
        cursor += cw

    # 字幕
    sub_a = ease_out_cubic((t_local - 1.05) / 0.7)
    draw_center_text(d, cx, cy + 150 * s, sub, f_sub,
                     (*hex_rgb(pal["text_secondary"]),), sub_a)

    # 琥珀色线条，随拍生长
    line_a = ease_out_cubic((t_local - 0.9) / 0.9)
    if line_a > 0:
        base_w = 420 * s * line_a
        pulse_w = 1 + 0.16 * beat_phase
        hw = base_w * pulse_w / 2
        y = cy + 108 * s
        d.rounded_rectangle([cx - hw, y - 2 * s, cx + hw, y + 2 * s],
                            radius=2 * s, fill=acc)


def scene_s2(d, W, H, F: Fonts, pal, t_local: float, beat_phase: float, s: float,
             env_row: np.ndarray):
    heading = "配乐 = 代码合成"
    sub = "失谐锯齿波 · FM 钟琴 · 滤波噪声 · 侧链压缩"
    f_h = F.get("bold", 84)
    f_sub = F.get("regular", 34)
    cx = W / 2

    a_h = ease_out_cubic((t_local - 0.05) / 0.6)
    draw_center_text(d, cx, H * 0.17, heading, f_h, hex_rgb(pal["text_primary"]), a_h)
    a_s = ease_out_cubic((t_local - 0.35) / 0.6)
    draw_center_text(d, cx, H * 0.17 + 118 * s, sub, f_sub,
                     (*hex_rgb(pal["text_secondary"]),), a_s)

    # 真实音频驱动的波形
    n = len(env_row)
    area_w = W * 0.80
    x0 = cx - area_w / 2
    bar_w = area_w / n
    mid_y = H * 0.60
    max_h = H * 0.20 * (1 + 0.10 * beat_phase)
    acc = hex_rgb(pal["accent"])
    cy2 = hex_rgb(pal["accent2"])
    d.line([(x0, mid_y), (x0 + area_w, mid_y)],
           fill=(*hex_rgb(pal["text_secondary"]), 40), width=max(1, int(1 * s)))
    fade_in = ease_out_cubic((t_local - 0.2) / 0.8)
    for j, v in enumerate(env_row):
        h = float(v) * max_h * fade_in
        if h < 0.5:
            continue
        x = x0 + j * bar_w
        gap = bar_w * 0.28
        col = mix_rgb(cy2, acc, j / max(1, n - 1))
        d.rounded_rectangle([x + gap / 2, mid_y - h, x + bar_w - gap / 2, mid_y + h],
                            radius=max(1, int(bar_w * 0.28)), fill=col)

    cap = "波形由真实音频采样驱动"
    f_cap = F.get("regular", 26)
    a_c = ease_out_cubic((t_local - 1.0) / 0.6)
    draw_center_text(d, cx, mid_y + max_h + 40 * s, cap, f_cap,
                     (*hex_rgb(pal["text_secondary"]),), a_c * 0.85)


def scene_s3(d, W, H, F: Fonts, pal, t_local: float, beat_phase: float, s: float):
    heading = "画面 = 帧驱动"
    sub = "每一帧都由代码算出，参数一改即可复现"
    f_h = F.get("bold", 84)
    f_sub = F.get("regular", 34)
    cx = W / 2

    a_h = ease_out_cubic((t_local - 0.05) / 0.6)
    draw_center_text(d, cx, H * 0.15, heading, f_h, hex_rgb(pal["text_primary"]), a_h)
    a_s = ease_out_cubic((t_local - 0.35) / 0.6)
    draw_center_text(d, cx, H * 0.15 + 118 * s, sub, f_sub,
                     (*hex_rgb(pal["text_secondary"]),), a_s)

    # 点阵脉冲
    cols, rows = 22, 9
    gw, gh = W * 0.78, H * 0.42
    gx0, gy0 = cx - gw / 2, H * 0.44
    dx, dy = gw / (cols - 1), gh / (rows - 1)
    ccx, ccy = cx, gy0 + gh / 2
    acc = hex_rgb(pal["accent"])
    cy2 = hex_rgb(pal["accent2"])
    t_fade = ease_out_cubic((t_local - 0.15) / 0.9)
    for r in range(rows):
        for c in range(cols):
            x = gx0 + c * dx
            y = gy0 + r * dy
            dist = math.hypot(x - ccx, y - ccy) / (gw / 2)
            wave = 0.5 + 0.5 * math.sin(dist * 6.0 - t_local * 4.2)
            rad = (2.0 + 5.0 * wave * beat_phase + 2.0 * wave) * s * t_fade
            if rad < 0.3:
                continue
            col = mix_rgb(cy2, acc, wave)
            d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=col)

    # 旋转方块
    a_sq = ease_out_cubic((t_local - 0.5) / 0.8)
    if a_sq > 0:
        side = 210 * s * (1 + 0.05 * beat_phase)
        rot = t_local * 26
        pts = []
        for k in range(4):
            ang = math.radians(rot + k * 90)
            pts.append((ccx + side / 2 * math.cos(ang), ccy + side / 2 * math.sin(ang)))
        d.line(pts + [pts[0]], fill=(*acc, int(200 * a_sq)), width=max(1, int(2 * s)))


def scene_s4(d, W, H, F: Fonts, pal, t_local: float, beat_phase: float, s: float,
             sting_t: float):
    heading = "零版权风险"
    sub = "BGM 与音效全部代码合成 · 不含任何素材"
    f_h = F.get("bold", 96)
    f_sub = F.get("regular", 36)
    cx, cy = W / 2, H * 0.40

    # 同心圆（配合品牌音扩散）
    acc = hex_rgb(pal["accent"])
    a_ring = ease_out_cubic((t_local - 0.05) / 0.5)
    if a_ring > 0:
        for k in range(3):
            base = clamp01((sting_t - k * 0.16) / 1.6)
            if base <= 0 or base >= 1:
                continue
            r = ease_out_cubic(base) * (H * 0.62)
            alpha = int(140 * (1 - base) ** 1.6 * a_ring)
            if alpha <= 2:
                continue
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      outline=(*acc, alpha), width=max(1, int(2.5 * s)))

    a_h = ease_out_cubic((t_local - 0.25) / 0.6)
    draw_center_text(d, cx, cy - 40 * s, heading, f_h, hex_rgb(pal["text_primary"]), a_h)
    a_s = ease_out_cubic((t_local - 0.6) / 0.7)
    draw_center_text(d, cx, cy + 96 * s, sub, f_sub,
                     (*hex_rgb(pal["text_secondary"]),), a_s)

    # 落版
    a_e = ease_out_cubic((t_local - 1.5) / 0.8)
    if a_e > 0:
        f_e = F.get("bold", 42)
        f_e2 = F.get("regular", 24)
        draw_center_text(d, cx, H * 0.845, "code-motion-video", f_e,
                         hex_rgb(pal["accent"]), a_e)
        draw_center_text(d, cx, H * 0.845 + 54 * s, "画面和配乐，都写在代码里", f_e2,
                         (*hex_rgb(pal["text_secondary"]),), a_e * 0.9)


# ---------------------------------------------------------------- 渲染

class Renderer:
    def __init__(self, tl: dict, fmt: str, env: np.ndarray | None):
        f = tl["formats"][fmt]
        self.fmt = fmt
        self.W, self.H = f["width"] * SS, f["height"] * SS
        self.out_w, self.out_h = f["width"], f["height"]
        self.fps = f["fps"]
        self.total = f["total_frames"]
        self.tl = tl
        self.pal = tl["palette"]
        # 所有字号与间距都按 1080p 基准编写，这里统一换算到目标分辨率再乘超采样倍数
        self.s = SS * (self.out_h / 1080.0)
        self.F = Fonts(tl["fonts"], self.s)
        self.env = env
        self.beat = tl["tempo"]["beat_sec"]
        self.bar = tl["tempo"]["bar_sec"]
        self.scenes = tl["scenes"]

    def scene_index(self, t: float) -> int:
        for i, sc in enumerate(self.scenes):
            if sc["start_sec"] <= t < sc["end_sec"]:
                return i
        return len(self.scenes) - 1

    def render_scene(self, idx: int, t: float) -> Image.Image:
        sc = self.scenes[idx]
        img = Image.new("RGB", (self.W, self.H), (0, 0, 0))
        d = ImageDraw.Draw(img, "RGBA")
        beat_phase = 1.0 - ((t % self.beat) / self.beat)      # 1 = 刚落拍
        beat_pulse = beat_phase ** 2.2
        draw_bg(img, d, self.W, self.H, self.pal, beat_pulse, t)
        d = ImageDraw.Draw(img, "RGBA")
        tl_local = t - sc["start_sec"]

        if sc["id"] == "S1":
            scene_s1(d, self.W, self.H, self.F, self.pal, tl_local, beat_pulse, self.s)
        elif sc["id"] == "S2":
            row = self.env[0] if self.env is None else None
            if self.env is not None:
                fi = min(self.env.shape[0] - 1, max(0, int(round(t * self.fps))))
                row = self.env[fi]
            else:
                row = np.zeros(88)
            scene_s2(d, self.W, self.H, self.F, self.pal, tl_local, beat_pulse, self.s, row)
        elif sc["id"] == "S3":
            scene_s3(d, self.W, self.H, self.F, self.pal, tl_local, beat_pulse, self.s)
        else:
            sting_at = (self.tl["tempo"]["bars"] - 1) * self.bar
            scene_s4(d, self.W, self.H, self.F, self.pal, tl_local, beat_pulse, self.s,
                     t - sting_at)
        return img

    def transition_at(self, t: float):
        """若 t 落在某次转场的窗口内，返回 (前一场景, 后一场景, 进度, 技法)。"""
        for tr in self.tl["transitions"]:
            dur = tr["duration_frames_30"] / 30.0
            half = dur / 2
            if tr["at_sec"] - half <= t < tr["at_sec"] + half:
                p = ease_in_out_cubic((t - (tr["at_sec"] - half)) / dur)
                return tr["from"], tr["to"], p, tr["technique"]
        return None

    def composite_transition(self, old: Image.Image, new: Image.Image,
                             p: float, technique: str) -> Image.Image:
        W, H = self.W, self.H
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        if technique == "color_wipe":
            md.rectangle([0, 0, p * W, H], fill=255)
        elif technique == "mask_split":
            hh = p * H / 2
            md.rectangle([0, H / 2 - hh, W, H / 2 + hh], fill=255)
        else:  # shared_element_zoom：圆形从中心扩张
            r = p * math.hypot(W / 2, H / 2)
            md.ellipse([W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r], fill=255)
        out = Image.composite(new, old, mask)
        # 转场瞬间的琥珀色扫光
        if technique == "color_wipe":
            d = ImageDraw.Draw(out, "RGBA")
            d.rectangle([p * W - 3 * SS, 0, p * W + 3 * SS, H],
                        fill=(*hex_rgb(self.pal["accent"]), 210))
        return out

    def render_frame(self, i: int) -> Image.Image:
        t = i / self.fps
        tr = self.transition_at(t)
        if tr:
            from_id, to_id, p, tech = tr
            idx_from = next(k for k, sc in enumerate(self.scenes) if sc["id"] == from_id)
            idx_to = next(k for k, sc in enumerate(self.scenes) if sc["id"] == to_id)
            old = self.render_scene(idx_from, t)
            new = self.render_scene(idx_to, t)
            img = self.composite_transition(old, new, p, tech)
        else:
            img = self.render_scene(self.scene_index(t), t)
        return img.resize((self.out_w, self.out_h), Image.LANCZOS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", default="preview", choices=["preview", "final"])
    ap.add_argument("--limit", type=int, default=0, help="只渲染前 N 帧（调试用）")
    args = ap.parse_args()

    tl = json.loads((DEMO / "timeline.json").read_text(encoding="utf-8"))
    fmt = args.format
    fps = tl["formats"][fmt]["fps"]
    total = tl["formats"][fmt]["total_frames"]

    wav = DEMO / "out" / "demo_mix.wav"
    env = None
    if wav.exists():
        print(f"载入音频包络: {wav.name} ...")
        env = load_env(wav, fps, total)
        print(f"  包络形状 {env.shape}, 最大值 {env.max():.3f}")
    else:
        print("⚠️ 未找到 out/demo_mix.wav，波形场景将为空。请先跑 audio/compose_demo.py")

    r = Renderer(tl, fmt, env)
    outdir = DEMO / "out" / f"frames_{fmt}"
    outdir.mkdir(parents=True, exist_ok=True)
    n = total if args.limit <= 0 else min(args.limit, total)
    print(f"渲染 {n} 帧 @ {r.out_w}x{r.out_h} {fps}fps → {outdir}")
    for i in range(n):
        r.render_frame(i).save(outdir / f"f{i:05d}.png")
        if (i + 1) % 60 == 0 or i + 1 == n:
            print(f"  {i + 1}/{n}")
    print("完成")


if __name__ == "__main__":
    main()
