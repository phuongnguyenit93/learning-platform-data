# Fully Consuming or Releasing Discarded Request Content in Spring WebFlux

> **Module:** Spring Framework – reactive · **Parent topic:** Forms and files. This lesson explains the request body lifecycle when a filter, controller, or multipart handler decides to ignore part or all of the data. The focus is on distinguishing consume, relay, and release; properly handling `DataBuffer`, `Part`, and `PartEvent`; and testing to detect forgotten body content.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why the request body in WebFlux is a reactive stream that can typically only be read once.
2. Distinguish consume, relay, and release when the application does not need the content.
3. Consume an entire `Flux<DataBuffer>` without buffering the whole body into memory.
4. Release pooled `DataBuffer` instances promptly and handle buffers dropped by `filter`, `skip`, errors, or cancellation.
5. Know when to use `DataBufferUtils.release`, `retain`, `join`, and `doOnDiscard`.
6. Handle URL-encoded forms, multipart maps, and multipart streaming with `PartEvent`.
7. Drain the body inside a `WebFilter` when short-circuiting before the controller.
8. Write HTTP integration tests for raw bodies, multipart requests, and subsequent requests after a body is rejected.

**Rule:** when the application takes ownership of a `DataBuffer` or a `PartEvent` containing a buffer, the application must consume it, transfer ownership to another consumer, or release its content. Calling `.then()` alone to ignore elements does not release buffers automatically.

## 2. Why Must the Request Body Be Handled to Completion?

In WebFlux, the request body is represented as a `Publisher`/Reactor `Flux` or `Mono`. At the lower level, the body is typically a sequence of `DataBuffer` instances emitted by the server connector on demand (backpressure). A `DataBuffer` can wrap pooled memory, especially when running on Reactor Netty.

~~~text
Client sends bytes
      |
      v
HTTP server / connector
      |
      v
Flux<DataBuffer>
      |
      +---- HttpMessageReader / codec
      |          |
      |          v
      |       DTO / String / PartEvent
      |
      +---- Controller / functional handler
      |
      +---- Filter may short-circuit
                 |
                 v
       Consume / Relay / Release
~~~

An endpoint might return 401, 413, or 415 before reading the full body. A multipart handler might only need a `name` field and ignore a file part. A stream might stop at the first element. Every one of these branches must have clear rules for the remaining content.

If buffers are forgotten, pooled memory may not be returned to the pool, leading to memory leaks or `OutOfDirectMemoryError` under load. If the request stream is not completed, the server connector may have to drain it or close the connection; keep-alive behavior and socket resources depend on the connector/protocol. Never assume every connector automatically cleans up body content ignored by the application.

### 2.1. Three Valid Ways to Handle Content

| Approach | Meaning | Example |
| --- | --- | --- |
| **Consume** | Read all content and use or discard the parsed value afterward | Decode JSON into DTO; read all bytes to calculate size |
| **Relay** | Pass the stream to another writer/consumer and wait for that consumer to finish | Forward `PartEvent` to WebClient or write to a file |
| **Release** | Bytes are not needed; release each buffer as it arrives | Drain body then return 413; skip an unselected file part |

All three can appear in the same pipeline. For example, an application reads multipart metadata, relays an accepted file, and releases all remaining parts. For every part, content must have exactly one owner at any given moment.

### 2.2. `.then()` Does Not Mean Release

The following example only waits for the Publisher to complete and discards values:

~~~java
Mono<Void> wrong = request.getBody().then();
~~~

`then()` does not know it must release the `DataBuffer` instances owned by the application. With a raw `Flux<DataBuffer>`, release before discarding:

~~~java
Mono<Void> drain = request.getBody()
    .doOnNext(DataBufferUtils::release)
    .then();
~~~

`then()` means "wait for the body to complete"; `doOnNext` is what actually releases each buffer.

## 3. DataBuffer and Memory Ownership

`DataBuffer` is Spring's abstraction over different byte buffer implementations. Some implementations are pooled and reference-counted. When the reference count reaches 0, memory can return to the pool; if a reference is held too long, the pool cannot reuse that memory region.

| Situation | What the application does |
| --- | --- |
| Receives raw `DataBuffer`, finishes reading, and does not forward | Call `DataBufferUtils.release(buffer)` |
| Drops buffers in `filter` or discard-capable operators | Register `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` |
| Joins multiple buffers via `DataBufferUtils.join` | Release the resulting buffer after use; join cleans up accumulated buffers on error/cancel |
| Passes buffer to another HTTP writer | Do not release before the writer finishes reading; ownership has transferred |
| Needs two consumers to read the same pooled buffer | Use `retain` intentionally and release each reference exactly once |
| Already decoded into `String`, DTO, or `byte[]` via standard codec | Do not manually release decoded objects |

Prefer `DataBufferUtils.release` instead of casting to `PooledDataBuffer` or calling Netty APIs directly. This utility handles pooled buffers properly without coupling the application to a specific connector.

### 3.1. Releasing a Buffer After Reading

~~~java
int byteCount = buffer.readableByteCount();
try {
    byte[] copy = new byte[byteCount];
    buffer.read(copy);
    // Process the copy here.
}
finally {
    DataBufferUtils.release(buffer);
}
~~~

Do not use the buffer after it has been released. If you need to keep content for asynchronous processing, copy it into a `byte[]` or another representation with clear ownership before releasing.

### 3.2. Do Not Release Twice

If your code already released a buffer in `doOnNext`, do not pass that same buffer to a writer afterward. If a writer receives a buffer to write an outbound request or response, the writer is the consumer and is responsible for releasing it after reading. A second release can cause reference count errors or access to freed memory.

### 3.3. Retain Only When Two Owners Truly Exist

`DataBufferUtils.retain(buffer)` increments the reference count when the implementation supports it. Every retained reference must have a matching release. If the goal is merely logging or checking a signature, it is usually safer to copy a bounded number of bytes and release the original buffer.

Do not use `retain` as a blanket fix for confusing pipelines. Write clearly which consumer holds the buffer and which consumer releases it.

## 4. Draining the Entire Raw Request Body

If an endpoint does not need the body but must read the full request before returning a response, drain `Flux<DataBuffer>` buffer by buffer. This avoids buffering the whole payload in memory.

~~~java
@PostMapping("/discard")
Mono<String> discard(@RequestBody Flux<DataBuffer> body) {
    AtomicLong totalBytes = new AtomicLong();

    return body
        .doOnNext(buffer -> {
            totalBytes.addAndGet(buffer.readableByteCount());
            DataBufferUtils.release(buffer);
        })
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
        .then(Mono.fromSupplier(
            () -> "discardedBytes=" + totalBytes.get()));
}
~~~

Explanation:

1. `@RequestBody Flux<DataBuffer>` receives the raw buffer stream instead of asking Jackson to decode JSON.
2. `readableByteCount()` gets the number of readable bytes in the buffer.
3. `doOnNext` updates the counter and releases the buffer immediately after use.
4. `doOnDiscard` is a safety net for buffers dropped by discard-capable operators due to filter, prefetch, error, or cancellation.
5. `then(...)` emits the result only after the body completes.

**Do not use `collectList()` to drain large bodies.** It keeps all elements in memory until the source completes; that defeats streaming and can create memory pressure.

### 4.1. Draining in a Functional Endpoint

~~~java
Mono<ServerResponse> discard(ServerRequest request) {
    return request.bodyToFlux(DataBuffer.class)
        .doOnNext(DataBufferUtils::release)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
        .then(ServerResponse.noContent().build());
}
~~~

Same principle as annotated controllers: consume the entire stream, release each buffer, and only then build the response.

### 4.2. When You Need to Buffer a Small Bounded Body

Sometimes you need to read bytes once to compute a digest, verify a format, or parse manually. Use `DataBufferUtils.join` with a byte limit:

~~~java
Mono<byte[]> readBounded(Flux<DataBuffer> body) {
    int maxBytes = 64 * 1024;

    return DataBufferUtils.join(body, maxBytes)
        .map(buffer -> {
            try {
                byte[] copy = new byte[buffer.readableByteCount()];
                buffer.read(copy);
                return copy;
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        })
        .defaultIfEmpty(new byte[0]);
}
~~~

`join` creates a combined buffer; depending on the implementation, the result may be composite/zero-copy. The application must release the resulting buffer after copying or reading. When the source errors or is canceled during aggregation, `DataBufferUtils.join` releases already accumulated buffers. If `maxBytes` is exceeded, the operation emits `DataBufferLimitException` instead of silently allocating unbounded memory.

Use a limit appropriate to business needs. For large files or unbounded bodies, stream to file/object storage or a downstream writer instead of collecting into a `byte[]`.

## 5. doOnDiscard: Releasing Elements Dropped by Operators

A pipeline may drop buffers before reaching the final `doOnNext`:

~~~java
Flux<DataBuffer> selected = request.getBody()
    .filter(this::isWanted)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Buffers failing `isWanted` are dropped by filter. `doOnDiscard` registers cleanup for discard-supporting operators in the upstream portion of the chain. It does not automatically release every object lost from arbitrary code; verify which operators actually support discard and place the hook in the right composition chain.

If you keep selected buffers for processing, you still must release them after reading:

~~~java
Mono<Void> processSelected(Flux<DataBuffer> selected) {
    return selected
        .doOnNext(buffer -> {
            try {
                inspect(buffer);
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        })
        .then();
}
~~~

Buffers dropped by filter are handled by the discard hook; buffers passing through filter are handled in `doOnNext`. The two cleanup paths serve different roles.

`doOnDiscard` does not replace cleanup for buffers that your code pulled out and stored in a field, collection, or closure. If the application stores buffers itself, it must release them on completion, error, or cancellation. `doFinally` only signals termination; it does not automatically know which buffers need releasing.

## 6. Errors and Cancellation While Reading the Body

A request can terminate before the body is fully read:
- Client closes the connection or aborts the upload.
- Server times out or cancels the subscription.
- Codec emits a decoding error.
- Filter/handler uses `take`, `next`, `timeout`, or short-circuits.
- Downstream writer rejects or errors while relaying.

In these scenarios:
1. Let cancellation/error propagate along the reactive chain.
2. Release buffers currently owned by the application.
3. Use `doOnDiscard` for buffers held by discard-supporting operators.
4. For manually held buffers, use cleanup with clear ownership.
5. Do not create a side subscription via `subscribe()` just to drain the body.

Error-prone pattern:

~~~java
request.getBody().subscribe(DataBufferUtils::release);
return response.setComplete();
~~~

A side subscription runs detached from the request lifecycle. The response may complete before draining finishes; stream errors and cancellation become hard to coordinate. Compose the Publisher instead:

~~~java
return request.getBody()
    .doOnNext(DataBufferUtils::release)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .then(response.setComplete());
~~~

The response completes only after the body Publisher finishes. If the client disconnects, cancellation can still end the chain early; you cannot guarantee draining a request whose peer has already disconnected.

## 7. URL-Encoded Forms: Use the Decoded and Cached API

For `application/x-www-form-urlencoded`, Spring WebFlux provides `ServerWebExchange.getFormData()` and `ServerRequest.formData()`. The framework uses `FormHttpMessageReader` to decode into `MultiValueMap<String, String>`.

~~~java
Mono<MultiValueMap<String, String>> form =
    exchange.getFormData();
~~~

Once `getFormData()` is called, Spring parses the body and caches the result so other components can access the form data again. Afterward, the original raw request body can no longer be re-read.

- If you need form values, use `getFormData()` consistently across components.
- Do not call `getFormData()` and still expect `getRequest().getBody()` to return the raw bytes.
- If you only want to discard the form, you can wait on `getFormData().then(...)`; the parser may still buffer form data within configured limits.
- If you need to drain raw bytes without decoding, read the raw body and release each `DataBuffer`; do not use the form parser at the same time.

Reading a form in a functional endpoint:

~~~java
Mono<ServerResponse> handleForm(ServerRequest request) {
    return request.formData()
        .flatMap(data -> {
            String name = data.getFirst("name");
            return ServerResponse.ok()
                .bodyValue("namePresent=" + (name != null));
        });
}
~~~

If you only need to check a few fields, `getFormData()` is better than parsing URL encoding manually. If bodies can be large or abused, configure appropriate byte limits and form sizes.

## 8. Multipart: Map-Style and Streaming

Multipart requests can contain many parts, including text fields and files. Spring WebFlux supports parsing into `MultiValueMap<String, Part>` or reading sequentially via `Flux<PartEvent>`.

### 8.1. Map-Style with getMultipartData()

~~~java
Mono<MultiValueMap<String, Part>> parts =
    exchange.getMultipartData();
~~~

`getMultipartData()` parses and caches the map; the original raw body cannot be re-read once the parser has consumed it. If the application ignores parsed parts and a part has temporary backing storage, delete that storage via `Part.delete()`:

~~~java
Mono<Void> deleteAllParts(ServerWebExchange exchange) {
    return exchange.getMultipartData()
        .flatMapMany(map ->
            Flux.fromIterable(map.values())
                .flatMapIterable(parts -> parts))
        .concatMap(Part::delete)
        .then();
}
~~~

`Part.delete()` returns `Mono<Void>`; the operation runs only when the Publisher is subscribed to. Compose it into the chain and wait for completion. Do not call `delete().subscribe()` and return the response immediately.

With `FilePart`, if you want to keep the file, use `transferTo(Path)` or an appropriate streaming API. `transferTo` consumes the part content and writes it to the destination; afterward, the application is responsible for managing the destination file. If rejecting a file, clean up part storage instead of leaving unnecessary temporary files behind.

### 8.2. Streaming with PartEvent

When using `Flux<PartEvent>`, each multipart part emits at least one event with headers and a content buffer:
- `FormPartEvent` represents a text field and provides `value()`.
- `FilePartEvent` represents a file; large files can emit multiple events/buffers.
- The final event of each part has `isLast() == true`.

You can split the stream into windows per part:

~~~java
Flux<Flux<PartEvent>> parts =
    allPartEvents.windowUntil(PartEvent::isLast);
~~~

If the endpoint needs none of the parts, release each event's content:

~~~java
Mono<Void> discardAllParts(Flux<PartEvent> events) {
    return events
        .doOnNext(event ->
            DataBufferUtils.release(event.content()))
        .doOnDiscard(PartEvent.class, event ->
            DataBufferUtils.release(event.content()))
        .then();
}
~~~

Every `PartEvent.content()` returns a `DataBuffer` received by the handler. When ignoring a part, you must release the content of all events, including subsequent events of large files. Never just read `filename()` or `FormPartEvent.value()` and drop the Publisher without handling the remaining content.

### 8.3. Skipping One Part While Continuing to the Next Part

`windowUntil(PartEvent::isLast)` creates one window per part. You can process each window sequentially; if a part is not needed, drain and release every event in the window:

~~~java
Mono<Void> discardPart(Flux<PartEvent> part) {
    return part
        .doOnNext(event ->
            DataBufferUtils.release(event.content()))
        .doOnDiscard(PartEvent.class, event ->
            DataBufferUtils.release(event.content()))
        .then();
}

Mono<Void> discardMultipart(Flux<PartEvent> allEvents) {
    return allEvents
        .windowUntil(PartEvent::isLast)
        .concatMap(this::discardPart)
        .then();
}
~~~

`concatMap` preserves ordering and only moves to the next window after the current window finishes. If processing a selected file, relay the entire content stream to the writer/storage and wait for the relay to complete before moving to the next part.

### 8.4. Relaying a File Part to WebClient

If the goal is forwarding the file to another service, do not release buffers before WebClient reads them. When the Publisher is handed to the writer, buffer consumption ownership transfers to the writer:

~~~java
Mono<Void> relay(
        WebClient client,
        Flux<PartEvent> partEvents) {

    return client.post()
        .uri("/internal/uploads")
        .body(partEvents, PartEvent.class)
        .retrieve()
        .bodyToMono(Void.class);
}
~~~

This is an illustrative fragment; in a real application, target route, metadata, timeouts, authentication, and response mapping must be configured. Only forward to services authorized to receive the data. Never both release a buffer in `doOnNext` and pass that same buffer into WebClient.

### 8.5. Choosing Map-Style or Streaming?

| Scenario | Suitable approach |
| --- | --- |
| Small form, few parts, need to read many fields | `getMultipartData()` or `@RequestPart` binding |
| Size-bounded file upload | `FilePart.transferTo(Path)` |
| Large file, need backpressure and chunk-by-chunk handling | `Flux<PartEvent>` |
| Discarding an already-parsed file part | `Part.delete()` |
| Discarding the entire multipart body via streaming | `PartEvent.content()` + `DataBufferUtils.release` |
| Relaying upload to another service | Pass `PartEvent`/`DataBuffer` to WebClient writer and await completion |

Do not parse multipart into a map just to discard a large file. Map-style may buffer metadata and manage temporary storage; `PartEvent` streaming fits when you need per-chunk control and backpressure.

## 9. Short-Circuiting in a WebFilter

A filter may block a request before the controller, such as auth middleware or policy checks. If it decides to return a response immediately, the body may not have been read by the controller yet.

For request bodies with bounded sizes, the filter can drain the entire stream and release each buffer before completing the response:

~~~java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class DrainAndRejectFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest()
            .getPath().pathWithinApplication().value();

        if (!"/api/body/reject".equals(path)) {
            return chain.filter(exchange);
        }

        exchange.getResponse()
            .setStatusCode(HttpStatus.PAYLOAD_TOO_LARGE);

        return exchange.getRequest().getBody()
            .doOnNext(DataBufferUtils::release)
            .doOnDiscard(
                DataBuffer.class, DataBufferUtils::release)
            .then(exchange.getResponse().setComplete());
    }
}
~~~

Order matters:
1. The filter identifies a request to short-circuit.
2. Sets the status without committing the response yet.
3. Subscribes to the request body and releases each buffer.
4. Waits for the body to complete.
5. Calls `setComplete()` to commit the response.

### 9.1. Do Not Drain a Rejected Request Infinitely

Draining the entire body is not always the right choice. If a client sends an oversized payload, a malicious upload, or an endless stream, draining to the end can waste bandwidth, CPU, and server time.

- For a size-valid request rejected by policy, draining/releasing and returning a response can be appropriate.
- For a request exceeding size limits, stop reading per policy and configure the server/proxy to close or reset the connection when necessary.
- Enforce limits at the gateway, HTTP server, codec, and upload layers; do not check only after the entire body has been received.
- Apply timeouts and rate limits for uploads.

The goal is proper ownership handling. That does not force the application to read an unbounded body in every situation.

## 10. Limiting Buffering and Preventing Memory Exhaustion

Some convenient APIs parse the entire body into an object or map. They are easy to use, but carry a cost:
- `Mono<byte[]>` holds the entire payload.
- `Mono<String>` holds the entire decoded string.
- `getFormData()` parses the form into a map.
- `getMultipartData()` builds a part map and may use temporary storage.
- `DataBufferUtils.join()` aggregates buffers into a combined buffer.

Required safeguards:

1. Enforce request size limits at the gateway and server.
2. Configure appropriate buffer/codec limits.
3. Use `PartEvent` for large files or streaming.
4. Do not log or cache the entire request body by default.
5. Do not use unbounded `collectList()` or `join()` on large streams.
6. Drain using `doOnNext(release).then()` when simply discarding the body.
7. Preserve backpressure; never use unbounded `onBackpressureBuffer()` for uploads.
8. Monitor memory pools, request duration, upload failures, and cancellations.

### 10.1. Request Body Is Read-Once

Do not attach two independent subscribers to the same raw body:

~~~java
Flux<DataBuffer> body = exchange.getRequest().getBody();

Mono<Long> count = body
    .map(DataBuffer::readableByteCount)
    .reduce(0L, Long::sum);

Mono<DataBuffer> joined = DataBufferUtils.join(body);
~~~

You cannot assume the body will replay for a second subscriber. If multiple operations are needed, perform them within one pipeline, copy a bounded number of bytes, or use the exchange's cached APIs for form/multipart. Custom body caching requires memory bounds and careful retain/release management.

## 11. Complete Example: Spring Boot 4.0.9 and Java 17+

Demo project:
- A controller accepting raw `Flux<DataBuffer>` and releasing the entire body.
- A controller accepting multipart `Flux<PartEvent>` and releasing each event's content.
- A `WebFilter` rejecting requests before the controller while draining the body before committing the response.

### 11.1. Structure

~~~text
webflux-body-discard/
├── pom.xml
├── src/main/java/com/example/body/BodyDiscardApplication.java
├── src/main/java/com/example/body/BodyController.java
├── src/main/java/com/example/body/DrainAndRejectFilter.java
└── src/test/java/com/example/body/BodyDiscardIntegrationTest.java
~~~

### 11.2. pom.xml

Spring Boot 4.0.9 requires Java 17+ and Maven 3.6.3+.

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
    <artifactId>webflux-body-discard</artifactId>
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

### 11.3. BodyDiscardApplication.java

~~~java
package com.example.body;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BodyDiscardApplication {
    public static void main(String[] args) {
        SpringApplication.run(BodyDiscardApplication.class, args);
    }
}
~~~

### 11.4. BodyController.java

~~~java
package com.example.body;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.PartEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/body")
public class BodyController {

    @PostMapping(
        value = "/discard",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> discard(@RequestBody Flux<DataBuffer> body) {
        AtomicLong totalBytes = new AtomicLong();

        return body
            .doOnNext(buffer -> {
                totalBytes.addAndGet(buffer.readableByteCount());
                DataBufferUtils.release(buffer);
            })
            .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
            .then(Mono.fromSupplier(
                () -> "discardedBytes=" + totalBytes.get()));
    }

    @PostMapping(
        value = "/multipart/discard",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<ResponseEntity<Void>> discardMultipart(
            @RequestBody Flux<PartEvent> allPartEvents) {

        return allPartEvents
            .doOnNext(event ->
                DataBufferUtils.release(event.content()))
            .doOnDiscard(PartEvent.class, event ->
                DataBufferUtils.release(event.content()))
            .thenReturn(ResponseEntity.noContent().build());
    }

    @GetMapping(value = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("ok");
    }
}
~~~

In `/discard`, each `DataBuffer` is counted and released immediately; the response is built only when the Publisher completes. In `/multipart/discard`, each `PartEvent.content()` is released, including subsequent file chunks.

### 11.5. DrainAndRejectFilter.java

~~~java
package com.example.body;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class DrainAndRejectFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String path = exchange.getRequest()
            .getPath().pathWithinApplication().value();

        if (!"/api/body/reject".equals(path)) {
            return chain.filter(exchange);
        }

        exchange.getResponse()
            .setStatusCode(HttpStatus.PAYLOAD_TOO_LARGE);

        return exchange.getRequest().getBody()
            .doOnNext(DataBufferUtils::release)
            .doOnDiscard(
                org.springframework.core.io.buffer.DataBuffer.class,
                DataBufferUtils::release)
            .then(exchange.getResponse().setComplete());
    }
}
~~~

The filter only short-circuits the test path `/api/body/reject`. It sets status 413, drains and releases the request body, and only then completes the response. In production, pair this with body limits and a connection close/reset policy when requests exceed limits or cannot be safely drained.

## 12. HTTP Integration Tests

The tests hit a real server using `RANDOM_PORT`. They reuse the same `HttpClient` to send a large body, a rejected request, and a subsequent request.

### 12.1. BodyDiscardIntegrationTest.java

~~~java
package com.example.body;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BodyDiscardIntegrationTest {

    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> send(
            String method, String path,
            String contentType, String body) throws Exception {

        HttpRequest.Builder builder = HttpRequest.newBuilder(
            URI.create("http://localhost:" + port + path));

        HttpRequest.BodyPublisher publisher = body == null
            ? HttpRequest.BodyPublishers.noBody()
            : HttpRequest.BodyPublishers.ofString(body);

        if (contentType != null) {
            builder.header("Content-Type", contentType);
        }

        return CLIENT.send(
            builder.method(method, publisher).build(),
            HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void rawBodyIsFullyDrainedAndCounted() throws Exception {
        String payload = "x".repeat(256 * 1024);

        HttpResponse<String> response = send(
            "POST", "/api/body/discard",
            "application/octet-stream", payload);

        assertEquals(200, response.statusCode());

        int expectedBytes =
            payload.getBytes(StandardCharsets.UTF_8).length;

        assertEquals(
            "discardedBytes=" + expectedBytes,
            response.body());
    }

    @Test
    void rejectedRequestIsDrainedBeforeNextRequest()
            throws Exception {

        String payload = "ignored=".repeat(32 * 1024);

        HttpResponse<String> rejected = send(
            "POST", "/api/body/reject",
            "application/octet-stream", payload);

        assertEquals(413, rejected.statusCode());

        HttpResponse<String> next =
            send("GET", "/api/body/ping", null, null);

        assertEquals(200, next.statusCode());
        assertEquals("ok", next.body());
    }

    @Test
    void multipartPartsAreConsumedAndReleased() throws Exception {
        String boundary = "----webflux-boundary-123";
        String multipart =
            "--" + boundary + "\r\n" +
            "Content-Disposition: form-data; name=\"description\"\r\n" +
            "\r\n" +
            "sample upload\r\n" +
            "--" + boundary + "\r\n" +
            "Content-Disposition: form-data; name=\"file\"; filename=\"note.txt\"\r\n" +
            "Content-Type: text/plain\r\n" +
            "\r\n" +
            "file content that will be discarded\r\n" +
            "--" + boundary + "--\r\n";

        HttpResponse<String> response = send(
            "POST", "/api/body/multipart/discard",
            "multipart/form-data; boundary=" + boundary,
            multipart);

        assertEquals(204, response.statusCode());
        assertTrue(response.body().isEmpty());
    }
}
~~~

### 12.2. Running the Project

Requires JDK 17+ and Maven 3.6.3+:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Test draining a raw body:

~~~bash
curl -i -X POST http://localhost:8080/api/body/discard ^
  -H "Content-Type: application/octet-stream" ^
  --data-binary "payload to discard"
~~~

Test the rejecting and draining filter:

~~~bash
curl -i -X POST http://localhost:8080/api/body/reject ^
  -H "Content-Type: application/octet-stream" ^
  --data-binary "request body is drained before 413"
~~~

`^` is the line continuation character for Windows CMD. If running PowerShell, use a single line or PowerShell's line continuation character.

**Expected results:**

| Request | Result |
| --- | --- |
| POST `/api/body/discard` | 200, body `discardedBytes=<UTF-8 byte count>` |
| POST `/api/body/reject` | 413, filter drains the body before completing |
| GET `/api/body/ping` after the rejected request | 200, body `ok` |
| POST `/api/body/multipart/discard` | 204, all event contents released |

The test uses the same `HttpClient` for the rejected request and the subsequent request. That verifies the HTTP flow continues working; it does not assert that the connector always reuses the exact same TCP socket.

## 13. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Calling `.then()` on a raw body without releasing | Buffers are ignored while still holding references | `doOnNext(DataBufferUtils::release).then()` |
| Releasing only the first buffer | The rest of the body/file remains retained | Consume or release all buffers/events until completion |
| Reading `PartEvent.filename()` then dropping the window | Subsequent file chunks go unhandled | Consume, relay, or release the entire window |
| Reading `FormPartEvent.value()` and assuming all parts are freed | Event content and later parts may still hold buffers | Ensure the entire `PartEvent` stream is consumed/released |
| Using `collectList()` to drain uploads | The whole body is held in memory | Stream buffer by buffer and release |
| Using unbounded `DataBufferUtils.join()` | Large payloads can exhaust memory | Use `join(body, maxBytes)` or streaming |
| Releasing a buffer then passing it to WebClient | Writer reads an already-released buffer | Transfer ownership to the writer; do not manually release first |
| Passing a buffer to two consumers without retain/copy | One consumer may read a freed buffer | Copy or retain/release with clear ownership |
| Using `doOnDiscard` as cleanup for every variable | Manually stored buffers in fields still leak | Explicitly clean up on completion/error/cancel |
| Calling a separate `subscribe()` in a filter to drain | Response may complete before draining finishes | Compose the drain via `.then(response.setComplete())` |
| Reading raw body after `getFormData()` | The body was already consumed by the parser | Use the `getFormData()` cache consistently |
| Reading raw body after `getMultipartData()` | The multipart parser already consumed the raw body | Use the cached map or `PartEvent` streaming from the start |
| Deleting temp files without subscribing to `Part.delete()` | Cleanup never executes | Compose `Part.delete()` into the returned Publisher |
| Draining rejected requests infinitely | Wastes bandwidth/CPU and may hold resources | Limit body size, set timeouts, and close/reset connections per policy |
| Testing only the happy path | Misses bugs on cancel, malformed bodies, or large uploads | Test error/cancel, size limits, multipart, and subsequent requests |

## 14. Debugging DataBuffer Leaks

### 14.1. Common Symptoms

- Direct memory steadily grows even though heap does not grow proportionally.
- Netty logs `LEAK: ByteBuf.release() was not called before it's garbage-collected`.
- `OutOfDirectMemoryError` or pool allocation failures.
- Failures appear after upload requests, multipart parsing, or filter short-circuiting.
- Small tests pass, but failures occur under concurrent load or large files.

### 14.2. Investigation Checklist

1. Find every place calling `getBody()`, `bodyToFlux(DataBuffer.class)`, and `PartEvent.content()`.
2. Identify which consumer owns each buffer.
3. Inspect branches with filters, `skip`, `filter`, `take`, `next`, timeouts, and cancellations.
4. Verify every `DataBuffer` is either released after reading or has ownership transferred to a writer.
5. Verify `doOnDiscard` is placed after operators that may discard elements.
6. Check whether code calls detached `subscribe()` or reads the body multiple times.
7. Check multipart temporary storage and `Part.delete()`.
8. Enable appropriate Reactor Netty leak detection/debug options in test environments.
9. Run integration tests with large bodies and many concurrent requests.
10. Monitor direct memory, pool metrics, and active request counts.

Do not keep high-detail leak detection enabled continuously in production if the performance overhead is too large. Use diagnostic profiles or test environments to pinpoint allocation and release sites.

## 15. Production Design Rules

- Read at the highest feasible abstraction: DTO/String/Part APIs let codecs manage buffers; handle raw `DataBuffer` only when needed.
- When discarding a body, drain and release as a stream; never aggregate payloads just to throw them away.
- When relaying, let the writer take ownership and await downstream Publisher completion.
- When parsing form/multipart via exchange APIs, do not re-read the raw body.
- When streaming multipart, process each part through `isLast`; do not drop remaining chunks.
- When using discard operators, add cleanup hooks while still explicitly releasing buffers passing through the main branch.
- Enforce size and time limits; avoid draining unbounded uploads.
- Test cancellation and errors; the happy path does not prove cleanup works.
- Never log bodies/files by default; avoid leaking data and creating large in-memory copies.
- Never subscribe manually; let the request lifecycle manage consumption, errors, and cancellation.

## 16. Hands-On Exercises

**Exercise 1 – Drain raw body.** Write an endpoint receiving `Flux<DataBuffer>`, counting bytes and releasing each buffer. Send a body of a few hundred KB and verify the byte count.

**Exercise 2 – Filter short-circuit.** Write a `WebFilter` rejecting a path before the controller. Drain/release the body then return 413. Use the same `HttpClient` to send a subsequent request.

**Exercise 3 – DataBufferUtils.join.** Write a helper reading a body bounded to 64 KB. Test a small body, an empty body, and an oversized body; verify the resulting buffer is always released.

**Exercise 4 – doOnDiscard.** Add a `filter` dropping some `DataBuffer` elements. Release selected buffers after reading and use `doOnDiscard` for buffers dropped by the filter.

**Exercise 5 – Form cache.** Call `getFormData()` from both a filter and a controller. Verify both read the same cache, while the raw request body can no longer be re-read.

**Exercise 6 – Multipart map.** Call `getMultipartData()`, skip a `FilePart`, and call `Part.delete()`. Verify the cleanup Publisher completes.

**Exercise 7 – PartEvent.** Use `windowUntil(PartEvent::isLast)` to split files by part. Release all content of unselected parts.

**Exercise 8 – Relay upload.** Relay `Flux<PartEvent>` to WebClient. Do not release buffers before the writer; await outbound response completion.

**Exercise 9 – Cancellation.** Disconnect the client mid-upload. Verify cancellation propagates upstream, held buffers are cleaned up, and there are no side subscriptions.

**Exercise 10 – Load test.** Send multiple concurrent uploads and monitor direct memory/pool metrics before and after fixes. Compare against a version that collects the whole body into `List<DataBuffer>`.

## 17. Official References

1. Spring Framework 7.0.8 – Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
2. Spring Framework 7.0.8 – Functional Endpoints / `ServerRequest.bodyToFlux` and multipart `PartEvent`: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
3. Spring Framework 7.0.8 – Multipart Content in annotated controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
4. Spring Framework 7.0.8 – Reactive Core, Form Data, and Multipart Data: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
5. Spring Framework Javadoc – `DataBufferUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
6. Spring Framework Javadoc – `DataBuffer` / `PooledDataBuffer`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html
7. Spring Framework Javadoc – `Part` / `PartEvent`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/Part.html
8. Spring Framework Javadoc – `FilePart`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/FilePart.html
9. Spring Boot 4.0.9 – System Requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html
10. Reactor Core – Reference Guide, discard hooks and cancellation: https://projectreactor.io/docs/core/release/reference/

**Final Self-Assessment:** Why does `.then()` not automatically release `DataBuffer` instances? When is `doOnDiscard` needed in addition to `doOnNext(release)`? Why can't the raw body be read after `getFormData()` or `getMultipartData()`? When ignoring a `PartEvent` file, what must happen to every chunk arriving after the first event? If you can answer these questions and test filter short-circuits, multipart, cancellation, and subsequent requests, you have mastered properly handling discarded bodies in WebFlux.
