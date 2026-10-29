import os
import socket
import time

from flask import Flask, jsonify

APP_VERSION = os.environ.get("APP_VERSION", "1.2.0")
UNHEALTHY_MARKER = "/tmp/unhealthy"
REQUESTS_LOG = "/tmp/requests.log"
START_TIME = time.time()

app = Flask(__name__)

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>K8s Self-Healing App</title>
<style>
  :root {
    --bg: #0b1020; --card: #131a2e; --line: #232d4a;
    --text: #e8ecf8; --muted: #8a93ad; --accent: #4f8cff;
    --ok: #2fd67b; --bad: #ff5c6c;
  }
  * { box-sizing: border-box; margin: 0; }
  body { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
         background: radial-gradient(1200px 600px at 70% -10%, #1b2b55 0%, var(--bg) 55%);
         color: var(--text); min-height: 100vh; display: flex; align-items: center;
         justify-content: center; padding: 2rem; }
  .wrap { width: 100%; max-width: 880px; }
  header { display: flex; align-items: center; gap: 14px; margin-bottom: 22px; flex-wrap: wrap; }
  .helm { width: 42px; height: 42px; flex: none; }
  h1 { font-size: 1.15rem; letter-spacing: 2px; text-transform: uppercase; }
  .sub { color: var(--muted); font-size: .8rem; margin-top: 4px; }
  .pill { margin-left: auto; display: flex; align-items: center; gap: 8px;
          border: 1px solid var(--line); padding: 8px 14px; border-radius: 999px;
          font-size: .8rem; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--ok);
         box-shadow: 0 0 0 0 rgba(47,214,123,.7); animation: pulse 1.6s infinite; }
  .pill.bad .dot { background: var(--bad); box-shadow: 0 0 0 0 rgba(255,92,108,.7); }
  .pill.bad { color: var(--bad); border-color: #4a2530; }
  @keyframes pulse { 70% { box-shadow: 0 0 0 9px rgba(47,214,123,0); } }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
  @media (max-width: 720px) { .grid { grid-template-columns: repeat(2, 1fr); } }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
          padding: 18px; }
  .card .label { color: var(--muted); font-size: .7rem; letter-spacing: 1.5px;
                 text-transform: uppercase; margin-bottom: 10px; }
  .card .value { font-size: 1.25rem; word-break: break-all; }
  .card .value.ok { color: var(--ok); }
  .card .value.bad { color: var(--bad); }
  .links { margin-top: 18px; display: flex; gap: 10px; flex-wrap: wrap; }
  .links a { color: var(--accent); text-decoration: none; font-size: .8rem;
             border: 1px solid var(--line); padding: 7px 12px; border-radius: 8px; }
  .links a:hover { background: #182140; }
  footer { margin-top: 20px; color: var(--muted); font-size: .72rem; line-height: 1.6; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <svg class="helm" viewBox="0 0 100 100" fill="none" aria-hidden="true">
      <circle cx="50" cy="50" r="44" stroke="#4f8cff" stroke-width="7"/>
      <circle cx="50" cy="50" r="15" fill="#4f8cff"/>
      <g stroke="#4f8cff" stroke-width="7" stroke-linecap="round">
        <line x1="50" y1="6" x2="50" y2="35"/>
        <line x1="50" y1="65" x2="50" y2="94"/>
        <line x1="6" y1="50" x2="35" y2="50"/>
        <line x1="65" y1="50" x2="94" y2="50"/>
      </g>
    </svg>
    <div>
      <h1>K8s Self-Healing App</h1>
      <div class="sub">Kubernetes Application Deployment &amp; Self-Healing</div>
    </div>
    <div class="pill" id="pill"><span class="dot"></span><span id="pill-text">...</span></div>
  </header>

  <div class="grid">
    <div class="card"><div class="label">Status</div><div class="value" id="status">...</div></div>
    <div class="card"><div class="label">Version</div><div class="value" id="version">...</div></div>
    <div class="card"><div class="label">Served by pod</div><div class="value" id="hostname">...</div></div>
    <div class="card"><div class="label">Uptime</div><div class="value" id="uptime">...</div></div>
    <div class="card"><div class="label">Requests served</div><div class="value" id="requests">...</div></div>
    <div class="card"><div class="label">Process</div><div class="value" id="pid">...</div></div>
  </div>

  <div class="links">
    <a href="/health">GET /health</a>
    <a href="/stats">GET /stats</a>
    <a href="/toggle-health">GET /toggle-health</a>
  </div>

  <footer>
    This page polls <b>/stats</b> every 2 seconds. Uptime and the request counter
    reset when Kubernetes restarts the container &mdash; trigger it via
    <b>/toggle-health</b> and watch the liveness probe heal this pod. Reload the
    page to see the Service balance requests across replicas.
  </footer>
</div>
<script>
async function refresh() {
  try {
    const s = await (await fetch('/stats')).json();
    const bad = s.status !== 'healthy';
    const pill = document.getElementById('pill');
    pill.classList.toggle('bad', bad);
    document.getElementById('pill-text').textContent = bad ? 'UNHEALTHY' : 'HEALTHY';
    const st = document.getElementById('status');
    st.textContent = s.status.toUpperCase();
    st.className = 'value ' + (bad ? 'bad' : 'ok');
    document.getElementById('version').textContent = s.version;
    document.getElementById('hostname').textContent = s.hostname;
    document.getElementById('requests').textContent = s.requests_served;
    document.getElementById('pid').textContent = 'PID ' + s.pid;
    const m = Math.floor(s.uptime_seconds / 60), sec = s.uptime_seconds % 60;
    document.getElementById('uptime').textContent = m + 'm ' + sec + 's';
  } catch (e) {
    document.getElementById('pill').classList.add('bad');
    document.getElementById('pill-text').textContent = 'UNREACHABLE';
  }
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


def _count_request():
    try:
        with open(REQUESTS_LOG, "a") as f:
            f.write("1\n")
    except OSError:
        pass


def _requests_served():
    try:
        with open(REQUESTS_LOG) as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _is_healthy():
    return not os.path.exists(UNHEALTHY_MARKER)


@app.route("/")
def index():
    _count_request()
    return PAGE


@app.route("/stats")
def stats():
    return jsonify(
        {
            "status": "healthy" if _is_healthy() else "unhealthy",
            "version": APP_VERSION,
            "hostname": os.environ.get("HOSTNAME", socket.gethostname()),
            "uptime_seconds": int(time.time() - START_TIME),
            "requests_served": _requests_served(),
            "pid": os.getpid(),
        }
    )


@app.route("/health")
def health():
    if not _is_healthy():
        return jsonify({"status": "unhealthy", "version": APP_VERSION}), 503
    return jsonify({"status": "healthy", "version": APP_VERSION}), 200


@app.route("/toggle-health")
def toggle_health():
    if os.path.exists(UNHEALTHY_MARKER):
        os.remove(UNHEALTHY_MARKER)
        return jsonify({"status": "healthy", "hint": "marker removed"})
    with open(UNHEALTHY_MARKER, "w") as f:
        f.write("unhealthy")
    return jsonify(
        {
            "status": "unhealthy",
            "hint": "marker created; /health returns 503 until the container restarts",
        }
    ), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
