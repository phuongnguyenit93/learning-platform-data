# Distinguishing Throughput, Latency, Concurrent Requests, and Resource Utilization in Spring Boot

## 1. Objectives and Context

In operating a **Spring Boot web runtime**, four quantities are very easily lumped together as "performance":

1. **Throughput:** how many HTTP requests does the system complete per unit of time?
2. **Latency:** how long does a request take from a defined start point to a defined end point?
3. **Concurrent / in-flight requests:** at a given point in time, how many requests have started but not yet completed?
4. **Resource utilization:** how much of CPU, memory, threads, connections, queues, disk I/O, network, and downstream capacity is being used relative to real limits?

These four quantities are **related but not synonymous**. A web service can achieve high RPS yet have poor p99 latency; it can have 500 requests waiting on I/O with only 10% CPU; it can sit at 95% CPU without throughput increasing; or it can have a huge number of open socket connections while only a small fraction of requests are actually running.

This lesson belongs to the topic **Performance and Limits**. The focus is on the measurement model, load capacity, and differences between **Spring MVC on Servlet container/Tomcat** and **Spring WebFlux**. The hands-on section uses **Java 17+, Spring Boot 3.5.16, Micrometer/Actuator, Tomcat** with compilable/runnable code; it includes real HTTP measurement commands, integration tests, and a load probe using JDK HttpClient to reproduce differences among offered load, latency, and resources.

After studying this lesson, you will be able to:

- Write the units correctly: **requests/second**, **milliseconds**, **requests in flight**, **CPU cores / CPU %**, **bytes**, **threads**, and **connections**.
- Read p50/p95/p99 without confusing percentiles with the mean.
- Apply **Little's Law** with the right assumptions to relate throughput, mean latency, and average in-flight requests.
- Identify **queueing**, saturation, backpressure, timeouts, retries, and tail latency.
- Know why increasing `server.tomcat.threads.max`, connection counts, or replica counts **does not automatically guarantee** a faster application.
- Enable HTTP/server/JVM metrics and measure them concurrently, rather than looking at a single log duration line.
- Run controlled load tests, avoiding "coordinated omission" and skewed measurements caused by weak clients or unstable environments.

**The question you must answer before any benchmark:** from **which perspective** are you measuring (client, proxy, Tomcat, controller, or downstream), at **which start/end points**, under **what load and environment**, and what is the SLO target?

## 2. The Four Quantities: Definitions, Formulas, and Units

| Quantity | Common Symbol | Definition / Unit | What Cannot Be Inferred from This Quantity Alone |
| --- | --- | --- | --- |
| Completed throughput | `X` or `λ` when the system is stable | completed requests / second (RPS) | Does not tell whether requests are fast or slow; does not tell if headroom remains |
| Offered load / arrival rate | `λ_in` | number of requests **sent in** per second | Does not guarantee completed requests equal the incoming rate |
| Latency | `W`, `R`, `T` | seconds/request or ms/request | A single average hides tail latency |
| In-flight/concurrency | `L`, `N` | number of requests received but not yet completed, at a point in time | Not synonymous with thread count or TCP connection count |
| CPU utilization | `U_cpu` | ratio of CPU busy time to **allocated quota/capacity** | Does not show blocked threads or DB bottlenecks |
| Memory usage | `M` | heap, non-heap, direct memory, RSS, % cgroup limit | 70% heap does not automatically mean a leak |
| Pool utilization | `U_pool` | active/leased connections divided by pool limit | Does not tell whether upstream is failing |
| Queue depth | `Q` | pending requests/tasks not yet processed | Does not mean throughput has increased |

**Exact definition of throughput:**

\[
\text{RPS}_{completed}
= \frac{\text{completed requests in observation window}}{\text{seconds in window}}
\]

For example, during **60 steady seconds**, the system completes 7,200 requests:

\[
X=7200/60=120\ \text{requests/second}
\]

If 9,000 requests were sent in during that same interval but only 7,200 completed, **arrival rate = 150 RPS** and **completed throughput = 120 RPS**. The difference may still be in queues/in-flight, canceled, errored, rejected by the gateway, or falling across different measurement window boundaries. Do not subtract the two rates and claim an exact number of lost requests without checking in-flight counts and counter boundaries.

**Account for errors when reporting throughput:** a server can process 100 RPS consisting of 60 200s, 30 429s, and 10 503s. Simply saying "100 RPS" does not reflect **goodput** — the rate of requests producing successful business outcomes. You must report status mix, accepted/successful throughput, error rate, and SLO compliance.

### 2.1. Where Is Latency Measured From and To?

A client can measure end-to-end latency:

```text
Client starts sending request
   | DNS/TCP/TLS, network to edge
   v
Gateway / reverse proxy (queue, route, retries)
   v
Tomcat accepts and dispatches
   v
Spring filters -> controller -> service -> database/outbound HTTP
   v
Serialize/compress and transmit response
   v
Client receives full response body
```

Several measurement types:

- **Client end-to-end**: from before sending until the client finishes receiving the response according to how it reads it; includes network/proxy/client overhead.
- **Time to first byte (TTFB)**: time until the first response byte reaches the client; does not represent **total download time**.
- **Server request duration**: time covered by the framework's HTTP server observations; configuration/filters/asynchronous completion affect semantics.
- **Controller method time**: time spent inside controller/service code; does **not** include all filters, proxy, network, or response streaming.
- **Downstream call duration**: from call start until the HTTP client receives data per its semantics; may include connection pool wait.

**Do not mix latency from two measurement points and subtract them directly.** For example, client p95=300 ms and service p95=120 ms does not mean exactly 180 ms was "lost in the network": percentiles do not add/subtract linearly, and request sets/sampling windows may differ.

### 2.2. In-Flight Requests and Concurrency

When a request begins being tracked, the counter increments; when the request actually ends according to the measurement contract, the counter decrements. The value `inFlight(t)` is a snapshot **at time t**, not "requests per minute".

Example:

```text
12:00:00.000  request A starts -> in-flight=1
12:00:00.010  request B starts -> in-flight=2
12:00:00.020  request C starts -> in-flight=3
12:00:00.070  request B completes -> in-flight=2
12:00:00.090  request A completes -> in-flight=1
12:00:00.130  request C completes -> in-flight=0
```

**Peak in-flight** during an interval does not equal **average in-flight** for that same interval. With Servlet async/SSE/WebSocket, the definition of "still-open request" needs clarification: a long-lived stream can keep connection/in-flight counts high for a long time even though the request thread has already been released.

### 2.3. Resource Utilization Must Specify the Denominator

Saying "80% CPU" lacks context unless you know:

- 80% of **one core**, of **4 allocated vCPUs**, or of the entire 64-core host?
- How many processors does the JVM see after container limits? Is there CPU throttling due to cgroup quota?
- At the same time, what is the CPU usage of the app, DB, proxy, and load generator?
- Is there throttling, steal time, GC pauses, or native/direct-buffer allocation?

If an app has a 2 vCPU quota and continuously uses close to 2 vCPUs, it can be throttled even when the host has many idle cores. `Runtime.availableProcessors()` is **the number of processors available to the JVM/runtime**, not CPU utilization percentage; do not print it as a utilization metric.

## 3. Illustrative Table: Same Throughput, Different Experience

The following values are **hypothetical data for learning**, not benchmark results of a specific Spring Boot application:

| Scenario | Completed RPS | Mean Latency | p95 Latency | Approx. Average In-Flight | CPU Usage |
| --- | ---: | ---: | ---: | ---: | --- |
| A — steady processing | 100 | 50 ms | 90 ms | ~5 | 35% quota |
| B — slow upstream | 100 | 300 ms | 700 ms | ~30 | 18% quota |
| C — queueing/saturation | 100 | 900 ms | 2,500 ms | ~90 | 95% quota |
| D — fast rejection with 429 | 150 total, but 90 successful | 60 ms (mixed status) | 100 ms | ~9 | 60% quota |

Explanation:

- **A and B both have 100 RPS**, but B holds more requests in-flight because each request waits longer.
- **B has low CPU** because threads may be blocking on database or network calls. Low CPU **does not prove** the application has spare throughput capacity; the bottleneck may be a connection pool or downstream quota.
- **C has flat throughput** while mean/p95 latency is high and CPU is busy: load has passed the knee, queues are growing, and tail latency degrades.
- **D has higher total throughput** but only 90 successful RPS: counting 429s as "fast processing" and reporting it as better than A is wrong. You must separate goodput/status mix.

The in-flight values in A/B/C apply **Little's Law** assuming a stable system and consistent boundary: `100 × 0.05 = 5`, `100 × 0.3 = 30`, `100 × 0.9 = 90`. For D, `150 × 0.06 = 9` only applies when the mean latency of **all** responses in the same completed population is used consistently.

## 4. Latency Percentiles: p50, p95, p99, and the Tail

Suppose 100 completed requests are sorted by ascending duration:

- **p50**: threshold below which roughly 50% of samples fall; reflects the "typical request" better than the mean in skewed distributions.
- **p95**: roughly 95% of samples do not exceed this threshold; the remaining 5% can be much slower.
- **p99**: roughly 99% of samples do not exceed it; especially important at high volume or under strict SLOs.
- **max**: the largest observed value in the window; sensitive to sample size and outliers.
- **mean**: sum of durations / number of samples; used in Little's Law when W is defined as **the mean time of the same population**.

For example, 99 requests take 20 ms while 1 request takes 10,000 ms:

\[
\mathrm{mean}=(99 \times 20 + 10000)/100=119.8\ \mathrm{ms}
\]

Most users see 20 ms, a few see 10 seconds, and the mean is nearly 120 ms. **A single mean hides the tail.** Conversely, p99—depending on percentile calculation method—may **not fully capture a single outlier** in the threshold; inspect p99, max, and sample count together.

### 4.1. Percentiles Do Not Add Across Services

If service A has p95=100 ms and B has p95=200 ms, you **cannot** conclude that A→B has total p95=300 ms. The percentile of a sum depends on **the distributions and correlation** between durations at each hop, as well as request population, retries, and parallel fan-out branches.

Similarly, do not sum per-instance p95s to get a cluster-wide p95, and do not average per-instance p95s and call it "global p95". To aggregate percentiles, you need **histograms/distributions** with compatible buckets or properly collected raw samples. Micrometer/Prometheus histograms are one way to compute aggregated estimates.

### 4.2. Latency SLOs Must Include Success Criteria

Example SLO:

> Over 30 days, 99% of **valid requests** to `GET /api/items/{id}` complete **under 300 ms** without server errors.

You must specify concretely:

- Which requests are valid and included in the denominator?
- Do client 4xx or overload 429s count as failures?
- Is latency measured from the browser, gateway, or server?
- Is full response body transfer included for streaming/downloads?
- Are warm-up or maintenance windows excluded?
- Which metric represents it with sufficient samples and without high-cardinality labels?

An SLO should not just be `p95 < 300ms` without error rate/goodput. A system could return 503 very quickly to "optimize latency" while failing to serve business traffic.

## 5. Little's Law: Relating Throughput, Latency, and Concurrent Requests

For a **stable** system and a consistent request population/measurement boundary:

\[
L = \lambda W
\]

Where:

- `L`: **average number of requests in the system** (waiting + executing within the chosen boundary), in requests.
- `λ`: **completed/arrival rate** in steady state, in requests/second, for a consistent population without unbounded queue growth.
- `W`: **mean time in the system**, in seconds/request, including wait time if the boundary contains a queue.

Example:

```text
λ = 120 requests/second
W = 250 milliseconds/request = 0.25 second/request

L = λ × W
  = 120 × 0.25
  = 30 requests (average)
```

Meaning: to sustain ~120 RPS with a 250 ms mean response time, the system typically holds ~30 requests on average inside that boundary. This is **not** a rule that you must set Tomcat `threads.max=30`. Requests can be waiting on I/O, Servlet async, HTTP/2 multiplexing, pool queues, business tasks, and open streams, so in-flight request count does not equal worker thread count.

**Do not substitute p95/p99 for W** in the formula. `L = λ × p99` is not Little's Law. W is **mean latency**, not a percentile.

**Conditions/limits:**

1. Load is sufficiently stable over the measurement window; arrivals/completions and in-flight counts are not growing without bound.
2. Same request population: if throughput counts all 2xx/4xx/5xx responses while mean latency only includes 2xx, the formula breaks.
3. Same boundary: do not multiply cluster-wide gateway throughput by a single route's controller duration and call it cluster-wide in-flight requests.
4. If retries occur, one user operation can generate multiple HTTP exchanges. Clarify whether you are counting **business operations** or **HTTP requests**.
5. For long-lived SSE/WebSocket connections, connection lifetime and individual message duration differ. Pick the right unit; do not apply Little's Law from short-lived GETs to size 10,000 long-lived sockets.
6. Units must match: 120 RPS × 250 ms = 30 requests **after converting ms to seconds**, not 30,000 requests.
7. During transient overload, pending requests can grow rapidly even while completed throughput stays nearly flat; steady-state Little's Law does not fully predict queue explosions.

### 5.1. Standalone Java 17 Program Demonstrating Little's Law

**`LittleLawDemo.java`**

```java
import java.util.Locale;

public class LittleLawDemo {
    public static void main(String[] args) {
        double completedRps = 120.0;
        double meanLatencyMs = 250.0;

        double meanInFlight = completedRps * meanLatencyMs / 1000.0;

        System.out.printf(
            Locale.ROOT,
            "Average in-flight requests: %.1f%n",
            meanInFlight
        );
    }
}
```

Run with JDK 17+:

```bash
javac LittleLawDemo.java
java LittleLawDemo
```

**Exact stdout** (per code and `Locale.ROOT`):

```text
Average in-flight requests: 30.0
```

This is an **illustrative calculation**, not a concurrency measurement of a running application. In a real system, pull completed RPS and **mean latency** from the same window and boundary.

## 6. Queueing, Saturation, and Why Adding Load Can Slow Everything Down

A web request can wait at multiple places:

```text
Client arrival
   |
   v
Ingress / gateway queue
   |
   v
Tomcat accept queue / worker availability
   |
   v
Application executor / semaphore / bulkhead
   |
   v
DB pool acquire / outbound HTTP pool acquire
   |
   v
CPU / database / network / service time
   |
   v
Response serialization + network
```

Each queue can **hide time** that looking at a single controller method misses. When arrivals exceed service capacity, wait time rises; some requests time out or get rejected. Near saturation, even a small increase in load can produce huge tail latency.

### 6.1. The M/M/1 Model Only for Understanding Trends

The **M/M/1** queueing model makes strong assumptions: Poisson arrivals, exponentially distributed service times, a single server, steady state, and an infinite ideal buffer. With `λ < μ` (where μ is service capacity in requests/s), **mean system response time**:

\[
W = \frac{1}{\mu-\lambda}
\]

If `μ = 100 requests/s`, illustratively:

| Arrival Rate λ | Utilization `ρ=λ/μ` | Mean Response W per M/M/1 |
| --- | ---: | ---: |
| 50 RPS | 50% | 20 ms |
| 80 RPS | 80% | 50 ms |
| 90 RPS | 90% | 100 ms |
| 98 RPS | 98% | 500 ms |

**These are theoretical model results, not real Spring Boot latencies.** Web services have multiple workers, variable CPU times, database calls, caching, retries, connection pools, HTTP/2, and multi-stage concurrency. The formula is useful for seeing that **latency grows nonlinearly near saturation**, not as a production capacity calculator without validating assumptions.

### 6.2. High Concurrency Does Not Guarantee High Throughput

If an upstream limits you to **10 connections** and each call takes 100 ms, a simple blocking model can only perform around **100 calls/s** across 10 slots under ideal conditions. Raising concurrent requests from 10 to 100 just leaves 90 requests waiting to acquire or timing out; it does not increase the upstream limit.

If a request consumes an average of 20 ms of CPU time and the app genuinely has a **4 vCPU quota**, the ideal CPU-demand upper bound is:

\[
X_{\max,\mathrm{CPU}} \leq \frac{4\ \mathrm{CPU\ seconds/second}}
{0.020\ \mathrm{CPU\ seconds/request}}
= 200\ \mathrm{requests/second}
\]

This is only a **theoretical ceiling at 100% CPU**, excluding kernel, GC, TLS, logging, JVM overhead, dependencies, load imbalance, and tail latency SLOs. Sustainable throughput at the desired latency is usually **lower** than this ceiling. If the bottleneck is the DB, that 200 number cannot predict actual throughput either.

### 6.3. Backpressure, Admission Control, and Retry Storms

A system can choose:

- **Bounded concurrency** with semaphores/bulkheads for downstreams.
- **Bounded queues** with explicit timeouts/deadlines.
- **Load shedding** or controlled 429/503 responses when over capacity instead of accepting requests indefinitely.
- **Retries with backoff + jitter**, only when the operation is idempotent/safe and budget remains within the deadline.
- **Circuit breakers** when dependencies fail; limit fan-out and avoid duplicate attempts.
- **Autoscaling** on appropriate signals such as CPU, latency, in-flight requests, and queue depth; accounting for warm-up/spin-up time.

Excessive concurrency can trigger **retry amplification**: client times out and retries, proxy retries, service also retries, causing the downstream to receive many attempts for a single business action. Always measure **offered load, completed throughput, rejected requests, retries, and queue depth** together.

## 7. Resource Utilization: Look Multi-Dimensionally Rather Than Just at CPU

### 7.1. CPU

High CPU can stem from business computation, JSON serialization, TLS, regex, GC, lock contention, or retry loops. Low CPU paired with high latency can come from:

- Slow DB queries or an exhausted DB connection pool.
- Pending outbound HTTP pool acquisitions.
- Threads blocking on `Future.get()`, socket reads, or filesystem I/O.
- Gateway/network or server-side throttling.
- Executor queues holding requests for a long time while threads use little CPU.
- Low CPU quota with periodic cgroup throttling.

Measure both **CPU used / quota**, **CPU throttling**, GC CPU, load distribution across pods, and downstreams. A 95% CPU number alone does not tell you which code to optimize; profiling/tracing locates the bottleneck.

### 7.2. Memory: Heap, Non-Heap, and RSS

Distinguish:

- **Heap used/committed/max**: object allocations, caches, request bodies; managed by GC.
- **Non-heap**: metaspace, code cache, and other JVM regions.
- **Direct/native buffers**: Netty/TLS/compression or native allocations.
- **Container RSS/working set**: actual memory per cgroup/pod; can differ significantly from heap.
- **GC pause frequency/duration**: stop-the-world pauses affect tail latency.

High heap due to a "warm" cache can be normal; continuously rising heap combined with frequent GC and OOM is what requires investigation. **Increasing heap** can lower GC frequency, but it also consumes quota and can lengthen some pauses; measure rather than assuming bigger is always faster.

### 7.3. Threads and Executors

- **JVM live threads** is not the count of in-flight HTTP requests.
- **Tomcat busy threads** differs from total threads; a thread waiting on a socket/DB still counts as busy.
- **Executor active/queued/rejected** are separate counters for async processing pools.
- With Java 21 virtual threads, concurrent tasks can far exceed platform thread count without changing compute CPU capacity.
- Thread dumps show BLOCKED/WAITING/TIMED_WAITING/RUNNABLE, but you must read stack/context; do not add up all WAITING threads and call it a deadlock.

### 7.4. TCP Connections and HTTP Requests

One HTTP/1.1 keep-alive connection can serve many requests **sequentially**; HTTP/2 can multiplex multiple streams. Idle sockets do not equal running requests. With WebSockets and SSE, connections stay open for a long time while consuming very little CPU. Counting connections to estimate max in-flight can be wrong in either direction.

### 7.5. Disk I/O and Network

File downloads, synchronous access logging, upload streaming, compression, and reverse proxy buffering can make throughput bounded by **network bytes/s**, disk IOPS, kernel buffers, TLS encryption, or bandwidth even when controller CPU is low. Measure request/response body size distributions and compression; "100 RPS" with 1 KB payloads is completely different from "100 RPS" with 100 MB files.

## 8. Spring MVC / Tomcat: Threads, Connections, Queues, and Async

### 8.1. Worker Threads Do Not Equal Concurrent Requests

In traditional synchronous Spring MVC, a request typically occupies a Servlet worker thread while filters/controllers execute blocking operations. If 200 requests all block on the DB for 1 second, you may need many threads or queueing, **but** enlarging the thread pool only queues more requests against the DB if the DB is already saturated.

Common embedded Tomcat properties in Spring Boot 3.5:

```properties
# The numbers below are demo configuration; NOT production recommendations.
server.tomcat.threads.max=40
server.tomcat.threads.min-spare=5
server.tomcat.max-connections=300
server.tomcat.accept-count=100
server.tomcat.mbeanregistry.enabled=true
```

Meaning:

- `server.tomcat.threads.max`: maximum Servlet worker threads in the platform-thread model; defaults to 200 in Boot 3.5, and may not apply in the same way when **virtual threads are enabled** per documentation.
- `server.tomcat.threads.min-spare`: minimum spare worker threads per the implementation, not a guaranteed active request count.
- `server.tomcat.max-connections`: limit on connections Tomcat accepts/handles concurrently; **not** synonymous with max active requests or max threads.
- `server.tomcat.accept-count`: queue size for incoming connection requests when the connector hits its limits, not the entire business request backlog.
- `server.tomcat.mbeanregistry.enabled=true`: required if you want Boot to auto-instrument Tomcat metrics from MBeans; MBeans/Tomcat stats are only useful with Actuator/Micrometer and version-appropriate metric names.

**Do not conclude from `threads.max=40` that the app can only handle 40 connections.** Idle keep-alive and async processing change that relationship; HTTP/2 streams also multiplex.

### 8.2. Servlet Async and Streaming

Spring MVC supports `Callable`, `DeferredResult`, `WebAsyncTask`, `StreamingResponseBody`, and `SseEmitter`. When a controller uses Servlet async, the container thread can be returned before the response finishes. However:

- An async request may still occupy a slot in the connection quota.
- Blocking operations inside an async executor still need threads.
- In Spring MVC, **streaming response writes remain blocking** on the framework async executor; this does not turn it into WebFlux non-blocking I/O.
- Client-perceived response latency still includes time waiting for callbacks/streams, even if the controller method returns almost immediately.
- A filter measuring time until `chain.doFilter` returns does not necessarily capture **request completion latency** under async/streaming.

Spring Framework recommends configuring an appropriate `AsyncTaskExecutor` under heavy load; the simple default executor should not be treated as production sizing. Do not accept unbounded long-lived streams and scale threads infinitely.

### 8.3. Java 21+ Virtual Threads

With `spring.threads.virtual.enabled=true` on Java 21+ and a supported stack, blocking request tasks can execute on virtual threads. This can **reduce thread overhead** when many tasks wait on I/O, yet:

- It does not create more CPU cores.
- It does not magically make slow DBs or queries faster.
- It does not change limits on DB connections, HTTP pools, memory, bandwidth, or downstream quotas.
- It does not automatically increase throughput for CPU-bound tasks.
- Pinning, `synchronized`/native calls, ThreadLocal-heavy behavior, and monitor contention still must be measured for your Java/JVM version.
- Do not use platform-thread `server.tomcat.threads.max` to size virtual-thread concurrency in the same way.

If enabling virtual threads, measure **outbound pool saturation, heap/GC, p95/p99, and user-perceived latency**. Business limits and bulkheads remain necessary.

## 9. Spring WebFlux / Reactor Netty: Non-Blocking Does Not Mean Unlimited

WebFlux is built for non-blocking I/O with event loops and Reactor `Mono`/`Flux`. When a handler mainly awaits outbound HTTP or a non-blocking DB driver, WebFlux can handle many in-flight operations without dedicating a thread per request.

But non-blocking does not mean:

- CPU-heavy work can run freely on the Netty event loop.
- Buffering or transferring large files uses no memory.
- You can call `RestClient.block()` or `Thread.sleep` on event-loop threads without stalling.
- Reactor backpressure solves every queue in proxies, DBs, or remote APIs.
- You can accept unlimited subscriptions without per-user quotas and timeouts.

Example WebFlux snippet (not a standalone class):

```java
@GetMapping("/remote")
Mono<String> remote() {
    return webClient.get()
        .uri("https://partner.example.org/status")
        .retrieve()
        .bodyToMono(String.class);
}
```

Requires an injected `webClient` and WebFlux/Reactor imports. Do not call `.block()` inside the handler. A non-blocking pipeline is still constrained by Netty's connection pool, the remote service, CPU decoding, backpressure, and client cancellation.

**Comparisons must be fair:** MVC with blocking I/O, MVC with virtual threads, MVC async, and WebFlux Netty **differ in thread/resource models**. You cannot conclude WebFlux is "faster" in all cases from a tiny localhost JSON benchmark; outcomes depend on workload, library compatibility, concurrency, logging, TLS, proxies, and thread usage.

## 10. Observability: Measuring with Spring Boot Actuator and Micrometer

Spring Boot Actuator/Micrometer provides visibility, but you must distinguish **request timers**, **active requests**, and **resource gauges**. A timer for completed requests does not automatically turn into an instantaneous concurrency gauge.

Important metric groups:

| What You Need to Know | Example Metric / Measurement | How to Read It |
| --- | --- | --- |
| Total completed requests and duration | `http.server.requests` (Micrometer Timer, standard name in Spring MVC/WebFlux Boot 3.5) | COUNT/TOTAL_TIME/MAX; derive RPS via rate over counter in monitoring backend |
| HTTP status mix | Tags `status`, `outcome`, `method`, `uri` | Break down 2xx/4xx/5xx ratios and routes; avoid high cardinality |
| JVM CPU | `process.cpu.usage` or JVM/process metrics per exporter | Process CPU usage; compare against cgroup quota |
| JVM threads | `jvm.threads.live`, `jvm.threads.states` | Not synonymous with in-flight requests |
| Heap/non-heap | `jvm.memory.used` and `jvm.memory.max` | Bytes by `area`/`id`, compare with container RSS |
| GC | `jvm.gc.pause` and corresponding version metrics | GC frequency/duration, correlate with tail latency |
| Tomcat threads | `tomcat.threads.busy`/config metrics when MBean registry is enabled | Busy container threads, not all in-flight requests |
| Tomcat connections | `tomcat.connections.current` or equivalent if present | Connections, including idle; not request count |
| Demo app in-flight requests | `demo.requests.active` (custom Gauge) | Snapshot within sync filter boundary, **excludes full async lifetime** |
| Process-lifetime peak | `demo.requests.peak` (custom Gauge) | Peak since app startup, not p95 |
| DB/HTTP pool queue | `hikaricp.connections.pending`, Reactor Netty provider pending | Pool bottleneck, can cause low CPU with high latency |

**Note:** Exact meter/tag names depend on Boot, Micrometer, binders, and runtime. Do not treat the table above as a guarantee that every metric is always present by default; open `/actuator/metrics` or the Prometheus endpoint to verify real names. In particular, Tomcat metrics require `server.tomcat.mbeanregistry.enabled=true` per Boot documentation.

### 10.1. Timer COUNT Is Not RPS by Itself

Suppose `http.server.requests` has COUNT 1,000 at t=10s and COUNT 2,200 at t=20s:

\[
\text{RPS over interval} = (2200-1000)/(20-10)=120
\]

Do not take the final COUNT 2,200 and read it as "2,200 RPS". In Prometheus, use `rate(...)` or `increase(...)` on the **counter series** with appropriate labels, paying attention to normalized metric names (for example `http_server_requests_seconds_count` when exported from a timer/histogram). Other monitoring backends have their own names and semantics.

### 10.2. Prometheus Histograms and Percentiles

Spring Boot supports:

```properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

This enables histograms suitable for **aggregable percentile approximations** when supported by the registry, though at a cost in cardinality/buckets. Choose low-cardinality route tags and bound bucket ranges/SLOs at scale.

In Prometheus, once histogram buckets exist for `http.server.requests`, you can estimate p95 with an expression such as:

```promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{job="spring-demo"}[5m])
  )
)
```

This is an **example query**: the `job` and `uri` labels, meter name, and bucket setup must match your actual exporter, and the route label must be a **template** rather than raw user IDs. Do not copy a query if your Prometheus data source does not yet contain those series.

**Do not compute global p95 by averaging per-instance p95s.** You must aggregate histogram buckets across the chosen dimensions, preserving `le` and the grouping labels.

### 10.3. Why `/actuator/metrics` Does Not Replace a Monitoring Backend

The metrics endpoint is for **in-process diagnostics**: listing meter names and viewing current measurements/tags. It is not a time-series database for computing last week's p99, rates across multiple replicas, or SLO error budgets. For production operations, use a proper registry/exporter and backend such as Prometheus/OpenTelemetry.

**Actuator Security:** `metrics`, `env`, `heapdump`, `threaddump`, and `configprops` can expose runtime details or secrets. In demos you may expose `health,metrics` on localhost. Production requires network isolation, authentication, and authorization—never expose `/actuator/**` openly to the Internet.

## 11. Hands-On Project: Measuring Latency and In-Flight Requests in Spring Boot MVC

This example provides two endpoints with very different characteristics:

- `GET /demo/wait?ms=100`: **waits with `Thread.sleep`** — simulates blocking I/O latency, using virtually no CPU while waiting. **For learning only.**
- `GET /demo/cpu?iterations=100000`: performs CPU calculation — measures latency affected by CPU/quota/concurrency; not a scientific CPU benchmark.
- `GET /demo/resources`: outputs a snapshot of requests currently inside the filter, peak, live JVM threads, heap used/max, and `availableProcessors`; this snapshot does **not** compute CPU utilization.
- `/actuator/metrics/http.server.requests` and `/actuator/metrics/demo.requests.active`: inspect HTTP metrics and custom gauges registered by the demo.

With these two load types, you will observe that **in-flight**, **duration**, **CPU usage**, and **throughput** do not change in the same way as concurrency increases.

### 11.1. File Structure

```text
performance-demo/
├─ pom.xml
└─ src/
   ├─ main/
   │  ├─ java/com/example/demo/
   │  │  ├─ PerformanceApplication.java
   │  │  ├─ RequestConcurrencyFilter.java
   │  │  └─ PerformanceController.java
   │  └─ resources/application.properties
   └─ test/
      └─ java/com/example/demo/
         └─ PerformanceApplicationTest.java
```

### 11.2. Maven `pom.xml`

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>performance-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot dependency management supplies compatible versions of Spring Framework, Micrometer, and embedded Tomcat. `3.5.16` was released on 2026-06-25, but **it is the final OSS release of the 3.5.x line**; for new production applications, choose a Spring Boot line still under active OSS support and patches, and check starter/API changes in Boot 4.x. Version 3.5.16 is pinned here so the lab keeps reproducible 3.x imports.

### 11.3. Configuration

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Sample limits for easier observation: only use in authorized local/benchmark runs.
server.tomcat.threads.max=40
server.tomcat.threads.min-spare=5
server.tomcat.max-connections=300
server.tomcat.accept-count=100

# Enable Tomcat MBean metrics collection.
server.tomcat.mbeanregistry.enabled=true

# Local diagnostics only. Do not expose /actuator/metrics publicly on the Internet.
management.endpoints.web.exposure.include=health,metrics

# Provide histogram buckets for the request timer when supported by the registry.
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

This demo only uses synchronous Spring MVC request handling. If you add Spring Security, protect actuator endpoints in `SecurityFilterChain`. When tests run on a random port, `server.port=8080` is overridden by `@SpringBootTest(RANDOM_PORT)` per Spring Boot integration test configuration.

### 11.4. Main Class

**`src/main/java/com/example/demo/PerformanceApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PerformanceApplication {
    public static void main(String[] args) {
        SpringApplication.run(PerformanceApplication.class, args);
    }
}
```

### 11.5. Measuring Concurrency Inside a Synchronous Filter

**`src/main/java/com/example/demo/RequestConcurrencyFilter.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.MeterRegistry;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestConcurrencyFilter extends OncePerRequestFilter {

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();

    public RequestConcurrencyFilter(MeterRegistry registry) {
        // The registry holds a reference to the AtomicInteger owned by this bean.
        registry.gauge("demo.requests.active", active);
        registry.gauge("demo.requests.peak", peak);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);

        try {
            chain.doFilter(request, response);
        } finally {
            active.decrementAndGet();
        }
    }

    public int active() {
        return active.get();
    }

    public int peak() {
        return peak.get();
    }
}
```

**Important meaning and limitations:**

1. `AtomicInteger` ensures thread-safe increments/decrements when multiple Servlet threads execute concurrently. The counters live inside the singleton bean.
2. `finally` decrements the counter even if the controller throws an exception, preventing counter "leaks". Do not use `AtomicInteger` as a business protection primitive: this is strictly for **observation**.
3. `peak.accumulateAndGet(now, Math::max)` stores the peak since process startup; it **does not auto-reset every minute**.
4. `MeterRegistry.gauge(...)` exposes a snapshot; a gauge is sampled **at scrape time**, so it may miss brief transient peaks.
5. The filter counts requests within **the synchronous filter chain scope**. It **does not measure** time spent waiting in the client, proxy, or accept queue before entering the filter.
6. With `Callable`, `DeferredResult`, `StreamingResponseBody`, or SSE, `chain.doFilter` can return earlier than HTTP completion. This is **not** a completion-aware counter suitable for all async workloads.
7. `@Component` registers the filter with the container; if multiple filters and Spring Security are present, filter ordering affects which requests are counted. Do not claim this gauge covers requests rejected by a gateway/WAF.
8. When `/demo/resources` or `/actuator/metrics` itself is called, **the metrics request is also counted in active**. Reading 1 even when no other requests are running is normal; do not mistake it for a leak.
9. Raising request concurrency does not always increase `active` indefinitely: if requests finish very quickly between scrapes, the gauge can read low; complement it with histograms and queue metrics.

### 11.6. Controller Simulating CPU and Wait Latency

**`src/main/java/com/example/demo/PerformanceController.java`**

```java
package com.example.demo;

import java.lang.management.ManagementFactory;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/demo")
public class PerformanceController {

    private final RequestConcurrencyFilter concurrency;

    public PerformanceController(RequestConcurrencyFilter concurrency) {
        this.concurrency = concurrency;
    }

    @GetMapping("/wait")
    public Map<String, Object> waitForIo(
            @RequestParam(defaultValue = "100") long ms) {

        if (ms < 0 || ms > 2000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "ms must be 0..2000"
            );
        }

        // Simulates a blocking wait only; never do this in production.
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Interrupted",
                ex
            );
        }

        return Map.of("kind", "wait", "delayMs", ms);
    }

    @GetMapping("/cpu")
    public Map<String, Object> cpuWork(
            @RequestParam(defaultValue = "100000") int iterations) {

        if (iterations < 1000 || iterations > 300000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "iterations must be 1000..300000"
            );
        }

        long checksum = 0L;
        for (int i = 1; i <= iterations; i++) {
            checksum += Math.round(Math.sqrt(i) * 1000.0);
        }

        return Map.of(
            "kind", "cpu",
            "iterations", iterations,
            "checksum", checksum
        );
    }

    @GetMapping("/resources")
    public Map<String, Object> resources() {
        Runtime runtime = Runtime.getRuntime();

        long heapUsed = runtime.totalMemory() - runtime.freeMemory();
        long heapMax = runtime.maxMemory();

        return Map.of(
            "activeFilterRequests", concurrency.active(),
            "peakFilterRequests", concurrency.peak(),
            "heapUsedBytes", heapUsed,
            "heapMaxBytes", heapMax,
            "liveJvmThreads",
                ManagementFactory.getThreadMXBean().getThreadCount(),
            "availableProcessors", runtime.availableProcessors()
        );
    }
}
```

**Exact explanation:**

- `/wait` uses `Thread.sleep` to create **wait latency** without actively burning CPU. In blocking MVC, each sleeping request can hold a worker thread; this is **not a production I/O pattern** and must never be used on a WebFlux event loop.
- `/cpu` uses a computation loop to illustrate CPU-bound work. It is not a FLOPS benchmark or standard CPU capacity test: JIT, Turbo Boost, GC, and warm-up change runtime duration; measure throughput/p95 rather than treating iterations as a CPU unit.
- Both endpoints clamp inputs to prevent callers from requesting huge sleeps or unbounded CPU loops. Even so, **only run this demo on localhost or a private test environment**.
- `resources()` is a **snapshot**. `heapUsedBytes` is approximate heap used at call time, not process RSS/cgroup memory; `heapMaxBytes` is not physical host memory. `liveJvmThreads` does not count WebFlux requests or virtual-thread tasks equivalently.
- `availableProcessors` is capacity information visible to the JVM, **not CPU utilization**. To measure actual CPU %, use Micrometer/process/cgroup metrics outside this endpoint.
- `Map.of` does not guarantee JSON key ordering. Tests should parse fields rather than comparing raw string ordering.
- When a client calls `/demo/resources`, the filter has already incremented `active` for that request; a value of 1 is normal when idle.

## 12. Running and Observing Metrics

### 12.1. Startup

With JDK 17+ and Maven:

```bash
java -version
mvn spring-boot:run
```

Or `./mvnw spring-boot:run` if the project has a Maven Wrapper (Windows: `mvnw.cmd spring-boot:run`). Port 8080 must be free. The configuration enables `/actuator/metrics` **for local demo use**; do not expose it publicly on the Internet in real deployments.

### 12.2. Baseline Requests

```bash
curl -i "http://localhost:8080/demo/wait?ms=100"
curl -i "http://localhost:8080/demo/cpu?iterations=100000"
curl -i "http://localhost:8080/demo/resources"
```

Sample `/wait` response:

```json
{"kind":"wait","delayMs":100}
```

Sample `/resources` response structure:

```json
{
  "activeFilterRequests": 1,
  "peakFilterRequests": 1,
  "heapUsedBytes": 24780000,
  "heapMaxBytes": 1073741824,
  "liveJvmThreads": 32,
  "availableProcessors": 4
}
```

These are **illustrative numbers**, not deterministic output: peak/heap/threads/processors depend on load, JVM, and container. Only the keys, types, and documented semantics are the sample code's contract; JSON key order varies.

### 12.3. Measuring Timing from curl

```bash
curl -sS -o /dev/null \
  -w 'http=%{http_code} ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  "http://localhost:8080/demo/wait?ms=100"
```

`time_starttransfer` is client-observed TTFB, and `time_total` is total request time per curl. With a small JSON body, the two values may be close but **not necessarily identical**. They include curl/HTTP/network factors and will not equal an exact 100 ms `Thread.sleep`.

In PowerShell, invoke `curl.exe` to avoid the alias with different syntax.

### 12.4. Reading HTTP Metrics from Actuator

```bash
curl -sS "http://localhost:8080/actuator/metrics"
curl -sS "http://localhost:8080/actuator/metrics/http.server.requests"
curl -sS "http://localhost:8080/actuator/metrics/demo.requests.active"
curl -sS "http://localhost:8080/actuator/metrics/demo.requests.peak"
```

After at least one request has been processed and its observation has completed, `http.server.requests` typically exposes measurements like **COUNT, TOTAL_TIME, MAX** and tags `method`, `status`, `uri`, `outcome` per the framework. Count is a **cumulative total** in the meter, not instantaneous RPS; total time is typically in seconds (check the meter's `baseUnit`). HTTP server timing does not include full client-side DNS/TLS.

You can filter by route/tag:

```bash
curl -sS \
  "http://localhost:8080/actuator/metrics/http.server.requests?tag=uri:/demo/wait"
```

The `uri` value is the path template recorded by the framework; inspect `availableTags` in an actual response before putting a query into a dashboard.

For `/actuator/metrics/demo.requests.active`, the value may be 1 because **the metrics-reading request itself** passes through the filter. Gauge metrics do not have a 1:1 relationship with Tomcat busy threads, and point-in-time reads can miss peaks between scrapes.

### 12.5. Reading Tomcat/JVM Metrics

```bash
curl -sS "http://localhost:8080/actuator/metrics/jvm.memory.used"
curl -sS "http://localhost:8080/actuator/metrics/jvm.threads.live"
curl -sS "http://localhost:8080/actuator/metrics/process.cpu.usage"
curl -sS "http://localhost:8080/actuator/metrics/tomcat.threads.busy"
```

If a name does not appear, **do not assume the system uses no CPU or has no threads**. Meters depend on environment, MBean registration, classpath, binders, and Spring Boot version; check the meter list first. Memory metrics carry tags for heap/nonheap and memory pools; process CPU usage uses process/JVM denominator semantics, while cgroup throttling must be checked from container metrics.

## 13. Generating Bounded Load and Calculating Client Throughput

**Never run load tests against corporate or public Internet endpoints without authorization.** The experiments below are for **localhost or owner-approved staging**, with bounded request counts and concurrency.

### 13.1. Manual Check with a Batch of Requests

On Bash/Linux/macOS with `xargs -P`:

```bash
seq 1 20 | xargs -P 5 -I {} sh -c \
  'curl -sS -o /dev/null "http://localhost:8080/demo/wait?ms=100"'
```

Up to roughly 5 curl processes send requests concurrently for a total of 20 requests. However, each curl invocation is a separate process/client creating its own connections with process overhead; **do not treat this measurement as a proper throughput benchmark**.

With a 100 ms sleep per request, 20 requests across 5 slots ideally take 4 waves (~400 ms of sleep), but actual wall time includes network, queueing, JVM scheduling, and TLS/proxy if any. Never assert 400 ms as a fixed result.

### 13.2. Java 17 LoadProbe: Distributing Workload Across Bounded Workers

Add **`LoadProbe.java`** in a separate directory or root; it uses **a single shared** JDK `HttpClient` instance, a fixed-size executor, and sends a **finite total number of requests**. The code has no Spring dependencies and runs on Java 17+. It measures client wall time, per-request completed latency, and status counts, though it is a **closed-loop load generator** (each worker sends the next request only after completing the previous one), which limits how well it finds true capacity.

**`LoadProbe.java`**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LoadProbe {

    record Sample(int status, double durationMs) {}

    private static Sample call(HttpClient client, URI url)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(url)
            .timeout(Duration.ofSeconds(5))
            .GET()
            .build();

        long begin = System.nanoTime();
        HttpResponse<byte[]> response = client.send(
            request, HttpResponse.BodyHandlers.ofByteArray()
        );

        double elapsedMs = (System.nanoTime() - begin) / 1_000_000.0;
        return new Sample(response.statusCode(), elapsedMs);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                "Usage: java LoadProbe <url> <totalRequests> <workers>"
            );
            return;
        }

        URI url = URI.create(args[0]);
        int total = Integer.parseInt(args[1]);
        int workers = Integer.parseInt(args[2]);

        if (total < 1 || total > 500 || workers < 1 || workers > 50) {
            throw new IllegalArgumentException(
                "Use 1..500 totalRequests and 1..50 workers"
            );
        }

        HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(2))
            .build();

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        List<Future<Sample>> jobs = new ArrayList<>();
        long wallStart = System.nanoTime();

        try {
            for (int i = 0; i < total; i++) {
                jobs.add(executor.submit(() -> call(client, url)));
            }

            List<Double> latenciesMs = new ArrayList<>();
            int success = 0;
            int errors = 0;

            for (Future<Sample> job : jobs) {
                Sample sample = job.get();
                latenciesMs.add(sample.durationMs());

                if (sample.status() >= 200 && sample.status() < 300) {
                    success++;
                } else {
                    errors++;
                }
            }

            double wallSeconds =
                (System.nanoTime() - wallStart) / 1_000_000_000.0;

            Collections.sort(latenciesMs);
            double mean = latenciesMs.stream()
                .mapToDouble(Double::doubleValue)
                .average()
                .orElse(0.0);

            // Nearest-rank p95 for a finite sample; other tools
            // may use interpolation/histogram estimates.
            int p95Index =
                (int) Math.ceil(0.95 * latenciesMs.size()) - 1;
            double p95 = latenciesMs.get(p95Index);

            System.out.printf(
                Locale.ROOT,
                "done=%d success=%d errors=%d " +
                "wall=%.3fs throughput=%.2fRPS " +
                "mean=%.2fms p95=%.2fms%n",
                total,
                success,
                errors,
                wallSeconds,
                total / wallSeconds,
                mean,
                p95
            );
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Run:

```bash
javac LoadProbe.java
java LoadProbe "http://localhost:8080/demo/wait?ms=100" 50 1
java LoadProbe "http://localhost:8080/demo/wait?ms=100" 50 5
java LoadProbe "http://localhost:8080/demo/wait?ms=100" 50 20
java LoadProbe "http://localhost:8080/demo/cpu?iterations=300000" 50 5
```

Example output line **illustrating format only**, **not a fixed measurement**:

```text
done=50 success=50 errors=0 wall=1.150s throughput=43.48RPS mean=110.10ms p95=130.00ms
```

**Numbers will differ on every machine.** Do not expect literally 43.48 RPS / 110.10 ms when you run it. The RPS value in code is **completed requests / wall seconds** over a 50-request batch. It can include thread creation/warm-up time and is not the server's **steady-state RPS**. `mean`/`p95` are client-measured HTTP exchange latencies, excluding time a Future waited in the executor **before the request started** (i.e., load-generator queue time).

**Limitations of this LoadProbe:**

1. It is **closed-loop**: a fixed number of worker threads wait for each response before continuing. When the server slows down, the arrival rate drops automatically; this can cause **coordinated omission** when evaluating tail latency compared to scheduled arrival traffic.
2. It awaits every Future, while all tasks are already submitted to the executor. Throughput over wall time includes load-generator queueing; latency starts only when the task actually begins sending. Those are two different boundaries.
3. Uses `BodyHandlers.ofByteArray()` to **consume the full body** before marking response completion; fine for small JSON, unsuitable for multi-GB downloads.
4. Max 500 requests and 50 workers are local guardrails only; do not turn this probe into a steady-ramp capacity test.
5. Does not guarantee Java HttpClient uses a single TCP connection; the shared client may open multiple sockets.
6. If any future fails with an exception/timeout, the sample code throws and omits the full success/error summary. A production load generator should record per-sample errors/timeouts; this demo is kept concise for stable local runs.
7. Client and server on the same host share CPU/network; the load generator itself can become the bottleneck. Measure CPU on both or run the load generator separately in a controlled environment.
8. Never send real credentials, tokens, or personal payloads; only target authorized local URLs.

### 13.3. Observation Table to Fill In Yourself

As you run each worker level, record:

| Workload | Workers | Offered/Completed RPS | Mean | p95/p99 | Active/Peak | CPU/Quota | Threads/Queue | Errors |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| wait 100 ms | 1 | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* |
| wait 100 ms | 5 | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* |
| wait 100 ms | 20 | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* |
| CPU 300000 | 5 | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* |

In the table above, *measure* means **collected by the learner**; these are not pre-filled values. LoadProbe does not directly measure **p99, CPU/quota, or threads/queue**; gather those columns from Actuator, container monitoring, and an appropriate metrics tool. Never fill in numbers from stdout that the tool did not print.

## 14. Real HTTP Integration Tests

Add a test class to verify API behavior, validation, metrics, and basic concurrency. `@SpringBootTest(RANDOM_PORT)` starts a **real embedded Tomcat** on a random port instead of using MockMvc to fake the connector. Thus the tests exercise requests through the actual HTTP stack rather than just calling Java controller methods.

**`src/test/java/com/example/demo/PerformanceApplicationTest.java`**

```java
package com.example.demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.stream.IntStream;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PerformanceApplicationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private HttpRequest request(String path) {
        return HttpRequest.newBuilder(uri(path)).GET().build();
    }

    private HttpResponse<String> get(String path) throws Exception {
        return client.send(
            request(path), HttpResponse.BodyHandlers.ofString()
        );
    }

    @Test
    void waitReturnsExpectedPayload() throws Exception {
        HttpResponse<String> response = get("/demo/wait?ms=50");

        assertEquals(200, response.statusCode());
        JsonNode payload = json.readTree(response.body());
        assertEquals("wait", payload.get("kind").asText());
        assertEquals(50, payload.get("delayMs").asLong());
    }

    @Test
    void invalidWaitIsRejected() throws Exception {
        assertEquals(
            400,
            get("/demo/wait?ms=2001").statusCode()
        );
    }

    @Test
    void cpuEndpointReturnsPositiveChecksum() throws Exception {
        HttpResponse<String> response =
            get("/demo/cpu?iterations=1000");

        assertEquals(200, response.statusCode());
        JsonNode payload = json.readTree(response.body());
        assertEquals("cpu", payload.get("kind").asText());
        assertTrue(payload.get("checksum").asLong() > 0L);
    }

    @Test
    void resourcesExposeSnapshotsNotCpuPercent() throws Exception {
        HttpResponse<String> response = get("/demo/resources");

        assertEquals(200, response.statusCode());
        JsonNode payload = json.readTree(response.body());

        assertTrue(payload.get("activeFilterRequests").asInt() >= 1);
        assertTrue(payload.get("heapUsedBytes").asLong() > 0);
        assertTrue(payload.get("availableProcessors").asInt() > 0);
        assertTrue(payload.get("liveJvmThreads").asInt() > 0);
    }

    @Test
    void actuatorExposesHttpServerRequestTimer() throws Exception {
        // Ensure at least one MVC observation exists.
        get("/demo/wait?ms=1");

        HttpResponse<String> response =
            get("/actuator/metrics/http.server.requests");

        assertEquals(200, response.statusCode());
        JsonNode payload = json.readTree(response.body());
        assertEquals(
            "http.server.requests",
            payload.get("name").asText()
        );
        assertTrue(payload.get("measurements").isArray());
    }

    @Test
    void concurrentRequestsAllComplete() {
        List<CompletableFuture<HttpResponse<String>>> calls =
            IntStream.range(0, 8)
                .mapToObj(i -> client.sendAsync(
                    request("/demo/wait?ms=100"),
                    HttpResponse.BodyHandlers.ofString()
                ))
                .toList();

        CompletableFuture.allOf(
            calls.toArray(CompletableFuture[]::new)
        ).join();

        for (CompletableFuture<HttpResponse<String>> call : calls) {
            assertEquals(200, call.join().statusCode());
        }
    }
}
```

Run:

```bash
mvn test
```

If using Maven Wrapper, run `./mvnw test` or on Windows `mvnw.cmd test`. **Six tests are expected to pass** given the right files, dependencies, and local environment. This is an **expected outcome**, not a claim that tests were executed in any repository.

What the tests verify:

- The `wait` and `cpu` HTTP endpoints and validation return the expected status/body.
- Resource snapshot returns reasonable field values without asserting CPU %.
- Actuator HTTP request timer exists after a real request.
- Eight concurrent HTTP requests all complete under light load.

What the tests **do not** prove:

- Maximum server RPS throughput or p99 latency under an SLO.
- Whether CPU is at 50% or 95%.
- That peak concurrency was literally 8: scheduling and client connection selection can vary overlap.
- That there is no queueing under production load or that the backend has enough capacity.
- CORS/TLS/proxy/CDN behavior, multi-replica scaling, or WebFlux behavior.
- JVM warm-up, GC, load-generator overhead, or production-like histogram aggregation.

Meaningful performance testing requires **a dedicated experiment with proper tooling and statistics**; never label a service "performance tested" simply because functional integration tests pass.

## 15. Designing a Fair Performance Experiment

### 15.1. Define Workload and SLO

Before starting the load tool, fix:

- Ratio of GET/POST endpoints, reads/writes, and traffic distribution.
- Payload and response sizes (1 KB vs 5 MB produces completely different limits).
- Authentication/cookies, TLS, HTTP/1.1 vs HTTP/2, keep-alive, and compression.
- Cache hit/miss rates, DB data volume/indexes, and dependency count.
- Replica count, CPU/memory limits, JVM heap, GC, and DB/HTTP pool configs.
- Arrival rate via user simulation (open-loop) or fixed concurrent users (closed-loop).
- JVM/JIT warm-up period, sampling length, ramp-up, cool-down, and repeatability.
- Target: e.g., `200 successful RPS, p95 < 250ms, errors < 0.5%` on a specifically described workload.

**Do not run destructive load tests against production without approval**; use staging with synthetic data or a production canary with owner-approved budgets and safeguards.

### 15.2. Step Load Gradually

Example concurrency steps in an authorized environment:

```text
C=1 -> C=5 -> C=10 -> C=20 -> C=40
  warm-up, hold load long enough, collect metrics at each step
```

Record:

- Completed RPS, successful/goodput RPS, 2xx/4xx/5xx/429 counts, timeouts.
- Mean/p50/p95/p99 latency, max, request duration histograms.
- Average/peak in-flight, Tomcat busy threads, pending outbound pool acquisitions.
- CPU % relative to quota, throttling, memory/GC, network/disk.
- Downstream DB/HTTP p95, circuit breakers, queue wait.
- Replica count, configurations, and commit/deploy version for comparison.

Watch for the "knee" of the curve: when increasing arrival rate/concurrency barely increases throughput while p95/p99, error rate, or CPU/queues spike, you have likely hit saturation. The practical operating point is **before** the saturation peak, leaving headroom for bursts and failover.

### 15.3. Avoiding Coordinated Omission

If a **closed-loop** load generator only sends a new request once the previous request completes, then as the server slows down, **the arrival rate drops too**. Intervals during which real users would still have sent requests get "omitted" from the latency distribution; p99 looks cleaner than real overload.

For arrival-rate SLO targets:

- Use an open-loop / constant-arrival-rate tool capable of scheduling requests **independently of response completion**.
- Ensure the load generator has enough capacity; if it cannot keep up with the target arrival rate, report `dropped/scheduled/delayed` requests.
- Record planned arrival timestamps, actual send timestamps, and completion timestamps; evaluate request delay/queueing appropriately.
- Monitor client-side queues and transport limits so you do not confuse a generator bottleneck with the server.
- Use latency histograms/analysis suited to your chosen tool; if histogram correction is applied, document the method and do not present corrected numbers as raw latency.
- Closed-loop benchmarks remain useful for studying concurrency, but **do not automatically infer** that handling 1,000 RPS under constant arrival rate will succeed.

### 15.4. Warm-Up and Noise

Java has JIT compilation, class loading, connection pool warm-up, caches, and GC cycles. The first few seconds can differ from steady state. Always:

1. Start up and warm up the app and downstreams in a controlled way.
2. Measure baseline idle resource usage.
3. Step load up and wait for stabilization before sampling.
4. Collect data over matching time windows with synchronized clocks/time zones.
5. Repeat experiments and report cross-run distribution rather than cherry-picking the best run.
6. Hold app version, CPU/memory quota, DB dataset/cache state, and traffic mix constant.
7. Separate the load generator from the server when needed, verifying the generator does not saturate.
8. Record failures/timeouts/cancellations rather than silently filtering them out of statistics.
9. When comparing two versions, run interleaved A/B tests or equivalent environments to reduce time-of-day variance.

## 16. Diagnosing by Symptom Patterns

| Symptom | Do Not Jump to This Conclusion | What to Investigate |
| --- | --- | --- |
| RPS flat, p99 rising | "Just add more users/threads" | Queueing, DB/HTTP pool saturation, CPU quota, GC |
| Low CPU, high in-flight | "App is still healthy, add more load" | Blocked I/O, downstream latency, executor queue |
| High CPU, flat RPS | "CPU metrics are wrong" | CPU saturation, serialization, GC, hotspots, contention |
| Thread count rising | "RPS must be increasing" | Thread-per-request blocked calls, thread leak, misconfigured executor |
| High TCP connections | "Lots of active HTTP requests" | Idle keep-alive, HTTP/2, SSE/WebSocket, pool routing |
| Average 50 ms, p99 5 s | "Fast average API is good enough" | Tail latency, lock contention, GC pauses, noisy neighbors |
| 200 RPS including many 503s | "Throughput hit 200 target" | Low goodput, upstream failure, overload shedding |
| Heap 80% used | "There is a memory leak" | Caches, GC allocation pressure, container memory limit, RSS |
| Client time > app timer | "Spring measures wrong" | Network/proxy/queue/response streaming, different boundaries |
| Actuator timer COUNT=10000 | "Currently serving 10000 RPS" | Cumulative COUNT requires `rate` over time |
| Gauge active=1 when idle | "One request leaked" | The request reading the gauge is counted too |
| Raising `threads.max` worsens p99 | "Need to raise it even more" | More downstream contention/queueing, CPU/memory pressure |
| Many 429s with low latency | "Latency SLO is great" | Requests shed/failing; track goodput/error SLO |
| Autoscaling adds replicas, DB overloads | "Autoscaling is broken" | Shared downstream bottleneck, fan-out/retry amplification |
| Average p95 across pods is low | "Global p95 meets SLO" | Percentiles cannot be combined via simple averaging |
| CPU usage 30% yet throttled | "Spare CPU quota available" | Check actual usage/quota and cgroup throttling, time slices |
| Async controller returns quickly | "Client gets response quickly" | Async completion, streaming, backpressure, client download |

## 17. Security and Operational Notes When Measuring Performance

- **Do not expose** `/actuator/metrics`, `/actuator/threaddump`, `/actuator/heapdump`, or exporters uncontrollably; runtime info helps attackers map the system.
- Do not attach user IDs, full paths containing tokens, raw query strings, or session IDs as high-cardinality **metric labels**. Use `uri` route templates, method, status, and stable service/env/version tags.
- Do not log full HTTP request/response bodies or Authorization/Cookie headers just to inspect latency; logging adds memory/I/O overhead and PII exposure risk.
- Restrict load tests to authorized environments with bounded rate/duration, test data, a rollback plan, and downstream monitoring.
- Under load, do not enable framework-wide DEBUG/TRACE logging, as it distorts performance results and may log secrets.
- Distinguish performance debugging from **disruptive stress tests**; never fire heavy traffic at production infrastructure unapproved.
- Measure endpoint latency with authorization/tenant checks intact; do not optimize by stripping security filters or validation.
- With proxies, trust forwarded headers only from trusted edges; metrics keyed by spoofable client IP/host can break rate limiting and raise privacy issues.
- Timeouts, max request body sizes, max HTTP connections, and pool quotas relate to DoS resilience; every limit must align with SLAs and corresponding tests.

## 18. Checklist Before Claiming "The System Handles X RPS"

- [ ] Clearly define **offered load**, **completed throughput**, **successful/goodput RPS**, HTTP status mix, and measurement window.
- [ ] Measure latency at a consistent boundary, reporting **mean/p50/p95/p99/max** and sample counts.
- [ ] Do not plug p95/p99 into Little's Law; only use `L=λW` with **mean W** near steady state.
- [ ] Track in-flight/peak metrics and understand counting scope (sync filter, async lifetime, proxy).
- [ ] Monitor CPU/quota/throttling, heap/non-heap/RSS, GC, threads, connections, pool pending, and downstream latency.
- [ ] Understand Tomcat `threads.max`, `max-connections`, and `accept-count` as three distinct limits.
- [ ] Run load tests with warm-up, ramp, steady window, multiple runs, confidence statistics, and repeatability.
- [ ] Distinguish closed-loop concurrency from open-loop arrival rate; evaluate coordinated omission.
- [ ] Keep request/payload mix, cache hit rate, TLS, auth, network, proxy, HTTP version, and keep-alive realistic.
- [ ] Verify capacity of both the **load generator** and downstreams, not just the Spring Boot process.
- [ ] Aggregate histogram percentiles properly from buckets rather than averaging p95 across replicas.
- [ ] Enforce both latency **and** success/error-rate SLOs so fast 429/503 responses do not look like improvements.
- [ ] Leave headroom for bursts, replica failover, and GC; do not run continuously near 100% utilization.
- [ ] Confirm Actuator/metrics are not public and tags contain no PII, secrets, or per-user IDs.
- [ ] Do not use a few local GETs or 6 functional tests to claim production capacity.
- [ ] Document app version, infra limits, dates/time windows, dataset, test scripts, and caveats in reports.

## 19. Self-Check Questions

**1. Are throughput and in-flight requests the same quantity?**  
No. RPS is the number of requests completed per second; in-flight is the number of open requests at a point in time.

**2. If λ=80 RPS and mean response time=0.5 seconds, roughly what is average in-flight?**  
By Little's Law in steady state: `L=80×0.5=40 requests`.

**3. Can you compute average in-flight using λ×p99?**  
No. Little's Law requires **mean W**, not p99.

**4. If CPU is only 15% while 500 requests are waiting, does the system definitely have spare capacity?**  
No. Requests may be held on I/O, DB pools, remote services, proxies, or queues.

**5. Do 200 open TCP connections mean 200 concurrent HTTP requests?**  
No. Idle keep-alive, HTTP/2 multiplexing, and long-lived connections cause the numbers to differ.

**6. Does increasing `server.tomcat.threads.max` from 40 to 400 multiply RPS by 10?**  
No. CPU, downstream quotas/latency, pools, memory, and queues can be the bottleneck.

**7. If `http.server.requests` shows COUNT=5000, is that 5000 RPS?**  
No. COUNT is cumulative; take the delta over time or use `rate`.

**8. When client p95=300ms and server p95=100ms, is network p95 definitely 200ms?**  
No. Percentiles do not subtract like means, and the two request sets or measurement boundaries may differ.

**9. Why can fast HTTP 429s make total throughput look good?**  
Because the server returns many fast responses while successful goodput is low; you need status mix and error SLOs.

**10. Is `Runtime.availableProcessors()` a CPU usage metric?**  
No. It reflects processors visible to the JVM, not actual CPU consumption.

**11. Does measuring `active` via OncePerRequestFilter cover long-lived SSE streams?**  
Not necessarily. The filter chain can return early once Servlet async starts; completion-aware instrumentation is required.

**12. Why are histograms needed for cluster-wide p95 across multiple pods?**  
Because percentiles cannot be added or averaged; compatible buckets or raw samples must be aggregated.

**13. Can a closed-loop load generator underestimate tail latency during overload?**  
Yes. When responses slow down, it dispatches new requests more slowly, leading to coordinated omission.

**14. Are `server.tomcat.max-connections`, `threads.max`, and `accept-count` the same thing?**  
No. They apply to connections, worker threads, and incoming connection backlog with distinct semantics.

**15. Is achieving 100 RPS with p99=10 seconds and 20% errors considered "sustaining 100 RPS" under an SLA?**  
You can only say it completed 100 total responses/s. Claiming SLA capacity requires meeting goodput, error, and tail-latency requirements.

**16. Can `/demo/resources` metrics diagnose a memory leak in a single request?**  
No. That is a snapshot; diagnosing memory leaks requires trend observation, GC behavior, authorized heap dumps/profiling, and cache/load context.

**17. Why do Java 21 virtual threads not eliminate the need for bulkheads and DB pools?**  
They reduce thread-holding cost while waiting, but do not create more CPU, DB connections, or downstream capacity.

**18. When latency drops while throughput stays constant, is the system definitely healthier?**  
Not enough evidence alone. Check traffic mix, error rate, client/gateway queues, resource utilization, and SLOs. Given the same workload and success rate, lower latency is generally positive.

## 20. Official Documentation and Further Learning

- Spring Boot 3.5 — **Common Application Properties**, including `server.tomcat.threads.max`, `server.tomcat.max-connections`, `server.tomcat.accept-count`, and `server.tomcat.mbeanregistry.enabled`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Boot — **Actuator Metrics**, HTTP server `http.server.requests`, Tomcat and JVM metrics, per-meter histograms: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Boot 3.5 — **Actuator Metrics Endpoint API**: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/metrics.html
- Spring Boot — **Actuator Endpoints and Exposure Security**: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Framework — **Asynchronous Requests in Spring MVC**, `Callable`, `DeferredResult`, `StreamingResponseBody`, thread/IO semantics: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — **WebFlux vs MVC**: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Micrometer — **Timers**, COUNT/TOTAL_TIME/MAX and percentile histograms: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — **Histograms and Percentiles**: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
- Prometheus — **Histograms and Summaries**: https://prometheus.io/docs/practices/histograms/
- Prometheus — **Querying Functions** (`rate`, `histogram_quantile`): https://prometheus.io/docs/prometheus/latest/querying/functions/
- OpenTelemetry — **Metrics Concepts**: https://opentelemetry.io/docs/concepts/signals/metrics/
- Spring Boot 3.5.16 — **Release, End of OSS Support**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Conclusion:** in the Spring Boot web runtime, **throughput** measures completed requests/second; **latency** measures per-request duration and the p50/p95/p99 distribution; **concurrency** measures unfinished requests; and **resource utilization** measures CPU/memory/threads/connections/queues against real limits. They connect via Little's Law when measured at the right boundary in steady state, yet none can substitute for another. As load approaches saturation, queues and tail latency can surge even when RPS stops growing. Measure **RPS + goodput + tail latency + in-flight + CPU/quota + pool queues + errors** together, test under controlled workloads, and evaluate against SLOs rather than a single benchmark figure.