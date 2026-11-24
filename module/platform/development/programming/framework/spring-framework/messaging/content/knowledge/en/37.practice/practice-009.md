# Building RSocket Request-Response and Request-Stream with Spring

RSocket provides multiple interaction models over a single bidirectional connection. In this lab, we build a Spring responder with two routes: `quotes.latest` receives one request and returns a single `Quote` using **Request-Response**; `quotes.stream` receives one request and returns multiple `Quote` items using **Request-Stream**.

The distinction lies in the cardinality of requests and responses:

| Interaction | Outbound data | Returned data | Typical Spring types |
| --- | --- | --- | --- |
| Request-Response | One payload (or no payload) | One response | `Mono<T>` |
| Request-Stream | One payload (or no payload) | Multiple streamed responses | `Flux<T>` |
| Request-Channel | A stream of payloads | One or more responses | Input `Flux<T>` and output `Flux<T>` |
| Fire-and-Forget | One payload | No business response | `Mono<Void>` on handler; `send()` on requester |

With Request-Response, the requester sends one request and awaits one response. With Request-Stream, the requester sends an initial request and receives a stream of responses; the requester can control emission speed via backpressure. Spring maps these two models from the cardinality of the parameters and return type on `@MessageMapping`.

## 1. Preparing the Spring Boot Project

The example uses Java 17+ and Spring Boot 4.1.0. `spring-boot-starter-rsocket` provides the RSocket server/client infrastructure, Spring Messaging, and JSON/CBOR codecs auto-configured by Boot. `reactor-test` is used to test publishers with `StepVerifier`.

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>rsocket-practice</artifactId>
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

Run a standalone TCP server with the configuration:

**src/main/resources/application.properties**

```properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
```

Spring Boot automatically creates `RSocketMessageHandler` to discover `@Controller` classes with `@MessageMapping`. There is no need to instantiate `RSocketServer` or register handlers manually in standard Boot setups.

Startup class:

```java
package example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteRSocketApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuoteRSocketApplication.class, args);
    }
}
```

## 2. Defining Request and Response Payloads

Request-Response accepts a `QuoteRequest`; Request-Stream accepts a `QuoteStreamRequest` specifying the number of items to fetch. Both return `Quote`.

**QuoteRequest.java**

```java
package example.rsocket;

public record QuoteRequest(String symbol) { }
```

**QuoteStreamRequest.java**

```java
package example.rsocket;

public record QuoteStreamRequest(String symbol, int count) { }
```

**Quote.java**

```java
package example.rsocket;

import java.math.BigDecimal;

public record Quote(String symbol, BigDecimal price, int sequence) { }
```

Records fit immutable DTOs well. In real systems, requests may include filters, time ranges, cursors, or data limits; responses should have versioned schemas if multiple services/clients deploy independently.

## 3. Writing a Service Returning Mono and Flux

`Mono<T>` represents at most one asynchronous value; `Flux<T>` represents 0 to many values. The service returns publishers so the controller can pass processing along without blocking threads.

**QuoteService.java**

```java
package example.rsocket;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class QuoteService {

    public Mono<Quote> latest(String symbol) {
        if (symbol == null || symbol.isBlank()) {
            return Mono.error(new IllegalArgumentException("symbol is required"));
        }
        return Mono.just(new Quote(symbol, new BigDecimal("101.25"), 1));
    }

    public Flux<Quote> stream(String symbol, int count) {
        if (symbol == null || symbol.isBlank()) {
            return Flux.error(new IllegalArgumentException("symbol is required"));
        }
        if (count < 1 || count > 100) {
            return Flux.error(new IllegalArgumentException("count must be between 1 and 100"));
        }
        return Flux.range(1, count)
                .map(sequence -> new Quote(symbol,
                        BigDecimal.valueOf(10_000L + sequence * 25L, 2), sequence));
    }
}
```

`Flux.range` is a finite source and supports backpressure: it only emits additional elements when downstream requests them. Bounding `count` is a resource control; production streaming APIs should also limit size, duration, and concurrent requests.

## 4. Building the RSocket Responder

Spring uses `@MessageMapping` to map an RSocket route to a method. Routes do not need a leading `/`. Parameter and return types determine the interaction model:

- One input payload + `Mono<Quote>` output -> Request-Response.
- One input payload + `Flux<Quote>` output -> Request-Stream.

**QuoteRSocketController.java**

```java
package example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class QuoteRSocketController {
    private final QuoteService quoteService;

    public QuoteRSocketController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("quotes.latest")
    public Mono<Quote> latest(@Payload QuoteRequest request) {
        return quoteService.latest(request.symbol());
    }

    @MessageMapping("quotes.stream")
    public Flux<Quote> stream(@Payload QuoteStreamRequest request) {
        return quoteService.stream(request.symbol(), request.count());
    }
}
```

Do not call `.subscribe()` inside a handler. Return `Mono` or `Flux` to the framework so it manages subscriptions, errors, cancellation, and demand from the requester. Subscribing manually inside a controller can break the link between the request lifecycle and background work, preventing clients from receiving responses properly.

## 5. Sending Request-Response from the Requester

The requester builds requests using `RSocketRequester`. `route(...)` puts the route name into metadata; `data(...)` puts the business object into the data section; `retrieveMono(...)` declares the expected response type.

```java
RSocketRequester requester = RSocketRequester.builder()
        .tcp("localhost", 7000);

Mono<Quote> latest = requester.route("quotes.latest")
        .data(new QuoteRequest("VN30"))
        .retrieveMono(Quote.class);
```

The result is a `Mono<Quote>`. Upon subscribing, Spring serializes `QuoteRequest`, sends the request to route `quotes.latest`, awaits the response, and decodes it into `Quote`.

Request-Response fits when the caller needs a single result: fetching current state, computing one result, checking status, or issuing a command that returns confirmation. If the server does not return a payload per the contract, design the appropriate interaction; do not pick `retrieveMono` just because you want to wait for an operation that has no response.

## 6. Sending Request-Stream from the Requester

Request-Stream still sends only one initial payload, yet the responder can emit multiple responses. Use `retrieveFlux(...)` to receive the stream:

```java
Flux<Quote> quotes = requester.route("quotes.stream")
        .data(new QuoteStreamRequest("VN30", 5))
        .retrieveFlux(Quote.class);
```

The client can process each item as it arrives:

```java
quotes
        .doOnNext(quote -> log.info("Received {}", quote))
        .doOnError(error -> log.error("Quote stream failed", error))
        .doOnComplete(() -> log.info("Quote stream completed"))
        .subscribe();
```

The code above illustrates an application-layer subscriber. In a WebFlux/controller or reactive service, you should normally return `Flux<Quote>` to the caller rather than subscribing manually. If side effects are needed inside a stream, use deliberate operators and ensure errors are handled.

## 7. End-to-End Testing with StepVerifier

Unit tests for `QuoteService` do not test transport, routing, codecs, and RSocket interaction types. The integration test below starts a real server on a random port, creates a TCP requester, and tests both interactions.

**QuoteRSocketIntegrationTest.java**

```java
package example.rsocket;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class QuoteRSocketIntegrationTest {
    @Value("${local.rsocket.server.port}")
    int port;

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    RSocketRequester requester;

    @BeforeEach
    void connect() {
        requester = requesterBuilder.tcp("localhost", port);
    }

    @AfterEach
    void close() {
        if (requester != null) {
            requester.dispose();
        }
    }

    @Test
    void requestResponseReturnsOneQuote() {
        Mono<Quote> response = requester.route("quotes.latest")
                .data(new QuoteRequest("VN30"))
                .retrieveMono(Quote.class);

        StepVerifier.create(response)
                .assertNext(quote -> {
                    assertEquals("VN30", quote.symbol());
                    assertEquals(0, new java.math.BigDecimal("101.25").compareTo(quote.price()));
                    assertEquals(1, quote.sequence());
                })
                .verifyComplete();
    }

    @Test
    void requestStreamHonorsDemandAndCompletes() {
        Flux<Quote> response = requester.route("quotes.stream")
                .data(new QuoteStreamRequest("VN30", 5))
                .retrieveFlux(Quote.class);

        StepVerifier.create(response, 0)
                .thenRequest(1)
                .assertNext(quote -> assertEquals(1, quote.sequence()))
                .thenRequest(4)
                .expectNextCount(4)
                .verifyComplete();
    }
}
```

`@SpringBootTest` starts the application's RSocket server. Setting `spring.rsocket.server.port=0` asks the OS for an available port; Spring Boot publishes the actual port via `local.rsocket.server.port`. The test creates a requester to that port and calls routes like an independent client.

`StepVerifier.create(response, 0)` starts with zero demand. The test requests one element, asserts sequence 1, and then requests four more elements. This verifies the stream can be consumed according to demand and completes properly without `Thread.sleep`.

Run tests:

```bash
mvn test
```

Sample test output run with Maven and Spring Boot 4.1.0:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

The test project sets `java.version=17`; the source code uses records and Java 17+ compatible APIs. The integration test passed on JDK 24 targeting Java 17.

## 8. Understanding Backpressure in Request-Stream

Backpressure is part of the RSocket protocol. The requester sends the initial number of elements it wants to receive and can send additional demand during the stream. RSocket propagates demand across the network boundary so the responder does not have to push infinitely into a client-side buffer.

In Spring, `Flux` is the natural return type for Request-Stream. Prefer data sources capable of emitting on demand such as `Flux.fromIterable`, `Flux.range`, `Flux.generate`, or reactive publishers from databases/clients.

Practical principles:

- Do not call `.collectList()` if the caller needs to stream items individually; this aggregates all data into a collection and defeats streaming benefits.
- Avoid loading all database data into a `List` before creating a `Flux`. Use cursors, paging, or appropriate reactive repositories.
- Do not call `subscribe()` inside a responder to run a stream independently of the request.
- If rate limiting is needed, use `limitRate`, `delayElements`, or source-level policies per business rules; do not add large buffers by default.
- When a client cancels a subscription, cancellation propagates to the responder. Use `doFinally` or Reactor resource management to release cursors, subscriptions, and open resources.
- If using `flatMap` to call multiple dependencies concurrently, set concurrency bounds and check result ordering. Use `concatMap` when sequential processing is required.

Example where a client takes at most 10 items:

```java
Flux<Quote> firstTen = requester.route("quotes.stream")
        .data(new QuoteStreamRequest("VN30", 100))
        .retrieveFlux(Quote.class)
        .take(10);
```

`take(10)` cancels the subscription after the tenth item; the responder can receive cancellation and stop the remaining work. This is a crucial difference compared to fetching all 100 items and discarding 90 on the client side.

## 9. Codecs, Data, Metadata, and Routes

`RSocketRequester` accepts and returns objects, while the framework converts objects to bytes using `RSocketStrategies` and encoders/decoders.

- Spring Boot auto-configures `RSocketStrategies`; Boot 4.1 tries the Jackson CBOR codec first, followed by Jackson JSON. `spring-boot-starter-rsocket` provides the required dependencies.
- If using Spring Framework directly without Boot, default basic codecs support `String`, `byte[]`, and `ByteBuffer`. To serialize JSON/CBOR DTOs, register the corresponding encoders/decoders.
- `route("quotes.latest")` is sent in routing metadata. `data(new QuoteRequest(...))` is the business payload.
- Data and metadata MIME types are declared in RSocket `SETUP` and apply for the connection. Both sides must be compatible in MIME types and codecs.
- Composite metadata allows sending multiple independent entries such as route, authentication, or tracing; each entry needs an appropriate encoder/decoder or extractor.

When connecting with clients written in other languages, agree on schemas, MIME types, routes, and number/date-time representations. Do not assume a Java DTO is automatically compatible with every client-side serializer.

## 10. Timeouts, Errors, and Connection Lifecycle

A requester created with `builder.tcp(...)` does not necessarily open a socket immediately; the connection is established when a request is executed. One requester can be shared across multiple requests over the same connection. Dispose of the requester when its owning component stops:

```java
requester.dispose();
```

Spring Boot provides `RSocketRequester.Builder` as a prototype bean because the builder is stateful. Each injection point receives its own builder; do not keep one configured builder and reuse it across multiple connections with different setups.

Reactive-level timeouts can be set per request:

```java
Mono<Quote> response = requester.route("quotes.latest")
        .data(new QuoteRequest("VN30"))
        .retrieveMono(Quote.class)
        .timeout(Duration.ofSeconds(3));
```

This snippet requires importing `java.time.Duration`. A client-side timeout only indicates the caller did not receive a response within the deadline; it does not prove the server did not execute the business logic. For commands with side effects, an idempotency key or status lookup mechanism is required before retrying.

An RSocket error frame terminates the corresponding request/stream. Classify validation errors, business errors, and infrastructure errors; use `@ControllerAdvice` or reactive error handling at the right boundary to produce a safe error contract. Never return stack traces or internal details in error payloads.

Request-Stream can complete normally, emit an error, or be canceled by the requester. Clients should handle all three signals: `onComplete`, `onError`, and cancellation. When retrying a stream, consider cursors/sequences to avoid replaying or skipping items.

## 11. TCP and WebSocket Transports

The main example uses a standalone TCP server on port 7000. If you need to expose RSocket over a WebSocket endpoint in a WebFlux application, configure the mapping path and transport:

```properties
spring.rsocket.server.mapping-path=/rsocket
spring.rsocket.server.transport=websocket
```

RSocket is integrated into the web server only when using Reactor Netty. A WebSocket client can build a requester with the corresponding URI:

```java
RSocketRequester requester = RSocketRequester.builder()
        .webSocket(URI.create("ws://localhost:8080/rsocket"));
```

TCP is usually suited for service-to-service traffic on internal networks. WebSocket is useful when RSocket must traverse HTTP/WebSocket infrastructure or integrate with client environments that already support WebSocket. The transport does not change Request-Response or Request-Stream semantics.

## 12. Common Errors and Troubleshooting

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| Route not found | Route name differs between `.route(...)` and `@MessageMapping` | Compare exact route strings; verify controller is component-scanned |
| Client reports decode error | Both ends disagree on MIME type or codec is missing | Check `RSocketStrategies`, `dataMimeType`, and payload schema |
| `retrieveMono` does not receive expected response | Responder returns different cardinality or route uses wrong interaction | Ensure handler returns exactly one `Mono<T>` for Request-Response |
| Stream emits only one element | Handler returns `Mono` or publisher was capped by `take`, `next`, `single` | Check return type and stream-limiting operators |
| Stream fails when client is slow | Source pushes without respecting demand or buffer overflows | Use a backpressure-aware publisher; check overflow and concurrency |
| Request hangs | Not subscribed, responder never emits/completes, dependency stalls, or no timeout configured | Verify subscription, trace route, and dependency deadlines |
| Server fails to start | Port already in use or transport/dependency misconfigured | Check port, `spring-boot-starter-rsocket`, and server bind logs |
| Resources not released after client disconnects | Stream does not tie cleanup to cancellation | Use `doFinally`, `usingWhen`, or Reactor resource cleanup mechanisms |
| Client disconnects after idle period | Network or RSocket connection keepalive/timeout | Check keepalive, proxy idle timeouts, reconnect, and session resumption if configured |

Step-by-step debugging checklist:

1. Confirm the server is listening on the right TCP port or WebSocket path.
2. Check whether the requester has subscribed to the `Mono`/`Flux`.
3. Compare the route on the client and `@MessageMapping`.
4. Check cardinality: one request/one response vs. one request/multiple responses.
5. Verify encoders/decoders and MIME types on both sides.
6. Trace error signals, timeouts, and cancellations in the reactive chain.
7. For streams, verify demand, operator concurrency, and that the data source supports backpressure.

## 13. Expanding After Both Interactions Work

- **Validation:** validate symbol, count, query limits, and access permissions before calling services.
- **Authentication:** configure RSocket Security or an appropriate authentication mechanism; never trust user/tenant fields in payloads without verification.
- **Metadata:** send correlation IDs, tenant, or tokens via composite metadata and register extractors/decoders on the responder.
- **Observability:** record route, connection ID, request duration, stream item count, errors, and cancellations; avoid putting high-cardinality user IDs or request IDs into metric tags.
- **Timeout/retry:** set explicit deadlines; retry only transient errors and ensure idempotency for side-effecting commands.
- **Resume:** RSocket session resumption can help recover sessions on connection drops if both sides configure and retain state properly; it does not replace durable event stores or business-level replay.
- **Service interfaces:** when you want to define requester/responder contracts via Java interfaces, consider `@RSocketExchange` and `RSocketServiceProxyFactory` as an alternative to calling `route(...)` directly.

## 14. Key Takeaways

- Request-Response: one request, one response; Spring typically uses `Mono<T>` and `retrieveMono(T.class)`.
- Request-Stream: one request, multiple responses; Spring typically uses `Flux<T>` and `retrieveFlux(T.class)`.
- Route lives in metadata; the object passed to `.data(...)` is the business payload.
- Spring Boot auto-configures `RSocketMessageHandler` and codecs via `spring-boot-starter-rsocket`.
- RSocket propagates backpressure across the network boundary; use reactive sources that honor demand.
- Do not subscribe inside a responder; let the framework manage requests, errors, and cancellation.
- Use integration tests with a random port and `StepVerifier` to verify real interactions.
- Address timeouts, idempotency, security, codecs, and connection lifecycles before deploying to production.

## References

- [Spring Framework 7.0 — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot 4.1 — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Framework API — RSocketRequester](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Spring Framework API — RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketMessageHandler.html)
- [Spring Boot API — Local RSocket server port](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)