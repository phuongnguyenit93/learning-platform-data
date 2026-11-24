# Data Size Limits, Consumption Rate, and Avoiding Full-Stream Collection in Spring WebFlux

## 1. Problem and Objectives

Spring WebFlux and Project Reactor help build **streaming** HTTP pipelines where the source, processing operators, and consumer can progress incrementally instead of waiting for the entire body to arrive. However, "an app returns `Flux`" **does not mean memory is always bounded**, "non-blocking" **does not mean infinite throughput**, and "having backpressure" **does not mean every downstream service, proxy, or database automatically slows down**.

A request can exceed limits because:
- The client sends a huge body or uploads slowly, and the server waits/buffers too many bytes.
- A JSON decoder is forced to buffer one huge object, even though the endpoint uses reactive APIs.
- Code calls `collectList()`, `collectMap()`, `reduce` with a growing accumulator, or unbounded `DataBufferUtils.join(...)`.
- A producer emits faster than the reader, causing buffers/queues in `flatMap`, hot sources, WebClient, or gateways to swell.
- A very large file download is read entirely into `byte[]` before sending the response.
- Retries, timeouts, connection pools, and concurrent requests push total memory up even when individual requests are bounded.

After this lesson, you will know how to:

1. Distinguish **size limits** (bytes/items), **rate limiting** (bytes/sec, requests/sec), **concurrency limiting**, **backpressure/demand**, **timeouts**, and **quotas**.
2. State the exact scope of `maxInMemorySize` in Spring WebFlux codecs, `DataBufferLimitException`, and `DataBufferUtils.join(source, maxByteCount)`.
3. Process `Flux<DataBuffer>` without retaining the whole body; count bytes with minimal state and release buffers once consumed.
4. Produce streaming NDJSON/SSE responses without unbounded materialization via `collectList()` or `block()` on the event loop.
5. Understand `limitRate`, `limitRequest`, `take`, `flatMap(..., concurrency)`, `concatMap`, `onBackpressureBuffer`, `onBackpressureLatest`, and `sample`, plus the consequences of dropping events.
6. Enforce limits across multiple layers: ingress, WebFlux codecs, application-level cumulative bytes, WebClient, connection pools, slow-client controls, and storage.
7. Run a **Java 17+, Spring Boot 3.x, Spring Framework 6.x** example with a hard-limited upload byte-counting REST endpoint and an NDJSON streaming endpoint; verify HTTP 200/413 and chunks using `WebTestClient`.
8. Design cleanup/cancellation/error handling, observe metrics, and avoid misinterpreting benchmark results.

**Scope:** WebFlux with Reactor/Reactive Streams and Reactor Netty common in Spring Boot 3.x. While Spring Framework 6.2 concepts are used to explain, verify APIs against your actual project version. This lesson does not claim WebFlux turns all application I/O non-blocking if blocking JDBC/SDK/file APIs sit underneath.

## 2. Data Flow Diagram and Where Memory Can Accumulate

An endpoint may pass through multiple buffering layers:

~~~text
HTTP client / upstream
         |
         | TCP incoming bytes / headers / chunks
         v
Ingress / CDN / reverse proxy
         |  - max request body
         |  - read timeout, slow client protection
         |  - buffering may be enabled/disabled per route
         v
Netty HTTP receive / request body Flux<DataBuffer>
         |
         |  decoder & message reader (JSON/NDJSON/multipart)
         |  maxInMemorySize applies per context
         v
Controller -> Reactor operators
         |  - map/filter, flatMap queues, buffers
         |  - collectList / join (aggregate!)
         |  - concurrency/prefetch/rate policy
         v
Service / WebClient / R2DBC / file storage
         |  - pool / DB connection / upstream timeout
         v
WebFlux response encoder / HTTP send
         |  - codec, TCP send buffers, slow reader
         v
Proxy / Browser
~~~

At every boundary, answer:
- **Who allocates data?** Java heap, direct/native buffers, temp disk, or remote queues?
- **Who owns release?** Framework decoder, DataBuffer owner, writer, store, cancellation handler?
- **Is there a clear hard limit?** Per element, per HTTP request, per user/tenant, per instance, and system-wide?
- **Is there true backpressure?** Does `Publisher` reach the source reader, or does an upstream service/message broker keep pushing?
- **Does any stage buffer the entire body before processing?** `bodyToMono(byte[].class)`, `collectList`, `join`, proxy buffering?
- **What happens if the client disconnects?** Does downstream cancel, are allocated buffers cleaned up, are partial files left on filesystem/object storage?

You must inspect the **entire chain**, not just drop in one Reactor operator and assume every layer is safe.

## 3. Distinguishing Five Commonly Confused Limits

| Mechanism | What It Controls | Example | Cannot Replace |
| --- | --- | --- | --- |
| **Size** | Total bytes/parts/items read | Max 10 MiB upload | Byte upload rate and request floods |
| **Rate** | Bytes/items processed per unit time | 1 MiB/s per tenant | Total bytes per single request |
| **Demand/backpressure** | Items downstream requests from upstream | Reactive Streams `request(n)` | Global rate limiting |
| **Concurrency** | Active operations/connections | At most 8 concurrent remote calls | Bytes/connection and timeouts |
| **Time/quota** | Deadlines, idle timeouts, capacity per user/day | 30 s/request, 1 GiB/day | Buffer leaks and malformed payloads |

For example: `flatMap(..., 8)` caps active inner subscriptions in that operator at roughly 8, **yet** if each subscription loads 1 GiB via `collectList`, the app can still OOM. A **10 MiB total byte** cap with no minimum upload rate lets a client hold a connection open for hours by sending 1 byte per minute. And `limitRate(16)` pulls from upstream in batches of up to 16 items, which **cannot** guarantee a rate of 16 events/second.

### 3.1. Calculating Total Resources by Concurrency

Suppose an application allows 200 concurrent uploads, each temporarily holding 1 MiB in memory. That alone can require ~**200 MiB**, excluding JVM, Netty direct buffers, TLS buffers, encoders, databases, and other requests.

~~~text
Total memory budget for buffers
  ≈ concurrent requests × buffered bytes/request
  + queues/caches/shared pools
  + framework and runtime overhead.
~~~

This is an **estimate**, not an exact heap equation: data may sit in native/direct memory, temp disk, or object storage. Bounding per-request size without a concurrency budget is still insufficient.

## 4. Backpressure: Item Consumption Demand, Not Wall-Clock Rate

In Reactive Streams, a subscriber calls `request(n)` to signal it wants up to `n` more elements. The Publisher may emit up to the requested amount per contract. Reactor operators propagate demand along the chain when the source supports it.

Example:

~~~java
Flux<Integer> source = Flux.range(1, 100);

Flux<Integer> boundedDemand = source.limitRate(8);
~~~

`limitRate(8)` splits large downstream demand into smaller upstream requests with replenishment. It does **not** insert `sleep(1/8s)`; an in-memory source can still emit all 100 items rapidly.

### 4.1. `limitRate` Is Not Bandwidth Throttling

~~~java
flux.limitRate(32);
~~~

This is Reactor `request(n)` batching; it does not constrain how many bytes each item holds. If each DataBuffer is 64 KiB, 32 items represent up to ~2 MiB of data; if each item is a few bytes, it is tiny. Moreover, uncooperative upstreams/bridges may have already buffered ahead.

`limitRate(highTide, lowTide)` configures demand/replenishment thresholds. `lowTide=0` requests in stricter batches, yet still is not a wall-clock token bucket.

### 4.2. `take(n)`/limitRequest Does Not Replace Byte Limits

~~~java
Flux<String> firstTen = source.take(10);
~~~

This only takes **10 items**, regardless of whether each item is 10 bytes or 10 MiB. If one giant NDJSON document or DataBuffer arrives as a single element, `take(10)` does not protect memory/bytes.

Reactor also provides `limitRequest(n)` to cap total demand through an operator per version docs; it bounds **item count**, not bytes or time.

### 4.3. `delayElements` Is Not Production Rate Limiting

~~~java
Flux.range(1, 5)
    .delayElements(Duration.ofMillis(200));
~~~

This demonstrates delayed item emission. Timers work for simple demos, yet `delayElements` does **not** manage global per-tenant quotas or real bandwidth across thousands of clients. If the source is hot, items may buffer/drop/overflow before reaching the operator; if downstream is slow, memory/queues still need a policy.

For real bytes/sec throttling, implement a token bucket/rate limiter over **bytes actually read or written**, ensuring it throttles the real data path rather than calling `Thread.sleep` on the event loop.

## 5. Codec `maxInMemorySize`: What Is Its Real Scope?

Spring WebFlux uses HTTP message readers and decoders to turn bytes into DTOs, JSON, form fields, multipart data, and text.

**`maxInMemorySize` is not a total-byte limit for every HTTP request or entire stream.** According to the Spring Framework reference:
- For `@RequestBody byte[]` or objects needing aggregation, the decoder may buffer data and apply the limit to the buffered portion.
- For NDJSON/JSON streams, the reader may buffer **each individual JSON object** before emitting; the limit typically applies to **one object's** size, not an infinite total of objects.
- For form fields, parts may be buffered per reader contract.
- For parsed multipart readers, the limit typically applies to non-file parts; for file parts, it acts as the **disk-spool threshold**, while max disk usage and part count have separate limits.
- For raw `Flux<DataBuffer>` bodies, you still need an **explicit hard byte count** in the app/ingress to cap the entire request.

### 5.1. Configuring Server-Side Codecs

~~~java
@Configuration
public class CodecBudgetConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(256 * 1024);
    }
}
~~~

This is an illustrative class; you must import `Configuration`, `WebFluxConfigurer`, `ServerCodecConfigurer`. In Spring Boot 3.x, you can also configure the property:

~~~properties
spring.codec.max-in-memory-size=256KB
~~~

Pick **one tested policy**; avoid adding conflicting custom codec configurers. 256 KiB is an example and also the default commonly documented for WebClient codecs; check your Boot version/codec. Appropriate sizing depends on the expected size of **one DTO/object**, not total file upload size.

### 5.2. DataBufferLimitException

When a decoder/join tries to buffer past the threshold, you may encounter:

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

Do not "fix" this by raising it to infinity or `-1` without understanding **why aggregation is happening**. Sensible steps:
1. Identify the aggregation point: `byte[]`, `String`, huge JSON object, `collectList`, `join`, multipart fields.
2. If business logic only needs row/record parsing, use `Flux<Record>` with a streaming format (NDJSON, SSE).
3. If large files are needed, stream with `Flux<DataBuffer>`/`FilePart` instead of `byte[]`.
4. If an object is inherently large and has a hard business limit, raise the budget just enough and test.
5. Set ingress/body size limits and application cumulative byte counts independently.

### 5.3. WebClient Has Its Own Codec Budget

~~~java
WebClient client = WebClient.builder()
        .codecs(c -> c.defaultCodecs()
                .maxInMemorySize(256 * 1024))
        .build();
~~~

This is a snippet within code that has imports. Calling `bodyToMono(String.class)` on a multi-MiB response may require aggregating into one String and hitting the limit. If the remote API supports NDJSON, use `bodyToFlux(Record.class)` with per-object bounds and HTTP connection limits; it still does not protect against unbounded total records if downstream calls `collectList`.

## 6. Avoiding Operators That Accidentally Collect the Whole Stream

### 6.1. Common Anti-Patterns

~~~java
Mono<List<Item>> all = itemFlux.collectList();
Mono<Map<String, Item>> map = itemFlux.collectMap(Item::id);
Mono<byte[]> bytes = webClient.get()
        .uri("/large-download")
        .retrieve()
        .bodyToMono(byte[].class);
Mono<DataBuffer> combined =
        DataBufferUtils.join(buffers);
~~~

These are **illustrative snippets** with assumed `Item`, `itemFlux`, `webClient`, `buffers`, and URI. These APIs have valid use cases when data is **small, bounded, and finite**, yet they create accumulation points:
- `collectList()` retains objects until the source completes; infinite sources never complete.
- `collectMap()` retains entries by key, growing with data cardinality.
- `bodyToMono(byte[].class)` materializes the entire response as one byte array.
- `DataBufferUtils.join(buffers)` merges/composes all DataBuffers from the source, potentially growing references/content unboundedly.
- `sort()`, or `reduce` with a growing list/string accumulator, also aggregates large data.
- Unbounded `cache()`, `replay()`, or replay-all sinks retain long-lived history.

**Prefer:** item-by-item processing, writing to bounded sinks, controlled-size transactional batches, or cursor-based pagination. For unbounded streams, never call `collectList` without a finite `take(n)` and per-item size limits.

### 6.2. When Is `collectList` Still Acceptable?

~~~java
return itemFlux
        .take(20)
        .collectList();
~~~

Acceptable when:
- Each `Item` also has a valid maximum size.
- 20 items is an appropriate business limit.
- No upstream operator has already aggregated huge data.
- Remote calls / timeouts / overall response size are controlled.
- Materializing 20 items before returning the response is acceptable.

`take(20)` does not replace per-item max-size validation. For pagination, return a finite `Page/Slice` using a database `LIMIT` rather than fetching millions of rows and calling `take(20)` in the application.

### 6.3. `DataBufferUtils.join(..., maxByteCount)`

When merging **a small payload with a hard maximum** is unavoidable, use the bounded overload:

~~~java
Mono<DataBuffer> joined =
        DataBufferUtils.join(buffers, 64 * 1024);
~~~

Javadoc confirms that exceeding `maxByteCount` emits `DataBufferLimitException` and releases accumulated buffers per contract. This is **not** infinite streaming: it still buffers until the source finishes within the limit.

If you receive the resulting buffer, the consumer must release the **joined buffer** after processing:

~~~java
return DataBufferUtils.join(buffers, 64 * 1024)
        .map(joinedBuffer -> {
            try {
                return decodeBoundedPayload(joinedBuffer);
            } finally {
                DataBufferUtils.release(joinedBuffer);
            }
        });
~~~

This snippet assumes an external `decodeBoundedPayload`. Do not manually release individual source buffers again once `join` has taken ownership per Javadoc; doing so causes double-release. Never assume raising `maxByteCount` makes a multi-GiB stream "non-blocking".

## 7. DataBuffer: Preserving Ownership While Counting Size

The lesson on **DataBuffer, Pooled Buffers, and Release Responsibility** covered `PooledDataBuffer`, `retain/release`, `join`, `write`, and leak detection in depth. Here, the key rule to apply is: **if your own code consumes a `DataBuffer` solely to count bytes and discards it, release after reading; if transferring the buffer to an HTTP writer, do not release early**.

| Case in a Byte-Bounded Pipeline | Who Is Responsible |
| --- | --- |
| Read `readableByteCount()` without forwarding the buffer | Consumer code calls `DataBufferUtils.release(buffer)` in `finally` |
| Pass `Flux<DataBuffer>` to the response writer | Writer takes ownership; do not release before `writeWith` |
| `DataBufferUtils.join(source, maxByteCount)` | Utility manages source buffers; consumer releases the **joined result** after use |
| Operator drops buffer on filter/cancel | Use `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` where operator supports discard |
| Write stream to file | Follow the specific `DataBufferUtils.write(...)` or `FilePart.transferTo(...)` contract; clean up partial files on cancel |

Example where a counter **consumes** a buffer without forwarding it:

~~~java
int size;
try {
    size = dataBuffer.readableByteCount();
} finally {
    DataBufferUtils.release(dataBuffer);
}
~~~

This snippet sits in a method with `DataBuffer dataBuffer` and `DataBufferUtils` imported. For response emission, flip ownership: hand off to the writer instead of releasing here. Never release **twice**, and remember to bound the number of in-flight buffers as well, not just single-buffer size.

**Avoid fake streaming:** `Files.readAllBytes(path)` followed by `Mono.just(byteArray)` both uses a blocking filesystem API and materializes the entire file. For large payloads, stream via `Resource`/`Flux<DataBuffer>` with byte caps, timeouts, and cancellation cleanup. `doOnDiscard` only supplements discard-aware operators and does not handle references kept in custom application collections.

## 8. Counting Bytes on the Stream Instead of Reading Everything: A Safe Pattern

Suppose the demo needs to protect a binary upload endpoint with a **64 KiB** hard limit. The body is received as `Flux<DataBuffer>`, keeping only a **`long` counter** and releasing each buffer:

~~~java
return Mono.defer(() -> {
    AtomicLong bytes = new AtomicLong();
    return body.concatMap(buffer -> {
        try {
            int n = buffer.readableByteCount();
            if (n > MAX_BYTES - bytes.get()) {
                return Mono.<Void>error(
                    new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE,
                        "body exceeds limit"));
            }
            bytes.addAndGet(n);
            return Mono.<Void>empty();
        } finally {
            DataBufferUtils.release(buffer);
        }
    }, 1)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .then(Mono.fromSupplier(() -> new Receipt(bytes.get())));
});
~~~

This is an **illustrative method body**; the full controller in Section 13 has complete imports and routes. Key reasons:

1. `Mono.defer` creates counting state **per subscription**, avoiding mutable state on the singleton controller.
2. `concatMap(..., 1)` processes sequentially with low prefetch, avoiding reordering/racy updates in the demo.
3. Checking `n > MAX_BYTES - bytes.get()` instead of `bytes.addAndGet(n) > MAX_BYTES` avoids integer overflow when limits are larger in real apps.
4. `finally` always invokes `DataBufferUtils.release(buffer)` after reading byte count, even when returning an error.
5. Once exceeded, `Mono.error` yields HTTP 413 before the response commits and cancels the upstream subscription. There is **no need** to read the remaining body into RAM just to prove the limit was exceeded.
6. `.doOnDiscard(...)` is an **extra** safeguard for discard-aware operators, not a replacement for primary release.
7. Since the response is a small Receipt returned **after the body is consumed or errors**, there is no need to retain the full body to build JSON.
8. The demo does not measure bytes/sec upload rate or block slowloris; enforce those at ingress/transport.

### 8.1. Is `Content-Length` Trustworthy?

You can inspect `Content-Length` early before reading—for instance, rejecting a request declaring 1 GiB when quota is 10 MiB. However:
- Requests may omit `Content-Length` (chunked/streaming).
- Proxies may rewrite the header.
- Clients should not be trusted for quota enforcement; you must count **bytes actually received**.
- Decoded bodies may differ in size from **compressed/encoded wire bytes**: clarify whether the limit applies to wire bytes, decompressed bytes, or business payload.
- Compression/decompression bombs require a hard cap after decompression if compressed uploads are supported.

Thus, checking `Content-Length` is a fast-fail optimization, **not a substitute** for a streaming cumulative byte guard.

## 9. Controlling Consumption Rate and Upstream/Downstream Mismatch

### 9.1. Backpressure When Upstream Cooperates

In a Reactor pipeline:

~~~java
Flux<Item> stream = repository.findMany()
        .limitRate(16)
        .flatMap(this::sendToUpstream, 4);
~~~

This snippet assumes `repository`, `Item`, and `sendToUpstream`. `limitRate(16)` tunes request batching; `flatMap(..., 4)` bounds concurrent inner subscriptions. If the downstream HTTP API only allows 10 QPS, **4 concurrent calls** do not guarantee ≤10 QPS; you need a rate limiter/downstream capacity control.

A sequential version:

~~~java
Flux<Result> stream = items
        .concatMap(item -> process(item));
~~~

`concatMap` processes inner streams sequentially, preserving order; throughput may be lower than `flatMap`. If per-item processing is blocking, `concatMap` does not move it off the event loop; use a non-blocking client or bounded offload.

### 9.2. Item Rate Differs from Byte Rate

If you must cap at **1 MiB/second**, calling `limitRate(100)` on `Flux<DataBuffer>` is wrong when buffer sizes vary. You need a **byte-aware rate limiter**, such as a token bucket measuring elapsed time with concurrency-safe state and admission budgets, or egress shaping at the reverse proxy/gateway/object storage.

One mechanism to slow a reactive source is `delayElements`, though:
- It only fits small data and cold sources with controlled item counts—not a proper bandwidth throttling system.
- It does not automatically share limits across multiple requests from the same tenant.
- If a source emits continuously faster, you must know which queue holds the backlog.
- **Never call `Thread.sleep` on the Reactor Netty event loop**; it blocks all other connections sharing that event-loop thread.

### 9.3. FlatMap Prefetch and Buffers

`flatMap`, `publishOn`, `buffer`, `window`, and `groupBy` each have prefetch/queue semantics. When a pipeline buffers or runs too many inner operations, it can retain many objects before downstream processes them. Make sure to:
1. Choose an explicit concurrency budget in `flatMap(fn, concurrency)`.
2. Consider appropriate prefetch overloads for your version when handling large items.
3. Consider `concatMap` for sources needing strict order and bounded memory.
4. Avoid unbounded-cardinality `groupBy` without fully consuming groups.
5. Never buffer an entire streaming source into `collectList` at the end.
6. Measure active memory and queue lengths under realistic load.

### 9.4. Hot Sources and Overflow Policies

With `Sinks.Many` or message brokers, producers can emit before downstream is ready. Reactor offers operators:

~~~java
source.onBackpressureLatest();
source.onBackpressureDrop();
source.onBackpressureBuffer(128);
~~~

These are illustrative snippets, each returning a new `Flux`; in real code they must be composed into the return chain. Semantics:
- **Latest**: drops older data, keeping the most recent update when demand is lacking.
- **Drop**: drops events when demand is lacking.
- **Buffer(128)**: retains up to a bounded item count, then signals overflow per overload/policy.
- Buffer size is **item count**, not bytes. A single 10 MiB object still creates heavy pressure.
- The source itself may have its own buffer before the operator; bounding one operator does not protect every boundary.

Use drop/latest for telemetry/dashboards where only the latest state matters; **never drop** transactions/orders/audit events that must be delivered intact. When reliable replay is required, use a durable event log + cursor/idempotency, not just an in-memory sink.

## 10. Streaming Responses: NDJSON, SSE, and Binary Bytes

### 10.1. JSON Arrays Are Usually Treated as One Document

An `application/json` response with body `[{"id":1}, ...]` may force consumers to wait for the full array or use specialized streaming JSON parsers. For record-by-record processing, pick a framing-friendly media type such as:
- `application/x-ndjson` for **one JSON object per line**.
- `text/event-stream` for SSE events (`data:`, optional IDs).
- `application/octet-stream` when streaming raw binary bytes/files.
- Custom framing/protocol if both sides agree.

Choose the format based on client decoding and business contracts—not just changing `produces` while still calling `collectList()` before returning.

### 10.2. NDJSON Example

~~~java
@GetMapping(path = "/numbers",
        produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<StreamItem> numbers() {
    return Flux.range(1, 5)
            .delayElements(Duration.ofMillis(70))
            .map(i -> new StreamItem(i, "item-" + i));
}
~~~

This method appears in the complete class in Section 13. Returning `Flux` lets the codec encode item-by-item without collecting all five items before writing HTTP. `delayElements` is for demo observation; it is **not** a business throughput guarantee.

### 10.3. SSE When Update Counts Are Unbounded

~~~java
@GetMapping(path="/events",
        produces=MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(i -> ServerSentEvent.<String>builder()
                    .event("tick")
                    .data("tick-" + i)
                    .build());
}
~~~

This snippet sits in a WebFlux controller with imports. Browsers use `EventSource`/named event listeners. This is an **infinite Flux**, so **never call `collectList()`** on it, and in integration tests use `take(n)` then cancel. SSE connections also need heartbeats, proxy flushing, active connection caps, and replay policies on disconnect.

### 10.4. Chunked Binary Download

An HTTP file/download response can return a `Flux<DataBuffer>` created via `DataBufferUtils.read(Path, DataBufferFactory, bufferSize)` or an appropriate `Resource`:

~~~java
Flux<DataBuffer> chunks = DataBufferUtils.read(
        filePath, new DefaultDataBufferFactory(), 8192);
~~~

Snippet assuming `Path filePath`. It avoids reading `Files.readAllBytes(filePath)` upfront, while requiring:
- Checking authorization before opening the file.
- Validating path/size and preventing path traversal.
- Letting the HTTP writer consume/release buffers per contract. Never release each buffer **before** the HTTP writer receives it.
- Handling source errors/cancellation and resource cleanup.
- Preventing public endpoints from opening thousands of unbounded file handles.
- Honoring HTTP range/ETag/cache policies if resumable downloads are supported.

When working with filesystem APIs, choose `DataBufferUtils.read` or `Resource`/HTTP resource writers in the proper context rather than reading files synchronously on the event loop.

## 11. WebClient: Avoid Aggregating Large Responses Accidentally

A gateway microservice calling upstream via `WebClient` can accidentally turn streaming into full aggregation.

### Anti-Pattern

~~~java
Mono<byte[]> all = webClient.get()
        .uri("/api/huge-file")
        .retrieve()
        .bodyToMono(byte[].class);
~~~

The data must materialize as a single `byte[]` before the consumer receives it. To relay a stream:

~~~java
Flux<DataBuffer> body = webClient.get()
        .uri("/api/huge-file")
        .retrieve()
        .bodyToFlux(DataBuffer.class);
~~~

Snippet: `body` returns raw `DataBuffer`s from WebClient; if piping straight into an HTTP server response, **understand ownership** and ensure the downstream writer receives/releases properly. If subscribing to read or discard the stream yourself, clean up buffers. Never call `.subscribe()` and return 200 before upstream completes.

For small bounded JSON, `bodyToMono(Dto.class)` is completely reasonable; the goal is **knowing what should and should not aggregate**.

### Outbound Limits to Configure

- WebClient codec `maxInMemorySize` for buffered decoding.
- Total remote response body byte limits if consumers disallow large files.
- HTTP client connection pool max connections and pending acquire timeouts.
- Connect/response/read timeouts and overall business deadlines.
- Rate limits and concurrency budgets per upstream/tenant.
- Bounded retries + backoff when idempotent; never retry infinitely.
- Max redirects/trusted hosts to prevent SSRF in proxy download features.
- Metrics on buffered bytes and slow downstream consumers.

Do not treat `timeout(Duration.ofSeconds(5))` as a byte cap: a fast upstream can send gigabytes well within 5 seconds. Conversely, a size cap with no timeouts lets ultra-slow clients hold connections indefinitely.

## 12. Numerical Budget Example

Suppose a system has:
- 4 instances.
- Up to 100 concurrent streaming requests per instance.
- 64 KiB pipeline application buffer allowance per request.
- HTTP writers also hold network buffers and event-loop queues.
- Downstream storage pool capped at 10 concurrent writes/instance.

An idealized application-buffer budget:

~~~text
100 requests × 64 KiB = 6,400 KiB ≈ 6.25 MiB / instance.
4 instances × 6.25 MiB = 25 MiB (one buffer type only).
~~~

**This is an illustrative calculation**, not measured telemetry; real total RSS/heap/direct memory can be substantially higher due to decoders, TCP, TLS, in-flight requests, object headers, temp files, and GC. Low thread counts do not prove low memory if per-request buffers and total connections keep growing.

If a queue uses `onBackpressureBuffer(128)` with 1 MiB items, that queue alone can hold roughly **128 MiB for a single subscriber**, excluding overhead. Bound **byte size** in addition to item count whenever item sizes vary.

### Where to Measure?

| Metric | What to Watch |
| --- | --- |
| JVM heap/live objects | Retained memory and GC frequency |
| Direct/native buffer allocation | Netty pooled buffer leaks, off-heap pressure |
| Active connections/in-flight streams | Server and client stream counts |
| Request/response bytes | P50/P95/P99 sizes and user/tenant quotas |
| Processing latency & p99 | Including timeouts/errors |
| Rate-limited/rejected requests | 413/429/503 counts and causes |
| Reactor scheduler queues | `boundedElastic` blocking work saturation |
| WebClient pending connections | Pool saturation, slow upstreams |
| DB/Redis pools/queries | Actual data processing progress |
| Downstream consumer lag | Backpressure, buffering, or dropped events |
| Temp disk/object storage staging | Spilled uploads or uncleaned files |

A rising "RPS" chart is insufficient if p99 latency, 413/503 errors, direct memory, or GC pauses are also climbing.

## 13. Practical Spring Boot 3.x / Java 17 Example

The demo project includes:
- `POST /api/stream/measure`: accepts **`application/octet-stream`**, counts bytes across `Flux<DataBuffer>` and releases each buffer, enforces a **64 KiB/request** limit, and returns JSON `{"bytes":N}`.
- `GET /api/stream/numbers`: returns **streaming NDJSON** of 5 records without collecting into a List in the controller.
- `GET /api/stream/ticks`: returns **SSE** from `Flux<ServerSentEvent<String>>`, running until cancelled.
- `WebTestClient`: verifies 4 bytes are accepted, 65,537 bytes return 413, NDJSON reads record-by-record, and SSE cancels after `take(2)`.
- `WebFluxConfigurer` sets a 256 KiB decoder budget. **The 64 KiB upload limit is separate logic**, independent of codec `maxInMemorySize`.

The demo **excludes** auth, admission control, gateway max-body config, slowloris defenses, virus scanning, and multi-tenant quotas; add those layers before public deployment.

### 13.1. Project Dependencies

Create a Spring Initializr Maven project with Java 17+, Spring Boot 3.x, `Spring Reactive Web`, and `Spring Boot Starter Test`. Ensure it contains:

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

This is a **fragment** placed in the Initializr-generated `pom.xml`, not a standalone Maven file. Adding both `spring-boot-starter-web` and WebFlux usually makes Boot 3.x default to the MVC application type; include only the WebFlux starter for this demo.

Structure:

~~~text
src/main/java/com/example/demo/
    DemoApplication.java
    StreamCodecConfig.java
    StreamController.java
src/test/java/com/example/demo/
    StreamControllerTest.java
~~~

### 13.2. DemoApplication.java

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

### 13.3. StreamCodecConfig.java

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class StreamCodecConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(256 * 1024);
    }
}
~~~

Reminder: this codec setting limits **decoder buffering** and does not guard total upload size. To cap total body at 64 KiB, the route **counts actual bytes**.

### 13.4. StreamController.java

~~~java
package com.example.demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
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
@RequestMapping("/api/stream")
public class StreamController {

    private static final long MAX_BYTES = 64L * 1024;

    @PostMapping(path = "/measure",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public Mono<ByteReceipt> measure(
            @RequestBody Flux<DataBuffer> body) {

        return Mono.defer(() -> {
            AtomicLong bytes = new AtomicLong();

            return body.concatMap(buffer -> {
                        try {
                            int n = buffer.readableByteCount();

                            // Check remaining budget before addition:
                            if (n > MAX_BYTES - bytes.get()) {
                                return Mono.<Void>error(
                                    new ResponseStatusException(
                                        HttpStatus.PAYLOAD_TOO_LARGE,
                                        "raw body exceeds 64 KiB"));
                            }

                            bytes.addAndGet(n);
                            return Mono.<Void>empty();
                        } finally {
                            DataBufferUtils.release(buffer);
                        }
                    }, 1)
                    .doOnDiscard(
                        DataBuffer.class, DataBufferUtils::release)
                    .then(Mono.fromSupplier(() ->
                            new ByteReceipt(bytes.get())));
        });
    }

    @GetMapping(path = "/numbers",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<StreamItem> numbers() {
        return Flux.range(1, 5)
                .delayElements(Duration.ofMillis(70))
                .map(i -> new StreamItem(i, "item-" + i));
    }

    @GetMapping(path = "/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ticks() {
        return Flux.interval(Duration.ofMillis(100))
                .map(n -> ServerSentEvent.<String>builder()
                        .event("tick")
                        .data("tick-" + n)
                        .build());
    }

    public record ByteReceipt(long bytes) {}

    public record StreamItem(int sequence, String label) {}
}
~~~

**Safety and boundary analysis:**
1. The controller is a singleton bean, yet `AtomicLong` state is created inside `Mono.defer` **per subscription**, avoiding shared mutable fields.
2. `concatMap(..., 1)` processes buffers sequentially with low prefetch; every buffer is released in `finally`.
3. Exceeding `MAX_BYTES` emits `ResponseStatusException(413)` **before returning the Receipt body**, without retaining the whole body in RAM. Upstream can be cancelled instead of reading the rest of the request.
4. `MAX_BYTES - bytes.get()` prevents overflow when adding; `long` gives far larger byte-counting headroom than `int`.
5. `doOnDiscard` supplements discard-aware operators; it does not prove every framework-allocated buffer not yet delivered will be cleaned up in every network error scenario. Run integration/stress tests under Netty's pooled buffer leak detector when using direct buffers.
6. `numbers` returns a finite 5-item NDJSON `Flux<StreamItem>`; the codec can encode/flush per item without `collectList` in the controller.
7. `ticks` emits infinite SSE; subscriptions must cancel when clients leave. Production apps need connection caps, heartbeat/proxy settings, and source lifecycle cleanup.
8. `delayElements`/timers here **only illustrate streaming visually**; they are not global bandwidth or QPS limiters.
9. The demo neither creates files nor publishes uploads, so staging file cleanup does not apply. Real file uploads need staging, atomic publishing, and cancellation cleanup.
10. The 256 KiB codec setting does not override the 64 KiB total-byte limit: the two policies operate at different layers.

### 13.5. StreamControllerTest.java — HTTP Integration Tests

~~~java
package com.example.demo;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamControllerTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void acceptsSmallBodyAndCountsExactBytes() {
        client.post()
                .uri("/api/stream/measure")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .bodyValue(new byte[] {1, 2, 3, 4})
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.bytes").isEqualTo(4);
    }

    @Test
    void rejectsActualBodyLargerThan64KiB() {
        client.post()
                .uri("/api/stream/measure")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .bodyValue(new byte[65_537])
                .exchange()
                .expectStatus().isEqualTo(413);
    }

    @Test
    void ndjsonCanBeReadIncrementally() {
        List<StreamController.StreamItem> data =
                client.get()
                        .uri("/api/stream/numbers")
                        .accept(MediaType.APPLICATION_NDJSON)
                        .exchange()
                        .expectStatus().isOk()
                        .expectHeader().contentTypeCompatibleWith(
                            MediaType.APPLICATION_NDJSON)
                        .returnResult(StreamController.StreamItem.class)
                        .getResponseBody()
                        .take(3)
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertNotNull(data);
        assertEquals(3, data.size());
        assertEquals(1, data.get(0).sequence());
        assertEquals("item-3", data.get(2).label());
    }

    @Test
    void infiniteSseIsBoundedInTestWithTakeTwo() {
        List<ServerSentEvent<String>> data =
                client.get()
                        .uri("/api/stream/ticks")
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

        assertNotNull(data);
        assertEquals(2, data.size());
        assertEquals("tick", data.get(0).event());
        assertEquals("tick-0", data.get(0).data());
        assertEquals("tick-1", data.get(1).data());
    }
}
~~~

**Important points in the tests:**
- `@SpringBootTest(RANDOM_PORT)` and `WebTestClient.bindToServer` exercise a real embedded HTTP server rather than invoking Java methods directly.
- The 65,537-byte test exceeds 65,536 bytes. If a gateway or client connector handles early termination by closing the socket, the network layer can sometimes close before delivering an error body; configure and integration-test large production routes accordingly. In this demo with a small over-limit request, HTTP 413 is expected.
- `take(3)` is placed **on the test subscriber** to avoid unbounded collection; the server's `numbers` emits only 5 items anyway. This test does not prove production throughput or streaming flush through nginx.
- `take(2)` causes the subscriber to cancel SSE after 2 events, preventing `collectList()` from waiting on an infinite Flux.
- `.block(Duration.ofSeconds(5))` runs **only on the JUnit test thread**; never call `.block()` inside a Spring WebFlux handler/event loop.
- To prove true streaming rather than full-response buffering, add tests observing **arrival timing of each element** (e.g., `StepVerifier` in a client-side test), because finite `collectList()` in the assertion still holds a small list.

Run:
~~~bash
./mvnw test
~~~

Windows:
~~~powershell
.\mvnw.cmd test
~~~

Without a wrapper, run `mvn test` with an installed Maven. Do not extrapolate this demo test to claim memory measurements under 100,000 concurrent uploads; run separate stress tests.

## 14. Using curl to Observe Streaming and Size Limits

Start the server:

~~~bash
./mvnw spring-boot:run
~~~

### 14.1. Small Binary Request

~~~bash
printf 'abcd' > input.bin
curl -i --data-binary @input.bin   -H "Content-Type: application/octet-stream"   http://localhost:8080/api/stream/measure
~~~

Expected result:

~~~json
{"bytes":4}
~~~

Counts **bytes**, not Unicode characters. UTF-8 files with accented Vietnamese characters typically contain more bytes than visible characters.

### 14.2. NDJSON Streaming

~~~bash
curl -i -N   -H "Accept: application/x-ndjson"   http://localhost:8080/api/stream/numbers
~~~

Logically, the response body consists of lines:

~~~json
{"sequence":1,"label":"item-1"}
{"sequence":2,"label":"item-2"}
{"sequence":3,"label":"item-3"}
{"sequence":4,"label":"item-4"}
{"sequence":5,"label":"item-5"}
~~~

Inside the `json` code fence, the content above is **NDJSON made of multiple independent JSON objects**, not a single valid JSON document. `curl -N` disables stdout buffering, though reverse proxies may still buffer responses if misconfigured.

### 14.3. Infinite SSE

~~~bash
curl -N -H "Accept: text/event-stream"   http://localhost:8080/api/stream/ticks
~~~

Observe `event:tick`, `data:tick-0`, `data:tick-1`, ... per codec wire format. Press `Ctrl+C` to disconnect. Never leave terminals or automated tests holding infinite streams unnecessarily.

### 14.4. Upload Limit

Create a file >64 KiB and POST to observe 413:

~~~bash
python -c "open('big.bin','wb').write(b'x' * 65537)"
curl -i --data-binary @big.bin   -H "Content-Type: application/octet-stream"   http://localhost:8080/api/stream/measure
~~~

The Python one-liner only generates a 65,537-byte **test file**; it is unrelated to the Java runtime. Expected response is HTTP 413. Some connectors close the request body early when the server returns 413; distinguish curl's broken-pipe or connection-reset messages here from business-logic bugs.

Multiline commands using `\` are for Linux/macOS/Git Bash. On Windows PowerShell, use `curl.exe` on one line or PowerShell's backtick line continuation.

## 15. Large Streaming File Uploads: Different from the Byte-Counting Demo

When actually storing uploaded files, typically:
1. Authenticate and enforce quotas before opening storage.
2. Accept `FilePart` or `Flux<DataBuffer>` and stream reads/writes.
3. Enforce per-file total bytes, minimum upload rate/timeouts, and concurrent upload limits.
4. Write to a staging file/object with a server-generated storage key—never trust raw client filenames.
5. Write in a single pass; never `collectList` then `Files.write`.
6. Hash and scan MIME/malware per policy—**never rely on client-sent Content-Type/extensions**.
7. On quota/virus/IO/error/cancellation, clean up staging and publish only upon completion.
8. Handle backpressure between inbound HTTP and disk/object-storage writers; disk writes can block if using synchronous APIs/SDKs.
9. Enforce max total bytes at ingress, app, and storage; codec `maxInMemorySize` is **not enough**.
10. Have an idempotency/retry/resumable strategy for large files over unreliable networks.

### `DataBufferUtils.write` Requires Reading the Right Overload

`DataBufferUtils.write(source, Path, OpenOption...)` returns `Mono<Void>` in Spring Framework 6.x; overloads taking `OutputStream`/`WritableByteChannel` may return `Flux<DataBuffer>` and **do not auto-release** buffers. Never blindly copy-paste `doOnNext(DataBufferUtils.releaseConsumer())` onto overloads with different ownership semantics.

When using `FilePart.transferTo(Path)`, do not read `file.content()` once and then transfer again assuming repeatability. Choose single-pass streaming contracts and tests. Write success alone does not guarantee virus scanning passed or data was durably replicated.

## 16. Proxies, Networking, and "Server Is Streaming but Client Sees Nothing"

A WebFlux pipeline may emit items immediately while nginx/gateway/compression layers **buffer the entire response**. For NDJSON/SSE routes:
- Set the proper `Content-Type` (`application/x-ndjson`, `text/event-stream`, `application/octet-stream`).
- Verify proxy response buffering, HTTP/2 stream settings, compression buffering, and flushing.
- Set appropriate idle timeouts; for SSE, emit comment-only heartbeats.
- Use `curl -N`/browser Network Timing/packet captures to observe per-item arrival, not just final bytes.
- Never cache responses across wrong users/tenants.
- Set max header/body/request limits at ingress.
- Measure slow-reader conditions; client download speed can also be a bottleneck.

SSE can use comment lines `: keep-alive` to avoid prolonged silence. This is not a data size limit, and heartbeats add overhead at high client counts.

## 17. Timeouts, Cancellation, and Cleanup

### 17.1. Two Types of Timeouts to Distinguish

- **Total deadline**: the request/operation must not exceed a business duration, e.g., 30 seconds.
- **Idle/read timeout**: the client/upstream must not stay silent too long, even within the 30-second budget.

An intentionally long-lived live SSE stream lasting hours may **conflict with a 30-second total response timeout**, yet still needs heartbeat/idle detection and connection caps. Conversely, an upload that must finish in 60 seconds may need an absolute deadline alongside a minimum data rate.

### 17.2. Cancellation Is Not Magic

When a client disconnects, Reactor propagates cancellation upstream; cooperative operators and I/O implementations stop. However:
- Blocking work currently running on a worker may not stop immediately.
- A DB query/client SDK without cancellation support may keep holding its connection.
- A half-written file still requires staging cleanup.
- `doFinally` fires on complete/error/cancel per Reactor lifecycle, yet async cleanup needs explicit design; never fire unowned `subscribe()` inside the hook.
- Discarded/cancelled pooled buffers must be released at the right ownership boundaries.

### 17.3. Overload Must Be Handled Explicitly

When queues/connections/quotas fill up, return:
- **413 Payload Too Large** when size exceeds policy.
- **429 Too Many Requests** when a user/tenant exceeds rate or quota.
- **503 Service Unavailable** when the service/storage is temporarily overloaded.
- **408/504** per HTTP client/proxy timeout failure modes, after checking which layer raised the error.

Never hold requests in an unbounded queue just to "avoid dropping work". Admission control and retries with backoff are far safer once resources saturate.

## 18. Proper Testing and Performance Validation

### 18.1. Functional Cases

| Case | What to Verify |
| --- | --- |
| Raw body 0 bytes | Receipt 0 or clear error contract |
| Raw body exactly 64 KiB | Accepted at threshold |
| Raw body 64 KiB + 1 | 413 without loading everything into RAM |
| Multiple chunks of varying sizes | Accurate total bytes, no overflow |
| Client disconnects mid-upload | Server cancels and cleans up properly |
| Multiple NDJSON items | Received object-by-object without waiting for a full array |
| JSON object exceeding codec budget | `DataBufferLimitException` or contract error |
| Infinite SSE | `take(n)`/cancel in tests, never `collectList` on the full stream |
| Fast hot producer, slow client | Buffer/drop/overflow obeys policy |
| Proxy buffering enabled | Confirm delayed flushing behavior |
| Concurrency 1/100/1000 | Heap/direct memory/DB pools stay within budgets |
| Downstream error mid-stream | Cleanup and response error semantics |
| Multiple retries | Does not amplify load or create duplicate events/records |
| Per-tenant quota | Limit enforced even across many concurrent requests |

### 18.2. Benchmarks Must Measure Memory Properly

Never measure a 1 KiB response and conclude the service can handle 100 GiB transfers. You should:
1. Compare `bodyToMono(byte[].class)` against raw chunk streaming under the **same throughput and payload profile**.
2. Run sufficient load to measure RSS/direct memory/heap allocation, GC, and Netty pooled buffer usage.
3. Record succeeded/timed-out/413/429/503 requests and p95/p99 latency.
4. Test fast upstream, slow downstream, client disconnects, and proxy buffering.
5. Measure `boundedElastic` queues, `flatMap` concurrency, WebClient pool acquires, and DB lock contention.
6. Test overload intentionally in controlled environments—never run load attacks against live production.
7. Verify data correctness (full bytes, checksums, no duplicate/missing chunks), because high throughput with lost data is not success.

### 18.3. BlockHound, Java Flight Recorder, and Observability

In suitable tests, BlockHound can help catch blocking calls on Reactor non-blocking threads, though it does not prove the pipeline has no unbounded buffering. Java Flight Recorder, thread dumps, Netty leak detector, and direct-memory metrics help locate queues, allocations, and event-loop stalls. Check tool compatibility with your Java/Reactor versions before enabling.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking `Flux` automatically saves memory | Downstream operators can still aggregate | Audit `collect*`, `join`, caches, buffers |
| Using `collectList` on an infinite stream | Never completes, memory grows | `take(n)`, streaming format, bounded storage |
| Using `maxInMemorySize` to cap total file uploads | Files/streams can still exceed the limit | Total byte counter + ingress cap |
| Setting `maxInMemorySize=-1` on error | OOM/heap spikes | Stream properly or use bounded DTOs |
| Using `limitRate(20)` as 20 items/sec | Demand batching ignores wall clock | Time-based rate limiter |
| Using `take(100)` to cap bytes | A single item can be huge | Count actual byte sizes |
| Unbounded `onBackpressureBuffer` | Slow consumers grow queues endlessly | Bounded buffers, overflow policy |
| Dropping transaction events with latest/drop | Silent data loss | Durable log + retry/checkpoints |
| High `flatMap` concurrency indiscriminately | Pool/DB/upstream saturation | Explicit concurrency budgets |
| Forgetting to release directly consumed `DataBuffer` | Netty direct memory leak | try/finally, ownership, discard tests |
| Releasing before HTTP writer uses the buffer | Use-after-release/corrupt bytes | Writer owns buffer until finished |
| `DataBufferUtils.join` on entire large files | Buffers the whole body | Stream/write or join with small cap |
| `bodyToMono(byte[].class)` in a gateway | Buffers large responses | `bodyToFlux(DataBuffer.class)` + streaming relay |
| `Thread.sleep` to throttle uploads | Blocks the event loop | Non-blocking limiter/transport shaping |
| Checking only `Content-Length` | Chunked/actual body differs from header | Count actual bytes + ingress cap |
| No timeouts | Slowloris/hanging streams | Deadlines + read/idle timeouts |
| Codec budget set, unlimited requests | Total memory scales with concurrency | Admission/connection limits |
| Server streams, client waits until end | Proxy/HTTP client buffers | Flush, proper content type, `curl -N` |
| Calling `collectList` in test on infinite SSE | Test hangs | `take(n)` and timeouts |
| Running blocking MVC SDK in WebFlux event loop | Stalls many connections | Reactive driver or bounded offload |
| Not cleaning up partial files on cancel | Disk bloat and wrong quotas | Staging + cleanup, integration tests |
| Retrying infinitely on 503 | Amplifies load and queues | Bounded backoff/jitter |
| Measuring only RPS, ignoring p99/errors | Misreads unhealthy load | Successful RPS + SLO + resource metrics |

## 20. Review Questions

**1. Does `limitRate(10)` mean limiting to 10 items per second?**  
No. It splits upstream demand into batches without enforcing a wall-clock or bandwidth policy.

**2. Does `maxInMemorySize=256 KiB` automatically block every request over 256 KiB?**  
No. It applies to reader/decoder buffering. NDJSON can carry many small objects in a long stream, while raw `Flux<DataBuffer>` requires its own cumulative byte limit.

**3. Why is `collectList()` on an SSE `Flux.interval` a bug?**  
The Flux has no normal terminal completion, so the List can never emit and may accumulate forever.

**4. If you allow only 10 DataBuffers of 8 MiB each, is memory safe?**  
You cannot assume so: up to ~80 MiB of buffers could be held before overhead. Account for byte sizes.

**5. What does `DataBufferUtils.join(buffers, 65536)` do?**  
It merges/composes buffers within a 65,536-byte budget and errors if exceeded. This is still finite aggregation, not raw streaming.

**6. Why release the buffer in `finally`?**  
If code throws while checking size, the buffer still must be released. `finally` runs on both success and exception paths.

**7. In the demo, why use `Mono.defer`?**  
Each subscription gets its own counter rather than storing mutable shared state in the singleton controller.

**8. Is `Content-Length` enough to enforce quotas?**  
No. Chunked requests may omit the header, and headers are not the sole source of truth. Count actual received bytes.

**9. If WebFlux uses WebClient and calls `bodyToMono(byte[].class)`, is it still streaming?**  
Not in the sense of the consumer receiving chunks incrementally; it materializes a single byte array before emitting. Use a raw DataBuffer Flux or NDJSON Flux when appropriate.

**10. Why are 413 and 429 different?**  
413 means payload size exceeds limits; 429 means rate/quota exceeded. Define clear policies and test both.

**11. How do you test infinite SSE with WebTestClient?**  
Use `take(n)`/timeouts on the test subscription rather than calling `collectList` on the whole infinite stream.

**12. Do concurrency limits and byte limits replace each other?**  
No. A single request can be huge; conversely, thousands of small requests can add up to overload.

## 21. Implementation Checklist

1. Map the entire ingest/process/egress chain and locate every aggregation/buffer point.
2. Configure ingress max-body/timeout/rate controls and concurrent connection budgets.
3. Configure WebFlux `maxInMemorySize` for decoders, understanding it bounds objects/parts—not total request size.
4. Use raw `Flux<DataBuffer>` or `FilePart` appropriately to stream large bodies; count cumulative bytes and stop on overflow.
5. Release every DataBuffer directly consumed by app code; guard error/cancel/discard paths without double-releasing buffers owned by the HTTP writer.
6. Avoid `collectList`, `collectMap`, unbounded `join`, `cache`, and `replay` on unbounded streams; use bounded batches/records.
7. For NDJSON/SSE, return Flux directly and test streaming/cancellation/slow readers instead of awaiting full data.
8. Use `limitRate` for demand batching, explicit concurrency for `flatMap`, and rate limiters for requests/bytes per second—never conflate them.
9. Choose overflow/drop/backpressure policies by business rules: can events be lost or not?
10. Set WebClient codec/connection pool/timeout/response-byte policies and downstream storage quotas.
11. For file uploads, use staging/scanning/atomic publishing/cleanup; never trust raw filenames/paths or `Content-Length` blindly.
12. Verify reverse proxy buffering/flushing, ingress limits, load balancer idle timeouts, and HTTP/2 behavior.
13. Test 0 bytes, exact limit, limit+1, chunked uploads, client disconnects, concurrency, large objects, and streaming correctness.
14. Monitor heap + direct memory + temp disk + GC + queues + connection pools + p99/errors; tune limits based on real SLOs.

## Official References

- [Spring Framework 6.2 — WebFlux Reactive Core, Limits, and Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — Configuring HTTP Codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Framework 6.2 — WebClient Configuration: maxInMemorySize](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html)
- [Spring Framework 6.2 — DataBufferUtils API, join and release](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework 6.2 — WebFlux Return Types](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Project Reactor — Backpressure, limitRate and Prefetch](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html)
- [Project Reactor — Reactor Sinks and Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)
- [Project Reactor — Schedulers and blocking offloading](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Reactive Streams specification](https://www.reactive-streams.org/)
