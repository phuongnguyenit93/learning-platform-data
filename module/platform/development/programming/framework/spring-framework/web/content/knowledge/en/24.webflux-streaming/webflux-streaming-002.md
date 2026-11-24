# Streaming JSON, NDJSON, and Choosing Media Types in Spring WebFlux

## 1. Context: A Flux Does Not Automatically Decide the HTTP Format

A Spring WebFlux controller can return `Flux<Event>` to represent multiple data items emitted over time. However, **`Flux<T>` is an application Publisher type, not a wire format**. The exact same `Flux<Event>` can be written by HTTP encoders as:

- **A single complete JSON array** with `Content-Type: application/json`, for example `[{"id":1},{"id":2}]`.
- **Newline-separated JSON values** with `Content-Type: application/x-ndjson`, for example one object per line.
- **Server-Sent Events (SSE)** with `Content-Type: text/event-stream`, each event framed with `id:`, `event:`, `data:`.
- Another binary/streaming format when using the corresponding codec, media type, and contract.

This difference directly affects when the client sees data, memory usage, backpressure, caching, browser support, status/error handling, and resumability after a connection drops.

For example, a report takes 10 seconds to produce 10,000 records:

- If the client simply wants to download a standard JSON document and parse the entire result: `application/json` is usually appropriate.
- If the client wants to process each record as soon as the server emits it, and both sides support line-oriented parsing: **NDJSON** is a better fit.
- If a browser wants to follow notification-style updates one-way over a long-lived connection: **SSE** is usually easier to consume than NDJSON via `EventSource`.
- If the requirement is a byte stream/file, or a protocol with different framing, you should not label it `application/json` just because the upstream data starts as Java objects.

**Scope:** Spring **WebFlux** (not Servlet MVC), Java **17**, Spring Boot **3.3.5**, Spring Framework **6.1.x**, Reactor `Flux`/`Mono`, Jackson JSON codec, annotated controllers, WebTestClient. The main topic is **JSON streaming, NDJSON, and media type selection**; sections on security, cancellation, and backpressure only explain the boundaries necessary for correct implementation.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish between a JSON document, JSON array, NDJSON, JSON Text Sequences, and SSE.
2. Explain why `Flux<T>` is encoded differently for `application/json` versus `application/x-ndjson`.
3. Design `produces`/`consumes`, `Accept`/`Content-Type`, and test 406/415 responses properly.
4. Write endpoints returning `ResponseEntity<Flux<DTO>>` as either a JSON array or NDJSON.
5. Accept `@RequestBody Flux<DTO>` as NDJSON, bound its size, and validate before side effects.
6. Use `WebTestClient` to verify JSON array contents, line framing, and reactive item decoding.
7. Understand the difference between encoder flushing and a client receiving individual network chunks.
8. Design status/headers and error policies when an HTTP response may already be partially committed.
9. Choose SSE, NDJSON, or regular JSON based on consumer, connection lifecycle, and business requirements.
10. Spot bugs involving event-loop blocking, unbounded buffers, request-body double-reads, stream cancellation, and data security.

## 2. Comparing the Three Formats First

Suppose the Java data consists of two events:

```java
new Event(1L, "order", "created");
new Event(2L, "order", "paid");
```

This snippet uses the `Event` record that will be declared in the full project.

### 2.1. A Single JSON Array: application/json

HTTP body:

```json
[
  {"id":1,"type":"order","message":"created"},
  {"id":2,"type":"order","message":"paid"}
]
```

This is **a single valid JSON document** whose root is an array. Even when Jackson prints compactly without whitespace, the array still has an opening bracket, element separators, and a closing bracket.

**Strengths:** understood by virtually all JSON parsers; convenient for small lists/complete responses, caching, schemas, and API tooling. **Limitations:** a JSON document is incomplete until its closing delimiter arrives; WebFlux encoders typically collect Flux elements to serialize a single JSON array when using a non-streaming media type. Do not assume the client receives the first record as soon as the upstream Flux emits it.

### 2.2. NDJSON: application/x-ndjson

HTTP body:

```text
{"id":1,"type":"order","message":"created"}
{"id":2,"type":"order","message":"paid"}
```

Each line is **an independent JSON text**. Records are separated by `\n` (newline), usually with a trailing newline. This is **not** a JSON array, and the concatenated string of objects is not a single JSON document that `JSON.parse(wholeBody)` accepts directly.

**Strengths:** a line-oriented parser can process each record as soon as a newline arrives; well-suited for large exports, append-only logs/events, ETL, and streaming pipelines. **Limitations:** schema/ordering/recovery must be defined by the application; parsers must handle partial incoming data and must never assume each TCP read or HTTP chunk corresponds to one line.

NDJSON stands for *Newline Delimited JSON* or *JSON Lines*. The standard MIME type in modern Spring WebFlux is **`application/x-ndjson`**. Legacy systems may use `application/stream+json`; do not assume they are automatically interchangeable without verifying codec/version/client support.

### 2.3. SSE: text/event-stream

HTTP body:

```text
id: 1
event: order
data: {"id":1,"type":"order","message":"created"}

id: 2
event: order
data: {"id":2,"type":"order","message":"paid"}

```

SSE uses **different protocol framing**: a blank line ends an event, `data:` holds the payload, `id:` supports reconnection via `Last-Event-ID`, and `event:` names the event. It can carry JSON inside data, yet it is **not NDJSON**. In browsers, `EventSource` is built to consume `text/event-stream`, not `application/x-ndjson`.

A browser EventSource is **unidirectional server → client**. If the client needs to continuously send messages bidirectionally, consider WebSocket or another suitable protocol.

### Summary Table

| Property | application/json | application/x-ndjson | text/event-stream |
| --- | --- | --- | --- |
| Framing | JSON document, typically an array | One JSON text per line | SSE fields + blank line |
| Ease of parsing | Very common | Requires an NDJSON parser | Browser EventSource or SSE parser |
| Multiple items over time | Possible from Flux, though encoder typically buffers before output | Yes, flushes per item via streaming codec | Yes, flushes per event |
| Parse before full body arrives | No with full-body JSON.parse | Yes, once each record's newline arrives | Yes, at each event boundary |
| Built-in browser client | fetch + response.json() | fetch streaming + TextDecoder/parser | EventSource |
| ID/reconnect semantics | App-defined | App-defined | `id`, `Last-Event-ID`, EventSource auto reconnect |
| Potentially infinite response | Not ideal with JSON array | Possible with bounds/protocol | Possible, needs heartbeat/cancel |
| Typical use | CRUD/small lists | Logs, exports, batch records | Live notifications, progress |

## 3. Media Types Are Part of the Contract, Not Decorative Labels

WebFlux uses `MediaType` to select the codec and response-writing behavior. Two decisions are usually independent:

- `Content-Type`: media type of **the HTTP body being sent**.
- `Accept`: media types that **the client wants to receive** in the response.

Example of a client requesting NDJSON:

```http
GET /api/streams/ndjson HTTP/1.1
Host: localhost:8080
Accept: application/x-ndjson
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"id":1,"type":"order","message":"created"}
{"id":2,"type":"order","message":"paid"}
```

With POST NDJSON, the client sends:

```http
POST /api/streams/ingest HTTP/1.1
Host: localhost:8080
Content-Type: application/x-ndjson
Accept: application/json

{"message":"first"}
{"message":"second"}
```

Here, the **request body** is NDJSON while the **response body** can be a single summary JSON object. Do not require `Accept: application/x-ndjson` just because `Content-Type` is NDJSON; the two directions are separate contracts.

### Constants to Use

```java
MediaType.APPLICATION_JSON
MediaType.APPLICATION_JSON_VALUE
MediaType.APPLICATION_NDJSON
MediaType.APPLICATION_NDJSON_VALUE
MediaType.TEXT_EVENT_STREAM
MediaType.TEXT_EVENT_STREAM_VALUE
```

These are Spring `org.springframework.http.MediaType` constants, not custom strings defined in the project. Use them in `@GetMapping(produces=...)`, `@PostMapping(consumes=...)`, `ResponseEntity.contentType(...)`, and WebTestClient.

### Commonly Confused Media Types

| Media type | Meaning | Note |
| --- | --- | --- |
| `application/json` | A single JSON representation/document | Does not mean line-oriented stream |
| `application/x-ndjson` | NDJSON, one JSON text per line | Use when consumers understand NDJSON |
| `text/event-stream` | Server-Sent Events | Has fields/event boundaries, not NDJSON |
| `application/json-seq` | JSON Text Sequences per RFC 7464 | Uses RS (ASCII 0x1E) framing; **not NDJSON** |
| `application/stream+json` | Legacy name seen in some Spring integrations | Depends on version/codec; prefer NDJSON when the contract allows |
| `application/octet-stream` | Arbitrary bytes | Carries no JSON/object stream semantics |
| `text/plain` | Plain text | May hold JSON-like text without a JSON codec contract |

**Do not choose `application/json-seq` instead of NDJSON just because both mean "multiple JSONs".** RFC 7464 uses the record separator character, whereas NDJSON relies on newlines. Parsers must agree on framing.

## 4. How Does Spring WebFlux Encode Flux to HTTP?

Requests pass through `DispatcherHandler`/result handling and `HttpMessageWriter` implementations. For JSON, Spring's `Jackson2JsonEncoder` and HTTP codecs operate based on element type, media type, and reactive publisher.

Mechanism:

```text
Controller's Flux<Event>
      |
      v
WebFlux HandlerResultHandler
      |
      v
HttpMessageWriter selects encoder by element type + media type
      |
      +--> application/json
      |      usually collects elements before encoding
      |      producing a single JSON array document
      |
      +--> application/x-ndjson
             encodes each Event into JSON text
             appends newline separator
             flushes per value for streaming media types
      |
      v
ServerHttpResponse.writeWith / writeAndFlushWith
      |
      v
Reactive HTTP adapter + network buffers + proxy
```

### Why Can Choosing NDJSON Reduce "Time-to-First-Item" Latency?

With `application/json`, the encoder usually needs the collection to form a complete JSON array. With a streaming media type, the encoder can encode, write, and **flush per value**, so it does not have to wait for the source to complete before pushing the first record down the output pipeline.

**However, flushing does not mean "arrived at the browser immediately"**:
- Reactor Netty has event loops and TCP buffers.
- The kernel has packetization and network latency.
- Reverse proxies/API gateways may enable buffering/compression.
- HTTP/2 flow control or a slow-reading client affects pacing.
- Client decoders may wait for a complete newline/frame.
- TLS transport and network chunk boundaries do not align with record boundaries.

Therefore, measure **server emission time**, **time to first byte**, and **client-observed first record**, rather than measuring only total latency.

### Flux<T> Is Not Necessarily a Streaming Response

```java
@GetMapping(path = "/json",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<Event> json() {
    return source.events();
}
```

Nothing in the `Flux<Event>` signature guarantees each Event is flushed individually. If you need an NDJSON contract, declare `produces=APPLICATION_NDJSON_VALUE` and test the response Content-Type and wire format.

### Do Not Use Flux<String> to "Automatically Create a JSON Array"

With Jackson codecs, `String` receives special handling and is typically treated as text content written by a CharSequence encoder rather than JSON DTOs serialized into JSON string elements. Therefore:

```java
// To return a proper JSON array of strings, use a single-value List:
@GetMapping(path = "/labels",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<List<String>> labels() {
    return Mono.just(List.of("first", "second"));
}
```

This snippet depends on imports for `GetMapping`, `Mono`, `List`, and `MediaType`. It explicitly produces the JSON array `["first","second"]`. Do not assume `Flux.just("first","second")` serializes into the same JSON array under all codec configurations.

## 5. Three Common Endpoint Patterns

### 5.1. Finite JSON List

```java
@GetMapping(path = "/list",
            produces = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<Flux<Event>> list() {
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(source.events());
}
```

The status and Content-Type are known immediately. The body is a Flux, but since the media type is regular JSON, the expected HTTP result after encoding is **a single JSON array**. Suitable when the list is finite and not overly large.

### 5.2. Finite NDJSON

```java
@GetMapping(path = "/ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
public ResponseEntity<Flux<Event>> ndjson() {
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(source.eventsWithDelay());
}
```

The source emits over time; the NDJSON encoder writes each object followed by a newline. Clients can process each record independently. Status 200 and headers are chosen before the body starts emitting. **If the third event fails after two lines have flushed, the status can hardly be changed to 500 anymore.**

### 5.3. Long-Lived or Infinite NDJSON

```java
@GetMapping(path = "/live",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<Event> live() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(n -> new Event(
                    n + 100, "heartbeat", "tick-" + n));
}
```

This snippet uses the three-field `Event` record defined below. `Flux.interval` uses a Reactor scheduler; it does not spawn a sleeping Java thread per request.

**Do not** call `collectList()` on an infinite Flux, because the Publisher never completes, so the list never emits and memory grows unboundedly. A live stream needs:
- Periodic heartbeats/idle behavior specification.
- Appropriate idle timeouts across server/proxy/client.
- Client cancellation cleanup.
- Event retention/replay policy if resume is required.
- Backpressure/sampling/drop policy if the producer outpaces the consumer.
- Concurrent connection limits.

## 6. SSE Differs from NDJSON Even When Data Is JSON

WebFlux supports `ServerSentEvent<T>` from `org.springframework.http.codec`:

```java
@GetMapping(path = "/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Event>> sse() {
    return source.eventsWithDelay()
            .map(value -> ServerSentEvent.<Event>builder()
                    .id(Long.toString(value.id()))
                    .event("change")
                    .data(value)
                    .build());
}
```

This snippet assumes an existing `source`. Server-Sent Events provide useful metadata to browser `EventSource` such as `id` and `event`, supporting reconnection. Plain NDJSON has **no** built-in protocol equivalent to `Last-Event-ID`; resuming requires a custom contract based on offsets/sequences/checkpoints.

### SSE Heartbeat

In a long-lived stream, if nothing is emitted for too long, broken connections may only be detected late, and reverse proxies may hit idle timeouts. SSE can emit comment-only heartbeats:

```text
: keep-alive

```

When writing complex WebFlux SSE streams, you can merge the event publisher with a ticker emitting comment-only `ServerSentEvent`s, while avoiding injecting heartbeats into streams where the business contract does not expect them. Client parsers must handle comments as defined by the SSE protocol.

### Do Not Pick SSE for Every Streaming API

SSE is convenient for browser notifications, yet usually unsuitable when:
- The client needs to POST a data stream to the server.
- Binary data is needed.
- A bidirectional protocol with command/data flows is needed.
- The client needs an NDJSON export processed by Unix line tools.

Conversely, NDJSON is typically suitable for server-to-server ETL/log exports without needing EventSource behavior.

## 7. Choosing a Media Type Based on Client Needs

| Need | Start With | Why |
| --- | --- | --- |
| A single DTO | `application/json` + `Mono<DTO>` | One JSON object |
| A small list (up to a few hundred items per policy) | `application/json` + list/finite Flux | Simple client parsing |
| Large export needing per-record processing | `application/x-ndjson` + `Flux<DTO>` | Per-line streaming |
| Browser dashboard receiving notifications | `text/event-stream` + SSE events | EventSource, id/reconnect |
| Client POSTing multiple incremental records | NDJSON request + `@RequestBody Flux<DTO>` | Producer/consumer stream |
| Transactional batch requiring upfront validation | `application/json` array + `Mono<List<DTO>>`/wrapper | Easy atomic validation/response |
| Raw file bytes | `application/octet-stream` or file-specific type | Avoids wrong framing |
| JSON sequence protocol per RFC 7464 | `application/json-seq` | RS framing per spec, not NDJSON |
| GraphQL/gRPC/WebSocket | Dedicated protocol | Do not disguise as NDJSON |
| Client only calls `response.json()` | `application/json` | Whole NDJSON body is not a JSON document |

**Questions before designing:** does the client read incrementally; if the server returns thousands of items, does the client have enough memory; is per-record ack/retry needed; is ordering required; are resume and event IDs needed; is there proxy buffering on the connection; when must the status code be known; how are mid-stream errors represented?

## 8. Content Negotiation: Accept, Content-Type, produces, consumes

`@GetMapping(produces=...)` constrains the response representation against `Accept`; `@PostMapping(consumes=...)` constrains the request body media type against `Content-Type`.

```java
@GetMapping(path = "/ndjson",
        produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<Event> ndjson() {
    return source.events();
}

@PostMapping(path = "/ingest",
        consumes = MediaType.APPLICATION_NDJSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<IngestReceipt> ingest(
        @RequestBody Flux<NewEvent> body) {
    return service.accept(body);
}
```

These snippets use classes/services from the example. Do not swap them:
- `Accept: application/x-ndjson` means the client wants to **receive** NDJSON.
- `Content-Type: application/x-ndjson` means the client **is sending** NDJSON.
- `produces` describes the response format.
- `consumes` describes the request-body format.

Examples:
- A GET to the NDJSON endpoint with `Accept: text/plain` may receive **406 Not Acceptable**.
- A POST to an NDJSON-only endpoint with `Content-Type: application/json` may receive **415 Unsupported Media Type**.
- Malformed JSON or syntactically invalid NDJSON lines typically result in **400 Bad Request**, depending on error handling.
- With browser `fetch`, cross-origin requests or credentials also trigger CORS preflight policies.

HTTP clients may send `Accept: */*`. When multiple mappings share the same path differentiated by media type, check content negotiation/ordering so clients do not accidentally get an unexpected format. For long-lived API contracts, explicit paths or headers can be easier to manage than implicit negotiation when streaming vs. non-streaming differ sharply in semantics.

## 9. Reading an NDJSON Request Body with @RequestBody Flux<T>

With NDJSON input:

```http
POST /api/streams/ingest HTTP/1.1
Content-Type: application/x-ndjson

{"message":"first"}
{"message":"second"}
```

The controller can declare:

```java
@PostMapping(path = "/ingest",
        consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Mono<Receipt> ingest(
        @RequestBody Flux<NewEvent> incoming) {

    return incoming
            .map(this::validate)
            .collectList()
            .map(events -> new Receipt(events.size()));
}
```

This is a **snippet** assuming `Receipt` and `validate`. `HttpMessageReader`/Jackson decoder produces `NewEvent` objects per NDJSON framing. However, `@RequestBody Flux<T>` **does not automatically guarantee**:
- That input is bounded in records/bytes.
- That all field constraints are validated as desired.
- That all events are persisted atomically.
- That client disconnect rolls back already-completed side effects.
- That each raw network packet contains exactly one JSON object.

### Choice: Process Record-by-Record or Collect a Batch?

**Record-by-record processing:**

```java
return incoming
        .concatMap(eventStore::save)
        .count();
```

Snippet assuming `eventStore.save` returns `Mono<?>`. `concatMap` preserves input processing order and enforces sequential concurrency. However, if the 5th record fails, the first 4 may already be saved: **not atomic**.

**Bounded batch collection:**

```java
return incoming.take(6)
        .collectList()
        .flatMap(list -> {
            if (list.size() > 5) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE,
                        "Too many records"));
            }
            return validateThenSave(list);
        });
```

Snippet assuming `validateThenSave`. If at most 5 records are allowed, read up to **6** to detect overflow; using `take(5)` and accepting the first 5 silently drops the excess. Then validate *everything* before any side effect if the contract requires integrity.

Limiting record count is **not enough** to protect the server against a single giant JSON object. Add byte limits, JSON nesting limits, timeouts, and business quotas.

## 10. Mid-Stream Errors: What If the HTTP Status Is Already Committed?

Suppose the server has already sent:

```text
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"id":1,"type":"order","message":"created"}
{"id":2,"type":"order","message":"paid"}
```

Then the source emits `Mono.error(new IOException(...))` before the 3rd record. In HTTP, status and headers are normally **already committed**. The framework cannot reliably turn the earlier stream into a fresh `500 application/problem+json` response; the client may simply observe an abrupt connection close, a truncated body, or a protocol-level error.

Therefore, for NDJSON exports:
- Document clearly that streams may be incomplete.
- Use stable event IDs/sequences so clients can detect missing records.
- If resume is needed, design checkpoints/`?afterId=...` and a retention policy.
- If all-or-nothing is required, do not start the response before finishing validation/computation; choose a JSON array or return a job ID to download a prepared file.
- Logging/metrics should track `onError` and `CANCEL` separately from HTTP 5xx.
- Do not retry an ingest stream with side effects without idempotency.

### What Not to Do

```java
// ANTI-PATTERN: all errors are masked by Flux.empty()
return source.eventsWithDelay()
        .onErrorResume(error -> Flux.empty());
```

If the server sent 2/3 records and the operator turns the error into normal completion, the client may mistakenly think the export succeeded completely. Only use a fallback if the protocol/business contract allows it, paired with an appropriate completeness indicator/checksum/end marker.

### Designing an End Sentinel When Required

Some protocols build an event wrapper:

```json
{"type":"row","data":{"id":1}}
{"type":"row","data":{"id":2}}
{"type":"end","count":2}
```

This is **not Spring's default NDJSON**, rather an application-specific contract. Clients must consider the stream complete only upon seeing `type=end` and verifying the count/checksum; if the socket closes before the marker, retry/resume. Never emit a fake end marker when upstream fails.

## 11. Reactive Backpressure and Its Relationship to HTTP Transport

Reactive Streams has `request(n)`/demand and cancellation. When the HTTP response consumer slows down, the pipeline can reduce upstream demand if codecs/server/runtime properly support it. However:
- `Flux.create` pushing unbounded callbacks can accumulate memory.
- Unbounded `onBackpressureBuffer()` can cause OOM.
- `collectList()` on an infinite stream never completes and grows memory.
- `flatMap` with high concurrency can alter ordering or overload downstream.
- `publishOn`/`subscribeOn` only switch schedulers; they do not make synchronous JDBC non-blocking.
- File reads/DB drivers have blocking APIs if the application uses them.

### Blocking Example

```java
// Avoid in the WebFlux event-loop path:
return source.events()
        .map(event -> blockingJdbcRepository.save(event));
```

This snippet assumes a repository; the JDBC call still occupies the executing thread. If you must use a blocking driver during migration:

```java
return source.events()
        .concatMap(event ->
                Mono.fromCallable(
                        () -> blockingJdbcRepository.save(event))
                    .subscribeOn(Schedulers.boundedElastic()));
```

This offloads to bounded workers; it **does not make JDBC non-blocking**. Configure connection pools, timeouts, concurrency, and cancellation strategy. For end-to-end non-blocking pipelines, use appropriate reactive clients/drivers.

### Order and Consistency

For sequential events, `concatMap` preserves processing order; default `flatMap` may complete out-of-order. If a stream reflects an aggregate transaction sequence, the contract must state ordering guarantees. HTTP/TCP preserves byte order on one connection, but upstream `merge`/`flatMap` can **produce** data out of order before encoding.

## 12. Security and Stream Operations

### Authentication/Authorization

An NDJSON export endpoint can return thousands of sensitive records. Require:
- Spring Security reactive authentication/authorization before starting the stream.
- Per-resource/tenant access checks to prevent IDOR.
- Never trust client-supplied `X-User` or `X-Role` headers as identity.
- Ensure permissions are not bypassed by a custom WebFilter creating a response stream.
- If a stream is long-lived and tokens expire or ACLs change, define a clear business policy for refreshing/terminating the stream.

### Privacy

An NDJSON record can still contain PII/secrets; newline delimiters do not mask data. Set `Cache-Control: no-store` or an appropriate cache policy for personal data to avoid shared CDN caching. Never log raw response bodies or `Authorization` headers. If delivering NDJSON as file exports, control retention lifetime, signed URL TTL, and access audits.

### Injection and Parser Safety

NDJSON is JSON syntax; it does not prevent XSS or downstream injection. If a consumer inserts `message` into the DOM using `innerHTML`, XSS risk remains; use `textContent`/escaping. If data enters downstream SQL/commands, use parameterized statements/proper escaping. Parsers should validate schema, max line length, max JSON depth, Unicode handling, and duplicate key policies.

### DoS/Resilience

- Bounded concurrent streams/users.
- Request/input limits by byte and record count.
- Idle/total duration limits per endpoint.
- Client disconnect/cancellation cleanup; never leave publishers/subscriptions open indefinitely.
- Retry/backoff/resume limits to prevent thundering herds.
- Proper reverse proxy buffering/timeouts; never disable all protections just to "stream fast".
- Metrics: bytes/second, emitted records, dropped items, active connections, p95 first-record latency, error/cancel counts.

## 13. Complete Spring Boot 3.3.5 Project

The demo includes these endpoints:

| Endpoint | Method | Request Content-Type | Response Content-Type | Purpose |
| --- | --- | --- | --- | --- |
| `/api/streams/json` | GET | No body | `application/json` | Flux of 3 items → JSON array |
| `/api/streams/ndjson` | GET | No body | `application/x-ndjson` | Flux of 3 items, emitted shortly apart |
| `/api/streams/sse` | GET | No body | `text/event-stream` | SSE with ID and event name |
| `/api/streams/live` | GET | No body | `application/x-ndjson` | Infinite stream, client cancels explicitly |
| `/api/streams/single` | GET | No body | `application/json` | One JSON object |
| `/api/streams/strings` | GET | No body | `application/json` | Proper JSON array of strings |
| `/api/streams/ingest` | POST | `application/x-ndjson` | `application/json` | Reads 1–5 records and returns summary, explicit validation |

No database is used. Data uses an immutable `List.of`; `Flux.delayElements`/`Flux.interval` demonstrate publishers emitting over time. There is no blocking I/O or manual `subscribe()`. The ingest endpoint **does not persist data**; it only validates and returns a summary to focus on codecs/framing.

### 13.1. Project Tree

```text
webflux-ndjson-demo/
├── pom.xml
└── src/
    ├── main/java/example/streaming/
    │   ├── StreamingApplication.java
    │   ├── StreamEvent.java
    │   ├── IncomingEvent.java
    │   ├── IngestReceipt.java
    │   ├── EventSource.java
    │   └── StreamController.java
    └── test/java/example/streaming/
        └── StreamControllerTest.java
```

### 13.2. pom.xml

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
    <artifactId>webflux-ndjson-demo</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

Add only `spring-boot-starter-webflux`, **never add `spring-boot-starter-web`**, so Spring Boot defaults to the reactive web application type. Jackson JSON support comes from the WebFlux starter. The Validation starter provides Jakarta Bean Validation `Validator`.

### 13.3. Application Class

**`src/main/java/example/streaming/StreamingApplication.java`**

```java
package example.streaming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamingApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamingApplication.class, args);
    }
}
```

### 13.4. DTO Records

**`src/main/java/example/streaming/StreamEvent.java`**

```java
package example.streaming;

public record StreamEvent(
        long id,
        String type,
        String message) {}
```

**`src/main/java/example/streaming/IncomingEvent.java`**

```java
package example.streaming;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record IncomingEvent(
        @NotBlank @Size(max = 80) String message) {}
```

**`src/main/java/example/streaming/IngestReceipt.java`**

```java
package example.streaming;

import java.util.List;

public record IngestReceipt(
        int accepted,
        List<String> messages) {}
```

Java 17 records are immutable DTOs, and Jackson supports JSON record serialization/deserialization in Boot 3.3.5. `@NotBlank` and `@Size` are validation metadata; the demo **invokes `Validator.validate(...)` explicitly** rather than assuming a Flux body is automatically checked under every custom validation policy.

### 13.5. EventSource: Data Source and Emission Cadence

**`src/main/java/example/streaming/EventSource.java`**

```java
package example.streaming;

import java.time.Duration;
import java.util.List;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class EventSource {

    private final List<StreamEvent> seed = List.of(
            new StreamEvent(1, "order", "created"),
            new StreamEvent(2, "order", "paid"),
            new StreamEvent(3, "order", "shipped"));

    public Flux<StreamEvent> snapshot() {
        return Flux.fromIterable(seed);
    }

    public Mono<StreamEvent> first() {
        return snapshot().next();
    }

    public Flux<StreamEvent> delayed() {
        return snapshot().delayElements(Duration.ofMillis(50));
    }

    public Flux<StreamEvent> live() {
        return Flux.interval(Duration.ofMillis(150))
                .map(n -> new StreamEvent(
                        n + 100, "heartbeat", "tick-" + n));
    }
}
```

`snapshot()` creates a Flux from a finite List; `delayed()` emits 3 items shortly apart using Reactor's scheduler without `Thread.sleep`; `live()` creates an infinite stream to test cancellation. Do not treat 50 ms/150 ms timings as hard deadlines: schedulers and OSes have jitter. In production, the source may be a change stream, message broker, or R2DBC; backpressure/cancellation must be handled at the real source.

### 13.6. Controller: JSON, NDJSON, SSE, and Ingest

**`src/main/java/example/streaming/StreamController.java`**

```java
package example.streaming;

import java.util.List;

import jakarta.validation.Validator;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/streams")
public class StreamController {

    private final EventSource source;
    private final Validator validator;

    public StreamController(
            EventSource source,
            Validator validator) {
        this.source = source;
        this.validator = validator;
    }

    @GetMapping(
            path = "/json",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Flux<StreamEvent>> json() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(source.snapshot());
    }

    @GetMapping(
            path = "/ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public ResponseEntity<Flux<StreamEvent>> ndjson() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_NDJSON)
                .cacheControl(CacheControl.noStore())
                .body(source.delayed());
    }

    @GetMapping(
            path = "/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<StreamEvent>> sse() {
        return source.delayed()
                .map(event -> ServerSentEvent
                        .<StreamEvent>builder()
                        .id(Long.toString(event.id()))
                        .event("change")
                        .data(event)
                        .build());
    }

    @GetMapping(
            path = "/live",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<StreamEvent> live() {
        return source.live();
    }

    @GetMapping(
            path = "/single",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<StreamEvent> single() {
        return source.first();
    }

    @GetMapping(
            path = "/strings",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<List<String>> strings() {
        return Mono.just(List.of("first", "second"));
    }

    @PostMapping(
            path = "/ingest",
            consumes = MediaType.APPLICATION_NDJSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<IngestReceipt>> ingest(
            @RequestBody Flux<IncomingEvent> incoming) {

        return incoming.take(6)
                .collectList()
                .map(records -> {
                    if (records.size() > 5) {
                        throw new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "At most five records");
                    }
                    if (records.isEmpty()) {
                        throw new ResponseStatusException(
                                HttpStatus.BAD_REQUEST,
                                "At least one record required");
                    }
                    for (IncomingEvent record : records) {
                        if (!validator.validate(record).isEmpty()) {
                            throw new ResponseStatusException(
                                    HttpStatus.BAD_REQUEST,
                                    "Invalid event");
                        }
                    }

                    List<String> messages = records.stream()
                            .map(IncomingEvent::message)
                            .toList();

                    return ResponseEntity.ok(
                            new IngestReceipt(
                                    records.size(), messages));
                });
    }
}
```

### Why Do These Endpoints Demonstrate the Media Types Properly?

- `json()` and `ndjson()` both return **`ResponseEntity<Flux<StreamEvent>>`**, so `Content-Type`/`produces` determines whether the encoder produces a JSON array or individual NDJSON lines.
- `sse()` returns `Flux<ServerSentEvent<...>>` and `text/event-stream`; on the wire there will be `id`/`event`/`data` and blank lines rather than plain NDJSON.
- `live()` emits continuously and the client must cancel; there is no `collectList()`.
- `single()` uses Mono for single-object cardinality.
- `strings()` avoids confusing `Flux<String>` with a JSON array of string values by returning a `Mono<List<String>>`.
- `ingest()` accepts NDJSON via `@RequestBody Flux<IncomingEvent>`, yet **returns a regular JSON object**; it caps at 5 records using `take(6)` and validates all of them before building the receipt.
- `cacheControl(CacheControl.noStore())` attaches the header to illustrate that streaming/private data should not be cached arbitrarily; in real apps, choose cache policies based on the data.
- `ResponseStatusException` is used when the body is syntactically valid but violates batch rules; decoder errors/malformed NDJSON go through WebFlux default error handling and do not turn into a receipt.

**Note:** The ingest demo only counts/validates and does not persist data. If adding a DB, you must design transactional/idempotent semantics; `collectList()` is not a DB transaction. If a client sends a giant single record, the 5-record limit does not replace request byte limits.

## 14. Running the Project and Observing the Wire Format

Install JDK 17+ and Maven. From the `webflux-ndjson-demo` directory:

```bash
mvn test
mvn spring-boot:run
```

Run the two commands **sequentially**. Once Boot starts, it listens on `http://localhost:8080` by default unless `server.port` is changed.

### 14.1. Regular JSON Array

```bash
curl -i \
  -H 'Accept: application/json' \
  'http://localhost:8080/api/streams/json'
```

Main parts of the response:

```http
HTTP/1.1 200 OK
Content-Type: application/json

[{"id":1,"type":"order","message":"created"},{"id":2,"type":"order","message":"paid"},{"id":3,"type":"order","message":"shipped"}]
```

The JSON serializer may use different spacing and additional headers. What to verify is **one root array with 3 items**, not 3 JSON documents separated by newlines.

### 14.2. NDJSON Output

```bash
curl -i -N \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/streams/ndjson'
```

Expected body:

```text
{"id":1,"type":"order","message":"created"}
{"id":2,"type":"order","message":"paid"}
{"id":3,"type":"order","message":"shipped"}
```

`curl -N` reduces buffering on curl's side so arriving data is easier to watch over time; it **does not** disable buffering at proxies/servers. With Spring 6.1's decoder, NDJSON output is generated per value with newline separators. Do not equate the number of HTTP chunks with the number of JSON lines.

### 14.3. SSE Output

```bash
curl -i -N \
  -H 'Accept: text/event-stream' \
  'http://localhost:8080/api/streams/sse'
```

The SSE body looks like:

```text
id:1
event:change
data:{"id":1,"type":"order","message":"created"}

id:2
event:change
data:{"id":2,"type":"order","message":"paid"}

id:3
event:change
data:{"id":3,"type":"order","message":"shipped"}

```

Some emitters/formatters may add a space after the colon; SSE parsers should not depend on that spacing. The distinguishing feature is the **`data:` field and blank line ending each event**, not merely newlines between JSON objects.

### 14.4. Live NDJSON and Disconnecting

```bash
curl -N \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/streams/live'
```

This is an **infinite stream**. Press `Ctrl+C` to stop the client after observing a few lines. Never use a JSON parser waiting for a closing `]`; the stream has no outer array. In a real API, the application must dispose subscriptions and clean up upstream resources when the client cancels.

### 14.5. POST NDJSON Input, Receive a JSON Receipt

In Bash:

```bash
curl -i -X POST \
  'http://localhost:8080/api/streams/ingest' \
  -H 'Content-Type: application/x-ndjson' \
  -H 'Accept: application/json' \
  --data-binary $'{"message":"alpha"}\n{"message":"beta"}\n'
```

Expected:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"accepted":2,"messages":["alpha","beta"]}
```

In PowerShell, Bash's `$'...'` syntax does not work; create an `input.ndjson` file containing those exact two lines and run:

```bash
curl -i -X POST \
  'http://localhost:8080/api/streams/ingest' \
  -H 'Content-Type: application/x-ndjson' \
  --data-binary '@input.ndjson'
```

This is portable across shells with real `curl`, though in Windows PowerShell `curl` may be a different alias; use `curl.exe` when needed.

### 14.6. Testing Content-Type and Accept Errors

```bash
curl -i -X POST \
  'http://localhost:8080/api/streams/ingest' \
  -H 'Content-Type: application/json' \
  -d '[{"message":"wrong-format"}]'

curl -i \
  -H 'Accept: text/plain' \
  'http://localhost:8080/api/streams/ndjson'
```

The ingest endpoint declares `consumes=application/x-ndjson`, so an `application/json` request does not match and typically receives **415 Unsupported Media Type**. The NDJSON GET declares `produces=application/x-ndjson`, so a client accepting only `text/plain` typically receives **406 Not Acceptable**.

### 14.7. Testing Validation on an NDJSON Line

```bash
curl -i -X POST \
  'http://localhost:8080/api/streams/ingest' \
  -H 'Content-Type: application/x-ndjson' \
  --data-binary $'{"message":"   "}\n'
```

Expected **400 Bad Request** because `@NotBlank` is checked manually via `Validator` in the handler. Spring Boot's default error body may vary by configuration; this demo does not claim a specific JSON error schema for it.

## 15. WebTestClient: Verifying JSON Array, NDJSON Framing, and Streaming

The test suite below runs with `RANDOM_PORT`, exercising the full reactive HTTP server pipeline, codecs, and content negotiation rather than just calling Java methods. Tests use immutable data so they do not depend on execution order.

**`src/test/java/example/streaming/StreamControllerTest.java`**

```java
package example.streaming;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class StreamControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void regularJsonReturnsOneArrayWithThreeEvents() {
        client.get().uri("/api/streams/json")
              .accept(MediaType.APPLICATION_JSON)
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      MediaType.APPLICATION_JSON)
              .expectBodyList(StreamEvent.class)
              .hasSize(3);
    }

    @Test
    void ndjsonHasThreeNonemptyLines() {
        client.get().uri("/api/streams/ndjson")
              .accept(MediaType.APPLICATION_NDJSON)
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      MediaType.APPLICATION_NDJSON)
              .expectBody()
              .consumeWith(result -> {
                  byte[] bytes = result.getResponseBody();
                  assertNotNull(bytes);

                  String body = new String(
                          bytes, StandardCharsets.UTF_8);
                  List<String> lines = body.lines()
                          .filter(line -> !line.isBlank())
                          .toList();

                  assertEquals(3, lines.size());
                  assertTrue(lines.get(0).contains("\"id\":1"));
                  assertTrue(lines.get(1).contains("\"id\":2"));
                  assertTrue(lines.get(2).contains("\"id\":3"));
              });
    }

    @Test
    void reactiveDecoderReadsNdjsonItems() {
        Flux<StreamEvent> events = client.get()
                .uri("/api/streams/ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .returnResult(StreamEvent.class)
                .getResponseBody();

        StepVerifier.create(events)
                .expectNextMatches(event -> event.id() == 1)
                .expectNextMatches(event -> event.id() == 2)
                .expectNextMatches(event -> event.id() == 3)
                .verifyComplete();
    }

    @Test
    void sseResponseUsesEventFraming() {
        client.get().uri("/api/streams/sse")
              .accept(MediaType.TEXT_EVENT_STREAM)
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      MediaType.TEXT_EVENT_STREAM)
              .expectBody()
              .consumeWith(result -> {
                  byte[] bytes = result.getResponseBody();
                  assertNotNull(bytes);
                  String text = new String(
                          bytes, StandardCharsets.UTF_8);
                  assertTrue(text.contains("id:"));
                  assertTrue(text.contains("event:"));
                  assertTrue(text.contains("data:"));
              });
    }

    @Test
    void ingestFluxOfTwoNdjsonObjects() {
        client.post().uri("/api/streams/ingest")
              .contentType(MediaType.APPLICATION_NDJSON)
              .accept(MediaType.APPLICATION_JSON)
              .body(Flux.just(
                      new IncomingEvent("alpha"),
                      new IncomingEvent("beta")),
                      IncomingEvent.class)
              .exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$.accepted").isEqualTo(2)
              .jsonPath("$.messages[0]").isEqualTo("alpha")
              .jsonPath("$.messages[1]").isEqualTo("beta");
    }

    @Test
    void ingestRejectsInvalidRecord() {
        client.post().uri("/api/streams/ingest")
              .contentType(MediaType.APPLICATION_NDJSON)
              .body(Flux.just(new IncomingEvent("   ")),
                      IncomingEvent.class)
              .exchange()
              .expectStatus().isBadRequest();
    }

    @Test
    void ingestRejectsMoreThanFiveRecords() {
        client.post().uri("/api/streams/ingest")
              .contentType(MediaType.APPLICATION_NDJSON)
              .body(Flux.range(0, 6)
                      .map(n -> new IncomingEvent("m" + n)),
                      IncomingEvent.class)
              .exchange()
              .expectStatus().isEqualTo(413);
    }

    @Test
    void rejectsWrongRequestContentType() {
        client.post().uri("/api/streams/ingest")
              .contentType(MediaType.APPLICATION_JSON)
              .bodyValue("{\"message\":\"one\"}")
              .exchange()
              .expectStatus().isEqualTo(415);
    }

    @Test
    void rejectsUnacceptableResponseType() {
        client.get().uri("/api/streams/ndjson")
              .accept(MediaType.TEXT_PLAIN)
              .exchange()
              .expectStatus().isEqualTo(406);
    }

    @Test
    void infiniteStreamCanBeCancelled() {
        Flux<StreamEvent> stream = client.get()
                .uri("/api/streams/live")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .returnResult(StreamEvent.class)
                .getResponseBody();

        StepVerifier.create(stream)
                .expectNextCount(2)
                .thenCancel()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void stringArrayIsValidJsonArray() {
        client.get().uri("/api/streams/strings")
              .accept(MediaType.APPLICATION_JSON)
              .exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$[0]").isEqualTo("first")
              .jsonPath("$[1]").isEqualTo("second");
    }
}
```

The test suite has **11 test methods**. When source files are created properly and tests pass, Maven typically reports `Tests run: 11, Failures: 0, Errors: 0` (output may vary by test runner). **The code was statically reviewed; while writing this Knowledge to Google Sheets, the Maven runtime was not executed.**

### What Does Each Test Verify?

- `regularJsonReturnsOneArrayWithThreeEvents`: the result list is a single JSON array of 3 DTOs.
- `ndjsonHasThreeNonemptyLines`: raw HTTP bytes contain three separate lines in the right event order.
- `reactiveDecoderReadsNdjsonItems`: the NDJSON response is decoded by WebTestClient into three `StreamEvent` items via Reactive Streams.
- `sseResponseUsesEventFraming`: contains `id:`, `event:`, `data:` fields; distinct from NDJSON.
- `ingestFluxOfTwoNdjsonObjects`: WebTestClient encodes the input Flux into NDJSON and the server decodes it into a Flux of DTOs.
- `ingestRejectsInvalidRecord`: Jakarta Validator rejects whitespace-only messages.
- `ingestRejectsMoreThanFiveRecords`: enforces the record count limit; 6 items return 413.
- `rejectsWrongRequestContentType`: POST's `consumes` rejects application/json.
- `rejectsUnacceptableResponseType`: GET's `produces` rejects text/plain.
- `infiniteStreamCanBeCancelled`: client receives two items and cancels; does not block waiting for an infinite stream to complete.
- `stringArrayIsValidJsonArray`: `Mono<List<String>>` has JSON array semantics.

### Why Not Assert That Every HTTP Chunk Is One Record?

An NDJSON line may be split across multiple TCP packets, or multiple lines may arrive in a single packet. Tests must parse using **newline delimiters** or a codec, not rely on HTTP chunk counts.

### Why Is StepVerifier Essential for Infinite Streams?

Calling `expectBody()` on a stream that never completes can hang forever or time out. `StepVerifier` with `thenCancel()` exercises a realistic client scenario: consume a few elements and close the subscription.

### Additional Tests for Production

- Slow downstream consumers, proxy buffering, and gzip/HTTP/2 interactions.
- Client disconnect before the last record and upstream cleanup.
- Mid-stream error after the first record and incomplete export detection.
- 1,000+ lines, max line/JSON nesting/byte size limits.
- UTF-8 characters split across network reads.
- Invalid JSON on the 2nd line.
- Sensitive data/cache directives.
- Tenant/owner authorization.
- Proxy and server timeouts/keepalives.
- Resume from event sequence or offset.
- Backpressure against a real broker/DB, not just an in-memory Flux.

## 16. Client Parsers: Reading NDJSON Safely

### 16.1. Python Client Reading Line by Line

Example Python client using `requests` with `stream=True`:

```python
import json
import requests

url = "http://localhost:8080/api/streams/ndjson"

with requests.get(
    url,
    headers={"Accept": "application/x-ndjson"},
    stream=True,
    timeout=(5, 30),
) as response:
    response.raise_for_status()
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        record = json.loads(line)
        print(record["id"], record["message"])
```

This example is runnable with the `requests` package installed; expected ID/message output is:

```text
1 created
2 paid
3 shipped
```

Do not call `response.json()` on an entire NDJSON body: it is not a single JSON document.

### 16.2. JavaScript Fetch Stream Parser

Browser `fetch` can read a `ReadableStream` by chunks. Concatenate partial chunks and split on newlines:

```javascript
async function readNdjson(url, onRecord) {
  const response = await fetch(url, {
    headers: { Accept: "application/x-ndjson" }
  });
  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }
  if (!response.body) {
    throw new Error("Streaming body unavailable");
  }

  const reader = response.body
    .pipeThrough(new TextDecoderStream())
    .getReader();

  let pending = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    pending += value;

    let newline;
    while ((newline = pending.indexOf("\n")) >= 0) {
      const line = pending.slice(0, newline).trim();
      pending = pending.slice(newline + 1);
      if (line.length > 0) {
        onRecord(JSON.parse(line));
      }
    }
  }

  // Accept a trailing line without a newline when allowed by the protocol.
  if (pending.trim() !== "") {
    onRecord(JSON.parse(pending.trim()));
  }
}

readNdjson("/api/streams/ndjson", event => {
  console.log(event.id, event.message);
});
```

This is a practical snippet for browsers supporting `fetch` streams and `TextDecoderStream`. For production:
- Bound `pending.length` so a malicious endless line cannot cause OOM.
- If the client requires a trailing newline to confirm integrity, do **not** treat trailing pending text as a complete record.
- Handle AbortController/cancellation, timeouts, retries, and CORS credentials.
- For the DOM, use `textContent` instead of `innerHTML` to avoid XSS from messages.
- Use a parser that handles CRLF (`\r\n`), whitespace, and invalid lines per contract.
- Behind reverse proxies, one `read()` call does not correspond to one record.

### 16.3. Unix Command-Line Tools

`curl -N` + line-oriented processors work well with NDJSON. For example, with `jq`:

```bash
curl -sS -N \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/streams/ndjson' \
  | jq -r '.id | tostring'
```

If the server returns 3 records as seeded, stdout is:

```text
1
2
3
```

Note that this pipeline depends on `jq` being installed; it is a CLI utility example, not a required step to run the Spring app.

## 17. Choosing ResponseEntity When Streaming Conditionally

If status/headers are known before emitting the stream:

```java
public ResponseEntity<Flux<StreamEvent>> export() {
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(source.delayed());
}
```

If you must check permissions/quotas or resource existence **asynchronously before returning status**, choose `Mono<ResponseEntity<Flux<StreamEvent>>>`:

```java
public Mono<ResponseEntity<Flux<StreamEvent>>> export() {
    return permissions.canExport()
            .map(allowed -> {
                if (!allowed) {
                    return ResponseEntity.status(
                            HttpStatus.FORBIDDEN)
                            .<Flux<StreamEvent>>build();
                }
                return ResponseEntity.ok()
                        .contentType(MediaType.APPLICATION_NDJSON)
                        .body(source.delayed());
            });
}
```

These two snippets assume `permissions` and `source`. Key points:

- `ResponseEntity<Flux<T>>`: HTTP envelope (status/headers) is chosen immediately when the controller returns.
- `Mono<ResponseEntity<Flux<T>>>`: HTTP envelope is chosen after the Mono check completes asynchronously; the Flux body can stream afterward.
- `Mono<ResponseEntity<T>>`: suitable for single-item requests choosing 200/404/201 based on the result.
- Once streaming starts, post-commit errors do not automatically turn 200 into 500.

In production, permission checks are not just a boolean; use Spring Security reactive authentication and check resource/tenant access at service boundaries. Never trust client-sent `X-Role` as "admin".

## 18. When Should You Return a Job ID Instead of Holding a Stream Open?

Not every long export needs a live HTTP stream. If generating a report takes 30 minutes, hits an expensive DB, or needs a file with a stable checksum, a better approach may be:

1. `POST /exports` returns **202 Accepted** with a job ID.
2. A background worker builds the export file into lifecycle-managed storage.
3. `GET /exports/{id}` returns status, checksum, and metadata.
4. Once done, the client downloads an `application/x-ndjson` or `application/json` file with a known content length and file integrity.
5. Enforce TTLs, access controls, auditing, retries, and idempotency.

Streaming is useful when truly incremental data is needed, yet long-lived open HTTP connections consume sockets, buffers, and tracking state; proxies/CDNs may time out. "Reactive" does not mean holding an HTTP connection open indefinitely is always superior to a job-based design.

## 19. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Flux produces 1 JSON array instead of lines | Response is `application/json` | Use `produces=application/x-ndjson` and compatible codec |
| Client's `JSON.parse(wholeBody)` fails | Body is NDJSON with multiple JSON texts | Parse line by newline delimiter |
| Client waits without seeing the first record | JSON codec collects Flux; proxy/client buffering | Use NDJSON/SSE, flush + measure client-side |
| A chunk holds half a JSON object | Transport chunks are not record framing | Buffer until newline |
| Strings like "first" don't become a JSON array | `Flux<String>` handled as text by writer | Use `Mono<List<String>>` for an array |
| SSE client fails to read NDJSON | EventSource requires `text/event-stream` | Return `Flux<ServerSentEvent<T>>` |
| NDJSON parser misreads `json-seq` | JSON-seq uses RS delimiters | Pick the right spec/framing |
| 406 Not Acceptable | `Accept` mismatches `produces` | Send matching header or offer another representation |
| 415 Unsupported Media Type | `Content-Type` mismatches `consumes` | Send the proper request media type |
| 400 on POST NDJSON | Malformed JSON line / DTO validation failure | Validate lines and input schema, log safely |
| Client sends 6 records but API accepts only 5 | Missing record count limit policy | `take(6)` + reject >5 |
| API accepts 5, drops the 6th | Using `take(5)` silently truncates | Read 1 extra to detect overflow |
| Stream returns 200 despite mid-stream error | Response already committed | Resume/end marker/error protocol |
| App memory grows with stream | `collectList()`/unbounded buffer | Bounded streams and limits |
| Thread pool stalls despite using Flux | Blocking JDBC/file/network call inside operator | Async driver or bounded offload |
| Ordering lost | `flatMap` concurrency | `concatMap` or sequence-aware merge |
| Proxy holds entire response | Proxy buffering/compression | End-to-end stream config/tracing |
| NDJSON leaks user data | Missing auth/tenant check/cache policy | Security + privacy + no-store |
| Client loses data after reconnect | No sequence/checkpoint | Event IDs, offsets, resume semantics |
| SSE ID fails to resume properly | Server does not handle `Last-Event-ID` | Retention/replay policy |
| Charset corruption with split Unicode packets | Decoding each binary chunk independently | Streaming TextDecoder |
| 413 does not appear as expected | Different codec/proxy limit | Test 413/400 and own the policy |
| Request body unreadable | WebFilter subscribed to raw DataBuffer first | Avoid double-reads, decorate properly |
| NDJSON record sends a JSON array on one line | Wrong client format | One JSON object per line |
| Streaming tests hang forever | Using `expectBody()` on infinite Flux | `StepVerifier` + `thenCancel` |
| Low throughput | Slow downstream, many buffered items | Measure source/encoder/network/client separately |

## 20. Real-World Implementation Checklist

- [ ] Clarify whether the client needs a JSON document, NDJSON, or SSE.
- [ ] Choose consistent `produces`/`consumes`, status codes, and headers.
- [ ] Test `Accept`/`Content-Type` along with 406/415 behavior.
- [ ] Do not equate `Flux<T>` with "streaming on the wire".
- [ ] Do not assume HTTP chunks/frames equal JSON lines.
- [ ] Use a client-side NDJSON decoder handling buffering, UTF-8, and newlines.
- [ ] Enforce limits on item counts, bytes/line, JSON depth, and request timeouts.
- [ ] Never call `collectList()` on unbounded/infinite streams.
- [ ] Check validation/auth/tenant access before side effects and response commit.
- [ ] Use `ResponseEntity<Flux<T>>` or `Mono<ResponseEntity<Flux<T>>>` at the right time to choose status.
- [ ] Never expect to change status after partial writes.
- [ ] Define schema, ordering, idempotency, and retry/resume contracts.
- [ ] Classify streaming errors/timeouts/cancellations in logs/metrics.
- [ ] Never block the event loop, manually subscribe, or double-read the request body.
- [ ] Propagate backpressure/bounds/cancellation to real upstream sources.
- [ ] If using SSE, define reconnect/`Last-Event-ID`/heartbeat policies.
- [ ] Behind reverse proxies, verify buffering, HTTP/2, TLS, and compression.
- [ ] Never log PII/tokens/raw event payloads, and never cache private data publicly.
- [ ] Test JSON lists, raw NDJSON lines, typed decoders, live cancellation, and SSE framing.
- [ ] Benchmark through a production-like deployment; server emission metrics alone are insufficient.
- [ ] Evaluate job-based exports when work is long-running and needs no live interaction.

## 21. Hands-On Exercises

### Exercise 1 — Switch Media Type

Change `/ndjson`'s annotation from `APPLICATION_NDJSON_VALUE` to `APPLICATION_JSON_VALUE`, then observe:
- The returned Content-Type.
- The raw body after all 3 items complete.
- How long until the client sees the first complete JSON document.
- What happens if you try parsing line-by-line as NDJSON.

Then restore the NDJSON configuration and write a WebTestClient test capturing raw bytes without assuming network chunk counts.

### Exercise 2 — Error After Partial Stream

Have `source.delayed()` emit two items and then emit a `Flux.error`. Check:
- Do the first two lines reach the client?
- Is the HTTP status still 200?
- How do WebTestClient/curl reflect the disconnect/error?
- Is an end marker needed to distinguish successful completion from a truncated stream?

Do not hardcode a test expecting "always returns 500" since the response may already be committed.

### Exercise 3 — Bounded Batch and Validation

Raise the maximum from 5 to 100:
- Use `take(101)`.
- Reject when item count exceeds 100 without silently truncating.
- Validate every object before writing.
- Add max line bytes/request bytes at the runtime/proxy layer.
- Test 100 valid records, 101 records, an invalid 2nd line, an empty stream, and mid-stream client cancellation.

### Exercise 4 — Browser Consumer

Write a `fetch()` + streaming NDJSON reader. Use `AbortController` to cancel after 2 records. Observe server logs/`doFinally` signals; avoid storing the entire payload in browser memory.

### Exercise 5 — SSE for a Dashboard

Create an event stream named `inventory-change` with `id` and JSON `data`. Consume it with EventSource and handle reconnection via `Last-Event-ID`. A durable event store or checkpoint is required to guarantee no lost events—simply adding an `id` field is not enough.

## 22. Self-Check Questions

1. Why is `Flux<Event>` not enough to determine the body on the wire?
2. How does `application/json` differ from `application/x-ndjson` when upstream is a 3-item Flux?
3. Why does `JSON.parse(wholeNdjsonBody)` usually fail?
4. Which delimiter does NDJSON use? Which delimiter do JSON Text Sequences (RFC 7464) use?
5. Is `text/event-stream` the same as NDJSON?
6. Which important fields does `ServerSentEvent` have?
7. In which direction do `Accept` and `Content-Type` differ?
8. What are `@GetMapping(produces=...)` and `@PostMapping(consumes=...)` used for?
9. When do HTTP statuses 406 and 415 typically occur?
10. Why is a `Flux<String>` not guaranteed to become a JSON array of strings?
11. What does `MediaType.APPLICATION_NDJSON` enable in the codec?
12. Does `curl -N` disable proxy buffering?
13. Should you parse NDJSON based on TCP packet/HTTP chunk boundaries?
14. Does NDJSON have built-in `Last-Event-ID` like SSE?
15. Can status 200 be changed to 500 JSON after 2/3 lines have been sent?
16. Why is `collectList()` on an infinite stream a serious bug?
17. Why must you read the 101st element to detect a batch >100?
18. Does `@Valid` replace authorization/tenant checks?
19. Does calling blocking JDBC inside `flatMap` become non-blocking thanks to Flux?
20. How does `Schedulers.boundedElastic` change where blocking happens?
21. Why is `concatMap` useful when event order matters?
22. Is HTTP status 404 necessarily a Reactor error signal?
23. Why do long-lived streams need heartbeats or idle policies?
24. If a client cancels, who is responsible for upstream cleanup?
25. Why should MIME type `application/json-seq` not be misused for NDJSON?
26. What should WebTestClient assert besides status to confirm framing?
27. If a client needs all data atomically, should you stream partial NDJSON?
28. Should user-specific NDJSON data be publicly cached at a CDN?
29. Why must clients buffer partial UTF-8 chunks and line fragments?
30. When should you use `202 Accepted` + a job ID instead of holding an HTTP stream open?

**Hints:** (1) Publisher type differs from wire media type. (2) JSON array vs. line-delimited objects/flushing. (3) Not a single JSON document. (4) LF vs. ASCII RS. (5) No, SSE has protocol fields. (6) id/event/data/retry/comment. (7) Receive vs. send. (8) Response vs. request media predicates. (9) Unacceptable `Accept` vs. unsupported request `Content-Type`. (10) Special String encoder. (11) Streaming JSON encoder/decoder. (12) No. (13) No. (14) No, resume must be custom-designed. (15) Not guaranteed because committed. (16) Waits for completion and grows RAM. (17) Reject accurately without truncating. (18) No. (19) No. (20) Offloads blocking, does not make the driver non-blocking. (21) Preserves order. (22) No. (23) Disconnect detection/proxy timeouts. (24) Application/source/client and reactive cancellation pipeline with proper ownership. (25) Different framing. (26) Content-Type, raw lines, decoded DTOs, cancellation. (27) Consider bounded JSON/job-based exports. (28) No, if sensitive. (29) Chunks do not match boundaries. (30) Long-running work needing job lifecycle/checksum/retries.

## 23. Official References

- [Spring Framework — WebFlux Reactive Core, HTTP Codecs, Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html)
- [Spring Framework — WebFlux @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html)
- [Spring Framework — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework — WebFlux ResponseEntity return types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html)
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — Server-Sent Events](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html#webflux-codecs)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Framework 6.1 — AbstractJackson2Encoder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/codec/json/AbstractJackson2Encoder.html)
- [Spring Framework 6.1 — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/codec/ServerSentEvent.html)
- [Project Reactor — Backpressure and Reactive Streams](https://projectreactor.io/docs/core/release/reference/)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 7464 — JavaScript Object Notation (JSON) Text Sequences](https://www.rfc-editor.org/rfc/rfc7464.html)
- [NDJSON specification repository](https://github.com/ndjson/ndjson-spec)

**Summary:** **Flux is a multi-value model, not an HTTP format.** With WebFlux/Jackson, `application/json` typically renders multiple values as **a single JSON array**; `application/x-ndjson` enables **per-value JSON text + newline**, encoding/writing/flushing element by element. `text/event-stream` is SSE with different framing and reconnect semantics. Choose the media type according to the **consumer protocol**, test Content-Type/Accept and byte framing properly, design backpressure/bounds, handle post-commit errors and cancellation, and never use reactive types as an excuse to skip validation, security, or downstream performance.
