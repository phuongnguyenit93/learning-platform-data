# Distinguishing Capacity from Single-Request Speed in Spring WebFlux

When evaluating a **Spring Reactive (Spring WebFlux)** service, distinguish two questions: **“How long does one request take to return a result?”** and **“How many requests can the system serve concurrently, over a period of time, while still meeting desired quality?”** The two questions are related, yet they measure different properties. Reactive programming is primarily helpful for efficient resource usage when many I/O operations are waiting; by itself, it does not guarantee that each individual request runs faster.

## 1. Metrics to Understand

| Metric | Meaning | How to Observe |
| --- | --- | --- |
| **Latency / response time** | Time from starting to send a request until receiving a response within the chosen measurement boundary. May include network, queue wait time, application processing, DB queries, and calls to other services. | ms/request; p50, p95, p99, max; measure from client or server side and state scope clearly. |
| **Throughput** | Number of **completed** requests per unit time, typically requests/second (RPS). Distinguish successful requests (*goodput*) from total requests including errors. | RPS or transactions/second over a time window. |
| **Concurrency** | Number of requests actively being processed or awaiting results at the same instant (*in-flight requests*). | Connection count, in-flight requests, pending I/O tasks, queues. |
| **Capacity** | Highest load level a system can **sustain** within acceptable latency thresholds and error rates, for a specific workload and configuration. | Sustainable RPS alongside SLOs, e.g., p95 < 400 ms and errors < 1%. |
| **Resource utilization** | CPU, memory/GC, threads, DB connections, event loop, downstream limits, etc. | System and application metrics as load increases. |

**Single-request speed** is typically expressed as latency; **capacity** requires looking simultaneously at throughput, concurrency, latency, and errors. A high RPS number over a few seconds does not prove strong capacity if queues keep growing or p99 surges sharply.

## 2. Example: Serving Many Requests Does Not Mean Each Request Is Faster

Suppose each request must wait for an I/O service to reply after about **200 ms** (an illustrative assumption only, ignoring other processing costs):

- If only one request is active at a time, the ideal maximum is around **5 requests/second** (1 / 0.2).
- If **100 requests can wait on I/O concurrently** without resource contention, after about 200 ms the whole batch can finish: ideal throughput is around **500 requests/second** (100 / 0.2).
- In both cases, a single individual request still waits about **200 ms**. Reaching 500 RPS does not mean response time dropped to 2 ms.

These numbers are an **idealized model**, not a WebFlux benchmark result. Reality is further constrained by CPU, network, connection counts, connection pools, database speed, external service limits, scheduling mechanics, and latency distributions.

You can apply **Little's Law** for a system in steady state:

`L = λ × W`

Where `L` is the average number of requests in the system, `λ` is the average completion throughput (requests/second), and `W` is the average time a request spends in the system (seconds). For example, `λ = 200 RPS` and `W = 0.25 s` gives `L ≈ 50` in-flight requests. The formula describes the relationship when the system is stable; it **does not by itself determine maximum capacity**. When incoming load exceeds serving capacity, queues grow, latency stretches, and steady state may no longer hold for this simple calculation.

## 3. Where Does Spring WebFlux Help Capacity?

In the asynchronous, non-blocking model, a request can initiate an I/O operation and temporarily yield the thread while waiting. When data arrives, processing resumes through `Mono` or `Flux` signals. With a reactive server such as Reactor Netty, event-loop threads can coordinate many connections instead of dedicating a sleeping thread to each request waiting on I/O.

This usually benefits **high-concurrency workloads with a high I/O-wait ratio**: chat, streaming, gateways, calling other APIs, or accessing data sources with non-blocking drivers. The system can reduce the thread count needed and some context-switching overhead, thereby sustaining better throughput under a given resource budget.

However:

1. **WebFlux does not make databases or external APIs respond faster.** If a call takes 200 ms, the request still pays that latency; reducing latency requires optimizing the slow source, call count, caching, algorithms, payloads, or network path.
2. **CPU-bound work does not become faster because of reactive.** Heavy CPU-consuming code still needs CPU time; running long computations directly on the event loop can even slow down other requests. Bound/schedule CPU work appropriately or change processing architecture when needed.
3. **Making blocking calls inside a pipeline loses the non-blocking advantage.** Examples like `Thread.sleep`, traditional JDBC, `block()` on a request-processing thread, or synchronous file/API operations can hold threads waiting. If forced to integrate a blocking library, tasks can be isolated on a suitable scheduler such as `Schedulers.boundedElastic()`, but that thread pool is bounded and still pays waiting costs.
4. **Backpressure has a specific scope.** In Reactive Streams, a subscriber requests how much data it can process from a publisher, helping regulate a `Flux` stream. This **does not automatically throttle all incoming HTTP requests**, expand connection pools, or rescue an overloaded backend. At the system boundary you may still need timeouts, connection limits, bounded queues, rate limiting, and load shedding.
5. **Spring MVC also has asynchronous options or virtual threads.** You cannot conclude WebFlux always has higher throughput or lower latency; compare on the same workload, I/O libraries, resources, and deployment versions.

### Java Example with Spring WebFlux

This is a **controller snippet used in a Spring Boot project with `spring-boot-starter-webflux` and Java 17+**; it is not a standalone plain Java program run directly via `javac`. Place it in `DelayController.java` inside a package scanned by Spring Boot:

```java
package com.example.demo;

import java.time.Duration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DelayController {
    @GetMapping("/demo/wait")
    public Mono<String> waitWithoutBlocking() {
        return Mono.delay(Duration.ofMillis(200))
                .map(tick -> "done");
    }
}
```

`Mono.delay` simulates an asynchronous event after roughly 200 ms: the method creates a `Mono` and returns it without using `Thread.sleep(200)` to occupy an HTTP thread during the wait. When the app runs, calling `GET /demo/wait` receives the body `done` after at least roughly the delay duration plus overhead. Many concurrent requests can wait on the timer simultaneously without each request holding its own sleeping thread.

**Example limitations:** a timer is not a real database or HTTP client; it only illustrates the principle of asynchronous waiting. Measured response time and throughput depend on the environment. With real I/O, the entire chain of operations (such as `WebClient` and reactive data drivers) must support non-blocking execution to obtain the corresponding benefit.

## 4. How Does Latency Typically Change as Load Increases?

In the light-load region, the server may have spare resources: increasing concurrency raises throughput while per-request latency stays nearly flat. Once a bottleneck is hit (CPU, event loop, connection pool, database, or downstream), requests must wait in queues; then **p95/p99 latency climbs**, throughput slows or hits a ceiling, and timeouts and errors may appear. Continuing to increase incoming load can severely degrade the system even when some threads appear idle.

Therefore, a system serving 1,000 RPS at p95 = 3 seconds does not necessarily meet product requirements better than one serving 700 RPS at p95 = 200 ms. Evaluate alongside SLOs, success rates, request types, and resource budgets. A lone `RPS` number does not capture user experience.

## 5. Measuring Both Goals Properly

**To measure single-request speed:** run tests at low load and measure end-to-end latency; inspect p50, p95, p99, and separate application processing time, queue time, downstream calls, DB, and network where possible. Find the operation taking the most time. Measuring a single request helps investigate baseline latency, not peak traffic.

**To measure capacity:** step up load across controlled concurrency levels or arrival rates, keeping request mix and test data constant; give each step enough time to stabilize. Record *completed/successful RPS*, errors and timeouts, p95/p99, in-flight requests, queue lengths, CPU/GC, thread/event-loop utilization, connection pools, and downstream metrics. Identify the RPS level **sustainable while still satisfying SLOs**; do not treat short-lived peak numbers as capacity.

When comparing Spring MVC with WebFlux, keep business logic, backends, payloads, network conditions, pool settings, machine specs, warm-up duration, and timeout policies identical. Avoid benchmarking only an endpoint returning an empty string and extrapolating to apps making real DB/API calls. Also measure **I/O-bound** and **CPU-bound** workloads separately because reactive benefits can differ dramatically.

| Observation During Load Testing | Initial Interpretation | What to Check |
| --- | --- | --- |
| Latency stays nearly flat while RPS rises with concurrency | System still has spare concurrent capacity | Resources and SLOs at the next load step |
| RPS hits a ceiling and p95/p99 rise quickly | A resource or dependency is saturating; requests are queueing | CPU, event loop, DB pool, network, downstream, and timeouts |
| RPS looks high but many HTTP 5xx/timeouts occur | True success rate is lower than total RPS | Goodput, exceptions, downstream limits, and load-rejection mechanisms |
| Switching to reactive lowers threads and raises RPS, while baseline latency does not drop | Concurrent request-serving capacity improved; single-request work did not shorten | Latency percentiles and per-request cost |
| A CPU-bound endpoint slows down as concurrency rises | CPU or thread sharing is the bottleneck; non-blocking I/O helps little | CPU profiling, long tasks on the event loop |

## 6. Improving the Right Problem

- **To make one request faster:** reduce round-trips, optimize queries/indexes, use caching properly, cut CPU work, fetch only needed data, avoid sequential calls when independent operations can be composed safely, enforce timeouts, and improve downstream latency.
- **To sustain more concurrent requests:** remove blocking I/O from reactive paths, ensure appropriate clients/drivers, tune pools and concurrency limits, monitor the event loop, expand real backend capacity, apply backpressure within its valid scope, limit incoming load, and scale at the bottleneck.
- **To achieve both:** set separate targets for p95/p99, successful RPS, and resource cost; verify with representative load tests rather than assuming `Mono`/`Flux` automatically means “fast.”

**Key takeaway:** *latency* answers “how long must one request wait?”; *capacity/throughput under SLO* answers “how many requests can be served reliably over the same period?” Spring WebFlux can noticeably improve the second on I/O-heavy waiting workloads, while the first improves only if the processing path itself or queueing time actually shrinks.