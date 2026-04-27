import os
import sys
import time
import shutil
import logging
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path

import flask
from flask import Flask, render_template, request, jsonify, send_file

BASEDIR = Path(__file__).parent
BASE_DIR = BASEDIR / "base"
TMP_DIR = BASEDIR / "tmp"
TMPIMG_DIR = BASEDIR / "tmpimg"
LOGS_DIR = BASEDIR / "logs"
ROUTES_DIR = BASEDIR / "routes"

for d in [BASE_DIR, TMP_DIR, TMPIMG_DIR, LOGS_DIR, ROUTES_DIR]:
    d.mkdir(exist_ok=True)

sys.path.insert(0, str(BASEDIR / "modules"))
try:
    from LibOrbisPkg import PKGMetadataExtractor
except ImportError:
    PKGMetadataExtractor = None

PAYLOAD_REPO = "https://github.com/infinitykkjstore/BGFT-Payload"
PAYLOAD_DIR = BASE_DIR / "BGFT-Payload"
PAYLOAD_LIB_DIR = PAYLOAD_DIR / "lib"
PAYLOAD_BIN = PAYLOAD_DIR / "payload.bin"

app = Flask(__name__, template_folder=str(BASEDIR / "templates"))
app.config['JSON_SORT_KEYS'] = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / 'server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

setup_status = {"complete": False, "error": None, "logs": []}
env_ready = threading.Event()

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    logger.info(msg)
    setup_status["logs"].append(line)
    if len(setup_status["logs"]) > 500:
        setup_status["logs"] = setup_status["logs"][-500:]

def run_cmd(cmd, cwd=None, capture=True, timeout=300):
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=capture, text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)

def check_env():
    log("Checking environment...")
    
    if not shutil.which("gcc"):
        log("gcc not found")
        return False
    if not shutil.which("make"):
        log("make not found")
        return False
    if not shutil.which("git"):
        log("git not found")
        return False
    
    log("Build tools OK")
    return True

def install_deps():
    log("Installing build dependencies...")
    
    has_sudo = shutil.which("sudo")
    has_apt = shutil.which("apt")
    
    if has_apt:
        log("Running apt update first...")
        code, out, err = run_cmd("apt update", timeout=120)
        log(f"apt update: {'OK' if code == 0 else err[:100]}")
    
    if not has_sudo and has_apt:
        log("sudo not found, attempting to install...")
        code, out, err = run_cmd("apt install sudo -y", timeout=60)
        if code == 0:
            log("sudo installed successfully")
            has_sudo = True
        else:
            log(f"Could not install sudo: {err}")
    
    if has_sudo:
        cmds = [
            "sudo apt update",
            "sudo apt install build-essential gcc make binutils yasm git file -y"
        ]
    elif has_apt:
        cmds = [
            "apt update",
            "apt install build-essential gcc make binutils yasm git file -y"
        ]
    else:
        log("Neither sudo nor apt available")
        return False
    
    for cmd in cmds:
        log(f"Running: {cmd}")
        code, out, err = run_cmd(cmd, timeout=180)
        if code != 0:
            log(f"Warning: {err}")
        else:
            log(f"OK")
    
    time.sleep(2)
    return True

def clone_payload_repo():
    if PAYLOAD_DIR.exists():
        log("Payload repo already exists, skipping clone")
        return True
    
    log(f"Cloning {PAYLOAD_REPO}...")
    code, out, err = run_cmd(f"git clone {PAYLOAD_REPO}", cwd=BASE_DIR, timeout=60)
    
    if code != 0:
        log(f"Clone failed: {err}")
        return False
    
    log("Repo cloned successfully")
    return True

def build_payload_lib():
    lib_dir = PAYLOAD_LIB_DIR
    if not lib_dir.exists():
        log(f"lib dir not found: {lib_dir}")
        return False
    
    log(f"Building payload lib in {lib_dir}...")
    code, out, err = run_cmd("make", cwd=lib_dir, timeout=120)
    
    if code != 0:
        log(f"lib build failed: {err}")
        return False
    
    log("Payload lib built successfully")
    return True

def full_setup():
    global setup_status
    
    try:
        if not check_env():
            result = install_deps()
            if not result or not check_env():
                raise Exception("Environment check failed after install")
        
        if not clone_payload_repo():
            raise Exception("Failed to clone payload repo")
        
        if not build_payload_lib():
            raise Exception("Failed to build payload lib")
        
        setup_status["complete"] = True
        log("SETUP COMPLETE - Ready to receive requests")
        
    except Exception as e:
        setup_status["error"] = str(e)
        log(f"SETUP FAILED: {e}")

def cleanup_old_payloads():
    if not TMP_DIR.exists():
        return
    
    now = datetime.now()
    cutoff = now - timedelta(minutes=15)
    
    for f in TMP_DIR.glob("*.bin"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                log(f"Cleaned up old payload: {f.name}")
        except Exception as e:
            log(f"Cleanup error: {e}")

def compile_payload(params):
    log(f"Compiling payload: {params.get('PKG_NAME', 'Unknown')}")
    
    run_cmd("make clean", cwd=str(PAYLOAD_DIR), timeout=30)
    
    def esc(v):
        return str(v).replace('"', '\\"')
    
    cmd = f'''make \\
PKG_URL="{esc(params["PKG_URL"])}" \\
PKG_NAME="{esc(params["PKG_NAME"])}" \\
PKG_ID="{esc(params["PKG_ID"])}" \\
PKG_ICON="{esc(params["PKG_ICON"])}" \\
PKG_TYPE="{esc(params["PKG_TYPE"])}" \\
PKG_SIZE={params["PKG_SIZE"]}
'''
    
    log(f"Running: {cmd[:100]}...")
    
    code, out, err = run_cmd(cmd, cwd=str(PAYLOAD_DIR), timeout=300)
    
    log(f"Make output: {out[:500]}" if out else "No output")
    if err:
        log(f"Make stderr: {err[:500]}")
    
    if PAYLOAD_BIN.exists():
        log("payload.bin generated successfully")
    elif code != 0 and "file: not found" in err:
        log("Warning: 'file' command missing but continuing...")
        if (PAYLOAD_DIR / "payload.bin").exists():
            log("payload.bin found, continuing...")
        else:
            log(f"Compilation failed: {err}")
            return None, f"Compilation failed: {err}"
    elif code != 0:
        log(f"Compilation failed: {err}")
        return None, f"Compilation failed: {err}"
    
    if not PAYLOAD_BIN.exists():
        log("payload.bin not found after compilation")
        return None, "payload.bin not found"
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = params.get("PKG_NAME", "payload").replace(" ", "_")
    out_name = f"{name}_{ts}.bin"
    out_path = TMP_DIR / out_name
    
    shutil.copy2(PAYLOAD_BIN, out_path)
    log(f"Payload saved: {out_name} ({out_path.stat().st_size} bytes)")
    
    return out_path, None

def background_setup():
    t = threading.Thread(target=full_setup)
    t.daemon = True
    t.start()
    
    def wait_loop():
        while not setup_status["complete"] and setup_status["error"] is None:
            time.sleep(1)
        env_ready.set()
    
    threading.Thread(target=wait_loop, daemon=True).start()

def extract_pkg_metadata(pkg_url: str, host_url: str = "") -> dict:
    """Extrai metadados do PKG/manifesto usando LibOrbisPkg"""
    log(f"Extracting metadata from: {pkg_url}")
    
    if PKGMetadataExtractor is None:
        log("LibOrbisPkg not available")
        return {"success": False, "error": "LibOrbisPkg module not found"}
    
    try:
        extractor = PKGMetadataExtractor(pkg_url, verbose=True)
        metadata = extractor.extract_metadata()
        
        title = metadata.get('title', 'Unknown')
        title_id = metadata.get('title_id', '')
        category = metadata.get('category', 'gd')
        pkg_size = metadata.get('package_size', 0)
        bgft_type = metadata.get('bgft_package_type', 'PS4GD')
        icon_data = metadata.get('icon_data')
        
        icon_url = None
        if icon_data:
            title_safe = "".join(c for c in title if c.isalnum() or c in "_").strip()[:30]
            title_id_safe = "".join(c for c in title_id if c.isalnum() or c in "_").strip()[:10]
            icon_filename = f"{title_safe}_{title_id_safe}.png"
            icon_path = TMPIMG_DIR / icon_filename
            
            with open(icon_path, 'wb') as f:
                f.write(icon_data)
            log(f"Icon saved: {icon_path.name}")
            icon_url = f"{host_url}api/icon/{icon_path.name}"
        
        return {
            "success": True,
            "title": title,
            "title_id": title_id,
            "category": category,
            "pkg_size": pkg_size,
            "pkg_type": bgft_type,
            "icon_path": icon_url,
            "content_id": metadata.get('content_id', ''),
        }
        
    except Exception as e:
        log(f"Metadata extraction failed: {e}")
        return {"success": False, "error": str(e)}

@app.route("/api/meta")
def api_meta():
    pkg_url = request.args.get("url", "")
    
    if not pkg_url:
        return jsonify({"error": "URL required"}), 400
    
    result = extract_pkg_metadata(pkg_url, request.url_root)
    
    if not result.get("success"):
        return jsonify(result), 500
    
    return jsonify(result)

@app.route("/api/icon/<path:filename>")
def api_icon(filename):
    import urllib.parse
    decoded_name = urllib.parse.unquote(filename)
    
    safe_name = "".join(c for c in decoded_name if c.isalnum() or c in "._-_")
    
    for f in TMPIMG_DIR.glob("*.png"):
        if safe_name.lower() in f.name.lower().replace("_", "").replace(".", ""):
            return send_file(f, mimetype="image/png")
    
    for f in TMPIMG_DIR.glob("*.png"):
        if f.stem.startswith(safe_name.rsplit("_", 1)[0][:20]):
            return send_file(f, mimetype="image/png")
    
    if not safe_name or not list(TMPIMG_DIR.glob("*.png")):
        return jsonify({"error": "Icon not found", "files": [f.name for f in TMPIMG_DIR.glob("*.png")]}), 404
    
    return jsonify({"error": "Icon not found"}), 404

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    return jsonify({
        "ready": setup_status["complete"],
        "error": setup_status["error"],
        "logs": setup_status["logs"][-50:]
    })

@app.route("/api/build")
def api_build():
    if not setup_status["complete"]:
        return jsonify({"error": "Environment not ready", "logs": setup_status["logs"]}), 400
    
    params = {
        "PKG_URL": request.args.get("url", ""),
        "PKG_NAME": request.args.get("name", ""),
        "PKG_ID": request.args.get("id", ""),
        "PKG_ICON": request.args.get("icon", ""),
        "PKG_TYPE": request.args.get("type", "PS4GD"),
        "PKG_SIZE": request.args.get("size", "0")
    }
    
    required = ["PKG_URL", "PKG_NAME", "PKG_ID"]
    missing = [k for k in required if not params.get(k)]
    if missing:
        return jsonify({"error": f"Missing params: {missing}"}), 400
    
    for k in ["PKG_SIZE"]:
        try:
            params[k] = int(params[k])
        except:
            pass
    
    params["PKG_NAME"] = "".join(c for c in params["PKG_NAME"] if c.isalnum() or c in " -_").strip()[:50]
    params["PKG_URL"] = params["PKG_URL"][:500]
    params["PKG_ID"] = "".join(c for c in params["PKG_ID"] if c.isalnum() or c in "-_").strip()[:30]
    params["PKG_ICON"] = params["PKG_ICON"][:300]
    params["PKG_TYPE"] = params["PKG_TYPE"][:10]
    
    payload_path, err = compile_payload(params)
    
    if err:
        return jsonify({"error": err, "logs": setup_status["logs"]}), 500
    
    return jsonify({
        "success": True,
        "file": payload_path.name,
        "size": payload_path.stat().st_size,
        "logs": setup_status["logs"]
    })

@app.route("/api/download/<path:filename>")
def api_download(filename):
    if not setup_status["complete"]:
        return jsonify({"error": "Environment not ready"}), 400
    
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")
    path = TMP_DIR / safe_name
    
    if not path.exists():
        return jsonify({"error": "File not found"}), 404
    
    return send_file(path, as_attachment=True, download_name="payload.bin")

@app.route("/api/cleanup", methods=["POST"])
def api_cleanup():
    cleanup_old_payloads()
    return jsonify({"success": True})

def init():
    log("=== BGFT Payload Builder Server ===")
    log(f"Base dir: {BASEDIR}")
    log(f"Payload dir: {PAYLOAD_DIR}")
    
    check_env()
    
    if PAYLOAD_DIR.exists() and (PAYLOAD_LIB_DIR / "libPS4Link.a").exists():
        log("Environment already configured, skipping setup")
        setup_status["complete"] = True
        env_ready.set()
    else:
        log("Starting full environment setup...")
        background_setup()
    
    cleanup_old_payloads()

if __name__ == "__main__":
    init()
    app.run(host="0.0.0.0", port=51584, debug=False, threaded=True)