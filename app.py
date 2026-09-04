import os
import time
import socket
import io
import base64
import logging
import mimetypes
import qrcode
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, Response
from werkzeug.utils import secure_filename

from services.youtube_service import get_video_info, start_download_task, get_task_status
from services.media_service import get_media_info, cut_media, convert_video, parse_time_to_seconds, seconds_to_time_str

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB Max upload limit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
UPLOADS_DIR = os.path.join(DOWNLOADS_DIR, 'uploads')
TRIMMED_DIR = os.path.join(DOWNLOADS_DIR, 'trimmed')
CONVERTED_DIR = os.path.join(DOWNLOADS_DIR, 'converted')

for d in [DOWNLOADS_DIR, UPLOADS_DIR, TRIMMED_DIR, CONVERTED_DIR]:
    os.makedirs(d, exist_ok=True)

def get_local_ip() -> str:
    """Returns local LAN IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def find_file_path(folder_type: str, filename: str) -> str:
    """Resolves secure absolute file path based on folder type and filename."""
    folder_map = {
        "downloads": DOWNLOADS_DIR,
        "uploads": UPLOADS_DIR,
        "trimmed": TRIMMED_DIR,
        "converted": CONVERTED_DIR,
    }
    base = folder_map.get(folder_type, DOWNLOADS_DIR)
    
    # Try direct file match
    path = os.path.join(base, filename)
    if os.path.exists(path):
        return path
        
    # Search across other folders if not found in given folder
    for f in [DOWNLOADS_DIR, UPLOADS_DIR, TRIMMED_DIR, CONVERTED_DIR]:
        candidate = os.path.join(f, filename)
        if os.path.exists(candidate):
            return candidate
            
    return path

@app.route('/')
def index():
    return render_template('index.html')

from services.youtube_service import get_video_info, start_download_task, get_task_status
from services.media_service import get_media_info, cut_media, convert_video, parse_time_to_seconds, seconds_to_time_str
from services.tunnel_service import tunnel_manager

def generate_qr_base64(url: str, fill_color: str = "#6366f1") -> str:
    """Generates base64 data URI for QR code."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=7,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color="#0b0f19")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"

STATIC_DIR = os.path.join(BASE_DIR, 'static')

@app.route('/manifest.json')
def pwa_manifest():
    return send_from_directory(STATIC_DIR, 'manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def pwa_service_worker():
    return send_from_directory(STATIC_DIR, 'sw.js', mimetype='application/javascript')

@app.route('/api/mobile-info', methods=['GET'])
def api_mobile_info():
    port = int(os.environ.get('PORT', 5050))
    local_ip = get_local_ip()
    local_url = f"http://{local_ip}:{port}"
    public_url = tunnel_manager.get_public_url()
    tunnel_status = tunnel_manager.get_status_info()

    base_active_url = public_url if public_url else local_url
    zip_download_url = f"{base_active_url}/static/mediastudio_mobile.zip"
    termux_apk_url = "https://f-droid.org/repo/com.termux_1020.apk"

    local_qr = generate_qr_base64(local_url, fill_color="#06b6d4")
    global_qr = generate_qr_base64(public_url, fill_color="#ec4899") if public_url else None
    termux_apk_qr = generate_qr_base64(termux_apk_url, fill_color="#10b981")
    zip_download_qr = generate_qr_base64(zip_download_url, fill_color="#f59e0b")

    return jsonify({
        "success": True,
        "port": port,
        "local_ip": local_ip,
        "local_url": local_url,
        "local_qr": local_qr,
        "global_url": public_url,
        "global_qr": global_qr,
        "termux_apk_url": termux_apk_url,
        "termux_apk_qr": termux_apk_qr,
        "zip_download_url": zip_download_url,
        "zip_download_qr": zip_download_qr,
        "tunnel": tunnel_status
    })

@app.route('/api/tunnel/start', methods=['POST'])
def api_tunnel_start():
    port = int(os.environ.get('PORT', 5050))
    tunnel_manager.port = port
    tunnel_manager.start_tunnel(async_mode=True)
    return jsonify({"success": True, "message": "터널 시작 요청 완료", "tunnel": tunnel_manager.get_status_info()})

@app.route('/api/info', methods=['POST'])
def api_get_info():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({"success": False, "error": "유튜브 URL을 입력해주세요."}), 400

    info = get_video_info(url)
    if not info.get('success'):
        return jsonify(info), 400
    return jsonify(info)

@app.route('/api/download', methods=['POST'])
def api_start_download():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    format_type = data.get('format_type', 'mp3').lower()
    quality = data.get('quality', 'best')

    if not url:
        return jsonify({"success": False, "error": "유튜브 URL을 입력해주세요."}), 400

    if format_type not in ['mp3', 'mp4']:
        return jsonify({"success": False, "error": "지원하지 않는 포맷입니다. (mp3 또는 mp4)"}), 400

    task_id = start_download_task(url, format_type, quality, DOWNLOADS_DIR)
    return jsonify({"success": True, "task_id": task_id})

@app.route('/api/download/status/<task_id>', methods=['GET'])
def api_get_download_status(task_id):
    status = get_task_status(task_id)
    if not status:
        return jsonify({"success": False, "error": "존재하지 않는 작업입니다."}), 404
    return jsonify({"success": True, "task": status})

@app.route('/api/upload', methods=['POST'])
def api_upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "업로드된 파일이 없습니다."}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"success": False, "error": "선택된 파일이 없습니다."}), 400

    # Ensure clean filename
    original_name = file.filename
    clean_name = f"{int(time.time())}_{secure_filename(original_name)}"
    if not clean_name.strip('_.'):
        clean_name = f"upload_{int(time.time())}_{original_name}"

    save_path = os.path.join(UPLOADS_DIR, clean_name)
    file.save(save_path)

    # Get media info
    info = get_media_info(save_path)
    return jsonify({
        "success": True,
        "filename": clean_name,
        "original_name": original_name,
        "folder": "uploads",
        "file_url": f"/api/files/uploads/{clean_name}",
        "info": info
    })

@app.route('/api/media/info', methods=['POST'])
def api_media_info():
    data = request.get_json() or {}
    filename = data.get('filename', '')
    folder = data.get('folder', 'downloads')
    
    file_path = find_file_path(folder, filename)
    if not os.path.exists(file_path):
        return jsonify({"success": False, "error": "파일을 찾을 수 없습니다."}), 404

    info = get_media_info(file_path)
    return jsonify({"success": True, "filename": filename, "folder": folder, "info": info})

@app.route('/api/audio/trim', methods=['POST'])
def api_audio_trim():
    data = request.get_json() or {}
    filename = data.get('filename', '')
    folder = data.get('folder', 'downloads')
    start_time_raw = data.get('start_time', 0)
    end_time_raw = data.get('end_time', 0)
    output_format = data.get('output_format', 'mp3').lower()
    fade_in = float(data.get('fade_in', 0))
    fade_out = float(data.get('fade_out', 0))

    start_time = parse_time_to_seconds(start_time_raw)
    end_time = parse_time_to_seconds(end_time_raw)

    if not filename:
        return jsonify({"success": False, "error": "파일명을 지정해주세요."}), 400

    input_path = find_file_path(folder, filename)
    if not os.path.exists(input_path):
        return jsonify({"success": False, "error": f"원본 파일({filename})을 찾을 수 없습니다."}), 404

    # Output filename
    base_name = os.path.splitext(os.path.basename(filename))[0]
    out_filename = f"trim_{int(time.time())}_{base_name}.{output_format}"
    output_path = os.path.join(TRIMMED_DIR, out_filename)

    res = cut_media(
        input_path=input_path,
        output_path=output_path,
        start_time=start_time,
        end_time=end_time,
        output_format=output_format,
        fade_in=fade_in,
        fade_out=fade_out
    )

    if not res.get('success'):
        return jsonify(res), 500

    res["file_url"] = f"/api/files/trimmed/{out_filename}"
    res["folder"] = "trimmed"
    return jsonify(res)

@app.route('/api/video/convert', methods=['POST'])
def api_video_convert():
    data = request.get_json() or {}
    filename = data.get('filename', '')
    folder = data.get('folder', 'downloads')
    target_format = data.get('target_format', 'wmv').lower().replace('.', '')
    resolution = data.get('resolution', 'original')
    quality = data.get('quality', 'high')

    if not filename:
        return jsonify({"success": False, "error": "파일명을 지정해주세요."}), 400

    input_path = find_file_path(folder, filename)
    if not os.path.exists(input_path):
        return jsonify({"success": False, "error": f"원본 파일({filename})을 찾을 수 없습니다."}), 404

    base_name = os.path.splitext(os.path.basename(filename))[0]
    out_filename = f"converted_{int(time.time())}_{base_name}.{target_format}"
    output_path = os.path.join(CONVERTED_DIR, out_filename)

    res = convert_video(
        input_path=input_path,
        output_path=output_path,
        target_format=target_format,
        resolution=resolution,
        quality=quality
    )

    if not res.get('success'):
        return jsonify(res), 500

    res["file_url"] = f"/api/files/converted/{out_filename}"
    res["folder"] = "converted"
    return jsonify(res)

@app.route('/api/files/<folder>/<filename>', methods=['GET'])
def api_get_file(folder, filename):
    folder_map = {
        "downloads": DOWNLOADS_DIR,
        "uploads": UPLOADS_DIR,
        "trimmed": TRIMMED_DIR,
        "converted": CONVERTED_DIR,
    }
    dir_path = folder_map.get(folder, DOWNLOADS_DIR)
    file_path = os.path.join(dir_path, filename)

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    download_mode = request.args.get('download', '0') == '1'
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        ext = os.path.splitext(filename)[1].lower()
        if ext == '.mp3':
            mime_type = 'audio/mpeg'
        elif ext == '.mp4':
            mime_type = 'video/mp4'
        elif ext == '.wmv':
            mime_type = 'video/x-ms-wmv'
        elif ext == '.avi':
            mime_type = 'video/x-msvideo'
        else:
            mime_type = 'application/octet-stream'

    return send_file(
        file_path,
        mimetype=mime_type,
        as_attachment=download_mode,
        download_name=filename
    )

@app.route('/api/history', methods=['GET'])
def api_history():
    files = []
    folders = [
        ("downloads", DOWNLOADS_DIR, "다운로드"),
        ("trimmed", TRIMMED_DIR, "오디오 편집"),
        ("converted", CONVERTED_DIR, "포맷 변환"),
        ("uploads", UPLOADS_DIR, "업로드")
    ]

    for f_type, f_dir, f_label in folders:
        if not os.path.exists(f_dir):
            continue
        for fname in os.listdir(f_dir):
            full_path = os.path.join(f_dir, fname)
            if os.path.isfile(full_path):
                stat = os.stat(full_path)
                ext = os.path.splitext(fname)[1].lower().replace('.', '')
                files.append({
                    "filename": fname,
                    "folder": f_type,
                    "category": f_label,
                    "extension": ext,
                    "size": stat.st_size,
                    "size_formatted": f"{stat.st_size / (1024 * 1024):.2f} MB" if stat.st_size >= 1024*1024 else f"{stat.st_size / 1024:.1f} KB",
                    "created_at": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime)),
                    "file_url": f"/api/files/{f_type}/{fname}",
                    "is_video": ext in ['mp4', 'wmv', 'avi', 'mkv', 'webm', 'mov'],
                    "is_audio": ext in ['mp3', 'wav', 'm4a', 'ogg', 'flac', 'aac']
                })

    # Sort descending by modified time
    files.sort(key=lambda x: x['created_at'], reverse=True)
    return jsonify({"success": True, "files": files})

@app.route('/api/delete', methods=['POST'])
def api_delete_file():
    data = request.get_json() or {}
    filename = data.get('filename', '')
    folder = data.get('folder', 'downloads')

    file_path = find_file_path(folder, filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return jsonify({"success": True, "message": "삭제 완료"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": False, "error": "파일을 찾을 수 없습니다."}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    logger.info(f"Starting YouTube Downloader & Media Studio Web App on http://127.0.0.1:{port} ...")
    
    # Auto start Cloudflare tunnel for external LTE/5G global access
    tunnel_manager.port = port
    tunnel_manager.start_tunnel(async_mode=True)
    
    app.run(host='0.0.0.0', port=port, debug=False)
