# Startup timeouts, readiness, and platform self-restart mechanisms

## 1. Why fast native startup still needs timeout and probe configuration

GraalVM Native Image often shortens Spring Boot startup time compared to the JVM in many applications. However, the time from container creation until the service actually receives traffic also includes scheduling, image pull, process startup, Spring ApplicationContext initialization, dependency connections, and readiness checks.

A native process may start very quickly yet still not be ready to serve because the database is unreachable, migrations have not finished, caches are not warm, or listeners have not registered. Conversely, an overly sensitive liveness probe can restart a process that is legitimately starting up or temporarily under heavy load. Repeated restarts discard initialization progress, increase load on dependencies, and prevent the service from ever reaching a healthy state.

In the **SPRING_BOOT_NATIVE_IMAGE** module, timeouts and probes must be configured based on the measured behavior of both the application and the deployment platform. This lesson distinguishes process startup, readiness, and liveness; explains Kubernetes startup/readiness/liveness probes; covers restarts/backoff, graceful shutdown, and how to test slow or failure scenarios.

## 2. Distinguishing three states: started, ready, and live

Three concepts answer three different questions:

| State | Question | Example |
|---|---|---|
| Started | Have the process and application completed the required startup phase? | Native executable is running, Spring context refresh is complete |
| Ready | Can the instance accept and process current traffic? | HTTP server accepts requests, required dependencies are ready |
| Live | Is the process still alive and capable of making progress? | Event loop/main threads are not deadlocked, application is not in an unrecoverable state |

A service can be started yet not ready. For example, the context has finished creating, but the database connection pool has not connected yet. A service can be ready while a specific request still fails due to a business error or an optional dependency.

Liveness should not check every external dependency. If a database temporarily drops and liveness fails, the platform could restart all replicas simultaneously even though restarting cannot fix the database. Readiness is usually the right place to stop sending traffic to instances that cannot serve.

## 3. Startup time differs from time-to-ready

Measuring startup as the time from process launch to the "Started …" log misses subsequent steps. For an orchestrator, the critical moment is usually when the readiness probe succeeds and the instance is added to service endpoints.

This can be modeled as:

[
T_{ready}=T_{schedule}+T_{imagePull}+T_{process}+T_{context}+T_{dependency}+T_{probe}
]

Not every platform measures each component identically. The formula helps identify where latency comes from. Native Image can reduce (T_{process}) and part of (T_{context}), but does not automatically reduce image pull, database migrations, or dependency wait times.

When measuring, record:
- Container creation and image pull duration.
- Process start timestamp.
- Spring application startup completion.
- Dependency initialization completion.
- Timestamp when readiness transitions to true.
- Timestamp when the platform begins routing traffic.

Use the same definition across JVM and native for a fair comparison.

## 4. Timeouts need specific meanings

The phrase "startup timeout" can refer to several different limits:

- **Container start timeout:** how long the platform waits for the process/container to start.
- **Startup probe window:** the maximum time allowed for the application to start before being considered failed.
- **Readiness probe timeout:** the time allowed for a single readiness check execution.
- **Liveness probe timeout:** the time allowed for a single liveness check.
- **Application startup timeout:** a limit enforced by a script, deployment tool, or supervisor.
- **Request timeout:** the time limit for handling a request, not a startup timeout.
- **Termination grace period:** how long the process has to shut down before being killed.

Do not use a single timeout value for everything. Each limit should reflect the failure mode and desired platform behavior.

## 5. Spring Boot Actuator provides health indicators

Spring Boot Actuator can expose health endpoints and Kubernetes-oriented health groups when properly configured. For example:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
```

In a Kubernetes environment, Spring Boot can expose health groups such as:
- `/actuator/health/liveness`
- `/actuator/health/readiness`

You must add the Actuator dependency and verify the actual endpoint path/port. Do not assume an endpoint exists just because YAML was added. If the management server runs on a separate port, probes must point to that port.

Custom health indicators must execute quickly, enforce timeouts, and avoid side effects. Avoid running heavy queries, migrations, or multiple downstream calls on every probe.

## 6. Liveness probe: detect only unrecoverable states

Liveness answers whether the process can still operate or needs to be restarted. Situations where failing liveness may be appropriate:

- Critical application threads are severely deadlocked and cannot recover.
- An essential internal subsystem is permanently stuck.
- The process entered a failure state where restarting is the designed recovery mechanism.
- An internal watchdog detects that the process is making no progress.

Do not fail liveness solely because:
- The database is temporarily unavailable.
- A payment provider is slow.
- A single request failed.
- A queue has a backlog while the process is still working.
- CPU spikes temporarily while handling a burst.

Restarting cannot fix a dependency outage and can cause a restart storm. If a service cannot serve due to a required dependency, readiness should usually fail to stop receiving traffic while keeping the process alive so it can recover.

## 7. Readiness probe: decide whether to receive traffic

Readiness determines whether an instance can accept new requests. Readiness may fail when:

- The ApplicationContext has not finished initializing.
- Listeners are not yet bound or serving subsystems have not initialized.
- A dependency that is strictly required for all requests is not ready.
- The instance is draining/shutting down.
- The instance is overloaded according to admission control policies.

Do not mechanically include every dependency in readiness. For example, an email provider might not be needed for an order-reading API; if the email service temporarily fails, you do not necessarily have to remove the entire API from traffic. Design readiness around the serving capability of your endpoints/workloads.

Readiness is typically used by the platform to add/remove instances from service endpoints. It does not restart the container on failure.

## 8. Startup probe protects the startup phase

A Kubernetes startup probe gives an application a longer startup window without being checked prematurely by liveness/readiness probes. While the startup probe has not yet succeeded, Kubernetes does not run liveness/readiness probes for that container.

Example:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 2
  timeoutSeconds: 1
  failureThreshold: 30
```

In this example, the maximum window by simple multiplication is roughly (30 × 2 = 60) seconds, though actual timing also depends on initial delay, probe execution, and kubelet scheduling. Do not treat that product as an absolute hard deadline.

Native startup can be fast, but you still need to account for image pull (which is outside the startup probe window), context initialization, secret/config mounts, and dependency setup. Base the window on the observed distribution of startup times rather than a single fastest run.

## 9. Complete Kubernetes startup, readiness, and liveness example

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 2
  timeoutSeconds: 1
  failureThreshold: 30

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 1

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
```

This is a sample configuration, not a default meant for every service. Tune it based on startup distribution, probe endpoint latency, platform load, and recovery objectives.

Liveness should have enough tolerance to avoid restarting on a single random timeout. Readiness can react more quickly to states where the instance cannot accept traffic. The startup probe shields the initial phase so liveness does not intervene too early.

## 10. How probe timeouts and failure thresholds affect behavior

Key Kubernetes probe parameters:

| Parameter | Meaning |
|---|---|
| `initialDelaySeconds` | Wait time before the first probe (if used) |
| `periodSeconds` | Interval between probes |
| `timeoutSeconds` | Timeout for a single probe |
| `failureThreshold` | Consecutive failures before taking the corresponding action |
| `successThreshold` | Consecutive passes to transition to success; liveness/startup usually require 1 |
| `terminationGracePeriodSeconds` | Time allowed for shutdown after the container needs to terminate |

For liveness/startup, reaching the failure threshold allows kubelet to restart the container according to its restart policy. For readiness, a non-ready endpoint causes the pod to be removed from service endpoints; the container is not restarted solely because readiness fails.

Probe endpoints must respond faster than their timeout under expected load. If a probe runs a slow database query, timeouts may reflect database latency rather than process health.

## 11. Dependency readiness and health groups

Spring Boot health groups let you separate liveness and readiness. External dependencies should only be part of readiness when the service cannot process essential requests if that dependency is unavailable.

For example, if all order-writing requests require the database, readiness can include the datasource health indicator. However, if the application can still serve cached read or metadata endpoints when the database loses connectivity, an overly strict global readiness check could unnecessarily pull instances out of rotation.

A good design:
- Liveness checks only internal state.
- Readiness reflects the ability to serve the primary workload.
- External health indicators use short timeouts without prolonged retries.
- Optional dependencies are observed via dedicated metrics/alerts.
- Degraded states can be represented without always failing readiness.

Avoid health checks that generate significant database load when hundreds of replicas probe periodically.

## 12. Restart policies and the role of the orchestrator

A restart policy defines what the platform does when a process exits or a container fails. In Kubernetes, behavior depends on the workload controller and the Pod's `restartPolicy`; Deployments typically use `Always`. When a container exits, kubelet can restart the container within the same Pod.

Distinguish between:
- Failed liveness/startup probes, which can trigger a container restart.
- Failed readiness probes, which only affect traffic routing state.
- A process exiting on its own, which can trigger a restart per policy.
- Pod deletion or node loss, which causes controllers/schedulers to recreate or reschedule the workload.

Do not design an application to restart itself via a shell loop when an orchestrator already manages its lifecycle. An extra supervisor can hide exit codes and distort shutdown signals.

## 13. CrashLoopBackOff and restart backoff

If a container repeatedly exits or is restarted due to probe failures, Kubernetes applies an exponential backoff before subsequent restarts and may report `CrashLoopBackOff`. Backoff prevents rapid continuous restarts, though it does not fix the root cause.

Investigation:

```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name> --previous
kubectl get events --sort-by=.lastTimestamp
```

Check:
- Exit code and termination reason.
- OOMKilled.
- Startup/liveness probe failures.
- Config/secret mounts.
- Port binding and permissions.
- Native library/loader errors.
- Dependency timeouts.
- Whether graceful shutdown exceeds the grace period.

Do not increase restart backoff or probe thresholds to mask a deterministic crash. Find the initial stack trace/log and reproduce it with the same image digest.

## 14. OOM and restarts differ from probe failures

A container can be `OOMKilled` when memory exceeds its limit. This is not a liveness failure. Native Image may use less heap than some JVM workloads, but RSS still includes code, thread stacks, native memory, mapped files, and libraries.

When a container restarts:
- Inspect the termination reason.
- Check cgroup peak memory usage.
- Compare heap limits against container limits.
- Check allocation bursts and live set size.
- Check whether CPU throttling is causing probe timeouts.
- Inspect native memory and third-party library usage.

Do not resolve OOM by increasing the liveness timeout. Nor should you set max heap equal to total container memory without leaving headroom.

## 15. Graceful shutdown and termination grace period

During a Deployment rollout or when a Pod is stopped, Kubernetes sends `SIGTERM` to the container process, then waits for the termination grace period before potentially sending `SIGKILL`.

Spring Boot provides graceful shutdown support. Configuration may include:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Specific timings must align with the Pod's `terminationGracePeriodSeconds` and load balancer drain times. Do not set the Spring shutdown timeout longer than the overall grace period, or the process may be killed before finishing.

During shutdown:
- Stop accepting new requests.
- Mark readiness false / drain traffic.
- Complete in-flight requests within limits.
- Close connection pools, broker consumers, and schedulers.
- Flush logs/telemetry if possible.
- Exit with an appropriate exit code.

Test shutdown while requests are in flight, not just when stopping an idle process.

## 16. Timeouts on Docker and other platforms

Docker does not have an equivalent set of Kubernetes startup/readiness/liveness probes with the same semantics. Docker `HEALTHCHECK` evaluates container health status; restart policies like `--restart=unless-stopped` control restarts on process/container exit, without automatically matching Kubernetes probe behavior.

Example:

```bash
docker run -d   --name orders-service   --restart unless-stopped   -p 8080:8080   orders-service:1.0
```

If using Docker `HEALTHCHECK`, the check command must exist inside the image. Distroless/scratch images may lack a shell or `curl`; use an exec-form healthcheck binary if available, or let an external system perform HTTP checks.

Platforms such as ECS, Nomad, or systemd have their own health/restart models. Map startup/readiness/liveness concepts onto the corresponding platform configuration; do not copy Kubernetes YAML verbatim to other platforms.

## 17. Setting timeouts from startup measurements

Measure the time from container creation to readiness across multiple runs and conditions:
- Cold image pull vs. cached image.
- Cold node vs. loaded node.
- Fast dependencies vs. slow dependencies.
- Normal startup vs. startup with migrations/cache initialization.
- Production CPU/memory limits.
- All released architectures.

Use percentiles such as p95/p99 rather than only averages. The startup probe window should cover legitimate cases without hanging indefinitely when an application stalls.

For example, if p99 time-to-ready is 18 seconds under production-like conditions, you can set a larger startup window for headroom. The exact value must factor in environmental variance and recovery objectives. Do not treat the 60-second example in documentation as a universal default for every application.

## 18. Testing probes and restart behavior

You must test not only healthy scenarios but also failure states:

| Scenario | Expected outcome |
|---|---|
| Normal startup | Startup probe passes, then readiness passes |
| Legitimately slow startup | Startup window is sufficient for the process to complete |
| Context init failure | Process/logs reflect the error; restarts per policy or rollout fails |
| Database temporarily unavailable | Readiness reflects serving capability; liveness avoids pointless restarts |
| Internal process deadlock | Liveness detects it via the designed mechanism |
| CPU throttling | Probe timeouts do not trigger a restart storm from overly sensitive settings |
| Shutdown with in-flight requests | Traffic drains and the process exits within the grace period |
| OOM | Events/metrics show OOM; sizing is adjusted |

You can use a test environment to block network access to dependencies, generate CPU load, or send `SIGTERM`. Do not run fault injection in production without a controlled plan.

## 19. Troubleshooting common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| Pod restarts before app is ready | Missing startup probe or startup window too short | Measure time-to-ready and configure a startup probe |
| Readiness fails while container keeps running | Dependency/service not yet ready | Check readiness indicator and dependencies |
| Repeated liveness restarts | Probe checks external dependencies or timeout too short | Narrow liveness scope, increase tolerance based on measurements |
| CrashLoopBackOff | Process crash, OOM, or probe failure | Describe pod, inspect previous logs and events |
| Native process starts fast but traffic arrives late | Image pull, scheduling, dependency, or readiness | Break down time-to-ready |
| Shutdown terminated by SIGKILL | Grace period too short or lifecycle phase hung | Align shutdown timeout and grace period |
| Health endpoint times out | Probe endpoint too heavy or wrong port/path | Make health checks lightweight, verify config |
| Container does not restart even though readiness fails | Readiness only removes from traffic | Use liveness for unrecoverable states |

## 20. Hands-on lab: configuring lifecycle for a native Order API

**Context:** Order API runs on Kubernetes; the native executable starts quickly but must connect to a database and message broker before accepting order-writing requests.

**Step 1 — Measure baseline.** Record process start, Spring context ready, dependency ready, and when the endpoint receives traffic across multiple runs.

**Step 2 — Enable Actuator probes.** Add the Actuator dependency, configure health groups, and confirm liveness/readiness endpoints on the actual port.

**Step 3 — Design liveness.** Check only internal state; do not let a database or payment provider outage restart all replicas.

**Step 4 — Design readiness.** Include dependencies strictly required for the served workload; keep indicator timeouts short and controlled.

**Step 5 — Configure startup probe.** Choose failure threshold/period based on p99 time-to-ready plus headroom.

**Step 6 — Align shutdown.** Enable graceful shutdown, configure phase timeout, and align the Pod termination grace period.

**Step 7 — Fault injection.** Test database unavailability, slow startup, CPU throttling, process crash, and `SIGTERM` under active requests.

**Step 8 — Observe restarts.** Record restart counts, `CrashLoopBackOff` events, `OOMKilled`, probe failures, and time-to-recovery.

Completion criteria: the startup window does not interrupt legitimate startups; readiness only accepts traffic when the service can serve; liveness does not cause restart storms; shutdown completes within the grace period; failure modes have clear logs/metrics and handling procedures.

## 21. Conclusion

Native Image can shorten process startup, yet reliable operations still depend on readiness, dependencies, image pulls, probes, and shutdown. Distinguish started, ready, and live; use a startup probe to protect initialization, readiness to control traffic, and liveness to detect unrecoverable process states.

Set timeouts according to p95/p99 time-to-ready and probe latencies measured under production-like conditions. Avoid making liveness depend on external services, align graceful shutdown with the termination grace period, and investigate `CrashLoopBackOff`/OOM using events and previous logs. Good configuration enables a native service to start quickly without creating restart loops or receiving traffic before it is ready.
