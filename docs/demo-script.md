# Demo Script — for recording the walkthrough video

A sequential, copy-paste script for recording a 3–5 minute demo. Every command
was verified to work (see `test-results.md`). Suggested narration beats are in
`>` blockquotes.

Tip: run `watch -n1 kubectl get pods` in a **second terminal window** so
viewers can see pods appear/die/restart live while you type in the first.

## 0. One-time setup (before hitting record)

```bash
cd k8s-self-healing-app
docker build -t k8s-self-healing-app:1.1.0 .
kind create cluster --name k8s-self-healing
kind load docker-image k8s-self-healing-app:1.1.0 --name k8s-self-healing
kubectl apply -f k8s/
kubectl rollout status deployment/k8s-self-healing-app
```

## 1. Baseline (10s)

```bash
kubectl get pods -o wide
kubectl get svc
```

> "Three replicas of a Flask app, each with liveness and readiness probes on
> /health, CPU and memory limits, behind a ClusterIP Service."

Optional — show load balancing across replicas:

```bash
kubectl exec deploy/k8s-self-healing-app -- python3 -c "
import urllib.request, re
for i in range(6):
    html = urllib.request.urlopen('http://k8s-self-healing-app/').read().decode()
    print(re.search(r'<code>(k8s-self-healing-app-\S+?)</code>', html).group(1))
"
```

## 2. Self-healing #1 — delete a Pod (~30s)

```bash
kubectl delete pod <POD_NAME>          # pick one from kubectl get pods
kubectl get pods
```

> "I just deleted a pod. The Deployment controller noticed the actual state
> (2) differs from the desired state (3) and created a replacement within
> seconds. The 0/1 means the readiness probe hasn't passed yet — traffic is
> never sent to a pod that isn't ready."

## 3. Self-healing #2 — crash the process inside a container (~30s)

```bash
kubectl get pods                        # note the RESTARTS column
kubectl exec <POD_NAME> -- sh -c "kill 1"
kubectl get pods                        # same pod name, RESTARTS = 1
```

> "The pod name is unchanged — this is the kubelet restarting the *container*
> because the process died. Different mechanism from pod replacement."

## 4. Self-healing #3 — the app is alive but broken (~90s, the best part)

```bash
kubectl exec <POD_NAME> -- python3 -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/toggle-health').read().decode())"
kubectl get endpoints k8s-self-healing-app     # pod removed after ~30s (readiness)
kubectl get pods                                # RESTARTS bumps after ~50-70s (liveness)
kubectl describe pod <POD_NAME> | grep -A5 Events
```

> "The process is running fine, but /health now returns 503. First the
> readiness probe fails — Kubernetes stops routing traffic to it. Then the
> liveness probe fails three times — Kubernetes kills and restarts the
> container. The restart wipes the marker file, so the app comes back healthy
> **on its own**. I never touched it."

Point at the events: `Unhealthy -> Killing -> Started`.

## 5. Scaling (~20s)

```bash
kubectl scale deployment/k8s-self-healing-app --replicas=5
kubectl get pods
kubectl scale deployment/k8s-self-healing-app --replicas=3
kubectl get pods
```

## 6. Zero-downtime rolling update (~60s)

Second terminal: `watch -n1 kubectl get pods`.

```bash
kubectl set image deployment/k8s-self-healing-app flask=k8s-self-healing-app:1.1.0
kubectl rollout status deployment/k8s-self-healing-app
kubectl rollout history deployment/k8s-self-healing-app
```

> "Old pods are only terminated after new ones pass their readiness probes —
> maxUnavailable zero, maxSurge one. We measured zero failed requests across
> an entire rollout."

## 7. Bad deploy + rollback (~60s)

```bash
kubectl set image deployment/k8s-self-healing-app flask=k8s-self-healing-app:2.0.0
kubectl get pods          # new pod stuck in ErrImagePull, old pods still Running
kubectl rollout undo deployment/k8s-self-healing-app
kubectl rollout status deployment/k8s-self-healing-app
kubectl get pods
```

> "I deployed a tag that doesn't exist. The new pod is stuck, but because a
> rollout only kills old pods after new ones are ready, my old version kept
> serving every request. One command rolls back."

## 8. Closing (10s)

```bash
kubectl get pods
```

> "Pod replacement, container restarts, probe-driven recovery, scaling,
> rolling updates and rollback — all declarative, all automatic."

## Cleanup (off camera)

```bash
kind delete cluster --name k8s-self-healing
```
