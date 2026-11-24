# SSE with Flux and ServerSentEvent in Spring WebFlux

## 1. Scenario and Objectives

A dashboard wants to display real-time notifications when an order changes; an admin page wants to show logs, job progress, stock prices, or task statuses without sending repeated `GET` requests every second. **Server-Sent Events (SSE)** is an HTTP mechanism that allows a server to **push a unidirectional stream of events** to the client over a long-lived response connection. In Spring WebFlux, you can return **`Flux<T>`** with `produces = text/event-stream`, or return **`Flux<ServerSentEvent<T>>`** to control `id`, `event`, `retry`, `comment`, and `data`.

This lesson takes you from the SSE protocol to practical operation with **Java 17+, Spring Framework 6.x, and Spring Boot 3.x**. Upon completion, you will be able to:

1. Read `text/event-stream` properly, including `data:`, `id:`, `event:`, `retry:`, comment lines `:`, and the blank line that terminates an event.
2. Explain `Flux<ServerSentEvent<T>>` and the **non-blocking HTTP response streaming** mechanism in Spring WebFlux; distinguish it from `Mono<T>`, regular JSON responses, and MVC `SseEmitter`.
3. Create finite/long-lived SSE controllers, setting event IDs, named events, event data, retry delays, and heartbeats.
4. Connect from the browser using **`EventSource`**, handling named events, `onerror`, `readyState`, automatic reconnection, and `close()`.
5. Understand **`Last-Event-ID`**, replay checkpoints, ordering, and at-least-once/duplicate/out-of-order caveats; recognize that SSE **does not include a built-in durable event log**.
6. Distinguish per-client cold publishers like `Flux.interval` from hot shared sources (`Sinks.Many`), and manage backpressure, slow consumers, memory, and cancellation.
7. Configure reverse proxies, timeouts, keep-alive, CORS/cookies, authorization, content security, and connection limits.
8. Run a Spring Boot WebFlux application with `/api/events/history` and `/api/events/ticks` endpoints, an EventSource web page, and HTTP tests with `WebTestClient`.
9. Know when to choose SSE, WebSocket, polling, or a message broker.

**Scope:** WebFlux reactive stack (`spring-boot-starter-web` is not needed). The examples use browser EventSource and GET endpoints; they do not promise exactly-once delivery or durable replay without a backing event store. Snippets labeled "illustrative" require external dependencies before use, whereas the group of files in Section 11 forms a standalone runnable practice example when placed in a Spring Boot 3.x Maven project with the listed dependencies.

## 2. What Is SSE? Why Is It Still HTTP?

SSE uses a regular **HTTP GET**, with the response:

~~~http
GET /api/events/history HTTP/1.1
Host: localhost:8080
Accept: text/event-stream
~~~

The server responds:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream;charset=UTF-8
Cache-Control: no-cache

id: 1
event: news
retry: 2000
data: news-1

id: 2
event: news
retry: 2000
data: news-2

~~~

Following the headers are UTF-8 lines. **A blank line** separates two events. The server can keep writing subsequent events without ending the response. Unlike polling, the client does not have to create a new request for each update; unlike WebSocket, the client and server do not exchange bidirectional messages over the same SSE channel.

SSE does not introduce a "new TCP protocol": it runs over HTTP, uses standard HTTP proxies/firewalls/observability, yet remains subject to HTTP response buffering, idle timeouts, and connection limits.

### Unidirectional SSE

| Need | SSE | WebSocket | Polling |
| --- | --- | --- | --- |
| Server continuously pushes updates | Very suitable | Suitable | Possible, but expensive in requests |
| Client sends real-time messages on the same connection | No | Yes | Creates separate HTTP requests |
| Simple browser API | `EventSource` | `WebSocket` | `fetch`/XHR |
| Default reconnection in the browser | Yes, with EventSource rules | App designs its own | App schedules its own |
| Standardized event ID/retry | Built-in SSE fields | App defines its own | App defines its own |
| Each stream corresponds to an HTTP GET | Yes | Separate handshake/connection | Many GETs |
| Guaranteed durable replay | Not built-in | Not built-in | Depends on server |
| Direct binary transfer by protocol | No (UTF-8 text) | Has binary frames | HTTP supports binary |

If the application needs to send cursors/input/actions to the server, it can still **POST via another HTTP endpoint** while EventSource receives notifications via GET. If the client must send many real-time messages continuously and receive corresponding server responses, consider WebSocket.

## 3. The `text/event-stream` Wire-Level Format

According to the SSE specification and MDN documentation, the stream must be UTF-8 encoded. Each event consists of **structured lines**, terminated by **a blank line**. Important fields:

| Field | Role | Notes |
| --- | --- | --- |
| `data: ...` | Event payload | Multiple data lines are joined by newline characters |
| `event: news` | Event type / named event | Browser uses `addEventListener("news", handler)` |
| `id: 42` | Event ID | Browser remembers this so it can send `Last-Event-ID` on reconnect |
| `retry: 3000` | Reconnect delay hint in **milliseconds** | Valid integers only; not the server timeout |
| `: comment` | Comment | Does not dispatch a message; suitable for heartbeats |
| Blank line | Ends the event | If missing, the client may not dispatch the event yet |

An event without `event:` is processed as a **`message` event**; the browser attaches handlers via `onmessage` or `addEventListener("message", ...)`. If `event: news` is present, it becomes a named event **`news`**, and **does not** automatically invoke `onmessage` for that same event.

### 3.1. An Event with Multiple Data Lines

~~~text
event: notice
id: 17
data: line one
data: line two

~~~

The browser receives `event.data` equivalent to:

~~~text
line one
line two
~~~

The trailing blank line only terminates the event; it is not part of the content. Handling newlines in data requires the encoder/server to serialize properly rather than concatenating raw user input directly into the wire format.

### 3.2. `id` and `retry`

~~~text
id: 18
retry: 5000
data: pending

~~~

The browser can remember ID **18** and use a reconnect time of **5000 ms**. However, `retry` is neither a heartbeat interval nor a guarantee that the server will emit ID 19 next. Event IDs must be designed alongside storage/replay semantics.

An empty `id:` has the semantics of **clearing the last-event-id** in the EventSource specification. Do not intentionally emit an empty ID when you need cursor recovery.

### 3.3. Comment-Only Heartbeat

~~~text
: keep-alive

~~~

A line starting with `:` is a comment and does not create a regular message, but helps **send periodic bytes** to detect disconnects or avoid some idle timeouts. The heartbeat must actually be flushed through the server/proxy; if nginx/gateway buffers the entire response before sending, the client still receives nothing.

### 3.4. Never Concatenate Untrusted Data into Event Frames

Wrong:

~~~java
String raw = "data: " + untrustedInput + "\n\n";
~~~

If the input contains newlines and fake `event:` or `id:` lines, you can alter SSE framing. Use `ServerSentEvent.builder().data(...)` or a properly configured codec to serialize. When the content is JSON, use a DTO/JSON encoder and ensure the client renders safely.

## 4. Emitting SSE with Flux in Spring WebFlux

An illustrative controller:

~~~java
@RestController
class DemoSseController {

    @GetMapping(path="/updates",
            produces=MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<String> updates() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(index -> "update-" + index);
    }
}
~~~

This is an **illustrative** class that requires imports and a Boot WebFlux project. WebFlux subscribes to the Publisher, encodes each string into an SSE `data:` frame, and sends it incrementally instead of waiting for the Flux to complete. Specifying `produces=text/event-stream` is crucial when not using the `ServerSentEvent` wrapper.

With the dedicated wrapper:

~~~java
@GetMapping(path="/events",
        produces=MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(i -> ServerSentEvent.<String>builder()
                    .id(Long.toString(i))
                    .event("tick")
                    .retry(Duration.ofSeconds(3))
                    .data("tick-" + i)
                    .build());
}
~~~

The snippet above is an **illustrative method in a WebFlux controller**, not a standalone project. `ServerSentEvent` resides in **`org.springframework.http.codec.ServerSentEvent`**; it uses a fluent builder: `id`, `event`, `retry(Duration)`, `comment`, `data`, `build`.

If the browser client uses `source.onmessage = ...` while the server emits `event("tick")`, the `onmessage` handler will **not** catch the named event; you must use `source.addEventListener("tick", ...)`.

### 4.1. Finite and Infinite `Flux`

- `Flux.range(1, 5)` has 5 items and completes; suitable for demos/history/tests.
- `Flux.interval(Duration.ofSeconds(1))` is an endless tick sequence by default, continuing until cancellation/disconnect or server stop.
- `Flux.interval(...).take(3)` emits exactly three ticks, then completes; suitable for deterministic tests on item counts.
- When the server completes a finite stream, browser `EventSource` usually **auto-reconnects**, because connection termination can be interpreted as a failure; for finite streams, the client should call **`close()`** once it has received all expected elements.
- An infinite Flux does not automatically mean the server has a durable event log; when a client loses network connectivity, events between two connections may be lost.

### 4.2. Never Call `block()` or `subscribe()` in a Handler

Wrong:

~~~java
@GetMapping("/wrong")
String wrong() {
    return remoteService.load().block();
}
~~~

On the Reactor Netty event-loop, `.block()` can throw `IllegalStateException` or cause blocking that degrades throughput. Calling `subscribe()` manually inside a controller prevents the framework from managing the task's lifecycle/cancellation. The right approach is to **return the composed `Flux`/`Mono`** so WebFlux subscribes to it.

If the source is a blocking library, you may need `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; that is an **offloading** mechanism and does not turn a blocking JDBC/file SDK into a non-blocking API. Bounding tasks/queues/downstream connection pools remains mandatory.

## 5. Browser EventSource

In the browser:

~~~javascript
const source = new EventSource("/api/events/history");

source.addEventListener("news", (event) => {
  console.log("ID:", event.lastEventId);
  console.log("Data:", event.data);
});

source.onerror = (event) => {
  console.warn("SSE disconnected or failed", source.readyState);
};

// Call when monitoring is no longer needed:
source.close();
~~~

Key points to understand:

- `EventSource(url)` opens an HTTP **GET**. JavaScript **cannot** choose POST, a request body `Content-Type`, or binary frames.
- The browser may automatically reconnect when the connection breaks or the server closes it, following the EventSource algorithm.
- `event.lastEventId` indicates the last event ID associated with the dispatched event.
- `source.readyState`: `0=CONNECTING`, `1=OPEN`, `2=CLOSED`. `onerror` does not always mean the stream has permanently ended.
- `close()` closes the connection and prevents reconnection. It should be called on component unmount, tab/page navigation, or upon receiving a terminal event.
- Standard EventSource **does not allow arbitrarily adding custom HTTP headers** to the request from its constructor, such as `Authorization: Bearer ...`. For bearer-token auth, another approach may be needed (same-origin cookie with CSRF/CORS policy, `fetch` streaming parser, or short-lived ticket) along with an appropriate security design.
- You can use `new EventSource(url, { withCredentials: true })` where CORS credentialed requests are permitted and cookies satisfy SameSite/Secure. Never use `Access-Control-Allow-Origin: *` with credentials.

### 5.1. Named Events Differ from `onmessage`

Server:

~~~text
event: progress
data: 25

event: progress
data: 50

event: done
data: finished

~~~

Browser:

~~~javascript
source.addEventListener("progress", (e) => {
  console.log("Progress:", e.data);
});
source.addEventListener("done", () => source.close());
~~~

Do not expect `onmessage` to receive `progress` events. If you want a unified handler, you must subscribe to the appropriate event names or emit defaults without an `event:` field.

### 5.2. Rendering Event Data Safely

Do not do:

~~~javascript
result.innerHTML = event.data;
~~~

If the server reflects unsanitized user input in `event.data`, HTML injection can lead to XSS. For text messages:

~~~javascript
result.textContent = event.data;
~~~

For JSON, parse with `JSON.parse(e.data)`, validate schema/type/limits, and render each value via `textContent` or framework escaping. EventSource does not replace CSP policies, authentication, authorization, or context-aware output encoding.

## 6. Last-Event-ID, Resume, and Delivery Semantics

When the server sends:

~~~text
id: 102
event: news
data: updated

~~~

The browser, following the EventSource algorithm, can remember `102`. If the connection drops, the new request typically includes:

~~~http
GET /api/events/history HTTP/1.1
Accept: text/event-stream
Last-Event-ID: 102
~~~

**However, the protocol only provides a cursor**; it does not automatically store events 103, 104, 105 on the server. To resume properly, the server must have a **reliable replay source** and understand the ID:
- Append-only database/event log (with retention).
- Kafka partition/topic by key and offset matching the consumer contract.
- Redis Streams with stream IDs and retention policies.
- Event store with global/per-user sequence numbers and the ability to query `WHERE id > lastId`.

If the server simply uses `Flux.interval` to generate fresh data per subscriber, IDs `0,1,2` of connection A **do not mean** connection B can recover what A missed. Do not use timer indexes as global durable event IDs.

### 6.1. Replay Must Handle Duplicates and Gaps

Suppose a client receives and displays event #42 but disconnects before persisting its processing state. Upon reconnect, the server might resend #42 or #43 depending on when the ID was updated/synchronized by the browser. This requires:
- Event IDs that are stable and meaningful within the domain/stream scope.
- **Idempotent** client processing, or skipping already-seen IDs per policy.
- Server explicitly defining **exclusive resume** (typically `id > Last-Event-ID`) versus inclusive semantics.
- Handling **stale cursors** (past retention): requiring a full resync/snapshot or returning an intentional API error.
- **Authorization during replay**: tenant A's ID must never allow tenant B to read tenant A's events.
- Do not promise "exactly-once" without true transactions/idempotency/state acknowledgement.
- Across multiple partitions/users, ordering can only be guaranteed within an application-defined key/partition/stream, not globally by default.

### 6.2. DB Logic Example, Not a Runnable Controller

~~~java
Flux<Notification> replayAfter(String principalId, long lastSeenId) {
    return notificationRepository
            .findAuthorizedAfter(principalId, lastSeenId);
}
~~~

This is a business-model snippet that depends on a real reactive repository. Queries must filter by authorization/tenant, order by a reliable sequence, and enforce batch limits/read timeouts. If you need to **combine replay with a live stream**, you must prevent the race condition "after the query finishes but before subscribing to live" using a cursor + atomic subscribe/snapshot or by treating the event log as the single source of truth. A naive `Flux.concat(replay, live)` can miss events in the seam if there is no synchronization mechanism.

## 7. Heartbeat, Flush, and Disconnect Detection

SSE is a typically long-lived connection. Various layers may close the connection if no data flows for too long:
- Load balancer idle timeout.
- CDN/reverse proxy response timeout.
- NAT or intermediaries.
- Browser/mobile network loss.
- Container/server write error when the client has already left.

According to the Spring WebFlux reference, when streaming you should emit data periodically to **detect client disconnects sooner**. An SSE heartbeat as a comment:

~~~java
Flux<ServerSentEvent<String>> heartbeats =
        Flux.interval(Duration.ofSeconds(15))
                .map(i -> ServerSentEvent.<String>builder()
                        .comment("keep-alive")
                        .build());
~~~

The above is a Reactor snippet, not a standalone controller. When merging with notifications, combine a heartbeat publisher with a notifications source:

~~~java
Flux<ServerSentEvent<String>> stream =
        Flux.merge(notifications, heartbeats);
~~~

Assuming `notifications` is a real declared publisher. Do not use `heartbeats` as a mechanism to repeat business events: comment-only events are not dispatched as `message` in the browser. Heartbeats are a connection-probing protocol; when the producer goes long without events, sending a small comment is better than staying silent for minutes.

**Practical configuration note:** a 15–30 second heartbeat is only an example; make sure it is shorter than the actual idle timeout across the entire HTTP path while staying within bandwidth/connection cost budgets. If a proxy buffers data, heartbeats must actually be forwarded/flushed, not merely generated in the Reactor pipeline.

## 8. Cold Flux vs. Hot Publisher: One Connection or Many Subscribers?

### 8.1. `Flux.interval` Usually Has a Separate Sequence per Subscription

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
~~~

Each time a client subscribes, `Flux.interval` creates a timer sequence per subscription; multiple clients may each see `0,1,2,...`. This is fine for demos/per-client timers, but cannot represent shared business updates with a single global monotonic ID.

With 10,000 EventSource clients, 10,000 per-client intervals/subscriptions still incur scheduling and connection management overhead, even without holding 10,000 blocking Servlet threads. Control global connection limits and broadcast architecture.

### 8.2. `Sinks.Many` for a Hot Source

An illustrative pattern in a Spring service:

~~~java
@Service
class NewsHub {

    private final Sinks.Many<String> sink =
            Sinks.many().multicast().directBestEffort();

    public Flux<String> events() {
        return sink.asFlux();
    }

    public boolean publish(String message) {
        Sinks.EmitResult result = sink.tryEmitNext(message);
        return result.isSuccess();
    }
}
~~~

This is an **illustrative class** requiring imports for `@Service`, `Sinks`, `Flux`, and a real producer. `directBestEffort` does not cache history and may **drop for slow subscribers** so other subscribers still receive events. `tryEmitNext` can return `FAIL_ZERO_SUBSCRIBER`, `FAIL_OVERFLOW`, `FAIL_NON_SERIALIZED`, or other statuses; do not treat `publish=true` as durable persistence.

If multiple producers emit into the same sink concurrently, `Sinks` detects concurrent emission and may reject non-serialized signals. Serialize producers or handle `EmitResult` with metrics/bounded retries per policy—never spin endlessly on the event loop.

### 8.3. Different Sink Types

| Sinks.Many | Meaning | Trade-off |
| --- | --- | --- |
| `multicast().directBestEffort()` | Best effort; slow subscribers may miss items | Not for durable/reliable delivery |
| `multicast().directAllOrNothing()` | If one subscriber has no demand, events may be dropped for all | One slow consumer affects the whole group |
| `multicast().onBackpressureBuffer()` | Has a buffer and demand coordination | Must choose bounded size, overflow policy, and avoid slow subscribers stalling things |
| `replay().limit(n)` | Replays the last n items to late subscribers | In-memory cache only, resets on restart, not durable |
| Event log DB/Kafka/Redis Streams | Queries durable history by cursor | Adds storage/retention/authorization/ordering complexity |

A **sink is an event-emitting source**, not a database. Multi-pod deployments do not automatically see the same events just because each pod creates a singleton sink; broker/stream distribution or valid sticky routing is required.

## 9. Backpressure and Slow Clients in SSE

Reactive Streams provides backpressure: downstream requests `request(n)`, and upstream produces in a controlled manner when capable. However, **HTTP SSE/EventSource has no per-event business acknowledgement**. When a browser reads slowly or TCP buffers fill up, backpressure may appear at the HTTP output/writer, while an upstream event log or external producer may still keep emitting continuously.

Issues to evaluate:

- Each SSE client is a long-lived connection with network/file-descriptor/memory overhead.
- Clients on mobile networks or background-throttled tabs may read slowly.
- If per-client queues are unbounded, memory grows with client count × lag.
- If events are dropped, downstream may experience **ID gaps**; the client must detect/resync.
- If slow clients are terminated, browsers auto-reconnect, creating a **reconnect storm** if there is no backoff/rate control.
- If a shared sink buffer faces backpressure from a slow subscriber, **all** subscribers can be impacted.
- If producers publish unpersisted events and the SSE connection drops, events can be lost without a durable store.

### Operator Patterns

~~~java
Flux<ServerSentEvent<String>> result =
        source.onBackpressureLatest()
              .map(v -> ServerSentEvent.<String>builder(v).build());
~~~

This snippet assumes `source` is a real publisher. `onBackpressureLatest` may drop intermediate values, making it suitable only when **only the latest state matters** (such as displayed temperature/price), and **unsuitable** for payment transactions or events that must not be lost. Do not pick a drop/overflow policy merely because it keeps a dashboard looking "smooth".

If every event must be replayable: use a durable log and cursor, emitting boundedly as the client demands. If demand cannot be kept up with, proactively close the stream or send a resync signal rather than keeping an unbounded queue.

## 10. Security, Cookies, CORS, and Reverse Proxies

### 10.1. Authorization for Long-Lived HTTP GETs

SSE is usually a GET, yet URLs can expose sensitive data. Rules:
1. Authenticate and authorize **before** subscribing to the event source.
2. On replay, check permissions **per event/tenant** or enforce properly scoped queries—do not rely solely on `Last-Event-ID`.
3. Do not embed secrets/tokens or PII in event IDs unnecessarily; `id` may appear in logs/headers.
4. If permissions are revoked while a connection remains open, design re-evaluation/forced disconnect and subscription revocation.
5. Never use a singleton `Sinks.Many<UserMessage>` to broadcast every user's messages to all listeners without permission filtering.
6. Avoid putting bearer tokens in URL query strings, as URLs are easily logged/leaked via analytics/referrer/history. Standard EventSource does not support custom auth headers; choose cookie/session or a carefully designed alternative.

### 10.2. CORS and Credentialed EventSource

~~~javascript
const source = new EventSource(
  "https://api.example.com/api/events/ticks",
  { withCredentials: true }
);
~~~

This is an **illustrative URL example** and will not work with the local demo without CORS/HTTPS configuration. The backend must explicitly allow the specific `Origin`, credentials, and valid cookie policy. Never set `Access-Control-Allow-Origin: *` when requests use credentials; address `SameSite`, `Secure`, HTTPS, and CSRF policies according to your threat model.

SSE is only a server → browser channel. If the page uses a separate POST to create work, a cookie-authenticated POST requires CSRF protection like any normal unsafe request.

### 10.3. Proxy Buffering and Idle Timeout

Some reverse proxies/CDNs may buffer HTTP responses. Even when the server has emitted an event, the browser receives nothing until the buffer fills or the connection closes. Verify and configure each layer individually:
- Proper Content-Type: **`text/event-stream; charset=UTF-8`**.
- Disable response buffering for the SSE route at the proxy if needed (for instance, some nginx configurations use `proxy_buffering off`; the `X-Accel-Buffering: no` header only works on layers that actually support it).
- Idle timeout **greater than the heartbeat interval**; check ingress, LB, CDN, app server, and mobile carriers.
- Ensure streaming actually flushes to the client; avoid compression/buffering that batches multiple events and introduces delay.
- `Cache-Control: no-cache` or an appropriate policy to prevent caches/intermediaries from improperly reusing a response stream. This is not `no-store` and does not solve auth/caching on its own.
- Connection limits/HTTP/2 multiplexing: HTTP/1.1 browsers typically limit parallel connections per origin, so multiple EventSource tabs can compete for connection slots; HTTP/2 negotiates concurrent streams differently. Do not assume HTTP/2 allows unlimited streams.
- Observability: measure bytes/second, concurrent SSE connections, drop/reconnect rate, response status, and disconnect causes.

Do not assume `Flux<ServerSentEvent>` automatically fixes gateway configuration or enables proxy streaming if the proxy layer has buffering enabled.

## 11. Runnable Spring Boot 3.x + Java 17 Example

To learn the protocol/replay without depending on a DB/message broker, the practice app uses a **fixed list of events 1..5**. The controller provides:

- `GET /api/events/history`: finite `Flux<ServerSentEvent<String>>`. With `Last-Event-ID`, returns events whose ID is greater than the received ID. This is **only an in-memory lesson dataset**; if deployment restarts while data changes, this code no longer proves durable replay.
- `GET /api/events/ticks`: `Flux<ServerSentEvent<String>>` running once per second, emitting events named `tick`. This is a **per-subscription** timer and promises neither a global sequence nor replay.
- `GET /` serves a static HTML file with `EventSource` connecting to history/ticks.
- `WebTestClient` integration tests against a real HTTP server, asserting named event ID/data, Last-Event-ID, and validation.
- No security, Redis, Kafka, reverse proxy, or DB is used, because the goal is to understand SSE wire format/lifecycle deterministically.

### 11.1. Creating the Project

Spring Initializr: Maven, Java 17+, Spring Boot **3.x**, dependencies `Spring Reactive Web` (artifact `spring-boot-starter-webflux`), and `Spring Boot Starter Test`.

Snippet in `pom.xml` generated by Spring Initializr:

~~~xml
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
~~~

This is a **dependencies snippet**, not a full Maven file (parent/BOM/compiler/spring-boot-maven-plugin are already in the skeleton generated by Initializr). Do not add `spring-boot-starter-web` because Boot 3.x typically selects Spring MVC when both MVC and WebFlux are on the classpath.

File structure:

~~~text
src/main/java/com/example/demo/
  DemoApplication.java
  NewsEventsController.java
src/main/resources/static/
  index.html
src/test/java/com/example/demo/
  NewsEventsControllerTest.java
~~~

### 11.2. DemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.3. NewsEventsController.java

~~~java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/events")
public class NewsEventsController {

    private static final int LAST_DEMO_ID = 5;

    @GetMapping(path = "/history",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> history(
            @RequestHeader(name = "Last-Event-ID",
                    required = false) String lastEventId) {

        int afterId = parseCursor(lastEventId);

        return Flux.range(afterId + 1, LAST_DEMO_ID - afterId)
                .delayElements(Duration.ofMillis(60))
                .map(id -> ServerSentEvent.<String>builder()
                        .id(Integer.toString(id))
                        .event("news")
                        .retry(Duration.ofSeconds(2))
                        .data("news-" + id)
                        .build());
    }

    @GetMapping(path = "/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ticks() {

        return Flux.interval(Duration.ofSeconds(1))
                .map(index -> ServerSentEvent.<String>builder()
                        .event("tick")
                        .comment("per-subscriber demo timer")
                        .data("tick-" + index)
                        .build());
    }

    private static int parseCursor(String value) {
        if (value == null || value.isBlank()) {
            return 0;
        }
        try {
            int id = Integer.parseInt(value);
            if (id >= 0 && id <= LAST_DEMO_ID) {
                return id;
            }
        } catch (NumberFormatException ignored) {
            // Return 400 below for malformed or non-numeric IDs.
        }
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid Last-Event-ID");
    }
}
~~~

**Step-by-step analysis:**

1. `history` accepts `Last-Event-ID` as an optional **HTTP request header**. If absent, it defaults to `0` in this dataset; any value not an integer in 0..5 is rejected with **400**.
2. `Flux.range(afterId+1, 5-afterId)` emits integers from the next ID through 5. With `Last-Event-ID: 3`, it emits **4,5**; with 5, it emits an empty Flux.
3. `delayElements(60ms)` is only so curl/browsers can observe streaming over time; it does not simulate a durable queue. Tests may wait up to 5 seconds.
4. `ServerSentEvent.<String>builder().id(...).event("news").retry(...).data(...).build()` creates a proper frame with ID, named event, and data.
5. `ticks` is an infinite cold timer per subscription and omits IDs because per-subscriber indexes are not a global log cursor.
6. The controller does **not** subscribe manually; WebFlux manages subscribing, writing, and cancelling when the connection closes.
7. `parseCursor` constrains input so an arbitrary header cannot alter the demo scope. Production cannot rely solely on validating a numeric range if the event log has complex namespaces/authorization/retention.
8. `Thread.sleep` is not used on the Netty event-loop; Reactor timer scheduling does not hold a blocked thread per tick.
9. Event data values are short, fixed `String`s. With DTOs/JSON, `ServerSentEvent<SomeRecord>` works similarly if codecs are configured, though the client needs `JSON.parse`.
10. `Cache-Control`/CORS/security/proxy deployment are not built into this demo. Production must configure those layers and test through actual ingress.

### 11.4. index.html: Browser Client

`src/main/resources/static/index.html`

~~~html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Spring WebFlux SSE Demo</title>
</head>
<body>
  <h1>SSE Notifications</h1>
  <p id="state">Not connected</p>
  <ul id="news"></ul>
  <button id="startTicks">Start live ticks</button>
  <button id="stopTicks">Stop live ticks</button>
  <ul id="ticks"></ul>

  <script>
    const state = document.getElementById("state");
    const news = document.getElementById("news");
    const ticks = document.getElementById("ticks");

    // Finite stream; close at event ID 5 to prevent a reconnect loop.
    const history = new EventSource("/api/events/history");

    history.onopen = () => {
      state.textContent = "Receiving history";
    };
    history.addEventListener("news", event => {
      const li = document.createElement("li");
      li.textContent = event.lastEventId + ": " + event.data;
      news.appendChild(li);

      if (event.lastEventId === "5") {
        history.close();
        state.textContent = "Received all five events";
      }
    });
    history.onerror = () => {
      if (history.readyState !== EventSource.CLOSED) {
        state.textContent = "Disconnected, browser may retry";
      }
    };

    let live = null;
    document.getElementById("startTicks").onclick = () => {
      if (live !== null) return;

      live = new EventSource("/api/events/ticks");
      live.addEventListener("tick", event => {
        const li = document.createElement("li");
        li.textContent = event.data; // do not use innerHTML
        ticks.appendChild(li);
      });
      live.onerror = () => {
        // Browser handles reconnect; log/observe if needed.
        console.warn("tick stream disconnected");
      };
    };
    document.getElementById("stopTicks").onclick = () => {
      if (live !== null) {
        live.close();
        live = null;
      }
    };
    window.addEventListener("beforeunload", () => {
      history.close();
      if (live !== null) live.close();
    });
  </script>
</body>
</html>
~~~

**Design notes:**
- Once the final ID `5` is received, the code calls **`history.close()`** because the history endpoint is finite. Otherwise, EventSource could reconnect after the server completes.
- `tick` is a named event, so `addEventListener("tick", ...)` is required.
- `textContent` avoids passing SSE data directly into the HTML parser; if rendering rich HTML, you must sanitize and enforce output encoding/CSP.
- `stopTicks` closes the subscription/connection, freeing browser/server resources sooner.
- The `live` code does not guard against rendering millions of `li` elements if left open for hours; production needs to **cap rendered items** or use a virtualized list. UI memory is also a resource to monitor.
- Do not assume an EventSource reconnect guarantees the server replayed all missing data; the history demo only replays five fixed IDs.

### 11.5. NewsEventsControllerTest.java

The tests use **WebTestClient** over an embedded HTTP server to read a finite stream into typed `ServerSentEvent<String>` values. Never connect to infinite `ticks` and try to wait for it to `complete`.

~~~java
package com.example.demo;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class NewsEventsControllerTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void emitsFiveNamedEventsWithIdsAndRetry() {
        List<ServerSentEvent<String>> received =
                client.get()
                        .uri("/api/events/history")
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .exchange()
                        .expectStatus().isOk()
                        .expectHeader().contentTypeCompatibleWith(
                                MediaType.TEXT_EVENT_STREAM)
                        .returnResult(
                            new ParameterizedTypeReference<
                                ServerSentEvent<String>>() {})
                        .getResponseBody()
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertNotNull(received);
        assertEquals(5, received.size());

        ServerSentEvent<String> first = received.get(0);
        assertEquals("1", first.id());
        assertEquals("news", first.event());
        assertEquals("news-1", first.data());
        assertEquals(Duration.ofSeconds(2), first.retry());

        ServerSentEvent<String> last = received.get(4);
        assertEquals("5", last.id());
        assertEquals("news-5", last.data());
    }

    @Test
    void lastEventIdRequestsOnlyEventsAfterCursor() {
        List<ServerSentEvent<String>> received =
                client.get()
                        .uri("/api/events/history")
                        .header("Last-Event-ID", "3")
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .exchange()
                        .expectStatus().isOk()
                        .returnResult(
                            new ParameterizedTypeReference<
                                ServerSentEvent<String>>() {})
                        .getResponseBody()
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertNotNull(received);
        assertEquals(2, received.size());
        assertEquals("4", received.get(0).id());
        assertEquals("5", received.get(1).id());
    }

    @Test
    void malformedCursorIsBadRequest() {
        client.get()
                .uri("/api/events/history")
                .header("Last-Event-ID", "abc")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void liveTimerProducesEventsWithoutWaitingForCompletion() {
        List<ServerSentEvent<String>> received =
                client.get()
                        .uri("/api/events/ticks")
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .exchange()
                        .expectStatus().isOk()
                        .returnResult(
                            new ParameterizedTypeReference<
                                ServerSentEvent<String>>() {})
                        .getResponseBody()
                        .take(2)
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertNotNull(received);
        assertEquals(2, received.size());
        assertEquals("tick", received.get(0).event());
        assertEquals("tick-0", received.get(0).data());
        assertEquals("tick-1", received.get(1).data());
    }
}
~~~

Test highlights:
- For a finite stream, `collectList()` completes only after the last event; a timeout is needed to keep tests from hanging if code is changed to an infinite stream.
- For an infinite stream, **`take(2)` limits items and cancels the subscription** after two items; never call `collectList()` on an infinite Flux.
- Assert `id`, `event`, `data`, and `retry` instead of relying on raw byte output snippets whose whitespace/codec formatting may vary.
- `Last-Event-ID: 3` yields events 4,5 per the demo contract. This is fixed-dataset replay logic, not message durability.
- The HTTP server runs on a random port with `bindToServer`, unlike testing the controller directly; **this test does not simulate reverse proxies/CDNs**. Testing streaming through real ingress is still needed separately.
- `.block(Duration)` is used **only on the JUnit test thread** to await results; never call `.block()` in a WebFlux event-loop controller.

To run:
~~~bash
./mvnw test
~~~

On Windows:
~~~powershell
.\mvnw.cmd test
~~~

If there is no Maven wrapper, run `mvn test` with an installed Maven. Test timeouts here guard the JUnit run; they do not prove production SLA/liveness.

## 12. Testing with curl and Observing the Wire Format

Start the application:

~~~bash
./mvnw spring-boot:run
~~~

Read history:

~~~bash
curl -N -i   -H "Accept: text/event-stream"   http://localhost:8080/api/events/history
~~~

Illustrative output (other headers omitted):

~~~text
id:1
event:news
retry:2000
data:news-1

id:2
event:news
retry:2000
data:news-2

~~~

The actual codec may include spaces after `:` or reorder fields, yet semantics must remain identical. curl's `-N` disables stdout buffering, letting you see events arrive incrementally. Running `curl` without `-N` may appear stalled by output buffering even though the server is actively streaming.

Test resume:

~~~bash
curl -N -i   -H "Last-Event-ID: 3"   -H "Accept: text/event-stream"   http://localhost:8080/api/events/history
~~~

The stream returns **IDs 4 and 5**, without re-emitting 1–3. This holds specifically due to the demo contract.

Watch live ticks:

~~~bash
curl -N -H "Accept: text/event-stream"   http://localhost:8080/api/events/ticks
~~~

In the terminal, press `Ctrl+C` to actively disconnect; the server should receive a cancellation/connection-closed signal and stop the subscription. Do not leave CLI/tests open indefinitely and conclude the server leaks when the connection was never closed.

Invalid cursor:

~~~bash
curl -i   -H "Last-Event-ID: abc"   http://localhost:8080/api/events/history
~~~

The endpoint returns **400 Bad Request** per `parseCursor`.

**Shell note:** multiline examples using `\` are for Linux/macOS/Git Bash. In Windows PowerShell, use `curl.exe` on a single line or appropriate line-continuation syntax.

## 13. Error Handling: Before and After the Response Is Committed

When a controller returns a Publisher, **errors can occur**:
1. Before HTTP response headers: failing to parse `Last-Event-ID` → can return **400** like a normal API.
2. After emitting the 100th event: response headers are already committed, so the server cannot arbitrarily switch to an HTTP 500 JSON body within the same response. The connection may terminate/fail and the browser will reconnect.
3. Inside a `WebClient`/database/message broker source: distinguish recoverable vs. fatal errors. If you want to emit an **application-level error event** and close the stream, you can `onErrorResume` to a custom-protocol `error` event, without leaking exception stack traces or credentials to the client.
4. Client disconnect: the Reactor subscription normally cancels; the source must release DB cursors, broker subscriptions, and resources via `doFinally`/`usingWhen` as needed.

Illustrative example:

~~~java
return source
        .map(message -> ServerSentEvent.<String>builder()
                .event("news")
                .data(message)
                .build())
        .onErrorResume(ex ->
                Flux.just(ServerSentEvent.<String>builder()
                        .event("stream-error")
                        .data("Temporary stream error")
                        .build()));
~~~

This snippet is not standalone-runnable because `source` is undeclared. After emitting `stream-error`, the stream usually completes; the client must decide whether to resubscribe, display a UI error, or perform a full resync. **Never** send `ex.getMessage()` raw if exceptions might contain internal service details/tokens/PII.

### 13.1. Retry Storm

If 5,000 browser clients reconnect together after an outage, all of them may issue GET requests almost simultaneously. `retry: 1000` does not prevent server saturation. You need:
- Rate limiting/admission control at ingress.
- Server/client retry/backoff/jitter policies where controllable.
- Avoiding heavy subscription setup.
- Shared event storage and suitable incremental catch-up.
- Capacity/load testing with reconnect bursts.
- Never creating unbounded new connection pools/tracing objects per reconnect.

Browser EventSource's built-in `retry` cannot express complex jitter policies through a single field. If specialized behavior is required, application-level connection management may need a different transport/client.

## 14. SSE and the Transaction/Event Outbox

Example: a REST POST creates an order in the database, and a notification is then pushed via SSE. If code emits the event **before DB commit**, the browser could receive "order-created" while the transaction rolls back. If it emits **after commit** but the server crashes before publishing, the event is lost.

A more reliable architecture:

~~~text
HTTP POST /orders
     |
     v
DB transaction: orders row + outbox_event row
     |
     +---- COMMIT
               |
               v
Outbox publisher/broker
               |
               v
Durable event stream
               |
               +---- replay after Last-Event-ID
               |
               v
Authorized SSE subscriptions (per user / tenant)
               |
               v
Browser EventSource
~~~

Outbox handles consistency between DB changes and notification workflows better than "save to DB then fire-and-forget `sink.tryEmitNext`". Still, you must address duplicate delivery, retention, authorization, crashes/restarts, message ordering, and poison messages.

### Last-Event-ID and DB Cursor

SQL example assuming `notification_events(id BIGINT, owner_id, payload)`:

~~~sql
SELECT id, payload
FROM notification_events
WHERE owner_id = :ownerId
  AND id > :lastEventId
ORDER BY id ASC
LIMIT :batchSize;
~~~

The variables are DB driver bind parameters, never concatenated strings from headers. Even if global IDs have gaps, the query still returns events with larger IDs in order. `LIMIT` bounds batch memory, while the server must loop until caught up with the log and then transition to a live tail **without missing the overlap boundary**.

Some stream IDs from Kafka/Redis are not system-wide monotonically increasing integers. `Last-Event-ID` is an opaque string to the SSE protocol; an application can use a composite/versioned token cursor (containing no secrets) and parse it in its own format.

## 15. Observability, Optimization, and Resource Limits

Every SSE connection is long-lived; HTTP server request latency metrics may reflect **connection open duration** rather than per-event latency. Measure:

| Metric | What it tells you |
| --- | --- |
| `sse_connections_active` | How many subscribers/connections are currently active |
| `sse_subscribe_rate` | Rate of new connections/reconnects |
| `sse_disconnections_total` | Clients leaving, network errors, proxy timeouts |
| `sse_heartbeat_gap_seconds` | Whether heartbeats are sent/flushed on time |
| `sse_event_lag_ms` | Time from event source timestamp to client receipt (if measurable) |
| `sse_events_dropped_total` | Events lost due to sink/operator policy |
| `sse_replay_requests_total` | Volume of reconnects/replays |
| `sse_replay_gap_total` | Cursors too old or missing data |
| JVM heap/direct memory/GC/threads | Server health and buffer pressure |
| Gateway/LB concurrent streams/timeouts | External layer bottlenecks |
| DB/broker consumer lag | Source already lagging before SSE emission |

These metric names are **design suggestions**, not a claim that Spring Boot exports these exact names without instrumentation. `Micrometer`/Actuator can be added to record application gauges/counters; avoid attaching high-cardinality `userId` labels unnecessarily.

### 15.1. Never Retain All Events in Memory

~~~java
// ANTI-PATTERN: no explicit bound on history.
List<Notification> history = new ArrayList<>();
~~~

Storing every event forever for every user causes unbounded heap growth. Use a durable store with TTL/retention and pagination/checkpoints; for in-memory replay, use only `replay().limit(n)` with small `n`, knowing it is lost on restart.

### 15.2. Slow Subscribers

Define policy upfront: can events be dropped? For latest telemetry, intermediate states may be dropped. For audit/payment events, silent drops are unacceptable—store in a durable log and let clients catch up via cursor. Never pick an unbounded `onBackpressureBuffer` just to avoid immediate overflow errors.

### 15.3. Timeouts and Heartbeats

Choose a heartbeat cadence shorter than all idle timeouts without saturating the network at huge client counts. With 100,000 clients and a 15 s heartbeat, there are on average ~6,667 heartbeat writes/second before counting real events; measure server/gateway capacity and never treat comment-only frames as free.

### 15.4. Graceful Shutdown

During rolling-restart deploys, connections may drop/reconnect. Design for:
- Health/readiness blocking new subscriptions when preparing to shut down.
- Adequate time to drain/close streams.
- Browser reconnecting to another instance while its cursor remains valid in the durable store.
- Logs/metrics distinguishing deliberate shutdowns from outages.
- Ensuring source jobs/threads/connections do not keep running after the SSE subscription cancels.

## 16. When to Choose SSE Instead of WebSocket?

Choose **SSE** when:
- Data flows primarily **server → browser**.
- Content consists of text/JSON notifications; clients do not need binary/custom multiplexed protocols.
- You want browser auto-reconnect with SSE semantics.
- You can use GET over existing HTTP infrastructure.
- Clients do not need to send many real-time messages over the same connection.

Choose **WebSocket** when:
- You need **full-duplex**: games, chat with real-time input, collaboration, low-latency interactive controls.
- Sending binary messages with custom framing.
- Bidirectional high-frequency messaging on one persistent channel, and you are ready to manage reconnect/ack/protocol.

Choose **polling** when:
- Traffic is low, data updates infrequently, and simplicity/infra compatibility outweighs real-time delivery.
- Gateways/proxies do not support long-lived SSE connections as required.
- Clients/tech stack restrict EventSource.

Choose a **message broker** like Kafka/Redis Streams when you need fan-out/durable replay/multi-pod scaling; the broker is the **internal source/transport**, and SSE can be the **HTTP interface to the browser**. They are not mutually exclusive choices.

## 17. Common Errors and How to Fix Them

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Client only sees output after stream closes | Proxy/HTTP client buffering | `curl -N`, proxy buffering off, heartbeat/flush |
| `onmessage` does not fire | Server emits named `event: news` | `addEventListener("news", ...)` |
| EventSource reopens repeatedly after receiving everything | Finite Flux completes; browser reconnects | Client calls `close()` on terminal event |
| Duplicate messages after reconnect | Replay may overlap / cursor update timing | Idempotent client, sequence IDs |
| Events lost on pod switch | In-memory sink/timer is not durable | Shared event log + Last-Event-ID |
| Same ID but different payload after restart | ID not stable/global | Stable domain/stream-scoped event IDs |
| Client gets 400 on reconnect | Cursor header format invalid/changed | Versioned cursor parser, resync policy |
| Server does not receive Last-Event-ID as expected | Client never saw a valid ID or isn't using EventSource | Inspect request/reconnect headers |
| SSE stream returns Content-Type application/json | Missing `produces=text/event-stream` | Declare proper mapping or ServerSentEvent wrapper |
| Client displays no data | Named event vs. JSON parsing/display logic | Check frames, event names, textContent |
| Connection closes every minute | Gateway idle timeout | Heartbeat shorter than timeout, configure gateway |
| Browser missing cross-site cookies | SameSite/CORS credentials | Origin allowlist, Secure cookie, withCredentials |
| Bearer header works with fetch but not EventSource | EventSource does not support custom headers | Cookies or streaming fetch client |
| All users receive other users' notifications | Unfiltered shared broadcast sink | Per-tenant/user subscriptions + authorization |
| RAM grows with client count | Unbounded buffer/history/UI list | Bounded queues, retention, cleanup |
| One slow client stalls everyone | Coupled/buffered sink policy | directBestEffort or isolated durable fan-out |
| Data events lost with drop policy | `onBackpressureLatest` discards intermediate updates | Durable log for data requiring accuracy |
| EventSource resends requests after errors | Auto reconnect is standard behavior | Handle backoff/rate/close on terminal event |
| `Flux.interval` resets to ID 0 after reconnect | Per-subscriber timer | Never use timer IDs as durable cursors |
| `collectList` test hangs | Infinite Flux never completes | `take(n)` before `collectList` |
| SSE causes XSS in UI | Using `innerHTML = event.data` | `textContent`/escaping |
| Server errors after streaming some events | HTTP headers already committed | App-level error event + close/reconnect |
| High HTTP latency stats | SSE connection is long-lived | Measure per-event lag and connection metrics separately |

## 18. Review Questions

**1. Does SSE work bidirectionally?**  
No. SSE is a server-to-client response stream over HTTP GET; separate requests are needed for the client to send data.

**2. Which fields does `ServerSentEvent` allow setting?**  
The main fields `id`, `event`, `data`, `retry`, and `comment`. `Flux<ServerSentEvent<T>>` is suitable when you need control over them.

**3. When do you use `onmessage` vs. `addEventListener`?**  
`onmessage` receives default events without a named `event:`; named events like `event: news` require `addEventListener("news", ...)`.

**4. Does Last-Event-ID automatically replay lost events?**  
No. It supplies a cursor; the server must provide a durable replay source and query/authorization logic.

**5. Why does the browser reconnect after a finite Flux completes?**  
EventSource normally retries when a connection closes; the client should call `close()` upon receiving an intentional terminal event.

**6. Does a `: keep-alive` heartbeat dispatch a message?**  
No. Comment frames send bytes periodically to check the connection/idle proxies, without invoking `onmessage`.

**7. Is `Flux.interval` a shared hot topic for all browsers?**  
Not by default; each subscription has its own timer/index. For fan-out, use a shared source/Sinks/broker and design event IDs.

**8. Does `directBestEffort` guarantee every subscriber receives all data?**  
No. Slow subscribers may have events dropped, and the sink does not persist history.

**9. Does SSE guarantee exactly-once delivery?**  
No. Idempotency, checkpoints, and an event storage system are required for stronger delivery semantics.

**10. Why does `collectList()` on `/ticks` easily hang tests?**  
Because `Flux.interval` never completes. Use `take(n)`/timeouts or cancel explicitly.

**11. Why shouldn't bearer tokens be placed in SSE URL query params?**  
URLs easily leak into logs, analytics, referrers, and browser history; use cookies with proper security policies or a purposefully designed auth mechanism.

**12. Does HTTP/2 eliminate all connection limits for SSE?**  
No. There are concurrent stream limits and infra/proxy/server budgets; real load testing is required.

## 19. Production Deployment Checklist

1. Declare `text/event-stream`, UTF-8 responses; return `Flux<ServerSentEvent<T>>` when full fields are needed.
2. Define event names, JSON schema/version, IDs, and retry semantics clearly for clients.
3. Use `EventSource` with proper named event listeners; call `close()` when the stream is no longer needed.
4. Configure comment-only heartbeats if the path may idle; test actual flushing through CDN/proxy.
5. When resume is desired, store a reliable event log + retention and handle `Last-Event-ID`, duplicates/gaps/resync.
6. Authorize connections, replays, and per-tenant/user access; never broadcast sensitive data over a shared sink.
7. Protect cookies/CORS/CSRF for related endpoints; never send tokens in URLs.
8. Explicitly choose hot/cold Publisher; cap connection counts, per-client buffers, subscriber lag, and cancellation.
9. Never enable replay-all or unbounded buffers without retention/memory budgets; own the overflow policy.
10. Set timeouts/ingress/proxy buffering/HTTP/2 settings suited for SSE, and measure reconnect storms.
11. For real DB events, consider an outbox/event log to avoid publish-before-commit and lost notifications after crashes.
12. Test browsers, `curl -N`, WebTestClient, cursor replay, named events, slow clients, proxy buffering, and rolling restarts.
13. Measure active connections, retry/drop/replay rates, per-event delivery lag, JVM memory, broker lag, and Gateway limits.
14. Never promise SSE is always faster than polling or WebSocket; measure against your traffic profile and operational constraints.

## 20. References

- [Spring Framework 6.2 — WebFlux controller return values, Flux ServerSentEvent](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — WebFlux Streaming and heartbeat](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — ServerSentEvent API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/ServerSentEvent.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Project Reactor — Sinks and multicast/replay/backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)
- [Project Reactor — Flux.interval and Reactor operators](https://projectreactor.io/docs/core/release/reference/)
- [MDN — Using server-sent events / EventSource](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [MDN — EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [WHATWG HTML Living Standard — Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
