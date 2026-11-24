# DataBuffer, Pooled Buffers, and Release Responsibility in Spring WebFlux

## 1. Goal and Real-World Problem

In Spring WebFlux, an HTTP body does not necessarily appear all at once as a `String` or `byte[]`. When downloading files, streaming video, proxying a data stream, or reading large payloads, the infrastructure typically processes **`Flux<DataBuffer>`**—a sequence of byte chunks. Some chunks use **pooled/direct memory** managed via reference counting; receiving a buffer without returning it on time causes a memory leak, whereas releasing it too early causes errors from accessing memory that has already been reused.

This lesson belongs to **Streaming WebFlux**, targeting **Java 17+, Spring Framework 6.x, Spring Boot 3.x, Project Reactor**. The focus is not merely knowing to call `DataBufferUtils.release`, but accurately answering **who owns the buffer at each step**.

After this lesson, you will be able to:

- Explain `DataBuffer`, `DataBufferFactory`, `DefaultDataBuffer`, `NettyDataBuffer`, `PooledDataBuffer`, and `DataBufferUtils`.
- Understand direct vs. heap memory, pooling, and reference counting (`retain`/`release`).
- Distinguish **read-and-discard** from **transferring ownership to the next consumer**.
- Know when you **must release manually** and when you **must never release manually** because WebFlux/codec/HTTP writer owns it.
- Write `Flux<DataBuffer>` pipelines handling `onNext`, `onError`, `cancel`, and discarded buffers properly.
- Use `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` in the right place; avoid misusing `doFinally` to release buffers whose ownership was transferred.
- Understand `DataBufferUtils.join(...)`, `maxByteCount`, `DataBufferLimitException`, zero-copy composites, and memory limits.
- Distinguish variants of `DataBufferUtils.write(...)`, file channels, and response writing.
- Build a Spring Boot WebFlux example with a bounded byte-receiving endpoint and a streaming byte-returning endpoint; test with `WebTestClient` and Reactor.
- Diagnose leaks, double-releases, use-after-release, native memory growth, and resource limits.

**Scope:** WebFlux reactive streaming, not standalone Java `ByteBuffer`. Code uses Spring Boot 3.x/WebFlux, where applications typically run on Reactor Netty. Exact behaviors of native buffer allocators can vary by HTTP server/framework version; rely on API contracts and tests rather than hardcoding reference counts across implementations.

## 2. Where Does DataBuffer Sit in the HTTP Pipeline?

```text
HTTP network -> Reactor Netty ByteBuf
                         |
                         v
                  NettyDataBuffer
                         |
                   Flux<DataBuffer>
                         |
           +-------------+--------------+
           |             |              |
           v             v              v
       JSON decoder  custom transform  raw streaming/file
           |             |              |
           v             v              v
       Java DTO        bytes/frames   DataBuffer stream
           |             |              |
           +-------------+--------------+
                         |
                         v
               HTTP response writer
                         |
                         v
                 release/cleanup
```

`DataBuffer` abstracts a byte chunk regardless of whether the backing platform is Netty, Jetty, an array, or `ByteBuffer`. The framework has `Encoder`, `Decoder`, message readers/writers, and transport handlers to manage them.

A typical endpoint:

```java
@PostMapping("/users")
public Mono<UserDto> create(@RequestBody Mono<UserInput> body) {
    return body.flatMap(service::create);
}
```

This is a **snippet**, not a standalone file. Application code does not directly see `DataBuffer` because the message reader/Jackson decoder owns the raw buffers and releases them per the codec contract. Adding `DataBufferUtils.release(...)` inside a DTO controller makes no sense.

You only handle raw `DataBuffer` when actively participating in the byte-level path such as uploads/proxies/filters/custom decoders/binary transforms. In that case, you must define ownership explicitly.

## 3. Key Interfaces and Classes

| Component | Responsibility |
| --- | --- |
| `DataBuffer` | Byte buffer abstraction: read/write, positions, readable/writable byte counts |
| `DataBufferFactory` | Allocates or wraps a byte array/ByteBuffer into a DataBuffer |
| `DefaultDataBufferFactory` | Factory typically using heap/NIO buffers without Netty-style reference counting |
| `NettyDataBufferFactory` | Factory backed by Netty `ByteBufAllocator` |
| `PooledDataBuffer` | DataBuffer extension with `retain()`, `release()`, `isAllocated()` |
| `CloseableDataBuffer` | Close API when a buffer supports AutoCloseable-style lifecycle |
| `DataBufferUtils` | Helpers for read/write/join/release/retain/touch and byte-count operations |
| `DataBufferLimitException` | Error when total bytes to buffer exceed a configured limit |
| `DataBufferUtils.releaseConsumer()` | Consumer calling release on each DataBuffer |
| `DataBufferUtils.join(...)` | Joins a Flux of buffers into one DataBuffer (potentially composite) |
| `DataBufferUtils.read(...)` | Turns a file/resource/channel into a Flux of buffers |
| `ServerHttpResponse.writeWith(...)` | Writes `Publisher<DataBuffer>` to the response body |

Classes reside in `org.springframework.core.io.buffer`, except HTTP request/response types belonging to Spring Web reactive HTTP APIs.

Do not confuse `org.springframework.core.io.buffer.DataBuffer` with `java.nio.ByteBuffer`: DataBuffer has its own memory management/pooled ownership semantics, especially when wrapping Netty `ByteBuf`.

## 4. Heap Memory, Direct Memory, and Pooled Memory

### Heap Buffer

A buffer backed by a Java `byte[]` generally lives on the JVM heap; the garbage collector manages the array's lifetime. `DefaultDataBufferFactory` can use this style. `DataBufferUtils.release` on a non-pooled/non-closeable buffer may return `false` since there is no native reference to decrement.

**This does not make the code leak-safe across transports.** If tests only run with `DefaultDataBufferFactory`, a missing release bug may stay hidden; Netty deployments using pooled direct memory will still leak.

### Direct Buffer

`ByteBuffer.allocateDirect`/Netty direct buffers can use off-heap memory to reduce copies during I/O. That memory is **not fully visible** via `Runtime.totalMemory()-freeMemory()`; leaks can trigger OOM/direct-memory pressure even while Java heap has plenty of room.

### Pool

Allocating and destroying thousands of buffers repeatedly has overhead. Pooling returns memory regions to the allocator for reuse. However, **a buffer returned to the pool can immediately be reused by another request**; if code keeps reading after release, data may be corrupted, exceptions thrown, or dangerous native-layer bugs triggered.

Never assume "GC will release the buffer on time" for reference-counted `PooledDataBuffer` instances. Pool ownership must be resolved by intentional release at the boundary.

## 5. Reference Counting: retain and release

`PooledDataBuffer` per Spring semantics:

```text
allocate()      refCount ≈ 1 (initial owner)
retain()        refCount ≈ 2 (adds a reference responsible for releasing)
release()       refCount ≈ 1
release()       refCount ≈ 0 -> allocator may reuse memory
```

The `≈` sign emphasizes this is a **simplified model**; allocators/shared slices/composite buffers have their own details.

- `retain()` keeps a buffer alive longer by incrementing the reference count if pooled.
- `release()` decrements the owned reference count; at 0, the memory region is considered returned.
- `isAllocated()` reflects status per the PooledDataBuffer contract.
- `DataBufferUtils.retain(dataBuffer)` retains only when appropriate; more portable than manual casting.
- `DataBufferUtils.release(dataBuffer)` releases when the buffer is pooled or closeable per API; may return true/false depending on release behavior.
- **Every ownership reference added via retain must have a matching release**.
- Never call release twice on **the same ownership**.
- Never retain "just in case" without designing release paths across success/error/cancel.

Memory checked out from a pool is not an immutable business object you can arbitrarily cache or share across threads. If you need to keep a payload beyond the HTTP request, **copy the data into a bounded `byte[]`/storage**, or manage retain/release with explicit ownership.

## 6. The Golden Rule: Who Is the Final Consumer?

| Situation | Who Holds Final Responsibility? | Action |
| --- | --- | --- |
| Controller receives `Mono<DTO>` from `@RequestBody` | Decoder/WebFlux | Do not manually release DTO |
| Code reads a `DataBuffer` directly, turns it into String/DTO, and discards buffer | That code | Release in `finally` |
| Code merges buffers via `DataBufferUtils.join` | Join manages component buffers; consumer of result manages joined buffer | Release the **joined result** once |
| Code creates buffer and passes it to `ServerHttpResponse.writeWith` | HTTP writer after receiving ownership | Do not release early in controller |
| Code creates buffer, but encoding fails **before handoff** | Code that created the buffer | Release in catch/finally |
| Code filters/drops a DataBuffer along the way | Pipeline/filter that dropped it | Release discarded buffers, e.g., `doOnDiscard` |
| Code needs to hold a pooled buffer beyond the current lifecycle | Holder of the extra reference | `retain` when keeping; `release` when done |
| Code uses `DataBufferUtils.write(..., OutputStream)` | Caller manages channel and handles returned buffers | Per contract, output stream is not closed and buffers are not auto-released |
| Code only calls `Flux<DataBuffer>.map(...)` to inspect and forwards same buffer | Final downstream if ownership is explicitly transferred | Do not release while still forwarding |

**There is no blanket rule "call release immediately whenever you see a DataBuffer."** Rather: **whenever a party finishes consuming ownership, it must release; if it transfers ownership to another party, it must not release that part itself**.

## 7. Using DataBufferFactory Properly

In a WebFlux HTTP handler, a factory is available on the response:

```java
DataBufferFactory factory = response.bufferFactory();
byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
DataBuffer buffer = factory.wrap(bytes);
```

This is a snippet in a method with `ServerHttpResponse response` and Spring/Java imports. `wrap(byte[])` wraps existing data; `allocateBuffer(initialCapacity)` allocates a new buffer.

```java
DataBuffer buffer = factory.allocateBuffer(64);
buffer.write("hello".getBytes(StandardCharsets.UTF_8));
```

Avoid the no-arg `allocateBuffer()` when a reasonable capacity is known (the no-arg method is deprecated in Spring Framework 6.0+). Setting `64` is an initial capacity, **not** a payload limit: DataBuffer implementations can expand if more bytes are written.

**If wrapping a mutable underlying `byte[]`, never mutate that array after handing off the buffer**; doing so risks data races/corruption. For small responses, simply returning `Mono<String>`/DTO lets the encoder manage everything instead of raw DataBuffers.

### How Do wrap and allocate Differ Regarding Pooling?

The specific factory decides whether `wrap` copies or uses pooling. `DefaultDataBufferFactory` and `NettyDataBufferFactory` differ in implementation. Do not rely on "wrap doesn't copy" to assume reference counts always increase or release is unnecessary. If you only need a standard text/JSON API, let framework encoders decide.

## 8. Reading a Buffer and Releasing in finally

Example converting a raw `DataBuffer` into `byte[]`:

```java
static byte[] consumeBytes(DataBuffer buffer) {
    try {
        byte[] out = new byte[buffer.readableByteCount()];
        buffer.read(out);
        return out;
    } finally {
        DataBufferUtils.release(buffer);
    }
}
```

**This is a complete method ready to place inside a class with imports** for `org.springframework.core.io.buffer.DataBuffer` and `DataBufferUtils`, though it will **not** compile standalone without Spring libraries and a class wrapper.

Ownership: this method **takes and consumes full ownership of the input buffer**. It returns an independent `byte[]` and releases the buffer even if `read(...)` throws. Never pass a buffer into this method if the HTTP writer or another downstream consumer still needs it without a separate reference/ownership.

**Memory warning:** Allocating `byte[]` sized to `readableByteCount()` can allocate hugely if input is unbounded. Use only after enforcing request size and total byte limits. For streaming multi-GB files, process buffer-by-buffer within memory bounds rather than collecting everything onto the heap.

## 9. Anti-Pattern: Releasing Before response.writeWith

**Wrong:**

```java
DataBuffer db = response.bufferFactory()
    .wrap("hello".getBytes(StandardCharsets.UTF_8));

DataBufferUtils.release(db);       // Ownership was released too early!
return response.writeWith(Mono.just(db));
```

This is an **anti-pattern**—do not put it into a project. If `db` is pooled and `refCount` hit 0, the HTTP writer may read memory already reclaimed by the allocator.

**Right when transferring ownership to the HTTP writer:**

```java
DataBuffer db = response.bufferFactory()
    .wrap("hello".getBytes(StandardCharsets.UTF_8));
return response.writeWith(Mono.just(db));
```

This is also a snippet in a method returning `Mono<Void>` with `response`. Once handed to `writeWith`, code must not release that buffer itself after emission. The writer/transport layer is responsible per contract. If the method allocates a buffer and fails **before returning/handing off the Publisher**, the allocating code must clean up that reference.

**Do not attach `doOnNext(DataBufferUtils::release)` to a source sent into an HTTP response.** It can expire the buffer before the response writer uses it.

## 10. Reactive Operators Can Drop or Hold Buffers

Reactor operators like `filter`, `skip`, `take`, `flatMap`, `buffer`, and `window` can drop elements or hold them in internal queues. When elements are pooled `DataBuffer`s, you must account for both the **forwarded path** and the **discarded path**.

Example filtering out empty buffers:

```java
Flux<DataBuffer> nonEmpty = incoming
    .filter(db -> db.readableByteCount() > 0)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

This snippet assumes an existing `Flux<DataBuffer> incoming`. For dropped buffers, `doOnDiscard` releases them when the operator supports discard hooks. **Buffers retained in `nonEmpty` still must be released or owned by the final consumer**—`doOnDiscard` does not release elements sent downstream.

If the pipeline transforms into DTOs/bytes:

```java
Flux<byte[]> payloads = incoming
    .filter(db -> db.readableByteCount() > 0)
    .map(db -> {
        try {
            byte[] out = new byte[db.readableByteCount()];
            db.read(out);
            return out;
        } finally {
            DataBufferUtils.release(db);
        }
    })
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

This snippet illustrates a pipeline with `incoming`. `map` processes passing buffers; `filter` may discard. With complex internal operators, place `doOnDiscard` where the hook sees the relevant upstream/downstream discards per Reactor semantics. Do not expect `doOnDiscard` to manage ownership held in local variables outside Reactor or inside every custom operator.

### Cancellation and Discarded Buffers

When a client disconnects/cancels, operators with prefetch/queues may drop queued elements; some operators invoke discard hooks for cleanup. However, if the application stores buffers in a `Map`, `List`, or shared queue, `doOnDiscard` does not manage those external references: you must explicitly release them on completion/error/cancel.

## 11. Why Can't doFinally Replace Releasing Each DataBuffer?

An anti-pattern:

```java
Flux<DataBuffer> source = incoming
    .doFinally(signal -> System.out.println("done"));
```

`doFinally` runs **once per subscription termination/cancellation at that operator's position**, not once per buffer. Merely logging here does not release elements already emitted and dropped. If you hold a `List<DataBuffer>` in scope, using `doFinally` to clean up the list can work **provided ownership, exactly-once cleanup, and no downstream handoff are guaranteed**, yet this pattern easily races between cancellation and async writes.

Better:

- Release each buffer directly upon finishing consumption (`try/finally`, `doOnNext` at the right boundary).
- Use `doOnDiscard` for operator-dropped elements.
- Use `DataBufferUtils.join` for bounded aggregation.
- Use `using/usingWhen` to manage resources like files/channels/connections (not a substitute for individual DataBuffer ownership).
- Let the response writer manage buffers passed to `writeWith`.

**Never release the same buffer in both `map finally` and a downstream `doOnNext`**, as that causes double-release.

## 12. DataBufferUtils.release, retain, touch

Standard helpers:

```java
DataBufferUtils.retain(buffer);   // Increment ref if buffer is pooled.
DataBufferUtils.release(buffer);  // Decrement ref/close if supported by implementation.
DataBufferUtils.touch(buffer, "request-123");
```

These are snippets. `touch` attaches a hint if the buffer supports leak tracking; hints **do not** replace releasing and should never contain tokens/PII.

### When to retain?

Suppose you hold a buffer owned by **one owner** and must also hand it to an independent consumer. Whenever and only when two ownership references are needed:

```text
Owner A             Owner B
  |                   |
  | -- retain(buf) -->|  (adds 1 reference)
  |                   |
  | release(buf)      |  Owner A done
  |                   |
  |                release(buf)  Owner B done
```

If A simply **transfers** sole ownership to B, **no retain is needed**; A must not release afterward. Retaining unnecessarily and releasing only once leaks a reference; A releasing before retaining for B causes use-after-release.

### Checking Allocation State

`PooledDataBuffer.isAllocated()` checks whether a buffer is still allocated. It is not a guarantee that "any thread can safely read" nor proof of sole ownership; multiple owners may hold references simultaneously. Never use check-then-use as synchronization across concurrent threads. Ownership and thread safety must be rigorously designed.

## 13. DataBufferUtils.join: Merging, Bounds, and Composites

`DataBufferUtils.join(Publisher<? extends DataBuffer>)` merges a stream into a single `Mono<DataBuffer>`. The result may either:

- Copy bytes into a new buffer; or
- Form a **composite/zero-copy** buffer holding references to component buffers.

Behavior depends on implementation; never assume `join` always copies or is always zero-copy.

**Special ownership rules:**

1. Buffers **successfully fed into join** are managed by the aggregate/composite—**do not release component buffers individually again**.
2. If join encounters an error or cancellation before completing, Spring releases accumulated buffers per the API contract.
3. **The consumer of the joined DataBuffer result** must release the **joined result** after reading it.
4. Do not release both the joined result and its components, as that can double-release.

### Limiting maxByteCount

```java
Mono<DataBuffer> bounded =
    DataBufferUtils.join(request.getBody(), 64 * 1024);
```

This is a snippet in a method with `ServerHttpRequest request`. `64 * 1024` = 65,536 bytes, the **total buffer capacity** in the join step. Exceeding it emits `DataBufferLimitException` rather than allocating a multi-GB byte array before checking length.

Note: Bounding `join` protects **that specific aggregation**, not HTTP server limits, decoders, gateways, upload quotas, CPU, or total in-flight requests. If 2,000 clients simultaneously allocate 65 KiB buffers, total memory is still substantial.

### Releasing the Joined Result in the Right Place

```java
return DataBufferUtils.join(request.getBody(), 65536)
    .map(joined -> {
        try {
            byte[] bytes = new byte[joined.readableByteCount()];
            joined.read(bytes);
            return calculate(bytes);
        } finally {
            DataBufferUtils.release(joined);
        }
    });
```

Snippet assuming `calculate(byte[])` returns a DTO; you can add `onErrorMap(DataBufferLimitException.class,...)` to map to HTTP 413. `map` receives only the completed joined buffer; if join is cancelled/errors before emitting, Spring manages accumulated buffers. Each joined result is released once in `finally`.

## 14. DataBufferUtils.write: Overloads Are Not Identical

`DataBufferUtils.write` has several signatures; do not lump them all into "write auto-releases".

| Variant | Return Type | Key Point |
| --- | --- | --- |
| `write(source, OutputStream)` | `Flux<DataBuffer>` | Does not close OutputStream and **does not auto-release buffers** |
| `write(source, WritableByteChannel)` | `Flux<DataBuffer>` | Does not close channel, does not auto-release buffers |
| `write(source, AsynchronousFileChannel)` | `Flux<DataBuffer>` | Does not close channel, does not auto-release buffers |
| `write(source, AsynchronousFileChannel, position)` | `Flux<DataBuffer>` | Also needs explicit ownership/close policy |
| `write(source, Path, OpenOption...)` | `Mono<Void>` | File write API manages the file channel per implementation; check Javadoc when using, do not conflate with Flux overloads |
| `read(Path, factory, size)` | `Flux<DataBuffer>` | Streams a file; API ensures closing the file when the Flux finishes |
| `join(source, max)` | `Mono<DataBuffer>` | Bounded aggregation; release joined result after use |

Example with `OutputStream` (illustrating a **blocking API**—never place directly on the Netty event loop):

```java
Flux<DataBuffer> written =
    DataBufferUtils.write(source, outputStream)
        .doOnNext(DataBufferUtils.releaseConsumer())
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

This snippet requires `source` and `outputStream` to be created/closed by the proper owner. `write(source, outputStream)` executes on subscription without closing the stream; `doOnNext` releases buffers emitted by the writer **after writing**. For prefetch/cancel, the discard hook releases in operators supporting discard. A complete implementation must also close the stream on complete/error/cancel, isolate blocking via an appropriate scheduler, and handle error paths before buffers reach `doOnNext`.

For actual file uploads, prefer `FilePart.transferTo(Path)` when appropriate, enforcing size limits, filename/path validation, storage authorization, and cleanup. Use low-level `write` only when byte-level control is truly needed.

## 15. Custom Decoders and Encoders: Ownership Handoff Points

Spring defines clear rules for codecs:

### Decoder

The decoder is the final party directly reading a buffer before producing a higher-level object (`String`/DTO/JSON). Once done reading and not forwarding the `DataBuffer`, **the decoder releases the buffer**.

```java
.map(buffer -> {
    try {
        return deserialize(buffer);
    } finally {
        DataBufferUtils.release(buffer);
    }
})
.doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

This snippet needs a `deserialize` implementation and upstream source. Each input buffer must be released after reading; the discard hook covers branches that do not route buffers into `map`. If a decoder merges multiple buffers, use `join`/bounded aggregation and release the **aggregate** properly; never store pooled objects in long-lived fields.

### Encoder

The encoder allocates a `DataBuffer` and passes it downstream to the HTTP response writer. When encoding succeeds, the encoder **transfers** ownership rather than releasing early. If encoding/serialization throws **before handoff**, the encoder must clean up.

```java
DataBuffer buffer = factory.allocateBuffer(256);
boolean transferred = false;
try {
    writeSerializedValue(buffer, value);
    transferred = true;
    return buffer;
} finally {
    if (!transferred) {
        DataBufferUtils.release(buffer);
    }
}
```

This snippet illustrates a method with `factory`, `value`, and `writeSerializedValue`. It covers exceptions **before return/handoff**; when a downstream filter or HTTP writer rejects/cancels, pipeline release/discard paths must also be designed. Do not treat this snippet as a production custom encoder without testing error/cancel cases.

**Important:** "Creator releases" applies only when creation fails before handoff; once the encoder hands the buffer to the writer, the **writer** is the responsible consumer per contract.

## 16. WebClient: Consuming or Releasing the Response Body

`WebClient` typically uses high-level methods:

```java
Mono<UserDto> user = webClient.get()
    .uri("/users/{id}", id)
    .retrieve()
    .bodyToMono(UserDto.class);
```

This snippet belongs in a service with `webClient`/`UserDto`. Framework codecs decode and manage DataBuffers; your code only receives DTOs and never manually releases raw buffers.

When inspecting status/body conditionally:

```java
Mono<String> result = webClient.get()
    .uri("/status")
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(String.class);
        }
        return response.createError();
    });
```

`exchangeToMono`/`exchangeToFlux` checks for unconsumed response bodies when the returned publisher completes and releases them to avoid leaks. **Do not use raw response exchange APIs and forget to consume/release the body.** Never return `ClientResponse` outside the callback to read the body later when the callback contract forbids it.

### When Explicitly Consuming DataBuffer from WebClient

If you call `response.bodyToFlux(DataBuffer.class)`, the raw consumer takes corresponding responsibility:

- If merely reading/copying the buffer into a DTO, release after reading.
- If relaying to `ServerHttpResponse.writeWith`, transfer ownership per contract and **do not release on the forwarding branch**.
- If filtering out a buffer or cancelling, release buffers still under your ownership.
- Never pass the same cold `Flux<DataBuffer>` to two unintended subscriptions; a network response body is not a repeatable collection.

In an HTTP proxy, beyond reference counts you must propagate backpressure, status/headers, cancellation, timeouts, hop-by-hop header filtering, and request size limits. Do not turn it into an unbounded `collectList`.

## 17. HTTP Response Streaming: Transferring Ownership Properly

A controller can return `Mono<Void>` and write raw buffers:

```java
@GetMapping("/download")
public Mono<Void> download(ServerHttpResponse response) {
    response.getHeaders()
        .setContentType(MediaType.APPLICATION_OCTET_STREAM);

    Flux<DataBuffer> buffers = Flux.defer(() ->
        Flux.just("alpha\n", "beta\n")
            .map(text -> response.bufferFactory().wrap(
                text.getBytes(StandardCharsets.UTF_8))));

    return response.writeWith(buffers);
}
```

This is a snippet; the complete runnable file is in the hands-on section. Here `response.writeWith` is the final owner per the HTTP server; **do not attach `.doOnNext(DataBufferUtils::release)`** to the buffers. `Flux.defer` ensures each subscription creates a fresh pipeline/source, though controller handlers are normally invoked per HTTP request; do not treat `defer` as a cure-all for ownership bugs.

### When Can You Return Flux<DataBuffer> Directly?

In an annotated WebFlux controller you can return reactive body types when handlers/codecs support them; however, `ServerHttpResponse.writeWith` makes ownership explicit. Functional handlers can also use `ServerResponse.ok().body(bufferFlux, DataBuffer.class)`. Either way, distinguish which producer allocates buffers, which HTTP writer consumes them, and which operators might discard them.

Do not casually call `Flux<DataBuffer>.cache()`: caching retains references to pooled buffers that the HTTP writer may already have released, causing invalid data on subsequent subscriptions. If content must be cached, cache `byte[]`/immutable domain data with size+TTL policies and allocate **fresh** DataBuffers per response.

## 18. Runnable Spring Boot 3 Java 17+ Application

Create a Maven project from Spring Initializr with:

- **Java 17+**.
- **Spring Boot 3.x**.
- `spring-boot-starter-webflux` (Reactor, Netty, Jackson).
- `spring-boot-starter-test` (test scope).
- `reactor-test` (test scope if not included by your version's starter-test).

Do not add `spring-boot-starter-web` if you want Boot to auto-select the reactive application type with only the WebFlux starter present. This app requires no database or real file upload. It provides:

- `POST /api/buffers/crc32` accepts an `application/octet-stream` binary body, joins **up to 65,536 bytes**, computes CRC32, and returns JSON; **releases the joined result in finally**.
- `GET /api/buffers/download` creates two text buffers and hands them directly to the HTTP writer.
- `DataBufferLimitException` is mapped to **413 Payload Too Large** on the receiving endpoint.

Structure:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  BufferController.java
src/test/java/com/example/demo/
  BufferControllerTest.java
  BufferOwnershipTest.java
```

### 18.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 18.2. BufferController.java

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;
import java.util.zip.CRC32;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/buffers")
public class BufferController {

    private static final int MAX_BYTES = 64 * 1024;

    @PostMapping(path = "/crc32",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Digest> crc32(ServerHttpRequest request) {

        return DataBufferUtils.join(request.getBody(), MAX_BYTES)
            .map(joined -> {
                try {
                    // MAX_BYTES is enforced before byte[] allocation.
                    byte[] bytes = new byte[joined.readableByteCount()];
                    joined.read(bytes);

                    CRC32 crc = new CRC32();
                    crc.update(bytes);
                    return new Digest(bytes.length,
                        String.format("%08x", crc.getValue()));
                } finally {
                    // We consume the joined result, so we release it ourselves.
                    DataBufferUtils.release(joined);
                }
            })
            .switchIfEmpty(Mono.just(new Digest(0, "00000000")))
            .onErrorMap(DataBufferLimitException.class, ex ->
                new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "body too large", ex));
    }

    @GetMapping(path = "/download",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public Mono<Void> download(ServerHttpResponse response) {
        response.getHeaders()
            .setContentType(MediaType.APPLICATION_OCTET_STREAM);

        // Create fresh buffers per subscription.
        Flux<DataBuffer> payload = Flux.defer(() ->
            Flux.just("alpha\n", "beta\n")
                .map(text -> response.bufferFactory().wrap(
                    text.getBytes(StandardCharsets.UTF_8))));

        // Transfer ownership to the HTTP response writer.
        return response.writeWith(payload);
    }

    public record Digest(int length, String crc32) {}
}
```

**Ownership analysis for the crc32 endpoint:**

1. `ServerHttpRequest.getBody()` provides `Flux<DataBuffer>`.
2. `DataBufferUtils.join(source, 65536)` takes in component buffers and manages accumulated buffers on success, cancellation, or error.
3. `map(joined -> ...)` consumes the **joined result**, copying bounded bytes onto the heap to compute the checksum.
4. `finally` releases the joined result exactly once, even if `CRC32`/reading throws.
5. If total bytes exceed 65,536, `join` signals `DataBufferLimitException`; accumulated buffers are managed by `join`, so there is **no joined result left for you to release**.
6. If the request body is empty and `join` completes empty, it returns `Digest(0,"00000000")`.
7. `onErrorMap` only translates the error to a response exception; it does not alter reference-count semantics.
8. Neither `block()` nor manual `subscribe()` is called in the controller.

**Download analysis:** `response.writeWith(payload)` is the final consumer/owner. Code retains no buffer after passing it into the publisher, does not double-release, and does not cache pooled memory. The payload is tiny, yet the pattern scales to bounded streaming from files/channels using `DataBufferUtils.read` with a clear lifecycle.

**Production caveat:** CRC32 is only an accidental-error checksum, **not a cryptographic signature and not tamper-resistant**. If an API needs attack-resistant integrity, use HMAC/SHA-256 appropriately and never mistake checksums for authentication. The demo endpoint does not authenticate callers; production requires gateway/security limits as well.

### 18.3. Starting the App

macOS/Linux:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

If `server.port` is unset, the app normally listens on port 8080. Do not compile these Spring files with bare `javac BufferController.java` without Maven/Gradle dependencies.

## 19. curl: Testing CRC32, Limits, and Streaming

### Sending the 5 Bytes "hello"

```bash
curl -i -X POST \
  'http://localhost:8080/api/buffers/crc32' \
  -H 'Content-Type: application/octet-stream' \
  -H 'Accept: application/json' \
  --data-binary 'hello'
```

Expected HTTP **200**:

```json
{"length":5,"crc32":"3610a686"}
```

This is the CRC32 of the 5 UTF-8 ASCII bytes `hello` (no newline). Using `echo hello | curl --data-binary @-` may append a newline on stdin and change the CRC32/length. Use `printf 'hello'` or literal `--data-binary 'hello'` to match the output above.

### Sending an Empty Body

```bash
curl -i -X POST \
  'http://localhost:8080/api/buffers/crc32' \
  -H 'Content-Type: application/octet-stream' \
  --data-binary ''
```

Expected JSON `{"length":0,"crc32":"00000000"}` when an empty HTTP body is received as in the demo. Omitting `Content-Type` may fail to match the endpoint before code inspects the body.

### Body Exceeding 64 KiB

No need to send MBs/GBs. Locally, use a script generating exactly 65,537 bytes:

```bash
python -c "import sys; sys.stdout.buffer.write(b'x' * 65537)" \
  | curl -sS -i -X POST \
      'http://localhost:8080/api/buffers/crc32' \
      -H 'Content-Type: application/octet-stream' \
      --data-binary @-
```

Expected HTTP **413 Payload Too Large** from `DataBufferLimitException` mapped in the controller if the request reaches `join`. Gateways/servers may enforce request limits earlier. Never send large payloads to servers outside authorized test environments.

### Downloading Raw Binary Stream

```bash
curl -i 'http://localhost:8080/api/buffers/download'
```

Exact HTTP body (UTF-8, two newlines):

```text
alpha
beta
```

The server may chunk or add transfer headers; **never** assume two `DataBuffer` instances always equal two TCP packets. Automatic headers may vary by web server. Never hardcode `Content-Length` if the streaming response length is unknown.

## 20. WebTestClient Testing the HTTP Endpoints

File `src/test/java/com/example/demo/BufferControllerTest.java`:

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BufferControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void crc32OfHelloHasExpectedLengthAndHex() {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);

        client.post().uri("/api/buffers/crc32")
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(bytes)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.length").isEqualTo(5)
            .jsonPath("$.crc32").isEqualTo("3610a686");
    }

    @Test
    void tooLargeBodyBecomes413() {
        byte[] bytes = new byte[65537];

        client.post().uri("/api/buffers/crc32")
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(bytes)
            .exchange()
            .expectStatus().isEqualTo(413);
    }

    @Test
    void downloadContainsExpectedBytes() {
        byte[] expected =
            "alpha\nbeta\n".getBytes(StandardCharsets.UTF_8);

        client.get().uri("/api/buffers/download")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_OCTET_STREAM)
            .expectBody()
            .consumeWith(result ->
                assertArrayEquals(expected, result.getResponseBody()));
    }
}
```

Run:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

These tests are **sample source code** for Boot 3/WebFlux test dependencies, not a claim of execution on the user's repository. `WebTestClient` goes through the WebFlux HTTP server with `RANDOM_PORT`; however, it does not automatically simulate reverse proxies, client disconnects, or every Netty leak detection mode.

**Key point:** Asserting HTTP 200/413 and exact bytes **does not prove** native reference counts returned to 0 on every path. Add unit tests for pooled buffers, cancellation tests, and soak/load tests with leak detection enabled.

## 21. Testing Pooled Ownership with NettyDataBufferFactory

Spring Boot WebFlux defaults to Reactor Netty and includes Netty `ByteBufAllocator`. File `src/test/java/com/example/demo/BufferOwnershipTest.java`:

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import io.netty.buffer.PooledByteBufAllocator;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.NettyDataBuffer;
import org.springframework.core.io.buffer.NettyDataBufferFactory;

import static org.junit.jupiter.api.Assertions.*;

class BufferOwnershipTest {

    @Test
    void retainedBufferNeedsMatchingReleases() {
        NettyDataBufferFactory factory =
            new NettyDataBufferFactory(
                PooledByteBufAllocator.DEFAULT);

        NettyDataBuffer buffer = factory.allocateBuffer(32);
        buffer.write("ok".getBytes(StandardCharsets.UTF_8));

        assertTrue(buffer.isAllocated());

        DataBufferUtils.retain(buffer);   // +1 reference
        DataBufferUtils.release(buffer);  // First release.
        assertTrue(buffer.isAllocated()); // Second ref still remains.

        DataBufferUtils.release(buffer);  // Final release.
        assertFalse(buffer.isAllocated());
    }

    @Test
    void joinedBufferCanBeReleasedAsOneUnit() {
        NettyDataBufferFactory factory =
            new NettyDataBufferFactory(
                PooledByteBufAllocator.DEFAULT);

        NettyDataBuffer a = factory.allocateBuffer(8);
        NettyDataBuffer b = factory.allocateBuffer(8);
        a.write(new byte[]{1, 2});
        b.write(new byte[]{3, 4});

        // join takes over management of the component buffers.
        var joined = DataBufferUtils.join(
            reactor.core.publisher.Flux.just(a, b),
            32).block();

        assertNotNull(joined);
        try {
            byte[] bytes = new byte[joined.readableByteCount()];
            joined.read(bytes);
            assertArrayEquals(
                new byte[]{1, 2, 3, 4}, bytes);
        } finally {
            DataBufferUtils.release(joined);
        }
        // Do not call release(a) or release(b) again.
    }
}
```

**Notes on the nature of these tests:**

- Netty `PooledByteBufAllocator.DEFAULT` requires Netty on the classpath. `spring-boot-starter-webflux` with Reactor Netty provides the Netty 4 dependency in standard Boot 3, though if you switch server stacks you must declare the right test dependency.
- The first test illustrates retaining/releasing two ownership references and `isAllocated`. Production code should never unconditionally call release twice on a buffer without knowing whether it was retained.
- The second test uses `join` and releases the **single joined result**, not `a` or `b`. If `join` fails before creating a result, the `join` contract manages accumulated buffers; advanced tests should also verify error/cancel branches.
- `block()` is used only on the JUnit test thread to fetch the joined result, **never** on the HTTP event loop.
- Never use `isAllocated` as synchronization in shared mutable/concurrent code. It only checks state at the moment of reading.

To genuinely prove leak-freedom, enable Netty's leak detector in test/staging and run load/cancellation tests; passing two unit tests does not cover all races.

## 22. Standalone JDK 17: Simulating Ref-Counting Ownership

No Spring dependencies are needed for this small conceptual model. File `ReferenceOwnershipDemo.java`:

```java
public class ReferenceOwnershipDemo {

    static final class Lease {
        private int references = 1;

        synchronized void retain() {
            if (references == 0) {
                throw new IllegalStateException("already released");
            }
            references++;
        }

        synchronized void release() {
            if (references == 0) {
                throw new IllegalStateException("double release");
            }
            references--;
        }

        synchronized int count() {
            return references;
        }
    }

    public static void main(String[] args) {
        Lease lease = new Lease();

        lease.retain(); // Owner B retains an additional reference.
        System.out.println("after retain=" + lease.count());

        lease.release(); // Owner A is done.
        System.out.println("after A=" + lease.count());

        lease.release(); // Owner B is done.
        System.out.println("after B=" + lease.count());
    }
}
```

Compile and run:

```bash
javac ReferenceOwnershipDemo.java
java ReferenceOwnershipDemo
```

Exact stdout:

```text
after retain=2
after A=1
after B=0
```

This is **not** a real Netty, `PooledDataBuffer`, or thread-safe memory allocator implementation. It merely expresses an easy-to-remember ownership balance rule; real Spring code must use `DataBufferUtils.retain/release` and respect who transferred or consumed the buffers.

## 23. DataBufferLimitException and Resource Limits

Why limits matter critically:

```text
1 upload request      10 MB
100 in-flight requests
------------------------
~1 GB payload if collected all at once
(excluding objects, codec state, network queues, copied buffers)
```

`DataBufferUtils.join(source, maxByteCount)` enforces a limit on **that specific aggregation**. For default codecs, Spring Boot's `spring.codec.max-in-memory-size` property controls in-memory decoding/aggregation limits depending on codec/framework version. Never assume one single property covers all low-level custom buffer handling, multipart streaming, HTTP server connection quotas, and gateway request sizes.

Practices:

- Enforce request body limits **before allocating the full payload**.
- Use `maxByteCount` on every raw aggregation.
- When parsing JSON, use decoders/validation with proper limits; never collect unboundedly yourself.
- When handling multipart, enforce limits on total size, per file, per field, part count, disk spill, and quarantine.
- Limit concurrent uploads/downloads/connections and total native memory budgets.
- Choose reasonable chunk sizes; never allocate a 1 GB buffer and call it streaming.
- Streaming many chunks does not mean the app isn't buffering; `collectList`/`join`/`cache` can turn it into a large aggregation.
- When storing very large files, stream directly to storage rather than holding the entire file on the heap.
- Isolate long streams from other request/worker capacity when needed.

**413 Payload Too Large** is the usual HTTP contract for bodies exceeding quota; if an error occurs after the response commits, you cannot always send a fresh 413.

## 24. Cancellation, Errors, and Races in Streams

Reactive Streams has three common termination signals:

```text
onComplete()   -> source finished successfully
onError(e)     -> source finished with an error
cancel()       -> subscriber no longer wants more items
```

Responsibilities:

| Scenario | What Must Be Released |
| --- | --- |
| Error while reading a DataBuffer | Local buffer whose ownership was received |
| Cancel while join is accumulating | Join releases accumulated buffers per contract |
| Cancel while an operator has an internal queue | Discard hook and operator semantics |
| HTTP client disconnects after several chunks | Pending buffers owned by writer/pipeline; producer cleanup |
| File write fails after opening channel | Channel/file resources and untransferred buffers |
| Encoder serialization fails before publishing | Newly allocated, untransferred buffer |
| Retry creates a new subscription | Never reuse pooled buffers already released on the previous attempt |

Never release a buffer in both `doOnError` and `doFinally` if both branches target the same reference. `doFinally` may execute after downstream termination; if used for cleanup, avoid races/double-frees and ensure nobody is still reading the buffer.

If a client disconnects, the application must not assume it can push `onNext` endlessly into a queue. Use bounded queues/backpressure, cancel file reads/remote subscriptions upon cancellation, and never store pooled buffers in static caches.

## 25. Leak Detection with Netty and Troubleshooting

Possible symptoms:

- Native/direct memory grows continuously even with steady active request counts.
- `OutOfDirectMemoryError` or errors related to Netty's pooled allocator.
- Netty's leak detector logs warnings like `LEAK: ByteBuf.release() was not called...`.
- HTTP streaming returns corrupted bytes or `IllegalReferenceCountException` when a buffer is released too early.
- Heap dumps do not account for native memory consumption.
- Increasing `-Xmx` does not fix native/direct buffer leaks and can even squeeze container memory limits tighter.

In a **controlled test/staging environment**, Netty provides `-Dio.netty.leakDetection.level=advanced` or `paranoid` to gather evidence, though high levels carry heavy overhead; never enable `paranoid` on busy production without impact analysis. Exact syntax/env vars depend on how the JVM/server is launched.

Investigation checklist:

1. Confirm whether the backend uses pooled buffers (Reactor Netty, Jetty, or custom implementation).
2. Locate every place directly consuming `Flux<DataBuffer>`.
3. Diagram ownership for each buffer: who allocates, who consumes, who releases, who transfers.
4. Inspect `filter`/`skip`/`take`/`timeout`/`onErrorResume`/`retry` branches.
5. Search for `collectList`/`cache`/shared state retaining buffers.
6. Inspect encoder failures prior to handoff.
7. Check whether raw `DataBufferUtils.write` overloads auto-release and whether channels close.
8. Check whether `WebClient` raw response bodies are consumed/relayed/released.
9. Write tests for cancellation/disconnect, malformed bodies, quota breaches, and streaming failures.
10. Monitor native memory, Netty allocator metrics, request concurrency, and P99 latency.
11. Compare performance before/after changes; never sprinkle `release` blindly to silence the leak detector.
12. When using `touch` hints, never record secrets in hints.

**Never use `System.gc()` or larger heaps as a fix for reference-counted leaks.** Fix the ownership path.

## 26. Real-World Scenarios and Choosing the Right Pattern

### 26.1. Standard JSON REST CRUD

The controller accepts `@RequestBody Mono<Dto>` and returns `Mono<ResponseEntity<Dto>>`. **No need** to manage `DataBuffer` directly. Spring codecs/HTTP writers handle responsibility.

### 26.2. Computing Hash/Checksum of a Small Binary Request

Use bounded `DataBufferUtils.join`, copy bounded bytes, release the joined result in `finally`, and return a DTO. This is the sample app's pattern.

### 26.3. Streaming a Large File to a Client

Prefer `Resource` or `DataBufferUtils.read`/`ServerResponse.body` as appropriate; never join the entire file. When passing `Flux<DataBuffer>` straight to the response writer, the final downstream owner releases; your code must not both forward and release.

### 26.4. Proxying/Relaying an Upstream WebClient Body

Read raw `Flux<DataBuffer>` only if truly necessary; forward ownership to the response writer and handle headers/status/backpressure/cancellation properly. Never cache raw buffers, dual-subscribe, or leak when the target/client closes.

### 26.5. Filtering Out Certain Chunks

If a filter drops a chunk, use a discard hook. If a kept chunk passes downstream, **never release the kept chunk before downstream uses it**.

### 26.6. Converting to DTO/String

If your code is the final consumer of a raw DataBuffer, release in `try/finally` after building the DTO. If using standard codecs, do not insert extra releases.

### 26.7. Joining Multiple Chunks and Splitting Again

`join` can create a composite holding references. Splitting into retained views requires understanding `retainedSlice`/Netty reference semantics: who holds the view, who releases the composite, and whether underlying memory is shared. Avoid this design unless necessary; copy into bounded immutable bytes for longer-lived data.

### 26.8. Request Body Logging/Filtering

This is a very common leak source. A `WebFilter` that reads the raw body to log without properly recreating/decorating the body prevents the downstream controller from reading it or causes double-reads. If payload inspection is mandatory, enforce size caps, redact secrets, ensure replay/decorator semantics, and test ownership/cancellation; never blindly copy debug body-logging snippets into production.

## 27. Common Mistakes

1. **Treating DataBuffer like a GC-managed byte[]:** pooled references need releasing.
2. **Ignoring heap vs. direct memory:** native leaks may not show in heap metrics.
3. **Reading a buffer without releasing:** local final consumers create leaks.
4. **Releasing before passing to `writeWith`:** use-after-release.
5. **Releasing in the controller while also letting the writer release:** double-release.
6. **Retaining without a matching release:** reference leak.
7. **Releasing every buffer in doFinally regardless of downstream handoff:** wrong ownership/race.
8. **Believing doOnDiscard releases every onNext:** it only handles discarded buffers where operators support it.
9. **Using filter/drop on a pooled source without doOnDiscard:** leaks dropped pieces.
10. **Using `join` and releasing both components and the joined result:** double-release.
11. **Using `join` without releasing the joined result:** aggregate leak.
12. **Joining bodies without maxByteCount:** memory exhaustion risk.
13. **Thinking `maxByteCount` on one join is a system-wide quota:** concurrency/server/gateway limits are still needed.
14. **Thinking `DataBufferUtils.write(OutputStream)` auto-closes the stream/releases buffers:** wrong overload contract.
15. **Using blocking OutputStream on the Netty event loop:** thread starvation.
16. **Caching pooled `Flux<DataBuffer>`:** resubscribers may see already-released memory.
17. **Subscribing to raw WebClient bodies and forgetting to consume/release:** leaks response resources.
18. **Reading the request body twice in filter/controller:** bodies are generally not repeatable.
19. **Mutating `byte[]` after wrapping/handoff:** data corruption.
20. **Assuming every DataBuffer is pooled:** implementation decides; use portable helpers.
21. **Assuming all pooled buffers share identical refCount numbers:** slices/composites have nuances.
22. **Checking `isAllocated` then reading on another thread unsynchronized:** TOCTOU/race.
23. **Forgetting the error path when a custom encoder allocates:** leak on serialization failure.
24. **Forgetting the cancel path in long-lived streaming:** leaks buffers/listeners.
25. **Using unbounded `collectList` for large files:** pulls byte buffers into RAM.
26. **Relying on one happy-path HTTP test to claim leak-freedom:** pooled/cancel/error stress tests are needed.
27. **Enabling Netty leakDetection paranoid on busy production:** heavy overhead.
28. **Increasing `-Xmx` to "fix" an off-heap leak:** misses the root cause.
29. **Sharing a buffer between two consumers without retain/copy:** broken dual ownership.
30. **Calling release twice because the first returned false:** return value is not license to release arbitrarily.
31. **Calling retainedSlice while forgetting parent/shared memory lifetime:** unsafe refs.
32. **Leaving file uploads/multipart unbounded:** memory/disk exhaustion.
33. **Exposing raw binary endpoints publicly without quotas/auth:** easy DoS vector.
34. **Treating CRC32 as a security signature:** not tamper-proof.
35. **Treating one DataBuffer = one TCP packet:** transport may split or coalesce per flow control.
36. **Failing to distinguish pre-commit vs. post-commit errors:** status cannot always be changed.
37. **Bypassing Spring codecs to manually parse JSON from raw ByteBuf unnecessarily:** complex and leak-prone.

## 28. Code Review and Production Checklist

### Ownership

- [ ] Is there an allocate → read/write → transfer/release diagram for every raw DataBuffer?
- [ ] Does the final consumer of a buffer release it on success/error/cancel?
- [ ] When transferring buffers to the HTTP writer, does the code avoid releasing early?
- [ ] Does every `retain` have an exact matching ownership release?
- [ ] Does `join` release only the joined result without double-releasing components?
- [ ] Do custom decoders/encoders clean up on exceptions before handoff?
- [ ] Is `doOnDiscard` placed on the right operators/paths where buffers may drop?
- [ ] Are raw pooled buffers never cached or shared beyond a request's lifetime?
- [ ] Are underlying `byte[]` arrays never mutated after transferring ownership?

### Resource Limits

- [ ] Does every aggregation have an appropriate `maxByteCount`/codec memory limit?
- [ ] Are concurrent requests, uploads, and stream connections capped?
- [ ] Are file sizes, part counts, and storage quotas enforced for multipart?
- [ ] Is blocking file/`OutputStream` work kept off the Netty event loop?
- [ ] Is the raw body never consumed twice across WebFilters and controllers?
- [ ] Are disconnects/cancellations handled with subscription resource cleanup?
- [ ] Are response status and headers set before commit?

### Testing and Operations

- [ ] Are there unit tests for pooled retain/release and joined composites?
- [ ] Do HTTP tests verify exact bytes, empty bodies, and limit-exceeded/413 responses?
- [ ] Are error paths tested: malformed bodies, decoder errors, stream writer failures?
- [ ] Are cancel/disconnect paths tested: no leftover pooled buffers or queued references?
- [ ] Are native memory, allocator metrics, and leak detector monitored in staging?
- [ ] Are raw bodies/tokens/file data excluded from uncontrolled debug logging?
- [ ] Are high-overhead leak-debug levels turned off in normal operations unless planned?

## 29. Self-Check Questions

**1.** Is `DataBuffer` always on the Java heap?

**Answer:** No. It can wrap direct/native pooled buffers, especially with Netty.

**2.** Why must `DataBufferUtils.release(buffer)` be called in a custom decoder?

**Answer:** The decoder is the final consumer of the raw buffer once it produces a DTO/String and stops forwarding it; pooled memory must be returned.

**3.** When should you not release in a controller?

**Answer:** When buffer ownership has been transferred to `response.writeWith`/HTTP writer or another designated final consumer.

**4.** What does retain do?

**Answer:** Adds a reference if the buffer is pooled, allowing a new owner to keep the buffer alive until its own release.

**5.** Is calling retain once and release only once okay?

**Answer:** If there was already an initial ownership and nobody releases the remaining reference, refCount > 0 and it leaks.

**6.** Which buffers does `doOnDiscard` release?

**Answer:** DataBuffer elements discarded by discard-supporting operators at the pipeline boundary; it does not auto-release buffers forwarded downstream.

**7.** Does `DataBufferUtils.join` always copy data?

**Answer:** No. It can create a zero-copy composite; component ownership lives inside the aggregate per contract.

**8.** After join completes, what do you release?

**Answer:** Release the joined result once consumed; do not re-release individual components fed into join.

**9.** Why is `join(source, maxByteCount)` needed?

**Answer:** Bounds total aggregated bytes, preventing unbounded body collection; exceeding the limit emits `DataBufferLimitException`.

**10.** Does `DataBufferUtils.write(source, OutputStream)` automatically release input DataBuffers?

**Answer:** No. The returned Flux emits buffers after writing; the caller must release per contract and manage closing the OutputStream.

**11.** Does `response.writeWith(flux)` need `doOnNext(DataBufferUtils::release)`?

**Answer:** It should not have it. The writer is the final consumer; releasing before the writer can reclaim memory too early.

**12.** What can cause native memory to climb steadily while heap usage stays low?

**Answer:** Pooled/direct buffer leaks, shared allocator pressure, outstanding connections, or other native resources; use metrics/leak detection and ownership analysis.

**13.** Why can't `doFinally` replace releasing each buffer?

**Answer:** `doFinally` observes a single subscription completion/cancellation rather than firing per buffer; buffers may already have transferred ownership downstream.

**14.** Does CRC32 prove data came from a trusted sender?

**Answer:** No. It is only a non-tamper-resistant checksum; for authentication/integrity, use HMAC/signatures.

**15.** Is a passing HTTP CRC32 test enough to conclude there are no leaks?

**Answer:** No. You need pooled reference-count tests, error/cancellation tests, and stress/leak-detector runs.

## 30. References

- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework 6.2.4 — `DataBufferUtils` Javadoc, `join`/`release`/`write`: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
- Spring Framework 6.2.4 — `PooledDataBuffer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html
- Spring Framework 6.2.4 — `DataBufferFactory` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/DataBufferFactory.html
- Spring Framework 6.2.4 — `DataBuffer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/DataBuffer.html
- Spring Framework 6.2.4 — `DataBufferLimitException`: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/DataBufferLimitException.html
- Spring Framework — WebFlux annotated controllers and request body: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework — WebClient response exchange/cleanup: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework — WebFlux WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Project Reactor — Handling discarded elements: https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html
- Project Reactor — Error handling and cancellation: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Netty — ByteBuf reference counting: https://netty.io/wiki/reference-counted-objects.html
- Netty — Resource leak detector: https://netty.io/wiki/reference-counted-objects.html#troubleshooting-buffer-leaks
