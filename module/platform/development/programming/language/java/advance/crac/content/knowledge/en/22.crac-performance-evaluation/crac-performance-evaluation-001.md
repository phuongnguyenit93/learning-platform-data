# Defining Startup Time, Time to Readiness, and First Response Time

When evaluating the performance of a Java application using CRaC (Coordinated Restore at Checkpoint), it is essential to clearly distinguish startup time, time to readiness, and first response time. These three metrics are related, yet they describe different phases. A process may be restored very quickly but remain unable to accept requests because it still needs to recreate connections, refresh caches, or finish warming up. Conversely, a Pod may already be Ready while the first request is still slow due to JIT compilation, cache misses, or connecting to dependent services.

Measuring only a single number such as "startup time" can lead a development team to misjudge the benefits of checkpointing. You need to define the start milestone, end milestone, and measurement scope for each metric. At the same time, separate measurements taken inside the JVM from measurements observed by Kubernetes or external clients.

This lesson defines the timeline milestones, how to measure them in Java applications and Kubernetes, how to interpret results when using CRaC, and a benchmarking methodology to compare cold start with restore.

## 1. Why Define Each Metric Separately?

A Java application goes through several phases from container creation until it successfully serves the first request:

1. Kubernetes schedules the Pod onto a node.
2. The container runtime prepares the filesystem and starts the process.
3. The JVM boots or the process is restored from a checkpoint.
4. The framework and application finish initialization.
5. External resources are recreated or reconnected.
6. Essential caches are validated and warmed up.
7. The application transitions to the Ready state.
8. The first request is sent to the application.
9. The application processes the request and sends a response.

Each phase can carry significant cost. Measuring from Pod creation to when the first request returns includes scheduling, image pull, restore, readiness, and request processing. Measuring only from entering main until the framework reports ready omits Kubernetes and container costs.

Therefore, identify which question you are trying to answer:

- How long does the JVM or process take to start executing?
- How long does the application take to finish initializing?
- How long does the Pod take to be marked Ready by Kubernetes?
- How long does it take from restore start until the application can receive traffic?
- How long does the first request take to return a response?
- How long does it take from Pod creation to the first successful response?

These questions are not interchangeable.

## 2. Timeline Milestone Model

Observation milestones can be placed as follows:

| Milestone | Meaning |
|---|---|
| T0 | Measurement start at process, container, or Pod level |
| T1 | JVM begins executing application code |
| T2 | Framework and application context initialization complete |
| T3 | Restore callbacks and essential resources complete |
| T4 | Application internally transitions to READY |
| T5 | Kubernetes marks the Pod Ready |
| T6 | First request arrives at the application |
| T7 | First successful response is sent |

Not every system needs all of these milestones. What matters is stating explicitly which milestones each metric uses.

~~~mermaid
flowchart TD
    A["T0: Container/process start"] --> B["T1: JVM/application execution"]
    B --> C["T2: Framework initialized"]
    C --> D["T3: CRaC resources restored"]
    D --> E["T4: Application READY"]
    E --> F["T5: Kubernetes Pod READY"]
    F --> G["T6: First request received"]
    G --> H["T7: First successful response"]
~~~

In a cold start, T1 is typically when the JVM starts executing the application. In a CRaC restore, the process is reconstructed from a checkpoint and may resume from saved state. Therefore, record the restore start milestone provided by the runtime or orchestrator separately rather than assuming every run shares the same JVM launch milestone.

## 3. What Is Startup Time?

**Startup time** is the elapsed duration from a predefined starting milestone until a component or application finishes a defined initialization phase.

The term startup time is often applied to multiple scopes. When publishing measurements, specify whether it refers to:

- JVM startup time.
- Application startup time.
- Container startup time.
- Pod startup time.
- CRaC restore duration.

### 3.1. JVM startup time

JVM startup time typically measures from when the Java process is launched until the JVM begins executing application code or reaches a chosen runtime milestone.

Example:

- T0: Java process is created.
- T1: application code begins executing.
- JVM startup time = T1 − T0.

This milestone is useful when analyzing JVM initialization cost, initial class loading, runtime configuration, and activities occurring before application code begins.

However, with CRaC, restore is not like starting a fresh Java run from scratch. The process is recovered from a checkpoint and can resume in an already-initialized state. Consequently, do not directly compare cold-start JVM startup time against restore duration if the two measurements begin at different milestones.

### 3.2. Application startup time

Application startup time measures from when the application begins initialization until the framework or application completes its defined startup phase.

For example, in a Spring Boot application, you can choose ApplicationReadyEvent as the milestone indicating the application has completed initialization according to Spring Boot's lifecycle.

If:

- T1: application startup begins.
- T2: application ready event occurs.

Then:

\[
T_{\text{application-startup}} = T2 - T1
\]

This milestone typically includes:

- Initializing the dependency injection container.
- Creating beans.
- Registering routes.
- Loading configuration.
- Initializing serializers and mappers.
- Creating certain clients or resources.
- Running application runners or startup tasks.

Examine the exact framework event chosen. An event indicating context refreshed does not necessarily mean all resources are ready to serve requests.

### 3.3. Container and Pod Startup Time

Container startup time typically measures from when the container runtime begins creating or starting the container until the process inside the container begins executing.

Pod startup time has a broader scope. It can include:

- Scheduler assigning a node.
- Image pulling.
- Volume mounting.
- Sandbox and network creation.
- Container creation.
- Process startup.
- JVM restore or startup.
- Waiting for startup/readiness probes.

When measuring Pod startup time, decide whether T0 is the Pod creation timestamp, the time the Pod is scheduled, or the time the container begins running. Each choice answers a different operational question.

## 4. Restore Time in CRaC

With CRaC, an additional dedicated metric is needed: **restore duration**.

Restore duration typically measures from when the runtime or tool starts restoring the checkpoint until the process is recovered and able to resume execution at the runtime level. The exact end milestone depends on the checkpoint tooling and CRaC integration.

Restore duration does not necessarily encompass all work in afterRestore callbacks, warm-up, or readiness. Therefore, record separately:

- Restore start.
- Process resumed.
- afterRestore preparation completed.
- Application ready.
- Pod ready.

Example:

| Phase | Illustrative Duration |
|---|---:|
| Restore process | 180 ms |
| Recreate database/Redis clients | 350 ms |
| Refresh essential caches | 220 ms |
| Application readiness transition | 30 ms |
| Kubernetes probe observation delay | 5 s |
| First request processing | 45 ms |

In this example, restoring the process takes only 180 ms, yet the time until Pod Ready is much longer. Reporting only the restore duration could mislead readers into thinking the application is ready to serve after 180 ms.

### 4.1. Starting Milestone of Restore Measurements

Depending on the architecture, you may choose:

- When the restore controller requests restoration.
- When CRIU begins restoring.
- When the container runtime starts the restore operation.
- When the container process is restored.

When comparing runs, use the exact same definition. Scheduling and image pull times should be measured separately if the goal is to evaluate only the CRaC portion.

### 4.2. The afterRestore Callback Does Not Equal Pod Ready

The afterRestore callback lets the application recover resources after the process is restored. Inside the callback, the application may:

- Recreate connection pools.
- Connect to Redis or databases.
- Refresh DNS or service discovery.
- Restore subscriptions.
- Invalidate stale caches.
- Warm up essential data.

Once the callback finishes, the application has only completed the tasks managed by that callback. Kubernetes still needs to observe the readiness probe and update the Pod status. If the application also performs background initialization after the callback, the Pod may need to wait longer.

## 5. What Is Time to Readiness?

**Time to readiness** is the elapsed duration from the selected start milestone until the application or Pod satisfies the conditions to accept traffic.

Distinguish two metrics:

1. Application readiness time: when the application internally declares itself ready.
2. Kubernetes Pod Ready time: when Kubernetes marks the Pod Ready condition as True.

These two milestones can be separated by probe intervals, timeouts, readiness gates, and control plane status updates.

### 5.1. Application readiness

The application can mark itself READY when:

- The JVM or process has resumed execution.
- Mandatory resources have been recreated.
- Essential dependencies are reachable.
- Critical caches have been refreshed or have a valid fallback.
- Admission gates are open.
- Request handlers can process requests according to policy.

Do not mark READY merely because the application context was created if a database or Redis is a mandatory dependency and is not yet connected.

Conversely, do not require every optional dependency to be available if the application can operate safely when they are temporarily unavailable.

### 5.2. Kubernetes Pod Ready

Kubernetes determines readiness based on container readiness, probes, and any configured readiness gates.

When the readiness probe succeeds, the Pod state transitions to Ready after kubelet updates the Pod condition. Therefore, Pod Ready time can lag behind when the application internally transitions to READY.

The Pod Ready metric is useful for managing rollouts, autoscaling, and Service endpoints. The application readiness metric is useful for analyzing initialization time inside the process.

### 5.3. Readiness Is Not Startup Time

An application may finish starting up without yet being ready to receive traffic. For example:

- The framework initialized, yet the database connection pool has not finished creating connections.
- The Redis client was created, yet has not authenticated.
- Caches already exist in the heap, yet require TTL/version validation.
- Message consumers have not been re-registered yet.
- Native resources have not been reopened yet.
- Critical warm-up has not completed yet.

Thus, application startup time is usually less than or equal to time to readiness when readiness encompasses additional steps. However, this depends on how milestones and the specific lifecycle are defined.

## 6. What Is First Response Time?

The phrase **first response time** can be interpreted in two ways. Distinguish them clearly to avoid mixing request latency with waiting time since startup.

### 6.1. First-request latency

First-request latency is the elapsed time from when the application receives the first request until the response for that request completes.

Let:

- T6: timestamp when the request arrives.
- T7: timestamp when the response completes.

Then:

\[
L_{\text{first-request}} = T7 - T6
\]

This metric reflects the cost of processing the first request, which may include:

- Routing and filters.
- Deserialization.
- Missing JIT compilation.
- Lazy initialization.
- Cache misses.
- On-demand dependency connections triggered by the request.
- Business logic.
- Serialization.
- Sending the response.

This is the latency of one specific request.

### 6.2. Time to first successful response

Time to first successful response measures from the startup or restore milestone until the application returns its first successful response.

Let:

- T0: measurement starting milestone.
- T7: first successful response.

Then:

\[
T_{\text{first-response}} = T7 - T0
\]

This metric includes startup time, readiness, and the wait time before the first request is dispatched to the application.

If the request is sent only after Pod Ready, this can be decomposed as:

\[
T_{\text{first-response}} =
T_{\text{ready}} + T_{\text{wait-for-request}} + L_{\text{first-request}}
\]

Where all components are measured from the same milestone T0 and follow consistent definitions.

### 6.3. Example Distinguishing the Two Metrics

Suppose:

- The Pod starts restoring at 10:00:00.000.
- Application Ready occurs at 10:00:00.700.
- Kubernetes Pod Ready occurs at 10:00:01.100.
- The load balancer sends the first request at 10:00:01.300.
- The response completes at 10:00:01.420.

Then:

| Metric | Value |
|---|---|
| Restore-to-application-ready | 700 ms |
| Restore-to-Pod-Ready | 1,100 ms |
| First-request latency | 120 ms |
| Restore-to-first-successful-response | 1,420 ms |

First-request latency is only 120 ms. However, the system required 1,420 ms from restore start until the first successful response.

Both numbers are useful and should not replace each other.

## 7. Formulas to Use

Assuming timestamps are synchronized against a single clock source:

| Metric | Formula |
|---|---|
| JVM startup | T1 − T0_process |
| Application startup | T2 − T1 |
| CRaC restore duration | T_process_resumed − T_restore_start |
| Post-restore initialization | T3 − T_process_resumed |
| Application time to ready | T4 − T_restore_start |
| Kubernetes time to Ready | T5 − T_pod_created |
| First-request latency | T_response − T_request |
| Time to first successful response | T_first_success − T_restore_start |
| Post-ready first response | T_first_success − T_app_ready |

Formulas are meaningful only when milestones are consistently defined. Do not subtract timestamps from two different clocks or two unsynchronized machines without accounting for clock skew.

### 7.1. Time Decomposition

A useful approach is to break time to ready into parts:

\[
T_{\text{ready}} =
T_{\text{restore}} +
T_{\text{resource-init}} +
T_{\text{cache-warmup}} +
T_{\text{readiness-overhead}}
\]

This is a simplified decomposition model. In practice, some steps may execute in parallel, so total elapsed time does not necessarily equal the sum of all task durations. When tasks run concurrently, measure the critical path.

For example, database connection takes 300 ms and Redis connection takes 250 ms. If run in parallel, the connection phase may take roughly 300 ms plus overhead rather than 550 ms.

## 8. Defining Measurement Points in a Java Application

For intervals within a single running process, use System.nanoTime() to measure duration. nanoTime is suited for measuring elapsed time because it does not depend on system wall-clock adjustments.

Do not use System.currentTimeMillis() to measure short durations if the system clock might be adjusted. Instant or wall-clock timestamps are suitable for recording calendar-time events and correlating logs, whereas internal benchmark durations should use a monotonic clock.

### 8.1. Simple Duration Timer

~~~java
import java.util.concurrent.TimeUnit;

public final class StartupTimer {

    private final long startedAtNanos = System.nanoTime();

    public long elapsedMillis() {
        return TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - startedAtNanos
        );
    }
}
~~~

Create the timer at the start milestone you want to measure and read it when the end milestone occurs.

Example:

~~~java
StartupTimer timer = new StartupTimer();

initializeFramework();
initializeRequiredClients();

long startupMillis = timer.elapsedMillis();
System.out.println("startup_ms=" + startupMillis);
~~~

This is only an example within the same execution run. Never use a nanoTime value captured before checkpointing to calculate a duration spanning the period while the process was stopped or across different runs. For milestones spanning across restore, use timestamps from the restore controller or an external measurement system.

### 8.2. Recording Timestamps and Durations Separately

You can record both wall-clock timestamps and monotonic durations:

~~~java
import java.time.Instant;

public final class StartupEvent {

    private final Instant occurredAt = Instant.now();
    private final long occurredAtNanos = System.nanoTime();

    public Instant occurredAt() {
        return occurredAt;
    }

    public long elapsedSince(StartupEvent start) {
        return (occurredAtNanos - start.occurredAtNanos) / 1_000_000;
    }
}
~~~

Timestamps help correlate logs and traces. Durations are used to compare milestones within the same process. For restore, the start milestone from an external controller must be propagated or recorded alongside a correlation ID and a clear clock source.

## 9. Measuring Application Readiness in Spring Boot

Spring Boot provides ApplicationReadyEvent to signal that the application has completed startup according to the framework lifecycle.

Example recording elapsed time from when the process starts running until ApplicationReadyEvent:

~~~java
import java.lang.management.ManagementFactory;
import java.time.Instant;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationReadyMetrics {

    private final long processStartedAtNanos = System.nanoTime();

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        long elapsedMillis =
                (System.nanoTime() - processStartedAtNanos) / 1_000_000;

        System.out.println(
            "application_ready"
            + " elapsed_ms=" + elapsedMillis
            + " event_time=" + Instant.now()
        );
    }
}
~~~

This example measures from when Spring instantiates the bean until the event is published. It excludes time before bean creation and does not automatically represent Kubernetes Pod Ready.

If you need to measure from process creation, record a timestamp earlier in the entry point or use container runtime metrics. If you need to measure post-restore readiness, place dedicated milestones inside the CRaC lifecycle.

### 9.1. ApplicationReadyEvent Does Not Always Equal Business Readiness

Some applications must perform additional work after ApplicationReadyEvent:

- Refresh caches.
- Initialize subscriptions.
- Wait for consumer assignments.
- Verify access permissions.
- Warm up critical endpoints.

In that case, maintain a separate readiness state and transition to READY only after business conditions have finished.

## 10. Measuring CRaC Phases Using Resource

You can record callback milestones before checkpoint and after restore. The example below illustrates a resource managing timing state during a restore.

~~~java
import java.time.Instant;
import java.util.concurrent.TimeUnit;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RestoreTimingResource implements Resource {

    private volatile long afterRestoreStartedNanos;
    private volatile Instant afterRestoreStartedAt;

    public RestoreTimingResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {

        System.out.println(
            "before_checkpoint_at=" + Instant.now()
        );
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        afterRestoreStartedNanos = System.nanoTime();
        afterRestoreStartedAt = Instant.now();

        recreateRequiredResources();
        verifyDependencies();

        long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - afterRestoreStartedNanos
        );

        System.out.println(
            "after_restore_initialization_ms=" + elapsedMillis
            + " started_at=" + afterRestoreStartedAt
            + " completed_at=" + Instant.now()
        );
    }

    private void recreateRequiredResources() throws Exception {
        // Recreate database, Redis and other required resources.
    }

    private void verifyDependencies() throws Exception {
        // Verify the dependencies required before readiness.
    }
}
~~~

In the example, duration is measured inside the afterRestore callback. It reflects the work from when the callback starts until the two illustrative steps finish. It excludes the restore duration prior to the callback or probe delay after the callback.

In production, emit separate metrics for each dependency to identify which step consumes time. Do not log only an aggregate duration if you need to optimize.

## 11. Measuring Kubernetes Pod Ready Time

At the Kubernetes level, Pod conditions and container statuses can be used to analyze timings.

Useful milestones:

- metadata.creationTimestamp: when the Pod object was created.
- PodScheduled condition: when the Pod was assigned a node by the scheduler.
- container state running.startedAt: when the container started running per container status.
- ContainersReady condition: containers are ready.
- Ready condition: the Pod is ready according to readiness probes and readiness gates.

These can be inspected using:

~~~bash
kubectl get pod orders-api-abc123 -o yaml
kubectl describe pod orders-api-abc123
~~~

To measure automatically, a controller or script can read condition timestamps and compute durations. Preserve raw milestones so data can be re-analyzed if metric definitions change.

### 11.1. Pod Ready Time Includes Many Overheads

If Pod creation timestamp is used as T0 and the Ready condition as T1, the metric includes:

- Scheduling delay.
- Image pull.
- Volume mount.
- Container startup.
- CRaC restore.
- Application resource initialization.
- Startup/readiness probes.
- Readiness gates.

This is a good metric for evaluating rollout experience at the platform level, but it is not an isolated measurement of the JVM or CRaC.

### 11.2. Probe Intervals Introduce Observation Delay

Suppose the application internally transitions to READY at 10:00:00.100, while the readiness probe runs every 5 seconds. Kubelet may only observe the passing state at the next probe execution.

Therefore, Pod Ready time can lag behind application readiness time. To reduce observation delay, you can adjust periodSeconds, though overly frequent probes also add extra requests and load to the application.

### 11.3. Readiness Gates

If the Pod uses a readiness gate, the Pod Ready condition becomes True only when the additional conditions are also satisfied. This is useful when a restore controller needs to grant a restore budget or verify a fleet-level dependency.

Record separately when the application becomes ready and when the external gate opens to pinpoint which component causes delay.

## 12. Measuring First-Request Latency

First-request latency should be measured from when the request actually reaches the application until the response finishes.

Do not use the client's send timestamp and receive timestamp as application latency if the goal is to measure server-side processing alone. Those timestamps also encompass networking, load balancers, service meshes, and client scheduling.

Distinguish between:

| Scope | Start | End |
|---|---|---|
| Client-observed latency | Client sends request | Client receives response |
| Gateway latency | Gateway receives request | Gateway sends response |
| Server processing time | Server receives request | Server completes processing |
| Dependency latency | Call sent to dependency | Result received |
| First-request latency | Server receives first request | Server completes first response |

If the goal is user experience, client-observed latency is usually most important. If the goal is analyzing JIT or lazy initialization, server processing time and trace spans may be more informative.

### 12.1. Using a Micrometer Timer

Request processing time can be recorded using Micrometer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

import java.io.IOException;

public final class RequestTimingFilter implements Filter {

    private final Timer requestTimer;

    public RequestTimingFilter(MeterRegistry registry) {
        this.requestTimer = Timer.builder("http.server.request.duration")
                .tag("scope", "application")
                .register(registry);
    }

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, jakarta.servlet.ServletException {

        Timer.Sample sample = Timer.start();

        try {
            chain.doFilter(request, response);
        } finally {
            sample.stop(requestTimer);
        }
    }
}
~~~

This is an illustrative example for a servlet stack. Reactive frameworks require instrumentation suited to the reactive lifecycle and should not use synchronous filters as shown above.

The metric above measures request processing time through the filter. To identify the first request, add a mechanism to recognize the first successful request per process or Pod UID.

### 12.2. Defining a Successful Response

Agree on which responses qualify as successful:

- HTTP 2xx.
- HTTP 2xx or 3xx.
- A valid business response.
- A non-transient-error response.
- A response from a specific functional check endpoint.

An HTTP 200 from a health endpoint does not prove the primary business path is operational. To measure actual serving capability, use a representative, side-effect-free smoke test request.

## 13. Measuring Time to First Successful Response Externally

An external synthetic client or test harness can:

1. Record the restore start or Pod creation timestamp.
2. Watch for Pod Ready.
3. Send test requests at a defined cadence.
4. Record the timestamp of the first request.
5. Record the timestamp of the first successful response.
6. Record that request's latency.
7. Capture errors prior to the first successful response.

External measurement has the advantage of observing the experience from the client or platform perspective instead of relying solely on internal process logs.

Example data:

| Event | Timestamp |
|---|---|
| Restore requested | 10:00:00.000 |
| Process resumed | 10:00:00.180 |
| Application ready | 10:00:00.700 |
| Pod Ready | 10:00:01.100 |
| First request sent | 10:00:01.300 |
| First response received | 10:00:01.420 |

From this data, you can independently compute restore duration, readiness delay, first-request latency, and time to first response.

### 13.1. Avoid Bursting Requests While Waiting

Synthetic probes should not poll continuously at an excessively high rate. If 100 Pods restore simultaneously and each probe sends a request every 100 ms, the measurement itself can overload the system.

Use a reasonable polling interval, jitter across clients, and Kubernetes readiness signals. Document the probe frequency in the benchmark.

### 13.2. Record Errors Before the First Response Too

If the first request returns 503 and the second returns 200, record both:

- First attempt latency.
- First successful response latency.
- Number of failures before success.
- Elapsed time from the first attempt to success.

Recording only the first 200 response can hide the window during which the system was unable to serve requests.

## 14. Comparing Cold Start and CRaC Restore

To evaluate CRaC, compare both workflows using the same application and environmental conditions.

### 14.1. Cold start

Cold start typically includes:

- Creating the container/process.
- Starting the JVM.
- Initializing the framework.
- Creating resources.
- Warming up if the application performs warm-up at startup.
- Transitioning to READY.
- Handling the first request.

### 14.2. CRaC restore

The restore path typically includes:

- Initializing the restore environment.
- Restoring the process from the checkpoint.
- Running afterRestore callbacks.
- Recreating or validating resources.
- Refreshing required caches.
- Transitioning to READY.
- Handling the first request.

~~~mermaid
flowchart LR
    subgraph Cold["Cold start"]
        A["Process start"] --> B["JVM startup"]
        B --> C["Framework initialization"]
        C --> D["Resource initialization"]
        D --> E["Ready"]
        E --> F["First request"]
    end
    subgraph Restore["CRaC restore"]
        G["Restore requested"] --> H["Process restored"]
        H --> I["afterRestore"]
        I --> J["Resource recreation"]
        J --> K["Ready"]
        K --> L["First request"]
    end
~~~

Do not conclude CRaC is better solely because process restore is faster. Compare time to readiness and time to first successful response, as those milestones reflect actual serving capability.

### 14.3. Comparing Under Identical Conditions

Keep the following factors consistent:

- Same application version.
- Same JDK distribution and build.
- Same JVM flags.
- Same CPU and memory limits.
- Same node pool or machine type.
- Same dependency endpoints.
- Same cache configuration and data.
- Same warm-up workload.
- Same readiness probe.
- Same first request and payload.

If restore uses a pre-warmed cache while cold start uses an empty cache, results conflate checkpoint benefits with cache benefits. Decide which cache state is part of the strategy and document it explicitly in the benchmark.

## 15. Percentiles and Time Distributions

Do not report only average startup time. Some restores can be slow due to scheduling, node contention, DNS, dependency failover, or image pulls.

Report:

- Minimum and maximum to understand the range.
- Median or p50 to describe a typical run.
- p90/p95 to evaluate the majority of runs.
- p99 when sample size is large enough and tail latency matters.
- Error rate or count of runs failing to reach readiness.

Illustrative example:

| Metric | Cold start p50 | CRaC restore p50 | Cold start p95 | CRaC restore p95 |
|---|---:|---:|---:|---:|
| Process start to app ready | 4.2 s | 0.8 s | 6.1 s | 1.4 s |
| Pod creation to Pod Ready | 7.5 s | 2.1 s | 11.0 s | 4.0 s |
| First-request latency | 310 ms | 140 ms | 650 ms | 290 ms |
| Time to first successful response | 7.9 s | 2.3 s | 11.6 s | 4.3 s |

These figures only illustrate presentation format and are not CRaC benchmarks or default targets.

### 15.1. Sample Size and Stability

A handful of runs is not enough to conclude p95 or p99. Gather sufficient samples, control for outliers, and record environmental conditions.

If a test has only 10 restores, p99 has virtually no statistical significance. Always report sample size alongside percentiles.

### 15.2. Grouping Results

Separate results by:

- Node or node pool.
- JDK version.
- Cold start vs. restore.
- Checkpoint version.
- Healthy vs. degraded dependencies.
- Warm vs. cold cache.
- New Pod vs. restarted Pod.
- Single Pod vs. fleet restore.

Mixing all cases together can let fast runs mask a slow group of restores.

## 16. Factors That Skew Measurements

### 16.1. Probe Interval and Readiness Delay

If the readiness probe runs every 10 seconds, Pod Ready time can be quantized to the probe interval. The actual time until the application is ready may be much shorter.

### 16.2. Image Pull and Node Cache

A run on a node that already cached the image can be faster than one that must pull the image. If the goal is to evaluate CRaC, measure image pull separately or enforce identical conditions.

### 16.3. Dependency Cache and Connection Reuse

Databases, Redis, and DNS may maintain their own caches. Subsequent runs can appear faster because dependency-side connections or caches are already warm, not because of the checkpoint.

### 16.4. JIT and Request Payloads

The first request can trigger JIT compilation or lazy initialization. Different payloads may exercise different code paths. Always use identical payloads and endpoints.

### 16.5. Background activity

Schedulers, telemetry exporters, cache refreshes, or consumer startups can compete for CPU and connections with the first request.

Record which background tasks are active and whether they affect the benchmark.

### 16.6. Clocks Across Multiple Machines

If T0 is recorded on the restore controller and T7 is recorded on a different client, clock skew can distort the duration. Use synchronized timestamps and estimate error bounds, or capture both milestones from the same observer.

## 17. Using Monotonic Clocks and Wall Clocks Properly

There are two common types of time sources:

**Wall clock** represents calendar time, such as Instant.now(). It is suitable for logging, timestamping events, and correlating across systems when clocks are synchronized.

**Monotonic clock** such as System.nanoTime() is suitable for measuring durations within the same process or clock domain. It is unaffected by system clock adjustments in the way a wall clock can be.

Do not:

- Subtract two nanoTime values obtained from two different processes.
- Compare nanoTime across two hosts.
- Keep a pre-checkpoint nanoTime value and assume it is a reliable baseline for computing duration across restore.
- Mix timestamps from client and server without identifying the clock source.

For time to first response across a restore, a more reliable approach is using an external observer with a stable clock to record both the start and end milestones. Inside the process, use nanoTime to measure internal segments after the process resumes execution.

## 18. Instrumentation and Metric Naming

Metrics should have clear names and consistent units. Example:

| Metric | Type | Unit |
|---|---|---|
| jvm_startup_duration | Histogram/Timer | seconds |
| application_startup_duration | Histogram/Timer | seconds |
| crac_restore_duration | Histogram/Timer | seconds |
| crac_after_restore_duration | Histogram/Timer | seconds |
| application_time_to_ready | Histogram/Timer | seconds |
| pod_creation_to_ready_duration | Histogram | seconds |
| first_request_duration | Histogram/Timer | seconds |
| time_to_first_successful_response | Histogram | seconds |
| startup_failure_total | Counter | count |
| restore_failure_total | Counter | count |
| readiness_transition_total | Counter | count |

Do not place high-cardinality values like Pod UID, request ID, or checkpoint ID into metric labels. Those IDs belong in logs or traces. Metrics should use bounded-cardinality labels such as application, version, startup_mode, or node_pool.

### 18.1. Distinguishing Counters, Gauges, and Histograms

- Counters count startup/restore failures.
- Gauges represent current state such as readiness or the number of connected dependencies.
- Histograms/Timers record duration distributions.

Do not use a single gauge to represent startup duration across runs, because values overwrite one another and hinder percentile analysis.

### 18.2. Correlation ID

Each restore should have a restore attempt ID. Attach this ID to logs for:

- Restore start.
- Process resumed.
- Resource initialization.
- Cache warm-up.
- Application ready.
- Pod ready.
- First request.
- First successful response.

This enables reconstructing a Pod's full timeline without putting the ID into every metric label.

## 19. Designing Health and Readiness Endpoints

An application can expose three distinct endpoints:

| Endpoint | Purpose | Condition |
|---|---|---|
| /health/startup | Basic initialization completed | Process and framework can make progress |
| /health/ready | Can accept traffic | Mandatory dependencies and admission gates are ready |
| /health/live | Process is alive | No deadlock or severe internal corruption |

Example Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 4
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: app
          image: registry.example.com/catalog-api:2026.11
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 3
            timeoutSeconds: 2
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

The probe paths are examples and must be implemented in the application. Startup probes allow extended startup sequences without premature restarts from the liveness probe. Readiness probes prevent the Pod from receiving traffic until ready. Liveness probes should reflect internal process health and should not fail merely because a database or Redis is temporarily slow.

## 20. Example Post-Restore Timeline Analysis

Suppose a Pod records these events:

| Event | Time Since Restore Start |
|---|---|
| Restore requested | 0 ms |
| Process resumed | 160 ms |
| afterRestore started | 170 ms |
| Database ready | 410 ms |
| Redis ready | 520 ms |
| Cache warm-up complete | 680 ms |
| Application readiness true | 710 ms |
| Kubernetes Pod Ready | 3,100 ms |
| First request received | 3,350 ms |
| First response completed | 3,470 ms |

From this timeline, we can conclude:

- Process restore is fast.
- Resource initialization and cache warm-up account for most of the internal post-restore time.
- The gap between application ready and Pod Ready lies primarily in probe/control-plane observation.
- First-request latency is 120 ms.
- Time to first successful response is 3,470 ms.

If the goal is to reduce time from restore to traffic, you can tune the readiness probe interval or readiness gate. If the goal is to reduce first-request latency, analyze request traces and lazy initialization.

Do not optimize the restore process when the actual bottleneck lies in cache warm-up or the probe interval.

## 21. Identifying Bottlenecks by Metric

| Observation | Likely Areas to Investigate |
|---|---|
| High JVM startup | JVM flags, classpath, class loading, runtime initialization |
| High application startup | Framework bean creation, configuration, startup hooks |
| High restore duration | Checkpoint size, storage I/O, CRIU and host compatibility |
| High afterRestore duration | Connection recreation, DNS, TLS, cache refresh |
| Fast application ready but slow Pod Ready | Probe interval, readiness gate, kubelet/control plane |
| Fast Pod Ready but slow first request | JIT, lazy init, cache miss, on-demand connections |
| Low first-request latency but high time to first response | Waiting for readiness, load balancer routing, or request scheduling |
| High p95 but low p50 | Node contention, dependency tail latency, retries, or scheduling |
| Unstable restore failures | Unrecovered resources, dependency timeouts, environment mismatches |

Stage-by-stage analysis helps target optimization accurately. A single aggregate number cannot explain root causes.

## 22. Benchmarking CRaC with a Repeatable Process

A benchmark can be conducted as follows:

### Step 1: Define Objectives

Examples:

- Reduce Pod creation-to-ready p95.
- Reduce restore-to-first-successful-response p95.
- Reduce first-request latency p95.
- Keep checkpoint size within limits.

Do not choose a vague objective like "faster startup" without measurable thresholds.

### Step 2: Standardize the Environment

Hold constant:

- Image digest.
- JDK build.
- JVM flags.
- CPU/memory limits.
- Node pool.
- Dependencies.
- Probe configuration.
- Workload and payload.
- Cache state.

### Step 3: Run the Cold-Start Baseline

Execute enough runs and collect startup, readiness, and first-response metrics. Record errors and environmental conditions.

### Step 4: Create the Checkpoint

Start the application, warm up using the defined workload, prepare resources, and create the checkpoint. Record checkpoint creation duration and image size separately.

### Step 5: Restore Multiple Times

Restore the same checkpoint under equivalent conditions. Record restore duration, afterRestore duration, application ready, Pod Ready, and first response.

### Step 6: Compare Percentiles

Compare p50, p95, and p99 when enough samples exist. Report total run counts and failed runs.

### Step 7: Test Tail Cases

Test under slow dependencies, stale caches, node contention, or concurrent multi-Pod restores. A solid checkpoint is not just fast in an ideal environment—it also exhibits clean recovery behavior when dependencies are slow.

## 23. Sample Benchmark Results Table

The table below illustrates how to organize a report:

| Metric | Cold start | CRaC restore | Difference |
|---|---:|---:|---:|
| Application startup p50 | 4.2 s | 0.8 s | -81.0% |
| Application time to ready p50 | 5.1 s | 1.2 s | -76.5% |
| Pod creation to Ready p50 | 7.5 s | 2.1 s | -72.0% |
| First-request latency p50 | 310 ms | 140 ms | -54.8% |
| Time to first response p50 | 7.9 s | 2.3 s | -70.9% |
| First-request latency p95 | 650 ms | 290 ms | -55.4% |

These figures are illustrative examples only. Do not treat them as performance guarantees or expectations for every application. Actual results depend on workload, JDK, checkpoint, dependencies, host, and metric definitions.

### 23.1. Calculating Percentage Improvement

This can be calculated as:

\[
\text{Improvement} =
\frac{T_{\text{baseline}} - T_{\text{new}}}
{T_{\text{baseline}}} \times 100\%
\]

For example, with a 5-second baseline and 1-second restore:

\[
\frac{5 - 1}{5} \times 100\% = 80\%
\]

Always report both absolute values and percentages. Dropping from 100 ms to 50 ms and from 10 seconds to 5 seconds are both 50%, yet their product impact differs.

## 24. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| Calling every metric startup time | Unclear measurement scope | Name metrics by start/end events |
| Using restore duration as time to ready | Omits callbacks and readiness | Measure phases separately |
| Using first-request latency as time to first response | Omits pre-request waiting time | Record both request and response timestamps |
| Measuring only inside the JVM | Misses scheduling, image pull, and probes | Add Kubernetes/client-side observers |
| Measuring only from Pod creation | Mixes platform cost with JVM cost | Keep container/process/restore milestones |
| Reporting only averages | Hides tail latency | Report p50/p95/p99 and sample count |
| Using wall clock for internal durations | Clock may be adjusted | Use a monotonic clock |
| Subtracting nanoTime across two processes | Not in the same clock domain | Use an external observer or synchronized timestamps |
| Ignoring initial failed requests | Overly optimistic evaluation | Record attempts and first successful response |
| Comparing warm cache against cold cache | Mixes multiple variables | Standardize or group by cache state |
| Benchmarking only a single Pod | Misses dependency storms | Test fleet-wide restores too |
| Making health checks excessively heavy | Measurement creates extra load | Use readiness state and lightweight probes |

## 25. Definition and Measurement Checklist

### Metric Definitions

- [ ] Clear starting milestone for each metric.
- [ ] Clear ending milestone for each metric.
- [ ] Distinguish JVM startup, application startup, and Pod startup.
- [ ] Distinguish CRaC restore duration from time to readiness.
- [ ] Distinguish application Ready from Kubernetes Pod Ready.
- [ ] Distinguish first-request latency from time to first successful response.

### Instrumentation

- [ ] Use System.nanoTime() for durations within the same process.
- [ ] Use wall-clock timestamps to record events and correlate logs.
- [ ] Never compute durations across restore using a pre-checkpoint nanoTime.
- [ ] Include a restore attempt ID or correlation ID.
- [ ] Emit separate metrics for resource initialization and cache warm-up.
- [ ] Have an external observer to measure Pod Ready and first response.

### Benchmark

- [ ] Cold start and CRaC restore use identical conditions.
- [ ] Image digest and JDK build are recorded.
- [ ] CPU, memory, dependencies, and payloads are standardized.
- [ ] Sufficient samples exist for reported percentiles.
- [ ] Errors and failed responses before success are recorded.
- [ ] Both single-Pod and multi-Pod restores are tested.
- [ ] Checkpoint creation duration and image size are recorded separately.

### Interpretation

- [ ] Report p50/p95/p99 when sufficient data exists.
- [ ] Analyze bottlenecks stage by stage.
- [ ] Do not draw conclusions from a single aggregate startup figure.
- [ ] Explicitly note whether metrics were measured at process, Pod, or client level.
- [ ] Document environmental conditions and clock accuracy bounds.

## 26. Frequently Asked Questions

### How do startup time and time to readiness differ?

Startup time measures the time to complete a defined initialization phase, typically JVM or application startup. Time to readiness measures from the starting milestone until the application or Pod can receive traffic. Readiness may require additional dependency connections, cache warm-up, and probe checks.

### Is restore duration the time until the application is ready?

No. Restore duration typically measures only the process recovery phase. The application may still need to execute afterRestore callbacks, recreate resources, refresh caches, and wait for the readiness probe.

### Is ApplicationReadyEvent equivalent to Kubernetes Pod Ready?

No. ApplicationReadyEvent is a Spring Boot event. Kubernetes Pod Ready also depends on the readiness probe, container readiness, and readiness gates. The application may also enforce additional business conditions after the event.

### Is first-request latency the same as time to first response?

No. First-request latency measures from when the first request arrives until the response completes. Time to first successful response measures from the startup/restore milestone until the first successful response, thus encompassing both startup time and waiting for the request.

### Should System.nanoTime() or Instant.now() be used?

Use nanoTime to measure durations within the same process. Use Instant or wall-clock timestamps to record event timestamps and correlate logs. For intervals spanning across a checkpoint or across multiple machines, use an external observer and synchronized clocks instead of subtracting nanoTime values from two environments.

### Should requests be sent immediately after restore to measure first response?

Yes, if the request is designed safely and the measurement defines milestones clearly. Send it through the intended routing path without causing side effects, and record errors prior to the first successful response as well.

### Why is Pod Ready fast yet the first request is still slow?

There may still be JIT compilation, lazy initialization, cache misses, on-demand dependency connections, or unwarmed code paths. Measure first-request latency and traces to pinpoint where the cost lies.

### Why is application Ready fast yet Pod Ready is slow?

The readiness probe may not have reached its next execution yet, a readiness gate may not be open, or kubelet/the control plane may not have updated the Pod condition yet. Compare the application readiness timestamp against the Pod Ready condition timestamp.

### Which metric should be optimized first?

Choose based on product goals. If rollouts are slow, prioritize Pod creation-to-ready. If internal application restore takes too long, analyze restore and afterRestore durations. If users experience slow first requests, optimize first-request latency. If you need the end-to-end experience from initialization to response, measure time to first successful response.

### Can cold start and restore be compared directly?

Yes, provided equivalent start/end events are defined and the environment is standardized. Report platform, restore, readiness, and request latency separately to avoid comparing mismatched scopes.

## Conclusion

Startup time, time to readiness, and first response time describe three distinct facets of application initialization experience. Startup time measures an initialization phase; time to readiness measures when an application or Pod can accept traffic; first-request latency measures processing duration for the first request; time to first successful response measures from the start until the first successful response.

With CRaC, separate restore duration from afterRestore initialization and Kubernetes readiness. Clearly document start/end milestones, use a monotonic clock for in-process durations, use an external observer for milestones spanning restore, and report percentiles alongside benchmark conditions. With a complete timeline, the engineering team knows whether slowness sits in the JVM, framework, resources, caches, probes, or the first request, and can optimize the exact bottleneck stage.
