# Codecs, HttpMessageReader, HttpMessageWriter, and Memory Limit Configuration in Spring WebFlux

## 1. Why can a reactive application still run out of memory?

Spring WebFlux uses reactive APIs and asynchronous I/O to process HTTP, yet **that does not mean every request/response is always streamed with zero memory bounds**. When receiving JSON, form data, multipart, SSE, or text, Spring still has to turn **HTTP body bytes** into Java objects. When returning responses, it must convert Java objects back into bytes. This work is handled by the **HTTP codecs** subsystem.

An API like:

```java
@PostMapping("/documents")
Mono<Result> upload(@RequestBody Mono<Document> input) {
    return input.map(this::process);
}
```

may have to **accumulate many bytes of a single JSON object** before the decoder can construct `Document`. If a client sends an object with a very long string value or deeply nested arrays, this process can put pressure on heap/direct memory even though the controller never calls `collectList()`. That is why the HTTP codecs subsystem enforces a **`maxInMemorySize`** limit and can throw `DataBufferLimitException`.

Questions covered in this article:

1. What is the difference between **`Encoder`/`Decoder`** and **`HttpMessageWriter`/`HttpMessageReader`**?
2. How are `@RequestBody Mono<T>`, `@RequestBody Flux<T>`, and `@ResponseBody Flux<T>` handled by codecs?
3. When does the limit apply to the **entire body** versus **a single record/delimiter/event**?
4. How do you properly configure `spring.http.codecs.max-in-memory-size` for **Spring Boot 3.5** and `ServerCodecConfigurer.defaultCodecs().maxInMemorySize(...)` for WebFlux?
5. How do you configure **WebClient** separately and distinguish inbound server from outbound client?
6. Why is a codec limit not a **max HTTP upload limit**, rate limit, total heap limit, or backpressure policy?
7. Why does multipart have separate limits for RAM, disk, and part count? When should you use `FilePart` vs `PartEvent`?
8. How do you test decoding, NDJSON streaming, `DataBufferLimitException`, and byte-buffer lifecycle rigorously?

**Scope:** Spring Framework **6.2.x**, Spring Boot **3.5.x**, Java **17+**, **WebFlux reactive stack**, and default Reactor Netty. Property names in Spring Boot 3.5 are taken from that release's actual metadata rather than mechanically copying older Boot examples. This article belongs to **WebFlux Infrastructure**.

## 2. Overview of request and response flow

```text
                  INBOUND HTTP REQUEST
HTTP/TCP bytes
    |
Reactor Netty / ServerHttpRequest
    |
Flux<DataBuffer>
    |
HttpMessageReader<T>
   + Decoder<T> when using a codec converting bytes -> object
    |
@RequestBody Mono<T> / Flux<T> or ServerRequest.bodyToMono(...)
    |
Handler / Service (validation + business)
    |
Flux<R> / Mono<R> / ResponseEntity<...>
    |
HttpMessageWriter<R>
   + Encoder<R> when using a codec converting object -> bytes
    |
Flux<DataBuffer>
    |
ServerHttpResponse -> Reactor Netty -> HTTP client
                  OUTBOUND HTTP RESPONSE
```

Important point: **`DataBuffer`** is an abstraction over a byte region, not necessarily a `byte[]` on the heap. With Reactor Netty, data may be backed by a Netty `ByteBuf` using pooled/direct memory. The codecs and writers/readers subsystem manages decode/encode operations, media types, charsets, hints, and buffer lifecycles.

- **Reader** handles the **inbound** HTTP request/response body of a component.
- **Writer** handles the **outbound** HTTP request/response body of a component.
- On the **server**, requests are read with readers and responses written with writers.
- On **WebClient**, outbound requests are written with writers and inbound responses read with readers.
- Roles swap according to read/write direction; **there is no "server-only" codec in principle**.
- HTTP codecs do not replace business validation, authorization, malware protection, total payload caps, or slow-connection management.

## 3. Comparing API layers

| Class/API | Typical Spring package | Role | HTTP-dependent? |
| --- | --- | --- | --- |
| `DataBuffer` | `org.springframework.core.io.buffer` | Represents bytes/chunks | No |
| `DataBufferFactory` | `org.springframework.core.io.buffer` | Creates/allocates DataBuffers | No |
| `DataBufferUtils` | `org.springframework.core.io.buffer` | Join, read, write, retain/release, stream helpers | No |
| `Decoder<T>` | `org.springframework.core.codec` | `Flux<DataBuffer>` → objects | Not necessarily |
| `Encoder<T>` | `org.springframework.core.codec` | Objects → `DataBuffer` | Not necessarily |
| `HttpMessageReader<T>` | `org.springframework.http.codec` | Reads HTTP bodies with headers, media types, hints | **Yes** |
| `HttpMessageWriter<T>` | `org.springframework.http.codec` | Writes HTTP bodies, handles HTTP output/message metadata | **Yes** |
| `DecoderHttpMessageReader<T>` | `org.springframework.http.codec` | Adapter wrapping a Decoder to read HTTP | Yes |
| `EncoderHttpMessageWriter<T>` | `org.springframework.http.codec` | Adapter wrapping an Encoder to write HTTP | Yes |
| `ServerCodecConfigurer` | `org.springframework.http.codec` | Configures readers/writers for WebFlux server | Yes |
| `ClientCodecConfigurer` | `org.springframework.http.codec` | Configures codecs for WebClient | Yes |
| `DataBufferLimitException` | `org.springframework.core.io.buffer` | Signals decoder/join exceeded accumulation limit | No |

Spring Framework describes `Encoder` and `Decoder` as low-level, HTTP-independent contracts; `HttpMessageReader` and `HttpMessageWriter` bring those contracts into the HTTP context. Specialized codecs such as **multipart, form data, and SSE** can be dedicated readers/writers rather than merely wrapped Jackson encoders.

### 3.1. Two fundamental conversions

**Reading JSON:**

```text
Content-Type: application/json
Body: {"id":7,"name":"An"}
                |
     Jackson2JsonDecoder
                |
             Item
```

**Writing JSON:**

```text
Item(id=7,name="An")
                |
     Jackson2JsonEncoder
                |
application/json response bytes
{"id":7,"name":"An"}
```

`Jackson2JsonDecoder` and `Jackson2JsonEncoder` follow different stream-processing rules depending on media type and Reactor publisher type. Do not describe WebFlux as "converting text to objects" while ignoring MediaType, DataBuffer lifecycle, validation, and limits.

## 4. HttpMessageReader: how are inbound bodies read?

In Spring WebFlux annotated controllers:

```java
@PostMapping("/items")
Mono<Item> create(@RequestBody Mono<Item> input) {
    return input;
}
```

`@RequestBody` uses an **`HttpMessageReader` matching** the body type and `Content-Type` to decode the request. For JSON, the reader typically wraps a Jackson decoder when Jackson is on the classpath.

### 4.1. Selecting a reader

Selection depends on:

- Target type: `Item`, `String`, `byte[]`, `DataBuffer`, `MultiValueMap`, `Part`, etc.
- `Content-Type` declared by the client and media types supported by the reader.
- Reactive wrapper/cardinality: `Mono<T>` or `Flux<T>`.
- Generic type information such as `List<Item>`, `Map<String,Object>`, `Flux<Item>`.
- Registered codecs and priority order.
- ObjectMapper/Kotlin/Jackson XML/Protobuf dependencies if needed.
- Decoding hints/charset/validation after deserialization.

**Do not trust Content-Type as proof of safe content.** The header is client-controlled; a JSON parser may reject malformed syntax, yet that does not mean the data obeys business rules.

### 4.2. `Mono<T>` may have to buffer content

```java
@PostMapping(path = "/echo", consumes = "application/json")
Mono<Echo> echo(@RequestBody Mono<Echo> request) {
    return request;
}
```

This is a **fragment** assuming record `Echo` exists. When a JSON object spans multiple network chunks, the decoder must accumulate enough tokens to construct the object. **The limit applies to bytes accumulated to decode one unit**, not just a single TCP chunk.

If a JSON object exceeds the limit (e.g., a field holding several MB of text), `DataBufferLimitException` can be thrown. Depending on the error-handling layer/exception resolver, the default status **should not be assumed to always be 413**. Configure and actually test your HTTP error contract.

### 4.3. `Flux<T>` supports streaming yet is not exempt from limits

```java
@PostMapping(
    path = "/items/stream",
    consumes = "application/x-ndjson")
Mono<Summary> summary(@RequestBody Flux<Item> items) {
    // Process per record...
    return items.reduce(...);
}
```

Illustrative fragment. With NDJSON, each line is one JSON value. The reader can decode record by record **without buffering the entire HTTP body**. However, a **single overly long line/record** can still exceed `maxInMemorySize` when the codec must buffer up to the delimiter or complete object.

A stream of **1 million lines × 1 KiB per line** can in principle be read incrementally even though the total request far exceeds 256 KiB. Yet if you call `collectList()` on the whole stream or `reduce` into an unboundedly growing structure, the heap can still OOM; codec limits do not bound data retained by the application itself.

### 4.4. Form bodies and multipart

For `application/x-www-form-urlencoded`, the framework typically has to parse all form fields into a structure, so buffering and corresponding limits apply. For multipart, the parser can spool file parts to disk and enforces separate limits. Do not view multipart as "just a big JSON request".

## 5. HttpMessageWriter: outgoing response bytes

`@ResponseBody` / `@RestController` return values are handled by WebFlux via `HttpMessageWriter`:

```java
@GetMapping(path = "/item", produces = "application/json")
Mono<Item> one() {
    return Mono.just(new Item(1, "demo"));
}
```

The Jackson encoder turns `Item` into JSON bytes, and HttpMessageWriter writes them to `ServerHttpResponse` via reactive buffers.

### 5.1. Flux and media type determine behavior

```java
@GetMapping(path = "/items", produces = "application/json")
Flux<Item> items() {
    return Flux.range(1, 3)
            .map(i -> new Item(i, "item-" + i));
}
```

With `application/json`, multiple values are normally rendered as a **JSON array**:

```json
[
  {"id":1,"name":"item-1"},
  {"id":2,"name":"item-2"},
  {"id":3,"name":"item-3"}
]
```

Whereas `application/x-ndjson` renders each JSON object per line:

```text
{"id":1,"name":"item-1"}
{"id":2,"name":"item-2"}
{"id":3,"name":"item-3"}
```

And `text/event-stream` uses SSE framing:

```text
event: update
data: {"id":1,"name":"item-1"}

event: update
data: {"id":2,"name":"item-2"}

```

**Do not assume** every `onNext` immediately creates one HTTP packet. Encoders/writers, buffering/flush policies, proxies, HTTP/2 DATA frames, and clients all affect when data arrives. `Flux<T>` is just a reactive source; HTTP output semantics also depend on `Content-Type`.

### 5.2. Writers and custom serialization

When you want to rename JSON fields or format timestamps, prefer configuring **Jackson ObjectMapper** / DTO annotations in standard Boot style. Do not write a custom `HttpMessageWriter` just to rename fields or truncate strings.

When you have a **custom media type** like `application/vnd.mycompany.binary`, consider writing a dedicated `Encoder`/`Decoder` or reader/writer if there is genuinely a new wire protocol; you must honor backpressure, byte lifecycles, and validation. See section 17.

## 6. DataBuffer: byte storage and lifecycle

`DataBuffer` abstracts byte regions. On Reactor Netty, a `DataBuffer` can wrap a pooled Netty `ByteBuf` (direct memory). Direct memory **does not show up fully in heap usage**; an application can hit OOM/direct-memory pressure even while heap metrics look fine.

Common operations:

```java
DataBufferFactory factory = new DefaultDataBufferFactory();
DataBuffer buffer = factory.wrap(
        "hello".getBytes(StandardCharsets.UTF_8));
```

This is a fragment with Spring buffer imports + `StandardCharsets`, not a standalone file. `DefaultDataBufferFactory` in tests usually allocates unpooled buffers; Netty can use a pooled buffer factory.

### 6.1. Never retain DataBuffers arbitrarily

Wrong pattern:

```java
List<DataBuffer> all = new ArrayList<>();
return request.getBody()
        .doOnNext(all::add)
        .then();
```

This is an **anti-pattern**: retaining all buffers spikes RAM/direct memory, and pooled buffers have a release lifecycle. You must consume, relay, or release according to contract.

If your code **owns** a buffer and decides to discard it, call `DataBufferUtils.release(buffer)`. If using a buffer across an asynchronous handoff, you may need to `retain` appropriately; never double-release or use after release.

### 6.2. `DataBufferUtils.join` is aggregation — set a limit when needed

```java
Mono<DataBuffer> combined =
        DataBufferUtils.join(sourceBuffers, 8 * 1024);
```

When total bytes exceed 8192, Spring can emit `DataBufferLimitException`. On success, a combined buffer is returned; the **consumer** must release it properly if managing it manually. When `join` hits an error/cancellation, the API contract releases accumulated buffers.

Do not use the unbounded `DataBufferUtils.join(sourceBuffers)` overload on untrusted data or infinite streams unless limits are enforced elsewhere.

### 6.3. File streaming

For large files, **stream** from disk/object storage rather than calling `DataBufferUtils.join` on the entire file. For example, use `DataBufferUtils.read(Path, DataBufferFactory, bufferSize)` with `ServerHttpResponse.writeWith(...)` where appropriate, or `Resource`/`FilePart.transferTo(...)` depending on the use case.

Note: do not treat using `Flux<DataBuffer>` as an absolute safety guarantee. You still need limits on **total bytes, duration, concurrent streams, disk quota, permissions, and file validation**.

## 7. Why does DataBufferLimitException occur?

Class:

```java
import org.springframework.core.io.buffer.DataBufferLimitException;
```

This exception indicates accumulated bytes exceeded a configured cap in a decoder/reader/join operation. It can happen when:

- Decoding an oversized JSON request object.
- Calling `bodyToMono(String.class)`/`bodyToMono(byte[].class)` on a large body.
- Decoding form-data into a full map.
- JSON streaming: **one** record/token set is too large.
- SSE: an event payload/line exceeds the accumulation capacity.
- `DataBufferUtils.join(source, maxBytes)`.
- WebClient receives a large response and aggregates it into one object.
- XML/protobuf/custom decoders need to buffer a large unit, depending on implementation.

Typical error:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

Exact wording may vary by Spring version/decoder. Do not jump to concluding "the heap is full"; it is normally an **intentional guardrail rejecting an oversized unit before allocating more memory**.

### 7.1. Not all cases behave the same

| Processing path | What the limit usually applies to | Limits total HTTP body? |
| --- | --- | --- |
| JSON object → `Mono<Pojo>` | Bytes needed to decode one object | Not necessarily separate |
| Text → `Mono<String>` | Aggregated body string | Effectively the body the decoder reads |
| NDJSON → `Flux<Pojo>` | One record/JSON value | Does **not** bound the whole stream |
| SSE → `Flux<ServerSentEvent<T>>` | Content of one event/parser unit | Does **not** bound the whole connection |
| Multipart form field | Bytes of each non-file part | Does **not** replace max-parts |
| Multipart file part | In-memory threshold before spooling to disk | Does **not** replace disk usage quota |
| `Flux<DataBuffer>` | Raw chunks | Not auto-aggregated; app must control |
| `collectList()` in service | Heap for all items in the list | Codec limit does not govern this |
| `WebClient.bodyToMono(...)` | Client decode/aggregation | Not a server inbound limit |

**Distinguish unit-of-aggregation from total bytes** when deciding to raise from 256 KiB to 2 MiB. If each user sends 2 MiB and 200 requests run concurrently, buffered payloads alone can total hundreds of MB, excluding parser structures and network buffers.

## 8. Defaults and Spring Boot 3.5 configuration

### 8.1. The RIGHT property for Boot 3.5

In **Spring Boot 3.5**, the official codec configuration property is:

```properties
# src/main/resources/application.properties
spring.http.codecs.max-in-memory-size=8KB
```

This namespace is **`spring.http.codecs.*`** in Boot **3.5**. Spring Boot 3.5 metadata confirms `HttpCodecsProperties` with prefix `spring.http.codecs` (introduced in 3.5.0). Some **older Boot** guides use `spring.codec.max-in-memory-size`; do not copy old properties without checking your version and configuration metadata.

**Boot 3.5 default:** `spring.http.codecs.max-in-memory-size` is **unset** unless configured by the user. In that case, codecs use their own defaults; most buffering codecs default to around **256 KiB**. Do not assume every codec/multipart mode has the exact same default/behavior.

This property applies to the **auto-configured WebFlux server** and **Boot auto-configured WebClient instances**; it does not automatically alter every `WebClient.create()` constructed outside Boot's builder, does not apply to completely self-managed Spring Framework apps, and is not a "JVM-wide memory cap".

### 8.2. YAML equivalent

```yaml
spring:
  http:
    codecs:
      max-in-memory-size: 8KB
```

Pick one consistent place to declare it. With environment-based config, verify precedence and inspect the effective configuration in staging/production rather than only reading source files.

### 8.3. Why choose 8 KiB for the demo?

To easily exercise the guardrail with small JSON payloads:

- An echo JSON body of a few dozen bytes → passes.
- A JSON field of tens of KiB → can trigger the decoder limit.
- NDJSON with many small lines → can stream through even when the **total** body exceeds 8 KiB.
- A **single NDJSON line** over 8 KiB → can exceed the per-record limit.

**8 KiB is only a learning threshold**, not a production recommendation. For real profile or user-info uploads, a valid record may need to be larger; choose based on payload distributions, business validation, concurrent load, and overhead.

### 8.4. A property alone is not enough to cap uploads

If you need to cap the **total HTTP request** at 1 MiB, a 1 MiB codec max-in-memory-size does not guarantee that. A `Flux<DataBuffer>` or disk-spooled multipart file can exceed that total size while the codec streams along normally. Combine proxy/gateway max request size, server/container controls, and application-layer byte counting.

## 9. Configuring ServerCodecConfigurer directly

Not using Boot autoconfiguration or need custom codec behavior? Spring WebFlux provides `WebFluxConfigurer`:

```java
package demo.codec;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
class CodecConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(512 * 1024);
    }
}
```

**This standalone class is valid when placed in a WebFlux app in the same package.** `ServerCodecConfigurer` provides default readers/writers and ways to add, replace, or customize codecs. `WebFluxConfigurer#configureHttpMessageCodecs` is called by WebFlux for both annotated controllers and functional endpoints.

**Do not blindly add `@EnableWebFlux` to a Spring Boot app just to change limits.** In Boot, `@EnableWebFlux` can replace/disable Boot WebFlux auto-configuration in unintended ways; implement `WebFluxConfigurer` without adding that annotation when you want to preserve Boot defaults.

### 9.1. Property vs Java config

- **Properties** fit best when setting a global Boot default.
- **`WebFluxConfigurer`** fits best when controlling codec setup programmatically in the app architecture.
- If both a property and a different Java override are set, precedence depends on auto-config/customization ordering; **do not guess the effective value**. Pick one source of truth and test payloads at the boundary.
- Custom codecs may have their own limits and ignore default settings automatically.
- For **WebClient**, configure codecs on the client builder separately if not using Boot-configured `WebClient.Builder` or if needing a different limit.

### 9.2. Server side does not use Servlet `HttpMessageConverter`

Spring MVC Servlet uses `HttpMessageConverter`. **Spring WebFlux uses `HttpMessageReader`/`HttpMessageWriter` with reactive codecs.** Similar class names, different contracts and stacks. Never copy MVC's `configureMessageConverters`/`extendMessageConverters` to configure WebFlux reactive codecs.

## 10. WebClient: HTTP clients also have codec memory limits

`WebClient` writes requests and reads responses via `ClientCodecConfigurer`. When reading large JSON responses:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.org")
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024))
        .build();
```

This is a **fragment** requiring import `org.springframework.web.reactive.function.client.WebClient`. The limit above applies to **this client instance's** codecs and does not change the inbound server `ServerCodecConfigurer`.

To preserve Boot customizations:

```java
@Service
class PartnerClient {
    private final WebClient http;

    PartnerClient(WebClient.Builder builder) {
        this.http = builder
                .baseUrl("https://partner.example")
                .codecs(c -> c.defaultCodecs()
                        .maxInMemorySize(512 * 1024))
                .build();
    }
}
```

This is a fragment requiring `@Service` and WebClient imports; partner hostname is illustrative. In Boot, injecting `WebClient.Builder` inherits auto-configured customizations; `WebClient.create()` **does not necessarily** include them. When mutating the builder, verify which limit takes effect last.

### 10.1. bodyToMono and bodyToFlux

```java
Mono<List<Item>> all = client.get()
        .uri("/items")
        .retrieve()
        .bodyToMono(new ParameterizedTypeReference<List<Item>>() {});
```

This form typically has to decode **one JSON array** into `List<Item>`; if the body/array is very large, it can hit codec limits or high heap usage.

```java
Flux<Item> stream = client.get()
        .uri("/items.ndjson")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(Item.class);
```

With NDJSON, each record can be decoded individually, reducing the need to aggregate the entire response. However, `stream.collectList()` would still gather every item on the application heap. **A streaming codec cannot fix a consumer that collects all data.**

### 10.2. Client limits do not automatically sync with server limits

For example, an origin server allows JSON objects up to 1 MiB while the WebClient consumer keeps the ~256 KiB default → the client can throw `DataBufferLimitException` even though the server returned HTTP 200. Read stack traces/metrics to identify **whether the error occurred in the client decoder or server decoder**.

Do not raise the client limit to 100 MiB just to "fix the error" without asking why the response is so large. Consider pagination/NDJSON/streaming endpoints, array size limits, and controlling aggregation in services.

## 11. Multipart: RAM limits differ from disk and part-count limits

Multipart commonly appears in image, CSV, video upload APIs or multi-field forms. Spring WebFlux provides parsers and `FilePart`/`Part`/`PartEvent`; their specialized limits differ from the global HTTP codec memory setting.

**Spring Boot 3.5** documents these properties:

```properties
# Policy example only, must be tuned per product:
spring.webflux.multipart.max-in-memory-size=64KB
spring.webflux.multipart.max-disk-usage-per-part=10MB
spring.webflux.multipart.max-parts=8
spring.webflux.multipart.max-headers-size=10KB
```

Meaning:

| Property | Scope |
| --- | --- |
| `spring.webflux.multipart.max-in-memory-size` | Threshold for holding non-file parts in RAM; for file parts, can determine when to spool to disk |
| `spring.webflux.multipart.max-disk-usage-per-part` | Maximum disk space per file part written to disk |
| `spring.webflux.multipart.max-parts` | Total number of parts per request |
| `spring.webflux.multipart.max-headers-size` | Memory allowed for headers of a single part |
| `spring.webflux.multipart.file-storage-directory` | Directory for file parts spooled to disk by the parser |
| `spring.webflux.multipart.headers-charset` | Charset used to decode part headers |

Notable Boot 3.5 defaults: `max-in-memory-size` is typically **256KB**; `max-disk-usage-per-part` and `max-parts` default to **-1** (unlimited), so you must decide proper production policies. Streaming multipart via `PartEvent` can behave differently in some cases from parsers using aggregated `Part`; do not apply all properties assuming identical enforcement.

**This is neither malware protection nor authorization.** The multipart parser only parses structure; the application still needs format allowlists, content inspection, quotas/rate limits, isolated storage permissions, scanning/CDR if required, auth, and cleanup.

### 11.1. `FilePart.transferTo(...)`

A reactive controller can accept a file part and transfer it to a server-generated path:

```java
@PostMapping(path = "/files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> save(@RequestPart("file") FilePart file) {
    Path safeDestination = ...; // Server-generated & private.
    return file.transferTo(safeDestination);
}
```

**This is a fragment**, not a standalone runnable method: `safeDestination` must be generated in a service with proper permissions, quotas, and collision/cleanup policies. Never use `file.filename()` as a path; it is client-controlled. `FilePart.transferTo` returns `Mono<Void>`; to let WebFlux subscribe, **return the Mono** instead of calling `subscribe()` inside the controller.

### 11.2. `PartEvent` for streaming multipart per part

Spring WebFlux 6.2 supports `@RequestBody Flux<PartEvent>`. Each part can emit multiple events; `PartEvent.isLast()` marks the final event of a part. One structuring pattern:

```java
Flux<PartEvent> events = ...;

Flux<Flux<PartEvent>> byPart =
        events.windowUntil(PartEvent::isLast);
```

This is a fragment; each inner flux must be **consumed, relayed, or released** completely, especially when `DataBuffer`s hold pooled memory. When processing file content manually with `PartEvent.content()`, maintain an ownership contract: when discarding content, release the buffer; when forwarding downstream, avoid double-release.

**Do not equate `PartEvent` with `Flux<FilePart>`**. PartEvent streams data as events, whereas `FilePart` is normally an abstraction for a parser-managed part that may spool to disk.

## 12. Configuration does not replace total HTTP request caps

Suppose an API accepts:

```http
POST /api/items.ndjson HTTP/1.1
Content-Type: application/x-ndjson

{"id":1,"name":"A"}
{"id":2,"name":"B"}
...
```

If each line is small and the decoder emits objects line by line, a **2 GB total request** can still pass through an 8KB per-item codec limit as long as other layers permit it. That may be unsafe for system resources.

To enforce a 1 MiB total cap, you need:

1. Gateway/load balancer policies for request body size and connection limits.
2. Compatible HTTP server settings on Reactor Netty / underlying server.
3. **Per-request byte counting** in the stream when needed, with cancellation/cleanup when exceeded.
4. Application quotas per user/tenant, plus multipart total-size/file-count limits.
5. Timeouts/slow-upload defenses, concurrency limits, and disk quotas.
6. No infinite streams or unboundedly buffered items.

### 12.1. Limiting byte counts manually in Flux<DataBuffer>

Sketch fragment capping total inbound bytes:

```java
AtomicLong total = new AtomicLong();

Flux<DataBuffer> limited = request.getBody()
        .handle((buffer, sink) -> {
            long length = buffer.readableByteCount();
            long now = total.addAndGet(length);
            if (now > MAX_TOTAL_BYTES) {
                DataBufferUtils.release(buffer);
                sink.error(new PayloadTooLargeException());
            } else {
                sink.next(buffer);
            }
        });
```

This **is only an illustrative fragment**: `request`, `MAX_TOTAL_BYTES`, `PayloadTooLargeException`, imports, buffer ownership, and cancel/error handling must be properly defined in a real app. Use `AtomicLong` to handle accumulation and overflow per policy (cap practical limits to avoid long overflow), and never reuse state across requests. Once `sink.next(buffer)` is called, downstream takes ownership per contract; do not release the buffer afterward. In functional WebFlux, you can decorate `ServerHttpRequest`/WebFilter to count bytes, provided you preserve backpressure, release buffers cleanly, and avoid double-reading the body.

For most applications, a **proxy/gateway request body cap** is simpler and more reliable than writing a global filter that intercepts the body. When limits are needed post-parse, check both metadata and source streams.

## 13. Runnable Spring Boot 3.5 WebFlux / Java 17 demo

A minimal example isolating each codec behavior:

- `POST /api/echo` reads a single JSON object and returns a single JSON object.
- `GET /api/items.ndjson` emits three JSON records as NDJSON.
- `POST /api/summary` consumes NDJSON `Flux<Item>` and keeps only **count + sum of IDs**, without collecting all records.
- The demo codec memory limit is set to **8KB** to test boundaries.
- Unit tests verify `DataBufferUtils.join(maxByteCount)` directly and HTTP tests run via WebTestClient.

There is no DB, upload, auth, or production rate limiting; the code is **for studying codec behavior**, not for direct use as a public service.

### 13.1. Build dependencies

Create the project via Spring Initializr with **Spring Boot 3.5.x**, Java **17**, and dependency **Spring Reactive Web**. In a Gradle project with Boot plugin, repositories, BOM, and toolchain already configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` fragment**, not a standalone Gradle build file. Do not add `spring-boot-starter-web` to this demo: when both MVC and WebFlux are present, Boot 3.x normally defaults to the MVC web application type, defeating the goal.

### 13.2. Properties

Create `src/main/resources/application.properties`:

```properties
# Spring Boot 3.5 namespace; 8KB to easily observe decoder limit.
spring.http.codecs.max-in-memory-size=8KB

# Do not log raw HTTP request details by default:
spring.http.codecs.log-request-details=false
```

The log-request-details property is documented in Boot 3.5 metadata; `false` is the safe default. It does not mean gateways, APMs, or other code will automatically mask payloads if they log them.

### 13.3. Java application

Create **`src/main/java/demo/codec/CodecDemoApplication.java`**:

```java
package demo.codec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class CodecDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CodecDemoApplication.class, args);
    }
}

record EchoInput(String message) {}

record EchoOutput(String message, int length) {}

record Item(int id, String name) {}

record Summary(long count, long sumIds) {}

@RestController
@RequestMapping("/api")
class CodecDemoController {

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<EchoOutput> echo(@RequestBody Mono<EchoInput> incoming) {
        return incoming.map(body -> {
            if (body.message() == null
                    || body.message().isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "message must not be blank");
            }

            String text = body.message().strip();
            return new EchoOutput(text, text.length());
        });
    }

    @GetMapping(
            path = "/items.ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<Item> itemsNdjson() {
        return Flux.range(1, 3)
                .map(id -> new Item(id, "item-" + id));
    }

    @PostMapping(
            path = "/summary",
            consumes = MediaType.APPLICATION_NDJSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<Summary> summary(@RequestBody Flux<Item> items) {
        return items.reduce(
                new Summary(0L, 0L),
                (acc, item) -> new Summary(
                        acc.count() + 1,
                        acc.sumIds() + item.id()));
    }
}
```

The code uses Java 17 **records**, `Flux`/`Mono`, and WebFlux annotation controllers. Only `CodecDemoApplication` is public; the records and controller in the same package are component-scanned. Jackson from `starter-webflux` can encode/decode Java records.

#### Details to read closely in the code

- `echo(...)` uses **`Mono<EchoInput>`**: the reader constructs **one object**. The 8KB limit can reject oversized JSON requests during decoding before entering `map`.
- `itemsNdjson()` returns **`Flux<Item>`** with `produces=application/x-ndjson`: the writer encodes three objects with line framing.
- `summary(...)` uses `@RequestBody Flux<Item>`: the reader decodes each NDJSON record; `reduce` retains only **two numbers**, without building a growing list. Yet if a client sends infinite records, CPU/network still work indefinitely; **codec limits do not replace request size/time/count quotas**.
- `Summary.count` and `sumIds` can overflow `long` if the source is gigantic or IDs are untrusted. Production needs range checks/count caps/checked arithmetic if business accuracy demands it.
- Invalid JSON bodies usually trigger a reader error; valid JSON that fails business validation returns `400` as coded. Do not assume every `DataBufferLimitException` automatically turns into 413 without an explicit error policy.
- Never call `subscribe()` or `block()` in the controller; the WebFlux HTTP adapter subscribes and manages lifecycle automatically.

### 13.4. Running HTTP

```bash
./gradlew bootRun
```

Small request:

```bash
curl -i -X POST 'http://localhost:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"message":"Hello WebFlux"}'
```

Expected response:

```json
{"message":"Hello WebFlux","length":13}
```

`Hello` = 5, one space = 1, `WebFlux` = 7, so length = **13** per Java String length with all-ASCII characters in the example. Adding Unicode supplementary characters makes `String#length()` count **UTF-16 code units** rather than grapheme/user-perceived characters; the example intentionally uses ASCII for verifiable output.

GET NDJSON:

```bash
curl -N -i \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/items.ndjson'
```

Expected body:

```text
{"id":1,"name":"item-1"}
{"id":2,"name":"item-2"}
{"id":3,"name":"item-3"}
```

POST NDJSON:

```bash
printf '%s\n' \
  '{"id":1,"name":"A"}' \
  '{"id":2,"name":"B"}' \
  '{"id":3,"name":"C"}' \
  | curl -i -X POST 'http://localhost:8080/api/summary' \
      -H 'Content-Type: application/x-ndjson' \
      -H 'Accept: application/json' \
      --data-binary @-
```

Expected body:

```json
{"count":3,"sumIds":6}
```

The responses above are **expected outcomes given the exact project/baseline and inputs**, not captured output from a live execution.

### 13.5. Testing payloads exceeding the limit

With `spring.http.codecs.max-in-memory-size=8KB`, try sending a `message` longer than 10,000 ASCII characters inside a **single JSON object**:

```bash
# Example generating payload with Python in a terminal outside the app:
python -c "import json; print(json.dumps({'message':'A'*10000}))" \
  | curl -i -X POST 'http://localhost:8080/api/echo' \
      -H 'Content-Type: application/json' \
      --data-binary @-
```

Expect **decode limit exceeded**; exact HTTP status and error body depend on the version/config's exception translation. **Do not claim it defaults to 413**, and never log 10,000-byte payloads in environments with sensitive data.

With NDJSON, you can stream hundreds of 100-byte lines; total request exceeds 8KB while each record stays within the limit, subject to other caps. If a single line contains 20KB of text, the decoder can raise `DataBufferLimitException` for **that line**.

## 14. Verifiable tests: HTTP codecs and buffer limits

Create **`src/test/java/demo/codec/CodecDemoApplicationTests.java`**:

```java
package demo.codec;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CodecDemoApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void echoesSmallJsonWithJacksonCodec() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue("""
                    {"message":"Hello WebFlux"}
                    """)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello WebFlux")
                .jsonPath("$.length").isEqualTo(13);
    }

    @Test
    void emitsThreeNdjsonRecords() {
        Flux<Item> items = client.get()
                .uri("/api/items.ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_NDJSON)
                .returnResult(Item.class)
                .getResponseBody();

        StepVerifier.create(items)
                .expectNext(new Item(1, "item-1"))
                .expectNext(new Item(2, "item-2"))
                .expectNext(new Item(3, "item-3"))
                .verifyComplete();
    }

    @Test
    void limitedJoinRejectsExcessBytes() {
        DefaultDataBufferFactory factory =
                new DefaultDataBufferFactory();

        Flux<DataBuffer> tooLarge = Flux.just(
                factory.wrap(new byte[8193]));

        StepVerifier.create(
                DataBufferUtils.join(tooLarge, 8192))
                .expectError(DataBufferLimitException.class)
                .verify();
    }

    @Test
    void limitedJoinCanCombineAllowedBytes() {
        DefaultDataBufferFactory factory =
                new DefaultDataBufferFactory();

        Flux<DataBuffer> parts = Flux.just(
                factory.wrap("ab".getBytes(
                        StandardCharsets.UTF_8)),
                factory.wrap("cd".getBytes(
                        StandardCharsets.UTF_8)));

        StepVerifier.create(DataBufferUtils.join(parts, 8))
                .assertNext(buffer -> {
                    try {
                        byte[] bytes = new byte[
                                buffer.readableByteCount()];
                        buffer.read(bytes);
                        assertEquals(
                                "abcd",
                                new String(bytes,
                                        StandardCharsets.UTF_8));
                    } finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .verifyComplete();
    }
}
```

Run:

```bash
./gradlew test
```

The four tests are **designed to pass** on the Java17/Boot3.5/WebFlux baseline; **Gradle was not executed in this document**. HTTP tests use `RANDOM_PORT` to traverse the WebFlux HTTP stack rather than merely calling the controller directly. `limitedJoinRejectsExcessBytes` tests the **exact contract** of `DataBufferUtils.join(source,maxBytes)`: 8193-byte buffer > 8192 limit throws `DataBufferLimitException`; the success test reads all 4 bytes and releases the owned buffer.

**Test limitations:** the two `join` tests illustrate the **DataBufferUtils guard**, not that every Boot decoder limit is configured properly. To verify the 8KB property over HTTP, add an HTTP test sending a >8KB JSON object and asserting the decode error; to assert **413**, build and test the application's error-handling contract rather than relying on unverified defaults.

## 15. Designing HTTP status codes when buffer limits are exceeded

A public API should define clear semantics for oversized payloads:

| Scenario | Usually appropriate status | Notes |
| --- | --- | --- |
| JSON body exceeds API-allowed size | `413 Content Too Large` | May be blocked at proxy before reaching codec |
| Form/file part exceeds quota | `413 Content Too Large` | Disk/part count cases have separate exceptions |
| Invalid JSON syntax | `400 Bad Request` | Not a quota issue |
| Unsupported media type | `415 Unsupported Media Type` | Reader selection differs from byte limit |
| Unsatisfiable response `Accept` | `406 Not Acceptable` | Writer content negotiation |
| Business validation failure | `400`/`422` per contract | Not DataBufferLimitException |
| Missing authentication | `401 Unauthorized` | Not codec-related |
| Insufficient upload/download permissions | `403 Forbidden` | Not codec-related |
| Server heap actually exhausted | System outage, not just 413 | Do not rely on exception mappers to rescue OOM |

You can map `DataBufferLimitException` to 413 in an appropriately scoped `@RestControllerAdvice` / `WebExceptionHandler`. However, the error may be **wrapped** by a reader/decoder or occur **after the response is committed**, and may originate from an **outbound WebClient** or internal aggregation rather than an oversized client request. When handling it, classify the origin first to avoid turning internal buffering errors into HTTP 413 "client fault".

**Never print raw exception/toString bodies to clients**, especially if messages contain request content, parser details, or paths. Use stable error codes like `PAYLOAD_TOO_LARGE`, brief public messages, and privacy-safe technical logs.

## 16. Readers, writers, and content negotiation

HTTP codecs are selected by both **Java type** and **MediaType**:

- Inbound: `Content-Type` declares the body format for the reader to decode.
- Outbound: `Accept` declares the format the client wants, while `produces` and available writers decide the response type.
- `Content-Encoding` such as gzip/br is a separate layer; do not confuse it with media type `application/json`.
- Charset matters for text codecs, while JSON commonly uses UTF-8 per HTTP/JSON specifications.
- Generic type parameters matter: `List<Item>` and raw `List.class` carry different metadata, affecting element decoding.
- The classpath determines whether Jackson JSON, JAXB/XML, Protobuf, or optional codecs exist; missing dependencies cause unsupported media type/codec selection failures.
- HTTP codecs do not automatically guard against unsafe deserialization of business types if ObjectMapper is configured with unrestricted polymorphic typing. Enable only thoroughly vetted typing with up-to-date dependencies.

### 16.1. `Mono<List<T>>` differs from `Flux<T>`

```java
Mono<List<Item>> a = ...;
Flux<Item> b = ...;
```

If the source is a genuinely large list, `Mono<List<Item>>` has already aggregated onto the heap before the writer sees it. `Flux<Item>` can stay streaming, yet with `application/json` the writer may behave differently than with NDJSON/SSE. To control memory, evaluate **producer, operators, and codec**, not just the return type.

### 16.2. String, byte[], and Resource

`Mono<String>` or `Mono<byte[]>` usually represents a complete body; when decoding these from a network response, the codec may buffer bytes first. With raw `Flux<DataBuffer>` response streaming, memory usage can be lower, yet ownership/release risks are higher.

When a file resides on disk, **`Resource`** with HTTP range/conditional support is often better than writing `Mono<byte[]>` for large files. Never copy an entire file onto the heap just to serve a 200 download.

## 17. When is a custom codec genuinely needed?

Write a custom codec only for a **wire representation not reasonably handled by built-in codecs**, such as an internal binary event format with custom framing. If you just want to rename JSON fields, annotations or a Jackson module suffice.

A custom `Decoder<CustomPacket>` must address:

1. **`canDecode(ResolvableType, MimeType)`** matching the exact type/media type.
2. Decoding `Flux<DataBuffer>` in a **backpressure-aware** manner.
3. Clear framing: length-prefix, delimiter, or self-delimiting format.
4. Enforcing max frame/object bytes before allocating large structures.
5. Handling partial frames split across two DataBuffers.
6. Handling split UTF-8 characters if frames are text; never decode individual chunks as standalone strings and concatenate blindly.
7. Releasing consumed, discarded, and errored/canceled buffers without double-releasing.
8. Rejecting invalid/truncated/oversized messages cleanly.
9. Avoiding blocking reads or `block()` on the Netty event loop.
10. Testing byte splits at every offset and fuzzing malformed frames.
11. Registering readers/writers in an order that does not shadow built-in codecs for common media types.
12. Configuring limits/metrics directly on that codec rather than assuming `defaultCodecs.maxInMemorySize` automatically governs a custom codec without limit support.

### 17.1. Low-level vs HTTP-level adapters

The framework provides:

```java
DecoderHttpMessageReader<MyType> reader =
        new DecoderHttpMessageReader<>(myDecoder);

EncoderHttpMessageWriter<MyType> writer =
        new EncoderHttpMessageWriter<>(myEncoder);
```

This is a **fragment** assuming `myDecoder`/`myEncoder` implement valid interfaces/generics. Readers/writers understand HTTP headers/media types beyond the byte semantics of encoders/decoders. Register via `ServerCodecConfigurer.customCodecs()` using the appropriate API; check your exact version's Javadoc as custom codec registration overloads vary across release series.

Do not write a 20-line custom codec and claim it is production-safe. Binary framing, buffer release, infinite streams, byte limits, and malformed data require far deeper testing than sample snippets.

## 18. Byte memory vs heap vs direct memory vs disk

| Resource tier | Examples | Who must bound it |
| --- | --- | --- |
| Java heap | Decoded DTOs, Strings, Lists, cached objects | JVM sizing, business quotas, bounded operators |
| Direct/native memory | Netty ByteBufs/pooled DataBuffers | Netty allocator, buffer lifecycle, runtime metrics |
| Codec aggregate memory | JSON object/string/form parsing | Respective codec's `maxInMemorySize` |
| Operator queues | `flatMap` prefetch, `buffer`, `collectList` | Reactor policies, concurrency/backpressure |
| Multipart temporary disk | FilePart spool directory | WebFlux multipart limits, disk quotas, cleanup |
| Persistent storage | Object store, DB/file uploads | Business quotas/retention/permissions |
| Gateway buffers | NGINX/CDN buffering | Proxy request/response size and buffering policies |
| Client heap | `WebClient.bodyToMono`, browser JSON parse | Client codecs, application and browser limits |

An application with a 256KB codec limit can still consume 10GB of heap via `collectList()` or high request concurrency. Conversely, raising the codec limit to 10MB does not automatically increase heap by 10MB per request; actual usage depends on concurrency, payload sizes, decoders, and connection behavior.

**Strategy for choosing thresholds:**

- Measure P50/P95/P99 sizes per endpoint, plus a reasonable margin.
- Use DTO/schema validation and business size quotas.
- Separate streaming/bulk-import endpoints from small JSON endpoints.
- Budget concurrent requests × peak buffered bytes plus buffer/decoded object overhead.
- Check uploads for both RAM and disk; do not treat multipart limits as one number.
- Test slow clients and high concurrency before increasing global defaults.
- Test chaos/overflow/large nested JSON to observe failure modes.
- Monitor memory and status errors post-rollout; never tweak production properties blindly without understanding side effects.

## 19. Multipart, SSE, NDJSON, and backpressure: how they relate

Backpressure in Reactive Streams regulates **element-level demand**, while codec limits bound **bytes accumulated while decoding one unit**. The two mechanisms complement each other and **do not replace one another**.

Example:

```text
Client sends 100MB NDJSON
  consisting of 100,000 lines, 1KB each

Codec maxInMemorySize=8KB
  => each record can be decoded individually

Reactive downstream request(n)
  => guides item processing rate

Application collectList()
  => can still accumulate all 100MB+ records on the heap

Gateway maxBodySize=10MB
  => can reject request before reaching 100MB

Conclusion:
  Four distinct limits/mechanisms
```

With SSE, an event can span multiple `data:` lines and an event delimiter; the decoder may buffer until the event is complete. If an event is too large, the codec limit can trigger an error even if each network chunk is small.

With multipart, `FilePart` can spool data to disk once above the threshold, so total file sizes exceed `max-in-memory-size` without necessarily raising `DataBufferLimitException`. However, without caps on disk usage per part, part count, and concurrency, an attacker can still fill the disk.

## 20. Common errors and how to handle them

| Symptom | Likely cause | How to check |
| --- | --- | --- |
| `DataBufferLimitException: Exceeded limit...` on JSON POST | One object/aggregated body exceeded limit | Inspect actual byte size, Boot property, and decoder |
| Small JSON passes, JSON with very long field fails | Per-object buffer limit | Validate max field length; consider contracted 413 |
| WebClient fails when origin returns 200 | Client decoder limit smaller than response | Inspect `WebClient.Builder.codecs` |
| Property has no effect | Using an older Boot version's property name | For Boot 3.5 use `spring.http.codecs.max-in-memory-size` |
| Custom WebFlux codec still accepts huge payloads | Custom codec ignores default limit | Add explicit max frame/object size |
| App memory grows despite 8KB limit | `collectList`, operator buffers/queues, high concurrency | Heap profiler + Reactor/Netty metrics |
| Direct memory OOM | Unreleased pooled DataBuffers or Netty buffer pressure | Audit retain/release and allocator metrics |
| Multipart upload >256KB still succeeds | 256KB is RAM→disk threshold, not max upload | `spring.webflux.multipart.max-disk-usage-per-part` and total body policy |
| Disk full from multipart | Default max-disk-usage unbounded or broken cleanup | Configure quotas, spool directory, retention |
| 100MB NDJSON stream not blocked by 8KB | Each record is below the limit | Add total byte limit/timeout/count limit |
| One large NDJSON record fails mid-stream | Buffering between delimiters too large | Bound record sizes; client splits data properly |
| Large SSE event breaks client decoder | Event accumulation exceeds limit | Event size limits; chunk domain data sensibly |
| `HTTP 415` despite valid JSON | Content-Type unsupported by reader | Check media type and dependencies |
| `HTTP 406` when client asks for YAML | No writer for Accept type | Configure produces or add appropriate codec |
| Corrupted Unicode text | Wrong charset/decoder or split bytes | Use proper UTF-8 codecs |
| Empty request body produces Mono.empty | Client sent no body, handler lacks default | Define required body/validation contract |
| Test only asserts 500 on oversized | Unstable/unclear exception mapping | Test DataBufferLimitException directly and HTTP policy separately |
| Netty event loop blocked | Custom codec/handler calls `block()` or blocking I/O | Use non-blocking APIs or isolate on boundedElastic |
| Form details leaked in DEBUG | Raw request detail logging enabled | Keep `spring.http.codecs.log-request-details=false`, redact across tiers |

### Short debugging workflow

1. Confirm runtime is WebFlux (not turned into MVC by `starter-web`).
2. Check request `Content-Type`, expected Java type, and serialization format.
3. Check whether exception occurred on **server or WebClient**, before or after the controller.
4. Verify **Boot 3.5 namespace** properties and WebFluxConfigurer/ClientCodecConfigurer customizations.
5. Check whether aggregation happened in the codec or in `collectList/join/reduce` in services.
6. Check streaming media types like NDJSON/SSE and individual record sizes.
7. If multipart, check **separate** multipart settings and disk metrics.
8. For custom DataBuffer access, audit release/retain.
9. Reproduce with payloads near the threshold and load-test concurrent requests.
10. Return error responses with appropriate status, error code, and retry policy.

## 21. Boundary testing and what to measure in practice

A solid test suite should cover three tiers:

### A. Unit-level codec/buffer

- `DataBufferUtils.join` with byte counts just below/at/above the limit.
- `StepVerifier` asserting `DataBufferLimitException`.
- Test buffer release on normal completion/error/cancellation.
- For custom Decoders, test data split across every byte offset, malformed UTF-8/JSON, trailing bytes, and memory leaks.

### B. WebFlux HTTP integration

- `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` to traverse real Reactor Netty/codecs.
- Send small valid JSON and verify deserialization/serialization.
- Send an oversized JSON object and observe the real HTTP error path.
- Send NDJSON with many small records totaling over the limit, verifying every record arrives.
- Send an oversized single NDJSON record, verifying error/cancellation.
- Send Accept/Content-Type mismatches to verify 406/415 contracts.
- Test client codec limits when downstream WebClient reads large responses.

### C. Staging through gateway/production topology

- Payloads exceeding total ingress body limit; verify blocked before reaching the app.
- Multipart with many parts, exceeding disk usage quota, interrupted mid-upload.
- Pooled buffers/Netty direct memory/GC/concurrency under load.
- Test slow clients/senders, cancellation, and streaming flush latency.
- Reverse proxy buffering, compression, and HTTP/2→HTTP/1.1 translation.
- Verify raw bodies, passwords, or file bytes are never persisted in logs/APM.
- Observe HTTP 413/4xx/5xx and error recovery.

**Do not treat a pure StepVerifier test as proof** that Boot properties bound correctly, nor a passing HTTP test as proof that pooled buffers do not leak. Each tier validates a different hypothesis.

## 22. Security considerations for data passing through codecs

- JSON/XML parsers can face malformed inputs, deeply nested data, or resource-exhaustion payloads; keep dependencies updated and validate schema/depth/size.
- Never enable unrestricted polymorphic deserialization/default typing on client data.
- Never log raw HTTP bodies, Authorization headers, cookies, access tokens, multipart parts, or signed URLs.
- Setting `spring.http.codecs.log-request-details=false` only governs codec-level logs; gateway/Netty access logs/APM need separate redaction.
- When custom codecs return errors, never include stack traces/parser internals in responses.
- Upload format allowlists, anti-malware/quarantine/storage isolation are application responsibilities, not the codec's.
- For XML, verify XXE/entity expansion policies of the XML parser if XML codecs are enabled; never add unsafe parsers.
- Multipart filenames, part Content-Types, and JSON field values are all client-supplied; never use them as filesystem paths or trusted hosts.
- DataBuffer does not encrypt, sign, or verify integrity; use HTTPS, auth, and application-level integrity when required by contract.
- `DataBufferLimitException` helps prevent one kind of memory growth, yet does not defend against floods of many small requests; enforce ingress rate/concurrency limits.

## 23. Comparing across Spring Framework/Boot versions

| Generation | Notable differences |
| --- | --- |
| Spring Framework 5.x / Boot 2.x | WebFlux codecs exist; Boot codec settings namespace may differ from newer releases; check the exact reference |
| Spring Framework 6.2 / Boot 3.5 | Java 17+, Jakarta APIs; WebFlux `ServerCodecConfigurer`; Boot property **`spring.http.codecs.max-in-memory-size`** |
| Spring Framework 7.x / Boot 4.x | Core reader/writer/encoder/decoder concepts remain, though codec classes (especially JSON), Boot starters/modules, and config properties may change; check exact version migration docs |

**Do not blindly copy** `spring.codec.max-in-memory-size` from Boot 2 / early Boot 3 tutorials and assume it works on Boot 3.5. Also do not confuse Servlet MVC's `spring.servlet.multipart.*` with **`spring.webflux.multipart.*`** in the reactive stack.

When migrating WebFlux to MVC or vice versa, beyond annotations/controller code you must also update **HTTP serialization infrastructure, validation/error handling, multipart parsing, response streaming, and test setup**. Reactor `Flux` can appear in Spring MVC in certain return types, yet MVC servlet response writing does not share the exact contract of WebFlux reactive readers/writers.

## 24. Production operations checklist

- [ ] Verify the app truly runs WebFlux, not accidentally MVC due to overlapping dependencies.
- [ ] Define media type/DTO contracts for inbound and outbound traffic.
- [ ] Use the proper Spring Boot 3.5 property: `spring.http.codecs.max-in-memory-size`.
- [ ] Verify defaults (~256KiB for many codecs) and effective config via tests.
- [ ] Avoid raising global limits just to patch one endpoint designed with overly large bodies.
- [ ] Streaming endpoints use NDJSON/SSE/Flux properly rather than buffering everything.
- [ ] Enforce record/event size caps, total HTTP payload caps, timeouts, and quotas.
- [ ] Configure WebClient separately if needing limits different from the server; avoid `WebClient.create()` bypassing customizations.
- [ ] Configure multipart RAM/disk/part/header limits and storage cleanup.
- [ ] Never use `originalFilename` as a file path; enforce validation and scanning.
- [ ] Avoid holding unbounded raw buffers; release/relay pooled buffers properly.
- [ ] Eliminate unbounded `collectList/join` on untrusted data.
- [ ] Custom codecs honor frame limits, media types, and backpressure.
- [ ] Translate decoder/limit errors into stable HTTP contracts without exposing stack traces.
- [ ] Test payloads near/just over limits and under concurrent requests.
- [ ] Maintain both WebTestClient HTTP tests and dedicated buffer unit tests.
- [ ] Monitor heap, direct memory, Netty pending buffers, disk usage, and 413/5xx rates.
- [ ] Align gateway/proxy size limits, rate limits, and timeouts with policy.
- [ ] Never log raw HTTP headers/form data/PII unless explicitly authorized.
- [ ] Review Spring/Boot migrations against dependency BOMs and property metadata.

## 25. Self-assessment exercises

1. Distinguish `Decoder<T>` and `HttpMessageReader<T>`. Why does the reader need HTTP metadata?
2. What does `HttpMessageWriter` do on the server, and what role does its counterpart play when WebClient sends a request?
3. Why can `@RequestBody Mono<byte[]>` exceed the limit when an HTTP request body is large, even if network chunks are small?
4. With NDJSON consisting of 10,000 records × 100 bytes, does an 8KiB codec limit cap the 1MB total?
5. An NDJSON record is 16KiB long while each TCP segment is only 1KiB. Why can `DataBufferLimitException` still happen?
6. Distinguish `spring.http.codecs.max-in-memory-size` (Boot 3.5) from properties in older Boot tutorials.
7. When a custom `WebFluxConfigurer` and a Boot property specify different values, how do you verify the effective limit?
8. Why might `WebClient.create()` miss auto-configured Boot customizations?
9. Why can a server return 200 with a 1MiB body while WebClient still fails in its 256KiB client-side decoder?
10. Why does `WebClient.bodyToFlux(Item.class)` usually enable streaming, yet `collectList()` can still cause OOM?
11. With multipart, why can a file exceed `max-in-memory-size` and still be saved by the parser?
12. Why are `maxDiskUsagePerPart`, `maxParts`, and gateway max request size three distinct limits?
13. When manually reading `Flux<DataBuffer>`, when is `DataBufferUtils.release` required? Why is double-release dangerous?
14. What must `DataBufferUtils.join(source, 8192)` do if the source has 8193 bytes? Test with StepVerifier.
15. Testing a successful `DataBufferUtils.join`: once you receive the combined buffer, who is responsible for releasing it if you consume it manually?
16. How do a `Flux<Item>` response with `application/json` and `application/x-ndjson` differ in framing?
17. After returning 200 + a few NDJSON lines, if the decoder/producer errors, can you change the HTTP status to 413?
18. When writing a custom codec for length-prefixed binary, how do you handle a frame split across multiple DataBuffers?
19. Why does `spring.http.codecs.log-request-details=false` not guarantee proxy logs contain no tokens?
20. Design a policy for a 1GB CSV import API where each record is small: total-size quota, disk storage, streaming decoder, auth, retries, cancellation, and validation.
21. Which metrics would you measure to distinguish codec aggregation pressure from a pooled Netty ByteBuf memory leak?
22. When server code calls `collectList()` after the decoder has produced individual objects, does codec `max-in-memory-size` protect that list's memory?
23. With large nested JSON arrays, how does raising the system-wide limit impact peak memory when 200 users upload concurrently?
24. When upgrading Boot 3.5 to Boot 4, why must you check exact codec classes, property metadata, and tests rather than copying snippets?

## 26. Official documentation

- [Spring Framework 6.2 — Reactive Core, Codecs and Limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): DataBuffer, HTTP codecs, memory limits, multipart, and sensitive logging.
- [Spring Framework 6.2 — WebFlux Config / HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): `WebFluxConfigurer#configureHttpMessageCodecs`, `ServerCodecConfigurer`.
- [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): `HttpMessageReader`, Mono/Flux request bodies.
- [Spring Framework 6.2 — @ResponseBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html): `HttpMessageWriter` and reactive responses.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.http.codecs.*` and `spring.webflux.multipart.*`.
- [Spring Boot 3.5 — HttpCodecsProperties Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/http/codec/HttpCodecsProperties.html): `@ConfigurationProperties("spring.http.codecs")`.
- [Spring Framework 6.2 — DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): `join`, `read`, `write`, and buffer lifecycle.
- [Spring Framework 6.2 — DataBufferLimitException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferLimitException.html): error when exceeding aggregation limits.
- [Spring Framework 6.2 — Multipart Content](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html): `FilePart`, `PartEvent`, and resource ownership.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html): `WebClient.Builder.codecs`.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): HTTP reactive integration testing.
- [Spring Framework — HTTP Codecs API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/ServerCodecConfigurer.html): default codecs/custom codecs.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): signal/exception tests.
