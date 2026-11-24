# Differences Between WebSocket, SSE, and Regular HTTP

## 1. Three Communication Models

A web application may need to load data, receive notifications when changes occur, or exchange messages continuously with the server. Regular HTTP, Server-Sent Events (SSE), and WebSocket all use web infrastructure, but they have different models:

- **HTTP request/response:** the client sends a request; the server returns a response. Each business operation is usually an independent call.
- **SSE:** the client opens an HTTP request and keeps the response stream open so the server can send consecutive events. Application data on the stream flows one way from the server to the client.
- **WebSocket:** the client and server establish a long-lived connection; after that, both sides can send messages at any time.

For example, on a dashboard page:

- When opening the page, the browser uses HTTP GET to load summary information.
- When an order status changes, the server sends an SSE event to update the UI.
- On a chat screen, the user sends messages and receives new messages almost simultaneously; WebSocket is a better fit.

No single protocol is always best. Choose based on data direction, update frequency, latency, the need to send messages from the client, reconnect/replay capability, proxy infrastructure, and the cost of keeping connections open.

## 2. Regular HTTP: Request/Response

### 2.1. Operating Model

HTTP models communication as requests to URLs. A request has a method, path, headers, and optionally a body. The server processes it and returns a status, headers, and response body.

~~~text
Client                         Server
  |                               |
  |------- GET /api/orders ------>|
  |                               |
  |<------ 200 + JSON ------------|
  |                               |
  |------- POST /api/orders ----->|
  |                               |
  |<------ 201 + JSON ------------|
~~~

Example:

~~~http
GET /api/orders/42 HTTP/1.1
Host: shop.example
Accept: application/json
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

The client typically initiates a request when it needs data. The server replies to that request; if the order status changes afterward, the client does not know automatically until it sends another request or uses another update mechanism.

### 2.2. Keep-Alive Is Not WebSocket

HTTP/1.1 often reuses a single TCP connection for multiple requests/responses via a persistent connection. HTTP/2 also allows multiplexing multiple streams over a single connection.

That does not turn HTTP into a continuous bidirectional message channel at the application layer. Each operation still follows HTTP request/response semantics. The client can open a new request when needed, while the server cannot arbitrarily push business messages after the response has completed.

HTTP also supports streaming bodies. For example, downloading a large file or writing a response incrementally can keep a response open for a long time. This is still a response stream from the server to the client; it does not provide a bidirectional message protocol like WebSocket.

### 2.3. Polling and Long Polling

If you only use HTTP and want to know whether data has changed, the client can poll:

~~~text
Client             Server
  |--- GET --------->|
  |<-- 200 data -----|
  |                  |
  |--- GET --------->|  (after an interval)
  |<-- 200 data -----|
~~~

Polling is easy to implement, easy to observe, and compatible with most proxies and caches. However, a short interval creates many unnecessary requests; a long interval makes updates slow.

Long polling keeps a request open until data arrives or a timeout occurs. After the server returns a response, the client sends the next request. It reduces repeated polling calls, but it is still a series of consecutive requests/responses rather than a bidirectional message connection.

### 2.4. Strengths and Limitations

**Strengths:**

- Well suited for CRUD, REST APIs, queries, and commands.
- Clear HTTP semantics: method, status, headers, caching, conditional requests.
- Easy to integrate with gateways, proxies, CDNs, logging, and tracing.
- Easy to retry by method/idempotency and handle errors by status.
- No need to keep a dedicated connection open per user just to receive updates.

**Limitations:**

- The client must send a request to fetch new data.
- Polling creates repeated requests and can introduce latency between polls.
- Regular responses do not allow the server to proactively send new messages after the response ends.
- Long polling and streaming require timeouts, cleanup, and handling dropped connections.

## 3. SSE: Server Sends Events Over HTTP

### 3.1. What Is SSE?

Server-Sent Events is a one-way streaming mechanism over HTTP. The browser creates an EventSource to a URL; the server returns a response with Content-Type text/event-stream and keeps the response open to send events.

~~~text
Browser                         Server
  |                               |
  |------- GET /api/events ------>|
  |<------ 200 text/event-stream -|
  |                               |
  |<------ event: status ---------|
  |<------ event: status ---------|
  |<------ event: notification ---|
~~~

The client can still send other HTTP requests to the server, but the SSE connection itself only delivers events from the server to the client. SSE is well suited for notifications, feeds, progress updates, job statuses, and live dashboards.

### 3.2. Event Stream Format

SSE is UTF-8 text. Each event consists of one or more field lines and ends with a blank line. Common fields:

| Field | Meaning |
| --- | --- |
| data | Event payload; multiple data lines are joined with a newline |
| event | Event type name so the client can register a matching listener |
| id | Event ID, stored as the last event ID |
| retry | Reconnect delay in milliseconds |
| comment | Line starting with a colon; does not dispatch an event to the application |

Example:

~~~text
id: 1042
event: order-status
retry: 3000
data: {"orderId":42,"status":"SHIPPED"}

~~~

The blank line after data terminates the event. If there are multiple data lines, the browser joins them with a newline character before invoking the listener.

Comments can be used as a heartbeat to keep the connection from being closed by proxies due to idle timeout:

~~~text
: heartbeat

~~~

Comments are ignored by event handlers while still generating traffic on the wire.

### 3.3. EventSource in the Browser

The browser provides the EventSource API:

~~~javascript
const source = new EventSource("/api/events");

source.addEventListener("order-status", (event) => {
    const update = JSON.parse(event.data);
    console.log("Order update:", update);
});

source.onopen = () => console.log("SSE connected");
source.onerror = (error) => console.warn("SSE interrupted", error);

// When leaving the screen, call source.close() or EventSource.close().
source.close();
~~~

An event without an event field is dispatched as a message event and can be handled with onmessage. Named events such as order-status must be registered with addEventListener("order-status", ...).

EventSource automatically attempts to reconnect when the connection is unexpectedly interrupted. The client can call EventSource.close() to stop completely and prevent further reconnection.

### 3.4. Reconnect, Retry, and Last-Event-ID

If the server sends a retry field, the browser uses that duration as the reconnect delay. If an event has an id, the browser stores the last received ID. When reconnecting, EventSource sends the Last-Event-ID header so the server knows how far the client has read.

An ID does not automatically make the server replay lost data. The application must have an event log, sequence, or durable enough storage to:

1. Read Last-Event-ID from the reconnect request.
2. Find the next event after that ID.
3. Replay missing events in the proper order.
4. Handle the case where the ID has expired or is no longer in the event log.

Without replay, reconnecting only recreates the stream from the new point in time, and the client may miss events during the disconnection window. If the server replays events, the client may also receive duplicates. Use stable event IDs and idempotent handling on the client side.

### 3.5. What Are the Limitations of SSE?

- Only delivers server-to-client events on a single EventSource connection.
- Event payloads are UTF-8 text; there are no native binary messages like WebSocket.
- Native EventSource uses GET and does not provide a general API to set a custom Authorization header. You can use same-origin cookies or credentials mode; if custom methods/headers are needed, consider fetch streaming and parsing SSE yourself.
- The browser reconnects automatically, but replay logic must still be built by the application.
- A long-lived stream requires heartbeats and proper proxy/load balancer configuration.
- With HTTP/1.1, browsers limit the number of concurrent connections per origin; opening many EventSource instances across tabs can hit that limit. HTTP/2 uses a number of streams negotiated between client and server, so the practical limit differs.

SSE is a good fit when the client mainly listens for events and does not need to send application messages back over the same stream.

## 4. WebSocket: Bidirectional Message Channel

### 4.1. What Is WebSocket?

WebSocket provides a full-duplex channel: both the client and server can send messages at any time over the same connection. Once the handshake completes, data is transmitted as WebSocket frames rather than separate HTTP requests/responses.

~~~text
Browser                         Server
  |                               |
  |---- HTTP Upgrade request ---->|
  |<--- 101 Switching Protocols --|
  |                               |
  |<========== WebSocket ========>|
  |---- chat message ------------>|
  |<--- chat reply ---------------|
  |<--- new notification ---------|
  |---- typing state ------------>|
  |<--- another user's message ---|
  |                               |
  |---------- close ------------->|
~~~

WebSocket is well suited for chat, multi-user collaboration, games, interactive control panels, and applications requiring continuous two-way exchange.

### 4.2. Handshake

With traditional WebSocket over HTTP/1.1, the client starts with an HTTP GET containing Upgrade and Connection headers:

~~~http
GET /ws/chat HTTP/1.1
Host: app.example
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example
~~~

If the handshake is valid, the server responds:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
~~~

Then the connection stays open and both sides exchange WebSocket frames. WebSocket is not simply a held-open HTTP response: after the protocol switch, HTTP request/response semantics no longer apply to application messages on that connection.

HTTP/2 has an Extended CONNECT mechanism to establish WebSocket; not every case uses HTTP/1.1 status 101. When deploying behind a proxy or gateway, you must verify that the infrastructure supports the WebSocket mechanism being used.

### 4.3. Messages and Frames

WebSocket distinguishes between protocol-level frames and application-level messages. Common data types:

- Text message: UTF-8 text, often carrying JSON.
- Binary message: binary data such as images, audio chunks, or encrypted payloads.
- Ping/Pong control frame: checks whether the peer is still responsive and supports keepalive.
- Close control frame: initiates the connection-closing handshake with an optional status code and reason.

A single message can be split into multiple frames. Applications do not need to handle fragmentation manually when using a message-level WebSocket API/framework.

WebSocket only provides message transport. It does not dictate the business meaning of the payload. Client and server must agree on schema, message type, version, correlation ID, acknowledgements, and errors. You can use a custom JSON envelope or negotiate a subprotocol such as STOMP via Sec-WebSocket-Protocol.

### 4.4. Reconnect and Reliability

The browser WebSocket API does not automatically reconnect like EventSource. The application must decide:

- When to attempt reconnection.
- How to apply exponential backoff and jitter.
- Whether to cap the number of retry attempts.
- Whether re-authentication is required on reconnect.
- Whether messages sent before disconnecting were acknowledged.
- How to replay missed events or commands.

WebSocket does not inherently guarantee durable message storage or exactly-once processing. If business requirements demand delivery guarantees, design message IDs, sequence numbers, acknowledgements, deduplication, and replay at the application layer.

### 4.5. What Are the Limitations of WebSocket?

- Each client typically holds a long-lived connection; the server must manage connection count, memory, heartbeats, timeouts, and cleanup.
- Proxies and load balancers must forward the handshake and keep the connection open long enough.
- The browser WebSocket API does not allow setting arbitrary HTTP Authorization headers in its constructor; use secure cookies, handshake authentication, or an appropriate token-issuing mechanism.
- If using cookie authentication, you must validate Origin and authorization to prevent Cross-Site WebSocket Hijacking.
- There are no HTTP cache semantics for messages after the handshake.
- The application must define the protocol, payload limits, rate limits, processing order, and disconnect recovery behavior.

## 5. Direct Comparison: HTTP, SSE, and WebSocket

| Criterion | Regular HTTP | SSE | WebSocket |
| --- | --- | --- | --- |
| Model | Request/response | HTTP response stream | Message channel |
| Data direction on one connection | Client-to-server request, server-to-client response | Server → client | Bidirectional |
| Connection | Usually ends logically after response; transport may use keep-alive/reuse | Keeps HTTP response open | Keeps WebSocket session open |
| Data | Body per HTTP media type | UTF-8 text, text/event-stream | Text or binary |
| Server proactively pushes events | Requires open request/stream or new request | Yes | Yes |
| Client sends continuous messages | Sends new HTTP requests | Uses separate HTTP requests | Can send on the same channel |
| Reconnect | Client retries per policy | EventSource reconnects automatically | Application implements it |
| Event replay | Application builds it | Last-Event-ID assists resume; server must replay | Application builds it |
| Cache/proxy | Supports standard HTTP semantics | Requires proper stream and buffering configuration | Requires proxy support for Upgrade/CONNECT |
| Binary | Possible via body | Not native; events are text | Yes |
| Best suited for | CRUD, commands, queries, downloads/uploads | Notifications, feeds, progress, live status | Chat, collaboration, games, bidirectional control |

### 5.1. Decision Tree

~~~text
Does the client need to send messages frequently
over the same connection to the server?
             |
        +----+----+
        |         |
       No        Yes
        |         |
        v         v
Does the server  WebSocket
need to push
events on change?
        |
    +---+---+
    |       |
   No      Yes
    |       |
    v       v
  HTTP     SSE
request/
response
~~~

If you only need a single read or write, start with HTTP. If the server needs to push one-way events, SSE is usually simpler. If both sides need to exchange messages continuously, WebSocket is a better fit.

### 5.2. Specific Use Cases

| Scenario | Typically Suitable Choice | Reason |
| --- | --- | --- |
| Create order, update profile | HTTP | Command and response with clear status |
| Download report or image | HTTP | Body download/upload using HTTP semantics |
| Display import progress | SSE | Server sends progress; browser mainly receives |
| Price feed or job status | SSE | One-way update stream |
| Two-person chat | WebSocket | Client and server send messages continuously |
| Collaborative editor | WebSocket | Multiple clients send edits and receive changes |
| Multiplayer game | WebSocket | High-frequency bidirectional exchange |
| Dashboard refreshing every 30 seconds | HTTP polling may suffice | Simple, no long-lived connection needed |
| Single update after an operation | HTTP response or SSE depending on latency | No need for WebSocket without continuous exchange |

## 6. Spring WebFlux Supports All Three Approaches

Spring WebFlux provides reactive abstractions:

- HTTP controllers return Mono or Flux; codecs read requests and write responses.
- SSE can return Flux<ServerSentEvent<T>> with media type text/event-stream.
- WebSocket uses WebSocketHandler and WebSocketSession; receive() is the inbound message Flux, and send(Publisher) writes outbound messages and returns Mono<Void>.

Mono/Flux pipelines handle non-blocking I/O, backpressure, cancellation, and errors. With WebSocket, the handler must compose the inbound and outbound streams into a single Mono<Void> reflecting the session lifecycle.

There is no need to allocate a separate thread per connection just to wait on I/O. However, CPU-heavy code or blocking libraries must still be isolated on the appropriate scheduler with bounded concurrency.

## 7. Runnable Java 17+ Example: HTTP, SSE, and WebSocket in One Application

This example uses Spring Boot 3.5.16, Java 17+, and WebFlux. The application provides:

- GET /api/status: regular HTTP request/response returning JSON.
- GET /api/events: SSE stream sending a status event every second.
- /ws/echo: WebSocket echo server receiving text messages and returning them prefixed with echo.

### 7.1. Project Structure

~~~text
webflux-realtime-demo/
├── pom.xml
└── src/
    ├── main/java/example/realtime/
    │   ├── DemoApplication.java
    │   ├── RealtimeController.java
    │   ├── StatusResponse.java
    │   ├── StatusEvent.java
    │   ├── EchoWebSocketHandler.java
    │   └── WebSocketConfig.java
    └── test/java/example/realtime/
        └── RealtimeIntegrationTest.java
~~~

### 7.2. pom.xml

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
    <artifactId>webflux-realtime-demo</artifactId>
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

### 7.3. DemoApplication.java

~~~java
package example.realtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.4. StatusResponse.java

~~~java
package example.realtime;

import java.time.Instant;

public record StatusResponse(String status, Instant checkedAt) {
}
~~~

### 7.5. StatusEvent.java

~~~java
package example.realtime;

import java.time.Instant;

public record StatusEvent(long sequence, Instant occurredAt) {
}
~~~

### 7.6. RealtimeController.java

~~~java
package example.realtime;

import java.time.Duration;
import java.time.Instant;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class RealtimeController {

    @GetMapping("/status")
    public Mono<StatusResponse> status() {
        return Mono.just(new StatusResponse("UP", Instant.now()));
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<StatusEvent>> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(sequence -> ServerSentEvent
                        .<StatusEvent>builder(
                                new StatusEvent(sequence, Instant.now()))
                        .id(Long.toString(sequence))
                        .event("status")
                        .retry(Duration.ofSeconds(3))
                        .build());
    }
}
~~~

Each event has an ID, event name, retry interval, and JSON data. Spring uses ServerSentEventHttpMessageWriter to write events as text/event-stream. Flux.interval emits one event per second; when the client disconnects and the subscription is cancelled, the pipeline can stop according to the reactive lifecycle.

This example generates sequences in memory for demonstration purposes. It does not persist events durably and does not replay past events when the browser reconnects. Production requires an event store or sequence/replay mechanism if missing events is unacceptable.

### 7.7. EchoWebSocketHandler.java

~~~java
package example.realtime;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Mono;

@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.send(
                session.receive()
                        .filter(message ->
                                message.getType() == WebSocketMessage.Type.TEXT)
                        .map(message -> session.textMessage(
                                "echo: " + message.getPayloadAsText()))
        );
    }
}
~~~

The handler reads the inbound stream with session.receive(), converts text messages into responses, and sends them with session.send(). When the inbound stream completes due to connection closure, the outbound stream also finishes.

This is a text-only echo server. If the application receives binary messages, you must define how to decode them and enforce appropriate payload limits. For nested asynchronous work, compose Publishers using concatMap/flatMap and manage the DataBuffer lifecycle if retaining data across callbacks.

### 7.8. WebSocketConfig.java

~~~java
package example.realtime;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration(proxyBeanMethods = false)
public class WebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(EchoWebSocketHandler handler) {
        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/echo", handler));
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

SimpleUrlHandlerMapping maps the URL /ws/echo to the WebSocketHandler. In a Spring Boot WebFlux application, WebFlux auto-configuration automatically provides WebSocketHandlerAdapter. Do not add @EnableWebFlux just to register a handler, as doing so can alter Boot's auto-configuration behavior.

### 7.9. RealtimeIntegrationTest.java

~~~java
package example.realtime;

import java.net.URI;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RealtimeIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @LocalServerPort
    int port;

    @Test
    void returnsOrdinaryHttpJsonResponse() {
        webTestClient.get()
                .uri("/api/status")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.status").isEqualTo("UP")
                .jsonPath("$.checkedAt").isNotEmpty();
    }

    @Test
    void streamsTwoServerSentEvents() {
        Flux<StatusEvent> events = webTestClient.get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(StatusEvent.class)
                .getResponseBody()
                .take(2);

        StepVerifier.create(events)
                .expectNextCount(2)
                .verifyComplete();
    }

    @Test
    void echoesWebSocketTextMessage() {
        AtomicReference<String> received = new AtomicReference<>();
        WebSocketClient client = new ReactorNettyWebSocketClient();
        URI uri = URI.create("ws://127.0.0.1:" + port + "/ws/echo");

        Mono<Void> exchange = client.execute(uri, session -> {
            Mono<Void> send = session.send(
                    Mono.just(session.textMessage("hello")));

            Mono<Void> receive = session.receive()
                    .take(1)
                    .filter(message ->
                            message.getType() == WebSocketMessage.Type.TEXT)
                    .doOnNext(message ->
                            received.set(message.getPayloadAsText()))
                    .then();

            return send.and(receive);
        });

        StepVerifier.create(exchange).verifyComplete();
        assertThat(received.get()).isEqualTo("echo: hello");
    }
}
~~~

The HTTP test verifies the JSON response. The SSE test reads two events and then cancels the subscription so the stream is not kept open indefinitely. The WebSocket test opens a session to the server, sends a text message, receives the echo, and asserts its content.

### 7.10. Running and Verifying the Application

From the directory containing pom.xml:

~~~bash
mvn test
~~~

Run the application:

~~~bash
mvn spring-boot:run
~~~

Verify regular HTTP:

~~~bash
curl -i http://localhost:8080/api/status
~~~

Sample response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP","checkedAt":"2026-11-08T01:00:00Z"}
~~~

The checkedAt timestamp changes with each call.

Verify SSE with curl. The -N flag disables curl buffering so events appear as soon as they are received:

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/events
~~~

Sample output:

~~~text
id:0
event:status
retry:3000
data:{"sequence":0,"occurredAt":"2026-11-08T01:00:01Z"}

id:1
event:status
retry:3000
data:{"sequence":1,"occurredAt":"2026-11-08T01:00:02Z"}

~~~

Timestamps depend on real time. In a browser, EventSource manages reconnection automatically.

Verify WebSocket using the browser console:

~~~javascript
const scheme = location.protocol === "https:" ? "wss://" : "ws://";
const socket = new WebSocket(scheme + location.host + "/ws/echo");

socket.addEventListener("open", () => {
    socket.send("hello");
});

socket.addEventListener("message", (event) => {
    console.log(event.data); // echo: hello
});

socket.addEventListener("close", (event) => {
    console.log("closed", event.code, event.reason);
});

socket.addEventListener("error", (event) => {
    console.error("websocket error", event);
});
~~~

You can use a WebSocket client tool such as websocat if installed:

~~~bash
websocat ws://localhost:8080/ws/echo
~~~

Entering hello will return echo: hello.

## 8. Security: HTTP, SSE, and WebSocket

### 8.1. TLS

- Use HTTPS for HTTP and SSE.
- Use WSS for WebSocket in production environments.
- Do not mix an HTTPS page with an unencrypted ws:// endpoint; browsers typically block mixed content.

### 8.2. Authentication and Authorization

Regular HTTP can use the Authorization header, cookies, OAuth2 bearer tokens, or other authentication mechanisms.

Native EventSource does not allow setting an arbitrary Authorization header. For same-origin SSE, session cookies can be sent according to browser policy. For cross-origin, configure CORS and credentials properly; EventSource supports withCredentials.

The browser WebSocket API also does not allow passing an arbitrary set of custom HTTP headers in its constructor. You can use secure session cookies, handshake authentication, or an appropriate token-issuing protocol. Avoid putting long-lived access tokens in query strings because URLs may appear in access logs, proxy logs, or telemetry.

After the handshake, WebSocket must still check permissions for each message and each resource requested by a message. Authenticating when opening a connection does not mean every subsequent action is permitted.

### 8.3. Origin and Cross-Site WebSocket Hijacking

With cookie authentication, another website could attempt to open a WebSocket to your server in a logged-in browser. The server must validate Origin against an allowlist and authenticate the session properly to prevent Cross-Site WebSocket Hijacking.

The WebSocket handshake includes an Origin header, but it should not be treated as a replacement for authentication. HTTP CORS does not automatically provide complete protection for WebSocket. Configure Origin checks at the WebSocket endpoint or handshake service.

SSE is an HTTP request and therefore follows standard CORS policies. When allowing credentials, do not use a wildcard origin; allow only specific origins and configure credentials properly.

### 8.4. Payload Validation and Resource Limits

Both SSE and WebSocket can keep connections open for a long time. Limit message size and send rate, validate schema/type/version, enforce permissions per channel/topic/resource, limit connections per user/tenant, and close inactive connections according to policy. Do not log tokens, cookies, personal data, or sensitive payloads.

## 9. Operations and Scaling

### 9.1. Proxies and Load Balancers

SSE requires the response stream to be forwarded continuously. Proxy buffering can cause events to be batched before sending, breaking the realtime experience. Disable buffering for SSE endpoints when needed, set a sufficiently long idle timeout, and send periodic heartbeats if the stream emits few events.

WebSocket requires proxies to forward the Upgrade handshake or support the corresponding WebSocket mechanism. Load balancers must keep connections open long-term and not close them due to an overly short idle timeout.

### 9.2. Connection Count and Capacity

Short HTTP requests/responses typically release resources after each operation. SSE and WebSocket hold connections open longer. When tens of thousands of clients are online concurrently, the server must manage many sessions, network buffers, heartbeats, schedulers, and subscriptions.

Monitor open connections, SSE stream and WebSocket session counts, outbound queue size, message rate, latency, reconnect rate, timeouts, close codes, memory, CPU, and network.

Do not create unbounded queues per connection. If a client is slow, choose an explicit policy: backpressure, dropping old events, coalescing to the latest state, bounding buffers, or closing overly slow clients.

### 9.3. Horizontal Scaling

If the application has multiple instances, clients may connect to different nodes. An event created on node A must reach open connections on nodes B/C if they belong to the same recipient group.

A message broker or internal pub/sub is usually required to fan out events across instances. Sticky sessions only route requests back to the same node; they do not synchronize events across nodes.

If SSE or WebSocket replay is needed, store events/sequences in a queryable location. Do not rely on a single JVM's memory as the source of truth across multiple instances or restarts.

### 9.4. Heartbeat and Timeout

SSE can send comment heartbeats to keep streams alive through proxies. WebSocket has ping/pong control frames to check whether the peer is alive. At the application layer, you can also define heartbeat messages if you need to observe logical state.

Set timeouts aligned with proxies, load balancers, and clients. Heartbeats that are too frequent increase traffic; heartbeats that are too sparse may fail to prevent idle timeouts.

## 10. Backpressure and Message Processing in WebFlux

WebFlux uses Reactive Streams to coordinate demand and cancellation. With SSE, the controller returns a Flux of events; with WebSocket, both session.receive() and session.send() work with Publishers.

- Return a Flux directly to the framework instead of calling subscribe() manually.
- Use concatMap when messages must be processed sequentially.
- Only use flatMap when concurrent processing is bounded.
- Never call block() on an event-loop thread.
- Bound queues if the producer is faster than the client.
- When a client disconnects, clean up subscriptions, timers, and resources bound to the session.
- If retaining a DataBuffer/WebSocket message across asynchronous work on a server using pooled buffers, follow the retain/release contract.

Backpressure alone does not decide the business policy for slow clients. A dashboard that only needs the latest state can coalesce multiple updates into one snapshot. Chat or transactions that must preserve every message may need durable queues and acknowledgements.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using WebSocket for every endpoint | Increases connection and protocol complexity | Use HTTP for regular request/response |
| Using overly short polling | Many repeated requests and increased load | Choose SSE if only server push is needed |
| Using SSE for two-way chat | Client must send messages via separate HTTP calls | Use WebSocket if both sides need continuous messages |
| Thinking HTTP keep-alive is WebSocket | Confuses transport reuse with a message channel | Distinguish request/response from post-handshake protocol |
| Thinking SSE replays lost events automatically | Data may be missed on disconnect | Store events and handle Last-Event-ID on the server |
| Not attaching stable event IDs | Cannot resume in a controlled manner | Use sequence/event IDs and a replay log |
| Thinking WebSocket reconnects automatically | Client loses connection and fails to recover | Implement backoff, reconnect, and resume |
| Thinking WebSocket guarantees delivery | Messages may be lost when connection drops | Use acknowledgements, IDs, deduplication, and replay |
| Not sending SSE heartbeats | Proxies may close idle streams | Send comment heartbeats and tune timeouts |
| Proxy buffers SSE | Events get batched, updates are delayed | Disable buffering for stream endpoints |
| Proxy does not forward Upgrade | WebSocket handshake fails | Configure Upgrade/CONNECT forwarding |
| Not validating Origin | Risk of Cross-Site WebSocket Hijacking | Allowlist Origins and authenticate handshakes |
| Putting tokens in query strings | Tokens may leak into logs | Use secure cookies or an appropriate handshake mechanism |
| Not bounding messages/queues | A single client can exhaust memory | Set payload limits, rate limits, and bounded queues |
| Calling subscribe() in WebSocket handler | Loses lifecycle and cancellation management | Compose Publishers and return Mono<Void> |
| Holding connections without cleanup | Sessions, timers, or subscriptions leak | Clean up on complete/error/cancel |
| Treating SSE and WebSocket as cacheable like HTTP GET | Caches/proxies mishandle streams | Set appropriate cache policies |

## 12. Protocol Selection Checklist

Before choosing, answer:

1. Is data one-way or two-way?
2. Does the client need to send messages frequently over the same connection?
3. Does the server need to push events immediately when changes occur?
4. Are binary messages required?
5. Does the client need automatic reconnection or application-controlled reconnection?
6. Is event replay required after a disconnect?
7. Are acknowledgements or delivery guarantees required?
8. Does the browser need a custom Authorization header?
9. How do proxies, gateways, and load balancers support SSE/WebSocket?
10. What is the expected number of concurrent connections?
11. How does the producer handle slow clients?
12. Is pub/sub across multiple application instances needed?
13. Are Origin checks, authentication, and per-message authorization in place?
14. Are connection counts, queues, latency, and disconnects monitored?

## 13. Key Takeaways

- Regular HTTP is suitable for request/response, CRUD, commands, queries, and file transfers.
- HTTP keep-alive reuses connections but does not turn HTTP into a bidirectional message channel.
- SSE keeps an HTTP response open and delivers one-way events from server to client via text/event-stream.
- EventSource supports named events, reconnect, retry, and Last-Event-ID; the server must implement event replay itself.
- WebSocket starts with an HTTP handshake and then switches to a bidirectional frame protocol over a long-lived connection.
- WebSocket supports text, binary, ping/pong, and close frames; message semantics belong to the application or subprotocol.
- SSE is typically simpler for notifications/feeds/progress; WebSocket fits chat, collaboration, and two-way interactive apps.
- With Spring WebFlux, SSE uses Flux<ServerSentEvent<T>>; WebSocket uses WebSocketHandler, WebSocketSession.receive(), and send().
- Manage timeouts, heartbeats, backpressure, queues, connection counts, Origin, and authentication.
- With multiple instances, use pub/sub or an event broker to distribute events; sticky sessions do not replace data synchronization.
- Choose a protocol based on data direction and recovery requirements, not merely how new the technology is.

**Official Documentation:**
- [Spring Framework 6.2 — WebFlux WebSocket](https://docs.spring.io/spring/reference/6.2/web/webflux-websocket.html)
- [Spring Framework — WebSocket API and handshake](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [Spring Framework 6.2 Javadoc — ServerSentEvent](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/http/codec/ServerSentEvent.html)
- [Spring Framework 6.2 Javadoc — ServerSentEvent.Builder](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/http/codec/ServerSentEvent.Builder.html)
- [Spring Framework — WebFlux reactive HTTP handling](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [MDN — Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [MDN — EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [IETF RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
