# Test results

I ran all of these on my machine on 29 Oct 2026: kind v0.33.0, Kubernetes
v1.37.0, single control-plane node, macOS (arm64). The output below is pasted
from the terminal, trimmed where it repeated.

## Summary

| # | Test | Worked? | Result |
|---|------|---------|--------|
| 1 | Delete a pod | yes | Replacement pod created immediately, Ready after the readiness probe delay |
| 2 | Kill PID 1 in a container | yes | Same pod, RESTARTS 0 to 1, clean exit, Ready again in ~15s |
| 3 | Break /health with /toggle-health | yes | Readiness dropped the pod at ~30s, liveness restarted the container at ~50s, recovered on its own |
| 4 | Scale 3 to 5 to 3 | yes | 5/5 Ready on scale up, back to 3 cleanly |
| 5 | Rolling update 1.0.0 to 1.1.0 | yes | 35/35 requests OK during the rollout, 0 failures |
| 6 | Bad image tag, then undo | yes | New pod stuck in ImagePullBackOff, old pods kept serving (25/25 OK), undo worked |

Things I did not test: OOMKill under memory pressure (limits are set but I
never pushed the app that hard), node failure (single-node cluster), and
network/DNS failures. Not pretending those happened.

## Scenario 1: pod deletion

```
=== BEFORE ===
k8s-self-healing-app-6dbbb77f79-7hpkg   1/1   Running   0
k8s-self-healing-app-6dbbb77f79-cmw9h   1/1   Running   0
k8s-self-healing-app-6dbbb77f79-mj7mp   1/1   Running   0

$ kubectl delete pod k8s-self-healing-app-6dbbb77f79-7hpkg

=== AFTER (5s) ===
k8s-self-healing-app-6dbbb77f79-cmw9h   1/1   Running   0
k8s-self-healing-app-6dbbb77f79-mj7mp   1/1   Running   0
k8s-self-healing-app-6dbbb77f79-rnm98   0/1   Running   0    <- new pod
```

The ReplicaSet showed DESIRED 3 / CURRENT 3 / READY 2 right after the delete,
so the controller was already creating the replacement. The new pod sat at
0/1 for a few seconds because of `initialDelaySeconds: 5` on the readiness
probe.

Useful commands when this happens to you: `kubectl get pods`, `kubectl get rs`,
`kubectl describe pod <name>`, `kubectl get events --sort-by=.lastTimestamp`.

## Scenario 2: process crash

```
$ kubectl exec k8s-self-healing-app-6dbbb77f79-cmw9h -- sh -c "kill 1"

k8s-self-healing-app-6dbbb77f79-cmw9h   0/1   Running   1 (4s ago)
k8s-self-healing-app-6dbbb77f79-cmw9h   0/1   Running   1 (10s ago)
k8s-self-healing-app-6dbbb77f79-cmw9h   1/1   Running   1 (15s ago)

restartCount: 1, lastState: Completed (exit code 0)
Events: Container created -> Container started
```

Two things I learned here. First, `kill` is a shell builtin so it has to go
through `sh -c` in the slim image. Second, gunicorn is PID 1 and handles
SIGTERM gracefully, hence exit code 0.

The important difference from scenario 1: the pod name does not change. The
kubelet restarted the container inside the same pod, the Deployment controller
was not involved at all.

## Scenario 3: app alive but returning errors

v1.1.0 added `/toggle-health`, which drops a marker file in /tmp that makes
`/health` return 503 until the container restarts.

```
$ kubectl exec <pod> -- python3 -c "...urlopen('http://localhost:5000/toggle-health')..."
{"hint":"marker created; /health returns 503 until the container restarts", ...}

$ /health inside the pod -> HTTP 503

polled every 10s:
t+10s: READY 1/1, RESTARTS 0, endpoints 3/3
t+20s: READY 1/1, RESTARTS 0, endpoints 3/3
t+30s: READY 0/1, RESTARTS 0, endpoints 2/3   readiness failed (3 x 10s), pod out of the Service
t+40s: READY 0/1, RESTARTS 0, endpoints 2/3
t+50s: READY 0/1, RESTARTS 1, endpoints 2/3   liveness failed (3 x 20s), container killed and restarted
t+60s: READY 1/1, RESTARTS 1, endpoints 3/3   healthy again, back in rotation

events:
Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 503
Warning  Unhealthy  Liveness probe failed: HTTP probe failed with statuscode: 503
Normal   Killing    Container flask failed liveness probe, will be restarted
Normal   Created    Container created
Normal   Started    Container started
```

I did not touch the pod after breaking it. The restart wiped /tmp, the marker
file went away, and /health returned 200 on its own.

## Scenario 4: scaling

```
$ kubectl scale deployment/k8s-self-healing-app --replicas=5
-> 5 pods, all 1/1 Running

$ kubectl scale deployment/k8s-self-healing-app --replicas=3
-> 3 pods, all 1/1 Running
```

Nothing surprising, it just worked.

## Scenario 5: rolling update

Before starting the rollout I ran a separate pod that requested /health
through the Service once per second for the whole update:

```
$ kubectl set image deployment/k8s-self-healing-app flask=k8s-self-healing-app:1.1.0
$ kubectl rollout status deployment/k8s-self-healing-app
deployment "k8s-self-healing-app" successfully rolled out

probe result:
REQUESTS OK: 35 / 35   FAILED: 0
VERSIONS SEEN: ['healthy1.0.0', 'healthy1.1.0']
```

Both versions appear in the probe output, which means old and new pods were
serving at the same time. With maxUnavailable 0 and maxSurge 1, an old pod
only dies after a new one passes its readiness probe, so nothing dropped.

The old ReplicaSet gets scaled to 0 but kept around. That is what makes
`rollout undo` possible.

## Scenario 6: bad deploy and rollback

```
$ kubectl set image deployment/k8s-self-healing-app flask=k8s-self-healing-app:2.0.0
   (tag does not exist on the node, imagePullPolicy is IfNotPresent)

new pod:   0/1  ErrImagePull -> ImagePullBackOff
old pods:  3x  1/1  Running   (never terminated, still serving)

probe result while the rollout was stuck:
OK: 25 / 25   FAILED: 0

$ kubectl rollout undo deployment/k8s-self-healing-app
deployment.apps/k8s-self-healing-app rolled back
-> 3 pods 1/1 Running, service back on 1.1.0
```

This is the test I liked most. A completely broken deploy still caused zero
downtime, because the rollout never got far enough to kill the old pods.

## What heals what

| Failure | Who fixes it | What you see |
|---|---|---|
| Process crashes or exits | kubelet restarts the container | Same pod, RESTARTS goes up |
| Pod deleted or node dies | Deployment controller makes a new pod | New pod name |
| App returns errors but process is alive | Liveness probe kills the container, restart follows | Same pod, RESTARTS goes up |
| App temporarily not ready (slow start, dependency down) | Readiness probe drops the pod from the Service | Pod stays up, just gets no traffic |

Worth saying plainly: Kubernetes restarts processes and pods. It does not fix
bugs. If every replica crashes on boot, you get CrashLoopBackOff forever until
a human shows up.
