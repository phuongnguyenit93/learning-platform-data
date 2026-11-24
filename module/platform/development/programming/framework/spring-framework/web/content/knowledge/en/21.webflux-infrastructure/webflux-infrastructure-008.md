# Reactive Servers, Connections, and Differences from the Servlet Model in Spring WebFlux

## 1. The problem: do many HTTP connections require just as many threads?

An API has 20,000 clients holding HTTP connections open, while each request only does brief work before waiting on a remote service or streaming events. If every execution is tied to a Java worker thread **waiting on blocking I/O**, scalability is pressured by thread count, stack memory, and context switching. A reactive server takes another approach: watching socket readiness, letting a small pool of **event-loop threads** serve many channels, and chaining asynchronous work through `Publisher`, `Mono`, and `Flux` instead of parking workers solely to wait on I/O.

However, the phrase "WebFlux serves thousands of connections with one thread" is also easy to misunderstand:

- **A connection is not a request**, especially with HTTP keep-alive and HTTP/2 multiplexing.
- **A request is not a thread**. A request can start on an event loop, hop across publishers/schedulers, and finish on another execution context.
- **Reactive does not mean automatically faster** for every workload. CPU-bound tasks still consume CPU; misplaced blocking JDBC, `Thread.sleep`, or `Future.get` can still stall the event loop.
- **WebFlux does not mandate Netty.** Spring provides adapters for Reactor Netty, Tomcat/Jetty, and Servlet containers with non-blocking I/O. Spring Boot WebFlux defaults to Reactor Netty when the default starter dependency is kept.
- **Servlet does not mean one thread lives for the lifetime of a TCP connection.** Tomcat has a non-blocking connector; Spring MVC has Servlet asynchronous processing. The main difference lies in the **application contract and request processing model**, not simply which server "has NIO" and which "lacks NIO".

This lesson explains WebFlux infrastructure from TCP sockets to responses, event loops, backpressure, and connection reuse; compares synchronous Servlet MVC, async MVC, and WebFlux; and then provides a Spring Boot 3 + Java 17 demo with WebTestClient to verify HTTP behavior without inventing thread or throughput numbers.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish **TCP connection**, **HTTP request**, **response**, **Reactor Netty Channel**, **event-loop thread**, **Servlet worker thread**, and **WebClient outbound connection pool**.
2. Trace the request pipeline from Reactor Netty to `HttpHandler`, `WebHandler`, `DispatcherHandler`, controller/functional handlers, codecs, and responses.
3. Explain why non-blocking I/O reduces thread occupancy while waiting, yet does not eliminate CPU, database, or network work.
4. Distinguish synchronous Servlet MVC, async Servlet MVC, and WebFlux running on Netty or Servlet adapters without misleading comparisons.
5. Understand `Mono<Void>` when writing responses, `Flux<DataBuffer>`, Reactive Streams demand, cancellation, streaming media types, and HTTP backpressure.
6. Manage timeouts, keep-alive, client connection pools, TLS, proxies, graceful shutdown, metrics, and avoid blocking on the event loop.
7. Run a reactive demo app on Reactor Netty and use WebTestClient to verify 200/400/204, reactive delays, SSE, filters, and error policies.

**Scope:** Spring Framework 6.x, Spring Boot 3.3.x, Reactor 3.x, Reactor Netty in a Servlet-vs-reactive context. Any performance/thread-count figures are presented as principles or illustrative examples, **never** claimed as actual benchmarks of an unmeasured system.

## 2. Precise definitions: connection, request, thread, channel

### 2.1. TCP connection

A TCP connection is a byte transport channel between two endpoints (IP/port and corresponding TCP state), often outliving a single HTTP/1.1 request when using **keep-alive**. One connection can carry multiple sequential HTTP requests via keep-alive; on HTTP/2, multiple logical streams can **concurrently** share one TCP/TLS connection.

A connection still requires file descriptors/socket buffers, flow-control state, TLS state for HTTPS, and HTTP server data structures. Therefore, never believe "because the event loop is lightweight, connections cost nothing".

### 2.2. HTTP request and response

A request is one logical HTTP exchange, e.g., `GET /api/ping`. Responses can be `200` with a body, `204` with no body, or a long-lived event stream. One connection can carry many requests, and one request can proceed through multiple async steps.

```text
HTTP/1.1 keep-alive on one TCP connection:
  TCP connection ─ GET /a → 200 ─ GET /b → 200 ─ GET /c → 404 ─ close

HTTP/2 on one TCP/TLS connection:
  Connection ─ stream 1: GET /events ───── multiple DATA frames ───
             ├ stream 3: GET /api/a ─ 200
             └ stream 5: GET /api/b ────── 200
```

**Do not infer:** 1000 concurrent requests necessarily equal 1000 TCP connections. HTTP version, keep-alive, proxies, connection limits, and client behavior determine that relationship.

### 2.3. Netty Channel

In Netty, `Channel` abstracts an I/O connection or endpoint. `ChannelPipeline` holds handlers responsible for inbound/outbound events and protocol transformations. A channel is normally bound to an `EventLoop` handling its I/O events; an event loop can serve **many** channels.

### 2.4. Event-loop thread

An event loop executes callbacks for I/O-ready events and scheduled tasks. Instead of one thread sleeping on one socket, the event loop briefly processes events that are ready. If a callback calls `Thread.sleep(2000)` or blocking JDBC, **other channels sharing the same loop** can slow down as well.

The number of event-loop threads **depends on version, CPU, configuration, native transport, and runtime environment**; never hardcode "always 1 loop/core" or "only 2 threads".

### 2.5. Servlet request worker thread

In synchronous Spring MVC, one worker thread usually runs the entire filter/controller/render sequence for **one request** and can be held while calling blocking APIs. However, a keep-alive TCP connection is **not pinned to the same thread at all times**. Tomcat connectors still have NIO mechanisms watching sockets; the thread pool relates to executing request processing rather than equaling the connection count.

## 3. Comparing three models doing the same work

Suppose an API calls a remote HTTP service taking 300 ms to reply; business code uses almost no CPU.

### 3.1. Synchronous Spring MVC

```text
TCP socket ─ Servlet container/connector
                    │ request ready
                    ▼
              Worker thread T1
                 ├─ Servlet Filters
                 ├─ DispatcherServlet
                 ├─ @Controller
                 ├─ blocking HTTP client call: waits ~300ms
                 ├─ JSON serialize
                 └─ HTTP response
                    T1 returns to pool
```

In this style, a worker can stay occupied for 300 ms despite doing little computation. If all workers are busy waiting, new requests queue or get rejected per server policy.

### 3.2. Spring MVC with Callable/DeferredResult

```text
Servlet worker T1:
  DispatcherServlet → Controller returns Callable / DeferredResult
  → Servlet async start → T1 returns to pool

Callable: MVC AsyncTaskExecutor worker T2
  → blocking remote call (~300ms) → result

or DeferredResult:
  → result populated by producer callback/event

Servlet worker T3:
  ASYNC dispatch → serialize/write response → finishes
```

Servlet async **frees the initial container thread**, yet a `Callable` running a blocking operation still holds an executor worker; `DeferredResult` can eliminate waiting threads if the producer is truly event-driven. Async MVC does not magically turn blocking database/client APIs into non-blocking ones.

### 3.3. Spring WebFlux with a non-blocking HTTP client

```text
Reactor Netty event-loop:
  HTTP request received
    → WebFlux handlers
    → WebClient reactive request initialized
    → Publisher has no result yet; callbacks registered
    → event-loop does not sleep waiting for remote response

When remote HTTP data arrives:
  → network readiness event
  → Reactor operator callbacks
  → HTTP codecs encode response
  → non-blocking write when channel is ready
```

With a truly non-blocking WebClient/driver, no Java worker needs to be held just waiting on the network. CPU is still needed for parsing/serialization, TLS, and business logic, and separate thread pools still exist for certain tasks.

### 3.4. Summary comparison table

| Question | MVC sync (Servlet) | MVC async (Servlet) | WebFlux reactive |
| --- | --- | --- | --- |
| HTTP entry point | Servlet/DispatcherServlet | Servlet/DispatcherServlet + async | HttpHandler/WebHandler/DispatcherHandler |
| Common return types | DTO, String, ResponseEntity | Callable, DeferredResult, CompletableFuture | Mono, Flux, Publisher, Coroutine |
| Downstream I/O | Usually blocking, can use async clients | Blocking worker or async callback | Designed for non-blocking; still easy to call blocking mistakenly |
| Thread while waiting | Request worker may wait | Servlet thread freed; dedicated worker may wait | No worker waiting if dependencies are reactive |
| Backpressure handling | Not a primary sync controller contract | Depends on async/streaming APIs | Reactive Streams demand across publishers and supporting server adapters |
| Server runtime | Tomcat/Jetty/Undertow, Servlet | Tomcat/Jetty/Undertow, Servlet async | Reactor Netty default in Boot; also Tomcat/Jetty/adapters |
| Best fit | Imperative/blocking logic, Servlet ecosystem | Async callbacks or freeing Servlet threads | High concurrent I/O, streaming, reactive dependencies |
| What to measure | Pool saturation/queues | Executors/timeouts/cancellations | Event-loop lag, buffers, demand, cancellations, connector pools |

**There is no automatic winner.** MVC is often simpler when the entire JDBC and library stack is blocking; WebFlux shines when HTTP clients, DB drivers, broker adapters, and serialization pipelines are genuinely non-blocking. For CPU-bound workloads, reactive does not make computation faster on its own.

## 4. Does Spring WebFlux require Reactor Netty?

**No.** Spring WebFlux sits at the web framework layer, with adapters underneath for HTTP runtimes.

Spring Framework layers:

```text
@REST Controller / RouterFunction
            │
            ▼
       DispatcherHandler
            │
            ▼
         WebHandler
            │
            ▼
        HttpHandler
            │
            ├── ReactorHttpHandlerAdapter → Reactor Netty
            ├── ServletHttpHandlerAdapter → Servlet container
            ├── Tomcat/Jetty adapters per stack/version
            └── Other HTTP server adapters supported by the framework
```

Exact adapter names and implementations can vary by Spring Framework version and embedded server. What stays constant is the **`HttpHandler` contract** adapting across multiple runtimes.

In Spring Boot **3.3.x**:

- `spring-boot-starter-webflux` includes `spring-boot-starter-reactor-netty` by default, so the default embedded server is **Reactor Netty**.
- You can swap the Netty server starter for Tomcat/Jetty/Undertow **within compatible Boot 3.3 config**. The app remains on the **WebFlux programming model**, not automatically switching to Spring MVC.
- If you add both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot normally **prefers the MVC/Servlet web application type**. Never use the presence of `Mono`/`Flux` on the classpath to infer the server is running WebFlux.
- When running WebFlux on Tomcat/Jetty, non-blocking HTTP I/O is bridged via Servlet support; never say Tomcat "cannot run reactive".
- Netty itself is **not** a Servlet container. Reactor Netty uses Netty APIs/event loops rather than passing through DispatcherServlet.

### 4.1. Netty and Servlet containers differ at the lower API layer

| Component | Reactor Netty runtime | Servlet container used for MVC |
| --- | --- | --- |
| HTTP entrypoint | Netty Channel/Pipeline, Reactor HTTP adapters | Servlet request/response and Servlet filters |
| Java web framework | WebFlux WebHandler/DispatcherHandler | Spring MVC DispatcherServlet |
| I/O primitives | Netty asynchronous channel I/O | Servlet container connectors (with NIO), Servlet request/response APIs |
| Async semantics | Reactive Publisher, event-driven flow | Servlet async `AsyncContext` or synchronous handlers |
| Web filters | WebFlux `WebFilter`, `WebExceptionHandler` | Servlet `Filter`, Spring Security Servlet chain |
| Request objects | `ServerHttpRequest`, `ServerWebExchange` | `HttpServletRequest`/`HttpServletResponse` |
| Main risk | Blocking event loops, unbounded buffers | Worker pool saturation, blocking waits, queue pressure |

**"Servlet container" does not mean "blocking TCP socket API".** Modern containers feature non-blocking transport and asynchronous Servlet I/O, yet servlet-style controller code can still block workers.

### 4.2. Boot selects the web application type

Example `pom.xml` with only the WebFlux starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

By default, Boot creates a **reactive** application context and a Reactor Netty embedded server.

Example switching the embedded server to Tomcat on Boot 3.3 (an alternative dependency pattern; do not include two server starters unintentionally):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-reactor-netty</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
</dependency>
```

This is an **alternative variant** for the section 11 demo `pom.xml`, not meant to be combined directly with a WebFlux starter that still retains Reactor Netty. When changing servers, separately test TLS/HTTP2/Servlet filters and resource management.

## 5. HTTP server pipeline in WebFlux

### 5.1. HttpHandler: the minimal contract

In Spring's reactive HTTP layer, `HttpHandler` can be understood as:

```java
public interface HttpHandler {
    Mono<Void> handle(
        ServerHttpRequest request,
        ServerHttpResponse response);
}
```

This is the core explanatory signature; the interfaces live in package `org.springframework.http.server.reactive`. The `Mono<Void>` result represents **completion of processing the HTTP response**, not a single DTO/body.

Spring implements/adapts this contract onto specific server APIs:

- Reactor Netty: Netty inbound/outbound APIs.
- Servlet non-blocking bridge: HTTP request/response can be adapted to Publisher-based body flows.
- Other server adapters depending on version.

You usually **do not write HttpHandler yourself** in Boot apps; Boot and WebFlux auto-configuration assemble the framework pipeline.

### 5.2. WebHandler and ServerWebExchange

`WebHandler` contract:

```java
public interface WebHandler {
    Mono<Void> handle(ServerWebExchange exchange);
}
```

`ServerWebExchange` bundles request, response, session, attributes, locale/principal APIs, and the context needed to handle one HTTP exchange. It is **not** `HttpServletRequest`. When running on Reactor Netty, there is no native Servlet request to cast to.

Representative classes:

| Class/interface | Responsibility |
| --- | --- |
| `HttpHandler` | Server-independent contract for HTTP exchanges |
| `ServerHttpRequest` | Reactive request abstraction, headers/method/body |
| `ServerHttpResponse` | Reactive response abstraction, status/headers/write |
| `WebHandler` | Contract for handling one `ServerWebExchange` |
| `WebFilter` | Functional WebFlux filter chain at the WebHandler layer |
| `WebExceptionHandler` | Handles errors in the reactive web chain |
| `DispatcherHandler` | WebFlux front controller finding handlers/routers |
| `HandlerMapping` | Picks controller/function based on request |
| `HandlerAdapter` | Invokes the matching handler |
| `HandlerResultHandler` | Converts return values into HTTP responses |
| `HttpMessageReader/Writer` | Codecs reading/writing bodies by media type |
| `DataBuffer` | Buffer abstraction used for body streams |

### 5.3. Full request flow

```text
Client TCP/TLS connection
    │ (HTTP/1.1 or HTTP/2; Netty Channel)
    ▼
Reactor Netty event-loop / HTTP codecs
    ▼
ReactorHttpHandlerAdapter
    ▼
HttpHandler (Spring WebFlux)
    ▼
HttpWebHandlerAdapter / WebFilter chain
    ▼
DispatcherHandler
    ├── HandlerMappings → finds @Controller or RouterFunction
    ├── HandlerAdapter → invoke handler
    └── HandlerResultHandler → encode result
            │
            ├── Mono<DTO>       → JSON object or response logic
            ├── Flux<DTO>       → finite JSON array / streaming when appropriate
            ├── Mono<Void>      → completion without body value
            └── Flux<DataBuffer> → body bytes on demand
    ▼
ServerHttpResponse non-blocking write
    ▼
Netty outbound Channel → socket → client
```

On the error path, WebFlux exception handling/filter chains can handle errors before the response is committed. Once the server has flushed some SSE/stream bytes, it cannot always switch the HTTP status from 200 to 500; you must use protocol-level error events or close the stream per contract.

### 5.4. Codec layers and buffer limits

Before a handler receives a `@RequestBody Mono<MyDto>` object, HTTP body bytes pass through readers/decoders like Jackson. When a handler returns a Flux, encoding behavior depends on media type and codec.

With `application/json`, a finite Flux is typically encoded as a JSON array; **there is no promise to flush each item immediately as onNext occurs**. With `text/event-stream` or newline-delimited JSON, streaming semantics are much more explicit.

Spring Boot provides the property:

```properties
spring.codec.max-in-memory-size=256KB
```

This limits in-memory buffering when codecs need to aggregate, not total bytes per TCP connection or whole-JVM memory. For large bodies, consider streaming readers, uploads, proxy/server max request sizes, and storage policies. `DataBufferLimitException` typically points to codec aggregation limits.

## 6. How does the event loop execute requests?

### 6.1. Diagram of a processing cycle

```text
Multiple channels assigned to event loops:

Channel A: data ready  ───┐
Channel B: idle         ───┤      EventLoop #1
Channel C: write ready ───┘       ├─ read bytes A
                                 ├─ decode HTTP request A
                                 ├─ invoke non-blocking Reactor callbacks
                                 └─ flush bytes C when writable

Channel D: data ready  ───┐
Channel E: idle         ───┤      EventLoop #2
Channel F: stream       ───┘       ├─ process D
                                 └─ continue F when demand/ready
```

This diagram is **illustrative**, not claiming every instance runs exactly two loops. An event loop executes scheduled tasks, channel callbacks, TLS encode/decode, and framework logic. It must avoid prolonged blocking work so other channels are not starved.

### 6.2. What work belongs on the event loop?

- Parsing headers/connections, lightweight handler routing.
- Composing reactive Publishers.
- Moderate-cost mapping/validation/serialization.
- Scheduling network writes and short reactive callbacks.

### 6.3. Work that must not hold the event loop

- `Thread.sleep(1000)` or blocking `CompletableFuture.get()`.
- Blocking JDBC/JPA queries.
- Calling HTTP with synchronous clients or `RestTemplate` on the event-loop path.
- Direct Java blocking file I/O on large files.
- Heavy CPU computations lasting hundreds of ms, or large encryption/decompression on the loop.
- Long-running database transactions in imperative code.

**One blocking request can stall many other requests** sharing the same event loop. When debugging, inspect thread dumps, event-loop latency, BlockHound (if configured for tests), request queues, and upstream timeouts — not just HTTP 500 counts.

### 6.4. Mono/Flux does not automatically make blocking non-blocking

Wrong:

```java
@GetMapping("/bad")
Mono<String> bad() {
    return Mono.just(legacyBlockingClient.call());
}
```

`legacyBlockingClient.call()` runs **immediately when the controller method is called**, before the Mono is even created. Returning Mono does not alter the blocking nature of this call.

Also insufficient:

```java
@GetMapping("/still-bad")
Mono<String> badToo() {
    return Mono.fromCallable(() -> legacyBlockingClient.call());
}
```

This is **lazy**, yet upon subscription it can still run on the event loop unless a suitable scheduler is chosen. When forced to bridge a blocking API, use a temporary bridge:

```java
@GetMapping("/bridge")
Mono<String> bridge() {
    return Mono.fromCallable(() -> legacyBlockingClient.call())
        .subscribeOn(Schedulers.boundedElastic());
}
```

Snippet requires `legacyBlockingClient` dependency and Reactor imports. `boundedElastic` is a bounded scheduler better suited for blocking tasks, yet it does not make JDBC non-blocking; if the pool/queue saturates, delays/rejections still occur. Prefer R2DBC, WebClient, or reactive clients when end-to-end non-blocking behavior is needed.

### 6.5. CPU-bound work should not hide under boundedElastic

If a task performs heavy cryptography/compression/ML transforms, using boundedElastic (designed primarily for blocking waits) does not guarantee good latency. Use a bounded compute executor/scheduler sized to CPU cores with proper workload/queue policies, or offload to separate services/worker jobs when needed. Reactor's `Schedulers.parallel()` suits short/appropriate CPU tasks, though you must avoid monopolizing worker threads with infinite loops.

## 7. Backpressure from Publisher to network

Reactive Streams distinguishes:

- **Publisher**: capable of emitting data.
- **Subscriber**: receives data.
- **Subscription**: manages `request(n)` / `cancel`.
- **Demand**: how many more items downstream wants.

Example:

```text
Flux.just(1,2,3,4,5)
       │
       ▼
Subscriber request(2)
       │
       ├── onNext(1)
       └── onNext(2)
       │
Subscriber request(3)
       ├── onNext(3)
       ├── onNext(4)
       └── onNext(5)
       │
       └── onComplete()
```

In WebFlux, HTTP readers/writers and Reactor Netty couple downstream readiness/buffering with reactive subscriptions where supported. However, distinguish three flow-control layers:

1. **Reactive Streams demand** between Publisher/Subscriber inside the JVM.
2. **TCP flow control** based on receive windows/network stacks.
3. **HTTP/2 stream/connection flow control** at the protocol layer.

They interact yet are **not one-to-one**, and there is no guarantee every external producer honors demand. An upstream broker pushing callbacks continuously can produce a `Flux` faster than a client can read; you must define buffer/drop/error policies and monitor memory.

### 7.1. Streaming and JSON arrays

```java
@GetMapping("/api/numbers")
Flux<Integer> numbers() {
    return Flux.range(1, 5);
}
```

With JSON content type, the body is normally:

```json
[1,2,3,4,5]
```

The response codec can buffer and avoid sending each item separately to the browser as `onNext` fires. To deliver events immediately to clients, use SSE:

```java
@GetMapping(
        value = "/api/ticks",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> ticks() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(n -> ServerSentEvent.<String>builder()
            .event("tick")
            .data("tick-" + n)
            .build());
}
```

This is an illustrative controller snippet; an infinite stream **requires handling cancellation, timeouts, and rate limits** in production. The runnable project in section 11 caps at three events for easy testing.

### 7.2. Streaming also needs limits

- `collectList()` must retain all items until the Flux completes. If the Flux is infinite, no result ever arrives and heap grows.
- Unbounded `onBackpressureBuffer()` can lead to OOM.
- `Flux.interval(...)` with slow consumers can emit overflow errors depending on strategy; do not treat timers as reliable data queues.
- `doFinally` helps clean up resources when a stream **completes, errors, or cancels**.
- Many-client WebSocket/SSE setups need connection budgets, heartbeats, and proxy idle timeouts.

## 8. WebClient outbound connections: different from inbound server

A common mistake is equating HTTP connections accepted by the Reactor Netty **server** with connections opened by `WebClient` to remote services.

### 8.1. Inbound server socket

`GET /api/proxy` from a browser into the app: the app is **accepting an inbound** connection via the Reactor Netty HttpServer. The server manages channels, request reads/writes, TLS, keep-alive, and event loops.

### 8.2. Outbound WebClient pool

Inside a handler, WebClient calls `https://catalog.example.test`: the app acts as an **HTTP client**, creating or reusing **outbound connections** to the target host. Reactor Netty HttpClient normally uses connection pooling; it can be managed via `ConnectionProvider`.

```text
Browser
   ─ TCP/TLS inbound #1 ─► Spring WebFlux / Reactor Netty server
                            │
                            │ WebClient.get(...)
                            ▼
                       HttpClient pool (outbound)
                            │   ├ TCP/TLS outbound A
                            │   ├ TCP/TLS outbound B
                            │   └ pending acquire queue
                            ▼
                      Remote catalog service
```

**Do not equate** "1 incoming request = 1 outbound connection". Outbound connections can be reused; one incoming request can fan out to multiple services; the pending acquire queue can fill up even while the inbound server still accepts sockets.

### 8.3. Custom outbound pool example

An explicit configuration (placed in `@Configuration`; this is an illustrative snippet, not required in the runnable demo):

```java
@Bean(destroyMethod = "dispose")
ConnectionProvider catalogPool() {
    return ConnectionProvider.builder("catalog-pool")
        .maxConnections(30)
        .pendingAcquireMaxCount(60)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofSeconds(20))
        .build();
}

@Bean
WebClient catalogWebClient(WebClient.Builder builder,
                           ConnectionProvider catalogPool) {
    HttpClient client = HttpClient.create(catalogPool)
        .responseTimeout(Duration.ofSeconds(3))
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000);

    return builder
        .baseUrl("https://catalog.example.test")
        .clientConnector(new ReactorClientHttpConnector(client))
        .build();
}
```

Requires imports `reactor.netty.resources.ConnectionProvider`, `reactor.netty.http.client.HttpClient`, `io.netty.channel.ChannelOption`, `org.springframework.http.client.reactive.ReactorClientHttpConnector`, `org.springframework.web.reactive.function.client.WebClient`, `Duration`, and Spring `@Bean`. Host is a sample domain, not a live endpoint for integration tests. In Boot, usually **reuse the Boot-supplied `WebClient.Builder`** instead of creating a new WebClient per request.

Meaning:

- `maxConnections(30)` is the pool limit in this example config, not a universal default for every Reactor Netty version.
- `pendingAcquireMaxCount(60)` caps requests waiting for a connection while the pool is busy.
- `pendingAcquireTimeout(2s)` caps how long to wait for a connection from the pool.
- `CONNECT_TIMEOUT_MILLIS` sets the timeout for opening the TCP connection.
- `responseTimeout` is HttpClient's network I/O response wait policy; distinct from an end-to-end business timeout.
- `maxIdleTime` limits holding idle connections too long; account for remote/proxy timeouts.
- `destroyMethod="dispose"` gives the custom ConnectionProvider lifecycle cleanup when the Spring context shuts down.

Do not copy 30/60/2s into production without measuring traffic, TLS handshakes, upstream rate limits, p95 response times, and pool saturation. An oversized pool can exhaust upstream, NAT ports, or OS resources. An undersized pool causes pending acquire latency and timeouts.

### 8.4. Types of timeouts to distinguish

| Type | Relates to |
| --- | --- |
| TCP connect timeout | Time to establish TCP connection to remote host |
| TLS handshake timeout | Time to complete TLS handshake |
| Pool pending acquire timeout | Waiting to obtain an idle outbound connection |
| HTTP response timeout | Waiting for response/network progress per HttpClient semantics |
| Reactive `timeout(Duration)` | Operator-level publisher time budget |
| Inbound HTTP server idle timeout | Idle client-to-server connection |
| Reverse proxy read timeout | Gateway/LB may close the request before the server |
| Business deadline | Entire operation must complete within SLA |

Attaching `timeout(Duration)` to a Mono does not necessarily **immediately cancel** side effects already received by a remote server. Cancellation propagates through reactive clients when supported, yet remote business logic may keep running; account for POST idempotency, retries, and duplicate suppression.

## 9. Swapping runtimes: Reactor Netty, Tomcat, Jetty

### 9.1. Boot's default Netty

When using `spring-boot-starter-webflux` without excluding Netty, Boot usually picks the Netty reactive web server factory. This works nicely when WebClient also uses Reactor Netty since they can share event-loop resources depending on configuration.

### 9.2. WebFlux on a Servlet adapter

You can use a Servlet container supporting async/non-blocking I/O to adapt the WebFlux contract. App code still returns Mono/Flux while the server adapter maps reactive reads/writes onto Servlet non-blocking APIs. **Never** use `HttpServletRequest` and `DispatcherServlet` as central abstractions in a WebFlux controller just because the runtime is Tomcat.

### 9.3. Spring MVC on Netty?

Spring MVC is built on the Servlet API; Reactor Netty is not a Servlet container. Therefore, never assume replacing `spring-boot-starter-tomcat` with `reactor-netty` will run Spring MVC controllers properly on Netty like WebFlux. If the app still needs Servlet filters, JSP, or synchronous servlet integrations, pick an appropriate MVC/Servlet runtime.

### 9.4. HTTP/2 and TLS

HTTP/2 multiplexing changes the connection→request mapping. One connection can carry many streams. Enabling HTTP/2 also depends on TLS/h2 ALPN or h2c, Netty/Tomcat/Jetty versions, reverse proxies, and clients.

In Boot, setting:

```properties
server.http2.enabled=true
```

is only part of it: verify protocol negotiation and server TLS/certificate/runtime support. Do not equate HTTP/2 with reactive; MVC/Tomcat can serve HTTP/2 as well.

## 10. Performance comparisons and real-world limits

### 10.1. Fewer threads is not automatically faster

*Simulated educational* table, not an actual Spring benchmark:

| Workload | Servlet sync | Reactive non-blocking |
| --- | --- | --- |
| 1 request calling remote API waiting 500ms | One worker may be held while waiting | Event loop does not wait if WebClient is non-blocking |
| 1000 requests waiting 500ms on remote API | Workers/queues can experience pressure | Can hold many in-flight subscriptions with few event-loop threads |
| 1 request encrypting 2GB (CPU-intensive) | Still uses CPU | Still uses CPU; event loop is easily monopolized if run directly |
| 1 request doing 500ms blocking JDBC | Clear blocking characteristics | If run directly on event loop, causes stalls even if method returns Mono |
| Many SSE connections | Servlet async has a viable model if tuned | Naturally fits reactive streaming/backpressure |
| 100% CDN cache-hit | Origin may receive no requests | Origin may likewise receive no requests |

What must be measured are **p95/p99 latency, throughput, CPU, active threads, queue lengths, heap, GC, connection metrics, response bytes, event-loop lag**, and downstream pool saturation. Never compare two servers with mismatched thread pools/database configs and conclude the framework alone dictates everything.

### 10.2. Little's Law and waiting time

A common relationship model: average in-flight requests ≈ arrival rate × average latency in a steady system. When many requests have latency dominated by I/O waits, concurrency can be high despite low CPU. Reactive makes **holding threads** far more flexible, yet **it does not turn in-flight requests or buffers into zero**.

For example, 200 requests/s × 0.5 seconds latency ≈ 100 average in-flight requests. This is just an arithmetic illustration, not a promise that a server can serve infinite requests given enough event-loop threads.

### 10.3. Resources that still run out despite few event loops

- File descriptors and ephemeral ports.
- Heap memory for request metadata, pending subscriptions, buffers, and JSON objects.
- Direct/off-heap buffers in Netty.
- HTTP client connection pools and DNS/TLS overhead.
- DB connection pools / remote upstream quotas.
- Pending writes when clients download slowly.
- Retry storms, timeouts, and queue overload.
- CPU spikes from codecs, compression, and TLS.
- Long-lived SSE/WebSocket state, heartbeats, and proxy idling.

Design connection budgets, bulkheads, admission control/rate limits, and graceful degradation. Never create unbounded queues just because an endpoint is called "async".

## 11. Runnable demo: Spring Boot 3 + Java 17 on Reactor Netty

The following app demonstrates **directly observable differences** without pretending to count event-loop threads in flaky tests.

Endpoints:

| URL | Return type | Purpose |
| --- | --- | --- |
| `GET /api/ping` | `Mono<Reply>` | Single JSON result |
| `GET /api/delay?ms=25` | `Mono<Reply>` | Non-blocking delay via `Mono.delay` |
| `GET /api/blocking-bridge` | `Mono<Reply>` | Offloads demo `Thread.sleep` to `boundedElastic` |
| `GET /api/headers` | `Mono<Map>` | Reads HTTP headers in WebFlux without Servlet request |
| `GET /api/none` | `Mono<ResponseEntity<Void>>` | Explicit HTTP 204 |
| `GET /api/stream` | `Flux<ServerSentEvent<String>>` | Finite SSE stream with 3 events |
| `GET /api/fail` | `Mono<Reply>` | Reactive error routed through exception handling |
| All `/api/**` | `WebFilter` | Response header confirming WebFlux filter ran |

No external service or real database is needed, so the project runs right after Maven downloads dependencies. `Thread.sleep` inside boundedElastic merely illustrates isolating workers from the event loop, **not a preferred production pattern**.

### 11.1. Directory tree

```text
reactive-server-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── ReactiveServerApplication.java
    │   │   ├── ApiController.java
    │   │   └── ReactiveFilter.java
    │   └── resources/application.properties
    └── test/
        └── java/example/ApiControllerTest.java
```

### 11.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-server-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

### 11.3. ReactiveServerApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveServerApplication.class, args);
    }
}
```

### 11.4. application.properties

```properties
server.port=8080
spring.codec.max-in-memory-size=256KB
logging.level.reactor.netty.http.server=INFO
```

The codec property is a guardrail when decoders need buffering; it does not mean "every body above 256KB is rejected" across all streaming paths. Depending on sources, filters, and decoders, other server/proxy limits may apply.

### 11.5. ApiController.java

```java
package example;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class ApiController {

    public record Reply(String kind, long value) {}

    @GetMapping("/api/ping")
    public Mono<Reply> ping() {
        return Mono.just(new Reply("pong", 1));
    }

    @GetMapping("/api/delay")
    public Mono<Reply> delay(
            @RequestParam(defaultValue = "25") long ms) {

        if (ms < 0 || ms > 2000) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "ms must be in 0..2000"));
        }

        return Mono.delay(Duration.ofMillis(ms))
                .map(tick -> new Reply("delayed", ms));
    }

    @GetMapping("/api/blocking-bridge")
    public Mono<Reply> bridge() {
        return Mono.fromCallable(() -> {
                // Blocking legacy work isolated from the event loop.
                TimeUnit.MILLISECONDS.sleep(20);
                return new Reply("bridged", 20);
            })
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/api/headers")
    public Mono<Map<String, String>> headers(
            @RequestHeader(name = "X-Demo", defaultValue = "absent")
                    String demo) {

        return Mono.just(Map.of("demo", demo));
    }

    @GetMapping("/api/none")
    public Mono<ResponseEntity<Void>> none() {
        return Mono.<Void>empty()
                .thenReturn(ResponseEntity.noContent().build());
    }

    @GetMapping(
            value = "/api/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> stream() {
        return Flux.interval(Duration.ofMillis(20))
            .take(3)
            .map(index -> ServerSentEvent.<String>builder()
                .id(Long.toString(index))
                .event("tick")
                .data("tick-" + index)
                .build());
    }

    @GetMapping("/api/fail")
    public Mono<Reply> fail() {
        return Mono.error(new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "dependency temporarily unavailable"));
    }
}
```

**What does this code illustrate?**

- `Mono.just` returns a `Reply` immediately without needing an extra thread.
- `Mono.delay` signals when the timer scheduler fires, **without calling `Thread.sleep` on the event loop**.
- `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` lets a brief blocking legacy call run without blocking the event loop. Enforce real timeouts/bulkheads in production.
- `@RequestHeader` still works in annotated WebFlux, while the reactive request infrastructure requires no `HttpServletRequest`.
- `Mono<Void>.thenReturn(ResponseEntity.noContent())` produces HTTP 204 explicitly.
- `Flux.interval(...).take(3)` stops after 3 events so the response is finite and easy to test; real streams can run longer and require cleanup/cancellation.
- Errors from `Mono.error(ResponseStatusException)` are mapped to status codes by WebFlux error handling if the response has not yet committed.

**Never claim a request through Mono always runs on one fixed thread.** Reactor schedulers and Netty callbacks can switch execution contexts; asserting body/status verifies stable behavior, whereas thread names are only diagnostic aids.

### 11.6. ReactiveFilter.java

```java
package example;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class ReactiveFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        if (exchange.getRequest().getPath()
                .value().startsWith("/api/")) {
            exchange.getResponse().getHeaders()
                    .add("X-Processing-Stack", "webflux");
        }
        return chain.filter(exchange);
    }
}
```

This is a **WebFlux WebFilter**, not `jakarta.servlet.Filter`. In this app, the response header `X-Processing-Stack: webflux` lets tests confirm the filter ran in the chain. It is not a security control, and the header name is purely educational.

WebFlux Security, when `spring-boot-starter-security` is added, uses `SecurityWebFilterChain` / reactive authentication/authorization; never apply Servlet `SecurityFilterChain` as in Spring MVC. In hybrid deployments, identify the active web application type accurately.

### 11.7. Running and observing with cURL

In the `pom.xml` directory with Java 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

A few requests:

```bash
curl -i http://localhost:8080/api/ping
curl -i "http://localhost:8080/api/delay?ms=25"
curl -i http://localhost:8080/api/blocking-bridge
curl -i -H "X-Demo: hello" http://localhost:8080/api/headers
curl -i http://localhost:8080/api/none
curl -i "http://localhost:8080/api/delay?ms=-1"
curl -i http://localhost:8080/api/fail
```

Expected:

| URL | Status | Main body |
| --- | ---: | --- |
| `/api/ping` | 200 | `{"kind":"pong","value":1}` |
| `/api/delay?ms=25` | 200 | `{"kind":"delayed","value":25}` |
| `/api/blocking-bridge` | 200 | `{"kind":"bridged","value":20}` |
| `/api/headers` with X-Demo: hello | 200 | `{"demo":"hello"}` |
| `/api/none` | 204 | No body |
| `/api/delay?ms=-1` | 400 | Error response formatted by Spring error handler |
| `/api/fail` | 503 | Error response formatted by Spring error handler |

Testing SSE:

```bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/stream
```

Expected body for SSE media type (omitting varying response headers):

```text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

id:2
event:tick
data:tick-2

```

Do not hardcode HTTP header ordering or Reactor Netty thread names; cURL `-N` disables curl's own output buffering without changing server semantics. Even with Flux streaming, actual flush timing still depends on server, client, and proxies.

### 11.8. What to observe in logs?

Reactor Netty logs HTTP server startup, bound ports, and transport errors. Specific thread names are not guaranteed across versions or environments. To inspect event-loop state, use proper metrics/observability, thread dumps, and load tests; never infer peak load capacity from having few idle threads in the JVM.

## 12. WebTestClient: end-to-end reactive API testing

Spring WebFlux commonly uses `WebTestClient`. With `@SpringBootTest(webEnvironment = RANDOM_PORT)` and `@AutoConfigureWebTestClient`, tests send real HTTP requests to the embedded server, validating Spring routing/filters/codecs/Netty config far better than pure controller unit tests.

File `src/test/java/example/ApiControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void pingIsJsonAndPassesReactiveWebFilter() {
        client.get().uri("/api/ping")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                    "X-Processing-Stack", "webflux")
            .expectBody()
                .jsonPath("$.kind").isEqualTo("pong")
                .jsonPath("$.value").isEqualTo(1);
    }

    @Test
    void reactiveDelayReturnsExpectedValue() {
        client.get().uri("/api/delay?ms=1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.kind").isEqualTo("delayed")
                .jsonPath("$.value").isEqualTo(1);
    }

    @Test
    void negativeDelayIsRejected() {
        client.get().uri("/api/delay?ms=-1")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void tooLargeDelayIsRejected() {
        client.get().uri("/api/delay?ms=5000")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void blockingBridgeReturnsFromOffloadedPublisher() {
        client.get().uri("/api/blocking-bridge")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.kind").isEqualTo("bridged")
                .jsonPath("$.value").isEqualTo(20);
    }

    @Test
    void requestHeaderIsAvailableThroughWebFlux() {
        client.get().uri("/api/headers")
            .header("X-Demo", "checked")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.demo").isEqualTo("checked");
    }

    @Test
    void noBodyEndpointReturns204() {
        client.get().uri("/api/none")
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();
    }

    @Test
    void reactiveErrorMapsTo503() {
        client.get().uri("/api/fail")
            .exchange()
            .expectStatus().isEqualTo(503);
    }

    @Test
    void sseEndpointHasCorrectContentType() {
        client.get().uri("/api/stream")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM);
    }

    @Test
    void missingRouteIsNotFound() {
        client.get().uri("/api/does-not-exist")
            .exchange()
            .expectStatus().isNotFound();
    }
}
```

The test suite does not assert "the server has exactly N event-loop threads" because that is an implementation/configuration detail, not an API contract. `reactiveDelayReturnsExpectedValue` verifies reactive timer completion; it does **not** prove better CPU/latency than MVC.

### 12.1. Testing the SSE body instead of just Content-Type

A deeper stream test can use:

```java
FluxExchangeResult<ServerSentEvent<String>> result =
    client.get().uri("/api/stream")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(new ParameterizedTypeReference<
                ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
    .expectNextMatches(e -> "tick-0".equals(e.data()))
    .expectNextMatches(e -> "tick-1".equals(e.data()))
    .expectNextMatches(e -> "tick-2".equals(e.data()))
    .verifyComplete();
```

This is an additional snippet for a test method requiring `FluxExchangeResult`, `ServerSentEvent`, `ParameterizedTypeReference`, and `StepVerifier` imports. Do not use this outside a context where `client` exists. Advantage: verifies **three actual SSE signals**, not only headers.

### 12.2. Unit/integration tests do not replace load testing

To measure reactive concurrency, test representative traffic: 100–1000 concurrent clients, realistic wait latencies, connection reuse, and response sizes. Use JFR, Micrometer/Actuator, Reactor Netty metrics, OS socket stats, thread dumps, and network tooling. Never conclude WebFlux is faster than MVC based solely on 10 passing HTTP assertions.

## 13. Managing response lifecycle and client disconnects

### 13.1. Before the response starts

If a handler returns `Mono.error(new ResponseStatusException(HttpStatus.BAD_REQUEST))` before commit, WebFlux can set the corresponding status and error response. Security filters/CORS/codecs can still participate per configuration.

### 13.2. Once SSE has already sent bytes

```text
GET /api/stream
HTTP/1.1 200 OK
Content-Type: text/event-stream

data:tick-0

data:tick-1

... then upstream errors ...
```

Once the response has committed and delivered events to the client, the server cannot roll back and turn 200 into HTTP 500 like a regular JSON response. It can emit an SSE protocol error event or close the stream and let the client retry per policy.

### 13.3. When the client cancels

The reactive subscription can receive cancellation when the browser closes the connection or the user aborts the request. Cleanup hooks:

```java
Flux<String> values =
    service.events()
        .doFinally(signal -> {
            // signal can be COMPLETE, ERROR, or CANCEL.
            // Collect metrics / clean up lightweight resources;
            // do not run blocking operations on the event loop.
        });
```

This is an illustrative snippet with a hypothetical `service.events()`. Client disconnects may not be detected immediately across proxies/LBs; add heartbeats/idle timeouts when early dead-connection detection is needed.

### 13.4. Retries and idempotency

Never blindly retry non-idempotent POSTs on network errors. The remote server may have already received the request and executed side effects before the connection dropped. Use idempotency keys, transaction/broker semantics, bounded retries/backoff, and duplicate suppression.

## 14. Server resources and lifecycle

In Reactor Netty, event loops, pooled buffers, and connections are all resources with lifecycles.

With Boot:

- Use the embedded Netty server via auto-configuration instead of manually calling `HttpServer.bindNow()` in multiple places.
- Reuse the Boot-provided `WebClient.Builder`; never allocate a new client/pool **per HTTP request**.
- When creating a custom `ConnectionProvider`, dispose of it cleanly when the application closes.
- For custom Netty LoopResources, manage disposal and avoid creating duplicate event loops.
- When swapping client connectors or server factories, track which component owns the event-loop resources.
- Graceful shutdown can use Boot config:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Actual shutdown duration for long-lived SSE/WebSocket/requests depends on the server/runtime and application. Never assume every connection always drains before timeout simply because graceful shutdown is enabled.

### 14.1. Keep-alive connections and idle timeouts

A connection that finished an HTTP request can stay open for reuse. If idle too long, server/client/proxy may close it. With SSE, a connection remains logically active yet may carry no bytes for long stretches; proxies may enforce their own read timeouts. Add appropriate heartbeats and avoid keeping connections open indefinitely if clients no longer exist.

### 14.2. HTTP server metrics to track

- Active/open connections, new connections, and close/error counts.
- In-flight requests, completed statuses, latency percentiles.
- Event-loop pending tasks / blocking detection / latency.
- Outbound connection pool active/idle/pending/acquire failures.
- TLS handshake/connect timeouts.
- Response stream cancellation/error counts.
- Heap/direct memory, GC pauses, and DataBuffer utilization.
- Remote dependency latencies and circuit-breaker states.
- TCP retransmits, proxy 502/503/504, and OS file-descriptor usage.

Exact metric names depend on Reactor Netty/Micrometer/Actuator versions; never invent series names without checking the actual runtime.

## 15. Security, CORS, and client identity

A reactive server does not replace security layers automatically.

- Reactive Spring Security uses `SecurityWebFilterChain`, not Servlet `SecurityFilterChain` as in MVC.
- CORS governs which origins browsers can share responses with; it is not authentication/authorization.
- If login sessions/cookies attach automatically, CSRF protection is required for state-changing methods; "WebFlux" does not make CSRF disappear.
- If a reverse proxy gateway sends `X-Forwarded-For` or `Forwarded`, trust forwarded headers only from trusted proxies; clients can spoof headers if ingress does not strip/validate them.
- Rate-limit by trusted principal/tenant and resource consumption, not solely by source IP.
- Request body limits, WebSocket/SSE limits, idle timeouts, and HTTP/2 stream limits help defend against resource exhaustion.
- Never log raw bearer tokens, passwords, session cookies, or personal data in headers or payloads.
- TLS termination at a proxy changes where encryption/certs/ALPN terminate; instrument transport at the right layer.

### 15.1. Reactor Context and ThreadLocal

A reactive request can switch threads across operators. Never rely on ThreadLocal/MDC propagating across the chain in imperative fashion without proper context-propagation integration. Reactor `Context` travels with the subscriber; reactive Spring Security provides the corresponding context mechanisms.

Example:

```java
Mono<String> trace =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "absent")))
        .contextWrite(Context.of("traceId", "req-001"));
```

This is an illustrative snippet needing `reactor.util.context.Context`. Never inject an unverified principal from a request header into Context and treat it as authenticated.

## 16. Debugging by symptom

| Symptom | Likely cause | Check step |
| --- | --- | --- |
| WebFlux shows many pending requests | Slow downstream, full pool, retry storms | HTTP client pool, downstream p95, pending queues |
| Low CPU yet high p99 latency | Blocking waits or network timeouts | Thread dumps, event-loop lag, client connect/response timeouts |
| One blocking handler slows many APIs | Event-loop blocking | Search for `block()`, `Thread.sleep`, JDBC, sync HTTP |
| `DataBufferLimitException` | Codec aggregation exceeded max-in-memory | Body format, codec limit, streaming strategy |
| Netty direct memory grows | Unreleased buffers / heavy traffic | Memory metrics, buffer ownership, leak detection |
| Connection refused | Server failed to bind host/port or backend dead | Startup logs, listeners, LB target |
| Many `PrematureCloseException`s | Client/remote/proxy closed early, overload/timeouts | Connect, maxIdleTime, LB idle, retries |
| WebClient pending acquire timeout | Outbound pool saturated | Active/idle/pending counts, remote response times |
| SSE drops after one minute | Proxy idle/read timeout or missing heartbeat | Reverse proxy/LB, heartbeat, cancellation |
| HTTP/2 falls back to HTTP/1.1 | ALPN/TLS/proxy/runtime not negotiated | curl `--http2`, server config, TLS chain |
| Servlet security filter not running on Netty | Running WebFlux reactive stack | Use SecurityWebFilterChain |
| WebFlux controller runs under DispatcherServlet | Boot selected Servlet/MVC due to mixed dependencies | Check starters/web-application-type |
| Returning Flux yet client does not receive items immediately | JSON array buffering/content negotiation | SSE/NDJSON media types and codecs |
| Test expects a fixed thread | Scheduler/Netty implementation varies | Assert API contracts; measure threads separately |
| Gateway returns 504 while app keeps running | Gateway timed out before business completion | End-to-end deadlines, cancellation, idempotency |
| OOM despite few event-loop threads | Many concurrent buffers/pending queues | Heap/direct memory, body sizes, backpressure |
| `Mono.just(...)` blocks immediately in controller | Argument to `just` is evaluated eagerly | `Mono.defer`/`fromCallable` + suitable scheduler |
| Reactor `.block()` throws IllegalStateException | Executed on non-blocking thread | Use composition/flatMap/WebClient |

### 16.1. Five-step investigation workflow

1. Confirm whether the app is **reactive or Servlet** (dependencies, logs, WebApplicationType, handler/filter types).
2. Confirm whether requests traverse a **proxy/CDN** before Netty/Tomcat; check protocol, TLS, and idle timeouts.
3. Separate inbound server connections from outbound WebClient connection pools.
4. Locate blocking calls and inspect event-loop lag, queues, and downstream latencies.
5. Measure response sizes, codec buffering, cancellations, and per-route p95/p99 before changing configs or frameworks.

## 17. Common mistakes: separating layers to avoid misguided optimizations

| Misconception | What is wrong | Correct understanding |
| --- | --- | --- |
| "One TCP connection = one Servlet thread" | Keep-alive and connectors do not pin threads forever | Workers are normally tied to request processing |
| "WebFlux uses only one thread for all clients" | There are multiple event loops/schedulers | One event loop serves many channels; count depends on runtime |
| "Netty is Spring WebFlux" | Netty is just a transport/server runtime | WebFlux has its framework pipeline and server adapters |
| "WebFlux requires Netty" | Tomcat/Jetty/Servlet adapters exist | Boot Netty is merely the default |
| "Tomcat is blocking TCP so it cannot run WebFlux" | Tomcat has async/non-blocking I/O | WebFlux provides a non-blocking bridge |
| "Async MVC is the same as WebFlux" | HTTP contracts/execution differ | Servlet async still runs through DispatcherServlet |
| "Mono brings its own thread" | Mono describes a publisher | Schedulers/sources govern execution |
| "Mono.fromCallable already solves blocking" | It is lazy, not auto-offloaded | Use boundedElastic or a non-blocking driver |
| "Thread.sleep in Netty is harmless" | Starves other channels on the same loop | Never block the loop |
| "Returning Flux streams immediately" | JSON codecs may buffer/aggregate | Pick SSE/NDJSON with the right media type |
| "Unbounded Flux buffer still has backpressure" | Buffers can exhaust heap | Use bounded queues / rate limits |
| "HTTP/2 means one request per connection" | HTTP/2 multiplexes streams | Connections and requests are distinct |
| "Inbound Netty pool is the WebClient pool" | Server and client roles differ | Manage separately |
| "ConnectionProvider default is always 500" | Defaults depend on Reactor Netty version | Check effective config/metrics |
| "HTTP timeout cancels all remote side effects" | Remote server may already have executed | Idempotency and deadlines |
| "Cancellation always triggers onComplete" | Cancel differs from completion | Use doFinally/usingWhen |
| "Enabling HTTP/2 only needs one property" | Also depends on TLS/ALPN/server/proxy/client | Verify negotiated protocol |
| "Few threads means low memory" | Buffers/channels still use memory | Budget heap, direct memory, and fd limits |
| "WebFlux is secure automatically" | Still needs auth/authz/CSRF/CORS | Configure SecurityWebFilterChain |
| "CORS headers are authentication credentials" | CORS is a browser policy | Authentication comes from credentials |
| "SSE that already emitted events can switch status to 500" | Response already committed | Use protocol error event / close stream |
| "Must create a new WebClient per request" | Loses connection reuse, spikes resources | Reuse managed clients |
| "Add MVC starter to use annotations" | Boot may pick the Servlet stack | Use only the WebFlux starter for reactive apps |
| "One microbenchmark proves reactive beats everything" | Ignores workload/configuration | Load-test and measure bottlenecks |
| "Every library in WebFlux is non-blocking" | JDBC/JPA/file APIs can block | Audit every downstream dependency |

## 18. Checklist for real systems

Before deploying WebFlux/Netty to production, verify:

1. **Application type**: genuinely Spring Boot reactive web app, no accidental MVC mix.
2. **Runtime**: Reactor Netty/Tomcat/Jetty selected intentionally per dependencies and requirements.
3. **Inbound limits**: max connections/idle timeouts/request body limits, HTTP/2 streams, and proxy budgets.
4. **Outbound pools**: max active/idle/pending, acquire/connect/response timeouts, ownership, and disposal.
5. **Downstream APIs**: WebClient, R2DBC, reactive messaging, or bounded blocking bridges.
6. **Event loops**: zero `block()`, `Thread.sleep`, sync DB/HTTP directly in handlers.
7. **Bounded resources**: queues, buffers, SSE clients, infinite Fluxes, concurrency/bulkheads.
8. **Backpressure**: verify publisher producers genuinely honor demand and cancellation.
9. **HTTP semantics**: 204, 404, errors before vs after response commit, JSON vs SSE.
10. **Auth/security**: SecurityWebFilterChain, permissions/ownership, CORS, CSRF, TLS.
11. **Reactive Context**: trace/principal propagation across thread switches.
12. **Observability**: inbound requests/connections, outbound pools, event-loop lag, direct memory, GC.
13. **Graceful shutdown**: app/sidecar/LB draining + long-lived streams and Kubernetes termination grace.
14. **Testing**: WebTestClient unit/integration, real HTTP/2/proxies, load tests, and client disconnects.
15. **Decision rationale**: driven by concurrent I/O/streaming needs rather than stylistic preference alone?

## 19. Self-check questions

**1.** Is "one connection always uses one worker thread" accurate?  
**Answer:** No; transport/socket readiness and request workers are not 1:1. Servlet workers normally tie to request processing, not permanently to TCP keep-alive.

**2.** How many requests can HTTP/2 carry over one connection?  
**Answer:** Multiple logical streams per protocol/settings; not limited to one request.

**3.** What is a Netty Channel?  
**Answer:** An abstraction for an I/O channel/endpoint with pipeline handlers, managed by an EventLoop.

**4.** Can one EventLoop serve multiple channels?  
**Answer:** Yes, that is the core model.

**5.** What server does Spring Boot WebFlux use by default?  
**Answer:** Reactor Netty when keeping the default dependencies of `spring-boot-starter-webflux`.

**6.** Can WebFlux run on Tomcat?  
**Answer:** Yes, via the appropriate reactive/non-blocking HTTP adapter on a Servlet container.

**7.** Why can synchronous MVC consume many request workers?  
**Answer:** Blocking service calls hold workers while waiting.

**8.** Does MVC Callable free the Servlet thread?  
**Answer:** Yes, yet blocking logic still holds an AsyncTaskExecutor worker.

**9.** Does returning `Mono<String>` make a JDBC call non-blocking?  
**Answer:** No. The downstream API can still block.

**10.** Why is `Mono.just(blockingCall())` dangerous?  
**Answer:** `blockingCall` executes eagerly at assembly time, potentially on the event loop.

**11.** Does boundedElastic make JDBC non-blocking?  
**Answer:** No; it only offloads the blocking wait to a more appropriate worker pool.

**12.** What type does `HttpHandler` return in Spring WebFlux?  
**Answer:** `Mono<Void>` representing completion of the HTTP exchange.

**13.** Which model does `ServerWebExchange` belong to?  
**Answer:** Spring WebFlux's `WebHandler` abstraction.

**14.** Are `DispatcherHandler` and `DispatcherServlet` identical?  
**Answer:** No; WebFlux uses DispatcherHandler/reactive contracts, while MVC uses DispatcherServlet/Servlet APIs.

**15.** Does `Flux<T>` always flush every item over HTTP immediately?  
**Answer:** No; it depends on HTTP codecs/media types. SSE/NDJSON provide appropriate streaming semantics.

**16.** Is Reactive Streams backpressure one-to-one with TCP flow control?  
**Answer:** No; they interact yet operate at different layers.

**17.** Are the inbound server connection pool and WebClient pool the same?  
**Answer:** No; the server accepts inbound connections, while HttpClient manages outbound connections.

**18.** What does `pendingAcquireTimeout` in WebClient refer to?  
**Answer:** Time spent waiting to acquire a connection from the outbound pool.

**19.** Does an HTTP client timeout guarantee the remote transaction rolled back?  
**Answer:** No; the remote server may already have executed side effects.

**20.** Why is WebFlux on Tomcat still reactive?  
**Answer:** The WebFlux programming contract is adapted onto Servlet non-blocking I/O; the runtime does not turn the app into MVC.

**21.** Does enabling both WebFlux and MVC starters always select reactive?  
**Answer:** No; Spring Boot typically prefers MVC when both are present.

**22.** With many SSE clients, if only a few threads are used, are all other resources free?  
**Answer:** No; connections, buffers, keep-alive state, file descriptors, and subscriber memory still cost resources.

**23.** If a response has already emitted SSE events and then errors, can HTTP 200 switch to 500?  
**Answer:** Usually not after commit; you must use an error event/close protocol.

**24.** Why must WebClient be reused?  
**Answer:** To leverage connection pools/resources and avoid repeated connection/TLS setup and resource pressure.

**25.** When is using WebFlux justified?  
**Answer:** When the stack has concurrent I/O/streaming needs and reactive downstream dependencies, verified against real workloads rather than framework hype.

## 20. Official documentation

- [Spring Framework 6.2 — Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): HttpHandler, WebHandler, server adapters, non-blocking I/O.
- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/new-framework.html): reactive concepts, contrast with MVC, servers.
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): mappings/adapters/result handlers.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): Reactor Netty default and choosing Tomcat/Jetty/Undertow, HTTP/2.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): Boot WebFlux auto-configuration.
- [Reactor Netty Reference — HTTP Server](https://projectreactor.io/docs/netty/1.1.26/reference/http-server.html): server, protocol configuration, observability.
- [Reactor Netty Reference — HTTP Client](https://projectreactor.io/docs/netty/1.1.26/reference/http-client.html): connection pooling, timeouts, reuse.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, threading, backpressure, and schedulers.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): reactive HTTP tests.
- [Reactive Streams Specification](https://www.reactive-streams.org/): Publisher/Subscriber/Subscription and demand.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): multiplexing streams over one connection.

**Final rule:** **A reactive server does not mean "one connection per thread", nor does it mean "no threads".** Reactor Netty gives event loops serving many connections; WebFlux uses the Publisher/non-blocking I/O contract to avoid holding workers purely for waiting. Servlet containers also support NIO and Servlet async, yet Spring MVC has a different programming model. To make WebFlux truly effective, you must master **inbound/outbound connections, blocking boundaries, event-loop scheduling, backpressure, timeouts, and resource lifecycles**, and measure against real workloads.
