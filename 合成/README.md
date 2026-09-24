# 剪映草稿合成（jianying_v8.py）

把已生成、已质检的动态视频和实际配音，排成可直接用剪映打开的本地草稿。不生成视频、不调付费服务、不用 FFmpeg 合成成片（正式成片一律在剪映里导出）。

## 依赖

- Python 3.10+，安装 `pyJianYingDraft`（`pip install pyJianYingDraft`）和 `pymediainfo`
- 本机装有剪映专业版（Windows）且**处于关闭状态**时执行 install
- `ffprobe` 可用（ffmpeg 套件）

## 它做什么

1. 从剧集目录读取镜头与台词 JSON（`EPISODE_DIR` 环境变量指定，默认 `episode_assets/`），校验句子 ID、全文和源文件校验值；镜头清单维护在本目录 `素材映射.json`。
2. 读取配音产出的 `line_timings.json`，用 ffprobe 实测每句有效音频；句间默认 0.12s，镜尾至少 0.4s（配音+0.4 是参考值，动作收尾按需调整）。
3. 检查每镜实际素材的尺寸、时长、检查状态。缺镜、缺音频、横屏、源文件变更、素材短于配音需求时直接停止——不补静止帧、不循环、不减速、不截对白。
4. 按真实素材排轨：关闭视频原声、逐句音轨、全文字幕自动换行，9:16、720×1280、30fps；导出草稿、SRT、逐句时间表和缺件清单。低于 720×1280 的素材停止接收，不自动放大。
5. 一镜可有多段真实视频（同一动作续段），在 `clips` 列表显式登记选段；要裁短先确认动作完整，再填 `in_seconds`/`out_seconds`。
6. 剧本要求的画面内文字（时间/账目/道具）走独立的普通文字轨，登记在 `画面文字映射.json`，不混入对白字幕轨。

## 用法

```powershell
$env:EPISODE_DIR = "你的剧集素材目录"
python -X utf8 合成/jianying_v8.py init    # 首次生成素材映射清单
python -X utf8 合成/jianying_v8.py scan    # 更新接收检查状态
python -X utf8 合成/jianying_v8.py build   # 全镜齐了才出完整草稿
python -X utf8 合成/jianying_v8.py build --through 3   # 只出前3镜试片草稿
python -X utf8 合成/jianying_v8.py install --draft "build打印的草稿目录"
```

- 每段素材人工检查通过后，把清单里的 `review_status` 改为 `passed`。
- `install` 只复制新草稿并在根列表新增条目（先备份），不覆盖旧草稿；剪映正在运行时会停止，避免保存冲突。
- 装好后打开剪映确认镜头、配音、字幕载入正确，完整听看后在剪映里导出 MP4——导出这步必须人来。

## 字幕规格（默认）

剪映字号 8、居中、白字黑边、自动换行，最大行宽为画布宽 78%，垂直位置相对坐标 -0.73（720p 时中心离底边约 173px）。字体用本机微软雅黑，不调在线字体/会员字体/特效模板。
