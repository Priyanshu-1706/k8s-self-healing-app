# Kubernetes Application Deployment & Self-Healing

[![CI](https://github.com/Priyanshu-1706/k8s-self-healing-app/actions/workflows/ci.yml/badge.svg)](https://github.com/Priyanshu-1706/k8s-self-healing-app/actions/workflows/ci.yml)

A small Python Flask web application, containerized with Docker and deployed
on Kubernetes (kind) with multiple replicas, liveness/readiness probes,
resource limits, self-healing behavior, scaling, zero-downtime rolling
updates, and rollback.

**All self-healing claims in this repo were actually executed and captured** —
see [docs/test-results.md](docs/test-results.md). A step-by-step recording
script is in [docs/demo-script.md](docs/demo-script.md).

## Goals

- Run a Flask app in Kubernetes with **3 replicas**
- **Liveness + readiness probes** on `/health`
- Explicit **CPU/memory requests and limits**
- Demonstrate **self-healing**: pod replacement, container restarts, probe-driven recovery
- Demonstrate **scaling** (3 → 5 → 3) and **zero-downtime rolling updates + rollback**

## Architecture

```mermaid
flowchart LR
    U["kubectl port-forward<br/>(local access)"] --> SVC

    subgraph K["kind cluster"]
        SVC["Service (ClusterIP)<br/>port 80"] --> P1["Pod 1<br/>gunicorn :5000"]
        SVC --> P2["Pod 2<br/>gunicorn :5000"]
        SVC --> P3["Pod 3<br/>gunicorn :5000"]
        D["Deployment<br/>3 replicas · RollingUpdate<br/>maxUnavailable 0 · maxSurge 1"]
        D -. manages .-> P1
        D -. manages .-> P2
        D -. manages .-> P3
    end
```

Every pod runs the same container image: `python:3.12-slim` → gunicorn (2
workers) → Flask app, as a non-root user. The Deployment guarantees 3
replicas; the Service load-balances across pods that pass their readiness
probe.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | Live dashboard (dark mission-control UI) — polls `/stats` every 2s: status, version, pod hostname, uptime, request count. Ticks in real time |
| `GET /health` | `200 {"status":"healthy"}` when healthy — the probe target. `503` if unhealthy |
| `GET /stats` | JSON: status, version, hostname, uptime, requests served, PID |
| `GET /toggle-health` | Demo-only: flips `/health` between 200 and 503 (marker file; a container restart clears it). The dashboard turns red while unhealthy |

## Prerequisites

- Docker (Docker Desktop or Docker Engine)
- kind (`brew install kind` / see [kind docs](https://kind.sigs.k8s.io))
- kubectl
- Python 3.12+ (only for running without Docker)

## Quickstart

```bash
# 1. Build
docker build -t k8s-self-healing-app:1.2.0 .

# 2. Create a local cluster
kind create cluster --name k8s-self-healing

# 3. Load the image (kind cannot see your local Docker images otherwise)
kind load docker-image k8s-self-healing-app:1.2.0 --name k8s-self-healing

# 4. Deploy
kubectl apply -f k8s/
kubectl rollout status deployment/k8s-self-healing-app

# 5. Access
kubectl port-forward svc/k8s-self-healing-app 8080:80
curl http://localhost:8080/health
```

## Demonstrations

Full commands, captured output, and timelines: **[docs/test-results.md](docs/test-results.md)**

| Test | One-liner | What it proves |
|---|---|---|
| Pod replacement | `kubectl delete pod <pod>` | Deployment controller recreates pods |
| Container restart | `kubectl exec <pod> -- sh -c "kill 1"` | kubelet restarts the process, same pod |
| Probe self-healing | `kubectl exec <pod> -- python3 -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/toggle-health').read().decode())"` | Readiness pulls pod from Service (~30s), liveness kills+restarts it (~50s), app recovers alone |
| Scaling | `kubectl scale deployment/k8s-self-healing-app --replicas=5` | Declarative horizontal scaling |
| Rolling update | `kubectl set image deployment/k8s-self-healing-app flask=k8s-self-healing-app:<new>` | 35/35 requests OK during rollout (measured) |
| Rollback | `kubectl rollout undo deployment/k8s-self-healing-app` | Old pods never stop serving, even during a broken deploy |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Pod stuck `ErrImagePull` / `ImagePullBackOff` | Image not loaded into kind | `kind load docker-image <img> --name k8s-self-healing` |
| Pod stuck `Pending` | Unschedulable (requests too high for node) | `kubectl describe pod <pod>` → Events; lower `resources.requests` |
| Pod `CrashLoopBackOff` | App crashes on boot | `kubectl logs <pod>` and `kubectl logs <pod> --previous` |
| `0/1 Running` for a long time | Readiness probe failing | `kubectl describe pod <pod>` → probe errors at the bottom |
| `port-forward` closed unexpectedly | Normal: it tunnels to **one** pod; that pod was replaced | Re-run `kubectl port-forward` |
| `curl` hits same hostname every time | Expected with port-forward (single pod tunnel) | Use the in-cluster loop in demo-script.md to see balancing |

## Cleanup

```bash
kubectl delete -f k8s/                     # remove app + service
kind delete cluster --name k8s-self-healing # remove entire cluster
docker rmi k8s-self-healing-app:1.0.0 k8s-self-healing-app:1.1.0 k8s-self-healing-app:1.2.0
```

## Repository layout

```
├── app.py                  # Flask app: /, /health, /toggle-health
├── requirements.txt        # pinned: Flask 3.0.3, Werkzeug 3.0.3, gunicorn 22.0.0
├── Dockerfile              # python:3.12-slim, non-root user, gunicorn
├── .dockerignore
├── .github/workflows/ci.yml  # build + smoke test + manifest validation
├── k8s/
│   ├── deployment.yaml     # 3 replicas, probes, resources, RollingUpdate
│   └── service.yaml        # ClusterIP :80 -> :5000
└── docs/
    ├── test-results.md     # captured evidence for every claim
    └── demo-script.md      # step-by-step recording script
```

## Security notes

- Container runs as non-root (`appuser`, uid 1000)
- No credentials, tokens, or secrets in this repository
- Dependencies pinned to exact versions; CI builds the same image on every push

## Skills demonstrated

Docker (multi-concern production image, non-root) · Kubernetes Deployments,
Services, probes, resource management · Rolling updates & rollback ·
kubectl debugging (describe/logs/events) · kind · GitHub Actions CI ·
Flask/gunicorn · technical documentation with captured evidence
