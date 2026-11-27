# Proxying WebSocket or SSE and Verifying Continuous Data Streaming

## 1. Practice Objectives

An API Gateway typically handles short request/response exchanges: the client sends a request, the Gateway picks a route, upstream returns a response, and the HTTP connection closes. However, some features require **long-lived open connections**:

This is a hands-on lab in the **Comprehensive Practice** chapter of the **SPRING_CLOUD_GATEWAY** module. **Module description:** Build an API Gateway with Spring Cloud Gateway using route predicates, filter chains, path/header transformations, and service discovery. Practice authentication, rate limiting, circuit breakers, retries, TLS, and request observability to operate a microservices entry point securely.

- Dashboards updating order status in real time.
- Pages tracking export or background job progress.
- Chat, notification, and collaborative editing apps.
- Dashboards receiving continuous log/metric/event streams.

In this lab, you will set up a Spring Cloud Gateway WebFlux instance in front of a WebFlux backend and proxy two streaming protocols:

1. **Server-Sent Events (SSE):** the backend pushes one-way events over a `text/event-stream` HTTP response; browsers use `EventSource` to consume events and reconnect automatically.
2. **WebSocket:** client and server exchange bidirectional messages over an upgraded HTTP connection.

Lab topology:

~~~mermaid
flowchart LR
    B["Browser / test client"] --> G["Spring Cloud Gateway WebFlux :8080"]
    G -->|"GET /api/events<br/>HTTP stream"| S["Realtime service :9081"]
    G -->|"GET /ws/echo<br/>Upgrade: websocket"| S
    S -->|"text/event-stream"| G
    S <-->|"WebSocket frames"| G
~~~

After completing this lab, you can:

- Distinguish the HTTP handshake from data transmitted after the handshake.
- Configure `http://` routes for SSE and `ws://`/`wss://` routes for WebSocket.
- Use `lb://` or `lb:ws://` when service discovery/load balancing is required.
- Write a reactive backend emitting SSE and handling WebSocket messages.
- Verify that events/frames traverse the Gateway, rather than checking only HTTP 200/101.
- Handle heartbeats, timeouts, reconnects, `Last-Event-ID`, Origin, auth, and graceful shutdown.
- Identify filters/policies unsuitable for long-lived streams.

**Outcome to prove:** data emitted by the backend reaches the client through the Gateway over time, the client receives multiple events/frames on a single connection, and when the client closes the connection, the reactive stream cancels cleanly.

## 2. Choosing the Right Protocol

| Criterion | SSE | WebSocket |
| --- | --- | --- |
| Direction | Server → client | Bidirectional |
| Transport | Long-lived HTTP response | HTTP Upgrade followed by WebSocket frames |
| Content type/handshake | `text/event-stream` | `Upgrade: websocket`, `101 Switching Protocols` response |
| Browser API | `EventSource` | `WebSocket` |
| Reconnect | `EventSource` reconnects automatically per SSE spec | Application implements its own |
| Resume cursor | `id` and `Last-Event-ID` request header | Application defines its own sequence/cursor |
| Sending client → server data | Separate HTTP requests | Send messages over the socket |
| Best suited for | Notifications, progress, live feeds | Chat, gaming, collaborative editing, realtime command/response |
| Proxy route | Standard HTTP route | WebSocket route with `ws`/`wss` scheme |

### 2.1. When to Use SSE?

Choose SSE when the server actively pushes events and the client does not need to stream messages continuously on the same connection. Examples:

- Processing status of `job-42`: queued → running → completed.
- Dashboards displaying live logs.
- Order pages updating delivery status.
- Receive-only notification streams where acknowledgments still call REST APIs.

Because SSE uses HTTP, it leverages existing HTTP infrastructure. Browser `EventSource` supports automatic reconnection and sends `Last-Event-ID` if the server emitted events with `id`.

### 2.2. When to Use WebSocket?

Choose WebSocket when both client and server need to send messages frequently:

- Chat: clients send messages; the server broadcasts messages and read receipts.
- Collaborative editors: clients send edit operations; the server broadcasts them.
- Games: clients send input; the server returns state.
- Realtime devices: both sides exchange commands/events over a single session.

WebSocket does not inherently define message schemas, authentication refresh, replay, or reconnection. Those belong to the **application protocol** your system must design.

### 2.3. A Long-Lived Connection Is Not a Series of Independent Requests

SSE keeps one HTTP response open; WebSocket keeps one session open after handshake. Once streaming begins:

- You cannot switch backends mid-stream by re-routing individual events/frames.
- HTTP retries cannot safely replay a partially delivered stream without a cursor/resume contract.
- Circuit breakers measure call setup/completion per their integration semantics; they are not a mechanism for inspecting individual WebSocket frames.
- Client disconnects, proxy idle timeouts, backend restarts, or deployments can terminate sessions.

Therefore, **reconnect/resume and duplicate/missed-event handling are the application's responsibility**.

## 3. Preparing Two Separate Spring Boot Applications

Create two standalone applications:

~~~text
realtime-lab/
├── gateway/
│   └── src/main/resources/application.yml
└── realtime-service/
    ├── src/main/java/demo/realtime/
    │   ├── RealtimeApplication.java
    │   ├── EventController.java
    │   ├── EchoWebSocketHandler.java
    │   └── WebSocketConfig.java
    └── src/main/resources/application.yml
~~~

Running two separate processes confirms the Gateway genuinely proxies over the network rather than invoking an in-process handler.

### 3.1. Gateway Dependencies

With compatible Spring Boot/Spring Cloud BOMs, the main Maven dependencies are:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Do not assign separate starter versions when managed by the Spring Cloud BOM. The Gateway application uses WebFlux/Reactor Netty; **do not mix Spring Cloud Gateway Server Web MVC into the same lab**.

### 3.2. realtime-service Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring WebFlux supports `Flux<ServerSentEvent<?>>` for writing events as they arrive, and `WebSocketHandler` for wiring inbound/outbound message streams.

### 3.3. Configuring the Backend Port

`realtime-service/src/main/resources/application.yml`:

~~~yaml
server:
  port: 9081

spring:
  application:
    name: realtime-service

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

`RealtimeApplication.java`:

~~~java
package demo.realtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RealtimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RealtimeApplication.class, args);
    }
}
~~~

## 4. Building an SSE Endpoint with Event IDs and Heartbeats

SSE is an HTTP response with media type `text/event-stream`. Each event may contain:

| Field | Purpose |
| --- | --- |
| `id` | Cursor sent back by the client as `Last-Event-ID` on reconnect |
| `event` | Event name for `addEventListener` |
| `data` | Payload |
| `retry` | Delay in milliseconds the browser waits before reconnecting |
| comment | Comment line, commonly used as a heartbeat without emitting a business event |

### 4.1. EventController.java

`realtime-service/src/main/java/demo/realtime/EventController.java`:

~~~java
package demo.realtime;

import java.time.Duration;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class EventController {

    @GetMapping(value = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<Flux<ServerSentEvent<String>>> events(
            @RequestHeader(name = "Last-Event-ID", required = false)
            String lastEventId) {

        long resumeAfter = parseEventId(lastEventId);

        Flux<ServerSentEvent<String>> businessEvents =
                Flux.interval(Duration.ofSeconds(1))
                        .map(sequence -> sequence + resumeAfter + 1)
                        .map(sequence -> ServerSentEvent.<String>builder()
                                .id(Long.toString(sequence))
                                .event("tick")
                                .data("event-" + sequence)
                                .retry(Duration.ofSeconds(3))
                                .build());

        Flux<ServerSentEvent<String>> heartbeats =
                Flux.interval(Duration.ofSeconds(15))
                        .map(ignored -> ServerSentEvent.<String>builder()
                                .comment("keepalive")
                                .build());

        Flux<ServerSentEvent<String>> stream =
                Flux.merge(businessEvents, heartbeats)
                        .doFinally(signal -> {
                            // Log only status/trace IDs in real applications.
                            // Never log payloads or session credentials.
                        });

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .cacheControl(CacheControl.noCache())
                // Helpful header when Nginx sits in front.
                .header("X-Accel-Buffering", "no")
                .body(stream);
    }

    private long parseEventId(String lastEventId) {
        if (lastEventId == null || lastEventId.isBlank()) {
            return -1;
        }
        try {
            return Math.max(-1, Long.parseLong(lastEventId));
        } catch (NumberFormatException ignored) {
            return -1;
        }
    }
}
~~~

**Lab resume scope:** `Last-Event-ID` is read to illustrate a cursor and continue sequence numbering. In real systems, events must come from an event log/broker or store with retention; incrementing a sequence number does not replay missed events. Only emit real events still within the retention window.

### 4.2. Heartbeats Are Comments, Not Business Events

The server emits a comment:

~~~text
:keepalive

~~~

Browsers do not fire a `message` event for comments. Heartbeats simply help proxies/load balancers recognize that the connection is still active. They do not replace health checks and do not prove the backend can process commands.

Set the heartbeat interval **shorter than the smallest idle timeout** along the entire path (browser/mobile network, ingress, Gateway, service mesh, load balancer), with a safety margin. Never guess one universal number for every environment.

### 4.3. Real Resume Requires an Event Store

In production, a typical flow is:

1. Each event carries a monotonically increasing ID or durable cursor.
2. The browser receives events and remembers `lastEventId`.
3. On reconnect, the browser sends `Last-Event-ID`.
4. The server reads events after that cursor from the store/broker within retention.
5. If the cursor is too old or invalid, return a reset/resync signal per contract.

If events are produced across multiple partitions, a single sequence number cannot be compared globally; the cursor must encode partition/offset or an opaque token. Do not rely on timestamps alone when duplicates or reordering can occur.

## 5. Building a WebSocket Echo Endpoint

WebSocket begins with an HTTP handshake. After the Gateway proxies the handshake successfully, the connection upgrades and message frames are relayed through the WebSocket routing infrastructure.

### 5.1. EchoWebSocketHandler.java

`realtime-service/src/main/java/demo/realtime/EchoWebSocketHandler.java`:

~~~java
package demo.realtime;

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
                .map(WebSocketMessage::getPayloadAsText)
                .map(text -> session.textMessage("echo: " + text));

        return session.send(replies);
    }
}
~~~

`receive()` is the inbound stream; `send()` writes the outbound stream. When the client closes the session, the inbound stream completes and the outbound source is cancelled. Never call `block()` on the event loop.

This is a lab echo handler, not a multi-user chat server. Broadcasting requires a broker/topic or a session registry with well-designed lifecycle management, backpressure, fan-out, and cleanup.

### 5.2. WebSocketConfig.java

`realtime-service/src/main/java/demo/realtime/WebSocketConfig.java`:

~~~java
package demo.realtime;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration(proxyBeanMethods = false)
public class WebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(EchoWebSocketHandler handler) {
        Map<String, WebSocketHandler> handlers =
                Map.of("/ws/echo", handler);

        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(handlers);
        // WebSocket mapping runs before annotated controller mappings.
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

Spring Boot WebFlux auto-configures the WebSocket handler adapter for supported embedded servers. If building WebFlux infrastructure manually outside auto-configuration, declare the appropriate adapter/service beans.

## 6. Configuring the Gateway to Proxy Both Protocols

The Gateway runs on port `8080`. `gateway/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: realtime-gateway
  cloud:
    gateway:
      server:
        webflux:
          websocket:
            # Same-origin lab: the test page is served from http://localhost:8080.
            # If the UI uses another origin, add that exact origin.
            allowed-origins:
              - http://localhost:8080
          routes:
            - id: realtime-sse
              uri: http://localhost:9081
              predicates:
                - Path=/api/events

            - id: realtime-websocket
              uri: ws://localhost:9081
              predicates:
                - Path=/ws/**

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Explanation:

- SSE uses an `http://` URI because it is HTTP response streaming.
- WebSocket uses `ws://`; when the public edge uses TLS, clients connect via `wss://` to the Gateway, and the Gateway can use internal `ws://` inside a trusted network or `wss://` if upstream requires TLS.
- `Path=/api/events` and `Path=/ws/**` preserve paths to the backend, so the lab needs no `StripPrefix`.
- WebFlux Gateway includes a WebSocket routing filter that recognizes `ws`/`wss` schemes.
- `allowed-origins` is an allowlist for browser WebSocket handshakes. If the frontend lives at `http://localhost:3000`, add that exact origin instead of opening all origins.

### 6.1. Paths When Using Service Discovery

Once discovery/LoadBalancer is configured, you can switch upstreams:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: realtime-sse
              uri: lb://realtime-service
              predicates:
                - Path=/api/events

            - id: realtime-websocket
              uri: lb:ws://realtime-service
              predicates:
                - Path=/ws/**
~~~

`lb:ws://` lets LoadBalancer select an instance at **the moment the WebSocket connection is established**. After the handshake, the session stays pinned to that instance for the lifetime of the connection; the Gateway does not re-select instances per frame. SSE likewise remains pinned to one upstream for the duration of the response stream.

Do not use `lb://` without a discovery client/LoadBalancer and an appropriate service instance list. For the localhost lab, keep static URIs.

### 6.2. Gateway 4.x Configuration

If using Spring Cloud Gateway Server WebFlux 4.x, route configuration typically lives under the older namespace:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: realtime-sse
          uri: http://localhost:9081
          predicates:
            - Path=/api/events
        - id: realtime-websocket
          uri: ws://localhost:9081
          predicates:
            - Path=/ws/**
~~~

Do not place both 4.x and 5.x namespaces in the same file. Pick the namespace matching your actual starter/BOM and verify routes are loaded at runtime.

## 7. Adding a Browser Page to Test Both SSE and WebSocket

To avoid Origin confusion, the lab serves a demo page through the Gateway itself at `http://localhost:8080/demo`. The page and WebSocket handshake therefore share the same origin.

### 7.1. DemoPageController.java

`realtime-service/src/main/java/demo/realtime/DemoPageController.java`:

~~~java
package demo.realtime;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoPageController {

    @GetMapping(value = "/demo", produces = MediaType.TEXT_HTML_VALUE)
    public String demo() {
        return """
                <!doctype html>
                <html lang="en">
                <head>
                  <meta charset="utf-8">
                  <meta name="viewport" content="width=device-width, initial-scale=1">
                  <title>Gateway streaming lab</title>
                </head>
                <body>
                  <h1>WebSocket and SSE through Gateway</h1>
                  <p>This page and the Gateway share the same origin: <code id="origin"></code></p>
                  <p>WebSocket: <strong id="ws-state">connecting</strong></p>
                  <input id="message" value="hello gateway" />
                  <button id="send" type="button">Send WebSocket message</button>
                  <p>SSE: <strong id="sse-state">connecting</strong></p>
                  <pre id="log"></pre>
                  <script>
                    const log = (value) => {
                      document.getElementById("log").textContent +=
                        value + "\\n";
                    };
                    document.getElementById("origin").textContent =
                      location.origin;

                    const wsScheme =
                      location.protocol === "https:" ? "wss://" : "ws://";
                    const socket = new WebSocket(
                      wsScheme + location.host + "/ws/echo");

                    socket.addEventListener("open", () => {
                      document.getElementById("ws-state").textContent = "open";
                      log("WebSocket handshake completed");
                    });
                    socket.addEventListener("message", (event) => {
                      log("WS ← " + event.data);
                    });
                    socket.addEventListener("close", (event) => {
                      document.getElementById("ws-state").textContent =
                        "closed (" + event.code + ")";
                    });
                    socket.addEventListener("error", () => {
                      log("WebSocket error; inspect browser Network/Console");
                    });
                    document.getElementById("send").addEventListener(
                      "click", () => {
                        if (socket.readyState !== WebSocket.OPEN) {
                          log("WebSocket is not open");
                          return;
                        }
                        const value =
                          document.getElementById("message").value;
                        socket.send(value);
                        log("WS → " + value);
                      });

                    const events = new EventSource("/api/events");
                    events.addEventListener("open", () => {
                      document.getElementById("sse-state").textContent = "open";
                    });
                    events.addEventListener("tick", (event) => {
                      log("SSE #" + event.lastEventId + " ← " + event.data);
                    });
                    events.addEventListener("error", () => {
                      document.getElementById("sse-state").textContent =
                        "reconnecting or disconnected";
                    });

                    window.addEventListener("beforeunload", () => {
                      socket.close(1000, "page closed");
                      events.close();
                    });
                  </script>
                </body>
                </html>
                """;
    }
}
~~~

### 7.2. Adding the Demo Page Route to the Gateway

Add this route under `routes` in `application.yml`:

~~~yaml
- id: realtime-demo-page
  uri: http://localhost:9081
  predicates:
    - Path=/demo
~~~

The `/demo` route exists solely to serve the lab HTML; SSE and WebSocket still have their own routes. In production, UI pages are normally served from a separate web server/CDN.

### 7.3. Opening and Interacting

Start both applications, then open:

~~~text
http://localhost:8080/demo
~~~

Expected results:

- WebSocket state switches to `open`.
- SSE state switches to `open`.
- Every second the log appends `SSE #0`, `SSE #1`, ...
- Enter a message and click Send; the log displays `WS → hello gateway` and `WS ← echo: hello gateway`.
- Reloading the page closes the old sessions and establishes new ones.

In DevTools → Network:

- The `/ws/echo` request completes a `101 Switching Protocols` handshake; the Messages/Frames tab shows echoes.
- The `/api/events` request stays pending/open and receives multiple events over time; the response has `Content-Type: text/event-stream`.

**Do not look only at `101` or `200`:** a successful handshake does not prove frame relay, and an SSE 200 does not prove events continue flushing to the client.

## 8. Starting Up and Verifying via Command Line

### 8.1. Start the Backend

In terminal 1, inside `realtime-service`:

~~~bash
./mvnw spring-boot:run
~~~

The backend listens on `http://localhost:9081`.

### 8.2. Start the Gateway

In terminal 2, inside `gateway`:

~~~bash
./mvnw spring-boot:run
~~~

The Gateway listens on `http://localhost:8080`.

If using Windows PowerShell, the Maven Wrapper is `.\mvnw.cmd spring-boot:run`. Ensure both applications use compatible Spring Boot/Spring Cloud BOMs and do not collide on ports.

### 8.3. Testing SSE with curl

~~~bash
curl -N -i --max-time 5 http://localhost:8080/api/events
~~~

`-N` disables curl-side buffering; `--max-time 5` ends the command after 5 seconds because the server stream does not terminate on its own. Curl exiting with a timeout after printing events is **expected in this lab**, not a Gateway error.

Sample response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

id:0
event:tick
data:event-0
retry:3000

id:1
event:tick
data:event-1
retry:3000
~~~

Headers/formatting may vary slightly depending on encoder/server version; confirm multiple events arrive before the client times out.

Test the lab's cursor:

~~~bash
curl -N -i --max-time 3 \
  -H "Last-Event-ID: 5" \
  http://localhost:8080/api/events
~~~

The first event in this fixture has ID `6`. This is purely an illustrative offset check; production must replay real event payloads from an event store.

### 8.4. Testing WebSocket with websocat

If `websocat` is installed:

~~~bash
websocat -v ws://localhost:8080/ws/echo
~~~

Enter:

~~~text
hello
~~~

Output:

~~~text
echo: hello
~~~

Each line entered should produce one text frame and one echo frame. Plain `curl` is not a full WebSocket client; sending an HTTP GET without Upgrade does not prove WebSocket routing works.

### 8.5. Testing Endpoints Directly and Through the Gateway

Direct SSE:

~~~bash
curl -N --max-time 3 http://localhost:9081/api/events
~~~

SSE through Gateway:

~~~bash
curl -N --max-time 3 http://localhost:8080/api/events
~~~

Direct WebSocket:

~~~bash
websocat ws://localhost:9081/ws/echo
~~~

WebSocket through Gateway:

~~~bash
websocat ws://localhost:8080/ws/echo
~~~

Compare messages/events across both paths. The Gateway path must preserve the same semantics while Gateway route markers/metrics confirm traffic traversed the edge.

## 9. Automated Smoke Tests for Streams

The tests below run while both realtime-service and the Gateway are up. They verify **data actually arrives through the Gateway**, not just route definitions.

### 9.1. Test Dependencies

In the Gateway project, add test dependencies if not already present:

~~~xml
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
~~~

Spring WebFlux provides `WebTestClient`; `ReactorNettyWebSocketClient` is the client API for opening WebSocket sessions.

### 9.2. GatewayStreamSmokeTest.java

`gateway/src/test/java/demo/gateway/GatewayStreamSmokeTest.java`:

~~~java
package demo.gateway;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayStreamSmokeTest {

    private final WebTestClient http = WebTestClient.bindToServer()
            .baseUrl("http://localhost:8080")
            .build();

    @Test
    void sseEventsArriveThroughGateway() {
        FluxExchangeResult<ServerSentEvent> result = http.get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .returnResult(ServerSentEvent.class);

        StepVerifier.create(result.getResponseBody().take(2))
                .assertNext(event -> {
                    assertThat(event.event()).isEqualTo("tick");
                    assertThat(event.id()).isNotBlank();
                    assertThat(event.data()).isNotNull();
                })
                .assertNext(event -> {
                    assertThat(event.event()).isEqualTo("tick");
                    assertThat(event.id()).isNotBlank();
                })
                .verifyComplete(Duration.ofSeconds(5));
    }

    @Test
    void websocketFramesAreRelayedThroughGateway() {
        ReactorNettyWebSocketClient client =
                new ReactorNettyWebSocketClient();
        AtomicReference<String> reply = new AtomicReference<>();

        Mono<Void> conversation = client.execute(
                URI.create("ws://localhost:8080/ws/echo"),
                session -> session.send(Mono.just(
                                session.textMessage("hello")))
                        .then(session.receive()
                                .next()
                                .map(WebSocketMessage::getPayloadAsText)
                                .doOnNext(reply::set)
                                .then()));

        StepVerifier.create(conversation)
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        assertThat(reply.get()).isEqualTo("echo: hello");
    }
}
~~~

These smoke tests use fixed lab ports and require two running processes. In CI, replace them with dynamic ports/test fixtures and manage both servers' lifecycles inside the test harness. Never make a test suite depend on an external running Gateway without health/readiness preconditions.

### 9.3. Running the Tests

~~~bash
./mvnw -Dtest=GatewayStreamSmokeTest test
~~~

Expectations:

- The SSE test receives two `tick` events with IDs and data.
- The WebSocket test receives the text frame `echo: hello`.
- Tests complete within the specified timeout; streams are not buffered indefinitely.

If the SSE test receives response headers but no events, investigate upstream flushing, proxy buffering, codecs, and timeouts. If the WebSocket handshake succeeds without an echo, investigate handler receive/send, Gateway websocket routing, and client callbacks.

## 10. Security: Protecting Handshakes and Streams

Both SSE and WebSocket can carry private data. Long-lived connections do not make authentication/authorization any less critical.

### 10.1. WebSocket Origin Is Not Authentication

Browsers send `Origin` during the WebSocket handshake. WebFlux Gateway by default accepts only same-origin and handshakes without an Origin; cross-origin requests are rejected unless present in the allowlist.

Example allowing only two specific frontends:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          websocket:
            allowed-origins:
              - https://app.example.test
              - https://admin.example.test
~~~

Origin helps mitigate certain cross-site WebSocket hijacking attacks, but non-browser clients can set this header arbitrarily. **Never use Origin as identity or access control**; you must still authenticate the principal and authorize endpoints/topics.

When the Gateway sits behind an ingress/reverse proxy, check the public scheme/host observed by the Gateway. Configure forwarded headers only from trusted proxies; otherwise same-origin checks may mistakenly compare a public origin against an internal URI.

### 10.2. Browser WebSocket and EventSource Cannot Set Arbitrary Authorization Headers

Browser `WebSocket` and `EventSource` constructors lack a standard API to attach custom `Authorization: Bearer ...` headers. Common options:

- Secure session cookies for same-origin browsers; cookies must have appropriate `Secure`, `HttpOnly`, `SameSite`, and scope settings.
- A very short-TTL one-time connection ticket minted over HTTPS after authentication; the ticket is single-use and narrowly scoped.
- For SSE, use `fetch()` streaming if a custom Authorization header is required and you are willing to handle parsing/reconnection yourself.
- Native clients can use client APIs supporting Authorization headers on handshakes/requests.

Avoid placing long-lived access tokens in query strings (`?token=...`): URLs routinely appear in access logs, traces, monitoring, and browser history. If a browser WebSocket must use a ticket query parameter, make it short-lived, single-use, narrowly scoped, and redacted from logs.

### 10.3. Authenticate at Handshake, Authorize Every Action

- A WebSocket handshake is an HTTP request; the Security WebFilter chain can authenticate it before the Gateway upgrades the connection.
- SSE requests must also pass authentication/authorization before opening the response.
- Enforce permissions by tenant/resource/topic, not merely `authenticated()`.
- For WebSocket, authorize every inbound command by user/resource/action; a successful handshake does not authorize arbitrary messages.
- For SSE, subscribe only to streams the principal is authorized to read; never trust client-supplied user IDs/tenant IDs in queries or headers.
- When tokens/sessions expire, define how to close, re-authenticate, and reconnect; never assume an open connection automatically refreshes credentials.

### 10.4. CORS for SSE and Origin for WebSocket Are Distinct Mechanisms

Because SSE uses HTTP, cross-origin EventSource requires appropriate CORS response headers and browser credentials policies. WebSocket handshakes do not use CORS preflight like `fetch`; the Gateway checks Origin separately.

When using cross-origin cookie credentials:

- Allowlist specific origins only; never use wildcards with credentials.
- Configure `Access-Control-Allow-Credentials: true` only when genuinely needed.
- Cookies must satisfy SameSite/Secure rules for your browser topology.
- Test OPTIONS preflight if the frontend sends custom headers via `fetch()`.

CORS does not replace authentication; native clients and cURL are not bound by browser CORS policies.

## 11. Timeouts, Heartbeats, Buffering, and Resource Limits

### 11.1. End-to-End Timeouts

An SSE stream may stay open for minutes or hours. An overly short HTTP client response timeout, ingress idle timeout, or service mesh timeout can sever the stream even while the backend is healthy.

Check hop by hop:

| Hop | What to check |
| --- | --- |
| Browser/mobile network | Network changes, sleep/background policies, connection lifetime |
| CDN/ingress/reverse proxy | Idle timeout, response buffering, max connection duration |
| Spring Cloud Gateway | HTTP client response timeout, connection pool, graceful shutdown |
| Service mesh/load balancer | Idle timeout, connection draining, TCP keepalive |
| Realtime backend | Session timeout, server shutdown, resource limits |

WebFlux Gateway has `spring.cloud.gateway.server.webflux.httpclient.response-timeout`. Do not set one short global value and expect infinite SSE streams to work; configure per route type and Gateway version. If short APIs need tight timeouts while SSE needs long lifetimes, separate policies/routes or use dedicated Gateway profiles/instances.

### 11.2. SSE Buffering

If events only arrive in bursts every few dozen seconds:

1. Verify the backend actually emits events on schedule.
2. Check `Content-Type: text/event-stream`.
3. Use `curl -N` to eliminate curl buffering.
4. Check whether Nginx/CDN/service mesh buffers responses.
5. Check whether compression or response-body filters accumulate data before flushing.
6. Inspect proxy logs/packet timing to pinpoint which layer holds events.

`X-Accel-Buffering: no` is an Nginx-specific header; other proxies have their own configuration mechanisms. Never assume this header controls every CDN or load balancer.

Avoid applying `ModifyResponseBody`, local response caches, or filters that buffer the entire body on SSE routes. An infinite stream has no "complete body" to cache or transform like ordinary JSON.

### 11.3. WebSocket Frame Size and Ping

WebFlux Gateway 5.1 includes HTTP client WebSocket properties such as:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            websocket:
              max-frame-payload-length: 65536
              proxy-ping: true
~~~

These property names are illustrative for Gateway 5.1; verify exact properties against your running release. Frame sizes must match your contract and backend/ingress limits. Do not raise limits infinitely to avoid disconnects; large payloads belong in HTTP/object storage rather than giant WebSocket frames.

Protocol-layer ping/pong helps detect dead connections over certain paths. Applications may still need **application heartbeats** (e.g., JSON `{"type":"ping"}` / `{"type":"pong"}`) to verify the backend is actively processing messages. Do not confuse a TCP/WebSocket ping answered by a proxy with a healthy business service.

### 11.4. Backpressure and Resource Limits

Every open connection consumes sockets/file descriptors, buffers, state, and memory on both the Gateway and backend. At tens of thousands of connections, you need a dedicated capacity plan:

- Cap concurrent connections per tenant/client and per node.
- Cap message/frame size, event rates, and outbound queues.
- Never attach an unbounded `onBackpressureBuffer()` for slow consumers.
- Pick a policy per event type: drop old events, coalesce to the latest state, disconnect slow consumers, or persist for replay.
- Close sessions when clients stop reading or miss heartbeats per contract.
- Monitor heap/direct buffers, file descriptors, active sessions, and queue depths.

SSE progress updates can coalesce to the latest state; chat messages or audit events normally must not be dropped arbitrarily. Backpressure policies must reflect business semantics.

### 11.5. Do Not Retry Streams Like JSON Requests

Retries can help before a response or handshake is established if policy and semantics permit, but **you cannot safely replay a partially delivered stream**:

- SSE: the client reconnects and sends `Last-Event-ID`; the server replays from an event store.
- WebSocket: the client reconnects and sends a resume cursor/last acknowledged sequence at the application protocol layer.
- A write command over WebSocket needs a command ID/idempotency key to prevent duplicate execution when the client does not know whether the server processed it.

Never attach a global Retry filter to SSE/WebSocket routes. Never assume a CircuitBreaker filter monitors the health of individual events/frames inside an upgraded session.

## 12. Reconnect and Graceful Shutdown

### 12.1. SSE Reconnect

Browser `EventSource` automatically reconnects when a connection closes unexpectedly. If events carried an `id`, the browser sends `Last-Event-ID` on the next request. The server must:

- Replay retained events after that cursor.
- Never replay events exceeding the current principal's permissions.
- Handle expired/invalid cursors using a resync contract.
- Expect duplicate delivery; clients should handle events idempotently by event ID.
- Enforce reconnect rate limits/backoff during backend outages.

This lab merely increments a sequence to demonstrate the header; without an event store, **it does not guarantee replay of missed data**.

### 12.2. WebSocket Reconnect

The browser WebSocket API does not auto-reconnect. Clients must:

1. Handle close/error events.
2. Wait using backoff with jitter.
3. Open a new connection and re-authenticate.
4. Send a resume cursor/last acknowledged sequence if the protocol supports it.
5. Re-subscribe to topics the principal is still authorized for.
6. Deduplicate messages by ID if old messages can be redelivered.

Never retry immediately in a tight loop; an outage can cause thousands of clients to reconnect simultaneously. Use exponential backoff + jitter with a cap.

### 12.3. Gateway/Backend Deployments and Draining

A live WebSocket session cannot be migrated intact to another instance when a pod terminates. SSE streams also break when a process shuts down. Deployment plans should:

- Mark the instance unready to stop receiving new connections (readiness/drain) before termination.
- Give existing connections a bounded grace period.
- Emit valid reconnect/retry signals if your application protocol supports them.
- Let clients reconnect to healthy instances and resume from their cursor.
- Configure `spring.lifecycle.timeout-per-shutdown-phase` / termination grace appropriately, without assuming an infinite stream will finish within the grace period.
- Test rolling updates with active open connections and representative traffic.

Spring Boot supports graceful shutdown for embedded Reactor Netty/Tomcat/Jetty. Graceful shutdown gives in-flight requests a window to finish; it does not keep sessions open forever or migrate sessions to another pod.

## 13. Observability for Long-Lived Connections

Plain HTTP request metrics are not enough to understand streams. Measure:

| Metric/log | Meaning |
| --- | --- |
| Active SSE connections | Number of currently open response streams |
| Active WebSocket sessions | Number of currently open socket sessions |
| Handshake success/failure | Upgrade success rate, 401/403/5xx |
| Stream duration | How long connections stay open before closing |
| Events/frames sent and received | Data throughput |
| Bytes per connection | Bandwidth and payload size |
| Reconnect/resume count | Frequency of disconnects and recoveries |
| Close code/reason category | Network error, client close, server shutdown, policy |
| Slow-consumer/queue depth | Backpressure and memory risk |
| Last-Event-ID replay lag | Number of events/offsets remaining to replay |

### 13.1. Safe Tracing and Logging

- Attach trace/correlation IDs to handshakes and session contexts where the framework/application supports it.
- For long streams, consider a dedicated handshake span plus lifetime metrics; do not create a span per frame if cardinality/volume is too high.
- Never log cookies, Authorization tokens, one-time tickets, or full sensitive message payloads.
- Never use unbounded session IDs, user IDs, or topic IDs as Prometheus labels.
- Record close reasons in standardized categories rather than putting raw client text into metric labels.

### 13.2. Distinguishing Gateway Metrics From Application Metrics

The Gateway can measure route requests/handshakes and upstream latency. Only the business service knows which events were published/acknowledged, which messages were duplicates, and which clients processed them. Combine both:

~~~text
Gateway:
  route=realtime-websocket
  handshake=success
  connection_duration=...

Realtime service:
  session_opened=...
  messages_received=...
  messages_sent=...
  reconnect_resume=...
  slow_consumer_disconnect=...
~~~

Never conclude a stream is healthy solely because the Gateway returned handshake status 101 or SSE status 200.

## 14. Negative Tests and Troubleshooting

### 14.1. Test Matrix

| Test | How to run | Expected result |
| --- | --- | --- |
| SSE through Gateway | `curl -N` or EventSource to `/api/events` | Receives multiple events, increasing IDs |
| WebSocket through Gateway | Open `/ws/echo`, send text | Receives echo frame |
| Wrong path | Call `/unknown/stream` | Does not route to realtime service |
| Wrong method on SSE | Send POST to `/api/events` | Backend/Gateway rejects; no stream created |
| WebSocket without Upgrade | Send plain GET to `/ws/echo` | No 101 handshake |
| Off-allowlist Origin | Browser from disallowed origin opens socket | Gateway rejects handshake, typically 403 |
| Client closes SSE | Call `EventSource.close()` | Backend stream cancels/cleans up |
| Client closes WebSocket | `socket.close(1000)` | Backend session completes and releases state |
| Backend restart | Restart realtime-service while stream open | Connection drops; client reconnects per contract |
| Gateway restart | Drain/restart Gateway | Client reconnects, SSE resumes if event store exists |
| Buffering proxy | Toggle response buffering on test proxy | Detects whether events are batched |
| Slow consumer | Read slowly or stop reading | Queue/connection handled per policy, memory bounded |
| Oversized payload | Send frame exceeding max size | Limited/rejected per config |

### 14.2. Quick Troubleshooting

| Symptom | Possible cause | Check |
| --- | --- | --- |
| WebSocket returns 404 | Wrong route predicate or wrong backend path | `Path`, route ID, `/ws/echo` mapping |
| WebSocket returns 403 | Origin not allowlisted or Security rejected | Actual Origin, forwarded host/scheme, authentication |
| 101 handshake but no echo | Handler not receiving/sending, or client callback exits early | `session.receive()`, `session.send()`, Network Frames |
| 400/426 handshake | Request missing Upgrade headers or hit HTTP route by mistake | Client using `ws://`/`wss://`, route URI scheme |
| WebSocket disconnects after fixed idle period | Proxy/LB idle timeout | Compare disconnect time with heartbeat interval and idle timeout |
| SSE 200 but no events visible | Backend not emitting or response buffered | `curl -N`, event controller, proxy buffering |
| SSE events arrive in batches | Compression/proxy response buffering | `X-Accel-Buffering`, CDN/ingress config |
| SSE disconnects after N seconds | Response timeout/idle timeout/connection max age | Gateway HTTP client, ingress, service mesh |
| EventSource reconnects but misses events | No replay store or broken cursor handling | `Last-Event-ID`, retention, partition/offset |
| EventSource reconnects too aggressively | Low retry delay or missing backoff | SSE `retry`, proxy outage, client network |
| WebSocket reconnect duplicates commands | Client retries command without an ID | Command idempotency/deduplication |
| One pod receives all sockets | Long-lived sessions stick to chosen instance | LoadBalancer distribution at handshake, connection counts |
| Old sessions cut when one pod deploys | Rolling shutdown/drain | Readiness, grace period, reconnect/resume |
| 502/503 when selecting `lb:ws://` | Discovery has no instances or WS scheme not routed | Discovery client, service ID, LoadBalancer dependency |
| Browser cross-origin WebSocket fails | Allowed origins mismatch | Exact origin including scheme/host/port |
| Cross-origin SSE fails | Wrong CORS/credentials policy | OPTIONS, ACAO, credentials, cookie SameSite |
| Gateway memory grows over time | Unbounded buffers, session leaks, slow consumers | Heap/direct memory, queue depth, cleanup hooks |
| Metrics show 200/101 but users receive no data | Measuring only handshake/response status | Event/frame counters, stream duration, browser trace |

### 14.3. Layered Investigation Workflow

1. Check client API/URL and scheme (`http`, `https`, `ws`, `wss`).
2. Inspect handshake/HTTP response headers.
3. Confirm the actual Gateway route ID and URI scheme.
4. Call the backend directly to isolate Gateway issues from handler bugs.
5. Check Origin, Security, cookies/tokens, and subscription permissions.
6. Measure time to first event/frame and intervals between sends.
7. Check timeouts/buffering/heartbeats across every proxy hop.
8. Inspect close reasons, cancellation, and cleanup on the backend.
9. Verify replay cursor/deduplication after reconnect.
10. Re-run positive/negative tests after updating routes or timeouts.

## 15. Extension Exercises

### Exercise 1 — Replace Static Backend With Service Discovery

Register realtime-service in a discovery registry with at least two instances. Change routes to:

~~~yaml
- id: realtime-sse
  uri: lb://realtime-service
  predicates:
    - Path=/api/events

- id: realtime-websocket
  uri: lb:ws://realtime-service
  predicates:
    - Path=/ws/**
~~~

Open multiple WebSocket sessions and log which instance was chosen at handshake. Prove subsequent frames stay on that session; on reconnect, the client may route to another instance.

### Exercise 2 — SSE Replay From an Event Store

Replace `Flux.interval` with a retention-backed event store:

- Every event has a durable ID.
- Clients send `Last-Event-ID`.
- Server replays events after the cursor, then switches to live tailing.
- If the cursor falls outside retention, the server tells the client to resync a snapshot.
- Two Gateway/backend instances can replay from the same event log.

Test disconnecting between events 10 and 13; on reconnect, the client must receive the missed events in order or receive a resync signal.

### Exercise 3 — WebSocket Resume and Deduplication

Design a JSON protocol:

~~~json
{"type":"command","commandId":"cmd-001","sequence":42,"payload":{"text":"hello"}}
~~~

The backend returns an acknowledgment with the same `commandId`. When the client reconnects and resends an unacknowledged command, the backend deduplicates by principal + command ID and avoids executing side effects twice.

### Exercise 4 — Cross-Origin Security

Run the UI on a different origin, e.g., `http://localhost:3000`:

- Allowlist that exact origin in WebSocket `allowed-origins`.
- Configure CORS for SSE if using cross-origin EventSource.
- Verify requests from a third origin are rejected.
- Test requests without an Origin from a native test client.
- Prove an Origin allowlist does not replace JWT/session authorization.

### Exercise 5 — Testing Timeouts and Heartbeats

Configure a low idle timeout on a test reverse proxy. Compare:

- SSE without heartbeats.
- SSE with comment heartbeats.
- WebSocket without app heartbeats.
- WebSocket with app-level ping/pong messages.

Measure disconnect time, reconnect counts, and bytes transferred. Pick a heartbeat interval smaller than the idle timeout with a safety margin, without spamming heartbeats excessively.

### Exercise 6 — Rolling Deploy With Open Connections

Open multiple SSE/WebSocket sessions, then perform a rolling restart of realtime-service:

- Measure how many sessions drop.
- Verify readiness/draining.
- Verify reconnect/backoff.
- Verify SSE replay and WebSocket resume.
- Ensure no business commands are lost or processed twice.

Never use a production environment without an approved load/fault test plan.

### Exercise 7 — Slow Consumers and Backpressure

Create a client reading slower than the server emits:

- Measure queue depth, memory, and disconnect timing.
- Compare drop/coalesce/disconnect/persist strategies.
- Prove queues remain bounded.
- Pick distinct policies for progress, notification, chat, and audit events.

## 16. Self-Check Questions

**1. How do SSE and WebSocket differ in transmission direction?**

SSE is primarily server → client over an HTTP response; WebSocket supports bidirectional messaging after an HTTP Upgrade.

**2. Which URI scheme does the Gateway use to proxy SSE?**

SSE uses HTTP routes `http://` or `lb://`; the response has media type `text/event-stream`.

**3. Which URI scheme does the Gateway use to proxy WebSocket?**

Use `ws://` or `wss://`. With load balancing, you can use the `lb:ws://service-id` prefix.

**4. Why is a 101 handshake insufficient to prove WebSocket works?**

101 only confirms the upgrade. You must send/receive frames and verify session lifetime/close behavior.

**5. Why is an SSE 200 response insufficient to prove streaming?**

The server could return headers and buffer the body. You must confirm multiple events flush to the client over time.

**6. How does browser EventSource reconnect?**

It automatically reconnects per its retry delay and sends `Last-Event-ID` if previous events had IDs.

**7. Is incrementing a sequence after Last-Event-ID real replay?**

No. The server must read actual events from an event store/broker within retention; merely incrementing a sequence number does not recover lost payloads.

**8. Can browser WebSocket set arbitrary Authorization headers?**

Not via the standard constructor. You can use session cookies or short-lived one-time tickets; authentication and authorization are still required.

**9. Does an Origin allowlist replace authentication?**

No. Origin validates the browser handshake source, not identity; native clients can set any Origin they want.

**10. Why shouldn't you use a Retry filter to recover a WebSocket session?**

Retry cannot replay partially sent frames or recreate session state. Clients need reconnection plus application-level resume/deduplication.

**11. Why doesn't `lb:ws://` load balance every message?**

LoadBalancer picks a backend at handshake time; the connection then stays pinned to that instance until the session closes.

**12. Why are heartbeats needed?**

Heartbeats help detect or prevent certain idle timeouts; they do not prove the business handler is healthy and must be tuned below the shortest timeout along the path.

**13. Why must frame size and outbound queues be bounded?**

To protect memory, direct buffers, and file descriptors when clients are slow or send oversized payloads.

**14. Does graceful shutdown keep WebSocket sessions open forever?**

No. It only grants existing requests/sessions a bounded grace period; clients still need reconnect/resume when the process exits.

**15. Do cross-origin SSE and cross-origin WebSocket use the same CORS mechanism?**

No. SSE is HTTP and uses CORS; the Gateway enforces Origin separately for WebSocket handshakes.

## 17. References

1. [Spring Cloud Gateway 5.1 — Global Filters / WebSocket Routing Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): how WebFlux Gateway detects `ws`/`wss`, uses `lb:ws://`, and configures Origin.
2. [Spring Cloud Gateway 5.1 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html): WebSocket allowed origins, response timeout, max frame payload length, and proxy ping.
3. [Spring Cloud Gateway 4.3 — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/global-filters.html): comparing 4.x behavior.
4. [Spring Framework — WebFlux WebSocket](https://docs.spring.io/spring-framework/reference/web/webflux/websocket.html): `WebSocketHandler`, `WebSocketSession`, send/receive streams, and WebSocket client.
5. [Spring Framework — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): reactive return types and `Flux<ServerSentEvent<?>>`.
6. [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): grace period and `spring.lifecycle.timeout-per-shutdown-phase`.
7. [WHATWG — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html): event format, `id`, `retry`, reconnect, and `Last-Event-ID`.
8. [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): EventSource, browser reconnect, and event listeners.
9. [MDN — WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket): browser WebSocket lifecycle, send/receive, and close.
10. [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html): opening handshake, frames, control frames, and close behavior.

**Remember:** SSE is one-way HTTP response streaming; WebSocket is a bidirectional session after an HTTP Upgrade. WebFlux Gateway proxies SSE over HTTP routes and WebSocket over `ws://`/`wss://` (or `lb:ws://` with LoadBalancer). Verification must observe **actual events/frames reaching the client**, rather than stopping at HTTP 200/101. Long-lived connections require proper Origin/auth, heartbeats shorter than idle timeouts, backpressure/size limits, reconnect/resume, and graceful draining. For SSE, `Last-Event-ID` is only meaningful when the server replays real events from a store; for WebSocket, clients need protocol-level cursors/acknowledgments and command deduplication. This is a joint responsibility between the application and the Gateway, not something a single route filter can guarantee alone.

## 18. Pre-Production Checklist for Streams

### Routing and Transport

- [ ] SSE route uses an HTTP URI and returns `Content-Type: text/event-stream`.
- [ ] WebSocket route uses `ws://`/`wss://`; both handshake and frames are verified.
- [ ] If using discovery, service instance list and `lb:ws://` route are properly configured.
- [ ] No unintended path rewrite/strip; backend mapping matches public path.
- [ ] Generic retry/cache/body-transform filters are not applied to stream routes.
- [ ] SockJS fallback (if used) has matching HTTP and WebSocket routes.

### Security

- [ ] WebSocket Origin allowlist is specific; Origin is never treated as authentication.
- [ ] Dedicated SSE CORS policy exists if cross-origin.
- [ ] Authentication runs before handshake/stream; subscriptions/topics are authorized.
- [ ] Browser tokens never appear in URLs or logs.
- [ ] Cookies, one-time tickets, and token expiry have a reconnect/re-auth contract.
- [ ] Public edge TLS and upstream TLS/mTLS are verified; no insecure trust managers.
- [ ] Forwarded headers are trusted only from controlled proxies.

### Reliability and Capacity

- [ ] Heartbeat interval is shorter than the shortest idle timeout along the path.
- [ ] Gateway response timeout does not sever SSE via an overly short global value.
- [ ] SSE event store provides retention/cursors if replay is required.
- [ ] WebSocket commands carry IDs/acks/deduplication if they cause side effects.
- [ ] Frame size, event rate, active connections, and outbound queues are bounded.
- [ ] Slow consumers have an explicit policy; no unbounded buffers.
- [ ] Reconnects use exponential backoff + jitter with a cap.
- [ ] Rolling deploys use readiness/draining and client resume/reconnect.
- [ ] Tested backend/Gateway restarts with active open connections.

### Observability and Testing

- [ ] Track active connections, duration, events/frames, bytes, reconnects, and close reasons.
- [ ] Dashboards exist per route, service instance, and deployment revision.
- [ ] Never log secrets, tokens, cookies, or sensitive payloads.
- [ ] Both positive and negative tests exist for SSE/WebSocket.
- [ ] Tests verify multiple events/frames arrive through the Gateway.
- [ ] Tested invalid Origin, failed auth, and client disconnects.
- [ ] Tested slow consumers, timeouts, proxy buffering, and rolling shutdowns.
- [ ] CI verifies the number of executed tests, not just build success.

## 19. Compatibility and Extension Notes

### 19.1. SockJS

If the application uses SockJS as a fallback when WebSocket is unavailable, you need HTTP routes for SockJS info/polling endpoints and WebSocket routes for upgrade endpoints. Do not configure a single `ws://` route and expect it to handle all HTTP transport fallbacks.

### 19.2. WebFlux Gateway vs. Web MVC

This lab uses **Gateway Server WebFlux**. Gateway Server Web MVC configures WebSocket, buffering, and backpressure differently; never copy `server.webflux.*` properties to `server.webmvc.*`. For Web MVC, consult its dedicated documentation on buffer/session limits and how the container handles ping/pong.

### 19.3. Metrics in the Lab

Gateway route metrics can be explicitly enabled in the lab profile:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          metrics:
            enabled: true
~~~

Actuator `metrics` must be protected in real environments. Gateway request metrics still do not replace business event/frame/session counters inside realtime-service.

### 19.4. Sample Graceful Shutdown

A grace period can be explicitly configured for the lab:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

`30s` is only an illustrative value. Choose the duration based on termination grace, drain duration, and reconnect policies. Do not set an infinite grace period to hold old connections; rolling deploys need a way to recover after sessions close.

### 19.5. TLS at Public Edge and Upstream

Production clients connect to:

~~~text
https://realtime.example.test/api/events
wss://realtime.example.test/ws/echo
~~~

The Gateway terminates TLS at the public edge using a valid certificate. If upstream also requires TLS/mTLS, routes use `https://`/`wss://` with trust/key material managed through SSL bundles or appropriate client configuration. Never disable certificate verification to work around handshake errors.

**The lab is complete when:** you can open `/demo`, observe increasing SSE events, send a WebSocket message and receive its echo, verify routing through the Gateway via DevTools/metrics, and explain how the system recovers when connections drop.
