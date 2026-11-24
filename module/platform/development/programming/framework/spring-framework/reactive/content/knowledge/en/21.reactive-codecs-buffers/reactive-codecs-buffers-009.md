# Avoiding Full Buffering of Large Bodies When Chunked Processing Is Possible in Spring WebFlux

## 1. The Problem: Reading an Entire Request into RAM Defeats Streaming

An endpoint receiving a 2 GB file or millions of records should not default to reading the entire request into a single Java object before processing. The following approaches typically aggregate data into memory:

```java
Mono<byte[]> body = request.bodyToMono(byte[].class);
Mono<String> text = request.bodyToMono(String.class);
Mono<List<Event>> events = request.bodyToFlux(Event.class).collectList();
```

These can fit small, clearly bounded payloads. For large bodies, they create memory pressure proportional to payload size and concurrent requests.

For example, if 20 concurrent requests buffer a 100 MB body, the bodies alone could require roughly 2 GB of memory, before counting objects, intermediate buffers, decoding copies, caches, and JVM overhead. As concurrent requests grow, the application can suffer long GC pauses, `OutOfMemoryError`, increased latency, or OS termination.

Spring WebFlux allows reading and writing bodies as `Mono`/`Flux`. Instead of waiting for the entire body to arrive, the application can process each element or `DataBuffer` and pass results along the reactive pipeline.

**The goal is not zero memory usage.** The goal is keeping memory held in RAM bounded rather than scaling with total body size.

## 2. Streaming Mindset: Process One Chunk, Then Request the Next

Data flow can be visualized as follows:

```text
HTTP request body
      |
      v
HttpMessageReader / Decoder
      |
      | decode element by element
      v
Flux<Event>
      |
      | validate one element
      v
process / save data
      |
      | complete current element
      v
request next element by demand
      |
      v
Mono<Summary>
```

Reactive Streams provides **backpressure**. The Subscriber signals how many elements it is ready to receive; the Publisher should not emit endlessly regardless of demand. Reactor operators such as `concatMap`, `flatMap` with bounded concurrency, and `limitRate` help control processing pace.

Example:

```java
Flux<Event> events = request.bodyToFlux(Event.class);

return events
        .concatMap(event -> eventService.save(event))
        .then();
```

Each event is forwarded to the service sequentially. The pipeline does not need to hold the entire list of events in a `List`.

If you need to return the number of processed records, you can maintain a small counter:

```java
return events
        .concatMap(event -> eventService.save(event).thenReturn(1L))
        .reduce(0L, Long::sum);
```

Here `reduce` holds only a single `long` accumulator. It differs from `collectList()`, which holds every element until the source completes.

## 3. Role of Codecs and HTTP Message Readers/Writers

In WebFlux, a body does not turn into an object automatically. The framework selects an `HttpMessageReader` and `Decoder` based on:

- Request `Content-Type`.
- The target type declared by the handler.
- Codecs on the classpath and current configuration.

On the response side, `HttpMessageWriter` and `Encoder` convert objects or Publishers into bytes.

```text
Request bytes
    |
    v
HttpMessageReader
    |
    v
Decoder
    |
    v
Mono<T> / Flux<T>
    |
    | business pipeline
    v
Mono<R> / Flux<R>
    |
    v
Encoder
    |
    v
HttpMessageWriter
    |
    v
Response bytes
```

Example:

```java
@PostMapping("/events")
Mono<Void> ingest(@RequestBody Flux<Event> events) {
    return events.concatMap(event -> eventService.save(event)).then();
}
```

Spring selects an appropriate decoder to turn the body into `Flux<Event>`. When returning `Flux<Event>` from a controller, the corresponding encoder writes the elements to the response.

`bodyToFlux` does not guarantee that every format shares the same streaming behavior. Choose a media type and codec that support splitting data into independent elements. For record-oriented data, NDJSON (`application/x-ndjson`) is often easier to stream than a single JSON document containing a huge array.

## 4. Choosing Body Types by Data Size and Structure

| Receiving type | Behavior | When appropriate |
|---|---|---|
| `@RequestBody Dto` or `Mono<Dto>` | Decodes one object | Small, bounded JSON |
| `@RequestBody byte[]` | Aggregates body into a byte array | Small payloads needing all bytes at once |
| `@RequestBody String` | Aggregates and decodes entire body to text | Small, bounded text |
| `@RequestBody List<Dto>` | Builds a collection holding all elements | Small lists of known size |
| `@RequestBody Flux<Dto>` | Emits and processes element by element | Record streams or JSON sequences |
| `@RequestBody Flux<DataBuffer>` | Receives raw byte buffers directly | Proxies, uploads/downloads, or custom byte handling |
| `FilePart` | Represents a multipart file | High-level multipart file uploads |
| `Flux<PartEvent>` | Receives each event/part in multipart | Large multipart needing streaming processing |

Do not pick `Flux` merely to make everything reactive. If a request carries a single small object, `Mono<Dto>` is usually clearer and sufficient. If the body can be very large or its element count is unknown ahead of time, avoid turning it into `byte[]`, `String`, or a full `List`.

## 5. Why Is NDJSON Useful for Record Streams?

A regular JSON document can contain an array:

```json
[
  {"id": 1, "value": "alpha"},
  {"id": 2, "value": "beta"},
  {"id": 3, "value": "gamma"}
]
```

NDJSON (Newline Delimited JSON) represents each object on one line:

```text
{"id":1,"value":"alpha"}
{"id":2,"value":"beta"}
{"id":3,"value":"gamma"}
```

Each line is an independent JSON object. The server can decode and process each object as data arrives without waiting for the entire document to finish.

Request:

```http
Content-Type: application/x-ndjson
```

Streaming responses can use the same media type. For Server-Sent Events, use `text/event-stream`.

Do not split each `DataBuffer` by newline manually using `new String(bufferBytes)`: a line can split across two buffers, or one buffer can contain multiple lines. Dedicated codecs and decoders handle framing and multi-byte characters properly.

## 6. `maxInMemorySize` Is a Buffer Limit, Not a Total Body Limit

Decoders and `HttpMessageReader` implementations may need to buffer part or all of the data to construct an object. Spring lets you cap buffered bytes via `maxInMemorySize`.

For default WebFlux codecs, the common default is **256 KiB**. If a codec must buffer beyond the limit, the request can emit `DataBufferLimitException`.

Important point: this limit does not mean an entire HTTP request is capped at 256 KiB.

- When a request is aggregated into one `byte[]`, `String`, or single object, the limit applies to the data requiring aggregation.
- When a decoder streams multiple objects, the limit applies to the bytes buffered to split/decode **one object** in the stream.
- For multipart, the limit has separate meanings for form fields and file parts; files can spill to disk according to the configured threshold.
- Codec limits do not replace total request body limits at reverse proxies, gateways, or server connectors.

If an NDJSON request contains 10 million lines and each line is small, the total request can far exceed `maxInMemorySize` while still being processed as a stream. A single oversized line can still exceed the limit.

### 6.1. Server-Side Codec Configuration

Default codecs can be customized using `WebFluxConfigurer`:

```java
@Configuration
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(512 * 1024);
    }
}
```

This snippet raises the default codecs' buffer threshold to 512 KiB. Increase it only with a clear reason, such as a valid single object larger than the default.

In Spring Boot, use `WebFluxConfigurer` without adding `@EnableWebFlux` if you want to preserve Boot's WebFlux auto-configuration. If replacing codecs yourself, check other codecs and configure matching limits; custom decoders may need to enforce their own limits.

### 6.2. WebClient Codec Configuration

Clients also have buffer limits when encoding/decoding:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(512 * 1024)
        )
        .build();
```

Client and server configurations are two independent places. Increasing WebClient's limit does not automatically change the limit of the server receiving the request.

### 6.3. Do Not Raise Limits to Mask Design Flaws

If an endpoint calls:

```java
Mono<byte[]> body = request.bodyToMono(byte[].class);
```

raising `maxInMemorySize` to hundreds of MB only allows the application to aggregate larger payloads. It does not turn the code into streaming and does not protect the application against many concurrent requests.

Redesign to use `Flux<T>`, `Flux<DataBuffer>`, `FilePart`, or `PartEvent` when business logic permits incremental processing.

## 7. Processing `Flux<T>` Element by Element

### 7.1. `concatMap`: Sequential and Order-Preserving

```java
return request.bodyToFlux(Event.class)
        .concatMap(event -> eventService.save(event))
        .then(ServerResponse.accepted().build());
```

`concatMap` processes inner Publishers strictly sequentially. Suitable when:

- Record ordering matters.
- The service writes data sequentially.
- You want to bound active operations.
- Per-element resource management needs to stay simple.

If one event takes a long time, subsequent events must wait. This is an intentional trade-off to control concurrency.

### 7.2. `flatMap` with Bounded Concurrency

```java
return request.bodyToFlux(Event.class)
        .flatMap(event -> eventService.save(event), 8)
        .then();
```

This allows at most 8 active inner Publishers concurrently. It can increase throughput when operations are independent, though completion order may differ from input order.

Never use unbounded `flatMap` for millions of elements if downstream services cannot sustain the load. Pick concurrency according to database pool limits, external services, and processing capacity.

### 7.3. `limitRate` and Prefetch

```java
Flux<Event> controlled = events.limitRate(64);
```

`limitRate` tunes how Reactor requests data from upstream in demand batches. It is useful to avoid requesting too much at once, but it is not a cap on total element count or total body size.

An operator with a large prefetch, high `flatMap` concurrency, or large queues can still hold many elements simultaneously. Inspect the whole pipeline, not just a single operator.

### 7.4. `onBackpressureBuffer` Needs Bounds

```java
events.onBackpressureBuffer(
        256,
        dropped -> log.warn("Dropped event: {}", dropped)
);
```

This is a bounded buffer of 256 elements with an overflow callback when overloaded. Buffering does not eliminate load by itself; it trades upstream pressure for RAM retention. Choose an intentional overflow policy: error, drop, or durable storage. Avoid unbounded queues for large bodies.

## 8. Keep Accumulators Small, Avoid `collectList()`

These two approaches have vastly different memory costs.

Aggregating all elements:

```java
Mono<List<Event>> allEvents =
        request.bodyToFlux(Event.class).collectList();
```

Counting elements only:

```java
Mono<Long> count =
        request.bodyToFlux(Event.class)
                .count();
```

Or processing and counting simultaneously:

```java
Mono<Long> count = request.bodyToFlux(Event.class)
        .concatMap(event ->
                eventService.save(event).thenReturn(1L)
        )
        .reduce(0L, Long::sum);
```

`collectList()` must retain all objects until the stream completes. `count()` and `reduce` with a small accumulator only keep summary state. However, `reduce` can also cause issues if the accumulator is a `List`, `Map`, or `StringBuilder` that grows continuously.

Ask: does the accumulator grow with the total number of records? If yes, that is still a form of aggregation.

## 9. Reading and Writing Bytes with `DataBuffer`

`DataBuffer` is Spring's byte buffer abstraction. When working directly with request/response bytes, APIs typically return `Flux<DataBuffer>`.

Some servers such as Reactor Netty use pooled, reference-counted buffers. When the application consumes `DataBuffer` directly, it must ensure buffers are released promptly. Holding buffers too long or forgetting to release can raise native memory even when JVM heap does not grow correspondingly.

### 9.1. Reading a Buffer and Releasing

Example converting each buffer into a small byte array for processing:

```java
Flux<byte[]> chunks = request.bodyToFlux(DataBuffer.class)
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return bytes;
            } finally {
                DataBufferUtils.release(buffer);
            }
        });
```

This only creates one array per chunk. The next consumer must still process and discard each chunk upon completion; collecting all arrays into a list brings back the original problem.

Never release a buffer before the downstream component finishes reading it. When handing a buffer to a response writer or another API that owns it, follow that API's ownership contract.

### 9.2. When Is `retain` Needed?

`DataBufferUtils.retain(buffer)` increments the reference count if the buffer is pooled. Retain only when you must keep the buffer past a boundary where the current owner may release it, such as transferring ownership to another async task. After use completes, release the exact number of retained references.

Never call `retain` as a supposed cure for memory leaks. Retaining without releasing keeps buffers alive longer.

### 9.3. `doOnDiscard` for Dropped Buffers

Some operators may discard elements on cancellation, filtering, or early termination. For pipelines managing `DataBuffer` directly, cleanup for discarded items may be needed:

```java
Flux<DataBuffer> safe = source
        .filter(this::shouldKeep)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

This is an illustrative example. `doOnDiscard` only handles elements for operators that support the discard hook; it does not replace releasing buffers already pulled and used directly by a consumer.

### 9.4. Never Decode Each Buffer as an Independent String

A UTF-8 character can span a two-buffer boundary. A JSON line can be split across multiple chunks. Therefore:

```java
new String(bytes, StandardCharsets.UTF_8)
```

on each individual buffer is not a safe parser for arbitrary text streams.

Use `Decoder`/`HttpMessageReader` and `bodyToFlux(Dto.class)` whenever possible. If defining a custom byte protocol, use a stateful parser to hold incomplete data across chunks.

## 10. `DataBufferUtils.join`: Aggregate Only When Bounded

`DataBufferUtils.join(...)` combines a stream of buffers into a single `DataBuffer`. It is useful for small payloads that must be processed as one block, but unsuitable for large unbounded bodies.

Use the bounded overload:

```java
Mono<String> smallText = DataBufferUtils.join(body, 64 * 1024)
        .map(joined -> {
            try {
                byte[] bytes = new byte[joined.readableByteCount()];
                joined.read(bytes);
                return new String(bytes, StandardCharsets.UTF_8);
            } finally {
                DataBufferUtils.release(joined);
            }
        });
```

This example accepts at most 64 KiB for aggregation. Exceeding the limit emits `DataBufferLimitException`. `join` manages accumulated input buffers; the returned combined buffer must be released after the application finishes reading it.

Do not use unbounded `join` for large uploads or downloads. If you only need to write data to a file, stream buffers to the file instead of merging everything into one giant buffer.

## 11. Streaming File Uploads and Downloads

### 11.1. Downloading Files in Chunks

`DataBufferUtils.read(Path, DataBufferFactory, bufferSize, ...)` reads a file into a `Flux<DataBuffer>` with an application-chosen buffer size:

```java
Path file = Path.of("exports", "large-report.bin");

Flux<DataBuffer> body = DataBufferUtils.read(
        file,
        new DefaultDataBufferFactory(),
        64 * 1024
);

return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(body);
```

Each buffer is up to roughly 64 KiB per read configuration. `DataBufferUtils.read` closes the channel when the Flux completes or is cancelled. The response writer consumes buffers to send to the client; do not release buffers before the writer finishes reading.

This is illustrative code inside a controller method returning `ResponseEntity<Flux<DataBuffer>>`. File paths must be server-controlled; never use raw paths supplied by clients.

### 11.2. Writing a Buffer Stream to a File

`DataBufferUtils.write(Publisher<DataBuffer>, Path, OpenOption...)` accepts a buffer stream and returns `Mono<Void>` signaling completion or error:

```java
Mono<Void> saveUpload(Flux<DataBuffer> body, Path destination) {
    return DataBufferUtils.write(body, destination);
}
```

Writing only starts when the Publisher is subscribed to. Compose this Mono into the handler/controller and let WebFlux coordinate subscription. Never call `.subscribe()` separately inside a service.

Pick a server-managed destination directory, generate safe filenames, enforce quotas, and handle cleanup when requests are cancelled. Check Javadoc for your exact Spring version when combining low-level buffer APIs; never release or retain buffers by guesswork.

### 11.3. Using `FilePart` for High-Level Multipart Uploads

If chunk-by-chunk control is unnecessary, `FilePart` is a convenient abstraction:

```java
@PostMapping(
        path = "/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<ResponseEntity<String>> upload(@RequestPart("file") FilePart file) {
    Path destination = uploadDirectory.resolve(
            UUID.randomUUID().toString() + ".bin"
    );

    return file.transferTo(destination)
            .thenReturn(ResponseEntity.accepted().body("stored"));
}
```

Create `uploadDirectory` before running. Destination filenames are generated server-side via UUID; never use client filenames directly in paths. `transferTo` returns a Publisher so writing is integrated into the request lifecycle.

In the default multipart reader, file parts larger than the memory threshold can be spilled to temporary files. Configure appropriate memory limits, disk usage limits, part counts, and temp-file cleanup policies.

## 12. Large Multipart: `multipartData()` and `PartEvent`

`ServerRequest.multipartData()` or equivalent APIs can return `MultiValueMap<String, Part>`. This is convenient when accessing multiple parts by name, but the reader aggregates parts into a map. For requests with many parts or needing to process files as they arrive, use `PartEvent` to stream part by part.

Spring WebFlux supports:

```java
Flux<PartEvent> events = request.bodyToFlux(PartEvent.class);
```

A single part can emit multiple `PartEvent` instances. `isLast()` marks the final event of the current part. Example pattern processing part by part:

```java
return request.bodyToFlux(PartEvent.class)
        .windowUntil(PartEvent::isLast)
        .concatMap(partEvents ->
                partEvents.switchOnFirst((signal, samePart) -> {
                    if (!signal.hasValue()) {
                        return samePart.then();
                    }

                    PartEvent first = signal.get();

                    if (first instanceof FormPartEvent form) {
                        return handleFormField(form.value());
                    }

                    if (first instanceof FilePartEvent file) {
                        Path destination = uploadDirectory.resolve(
                                UUID.randomUUID().toString()
                        );

                        Flux<DataBuffer> content =
                                samePart.map(PartEvent::content);

                        return DataBufferUtils.write(
                                content, destination
                        );
                    }

                    return Mono.error(
                            new IllegalStateException("Unsupported part")
                    );
                })
        )
        .then();
```

This is a functional handler pattern requiring `ServerRequest`, `PartEvent`, `FormPartEvent`, `FilePartEvent`, `DataBuffer`, `DataBufferUtils`, and the application's `handleFormField`/`uploadDirectory`. `concatMap` preserves part order; file content is forwarded directly as a buffer stream for writing.

**All `PartEvent` content must be consumed, forwarded, or released.** Never skip a file part and move to the next part while the previous content remains unconsumed. If the client cancels or processing errors, clean up temporary files and created resources.

## 13. Multipart Limits and Disk Usage

Multipart involves several distinct limits:

- `maxInMemorySize`: memory limit for form fields or threshold for keeping file parts in RAM.
- `maxDiskUsagePerPart`: disk space limit per file part written to disk in readers supporting this property.
- `maxParts`: maximum number of parts in a single request.
- `maxHeadersSize`: memory limit allocated to each part's headers.
- Total request body limit: must be coordinated at the server connector, gateway, or reverse proxy.

`DefaultPartHttpMessageReader` and `PartEventHttpMessageReader` differ in configuration across Spring versions. With `PartEventHttpMessageReader`, Spring 6.1 versions support limits on form field memory, part size, part count, and headers. Check Javadoc for your running version before configuring.

Never set unlimited disk usage in environments accepting large uploads from untrusted users. Enforce total directory quotas, temp-file cleanup, timeouts, and concurrent request limits.

## 14. Response Streams Must Also Avoid Aggregation

Avoid building a large list before returning:

```java
Mono<List<Order>> allOrders = orderRepository.findAll()
        .collectList();
```

If clients can receive data element by element:

```java
@GetMapping(
        value = "/orders/export",
        produces = "application/x-ndjson"
)
Flux<OrderExportRow> export() {
    return orderRepository.findAll()
            .map(OrderExportRow::from);
}
```

With SSE:

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<ServerSentEvent<EventMessage>> stream() {
    return eventPublisher.map(event ->
            ServerSentEvent.builder(event).build()
    );
}
```

When streaming responses are long-lived, emit periodic data or appropriate heartbeats to detect client disconnects sooner. If the client disconnects, cancellation should propagate to upstream sources and downstream tasks.

Not every client consumes streams identically. A client might still buffer the entire body before displaying it. Choose media types and client APIs together; `application/x-ndjson` or SSE are generally better suited for incremental consumption.

## 15. WebClient: Do Not Buffer Large Responses Client-Side

Avoid:

```java
Mono<byte[]> file = webClient.get()
        .uri("/large-file")
        .retrieve()
        .bodyToMono(byte[].class);
```

Use object streaming:

```java
Flux<Event> events = webClient.get()
        .uri("/events")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .bodyToFlux(Event.class);
```

Or stream raw byte buffers when transferring files:

```java
Mono<Void> download = webClient.get()
        .uri("/large-file")
        .retrieve()
        .bodyToFlux(DataBuffer.class)
        .as(buffers -> DataBufferUtils.write(
                buffers,
                Path.of("downloads", "large-file.bin")
        ));
```

To send an object stream:

```java
Mono<Void> upload = webClient.post()
        .uri("/events")
        .contentType(MediaType.parseMediaType("application/x-ndjson"))
        .body(eventFlux, Event.class)
        .retrieve()
        .bodyToMono(Void.class);
```

`eventFlux` should be a genuine reactive source, such as a database stream or file parser; do not pre-build a huge `List` and wrap it in `Flux.fromIterable(list)`.

## 16. Blocking I/O and CPU-Heavy Operations

Streaming does not automatically turn a blocking operation into a non-blocking one. Processing each chunk with a blocking file/database API on an event-loop thread can stall other requests.

Prefer:

- Reactive drivers and non-blocking I/O APIs.
- `DataBufferUtils.read` or `write` where appropriate.
- Decoding with built-in codecs.
- Per-record processing with bounded concurrency.

If calling a blocking library is unavoidable, isolate the exact call:

```java
Mono<Result> result = Mono.fromCallable(
        () -> legacyBlockingService.process(event)
).subscribeOn(Schedulers.boundedElastic());
```

Do not move the entire pipeline onto `boundedElastic` out of habit. Isolate only the blocking part, and still keep concurrent tasks within controllable bounds.

For CPU-intensive work, benchmark under load and pick an appropriate scheduler. Increasing concurrency does not always raise throughput; it can overload CPU, heap, queues, and downstream systems.

## 17. Request Cancellation, Mid-Stream Errors, and Cleanup

A body stream can end in three ways: complete, error, or cancel. Cancellation happens when the client closes the connection, times out, the server stops, or the subscriber no longer needs data.

On cancel:

- Stop reading new data if upstream supports cancellation.
- Close files/channels and release owned buffers.
- Delete incomplete temporary files according to policy.
- Cancel downstream tasks that are no longer needed.
- Never let nested `subscribe()` calls create pipelines outliving the request.

On mid-stream errors, the response may have already sent part of the body. The server cannot recall bytes already sent. For exports/downloads, clients must recognize interrupted streams and retry using idempotent or cursor-based mechanisms.

For uploads with side effects, define the business commit point. If only part of a file was written before an error, delete the incomplete file or write to a staging path before renaming to the final file. Never expose files to other systems before the upload completes.

## 18. Complete Java 17+ Example with Spring Boot WebFlux

The example has two endpoints:

- `POST /stream/events`: accepts NDJSON, validates and processes each record sequentially, keeping only a counter.
- `GET /stream/demo`: emits 5 NDJSON records for clients to read line by line.

### Directory Structure

```text
webflux-streaming-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

### `pom.xml`

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
    <artifactId>webflux-streaming-demo</artifactId>
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

### `src/main/java/demo/Main.java`

```java
package demo;

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
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }
}

@RestController
@RequestMapping("/stream")
class StreamController {

    @PostMapping(
            path = "/events",
            consumes = "application/x-ndjson",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<IngestSummary> ingest(@RequestBody Flux<EventRecord> events) {
        return events
                .concatMap(this::accept, 1)
                .reduce(0L, Long::sum)
                .map(IngestSummary::new);
    }

    private Mono<Long> accept(EventRecord event) {
        if (event.id() <= 0
                || event.value() == null
                || event.value().isBlank()) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Each event needs a positive id and a non-empty value"
            ));
        }

        // Replace with repository.save(event) if using a reactive database.
        return Mono.just(1L);
    }

    @GetMapping(
            path = "/demo",
            produces = "application/x-ndjson"
    )
    Flux<EventRecord> demo() {
        return Flux.range(1, 5)
                .map(id -> new EventRecord(id, "event-" + id));
    }

    record EventRecord(long id, String value) {}

    record IngestSummary(long accepted) {}
}
```

Run from the project directory with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

### Testing Response Streaming

```bash
curl -N http://localhost:8080/stream/demo
```

Body is emitted line by line as NDJSON:

```text
{"id":1,"value":"event-1"}
{"id":2,"value":"event-2"}
{"id":3,"value":"event-3"}
{"id":4,"value":"event-4"}
{"id":5,"value":"event-5"}
```

### Sending an NDJSON Stream

Create file `events.ndjson`:

```text
{"id":1,"value":"alpha"}
{"id":2,"value":"beta"}
{"id":3,"value":"gamma"}
```

Send request:

```bash
curl -i -X POST http://localhost:8080/stream/events \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @events.ndjson
```

Response body:

```json
{"accepted":3}
```

**Explanation:**

1. `@RequestBody Flux<EventRecord>` lets the decoder emit each record individually.
2. `concatMap(..., 1)` processes sequentially and keeps prefetch small.
3. `accept` returns only a `Long` value after validating the record; real applications can replace this with `repository.save(event)`.
4. `reduce(0L, Long::sum)` maintains a counter, not a list of events.
5. The demo endpoint returns `Flux<EventRecord>` with NDJSON media type so clients read line by line.
6. There are no `.collectList()`, `byte[]`, or `.block()` calls in the request pipeline.

This is a demo program processing records in memory to illustrate streaming. In production use, replace `Mono.just(1L)` with reactive persistence or a task with bounded concurrency. The example does not simulate durable storage.

## 19. Testing with `WebTestClient`

Endpoints can be tested without opening a TCP port:

```java
WebTestClient client = WebTestClient
        .bindToController(new StreamController())
        .build();

client.post()
        .uri("/stream/events")
        .contentType(MediaType.parseMediaType("application/x-ndjson"))
        .body(
                Flux.just(
                        new StreamController.EventRecord(1, "alpha"),
                        new StreamController.EventRecord(2, "beta")
                ),
                StreamController.EventRecord.class
        )
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.accepted").isEqualTo(2);
```

This is an illustrative test snippet requiring `spring-test` (typically included via `spring-boot-starter-test`) and importing `WebTestClient`. If a record nested inside a controller is inaccessible from the test package, adjust visibility or move DTOs to separate files.

Additional tests to include:

- Many records and empty records.
- An invalid record mid-stream.
- A payload with one record exceeding `maxInMemorySize`.
- Client cancellation while the server is emitting data.
- Memory measurement with increasing record counts while individual record size remains steady.
- Large multipart files, disk limits, and cleanup on cancel.
- Ordering checks with `concatMap` and concurrency checks with `flatMap`.

## 20. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Using `bodyToMono(byte[].class)` for large files | Entire body may be held in RAM | Stream `Flux<DataBuffer>` or use `FilePart` |
| Using `collectList()` for millions of records | Heap grows with element count | Process record by record and keep accumulators small |
| Raising `maxInMemorySize` to hundreds of MB to silence errors | One request can occupy huge RAM | Switch to streaming; raise limits only for single objects that truly require it |
| Mistaking `maxInMemorySize` for total request limit | Misses upload and request body limits | Configure additional limits at server, gateway, and proxy |
| Using `multipartData()` for huge uploads without considering aggregation | Builds a map holding all part metadata/content abstractions | Use `PartEvent` when streaming part by part |
| Using unbounded `flatMap` | Increases concurrency and queues beyond downstream capacity | Use `concatMap` or bounded-concurrency `flatMap` |
| Using unbounded `onBackpressureBuffer()` | Buffer grows at producer speed | Use a bounded buffer and overflow policy |
| Calling `subscribe()` manually in controller/service | Pipeline detaches from request lifecycle | Return Publisher for WebFlux to coordinate |
| Forgetting to release manually consumed `DataBuffer` | Pooled native memory may leak | Release after reading, handle retain/discard per ownership |
| Releasing buffers before writer uses them | Response fails or data corrupts | Release only after owning consumer finishes |
| Converting each buffer directly to String | Can split mid UTF-8 character or record | Use codecs/stateful framing parsers |
| Reading the body twice | Bodies do not replay automatically | Decode once and pass objects through the pipeline |
| Using blocking file/database calls on event loop | Blocks many concurrent requests | Use reactive I/O or isolate blocking calls |
| Not handling cancellation | Temp files, channels, or tasks keep running | Bind cleanup to lifecycle/cancel |
| Using client filenames in paths | Risk of path traversal or file overwrites | Generate filenames server-side and confine to directory |
| Not bounding multipart disk usage/parts | Can exhaust disk space or create too many parts | Set quotas, max part size, maxParts, and cleanup |
| Thinking NDJSON automatically caps line sizes | One huge line still needs buffering to decode | Set object limits and validate record sizes |
| Returning a stream while client buffers everything | Client still consumes high RAM | Pick client APIs and media types supporting incremental reads |

## 21. Large-Body Endpoint Design Checklist

1. Determine whether the request is a small object, a finite list, or an unknown-size stream.
2. Choose `Mono<T>`, `Flux<T>`, `Flux<DataBuffer>`, `FilePart`, or `PartEvent` appropriately.
3. Use NDJSON/SSE or explicit framing when clients need incremental delivery.
4. Avoid unbounded `byte[]`, `String`, `collectList()`, and `DataBufferUtils.join()`.
5. Set `maxInMemorySize` to valid object size, not total file size.
6. Set total request, multipart size, disk usage, part count, and timeout limits.
7. Choose `concatMap` or bounded concurrency matching downstream capacity.
8. Keep accumulators small; avoid unbounded queues.
9. When handling `DataBuffer` directly, define owner, retain/release, and discard cleanup.
10. Never perform blocking I/O on event-loop threads.
11. Handle cancellation, mid-stream errors, and temporary files.
12. Test with payloads larger than normal data and monitor both heap and direct/native memory.
13. Check the client too: clients must stream instead of buffering responses in RAM.
14. Never log entire large bodies or sensitive data.

## 22. Self-Check Exercises

**Q1.** Why is `bodyToMono(byte[].class)` unsuitable for multi-GB uploads?

**Answer:** Because the application must allocate a byte array holding the entire body; memory scales with file size and concurrent requests.

**Q2.** What is the benefit of `bodyToFlux(Event.class)`?

**Answer:** The decoder can emit events as a stream so the pipeline processes element by element instead of building a List holding all data.

**Q3.** Is `maxInMemorySize` a total request body limit?

**Answer:** No. It limits data codecs must buffer; for streams, the limit can apply per object. Total body size requires separate limits at the server/gateway.

**Q4.** Why does NDJSON fit large record datasets?

**Answer:** Each line is an independent JSON object, enabling the decoder to split and emit records as data arrives.

**Q5.** How do `concatMap` and `flatMap` differ when processing streams?

**Answer:** `concatMap` processes sequentially and preserves order; `flatMap` allows concurrent processing, needs bounded concurrency, and does not guarantee completion order.

**Q6.** Does `reduce(0L, Long::sum)` collect the entire stream?

**Answer:** No. It keeps only a `long` counter; however, if an accumulator is an unboundedly growing List/Map/String, that is still aggregation.

**Q7.** When must `DataBufferUtils.release` be called?

**Answer:** When the application directly consumes and owns a pooled `DataBuffer`; release after use completes, never before a downstream consumer finishes.

**Q8.** Is `DataBufferUtils.join` suitable for a 10 GB file?

**Answer:** No. `join` aggregates buffers into one buffer; use only with small, explicit bounds.

**Q9.** Why might `multipartData()` be unsuitable for very large multipart requests?

**Answer:** This API builds a `MultiValueMap` holding parts. If you need to process each part as a stream, use `PartEvent`.

**Q10.** Can `PartEvent` content be skipped after reading the filename?

**Answer:** No. Each part's buffer content must be consumed, forwarded, or released to avoid memory leaks.

**Q11.** Why can unbounded `onBackpressureBuffer()` be dangerous?

**Answer:** When the producer outpaces the consumer, the queue keeps growing and retains data in RAM.

**Q12.** What should the server do if a client cancels a download mid-way?

**Answer:** Propagate cancellation, close channels/files, and clean up resources no longer needed.

## 23. Practical Rules

- Use `Mono<T>` for small objects and `Flux<T>` for multi-element streams.
- Choose NDJSON/SSE when incremental transfer is needed; avoid collecting into a huge JSON array unnecessarily.
- Treat `maxInMemorySize` as a codec buffer limit, not a total request limit.
- Use `concatMap` or bounded-concurrency `flatMap`; keep accumulators small.
- For files, prefer streaming `DataBuffer`, `FilePart`, or `PartEvent` over `byte[]`.
- Use `DataBufferUtils.join` only for small, bounded payloads.
- When handling `DataBuffer` directly, obey ownership and release promptly.
- Design cleanup for error/cancel and enforce memory, disk, and request-size limits.
- Test both server and client with large payloads and varying producer/consumer speeds.

**Key takeaway:** WebFlux can process large bodies incrementally thanks to `Flux`, codecs, and backpressure. Never aggregate an entire body into `byte[]`, `String`, or `List` when you can process record by record or buffer by buffer. Codec limits, concurrency, disk usage, and `DataBuffer` lifecycles must be designed together.

## 24. Official References

- [Spring Framework — Functional Endpoints: request body and PartEvent streaming](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — Reactive Core: codec limits, multipart, and DataBuffer](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework — WebFlux Config: HTTP message codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework 6.1.11 — DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework 6.1.11 — PartEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/codec/multipart/PartEvent.html)
- [Spring Framework 6.1.11 — DefaultPartHttpMessageReader Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html)
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — WebClient request body streaming](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html)
