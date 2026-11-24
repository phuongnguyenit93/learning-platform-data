# Real-Time Updates Practice: Choosing SSE or WebSocket in Spring Web

A dashboard needs to see new orders without refreshing; a chat app needs users to send and receive messages continuously. Both are "real-time updates," yet their transport requirements differ. **Server-Sent Events (SSE)** keep a single HTTP response open so the server pushes multiple **one-way events to the client**. **WebSocket** upgrades an HTTP connection into a **bidirectional** message channel.

This lesson focuses on Spring MVC (Servlet stack), Java 17+, and Spring Boot 3.3. We build a mini app featuring both SSE and WebSocket sharing the same data source, then test delivery, reconnects, and production limits. The goal is choosing the protocol from requirements rather than assuming WebSocket is always "more real-time."

## 1. Choosing a protocol by data direction and recovery needs

| Criterion | SSE | WebSocket |
| --- | --- | --- |
| Data flow on one connection | Server → client | Server ⇄ client |
| Transport | HTTP streaming, `text/event-stream` | HTTP handshake, `101 Switching Protocols`, then WebSocket frames |
| Browser JavaScript | `EventSource` | `WebSocket` |
| Client sending to server | Separate POST/PUT/HTTP requests | `socket.send(...)` on the same connection |
| Auto-reconnect | `EventSource` retries automatically on drops; supports `retry`/`Last-Event-ID` | Native WebSocket does not auto-reconnect; app manages retry/re-subscribe |
| Message content | UTF-8 text events, can carry JSON | Text/binary frames, format defined by app/subprotocol |
| Good fit for | Task progress, notifications, feeds, read-only dashboards | Chat, collaborative editing, bidirectional control, frequent client events |
| Replay capability | ID field supports resume design, but **server must store and replay** | Design id/ack/replay per business rules |
| Infrastructure | Proxies must allow streaming, avoiding buffering and short idle timeouts | Proxies/load balancers must handle Upgrade handshakes, keepalive, and WS timeouts |
| Resource cost | Long-lived HTTP connections subject to connection/stream limits | Each WS session holds connection resources; must handle slow clients and fan-out |

If the server **only pushes updates** while client actions are infrequent and already served by REST APIs, try **SSE + POST** first. If clients frequently send multiple message types over the same channel, try **WebSocket**. If you need subscriptions, topics, user routing, and a broker, consider **STOMP over WebSocket**, unlike the raw handler in this lesson. If data changes only every few minutes, HTTP polling may satisfy the need with lower complexity.

**Important:** Neither SSE nor WebSocket automatically guarantees zero message loss, "exactly once," global ordering, or history on reconnect. Those are decisions for the application, storage, and event broker layers.

## 2. How does an SSE HTTP stream differ from WebSocket?

### SSE: one response carrying many events

The browser opens an HTTP request:

```http
GET /api/updates/stream HTTP/1.1
Accept: text/event-stream
```

The server keeps the response open and sends events sequentially:

```text
retry: 3000
event: ready
data: connected

id: 17
event: update
data: {"id":17,"source":"http","message":"New order","time":"2026-10-21T10:00:00Z"}

: keepalive

```

Each event can contain `id:`, `event:`, `data:`, `retry:`, and **ends with a blank line**. A line starting with `:` is a comment/heartbeat. JavaScript uses `addEventListener("update", ...)` for the named `update` event; `onmessage` only receives unnamed `message` events.

`EventSource` reconnects automatically and sends the `Last-Event-ID` header once it has received an event with an `id`. If the server does not persist history to look up from that ID, reconnecting only delivers **new** events and provides zero guarantee of recovering missed ones.

### WebSocket: handshake then bidirectional frames

```text
Browser -- HTTP Upgrade /ws/updates --> Spring WebSocket
Browser <-- 101 Switching Protocols --  Spring WebSocket
Browser <--- text/binary frames ---> WebSocketHandler
```

A raw WebSocket handler has no built-in topic subscriptions, acks, or message schemas. This lesson adopts a convention where clients send short strings and the server broadcasts JSON to all connected clients. With STOMP, messages use STOMP frames/destinations and require configuring `@EnableWebSocketMessageBroker` with a matching STOMP client.

## 3. Setting up the demo project

The project uses Spring Boot 3.3 and Java 17+ with Gradle dependencies (versions managed by Boot):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` provides Spring MVC and the embedded Servlet server; `spring-boot-starter-websocket` adds WebSocket. You do not need to switch to WebFlux just to use `SseEmitter`.

File layout:

```text
src/main/java/com/example/realtime/
  RealtimeApplication.java
  LiveHub.java
  UpdatesController.java
  UpdateSocketHandler.java
  WebSocketConfig.java
src/main/resources/static/
  index.html
src/test/java/com/example/realtime/
  UpdatesControllerTest.java
```

File `RealtimeApplication.java`:

```java
package com.example.realtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class RealtimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RealtimeApplication.class, args);
    }
}
```

`@EnableScheduling` powers scheduled SSE heartbeats. Use a Spring-managed scheduler rather than spawning a dedicated thread per subscriber.

## 4. One event hub for both SSE and WebSocket

`LiveHub.java` below keeps subscribers in memory **within a single JVM**. Updates from REST or WebSocket serialize to the same JSON format, with a sequence `id` illustrating event identification.

```java
package com.example.realtime;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

@Component
public class LiveHub {
    private final ObjectMapper mapper;
    private final AtomicLong sequence = new AtomicLong();
    private final ConcurrentMap<String, SseEmitter> emitters =
            new ConcurrentHashMap<>();
    private final Set<WebSocketSession> sockets =
            ConcurrentHashMap.newKeySet();

    public LiveHub(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public record UpdateEvent(
            long id, String source, String message, Instant time) {}

    public SseEmitter subscribeSse() {
        SseEmitter emitter =
                new SseEmitter(TimeUnit.MINUTES.toMillis(5));
        String subscriptionId = UUID.randomUUID().toString();

        emitters.put(subscriptionId, emitter);
        emitter.onCompletion(() -> emitters.remove(subscriptionId));
        emitter.onTimeout(() -> emitters.remove(subscriptionId));
        emitter.onError(error -> emitters.remove(subscriptionId));

        try {
            emitter.send(SseEmitter.event()
                    .name("ready")
                    .reconnectTime(3000)
                    .data("connected"));
        } catch (IOException | IllegalStateException ex) {
            emitters.remove(subscriptionId);
            emitter.completeWithError(ex);
        }
        return emitter;
    }

    public void addSocket(WebSocketSession session) {
        sockets.add(session);
    }

    public void removeSocket(WebSocketSession session) {
        sockets.remove(session);
    }

    public UpdateEvent publish(String raw, String source) {
        if (raw == null || raw.isBlank() || raw.length() > 200) {
            throw new IllegalArgumentException(
                    "message must contain 1..200 characters");
        }

        UpdateEvent event = new UpdateEvent(
                sequence.incrementAndGet(), source, raw.strip(), Instant.now());
        String json = toJson(event);

        for (Map.Entry<String, SseEmitter> entry : emitters.entrySet()) {
            try {
                entry.getValue().send(SseEmitter.event()
                        .id(Long.toString(event.id()))
                        .name("update")
                        .data(json));
            } catch (IOException | IllegalStateException ex) {
                emitters.remove(entry.getKey());
            }
        }

        for (WebSocketSession session : sockets) {
            if (!session.isOpen()) {
                sockets.remove(session);
                continue;
            }
            try {
                // Concurrent sends on the same session must be serialized.
                synchronized (session) {
                    if (session.isOpen()) {
                        session.sendMessage(new TextMessage(json));
                    }
                }
            } catch (IOException | IllegalStateException ex) {
                sockets.remove(session);
            }
        }

        return event;
    }

    @Scheduled(fixedDelay = 20_000)
    public void heartbeat() {
        for (Map.Entry<String, SseEmitter> entry : emitters.entrySet()) {
            try {
                entry.getValue().send(
                        SseEmitter.event().comment("keepalive"));
            } catch (IOException | IllegalStateException ex) {
                emitters.remove(entry.getKey());
            }
        }
    }

    private String toJson(UpdateEvent event) {
        try {
            return mapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Failed to serialize JSON", ex);
        }
    }
}
```

How it works: `subscribeSse()` creates an `SseEmitter` keeping the HTTP response open; `onCompletion`, `onTimeout`, and `onError` remove the emitter from the map. `publish(...)` builds an event and delivers it to both SSE subscribers and WebSocket sessions. `heartbeat()` emits periodic comments to help keep connections alive past idle timeouts. `@Scheduled(fixedDelay=20_000)` does not guarantee every proxy flushes the stream; proxies must be configured separately.

The demo code intentionally caps messages at 200 characters and uses Jackson to emit valid JSON. JavaScript parses it via `JSON.parse`. JSON is sent as **text** when passing `json` to `.data(json)` for SSE or `new TextMessage(json)` for WebSocket. If you later switch to passing objects directly with JSON converters, inspect serialization behavior to avoid double-encoding JSON strings.

**Three notable limitations:**

- `AtomicLong` produces distinct IDs within one JVM, is not persisted, resets on restart, and does not guarantee strict broadcast ordering under concurrent publishers.
- The fan-out loop in `publish` executes synchronously and can slow down when many clients or sockets stall. For production, use a broker, async workers, bounded outbound buffers, and timeout/slow-consumer policies; with Spring WebSocket, consider `ConcurrentWebSocketSessionDecorator` where suitable.
- The map/set hold state local to **one instance**. Behind a load balancer across multiple instances, broadcasts will not automatically reach clients connected to other instances.

## 5. Implementing SSE with Spring MVC

`UpdatesController.java` exposes the HTTP stream for browsers and a POST endpoint for sending updates while in SSE mode:

```java
package com.example.realtime;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
public class UpdatesController {
    private final LiveHub hub;

    public UpdatesController(LiveHub hub) {
        this.hub = hub;
    }

    @GetMapping(
            path = "/api/updates/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream() {
        return hub.subscribeSse();
    }

    @PostMapping(
            path = "/api/updates",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public LiveHub.UpdateEvent publish(@RequestBody UpdateRequest request) {
        try {
            return hub.publish(request.message(), "http");
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, ex.getMessage(), ex);
        }
    }

    public record UpdateRequest(String message) {}
}
```

The browser only receives SSE via `GET /api/updates/stream`. To trigger an action, the browser sends `POST /api/updates` as a **separate** HTTP request, and the result broadcasts down the stream to all subscribers. Thus an SSE-based app is still bidirectional *at the system level*, while the SSE stream itself remains one-way.

This is an **unauthenticated localhost demo**. Never expose a public broadcast POST endpoint to the Internet. Authenticate senders, authorize publishing/subscribing per user/tenant, enforce rate limits, apply CSRF when using cookie sessions, filter sensitive payloads, and bound connection counts.

## 6. Implementing a raw WebSocket handler

`UpdateSocketHandler.java` handles text frames from browsers. Upon receiving valid text, it calls the same `hub.publish`, tagged with source `websocket`:

```java
package com.example.realtime;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class UpdateSocketHandler extends TextWebSocketHandler {
    private final LiveHub hub;

    public UpdateSocketHandler(LiveHub hub) {
        this.hub = hub;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        hub.addSocket(session);
    }

    @Override
    protected void handleTextMessage(
            WebSocketSession session, TextMessage message) throws Exception {
        try {
            hub.publish(message.getPayload(), "websocket");
        } catch (IllegalArgumentException ex) {
            session.close(CloseStatus.BAD_DATA);
        }
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session, CloseStatus status) {
        hub.removeSocket(session);
    }

    @Override
    public void handleTransportError(
            WebSocketSession session, Throwable exception)
            throws Exception {
        hub.removeSocket(session);
        if (session.isOpen()) {
            session.close();
        }
    }
}
```

`afterConnectionEstablished` registers the session in the active set; `afterConnectionClosed`/`handleTransportError` clean up when the connection ends. Closing the socket with `CloseStatus.BAD_DATA` signals invalid client data. This snippet supports text frames only; if binary frames or richer protocols are needed, design the handler accordingly.

File `WebSocketConfig.java`:

```java
package com.example.realtime;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {
    private final UpdateSocketHandler handler;

    public WebSocketConfig(UpdateSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/updates");
    }
}
```

Clients connect to `ws://localhost:8080/ws/updates` over local HTTP; HTTPS sites must use `wss://`. Spring validates Origin during the WebSocket handshake per configuration; never blindly add `setAllowedOrigins("*")`. Origin checks are only a browser-side control and do not replace authentication or per-action socket authorization.

This is a raw handler. If you need multiple chat rooms, subscriptions, `@MessageMapping`, and `SimpMessagingTemplate`, configure STOMP via `@EnableWebSocketMessageBroker`. STOMP is an **application protocol layered over WebSocket**, so a STOMP client cannot point at a raw handler URL and expect `/topic/...` destinations to work automatically.

## 7. UI to test both transports

Create `src/main/resources/static/index.html`. Spring Boot serves this file at `http://localhost:8080/` under default web configuration:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Spring Realtime: SSE and WebSocket</title>
</head>
<body>
  <h1>Real-time updates</h1>
  <button id="open-sse">Use SSE</button>
  <button id="open-ws">Use WebSocket</button>
  <button id="stop">Disconnect</button>
  <p id="status">Not connected</p>

  <label for="input">Message:</label>
  <input id="input" maxlength="200" value="New update">
  <button id="publish">Publish update</button>
  <ol id="updates"></ol>

  <script>
    let sse = null;
    let ws = null;
    let mode = null;
    const status = document.getElementById("status");
    const updates = document.getElementById("updates");

    function write(text) {
      const li = document.createElement("li");
      li.textContent = text;
      updates.prepend(li);
    }

    function showEvent(json) {
      const event = JSON.parse(json);
      write("#" + event.id + " [" + event.source + "] " + event.message);
    }

    function disconnect() {
      if (sse !== null) {
        sse.close();
        sse = null;
      }
      if (ws !== null) {
        ws.close();
        ws = null;
      }
      mode = null;
      status.textContent = "Not connected";
    }

    document.getElementById("open-sse").onclick = () => {
      disconnect();
      mode = "sse";
      sse = new EventSource("/api/updates/stream");
      status.textContent = "SSE connecting";
      sse.addEventListener("ready", () => {
        status.textContent = "SSE ready";
      });
      sse.addEventListener("update", e => showEvent(e.data));
      sse.onerror = () => {
        status.textContent = "SSE interrupted, browser will retry";
      };
    };

    document.getElementById("open-ws").onclick = () => {
      disconnect();
      mode = "ws";
      const scheme = location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(scheme + "//" + location.host + "/ws/updates");
      status.textContent = "WebSocket connecting";
      ws.onopen = () => status.textContent = "WebSocket ready";
      ws.onmessage = e => showEvent(e.data);
      ws.onclose = () => {
        status.textContent = "WebSocket closed, please reconnect";
      };
      ws.onerror = () => status.textContent = "WebSocket error";
    };

    document.getElementById("stop").onclick = disconnect;

    document.getElementById("publish").onclick = async () => {
      const message = document.getElementById("input").value.trim();
      if (!message || message.length > 200) {
        write("Message must contain 1..200 characters");
        return;
      }

      if (mode === "ws") {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          write("WebSocket is not ready");
          return;
        }
        ws.send(message);
      } else if (mode === "sse") {
        try {
          const response = await fetch("/api/updates", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({message})
          });
          if (!response.ok) {
            write("POST failed with HTTP " + response.status);
          }
        } catch (error) {
          write("Failed to send POST");
        }
      } else {
        write("Please select SSE or WebSocket");
      }
    };
  </script>
</body>
</html>
```

**Observable comparison:** in SSE mode, JavaScript creates an `EventSource`, yet clicking publish sends `fetch(POST)`. In WebSocket mode, the same button calls `ws.send(message)` directly over the open socket. Both receive each other's events because the server publishes into the shared `LiveHub`.

The HTML uses `textContent` so messages are never interpreted as HTML/scripts. Real apps must still enforce channel read/write permissions and protect against spam, malicious payloads, and sensitive data exposure.

## 8. Running and verifying with browser/curl

From the Boot-configured project:

```bash
./gradlew bootRun
```

Windows PowerShell: `.\gradlew.bat bootRun`. Open `http://localhost:8080/` in two tabs. Select SSE in tab A and WebSocket in tab B. Send "New order" from tab A; both tabs receive the event with `source=http`. Send "Sent via WebSocket" from tab B; both tabs receive the event with `source=websocket`. This demonstrates both clients receiving from the same publisher **within one JVM**.

Open Bash terminal A to inspect raw SSE:

```bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8080/api/updates/stream
```

`curl -N` disables curl's output buffering, showing events immediately as the server flushes. From terminal B, publish an update:

```bash
curl -i -X POST http://localhost:8080/api/updates \
  -H "Content-Type: application/json" \
  -d '{"message":"New order"}'
```

In PowerShell you can run the **single-line** command:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/updates" -ContentType "application/json" -Body '{"message":"New order"}'
```

The SSE receiver is expected to see this structure:

```text
id: 1
event: update
data: {"id":1,"source":"http","message":"New order","time":"..."}

```

Actual `id` and `time` vary with publish order and server clock. This illustrates the data format, **not captured stdout from running the code**. The `GET /api/updates/stream` HTTP response stays open and can receive many events.

To inspect the WebSocket handshake, open Developer Tools → Network → WS and click **Use WebSocket**. A successful handshake normally shows status `101 Switching Protocols`; the Frames tab displays client-sent text and server-broadcast JSON. Calling `ws://` from an HTTPS page causes browsers to block mixed content; use `wss://` behind an appropriate TLS reverse proxy.

### Four experiments contrasting the two protocols

1. **Two tabs:** use SSE in A, WebSocket in B, and send from each; both observe the update, confirming fan-out.
2. **Network drop:** temporarily disconnect. `EventSource` retries automatically per `retry`; WebSocket in the demo only reports closed and waits for the user to reconnect. Real WS apps need backoff/jitter and re-authentication on reconnect.
3. **Server restart:** IDs in `AtomicLong` reset; events published while a browser was offline are not replayed. This is a demo limitation, not an SSE-specific flaw.
4. **Invalid input:** POSTing a whitespace-only message must return 400; sending blank text over WebSocket closes with invalid-data status. Both entry points enforce the 1..200 character rule.

## 9. Testing Spring MVC and test boundaries

File `src/test/java/com/example/realtime/UpdatesControllerTest.java`:

```java
package com.example.realtime;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UpdatesControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publishesValidPayload() throws Exception {
        mvc.perform(post("/api/updates")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"Hello\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello"))
                .andExpect(jsonPath("$.source").value("http"));
    }

    @Test
    void rejectsBlankPayload() throws Exception {
        mvc.perform(post("/api/updates")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"  \"}"))
                .andExpect(status().isBadRequest());
    }
}
```

Run:

```bash
./gradlew test --tests com.example.realtime.UpdatesControllerTest
```

The test above loads the context and uses `MockMvc` to verify the HTTP controller. It **does not perform TCP streaming or WebSocket handshakes**, so it is not enough to prove browsers actually receive updates. Transport integration tests must run the embedded server on a real port, using an SSE client reading multiple chunks and a real WebSocket client connecting, exchanging messages, and closing. Test two subscribers, timeouts, disconnects, errors, and slow networks with finite timeouts; never rely on arbitrary sleeps as proof of delivery.

## 10. Operational concerns required before production

### 10.1. Idle timeouts, heartbeats, proxy buffering

SSE is HTTP streaming. Reverse proxies can buffer data and flush to browsers only once a threshold fills, delaying events; disable stream buffering, set adequate timeouts, and flush frequently. Heartbeat comments `: keepalive` help avoid idle closure, though every proxy has its own settings. WebSockets require proxies supporting Upgrade handshakes, connection timeouts, ping/pong, and controlled termination. Always measure through your actual proxy/load balancer rather than extrapolating from localhost.

Browsers over HTTP/1.1 limit concurrent connections per origin; multiple tabs holding SSE share that connection budget. HTTP/2 multiplexing helps, yet still enforces max concurrent streams. WebSockets also retain a connection/resources per client, so both carry capacity costs at scale.

### 10.2. Security and authorization

- For SSE, native `EventSource` cannot set custom `Authorization` headers. Cookie-based sessions work; cross-origin requires proper CORS/credentials. Avoid placing sensitive tokens in URL query strings whenever alternatives exist.
- WebSockets start with an HTTP handshake. Validate Origin, principal, and channel access, then **continue enforcing authorization per message** inside the handler/protocol. Origin checks do not replace authentication; a valid handshake does not make every subsequent message valid.
- POST endpoints using cookies/sessions normally need CSRF tokens when Spring Security is enabled; missing tokens can return HTTP 403. Combine with rate limits, payload bounds, and publish permissions.
- The demo broadcasts to all sessions. Multi-user/multi-tenant systems must segment audiences, filter events by permission, and revoke access when sessions expire.

### 10.3. Reconnect is not replay

When a stream drops, clients can reconnect, yet events emitted while offline do not reappear automatically. To recover them, persist events in an event store/broker with durable offsets; SSE servers read `Last-Event-ID`, WebSocket apps send a last-seen sequence on reconnect, and replay the missing range. Clients must deduplicate by event ID because reconnects/retries can deliver an event more than once. Choose delivery semantics and idempotency per requirements: updating UI with latest state differs from payment commands that must never run twice.

### 10.4. Scaling, ordering, and slow consumers

```text
Producer → Event broker / durable log
              ├→ Instance A → SSE + WS clients A
              └→ Instance B → SSE + WS clients B
```

Using `ConcurrentHashMap` inside one JVM means a publisher on instance A does not automatically reach clients on instance B. Sticky sessions only keep a client pinned to one node while connected; **they do not solve multi-node broadcasting**. Use Redis pub/sub, Redis Streams, Kafka, RabbitMQ, or another broker suited to your fan-out, persistence, ordering, latency, and cost needs.

Incrementing event IDs on one instance does not guarantee total delivery order when multiple threads publish concurrently. For critical data, define ordering per stream/partition using explicit offsets/versions. For slow consumers, enforce **bounded** queues/buffers, drop/terminate/replay policies, and track latency and memory. Never let one slow client stall the entire broadcast path.

### 10.5. Observability and resource cleanup

Measure open SSE/WS connections, connection lifetimes, reconnect counts, send error rates, fan-out latency, message backlogs, slow-client disconnects, and bytes/messages. Clean up `SseEmitter` on completion/timeout/error; clean up `WebSocketSession` on close/error. Clients leaving a page should call `EventSource.close()` or `WebSocket.close()`. With Spring MVC async SSE, Servlet threads return to the pool while connections remain open, yet sockets and other resources remain allocated; high connection counts require capacity planning.

## 11. Common issues and how to troubleshoot

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| `EventSource` connects but JS misses events | JS uses `onmessage` while server emits named `event: update` | Use `addEventListener("update", ...)` |
| SSE delivers data in delayed batches | Proxy buffering or missing flush | Test `curl -N` directly against instance vs. behind proxy |
| Missed updates after reconnect | Server does not replay from event ID | Add persistence/offsets and inspect `Last-Event-ID` |
| WebSocket fails handshake | Wrong URL, `ws/wss`, Origin, auth, or reverse-proxy Upgrade | Check status and headers in Network → WS |
| Socket closes unexpectedly | Timeout, invalid payload, or server restart | Check close code, server logs, and heartbeats |
| POST returns 403 | CSRF/authorization failure | Include CSRF token and authenticate per policy |
| One node sees messages, another does not | Local in-memory subscriber storage | Check routing and broker fan-out |
| Memory grows over time | Uncleaned emitters/sockets or oversized queues | Check close/error callbacks and connection/buffer metrics |
| Duplicates or out-of-order events | Retries and multiple producers | Use event IDs/versions, ordering, and deduplication |
| Users see other users' data | Unfiltered broadcast | Enforce per-user, tenant, and topic authorization |

## 12. Practice completion checklist

- **SSE:** `GET /api/updates/stream` returns `text/event-stream`, browsers receive `ready` and `update` events, and SSE receives messages published via POST or WebSocket.
- **WebSocket:** HTTP `101` handshake succeeds, clients send raw text messages, receive JSON text frames, and broadcast to other clients.
- **Resilience:** SSE and WebSocket reconnect behaviors differ; the demo has no replay so offline events can be missed.
- **Protocol selection:** SSE for one-way fan-out, WebSocket for bidirectional traffic, STOMP/brokers for complex topics/subscriptions, polling for low change frequency.
- **Production:** plan for auth, Origin/CSRF, proxy timeouts, heartbeats, persistence, multi-instance scaling, slow consumers, and observability.

This practice is complete when you can **demonstrate with browser/Network tab and curl** that both channels work, explain why each fits different requirements, and identify the application-level guarantees still needed for production.

### References

- Spring Framework 6.1 — Async MVC and SSE: https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-ann-async.html
- Spring Framework 6.1 — WebSocket Server: https://docs.spring.io/spring-framework/reference/6.1/web/websocket/server.html
- Spring Framework 6.1 — STOMP over WebSocket: https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp.html
- Spring Framework API — SseEmitter: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html
- WHATWG — Server-sent events: https://html.spec.whatwg.org/multipage/server-sent-events.html
- RFC 6455 — WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455
