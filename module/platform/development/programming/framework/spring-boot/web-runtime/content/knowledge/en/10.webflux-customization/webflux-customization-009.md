# Limiting In-Memory Buffering When Reading Content – Spring WebFlux

## 1. Learning Objectives

Spring WebFlux receives HTTP bodies as a stream of data rather than forcing the entire payload into RAM upfront. However, when a codec converts a byte stream into **a single String, byte[], JSON DTO, form data, or another object**, it may need to **aggregate/buffer** multiple `DataBuffer`s. Unbounded, even a single large payload or many concurrent requests can trigger heap pressure, direct memory pressure, garbage collection overhead, and latency spikes.

Spring Framework provides **`maxInMemorySize`** for codecs that need buffering. Spring Boot 3.5 provides the property **`spring.http.codecs.max-in-memory-size`** to configure this limit for the WebFlux server and Boot-auto-configured `WebClient` instances.

After this lesson, you will be able to:

1. Distinguish byte streams, `DataBuffer`, `Decoder`, `HttpMessageReader`, aggregation, and streaming.
2. Understand the true scope of **`maxInMemorySize`** and **`DataBufferLimitException`**.
3. Configure Spring Boot 3.5 using YAML, Java **`WebFluxConfigurer`**, and separate **`WebClient`** configuration.
4. Distinguish codec buffer limits, total HTTP request limits, multipart disk usage, and concurrency limits.
5. Run a Java 17 / Spring Boot 3.5 demo to test large JSON, small JSON, and NDJSON streaming.
6. Choose strategies for files, streaming, and `DataBuffer` handling that avoid unintended RAM accumulation.

This lesson belongs to **WebFlux Customization**; do not copy Servlet properties like **`spring.servlet.multipart.max-file-size`** verbatim to WebFlux/Reactor Netty.

## 2. Why Doesn't Reactive Mean Zero Memory Usage?

Overview diagram:

~~~mermaid
flowchart TD
    A[HTTP network chunks] --> B[Flux DataBuffer]
    B --> C{Which shape does app / codec need?}
    C -->|Single object / String / byte array| D[Aggregation]
    D --> E[maxInMemorySize]
    E --> F[Decoded DTO or DataBufferLimitException]
    C -->|Independent elements| G[Streaming decoder]
    G --> H[Decode each item with possible per-item buffer]
    H --> I[Flux processes items incrementally]
~~~

**`DataBuffer`** is an abstraction for a region of bytes, potentially allocated from pooled/direct memory depending on the server. **`Mono`** represents at most one result; **`Flux`** represents multiple results. Yet this **does not** guarantee `Mono` always buffers or `Flux` always streams without limit: you must check the actual codec and data type.

For example:

- **`@RequestBody Mono<MyDto>`**: typically requires decoding a complete JSON object and may buffer.
- **`@RequestBody Mono<String>`**: typically aggregates text chunks into a single `String`.
- **`WebClient.bodyToMono(byte[].class)`**: typically aggregates the response into a byte array.
- **`Flux<Event>` with NDJSON**: can read one JSON object at a time, though the codec may still buffer enough to complete **one record**.
- **`Flux<DataBuffer>`**: lets you process chunk by chunk, though calling **`collectList()`**, **`DataBufferUtils.join()`**, or manually concatenating `byte[]` still performs aggregation.

**Backpressure** regulates consumption rate between compatible publishers and subscribers; it does not replace total payload caps or limits on accumulated objects.

## 3. What Does maxInMemorySize Limit?

Some WebFlux codecs must retain part or all of an input in memory to produce output. **`maxInMemorySize`** caps the buffered bytes for the corresponding decode operation.

Specific cases:

| Read type | How it buffers | Meaning of threshold |
|---|---|---|
| **`Mono<String>`** | Aggregates text into one value | Rejected when exceeding limit |
| **`Mono<byte[]>`** | Aggregates bytes into one array | Threshold applies to this accumulation |
| **`Mono<MyDto>`** from JSON | Decoder must parse the JSON object | A large object can exceed the threshold |
| Form **`application/x-www-form-urlencoded`** | Typically parses and collects form fields | Codec can cap buffered data |
| **`Flux<Event>`** from NDJSON | Splits each record and decodes | Normally applied **per record** |
| Line-delimited text `Flux` | Buffers up to a line boundary | A single overly long line can still exceed the threshold |
| Raw **`Flux<DataBuffer>`** | Does not inherently aggregate into an object | Limit is not a total byte cap on the stream |
| Multipart | Parser has separate RAM/disk thresholds | Do not treat memory limit as file-size cap |

### 3.1. Common Default Values

When no global limit is set, each codec uses its default configuration. Per Spring Framework and Spring Boot 3.5 documentation, **most codecs default to around 256 KiB**, which equals **262,144 bytes**.

This is measured in **bytes**, not 262,144 characters. A UTF-8 string containing accented characters or emojis can consume more bytes than its visible character count.

Typical error when a codec buffers beyond the threshold:

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

The exact message may include the configured limit depending on version. This exception reports that **codec aggregation exceeded its cap**, not necessarily that the JVM hit an `OutOfMemoryError`.

### 3.2. What This Limit Does NOT Do

**`maxInMemorySize` is NOT:**

- A total byte limit for every HTTP request: an NDJSON stream of many small records can exceed the threshold in total bytes while still being processed sequentially.
- A total cap on process heap or direct memory; many requests can still buffer concurrently.
- A cap on concurrent requests, number of elements in a `Flux`, transfer rate, or request duration.
- A blanket cap on file uploads; multipart parsing can spool parts to disk.
- Your sole DoS defense; you still need connection limits, rate limits, timeouts, disk quotas, body size caps, and authentication.
- A limit on manual accumulation operators written outside codecs, such as an unbounded **`collectList()`**.

Key rule: **size codec limits for valid data needs, while enforcing total request limits at the appropriate layer**.

## 4. Proper Configuration for Spring Boot 3.5

In **`src/main/resources/application.yml`**, set:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 512KB
~~~

Boot converts the data size into the corresponding byte limit for auto-configured codecs. **`512KB`** in Spring Boot `DataSize` syntax equals **512 × 1,024 bytes**.

If endpoints only expect small payloads, such as a 128 KiB limit:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 128KB
~~~

Evaluate real payload sizes, concurrent client counts, and downstream constraints before raising or lowering it.

### 4.1. Note Property Name Changes Across Versions

| Version | Property |
|---|---|
| **Spring Boot 3.4.x and older docs** | **`spring.codec.max-in-memory-size`** |
| **Spring Boot 3.5.x** | **`spring.http.codecs.max-in-memory-size`** |
| **Spring Boot 4.x** | Check docs for your running branch; the newer property group is **`spring.http.codecs`** |

Spring Boot 3.5 deprecated the old property name. **Do not copy YAML from old blog posts** without checking the version: if the property does not bind, you may still hit errors at the default limit.

Official documentation URL: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/

### 4.2. Configuring via WebFluxConfigurer

When configuring directly at the Spring Framework level, for example:

~~~java
package com.example.bufferlimit;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

`configureHttpMessageCodecs` customizes codecs on the WebFlux server. This example sets a 512 KiB limit for default codecs.

**Pick one clear source of truth**: when both a property and a configuration class touch the same codec, verify effective precedence for your version and avoid declaring conflicting values.

### 4.3. Server and WebClient Are Two Separate Directions

The Spring Boot 3.5 property applies to **auto-configured WebFlux servers** and **Boot-auto-configured `WebClient` instances**. However, a client created manually with **`WebClient.builder()`** or custom `ExchangeStrategies` **is not guaranteed to inherit** Boot's property settings.

Example configuring an individual client:

~~~java
import org.springframework.web.reactive.function.client.WebClient;

WebClient client = WebClient.builder()
        .baseUrl("https://example.org")
        .codecs(codecs -> codecs.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024))
        .build();
~~~

The snippet above is an **illustration inside an application class** with the WebFlux dependency, not a standalone program.

Distinguish:

- **Inbound request body**: the WebFlux server reads data sent by callers.
- **Outbound HTTP call response**: `WebClient` reads data returned by another service.
- If you use both, check **both codec contexts**, even when both inherit the property via Boot auto-configuration.

## 5. DataBufferLimitException and HTTP Responses

Buffer limits exist primarily to **protect resources**. When exceeded, codecs can emit **`DataBufferLimitException`**.

### 5.1. Why Doesn't Every Error Automatically Return HTTP 413?

**HTTP 413 Content Too Large** is a meaningful status when a request exceeds accepted limits. However, Spring WebFlux does not guarantee that a `DataBufferLimitException` is automatically mapped to 413 in **every version, every reader, and every exception path**. Without an explicit mapping, the default error response may differ.

To enforce a stable error contract in your application, handle the error at an appropriate boundary. A simple example when the exception reaches controller advice:

~~~java
package com.example.bufferlimit;

import java.util.Map;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class BufferLimitAdvice {

    @ExceptionHandler(DataBufferLimitException.class)
    public ResponseEntity<Map<String, String>> tooLarge(
            DataBufferLimitException ex) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of(
                        "code", "DECODE_BUFFER_LIMIT",
                        "message", "Request content exceeds the decode limit"));
    }
}
~~~

When the error reaches this advice, the result is **HTTP 413** and JSON containing **`code=DECODE_BUFFER_LIMIT`**. Yet if the error occurs before Spring routing, after the response has committed, or wrapped in another exception type, this advice may not intercept it. Test actual HTTP behavior.

**Never** try to recover by catching the exception and reading the entire HTTP body into a large byte array: the body stream may already be partially consumed, and doing so defeats the purpose of capping RAM.

### 5.2. Diagnosing by Boundary

1. Did the error happen on the **server** reading a request, or in **`WebClient`** reading a response?
2. Is the endpoint reading one full object or streaming record by record?
3. Is there another custom decoder or an operator like **`collectList()`**?
4. Did the property bind under the right name and active profile?
5. Did a proxy return 413 before the request even reached the application?
6. Can the API switch to streaming or chunked uploads instead of raising the limit?

## 6. Runnable Spring Boot 3.5 / Java 17 Example

Build a WebFlux application with two endpoints:

- **`POST /api/echo`**: accepts a JSON object and returns the UTF-16 code unit count of the `text` field.
- **`POST /api/events`**: accepts NDJSON containing multiple records and counts the records in streaming fashion.

### 6.1. Project Structure

~~~text
buffer-limit-demo/
├── pom.xml
├── BodyGenerator.java
└── src/main/
    ├── java/com/example/bufferlimit/
    │   ├── BufferLimitApplication.java
    │   ├── PayloadController.java
    │   └── BufferLimitAdvice.java
    └── resources/
        └── application.yml
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>buffer-limit-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
~~~

**Do not add `spring-boot-starter-web`** to this demo: when MVC and WebFlux coexist, Boot usually prioritizes MVC and test outcomes would no longer reflect the same stack.

### 6.3. BufferLimitApplication.java

~~~java
package com.example.bufferlimit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BufferLimitApplication {
    public static void main(String[] args) {
        SpringApplication.run(BufferLimitApplication.class, args);
    }
}
~~~

### 6.4. PayloadController.java

~~~java
package com.example.bufferlimit;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class PayloadController {

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Summary> echo(@RequestBody Mono<Payload> input) {
        return input.map(p ->
                new Summary(p.text() == null ? 0 : p.text().length()));
    }

    @PostMapping(
            path = "/events",
            consumes = "application/x-ndjson",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, Long>> events(
            @RequestBody Flux<Event> events) {
        return events.count()
                .map(count -> Map.of("processed", count));
    }

    public record Payload(String text) {}
    public record Summary(int chars) {}
    public record Event(String id, String value) {}
}
~~~

For **`/api/echo`**, a large JSON document is decoded into a single **`Payload`**. For **`/api/events`**, the decoder can emit each `Event` from NDJSON; **`count()`** does not accumulate all events into a `List`. However, this endpoint does not yet cap **the total number of events**, which should be added in real deployments.

### 6.5. BufferLimitAdvice.java

Use the **`BufferLimitAdvice`** class from section 5.1 as-is. Because it is in the same package as the main class, component scanning picks it up.

### 6.6. application.yml

~~~yaml
server:
  port: 8080

spring:
  http:
    codecs:
      max-in-memory-size: 128KB
~~~

The 128 KiB limit is chosen for learning and reproducing the error; it is not a universal recommendation for every application.

Run:

~~~bash
mvn spring-boot:run
~~~

Send a small request:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary '{"text":"xin chào"}' \
  "http://localhost:8080/api/echo"
~~~

With a valid UTF-8 payload, expect HTTP 200 with body:

~~~json
{"chars":8}
~~~

The number 8 is the count of UTF-16 code units in **`xin chào`** (3 + 1 space + 4), not the HTTP byte length.

### 6.7. Generating a Large JSON Document with Java 17

Create **`BodyGenerator.java`** in the root directory, independent of Spring dependencies:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class BodyGenerator {
    public static void main(String[] args) throws Exception {
        int length = Integer.parseInt(args[0]);
        String json = "{\"text\":\"" + "a".repeat(length) + "\"}";
        Path output = Path.of("body.json");
        Files.writeString(output, json, StandardCharsets.UTF_8);
        System.out.println(Files.size(output));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 BodyGenerator.java
java BodyGenerator 200000
~~~

Exact stdout:

~~~text
200011
~~~

The `body.json` file contains **200,011 bytes** (200,000 bytes for character `a` plus 11 bytes for braces/quotes/field name), which exceeds **128 KiB = 131,072 bytes**.

Send it:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary @body.json \
  "http://localhost:8080/api/echo"
~~~

In this demo, **do not expect a normal 200 `Summary` result** when the codec cannot decode an object exceeding the buffer limit. If `DataBufferLimitException` passes through **`BufferLimitAdvice`**, the result is HTTP 413 with error JSON containing **`code=DECODE_BUFFER_LIMIT`**. If you observe a different result, inspect the logs and check the actual exception rather than assuming every threshold violation returns 413.

Test a smaller payload:

~~~bash
java BodyGenerator 1000
~~~

Stdout:

~~~text
1011
~~~

Resend `body.json`: expect HTTP 200 with:

~~~json
{"chars":1000}
~~~

ASCII characters are used here so byte counting stays exact; with Vietnamese accents and emojis, UTF-8 byte counts differ from UTF-16 code units.

### 6.8. Testing NDJSON Streaming

Create **`events.ndjson`**, saved as UTF-8:

~~~json
{"id":"1","value":"a"}
{"id":"2","value":"b"}
{"id":"3","value":"c"}
~~~

Call:

~~~bash
curl -i \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @events.ndjson \
  "http://localhost:8080/api/events"
~~~

Expected response body:

~~~json
{"processed":3}
~~~

**Key point:** with NDJSON streaming, many records can add up to a large total body while the codec only needs to retain each individual record as needed. A single giant record can still exceed `maxInMemorySize`. **Never** switch to `collectList()` just for convenience if the record count can be unbounded.

The multiline `curl` commands use Bash syntax. In Windows PowerShell, use **`curl.exe`** with appropriate syntax; sending payloads from UTF-8 files helps avoid escaping issues.

## 7. Limits When Using WebClient

`WebClient` faces the exact same issue when **reading HTTP responses**:

~~~java
Mono<String> result = client.get()
        .uri("/reports/latest")
        .retrieve()
        .bodyToMono(String.class);
~~~

If the response is large text, **`bodyToMono(String.class)`** must aggregate bytes into a `String`, causing `DataBufferLimitException` on the **client side**. Do not raise the server's inbound limit to fix a manually constructed `WebClient`.

Appropriate strategies:

- If an API returns a legitimately large single JSON object, configure a client-specific limit after calculating your memory budget.
- If the API supports NDJSON/SSE, use `Flux` and process items incrementally; note each individual record still has its own limit.
- If downloading large files, stream directly to disk/storage instead of `bodyToMono(byte[].class)`.
- Set timeouts, bounded retries, and limits on concurrent responses. A `WebClient` buffering many 2 MiB responses concurrently can still drive significant memory usage.

## 8. Multipart: Memory Limits Are Not File Size Limits

For **`multipart/form-data`**, Spring WebFlux has a separate property group. Example in Spring Boot 3.5:

~~~yaml
spring:
  webflux:
    multipart:
      max-in-memory-size: 256KB
      max-disk-usage-per-part: 20MB
      max-parts: 5
~~~

| Property | Purpose |
|---|---|
| **`spring.webflux.multipart.max-in-memory-size`** | For non-file parts, the memory limit; for file parts, the threshold before spooling to disk |
| **`spring.webflux.multipart.max-disk-usage-per-part`** | Disk usage cap per part when the parser writes to disk |
| **`spring.webflux.multipart.max-parts`** | Maximum number of parts allowed in one request |
| **`spring.webflux.multipart.max-headers-size`** | Header data cap per part |
| **`spring.webflux.multipart.file-storage-directory`** | Directory for temporary multipart files in applicable modes |

Do not equate **`max-in-memory-size: 256KB`** with "maximum file upload size is 256 KB." Larger file parts can spill to disk; you still need quotas, total file size caps, part limits, timeouts, storage lifecycle cleanup, and proxy/ingress limits.

To handle uploaded files in a reactive controller, **`FilePart.transferTo(Path)`** is far better than trying to decode the entire file into `byte[]` or `String`.

Illustrative **snippet inside a controller**, not a standalone class:

~~~java
@PostMapping(path = "/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<String> upload(@RequestPart("file") FilePart file) {
    Path target = Path.of("/srv/uploads")
            .resolve(UUID.randomUUID() + ".bin");
    return file.transferTo(target).thenReturn("uploaded");
}
~~~

This requires importing **`Path, UUID, MediaType, FilePart, PostMapping, RequestPart, Mono`**, an existing storage directory, and valid write permissions. Never concatenate user-supplied filenames directly into paths. **`transferTo`** does not automatically cap total upload size or sanitize malicious files.

### 8.1. Using PartEvent for Streaming Multipart

Spring WebFlux supports **`PartEvent`** to process multipart streams incrementally. In that mode, temporary file storage and memory limits differ from the standard parser; configure and test the appropriate HTTP message reader. Read the Spring Framework docs on multipart and `DataBuffer` before building a large-file pipeline yourself.

## 9. Managing DataBuffers and Avoiding Direct Memory Leaks

On Netty-backed servers, `DataBuffer` can wrap pooled/reference-counted memory. At the DTO level, codecs normally manage buffer lifecycles. When handling **`Flux<DataBuffer>`** directly, you must track who **owns** each buffer and who is responsible for releasing it.

Rules:

1. Never access a `DataBuffer` after it has been released.
2. Never release twice, and never forget to release when your code is the consumer.
3. Never call **`DataBufferUtils.join(...)`** on an unbounded data source.
4. Never collect an entire buffer `Flux` via **`collectList()`** without strict bounds and cleanup handling.
5. On pipeline cancel or error, ensure buffers are discarded/released per the API contract.
6. Prefer Spring's streaming-to-disk APIs and codecs/utilities that already manage resource lifecycles properly.

Illustrative operator-level example:

~~~java
Flux<Integer> sizes = input.map(buffer -> {
    try {
        return buffer.readableByteCount();
    } finally {
        DataBufferUtils.release(buffer);
    }
});
~~~

**This is not a standalone program**: `input` must be a `Flux<DataBuffer>` whose ownership belongs to your code. Only release when your code finishes processing the buffer and does not pass ownership downstream. Verify cancellation paths and pooled buffers in real applications.

## 10. Memory Budget and Concurrent Load

Suppose you set the codec buffer limit to **2 MiB** and have **200 concurrent requests** decoding objects near that limit. Aggregation data alone could reach:

~~~text
200 × 2 MiB = 400 MiB
~~~

That figure is illustrative, **not the application's RAM ceiling**. You must also account for decoded Java objects, `String` copies, temporary buffers, Netty direct memory, caches, logs, business processing, and responses.

When changing the limit, measure:

- Valid payload sizes at p50/p95/p99 and real-world maxima.
- Concurrent request counts and the lifetime of each aggregation.
- Heap, off-heap/direct memory, garbage collection, and event-loop latency.
- `DataBufferLimitException` counts and HTTP 4xx/5xx rates.
- Whether data can be streamed instead of loaded into a DTO or collection.
- Gateway request limits, timeouts, file/part counts, and disk quotas.

A raised limit can pass single-request tests cleanly and still fail when hundreds of clients send large payloads concurrently.

## 11. Configuration Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Still seeing 256 KiB cap despite configuring property | Old property name or wrong active profile | Boot 3.5: check **`spring.http.codecs.max-in-memory-size`** |
| Server fails on large JSON | `Mono` DTO/String needs buffer above limit | Pick a sensible limit or switch to streaming |
| `WebClient` `bodyToMono` fails while server works | Client uses its own codec/config | Configure the right `WebClient.Builder` |
| NDJSON with many small records succeeds | Limit applies per record | Do not treat the limit as a total request-size cap |
| One overly long NDJSON line fails | Per-record buffer exceeds threshold | Cap per-record size or redesign payload |
| 1MB multipart file exceeds 256KB threshold without error | Threshold may spool files to disk | Set separate disk/total upload limits |
| HTTP status returns 500 instead of 413 | Exception unmapped along that path | Add error-handling policy and integration tests |
| Multiple large requests trigger OOM | High concurrency and allocations | Lower limits, cap concurrency, or stream |
| API uses `Flux` yet memory still climbs | `collectList`/`join` or cache retains everything | Avoid unbounded aggregation |
| `FilePart` saved with dangerous original filename | Path built from user filename | Generate server-side IDs and sanitize metadata |
| Heap looks fine but direct memory grows | Pooled `DataBuffer`s retained/leaked | Audit ownership, release, and cancellation paths |
| Relying only on `Content-Length` to cap body | Clients can use chunked/streaming transfers | Enforce actual byte limits at proxy and app |

### 11.1. Recommended Test Matrix

- 1 KiB JSON, JSON near 128 KiB, and 200 KiB JSON when the server limit is 128 KiB.
- Unicode/emoji input to verify **byte size** differs from `String.length()`.
- NDJSON with many small records and a test with one oversized record.
- Multipart with one small file, one file exceeding the memory threshold, and one exceeding the disk usage cap.
- Small/large `WebClient` responses with both manually built and Boot-injected clients.
- Multiple concurrent clients, cancelled requests, timeouts, and client disconnects.
- Requests omitting `Content-Length` or routed through a gateway, verifying which layer returns errors.
- Do not assert status codes alone; monitor heap/direct memory and temp file cleanup.

## 12. Production Checklist

- [ ] You know the exact Boot/WebFlux version and HTTP server runtime.
- [ ] You use the right property: **`spring.http.codecs.max-in-memory-size`** for Boot 3.5.
- [ ] You understand the **codec aggregation** limit is not a total request limit.
- [ ] You size the threshold from real valid payloads and concurrency, not blindly.
- [ ] You use streaming for large lists, NDJSON, files, or potentially unbounded sources.
- [ ] You do not disable the limit with **`maxInMemorySize(-1)`** without a safe boundary.
- [ ] Total request sizes, timeouts, rates, concurrent requests, and disk quotas are enforced at appropriate layers.
- [ ] Multipart part limits, file thresholds, disk caps, and temp directories are checked.
- [ ] Separate `WebClient` codec limits are configured for clients not auto-configured by Boot.
- [ ] `DataBuffer`s are released according to ownership and cancellation contracts.
- [ ] `DataBufferLimitException` and HTTP status/error contracts are covered by tests.
- [ ] Logs, metrics, heap, direct memory, and failures are monitored under load.

## 13. Official References

1. Spring Boot 3.5 – Common Application Properties (**`spring.http.codecs.max-in-memory-size`** and **`spring.webflux.multipart`**): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
2. Spring Framework 6.2 – WebFlux Config, **`ServerCodecConfigurer`**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
3. Spring Framework – WebFlux Reactive Core, **Limits**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
4. Spring Framework – WebClient Configuration/MaxInMemorySize: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
5. Spring Framework – Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
6. Spring Boot 3.5 – Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
7. Spring Framework – Multipart Content: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html

## 14. Summary

In WebFlux, HTTP data can be received as a stream, yet codecs still have to **buffer a certain number of bytes** when decoding a single value. The **`maxInMemorySize`** limit—commonly defaulting to around **256 KiB** across many codecs—catches oversized aggregations via **`DataBufferLimitException`**.

On **Spring Boot 3.5**, use **`spring.http.codecs.max-in-memory-size`** or direct codec configuration to tune the cap. **Codec limits do not replace HTTP request limits, multipart file limits, concurrency caps, or process-wide RAM budgets**. Use objects/`Mono` for small payloads, `Flux` streaming for multi-record streams, `FilePart`/`PartEvent` for uploads, and proper `DataBuffer` lifecycle management to keep reactive applications stable under load.