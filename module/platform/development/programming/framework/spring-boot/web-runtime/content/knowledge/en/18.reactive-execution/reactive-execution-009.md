# DataBuffer, Memory References, and Buffer Leak Risks

In Spring WebFlux, HTTP data can flow through an application as consecutive chunks of bytes: `Flux<DataBuffer>`. This sits below JSON DTOs, `String`, or `Resource`. Some `DataBuffer` implementations use reusable memory (*pooled memory*), and even native memory outside the Java heap (*direct/off-heap memory*). When application code receives such a buffer, failing to terminate its lifecycle properly prevents memory from returning to the pool. Releasing too early leaves the data invalid before the next component reads it.

**Overarching principle:** not every `DataBuffer` requires the application to call `release()`. You must clearly identify **who owns the buffer at each stage of the pipeline**, who transfers ownership, and who is responsible for final release. Use high-level codec APIs whenever direct byte manipulation is unnecessary; when writing custom decoders, filters, proxies, or streaming uploads, manage the lifecycle according to the actual contract.

Scope: `DataBuffer` mechanics in the reactive runtime, reference counting and pooled buffers, leak/double-release scenarios, using `DataBufferUtils`, interactions with Reactor cancellation/backpressure, a runnable Java example, and a diagnostic workflow. Main examples target **Spring Boot 3.x + Spring Framework 6.x + Java 17+**; APIs may vary across major versions.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the differences among Java heap, direct memory, pooled memory, `ByteBuf`, and `DataBuffer`.
- Understand `PooledDataBuffer` along with `retain`, `release`, and reference counts; distinguish losing ownership from an already-released buffer.
- Pinpoint where `DataBufferUtils.release` is required when code directly receives/reads buffers, and where you must not release because ownership transferred to the framework.
- Use bounded `DataBufferUtils.join`, understanding why `join` manages input buffers while the joined result still needs lifecycle cleanup.
- Explain buffer drop risks across `filter`/`skip`/prefetch/cancel/error, and the bounded role of `doOnDiscard`.
- Write a small WebFlux endpoint with cleanup in `finally`, testing both valid payloads and oversized payloads.
- Read Netty leak warnings and structure combined tests covering both memory leaks and double releases.

## 2. What Abstraction Is `DataBuffer`?

`org.springframework.core.io.buffer.DataBuffer` is Spring Core's byte-buffer abstraction. In WebFlux, low-level HTTP bodies can be publishers emitting individual `DataBuffer`s. A buffer represents a byte region with read and write positions; an HTTP request or response may span multiple buffers rather than fitting into a single byte array.

Common APIs:

| API | Meaning |
| --- | --- |
| `DataBufferFactory.allocateBuffer(capacity)` | Allocates a buffer; heap vs. direct depends on factory and configuration |
| `DataBufferFactory.wrap(byte[])` | Wraps an existing byte region without forcing new payload allocation/copying |
| `DataBuffer.write(byte[])` | Writes bytes at the current write position |
| `DataBuffer.read(byte[])` | Copies bytes from the current read position into destination array and advances read position |
| `DataBuffer.readableByteCount()` | Number of currently readable bytes, not necessarily total capacity |
| `DataBuffer.readPosition()/writePosition()` | Two independent cursors, avoiding `flip()` needed by some `ByteBuffer` usages |
| `DataBufferUtils.retain(buffer)` | Retains an extra reference if it is a compatible pooled buffer |
| `DataBufferUtils.release(buffer)` | Releases according to buffer type when applicable |
| `DataBufferUtils.join(publisher, maxByteCount)` | Joins multiple buffers into one, enforcing a total byte limit |
| `DataBufferUtils.touch(buffer, hint)` | Attaches a debug hint if the implementation supports leak tracking |

Spring provides multiple implementations. `DefaultDataBuffer` wraps Java `ByteBuffer`; `NettyDataBuffer` wraps Netty `ByteBuf` and is typically used when WebFlux runs on Reactor Netty. Never assume every server uses Netty or every implementation handles reference counting identically.

Data flow diagram:

```text
HTTP socket / driver
    |
    v
ByteBuf (Netty) or server-supplied byte region
    |
    v
DataBuffer --> Flux<DataBuffer> --> decoder / custom operator
                                      |
                                      +--> DTO / String / object
                                      |      (original buffer released after consumption)
                                      |
                                      +--> pass Flux<DataBuffer> --> HTTP response
                                              (HTTP writer assumes duty per contract)
```

For standard controllers receiving `@RequestBody Mono<MyDto>`, returning `Mono<MyDto>`, and using default codecs, Spring handles most buffer management. Pay special attention whenever directly calling `request.getBody()`, using `bodyToFlux(DataBuffer.class)`, writing custom encoders/decoders, transforming binary payloads, writing custom filters, caching bodies, or proxying bytes.

## 3. Heap, Direct Memory, and Pool: Three Concepts to Separate

**Java heap** is the object space managed by GC. Large `byte[]` arrays reside on the heap and drive heap/GC pressure. **Direct/off-heap memory** is native memory close to I/O, which can increase process resident memory (RSS) without a matching rise in heap charts. **Pooling** is a policy of reusing buffers/memory regions instead of repeatedly reallocating; pools may back buffers with direct memory or heap depending on the allocator.

With Netty, `ByteBuf` instances may come from a pooled allocator, carry a reference count, and require balanced releases. When `refCnt` drops to 0, the buffer returns to the pool; that **does not necessarily** drop process RSS immediately, because the pool retains memory for reuse. Conversely, steady RSS does not prove every buffer was released properly.

| Observation | Careful interpretation |
| --- | --- |
| Heap climbs steadily, frequent GC | Possible retained objects/arrays, unbounded queues, caches, or object leaks |
| Direct memory / allocator active bytes climb, leak logs appear | Possible unreleased pooled `ByteBuf`s or abnormally prolonged lifetimes |
| Direct memory "used" is high while "active" stays flat | Pool may be holding allocated chunks for reuse; check allocator metrics |
| `DataBufferLimitException` | Byte aggregation/decoding limit was exceeded; **does not automatically prove** a leak |
| `IllegalReferenceCountException` | Usually indicates use-after-release or unbalanced release/retain |
| Memory rises under load and falls when load stops | May be normal; compare across multiple load cycles and inspect retention |

**Distinguish two independent bugs:** *resource leak* means a resource is never returned after use; *unbounded buffering* means holding too much data simultaneously. Both can occur together, yet their fixes differ: add `release` for finished buffers while enforcing buffer/queue/concurrency limits to stop unbounded accumulation.

## 4. `PooledDataBuffer` and Reference Counting

`PooledDataBuffer` extends `DataBuffer` to manage the lifecycle of potentially pooled resources. Core mechanics:

- Upon creating a pooled buffer, initial reference count is typically **1**.
- `retain()` increments reference count by **1** to hold an additional ownership reference when needed.
- `release()` decrements reference count by one; upon reaching **0**, the memory can be reclaimed.
- After reference count hits **0**, code must never read, write, or forward that buffer; doing so triggers freed-buffer access errors.
- If a `retain` lacks a matching `release`, memory remains pinned.
- Calling `release` more times than valid ownership references causes double release / use-after-release.

Think of a buffer **intentionally** shared between two consumers:

```text
allocate                        refCnt = 1   (A holds one reference)
A retains before handing to B   refCnt = 2   (A and B each hold one reference)
A finishes and releases         refCnt = 1   (B can still use it)
B finishes and releases         refCnt = 0   (buffer is returned)
```

Never sprinkle `retain` "just in case" across HTTP flows: each retain adds a release obligation. Likewise, never call `release` twice merely because a pipeline has two operators. **Operators do not invent new ownership**, unless their API/contract explicitly documents retaining or transferring ownership.

### 4.1. Why Use `DataBufferUtils` Instead of Direct Casting?

Example:

```java
DataBufferUtils.retain(buffer);
DataBufferUtils.release(buffer);
```

In Spring Framework 6.x, `retain` retains when the buffer is an appropriate pooled type; `release` handles `PooledDataBuffer` and compatible closeable types. When a buffer does not require such release, `release` may return `false`. Do not rely on the `true/false` return value to deduce exact final refCnt across all implementations.

Consult version-specific API docs since WebFlux/Netty implementations evolve; the enduring principle is ownership management.

### 4.2. When Is `retain` Actually Needed?

Suppose code receives a `DataBuffer` from a request and wants to keep it for an asynchronous task running **after** the initial handling path finishes. Truly sharing a buffer demands a disciplined retain/handoff/release protocol covering failure paths. Usually that design is complex and error-prone under cancellation, retries, or a slow second consumer. For small payloads, **copy** bytes into a bounded `byte[]` and release the original buffer; for large payloads, prefer streaming or lifecycle-managed temp files.

**Never keep `DataBuffer`s inside singletons, caches, or unbounded collections.** If caching is required, cache independent decoded/copied domain objects with clear bounds and eviction.

## 5. Buffer Ownership: The Most Important Question

Whenever code directly allocates, receives, retains, or returns a `DataBuffer`, answer these questions:

1. Who created or passed the buffer into this operator?
2. Once this operator finishes, is the payload **fully read and discarded**, or **forwarded to another consumer**?
3. If read and terminated here, who calls release?
4. When handed to the framework's HTTP writer, do you still have any right to release it yourself?
5. If an error, cancellation, timeout, or discard occurs before the consumer receives it, who still holds the resource?
6. If `retain` was called, does every reference have a matching release point?

Ownership checklist table:

| Action | Typical responsible party | Rule |
| --- | --- | --- |
| `@RequestBody Mono<Dto>` via default JSON codec | Codec/framework | Do not release manually because the app never handles raw buffers directly |
| Reading a `DataBuffer` and converting to your own `String`/DTO | Final consumer code | Release in `finally` after copying/reading completes |
| Calling `DataBufferUtils.join(source)` | `join` manages **input** buffers | Do not release individual input buffers again |
| Receiving the **resulting** buffer from `join` and decoding manually | Code receiving the result | Release the joined buffer after processing, even if decoding throws |
| Creating a `DataBuffer` and passing to `ServerHttpResponse.writeWith(...)` | Response-writing stage per framework contract | Do not release early right after handing into the write pipeline |
| Creating a buffer and hitting an exception before emitting into a publisher/transfer | Buffer-creating code | Release in the failure path before ownership transfers |
| `filter`/`skip` drops a received buffer | Operator/pipeline cleanup via supported mechanism | Place `doOnDiscard` correctly and test cancellation/error paths |
| Retaining a buffer for parallel work outside source lifetime | Party holding the extra reference | Retain deliberately and guarantee release when finished |
| `DataBufferUtils.write(source, OutputStream/Channel)` | API caller must read the contract | `Flux<DataBuffer>`-returning overloads do not auto-release sources; release in subscriber/proper path |

This table states principles, not a license to "release everything". Always check the Javadoc of the **specific overload**; for instance, `DataBufferUtils.write(source, Path)` returns `Mono<Void>` and carries a different contract than `OutputStream` overloads.

## 6. Bugs Causing Leaks and Double Releases

### 6.1. Reading Raw Body Without Releasing

**Wrong** when this code is the final consumer and nothing else releases:

```java
request.getBody()
        .map(buffer -> {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return new String(bytes, StandardCharsets.UTF_8);
        });
```

This turns buffers into `String`s without cleanup. With pooled buffers, refCnt stays elevated. You must release after copying data.

**Better** for a local transformation:

```java
request.getBody()
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return new String(bytes, StandardCharsets.UTF_8);
            } finally {
                DataBufferUtils.release(buffer);
            }
        })
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Both are **snippets** assuming `request` exists, not standalone classes; import `java.nio.charset.StandardCharsets`, `DataBuffer`, and `DataBufferUtils`. `finally` handles buffers **delivered into the lambda**; `doOnDiscard` cleans elements dropped/queued by compatible upstream operators. Do not assume hooks cover every error type or register two release paths for the same ownership. When applying this pattern to complex pipelines, verify actual lifecycle with cancellation tests.

When a body arrives across multiple chunks, `map` creates multiple partial strings rather than assembling one complete UTF-8 string. A multi-byte UTF-8 character can split across two chunks; to parse a small full body, use a text codec or bounded `join`. Avoid decoding each chunk independently and concatenating strings, as that corrupts multi-byte characters.

### 6.2. Releasing Before Forwarding Downstream

**Wrong:**

```java
Flux<DataBuffer> forwarded = request.getBody()
        .doOnNext(DataBufferUtils::release);
return response.writeWith(forwarded);
```

`doOnNext` executes **before** buffers reach the writer. If release drops refCnt to 0, the HTTP writer receives an invalid buffer. This causes `IllegalReferenceCountException` or corrupted responses.

If your intent is to **forward** raw buffers, transfer ownership according to the writer's contract without releasing before downstream finishes. If you must inspect/log contents, use non-mutating inspection where possible and never retain beyond the valid lifecycle.

### 6.3. Retaining and Forgetting to Release

**Wrong:**

```java
DataBufferUtils.retain(buffer);
savedBuffers.add(buffer); // Unbounded, no cleanup
```

Every retain adds a cleanup obligation. If executed per request, memory climbs proportionally to cumulative traffic. Avoid retaining raw pooled buffers; if truly required, use a lifecycle manager with close/cancel paths, capacity limits, and guaranteed release on timeouts/errors.

### 6.4. Double Release

**Wrong** when holding only one ownership reference without retain:

```java
try {
    consume(buffer);
} finally {
    DataBufferUtils.release(buffer);
    DataBufferUtils.release(buffer); // No second reference exists
}
```

The same hazard happens when a helper already releases a buffer and the caller releases it again due to an unclear contract. Define explicitly whether helpers **consume and release** or **borrow without releasing**. Never rely on a library silently ignoring a second release: never write logic depending on that behavior.

### 6.5. Unbounded Byte Accumulation

**Risky:**

```java
DataBufferUtils.join(request.getBody()) // No total byte cap
```

`join` manages input references, yet does nothing to stop an infinite or huge body from exhausting memory. For small payloads, use the explicitly bounded overload. For large payloads, design streaming, quotas, file size caps, and ingestion timeouts rather than joining everything into one buffer.

### 6.6. Subscribing Manually Inside Filters/Controllers

**Risky:**

```java
request.getBody().subscribe(buffer -> inspect(buffer));
return chain.filter(exchange);
```

This is an anti-pattern snippet. An independent subscription can drain the body before downstream reads it, detach errors/cancellation from the HTTP request lifecycle, and leak buffers if `inspect` throws. Compose publishers instead; subscribe only at boundaries with explicit ownership, error, cancel, and release handling. In a WebFlux HTTP server, the framework is normally the final subscriber.

## 7. `DataBufferUtils.join`: Convenient, Provided You Understand Ownership

For small, size-bounded `Flux<DataBuffer>` streams, `DataBufferUtils.join(source, limit)` is practical. It may create a single buffer with copied bytes or a **composite buffer** referencing original chunks. Both require clear ownership tracking:

```text
Flux<DataBuffer> (A, B, C)
          |
          v
DataBufferUtils.join(source, maxByteCount)
          |
          +-- Success: joined result J owns the combined data
          |             => consumer releases J after finishing with J
          |             => DO NOT individually release A, B, C again
          |
          +-- Error / cancellation before result:
                        join releases accumulated buffers
```

Spring Framework Javadoc states `join` releases accumulated buffers if the publisher errors/cancels; inputs are released as part of the composite. That does not mean the **result buffer** auto-releases after application callbacks read it. If `join` returns `Mono.empty()` because the source had no data, there is no result buffer to release.

### 7.1. Pattern for Reading Bounded Small Payloads

```java
Mono<String> body = DataBufferUtils.join(request.getBody(), 1024 * 1024)
        .map(joined -> {
            try {
                byte[] bytes = new byte[joined.readableByteCount()];
                joined.read(bytes);
                return new String(bytes, StandardCharsets.UTF_8);
            } finally {
                DataBufferUtils.release(joined);
            }
        })
        .defaultIfEmpty("");
```

This **snippet** applies when the body is genuinely UTF-8 text and `request` is available; it does not replace content-type, format, charset, schema, or application validation checks. `1024 * 1024` sets a 1 MiB limit at the join level. Temporary memory for chunks and the `byte[]` copy still exists; that limit **does not** prove total memory footprint is only 1 MiB.

If `maxByteCount` is exceeded, Spring emits `DataBufferLimitException`. Map it to an appropriate HTTP status or business error (commonly HTTP 413 for oversized uploads/bodies). Never swallow the error to return truncated data silently.

### 7.2. Do Not Release Individual Inputs to `join`

Common mistakes:

1. Putting `doOnNext(DataBufferUtils::release)` upstream of `join`; `join` may receive already-released buffers.
2. Keeping a list of inputs and releasing each after `join`, while the composite also owns them.
3. Calling unbounded `join` just to count bytes or log a large request, causing needless memory pressure.

If you only need to **count total bytes**, process each chunk and release immediately without joining the entire body. For JSON parsing, prefer Spring's codecs since they already manage buffers, limits, and error translation.

## 8. Complete Spring Boot 3.x Example: Reference Counts and HTTP Body with Cleanup

This example combines two checks:

1. At app startup, print the refCnt of a `NettyDataBuffer` before/after `retain` and `release`; demonstrating ownership with **two valid references**.
2. Endpoint `POST /inspect` reads bodies up to 1024 bytes, releases the joined buffer in `finally`, and rejects payloads exceeding the limit.

### 8.1. Project Setup

Use Spring Initializr to create a **Java 17+**, **Spring Boot 3.3.x** (or compatible 3.x) project with **Spring Reactive Web** / `spring-boot-starter-webflux`. Do not add `spring-boot-starter-web`; in Boot 3.x, having both Web and WebFlux starters typically makes auto-configuration select Spring MVC.

With Gradle/Groovy, the matching dependency block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Spring Initializr manages versions via the Spring Boot plugin/BOM. If creating a Maven project, add `spring-boot-starter-webflux` accordingly instead of copying the Gradle block.

Create **`src/main/java/demo/DataBufferLessonApplication.java`**:

```java
package demo;

import java.nio.charset.StandardCharsets;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.PooledByteBufAllocator;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.NettyDataBuffer;
import org.springframework.core.io.buffer.NettyDataBufferFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class DataBufferLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(DataBufferLessonApplication.class, args);
    }

    @Bean
    CommandLineRunner referenceCountDemo() {
        return args -> {
            NettyDataBufferFactory factory =
                    new NettyDataBufferFactory(PooledByteBufAllocator.DEFAULT);
            NettyDataBuffer buffer = factory.allocateBuffer(16);
            ByteBuf nativeBuffer = buffer.getNativeBuffer();

            try {
                buffer.write("abc".getBytes(StandardCharsets.UTF_8));
                System.out.println("1 initial refCnt=" + nativeBuffer.refCnt());

                DataBufferUtils.retain(buffer);
                System.out.println("2 retained refCnt=" + nativeBuffer.refCnt());

                DataBufferUtils.release(buffer);
                System.out.println("3 first release refCnt=" + nativeBuffer.refCnt());
            } finally {
                DataBufferUtils.release(buffer);
                System.out.println("4 final release refCnt=" + nativeBuffer.refCnt());
            }
        };
    }

    @PostMapping(
            path = "/inspect",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> inspect(ServerHttpRequest request) {
        return DataBufferUtils.join(request.getBody(), 1024)
                .map(joined -> {
                    try {
                        // Copied here solely to confirm byte count in this example.
                        byte[] bytes = new byte[joined.readableByteCount()];
                        joined.read(bytes);
                        return "bytes=" + bytes.length;
                    } finally {
                        DataBufferUtils.release(joined);
                    }
                })
                .defaultIfEmpty("bytes=0")
                .onErrorMap(
                        DataBufferLimitException.class,
                        ex -> new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "Body exceeds 1024 bytes", ex)
                );
    }
}
```

No `DataBufferFactory` bean is needed for HTTP: Spring supplies the factory matching the web server. The `CommandLineRunner` bean solely demonstrates Netty reference counting at startup and handles no real HTTP requests.

**Detailed explanation:**

- `PooledByteBufAllocator.DEFAULT` provides the allocator; `NettyDataBufferFactory.allocateBuffer(16)` creates a `NettyDataBuffer` backed by a Netty `ByteBuf` with initial refCnt 1.
- `retain` raises refCnt to 2; after one `release` it is 1; the final release in `finally` drops it to 0. There are exactly **two ownership references**, matching the single retain.
- Code never reads/writes the buffer **after** the final release; it only checks `refCnt()` to print reference state in the demo.
- `DataBufferUtils.join(request.getBody(), 1024)` accumulates up to 1024 bytes to build the joined buffer.
- `joined.read(bytes)` copies bytes into `byte[]`; `finally` releases `joined` even if code inside `map` throws.
- For an empty input, `join` may return `Mono.empty()`, so `defaultIfEmpty("bytes=0")` returns a meaningful response.
- Exceeding the join cap maps `DataBufferLimitException` into a `ResponseStatusException` with HTTP 413. Depending on error-handler configuration, the error body may contain detailed or minimal JSON.
- There is no loop releasing source buffers: `join` manages them, avoiding double releases.

### 8.2. Running the Project

From the directory with Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ignoring the banner and framework logs, the four lines printed in order by `CommandLineRunner` are:

```text
1 initial refCnt=1
2 retained refCnt=2
3 first release refCnt=1
4 final release refCnt=0
```

If your allocator/transport version differs, check your project's Netty API; the learning goal is observing two releases for two ownership references.

Test a valid request:

```bash
curl -s -X POST http://localhost:8080/inspect \
  -H 'Content-Type: application/octet-stream' \
  --data-binary 'hello'
```

HTTP response body:

```text
bytes=5
```

In Windows PowerShell, use `curl.exe` with the command above (or write it on one line to avoid line-continuation differences). For payloads over 1024 bytes, the endpoint should return **HTTP 413 Payload Too Large**. To generate a repeatable test payload using Python 3 if available:

```bash
python -c "print('x' * 1025, end='')" | curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST http://localhost:8080/inspect \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @-
```

Expected output:

```text
413
```

This command targets shells supporting pipes and `/dev/null` such as Linux/macOS. On Windows, send a 1025-byte file via `curl.exe --data-binary @payload.bin` and inspect the HTTP status with `-i`. HTTP 413 here comes from our `onErrorMap`; not every WebFlux app maps `DataBufferLimitException` identically by default.

### 8.3. Example Limitations

For clarity, the endpoint copies up to 1024 bytes into a `byte[]`. For multi-GB files, **do not** raise this limit to GBs; switch to streaming with quotas, content-length checks, slow-upload protection, timeouts, and cancellation cleanup. For standard JSON or text, prefer `@RequestBody` / codecs rather than manual buffer management.

## 9. Reactor: Discard, Cancellation, Errors, and Prefetch

A publisher emitting `DataBuffer`s has more states than "run and complete". Subscribers can cancel on client disconnect, `take` operator limits, timeouts, or upstream errors. Operators like `filter`, `skip`, `flatMap`, `publishOn`, and prefetching operators can hold or drop elements before they reach the terminal subscriber.

```text
Flux<DataBuffer>
    |
    +-- buffer A --> consumer receives -> reads -> releases A
    |
    +-- buffer B --> filter drops -> discard hook (if supported) -> releases B
    |
    +-- buffer C --> sits in queue -> client cancels -> queue cleanup -> releases C
    |
    +-- buffer D --> not yet emitted -> upstream depends on cancellation contract
```

### 9.1. `doOnDiscard` Is a Localized Mechanism

```java
Flux<DataBuffer> filtered = request.getBody()
        .filter(buffer -> buffer.readableByteCount() > 0)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

This is a **snippet**; assuming `request` exists, **the final consumer of `filtered` still bears responsibility for releasing forwarded buffers** once it reads them. `doOnDiscard` handles buffers discarded by supported **upstream** operators. It is not an "auto-release every buffer ever seen" directive. Spring/Project Reactor emphasize checking `Discard Support` in each operator's Javadoc, since not every operator supports discard hooks.

Key characteristics to remember:

- Multiple `doOnDiscard` hooks of the same type can accumulate; avoid registering two incompatible cleanups accidentally.
- Hooks affect only **upstream** operators that see the hook; chain placement matters critically.
- Hooks do not guarantee cleanup for contract-violating publishers, elements dropped after terminal signals, or resources already handed to external systems.
- For retained buffers, a discard event must release only **its corresponding ownership**; never free references still used by another consumer.
- Reactor specifies cleanup hooks should be idempotent/safe if invoked repeatedly; never rely on blind double releases.
- `doFinally` helps log `onComplete`, `onError`, `cancel` or release **subscription-wide shared resources**; it does not maintain a list of buffers needing release.

### 9.2. Why Isn't `doOnCancel` Enough?

Example:

```java
source.doOnCancel(() -> log.info("request cancelled"));
```

This only logs cancellation. If buffers already sit in queues, application collections, or custom operators, logging never frees them. Use buffer-cleanup-aware APIs/operators and handle error branches as well. Custom subscribers/operators storing `DataBuffer`s carry far more cleanup responsibility than a `doOnCancel`.

### 9.3. Be Careful with `doOnNext`

`doOnNext` suits metrics/observation that **neither alters ownership** nor invalidates the buffer. Reading and releasing inside `doOnNext` before downstream receives the buffer causes use-after-release. To convert `DataBuffer` into higher-level data, use `map` with `try/finally` and **do not emit the old buffer downstream**; to forward raw buffers intact to a writer, do not release in `doOnNext`.

### 9.4. Backpressure Does Not Replace Cleanup

Reactive Streams allows subscribers to request element counts, throttling flow, yet **never** auto-releases buffers already retained by application code. Prefetch queues, custom collections, or unbounded `join` still consume large memory even when publishers honor backpressure. You need all of these:

- Byte/message caps and concurrency bounds.
- Fast-enough consumers or coordinated processing.
- Proper cleanup on complete/error/cancel/discard.
- Monitoring active buffer counts and retention durations.

## 10. Streaming Uploads, Responses, and Proxies: Avoiding Broken Ownership

### 10.1. Uploads: Use High-Level Abstractions When Possible

For multipart uploads, `FilePart.transferTo(Path)` writes contents to a file without manually dissecting `DataBuffer`s in the controller. Illustrative **snippet** in a WebFlux controller:

```java
@PostMapping(path = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> upload(@RequestPart("file") FilePart part) {
    return part.transferTo(targetPath);
}
```

This is a **snippet**, not a standalone program: `targetPath` must be validated, confined to an allowed directory, granted safe permissions, and never trust raw client filenames. Configure multipart limits, storage quotas, and temp-file cleanup on upload cancel/error. `transferTo` does not excuse skipping resource controls.

### 10.2. Responses: Never Release Buffers Before the Writer

In custom response streaming:

```java
Flux<DataBuffer> payload = createBodyBuffers();
return response.writeWith(payload);
```

This is a **snippet** with `createBodyBuffers()` and `response` supplied by the system. The HTTP output side normally handles release after writing per Spring's contract. Releasing buffers immediately via `doOnNext` before writing causes downstream to read freed memory.

Conversely, if **your code allocates a buffer and hits an error before emitting it to the publisher**, clean it up immediately in the error path. Read the Javadoc of any custom producers and adapters you use; never generalize one library's example into a universal rule.

### 10.3. `DataBufferUtils.write` Has Multiple Distinct Overloads

Spring Framework 6.x includes overloads:

- `write(source, OutputStream)`.
- `write(source, WritableByteChannel)`.
- `write(source, AsynchronousFileChannel[, position])`.
- `write(source, Path[, options])`.

Overloads returning `Flux<DataBuffer>` when writing to streams/channels **do not automatically release input buffers** and **do not close the supplied stream/channel**; they re-emit buffers downstream. If you write the final consumer, ensure proper release and resource closure. The `Path` overload returns `Mono<Void>` with its own contract. Check the exact API of your Spring version and avoid releasing in both producer and consumer.

### 10.4. `WebClient`: Closing the Response Body Lifecycle

With `WebClient`, prefer:

```java
webClient.get()
        .uri("/items")
        .retrieve()
        .bodyToFlux(Item.class);
```

This is a **snippet** with hypothetical `webClient`/`Item`. Codecs process data once the publisher is subscribed to within a valid lifecycle. With `exchangeToMono`/`exchangeToFlux`, ensure the body is consumed or released per contract. If you only need the status and want to discard the body, call the supported API method (e.g., `ClientResponse.releaseBody()` where appropriate); leaving raw bodies unconsumed can harm connection pools.

Never retain a raw `ClientResponse` outside its callback expecting the body to remain valid indefinitely. And never subscribe once "just to log" and subscribe again in the HTTP handler: body publishers are generally not meant for arbitrary repeated consumption.

### 10.5. Request Body Logging/Tracing Is High-Risk

Request-logging filters easily commit three bugs at once: (1) consuming the body before the controller, (2) retaining buffers without releasing, and (3) leaking sensitive data. Prefer logging metadata like method, URI, content-type, content length, correlation ID, and bounded total byte size. If payload logging is legally/business-mandated, cap logged bytes, redact secrets, define explicit ownership, and test streaming/error/cancel paths. Never push raw buffers onto a separate async logging queue.

## 11. Diagnosing Leaks in Reactor Netty

Common symptoms: process direct memory climbs steadily, memory pool pressure rises, upload/streaming requests fail after running awhile, Netty logs warnings like `LEAK: ByteBuf.release() was not called before it's garbage-collected`, or containers OOM-kill the process.

### 11.1. Enabling Netty Leak Detection in Test Environments

Netty provides leak detection levels such as `SIMPLE`, `ADVANCED`, and `PARANOID`. Configure the JVM system property:

```text
-Dio.netty.leakDetection.level=advanced
```

Apply this flag to the **application JVM** (not only the Gradle daemon). `advanced` is usually helpful during investigation; `paranoid` adds heavy overhead and should be reserved for narrow diagnostic tests. Leak detection uses sampling and relies on garbage collection, so **seeing no warnings does not prove zero leaks**; reported stack traces show where a buffer was accessed/allocated, not necessarily where the missing release logic sits.

### 11.2. Using `DataBufferUtils.touch` to Attach Diagnostic Hints

```java
DataBufferUtils.touch(buffer, "incoming body: upload endpoint");
```

This snippet attaches a hint when the implementation supports leak tracking. It neither retains, releases, nor fixes leaks. Never embed user tokens, request bodies, passwords, or sensitive PII inside hints/logs.

### 11.3. Metrics to Monitor

- Process RSS and direct/native memory alongside Java heap/GC.
- Reactor Netty allocator metrics supported by your runtime version: used/active direct memory and associated pools.
- Open requests/uploads, incomplete streams, cancellation/timeout/error rates.
- Chunk sizes, body sizes, response times, concurrency, queue/prefetch depths.
- Netty leak warnings, `IllegalReferenceCountException`, `DataBufferLimitException`, and root exceptions.
- Before/after comparisons under load; pools may keep allocated memory cached for reuse even with zero leaks.

**Note:** tweaking GC flags or increasing heap will not fix unreleased pooled `ByteBuf`s. Raising the direct-memory limit only delays OOM if the leak remains.

## 12. Testing Strategy to Catch Missing and Extra Releases

### 12.1. Deliberate Reference Count Verification

For units handling Netty `ByteBuf`s, checking refCnt before/after each branch exposes leaks. The Section 8 demo prints four deterministic lines proving one retain demands two releases. A unit test can allocate a buffer via `NettyDataBufferFactory`, pass it through the function under test, and verify refCnt returns to 0 **once ownership finishes consuming it**. Do not demand every buffer hit refCnt 0 inside the very same callback if ownership legitimately transfers to the framework.

### 12.2. Test Every Termination Path

For any custom `Flux<DataBuffer>`, use Reactor `StepVerifier` and related tools to verify:

1. **Normal completion:** every buffer is consumed and released or transferred properly.
2. **Decode throws an exception:** buffers inside the lambda still release via `finally`.
3. **Upstream errors:** buffers accumulated inside `join` are cleaned up and the error propagates.
4. **Client cancel / `take(1)` / timeout:** buffers discarded from queues/prefetch are released.
5. **Filter/skip discards:** hooks at the right position release dropped buffers.
6. **Multiple subscribers/retries:** each subscription receives fresh valid buffers; never share a `refCnt=0` buffer across retries.
7. **Oversized payloads:** fail deterministically without leaking or continuing unbounded reads.
8. **Connection bursts:** no abnormal growth in active pooled buffers after load finishes.

Never write tests that only check response text correctness: leaks often surface silently after tens of thousands of requests. Combine reference-count unit tests with load tests, metrics, and leak detection.

### 12.3. Before/After Verification After Fixing a Bug

Example bug occurring only when `filter` drops buffers:

- Before fix: 10,000 requests with random client cancellations cause unreleased buffer counts to climb continuously.
- After fix: every dropped buffer cleans up via the proper discard contract, forwarded buffers release at the consumer, and active memory returns to a stable baseline across load cycles.
- Also verify the inverse path: retained/forwarded buffers remain valid without triggering `IllegalReferenceCountException`.

These numbers illustrate a test scenario, not production benchmarks. Depending on the allocator, pools may keep allocated memory reserved, so do not expect RSS to drop back to initial baseline after every run.

## 13. Quick Troubleshooting Table by Symptom

| Symptom | Suspect | How to check / fix |
| --- | --- | --- |
| Direct memory climbs over many requests | Final consumer didn't release, extra `retain` | Map ownership, instrument refCnt and leak detector |
| `IllegalReferenceCountException: refCnt: 0` | Released before writer used it, double release | Search for `doOnNext(release)` and overlapping `finally` blocks |
| Valid JSON works, invalid requests leak | Exception path skips releasing raw buffer | Wrap manual decoding in `try/finally`; test error paths |
| Leaks happen only on client cancel | Queue/prefetch/discard missing cleanup | Inspect `doOnDiscard`, operator docs, and cancel tests |
| Leaks after `join` | Caller failed to release **joined result buffer** | Release result after decoding; avoid re-releasing inputs |
| Failure on large input | `join`/codec exceeded memory limit | Set appropriate caps and return 413 where applicable |
| Body logging causes controller to see empty body | Filter subscribed/consumed the stream | Compose/decorate properly; avoid reading twice |
| Large file upload OOMs without leak logs | Unbounded aggregation, copying, huge queues | Stream with bounded in-memory limits/size/concurrency |
| Memory stays high after requests stop | Pool caching vs. real buffer retention | Compare active/used direct memory, GC, RSS, leak logs, and load cycles |
| Tests pass yet production leaks | Missing cancel/timeout/chunking cases, different server | Test Netty pooled implementation and real failure conditions |

## 14. Self-Check

**Q1.** A `PooledDataBuffer` has refCnt=1, and code calls `retain` once. How many balanced `release` calls are needed?  
**Answer:** Two, matching the two valid references; release only when each owner genuinely finishes using the data.

**Q2.** A controller accepts `@RequestBody Mono<OrderRequest>` and returns `Mono<OrderResponse>`. Must it call `DataBufferUtils.release` on the body?  
**Answer:** Application code isn't handling raw `DataBuffer`s; codecs/framework manage normal lifecycles. Only code touching low-level buffers must evaluate concrete ownership.

**Q3.** Code calls `DataBufferUtils.join(flux, 4096)`, then releases each input buffer and finally releases the result buffer. What is wrong?  
**Answer:** `join` already manages input ownership; releasing inputs again risks double release, especially when the result is a composite. Only the final consumer releases the result buffer when done.

**Q4.** Why isn't `doOnDiscard` enough to guarantee zero leaks?  
**Answer:** It only takes effect for discard-supporting operators upstream; normally consumed/forwarded buffers or custom collections still require dedicated cleanup matching ownership.

**Q5.** Does `DataBufferLimitException` equate to a pooled-buffer leak?  
**Answer:** No. It indicates accumulated/decoded bytes exceeded the configured limit; separate it from resource leaks and design limits/streaming accordingly.

**Q6.** An HTTP response uses `response.writeWith(flux)`; should you place `doOnNext(DataBufferUtils::release)` before the writer "just to be sure there's no leak"?  
**Answer:** No. That can release buffers before the writer reads them and cause use-after-release. Let ownership transfer per the writer's contract, and clean up buffers in producer error paths only if never emitted.

## 15. Checklist Before Merging Custom `DataBuffer` Code

- [ ] Clear justification exists for raw `DataBuffer` over codecs/DTOs/`FilePart`.
- [ ] Identified the actual runtime implementation and whether it is pooled/reference-counted.
- [ ] Every created/received buffer has a clear final owner and deterministic transfer or release path.
- [ ] Every `retain` has a matching `release` path across complete/error/cancel.
- [ ] Buffers handed to writers/framework are never released prematurely.
- [ ] Buffers read and converted into independent types are released in `finally`.
- [ ] `join` enforces an appropriate cap; callers release only the result and never double-release inputs.
- [ ] Checked discard/prefetch/queues and placed `doOnDiscard` per operator Javadoc.
- [ ] Never re-subscribe bodies multiple times or cache raw buffers unboundedly.
- [ ] Uploads/streams enforce byte limits, timeouts, concurrency limits, and cancellation cleanup.
- [ ] Tested happy paths, decode errors, timeouts, client disconnects, and buffer-limit errors.
- [ ] Monitored direct memory, allocator metrics, leak warnings, and use-after-release errors.
- [ ] Verified code on the exact Spring Boot/Spring Framework/Netty target versions.

## Official References

- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework 6.1 — DataBufferUtils API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework — WebFlux Reactive Core, DataBuffer](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Project Reactor — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html)
- [Project Reactor — Flux.doOnDiscard API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)

When working with raw buffers, what matters is not merely "did we call release" but **every ownership reference lives until the right moment and is transferred or terminated exactly once**. The best design keeps byte manipulation narrow, uses APIs with clear lifecycles, bounds memory accumulation, and tests cancellation and error paths before shipping under load.