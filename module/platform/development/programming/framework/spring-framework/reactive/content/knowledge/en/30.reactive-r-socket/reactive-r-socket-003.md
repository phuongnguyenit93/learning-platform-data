# Protocol-Level Backpressure and Differences from HTTP

**Module:** Spring Framework – reactive  
**Parent topic:** RSocket  
**Focus:** How RSocket propagates consumption demand across the network via `REQUEST_N`, how it differs from TCP/HTTP flow control, and how to use it with Spring Reactor.

## 1. The problem: sender faster than receiver

Imagine service A produces 10,000 events/second, while service B processes only 100 events/second. If A sends continuously without regard for B, data accumulates in queues, increasing memory usage and latency, and eventually exhausting application resources. **Backpressure** is the mechanism for the receiver to express how much data it can currently accept and for the sender to adjust to that limit.

In Reactive Streams, a `Subscriber` not only receives `onNext(T)` but can also call `Subscription.request(n)`, requesting `n` more items. A demand-honoring `Publisher` will not emit beyond the currently granted count. For example, a subscriber requests 2 items, finishes consuming 2 items, and then requests 3 more items.

**Key differences:**

- **Project Reactor (`Flux`/`Mono`) within the same JVM:** `request(n)` is a signal between reactive components in a single process, propagating upstream through the operator chain.
- **RSocket:** turns that demand into **protocol-level signals** (`REQUEST_STREAM`, `REQUEST_CHANNEL`, `REQUEST_N`), allowing backpressure to cross network connections between requester and responder.
- **HTTP:** HTTP/1.1 has no standard way to request `n` more application objects; HTTP/2 has flow control, but grants credit in **bytes** via `WINDOW_UPDATE`, not in Reactor item counts.

Therefore, do not say "HTTP has no flow control." The accurate statement is **HTTP has network/byte-level throttling depending on version and transport, while RSocket builds per-item demand into the request stream/channel protocol**.

## 2. What is RSocket and where does backpressure live?

RSocket is a binary, asynchronous protocol supporting multiplexed streams and bidirectional communication over a transport connection such as TCP or WebSocket. After the connection is established and `SETUP` is exchanged, either side can send requests to the other; hence the protocol uses the terms **requester** (the side initiating an interaction) and **responder** (the side handling the interaction), rather than tying permanently to TCP client/server roles.

Four interaction models:

| Interaction | Exchange direction | Result | Per-item backpressure |
|---|---|---|---|
| Request–Response | One request, at most one response | `Mono<T>` | No multi-item request-N window needed for a single response |
| Fire-and-Forget | One-way, no response body | `Mono<Void>` on send API | No per-item response demand |
| Request–Stream | One request, many responses | `Flux<T>` | Yes, requester grants credit for responses |
| Request–Channel | Bidirectional data streams | Input `Flux<T>` and output `Flux<R>` | Yes, both directions have independent credit |

RSocket does not automatically guarantee every request succeeds: Fire-and-Forget is best-effort, and application errors can still occur; connections can drop and resources may require cleanup.

**Backpressure is not time-based pacing.** Demand n only specifies how many more items may be emitted, not "send one item every 100 ms" or total bytes. A 1 KiB item and a 10 MiB item both consume one unit of demand at the Reactive Streams layer, even though transport may require multiple frames/fragments.

## 3. From request(n) to REQUEST_N on the wire

RSocket uses **credit-based flow control**: the receiver grants credit in terms of how many `PAYLOAD` frames carrying `onNext` events may be sent; the sender may only emit within the granted credit.

The specification defines:

- `REQUEST_STREAM` carries an `Initial Request N` field: the initial number of response items the requester allows the responder to send.
- `REQUEST_CHANNEL` also carries `Initial Request N` for the **response stream**; the responder uses `REQUEST_N` to grant further sending credit for the requester's **request stream**.
- `REQUEST_N` is a frame granting additional credit for the corresponding stream after an interaction has started.
- The value `N` must be positive; the protocol field is 31-bit unsigned, up to `2^31 - 1` per value.
- Credit is **cumulative**: `request(3)` followed by `request(2)` yields a total allowance of 5 items, minus any already sent.
- A `PAYLOAD` carrying the `NEXT` flag counts as one item consuming credit. A frame signaling only `COMPLETE` is not a new item.

Conceptual request-stream example:

```text
Requester B                                  Responder A
    |                                              |
    | REQUEST_STREAM(initialRequestN=2) ---------->|
    |                                              |
    |<------------------------------- PAYLOAD #1   |  credit: 1
    |<------------------------------- PAYLOAD #2   |  credit: 0
    |                                              |  does not emit #3
    | REQUEST_N(N=3) ------------------------------>|
    |                                              |
    |<------------------------------- PAYLOAD #3   |  credit: 2
    |<------------------------------- PAYLOAD #4   |  credit: 1
    |<---------------- PAYLOAD #5 + COMPLETE        |  ends
    |                                              |
```

This illustrates the core logic. In applications using libraries, operators may **prefetch**, coalesce, or split demand, and an implementation may choose an initial request-N larger than what was just seen at the outermost subscriber. **Do not claim** that calling `thenRequest(2)` twice in a test will emit exactly two wire frames with N=2.

### 3.1. Why is there an initial request N?

If the responder has been granted zero credit, it cannot emit response items. To avoid sending a request frame followed by a separate credit frame before the first item, `REQUEST_STREAM` and `REQUEST_CHANNEL` embed initial credit directly in the interaction-opening frame. When credit runs low, the requester sends `REQUEST_N` to expand the window.

RSocket specifies credit and frame semantics without mandating when replenishment occurs; requesting in batches or per item is decided by the subscriber and library.

### 3.2. Credit is not a byte limit or an absolute memory bound

If 10 items are allowed, each item could be huge. You must combine it with:

- Payload/fragment size and codec limits.
- Concurrent stream and in-flight request limits.
- Pool/resource quotas and processing deadlines.
- Control over producers/hot sources that do not honor demand.
- Metrics for backlog, pending requests, latency, and memory.

Backpressure prevents emitting beyond demand, but does not replace capacity planning.

## 4. Request–Stream: throttling responses from the requester

In request-stream, the requester sends **one** request to open the stream; the responder returns multiple items.

Spring example:

```java
@Controller
class NumbersResponder {

    @MessageMapping("numbers.stream")
    public Flux<Integer> numbers(Integer count) {
        return Flux.range(1, count);
    }
}
```

Requester side:

```java
Flux<Integer> numbers = requester.route("numbers.stream")
        .data(5)
        .retrieveFlux(Integer.class);
```

`retrieveFlux` denotes a multi-value response, corresponding to request-stream when the input is a single item. `Flux.range` honors Reactive Streams demand. If the requester has not permitted more items, the RSocket implementation throttles responses transmitted over the connection.

Distinguish two layers:

1. `Flux.range` is the publisher producing numbers inside the responder process.
2. The RSocket protocol exchanges credit to regulate data between two processes.

When downstream changes demand, RSocket Java bridges the signals so the producer does not have to manipulate `REQUEST_N` frames directly.

## 5. Request–Channel: two independent backpressure directions

Request-channel has two streams:

- Requester → Responder: request items after the first message.
- Responder → Requester: response items.

Each direction must honor demand from the side **receiving** that direction. It is not a single shared credit counter.

```text
      REQUESTER                                    RESPONDER
   request Flux ---> REQUEST_CHANNEL + PAYLOAD ---> handle input Flux
                  <--- REQUEST_N for input items --
                  ----- next PAYLOAD if credited -->
                  <---- response PAYLOAD if credited
   response Flux  <--- response stream ----------------
   response demand -> REQUEST_N for response -------->
```

Per the specification, `REQUEST_CHANNEL` carries initial request-N for output responses, while the responder must send `REQUEST_N` to allow the requester to send further request `PAYLOAD` frames after the first frame. In implementations, prefetching or buffering may cause observed wire frames not to match each application `request(n)` call one-for-one.

Responder example:

```java
@Controller
class TransformResponder {

    @MessageMapping("labels.channel")
    public Flux<String> transform(Flux<Integer> input) {
        return input.map(number -> "label-" + number);
    }
}
```

Requester:

```java
Flux<Integer> input = Flux.range(1, 5);

Flux<String> output = requester
        .route("labels.channel")
        .data(input, Integer.class)
        .retrieveFlux(String.class);
```

This snippet uses Spring `RSocketRequester`; running it requires a connected RSocket server/client and appropriate codecs. `data(Publisher, elementClass)` specifies the type of each request item. Because input is multi-value and output is multi-value, Spring selects a channel interaction.

**Common mistake:** treating request-channel like a plain WebSocket chat with only "send" and "receive." WebSocket itself does not standardize per-application-message `request(n)` credits; when RSocket runs over WebSocket, it is the RSocket layer that provides those semantics.

## 6. Request–Response and Fire-and-Forget are not like streams

**Request–Response** receives at most one response. It does not need `REQUEST_N` replenishment like request-stream. The subscriber can still cancel the interaction if it no longer wishes to wait for the result.

**Fire-and-Forget** sends a message without a response payload for the requester to throttle. Completion of the send call does not prove the responder executed business logic or committed data.

```java
Mono<Receipt> receipt = requester.route("orders.create")
        .data(command)
        .retrieveMono(Receipt.class);

Mono<Void> acknowledgement = requester.route("telemetry.oneway")
        .data(event)
        .send();
```

Both snippets assume the DTOs and routes exist. For commands with critical side effects, do not confuse fire-and-forget with durable delivery. If execution guarantees are needed, idempotency, retries, business acknowledgments, or durable queues must be designed separately.

## 7. Cancellation and stream-level terminal signals

Reactive Streams distinguishes:

- `onComplete`: the stream has completed.
- `onError`: the stream has failed.
- `Subscription.cancel()`: the subscriber no longer wants to receive items.

RSocket provides `CANCEL` and `ERROR` frames corresponding to interaction-level lifecycles. If the requester cancels a request-stream before receiving all items, the responder must stop emitting per contract and release resources tied to the subscription.

Example:

```java
return repository.streamByCategory(category)
        .doOnRequest(n -> metrics.recordDemand(n))
        .doOnCancel(() -> metrics.incrementCancelled())
        .doFinally(signal -> metrics.recordTerminal(signal.name()));
```

`doOnCancel` observes cancellation; `doFinally` observes complete, error, and cancel alike. If a publisher holds a cursor/connection, use `Flux.using` or `Flux.usingWhen` to clean up according to the subscription lifecycle, not just `doOnError`.

**Cancellation does not automatically roll back side effects.** Database queries or network calls that already ran may not be undone. If a producer cannot stop immediately (legacy blocking calls or hot sources), cancel signals must still be handled and resources must have dedicated timeouts/cleanup.

## 8. At which layer do RSocket and HTTP differ?

To compare fairly, separate **application items**, **protocol streams**, and **network bytes**:

| Criterion | RSocket | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|---|
| Request semantics | Four interaction models | Traditional request–response | Request–response, multiplexed streams | Request–response over QUIC |
| Multi-item data | `REQUEST_STREAM`/`REQUEST_CHANNEL` | Chunked/stream responses possible | Response DATA on HTTP/2 stream | Response DATA on QUIC stream |
| Per-**item** credit | Yes, `Initial Request N` / `REQUEST_N` | Not standardized in HTTP | Not standardized in HTTP/2 | Not standardized in HTTP/3 |
| Per-**byte** flow control | Handled by underlying transport | TCP receive window | Byte-level `WINDOW_UPDATE` per stream and connection | QUIC flow control per stream and connection |
| Bidirectional on one connection | Yes, symmetric protocol; bidirectional channel | No standard request-channel | Multiplexes HTTP streams, request/response semantics | Multiplexes over QUIC, HTTP semantics |
| Canceling interactions | `CANCEL` | Close/abort connection or app logic | `RST_STREAM` and request abort depending on case | Cancel/reset stream in QUIC/HTTP semantics |
| Nature of backpressure | Demand by application message count | Buffers and network flow control | Byte credit, hop-by-hop | Byte credit in QUIC and transport |

The table describes **standard mechanisms**, without denying that libraries may implement extra throttling. WebFlux can propagate backpressure from subscribers down to sockets on certain paths and supports returning `Flux` over HTTP, but HTTP does not define a `REQUEST_N` frame per business object.

### 8.1. HTTP/1.1 and TCP

HTTP/1.1 can send large responses using chunked transfer encoding or content-length, and applications can emit chunks incrementally. When the receiver is slow, the TCP receive window, socket write readiness, and buffering affect sender throughput.

However, TCP only knows bytes. TCP does not know JSON object A or event B. Upper layers decide how to parse and bound queues. TCP flow control does not directly express "give me the next 3 records."

If a server produces data faster than the socket can write, the framework can reduce demand on the in-process publisher. Yet that is how an implementation bridges local Reactive Streams with transport, not a standard HTTP clause for application-item credit.

### 8.2. HTTP/2: WINDOW_UPDATE is not REQUEST_N

RFC 9113 `5.2` and `6.9` define HTTP/2 flow control in **octets/bytes**:

- Each HTTP/2 stream has its own window.
- There is a window for the entire connection.
- Receivers send `WINDOW_UPDATE` to increase the number of bytes permitted for transmission.
- Flow control is **hop-by-hop**: intermediaries can maintain separate windows with each peer and do not forward credits end-to-end automatically.
- Only `DATA` frames are governed by the flow control specified in this RFC.
- The default initial window size is 65,535 bytes (adjustable per protocol).

For example, if a client grants 32 KiB more, the server may send up to 32 KiB more `DATA` under that window, not 32 JSON objects. One application item can span multiple DATA frames, and conversely one DATA frame can hold multiple items.

RSocket `REQUEST_N(3)` means something different: the receiver permits 3 more messages/`onNext` items of the RSocket stream, regardless of how many frames or bytes each message later requires.

**Do not say HTTP/2 lacks backpressure.** It has flow control at the transport/framing layer, but it does not standardize Reactive Streams `request(n)` at the business-message layer.

### 8.3. HTTP/3: QUIC flow control is byte-based

HTTP/3 carries HTTP over QUIC. QUIC has byte-based flow control at connection and stream levels, with credits such as `MAX_DATA`/`MAX_STREAM_DATA`. This is not credit counted in JSON objects or Reactor elements.

HTTP/3 does not automatically turn an endpoint into an RSocket request-stream. If an application needs protocol-level item demand, it needs extra application-layer semantics or a protocol like RSocket.

### 8.4. SSE, NDJSON, gRPC, and WebSocket

- **SSE over HTTP:** long-lived response of `text/event-stream` events. Browser `EventSource` has no standard frame to send `request(n)` to the server.
- **NDJSON:** multiple newline-delimited JSON objects in one response; clients can decode into `Flux<T>`, but line framing does not create application credits.
- **gRPC streaming:** uses HTTP/2 and has flow control mechanisms, though HTTP/2 `WINDOW_UPDATE` does not automatically become Reactive Streams item request-N. Examine the semantics of the specific gRPC library and application.
- **WebSocket:** supports bidirectional message transport; WebSocket itself does not define `REQUEST_N`. RSocket can run **over WebSocket**, in which case the RSocket layer provides per-message credit.

Do not pick a transport solely because "WebSocket is bidirectional" or "HTTP/2 multiplexes"; evaluate whether the application needs one-way streaming, duplex channels, per-message credit, browser/gateway compatibility, authentication, or observability.

## 9. Backpressure traversing multiple layers in real systems

A pipeline may include:

```text
Database / Broker
       |
       v
Publisher in server  -- Reactive Streams request(n) -->
       |
       v
RSocket responder
       |
       |  REQUEST_N / PAYLOAD over network
       v
RSocket requester
       |
       v
Reactor operators (map / filter / flatMap)
       |
       v
Final subscriber
```

Libraries can propagate demand backward from the final subscriber across the network to the source, but end-to-end backpressure only works when **every segment** respects demand. Points that can break the mechanism:

1. A hot source emitting regardless of how much the subscriber wants.
2. A message broker pushing into an unbounded queue.
3. `onBackpressureBuffer` allowing too many items to accumulate.
4. `publishOn` or `flatMap` creating prefetch/inner subscriptions different from externally observed demand.
5. Blocking APIs reading an entire result set before creating a Flux.
6. Codecs aggregating large bodies into a single object before publishing.
7. Producers calling `subscribe()` themselves and detaching from the request lifecycle.

RSocket cannot automatically turn an uncooperative hot source into a cold publisher. For data that cannot slow down, you need an explicit policy: drop, latest, bounded buffer, error, sampling, or a durable queue with quotas.

## 10. Prefetch, limitRate, and actual REQUEST_N counts

Reactor has several operators that adjust demand. For example:

```java
Flux<Event> processed = requester.route("events.live")
        .retrieveFlux(Event.class)
        .limitRate(16)
        .concatMap(event -> saveEvent(event));
```

`limitRate(16)` changes how the operator requests from upstream in batches; `concatMap` processes sequentially. Yet signals pass through `RSocketRequester`, codecs, and internal operators. Do not assume that each `request(n)` at the subscriber corresponds directly to one `REQUEST_N(N=n)` frame.

`doOnRequest` is a tool to observe demand **at the operator's position**:

```java
return Flux.range(1, 20)
        .doOnRequest(n ->
                log.info("source has received demand={}", n));
```

This log is not a packet capture and does not prove wire-level frames. To verify actual network credits, use an RSocket transport instrument/interceptor or appropriate packet/frame tracing, cross-checking against the spec and library version.

### 10.1. Do not equate request(Long.MAX_VALUE) with an RSocket integer

Reactive Streams inside the JVM allows `Subscription.request(long)` and uses `Long.MAX_VALUE` to represent unbounded demand. Meanwhile, RSocket's `REQUEST_N` frame has a positive 31-bit field. The library is responsible for translating large demand into a valid wire-level representation.

Never cast a `long` demand directly to `int` and send a frame; it can overflow or produce an invalid N=0.

## 11. Runnable Java 17+ program: Spring Boot RSocket + StepVerifier

The example below uses Spring Boot 3.5.16, Java 17, and RSocket TCP. The server provides a `numbers.stream` route returning numbers 1 through 5. An integration test creates a real client, calls the route with `RSocketRequester`, and uses `StepVerifier` to request items in batches. A separate test observes local Reactor demand to distinguish it from wire credit frames.

Structure:

```text
rsocket-backpressure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/RsocketBackpressureApplication.java
    │   ├── java/demo/NumbersResponder.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/RsocketBackpressureIntegrationTest.java
```

### 11.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>rsocket-backpressure-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
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

`spring-boot-starter-rsocket` provides Spring Messaging RSocket, RSocket Java, Reactor Netty, and Boot-managed codecs. `reactor-test` is only needed for tests. `spring-boot-starter-webflux` is not needed if the application only serves RSocket TCP and has no HTTP endpoints.

### 11.2. application.properties

```properties
spring.application.name=rsocket-backpressure-demo
spring.main.web-application-type=none
spring.rsocket.server.address=127.0.0.1
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
```

The RSocket TCP server runs standalone on port 7000. Setting `web-application-type=none` explicitly tells the project no HTTP web server is needed; the RSocket server is still auto-configured via `spring.rsocket.server.port`.

Because the test uses a fixed port, ensure 7000 is not occupied by another service. In parallel CI environments, you can use a random port and read the actual bound port through the test infrastructure instead of hardcoding a value.

### 11.3. RsocketBackpressureApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RsocketBackpressureApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RsocketBackpressureApplication.class, args);
    }
}
```

### 11.4. NumbersResponder.java

```java
package demo;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;

@Controller
public class NumbersResponder {

    @MessageMapping("numbers.stream")
    public Flux<Integer> numbers(Integer count) {
        return Flux.range(1, count)
                .doOnRequest(n ->
                        System.out.println("source demand=" + n))
                .doOnCancel(() ->
                        System.out.println("stream cancelled"));
    }
}
```

`@MessageMapping` declares an RSocket route, not an HTTP `@GetMapping`. The result is `Flux<Integer>`; with a single input payload and multi-item output, Spring uses request-stream.

`Flux.range` generates numbers on demand. `doOnRequest` only logs the demand observed by the source publisher; it does not necessarily equal the actual `REQUEST_N` frames. `doOnCancel` runs when the subscription is canceled.

### 11.5. RsocketBackpressureIntegrationTest.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.rsocket.RSocketRequester;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class RsocketBackpressureIntegrationTest {

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    @Test
    void requestStreamHonorsDownstreamDemand() {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", 7000);

        try {
            Flux<Integer> response = requester
                    .route("numbers.stream")
                    .data(5)
                    .retrieveFlux(Integer.class);

            StepVerifier.create(response, 0)
                    .thenRequest(2)
                    .expectNext(1, 2)
                    .thenRequest(3)
                    .expectNext(3, 4, 5)
                    .expectComplete()
                    .verify(Duration.ofSeconds(10));
        }
        finally {
            requester.rsocket().dispose();
        }
    }

    @Test
    void localReactiveStreamsDemandCanBeMeasured() {
        AtomicLong requested = new AtomicLong();

        Flux<Integer> source = Flux.range(1, 5)
                .doOnRequest(requested::addAndGet);

        StepVerifier.create(source, 0)
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        assertThat(requested).hasValue(5);
    }
}
```

Run tests with JDK 17+ and Maven:

```bash
mvn test
```

**Expected result:** Maven exits with code 0, two tests pass, and zero failures occur. Server-side `doOnRequest` console output may print numbers other than 2 and 3 because the RSocket implementation can prefetch/replenish according to internal policy. Do not treat server log counts as fixed expected stdout.

If you only want to start the server, run:

```bash
mvn spring-boot:run
```

The application opens RSocket TCP port 7000 and has no HTTP `GET /numbers.stream`. To call the route, use `RSocketRequester` or a compatible RSocket client, not `curl http://localhost:7000`.

### 11.6. What does the test prove and what does it not prove?

The network test proves a caller can subscribe with an initial demand of 0, increase demand via `thenRequest`, and receive all items in order. It exercises the Reactive Streams interface and a real RSocket interaction, **but does not assert that the actual wire frames captured were `REQUEST_N(2)` then `REQUEST_N(3)`**.

The local `Flux.range` test verifies that a publisher honors demand and the total requests observed by `doOnRequest` equal 5. Since it does not go through RSocket, the local test says nothing about wire frames.

To verify exact protocol frames, you must use an RSocket frame interceptor/instrumentation or a suitable transport-level integration test and check against the specification. Do not treat a plain `StepVerifier` as a packet analyzer.

## 12. When combining RSocket with WebFlux HTTP

An application can expose both endpoints:

- WebFlux HTTP for browsers, REST, SSE, or NDJSON.
- RSocket for service-to-service communication or bidirectional streams with per-item credit.

Boot configuration to run RSocket over WebSocket inside a WebFlux server:

```properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
```

This configures RSocket-over-WebSocket attached to the Reactor Netty web server; the application needs an appropriate WebFlux server. For a standalone RSocket TCP server, set `spring.rsocket.server.port` and `transport=tcp`.

Do not confuse an arbitrary WebSocket endpoint with an RSocket endpoint. RSocket-over-WebSocket still uses `SETUP`, `REQUEST_STREAM`, `REQUEST_N`, and RSocket frames; raw WebSocket does not generate those frames by itself.

If the application needs to expose the same data over both HTTP and RSocket, share a **reactive service** rather than forcing both protocols to use the same response type:

```java
@Service
class EventService {
    public Flux<Event> streamEvents() {
        return repository.findEvents();
    }
}
```

An HTTP controller can serialize `Flux<Event>` to NDJSON/SSE; an RSocket responder returns `Flux<Event>` over a route. The source will receive different demand depending on subscriber, operators, and transport. Do not assume sharing a service gives HTTP protocol-level `REQUEST_N`.

## 13. RSocket LEASE vs. request-N

The specification also defines `LEASE` to limit **the number of new interactions** a requester may initiate within a time window (TTL). This is a request-admission control mechanism at the connection/request level.

Distinction:

| Mechanism | What is limited | Example |
|---|---|---|
| `REQUEST_N` | Number of response/request-channel items within a stream | Allow the next 3 events |
| `LEASE` | Number of new interactions opened within a TTL | Allow opening 10 more requests over 5 seconds |
| Connection pool/quota | Number of connections or active requests | Maximum 50 connections |
| Rate limiter | Number of operations over a time policy | 100 requests/second |
| Transport flow control | Number of bytes transferable | HTTP/2 WINDOW_UPDATE 32 KiB |

`LEASE` does not replace `REQUEST_N`. A requester may be permitted by a lease to open a request-stream yet still have only 2 response-item credits. Implementations may not enable leasing by default; check your specific configuration/version.

## 14. Limits: backpressure does not solve every problem

RSocket backpressure is meaningful when the application has demand-honoring producers. It **does not automatically guarantee**:

- Consistently low end-to-end latency.
- Broker/database queues disappearing on their own.
- Large payloads not exhausting memory.
- Side effects rolling back when a client cancels.
- Fair CPU and connection allocation across streams automatically.
- A hot producer stopping event generation when a subscriber is slow.
- Streams stalled for lack of demand timing out automatically.
- Dropped connections resuming successfully in every case.

RSocket provides `KEEPALIVE` to help detect inactive connections and optional `RESUME` when supported by implementations/protocol extensions. Yet keepalive, resume, and request-N are distinct mechanisms. Do not treat resume as exactly-once processing or a durable message queue.

If no further `REQUEST_N` arrives, a stream can stop sending data while waiting for demand. The specification does not mandate a separate timeout purely for lack of demand; the application needs deadlines and policies to avoid holding resources indefinitely.

## 15. How to design a slow consumer safely

### 15.1. Reduce demand instead of unbounded buffering

Suppose processing each event takes 100 ms. The consumer should keep concurrency bounded:

```java
Flux<Processed> processed = requester.route("events.stream")
        .retrieveFlux(Event.class)
        .concatMap(event -> processEvent(event));
```

`concatMap` preserves processing order. If concurrency is desired, use `flatMap` with a cap:

```java
Flux<Processed> processed = requester.route("events.stream")
        .retrieveFlux(Event.class)
        .flatMap(event -> processEvent(event), 4);
```

A concurrency limit of 4 does not mean a wire frame `REQUEST_N` with N=4; Reactor also performs prefetch/replenishment. Measure queue, throughput, and latency metrics.

### 15.2. Hot sources must have an overload policy

If a data source emits independently of demand:

```java
Flux<Event> hot = eventBroker.liveFeed();
```

When the broker adapter cannot slow down, define an explicit policy:

- Bounded buffer and reject on overflow.
- Drop newest, drop oldest, or keep latest if data loss is acceptable.
- Sampling/rate reduction.
- Persist events to a durable queue/broker with quotas.
- Isolate slow consumers from fast consumers when multiple subscribers exist.

Never add an unbounded `onBackpressureBuffer()` by default assuming RSocket will protect the heap. Buffering merely moves the problem into memory.

### 15.3. Cancellation and resource ownership

If a stream uses a connection/cursor:

```java
Flux<Row> rows = Flux.usingWhen(
        connectionFactory.acquire(),
        connection -> queryRows(connection),
        connection -> connection.closeAsync(),
        (connection, error) -> connection.closeAsync(),
        connection -> connection.closeAsync());
```

This is an abstract snippet: `acquire`, `queryRows`, and `closeAsync` represent concrete resource APIs. `usingWhen` declares async cleanup on complete, error, or cancel. Tie resources to each subscription rather than creating a single shared cursor across all clients.

### 15.4. Message protection and size limits

A `Flux<Payload>` response can produce very many small items or a few huge items. Limit:

- Message/fragment sizes.
- Running interactions and concurrent subscribers.
- Processing timeouts, idle timeouts, and connection policies.
- Codec memory and buffered data.
- Payload tracing/logging via sampling; avoid logging PII or tokens.
- CPU spent encoding/decoding.

Set limits matching the business contract. Do not optimize a single request-N number in isolation.

## 16. Observing and testing backpressure

Test at three levels:

**Level 1 — In-process Reactor publisher.**

- `StepVerifier.create(publisher, 0)` initializes with zero demand.
- `thenRequest(n)` increases demand.
- `expectNext(...)` confirms no missing, duplicate, or out-of-order items.
- `thenCancel()` verifies the cancellation path.
- `doOnRequest` and `doFinally` observe the source.

**Level 2 — RSocket over real TCP/WebSocket.**

- Use separate requester and responder or an embedded RSocket server.
- Execute real request-stream/channel flows.
- Verify correct data, cancellation, errors, and cleanup.
- Simulate a slow consumer with explicit test deadlines.
- Observe queues, bytes, active streams, and resource release.

**Level 3 — Protocol framing.**

- Instrument an RSocket frame interceptor or transport-level tracing.
- Verify `REQUEST_STREAM Initial Request N` and `REQUEST_N` increment credit properly.
- Verify the responder never emits `NEXT` beyond remaining credit.
- Verify `CANCEL` frees streams and resources.
- Verify channels maintain independent credits in both directions.
- Verify message fragmentation and payload frames are not miscounted as application items.

Do not use `Thread.sleep` to verify exact frame ordering. Use `StepVerifier`, latches/probes, or interceptors with timeouts and conditional assertions. If a test must prove an implementation does not emit before receiving credit, instrument at the frame layer rather than inferring from application logs.

## 17. Common mistakes

1. **Saying "HTTP has no backpressure."** HTTP/2 has byte-level flow control; TCP also has a receive window. The difference is application-item demand.
2. **Confusing `WINDOW_UPDATE` with `REQUEST_N`.** One grants bytes; the other grants message/`onNext` counts.
3. **Confusing `Request–Stream` with `Request–Channel`.** Channel has input and output streams requiring independent credits.
4. **Thinking Fire-and-Forget always succeeds.** There is no business response, and messages can be lost or fail.
5. **Assuming `request(n)` always maps to a single frame with N=n.** Prefetch/replenishment can change actual wire frames emitted.
6. **Assuming one PAYLOAD fragment is always one item.** Distinguish fragmentation from logical `onNext` events.
7. **Not validating N.** REQUEST_N must be positive and bounded by a 31-bit field.
8. **Treating credit as a byte limit.** One huge item can still consume vast memory and fragment.
9. **Using unbounded `onBackpressureBuffer()`.** Can trigger `OutOfMemoryError`.
10. **Calling `subscribe()` manually inside a service.** Detaches the subscription from the lifecycle, breaking cancellation/error propagation.
11. **Blocking the event loop with `block()` or JDBC.** Can slow down many other streams.
12. **Treating server `doOnRequest` logs as a wire trace.** They only reflect demand at that operator's position.
13. **Not cleaning up on cancel.** Resources can remain held after the subscriber stops receiving.
14. **Thinking cancel undoes all side effects.** Side effects may have already committed.
15. **Lumping lease and request-N together.** Lease caps new requests; request-N caps items within a stream.
16. **Treating WebSocket as RSocket.** Raw WebSocket does not define request-N on its own.
17. **Using `collectList()` on an infinite SSE stream.** The publisher may never complete and memory will grow.
18. **Not testing hot producers.** Demand may not reach an uncooperative source; an overload policy is required.
19. **Choosing RSocket for every REST API.** HTTP remains simpler when browser/cache/CDN support and public request-response APIs are needed.
20. **Confusing multiplexing with resource fairness.** Multiplexing lets streams share a connection without automatically guaranteeing fairness or CPU quotas.
21. **Designing timeouts only at TCP level.** Streams can stall indefinitely waiting for demand; application deadlines and cleanup policies are needed.
22. **Testing only received data.** Also test cancellation, outstanding demand, queues/buffers, memory, and connection lifecycles.
23. **Assuming gRPC streams equal RSocket REQUEST_N.** Inspect the exact semantics and flow-control layer of your library.
24. **Ignoring security/authentication on long-lived connections.** RSocket routes and metadata can carry sensitive data; enforce authentication, authorization, and lease/DoS limits.

## 18. Checklist when choosing RSocket over HTTP

Before deciding to use RSocket:

- Do you genuinely need multiple messages per interaction, long-lived streaming, or duplex channels?
- Does the consumer need to throttle the source with **per-item** credit at the protocol level?
- Is the data source cold/backpressure-aware or hot/unbounded?
- Do your team and clients support RSocket, or do you need browsers/CDNs/HTTP API gateways?
- Do you need request-response, stream, or channel? Did you pick the right interaction?
- How large are typical payloads in bytes? Are fragmentation and memory limits appropriate?
- Are you measuring prefetch and demand at operators instead of guessing wire frames?
- Are you testing credits via interceptors when you need to prove wire-protocol behavior?
- Is cleanup implemented for cancel, error, timeout, and disconnect?
- Are policies in place for slow subscribers, full buffers, and hot publishers?
- Do you need leasing to cap new interactions, distinct from request-N?
- Do you need keepalive, resume, reconnect, and idempotency per the business contract?
- Are stream counts, connection lifetimes, and per-client quotas bounded?
- Are latency, demand, queue depth, memory, active streams, and transport errors observed?
- Is it compatible with network/proxy/TLS, securing routes and metadata?
- Would HTTP/2, SSE, or NDJSON already be simpler and sufficient?

**Takeaway:** RSocket performs **per-message** backpressure in request-stream/channel using `Initial Request N` and `REQUEST_N`. Those credits bridge Reactive Streams semantics across network boundaries. HTTP/1.1 relies on TCP flow control, HTTP/2 uses byte-based `WINDOW_UPDATE`, and HTTP/3 uses QUIC byte credits; none standardize `request(n)` per application item. RSocket still requires timeouts, payload/queue bounds, cancellation, and proper cleanup. Observing `doOnRequest` helps understand demand, but does not replace protocol-frame tracing.

## References

- RSocket Protocol Specification — [REQUEST_STREAM, REQUEST_CHANNEL, REQUEST_N, Flow Control and Lease](https://github.com/rsocket/rsocket/blob/master/Protocol.md).
- RSocket — [Protocol Overview](https://rsocket.io/about/protocol/).
- Spring Framework — [RSocket reference: interactions, requester and annotated responder](https://docs.spring.io/spring-framework/reference/rsocket.html).
- Spring Boot 3.5 — [RSocket auto-configuration and server/client setup](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html).
- Project Reactor — [Backpressure and Reactive Streams](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html).
- Project Reactor — [StepVerifier testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- IETF RFC 9113 — [HTTP/2 `5.2 Flow Control and `6.9 WINDOW_UPDATE](https://www.rfc-editor.org/rfc/rfc9113.html).
- IETF RFC 9000 — [QUIC Transport Flow Control](https://www.rfc-editor.org/rfc/rfc9000.html).
