import os
import subprocess
import json
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def parse_time_to_seconds(time_str: str) -> float:
    """
    Parses time strings like '01:30', '00:01:30', '90', '90.5' to float seconds.
    """
    if isinstance(time_str, (int, float)):
        return float(time_str)
    
    time_str = str(time_str).strip()
    if not time_str:
        return 0.0

    parts = time_str.split(':')
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) >= 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return 0.0
    return 0.0

def seconds_to_time_str(seconds: float) -> str:
    """
    Formats seconds float to 'HH:MM:SS' or 'MM:SS' string.
    """
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:05.2f}"
    return f"{mins:02d}:{secs:05.2f}"

def get_media_info(file_path: str) -> Dict[str, Any]:
    """
    Uses ffprobe to extract rich media metadata.
    """
    if not os.path.exists(file_path):
        return {"error": "File does not exist"}

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            errors='replace',
            check=True
        )
        data = json.loads(result.stdout or "{}")
        
        format_info = data.get("format", {})
        streams = data.get("streams", [])
        
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        
        duration = float(format_info.get("duration", 0.0))
        if duration == 0.0 and video_stream and "duration" in video_stream:
            try:
                duration = float(video_stream["duration"])
            except ValueError:
                pass
        if duration == 0.0 and audio_stream and "duration" in audio_stream:
            try:
                duration = float(audio_stream["duration"])
            except ValueError:
                pass

        size = int(format_info.get("size", os.path.getsize(file_path)))
        
        info = {
            "duration": duration,
            "duration_formatted": seconds_to_time_str(duration),
            "size": size,
            "size_formatted": f"{size / (1024 * 1024):.2f} MB",
            "format_name": format_info.get("format_name", ""),
            "has_video": video_stream is not None,
            "has_audio": audio_stream is not None,
            "video": {},
            "audio": {}
        }
        
        if video_stream:
            info["video"] = {
                "codec": video_stream.get("codec_name", ""),
                "width": video_stream.get("width", 0),
                "height": video_stream.get("height", 0),
                "fps": eval(video_stream.get("r_frame_rate", "0/1")) if "/" in video_stream.get("r_frame_rate", "") else 0
            }
            
        if audio_stream:
            info["audio"] = {
                "codec": audio_stream.get("codec_name", ""),
                "sample_rate": audio_stream.get("sample_rate", ""),
                "channels": audio_stream.get("channels", 2),
                "bitrate": format_info.get("bit_rate", "")
            }
            
        return info
    except Exception as e:
        logger.error(f"Failed to probe media: {e}")
        return {
            "error": str(e),
            "duration": 0.0,
            "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0
        }

def cut_media(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
    output_format: str = "mp3",
    fade_in: float = 0.0,
    fade_out: float = 0.0
) -> Dict[str, Any]:
    """
    Cuts an audio or video file from start_time to end_time.
    Supports audio filters like fade-in and fade-out.
    """
    if not os.path.exists(input_path):
        return {"success": False, "error": "Input file not found"}

    duration = end_time - start_time
    if duration <= 0:
        return {"success": False, "error": "End time must be greater than start time"}

    output_format = output_format.lower().replace(".", "")
    is_audio_only = output_format in ["mp3", "wav", "m4a", "ogg", "aac", "flac"]
    
    cmd = ["ffmpeg", "-y", "-ss", str(start_time), "-to", str(end_time), "-i", input_path]
    
    # Audio filters
    filters = []
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        st_out = max(0.0, duration - fade_out)
        filters.append(f"afade=t=out:st={st_out}:d={fade_out}")
        
    filter_complex = ",".join(filters) if filters else None
    
    if is_audio_only:
        cmd.append("-vn")
        if filter_complex:
            cmd.extend(["-af", filter_complex])
            
        if output_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])
        elif output_format == "wav":
            cmd.extend(["-c:a", "pcm_s16le"])
        elif output_format == "m4a" or output_format == "aac":
            cmd.extend(["-c:a", "aac", "-b:a", "256k"])
        elif output_format == "ogg":
            cmd.extend(["-c:a", "libvorbis", "-q:a", "6"])
        elif output_format == "flac":
            cmd.extend(["-c:a", "flac"])
        else:
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])
    else:
        # Video cut
        if filter_complex:
            cmd.extend(["-af", filter_complex])
        cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "fast", "-c:a", "aac", "-b:a", "192k"])

    cmd.append(output_path)
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            return {"success": False, "error": f"FFmpeg failed: {result.stderr[-500:]}"}
            
        return {
            "success": True,
            "output_path": output_path,
            "output_filename": os.path.basename(output_path),
            "duration": duration,
            "info": get_media_info(output_path)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def convert_video(
    input_path: str,
    output_path: str,
    target_format: str,
    resolution: Optional[str] = None,
    quality: str = "high"
) -> Dict[str, Any]:
    """
    Converts video/audio files between MP4, WMV, AVI, MKV, WEBM, MP3.
    Target formats: mp4, wmv, avi, mkv, webm, mp3.
    """
    if not os.path.exists(input_path):
        return {"success": False, "error": "Input file not found"}

    target_format = target_format.lower().replace(".", "")
    cmd = ["ffmpeg", "-y", "-i", input_path]
    
    # Video filters (Resolution scaling if requested)
    vf_filters = []
    if resolution and resolution != "original":
        if resolution == "1080p":
            vf_filters.append("scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2")
        elif resolution == "720p":
            vf_filters.append("scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2")
        elif resolution == "480p":
            vf_filters.append("scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2")
    
    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    # Format specific codecs
    if target_format == "mp4":
        crf = "18" if quality == "high" else ("23" if quality == "medium" else "28")
        cmd.extend([
            "-c:v", "libx264",
            "-crf", crf,
            "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart"
        ])
    elif target_format == "wmv":
        # Windows Media Video 2 + WMA 2
        v_bitrate = "4000k" if quality == "high" else ("2500k" if quality == "medium" else "1200k")
        cmd.extend([
            "-c:v", "wmv2",
            "-b:v", v_bitrate,
            "-c:a", "wmav2",
            "-b:a", "192k"
        ])
    elif target_format == "avi":
        # Xvid or MPEG-4 AVI for universal compatibility
        qscale = "3" if quality == "high" else ("5" if quality == "medium" else "8")
        cmd.extend([
            "-c:v", "mpeg4",
            "-vtag", "XVID",
            "-qscale:v", qscale,
            "-c:a", "libmp3lame",
            "-b:a", "192k"
        ])
    elif target_format == "mkv":
        crf = "18" if quality == "high" else ("23" if quality == "medium" else "28")
        cmd.extend([
            "-c:v", "libx264",
            "-crf", crf,
            "-c:a", "aac",
            "-b:a", "192k"
        ])
    elif target_format == "webm":
        crf = "24" if quality == "high" else ("30" if quality == "medium" else "36")
        cmd.extend([
            "-c:v", "libvpx-vp9",
            "-crf", crf,
            "-b:v", "0",
            "-c:a", "libopus",
            "-b:a", "128k"
        ])
    elif target_format == "mp3":
        # Extract audio only
        bitrate = "320k" if quality == "high" else ("192k" if quality == "medium" else "128k")
        cmd.extend([
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", bitrate
        ])
    else:
        # Default fallback
        cmd.extend(["-c:v", "libx264", "-c:a", "aac"])

    cmd.append(output_path)

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode != 0:
            logger.error(f"FFmpeg conversion error: {result.stderr}")
            return {"success": False, "error": f"Conversion failed: {result.stderr[-500:]}"}

        return {
            "success": True,
            "output_path": output_path,
            "output_filename": os.path.basename(output_path),
            "target_format": target_format,
            "info": get_media_info(output_path)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
