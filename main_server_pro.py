import os
import sys  # <--- 1. 导入 SYS 模块
import socket
import io
import base64
import time
import math
from flask import (
    Flask, render_template, request, send_from_directory,
    redirect, url_for, abort, send_file
)
from waitress import serve
import qrcode

# --- 配置 ---
UPLOAD_FOLDER = 'uploads'  # 这是一个相对的文件夹名
PORT = 5000
app = Flask(__name__)

# ==========================================================
# VVV 2. 这是核心修复：定义绝对路径 VVV
# ==========================================================
# 智能地判断我们是在 .py 脚本中还是在 .exe 文件中
if getattr(sys, 'frozen', False):
    # 如果是 .exe (frozen)
    base_dir = os.path.dirname(sys.executable)
else:
    # 如果是 .py
    base_dir = os.path.dirname(os.path.abspath(__file__))

# 构造一个【绝对路径】指向 'uploads' 文件夹
# 例如 'D:\Lan-Transfer\dist\uploads'
UPLOAD_FOLDER_ABSOLUTE = os.path.join(base_dir, UPLOAD_FOLDER)

# 把这个绝对路径存入 app 配置中
app.config['UPLOAD_FOLDER_PATH'] = UPLOAD_FOLDER_ABSOLUTE
# ==========================================================

app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

# 确保【绝对路径】的上传文件夹存在
os.makedirs(app.config['UPLOAD_FOLDER_PATH'], exist_ok=True)

active_devices = set()

# --- 辅助函数 ---

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80)) 
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1' 

def generate_qr_code(url):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    base64_data = base64.b64encode(buf.getvalue()).decode('utf-8')
    return base64_data

def human_readable_size(size_bytes):
    if size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.log(size_bytes, 1024))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def get_files_info():
    """获取上传目录中所有文件的详细信息"""
    files_info = []
    try:
        # ==========================================================
        # 3. 使用【绝对路径】读取文件列表
        upload_path = app.config['UPLOAD_FOLDER_PATH']
        filenames = os.listdir(upload_path)
        # ==========================================================
        for filename in sorted(filenames, key=lambda f: os.path.getmtime(os.path.join(upload_path, f)), reverse=True):
            if filename.startswith('.'):
                continue
            
            filepath = os.path.join(upload_path, filename)
            try:
                stat = os.stat(filepath)
                files_info.append({
                    'name': filename,
                    'size': human_readable_size(stat.st_size),
                    'time': time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_mtime))
                })
            except FileNotFoundError:
                continue
    except Exception as e:
        print(f"读取文件列表时出错: {e}")
    return files_info

# --- 路由 (Web 界面) ---

@app.before_request
def track_device():
    global active_devices
    if request.remote_addr != app.config.get('SERVER_IP', '127.0.0.1'):
        active_devices.add(request.remote_addr)

@app.route('/')
def index():
    files = get_files_info()
    server_url = f"http://{app.config['SERVER_IP']}:{PORT}"
    qr_data = generate_qr_code(server_url)
    
    return render_template(
        'index_pro.html',
        files=files,
        qr_data=qr_data,
        server_url=server_url,
        active_devices=list(active_devices)
    )

@app.route('/upload', methods=['POST'])
def upload_file():
    """处理文件上传 (无文件类型限制)"""
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        return redirect(request.url)
    
    try:
        filename = os.path.basename(file.filename) # 清理文件名
        if filename == '':
            return "无效的文件名", 400

        # ==========================================================
        # 4. 使用【绝对路径】保存文件
        file.save(os.path.join(app.config['UPLOAD_FOLDER_PATH'], filename))
        # ==========================================================
        return redirect(url_for('index'))
    except Exception as e:
        print(f"保存文件时出错: {e}") 
        print(f"尝试保存的文件名是: {filename}")
        return "保存文件时出错", 500


@app.route('/download/<path:filename>')
def download_file(filename):
    """处理文件下载 (使用 send_file 增强版)"""
    
    print(f"--- 收到下载请求: {filename} ---")
    
    try:
        # ==========================================================
        # 5. 使用【绝对路径】查找文件
        filepath = os.path.join(app.config['UPLOAD_FOLDER_PATH'], filename)
        # ==========================================================
        
        print(f"--- 正在查找【绝对路径】: {filepath} ---")

        if not os.path.exists(filepath):
            print(f"--- 错误: 文件未找到! ---")
            abort(404)
        
        print(f"--- 文件已找到, 准备发送... ---")
        return send_file(filepath, as_attachment=True)

    except Exception as e:
        print(f"--- 下载时发生未知错误: {e} ---")
        abort(500)

# --- 启动器 ---
if __name__ == '__main__':
    server_ip = get_lan_ip()
    app.config['SERVER_IP'] = server_ip
    
    print("\n" + "="*50)
    print(" 局域网文件传输工具已启动！")
    print(f" PC端 (本机) 访问: http://127.0.0.1:{PORT}")
    print(f" 手机/电视/其他设备请访问: http://{server_ip}:{PORT}")
    print(" (或直接扫描 PC 页面上显示的二维码)")
    print("="*50 + "\n")
    
    serve(app, host='0.0.0.0', port=PORT, threads=16)