import os
import socket

from flask import Flask, jsonify

APP_VERSION = os.environ.get("APP_VERSION", "1.1.0")
UNHEALTHY_MARKER = "/tmp/unhealthy"

app = Flask(__name__)


@app.route("/")
def index():
    hostname = os.environ.get("HOSTNAME", socket.gethostname())
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>K8s Self-Healing App</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 640px; margin: 4rem auto;
           padding: 0 1rem; color: #222; }}
    .card {{ border: 1px solid #ddd; border-radius: 12px; padding: 1.5rem; }}
    .ok {{ color: #0a7d32; font-weight: 600; }}
    code {{ background: #f4f4f4; padding: 0.15rem 0.4rem; border-radius: 4px; }}
    table {{ border-collapse: collapse; margin-top: 1rem; }}
    td {{ padding: 0.35rem 1rem 0.35rem 0; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Kubernetes Application Deployment &amp; Self-Healing</h1>
    <p class="ok">Status: RUNNING</p>
    <table>
      <tr><td>Version</td><td><code>{APP_VERSION}</code></td></tr>
      <tr><td>Hostname</td><td><code>{hostname}</code></td></tr>
      <tr><td>Health endpoint</td><td><a href="/health">/health</a></td></tr>
    </table>
    <p style="margin-top:1.5rem; color:#666;">
      Reload this page a few times &mdash; the hostname changes when multiple
      replicas are serving traffic behind a Service.
    </p>
  </div>
</body>
</html>
"""
    return html


@app.route("/health")
def health():
    if os.path.exists(UNHEALTHY_MARKER):
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
