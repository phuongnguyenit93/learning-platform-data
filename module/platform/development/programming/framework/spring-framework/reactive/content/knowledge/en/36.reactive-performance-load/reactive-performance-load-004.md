# Tuning Prefetch, Buffers, and Connection Pool Size in Spring WebFlux

## 1. Three Limits That Are Often Confused

In a Spring WebFlux application, throughput and latency are influenced by multiple layers. Three parameters are often tuned together, yet they control three different resources:

- **Prefetch**: the amount of demand an operator requests ahead from upstream, or the number of elements that can be held ready in an operator's internal queue.
- **Buffer**: the amount of data accumulated to form batches or wait for a consumer to process. Buffers can live inside an operator, at a scheduler boundary, in an application queue, or in network buffers.
- **Connection pool size**: the number of connections to a remote host that an HTTP client is allowed to keep/lease concurrently; in Reactor Netty, this is configured on `ConnectionProvider`.

They interact, but do not replace one another. Raising prefetch does not increase TCP connections. Growing a pool does not make the consumer process faster. Enlarging buffers can smooth out short bursts, but can also increase memory usage and latency when downstream is slow.

| Parameter | Primary Limit | Unit to Think About |
| --- | --- | --- |
| `flatMap(..., concurrency, prefetch)` | Number of running inner Publishers and items requested per inner | Inner subscription / item |
| `publishOn(scheduler, prefetch)` | Queue at an asynchronous boundary | Item |
| `limitRate(highTide, lowTide)` | Size of request batches sent upstream | Item / request batch |
| `buffer(maxSize)` | Number of items grouped into each batch | Item / batch |
| `onBackpressureBuffer(maxSize)` | Number of items held when consumer cannot keep up | Item / queue |
| `ConnectionProvider.maxConnections` | Maximum active connections in a pool | TCP channel / host |
| `pendingAcquireMaxCount` | Maximum requests waiting for a connection | Pending request |
| `pendingAcquireTimeout` | Time spent waiting for a connection | Duration |

The tuning goal is to control concurrency, demand, and memory so downstream services handle the load, latency remains stable, and the system can reject excess load in a controlled manner.

## 2. Reactive Streams Demand and Backpressure

Reactive Streams propagates pressure from consumer to producer via `Subscription.request(n)`. The subscriber requests the number of items it is ready to receive:

~~~text
        Downstream consumer
                |
                | request(8)
                v
         Operator / queue
                |
                | adjusted request(n)
                v
           Upstream source
                |
                v
            onNext(...)
~~~

Key points:

- Demand is the number of additional elements downstream allows upstream to emit.
- `request(Long.MAX_VALUE)` represents unbounded demand.
- `cancel()` tells upstream to stop emitting and release resources.
- Backpressure works only if upstream honors Reactive Streams demand or an adapter throttles that source.
- External callback/hot sources may emit faster than the consumer; in that case, choose a buffer, drop, latest, or overflow policy.

### 2.1. Operations That Commonly Request Unbounded Demand

Convenience subscription methods such as `subscribe()` with a lambda, `block()`, `blockFirst()`, `blockLast()`, `toIterable()`, and `toStream()` typically request unbounded demand. That is why you should not subscribe manually or block inside WebFlux controllers/services.

~~~java
// Not recommended in a WebFlux handler:
source.subscribe(this::process);

// Also avoid on the Netty event loop:
Result result = source.block();
~~~

Compose the publisher and return it to the framework:

~~~java
return source
        .concatMap(this::processReactive)
        .then();
~~~

`block()` can be appropriate at the boundary of a command-line demo or synchronous test, but should not be used inside a reactive request pipeline.

### 2.2. Backpressure Is Not Per-Second Rate Limiting

`limitRate(32)` splits demand into batches of at most 32 items. It does not mean only 32 items per second are allowed. To cap rate over time, use a rate limiter/token bucket or an application-layer policy.

## 3. What Does Prefetch Actually Control?

Prefetch is the number of items an operator requests ahead from upstream so data is ready when downstream needs it. It typically appears on operators with queues or nested Publisher handling.

Example:

~~~java
Flux<Result> results = ids.flatMap(
        id -> service.fetch(id),
        8,  // maxConcurrency
        4   // prefetch per inner Publisher
);
~~~

Meaning:

- At most 8 inner Publishers are subscribed to concurrently.
- For each inner Publisher, the operator may request ahead up to 4 items per its prefetch setting.
- With multi-item sources, the number of requested/buffered items can grow with concurrency and prefetch.
- If each inner is a `Mono<Result>`, it emits at most one item, so a prefetch of 4 does not produce four results per request.

Prefetch does **not** mean:

- Number of threads created.
- Number of TCP connections.
- Requests per second.
- Number of items guaranteed to sit in RAM at all times.
- Total item limit that the entire pipeline will process.

It is part of the demand/queue mechanism. An operator may emit fewer than prefetch items if the source completes early or downstream needs no more data.

### 3.1. Default Values Depend on the Operator

Reactor documentation notes that many operators use a default prefetch of 32, but you should not generalize that number as the default for every operator. Some operators also have their own concurrency parameter; defaults can vary by operator and Reactor version.

When predictable behavior is needed at a hotspot, explicitly call the overload taking prefetch:

~~~java
Flux<Result> result = source.flatMap(
        this::callRemote,
        12,
        2);
~~~

The numbers 12 and 2 are illustrative settings only. Choose them based on downstream latency, payload size, available connections, and memory budget.

## 4. Prefetch Across Key Operators

### 4.1. flatMap: Concurrency and Prefetch Are Different Parameters

~~~java
Flux<Product> products = productIds.flatMap(
        id -> webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class),
        16,
        1);
~~~

- `16` is the number of inner requests that can run concurrently.
- `1` is the prefetch of each inner Publisher.
- Since each inner here is a `Mono`, a prefetch of 1 naturally reflects one response per ID.
- `flatMap` output may interleave based on request completion times; original ID ordering is not guaranteed.

If concurrency is 16 while the pool allows only 4 connections to that host, at most 4 requests can hold connections while the rest wait to acquire. That is a separate queue from the prefetch queue.

### 4.2. concatMap: Sequential and Order-Preserving

~~~java
Flux<Result> results = ids.concatMap(
        id -> service.fetch(id),
        8);
~~~

`concatMap` subscribes to the next inner Publisher only after the previous inner completes. It preserves input order and avoids running multiple inner tasks concurrently. Here, prefetch adjusts demand against the **input source**, and does not mean running 8 requests concurrently.

Use it when commands depend on order or update shared state. If remote calls are independent and throughput is the primary goal, `concatMap` may constrain concurrency too tightly.

### 4.3. flatMapSequential: Runs in Parallel, Emits in Order

~~~java
Flux<Result> results = ids.flatMapSequential(
        id -> service.fetch(id),
        8,
        2);
~~~

The operator can subscribe to up to 8 inner Publishers concurrently, yet results are emitted in source order. If the first item processes slowly while subsequent items finish quickly, the later inner results must wait in a queue.

This is head-of-line blocking at the emission stage. Use it when parallelism is allowed but the contract requires ordering; do not pick it merely to "get both concurrency and order" without accounting for queue memory.

### 4.4. publishOn: Queue at a Scheduler Boundary

~~~java
Flux<Result> results = source
        .publishOn(Schedulers.parallel(), 32)
        .map(this::cpuBoundTransform);
~~~

`publishOn` shifts downstream processing onto the specified Scheduler. Prefetch is the capacity/demand at that asynchronous boundary. If upstream is fast and downstream processes slowly, items can wait in `publishOn`'s queue.

A `publishOn` does not create a new TCP pool. Nor does it make blocking I/O non-blocking. Use a Scheduler suited to the workload: CPU-bound, blocking I/O, and event-loop workloads have different characteristics.

### 4.5. limitRate: Splitting Requests into Batches

~~~java
Flux<Event> events = eventSource
        .limitRate(64, 48);
~~~

`highTide` is the initial request amount/batch cap; `lowTide` is the amount of demand replenished once enough items are consumed. For example, 64 and 48 create controlled request batches.

If only `limitRate(64)` is used, Reactor applies a default replenishment strategy proportional to prefetch. This shapes demand; it does not drop items and does not cap total item count.

## 5. Buffer: Batching or Waiting Queue for Consumers?

The word "buffer" appears across multiple operators with different meanings.

| Mechanism | Purpose | When Are Items Emitted Next? |
| --- | --- | --- |
| `buffer(100)` | Group 100 items into a List | When 100 items arrive or source completes |
| `bufferTimeout(100, Duration.ofMillis(50))` | Group by size or time | When 100 items arrive or 50 ms elapses |
| `publishOn(scheduler, 32)` | Queue across a Scheduler boundary | Based on downstream demand |
| `onBackpressureBuffer(256)` | Hold up to 256 items when downstream is slow | When downstream signals demand |
| Application-managed Queue/Sink | Bridge callback/event producer to reactive consumer | Per application queue policy |

Avoid using "buffer" generically when debugging. Specify whether it is a batch buffer, operator queue, scheduler queue, network buffer, or business queue.

### 5.1. buffer(N) Reshapes Demand

If downstream requests 2 buffers and each buffer holds 10 items, the operator may need to request 20 items from upstream to fill 2 buffers:

~~~text
Downstream request(2 batches)
            |
            v
      buffer(10)
            |
            v
Upstream request(2 x 10 = 20 items)
~~~

This matters when upstream is database paging or an API with per-call cost. Increasing batch size can reduce round trips, while increasing memory usage, latency waiting for a full batch, and transaction size.

### 5.2. bufferTimeout to Balance Throughput and Latency

~~~java
Flux<List<Event>> batches = events.bufferTimeout(
        100,
        Duration.ofMillis(50));
~~~

A batch is emitted once 100 events arrive or 50 ms passes. This helps reduce database/broker writes while keeping wait time bounded.

- Larger batches: fewer round trips, but higher memory and batch wait latency.
- Smaller batches: faster responsiveness, but higher per-write overhead.
- Shorter timeout: batches may contain fewer items, increasing downstream call frequency.
- Longer timeout: fuller batches, but the first item waits longer.

Measure p95/p99 and actual throughput; do not measure only items/second.

### 5.3. onBackpressureBuffer Must Be Bounded

~~~java
Flux<Event> safe = hotSource.onBackpressureBuffer(500);
~~~

Size-bounded overloads prevent the queue from growing indefinitely. When the limit is exceeded, the pipeline emits an overflow error per operator semantics. The application must decide how to handle that error: reject the producer, close the connection, perform bounded retries, or write to a durable queue.

Do not use unbounded buffers for streams that may run long or have uncontrolled producers. If each event holds 32 KiB and the queue has 10,000 events, raw payload alone is roughly 312.5 MiB, excluding object overhead and other queues.

### 5.4. Choosing Drop, Latest, or Buffer by Business Semantics

| Strategy | Behavior | Use When |
| --- | --- | --- |
| Bounded buffer | Holds items waiting for consumer; overflow triggers error or policy | You do not want to lose items during short bursts |
| Drop | Discards new items when there is no demand | Telemetry where sample loss is acceptable |
| Latest | Keeps the newest value, discarding older unconsumed values | Current state, sensor readings |
| Error | Signals an error when upstream exceeds intake capacity | You want fail-fast and load control |

Do not drop payment commands, audit records, or events requiring preservation without persistence/replay. For replaceable state, latest/coalescing can make more sense than a long buffer.

## 6. Estimating Memory from Prefetch and Queues

Prefetch and buffers must be sized by **item size**, not just item count.

A simple queue estimate:

\[
M_{\text{queue}} \approx
\sum_i Q_i \times S_i
\]

Where:

- \(Q_i\): maximum items that can wait in queue i.
- \(S_i\): average retained item size (payload + associated object graph).

Example:

- `flatMap` concurrency = 16.
- Prefetch per inner = 8.
- Average item size = 64 KiB.

Rough estimate of items that may be held across inner queues:

\[
16 \times 8 \times 64\text{ KiB} = 8\text{ MiB}
\]

This number is **not total application memory**. It excludes source queues, publishOn queues, batch buffers, decoded objects, Netty direct buffers, response bodies, pending connection requests, and JVM overhead. It simply illustrates how concurrency × prefetch × payload size can produce a significant footprint.

Raising concurrency from 16 to 64 while keeping prefetch and payload unchanged can multiply the number of requested/retained items severalfold. If downstream remains slow, increasing concurrency can raise memory usage without improving latency.

## 7. Connection Pools in Reactor Netty

`WebClient` typically uses the Reactor Netty connector in Spring Boot WebFlux. `HttpClient.create()` uses `ConnectionProvider` to manage reusable connections.

A pool manages connections per remote host; host refers to the hostname and port combination.

~~~text
                 WebClient
                     |
                 HttpClient
                     |
              ConnectionProvider
                     |
       +-------------+-------------+
       |             |             |
   Connection 1  Connection 2  Connection 3
       |             |             |
       +-------------+-------------+
                     |
                Remote API
~~~

With standard HTTP/1.1, each connection typically serves one active request at a time; once the response is read/released, the connection can return to the pool for reuse.

Key terms:

- **Active connection:** currently in use by a request.
- **Idle connection:** available to be leased by another request.
- **Pending acquire:** a request waiting for a connection.
- **Max connections:** cap on active channels in the pool.
- **Acquire timeout:** maximum time a request waits to lease a connection.
- **Max idle time:** how long a connection may remain idle.
- **Max life time:** maximum lifetime of a connection.

A connection pool acts as a transport-layer bulkhead: it caps concurrency toward a downstream host. However, if the pending queue is unbounded or the timeout is too long, waiting requests can pile up ahead of the pool.

## 8. Key ConnectionProvider Parameters

Example creating a dedicated pool for a downstream:

~~~java
ConnectionProvider provider =
        ConnectionProvider.builder("inventory-api")
                .maxConnections(32)
                .pendingAcquireMaxCount(64)
                .pendingAcquireTimeout(Duration.ofMillis(500))
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(2))
                .evictInBackground(Duration.ofSeconds(30))
                .metrics(true)
                .build();
~~~

| API | Meaning | How to Choose |
| --- | --- | --- |
| `maxConnections(32)` | Maximum active connections per host pool | Based on concurrency, latency, and upstream capacity |
| `pendingAcquireMaxCount(64)` | Maximum queued waiting requests | Bounds bursts and memory |
| `pendingAcquireTimeout(500ms)` | Time waiting for a connection before failing | Aligned with request SLA |
| `maxIdleTime(20s)` | Maximum idle age | Should be equal to or lower than server/proxy idle timeout |
| `maxLifeTime(2m)` | Maximum connection lifetime | Used when connections must rotate per policy |
| `evictInBackground(30s)` | Background check/eviction interval | Used when the pool should periodically evict expired idle connections |
| `metrics(true)` | Enables Reactor Netty metrics integration | Requires appropriate Micrometer/registry to observe |

The numbers above are illustrative examples only. Do not copy 32/64/500 ms across every service.

### 8.1. Distinguishing HttpClient.create() Defaults from a Custom Provider

Current Reactor Netty documentation describes two different cases:

- The default shared provider used by `HttpClient.create()` has a fixed pool with up to 500 active channels and 1000 pending acquire attempts per remote host.
- When building a custom `ConnectionProvider.builder(...)`, default `maxConnections` is calculated as 2 × available processors, minimum 16; default pending acquire count is 2 × max connections.
- Default `pendingAcquireTimeout` is 45 seconds.
- `maxIdleTime` and `maxLifeTime` are not set by default in the pool configuration table.

Defaults depend on the Reactor Netty version and can be altered via system properties. When creating a custom provider, explicitly configure limits suited to your workload rather than relying on the shared provider's defaults.

### 8.2. The Pending Queue Is a Real Queue

If `maxConnections=10` and `pendingAcquireMaxCount=20`, up to 10 requests hold connections while 20 requests can wait to acquire in that pool. Subsequent requests are rejected according to pool policy.

A bounded queue helps reject overload before requests wait indefinitely. An overly long `pendingAcquireTimeout` can keep requests in the queue even after most of their deadline has passed.

Do not arbitrarily set `pendingAcquireMaxCount(-1)` or `pendingAcquireTimeout(-1)` just to "eliminate pool timeouts." The system can accumulate unbounded waiters and exhaust memory.

### 8.3. Size MaxIdleTime Based on Server-Side Timeouts

If a reverse proxy closes connections after 30 seconds of idle time, setting client maxIdleTime significantly longer can cause the client to lease a connection already closed by the peer. Reactor Netty documentation recommends setting maxIdleTime equal to or shorter than the target server's idle timeout to reduce I/O errors from stale connections.

No single value fits every upstream. Check load balancer, gateway, and server timeouts before configuring.

## 9. HTTP/2: Connection Count Does Not Equal Concurrent Requests

HTTP/2 supports multiplexing multiple streams over a single TCP connection. Therefore:

- `maxConnections` still caps the number of channels/connections in the pool.
- One HTTP/2 connection can carry multiple concurrent streams up to peer/protocol limits.
- Concurrent requests also depend on stream capacity, server SETTINGS, and client limits.
- HTTP/2 metrics can expose active streams and pending streams.

Do not apply the HTTP/1.1 rule of "one connection = one active request" when sizing an HTTP/2 pool. When HTTP/2 is enabled, inspect stream metrics and peer limits before decreasing or increasing connection count.

## 10. Sizing Pools with Concurrency and Latency

A useful starting point is Little's Law:

\[
L = \lambda \times W
\]

Where:

- \(L\): average number of requests in the system.
- \(\lambda\): average throughput (requests/second).
- \(W\): average duration a request occupies the resource (seconds).

Example:

- Downstream receives 120 requests/second.
- Average duration from acquire until connection release is 80 ms = 0.08 seconds.

\[
L = 120 \times 0.08 = 9.6
\]

Thus roughly 10 connections are in use on average if all requests go to the same host under an HTTP/1.1 one-request-per-connection model.

This is only **average concurrency**, not the mandatory `maxConnections` value. You need headroom for bursts and tail latency while respecting what upstream can handle.

### 10.1. Practical Sizing Process

1. Measure expected throughput to each downstream host.
2. Measure how long a connection is held (request sent until response body is consumed/released).
3. Calculate average concurrency using Little's Law.
4. Measure p95/p99 and burst patterns.
5. Choose `maxConnections` with headroom without exceeding upstream capacity.
6. Choose a small `pendingAcquireMaxCount`, enough to absorb brief bursts.
7. Set `pendingAcquireTimeout` shorter than the remaining request deadline.
8. Run load tests and monitor active/idle/pending counts, latency, and error rate.
9. Change one parameter at a time to observe its impact.
10. Repeat across multiple hosts and load profiles.

### 10.2. Over-Sizing the Pool Can Make Things Worse

An oversized pool can:

- Increase concurrent TCP/TLS handshakes.
- Increase file descriptors, socket memory, and Netty buffer usage.
- Push more requests into an already-overloaded upstream.
- Increase lock/contention or queues at the target database/API.
- Increase connect timeouts or premature closes when opening too many connections at once.

Reactor Netty documentation warns that setting `maxConnections` too high under heavy load can trigger `PrematureCloseException` with a Connect Timeout root cause because too many connections are opened/acquired simultaneously.

If upstream can handle only 20 concurrent requests, setting the pool to 500 does not make it faster. It may simply shift the queue from the client to the server.

## 11. Aligning flatMap Concurrency with the Pool

Suppose:

- `flatMap` concurrency = 24.
- `ConnectionProvider.maxConnections` = 8.
- Each inner publisher makes an HTTP request to the same host.

You can picture it as:

~~~text
             flatMap concurrency = 24
           /          |           \
      8 active      8 pending    8 not yet active
          |             |
          v             v
     Pool max=8     acquire queue
          |
          v
       Remote API
~~~

Actual pending counts and inner creation timing also depend on demand/operators; the diagram simply illustrates pressure when concurrency exceeds pool capacity.

Guidelines:

- If you want to cap total remote calls, set flatMap concurrency close to the connection/stream capacity downstream accepts.
- If you want a small pending queue to absorb bursts, concurrency can exceed maxConnections by a controlled margin.
- If pending connections stay consistently high, re-examine upstream latency, pool size, concurrency, and deadlines.
- If active pool connections are low while flatMap backlog is large, the bottleneck may be the data source or scheduler rather than connections.

You do not have to force flatMap concurrency to always equal maxConnections. Both layers serve distinct purposes, yet there must be a clear overall budget.

## 12. Configuring WebClient with a Shared Pool

In a Spring Boot application, create the provider and WebClient as shared beans per downstream dependency:

~~~java
@Configuration
class PartnerClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider partnerConnectionProvider() {
        return ConnectionProvider.builder("partner-api")
                .maxConnections(32)
                .pendingAcquireMaxCount(64)
                .pendingAcquireTimeout(Duration.ofMillis(500))
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(2))
                .metrics(true)
                .build();
    }

    @Bean
    WebClient partnerWebClient(
            ConnectionProvider partnerConnectionProvider) {

        HttpClient httpClient =
                HttpClient.create(partnerConnectionProvider)
                        .option(
                                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                                1_000)
                        .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
                .baseUrl("https://partner.example.test")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

The example requires the corresponding Spring WebFlux, Reactor Netty, and Netty imports. Host `partner.example.test` is an illustrative address; replace it with your system's real endpoint.

Design points:

- The provider is created once and reused.
- The pool name helps distinguish metrics.
- The pool bounds active and pending counts.
- Acquire, connect, and response timeouts each serve a distinct purpose.
- `destroyMethod="dispose"` lets Spring release the custom provider when the context closes.

Do not create a new `ConnectionProvider` on every request/controller invocation. Doing so breaks connection reuse and creates unnecessary pools.

### 12.1. Separate Pools per Downstream as a Bulkhead

If one API is slow, do not let all downstreams share a single pool without good reason. You can create separate pools for inventory, billing, and notification to isolate resources per dependency.

Separate pools do not fully isolate CPU, event loops, heap, or databases, but they help control concurrency and pending acquires per remote host/service.

### 12.2. When Not to Use a Pool?

`HttpClient.newConnection()` opens a new connection per request instead of using a pool. This is not the default choice for normal HTTP workloads. It may be used for tests, special connections, or cases intentionally avoiding reuse; factor in handshake and socket overhead.

## 13. Metrics to Know Which Parameter to Tune

Reactor Netty can export metrics via Micrometer. For a pooled ConnectionProvider, the prefix is:

`reactor.netty.connection.provider`

Key metrics:

| Metric | Meaning | Signal to Investigate |
| --- | --- | --- |
| `total.connections` | Total active + idle connections | Growing abnormally or failing to drop |
| `active.connections` | Connections currently in use | Continuously near max |
| `idle.connections` | Idle connections in the pool | Too low during bursts |
| `max.connections` | Active connection cap | Cross-check against config |
| `pending.connections` | Requests waiting to acquire | Growing continuously |
| `pending.connections.time` | Time spent waiting to acquire | High p95/p99 |
| `max.pending.connections` | Pending limit | Frequently hitting ceiling |

HTTP client metrics also include `reactor.netty.http.client.response.time`, connect time, TLS handshake time, data sent/received, and errors. When HTTP/2 is needed, monitor active/pending streams.

Enable metrics:

~~~java
ConnectionProvider provider =
        ConnectionProvider.builder("partner-api")
                .maxConnections(32)
                .metrics(true)
                .build();
~~~

Ensure the appropriate Micrometer dependency and metrics registry are configured in the application. Do not put raw URLs/user IDs into metric tags because cardinality can grow unbounded.

### 13.1. Reading Metric Patterns

| Observation | Investigation Direction |
| --- | --- |
| Active always equals max, pending grows, response time stable | Pool may be too small for required throughput or concurrency is too high |
| Active equals max, pending grows, upstream response time rises | Upstream is slow; enlarging the pool may overload upstream further |
| Pending acquire time rises yet active is low | Issue with pool acquisition/connection lifecycle or host pool mapping |
| Active is low, event-loop pending tasks high | Bottleneck may be on the event loop/CPU, not the pool |
| Pool stable yet heap/direct memory rises | Look for buffers, response aggregation, queues, or leaks |
| Pending hits max then acquire times out | System is rejecting excess load beyond limits |

Do not draw conclusions from a single metric. Cross-check latency, error rate, CPU, heap/direct memory, event-loop tasks, and upstream metrics.

## 14. Tuning Prefetch, Buffers, and Pools by Scenario

### 14.1. CPU-Bound Transformation

For heavy CPU processing, raising flatMap concurrency or prefetch may not help once CPU is saturated. Use a bounded scheduler/parallelism appropriately and keep queues bounded:

~~~java
Flux<Result> result = source
        .publishOn(Schedulers.parallel(), 16)
        .map(this::expensiveTransform);
~~~

Monitor CPU, scheduler queues, and latency. Do not stack multiple consecutive `publishOn` calls unless a boundary is truly needed.

### 14.2. Slow Remote API

- Size pool max according to upstream capacity.
- Limit flatMap concurrency.
- Keep the pending queue small.
- Configure appropriate acquire/connect/response timeouts.
- Do not raise prefetch if the inner is a Mono and the bottleneck is connection latency.
- Use bounded retries and idempotency for operations with side effects.

### 14.3. Database Paging

You can use `limitRate` or `buffer` to regulate request/page sizes:

~~~java
Flux<Row> rows = repository.streamAll()
        .limitRate(128, 96);
~~~

If batch inserts are needed:

~~~java
Flux<Void> writes = rows
        .bufferTimeout(100, Duration.ofMillis(100))
        .concatMap(batch -> repository.insertBatch(batch));
~~~

Sequential batch writes help control database load. If batches are independent and can run in parallel, use `flatMap` with low concurrency and monitor locks/connection pool on the database driver.

### 14.4. Event Stream Faster Than Consumer

If the source can emit quickly:

- Prefer end-to-end backpressure.
- If the source does not support demand, use a bounded queue.
- Choose drop/latest only when business rules allow losing items.
- For events that must be preserved, use a broker/durable storage and consumer offsets instead of an in-RAM queue.
- Monitor overflow/drop counts.

### 14.5. Large Response Bodies

Do not enlarge every buffer just to "avoid slowness." Stream responses with `bodyToFlux` when the protocol permits, set memory limits, consume the body so connections are released, and avoid collecting everything into an overly large List/String.

## 15. Load Testing: Change One Variable at a Time

An experimental plan may include:

1. **Baseline:** small pool/concurrency/prefetch, bounded buffers.
2. **Warm-up:** initialize connections, DNS/TLS, and JIT.
3. **Steady load:** step up request rate incrementally.
4. **Burst:** generate short traffic spikes to observe pending queues.
5. **Soak:** sustain load over a long period to detect memory/connection leaks.
6. **Slow downstream:** simulate increased upstream latency.
7. **Failure:** return 429/503 or close connections.
8. **Recovery:** check whether the pool and pending queue return to baseline.

Change only one parameter group per run:

- Prefetch: 4 → 8 → 16.
- flatMap concurrency: 4 → 8 → 16.
- Pool maxConnections: 8 → 16 → 24.
- Pending queue: 8 → 16 → 32.
- Batch size: 32 → 64 → 128.

Record:

- Throughput.
- p50, p95, p99 latency.
- Error/timeout rate.
- Active/idle/pending connections.
- Pending acquire time.
- Heap and direct memory.
- CPU and event-loop pending tasks.
- Upstream latency, 429/503s, and connection errors.

Keep the configuration that delivers strong throughput **without pushing p99, error rate, or memory past thresholds**. Tuning is not a contest to maximize `maxConnections`.

## 16. Runnable Java 17+ Program: Capping the Pool at Two Connections

This example uses a local JDK HttpServer and WebClient/Reactor Netty. Six HTTP requests are issued with `flatMap` concurrency 6, yet the custom pool allows only two active connections. The server tracks concurrent in-flight requests to demonstrate the transport limit.

The program makes no internet calls and requires no Identity Provider or external API.

### 16.1. Project Structure

~~~text
webflux-pool-demo/
  pom.xml
  src/main/java/example/pool/PoolSizingDemo.java
~~~

Requires JDK 17+, Maven 3.6.3+, and Spring Boot 4.1.2.

### 16.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-pool-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 16.3. PoolSizingDemo.java

~~~java
package example.pool;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import io.netty.channel.ChannelOption;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

public final class PoolSizingDemo {

    private static void handle(
            HttpExchange exchange,
            AtomicInteger active,
            AtomicInteger maximum) {

        int current = active.incrementAndGet();
        maximum.accumulateAndGet(current, Math::max);

        try {
            Thread.sleep(150);

            String path = exchange.getRequestURI().getPath();
            String id = path.substring("/work/".length());
            byte[] body = ("ok-" + id)
                    .getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");

            exchange.sendResponseHeaders(200, body.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        }
        catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            exchange.close();
        }
        catch (IOException error) {
            exchange.close();
        }
        finally {
            active.decrementAndGet();
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        ExecutorService serverExecutor =
                Executors.newFixedThreadPool(8);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.setExecutor(serverExecutor);
        server.createContext("/work", exchange ->
                handle(exchange, active, maximum));
        server.start();

        ConnectionProvider provider =
                ConnectionProvider.builder("demo-pool")
                        .maxConnections(2)
                        .pendingAcquireMaxCount(10)
                        .pendingAcquireTimeout(
                                Duration.ofSeconds(3))
                        .build();

        try {
            HttpClient transport = HttpClient.create(provider)
                    .option(
                            ChannelOption.CONNECT_TIMEOUT_MILLIS,
                            1_000)
                    .responseTimeout(Duration.ofSeconds(2));

            WebClient client = WebClient.builder()
                    .baseUrl("http://127.0.0.1:"
                            + server.getAddress().getPort())
                    .clientConnector(
                            new ReactorClientHttpConnector(transport))
                    .build();

            List<String> responses = Flux.range(1, 6)
                    .flatMap(
                            id -> client.get()
                                    .uri("/work/{id}", id)
                                    .retrieve()
                                    .bodyToMono(String.class),
                            6,
                            1)
                    .sort()
                    .collectList()
                    .block(Duration.ofSeconds(10));

            List<String> expected = List.of(
                    "ok-1", "ok-2", "ok-3",
                    "ok-4", "ok-5", "ok-6");

            if (!expected.equals(responses)) {
                throw new AssertionError(
                        "Unexpected responses: " + responses);
            }

            if (maximum.get() > 2) {
                throw new AssertionError(
                        "Pool limit exceeded: " + maximum.get());
            }

            System.out.println("responses=" + responses);
            System.out.println(
                    "max-server-in-flight=" + maximum.get());
        }
        finally {
            provider.disposeLater()
                    .block(Duration.ofSeconds(3));
            server.stop(0);
            serverExecutor.shutdownNow();
        }
    }
}
~~~

### 16.4. Running the Program

From the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.pool.PoolSizingDemo
~~~

**Expected stdout:**

~~~text
responses=[ok-1, ok-2, ok-3, ok-4, ok-5, ok-6]
max-server-in-flight=2
~~~

Explanation:

- `Flux.range(1, 6)` creates six IDs.
- `flatMap(..., 6, 1)` allows up to six inner requests to be active concurrently; prefetch per Mono is 1.
- `ConnectionProvider.maxConnections(2)` limits active connections in the pool to the local host to two.
- Remaining requests wait to acquire, then use connections in turn as earlier requests complete.
- The JDK HttpServer tracks running handlers; the assertion ensures that number never exceeds 2.
- `sort()` stabilizes response order before printing.

This is a local HTTP/1.1 demo. HTTP/2 multiplexes multiple streams over one connection, so active request count cannot be inferred from connection count alone.

## 17. Reading Demo Results and Extending Experiments

Try changing:

~~~java
.maxConnections(4)
~~~

while keeping `flatMap concurrency=6`. The server can handle up to four concurrent requests.

Try changing:

~~~java
.maxConnections(2)
.pendingAcquireMaxCount(1)
~~~

When multiple requests acquire at once, some may be rejected because the pending queue is too small. This illustrates backpressure/bulkhead behavior at the connection pool layer; acquire errors should not be mistaken for JSON or business errors.

Try changing `flatMap concurrency` to 2 while keeping the pool at 2: concurrent requests created are also bounded at the pipeline before reaching the pool. This helps distinguish queues caused by `flatMap` from queues caused by `ConnectionProvider`.

The demo deliberately uses a local server so results do not depend on the internet. Per-request duration may vary by machine, yet the active connection limit must still not exceed 2.

## 18. Common Tuning Pitfalls

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Raising prefetch to increase TCP connections | No effect on the connection pool | Tune `maxConnections` separately |
| Raising maxConnections to fix CPU queues | Sends more requests while CPU stays saturated | Measure event-loop/CPU/schedulers |
| Raising flatMap concurrency unboundedly | Increases inner subscriptions and downstream pressure | Bound concurrency |
| Using high prefetch for huge payloads | Queues retain excessive memory | Lower prefetch or stream smaller chunks |
| `buffer()` on an infinite stream | Never emits batches until complete, unbounded memory growth | `buffer(maxSize)` or `bufferTimeout` |
| Unbounded `onBackpressureBuffer` | Queue grows with producer when consumer is slow | Bounded buffer + overflow policy |
| Using drop for events that must be preserved | Loss of command/audit/business events | Durable queue or fail-fast |
| Pool max larger than upstream capacity | Pushes overload onto upstream | Size by SLA and load tests |
| Unbounded pending queue | Waiting requests pile up, raising latency and memory | Bounded `pendingAcquireMaxCount` |
| Overly long `pendingAcquireTimeout` | Requests wait even after deadline expires | Align with business deadline |
| Creating `ConnectionProvider` per request | Loses reuse, increases socket/TLS churn | Singleton provider per downstream |
| `maxIdleTime` longer than server timeout | High risk of reusing stale connections | Set equal to or below peer idle timeout |
| Ignoring HTTP/2 multiplexing | Incorrect connection sizing | Monitor active streams |
| Using `flatMapSequential` for every flow | Head-of-line queues and latency | Use only when output order is required |
| Looking only at average throughput | Misses p99 and bursts | Measure latency percentiles and error rate |
| Changing multiple parameters at once | Cannot tell what improved/degraded performance | Change one variable at a time |

## 19. Pre-Production Tuning Checklist

- [ ] Know whether the source supports Reactive Streams backpressure or is a hot/callback source.
- [ ] Know which operators create queues and what their capacities are.
- [ ] Choose `flatMap` concurrency based on downstream capacity.
- [ ] Choose prefetch based on item count and payload size.
- [ ] Distinguish inner publisher prefetch from `publishOn` prefetch.
- [ ] Use `limitRate` when demand needs to be split into batches.
- [ ] Buffer only with a clear batch/queue policy.
- [ ] Every queue that can grow with load has a bound or durable storage.
- [ ] Overflow policies match business semantics.
- [ ] Know whether the HTTP protocol is HTTP/1.1 or HTTP/2.
- [ ] Maintain a shared `ConnectionProvider` per downstream host/service.
- [ ] Size `maxConnections` based on concurrency and upstream capacity.
- [ ] Bound `pendingAcquireMaxCount`.
- [ ] Set `pendingAcquireTimeout` according to request deadlines.
- [ ] Align `maxIdleTime` with server/proxy timeouts.
- [ ] Enable metrics and monitor active/idle/pending connections.
- [ ] Monitor p95/p99, errors, CPU, heap, and direct memory.
- [ ] Load test steady, burst, slow downstream, and recovery scenarios.
- [ ] Never block the event loop or manually subscribe inside WebFlux handlers.
- [ ] Never enlarge a pool merely to mask upstream latency or capacity bugs.

## 20. Self-Check Questions

**Question 1.** What is prefetch?

The amount of demand an operator requests ahead from upstream or the number of items that can be held ready in the operator's internal queue.

**Question 2.** Is prefetch a thread count?

No. Threads/Schedulers are execution resources; prefetch is demand/queue capacity.

**Question 3.** How does `flatMap` concurrency differ from prefetch?

Concurrency caps how many inner Publishers run concurrently; prefetch caps how many items are requested ahead from each inner Publisher.

**Question 4.** What does `publishOn` prefetch control?

Capacity/demand at the asynchronous boundary where signals transfer onto a Scheduler.

**Question 5.** Does `limitRate(32)` mean 32 items/second?

No. It splits upstream demand into batches of at most 32 items.

**Question 6.** How can `buffer(10)` alter requests?

If downstream requests two batches, `buffer` may request 20 items from upstream to assemble two full batches.

**Question 7.** Why are unbounded buffers dangerous?

Producers can emit faster than consumers for extended periods, causing queues to retain too many objects/payloads and exhaust memory.

**Question 8.** What does `ConnectionProvider.maxConnections` limit?

The maximum number of active connections in a pool to a remote host.

**Question 9.** What is `pendingAcquireMaxCount`?

The cap on requests waiting to acquire a connection when the pool has reached `maxConnections`.

**Question 10.** How does `pendingAcquireTimeout` differ from `responseTimeout`?

Acquire timeout caps how long a request waits for a connection from the pool; Reactor Netty's `responseTimeout` controls the idle silence interval while reading the response per connector semantics.

**Question 11.** Why should you avoid creating a `ConnectionProvider` per request?

It eliminates connection reuse and creates too many pools/sockets, increasing resource churn.

**Question 12.** Does HTTP/2 use one request per connection?

No. HTTP/2 multiplexes multiple streams over one connection; stream capacity/metrics must be observed.

**Question 13.** What is Little's Law used for?

Estimating average concurrency from throughput and the duration a request occupies a resource.

**Question 14.** If pending connections rise while active is always at max, what should you inspect?

Upstream latency, `maxConnections`, `flatMap` concurrency, acquire timeout, and the remote service's capacity.

**Question 15.** When should drop/latest be used?

When business rules allow discarding old or new items; never use them for events that must be preserved without persistence/replay.

## 21. Official References

- [Project Reactor — On Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): Reactive Streams demand, prefetch, buffering, and limitRate.
- [Project Reactor — Flux JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): flatMap, concatMap, flatMapSequential, publishOn, buffer, and limitRate.
- [Project Reactor — Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): publishOn/subscribeOn and execution context.
- [Reactor Netty — HTTP Client Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html#connection-pool): maxConnections, pendingAcquireMaxCount, idle/lifetime, and leasing.
- [Reactor Netty — HTTP Client Metrics](https://projectreactor.io/docs/netty/release/reference/http-client.html#_metrics): pool metrics, pending acquisitions, active/idle connections, and HTTP client latency.
- [Reactor Netty — Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#timeout-configuration): pending acquire, connect, response, and per-phase timeouts.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client and connector integration.
- [Spring Boot — WebClient](https://docs.spring.io/spring-boot/reference/io/rest-client.html): WebClient and builder configuration in Spring Boot.

**Key Takeaway:** Prefetch controls operator demand/queues; buffers group or hold items; connection pools cap connections to remote hosts. Tune concurrency and prefetch to item sizes, queues to memory budgets, and pools to throughput × connection hold time and upstream capacity. Bound pending acquires, monitor active/idle/pending metrics, and load test p95/p99 before changing production configuration.