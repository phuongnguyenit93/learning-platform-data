# CPU Limits, RAM Limits, Health Checks, and Termination Signals

## Lesson Objectives

A Spring Boot application compiled into a **GraalVM Native Image** still runs within container resource limits and lifecycle constraints. A native executable may start fast, yet when a container is constrained by CPU or RAM, the application can still start slowly, suffer throttling, get OOM-killed, or fail to finish in-flight requests during container shutdown.

Stable operation requires coordinating three layers:

- **Container runtime/orchestrator:** CPU, RAM, and PID limits, termination grace period, and signal delivery.
- **Spring Boot:** health groups, graceful shutdown, and web server, executor, and connection pool lifecycles.
- **Native executable:** managed heap/runtime memory, threads, native libraries, and target platform constraints.

This lesson helps you:

- Set appropriate CPU/memory requests and limits for native containers.
- Distinguish heap from RSS and cgroup memory accounting.
- Design startup, readiness, and liveness health checks for their intended purposes.
- Configure graceful shutdown and handle SIGTERM/SIGKILL.
- Avoid issues caused by PID 1, shell entrypoints, and overly short termination timeouts.
- Test containers under resource limits and termination.

## 1. Containers Do Not Make Applications Immune to Resource Limits

### 1.1. Native Image Still Consumes CPU and Memory

A native executable does not need a JVM to run, yet it still has:

- A heap managed by the Native Image runtime.
- Objects, thread stacks, and runtime structures.
- Machine code, metadata, and libraries mapped into the process.
- Direct/native memory used by libraries.
- Network buffers, TLS, database drivers, caches, and in-flight payloads.

Therefore, **heap is not the entire memory footprint**. When a container is RAM-limited, the kernel tracks memory via cgroup/container accounting. Process RSS and container memory usage can exceed the active heap.

An application with free heap space can still hit the memory limit due to thread stacks, direct buffers, native libraries, or memory mappings.

### 1.2. CPU Limits Affect Both Startup and Runtime

When a container receives only a fraction of a CPU, all of the following are affected:

- Spring `ApplicationContext` initialization.
- Class loading, initialization, and bootstrap tasks.
- Database/cache connections and health checks.
- Request processing, serialization, and cryptography.
- GC and background tasks.

Native Image generally has a shorter cold start than the JVM for many workloads, yet a low CPU quota can still stretch readiness time. Measure under the exact CPU limits used in production.

### 1.3. Three Failure Types to Distinguish

| Symptom | Signs | Possible Cause |
|---|---|---|
| CPU throttling | Process stays alive but latency rises; CPU capped by quota | Low CPU limit or bursty workload |
| Memory pressure/OOM | Container is killed; exit code is often 137; Kubernetes reports `OOMKilled` | Total memory exceeds the cgroup limit |
| Probe failure | Orchestrator marks pod unhealthy, restarts it, or removes it from traffic | Wrong probe path/port, timeout too short, or app not ready yet |

Do not treat all three by blindly raising memory. Determine whether the container is CPU-throttled, OOM-killed, or misconfigured in its health probes.

## 2. Setting CPU Limits and Requests

### 2.1. Docker CPU Options

Docker supports CPU limits via options such as:

| Option | Meaning |
|---|---|
| `--cpus` | Caps CPU quota, e.g., `1.5` CPUs |
| `--cpu-shares` | Relative CPU weight under contention; not a standalone hard limit |
| `--cpuset-cpus` | Pins the process to specific CPU cores |

Example running a native container with roughly 1.5 CPUs:

```bash
docker run --rm \
  --name payment-native \
  --cpus="1.5" \
  -p 8080:8080 \
  payment-service:native
```

For performance benchmarks, record the actual CPU quota. `--cpu-shares` is not equivalent to `--cpus`: shares mainly determine relative priority when multiple containers contend for CPU.

### 2.2. Kubernetes Requests and Limits

In Kubernetes:

- `requests.cpu` is used by the scheduler to place pods on nodes and serves as the basis for certain CPU allocation mechanisms.
- `limits.cpu` sets the maximum CPU a container can use; when exceeding quota, the container may be throttled.
- `requests.memory` is the memory amount the scheduler uses to determine pod placement.
- `limits.memory` is the memory ceiling; when exceeded, the kernel may OOM-kill processes in the container.

Example:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "1500m"
    memory: "512Mi"
```

These values are illustrative only. Choose requests/limits from measurements under a representative workload, accounting for peak memory, startup bursts, concurrency, and thread counts.

### 2.3. A CPU Request Is Not Dedicated CPU

A pod requesting `500m` does not necessarily receive half a dedicated core. The scheduler uses requests for placement, and nodes may run many workloads concurrently. With a low CPU limit, an application can still be throttled even when the node has idle CPU depending on quota/cgroup mechanisms.

If startup probes fail when a node is busy or the CPU quota is very low, investigate CPU throttling before arbitrarily lengthening probe timeouts.

### 2.4. Measuring CPU Throttling

In Linux/cgroup environments, throttling counts and durations can be observed via cgroup CPU statistics or container runtime/Prometheus metrics. Exact metric names depend on cAdvisor/runtime/version, typically involving throttled periods and throttled seconds.

Correlate:

- Actual CPU usage.
- CPU limit/quota.
- Throttled time.
- Request latency and readiness duration.
- Node CPU contention.

If throttling spikes alongside p95 latency or readiness time, test raising the CPU limit in a controlled benchmark run to confirm the correlation.

## 3. Setting Memory Limits for Native Image

### 3.1. Do Not Equate Heap with the Memory Limit

The container memory limit must cover the entire process and any helper processes accounted to the cgroup. For a native executable, account for:

- Native Image managed heap.
- Thread stacks and maximum thread count.
- Direct buffers and native allocations.
- Shared libraries and memory-mapped files.
- TLS, database/cache clients, and serialization buffers.
- Runtime metadata and process overhead.

If the container limit is `512Mi`, do not allow the managed heap to consume all `512Mi`. Leave headroom for off-heap memory and traffic spikes.

### 3.2. Choosing a Heap Cap with Headroom

Native Image supports runtime options similar to `-Xms`/`-Xmx` to tune the managed heap; exact support and option names should be verified for your GraalVM version and built binary. Setting a max heap caps only the managed heap, not total RSS.

Guidelines:

1. Measure RSS/container memory at readiness, steady state, and peak.
2. Estimate memory outside the managed heap.
3. Set a heap cap sufficient for the workload while keeping headroom.
4. Run burst/soak tests under production memory limits.
5. Check GC pressure, allocation failures, and OOM behavior.

Do not use `JAVA_TOOL_OPTIONS` or `JAVA_OPTS` as though the native executable were a JVM. Those variables configure the Java launcher/JVM; native executables do not automatically read them. Pass runtime arguments in the way supported by your native binary and container entrypoint.

### 3.3. Recognizing OOM

When a container exceeds its memory limit, the kernel may send SIGKILL. The process gets no chance to run shutdown hooks or flush final logs.

Common signs:

- Docker container exits with code `137`.
- Kubernetes container state shows `reason: OOMKilled`.
- Kernel/cgroup memory events record an OOM event.
- Application logs stop abruptly with no graceful shutdown message.

Exit code 137 can also occur when a process receives SIGKILL for other reasons; check container state and kernel events before concluding OOM.

### 3.4. Reading Memory Metrics Consistently

| Metric | Question Answered |
|---|---|
| Managed heap used | How many live objects the application holds in heap |
| Managed heap committed/max | How much heap the runtime has allocated or allows |
| Process RSS | How many memory pages are resident for the process |
| Container memory/cgroup usage | How much memory the container consumes per kernel accounting |
| Peak container memory | Highest observed usage during the benchmark window |

When the goal is preventing OOM or increasing pod density, prioritize tracking container memory and peak usage. Heap metrics remain useful for spotting allocation/GC pressure, but they do not represent the full container.

## 4. Designing Health Checks for Their Intended Purpose

### 4.1. Distinguishing Startup, Readiness, and Liveness

The three probes answer three distinct questions:

| Probe | Question | On Failure |
|---|---|---|
| Startup | Has the application completed required initialization? | Orchestrator keeps waiting within the startup probe window; if exhausted, container restarts |
| Readiness | Can this instance accept new traffic? | Instance is removed from Service/endpoints while the process keeps running |
| Liveness | Is the process alive and able to continue serving? | Orchestrator restarts the container |

Do not point all three probes at a single endpoint with identical semantics. Startup protects applications with longer startup; readiness gates incoming traffic; liveness detects hung or unrecoverable processes.

### 4.2. Enabling Spring Boot Actuator Health Groups

Add Spring Boot Actuator and configure:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.show-details=never
management.endpoints.web.exposure.include=health
```

When probe support is enabled, Spring Boot exposes health groups:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Liveness state and readiness state reflect application lifecycle phases. Readiness transitions to ready once the application reaches the appropriate phase; when the context closes or readiness is marked `REFUSING_TRAFFIC`, the endpoint reports unready.

Expose only the Actuator endpoints you need. Do not expose all management endpoints to public networks solely for Kubernetes health checks.

### 4.3. Liveness Should Not Depend on External Services

Do not include databases, Redis, or message brokers in the liveness group by default. If a database suffers a brief outage, failing liveness across all pods can trigger mass restarts in Kubernetes, adding load to the struggling dependency.

Liveness should focus on internal state indicating whether the process can keep operating. If a dependency prevents an instance from handling requests, consider using readiness to pause incoming traffic temporarily.

Readiness should also be designed selectively. Including every optional dependency in readiness means an outage in an auxiliary service can take the entire service out of rotation even while core functionality works.

### 4.4. Health Endpoints Should Run on the Application Port

Prefer checking health endpoints on the same server port that serves real traffic. If Actuator runs on a separate management port, the management server can report healthy even when the main web server cannot accept requests.

If a separate management port is mandatory, add appropriate checks on the application port and test failure scenarios where the main web server fails.

### 4.5. Custom Health Indicators

When checking a critical dependency, you can write a `HealthIndicator` and explicitly include it in the readiness group:

```java
@Component
class PaymentProviderHealthIndicator implements HealthIndicator {

    private final PaymentProviderClient client;

    PaymentProviderHealthIndicator(PaymentProviderClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        if (client.isAvailable()) {
            return Health.up().build();
        }
        return Health.down()
                .withDetail("provider", "unavailable")
                .build();
    }
}
```

Use only fast, bounded-timeout checks that do not overload dependencies. Avoid heavy queries or calling multiple external APIs every few seconds. Explicitly configure the readiness group if you want this indicator to affect readiness only.

Example adding the `paymentProviderHealthIndicator` bean to the readiness group:

```properties
management.endpoint.health.group.readiness.include=readinessState,paymentProvider
```

`paymentProvider` is the contributor ID derived from the `paymentProviderHealthIndicator` bean name following health indicator naming conventions. Verify the actual ID via the health endpoint in a test environment before applying.

## 5. Configuring Kubernetes Probes

### 5.1. Startup Probe

A startup probe gives the application enough time to finish bootstrapping before liveness/readiness take effect. Example:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 24
```

In this example, Kubernetes allows roughly up to 120 seconds for startup before the startup probe fails (24 attempts spaced 5 seconds apart; actual duration depends on probe timing and timeouts). Tune based on observed startup distributions under production CPU limits.

Once the startup probe succeeds, Kubernetes stops running it and begins evaluating liveness/readiness probes.

### 5.2. Readiness and Liveness

Continuing in the same container spec:

```yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
```

These values are starting points only. Timeout must exceed normal expected response time; failure thresholds must balance prompt failure detection against avoiding restarts from brief slowdowns.

### 5.3. Illustrative Deployment Manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: payment-service
          image: registry.example.com/payment-service:native
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "256Mi"
            limits:
              cpu: "1500m"
              memory: "512Mi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
```

Adjust image, ports, and resources for your actual service. This manifest illustrates structure; add security context, service account, environment/secrets, and deployment policies for your environment.

### 5.4. Understanding Probe Failure Behavior

- Startup probe exceeds failure threshold: container restarts because startup did not finish within the configured window.
- Readiness probe fails: pod stops receiving new traffic through the Service, but the process is not restarted due to readiness alone.
- Liveness probe fails: kubelet restarts the container once the failure threshold is reached.

Timed-out HTTP probes also consume resources. Health endpoints must never wait on unbounded database queries or long locks.

## 6. Health Checks with Docker

### 6.1. HEALTHCHECK Reports Container Status

A Dockerfile can declare `HEALTHCHECK` so Docker marks the container healthy/unhealthy. For example, if the image includes `curl`:

```dockerfile
HEALTHCHECK --interval=10s --timeout=2s --start-period=30s --retries=3 \
  CMD curl --fail --silent http://127.0.0.1:8080/actuator/health/readiness || exit 1
```

Minimal/distroless images usually lack a shell, `curl`, or `wget`. Do not copy heavy toolkits into a production image solely for health checks when the orchestrator already performs HTTP probes from outside the container.

Docker marks unhealthy status, though `HEALTHCHECK` alone does not guarantee Docker restarts the container. Restart behavior depends on restart policies or the orchestrator.

### 6.2. Choosing the Right Endpoint

For traffic-serving services, readiness is typically suited for load-balancer health checks. Liveness detects processes no longer making progress. Do not use endpoints that only check PID or open ports, as they can report healthy even when the application cannot process requests.

### 6.3. Avoid Turning Health Checks into Heavy Background Load

Health checks run repeatedly. Keep endpoints lightweight, timeout-bounded, and free of continuous calls to multiple downstream services. If deep dependency checks are required, consider a separate frequency and scope instead of placing everything into liveness.

## 7. Termination Signals and Graceful Shutdown

### 7.1. Containers Normally Receive SIGTERM First

When stopping a container:

- Docker sends SIGTERM to the main process, waits for the stop timeout, and sends SIGKILL if the process has not exited.
- Kubernetes starts the termination grace period. If a `preStop` hook exists, kubelet runs it first; then it sends SIGTERM to container processes. If the grace period expires before exit, the container receives SIGKILL.

SIGTERM gives the application a chance to stop accepting new work, complete in-flight requests, close connections, and flush necessary data. SIGKILL cannot be caught or handled by shutdown hooks.

### 7.2. Configuring Spring Boot Graceful Shutdown

Configure explicitly in `application.properties`:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

When the `ApplicationContext` closes, graceful web server shutdown stops accepting new requests and allows in-flight requests to finish within the allowed time. Spring also closes beans in lifecycle order, including executors and container-managed resources.

`spring.lifecycle.timeout-per-shutdown-phase` applies per lifecycle phase. If an application has multiple `SmartLifecycle` phases or long shutdown tasks, total context shutdown time can exceed a single phase's value. Sum the total time needed and leave headroom for the orchestrator.

### 7.3. Coordinating Spring and Kubernetes Timeouts

Example:

```yaml
spec:
  terminationGracePeriodSeconds: 45
```

With a 20-second Spring lifecycle timeout, a 45-second grace period is an example. Account for:

1. `preStop` hook duration, if any.
2. Time to stop receiving traffic and drain in-flight requests.
3. Time to complete lifecycle phases and close executors/clients.
4. Buffer before kubelet sends SIGKILL.

The grace period must exceed the total time required, not just a single phase's timeout. If shutdown repeatedly exceeds the budget, hunt down hung tasks or downstream calls without timeouts rather than raising the grace period indefinitely.

### 7.4. Ensuring the Native Executable Receives Signals

Prefer Docker exec form:

```dockerfile
ENTRYPOINT ["/app/payment-service"]
```

Exec form runs the native binary directly as the main process. Avoid shell wrappers that do not forward signals:

```dockerfile
# Avoid this form if the shell does not forward signals
ENTRYPOINT sh -c "/app/payment-service"
```

If an entrypoint script is mandatory, use `exec` to replace the shell process with the native binary:

```sh
#!/bin/sh
set -eu

# Perform minor setup if needed
exec /app/payment-service "$@"
```

When an application spawns subprocesses, consider a lightweight init process such as `tini` or Docker's init option to forward signals and reap child processes. Do not add an init process if the application has no subprocesses to manage.

### 7.5. Do Not Rely on Shutdown Hooks for Data Durability

Graceful shutdown only offers a finite window to finish work. A process can still be OOM-killed, lose power on a node, suffer a container runtime crash, or exceed the grace period.

For messages, payments, or orders that must not be lost:

- Persist state or outbox records within a durable transaction.
- Use a message broker/queue with acknowledgments.
- Design idempotent consumers to safely reprocess on retry.
- Acknowledge only after side effects are durably persisted.
- Enforce timeouts on downstream requests and close connections cleanly.

Never hold critical work solely in memory and assume a shutdown hook will always run.

## 8. Handling preStop and Traffic Draining

### 8.1. When Is preStop Needed?

Kubernetes updates Endpoints/Services so terminating pods stop receiving new traffic, yet external load balancers or service meshes may take extra time to propagate deregistration.

Use `preStop` only when a concrete deregister/drain step is needed. Hooks execute within the same termination grace period; time spent in the hook reduces the time remaining for application graceful shutdown.

Do not add long `sleep` commands “just to be safe” without measuring endpoint propagation lag. Measure actual draining and set a justified buffer.

### 8.2. Readiness When Shutdown Begins

When the Spring context begins closing, readiness state transitions to refusing traffic. This causes the health endpoint to report unready during shutdown.

Do not assume the readiness probe is the sole draining mechanism. The orchestrator, Service, ingress, and load balancers have their own propagation timings; test end-to-end to confirm new requests stop reaching terminating pods.

### 8.3. In-Flight Requests

Align request timeouts with the shutdown budget. If requests can run longer than the termination grace period:

- Enforce request timeouts or processing caps.
- Offload long tasks to durable jobs/messages.
- Return an accepted status and process via durable workers.
- Account for drain duration in deployment configuration.

Graceful shutdown is not an infinite wait for arbitrarily long requests.

## 9. Dockerfile for a Native Executable

### 9.1. Minimal Runtime Image

A simple Dockerfile for an already built binary:

```dockerfile
FROM <compatible-runtime-base>

WORKDIR /app
COPY --chown=10001:10001 payment-service /app/payment-service

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["/app/payment-service"]
```

`<compatible-runtime-base>` is a placeholder. Choose a base image compatible with how the native binary is linked—such as glibc vs. musl and required shared libraries. A binary built on one OS/ABI does not automatically run on every other image.

Run as non-root when special privileges are unnecessary. Ensure the working directory, temp directory, and required mounts have proper permissions.

### 9.2. Do Not Use Shell Form as the Main Process

Exec form lets the native binary receive SIGTERM directly and preserve clear exit codes. If using a shell script, end the script with `exec` as shown earlier.

### 9.3. Read-Only Filesystem and Writable Paths

When enabling a read-only root filesystem, identify whether the application must write to:

- `/tmp` or temporary directories.
- Log files if not writing to stdout/stderr.
- Uploaded or exported files.
- Local caches or runtime files.
- Mounted certificates/trust stores.

Prefer logging to stdout/stderr and mount separate volumes for required writable paths. Never store persistent data in a container's writable layer.

### 9.4. Verifying the Binary and Shared Libraries

Before deploying, confirm:

- Image OS and CPU architecture match the binary.
- glibc/musl and shared library dependencies are compatible.
- CA certificates are present if making HTTPS calls.
- DNS, timezone, and locale data meet requirements.
- The non-root user can read the binary and required files.
- The listening port requires no privileged capability.

A native executable does not bundle every OS library on its own. An overly minimal base image can prevent the binary from loading even when compilation succeeded.

## 10. Testing Resource Limits and Lifecycle

### 10.1. Testing CPU and Memory with Docker

Example:

```bash
docker run --rm \
  --name payment-native-limited \
  --cpus="1.0" \
  --memory="512m" \
  --pids-limit=256 \
  --stop-timeout=45 \
  -p 8080:8080 \
  payment-service:native
```

Run a representative workload while the container is constrained. Monitor:

- Readiness time and first-request latency.
- CPU throttling and CPU usage.
- Container memory, peak RSS, and OOM events.
- Thread count, PID usage, and executor queues.
- Error rate, p95/p99 latency, and throughput.

These values are illustrative. If the container hits its memory limit, do not bump the heap cap before identifying which memory region grew.

### 10.2. Testing Graceful Stop

While sending continuous requests:

```bash
docker stop --time 45 payment-native-limited
```

Confirm:

1. The process receives SIGTERM and starts shutting down.
2. Readiness switches to unready.
3. New requests stop arriving at the stopping instance.
4. In-flight requests complete within budget.
5. Executors, connection pools, and clients close cleanly.
6. The container exits before the timeout without receiving SIGKILL.

### 10.3. Testing in Kubernetes

Delete a pod while traffic is flowing:

```bash
kubectl delete pod <pod-name> --grace-period=45
```

Observe:

- Pod transitions to `Terminating`.
- Its endpoint is removed from new traffic selection.
- Logs show graceful shutdown starting and completing.
- Container exits before the grace period expires.
- Remaining replicas continue serving without overload.

Then test a scenario with requests lasting close to the shutdown budget to verify timeouts and drain behavior.

### 10.4. Controlled OOM Testing

In a test environment, generate load or configure a low memory limit to confirm monitoring detects OOMs. Never run destructive tests in production.

Verify:

- Container state and exit reason.
- Cgroup/kernel OOM events.
- Alerts fire.
- Orchestrator restarts per policy.
- Application restarts and readiness recovers.

Do not expect graceful shutdown logs when SIGKILL occurs due to OOM.

## 11. Complete Operational Configuration

### 11.1. Application Properties

Illustrative configuration:

```properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

management.endpoint.health.probes.enabled=true
management.endpoint.health.show-details=never
management.endpoints.web.exposure.include=health
```

Timeouts must align with request durations and the termination grace period. With multiple lifecycle phases, sum the total time needed rather than treating one phase's timeout as the whole shutdown budget.

### 11.2. Security Context for Kubernetes

If the binary and application do not require root privileges, run the container as an unprivileged user:

```yaml
containers:
  - name: payment-service
    securityContext:
      runAsNonRoot: true
      runAsUser: 10001
      runAsGroup: 10001
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop:
          - ALL
```

When enabling a read-only root filesystem, mount writable volumes for paths that genuinely need writes, such as `/tmp`. Verify the application never attempts to write logs, uploads, or caches to the root filesystem.

### 11.3. Docker Stop Timeout

Docker accepts a stop timeout when launching a container:

```bash
docker run -d --rm \
  --name payment-native \
  --stop-timeout=45 \
  --cpus="1.5" \
  --memory="512m" \
  -p 8080:8080 \
  payment-service:native
```

This timeout is how long Docker waits after SIGTERM before sending SIGKILL. It must align with Spring shutdown duration and request drain time.

### 11.4. Runtime Environment Variables

CPU/memory limits and probe settings belong to deployment configuration. Application values such as server port, database URL, cache endpoint, and timeouts can be passed via environment variables or secret/config management.

Never put credentials into a Dockerfile, build arguments stored in image history, or the native binary. Supply secrets at deployment time and control access.

## 12. Diagnosing Common Errors

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Startup probe repeatedly fails | Low CPU limit, short timeout, wrong endpoint, or slow dependency startup | Startup logs, CPU throttling, probe path/port, and readiness time |
| Readiness fails while liveness passes | App not ready yet or required dependency unavailable | Readiness group and dependency status |
| Liveness fails leading to restart loop | Hung process, unresponsive health endpoint, or liveness checks too many dependencies | Keep liveness lightweight; check thread dumps/metrics and pre-restart logs |
| Container exits with 137 | SIGKILL due to OOM or expired stop timeout | `OOMKilled`/cgroup events and termination events |
| Container OOMs despite free heap | Thread stacks, direct/native memory, mmap, or other memory grew RSS | Measure container memory/RSS, thread count, and native allocations |
| Native binary fails in minimal image | Wrong ABI, missing shared library, CA cert, or file permissions | Target OS/CPU, glibc/musl, libraries, and user permissions |
| No shutdown completion log | Process hit SIGKILL or signal did not reach binary | PID 1, exec-form entrypoint, stop timeout, and grace period |
| Requests dropped during rollout | Short grace period, incomplete drain, or overly long request timeout | Measure request duration, endpoint removal, and shutdown phases |
| Async tasks lost on restart | Tasks held only in an in-memory executor | Use durable queues/outbox and idempotent retries |

## 13. Deployment and Verification Workflow

### Step 1 — Measure Baseline Under Realistic Limits

Run the native executable with expected CPU/memory limits. Measure readiness, RSS/container memory, CPU throttling, throughput, p95/p99 latency, and peak memory.

### Step 2 — Configure Probes

Enable Actuator health groups. Select startup/readiness/liveness paths, test endpoints on the main server port, and confirm liveness does not depend on unnecessary external dependencies.

### Step 3 — Configure Graceful Shutdown

Set `server.shutdown=graceful`, lifecycle phase timeouts, and termination grace period. Use an exec-form entrypoint so the native binary receives SIGTERM.

### Step 4 — Test Rollout

Send continuous requests while deleting a pod or running `docker stop`. Confirm new traffic drains, in-flight requests finish within budget, and the process exits before SIGKILL.

### Step 5 — Test Limits

Run burst/soak tests under CPU quotas and memory limits. Monitor throttling, peak RSS, OOM events, thread/PID usage, and executor queues.

### Step 6 — Put into Operations

Configure alerts for `OOMKilled`, restart counts, probe failures, CPU throttling, memory saturation, and shutdown timeouts. Record limits/probes/grace period settings alongside the image version for traceability.

## 14. Hands-On Exercises

### Exercise 1 — CPU and Memory

Run the same native image under two different CPU quotas and two memory limits. Record readiness time, throughput, p95 latency, CPU throttling, and peak container memory. Explain why heap usage does not represent total RSS.

### Exercise 2 — Health Probes

Enable Actuator liveness/readiness groups. Simulate a required dependency temporarily becoming unavailable and observe readiness. Then simulate an unresponsive process to observe liveness. Confirm the two states lead to distinct orchestrator actions.

### Exercise 3 — Graceful Shutdown

Send requests with a known processing duration, then stop the container with SIGTERM. Try different termination timeouts. Record completed requests, dropped requests, shutdown duration, and exit status.

### Exercise 4 — PID 1 and Entrypoint

Compare an exec-form entrypoint with a shell wrapper that omits `exec`. Observe signal delivery and process exit duration. Switch the wrapper to `exec` and repeat.

### Self-Check Questions

1. Why can a native executable still be OOM-killed even when the managed heap has not reached max?
2. How does a CPU request differ from a CPU limit in Kubernetes?
3. Why shouldn't liveness depend directly on a database or Redis?
4. When is a startup probe better than raising the liveness failure threshold?
5. Does a readiness failure automatically restart the container?
6. How do Docker and Kubernetes handle SIGTERM/SIGKILL?
7. Why must the termination grace period account for both preStop hooks and lifecycle shutdown?
8. Why does a Docker exec-form `ENTRYPOINT` make graceful shutdown more reliable?
9. Why cannot shutdown hooks guarantee that messages or payments are never lost?

**Key Takeaway:** CPU limits affect startup and latency; memory limits apply to the entire process/container rather than heap alone. Startup, readiness, and liveness serve distinct purposes. When stopping, let the native binary receive SIGTERM directly, give Spring enough time to drain requests and close resources, and use queues/outboxes for work requiring durability. Test under real limits, probes, and termination timeouts before promoting an image to production.
