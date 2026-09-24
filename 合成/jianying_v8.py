"""Receive real v8 assets and build a new Jianying draft; never render a movie."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EPISODE = Path(os.environ.get("EPISODE_DIR", ROOT / "episode_assets"))
STORY = EPISODE / "04_镜头与提示词_v8.json"
LINES = EPISODE / "03_台词与全文字幕_v8.json"
MAPPING = HERE / "素材映射.json"
PICTURE_TEXTS = HERE / "画面文字映射.json"
SUBTITLE_TRACK = "v8完整对白字幕"
DEFAULT_DRAFT_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "JianyingPro/User Data/Projects/com.lveditor.draft"
OUTPUT_WIDTH, OUTPUT_HEIGHT, OUTPUT_FPS = 720, 1280, 30


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def absolute(path):
    value = Path(path)
    return (ROOT / value).resolve() if not value.is_absolute() else value.resolve()


def identifier():
    return uuid.uuid4().hex.upper()


def microseconds(seconds):
    return round(float(seconds) * 1_000_000)


def init_mapping():
    if MAPPING.exists():
        print(f"保留已有素材清单：{MAPPING}")
        return
    story = read_json(STORY)
    mapping = {
        "schema": "jianying-v8-assets-1",
        "authorization_note": "用户已要求：行 那你继续 完成第一集 我看看效果。review_status 指素材检查，不是用户审批。",
        "source_story_sha256": digest(STORY),
        "source_lines_sha256": digest(LINES),
        "audio_timings_path": str(EPISODE / "audio_v8_20260908/line_timings.json"),
        "line_gap_seconds": 0.12,
        "minimum_tail_seconds": 0.4,
        "shots": [{
            "shot_id": shot["id"],
            "clips": [{
                "path": str(EPISODE / f"assets/videos/{shot['id']}.mp4"),
                "in_seconds": 0,
                "out_seconds": None,
                "review_status": "pending",
                "review_note": "待检查人物、道具、真实动作和相邻接缝。",
            }],
        } for shot in story["shots"]],
    }
    write_json(MAPPING, mapping)
    print(f"已创建 24 镜素材清单：{MAPPING}")


def probe(path):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
    ], capture_output=True, text=True, encoding="utf-8", timeout=45, check=True)
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    durations = [float(s["duration"]) for s in streams if s.get("duration") not in (None, "N/A")]
    format_duration = data.get("format", {}).get("duration")
    if format_duration not in (None, "N/A"):
        durations.append(float(format_duration))
    duration = max(durations, default=0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"不能实测有效时长：{path}")
    return {"duration_seconds": duration, "streams": streams}


def select_sources(mapping_path, through):
    mapping = read_json(mapping_path)
    story = read_json(STORY)
    lines = read_json(LINES)
    if digest(STORY) != mapping["source_story_sha256"] or digest(LINES) != mapping["source_lines_sha256"]:
        raise ValueError("v8 文稿已变更，先重新核对素材和配音并更新清单中的校验值。")
    if len(story["shots"]) != 24 or len(lines) != 53:
        raise ValueError("本工具限定当前 v8 的 24 镜、53 句，不能混用其他剧本。")
    canonical = {line["id"]: line for line in lines}
    if len(canonical) != len(lines):
        raise ValueError("源台词存在重复句子 ID。")
    for shot in story["shots"]:
        if [canonical[key]["text"] for key in shot["line_ids"]] != [pair[1] for pair in shot["lines"]]:
            raise ValueError(f"镜头与台词源不一致：{shot['id']}")
        for line_id in shot["line_ids"]:
            line = canonical[line_id]
            if line["subtitle_text"] != line["text"] or line["shot_id"] != shot["id"]:
                raise ValueError(f"源字幕或镜号不一致：{line_id}")
    ids = [shot["shot_id"] for shot in mapping["shots"]]
    if ids != [shot["id"] for shot in story["shots"]]:
        raise ValueError("素材清单须按顺序完整登记 24 镜。")
    return mapping, story["shots"][:through], canonical


def inspect_assets(mapping_path=MAPPING, through=24):
    mapping, shots, canonical = select_sources(mapping_path, through)
    issues, records = [], []
    audio_path = absolute(mapping["audio_timings_path"])
    audio_lines = {}
    if not audio_path.exists():
        issues.append(f"缺配音时间清单：{audio_path}")
    else:
        audio = read_json(audio_path)
        if audio.get("source_sha256") != digest(LINES):
            issues.append("配音清单的台词源校验值与当前 v8 不符。")
        audio_lines = {line["id"]: line for line in audio.get("lines", [])}
    selected_mapping = {item["shot_id"]: item for item in mapping["shots"]}
    gap = float(mapping.get("line_gap_seconds", 0.12))
    tail = float(mapping.get("minimum_tail_seconds", 0.4))
    if gap < 0 or tail < 0:
        raise ValueError("句间和镜尾时长不能为负。")
    for shot in shots:
        sid = shot["id"]
        record = {"shot_id": sid, "clips": [], "lines": [], "issues": []}
        audio_cursor = 0
        for line_id in shot["line_ids"]:
            src, measured = canonical[line_id], audio_lines.get(line_id)
            if not measured:
                record["issues"].append(f"缺配音：{line_id}")
                continue
            if any(measured.get(key) != src[key] for key in ("shot_id", "role", "text", "subtitle_text")):
                record["issues"].append(f"配音文本或角色不一致：{line_id}")
                continue
            path = absolute(measured["audio_path"])
            if not path.is_file():
                record["issues"].append(f"缺音频文件：{path}")
                continue
            try:
                media = probe(path)
                if not any(s.get("codec_type") == "audio" for s in media["streams"]):
                    raise ValueError("文件没有音轨")
                duration = media["duration_seconds"]
                declared = measured.get("duration_seconds")
                if declared is not None and abs(duration - float(declared)) > 0.06:
                    record["issues"].append(f"配音变更，清单时长与实测不符：{line_id}")
                record["lines"].append({
                    "id": line_id, "role": src["role"], "text": src["text"],
                    "audio_path": str(path), "duration_seconds": duration,
                    "start_in_shot_seconds": round(audio_cursor, 6),
                    "review_status": measured.get("review_status", "未登记听审状态"),
                })
                audio_cursor += duration + gap
            except (ValueError, subprocess.SubprocessError, OSError) as exc:
                record["issues"].append(f"不能测量配音 {line_id}：{exc}")
        audio_end = max(0, audio_cursor - gap) if record["lines"] else 0
        record["measured_audio_span_seconds"] = round(audio_end, 6)
        record["minimum_video_seconds"] = round(audio_end + tail, 6)
        video_cursor = 0
        clips = selected_mapping[sid].get("clips", [])
        if not clips:
            record["issues"].append("没有登记动态视频。")
        for item in clips:
            path = absolute(item["path"])
            if not path.is_file():
                record["issues"].append(f"缺动态视频：{path}")
                continue
            if path.suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm", ".m4v"):
                record["issues"].append(f"只接受实际动态视频文件：{path}")
                continue
            if item.get("review_status") != "passed":
                record["issues"].append(f"动态、人物及接缝尚未检查通过：{path.name}")
            try:
                media = probe(path)
                video = next((s for s in media["streams"] if s.get("codec_type") == "video"), None)
                if not video or video.get("disposition", {}).get("attached_pic"):
                    raise ValueError("没有实际视频流")
                width, height = int(video.get("width", 0)), int(video.get("height", 0))
                if not height or abs(width / height - 9 / 16) > 0.018:
                    raise ValueError(f"尺寸 {width}×{height} 不是 9:16，需先确认构图，不自动拉伸")
                if width < OUTPUT_WIDTH or height < OUTPUT_HEIGHT:
                    raise ValueError(f"尺寸 {width}×{height} 低于本轮 720×1280 输出，需核实原始下载，不自动放大补分辨率")
                video_duration = float(video.get("duration")) if video.get("duration") not in (None, "N/A") else media["duration_seconds"]
                start = float(item.get("in_seconds", 0))
                end = video_duration if item.get("out_seconds") is None else float(item["out_seconds"])
                if not all(math.isfinite(t) for t in (start, end)) or start < 0 or end <= start or end > video_duration + 0.000001:
                    raise ValueError("选择的入点/出点超出实际素材")
                record["clips"].append({
                    "path": str(path), "in_seconds": start, "out_seconds": end,
                    "duration_seconds": round(end - start, 6),
                    "source_duration_seconds": video_duration,
                    "start_in_shot_seconds": round(video_cursor, 6), "width": width, "height": height,
                    "audio_mode": item.get("audio_mode", "tts"),
                })
                video_cursor += end - start
            except (ValueError, subprocess.SubprocessError, OSError) as exc:
                record["issues"].append(f"视频不可接收 {path.name}：{exc}")
        record["selected_video_seconds"] = round(video_cursor, 6)
        if record["clips"] and video_cursor + 0.002 < audio_end + tail:
            record["issues"].append(f"选段仅 {video_cursor:.3f} 秒，配音及尾停至少 {audio_end + tail:.3f} 秒；需真实续段或重新生成。")
        issues.extend(f"{sid}：{issue}" for issue in record["issues"])
        records.append(record)
    return {
        "scope": "完整第一集" if through == 24 else f"前 {through} 镜试看片段，非完整第一集",
        "ready": not issues,
        "audio_measured_not_estimated": True,
        "video_motion_review_is_manual": True,
        "audio_complete_listening_review": "未由本工具完成，沿用每句清单记录；草稿可用于听审，不代表声音终验。",
        "source_story_sha256": digest(STORY), "source_lines_sha256": digest(LINES),
        "selected_shots": through, "expected_full_episode_shots": 24,
        "output_canvas": {"width": OUTPUT_WIDTH, "height": OUTPUT_HEIGHT, "fps": OUTPUT_FPS},
        "issues": issues, "shots": records,
    }


def srt_timestamp(seconds):
    total_ms = round(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def resolve_picture_texts(report, mapping_path=PICTURE_TEXTS):
    """Resolve shot-relative text cues without claiming visual placement passed."""
    mapping = read_json(mapping_path)
    if mapping.get("schema") != "jianying-v8-picture-texts-1":
        raise ValueError("画面文字映射格式不受支持。")
    if mapping.get("canvas") != {"width": OUTPUT_WIDTH, "height": OUTPUT_HEIGHT, "fps": OUTPUT_FPS}:
        raise ValueError("画面文字映射必须使用本轮720×1280、30fps画布。")
    for source in mapping["source_files"]:
        if digest(absolute(source["path"])) != source["sha256"]:
            raise ValueError(f"画面文字所依据的文稿已变化，须先复核映射：{source['path']}")
    known_shots = {shot["id"] for shot in read_json(STORY)["shots"]}
    shot_ranges, cursor = {}, 0
    for shot in report["shots"]:
        duration = microseconds(shot["selected_video_seconds"])
        if duration <= 0:
            raise ValueError(f"画面文字缺少实际镜长：{shot['shot_id']}")
        shot_ranges[shot["shot_id"]] = (cursor, duration)
        cursor += duration
    track_names = mapping["track_names"]
    if len(set(track_names.values())) != len(track_names) or SUBTITLE_TRACK in track_names.values():
        raise ValueError("画面文字必须分轨，不能混入全文对白字幕轨。")
    resolved, seen_ids = [], set()
    for item in mapping["entries"]:
        if item["id"] in seen_ids or item["shot_id"] not in known_shots:
            raise ValueError("画面文字ID重复或引用了无效镜号。")
        seen_ids.add(item["id"])
        if not item.get("enabled", True) or item["shot_id"] not in shot_ranges:
            continue
        if item["category"] not in track_names or not isinstance(item["text"], str) or not item["text"].strip():
            raise ValueError(f"画面文字分类或正文无效：{item['id']}")
        shot_start, shot_duration = shot_ranges[item["shot_id"]]
        timing = item["timing"]
        start, end = float(timing["start"]), float(timing["end"])
        if not all(math.isfinite(value) for value in (start, end)):
            raise ValueError(f"画面文字时间无效：{item['id']}")
        if timing["mode"] == "fraction_of_shot":
            if not 0 <= start < end <= 1:
                raise ValueError(f"画面文字镜内比例超界：{item['id']}")
            start, end = round(start * shot_duration), round(end * shot_duration)
        elif timing["mode"] == "seconds":
            start, end = microseconds(start), microseconds(end)
        else:
            raise ValueError(f"画面文字时间模式无效：{item['id']}")
        if not 0 <= start < end <= shot_duration:
            raise ValueError(f"画面文字越过真实镜长，须重新核对镜内时间：{item['id']}")
        place = item["placement"]
        values = [float(place[key]) for key in ("transform_x", "transform_y", "font_size", "max_line_width", "rotation_degrees", "border_width")]
        if not all(math.isfinite(value) for value in values) or not all(-1 <= place[key] <= 1 for key in ("transform_x", "transform_y")):
            raise ValueError(f"画面文字位置无效：{item['id']}")
        if not 0 < place["max_line_width"] <= 1 or place["font_size"] <= 0 or place["border_width"] < 0:
            raise ValueError(f"画面文字字号或行宽无效：{item['id']}")
        if len(place["color"]) != 3 or not all(math.isfinite(float(c)) and 0 <= c <= 1 for c in place["color"]):
            raise ValueError(f"画面文字颜色无效：{item['id']}")
        resolved.append({
            **item, "track_name": track_names[item["category"]],
            "start_in_shot_seconds": start / 1e6, "end_in_shot_seconds": end / 1e6,
            "timeline_start_seconds": (shot_start + start) / 1e6,
            "timeline_end_seconds": (shot_start + end) / 1e6,
        })
    resolved.sort(key=lambda item: (item["timeline_start_seconds"], item["id"]))
    track_ends = {}
    for item in resolved:
        name = item["track_name"]
        if item["timeline_start_seconds"] < track_ends.get(name, 0) - 0.000001:
            raise ValueError(f"画面文字同轨重叠：{item['id']}")
        track_ends[name] = item["timeline_end_seconds"]
    return resolved


def add_picture_text_tracks(script, picture_texts):
    """Add only ordinary text; positions on paper/signs remain provisional."""
    import pyJianYingDraft as draft

    tracks = {}
    for item in picture_texts:
        name, place = item["track_name"], item["placement"]
        if name not in tracks:
            tracks[name] = script.append_track(draft.TrackSpec(draft.TrackType.text, name))
        start, end = microseconds(item["timeline_start_seconds"]), microseconds(item["timeline_end_seconds"])
        segment = draft.TextSegment(
            item["text"], draft.Timerange(start, end - start),
            style=draft.TextStyle(size=place["font_size"], bold=item["category"] != "prop_surface", align=1,
                                  color=tuple(place["color"]), auto_wrapping=True, max_line_width=place["max_line_width"]),
            border=draft.TextBorder(color=(0, 0, 0), width=place["border_width"]) if place["border_width"] else None,
            clip_settings=draft.ClipSettings(transform_x=place["transform_x"], transform_y=place["transform_y"], rotation=place["rotation_degrees"]),
        )
        segment.extra_material_refs.clear()
        script.add_segment(segment, tracks[name])


def validate_draft(data, expected_lines, expected_shots, expected_picture_texts=None, original_audio_lines=0, original_audio_segments=0):
    canvas = data["canvas_config"]
    if (canvas["width"], canvas["height"], data["fps"]) != (OUTPUT_WIDTH, OUTPUT_HEIGHT, OUTPUT_FPS):
        raise ValueError("本轮草稿须为 720×1280、30fps；不能将上采样称为原生 1080p。")
    all_material_ids = {m["id"] for values in data["materials"].values() if isinstance(values, list) for m in values if isinstance(m, dict) and "id" in m}
    seen_segments, videos, audios, texts, text_tracks = set(), [], [], [], {}
    for track in data["tracks"]:
        segments = track.get("segments", [])
        last_end = 0
        for segment in segments:
            if segment["id"] in seen_segments:
                raise ValueError("生成草稿的片段 ID 重复。")
            seen_segments.add(segment["id"])
            if segment["material_id"] not in all_material_ids:
                raise ValueError("生成草稿出现失效的素材引用。")
            if any(ref not in all_material_ids for ref in segment.get("extra_material_refs", [])):
                raise ValueError("生成草稿出现失效的附加素材引用。")
            timerange = segment["target_timerange"]
            if timerange["duration"] <= 0 or timerange["start"] < last_end - 1:
                raise ValueError("草稿存在负时长或同轨重叠。")
            last_end = timerange["start"] + timerange["duration"]
        {"video": videos, "audio": audios, "text": texts}.get(track["type"], []).extend(segments)
        if track["type"] == "text":
            name = track.get("name")
            if name in text_tracks:
                raise ValueError("文字轨名称重复，不能确认对白与画面文字的归属。")
            text_tracks[name] = segments
    text_materials = {t["id"]: json.loads(t["content"])["text"] for t in data["materials"]["texts"]}
    expected_by_track = {SUBTITLE_TRACK: expected_lines}
    for item in expected_picture_texts or []:
        expected_by_track.setdefault(item["track_name"], []).append(item["text"])
    if set(text_tracks) != set(expected_by_track):
        raise ValueError("文字轨缺失或多出未登记轨道，不能将画面文字混入对白字幕。")
    for name, expected in expected_by_track.items():
        if [text_materials[s["material_id"]] for s in text_tracks[name]] != expected:
            raise ValueError(f"文字正文或顺序与对应清单不符：{name}")
    expected_text_count = sum(len(values) for values in expected_by_track.values())
    if len(audios) != len(expected_lines) - original_audio_lines:
        raise ValueError("生成草稿的配音没有完整逐句覆盖（原声镜不叠TTS属正常）。")
    if len(texts) != expected_text_count or len(text_materials) != expected_text_count:
        raise ValueError("生成草稿的字幕没有完整逐句覆盖。")
    if len(videos) < expected_shots:
        raise ValueError("动态视频数量不足。")
    loud = [segment for segment in videos if segment.get("volume") == 1]
    if len(loud) != original_audio_segments:
        raise ValueError("保留原声的视频片段数量与登记的原声镜不符。")
    if any(segment["volume"] not in (0, 1) or segment["speed"] != 1 for segment in videos):
        raise ValueError("视频音量只允许0（TTS镜）或1（同期对白镜），且不得变速。")


def build_draft(report, output_parent=None):
    if not report["ready"]:
        raise ValueError(f"当前有 {len(report['issues'])} 项未就绪；详见接收检查.json。未创建草稿。")
    import pyJianYingDraft as draft

    picture_texts = resolve_picture_texts(report)
    system_font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
    if not system_font.is_file():
        raise ValueError("缺少本地微软雅黑字体，停止创建草稿；不自动下载或使用付费字体。")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "完整集待验收" if report["selected_shots"] == 24 else f"前{report['selected_shots']}镜试片"
    name = f"episode_E01_{suffix}_{stamp}"
    output_parent = Path(output_parent) if output_parent else HERE / "输出草稿"
    output_parent.mkdir(parents=True, exist_ok=True)
    directory = output_parent / name
    script = draft.DraftFolder(str(output_parent)).create_draft(name, OUTPUT_WIDTH, OUTPUT_HEIGHT, fps=OUTPUT_FPS, maintrack_adsorb=False, allow_replace=False)
    video_track = script.append_track(draft.TrackSpec(draft.TrackType.video, "剧情动态视频", mute=False))
    audio_track = script.append_track(draft.TrackSpec(draft.TrackType.audio, "v8旁白与角色对白"))
    text_track = script.append_track(draft.TrackSpec(draft.TrackType.text, SUBTITLE_TRACK))
    timeline, expected_lines, srt = [], [], []
    shot_start = 0
    for shot in report["shots"]:
        keep_original = any(clip.get("audio_mode") == "grok_original" for clip in shot["clips"])
        for clip in shot["clips"]:
            duration = microseconds(clip["duration_seconds"])
            material = draft.VideoMaterial(clip["path"])
            # MediaInfo may round to milliseconds. Use the real video stream's
            # ffprobe duration, so no source range exceeds measured video frames.
            material.duration = microseconds(clip["source_duration_seconds"])
            segment = draft.VideoSegment(
                material, draft.Timerange(shot_start + microseconds(clip["start_in_shot_seconds"]), duration),
                source_timerange=draft.Timerange(microseconds(clip["in_seconds"]), duration),
                speed=1, volume=1 if keep_original else 0,
            )
            script.add_segment(segment, video_track)
        for line in shot["lines"]:
            start = shot_start + microseconds(line["start_in_shot_seconds"])
            duration = microseconds(line["duration_seconds"])
            if not keep_original:
                # No re-encoding or assembly: each line is its own real audio material.
                audio_material = draft.AudioMaterial(line["audio_path"])
                audio_material.duration = duration
                audio = draft.AudioSegment(audio_material, draft.Timerange(start, duration), source_timerange=draft.Timerange(0, duration), speed=1, volume=1)
                script.add_segment(audio, audio_track)
            subtitle = draft.TextSegment(
                line["text"], draft.Timerange(start, duration),
                style=draft.TextStyle(size=8, bold=True, align=1, auto_wrapping=True, max_line_width=0.78),
                border=draft.TextBorder(color=(0, 0, 0), width=30),
                clip_settings=draft.ClipSettings(transform_y=-0.73),
            )
            # 0.3.0 adds an unused speed reference to plain text without exporting
            # that speed material. These subtitles use no animation or effects.
            subtitle.extra_material_refs.clear()
            script.add_segment(subtitle, text_track)
            expected_lines.append(line["text"])
            timeline.append({"shot_id": shot["shot_id"], **line, "timeline_start_seconds": start / 1e6, "timeline_end_seconds": (start + duration) / 1e6})
            srt.append(f"{len(srt) + 1}\n{srt_timestamp(start / 1e6)} --> {srt_timestamp((start + duration) / 1e6)}\n{line['text']}\n")
        shot_start += microseconds(shot["selected_video_seconds"])
    add_picture_text_tracks(script, picture_texts)
    script.save()
    content_path = directory / "draft_content.json"
    content = read_json(content_path)
    draft_id = str(uuid.uuid4()).upper()
    content["id"], content["name"] = draft_id, name
    # Use the installed system font and avoid a network-downloaded font dependency.
    for material in content["materials"]["texts"]:
        body = json.loads(material["content"])
        for style in body["styles"]:
            style["font"] = {"id": "", "path": str(system_font)}
        material["content"] = json.dumps(body, ensure_ascii=False)
    original_clips = sum(1 for shot in report["shots"] for clip in shot["clips"] if clip.get("audio_mode") == "grok_original")
    original_lines = sum(len(shot["lines"]) for shot in report["shots"] if any(clip.get("audio_mode") == "grok_original" for clip in shot["clips"]))
    validate_draft(content, expected_lines, report["selected_shots"], picture_texts, original_audio_lines=original_lines, original_audio_segments=original_clips)
    write_json(content_path, content)
    now = time.time_ns() // 1000
    metadata = read_json(directory / "draft_meta_info.json")
    metadata.update({
        "draft_id": draft_id, "draft_name": name, "draft_fold_path": directory.as_posix(),
        "draft_root_path": output_parent.resolve().as_posix(), "draft_cover": "", "tm_duration": content["duration"],
        "tm_draft_create": now, "tm_draft_modified": now, "tm_draft_removed": 0,
        "draft_timeline_materials_size_": content_path.stat().st_size,
        "draft_is_invisible": False, "cloud_draft_sync": False,
    })
    write_json(directory / "draft_meta_info.json", metadata)
    write_json(directory / "实测排轨与素材检查.json", report)
    write_json(directory / "逐句时间表.json", timeline)
    write_json(directory / "画面文字时间表.json", {
        "source_mapping_path": str(PICTURE_TEXTS), "source_mapping_sha256": digest(PICTURE_TEXTS),
        "review_status": "待按实际画面校对位置、手部遮挡及道具文字连续性，尚未视觉验收",
        "entries": picture_texts, "continuity_checks": read_json(PICTURE_TEXTS)["continuity_checks"],
    })
    (directory / "全文字幕.srt").write_text("\n".join(srt), encoding="utf-8-sig")
    with (directory / "逐句时间表.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["shot_id", "id", "role", "text", "timeline_start_seconds", "timeline_end_seconds", "audio_path"])
        writer.writeheader()
        writer.writerows({key: row[key] for key in writer.fieldnames} for row in timeline)
    (directory / "状态说明.txt").write_text(f"{report['scope']}：720×1280、30fps，仅已生成剪映草稿，尚未在剪映 11.3 验证打开、完整听看或导出 MP4。最终在剪映选择 720p、30fps 导出。\n画面文字已独立分轨，位置与时间仍须对照真实画面，尤其纸面和木牌的透视、遮挡及连续性；不代表文字视觉验收通过。仅用普通文字与本地字体，导出前实际确认没有Pro素材、音色、特效或字体。\n", encoding="utf-8")
    print(f"已生成 {report['selected_shots']} 镜、{len(timeline)} 句草稿；需剪映实际打开验收：\n{directory}")
    return directory


def install_draft(directory, draft_root):
    directory, draft_root = Path(directory).resolve(), Path(draft_root).resolve()
    if not directory.is_dir() or not (directory / "实测排轨与素材检查.json").is_file():
        raise ValueError("仅安装本工具生成并校验的草稿目录。")
    check = read_json(directory / "实测排轨与素材检查.json")
    if not check.get("ready"):
        raise ValueError("草稿素材未通过检查。")
    running = subprocess.run(["tasklist", "/FI", "IMAGENAME eq JianyingPro.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace", timeout=15, check=True)
    if '"JianyingPro.exe"' in running.stdout:
        raise ValueError("请先退出剪映，再安装草稿；本工具不会结束应用或覆盖正在编辑的草稿。")
    root_file = draft_root / "root_meta_info.json"
    original_root_digest = digest(root_file)
    root = read_json(root_file)
    target = draft_root / directory.name
    if target.exists():
        raise FileExistsError(f"同名草稿已存在，保留不覆盖：{target}")
    # Recheck that all referenced original media still exists before registration.
    content = read_json(directory / "draft_content.json")
    for kind in ("videos", "audios"):
        for material in content["materials"][kind]:
            if not Path(material["path"]).is_file():
                raise FileNotFoundError(material["path"])
    metadata = read_json(directory / "draft_meta_info.json")
    if any(row.get("draft_id") == metadata["draft_id"] for row in root.get("all_draft_store", [])):
        raise ValueError("这个草稿已经登记，未重复安装。")
    backup = root_file.with_name(f"root_meta_info.before_JQ_v8_{datetime.now():%Y%m%d_%H%M%S_%f}.json")
    shutil.copy2(root_file, backup)
    shutil.copytree(directory, target)
    metadata.update({"draft_fold_path": target.as_posix(), "draft_root_path": draft_root.as_posix()})
    write_json(target / "draft_meta_info.json", metadata)
    entry = dict(metadata)
    entry.update({"draft_json_file": (target / "draft_content.json").as_posix(), "draft_timeline_materials_size": (target / "draft_content.json").stat().st_size, "streaming_edit_draft_ready": True})
    root.setdefault("all_draft_store", []).insert(0, entry)
    root["draft_ids"] = sum(not row.get("tm_draft_removed") for row in root["all_draft_store"])
    pending = root_file.with_name("root_meta_info.JQ_v8.pending.json")
    write_json(pending, root)
    if digest(root_file) != original_root_digest:
        raise ValueError("剪映草稿列表在复制期间发生变化，保留当前列表，停止登记。")
    os.replace(pending, root_file)
    print(f"已登记新的本地草稿：{target}\n原列表备份：{backup}\n请在剪映实际打开确认，尚未导出成片。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "scan", "build", "install"])
    parser.add_argument("--mapping", type=Path, default=MAPPING)
    parser.add_argument("--through", type=int, choices=range(1, 25), default=24, help="只处理开头 N 镜，并明确标为试片；默认全部 24 镜")
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--draft-root", type=Path, default=DEFAULT_DRAFT_ROOT)
    args = parser.parse_args()
    if args.command == "init":
        init_mapping()
    elif args.command in ("scan", "build"):
        report = inspect_assets(args.mapping, args.through)
        write_json(HERE / "接收检查.json", report)
        print(f"检查 {args.through} 镜：{'可排轨' if report['ready'] else str(len(report['issues'])) + ' 项待处理'}。详见 {HERE / '接收检查.json'}")
        if args.command == "build":
            build_draft(report)
    elif args.command == "install":
        if not args.draft:
            parser.error("install 必须提供 --draft 草稿目录")
        install_draft(args.draft, args.draft_root)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"停止：{exc}", file=sys.stderr)
        raise SystemExit(1)
