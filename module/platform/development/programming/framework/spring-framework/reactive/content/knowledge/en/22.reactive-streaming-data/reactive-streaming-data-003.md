# Server-Sent Events with `Flux` and `ServerSentEvent` in Spring WebFlux

## 1. When are Server-Sent Events used?

**Server-Sent Events (SSE)** is a unidirectional event-streaming mechanism from server to client over a single kept-open HTTP response. The browser can receive each event as soon as the server emits it, rather than waiting for the entire response to complete.

SSE is well suited for cases where the client needs continuous updates without requiring a bidirectional channel like WebSocket:

- Order processing status or long-running job status.
- File import/export progress.
- New notifications, activity feeds, or dashboard updates.
- Prices, metrics, or device status pushed from the server to the browser.
- Live logs or progress information.

In Spring WebFlux, the natural return type for a stream is `Flux<T>`. When per-event metadata needs to be controlled, use `ServerSentEvent<T>`:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Notice>> events() {
    return eventService.events()
            .map(notice -> ServerSentEvent.builder(notice).build());
}
```

WebFlux registers the appropriate response writer, serializes each event, and writes it incrementally to the HTTP connection. There is no need to spawn threads manually, call `.subscribe()`, or manage sockets inside the controller.

## 2. How does SSE differ from polling and WebSocket?

| Mechanism | Data direction | Connection | When suitable |
|---|---|---|---|
| Polling | Client asks the server periodically | Each check is usually a new request | Data changes infrequently, simple setup |
| Long polling | Client asks; server holds the request until data or timeout | Request is held, then client sends the next request | Near-realtime updates needed without using a stream |
| SSE | Server pushes events to the client | One long-lived open HTTP response | Server → browser, text-based events |
| WebSocket | Bidirectional | Long-lived socket connection | Both client and server need to send data continuously |

SSE uses HTTP and a text-based response body. The client can still send separate HTTP requests to issue commands, confirm actions, or update data; the SSE stream only handles the server-to-client direction.

WebSocket is more suitable when continuous two-way exchange, binary frames, or complex interactive protocols are needed. SSE is usually simpler when the browser only needs to listen for notifications.

## 3. Wire format structure of an SSE event

SSE uses a UTF-8 text stream with the media type:

```http
Content-Type: text/event-stream
```

An event can contain these fields:

```text
id: 42
event: order-status
retry: 3000
data: {"orderId":42,"status":"SHIPPED"}

```

A blank line terminates the event. Without a blank line, the browser does not consider the event complete.

| Field | Meaning |
|---|---|
| `data` | Event payload; there can be multiple `data:` lines |
| `event` | Event type name; defaults to `message` if omitted |
| `id` | Event ID for the browser to remember and send back on reconnect |
| `retry` | Reconnect wait interval in milliseconds |
| Comment (`:`) | Comment line, commonly used as a heartbeat; not dispatched as an event to JavaScript |

Data-only example:

```text
data:hello

```

Multi-line data example:

```text
data:first line
data:second line

```

The browser joins data lines with newline characters. Lines starting with `:` are comments:

```text
: keep-alive

```

Comments are useful for keeping a connection alive across proxies with idle timeouts without creating a business message.

Do not concatenate event strings manually when you can use `ServerSentEvent`. Spring's writer is responsible for formatting fields, newlines, and encoding data.

## 4. `ServerSentEvent<T>` in Spring

`org.springframework.http.codec.ServerSentEvent<T>` models a single event. Main properties:

- `id`: event identifier.
- `event`: event name.
- `retry`: duration the client waits before attempting to reconnect.
- `comment`: comment/heartbeat.
- `data`: event payload.

Commonly used builder:

```java
ServerSentEvent<Notice> event =
        ServerSentEvent.<Notice>builder()
                .id("42")
                .event("order-status")
                .retry(Duration.ofSeconds(3))
                .data(new Notice(42L, "SHIPPED"))
                .build();
```

You can create a data-only event:

```java
ServerSentEvent<Notice> event =
        ServerSentEvent.builder(new Notice(42L, "SHIPPED")).build();
```

Or a heartbeat without data:

```java
ServerSentEvent<Notice> heartbeat =
        ServerSentEvent.<Notice>builder()
                .comment("keep-alive")
                .build();
```

`ServerSentEvent<T>` is not a complete HTTP response. It describes a single event in the body. HTTP status, response headers, and media type are still determined by the controller/result handler.

### 4.1. `Flux<T>` or `Flux<ServerSentEvent<T>>`?

Use `Flux<T>` when you only need to send default data events without event names, IDs, or retry metadata:

```java
@GetMapping(value = "/messages", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<Notice> messages() {
    return eventService.messages();
}
```

Use `Flux<ServerSentEvent<T>>` when per-event metadata is needed:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Notice>> events() {
    return eventService.messages()
            .map(notice -> ServerSentEvent.builder(notice)
                    .id(notice.id().toString())
                    .event("notice")
                    .build());
}
```

If the client needs to distinguish `progress`, `completed`, and `failed`, the event name allows the client to register separate listeners. If the client needs to resume after reconnecting, provide a stable `id`.

## 5. `Flux` controls the stream lifecycle

`Flux` represents 0..N events over time. When the publisher emits an event, WebFlux writes that event to the response; the stream can continue until complete, error, or cancel.

Example emitting one event per second:

```java
Flux<Notice> notices = Flux.interval(Duration.ofSeconds(1))
        .map(index -> new Notice(index + 1, "update-" + (index + 1)));
```

`Flux.interval` creates a time-based sequence. This is a demo source; in a real application, the source can come from a reactive database, message broker, event store, or a shared publisher.

### 5.1. Cold and hot publishers

A cold publisher typically creates a fresh stream for each subscriber. For example, `Flux.interval` inside a controller method usually starts a separate counter when each client subscribes.

A hot/shared publisher can broadcast the same events to multiple clients. For example, notifications from a broker or a `Sinks.Many` managed in a service. When using a hot source, you must decide:

- Does each client receive every event or only events from the moment it connects?
- Are events stored so clients can reconnect and replay?
- If one client is slow, how is that client's individual queue bounded?
- When a client disconnects, is the subscription cancelled and released?

Do not use an unbounded queue per client. A slow client must not be allowed to cause unbounded memory growth.

### 5.2. Intentionally ending the stream

You can limit the number of events in a demo:

```java
Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(index -> "event-" + index);
```

`take(5)` completes the stream after five elements. With browser SSE, closing the connection can cause `EventSource` to automatically reconnect. Therefore, a finite endpoint may be called again after each completion; if using event IDs, the server needs to determine the next cursor.

Production real-time streams usually live longer and end when the client closes the connection, the server shuts down, or the event source completes.

## 6. Reconnect and `Last-Event-ID`

An important benefit of SSE is that browser `EventSource` automatically reconnects when the connection is interrupted. If the server sends an `id` for events, the browser remembers the last received ID and sends the header:

```http
Last-Event-ID: 42
```

The server can use that value as a cursor to resume the stream from the next event.

In Spring WebFlux, read the header with:

```java
@RequestHeader(name = "Last-Event-ID", required = false)
String lastEventId
```

Example:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Notice>> events(
        @RequestHeader(name = "Last-Event-ID", required = false)
        String lastEventId) {

    long after = parseCursor(lastEventId);

    return eventStore.readAfter(after)
            .map(notice -> ServerSentEvent.builder(notice)
                    .id(Long.toString(notice.id()))
                    .event("notice")
                    .data(notice)
                    .build());
}
```

`eventStore.readAfter(after)` is an illustrative API; in a real application, the event store must be capable of reading back events after the cursor. Do not merely increment a counter and assume data has been replayed.

### 6.1. IDs must be stable and resumable

The ID should be an ordered cursor or durable event identifier:

- Monotonically increasing sequence number.
- Message broker partition offset.
- Event ID in a database.
- Opaque cursor generated by the server that can be decoded/looked up.

Do not use the current timestamp as an ID if multiple events can share a timestamp or precision is insufficient. Do not use random IDs if the server needs to know which event follows another.

### 6.2. Reconnect does not automatically guarantee zero loss or duplicates

`Last-Event-ID` only provides the last cursor recorded by the browser. For reliable resumption:

1. Write the event to the event store/broker before or in the same transaction as the business change.
2. Send a unique, ordered ID that the client can resume from.
3. On reconnect, read events after that ID.
4. Have the client process events idempotently, because certain situations can result in duplicate delivery.
5. Define retention: if the cursor is too old and events have been purged, return an error or ask the client to load a fresh snapshot.

If you only emit real-time events without persisting them, the server cannot reconstruct events missed while the client was offline.

## 7. Heartbeats to keep the connection alive

Some proxies/load balancers close connections if they see no data for a period of time. You can send periodic comment heartbeats:

```java
Flux<ServerSentEvent<Notice>> heartbeats =
        Flux.interval(Duration.ofSeconds(15))
                .map(tick -> ServerSentEvent.<Notice>builder()
                        .comment("keep-alive")
                        .build());
```

Merge with the long-lived event stream:

```java
Flux<ServerSentEvent<Notice>> output =
        Flux.merge(businessEvents, heartbeats);
```

`businessEvents` is a `Flux<ServerSentEvent<Notice>>` from the business source. A heartbeat is a comment, so the browser does not invoke `onmessage` or event listeners for it.

Choose a heartbeat interval shorter than the smallest idle timeout along the path, but not so frequent as to cause unnecessary traffic. For example, 15–30 seconds is often a starting point to test, not a mandatory number.

Do not send heartbeats after the client has disconnected. When downstream cancels, the heartbeat subscription and event source must be cancelled per the reactive lifecycle.

## 8. Browser client with `EventSource`

Native browser API:

```javascript
const source = new EventSource("/api/events");

source.addEventListener("notice", (event) => {
    const notice = JSON.parse(event.data);
    console.log("id:", event.lastEventId, "notice:", notice);
});

source.addEventListener("completed", (event) => {
    console.log("completed:", event.data);
});

source.onerror = (error) => {
    console.log("SSE connection interrupted", error);
};

// When no longer needing to listen:
source.close();
```

If the server does not set `event`, the browser dispatches a default event named `message` and `source.onmessage` can be used.

`EventSource` automatically reconnects when the connection drops. The `retry` field sent by the server adjusts the reconnect delay. When `id` is present, the browser sends `Last-Event-ID` on the next reconnection attempt.

`event.data` is always text. If the server sends JSON, the client needs `JSON.parse(event.data)`.

### 8.1. Limitations of native EventSource

Native `EventSource` primarily opens a GET request. This API does not let you arbitrarily set a POST method, request body, or custom `Authorization` header.

If authentication is needed:

- Prefer secure cookies/sessions fitting the architecture.
- For cross-origin cookies, create `EventSource(url, { withCredentials: true })` and configure CORS credentials accurately.
- Do not put sensitive bearer tokens in the query string just so native EventSource can send them; URLs can appear in logs, history, or telemetry.
- If a custom authorization header or request body is mandatory, consider `fetch` streaming and parsing SSE framing yourself, or design an endpoint issuing controlled short-lived tickets.

Credential mode example:

```javascript
const source = new EventSource(
    "https://api.example.com/api/events",
    { withCredentials: true }
);
```

The server must allow the exact origin and credentials; `Access-Control-Allow-Credentials: true` cannot be combined with a wildcard origin.

## 9. CORS, authentication, and access control

SSE is still an HTTP endpoint, so it requires the same protections as any other API:

- Authenticate the client before starting the stream.
- Verify the user has permission to receive events for the corresponding resource/tenant.
- Do not trust `tenantId` or user ID merely because they appear in query parameters.
- Do not emit user A's events to user B's connection.
- Limit concurrent streams per user/IP.
- Close the stream when the session expires or permissions are revoked.
- Do not include tokens, secrets, or unnecessary personal data in event payloads.

With reactive Spring Security, configure authorization for the SSE route like a normal HTTP endpoint. If the stream depends on order ownership, check permissions before subscribing to the event source and consider re-checking when permissions may change while the connection is open.

CORS must declare explicit origins when using credentials. Because native EventSource does not support custom headers, cookie-based authentication is often easier to integrate in the browser.

## 10. Backpressure, slow clients, and queue bounds

`Flux` participates in Reactive Streams, so demand and cancellation can propagate back from the response writer to the source. However, SSE does not automatically guarantee the entire system stays within memory limits if the producer is faster than the client.

Risk sources:

- A client keeps a connection open for a long time while reading very slowly.
- A message broker emits faster than the socket write rate.
- The application buffers events unboundedly for each subscriber.
- A stream emits large payloads or too many small events.
- Many concurrent clients multiply queues and objects.

Control measures:

- Use `concatMap` or `flatMap` with bounded concurrency for processing before emitting events.
- Bound queues/prefetch and define an overflow policy.
- Use a bounded replay window instead of keeping every event on the heap.
- Set limits on payload size and event frequency.
- If important events must not be lost, store them durably in a broker/event store and let clients resume using a cursor.
- If only the latest state matters, coalesce or merge updates instead of keeping every intermediate value.

Do not use an unbounded `onBackpressureBuffer()` as the default solution. Buffering only postpones the problem when a consumer is slow; eventually it can exhaust memory.

## 11. Cancellation and resource cleanup

When the browser calls `source.close()`, a tab closes, the network drops, or the server times out, downstream can cancel the subscription.

The reactive pipeline needs to tie resource cleanup to its lifecycle:

```java
Flux<ServerSentEvent<Notice>> stream =
        eventSource.events()
                .doOnCancel(() -> log.info("SSE client disconnected"));
```

`doOnCancel` is useful for observing disconnects, but does not replace closing real resources. If the handler creates a consumer, broker subscription, or separate file/channel, it must cancel/close them when the stream completes, errors, or cancels.

You can use `Flux.using` or `Flux.usingWhen` when a resource's lifecycle is tied to the subscription. Avoid calling `.subscribe()` inside a controller to launch an independent flow; doing so means a cancelled request may not stop the background flow and resources will leak.

You should record metrics for open connections, connection lifetime, events sent/sec, disconnects, errors, queue depth, and reconnects. Do not use user ID or session ID as high-cardinality metric tags.

## 12. Errors in an SSE stream

The HTTP status is sent when the response commits, usually when the first event begins being written. After the client has received `200 OK` and part of the stream, the server cannot change the status to `500` on the same response.

If a business error occurs after commit, you can emit an error event according to a published schema:

```java
return events
        .onErrorResume(error ->
                Flux.just(ServerSentEvent.<Notice>builder()
                        .event("error")
                        .data(new Notice(0L, "stream interrupted"))
                        .build())
        );
```

This is an illustrative example; `Notice` must be defined appropriately. Do not send stack traces or raw exception messages to the client.

If an error event cannot be emitted, let the stream terminate with an error and let the browser reconnect per policy. The client must distinguish transient errors from unrecoverable errors; it may need to reload a snapshot or display an interrupted state.

Authentication/authorization errors must be detected before the response starts. Once the stream has committed, it cannot be changed to `401` or `403`.

## 13. Caching, proxy buffering, and timeouts

SSE is a long-lived response, usually unsuitable for ordinary HTTP caching. Several headers and deployment configurations commonly need attention:

```http
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

- `Content-Type` indicates the body is SSE.
- `Cache-Control: no-cache` prevents caches from reusing a stale response without revalidation; if the stream contains private data and caches must not store it, consider `no-store`.
- `X-Accel-Buffering: no` is an Nginx-specific header to disable response buffering when configuration permits.

Do not manually set `Connection: keep-alive` for all environments; it is a connection-specific header and is disallowed in HTTP/2. Check reverse proxy/load balancer configuration to prevent buffering or idle timeouts from closing streams too early.

Compression middleware can also buffer data before sending. Test from a browser through the entire real proxy/CDN path, not just localhost. If events only arrive at the client after a proxy accumulates many KBs, the stream no longer feels real-time even if the publisher emits on time.

## 14. SSE in HTTP/1.1 and HTTP/2

SSE uses a long-lived HTTP response. With HTTP/1.1, browsers typically limit concurrent connections to the same origin; opening many tabs or many streams can hit that limit. HTTP/2 multiplexes multiple streams over a single TCP connection, reducing per-origin connection limit issues.

Even with HTTP/2, each stream still consumes server resources: subscription, state, buffers, socket/stream state, and possibly a dedicated broker consumer. You must limit connection counts, timeouts, and resources per user.

If the application has multiple notification types, consider multiplexing them into one SSE stream with different event names instead of opening one connection per type.

## 15. Complete Java 17+ example with Spring Boot WebFlux

This example creates the `GET /api/events` endpoint:

- Returns `text/event-stream`.
- Emits one `notice` event per second.
- Each event has an ID, event name, retry delay, and JSON data.
- Completes after five events for easy testing with `curl`.
- Reads `Last-Event-ID` to illustrate the reconnect cursor.

### Project structure

```text
webflux-sse-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-sse-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### File `src/main/java/demo/Main.java`

```java
package demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import org.springframework.http.codec.ServerSentEvent;

import reactor.core.publisher.Flux;

@SpringBootApplication
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }
}

@RestController
class EventController {

    @GetMapping(
            value = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<Notice>> events(
            @RequestHeader(
                    name = "Last-Event-ID",
                    required = false
            ) String lastEventId,
            ServerHttpResponse response) {

        long cursor = parseCursor(lastEventId);

        response.getHeaders().set(
                "Cache-Control", "no-cache"
        );
        response.getHeaders().set(
                "X-Accel-Buffering", "no"
        );

        return Flux.interval(Duration.ofSeconds(1))
                .map(tick -> cursor + tick + 1)
                .take(5)
                .map(id -> ServerSentEvent.<Notice>builder()
                        .id(Long.toString(id))
                        .event("notice")
                        .retry(Duration.ofSeconds(3))
                        .data(new Notice(id, "update-" + id))
                        .build());
    }

    private long parseCursor(String value) {
        if (value == null || value.isBlank()) {
            return 0;
        }

        try {
            long cursor = Long.parseLong(value);
            if (cursor < 0) {
                throw new NumberFormatException("negative cursor");
            }
            return cursor;
        } catch (NumberFormatException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Last-Event-ID must be a non-negative integer"
            );
        }
    }

    record Notice(long id, String message) {}
}
```

Run from the project directory using JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

### Testing the stream with curl

```bash
curl -N http://localhost:8080/api/events
```

`-N` disables curl-side buffering so data is displayed as soon as received. The body looks like:

```text
id:1
event:notice
retry:3000
data:{"id":1,"message":"update-1"}

id:2
event:notice
retry:3000
data:{"id":2,"message":"update-2"}

id:3
event:notice
retry:3000
data:{"id":3,"message":"update-3"}

id:4
event:notice
retry:3000
data:{"id":4,"message":"update-4"}

id:5
event:notice
retry:3000
data:{"id":5,"message":"update-5"}

```

### Testing resume with Last-Event-ID

```bash
curl -N \
  -H "Last-Event-ID: 5" \
  http://localhost:8080/api/events
```

The first event on the new connection has ID `6`, followed by `7` through `10`.

**Demo limitation:** the sequence is generated from the cursor, not read from historical events in an event store. It only illustrates receiving `Last-Event-ID` and producing subsequent IDs. Production must read missing events from a database, broker, or durable log so data is not lost while the client is offline.

The `X-Accel-Buffering` header only matters for Nginx when configuration allows it; it can be omitted if the infrastructure does not use Nginx. There is no need to manually set the `Connection` header.

## 16. Testing with `WebTestClient`

You can verify media type, event metadata, and payloads without opening a TCP port:

```java
WebTestClient client = WebTestClient
        .bindToController(new EventController())
        .build();

FluxExchangeResult<ServerSentEvent<EventController.Notice>> result =
        client.get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                        new ParameterizedTypeReference<
                                ServerSentEvent<EventController.Notice>>() {}
                );

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event ->
                "1".equals(event.id())
                        && "notice".equals(event.event())
                        && event.data() != null
                        && event.data().id() == 1
        )
        .expectNextCount(4)
        .verifyComplete();
```

This is an illustrative test snippet; it requires `spring-test` and `reactor-test` (which can be added via `spring-boot-starter-test`) along with imports for `WebTestClient`, `FluxExchangeResult`, `ParameterizedTypeReference`, `StepVerifier`, `Flux`, and `ServerSentEvent`.

Additional things to test:

- Requests without `Last-Event-ID`.
- Reconnects with a valid ID.
- Malformed cursor headers.
- Events with data, event name, and retry.
- Client cancellation mid-stream.
- Event source error mid-stream.
- Multiple concurrent clients and slow-reading clients.
- CORS and authentication from a real browser.
- Proxy buffering and idle timeouts in the deployment environment.

## 17. Common mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Returning `application/json` for SSE | Browser does not process response as an EventSource stream | Use `text/event-stream` |
| Collecting events into a `List` before returning | Client must wait for all data | Return `Flux` to emit event by event |
| Omitting `id` while expecting resume | Server has no reliable cursor | Send a stable ID for each event |
| Using random unordered IDs | Cannot query subsequent events | Use sequence/offset/cursor |
| Reading `Last-Event-ID` without replaying | Events during offline period are still lost | Read from an event store or broker |
| Treating reconnect as exactly-once | Client may receive duplicate events | Design idempotent handling |
| Having no heartbeat | Proxies may close idle connections | Send comment heartbeats based on infrastructure timeouts |
| Sending heartbeats too frequently | Wastes bandwidth and CPU | Choose interval based on idle timeout |
| Using unbounded queues | Slow clients drive RAM up | Bounded queues, overflow policy, or durable broker |
| Calling `.subscribe()` in controller | Stream detaches from request lifecycle | Return `Flux` to WebFlux |
| Not cleaning up on cancel | Consumers, files, or subscriptions remain alive | Bind cleanup to the reactive lifecycle |
| Trying to change status after first event | Response already committed | Validate/authenticate before emitting events |
| Sending stack traces in error events | Exposes internal details | Send safe error codes and messages |
| Using EventSource with custom bearer header | Native API does not support arbitrary headers | Cookie/session or fetch streaming |
| Misconfiguring CORS credentials | Browser cannot open cross-origin stream | Declare explicit origin and credentials |
| Proxy buffers responses | Events arrive at client delayed in batches | Disable buffering appropriately and test through proxy |
| Opening too many streams per origin | Hits connection or resource limits | Combine events into one stream and consider HTTP/2 |
| Using `Connection: keep-alive` on every protocol | Header incompatible with HTTP/2 | Let the server manage connection semantics |

## 18. SSE implementation checklist

1. Determine whether SSE fits a unidirectional server → client flow.
2. Return `Flux<T>` or `Flux<ServerSentEvent<T>>` with `text/event-stream`.
3. Use event names to categorize messages; use stable IDs if resume is needed.
4. Read `Last-Event-ID` and replay from a durable data source.
5. Ensure the client handles duplicate events idempotently.
6. Send heartbeat comments according to proxy/load balancer idle timeouts.
7. Bound event size, event rate, queues, and concurrent connections.
8. Propagate cancellation and clean up consumers/resources.
9. Handle post-commit errors via error events or stream termination.
10. Design authentication, authorization, tenant isolation, and CORS.
11. Disable proxy buffering if necessary and verify real timeouts.
12. Test reconnect, slow clients, disconnects, and server restarts.
13. Monitor open stream count, throughput, latency, queue depth, and error rate.

## 19. Self-check exercises

**Question 1.** In which direction does SSE transmit data?

**Answer:** Server to client over an HTTP response stream. The client sends data back via separate HTTP requests.

**Question 2.** What is the standard media type for SSE?

**Answer:** `text/event-stream`.

**Question 3.** How do `Flux<T>` and `Flux<ServerSentEvent<T>>` differ?

**Answer:** `Flux<T>` sends default data events; `Flux<ServerSentEvent<T>>` allows setting ID, event name, retry, and comments per event.

**Question 4.** What is the meaning of a blank line in the SSE wire format?

**Answer:** Terminates the current event so the browser dispatches the event.

**Question 5.** When is `Last-Event-ID` used?

**Answer:** The browser sends back the last received ID upon reconnecting; the server uses it as a cursor to continue or replay events.

**Question 6.** Do heartbeat comments invoke JavaScript event listeners?

**Answer:** No. Comments are ignored at the event dispatch layer, while keeping the connection alive.

**Question 7.** Why is an event store needed for reliable resumption?

**Answer:** The cursor only tells how far the client received; the server needs a durable source to read back events generated while the client was offline.

**Question 8.** Does native `EventSource` send a custom Authorization header?

**Answer:** No. It provides no API to set arbitrary headers; use cookies/sessions or fetch streaming when custom headers are required.

**Question 9.** Can the server change the status to 500 after sending the first event?

**Answer:** No. The response is already committed; emit an error event per contract or terminate the stream.

**Question 10.** Why should unbounded buffers not be used for slow clients?

**Answer:** The queue will grow with the producer/consumer speed mismatch and can exhaust memory.

## 20. Application rules

- Use SSE when one-way events need to be streamed from server to browser over HTTP.
- Use `Flux` to emit incrementally; use `ServerSentEvent<T>` when `id`, `event`, `retry`, or comments are needed.
- Keep `Content-Type: text/event-stream` and verify proxies do not buffer the stream.
- Use stable IDs with `Last-Event-ID` and an event store when reconnect/replay is required.
- Send heartbeat comments according to idle timeouts.
- Bound queues, payloads, event rates, and stream counts.
- Propagate cancellation and clean up resources when the client disconnects.
- Authenticate/authorize before the stream starts; handle CORS and tenant data safely.
- Post-commit, represent errors inside the stream or terminate the stream; do not try to change HTTP status.
- Test with `WebTestClient` and real browsers across production-like infrastructure.

**Key takeaway:** `Flux` drives the event sequence; `ServerSentEvent<T>` adds SSE-compliant metadata. `id` and `Last-Event-ID` support resumption, heartbeats keep connections alive, and backpressure/cancellation help manage resources. For reliable streams across reconnects, combine cursors with an event store and handle duplicates on the client.

## 21. Official references

- [Spring Framework — Reactive Types and Server-Sent Events in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — `ServerSentEvent` Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/codec/ServerSentEvent.html)
- [Spring Framework — `ServerSentEventHttpMessageWriter` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/codec/ServerSentEventHttpMessageWriter.html)
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [WHATWG — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [MDN — Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [MDN — EventSource API](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
