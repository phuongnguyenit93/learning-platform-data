# Backpressure, Demand, and Boundaries Across the HTTP Protocol in Spring WebFlux

## 1. Why Does WebFlux Need Backpressure?

An API server or streaming producer can generate data faster than the receiver can process it:

```text
Data Source                     Consumer
20,000 events/second            300 events/second
         |                              ^
         v                              |
     [ QUEUE ? ] -----------------------+
         |
  Memory grows, latency rises, possible OOM
```

If the producer keeps generating without limit, data can accumulate in the heap, codec buffers, network stack, or internal queues; keeping every message in RAM can exhaust application memory. **Backpressure** is the receiver's ability to express **demand** so the sender produces/emits an appropriate amount.

In **Reactive Streams**, the central signal is `Subscription.request(n)`, where `n` is the **number of elements** downstream is ready to receive; upstream must not emit `onNext` beyond the demand granted to that subscriber. This is a contract at the **publisher/subscriber layer**, not an HTTP command automatically sent by a browser.

**Spring WebFlux** builds on reactive programming and non-blocking I/O to connect request/response bodies with `Publisher` sources. Reactor provides `Flux<T>` (0..N values) and `Mono<T>` (0..1 value) along with demand-shaping operators. However, end-to-end backpressure **only holds if every segment of the pipeline respects signals or handles overload with bounded limits**. An external data source pushing continuously, a blocking API, or a proxy buffering the whole response can break expectations of “low memory usage”.

This lesson is part of **WebFlux Foundations**, introducing:

- `Publisher`, `Subscriber`, `Subscription`, and `request(n)`.
- How demand flows in the **opposite direction** from data.
- `StepVerifier`/`BaseSubscriber` to control requests and observe `doOnRequest`.
- Operators `limitRate`, `buffer`, `flatMap`, `publishOn`, and `onBackpressureBuffer/Drop/Latest/Error`.
- Differences between cold sources and hot sources, handling slow consumers and sources that do not support demand.
- **Critical boundaries:** Reactive Streams demand, HTTP response streaming, TCP receive windows, HTTP/2 flow-control windows, proxy buffering, and browsers are all distinct mechanisms.
- Designing WebFlux NDJSON/SSE APIs, cancellation/timeouts, layered tests, and production observability.

Example baseline: **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Project Reactor 3.7.x, Reactor Netty**. The code does not use `spring-boot-starter-web` and does not mix Servlet MVC with WebFlux.

## 2. Reactive Streams Model: Two Directions of Information

Reactive Streams defines the core interfaces (in `org.reactivestreams`):

```java
interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}

interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T value);
    void onError(Throwable error);
    void onComplete();
}

interface Subscription {
    void request(long n);
    void cancel();
}
```

The snippet above shows **abbreviated signatures for learning**, not a Java file you should declare yourself. Important rules:

1. The Subscriber receives `onSubscribe(subscription)` before any data signals.
2. The Subscriber calls `request(n)` to grant the **number of elements** it can additionally receive; `n` must be **positive**. `request(0)` or negative values violate the contract and typically cause `onError`.
3. Total demand is cumulative; each `request(n)` does not create a new subscription.
4. Upstream sends `onNext` only within remaining demand; `onError` or `onComplete` terminates the stream.
5. `cancel()` signals that no more data is needed; cancel is not a promise to immediately abort an external HTTP request or database job already in progress.
6. Signals must be **serialized per the contract**; designing a publisher that arbitrarily calls `onNext` concurrently from multiple threads is invalid.

Opposite flow of data and demand:

```text
Publisher / Flux                     Subscriber
      |                                  |
      |<---- onSubscribe/subscription ---| (conceptually binds Subscription)
      |<----------- request(3) ---------|
      |------------ onNext(A) --------->|  2 left
      |------------ onNext(B) --------->|  1 left
      |------------ onNext(C) --------->|  0 left
      |                                  | no more requests:
      |       must wait for new demand  | cannot send onNext D
      |<----------- request(2) ---------|
      |------------ onNext(D) --------->|
      |------------ onNext(E) --------->|
      |----------- onComplete() ------->|
```

**Note:** `onSubscribe` is a signal from Publisher to Subscriber; the subscriber receives the `Subscription` first before calling request. The diagram merely illustrates the two opposing control/data flows.

### 2.1. “n” Is Item Count, Not Byte Count

With `Flux<Integer>`, `request(3)` allows three integers. With `Flux<Record>`, each record is one item that might be 100 bytes or 10 MB. With `Flux<DataBuffer>`, each item is a byte buffer of varying size.

Therefore:

- `request(10)` does **not** guarantee granting exactly 10 KB.
- `request(1)` is **not** synonymous with “read only 1 byte from TCP”.
- If each item is huge, item-count backpressure can still cause memory pressure.
- If `buffer(1000)` produces a `List<T>`, **one output item** can hold 1,000 source items.
- TCP windows measure **bytes** and buffer capacity, not Java object counts.

Design must measure **element size, queue size, bytes in-flight**, and throughput, not just demand counts.

### 2.2. `Long.MAX_VALUE` Is Unbounded Demand

Many convenience subscribe methods use effectively unlimited demand:

```java
Flux.range(1, 10).subscribe(System.out::println);
```

This is a fragment inside a Java class with the Reactor dependency; it is not a way to test per-element backpressure because lambda `subscribe` overloads typically request `Long.MAX_VALUE`. That suits small, fast streams, yet **does not prove a production consumer bounds demand**.

`block()` and `blockLast()` also consume eagerly/unboundedly on many code paths. On WebFlux's Netty event loop, **never call `block()`** to “wait” for reactive results, as it can block the I/O thread and severely degrade throughput or throw an exception.

## 3. Java Example: Observing Demand Without HTTP

To learn backpressure, first isolate HTTP from the problem so you can clearly see `request(n)`. A reliable approach is `StepVerifier` with an **initial request of 0**.

### 3.1. StepVerifier Granting Batches

```java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicInteger produced = new AtomicInteger();

Flux<Integer> source = Flux.range(1, 5)
        .doOnNext(value -> produced.incrementAndGet());

StepVerifier.create(source, 0)
        .expectSubscription()
        .then(() -> {
            if (produced.get() != 0) {
                throw new AssertionError(
                        "Source emitted without demand");
            }
        })
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();
```

This is a **Java fragment inside a test method**, requiring `reactor-test` in test dependencies. `StepVerifier.create(source, 0)` means **granting zero initial demand**, *not* calling `Subscription.request(0)` (an invalid operation in Reactive Streams). After `thenRequest(2)`, the subscriber receives exactly two items; after `thenRequest(3)`, it receives the remaining three items.

If the source honors demand, no `onNext` occurs before the first request. `Flux.range` is a cold publisher that respects pull demand, making it ideal for observing the mechanism.

### 3.2. Manual Control with BaseSubscriber

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux.range(1, 6).subscribe(
    new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(2);
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println("got=" + value);
            if (value == 2) {
                request(2);
            }
            if (value == 4) {
                cancel();
            }
        }

        @Override
        protected void hookOnCancel() {
            System.out.println("cancelled");
        }
    });
```

This is a fragment inside a Java method with Reactor Core. With synchronous `Flux.range` and no added scheduler, expected values are 1, 2, 3, 4 followed by cancel; values 5 and 6 are **never requested**. Sample deterministic output:

```text
got=1
got=2
got=3
got=4
cancelled
```

In pipelines using multiple schedulers, do not rely on log ordering across threads to infer request boundaries without knowing scheduling and concurrency.

**`cancel()` is a cancellation signal on the Subscription**, not equivalent to rolling back a committed transaction or recalling a message already sent to Kafka.

## 4. Demand Does Not Necessarily Pass Unchanged Through Operators

In practice, downstream `request(3)` can cause upstream to see a request **different from 3** because many operators prefetch, batch, or manage multiple inner publishers.

```text
HTTP writer requests 1 record
       |
       v
map          -> usually 1:1 demand
       |
buffer(10)   -> needs up to 10 upstream records for 1 List<Record>
       |
flatMap(...) -> has its own concurrency and prefetch
       |
publishOn   -> queue + prefetch, replenishment
       |
Data source receives transformed demand
```

### 4.1. `map` / `filter`

- `map` typically transforms one input to one output, making demand straightforward.
- `filter` can drop items. To deliver **n valid outputs** downstream, it may need to request **more than n source items**.
- `take(n)` limits the **total items downstream receives** and cancels upstream once the desired count is reached (check overload and version semantics).
- `buffer(k)` groups k source items into one `List<T>`; downstream demand is measured in **lists**, not the elements inside.

Example:

```java
Flux<List<Integer>> windows =
        Flux.range(1, 10).buffer(5);
```

If the subscriber requests **1**, the pipeline may need to read **5 numbers** to emit one list `[1,2,3,4,5]`. This is not a backpressure bug; it is unit transformation of demand.

### 4.2. `flatMap` and Concurrency

```java
Flux<Result> results = keys
        .flatMap(
            key -> repository.findByKey(key),
            8,   // concurrency: max concurrent inner publishers
            16); // prefetch: request-ahead per inner publisher
```

This is a **fragment**, assuming `keys` is a Flux and the reactive repository returns an appropriate Publisher/Mono. `flatMap` can request data from multiple inner sequences concurrently; `concurrency=8` and `prefetch=16` cap those operator parameters, **not** total heap used across the whole request.

Do not derive an exact memory upper bound merely by multiplying 8×16: items vary in size, plus there are queues, codecs, outbound buffers, and external sources. When result ordering matters, `concatMap` or `flatMapSequential` with their respective trade-offs may fit.

### 4.3. `publishOn` Creates a Scheduler and Queue Boundary

```java
Flux<Data> processed = source
        .publishOn(Schedulers.parallel(), 32)
        .map(this::transform);
```

The fragment assumes `source`, `Data`, and `transform` exist. `publishOn` shifts downstream processing onto the specified scheduler and maintains an internal `prefetch`. It may issue an initial upstream `request(32)` even when the final consumer is only observing a few items.

**Never use `publishOn(Schedulers.parallel())` for blocking JDBC, `Thread.sleep`, blocking file I/O, or blocking HTTP clients.** Those tasks need genuine non-blocking systems or isolation on `boundedElastic` by design.

## 5. `limitRate`: Splitting Large Demand into Batches, Not Capping Total Items

A subscriber (including many framework-managed components) may request a huge or unbounded amount. `limitRate(int)` makes upstream see demand in **batches**.

```java
Flux<Integer> limited = Flux.range(1, 100)
        .doOnRequest(n ->
                System.out.println("upstream requested=" + n))
        .limitRate(10);
```

If downstream requests 100, upstream receives batched requests with a high-tide of 10 and the default **75% replenishment** mechanism. That means logs will **not** necessarily show ten consecutive `request(10)` lines: once 75% of the buffer is consumed, the operator can request more early.

To illustrate strict batches with low-tide=0:

```java
Flux<Integer> strictBatches = Flux.range(1, 100)
        .doOnRequest(n ->
                System.out.println("requested upstream=" + n))
        .limitRate(10, 0);
```

`limitRate(10, 0)` sends demand in chunks of at most 10 before requesting the next batch; it can still deliver **all 100 items** as downstream keeps requesting. It is **not** equivalent to `take(10)`, is not time-based rate limiting like “10 requests per second”, and is not an HTTP rate limiter blocking spam.

### 5.1. Three Very Easily Confused Concepts

| API | Primary Effect | What It Does Not Mean |
| --- | --- | --- |
| `limitRate(10)` | Splits downstream demand before upstream sees it | Does not cap total output to 10 |
| `take(10)` | Takes at most 10 items then completes/cancels | Does not guarantee 10 HTTP bytes/chunks |
| `delayElements(Duration.ofMillis(100))` | Delays element emission over time via a scheduler | Does not guarantee rate limiting for any hot upstream |
| `timeout(Duration.ofSeconds(5))` | Errors or falls back if no signal arrives on time | Does not cap concurrent connections |
| `flatMap(mapper,8,16)` | Controls inner concurrency/prefetch | Not an application-wide request quota |

When you need rate limiting for **requests per client/tenant**, use a gateway, security/rate limiter, or server-side mechanism with shared state. `limitRate` is a reactive sequence demand-shaping operator, not DDoS protection for public endpoints.

## 6. Cold Publishers and Hot Publishers

### 6.1. Cold Source

A publisher like `Flux.range`, `Flux.defer`, or `Mono.fromCallable` typically produces independently per subscription. Cold sources can naturally honor request demand when implemented properly.

```java
Flux<Integer> cold = Flux.range(1, 5)
        .doOnSubscribe(s -> System.out.println("new subscriber"));
```

Two subscribers typically receive two independent data runs. If the source is an R2DBC query or reactive HTTP client, a new subscription can initiate new I/O; mind cancellation and connection/resource cleanup.

### 6.2. Hot Source

A sensor, WebSocket incoming stream, Kafka consumer, or callback listener may produce data **independently** of current subscribers. Even without downstream demand, the external producer may keep emitting.

```text
Hot source:  event event event event event ...
Subscriber: requests 1 then pauses 5 seconds
              |
              v
  Must choose: bounded buffer, drop, latest,
             signal overflow, slow external upstream,
             or disconnect subscriber
```

`Flux.interval` is also an example of a clock-driven source; if a subscriber falls behind, it **can signal an overflow error** instead of silently queueing forever. Do not assume every hot publisher automatically buffers all messages.

An external source API with **pause/resume** or backpressure support (e.g., a demand-aware cursor) is easier to manage than a push-only callback source. For sources that cannot slow down, an **explicit overflow strategy** is mandatory.

## 7. `onBackpressure...` Strategies

Reactor provides operators for handling sources whose emission pressure is incompatible with downstream.

| Operator | When Downstream Lacks Demand | Best Suited For | Risks |
| --- | --- | --- | --- |
| `onBackpressureBuffer()` | Queues backlog | Temporary slowdowns | Unbounded variant can cause OOM |
| `onBackpressureBuffer(maxSize,...)` | Holds up to cap, then overflows per strategy | Bounded delay tolerance | Requires policy, metrics, and error handling |
| `onBackpressureDrop()` | Discards values that cannot be delivered immediately | Telemetry where sampling loss is acceptable | Data loss; never use for transactions |
| `onBackpressureLatest()` | Keeps only the newest value instead of all values | Progress %, live gauges | Skips intermediate states |
| `onBackpressureError()` | Emits overflow error | Streams needing integrity, fail-fast | Clients need retry/recovery |
| `limitRate` | Splits demand sent upstream to demand-aware sources | Cursors/DB paging | Does not handle external sources pushing regardless of demand |

### 7.1. Bounded Buffer — Must Plan for When It Fills

```java
Flux<Event> buffered = hotEvents
        .onBackpressureBuffer(
            256,
            event -> metrics.recordOverflow());
```

This is a fragment; `Event`, `hotEvents`, and `metrics` are application-supplied. This overload has finite capacity and an overflow callback; when full, it can terminate with an overflow error per API semantics. **Never use an unbounded buffer** for arbitrary topics or unlimited users, especially with sensitive data.

You must specify:

- Max backlog in **items and bytes**.
- Action when full: error/disconnect, drop oldest/newest, or coalesce.
- Deadline/TTL for stale events.
- Who cleans up buffered data when a client cancels.
- Metrics for backlog size/age/overflow counts.
- The difference between a **global buffer** and a **per-subscriber** buffer, since 10,000 subscribers × 256 items can be huge.

### 7.2. Do Not Use Drop/Latest Carelessly

```java
Flux<Progress> latestProgress = updates
        .onBackpressureLatest();
```

Appropriate for dashboards caring only about the **latest %**, but inappropriate for balance changes, payment events, security audits, or data where dropping one message alters the outcome.

```java
Flux<Telemetry> sampled = telemetry
        .onBackpressureDrop(value ->
                metrics.incrementDropped());
```

This fragment accepts losing telemetry samples. If `Telemetry` must store every data point accurately, never drop; instead use a broker/durable log, reduce source rate, or decouple ingest from serving.

### 7.3. `onBackpressureError` and Already-Committed HTTP Responses

A `Flux` being written by WebFlux to an HTTP response may encounter `onError` due to overflow. If HTTP headers/body have already started streaming, the server **cannot reliably change status 200 to 500** or send an intact JSON error envelope. The client may observe an aborted stream.

SSE needs a protocol/reconnect/replay policy; NDJSON needs explicit incomplete-stream/cancel semantics. Do not assume an operator error automatically produces `HTTP 429`. **429 Too Many Requests** is a separate HTTP rate-limiting/application policy that must be designed explicitly before committing the response.

## 8. How Spring WebFlux Connects Reactive Streams to HTTP

Spring WebFlux uses `HttpHandler`, `WebHandler`, HTTP codecs (`HttpMessageReader`, `HttpMessageWriter`), reactive server adapters, and `DataBuffer` to process bodies non-blockingly with backpressure.

```text
Business Flux<Item>
    |
    | demand coordinated via Reactor Publisher/Subscriber
    v
JSON/SSE encoder
    |
    v
Flux<DataBuffer>
    |
    v
ServerHttpResponse / HttpHandler adapter
    |
    v
Reactor Netty / TCP socket output
    |
    v
HTTP/1.1 chunks or HTTP/2 DATA frames
    |
    v
Browser / WebClient / Gateway
```

When the network slows down, the server adapter can use non-blocking write readiness and buffer watermarks to throttle how many buffers are pulled from the pipeline. Still, you must distinguish:

- **Reactor demand:** count of `T` or `DataBuffer` via `request(n)` inside the JVM.
- **Netty buffer/write readiness:** event-loop state, outbound queue, and writable watermarks.
- **TCP flow control:** receive window in **bytes**; TCP endpoints regulate byte streams via ACKs/window updates.
- **HTTP/2 flow control:** connection-level and stream-level windows for **DATA bytes**, not `Flux<Item>` `request(n)`.
- **HTTP/1.1 chunked transfer:** framing the body without Content-Length; chunk boundaries do not map 1:1 to `onNext`.
- **HTTP client application:** browsers read/parse payloads at their own pace; JavaScript does not receive a `Subscription` from the server over standard HTTP.

Key takeaway: **there is no standard HTTP header equivalent to “request(3) Java objects”** sent by a browser after every three SSE messages. WebFlux bridges reactive demand and read/write readiness at the HTTP adapter, yet the mapping involves buffers/codecs and is not “one item equals one TCP packet”.

### 8.1. Example: Which Layer Bottlenecks the Speed?

Suppose `Flux` generates 1,000 records/s and the browser processes 100 records/s:

1. If the browser/client cannot read bytes fast enough, receive buffers and TCP/HTTP2 windows can throttle transmission.
2. Server write queues may become unwritable, causing the HTTP adapter to lower demand or defer writes.
3. A few items still sit in codec/operator prefetch/network buffers.
4. If the source is cold and demand-aware, it can eventually slow down production.
5. If a hot source from a broker keeps pushing unboundedly, **this layer still needs a queue/drop/pause strategy**.
6. If a CDN reads the entire response rapidly and buffers it for the browser, the origin **no longer sees the slow browser in the same way**.

Therefore, test **end-to-end** on the real topology, rather than looking only at `doOnRequest` in a controller.

### 8.2. Streaming Media Types Determine Framing

| Media Type | Body Structure | Expected Streaming Behavior |
| --- | --- | --- |
| `application/json` | One complete JSON value/array | A `Flux<T>` may be assembled into an array, potentially buffered by the encoder |
| `application/x-ndjson` | One JSON object per line | Can encode each element and stream incrementally |
| `text/event-stream` | SSE frames `id/event/data` + blank line | Streams events over time; browser EventSource |
| `application/octet-stream` | Raw bytes | Uses `Flux<DataBuffer>`/Resource at the appropriate layer |
| `text/plain` | Text bytes; no built-in message delimiter | Needs explicit framing when emitting multiple items |

**A Flux does not automatically ensure an HTTP response streams every event immediately.** Media type, codecs, flush semantics, proxy buffering, and client parsers all affect it.

With `application/json`, WebFlux may need to collect items into a JSON array; with `application/x-ndjson` or SSE, message writers usually stream per item/event. If observable low latency is required, measure actual time-to-first-byte/first-frame arrival.

## 9. NDJSON and SSE: Same Flux, Different Clients

### 9.1. NDJSON

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"id":1,"name":"item-1"}
{"id":2,"name":"item-2"}
{"id":3,"name":"item-3"}
```

Each line is a valid JSON value. Clients can parse line by line. If the request cancels after the second line, the stream may contain only two lines — the protocol must decide whether a **partial result** is valid.

### 9.2. Server-Sent Events

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream

id: 1
event: progress
data: {"seq":1,"state":"running"}

id: 2
event: done
data: {"seq":2,"state":"complete"}

```

SSE is a **server → browser** protocol over HTTP GET. Browser `EventSource` understands `data`, `id`, and `event`, and reconnects automatically in many cases. However, `Last-Event-ID` **does not automatically provide durable replay on the server**; if zero event loss is required, you must store an event log, assign IDs, and implement resumption.

**SSE does not mean end-to-end Reactive Streams across the browser.** `EventSource` has no `request(5)` API controlling upstream Reactor directly. The browser can close the connection (`source.close()`) and the network stack exerts byte-level backpressure, yet application-level demand does not translate 1:1 into Reactive Streams request signals.

### 9.3. Heartbeats

WebFlux docs recommend sending periodic data/heartbeats to detect disconnected clients sooner, because an idle connection does not always report cancellation immediately. SSE can send a comment:

```text
: keep-alive

```

Heartbeats must be shorter than reverse-proxy/gateway idle timeouts and must not create unbounded loops or queues per subscriber.

## 10. Runnable Example: Spring Boot 3.5 WebFlux + Java 17

The demo includes:

1. `GET /api/items` returns five items as a single JSON array.
2. `GET /api/items.ndjson` returns five NDJSON items and logs upstream demand.
3. `GET /api/events` emits three ordered SSE events, then completes; clients can observe each event.
4. No DB, network broker, or blocking I/O is used so the example stays focused on Reactive Streams and HTTP framing.
5. Tests include `StepVerifier` checking demand without HTTP and `WebTestClient` hitting a real server to verify NDJSON/SSE.

### 10.1. Creating the Project

Choose **Spring Boot 3.5.x**, Java 17, Gradle or Maven, and the **Spring Reactive Web (WebFlux)** dependency. In a Boot project with Gradle plugin/BOM/Java toolchain configured, use:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` fragment**, not the full build file. `spring-boot-starter-webflux` uses Reactor Netty by default when running the reactive stack. **Do not add `spring-boot-starter-web` just to use `@RestController`**: when both MVC and WebFlux starters are present, Boot 3.x normally selects MVC as the default web application type, which completely changes the demo away from its goal.

### 10.2. Complete Java Application

Create `src/main/java/demo/backpressure/BackpressureApplication.java`:

```java
package demo.backpressure;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@SpringBootApplication
public class BackpressureApplication {

    public static void main(String[] args) {
        SpringApplication.run(BackpressureApplication.class, args);
    }
}

record Item(int id, String name) {}

record Progress(long seq, String state) {}

@RestController
@RequestMapping("/api")
class BackpressureController {
    private static final Logger log =
            LoggerFactory.getLogger(BackpressureController.class);

    private Flux<Item> items() {
        return Flux.range(1, 5)
                .map(id -> new Item(id, "item-" + id));
    }

    @GetMapping(
            path = "/items",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Flux<Item> jsonItems() {
        return items();
    }

    @GetMapping(
            path = "/items.ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<Item> ndjsonItems() {
        return items()
                .doOnRequest(n ->
                        log.info("items_upstream_demand={}", n))
                .limitRate(2)
                .doOnCancel(() ->
                        log.info("items_stream_cancelled"));
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<Progress>> events() {
        return Flux.range(1, 3)
                .delayElements(Duration.ofMillis(150))
                .map(seq ->
                        ServerSentEvent.<Progress>builder()
                            .id(Integer.toString(seq))
                            .event(seq == 3
                                    ? "done" : "progress")
                            .data(new Progress(seq,
                                    seq == 3
                                        ? "complete" : "running"))
                            .build())
                .doOnCancel(() ->
                        log.info("sse_stream_cancelled"));
    }
}
```

**Valid Java 17 + Boot 3.5 WebFlux code:** the file has one `public` class `BackpressureApplication`; package-private records and controller in the same package are picked up by component scan. `Flux.range` is cold, finite, and backpressure-aware. There is no `Thread.sleep` or `block()` in handlers, nor manual `subscribe()` inside the controller; **WebFlux owns the subscription** while writing the HTTP response.

**`limitRate(2)` is applied after `doOnRequest`**, so the upstream logger can observe batched requests instead of concluding an HTTP client literally sent `request(2)`. Never hardcode the exact request log sequence, since low-tide replenishment and codecs/servers can vary.

**The SSE demo emits only three events** so tests remain finite. `delayElements` creates observable spacing between events, yet is not a production rate limiter for uncooperative hot sources. If the client closes early, `doOnCancel` can log when the cancel signal reaches the subscription. Do not claim a closed TCP socket triggers the callback instantaneously when the server is no longer writing.

### 10.3. Running curl

```bash
./gradlew bootRun
```

**JSON array:**

```bash
curl -i -H 'Accept: application/json' \
  'http://localhost:8080/api/items'
```

Expected body (whitespace-independent):

```json
[
  {"id":1,"name":"item-1"},
  {"id":2,"name":"item-2"},
  {"id":3,"name":"item-3"},
  {"id":4,"name":"item-4"},
  {"id":5,"name":"item-5"}
]
```

**NDJSON:**

```bash
curl -N -i -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/items.ndjson'
```

Expected body:

```text
{"id":1,"name":"item-1"}
{"id":2,"name":"item-2"}
{"id":3,"name":"item-3"}
{"id":4,"name":"item-4"}
{"id":5,"name":"item-5"}
```

**SSE:**

```bash
curl -N -i -H 'Accept: text/event-stream' \
  'http://localhost:8080/api/events'
```

Body format:

```text
id:1
event:progress
data:{"seq":1,"state":"running"}

id:2
event:progress
data:{"seq":2,"state":"running"}

id:3
event:done
data:{"seq":3,"state":"complete"}

```

There may be spaces after `:` or different field ordering depending on the encoder. What matters are event ID, type, data, and separating blank lines. Because the example is finite, the connection closes after the third event. A browser `EventSource` may **reconnect automatically**; demo clients wanting to stop must handle the `done` event and call `source.close()`.

`curl -N` disables **curl output** buffering; it does not force origins, proxies, or CDNs to flush every element.

## 11. Testing Properly at Two Layers: Reactive Streams and HTTP

### 11.1. Demand Unit Tests with StepVerifier

This test isolates Reactor core, verifying that a cold source **emits no elements before demand is granted**, then emits cleanly in batches.

Create `src/test/java/demo/backpressure/BackpressureApplicationTests.java` with the test class below.

### 11.2. HTTP Integration Tests with WebTestClient

`WebTestClient` runs against a real server when `@SpringBootTest(webEnvironment=RANDOM_PORT)` is used. It decodes response bodies by media type; the tests below verify statuses and item/event contents, **without directly inferring TCP-level `request(n)`**.

```java
package demo.backpressure;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BackpressureApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void coldSourceWaitsForRequests() {
        AtomicInteger produced = new AtomicInteger();

        Flux<Integer> source = Flux.range(1, 5)
                .doOnNext(x -> produced.incrementAndGet());

        StepVerifier.create(source, 0)
                .expectSubscription()
                .then(() -> assertEquals(0, produced.get()))
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();

        assertEquals(5, produced.get());
    }

    @Test
    void ndjsonStreamsFiveItemsThroughHttp() {
        Flux<Item> body = client.get()
                .uri("/api/items.ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_NDJSON)
                .returnResult(Item.class)
                .getResponseBody();

        StepVerifier.create(body)
                .expectNextMatches(item ->
                        item.id() == 1
                                && "item-1".equals(item.name()))
                .expectNextCount(3)
                .expectNextMatches(item ->
                        item.id() == 5
                                && "item-5".equals(item.name()))
                .verifyComplete();
    }

    @Test
    void sseCarriesTypedEventsAndCompletes() {
        Flux<ServerSentEvent<Progress>> body =
                client.get()
                    .uri("/api/events")
                    .accept(MediaType.TEXT_EVENT_STREAM)
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(
                            MediaType.TEXT_EVENT_STREAM)
                    .returnResult(
                        new ParameterizedTypeReference<
                            ServerSentEvent<Progress>>() {})
                    .getResponseBody();

        StepVerifier.create(body)
                .expectNextMatches(event ->
                        "progress".equals(event.event())
                            && "1".equals(event.id())
                            && event.data() != null
                            && event.data().seq() == 1)
                .expectNextMatches(event ->
                        "progress".equals(event.event())
                            && "2".equals(event.id())
                            && event.data() != null
                            && event.data().seq() == 2)
                .expectNextMatches(event ->
                        "done".equals(event.event())
                            && "3".equals(event.id())
                            && event.data() != null
                            && "complete".equals(
                                    event.data().state()))
                .verifyComplete();
    }
}
```

Run:

```bash
./gradlew test
```

All three tests are **designed to pass** on Boot 3.5 WebFlux/Java 17 with the source from section 10. This is **an expectation from code and documentation review**, **not a Gradle execution log**. The tests use `WebTestClient` over **RANDOM_PORT** so HTTP codecs and Reactor Netty participate, unlike mock `bindToController` tests.

**Key takeaway:** `coldSourceWaitsForRequests` directly proves Reactive Streams demand. The two HTTP tests verify serialization, framing, and event contents. They **cannot verify “the HTTP client sent `request(5)` to the server”**, because no such signal exists on the wire protocol.

## 12. Observing request(n) in Pipelines, in the Right Place and for the Right Purpose

`doOnRequest` records demand passing a specific point:

```java
Flux<Integer> observable = Flux.range(1, 100)
        .doOnRequest(n ->
                log.debug("upstream_request_count={}", n))
        .publishOn(Schedulers.parallel(), 16)
        .filter(n -> n % 2 == 0)
        .limitRate(4);
```

A final client requesting 4 values **does not guarantee** logging upstream `request(4)`. `publishOn` has prefetch 16; `filter` skips odd items; `limitRate` adds batching logic.

Moving `doOnRequest` **after** `publishOn` may log different numbers. Therefore, when debugging:

- Place `doOnRequest` on both sides of a suspect operator, tagging each stage clearly.
- Use `doOnNext`, `doOnCancel`, and `doFinally` to observe terminal/cleanup signals.
- For detailed signal debugging in dev/test, use Reactor `log()` sparingly; never log every item under high production traffic.
- Never log raw payloads, auth tokens, or PII into telemetry.
- Track **queue sizes and bytes**, not merely `request(n)` counts.
- Use Reactor metrics/Micrometer or OpenTelemetry matching your Boot setup; operator labels must have low cardinality.

### `doOnRequest` May Receive `Long.MAX_VALUE` While the System Still Runs Fine

Downstream stages of many operators/frameworks may request unbounded demand and internally rely on write readiness/queues. That alone does not prove the whole application lacks backpressure; inspect the entire chain, buffering capacity, and protocol adapters. Conversely, logging `request(1)` does not prove a real client finished processing the previous item either.

## 13. Backpressure and Request Body Uploads

Backpressure is not just for **responses**. When WebFlux receives an HTTP request body, the adapter/`HttpMessageReader` can supply `Flux<DataBuffer>` or decode into a publisher:

```text
Client POST streamed body
    |
    v
TCP receive buffer / HTTP/2 flow-control
    |
    v
Reactor Netty inbound byte buffers
    |
    v
Flux<DataBuffer> -> HttpMessageReader/Decoder
    |
    v
Application processing & bounded storage
```

Yet boundaries exist:

- If a controller calls `bodyToMono(String.class)` or `@RequestBody Mono<LargeObject>`, the decoder may **aggregate data** to construct one object.
- `spring.codec.max-in-memory-size` caps memory for many codecs when buffering/aggregating; **it is not a total HTTP upload cap** across every stream/file format.
- `multipart/form-data` has its own rules/limits (part counts, disk usage, file handling); check exact docs for your Spring version.
- Consuming `DataBuffer` directly requires lifecycle management; with pooled Netty buffers, you must **release** them properly when retaining/discarding them yourself. Standard codecs usually handle buffer management for you.
- Never convert every incoming body via unbounded `collectList()` or `DataBufferUtils.join(...)`; you lose streaming benefits and risk OOM.
- Enforce request size limits at **gateway, web server, decoder, and business layers**, applying quotas/rate limits and auth.
- `Flux<DataBuffer>` only represents buffer chunks; a multipart upload can deliver a huge file even chunk by chunk.

Example property capping aggregating codecs:

```properties
spring.codec.max-in-memory-size=256KB
```

**Do not conclude a 10 GB upload is safe** just because the codec limit is 256 KB: if a pipeline streams files to disk/object storage, total bytes, quotas, cancellation, and storage limits still require separate enforcement.

## 14. Blocking I/O in WebFlux Breaks Demand-Aware Pipelines

An improper WebFlux handler:

```java
@GetMapping("/report")
Mono<Report> report() {
    Report report = blockingJdbcDao.load(); // Runs immediately on event loop.
    return Mono.just(report);
}
```

This is an **anti-pattern fragment**, assuming `blockingJdbcDao` returns `Report`. Spring WebFlux event loops have few threads; blocking JDBC or `Thread.sleep` can hold a thread too long, hurting all other requests.

If you are still forced to use a blocking library during migration:

```java
@GetMapping("/report")
Mono<Report> report() {
    return Mono.fromCallable(() -> blockingJdbcDao.load())
            .subscribeOn(Schedulers.boundedElastic());
}
```

This is a **fragment** needing Reactor `Mono`, `Schedulers`, and the `Report` service/record. `boundedElastic` isolates blocking work off the Netty event loop into a bounded pool; **it does not make JDBC non-blocking** and does not eliminate connection-pool, timeout, queue, or thread-count limits.

Recommendations:

- Use R2DBC/reactive database drivers when backpressure on the database read path is needed.
- Use `WebClient` instead of blocking HTTP clients when pipelines require async/non-blocking I/O.
- With cursors/queries, verify whether the driver genuinely honors demand and manages resource lifecycles.
- Configure DB pools, outbound HTTP concurrency, and global rate limits alongside Reactor prefetch.
- Avoid `block()`, `toIterable()`, synchronized locks, or CPU-heavy loops on Netty event loops.
- For CPU-heavy work, use `parallel` or a dedicated measured executor instead of sprinkling `subscribeOn`/`publishOn` everywhere.

## 15. HTTP/1.1, HTTP/2, and HTTP/3: Which Limits Are Physical, Which Are API?

### 15.1. HTTP/1.1

- A streaming response can use chunked transfer encoding when Content-Length is absent; the container determines framing.
- TCP controls **byte** transmission, unaware of `Flux<Item>` or `ServerSentEvent<T>`.
- An HTTP/1.1 connection typically lacks multiplexing compared to HTTP/2; many concurrent SSE connections can strain browser/network limits.
- HTTP clients/proxies may buffer, decompress, and parse in their own ways.
- “`onNext(item)` was called” does not mean the client immediately received the entire item at that instant.

### 15.2. HTTP/2

HTTP/2 has **stream-level and connection-level flow control** via windows and `WINDOW_UPDATE` for DATA frames. This is byte-oriented and independent of Reactor's `Subscription.request(n)`. HTTP/2 also supports multiplexing: one connection carries many streams; one slow stream does not mean another publisher shares the same demand pattern.

The relationship is indirect: a small HTTP/2 send window → outbound writes are throttled → the adapter slows reading more data buffers → reactive pipeline demand is regulated. Yet there is no formula `request(n) = HTTP2 WINDOW_UPDATE(n)`.

### 15.3. HTTP/3/QUIC

HTTP/3 runs over QUIC, with byte-based stream/connection flow control and different transport mechanics from TCP, yet the principle “the wire protocol does not send Reactor `request(n)`” stays the same. With WebFlux behind an HTTP/3-terminating reverse proxy, HTTP/3 may exist only between browser and gateway while origin uses HTTP/1.1 or HTTP/2; measure the actual deployment.

### 15.4. Other Types of Limits

- **Content-Length**: declared/known body size upfront, not Reactive Streams demand.
- **Max request size / codec max buffer**: payload/memory protection thresholds, not how many items a consumer will request.
- **Rate limit**: requests or tokens/bytes per time/user, not the `limitRate` operator.
- **Timeout**: response/idle duration, not direct queue byte control.
- **Concurrency cap**: allowed concurrent tasks/connections/subscribers, distinct from item prefetch.
- **Backpressure**: flow-controlled demand between reactive stages, capable of slowing compatible upstream sources.

## 16. Proxies/CDNs Can Mask a Slow Consumer

Suppose the real client reads slowly, while NGINX enables response buffering:

```text
WebFlux origin  -->  Proxy RAM/disk buffer  -->  Slow browser
    fast                 accumulates                slow

Origin finishes sending quickly
=> demand at origin does NOT necessarily reflect slow browser processing
```

This remains true even if the application's Reactor pipeline is written with “textbook backpressure”. Layers to check:

- Reverse proxy `proxy_buffering` / `proxy_request_buffering`, response compression.
- CDN edge caching, transformations, WAF buffering.
- GZIP/Brotli chunk flush policies.
- HTTP/2 → HTTP/1.1 gateway translation.
- Keep-alive, read/write/idle timeouts, and max connections.
- Browser `EventSource`/client buffering/console output.
- Network latency, packet loss, and TCP flow control.

For latency-sensitive streaming routes, configure proxies appropriately; for instance, NGINX can honor:

```http
X-Accel-Buffering: no
Cache-Control: no-cache
Content-Type: text/event-stream
```

`X-Accel-Buffering` is an NGINX-specific hint, **not a standard HTTP guarantee**; the proxy must be configured to honor it. Do not disable buffering site-wide unconditionally.

Test on **localhost**, **embedded Reactor Netty**, **staging gateways**, and if needed **real browsers**; measure time-to-first-event, queue growth, and disconnect detection.

## 17. Cancellation, Timeouts, Errors, and Client Disconnects

A consumer can stop via `cancel()` (such as `take(3)` or StepVerifier cancel). An HTTP client may disconnect mid-stream. However, cancel propagation across codecs, adapters, schedulers, and drivers is **not always instantaneous**.

```java
Flux<Data> stream = source
        .doOnCancel(() ->
                metrics.incrementCancelled())
        .doFinally(signal ->
                metrics.recordTerminal(signal));
```

This is a fragment. `doFinally` receives `SignalType` (complete, error, or cancel) and fits tracking terminal lifecycles; callbacks do not replace transaction cancellation in external sources.

When the source is a database cursor, file reader, or broker subscription, cancellation should trigger cleanup:

- Close/release DB cursors, reactive connections, or pooled resources.
- Cancel unnecessary timers/subscriptions/producer work.
- Clean up per-client buffers and queues.
- Bound durations of network requests and external service calls.
- Wire user-disconnect cancellation cleanly at the adapter.
- Do not retain pooled `DataBuffer` instances beyond their lifecycle without proper retain/release handling.

### 17.1. Errors After the Response Has Started

If WebFlux has already sent `HTTP 200` headers and several NDJSON/SSE items before upstream emits `onError`, the server **cannot change** the response into a valid `500 application/problem+json`. The client may see an incomplete stream or connection reset.

Solutions depend on the protocol: emit an SSE `error` event while the stream is still writable, provide event IDs/replay, include checksums/end markers for batch data, or support client retries/idempotency.

**`onErrorResume` does not automatically turn every stream error into HTTP 500**; it merely swaps the Publisher for a fallback per Reactor logic. If the fallback object breaks schema/framing, clients can fail parsing; for security errors, never return stack traces.

### 17.2. Timeouts Do Not Replace Overload Control

`timeout(Duration)` can terminate a flow when signals stop arriving. Yet request concurrency, pending upstream calls, and buffer memory still need bounding. When returning timeouts/retries, avoid causing a **retry storm**.

Never use unbounded `retry()` on databases, gateways, or hot sources without backoff, jitter, attempt caps, and idempotency policies.

## 18. Client-Side Backpressure Using WebClient

`WebClient` in WebFlux is also a reactive HTTP client; when a response body is NDJSON/SSE, it can decode into `Flux<T>`:

```java
WebClient client = WebClient.create(
        "https://api.example.org");

Flux<Item> items = client.get()
        .uri("/api/items.ndjson")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(Item.class)
        .limitRate(8);
```

This is a **fragment**, requiring WebClient/Reactor/MediaType imports and the `Item` DTO. Without subscribing, most of the pipeline has not sent an HTTP request. `limitRate(8)` shapes Reactor demand on the client side; it **does not send an HTTP message `request(8)` to the origin**. The network/backpressure bridge may reduce bytes read/buffered, yet there is no contract of “exactly eight network objects in flight”.

If a client calls:

```java
List<Item> all = client.get()
        .uri("/api/items.ndjson")
        .retrieve()
        .bodyToFlux(Item.class)
        .collectList()
        .block();
```

it will **collect the entire result** into a list (and block the thread). For long or infinite sources, this is an anti-pattern causing memory pressure and potentially never finishing. On WebFlux request threads/event loops, use reactive composition instead of `block()`.

### WebClient Filters, Timeouts, and Connection Pooling

- Cap connection pools, pending acquires, response timeouts, and max in-memory codec buffering.
- Use `flatMap(..., concurrency)` to cap concurrent HTTP requests.
- Use circuit breakers/bulkheads where appropriate, not `limitRate` alone.
- With retries, enforce idempotency and prevent thundering herds.
- When receiving very long streams, avoid `bodyToMono(byte[].class)` which aggregates everything.
- Ensure response bodies are consumed or cancelled cleanly so connections can be released/reused.

## 19. Measuring Backpressure Properly in Production

Metrics to observe:

| Metric | Why It Is Useful |
| --- | --- |
| Active connections/streams | Detects lingering connections or leaks |
| Inbound/outbound bytes/s | Actual HTTP/network throughput |
| Queue depth **and bytes** | Measures backlog; bytes matter because item sizes vary |
| Oldest queued item age | Detects stale data reaching clients |
| Time-to-first-byte / first-event | Directly measures streaming UX |
| End-to-end event latency | Compares creation time vs. client receipt time |
| HTTP write/flush stalls | Detects slowdowns from sockets/gateways |
| Dropped/latest/overflow count | Shows loss policies actively firing |
| Subscription cancel/error/complete | Distinguishes normal stops from failures |
| Reactor scheduler pending tasks | Detects scheduling bottlenecks |
| DB/outbound pool utilization | Measures whether upstream actually experiences reduced load |
| Gateway/edge buffer occupancy | Identifies where origin and browser become decoupled |
| HTTP client consumption latency | Avoids inferring UX solely from producer send timestamps |

`doOnRequest` is useful for bounded debugging, yet **request count is not directly network throughput**. Avoid attaching event payloads or PII to metric tags; high cardinality explodes observability systems.

### 19.1. Designing Slow-Consumer Load Tests

A rigorous test should:

1. Spin up 100/1,000 concurrent clients in a controlled environment.
2. Use HTTP clients that read **incrementally**, including slow-reading or paused clients.
3. Monitor heap, direct memory, Netty pending writes, queue depth, GC, and CPU.
4. Compare origin vs. gateway vs. client timestamps.
5. Test cold and hot sources separately.
6. Exercise buffer policies, drop/latest/error, and subscriber caps.
7. Test early client disconnects, server cancellations, and cleanup.
8. Compare HTTP/1.1 vs. HTTP/2 configurations across the same topology.
9. Increase payload size per item, not just item count.
10. Verify retry storm behavior when overload/circuit breakers trigger.

Never use `Thread.sleep` on the WebFlux event loop to simulate slow consumers. Client-side test harnesses can read slowly on bounded threads, or use virtual-time tests for isolated Reactor logic.

## 20. Common Misconceptions

| Wrong Claim | Accurate Fact |
| --- | --- |
| “`Flux` means every response streams immediately.” | Depends on encoder, media type, flush, and proxies |
| “`request(3)` sends an HTTP command to the browser.” | Internal Reactive Streams signal, not HTTP wire traffic |
| “`request(3)` equals 3 KB.” | Measured in **items**; item sizes vary |
| “`limitRate(10)` limits 10 requests/second.” | Splits demand into batches, not a rate limiter |
| “`take(10)` and `limitRate(10)` are the same.” | `take` caps total items; `limitRate` batches demand |
| “Downstream requests 1 so upstream always requests 1.” | `buffer`/`filter`/`flatMap`/`publishOn`/prefetch alter demand |
| “`onBackpressureBuffer()` solves overload forever.” | Unbounded buffers can cause OOM |
| “`onBackpressureDrop` is always harmless.” | Unsuitable for must-deliver data like payments |
| “A hot source slows down automatically if subscriber doesn't request.” | External sources may keep pushing; explicit policy needed |
| “SSE EventSource has `request(n)`.” | Browser EventSource does not implement Reactive Streams |
| “HTTP/2 WINDOW_UPDATE is `request(n)`.” | Windows count bytes, not objects |
| “Slow TCP slows the origin immediately.” | Proxies/CDNs can buffer and decouple |
| “`subscribe()` always asks for 1 item.” | Many overloads request `Long.MAX_VALUE` |
| “Reactive = automatically non-blocking even with JDBC.” | Blocking libraries still block threads |
| “`collectList()` on an infinite stream is safe.” | Can grow RAM unboundedly and never complete |
| “Returning Flux from a controller stops DDoS.” | Still requires auth, quotas, concurrency/rate limits |
| “Closing a browser tab triggers `doOnCancel` instantly.” | Depends on writes, heartbeats, and network detection |
| “`onError` mid-stream changes status 200.” | Response may already be committed; needs protocol-level handling |

## 21. WebFlux Streaming Development Checklist

- [ ] Clearly identify the unit of demand: `T`, `List<T>`, or `DataBuffer`.
- [ ] Ensure source pipelines are genuinely demand-aware; for hot sources, define overflow policies.
- [ ] Eliminate unbounded buffers/`collectList` on long-lived streams.
- [ ] Set appropriate concurrency/prefetch on `flatMap`/`publishOn` operators.
- [ ] Never use `limitRate` as an API request rate limiter.
- [ ] Keep blocking I/O and `block()` off Reactor Netty event loops.
- [ ] Pick `application/x-ndjson` or `text/event-stream` matching the contract.
- [ ] Ensure clients parse framing properly and handle partial streams/cancellation.
- [ ] Enforce HTTP codec buffer limits, request sizes, and queue byte caps.
- [ ] Cap Netty connection pools and outbound HTTP concurrency.
- [ ] Add heartbeats, `Last-Event-ID` replay if needed, and per-connection/tenant limits for hot SSE.
- [ ] Clean up DB cursors, subscriptions, timers, and pooled buffers in `doOnCancel`/`doFinally`.
- [ ] Define clear retry/protocol handling for errors after committed responses.
- [ ] Verify proxies/CDNs/ingress for buffering and timeouts.
- [ ] Write `StepVerifier` unit tests starting from demand 0; write `WebTestClient` HTTP tests for framing.
- [ ] Load-test slow consumers while monitoring direct-memory and queue metrics.
- [ ] Never put tokens, payloads, or arbitrary user IDs into logs/metric tags.
- [ ] When upgrading Spring/Boot/Reactor, check operator prefetch defaults, codecs, and server adapter behavior.

## 22. Self-Assessment Exercises

1. Does `request(5)` ask for 5 bytes, 5 HTTP chunks, or 5 Reactor elements? What if each element is a `List<Order>`?
2. Call `StepVerifier.create(Flux.range(1,5),0)` then `thenRequest(2)`. Why is initial request 0 in the test **different** from calling `Subscription.request(0)`?
3. Place `doOnRequest` before and after `limitRate(4)`. Predict how the logs differ when downstream requests 100.
4. Compare `limitRate(10)` with `limitRate(10,0)`, especially regarding low-tide replenishment.
5. With `Flux.range(1,100).buffer(10)`, how much demand might the source receive if the subscriber requests 2?
6. Why does `flatMap(mapper,8,16)` fail to enforce a hard byte memory limit for every request?
7. Explain how `onBackpressureLatest` drops intermediate progress events while still remaining valid for a percentage dashboard.
8. Why must `onBackpressureDrop` never be used for order payments or security audit events?
9. Suppose upstream publishes continuously from Kafka at 50k msg/s while SSE clients consume 100/s. Would you choose pause, bounded buffer, durable broker, or disconnect? Explain data-loss semantics.
10. Given the same `Flux<Item>`, how can `application/json` and `application/x-ndjson` differ in emission behavior?
11. Can browser `EventSource` send `request(2)`? If not, what mechanisms still provide HTTP backpressure?
12. What units do HTTP/2 stream windows and TCP receive windows use? Why aren't they equivalent to Reactor element demand?
13. NGINX reads fast from origin while buffering the response for a slow browser. Does origin `doOnRequest` still accurately reflect browser latency?
14. If a `Flux<DataBuffer>` has a single 50 MB item, is `request(1)` memory-safe? Design chunk/buffer size limits.
15. Add `onBackpressureBuffer(100)` to hot events. What policies can apply when the buffer fills, and which metrics should be watched?
16. Replace DB access in WebFlux with direct blocking JDBC. How does that affect Reactor Netty event loops? What does `boundedElastic` fix and what does it not fix?
17. On `WebClient.bodyToFlux(Item.class)`, what is the design flaw if you change it to `collectList().block()` for an infinite stream?
18. A client disconnects after 2 of 5 NDJSON records while the server already returned status 200. How can the client detect partial results and retry safely?
19. Design a `StepVerifier` test measuring demand directly, a `WebTestClient` test checking SSE fields, and a proxy load test measuring first-event latency; distinguish the three goals.
20. During a rolling deployment, a browser reconnects SSE with `Last-Event-ID` to a different node. Why is a shared durable event log needed if events must not be lost?
21. Feed a hot source into `publishOn` with prefetch 32; if the client stops requesting, where can buffers/overflow build up?
22. Build per-tenant HTTP rate limiting and stream overflow policies; explain why `limitRate(10)` alone cannot solve this.

## 23. Official Documentation

- [Reactive Streams Specification — JVM](https://www.reactive-streams.org/): `Publisher`/`Subscriber`/`Subscription` principles and the `request(n)` contract.
- [Project Reactor Reference — Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html#_on_backpressure_and_ways_to_reshape_requests): demand, BaseSubscriber, prefetch, limitRate.
- [Project Reactor — Flux Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `limitRate`, `flatMap`, `publishOn`, `onBackpressureBuffer/Drop/Latest/Error`.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): initial request, thenRequest, deterministic signal testing.
- [Spring Framework — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): `HttpHandler`, codecs, non-blocking I/O, Reactive Streams backpressure, and `DataBuffer`.
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods.html): reactive controller return values.
- [Spring Framework — WebFlux Reactive Libraries](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-libraries.html): reactive adaptation, cancellation, and request signals.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing HTTP streaming/response bodies.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): default Reactor Netty reactive server.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): RANDOM_PORT, WebTestClient, WebFlux test configuration.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.codec.max-in-memory-size`.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html): stream/connection byte-oriented flow control.
- [RFC 9293 — Transmission Control Protocol](https://www.rfc-editor.org/rfc/rfc9293.html): TCP receive windows and byte stream semantics.
- [WHATWG HTML — Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html): SSE/EventSource protocol/reconnect.
