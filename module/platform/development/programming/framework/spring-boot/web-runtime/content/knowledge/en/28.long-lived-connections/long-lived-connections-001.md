# Distinguishing HTTP Streaming, Server-Sent Events, and WebSocket

When a web page needs to see data before the server finishes its entire job, three techniques are commonly mentioned: **HTTP streaming**, **Server-Sent Events (SSE)**, and **WebSocket**. They can all keep a connection open for a long time, but they are **not at the same conceptual level** and **do not replace each other in every situation**.

- **HTTP response streaming** is a way for the server to send the body of an HTTP response in parts over time instead of preparing the whole response before returning it. The data can be raw bytes, text, NDJSON, files, or an application-specific format. The client must know how to split the chunks to make sense of them.
- **SSE** is **an event protocol built on top of HTTP response streaming**, using `Content-Type: text/event-stream`, the fields `event:`, `data:`, `id:`, `retry:`, and a browser `EventSource` client with a built-in reconnection mechanism. At the application level, the event stream flows **from server to client**.
- **WebSocket** is a **bidirectional, full-duplex** communication protocol after a connection is established via a handshake. Both the client and the server can send text/binary messages at any time. It does not automatically provide authentication, business acknowledgements, replay, or reconnection.

Therefore, the question should be **in which direction does the application need to transmit information, in what format, with what level of guarantees, and through which proxy infrastructure?** rather than just "which technology is more real-time?".

This lesson uses **Spring Boot 3.x, Spring MVC, Java 17+**, with a demo running all three techniques in the same application and a comparison section with **Spring WebFlux**. Properties and server details may differ in other major Spring Boot versions.

## 1. Learning Objectives

After completing this lesson, you will be able to:

- Explain HTTP response body streaming, SSE, and WebSocket in terms of **transport**, **message format**, **direction**, and **lifecycle**.
- Read HTTP headers, the SSE wire format, and the WebSocket handshake/connection states.
- Build NDJSON streaming with `StreamingResponseBody`, SSE with `SseEmitter`, and a WebSocket echo endpoint with `TextWebSocketHandler`.
- Use the browser `fetch()` streaming reader, `EventSource`, and `WebSocket`; test NDJSON/SSE with `curl -N`.
- Distinguish **streamed bytes**, **event delivery**, **message boundaries**, **heartbeats**, **reconnect**, **replay**, and **backpressure**.
- Design timeouts, proxy buffering, TLS, CORS/Origin/CSRF, connection limits, and access control for long-lived connections.
- Recognize why opening many SSE/WebSocket connections does not automatically make a system scale well.
- Choose the right solution for progress logs, stock prices, notifications, chat/collaboration, file downloads, and binary data.
- Test scenarios including mid-stream connection drops, server restarts, slow clients, multiple replicas, and rolling deployments.

## 2. A Comparison Table Before Diving Deep

| Criterion | HTTP response streaming | SSE | WebSocket |
| --- | --- | --- | --- |
| Nature | HTTP response sent progressively in chunks/frames | **HTTP streaming with event standard** `text/event-stream` | Bidirectional message protocol after handshake |
| Direction in common examples | Server → client within one response; HTTP still supports request body streaming in other flows | Server → client; client commands are typically sent via separate HTTP requests | Client ↔ server over the same channel |
| Data types | Arbitrary bytes; NDJSON, text, CSV, video, files | UTF-8 text via `data:`/`event:`, which can carry serialized JSON as text | Text and binary messages |
| Message framing | Application-defined: newline, length prefix, boundary... | The SSE parser dispatches an event upon encountering a blank line | WebSocket has message framing at the protocol layer |
| Browser API | `fetch()` + `ReadableStream` or an equivalent stream reader | `EventSource` | `WebSocket` |
| Built-in auto-reconnect | No; handled by the application | `EventSource` has automatic reconnect | No; handled by the application |
| Recovering missed data | Custom offset/range/cursor design | `id`/`Last-Event-ID` helps request resume; the server **must provide its own replay store** | Custom seq/ack/replay design |
| Proxy/cache | Follows HTTP; subject to buffering | Follows HTTP; requires disabling buffering and improper caching | Must allow Upgrade handshake / corresponding transport |
| Per request/connection | Finite or long-lived HTTP request | A long-lived HTTP response; reconnect opens a new request | A long-lived socket messaging channel |
| Best suited for | Large downloads, NDJSON data, incremental computation progress | Event notifications, dashboards, status tracking | Chat, games, collaboration, bidirectional interactive operations |
| Notable limitations | Client must handle parsing and resume itself | Cannot send raw binary directly; browser `EventSource` uses GET and cannot easily customize headers | Managing bidirectional connections, message security, and state/distribution is more complex |

**Subset relationship:** SSE **is a form of HTTP streaming**. Placing SSE and HTTP streaming side by side for comparison is shorthand for comparing **arbitrary HTTP streaming** with **SSE-formatted HTTP streaming**. WebSocket is not simply "better HTTP streaming": the application gets a different protocol along with different responsibilities.

## 3. Why Does Incremental Delivery Matter?

### 3.1. Standard HTTP Response

```text
Client GET /report
            |
            v
Server computes full report (5 seconds)
            |
            v
HTTP 200 + complete body
            |
            v
Client processes after response completes
```

For large or incrementally generated content, the client must wait until the last byte before having enough data if the code loads the entire body prior to processing. Even though the HTTP stack can read data incrementally, application code calling `response.json()` typically receives the result only once **the entire body has completed and been parsed**.

### 3.2. HTTP Response Streaming

```text
Client GET /stream/ndjson
            |
            v
HTTP 200 + headers
            |
            +--> {"seq":1,"kind":"snapshot"}\n
            |
         800 ms
            |
            +--> {"seq":2,"kind":"snapshot"}\n
            |
         800 ms
            |
            +--> ...
            |
            +--> end of response
```

Each NDJSON line is a **complete** JSON object delimited by a newline. The client can parse each line as soon as enough bytes arrive without waiting for the body to end. However, TCP segments and HTTP chunks **do not necessarily align** with JSON line boundaries: a single object may be split across multiple reads, or multiple objects may be coalesced into a single read. The parser must **buffer incomplete portions**.

**Streaming does not mean fixed "HTTP chunked".** With HTTP/1.1, the server can use `Transfer-Encoding: chunked` when Content-Length is unknown. With HTTP/2/3, data is sent as DATA frames of the respective protocol; the application still reads the response body incrementally. Do not manually set `Transfer-Encoding: chunked` in a controller to try to force streaming to work.

### 3.3. SSE Is a Stream with a Standard Event Syntax

```text
Client EventSource("/events")
            |
            v
GET /events
Accept: text/event-stream
            |
            v
HTTP 200 Content-Type: text/event-stream
            |
            +--> event: tick
            |    id: 1
            |    retry: 2000
            |    data: tick-1
            |
            |    [a blank line => dispatch event]
            |
            +--> event: tick
            |    id: 2
            |    data: tick-2
            |
            +--> ...
```

SSE is still an HTTP response; `EventSource` interprets the content according to field rules and automatically dispatches corresponding `MessageEvent` objects. When the socket breaks, the browser usually attempts to reconnect. However, the server must **keep an event history** if you want the client to actually receive missed events.

### 3.4. WebSocket Establishes a Bidirectional Message Channel

```text
Browser                                  Spring Boot
   |                                          |
   | HTTP/1.1 GET /ws/echo                    |
   | Upgrade: websocket                       |
   |----------------------------------------->|
   |        101 Switching Protocols           |
   |<-----------------------------------------|
   |                                          |
   |   WebSocket text message: "hello"        |
   |----------------------------------------->|
   |   WebSocket text message: "echo: hello"  |
   |<-----------------------------------------|
   |   text/binary messages both ways ...     |
   |<---------------------------------------->|
   |              Close handshake             |
   |<---------------------------------------->|
```

This is the common **WebSocket over HTTP/1.1** handshake. HTTP/2 has an extended CONNECT mechanism for WebSocket when supported by client/server/proxy, though not every Boot/ingress deployment supports it. Once upgraded, data messages are no longer independent HTTP responses like SSE.

## 4. HTTP Streaming: Concepts and Common Formats

### 4.1. Raw Bytes and StreamingResponseBody

In Spring MVC, `StreamingResponseBody` lets the application write directly to the response `OutputStream` without building the entire body upfront. The handler returns a callback executed via Servlet asynchronous request processing; `write`/`flush` calls can cause bytes to be transmitted incrementally as long as downstream layers do not buffer them.

Use it when:

- Generating a large CSV/export record by record;
- Returning a file or report generated incrementally;
- Returning data in a custom streaming format;
- Returning NDJSON when the client needs to process each object as it arrives.

**Do not assume** that every `flush()` in Java corresponds immediately to one `reader.read()` in the browser. There can be servlet buffers, gzip, reverse proxy buffering, TLS records, HTTP/2 frames, network coalescing, and browser buffering.

### 4.2. NDJSON: One JSON Object per Line

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson
Cache-Control: no-store
```

Illustrative body:

```jsonl
{"seq":1,"kind":"snapshot"}
{"seq":2,"kind":"snapshot"}
{"seq":3,"kind":"snapshot"}
```

The **newline-delimited JSON** format allows line-by-line parsing. It differs from a single JSON array:

```json
[{"seq":1},{"seq":2},{"seq":3}]
```

If client code calls `await response.json()`, it does not automatically understand individual NDJSON lines; you typically need `ReadableStream`, `TextDecoder`, and a buffer up to the newline. By contrast, a regular JSON array requires complete data or a specialized incremental JSON parser.

Other stream types exist such as `text/plain` log lines, `multipart/mixed`, `application/octet-stream`, file/range streams, or custom length-prefixed protocols. Because HTTP streaming does not define universal event semantics, **both sides must agree on framing**.

### 4.3. HTTP Has Request Streaming, Which Differs from Server Push

A client can upload a request body as a stream (for example, a file or incrementally generated data), and the server can also stream the response. However, these are still HTTP messages with request/response semantics. Do not say "HTTP only goes one way": what is accurate is that **a specific response stream flows from server to client**, whereas SSE standardizes only the server→client direction at the event API level.

### 4.4. When Keeping a Stream Open Is Unnecessary

If the backend can return the result in tens of milliseconds with a small payload, a regular JSON response is easier to cache, test, and observe. Streaming creates a long-lived request lifecycle, making timeouts, retries, rate limits, and CPU management harder if it delivers no practical value.

## 5. SSE: Protocol Structure and EventSource

### 5.1. Content-Type and UTF-8

An SSE response uses `Content-Type: text/event-stream`, with UTF-8 text content. An event is a group of lines terminated by a **blank line**. Common fields:

| Field | Meaning |
| --- | --- |
| `data:` | Text payload; multiple data lines are joined with a newline |
| `event:` | Event type name; the client listens via `addEventListener` |
| `id:` | Event ID remembered by the browser to send back upon reconnect |
| `retry:` | Suggested retry delay in **milliseconds**; must be a valid integer |
| `: comment` | Comment/heartbeat; the browser does not dispatch it as an application event |

Raw stream example:

```text
: heartbeat

id: 100
event: status
data: {"jobId":42,"state":"RUNNING"}

id: 101
event: status
data: {"jobId":42,"state":"DONE"}

```

A `status` event is dispatched after the blank line, not immediately when the parser reads the `data:` line. If the payload spans multiple lines:

```text
event: notice
data: First line
data: Second line

```

The browser sees `event.data` equal to the string `"First line\nSecond line"`. When sending multiline JSON, ensure each line is properly formatted according to SSE rules rather than writing raw multiline JSON arbitrarily into the stream.

### 5.2. EventSource API

In the browser:

```javascript
const source = new EventSource("/events");

source.addEventListener("tick", (event) => {
  console.log(event.lastEventId, event.data);
});

source.onerror = () => {
  console.log("SSE temporarily interrupted");
};

// When updates are no longer needed:
source.close();
```

`EventSource` automatically manages the GET connection, parses `text/event-stream`, dispatches events, and by default attempts to reconnect when the connection is lost/closed under conditions defined by the standard. The browser can stop reconnecting when the server returns a status such as `204 No Content` or when JavaScript calls `close()`. Do not write logic assuming every HTTP status or redirect results in the same retry behavior.

With native `EventSource`, the client cannot proactively send arbitrary messages back to the server over the same stream. A "cancel job" button can call `fetch("/jobs/42/cancel", {method:"POST", ...})`, while job results are emitted over SSE. This is a common combination that is simpler than WebSocket when the client only sends infrequent actions.

### 5.3. Last-Event-ID Does Not Automatically Create Reliability

If the browser has received `id: 105`, upon reconnecting it can send:

```http
Last-Event-ID: 105
```

The server can read that header and **query an event store** to send events after that ID. However, `SseEmitter` does not automatically persist events to a database and does not replay automatically. If events are only sent from RAM, a restart or routing to another replica can cause missed data.

To guarantee resume behavior, you must design:

1. Ordered/meaningful IDs within a stream, scoped appropriately to user/job/tenant.
2. An event store or durable log (database, Kafka, Redis Streams...) retaining events for a sufficient window.
3. Server authentication and authorization of the sender of `Last-Event-ID` before replaying.
4. Determining the missing range and re-sending **only data the user is permitted to view**.
5. Client handling of duplicates or gaps via IDs and idempotency.
6. A clear reset/full-resync signal to the client when history has been purged.

**SSE does not guarantee "exactly once delivery" by default.** Reconnection can cause duplicate or missed events unless persistence and deduplication are designed.

### 5.4. Heartbeat for SSE Connections

Proxies/load balancers often cut idle connections after a timeout. SSE can periodically send a `: heartbeat` comment. It does not alter business events, but generates traffic to keep the network path alive and detect client disconnects earlier.

The heartbeat interval must match proxy idle timeouts and connection overhead. Sending too frequently across hundreds of thousands of clients increases bandwidth and CPU usage; sending too infrequently allows a proxy to disconnect before the next server event. Measure on the real path.

## 6. WebSocket: A Bidirectional Message Channel

### 6.1. Handshake and States

In `ws://` or `wss://` deployments, the browser requests a WebSocket connection via JavaScript:

```javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.onopen = () => socket.send("hello");
socket.onmessage = (event) => console.log(event.data);
socket.onerror = () => console.log("Socket error");
socket.onclose = (event) => console.log(event.code, event.reason);
```

For public websites using HTTPS, WebSocket should also use **`wss://`**. Browsers can block mixed content if an HTTPS page opens an insecure `ws://` connection. Handshake URLs can be affected by context paths, reverse proxies, and public host/ports.

Browser `WebSocket.readyState` values include `CONNECTING`, `OPEN`, `CLOSING`, `CLOSED`. Calling `send()` before `OPEN` can fail; do not queue every message into an unbounded array while the socket is disconnected.

### 6.2. Text and Binary Messages

WebSocket provides **messages** with API-level boundaries, unlike a raw HTTP byte stream. The browser can send text, `ArrayBuffer`, or `Blob`; the server supports text/binary handlers. However, the WebSocket protocol **does not define a business schema**: if using JSON, you must define `type`, `id`, `payload`, and error/ack semantics yourself.

One WebSocket message may be split into multiple **frames** on the wire protocol; the API layer typically presents the complete message to the application. Do not assume one TCP packet equals one WebSocket frame or one business message.

### 6.3. WebSocket Does Not Automatically Reconnect or Replay

When the network drops or the server restarts, a browser WebSocket typically transitions to `CLOSED`; the app must handle reconnection, backoff with jitter, re-authentication, re-subscription, and state recovery. A new socket **does not remember** the subscriptions or messages of the old socket. If durable delivery is required, design IDs/acks, storage, and a mechanism to fetch missed items.

### 6.4. Ping/Pong and Heartbeats

The WebSocket protocol has `Ping`/`Pong` control frames to check connection health. Server/client libraries may manage ping/pong; **the browser WebSocket API does not allow JavaScript to send arbitrary Ping control frames**. If you want an application-level heartbeat, you can define a JSON message such as `{"type":"ping"}` with a `pong` response, but distinguish it from protocol-level WebSocket ping/pong. Proxy idle timeouts may still require regular heartbeats.

### 6.5. When Is WebSocket Worth Using?

- Bidirectional chat with frequent messages;
- Real-time collaborative document editing, multiplayer games;
- Continuous client commands or actions where the server must respond/push updates immediately;
- Need for binary messages or a custom message protocol;
- A complex subscription channel with many command/interaction types.

In return, WebSocket introduces harder **connection state**, message-level permissions, backpressure, reconnect, heartbeats, broker/routing, and lifecycle management. For a dashboard that only needs server-pushed updates, SSE is usually simpler.

## 7. Spring Boot MVC Java 17+ Project Demonstrating All Three

A single application serving:

- `GET /stream/ndjson`: 5 JSON lines sent progressively via HTTP streaming.
- `GET /events`: 5 SSE `tick` events with `id` and `retry`.
- `GET /ws/echo`: WebSocket echo where the server replies to each text message.
- `GET /`: an HTML page to test all three in the browser.

To keep the demo **easy to verify without a database**, the data is simply sequence numbers from 1 to 5. There is no authentication in the sample app; production must add authorization, TLS, and resource limits.

### 7.1. Initializing Spring Boot 3.x

From [Spring Initializr](https://start.spring.io/), generate a Gradle/Groovy, Java 17+, **Spring Boot 3.x** project with the **Spring Web** and **WebSocket** dependencies. In the `build.gradle` generated by Initializr, the core dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is **the dependencies block**, not a standalone complete `build.gradle`; Initializr generates plugins, repositories, version management, and the Gradle Wrapper. For Boot 4.x, check the corresponding starter names and Spring Framework versions; do not mix versions.

Structure:

```text
src/main/
  java/demo/
    LongConnectionsApplication.java
    StreamConfiguration.java
    StreamController.java
    EchoHandler.java
    WebSocketConfiguration.java
  resources/
    application.properties
    static/index.html
```

### 7.2. LongConnectionsApplication.java

File `src/main/java/demo/LongConnectionsApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LongConnectionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(LongConnectionsApplication.class, args);
    }
}
```

`@SpringBootApplication` in package `demo` scans the controller, handler, and configuration beans below. Neither Spring Security nor reactive dependencies are required to run this MVC demo.

### 7.3. StreamConfiguration.java: Bounded Executor

Spring MVC streaming requires asynchronous request handling. Writing the response to the Servlet `OutputStream` is still **blocking I/O**, even though the handler returns early. Therefore, production must use a properly configured `AsyncTaskExecutor` instead of trusting a default unbounded executor to always be safe.

File `src/main/java/demo/StreamConfiguration.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class StreamConfiguration {

    @Bean
    ThreadPoolTaskExecutor streamExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("stream-demo-");
        executor.initialize();
        return executor;
    }

    @Bean
    WebMvcConfigurer mvcAsyncConfigurer(
            ThreadPoolTaskExecutor streamExecutor) {

        return new WebMvcConfigurer() {
            @Override
            public void configureAsyncSupport(
                    AsyncSupportConfigurer configurer) {

                configurer.setTaskExecutor(streamExecutor);
                configurer.setDefaultTimeout(30_000L);
            }
        };
    }
}
```

This is a **lab configuration with a finite task capacity**, not complete capacity planning. The demo shares the executor between the SSE producer and MVC async writes; more connections than the pool can handle can fill or reject the queue and increase latency. In production, separate executors/event loops appropriately, configure connection limits, bounded queues, metrics, and rejection handling. Even with a bounded executor, each streaming response still consumes a socket, buffers, and proxy resources.

`ThreadPoolTaskExecutor` has its lifecycle managed by Spring when declared as a bean. `configurer.setTaskExecutor` is the MVC configuration point for async tasks such as `StreamingResponseBody`. Returning reactive types on Spring MVC also requires an executor to handle blocking writes.

### 7.4. StreamController.java: NDJSON and SSE

File `src/main/java/demo/StreamController.java`:

```java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class StreamController {

    private final ThreadPoolTaskExecutor executor;

    public StreamController(ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    @GetMapping(
            path = "/stream/ndjson",
            produces = "application/x-ndjson")
    public StreamingResponseBody ndjson(HttpServletResponse response) {
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader("X-Accel-Buffering", "no");

        return outputStream -> {
            for (int i = 1; i <= 5; i++) {
                String line =
                        "{\"seq\":" + i + ",\"kind\":\"snapshot\"}\n";
                outputStream.write(
                        line.getBytes(StandardCharsets.UTF_8));
                outputStream.flush();

                try {
                    Thread.sleep(800);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        };
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(HttpServletResponse response) {
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader("X-Accel-Buffering", "no");

        SseEmitter emitter = new SseEmitter(30_000L);

        executor.execute(() -> {
            try {
                for (int i = 1; i <= 5; i++) {
                    emitter.send(
                            SseEmitter.event()
                                    .id(Integer.toString(i))
                                    .name("tick")
                                    .reconnectTime(2_000L)
                                    .data("tick-" + i));
                    Thread.sleep(800);
                }
                emitter.complete();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                emitter.complete();
            } catch (IOException ex) {
                // Client disconnected; the container performs async error handling.
            } catch (RuntimeException ex) {
                emitter.completeWithError(ex);
            }
        });

        return emitter;
    }
}
```

**How NDJSON works:**

- `StreamingResponseBody` writes each complete JSON line as UTF-8 bytes.
- `flush()` asks to push data out, but does not guarantee bytes arrive immediately at the browser if a proxy or browser buffers them.
- After each line, the worker sleeps 800 ms so you can observe the stream easily. **Do not use `Thread.sleep` to drive production work**; the demo uses it as a simulated delay.
- Once the callback finishes, the HTTP response ends. There is no standard `Last-Event-ID` or built-in reconnect for NDJSON.
- `Cache-Control: no-store` makes clear not to cache the demo stream content. This header does not automatically disable gzip; production must address buffering/compression separately.

**How SSE works:**

- `SseEmitter` formats events according to the SSE standard.
- `id(1..5)` helps the browser identify each event, but this demo **does not store a replay log**.
- `reconnectTime(2_000L)` suggests a 2-second retry delay. When the emitter completes after 5 events, **EventSource may still reconnect** because the response closed; the demo HTML page calls `close()` upon receiving ID 5.
- If `send()` throws `IOException` because the client disconnected, Spring MVC/the container handles async error dispatch; per Spring documentation, you do not necessarily call `completeWithError` on an `IOException`.
- On other runtime errors, `completeWithError` notifies Spring to complete the stream via the exception path. Once headers have been sent, do not assume you can change the HTTP response status/body in the normal HTTP way.

**An important difference:** response streaming typically submits **one** callback on the MVC async executor. `SseEmitter` can keep a request open and be sent to from another thread/service. To broadcast to thousands of subscribers, do not use `Thread.sleep` or dedicate one thread per subscriber like the demo; use an event bus and an appropriate dispatch/buffering strategy.

### 7.5. EchoHandler.java: WebSocket Echo

File `src/main/java/demo/EchoHandler.java`:

```java
package demo;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class EchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws Exception {

        String payload = message.getPayload();

        if (payload.length() > 1024) {
            session.sendMessage(
                    new TextMessage("error: message too long"));
            return;
        }

        session.sendMessage(new TextMessage("echo: " + payload));
    }
}
```

The server receives a text message and sends a reply on **the same WebSocket session**, unlike NDJSON/SSE which only send events from the server over an HTTP response. The 1024-character length check is just demo logic; production must also configure **WebSocket frame/message limits at the server/container**, because a huge payload can already consume memory before the handler executes.

In this example, only the input-handling callback sends replies; there are no concurrent publisher threads sending at the same time. When multiple threads want to send through the same `WebSocketSession`, ensure **there are no uncoordinated concurrent sends**; Spring provides `ConcurrentWebSocketSessionDecorator` or a single-writer queue pattern. Do not assume `sendMessage` is thread-safe across all WebSocket engines.

### 7.6. WebSocketConfiguration.java: Registering the Handshake Path

File `src/main/java/demo/WebSocketConfiguration.java`:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration(proxyBeanMethods = false)
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoHandler handler;

    public WebSocketConfiguration(EchoHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {

        registry.addHandler(handler, "/ws/echo");
    }
}
```

`@EnableWebSocket` with `WebSocketConfigurer` registers a raw `WebSocketHandler`. A STOMP message broker is unnecessary for a simple echo channel. By default, Spring restricts allowed origins for WebSocket handshakes (same-origin under standard configuration); the browser demo loads the page and connects on the same host/port. **Do not add `setAllowedOriginPatterns("*")` to fix every handshake error**, because browser WebSocket is not restricted by the same-origin policy identically to `fetch` and requires server-side origin validation.

### 7.7. static/index.html: Testing All Three in the Browser

File `src/main/resources/static/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>HTTP Stream, SSE, and WebSocket</title>
</head>
<body>
  <h1>Long-Lived Connections Demo</h1>

  <button id="ndjson">Stream NDJSON</button>
  <button id="sse">Open SSE</button>
  <button id="ws">WebSocket echo</button>
  <button id="stop">Stop connections</button>
  <pre id="output"></pre>

  <script>
    const output = document.querySelector("#output");
    const log = (line) => {
      output.textContent += line + "\n";
    };

    let source = null;
    let socket = null;
    let abort = null;

    document.querySelector("#ndjson").onclick = async () => {
      abort?.abort();
      abort = new AbortController();

      try {
        const response = await fetch("/stream/ndjson", {
          signal: abort.signal
        });
        if (!response.ok || !response.body) {
          throw new Error("HTTP status " + response.status);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const result = await reader.read();

          if (result.done) {
            buffer += decoder.decode();
            if (buffer.trim()) log("last: " + buffer);
            break;
          }

          buffer += decoder.decode(result.value, { stream: true });
          let newline = buffer.indexOf("\n");

          while (newline !== -1) {
            const line = buffer.slice(0, newline).trim();
            buffer = buffer.slice(newline + 1);

            if (line) {
              log("NDJSON: " + JSON.stringify(JSON.parse(line)));
            }
            newline = buffer.indexOf("\n");
          }
        }
        log("NDJSON complete");
      } catch (error) {
        log("NDJSON stopped/error: " + error.message);
      }
    };

    document.querySelector("#sse").onclick = () => {
      source?.close();
      source = new EventSource("/events");

      source.addEventListener("tick", (event) => {
        log("SSE id=" + event.lastEventId +
            " data=" + event.data);

        // Finite stream demo: stop reconnect after the last event.
        if (event.lastEventId === "5") {
          source.close();
          log("SSE closed by browser");
        }
      });

      source.onerror = () => log("SSE interrupted/reconnecting");
    };

    document.querySelector("#ws").onclick = () => {
      socket?.close();

      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      const url = protocol + "//" + location.host + "/ws/echo";
      socket = new WebSocket(url);

      socket.onopen = () => {
        log("WebSocket OPEN");
        socket.send("hello");
      };
      socket.onmessage = (event) => {
        log("WebSocket: " + event.data);
      };
      socket.onclose = (event) => {
        log("WebSocket CLOSED code=" + event.code);
      };
      socket.onerror = () => log("WebSocket error");
    };

    document.querySelector("#stop").onclick = () => {
      abort?.abort();
      source?.close();
      socket?.close();
      log("All browser connections stopped");
    };
  </script>
</body>
</html>
```

The browser loads `http://localhost:8080/` and uses the buttons to test. Data from the server is written via `textContent` rather than `innerHTML`; in a real app you must enforce user content sanitization, authorization, and DOM injection protections accordingly.

The NDJSON reader maintains a `buffer` because a single `reader.read()` call can contain half a line or multiple lines. `EventSource`, by contrast, handles `event:`/`data:` parsing and dispatching automatically. `WebSocket` sends a message on `onopen` and receives the reply in `onmessage`.

This is a simple single-page demo **without an app-level retry queue or replay**. The Stop button actively aborts the HTTP stream, closes EventSource, and sends a WebSocket close. When the server restarts, the HTTP stream is cut; browser SSE can reconnect, while browser WebSocket does not automatically open a new socket.

### 7.8. application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.mvc.async.request-timeout=30s

# Disable compression in the lab to see each chunk/event more clearly.
server.compression.enabled=false
```

`spring.mvc.async.request-timeout` sets a limit for async requests in MVC, though each `SseEmitter` also has its own timeout (30,000 ms) in code. In production, this must be coordinated with proxy idle/read timeouts and stream termination policies; increasing timeouts to infinity does not solve lost clients or missing resource limits.

### 7.9. Running the Application

From the root directory containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

The Java files use Spring MVC/WebSocket APIs and cannot be run standalone with `javac StreamController.java` without providing the classpath. Initializr and the Gradle Wrapper manage compile/runtime dependencies. By default, the example listens on `http://localhost:8080` if the port is free.

Visit `http://localhost:8080/` in the browser and try the buttons. With the exact source above, the WebSocket button will print:

```text
WebSocket OPEN
WebSocket: echo: hello
```

These are the two main lines; when you close the connection, the page will also log the corresponding CLOSED/Stop line. The exact order of some events depends on scheduling/network, but the echo payload is fixed.

## 8. Testing HTTP Streaming with curl

Open a terminal while `bootRun` is running:

```bash
curl -N -i http://localhost:8080/stream/ndjson
```

`-N`/`--no-buffer` tells curl not to buffer output on the client side. You will receive the body incrementally:

```jsonl
{"seq":1,"kind":"snapshot"}
{"seq":2,"kind":"snapshot"}
{"seq":3,"kind":"snapshot"}
{"seq":4,"kind":"snapshot"}
{"seq":5,"kind":"snapshot"}
```

This is **the exact body from the callback**, omitting headers and arrival timestamps for each line. Lines are generated with an 800 ms pause between iterations; if proxy buffering or terminal buffering occurs, you might not see each line immediately even though the code called `flush()`.

Try a standard client call:

```bash
curl -i http://localhost:8080/stream/ndjson
```

The output might appear to arrive "all at once" due to endpoint buffering; that does not prove the server isn't streaming. Compare `curl -N`, browser Network timing, and packet/edge logs.

**Do not use `curl --compressed` to verify "per-flush delivery" while gzip is enabled**, because the compressor or proxy may coalesce output. The demo disables compression in `application.properties` to reduce variables.

## 9. Testing SSE with curl and the Browser

```bash
curl -N -i -H 'Accept: text/event-stream' \
  http://localhost:8080/events
```

Expected headers include `Content-Type: text/event-stream`; the body looks like:

```text
id: 1
event: tick
retry: 2000
data: tick-1

id: 2
event: tick
retry: 2000
data: tick-2

...
id: 5
event: tick
retry: 2000
data: tick-5

```

This is **a structural representation of the fields**, not a guarantee of exact field ordering or whitespace across all Spring Framework versions. What matters: each event has the name `tick`, IDs `1..5`, and data `tick-1..tick-5`, with blank lines between events.

When called directly with `curl`, once the server completes the response, `curl` exits; curl **is not an EventSource** so it does not auto-reconnect. Browser `EventSource` does reconnect, though the demo page proactively calls `close()` upon receiving `lastEventId === "5"`.

### 9.1. Receiving Named Events

```javascript
const source = new EventSource("/events");

source.onmessage = (event) => {
  console.log("default message:", event.data);
};

source.addEventListener("tick", (event) => {
  console.log("named tick:", event.data);
});
```

Because the server emits `event: tick`, the client should listen using `addEventListener("tick", ...)`. `onmessage` applies to unnamed events or `message`-type events per the standard rules, so writing only `onmessage` can make it look like the server sent nothing.

### 9.2. Testing Last-Event-ID on Request

```bash
curl -N -H 'Last-Event-ID: 3' \
  http://localhost:8080/events
```

In the demo, the server **does not read the header**, so it still sends from `id: 1`. This is not an SSE parser bug: the application simply has not implemented replay. A real service needs:

```java
@GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events(
        @RequestHeader(value = "Last-Event-ID", required = false)
        String lastEventId) {
    // Authenticate the user and validate the cursor.
    // Query a durable event store to replay after lastEventId.
    // Then stream new events on the same flow.
    throw new UnsupportedOperationException("Illustrative only");
}
```

This is **a design snippet, not standalone runnable code**, intentionally highlighting the missing piece. Do not copy `UnsupportedOperationException` directly into a running demo. When implementing replay in production, handle invalid/expired cursors, events belonging to other tenants, races between replay and live subscription, deduplication, and gap detection.

## 10. Testing WebSocket with the Right Tools

Standard `curl` is only suitable for low-level inspection of HTTP upgrade headers and is **not a complete WebSocket client** for properly sending/receiving frames. Use the browser button on the demo page or a dedicated WebSocket client such as `wscat`, `websocat`, Postman WebSocket mode, or another tool.

Example with a command-line client if `websocat` is installed:

```bash
websocat ws://localhost:8080/ws/echo
```

After connecting, type:

```text
hello
```

Response:

```text
echo: hello
```

`websocat` is **an external tool**, not installed by the Spring Boot project. If you don't have it, use the browser; do not expect `curl -X POST /ws/echo` to work because a WebSocket handshake is not a regular JSON POST API.

### 10.1. Inspecting the Handshake Is Useful but Not Enough

An HTTP/1.1 handshake typically has `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Key`, and `Sec-WebSocket-Version: 13`; the server returns 101 and a valid `Sec-WebSocket-Accept`. Afterward, WebSocket frames must be read/written according to the protocol. Even seeing 101 **does not prove** that echo messaging, authorization, or reconnect works.

### 10.2. Browser WebSocket Differs from Raw HTTP Requests

`new WebSocket("ws://...")` initializes a connection and a protocol object. After `onopen`, `send("hello")` sends a WebSocket **message**, not a new HTTP request. `onmessage` likewise does not contain an HTTP status per message. To report business errors, define a message schema (such as `{"type":"error","code":"INVALID_ROOM"}`) or close the socket with an appropriate close code.

## 11. Proxy/Ingress: Where Streaming Most Commonly Breaks

An app that works fine when accessed directly at `localhost:8080` can fail behind a reverse proxy/CDN due to:

- Proxy buffering holding NDJSON/SSE until a threshold is reached or the response ends;
- Gzip compression holding bytes until a block flushes;
- Idle timeouts cutting SSE/WebSocket when there is no heartbeat;
- Proxy failing to forward WebSocket `Upgrade`/`Connection` headers;
- CDN not supporting WebSocket or attempting to cache the stream;
- Upstream/downstream using mismatched HTTP versions with wrong configuration;
- TLS termination causing an HTTPS browser page to open `ws://` instead of `wss://`;
- Rolling deploys dropping live sockets when clients lack resume logic.

### 11.1. Illustrative NGINX Config for All Three Paths

Suppose NGINX runs on the same host and proxies to Spring Boot at `127.0.0.1:8080`. A sample configuration with `map` in the **http context**:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 8081;
    server_name localhost;

    location /stream/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 90s;
        gzip off;
    }

    location /events {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 90s;
        gzip off;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 90s;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
    }
}
```

This is an **NGINX snippet without a full nginx.conf** and uses **local HTTP** for debugging. Production needs HTTPS, hostname/Host forwarding, forwarded scheme, network policies, security headers, and an ingress trust boundary. If NGINX runs in a separate container, `127.0.0.1` refers to the NGINX container itself; replace it with the actual service DNS name.

Explanation:

- `proxy_buffering off` attempts to forward streaming bytes immediately instead of buffering the full response.
- `gzip off` on the two routes avoids batching individual events/chunks in the compression layer in the lab; production may consider stream compression if flush/latency guarantees are met.
- `proxy_read_timeout 90s` is **the wait time between reads from upstream**, not the exact maximum lifetime of the connection.
- WebSocket `Upgrade` is a hop-by-hop header; NGINX must forward the required headers to upstream and establish a tunnel upon successful handshake.
- `map` sets `Connection: upgrade` when an Upgrade request is present and `close` otherwise.
- `proxy_http_version 1.1` ensures an HTTP/1.1 upstream hop suitable for the WebSocket demo. With very recent NGINX versions, defaults may vary; setting it explicitly is helpful for clarity.
- When routes are `/events` or `/ws/echo`, the public path/URI must match the backend path; changing trailing slashes in `proxy_pass` can rewrite URIs unexpectedly.

### 11.2. X-Accel-Buffering: no

In the controller we have:

```java
response.setHeader("X-Accel-Buffering", "no");
```

NGINX can use this header to control buffering when not configured to ignore it. It **is not an HTTP standard honored by every CDN/reverse proxy**; other proxies may not understand it. Therefore, you still need to check configuration at every hop. If a caching layer tries to store `text/event-stream` responses, bypass cache; protect privacy with appropriate `Cache-Control` and edge policies.

### 11.3. Heartbeat vs. Timeout

For example, a proxy cuts the stream if no upstream data arrives within 60 seconds. An SSE stream that only emits business events every 5 minutes should send `: heartbeat` at an appropriate interval (e.g., 15–25 seconds, depending on infrastructure) to keep the connection alive and detect disconnects. With WebSocket, the server can send protocol Ping frames or heartbeat messages and check Pong/timeouts. **Do not promise that heartbeats prevent every disconnect:** mobile networks, NATs, browser sleep, and pod restarts can still close the socket.

### 11.4. HTTP/2 Does Not Turn WebSocket into SSE

SSE and NDJSON streaming run over HTTP/1.1, HTTP/2, or HTTP/3 depending on the stack; the application format remains the same. Standard browser WebSocket uses HTTP/1.1 Upgrade, while some infrastructures support HTTP/2 extended CONNECT. Do not copy an HTTP/1.1 Upgrade config and assume every HTTP/2 hop handles it automatically. Verify the actual ingress/proxy/controller with a real browser.

## 12. Timeouts and Resource Limits

### 12.1. Three Timeout Groups

| Timeout | Layer | Common Consequence |
| --- | --- | --- |
| MVC async request timeout | Spring MVC/Servlet | `StreamingResponseBody`/`SseEmitter` may time out |
| Reverse proxy upstream read timeout | NGINX/LB/Ingress | Cuts stream if no bytes arrive within the configured window |
| WebSocket idle/ping timeout | WebSocket engine/proxy | Socket closed if idle too long or ping/pong goes unanswered |

Additionally, there are TCP keep-alive, browser/mobile network timeouts, CDN limits, application-specific session TTLs, auth token expiry, and rolling-deployment termination. Raising a single property cannot override all limits.

### 12.2. Threads and Memory in Spring MVC

Spring MVC has asynchronous request processing, but writes to the Servlet response remain **blocking** under the Servlet I/O model. With thousands of connections streaming large payloads, you need a bounded worker pool and slow-client controls. A request can hold a socket, response buffers, app resources, and context for a long time even after the initial request thread is released.

The `ThreadPoolTaskExecutor` in the demo is a basic model and must not be assumed to handle unlimited connections; when the pool/queue fills up, the app must return/record errors gracefully and proactively limit concurrent streams. Do not use `Executors.newCachedThreadPool()` per request or spawn unbounded `new Thread()` instances.

### 12.3. What Is Backpressure?

**Backpressure** is the mechanism for coordinating production and consumption rates so a producer does not generate data faster than a consumer indefinitely. If the server produces 1,000 events/s while the client only processes 50 events/s, data can pile up in memory, TCP buffers, queues, or brokers.

Strategies:

- Bound queue sizes and message sizes.
- Apply backpressure/demand through reactive streams when using WebFlux, while still accounting for network/client buffering.
- For live data that can be skipped, keep only the "latest value" instead of every tick.
- For data that must be durably stored, use a durable broker/log with client cursors/acks.
- Slow clients can be disconnected cleanly to protect the overall system.
- Define business SLAs for data loss, latency, ordering, and replay.

Browser WebSocket exposes `bufferedAmount` to measure bytes queued for `send()` on the browser side; it does not guarantee the server keeps up. Standard browser WebSocket APIs **do not provide full backpressure** like Reactive Streams. SSE likewise does not automatically slow down the producer for the client; `SseEmitter.send()` can block or error depending on transport and client.

### 12.4. Connection Counts

For SSE over HTTP/1.1, browsers enforce practical limits on connections to the same origin (typically around 6 in many browsers when not using HTTP/2). Multiple tabs plus multiple EventSource connections can hit the limit; HTTP/2 stream multiplexing changes practical limits according to negotiated concurrent streams. Do not open one SSE connection per widget when a single stream multiplexed by `event:` type can be used.

WebSocket also has limits on sockets, file descriptors, memory, load balancer capacity, and browser/network limits. No technology allows 100,000 connections simply with an annotation without capacity planning.

## 13. Reconnect, Delivery, and Server Restarts

### 13.1. Plain HTTP Streaming

When a response cuts off at line 3, the client must decide whether a new request starts from the beginning or from the next sequence number. With a cursor:

```http
GET /stream/ndjson?after=3
```

The server can query a durable store and emit starting from seq 4. **This is an additional API design**, not present in the demo. For file downloads, HTTP Range/ETag can support byte-level resume; for NDJSON business events, a record-level cursor is usually more suitable.

### 13.2. SSE

`EventSource` reconnects and sends `Last-Event-ID` according to the specification. This **only lets the client report the ID it last saw**. If a new server after restart does not retain old events, events produced during downtime can still be lost. Use an event store/broker if reliable delivery is required; do not rely on `SseEmitter` alone.

### 13.3. WebSocket

WebSocket can close with close code `1000` (normal), `1001` (going away), `1006` (abnormal closure reported by the API, not a wire close frame), or other codes. Applications should distinguish intentional closes from network loss/server errors and use reconnect backoff with jitter and timeouts. After reconnecting, handle authentication, re-subscription, state synchronization, and replay/dedup by message ID.

### 13.4. Event Delivery Guarantees

| Guarantee | What Is Required? |
| --- | --- |
| Best effort | Send to currently connected clients; can lose events on disconnect |
| At-most-once | No replay, can lose events; avoids duplicates by design |
| At-least-once | Store events + retry/replay + ACK or cursor; client deduplicates since repeats can occur |
| Exactly-once business effect | Idempotent processing, transactions/unique constraints/dedup store; transport protocol alone does not guarantee it |

The same socket or TCP connection does not turn every business action into exactly-once. If WebSocket is used to place orders or payments, require the server to attach idempotency keys and persist state durably just like HTTP POST.

## 14. Multiple Replicas, Broadcast, and Brokers

Consider two Spring Boot pods A and B. Browser 1 holds an SSE connection to A; Browser 2 holds a WebSocket connection to B. An event is generated on A:

```text
Business event created at A
            |
            v
Need to reach clients on A AND B
            |
      +-----+------+
      | shared bus |
      +-----+------+
         |      |
         v      v
        Pod A   Pod B
         |      |
      SSE/WS   SSE/WS
       clients  clients
```

If `List<SseEmitter>` or `Map<WebSocketSession>` is kept only in A's RAM, B cannot see those connections. A **shared pub/sub or broker** is needed while each pod manages its own physical client connections. Options include Redis Pub/Sub (non-durable), Redis Streams, Kafka, RabbitMQ, or a dedicated realtime service; choose based on durability, ordering, latency, and requirements.

With Spring WebSocket messaging, **STOMP** is an additional protocol for routing messages by destinations (`/topic`, `/queue`, `/app`), not a mandatory part of raw WebSocket. Spring includes a **simple in-memory broker** for demos, which is not suitable for clustering; to broadcast across multiple app nodes, you can use a **STOMP broker relay** to a dedicated external broker.

**Do not conclude that using STOMP = durable delivery.** Acknowledgments, receipts, transactions, persistent queues, replay, and retries depend on the broker, protocol/subscription mode, and actual configuration.

### 14.1. Sticky Sessions and Failover

Session affinity can keep a client routed to the same instance during a connection, but when a pod is replaced, the connection still drops. When the client reconnects to another node, subscription state must be recreated or fetched from a shared store. Sticky sessions do not replace durable events or a broker.

### 14.2. Rollout and Graceful Shutdown

During deployment:

1. Mark the pod as draining and stop accepting new connections.
2. Allow finite responses to finish within the allowed grace window.
3. For long-lived SSE/WS, notify clients to reconnect or close cleanly.
4. Clients reconnect with jitter to avoid thousands of connections spiking simultaneously.
5. Resume via cursor/event ID or fetch a fresh snapshot to restore state.

Graceful shutdown **cannot preserve a TCP socket across a JVM death and new process creation**. It only reduces errors and lets clients transition state cleanly.

## 15. Security for HTTP Streams, SSE, and WebSocket

### 15.1. Authentication and Authorization

Streaming endpoints can use Spring Security sessions, OAuth2 resource server/JWT, API keys/mTLS, or an appropriate identity mechanism. **Do not assume opening a socket authorizes every subsequent message.**

- HTTP streaming: authorize GET + resource/job/tenant; prevent clients from guessing other users' IDs.
- SSE: authorize the connection, then verify each subscription/job/event is permitted; tokens/roles may change while a stream stays open.
- WebSocket: authorize the handshake **and each message/action**, checking message schema, rate limits, room membership, and destination send permissions.
- When a session/token is revoked, the application must decide whether to terminate open connections, because a previously successful handshake does not grant permanent access.

### 15.2. CORS and Browser EventSource

Because SSE uses HTTP GET, it is subject to browser cross-origin policies. For cross-origin connections, `EventSource` supports:

```javascript
const stream = new EventSource("https://api.example.test/events", {
  withCredentials: true
});
```

If using cross-origin cookies/credentials, the server needs an explicit CORS allowlist, `Access-Control-Allow-Credentials`, and appropriate `SameSite`/`Secure` cookies. Native `EventSource` **does not allow setting arbitrary `Authorization` headers** like `fetch`; with bearer tokens, consider a same-origin BFF/cookie auth with a proper CSRF policy, or an HTTP streaming client using `fetch` with custom headers when needed. **Avoid putting long-lived access tokens in query strings** because URLs can leak into logs, referrers, and browser history.

### 15.3. WebSocket Origin and Cross-Site WebSocket Hijacking

The browser WebSocket API is not bound by the same-origin policy in the same way `fetch` is. A malicious page can attempt to open a WebSocket to your service; if cookies are sent automatically with the handshake and the server does not check `Origin`, there is a risk of **Cross-Site WebSocket Hijacking**.

Use:

- A strict Origin allowlist, without reckless wildcard `*`;
- Appropriate authentication/session/token or channel binding;
- Per-message/room/tenant authorization;
- CSRF/handshake tokens according to the system mechanism if needed;
- TLS `wss://`, connection limits, and message size limits.

`Origin` mitigates browser-based threats, but non-browser clients can set or spoof headers, so **Origin does not replace authentication**. Spring raw WebSocket config enforces same-origin checks by default in many setups, but verify behavior whenever customizing endpoints or handshakes.

### 15.4. Sensitive Data and Caching

User-specific SSE/NDJSON should not be stored in a shared CDN cache. Use `Cache-Control: no-store` along with CDN bypass policies to prevent accidental caching. WebSocket messages do not enter HTTP response caches, yet they can still be logged by apps, gateways, observability pipelines, or browser devtools; avoid sending unnecessary secrets.

When streaming private data, check permissions before starting and throughout long lifecycles; terminate or refresh when the user logs out, permissions are revoked, or a job is canceled.

### 15.5. Input Validation and Rate Limits

WebSocket requires limits on max message size, connections/user, messages/s, subscription count, and total buffer size. HTTP streaming and SSE require limits on concurrent subscribers, heartbeat frequency, server event size, and producer queues. A slow or malicious client can hold connections and consume sockets/threads far longer than normal requests.

## 16. WebFlux: A Different Model from Spring MVC

In **Spring WebFlux**, streaming responses typically use Project Reactor `Flux<T>`. WebFlux provides non-blocking I/O and Reactive Streams backpressure across the processing chain, unlike Spring MVC `StreamingResponseBody` which performs blocking response writes on an async executor.

WebFlux SSE example **as a standalone snippet separate from the MVC project in section 7**:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping(path = "/reactive/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(i -> ServerSentEvent.<String>builder()
            .id(Long.toString(i + 1))
            .event("tick")
            .data("tick-" + (i + 1))
            .build());
}
```

This is a **method snippet** requiring a `@RestController` in a `spring-boot-starter-webflux` project, not a standalone compilable class. `Flux.interval` emits values 0..4, mapped to IDs 1..5. The `Flux` completes after 5 events; browser EventSource may still reconnect unless the client closes explicitly.

WebFlux can return `Flux<YourDto>` with a streaming media type like `application/x-ndjson`, or `Flux<ServerSentEvent<?>>` for SSE. Do not assume returning `Flux` with `application/json` always flushes item by item immediately: media type and encoder govern flush semantics.

### 16.1. Reactive WebSocket

WebFlux uses `org.springframework.web.reactive.socket.WebSocketHandler`, `WebSocketSession.receive()`/`send(Publisher<WebSocketMessage>)`, and reactive handler mappings. It **is not** raw MVC `TextWebSocketHandler`. In WebFlux, do not block the event loop with `Thread.sleep` or direct synchronous JDBC calls; use reactive APIs or offload to an appropriate scheduler.

### 16.2. Backpressure Does Not Magically Span Every Layer

Reactive Streams helps producers and consumers coordinate demand inside the pipeline, but the browser native WebSocket API still has its own buffering, network/TCP has its own flow control, and a message broker has its own queue policies. Measure end-to-end, especially when WebFlux sends to slow clients.

## 17. Choosing a Technology by Scenario

| Scenario | Recommendation | Rationale and Limitations |
| --- | --- | --- |
| Generating a multi-GB CSV report | HTTP response streaming/download | Suitable byte stream; needs backpressure, Content-Disposition, Range/resume if needed |
| Task processing progress | SSE if push-only; or polling if updates are rare | Server emits status; a Cancel button still uses HTTP POST |
| Live build/deploy logs | SSE or NDJSON | SSE offers EventSource/reconnect metadata; NDJSON suits CLIs and custom parsers |
| Order notifications | SSE | Server→client; add a replay store so notifications aren't lost |
| Price/metrics dashboard | SSE if unidirectional, WebSocket if frequent interactive commands are needed | Balance frequency, client count, and message semantics |
| Bidirectional chat | WebSocket | Client/server send messages continuously; requires auth, broker, persistence |
| Multiplayer game or collaborative editor | WebSocket | Bi-directional low-latency messaging; ordering/reconciliation remain app responsibilities |
| Binary file streaming | HTTP streaming or WebSocket depending on requirements | SSE is text-only; HTTP is usually better for file downloads due to caching/ranges |
| Webhook between two services | Standard HTTP POST | Long-lived connection unnecessary; use delivery/retry/idempotency |
| Single JSON value after 100 ms | Standard HTTP JSON | Simpler and easier to cache than a stream |
| Sending continuous data from an IoT device | HTTP upload streaming or WebSocket depending on design | Do not pick SSE for client→server streams since SSE is server→client only |
| Mobile client with frequent network drops | Any transport paired with durable cursor/ACK | Reconnect/replay matters more than transport choice |

**Rule of thumb:** need only *server-pushed events* and want a simple browser API → consider SSE; want *large/incremental content download* → HTTP streaming; need *continuous bidirectional interaction* → WebSocket. With low update frequency and huge client counts, **conditional polling** is sometimes simpler and good enough; do not assume long-lived connections are always optimal.

## 18. Observability, Testing, and Operations

### 18.1. Useful Metrics

- Active streams/SSE emitters/WebSocket sessions per pod and per user (avoid PII in labels).
- Connection opens/closes, abnormal close codes, reconnect rate.
- Connection lifetime, idle duration without events, heartbeat failures.
- Bytes/messages per second, queue depth, and rejected task count.
- Emitter send latency, blocked writer threads, proxy buffering delay.
- Dropped messages, duplicate IDs, replay gaps, and end-to-end latency.
- Memory/heap, GC, file descriptors, CPU, thread pool utilization.
- 401/403 counts on handshake/subscribe and unauthorized events blocked.
- Proxy 499/502/504 or equivalent status codes, load balancer idle resets, CDN behavior.

**Do not log raw Authorization headers/cookies, tokens, full private message payloads, or user IDs as metric labels**. Use safe correlation IDs with controlled retention.

### 18.2. Fault-Testing Matrix

1. Run NDJSON/SSE/WebSocket directly on `localhost:8080`; verify payload/timing.
2. Run the same endpoints through NGINX/ingress/CDN; compare arrival time of each event at the client.
3. Intentionally enable `proxy_buffering on` for SSE in a test environment and observe the difference.
4. Lower proxy read timeout below the heartbeat interval; measure disconnects.
5. Disconnect Wi-Fi/VPN, sleep the browser tab, switch mobile networks; observe reconnect and replay.
6. Restart Spring Boot while SSE/WebSocket is open; confirm old connections close and clients recover per your logic.
7. Deploy multiple replicas; confirm an event from A reaches a subscriber on B via the broker.
8. Send oversized messages, many concurrent clients, and slow readers; confirm bounded queues and rejections.
9. Verify user A cannot view user B's stream/job/room; test Origin, CORS, cookies, and TLS.
10. When deploying a new version, verify message format and resume compatibility.

### 18.3. Testing "True Streaming" Instead of Just the Final Body

A `curl -s ...` response that completes successfully can mask buffering bugs. Measure timestamps on the server at `send/flush` and on the client when each event/line/message is processed. Compare **per-item latency**, not just total response time. With HTTP/2 proxying, evaluate on a real viewer path rather than only localhost HTTP/1.1.

### 18.4. When You Can Return HTTP Errors vs. When You Cannot

For HTTP streaming or SSE, **before headers/body are sent** the server can return 401/403/500 and a normal JSON error. **Once the body has started**, you cannot reliably "change the status to 500" within the same response. Use a structured error record/event, end the stream cleanly, and let the client detect an incomplete/truncated stream. WebSocket likewise has no HTTP status per message after handshake; send an application error message or a protocol close code.

## 19. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "SSE is a completely different technology from HTTP streaming." | SSE uses HTTP streaming with a standardized `text/event-stream` format. |
| "HTTP streaming only allows one-way TCP." | HTTP has requests/responses and supports request body streaming; a specific response stream is primarily server→client. |
| "One `flush()` equals one JavaScript event." | TCP/HTTP/proxy buffers do not preserve `write/flush` boundaries; protocol framing is required. |
| "Each HTTP chunk corresponds to one NDJSON line." | The parser must buffer and split on newlines, not chunk boundaries. |
| "EventSource guarantees no lost events." | It auto-reconnects and sends Last-Event-ID; the server still needs a replay store and deduplication. |
| "SSE cannot be interactive." | Server→client is one-way, but the browser can send separate HTTP POST requests in parallel. |
| "WebSocket has a built-in durable message queue." | No; you must add a broker/storage/ACK/replay if needed. |
| "Browser WebSocket reconnects automatically." | No; your code must handle reconnecting after close/failure. |
| "WebSocket is always faster than SSE." | Performance depends on volume, protocol, infrastructure, and workload. |
| "Using @Async or Flux eliminates all blocking." | Spring MVC writes remain blocking; WebFlux requires keeping the event loop non-blocking. |
| "SSE works well through every CDN." | Proxy buffering, caching, idle timeouts, and HTTP versions must be compatible. |
| "CORS protects WebSocket from all clients." | WebSocket handshake/origin and authentication/authorization require separate policies. |
| "Heartbeats prevent all disconnects." | Pod restarts, mobile network changes, and device sleep still drop connections. |
| "Sticky sessions solve failover." | They do not preserve sockets or RAM when a pod dies; reconnect + shared state are what matter. |
| "Adding WS makes chat automatically scale across pods." | You need message routing/brokers and distributed session state handling. |

## 20. Self-Check Questions

**1.** An application needs to return 5,000 JSON lines for the frontend to render progressively, without needing event names or standard reconnect. What should you choose?  
**Answer:** HTTP streaming with NDJSON is a reasonable choice. The client uses `fetch().body`/reader and a newline-based parser, not TCP chunks.

**2.** A page needs job status updates pushed by the server, and the browser occasionally sends a Cancel button click. Is WebSocket mandatory?  
**Answer:** No. SSE for status + HTTP POST for Cancel is usually simpler and sufficient.

**3.** When `EventSource` reconnects with `Last-Event-ID: 27`, does Spring `SseEmitter` automatically replay from 28 onward?  
**Answer:** No. The app must read the header, query a durable event store, and replay; permission checks and deduplication are also required.

**4.** A chat feature has users sending/receiving messages continuously and needs binary attachment metadata. What should be considered?  
**Answer:** WebSocket for bidirectional messages; large file uploads can use separate HTTP requests. Requires a broker, auth/permissions, and persistence/ack/resume.

**5.** `curl -N` shows NDJSON every 800 ms at the origin, but via the CDN it arrives only when the server finishes. Where do you look for the cause?  
**Answer:** Proxy/CDN buffering, gzip, cache/response transforms, or network layers. Inspect each hop directly.

**6.** `ws://` is blocked by the browser on an HTTPS page. How do you fix it?  
**Answer:** Use `wss://` to a public endpoint backed by a TLS proxy, configure Upgrade/handshake forwarding, and trust the forwarded scheme properly.

**7.** Why must WebSocket validate `Origin` when users have session cookies?  
**Answer:** Browser WebSocket is not subject to the same-origin checks of fetch; a malicious site could try opening a WS with the browser's automatically attached cookies. An Origin allowlist plus authentication and per-message authorization are necessary.

**8.** After WebSocket returns 101, can you return HTTP 401 for each unauthorized message afterward?  
**Answer:** Not as a new HTTP response; send an application error message or close per policy. The handshake can return 401/403 prior to upgrade.

**9.** If Spring MVC `StreamingResponseBody` returns immediately from the handler, are writes non-blocking like WebFlux?  
**Answer:** No. MVC async support frees the initial request thread, but response writes remain blocking, typically on another executor.

**10.** Pod A holds 50,000 SSE subscribers in RAM, and Pod B emits an event. Does A automatically receive B's event?  
**Answer:** No. A shared pub/sub/broker is needed, plus a durable log if replay across disconnects is required.

## 21. Deployment Checklist

- [ ] Clarify whether you need a byte stream, a one-way event stream, or a bidirectional channel.
- [ ] Define message framing: newlines, SSE fields, or a WebSocket message schema.
- [ ] Never assume HTTP chunks, TCP packets, or proxy flushes align with business messages.
- [ ] Use an executor and bounded queues when streaming with Spring MVC; never create unbounded threads.
- [ ] Ensure SSE uses `text/event-stream`, valid event names/data/id/retry, and a heartbeat plan.
- [ ] If SSE replay is needed, include a durable store, authorization, cursor/dedup/gap handling.
- [ ] Ensure WebSocket has handshake authentication, Origin checks, per-message authorization, and size limits.
- [ ] Do not expect WebSocket to auto-reconnect; implement backoff/jitter/resubscribe logic.
- [ ] Equip long-lived connections with timeouts, heartbeats, and cleanup on client disconnect.
- [ ] Test proxy buffering/compression/caching per streaming route.
- [ ] Ensure NGINX/ingress supports WebSocket Upgrade handshakes or the equivalent transport.
- [ ] Use TLS HTTPS/WSS in production, managing cookies/CORS/CSRF appropriately.
- [ ] Do not share-cache streams with private data and never log tokens/sensitive payloads.
- [ ] Multi-replica setups use a shared bus/broker; sticky sessions do not replace durable state.
- [ ] Implement idempotency/ack/resume when reliable delivery is required instead of relying on transport.
- [ ] Measure time-to-first-event, per-event latency, reconnect rate, queue depth, and connection counts.
- [ ] Test browser, CLI, proxy/CDN, rolling deploys, slow clients, and network loss.

## Official References

- [Spring Framework — MVC Asynchronous Requests: ResponseBodyEmitter, SseEmitter, StreamingResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework — WebSocket API, WebSocketConfigurer, WebSocketHandler](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [Spring Framework — WebSocket Overview and RFC 6455](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [Spring Framework — STOMP Message Broker and External Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework — WebFlux Streaming and Reactive Backpressure](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Boot 3.3 — Common Application Properties: spring.mvc.async.request-timeout](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — WebSocket Support](https://docs.spring.io/spring-boot/3.3/reference/messaging/websockets.html)
- [MDN — Server-Sent Events and EventSource](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [WHATWG HTML Standard — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [MDN — WebSocket Browser API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [NGINX — WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
- [NGINX — HTTP Proxy Buffering/Timeout Configuration](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)

**Takeaway:** HTTP streaming enables **incremental byte delivery in responses**; SSE adds **an event standard and automatic reconnect on top of HTTP streaming**; WebSocket provides **a bidirectional message channel**. When choosing, designing **business framing, permissions, timeouts, heartbeats, replay, and scaling** matters far more than merely picking an API that sounds "real-time".
