# Providing NDJSON or SSE with Clear Connection Lifecycle in Spring WebFlux

> **Module:** Spring Framework – reactive  
> **Parent topic:** Integrated Practice  
> **Focus:** designing HTTP streaming with Newline Delimited JSON (NDJSON) or Server-Sent Events (SSE); choosing the right media type and framing; emitting data element by element; managing heartbeats, timeouts, reconnects, cursors, cancellation, backpressure, proxy buffering, and errors after the response has committed. The sample project uses Java 17+, Spring Boot 4.0.9, Spring WebFlux, Reactor, and WebTestClient.

## 1. Learning Objectives

After this lesson, you can:

1. Explain why returning a `Flux<T>` from a controller does not automatically guarantee the client receives data record by record.
2. Distinguish a JSON document/array, NDJSON, and SSE by their HTTP byte format.
3. Choose `application/x-ndjson` or `text/event-stream` based on client needs.
4. Write a WebFlux controller returning `Flux<T>` with a streaming media type and understand per-element codec flushing.
5. Build `ServerSentEvent<T>` with `data`, `event`, `id`, `retry`, and comment heartbeats.
6. Design an event envelope with `data`, `complete`, and `error` so clients recognize business states.
7. Distinguish HTTP errors before commit from errors occurring mid-stream.
8. Understand `Last-Event-ID`, `EventSource` reconnection, and replaying from an event store.
9. Write an NDJSON client using `fetch`, `ReadableStream`, `TextDecoder`, and a parser handling arbitrarily split chunks.
10. Cancel a stream from the client and propagate cancellation back to the Reactor publisher.
11. Bound queues, emission rates, connection lifetimes, connection counts, and per-stream resources.
12. Handle heartbeats, reverse proxy buffering, idle timeouts, and compression.
13. Test NDJSON/SSE with `WebTestClient`, `FluxExchangeResult`, and `StepVerifier`.
14. Decouple the HTTP connection lifecycle from the job lifecycle when a task must persist after client disconnect.

**Core principle:** a streaming connection has three parts that must be designed together: *protocol* (how records/events are framed), *lifecycle* (start, completion, errors, reconnect, and cancel), and *resource policy* (buffers, rate, timeouts, and connection limits). Simply returning a `Flux` solves only composition; server and client must still agree on the other two parts.

## 2. Why Does Streaming Need Framing?

HTTP transmits a byte stream. TCP packets, HTTP/1.1 chunks, or HTTP/2 DATA frames are not record boundaries that an application can rely on.

Suppose the server wants to send three objects:

~~~json
{"id":1,"state":"queued"}
{"id":2,"state":"running"}
{"id":3,"state":"done"}
~~~

If the client receives a buffer containing 1.5 records or multiple records at once, it must know where a record ends. A streaming protocol needs a stable framing rule.

### 2.1. A JSON Document Is Not a JSON Stream

A regular JSON document can be an object:

~~~json
{"id":1,"state":"queued"}
~~~

Or an array:

~~~json
[
  {"id":1,"state":"queued"},
  {"id":2,"state":"running"},
  {"id":3,"state":"done"}
]
~~~

An array is a single complete JSON document. Clients usually must wait for the entire document to parse the array; this encoding is not appropriate if the client needs to process each record as soon as it arrives.

### 2.2. NDJSON: Each Line Is One JSON Value

NDJSON (Newline Delimited JSON) uses newlines as the delimiter:

~~~text
{"id":1,"state":"queued"}\n
{"id":2,"state":"running"}\n
{"id":3,"state":"done"}\n
~~~

Important rules:
- Each line is a valid JSON text.
- Each record is followed by `LF` (`\n`); `CRLF` (`\r\n`) is also accepted by parsers.
- Encoding is UTF-8.
- There are no commas between lines and no outer array.
- JSON strings must escape newlines as `\n`; literal newlines are used to terminate records.
- The standard media type is `application/x-ndjson`.

Each line can be parsed independently. The parser must accumulate bytes/characters until a newline because a single network chunk may contain half a line or multiple lines.

### 2.3. SSE: Each Event Is a Text Block

SSE uses the `text/event-stream` media type. An event consists of fields, terminated by **a blank line**:

~~~text
id: 1
event: progress
retry: 3000
data: {"percent":20,"message":"started"}

id: 2
event: progress
data: {"percent":60,"message":"working"}

id: 3
event: complete
data: {"percent":100,"message":"done"}

~~~

Common fields:
- `data`: event payload.
- `event`: event name so clients can register dedicated listeners.
- `id`: event ID stored as the last event ID.
- `retry`: reconnection delay in milliseconds.
- Lines starting with `:` are comments; commonly used as heartbeats.
- Events are separated by a blank line, not by a TCP/HTTP chunk.

SSE is a unidirectional server-to-client protocol over HTTP. Browsers provide the `EventSource` API with automatic reconnection when the connection closes, sending `Last-Event-ID` on reconnect if prior events had an `id`.

### 2.4. Quick Comparison

| Criterion | NDJSON | SSE |
| --- | --- | --- |
| Media type | `application/x-ndjson` | `text/event-stream` |
| Framing | One JSON value + newline | Field lines + blank line |
| Payload | JSON directly on each line | Event data, usually JSON |
| Event name | Defined by JSON schema | `event` field |
| Event ID | Not in core format | `id` field |
| Reconnect | Designed by client | Supported by `EventSource` |
| Cursor/replay | Query/header defined by API | `Last-Event-ID` built into protocol |
| Heartbeat | JSON control record per schema | Comment `: keep-alive` |
| Browser API | `fetch` + `ReadableStream` | `EventSource` |
| Custom request headers | Yes with `fetch` | Native EventSource has no custom headers API |
| Direction | Unidirectional in one response | Unidirectional server → client |
| Best fit | Data pipelines, CLI, backend consumers, records | Browser notifications, progress, live updates |

Choose NDJSON when consumers want to process JSON records sequentially and control cursors/retries themselves. Choose SSE when browsers need event names, reconnection, and last-event IDs. If client and server need continuous bidirectional exchange, consider WebSocket; if only request-based bidirectional commands are needed, combine POST for commands with SSE for updates.

## 3. Streaming in Spring WebFlux

WebFlux supports reactive return values like `Mono` and `Flux`. However, the media type determines how `HttpMessageWriter` encodes a multi-value publisher.

### 3.1. `application/json` vs. `application/x-ndjson`

Example returning `Flux<OrderEvent>`:

~~~java
@GetMapping(value = "/events", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<OrderEvent> events() {
    return service.events();
}
~~~

With `application/json`, the client receives a single JSON document, typically an array containing the elements. This is not the right choice for newline-delimited streaming.

To stream records:

~~~java
@GetMapping(value = "/events", produces = "application/x-ndjson")
public Flux<OrderEvent> ndjson() {
    return service.events();
}
~~~

With a supported streaming media type, Spring WebFlux encodes, writes, and flushes each element as line-delimited JSON. Each record is pushed to the response as the publisher emits it, instead of collecting everything into an in-memory list.

### 3.2. SSE with `ServerSentEvent<T>`

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<OrderEvent>> sse() {
    return service.events()
        .map(event -> ServerSentEvent.builder(event)
            .id(Long.toString(event.sequence()))
            .event("progress")
            .retry(Duration.ofSeconds(3))
            .build());
}
~~~

`ServerSentEvent<T>` represents event metadata and payload. Spring encodes the payload via the JSON codec, writes event fields in SSE format, and flushes so clients receive events without waiting for the entire stream.

### 3.3. Do Not Use `collectList()` for a Stream Meant to Emit Element by Element

~~~java
// Not streaming: waits for everything before building the response.
public Mono<List<OrderEvent>> buffered() {
    return service.events().collectList();
}

// Streaming: each event is encoded per the appropriate media type.
public Flux<OrderEvent> streaming() {
    return service.events();
}
~~~

`collectList()` makes sense when the contract requires a bounded JSON array. For large or infinite streams, it can hold all data on the heap and delay the response start until upstream completes.

### 3.4. Flush Does Not Mean One Event = One Packet

When Spring flushes an element, the client can receive data sooner. Yet TCP, TLS, HTTP/2, reverse proxies, compression, and client runtimes can still coalesce or split bytes into different chunks.

**Never write a parser that relies on chunk boundaries.** Parse strictly by NDJSON newlines or SSE blank-line/event framing.

## 4. Designing Protocol Envelopes and Lifecycle

A production stream must make clear when data starts, when it succeeds, when it fails, and when the client should reconnect.

### 4.1. Unified Envelope

A simple schema:

~~~json
{"type":"data","id":"1","sequence":1,"message":"job started"}
{"type":"data","id":"2","sequence":2,"message":"processing"}
{"type":"complete","message":"stream completed"}
~~~

If the task fails:

~~~json
{"type":"data","id":"1","sequence":1,"message":"job started"}
{"type":"stream-error","errorCode":"UPSTREAM_FAILED","message":"Stream could not continue"}
~~~

Conventions:
- `data`: a business record.
- `complete`: normal stream completion.
- `stream-error`: business error represented inside the stream.
- `id`/`sequence`: stable cursor for resuming.
- Never put stack traces, SQL, credentials, or raw exception messages into error payloads.

Using these exact field names is not mandatory; what matters is a versioned contract where clients know terminal semantics.

### 4.2. Lifecycle Diagram

~~~text
Client request
    |
    v
Validate auth, job, cursor, media type
    |
    +---- invalid before commit ----> HTTP 4xx/5xx Problem response
    |
    v
Commit HTTP status + streaming headers
    |
    v
Subscribe to reactive source
    |
    +---- data frame/event ---------> client processes incrementally
    |
    +---- heartbeat ---------------> connection remains active
    |
    +---- complete ----------------> normal end; client closes
    |
    +---- stream-error ------------> in-band error; client decides retry
    |
    +---- client disconnect -------> cancel upstream subscription
~~~

Validating before commit is critical. Once the response has sent status/headers and some bytes, the server cannot switch status 200 to 500 or replace the already-sent body with a full ProblemDetail.

### 4.3. Errors Before vs. After Response Commit

| Timing | Example | Representation |
| --- | --- | --- |
| Before commit | Missing job ID, unauthorized | HTTP 404/403, ProblemDetail |
| Before commit | Malformed cursor | HTTP 400 |
| After commit | Database stream fails after 4 records | In-band error event/record or close connection |
| After commit | Client disconnect | Cancellation, cleanup |
| After commit | Proxy idle timeout | Client detects disconnect and applies reconnect policy |

If a post-commit error is converted into a `stream-error` record/event inside the publisher, the HTTP status stays 200; the client must inspect `type` or `event` to know the stream failed. Without an in-band error protocol, the connection terminates abnormally and the client must treat the stream as incomplete.

### 4.4. Do Not Equate HTTP Completion with Business Completion

`onComplete` means the Publisher terminated normally. By itself, it does not prove a background job committed its result, a payment succeeded, or data was durably saved.

If the business requires result confirmation, emit a `complete` frame only after the job state has been persisted or verified. For durable tasks, persist events/cursors so clients can reconnect and fetch missing parts.

## 5. NDJSON: Server Framing and Client Parsing

### 5.1. Byte Stream Example

An NDJSON response:

~~~text
Content-Type: application/x-ndjson; charset=utf-8

{"type":"data","sequence":1,"message":"started"}\n
{"type":"data","sequence":2,"message":"working"}\n
{"type":"complete","message":"done"}\n
~~~

Each line can be parsed independently. There are no commas between lines and no outer array. If a string contains a newline, the JSON encoder must escape it as the two characters `\` and `n`, never inserting a literal newline into the record.

### 5.2. `fetch` Clients Must Retain Incomplete Tails

`ReadableStream` may return:
- Half of a JSON record.
- Multiple JSON records in one chunk.
- A record split across two chunks.
- A final chunk without a trailing newline.

Therefore the client maintains a `buffer`, splits complete lines, and parses any remainder only on EOF:

~~~javascript
async function readNdjson(url, signal, onRecord) {
  const response = await fetch(url, { signal });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/x-ndjson")) {
    throw new Error(`Unexpected Content-Type: ${contentType}`);
  }

  if (!response.body) {
    throw new Error("Streaming response body is unavailable");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();

      buffer += decoder.decode(value, { stream: !done });

      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (line.length === 0) {
          continue; // This client's policy: skip blank lines.
        }
        onRecord(JSON.parse(line));
      }

      if (done) {
        break;
      }
    }

    // Process the final record if the server closes without a trailing newline.
    if (buffer.length > 0) {
      onRecord(JSON.parse(buffer));
    }
  } finally {
    reader.releaseLock();
  }
}
~~~

`TextDecoder` uses `{stream:true}` to preserve a UTF-8 code point split across multiple bytes/chunks. Never convert each individual chunk to a string and parse immediately: chunks are not record boundaries.

In the example, blank lines are skipped. An NDJSON reader may ignore blank lines if that policy is documented; if the system requires strict parsing, raise an error on blank lines.

### 5.3. Cancelling an NDJSON Request

~~~javascript
const controller = new AbortController();

readNdjson(
  "/api/streams/job-42/ndjson?after=0",
  controller.signal,
  frame => {
    console.log(frame.type, frame.sequence, frame.message);
  }
).catch(error => {
  if (error.name !== "AbortError") {
    console.error("Stream failed", error);
  }
});

// When the user closes the screen or clicks Stop:
controller.abort();
~~~

`AbortController.abort()` cancels fetch; the browser closes the response stream. On the server, cancellation can propagate to the publisher if the connector and source support it. An in-flight blocking call may not stop immediately; do not treat cancellation as a transaction rollback mechanism.

### 5.4. Resuming NDJSON

NDJSON does not define `Last-Event-ID`. The API must choose its own cursor, for example:
- Query `?after=123`.
- Header `X-Stream-Cursor: 123`.
- POST body containing the cursor when complex filters are needed.

Cursors must be stable and authorization-checked. When using monotonically increasing sequence IDs, the server reads records after the cursor from an event store without relying on in-memory state from the old connection.

## 6. SSE: Event Format, Heartbeat, and Reconnect

### 6.1. Event Structure

An SSE event can contain these lines:

~~~text
id: 42
event: progress
retry: 3000
data: {"sequence":42,"percent":70}

~~~

The blank line at the end of the block triggers dispatch. If `data` spans multiple lines, the browser joins them with newlines. Event streams always use UTF-8.

### 6.2. Named Events

~~~javascript
const source = new EventSource("/api/streams/job-42/sse");

source.addEventListener("progress", event => {
  const frame = JSON.parse(event.data);
  renderProgress(frame);
});

source.addEventListener("complete", () => {
  source.close();
});

source.addEventListener("stream-error", event => {
  const frame = JSON.parse(event.data);
  showStreamError(frame.errorCode);
  source.close();
});

source.onerror = error => {
  // This is an EventSource connection/state error,
  // distinct from the business event named "stream-error".
  console.warn("SSE transport error", error);
};
~~~

`EventSource` automatically reconnects when the connection closes according to browser mechanics. When the application receives `complete` or `stream-error` and does not want to reconnect, call `source.close()`.

### 6.3. `id` and `Last-Event-ID`

If the server sends:

~~~text
id: 42
event: progress
data: {"sequence":42,"percent":70}

~~~

The browser stores the last event ID. When reconnecting, it can send:

~~~http
Last-Event-ID: 42
~~~

The server reads this header and replays events after ID 42. This is only useful when:
- Event IDs have clear ordering or cursor semantics.
- Event history is still stored.
- The server can replay events from the cursor.
- The client is authorized to read that stream/job.
- Replaying does not trigger duplicate side effects.

**Do not simply accept the header and ignore it.** If the server always starts from event 1, the client may receive duplicates or miss data. `Last-Event-ID` can be used as a sequence cursor or a signed opaque cursor.

### 6.4. `retry` Is Not Business Retry

The SSE field `retry: 3000` instructs the browser to wait the specified reconnect interval when the connection closes. It does not:
- Retry an event whose JavaScript handler threw an error.
- Guarantee events are never lost or duplicated.
- Replace idempotency.
- Replace server-side event replay.

If reconnecting after event 42, the server must replay starting from event 43. Clients should still deduplicate by event ID because network failures can happen right around event dispatch.

### 6.5. Heartbeat via Comment

An SSE heartbeat:

~~~text
: keep-alive

~~~

Comments do not trigger message events for application listeners, yet they keep connections alive across proxies/load balancers with idle timeouts. The heartbeat interval should be shorter than the lowest idle timeout along the path, with safety margin.

Do not send comments too frequently. Heartbeats generate network traffic, encode/write work, and can inflate logs/metrics. Pick the interval based on infrastructure, typically tens of seconds, and measure in practice through the proxy.

### 6.6. Native EventSource Has Request Limitations

Browser `EventSource` issues a GET request and has no custom API to attach a bearer `Authorization` header or send a POST body. Cookies/sessions can be used with `withCredentials` if CORS/security policies permit:

~~~javascript
const source = new EventSource(
  "https://api.example.test/events",
  { withCredentials: true }
);
~~~

If you need a bearer token in a custom header, a POST body, or fine-grained parser/cursor control, use `fetch` + `ReadableStream` and parse SSE manually. Never place access tokens in query strings because URLs are routinely written to proxy/access logs.

## 7. Heartbeat, Flush, and Reverse Proxies

### 7.1. Why Are Heartbeats Needed?

A stream may emit no business events for several minutes. Proxies/load balancers can treat a connection with no bytes transferred as idle and close it. The server might not detect that the client disconnected until the next write.

Spring Framework recommends emitting data periodically for streaming responses such as `text/event-stream` or `application/x-ndjson` to detect disconnects earlier. A heartbeat can be a comment-only SSE event or a protocol-appropriate no-op record.

### 7.2. NDJSON Heartbeat Is a Control Record

NDJSON has no comment syntax. If a heartbeat is needed, use a valid envelope:

~~~json
{"type":"heartbeat","sentAt":"2026-11-08T08:30:00Z"}
~~~

Clients must recognize `type=heartbeat` and not display it as business data. Do not send a blank line instead of a heartbeat; a blank line is not a JSON record.

### 7.3. Response Headers

A streaming response typically needs appropriate headers:

~~~http
Content-Type: text/event-stream
Cache-Control: no-cache, no-transform
X-Accel-Buffering: no
~~~

- `Content-Type` identifies the protocol.
- `Cache-Control` prevents caching the streaming response and restricts intermediary transformations.
- `X-Accel-Buffering: no` is a vendor-specific header commonly understood by Nginx to disable proxy buffering; it is not an HTTP standard and other proxies may ignore it.

For NDJSON, replace `Content-Type` with `application/x-ndjson`.

### 7.4. Illustrative Nginx Configuration

~~~nginx
location /api/streams/ {
    proxy_pass http://webflux_app;
    proxy_http_version 1.1;

    proxy_buffering off;
    proxy_cache off;

    proxy_read_timeout 75s;
    proxy_send_timeout 75s;
}
~~~

This configuration is only an Nginx example; match it to your upstream, TLS, ingress, and deployed version. `proxy_read_timeout` must exceed the expected heartbeat interval. Also check load balancers, API gateways, service meshes, CDNs, and client timeouts; disabling buffering in one proxy does not disable buffering at every hop.

### 7.5. Compression and Latency

Compression may buffer data before sending or wait for enough data to compress efficiently. For low-latency streams, verify how servers/proxies handle gzip/brotli and consider disabling compression on streaming routes. Do not assume calling `flush()` in Spring causes every proxy to immediately send bytes out onto the Internet.

## 8. Backpressure, Buffers, and Concurrency

### 8.1. Backpressure Only Works When the Entire Pipeline Honors Demand

Reactive Streams allows downstream to request an element count. WebFlux and Reactor propagate demand from the HTTP writer back to the publisher, but callbacks/queues outside Reactor may be unaware of or ignore demand.

If the producer outpaces the consumer, define a policy:
- Slow down the producer if flow control exists.
- Bound the queue.
- Drop non-critical data if the contract allows.
- Coalesce the latest state update instead of keeping every update.
- Fail the stream when the buffer fills if data cannot be retained.
- Use a durable queue/event log when records must not be lost.

### 8.2. Never Use Unbounded Buffers Per Connection

Dangerous example:

~~~java
source.onBackpressureBuffer();
~~~

Overload can grow the queue without bound. Across many concurrent connections, memory usage can become:

\[
\text{memory} \approx
\text{active connections}
\times \text{queued events per connection}
\times \text{average event bytes}
\]

Use a bounded buffer with an appropriate overflow policy:

~~~java
source.onBackpressureBuffer(
    256,
    dropped -> metrics.recordDroppedEvent(),
    BufferOverflowStrategy.ERROR
);
~~~

This is an example policy that fails the stream when the queue fills; metrics and error mapping must be implemented. If events can be dropped, notify the client or provide cursor/replay so correctness is preserved.

### 8.3. Bounding Connection Count and Lifetime

Each stream can hold:
- An HTTP connection/socket.
- Subscription and operator state.
- Event cursor, context, and tracing state.
- Buffers and pending writes.
- Scheduled heartbeat tasks.
- Downstream resources such as DB cursors/message subscriptions.

Set limits on streams per user/tenant/service, maximum lifetime, idle timeout, request timeout, and rate limits. For long-lived streams, consider periodic reconnects to balance load or roll deployments.

### 8.4. Do Not Use `collectList()` to "Keep the Stream Stable"

`collectList()` buffers every element until completion. For an infinite stream, it never emits the list. For a large finite stream, heap grows linearly with total records.

Encode event by event, paginate, or store data in a dedicated event store if replay is required.

## 9. Cancellation and Resource Lifecycle

### 9.1. Client Disconnect Propagates Cancellation

When a browser closes a tab, calls `EventSource.close()`, aborts fetch, or loses network connectivity, the HTTP response subscriber can cancel the publisher. Reactor propagates cancellation upstream so the source stops emitting if supported.

~~~java
return service.stream(jobId)
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            log.info("stream_cancelled jobId={}", safeJobId);
        }
    });
~~~

`doFinally` observes `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`. Never log raw queries/headers/secrets alongside the job ID.

### 9.2. Cleanup with Asynchronous Resources

If a stream opens resources such as a DB cursor, listener, or message broker subscription, cleanup must follow complete/error/cancel. For asynchronous resources, use `usingWhen` or the driver's lifecycle abstraction:

~~~java
Flux<Record> records = Flux.usingWhen(
    repository.openCursor(jobId),
    cursor -> cursor.readAll(),
    cursor -> cursor.close(),
    (cursor, error) -> cursor.close(),
    cursor -> cursor.close()
);
~~~

This is a conceptual fragment: cursor types and `close()` must return reactive types matching the chosen overload. In real code, handle cleanup errors separately and ensure the driver implements proper close/cancel semantics.

Do not call `.subscribe()` manually on a cleanup task and return the response; compose cleanup into the Publisher's lifecycle.

### 9.3. HTTP Connections Differ from Job Lifecycles

There are two models:

**Ephemeral stream tied to the connection**
- Client disconnect cancels the source/job.
- Fits ad-hoc queries or streams with no value after the client leaves.
- Must clean up immediately on cancel.

**Durable job decoupled from the connection**
- The job continues running even if the client disconnects.
- Events are durably stored with sequence/cursor.
- Clients reconnect and read events after the cursor.
- Fits report generation, imports/exports, or long-running workflows.

Do not let a single HTTP subscription be the only thing keeping a job alive across restarts/deployments. When durable execution is needed, use a job store/event store and manage job lifecycle independently.

## 10. Errors and Terminal Events After Response Commit

### 10.1. Status Cannot Change Once Bytes Are Sent

A stream might send status 200 and 3 records before encountering an error. The server cannot go back and change the response to 500.

Therefore choose one of two policies:

1. **In-band error:** emit a `stream-error` record/event with a stable code, then terminate the stream.
2. **Abrupt termination:** close the connection; the client detects the missing `complete` marker and treats the stream as incomplete.

For clients that need to distinguish completion from failure, in-band errors are usually clearer.

### 10.2. NDJSON Terminal Envelope

~~~json
{"type":"data","sequence":1,"message":"started"}
{"type":"data","sequence":2,"message":"working"}
{"type":"stream-error","errorCode":"UPSTREAM_FAILED"}
~~~

On success:

~~~json
{"type":"data","sequence":1,"message":"started"}
{"type":"data","sequence":2,"message":"done"}
{"type":"complete"}
~~~

The client considers the stream successful only when receiving `complete`. EOF without `complete` may indicate a disconnect or a mid-stream failure.

### 10.3. SSE Terminal Event

~~~text
id: 2
event: progress
data: {"sequence":2,"message":"working"}

event: stream-error
data: {"errorCode":"UPSTREAM_FAILED"}

~~~

Or success event:

~~~text
id: 2
event: progress
data: {"sequence":2,"message":"done"}

event: complete
data: {"status":"ok"}

~~~

Do not use the event name `error` for business errors if clients also need to handle transport `EventSource.onerror`; a name like `stream-error` is easier to distinguish.

### 10.4. Safe Error Payloads

Send only:
- A stable error code.
- An approved public message.
- Job/event ID if non-sensitive.
- A retryable flag if defined by the API contract.
- Trace/correlation ID if safe for clients to use for support.

Never send raw exception messages, SQL, stack traces, internal URLs, tokens, or credentials.

## 11. Reconnect, Replay, and Duplicate Handling

### 11.1. SSE Reconnect Does Not Guarantee Exactly-Once

`EventSource` sends `Last-Event-ID`, yet preventing lost or duplicate events depends on whether the server stores and replays events properly. The network can drop after the server sends bytes but before the client finishes processing. An event may be redelivered.

Clients should:
- Persist the last processed event ID after successful handling.
- Ignore already-processed event IDs.
- Process events in order if the protocol requires.
- Ensure idempotency for side effects.
- Verify the cursor belongs to the right job/user/tenant.

### 11.2. Event Store and Cursors

A minimal event store needs:
- `job_id`.
- Monotonically increasing `sequence` scoped to the job.
- `event_type`.
- Payload/version.
- `created_at`.
- Retention or checkpoint policy.

When reconnecting with `Last-Event-ID=42`, the server reads events with sequence `>42`. If the cursor is too old and history has expired past retention, return an explicit error before commit or instruct the client to fetch a fresh snapshot.

### 11.3. Opaque Cursors

Integer sequences are not always sufficient. You can use a signed or opaque cursor token containing:
- Job ID.
- Offset/sequence.
- Version.
- Expiry.
- Integrity signature.

Do not allow clients to tamper with cursors to read another job/tenant's data. Check authorization on every reconnect.

## 12. Runnable Project: Spring Boot 4.0.9 + Java 17+

The demo creates two endpoints sharing one stream envelope:
- `GET /api/streams/{jobId}/ndjson?after=0`
- `GET /api/streams/{jobId}/sse`

The service emits 5 data frames, then `complete`. With `jobId=fail`, the service emits a couple of data frames and then a `stream-error` frame. The SSE route adds comment heartbeats and accepts `Last-Event-ID` to simulate replay. Client disconnect cancels the subscription.

### 12.1. Project Structure

~~~text
webflux-stream-lifecycle/
├── pom.xml
├── src/main/java/com/example/stream/
│   ├── StreamApplication.java
│   ├── StreamFrame.java
│   ├── StreamService.java
│   └── StreamController.java
└── src/test/java/com/example/stream/
    └── StreamControllerTest.java
~~~

### 12.2. `pom.xml`

Spring Boot 4.0.9 and Java 17+. The parent manages versions of Spring Framework, Reactor, and test dependencies.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-stream-lifecycle</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
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

### 12.3. `StreamApplication.java`

~~~java
package com.example.stream;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamApplication.class, args);
    }
}
~~~

### 12.4. `StreamFrame.java`

~~~java
package com.example.stream;

public record StreamFrame(
    String type,
    String id,
    Long sequence,
    String message,
    String errorCode
) {
    public static StreamFrame data(long sequence, String jobId) {
        return new StreamFrame(
            "data",
            Long.toString(sequence),
            sequence,
            "job " + jobId + " update " + sequence,
            null
        );
    }

    public static StreamFrame complete() {
        return new StreamFrame(
            "complete", null, null, "stream completed", null);
    }

    public static StreamFrame error(String code) {
        return new StreamFrame(
            "stream-error", null, null, null, code);
    }
}
~~~

`type` defines the protocol event; `id` is the data event cursor; `sequence` is convenient for consumers; `errorCode` is the public code. In production, version the schema and bound message size.

### 12.5. `StreamService.java`

~~~java
package com.example.stream;

import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@Service
public class StreamService {

    private static final Logger log =
        LoggerFactory.getLogger(StreamService.class);

    private static final long EVENT_COUNT = 5;

    public Flux<StreamFrame> frames(
            String jobId,
            long afterSequence) {

        if (afterSequence < 0 || afterSequence > EVENT_COUNT) {
            return Flux.error(
                new IllegalArgumentException("invalid stream cursor"));
        }

        long remaining = EVENT_COUNT - afterSequence;

        Flux<Long> sequence = Flux.interval(Duration.ofMillis(250))
            .take(remaining)
            .map(index -> afterSequence + index + 1);

        if ("fail".equals(jobId)) {
            sequence = sequence
                .take(2)
                .concatWith(Mono.<Long>error(
                    new IllegalStateException("simulated upstream failure")));
        }

        return sequence
            .map(value -> StreamFrame.data(value, jobId))
            .concatWith(Mono.just(StreamFrame.complete()))
            .onErrorResume(error ->
                Flux.just(StreamFrame.error("UPSTREAM_FAILED")))
            .doFinally(signal ->
                logLifecycle(jobId, signal));
    }

    private void logLifecycle(String jobId, SignalType signal) {
        // Do not log client payloads or authentication data.
        log.info(
            "stream_finished jobId={} signal={}",
            safeJobId(jobId),
            signal.name());
    }

    private String safeJobId(String jobId) {
        if (jobId == null) {
            return "unknown";
        }
        return jobId.replaceAll("[^A-Za-z0-9_-]", "_")
            .substring(0, Math.min(40, jobId.length()));
    }
}
~~~

Explanation:
- `Flux.interval` simulates a periodic source; `take` limits the element count.
- `afterSequence` simulates a cursor to continue emitting after already-processed events.
- Job `fail` emits a few records and then errors.
- `onErrorResume` converts errors into a safe `stream-error` frame; errors are not lost but represented in the protocol.
- `concatWith(Mono.just(StreamFrame.complete()))` emits `complete` only when the source completes normally. If the source errors, `concatWith` does not emit complete; the fallback branch emits only `stream-error`.
- `doFinally` logs `CANCEL`, `ON_ERROR`, or `ON_COMPLETE` according to subscription lifecycle.

This is an in-memory demo source, not a durable event store. On reconnect, it reconstructs records by sequence; production must replay from persisted data.

### 12.6. `StreamController.java`

~~~java
package com.example.stream;

import java.time.Duration;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/streams")
public class StreamController {

    private static final MediaType NDJSON =
        MediaType.parseMediaType("application/x-ndjson");

    private static final Duration HEARTBEAT_INTERVAL =
        Duration.ofMillis(500);

    private final StreamService service;

    public StreamController(StreamService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{jobId}/ndjson",
        produces = "application/x-ndjson")
    public ResponseEntity<Flux<StreamFrame>> ndjson(
            @PathVariable String jobId,
            @RequestParam(defaultValue = "0") long after) {

        validateCursor(after);

        Flux<StreamFrame> body = service.frames(jobId, after);

        return ResponseEntity.ok()
            .contentType(NDJSON)
            .header(
                HttpHeaders.CACHE_CONTROL,
                "no-cache, no-transform")
            .header("X-Accel-Buffering", "no")
            .body(body);
    }

    @GetMapping(
        value = "/{jobId}/sse",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<Flux<ServerSentEvent<StreamFrame>>> sse(
            @PathVariable String jobId,
            @RequestHeader(
                name = "Last-Event-ID",
                required = false) String lastEventId) {

        long after = parseLastEventId(lastEventId);
        validateCursor(after);

        Flux<ServerSentEvent<StreamFrame>> data =
            service.frames(jobId, after)
                .map(this::toServerSentEvent);

        Flux<ServerSentEvent<StreamFrame>> body =
            data.publish(shared -> Flux.merge(
                shared,
                Flux.interval(HEARTBEAT_INTERVAL)
                    .map(tick ->
                        ServerSentEvent.<StreamFrame>builder()
                            .comment("keep-alive")
                            .build())
                    .takeUntilOther(shared.then())
            ));

        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .cacheControl(CacheControl.noCache())
            .header("X-Accel-Buffering", "no")
            .body(body);
    }

    private ServerSentEvent<StreamFrame> toServerSentEvent(
            StreamFrame frame) {

        ServerSentEvent.Builder<StreamFrame> builder =
            ServerSentEvent.builder(frame)
                .event(frame.type())
                .retry(Duration.ofSeconds(3));

        if (frame.id() != null) {
            builder.id(frame.id());
        }

        return builder.build();
    }

    private long parseLastEventId(String value) {
        if (value == null || value.isBlank()) {
            return 0;
        }

        try {
            return Long.parseLong(value);
        }
        catch (NumberFormatException exception) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Invalid Last-Event-ID");
        }
    }

    private void validateCursor(long cursor) {
        if (cursor < 0 || cursor > 5) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Stream cursor is out of range");
        }
    }
}
~~~

Points to note:
1. NDJSON uses `application/x-ndjson`, SSE uses `text/event-stream`.
2. Response headers are configured before the publisher starts emitting.
3. SSE `id` is attached only to data frames that have a cursor; `complete` and `stream-error` do not change the last event ID.
4. Heartbeats are comment-only SSE events; they do not trigger business messages.
5. `publish` shares one upstream subscription between the data branch and the heartbeat completion-tracking branch.
6. When the source completes, `takeUntilOther(shared.then())` stops the heartbeat.
7. When the client cancels, cancellation propagates upstream through the publisher; `StreamService.doFinally` observes the lifecycle.
8. The demo cursor is only a number from 0 to 5; production must verify the cursor belongs to the right job and user.

### 12.7. `StreamControllerTest.java`

~~~java
package com.example.stream;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamControllerTest {

    @Value("${local.server.port}")
    int port;

    private WebTestClient http() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void ndjsonStreamsFiveRecordsAndCompleteFrame() {
        FluxExchangeResult<StreamFrame> result =
            http().get()
                .uri("/api/streams/demo/ndjson?after=0")
                .accept(MediaType.parseMediaType(
                    "application/x-ndjson"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.parseMediaType(
                            "application/x-ndjson"))
                .returnResult(StreamFrame.class);

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(frame ->
                frame.type().equals("data")
                    && frame.sequence() == 1)
            .expectNextCount(4)
            .expectNextMatches(frame ->
                frame.type().equals("complete"))
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void ndjsonCanResumeAfterCursor() {
        FluxExchangeResult<StreamFrame> result =
            http().get()
                .uri("/api/streams/demo/ndjson?after=3")
                .exchange()
                .expectStatus().isOk()
                .returnResult(StreamFrame.class);

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(frame ->
                frame.type().equals("data")
                    && frame.sequence() == 4)
            .expectNextMatches(frame ->
                frame.type().equals("data")
                    && frame.sequence() == 5)
            .expectNextMatches(frame ->
                frame.type().equals("complete"))
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void sseStreamsNamedEventsAndHeartbeatComments() {
        FluxExchangeResult<ServerSentEvent<StreamFrame>> result =
            http().get()
                .uri("/api/streams/demo/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<StreamFrame>>() {});

        Flux<ServerSentEvent<StreamFrame>> dataEvents =
            result.getResponseBody()
                .filter(event -> event.data() != null);

        StepVerifier.create(dataEvents)
            .expectNextMatches(event ->
                event.event().equals("data")
                    && event.id().equals("1")
                    && event.data().sequence() == 1)
            .expectNextCount(4)
            .expectNextMatches(event ->
                event.event().equals("complete"))
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void sseResumesFromLastEventId() {
        FluxExchangeResult<ServerSentEvent<StreamFrame>> result =
            http().get()
                .uri("/api/streams/demo/sse")
                .header("Last-Event-ID", "2")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<StreamFrame>>() {});

        StepVerifier.create(
                result.getResponseBody()
                    .filter(event -> event.data() != null))
            .expectNextMatches(event ->
                event.id().equals("3")
                    && event.data().sequence() == 3)
            .expectNextMatches(event ->
                event.id().equals("4"))
            .expectNextMatches(event ->
                event.id().equals("5"))
            .expectNextMatches(event ->
                event.event().equals("complete"))
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void upstreamFailureBecomesAnInBandErrorFrame() {
        FluxExchangeResult<StreamFrame> result =
            http().get()
                .uri("/api/streams/fail/ndjson")
                .exchange()
                .expectStatus().isOk()
                .returnResult(StreamFrame.class);

        StepVerifier.create(result.getResponseBody())
            .expectNextCount(2)
            .expectNextMatches(frame ->
                frame.type().equals("stream-error")
                    && frame.errorCode().equals("UPSTREAM_FAILED"))
            .verifyComplete();
    }

    @Test
    void cancellationReachesTheReactiveSource() {
        StreamService service = new StreamService();
        java.util.concurrent.atomic.AtomicReference<SignalType> signal =
            new java.util.concurrent.atomic.AtomicReference<>();

        Flux<StreamFrame> source = service.frames("demo", 0)
            .doFinally(signal::set);

        StepVerifier.create(source)
            .expectNextMatches(frame -> frame.type().equals("data"))
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertEquals(SignalType.CANCEL, signal.get());
    }

    @Test
    void invalidCursorIsRejectedBeforeStreaming() {
        http().get()
            .uri("/api/streams/demo/ndjson?after=99")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void invalidLastEventIdIsRejected() {
        http().get()
            .uri("/api/streams/demo/sse")
            .header("Last-Event-ID", "not-a-number")
            .exchange()
            .expectStatus().isBadRequest();
    }
}
~~~

This test uses a real HTTP server on a random port, checks status/headers, and then uses `StepVerifier` to consume `FluxExchangeResult`. Spring Framework recommends this approach for streaming responses that may be long-running or infinite.

The final cancellation test verifies the signal on the service Publisher. In production integration tests, add a test that closes the HTTP client early and observes cleanup at the server/driver.

### 12.8. Running the Project

Requires JDK 17+, Maven, and network access to download dependencies on the first run.

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

### 12.9. Trying NDJSON with curl

~~~bash
curl -N -i \
  -H "Accept: application/x-ndjson" \
  "http://localhost:8080/api/streams/demo/ndjson?after=0"
~~~

Illustrative output:

~~~text
{"type":"data","id":"1","sequence":1,"message":"job demo update 1","errorCode":null}
{"type":"data","id":"2","sequence":2,"message":"job demo update 2","errorCode":null}
{"type":"data","id":"3","sequence":3,"message":"job demo update 3","errorCode":null}
{"type":"data","id":"4","sequence":4,"message":"job demo update 4","errorCode":null}
{"type":"data","id":"5","sequence":5,"message":"job demo update 5","errorCode":null}
{"type":"complete","id":null,"sequence":null,"message":"stream completed","errorCode":null}
~~~

`curl -N` disables output buffering on the curl side so each element is easier to observe. Arrival timing depends on the connector and proxies; do not take terminal display lines as sole proof of production latency.

### 12.10. Trying SSE with curl

~~~bash
curl -N -i \
  -H "Accept: text/event-stream" \
  "http://localhost:8080/api/streams/demo/sse"
~~~

The response will contain event fields similar to:

~~~text
id: 1
event: data
retry: 3000
data: {"type":"data","id":"1","sequence":1,"message":"job demo update 1","errorCode":null}

:keep-alive

id: 2
event: data
retry: 3000
data: {"type":"data","id":"2","sequence":2,"message":"job demo update 2","errorCode":null}

event: complete
retry: 3000
data: {"type":"complete","id":null,"sequence":null,"message":"stream completed","errorCode":null}

~~~

The order of heartbeats relative to data depends on timers; the output only illustrates format. SSE comments do not generate `data` events for clients.

### 12.11. Simulating Reconnect

Take event ID 2 and send the header:

~~~bash
curl -N \
  -H "Accept: text/event-stream" \
  -H "Last-Event-ID: 2" \
  "http://localhost:8080/api/streams/demo/sse"
~~~

The demo server starts from sequence 3. With NDJSON, the cursor is sent via query parameter:

~~~bash
curl -N \
  -H "Accept: application/x-ndjson" \
  "http://localhost:8080/api/streams/demo/ndjson?after=2"
~~~

## 13. Production Design: Validate Before Commit, Stream After Commit

Before returning the response:
- Authenticate user/tenant and read authorization for the job.
- Verify the job exists and is in a streamable state.
- Check `Accept` and media type.
- Parse/verify the cursor.
- Select event source and replay window.
- Set response headers, idle policy, and cache policy.
- Determine whether the client is allowed to reconnect or resume.

After the response commits:
- Emit records/events using the versioned schema.
- Heartbeat per idle timeout.
- Keep queues/concurrency bounded.
- Convert errors to in-band events if specified by protocol.
- Cancel upstream and clean up on cancellation.
- Never alter already-sent status/body.

### 13.1. Separate Validation from the Body Publisher

A common mistake is putting all validation inside a `Flux.defer` and returning HTTP 200 before knowing whether the job is valid. When validation fails after commit, the client only sees a stream error.

When standard 404/403/400 responses are required, validate sync/async before creating the `ResponseEntity` body:

~~~java
return jobService.authorize(jobId, principal)
    .switchIfEmpty(Mono.error(new ResponseStatusException(
        HttpStatus.NOT_FOUND)))
    .map(job -> ResponseEntity.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(jobService.events(job)));
~~~

This is an illustrative fragment; define `principal`, `jobService`, and appropriate return types. `authorize` must complete before the response is created/committed. Errors occurring after `events(job)` has begun follow the stream error protocol.

### 13.2. Durable Jobs and Event Replay

For long-running reports/jobs:
1. POST creates the job, returning `202 Accepted` and `jobId`.
2. A worker processes the job independently of any HTTP connection.
3. Each event is persisted along with its sequence.
4. GET NDJSON/SSE reads events starting from the cursor.
5. Client disconnect stops only the subscriber, not the durable job.
6. The client reconnects with the cursor and receives the rest.
7. When the job finishes, emit `complete`; on failure, emit the persisted error code.

This pattern decouples execution from delivery. It avoids losing tasks just because of a browser refresh or brief network drop.

## 14. Security and Stream Access Control

Long-lived streaming has specific concerns:
- Authorization must be checked before commit and scoped by tenant/job.
- If permissions can be revoked while a stream runs, decide whether to re-check periodically or cancel the connection.
- Never put bearer tokens in query strings.
- Never let `Last-Event-ID` become an IDOR vector; a cursor does not replace authorization.
- Limit concurrent streams per user/tenant.
- Limit event payload size and sensitive fields.
- Validate event names/IDs; prevent user input containing CR/LF from breaking framing.
- Never put raw exceptions/stack traces into events.
- CORS and cookie credentials must have explicit policies; do not use wildcard origins with credentials.
- For SSE GET with cookie authentication, evaluate CSRF/session policies and route access rules.

Both NDJSON and SSE can carry private data. Streaming payloads incrementally does not relax security requirements compared to ordinary JSON responses.

## 15. Observability for Streaming Connections

A streaming request can last many minutes. "Request started" and "request completed" logs must be clearly distinguished; do not log once per event under high traffic.

Monitor:
- Active stream connections by bounded route/protocol/tenant group.
- Connection duration.
- Bytes/records/events emitted.
- Heartbeats sent.
- Client cancellations.
- Stream errors by error code.
- Resume/reconnect counts.
- Replay lag/cursor age.
- Queue depth and overflows.
- p95/p99 time-to-first-event and inter-event gap.
- Proxy idle timeouts/disconnects.
- Memory/direct buffers and network throughput.

Do not use job ID, user ID, or event ID as metric tags if cardinality is unbounded. Record them in structured logs/traces with appropriate access controls.

## 16. Thoroughly Testing Streaming

### 16.1. Unit Tests with StepVerifier

Verify:
- Record ordering.
- `complete` appears only after success.
- `stream-error` appears when upstream fails.
- Cancellation emits `SignalType.CANCEL`.
- Resuming a cursor starts from the next event.
- No duplicate sequences within a single stream.

### 16.2. HTTP Contract Tests with WebTestClient

Verify:
- Status before body begins.
- Exact `Content-Type`.
- Cache/buffering headers if part of the API contract.
- Each NDJSON object decodes properly.
- SSE event name/id/data.
- Heartbeats do not become business data.
- Reconnect with `Last-Event-ID`.
- Invalid cursor returns 400 before stream commit.
- Client cancel triggers upstream cleanup.

`WebTestClient` can return `FluxExchangeResult<T>` for long streams; `StepVerifier` asserts on the response body according to signals the client actually receives.

### 16.3. Testing Through Proxies/Load Balancers

Unit tests do not catch buffering in Nginx, ingress, or CDNs. Staging should confirm:
- Time-to-first-event.
- Whether events reach the client while the stream is still open or get buffered together.
- Heartbeats are frequent enough to prevent idle-timeout disconnects.
- Client disconnects propagate to the server.
- Whether compression adds latency.
- HTTP/2 works properly.
- Reconnect replays from the exact cursor.
- Deployments/rolling restarts do not lose durable events.

## 17. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning `Flux<T>` with `application/json` while expecting NDJSON | Client gets JSON document/array semantics | Use `application/x-ndjson` |
| Parsing each network chunk as JSON | A chunk can contain half a record or multiple records | Buffer and parse by newline |
| Not handling a final line without a newline | Last record lost | Parse remainder on EOF |
| Pretty-printing JSON in NDJSON | Embedded newlines break framing | Serialize compact single-line JSON |
| Sending an SSE event without a blank line | Browser does not dispatch the event | End every event with a blank line |
| Using a single newline as SSE delimiter | Events are not dispatched properly | Use a blank line |
| Using SSE comments as business events | Client receives no data callback | Use `data`/`event` fields |
| Not sending event IDs | Reconnect lacks a reliable cursor | Send stable IDs and replay |
| Accepting `Last-Event-ID` without replaying | Client gets duplicates or misses data | Read event store after cursor |
| Treating `retry` as business retry | Does not solve duplicates/loss | Idempotency + event replay |
| Missing heartbeats | Proxy closes idle stream | SSE comments or NDJSON heartbeat records |
| Heartbeats too frequent | Network/log/CPU overhead increases | Tune interval to idle timeout |
| Not disabling proxy buffering | Events get held at proxy | Configure proxy and verify in staging |
| Assuming `flush()` guarantees immediate client delivery | Proxies/transport can still buffer | Test the full network path |
| Using unbounded `onBackpressureBuffer()` | Memory grows with slow consumers | Bounded buffer and overflow policy |
| `collectList()` on large streams | High heap usage, response waits for completion | Stream element by element |
| Not handling cancellation | DB cursors/listeners/jobs leak | `doFinally`, `usingWhen`, cleanup |
| Assuming client disconnect cancels durable jobs | Jobs get lost unexpectedly | Decouple job lifecycle from connection |
| Returning HTTP 500 after sending 200 bytes | Committed status cannot be changed | In-band error frame/event |
| Missing a complete marker | Client struggles to distinguish success from truncation | Emit `complete` envelope |
| Emitting `complete` before persisting results | Client assumes job succeeded prematurely | Persist terminal state before emitting |
| Custom Authorization header on EventSource | Browser API does not support arbitrary headers | Appropriate cookies or fetch parser |
| Not bounding stream duration/connections | Holds sockets and state indefinitely | Quotas, timeouts, connection caps |
| Using event ID/user ID as metric tags | High cardinality | Tag by route/protocol/outcome |

## 18. Production Checklist

- [ ] Choose NDJSON or SSE based on consumer needs.
- [ ] Content-Type is exact and tested.
- [ ] NDJSON: UTF-8, one JSON value per line, LF delimiter, no outer array.
- [ ] SSE: UTF-8, `text/event-stream`, blank-line framing.
- [ ] Client parser handles arbitrarily split chunks and the final record.
- [ ] Event envelope has an explicit schema/version.
- [ ] Terminal `complete` and in-band error policies are defined.
- [ ] Validation/auth/cursor errors are handled before response commit.
- [ ] SSE event IDs are stable and replay genuinely uses the cursor.
- [ ] NDJSON has its own cursor/retry policy if resume is required.
- [ ] Heartbeat interval is smaller than proxy idle timeouts.
- [ ] Proxy buffering/caching/compression are configured and verified in staging.
- [ ] Queues/buffers/concurrency are bounded.
- [ ] The entire stream is never buffered in memory.
- [ ] Client cancel propagates upstream and resources clean up.
- [ ] Durable jobs have lifecycles decoupled from HTTP connections.
- [ ] Authorization is checked on every reconnect.
- [ ] Cursors cannot be used to read another tenant's data.
- [ ] No secrets in URLs or stream payloads.
- [ ] Limits exist for connection counts, duration, and event size.
- [ ] Metrics have bounded cardinality.
- [ ] NDJSON/SSE are tested with WebTestClient and StepVerifier.
- [ ] Cancellation, reconnect, cursor replay, and error frames are tested.
- [ ] Staging smoke tests pass through real proxies/load balancers.
- [ ] Runbooks exist for disconnects, backlogs, stream errors, and reconnect storms.

## 19. Practice Exercises

**Exercise 1 – JSON array vs. NDJSON.** Return the same 5 records with `application/json` and `application/x-ndjson`; observe how clients parse each contract differently.

**Exercise 2 – Client parser.** Write a test feeding NDJSON in chunks deliberately split inside a UTF-8 character, inside a JSON token, and across newlines; confirm the parser still reconstructs every record accurately.

**Exercise 3 – SSE event types.** Emit `progress`, `complete`, and `stream-error`; use `addEventListener` and call `EventSource.close()` at the right time.

**Exercise 4 – Heartbeat.** Have a source emit no business events for 30 seconds; send periodic SSE comments and verify the proxy does not idle-close the connection.

**Exercise 5 – Resume.** Disconnect after event 3, reconnect with `Last-Event-ID: 3`, and verify the next event is 4.

**Exercise 6 – NDJSON cursor.** Send `?after=3` and verify the stream emits only records after the cursor.

**Exercise 7 – Error after commit.** Emit two records then fail; verify the stream emits a `stream-error` frame and does not emit `complete`.

**Exercise 8 – Cancel.** Client cancels after the first record; verify the service receives `CANCEL` and DB cursors/listeners close.

**Exercise 9 – Slow consumer.** Slow down the client and speed up the producer; verify bounded queues and the overflow policy take effect.

**Exercise 10 – Durable job.** Keep a job running after HTTP disconnect; persist event sequences and replay when the client reconnects.

**Exercise 11 – Proxy buffering.** Enable and disable Nginx buffering; measure time-to-first-event and inter-event latency.

**Exercise 12 – Connection quota.** Open multiple concurrent streams; verify per-user limits, idle timeouts, and metric cardinality.

## 20. Official References

1. Spring Framework – Reactive WebFlux Core, streaming media types, flush, heartbeat, and DataBuffer: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
2. Spring Framework – Controller response bodies and reactive return values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html
3. Spring Framework – `ServerSentEvent` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ServerSentEvent.html
4. Spring Framework – WebTestClient and testing streaming with `FluxExchangeResult`/`StepVerifier`: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
5. WHATWG HTML Living Standard – Server-sent events, EventSource, Last-Event-ID, and event framing: https://html.spec.whatwg.org/dev/server-sent-events.html
6. MDN – Using server-sent events, reconnect, event names, and heartbeats: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
7. NDJSON specification – UTF-8, newline delimiter, and `application/x-ndjson`: https://github.com/ndjson/ndjson-spec
8. RFC 8259 – JSON Data Interchange Format: https://www.rfc-editor.org/rfc/rfc8259
9. Reactor Reference – Backpressure, cancellation, and lifecycle: https://projectreactor.io/docs/core/release/reference/
10. Spring Boot 4.0 – WebFlux and dependency management: https://docs.spring.io/spring-boot/4.0/reference/web/reactive.html

**Final self-check:** Why does `Flux<T>` with `application/json` not automatically have NDJSON framing? What must a client do when a network chunk contains only half a JSON record? On which delimiter is an SSE event dispatched? What good is `Last-Event-ID` if the server does not replay? Why does `retry` not guarantee exactly-once? Once a response has committed, why can status not change to 500? Should a client disconnect cancel a durable job? If you can answer these and run both endpoints along with the reconnect/cancel/error tests, you have mastered the protocol and lifecycle of NDJSON/SSE in Spring WebFlux.
