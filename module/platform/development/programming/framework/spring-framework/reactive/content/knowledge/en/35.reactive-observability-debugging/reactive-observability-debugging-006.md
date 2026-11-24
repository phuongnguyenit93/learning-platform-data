# Observing Schedulers, Queues, Connection Pools, and Buffers in Spring WebFlux

## 1. Goal and Observability Mindset

A Spring WebFlux application can handle many concurrent requests without dedicating a separate thread to each request. However, non-blocking does not mean infinite resources or immunity to bottlenecks. A pipeline can slow down due to CPU saturation, exhausted Scheduler workers, growing queues, depleted connection pools, slow database responses, slow-reading clients, or buffers held too long.

**Observability** is the ability to understand the internal state of a system through metrics, logs, and traces. For a reactive system, you need to inspect layer by layer:

1. HTTP requests: traffic volume, latency, status, and errors.
2. Reactor pipelines: subscriptions, lifetime, demand, cancellation, and errors.
3. Schedulers: active tasks, pending tasks, and completion rate.
4. Queues: depth, capacity, wait time, and rejected task count.
5. Connection pools: active, idle, pending connections, and acquire time.
6. Memory/buffers: heap, direct memory, Netty allocator, and leak indicators.
7. Database/downstream: query latency, timeouts, locks, retries, and dependency limits.

After this lesson, you will be able to pick the right metrics for each resource, enable Reactor/Micrometer metrics, read R2DBC and Reactor Netty pool metrics, observe buffers, build dashboards/alerts, diagnose common symptoms, and implement a Java 17+ Spring Boot WebFlux demo.

**Principle:** a single number rarely explains an incident. Correlate traffic, p95/p99 latency, pending work, throughput, errors, and resource utilization over the same time window.

## 2. Four Concepts to Distinguish

| Concept | Question Answered | Example |
| --- | --- | --- |
| Metrics | How many, how fast/slow, what is the trend? | requests/s, p99, pending connections |
| Logs | Which specific event just occurred? | request timeout, pool acquire failed |
| Traces | Which services/spans did a request traverse? | HTTP → service → database → remote API |
| Profiling/diagnostics | Where are CPU, allocations, locks, or threads being spent? | JFR, thread dump, heap dump, async-profiler |

Metrics are suited for dashboards and alerting over time. Logs capture event details and context. Distributed traces locate slow spans in requests spanning multiple services. Profiling pinpoints deep root causes such as CPU loops, lock contention, high allocations, or blocking calls.

Do not log every payload in order to achieve "full observability". Payloads may contain tokens, personal data, or sensitive information. Log correlation IDs, route templates, operations, statuses, error types, and durations; only include permitted and redacted data.

## 3. Resource Flow in a WebFlux Request

~~~text
HTTP client
    |
    v
Reactor Netty event loop
    |
    v
WebFlux controller / service
    |
    +------> Reactor Scheduler (if the pipeline switches schedulers)
    |
    +------> R2DBC Connection Pool
    |             |
    |             v
    |          Database
    |
    +------> WebClient Connection Pool
    |             |
    |             v
    |          Remote service
    |
    +------> Application queue / buffer
                  |
                  v
              Consumer
~~~

The event loop handles I/O and short callbacks. Never run JDBC/JPA, blocking file I/O, or heavy CPU computations on the event loop. If you must isolate an irreplaceable blocking API, use an appropriate Scheduler and bound concurrency/queueing. If the work is CPU-bound, use a parallel Scheduler or a CPU executor sized to core count; do not dump everything onto boundedElastic.

Every pool and queue has limits. When a consumer processes slower than a producer, work can wait, be rejected, be dropped, or increase memory usage. You must choose an intentional overflow/backpressure policy.

## 4. Foundational Spring Boot Actuator Metrics

Add Actuator and an appropriate registry to export metrics:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Spring Boot uses Micrometer as its metrics facade. Depending on dependencies and configuration, meters can be exported to Prometheus, OTLP, Datadog, New Relic, or other backends.

Commonly needed metrics:

| Category | Common Meters | Meaning |
| --- | --- | --- |
| HTTP server | `http.server.requests` | request count and processing duration by route/status |
| JVM heap | `jvm.memory.used`, `jvm.memory.max` | heap used and limit |
| JVM buffer | `jvm.buffer.count`, `jvm.buffer.memory.used` | count and memory of JVM buffer pools |
| GC | `jvm.gc.pause` | GC pause duration |
| Threads | `jvm.threads.live`, `jvm.threads.peak` | live and peak threads |
| Process/system | `process.cpu.usage`, `system.cpu.usage` | process and host CPU |
| Application | custom-defined metrics | queue depth, rejected work, business latency |

`/actuator/metrics` is for listing meters and diagnosing a specific meter. This endpoint is not a backend for continuous Prometheus scraping. For Prometheus, use `/actuator/prometheus` and the corresponding registry.

Illustrative configuration:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.tags.application=reactive-observability-lab
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=50ms,100ms,250ms,500ms,1s
~~~

Expose only necessary endpoints. In production, restrict network access and apply authentication/authorization to Actuator. Never expose all endpoints to the public Internet. Meter names in `/actuator/metrics` use Micrometer dot notation such as `jvm.memory.used`; Prometheus may convert names to snake_case.

## 5. Observing Reactor Schedulers

The Scheduler determines where tasks execute. Common options:

| Scheduler | Purpose | Notes |
| --- | --- | --- |
| `Schedulers.parallel()` | Short CPU-bound work | Do not use for blocking I/O |
| `Schedulers.boundedElastic()` | Isolating blocking work | Has thread and queue limits |
| `Schedulers.single()` | Single shared worker thread | One slow task can make other tasks wait |
| `Schedulers.immediate()` | Runs on the current thread | Does not create new threads |
| `Schedulers.newParallel(...)` | Dedicated CPU Scheduler | Needs to be disposed when no longer used |
| `Schedulers.newBoundedElastic(...)` | Dedicated blocking Scheduler with limits | Choose thread cap and queue cap per workload |

A request can switch threads via `publishOn` or `subscribeOn`. Therefore, do not infer request lifecycle solely from the current thread name. Measure the specific Schedulers your application intentionally uses.

### 5.1. Using Micrometer.timedScheduler

In modern Reactor, the `reactor-core-micrometer` module provides a wrapper to measure Schedulers:

~~~groovy
implementation 'io.projectreactor:reactor-core-micrometer'
~~~

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
class SchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    Scheduler observedIoScheduler(MeterRegistry registry) {
        Scheduler delegate =
            Schedulers.newBoundedElastic(4, 100, "observed-io");

        return Micrometer.timedScheduler(
            delegate,
            registry,
            "app.io"
        );
    }
}
~~~

Metric names use the supplied prefix, for example `app.io.scheduler.tasks.completed`. Key meters:

| Meter | Type | Meaning |
| --- | --- | --- |
| `app.io.scheduler.tasks.active` | LongTaskTimer | currently active tasks, including delayed/periodic tasks |
| `app.io.scheduler.tasks.completed` | Timer | execution duration of completed tasks |
| `app.io.scheduler.tasks.pending` | LongTaskTimer | immediate tasks that cannot start right away because the Scheduler has reached capacity |
| `app.io.scheduler.tasks.submitted` | Counter | submission count, tagged by submission type |

**Very important point:** the wrapper only instruments Runnables submitted through the exact Scheduler returned by `Micrometer.timedScheduler`. If code continues calling `Schedulers.parallel()` or another Scheduler, those tasks do not automatically appear under the `app.io` prefix.

`tasks.pending` is not a gauge for total queue depth. It describes immediate tasks that were submitted but could not start right away under the wrapper's semantics. To know application queue depth, instrument the queue yourself at the application layer.

`Schedulers.enableMetrics()` is an older deprecated API; prefer the explicit `Micrometer.timedScheduler` wrapper. Do not call the old API merely because you saw examples from earlier Reactor versions.

### 5.2. Wiring the Scheduler into a Pipeline

~~~java
@Service
class WorkService {
    private final Scheduler ioScheduler;
    private final MeterRegistry registry;

    WorkService(
            Scheduler observedIoScheduler,
            MeterRegistry registry) {
        this.ioScheduler = observedIoScheduler;
        this.registry = registry;
    }

    Flux<Integer> calculate(int count) {
        return Flux.range(1, count)
            .flatMapSequential(value ->
                Mono.fromCallable(() -> {
                    // Simulate a legacy blocking API.
                    Thread.sleep(20);
                    return value * value;
                }).subscribeOn(ioScheduler),
                4
            )
            .name("demo.work")
            .tag("operation", "square")
            .tap(Micrometer.metrics(registry));
    }
}
~~~

`Thread.sleep` only simulates a blocking dependency in the hands-on exercise and is isolated on bounded elastic. Real applications should replace it with a non-blocking client whenever possible. `flatMapSequential(..., 4)` caps concurrency at four tasks and preserves source ordering.

### 5.3. Metrics for Reactive Sequences

Besides Schedulers, `Micrometer.metrics(registry)` attached via `tap` can measure a named sequence:

- `demo.work.flow.duration`: duration from subscribe to complete/error/cancel.
- `demo.work.onNext.delay`: time interval between onNext emissions.
- `demo.work.requested`: amount of demand requested.
- `demo.work.subscribed`: number of subscriptions.
- `demo.work.malformed.source`: protocol-violating events from the source, when detected.

Sequence meters can carry a status tag such as completed, completedEmpty, error, or cancelled. This is useful for distinguishing successful requests from publishers cancelled because the client disconnected.

Use `name` and low-cardinality tags such as operation, source, or result. Do not put user IDs, request IDs, emails, raw URLs, or exception messages into metric tags; high cardinality can cause Prometheus/Micrometer memory and storage costs to grow rapidly.

## 6. Observing Queues and Backpressure

A queue is where work waits for a consumer. Useful indicators to have:

| Application Metric | Meaning |
| --- | --- |
| `app.work.queue.depth` | current number of items |
| `app.work.queue.capacity` | maximum capacity |
| `app.work.queue.rejected` | number of failed enqueues |
| `app.work.queue.wait` | time from enqueue to dequeue |
| `app.work.queue.processed` | number of completed items |
| `app.work.queue.processing` | number of items currently being processed |

If depth keeps growing, the producer is outpacing the consumer. Increasing capacity only delays when the queue fills; it does not solve insufficient throughput and can hold even more objects in memory.

The policy when a queue is full must be defined:

- Reject: refuse new work and return 429/503 or the corresponding signal.
- Drop newest: discard the newest item if business rules permit.
- Drop oldest: discard the oldest item if newer data is more valuable.
- Bounded buffer: wait for a fixed duration and then reject.
- Backpressure: ask upstream to slow down if upstream honors demand.
- Persist: write work to a broker/database when durability is required.

Never use an unbounded queue as a solution for a slow consumer. Define queue capacity, maximum wait, overflow policy, and metrics for every queue.

### 6.1. Reactor Netty Queues and Application Queues Are Not the Same

`reactor.netty.eventloop.pending.tasks` measures tasks waiting on the Reactor Netty event loop when the corresponding metrics are enabled. It does not measure business queues, queues inside `flatMap`, or every buffer inside Reactor operators.

Spring-managed `ThreadPoolTaskExecutor` and `ThreadPoolTaskScheduler` can be auto-instrumented by Actuator. Executor meters typically report active threads, pool size, queued tasks, and completed tasks. A separate Reactor Scheduler requires Reactor instrumentation as shown above.

### 6.2. Measuring Your Own Application Queue

~~~java
@Component
class WorkQueueTelemetry {
    private record Entry(String value, long enqueuedAtNanos) {}

    private final ArrayBlockingQueue<Entry> queue =
        new ArrayBlockingQueue<>(64);

    private final Counter rejected;
    private final Timer waitTime;

    WorkQueueTelemetry(MeterRegistry registry) {
        Gauge.builder(
            "app.work.queue.depth", queue, Queue::size
        ).register(registry);

        Gauge.builder(
            "app.work.queue.capacity",
            queue,
            q -> q.size() + q.remainingCapacity()
        ).register(registry);

        this.rejected = registry.counter("app.work.queue.rejected");
        this.waitTime = registry.timer("app.work.queue.wait");
    }

    boolean offer(String value) {
        boolean accepted =
            queue.offer(new Entry(value, System.nanoTime()));

        if (!accepted) {
            rejected.increment();
        }
        return accepted;
    }

    Optional<String> poll() {
        Entry entry = queue.poll();
        if (entry == null) {
            return Optional.empty();
        }

        waitTime.record(
            System.nanoTime() - entry.enqueuedAtNanos(),
            TimeUnit.NANOSECONDS
        );
        return Optional.of(entry.value());
    }

    int depth() {
        return queue.size();
    }

    int capacity() {
        return queue.size() + queue.remainingCapacity();
    }
}
~~~

A Gauge only reflects a snapshot at scrape time. The rejection Counter is cumulative; the wait Timer records the distribution of wait durations. When a queue is replaced by a broker, use the broker's corresponding metrics instead of measuring only local queues.

## 7. Observing Connection Pools

A reactive request may not block a thread while waiting on the database, yet it still has to wait for a connection if the pool is exhausted. This is a common bottleneck: CPU can be low while HTTP latency and pending acquires rise.

### 7.1. R2DBC Pool Metrics

Spring Boot 3.5 supports Actuator metrics for the R2DBC connection pool when pooling is configured and the corresponding driver/pool is present.

| Meter | Meaning |
| --- | --- |
| `r2dbc.pool.acquired` | connections currently acquired and in use |
| `r2dbc.pool.allocated` | total allocated connections in the pool, including active and idle |
| `r2dbc.pool.idle` | currently idle connections |
| `r2dbc.pool.pending` | requests waiting to acquire a connection |
| `r2dbc.pool.max.allocated` | connection pool limit |
| `r2dbc.pool.max.pending` | limit of the pending acquire queue |

Useful readings:

- `acquired` near `max.allocated` and `pending` rising: the pool may be saturated.
- `idle` is high yet latency is high: inspect queries, network, locks, transactions, or other downstream calls.
- `pending` at 0 does not prove the database is healthy; queries can still be slow once a connection is acquired.
- Long-held transactions can starve pool capacity even if individual queries are fast.

Illustrative configuration:

~~~properties
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=5
spring.r2dbc.pool.max-size=20
spring.r2dbc.pool.max-acquire-time=3s
spring.r2dbc.pool.max-idle-time=30m
~~~

Choose max-size based on database limits, instance/pod count, and workload. Maximum total connections are roughly replica count times pool max-size; leave headroom for migrations, monitoring, and other services.

Do not blindly increase pool size. If the database is already saturated on CPU/I/O/locks, adding connections can make matters worse. Inspect query duration, transaction hold time, concurrency, and database limits before changing pool settings.

### 7.2. Reactor Netty HTTP Client Connection Pool

With WebClient/Reactor Netty, the connection pool has its own set of metrics when metrics are enabled:

| Meter | Meaning |
| --- | --- |
| `reactor.netty.connection.provider.active.connections` | connections currently in use |
| `reactor.netty.connection.provider.idle.connections` | currently idle connections |
| `reactor.netty.connection.provider.total.connections` | total active + idle |
| `reactor.netty.connection.provider.max.connections` | connection limit |
| `reactor.netty.connection.provider.pending.connections` | requests waiting for a connection |
| `reactor.netty.connection.provider.pending.connections.time` | time spent waiting to acquire |
| `reactor.netty.connection.provider.max.pending.connections` | pending queue limit |

If you create `ConnectionProvider` or `HttpClient` manually, you must enable metrics in the Reactor Netty configuration, for example `ConnectionProvider.builder(...).metrics(true)` and `HttpClient.metrics(true, ...)`. Do not assume a manually created client is instrumented identically to one managed by Spring Boot.

Client pool metrics only describe outbound connections to remote servers. They are not the count of inbound WebFlux clients connected to your application.

## 8. Observing Buffers and Memory

A reactive pipeline can hold data in:

- JVM heap: objects, DTOs, collections, and queues.
- JVM direct buffer pool: NIO direct ByteBuffers.
- Netty ByteBuf allocator: pooled heap/direct memory.
- Reactor operator buffers: prefetch, publishOn, flatMap, buffer/window.
- Application queues: custom-built queues.
- Drivers/brokers/network: buffers outside the JVM or in native memory.

There is no single metric reflecting the total of all buffers across the entire system.

### 8.1. JVM Buffer Pool

Spring Boot can expose the meters:

- `jvm.buffer.count`: number of buffers in the pool.
- `jvm.buffer.memory.used`: memory currently used by JVM buffer pools.
- `jvm.buffer.total.capacity`: total capacity of buffers.

You can drill down by the `id` tag to distinguish `direct` and `mapped` when that meter provides the corresponding tag. JVM buffer pool metrics do not always equal the exact bytes held by the Netty allocator.

### 8.2. Reactor Netty ByteBufAllocator Metrics

When Reactor Netty metrics are enabled, meters can include:

| Meter | Meaning |
| --- | --- |
| `reactor.netty.bytebuf.allocator.active.direct.memory` | direct memory actually backing buffers currently in use |
| `reactor.netty.bytebuf.allocator.active.heap.memory` | heap memory actually backing buffers currently in use |
| `reactor.netty.bytebuf.allocator.used.direct.memory` | direct memory reserved by the allocator |
| `reactor.netty.bytebuf.allocator.used.heap.memory` | heap memory reserved by the allocator |
| `reactor.netty.eventloop.pending.tasks` | number of tasks pending on the event loop |

**Distinguish active vs used:** the allocator can keep reserved memory regions for reuse after buffers are released. Therefore, `used.direct.memory` remaining high after a traffic burst is not by itself proof of a leak. If `active.direct.memory` climbs steadily and does not drop after traffic stops, investigate ownership/release and Netty leak logs.

Reactor Netty has the `_reactor.netty.channel.LeakDetection` logger to aid buffer leak diagnosis; enabling DEBUG can provide ownership traces. Use high leak-detection levels only in controlled test environments because they add overhead. Do not enable the heaviest mode by default across all production traffic.

### 8.3. No Single Metric Covers All Operator Buffers

`publishOn`, `flatMap`, `onBackpressureBuffer`, and `buffer` can create internal queues with different semantics. Reactor does not provide a single global gauge for the total number of items sitting across all operator buffers.

If a queue is part of business logic, instrument it at the application boundary. If you suspect operator prefetching is increasing memory, inspect concurrency/prefetch settings, payload sizes, downstream throughput, and heap/direct memory; use heap dumps/JFR to find objects retaining references.

## 9. Reactor Sequence Metrics and Tracing

You can instrument a pipeline segment with `reactor-core-micrometer`:

~~~java
Flux<Order> observed = orderSource
    .name("orders.pipeline")
    .tag("stage", "validation")
    .tap(Micrometer.metrics(meterRegistry))
    .checkpoint("orders.after-validation");
~~~

`name` creates a meaningful prefix; `tag` should hold low-cardinality values; `tap(Micrometer.metrics(...))` collects flow metrics. `checkpoint` adds a boundary supporting stack traces when errors propagate through the pipeline.

Metrics and traces serve different purposes:

- Metrics tell you that many requests are slow or failing.
- Traces show which span a specific request spent time in.
- Logs tie traceId/spanId to concrete events.
- Profiling pinpoints resource-heavy code paths, locks, or allocations.

For tracing, use Micrometer Observation/Tracing and appropriate context propagation. Reactive execution can switch threads, so do not rely on plain ThreadLocal to carry correlation IDs through a pipeline. Avoid enabling automatic context propagation without measuring overhead and checking integrated libraries.

## 10. Structured Logs and Correlation

A useful log for a reactive request should contain:

- timestamp and level;
- service/instance;
- traceId/spanId or request correlation ID;
- route template, method, and status;
- operation name;
- duration;
- exception class and redacted cause.

Illustrative log example:

~~~text
INFO traceId=7fa... spanId=21b... method=GET
route=/api/items status=200 durationMs=42 operation=load-items
~~~

Do not log raw URIs if they can contain IDs or tokens. Do not use user ID, order ID, or request ID as metric tags; those values belong in controlled logs/traces instead.

When an error occurs in a long pipeline, place `checkpoint("order.load.after-db")` at a meaningful boundary. Avoid enabling global operator debugging in production without evaluating cost; it can increase CPU overhead and memory usage.

## 11. Reading Dashboards by Correlation

A minimal dashboard should have panels for:

| Panel | Meter/Quantity |
| --- | --- |
| Request rate | HTTP requests/s |
| Error rate | 4xx/5xx by route |
| p50/p95/p99 | HTTP latency and downstream latency |
| Scheduler active/pending | `app.io.scheduler.tasks.active/pending` |
| Scheduler throughput | completed tasks/s and submitted tasks/s |
| Application queue | depth, capacity, rejected, wait time |
| R2DBC pool | acquired, idle, pending, max allocated |
| WebClient pool | active, idle, pending, pending acquire time |
| Heap/GC | heap used, GC pause, allocation |
| Buffer | JVM direct/mapped pools and Netty active/used direct memory |
| Event loop | pending tasks and thread dump when needed |

Put panels on the same time range and slice by instance/region/route when tags have low cardinality. Do not compare a current gauge against p99 from an hour ago and conclude causation.

Alerts should be based on sustained duration and impact:

- p99 continuously exceeding SLO.
- Error/timeout rate rising.
- R2DBC pending acquires persisting continuously or pool acquire timeouts occurring.
- Queue depth climbing and rejected count starting to rise.
- Scheduler pending rising alongside latency.
- Active direct memory climbing continuously after workload drops.
- Event loop pending tasks rising alongside HTTP latency.

A pending count spiking for a few milliseconds is not necessarily an incident. Alerts need duration, thresholds, baselines, and runbooks.

## 12. Diagnostic Workflow When Latency Increases

Proceed in order to isolate the bottleneck:

1. Confirm scope: one route, one instance, one region, or the whole system?
2. Compare request rate, error rate, and p95/p99 within the same time window.
3. Check CPU, GC, heap, thread count, and event loop.
4. Check Scheduler active/pending/completed and application queues.
5. Check R2DBC/WebClient pool pending counts and acquire latency.
6. Check database query latency, locks, slow queries, and remote dependencies.
7. Check heap/direct buffer metrics if memory is climbing.
8. Use thread dumps, JFR, or a profiler to verify hypotheses.
9. Change one variable in a controlled manner, then compare before/after metrics.

### 12.1. Symptom Matrix

| Symptom | Accompanying Signals | Investigation Direction |
| --- | --- | --- |
| Latency up, CPU high | Scheduler pending/active rising | CPU saturation, heavy loops, excessive concurrency |
| Latency up, CPU low | R2DBC pending rising | Pool exhausted, queries/transactions holding connections too long |
| High HTTP latency, event loop pending up | Thread dump shows blocking calls | Blocking I/O on the event loop, locks, or synchronized blocks |
| Queue depth climbs endlessly | rejected rising, low consumer throughput | Producer outpaces consumer, failing consumer, or slow downstream |
| Active direct memory climbs continuously | traffic drops but active does not drop | buffer ownership/release, leaks, or slow-reading clients |
| Heap rising, frequent GC | large objects/collections | unbounded queues, collectList, caches holding references |
| Remote calls slow | WebClient pending acquire rising | remote connection pool, remote service, or timeouts |
| Tasks completing slowly | tasks.active high, CPU low | tasks waiting on I/O/locks or blocking on an unsuitable Scheduler |

## 13. Runbook: Quick Checks via Actuator

List meters:

~~~bash
curl http://localhost:8080/actuator/metrics
~~~

Inspect HTTP requests:

~~~bash
curl http://localhost:8080/actuator/metrics/http.server.requests
~~~

Inspect R2DBC pool pending:

~~~bash
curl http://localhost:8080/actuator/metrics/r2dbc.pool.pending
~~~

Inspect JVM buffers:

~~~bash
curl http://localhost:8080/actuator/metrics/jvm.buffer.memory.used
~~~

Inspect scheduler metric:

~~~bash
curl http://localhost:8080/actuator/metrics/app.io.scheduler.tasks.pending
~~~

Inspect Prometheus exposition:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

Meter names on the metrics endpoint use dots. Prometheus may normalize them to snake_case. If a meter does not appear, check dependencies/registry, whether the meter has been created yet, whether metrics are enabled on the corresponding client/pool, and whether the actuator endpoint is exposed.

`/actuator/metrics` is a point-in-time diagnostic endpoint; Prometheus should scrape `/actuator/prometheus`. Secure management endpoints and never expose endpoints with internal details to public networks.

## 14. Additional Debugging Tools

| Tool | Use When |
| --- | --- |
| Thread dump | threads are blocked, deadlocked, or event loop is unresponsive |
| Heap dump | heap is growing or objects/collections are retained |
| Java Flight Recorder | analyzing CPU, allocations, locks, GC, sockets, and thread events |
| async-profiler | CPU flame graphs or allocation profiling |
| BlockHound | detecting blocking calls on non-blocking threads in test/dev |
| Netty leak detection | suspecting ByteBufs are retained or improperly released |
| Database slow query log | slow queries, locks, or missing indexes |
| Prometheus/Grafana | trends, correlations, and time-based alerting |

Thread dumps do not show every task sitting inside a queue. Heap dumps are also not the sole tool for analyzing direct native memory. Use the right tool for the right resource.

## 15. Complete Demo: Spring Boot 3.5, WebFlux, and Actuator

The demo provides three workload groups:

- `GET /api/work?count=8`: executes tasks on an instrumented Scheduler.
- `GET /api/items`: reads data from H2 via R2DBC to generate connection pool activity.
- `POST /api/queue` and `POST /api/queue/poll`: enqueues/dequeues work from a bounded queue with depth, capacity, wait, and rejected metrics.

The project uses Java 17, Spring Boot 3.5.6, Micrometer, Reactor Core Micrometer, Prometheus, and H2 R2DBC.

### 15.1. Project Structure

~~~text
reactive-observability-lab/
  settings.gradle
  build.gradle
  src/main/
    java/demo/observability/
      ObservabilityApplication.java
      SchedulerConfiguration.java
      WorkService.java
      WorkController.java
      QueueTelemetry.java
      QueueController.java
      ItemService.java
      ItemController.java
      QueueRequest.java
    resources/
      application.properties
      schema.sql
      data.sql
  src/test/java/demo/observability/
      ObservabilityIntegrationTest.java
      QueueTelemetryTest.java
~~~

### 15.2. settings.gradle

~~~groovy
rootProject.name = 'reactive-observability-lab'
~~~

### 15.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    implementation 'io.projectreactor:reactor-core-micrometer'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    runtimeOnly 'io.r2dbc:r2dbc-h2'
    runtimeOnly 'io.r2dbc:r2dbc-pool'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management picks compatible Micrometer, Reactor, and driver versions. Do not manually override reactor-core-micrometer to a version different from the Reactor Core managed by Boot.

### 15.4. application.properties

~~~properties
spring.application.name=reactive-observability-lab

spring.r2dbc.url=r2dbc:h2:mem:///observability?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.username=sa
spring.r2dbc.password=
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=2
spring.r2dbc.pool.max-size=8
spring.r2dbc.pool.max-acquire-time=3s
spring.sql.init.mode=always

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.tags.application=reactive-observability-lab
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=50ms,100ms,250ms,500ms,1s
~~~

In-memory H2 is for demo purposes only. A pool size of 8 is not a universal production template for every database; it helps observe pool behavior in the lab.

### 15.5. schema.sql

~~~sql
CREATE TABLE observed_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
~~~

### 15.6. data.sql

~~~sql
INSERT INTO observed_items (name) VALUES ('alpha');
INSERT INTO observed_items (name) VALUES ('beta');
INSERT INTO observed_items (name) VALUES ('gamma');
~~~

### 15.7. ObservabilityApplication.java

~~~java
package demo.observability;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            ObservabilityApplication.class,
            args
        );
    }
}
~~~

### 15.8. SchedulerConfiguration.java

~~~java
package demo.observability;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
public class SchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    Scheduler observedIoScheduler(MeterRegistry registry) {
        Scheduler delegate =
            Schedulers.newBoundedElastic(
                4,
                100,
                "observed-io"
            );

        return Micrometer.timedScheduler(
            delegate,
            registry,
            "app.io"
        );
    }
}
~~~

The bean is disposed when the context closes. Any pipeline that wants to be measured under the `app.io` prefix must use this Scheduler bean. If a piece of code calls `Schedulers.boundedElastic()` directly, those tasks will not pass through the wrapper above.

### 15.9. WorkService.java

~~~java
package demo.observability;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

@Service
public class WorkService {
    private final Scheduler scheduler;
    private final MeterRegistry registry;

    public WorkService(
            @Qualifier("observedIoScheduler") Scheduler scheduler,
            MeterRegistry registry) {
        this.scheduler = scheduler;
        this.registry = registry;
    }

    public Flux<Integer> calculate(int count) {
        return Flux.range(1, count)
            .flatMapSequential(value ->
                Mono.fromCallable(() -> {
                    // Simulate a blocking dependency in the lab.
                    Thread.sleep(20);
                    return value * value;
                }).subscribeOn(scheduler),
                4
            )
            .name("demo.work")
            .tag("operation", "square")
            .tap(Micrometer.metrics(registry))
            .checkpoint("demo.work.calculate");
    }
}
~~~

`flatMapSequential` allows up to four concurrent tasks while preserving result ordering. The sleep only simulates an isolated legacy blocking call; production should prefer non-blocking APIs.

### 15.10. WorkController.java

~~~java
package demo.observability;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/work")
public class WorkController {
    private final WorkService service;

    public WorkController(WorkService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<Integer> calculate(
            @RequestParam(defaultValue = "8") int count) {
        if (count < 1 || count > 100) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "count must be between 1 and 100"
            );
        }
        return service.calculate(count);
    }
}
~~~

### 15.11. QueueTelemetry.java

~~~java
package demo.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Optional;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class QueueTelemetry {
    private record Entry(String value, long enqueuedAtNanos) {}

    private final ArrayBlockingQueue<Entry> queue =
        new ArrayBlockingQueue<>(64);

    private final Counter rejected;
    private final Timer waitTime;

    public QueueTelemetry(MeterRegistry registry) {
        Gauge.builder(
            "app.work.queue.depth",
            queue,
            q -> q.size()
        ).register(registry);

        Gauge.builder(
            "app.work.queue.capacity",
            queue,
            q -> q.size() + q.remainingCapacity()
        ).register(registry);

        this.rejected =
            registry.counter("app.work.queue.rejected");

        this.waitTime =
            registry.timer("app.work.queue.wait");
    }

    public boolean offer(String value) {
        boolean accepted = queue.offer(
            new Entry(value, System.nanoTime())
        );

        if (!accepted) {
            rejected.increment();
        }
        return accepted;
    }

    public Optional<String> poll() {
        Entry entry = queue.poll();
        if (entry == null) {
            return Optional.empty();
        }

        waitTime.record(
            System.nanoTime() - entry.enqueuedAtNanos(),
            TimeUnit.NANOSECONDS
        );
        return Optional.of(entry.value());
    }

    public int depth() {
        return queue.size();
    }

    public int capacity() {
        return queue.size() + queue.remainingCapacity();
    }

    public double rejectedCount() {
        return rejected.count();
    }
}
~~~

The queue has a capacity of 64. When full, `offer` returns false and increments the counter; it does not silently drop data. The depth/capacity Gauges provide snapshots, and the wait Timer measures how long an item stays in the queue.

### 15.12. QueueRequest.java

~~~java
package demo.observability;

public record QueueRequest(String value) {
}
~~~

### 15.13. QueueController.java

~~~java
package demo.observability;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/queue")
public class QueueController {
    private final QueueTelemetry queue;

    public QueueController(QueueTelemetry queue) {
        this.queue = queue;
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> enqueue(
            @RequestBody QueueRequest request) {
        boolean accepted = queue.offer(request.value());

        Map<String, Object> body = Map.of(
            "accepted", accepted,
            "depth", queue.depth(),
            "capacity", queue.capacity()
        );

        return ResponseEntity
            .status(accepted
                ? HttpStatus.ACCEPTED
                : HttpStatus.TOO_MANY_REQUESTS)
            .body(body);
    }

    @PostMapping("/poll")
    public Map<String, Object> poll() {
        var value = queue.poll();

        return Map.of(
            "present", value.isPresent(),
            "value", value.orElse(""),
            "depth", queue.depth()
        );
    }

    @GetMapping
    public Map<String, Object> stats() {
        return Map.of(
            "depth", queue.depth(),
            "capacity", queue.capacity(),
            "rejected", queue.rejectedCount()
        );
    }
}
~~~

### 15.14. ItemService.java

~~~java
package demo.observability;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class ItemService {
    private final DatabaseClient databaseClient;

    public ItemService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<String> findAll() {
        return databaseClient
            .sql("SELECT name FROM observed_items ORDER BY id")
            .map((row, metadata) ->
                row.get("name", String.class)
            )
            .all();
    }
}
~~~

### 15.15. ItemController.java

~~~java
package demo.observability;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<String> findAll() {
        return service.findAll();
    }
}
~~~

When calling this endpoint, the Boot R2DBC pool can produce acquired/allocated/idle/pending meters to observe connection usage. If those meters do not appear in another environment, check the r2dbc-pool dependency, pool enablement, and Actuator R2DBC metrics auto-configuration.

### 15.16. QueueTelemetryTest.java

~~~java
package demo.observability;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class QueueTelemetryTest {

    @Test
    void queueDepthAndOverflowAreMeasured() {
        SimpleMeterRegistry registry =
            new SimpleMeterRegistry();

        QueueTelemetry queue = new QueueTelemetry(registry);

        for (int i = 0; i < 64; i++) {
            assertTrue(queue.offer("task-" + i));
        }

        assertFalse(queue.offer("overflow"));
        assertEquals(64.0,
            registry.get("app.work.queue.depth")
                .gauge().value());
        assertEquals(1.0,
            registry.get("app.work.queue.rejected")
                .counter().count());

        assertTrue(queue.poll().isPresent());
        assertEquals(63, queue.depth());

        registry.close();
    }
}
~~~

### 15.17. ObservabilityIntegrationTest.java

~~~java
package demo.observability;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ObservabilityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    MeterRegistry registry;

    @Test
    void workEndpointProducesSchedulerAndReactorMetrics() {
        client.get()
            .uri("/api/work?count=4")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Integer.class)
            .contains(1, 4, 9, 16);

        assertNotNull(
            registry.find("app.io.scheduler.tasks.submitted")
                .counter()
        );

        assertTrue(
            registry.find("demo.work.subscribed")
                .counter()
                .count() > 0
        );
    }

    @Test
    void databaseEndpointUsesR2dbcPool() {
        client.get()
            .uri("/api/items")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(String.class)
            .contains("alpha", "beta", "gamma");

        assertNotNull(
            registry.find("r2dbc.pool.allocated").gauge()
        );
    }

    @Test
    void actuatorMetricsEndpointIsAvailable() {
        client.get()
            .uri("/actuator/metrics")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.names").isArray();
    }
}
~~~

The integration tests issue real HTTP requests to the application running on a random port. The queue unit test uses a standalone SimpleMeterRegistry. The tests prove that metrics are registered and endpoints work; they do not replace load tests or real saturation testing.

### 15.18. Running and Observing the Application

Requires Java 17 and Gradle:

~~~bash
gradle test
gradle bootRun
~~~

Call the Scheduler workload:

~~~bash
curl "http://localhost:8080/api/work?count=8"
~~~

Expected body:

~~~json
[1,4,9,16,25,36,49,64]
~~~

Read the database via R2DBC:

~~~bash
curl http://localhost:8080/api/items
~~~

Expected body:

~~~json
["alpha","beta","gamma"]
~~~

Add an item to the queue:

~~~bash
curl -i -X POST http://localhost:8080/api/queue \
  -H "Content-Type: application/json" \
  -d '{"value":"task-1"}'
~~~

Check queue status:

~~~bash
curl http://localhost:8080/api/queue
~~~

Poll an item from the queue:

~~~bash
curl -X POST http://localhost:8080/api/queue/poll
~~~

Inspect scheduler metrics:

~~~bash
curl http://localhost:8080/actuator/metrics/app.io.scheduler.tasks.submitted
~~~

Inspect pool metrics:

~~~bash
curl http://localhost:8080/actuator/metrics/r2dbc.pool.pending
~~~

Inspect Prometheus:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

Meter names and values change based on request counts and scrape timing. There is no fixed stdout for all metrics.

## 16. Configuring and Observing the Reactor Netty Client

If an application creates its own WebClient with Reactor Netty, it can configure a bounded pool and enable metrics:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("observed-remote")
        .maxConnections(40)
        .pendingAcquireMaxCount(100)
        .pendingAcquireTimeout(Duration.ofSeconds(3))
        .metrics(true)
        .build();

HttpClient httpClient = HttpClient.create(provider)
    .metrics(true, uri -> uri);

WebClient client = WebClient.builder()
    .clientConnector(
        new ReactorClientHttpConnector(httpClient)
    )
    .build();
~~~

This snippet configures a custom client; in Spring Boot, prefer using the Boot-managed builder and customizing it to preserve registered customizers/observations. Never create a new WebClient/ConnectionProvider per request.

When the application shuts down, dispose client/provider resources according to bean lifecycle. Pool metrics help detect pending acquires and connection saturation; they do not replace latency metrics for remote endpoints.

## 17. Setting Thresholds and Alerts

Do not use the same threshold for every workload. Start from SLOs and baselines, then adjust.

| Signal | Condition Worth Investigating | Next Question |
| --- | --- | --- |
| HTTP p99 | continuously exceeds SLO | which route, which downstream? |
| HTTP 5xx/timeouts | rises above baseline | which instance are errors concentrated on? |
| Scheduler pending | rises persistently with latency | are workers occupied by slow tasks? |
| Queue depth | climbs steadily or stays near capacity | does the consumer have enough throughput? |
| Queue rejected | non-zero or rising rapidly | need admission control or consumer scaling? |
| R2DBC pending | persists continuously | are connections held too long or is the DB slow? |
| Netty pending acquire | rises alongside remote latency | is the remote pool or remote service saturated? |
| Active direct memory | rises continuously after traffic drops | are buffers unreleased? |
| GC pause | rises alongside heap pressure | where are allocations or retained objects? |
| Event loop pending | rises persistently | is there blocking or overly heavy callbacks? |

Some illustrative PromQL queries after scraping Prometheus:

~~~promql
rate(http_server_requests_seconds_count[5m])
~~~

~~~promql
r2dbc_pool_pending
~~~

~~~promql
reactor_netty_connection_provider_pending_connections
~~~

~~~promql
app_work_queue_depth / app_work_queue_capacity
~~~

Metric names in Prometheus may be normalized from Micrometer names. Inspect the actual exposition endpoint before writing queries/alerts.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Looking only at CPU | Misses I/O wait and pool saturation | Combine latency, pending counts, and pools |
| Treating tasks.pending as queue depth | Misinterprets metric scope | Instrument business queues separately |
| Thinking timedScheduler measures every Scheduler | Meters miss some workloads | Use the right wrapper in the pipeline |
| Using Schedulers.enableMetrics() in new code | Uses deprecated API | Use Micrometer.timedScheduler |
| Increasing pool connections to fix slow queries | DB may become even more overloaded | Measure queries, locks, and transaction duration |
| Using unbounded queues | Uncontrolled memory growth | Bounded queues and overflow policies |
| Not counting rejected/dropped work | Silent data loss goes unnoticed | Counters for drops/rejects |
| Treating high used direct memory as a leak | False alarms with pooled allocators | Compare active vs used and watch post-load trends |
| Not instrumenting app buffers/queues | Only total JVM memory is visible | Gauge depth/capacity and wait timers |
| Tagging metrics with userId/requestId | Cardinality explosion | Put IDs into logs/traces |
| Logging full payloads | Leaks sensitive data | Log redacted metadata |
| Exposing all of Actuator publicly | Exposes internal info | Restrict endpoints and protect the management port |
| Creating a new WebClient per request | Pool fragmentation and resource leaks | Reuse clients and ConnectionProviders |
| Using heap dumps to explain all direct memory | Lacks visibility into native allocators | JVM buffer/Netty metrics, JFR/NMT/leak logs |
| Alerting on a single sample | Many false alerts | Use windows, duration, and baselines |
| Having no runbook for alerts | Unclear next investigation steps | Attach owner, queries, and actions to each alert |

## 19. Production Readiness Checklist for Reactive Apps

1. Are Actuator, MeterRegistry, and the scrape/export backend in place?
2. Do HTTP requests have rate, error rate, latency histograms, and route tags?
3. Do key Schedulers have metric wrappers and get injected in the right places?
4. Is Scheduler pending clearly distinguished from application queue depth?
5. Does every queue have capacity, overflow policy, depth, and a rejected counter?
6. Does the R2DBC pool have acquired/idle/pending/max metrics?
7. Does the WebClient/Netty pool have active/idle/pending/acquire latency?
8. Are heap, GC, JVM buffers, and Netty direct memory observed?
9. Are there metrics for dropped/cancelled/retried work?
10. Do logs include traceId/correlation ID and redaction?
11. Do traces show latency per dependency?
12. Are there p95/p99 dashboards and SLO-based alerts?
13. Are Actuator endpoints secured?
14. Are thread dump/JFR/profiling runbooks ready?
15. Have load tests covered slow consumers, pool exhaustion, and queue overflow?
16. Have metric cardinality and scrape costs been verified?
17. Have shutdown/disposal of Schedulers and connection providers been tested?

## 20. Review Questions with Answers

**Question 1. Why can WebFlux still bottleneck without blocking the event loop?**

Because Schedulers, connection pools, queues, databases, and remote services all have finite capacity. Requests can wait on resources even when threads are not blocked.

**Question 2. What does Micrometer.timedScheduler measure?**

It instruments tasks submitted through the Scheduler wrapper, including active/completed/pending/submitted according to the wrapper's semantics.

**Question 3. Why can tasks.pending not be used in place of queue depth?**

tasks.pending reflects immediate tasks that could not start yet because the Scheduler reached capacity; it is not the length of all queues, operators, or application buffers.

**Question 4. Which metric reports requests waiting for an R2DBC connection?**

`r2dbc.pool.pending`.

**Question 5. How do acquired and allocated differ?**

acquired is connections currently in use; allocated is total connections allocated in the pool, including both active and idle.

**Question 6. Why is increasing max-size not always beneficial?**

It can push more concurrent queries into a database already saturated on CPU, I/O, or locks, increasing latency.

**Question 7. How does direct memory differ from heap memory?**

Direct memory resides outside the regular Java heap and is commonly used by NIO/Netty; it has a different lifecycle and diagnostic tooling.

**Question 8. Does rising used.direct.memory prove a leak?**

No. The allocator can keep reserved memory for reuse. You need to inspect active direct memory, post-load trends, and leak diagnostics.

**Question 9. Why must business queues be instrumented separately?**

Because Reactor/Netty does not provide a single global metric for every operator buffer or application-created queue.

**Question 10. Why should requestId not be used as a metric tag?**

Every request creates a new time series, causing cardinality and storage costs to grow sharply. IDs fit logs/traces better.

**Question 11. How do metrics, logs, and traces differ?**

Metrics provide trends/aggregates; logs record events; traces show the path and duration of each span in a request.

**Question 12. When are thread dumps or JFR needed?**

When metrics show symptoms but the root cause—such as blocking, lock contention, CPU hotspots, allocations, or GC—is still unclear.

**Question 13. Why track rejected queue work?**

Depth can stay low if the producer is rejected early. The rejected counter helps detect lost/refused work.

**Question 14. Does the Actuator metrics endpoint replace Prometheus?**

No. `/actuator/metrics` serves interactive diagnostics; metrics backends should scrape/export from registry endpoints like `/actuator/prometheus`.

## 21. Key Takeaways

- Observing a reactive system must cover HTTP, Reactor pipelines, Schedulers, queues, connection pools, and buffers.
- `Micrometer.timedScheduler` measures a specific Scheduler wrapper; tasks must go through that wrapper.
- `tasks.pending` is not general queue depth.
- R2DBC pools expose acquired/allocated/idle/pending/max metrics.
- Reactor Netty pools and ByteBufAllocator have their own metrics when instrumented.
- Compare active and used direct memory to avoid false leak conclusions.
- Queues need capacity, wait time, and rejected/dropped metrics.
- Use metrics for trends, logs for events, traces for request paths, and profiling to find root causes.
- Keep tag cardinality low, protect Actuator, and pair alerts with runbooks.
- Diagnose by correlating latency, throughput, pending counts, errors, and resource saturation.

## 22. Official Documentation

1. [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): JVM, executor, HTTP, Actuator metrics endpoint, and Micrometer integration.
2. [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): exposure, access control, and endpoint security.
3. [Spring Boot 3.5 — R2DBC SQL](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): ConnectionFactory, configuration, and R2DBC support.
4. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): pool max-size, acquire timeout, and R2DBC configuration.
5. [Spring Boot 3.5 — ConnectionPoolMetrics Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/metrics/r2dbc/ConnectionPoolMetrics.html): metric binder for R2DBC ConnectionPool.
6. [Project Reactor 3.8.7 — Exposing Reactor Metrics](https://projectreactor.io/docs/core/3.8.7/reference/metrics.html): reactor-core-micrometer, timedScheduler, sequence metrics, and Observation.
7. [Project Reactor — Metrics Details](https://projectreactor.io/docs/core/release/reference/metrics-details.html): Scheduler/publisher meter names and tags.
8. [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): Scheduler types, boundedElastic, parallel, and threading model.
9. [Reactor Netty — Reference Guide](https://projectreactor.io/docs/netty/release/reference/index.html): connection pool, event loop, ByteBufAllocator metrics, and leak detection.
10. [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): meters, tags, timers, gauges, counters, and cardinality.
11. [Spring Boot — Prometheus Endpoint](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): Prometheus registry and exposition endpoint.
12. [OpenJDK — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html): recording and analyzing runtime events.
