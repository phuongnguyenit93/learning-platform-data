# Measuring Before Resizing Thread Pools or Executors

## 1. Why shouldn't you just “add threads” when an app is slow?

In a Spring Boot application, rising response times can stem from CPU, databases, external APIs, networking, garbage collection, queues, or how tasks are dispatched to threads. If you simply see slow requests and raise `server.tomcat.threads.max` or `spring.task.execution.pool.max-size`, you can make the system **even slower** by increasing CPU contention, memory pressure, database connections, or overloading a downstream dependency.

**Core principle of this lesson:** measure **traffic rate → wait time → execution time → resource utilization → queues/rejections**, and only then form a hypothesis and change **one parameter** under comparable load. The goal is meeting SLOs with appropriate resources and stability, not maximizing thread count.

After this lesson, you will be able to:
- Identify the exact thread pool/executor handling a request or task.
- Select baseline metrics to tell whether the system lacks capacity, is bottlenecked externally, or is measuring the wrong target.
- Record baselines and interpret p95/p99, throughput, queue wait, saturation, rejections, and CPU/GC.
- Estimate concurrency using Little's Law and understand the limits of sizing formulas.
- Run before/after experiments and decide whether to increase, decrease, or keep pool sizes unchanged.
- Distinguish Servlet/Tomcat pools, `@Async`/`ThreadPoolTaskExecutor`, `@Scheduled`, WebFlux, and virtual threads.

> **Scope:** concepts apply to Java 17+ and Spring Boot web-runtime. Standalone Java examples use Java 17. Actuator and pool configurations illustrate Spring Boot 3.5/4.x with platform threads; verify the exact version and server type in your project before applying.

## 2. Find the right pool before optimizing

Within a single Spring Boot service, multiple independent thread pools and bounded resources can coexist. They do not share a single global “maxThreads.”

| Component | Primary responsibility | What to measure | Knob to adjust if truly the bottleneck |
|---|---|---|---|
| **Tomcat/Jetty request workers** in Spring MVC | Execute requests through the Servlet stack | Busy/max threads, request latency, waiting, HTTP errors, CPU | Embedded server properties, e.g. `server.tomcat.threads.max` |
| **`ThreadPoolTaskExecutor` / `@Async`** | Run tasks submitted to an executor (can also serve MVC async) | Active/pool size, queue depth, queue wait, run duration, rejections | `corePoolSize`, `maxPoolSize`, `queueCapacity`, policy |
| **`ThreadPoolTaskScheduler` / `@Scheduled`** | Trigger scheduled jobs | Lateness, overlapping tasks, execution time, missed tasks | Scheduler size and scheduling mode |
| **Reactor Netty event loops / WebFlux** | Handle non-blocking I/O and callbacks on event loops | Event-loop lag, latency, blocked tasks, CPU; bounded queues involved | Remove blocking operations, offload blocking work to a suitable scheduler; tune event loops only with evidence |
| **Reactor `boundedElastic` / custom Scheduler** | Isolate blocking tasks in reactive apps | Running/waiting tasks, queues, wait times, rejections | Bound scheduler concurrency and upstream arrival rate |
| **HikariCP / JDBC connections** | Lease database connections; **not** a Java thread pool | Active, idle, pending, acquisition time, DB utilization | Optimize SQL/transactions, limit concurrency, tune DB pool with evidence |
| **Message consumer workers** | Process messages from Kafka/RabbitMQ or queues | Consumer lag, time per message, retries, DLQ, partitions/concurrency | Consumer concurrency, backpressure, dependency throughput |

**Wrong-target example:** an MVC request receives a call, invokes `@Async("reportExecutor")`, and blocks on `CompletableFuture.join()`. If `reportExecutor` has a deep queue, increasing Tomcat workers will not make `reportExecutor` finish faster; it may even tie up more Tomcat threads waiting. Locate the **actual** waiting point in traces/thread dumps and **`reportExecutor`** metrics.

**Another example:** a WebFlux app runs on Reactor Netty, yet handler code calls synchronous JDBC directly on the event loop. Configuring `spring.task.execution.pool.max-size` will not fix it unless that code actually runs on Boot's task executor. The first step is identifying blocking calls on the event loop and isolating or removing them.

### How to identify which pool is actually in use

1. Check logs and application context for stack type: Spring MVC/Servlet vs. WebFlux/Reactive; actual server Tomcat, Jetty, or Netty.
2. For `@Async`, check whether the annotation specifies a bean name (`@Async("someExecutor")`), `AsyncConfigurer`, executor beans, and auto-configuration.
3. For `@Scheduled`, inspect the active scheduler and schedule type (`fixedDelay`, `fixedRate`, cron); never blame scheduler delays on the web request pool.
4. For custom `ExecutorService` instances, inspect where beans or pools are instantiated and their shutdown policies.
5. Cross-check **pool names** in metrics against **thread names** in Java Flight Recorder (JFR)/thread dumps. Never judge solely from total JVM thread count.

## 3. Minimum metrics before changing anything

Measure values over identical intervals, app versions, replica counts, load profiles, and dependency configurations.

| Category | Metrics / interpretation | Question to answer |
|---|---|---|
| **Traffic rate** | Requested/accepted/completed requests per second (RPS), tasks/s | Are incoming load and completed load diverging? |
| **Latency** | p50, p95, p99; split HTTP response time, queue wait, execution time, downstream wait | Where are users waiting, and is tail latency rising? |
| **Pool capacity** | `poolSize`, `corePoolSize`, `maxPoolSize`, `activeCount`, active/max over time | Is the pool actually saturated or over-provisioned? |
| **Queueing** | Queue size/capacity, queue wait p95/p99, queue growth/drain rate, oldest task age | How long are tasks waiting, and can the queue recover? |
| **Rejections & errors** | Rejected tasks/s, timeouts, caller-runs, dropped tasks, HTTP 429/503/5xx | Which limit is breaking? Are tasks lost or propagating slowness? |
| **CPU, memory, GC** | Container/host CPU %, quota/throttling, heap, live threads, GC pauses, allocation | Does adding threads cause CPU or GC contention? |
| **Downstream** | DB active/pending, connection acquisition time, SQL duration, external API p95, rate limits | Are threads just waiting on another resource? |
| **Stability** | Error rate, retry rate, per-replica saturation, cold/warm start | Do average gains come at the cost of worse tails or errors? |

Distinguish numbers that are easily confused:

- **Active threads** is the count executing tasks at the sample instant; **pool size** is created threads; **max pool size** is the configured ceiling. A pool of 40 threads with 8 active does not prove you can safely shrink to 8, since peak bursts may be larger.
- **Queue depth** is waiting task count at an instant; **queue wait time** is how long a task waits from submission until execution starts. Low queue depth does not guarantee good p99 queue wait, especially under micro-bursts.
- **Completed throughput** differs from **submission rate**. A system can receive 120 tasks/second while completing 90 tasks/second, growing the queue by ~30 tasks/second briefly. Sustained mismatch hits queue or resource limits.
- **p95/p99** are percentiles, not averages. `p99=800ms` means roughly 99% of samples in that window did not exceed 800ms; comparisons require adequate sample sizes, matching intervals, and identical aggregation methods.
- **Saturation** is not simply high thread counts: combine active/max, wait times, rejections, and stability under rising load.
- **`RejectedExecutionException`** from `ThreadPoolExecutor` and **`TaskRejectedException`** in Spring can surface at different layers; policies like `CallerRunsPolicy` push back onto calling threads without necessarily incrementing error counters.

**An essential metric often missing:** wait time **inside the executor queue**. HTTP latency and total task duration can hide how long a task waited before starting. For custom executors, record submission timestamps before `execute/submit`, measure at the start of the executed `Runnable`, and count rejections/timeouts. Tag by pool name, avoiding high-cardinality tags like request ID or user ID.

## 4. Collecting metrics in Spring Boot with Actuator + Micrometer

Depending on version, Spring Boot Actuator auto-instruments JVM, system, HTTP, connection pool, and eligible `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` beans. **Check actual metric names** via `/actuator/metrics`; never guess metric names from bean names or Prometheus formatting.

### 4.1. Enabling metrics in a test environment

The Gradle snippet below is a **fragment** for a Spring Boot project already configured with plugins and repositories:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Example `application.yml` for a test environment with protected management endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true

server:
  tomcat:
    mbeanregistry:
      enabled: true
~~~

In this example:
- `/actuator/metrics` aids **live diagnostics**; it does not replace a production time-series store.
- `/actuator/prometheus` exposes metrics for Prometheus when the registry is present.
- Histograms on `http.server.requests` enable aggregating latency quantiles across multiple instances. Configure buckets and cardinality bounds appropriately for production.
- `server.tomcat.mbeanregistry.enabled=true` only applies when using **Tomcat**; Boot docs note Tomcat metrics require the MBean registry. For Jetty/Netty, use your server's metrics.
- Keep management endpoints on trusted networks or protected by security policies. Never expose diagnostic endpoints openly on the Internet.

### 4.2. Inspecting available meters

After starting the app and driving some requests/tasks:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/http.server.requests
curl -s http://localhost:8080/actuator/metrics/jvm.threads.live
curl -s http://localhost:8080/actuator/prometheus
~~~

These commands **work only when the app exposes these endpoints on port 8080**. Actual outputs vary with workload, container, version, and tags; there is no fixed stdout. A missing meter may be due to dependencies, auto-configuration, unexposed endpoints, zero traffic yet, or uninstrumented executor/server types; **do not treat “missing” as 0**.

Metric groups to look for:
- `http.server.requests`: request counts, latency, method/URI-template/status tags when present.
- `jvm.threads.*`, `jvm.gc.*`, `process.cpu.*`, and `system.cpu.*`: JVM and host health.
- `executor.*`: eligible `ThreadPoolTaskExecutor` and `ThreadPoolTaskScheduler` beans expose pool/queue/task metrics tagged by executor name depending on instrumentation.
- `tomcat.*` when using Tomcat with MBean registry; busy worker count and configured max are key signals.
- `hikaricp.*` or `jdbc.connections.*` when using a datasource/HikariCP; monitor these alongside thread pools whenever DB access is involved.

Dotted names above are **Micrometer/Actuator** names; Prometheus converts them to snake_case with unit suffixes. Do not paste a Prometheus metric name verbatim into `/actuator/metrics/{name}`.

### 4.3. Time-series dashboards and reference queries

Prometheus stores time series; counters need `rate(...)` or `increase(...)`, and histogram quantiles need published buckets. Example queries for the default HTTP timer (adjust selectors/tags to match your series):

~~~promql
sum(rate(http_server_requests_seconds_count[5m]))
~~~

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (rate(http_server_requests_seconds_bucket[5m]))
)
~~~

These two queries estimate request/s and p95 from histograms **over a 5-minute window**. To measure specific endpoints or apps, add verified selectors. In Prometheus, histograms do not exist unless histogram emission is enabled and series have arrived; never infer `p95=0` from an empty query result.

**A minimal dashboard** puts 4 panels on a shared time axis: RPS, p95/p99 + error rate, executor active/queue/reject, and CPU + DB pending/GC. Annotate deployments and config changes on the timeline. Inspecting charts in isolation misses time offsets between arrivals, queueing, and latency spikes.

## 5. Java 17 lab — seeing why max threads cannot fix an unbounded queue

`ThreadPoolExecutor` follows a specific task-acceptance order:
1. If fewer than `corePoolSize` workers exist, create a new worker.
2. Once core size is reached, prefer placing the task in the queue if space remains.
3. Only when the queue is full does it try creating workers up to `maximumPoolSize`.
4. If neither queueing nor creating workers is possible, invoke `RejectedExecutionHandler`.

Consequently, an **unbounded queue** normally prevents `maximumPoolSize` from **ever taking effect**. That is why people raise `max-size` yet see `active` stay flat while latency climbs.

The standalone example below uses a **queue capacity of 2** so the behavior is visible. Save with exact filename `SaturationDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class SaturationDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2,                          // corePoolSize
                4,                          // maximumPoolSize
                30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy()
        );

        Runnable blockedTask = () -> {
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        int accepted = 0;
        int rejected = 0;
        try {
            for (int i = 0; i < 8; i++) {
                try {
                    pool.execute(blockedTask);
                    accepted++;
                } catch (RejectedExecutionException e) {
                    rejected++;
                }
            }
            System.out.printf(
                    "accepted=%d rejected=%d%n", accepted, rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac SaturationDemo.java
java SaturationDemo
~~~

Expected stdout:

~~~text
accepted=6 rejected=2
~~~

**Why this output?** During submission, running tasks block on the latch; the pool cannot finish them before the latch releases. The first two tasks use core workers, the next two fill the queue, the next two expand the pool from 2 to 4 workers, and the final two are rejected because the pool is at max and the queue is full. After printing counts, `finally` releases the latch and shuts down cleanly.

This is a **mechanism demonstration**, not a throughput benchmark or evidence for picking pool size 4 in real apps. In particular, sampling `activeCount()` once is noisy due to scheduling; real evaluations require time-series sampling, load tests, and realistic task durations.

### Relating back to Spring

`ThreadPoolTaskExecutor` wraps `ThreadPoolExecutor`. In Boot apps using **platform threads**, `spring.task.execution.pool.core-size`, `max-size`, and `queue-capacity` configure the auto-configured executor. Example **candidate only to test after measuring**, not a universal recommendation:

~~~yaml
spring:
  task:
    execution:
      pool:
        core-size: 8
        max-size: 24
        queue-capacity: 100
        keep-alive: 30s
~~~

A custom `ThreadPoolTaskExecutor` bean can override settings, and `@Async("namedExecutor")` may bypass the auto-configured executor. Always confirm which bean runs the tasks you want to tune.

## 6. Recording comparable baselines

Capture a baseline **before changing** any limit. A solid measurement run records:

| What to record | Why |
|---|---|
| JDK version, Spring Boot version, image/build, commit, current pool config | Avoid comparing different releases or algorithms |
| Instance/pod count, CPU quota, RAM limit, available vCPUs | Identical pool sizes behave differently under different hardware budgets |
| Server type, pool/executor type, rejection policy, queue capacity | Know the exact limits under evaluation |
| Endpoint/message mix, read/write ratio, payload sizes, cache hit rate | Different workloads need different concurrency |
| Incoming RPS vs. completed RPS, target p95/p99/error SLOs | Judge success by user impact |
| Active/max, queue depth/age/wait, task run time, rejections/timeouts | Identify whether the executor itself lacks capacity |
| CPU, GC, heap, DB pool, downstream latency, retries | Detect bottlenecks shifting to other resources |
| Warm-up period, test start/end times, deploy timestamps | Avoid comparing cold vs. warm runs or misaligned windows |

If traffic follows daily cycles, baselines must cover both steady load and **peak hours**, bursts, and recovery windows. A 10-second low-load snapshot is insufficient for long-term capacity sizing.

**Recommended sampling order:** warm up so JIT, caches, and connection pools stabilize; run steady state long enough to observe queues/GC; ramp load in steps; record recovery after bursts. Choose window durations based on latency, GC cycles, and downstream behavior rather than one rigid minute count for all services.

Example baseline table:

| Test ID | Arrival RPS | Completed RPS | HTTP p95/p99 | Active/max | Queue p95 / wait p95 | Rejected/s | CPU | DB pending |
|---|---:|---:|---|---|---|---:|---:|---:|
| B0, steady load | 80 | 80 | 240/390 ms | 18/24 | 3 tasks / 15 ms | 0 | 61% | 0 |
| B1, peak load | 130 | 112 | 970/1700 ms | 24/24 | 90 tasks / 650 ms | 5 | 65% | 0 |

*Synthetic numbers illustrating how to read the table, not real measurements from a specific system.*

Reading B1: active hits max, queue and queue wait surge, rejections appear while CPU is only 65% and DB pending=0. That suggests the hypothesis that **the executor may be the bottleneck**, especially if tasks frequently wait on I/O. Still, that alone does not justify raising max threads: inspect what tasks wait on, connection pools/downstream latency, and arrival vs. completion rates.

## 7. Formulas to guide thinking — not replacements for measurement

### 7.1. Little's Law: average concurrency

In steady state with a consistently defined scope:

`L = λ × T`

Where:
- `L`: average requests/tasks present in the measured system (including running and waiting if `T` covers both).
- `λ`: average completion rate (requests/second or tasks/second).
- `T`: average time a request/task spends in the system (seconds).

Example: an endpoint steadily completes **80 requests/s** with an average time in system of **0.25 seconds**:

`L = 80 × 0.25 = 20 requests present on average.`

**This does not mean you need exactly 20 worker threads.** Async/reactive systems can hold many active requests without dedicating a thread to each; blocking requests may occupy workers most of the time; one request may spawn multiple subtasks or fan-outs. Little's Law validates consistency across throughput, latency, and concurrency, after which you map to the actual execution model.

### 7.2. Heuristic for blocking tasks

A commonly cited heuristic:

`N ≈ N_CPU × U_target × (1 + W_wait / C_cpu)`

Where:
- `N_CPU`: effective allocated CPUs (including container quota).
- `U_target`: target CPU utilization between 0 and 1.
- `W_wait`: average time a task spends **not using CPU** (waiting on I/O or synchronization).
- `C_cpu`: actual CPU time consumed by the task.

Suppose 4 CPUs, target 70% CPU, and a task uses 25ms CPU plus 225ms external wait on average:

`N ≈ 4 × 0.7 × (1 + 225 / 25) = 28 threads.`

**28 is only a starting point for a hypothesis**, not a setting to ship blindly. The formula assumes clean CPU/wait separation, mostly independent tasks, and no downstream cap. Test values around it under real load; multi-phase tasks, lock contention, context switching, or high variance can skew the heuristic significantly.

**Cross-check:** at 80 requests/s and 250ms average duration, average in-flight requests are ~20. A pool of 28 gives headroom without implying 28 threads are always active. If the database permits only 10 connections and tasks hold them long, 28 workers may simply form a bigger queue waiting on the DB.

### 7.3. Queue growth rate

During an overload interval, you can approximate:

`ΔQ/Δt ≈ arrival_rate − completion_rate`

If 120 tasks/s arrive while only 90 tasks/s finish and the queue can absorb them, after 10 seconds the queue can grow by roughly **300 tasks** (adjusted for changes in active workers and rejections). This is a flow approximation; applying it rigidly breaks down when worker counts are scaling or arrivals, retries, and completions are not measured on the same basis.

**Large queues do not increase serving capacity**; they trade early rejections for longer waits, higher memory usage, and worse tail latency. Measure queue wait—do not optimize merely to reach “zero rejections.”

## 8. Distinguishing three bottleneck types by symptoms

### Case A — CPU-bound

Symptoms: CPU near quota, high throttling, significant GC/allocations; raising pool size increases context switching and p99 even when queues are small. Tasks do heavy computation with little I/O waiting.

Experiments to try: eliminate redundant work, add sensible caching/precomputation, optimize algorithms, profile CPU/JFR, scale CPU/instances; avoid unbounded worker counts. For CPU-bound workloads, sizes near core count are a better starting point than hundreds of threads.

### Case B — I/O-bound or lock contention

Symptoms: high active threads, spare CPU, thread dumps showing many tasks waiting on network/database/locks, growing queue wait, throughput lagging active count. A few tasks waiting 2 seconds on a slow API tie up workers the whole time.

Experiments to try: tighten uncontrolled timeouts/retries, use async/non-blocking where sensible, isolate executors by task type, cap concurrency toward downstream services, shorten lock/transaction durations. Only afterward test raising the pool if downstream has spare capacity.

### Case C — Pool or queue limits set too low

Symptoms: queues fill and reject steadily at target load while CPU and downstream still have headroom, and task service time stays relatively stable; increasing max or trimming queue wait in a controlled experiment boosts throughput and lowers p95/p99 without saturating other resources.

Experiments to try: step through `core-size`/`max-size`/`queue-capacity`; enforce bounded queues and clear rejection policies, applying backpressure as needed. Monitor fail-fast behavior, timeouts, and recovery once bursts subside.

| Combined observation | Primary hypothesis | What to verify |
|---|---|---|
| Active ≈ max; queue growing; low CPU | Blocking/I/O wait or undersized pool | Thread dumps, DB/API waits, throughput after increasing max |
| Active ≈ max; CPU 95–100%; queue growing | CPU limit | CPU profiling, throttling, per-task CPU |
| Active low; queue large; max large; unbounded queue | Queue absorbs tasks before pool scales | Actual `core`/`max`/`queueCapacity` |
| Queue small; HTTP p99 high; DB pending high | Waiting on database connections | Hikari acquisition time and SQL p99 |
| Zero rejections yet p99 rises continuously | Deep queues or caller-runs masking overload | Queue wait, caller request thread blocking |
| Reactor event-loop lag high, CPU not necessarily high | Blocking on the event loop | JFR, BlockHound in appropriate tests, trace handlers |

Never infer causation from **a single metric**. High active count alone can reflect CPU-bound work, I/O waits, deadlocks, or simply a busy healthy workload.

## 9. Step-by-step controlled experimentation process

A valid experiment follows these steps:

**Step 1 — Define goals and constraints.** E.g. at 80 RPS, p95 < 300ms, p99 < 500ms, error rate < 1%, zero lost-work rejections, CPU within safe headroom, low DB pending, reasonable cost. These are **illustrative thresholds**—replace them with your service's real SLOs.

**Step 2 — Hold conditions constant.** Use the same image, payload, replica count, vCPUs, JDK, GC config, DB, cache, and load generator; avoid comparing runs with multiple simultaneous changes.

**Step 3 — Capture the baseline.** Measure warm-up, steady load, burst, and recovery. Record active/max, queue depth/wait, rejections, CPU, and downstream metrics. Verify the **load generator** itself is not the bottleneck: compare achieved RPS to target RPS and check dropped iterations.

**Step 4 — Pick one hypothesis and one parameter.** For example, change only `maxPoolSize=16 → 24` with a bounded queue, holding core/queue/policy constant. Test queue capacity in a separate experiment so effects do not blur.

**Step 5 — Re-run under identical conditions.** Collect full metrics for each candidate; compare p50/p95/p99, throughput, rejections, resource usage, overload behavior, and queue recovery time.

**Step 6 — Decide by SLOs and knee points.** Choose the smallest configuration meeting targets with reasonable headroom. If p95 improves while p99, error rates, CPU, or DB worsen, it is not an overall win.

**Step 7 — Roll out safely.** Use canary/gradual rollout where appropriate, annotate config changes, monitor across full traffic cycles, and roll back if key metrics breach thresholds. Treat pool changes as changes to admission and queueing behavior, not just tweaking a number.

### Example reading A/B results

Suppose a service uses a platform-thread executor with `core=8`, bounded queue 100, and target load 80 requests/s:

| max threads | Completed RPS | p95 / p99 | Queue wait p95 | CPU | Rejected/s |
|---:|---:|---|---:|---:|---:|
| 16 | 78 | 480 / 900 ms | 160 ms | 57% | 0.3 |
| 24 | 80 | 280 / 450 ms | 8 ms | 63% | 0 |
| 32 | 80 | 295 / 520 ms | 4 ms | 79% | 0 |

*Synthetic numbers for practicing decisions, not a real benchmark.*

Given the SLO from Step 1, **24** is the best candidate: it hits p95/p99, full throughput, zero rejections, and preserves CPU headroom. Pool 32 adds no throughput, shaves almost nothing off queue wait, and worsens CPU and tail latency. Still confirm stability over full load cycles and statistical confidence across runs.

## 10. Configuring the right target once you have evidence

### 10.1. Spring MVC with Tomcat

**One candidate** configuration to test for Servlet/Tomcat:

~~~yaml
server:
  tomcat:
    threads:
      min-spare: 16
      max: 120
~~~

`server.tomcat.threads.max` adjusts Tomcat request workers when using a matching setup; **it does not directly change** `@Async` executor threads or the Hikari connection pool. `server.tomcat.accept-count` governs the TCP accept backlog when the server cannot accept fast enough, not an arbitrary Java task queue to inflate for slow apps. Jetty and Netty settings differ from Tomcat.

Check `server.tomcat.max-connections`, accept/backlog behavior, request latency, busy worker counts, and dependencies before blaming the thread pool.

### 10.2. Spring `@Async` / `ThreadPoolTaskExecutor`

Candidate noted earlier:

~~~yaml
spring:
  task:
    execution:
      pool:
        core-size: 8
        max-size: 24
        queue-capacity: 100
~~~

In `ThreadPoolExecutor`, raising `max-size` **only takes effect once the queue is full** (under default mechanics). Enlarging `queue-capacity` can prevent the pool from scaling up and increase tail latency. Huge queues hold tasks long enough to trigger HTTP timeouts or memory exhaustion before rejections occur.

With a custom bean, configure directly:

~~~java
// Fragment placed inside a Spring @Configuration class.
// Not a standalone Java program.
@Bean
ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setThreadNamePrefix("report-");
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(24);
    executor.setQueueCapacity(100);
    return executor;
}
~~~

Corresponding imports:
- `org.springframework.context.annotation.Bean`
- `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`

If injected via `@Async("reportExecutor")`, metrics and tests must track that exact bean. Boot can auto-instrument eligible `ThreadPoolTaskExecutor` beans, though business-level queue wait and rejections still require verification.

### 10.3. Spring WebFlux / Reactor Netty

I/O event loops must avoid long blocking tasks. When blocking handlers appear on an event loop, prefer:
- Switching to non-blocking clients/drivers when viable options exist.
- Isolating blocking work onto `Schedulers.boundedElastic()` or an appropriate executor with clear concurrency limits.
- Measuring scheduler queue wait, bounded resources, and downstream behavior; checking for backpressure bottlenecks.

Do not conclude “WebFlux is faster so add more Netty event-loop threads.” Nor is `spring.task.execution.pool.*` a master switch for all Reactor schedulers. Before tuning any resource, confirm that exact resource runs the slow work.

### 10.4. Java 21+ virtual threads

When `spring.threads.virtual.enabled=true` is enabled in supported Spring Boot versions, the auto-configured task executor can switch to a virtual-thread `SimpleAsyncTaskExecutor` instead of `ThreadPoolTaskExecutor`. `spring.task.execution.pool.*` properties **no longer tune a platform-thread pool** in that mode; `server.tomcat.threads.max` may also stop taking effect when the server uses virtual threads.

Do not evaluate virtual threads with a dashboard built solely around active platform threads. Measure concurrency, CPU, heap, JDK-specific pinning/carrier behavior, JFR, semaphores, DB/API connection limits, and wait times instead. Virtual threads add neither CPU cores nor database capacity; allowing high task concurrency without upstream/downstream bounds can overwhelm dependencies.

### 10.5. Rejection policies and backpressure

- `AbortPolicy` rejects tasks when full; surfaces overload early, though the app must translate rejections into clear business responses.
- `CallerRunsPolicy` makes the submitting thread run the task. It creates backpressure while **increasing caller latency**; measure its impact on submitting Tomcat workers or consumers.
- `DiscardPolicy`/`DiscardOldestPolicy` silently drop tasks in certain scenarios—dangerous when tasks represent payments, orders, or durable work.

Never make queues unbounded just to “eliminate errors.” For durable workloads, consider persistent message queues, bounded retries, idempotency, and admission control instead of huge in-memory Java queues.

## 11. Case study: from slow requests to deciding NOT to increase the pool

Suppose Spring MVC serves `GET /reports/{id}`. At peak, HTTP p99 is 2.5 seconds, Tomcat active is 40/200, `reportExecutor` active is 8/8, queue is 200, CPU is 38%, and Hikari pending is 0. Report tasks call an external report-export service that takes 2 seconds and frequently times out.

**Initial data suggests:** Tomcat is not saturated; `reportExecutor` is full; the queue is deep, yet the bottleneck may be the external export API. Raising the executor to 40 threads would send 32 more concurrent requests into that slow API, likely overloading it and causing even more timeouts.

Sensible investigation:

1. Trace one request: time queued in `reportExecutor`, CPU time building the report, and time waiting on the export API.
2. Correlate tail latency with downstream charts, retry rates, and API quotas.
3. Trim uncontrolled timeouts/retries, cache repeated report pieces, cap concurrency toward the API, or move long exports to an async job flow with status polling if business rules allow.
4. Re-test under identical load: if API latency stabilizes, executor queues drain and HTTP p99 improves without growing the pool.
5. Only test raising the executor if downstream has spare capacity and queue wait remains an observed bottleneck.

This example shows why **“what are the threads doing?”** matters more than **“how many threads do we need?”**

## 12. Extra diagnostic tools when metrics are not enough

**JFR / Java Mission Control:** capture CPU sampling, allocations, thread states, monitor/lock contention, and virtual-thread events if supported by your JDK. JFR separates active CPU execution from blocked/waiting time, which a single active-count gauge hides.

**Thread dumps:** inspect thread/pool names, stack traces, and `RUNNABLE`, `WAITING`, `TIMED_WAITING`, and `BLOCKED` states. Never treat a single snapshot as absolute truth: take multiple snapshots over time aligned with queue growth. `RUNNABLE` can include native I/O waits rather than pure CPU burn.

**Distributed tracing:** shows HTTP → executor → database → API relationships. Adding spans for queue wait vs. task execution separates “waiting to start” from “running while waiting on another system.”

**CPU/heap profiling:** use when CPU or GC climbs after growing a pool. Never expand a pool based solely on thread counts when CPU is already saturated.

**Load generator:** record intended arrival rate, achieved throughput, and dropped iterations. If the load generator itself runs out of CPU or connections, experiments can falsely conclude the app hit maximum throughput.

## 13. Common tuning mistakes

1. **Raising `maxPoolSize` with an unbounded queue:** the pool stops at core size while backlog keeps growing. Understand `ThreadPoolExecutor`'s queue-first algorithm.
2. **Tuning the wrong pool:** editing Tomcat when `@Async` is the bottleneck, or editing `spring.task.execution.*` when a custom executor is active.
3. **Looking only at average CPU:** one core can be pinned, containers throttled, or connection pools/locks saturated while total CPU looks low.
4. **Looking only at p50:** burst p99 latency and wait times can degrade severely while the median barely moves.
5. **Tracking only completed RPS:** higher offered load that gets rejected, timed out, or dropped by the generator disappears from completion counters.
6. **Growing queues to avoid rejections:** giant queues cause stale/timed-out tasks, memory pressure, and masked overload; monitor queued task age.
7. **Confusing queue wait with task run time:** short execution times still yield slow user responses if tasks sit in queues.
8. **Ignoring dependencies:** 100 concurrent tasks hitting a 10-connection DB pool increase contention and timeouts.
9. **Skipping warm-up or varying conditions:** changing builds, JDKs, replicas, or caches between runs and attributing differences to pool size.
10. **Changing multiple parameters at once:** impossible to tell which knob helped or hurt p99.
11. **Skipping overload/recovery tests:** steady state looks fine, yet after a burst the queue never drains or memory climbs.
12. **Using platform-thread metrics to tune virtual threads:** many pool properties no longer apply; downstream resources and concurrency caps matter instead.
13. **Unbounded metric label cardinality:** putting request IDs in metric labels explodes time series and overloads monitoring.
14. **Overlooking rejection policies:** `CallerRunsPolicy` slows down submitters, while discard policies drop tasks silently.

## 14. Before/after change checklist

Before:
- [ ] Identified the exact pool and request/task execution path.
- [ ] Recorded JDK/Boot versions, server type, vCPU/quotas, replica count, and core/max/queue/policy config.
- [ ] Captured baseline RPS, p95/p99, queue wait/size, active/max, rejections, CPU, GC, and DB/downstream metrics.
- [ ] Identified the bottleneck with evidence: CPU, I/O, dependency, queue, or worker shortage.
- [ ] Defined SLOs, error/latency/resource thresholds, and burst/recovery scenarios.
- [ ] Selected one isolated change and a clear rollback plan.

After:
- [ ] Identical workload, resources, and measurement duration.
- [ ] Compared throughput, p95/p99, queue wait/rejections, and CPU/downstream metrics.
- [ ] Confirmed the bottleneck did not merely shift to DB, external APIs, GC, event loops, or callers.
- [ ] Made a keep/revert decision grounded in SLOs and repeatable runs.
- [ ] Monitored production post-rollout long enough to cover peak traffic cycles.

## 15. Review questions

**Question 1.** A pool has `core=8`, `max=64`, and an unbounded queue. As task load increases, will the pool necessarily grow to 64 threads?

**Answer:** No. Under `ThreadPoolExecutor`'s default behavior, an unbounded queue absorbs tasks after core size is reached; `maxPoolSize` is typically never used to scale up.

**Question 2.** Does 30% CPU plus a long queue prove you should enlarge the executor?

**Answer:** Not yet. Tasks may be waiting on the DB, APIs, or locks, or the executor may lack threads. Measure queue wait, task service vs. wait times, and underlying resources, then test in a controlled experiment.

**Question 3.** At 100 req/s and 200ms average time in the system, how many concurrent requests does Little's Law estimate?

**Answer:** `100 × 0.2` = **20 requests** present on average in steady state. That does not automatically translate to 20 Java threads.

**Question 4.** Why might increasing `server.tomcat.threads.max` fail to reduce wait time for work running via `@Async("billingExecutor")`?

**Answer:** They are two independent limits. You must measure `billingExecutor` and the downstream systems it calls.

**Question 5.** If raising max threads lowers p50 yet increases p99 and spikes CPU, should you ship it right away?

**Answer:** No. Evaluate against SLOs and trade-offs, inspect saturation/GC/context switching/DB, re-run under identical conditions, and consider a smaller thread count.

**Question 6.** When virtual threads are enabled, should you tune `spring.task.execution.pool.max-size` like a platform pool?

**Answer:** Do not assume it takes effect. Check the actual active executor; many pool properties are ignored when Boot uses `SimpleAsyncTaskExecutor` with virtual threads.

## 16. References

- [Spring Boot — Metrics / Actuator / HTTP / Task Execution / Tomcat](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Task Execution and Scheduling, virtual threads and task executor properties](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html)
- [Spring Framework — Task Execution and Scheduling; ThreadPoolTaskExecutor, queues and rejection policies](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Java SE — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Boot — Actuator metrics endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/metrics.html)

**Remember when tuning:** measure user-facing time, queue wait time, and backend resource capacity together. Changing executor size is merely a hypothesis to verify with data.