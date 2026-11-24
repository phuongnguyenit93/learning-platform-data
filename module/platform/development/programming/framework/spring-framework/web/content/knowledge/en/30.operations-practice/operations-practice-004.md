# Diagnosing Thread Starvation, Connection-Pool Exhaustion, Memory Pressure, and Event-Loop Blocking in Spring Web

## 1. Why are these four problems easily confused?

A Spring application can return HTTP 503, 500, timeouts, or respond very slowly even when CPU is low. The cause is not necessarily in the controller that just appeared in the logs. A request traverses many resources: accepting threads, schedulers, queues, HTTP connections to other services, JDBC connections, heap memory, direct memory, and data serialization/deserialization steps.

Four incident classes commonly produce similar symptoms:

1. **Thread starvation:** the threads needed to do work are busy or waiting too long; new requests queue up, get rejected, or time out.
2. **Connection-pool exhaustion:** HTTP client, JDBC, or server connection limits are exhausted; threads may be waiting to acquire a connection without using much CPU.
3. **Memory pressure/OOM:** heap, direct buffers, metaspace, native thread stacks, or container RSS approaches its limit, leading to frequent GC, OOM, or container kills.
4. **Event-loop blocking:** blocking code executes on the small, critical Reactor Netty/WebFlux threads, slowing down many unrelated requests.

You cannot determine the cause from a `TimeoutException` message or thread name alone. The right method is **measure symptoms → identify the constrained resource → gather independent evidence → fix one cause → re-measure under comparable load**.

### 1.1 Two common execution models

| Characteristic | Spring MVC + Servlet (typically Tomcat) | Spring WebFlux + Reactor Netty |
| --- | --- | --- |
| HTTP semantics | Controllers typically run on Servlet worker threads | Reactive handlers, non-blocking event loop |
| Thread count | Usually has a relatively large pool to absorb blocking operations | Few event-loop threads; must never block them |
| Handling blocking JDBC | Typically uses Servlet workers; pool must be bounded | Must offload from event loop or use reactive drivers |
| Outbound HTTP calls | Can use RestClient/RestTemplate or WebClient | Non-blocking WebClient is the natural choice |
| Typical bottlenecks | Worker threads, accept queue, HikariCP, outbound HTTP | Event-loop blocking, connection provider, Scheduler, buffers |
| Failure signals | Busy threads, growing queues, connection waits | Event-loop latency, pool acquire queue, stalled subscribers |

An MVC application **can still use WebClient** and therefore also has a Reactor Netty event loop on the HTTP client side. Do not infer that seeing `reactor-http-nio-*` means the whole application runs WebFlux. Spring Boot may choose MVC when both starters are present, depending on configuration. Always check dependencies, runtime behavior, and stack traces.

### 1.2 Distinguishing CPU-bound slowness from resource-wait slowness

If CPU is sustained high alongside `RUNNABLE` threads performing continuous computation, look for hot paths, loops, serialization, or GC. If CPU is low while latency is high, suspect waiting on sockets/DB, queues, mutexes, pools, or condition waits. Measure **wait times and queue depths** rather than assuming "low CPU means healthy."

For example, a request takes 300 ms total, spending 240 ms waiting for a database connection, 30 ms running SQL, 20 ms in business logic, and 10 ms converting JSON. Optimizing the 20 ms Java code will not fix most of the latency. Building a per-phase timeline helps prioritize the right resources.

## 2. Evidence-based incident response workflow

When timeout rates climb, follow a disciplined order:

1. **Scope the incident:** all endpoints or one route? across every instance/pod? since which config deployment? error rate, p50/p95/p99, throughput, in-flight requests, and error breakdown.
2. **Protect the running system:** if needed, apply admission limits, backpressure, shed non-critical traffic, or roll back a recent release per incident policy. Do not blindly raise every limit.
3. **Collect metrics, logs, traces, and JVM evidence simultaneously:** timestamps must align. A snapshot captured when the system is idle may miss the bottleneck.
4. **Correlate JVM/HTTP/database signals:** busy workers, active/pending connections, connection acquire wait, GC pauses, used heap/direct memory, thread count, and event-loop health.
5. **Capture multiple spaced thread dumps/JFR recordings:** distinguish a thread momentarily sleeping from a group of threads repeatedly stuck at the same call.
6. **Check external dependencies:** DB slow queries/locks, upstream API latency, DNS, load balancer, proxy, network RTT, CPU throttling/GC.
7. **Form a falsifiable hypothesis:** if the connection pool is the bottleneck, lengthening SQL or holding the response body longer will drive active=max and grow pending; if a code fix releases connections earlier, pending must drop under the same load.
8. **Make a small change and re-verify:** inspect p95/p99, error rate, memory, pool waiters, and resource headroom. Record the decision and outcome.

Every hypothesis must answer three questions: **what evidence supports it, what evidence contradicts it, and what observation changes after the fix?**

### 2.1 Signals to capture immediately

| Group | Metrics/evidence to inspect | How to interpret |
| --- | --- | --- |
| HTTP | RPS, in-flight requests, p95/p99 latency, 429/503/5xx, timeouts by route | Separate ingress overload from an abnormal downstream |
| Servlet | Tomcat busy/current/max threads, request queue, connection counts | Busy near max plus growing queue suggests worker starvation |
| Thread/JVM | thread count, daemon count, thread dumps, per-thread CPU, deadlocks | Stacks show whether threads block on I/O, locks, waits, or run CPU |
| JDBC/Hikari | active, idle, pending, acquire timeout, query duration, DB connections | Active near max + growing pending signals connection shortage or long-held connections |
| Outbound HTTP | Reactor Netty active/idle/pending connections, acquire timeouts, connect/response timeouts | Distinguish failure to acquire a connection from slow remote responses |
| Memory | heap used/committed/max, GC pause/rate, direct buffers, RSS/container limit | Distinguish heap retention from native/direct memory pressure |
| Event loop | event-loop responsiveness, thread dump stacks, long/blocking tasks, BlockHound | One blocking call can stall many sockets sharing that loop |
| Dependencies | DB locks, slow SQL, upstream p95, connection resets, DNS | Do not tune pools when the root cause is a dependency server |

Metrics should be collected over time (time series) with sensible tags. Avoid dynamic tags like userId, orderId, or raw URLs with millions of variants; high cardinality can exhaust monitoring memory.

## 3. Gathering evidence with Spring Boot Actuator and the JVM

### 3.1 Actuator: discover which metrics actually exist

Spring Boot Actuator and Micrometer expose groups of HTTP, JVM, datasource, server, and driver metrics. **Exact metric names depend on version, libraries, and configuration**: first call `/actuator/metrics` to list available meters, then query existing metrics.

Minimal example config for an internal environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  metrics:
    tags:
      application: order-api
```

This is an example configuration for a Spring Boot app with `spring-boot-starter-actuator`; the `prometheus` endpoint also requires its registry dependency, such as `io.micrometer:micrometer-registry-prometheus`. Metrics endpoints are not always exposed by default. Expose them only on authenticated/authorized management networks and never reveal runtime internals to public users.

Verification commands from an authorized host:

```bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/jvm.threads.live
curl -s http://localhost:8080/actuator/metrics/jvm.memory.used
curl -s http://localhost:8080/actuator/metrics/jvm.gc.pause
curl -s http://localhost:8080/actuator/metrics/http.server.requests
```

Do not assume hardcoded outputs for these commands: they depend on runtime state. For instance, `jvm.memory.used` may return multiple measurements/tags by `area` and `id`; to isolate heap, query by tag if the metric supports it. With Prometheus, metric names may be converted to underscores with unit suffixes; Actuator `/metrics` uses the **base meter name**.

Useful metrics **when registered**:

- `tomcat.threads.busy`, `tomcat.threads.current`, `tomcat.threads.config.max` for Tomcat; some versions/setups require enabling the MBean registry.
- `hikaricp.connections.active`, `hikaricp.connections.idle`, `hikaricp.connections.pending` for HikariCP.
- `jdbc.connections.active` for certain instrumented DataSources.
- `reactor.netty.connection.provider.active.connections`, `...idle.connections`, `...pending.connections`, `...pending.connections.time` when Reactor Netty ConnectionProvider metrics are enabled.
- `jvm.memory.used`, `jvm.memory.max`, `jvm.buffer.memory.used`, `jvm.threads.live`, `jvm.gc.pause`, and HTTP server metrics.

Never look at a single current value and conclude a leak: watch the trend under load, after GC, when traffic drops, and compare against a baseline.

### 3.2 Capturing thread dumps with jcmd

Using JDK 17+/21's `jcmd` tool, run under an account permitted to access the target Java process. You must know the exact PID inside the VM/container:

```bash
jcmd -l
jcmd <PID> Thread.print -l > thread-1.txt
```

`<PID>` is a placeholder for the actual process ID; the two lines above are command templates, not literal commands to run with placeholders. Check supported subcommands with `jcmd <PID> help Thread.print` for your JDK. Capture 2–3 thread dumps spaced a few seconds apart **while the incident is happening**; avoid treating a single point-in-time stack as definitive proof of root cause.

Reading thread dumps:

- `RUNNABLE` does not always mean CPU consumption: a Java thread in native socket I/O can appear as RUNNABLE. Combine with per-thread CPU/JFR.
- `WAITING` / `TIMED_WAITING` can be normal idle thread-pool waiting; check **where it is waiting** and how many requests are affected.
- `BLOCKED` usually involves monitors/`synchronized`; stacks and `locked ownable synchronizers` help trace locks.
- Look for many `http-nio-*-exec-*` stuck in JDBC, RestTemplate, locks, or remote calls; look for `reactor-http-nio-*` stuck in `Thread.sleep`, `Future.get`, JDBC, or blocking clients.
- If hundreds of requests wait on a connection pool, thread dumps show **where they block**, while pool metrics confirm resource exhaustion.

In production, thread dumps can contain method names, file paths, and occasionally sensitive data on stacks; store with restricted permissions and follow data-protection procedures. JFR/thread dumps are less invasive than heap dumps, though they still carry overhead.

### 3.3 Java Flight Recorder (JFR)

JFR provides a timeline of CPU, allocation, GC, locks, sockets, and many Java events. Example short 60-second recording during issue reproduction:

```bash
jcmd <PID> JFR.start name=web-incident settings=profile duration=60s filename=/tmp/web-incident.jfr
jcmd <PID> JFR.check
```

The path must be writable by the process; on Windows replace `/tmp/...` with a suitable path. With `duration`, the recording finalizes on schedule; `JFR.dump` or `JFR.stop` can be used as needed. Open the output with JDK Mission Control (JMC) or an approved JFR analysis tool.

JFR helps answer: which threads consume CPU, which socket reads take long, where allocations happen, which GC pauses align with p99 spikes, and whether real lock contention exists. Use `settings=profile` for limited durations because event volume/overhead is higher than `default`; check your environment's diagnostic policies.

### 3.4 GC, heap, and native memory

Commonly useful read-only commands (subject to JDK and process permissions):

```bash
jcmd <PID> GC.heap_info
jcmd <PID> VM.flags
jcmd <PID> VM.native_memory summary
```

`VM.native_memory summary` only provides full details if **Native Memory Tracking** was enabled at JVM startup, e.g., `-XX:NativeMemoryTracking=summary`, which incurs overhead. Calling the command does not enable NMT retroactively. If the app dies via orchestrator OOMKilled, the JVM may not have time to throw `OutOfMemoryError` or write a heap dump; check container memory limits and platform logs.

`GC.class_histogram` and `GC.heap_dump` can cause significant pauses, produce large files, and contain sensitive data. Run them only under a plan verifying disk space, timing, and authorization. Never trigger a heap dump when a machine is already running out of disk or memory.

## 4. Thread starvation in Spring MVC/Servlet

### 4.1 The thread starvation model

Tomcat maintains a worker pool to execute HTTP requests. If 200 threads are all waiting on DB/HTTP/locks, new requests must queue. Latency rises even while CPU stays low.

```text
Incoming requests
        |
        v
Tomcat accept/connection handling
        |
        v
Request workers (busy: 200 / max: 200)
   |      |      |
   v      v      v
 DB wait HTTP wait Lock wait
        |
        v
Pending work accumulates -> high latency/timeouts
```

An estimate from Little's Law for a steady-state system:

**Approximate concurrent requests = arrival rate (requests/sec) × average time in system (sec).**

For example, 100 RPS × 0.2 s ≈ 20 in-flight requests. If a dependency slows to 2 s while RPS stays 100, concurrency climbs toward ~200. This is an **average estimate**, not an exact formula for sizing thread pools; bursts, queues, CPU, async processing, multiple upstreams, and container limits can shift the outcome.

### 4.2 Evidence to cross-check

- `tomcat.threads.busy` climbs near max while request latency and pending queues rise together.
- Repeated thread dumps show many workers inside `HikariPool.getConnection`, `SocketInputStream.read`, `HttpURLConnection`, or locks.
- Do database metrics show active=max + waiters/pending? If so, thread starvation may **be a symptom of JDBC connection exhaustion**.
- CPU near 100% with runnable threads computing continuously indicates more than I/O starvation.
- Did the request rate surge after a deploy or retry storm? Evaluate the traffic source before raising thread counts.

### 4.3 Fixing at the right layer

**If work is just waiting on slow HTTP/DB:** optimize queries, shorten transactions, set timeouts per dependency, apply circuit breakers/concurrency limits, and curb synchronized retries. Adding threads can increase concurrent waiters and push more pressure onto the DB.

**If CPU is the true bottleneck:** profile hot methods, cut unnecessary serialization/parsing, and bound parallelism to CPU count; adding workers does not create more CPU compute time.

**If pool queues grow too deep:** bound request concurrency and reject early within system capacity; return appropriate status codes (e.g., 429 for rate limits, 503 for temporary overload) with Retry-After per contract.

**If running many async tasks:** `@Async` and `Callable`/`DeferredResult` need a managed executor with bounded queues, timeouts, and an explicit rejection policy. Never use an unbounded default pool in production.

Example `ThreadPoolTaskExecutor` configuration for controlled async work:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class WorkerPoolConfig {
    @Bean
    ThreadPoolTaskExecutor blockingWorkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("blocking-work-");
        return executor;
    }
}
```

This is a Spring configuration class (placed in a component-scanned package), not a standalone `main` program. The numbers 8/16/100 are illustrative; capacity must be determined via profiling and resource limits. This bean **does not automatically change the Tomcat worker pool** or WebFlux event loop; it is only used where the application injects and invokes the executor or configures it on a specific async component.

## 5. Connection-pool exhaustion: identify which pool

An application can simultaneously use multiple connection types:

- **Inbound server connections/workers:** Tomcat/Netty accepting client requests.
- **JDBC/HikariCP:** acquiring a connection from the pool to run SQL/transactions.
- **Reactor Netty outbound HTTP pool:** `WebClient` using `ConnectionProvider` to reuse HTTP connections.
- **Brokers, Redis, or other clients:** each driver has its own limits and metrics.

A "connection timeout" message can occur at DNS, TCP connect, waiting for a pool connection, awaiting a response, or inside the database. Never lump them into one generic timeout.

### 5.1 HikariCP holding connections too long

Typical signs: active near maximum, idle at 0, pending threads rising, `SQLTransientConnectionException`, or log "Connection is not available, request timed out." Possible causes:

- Each transaction drags on due to slow queries, row locks, or waiting on remote HTTP while holding a DB connection.
- Code opens connections/ResultSets without closing them properly, or response streaming is tied to a long transaction.
- The DB reached its connection limit or refuses new sessions.
- The pool is too small for the **legitimately needed** concurrent transactions, or load exceeds DB capacity.
- A retry storm spawns many new transactions before older ones finish.

`@Transactional` does not necessarily hold a connection from start to finish in every driver/transaction, yet it commonly **holds a connection once the transaction touches the DB**. Avoid multi-second remote API calls inside a DB transaction without a compelling reason.

### 5.2 Reactor Netty connection pool

`WebClient` backed by Reactor Netty `HttpClient` operates with a pool retaining connections per remote host. When active connections reach `maxConnections`, subsequent requests wait in `pending acquire`. If the wait exceeds the timeout or the pending queue fills, the client fails acquisition before sending the request.

Distinguish clearly:

- `pendingAcquireTimeout`: time spent waiting to borrow a connection from the pool.
- `CONNECT_TIMEOUT_MILLIS`: deadline to establish the TCP connection.
- `responseTimeout`: wait limit for response behavior per HTTP client config.
- `Mono.timeout(...)`: Reactor-level publisher deadline; can cancel upstream.
- `maxIdleTime` / `maxLifeTime`: connection retention/reuse policies, not server processing timeouts.

Do not rely on a memorized "default pool size" because it varies by Reactor Netty version, global configuration, CPU count, and how `ConnectionProvider` is created. Always verify runtime metrics and version.

### 5.3 Example bounded outbound HTTP pool configuration

This is a Spring Boot configuration with `spring-webflux` and the Reactor Netty connector, usable for outbound `WebClient` even inside an MVC application:

```java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
class OutboundHttpClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider inventoryConnectionProvider() {
        return ConnectionProvider.builder("inventory-api")
                .maxConnections(50)
                .pendingAcquireMaxCount(100)
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .metrics(true)
                .build();
    }

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder,
                                 ConnectionProvider inventoryConnectionProvider) {
        HttpClient http = HttpClient.create(inventoryConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
                .responseTimeout(Duration.ofSeconds(3));

        return builder.clone()
                .baseUrl("https://inventory.example")
                .clientConnector(new ReactorClientHttpConnector(http))
                .build();
    }
}
```

Spring manages the `ConnectionProvider` bean and calls `dispose` when the context closes. Replace the domain with a real configured address and add TLS/auth if the endpoint requires it. `metrics(true)` requires matching Micrometer dependencies. Do not share a single connection provider merely to "solve" pool exhaustion across partners with completely different profiles; size resources to need and assign pool ownership.

**The 50/100/2s/3s limits are illustrative only.** If upstream does not respond within 3 seconds, timeouts occur even with spare connections; raising `maxConnections` then can overload upstream further. Measure active/pending connections, duration, error codes, TLS/connect time, and throughput.

### 5.4 Returning connections to the pool cleanly

An HTTP connection requires the response body to be consumed or released properly to be reused. With `WebClient.retrieve().bodyToMono(...)`, Spring normally manages decoding and body lifecycle. With lower-level `exchangeToMono` / `exchangeToFlux`, consume the body inside that function; do not return `ClientResponse` for handling outside the callback lifecycle unless you understand the API. When working directly with pooled `DataBuffer`s, release unused buffers per Spring's rules.

**Signs of leaked/held connections:** active persistently pinned near max even after requests "finished" at the business layer, pending continuously climbing, and thread dumps or leak detectors showing uncompleted response bodies. Alternatively, a streaming endpoint may intentionally hold connections open; separate long-lived streams from short requests in capacity planning.

## 6. Memory pressure: heap, direct memory, metaspace, and containers

### 6.1 JVM memory is more than -Xmx

A Java process's RSS can include:

```text
Container memory budget / process RSS
       |
       +-- Java heap (-Xmx) / object graph
       +-- JVM metaspace / class metadata
       +-- Code cache / JIT
       +-- Platform thread stacks
       +-- Direct / off-heap buffers (NIO/Netty)
       +-- JNI/native libraries & allocator overhead
       +-- JVM runtime structures and other native regions
```

Setting `-Xmx` too close to the container memory limit leaves no room for native/direct/thread stacks; the container can be OOMKilled even before the Java heap fills up. `jvm.memory.used` does not measure total RSS. Conversely, heap usage rising to a plateau and stabilizing after GC can be normal and **does not by itself prove a memory leak**.

### 6.2 Distinguishing failure modes

| Symptom | Hypothesis to verify | Evidence |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Heap genuinely too small or objects retained too long | Heap/GC, allocation rate, histogram, and dominator tree when a heap dump exists |
| `OutOfMemoryError: Direct buffer memory` | Too many/unreleased direct buffers or direct memory cap | Direct buffer metrics, allocation stacks, Netty leak detector, RSS |
| `Metaspace` OOM | Excessive class/classloader loading or classloader leak | Classloader stats, metaspace metrics, JFR |
| `unable to create native thread` | Too many threads or native memory/PID limits | Thread count, OS process/thread limit, stack size, RSS |
| Container `OOMKilled` without Java OOME | RSS/container limit exceeded | Orchestrator events, container working-set memory, JVM memory breakdown |
| Frequent GC pauses, high CPU | Allocation churn or heap pressure | JFR GC, allocation profile, post-GC heap occupancy |

### 6.3 Common Spring WebFlux/DataBuffer pitfalls

- `bodyToMono(String.class)` aggregates the entire body into one String: large responses cause large allocations and heap pressure. For large payloads, parse/stream incrementally with a per-request maximum size.
- `DataBufferLimitException` means **exceeding the buffered/decoded data limit**, not necessarily a memory leak; do not raise `maxInMemorySize` toward infinity to mask oversized payloads.
- With pooled `DataBuffer`s, manually retaining, passing, discarding, or reading without timely release can inflate direct memory.
- Unbounded `Flux.cache()`/`collectList()`/`buffer()` on infinite or large streams can retain millions of objects; unbounded `onBackpressureBuffer` can turn downstream slowness into OOM.
- Numerous long-lived SSE/WebSocket connections require quotas, lifetimes, message size limits, timeouts, and cleanup.
- Logging unbounded HTTP bodies or keeping huge exception stacks/bodies also creates memory pressure.

For uploads/downloads, enforce bounds, stream/forward when appropriate, and avoid buffering everything into `byte[]` unnecessarily. Only adjust codec limits after knowing max valid payloads and concurrency memory budgets.

### 6.4 Diagnosing real leaks vs. valid caches

A memory leak typically exhibits a **live set** climbing across GC cycles that does not recover when load drops. Investigation uses multiple histograms, JFR allocations, a heap dump taken safely with enough disk/headroom, and dominator-graph comparisons. Hypothesize who holds references (static maps, TTL-less caches, uncleaned subscribers/connections, ThreadLocals, classloaders, scheduled jobs).

For Netty direct memory, a heap dump may not contain native buffer contents; combine direct buffer metrics, Netty leak detection in controlled environments, NMT (if enabled), and native allocation profiles. Never conclude "no heap leak means no leak."

## 7. Event-loop blocking in Spring WebFlux

### 7.1 Why is the event loop especially sensitive?

Reactor Netty typically uses a small number of I/O threads (e.g., named `reactor-http-nio-*`) to serve many sockets. If a callback runs `Thread.sleep`, blocking JDBC, `Future.get`, `RestTemplate`, or synchronous file I/O on the event loop, it stalls that thread while waiting. Other connections sharing that event loop cannot make progress, spiking p99 even while CPU remains very low.

```text
Event-loop thread #1:
  socket A -> callback -> Thread.sleep(1000)  [BLOCKED 1 second]
  socket B -> cannot progress
  socket C -> cannot progress

Event-loop thread #2:
  sockets D, E ... continue normally
```

Crucial point: **"code returning Mono" does not automatically make everything inside non-blocking**. Calling JDBC before constructing the Mono or invoking a blocking method inside a `map` running on the event loop still blocks.

### 7.2 Bad example: blocking before creating the publisher

```java
@GetMapping("/customers/{id}")
Mono<Customer> customer(@PathVariable long id) {
    Customer value = legacyJdbcService.loadCustomer(id); // Blocks immediately.
    return Mono.just(value);
}
```

This is a fragment inside a WebFlux controller with `legacyJdbcService` (a blocking API). Blocking happens immediately when the controller method executes. `Mono.just` does not offload work to another thread; it only wraps an already-computed value.

Even the following still blocks if the subscriber runs on the event loop:

```java
return Mono.fromCallable(() -> legacyJdbcService.loadCustomer(id));
```

`fromCallable` defers execution until subscription, but **does not change the scheduler automatically**.

### 7.3 Wrapping a blocking API when a reactive driver isn't available yet

```java
@GetMapping("/customers/{id}")
Mono<Customer> customer(@PathVariable long id) {
    return Mono.fromCallable(
                    () -> legacyJdbcService.loadCustomer(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

This is a fragment in a `@RestController` with `legacyJdbcService` and imports for `Mono`, `Schedulers`, `GetMapping`, `PathVariable`, `Customer`. `subscribeOn(boundedElastic())` schedules the blocking call onto a pool meant for blocking work, keeping the event loop free while waiting.

Switching schedulers **does not make JDBC non-blocking**. BoundedElastic still has thread/queue limits; if queries are slow and traffic surges, boundedElastic's queue fills up too. You must still address DB limits, query duration, timeouts, concurrency, and shed unwanted work.

Whereas `publishOn` switches execution downstream from its position, `subscribeOn` on a publisher wrapping a blocking source is usually more predictable for this pattern. Never use `Schedulers.parallel()` for long blocking I/O because that scheduler is sized for CPU-bound work.

### 7.4 Do not "fix" with manual block() or subscribe()

- `.block()` inside a WebFlux handler signals a broken model; on Reactor threads marked non-blocking, it can throw `IllegalStateException`. Elsewhere it can still stall workers.
- Manual `.subscribe()` in a controller detaches error/cancellation lifecycles from the HTTP response; normally return the publisher so the framework subscribes.
- `CompletableFuture.join()`, `Thread.sleep()`, `LockSupport.parkNanos()`, synchronous JDBC/Redis drivers, or synchronous DNS inside callbacks also warrant scrutiny.
- `Flux.parallel()` or adding scheduler threads does not replace external resource limits.

### 7.5 Detecting blocking calls

Look for stacks like these in thread dumps/JFR: `reactor-http-nio-*` inside `Thread.sleep`, `SocketInputStream.read`, `java.sql.*`, `Future.get`, `FileInputStream.read`, or synchronous libraries. Correlate with latency spikes across **multiple independent endpoints** sharing the event loop.

In tests, **BlockHound** can instrument code to catch blocking calls on threads marked non-blocking. Conceptual example:

```java
BlockHound.install();

Mono.delay(Duration.ofMillis(1))
        .doOnNext(ignored -> {
            try {
                Thread.sleep(10); // Intentional error in test only.
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new RuntimeException(error);
            }
        })
        .block();
```

This is a test fragment requiring `io.projectreactor.tools:blockhound` (compatible version) and `reactor-core`, not production code. On JDK 13+ and certain BlockHound versions, the tool may require JVM flag `-XX:+AllowRedefinitionToAddDeleteMethods`; check documentation and JDK compatibility. BlockHound does not catch **every** blocking operation, and one clean test does not prove the entire application never blocks.

To enforce safety policies in a project, combine JFR + event-loop/CPU latency tests, monitor thread names, and run isolated BlockHound tests in an appropriate environment; never install the agent unconditionally in production.

## 8. Java 17+ exercise: understanding how wait time impacts concurrency

Before tuning pools, understand the fundamental relationship between processing time and in-flight work. This **plain Java** example runs without Spring/Gradle to estimate average load via Little's Law. It **does not simulate a real scheduler** and does not prescribe production settings.

**File `CapacityEstimateDemo.java`:**

```java
public class CapacityEstimateDemo {

    static double averageInFlight(double requestsPerSecond,
                                  double averageSeconds) {
        if (requestsPerSecond < 0 || averageSeconds < 0) {
            throw new IllegalArgumentException("Non-negative only");
        }
        return requestsPerSecond * averageSeconds;
    }

    public static void main(String[] args) {
        double rps = 100;

        System.out.printf("fast dependency: %.0f requests%n",
                averageInFlight(rps, 0.2));

        System.out.printf("slow dependency: %.0f requests%n",
                averageInFlight(rps, 2.0));

        System.out.printf("after timeout cap: %.0f requests%n",
                averageInFlight(rps, 0.8));
    }
}
```

Commands:

```bash
javac CapacityEstimateDemo.java
java CapacityEstimateDemo
```

**Exact stdout** (in an environment using dot decimal formatting for the example):

```text
fast dependency: 20 requests
slow dependency: 200 requests
after timeout cap: 80 requests
```

Explanation: at a steady 100 RPS, increasing time in system from 0.2 seconds to 2 seconds raises average in-flight count from 20 to 200. The "after timeout cap" figure illustrates average time dropping to 0.8 seconds; in practice, enforcing timeouts can increase errors, retries, or queuing. Never set timeouts merely to force a math estimate.

**Next exercise:** pick an internal API with test metrics. Measure throughput, p95/p99, pool active/pending, and thread dumps. Introduce controlled dependency latency in a test environment, observe which resource saturates, then restore dependency speed or add a concurrency limit and re-measure. Never inject artificial load onto production systems.

## 9. Diagnosing four classic cases

### 9.1 Case A: Tomcat threads 200/200, CPU 20%

**Symptoms:** p99 climbs, HTTP 503/timeouts, JVM CPU is only ~20%, busy workers near max. Thread dumps show many `http-nio-*` calling `HikariPool.getConnection`. Hikari metrics show active=max and rising pending.

**Plausible hypothesis:** JDBC connection shortage due to queries/transactions holding connections, causing Servlet workers to wait. **Do not** conclude "Tomcat needs 500 threads": more threads will just wait on the DB together longer.

**Verification:** inspect slow queries/DB locks, transaction durations, compare Hikari active vs. max, pending count, and DB-side connections/locks; trace slow SQL by traceId.

**Remediation:** optimize SQL/indexes, shorten transactions, avoid network calls mid-transaction; set bounded concurrency/timeouts; resize the pool only if the DB has capacity. After fixing, pending drops and p99 recovers.

### 9.2 Case B: WebClient pending connections rising while HTTP upstream looks healthy

**Symptoms:** outbound requests fail with pool acquire timeouts; Reactor Netty metrics show active near max and growing pending; meanwhile the remote server has steady latency.

**Possibilities:** connections held because response bodies are not consumed/closed, long-lived streams, max pool too small for concurrency, or request fan-out opening many concurrent connections.

**Verification:** active/pending counts after traffic drops, streaming endpoint types, trace span durations, body consumption paths, and Reactor Netty metrics. Test a fixed workload with and without proper response body release.

**Remediation:** consume/release bodies per lifecycle, cap fan-out, isolate pools for long streams, configure sensible pending timeouts and limits, apply backpressure; raise maxConnections only if server/upstream truly has headroom.

### 9.3 Case C: JVM heap steady yet pod OOMKilled

**Symptoms:** heap used ~60% of Xmx and GC looks normal, yet container RSS hits the limit and gets OOMKilled; app logs no `Java heap space`.

**Possibilities:** direct/off-heap buffers, many native thread stacks, metaspace, JVM native allocator, or container limits not budgeting off-heap memory.

**Verification:** JVM heap, `jvm.buffer.memory.used`, thread count, `VM.native_memory summary` (if NMT enabled), RSS, and cgroup limits. Check trends prior to termination; a heap dump **may not contain the cause** if the leak is in direct memory.

**Remediation:** reduce buffer retention and sizes, release pooled DataBuffers, cap connections/streams/threads, size Xmx and native headroom properly for the container, and bound unbounded caches/queues.

### 9.4 Case D: WebFlux latency spikes while CPU remains low

**Symptoms:** multiple endpoints simultaneously stall in ~1-second bursts; thread dumps show `reactor-http-nio-*` in `Thread.sleep(1000)` or blocking JDBC calls.

**Possibility:** a callback on the event loop is blocking. Unlike a single slow downstream, the impact spreads across many requests sharing the same event loop.

**Verification:** consecutive thread dumps, JFR, or BlockHound in tests; reproduce by toggling the blocking call in a controlled environment.

**Remediation:** replace with true non-blocking I/O; during transition, wrap with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; apply concurrency limits and timeouts on blocking dependencies. Verify event-loop latency/p99 recovers without shifting the bottleneck to boundedElastic/DB.

## 10. Classifying common errors: do not guess from the exception

| Error/signal | What it might mean | What else to verify |
| --- | --- | --- |
| `TimeoutException` from `Mono.timeout` | Publisher did not emit in time | Slow source, acquire wait, event-loop block, timeout set too low |
| `PoolAcquireTimeoutException` | Timed out waiting for a Reactor Netty pool connection | Active/pending/max, response body retention, upstream concurrency |
| `ConnectTimeoutException` | TCP connection could not be established in time | DNS, routing, firewall, server backlog, network, and remote readiness |
| `ReadTimeoutException` / response timeout | Response/data not received within limit | Remote server/stream, network, proxy, or timeout config |
| `SQLTransientConnectionException` | JDBC pool could not grant a connection in time | Hikari active/pending, DB locks, transaction duration |
| `DataBufferLimitException` | Aggregate/codec limit exceeded | Payload size/shape, codec limit, streaming design; not automatically a leak |
| `OutOfMemoryError: Java heap space` | Insufficient available heap | GC, live set, allocations, caches, heap dominators |
| `OutOfMemoryError: Direct buffer memory` | Insufficient direct memory | Buffers, connection counts, releases, direct memory cap |
| `IllegalStateException: block() ... non-blocking thread` | Blocking Reactor API called on non-blocking thread | Location of `block()`/`blockFirst()` and pipeline |
| Pod `OOMKilled` | Container exceeded memory limit | RSS/cgroup/native memory; JVM heap is only part of it |
| Rising 503 alongside thread/queue saturation | Server lacks immediate capacity | Pools, backlog, downstream, rate, retries, admission control |

Do not rely solely on the exception name; read the root cause and full stack (stripping sensitive data before sharing). The same HTTP 503 can originate from the application, reverse proxy, load balancer, or upstream. Correlation/trace IDs are needed to identify which layer emitted the error.

## 11. Changes that easily make things worse

- **Raising Tomcat maxThreads without bounds:** more requests hold JDBC/sockets longer, native thread stacks grow, and the DB takes heavier load.
- **Raising Hikari maximumPoolSize immediately:** the DB can run out of sessions and memory with higher lock contention; pool size must fit DB limits and SQL latency.
- **Setting Reactor Netty maxConnections huge:** opening too many connections can trigger connect timeouts or overload upstream; fix response lifecycle and fan-out first.
- **Using unbounded queues:** converts overload into growing heap, long wait times, and OOM instead of controlled early rejection.
- **Disabling timeouts indefinitely:** holds threads/connections/subscriptions forever when a dependency dies.
- **Raising `maxInMemorySize` without analysis:** may dodge one `DataBufferLimitException` only to cause heap OOM under concurrency.
- **Dumping all blocking calls onto boundedElastic without limits:** avoids blocking the event loop but still exhausts boundedElastic threads/queues or connection pools.
- **Synchronized retries without backoff/jitter/idempotency:** amplifies traffic when the system is weakest.
- **Turning off all logging/metrics to save overhead:** destroys root-cause evidence; trim redundant logs while keeping targeted observability enabled.
- **Looking only at heap dumps when pods die:** can miss native memory, sockets, or thread stacks.

Any change to pools/timeouts/retries must be paired with target p95/p99, error rate, throughput, and resource bounds, then re-measured.

## 12. Testing and game days in controlled environments

### 12.1 Scenario 1: DB delay

Use a test database or stub repository introducing controlled latency. Send moderate request load while recording Hikari active/pending, Tomcat busy, and p95. Repeat the same load with shortened transactions; verify pending drops. Never send abnormal traffic into production to induce an incident.

### 12.2 Scenario 2: Small WebClient pool

Spin up a slow-responding HTTP test server (e.g., WireMock/MockWebServer) and a `WebClient` with small maxConnections and bounded pending queue. Send concurrent requests, confirm pending/acquire-timeout metrics match theory; then implement proper body consumption and concurrency limits and compare.

### 12.3 Scenario 3: Event-loop blocking

In a test environment, create two WebFlux endpoints where one callback intentionally calls `Thread.sleep`. Send concurrent requests to the fast endpoint; measure tail latency. Move the blocking endpoint to `boundedElastic` and verify the fast requests no longer suffer the same delay. Use generous timing thresholds in tests rather than brittle millisecond assertions.

### 12.4 Scenario 4: Memory retention

Simulate a TTL-less cache or `Flux.cache()` on a growing stream under a small test quota; observe heap/live set across GC cycles. Remove reference retention, add bounds/TTL, and compare. Direct-buffer tests must verify buffer release and cleanup; never create intentional leaks on shared/production machines.

### 12.5 Assertions you should have

- Under overload, the system rejects/times out **within an intentional time bound**, never hanging indefinitely.
- Once a dependency recovers, queues/pending and error rates return near baseline without lingering buildup.
- Leaks are proven with trend data over time, not a lucky single snapshot.
- Prevent duplicate side effects from retries: idempotency keys and consistent processing state.
- Zero blocking calls remain on the event loop in verified paths.
- After stream stop or cancellation, connections and allocated buffers are released.

## 13. Quick ordered checklist

**When HTTP responses are slow and CPU is low:**

1. Which endpoints, which instances, since when? Check error rates and dependency latencies.
2. Are Tomcat workers busy or WebFlux event loops stalled? Is Spring MVC using WebClient on the client side?
3. Are DB connections or outbound HTTP connections at `active=max` with `pending>0`?
4. What do thread dumps/JFR prove threads are waiting on? Are any threads blocking the event loop?
5. Are heap, native RSS, and GC rising together? Any container OOMKills?
6. Was a config change, retry, fan-out, or cache recently deployed?
7. Minimal intervention: cap ingress, fix queries/response lifecycles/offload blocking, set realistic timeouts.
8. Re-measure p95/p99, saturation, memory, and key user metrics under comparable load.

**When suspecting a memory leak:** check post-GC live set, heap dump when safe, direct memory, thread count, classloaders, and object retention. **When suspecting the event loop:** search for blocking stacks on `reactor-http-nio-*`, test an independent endpoint's responsiveness, and reproduce under control. **When suspecting connection starvation:** prove pending acquire/connection wait and identify **which pool** before resizing.

## 14. Official references

- [Spring Framework — WebFlux concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): Servlet blocking model vs. event loop, handling blocking libraries.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): JVM/HTTP/connection metrics and the Actuator metrics endpoint.
- [Reactor Netty — HTTP client connection pool and timeouts](https://projectreactor.io/docs/netty/release/reference/http-client.html): `ConnectionProvider`, queues, timeouts, and Micrometer metrics.
- [Oracle JDK 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): `jcmd`, thread dumps, JFR, native memory, and JVM tools.
- [Oracle JDK 21 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder.html): capturing and analyzing JFR events.
- [Spring Framework — DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): lifecycle and release of pooled buffers.
- [Spring Framework — DataBufferLimitException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferLimitException.html): cause of exceeding aggregate limits.
- [Project Reactor — FAQ: blocking calls on boundedElastic](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): wrapping blocking sources with `fromCallable` and `subscribeOn`.
- [Reactor BlockHound](https://github.com/reactor/BlockHound): detecting blocking calls on non-blocking threads.
