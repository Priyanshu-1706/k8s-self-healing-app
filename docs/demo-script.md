# Demo script

The sequence I follow when showing this project live. Every command here was
run and verified (see test-results.md). Roughly 3-5 minutes end to end.

Tip: keep `watch -n1 kubectl get pods` running in a second terminal so people
can see pods come and go while you type.

## Before hitting record

```bash
cd k8s-self-healing-app
docker build -t k8s-self-healing-app:1.2.0 .
kind create cluster --name k8s-self-healing
kind load docker-image k8s-self-healing-app:1.2.0 --name k8s-self-healing
kubectl apply -f k8s/
kubectl rollout status deployment/k8s-self-healing-app
```

## 1. Baseline (10s)

```bash
kubectl get pods -o wide
kubectl get svc
```

Say: three replicas of a Flask app, liveness and readiness probes on /health,
CPU and memory limits, behind a ClusterIP Service.

To show the Service balancing across replicas:

```bash
kubectl exec deploy/k8s-self-healing-app -- python3 -c "
import urllib.request, re
for i in range(6):
    html = urllib.request.urlopen('http://k8s-self-healing-app/').read().decode()
    print(re.search(r'<code>(k8s-self-healing-app-\S+?)</code>', html).group(1))
"
```

(Note: this prints hostnames from the page source, so it still works on the
new dashboard version too.)

## 2. Delete a pod (~30s)

```bash
kubectl delete pod <POD_NAME>          # pick one from kubectl get pods
kubectl get pods
```

Say: the Deployment controller saw 2 pods when it wanted 3, and created a
replacement within seconds. The 0/1 means the readiness probe has not passed
yet, so it gets no traffic meanwhile.

## 3. Crash the process inside a container (~30s)

```bash
kubectl get pods                        # note the RESTARTS column
kubectl exec <POD_NAME> -- sh -c "kill 1"
kubectl get pods                        # same pod name, RESTARTS is now 1
```

Say: the pod name did not change. That is the kubelet restarting the
container, a different mechanism from pod replacement.

## 4. The app is alive but broken (~90s, best part)

Have the dashboard open in a browser via port-forward so viewers see it go
red and recover.

```bash
kubectl port-forward svc/k8s-self-healing-app 8080:80
```

Then break one pod:

```bash
kubectl exec <POD_NAME> -- python3 -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/toggle-health').read().decode())"
kubectl get endpoints k8s-self-healing-app     # pod disappears after ~30s
kubectl get pods                                # RESTARTS bumps after ~50-70s
kubectl describe pod <POD_NAME> | grep -A5 Events
```

Say: the process is running fine but /health returns 503. First readiness
fails and the pod stops getting traffic. Then liveness fails three times and
Kubernetes kills the container. The restart clears the marker file, so the
app comes back healthy without me touching it. Point at the events: Unhealthy,
Killing, Started.

## 5. Scaling (~20s)

```bash
kubectl scale deployment/k8s-self-healing-app --replicas=5
kubectl get pods
kubectl scale deployment/k8s-self-healing-app --replicas=3
kubectl get pods
```

## 6. Rolling update (~60s)

Second terminal: `watch -n1 kubectl get pods`.

```bash
kubectl set image deployment/k8s-self-healing-app flask=k8s-self-healing-app:1.2.0
kubectl rollout status deployment/k8s-self-healing-app
kubectl rollout history deployment/k8s-self-healing-app
```

Say: old pods are only terminated after new ones pass readiness, that is
maxUnavailable 0 with maxSurge 1. I measured zero failed requests across an
entire rollout.

## 7. Bad deploy and rollback (~60s)

```bash
kubectl set image deployment/k8s-self-healing-app flask=k8s-self-healing-app:2.0.0
kubectl get pods          # new pod stuck in ErrImagePull, old pods still Running
kubectl rollout undo deployment/k8s-self-healing-app
kubectl rollout status deployment/k8s-self-healing-app
kubectl get pods
```

Say: I deployed a tag that does not exist. The new pod is stuck, but since a
rollout only kills old pods after new ones are ready, the old version kept
serving every request. One command to roll back.

## 8. Closing (10s)

```bash
kubectl get pods
```

Say: pod replacement, container restarts, probe recovery, scaling, rolling
updates and rollback, all declarative.

## Cleanup (off camera)

```bash
kind delete cluster --name k8s-self-healing
```
