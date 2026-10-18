# code-motion-video-skill

纯代码动画视频制作规范：画面、动效、转场、配乐、音效、排版全部用代码完成，不用 AI 视频或音乐生成模型。适合做产品介绍、片头、宣传片、自我介绍等短片。

## 怎么用

`SKILL.md` 是一个 Agent Skill 文件（带 YAML frontmatter：`name` 和 `description`）。

- 放进支持 Skills 的 AI 编程助手的技能目录，例如 `.claude/skills/code-motion-video/SKILL.md` 或 `~/.claude/skills/code-motion-video/SKILL.md`，助手会在需要做代码动画视频时自动调用。
- 也可以直接当成人看的制作清单，按步骤走。

## 8 个步骤一览

1. **明确需求**：主角、受众、时长、画幅、帧率、渠道，先读官方资料。
2. **调研开源参考**：框架、配色、动效、音频、字体、图标、文案，逐条核实地址和许可证。
3. **写方案**：统一时间轴（BPM + 帧号）、分镜表、转场表、视觉系统、配乐和音效清单、风格帧。
4. **视觉方向备选**：出 3–4 套差异明显的风格供选择。
5. **制作**：帧驱动动画，自写合成器做音频，统一响度。
6. **预览**：先出低分辨率完整预览，自检时长、帧数、音轨和画面。
7. **文案去 AI 腔**：去掉套话和排比，写具体场景，给前后对照表。
8. **正式版**：提高规格渲染，复查，按需导出其他画幅。

## 技术栈

- 画面：[Remotion](https://github.com/remotion-dev/remotion)（React），可换 Motion Canvas、Revideo、Manim 等
- 音频：Python + NumPy / SciPy 自写合成器
- 合成：FFmpeg（H.264 + AAC，响度统一到 -14 LUFS）

## 许可

本规范以 [MIT](LICENSE) 许可发布。文中提到的开源项目、字体、图标等各自保留原有许可证，使用前请自行确认（例如 Remotion 对公司商用有单独的许可条款）。
