# Handling Text, Binary, and Buffered Payloads in Spring WebFlux WebSocket

## 1. Goal: Handling Bidirectional Messages Without Memory Leaks

WebSocket establishes a long-lived bidirectional connection between client and server. After the HTTP handshake, both sides can proactively send messages over the same connection. Spring WebFlux provides a reactive API to handle that connection through `WebSocketHandler`, `WebSocketSession`, and `WebSocketMessage`.

Each WebSocket message has a primary payload type:

- **Text**: textual data, typically JSON, commands, or events.
- **Binary**: raw byte data, typically images, audio, file chunks, or serialized payloads.
- **Ping/Pong**: control messages for connection health checks and keep-alive.

In WebFlux, payloads are represented by `DataBuffer`. On Reactor Netty, buffers are typically pooled and reference-counted. If you keep a buffer after the current callback ends without retaining it, the data may already be released when asynchronous code later reads it. Conversely, retaining without releasing can cause memory leaks.

This lesson focuses on:

1. The WebSocket handshake and reactive session lifecycle.
2. Receiving and sending text/binary messages.
3. Distinguishing `WebSocketMessage`, frames, payloads, and `DataBuffer`.
4. Converting text to DTOs and handling byte payloads.
5. Managing ownership with `retain()` and `release()`.
6. Using `concatMap`, `flatMap`, and backpressure to process message streams.
7. Limiting sizes, splitting large payloads into chunks, and handling errors.
8. Closing sessions properly, handling Ping/Pong, and dealing with transport errors.
9. Testing the server with `ReactorNettyWebSocketClient`.
10. Building a Java 17+ Spring Boot project runnable with Maven.

## 2. How Does WebSocket Work?

WebSocket starts with an HTTP request asking to upgrade the connection. If the server accepts, both sides switch from HTTP request/response to the WebSocket protocol over the same TCP connection.

Abbreviated handshake example:

```http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
```

The server responds with `101 Switching Protocols` when accepting the upgrade. Then the client and server can send messages independently in both directions.

```text
HTTP handshake
      |
      v
101 Switching Protocols
      |
      v
WebSocket connection
      |
      +------ Client -> Text message ------> Server
      |
      +<----- Binary message <------------- Server
      |
      +------ Client -> Ping --------------> Server
      |
      +<----- Pong ------------------------- Server
      |
      v
Close handshake
```

WebSocket differs from HTTP polling in that a new HTTP request does not need to be created for every message. The connection stays open to exchange many messages, so the server must manage sessions, resources, timeouts, cancellation, and concurrent connection counts.

WebSocket does not define a business schema by itself. The application must specify which fields JSON text contains, what format binary payloads use, which messages are valid, and which errors lead to closing the connection.

## 3. Spring's Reactive WebSocket API

The key abstractions live in the package:

```java
org.springframework.web.reactive.socket
```

### 3.1. `WebSocketHandler`

The server implements `WebSocketHandler` and processes a single session:

```java
public interface WebSocketHandler {
    Mono<Void> handle(WebSocketSession session);
}
```

`handle` returns a `Mono<Void>` representing the entire session handling lifecycle. This publisher must compose the inbound and outbound streams. Do not call `subscribe()` or `block()` inside the handler to run a detached flow.

### 3.2. `WebSocketSession`

`WebSocketSession` represents a WebSocket connection after the handshake. Key APIs:

| API | Role |
|---|---|
| `receive()` | Returns `Flux<WebSocketMessage>` of inbound messages; completes when the connection closes |
| `send(Publisher<WebSocketMessage>)` | Sends an outbound message publisher and returns `Mono<Void>` when sending finishes |
| `textMessage(String)` | Creates a text message using the session's buffer factory |
| `binaryMessage(Function<DataBufferFactory, DataBuffer>)` | Creates a binary message |
| `pingMessage(...)` | Creates a Ping control message |
| `pongMessage(...)` | Creates a Pong control message |
| `close()` | Closes the session with a normal close status |
| `close(CloseStatus)` | Closes the session with a specific status |
| `closeStatus()` | Observes the close status when the connection ends |
| `getId()` | Gets the session ID |
| `getHandshakeInfo()` | Reads handshake metadata |
| `getAttributes()` | Reads session attributes |
| `bufferFactory()` | Gets the factory that creates `DataBuffer` instances for the session |

### 3.3. `WebSocketMessage`

`WebSocketMessage` holds the message type and payload:

```java
WebSocketMessage.Type type = message.getType();
DataBuffer payload = message.getPayload();
```

Common types:

| `WebSocketMessage.Type` | Meaning |
|---|---|
| `TEXT` | Text message |
| `BINARY` | Binary message |
| `PING` | Ping control message |
| `PONG` | Pong control message |

`getPayloadAsText()` decodes the payload into a String using UTF-8. `getPayloadAsText(Charset)` lets you specify a charset when the payload is genuinely contracted to use that charset.

For binary, use `getPayload()` and process the bytes directly. Do not call `getPayloadAsText()` on arbitrary binary data because bytes are not guaranteed to be valid text.

## 4. Inbound and Outbound Are Two Reactive Streams

`session.receive()` and `session.send(...)` are two independent transmission directions:

```text
Client messages
      |
      v
session.receive()
      |
      v
Flux<WebSocketMessage>
      |
      v
Application processing
      |
      v
Flux<WebSocketMessage>
      |
      v
session.send(...)
      |
      v
Client receives messages
```

A simple receive-only handler:

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.receive()
            .doOnNext(message ->
                    log.debug("Received type={}", message.getType()))
            .then();
}
```

`then()` converts the `Flux` into a `Mono<Void>` that completes when the inbound stream ends. This example sends no response.

### 4.1. Echoing Text Messages

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> replies = session.receive()
            .filter(message ->
                    message.getType() == WebSocketMessage.Type.TEXT)
            .map(message ->
                    session.textMessage(
                            "echo: " + message.getPayloadAsText()));

    return session.send(replies);
}
```

For each received text message, the handler creates a new text message and sends it back. `session.send` consumes the outbound publisher; the publisher stays active while inbound keeps emitting messages.

### 4.2. Combining Independent Inbound and Outbound Streams

An application can receive commands while pushing notifications from another source. In that case, compose both publishers into the session lifecycle:

```java
Mono<Void> inbound = session.receive()
        .concatMap(this::processInbound)
        .then();

Mono<Void> outbound = session.send(
        notificationPublisher.map(session::textMessage));

return inbound.and(outbound);
```

The example above works well when both streams have coordinated lifecycles. If `notificationPublisher` is an infinite stream, explicitly design how outbound is cancelled when the client closes the connection; do not let an infinite publisher keep the handler lifecycle holding resources after inbound has ended.

Do not create a separate `subscribe()` for the notification stream. Doing so lets the publisher keep running after the session has closed, and errors/cancellation will not propagate properly through the handler lifecycle.

## 5. Handling Text Payloads

Text WebSocket messages typically contain JSON, commands, or events. `getPayloadAsText()` returns a UTF-8 String:

```java
String json = message.getPayloadAsText();
```

WebSocket text payloads are not automatically deserialized by Spring MVC/WebFlux into DTOs like `@RequestBody`. The handler must parse them explicitly according to the application schema.

DTO example:

```java
public record ChatCommand(
        String type,
        String text,
        String requestId) {
}
```

Use Jackson `ObjectMapper` to decode:

```java
private final ObjectMapper objectMapper;

private ChatCommand decodeText(WebSocketMessage message) {
    if (message.getType() != WebSocketMessage.Type.TEXT) {
        throw new IllegalArgumentException("Expected text message");
    }

    try {
        return objectMapper.readValue(
                message.getPayloadAsText(),
                ChatCommand.class);
    }
    catch (JsonProcessingException error) {
        throw new IllegalArgumentException(
                "Invalid WebSocket JSON message", error);
    }
}
```

Inside a reactive handler, you can parse and invoke a service:

```java
return session.receive()
        .filter(message ->
                message.getType() == WebSocketMessage.Type.TEXT)
        .concatMap(message -> {
            ChatCommand command = decodeText(message);

            return chatService.handle(command)
                    .map(result ->
                            session.textMessage(
                                    objectMapper.writeValueAsString(result)));
        })
        .as(session::send);
```

The illustrative snippet above assumes `writeValueAsString` is wrapped in a helper that handles `JsonProcessingException`; do not let a checked exception leak directly into a `map` lambda.

For small JSON, decoding synchronously upon receiving the message is usually simple. If payloads are large or parsing is CPU-intensive, bound sizes and consider offloading CPU-heavy work to an appropriate scheduler. Never pass a pooled buffer to an asynchronous task without retaining it.

### 5.1. Validating Schema and Command Types

Do not check only that JSON parsing succeeds. Verify:

- Is `type` in the list of allowed commands?
- Are required fields present?
- Is text length within limits?
- Does `requestId` have the right format?
- Is the current user authorized to execute the command?
- Is replay or duplicate request protection applied when business logic requires it?

Syntactically valid JSON can still violate the schema or be unauthorized by business rules.

## 6. Handling Binary Payloads

Binary messages contain raw bytes. Spring does not automatically turn bytes into images, files, protobufs, or objects. The application must know the payload contract.

For example, binary payloads may contain:

- JPEG/PNG or media data.
- File chunks.
- Protobuf/Avro.
- Application-serialized byte arrays.
- Compressed or encrypted data.

Reading the payload:

```java
DataBuffer payload = message.getPayload();
int byteCount = payload.readableByteCount();
```

Copying to `byte[]` when the payload is small and an independent copy is needed:

```java
private static byte[] copyBytes(DataBuffer buffer) {
    byte[] bytes = new byte[buffer.readableByteCount()];
    buffer.read(bytes);
    return bytes;
}
```

`read(bytes)` advances the `DataBuffer` read position. If multiple components need to read the same payload, make a copy or explicitly design ownership and read positions.

### 6.1. Creating Outbound Binary Messages

Use `WebSocketSession.binaryMessage(...)`:

```java
byte[] bytes = new byte[] {0, 1, 2, 3, (byte) 0xFF};

WebSocketMessage response = session.binaryMessage(
        factory -> factory.wrap(bytes));
```

`factory` is the session's `DataBufferFactory`. This creates an outbound buffer from an existing byte array.

### 6.2. Echoing Binary Payloads

```java
private WebSocketMessage echoBinary(
        WebSocketSession session,
        WebSocketMessage inbound) {

    byte[] copy = copyBytes(inbound.getPayload());

    return session.binaryMessage(
            factory -> factory.wrap(copy));
}
```

The byte copy is created synchronously while handling the inbound event. The lambda constructing the outbound buffer references only the independent byte array and does not re-read the inbound `DataBuffer`, which might already be released before send time.

### 6.3. Do Not Arbitrarily Convert Binary to String

Do not use:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
```

unless the application protocol explicitly defines those bytes as UTF-8 text. Binary data can contain invalid charset byte sequences, compressed data, or offset-based structures. Converting to String can lose data or produce unrecoverable content.

## 7. `DataBuffer`: A Byte Region with a Lifecycle

`DataBuffer` is Spring's abstraction for byte data. It can wrap a `ByteBuffer`, a Netty `ByteBuf`, or another implementation.

Some connectors such as Reactor Netty use pooled buffers and reference counting:

```text
Inbound WebSocketMessage
        |
        v
DataBuffer (pooled)
        |
        +---- synchronous read / byte copy
        |             |
        |             v
        |        processing done
        |
        +---- retain across async boundary
                      |
                      v
                  retain()
                      |
                      v
              async processing
                      |
                      v
                  release()
```

The key point is that the payload is not always a `byte[]` owned by the application. The buffer can be reused after the framework/connector finishes handling the message.

### 7.1. Reading Synchronously in a Callback

Example:

```java
session.receive()
        .map(message -> {
            String text = message.getPayloadAsText();
            return session.textMessage("echo:" + text);
        });
```

Text reading happens synchronously right inside the `map` callback, after which a new outbound message is created. No reference to the inbound buffer is kept to be read later.

Similarly, copy binary data into a `byte[]` right inside the callback if the data must outlive the callback.

### 7.2. Retaining a Message Across a Nested Asynchronous Operation

If you need to use an inbound message inside a nested asynchronous publisher, call `retain()` before the message can be released:

```java
return session.receive()
        .concatMap(message -> {
            message.retain();

            return binaryService.store(message.getPayload())
                    .doFinally(signal -> message.release());
        })
        .then();
```

In this example, the service must finish reading/writing the buffer before the publisher completes. `doFinally` frees the retained reference when the publisher completes, errors, or is cancelled.

Rules:

1. Retain only when the buffer must outlive the current callback.
2. Release exactly once for each retain.
3. Release on complete, error, and cancellation paths.
4. Do not release while downstream is still using the buffer.
5. Do not keep pooled buffers in long-lived collections or caches without an explicit ownership policy.

### 7.3. Using `DataBufferUtils` Directly

`WebSocketMessage.retain()` and `release()` are shortcuts for payload operations:

```java
DataBufferUtils.retain(message.getPayload());

// After finishing usage:
DataBufferUtils.release(message.getPayload());
```

Use one consistent ownership management style. Do not call `message.retain()` and also retain the same payload again without a reason and balanced releases.

### 7.4. Avoiding Memory Leaks and Double Releases

Common mistakes:

- Storing a `DataBuffer` in a field and reading it after the receive callback ends.
- Passing the payload into `Mono.delay`, `publishOn`, or an async callback without retaining.
- Retaining a buffer but failing to release on exception.
- Releasing a buffer before an async service finishes reading it.
- Releasing the same reference twice.
- Pushing payloads into an unbounded queue and keeping connections/sessions open long-term.

If the application only needs small data for later processing, copying into a `byte[]` or immutable DTO is usually easier to manage. For large files/binary data, stream to storage with explicit ownership and bounded memory.

## 8. Backpressure and Sequential Processing

WebSocket can deliver messages continuously. Reactive Streams helps regulate demand, yet an application can still build up huge queues if processing is unbounded.

### 8.1. `concatMap`: Preserving Order and Processing Sequentially

```java
return session.receive()
        .concatMap(message ->
                messageService.process(message))
        .then();
```

`concatMap` waits for the current message's publisher to complete before processing the next message. This is a good choice when:

- Message order is meaningful.
- Every message updates the same state.
- You do not want multiple tasks writing to the same session state concurrently.
- Downstream processing has a predictable completion time.

### 8.2. `flatMap`: Bounded Concurrent Processing

```java
return session.receive()
        .flatMap(
                message -> messageService.process(message),
                8)
        .then();
```

Concurrency `8` allows at most a bounded number of tasks to run concurrently. Results may complete out of message arrival order. Use this only when business rules permit and downstream can handle concurrency.

Do not use unbounded concurrency on a stream that can remain open long-term. If each message holds a buffer, high concurrency increases the number of simultaneously live buffers.

### 8.3. Watch Out for Queue and Buffer Operators

Operators such as `onBackpressureBuffer`, `publishOn`, `flatMap` with prefetch, `cache`, or custom queues can hold extra messages/buffers.

If using a queue, specify:

- Maximum capacity.
- Policy when the queue is full.
- Appropriate timeout or drop policy.
- How payloads of dropped messages are released.
- Metrics for queue depth and wait time.

Do not use an unbounded `onBackpressureBuffer()` to mask a producer that is faster than the consumer. With WebSocket, an unboundedly growing queue can exhaust the heap until the application stops functioning.

## 9. Large Payloads and Chunking

A WebSocket message can carry a large payload. If the application copies the entire message into a `byte[]`, the heap must hold a copy of that size in addition to the original buffer and other objects.

For large files or media, design application-level chunking:

```text
Message 1: metadata {transferId, fileName, totalBytes}
Message 2: binary chunk {transferId, sequence=0}
Message 3: binary chunk {transferId, sequence=1}
Message 4: binary chunk {transferId, sequence=2}
Message 5: completion {transferId, checksum}
```

A chunking protocol should include:

- Transfer/session ID.
- Sequence number.
- Total byte count or total chunks if known in advance.
- End flag or completion message type.
- Checksum/hash to verify data integrity.
- ACK or windowing when in-flight data needs to be bounded.
- Timeouts and a transfer cancellation mechanism.
- Resume/retry policy if business requirements demand it.

### 9.1. WebSocket Fragmentation Differs from Application Chunks

The WebSocket protocol can split one logical message into multiple protocol-level frames. Frame boundaries are not business boundaries and should not be used as file-transfer sequence numbers.

Application-level chunking creates multiple independent WebSocket messages with their own metadata. This lets the application control ordering, ACKs, resume, size limits, and partial storage.

Do not assume one TCP packet corresponds to one WebSocket message or one frame. TCP segmentation and WebSocket framing are different layers.

### 9.2. Limiting Message Sizes

Limit all of the following:

- Text message size.
- Binary message size.
- Decoded JSON size.
- Messages per second.
- Total in-flight bytes per session.
- Total concurrent sessions and transfers.

Checking `message.getPayload().readableByteCount()` tells you how many payload bytes the application is receiving. However, checks inside the handler happen after the connector has received/assembled the message. If the connector/server provides frame or message size configuration, set limits at that layer as well to reject oversized payloads earlier.

Do not use `String.length()` as a byte limit. A single Unicode character can occupy multiple UTF-8 bytes.

## 10. Ping, Pong, and Keep-Alive

WebSocket defines Ping and Pong control frames. Ping can check whether the peer is still alive; Pong is the corresponding response.

Spring represents them with:

```java
WebSocketMessage.Type.PING
WebSocketMessage.Type.PONG
```

`WebSocketSession` provides factories:

```java
session.pingMessage(factory -> factory.wrap(payload));
session.pongMessage(factory -> factory.wrap(payload));
```

Connectors may handle some control frames automatically. If the application needs to handle Ping/Pong at the handler layer, verify your connector's behavior to avoid sending duplicate replies.

Ping/Pong is not application data. Do not parse a Ping payload as a JSON command or save it into a binary file transfer.

For long-lived sessions:

- Set a reasonable heartbeat interval.
- Time out sessions when no heartbeat arrives per contract.
- Handle client disconnect/cancellation.
- Do not hold database/file resources once the session has closed.
- Do not send heartbeats so frequently that they create heavy load.

## 11. Closing Sessions and Error Handling

`WebSocketSession.close()` closes the session with normal status. You can pass a `CloseStatus` to describe the reason:

```java
return session.close(CloseStatus.NORMAL);
```

Some standard WebSocket close codes:

| Code | Meaning |
|---:|---|
| 1000 | Normal Closure |
| 1001 | Going Away |
| 1002 | Protocol Error |
| 1003 | Unsupported Data |
| 1007 | Invalid Payload Data |
| 1008 | Policy Violation |
| 1009 | Message Too Big |
| 1011 | Internal Server Error |

Example closing because a payload exceeded limits:

```java
CloseStatus tooLarge = new CloseStatus(
        1009,
        "Message exceeds application limit");

return session.close(tooLarge);
```

Close reasons should be brief and free of stack traces, secrets, or internal details.

### 11.1. Errors in Reactive Handlers

If message processing emits an error, the `handle` publisher may terminate with an error and the connector closes the session per the server's lifecycle. You can log errors in a controlled manner or map business errors before terminating.

```java
return session.receive()
        .concatMap(this::processMessage)
        .then()
        .doOnError(error ->
                log.warn("WebSocket session processing failed: {}",
                        error.getClass().getSimpleName()));
```

Do not swallow every exception with `onErrorResume(error -> Mono.empty())` if doing so misleads the client into thinking the message succeeded. Define which errors are recoverable, which should send an error message, and which should close the session.

### 11.2. Distinguishing Application and Transport Errors

| Category | Examples | Handling |
|---|---|---|
| Payload/schema | Malformed JSON, command missing field | Send error event or close per policy |
| Binary format | Invalid file header, checksum mismatch | Reject transfer and release buffers |
| Policy | Message too large, unauthorized user | Appropriate close status or error response |
| Transport | TCP reset, network disconnect | Clean up resources and terminate session |
| Timeout | Client sends no data before deadline | Close session and release state |
| Internal error | Database/storage failure | Log correlation ID, return safe error or close |

## 12. WebSocket Security

WebSocket does not bypass security just because the initial handshake is HTTP. Both the handshake and post-connection messages must be protected.

- Authenticate users before or during the handshake using Spring Security mechanisms.
- Restrict Origin for browser-facing applications; do not treat `Origin` as an authentication mechanism.
- Authorize per message/command, not only at connection time.
- Limit text/binary sizes and messages per second.
- Validate JSON schemas and binary file signatures.
- Enforce quotas on session count, transfer count, and total volume.
- Close sessions when tokens/sessions expire or permissions are revoked per policy.
- Never log access tokens, cookies, raw binary data, or sensitive chat content.
- Use `wss://` in production over TLS.
- Handle reconnects and duplicate messages using request IDs/idempotency when business logic requires it.

A long-lived WebSocket connection can outlive the initial access token expiration. The application must define policies for re-authentication, token expiry, and session termination.

## 13. Registering a WebSocket Endpoint in Spring Boot WebFlux

You can map `WebSocketHandler` to a URL using `SimpleUrlHandlerMapping`.

```java
@Configuration
public class WebSocketConfiguration {

    @Bean
    public HandlerMapping webSocketMapping(
            EchoWebSocketHandler handler) {

        Map<String, WebSocketHandler> handlers = new HashMap<>();
        handlers.put("/ws/echo", handler);

        SimpleUrlHandlerMapping mapping =
                new SimpleUrlHandlerMapping();

        mapping.setUrlMap(handlers);
        mapping.setOrder(-1);

        return mapping;
    }
}
```

`order = -1` places the WebSocket mapping ahead of annotated controller mappings. When using Spring WebFlux Java configuration or Spring Boot WebFlux auto-configuration, `WebSocketHandlerAdapter` is provided by the WebFlux infrastructure; you do not need to create the adapter manually unless the application does not use that WebFlux configuration.

Do not confuse reactive `WebSocketHandler` with Servlet `WebSocketHandler`. The two stacks have different APIs and session types.

## 14. Runnable Java 17+ Project: Text and Binary Echo

The project below uses:

- Java 17.
- Spring Boot 3.3.5.
- Spring WebFlux and Reactor Netty.
- JUnit 5.
- `ReactorNettyWebSocketClient` to test real connections against a local server.

The server accepts text or binary, adds a prefix for text, and echoes the exact bytes for binary. Binary data is copied synchronously into a `byte[]` before creating the outbound message, so the code never holds an inbound pooled `DataBuffer` past the callback execution.

### 14.1. Structure

```text
webflux-websocket-payload/
├── pom.xml
└── src/
    ├── main/java/edu/demo/ws/
    │   ├── WebSocketApplication.java
    │   ├── EchoWebSocketHandler.java
    │   └── WebSocketConfiguration.java
    └── test/java/edu/demo/ws/
        └── WebSocketIntegrationTests.java
```

### 14.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-websocket-payload</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
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
```

### 14.3. `WebSocketApplication.java`

```java
package edu.demo.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketApplication.class, args);
    }
}
```

### 14.4. `EchoWebSocketHandler.java`

```java
package edu.demo.ws;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Mono;

@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    private static final int MAX_MESSAGE_BYTES = 1024 * 1024;

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.send(
                session.receive()
                        .concatMap(message -> {
                            int size = message.getPayload()
                                    .readableByteCount();

                            if (size > MAX_MESSAGE_BYTES) {
                                return session.close(
                                                new CloseStatus(
                                                        1009,
                                                        "Message too large"))
                                        .then(Mono.<WebSocketMessage>empty());
                            }

                            return switch (message.getType()) {
                                case TEXT -> Mono.just(
                                        session.textMessage(
                                                "echo: "
                                                        + message.getPayloadAsText()));

                                case BINARY -> {
                                    byte[] copy = copyBytes(
                                            message.getPayload());

                                    yield Mono.just(
                                            session.binaryMessage(
                                                    factory -> factory.wrap(copy)));
                                }

                                case PING -> {
                                    byte[] copy = copyBytes(
                                            message.getPayload());

                                    yield Mono.just(
                                            session.pongMessage(
                                                    factory -> factory.wrap(copy)));
                                }

                                case PONG -> Mono.empty();
                            };
                        }));
    }

    private static byte[] copyBytes(DataBuffer buffer) {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return bytes;
    }
}
```

The handler caps each message at 1 MiB after the connector delivers the message into the application. Production should also set corresponding limits at the connector/server layer to reject oversized messages earlier.

`PING` is answered with `PONG` if control messages are forwarded to the handler. Some connectors handle control frames automatically; verify connector behavior before adding manual reply logic in a real application.

### 14.5. `WebSocketConfiguration.java`

```java
package edu.demo.ws;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration
public class WebSocketConfiguration {

    @Bean
    public HandlerMapping webSocketMapping(
            EchoWebSocketHandler handler) {

        SimpleUrlHandlerMapping mapping =
                new SimpleUrlHandlerMapping();

        mapping.setUrlMap(
                Map.of("/ws/echo", (WebSocketHandler) handler));

        mapping.setOrder(-1);
        return mapping;
    }
}
```

### 14.6. `WebSocketIntegrationTests.java`

```java
package edu.demo.ws;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketIntegrationTests {

    @LocalServerPort
    int port;

    private final WebSocketClient client =
            new ReactorNettyWebSocketClient();

    private URI endpoint() {
        return URI.create("ws://127.0.0.1:" + port + "/ws/echo");
    }

    @Test
    void echoesTextMessage() {
        AtomicReference<String> received = new AtomicReference<>();

        client.execute(endpoint(), session -> {
            Mono<Void> send = session.send(
                    Mono.just(session.textMessage("hello")));

            Mono<Void> receive = session.receive()
                    .take(1)
                    .doOnNext(message -> {
                        assertEquals(
                                WebSocketMessage.Type.TEXT,
                                message.getType());

                        received.set(message.getPayloadAsText());
                    })
                    .then();

            return send.then(receive);
        }).block(Duration.ofSeconds(5));

        assertEquals("echo: hello", received.get());
    }

    @Test
    void echoesBinaryPayloadWithoutChangingBytes() {
        byte[] sent = new byte[] {
                0,
                1,
                2,
                3,
                (byte) 0x80,
                (byte) 0xFF
        };

        AtomicReference<byte[]> received = new AtomicReference<>();

        client.execute(endpoint(), session -> {
            Mono<Void> send = session.send(
                    Mono.just(session.binaryMessage(
                            factory -> factory.wrap(sent))));

            Mono<Void> receive = session.receive()
                    .take(1)
                    .doOnNext(message -> {
                        assertEquals(
                                WebSocketMessage.Type.BINARY,
                                message.getType());

                        received.set(copyBytes(message.getPayload()));
                    })
                    .then();

            return send.then(receive);
        }).block(Duration.ofSeconds(5));

        assertNotNull(received.get());
        assertArrayEquals(sent, received.get());
    }

    @Test
    void preservesOrderForMultipleTextMessages() {
        List<String> received = new CopyOnWriteArrayList<>();

        client.execute(endpoint(), session -> {
            Mono<Void> send = session.send(
                    Flux.just(
                            session.textMessage("first"),
                            session.textMessage("second"),
                            session.textMessage("third")));

            Mono<Void> receive = session.receive()
                    .take(3)
                    .doOnNext(message ->
                            received.add(message.getPayloadAsText()))
                    .then();

            return send.then(receive);
        }).block(Duration.ofSeconds(5));

        assertEquals(
                List.of(
                        "echo: first",
                        "echo: second",
                        "echo: third"),
                received);
    }

    private static byte[] copyBytes(DataBuffer buffer) {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return bytes;
    }
}
```

The tests use `block(Duration)` at the JUnit boundary to await completion of the WebSocket exchange. Application session-handling code still uses reactive composition.

### 14.7. Running the Project

From the directory containing `pom.xml`:

```bash
mvn test
```

Run the server:

```bash
mvn spring-boot:run
```

WebSocket endpoint:

```text
ws://localhost:8080/ws/echo
```

You can connect with a WebSocket client such as `wscat`:

```bash
wscat -c ws://localhost:8080/ws/echo
```

Send text:

```text
hello
```

Response:

```text
echo: hello
```

The test suite has three cases:

1. A text message is echoed with the prefix.
2. A binary payload is returned with exact bytes, including `0x80` and `0xFF`.
3. Multiple text messages are processed and returned in order.

Expected output after Maven runs successfully:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

This is the expected result to compare against when running in an environment with Maven/dependencies; this document does not claim the tests were executed in the authoring environment.

## 15. Connecting to a WebSocket Server with WebSocketClient

Spring WebFlux also provides the `WebSocketClient` abstraction. With Reactor Netty:

```java
WebSocketClient client = new ReactorNettyWebSocketClient();

URI uri = URI.create("wss://stream.example.com/ws");

Mono<Void> connection = client.execute(uri, session ->
        session.receive()
                .doOnNext(message ->
                        log.info("Received type={}", message.getType()))
                .then());
```

`execute` opens the handshake, invokes the callback with the session, and returns a `Mono<Void>` representing the connection lifecycle.

Send one message and continue receiving:

```java
Mono<Void> connection = client.execute(uri, session -> {
    Mono<Void> outbound = session.send(
            Mono.just(session.textMessage("{\"type\":\"subscribe\"}")));

    Mono<Void> inbound = session.receive()
            .doOnNext(message -> process(message))
            .then();

    return outbound.then(inbound);
});
```

For long-lived connections, `inbound` usually completes only when the server closes or the transport terminates. Configure appropriate timeouts, cancellation, and reconnect policies.

Do not create a new client per message. Reuse the connector/client per application lifecycle to manage connection resources properly.

## 16. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `getPayloadAsText()` on binary data | Data loss or corruption | Check type and read `DataBuffer` as bytes |
| Assuming JSON is auto-decoded into DTOs | No business object created | Parse text according to application schema |
| Holding `DataBuffer` across async boundary without retain | Buffer may already be released | `message.retain()` and release after processing |
| Retaining without releasing | Pooled memory leak | Release on complete/error/cancel |
| Releasing before service finishes reading | Buffer may become invalid | Release after the consuming publisher completes |
| Copying huge files into `byte[]` | Heap spikes and large copies | Chunk payloads and stream to storage |
| Using unbounded `flatMap` concurrency | Many live buffers/tasks at once | Use `concatMap` or bounded concurrency |
| Using an unbounded queue | Heap grows when consumer is slow | Bounded queue with overflow policy |
| Calling `subscribe()` inside handler | Detaches task from session lifecycle | Return and compose `Mono`/`Flux` |
| Calling `block()` on event loop | Blocks I/O thread | Compose reactive publishers |
| Assuming a TCP packet equals a WebSocket message | Incorrect payload boundary parsing | Handle `WebSocketMessage`, not packet boundaries |
| Assuming protocol fragmentation is file chunking | No sequence/resume control | Define an application-level chunk protocol |
| Not limiting payload size | Clients can send oversized messages | Bound at both connector and application layers |
| Using `String.length()` as a byte limit | Wrong for UTF-8 and Unicode | Use `readableByteCount()` for byte payloads |
| Not distinguishing Ping/Pong from data | Parses control frames as commands | Handle control messages per connector/protocol |
| Not handling client disconnect | Holds resources after socket closes | Rely on completion/cancellation for cleanup |
| Returning stack traces in close reason | Internal information leak | Keep close reasons short and safe |
| Authenticating only at handshake | User may lose access while session stays open | Enforce permission/token-expiry policy per session |

## 17. Production Checklist

### Message Contract

- Text messages have a clear schema and version.
- Binary messages have a defined format and metadata.
- Text/binary payload size limits are enforced.
- Request IDs or sequence numbers are used when needed.
- Rules exist for handling unsupported messages.
- Ping/Pong is handled consistently with the connector.

### Buffer Lifecycle

- Read/copy buffers synchronously when possible.
- If keeping a buffer across an async boundary, retain it.
- Every retain has a matching release.
- Release runs on complete, error, and cancel.
- Do not store pooled buffers in collections/queues indefinitely.
- Large binary data is chunked or streamed instead of copied whole into heap.

### Reactive Lifecycle

- Handler returns `Mono<Void>` representing the session.
- Never call `subscribe()` or `block()` in the handler.
- `concatMap` is used when order is required.
- `flatMap` has bounded concurrency.
- Outbound publisher stops when the session ends.
- Queues are bounded with a full-queue policy.

### Security and Operations

- Handshake is authenticated and Origin-checked appropriately.
- Each message is validated and authorized as needed.
- Rate limits, size limits, and session quotas are enforced.
- Timeouts/heartbeats and reconnect policies are configured.
- Session ID, message type, and correlation ID are logged safely.
- Sensitive raw text/binary payloads are not logged.
- Session cleanup releases resources on disconnect.
- Metrics track active sessions, message rates, payload bytes, queue depth, and errors.

### Testing

- Test text messages.
- Test binary messages with non-ASCII bytes.
- Test multiple messages and ordering.
- Test empty payloads.
- Test oversized messages.
- Test malformed JSON/schema.
- Test disconnect/cancellation.
- Test retain/release in custom async processing if code holds buffers.
- Test Ping/Pong per connector if the application handles control frames.

## 18. Self-Check Exercises

**Exercise 1.** What type does `session.receive()` return?

**Answer:** `Flux<WebSocketMessage>`, emitting inbound messages and completing when the connection closes.

**Exercise 2.** What type does `session.send(...)` return?

**Answer:** `Mono<Void>`, completing when the outbound publisher completes and message writes finish.

**Exercise 3.** Which charset does `getPayloadAsText()` use by default?

**Answer:** UTF-8.

**Exercise 4.** Why should `getPayloadAsText()` not be used to read a JPEG image?

**Answer:** JPEG consists of binary bytes, not UTF-8 text. You must read the `DataBuffer` or copy bytes.

**Exercise 5.** When should `message.retain()` be called?

**Answer:** When keeping an inbound payload across a nested asynchronous operation or past the current callback on a connector using pooled buffers, such as Netty.

**Exercise 6.** After calling retain, what must be done?

**Answer:** Call `message.release()` when processing finishes, including on complete, error, or cancel.

**Exercise 7.** What is the key difference between `concatMap` and `flatMap` when processing messages?

**Answer:** `concatMap` processes publishers sequentially and preserves order; `flatMap` allows concurrent processing and may complete out of order.

**Exercise 8.** Why should an unbounded `onBackpressureBuffer()` not be used?

**Answer:** When the producer is faster than the consumer, the queue grows unboundedly and can exhaust the heap.

**Exercise 9.** Does WebSocket protocol fragmentation replace application-level chunking?

**Answer:** No. Fragmentation is protocol-level frame splitting; application-level chunking requires its own sequence numbers, metadata, ACKs, checksums, and resume rules.

**Exercise 10.** Why should payload size be checked at both the connector and the handler?

**Answer:** Handler checks occur after the message has been received/assembled. Connector limits can reject oversized messages earlier; handler checks enforce business policies.

## 19. Key Takeaways

- `WebSocketHandler` handles a `WebSocketSession` and returns `Mono<Void>` for the entire lifecycle.
- `receive()` is the inbound `Flux<WebSocketMessage>`; `send(Publisher)` is the outbound `Mono<Void>`.
- `WebSocketMessage.Type` distinguishes TEXT, BINARY, PING, and PONG.
- `getPayloadAsText()` decodes UTF-8; binary requires reading `DataBuffer`/bytes.
- `session.textMessage()` and `session.binaryMessage()` create outbound messages using the session's buffer factory.
- On Netty, `DataBuffer` can be pooled and reference-counted.
- If keeping an inbound message across an async boundary, retain beforehand and release after use.
- Synchronous copying into a byte array fits small payloads; large files should be chunked/streamed.
- `concatMap` preserves order; `flatMap` requires bounded concurrency.
- Reactive backpressure does not replace queue bounds, payload size limits, or session quotas.
- WebSocket fragmentation differs from an application-level chunk protocol.
- Close status, Ping/Pong, authentication, Origin, and message authorization must be explicitly designed.
- Handlers must compose reactive lifecycles; do not subscribe manually or block.

When handling WebSocket payloads, determine in order: **message type → payload format → size → DataBuffer ownership → reactive processing approach → session termination**. This sequence helps prevent confusing text with binary and avoids memory leaks when moving processing into asynchronous flows.

## Official Documentation

- Spring Framework 6.2, **WebSockets on the Reactive Stack**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-websocket.html
- Spring Framework 6.1, **`WebSocketSession` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html
- Spring Framework 6.1, **`WebSocketMessage` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html
- Spring Framework 6.1, **`WebSocketMessage.Type` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.Type.html
- Spring Framework 6.2, **Data Buffers and Codecs**: https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html
- Spring Framework 6.2, **WebTestClient**: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html
- IETF, **RFC 6455 – The WebSocket Protocol**: https://www.rfc-editor.org/rfc/rfc6455