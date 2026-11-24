# Testing RSocketRequester and RSocketMessageHandler

RSocket is a bidirectional, multiplexed messaging protocol running over TCP, WebSocket, or another compatible transport. When testing a Spring application, both sides of the contract must be verified: the client builds the right request with route, data, metadata, and interaction model; the responder receives the right request, invokes the right handler, encodes the result, and returns the appropriate reactive signals.

Spring provides two central components:

- RSocketRequester is a fluent API for sending requests, passing data/metadata, and reading results as Mono or Flux. It abstracts away most Payload construction and encode/decode operations.
- RSocketMessageHandler maps RSocket requests to `@MessageMapping` and `@ConnectMapping` methods while managing payload conversion, routing, and metadata.

This lesson focuses on practical testing of these two components using JUnit 5, Reactor Test, and RSocket LocalTransport. The examples use Spring Framework 7.0.8, RSocket Java 1.1.5, and Java 17. If a project uses Spring Boot, prefer dependency versions managed by the Spring Boot BOM.

## 1. Defining the Boundaries to Test

A test that only calls a controller's Java method directly does not verify RSocket routes, metadata, serialization, or protocol interactions. Conversely, an end-to-end test over TCP/WebSocket is usually slower and harder to isolate failures in. Choose the testing level based on what needs to be proven:

| Testing Level | How It Works | What Is Verified |
|---|---|---|
| Business logic unit test | Call service or business method directly | Business rules, validation, error branches |
| Handler mapping test | Instantiate RSocketMessageHandler with specific handlers | Mapping detection, route, method signature, interaction type |
| Local transport integration test | Connect RSocketRequester and RSocketMessageHandler via LocalTransport | Encode/decode, route metadata, request/response/stream, and connection lifecycle |
| Transport integration test | Run real TCP or WebSocket | Network config, TLS/proxy if any, frame/connection behavior |
| Application context test | Initialize Spring context or Spring Boot test | Bean discovery, `@Controller` scanning, auto-configuration, codec config |

LocalTransport runs in-process, opens no TCP sockets, and does not test Netty/TLS/WebSocket. It still passes requests through the RSocket protocol and Spring's requester/responder stack, making it very useful for verifying interactions between the two components at low cost. Reserve a smaller set of dedicated TCP or WebSocket tests to verify real transport configuration.

## 2. What Needs to Be Tested on RSocketRequester?

RSocketRequester constructs requests from a route, data, metadata, and a retrieval method. Points to verify include:

- The route is sent accurately and matches `@MessageMapping` on the responder.
- Data is encoded according to the data MIME type and decoded into the expected response type.
- Metadata is sent with the registered MIME type and converted by MetadataExtractor into the right headers.
- The interaction model matches the input/output cardinality.
- Completion, errors, timeouts, or cancellations are observed properly.
- Connections are disposed when the test or requester-owning component shuts down.

Common invocation patterns:

~~~java
Mono<Reply> response = requester.route("orders.find")
        .data(orderId)
        .retrieveMono(Reply.class);

Flux<Update> updates = requester.route("orders.watch")
        .data(orderId)
        .retrieveFlux(Update.class);

Mono<Void> sent = requester.route("orders.audit")
        .data(event)
        .send();
~~~

`retrieveMono()` fits Request-Response; `retrieveFlux()` fits Request-Stream or multi-item outputs. `send()` is used for Fire-and-Forget. Completion of `send()` only indicates that the request was sent per the requester contract; it does not prove that the handler finished processing or that business side effects committed.

RSocket has four primary interaction models:

| Interaction | Input | Output | Typical API |
|---|---|---|---|
| Request-Response | One message | At most one response | `retrieveMono()` |
| Request-Stream | One message | Multiple responses | `retrieveFlux()` |
| Fire-and-Forget | One message | No response | `send()` |
| Request-Channel | One stream | One response stream | `data(Publisher)` and `retrieveFlux()` |

When testing, do not check only the first item. For streams, verify ordering, element counts, terminal signals, and cancellation/backpressure if required by the application.

## 3. What Needs to Be Tested on RSocketMessageHandler?

RSocketMessageHandler is the adapter from RSocket requests to handler methods. It supports `@MessageMapping` for individual requests and `@ConnectMapping` for connection setup or metadata push. It determines the interaction type based on method input and output cardinality:

- One input payload and one return value (e.g., `Mono<T>`) forms Request-Response.
- One input payload and multiple return values (`Flux<T>`) forms Request-Stream.
- One input payload and `void`/`Mono<Void>` can form Fire-and-Forget.
- An input stream is handled as Request-Channel.

Key checks:

1. Valid routes invoke the right method.
2. Non-existent routes return an appropriate error.
3. Input payloads are decoded into the right type and not confused with metadata.
4. `@DestinationVariable`, `@Header`, and `@Headers` receive the right extracted values.
5. Returned `Mono`/`Flux` values are encoded properly and preserve order.
6. Synchronous exceptions and reactive errors propagate as appropriate error signals.
7. `@ConnectMapping` handles setup data/metadata before requests on the connection begin.
8. Handlers do not trigger unintended side effects when the publisher has not been subscribed to or has been canceled.

When running inside a Spring ApplicationContext, RSocketMessageHandler detects `@Controller` beans containing `@MessageMapping`/`@ConnectMapping`. When instantiating the handler programmatically in tests, you can register handlers directly via `setHandlers()`. Manual registration helps test a handler in isolation; it does not test component scanning or application auto-configuration.

## 4. Writing a LocalTransport Test

LocalTransport provides an in-memory server/client transport. Generate a unique transport name per test to avoid collisions when running in parallel. `RSocketServer.bind()` starts the responder; `RSocketRequester.builder().transport()` creates a requester connected to the same name.

Tests should use the same `RSocketStrategies` on both sides if the goal is to exclude codec mismatches from the test scope. In production, the two sides may have separate strategies; in that case, add tests verifying that MIME types and codecs across both sides are compatible.

### 4.1. Maven Dependencies

Minimal POM example to run the test below with Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>rsocket-test</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.version>7.0.8</spring.version>
    <rsocket.version>1.1.5</rsocket.version>
    <junit.version>5.12.2</junit.version>
    <reactor.version>3.8.7</reactor.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-messaging</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-core</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-transport-local</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>${reactor.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.3</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

In a Spring Boot application, use Boot's dependency management and the appropriate starters instead of manually pinning every version. The core dependencies for standalone tests are `spring-messaging`, `spring-context`, `rsocket-core`, `rsocket-transport-local`, `reactor-test`, and JUnit Jupiter.

### 4.2. Complete Test for Request-Response and Request-Stream

Save as `src/test/java/example/RSocketRoundTripTest.java`:

~~~java
package example;

import java.time.Duration;
import java.util.List;

import io.rsocket.core.RSocketServer;
import io.rsocket.transport.local.LocalClientTransport;
import io.rsocket.transport.local.LocalServerTransport;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class RSocketRoundTripTest {

    public static class EchoHandler {

        @MessageMapping("echo")
        public Mono<String> echo(@Payload String value) {
            return Mono.just("reply:" + value);
        }

        @MessageMapping("stream")
        public Flux<String> stream(@Payload String prefix) {
            return Flux.just(prefix + "-1", prefix + "-2");
        }
    }

    @Test
    void requesterDispatchesThroughAnnotatedMessageHandler() {
        String transportName = "row382-test";
        RSocketStrategies strategies = RSocketStrategies.create();

        RSocketMessageHandler messageHandler = new RSocketMessageHandler();
        messageHandler.setRSocketStrategies(strategies);
        messageHandler.setHandlers(List.of(new EchoHandler()));
        messageHandler.afterPropertiesSet();

        Disposable server = RSocketServer.create(messageHandler.responder())
                .bind(LocalServerTransport.create(transportName))
                .block(Duration.ofSeconds(5));
        assertNotNull(server);

        RSocketRequester requester = RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .transport(LocalClientTransport.create(transportName));

        try {
            StepVerifier.create(requester.route("echo")
                            .data("hello")
                            .retrieveMono(String.class))
                    .expectNext("reply:hello")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            StepVerifier.create(requester.route("stream")
                            .data("item")
                            .retrieveFlux(String.class))
                    .expectNext("item-1", "item-2")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        }
        finally {
            requester.dispose();
            server.dispose();
        }
    }
}
~~~

The test initializes `RSocketMessageHandler`, registers two routes, binds the responder to `RSocketServer`, and creates a requester using `LocalClientTransport`. StepVerifier then sends real requests over the protocol and verifies:

- Route `echo` receives `"hello"` and returns `"reply:hello"`.
- Route `stream` receives `"item"` and returns two elements `"item-1"`, `"item-2"` in order.
- Both publishers complete normally.
- Both the client requester and the server are disposed in `finally` even if assertions fail.

Run the test:

~~~bash
mvn test
~~~

Expected Surefire output:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
~~~

This is an in-memory integration test requiring no fixed port or external server.

## 5. Using StepVerifier Properly

StepVerifier describes Reactive Streams signals in order and begins verification when `verify()` is called. Basic pattern:

~~~java
StepVerifier.create(publisher)
        .expectNext(expected)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
~~~

Common assertions:

- `expectNext(value)`: the next element must equal the expected value.
- `assertNext(consumer)`: inspect multiple fields on an element.
- `expectNextCount(n)`: assert element count.
- `expectError(type)`: verify the publisher terminates with an error of the specified type.
- `thenCancel()`: send a cancellation signal from the subscriber.
- `thenRequest(n)`: request `n` more items to verify backpressure.
- `verify(Duration)`: bound how long the test waits for a terminal signal.

Always supply a finite timeout to `verify` in network or async tests to prevent builds from hanging forever. `verify()` without a timeout can wait indefinitely.

For publishers using Reactor schedulers for delays, retry/backoff, or timeouts, `StepVerifier.withVirtualTime()` lets you test time progression without waiting in real time. Construct the publisher inside the `Supplier` passed to `withVirtualTime` so the virtual scheduler is installed before operators are initialized. Virtual time does not simulate TCP/WebSocket network latency; real timeouts are still needed for transport integration tests.

## 6. Testing Metadata and Serialization

RSocket has two MIME type categories: data and metadata. Routes are typically encoded into routing metadata; application metadata can be encoded in composite metadata. When testing metadata, verify that both sides use compatible configuration.

Example of a client sending token metadata:

~~~java
MimeType bearerMimeType =
        MimeType.valueOf("message/x.rsocket.authentication.bearer.v0");

Mono<Account> account = requester.route("accounts.current")
        .metadata(token, bearerMimeType)
        .retrieveMono(Account.class);
~~~

On the responder side, metadata must be registered with a `MetadataExtractor` or corresponding strategy before reading via `@Header`/`@Headers`. A method can accept payload and metadata separately:

~~~java
@MessageMapping("accounts.current")
public Mono<Account> current(
        @Payload AccountQuery query,
        @Header("authorization") String authorization) {
    return accountService.find(query, authorization);
}
~~~

Actual header names depend on the `MetadataExtractor` and MIME types registered by the application; do not assume a token automatically becomes an `authorization` header just because the client called `metadata()`. Tests should send real metadata through the requester and verify the extracted value in the handler or a mocked service.

For object payloads, register compatible Encoders/Decoders on both client and responder, such as Jackson CBOR or JSON codecs. Test objects with nested fields, null/optional fields, enums, dates/times, and collections if those types appear in the contract. Testing only default `String` or `byte[]` is not enough to verify JSON/CBOR codec configuration.

## 7. Testing Error Branches

A solid test suite should cover both pre-send failures and errors raised inside handlers:

| Scenario | How to Trigger | What to Verify |
|---|---|---|
| Non-existent route | Call a route with no mapping | Error signal and diagnosable error content |
| Malformed payload | Send an undecodable payload | Business handler is not called; decode error propagates |
| Missing metadata | Omit required metadata | Handler rejects according to policy |
| Business exception | Handler returns `Mono.error()` | Client receives error signal; consistent exception mapping |
| Empty handler result | Handler returns `Mono.empty()` | Request-Response completes with no value per contract |
| Mid-stream error | Flux emits a few values then errors | Earlier items and terminal error match expectations |
| Client cancels stream | `thenCancel()` or dispose subscription | Producer receives cancellation and releases resources |
| Connection closed | Dispose requester or server | Active publishers terminate per connection policy |
| Slow request | Delay exceeds client timeout | Timeout is observed; do not confuse with server rollback |

Do not assert exact internal framework exception messages unless that is an application contract. Prefer asserting error types, error codes, or application-controlled error payloads.

## 8. Testing Request-Channel and Fire-and-Forget

Request-Channel uses streams for both input and output. Use a `Flux` as the data producer and `retrieveFlux` to read responses. Tests must verify backpressure, ordering, and cancellation. If the producer is infinite, the test must limit the item count or cancel explicitly so the connection is not held open indefinitely.

Fire-and-Forget has no response payload. `send()` completes once the requester dispatches the request per protocol. If you need to confirm that the business handler finished processing, use an independent test signal such as `CountDownLatch`, `Sinks.One`, a test probe, or a state query. Do not treat `send().block()` completing as proof that the handler wrote data.

Example of verifying side effects with a probe:

~~~java
Sinks.One<String> handled = Sinks.one();

@MessageMapping("audit")
public Mono<Void> audit(@Payload AuditEvent event) {
    return auditService.store(event)
            .doOnSuccess(ignored -> handled.tryEmitValue(event.id()))
            .then();
}
~~~

In the test, send via `send()`, then verify that `handled.asMono()` emits the expected ID. In real code, the probe should be a test-only dependency; avoid adding test hooks into production APIs unless necessary.

## 9. Testing @ConnectMapping and Connection Lifecycle

`@ConnectMapping` handles the SETUP frame when a connection is established and can read setup data or metadata. A setup failure can prevent the connection from being accepted. Tests should include:

- Client sends valid setup data and the server records it properly.
- Missing or malformed setup metadata causes the connection to be rejected per policy.
- `@ConnectMapping` returning `Mono<Void>` completes and the connection can proceed to send requests.
- When the connection closes, resources tied to the session are cleaned up.
- If the server initiates requests back to the client, the client responder must be registered on the requester builder and tests must verify the client-side route.

Do not send synchronous requests during SETUP processing if they depend on SETUP having already completed; requests initiated from `@ConnectMapping` must be decoupled from setup handling according to the connection lifecycle.

## 10. When Are Real TCP/WebSocket Tests Needed?

LocalTransport verifies requester, responder, routing, and codecs through the in-memory protocol stack. It does not verify components that only exist on real transports. Add TCP/WebSocket tests when the application depends on:

- Port binding, bind addresses, and server lifecycle configuration.
- TLS, certificates, authentication, or proxies.
- WebSocket paths, HTTP upgrade, load balancers, and ingress.
- Frame size, fragmentation, keepalive, and connection timeouts.
- Network disconnects, reconnects, session resumption, or transport-level backpressure.

In TCP tests, use port 0 if the transport supports dynamic port binding and read the actual bound address from the channel. If using a fixed port, avoid running multiple tests in parallel on the same port. Close the server and requester after each test so sockets and threads do not leak. For WebSocket, use a dedicated test URI and close client/server similarly.

## 11. Common Testing Mistakes

| Mistake | Why the Test Is Unreliable | How to Fix |
|---|---|---|
| Mocking `RSocketRequester` and verifying `route()` was called | Does not test encoding, metadata, or protocol | Have at least one LocalTransport round-trip test |
| Calling `@MessageMapping` methods directly | Does not test route mapping or argument resolution | Send requests through `RSocketRequester` |
| Testing only the `String` codec | Misses JSON/CBOR and custom type errors | Test real object payloads |
| Using `verify()` without a timeout | Builds can hang forever if a stream never terminates | Use `verify(Duration)` |
| Using `Thread.sleep()` to wait for responses | Slow and flaky tests | Use `StepVerifier` or timeout-bounded latches/probes |
| Not disposing requester/server | Leaks connections, event loops, or threads | Clean up in `finally`/`@AfterEach` |
| Sharing a `LocalTransport` name in parallel runs | Tests may connect to the wrong server | Generate a unique name per test |
| Assuming `send()` proves handler completion | Fire-and-Forget has no business response | Use a probe or independent state query |
| Asserting internal status codes/exception messages | Couples tests to implementation details | Assert published application error contracts |

## 12. Pre-Merge Checklist

- Business logic has unit tests independent of RSocket.
- LocalTransport tests connect a real `RSocketRequester` to a real `RSocketMessageHandler`.
- Request-Response and Request-Stream are tested; other interaction models are tested if used.
- Routes, payloads, metadata, and MIME types are verified end-to-end.
- Real object codecs are tested, not only `String`/`byte[]`.
- Route, decode, metadata, handler, and cancellation errors have assertions.
- `StepVerifier` uses terminal expectations and finite timeouts.
- `@ConnectMapping` is tested if the application uses setup data/metadata.
- Fire-and-Forget is verified via probes when business side effects must be proven.
- Requester and server are disposed after tests.
- At least one transport integration test exists if production uses TCP/WebSocket with custom settings.
- Tests can run in parallel without sharing ports or transport names.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework API — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Spring Framework API — RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)
- [RSocket Java — RSocketServer](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
