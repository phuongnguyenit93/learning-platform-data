# Evaluating WebFlux Across the Entire I/O Chain; Not Faster Than MVC by Default

## 1. Lesson Objectives

**Spring WebFlux** is Spring Framework's reactive web stack, supporting **non-blocking I/O**, `Mono`/`Flux`, Reactive Streams, and backpressure. However, switching from Spring MVC to WebFlux **does not automatically make an API respond faster**. The biggest potential benefit is usually using fewer threads and less memory when serving **many concurrent requests with I/O wait times**, provided that the critical I/O stages in the system also **do not block the event loop**.

The core point: you must evaluate the **entire processing chain from HTTP ingress to HTTP egress**, not just look at a controller returning `Mono<T>`.

After this lesson, you will be able to:

1. Distinguish **latency**, **throughput**, **concurrency**, **resource efficiency**, **p95/p99**, saturation, backpressure, and CPU computation speed.
2. Understand the Servlet MVC model (often thread-per-active-request with blocking I/O) and WebFlux (event loop + reactive signals), without oversimplifying that MVC “does not support async”.
3. Diagram and audit an end-to-end request: **client → gateway → WebFlux handler → HTTP client → database → cache → messaging → serializer → HTTP response**.
4. Identify JDBC/JPA, `RestTemplate`, `Thread.sleep`, `Files.readAllBytes`, `block()`, synchronization, and blocking client libraries that undermine WebFlux.
5. Explain how to use **`WebClient`**, **R2DBC**, `Schedulers.boundedElastic()`, Reactor Context, `timeout`, `flatMap(..., concurrency)`, pool/queue bounds, and proper cancellation.
6. Run a **Java 17+, Spring Boot 3.x, Spring WebFlux + R2DBC/H2** example without JDBC, featuring an HTTP endpoint returning `Mono` from a reactive database and tested with `WebTestClient`.
7. Design a fair MVC-vs-WebFlux experiment measuring concurrency/latency/CPU/memory/threads/GC/errors per workload and reading results without bias.
8. Decide whether to **keep MVC**, **adopt WebClient in MVC**, or **migrate to WebFlux** based on evidence and operational readiness.

**Scope:** Spring Framework **6.x**, Spring Boot **3.x**, Project Reactor on Java 17+. If using Spring Framework 7/Spring Boot 4 or different driver generations, check the corresponding APIs/versions. This lesson focuses on web servers/reactive data I/O; do not treat it as a benchmark already executed on your machine.

## 2. Technical Conclusion to Remember First

> **Reactive/non-blocking does not automatically make code run faster.** It enables an application to manage more I/O-waiting operations with fewer threads, given the right workload and architecture.

Spring Framework documentation states clearly: WebFlux generally **does not** speed up a single isolated request; sometimes it adds reactive programming and scheduling overhead. WebFlux can pay off when concurrent request counts are high, remote/database I/O has variable latency, and all critical layers use compatible APIs.

A REST endpoint returning static in-memory data and finishing in 1 ms will likely see no meaningful gain from switching to WebFlux; in exchange, you add a learning curve and harder debugging. Conversely, an endpoint waiting on multiple upstream services for 100–500 ms with thousands of concurrent connections can be a good candidate for measuring non-blocking benefits.

**There is no absolute ranking:** never conclude “MVC is always faster” or “WebFlux is always faster” from a single benchmark chart. Hardware, Java version, GC, server connector, database, SSL/TLS, compression, payload size, concurrency, error budgets, and test tooling can flip the results.

## 3. Understanding Performance Metrics Accurately

| Concept | Meaning | Common Misconception |
| --- | --- | --- |
| Latency | Time from client send to complete response or defined milestone | Not synonymous with requests per second |
| p50 | Median latency | Can hide a slow tail |
| p95 / p99 | 95% / 99% of samples fall at or below this level | Needs enough samples and must include timeouts |
| Throughput | Requests/transactions completed per second (RPS/TPS) | Do not equate “requests sent” with success |
| Concurrency | Number of in-flight operations/requests | Not synonymous with thread count |
| CPU utilization | CPU usage percentage | High usage can mean saturation, not efficiency |
| Memory / RSS | Heap, native memory, direct buffers, process resident set | WebFlux still has buffer/Netty/native overhead |
| Thread count | Number of JVM/worker/event-loop threads | Fewer threads do not guarantee lower latency |
| Saturation | CPU, DB pool, network, queue, or downstream hit limits | Never solved by increasing concurrency infinitely |
| Error / timeout rate | Share of requests failing or exceeding deadlines | Excluding errors skews benchmarks |
| Backpressure | Mechanism regulating data rate by consumer demand | Does not automatically throttle every external source |

When saying “faster”, specify the **optimization goal**:
- Reduce p99 from request start to **last byte** under 200 concurrent clients?
- Increase **successful RPS** on the same vCPU/RAM while keeping p99 within SLA?
- Reduce threads/RSS while sustaining 5,000 concurrent sockets?
- Lower CPU cost per request at the same load?
- Reduce operational cost for a given real traffic volume?

A system with pretty p50 yet terrible p99, frequent timeouts, or ballooning memory has **not** won.

### 3.1. Little's Law Is Intuition, Not Magic

In a relatively steady state, requests in the system roughly equal throughput × time spent in the system:

~~~text
L ≈ λ × W

L: in-flight requests (average)
λ: request completion rate (requests/second)
W: response time (seconds)
~~~

When backends have long I/O latency, concurrent requests climb even if each request uses little CPU. WebFlux can avoid holding a blocking thread across that entire wait — **if** the I/O is genuinely non-blocking. Yet database connections, socket pools, memory, and remote service rate limits remain finite resources.

## 4. Execution Models: Spring MVC and WebFlux

### 4.1. Spring MVC / Servlet

Typical MVC flow:

~~~text
Client -> Tomcat/Jetty Servlet connector
       -> Servlet filter / DispatcherServlet
       -> Controller -> Service
       -> JDBC/JPA/HTTP blocking call
       -> Result -> HTTP response
~~~

With synchronous handlers, the request thread typically **waits** during blocking JDBC/HTTP calls. Servlet containers therefore configure a thread pool large enough for active requests.

However, **MVC does not mean all I/O is blocking in every scenario**:
- Modern Servlet APIs support async request processing.
- MVC supports `Callable`, `DeferredResult`, `StreamingResponseBody`, and reactive return types via integration.
- An MVC service can use `WebClient` to make non-blocking upstream calls and return reactive types.
- MVC can be simpler and operate very effectively when the system relies on JDBC/JPA or imperative business logic.

Never compare an MVC controller calling `Thread.sleep(500)` against WebFlux `Mono.delay(Duration.ofMillis(500))` under load and conclude WebFlux is faster: the two have **different I/O semantics**—one truly blocks a thread while the other sets a non-blocking timer without modeling the same downstream resource.

### 4.2. Spring WebFlux / Reactor Netty

Typical WebFlux flow on Netty:

~~~text
Client -> Reactor Netty event loop (non-blocking HTTP)
       -> DispatcherHandler / WebFlux controller
       -> Publisher (Mono/Flux)
       -> WebClient / R2DBC reactive driver
       -> onNext / onError / onComplete signals
       -> reactive HTTP response
~~~

Event-loop threads handle many connections and callbacks and **must not be blocked** by long-running work. A small fixed number of event-loop workers can serve many I/O-bound connections because each operation yields the thread while awaiting I/O.

WebFlux can also run on Servlet containers supporting non-blocking I/O. “WebFlux” is a **framework programming model**, not strictly synonymous with “Netty” in every deployment.

**Core warning:** if you call a blocking database client on the event loop, the whole low-thread-count advantage turns into a liability: a handful of event-loop workers get tied up, stalling **many other connections**.

## 5. Auditing the Entire End-to-End I/O Chain

This is the centerpiece of the lesson.

~~~text
Browser / Mobile / API client
         |
         v
CDN / WAF / load balancer / reverse proxy
         |
         v
TLS / Netty receive / WebFlux handler
         |
         +----> Auth / token check / remote identity provider
         |
         +----> Cache (in-process / Redis)
         |
         +----> Database (JDBC/JPA  vs  R2DBC)
         |
         +----> HTTP upstream (RestTemplate/block  vs  WebClient)
         |
         +----> Filesystem / object storage
         |
         +----> Message broker / async callback
         |
         +----> Serialization / compression / crypto / CPU
         |
         v
Netty send / reverse proxy / client reads response
~~~

For **each step**, label whether it is: genuinely non-blocking, blocking isolated on a bounded worker, CPU-bound, or externally dependent. A reactive endpoint can **harbor multiple hidden blocking points**.

### 5.1. Library Audit Matrix

| Layer | Examples Fitting Reactive I/O | Blocking Warnings / Limits |
| --- | --- | --- |
| HTTP server | Spring WebFlux with Reactor Netty | Controller calling blocking operations on the event loop |
| HTTP client | Spring `WebClient` with non-blocking connector | `RestTemplate`, `HttpURLConnection`, `WebClient(...).block()` |
| RDBMS | Database-matched R2DBC driver | Traditional JDBC, JPA/Hibernate ORM |
| Redis | Reactive Redis client/API with reactive driver | Sync Redis API/blocking wrapper |
| Filesystem | Async NIO APIs where stack truly supports them | `Files.readAllBytes`, `Files.newInputStream` sync reads |
| Object storage | Async SDK/client, end-to-end streaming | Sync SDK client, blocking `getObject` |
| Messaging | Non-blocking/reactive receiver when available | Blocking consumer callbacks or unbounded bridges |
| JSON serialization | Jackson codec in WebFlux | Heavy JSON serialization still burns CPU and can stall the loop |
| Security | Reactive security chain | Blocking remote auth introspection, CPU-heavy BCrypt/crypto |
| Template/rendering | Compatible reactive pipeline | Blocking template lookups/dynamic rendering; CPU cost |
| Tracing/logging | Proper Reactor Context/Micrometer | Blocking appenders, sync network log sinks |
| Legacy integration | Bounded scheduler wrapper when unavoidable | Unbounded threads/queues or missing timeouts |
| Reverse proxy | Configured async/non-blocking proxy | Connection limits, buffering, idle timeouts still apply |

**If the primary database is JPA/JDBC**, WebFlux does not magically make DB access non-blocking. Wrapping `Mono.fromCallable(() -> jpaRepo.findById(...))` on a bounded worker keeps it off the event loop, yet still **consumes blocking threads and DB connections**. That is a migration bridge, not full reactive benefit.

### 5.2. “Returning Mono” Does Not Prove Non-Blocking

Anti-pattern:

~~~java
@GetMapping("/unsafe/{id}")
public Mono<BookDto> unsafe(@PathVariable long id) {
    BookEntity entity = jdbcRepository.findById(id);
    return Mono.just(mapToDto(entity));
}
~~~

This is an **illustrative anti-pattern**, not standalone compilable since `jdbcRepository`, `BookEntity`, `BookDto`, and `mapToDto` are undefined. The JDBC call ran synchronously **before the Mono was returned**, very likely on the event-loop thread. Despite returning `Mono<BookDto>`, this code is not an end-to-end non-blocking pipeline.

Similarly:

~~~java
@GetMapping("/also-unsafe")
public String alsoUnsafe() {
    return webClient.get().uri("/upstream")
            .retrieve()
            .bodyToMono(String.class)
            .block();
}
~~~

This is an anti-pattern. `WebClient` itself is non-blocking, yet `block()` forces the caller to wait; on an event loop, Reactor can detect this and throw `IllegalStateException` because `block()` is disallowed on non-blocking threads. Never use `block()` on a WebFlux request path just to convert reactive code back to imperative style for convenience.

## 6. Reactor Mono, Flux, and Reactive Streams Backpressure

- **`Mono<T>`** emits at most 0 or 1 element, then completes or errors.
- **`Flux<T>`** emits 0 to many elements; may be finite or infinite.
- A **Publisher** is subscribed to and emits `onSubscribe`, `onNext`, `onError`, and `onComplete`. Backpressure works via **demand (`request(n)`)**.
- **Lazy execution**: many reactive operations execute only when subscribed. Spring WebFlux subscribes to the Publisher returned by the controller.
- **Never call `subscribe()` arbitrarily inside a handler** just to trigger work and return `Mono.empty()`; you lose lifecycle control, error propagation, cancellation, tracing, and backpressure.

Non-blocking pipeline example:

~~~java
@GetMapping("/hello")
public Mono<String> hello() {
    return Mono.just("hello")
            .map(String::toUpperCase);
}
~~~

Illustrative code inside a `@RestController`. The result is `HELLO`, yet this is trivial in-memory/CPU work; **with no I/O waiting**, it does not prove WebFlux scales better than MVC.

### 6.1. Backpressure Is Not a System-Wide Quota

Backpressure expresses element consumption demand for a single reactive stream. It **does not** automatically cap:
- New HTTP requests flooding the server;
- Open TCP connections;
- Total concurrent queries;
- Redis/object storage clients lacking backpressure support;
- Remote services receiving requests before clients slow down;
- Memory of `collectList()` on a huge Flux;
- Retries/timeouts amplifying load.

If a producer cannot slow down, you still need **buffer/drop/error** policies and capacity limits. **Network boundaries, JDBC adapters, and distributed messaging** may not honor demand like a pure in-memory Flux.

### 6.2. Operators That Can Cause Resource Explosions

~~~java
Flux.range(1, 100_000)
    .flatMap(id -> remoteCall(id));
~~~

Illustrative snippet assuming `remoteCall` is in scope; not standalone runnable. `flatMap` has concurrency and prefetch semantics depending on the overload/Reactor version, and **must not be assumed unlimited or automatically safe**. If downstream can be overwhelmed, set explicit limits:

~~~java
Flux.range(1, 1_000)
    .flatMap(id -> remoteCall(id), 8);
~~~

At most roughly 8 inner publishers are active concurrently at this operator, yet remote APIs still need connection-pool bounds, timeouts, and rate limits. `flatMap` results **may not preserve order**; if ordering matters, evaluate `concatMap` or `flatMapSequential` and assess latency.

Another anti-pattern:

~~~java
Mono<List<Item>> all = hugeFlux.collectList();
~~~

If `hugeFlux` is massive or unending, `collectList()` can exhaust heap or never complete. For downloads/streaming, pick suitable media types and streaming response semantics instead of materializing the whole stream.

## 7. Blocking I/O in Reactive Pipelines: Handling Boundaries Properly

When a synchronous/blocking library cannot yet be replaced (JDBC, legacy SDK, filesystem APIs), Reactor docs recommend:

~~~java
public Mono<LegacyResult> legacy(long id) {
    return Mono.fromCallable(() -> blockingLegacyClient.fetch(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

This is an illustrative method needing real `LegacyResult` and `blockingLegacyClient`. Key points:

1. `Mono.fromCallable` **defers** invoking the blocking API until subscription.
2. `subscribeOn(Schedulers.boundedElastic())` moves source execution to a worker scheduler suited for blocking operations.
3. The event loop is not blocked because work is offloaded.
4. **The work is still blocking** on another thread; DB connections, heap, queues, and scheduler capacity do not vanish.
5. `boundedElastic` has bounds (threads/queued tasks), yet defaults may not match your workload/SLO thresholds. Concurrency/downstream limits and overload testing remain necessary.
6. Place `subscribeOn` right after the blocking source per Reactor doc conventions so readers do not misread scheduler scope.

### 7.1. `publishOn` vs. `subscribeOn`

- `subscribeOn(scheduler)` affects upstream subscription/source execution per Reactor semantics, fitting for wrapping a blocking **source**.
- `publishOn(scheduler)` switches threads used for downstream signals/operators from that operator onward.

Example:

~~~java
Mono.fromCallable(() -> blockingRead())
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::transform);
~~~

Illustrative snippet with undefined `blockingRead` and `transform`. The source is offloaded from the start; `map` can run on that worker. To move a CPU-heavy transform to another pool, evaluate CPU scheduling and avoid unnecessary thread-switch overhead.

**Never place** `publishOn` **after** a `map` calling a blocking API and think you fixed it:

~~~java
Mono.just(id)
    .map(x -> blockingLegacyClient.fetch(x))
    .publishOn(Schedulers.boundedElastic());
~~~

This is a **counterexample**: the blocking `map` occurs **before** `publishOn`, so it can still block the original thread. Prefer `fromCallable(...).subscribeOn(boundedElastic())` or place `publishOn` before the blocking step if you fully understand the pipeline.

### 7.2. Never Use `Thread.sleep` to Simulate I/O Latency

~~~java
return Mono.just("done")
        .map(v -> {
            Thread.sleep(200);  // anti-pattern illustration
            return v;
        });
~~~

This snippet also needs `InterruptedException` handling to compile. It illustrates one point: **putting sleep inside `map`** is blocking, not a reactive wait. To create an asynchronous timer **for demos/tests**, use:

~~~java
return Mono.delay(Duration.ofMillis(200))
        .map(tick -> "done");
~~~

Still, `Mono.delay` **does not simulate database lock contention, connection pools, network bandwidth, or payload serialization**. Never cite synthetic timer benchmarks as proof of production throughput.

## 8. WebClient: Non-Blocking HTTP I/O Still Has Limits

`WebClient` is a non-blocking reactive HTTP client usable in WebFlux **or Spring MVC**. When calling remote services, use:

~~~java
@Service
public class InventoryGateway {
    private final WebClient client;

    public InventoryGateway(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://inventory.example.com")
                .build();
    }

    public Mono<Stock> getStock(long id) {
        return client.get()
                .uri("/stock/{id}", id)
                .retrieve()
                .bodyToMono(Stock.class)
                .timeout(Duration.ofSeconds(2));
    }

    public record Stock(long productId, int available) {}
}
~~~

This is an **illustrative class integrating a hypothetical upstream**; requires `@Service`, `WebClient`, `Mono`, `Duration` imports and a real upstream returning JSON matching `Stock`. `https://inventory.example.com` here is **only an example domain**, not a live service called by the section 11 demo. `WebClient.Builder` is auto-configured by Boot when WebFlux infrastructure is present.

Points to remember:

- `bodyToMono` does not call `block()`; **return the Mono** or compose it in the pipeline.
- `timeout(Duration)` sets a Publisher deadline; also configure connect/response/read timeouts on the HTTP client connector where needed.
- Bound connection pools, pending acquires, DNS, TLS handshakes, remote rate limits, max in-memory buffer sizes, and error status handling.
- `retrieve()` treats 4xx/5xx responses as error signals by default; design `onStatus`, retries, and fallbacks deliberately.
- `retryWhen` can amplify load on an already struggling service; retries need backoff, jitter, caps, and appropriate idempotency.
- When calling independent upstreams, `Mono.zip(a, b)` allows overlapping I/O waits (when sources are non-blocking), yet never claim every case is faster or total request time always equals `max(latencies)`.
- At 10,000 concurrent requests, WebClient still needs sufficient connections/FDs and upstream capacity. Non-blocking does not mean “infinite connections”.

### 8.1. A Truly Reactive Chain vs. a Pseudo-Reactive Chain

~~~text
A: WebFlux -> Mono -> WebClient(non-blocking) -> R2DBC(non-blocking)
   -> response codecs -> Netty
   => Grounded expectation of saving blocked threads when I/O latency is high.

B: WebFlux -> Mono.just(jpaRepository.findById(...))
   -> blocking JDBC on the event loop -> Netty
   => Reactive return type, yet core I/O remains blocking.

C: WebFlux -> Mono.fromCallable(JPA).subscribeOn(boundedElastic)
   -> blocking JDBC on a worker -> Netty
   => Event loop protected; still needs threads/queues/JDBC pool.
~~~

Benefits must be measured across **the entire path A**, not assumed simply from `Mono` in a signature.

## 9. Database: R2DBC vs. JDBC/JPA

Traditional JDBC uses blocking APIs. JPA/Hibernate ORM typically relies on JDBC and thread-bound transaction contexts. R2DBC provides reactive APIs for relational database drivers, though **the actual driver and database** must support and remain stable under your workload.

| Aspect | MVC + JDBC/JPA | WebFlux + R2DBC |
| --- | --- | --- |
| Coding style | Imperative, familiar services/transactions | Publishers, composition, reactive transactions |
| DB I/O | Blocks calling thread | Reactive API/driver when properly implemented |
| ORM/ecosystem | Mature JPA/Hibernate with broad integrations | R2DBC support varies by dialect/driver; not equivalent to all JPA features |
| Lazy loading | JPA proxies/lazy entities tied to session | Does not use ORM JPA lazy-loading the same way |
| Transactions | `PlatformTransactionManager`, thread-bound | `ReactiveTransactionManager`, Reactor Context |
| Backpressure | Not Reactive Streams | Reactive API, yet DB protocol/pool limits still apply |
| Pool | JDBC pool (e.g., HikariCP) | R2DBC connection pool when needed |
| Failure modes | Thread/connection exhaustion | Connection pool/queue/event-loop/retry pressure |
| Migration cost | Keep existing code | Rewrite repositories, transactions, mappings, tests |

**R2DBC is not automatically faster than JDBC.** It changes the execution model; the advantage is avoiding holding threads while awaiting DB I/O at high concurrency. A poorly optimized SQL query or saturated DB stays slow regardless of reactive clients. Joins, indexes, row scans, locks, network, and connection counts usually remain the decisive factors.

### Reactive Transactions Do Not Follow ThreadLocal

With R2DBC, `@Transactional` can use `ReactiveTransactionManager` with reactive return types. Transaction state binds to the subscriber/Reactor Context, unlike thread-bound JDBC. Avoid having an imperative `@Transactional` method call async code expecting the transaction to span the whole subscription.

Do not call `subscribe()` inside a service and leave the transaction scope. Return the Publisher so Spring manages lifecycle/transactions. Verify which reactive transaction manager is configured if a project has both JDBC/JPA and R2DBC.

## 10. What Must a Fair Benchmark Control?

When benchmarking MVC vs. WebFlux, **both versions must solve the same problem** under identical contracts and conditions:

1. **Identical endpoint semantics:** status codes, JSON schemas, record counts, validation, authentication, error handling, serialization.
2. **Identical data:** database size/indexes/query plans, cache hit/miss ratios, network latency, SQL result set sizes.
3. **Identical downstream:** same DB cluster, upstream HTTP services, rate limits, and connection pools tuned appropriately per stack.
4. **Identical infrastructure:** vCPUs, RAM, JVM version, GC, heap, containers, network, TLS, proxies, and bandwidth.
5. **Equivalent warm-up:** JIT, driver pools, DB caches, and connection establishment.
6. **Independent load generator:** load generator must not saturate CPU/network; preserve proper connection reuse/keep-alive and payload profiles.
7. **Error rates:** never omit 429/503/timeouts or client aborts from metrics.
8. **Same arrival pattern:** test both fixed closed-loop concurrency and open-loop arrival rates to reduce coordinated omission.
9. **Same time budget:** run multiple independent trials, use confidence intervals/distributions.
10. **Observe every layer:** HTTP server, event loops/worker threads, DB pools, GC, remote services, OS sockets/FDs, and gateways.

Never run a single `curl` command and declare one stack “faster”. A 5 ms dev response says nothing about p99 under 500 concurrent clients.

### 10.1. Scenarios to Include

| Scenario | Verification Goal | Does WebFlux Help? |
| --- | --- | --- |
| K1: Tiny JSON echo | Baseline framework/codec CPU overhead | Do not assume so |
| K2: CPU-bound mapping/crypto | CPU compute, context switching | Reactive does not create extra CPU |
| K3: JDBC/JPA blocking query | Impact of blocking DB/client library | Usually no full-reactive advantage |
| K4: R2DBC + high-latency DB | Concurrent I/O and thread/memory footprint | Possibly; must measure |
| K5: Two independent WebClient upstreams | Composed concurrent waits | Possibly; MVC + WebClient is also a candidate |
| K6: Large streaming | Buffering, backpressure, slow clients | Depends on end-to-end support |
| K7: 500 concurrent clients | Saturation, queues, pools, p99 | Possibly; requires sufficient DB/service capacity |
| K8: Failing/slow upstream | Timeouts, retries, circuit breakers | Reactive does not prevent cascading failures alone |
| K9: 90% cache hits | CPU/cache path efficiency | May show little difference |
| K10: Real TLS+compression+auth | Real-world production overheads | Never extrapolate from toy demos |

### 10.2. Required Metric Set

**Client/HTTP:** successful RPS, p50/p95/p99 latency, max latency, total errors, 4xx/5xx breakdown, timeouts, pending/in-flight requests, bytes transferred.

**JVM:** CPU utilization, heap used, GC pauses/allocation rate, native/direct memory, JVM thread count, event-loop busy time.

**Pools/queues:** Netty connection provider active/pending, R2DBC/JDBC pool active/idle/acquire wait, scheduler queues, executor threads, and rejections.

**Downstream:** DB query latency/pools/locks, upstream HTTP latency/errors/rate limits, Redis/streaming throughput, filesystem/object storage times.

**Business:** data accuracy, record counts, result ordering, duplicate retries, p99 on critical endpoints. Failing fast under overload is sometimes **better** than endless queues, yet error budgets must be measured.

Never report a single RPS figure alone; all metrics must be evaluated **together**.

## 11. Runnable Example: WebFlux → R2DBC/H2 → HTTP Response

To illustrate an **HTTP → database** chain without JDBC, the sample app uses:
- Spring Boot 3.x, Java 17+, **only `spring-boot-starter-webflux`** for the HTTP server.
- **`spring-boot-starter-data-r2dbc`** and **`io.r2dbc:r2dbc-h2`** for reactive H2 access.
- `DatabaseClient` reading a row from H2 as a Publisher.
- Controller returning `Mono<ResponseEntity<CatalogItem>>` and `Flux<ServerSentEvent<String>>`.
- **`spring-boot-starter-test`** and `WebTestClient` for HTTP integration tests.

This example demonstrates a **non-blocking path and correctness**, **not** a substitute for production benchmarks. In-memory H2 is unrealistically fast and does not represent real networked databases with lock contention. Never cite numbers from this demo to claim WebFlux outperforms MVC.

### 11.1. Maven Dependencies

Create a Maven project via Spring Initializr with Java 17+ and Spring Boot 3.x. Select WebFlux, Spring Data R2DBC, and Test; add the R2DBC H2 driver if not auto-selected. Dependencies in `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
        <groupId>io.r2dbc</groupId>
        <artifactId>r2dbc-h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This is a **dependencies snippet** for a `pom.xml` generated by Spring Initializr, not a full standalone Maven file. **Do not** add `spring-boot-starter-web`/Spring MVC here. In Spring Boot 3.x, if both Web MVC and WebFlux starters are on the classpath, **Spring MVC is normally selected by default** unless the reactive app type is explicitly set; using only the WebFlux starter keeps the example clear.

### 11.2. Project Structure

~~~text
src/
  main/
    java/com/example/demo/
      DemoApplication.java
      CatalogItem.java
      CatalogService.java
      CatalogController.java
    resources/
      application.properties
      schema.sql
      data.sql
  test/
    java/com/example/demo/
      CatalogHttpTest.java
~~~

### 11.3. R2DBC Database Configuration and SQL Scripts

`src/main/resources/application.properties`:

~~~properties
spring.application.name=webflux-io-chain-demo
spring.r2dbc.url=r2dbc:h2:mem:///catalogdb
spring.sql.init.mode=always
~~~

H2 is an in-memory database for the demo. `spring.sql.init.mode=always` lets Boot initialize `schema.sql` and `data.sql` over the reactive `ConnectionFactory`; this is **not** a JDBC URL. The project uses the Boot/R2DBC H2 versions managed by Boot's BOM, avoiding mismatched driver versions.

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE catalog_item (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    stock INTEGER NOT NULL
);
~~~

`src/main/resources/data.sql`:

~~~sql
INSERT INTO catalog_item (id, name, stock)
VALUES (7, 'spring', 9);

INSERT INTO catalog_item (id, name, stock)
VALUES (8, 'reactor', 12);
~~~

Because in-memory H2 is initialized inside the app, the demo has deterministic data. When running multiple application contexts concurrently against the same in-memory H2 database, avoid unintended schema reuse; tests must control data setup/teardown or database isolation. In production, use a migration tool and consistent deployment workflow rather than demo schema initialization on every startup.

### 11.4. Java Application

`src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.5. Immutable DTO

`src/main/java/com/example/demo/CatalogItem.java`:

~~~java
package com.example.demo;

public record CatalogItem(
        Long id,
        String name,
        Integer stock
) {}
~~~

`CatalogItem` is an immutable Java record with no shared mutable state. Making a record immutable **does not** by itself prove the entire pipeline is thread-safe, yet eliminates one class of shared-object risks.

### 11.6. Service Using Reactive `DatabaseClient`

`src/main/java/com/example/demo/CatalogService.java`:

~~~java
package com.example.demo;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CatalogService {

    private final DatabaseClient db;

    public CatalogService(DatabaseClient db) {
        this.db = db;
    }

    public Mono<CatalogItem> findById(long id) {
        return db.sql("""
                SELECT id, name, stock
                FROM catalog_item
                WHERE id = :id
                """)
                .bind("id", id)
                .map((row, metadata) ->
                        new CatalogItem(
                                row.get(0, Long.class),
                                row.get(1, String.class),
                                row.get(2, Integer.class)))
                .one();
    }
}
~~~

**Explanation:**

1. `DatabaseClient` is auto-configured by Spring Boot with the R2DBC `ConnectionFactory`.
2. `:id` is a **bind marker**, not raw SQL string concatenation. It prevents SQL injection when bound properly.
3. `.one()` returns `Mono<CatalogItem>`, completing empty if no row matches.
4. `row.get(0, Long.class)` maps positionally to SELECT columns. With this H2 schema, `BIGINT` and `INTEGER` map to `Long`/`Integer`.
5. No `.block()`, `.subscribe()`, or JDBC client is called inside the service.
6. The actual query pipeline executes only when WebFlux subscribes to the Publisher; DB drivers and pools still require monitoring.
7. The SQL table and scripts must exist on startup. Changing SELECT column order requires updating positional mapping; production services can map by column name or explicit row mappers.

### 11.7. Reactive HTTP Controller

`src/main/java/com/example/demo/CatalogController.java`:

~~~java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<CatalogItem>> one(
            @PathVariable("id") long id) {

        return catalogService.findById(id)
                .map(item -> ResponseEntity.ok(item))
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(
            path = "/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ticks() {
        return Flux.interval(Duration.ofMillis(200))
                .take(3)
                .map(number -> ServerSentEvent
                        .builder("tick-" + number)
                        .build());
    }
}
~~~

With the initial H2 records:
- `GET /api/catalog/7` returns **200** JSON `{"id":7,"name":"spring","stock":9}`.
- `GET /api/catalog/999` returns **404**, because `Mono.empty()` is mapped via `defaultIfEmpty`.
- `GET /api/catalog/ticks` is an **SSE** demo emitting `tick-0`, `tick-1`, `tick-2` and completing; it uses a non-blocking timer and does **not** replace measuring streaming with slow clients.

Never use `Thread.sleep` to build intervals. `Flux.interval` emits via an appropriate scheduler; subscribers/timers still consume resources, so production SSE needs heartbeats, connection limits, and cleanup.

### 11.8. Real HTTP Testing with WebTestClient

`src/test/java/com/example/demo/CatalogHttpTest.java`:

~~~java
package com.example.demo;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CatalogHttpTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void readsOneRowThroughReactiveDatabase() {
        client.get()
                .uri("/api/catalog/7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7)
                .jsonPath("$.name").isEqualTo("spring")
                .jsonPath("$.stock").isEqualTo(9);
    }

    @Test
    void notFoundWhenDatabasePublisherIsEmpty() {
        client.get()
                .uri("/api/catalog/999")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody().isEmpty();
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

or on Windows:

~~~powershell
.\mvnw.cmd test
~~~

If the project lacks a Maven Wrapper, run `mvn test` with Maven installed. The test starts an **embedded HTTP server on a random port**, executes an **HTTP network request**, queries **R2DBC H2**, and asserts JSON/status. That is a much more meaningful integration test than merely testing a mocked `Mono.just`.

However, this test **does not measure performance**: it does not exercise meaningful high concurrency, TLS, reverse proxies, packet loss, remote database latency, or real network contention. Never present two passing tests as proof that “WebFlux is faster”.

### 11.9. Testing with curl

Start the app:

~~~bash
./mvnw spring-boot:run
~~~

Call the API:

~~~bash
curl -i http://localhost:8080/api/catalog/7
~~~

Expected result: status **200 OK**, `Content-Type: application/json`, and body:

~~~json
{"id":7,"name":"spring","stock":9}
~~~

Nonexistent item:

~~~bash
curl -i http://localhost:8080/api/catalog/999
~~~

Expected status **404 Not Found**. The default WebFlux error response body can depend on configuration/negotiation; in this controller `ResponseEntity.notFound().build()` provides no business payload.

SSE timer:

~~~bash
curl -N http://localhost:8080/api/catalog/ticks
~~~

The body contains three events looking like:

~~~text
data:tick-0

data:tick-1

data:tick-2
~~~

`-N` disables curl stdout buffering; event order is 0, 1, 2, while **actual emission timing** depends on schedulers, servers, proxies, and clients rather than guaranteeing exact 200 ms intervals over the network.

## 12. Extending the I/O Chain with External WebClient

Section 11 only traverses a reactive database. If real business logic also calls an inventory service, the pipeline could look like:

~~~java
public Mono<ItemDetail> detail(long id) {
    Mono<CatalogItem> item = catalogService.findById(id);
    Mono<InventoryGateway.Stock> stock = inventoryGateway.getStock(id);

    return Mono.zip(item, stock)
            .map(pair -> new ItemDetail(
                    pair.getT1(), pair.getT2()));
}
~~~

This is an **illustrative method**, not standalone runnable: requires `catalogService`, `inventoryGateway`, and `ItemDetail`; the gateway in section 8 uses an example domain. `Mono.zip` emits only when both sources produce a value; if either completes empty, zip completes empty, so handle missing data per business semantics. If both calls are independent, subscribing overlaps their I/O. Never **call `.block()`** to gather results:

~~~java
// Anti-pattern: synchronizing two asynchronous requests
CatalogItem a = item.block();
InventoryGateway.Stock b = stock.block();
~~~

Even if upstream uses WebClient, that anti-pattern blocks the caller and can stall the event loop. Return `Mono<ItemDetail>` so the framework subscribes and propagates errors/cancellation cleanly.

### When Is MVC + WebClient Good Enough?

If a system already runs stably on MVC/JPA with only a few HTTP fan-outs, you can:
- Keep Spring MVC and blocking DB calls on properly sized Servlet/worker threads.
- Use `WebClient` for specific integration calls.
- Return reactive types from MVC handlers where appropriate, or focus on tuning connection pools and timeouts.
- Re-measure SLOs before considering rewriting an entire service to WebFlux/R2DBC.

This is a **bottleneck-driven optimization strategy**, not an inferior architectural compromise.

## 13. Bugs When Running Reactive with Hidden Blocking: How to Detect

Items to look for during code review:

~~~text
.block()
.blockOptional()
Thread.sleep(...)
Future.get()
CompletableFuture.join()
RestTemplate.exchange(...)
JdbcTemplate.query(...)
jpaRepository.find...
Files.readAllBytes(...)
InputStream.read(...) on blocking sources
ObjectMapper.writeValueAsBytes(hugeObject)
long-held synchronized / locks
unbounded Flux collectList()
flatMap(...) without clear concurrency budget
subscribe() inside controller/service
Schedulers.boundedElastic() treated as a cure-all
~~~

Not every method in this list is always wrong **in every thread/context**: for instance, `Files.readAllBytes` in startup configuration or a CLI tool can be completely valid. The problem is running it **on the event-loop request path** or inside a publisher without proper offloading/resource bounds.

### 13.1. BlockHound

**BlockHound** helps detect certain blocking calls on threads marked non-blocking during tests. It is useful for catching `Thread.sleep` or blocking APIs accidentally invoked on Reactor schedulers/event loops.

However:
- It does not prove every I/O operation across the entire system is non-blocking.
- It can have false positives/require whitelisting; use a dedicated test profile.
- Verify **JVM and Reactor/BlockHound version compatibility**; Java 17+ requires specific instrumentation/JVM arguments depending on version.
- Do not enable it blindly in production without evaluating overhead.

### 13.2. Java Flight Recorder, Traces, and Thread Dumps

Inspect:
- What are Reactor Netty event-loop threads doing? Are there stack traces in JDBC, huge JSON, file I/O, locks, or long crypto?
- Are reactive schedulers/`boundedElastic` filling up queues/threads?
- Are connection pool acquires waiting long?
- Are DB query latencies and counts/locks rising?
- Does `WebClient` have enough channels and DNS/connect/response timeouts?
- Is Reactor Context/tracing lost across thread hops?
- Is p99 held back by network/proxy/client speed or the application itself?

Find the **exact bottleneck** before deciding to change frameworks.

## 14. Reactive Context, ThreadLocal, and Transactions

Reactor provides **`Context`** bound to the subscription, carrying metadata across async execution without relying by default on a single `ThreadLocal`:

~~~java
Mono<String> observed = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")))
        .contextWrite(context -> context.put("requestId", "req-42"));
~~~

This pure Reactor snippet yields a Publisher holding `req-42` when subscribed. **Never** use `ThreadLocal` or share a mutable map across requests. Conversely, if logging/tracing libraries rely on MDC, use an appropriate bridge/context propagation mechanism rather than assuming MDC follows every operator across every thread simply because the return type is `Mono`.

For **reactive transactions**, Spring uses a transaction context tied to the reactive pipeline when `ReactiveTransactionManager` is configured, instead of assuming a JDBC `ThreadLocal` transaction follows threads across `publishOn`/`subscribeOn`. Return the Publisher to the transaction interceptor so the lifecycle is managed; never call `subscribe()` yourself assuming the ambient transaction wraps everything.

**Security:** Spring Security for WebFlux uses the reactive security model/`SecurityWebFilterChain` and reactive context handling. Never copy Servlet `SecurityFilterChain`/`HttpServletRequest` configs assuming they handle WebFlux properly. Every endpoint still needs authorization even though the reactive chain is non-blocking.

## 15. Cancellation, Timeouts, Retries, and Finite Resources

A client disconnecting can cancel the subscription; not every legacy library/downstream operation stops immediately. With R2DBC/WebClient, cancellation can release resources per driver/client semantics, though actual resource lifecycles must be verified.

Set appropriate timeouts:

~~~java
return inventoryGateway.getStock(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
                ex -> Mono.just(new StockFallback(id, 0)));
~~~

This is an illustrative business snippet, not standalone runnable since `StockFallback` and return types must match and `TimeoutException` must be imported. **Fallback `stock=0` may make no commercial sense**: only return fallback values when the domain permits; otherwise return HTTP 503/504 or a clearly defined partial result.

Never configure unbounded retries:

~~~java
return remoteMono.retry();
~~~

This is an anti-pattern for remote services: it can hammer an already-failing upstream continuously. Cap attempt counts, use backoff + jitter, retry only idempotent operations when sensible, and enforce an overall deadline. Every retry has a real capacity cost.

### 15.1. BoundedElastic Does Not Replace Admission Control

Even though the scheduler bounds threads/queues, you still need:
- limits on active requests/traces;
- `flatMap` concurrency limits;
- HTTP client connection pool limits;
- DB connection pool sizes and acquire timeouts;
- per-tenant/per-user quotas;
- circuit breakers/bulkheads and rate limiting;
- bounded buffers for streaming/event processing;
- metrics for cancellations, timeouts, OOM, and scheduler saturation.

If upstream max concurrency is 50 and you open 5,000 in-flight requests, WebFlux will not give upstream 4,950 extra slots.

### 15.2. HTTP Response Sending Resources

Slow-reading clients can hold TCP connections and buffers open for a long time. Backpressure in reactive chains helps regulate data flow at boundaries that support it, yet `collectList` and gateway buffering can still accumulate MBs/GBs. Evaluate response sizes, streaming content types, codec `maxInMemorySize`, slow-reader rates, and proxy caching/buffering.

## 16. When to Choose MVC, WebFlux, or a Hybrid?

| Current Condition | Recommended First Step | Why |
| --- | --- | --- |
| Stable MVC, JPA/JDBC core | Keep MVC, optimize DB/SQL/pools | Switching to WebFlux does not eliminate blocking drivers |
| Mostly CPU-bound endpoints, fast responses | Keep current stack, optimize algorithms/CPU | Reactive does not generate extra CPU |
| Many high-latency HTTP upstream calls | Try `WebClient` on MVC first | Gains I/O concurrency without a full rewrite |
| Green-field I/O-bound service with R2DBC + async HTTP | Benchmark WebFlux realistically | Full chain can be genuinely non-blocking |
| Streaming/SSE with huge idle connection counts | Compare WebFlux vs. MVC async | Connection/thread models differ significantly |
| Mandatory blocking legacy SDK | MVC or WebFlux with monitored bounded adapter | Do not mask blocking merely behind `Mono` |
| Team inexperienced in Reactor, hard debugging | Keep MVC if SLOs are met | Operational/learning curve is a real cost |
| Tail latency caused by DB locks | Fix DB, pools, query plans first | Web stacks cannot fix lock contention |
| Needs maximum throughput on CPU-bound work | Benchmark stack/GC/serialization empirically | Never decide from marketing |
| Partial migration to reactive | Isolate clear boundaries, run small POC | Reduces blast radius and preserves rollback |

### 16.1. A Brief Decision Tree

~~~text
Does the service already meet SLOs at acceptable cost?
   |
   +-- Yes -> No need to switch to WebFlux
   |
   +-- No:
        |
        +-- Bottleneck in DB/SQL/JDBC locks?
        |       -> Optimize data/queries first
        |
        +-- Bottleneck in waiting on many remote I/O calls?
        |       -> Try WebClient, concurrency/timeouts/pools
        |       -> Evaluate WebFlux+reactive drivers if gains are measurable
        |
        +-- CPU-bound / serialization?
        |       -> Optimize CPU/algorithms/codecs/GC
        |
        +-- Connection/streaming pressure?
                -> Benchmark WebFlux vs. MVC async end-to-end
~~~

WebFlux is **an architectural choice**, not automatically superior for every service.

## 17. Benchmarking Anti-Patterns

### 17.1. Comparing Two Different I/O Paths

It is unfair when:
- MVC uses JDBC to a real DB while WebFlux returns `Mono.just` from memory.
- MVC uses `Thread.sleep` while WebFlux uses `Mono.delay`.
- MVC tests traverse TLS/gateways while WebFlux hits local Netty directly.
- WebFlux gets a 100-connection R2DBC pool while MVC gets a 10-connection JDBC pool.
- MVC gzips JSON while WebFlux skips gzip or returns a smaller payload.

Both versions must fulfill **the exact same business contract and quality of service**.

### 17.2. Closed-Loop Benchmarks Hide Slow Tails

Clients that send a new request only after the previous finishes reduce actual offered load when the server slows down, causing **coordinated omission** in some load tools. Consider open-loop arrival scenarios or tools supporting latency correction, while ensuring the load generator itself is not the bottleneck.

### 17.3. Changing Concurrency and Drawing Latency Conclusions

As concurrency rises, throughput can climb until saturation while p99 shoots up. Never compare peak RPS while ignoring SLAs or 503s. Fix p99/error-rate thresholds first, then compare which stack achieves **lower total cost** at that SLA.

### 17.4. Measuring Only Once

JIT compilation, heap warm-up, database caches, background GC, noisy neighbors, and OS scheduling introduce variance. Run multiple independent trials, compute distributions/confidence intervals, and document environment and configuration. Never fabricate percentage differences between WebFlux and MVC without real measurements.

## 18. Common Issues and Fixes

| Symptom | Likely Cause | Remediation |
| --- | --- | --- |
| WebFlux still slower than MVC | CPU-bound workload, reactive overhead, DB/serialization bottleneck | Profile and benchmark the true workload |
| Just a few requests stall the whole server | JDBC/SDK/`Thread.sleep` on the event loop | Capture stack traces; offload or swap for reactive clients |
| `block()` throws exception in Reactor Netty | Blocking on a non-blocking thread | Return `Mono`/`Flux`; never call `block` in handlers |
| `boundedElastic` scheduler queue fills up | Legacy blocking tasks exceed capacity | Cap requests, DB calls, timeouts, admission control |
| Memory spikes on large downloads | `collectList`/`readAllBytes`, gateway buffering | Stream with bounds, backpressure, quotas |
| High p99 despite low thread count | DB/upstream saturated, blocked event loop, network, GC | Collect end-to-end traces |
| HTTP 200 yet wrong data | `combine`/`zip` empty behavior, retries, mutable state | Audit semantics, add unit/integration tests |
| SSE clients disconnect yet resources stay open | Missing cancellation/cleanup | `doFinally`, lifecycle hooks, subscriber limits |
| Request ID disappears in debug logs | `ThreadLocal` does not follow reactive operators | Use Reactor Context/Micrometer propagation |
| `@Transactional` does not span the stream | Mixed reactive and imperative transaction managers | Use `ReactiveTransactionManager` and return Publisher |
| Boot runs MVC despite adding WebFlux | Both `spring-boot-starter-web` and `webflux` present | Keep only WebFlux starter or configure explicitly |
| `WebTestClient` passes yet production fails | In-memory H2/tests miss real I/O behavior | Run integration tests against real downstream/proxies |
| Retries make upstream crash harder | Unbounded retries without backoff | Add timeouts, backoff, jitter, circuit breakers |
| DB pool runs out of connections | Too many in-flight queries | Tune pool/concurrency + optimize slow SQL |
| Great RPS yet rising timeouts | Errors excluded from stats or overload | Measure successful RPS alongside error/timeout rates |
| Blocking logger stalls loops | Missing async appender or sync network sink | Audit log sinks, limits, and queues |

## 19. Review Questions

**1. Why does `Mono<T>` not prove an endpoint is non-blocking?**

Because JDBC, file reads, `Thread.sleep`, or `block()` might have run before creating the Mono or inside the pipeline. The return type does not dictate the I/O implementation of every layer.

**2. Does WebFlux always deliver better p99 than MVC?**

No. It depends on workload, concurrency, backpressure, blocking boundaries, CPU/GC, DB pools, and many other factors. You must benchmark end-to-end.

**3. When a service uses JPA/JDBC, is switching the controller to WebFlux enough?**

No. Traditional JDBC/JPA remains blocking. You can temporarily offload onto bounded schedulers, yet it still uses threads/connections and is not a full reactive database path.

**4. Can `WebClient` run only inside WebFlux?**

No. Spring MVC can also use `WebClient`. This is often an effective incremental way to optimize I/O.

**5. Why is `Mono.delay` not an equivalent benchmark to a 200 ms JDBC query?**

Because a reactive timer neither blocks threads/DB connections nor simulates SQL locks, networking, pool waits, and downstream resource consumption of a real query.

**6. Does `flatMap(fn, 8)` prevent all overload?**

No. It bounds inner concurrency for that specific operator; you still need HTTP connection caps, DB pool sizing, request arrival limits, retry bounds, and memory limits.

**7. When should `Mono.fromCallable(...).subscribeOn(boundedElastic())` be used?**

When forced to wrap a synchronous blocking call inside a reactive app to avoid blocking the event loop; it is a transitional bridge, not true non-blocking I/O.

**8. What does the lesson's WebFlux + R2DBC/H2 test prove?**

It verifies that the HTTP response and reactive DB query work properly over an embedded server; it does **not** prove WebFlux is faster than MVC on a production database.

**9. If a benchmark shows higher RPS while p99 and errors both rise, can you declare victory?**

No, not if SLAs govern p99 and error budgets. Compare successful RPS at the same service-quality threshold.

**10. If the bottleneck is database lock contention, does switching to Netty/WebFlux fix it directly?**

No. Optimize queries, transactions, indexes, pools, and concurrency first.

## 20. Pre-Decision Architectural Checklist

1. State success criteria clearly: **successful RPS, p95/p99, error budget, CPU/RAM, cost**.
2. Diagram and annotate the entire I/O chain: ingress/proxy → handler → auth → DB/cache/upstream → serializer → response.
3. Verify whether each **driver/client** is blocking or non-blocking; inspect callbacks/schedulers, not just return types.
4. Audit for `.block()`, `Thread.sleep`, JDBC/JPA, synchronous filesystem calls, unbounded queues, and `collectList`.
5. If blocking code exists in WebFlux, wrap with bounded adapters having timeouts/concurrency budgets and monitor saturation; plan driver migration if worthwhile.
6. Adopt R2DBC/WebClient/reactive clients only when aligned with DB, drivers, team skill, operational tooling, and production readiness.
7. Benchmark MVC, MVC+WebClient/MVC async, and WebFlux under **identical end-to-end contracts**; never compare `Thread.sleep` against `Mono.delay`.
8. Measure across diverse workloads: CPU-bound, high-latency remote calls, DB contention, streaming, slow clients, and overload.
9. Track p50/p95/p99, successful RPS, timeouts/errors, CPU, heap/RSS, event loops, threads, pool waits, queues, GC, and downstream health.
10. Test security, transactions, cancellation, retries, backpressure, tracing/Reactor Context, and resource cleanup.
11. Keep connection/queue/concurrency limits enforced; never treat reactive backpressure as a system-wide quota.
12. If MVC already meets SLOs stably at reasonable cost, there is **no obligation** to migrate to WebFlux. Pick the simplest solution that satisfies measured requirements.

## Official References

- [Spring Framework 6.2 — WebFlux overview, performance, and concurrency model](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/new-framework.html)
- [Spring Framework 6.2 — WebFlux reference](https://docs.spring.io/spring-framework/reference/6.2/web/webflux.html)
- [Spring Framework 6.2 — Reactive libraries, Mono/Flux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-reactive-libraries.html)
- [Spring Framework 6.2 — WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Boot 3.5 — SQL databases, R2DBC, and DatabaseClient](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Boot — SQL script database initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Project Reactor — FAQ: wrapping a synchronous/blocking call](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking)
- [Project Reactor — Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [R2DBC specification](https://r2dbc.io/spec/1.0.0.RELEASE/spec/html/)
