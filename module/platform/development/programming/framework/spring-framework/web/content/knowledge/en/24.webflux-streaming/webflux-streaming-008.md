# Reactive WebSocketHandler and Inbound/Outbound Stream Lifecycle in Spring WebFlux

## 1. Goal: One Connection, Two Asynchronous Streams

In regular HTTP REST, a client sends one request and gets one response. With **WebSocket**, the client first performs an **HTTP handshake**; once the server accepts the protocol upgrade, client and server can **send messages in both directions** over one long-lived connection. This fits chat, collaboration, live dashboards, games, and bidirectional event notifications well.

Spring WebFlux provides its WebSocket API in `org.springframework.web.reactive.socket`. The two most important types are:

- `WebSocketHandler`: handles the **entire WebSocket session** via `Mono<Void> handle(WebSocketSession session)`.
- `WebSocketSession`: provides the **inbound stream** `Flux<WebSocketMessage> receive()` and the **outbound stream** `Mono<Void> send(Publisher<WebSocketMessage>)`, plus handshake info, session ID, factories for text/binary/ping/pong messages, and close APIs.

This is neither an `@GetMapping` controller nor a WebFlux.fn `HandlerFunction<ServerResponse>`. WebSocket typically routes on an endpoint URL **only at handshake time**, after which the application must define its own **in-session message protocol**.

This lesson uses **Spring Boot 3.3.5, Spring Framework 6.1.x, Java 17, and Reactor**. The examples run on `spring-boot-starter-webflux` with Reactor Netty, requiring no Servlet MVC or STOMP libraries.

### Learning Outcomes

After this lesson, you will be able to:

1. Explain the HTTP 101 WebSocket handshake and the post-upgrade text/binary frame streams.
2. Distinguish `WebSocketHandler`, `WebSocketSession`, `WebSocketMessage`, `WebSocketClient`, `HandlerMapping`, and `WebSocketHandlerAdapter`.
3. Understand `receive()` as an inbound Flux and `send(...)` as an outbound Mono completion.
4. Compose inbound and outbound into **a single Publisher** accurately reflecting session lifecycle.
5. Build an echo handler and a bounded notification-emitting handler yourself.
6. Understand close, error, cancel, half-open connections, ping/pong, graceful shutdown, and session scope.
7. Handle bounded input/output without blocking the event loop or subscribing manually.
8. Distinguish WebSocket streams from SSE, NDJSON, and HTTP response streaming.
9. Understand handshake authentication, per-message authorization, Origin/subprotocols, and WebSocket security.
10. Write integration tests with a WebSocket client verifying messages and closure.
11. Know when a broker/pub-sub/`Sinks` is needed to multiplex multiple producers onto one safe send path.
12. Recognize pooled buffer ownership, memory/backpressure, per-connection resource leaks, and production risks.

## 2. From HTTP Handshake to WebSocket Frames

A WebSocket connection begins as an HTTP GET with Upgrade headers (e.g., HTTP/1.1):

```http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Origin: http://localhost:3000
```

`Sec-WebSocket-Key` above is a documentation example; WebSocket clients generate a random key per protocol. When accepting the handshake, the server replies:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

`Sec-WebSocket-Accept` is computed from the key per RFC 6455; never hardcode it in an application. After status **101**, regular REST-style HTTP request/response semantics upgrade into a WebSocket frame exchange session.

Logical flow:

```text
Browser / WebSocketClient
       |
       | HTTP GET + Upgrade headers
       v
Reactive HTTP server (e.g., Reactor Netty)
       |
       v
WebFlux DispatcherHandler
       |
       +--> SimpleUrlHandlerMapping: /ws/echo -> WebSocketHandler
       |
       +--> WebSocketHandlerAdapter
              |
              +--> WebSocketService / HandshakeWebSocketService
                       |
                       +--> validate handshake
                       +--> select server-specific upgrade strategy
                       +--> return 101 when valid
                       +--> create WebSocketSession
                                  |
                                  v
                             handle(session)
                                  |
                  +---------------+---------------+
                  |                               |
            receive() Flux                  send(Publisher)
                  |                               |
             inbound frames                 outbound frames
                  |                               |
                  +---------- Mono<Void> ---------+
                                completion/error/cancel
```

**Do not confuse:** One handshake can carry **many** bidirectional messages, with no per-message HTTP status code. If the application needs to report a "business error" when a client sends invalid JSON, it must define an error message schema or close code—you cannot emit a fresh HTTP 400 per message after upgrade.

### When to Use WebSocket?

- Chat, collaborative editing, multiplayer/game state, and low-latency command/reply.
- Clients both send commands and receive events without creating a new HTTP request each time.
- Bidirectional interaction or continuous pushes with frequent responses.

If only the server pushes updates to a browser, **SSE** may be simpler. If only exporting a one-way list of data, **NDJSON** can also fit better. Choose by **communication pattern**, not merely to use Reactor.

## 3. WebSocketHandler: The Core Contract

The interface in `org.springframework.web.reactive.socket.WebSocketHandler` declares:

```java
public interface WebSocketHandler {
    Mono<Void> handle(WebSocketSession session);

    // Real API also includes default getSubProtocols().
}
```

This illustrates the **API signature**, not a file to redefine.

`handle(session)` is invoked after a successful handshake. It must **return a `Mono<Void>` reflecting the entire session handling**. That Publisher completes when the session finishes or closes per policy; emits an error signal on unhandled failures; and can be cancelled on connection termination/disconnect.

### Mono<Void> Does Not Mean "Do Nothing"

- It carries no Java DTO to serialize into an HTTP JSON response.
- It carries **onSubscribe, onComplete, onError, and cancel** signals.
- The server/framework subscribes to the returned Mono; the application **must not** subscribe to a detached Mono and immediately return `Mono.empty()`.
- Returning `Mono.empty()` immediately can terminate the session prematurely before anything is read or sent.
- Returning a Mono that never completes and ignores cancellation can keep connections/resources alive needlessly.

### Never Use the Servlet WebSocket Interface in WebFlux

| Stack | Common Type | Entry Point and Lifecycle |
| --- | --- | --- |
| WebFlux reactive | `org.springframework.web.reactive.socket.WebSocketHandler` | `handle(WebSocketSession): Mono<Void>` |
| Spring Servlet WebSocket | `org.springframework.web.socket.WebSocketHandler` | Callbacks like `afterConnectionEstablished`, `handleMessage` |
| Spring messaging/STOMP | `@MessageMapping`, broker abstractions | High-level messaging protocol |
| Browser client | JavaScript `WebSocket` | `onopen`, `onmessage`, `onclose`, `onerror` |

The Servlet and WebFlux `WebSocketHandler` interfaces **share the same name but have different packages and execution models**. Never import `org.springframework.web.socket.WebSocketHandler` in this reactive example.

## 4. WebSocketSession Is the Context of One Connection

Key APIs on `org.springframework.web.reactive.socket.WebSocketSession`:

| API | Meaning |
| --- | --- |
| `getId()` | Implementation-provided session ID, useful for correlation |
| `getHandshakeInfo()` | Handshake metadata (URI, headers, principal, etc.) |
| `receive()` | `Flux<WebSocketMessage>` of incoming messages |
| `send(Publisher<WebSocketMessage>)` | Writes outbound messages; returns `Mono<Void>` upon completion |
| `textMessage(String)` | Creates an outbound text message |
| `binaryMessage(Function<DataBufferFactory,DataBuffer>)` | Creates a binary message |
| `pingMessage(...)` / `pongMessage(...)` | Creates control messages if needed |
| `close(CloseStatus)` | Requests closing the session with a close status |
| `closeStatus()` | `Mono<CloseStatus>` reflecting close outcome |
| `isOpen()` | Point-in-time check; never rely on it to synchronize lifecycle |
| `bufferFactory()` | Factory creating DataBuffers for outbound messages |

`WebSocketSession` **lives only for a single connection**. Never store it in a mutable field on a singleton handler to share across clients. For multi-user notifications, session registries/caches need lifecycle cleanup, bounded queues, and concurrency policies—not an unbounded `HashMap<String,Session>`.

### HandshakeInfo Is Not a Regular HTTP Request

Handshake metadata exposes `URI`, headers, and principal. After upgrading, the handler does not receive a new HTTP request each time the client sends text. To carry per-message metadata, **define an explicit message envelope** or subprotocol. Never treat a raw query parameter `?user=alice` as proof of authenticated identity.

## 5. Inbound Stream: Flux<WebSocketMessage> receive()

`session.receive()` returns `Flux<WebSocketMessage>`. Each message has type TEXT, BINARY, PING, or PONG (exposure/handling of control frames depends on server implementation/protocol); payload resides in a `DataBuffer`.

Example logging only the **message type**:

```java
Mono<Void> inbound = session.receive()
        .doOnNext(message ->
                logger.info("session {} type={}",
                        session.getId(), message.getType()))
        .then();
```

This is a **snippet** (requires `session` and a logger bean). `then()` turns the multi-message stream into `Mono<Void>`, completing when inbound completes. Never log raw payloads if they may contain credentials, PII, or secrets.

### Reading Text Immediately in a Synchronous Operator

```java
Flux<String> textInput = session.receive()
        .filter(message ->
                message.getType() == WebSocketMessage.Type.TEXT)
        .map(WebSocketMessage::getPayloadAsText);
```

Snippet assuming `session`. `getPayloadAsText()` converts text-frame bytes to `String` while the message buffer is still valid. If processing asynchronously **later** while keeping the raw `WebSocketMessage`/pooled `DataBuffer`, manage `retain`/`release` carefully (Section 13). The full echo example **extracts `String` early** instead of holding buffers across async boundaries.

### Inbound Flux Usually Ends When the Connection Closes

Do not treat every `onComplete` as business "received all N messages" if the client protocol is a live channel. It may occur due to a normal close. `onError` can signal network/decoder failures; `cancel` can arrive when the application returns/handler cancels. To stop after a `stop` command, design explicit close semantics rather than relying implicitly on "the client will close the socket after sending".

## 6. Outbound Stream: Mono<Void> send(Publisher<WebSocketMessage>)

`session.send(outboundPublisher)` accepts a publisher of outbound `WebSocketMessage`s. Once the source completes and messages are written, the returned `Mono` completes.

```java
Flux<WebSocketMessage> greeting = Flux.just(
        session.textMessage("hello"),
        session.textMessage("welcome"));

Mono<Void> result = session.send(greeting);
return result;
```

This is a **snippet** used inside `handle(session)`. If a handler only needs to emit two messages and end the session, completing `send` can also mark the end of application handling; the framework/runtime manages closure per lifecycle.

### Never Call send() Multiple Times Independently

Anti-pattern:

```java
// ANTI-PATTERN: two outbound writers competing on the same session.
session.send(streamA).subscribe();
session.send(streamB).subscribe();
return Mono.empty();
```

This spawns detached subscriptions disconnected from the handler's lifecycle/errors/cancellation. Competing writers can race or scramble message order. When emitting from multiple sources, **merge/multiplex into one `Publisher<WebSocketMessage>` and call `session.send(...)` once**, with queue bounds and ordering policies.

### Sending Text

```java
return session.send(
        Flux.just("first", "second")
                .map(session::textMessage));
```

Snippet. `WebSocketSession.textMessage` builds a WebSocket text frame with standard encoding (UTF-8). Never append `\n` delimiters unless your protocol specifies it; **WebSocket already has message boundaries**, unlike NDJSON over an HTTP stream.

## 7. Echo: Composing Inbound and Outbound in One Flow

An echo server receives text and sends it back:

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> outbound = session.receive()
            .filter(message ->
                    message.getType() == WebSocketMessage.Type.TEXT)
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> "echo:" + text)
            .map(session::textMessage);

    return session.send(outbound);
}
```

This is an **implementation snippet**; the runnable class is in Section 14. Key structure:

```text
session.receive()
    -> WebSocketMessage
    -> String
    -> transform
    -> session.textMessage(...)
    -> session.send(outgoing)
    -> Mono<Void>
```

No `block()` or manual `subscribe()`. `session.send(outgoing)` subscribes to `outgoing`; `outgoing` subscribes to inbound. When the client closes, inbound completes/errors; `outgoing` stops accordingly, `send` finishes/cancels, and the framework cleans up the session.

### Why Is This Approach Simple and Safe?

- One inbound subscription.
- One outbound writer.
- Each text message is answered once.
- No mutable per-session fields retained.
- Uses reactive operators and honors cancellation.
- No need for `Sinks.Many`/shared queues without broadcasting.

### Echo Is Not Production Chat

Echo lacks auth, rooms, fan-out, durable messages, replay, unread counts, delivery acknowledgements, and multi-node coordination. Simply copying an echo handler and stashing every session in a global map solves neither authorization, memory limits, cleanup, nor horizontal scaling.

## 8. When Inbound and Outbound Are Independent

A notification system may simultaneously **receive commands** and **push events from an external source**. The two streams need not have a 1-to-1 "one input → one output" relationship.

Conceptual example:

```java
Mono<Void> inbound = session.receive()
        .filter(message ->
                message.getType() == WebSocketMessage.Type.TEXT)
        .map(WebSocketMessage::getPayloadAsText)
        .concatMap(commandService::handle)
        .then();

Flux<WebSocketMessage> outboundMessages =
        eventService.streamForUser(userId)
                .map(session::textMessage);

Mono<Void> outbound = session.send(outboundMessages);

return inbound.and(outbound);
```

This is a **snippet depending** on assumed `session`, `commandService`, `eventService`, and `userId`. `inbound.and(outbound)` coordinates completion of both sides in Reactor, matching Spring documentation examples. **Do not equate this with every closure need**: if outbound is infinite while inbound completes on client disconnect, verify the chosen composition cancels outbound promptly; in some apps, `takeUntilOther(inbound)` or a clearer termination signal fits better.

### Different Termination Strategies

1. **Echo dependent flow:** outbound depends directly on inbound and stops when inbound ends; `return session.send(session.receive().map(...))`.
2. **Server finite push:** emit only N messages and stop, `return session.send(Flux.take(N)...)`.
3. **Long-lived push:** outbound may be infinite, requiring connection completion/cancellation wiring and business shutdown policies.
4. **'stop' command:** receive an app command, send an acknowledgement, then close with an appropriate status; client and server agree on semantics.
5. **Server shutdown:** gracefully close active sessions, wait up to a deadline, cancel remaining subscriptions.
6. **Fatal protocol error:** close with the right close code—never try sending a fresh HTTP 500 post-upgrade.

**A WebSocket connection is full-duplex**, yet *orchestrating* the two flows is an application decision; `send` does not read inbound for you.

## 9. Reactive Completion, Error, and Cancellation

The `Mono<Void>` returned by `handle()` defines lifecycle termination. Table:

| Signal | Meaning | Design Action |
| --- | --- | --- |
| `onComplete` | Handling flow finished normally | Clean up state, counters, subscriptions |
| `onError` | Unhandled failure | Log safely; close properly; never fake a fresh JSON HTTP response |
| `CANCEL` | Subscription cancelled by disconnect/shutdown/other logic | Clean up upstream resources and timers |
| Close frame | WebSocket protocol close signal | Record close code/reason when available |
| Socket reset without close frame | Abnormal network failure | Never assume a clean close event always arrives |
| Timeout/idle expiry | Inactivity or expired policy | Configure ping/heartbeat and server/proxy idle settings |

Do not write only:

```java
return session.receive()
        .doOnComplete(() -> metrics.connectedMinusOne())
        .then();
```

If the connection cancels or errors, `doOnComplete` may never run and active connection counts leak. Use `doFinally` on the **single lifecycle-owning publisher**, counting accurately once and avoiding double-decrements:

```java
return session.send(outgoing)
        .doOnSubscribe(sub -> active.increment())
        .doFinally(signal -> active.decrement());
```

This is a **snippet** with application-provided `outgoing` and `active`. Guard counting logic against non-execution or re-subscription on the same session; `doFinally` is right for COMPLETE/ERROR/CANCEL handling, though not always for synchronously closing every resource.

### Never Rely on isOpen() to Drive Lifecycle

`session.isOpen()` is only a point-in-time snapshot that races with network close. In reactive code, rely on completion/error/cancellation and `closeStatus()` as appropriate. Never write `while(session.isOpen())` loops with `Thread.sleep` to poll a WebSocket.

## 10. CloseStatus and Closing Rules

WebSocket RFC 6455 defines a **close frame** with a status code and optional reason. Spring WebFlux provides `CloseStatus` and `session.close(...)`.

Example:

```java
return session.close(CloseStatus.NORMAL);
```

Snippet inside a handler. `CloseStatus.NORMAL` represents normal closure (1000). Common codes:

| Code | Standard Meaning | Notes |
| --- | --- | --- |
| 1000 | Normal Closure | Normal session termination |
| 1001 | Going Away | Endpoint leaving / server shutdown |
| 1002 | Protocol Error | WebSocket protocol violation |
| 1003 | Unsupported Data | Unsupported data type |
| 1008 | Policy Violation | Policy violated, e.g., authorization policy |
| 1009 | Message Too Big | Frame/message exceeds server limit |
| 1011 | Unexpected Condition | Unexpected server error |
| 1006 | Abnormal Closure (reserved, never sent on wire) | Client observes when no valid close frame arrives |
| 1015 | TLS failure (reserved, never sent on wire) | Never send as an application close code |

Never send 1006/1015 in a close frame. `CloseStatus` constants cover common cases, though verify your Javadoc version before picking constants. Custom statuses must not violate RFC 6455 rules.

### Where Does Closing Make Sense?

- When handling a leave-room command, send a final acknowledgement then `.then(session.close(...))`.
- On severe invalid input or oversized payloads, close with 1008/1009 depending on which layer caught it.
- During server deploy/shutdown, send 1001 when possible and cancel after a deadline.
- If the client already vanished, close frame delivery is not guaranteed.
- Reasons have a bounded UTF-8 byte length and must never contain secrets/stack traces/PII.

**WebSocket close codes are not HTTP statuses.** After HTTP 101, codes 1000/1008/1011 travel inside WebSocket close frames—not as a new `200/403/500` HTTP response.

## 11. Backpressure in WebSocket: What Is Guaranteed?

`session.receive()` is a Flux, and `session.send(Publisher)` takes a Reactive Streams source. This enables demand/cancellation composition, yet does not turn TCP/browsers/WebSocket into an infinitely smart queue.

- Server-side reactive writes can slow down with I/O demand and network conditions.
- Browser `WebSocket.send(...)` has no Reactive Streams `request(n)` API; rapid sends grow `bufferedAmount` on the client.
- A message broker may push faster than socket writes; unbounded queues grow RAM.
- `Sinks.Many` can return `FAIL_OVERFLOW` when queue limits fill; handle it instead of ignoring.
- Unbounded `Flux.onBackpressureBuffer()` can cause OOM.
- One slow client must never force the whole cluster or room to retain events indefinitely.
- `flatMap` may reorder results; use `concatMap` when command/reply ordering must be preserved.

### Always Bound the Pipeline

For a chat room:
- Enforce per-connection messages/sec quotas and max payload bytes.
- Keep per-session outbound queues **bounded**.
- Define full-queue policy: drop stale presence updates, coalesce status, disconnect slow clients, or signal backpressure.
- Never silently drop durable business messages.
- In pub/sub, separate durable delivery/ACK/replay from best-effort live notifications.
- Use transport-level ping/pong and idle eviction rather than keeping "ghost" sessions forever.

**Reactive APIs do not make every downstream non-blocking**: calling synchronous JDBC, filesystem, or HTTP clients inside `map` still blocks the event loop.

## 12. Never Block the WebFlux Event Loop

Anti-pattern:

```java
// ANTI-PATTERN: blocking database call on the event loop.
return session.send(session.receive()
        .map(message -> {
            String text = message.getPayloadAsText();
            return session.textMessage(jdbcService.lookup(text));
        }));
```

`jdbcService.lookup` is assumed and may block. When thousands of connections receive messages concurrently, blocking calls on the event loop cause server-wide latency.

If forced to call a blocking API temporarily:

```java
Flux<WebSocketMessage> outbound = session.receive()
        .filter(m -> m.getType() == WebSocketMessage.Type.TEXT)
        .map(WebSocketMessage::getPayloadAsText)
        .concatMap(text ->
                Mono.fromCallable(() -> jdbcService.lookup(text))
                    .subscribeOn(Schedulers.boundedElastic()))
        .map(session::textMessage);

return session.send(outbound);
```

This snippet requires `jdbcService` and `Schedulers` imported. It **offloads blocking work to bounded workers**, without making JDBC non-blocking. Configure timeouts, concurrency limits, and DB pools; prefer reactive drivers/clients when practically beneficial. On cancellation after a blocking task starts, JDBC side effects are not guaranteed to roll back automatically.

## 13. DataBuffer Ownership, Binary Messages, and Ping/Pong

### 13.1. WebSocketMessage Carries a DataBuffer Payload

`WebSocketMessage` has a type and payload. On Reactor Netty, some buffers are **pooled and reference-counted**. Reading text immediately in a synchronous `map` converts early to `String` and avoids holding buffers long.

Anti-pattern:

```java
// DANGEROUS if message/buffer is released before callback.
return session.receive()
        .delayElements(Duration.ofSeconds(1))
        .map(WebSocketMessage::getPayloadAsText)
        .then();
```

If an async boundary retains the raw message, the buffer may no longer be valid when read later. When you truly must retain buffers, apply `retain`/`release` with strict ownership per Spring guidelines, preferring higher-level abstractions. Never retain and forget to release—pooled direct memory will leak.

### 13.2. Binary Frames Differ from Text Frames

`session.binaryMessage(factory -> factory.wrap(byteArray))` creates a binary `WebSocketMessage`. For large binary payloads, avoid allocating huge `byte[]` without a max size. When receiving binary:
- Define compression/frame fragmentation policies.
- Validate content length, magic bytes/schema/CRC if needed.
- Never interpret binary data as UTF-8 text.
- Cap max frame/message bytes at the server WebSocket upgrade strategy, proxy, and application.

### 13.3. Ping/Pong and Heartbeats

Standard WebSocket has PING/PONG and CLOSE control frames. Heartbeats help:
- Detect half-open sockets.
- Keep connections alive through intermediary idle timeouts.
- Measure round-trip latency where protocols/implementations permit.

However, **do not assume every Ping frame appears in `session.receive()` as an application message**: server runtimes may handle Ping/Pong at the transport layer and reply with Pong automatically. Check your Netty/Jetty/Tomcat strategy. When browser clients do not expose Ping/Pong APIs, use **application-level heartbeats** via JSON/text messages with `ping`/`pong` types (noting that is a custom protocol, not RFC control frames).

## 14. Runnable Maven Project: Echo + Ticks WebSocket Endpoints

The project demonstrates three features:

1. `/ws/echo`: client sends two text messages and server echoes them; inbound drives outbound.
2. `/ws/ticks`: server emits exactly three periodic messages without requiring input messages.
3. `/api/status`: standard REST JSON endpoint, showing WebSocket and REST coexisting in one WebFlux application.

Both WebSocket handlers are registered via `SimpleUrlHandlerMapping`. In standard Boot WebFlux, the framework auto-configures `WebSocketHandlerAdapter`, so no second adapter bean is needed.

### 14.1. Project Structure

```text
webflux-websocket-demo/
├── pom.xml
└── src/
    ├── main/java/example/ws/
    │   ├── WebSocketDemoApplication.java
    │   ├── EchoSocketHandler.java
    │   ├── TickSocketHandler.java
    │   ├── WebSocketRouting.java
    │   └── StatusController.java
    └── test/java/example/ws/
        └── WebSocketIntegrationTest.java
```

### 14.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-websocket-demo</artifactId>
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

You do not need `spring-boot-starter-websocket` (for the Servlet MVC stack) in this WebFlux example, and do not add `spring-boot-starter-web` so Boot does not prefer MVC when both are present.

### 14.3. Main Class

**`src/main/java/example/ws/WebSocketDemoApplication.java`**

```java
package example.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSocketDemoApplication.class, args);
    }
}
```

### 14.4. Reactive Echo Handler

**`src/main/java/example/ws/EchoSocketHandler.java`**

```java
package example.ws;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {

        Flux<WebSocketMessage> outbound = session.receive()
                .filter(message ->
                        message.getType()
                                == WebSocketMessage.Type.TEXT)
                // Read immediately while DataBuffer is still valid.
                .map(WebSocketMessage::getPayloadAsText)
                .map(text -> text.length() > 256
                        ? "error:too-long"
                        : "echo:" + text)
                .map(session::textMessage);

        return session.send(outbound);
    }
}
```

**Key points:** Only **one** `receive()` and **one** `send(outbound)`, joined in a single reactive pipeline. No manual `subscribe()`, no caching `WebSocketMessage`s, no blocking calls. The server keeps the connection active while the client sends text and closes when the lifecycle ends.

The demo limits **256 Java UTF-16 code units** for simplicity, **not** RFC 6455 byte limits. Production needs server max message bytes, encoding/length checks, and a close policy on violations. Replying with `error:too-long` as text is just demo behavior, not a standard WebSocket protocol error.

Non-text messages are filtered out rather than echoed; production protocols should explicitly define binary/control handling and unsupported close statuses instead of silently dropping message types clients might expect feedback on.

### 14.5. Periodic Outbound Handler

**`src/main/java/example/ws/TickSocketHandler.java`**

```java
package example.ws;

import java.time.Duration;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class TickSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> ticks =
                Flux.interval(Duration.ofMillis(60))
                    .take(3)
                    .map(i -> session.textMessage(
                            "tick-" + (i + 1)));

        return session.send(ticks);
    }
}
```

`Flux.interval` emits ticks on a Reactor scheduler, **without `Thread.sleep` or dedicating a sleeping thread per socket**. `take(3)` guarantees finite output; after three messages, the source completes and `send` finishes. Response/connection lifecycle is handled by the framework; do not expect ticks to arrive at exactly 60/120/180 ms due to scheduling/network jitter.

### 14.6. WebSocket Route Mapping

**`src/main/java/example/ws/WebSocketRouting.java`**

```java
package example.ws;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration
public class WebSocketRouting {

    @Bean
    HandlerMapping webSocketMapping(
            EchoSocketHandler echo,
            TickSocketHandler ticks) {

        return new SimpleUrlHandlerMapping(
                Map.of("/ws/echo", echo,
                       "/ws/ticks", ticks),
                -1);
    }
}
```

**Reading the configuration:** `SimpleUrlHandlerMapping` maps URLs to `WebSocketHandler` instances. Order `-1` generally gives this mapping priority ahead of annotated controller mappings in the same `DispatcherHandler`. In a standard Boot WebFlux app with default Java config, `WebSocketHandlerAdapter` is already registered; **do not create a duplicate `WebSocketHandlerAdapter` bean just because you don't see that class in source**.

In apps with many custom mappings, avoid overlapping `/ws/**` with annotated controllers or static fallbacks. Check mapping ordering, proper HTTP handshakes, and startup logs for collisions.

### 14.7. REST Status Endpoint Sharing the Application

**`src/main/java/example/ws/StatusController.java`**

```java
package example.ws;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/api/status")
    public Map<String, String> status() {
        return Map.of("state", "ready");
    }
}
```

Though unrelated to WebSocket sessions directly, it illustrates **REST and WebSocket sharing WebFlux's `DispatcherHandler`**. On `/ws/echo`, a plain HTTP request without `Upgrade` does not turn into a JSON REST call: the handshake will be rejected.

## 15. Running the Project and Testing with a WebSocket Client

From the `webflux-websocket-demo` directory with Java 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

Run both commands sequentially. Once Boot listens on default port 8080:

### Test the REST Endpoint

```bash
curl -i 'http://localhost:8080/api/status'
```

Expected body:

```json
{"state":"ready"}
```

### Why Doesn't curl GET Normally Test WebSocket?

`curl -i http://localhost:8080/ws/echo` does not send full WebSocket handshake/Upgrade headers and does not speak the WebSocket frame protocol like a WebSocket client. It typically receives HTTP 4xx instead of 101. Use a browser WebSocket API, `websocat`, `wscat`, or Spring `WebSocketClient`.

### CLI with websocat

If `websocat` is installed:

```bash
websocat ws://localhost:8080/ws/echo
```

Type:

```text
hello-world
reactor
```

The client will observe the matching echo messages:

```text
echo:hello-world
echo:reactor
```

This shows expected message content, not a claim that every terminal client prints prompts/local echo identically across OSes. Press Ctrl+C or close the client to terminate the connection.

### CLI Periodic Ticks

```bash
websocat ws://localhost:8080/ws/ticks
```

The server is expected to emit three messages:

```text
tick-1
tick-2
tick-3
```

After the outbound source completes, the session may be closed by the framework; clients must handle close events. No `tick-4` arrives because `take(3)` bounds the source.

## 16. Browser Client: Listening for Messages and Close

Example on an HTML page served from a server-permitted origin in a WebSocket-capable browser:

```javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.addEventListener("open", () => {
  console.log("socket open");
  socket.send("hello");
  socket.send("Spring WebFlux");
});

socket.addEventListener("message", event => {
  console.log("received:", event.data);
});

socket.addEventListener("close", event => {
  console.log("closed:", event.code, event.reason);
});

socket.addEventListener("error", () => {
  console.error("WebSocket transport error");
});
```

On success, the browser console may print:

```text
socket open
received: echo:hello
received: echo:Spring WebFlux
```

Since the client does not close explicitly, the echo server keeps the session open until the browser/tab/network closes. In production, close sockets on component unmount/page close and define reconnect/heartbeat policies.

**HTTPS pages:** from an `https://` page, use secure WebSocket `wss://` to avoid mixed-content failures and send traffic over TLS. The browser generates Upgrade/handshake headers automatically; never hand-code `Sec-WebSocket-Key`.

### Watch Out for bufferedAmount

Browser `socket.send(...)` queues outbound bytes in a buffer; `socket.bufferedAmount` reports how many bytes are currently queued. If a producer emits too fast, avoid sending unboundedly:

```javascript
if (socket.readyState === WebSocket.OPEN &&
    socket.bufferedAmount < 64 * 1024) {
  socket.send("presence:update");
}
```

This is a **best-effort policy** example for droppable/coalesceable messages—never use it in a way that drops durable business commands. This browser API does not expose full Reactive Streams backpressure; applications must design ACKs/rate limits when messages are critical.

## 17. Integration Tests: Handshake, Echo, Ticks, and REST

`WebTestClient` is great for REST, whereas WebSocket frames require a **WebSocket client**. The tests below boot Spring Boot on a random port and connect with `ReactorNettyWebSocketClient`.

**`src/test/java/example/ws/WebSocketIntegrationTest.java`**

```java
package example.ws;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketIntegrationTest {

    @LocalServerPort
    int port;

    private URI ws(String path) {
        return URI.create(
                "ws://localhost:" + port + path);
    }

    @Test
    void echoRepliesForTwoTextMessages() {
        ReactorNettyWebSocketClient client =
                new ReactorNettyWebSocketClient();
        AtomicReference<List<String>> replies =
                new AtomicReference<>();

        client.execute(ws("/ws/echo"), session -> {
            Mono<Void> sending = session.send(
                    Flux.just("hello", "reactor")
                            .map(session::textMessage));

            Mono<Void> receiving = session.receive()
                    .map(WebSocketMessage::getPayloadAsText)
                    .take(2)
                    .collectList()
                    .doOnNext(replies::set)
                    .then();

            return Mono.when(sending, receiving)
                    .then(session.close());
        }).block(Duration.ofSeconds(5));

        assertEquals(
                List.of("echo:hello", "echo:reactor"),
                replies.get());
    }

    @Test
    void periodicHandlerEmitsExactlyThreeTicks() {
        ReactorNettyWebSocketClient client =
                new ReactorNettyWebSocketClient();
        AtomicReference<List<String>> ticks =
                new AtomicReference<>();

        client.execute(ws("/ws/ticks"), session ->
                session.receive()
                        .map(WebSocketMessage::getPayloadAsText)
                        .take(3)
                        .collectList()
                        .doOnNext(ticks::set)
                        .then())
              .block(Duration.ofSeconds(5));

        assertEquals(
                List.of("tick-1", "tick-2", "tick-3"),
                ticks.get());
    }

    @Test
    void ordinaryRestRequestStillWorks() {
        WebTestClient http = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        http.get().uri("/api/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("ready");
    }

    @Test
    void plainHttpGetCannotReplaceWebSocketHandshake() {
        WebTestClient http = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        http.get().uri("/ws/echo")
                .exchange()
                .expectStatus().is4xxClientError();
    }
}
```

The suite has **4 methods**. Two test real WebSocket frames; one confirms REST/JSON on the same server; one confirms plain GET is not equivalent to a handshake. `block(Duration.ofSeconds(5))` runs **only on the JUnit test thread**, never in WebFlux event-loop server code. In production apps, never call `block()` inside handlers.

**Explaining `Mono.when(sending, receiving)`:** it subscribes concurrently to the client's send stream and reply-receive stream, completing once both finish. Then the client explicitly sends close. Using `sending.then(receiving)` instead—subscribing to receive only after send finishes—can occasionally depend on buffering/timing; concurrent composition makes the lifecycle clearer.

**Do not hardcode exact timing:** ticks may be delayed by schedulers/network; tests assert ordering/content rather than asserting each tick arrives at exactly 60 ms.

**Not a benchmark:** four tests do not measure thousands of concurrent sockets, proxy upgrades, TLS, idle timeouts, memory leaks, backpressure, or message delivery guarantees. This is a runnable project verified by static API review; **Maven was not executed during this Knowledge authoring session on Google Sheets**.

### If a WebSocket Test Times Out

Check:
- The app actually runs WebFlux, not Spring MVC due to dependency selection.
- `/ws/echo` and `/ws/ticks` are registered by `SimpleUrlHandlerMapping`.
- `WebSocketHandlerAdapter` is provided by WebFlux configuration without conflicting custom WebFlux configs.
- Any reverse proxy/ingress forwards `Upgrade` and `Connection` headers.
- The server bound `@LocalServerPort` before the Reactor Netty client connected.
- The test client actually subscribes to `receive()` and the send publisher.
- The handler returns a lifecycle-scoped publisher instead of completing `Mono.empty()` too early.

## 18. Multiple Outbound Publishers: Safe Multiplexing Design

A chat connection may need to emit:
- Direct handler replies.
- Room messages.
- Presence notifications.
- Heartbeats/periodic status.

**Do not launch four independent `session.send(...)` calls.** A general pattern merges sources into one `Flux<WebSocketMessage>`:

```java
Flux<String> replies = ...;
Flux<String> roomEvents = ...;
Flux<String> presence = ...;

Flux<WebSocketMessage> output = Flux.merge(
        replies, roomEvents, presence)
        .map(session::textMessage);

return session.send(output);
```

This is an **architectural snippet** assuming publishers from application services. `Flux.merge` can interleave events and does not guarantee global ordering across sources. If ordering matters, add sequence numbers, partition keys, or serialize commands through a queue.

### Avoid Subscribing to Raw receive() Twice

Wrong:

```java
Mono<Void> a = session.receive().doOnNext(this::audit).then();
Mono<Void> b = session.send(session.receive().map(this::reply));
return Mono.when(a, b);
```

This is an anti-pattern; when the inbound source is a one-shot/live stream, two subscriptions can compete or double-consume. Keep **one inbound flow** and intentionally share/multicast or route commands into a controlled sink/processor.

### Sinks.Many: When Is It Appropriate?

Reactor's `Sinks.Many<T>` can bridge imperative broker/callback events to a reactive outbound publisher. Choose the right mode:
- `multicast()` for currently online subscribers.
- `replay()` when retaining history, **with bounded retention**.
- `unicast()` with a single subscriber when appropriate per session.
- Overflow strategies/quotas and handling `tryEmitNext` failures.

Never call `sink.tryEmitNext(event)` and assume it always succeeds. If a consumer is too slow, apply a business-approved policy. Close sinks when sessions end, clean up subscriptions/room memberships, and avoid holding leaking references.

## 19. Auth, Origin, CSRF, and Per-Message Authorization

### Authentication at Handshake

The handshake is still an HTTP request. Spring Security WebFlux can enforce authentication in the `WebFilter`/`SecurityWebFilterChain` layer and attach a `Principal`/metadata to the WebSocket handshake/session. However, **not every header/token works identically to HTTP fetch**:

- The browser `WebSocket` constructor **does not allow setting arbitrary `Authorization` headers** like a Java HTTP client.
- Cookies may be sent automatically per browser policy; account for `SameSite`, `Secure` flags, and session fixation.
- Query-string tokens risk leaking into server/proxy logs/history, so never put long-lived secrets in `?token=...`.
- If using subprotocols to carry auth metadata, design the protocol explicitly rather than abusing negotiation headers for secrets.

### Origin and Cross-Site WebSocket Hijacking

WebSocket handshakes include `Origin` in browsers. **WebSocket CORS is not identical to `fetch()` policies**: browsers do not enforce the same REST preflight/response-read checks. The server must validate `Origin` against an allowlist to mitigate cross-site WebSocket hijacking (especially with cookie/session auth).

Spring WebFlux can configure CORS/allowed origins on WebSocket handler mappings—for instance via `CorsConfigurationSource` on handlers or `SimpleUrlHandlerMapping` URL CORS config per Spring docs. **Never** allow all origins in production just to make a browser demo work. Test real browsers, reverse proxies, and WebSocket handshake responses when adding origin policies.

### Per-Message Authorization

A user allowed to **open a connection** is not automatically authorized to:
- Join a specific room.
- Subscribe to someone else's private event stream.
- Execute `deleteDocument`/`transferFunds` messages.
- Send at high rates or huge payloads.

Message envelope design:

```json
{"type":"join","roomId":"room-17","requestId":"r-42"}
```

This is solely an **application** JSON protocol, not a WebSocket-mandated payload. The server decodes the schema, validates input, checks the authenticated principal, and **enforces ACLs per action**; never trust a client-sent `userId` to impersonate someone. In multi-tenant systems, route messages by the trusted tenant identity from authentication, not just URLs/bodies.

### CSRF and WebSocket

When browsers send session cookies, cross-site handshake/command risks must be mitigated via Origin validation, auth/session policies, and message-level authorization. Do not assume an HTTP CSRF filter checks every post-upgrade WebSocket message. STOMP/Spring Security messaging has its own policies; this lesson uses low-level `WebSocketHandler`, so **you must define protocol security yourself**.

## 20. WebSocket vs. HTTP Streaming, SSE, and NDJSON

| Feature | WebSocket | SSE | NDJSON over HTTP |
| --- | --- | --- | --- |
| Protocol | Upgrade to WS (typically HTTP 101 on HTTP/1.1) | HTTP response streaming | HTTP response/request streaming |
| Primary direction | **Bidirectional** | Server → client | Typically one-way per HTTP exchange |
| Framing | Message frames (text/binary/control) | `data:`/`event:`/blank line | One JSON record per line |
| Browser API | `WebSocket` | `EventSource` | `fetch` + `ReadableStream`/parser |
| Reconnect | App-managed | `EventSource` auto-reconnects | App-managed |
| Event IDs | App protocol | `id`/`Last-Event-ID` | App protocol |
| Error status after connect | Message/close code | Streaming HTTP error constraints | Streaming HTTP error constraints |
| Multiple client → server commands | Yes on same connection | Needs separate HTTP requests | POST streaming works, not full-duplex messaging like WS |
| Binary payloads | Yes | Usually text/data framing | Raw HTTP stream possible with right media type |
| Proxy support | Requires Upgrade/WS support | HTTP streaming, may buffer | HTTP streaming, may buffer |
| Operational complexity | Connections/rooms/security/retry | Heartbeats/replay/idle | Parsing/partial errors/resume |

**Never pick WebSocket merely because you return a Flux.** For a one-way download of a 100,000-record report, NDJSON/HTTP files are simpler. For server-to-browser dashboard updates, SSE is often less complex. When collaboration with bidirectional commands is needed, WebSocket shines.

## 21. Post-Handshake Error Handling Rules

After HTTP 101 succeeds:

1. **There is no longer a per-message HTTP 400/500 response**.
2. To signal business errors, send a protocol message such as:
   `{"type":"error","code":"invalid_command","requestId":"r-42"}`.
3. If a client violates policy/protocol severely, close with the appropriate close status.
4. On unexpected server errors, avoid leaking exception messages/stack traces.
5. If a sequence streams partially before dropping, clients must know **up to which message sequence was received**.
6. Durable commands need `requestId`/idempotency/ACKs and retry policies.
7. Ensure errors containing private room data are never broadcast to unauthorized users.
8. Logs/metrics should include session ID, trace ID, and auth/tenant per policy without dumping raw payloads.

Example reply envelope:

```json
{"type":"ack","requestId":"r-42","sequence":182,"status":"accepted"}
```

An ACK protocol must define whether `accepted` means queued or committed to durable storage. Never promise exactly-once merely because messages share one TCP connection; an ACK can be lost if the network drops right after a side effect, causing client retries to duplicate work.

## 22. Per-Session State, Rooms, and Horizontal Scaling

Every connection has its own session. In one application process, you may hold thousands of sessions, yet never stash them in a static `List<WebSocketSession>` and broadcast regardless of user/tenant.

Production concerns:

- **Identity:** map session → authenticated user/tenant/principal.
- **Rooms:** who may join, subscribe, leave; validate ACLs.
- **Presence:** join/leave may repeat on reconnect; use TTLs/dedup.
- **Memory:** bounded outbound queues, remove disconnected sessions.
- **Ordering:** sequence per room/user, order across producers/instances.
- **Horizontal scale:** message broker/pub-sub to fan out across nodes; a process-local `Map` sees only that node's sessions.
- **Sticky sessions:** a WebSocket TCP connection stays on one node for its lifetime, yet reconnects can hit another node.
- **Replay:** broker/event log/DB when messages must not be lost.
- **Security:** never deliver private messages solely based on a client-supplied `roomId`.
- **Observability:** active connections, handshakes, close code distribution, messages/sec, queue depth, late cancellations.

When scaling across multiple nodes, a local `Sinks.Many` does not synchronize subscriptions or history across the cluster. Use a shared broker or distributed architecture. For durable chat, persistence and ACK protocols matter more than merely "pushing a WebSocket frame".

## 23. Health, Idle Timeouts, Shutdown, and Reconnects

### Idle Connections

When client/server stay quiet for long periods:
- Load balancers/proxies may close idle connections.
- Half-open sockets are not necessarily detected immediately.
- TCP keepalive is usually insufficient for application heartbeat SLAs.

Use transport ping/pong or application heartbeats and timeouts (e.g., close if no pong/heartbeat arrives after N intervals). Avoid overly aggressive heartbeats across tens of thousands of clients that create unnecessary overhead.

### Graceful Shutdown

During rolling deploys:
1. Stop accepting new handshakes.
2. Send going-away/drain notices if supported by the app.
3. Close existing sessions within a deadline.
4. Clean up subscriptions/timers/queues/room memberships.
5. Clients retry/reconnect with backoff + jitter.
6. Resume subscriptions/replay from cursors if needed.

### Browser Reconnects

Never reconnect immediately in a tight infinite loop when the server errors. Use exponential backoff + jitter, cap max attempts, and distinguish policy-rejection close codes from network failures. On user logout, **stop reconnecting** and clear sensitive state. If the server requires re-authentication, never endlessly reuse expired tokens.

## 24. Common Pitfalls

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| WebSocket 404 | Unregistered `SimpleUrlHandlerMapping` or wrong path | Register bean with exact URL, test handshake |
| Handshake fails to upgrade | Missing Upgrade headers, proxy doesn't pass WebSocket | Use WebSocket client and configure proxy |
| Wrong `WebSocketHandler` imported | Using Servlet `org.springframework.web.socket` in WebFlux | Use `org.springframework.web.reactive.socket` |
| `handle()` returns immediately, socket closes early | Returning `Mono.empty()` with detached work | Return lifecycle-owning `Mono<Void>` |
| Client sends but gets no reply | Outbound `session.send` not returned/subscribed | Chain receive→send into one pipeline |
| Two replies arrive out of order | `flatMap` async out-of-order completion | `concatMap`/sequence IDs |
| Socket double write | Multiple `session.send(...).subscribe()` calls | One outbound publisher / one `send` |
| Connection hangs forever | Infinite outbound not tied to cancellation | Compose inbound close/termination |
| Memory leak on client disconnect | Registry/sink/timer not removed | `doFinally` cleanup on owner publisher |
| Duplicate processing | Subscribing to `receive()` in multiple places | One receive flow, proper multicast |
| `DataBuffer` error after async delay | Pooled buffer released early | Copy String/bytes early or retain/release properly |
| Direct memory leak | Retained buffer without matching release | `DataBufferUtils` and ownership policy |
| Text message ignored | Filter accepts TEXT only while client sends binary | Define protocol/types and explicit close/error |
| Server sends 1006 | Using reserved close code | Send only valid RFC 6455 codes |
| Post-upgrade HTTP error doesn't reach client | WebSocket is not HTTP responses | Error message or close status |
| Browser handshake blocked | Origin allowlist/proxy/security policy | Configure and test allowed origins |
| Browser cannot set `Authorization` | Native `WebSocket` constructor restricts headers | Use suitable auth flow, avoid naive query tokens |
| User accesses unauthorized room | Checking auth only at handshake | Authorize per room/action |
| Slow client grows queues | Unbounded `Sinks`/buffers | Bounded queues and overload policies |
| Event-loop lag | Blocking JDBC/API inside handler | Reactive driver or bounded offload |
| Ping absent from `receive()` | Runtime auto-handles control frames | Check implementation; use app heartbeats if needed |
| Client reconnect duplicates commands | Missing `requestId`/idempotency | Dedup/ACK/persistence |
| WebSocket over HTTPS fails | Using `ws://` on secure page | `wss://` and TLS |
| `WebTestClient` GET fails to upgrade | HTTP client doesn't speak WS frames | `ReactorNettyWebSocketClient`/`WebSocketClient` |
| Multi-node chat misses notifications | Process-local sessions aren't shared | Broker/event bus + durable offsets |
| `Origin: *` with cookie auth | Cross-site WS hijacking | Strict allowlist and auth/ACL |
| Connection leaks on deploy | No graceful drain | Close with deadline, cleanup, client reconnect |

## 25. Production Review Checklist

- [ ] Uses `spring-boot-starter-webflux` with proper reactive socket imports.
- [ ] `WebSocketHandlerAdapter` and WebSocket routing discovered by WebFlux config.
- [ ] Each handler returns **one** lifecycle-owning `Mono<Void>`.
- [ ] `receive()` is never accidentally subscribed multiple times.
- [ ] One outbound `send` Publisher per connection with controlled multiplexing.
- [ ] No `block()` or detached `subscribe()` on the Netty event loop.
- [ ] Never hold pooled `WebSocketMessage` across async boundaries without `retain`/`release`.
- [ ] Message type/schema validation and max bytes/frame/message enforced.
- [ ] Handshake authentication and Origin allowlists configured properly.
- [ ] Per-command/room/tenant authorization enforced.
- [ ] No long-lived secrets in URL query strings or logs.
- [ ] Session-scoped resources and room memberships cleaned up on complete/error/cancel.
- [ ] Clear rules for close codes, heartbeats, and idle detection.
- [ ] Per-client outbound queues bounded with backpressure/overload policies.
- [ ] No attempts to send fresh HTTP responses after 101 upgrade.
- [ ] Retries/reconnects use backoff, idempotency, and replay policies where needed.
- [ ] App supports graceful shutdown/draining with many long-lived connections.
- [ ] Metrics track active sockets, close codes, dropped messages, queue sizes, and latency.
- [ ] Integration tests use real `WebSocketClient`, not solely `MockMvc`/`WebTestClient` HTTP.
- [ ] Tested through production-like reverse proxies, TLS, load balancers, and idle timeouts.

## 26. Hands-On Exercises

### Exercise 1 — Application-Layer Ping-Pong

Add a `"ping"` text command to the echo protocol returning `"pong"`. Explain why this **differs** from WebSocket PING/PONG control frames. Test with `WebSocketClient` by sending `ping` and asserting `pong`.

### Exercise 2 — Close with Acknowledgement

When the client sends `"bye"`:
1. Send text acknowledgement `"goodbye"`.
2. After the acknowledgement is written, close with `CloseStatus.NORMAL`.
3. Do not send further messages once the session closes.
4. Test that closing causes no double sends and inbound cancels/cleans up.

### Exercise 3 — Broadcast Room

Design a room with 3 sessions:
- Only authenticated users may join.
- Attach a sequence number to every room event.
- One inbound receive flow per session.
- One outbound send flow per session.
- Bounded queue and overflow policy when one user reads slowly.
- Proper cleanup on cancel/error/normal close.
- When scaling to 2 nodes, describe why pub/sub or a broker is required.

### Exercise 4 — Slow Consumer

Simulate a client reading outbound slowly:
- Measure queue depth, active sessions, and send completion latency.
- Test overload policies (drop presence updates vs. disconnect).
- Never drop durable payment/chat commands without ACKs.
- Verify the difference between Reactor backpressure and browser `bufferedAmount`.

### Exercise 5 — Reverse Proxy / TLS

Connect to `wss://example.test/ws/echo` through a trusted proxy configured with Upgrade/Connection, TLS, and idle timeouts:
- Test HTTP 101 vs. handshake errors.
- Test the browser Origin allowlist.
- Observe close 1000 vs. abnormal disconnects.
- Test reconnect backoff during server rolling deploys.

## 27. Self-Check Questions

1. What parameter and return type does `WebSocketHandler.handle` take and return?
2. Which reactive types do `WebSocketSession.receive()` and `send(...)` return?
3. Why does WebSocket need an HTTP 101 handshake before sending frames?
4. Do WebSocket text messages use newline delimiters like NDJSON?
5. How does reactive `WebSocketHandler` differ from Servlet `WebSocketHandler`?
6. Why can returning `Mono.empty()` immediately close the session too early?
7. Should you call `session.send(...).subscribe()` inside a handler?
8. When outbound is `session.receive().map(...)`, what does completion depend on?
9. When inbound and outbound are independent, how must termination be composed?
10. How do you distinguish client cancellation, network errors, and normal close?
11. What advantage does `doFinally` have over `doOnComplete` for cleanup?
12. Why is `session.isOpen()` snapshot insufficient as a lifecycle loop?
13. Why should there be only one outbound writer per connection?
14. How do `flatMap` and `concatMap` differ when handling ordered replies?
15. How does `WebSocketMessage.Type.TEXT` differ from `BINARY`?
16. When is `retain`/`release` needed for a `WebSocketMessage` `DataBuffer`?
17. Can HTTP 400 be returned for a business error after upgrading to WebSocket?
18. Is code 1006 ever transmitted in a close frame?
19. Can you use `WebTestClient` HTTP GET instead of a WebSocket client to verify messages?
20. Why doesn't the browser `WebSocket` API support custom `Authorization` headers like `fetch`?
21. What does Origin validation prevent for cookie-authenticated WebSockets?
22. Is checking permissions at handshake time enough for room-specific commands?
23. Does WebSocket automatically protect against message floods, slow consumers, and memory leaks?
24. Does `Flux.interval` spawn a dedicated sleeping Java Thread per session?
25. Why doesn't `boundedElastic` make JDBC non-blocking?
26. With multiple producers, should you call `send` multiple times or merge into one outbound Flux?
27. If a chat room spans multiple server nodes, is a local `Map<sessionId,session>` enough to broadcast?
28. What advantages do SSE/NDJSON offer when clients only need one-way data?
29. When clients reconnect after disconnects, how do you prevent duplicate business commands?
30. During shutdown, which rules must server and client follow to avoid leaking state?

**Hints:** (1) `WebSocketSession` → `Mono<Void>`. (2) `Flux<WebSocketMessage>` and `Mono<Void>`. (3) Upgrades from HTTP to the WS protocol. (4) No; WS has its own framing. (5) Reactive `Mono`/`Flux` vs. Servlet callbacks. (6) The lifecycle Mono ends immediately. (7) No. (8) Inbound close/error/cancel. (9) One `Mono<Void>` combining signals properly. (10) Reactive signals/`closeStatus`/metrics. (11) Handles ERROR/CANCEL too. (12) Races/CPU polling. (13) Avoids competing writers and scrambled ordering. (14) `concatMap` preserves order. (15) Different content/framing/payload handling. (16) Holding pooled buffers across async boundaries. (17) No; use WS error messages/close codes. (18) No. (19) No. (20) Native browser constructor disallows arbitrary custom request headers. (21) Mitigates cross-site WS hijacking. (22) No. (23) No; bounds/policies are needed. (24) No. (25) Only offloads blocking. (26) One merged Flux. (27) No; requires a bus/broker. (28) Less complexity for one-way streams. (29) `requestId` + ACK + idempotency. (30) Drain/close/cleanup/backoff/replay.

## 28. References

- [Spring Framework — WebFlux WebSocket API](https://docs.spring.io/spring-framework/reference/6.1/web/webflux-websocket.html)
- [Spring Framework 6.1 — WebSocketHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/WebSocketHandler.html)
- [Spring Framework 6.1 — WebSocketSession Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html)
- [Spring Framework 6.1 — WebSocketMessage Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html)
- [Spring Framework 6.1 — CloseStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/CloseStatus.html)
- [Spring Framework 6.1 — WebSocketHandlerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/server/support/WebSocketHandlerAdapter.html)
- [Spring Framework — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Framework — Reactive Data Buffers](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
- [MDN — WebSocket Web API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [MDN — Writing WebSocket client applications](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications)

**Summary:** Spring WebFlux `WebSocketHandler` handles **one post-handshake WebSocket connection**, taking a `WebSocketSession` and returning a **`Mono<Void>` describing the entire lifecycle**. `receive()` is the inbound `Flux<WebSocketMessage>`; `send(Publisher<WebSocketMessage>)` is the outbound writer. An echo handler uses `session.send(session.receive().map(...))` to join both directions into one flow; multi-producer or long-lived applications must design termination, cancellation, close codes, message ordering, backpressure, and resource cleanup. WebSocket differs from SSE/NDJSON by being **bidirectional with its own message framing**, yet does not automatically provide authentication, authorization, durable delivery, or cluster broadcasting. Test with real WebSocket clients and protect every connection with bounds, security, and lifecycle policies.
