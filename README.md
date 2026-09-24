# 沙雕漫零成本生产线

单人可跑的沙雕漫（Q版搞笑动画短剧）批量制作管线：**批量生图 → AI质检 → 文稿自检 → TTS配音 → 剪映草稿合成**。现金成本≈0（生图走订阅额度、配音和剪辑全免费）。

完整方法论见 [docs/沙雕漫管线方案.md](docs/沙雕漫管线方案.md)（五步管线 + 任务JSON示例）。

## 目录

| 目录 | 内容 |
|---|---|
| `批量生图/` | Grok 网页版 CDP 自动化批量生图：`grok_imagine_batch.py` 主力（定妆/表情/场景/底图批量出图），`home_video.py` 生视频，其余为会话/下载/探针辅助 |
| `QC/` | MiniMax-M3 视觉质检：`m3_batch_qc.py` 分镜图批量四项质检（肢体/画面文字/画风/内容），`qc_m3_recheck.py` 返修复检，`m3_video_qc.py` 视频逐秒抽帧质检（断点续跑） |
| `自检/` | `文稿自检.py` 剧本/台词机器检查 + `pre-commit` 钩子（无自检记录的文稿不允许commit） |
| `配音/` | `make_audio_template.py` edge-tts 批量配音：逐镜MP3 + ffprobe实测时长 |
| `合成/` | `jianying_v8.py` 用 pyJianYingDraft 生成剪映草稿（排轨/字幕/画面文字），最终成片在剪映里人工导出 |
| `docs/` | 管线方案 + v10任务JSON示例（定妆表情/白球头/身体模板/镜4测试） |

## 快速开始

```bash
# 1. 批量生图（本地开好 Grok 网页版登录态后）
python 批量生图/grok_imagine_batch.py

# 2. 分镜图质检（需 MiniMax key）
set MINIMAX_API_KEY=你的key
python QC/m3_batch_qc.py --img-dir ./output --expect qc_expect.json

# 3. 配音（需 edge-tts；时长以 ffprobe 实测为准）
pip install edge-tts
python 配音/make_audio_template.py

# 4. 生成剪映草稿（需 pyJianYingDraft）
pip install pyJianYingDraft
set EPISODE_DIR=你的剧集素材目录
python -X utf8 合成/jianying_v8.py init && python -X utf8 合成/jianying_v8.py build
```

## 管线原则

- **时长只信实测**：TTS 真读 + ffprobe 量实际时长，禁止估算或先定时长再配台词
- **一份台词源**：旁白/对白/字幕从同一份数据派生，不手抄两遍
- **成片在剪映导出**：FFmpeg 只用于抽帧、测时长、裁静音
- **角色一致性**：同一角色全片用同一套定妆+表情图拼合，抽卡不合格就重抽（QC 把关）
- **合规**：AI 生成内容上线需按平台要求添加 AI 标识

## 已知边界

- 生图脚本依赖 Grok 网页版 DOM 结构，前端改版需要跟着修（CDP 自动化的通病）
- 剪映草稿兼容性与剪映版本相关，install 前关闭剪映
- 仅供个人学习与内容制作研究，请遵守各平台服务条款
