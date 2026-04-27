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
LOGS_DIR = BASEDIR / "logs"
ROUTES_DIR = BASEDIR / "routes"

for d in [BASE_DIR, TMP_DIR, LOGS_DIR, ROUTES_DIR]:
    d.mkdir(exist_ok=True)

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
    
    cmds = [
        "sudo apt update",
        "sudo apt install build-essential gcc make binutils yasm git -y"
    ]
    
    for cmd in cmds:
        log(f"Running: {cmd}")
        code, out, err = run_cmd(cmd, timeout=180)
        if code != 0:
            log(f"Warning: {err}")
        else:
            log(f"OK")
    
    time.sleep(2)

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
            install_deps()
            if not check_env():
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
    
    env = os.environ.copy()
    env.update(params)
    
    code, out, err = run_cmd(
        "make clean", 
        cwd=PAYLOAD_DIR, 
        timeout=30
    )
    
    make_cmd = " ".join([f'{k}="{v}"' if ' ' in str(v) else f'{k}={v}' for k, v in params.items()])
    log(f"Running: make {make_cmd}")
    
    code, out, err = run_cmd(f"make {make_cmd}", cwd=PAYLOAD_DIR, timeout=300)
    
    log(f"Make output: {out[:500]}" if out else "No output")
    if err:
        log(f"Make stderr: {err[:500]}")
    
    if code != 0:
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