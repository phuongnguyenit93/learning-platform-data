# Queue Bounds, Timeouts, and Overload Rejection in Spring WebFlux

## 1. Goal: Protecting the System When Load Exceeds Capacity

A reactive application can handle many concurrent requests without dedicating a thread to each request. However, **non-blocking does not mean infinite capacity**. CPU, heap, direct memory, file descriptors, connection pools, databases, the event loop, and downstream APIs all have limits.

When the incoming request rate exceeds the system's processing rate, queued work accumulates. If every queue is unbounded, the system can suffer continuously rising heap/direct memory, requests waiting past their deadlines, cascading timeouts, connection pool exhaustion, retry storms, event-loop stalls, and noisy-neighbor interference across tenants.

Overload protection requires coordinating three mechanisms:

1. **Bounded queues:** hold a finite backlog of waiting work to absorb short bursts.
2. **Timeouts/deadlines:** stop waiting or processing once work no longer has value within its time budget.
3. **Load shedding/admission control:** reject new work when safe capacity is exhausted.

A well-designed system does not try to accept every request. It admits what it can complete within SLA and rejects excess load as early as possible.

## 2. Map of Queues in a WebFlux Request

~~~text
Client
  |
  v
Load balancer / ingress queue
  |
  v
OS listen / accept backlog
  |
  v
Reactor Netty connection + HTTP processing
  |
  v
WebFlux handler / application admission gate
  |
  +--> Reactor operator queues (flatMap / publishOn / buffer)
  |
  +--> Scheduler task queue
  |
  +--> WebClient ConnectionProvider pending-acquire queue
  |
  +--> Database connection pool / downstream service queue
  |
  v
Response
~~~

| Location | Unit Held | Example Limit | Behavior When Full |
| --- | --- | --- | --- |
| Load balancer/ingress | Request | Max pending requests, queue timeout | Return 429/503 or reject at edge |
| OS accept backlog | Unaccepted TCP connection | Socket backlog | OS-dependent behavior; may reject/drop |
| Reactor Netty server | TCP connection | `HttpServer.maxConnections` | Closes new connections at cap |
| Admission gate | In-flight request | Semaphore/bulkhead | Fail-fast 503/429 |
| Reactor operator | Item | Prefetch, bounded buffer | Waits on demand or overflows |
| Scheduler | Runnable/task | Thread cap + queue capacity | Queue full/reject task |
| WebClient pool | Request awaiting connection | `pendingAcquireMaxCount` | Acquire timeout/reject |
| Database pool | Request awaiting connection | Max pool size + wait timeout | Pool timeout/reject |

A queue may hold TCP connections, HTTP requests, Publisher items, tasks, or connection-acquire requests. Identify the right layer before tuning.

## 3. Backpressure vs. Admission Control

### 3.1. Backpressure Regulates Demand Between Publisher and Subscriber

Reactive Streams propagates demand via `Subscription.request(n)`. Downstream requests how many items it is ready to receive; upstream emits only per demand if it complies with Reactive Streams.

~~~text
Downstream
    |
    | request(8)
    v
Operator / queue
    |
    | propagated/adjusted demand
    v
Upstream Publisher
    |
    v
  onNext(...)
~~~

Backpressure works well when the entire pipeline stays inside one reactive flow and the source knows how to honor demand.

### 3.2. Admission Control Decides Whether to Accept New Work

Admission control checks capacity before starting resource-intensive work: are permits available, is queue space available, has the tenant exceeded quota, is downstream healthy, and is enough deadline remaining? If not, the request is rejected instead of waiting indefinitely.

HTTP clients can send requests to the server independently of demand inside a Publisher. Having a handler use `flatMap(concurrency)` does not automatically cap incoming TCP connections, incoming HTTP requests, or requests already accepted by the framework.

Backpressure also does not automatically throttle a callback/hot source that ignores demand. When such a source keeps emitting, the application needs a bounded queue or a drop/reject policy.

Convenience subscription methods such as `subscribe()`, `block()`, and `toIterable()` typically request unbounded demand `Long.MAX_VALUE`. Subscribing manually inside a WebFlux handler can break the lifecycle/backpressure managed by the framework.

**Use backpressure to regulate data flow; use admission control to protect request-processing capacity.**

## 4. Why Queues Cannot Solve Sustained Overload

Let:

- \(\lambda\): incoming request arrival rate (requests/second).
- \(\mu\): completed processing rate (requests/second).
- \(Q\): number of waiting requests.
- \(S\): average memory size of one request.

If \(\lambda > \mu\) over an extended period, the queue grows until hitting its limit. A bounded queue defines how much waiting work the system holds before rejecting, without increasing processing capacity.

Little's Law:

\[
L = \lambda \times W
\]

In steady state, \(L\) is the average number of operations in the system, \(\lambda\) is actual throughput, and \(W\) is the average time an operation spends in the system.

For example, suppose a service processes 100 requests/second. If on average 200 requests are waiting/in-flight, Little's Law puts average system time at roughly 2 seconds:

\[
W = \frac{L}{\lambda} = \frac{200}{100} = 2s
\]

If the SLA allows only 500 ms, a queue holding 200 requests is pointless: many requests have already blown past their deadline before their turn arrives.

### 4.1. Estimating Queue Wait Time and Memory

With a FIFO queue and relatively steady processing rate:

\[
T_{\text{queue}} \approx \frac{Q_{\text{ahead}}}{\mu}
\]

If 80 tasks sit ahead of a request and workers finish 40 tasks/second, estimated wait time is 2 seconds. If only 300 ms of deadline remain, reject the request instead of enqueuing it.

Memory estimate:

\[
M_{\text{queue}} \approx Q \times S
\]

If a queue holds 5,000 items averaging 24 KiB of payload/object graph each, that portion alone is roughly 117.2 MiB—excluding queue nodes, wrappers, references, Netty direct buffers, decoded DTOs, trace contexts, and other queues.

**Queues must be bounded by both memory budget and deadline.**

## 5. Designing Bounded Queues

A bounded queue has a maximum capacity, a dequeue discipline, and an overflow policy when a producer submits an item while the queue is full.

| Policy | When Full | Use When |
| --- | --- | --- |
| Reject / error | Rejects new item | Critical commands, fail-fast desired |
| Drop newest | Discards incoming item | Telemetry where losing recent samples is acceptable |
| Drop oldest | Evicts oldest item to admit newest | Freshness matters more than history |
| Latest/coalesce | Retains only newest state | Dashboards, sensor readings |
| Durable queue | Writes to persistent broker/storage | Jobs to process later or needing replay |
| Priority queue | Prioritizes critical work groups | Multiple SLA tiers |

Do not pick drop merely to avoid exceptions. If items are payments, audit events, order commands, or workflows requiring preservation, use a durable queue/outbox/broker and proper acknowledgements.

### 5.1. onBackpressureBuffer(maxSize)

~~~java
Flux<Event> bounded = hotEvents.onBackpressureBuffer(
        256,
        BufferOverflowStrategy.ERROR);
~~~

This Reactor API requests unbounded demand from upstream and holds up to a 256-item backlog if downstream lacks demand. When exceeded, the overflow strategy is applied.

Thus `onBackpressureBuffer(maxSize)` is a **bounded buffer with an overflow policy**, not always a way to propagate demand back to a hot source. The source may still emit fast and fill the queue.

Strategies can include ERROR, DROP_LATEST, and DROP_OLDEST depending on the overload/version. Choose per business semantics and ensure discarded items/resources are cleaned up properly.

### 5.2. Sinks with Bounded Queues

When an application bridges producers to a reactive consumer itself, it can use a unicast sink with a bounded queue:

~~~java
Queue<Command> queue = new ArrayBlockingQueue<>(128);

Sinks.Many<Command> commands =
        Sinks.many().unicast().onBackpressureBuffer(queue);

Sinks.EmitResult result = commands.tryEmitNext(command);

if (result == Sinks.EmitResult.FAIL_OVERFLOW) {
    // Queue full: reject/defer/durable persistence.
}
else if (result != Sinks.EmitResult.OK) {
    // Handle no subscriber/terminated/non-serialized.
}
~~~

- `ArrayBlockingQueue` bounds waiting commands.
- `tryEmitNext` does not block waiting for queue space; it returns immediately.
- `FAIL_OVERFLOW` is the signal the producer must handle.
- `unicast` supports only one Subscriber; each worker/session needs a suitable topology.
- In-RAM queues are not durable across process restarts.
- If multiple producers emit concurrently, handle emission results and concurrency per the sink's contract.

Do not ignore `EmitResult`. If the producer skips checking the result, commands can be rejected while the application assumes they were accepted.

## 6. Bounding Concurrency with flatMap and Bulkheads

### 6.1. flatMap Concurrency

~~~java
Flux<Result> results = requests.flatMap(
        request -> downstream.call(request),
        12,
        1);
~~~

12 is the maximum number of concurrently subscribed inner Publishers; 1 is the prefetch per inner Publisher. Results may interleave by completion order. When concurrency is reached, the operator throttles subscribing to new inners and may retain some outer items per demand/prefetch.

This is a pipeline-internal concurrency limit, not a per-second rate limit, and does not automatically return HTTP 429/503 at ingress.

### 6.2. concatMap

~~~java
Flux<Result> results = requests.concatMap(
        downstream::call,
        16);
~~~

`concatMap` processes only one inner Publisher at a time and preserves order. The prefetch parameter does not mean 16 downstream requests run concurrently.

Use when command ordering matters or shared state disallows parallel execution. If remote calls are independent, `concatMap` can throttle throughput overly aggressively.

### 6.3. Per-Dependency Bulkheads

~~~text
WebFlux API
   |
   +--> Inventory bulkhead: 12 calls
   |
   +--> Billing bulkhead:    4 calls
   |
   +--> Search bulkhead:    20 calls
~~~

Bulkheads isolate resources so one slow downstream cannot consume all capacity meant for other dependencies. Resilience4j provides `SemaphoreBulkhead` and `FixedThreadPoolBulkhead`. Reactor operators can emit `BulkheadFullException` when the bulkhead is full.

A semaphore bulkhead suits many reactive/I/O models because it does not introduce a replacement thread pool. Set wait duration to 0 to fail fast; waiting for a permit by blocking the event loop is a design flaw.

ThreadPoolBulkhead has a queue capacity. That is a separate task queue; bound its queue, wait duration, and rejection handling. Do not use a thread pool bulkhead as a way to accidentally turn all reactive I/O into blocking workers.

## 7. Rate Limits Differ from Concurrency Limits

A **concurrency limit** caps how many operations run at the same time. A **rate limit** caps how many operations are allowed to start within a time window.

Example:
- Concurrency = 10: at most 10 requests in-flight simultaneously.
- Rate limit = 100 requests/second: at most 100 starts per second per the limiter algorithm.
- A single request may run for 2 seconds; at 100 req/s, concurrency can exceed 10 without a bulkhead.

| Mechanism | Question Answered | Scope |
| --- | --- | --- |
| Semaphore/Bulkhead | How many requests are running right now? | Concurrent calls |
| Token bucket/rate limiter | How many requests are allowed in this interval? | Requests/time |
| Queue capacity | How many waiting requests can be held? | Pending work |
| Timeout | How long at most to wait or process? | Duration/deadline |

Rate limits are typically applied per API key, user, tenant, IP, or endpoint. With only a global rate limit, one large tenant can exhaust another tenant's quota.

When a single caller exceeds its quota, HTTP 429 is usually appropriate. When the entire service is temporarily unable to serve traffic, 503 expresses that more accurately.

## 8. Timeouts: Multiple Layers, Multiple Meanings

No single timeout protects an entire request. A WebFlux request may traverse client connect, DNS, TLS handshake, connection pool acquire, request upload/read, downstream response, Mono/Flux operators, server request-body read, overall request deadline, and idle connection timeout.

| Timeout | What Does It Bound? | API / Location |
| --- | --- | --- |
| Connect timeout | Establishing TCP connection to remote | Reactor Netty `CONNECT_TIMEOUT_MILLIS` |
| Pool acquire timeout | Waiting to lease a connection from client pool | `pendingAcquireTimeout` |
| Response timeout | Duration waiting for response/read per Reactor Netty | `HttpClient.responseTimeout` |
| Mono/Flux timeout | Duration waiting for Publisher signals | `Mono.timeout`, `Flux.timeout` |
| Server read timeout | Interval between network reads of request body | `HttpServer.readTimeout` |
| Server request timeout | Total time reading request content | `HttpServer.requestTimeout` |
| Server idle timeout | Connection waiting for next HTTP request | `HttpServer.idleTimeout` |
| Overall deadline | Total allowed processing duration | Application/request deadline |

### 8.1. Pool Acquire Timeout vs. Response Timeout

Suppose a client pool has 20 connections and all are busy:

- New requests wait for a connection in the pending queue.
- If no connection arrives before acquire timeout, the request fails acquire.
- Once a connection is acquired, the request begins connect/write/read.
- Response timeout governs the response-waiting phase, not time spent in the pending queue.

~~~java
ConnectionProvider provider =
        ConnectionProvider.builder("orders-api")
                .maxConnections(20)
                .pendingAcquireMaxCount(40)
                .pendingAcquireTimeout(Duration.ofMillis(150))
                .build();

HttpClient client = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
        .responseTimeout(Duration.ofMillis(800));
~~~

Values are illustrative only. Bounded `pendingAcquireMaxCount` protects the queue; `pendingAcquireTimeout` caps wait time. Reactor Netty currently defaults acquire timeout to 45 seconds if unconfigured, which can be far too long for an API request SLA.

### 8.2. Reactor's Timeout Operator

~~~java
Mono<PartnerResult> result = partnerClient.fetch()
        .timeout(Duration.ofMillis(700));
~~~

`timeout` bounds time from subscription to signals per Publisher semantics. For a Mono awaiting one result, timeout emits an error if no signal arrives before the deadline. For a Flux, timeout applies between signals by default; it is not automatically an absolute deadline for the entire stream.

If an overall operation deadline is needed, define semantics clearly and place the timeout at the right boundary. Do not assume a simple `Flux.timeout(Duration)` always bounds the total duration of an infinite stream.

When timeout triggers, Reactor cancels the upstream subscription. However, cancellation does not guarantee side effects already sent to external systems are rolled back or halted immediately. Downstream may have already received the command and continue executing it.

For write operations, use idempotency keys, transaction semantics, or queryable processing status so retries do not create duplicate transactions.

### 8.3. Server readTimeout and requestTimeout Are Not Handler Deadlines

Reactor Netty server distinguishes:

- `readTimeout`: maximum time between network-level reads while reading request content.
- `requestTimeout`: total time spent reading request content.
- `idleTimeout`: time a connection stays open waiting for the next HTTP request.

`requestTimeout` is not the deadline for the entire controller/service. If a handler calls downstream for 3 seconds, you need a deadline on the reactive operation or a separate gateway/request deadline.

~~~java
HttpServer server = HttpServer.create()
        .readTimeout(Duration.ofSeconds(5))
        .requestTimeout(Duration.ofSeconds(20))
        .idleTimeout(Duration.ofSeconds(60));
~~~

Values are illustrative; choose them according to body sizes, client networks, proxy timeouts, and API contracts.

## 9. End-to-End Deadlines

If every layer sets independent timeouts without a shared budget, child timeouts can outlast the parent deadline.

Example request with a 1,500 ms deadline:

| Phase | Example Budget |
| --- | ---: |
| Admission/queue wait | 100 ms |
| Connection acquire | 100 ms |
| Connect/TLS | 200 ms |
| Downstream processing | 700 ms |
| Serialize/response | 150 ms |
| Safety margin | 250 ms |
| **Total** | **1,500 ms** |

This is an illustrative budget, not a default configuration.

- Admission queues should keep a request only if enough time remains to process it.
- Pool acquire timeout must be shorter than the remaining deadline.
- Downstream timeout must leave time for serialization/response.
- Do not retry if the next attempt lacks sufficient budget.
- Propagate deadlines/remaining budget downstream if the protocol supports it.
- When the deadline expires, cancel cancelable work and record timeout metrics at the right layer.

If a request has already waited 1 second in a queue, do not start a downstream call with a 2-second timeout when the caller will wait at most 1.5 seconds.

## 10. Choosing HTTP Status Codes on Rejection or Timeout

| Status | Use When | Example |
| --- | --- | --- |
| 429 Too Many Requests | Caller/tenant exceeds rate quota | API key exceeds 100 requests/minute |
| 503 Service Unavailable | Service is temporarily overloaded or in maintenance | Admission gate out of permits, dependency unavailable |
| 504 Gateway Timeout | API/gateway does not receive timely response from upstream | Orders API waits on Inventory API past deadline |
| 408 Request Timeout | Server did not receive complete request within allowed time | Client uploads body too slowly (server-behavior dependent) |

`Retry-After` can express wait seconds or an HTTP-date. When returning 503 due to temporary overload, the server can suggest a retry delay. For 429, Retry-After is also helpful when quotas reset periodically.

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 2

{"code":"SERVICE_OVERLOADED"}
~~~

Do not send an overly optimistic Retry-After if the system does not know when it will recover. Without a reliable estimate, prefer client backoff policies over promising a specific time.

### 10.1. Special Note on Server maxConnections

`HttpServer.maxConnections(n)` caps TCP connections. When the limit is reached, Reactor Netty closes new connections immediately. It does not guarantee the request receives HTTP 503 because the HTTP connection may not even be accepted to process a request.

With HTTP/2, multiple streams can share a TCP connection; capping connections does not equal capping HTTP/2 streams/requests.

If you need to return 429/503 with a response body and Retry-After, enforce admission/rate limiting at the layer that has already accepted the HTTP request or at a gateway capable of returning responses. Use the connection cap as an extra transport-level guard.

## 11. Fail-Fast Admission Gate in WebFlux

A simple way to cap concurrently running tasks is a non-waiting semaphore:

~~~java
@Component
class AdmissionGate {

    private final Semaphore permits = new Semaphore(20);

    <T> Mono<T> execute(Supplier<Mono<T>> work) {
        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                return Mono.error(new OverloadedException());
            }

            return Mono.defer(work)
                    .doFinally(signal -> permits.release());
        });
    }
}
~~~

How it works:

1. `Mono.defer` attempts to acquire a permit only upon subscription.
2. `tryAcquire()` returns immediately without blocking the event loop.
3. If no permit is available, it immediately returns an overload error.
4. If a permit is acquired, it subscribes to the reactive work.
5. `doFinally` releases the permit on complete, error, or cancel.

This is a **queue-less** admission gate. It favors failing fast to avoid adding latency and memory pressure.

### 11.1. Mapping Overload Errors to 503

~~~java
@RestControllerAdvice
class OverloadExceptionHandler {

    @ExceptionHandler(OverloadedException.class)
    ResponseEntity<Map<String, String>> overloaded() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.RETRY_AFTER, "1")
                .body(Map.of("code", "SERVICE_OVERLOADED"));
    }
}
~~~

This example shows returning 503 and suggesting a 1-second retry. For per-API-key/tenant quotas, 429 and an appropriate Retry-After policy fit better.

Do not catch every `RuntimeException` and convert it to 503. Map only classified admission/bulkhead errors; input, authentication, authorization, and bug errors must keep their own semantics.

### 11.2. Why doFinally Must Release the Permit

The permit must be returned whether the publisher completes successfully, errors, is canceled due to client disconnect, or is canceled by a timeout operator.

If you release only in `doOnSuccess`, permits can leak on errors/cancellations and the system will permanently reject requests over time.

In complex code, consider `usingWhen` or an abstraction with explicit lifecycle management for async resources.

## 12. Controlled Bounded Waiting Queues

Sometimes short bursts must be absorbed rather than rejected immediately. The queue must then have finite capacity, a wait timeout, an overflow policy, depth/age/rejection metrics, cancellation when callers hit deadlines, and cleanup on process shutdown.

Example Resilience4j ThreadPoolBulkhead configuration:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      partner:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 32
        keepAliveDuration: 20ms
~~~

This illustrative config applies to work allowed to run on a worker thread pool. Queue capacity 32 caps waiting tasks; tasks beyond that are rejected per bulkhead behavior.

For pure reactive I/O, a semaphore bulkhead is usually better because requests do not need to hop to a separate thread pool. If a blocking SDK must run, use a bounded scheduler or thread pool with a bounded queue and offload work onto appropriate workers.

### 12.1. Setting Queue Timeouts

A request may be admitted into a queue yet expire before starting if its deadline passes. Do not execute already-expired requests just to finish work the caller is no longer waiting for.

- Record request arrival time/deadline.
- When dequeuing an item, compute remaining budget.
- If remaining budget is insufficient, drop/reject the item before calling downstream.
- If the caller already canceled, remove the item from the queue if the queue supports remove/cancel.
- Do not retain large payloads in the queue if only a request ID and metadata are needed to fetch later.

### 12.2. FIFO or Priority Queue?

FIFO is simple and fair by arrival order, yet one very slow task can delay small tasks behind it.

Priority queues can prioritize critical requests, yet low-priority groups must be protected from starvation. You can use per-tenant/service-tier queues, weighted fair scheduling, or independent quotas.

Do not let a single tenant monopolize a global queue. Per-tenant limits and global caps help prevent noisy-neighbor issues.

## 13. Timeouts and Cancellation Must Work Together

When a request times out, WebFlux may cancel the handler subscription, Reactor operators propagate cancellation upstream, WebClient may cancel the request per connector semantics, and the connection pool/transport releases or handles the connection according to state. However, side effects that already reached a database/remote service may still be executing.

Therefore:

1. Use reactive clients and publishers with clear cancellation semantics.
2. Do not manually subscribe to detach work from the request lifecycle without a dedicated job system.
3. For jobs that must continue after client disconnect, enqueue into a durable worker rather than holding an HTTP request.
4. For write commands, use idempotency keys and transactions.
5. For retries, ensure the prior attempt can no longer commit a duplicate or that the operation is idempotent.

**A timeout is a caller wait limit; it is not a distributed rollback.**

## 14. Retries During Overload Can Worsen Incidents

Suppose a service can handle only 100 requests/second yet receives 150 requests/second. If every client times out and retries immediately, incoming request volume climbs even higher.

Retries require max attempts, exponential backoff, jitter, retrying only transient errors and safe/idempotent operations, respecting `Retry-After`, never retrying 400/401/403 or business validation errors, not retrying relentlessly when bulkheads/rate limiters report full, and fitting the total retry budget inside the original deadline.

~~~java
Retry retry = Retry.backoff(2, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(1))
        .jitter(0.5)
        .filter(this::isTransientFailure);

Mono<Result> result = remoteCall()
        .retryWhen(retry);
~~~

This illustrative snippet requires defining `isTransientFailure` and classifying exceptions. 2 is the number of retries after the initial attempt, not total calls. Do not retry explicit server overload responses if immediate retries would lengthen queues further.

## 15. Coordinating Circuit Breakers, Bulkheads, and Rate Limiters

| Pattern | What Does It Protect? | When Does It Trigger? |
| --- | --- | --- |
| Rate limiter | New request rate | Quota/requests per time exceeds threshold |
| Bulkhead | Concurrent operations | Permits/threads exhausted |
| Bounded queue | Short bursts | Consumer temporarily slow |
| Timeout | Wait/processing time | Deadline expires |
| Circuit breaker | Failing dependency | Error/slow-call rate exceeds threshold |
| Retry | Transient failures | Bounded attempts with backoff |

A sensible layering typically follows this order:

1. Rate limiter/admission gate rejects callers exceeding thresholds.
2. Bulkhead caps concurrent work per dependency.
3. Bounded queue absorbs only brief bursts when justified.
4. Timeout keeps requests within deadlines.
5. Circuit breaker stops calling unhealthy dependencies.
6. Retries apply only to transient failures within the deadline budget.

Do not stack every pattern mechanically. Long queues + aggressive retries + long timeouts can hold requests far too long and generate extra load while the system is degraded.

## 16. Configuring Reactor Netty Server in Spring Boot

Spring Boot WebFlux typically uses Reactor Netty, though another reactive server may be substituted. With Reactor Netty, a customizer lets you configure HTTP server-layer limits:

~~~java
@Configuration
class NettyServerConfiguration {

    @Bean
    WebServerFactoryCustomizer<NettyReactiveWebServerFactory>
    nettyCustomizer() {

        return factory -> factory.addServerCustomizers(server ->
                server
                        .maxConnections(500)
                        .readTimeout(Duration.ofSeconds(5))
                        .requestTimeout(Duration.ofSeconds(20))
                        .idleTimeout(Duration.ofSeconds(60)));
    }
}
~~~

Numbers are examples only:

- `maxConnections(500)`: caps TCP connections.
- `readTimeout(5s)`: limits silence between request body reads.
- `requestTimeout(20s)`: total time to read request content.
- `idleTimeout(60s)`: closes connections waiting too long for the next request.

These parameters do not replace an application admission gate, queue timeouts, or overall handler deadlines.

If the application uses Tomcat/Jetty reactive servers instead of Reactor Netty, use the corresponding server configuration. Do not copy a Netty customizer onto a different server.

## 17. Observability: Measure Both Queues and Rejections

A queue can grow even while CPU remains low. Looking only at CPU can mislead operators into raising concurrency and accidentally pushing overload onto databases or downstreams.

Essential metrics:

| Metric | Meaning | Warning Signal |
| --- | --- | --- |
| `in_flight_requests` | Requests currently processing | Continuously hitting cap |
| `queue_depth` | Waiting items | Climbing continuously |
| `queue_oldest_age` | Age of longest-waiting item | Exceeding deadline/SLA |
| `queue_wait_seconds` | Queue wait duration | Rising p95/p99 |
| `rejected_total` | Rejected request count | Sudden spike |
| `timeout_total{layer}` | Timeouts by layer | Pool/server/downstream timeouts rising |
| `bulkhead_available` | Remaining free permits | Frequently 0 |
| `active_connections` | TCP connections in use | Continuously near max |
| `pending_acquires` | Requests awaiting client connection | Pool queue growing |
| `scheduler_pending_tasks` | Tasks awaiting workers | Scheduler congested |
| `downstream_latency` | Dependency latency | Rising before overload spreads |
| `event_loop_pending_tasks` | Tasks awaiting event loop | Event loop falling behind |

Monitor p50/p95/p99, not just averages. Pair queue depth with oldest age; a queue of 20 items where the head has waited 15 seconds can be far worse than a 100-item queue drained in 20 ms.

Do not use user ID, raw URL, or request ID as unbounded-cardinality metric labels. Use route templates, service names, tenant tiers, and error categories.

## 18. Priority-Based Load Shedding

When load exceeds capacity, requests can be grouped:

- **Critical:** payments, order confirmations, security-sensitive operations.
- **Standard:** regular business reads/writes.
- **Best effort:** recommendations, analytics, telemetry, previews.
- **Background:** reports, batches, exports.

A load-shedding strategy can reserve capacity for critical paths, throttle best-effort traffic first, reject tenants over quota, stop enqueuing expired jobs, protect downstreams with separate bulkheads, and return appropriate status/Retry-After headers.

Do not let heavy requests like exports/reports share one unbounded queue and concurrency pool with light requests like health/profile checks. Use route-specific semaphores, dedicated worker pools, or asynchronous job APIs.

## 19. Runnable Java 17+ Program: Fail-Fast Admission

Standalone example using Reactor Core proving an admission gate limits concurrent tasks to two. Five requests are subscribed simultaneously; two receive permits and the remaining three are rejected immediately. The program never uses `Thread.sleep()` or blocks in the pipeline.

### 19.1. Project Structure

~~~text
webflux-overload-demo/
  pom.xml
  src/main/java/example/overload/AdmissionDemo.java
~~~

Requires JDK 17+, Maven 3.6.3+, and Maven Central for initial dependency download.

### 19.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-overload-demo</artifactId>
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

### 19.3. AdmissionDemo.java

~~~java
package example.overload;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class AdmissionDemo {

    private static final Semaphore PERMITS = new Semaphore(2);

    private static final AtomicInteger ACTIVE = new AtomicInteger();
    private static final AtomicInteger MAX_ACTIVE = new AtomicInteger();
    private static final AtomicInteger ACCEPTED = new AtomicInteger();
    private static final AtomicInteger REJECTED = new AtomicInteger();

    static final class OverloadedException
            extends RuntimeException {
    }

    private static Mono<String> handle(int id) {
        return Mono.defer(() -> {
            if (!PERMITS.tryAcquire()) {
                REJECTED.incrementAndGet();
                return Mono.error(new OverloadedException());
            }

            ACCEPTED.incrementAndGet();

            int current = ACTIVE.incrementAndGet();
            MAX_ACTIVE.accumulateAndGet(current, Math::max);

            return Mono.delay(Duration.ofMillis(200))
                    .map(ignored -> "ok-" + id)
                    .doFinally(signal -> {
                        ACTIVE.decrementAndGet();
                        PERMITS.release();
                    });
        });
    }

    public static void main(String[] args) {
        List<String> results = Flux.range(1, 5)
                .flatMap(
                        id -> handle(id)
                                .onErrorResume(
                                        OverloadedException.class,
                                        error -> Mono.just(
                                                "rejected-" + id)),
                        5,
                        1)
                .sort()
                .collectList()
                .block(Duration.ofSeconds(5));

        List<String> expected = List.of(
                "ok-1",
                "ok-2",
                "rejected-3",
                "rejected-4",
                "rejected-5");

        if (!expected.equals(results)) {
            throw new AssertionError(
                    "Unexpected results: " + results);
        }

        if (ACCEPTED.get() != 2
                || REJECTED.get() != 3
                || MAX_ACTIVE.get() != 2
                || ACTIVE.get() != 0) {
            throw new AssertionError(
                    "Admission counters are inconsistent");
        }

        System.out.println("results=" + results);
        System.out.println("accepted=" + ACCEPTED.get());
        System.out.println("rejected=" + REJECTED.get());
        System.out.println("max-in-flight=" + MAX_ACTIVE.get());
    }
}
~~~

### 19.4. Running the Program

From the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.overload.AdmissionDemo
~~~

**Expected stdout:**

~~~text
results=[ok-1, ok-2, rejected-3, rejected-4, rejected-5]
accepted=2
rejected=3
max-in-flight=2
~~~

Explanation:

- `Semaphore(2)` permits only two running tasks.
- `tryAcquire()` does not wait and does not block the event loop.
- `Mono.defer` attempts to acquire a permit only when subscription starts.
- The remaining three requests receive `OverloadedException`, which the demo maps to `rejected` results.
- `doFinally` releases the permit across complete, error, and cancel.
- `flatMap(..., 5, 1)` allows five inner Publishers to subscribe; the admission gate limits the actually admitted tasks to two.
- `block(Duration)` sits solely at the main boundary for the demo to await results; never use `block` in a WebFlux handler.

This demonstrates admission control inside a reactive pipeline, not a full HTTP server. In a WebFlux controller, map `OverloadedException` to 503/429 via an exception handler instead of returning a rejected string.

## 20. Testing Overload and Timeouts

Tests should verify the following behaviors:

| Test | Expectation |
| --- | --- |
| Below concurrency limit | Requests succeed with 2xx |
| At capacity | All permits used without exceeding max |
| Over capacity | Excess requests receive 503/429 per policy |
| Queue full | Producer receives explicit overflow/rejection |
| Waiting too long in queue | Request times out before starting |
| Downstream timeout | Cancels upstream and returns classified error |
| Client disconnect | Permits/queued items cleaned up |
| Downstream recovery | Queue depth and active counts return to baseline |
| Retry storm | Does not generate unbounded extra load |
| Noisy neighbor tenant | Other tenants retain their own capacity |

Use `StepVerifier.withVirtualTime` to test timeouts/retries without waiting in real time where appropriate. Use `WebTestClient` or real HTTP load tests to verify status codes, Retry-After headers, client disconnects, and embedded server behavior.

For Reactor Netty connection caps, run integration/load tests over real TCP; unit testing a controller does not prove kernel accept backlog or connection rejection behavior.

## 21. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using unbounded queues | Heap grows until OOM | Bounded queue + overflow policy |
| Only enlarging queues under overload | Requests wait longer without adding service capacity | Shed admission or scale capacity |
| Using only flatMap concurrency to protect ingress | HTTP requests still enter the server | Admission gate/edge limit |
| Blocking the event loop waiting on a semaphore | Other requests hang | `tryAcquire()` or async queue |
| Using default onBackpressureBuffer for hot sources | Unbounded buffer | `maxSize` and overflow strategy |
| Using bounded buffers without monitoring overflow | Silent item loss or unhandled errors | Callbacks/metrics/error policy |
| Queues without timeouts | Stale items run past their deadlines | Queue wait deadlines |
| Overly long per-layer timeouts | Total request exceeds SLA | End-to-end deadlines |
| Treating server requestTimeout as handler timeout | Handlers/downstreams run too long | Separate Mono timeout/deadline |
| Treating maxConnections as max HTTP/2 requests | Multiplexed streams exceed expectations | Cap streams/admission at the right layer |
| Retrying immediately on 503 | Retry storm | Backoff, jitter, Retry-After, max attempts |
| Retrying non-idempotent writes | Duplicate writes | Idempotency keys/transactions |
| One global bulkhead for all dependencies | One slow dependency consumes all permits | Separate bulkhead per dependency |
| Failing to release semaphores on cancel | Permit leak, permanent rejection | `doFinally`/`usingWhen` |
| In-RAM queues for jobs requiring durability | Jobs lost on process restart | Durable broker/outbox |
| Watching only CPU | Misses queue waits and connection starvation | Queue/latency/pending metrics |
| Returning 200 with a "busy" body | Clients fail to detect errors and misbehave on retries | 429/503 with error contract |
| Logging payloads during overload | Increases I/O and exposes data | Structured metadata, sampling |

## 22. Production Checklist

- [ ] Inventory every queue from load balancer to database/downstream.
- [ ] Identify what each queue holds: TCP connections, requests, tasks, Publisher items, or connection acquires.
- [ ] Every queue that can grow with load has finite capacity or durable storage.
- [ ] Overflow policies match business semantics.
- [ ] Admission control guards resource-intensive work.
- [ ] Concurrency is bounded per dependency.
- [ ] Rate limits per user/tenant/API key are configured where needed.
- [ ] Never block the Netty event loop waiting for permits/queues.
- [ ] Set queue wait timeouts and discard expired items.
- [ ] Define an overall deadline and per-layer budgets.
- [ ] Distinguish pool acquire, connect, TLS, response, server read, and handler timeouts.
- [ ] Know whether cancellation propagates downstream.
- [ ] Enforce idempotency for retried side effects.
- [ ] Return 429 for caller quotas; 503 for service overload; 504 for upstream gateway timeouts.
- [ ] Use controlled Retry-After/backoff/jitter.
- [ ] Never retry overload errors instantaneously.
- [ ] Monitor queue depth, oldest age, wait time, rejected count, and in-flight requests.
- [ ] Monitor pending connections, event-loop tasks, heap/direct memory, and downstream latency.
- [ ] Load test steady-state, bursts, slow consumers, downstream outages, and recovery.
- [ ] Maintain runbooks for overload and scale-out/scale-in.

## 23. Self-Check Questions

**Question 1.** What problem does a bounded queue solve?

It caps waiting work and absorbs short bursts; it does not increase consumer throughput.

**Question 2.** What happens if arrival rate exceeds processing rate for a long time?

The queue fills to capacity; afterward requests must be rejected/dropped or written to durable storage per policy.

**Question 3.** How does backpressure differ from admission control?

Backpressure regulates demand between Publisher and Subscriber; admission control decides whether to accept a new request/operation at all.

**Question 4.** Does `flatMap(concurrency)` replace an HTTP ingress rate limit?

No. It caps inner subscriptions inside a pipeline, not requests accepted at ingress directly.

**Question 5.** Why avoid unbounded queues?

They can retain unbounded payloads/objects, driving memory and latency up to OOM.

**Question 6.** Does `onBackpressureBuffer(maxSize)` always propagate demand upstream?

No. This API requests unbounded demand from upstream and holds a finite backlog; when full, it applies the overflow strategy.

**Question 7.** What advantage does Semaphore `tryAcquire()` have in WebFlux?

It checks permits immediately without blocking the event loop; when permits are exhausted, it can fail fast.

**Question 8.** Why must permit release handle cancellation?

Client disconnects or timeouts can cancel the Publisher; failing to release leaks permits.

**Question 9.** How does pool acquire timeout differ from response timeout?

Acquire timeout limits waiting for a connection in the pool; response timeout applies to waiting/reading the response per HTTP client semantics.

**Question 10.** What does Reactor Netty server `requestTimeout` limit?

Total time spent reading request content, not total controller processing time.

**Question 11.** Does HttpServer `maxConnections` cap HTTP/2 streams?

No. It caps TCP connections; multiple HTTP/2 streams can multiplex over one connection.

**Question 12.** When should 429 be returned?

When a caller/tenant/API key exceeds its rate quota.

**Question 13.** When should 503 be returned?

When the service is temporarily unable to process requests due to overload or maintenance.

**Question 14.** When should 504 be returned?

When a gateway/proxy fails to receive a timely response from a required upstream.

**Question 15.** Why can retries worsen overload?

Retries increase the request rate right when the service lacks capacity; use backoff, jitter, attempt limits, and idempotency.

**Question 16.** Why must queues enforce deadlines?

Requests waiting too long may lose value before processing starts; executing work past its deadline only wastes resources.

## 24. Official References

- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): Reactive Streams demand, unbounded requests, backpressure, and reshaping requests.
- [Project Reactor — Flux JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): onBackpressureBuffer, bounded buffers, overflow strategies, drop/latest, and discard behavior.
- [Project Reactor — Sinks Reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): unicast sinks, custom bounded queues, emission results, and backpressure.
- [Reactor Netty — HTTP Server](https://projectreactor.io/docs/netty/release/reference/http-server.html): maxConnections, server readTimeout, requestTimeout, idleTimeout, and server metrics.
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection pool pending queue, pendingAcquireMaxCount, pendingAcquireTimeout, response/connect timeouts, and pool metrics.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): reactive server configuration and NettyReactiveWebServerFactory customizers.
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html): WebServerFactoryCustomizer and server-specific settings.
- [Resilience4j — Bulkhead](https://resilience4j.readme.io/docs/bulkhead): semaphore bulkhead, fixed thread pool bulkhead, and bounded queues.
- [Resilience4j — RateLimiter](https://resilience4j.readme.io/docs/ratelimiter): periodic request quotas and handling exceeded limits.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): 503, 504, and Retry-After.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585.html): 429 Too Many Requests.

**Key Takeaway:** Bounded queues only absorb bursts; admission control caps accepted work; timeouts keep every request within deadline; overload must be rejected explicitly. Measure queue depth/age, concurrency, pending connections, and p95/p99 to locate bottlenecks. Use 429 for caller quotas, 503 for temporary service overload, and 504 for gateways waiting on upstreams; pair with Retry-After, backoff, and idempotency to prevent retry storms.