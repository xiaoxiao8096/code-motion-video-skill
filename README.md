# code-motion-video

**纯代码动画视频制作规范 —— 画面、动效、转场、配乐、音效、排版全部由代码产出，全程不用 AI 视频或音乐生成模型。**

适合产品介绍、片头、宣传片、发布会开场、自我介绍等 15–60 秒短片。

> 产出物 100% 可控、可复现、可改参数重渲染；**没有任何版权风险** —— BGM 和音效都是当场合成出来的，不是采样、不是 AI 生成。

---

## 为什么用它，而不是那些「脚本一键出片」的

| 能力 | 本 Skill | 常见「AI 出片」类 Skill |
|---|---|---|
| 画面 | 代码帧驱动渲染，每个像素可按帧控制 | 生成模型出图，细节不可控、不可复现 |
| **配乐** | ✅ **Python 自写合成器现场合成**（锯齿波铺底 / FM 钟琴 / Karplus-Strong 拨弦 / 侧链压缩 / 混响） | ❌ 用"免费占位 BGM"或外部素材 |
| **音效** | ✅ **噪声 + 扫频 + 共振合成**（镲、拍手、底鼓、转场 riser） | ❌ 无，或依赖素材库 |
| 版权 | ✅ **原创，零版权风险** | ⚠️ 依赖所文字体/素材/模型的授权 |
| 一致性 | ✅ 固定随机种子，每次渲染结果相同 | ⚠️ 每次生成都不同，改一版要重来 |
| 工程化 | ✅ **8 阶段确认制** + 统一时间轴 `timeline.json`，画面与音频共用一个节拍 | ❌ 给一段文案，直接黑箱出片 |
| 文案 | ✅ 内置**去 AI 腔**环节（去排比、去空洞口号、给前后对照表） | ❌ 无 |

**一句话：** 如果你要的是"能拿去正式发布的产品片"，选它；如果你要的是"随便出个东西发朋友圈"，那用 AI 生成更省事。

---

## 你需要自备什么（本 Skill 不内置任何素材）

**本仓库只包含流程规范与脚本，不打包字体、图片、Logo、音乐或模板。** 所有外部素材由你自己提供，放进自己的工程目录：

| 资源 | 是否必需 | 说明 |
|---|---|---|
| **字体文件** | ✅ 必需 | 只用可商用许可（如 SIL OFL）。放 `fonts/` 本地加载，不依赖系统字体或 CDN |
| **事实来源材料** | ✅ 必需 | 主角官网 / 发布文章 / 产品文档 —— 片中事实与卖点只能来自这些 |
| **品牌素材**（Logo、产品图、截图） | 视项目 | 必须确认授权；商标图形未经授权只能内部预览，公开发布前须取得许可 |
| **品牌规范**（色板 hex、版式、slogan） | 可选 | 有就提供，没有由流程第 4 步给出多套视觉方向供选 |
| **音频参考风格** | 可选 | 只作风格参照，**不采样、不扒带**；旋律与音色由代码重新合成 |

**不需要**你提供 BGM 或音效文件 —— 音频在本流程里是由代码当场合成的（见 `scripts/compose.py`），这正是它零版权风险的原因。

素材请走 `assets/`、`fonts/` 相对路径，方便替换；没有的素材在方案里标注「待提供」，不要用占位图冒充成品。

---

## 效果预览

![preview](docs/preview.gif)

上面这支 **16 秒片完全由本流程产出**，源工程就在 `demo/` 里，可复现、可改参数重渲染。

| 文件 | 内容 |
|---|---|
| `docs/preview.mp4` | 正式版 1920×1080 / 60fps / H.264+AAC，响度 **-14.9 LUFS**、真峰值 **-1.5 dBTP** |
| `docs/preview.gif` | 480px 动图（README 用） |
| `docs/contact-sheet.jpg` | 抽帧接触表，自检用 |
| `docs/style-dark-tech.png` | 风格帧（对应流程第 4 步） |

**最值得看的是第 2 段（4–8 秒）**：画面里的波形由**真实音频采样**驱动，而那支配乐全部由 `scripts/compose.py` 的合成器当场合出——没有采样、没有素材库、没有 AI 生成。这是本流程和「AI 一键出片」最本质的区别。

### 复现它

```bash
cd demo
# demo/fonts/ 需自行放入可商用中文字体（如 Noto Sans SC，SIL OFL）
python audio/compose_demo.py                      # 合成 16s 原创配乐 → out/demo_mix.wav
python video/render_frames.py --format preview    # 960x540@30 预览帧
python video/render_frames.py --format final      # 1920x1080@60 正式帧

ffmpeg -framerate 60 -i out/frames_final/f%05d.png -i out/demo_mix.wav \
       -c:v libx264 -crf 17 -pix_fmt yuv420p -c:a aac -b:a 256k \
       -movflags +faststart -shortest out/final.mp4

# 响度统一到 -14 LUFS（先测再压）
ffmpeg -i out/final.mp4 -af loudnorm=print_format=json -f null -
ffmpeg -i out/final.mp4 -af "volume=8.6dB,alimiter=limit=0.80:attack=4:release=60:level=disabled" \
       -c:v copy -c:a aac -b:a 256k out/final_loud.mp4

# 自检
../scripts/verify.sh out/final_loud.mp4 12
```

工程里的 `demo/plan_v1.md` 是这次的完整方案（分镜表 / 转场表 / 视觉系统 / 配乐结构），可以直接当作流程第 3 步的范例。

---

## 8 个步骤一览

| # | 阶段 | 产出 |
|---|---|---|
| 1 | **明确需求** | 主角、受众、时长、画幅、帧率、渠道；先读主角官方资料，摘录原话 |
| 2 | **调研开源参考** | 框架 / 配色 / 动效 / 音频 / 字体 / 图标 / 文案，逐条核实地址和许可证 |
| 3 | **写方案**（先不渲染） | 统一时间轴（BPM + 帧号）、分镜表、转场表、视觉系统、配乐与音效清单、风格帧 |
| 4 | **视觉方向备选** | 3–4 套差异明显的风格 + 同场景对比图 |
| 5 | **制作** | 帧驱动动画；自写合成器做音频；统一响度到 -14 LUFS |
| 6 | **预览** | 低分辨率完整预览；ffprobe 核规格 + 抽帧接触表自检 |
| 7 | **文案去 AI 腔** | 去排比、去口号、写具体数字；给逐场景修改前后对照表 |
| 8 | **正式版** | 提规格渲染（如 1080p60 / CRF 16–18 / yuv420p / AAC 320k），ffprobe 复查 |

**每个阶段先给需求方看，确认后再进下一步。**

---

## 内置脚本

### `scripts/compose.py` — 音频合成骨架

把 SKILL.md 里的合成技法做成可直接调用的函数，改参数就能出原创配乐：

```bash
python scripts/compose.py --out out/demo.wav --bpm 120 --bars 8
```

包含：

- `saw_detuned()` 失谐锯齿波铺底、`fm_bell()` FM 钟琴、`karplus_strong()` 拨弦
- `noise_perc()` 滤波噪声镲/拍手、`kick()` 下滑正弦底鼓、`sweep()` 转场 riser
- `branded_sting()` 2–3 音品牌音（落版用）
- `sidechain()` 侧链压缩、`reverb()` FFT 卷积混响
- `write_wav()` 16/24/32 bit 写出、`normalize()` 峰值归一化

> 固定随机种子，同一参数渲染结果完全一致。

### `scripts/verify.sh` — 成片自检

```bash
./scripts/verify.sh out/final.mp4 12
```

- ffprobe 核时长 / 帧数 / 分辨率 / 帧率 / 编码 / 是否有音轨
- `loudnorm` 打印度量（目标 -14 LUFS，真峰值 ≤ -1 dBTP）
- 均匀抽帧生成 `contact-sheet.jpg`，肉眼查元素重叠、缺字、豆腐块
- 打印上架前自检清单

---

## 安装

本仓库是一个 Agent Skill：`SKILL.md` + `scripts/`。

任选其一：

**1. 直接放进技能目录**

```bash
# 用户级（所有项目可用）
cp -r . ~/.workbuddy/skills/code-motion-video

# 或项目级（随仓库共享）
cp -r . .workbuddy/skills/code-motion-video
```

也兼容其他支持 Agent Skills 的助手目录，例如 `.claude/skills/code-motion-video/`。

**2. 当成人看的制作清单**

直接读 `SKILL.md`，按 8 个步骤走，脚本按需取用。

### 依赖

- 画面：Node 18+，[Remotion](https://github.com/remotion-dev/remotion)（React）
- 音频：Python 3.10+，NumPy（可选 SciPy）
- 合成：FFmpeg（含 ffprobe）

```bash
python -m pip install numpy scipy
```

---

## 技术栈

| 层 | 默认 | 可替换 |
|---|---|---|
| 画面 | Remotion（React） | Motion Canvas、Revideo、Manim、HyperFrames、theatre.js、GSAP |
| 音频 | Python + NumPy / SciPy 自写合成器 | Tone.js、SuperCollider |
| 合成 | FFmpeg（H.264 + AAC，faststart） | — |

**流程与技法不绑定具体框架**，换渲染器只换第 5 步的实现。

---

## 许可

本规范以 [MIT](LICENSE) 许可发布。

文中提到的开源项目、字体、图标各自保留原有许可证，使用前请自行确认。特别注意：

- **Remotion** 对公司商用有单独的许可条款，商用前请阅读其 LICENSE。
- 字体请只用允许商用的许可（如 SIL OFL）：思源黑体 / Noto Sans SC、思源宋体、霞鹜文楷、Inter、Space Grotesk、JetBrains Mono 等。
- Logo 与商标图形未经授权只能用于内部预览，公开发布前须取得许可。

---

## 关键词

纯代码视频 · 程序化动画 · Remotion 动画 · 代码生成视频 · 自制 BGM · 无版权音乐 · 代码合成音效 · FFmpeg 合成 · 不绑定素材库 · 不用 AI 生成视频 · 产品宣传片 · 片头动画
