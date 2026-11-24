# Controlling Buffering and DataBufferLimitException Errors in Spring WebFlux

In **Spring WebFlux**, HTTP bodies typically flow through reactive components such as `Flux<DataBuffer>`, `HttpMessageReader`, `Decoder`, `HttpMessageWriter`, and `Encoder`. This mechanism can process data as a stream, yet it **does not guarantee that every body is decoded without buffering data in memory**.

When a codec must accumulate multiple bytes to construct a complete Java value, Spring may enforce a **maxInMemorySize** limit. If the amount of data retained in memory exceeds the threshold, you can encounter **`org.springframework.core.io.buffer.DataBufferLimitException`**.

Understanding this goes beyond merely increasing a configuration number. Developers must distinguish:

1. **Codec aggregation limit**: the amount of data a matching reader/decoder is allowed to buffer in memory.
2. **HTTP request body size limit**: total bytes a client is permitted to send in one request.
3. **Streaming/backpressure**: consuming data incrementally and regulating downstream demand.
4. **Resource ownership**: who is responsible for releasing a `DataBuffer`, especially when using Netty pooled buffers.
5. **Server and WebClient**: the error can arise both when the server reads a request **and** when a reactive HTTP client reads a response.

**Key takeaway:** `maxInMemorySize` is an **in-memory aggregation limit for certain codecs**; it is **not a global cap** on total HTTP request size, does not replace reverse-proxy protections, and does not turn an endpoint that buffers the entire body into a streaming one merely because it returns `Mono`.

## 1. What Is a DataBuffer?

`DataBuffer` is Spring's abstraction for a byte region. In WebFlux, an HTTP server/client can emit or receive a stream of `DataBuffer`s instead of requiring the entire content up front.

~~~text
HTTP request body 40 KiB
         |
         v
Netty receives byte chunks from network
         |
         v
Flux<DataBuffer>
  |-- chunk A
  |-- chunk B
  |-- chunk C
  |-- ...
         |
         +--> read/write as a stream if the API supports it
         |
         +--> decoder aggregates bytes to construct an Object
                    |
                    v
              Check limit
              maxInMemorySize
                    |
             +------+------+
             |             |
           <= limit     > limit
             |             |
          Decode       DataBufferLimitException
~~~

The size of each chunk is not a fixed API contract: an HTTP request can arrive in varying buffer sizes depending on transport, backpressure, and arrival timing.

**Buffer implementations can vary.** Reactor Netty can use Netty-based pooled buffers; in that case, holding or releasing references improperly can raise memory usage or trigger use-after-release errors. When using `@RequestBody DTO` with default codecs, the framework generally manages buffer lifecycles for you. When manipulating `Flux<DataBuffer>` directly, you must clearly understand ownership and lifecycle rules.

## 2. Why Does WebFlux Still Need Buffering Sometimes?

WebFlux supports non-blocking I/O, yet an HTTP body can represent **a complete JSON object**, a plain text string, or a structure that must be fully parsed before building a Java object.

Example:

~~~http
POST /api/profile HTTP/1.1
Content-Type: application/json

{"name":"Lan","description":"... thousands of characters ..."}
~~~

The controller may be written as:

~~~java
@PostMapping("/api/profile")
Mono<Profile> create(@RequestBody Mono<Profile> body) {
    return body;
}
~~~

This is a fragment requiring `Profile` and annotation imports. Even though the controller receives `Mono<Profile>`, **the JSON decoder still has to receive enough content to instantiate `Profile`**. If the codec needs to aggregate beyond the threshold, the request can fail before the controller ever sees a `Profile` object.

Similarly, in an HTTP client:

~~~java
Mono<String> entireResponse = webClient.get()
        .uri("/large-text")
        .retrieve()
        .bodyToMono(String.class);
~~~

This is a fragment assuming a pre-configured `webClient`. `bodyToMono(String.class)` expresses the intent to receive **the entire response as a single string**. When the response is large, the matching codec may have to retain significant data in memory and exceed `maxInMemorySize`.

**Reactive does not mean zero-memory:** results that must be materialized as a single complete object or string incur memory overhead proportional to their size. Reducing aggregation requires changing data design and processing patterns, not merely switching the return type from `String` to `Mono<String>`.

## 3. What Error Is DataBufferLimitException?

The full exception name is:

~~~java
org.springframework.core.io.buffer.DataBufferLimitException
~~~

It indicates that a buffer processing/decoding operation **exceeded the maximum number of bytes allowed to be held in memory** for that operation. A typical message looks like:

~~~text
Exceeded limit on max bytes to buffer : 262144
~~~

The line above is an **example message only**, not fixed text across Spring versions, nor do all environments default to 262144 bytes. **262144 bytes equals 256 KiB**.

The error can occur when:

- A WebFlux server reads a JSON request via a decoder that must aggregate the body into an object.
- A `WebClient` reads a large response via `bodyToMono(String.class)`, DTO, or byte array.
- Reading certain form/multipart parts or content types requiring aggregation via codecs.
- Application code explicitly calls `DataBufferUtils.join(..., maxByteCount)` with a `maxByteCount` cap.
- A custom reader/decoder accumulates data into buffers while enforcing a limit.

The error **does not necessarily mean the total request `Content-Length` is too large**. Some codecs limit the size of **each item** or each part being aggregated; exact accounting depends on the codec, format, and framework version.

A body larger than the threshold can still stream cleanly if no step must buffer more than that threshold at once. Conversely, a body smaller than the proxy's total HTTP cap can still trip the codec's aggregation limit.

### 3.1. Do Not Confuse with OutOfMemoryError

`DataBufferLimitException` is a **protective rejection of excessive buffering** before memory grows unboundedly for a specific operation. It does not mean the JVM has run out of heap.

`OutOfMemoryError` is a runtime memory exhaustion failure and is far more severe. Raising `maxInMemorySize` blindly to "make DataBufferLimitException go away" can overload heap/direct memory and lead to GC thrashing or a real OOM.

## 4. maxInMemorySize: Defaults and Scope

In many Spring WebFlux / Spring Framework 6.x configurations, a common default threshold for codecs that aggregate is **256 KiB** (262144 bytes). **Do not treat this number as immutable**: defaults, specific codecs, and how Spring Boot applies them can vary by version or custom configuration.

`maxInMemorySize` typically applies to:

- Certain text/JSON decoders and default codecs in `ServerCodecConfigurer`.
- Default codecs in `ClientCodecConfigurer` used by `WebClient`.
- Multipart or specialized format paths, subject to their own limits and rules.
- Certain buffer-joining methods when callers supply `maxByteCount`.

It is **not**:

- An overall size limit for every HTTP request arriving at the server.
- A mandatory file upload cap across all multipart mechanisms.
- The maximum total bytes a `Flux<DataBuffer>` is ever permitted to emit over its lifetime.
- A JVM heap limit or Netty direct memory cap.
- A limit on `Flux` element counts or concurrent requests.

When changing the threshold, check **which codec actually reads the body**. If code consumes `DataBuffer` directly or uses a custom codec outside the default configurer, the global property may not protect that path.

## 5. Configuring the Server via application.yml

In **Spring Boot 3.x**, the standard way to adjust the buffer limit for Boot-managed WebFlux codecs is:

~~~yaml
spring:
  codec:
    max-in-memory-size: 512KB
~~~

Here `512KB` is an illustrative configuration value, not a universal recommendation. Spring Boot parses this value as a `DataSize`; use explicit units (`KB`, `MB`) to avoid confusion with raw bytes.

For example, to set a low threshold to test the error in development:

~~~yaml
spring:
  codec:
    max-in-memory-size: 8KB

server:
  port: 8080
~~~

When a codec processes a JSON object exceeding this small threshold, you can observe `DataBufferLimitException` in logs or the error chain. After testing, choose production limits based on valid payload sizes, concurrency, and memory budgets.

**Do not assume `8KB` blocks every HTTP request larger than 8 KB.** For instance, an endpoint consuming raw chunks directly can bypass aggregation under this threshold, while multipart uploads follow separate configurations and behavior.

### 5.1. Separating Configuration by Profile

A system may have larger production payloads than dev environments:

~~~yaml
# application-prod.yml
spring:
  codec:
    max-in-memory-size: 1MB
~~~

Profiles manage per-environment requirements, not as an excuse to raise limits to dodge performance bottlenecks. Align with proxy, container, downstream, and API contract limits so clients do not hit 413 at the proxy even when the application permits more.

### 5.2. Do Not Overlap Properties and Customizers

If `spring.codec.max-in-memory-size`, a custom `WebFluxConfigurer`, and a custom `ServerCodecConfigurer` all modify the same setting, the final value can depend on application order. Pick one primary source of truth and write tests verifying effective behavior.

## 6. Configuring in Java: ServerCodecConfigurer

When programmatic customization is required, Spring WebFlux provides `WebFluxConfigurer#configureHttpMessageCodecs(ServerCodecConfigurer)`:

~~~java
package demo.buffer;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
class BufferCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

This is a complete Java class inside a project with Spring WebFlux and component scanning enabled. `512 * 1024` equals **524288 bytes** (512 KiB).

- `defaultCodecs()` configures the default codec group registered by Spring.
- `maxInMemorySize(...)` adjusts the limit for default codecs supporting this setting.
- Not every custom codec automatically inherits this value.
- Registering other codecs can change the decoding path.

**This is an alternative to `spring.codec.max-in-memory-size` above**, not something you must use together. Never add `@EnableWebFlux` just to change the threshold: that annotation can alter the scope of WebFlux auto-configuration managed by Spring Boot.

You do not need to clear the codec list or disable defaults with `registerDefaults(false)` to change the buffer limit.

## 7. Runnable Java 17+ Example: Echo JSON, Large Body, and NDJSON

This example uses **Spring Boot 3.x**, **Java 17+**, the **WebFlux** web stack, and Reactor Netty by default. Create a Gradle project with the Spring Boot plugin/dependency management and add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

**Do not add `spring-boot-starter-web` in this example**, because when both MVC and WebFlux are present, Spring Boot typically infers a Servlet web application by default.

File **src/main/java/demo/buffer/BufferDemoApplication.java**:

~~~java
package demo.buffer;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class BufferDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BufferDemoApplication.class, args);
    }
}

record EchoPayload(String content) {
}

@RestController
class BufferDemoController {

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<EchoPayload> echo(
            @RequestBody Mono<EchoPayload> body) {
        return body;
    }

    @GetMapping(
            path = "/api/large-text",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    Mono<String> largeText() {
        return Mono.fromSupplier(() -> "A".repeat(32 * 1024));
    }

    @GetMapping(
            path = "/api/events",
            produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    Flux<Map<String, Integer>> streamEvents() {
        return Flux.range(1, 1000)
                .map(index -> Map.of("index", index));
    }
}
~~~

Configuration **src/main/resources/application.yml** for learning purposes:

~~~yaml
spring:
  codec:
    max-in-memory-size: 8KB

server:
  port: 8080
~~~

**Do not put `BufferCodecConfiguration` from section 6 into this demo project at the same time**, as it would override the 8 KB limit we want to test. Those two configurations are simply two alternative learning options.

### 7.1. Reading the Example

- `POST /api/echo`: reads a JSON object into `EchoPayload`. During decoding, the body requires aggregation, making the 8 KB cap useful for reproducing the limit error.
- `GET /api/large-text`: creates a 32 KiB string and returns it as `text/plain`. The server writes the response; having a client attempt to **read the whole** response as a `String` is ideal for observing client-side buffer limits.
- `GET /api/events`: emits a `Flux` of 1000 individual items as NDJSON. Each JSON line is encoded as the publisher emits each element, rather than assembling one huge JSON array string in memory.

**Subtle point:** `Mono<EchoPayload>` does not automatically make JSON decoding stream field-by-field; it represents one target object. Meanwhile, `Flux<Map<...>>` with NDJSON allows emitting multiple records without having to aggregate the entire stream into one object.

### 7.2. Start and Send a Small Body

Use the project's Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows, use `gradlew.bat bootRun`. In another terminal:

~~~bash
curl -i http://localhost:8080/api/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"content":"hello"}'
~~~

In this exact demo project without filters/security altering behavior, the small request returns **200 OK** and an equivalent JSON body:

~~~json
{"content":"hello"}
~~~

Field/header ordering and JSON formatting can vary by codec; for the single-field payload in this example, the value `hello` must be preserved.

### 7.3. Reproducing a JSON Object Exceeding 8 KB

Create **make_payload.py** to generate a long JSON object:

~~~python
import json
from pathlib import Path

payload = {"content": "x" * 16384}
Path("large.json").write_text(
    json.dumps(payload), encoding="utf-8"
)
print("large.json created")
~~~

Run:

~~~bash
python3 make_payload.py
~~~

Then:

~~~bash
curl -i http://localhost:8080/api/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary @large.json
~~~

When the decoder enforces the 8 KB cap on the aggregated JSON value, this request trips the limit before constructing `EchoPayload`. Inspect **server logs and the exception cause chain** to confirm `DataBufferLimitException`.

**Do not guarantee the default HTTP status is always 413**: depending on where the exception occurs, Spring Boot version, WebFlux exception handling, and wrapper exceptions, clients may receive another status. To return 413 consistently, implement explicit size-limit policy and error mapping verified by integration tests.

### 7.4. Observing NDJSON

Example:

~~~bash
curl -N -H 'Accept: application/x-ndjson' \
  http://localhost:8080/api/events
~~~

The response is one JSON line per `index`; the first two lines look like:

~~~text
{"index":1}
{"index":2}
~~~

The stream emits up to index 1000 as long as the client keeps reading without errors/cancellation. Flag `-N` disables curl's output buffering for observation, though it **does not guarantee each element maps to one TCP packet**. Reverse proxies or transports may buffer/coalesce chunks differently.

## 8. WebClient Limits Differ from Server Limits

`DataBufferLimitException` can happen even when the server works normally. For example, `WebClient` calls an API returning a long response and executes:

~~~java
Mono<String> text = webClient.get()
        .uri("/api/large-text")
        .retrieve()
        .bodyToMono(String.class);
~~~

This fragment requires a `webClient` bean and proper base URL. `bodyToMono(String.class)` asks to decode the body into a single `String`. If the client codec's cap is smaller than the response body, the reactive pipeline can terminate with `DataBufferLimitException` (potentially wrapped inside another exception along some paths).

**Identify which side triggered the error:**

| Location | What Is Happening | Where to Check First |
|---|---|---|
| WebFlux server receiving JSON | Decoder reading `@RequestBody` | Server codec config, API payload, logs |
| `WebClient` reading large String/DTO | Client decoder aggregating response | `WebClient` codec config, response size |
| Multipart upload | Reader processing form/parts | Multipart config, file/part limits, temp disk |
| Custom reactive processing | `DataBufferUtils.join` or custom accumulator | Aggregation logic, `maxByteCount`, buffer ownership |
| Proxy/ingress | Proxy rejects oversized request | Proxy request-size limit, 413 response |

If **`WebClient`** hits the limit, raising the server's `ServerCodecConfigurer` will not fix the client error. Conversely, raising the client limit does not help the server decode an oversized inbound JSON object.

### 8.1. Configuring a Dedicated WebClient

In Spring Framework 6.x / Spring Boot 3.x, codecs can be configured for one specific `WebClient`:

~~~java
package demo.buffer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class PartnerClientConfiguration {

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://partner.example.test")
                .codecs(configurer -> configurer.defaultCodecs()
                        .maxInMemorySize(2 * 1024 * 1024))
                .build();
    }
}
~~~

In this example, `2 * 1024 * 1024` equals **2 MiB**. The base URL is a placeholder hostname, not a live service to call. Defining the bean makes no network requests at startup.

If using the Spring Boot-managed `WebClient.Builder`, the builder may already include Boot customizers/auto-configuration. The code above explicitly sets the limit for this client, though you should check whether later customizers override it. Avoid raising the limit for **every `WebClient`** if only one partner API returns exceptionally large payloads.

### 8.2. Should the Client Aggregate or Stream the Body?

| Response Reading Method | Characteristics |
|---|---|
| `bodyToMono(String.class)` | Needs entire response as one `String` |
| `bodyToMono(MyDto.class)` | Needs enough data to decode the matching object |
| `bodyToMono(byte[].class)` | Allocates a byte array holding the content |
| `bodyToFlux(MyDto.class)` with NDJSON | Can decode item-by-item per codec/media type |
| `bodyToFlux(DataBuffer.class)` | Lets you process each buffer; requires careful ownership management |

If your goal is downloading a large file to disk, avoid `bodyToMono(byte[].class)` just to call `Files.write(...)`, because that holds every byte in RAM before writing.

A streaming download fragment using `WebClient`:

~~~java
Mono<Void> download = webClient.get()
        .uri("/archive.bin")
        .retrieve()
        .bodyToFlux(DataBuffer.class)
        .as(buffers -> DataBufferUtils.write(buffers, targetPath));
~~~

This snippet requires `webClient`, `targetPath`, and imports for `DataBuffer` and `DataBufferUtils`. It is a fragment and will not run standalone since `targetPath` and the client are undeclared. `DataBufferUtils.write(Publisher<DataBuffer>, Path, ...)` in Spring Framework 6.x writes buffers incrementally to disk and handles releasing per its API contract; validate safe paths, write permissions, disk quotas, error/cancellation handling, and library version. Never construct paths directly from URLs or user-supplied filenames.

**Streaming is not free:** network bandwidth, disk I/O, encode/decode CPU, file descriptors, and concurrent requests remain bounded resources.

## 9. DataBufferUtils.join: A Common Source of Large Buffers

A frequent anti-pattern:

~~~java
Mono<DataBuffer> wholeBody = DataBufferUtils.join(body);
~~~

`body` is a hypothetical `Flux<DataBuffer>`. This call aims to **join all buffers into a single DataBuffer**. If the source is huge, having no cap creates severe memory pressure; another overload accepts a maximum cap:

~~~java
Mono<DataBuffer> boundedBody =
        DataBufferUtils.join(body, 512 * 1024);
~~~

The limit above is 512 KiB. If exceeded, the operation emits `DataBufferLimitException`; on success, you must still understand how to release the returned buffer after consumption per `DataBufferUtils.join`'s ownership contract.

**Never "fix" the error by switching to unbounded `join(body)`.** That merely trades a controlled exception for unbounded memory accumulation.

If business logic only needs chunk-by-chunk processing, use a streaming pipeline. If it must parse a single object, decide the maximum allowed object size, enforce that cap, and return a clear error response.

## 10. Reading and Releasing Pooled DataBuffers

Netty can use `PooledDataBuffer` with reference counting. When writing custom operators, developers must know who owns the buffer in every branch.

**Key principles:**

1. Never hold a reference to a buffer after the owner releases it.
2. Never call release twice if the API/framework already manages it.
3. If you consume a buffer yourself without handing ownership to the framework/next operator, release it per the API contract.
4. When calling `DataBufferUtils.join`, release the resulting buffer after processing it.
5. On pipeline error, cancellation, or discard, ensure owned buffers are not leaked.
6. Prefer `FilePart.transferTo`, framework codecs, and `DataBufferUtils.write` instead of reimplementing low-level buffer/file logic.

A fragment processing a buffer and releasing it in `finally`, **only appropriate when your code genuinely owns the buffer at that stage**:

~~~java
.map(buffer -> {
    try {
        int remaining = buffer.readableByteCount();
        return remaining;
    } finally {
        DataBufferUtils.release(buffer);
    }
})
~~~

This fragment requires a `DataBuffer` stream and imports. Do not copy this release pattern blindly into arbitrary `doOnNext` hooks or framework codecs if downstream operators still expect to read the buffer.

### 10.1. When to Use doOnDiscard?

Certain operators discard elements upon cancellation, errors, or filtering. In pipelines with appropriate ownership, Spring/Reactor supports cleanup hooks like `doOnDiscard(DataBuffer.class, DataBufferUtils::release)`. However, cleanup must be placed carefully where the buffer has not already been released on another path; never treat a global hook as a magic cure for all leaks.

### 10.2. Direct Memory and Heap

With Netty pooled/direct buffers, memory usage does not behave like normal heap objects. A generous heap limit will not save you if direct memory or pooled buffers leak. Monitor heap, direct/native memory, GC, and Netty allocator metrics when instrumented.

## 11. Multipart Uploads and Separate Limits

A multi-megabyte file upload does not need to reside wholly in heap memory. Spring WebFlux offers the `FilePart` API and multipart reader settings to handle parts/files with bounded memory and disk spillover.

Example controller fragment:

~~~java
@PostMapping(
        path = "/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<String> upload(@RequestPart("file") FilePart file) {
    Path destination = Path.of("/srv/app-uploads")
            .resolve(java.util.UUID.randomUUID() + ".bin");

    return file.transferTo(destination)
            .thenReturn("stored");
}
~~~

This is a fragment requiring imports for `FilePart`, `Path`, Reactor `Mono`, annotations, and **an existing writable destination directory**. Never pass client-supplied `file.filename()` directly into paths due to path traversal, overwrites, or invalid filenames. Always enforce quotas, authentication, content validation, and file limits.

**Do not confuse:** `spring.codec.max-in-memory-size` is just one piece; multipart readers can have separate limits for file parts, form fields, part counts, and memory/temp disk thresholds. Exact property names and behavior vary across Spring Boot/Spring Framework versions, so verify against your deployed version.

Establish limits for **total upload size**, **per-file size**, **part count**, **disk usage**, **upload duration**, and **concurrency**, combining proxy/server settings and multipart readers. Never think raising `maxInMemorySize` solves all large upload scenarios.

## 12. Choosing a Streaming-Friendly JSON Structure

There is an important difference between a **JSON array** and **NDJSON**.

JSON array:

~~~json
[{"id":1},{"id":2},{"id":3}]
~~~

NDJSON:

~~~text
{"id":1}
{"id":2}
{"id":3}
~~~

When an endpoint returns `Flux<Item>`, streaming element by element works well with `application/x-ndjson` because each line is an independent JSON value. However:

- Codecs may still bound the size of **each element** or value being aggregated.
- One gigantic JSON element can still exceed the limit even when the outer stream streams line by line.
- Clients must support the streaming format and proper backpressure.
- Proxies, TLS layers, and HTTP transports may buffer/coalesce chunks.
- Do not promise each item always arrives instantaneously at the client upon server emission.

A WebFlux pattern:

~~~java
@GetMapping(
        path = "/events",
        produces = MediaType.APPLICATION_NDJSON_VALUE
)
Flux<Event> stream() {
    return eventService.events();
}
~~~

This fragment requires `Event`, `eventService`, and imports. When an API contract mandates a single huge structured JSON object, you cannot unilaterally swap it to NDJSON without coordinating with clients.

## 13. DataBufferLimitException and HTTP 413

`DataBufferLimitException` **is not itself an HTTP status code**. It is an exception thrown during buffer processing. On the server, the resulting HTTP status depends on where it is thrown, outer wrapper exceptions, WebFlux error handlers, and whether the response is already committed.

### 13.1. Three Cases to Distinguish

- **Proxy returns 413:** the request may never reach Spring Boot. Increasing app codec limits will not change proxy limits.
- **WebFlux decoder throws `DataBufferLimitException`:** the request reached the codec and exceeded the aggregation cap. Do not assume clients get 413 without explicit mapping and tests.
- **`WebClient` decoder throws `DataBufferLimitException`:** your application is acting as an **HTTP client**; this is a client-side pipeline failure reading a response, not an HTTP 413 from the target server.

For a consistent API contract, you can explicitly handle `DataBufferLimitException` dispatched to error resolvers:

~~~java
@RestControllerAdvice
class BodySizeAdvice {

    @ExceptionHandler(DataBufferLimitException.class)
    ResponseEntity<Map<String, String>> tooLarge(
            DataBufferLimitException ex) {
        return ResponseEntity
                .status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("error", "payload_too_large"));
    }
}
~~~

This illustrative class requires imports for `RestControllerAdvice`, `ExceptionHandler`, `ResponseEntity`, `HttpStatus`, `DataBufferLimitException`, and `Map`. **There is no guarantee every codec failure dispatches under this exact exception class:** some decode paths wrap errors inside `ServerWebInputException` or other exceptions. Design proper error handling and verify with real tests to guarantee 413 responses. Never map all `ServerWebInputException` instances to 413, as JSON syntax/validation errors are normally not oversized payloads.

If the response has already committed or streaming already flushed partial bytes, changing the HTTP status to 413 is generally impossible. Therefore enforce size checks as early as possible on endpoints prone to large bodies.

### 13.2. 413 Does Not Replace Input Validation

Even when a request stays under codec limits, it can still contain unusually deep JSON, huge text fields within budget, or business-invalid data. Combine:

- DTO and business value validation.
- Content-Type allowlists and explicit API contracts.
- Global request size caps at infrastructure layers.
- Concurrency/rate limits to curb resource exhaustion.
- Timeouts and connection limits.
- Error handling that never leaks stack traces to clients.

## 14. Automated Testing for Buffer Limits

Two testing levels matter:

1. **Small-app behavior:** valid JSON below the threshold succeeds; payloads above the threshold are rejected per the designed error policy.
2. **Real HTTP path:** test with an embedded server and HTTP client to verify server codecs, any real proxies, and client codecs.

In Spring Boot 3.x, use `spring-boot-starter-test`. WebFlux tests use `WebTestClient`, distinguishing context-bound test clients from real HTTP calls over a live server.

Illustrative test using **`WebTestClient.bindToApplicationContext(...)`** without relying on auto-injected clients:

~~~java
package demo.buffer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class BufferDemoApplicationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void smallJsonBodyStillWorks() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(context)
                .configureClient()
                .build();

        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoPayload("ok"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.content").isEqualTo("ok");
    }
}
~~~

The test file lives at **src/test/java/demo/buffer/BufferDemoApplicationTest.java** in the **same project** as `BufferDemoApplication`. The correct package for `WebTestClient` is `org.springframework.test.web.reactive.server.WebTestClient`. Because it uses `bindToApplicationContext`, it does not open an HTTP port; it is an in-process WebFlux handler integration test.

Add to `build.gradle`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Run:

~~~bash
./gradlew test
~~~

When testing over-limit rejections, account for your active error handling: without a standardized status mapping, **do not hard-assert 413** when the framework might return another status. The rigorous approach is adding explicit error mapping for that exception path and asserting status/body with end-to-end HTTP tests.

### 14.1. When Testing Dedicated WebClient Limits

Do not merely send a large payload to the server and assume client codecs are bounded. A server may validly emit a large response while **the client itself** fails to decode it into a `String`. For client tests, configure `WebClient.builder().codecs(...maxInMemorySize(...))`, read the response, and inspect the error cause chain. Avoid calling `block()` on an event-loop thread—when calling `block()` on the JUnit thread to observe errors, ensure tests do not deadlock the server pipeline and properly release resources.

## 15. Why Not Immediately Raise the Limit to Tens of MBs?

Suppose a single JSON request can buffer 20 MiB and 100 requests aggregate concurrently. Intermediate buffer data alone consumes substantial memory, alongside decoded Java objects, request metadata, network buffers, and related structures. Total memory cannot be computed by naive multiplication, yet the memory spike risk is real.

Before raising the cap, answer:

1. **What is the maximum valid payload?** Just because a client accidentally sends 50 MB does not mean the API should accept it.
2. **Can the contract switch to upload/streaming?** Files or event streams rarely belong inside a single JSON string.
3. **How many concurrent requests occur?** Per-request max size multiplied by concurrency drives peak usage.
4. **How much memory is allocated to the pod/JVM?** Heap, direct memory, thread stacks, and OS all share resources.
5. **Is there a proxy limit?** If the proxy rejects first, tuning Spring codecs changes nothing.
6. **Are there custom decoders or `DataBufferUtils.join` calls?** Global properties may not govern them.
7. **Is a client aggregating responses?** If the failure is in `WebClient`, do not reconfigure the server.
8. **Are there benchmarks/metrics?** Measure p95/p99, GC, and buffer allocations instead of guessing.

A sound limit comes from **payload contracts and memory budgets**, not the habit of setting an arbitrarily high value.

## 16. Distinguishing maxInMemorySize from Backpressure

Reactive Streams provide **backpressure**: downstream signals demand to regulate how many items upstream emits where supported. However, backpressure does not replace size limits:

- A 10 MiB JSON element is still one item, even if the subscriber requests exactly 1 item.
- A `Mono<String>` emits one item, yet that value can be huge.
- A `Flux<DataBuffer>` can stream gigabytes across many buffers, provided throughput and storage resources are controlled.
- Upstream sources not supporting backpressure may require buffering, dropping, or error policies.
- Decoders may still need to aggregate enough bytes to materialize a single object.

Therefore, **backpressure regulates item flow rate**, whereas **`maxInMemorySize` caps in-memory buffering for specific operations**. Both are needed when handling large streaming payloads.

## 17. Step-by-Step Error Investigation

When seeing `DataBufferLimitException` in logs:

1. **Locate the source:** WebFlux server decoding a request, `WebClient` decoding a response, or custom `DataBufferUtils.join`?
2. **Read the exception chain:** is it wrapped inside `ServerWebInputException`, `DecodingException`, or another client exception?
3. **Identify media type and Java type:** JSON object, `String`, `byte[]`, multipart part, NDJSON stream, or custom format?
4. **Measure actual sizes:** total HTTP payload, individual JSON value/part size, decoded object footprint, and buffer usage.
5. **Check effective limits:** `spring.codec.max-in-memory-size`, `WebFluxConfigurer`, `ServerCodecConfigurer`, dedicated `WebClient`, custom codecs.
6. **Check infrastructure:** reverse proxy, CDN, ingress, load balancer, HTTP request size caps, and timeouts.
7. **Evaluate design:** can the endpoint switch from `bodyToMono(byte[].class)` to file streaming?
8. **If the limit must increase:** raise it based on measurements using max valid payloads, test under concurrency, and watch memory.
9. **Add regression tests:** small body succeeds; over-limit body fails cleanly; streaming works.
10. **Monitor production:** heap/direct memory, GC, 4xx/5xx rates, payload sizes, and timeouts.

In systems with Micrometer/Actuator, you can observe HTTP server/client metrics; Netty buffer and allocator metrics require explicit instrumentation/support. Do not assume every environment exposes those metrics automatically.

## 18. Common Design Mistakes

### Mistake 1 — Treating maxInMemorySize as a Global Request Cap

Incorrect. It applies to aggregation inside specific codecs. To cap all HTTP request bodies, configure proxy/server/ingress limits and matching validation.

### Mistake 2 — Raising the Limit to 100MB Just to Silence Exceptions

This turns controlled rejections into memory pressure or OOMs. Verify valid payload sizes and concurrency; consider streaming.

### Mistake 3 — Changing Server Properties When the Error Is in WebClient

`WebClient` uses client codecs. If responses are too big for `bodyToMono(String.class)`, inspect client codecs or change how responses are read. Server decoder limits do not fix client-side over-aggregation.

### Mistake 4 — Switching Mono<String> to Flux<String> While Still Building One Huge String

If the source already materializes one giant String, changing the publisher type does not stream chunks. The design must emit real chunks/records with a suitable media type.

### Mistake 5 — Calling Unbounded DataBufferUtils.join

`join` means aggregation; omitting `maxByteCount` dodges the limit exception while leaving memory unprotected. Use the bounded overload or avoid joining when streaming suffices.

### Mistake 6 — Forgetting to Release Pooled DataBuffers in Custom Code

Can leak direct memory. Use Spring lifecycle operators and release strictly according to ownership; avoid double-release.

### Mistake 7 — Treating Multipart Uploads and JSON Bodies Identically

Multipart uses distinct limits and processing paths, potentially backed by disk storage. Use `FilePart.transferTo` where suitable and configure per-part/file caps rather than wrapping huge files in JSON/base64.

### Mistake 8 — Assuming Every DataBufferLimitException Returns 413

The exception may be wrapped, occur on client or server, or happen after response commit. Test real HTTP statuses alongside error handlers.

### Mistake 9 — Checking Only the HTTP Response Code

Ignoring heap/direct memory, concurrency, logs, and GC misses the consequences of raising limits. Measure resources and latency too.

### Mistake 10 — Letting Untrusted Filenames Determine Upload Paths

Risks path traversal and file overwrites. Generate server-side names, restrict target directories, enforce auth, and apply quotas.

### Mistake 11 — Logging Full Bodies to Debug Buffer Errors

Large bodies bloat logs and expose sensitive data. Log payload size, media type, route, request ID, and concise error context; never log passwords or tokens.

### Mistake 12 — Testing Only Small Bodies

After adjusting limits or codecs, test payloads right at the limit, over the limit, and under concurrent requests. Also test client response decoding and multipart uploads if used.

## 19. Pre-Production Configuration Checklist

- Confirm whether WebFlux/Reactor Netty or the Spring MVC Servlet stack is running.
- Pinpoint the origin of `DataBufferLimitException`: server decoder, `WebClient` decoder, or custom buffer aggregation.
- Understand `maxInMemorySize` as an in-memory aggregation cap, **not** a total HTTP upload size limit.
- Set limits based on API contracts, memory budgets, and concurrency rather than raising unboundedly.
- Configure `spring.codec.max-in-memory-size` or `ServerCodecConfigurer.defaultCodecs().maxInMemorySize(...)` deliberately.
- For specific `WebClient`s, prefer `WebClient.Builder.codecs(...)` instead of altering all server codecs.
- Use streaming/NDJSON for large record sets when clients and API contracts support it.
- For large file uploads, use multipart/`FilePart.transferTo` and quotas instead of buffering entire files in `byte[]`.
- Never call unbounded `DataBufferUtils.join` on untrusted bodies; follow `DataBuffer` ownership/release contracts.
- Test actual 413/error mapping responses rather than inferring them from exception names.
- Enforce proxy/ingress limits, timeouts, rate/concurrency caps, and input validation.
- Test small bodies, over-limit bodies, large `WebClient` responses, streaming, cancellation, concurrency, and memory metrics.
- Protect logs and client error bodies from leaking stack traces or private data.

**Conclusion:** `DataBufferLimitException` signals that an **in-memory buffering step exceeded its threshold** in WebFlux or a related pipeline. A durable fix identifies **who is aggregating data and why**, picks sensible server/client limits, switches to streaming where feasible, respects buffer ownership lifecycles, and verifies HTTP/error/memory behavior. Raising `maxInMemorySize` is merely a config tweak, not a substitute for safe payload design and resource limits.
