# Test Results — Self-Healing Demonstrations

All results below were **actually executed and captured** on a local kind
cluster (Kubernetes v1.37.0, kind v0.33.0, single control-plane node) on
2026-10-29. Nothing here is fabricated or simulated.

## Summary table

| # | Scenario | Result | Evidence |
|---|----------|--------|----------|
| 1 | Delete a Pod → Deployment creates replacement | ✅ VERIFIED | New pod created ~instantly, Ready after readiness probe |
| 2 | Kill app process (PID 1) → container restart | ✅ VERIFIED | Same pod, `RESTARTS 0→1`, exit 0, back Ready in ~15s |
| 3 | Break `/health` → probes detect & self-heal | ✅ VERIFIED | Readiness removal at t+30s, liveness kill+restart at t+50s, Ready at t+60s |
| 4 | Scale 3 → 5 → 3 | ✅ VERIFIED | 5/5 Ready on scale-up, clean return to 3 |
| 5 | Rolling update 1.0.0 → 1.1.0 | ✅ VERIFIED | **35/35 requests OK, 0 failures during rollout** |
| 6 | Faulty rollout → stuck, old pods serve → undo | ✅ VERIFIED | ImagePullBackOff; **25/25 requests OK while stuck**; undo restored 1.1.0 |

### Not performed (honest scope)

- OOMKill under memory-limit pressure (limits are set but not stress-tested)
- Node failure / cluster autoscaling (single-node kind cluster)
- Network partitions, DNS failures

---

## Scenario 1 — Pod deletion (Pod replacement)

```
=== BEFORE ===
k8s-self-healing-app-6dbbb77f79-7hpkg   1/1   Running   0
k8s-self-healing-app-6dbbb77f79-cmw9h   1/1   Running   0
k8s-self-healing-app-6dbbb77f79-mj7mp   1/1   Running   0

$ kubectl delete pod k8s-self-healing-app-6dbbb77f79-7hpkg

=== AFTER (5s) ===
k8s-self-healing-app-6dbbb77f79-cmw9h   1/1   Running   0
k8s-self-healing-app-6dbbb77f79-mj7mp   1/1   Running   0
k8s-self-healing-app-6dbbb77f79-rnm98   0/1   Running   0    <- NEW pod
```

The ReplicaSet `DESIRED 3 / CURRENT 3 / READY 2` shows the controller
immediately reconciling toward the desired state. The new pod shows `0/1`
for a few seconds because the readiness probe has `initialDelaySeconds: 5`.

**Diagnosis commands:** `kubectl get pods`, `kubectl get rs`,
`kubectl describe pod <name>`, `kubectl get events --sort-by=.lastTimestamp`

## Scenario 2 — Process crash (container restart, same Pod)

```
$ kubectl exec k8s-self-healing-app-6dbbb77f79-cmw9h -- sh -c "kill 1"

k8s-self-healing-app-6dbbb77f79-cmw9h   0/1   Running   1 (4s ago)
k8s-self-healing-app-6dbbb77f79-cmw9h   0/1   Running   1 (10s ago)
k8s-self-healing-app-6dbbb77f79-cmw9h   1/1   Running   1 (15s ago)

restartCount: 1; lastState: Completed (exit code 0)
Events: Container created -> Container started   (kubelet restarted it)
```

Note: `kill` is a shell builtin, so `sh -c "kill 1"` is required inside the
slim image. Gunicorn (PID 1) handled SIGTERM gracefully (exit 0).

**Key difference vs Scenario 1:** the Pod NAME stays the same and only
`RESTARTS` increments — the kubelet restarts the *container*; the Deployment
controller is not involved.

## Scenario 3 — Liveness/readiness failure (controlled break + auto-recovery)

v1.1.0 adds `GET /toggle-health`, which creates a marker file that makes
`/health` return 503 until the container restarts (a restart wipes `/tmp`).

```
$ kubectl exec <pod> -- python3 -c "...urlopen('http://localhost:5000/toggle-health')..."
{"hint":"marker created; /health returns 503 until the container restarts", ...}

$ /health inside the pod -> HTTP 503

Timeline (polled every 10s):
t+10s: READY 1/1, RESTARTS 0, endpoints 3/3
t+20s: READY 1/1, RESTARTS 0, endpoints 3/3
t+30s: READY 0/1, RESTARTS 0, endpoints 2/3   <- readiness failed (3 x 10s), pod pulled from Service
t+40s: READY 0/1, RESTARTS 0, endpoints 2/3
t+50s: READY 0/1, RESTARTS 1, endpoints 2/3   <- liveness failed (3 x 20s), container killed & restarted
t+60s: READY 1/1, RESTARTS 1, endpoints 3/3   <- healthy again, back in rotation

Events (kubectl get events):
Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 503
Warning  Unhealthy  Liveness probe failed: HTTP probe failed with statuscode: 503
Normal   Killing    Container flask failed liveness probe, will be restarted
Normal   Created    Container created
Normal   Started    Container started
```

The app required **zero manual repair**: the restart cleared the marker file
and `/health` returned 200 automatically.

## Scenario 4 — Scaling

```
$ kubectl scale deployment/k8s-self-healing-app --replicas=5
-> 5 pods, all 1/1 Running

$ kubectl scale deployment/k8s-self-healing-app --replicas=3
-> 3 pods, all 1/1 Running    (3 desired, 3 ready)
```

## Scenario 5 — Rolling update with zero downtime

A separate probe pod requested `/health` through the Service once per second
for the entire rollout:

```
$ kubectl set image deployment/k8s-self-healing-app flask=k8s-self-healing-app:1.1.0
$ kubectl rollout status deployment/k8s-self-healing-app
deployment "k8s-self-healing-app" successfully rolled out

Probe result:
REQUESTS OK: 35 / 35   FAILED: 0
VERSIONS SEEN: ['healthy1.0.0', 'healthy1.1.0']   <- old & new both served during rollout

ReplicaSets after: new 3/3/3, old 0/0/0 (kept for rollback)
```

`maxUnavailable: 0` + `maxSurge: 1` meant a new pod became Ready before each
old pod was terminated.

## Scenario 6 — Faulty rollout, stuck safely, then undo

```
$ kubectl set image deployment/k8s-self-healing-app flask=k8s-self-healing-app:2.0.0
   (tag does not exist on the node; imagePullPolicy: IfNotPresent)

new pod:   0/1  ErrImagePull -> ImagePullBackOff ("Back-off pulling image k8s-self-healing-app:2.0.0")
old pods:  3x  1/1  Running   <- never terminated, still serving

Probe result DURING the stuck rollout:
OK: 25 / 25   FAILED: 0      <- zero downtime even during a broken deploy

$ kubectl rollout undo deployment/k8s-self-healing-app
deployment.apps/k8s-self-healing-app rolled back
-> 3 pods 1/1 Running, service serving version 1.1.0
```

---

## Concept summary — what heals what

| Failure | Healed by | Granularity |
|---|---|---|
| Process crashes/exits | kubelet restarts the **container** (liveness/restartPolicy) | Same Pod, RESTARTS++ |
| Pod deleted / node lost | Deployment controller creates a **new Pod** | New Pod name |
| App returns errors but process alive | **Liveness probe** kills container -> restart | Same Pod, RESTARTS++ |
| App temporarily not ready (startup, dep down) | **Readiness probe** removes Pod from Service (no restart) | Endpoints only |

Kubernetes restarts *processes and pods* — it does **not** fix application
bugs, and it cannot recover from a failure where every replica is permanently
unhealthy (e.g. a bad image on the very first deploy, or a crash-on-boot bug,
which causes CrashLoopBackOff forever).
