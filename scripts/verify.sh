#!/usr/bin/env bash
# 成片自检：ffprobe 核规格 + 按间隔抽帧拼接触表 + 检查音轨响度。
#
# 用法：
#   ./verify.sh out/final.mp4 [抽帧数量]
#
# 输出：
#   - 终端里打印时长、帧数、分辨率、帧率、编码、音轨、响度
#   - 在输入文件同级生成 contact-sheet.jpg（接触表），用于肉眼查元素重叠、缺字、豆腐块

set -uo pipefail

VIDEO="${1:-}"
COUNT="${2:-12}"

if [[ -z "$VIDEO" ]]; then
  echo "用法: $0 <视频文件> [抽帧数量]" >&2
  exit 1
fi
if [[ ! -f "$VIDEO" ]]; then
  echo "找不到文件: $VIDEO" >&2
  exit 1
fi
if ! command -v ffprobe >/dev/null 2>&1; then
  echo "未安装 ffprobe（随 FFmpeg 一起提供），请先安装 FFmpeg。" >&2
  exit 1
fi

DIR="$(cd "$(dirname "$VIDEO")" && pwd)"
BASE="$(basename "$VIDEO")"

echo "=========== 1. 容器与流信息 ==========="
ffprobe -v error -show_entries \
  format=duration,size,bit_rate,format_name \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,pix_fmt,sample_rate,channels,bit_rate,duration,nb_frames \
  -of default=noprint_wrappers=0 "$VIDEO"

echo
echo "=========== 2. 关键规格核对 ==========="
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO")
echo "时长        : ${DUR}s"

V_CODEC=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$VIDEO")
V_W=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$VIDEO")
V_H=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$VIDEO")
V_PIX=$(ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt -of csv=p=0 "$VIDEO")
V_FPS=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$VIDEO")
V_FRAMES=$(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$VIDEO")
echo "分辨率      : ${V_W}x${V_H}"
echo "帧率        : ${V_FPS}"
echo "总帧数      : ${V_FRAMES}"
echo "视频编码    : ${V_CODEC}"
echo "像素格式    : ${V_PIX}"

if ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$VIDEO" | grep -q .; then
  A_CODEC=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$VIDEO")
  A_SR=$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of csv=p=0 "$VIDEO")
  A_CH=$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of csv=p=0 "$VIDEO")
  echo "音轨        : 有（${A_CODEC} / ${A_SR}Hz / ${A_CH}声道）"
else
  echo "音轨        : ⚠️ 没有音轨！"
fi

echo
echo "=========== 3. 响度检查（目标 -14 LUFS，真峰值 ≤ -1 dBTP）==========="
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -hide_banner -nostats -i "$VIDEO" -af loudnorm=print_format=summary -f null - 2>&1 \
    | grep -Ei "input integrated|input true peak|input lra|input threshold" || echo "（未取到响度信息）"
else
  echo "未安装 ffmpeg，跳过响度检查。"
fi

echo
echo "=========== 4. 抽帧接触表 ==========="
if ! [[ "$DUR" =~ ^[0-9.]+$ ]] || [[ "$COUNT" -lt 1 ]]; then
  echo "时长或数量无效，跳过抽帧。"
  exit 0
fi
FPS_OUT=$(( COUNT > 1 ? 1 : 1 ))
SHEET="$DIR/contact-sheet.jpg"
# 用 select 按均匀间隔抽帧，再平铺成网格
ffmpeg -hide_banner -loglevel error -y -i "$VIDEO" \
  -vf "select='not(mod(n\,max(1\,floor(n_frames/${COUNT}))))',scale=320:-1,tile=${COUNT}x1" \
  -frames:v 1 "$SHEET" 2>/dev/null \
  || ffmpeg -hide_banner -loglevel error -y -i "$VIDEO" \
     -vf "fps=${COUNT}/${DUR},scale=320:-1,tile=${COUNT}x1" -frames:v 1 "$SHEET" 2>/dev/null

if [[ -f "$SHEET" ]]; then
  echo "接触表已生成: $SHEET"
  echo "→ 打开它，逐格检查：元素重叠、缺字/豆腐块、文字出画、色彩断层"
else
  echo "⚠️ 接触表生成失败，可手动执行："
  echo "   ffmpeg -i \"$VIDEO\" -vf \"fps=1/2,scale=320:-1,tile=6x2\" -frames:v 1 contact-sheet.jpg"
fi

echo
echo "=========== 5. 上架前自检清单 ==========="
cat <<'EOF'
[ ] 时长、帧数与方案一致
[ ] 分辨率、帧率、像素格式符合正式版要求（如 1920x1080 / 60fps / yuv420p）
[ ] 有音轨，且响度接近 -14 LUFS，真峰值不超过 -1 dBTP
[ ] 接触表里没有元素重叠、缺字、豆腐块
[ ] 搜索源码，确认不该出现的名字/内容没有出现
[ ] 字体为可商用许可（如 SIL OFL），已随包或已注明
[ ] 素材/Logo 已确认授权，商标图形公开发布前已获许可
EOF
