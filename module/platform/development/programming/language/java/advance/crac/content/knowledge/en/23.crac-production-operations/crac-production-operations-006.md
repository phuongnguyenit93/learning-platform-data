# Monitoring Restore Errors, Time to Readiness, and Resource Health

CRaC helps a Java application recover from a checkpoint faster than a full startup, but a successful restore time does not equal the time when the application can receive traffic. After the process is restored, the application may still need to run `afterRestore` callbacks, load configurations and secrets, recreate connection pools, connect to brokers, resume workers, verify dependencies, and transition readiness to a state accepting requests.

For reliable operations, monitor three outcomes separately:

1. **Restore success:** the JVM and checkpoint engine recover the process.
2. **Post-restore bootstrap completion:** callbacks and required resources are operational.
3. **Application readiness:** health checks pass and traffic can be routed to the instance.

A good observability system must be able to answer: which restore attempt failed, in which phase it failed, how long it took to become Ready, which dependency slowed down the process, which resource is running low, and whether the instance stays healthy after beginning to serve.

## 1. Distinguishing Restore Duration from Time to Ready

Do not combine all timings into a single metric named `startup_time`. With CRaC, there are multiple distinct milestones.

You can define the following milestones:

| Milestone | Meaning | Observation Source |
|---|---|---|
| T0 | Container or restore process starts | Kubernetes Pod/container status, entrypoint log, or node agent |
| T1 | JVM begins executing lifecycle logic after process recovery | First log in callback or application restore hook |
| T2 | All `afterRestore` callbacks and required bootstrap steps complete | Application lifecycle event |
| T3 | Readiness transitions to `ACCEPTING_TRAFFIC` and probe succeeds | Spring Boot availability, Kubernetes condition/EndpointSlice |

From there you can measure:

- **Engine/process restore time:** T0 to T1. This interval may only be measurable from outside the JVM because Java code is not running yet to write logs.
- **Post-restore bootstrap time:** T1 to T2. Measured within the application lifecycle.
- **Readiness propagation time:** T2 to T3. Includes probe duration and state updates in Kubernetes.
- **Restore-to-ready time:** T0 to T3. This is the most important metric for deployment availability.

If you measure only `afterRestore` duration, the dashboard might report restore taking 200 ms while the Pod needs another 15 seconds to become Ready. If you look only at the Pod Ready timestamp, it is hard to tell which part of the process is slow. Track both individual phases and total duration.

### 1.1. Measuring Time Inside and Outside the Process

In Java, use `System.nanoTime()` or a Micrometer `Timer` to measure the duration of callbacks and bootstrap steps. This is a monotonic measurement suited for an ongoing elapsed interval.

~~~java
long started = System.nanoTime();

try {
    reconnectDatabase();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    logger.info(
            "restore_step=database_reconnect elapsedMs={}",
            elapsedNanos / 1_000_000);
}
~~~

To measure T0 to T1, observe from outside the process, such as an entrypoint logging before invoking JVM restore, container runtime events, or node telemetry. Do not assume Java can log before the JVM has been restored.

Do not save a `System.nanoTime()` value into a checkpoint and use it to calculate elapsed time while the process was stopped. Use a monotonic clock for intervals within the same running phase; if you need to persist a deadline across a checkpoint, use `Instant` or an epoch timestamp and clearly define the policy for handling elapsed time.

### 1.2. Distinguishing Cold Start and Restore

When evaluating CRaC benefits, compare:

- Cold start: container start to readiness.
- Restore: container start/restore invocation to readiness.
- Post-restore callback time.
- Dependency reconnect time.
- Warm-up time after restore.

Compare percentiles under the same workload, same node profile, same resource limits, and same dependency conditions. If restore is fast but database reconnection is slow, further optimizing the checkpoint image may not significantly improve actual serving time.

## 2. Classifying Failures by Phase

A restore failure can occur before the JVM resumes, inside a callback, or after callbacks succeed. Classify errors so alerts reach the right responsible team.

| Phase | Example Error | Evidence to Collect |
|---|---|---|
| Artifact selection | Checkpoint missing files, checksum mismatch, or invalid manifest | Artifact ID, checksum, manifest validation |
| Engine restore | CRIU cannot restore process, incompatible kernel/CPU | CRIU logs, node fingerprint, container exit code |
| JVM resume | JVM cannot resume from image | JVM stderr, JDK vendor/build, CPU features |
| `afterRestore` callback | Resource callback throws exception or times out | Callback logs, resource name, stack trace |
| Runtime configuration | Missing config, expired secret, invalid schema | Config revision, secret provider status |
| Dependency reconnect | Database, broker, or partner API unreachable | Connection errors, timeouts, endpoint health |
| Resource initialization | Pool, executor, listener, or HTTP server fails to create | Pool/worker metrics, bind errors, resource logs |
| Readiness | Application does not transition to accepting traffic | Availability state, readiness endpoint |
| Post-ready degradation | Heap, threads, file descriptors, or queues grow abnormally | JVM metrics, cgroup metrics, resource saturation |

Use a bounded set of phase and reason values, such as `engine`, `callback`, `config`, `dependency`, `resource`, `readiness`. Do not put full exception messages or URLs into metric labels.

### 2.1. Do Not Lump Every Error into Restore Failure

For example, if the database is temporarily unavailable after the JVM has restored:

- Engine restore: succeeded.
- CRaC callbacks: may be retrying or partially completed.
- Database reconnect: temporarily failed.
- Readiness: still refusing traffic.
- Liveness: may still be healthy if the process is making progress and capable of self-recovery.

If everything is recorded as `restore_failed`, operations will struggle to distinguish checkpoint errors from dependency errors. Record phases separately and mark the overall restore attempt as failed only when the actual policy concludes it cannot continue.

## 3. Designing Structured Logs for the Restore Lifecycle

Logs should help link events from when the container starts restoring until the Pod becomes Ready. Each event should have stable fields:

- `event`: event name, such as `restore_started`, `callback_completed`, `readiness_changed`.
- `phase`: engine, callback, configuration, dependency, resource, or readiness.
- `checkpoint_id`: ID of the artifact being restored.
- `restore_operation_id`: ID of a single restore operation.
- `pod_uid` and `container_id`: identify the instance in Kubernetes.
- `node_name` and `node_profile`: identify the node/CPU profile.
- `application_version` and `image_digest`.
- `jdk_vendor`, `jdk_version`, `criu_version` when available.
- `resource`: name of the callback/resource if the event belongs to a resource.
- `elapsed_ms`: duration of the just-completed step.
- `result`: success, failure, timeout, or retry.
- `error_type`: standardized exception class or error group.
- `config_revision`: non-sensitive revision of the runtime configuration.

Example log:

~~~json
{
  "timestamp": "2026-11-13T07:10:00.015Z",
  "level": "INFO",
  "event": "restore_step_completed",
  "phase": "dependency",
  "restore_operation_id": "restore-20261113-001",
  "checkpoint_id": "orders-2.4.0-amd64-001",
  "resource": "database-pool",
  "elapsed_ms": 420,
  "result": "success",
  "pod_uid": "pod-uid-example",
  "node_profile": "orders-amd64-v2",
  "config_revision": "runtime-42"
}
~~~

The example illustrates the schema only. IDs, versions, and timestamps must come from the real runtime. Do not log passwords, tokens, private keys, connection strings containing credentials, secret contents, or customer payloads.

### 3.1. Lifecycle Events to Log

A useful event sequence:

~~~text
restore_requested
restore_process_started
restore_engine_completed
after_restore_started
runtime_config_loaded
secrets_loaded
database_reconnected
external_clients_ready
background_workers_resumed
application_ready
~~~

If engine restore fails before the JVM runs, application logs may not contain `restore_engine_completed`. In that case, correlate CRIU/container runtime logs with Pod Events and the exit code.

### 3.2. Using Logs to Measure Each Slow Step

Do not log only `afterRestore completed`. Record durations separately for:

- Reading configuration.
- Fetching secrets.
- Creating connection pools.
- Checking the database.
- Connecting to the message broker.
- Creating HTTP clients.
- Warming up caches.
- Resuming schedulers/workers.
- Final health check.

If total callbacks take 12 seconds and database reconnection accounts for 10 seconds, the dashboard needs to clearly highlight that breakdown. When multiple callbacks exist, log both the resource name and execution order.

## 4. Core Metrics for CRaC

Metrics help track trends across multiple Pods, checkpoints, and nodes. Organize them into groups: restore outcomes, durations, callbacks, readiness, dependencies, and resources.

### 4.1. Restore Results and Failures

Suggested metrics:

| Metric | Type | Meaning |
|---|---|---|
| `crac_restore_attempts_total` | Counter | Total recorded restore attempts |
| `crac_restore_failures_total` | Counter | Number of failed restore attempts |
| `crac_restore_in_progress` | Gauge | Whether a restore/bootstrap is currently in progress |
| `crac_restore_phase_failures_total` | Counter | Failures by standardized phase |
| `crac_checkpoint_artifact_validation_failures_total` | Counter | Pre-restore artifact validation failures |

The failure counter should increment exactly once per failed attempt. Avoid incrementing multiple times for the same exception due to internal retries; if retries need to be observed, create a separate metric such as `crac_dependency_retries_total`.

### 4.2. Restore Duration and Callback Duration

| Metric | Type | Meaning |
|---|---|---|
| `crac_restore_to_ready_seconds` | Histogram | Time from T0 to T3 |
| `crac_engine_restore_seconds` | Histogram | Engine/process restore duration |
| `crac_post_restore_bootstrap_seconds` | Histogram | T1 to T2 |
| `crac_callback_duration_seconds` | Histogram | Callback duration by resource and phase |
| `crac_dependency_reconnect_seconds` | Histogram | Dependency reconnect duration |
| `crac_readiness_transition_seconds` | Histogram | Time from bootstrap completion to readiness success |

Use histograms to compute p50, p95, and p99 across multiple instances. Do not rely solely on averages; a few very slow restoring Pods can be hidden by the mean.

### 4.3. Readiness and Unavailability Duration

| Metric | Type | Meaning |
|---|---|---|
| `application_ready` | Gauge | 1 when the application accepts traffic, 0 when not ready |
| `application_not_ready_seconds` | Histogram or total duration | Time spent in the non-Ready state |
| `crac_restore_ready_timeout_total` | Counter | Number of readiness deadline breaches |
| `crac_readiness_transitions_total` | Counter | Number of readiness state transitions |
| `crac_background_workers_ready` | Gauge | Status of required background workers |

For Ready state, you can use the Spring Boot availability state or an application-updated gauge. Do not create a new gauge for each request or each callback execution.

### 4.4. Callback Failures and Timeouts

Monitor:

- Callbacks currently running.
- Completed callbacks.
- Callback timeouts.
- Callback exceptions by group.
- Callback duration by resource.
- Worker drain and pool close durations.

Suggested metrics:

~~~text
crac_callback_duration_seconds{phase="afterRestore",resource="database",outcome="success"}
crac_callback_failures_total{phase="beforeCheckpoint",resource="worker",error_type="TimeoutException"}
crac_callback_in_progress{phase="afterRestore",resource="http-client"}
~~~

Use only values for `resource`, `phase`, `outcome`, and `error_type` from a bounded list. Do not use exception messages as labels, because each message can differ and create very high cardinality.

## 5. Micrometer Instrumentation in Spring Boot

Spring Boot Actuator and Micrometer can expose metrics to Prometheus or other observability backends. Custom metrics help measure lifecycle phases that default JVM metrics are unaware of.

Example recorder:

~~~java
package com.example.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.TimeUnit;

@Component
public class RestoreMetrics {

    private final MeterRegistry registry;
    private final AtomicInteger restoreInProgress = new AtomicInteger();

    public RestoreMetrics(MeterRegistry registry) {
        this.registry = registry;
        Gauge.builder(
                "crac_restore_in_progress",
                restoreInProgress,
                AtomicInteger::get)
                .register(registry);
    }

    public Timer.Sample startTimer() {
        return Timer.start(registry);
    }

    public void setRestoreInProgress(boolean inProgress) {
        restoreInProgress.set(inProgress ? 1 : 0);
    }

    public void recordCallback(
            Timer.Sample sample,
            String phase,
            String resource,
            String outcome) {

        Timer timer = Timer.builder("crac_callback_duration")
                .description("Duration of CRaC resource callbacks")
                .tag("phase", phase)
                .tag("resource", resource)
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry);

        sample.stop(timer);
    }

    public void incrementRestoreFailure(String phase, String reason) {
        Counter.builder("crac_restore_failures")
                .description("Failed CRaC restore attempts")
                .tag("phase", phase)
                .tag("reason", reason)
                .register(registry)
                .increment();
    }

    public void recordRestoreToReady(long elapsedNanos) {
        Timer.builder("crac_restore_to_ready")
                .description("Time from restore invocation to application readiness")
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);
    }
}
~~~

Micrometer normalizes metric names per registry. For example, the name `crac_restore_to_ready` may be exported as `crac_restore_to_ready_seconds` in Prometheus. Check the actual name at the metrics endpoint of the registry in use.

Example invocation inside a callback:

~~~java
@Override
public void afterRestore(
        Context<? extends Resource> context) throws Exception {

    Timer.Sample sample = restoreMetrics.startTimer();
    String outcome = "success";

    try {
        reconnectDatabase();
        restoreHttpClient();
    } catch (Exception failure) {
        outcome = "failure";
        restoreMetrics.incrementRestoreFailure(
                "afterRestore",
                classify(failure));
        throw failure;
    } finally {
        restoreMetrics.recordCallback(
                sample,
                "afterRestore",
                "runtime-dependencies",
                outcome);
    }
}
~~~

This is an illustrative pattern. In production code, record callbacks separately per resource so you know exactly which step is slow. If a callback hangs indefinitely, the `finally` block will not execute; an external watchdog or supervisor must detect that state.

### 5.1. Avoiding High Cardinality

Do not use the following values as metric labels:

- Checkpoint ID unique to each build or dump.
- Restore operation ID.
- Pod UID if the system has a large number of instances and per-Pod breakdown in metrics is not needed.
- Exception message.
- Full URL or database hostname.
- User ID, tenant ID, or request ID.

Detailed identifying values should be placed in logs or traces. Metrics should use bounded dimensions such as phase, resource class, outcome, environment, and node profile.

### 5.2. Handling Metric State Restored from a Checkpoint

The metrics registry, counters, timers, or gauges may be objects in the heap saved inside the checkpoint. Therefore, after restore, do not assume every counter starts at 0 or every timestamp reflects the current restore run.

Decide semantics for each metric:

- Business/lifetime counters may continue from their checkpointed values if preserving cumulative totals is desired.
- Per-process/restore-attempt counters should be initialized per instance lifecycle or restore generation.
- Gauges for connections, active workers, queue sizes, and readiness must be refreshed from actual resource state.
- Timestamps such as process start or last scrape must be checked to avoid reflecting pre-checkpoint times.
- Exporters/registries must reconnect to backends and not retain stale transport state.

If the same checkpoint is restored multiple times, each instance may start from the same counter snapshot. Use an instance identity appropriate to the Pod/container, or reinitialize process-local metric groups after restore according to policy. Do not attach a unique restore ID to every metric label if doing so causes unbounded cardinality growth.

## 6. Monitoring JVM Health After Restore

After restore, the JVM may run while internal resources are already near their limits or in an unsuitable state.

### 6.1. Heap and Non-Heap Memory

Monitor:

- Heap used, committed, and max.
- Metaspace and compressed class space.
- Direct buffer memory.
- Code cache.
- Garbage collection count and pause duration.
- Allocation rate and promotion rate.

A checkpoint created after warm-up may contain a heap that already grew during the preparation workload. After restore, if the heap is already near max, new requests may trigger continuous GC or OutOfMemoryError.

Do not look only at the heap percentage immediately after restore. Observe the trend over several minutes once traffic starts and compare it against a cold-start baseline.

### 6.2. Threads and Executors

Monitor:

- Live thread count.
- Daemon thread count.
- Thread states: RUNNABLE, BLOCKED, WAITING, TIMED_WAITING.
- Executor active count.
- Queue depth.
- Rejected task count.
- Worker start/stop failures.
- Callback duration and lock wait.

If thread count after restore is higher than normal, a callback may have created new threads without stopping old ones, or an executor was initialized twice. If queue depth climbs continuously, workers may not have resumed yet or a dependency is degrading throughput.

### 6.3. Class Loading, JIT, and GC

Warm-up before checkpoint may have already initialized the code cache and JIT state. After restore, observe:

- JIT compilation activity.
- Code cache usage.
- Class loading count.
- GC pauses.
- Safepoint duration.
- CPU usage during bootstrap.

Do not assume all optimizations will always be preserved as expected across every JDK/runtime. Measure on the exact JDK build and workload.

### 6.4. Native Memory and Direct Buffers

Heap does not reflect all JVM memory. HTTP clients, TLS, Netty, NIO, compression, and native libraries can use native/direct memory.

Monitor:

- Direct buffer pool used/capacity.
- Native Memory Tracking if enabled from JVM startup.
- Process/container RSS.
- Cgroup memory usage.
- Memory pressure and OOM kill events.

If direct buffer or native memory spikes after restore, check whether clients/resources were duplicated or old buffers were not released.

## 7. Monitoring Resource and Dependency Health

Readiness may pass while resources are already saturated. Monitor the health and saturation of each dependency.

### 7.1. Database Connection Pool

With HikariCP, useful metrics include:

- Active connections.
- Idle connections.
- Pending threads waiting for a connection.
- Maximum pool size.
- Connection acquisition time.
- Connection timeout count.
- Connection creation/validation failures.

After restore, the pool needs to be recreated or verified according to the designed lifecycle. Having 0 active connections right after restore may simply mean no traffic has arrived yet; if pending threads keep increasing, the pool may be unable to meet load.

Do not mark the pool healthy just because the DataSource object exists. Verify connection acquisition capability and a lightweight query with a timeout.

### 7.2. HTTP Clients and External Services

Monitor:

- Number of open/available/pending connections.
- TLS handshake failures.
- DNS resolution errors.
- Connect/read/request timeouts.
- Retry count and backoff.
- Request error rate and latency.

A connection restored in the heap may no longer be valid on the server side. The client must reconnect or validate connections per its lifecycle. Do not let health indicators fire bursts of requests to partner APIs on every probe.

### 7.3. Message Brokers and Consumers

Monitor:

- Consumer connected/registered status.
- Partition assignment or subscription state.
- Consumer lag.
- In-flight messages.
- Ack/nack/retry rate.
- Lease/session expiry.
- Rebalance duration.
- Duplicate processing or idempotency conflicts.

An existing consumer object does not prove the broker still considers it a valid consumer. After restore, verify the session/lease and observe lag before treating the worker as ready.

### 7.4. Background Workers and Schedulers

Monitor:

- Active worker count.
- Queue depth.
- Timestamp of the most recent successful job.
- Next scheduled run.
- Missed-run/catch-up count.
- Retry backlog.
- Task duration and failure count.

HTTP server readiness does not by itself prove that schedulers or consumers are operational. If workers are part of serving capability, include their status in the readiness policy or a dedicated health group.

## 8. File Descriptors, Sockets, Filesystem, and Linux Resources

A JVM may have a normal heap yet fail due to operating system resources.

Metrics to observe:

| Resource | Abnormal Sign |
|---|---|
| File descriptors | Open FDs approaching `ulimit -n` or container limit |
| Sockets | Many connections in CLOSE_WAIT/TIME_WAIT state, bind errors |
| Disk/ephemeral storage | Checkpoints, logs, or temp files filling up the volume |
| Inodes | No free inodes left to create new files |
| Cgroup memory | Memory usage near limit or OOM events |
| CPU throttling | Container CPU-throttled during bootstrap |
| PID/thread limit | Unable to spawn additional worker threads or processes |
| Mount/volume | File does not exist, permission denied, or volume unavailable |

On Linux, some inspection commands:

~~~bash
cat /proc/self/limits
ls /proc/<PID>/fd | wc -l
cat /proc/<PID>/status
df -h
df -i
~~~

In Kubernetes:

~~~bash
kubectl describe pod <POD_NAME>
kubectl describe node <NODE_NAME>
kubectl top pod <POD_NAME>
kubectl top node <NODE_NAME>
~~~

Process and cgroup metrics must be collected from the exact container/cgroup. Host-level numbers do not always reflect the limits actually enforced on the Pod.

## 9. Readiness, Liveness, and Resource Health

Do not use a single health endpoint to represent every type of health.

You can divide health into groups:

- **Liveness:** the JVM/process is still making progress and capable of self-recovery.
- **Readiness:** required requests can be served at the current moment.
- **Startup/restore completion:** mandatory bootstrap steps have finished.
- **Dependency health:** status of database, broker, secret provider, and external APIs.
- **Resource health:** whether memory, threads, file descriptors, queues, and pools are within operational limits.

For example, if the database is temporarily unavailable:

- Liveness: UP.
- Readiness: DOWN if all critical requests require the database.
- Dependency health: database DOWN.
- Restore completion: may be COMPLETE if the application has restored and can wait to reconnect.

For example, if heap is near the warning threshold while requests still work:

- Liveness: UP.
- Readiness: may be UP if it has not crossed a threshold impacting serving capability.
- Resource health: DEGRADED.
- Alert: raise a memory pressure warning.

Do not feed every resource warning into liveness. A metric exceeding a warning threshold does not necessarily require restarting the container.

### 9.1. Spring Boot Actuator Health Indicator

You can create a dedicated health indicator for restore state:

~~~java
package com.example.health;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class RestoreHealthIndicator implements HealthIndicator {

    private final RestoreState restoreState;

    public RestoreHealthIndicator(RestoreState restoreState) {
        this.restoreState = restoreState;
    }

    @Override
    public Health health() {
        if (restoreState.isInProgress()) {
            return Health.down()
                    .withDetail("phase", restoreState.phase())
                    .build();
        }

        if (restoreState.hasFailed()) {
            return Health.down()
                    .withDetail("phase", restoreState.phase())
                    .withDetail("errorType", restoreState.errorType())
                    .build();
        }

        return Health.up()
                .withDetail("phase", "complete")
                .build();
    }
}
~~~

This is an example of a health indicator; you need to decide which group includes it. If the indicator is placed in the readiness group, the Pod will not receive traffic until restore completes. It does not necessarily belong in the liveness group.

Public/internal health responses should limit details. Only expose standardized exception classes or phases; do not return messages containing credentials or internal URLs.

### 9.2. Updating Availability State

Spring Boot can use `AvailabilityChangeEvent` to transition readiness:

~~~java
publisher.publishEvent(
        new AvailabilityChangeEvent<>(
                this,
                ReadinessState.REFUSING_TRAFFIC));

// Once config, dependencies, and required resources are ready:
publisher.publishEvent(
        new AvailabilityChangeEvent<>(
                this,
                ReadinessState.ACCEPTING_TRAFFIC));
~~~

After restore, keep `REFUSING_TRAFFIC` while callbacks and bootstrap are still running. Transition the state only after mandatory resources are verified. Additional health indicators provide detailed observability; the availability state controls the readiness outcome.

## 10. Monitoring Restore on Kubernetes

Kubernetes provides Pod status, container status, Events, restart counts, and EndpointSlices. Combine these sources to distinguish restore failures from readiness delays.

### 10.1. Pod Conditions and Container Status

~~~bash
kubectl get pod <POD_NAME> -o wide
kubectl describe pod <POD_NAME>
kubectl get pod <POD_NAME> -o json
~~~

Observe:

- `PodScheduled`.
- `Initialized`.
- `ContainersReady`.
- `Ready`.
- Container `state`, `lastState`, `restartCount`.
- `startedAt`, `finishedAt` if present.
- Reason/message of container termination.
- Probe failures and Events.

`Pod Ready` is a Kubernetes state aggregated from container readiness and related conditions. It does not indicate which callback caused a slowdown; correlate it with application logs and metrics.

### 10.2. Confirming the Pod Has Joined Service Endpoints

~~~bash
kubectl get endpointslices \
  -l kubernetes.io/service-name=<SERVICE_NAME> \
  -o yaml
~~~

Check `conditions.ready` on the endpoint. When readiness fails, the endpoint is not considered Ready to receive new traffic through the Service under standard configurations.

If the application has already logged `application_ready` but the EndpointSlice has not updated yet, there may be propagation delay or a Service/Pod configuration mismatch. Measure T2 to T3 separately to detect this case.

### 10.3. Collecting Logs When a Container Restarts

~~~bash
kubectl logs <POD_NAME> -c app
kubectl logs <POD_NAME> -c app --previous
kubectl get events --sort-by=.lastTimestamp
~~~

`--previous` is useful when the container has restarted and logs from the previous instance still remain. If engine restore fails before Java logging is initialized, capture container stderr, CRIU logs, and node/runtime diagnostics as well.

## 11. Operational Dashboard for CRaC

A dashboard should be organized around the questions operators need to answer.

### 11.1. Overview Row

Display:

- Total restore attempts within the time window.
- Restore success rate.
- Restore failure count by phase.
- p50/p95/p99 restore-to-ready.
- Number of Pods currently restoring.
- Number of Pods not Ready.
- Number of Pods in a restart loop.
- Number of node profiles experiencing restore failures.

### 11.2. Lifecycle Row

Time-series charts for:

- Engine restore duration.
- `afterRestore` total duration.
- Callback duration by resource.
- Runtime config/secret load duration.
- Database reconnect duration.
- Broker/client reconnect duration.
- Readiness propagation time.

Use stacked breakdowns or heatmaps to identify which phase accounts for most of the time.

### 11.3. JVM and Resource Row

Display:

- Heap used/max and GC pauses.
- Non-heap/direct memory.
- Live/blocked thread count.
- Executor active/queue/rejected counts.
- Database pool active/idle/pending connections.
- HTTP client connections/pending requests.
- Open file descriptors.
- Container memory/CPU/throttling.
- Ephemeral storage.
- Message consumer lag.

### 11.4. Node and Compatibility Profile Row

Display:

- Node architecture.
- CPU profile/feature label.
- Kernel version.
- CRIU version.
- Container runtime.
- Restore success rate by node profile.
- Restore-to-ready percentiles by profile.
- Failures concentrated on a single node or hardware type.

Profile-based dashboards help detect checkpoints failing only on a group of nodes with different CPU/kernel/runtime characteristics. Do not make node name or Pod UID a label on every metric if the cardinality is large; use logs/tracing or drill-down dashboards for per-instance details.

## 12. Alerting and SLI/SLO

Alerts should reflect user impact or operational risk, not just a single failed probe.

Signals worth watching:

- Sudden spike in restore failures.
- p95/p99 restore-to-ready exceeding budget.
- Pods remaining not Ready past deadline.
- Callbacks running too long.
- Continuous readiness flapping.
- Rising database pool pending threads or connection timeouts.
- Thread count/FD/memory climbing near limits.
- Increasing consumer lag after restore.
- Multiple Pods restarting or failing together on a single node profile.

### 12.1. Defining SLIs

Example SLIs for restore:

- **Restore success rate:** number of successful restore attempts divided by total attempts.
- **Restore-to-ready latency:** time from restore invocation to readiness success.
- **Readiness availability:** percentage of time instances are eligible to receive traffic.
- **Post-restore stability:** percentage of instances that do not restart or drop out of readiness within a defined post-restore window.

Set SLOs based on actual workload and serving requirements. For example, you might target p95 restore-to-ready below a set budget and a restore success rate above a threshold. Do not copy numbers from another environment without measuring a baseline.

### 12.2. PromQL Examples

Assuming the histogram metric is exported with the `_bucket` suffix:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(crac_restore_to_ready_seconds_bucket[15m])
  )
)
~~~

Failure rate over a window:

~~~promql
sum(rate(crac_restore_failures_total[10m]))
/
clamp_min(sum(rate(crac_restore_attempts_total[10m])), 1)
~~~

Restore failure count:

~~~promql
increase(crac_restore_failures_total[15m])
~~~

Callback running too long, assuming a gauge tracks callback state and a separate start-age metric exists:

~~~promql
crac_callback_in_progress == 1
and
crac_callback_elapsed_seconds > 30
~~~

Metric names are examples. Ensure metrics have the right semantics and labels before using them in alerts. Do not divide the failure counter by the attempt counter if one attempt can emit multiple failure events; clearly define counter increments so numerator and denominator share the same unit.

### 12.3. Multi-Level Alerting

| Level | Example Condition | Action |
|---|---|---|
| Warning | p95 restore-to-ready rises compared to baseline | Check slow phases and node profiles |
| Warning | Callback exceeds budget without timing out yet | Collect thread dump or inspect resource metrics |
| Critical | Consecutive restore attempt failures | Halt rollout, keep artifact/node profile stable |
| Critical | Pod not Ready past SLO and making no progress | Check callbacks, dependencies, and probes |
| Critical | Memory/FDs near limit or OOM kill | Investigate leaks, resource limits, and concurrency |
| Critical | Multiple nodes with same profile fail to restore | Check compatibility, CRIU, and kernel changes |

Do not alert solely on a brief single readiness failure during normal bootstrap. Combine duration, failure count, restart count, and impact on the number of Ready replicas.

## 13. Detecting Readiness Flapping and Resource Degradation

A Pod may toggle between Ready and NotReady repeatedly after restore due to flaky dependencies or saturated pools.

Monitor:

- Number of availability transitions within a window.
- Continuous duration in NotReady.
- Request error rate and latency while Ready.
- Pool pending threads and acquisition timeouts.
- Worker queue depth and rejected tasks.
- Consumer lag and reconnect count.

Readiness flapping can cause EndpointSlices to churn continuously, destabilize traffic distribution, and put extra load on remaining Pods. Identify the root cause before merely increasing probe thresholds.

Resource degradation can occur while readiness remains UP. For example, heap at 90%, rising GC pauses, and worsening request latency while the health endpoint still returns 200. Therefore, health endpoints do not replace saturation metrics and alerts.

## 14. Tracing Post-Restore Bootstrap Steps

Distributed tracing can help analyze the reconnection sequence when the application has many dependencies. Create a new trace or span for each restore attempt, with child spans:

~~~text
crac.restore.bootstrap
  ├── load.runtime-config
  ├── load.secrets
  ├── reconnect.database
  ├── reconnect.message-broker
  ├── create.http-client
  ├── warmup.required-cache
  ├── resume.background-workers
  └── publish.application-ready
~~~

Attach useful attributes:

- `checkpoint.id`
- `restore.operation`
- `restore.phase`
- `application.version`
- `node.profile`
- `resource.name`
- `outcome`

Do not attach secrets, full credential URLs, or sensitive payloads. Limit sampling and retention to avoid generating excessive traces on every restore.

Do not keep an open span across a checkpoint and expect the trace exporter to continue sending it properly after restore. Before checkpoint, flush or end spans appropriately; after restore, start a new trace for the new phase and link them via the checkpoint/operation correlation ID if the tracing backend supports links.

## 15. Distinguishing Application Failures from Checkpoint Engine Failures in Metrics

There are cases where application logs contain no callback events at all because the process image was never restored. Relying solely on Micrometer may cause the dashboard to miss the failure.

Collect data across multiple layers:

| Layer | Data |
|---|---|
| Pipeline/artifact store | Checkpoint ID, checksum, manifest, validation result |
| Kubernetes | Pod events, scheduling, restart count, node assignment |
| Container runtime | Container start/exit, image digest, runtime errors |
| CRIU/CRaC engine | Dump/restore logs, error codes, kernel/CPU diagnostics |
| JVM/application | Callback logs, exceptions, bootstrap duration |
| Metrics backend | Restore attempts, readiness, JVM/resource metrics |
| Node monitoring | Kernel, memory pressure, CPU, disk, cgroups |

If `restore_requested` appears in the orchestrator without `after_restore_started`, inspect the engine/runtime before looking for bugs in application callbacks.

## 16. Testing Observability and Failure Scenarios

Instrumentation is only useful if verified under realistic scenarios.

| Scenario | What to Verify |
|---|---|
| Normal successful restore | Milestones T0–T3 and restore-to-ready duration are complete |
| Callback throws exception | Failure counter increments exactly once and logs include phase/resource |
| Callback hangs | Watchdog detects it, elapsed time rises, and thread dump is captured |
| Database unavailable | Dependency failure is classified separately, readiness follows policy |
| Secret provider timeout | No secrets logged; standardized timeout and reason recorded |
| Resource pool fails to initialize | Callback/resource failure is recorded |
| Readiness does not transition | Pod remains NotReady and alerts trigger per budget |
| Pod restarts after restore | `--previous` logs and restore attempt identity can be correlated |
| Insufficient memory/FDs | Metrics and node/container events identify the limit |
| Restore on different node profile | Dashboard separates failures by profile |
| Many Pods restore simultaneously | No unexpected connection bursts or memory pressure |
| Repeated restores of same checkpoint | Metric counters/instance identity do not mislead |

### 16.1. Verifying Metric Semantics

Reconcile the restore count in application logs against `crac_restore_attempts_total` and `crac_restore_failures_total`. Check whether the histogram count matches the number of completed attempts.

If the metrics registry is restored from the checkpoint, test restoring the same artifact multiple times and observe counters, process start timestamps, gauges, and exporter state. Verify that the dashboard does not misinterpret restored values as fresh data from the current attempt.

### 16.2. Verifying Alerts

In staging, simulate:

- Restore duration exceeding budget.
- Slow callbacks.
- Failed dependency reconnection.
- Readiness remaining false.
- Memory pressure or growing worker queues.

Confirm that alerts reach the right team and include sufficient checkpoint ID, phase, and Pod/node identity in logs or dashboard links for investigation.

## 17. Runbook for Slow or Failed Restores

When receiving an alert, handle it in sequence:

1. Identify the checkpoint ID, restore operation ID, Pod UID, and node.
2. Check Pod Events, container exit code, restart count, and Ready status.
3. Inspect restore engine logs to determine whether the process was recovered.
4. If `afterRestore start` occurred without completion, check the last callback/resource and capture a thread dump.
5. Compare T0–T3 to determine whether engine, callbacks, dependencies, or readiness propagation consumed the time.
6. Check config revision, secret provider, and dependency endpoints.
7. Check heap, GC, threads, executor queues, pools, FDs, cgroup memory/CPU, and disk.
8. Compare node fingerprints/profiles if the failure occurs only on a subset of nodes.
9. Keep the Pod NotReady while mandatory dependencies are not working.
10. Halt rollout if the error repeats across multiple instances; collect artifacts/manifests/logs before retrying.
11. Switch to cold start or another checkpoint only according to a tested recovery policy.

Do not trigger mass restarts simply because the database is temporarily unavailable. Do not increase probe timeouts to mask a callback deadlock. If the checkpoint artifact or node profile is incompatible, fix the root cause or choose a verified artifact/profile.

## 18. Operational Checklist

Before deploying a checkpoint to production, confirm the system can:

- [ ] Record checkpoint ID and restore operation ID.
- [ ] Distinguish engine restore, callback, dependency, and readiness failures.
- [ ] Measure restore-to-ready and individual phase durations.
- [ ] Emit callback start/complete/error logs.
- [ ] Expose attempt, failure, duration, and in-progress metrics.
- [ ] Maintain readiness state accurately reflecting mandatory dependencies.
- [ ] Monitor heap, GC, direct/native memory, and threads.
- [ ] Monitor database pools, HTTP clients, brokers, and worker queues.
- [ ] Monitor FDs, sockets, disk, cgroup memory, and CPU throttling.
- [ ] Provide dashboards broken down by node/CPU/runtime profile.
- [ ] Configure alerts aligned with SLOs and failure budgets.
- [ ] Maintain a runbook for collecting logs, thread dumps, and CRIU diagnostics.
- [ ] Test counter/gauge semantics across repeated restores.
- [ ] Exclude secrets and high-cardinality IDs from metric labels.
- [ ] Run canary restores and smoke tests before broad rollout.

## 19. Observability Design Principles for CRaC

CRaC monitoring must cover both process restore and post-restore serving capability. Measure engine restore, callbacks/bootstrap, dependency reconnection, and readiness propagation separately; write structured logs to link events by checkpoint and restore attempt; use histogram metrics to track percentiles; and monitor both JVM and operating system resources.

A Pod should be considered ready only when mandatory dependencies and resources needed for requests are operational. At the same time, readiness does not replace liveness, and health endpoints do not replace saturation metrics. The database may be unavailable while the process is alive; the heap may be near its limit while readiness is still UP; consumers may not have resumed even though the HTTP server is Ready. Separate signals are needed for each state.

When restore is slow or fails, dashboards and logs must show the last completed phase, the running node/profile, which resource is waiting, and whether the process is making progress. With this data in hand, operations teams can distinguish checkpoint engine failures, hung callbacks, slow dependencies, and resource exhaustion, and choose the right remediation without blind restarts or rollbacks.

## 20. References

- [CRaC: Implementing the CRaC API](https://crac.org/use/implement-crac/): managing resources before checkpoint and after restore.
- [CRaC: Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/): configuring and performing checkpoint/restore.
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer and metrics integration in Spring Boot.
- [Spring Boot Actuator — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): readiness/liveness health groups.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): measuring durations and histograms.
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): counting events.
- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/): percentiles and latency distributions.
- [Kubernetes — Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): Pod conditions and container lifecycle.
- [Kubernetes — Configure liveness, readiness and startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): probe behavior and configuration.