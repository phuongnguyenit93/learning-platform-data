# Designing Health Checks, Readiness, and Liveness by Platform

A service can still have a running process yet fail to handle requests. Conversely, a process can be healthy yet still be loading configuration, waiting to connect to required resources, or overloaded and unable to accept additional traffic. Checking only whether a VM or container is alive makes it hard to distinguish these states and can trigger the wrong recovery action.

Health checks are intentional probes that let a platform decide whether a workload has started, remains healthy, or can accept traffic. On Google Cloud, implementation differs across GKE, Cloud Run, and Compute Engine. Sound design starts from the meaning of each state, then selects the appropriate probe type, endpoint, thresholds, and platform action.

## 1. Distinguishing Startup, Liveness, and Readiness

Three common checks answer three different questions:

| Check Type | Question | What Does the Platform Typically Do on Failure? | Example |
| --- | --- | --- | --- |
| Startup | Has the application finished initializing and entered the serving phase? | Stops and restarts the container, or treats the VM as still initializing, depending on the platform. | Waiting for configuration load, cache warm-up, required migrations, and opening listeners. |
| Liveness | Can the process still make forward progress? | Restarts the container or triggers VM repair if autohealing is enabled. | Detecting deadlocks, frozen event loops, or stalled workers. |
| Readiness | Can the workload accept new requests right now? | Stops sending new traffic to the workload; the process typically keeps running. | Initializing, losing connection to a required dependency, draining, or intentionally shedding load. |

Startup probes are helpful for slow-starting applications. Only after startup succeeds does the platform start liveness and readiness checks according to its lifecycle rules. Liveness targets internal failures from which the process cannot self-recover. Readiness targets temporary conditions during which the workload should not receive new requests.

Do not reuse a single endpoint with identical logic for every check type. For instance, temporary database unavailability may mean the application is not ready for requests, not that the process is deadlocked and needs restarting. If liveness depends directly on external services, a shared dependency outage can trigger simultaneous restarts across many workloads, amplifying load and prolonging the outage.

## 2. Designing the Health Endpoint Contract

An HTTP application can expose three distinct endpoints:

| Example Endpoint | Success Condition | Failure Condition |
| --- | --- | --- |
| `GET /startupz` | Configuration loaded, core initialization finished, listener ready. | Initialization still running or failed unrecoverably. |
| `GET /livez` | Process remains responsive and able to make internal progress. | Unrecoverable state detected, such as a deadlock or stalled main loop. |
| `GET /readyz` | Application can accept new requests and required flow dependencies are working. | Application initializing, draining, in controlled overload, or missing an essential dependency. |

For HTTP probes, a simple convention is returning `200 OK` (or another platform-accepted success code) when healthy, and `503 Service Unavailable` when unready or unhealthy. Endpoints should respond quickly, stay lightweight, and avoid returning sensitive payloads. Do not redirect health endpoints through a login page or reverse proxy that alters status codes.

Each endpoint should check precisely what needs to be known:

- `/startupz` should not block on optional dependencies. If a database is strictly required to boot, startup can verify connectivity or pool initialization. If a dependency experiences a brief disruption, consider letting the app start and fail readiness rather than entering an infinite restart loop.
- `/livez` should check internal state. Avoid calling databases, external APIs, or other services on every liveness probe. If a dependency goes down, mass-restarting the application will not fix that dependency.
- `/readyz` can check essential dependencies, connection pools, read/write capability on required resources, queue limits, and draining state. Check only conditions that genuinely determine whether the app can accept more requests.

If the application serves multiple request types with different dependencies, clarify which flows readiness represents. A service might still serve read endpoints while the write path is temporarily degraded; marking the entire instance unready can eliminate still-healthy serving capacity.

Health endpoints do not replace SLI/SLO monitoring. A passing probe only proves its check condition passed; it does not prove latency, error rates, data correctness, or user experience are healthy.

## 3. Choosing Probe Mechanisms and Parameters

Kubernetes and GKE support four primary probe mechanisms:

| Mechanism | How It Works | When Appropriate |
| --- | --- | --- |
| HTTP GET | Sends GET to the container's address and port; response codes from `200` up to `400` count as success. | Application exposes clear health endpoints. |
| TCP socket | Attempts a TCP connection to the port; successful handshake counts as passing. | Need to verify the listener is open without checking app logic. |
| Exec | Runs a command inside the container; exit code `0` counts as success. | Simple local check that HTTP/gRPC cannot express. |
| gRPC | Calls the gRPC Health Checking Protocol; `SERVING` status counts as success. | Application implements the gRPC health service. |

TCP only proves the port is accepting connections. It does not confirm the application loaded configuration properly, can query the database, or can process business requests. Exec probes also incur process-spawning overhead; avoid running heavy commands or setting aggressive intervals on high-density Pod clusters.

Common Kubernetes probe parameters:

| Parameter | Meaning | How to Choose |
| --- | --- | --- |
| `initialDelaySeconds` | Wait time before the first check runs. | Use only when needed; startup probes usually express boot time more cleanly. |
| `periodSeconds` | Interval between checks. | Balance detection speed against probe overhead. |
| `timeoutSeconds` | Maximum wait per check attempt. | Must exceed normal response time while remaining small enough to catch hangs. |
| `failureThreshold` | Consecutive failures before declaring failure. | Raise if brief jitter occurs; do not raise so high that outages linger. |
| `successThreshold` | Consecutive successes required to recover after failure. | Must be `1` for Kubernetes liveness and startup; readiness can exceed `1`. |
| `terminationGracePeriodSeconds` | Time allowed for graceful container shutdown after stop signal. | Match draining time and in-flight work completion. |

With a startup probe, you can estimate the startup budget as `failureThreshold × periodSeconds`. For example, `30 × 10s` gives the application roughly 300 seconds to boot before the probe declares failure. Measure real startup duration under load and constrained resources, then set thresholds with a reasonable buffer.

Liveness should generally tolerate higher failure thresholds than readiness. A brief timeout can temporarily fail readiness so the workload stops receiving new traffic; liveness should only fail when the app genuinely cannot self-recover. Conversely, setting `failureThreshold` too high on readiness can keep routing traffic to a broken instance for too long.

## 4. Designing for GKE and Kubernetes

GKE uses Kubernetes probe mechanisms. Kubelet probes each container in a Pod and acts based on the probe type:

- Startup exceeds failure threshold: kubelet stops the container; the restart policy governs restarting.
- Liveness exceeds failure threshold: kubelet stops and restarts that container.
- Readiness fails: the container keeps running, but the Pod is marked `Ready=false`; the Service's EndpointSlice stops including that Pod as a normal traffic-serving endpoint.

When a container defines a `startupProbe`, kubelet holds off on running liveness and readiness probes for that container until startup succeeds. Afterward, liveness and readiness run periodically throughout the container's lifetime.

### 4.1. Example Deployment Configuration

The following example assumes the app listens for HTTP on port `8080` and exposes `/startupz`, `/livez`, and `/readyz` as described earlier:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:TAG
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /startupz
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 2
```

Apply and inspect status:

```bash
kubectl apply -f orders-api.yaml
kubectl rollout status deployment/orders-api -n production
kubectl get pods -n production
kubectl describe pod POD_NAME -n production
kubectl get endpointslice -n production
```

`kubectl describe pod` displays probe events, restart counts, and container status. EndpointSlice lets you confirm unready Pods were removed from the Service's endpoint set. Do not rely solely on `Running` status: a Pod can be `Running` yet `Ready=false`.

### 4.2. Separating Readiness and Liveness Behavior

Suppose the database becomes temporarily unreachable:

1. `/livez` still succeeds because the process, event loop, and internal handlers are alive.
2. `/readyz` returns `503` if the database is a mandatory dependency for incoming requests.
3. The Pod keeps running, while the Service stops routing new traffic to that Pod.
4. Once the database recovers and the app passes enough consecutive checks, the Pod returns to `Ready`.

If liveness also checked the database, every Pod could be restarted simultaneously. After restarting, they still could not reach the database, would keep failing, and would add connection churn while the dependency is trying to recover.

### 4.3. GKE LoadBalancer Health Checks Are a Separate Layer

LoadBalancer Service health checks operate outside the cluster and differ from Pod startup, readiness, and liveness probes. For a GKE LoadBalancer Service, health check packets may be answered by `kube-proxy` or `cilium-agent` on the node; they are not requests sent directly to the Pod. Which nodes count as healthy also depends on `externalTrafficPolicy` and backend type.

Therefore, if a Load Balancer reports unhealthy backends, inspect both layers: Pod readiness/EndpointSlice and the Load Balancer's health check. Check target ports, NodePorts or NEGs, firewall rules, and `externalTrafficPolicy`. A passing Load Balancer health check does not guarantee every Pod is healthy; likewise, a Ready Pod does not guarantee firewall rules for health checkers are configured properly.

## 5. Designing for Cloud Run

Cloud Run provides container health checks for services. According to current Google Cloud documentation, a service can configure:

- Startup probe to confirm the container has initialized and is ready to receive traffic.
- Liveness probe to detect containers that can no longer continue operating; once failures reach the threshold, Cloud Run terminates the container and starts a replacement instance.
- Readiness probe to temporarily pause sending new requests to an unready instance; the instance remains alive and can receive traffic again once the probe succeeds. Readiness probes are currently marked **Preview** in the documentation.

Cloud Run supports HTTP, TCP, and gRPC for these probes; there is no `exec` mechanism as in Kubernetes. HTTP health endpoints must use HTTP/1. For HTTP probes, `2xx` or `3xx` responses count as success. If using gRPC, the application must implement the gRPC Health Checking Protocol.

### 5.1. Illustrative YAML Configuration

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: orders-api
spec:
  template:
    spec:
      containers:
        - image: REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:TAG
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /startupz
              port: 8080
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 18
          livenessProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 2
```

This is an illustrative configuration; verify readiness probe Preview availability and your tooling version before using it in production. Configuration updates create a new revision. You can deploy YAML via `gcloud run services replace` after substituting placeholders with your actual project, region, image, and configuration.

### 5.2. Cloud Run Behavioral Considerations

The startup probe is a critical initialization gate. Once the startup probe succeeds, Cloud Run considers the container ready for traffic. Consequently, the startup endpoint must ensure the app can safely serve immediately at that moment; do not let startup pass before the app can handle its first request while expecting a subsequent readiness probe to block traffic.

Readiness probes begin after startup succeeds. If readiness fails beyond `failureThreshold`, Cloud Run stops sending new requests to that instance without terminating it. Once consecutive probes succeed per `successThreshold`, the instance can receive traffic again. One important caveat: if session affinity is enabled, Cloud Run may continue routing requests to the same instance even when its readiness probe fails.

Liveness is suited for detecting deadlocks or unrecoverable internal failures. When liveness fails enough times, Cloud Run stops the container; in-flight requests may fail with `503`, and autoscaling launches a new instance. Cloud Run also rate-limits restarts when a service restarts repeatedly to avoid runaway restart loops.

If your app starts slowly, increase the startup probe budget rather than loosening liveness so much that deadlocks go undetected too long. For environment variables or secrets loaded at boot, the startup endpoint should succeed only after required configuration is verified.

## 6. Designing for Compute Engine and Managed Instance Groups

Compute Engine VMs do not have Kubernetes-style container startup/readiness/liveness probes. Instead, Google Cloud provides health checks for two key operational purposes:

1. **Load balancing:** determines whether a backend is healthy enough to receive new connections or requests. Unhealthy backends are removed from the eligible traffic pool; VMs are not automatically restarted simply because a Load Balancer health check fails.
2. **MIG autohealing:** detects VMs with unhealthy applications so the Managed Instance Group can repair them, typically by recreating the VM. This is a stronger action and requires conservative thresholds.

Create separate health checks for Load Balancing and autohealing. Load Balancer health checks can detect failures quickly to shift traffic away. Autohealing health checks should be more conservative to avoid deleting and recreating healthy VMs over a single slow response or brief network blip.

### 6.1. Creating a Load Balancer Health Check

Example creating an HTTP health check for backends listening on port `8080`:

```bash
gcloud compute health-checks create http orders-lb-health \
  --port=8080 \
  --request-path=/readyz \
  --check-interval=5s \
  --timeout=3s \
  --healthy-threshold=2 \
  --unhealthy-threshold=3
```

The health checker sends requests to the configured endpoint. A backend is considered healthy only after consecutive passing probes; consecutive failures mark the backend unhealthy. The `timeout` parameter must be less than or equal to `check-interval`.

### 6.2. Configuring MIG Autohealing

Create a separate health check with a less frequent check interval, then attach it to the MIG:

```bash
gcloud compute health-checks create http orders-autoheal-health \
  --port=8080 \
  --request-path=/healthz \
  --check-interval=30s \
  --timeout=5s \
  --healthy-threshold=2 \
  --unhealthy-threshold=3

gcloud compute instance-groups managed update orders-mig \
  --health-check=orders-autoheal-health \
  --initial-delay=300 \
  --zone=ZONE
```

`--initial-delay` gives new VMs time to boot and run startup scripts. During this window, the MIG ignores health check failures because the application may not be ready yet. The maximum value is 3,600 seconds; the example `300` seconds should be tuned to measured startup times.

Autohealing health checks can cause the MIG to delete and recreate VMs. Before enabling autohealing, verify instance templates, startup scripts, stateful data handling, network settings, and replacement VM provisioning capacity. Avoid using an overly sensitive readiness endpoint for autohealing, because an external dependency outage could trigger widespread VM replacements even though the VMs themselves are healthy.

### 6.3. Firewalls and Probe Sources

Google Cloud health checkers must be able to reach your backends. If ingress firewall rules block probe sources or health check ports, backends will be marked unhealthy even while the application is running. Identify your exact Load Balancer and backend type before creating firewall rules: probe source ranges vary by Load Balancer type, IPv4/IPv6, and proxy architecture.

For many backends using Google Front Ends, common IPv4 ranges include `35.191.0.0/16` and `130.211.0.0/22`; do not apply these two ranges blindly to every Load Balancer type. Look up the official probe IP ranges table, permit only required protocols/ports, and scope rules with appropriate network tags or service accounts.

Illustrative firewall rule example for a backend type requiring those IPv4 ranges:

```bash
gcloud compute firewall-rules create allow-orders-health-checks \
  --network=VPC_NAME \
  --direction=INGRESS \
  --action=ALLOW \
  --source-ranges=35.191.0.0/16,130.211.0.0/22 \
  --target-tags=allow-health-checks \
  --rules=tcp:8080
```

Do not open an entire VPC or all ports just to make health checks pass. Check backend service ports, NEG ports, or NodePorts depending on the Load Balancer architecture.

## 7. Cross-Platform Behavior Comparison

| Platform | Startup | Readiness | Liveness / Recovery | Key Considerations |
| --- | --- | --- | --- | --- |
| GKE / Kubernetes | Kubelet `startupProbe`; failure stops container. | `readinessProbe` marks Pod unready and removes it from Service endpoints. | Failing `livenessProbe` stops and restarts container. | Supports HTTP, TCP, exec, gRPC; Pod probes differ from LoadBalancer health checks. |
| Cloud Run service | Startup probe; success marks container ready to receive traffic. | Readiness probe (Preview); pauses new traffic on failure. | Liveness probe stops container so Cloud Run creates another instance. | Supports HTTP, TCP, gRPC; HTTP probes use HTTP/1; session affinity affects readiness. |
| Compute Engine VM / MIG | Startup script and autohealing `initial-delay` create boot window. | Load Balancer health check determines whether backend receives traffic. | Autohealing health check can trigger MIG VM recreation. | Separate Load Balancer and autohealing checks; configure firewall rules for probes. |

Different platforms do not use identical states to express every goal. When designing cross-platform architectures, keep endpoint contracts and business semantics consistent, then map them to each platform's specific behavior.

## 8. Testing and Operating Health Checks

Never deploy probes based solely on confirming an endpoint returns `200` under normal conditions. Test state transitions as well:

1. **Slow startup:** intentionally delay configuration loading or cache warming. Startup must have sufficient budget; liveness must not restart the app before startup finishes.
2. **Dependency disconnection:** disconnect a required database or API in a test environment. Readiness must reflect serving capability; liveness must not cause mass restarts if the process is still making progress.
3. **Deadlock or stalled worker:** simulate a controlled internal hang. Liveness must detect it within the target timeframe and the platform must recover properly.
4. **Overload:** ramp up requests or queue depth. Readiness can temporarily pause new traffic under backpressure policies; probes themselves should not add significant load.
5. **Drain and rollout:** terminate a Pod or swap revisions. The app should stop accepting new requests, finish or cancel in-flight work within deadlines, and let the new workload become Ready before shifting load.
6. **Firewall or wrong port:** test health checkers from the actual network and backend. Verify probes are not blocked by VPC firewalls, NetworkPolicies, or listener settings.

In operations, monitor at least:

- Container restart counts, `CrashLoopBackOff`, startup duration, and Pod Ready ratios.
- Readiness/liveness failure counts, timeout causes, and recovery times.
- Load Balancer backend health status and MIG VM repair counts.
- Error rates, latency, saturation, queue depth, and business-flow SLOs.

A health-check alert should point operators toward the right layer: application, dependency, resources, probe config, IAM, network, or firewall. Alerting solely "unhealthy" without correlated metrics and logs slows down response and invites wrong actions.

## 9. Common Design Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Liveness calls a database or external API | A dependency outage restarts many containers simultaneously. | Keep liveness focused on process health; move strictly required dependencies to readiness. |
| Using a TCP port check as sole proof | Port is open before the app can actually process requests. | Use HTTP/gRPC endpoints reflecting real application state. |
| Missing startup probe for slow-booting apps | Liveness starts too early and restarts containers repeatedly. | Configure a startup probe with enough budget for initialization. |
| Readiness returns success during draining | New traffic keeps arriving at an instance preparing to stop. | Flip readiness before shutdown and coordinate termination grace periods. |
| Probes run heavy queries or poll too frequently | Increases CPU, connections, and load on dependencies. | Use cheap checks, cache state appropriately, and choose intentional intervals. |
| Sharing one health check for Load Balancer and MIG autohealing | Sensitive Load Balancer probes trigger premature VM recreations. | Create two separate checks with thresholds and intervals tuned to each action. |
| Forgetting firewall rules or using wrong ports | Backends are marked unhealthy even while the app works. | Verify probe IP ranges, protocols, ports, tags, and backend types. |
| Returning detailed errors or secrets from health endpoints | Leaks internal info and expands attack surface. | Return minimal status; keep details in controlled logs and metrics. |

## 10. Hands-On Exercise

An order-processing system has three components: an API on Cloud Run, a worker on GKE, and a group of VMs in a MIG running background tasks. The shared database occasionally experiences brief disruptions. During those windows, application processes remain alive but cannot process requests requiring the database.

Design health checks for this system:

1. Define success/failure criteria for `/startupz`, `/livez`, and `/readyz`.
2. Choose which dependencies belong in readiness checks and explain why all dependencies should not be placed in liveness.
3. Configure `startupProbe`, `livenessProbe`, and `readinessProbe` for the GKE worker. Set the startup budget from measured boot times.
4. Configure Cloud Run startup/liveness and evaluate the Preview readiness probe alongside session affinity effects.
5. Create separate Load Balancer and MIG autohealing health checks; set `initial-delay` to avoid repairing VMs while startup scripts are still running.
6. Simulate database outages, deadlocks, overload, and rollouts; record each platform's behavior, detection time, and recovery time.

Your output should include a mapping table from application states to each platform's actions, along with metrics confirming that health checks improve reliability without creating unintended restart or repair loops.

## References

- [Kubernetes: Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes: Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Cloud Run: Configure container health checks for services](https://docs.cloud.google.com/run/docs/configuring/healthchecks)
- [GKE: About LoadBalancer Services and health checks](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/service-load-balancer)
- [Cloud Load Balancing: Health checks overview](https://docs.cloud.google.com/load-balancing/docs/health-check-concepts)
- [Compute Engine: Set up an application-based health check and autohealing](https://docs.cloud.google.com/compute/docs/instance-groups/autohealing-instances-in-migs)
