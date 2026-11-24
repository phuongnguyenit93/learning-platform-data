# `maxInMemorySize` and `DataBufferLimitException` in Spring WebFlux

## 1. The Problem: Codecs Cannot Hold Data in Memory Indefinitely

Spring WebFlux receives and sends HTTP bodies as streams of `DataBuffer`. Codecs and `HttpMessageReader` implementations convert this byte stream into Java types such as `String`, `byte[]`, JSON DTOs, form data, or multipart. To construct a complete object, some readers must aggregate multiple buffers in memory. Without a limit, a single large request or many concurrent requests can cause the heap to grow rapidly.

Two concepts to grasp:

- **`maxInMemorySize`** is the byte limit that a codec/reader is allowed to hold when data must be buffered in memory.
- **`DataBufferLimitException`** is the exception indicating that the cumulative bytes in a buffer/aggregate operation exceeded the configured limit.

This is a codec memory-protection mechanism. It is neither the total upload size limit of an entire HTTP request nor an HTTP status code. The final status depends on where the exception occurs and how the application maps errors.

In Spring Framework 6.2, most default codecs have a 256 KB limit. The limit can be changed on the server side via `ServerCodecConfigurer`, on the client side via `WebClient.Builder`, or via Spring Boot configuration. For streaming, the limit typically applies to **each element/unit being aggregated**, not the total size of the entire stream. For multipart, the same property has distinct per-part semantics: limiting non-file parts and serving as the threshold before file parts are spilled to disk.

## 2. `DataBuffer`, Codecs, and Aggregation

### 2.1. What Is `DataBuffer`?

`DataBuffer` is Spring's abstraction for a byte region. It hides differences between underlying implementations, such as:

- Netty `ByteBuf`.
- Java NIO `ByteBuffer`.
- Buffers provided by other server connectors or I/O libraries.

An HTTP body usually arrives in multiple chunks. A 1 MB JSON document may be transported across dozens or hundreds of small `DataBuffer` instances; buffer boundaries do not necessarily align with JSON object boundaries, NDJSON lines, or SSE events.

Codecs read buffers and convert them into higher-level data:

```text
Network / HTTP body
        |
        v
Flux<DataBuffer>
        |
        v
Decoder / HttpMessageReader
        |
        +---- parse / aggregate / split
        |
        v
Mono<DTO> or Flux<DTO>
        |
        v
Controller / WebClient caller
```

`Encoder` performs the reverse direction: accepting objects and producing `DataBuffer` instances to write to the response/request body.

### 2.2. When Must Data Be Aggregated?

Certain target types require the reader to have sufficient data before emitting a result:

| Body reading approach | Common behavior |
|---|---|
| `@RequestBody byte[]` | Aggregates the body into a single byte array |
| `bodyToMono(String.class)` | Aggregates content into a single String |
| `bodyToMono(MyDto.class)` | Parses one JSON object into one DTO; the parser may buffer tokens/buffers for that object |
| `application/x-www-form-urlencoded` | Parses the body into a map of form fields |
| Multipart via `getMultipartData()` or `@RequestPart` | Parses and builds a parts structure for lookup by name |
| `DataBufferUtils.join(...)` | Explicitly combines multiple buffers into a single buffer |
| Delimiter-splitting readers | Holds data until a delimiter or a complete element is found |

These reading approaches can consume more memory than a pipeline that forwards elements one by one. Thus, reading a large JSON response with `bodyToMono(String.class)` may exceed the limit, whereas a stream of many small records read as `Flux<Record>` can be processed sequentially.

### 2.3. Aggregation and Streaming Examples

Aggregating the entire body:

```java
Mono<String> body = webClient.get()
        .uri("/export")
        .retrieve()
        .bodyToMono(String.class);
```

The reader must construct one complete String before emitting `Mono<String>`. If the body exceeds the decoder's threshold, reading may fail.

Reading record by record:

```java
Flux<LogEntry> entries = webClient.get()
        .uri("/logs")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .bodyToFlux(LogEntry.class);
```

With supported streaming formats, the Jackson decoder can emit each object once that object is complete. The application can process a record and continue receiving the next without building a `List` holding all results.

**Note:** `Flux<T>` by itself does not guarantee every part of processing is streaming. Calling `.collectList()`, `.collectMap()`, `.reduce(...)` to hold all results or switching to `bodyToMono(List.class)` can cause the application to aggregate data again. Inspect the entire pipeline, not just the controller's return type.

## 3. What Exactly Does `maxInMemorySize` Limit?

`maxInMemorySize` limits the number of bytes buffered when an input stream must be aggregated. These situations can include:

- Combining multiple `DataBuffer` instances into one buffer or one object.
- Decoding a `byte[]`, `ByteBuffer`, `Resource`, or `String`.
- Parsing a JSON object into a DTO.
- Splitting data by a delimiter, such as lines of text or an element in a stream.
- Aggregating the data payload of a single SSE event.

In streaming scenarios, the limit applies to the bytes associated with **one object/unit currently being constructed**, not the total bytes of all elements that pass through the stream.

Example with a 256 KB limit:

```text
Flux<LogEntry>
  record 1: 12 KB  -> OK
  record 2: 20 KB  -> OK
  record 3: 18 KB  -> OK
  ...
  entire stream total: 2 GB -> does not automatically violate just because total is 2 GB
```

However, if a single record requires buffering 400 KB, that record can exceed the limit:

```text
Flux<LogEntry>
  record 1: 12 KB  -> OK
  record 2: 400 KB -> DataBufferLimitException
  record 3: not processed normally after terminal error
```

This does not mean an infinite stream is unconditionally safe. A pipeline can still retain data via `cache`, `collectList`, unbounded queues, or custom operators. `maxInMemorySize` guards aggregation points managed by codecs/readers; it is not an application-wide heap limiter.

### Default Limit

In Spring Framework 6.2, most default codecs use a **256 KB** limit. Some decoders/readers have separate configurations; consult the specific codec's Javadoc for exact details. `CodecConfigurer.defaultCodecs().maxInMemorySize(...)` provides a common configuration point for default codecs.

The value is passed in bytes:

```java
configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
```

This is 2 MiB (2,097,152 bytes). Do not confuse decimal 2 MB with binary 2 MiB (powers of 1024) when calculating capacity.

## 4. What Is `DataBufferLimitException`?

`org.springframework.core.io.buffer.DataBufferLimitException` is a subclass of `IllegalStateException`. The exception indicates that the total bytes consumed from a `DataBuffer` stream exceeded the previously configured threshold.

It can occur when:

- `DataBufferUtils.join(...)` merges buffers.
- A codec retains and aggregates data during decoding.
- Jackson asynchronous parsing buffers tokens for a JSON object.
- An SSE reader collects lines into an event.
- A delimiter-splitting reader sees too much data before encountering a delimiter.

A common message:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

This is a buffering-limit error, not necessarily meaning the entire HTTP body is too large. For example, a 100 MB stream of many small JSON records can succeed; a single 400 KB JSON record can exceed a 256 KB threshold.

### 4.1. Example Triggering the Error with `DataBufferUtils.join`

`DataBufferUtils.join(publisher, maxByteCount)` is a useful API when an application genuinely needs to merge buffers and impose a dedicated cap on that operation:

```java
DataBufferFactory factory = new DefaultDataBufferFactory();

Flux<DataBuffer> input = Flux.just(
        factory.wrap(new byte[8]),
        factory.wrap(new byte[8])
);

Mono<DataBuffer> joined =
        DataBufferUtils.join(input, 12);
```

The two buffers contain 16 bytes in total, but the join operation is allowed to hold at most 12 bytes. Upon subscription, the publisher emits `DataBufferLimitException`.

Do not use unbounded `DataBufferUtils.join(input)` for bodies that can grow arbitrarily large. If the business goal is simply saving a file or forwarding content, use streaming APIs instead of merging the entire body.

### 4.2. `DataBufferLimitException` vs. `OutOfMemoryError`

| Characteristic | `DataBufferLimitException` | `OutOfMemoryError` |
|---|---|---|
| Cause | A buffer operation exceeded a configured limit | The JVM could not allocate required memory |
| Nature | Exception that can be handled in the reactive pipeline | Severe JVM Error |
| Predictable? | Yes, if limits and data sizes are controlled | Not necessarily |
| Handling | Adjust design/limits or return an appropriate error | Investigate memory pressure, leaks, heap sizing, and concurrency |

Codec limits reject an aggregation operation before it can consume unbounded memory. They do not replace monitoring heap, GC, concurrent requests, or other sources of object retention.

## 5. Server-Side Configuration with `ServerCodecConfigurer`

In Spring WebFlux, default codecs can be customized through `WebFluxConfigurer`.

```java
@Configuration
public class WebFluxCodecConfiguration
        implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }
}
```

This example sets a 2 MiB limit for server-side default codecs.

### 5.1. With Spring Boot

In a Spring Boot application, you can use configuration properties:

`application.properties`:

```properties
spring.codec.max-in-memory-size=2MB
```

Or YAML:

```yaml
spring:
  codec:
    max-in-memory-size: 2MB
```

This property applies to WebFlux server and WebClient instances auto-configured by Spring Boot. If you build a custom `WebClient` with your own builder or create a codec configurer outside auto-configuration, configure it directly on that builder/configurer.

When using Spring Boot, normally declare `WebFluxConfigurer` without adding `@EnableWebFlux`. `@EnableWebFlux` enables explicit WebFlux configuration mode and can discard Boot's auto-configuration customizations if not fully reconfigured.

### 5.2. Choosing Limits Based on Endpoint Needs

You do not need to raise all codecs to tens of MB just because one endpoint accepts large files. Determine:

- Which endpoint needs to aggregate a large object?
- Can it switch to `Flux<T>` or file streaming?
- What is the largest expected single record in bytes?
- How many requests might aggregate at peak concurrency?
- Are there body limits at the reverse proxy, API gateway, or HTTP server?
- Does the endpoint accept untrusted input from clients?

If only one endpoint requires a large JSON object, consider a dedicated design for that endpoint instead of widening the global limit for the entire API.

## 6. Client-Side Configuration with `WebClient`

`WebClient` also uses codecs to decode response bodies. Thus `DataBufferLimitException` can occur when the application calls another API and tries to read a large response into a single object/string.

Configuring a 2 MiB limit for default codecs of a `WebClient`:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(2 * 1024 * 1024))
        .build();
```

If the application uses a Spring Boot-injected `WebClient.Builder`, it can leverage `spring.codec.max-in-memory-size`. For self-constructed client builders, declaring `.codecs(...)` explicitly makes it clear what limit is enforced.

### 6.1. Choosing the Appropriate Body API

Aggregating the response into a String:

```java
Mono<String> report = client.get()
        .uri("/reports/large")
        .retrieve()
        .bodyToMono(String.class);
```

This keeps the entire report content in memory as one String. It fits when responses are small and business logic genuinely requires the full content.

Reading record by record:

```java
Flux<ReportRow> rows = client.get()
        .uri("/reports/stream")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .bodyToFlux(ReportRow.class);
```

Then processing sequentially:

```java
Mono<Void> processing = rows
        .concatMap(reportService::process)
        .then();
```

`concatMap` preserves order and moves on to the next element only after the current element's publisher completes. If business logic allows concurrent processing, use `flatMap` with bounded concurrency. Never use unbounded concurrency on large streams.

### 6.2. Do Not Cache Large Responses Unboundedly

The following patterns can turn a stream into in-memory retained data:

```java
Mono<List<ReportRow>> allRows = rows.collectList();

Mono<String> allText = rows
        .map(ReportRow::toString)
        .collect(Collectors.joining("\n"));
```

These may be appropriate for small, strictly bounded datasets. For large datasets, process element by element, write in batches to a file/database, or forward the stream downstream.

## 7. Multipart: File Parts and Non-File Parts Follow Different Rules

Multipart should not be viewed simply as a single body with a 256 KB limit.

In WebFlux multipart parsing:

- `maxInMemorySize` limits the size of **non-file parts** kept in memory.
- For **file parts**, this property is the threshold after which file contents are written to disk.
- File parts written to disk also have `maxDiskUsagePerPart` to cap disk usage per part.
- `maxParts` limits the total number of parts in a request.
- `file-storage-directory` specifies the directory storing file parts exceeding the threshold; by default it is a `spring-multipart` directory under the system temp directory.

Spring Boot 3.3 example:

```properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=1GB
spring.webflux.multipart.max-parts=20
spring.webflux.multipart.file-storage-directory=/var/app/upload-tmp
```

These multipart properties have a different scope from `spring.codec.max-in-memory-size`. Set both according to API characteristics if the application accepts both JSON/form bodies and file uploads.

### 7.1. `FilePart.transferTo` Instead of Reading the Whole File into a Byte Array

```java
@PostMapping(
        path = "/files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<ResponseEntity<Void>> upload(
        @RequestPart("file") FilePart file) {

    Path destination = uploadDirectory.resolve(
            UUID.randomUUID() + ".bin");

    return file.transferTo(destination)
            .thenReturn(ResponseEntity.accepted().build());
}
```

This example illustrates saving a file part to disk. The destination filename is generated from a UUID; never concatenate `file.filename()` directly into a filesystem path without validation to prevent path traversal. In real applications, validate permissions, size limits, file types, and clean up temporary files according to lifecycle.

Avoid:

```java
file.content()
        .reduce(new byte[0], this::append);
```

or reading into a large `byte[]` when the ultimate goal is simply writing a file. Aggregating a file into an array causes memory pressure and can exceed codec limits.

### 7.2. Multipart Streaming with `PartEvent`

When multipart must be processed as a stream, WebFlux supports `Flux<PartEvent>`. This avoids parsing the entire content into a `MultiValueMap` just to access parts by name.

Example signature:

```java
@PostMapping(
        path = "/stream-upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<Void> upload(
        @RequestBody Flux<PartEvent> events) {

    return events
            .concatMap(this::processPartEvent)
            .then();
}
```

`processPartEvent` is an application method written to handle headers, part types, buffers, and part-end boundaries. When reading `PartEvent.content()` or `DataBuffer` manually, you must manage buffer consumption/release according to contract. For simple upload APIs, `FilePart.transferTo` is usually easier to maintain.

## 8. Streaming to Avoid Aggregating Large Data

### 8.1. NDJSON for Many JSON Records

NDJSON (Newline Delimited JSON) places each object on its own line:

```text
{"id":1,"value":"alpha"}
{"id":2,"value":"beta"}
{"id":3,"value":"gamma"}
```

A controller can accept:

```java
@PostMapping(
        path = "/events",
        consumes = "application/x-ndjson"
)
public Mono<Void> ingest(
        @RequestBody Flux<Event> events) {

    return events
            .concatMap(eventService::process)
            .then();
}
```

The Jackson decoder supports streaming JSON objects in formats such as NDJSON. Each object is emitted once the parser receives enough data for that object; the memory limit applies per object currently being parsed. Thus the total stream can exceed `maxInMemorySize` as long as each individual object stays within the limit and downstream consumes steadily.

Do not convert `Flux<Event>` into `List<Event>` unless you genuinely need the entire list at once.

### 8.2. JSON Array and `Flux<T>`

The Jackson decoder also supports reading a JSON array as multiple values in `Flux<T>`. For example:

```json
[
  {"id":1,"value":"alpha"},
  {"id":2,"value":"beta"},
  {"id":3,"value":"gamma"}
]
```

Can be accepted by:

```java
@PostMapping("/events-json")
public Mono<Void> ingestJsonArray(
        @RequestBody Flux<Event> events) {

    return events.concatMap(eventService::process).then();
}
```

Do not confuse the decoder with the encoder. For multi-value publishers using `application/json`, `Jackson2Encoder` by default may collect values into a list before serializing them as a JSON array. If you need to write and flush element by element sequentially, use a streaming media type such as `application/x-ndjson` or a suitable streaming format.

### 8.3. Server-Sent Events

SSE is a stream of line-delimited events. WebFlux can decode/encode individual events, but the reader must collect the lines belonging to one event to parse it completely. A single oversized event or an overly long line without a delimiter can still exceed the buffer limit.

Therefore, when using SSE:

- Keep each event small and clearly structured.
- Do not put entire logs or large documents into a single event.
- Send periodic heartbeats on long-lived streams to detect client disconnects.
- Do not aggregate the whole stream with `collectList()`.
- Set event limits appropriate to the contract.

### 8.4. Backpressure Does Not Replace Buffer Limits

Backpressure regulates producer/consumer rates via demand. It does not automatically guarantee constant memory usage across all operators. An operator may prefetch, cache, or buffer data. An application may also use its own unbounded queue.

Safe streaming design simultaneously requires:

1. The publisher emits data element by element.
2. Downstream consumes by demand.
3. Operators have bounded concurrency/prefetch.
4. The entire stream is never collected into a collection.
5. Buffers are released once used or discarded.
6. Separate limits exist for individual elements and off-heap resources.

## 9. Managing `DataBuffer` and Avoiding Leaks

For applications using only `@RequestBody DTO`, `bodyToMono`, `bodyToFlux`, `FilePart`, and default codecs, Spring normally manages buffer lifecycles. Applications must pay closer attention when reading/writing `DataBuffer` directly, writing custom codecs, or using operators that may drop buffers.

### 9.1. Buffers Can Be Pooled and Reference-Counted

Some connectors such as Reactor Netty use pooled buffers. Once data is consumed, buffers must be released to return resources to the pool. Retaining buffers after the pipeline ends or dropping buffers without releasing them can cause memory leaks.

Supporting APIs:

- `DataBufferUtils.release(dataBuffer)`: releases if the buffer is pooled/closeable and requires release.
- `DataBufferUtils.retain(dataBuffer)`: increments the reference count when a buffer must be held longer than the current contract.
- `DataBufferUtils.join(...)`: safely merges buffers and manages input buffers during aggregation.
- `doOnDiscard(DataBuffer.class, DataBufferUtils::release)`: releases buffers discarded by operators when the composition follows an appropriate pattern.

Do not call `release` arbitrarily on buffers still owned by the framework or downstream. Every buffer needs clear ownership: who reads, who holds, and who releases.

### 9.2. Operators Can Discard Buffers

Operators like `filter`, `skip`, `take`, `flatMap`, or operators with prefetch/caching can drop elements along certain error/cancel paths. When a dropped element is a pooled `DataBuffer`, ensure it is released.

Example pattern in a decoder/custom pipeline:

```java
Flux<DataBuffer> safe = source
        .filter(this::isUseful)
        .doOnDiscard(
                DataBuffer.class,
                DataBufferUtils::release);
```

This is an example of a discard hook, not a recipe to blindly add to every `Flux<DataBuffer>`. Add it only when an operator can actually discard buffers and this pipeline holds ownership.

### 9.3. When Using `DataBufferUtils.join`

```java
Mono<DataBuffer> joined = DataBufferUtils.join(
        request.getBody(),
        1024 * 1024);
```

This caps the joined body at 1 MiB. Upon receiving the resulting buffer, consuming code must ensure release after reading finishes. If you only want to save/forward the stream, joining is unnecessary.

Do not convert `DataBuffer` to `byte[]` and keep unnecessary copies. During processing, the original buffer, byte array, UTF-16 String, and JSON object could all coexist, making actual memory consumption much higher than the wire body size.

## 10. `DataBufferLimitException` and HTTP Status Codes

`DataBufferLimitException` is a Spring Core exception; it carries no built-in HTTP status. It does not automatically mean the response must be `413 Payload Too Large`.

Distinguish where the exception happens:

| Origin | Meaning |
|---|---|
| Server decoding request body | The server cannot continue aggregating the body/record within codec limits |
| WebClient decoding response body | The client application cannot decode the response within local limits |
| Custom `DataBufferUtils.join` | The join operation itself exceeded `maxByteCount` |
| Multipart parser | A part exceeded memory/disk/parts limits per reader configuration |

On the server, request decode errors may be wrapped in input/codec exceptions before reaching an exception handler. The default status depends on the processing path and error configuration. If an API wants to represent exceeding the body threshold specifically with 413, explicitly detect `DataBufferLimitException` in the cause chain and map it in `@ControllerAdvice` or `WebExceptionHandler`.

On the client, if WebClient receives HTTP 200 but the body exceeds the local decode limit, the application may receive `DataBufferLimitException` in the reactive pipeline. This is not an HTTP 413 from the remote server; the server may have returned a successful response.

### Example Intentional Mapping to 413

```java
@RestControllerAdvice
public class PayloadLimitAdvice {

    @ExceptionHandler({
            DataBufferLimitException.class,
            ServerWebInputException.class
    })
    public ResponseEntity<ProblemDetail> handleInput(Exception error) {
        boolean limitExceeded = hasCause(
                error, DataBufferLimitException.class);

        HttpStatus status = limitExceeded
                ? HttpStatus.PAYLOAD_TOO_LARGE
                : HttpStatus.BAD_REQUEST;

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                limitExceeded
                        ? "The request contains a buffered item that is too large."
                        : "The request body could not be read.");

        problem.setTitle(limitExceeded
                ? "Payload limit exceeded"
                : "Invalid request body");

        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expected) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (expected.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

This is an illustrative policy. Depending on the codec/argument resolver, the exception may be wrapped across multiple layers; test against your actual Spring version and endpoint to confirm the cause chain. Never return stack traces, internal filenames, or raw bodies to clients.

## 11. Choosing Thresholds Based on Memory Budget

Do not raise `maxInMemorySize` arbitrarily just to silence errors. Estimate consumption when many requests run concurrently.

Hypothetical example:

- Aggregation limit per request: 2 MiB.
- 200 concurrent requests pass through the aggregation point simultaneously.
- Theoretical aggregated data volume: roughly 400 MiB.

That is only the buffered data at the limit, before counting decoded objects, token buffers, String/byte array copies, response buffers, queues, connections, framework heap, and the rest of the application. A 10 MiB limit may look small for one request, but becomes huge when multiplied across hundreds of concurrent requests.

When selecting thresholds:

1. Measure the largest valid payload size in business workflows.
2. Estimate concurrency on the endpoint.
3. Measure heap/GC under realistic load.
4. Set a sufficient threshold with controlled headroom.
5. Limit concurrent requests or upload rates when necessary.
6. Use streaming for large files/records.
7. Set total body limits at the gateway/server if the API needs whole-request protection.
8. Set separate limits for multipart parts, part count, and disk usage.
9. Monitor `DataBufferLimitException` counts by endpoint and over time.
10. Test with payloads just below, exactly at, and above the limit.

### What Does `-1` Mean?

Some `maxInMemorySize` APIs accept `-1` to disable the limit. This is a dangerous configuration for untrusted input or payloads that can grow arbitrarily. Only use it when another proven limiting mechanism is in place and memory impact is well understood.

Disabling the codec limit does not make data streaming. If code still calls `bodyToMono(String.class)` or `collectList()`, the application can still retain all data on the heap and hit `OutOfMemoryError`.

## 12. Runnable Java 17+ Project: Testing Codec Limits

The example uses Spring Boot 3.3.5, Java 17, Spring WebFlux, and `WebTestClient`. The server codec is configured with a 128-byte limit for quick testing:

- Small text bodies are read successfully.
- Large text bodies exceeding the limit are mapped to 413 by the application's advice.
- NDJSON whose total size exceeds 128 bytes is still read when each individual record stays below the threshold.
- `DataBufferUtils.join` emits `DataBufferLimitException` when exceeding its dedicated limit.

### 12.1. Structure

```text
webflux-buffer-limit/
├── pom.xml
└── src/
    ├── main/java/edu/demo/buffer/
    │   ├── BufferApplication.java
    │   ├── CodecConfiguration.java
    │   ├── BufferController.java
    │   └── PayloadLimitAdvice.java
    └── test/java/edu/demo/buffer/
        └── BufferLimitTests.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-buffer-limit</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

### 12.3. `BufferApplication.java`

```java
package edu.demo.buffer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BufferApplication {

    public static void main(String[] args) {
        SpringApplication.run(BufferApplication.class, args);
    }
}
```

### 12.4. `CodecConfiguration.java`

```java
package edu.demo.buffer;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs().maxInMemorySize(128);
    }
}
```

The 128-byte limit is strictly for easy reproduction in tests. Never use such a tiny number as a production configuration for normal JSON APIs.

### 12.5. `BufferController.java`

```java
package edu.demo.buffer;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class BufferController {

    public record Event(String value) {
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> echo(@RequestBody Mono<String> body) {
        return body;
    }

    @PostMapping(
            path = "/events",
            consumes = "application/x-ndjson"
    )
    public Mono<Void> events(@RequestBody Flux<Event> events) {
        return events
                .doOnNext(event -> {
                    // Replace with bounded, non-blocking processing.
                })
                .then();
    }
}
```

`/echo` must build one complete String. `/events` receives each NDJSON object without collecting all of them into a list. In a real application, replace `doOnNext` with a reactive service that has bounded concurrency and appropriate side effects.

### 12.6. `PayloadLimitAdvice.java`

```java
package edu.demo.buffer;

import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
public class PayloadLimitAdvice {

    @ExceptionHandler({
            DataBufferLimitException.class,
            ServerWebInputException.class
    })
    public ResponseEntity<ProblemDetail> handle(Exception error) {
        boolean exceeded = hasCause(
                error, DataBufferLimitException.class);

        HttpStatus status = exceeded
                ? HttpStatus.PAYLOAD_TOO_LARGE
                : HttpStatus.BAD_REQUEST;

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                exceeded
                        ? "A buffered request item exceeded the configured limit."
                        : "The request body could not be read.");

        problem.setTitle(exceeded
                ? "Payload limit exceeded"
                : "Invalid request body");

        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expected) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (expected.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

This advice reflects the sample app's policy: 413 is returned only when `DataBufferLimitException` appears in the cause chain. Other body-read errors return 400. A real application should test exception wrapping and may need to handle additional exception types depending on the codec/endpoint.

### 12.7. `BufferLimitTests.java`

```java
package edu.demo.buffer;

import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferFactory;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BufferLimitTests {

    @Autowired
    WebTestClient client;

    @Test
    void smallTextBodyIsAccepted() {
        client.post()
                .uri("/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("hello");
    }

    @Test
    void oversizedAggregatedBodyMapsTo413() {
        String large = "x".repeat(1024);

        client.post()
                .uri("/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue(large)
                .exchange()
                .expectStatus().isEqualTo(413)
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("Payload limit exceeded");
    }

    @Test
    void streamCanExceedTotalLimitWhenEachRecordIsSmall() {
        String ndjson = IntStream.range(0, 20)
                .mapToObj(index ->
                        "{\"value\":\"record-" + index + "\"}")
                .collect(Collectors.joining("\n"));

        client.post()
                .uri("/events")
                .contentType(MediaType.parseMediaType(
                        "application/x-ndjson"))
                .bodyValue(ndjson)
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void joinFailsWhenCumulativeBytesExceedItsLimit() {
        DataBufferFactory factory = new DefaultDataBufferFactory();

        Flux<DataBuffer> buffers = Flux.just(
                factory.wrap(new byte[8]),
                factory.wrap(new byte[8]));

        StepVerifier.create(DataBufferUtils.join(buffers, 12))
                .expectError(DataBufferLimitException.class)
                .verify();
    }
}
```

### 12.8. Running Tests

From the directory containing `pom.xml`:

```bash
mvn test
```

When dependencies download successfully and the test environment works, the test suite has four cases:

1. A small body is read successfully.
2. A 1,024-byte aggregated body exceeds the 128-byte limit and the advice returns 413.
3. NDJSON exceeding 128 bytes in total is still read when each record is smaller than the limit.
4. `DataBufferUtils.join` emits `DataBufferLimitException` when cumulative buffers exceed 12 bytes.

Expected Maven Surefire output:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

This is the expected result to verify after running `mvn test`; this document does not claim Maven was executed in the authoring environment.

## 13. Diagnosing `DataBufferLimitException`

When `Exceeded limit on max bytes to buffer` appears in logs, check in sequence:

1. Did the exception occur on the server or in WebClient?
2. Is the endpoint using `Mono<T>`, `byte[]`, `String`, `collectList()`, or `Flux<T>`?
3. Which codec is decoding? Jackson, String, form, SSE, or multipart?
4. Does the effective limit come from default codecs, `WebFluxConfigurer`, `spring.codec.max-in-memory-size`, or a custom WebClient configuration?
5. If streaming, which single element exceeded the limit?
6. If multipart, is it a non-file part or a file part? Are spill-to-disk threshold, max disk usage, and max parts configured?
7. Is any filter, logger, or custom decoder reading/aggregating the body a second time?
8. Are there `collectList`, `cache`, `join`, `reduce`, or unbounded queues after decoding?
9. What are the concurrent request count and heap/GC levels at the time of error?
10. Can it be processed as a stream, split into batches, or written directly to storage?

### Distinguishing Easily Confused Errors

| Error | Meaning | Where to investigate |
|---|---|---|
| `DataBufferLimitException` | Buffer/aggregate operation exceeded threshold | Codec limit, record size, `join`, delimiters |
| `OutOfMemoryError` | JVM exhausted allocatable memory | Heap dump, leaks, object retention, concurrency |
| 413 Payload Too Large | HTTP server/gateway/API contract rejected an oversized payload | Request-size policy and body limits at each layer |
| 415 Unsupported Media Type | Server does not support the Content-Type | Codec/reader and `consumes` |
| JSON decode error | Body could not be parsed into target type | Syntax, JSON shape, DTO, Jackson |
| Timeout | Timed out waiting for I/O or processing | Network, scheduler, upstream, timeout config |

`413` does not appear automatically simply because a codec throws `DataBufferLimitException`; it must be mapped per the API contract. Conversely, a gateway may return 413 before the request reaches WebFlux, so the application never sees this exception.

### Logs and Metrics

Record:

- Request ID/correlation ID.
- Route template and HTTP method.
- Server or client side.
- Codec/operation if identifiable.
- Estimated size or content length when reliable.
- Error counts by endpoint and over time.
- Heap, GC, and concurrency at the time of error.

Do not log the entire body just to find the cause; the act of logging the body itself can aggregate data and trigger the error. Never write tokens, passwords, PII, or file contents to logs.

## 14. Common Design Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Raising `maxInMemorySize` very high to mask all errors | Many concurrent requests can cause memory pressure/OOM | Pick limits based on record size and concurrency |
| Setting `-1` for untrusted input | Aggregation has no protective threshold | Keep finite limits and use streaming |
| Reading large files with `byte[]` or `String` | Entire file sits on the heap | `FilePart.transferTo` or streaming to storage |
| Calling `collectList()` on long streams | Accumulates all records in memory | Process record by record or in bounded batches |
| Assuming `Flux<T>` is always streaming | Downstream operators may still aggregate | Check the full pipeline and media type |
| Sending a huge single JSON object inside NDJSON | One record still exceeds the threshold | Split the object into smaller pieces or raise threshold in a controlled way |
| Confusing codec limit with total upload limit | Missing body-size policy at gateway/server | Set a separate total request limit |
| Confusing multipart threshold with file-size cap | Large files can still be written to disk | Configure `maxDiskUsagePerPart`, `maxParts`, and total limits |
| Calling unbounded `DataBufferUtils.join` | Merges large bodies into memory | Use the overload with `maxByteCount` |
| Reading `DataBuffer` directly without releasing | Pooled buffer leak | Manage ownership and release per contract |
| Using `filter`/`skip` on DataBuffers while ignoring discard | Dropped buffers are not released | Use `doOnDiscard` appropriately |
| Checking only status 413 | Misses client-side decode errors or 400 errors | Check exception/cause chain and origin |
| Logging bodies to debug | Creates extra aggregation, exposes data | Log safe metadata and trace IDs |
| Using unbounded concurrency to process a stream | Many objects/buffers sit in memory simultaneously | Use `flatMap` with bounded concurrency or `concatMap` |

## 15. Production Configuration Checklist

Before shipping an endpoint receiving large data to production:

- Have you identified which codecs/readers actually aggregate data?
- Does `maxInMemorySize` match the maximum size of a single object/record?
- Is the limit applied consistently to both the WebFlux server and any WebClients used?
- Do manually constructed WebClients have their own codec configuration?
- Are multipart non-file parts, file threshold, disk usage, and part counts bounded?
- Are file parts streamed/transferred to storage instead of collected into byte arrays?
- Do NDJSON/SSE streams have finite sizes per record/event?
- Are `collectList`, `cache`, `join`, and unbounded queues avoided?
- Do operators handling `DataBuffer` properly release consumed or discarded buffers?
- Are concurrency, upload rate, and request-size limits enforced at the gateway/server?
- Are server-side codec errors distinguished from WebClient response decode errors?
- Are status/error bodies mapped per contract instead of assuming default 413?
- Are there tests below threshold, above threshold, streaming many small records, and uploading large multipart files?
- Are there metrics for limit errors, heap, GC, request concurrency, and processing latency?

## 16. Self-Check Exercises

**Exercise 1.** `bodyToMono(String.class)` receives a 1 MB response while the codec limit is 256 KB. What can happen?

**Answer:** The reader must aggregate the entire body into a String; it may emit `DataBufferLimitException` when exceeding 256 KB.

**Exercise 2.** A `Flux<Event>` has 10,000 records, 2 KB each. Total stream is about 20 MB, codec limit is 256 KB. Will the stream definitely fail?

**Answer:** No. With a streaming decoder, the limit applies per object being aggregated; the total stream can exceed the limit if each record stays within the threshold and downstream consumes sequentially.

**Exercise 3.** A single NDJSON record is 500 KB, limit is 256 KB. What happens?

**Answer:** That record can exceed the limit because the parser must hold enough data for one complete object.

**Exercise 4.** Does a 100 MB multipart file have to keep 100 MB on the heap?

**Answer:** No. `maxInMemorySize` is the threshold to spill file parts to disk; file parts larger than the threshold can be saved to a temp directory. Disk usage and part-count limits should be configured.

**Exercise 5.** Does `DataBufferLimitException` always return HTTP 413?

**Answer:** No. It is a Spring Core exception and carries no HTTP status. An application can intentionally map it to 413; the actual status depends on where it occurs and exception handling.

**Exercise 6.** Why is setting the limit to `-1` not a sustainable fix?

**Answer:** `-1` removes the aggregation limit. With a large request or many concurrent requests, the application can retain huge amounts of data and hit `OutOfMemoryError`.

**Exercise 7.** Why is `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` needed in some custom pipelines?

**Answer:** Some operators can discard buffers on filter/skip/error/cancel. With pooled DataBuffers, discarded buffers owned by the pipeline must be released.

**Exercise 8.** WebClient receives HTTP 200 but decoding the response fails due to exceeding the memory limit. Can we say the server returned 413?

**Answer:** No. The server may have returned 200; the error occurred on the client while decoding the response under the local limit.

## 17. Key Takeaways

- `maxInMemorySize` limits bytes aggregated in memory by codecs/readers.
- Most Spring Framework 6.2 default codecs use a 256 KB threshold; exact configuration can vary by codec.
- `DataBufferLimitException` signals that total bytes in a buffer/aggregate operation exceeded the threshold.
- For streaming, the limit applies per object/record/event being aggregated, not to the total bytes of the entire stream.
- The server uses `ServerCodecConfigurer`; WebClient uses `WebClient.Builder.codecs(...)`; Spring Boot provides `spring.codec.max-in-memory-size`.
- Multipart uses `maxInMemorySize` as the non-file part limit and spill-to-disk threshold for file parts; disk and part-count limits are also needed.
- `Flux<T>` only enables streaming when downstream does not aggregate all data.
- If handling `DataBuffer` directly, manage release/retain and discard according to contract.
- `DataBufferLimitException` does not automatically mean HTTP 413; map it intentionally.
- Do not just raise thresholds: choose streaming reading/writing, bound concurrency, and measure memory under load.

When encountering an error, answer three questions: **what is being aggregated, which unit does the limit apply to, and can it be processed element by element instead of holding the entire content?**

## Official Documentation

- Spring Framework 6.2, **WebFlux Reactive Core – Limits, Codecs, Multipart and DataBuffer**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2, **Data Buffers and Codecs**: https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html
- Spring Framework 6.2, **WebFlux HTTP Message Codec Configuration**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
- Spring Framework 6.2, **WebClient Configuration and MaxInMemorySize**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html
- Spring Framework 6.2, **`DataBufferLimitException` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/io/buffer/DataBufferLimitException.html
- Spring Framework 6.2, **`DataBufferUtils` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
- Spring Framework 6.2, **`CodecConfigurer.DefaultCodecs` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/codec/CodecConfigurer.DefaultCodecs.html
- Spring Boot 3.3, **Common Application Properties – codec and multipart limits**: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.2, **WebTestClient**: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html