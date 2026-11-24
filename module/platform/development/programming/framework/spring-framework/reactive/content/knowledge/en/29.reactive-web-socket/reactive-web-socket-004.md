# Reading receive, Writing send, and Combining Bidirectional Lifecycles in Spring WebFlux WebSocket

## 1. WebSocket Is a Bidirectional Communication Channel

WebSocket creates a full-duplex connection between client and server over a single TCP connection. After a successful HTTP handshake, both sides can send and receive messages independently without creating a new HTTP request for each message.

In Spring WebFlux, the core reactive APIs are:

- `WebSocketHandler`: handles a WebSocket session; the `handle(WebSocketSession)` method returns `Mono<Void>`.
- `WebSocketSession.receive()`: provides a `Flux<WebSocketMessage>` of inbound messages.
- `WebSocketSession.send(Publisher<WebSocketMessage>)`: writes an outbound message publisher and returns `Mono<Void>` that completes when the source completes and writing finishes.
- `WebSocketSession.close(...)`: requests closing the session with a close status.
- `WebSocketSession.closeStatus()`: receives the session's close status if available.

Every handler must combine the inbound stream, outbound stream, and session termination rules into a single reactive flow. If you create a publisher without returning it from `handle` or composing it into the returned publisher, work may not run or the session lifecycle may terminate incorrectly.

## 2. Lifecycle from Handshake to Closure

~~~text
Client                              Spring WebFlux
  |                                      |
  |--- HTTP Upgrade: websocket -------->|
  |<-- 101 Switching Protocols ---------|
  |                                      |
  |<====== WebSocket connection ========>|
  |                                      |
  |--- message A ----------------------->|
  |--- message B ----------------------->|
  |<-- reply A --------------------------|
  |<-- reply B --------------------------|
  |                                      |
  |--- Close frame --------------------->|
  |<-- Close frame / connection ends ---|
  |                                      |
  |        receive completes/errors      |
  |        send is completed/cancelled   |
  |        handle Mono terminates        |
~~~

There are three milestones to distinguish:

1. **Handshake:** HTTP upgrades to WebSocket. The handler is invoked only after the session has been established.
2. **Message exchange:** inbound and outbound operate concurrently; each stream has its own demand, completion, error, and cancellation.
3. **Termination:** the client closes, the server proactively closes, a protocol error occurs, a processing error occurs, or the caller cancels. The publisher returned from the handler must accurately reflect when the application finishes handling the session.

WebSocket is a connection-stateful protocol. Do not treat it like an HTTP controller that returns a response and finishes immediately.

## 3. Two Core APIs: receive and send

### 3.1. receive(): Reading Inbound Messages

`receive()` returns `Flux<WebSocketMessage>`:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.receive()
            .doOnNext(message ->
                    log.debug("Inbound type={}", message.getType()))
            .then();
}
~~~

- Each element represents one WebSocket message.
- The receive stream emits completion or error when the connection closes.
- `then()` discards elements and turns the Flux's completion/error into a `Mono<Void>`.
- Publishers only execute when subscribed to. Returning the publisher from `handle` causes the framework to subscribe and manage the lifecycle.

Do not call `subscribe()` separately inside the handler:

~~~java
// Wrong: detaches receive from the lifecycle managed by the framework.
session.receive().subscribe(this::process);
return Mono.empty();
~~~

The handler above can finish immediately while message-reading work continues running independently. Errors, cancellation, and session closure are then no longer coordinated properly.

### 3.2. send(): Writing Outbound Messages

`send(Publisher<WebSocketMessage>)` accepts a message source and returns `Mono<Void>`:

~~~java
Flux<WebSocketMessage> outgoing = Flux.just(
        session.textMessage("first"),
        session.textMessage("second"));

return session.send(outgoing);
~~~

`send` completes when the outbound source completes and all message writes finish. If the source never completes, the send stream stays alive until the session or source is terminated.

Use the session's factories to create messages:

~~~java
WebSocketMessage text =
        session.textMessage("hello");

WebSocketMessage binary =
        session.binaryMessage(
                factory -> factory.wrap(new byte[] {1, 2, 3}));

WebSocketMessage ping =
        session.pingMessage(
                factory -> factory.wrap(new byte[] {1}));

WebSocketMessage pong =
        session.pongMessage(
                factory -> factory.wrap(new byte[] {1}));
~~~

These factories use the session's `DataBufferFactory`. For binary payloads, data is supplied through the factory callback.

### 3.3. Message Types and Reading Payloads

`WebSocketMessage.Type` has the following types:

| Type | Content |
| --- | --- |
| `TEXT` | Text message |
| `BINARY` | Binary message |
| `PING` | Ping control message |
| `PONG` | Pong control message |

`getPayloadAsText()` decodes the payload using UTF-8 by default. Use it only when the message is text or the payload is agreed to be text:

~~~java
String text = message.getPayloadAsText();
~~~

For binary messages, read `getPayload()` as a `DataBuffer` and process bytes according to the application's protocol. Do not use `getPayloadAsText()` to decode arbitrary binary data.

## 4. Simplest Pattern: Read a Message and Reply

For an echo server, outbound messages can be produced directly from inbound messages:

~~~java
@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> replies = session.receive()
                .map(message ->
                        session.textMessage(
                                "echo:" + message.getPayloadAsText()));

        return session.send(replies);
    }
}
~~~

How the flow works:

1. `receive()` reads messages from the client.
2. `map` synchronously extracts text and creates a new text message.
3. `send` writes each generated message.
4. The handler stays alive while the inbound source still emits messages and the session remains active.

This is a single flow that naturally binds both directions: outbound is driven by inbound. There is no need to create two independent subscriptions for the same receive source.

This example defines a text-only protocol. If the endpoint must accept binary, branch on `message.getType()` and convert bytes using the binary message factory.

## 5. Asynchronous Per-Message Processing with concatMap

When each message needs to call a service, database, or another publisher, use an operator that subscribes to and waits for the inner publisher to complete:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> replies = session.receive()
            .concatMap(message ->
                    messageService.process(message.getPayloadAsText())
                            .map(result ->
                                    session.textMessage(result)));

    return session.send(replies);
}
~~~

`concatMap` processes sequentially:

- The next message is processed only after the current message's publisher completes.
- Input order is preserved in the reply order.
- A slow operation makes subsequent messages wait; this is an intentional choice when ordering matters.

Do not use `doOnNext` to launch a reactive task and discard the publisher:

~~~java
// Wrong: process() is not composed into the lifecycle.
session.receive()
        .doOnNext(message ->
                messageService.process(message.getPayloadAsText()).subscribe());
~~~

The right approach is returning the publisher from `concatMap`, `flatMap`, or another appropriate operator.

### 5.1. concatMap, flatMap, and flatMapSequential

| Operator | Processing Style | When Suitable |
| --- | --- | --- |
| `concatMap` | One inner publisher at a time, preserves order | Chat, commands, ordered state updates |
| `flatMap` | Allows multiple inner publishers concurrently; results may interleave | Independent messages, throughput needed |
| `flatMapSequential` | Runs inner publishers concurrently but emits results in source order | Concurrent processing while preserving reply order |

Example with bounded concurrency:

~~~java
Flux<WebSocketMessage> replies = session.receive()
        .flatMap(
                message -> messageService.process(
                                message.getPayloadAsText())
                        .map(session::textMessage),
                8);
~~~

The number `8` is the maximum concurrency for inner publishers in this example. Choose it based on downstream service capacity and realistic load limits.

If messages mutate state or depend on preceding messages, concurrency can break business ordering. Keep `concatMap` in that case.

## 6. Two Independent Streams: Processing Inbound and Proactively Pushing Outbound

Not every outbound message is a direct reply to a just-received message. The server may need to send notifications from an event bus, background task, timer, or another service while still receiving commands from the client.

Composition pattern:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Mono<Void> input = session.receive()
            .concatMap(message ->
                    commandService.handle(
                            session.getId(),
                            message.getPayloadAsText()))
            .then();

    Flux<String> notifications =
            notificationService.eventsFor(session.getId());

    Mono<Void> output = session.send(
            notifications.map(session::textMessage));

    return input.and(output);
}
~~~

Here:

- `input` owns reading and processing inbound messages.
- `output` owns an independent notification source.
- `and` combines the termination signals into a single `Mono<Void>`.
- Errors from either branch propagate to the composed result; the remaining branch is coordinated according to operator semantics and session state.

`notificationService.eventsFor` and `commandService.handle` are hypothetical application services. Ensure they return reactive publishers and do not block the event loop.

### 6.1. Choosing a Termination Policy for Two Branches

Different lifecycle requirements exist:

**Wait for both branches to finish normally:**

~~~java
return Mono.when(input, output);
~~~

`Mono.when` waits for all publishers to complete; if one publisher errors, other still-running publishers are cancelled.

**Terminate when whichever branch emits a terminal signal first:**

~~~java
return Mono.firstWithSignal(input, output);
~~~

`firstWithSignal` picks the first signal (complete or error) and cancels the other branch. Use this when either branch ending must cause the handler to terminate immediately.

**Use `and`:**

~~~java
return input.and(output);
~~~

`Mono.and` combines the termination signals of two sources into a single `Mono<Void>`. This is the composition pattern Spring uses in examples with independent inbound/outbound streams. Understand the semantics of both publishers and how the connector finishes send when the socket closes.

Do not use `Mono.zip(input, output)` merely to coordinate two void tasks. Zip waits for each Mono to emit a value; `Mono<Void>` completes empty, so zip does not match the intent of waiting for two tasks. Use `and` or `when` for publishers that only represent completion.

## 7. Merging Multiple Outbound Sources into One send

A session often has multiple outbound data sources: business notifications, application heartbeats, command results, or system events.

Merge them before calling `send`:

~~~java
Flux<WebSocketMessage> outgoing = Flux.merge(
        chatEvents.map(session::textMessage),
        statusEvents.map(session::textMessage),
        heartbeatEvents.map(session::textMessage));

return session.send(outgoing);
~~~

`Flux.merge` allows sources to emit interleaved items. Ordering across sources depends on emission timing, with no guarantee that all chat messages precede status messages.

If sequential ordering between sources is needed:

~~~java
Flux<WebSocketMessage> outgoing = Flux.concat(
        initialSnapshot.map(session::textMessage),
        liveEvents.map(session::textMessage));

return session.send(outgoing);
~~~

`concat` completes the first source before subscribing to the next. Do not use this if the first source is an infinite stream, as the second source will never be subscribed to.

**Practical rule:** a session should have one primary outbound publisher and one `session.send(...)` call managing writes. Feed sources into `merge`, `concat`, or a queue with an explicit policy before sending. Avoid having multiple components call send independently, which makes ordering and lifecycle control unpredictable.

## 8. Backpressure and Slow Readers

Reactive Streams uses demand to regulate data flow. Both `receive()` and `send()` sit inside the publisher chain, so processing and write speeds can influence demand.

Example:

~~~java
Flux<WebSocketMessage> replies = session.receive()
        .concatMap(message ->
                messageService.process(message.getPayloadAsText())
                        .map(session::textMessage));

return session.send(replies);
~~~

If the service processes slowly, `concatMap` does not launch additional concurrent tasks at the same time. This helps bound in-flight work and preserve order.

If the client reads slowly, outbound writes can slow down accordingly. A source emitting faster than the write rate can accumulate data if the application actively buffers it.

### 8.1. Do Not Buffer Unboundedly

Do not turn an event stream into an unbounded queue:

~~~java
// Risk: a persistently slow client can cause the queue to grow without bound.
events.onBackpressureBuffer()
~~~

On a server with many sessions, each queue can hold payloads and objects until the client reads or disconnects. This causes memory pressure and can degrade the entire service.

Choose a policy per message category:

- **Command/audit:** do not drop silently; bound the queue and return an error or close the session when exceeded.
- **Latest state:** coalesce, keeping only the newest value if the protocol allows.
- **Telemetry:** drop in a controlled manner and measure the dropped count.
- **Chat/critical events:** require persistence or a broker so clients can resume, rather than relying solely on in-memory queues.

Backpressure does not solve every case automatically. Event sources outside Reactive Streams may be unaware of client demand; in those cases, use a bounded adapter/queue with an explicit overflow policy.

### 8.2. Handling Multiple Producers

If multiple business components generate outbound events for one session, you can route them into a sink/queue and use a single publisher for `send`.

Conceptual example with a bounded queue:

~~~java
Queue<ServerEvent> queue = new ArrayBlockingQueue<>(256);

Sinks.Many<ServerEvent> sink =
        Sinks.many().unicast().onBackpressureBuffer(queue);

Mono<Void> output = session.send(
        sink.asFlux().map(event ->
                session.textMessage(event.toJson())));
~~~

Producers call `sink.tryEmitNext(event)` and must handle the emission result. If the queue is full or emission fails, do not ignore the result; apply a policy such as bounded retry, reject, coalesce, or drop with metrics.

This is an illustrative structural snippet; you must manage the sink per session and complete/error it when the session ends. Do not share one sink across all clients if each client must receive its own set of events.

## 9. Buffer Ownership: retain and release in Asynchronous Processing

`WebSocketMessage` holds a `DataBuffer`. On Reactor Netty, payloads may use pooled buffers and reference counting. When code retains a payload beyond the message-receiving callback, the buffer may be released before asynchronous work finishes reading it.

### 9.1. Synchronous Text Reading

If you convert the payload to a String immediately inside an operator:

~~~java
Flux<String> textMessages = session.receive()
        .map(WebSocketMessage::getPayloadAsText);
~~~

String is a Java object independent of DataBuffer. If the service only needs String, you can pass the String across asynchronous steps without retaining WebSocketMessage.

### 9.2. Retaining a Message for Asynchronous Processing

If an operation needs to read the DataBuffer payload after the current callback ends, retain before transferring ownership and release after the processing publisher completes:

~~~java
Mono<Void> input = session.receive()
        .concatMap(message -> {
            message.retain();

            return Mono.defer(() ->
                            binaryService.store(message.getPayload()))
                    .doFinally(signal -> message.release());
        })
        .then();
~~~

In this example:

- `retain()` increments the reference count for the payload.
- `Mono.defer(...)` defers invoking the service until subscription.
- `doFinally(...)` releases the retained reference when the publisher completes, errors, or is cancelled.
- `concatMap` waits for the current task to complete before processing the next message.

`binaryService.store(...)` is a hypothetical service and must finish reading the payload before its publisher completes. If the service retains the buffer itself or hands it off to another task outliving the publisher, ownership must be explicitly transferred with a corresponding release by the final owner.

### 9.3. Do Not Retain Unnecessarily

Retaining an extra reference increases cleanup responsibility. If you only need text or small byte arrays, copying/converting synchronously and processing an independent object is usually simpler.

Never call release twice for the same reference. Never release the payload before downstream or the writer finishes. Never store a WebSocketMessage in a field or collection after the receive callback finishes without retaining and designing lifecycle cleanup.

## 10. Session Termination: complete, error, and cancel

`handle` returns `Mono<Void>` representing how long the application continues handling the session.

Scenarios:

| Event | Reactive Signal | Meaning |
| --- | --- | --- |
| Client sends close frame | receive completes per session lifecycle | No more inbound messages |
| Connection error | receive or send emits error | Handler must terminate or handle error intentionally |
| Outbound publisher completes | send completes after writes finish | Outbound source is exhausted |
| Caller cancels handler | Subscription is cancelled | Upstream work is requested to stop |
| Server calls close | close publisher completes/errors | Application proactively requests closing the session |

When inbound and outbound are composed properly, there is no need for a loop polling `session.isOpen()` to guess connection state. Reactive Streams propagates completion, error, and cancellation through publishers.

### 10.1. Deliberately Closing a Session

`close()` defaults to `CloseStatus.NORMAL`:

~~~java
Mono<Void> closeNormally(WebSocketSession session) {
    return session.close();
}
~~~

Or specify a close status:

~~~java
Mono<Void> closeWithReason(WebSocketSession session) {
    return session.close(
            new CloseStatus(1008, "Policy violation"));
}
~~~

Common codes in the WebSocket protocol:

| Code | Meaning |
| --- | --- |
| 1000 | Normal closure |
| 1001 | Going away |
| 1002 | Protocol error |
| 1003 | Unsupported data |
| 1008 | Policy violation |
| 1009 | Message too big |
| 1011 | Unexpected server condition |

Certain codes such as 1005 and 1006 are reserved for describing closing states internally in the protocol; do not send them as regular close frames.

`close` returns a Publisher. Compose it into the handler:

~~~java
return processCommand()
        .then(session.close(CloseStatus.NORMAL));
~~~

Do not call `session.close()` and ignore the returned Mono. Without subscribing/composing, the close operation is outside the managed lifecycle.

### 10.2. Reading Close Status

After the session ends, you can record the close status:

~~~java
return session.receive()
        .then(session.closeStatus())
        .doOnNext(status ->
                log.info("WebSocket closed: {}", status))
        .then();
~~~

`closeStatus()` returns `Mono<CloseStatus>`. The publisher may complete empty if the session ends without a close status.

`isOpen()` only reflects the state at the moment of the call; it does not replace receive/send terminal signals.

### 10.3. Cleanup with doFinally

`doFinally` runs after complete, error, or cancel:

~~~java
return session.send(outgoing)
        .doFinally(signal ->
                sessionRegistry.remove(session.getId()));
~~~

This is the right place for lightweight synchronous cleanup such as removing a session from a registry, recording metrics, or updating state. If cleanup is asynchronous and must finish before the handler completes, compose the cleanup Publisher using appropriate operators such as `then`, `onErrorResume`, or `usingWhen`.

Do not perform blocking I/O or heavy work inside a `doFinally` callback.

## 11. Error Handling in Both Directions

Errors can originate from:

- Malformed or protocol-violating payloads.
- A message-processing service emitting an error.
- An outbound source emitting an error.
- Abnormal network/connection closure.
- A writer unable to write a message.

Do not turn every error into an empty completion:

~~~java
// Avoid: loses the root cause and masks session errors.
return session.receive()
        .onErrorResume(error -> Flux.empty())
        .then();
~~~

If a message's business error is recoverable, handle it inside the inner publisher:

~~~java
Flux<WebSocketMessage> replies = session.receive()
        .concatMap(message ->
                messageService.process(message.getPayloadAsText())
                        .map(session::textMessage)
                        .onErrorResume(
                                RecoverableMessageException.class,
                                error -> Mono.just(
                                        session.textMessage(
                                                "error:" + error.getMessage()))));

return session.send(replies);
~~~

Unrecoverable errors should continue propagating out of the handler so the framework/connector terminates the session per lifecycle. If a specific close status is needed, translate the error into a deliberate session-closing flow and compose that result.

Log the session ID, message type, error category, and correlation ID. Avoid logging full payloads if messages contain tokens, personal data, or secrets.

## 12. A Complete Echo WebSocketHandler

The following example accepts only text messages and replies with the prefix `echo:`. Converting text to String occurs synchronously before creating the outbound message, so there is no need to retain the inbound buffer.

~~~java
package example.websocket;

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
        Flux<WebSocketMessage> replies = session.receive()
                .map(message -> {
                    if (message.getType()
                            != WebSocketMessage.Type.TEXT) {
                        throw new IllegalArgumentException(
                                "This endpoint accepts text messages only");
                    }

                    String text = message.getPayloadAsText();
                    return session.textMessage("echo:" + text);
                });

        return session.send(replies);
    }
}
~~~

This handler suffices to demonstrate the receive-to-send flow. Production endpoints must define how errors are returned for unsupported message types, message size limits, session authentication, and connection-closing policies.

## 13. Runnable Spring Boot WebFlux Java 17+ Program

The following project creates a WebSocket endpoint `/ws/echo` and an integration test using Spring's `WebSocketClient` to send two messages and assert both replies.

Requirements: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. The Spring Boot BOM manages compatible Spring Framework, Reactor, and Reactor Netty versions.

### 13.1. Directory Structure

~~~text
webflux-websocket-demo/
  pom.xml
  src/main/java/example/websocket/WebSocketDemoApplication.java
  src/main/java/example/websocket/WebSocketConfiguration.java
  src/main/java/example/websocket/EchoWebSocketHandler.java
  src/test/java/example/websocket/WebSocketIntegrationTest.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-websocket-demo</artifactId>
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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

### 13.3. Startup Class

**src/main/java/example/websocket/WebSocketDemoApplication.java**

~~~java
package example.websocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                WebSocketDemoApplication.class, args);
    }
}
~~~

### 13.4. Registering the WebSocket Endpoint

**src/main/java/example/websocket/WebSocketConfiguration.java**

~~~java
package example.websocket;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration
public class WebSocketConfiguration {

    @Bean
    HandlerMapping webSocketMapping(EchoWebSocketHandler handler) {
        Map<String, WebSocketHandler> handlers =
                Map.of("/ws/echo", handler);

        SimpleUrlHandlerMapping mapping =
                new SimpleUrlHandlerMapping();

        mapping.setUrlMap(handlers);
        mapping.setOrder(-1);

        return mapping;
    }
}
~~~

`SimpleUrlHandlerMapping` maps the URL to `WebSocketHandler`. When using Spring Boot WebFlux auto-configuration, `WebSocketHandlerAdapter` is configured by the WebFlux infrastructure. If the application does not use WebFlux config, register the corresponding adapter manually.

Do not add `@EnableWebFlux` just to register a WebSocket endpoint in a standard Boot application, as that annotation changes how Boot auto-configures WebFlux.

### 13.5. Echo Handler

**src/main/java/example/websocket/EchoWebSocketHandler.java**

~~~java
package example.websocket;

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
        Flux<WebSocketMessage> replies = session.receive()
                .map(message -> {
                    if (message.getType()
                            != WebSocketMessage.Type.TEXT) {
                        throw new IllegalArgumentException(
                                "Text messages only");
                    }

                    return session.textMessage(
                            "echo:" + message.getPayloadAsText());
                });

        return session.send(replies);
    }
}
~~~

The handler uses a pipeline that receives and transforms messages, then passes the resulting publisher to send. When inbound/session ends, the outbound publisher also terminates per the connection lifecycle.

### 13.6. Integration Test with WebSocketClient

**src/test/java/example/websocket/WebSocketIntegrationTest.java**

~~~java
package example.websocket;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void sendsAndReceivesMessagesConcurrently() {
        WebSocketClient client =
                new ReactorNettyWebSocketClient();

        URI url = URI.create(
                "ws://localhost:" + port + "/ws/echo");

        Mono<Void> sessionResult = client.execute(url, session -> {
            Flux<WebSocketMessage> messages = Flux.just(
                    session.textMessage("one"),
                    session.textMessage("two"));

            Mono<Void> send = session.send(messages);

            Mono<List<String>> receive = session.receive()
                    .map(WebSocketMessage::getPayloadAsText)
                    .take(2)
                    .collectList();

            return Mono.zip(
                            send.thenReturn(Boolean.TRUE),
                            receive)
                    .doOnNext(result ->
                            assertEquals(
                                    List.of("echo:one", "echo:two"),
                                    result.getT2()))
                    .then();
        });

        sessionResult.block(Duration.ofSeconds(5));
    }
}
~~~

Key points in the test:

- `send` and `receive` are subscribed concurrently via `Mono.zip`.
- The client does not wait for sending to finish before starting to read; the server can respond while the client is still writing.
- `take(2)` limits the two replies to verify.
- `block(Duration)` is used only at the test boundary to wait for the entire session; never call block inside a WebFlux handler or reactive service.

### 13.7. Running the Project and Tests

From the directory containing `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Maven test runs the integration test against a random port on localhost. The test verifies the exact two replies in order:

~~~text
echo:one
echo:two
~~~

You can test in a browser after the application starts:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.onopen = () => {
  socket.send("one");
  socket.send("two");
};

socket.onmessage = event => {
  console.log(event.data);
};
~~~

The console prints:

~~~text
echo:one
echo:two
~~~

## 14. Client Example with Independent Inbound and Outbound

The client side uses the same session API. Example of a client that both sends commands and receives notifications:

~~~java
WebSocketClient client = new ReactorNettyWebSocketClient();

Mono<Void> connected = client.execute(
        URI.create("ws://localhost:8080/ws/notifications"),
        session -> {
            Mono<Void> sendCommands = session.send(
                    Flux.just(
                            session.textMessage("subscribe:orders"),
                            session.textMessage("subscribe:alerts")));

            Mono<Void> receiveEvents = session.receive()
                    .concatMap(message -> {
                        String event = message.getPayloadAsText();
                        return eventProcessor.handle(event);
                    })
                    .then();

            return sendCommands.and(receiveEvents);
        });
~~~

This is an illustrative client snippet assuming an `eventProcessor`. The client must still keep a handler publisher as the session owner. If you only need to send a few commands and then continue receiving indefinitely, the composition must allow inbound to continue after the finite send source completes.

## 15. Testing Lifecycle and Edge Cases

A basic echo test only verifies the happy path. Real applications should also test:

| Scenario | What to Verify |
| --- | --- |
| Client sends multiple consecutive messages | No lost messages and order matches contract |
| Client closes normally | receive finishes and handler cleanup runs |
| Client drops network abruptly | error/cancel is handled, session registry is cleaned up |
| Message-processing service emits error | Error propagates or converts to an error message per policy |
| Outbound publisher completes | Handler applies the right close or continue-receiving policy |
| Outbound publisher emits infinitely | Connection closure cancels the outbound stream |
| Slow-reading client | Queue is bounded and memory does not grow unboundedly |
| Oversized message | Server rejects according to configured limits |
| Binary message sent to text endpoint | Endpoint rejects or handles per explicit protocol |
| Handler is cancelled | Downstream tasks and resources are cleaned up |
| Server proactively closes | Client receives close frame/status per contract |

Use `WebSocketClient` for integration tests over the real connector. Testing with a mock Flux can verify operator logic, but does not fully reproduce handshakes, close frames, network disconnects, or Netty behavior.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling receive().subscribe() inside handle | Handler finishes before inbound task | Return publisher or compose into Mono<Void> |
| Calling receive without then/send | Does not reflect session lifecycle | Return Mono<Void> from the processing flow |
| Calling send multiple times from multiple sources | Hard to control ordering and concurrent writers | Merge sources and make one send call |
| Using doOnNext to run a reactive service | Does not await task, errors are not composed | Use concatMap/flatMap |
| Using flatMap for order-dependent messages | Replies can arrive out of order | Use concatMap or flatMapSequential |
| Using collectList on an infinite stream | Unbounded memory accumulation | Process streaming per message |
| Unbounded outbound buffering | Slow clients cause memory growth | Bounded queue and overflow policy |
| Calling block inside handler | Blocks the event loop | Compose Mono/Flux |
| Holding WebSocketMessage for async tasks without retain | Payload may be released before reading | retain before, release in doFinally |
| Retaining without releasing | Leaks pooled buffers | Balance retain/release |
| Releasing message before send finishes writing | Writer may read a released buffer | Transfer ownership per contract |
| Calling session.close() and ignoring the Mono | Close operation is outside the lifecycle | Compose the close publisher |
| Polling isOpen() in a loop | Race conditions and complex code | Use complete/error/cancel signals |
| Swallowing all errors with onErrorResume | Protocol or system errors go undetected | Fall back only for recoverable errors |
| Using an infinite publisher unconnected to receive lifecycle | Session may hold resources after disconnect | Compose both branches and define cancellation |
| Using Mono.zip for Mono<Void> | Zip has no emitted values to combine | Use and/when/firstWithSignal |
| Not bounding payload size | High memory usage and DoS risk | Configure appropriate frame/message limits |
| Logging full payloads | Can expose sensitive data | Log metadata and redacted payloads |

## 17. Bidirectional WebSocket Design Checklist

- [ ] `handle(session)` returns `Mono<Void>` representing the session handling lifecycle.
- [ ] There is only one owning inbound pipeline for `session.receive()`.
- [ ] Outbound messages go through one publisher and one `session.send()` call.
- [ ] Inbound and outbound are explicitly composed.
- [ ] Complete/error/cancel rules are defined for each branch.
- [ ] Use concatMap when message processing order matters.
- [ ] Use flatMap with bounded concurrency when messages are independent.
- [ ] Backpressure and outbound queue limits are in place.
- [ ] Text/binary/control message protocol is defined.
- [ ] DataBuffer payloads are retained/released properly during async processing.
- [ ] Event loop is never blocked.
- [ ] Close publisher is composed into the flow.
- [ ] Registry/resource cleanup runs on complete, error, and cancel.
- [ ] Appropriate timeout/idle policy and heartbeats are configured if needed.
- [ ] Handshake has authentication, authorization, and origin policy.
- [ ] Tests cover handshake, echo, concurrent inbound/outbound, disconnect, and slow consumers.
- [ ] Metrics track session count, message rate, send latency, queue depth, and close reasons.

## 18. Self-Check

**Question 1.** What type does `session.receive()` return?

`Flux<WebSocketMessage>`, representing the inbound message stream.

**Question 2.** What type does `session.send(...)` return?

`Mono<Void>`, completing when the outbound source completes and message writes finish.

**Question 3.** Why must handle return Mono<Void>?

So the framework knows when the application has finished handling the session and can coordinate lifecycle, errors, and cancellation.

**Question 4.** How do you echo messages in WebFlux?

Map each message from `session.receive()` into a new WebSocketMessage and pass that Flux to `session.send()`.

**Question 5.** Which operator should be used when calling a reactive service per message while preserving order?

`concatMap`, because it waits for the current inner publisher to complete before processing the next message.

**Question 6.** When should flatMap be used?

When independent messages can be processed concurrently; bound concurrency and accept or manage output ordering.

**Question 7.** How do you send notifications independent of inbound messages?

Create a separate outbound publisher, call session.send for that publisher, and compose the inbound and outbound Mono<Void> instances.

**Question 8.** How do `Mono.and` and `Mono.firstWithSignal` differ?

`and` combines the termination of two sources; `firstWithSignal` finishes on whichever signal arrives first and cancels the remaining source.

**Question 9.** Why should Mono.zip not be used for two Mono<Void> instances?

Two Mono<Void> instances complete empty without emitting values for zip to combine into a tuple. Use completion-coordinating operators like and or when.

**Question 10.** When is `message.retain()` needed?

When keeping a pooled payload past the message-receiving callback so an asynchronous task can continue reading it afterward.

**Question 11.** What must be done after retain?

Release the extra reference when the task completes, errors, or is cancelled.

**Question 12.** Does `session.closeStatus()` always emit a value?

No. It can complete empty if the session ends without a close status.

**Question 13.** Why should an unbounded onBackpressureBuffer not be used?

A slow client can cause the outbound queue to grow without bound and exhaust memory.

**Question 14.** What is `doFinally` suitable for?

Observing complete/error/cancel and performing lightweight synchronous cleanup. Asynchronous cleanup must be composed if it must be awaited before completion.

## 19. Official References

- [Spring Framework — WebSockets in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html): WebSocketHandler, receive/send, lifecycle composition, client, and server.
- [WebSocketSession JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html): receive, send, close, closeStatus, message factories, and session metadata.
- [WebSocketMessage JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html): type, payload, getPayloadAsText, retain, and release.
- [WebSocketHandler JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/WebSocketHandler.html): contract for handle and sub-protocols.
- [WebSocketClient JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/client/WebSocketClient.html): execute handshake and client-side handler lifecycle.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled DataBuffer, reference counting, and cleanup.
- [Reactor Core — Mono JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): and, when, firstWithSignal, doFinally, and cancellation.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html): handshake, full-duplex framing, control frames, and close handshake.

**Key Takeaway:** `receive()` is the inbound stream, `send()` is the outbound stream, and `handle` must return a Mono<Void> controlling the connection lifecycle. You can drive outbound from inbound for echo or run two independent publishers and compose them. Choose operators matching your termination policy, preserve backpressure, avoid multiple writers, and properly retain/release payloads during asynchronous processing. When a session closes or is cancelled, all secondary branches and resources must terminate along the same lifecycle.