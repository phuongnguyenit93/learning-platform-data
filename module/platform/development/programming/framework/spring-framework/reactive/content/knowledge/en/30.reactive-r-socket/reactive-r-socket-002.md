# RSocket: Fire-and-forget, Request-response, Request-stream, and Request-channel

**Module:** Spring Framework – reactive  
**Parent topic:** RSocket  
**Topic:** Fire-and-forget, request-response, request-stream, and request-channel

## Learning Objectives

After this lesson, you will be able to:

1. Explain RSocket as an asynchronous, full-duplex application protocol that multiplexes multiple requests over a single TCP/WebSocket connection with Reactive Streams semantics.
2. Accurately distinguish the four interaction models based on **number of input messages** and **number of output messages**, without confusing them with the four HTTP methods.
3. Evaluate the meaning of fire-and-forget: completion of sending does not equate to successful processing.
4. Write request-response with `Mono<T>`, request-stream with `Flux<T>`, and request-channel with two streams capable of operating concurrently.
5. Understand `REQUEST_N`, backpressure, `CANCEL`, `COMPLETE`, and `ERROR`; know when to stop upstream and release resources.
6. Map `@MessageMapping` on the responder side and `RSocketRequester` on the requester side in Spring Boot 3.
7. Run a Java 17+ example covering all four models over TCP and verify handlers with Reactor Test.
8. Choose the right model for business requirements, reliability, error handling, load limits, and security.

## 1. Foundation: RSocket transmits messages instead of traditional HTTP responses

RSocket is an **application protocol** running over byte-stream transports such as TCP or WebSocket. Once a connection is established, either side can initiate requests to the other; therefore, the accurate terms are **requester** (the side opening an interaction) and **responder** (the side serving an interaction), rather than fixed HTTP client and HTTP server roles.

One RSocket connection can carry multiple independent interactions, distinguished by stream IDs. Frames from multiple streams are multiplexed over the same physical connection. RSocket has data payloads, metadata (such as routes), framing, flow control, and lifecycle signals; it **is not the HTTP protocol**. When running over WebSocket, WebSocket is only the transport, while request-response/request-stream remain RSocket's models.

```text
                 One RSocket connection (TCP or WebSocket)
Requester                                                        Responder
   |                                                                 |
   |--- REQUEST_RESPONSE (stream 1) -------------------------------->|
   |--- REQUEST_STREAM   (stream 3, demand=N) ---------------------->|
   |<-- PAYLOAD           (stream 3) ---------------------------------|
   |<-- PAYLOAD           (stream 1, response+complete) -------------|
   |--- REQUEST_FNF      (stream 5) -------------------------------->|
   |--- REQUEST_CHANNEL  (stream 7, outbound data) ----------------->|
   |<-- PAYLOAD           (stream 7, inbound data) ------------------|
   |                                                                 |
```

RSocket uses Reactive Streams to propagate demand between requester and responder. When the responder has a large `Flux`, the requester can request n items instead of forcing the server to push infinitely; this is especially important for long-lived streams.

### 1.1. SETUP, route, and payload

A client establishes a TCP/WebSocket connection and exchanges `SETUP` to negotiate connection details such as data and metadata MIME types. Each interaction typically carries a route (e.g., `orders.lookup`) in the initial metadata and a data payload (e.g., an ID or JSON object).

In Spring:

- `@MessageMapping("orders.lookup")` declares the route on the responder side.
- `requester.route("orders.lookup")` puts the route into request metadata.
- `data(...)` supplies the data payload.
- `RSocketStrategies` manages codecs and decodes payloads into Java types.
- `RSocketRequester.Builder` helps build a requester and connect via TCP/WebSocket.

A route is **not an HTTP URL**, and `@MessageMapping` is not `@GetMapping`. The protocol can use dot-separated hierarchical route names.

## 2. Comparison table of the four models

| Model | Input requester → responder | Output responder → requester | Spring requester API | Common responder API | Real-world example |
| --- | --- | --- | --- | --- | --- |
| **Fire-and-forget (FNF)** | 1 message | No response payload | `route(...).data(x).send(): Mono<Void>` | `@MessageMapping` returning `void` or `Mono<Void>` | Non-critical telemetry, loss-tolerant events. |
| **Request-response (RR)** | 1 message | At most 1 result / error | `retrieveMono(T.class)` | Takes object, returns `Mono<T>` | Account lookup, status check. |
| **Request-stream (RS)** | 1 message | 0..N results over time | `retrieveFlux(T.class)` | Takes object, returns `Flux<T>` | Continuous price quotes, batched reads, location updates. |
| **Request-channel (RC)** | A stream of 1..N messages | An independent stream of 0..M messages | `data(Flux<X>, X.class).retrieveFlux(Y.class)` | Takes `Flux<X>`, returns `Flux<Y>` | Chat, interactive control/monitoring, bidirectional telemetry. |

**Key takeaway:** Request-channel does not have to be 1 request ↔ 1 response. Both sides have their own streams and can emit multiple signals independently in time. In contrast, request-stream has only **one** initial request payload, followed by multiple responses.

Some `@MessageMapping` methods with the same `void` or `Mono<Void>` signature can serve interactions that return no payload, but **the request type initiated by the requester** determines the actual interaction frame. Do not infer the model solely from the method name.

## 3. Fire-and-forget: one-way send, no business result

### 3.1. Sequence

```text
Requester                                    Responder
    |                                            |
    |--- REQUEST_FNF(data, route) -------------->|
    |                                            | (may process)
    |                                            |
    |  No response PAYLOAD for this request      |
```

The requester does not wait for a response payload. In Spring, `send()` returns `Mono<Void>`; completion of that Mono indicates sending succeeded from the transport/client perspective, **not confirmation that the responder processed it, wrote to a database, or committed a transaction**.

Example of sending non-critical telemetry:

```java
Mono<Void> sent = requester.route("metrics.sample")
        .data(new MetricSample("cpu", 62))
        .send();

sent.subscribe(); // Start sending; not proof of successful processing.
```

`MetricSample` is a hypothetical DTO in this illustration. In production applications, you should control errors and subscription lifecycles instead of calling `subscribe()` casually without tracking.

The responder can be:

```java
@Controller
class MetricResponder {
    @MessageMapping("metrics.sample")
    public void consume(MetricSample metric) {
        // Example: write to a bounded buffer.
    }
}
```

### 3.2. What FNF does not guarantee

FNF is best-effort. The server might not have processed the message even though the requester completed `send()`; the connection may fail, SETUP may be rejected, the handler may reject the payload, or the application may crash before committing.

Because there is no response in the same interaction:

- The requester receives no resource ID or business processing status.
- Exceptions occurring in the responder's business handler cannot be sent back as a response to FNF.
- Do not use FNF as proof that money was deducted, an order was recorded, or an email was sent.

If confirmation is needed, use request-response with a clearly defined `accepted/processed` result. If durable delivery and retries are required, consider a queue/broker, outbox pattern, or idempotency mechanisms rather than assuming RSocket persists messages to disk itself.

### 3.3. When to use

Use for sampled logs, non-critical statistics updates, signals the application can afford to drop on error, or events already durably stored elsewhere before emission. Do not use for business operations requiring exactly-once guarantees.

## 4. Request-response: one request, at most one result

### 4.1. Sequence

```text
Requester                                    Responder
    |                                            |
    |--- REQUEST_RESPONSE(query) --------------->|
    |                                            | lookup
    |<-- PAYLOAD(result) + COMPLETE -------------|
    |                  or ERROR                  |
```

In Spring, `retrieveMono(T.class)` corresponds to a single response. `Mono<T>` represents 0 or 1 data item, followed by complete or error. The response may be empty depending on the contract; do not treat `Mono.empty()` as equivalent to "not found" unless defined by business rules.

Example:

```java
Mono<UserView> result = requester.route("users.byId")
        .data(new UserQuery("u-42"))
        .retrieveMono(UserView.class)
        .timeout(Duration.ofSeconds(3));
```

The DTOs here only illustrate the structure. A typical responder:

```java
@MessageMapping("users.byId")
public Mono<UserView> findUser(UserQuery query) {
    return userService.findById(query.id());
}
```

### 4.2. Error handling and deadlines

- `onErrorResume` can provide a fallback when the remote returns an error or the connection fails; only fall back on known error types.
- `timeout` sets a wait limit on the caller. It can cancel the subscription, but **does not prove responder-side effects were rolled back**.
- Retries are safer for read-only queries. For create/update commands, you need idempotency keys, unique constraints, or deduplication mechanisms.
- If the server returns `Mono.empty()`, the caller needs a clear convention: is empty valid, not found, or a business error? You can use a response DTO with status or `switchIfEmpty(Mono.error(...))`.

Request-response fits concise RPCs, acknowledging an operation, fetching configuration, checking an account, or computations returning a single result.

## 5. Request-stream: one request, many results

### 5.1. Sequence and demand

```text
Requester                                    Responder
    |                                            |
    |--- REQUEST_STREAM(input, initial N=2) ---->|
    |<-- PAYLOAD(item 1) ------------------------|
    |<-- PAYLOAD(item 2) ------------------------|
    |--- REQUEST_N(3) --------------------------->|
    |<-- PAYLOAD(item 3) ------------------------|
    |<-- PAYLOAD(item 4) ------------------------|
    |<-- PAYLOAD(item 5) ------------------------|
    |<-- COMPLETE -------------------------------|
```

The numbers N above are a conceptual diagram; libraries may prefetch or batch demand differently. RSocket supports `REQUEST_N` to express how many items downstream can receive, rather than the server pushing infinitely regardless of consumption capacity. `CANCEL` can stop the stream before completion.

Example:

```java
Flux<PriceQuote> quotes = requester.route("prices.watch")
        .data(new PriceFilter("BTC"))
        .retrieveFlux(PriceQuote.class);

// Caller can stop once enough data has arrived.
Mono<List<PriceQuote>> firstFive = quotes.take(5).collectList();
```

Responder:

```java
@MessageMapping("prices.watch")
public Flux<PriceQuote> watch(PriceFilter filter) {
    return quoteService.watch(filter.symbol());
}
```

### 5.2. Completion, cancellation, and hot sources

Request-stream can be finite or long-lived. For finite streams, the responder emits `COMPLETE` when done. For live streams with no end point, the caller must manage subscriptions and cancellation itself.

`take(5)` takes only five items and cancels upstream; cancellation is a best-effort signal and does not guarantee an underlying blocking task or DB query stops immediately. The responder should use reactive sources that support cancellation and release resources with `doFinally` or `usingWhen` when appropriate.

Backpressure is only effective if upstream honors demand. A hot source unable to slow down may need a bounded buffer, drop, latest, or error policy; do not configure an unbounded `onBackpressureBuffer()` without accounting for memory limits.

### 5.3. When to choose it

Use when one request produces a large result set, data is computed incrementally, updates arrive over time, or results do not need to be collected entirely before sending. Compared to request-response returning `List<T>`, request-stream can reduce time to first item and reduce memory usage as the consumer processes items one by one.

## 6. Request-channel: bidirectional streaming

### 6.1. Sequence

```text
Requester                                    Responder
    |                                            |
    |--- REQUEST_CHANNEL(msg 1, N out) --------->|
    |<-- REQUEST_N(N in) ------------------------|
    |--- PAYLOAD(msg 2) ------------------------>|
    |<-- PAYLOAD(reply A) -----------------------|
    |<-- PAYLOAD(reply B) -----------------------|
    |--- PAYLOAD(msg 3) ------------------------>|
    |--- COMPLETE (outbound) ------------------->|
    |<-- PAYLOAD(reply C) -----------------------|
    |<-- COMPLETE (inbound) ---------------------|
```

Both sides have their own data streams and independent demand; sending and receiving can interleave. Completing **the outbound direction** on one side does not necessarily end the inbound direction immediately. When both directions have completed, or when error/cancel terminates the interaction, the channel is released.

Request-channel allows:

- The requester to continuously send N messages while the responder sends back M messages.
- The responder to process sequentially, with controlled concurrency, or emit responses based on external events.
- Both directions to run at different speeds; backpressure must be considered per direction.
- A channel to be long-lived, requiring heartbeats, cancellation, and shutdown procedures.

Example:

```java
Flux<ChatMessage> outgoing = Flux.just(
        new ChatMessage("an", "xin chao"),
        new ChatMessage("binh", "webflux"));

Flux<ChatReply> incoming = requester.route("chat.room")
        .data(outgoing, ChatMessage.class)
        .retrieveFlux(ChatReply.class);
```

Responder:

```java
@MessageMapping("chat.room")
public Flux<ChatReply> talk(Flux<ChatMessage> messages) {
    return messages.map(m ->
            new ChatReply(m.sender(), "echo:" + m.text()));
}
```

This is a **1–1 example for easy observation**, not a limitation of RSocket. Real responders can use `flatMap`, `merge`, or an independent emitter to return a different number of responses than requests; in that case, ordering, concurrency, and buffering policies must be explicit.

### 6.2. Do not turn a channel into a request-stream

If you only need to send **one** filter condition and receive updated results, use request-stream. Only use request-channel if **the input is also a multi-message stream** or the application requires stateful duplex interaction like chat or progress control.

A stream carrying no further data after connection is not a reason to automatically pick channel; choose based on the two-way stream contract, not just because the server can push.

## 7. How does Spring @MessageMapping determine the model?

Spring Messaging reads the route from metadata and locates the corresponding `@MessageMapping`. Once the route matches, the input payload type and return type help the framework determine which interactions the handler supports.

| Handler input | Handler output | Interactions it can serve |
| --- | --- | --- |
| Object or `Mono<T>` | `void`, `Mono<Void>` | FNF or RR with no payload, depending on the frame sent by the requester |
| Object or `Mono<T>` | Object or `Mono<R>` | RR |
| Object or `Mono<T>` | `Flux<R>` | Request-stream |
| `Flux<T>` | `Flux<R>`, `Mono<R>`, or no-value | Request-channel |

In this exercise, we use `void` for FNF, `Mono<R>` for RR, `Flux<R>` with a single input for RS, and `Flux<T>` input plus `Flux<R>` output for RC. Four distinct routes keep the code explicit.

`RSocketRequester` determines how the interaction is initiated:

- `send()` → Fire-and-forget.
- `retrieveMono(...)` → Request-response, when the input is a single value.
- `retrieveFlux(...)` with a single input → Request-stream.
- `data(Flux<X>, X.class).retrieveFlux(Y.class)` → Request-channel.

A request with a multi-element input Publisher **cannot** become a traditional HTTP-style "many-to-one" RPC; with RSocket, a multi-element input uses request-channel, even if the handler returns only a single result.

## 8. Complete runnable Java 17+ example over TCP

The example uses **Spring Boot 3.3.5**, Java 17, Maven, and RSocket TCP. Server and requester live in the same application for easy execution: Spring Boot opens RSocket port 7000, and then an `ApplicationRunner` sends all four request types to `localhost:7000`. This is a self-calling demo, not a mandatory deployment architecture.

### 8.1. Project structure

```text
rsocket-four-models/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── RSocketModesApplication.java
    │   │   ├── Messages.java
    │   │   ├── ModesController.java
    │   │   └── DemoRunner.java
    │   └── resources/application.properties
    └── test/java/demo/ModesControllerTest.java
```

### 8.2. pom.xml

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
    <artifactId>rsocket-four-models</artifactId>
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
            <artifactId>spring-boot-starter-json</artifactId>
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

`spring-boot-starter-rsocket` provides the RSocket infrastructure; `spring-boot-starter-json` ensures Jackson codecs for JSON DTOs; `reactor-test` provides `StepVerifier`.

### 8.3. application.properties

```properties
spring.application.name=rsocket-four-models
spring.main.web-application-type=none
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
```

This application **exposes no HTTP endpoints**. The `spring.rsocket.server.port` property opens the RSocket TCP listener. If port 7000 is in use, choose another port and update the host/port in `DemoRunner` accordingly.

### 8.4. RSocketModesApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketModesApplication {
    public static void main(String[] args) {
        SpringApplication.run(RSocketModesApplication.class, args);
    }
}
```

Spring Boot auto-configures `RSocketMessageHandler`, `RSocketStrategies`, and `RSocketRequester.Builder` when the appropriate dependencies are present.

### 8.5. Messages.java — shared DTOs

```java
package demo;

public final class Messages {
    private Messages() {
    }

    public record Notice(String text) {
    }

    public record NumberInput(int value) {
    }

    public record SquareReply(int result) {
    }

    public record StreamInput(int count) {
    }

    public record Tick(int sequence, String label) {
    }

    public record ChatMessage(String from, String text) {
    }

    public record ChatReply(String from, String text) {
    }
}
```

Java 17 records are small, immutable data types. Client and server use the same schema for the JSON demo; real systems can share a schema/module or apply API/schema versioning when the two sides deploy independently.

### 8.6. ModesController.java — responder with all four models

```java
package demo;

import java.time.Duration;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class ModesController {

    private final Queue<Messages.Notice> notices =
            new ConcurrentLinkedQueue<>();

    // Fire-and-forget: one input and no response payload.
    @MessageMapping("demo.fnf")
    public void onNotice(Messages.Notice notice) {
        notices.add(notice); // Demo: non-blocking in-memory operation.
    }

    // For testing only, not an RSocket route.
    public int receivedNoticeCount() {
        return notices.size();
    }

    // Request-response: one input, at most one output.
    @MessageMapping("demo.rr")
    public Mono<Messages.SquareReply> square(
            Messages.NumberInput input) {
        return Mono.fromSupplier(() ->
                new Messages.SquareReply(
                        Math.multiplyExact(
                                input.value(), input.value())));
    }

    // Request-stream: one input, multiple outputs with demand.
    @MessageMapping("demo.stream")
    public Flux<Messages.Tick> ticks(Messages.StreamInput input) {
        if (input.count() < 1 || input.count() > 100) {
            return Flux.error(new IllegalArgumentException(
                    "count must be from 1 to 100"));
        }

        return Flux.range(1, input.count())
                .delayElements(Duration.ofMillis(30))
                .map(i -> new Messages.Tick(i, "tick-" + i));
    }

    // Request-channel: input Flux and output Flux.
    @MessageMapping("demo.channel")
    public Flux<Messages.ChatReply> chat(
            Flux<Messages.ChatMessage> incoming) {
        return incoming.map(message ->
                new Messages.ChatReply(
                        message.from(),
                        "echo:" + message.text()));
    }
}
```

Explanation:

- `demo.fnf`: the handler returns `void`, and the client does not wait for a business response. The demo queue can be removed in real deployments.
- `demo.rr`: `Mono.fromSupplier` runs the computation on subscription; `multiplyExact` surfaces overflow as an error instead of silently overflowing.
- `demo.stream`: `Flux.range` is a finite source, and `delayElements` makes emission over time visible. Validate `count` to prevent a single request from generating too many items.
- `demo.channel`: transforms each input into an output. This is a 1–1 echo example and does not restrict real channels to 1–1 mapping.

### 8.7. DemoRunner.java — requester for all four models

```java
package demo;

import java.time.Duration;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Component;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;

@Component
public class DemoRunner implements ApplicationRunner {

    private final RSocketRequester.Builder builder;

    public DemoRunner(RSocketRequester.Builder builder) {
        this.builder = builder;
    }

    @Override
    public void run(ApplicationArguments args) {
        RSocketRequester requester = builder
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .tcp("localhost", 7000);

        // 1. Fire-and-forget.
        requester.route("demo.fnf")
                .data(new Messages.Notice("hello"))
                .send()
                .block(Duration.ofSeconds(5));

        System.out.println(
                "FNF: sent (not a business acknowledgment)");

        // 2. Request-response.
        Messages.SquareReply squared = requester.route("demo.rr")
                .data(new Messages.NumberInput(7))
                .retrieveMono(Messages.SquareReply.class)
                .block(Duration.ofSeconds(5));

        System.out.println("RR: " + squared);

        // 3. Request-stream. take(3) cancels upstream once enough data is received.
        List<Messages.Tick> ticks = requester.route("demo.stream")
                .data(new Messages.StreamInput(5))
                .retrieveFlux(Messages.Tick.class)
                .take(3)
                .collectList()
                .block(Duration.ofSeconds(5));

        System.out.println("STREAM (first 3): " + ticks);

        // 4. Request-channel. Outbound is also a Flux.
        Flux<Messages.ChatMessage> outgoing = Flux.just(
                new Messages.ChatMessage("an", "hello"),
                new Messages.ChatMessage("binh", "reactive"));

        List<Messages.ChatReply> replies =
                requester.route("demo.channel")
                        .data(outgoing, Messages.ChatMessage.class)
                        .retrieveFlux(Messages.ChatReply.class)
                        .collectList()
                        .block(Duration.ofSeconds(5));

        System.out.println("CHANNEL: " + replies);
    }
}
```

Notes:

1. `Builder.tcp(host,port)` in Spring Framework 6.1 creates a requester with a shared/lazy connection; the connection is established when a request actually occurs. Do not confuse it with the older deprecated `connectTcp` API that returned a `Mono`.
2. `block(Duration)` is used **only in this command-line demo's ApplicationRunner**; never call it in a reactive handler or on a WebFlux application's event-loop thread.
3. `send()` completing does not prove the FNF handler stored the Notice. Do not treat this FNF log as a commit signal.
4. The RR, RS, and RC calls have client-side timeouts to avoid hanging the demo if the server is not running.
5. `take(3)` actively cancels the stream after three results; this does not mean the server definitely has not computed extra elements due to prefetching or concurrent work.
6. Both channel elements are sent over the same connection; the output count is two here because of the responder's echo code, not a protocol requirement.

### 8.8. Expected output

Run:

```bash
mvn spring-boot:run
```

Ignoring Spring/Netty startup logs, **four business lines** are printed sequentially by `DemoRunner`:

```text
FNF: sent (not a business acknowledgment)
RR: SquareReply[result=49]
STREAM (first 3): [Tick[sequence=1, label=tick-1], Tick[sequence=2, label=tick-2], Tick[sequence=3, label=tick-3]]
CHANNEL: [ChatReply[from=an, text=echo:hello], ChatReply[from=binh, text=echo:reactive]]
```

These are Java record values using default `toString()`. Spring Boot and Reactor Netty logs may interleave depending on the environment; the order of the lines explicitly printed by the Runner is preserved because each `block()` executes sequentially.

The application has an RSocket server listening on TCP port 7000, so the process stays up serving requests until the user stops it with Ctrl+C. In production, separate client and server into distinct processes, share schemas, and do not have a runner call itself.

### 8.9. ModesControllerTest.java — unit tests for handlers

```java
package demo;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ModesControllerTest {

    private final ModesController controller = new ModesController();

    @Test
    void fireAndForgetHasNoResponsePayload() {
        controller.onNotice(new Messages.Notice("ping"));
        assertThat(controller.receivedNoticeCount()).isEqualTo(1);
    }

    @Test
    void requestResponseReturnsOneValue() {
        StepVerifier.create(
                controller.square(new Messages.NumberInput(7)))
                .expectNext(new Messages.SquareReply(49))
                .verifyComplete();
    }

    @Test
    void requestStreamReturnsMultipleValuesAndCanBeCancelled() {
        StepVerifier.create(
                controller.ticks(new Messages.StreamInput(5)).take(3))
                .expectNext(
                        new Messages.Tick(1, "tick-1"),
                        new Messages.Tick(2, "tick-2"),
                        new Messages.Tick(3, "tick-3"))
                .verifyComplete();
    }

    @Test
    void requestChannelReceivesAndEmitsStreams() {
        Flux<Messages.ChatMessage> incoming = Flux.just(
                new Messages.ChatMessage("an", "hello"),
                new Messages.ChatMessage("binh", "reactive"));

        StepVerifier.create(controller.chat(incoming))
                .expectNext(
                        new Messages.ChatReply("an", "echo:hello"),
                        new Messages.ChatReply("binh", "echo:reactive"))
                .verifyComplete();
    }
}
```

Run:

```bash
mvn test
```

The four tests verify handler logic and Mono/Flux signals; they do **not** start a TCP listener or test wire-level serialization/routing. Running `mvn spring-boot:run` above serves as the actual end-to-end smoke test over RSocket TCP. For higher quality assurance, add integration tests with a random port, a real connected client, and checks for error cases, timeouts, disconnects, and backpressure; do not treat unit tests as full proof of transport behavior.

## 9. How do demand, backpressure, and CANCEL work?

### 9.1. Backpressure at the network boundary

With request-stream and request-channel, requester and responder exchange demand via `REQUEST_N`. This lets a slow subscriber request fewer items. Initial demand can be specified in the opening frame and replenished with `REQUEST_N`.

In Reactor:

```java
Flux<Messages.Tick> stream = requester.route("demo.stream")
        .data(new Messages.StreamInput(100))
        .retrieveFlux(Messages.Tick.class);

stream.take(10)
        .doFinally(signal -> System.out.println("end=" + signal))
        .subscribe(System.out::println);
```

`take(10)` cancels after taking 10 items. `doFinally` records completion, error, or cancel. Console output can interleave with scheduler logs, so use it only to understand lifecycle rather than relying on deterministic stdout ordering.

### 9.2. Do not equate backpressure with an unbounded queue

Backpressure is **a signal requesting a consumption rate**, not automatic buffering of all data from an external source. If the producer is a hot source that cannot slow down, you need a clear strategy:

- Bound the buffer size.
- Slow down or pause sources that support demand.
- Drop/latest for data that can be lost.
- Signal an error when limits are exceeded.
- Persist critical data to durable storage.

Using an unbounded `onBackpressureBuffer()` on a potentially infinite stream risks running out of memory.

### 9.3. Cancellation and resource release

When a client cancels, the responder should release subscriptions, data streams, DB connections, files, or external resources whenever possible. For reactive resources, `usingWhen` or `doFinally` helps manage lifecycles; if a blocking library that does not support cancellation has already been called, the cancel signal cannot automatically halt that task.

Do not treat cancel as a transaction rollback. A database write may have already committed even if the client timed out or canceled.

## 10. Errors and stream termination

| Scenario | FNF | RR | RS | RC |
| --- | --- | --- | --- | --- |
| Request sent successfully | `send()` completes, no processing ack | Waits for one response or error | Starts receiving data per demand | Both directions can send/receive |
| Responder signals business error | No dedicated response request to confirm | `Mono.error` to caller | `Flux.error` terminates stream | Error can terminate entire channel |
| Requester cancels | No response stream to cancel | Can cancel while awaiting response | `CANCEL` stops stream | `CANCEL` terminates interaction |
| Responder completes normally | No response payload | Result or empty completion | `COMPLETE` after last item | Each direction can complete independently |

Do not use unbounded `retry()`: reconnecting and resending requests can produce duplicate side effects. Use `retryWhen` with backoff, a retry limit, and apply only according to your idempotency contract.

Mismatched codecs or routes can surface as RSocket errors; check MIME types, route names, DTO serializers, null/empty handling, and schema compatibility before suspecting the network.

## 11. Choosing a model by scenario

### Scenario A: Collecting temperature every second, tolerating dropped samples

**FNF** is suitable if each sample is sent independently and losing a few samples does not harm business logic. If the server must confirm every sample was stored, use RR or an ingestion mechanism with delivery guarantees.

### Scenario B: User requests a credit score calculation

**RR** fits because the user needs a specific decision or status. If the process is long-running, consider returning a job ID via RR and tracking progress with RS or another model.

### Scenario C: Watching the latest 500 events or real-time prices

**RS** fits: one filter condition, many events. Use demand and cancellation so the client does not overload itself. Distinguish finite streams (500 records) from live streams (running until canceled).

### Scenario D: Bidirectional chat or device control

**RC** fits when the client continuously sends commands/messages while also continuously receiving status/responses. Both directions have independent lifecycles and do not need to pair every message into a standalone request-response.

### Scenario E: Uploading multiple chunks and receiving one final result

Multi-chunk input → that is **request-channel**, even if the server returns a single aggregated final result. However, clearly define chunk limits, total size checks, checksums, mid-stream cancellation, and avoid holding the entire upload in RAM.

## 12. Operations, security, and resilience

### 12.1. Keep connections and streams bounded

- Monitor open connections and streams, request rates, latency, RSocket ERROR/CANCEL counts, and pending items.
- Set sensible timeouts; for long-lived streams, use idle/heartbeat policies rather than an overly short total deadline.
- Limit payload size, max items, and concurrency to prevent abuse.
- Do not create a new requester/connection for every Flux element; reuse a lifecycle-managed requester.
- Dispose subscriptions when users leave a page or when the application shuts down.

### 12.2. TLS, authentication, and authorization

RSocket defines the protocol itself, but **does not provide business authorization policies out of the box**. Use secure transports (TLS for TCP, WSS for WebSocket), authenticate identity (e.g., setup/auth metadata combined with Spring Security RSocket), and check permissions per route.

Routes reside in metadata and are therefore untrusted input: do not infer from a route that the sender is authorized to perform the action. Do not put tokens or sensitive content into wiretap logs. Limit frame and request sizes to prevent DoS.

The local TCP `7000` example is for demonstration only. In production, enforce network ingress/firewalls, TLS, authentication, authorization, and quotas.

### 12.3. Resumption and leasing are not enabled by default

RSocket is extensible with **keepalive**, **leasing** (limiting how many requests the peer may open over a period), and **session resumption** upon transport loss, though support and activation depend on library versions, runtime, and configuration on both sides.

Do not claim resumption automatically guarantees zero lost business events or exactly-once delivery. Durable delivery still requires transactions/outbox, idempotency, and intentional replay mechanisms.

### 12.4. Avoid blocking on the Reactor event loop

Do not call `block()`, use blocking JDBC, or perform long synchronous I/O inside `@MessageMapping` reactive handlers; doing so can block the event loop and stall all other streams. If calling a legacy blocking library is unavoidable, offload to a dedicated bounded scheduler like `Schedulers.boundedElastic()` and consider migrating to reactive drivers.

The `block()` calls in the example's `ApplicationRunner` are an intentional exception for a sequential command-line demo, not a guide for writing production handlers.

## 13. Common mistakes

| Mistake | Why it is wrong | How to handle it |
| --- | --- | --- |
| Using FNF to confirm order creation | `send()` is not a business ack | Use RR with idempotency or a durable queue. |
| Expecting FNF to return a body | FNF has no response payload | Use RR if a result must be received. |
| Expecting RR to emit multiple items | RR has at most one result | Use RS or wrap results into one object when truly needed. |
| Sending a `Flux` input and thinking it is request-stream | Multi-item input is channel | Use RC with `data(Flux, elementClass)`. |
| Thinking channel forces 1–1 request/response | Channel streams are independent | Design an application protocol with correlation if needed. |
| Not subscribing to the requester publisher | Reactive pipelines are lazy; no interaction happens yet | Subscribe with the proper lifecycle or let the framework subscribe. |
| Calling `subscribe()` casually and dropping errors | Resource/error leaks | Return Mono/Flux to the caller or manage the subscription. |
| Calling `block()` on the event loop | Starves other streams | Use non-blocking operators. |
| Using an unbounded buffer on a hot publisher | Can exhaust memory | Use a bounded backpressure policy. |
| Not handling cancel on long-lived streams | Subscription/resource leaks | Use `doFinally`/`usingWhen`, close connections on shutdown. |
| Retrying non-idempotent side effects | Creates duplicate transactions or messages | Add idempotency keys and retry limits. |
| Expecting timeout to mean rollback | Server may have processed before timeout | Query status via a dedicated API/ID. |
| Confusing RSocket routes with HTTP URLs | Routing and protocol mismatch | Use `@MessageMapping` and route metadata. |
| Missing JSON codec on classpath | DTO decoding fails | Add Jackson/codecs and configure matching MIME types. |
| Assuming TCP RSocket encrypts automatically | Plain TCP lacks TLS | Configure TLS/WSS and proper authentication. |
| Exposing a public port without limits | Risk of abuse and attacks | Restrict ingress, authz, payload size, and quotas. |
| Treating `mvn test` as an end-to-end test | Unit tests only call handlers directly | Run the app over TCP or write separate integration tests. |

## 14. Self-check questions

**Question 1:** Is RSocket HTTP, and is `@MessageMapping` GET/POST?  
**Answer:** No. RSocket is a separate application protocol running over TCP/WebSocket; routes are carried in metadata.

**Question 2:** Does FNF confirm successful processing?  
**Answer:** No. The `Mono<Void>` from `send()` only reflects sending on the requester side, not guaranteed processing by the responder.

**Question 3:** Which model fits one request and one response object?  
**Answer:** Request-response; typically using `retrieveMono`.

**Question 4:** What fits one request and many records streamed incrementally?  
**Answer:** Request-stream; use `retrieveFlux` and have the responder return `Flux`.

**Question 5:** The requester sends 10 messages, and the responder sends 2 messages; is that valid?  
**Answer:** Valid for request-channel; the two directions are not forced to have the same item count.

**Question 6:** What is `REQUEST_N` used for?  
**Answer:** It expresses how many more items downstream wants to receive, supporting backpressure across the network boundary.

**Question 7:** What happens when using `take(3)` on a request-stream?  
**Answer:** The caller receives at most three items and cancels the subscription; RSocket can send CANCEL. Cancellation does not guarantee side effects were rolled back.

**Question 8:** Distinguish input `Flux<T>` from output `Flux<R>`?  
**Answer:** Input `Flux` means the requester sends multiple messages (channel); output `Flux` means the responder can send multiple messages. Single input with multiple outputs is request-stream.

**Question 9:** Why not put everything in `Mono<List<T>>`?  
**Answer:** That collects everything before returning, increasing memory/latency; request-stream enables streaming and consuming items incrementally per demand.

**Question 10:** Do resumption and leasing guarantee exactly-once by default?  
**Answer:** No. These are protocol capabilities depending on support/configuration; business correctness requires durable storage, retries, and separate idempotency.

## 15. Summary

- **FNF:** one-way, no business ack; `send()` completing does not mean the message was processed.
- **RR:** 1 request → at most 1 result, typically using `Mono<T>`.
- **RS:** 1 request → many results, using `Flux<T>` with demand/cancel.
- **RC:** both directions can be streams, not necessarily 1–1, with independent lifecycles.
- Spring `@MessageMapping` handles routes; `RSocketRequester` initiates interactions via `send`, `retrieveMono`, or `retrieveFlux`.
- Backpressure does not replace memory bounds, durability, authentication, timeouts, or idempotency.

## References

1. [Spring Framework – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): overview, requester, annotated responder, cardinality, and metadata.
2. [Spring Boot 3.3 – RSocket](https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html): auto-configuration, TCP/WebSocket server, and RSocketRequester.Builder.
3. [RSocket Protocol Definition](https://github.com/rsocket/rsocket/blob/master/Protocol.md): REQUEST_FNF, REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_CHANNEL, REQUEST_N, CANCEL, and COMPLETE frames.
4. [RSocket – Protocol](https://rsocket.io/about/protocol/): flow control, lifecycle, and frame semantics.
5. [Spring Framework 6.1 – RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html): `tcp`, `dataMimeType`, connection setup.
6. [Spring Framework 6.1 – RSocketRequester.RequestSpec](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html): `data`, `send`, and `retrieveFlux`.
7. [Project Reactor – Reference](https://projectreactor.io/docs/core/release/reference/): demand, cancellation, `Mono`, `Flux`, and test support.
