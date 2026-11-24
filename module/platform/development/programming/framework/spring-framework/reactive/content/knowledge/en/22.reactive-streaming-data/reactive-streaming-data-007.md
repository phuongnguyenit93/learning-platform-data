# Slow Connections, Backpressure, and Data-Limiting Policies

**Module:** Spring Framework – reactive  
**Parent topic:** Continuous Data Streaming

## Learning objectives

After this lesson, you will be able to:

1. Explain Reactive Streams backpressure and how demand propagates upstream from subscriber to publisher.
2. Analyze what happens when an HTTP client reads slowly, downstream processes slowly, or upstream emits data faster than it can be consumed.
3. Distinguish publishers that can honor demand from hot data sources that cannot pause.
4. Choose bounded buffer, drop, latest, or error policies based on business requirements.
5. Use Reactor operators such as `limitRate`, `onBackpressureBuffer`, `onBackpressureDrop`, `onBackpressureLatest`, `flatMap`, and `timeout` for their intended purpose.
6. Bound memory, item counts, concurrency, prefetch, body size, and timeouts to avoid unbounded data accumulation.
7. Handle overflow, cancellation, and slow consumers in WebFlux HTTP/SSE.
8. Build and test a streaming endpoint with a bounded buffer using Spring Boot and `WebTestClient`.

## 1. What problem does backpressure solve?

A reactive pipeline typically consists of a publisher producing data, operators transforming data, and a subscriber consuming data. If the publisher emits faster than the subscriber processes, unconsumed data can accumulate in queues, buffers, or intermediate layer memory.

Backpressure is a mechanism for regulating emission rate via **demand**. The subscriber requests the number of elements it is ready to receive via `Subscription.request(n)`. A Reactive Streams–compliant publisher may emit at most the requested number of elements until it receives additional demand.

```text
Publisher / source
       |
       | onNext(item) per demand
       v
Operator A
       |
       v
Operator B
       |
       v
Subscriber / HTTP writer
       |
       | request(n): need n more elements
       +-------------------------------> demand propagates upstream

If consumer is slow:
- new demand arrives more slowly
- publisher can slow down or pause emission
- bounded queues help prevent unbounded accumulation
```

Core Reactive Streams signals:

- `onSubscribe(subscription)`: the subscriber receives the subscription.
- `request(n)`: the subscriber signals demand for n more elements.
- `onNext(value)`: the publisher emits an element when demand exists.
- `onError(error)`: the publisher terminates with an error.
- `onComplete()`: the publisher completes normally.
- `cancel()`: the subscriber cancels consumption; upstream should stop and release resources appropriately.

Demand counts **elements**, not bytes. One element may be a string of a few bytes or an object carrying a large payload. Therefore, backpressure must be paired with element/body size limits and memory policies.

## 2. Why can slow connections cause data accumulation?

Consider an SSE endpoint emitting device status:

- The producer generates 500 events per second.
- The client can only read and process 20 events per second.
- The mismatch is 480 events per second.

If the application keeps all events in an unbounded queue, after 60 seconds it can accumulate 28,800 unconsumed events for that client alone. If many clients are simultaneously slow, data volume grows with connection count and individual event size.

Places where data can accumulate include:

1. Queues of hot data sources or message listeners.
2. Reactor operator buffers, such as buffer, window, or prefetch.
3. Queues in publisher/consumer adapters.
4. HTTP encoders and server transport write queues.
5. Operating system socket buffers.
6. Reverse proxies, load balancers, and client-side buffers.

WebFlux can propagate backpressure from the HTTP writer back to the reactive publisher when participating layers support demand. However, that **does not guarantee the entire network path is buffer-free**. TCP flow control, proxy queues, and client libraries are separate mechanisms. A hot source or external callback can keep emitting even after the subscriber reduces demand.

Therefore, identify which layer is accumulating data. Merely increasing buffer sizes only delays failure and drives memory consumption higher.

### 2.1. Three situations to distinguish

| Situation | Characteristic | Handling approach |
| --- | --- | --- |
| Upstream can honor demand | Source only emits when downstream requests | Let backpressure propagate back; avoid unnecessary queues. |
| Hot upstream, cannot pause | Timers, callbacks, event buses, or external producers keep emitting | Choose bounded buffer, drop, latest, or reject/error. |
| Slow or disconnected HTTP consumer | Write demand drops or subscriber cancels | Keep pipeline streaming, bound queues, handle cancellation and timeouts. |

Example of a demand-respecting source: a reactive database driver returning `Flux<Row>` that only reads more rows when the subscriber requests them. Example of a hot source: a hardware sensor emitting events on its own clock regardless of whether the client reads fast or slow.

### 2.2. Backpressure differs from TCP flow control

TCP uses a receive window to regulate how many bytes a sender may transmit before receiving acknowledgement. Reactive Streams uses demand to regulate **elements** between publisher and subscriber inside the application.

The two mechanisms can cooperate through the HTTP server adapter, but they are not identical:

- TCP can slow down socket writes when the receiver cannot read fast enough.
- Reactive backpressure can slow down a publisher emitting objects when the HTTP writer stops requesting more.
- Proxies or intermediate layers may still buffer data.
- A producer that does not support demand still needs an application-level overflow policy.

Do not conclude that using WebFlux makes running out of memory impossible. Unbounded queues, large payloads, too many connections, or operations collecting entire bodies can still spike memory usage.

## 3. Choosing a policy when the consumer is slow

No single overflow policy fits every kind of data. The first question is: **when processing cannot keep up, do older events still hold value?**

| Policy | Behavior | Fits | Trade-off |
| --- | --- | --- | --- |
| Pure backpressure | Asks upstream to slow emission per demand | Reactive databases, file streams, pausable sources | Does not apply to every hot source. |
| Bounded buffer | Holds at most N pending elements | Short bursts, data needing bounded retention | When full, an overflow handling strategy is required. |
| Drop incoming | Discards new elements when consumer is not ready | Metrics, telemetry where sample loss is acceptable | Loses the newest data. |
| Drop oldest / keep latest | Evicts old elements to retain newer state | Dashboards, sensor state | Unsuitable for audits/events that must all be saved. |
| Latest | Keeps only the newest value while consumer is slow | Current state, snapshots | Intermediate states are skipped. |
| Error/reject | Terminates stream or rejects producer when full | Transactions, commands needing explicit confirmation | Client must handle errors/retries or persist durably. |
| Durable queue | Writes to broker/database with retention and acks | Events that must never be lost | Increases complexity and operational cost. |

The decision must come from data semantics:

- **Current state values:** keeping latest usually makes sense; stale states are no longer needed.
- **High-frequency metrics:** dropping or sampling can be acceptable if a metric counts dropped samples.
- **Payment commands, audits, or business events:** never drop silently; require confirmation, durable persistence, or explicit rejection on overload.
- **Short bursts:** small buffers can absorb temporary spikes; buffers do not solve a producer that is continuously faster than the consumer.

## 4. Backpressure operators in Reactor

### 4.1. limitRate: regulating requests in batches

`limitRate(highTide)` splits demand into smaller request batches. It is useful when you want upstream to receive batched requests instead of one unbounded request.

```java
Flux<Row> rows = repository.findAll()
        .limitRate(64);
```

This is an **illustrative snippet**. The value 64 is the batch request threshold, not a limit of 64 rows per second and not a limit on the total rows in the stream.

Both high-tide and low-tide can be configured:

```java
Flux<Row> rows = repository.findAll()
        .limitRate(64, 32);
```

High-tide is the request threshold; low-tide controls when Reactor replenishes the next demand. Specific parameters should be chosen based on processing cost and upstream prefetch.

**Common confusion:** `limitRate` is not a time-based rate limiter. It does not guarantee at most X events/second. If time-based rate limiting is required, use a rate limiter/token bucket at the appropriate boundary, or pace emission over time with an appropriate operator. `delayElements` slows individual elements without limiting incoming HTTP requests to the server.

### 4.2. onBackpressureBuffer: bounded buffer

`onBackpressureBuffer(maxSize)` holds waiting elements in a buffer when upstream emits faster than demand. Always choose a finite limit for data of meaningful size or frequency.

```java
Flux<Reading> readings = hotSource
        .onBackpressureBuffer(128);
```

When the limit is exceeded, the pipeline can terminate with an overflow error. To explicitly decide which elements are dropped, use the overload with an overflow callback and strategy:

```java
Flux<Reading> readings = hotSource.onBackpressureBuffer(
        128,
        dropped -> metrics.incrementDropped(),
        BufferOverflowStrategy.DROP_OLDEST);
```

This is an **illustrative snippet**; `metrics` is an application component. `DROP_OLDEST` evicts the oldest element in the buffer when full to favor newer data. Common `BufferOverflowStrategy` choices include `ERROR`, `DROP_OLDEST`, and `DROP_LATEST`. Choose based on data semantics, not throughput alone.

A buffer only helps if it is bounded. An unbounded buffer turns a slow consumer into heap exhaustion—just with a delayed failure.

### 4.3. onBackpressureDrop: dropping unaccepted elements

`onBackpressureDrop()` discards emitted elements when downstream has no demand. A callback can be attached to count or observe dropped elements:

```java
Flux<Metric> metrics = hotMetricsSource
        .onBackpressureDrop(dropped ->
                meterRegistry.counter("metrics.dropped").increment());
```

This is an **illustrative snippet**. Use only when sample loss is acceptable. The callback should be lightweight and non-blocking because it runs on the emission path.

### 4.4. onBackpressureLatest: keeping the latest state

`onBackpressureLatest()` retains the newest element while downstream is not ready; intermediate values may be overwritten:

```java
Flux<DeviceState> state = hotStateSource
        .onBackpressureLatest();
```

Fits dashboards that only need current state, such as current temperature or latest position. Unsuitable for transaction sequences where every event must be processed.

### 4.5. onBackpressureError: explicit error on missing demand

`onBackpressureError()` turns emitting past demand into an error instead of silently accumulating or dropping:

```java
Flux<Command> commands = hotCommandSource
        .onBackpressureError();
```

This fits when the application wants to fail fast and has clear error/recovery handling. With an already-committed HTTP stream, a mid-stream error cannot turn the response into a fresh JSON 503; the client will see the stream terminate or a transport error per the protocol.

### 4.6. Do not stack operators arbitrarily

Avoid chaining large buffers, latest, drop, and retries in sequence without establishing which operator owns the overflow policy. Operator order changes where demand is regulated and where elements are discarded.

Example:

```java
Flux<Reading> bounded = hotSource
        .onBackpressureBuffer(
                128,
                dropped -> metrics.incrementDropped(),
                BufferOverflowStrategy.DROP_OLDEST)
        .limitRate(32);
```

This snippet places a bounded queue at the hot source boundary and limits how downstream requests data in batches. Measure queue depth, overflows, and latency to confirm the configuration actually fits.

## 5. Limiting concurrency and prefetch

Backpressure controls demand, yet a pipeline can still spawn many concurrent tasks. `flatMap` allows asynchronous parallel processing of elements; without appropriate concurrency limits, many I/O requests may open or wait simultaneously.

```java
Flux<EnrichedOrder> result = orderIds
        .flatMap(
                id -> remoteService.loadOrder(id),
                8,
                1);
```

In this example:

- `8` is the maximum number of inner publishers subscribed concurrently.
- `1` is the prefetch per inner publisher.
- `flatMap` may still emit results in completion order, not guaranteeing input order.

If order must be preserved, consider `flatMapSequential`. If elements must be processed strictly sequentially one by one, use `concatMap`:

```java
Flux<Result> sequential = inputs.concatMap(this::process);
```

Excessive concurrency increases open DB/HTTP connections, live objects, and results queued downstream. Excessive prefetch can inflate queues. Set concurrency according to real dependency capacity and memory budgets, then measure latency/errors/queues.

### 5.1. Limiting element count and stream duration

An infinite stream needs an explicit lifecycle and quota. Element counts can be bounded:

```java
Flux<Event> firstThousand = eventSource.take(1_000);
```

Or timed out if upstream emits no signal within the allowed duration:

```java
Mono<Response> response = remoteCall()
        .timeout(Duration.ofSeconds(3));
```

With `Flux.timeout(Duration)`, the timeout typically applies to the gap between signals; an active stream can still run for a long time. If business rules require an overall deadline, design an explicit request-wide deadline/cancellation mechanism.

Timeouts do not solve full queues. They only end work when a timing condition is violated; queues still require bounds and overflow policies.

## 6. Memory budget: bounding queues by data size

Backpressure counts items, whereas the heap is consumed in bytes and object overhead. A buffer of 1,000 tiny items differs dramatically from a buffer of 1,000 items containing large JSON payloads.

If each client has its own queue, raw payload size can be estimated:

```text
Memory payload ≈ number of slow clients
               × max items per queue
               × average size per item
```

Example:

- 150 concurrently slow clients.
- Each client holds at most 64 items.
- Each item has an average payload of 2 KiB.

Estimated raw payload is:

```text
150 × 64 × 2 KiB = 19,660,800 bytes ≈ 18.75 MiB
```

This is raw payload only. Object headers, references, queue nodes, byte buffers, encoders, and transport buffers make actual usage higher. If a pipeline has multiple queues, sum the budgets of every layer.

A safe configuration typically includes:

- Limits on concurrent clients/connections.
- Queue or buffer limits per client.
- Size limits per item and total body when needed.
- Concurrency/prefetch limits for I/O work.
- Timeouts and cancellation to release resources.
- Metrics for queue depth, overflows, dropped items, active streams, and processing time.

Do not pick buffer capacities based solely on a quick benchmark. Test under many concurrently slow clients and payloads near maximum size.

## 7. Limiting request bodies and codecs in WebFlux

Another issue is clients sending large or very slow bodies. When using `bodyToMono(MyDto.class)` or `@RequestBody MyDto`, codecs usually must accumulate enough content to decode into an object. If the body exceeds the configured memory limit, WebFlux can emit `DataBufferLimitException`.

You can set the codec memory limit via Spring Boot configuration:

```properties
spring.codec.max-in-memory-size=1MB
```

Or configure it directly:

```java
@Configuration
public class WebFluxCodecConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(1024 * 1024);
    }
}
```

This limit applies to data that codecs must buffer/aggregate during reading or writing. It is **not a general byte quota for all streaming requests** if the application consumes `Flux<DataBuffer>` directly without buffering the body in memory. For uploads or APIs needing total request byte limits, add limits at the server/proxy or count bytes in the pipeline and abort when exceeded.

### 7.1. Streaming the body instead of collecting everything

For large files or continuous data, avoid reading everything into a `byte[]` or `List<T>`:

```java
@PostMapping("/import")
public Mono<Void> importData(@RequestBody Flux<ImportRow> rows) {
    return rows
            .limitRate(32)
            .concatMap(importService::process);
}
```

This is an **illustrative snippet**. `concatMap` processes each row sequentially and only advances per demand; `limitRate` regulates batch requests. If parallel processing is needed, set bounded concurrency via `flatMap(mapper, concurrency, prefetch)`.

Avoid:

```java
return rows.collectList()
        .flatMap(importService::processAll);
```

`collectList()` holds all elements until the source completes. For long or unending streams, memory can grow without bound or the final processing step may never run. Use it only when input size is explicitly bounded and collecting everything is a real requirement.

### 7.2. Counting bytes when raw body limits are required

If you must limit total raw body bytes, you can count `DataBuffer.readableByteCount()` in the pipeline and abort when exceeding the threshold. Illustrative example:

```java
AtomicLong received = new AtomicLong();

Flux<DataBuffer> boundedBody = request.getBody()
        .handle((buffer, sink) -> {
            long total = received.addAndGet(buffer.readableByteCount());
            if (total > MAX_BODY_BYTES) {
                DataBufferUtils.release(buffer);
                sink.error(new PayloadTooLargeException());
            } else {
                sink.next(buffer);
            }
        });
```

This is **low-level illustrative code**, not a complete copy/paste solution for every transport. When passing buffers downstream, preserve ownership; on discard/cancel/error, release each buffer exactly once. Test buffer drop/discard paths as well as how the server terminates the request. For ordinary endpoints, prefer server/codec limits and bounded DTO bodies instead of handling DataBuffers manually.

## 8. Handling slow HTTP clients and cancellation

When a client reads the response slowly, demand at the HTTP writer can drop. If the reactive upstream can honor demand, it will emit more slowly. If upstream is a hot source, the buffer/overflow policy decides what happens.

When the client closes the connection, the subscriber can send `cancel`. The pipeline should propagate cancellation upstream to stop queries, timers, or unneeded work. Do not store subscriptions in singleton fields and do not spawn detached subscriptions via `subscribe()`.

Lifecycle observation example:

```java
return eventService.stream()
        .doOnCancel(() -> log.info("client cancelled stream"))
        .doFinally(signal -> releaseRequestResources());
```

This is an **illustrative snippet**. `doOnCancel` observes cancellation; `doFinally` runs on complete, error, or cancel. Cleanup must be idempotent if multiple termination paths exist and must use appropriate APIs for async resources.

### 8.1. Timeouts and idle clients

Timeouts prevent holding resources indefinitely when upstream stops emitting or a dependency responds too slowly. However, inter-event timeouts and overall deadlines serve two different goals.

For SSE streams, once response headers and some events have been sent, a timeout cannot turn the status into 504 with a new JSON body. You can emit an error event per a defined schema or terminate the stream. For requests that have not committed a response, timeout errors can be mapped to an appropriate status by an error handler.

### 8.2. Do not retry infinitely on overflow

When a queue is full, retrying immediately can make the producer emit even more data and fill the queue faster. Retries only make sense with recovery conditions, attempt limits, and backoff. For producers requiring explicit acceptance, return 429/503 or write to a durable queue so the client/worker retries per contract.

## 9. Runnable Spring Boot 3.3.5 program

This example uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, and `spring-boot-starter-webflux`. A hot source emits events through a Reactor Sink with a maximum buffer of 32 items. When a slow consumer fills the buffer, the producer receives an overflow result and the endpoint returns HTTP 503 instead of accumulating more memory.

Structure:

```text
webflux-backpressure-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── BackpressureApplication.java
    │   ├── ReadingFeed.java
    │   └── ReadingController.java
    └── test/java/demo/
        └── ReadingControllerTest.java
```

### 9.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-backpressure-demo</artifactId>
    <version>1.0.0</version>

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

### 9.2. application.properties

```properties
server.port=8080
spring.codec.max-in-memory-size=1MB
```

The codec limit here is 1 MiB for cases requiring buffering/aggregation; raw streaming bodies still need separate total-byte limit policies if the API requires them.

### 9.3. BackpressureApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackpressureApplication {
    public static void main(String[] args) {
        SpringApplication.run(BackpressureApplication.class, args);
    }
}
```

### 9.4. ReadingFeed.java

```java
package demo;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
public class ReadingFeed {
    private final Sinks.Many<Reading> sink;
    private long nextId;

    public ReadingFeed() {
        this(32);
    }

    ReadingFeed(int capacity) {
        this.sink = Sinks.many()
                .multicast()
                .onBackpressureBuffer(capacity);
    }

    public Flux<Reading> stream() {
        return sink.asFlux();
    }

    public synchronized Sinks.EmitResult publish(String value) {
        long id = nextId + 1;
        Sinks.EmitResult result =
                sink.tryEmitNext(new Reading(id, value));

        if (result.isSuccess()) {
            nextId = id;
        }
        return result;
    }

    public record Reading(long id, String value) {}
}
```

`Sinks.Many` is a hot source that can accept data from external producers. `onBackpressureBuffer(32)` creates a bounded buffer for the multicast sink. `tryEmitNext` returns immediately; when the buffer is full, the result is `FAIL_OVERFLOW`. The publish method is synchronized so producers in this example emit sequentially, avoiding `FAIL_NON_SERIALIZED` from two threads emitting concurrently. There is no blocking I/O inside this synchronized section.

### 9.5. ReadingController.java

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@RestController
public class ReadingController {
    private final ReadingFeed feed;

    public ReadingController(ReadingFeed feed) {
        this.feed = feed;
    }

    public record PublishRequest(String value) {}
    public record PublishResult(String status) {}

    @PostMapping(
            value = "/readings",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<PublishResult>> publish(
            @RequestBody PublishRequest request) {

        if (request.value() == null || request.value().isBlank()) {
            return Mono.just(ResponseEntity.badRequest()
                    .body(new PublishResult("VALUE_REQUIRED")));
        }

        Sinks.EmitResult result = feed.publish(request.value());

        if (result.isSuccess()) {
            return Mono.just(ResponseEntity.accepted()
                    .body(new PublishResult("QUEUED")));
        }

        String code = result == Sinks.EmitResult.FAIL_OVERFLOW
                ? "BACKPRESSURE_OVERFLOW"
                : "FEED_UNAVAILABLE";

        return Mono.just(ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE)
                .body(new PublishResult(code)));
    }

    @GetMapping(
            value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<ReadingFeed.Reading>> events() {
        return feed.stream()
                .limitRate(16)
                .map(reading -> ServerSentEvent.builder(reading)
                        .id(Long.toString(reading.id()))
                        .event("reading")
                        .build());
    }
}
```

The `POST /readings` endpoint accepts data from the producer and returns 202 when the sink accepts it. When the buffer is full, it returns 503 with code `BACKPRESSURE_OVERFLOW`. The `GET /events` endpoint streams readings via SSE. `limitRate(16)` regulates the subscriber's batch demand; it is not a limit of 16 events per second. The buffer of 32 in the sink is the queue limit of the example.

### 9.6. Running and observing

In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Open a terminal to receive SSE:

```bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/events
```

In another terminal, send a reading:

```bash
curl -i -X POST http://localhost:8080/readings \
  -H "Content-Type: application/json" \
  -d '{"value":"temperature=25"}'
```

POST response when the sink accepts the data:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"status":"QUEUED"}
```

The SSE terminal receives an event like:

```text
id:1
event:reading
data:{"id":1,"value":"temperature=25"}

```

IDs increment with each reading accepted by the sink. JSON data and field ordering reflect record/Jackson formatting; headers depend on server and environment configuration.

If a subscriber does not request/consume fast enough, the bounded buffer can fill up. The producer then receives `FAIL_OVERFLOW` and the endpoint returns HTTP 503. In a real system, measure overflows and decide whether the producer retries with backoff, writes to a durable queue, or reports an error upstream.

## 10. Testing backpressure and overflow

The test example below verifies two things:

1. A subscribed SSE client receives the event published by POST.
2. A subscriber that has not requested elements only allows the buffer to hold at most two readings; the third emit receives `FAIL_OVERFLOW`.

```java
package demo;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReadingControllerTest {
    @Autowired
    WebTestClient client;

    @Test
    void connectedSseClientReceivesPublishedReading() {
        var result = client.get()
                .uri("/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                        new ParameterizedTypeReference<
                                ServerSentEvent<ReadingFeed.Reading>>() {});

        StepVerifier.create(result.getResponseBody())
                .then(() -> client.post()
                        .uri("/readings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(
                                new ReadingController.PublishRequest(
                                        "temperature=25"))
                        .exchange()
                        .expectStatus().isAccepted())
                .assertNext(event -> {
                    assertThat(event.event()).isEqualTo("reading");
                    assertThat(event.data().value())
                            .isEqualTo("temperature=25");
                })
                .thenCancel()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void boundedSinkRejectsThirdItemWhenSubscriberHasNoDemand() {
        ReadingFeed feed = new ReadingFeed(2);

        StepVerifier.create(feed.stream(), 0)
                .then(() -> {
                    assertThat(feed.publish("one"))
                            .isEqualTo(Sinks.EmitResult.OK);
                    assertThat(feed.publish("two"))
                            .isEqualTo(Sinks.EmitResult.OK);
                    assertThat(feed.publish("three"))
                            .isEqualTo(Sinks.EmitResult.FAIL_OVERFLOW);
                })
                .thenRequest(2)
                .expectNextMatches(reading ->
                        reading.value().equals("one"))
                .expectNextMatches(reading ->
                        reading.value().equals("two"))
                .thenCancel()
                .verify(Duration.ofSeconds(2));
    }
}
```

The `reactor-test` dependency is included in `pom.xml` to use `StepVerifier`. Run:

```bash
mvn test
```

The first test checks the end-to-end HTTP/SSE path. The second test simulates a subscriber with zero demand and verifies a buffer of capacity 2 rejects the third item. When running real tests, keep the Reactor version managed by the Spring Boot BOM.

## 11. Measurement and operations

You cannot evaluate backpressure merely by checking that the application does not crash. Observe producer rate, consumer rate, and queues together.

Useful metrics:

| Metric | Indicates | How to use |
| --- | --- | --- |
| Active streams/connections | Number of open consumers | Enforce limits and detect stalled clients. |
| Queue depth / buffer occupancy | Amount of queued data | Alert before overflow occurs. |
| Overflow count | How often the buffer filled | Tune producer, consumer, or policy. |
| Dropped/latest replaced count | Items not forwarded | Assess whether data loss is acceptable. |
| Demand/request rate | Rate at which subscriber requests items | Detect slow consumers. |
| Producer rate / consumer rate | Speed mismatch | Pinpoint bottlenecks. |
| End-to-end latency | Time from emission to processing | Detect queues making data stale. |
| Cancellation/timeout count | Cancelled or timed-out streams | Distinguish client disconnects from server errors. |
| Heap/direct memory | Memory pressure | Detect buffer/object accumulation. |

When buffers frequently approach capacity, treat it as a signal that consumption capacity is insufficient or the policy is unsuitable. Increasing capacity should only be a decision with an explicit budget and timeframe; if the producer is permanently faster than the consumer, a larger queue only delays overflow.

## 12. Rate limiting differs from backpressure

The two concepts are often mentioned together but solve different problems:

| Mechanism | What does it limit? | Example |
| --- | --- | --- |
| Backpressure | Number of elements subscriber is ready to receive | `request(32)`, `limitRate(32)` |
| Bounded buffering | Number of elements allowed to wait | `onBackpressureBuffer(128)` |
| Rate limiting | Number of requests/events over a time window | 100 requests/minute per client |
| Concurrency limiting | Number of tasks running concurrently | `flatMap(mapper, 8, 1)` |
| Payload/body limit | Byte or item size | codec max memory, max upload bytes |
| Timeout/deadline | Wait time or processing duration | `timeout(Duration.ofSeconds(3))` |

A client can send few requests per second while each request uploads a huge file. A stream can have healthy demand while each item is huge. A source can emit 10 items/second while each item triggers 100 concurrent tasks. Thus, real systems must combine multiple limits.

`limitRate` does not replace a token bucket or rate limiter at an API gateway. `onBackpressureBuffer` does not replace body limits. `timeout` does not replace queue limits.

## 13. Common mistakes and remedies

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Assuming WebFlux guarantees memory never grows | Hot sources, proxies, or queues can still buffer | Identify every layer and set finite bounds. |
| Using unbounded buffers for fast producers | Heap grows over time when consumers stay slow | Use bounded-capacity buffers and overflow policies. |
| Only increasing buffer size on overflow | Only delays failure if producer stays faster than consumer | Measure rates, throttle producer, scale consumer, or drop/reject intentionally. |
| Using `limitRate(32)` as a 32 events/sec rate limit | Confusing demand batching with time-based rate | Use a rate limiter/token bucket or time-based pacing. |
| Using `onBackpressureDrop` for audit events | Irrecoverable data loss | Use durable queues/acknowledgements or reject producer. |
| Using `onBackpressureLatest` for commands | Older commands can be overwritten | Use only for state snapshots where intermediates can be skipped. |
| Collecting infinite streams with `collectList()` | Never completes or exhausts memory | Process item by item, window/chunk, or bound element counts. |
| Setting overly high concurrency in `flatMap` | Opens too many DB/HTTP requests and increases memory | Choose concurrency/prefetch matching dependency capacity. |
| Thinking codec max memory bounds all request bytes | Raw streaming bodies can still exceed that byte total | Add total body limits at server/proxy or count bytes in pipeline. |
| Not handling cancellation on client disconnect | Upstream work keeps running and holding resources | Propagate cancellation and clean up with proper lifecycle hooks. |
| Retrying immediately when buffer is full | Producer worsens overload | Use backoff, retry limits, or explicit rejection. |
| Measuring only CPU without measuring queues | Queues grow long before CPU spikes | Monitor queue depth, overflows, dropped counts, and latency. |
| Calling `subscribe()` separately to consume a stream | Creates detached pipelines, hard to throttle or cancel | Return/compose publishers within the request lifecycle. |
| Reading entire files/bodies into byte arrays | Creates large copies and breaks streaming | Use `Flux<DataBuffer>` or streaming codecs. |
| Not limiting SSE client count | Each connection may hold its own subscription and buffer | Limit concurrent streams and set per-user/tenant quotas. |
| Returning 200 when producer is rejected on overflow | Client thinks event was accepted | Return 429/503 or an explicit error contract. |

## 14. Self-check questions

**Question 1.** By which signal is backpressure represented in Reactive Streams?  
**Answer:** The subscriber calls `Subscription.request(n)` to declare how many elements it wants; the publisher honors demand and emits no more than requested.

**Question 2.** Why do hot sources need an overflow policy?  
**Answer:** Hot sources can emit on their own clock/callbacks and do not pause when downstream reduces demand. Unconsumed data must be boundedly buffered, dropped, kept as latest, or rejected/errored.

**Question 3.** Does `limitRate(64)` mean at most 64 items per second?  
**Answer:** No. It regulates how Reactor issues requests in batches; it is not a time-based rate limiter.

**Question 4.** When is `onBackpressureLatest` used?  
**Answer:** When only the latest state matters, such as current temperature or dashboard state; intermediate values can be skipped.

**Question 5.** Why should unbounded buffers not be used?  
**Answer:** If the producer stays faster than the consumer over time, the queue grows without bound and can exhaust heap/direct memory.

**Question 6.** What does `flatMap(mapper, 8, 1)` control?  
**Answer:** At most eight inner publishers are processed concurrently with a prefetch of one element per inner publisher.

**Question 7.** What does `spring.codec.max-in-memory-size` limit?  
**Answer:** Limits the data codecs must buffer/aggregate in certain encode/decode operations; it does not create a universal byte quota for all raw streaming requests.

**Question 8.** What signal should the reactive pipeline receive when a client disconnects SSE?  
**Answer:** The subscriber can cancel; cancellation should propagate upstream to stop producers/queries and release resources.

**Question 9.** Why should you not retry continuously when a sink returns FAIL_OVERFLOW?  
**Answer:** The queue has no free space yet; retrying immediately keeps pressuring the system. Use backoff, throttling, a durable queue, or return an error for upstream to decide.

**Question 10.** Is a 64-item queue guaranteed to use little memory?  
**Answer:** No. You must account for average/maximum size per item, client count, object overhead, and buffers in other layers.

## Key takeaways

- Backpressure is demand-based flow control between publisher and subscriber; demand counts items, not bytes.
- Demand-respecting sources should allow backpressure to propagate upstream. Hot sources require explicit policies when consumers are slow.
- Buffers must be bounded. Choose buffer/drop/latest/error based on semantics; never silently discard critical business events.
- `limitRate` batches requests, not events per second. Use dedicated rate limiters when time-based quotas are needed.
- Bound concurrency/prefetch, body bytes, codec memory, item counts, connection counts, and timeouts to manage resource budgets.
- When clients cancel or queues overflow, propagate lifecycle signals properly; monitor queues, drops, overflows, latency, and memory for data-driven operations.

### References

1. [Reactive Streams Specification](https://www.reactive-streams.org/): publisher, subscriber, subscription, and demand.
2. [Project Reactor Reference – Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/backpressure.html): demand, backpressure operators, and handling hot sources.
3. [Project Reactor Flux Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `limitRate`, `onBackpressureBuffer`, `onBackpressureDrop`, `onBackpressureLatest`, and `flatMap`.
4. [Project Reactor Sinks Reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): creating hot sources, multicasting, and handling emit results.
5. [Spring Framework – WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): reactive servers, publishers, and WebFlux lifecycle.
6. [Spring Framework – WebFlux Codec Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): configuring message codecs and buffering limits.
7. [Spring Boot – Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): configuring `spring.codec.max-in-memory-size`.
