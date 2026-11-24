# DataBuffer, PooledDataBuffer, and Off-Heap Memory in Spring WebFlux

## 1. Role of DataBuffer in WebFlux

HTTP transmits data as bytes. Before JSON becomes a Java object or a Java object is encoded into JSON, data must pass through a byte representation layer. In Spring WebFlux, that abstraction is `DataBuffer`.

`DataBuffer` lets Spring work across different I/O platforms without coupling the entire application directly to `java.nio.ByteBuffer` or Netty `ByteBuf`. Depending on the running server/client, the implementation may be a heap buffer, a direct buffer, or a pooled buffer.

Core components:

- **`DataBuffer`**: represents a byte region with read and write positions.
- **`DataBufferFactory`**: allocates new buffers or wraps existing byte data.
- **`PooledDataBuffer`**: extends DataBuffer with reference counting to manage pooled buffers.
- **`DataBufferUtils`**: utility operations such as join, retain, release, read, write, skip, and take.
- **`Decoder` / `Encoder`**: converts between DataBuffer streams and higher-level objects.
- **`HttpMessageReader` / `HttpMessageWriter`**: connects codecs with HTTP request/response semantics.

Request reading diagram:

~~~text
HTTP socket
    |
    v
Server runtime (e.g., Reactor Netty)
    |
    v
ByteBuf / byte buffer
    |
    v
DataBuffer
    |
    v
HttpMessageReader + Decoder
    |
    v
Mono<DTO> / Flux<DTO>
    |
    v
Controller / HandlerFunction
~~~

Response writing diagram:

~~~text
Controller / HandlerFunction
    |
    v
Mono<DTO> / Flux<DTO>
    |
    v
HttpMessageWriter + Encoder
    |
    v
DataBuffer
    |
    v
Server runtime
    |
    v
HTTP socket
~~~

In most regular controllers, you only work with DTOs, String, Resource, Mono, or Flux; Spring and codecs manage buffers underneath. You need to understand ownership and release when reading/writing DataBuffer directly, writing custom codecs, manipulating raw request/response bodies, or holding buffers across asynchronous callbacks.

## 2. Heap Memory, Direct Memory, and Off-Heap

### 2.1. Heap Buffers

Heap buffers use memory belonging to the Java heap. The JVM manages object lifecycles via the garbage collector. When an object is no longer referenced and is eligible for collection, GC can reclaim the memory.

Advantages:

- Easy to inspect with heap dumps and object profiling tools.
- Lifecycle tied to Java objects and GC.
- Suitable for much general-purpose data processing.

Limitation in network I/O: when native I/O requires a native memory address, heap data may have to be copied to an intermediate region or direct buffer depending on the implementation.

### 2.2. Direct Buffers and Off-Heap Memory

`ByteBuffer.allocateDirect` creates a direct buffer whose data region resides outside the Java heap. Direct buffers are useful for native I/O because the runtime can work with native memory while reducing certain copy steps.

Advantages:

- Can reduce copying between Java heap and native I/O.
- Suits high-throughput socket, file channel, and networking operations.

Costs:

- Allocating/freeing direct memory is typically more expensive than normal heap object allocation.
- This memory is not inside the heap region directly capped by `-Xmx`.
- Reclamation follows different mechanisms and timing than heap objects; do not rely on GC to manage per-request pooled buffers.
- If buffers are held too long or not returned to the pool, direct memory can grow and cause native out-of-memory errors.

**Off-heap does not mean infinite memory or zero management.** The process is still constrained by RAM, container limits, direct memory limits, and OS native resources.

### 2.3. Why Does Networking Typically Use Pooling?

Continuously allocating and freeing native buffers can be expensive. A pool allows reusing already-allocated regions instead of creating new regions for every read/write.

Reactor Netty uses direct memory and pooled buffers by default for networking. When a buffer is returned to the pool, the memory region may still be retained by the allocator for reuse. Therefore:

- Direct memory held by the allocator does not necessarily indicate a leak.
- Looking only at RSS or heap metrics is insufficient to conclude there is a leak.
- Track active allocated memory, trends over time, and the leak detector.
- Pooled buffers must have clear ownership so the allocator knows when reuse is allowed.

### 2.4. Pooled Does Not Mean Direct

These two concepts answer two distinct questions:

| Concept | Question |
| --- | --- |
| Heap / direct | Where does the data region reside? |
| Pooled / unpooled | By what mechanism is memory reused? |
| Reference counted | When can memory be returned or freed? |

A buffer may use pooling and reference counting; do not assume every DataBuffer is a PooledDataBuffer or that every direct buffer must be released manually by the application.

## 3. DataBuffer: Byte Representation API

### 3.1. Key Capabilities

DataBuffer provides operations similar to ByteBuffer, along with several conveniences:

- Reading and writing bytes.
- Independent read position and write position.
- No need to call `flip()` to switch from writing to reading as with ByteBuffer.
- Capacity can grow when needed, depending on the implementation.
- Querying remaining readable bytes via `readableByteCount()`.
- Accessing data as a ByteBuffer, InputStream, or OutputStream.
- Searching for bytes within the data region.

Example reading content:

~~~java
int size = buffer.readableByteCount();
byte[] bytes = new byte[size];
buffer.read(bytes);
~~~

`readableByteCount()` is the number of bytes from the current read position to the write position. It is not necessarily equal to capacity or total bytes ever written to the buffer.

### 3.2. Independent Read and Write Positions

A DataBuffer has a read position and a write position. Writing advances the write position; reading advances the read position. Because the two positions are independent, there is no need to flip the buffer like the familiar ByteBuffer workflow.

~~~java
DataBuffer buffer = factory.allocateBuffer(16);

buffer.write("hello".getBytes(StandardCharsets.UTF_8));

int readable = buffer.readableByteCount();
byte[] result = new byte[readable];
buffer.read(result);
~~~

In WebFlux applications, typically obtain the factory from the request/response rather than picking an implementation manually:

~~~java
DataBufferFactory factory = exchange.getResponse().bufferFactory();
DataBuffer output = factory.allocateBuffer(128);
~~~

The factory may be `NettyDataBufferFactory` when running Reactor Netty or `DefaultDataBufferFactory` in other environments.

### 3.3. Allocate and Wrap

`DataBufferFactory` is commonly used in two ways:

~~~java
DataBuffer allocated = factory.allocateBuffer(1024);

byte[] source = "hello".getBytes(StandardCharsets.UTF_8);
DataBuffer wrapped = factory.wrap(source);
~~~

- `allocateBuffer` creates a new buffer with an optional initial capacity.
- `wrap` creates a DataBuffer wrapping an existing byte[] or ByteBuffer; it does not necessarily copy all bytes into a new array.

Do not mutate the source array after wrapping if another component is still reading the same region. With pooled buffers, you must still follow the implementation's ownership and release rules.

### 3.4. Reading Bytes into a String

Simple example:

~~~java
int size = buffer.readableByteCount();
byte[] bytes = new byte[size];
buffer.read(bytes);

String text = new String(bytes, StandardCharsets.UTF_8);
~~~

This snippet consumes the readable byte region because the read position advances. If you need to read again, actively manage positions or copy the data appropriately. Do not assume DataBuffer is an immutable byte array.

With text data, respect UTF-8 character boundaries. A single character can span multiple buffers; do not decode each chunk independently and concatenate Strings if a chunk can end mid-way through a multi-byte sequence. Use a stateful codec or decoder.

## 4. PooledDataBuffer and Reference Counting

### 4.1. How Does Reference Counting Work?

PooledDataBuffer extends DataBuffer with reference counting. When a pooled buffer is allocated, the initial reference count is 1.

- `retain()` increments the reference count by 1.
- `release()` decrements the reference count by 1.
- When the reference count reaches 0, the buffer is freed or returned to the pool for reuse.
- While the reference count remains above 0, the buffer cannot be reused yet because an owner still holds it.

Conceptual diagram:

~~~text
allocate buffer
refCount = 1
     |
     +-- retain()  -> refCount = 2
     |
     +-- release() -> refCount = 1
     |
     +-- release() -> refCount = 0
                         |
                         v
                 memory can be recycled
~~~

The reference count is not the number of Java variables pointing to the object. It is the number of ownership references tracked by the pooled buffer mechanism.

### 4.2. Why Is Reference Counting Needed?

Suppose Netty receives data from a socket into a direct buffer. If the framework returned the buffer to the pool the moment a controller received a Java reference, the memory region could be reused for another request while current code is still reading it. That could cause corrupted data, access errors, or crashes.

Reference counting prevents premature reuse: the buffer is only returned to the pool once all ownership references have been released.

### 4.3. Use DataBufferUtils Instead of Casting

Do not cast every DataBuffer to PooledDataBuffer:

~~~java
PooledDataBuffer pooled = (PooledDataBuffer) buffer;
pooled.release();
~~~

Some implementations are not pooled, so casting can fail. Use Spring's utilities:

~~~java
DataBufferUtils.retain(buffer);
DataBufferUtils.release(buffer);
~~~

These methods inspect the implementation and perform retain/release when the buffer supports the corresponding mechanism. `DataBufferUtils.release` also supports closeable buffers such as `CloseableDataBuffer`.

### 4.4. Every Ownership Must Have an End

A useful principle:

- When code receives ownership of a buffer and finishes consuming it, that code must release its ownership.
- When code forwards a buffer to a downstream component responsible for consuming it, ownership is transferred; do not release early before downstream reads it.
- When needing to keep a buffer beyond the point where the current owner may release it, retain to create an additional ownership reference; release that extra reference when done.
- Every retain must have a matching release.
- Never release the same ownership multiple times.

Never release a buffer merely because a callback returns if the buffer is still used downstream. Conversely, never hold buffers in collections/caches without a release policy on complete, error, or cancel.

## 5. Ownership in Reactive Pipelines

### 5.1. Transferring Ownership Downstream

When a buffer is emitted through a Publisher, the receiving component must know what it is doing with it:

1. Read and consume immediately, then release.
2. Forward the buffer unchanged to the next writer/consumer; that consumer is responsible for releasing per contract.
3. Keep the buffer for asynchronous processing after the callback; retain if the prior owner may release, then release when finished.
4. Drop the buffer due to filter/skip/cancel; provide appropriate discard cleanup.

For example, if merely forwarding a raw request body to the response body:

~~~java
return exchange.getResponse()
    .writeWith(exchange.getRequest().getBody());
~~~

In this forwarding pattern, your code neither reads bytes nor keeps its own buffer; the response writer consumes the buffers passed to it. Do not call release before the writer finishes writing.

### 5.2. Reading and Releasing a Buffer

If the application directly consumes a request DataBuffer to extract bytes or compute a checksum, it must release the buffer after reading finishes:

~~~java
byte[] copy;

try {
    copy = new byte[buffer.readableByteCount()];
    buffer.read(copy);
}
finally {
    DataBufferUtils.release(buffer);
}
~~~

If reading throws an exception, the finally block still releases. If the buffer is forwarded downstream, do not apply this release block before downstream completes.

### 5.3. Holding a Buffer Across an Asynchronous Callback

Sometimes a buffer must outlive the callback receiving it. For example, a component needs to retain data to process after the callback returns. When the source might release the buffer after the callback, retain before holding and release the additional reference after processing finishes.

~~~java
DataBufferUtils.retain(buffer);

return processLater(buffer)
    .doFinally(signal -> DataBufferUtils.release(buffer));
~~~

This is an illustrative ownership skeleton. Use it only when you understand the source's contract and know which references you own. If the source does not release the initial ownership itself, the application must also release the initial reference per contract. Never add retain mechanically, because retain creates an additional release obligation.

### 5.4. Never Use a Buffer After Release

Once the reference count reaches 0, the memory region may already be returned to the pool and reused. Never continue:

- Reading bytes.
- Writing bytes.
- Creating new views from the buffer.
- Sending the buffer to another Publisher.
- Holding a ByteBuffer view and using it after the parent buffer was released.

These bugs can manifest intermittently because memory reuse depends on timing and load.

## 6. DataBufferUtils: Essential Utilities

### 6.1. release and releaseConsumer

~~~java
DataBufferUtils.release(buffer);
~~~

Decrements the reference count if the buffer is pooled and currently allocated; for unpooled implementations, no reference count operation is needed.

Using as a Consumer:

~~~java
fluxOfBuffers.doOnNext(DataBufferUtils.releaseConsumer());
~~~

`releaseConsumer()` is useful when an API re-emits DataBuffers after writing/consuming them, and the application is responsible for releasing those buffers.

### 6.2. retain

~~~java
DataBufferUtils.retain(buffer);
~~~

Increments the reference count if the buffer is pooled. Use when creating an additional ownership reference so the buffer survives after the current owner may release it.

Do not retain just to read a buffer within the same synchronous callback; keeping a buffer beyond the current lifecycle is the reason to consider retain.

### 6.3. join: Merging Multiple Buffers into One

`DataBufferUtils.join` accepts a Publisher of multiple DataBuffers and produces a combined DataBuffer. Depending on the implementation, the result may be a new buffer or a composite buffer referencing the input buffers, potentially avoiding copies if supported by the underlying API.

~~~java
Mono<DataBuffer> joined = DataBufferUtils.join(body);
~~~

There is a byte-limit overload:

~~~java
Mono<DataBuffer> joined =
    DataBufferUtils.join(body, 1024 * 1024);
~~~

The limit prevents unbounded request body aggregation. If exceeded, Spring emits `DataBufferLimitException`. If the source errors or is cancelled during join, accumulated buffers are released. Input buffers do not need to be released individually by the application after passing into join; their ownership is managed inside the composite result.

**Join does not always mean zero-copy.** It may use a composite when supported by the implementation; otherwise, it may allocate a buffer holding the combined data.

### 6.4. skipUntilByteCount and takeUntilByteCount

These two utilities operate by total byte count rather than just Publisher element count:

- `skipUntilByteCount(source, count)` skips bytes until the requested byte count is reached.
- `takeUntilByteCount(source, count)` forwards data up to the byte limit.

They are useful for framing or segmenting byte streams. Carefully verify ownership and discard behavior when combining them with other operators.

### 6.5. read and write

`DataBufferUtils.read` can turn a Resource or NIO Channel into a `Flux<DataBuffer>`. Some overloads manage closing the channel when the Publisher terminates.

`DataBufferUtils.write` can write a Publisher<DataBuffer> to an OutputStream or NIO Channel. There is an important detail: overloads writing to streams/channels typically re-emit the written DataBuffers and **do not automatically release source buffers**. If the application consumes the resulting Flux, attach `DataBufferUtils.releaseConsumer()` when appropriate. The API also does not close the OutputStream/channel automatically; the application must manage that resource's lifecycle.

Conceptual example:

~~~java
DataBufferUtils.write(source, channel)
    .doOnNext(DataBufferUtils.releaseConsumer())
    .then();
~~~

This snippet illustrates releasing buffers re-emitted after writing. Opening/closing the channel, write positioning, and error handling must be managed separately. For large files, prefer streaming instead of joining the entire file into a single buffer.

## 7. Codecs and DataBuffer Lifecycle

### 7.1. Decoders Read and Must Release

A Decoder is the final component reading input DataBuffers before creating higher-level objects. Once a decoder finishes reading a buffer and no longer needs it, the decoder must release that buffer.

~~~java
DataBufferUtils.release(dataBuffer);
~~~

If a decoder uses operators that may prefetch/cache like `flatMap` or `reduce`, or operators that drop elements like `filter`/`skip`, discarded buffers still must be released. Attach an appropriate discard hook:

~~~java
Flux<DataBuffer> decodedInput = source
    .filter(this::isUseful)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

`doOnDiscard` must be placed at the right downstream position to receive elements dropped by upstream operators. In complex pipelines, inspect the semantics of each operator and all error/cancel paths.

### 7.2. Encoders Allocate Buffers and Consumers Must Release

An Encoder allocates DataBuffers containing output bytes. The component consuming the buffer — such as a writer writing to the HTTP response or client request — is responsible for releasing it after reading completes.

If an encoder encounters an error during serialization before the buffer is handed off, the encoder must release the allocated buffer itself:

~~~java
DataBuffer buffer = factory.allocateBuffer();
boolean transferred = false;

try {
    buffer.write(bytes);
    transferred = true;
    return buffer;
}
finally {
    if (!transferred) {
        DataBufferUtils.release(buffer);
    }
}
~~~

Once the buffer is emitted to the consumer, ownership transfers to the consumer per pipeline contract. The encoder must never release it again after a successful handoff.

### 7.3. Do Regular WebFlux Applications Need to Release Everything?

No. When using high-level APIs like `@RequestBody DTO`, `bodyToMono`, `bodyToFlux`, `ServerResponse.body`, or default codecs, Spring manages most of the buffer lifecycle.

Manual management is needed when:

- Receiving raw `Flux<DataBuffer>`.
- Returning raw DataBuffers from a custom encoder.
- Writing a custom Decoder/Encoder or `HttpMessageReader`/`HttpMessageWriter`.
- Saving buffers across asynchronous callbacks.
- Directly handling pooled buffers from Netty/WebSocket.
- Using operators with discard/cancel while holding buffers in queues or caches.

## 8. Streaming or Aggregating?

### 8.1. Aggregating the Entire Body

When using `DataBufferUtils.join`, the entire body is held as one combined DataBuffer before processing. This is simple when parsing a small document or calling a legacy API requiring a byte array.

Drawbacks:

- Memory grows with body size.
- A single large request can consume substantial direct/heap memory.
- Many concurrent requests can cause total memory to spike rapidly.
- Byte limits and limit-exceeded handling are required.

Never use unbounded join for large file uploads or infinite streams.

### 8.2. Processing Chunk by Chunk

Streaming allows processing each DataBuffer as it arrives, avoiding holding the entire body in one large buffer.

Example counting total bytes:

~~~java
Flux<DataBuffer> body = request.getBody();

return body
    .map(buffer -> {
        try {
            return buffer.readableByteCount();
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    })
    .reduce(0L, Long::sum);
~~~

Each buffer has its byte count read and is released immediately. The pipeline holds only the running count, not the whole body. If adding operators that may discard buffers before map, add discard cleanup in the proper place.

### 8.3. Limits and Backpressure

Backpressure regulates emission/consumption rates between Publishers. It does not automatically release buffers already held by the application, nor does it prevent an operator from aggregating the whole body.

Combine:

- Streaming when data is large or unbounded.
- `maxByteCount` when aggregation is necessary.
- Request size limits at the gateway/server.
- Concurrency limits when processing multiple files/uploads concurrently.
- Immediate release after consumption.
- Cleanup on error/cancel.

## 9. Example: Safe DataBuffer Transformation

Suppose you need to copy each buffer into a new buffer using the same factory. The example below illustrates ownership:

~~~java
Flux<DataBuffer> copyBuffers(
    Flux<DataBuffer> source,
    DataBufferFactory factory
) {
    return source
        .map(input -> {
            byte[] bytes;

            try {
                bytes = new byte[input.readableByteCount()];
                input.read(bytes);
            }
            finally {
                DataBufferUtils.release(input);
            }

            DataBuffer output = factory.allocateBuffer(bytes.length);
            boolean handedOff = false;

            try {
                output.write(bytes);
                handedOff = true;
                return output;
            }
            finally {
                if (!handedOff) {
                    DataBufferUtils.release(output);
                }
            }
        })
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
}
~~~

Analysis:

1. The pipeline receives ownership of input and reads all remaining bytes.
2. `finally` releases input even if copying throws an error.
3. A new output buffer is allocated and bytes are written into it.
4. When map returns output successfully, ownership of output transfers downstream.
5. If writing output fails before handoff, the finally block releases output.
6. If a downstream operator queues output and discards it on cancel/error, the discard hook releases output.

This is a copy example to clarify ownership, not a zero-copy optimization. If you only need to forward unmodified data, pass the buffer straight to the writer and let the writer consume it per contract instead of copying unnecessarily.

## 10. Common Bugs Causing Memory Leaks or Data Corruption

**Bug 1 — Reading a DataBuffer and forgetting to release.** Pooled buffers are not returned to the pool. Release after consumption if your code owns the buffer.

**Bug 2 — Releasing before downstream reads.** The writer receives an already-deallocated buffer. Only release after the consumer finishes or transfer ownership properly.

**Bug 3 — Calling retain without a matching release.** The reference count never reaches 0 and memory stays pinned. Every retain must have a release point.

**Bug 4 — Releasing the same ownership multiple times.** Can cause reference count errors or premature deallocation. Only the respective owner releases its own reference.

**Bug 5 — Casting every DataBuffer to PooledDataBuffer.** Implementations may be unpooled. Use DataBufferUtils.retain/release.

**Bug 6 — Using a buffer after release.** Memory may already be reused; read results are no longer reliable.

**Bug 7 — Filter/skip dropping buffers without discard cleanup.** Buffers dropped from the pipeline may never be released. Place `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` at the right spot.

**Bug 8 — Caching or holding a buffer across callbacks without retain.** The previous owner may release before the later callback finishes reading. Retain when extending lifetime and release after use.

**Bug 9 — Unbounded body join.** A single large payload can spike memory sharply. Use the overload with maxByteCount or streaming.

**Bug 10 — Assuming direct memory is inside Xmx.** Direct memory is off-heap; monitor allocator metrics and set appropriate native limits.

**Bug 11 — Assuming high RSS always means a leak.** Pools may retain memory for reuse. Track active memory over time and verify with the leak detector.

**Bug 12 — Using DataBufferUtils.write and assuming it auto-releases.** Overloads return a Flux of written buffers and do not auto-release source buffers. Attach releaseConsumer when consuming the resulting Flux.

**Bug 13 — Closing a channel too early.** Writes are unfinished while the channel is already closed. Manage resources along the reactive lifecycle, including complete/error/cancel.

**Bug 14 — Decoding UTF-8 independently per chunk.** A character can split across two DataBuffers. Use a stateful decoder or high-level codec.

**Bug 15 — Creating byte[] manually for large files.** Can aggregate the entire file onto the heap. Use streaming Resource/channel when data is large.

**Bug 16 — Holding buffers in a static collection or singleton field.** Lifetime outlives the request without clear cleanup. Copy the bytes if long-term storage is needed, or manage ownership/expiry/release explicitly.

**Bug 17 — Assuming GC will free pooled Netty buffers on time.** Reference-counted buffers require contractual release; GC does not replace release.

**Bug 18 — Looking only at heap dumps to find direct-memory leaks.** Heap dumps may not reveal all direct memory held by the allocator. Combine allocator metrics, Netty leak detection, and process metrics.

## 11. Diagnosing Direct-Memory Leaks with Reactor Netty

### 11.1. Enabling Netty Leak Detection

Netty provides a leak detector with multiple inspection levels. It can be enabled via a JVM system property, for example:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar app.jar
~~~

Higher inspection levels increase detection capability but also raise CPU cost and overhead. Use an appropriate level in reproduction or staging environments; do not arbitrarily enable heavy modes on high-load production systems.

### 11.2. Reactor Netty Logger

Reactor Netty provides the logger:

~~~text
_reactor.netty.channel.LeakDetection
~~~

This logger is off by default. You can set DEBUG level on the corresponding logger to investigate buffer leaks and see where ownership was transferred to application/framework code.

### 11.3. Tracking Active Heap/Direct Memory

Useful allocator metrics:

| Metric | Meaning |
| --- | --- |
| `reactor.netty.bytebuf.allocator.active.heap.memory` | Bytes currently in use from the heap buffer pool |
| `reactor.netty.bytebuf.allocator.active.direct.memory` | Bytes currently in use from the direct buffer pool |

If active values climb continuously over time and do not drop after workload stops, investigate ownership/release. However, a steady baseline may simply be the pool retaining buffers for reuse, which does not automatically prove a leak.

### 11.4. Distinguishing Heap Pressure from Direct-Memory Pressure

- Growing heap: inspect object retention, collections, caches, and heap dumps.
- Growing direct memory: inspect pooled buffer ownership, Netty allocator metrics, leak detector, and `MaxDirectMemorySize`.
- Growing RSS: inspect heap, direct memory, metaspace, thread stacks, native libraries, and memory mappings; RSS does not equal heap.
- Container OOM: inspect container memory limits and total native + heap, not just Xmx.

### 11.5. Narrowing Down the Root Cause

A practical workflow:

1. Record the workload, endpoint, and timestamp when direct memory starts growing.
2. Compare active heap/direct allocator metrics before, during, and after load.
3. Enable leak detection in a reproducible environment.
4. Search for code directly using DataBuffer, custom codecs, raw bodies, WebSockets, or channels.
5. Audit every complete, error, cancel, and discard branch.
6. Verify every retain has a matching release and buffers are not released before consumers finish.
7. Create a repeatable load test and verify active memory returns to a stable baseline.

## 12. Spring Boot 3.5.7 + Java 17 Example: Bounded Raw Body Reading

This example creates an endpoint receiving a binary body and returning the byte count along with a hex preview. It uses `DataBufferUtils.join` with a 1 MiB limit, reads the combined DataBuffer, and releases it in `finally`.

The project only needs WebFlux; no direct Netty dependency is required because Spring Boot WebFlux manages the server runtime.

### 12.1. Project Structure

~~~text
webflux-databuffer-demo/
├── pom.xml
├── src/main/java/example/buffer/
│   ├── DataBufferApplication.java
│   └── PayloadController.java
└── src/test/java/example/buffer/
    └── PayloadControllerTest.java
~~~

### 12.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-databuffer-demo</artifactId>
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

### 12.3. `DataBufferApplication.java`

~~~java
package example.buffer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DataBufferApplication {

    public static void main(String[] args) {
        SpringApplication.run(DataBufferApplication.class, args);
    }
}
~~~

### 12.4. `PayloadController.java`

~~~java
package example.buffer;

import java.util.HexFormat;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class PayloadController {

    private static final int MAX_BODY_BYTES = 1024 * 1024;
    private static final int PREVIEW_BYTES = 16;

    public record PayloadSummary(
        int bytes,
        String firstBytesHex,
        boolean previewTruncated
    ) {}

    @PostMapping(
        path = "/api/inspect",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<PayloadSummary> inspect(ServerHttpRequest request) {
        return DataBufferUtils.join(
                request.getBody(),
                MAX_BODY_BYTES
            )
            .map(this::summarizeAndRelease)
            .defaultIfEmpty(new PayloadSummary(0, "", false))
            .onErrorMap(
                DataBufferLimitException.class,
                error -> new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "Request body exceeds the configured limit",
                    error
                )
            );
    }

    private PayloadSummary summarizeAndRelease(DataBuffer buffer) {
        try {
            int totalBytes = buffer.readableByteCount();
            int previewLength = Math.min(totalBytes, PREVIEW_BYTES);

            byte[] preview = new byte[previewLength];
            buffer.read(preview);

            return new PayloadSummary(
                totalBytes,
                HexFormat.of().formatHex(preview),
                totalBytes > previewLength
            );
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    }
}
~~~

Key points in `summarizeAndRelease`:

- The controller receives the raw body as a Publisher<DataBuffer>.
- `join` aggregates the body and caps total bytes at 1 MiB.
- `readableByteCount` retrieves the number of readable bytes.
- Only up to the first 16 bytes are copied for the preview.
- `finally` releases the joined buffer whether reading succeeds or throws an exception.
- If the body exceeds the limit, `DataBufferLimitException` is mapped to HTTP 413.
- An empty body maps to a summary with 0 bytes.

This example intentionally aggregates a small bounded body. For large files or infinite streams, process each DataBuffer and release chunk by chunk instead of joining everything.

### 12.5. `PayloadControllerTest.java`

~~~java
package example.buffer;

import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.http.MediaType.APPLICATION_OCTET_STREAM;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class PayloadControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsAndReleasesSmallBinaryBody() {
        byte[] payload = new byte[] {0x68, 0x65, 0x6c, 0x6c, 0x6f};

        client.post()
            .uri("/api/inspect")
            .contentType(APPLICATION_OCTET_STREAM)
            .accept(APPLICATION_JSON)
            .bodyValue(payload)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.bytes").isEqualTo(5)
            .jsonPath("$.firstBytesHex").isEqualTo("68656c6c6f")
            .jsonPath("$.previewTruncated").isEqualTo(false);
    }

    @Test
    void rejectsBodyLargerThanConfiguredLimit() {
        byte[] payload = new byte[1024 * 1024 + 1];

        client.post()
            .uri("/api/inspect")
            .contentType(APPLICATION_OCTET_STREAM)
            .bodyValue(payload)
            .exchange()
            .expectStatus().isEqualTo(413);
    }
}
~~~

The first test verifies a 5-byte body is read and converted to a hex preview. The second test sends 1 MiB + 1 byte and verifies the endpoint rejects the oversized payload. Run tests:

~~~bash
mvn test
~~~

### 12.6. Running and Calling the API

Start:

~~~bash
mvn spring-boot:run
~~~

Send the string `hello` as bytes:

~~~bash
curl -i -X POST http://localhost:8080/api/inspect \
  -H "Content-Type: application/octet-stream" \
  -H "Accept: application/json" \
  --data-binary "hello"
~~~

Expected response body:

~~~json
{
  "bytes": 5,
  "firstBytesHex": "68656c6c6f",
  "previewTruncated": false
}
~~~

Sending a body over 1 MiB receives HTTP 413. Do not use this aggregating endpoint as a large-file upload endpoint; it is designed to illustrate ownership management on a bounded body.

## 13. Checklist Before Using DataBuffer Directly

Before merging code that manipulates raw DataBuffers, check:

1. Is the code reading, writing, retaining, or forwarding the buffer?
2. Who is the current owner and who will release it?
3. Is retain needed because the buffer outlives the current callback?
4. Does every retain have a corresponding release?
5. Could the buffer be released before the writer/consumer finishes reading?
6. Do any operators filter, skip, prefetch, cache, or discard buffers?
7. Is `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` placed properly for dropped items?
8. On source error or client cancel, are retained buffers released?
9. Is the entire body aggregated? If so, where is the byte limit?
10. Can it be processed chunk by chunk to reduce memory usage?
11. Is `DataBufferUtils.write` re-emitting buffers without being released?
12. Are channels/streams/file resources closed on complete/error/cancel?
13. Is a buffer used after release, or is a view kept after the parent was released?
14. Are there tests for large payloads, empty bodies, mid-stream errors, and cancellation?
15. Are active direct-memory metrics monitored and is the leak detector enabled during investigation?

## 14. Self-Check Exercises

1. What does `DataBuffer` represent? **A byte region with read/write positions and an API independent of the concrete implementation.**
2. What are the two common roles of `DataBufferFactory`? **Allocating new buffers and wrapping existing byte[]/ByteBuffer instances.**
3. Where do direct buffers store data? **Outside the Java heap, typically in native memory.**
4. Why does networking commonly use pooled buffers? **To reduce allocation/deallocation cost of native buffers through reuse.**
5. What reference count does a `PooledDataBuffer` start with? **1.**
6. What does `retain()` do? **Increments the reference count by one.**
7. What does `release()` do? **Decrements the reference count; at 0 the buffer can be freed/returned to the pool.**
8. Should every DataBuffer be cast to PooledDataBuffer? **No; use DataBufferUtils.retain/release.**
9. When should `DataBufferUtils.join` be used? **When a bounded body/stream must be aggregated into a single buffer.**
10. Why does join need maxByteCount? **To avoid unbounded payload aggregation and running out of memory.**
11. When a Decoder finishes reading a DataBuffer, who releases it? **The Decoder is responsible for releasing the input buffer it consumed.**
12. When an Encoder allocates an output buffer, who releases it after writing? **The consumer/writer receiving the buffer is responsible for releasing it.**
13. Why is `doOnDiscard` needed? **To release buffers dropped by operators due to filter/skip/error/cancel or prefetch.**
14. Does `DataBufferUtils.write` release source buffers automatically? **No; releaseConsumer is needed when the application consumes the resulting Flux.**
15. Do heap dumps always reveal direct-memory leaks? **No; allocator metrics and the leak detector are needed.**
16. Does high RSS always prove a leak? **No; pools may retain memory for reuse.**
17. When is retain needed? **When creating an additional ownership reference or holding a buffer past when the current owner may release it.**
18. If holding a buffer across an asynchronous callback, what must be done? **Retain according to the source contract and release the extra reference when finished.**
19. Why should UTF-8 not be decoded per chunk independently? **Multi-byte characters can split across buffers.**
20. When should byte[] be preferred over DataBuffer? **When data is small, an independent heap object is needed, and zero-copy is unnecessary; for large streams, process chunk by chunk.**

## 15. Key Takeaways and Official References

- **`DataBuffer`** is Spring's byte buffer abstraction; **`DataBufferFactory`** allocates or wraps buffers.
- **Heap/direct** describes memory location; **pooled** describes reuse strategy.
- **`PooledDataBuffer`** uses reference counting: retain increments, release decrements, and at 0 the buffer can return to the pool.
- **Ownership matters more than the number of Java variable references.** Each owner must know when to release.
- **`DataBufferUtils`** provides retain, release, join, read, write, skip, and take.
- Decoders release input buffers upon consumption; encoder consumers release output buffers after writing.
- Use `doOnDiscard` when operators can drop DataBuffers.
- Join must be bounded; large streams should be processed chunk by chunk.
- Direct-memory leaks do not necessarily show up in heap dumps; monitor Reactor Netty allocator metrics and leak detection.

Official references:

1. [Spring Framework Reference — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): DataBuffer, DataBufferFactory, PooledDataBuffer, DataBufferUtils, ownership, decoders, and encoders.
2. [Spring Framework Javadoc — DataBuffer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/io/buffer/DataBuffer.html): read/write APIs, positions, capacity, and views.
3. [Spring Framework Javadoc — PooledDataBuffer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html): retain, release, and reference counting.
4. [Spring Framework Javadoc — DataBufferUtils](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): join, retain/release, read/write, byte limits, and releaseConsumer.
5. [Spring Framework Reference — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): DataBuffer in request/response pipelines and when applications must manage buffers.
6. [Reactor Netty Reference — Debugging a Memory Leak](https://docs.spring.io/projectreactor/reactor-netty/docs/current/reference/html/index.html#faq.memory-leak): direct memory, pooled buffers, LeakDetection logger, and active heap/direct memory metrics.
7. [Netty Reference — Reference Counted Objects](https://netty.io/wiki/reference-counted-objects.html): Netty ByteBuf reference counting model and ownership.
