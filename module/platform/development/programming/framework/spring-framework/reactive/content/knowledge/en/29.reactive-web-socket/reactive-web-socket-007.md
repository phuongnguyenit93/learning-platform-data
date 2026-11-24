# WebSocketClient and Coordinating Connections in Spring WebFlux

## 1. Context and Goals

A Spring WebFlux application can act as both a WebSocket **server** for browsers and a WebSocket **client** for other systems. Examples include a gateway receiving price feeds from three sources, a backend connecting to hundreds of devices, or a chat service maintaining bidirectional channels.

The problem is not merely "opening a connection." You must determine:

- Is there one session or multiple independent sessions?
- Does the client send one command and receive one reply, or send and receive continuously?
- For results from multiple connections, should you wait for all of them, take the fastest result, or accept partial success?
- How many connections are opened simultaneously?
- When one session fails, should the other sessions be cancelled?
- When a connection drops, how do you reconnect without sending duplicate commands?
- Who is responsible for closing sessions and releasing buffers, timers, and subscriptions?

Spring WebFlux's WebSocketClient lets you initiate handshakes and handle sessions with a reactive API. Reactor's Mono/Flux help combine multiple sessions, limit fan-out, and propagate errors and cancellation consistently.

## 2. Distinguishing the Abstractions

| Component | Responsibility |
| --- | --- |
| WebClient | Reactive HTTP client for request/response and HTTP streaming |
| WebSocketClient | Initiates a WebSocket handshake and then runs WebSocketHandler for the session |
| ReactorNettyWebSocketClient | WebSocketClient backed by Reactor Netty |
| WebSocketHandler | Function handling a session's lifecycle, returning Mono<Void> |
| WebSocketSession | A WebSocket session with receive(), send(), close() |
| WebSocketMessage | Text, binary, or control message |
| Mono<Void> from execute() | Session completion/error, does not emit message payloads |

WebSocket differs from regular HTTP in that after the handshake, both sides send WebSocket messages over a long-lived connection without creating a separate HTTP request for each message.

WebSocket also does not prescribe a business message format: JSON envelopes, correlation IDs, ACKs, subscription topics, and replay rules must be defined by the application or a subprotocol such as STOMP. Plain WebSocketClient does not automatically become a STOMP client.

## 3. Creating WebSocketClient and the Handshake

### 3.1. Creating the Client

~~~java
import java.net.URI;

import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

import reactor.core.publisher.Mono;

WebSocketClient client = new ReactorNettyWebSocketClient();

URI uri = URI.create("ws://localhost:8080/ws/echo");

Mono<Void> lifecycle = client.execute(
        uri,
        session -> session.receive()
                .doOnNext(message ->
                        System.out.println(message.getPayloadAsText()))
                .then());
~~~

This snippet must be placed inside a Java method. execute() returns a **lazy Mono<Void>**: when a subscriber subscribes, the handshake begins and the handler runs. The Mono completes when session handling completes. No payload is emitted directly through Mono<Void>.

Typical HTTP/1.1 handshake:

~~~http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
~~~

When accepting, the server returns 101 Switching Protocols. Afterward, the connection uses WebSocket frames. HTTP/2 has an Extended CONNECT mechanism; not every environment uses the exact HTTP/1.1 handshake above.

### 3.2. Two execute Overloads

~~~java
Mono<Void> execute(URI uri, WebSocketHandler handler);

Mono<Void> execute(URI uri, HttpHeaders headers,
                   WebSocketHandler handler);
~~~

The overload with HttpHeaders is used to customize the handshake from a Java backend client:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);

Mono<Void> lifecycle = client.execute(
        URI.create("wss://stream.example/ws"),
        headers,
        session -> session.receive().then());
~~~

accessToken is a credential retrieved from a secure token-issuing system, never hardcoded. A Java client can set the Authorization header, whereas the browser WebSocket constructor does not allow setting arbitrary HTTP Authorization headers.

### 3.3. Choosing an Implementation

ReactorNettyWebSocketClient is appropriate in Spring Boot WebFlux using Reactor Netty. Spring Framework also supports other implementations (such as Jetty), though they can differ in lifecycle, TLS, backpressure, and frame configuration.

Do not confuse the reactive interface org.springframework.web.reactive.socket.client.WebSocketClient with WebSocketClient in the Servlet stack or browser APIs.

## 4. WebSocketSession Lifecycle

### 4.1. Methods to Remember

| API | Contract |
| --- | --- |
| receive() | Inbound Flux<WebSocketMessage>; typically completes when the session closes |
| send(Publisher<WebSocketMessage>) | Mono<Void> finishing when the outbound source completes and messages are written |
| textMessage(String) | Creates a text message from a String |
| binaryMessage(...) | Creates a binary message using DataBufferFactory |
| close() | Mono<Void> closing the session normally when subscribed |
| close(CloseStatus) | Closes with a specific code/reason |
| closeStatus() | Publisher reporting the close status |
| getHandshakeInfo() | Handshake metadata |
| getId() | ID of the current session |

The handler must return a Mono<Void> reflecting **the entirety of session work**. If the handler returns Mono.empty() immediately while calling subscribe() separately for receive/send, the framework may consider the session finished while independent tasks are still running.

### 4.2. Reactive Echo Server

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> outgoing = session.receive()
            .filter(message ->
                    message.getType() == WebSocketMessage.Type.TEXT)
            .map(message -> session.textMessage(
                    "echo: " + message.getPayloadAsText()));

    return session.send(outgoing);
}
~~~

One inbound stream is transformed into one outbound stream. There is no manual subscribe(). For text messages, getPayloadAsText() is called synchronously inside the mapper, so no pooled DataBuffer is held past the message's lifecycle.

If you need to pass a raw message to an asynchronous task and hold the buffer, check the DataBuffer/WebSocketMessage retain/release contract. The simpler approach for text is copying the payload into a String before crossing the asynchronous boundary.

### 4.3. Independent Send and Receive Directions

~~~java
Mono<Void> receive = session.receive()
        .doOnNext(msg -> processText(msg.getPayloadAsText()))
        .then();

Flux<WebSocketMessage> outgoing =
        commands.map(session::textMessage);

Mono<Void> send = session.send(outgoing);

return Mono.when(receive, send);
~~~

This is an illustrative snippet; processText and commands are supplied by the application. Mono.when subscribes to both branches and waits for completion. If receive is an infinite stream and commands also never ends, the session stays alive until close, cancellation, or error.

Do not make multiple independent session.send calls on the same session without coordination. When there are multiple producers, merge them into **a single outbound Publisher** (with a bounded queue and appropriate overload policy) and send via one session.send call.

## 5. Coordinating Two or More Connections

### 5.1. Waiting for Sessions to Complete with Mono.when

~~~java
Mono<Void> sessionA = client.execute(uriA, handlerA);
Mono<Void> sessionB = client.execute(uriB, handlerB);

Mono<Void> allDone = Mono.when(sessionA, sessionB);
~~~

Mono.when coordinates completion of publishers and propagates errors. It fits multiple Mono<Void> tasks. If sessions are designed to live for hours, allDone likewise does not complete until the sessions finish.

**Do not use Mono.zip(sessionA, sessionB) to get two messages** because Mono<Void> emits no onNext values, leaving zip with no data to combine into a tuple.

### 5.2. Getting One Business Reply per Session, Then Zipping

If each session sends one command, receives one reply, and closes, the application can build an echo method returning Mono<String>. Then:

~~~java
Mono<String> replyA = gateway.echo(uriA, "ping");
Mono<String> replyB = gateway.echo(uriB, "ping");

Mono<String> combined = Mono.zip(
        replyA,
        replyB,
        (left, right) -> "A=" + left + "; B=" + right);
~~~

gateway.echo is a custom method written in the example at the end of this lesson, not a built-in Spring method. Mono.zip waits for both sources to emit values; if one source errors, zip defaults to fail-fast and cancels the other source. If one source completes empty, zip likewise lacks enough data to combine.

A WebSocket session can receive multiple messages or return replies out of command order. Therefore, a "send one, receive one" model is valid only when the upstream has an explicit contract. For multiple concurrent commands on the same session, you need a correlationId and a registry of pending replies.

### 5.3. Multiple Independent URIs: Flux.flatMap

~~~java
Flux<WsReply> replies = Flux.fromIterable(targets)
        .flatMap(target ->
                gateway.echo(target.uri(), "ping")
                        .map(text -> new WsReply(
                                target.label(), text)),
                4);
~~~

Here flatMap with maxConcurrency=4 allows at most four inner Publishers to be subscribed concurrently within one subscription. When each inner Publisher performs a short WebSocket exchange and ends after the reply, that also bounds active sessions running through this pipeline.

If each handler holds an infinite stream, all four slots stay occupied until those four sessions close; subsequent targets are not yet subscribed. This is critical when coordinating multiple **long-lived** connections.

### 5.4. flatMap, flatMapSequential, and concatMap

| Operator | Parallel Sessions? | Output Order |
| --- | --- | --- |
| flatMap(mapper, 4) | Yes, up to 4 inner publishers | In completion order |
| flatMapSequential(mapper, 4, 1) | Yes, up to 4 inner publishers | Preserves target order |
| concatMap(mapper) | No, sequentially one inner publisher at a time | Preserves target order |

For example, source A replies in 800 ms, B in 100 ms, and C in 400 ms. With flatMap, output may be B, C, A. With flatMapSequential, output is A, B, C, though B/C may have to wait in a queue. With concatMap, B starts only after A completes.

If upstream does not depend on order and you want to reduce total aggregation time, flatMap is the common choice. If business logic requires exact list order, use flatMapSequential. If one session must complete before opening the next, use concatMap.

## 6. Per-Subscription Concurrency Is Not a System-Wide Quota

maxConcurrency applies per subscription of a single Flux. If an HTTP endpoint in your application builds a flatMap(..., 8) pipeline, 20 concurrent HTTP requests can open more than 8 WebSocket sessions across the entire application.

Distinguish between:

- **Per-batch concurrency:** bounds inner publishers of a single subscription via flatMap.
- **Global bulkhead:** bounds process-wide session count using a shared limiter; permits must be released on complete/error/cancel.
- **Rate limit:** bounds handshakes or messages per second, distinct from open connection count.
- **Transport resources:** connections, buffers, sockets, threads/event loops, and file descriptors.
- **Upstream quota:** limits per tenant, account, token, or IP enforced by the server.

Do not call blocking Semaphore.acquire() directly on an event loop. If a global limiter is needed, choose an asynchronous permit-acquisition model, ensure reliable cleanup, and test races/cancellation.

A connection after a WebSocket handshake is not equivalent to an HTTP keep-alive connection ready to serve the next HTTP request. Do not assume maxConnections in an HTTP pool equals the business WebSocket session limit.

## 7. Errors, Cancellation, and Partial Success

### 7.1. Default Error Behavior

When an inner publisher in flatMap emits an error, downstream receives the error by default and remaining inner publishers in that subscription may be cancelled.

This is appropriate when a batch is meaningful only if every source succeeds. However, aggregation dashboards often want to display remaining results even if one source is offline.

### 7.2. Recovering Errors Inside Each Mapper

~~~java
Flux<TargetResult> results = Flux.fromIterable(targets)
        .flatMap(target ->
                gateway.echo(target.uri(), "ping")
                        .map(text -> TargetResult.ok(
                                target.label(), text))
                        .onErrorResume(error -> Mono.just(
                                TargetResult.failed(
                                        target.label(),
                                        classify(error)))),
                4);
~~~

This snippet uses application-defined TargetResult and classify. Place onErrorResume **inside** the mapper so one failing endpoint does not cancel the entire batch. Never return raw exceptions, tokens, or URLs containing credentials to clients.

If you place onErrorResume after flatMap, the first error may already have cancelled the other sessions before the fallback runs.

Mono.whenDelayError and Mono.zipDelayError delay errors across multiple sources until the other sources have had a chance to finish. They do not turn errors into successes; for long-lived sessions, delaying can stretch indefinitely without timeouts.

### 7.3. Categorizing Timeouts

~~~java
Mono<Void> lifecycle = client.execute(uri, handler)
        .timeout(Duration.ofSeconds(10));
~~~

This is a timeout for the **entire Mono<Void>**, not just the handshake. If the handler is meant to hold a session for hours, that timeout closes the session after 10 seconds even when completely healthy.

Distinguish:

1. Handshake/connection timeout.
2. First-reply timeout after sending a command.
3. Idle timeout when no data/heartbeat is received.
4. Total duration of a short exchange.
5. Maximum session lifetime.
6. Shutdown/close timeout.

For example, a one-shot send-and-receive echo might use a 5-second timeout for the whole exchange. A client continuously reading stock ticks should not time out just because the session has lived longer than 5 seconds.

### 7.4. Cancellation

When downstream cancels the subscription, Reactor propagates cancellation to inner sessions and the connector can terminate I/O. Do not open a detached subscribe() if you want cancellation of the originating HTTP request to propagate to the WebSocket client.

When closing intentionally, use session.close() in the returned publisher. When a close code/reason is needed, use close(CloseStatus) and avoid putting sensitive information in the reason.

## 8. Reconnect and Delivery Semantics

### 8.1. retryWhen Runs Only on Error

~~~java
Mono<Void> reconnectOnError = client.execute(uri, handler)
        .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
                .maxBackoff(Duration.ofSeconds(20))
                .jitter(0.5));
~~~

retryWhen resubscribes when the source emits an error. If the server closes the session normally and the handler completes successfully, it does **not** automatically reconnect. If reconnecting after normal closure is also required, build a connection loop with delay, a stop condition, and dedicated shutdown lifecycle handling.

Never use unbounded repeat() without delay: it can cause a reconnect storm when an upstream or proxy repeatedly closes connections.

### 8.2. Message IDs, ACKs, and Replay

WebSocket provides message transport but does not guarantee a business command is processed exactly once. When a connection drops right after sending, the client cannot be certain whether the server received, processed, or replied to it.

For critical operations, design:

- Unique correlationId/messageId.
- Server acknowledgement carrying the same ID.
- Pending request registry with timeouts and bounded capacity.
- Server-side idempotency/deduplication.
- Sequence numbers and a replay log if data must be recovered.
- Exponential backoff reconnect policy with jitter.
- Handling for late replies arriving after timeout and duplicate responses.

Do not unconditionally retry a state-mutating command unless the server supports idempotency.

### 8.3. Do Not Subscribe to the Same Cold Publisher Twice

~~~java
Mono<Void> lifecycle = client.execute(uri, handler);

// Illustrative anti-pattern; do not use in services:
lifecycle.subscribe();
lifecycle.subscribe();
~~~

Two subscriptions can trigger two handshakes and two separate sessions. To share one connection across multiple callers, use a connection manager owning one session with a single outbound publisher and an inbound message dispatcher; share() on Mono<Void> does not automatically create a message multiplexer.

## 9. One Session with Many Messages or Many Independent Sessions?

### 9.1. One Session, Many Commands

One socket can handle many commands. When the server replies out of send order, the client matches replies via correlationId:

~~~json
{"type":"request","correlationId":"req-82","payload":{"symbol":"ABC"}}
~~~

Response:

~~~json
{"type":"response","correlationId":"req-82","payload":{"price":12.5}}
~~~

A connection manager can use a Map<correlationId, Sinks.One<Reply>> for pending requests. Bound the entry count, remove entries on complete/error/cancel, handle races between timeout and reply, and never hand off raw DataBuffer ownership to recipients without cleanup.

There should be **one outbound send stream** aggregating multiple producers rather than multiple components calling session.send() individually.

### 9.2. Multiple Sessions to Different Systems

Multiple sessions fit when connecting to independent upstreams, devices, or tenants. This isolates state, errors, tokens, and reconnect policies, at the cost of extra handshakes, sockets, heartbeats, and memory.

Use flatMap with maxConcurrency for **finite** exchanges. For long-lived sessions, consider a manager tracking independent connections, a global limiter, resource quotas, a reconnect schedule, and a shutdown API.

If very large-scale pub/sub or fan-out across multiple application instances is needed, consider a message broker; WebSocketClient does not create a distributed event log or guarantee replay.

## 10. Complete Java 17+ Spring Boot 3.5.16 Example

This example creates a WebSocket echo server at /ws/echo and a Java client coordinating multiple sessions. It includes:

- EchoWebSocketHandler: text echo server.
- SocketRouteConfiguration: URL mapping.
- ReactiveSocketCoordinator: Java WebSocketClient sending one text, awaiting one reply, closing the session, and returning Mono<String>.
- gather: runs one exchange per target with bounded active sessions.
- gatherOrdered: ordered fan-out.
- Integration test using a real server on a random port and StepVerifier.

In this demo, each exchange is a **finite** session: send one text, receive one text, close. Do not blindly apply the same lifecycle to clients that must keep an infinite stream open.

### 10.1. File Structure

~~~text
webflux-ws-client-demo/
├── pom.xml
└── src/
    ├── main/java/example/ws/
    │   ├── DemoApplication.java
    │   ├── EchoWebSocketHandler.java
    │   ├── SocketRouteConfiguration.java
    │   ├── WsTarget.java
    │   ├── WsReply.java
    │   └── ReactiveSocketCoordinator.java
    └── test/java/example/ws/
        └── ReactiveSocketCoordinatorTest.java
~~~

### 10.2. pom.xml

~~~xml
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
    <groupId>example</groupId>
    <artifactId>webflux-ws-client-demo</artifactId>
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
~~~

### 10.3. DemoApplication.java

~~~java
package example.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.4. EchoWebSocketHandler.java

~~~java
package example.ws;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> outgoing = session.receive()
                .filter(message ->
                        message.getType() == WebSocketMessage.Type.TEXT)
                .map(message -> session.textMessage(
                        "echo: " + message.getPayloadAsText()));

        return session.send(outgoing);
    }
}
~~~

The server sends back a new text message for every received text message. No manual subscribe; session.send directly consumes the Flux derived from receive.

### 10.5. SocketRouteConfiguration.java

~~~java
package example.ws;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration(proxyBeanMethods = false)
public class SocketRouteConfiguration {

    @Bean
    HandlerMapping echoSocketMapping(EchoWebSocketHandler handler) {
        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/echo", handler));
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

Spring Boot WebFlux provides WebSocketHandlerAdapter by default. Do not add @EnableWebFlux just to create this URL mapping.

### 10.6. WsTarget.java

~~~java
package example.ws;

import java.net.URI;

public record WsTarget(String label, URI uri) {
}
~~~

### 10.7. WsReply.java

~~~java
package example.ws;

public record WsReply(String label, String payload) {
}
~~~

### 10.8. ReactiveSocketCoordinator.java

~~~java
package example.ws;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.function.Function;

import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.WebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

public final class ReactiveSocketCoordinator {

    private final WebSocketClient client;

    public ReactiveSocketCoordinator(WebSocketClient client) {
        this.client = client;
    }

    public Mono<String> echo(URI uri, String text) {
        return Mono.defer(() -> {
            Sinks.One<String> answer = Sinks.one();

            Mono<Void> lifecycle = client.execute(uri, session -> {
                Mono<Void> outbound = session.send(
                        Mono.just(session.textMessage(text)));

                Mono<Void> inbound = session.receive()
                        .filter(message ->
                                message.getType()
                                        == WebSocketMessage.Type.TEXT)
                        .next()
                        .switchIfEmpty(Mono.error(
                                new IllegalStateException(
                                        "Peer closed without text reply")))
                        .doOnNext(message ->
                                answer.tryEmitValue(
                                        message.getPayloadAsText()))
                        .then();

                return Mono.when(outbound, inbound)
                        .then(session.close());
            });

            return lifecycle
                    .then(answer.asMono())
                    .timeout(Duration.ofSeconds(5));
        });
    }

    public Flux<WsReply> gather(
            List<WsTarget> targets,
            String text,
            int maxSessions
    ) {
        return bounded(
                targets,
                target -> echo(target.uri(), text)
                        .map(reply -> new WsReply(
                                target.label(), reply)),
                maxSessions
        );
    }

    public Flux<WsReply> gatherOrdered(
            List<WsTarget> targets,
            String text,
            int maxSessions
    ) {
        if (maxSessions < 1) {
            return Flux.error(new IllegalArgumentException(
                    "maxSessions must be positive"));
        }

        return Flux.fromIterable(targets)
                .flatMapSequential(
                        target -> echo(target.uri(), text)
                                .map(reply -> new WsReply(
                                        target.label(), reply)),
                        maxSessions,
                        1
                );
    }

    static <T, R> Flux<R> bounded(
            Iterable<T> items,
            Function<T, Mono<R>> operation,
            int maxSessions
    ) {
        if (maxSessions < 1) {
            return Flux.error(new IllegalArgumentException(
                    "maxSessions must be positive"));
        }

        return Flux.fromIterable(items)
                .flatMap(operation, maxSessions);
    }
}
~~~

**Explanation of the Sinks.One mechanism:**

execute() only returns the Mono<Void> of the session lifecycle. However, business logic needs the text reply. Sinks.One<String> lets the handler emit a value back to the caller:

1. Mono.defer creates a fresh sink per subscription, preventing replies from different calls from mixing.
2. The handler starts send and receive with Mono.when.
3. receive().next() takes the first text message.
4. doOnNext reads the payload as a String and emits it into the sink.
5. session.close() ends the session after both outbound and inbound complete.
6. lifecycle.then(answer.asMono()) returns the result once the session has closed.
7. timeout cancels the exchange if no reply arrives on time.
8. If the peer closes before sending text, switchIfEmpty turns it into an error.

A single Sinks.One suits **one** reply. For multiple pending commands on the same socket, use correlationId and a bounded registry instead of a shared sink.

### 10.9. ReactiveSocketCoordinatorTest.java

~~~java
package example.ws;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveSocketCoordinatorTest {

    @LocalServerPort
    int port;

    private ReactiveSocketCoordinator coordinator;

    @BeforeEach
    void setUp() {
        coordinator = new ReactiveSocketCoordinator(
                new ReactorNettyWebSocketClient());
    }

    private URI endpoint() {
        return URI.create(
                "ws://127.0.0.1:" + port + "/ws/echo");
    }

    @Test
    void sendsAndReceivesOneTextMessage() {
        StepVerifier.create(coordinator.echo(endpoint(), "hello"))
                .expectNext("echo: hello")
                .verifyComplete();
    }

    @Test
    void coordinatesThreeConnections() {
        List<WsTarget> targets = List.of(
                new WsTarget("alpha", endpoint()),
                new WsTarget("beta", endpoint()),
                new WsTarget("gamma", endpoint())
        );

        StepVerifier.create(
                        coordinator.gather(targets, "ping", 2)
                                .collectList())
                .assertNext(replies -> {
                    assertThat(replies).hasSize(3);
                    assertThat(replies)
                            .extracting(WsReply::label)
                            .containsExactlyInAnyOrder(
                                    "alpha", "beta", "gamma");
                    assertThat(replies).allSatisfy(reply ->
                            assertThat(reply.payload())
                                    .isEqualTo("echo: ping"));
                })
                .verifyComplete();
    }

    @Test
    void preservesTargetOrderWhenRequested() {
        List<WsTarget> targets = List.of(
                new WsTarget("one", endpoint()),
                new WsTarget("two", endpoint()),
                new WsTarget("three", endpoint())
        );

        StepVerifier.create(
                        coordinator.gatherOrdered(targets, "ok", 2))
                .assertNext(reply -> assertThat(reply.label())
                        .isEqualTo("one"))
                .assertNext(reply -> assertThat(reply.label())
                        .isEqualTo("two"))
                .assertNext(reply -> assertThat(reply.label())
                        .isEqualTo("three"))
                .verifyComplete();
    }

    @Test
    void boundedOperatorLimitsActiveInnerPublishers() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        List<Integer> ids = IntStream.range(0, 8)
                .boxed()
                .toList();

        StepVerifier.create(
                        ReactiveSocketCoordinator.bounded(
                                ids,
                                id -> Mono.delay(
                                                Duration.ofMillis(60))
                                        .doOnSubscribe(subscription -> {
                                            int current =
                                                    active.incrementAndGet();
                                            maximum.accumulateAndGet(
                                                    current, Math::max);
                                        })
                                        .doOnTerminate(
                                                active::decrementAndGet)
                                        .map(ignored -> id),
                                2))
                .expectNextCount(8)
                .verifyComplete();

        assertThat(maximum.get()).isBetween(1, 2);
    }

    @Test
    void rejectsNonPositiveConcurrency() {
        StepVerifier.create(
                        coordinator.gather(List.of(), "ping", 0))
                .expectError(IllegalArgumentException.class)
                .verify();
    }
}
~~~

The test starts an embedded HTTP server on a random port; the Reactor Netty client creates real WebSocket connections. The bounded test uses Mono.delay to measure concurrent inner Publishers without relying on network timing. It tests the operator used by gather, not as a replacement for load tests measuring total TCP connections or global quotas.

### 10.10. Running the Project

Run tests from the directory containing pom.xml:

~~~bash
mvn test
~~~

Run the server:

~~~bash
mvn spring-boot:run
~~~

If websocat is installed, test manually:

~~~bash
websocat ws://localhost:8080/ws/echo
~~~

Type:

~~~text
hello
~~~

Receive:

~~~text
echo: hello
~~~

You can test via the browser JavaScript console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");
socket.addEventListener("open", () => socket.send("ping"));
socket.addEventListener("message", (event) => {
    console.log(event.data);  // echo: ping
    socket.close();
});
~~~

The browser snippet is a standalone JavaScript client; ReactorNettyWebSocketClient and the project's integration tests demonstrate the reactive Java client.

## 11. Custom Handshakes, Frame Limits, and Security

### 11.1. TLS and Credentials

Use wss:// in production. Verify TLS certificates and hostnames; never disable verification for convenience. Java's WebSocketClient allows adding HttpHeaders during the handshake, but use tokens from a secure credential manager.

Do not place long-lived access tokens in URI query strings because URIs can leak into access logs, tracing, or exceptions.

### 11.2. Origin and Authorization

The WebSocket server must enforce authentication and authorization for every resource after the handshake. Origin is useful for restricting browser cross-site connections; however, non-browser Java clients can set arbitrary Origin headers, so never treat Origin as a credential.

### 11.3. SSRF Prevention

If your API allows users to provide arbitrary URIs and the backend opens a WebSocket to those URIs, there is an SSRF risk. Allowlist schemes, hosts, ports, and paths; guard against DNS rebinding, loopback, private networks, and metadata services per policy.

### 11.4. Frame and Message Limits

Reactor Netty WebSocket client can be customized via WebsocketClientSpec:

~~~java
ReactorNettyWebSocketClient client =
        new ReactorNettyWebSocketClient(
                HttpClient.create(),
                () -> WebsocketClientSpec.builder()
                        .maxFramePayloadLength(64 * 1024));
~~~

Requires imports from reactor.netty.http.client.HttpClient and WebsocketClientSpec. Frame limits do not necessarily equal total application message size because a message can span multiple frames. Bound decoded payload size, receive rate, pending command count, and outbound queues as well.

## 12. Backpressure, Pooled Buffers, and a Single Outbound Writer

WebSocket streams are modeled with Flux/Mono, but backpressure does not automatically make all external systems stop pushing data. If upstream pushes faster than the client can process, use bounded buffers and an overload policy:

- For dashboard state that only needs the latest value: intentionally drop/coalesce older events.
- For critical commands/audits: use durable queues, flow control, or load shedding.
- For slow clients: bound outbound queues, disconnect, or reduce update frequency per contract.
- For multiple producers: merge messages into one Publisher and call session.send once.

WebSocketMessage wraps a DataBuffer; on Netty this may be pooled direct memory. Decoding synchronously inside the callback into a String usually avoids holding the buffer. If storing a message beyond the callback lifecycle, follow the retain/release contract, including on errors and cancellation.

## 13. Monitoring and Graceful Shutdown

Useful metrics:

- Active sessions by upstream/tenant, avoiding high label cardinality.
- Handshake duration, handshake failures, TLS errors.
- Session duration and close status.
- Reconnect attempts, backoff, retry exhaustion.
- Messages sent/received, message sizes, payload validation failures.
- Pending command count, timeout count, and replay gaps.
- Outbound buffer depth, dropped/coalesced events.
- CPU, heap, direct memory, file descriptors, and network traffic.

Reactor Netty provides WebSocket client metrics such as reactor.netty.websocket.client.handshake.time, connection.duration, data.sent/received, and errors when metrics are enabled.

During shutdown: stop opening new connections, stop generating new outbound commands, give pending work a bounded window to complete, close sessions intentionally, cancel remaining subscriptions/timers, and stop reconnect loops. If multiple instances restart simultaneously, add jitter to prevent reconnection storms.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating WebSocketClient like WebClient GET | Misunderstands lifecycle and payloads | Use execute with WebSocketHandler |
| Expecting execute to return Mono<String> | execute only signals completion | Build a result Mono per message contract |
| Using Mono.zip on Mono<Void> | No onNext values to combine | Use Mono.when for completion |
| Calling subscribe separately inside handler | Handler finishes before real work | Compose inbound/outbound in returned Mono |
| Subscribing to the same cold execute twice | Creates two independent sessions | Manage ownership of one session |
| Calling session.send from uncoordinated streams | Outbound contention and ordering bugs | One bounded outbound publisher |
| Unbounded flatMap | Exhausts connections, buffers, upstream quotas | maxConcurrency and global bulkhead |
| Assuming maxConcurrency is global | Multiple callers still open too many sessions | Share a limiter across subscriptions |
| Using flatMap when order must be preserved | Replies arrive out of order | flatMapSequential |
| Using concatMap when parallelism is needed | Low throughput | flatMap if sources are independent |
| Placing onErrorResume after the batch | One failing source cancels all others | Recover inside the mapper |
| Relying on retryWhen for graceful close | Does not reconnect on onComplete | Dedicated reconnect policy |
| Retrying commands without ACK/idempotency | Can cause duplicate side effects | Correlation IDs, ACKs, deduplication |
| Applying a short timeout to a long-lived session | Closes healthy active sessions | Separate handshake, idle, and reply timeouts |
| Ignoring pooled buffer ownership | Use-after-release or leaks | Copy payloads or retain/release |
| Putting tokens in URIs | Leaks credentials into logs | Handshake headers/credential management |
| Unbounded queues/payloads | Slow clients cause out-of-memory errors | Bounded queues and overload policies |
| Missing cleanup on cancel/shutdown | Leaks sessions/permits/timers | Clean up inside lifecycle |
| Opening WebSockets to arbitrary user URIs | SSRF | Allowlist and validate targets |

## 15. Production Checklist

- [ ] Choose one or many connections based on the use case, not API convenience.
- [ ] Every session has a clear owner and explicit complete/error/cancel/close conditions.
- [ ] Never call nested subscribe() inside reactive handlers.
- [ ] When callers need replies, enforce a proper correlation/result publisher contract.
- [ ] Distinguish per-batch max concurrency from global quotas.
- [ ] Configure timeouts for handshake, reply, idle, and shutdown.
- [ ] Configure reconnect backoff/jitter and stop conditions.
- [ ] When command execution guarantees are needed, implement ACKs, IDs, and idempotency.
- [ ] Bound outbound queues, pending requests, and message sizes.
- [ ] Use wss:// and enforce TLS, token, and authorization checks.
- [ ] Validate URIs to prevent SSRF.
- [ ] Track metrics for active sessions, handshakes, closures, queues, and errors.
- [ ] Test multiple connections, single-target failure, cancellation, and server closure.
- [ ] Implement graceful shutdown cleaning up sessions, timers, and pending resources.

## 16. Key Takeaways

- WebSocketClient is used to **open and handle sessions**; ReactorNettyWebSocketClient is one implementation.
- execute(URI[,HttpHeaders], WebSocketHandler) returns Mono<Void> tied to the session lifecycle.
- session.receive() is the inbound Flux; session.send(Publisher) is the outbound Mono<Void>.
- To combine completion of multiple Mono<Void> sessions, use Mono.when; to combine business results with values, use Mono.zip on result Monos.
- Use flatMap(maxConcurrency) for finite independent sessions; flatMapSequential preserves order; concatMap runs sequentially.
- Per-subscription concurrency limits do not replace application-wide connection quotas.
- retryWhen retries only on errors, not automatically after graceful close.
- WebSocket does not automatically guarantee ACKs, durable delivery, or exactly-once semantics.
- Every session requires managing backpressure, buffers, timeouts, security, and cleanup.

**Official Documentation:**
- [Spring Framework 6.2 — WebFlux WebSocket, Client, and WebSocketHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-websocket.html)
- [Spring Framework 6.2 — WebSocketClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/reactive/socket/client/WebSocketClient.html)
- [Spring Framework 6.2 — Reactive WebSocketSession Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0-RC1/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html)
- [Spring Framework 6.2 — Reactive WebSocketMessage Javadoc](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html)
- [Project Reactor — Flux and Mono API](https://projectreactor.io/docs/core/release/reference/)
- [Reactor Netty — HTTP Client and WebSocket Metrics](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Spring Boot 3.5.16 Release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
- [RFC 6455 — WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
