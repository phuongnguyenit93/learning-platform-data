# Releasing Buffers on Filtering, Errors, or Cancellation in Spring WebFlux

## 1. Why Does DataBuffer Need to Be Released?

Spring WebFlux represents byte data via `DataBuffer`. When running on Reactor Netty, buffers are typically backed by Netty `ByteBuf` and may use direct, pooled, reference-counted memory. These buffers do not live solely by Java heap garbage collection rules.

An allocated buffer typically starts with a reference count of 1:

- `retain()` increments the reference count.
- `release()` decrements the reference count.
- When the reference count reaches 0, the buffer is freed and its memory region can return to the pool.
- If the reference count never reaches 0, pooled/direct memory can remain pinned even after the Java object is no longer used.

Thus, an application may show no obvious heap growth yet still hit direct-memory exhaustion, Netty leak reports, or connection failures under rising load.

`DataBuffer` is a shared abstraction across multiple servers. With implementations like Netty or Jetty, buffers can be pooled and must be released. With unpooled `DefaultDataBufferFactory`, `DataBufferUtils.release` may be a no-op. Using `DataBufferUtils` keeps code from branching manually per implementation.

**Core principle:** whichever component receives ownership of a buffer to consume it must ensure the buffer is released exactly once for the reference that component owns, even when processing errors or is cancelled.

## 2. DataBuffer, PooledDataBuffer, and Ownership

Foundational APIs:

| API | Role |
| --- | --- |
| `DataBuffer` | Byte read/write abstraction |
| `PooledDataBuffer` | DataBuffer with reference count and pool lifecycle |
| `DataBufferFactory` | Allocates or wraps DataBuffers |
| `NettyDataBufferFactory` | DataBufferFactory backed by Netty ByteBufAllocator |
| `DataBufferUtils.release(buffer)` | Releases if the buffer is pooled |
| `DataBufferUtils.retain(buffer)` | Retains an additional reference if the buffer is pooled |
| `DataBufferUtils.releaseConsumer()` | Convenient Consumer that calls release on each buffer |
| `DataBufferUtils.join(publisher)` | Combines multiple buffers into a single buffer |

### 2.1. Reference Count Illustration

~~~text
allocate buffer
      |
      v
  refCnt = 1
      |
      +---- retain() ------> refCnt = 2
      |                         |
      |                      release()
      |                         |
      |                      refCnt = 1
      |
   release()
      |
      v
  refCnt = 0
      |
      v
buffer is freed / returned to pool
~~~

`DataBufferUtils.release` and `DataBufferUtils.retain` apply reference count operations only when the implementation supports pooled buffers. Therefore, they are preferable to casting every buffer to `PooledDataBuffer` or calling Netty APIs directly.

### 2.2. Ownership Rules in Pipelines

Clearly identify who owns each buffer:

| Scenario | Responsibility |
| --- | --- |
| Receive DataBuffer and read all content to build String/DTO | Consumer releases after reading completes |
| Receive DataBuffer and forward intact downstream | Transfer ownership downstream; do not release before downstream reads |
| Filter drops a buffer | Discarded buffer must be released |
| Operator queues buffers and is cancelled | Queue must release discarded items |
| Code manually holds buffers in a List/field/cache | Code owning the collection must release held buffers on complete, error, or cancel |
| Call retain to hold an extra reference | Must release that exact extra reference after use |
| DataBufferUtils.join merges multiple buffers | Do not release input buffers individually; release resulting buffer after consuming |
| Encoder allocates buffer but serialization fails before passing to consumer | Encoder releases the buffer it owns |
| Encoder already emitted buffer to HTTP writer | Consumer/writer is responsible for releasing |

**Do not release a buffer merely because you saw it in doOnNext.** If the pipeline still forwards the buffer to a writer or another codec, releasing early causes use-after-release or `IllegalReferenceCountException`.

Conversely, if code has already read the buffer into a byte[]/String and does not pass the buffer onward, release it within the same consumption step.

## 3. Three Scenarios to Handle: Filter, Error, and Cancellation

A pipeline working with `Flux<DataBuffer>` can terminate in several ways:

~~~text
Flux<DataBuffer>
      |
      +-- filter drops an item ----------------> DISCARD
      |
      +-- map/decode reads item ---------------> CONSUME
      |                                               |
      |                                               +-- success
      |                                               +-- exception
      |
      +-- publishOn/flatMap prefetch ------------> QUEUE
                                                      |
                                                      +-- downstream cancel
                                                      +-- upstream error
                                                      +-- queue is drained
~~~

Distinguish two categories of buffers:

1. **Buffer currently being processed:** current code is reading/decoding it. Use `try/finally` to release even if processing throws an exception.
2. **Dropped or queued buffers:** code is no longer reading them directly. Use `doOnDiscard` for Reactor operators that support discard.

One cleanup hook does not replace cleanup for the other category.

## 4. Releasing Buffers After Successful Consumption

If a consumer reads the entire content to construct a higher-level object, release after reading:

~~~java
static String readAndRelease(DataBuffer buffer) {
    try {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }
    finally {
        DataBufferUtils.release(buffer);
    }
}
~~~

This is the pattern for a consumer that **has received buffer ownership and consumes it**:

- Reads the currently readable bytes.
- Converts bytes into a String.
- Whether reading or conversion fails, the finally block still runs.
- Once converted to String, there is no longer any need to keep the DataBuffer.

If forwarding the buffer intact downstream:

~~~java
Flux<DataBuffer> forwarded = source
        .map(buffer -> buffer);
~~~

Do not release inside this map because downstream still needs to read the buffer. The final component consuming the buffer releases it, or transfers ownership to an HTTP writer/codec per API contract.

### 4.1. Never Release Before Emitting the Buffer

Wrong:

~~~java
Flux<DataBuffer> broken = source.map(buffer -> {
    DataBufferUtils.release(buffer);
    return buffer;
});
~~~

Downstream receives an already-released object. With pooled buffers, subsequent reads may fail or access invalid memory.

Right if the goal is forwarding:

~~~java
Flux<DataBuffer> forwarded = source;
~~~

Right if the goal is converting to another data type:

~~~java
Flux<String> decoded = source.map(MyDecoder::readAndRelease);
~~~

`readAndRelease` must take responsibility for releasing the buffer in finally as shown above.

## 5. Filtering DataBuffers: Use doOnDiscard

`filter` drops items that fail the predicate. Dropped items are not emitted downstream, so you cannot rely on the final consumer in the pipeline to release them.

Example:

~~~java
Flux<String> accepted = source
        .filter(buffer -> buffer.readableByteCount() >= 5)
        .map(MyDecoder::readAndRelease)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

`doOnDiscard(DataBuffer.class, DataBufferUtils::release)` registers a cleanup hook for `DataBuffer` instances discarded by discard-aware upstream operators.

### 5.1. Placement of doOnDiscard Matters

`doOnDiscard` is scoped locally and affects operators **upstream of it in the chain**. Therefore, place the hook after operators that can drop or queue items:

~~~java
source
    .filter(this::shouldKeep)
    .skip(2)
    .publishOn(Schedulers.parallel(), 16)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .map(MyDecoder::readAndRelease);
~~~

The hook sits after `filter`, `skip`, and `publishOn`, so it can handle buffers discarded by those operators, including items drained from queues on cancellation.

If placed before filter:

~~~java
// Not enough for this hook to cover a filter placed after it.
source
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .filter(this::shouldKeep);
~~~

filter is downstream of the hook, so it falls outside the upstream scope protected by this hook.

**Rule of thumb:** identify operators capable of discarding, then place `doOnDiscard` downstream of those operators in code order.

### 5.2. Filter Predicates Should Not Consume the Buffer

If only checking length, use `readableByteCount()` as in the example. If a predicate must inspect bytes, avoid reads that advance the read position without restoring it, or design reading so ownership and read position stay clear.

Do not turn a filter into a step that reads the whole body while assuming downstream decoders still have intact data. If a buffer is consumed, pass the decoded result or allocate a new buffer per contract.

### 5.3. Other Operators Can Also Discard

It is not just `filter`:

- `skip` drops leading items.
- `take` can cancel upstream once enough items are received.
- `flatMap`, `publishOn`, and prefetching/queuing operators can hold items internally.
- `reduce` or aggregating operators can cache items while processing.
- Certain buffer-managing operators have dedicated cleanup callbacks.

For decoder pipelines using operators that may prefetch/cache or drop DataBuffers, Spring recommends adding `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` to the chain.

Never assume every operator or custom Publisher supports discard hooks. If writing a custom operator capable of dropping items, that implementation must manage cleanup according to its contract.

## 6. When Decoding Throws an Exception: Release the In-Flight Item

`doOnDiscard` primarily handles items dropped by discard-aware operators. It does not replace releasing a buffer that your code is directly reading when that operation throws an exception.

Wrong example:

~~~java
Flux<String> decoded = source.map(buffer -> {
    String text = decode(buffer); // May throw exception.
    DataBufferUtils.release(buffer);
    return text;
});
~~~

If `decode(buffer)` throws an exception, the release line never runs. The current buffer leaks.

Fix with finally:

~~~java
Flux<String> decoded = source
        .map(buffer -> {
            try {
                return decode(buffer);
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        })
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Here there are two mechanisms with two scopes:

- `finally` releases the buffer received by the lambda for processing, whether decode succeeds or fails.
- `doOnDiscard` releases other buffers dropped by upstream operators or drained from queues on error/cancel.

Never call release twice for the same reference. If `decode` has already transferred buffer ownership to another component, do not release in this lambda; ownership must be documented clearly.

### 6.1. Errors Occurring After Accumulating Several Buffers

Suppose a decoder holds multiple buffers in a List itself:

~~~java
List<DataBuffer> pending = new ArrayList<>();
~~~

If the decoder manages this collection manually, it must release all retained buffers when:

- Reading succeeds and usage completes.
- A subsequent buffer triggers a parse error.
- The Publisher emits onError.
- The Subscriber cancels before the collection is fully consumed.

Do not release only the final buffer that caused the error. Previously accumulated buffers also need cleanup.

When the goal is merging buffers into one byte sequence, prefer `DataBufferUtils.join` over manually managing a List. If you must keep manual state, design the collection's lifecycle explicitly and synchronize it with error/cancel; `doOnDiscard` does not automatically see references stored inside application-managed fields or collections.

## 7. Cancellation: Releasing Items Remaining in Queues

Cancellation happens when downstream no longer wants data. Examples:

- The client closes the HTTP connection.
- The Subscriber calls cancel.
- `take(1)` has received one item and cancels upstream.
- A request times out.
- A pipeline is replaced or terminated early.

Some operators prefetch data to maintain throughput. On cancellation, queues may still contain un-emitted DataBuffers. Reactor needs to discard these items, and `doOnDiscard` helps release them.

Example:

~~~java
Flux<String> firstChunk = incomingBuffers
        .publishOn(Schedulers.parallel(), 8)
        .take(1)
        .map(MyDecoder::readAndRelease)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

If `publishOn` has prefetched buffers and `take(1)` cancels upstream, remaining buffers in the queue can be discarded. The hook at the end of the chain releases DataBuffers discarded by discard-aware upstream operators.

### 7.1. doFinally Does Not Automatically Release Every Buffer

`doFinally` receives termination signals such as complete, error, or cancel:

~~~java
pipeline.doFinally(signal -> {
    log.debug("pipeline terminated: {}", signal);
});
~~~

It is useful for cleaning up application-owned state/resources, but **it does not automatically know which DataBuffers sit inside Reactor's internal queues**. You cannot replace `doOnDiscard` with a `doFinally` that only logs.

If the application holds buffers outside queues itself, release them in an application-owned cleanup callback. If buffers are held in a collection, cleanup must handle every remaining reference. If a buffer was handed to an async task, that task's lifecycle must include release on complete/error/cancel.

### 7.2. Retaining When Holding a Buffer Across an Async Boundary

Normally, `retain` is unnecessary when reading a buffer immediately in the pipeline and releasing after consumption. Retain only when an independent extra reference is needed because another component may release the original reference while async work is still using the buffer.

Conceptual pattern:

~~~java
DataBuffer retained = DataBufferUtils.retain(buffer);

return asyncConsumer.consume(retained)
        .doFinally(signal ->
                DataBufferUtils.release(retained));
~~~

This is an **ownership pattern**, not code to blindly apply to every publisher. `retain` adds one reference; cleanup must release that exact extra reference. The original reference's owner must still fulfill its own release responsibility. Without a clear reason involving two owners, do not add retain "just in case."

Never store a DataBuffer in a field or queue and let a request end without cleanup. If transferring ownership to a worker, designate the worker as the new owner and ensure it releases across all complete/error/cancel paths.

## 8. DataBufferUtils.join: Safe Buffer Aggregation

When multiple buffers must be merged into one buffer, `DataBufferUtils.join` is the API Spring provides to do this safely and efficiently. Depending on the implementation, the result may be a new buffer or a nearly zero-copy composite buffer.

~~~java
Mono<DataBuffer> joined = DataBufferUtils.join(body);
~~~

Ownership rules of `join`:

1. Input buffers are managed as parts of the resulting buffer.
2. Do not manually release individual input buffers after calling join.
3. If the source errors or is cancelled while aggregating, accumulated buffers are released.
4. Once join emits the resulting buffer, the consumer owns consuming and releasing the resulting buffer.
5. If the consumer reads the result into a byte[]/String, release the resulting buffer in finally.

Example:

~~~java
Mono<String> bodyText = DataBufferUtils.join(body, 256 * 1024)
        .map(MyDecoder::readAndRelease);
~~~

The byte-limited overload prevents aggregating an unbounded body in memory. If exceeded, `DataBufferLimitException` is raised. Choose limits based on the contract and expected payload size.

### 8.1. Do Not Aggregate the Whole Body Unnecessarily

`join` must accumulate data before emitting the resulting buffer. For large bodies or streams such as file uploads, video, SSE, or NDJSON, aggregating the whole body increases memory pressure and latency.

Only use join when business logic truly requires the aggregated data. If chunk-by-chunk processing is possible, decode/forward incrementally and release each buffer promptly.

### 8.2. Memory Limits and Errors

Example:

~~~java
Mono<byte[]> bytes = DataBufferUtils.join(body, 1024 * 1024)
        .map(buffer -> {
            try {
                byte[] result = new byte[buffer.readableByteCount()];
                buffer.read(result);
                return result;
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        });
~~~

This caps total body size at 1 MiB. If exceeded, the pipeline emits an error rather than silently retaining unbounded buffers. The resulting buffer is released whether copying bytes succeeds or fails.

If join is cancelled before emitting a result, Spring frees accumulated buffers. If join has already emitted the result to the consumer, the consumer must release the result per the ownership contract.

## 9. Using Byte-Count Utilities

Spring provides methods to slice/skip by byte count without building a custom buffer manager:

- `DataBufferUtils.takeUntilByteCount(publisher, maxByteCount)`: takes data up to the byte limit.
- `DataBufferUtils.skipUntilByteCount(publisher, maxByteCount)`: skips data up to the byte limit.
- `DataBufferUtils.join(publisher, maxByteCount)`: merges data with a total byte limit.

Example:

~~~java
Flux<DataBuffer> firstMegabyte =
        DataBufferUtils.takeUntilByteCount(body, 1024 * 1024);

Flux<DataBuffer> afterHeader =
        DataBufferUtils.skipUntilByteCount(body, headerLength);
~~~

These helpers already handle splitting/releasing buffers according to their logic. Read the Javadoc for your Spring version before writing custom DataBuffer splitting logic, as splitting may allocate new buffers or alter ownership of data slices.

If downstream consumes the emitted buffers, downstream must still release after reading or transfer ownership onward.

## 10. Encoders: Release if Serialization Fails Before Transferring Ownership

An Encoder typically allocates a DataBuffer, writes data into it, and emits the buffer for an HTTP writer or client request to consume. If serialization fails before the buffer is passed to the consumer, the encoder still owns the buffer and must release it.

Pattern:

~~~java
DataBuffer buffer = factory.allocateBuffer();
boolean transferred = false;

try {
    serialize(value, buffer);
    transferred = true;
    return buffer;
}
finally {
    if (!transferred) {
        DataBufferUtils.release(buffer);
    }
}
~~~

This is an illustrative snippet for an encoder returning one DataBuffer. The `transferred` variable marks the ownership boundary:

- Before emitting the buffer, the encoder is responsible for releasing if an error occurs.
- After emitting the buffer, the consumer takes responsibility for reading and releasing.
- Do not release the buffer after passing it to an HTTP writer, unless the API contract explicitly requires a separate additional reference.

In normal WebFlux applications, built-in encoders/codecs already handle most of these details. Developers typically only handle them directly when writing custom codecs or manipulating DataBuffers directly.

## 11. Differences Between doOnDiscard, onOperatorError, and onNextDropped

Reactor has several cleanup hooks, each serving a distinct category of situations.

| Hook | When used | Scope |
| --- | --- | --- |
| `doOnDiscard` | Operator actively drops items or drains internal queues | Local to the chain and discard-aware upstream operators |
| `onOperatorError` | Error occurs while an operator processes onNext | Operator error hook; may need to clean up the offending item |
| `onNextDropped` | Publisher violates protocol, emitting items after terminal signal or unrequested items | Hook for items dropped due to malformed sources |
| Operator-specific cleanup | Operator maintains its own collection/queue | Cleanup callback per the operator's contract |

For typical custom decoders, start with:

1. `try/finally` for the buffer currently being read.
2. `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` for filter/prefetch/queue.
3. Explicit cleanup for buffers held by the application outside the chain.

Do not install global hooks `Hooks.onOperatorError` or `Hooks.onNextDropped` merely to patch a local pipeline. Global hooks can affect other Publishers in the JVM; only use them when building infrastructure/libraries with full understanding of their scope.

Some operators may manage collections or overlapping buffers in specialized ways. Do not assume a simple discard hook safely frees an object if that same object is still referenced by multiple active structures. Follow each operator's contract and keep ownership explicit.

## 12. Runnable Java 17+ Program with Pooled Netty DataBuffers

The example below uses Netty's allocator to create buffers with real reference counts. The program proves:

1. Buffers dropped by filter are released by `doOnDiscard`.
2. Consumed buffers are released in `finally`.
3. `DataBufferUtils.join` merges multiple buffers; releasing the result releases the components.
4. When a decoder throws an exception, the current buffer is still released.

Requirements: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. The Boot BOM manages compatible Spring Framework, Reactor, and Netty versions.

### 12.1. Project Structure

~~~text
data-buffer-cleanup-demo/
  pom.xml
  src/main/java/example/buffer/DataBufferCleanupDemo.java
~~~

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>data-buffer-cleanup-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
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

### 12.3. DataBufferCleanupDemo.java

~~~java
package example.buffer;

import java.nio.charset.StandardCharsets;
import java.util.List;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.PooledByteBufAllocator;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.NettyDataBuffer;
import org.springframework.core.io.buffer.NettyDataBufferFactory;

import reactor.core.publisher.Flux;

public final class DataBufferCleanupDemo {

    private static NettyDataBuffer create(
            NettyDataBufferFactory factory, String value) {

        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        NettyDataBuffer buffer = factory.allocateBuffer(bytes.length);
        buffer.write(bytes);
        return buffer;
    }

    private static String readAndRelease(DataBuffer buffer) {
        try {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return new String(bytes, StandardCharsets.UTF_8);
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    }

    private static String failAfterRelease(DataBuffer buffer) {
        try {
            throw new IllegalStateException("decode failed");
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    }

    public static void main(String[] args) {
        NettyDataBufferFactory factory =
                new NettyDataBufferFactory(PooledByteBufAllocator.DEFAULT);

        // 1) Filter drops one buffer. The discard hook releases it.
        NettyDataBuffer keepA = create(factory, "keep-A");
        NettyDataBuffer drop = create(factory, "no");
        NettyDataBuffer keepB = create(factory, "keep-B");

        ByteBuf keepARef = keepA.getNativeBuffer();
        ByteBuf dropRef = drop.getNativeBuffer();
        ByteBuf keepBRef = keepB.getNativeBuffer();

        List<String> filtered = Flux.just(keepA, drop, keepB)
                .filter(buffer -> buffer.readableByteCount() >= 5)
                .map(DataBufferCleanupDemo::readAndRelease)
                .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
                .collectList()
                .block();

        System.out.println("filtered=" + filtered);
        System.out.println("keepA.refCnt=" + keepARef.refCnt());
        System.out.println("drop.refCnt=" + dropRef.refCnt());
        System.out.println("keepB.refCnt=" + keepBRef.refCnt());

        // 2) join owns the input buffers; release the joined result.
        NettyDataBuffer partA = create(factory, "hello ");
        NettyDataBuffer partB = create(factory, "world");
        ByteBuf partARef = partA.getNativeBuffer();
        ByteBuf partBRef = partB.getNativeBuffer();

        String joined = DataBufferUtils.join(
                        Flux.just(partA, partB), 1024)
                .map(DataBufferCleanupDemo::readAndRelease)
                .block();

        System.out.println("joined=" + joined);
        System.out.println(
                "join.parts.refCnt=" +
                partARef.refCnt() + "," + partBRef.refCnt());

        // 3) The current item is released even when decoding fails.
        NettyDataBuffer broken = create(factory, "broken");
        ByteBuf brokenRef = broken.getNativeBuffer();

        try {
            Flux.just(broken)
                    .map(DataBufferCleanupDemo::failAfterRelease)
                    .doOnDiscard(
                            DataBuffer.class, DataBufferUtils::release)
                    .blockLast();
        }
        catch (IllegalStateException expected) {
            System.out.println("error=" + expected.getMessage());
        }

        System.out.println("error.refCnt=" + brokenRef.refCnt());
    }
}
~~~

### 12.4. Running the Program

~~~bash
mvn -q clean package
mvn -q exec:java -Dexec.mainClass=example.buffer.DataBufferCleanupDemo
~~~

**Expected stdout:**

~~~text
filtered=[keep-A, keep-B]
keepA.refCnt=0
drop.refCnt=0
keepB.refCnt=0
joined=hello world
join.parts.refCnt=0,0
error=decode failed
error.refCnt=0
~~~

Explanation:

- `keepA` and `keepB` pass the filter, are read, and are released in `readAndRelease`.
- `drop` is filtered out and released via the discard hook.
- `partA` and `partB` are placed into a composite by `join`; when the consumer releases the composite, the parts are released too.
- `broken` is the item being processed by the decoder; `finally` releases it before the error propagates outward.
- `refCnt=0` confirms each buffer's reference count dropped to 0.

The example uses `PooledByteBufAllocator` to observe Netty reference counts. In real WebFlux applications, DataBufferFactory is usually obtained from the request/response instead of constructing a factory in a controller.

## 13. Example: Cancellation in a Prefetching Pipeline

This pattern applies to a stream that may be cancelled early:

~~~java
Flux<String> firstChunk = incomingBuffers
        .publishOn(Schedulers.parallel(), 8)
        .take(1)
        .map(MyDecoder::readAndRelease)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Once downstream receives one chunk and completes, `take(1)` cancels upstream. `publishOn` may still have DataBuffers sitting in its queue due to prefetching; the discard hook releases those items.

In tests, create a source with multiple pooled buffers, let the subscriber receive one item and cancel, then assert that remaining queued buffers were released. Do not test only the normal completion path because leak bugs often hide in cancel/error paths.

If the pipeline holds DataBuffers in a manually managed collection, this hook will not release the collection automatically. Add dedicated cleanup for that state.

## 14. Debugging Memory Leaks with Netty

When the application shows signs of abnormal direct memory retention, logs may contain:

~~~text
LEAK: ByteBuf.release() was not called before it's garbage-collected
~~~

Netty has ResourceLeakDetector with the following levels:

| Level | Purpose |
| --- | --- |
| `DISABLED` | Disables leak detection; never use to hide bugs |
| `SIMPLE` | Detects leaks using default sampling |
| `ADVANCED` | Also reports recent buffer access sites |
| `PARANOID` | Checks every allocation; fits tests, high overhead |

Enable advanced mode while debugging:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar app.jar
~~~

In test environments you can use:

~~~bash
java -Dio.netty.leakDetection.level=paranoid -jar app.jar
~~~

Do not leave `PARANOID` on by default in production because tracking overhead is high. Use it to reproduce bugs in tests or debug environments, then switch back to an operations-appropriate level.

When investigating:

1. Identify the request or route allocating the buffer.
2. Find filter/skip/prefetch/flatMap operators capable of discarding.
3. Verify the hook is placed after those operators.
4. Find error/cancel paths where code currently holds buffers.
5. Check whether release happens before forwarding downstream.
6. Check whether retains are balanced by matching releases.
7. Check whether the same reference is released twice.
8. Use the leak detector to collect allocation/access traces.
9. Write regression tests for filter, error, and cancellation paths.

Do not look only at heap usage. Direct/pooled buffers may not appear in Java heap the way typical heap profilers display memory.

## 15. WebFlux Filters and Custom Codecs: Practical Notes

WebFlux usually manages DataBuffers automatically when applications work with higher-level types, for example:

~~~java
Mono<MyRequest> body = request.bodyToMono(MyRequest.class);
~~~

The codec reads incoming DataBuffers, constructs the object, and manages lifecycles per framework contract.

Be especially careful when:

- Reading `Flux<DataBuffer>` directly.
- Writing a custom `Decoder` or `Encoder`.
- Using `ServerHttpRequestDecorator` to observe/replace the body.
- Using `ServerHttpResponseDecorator` to record the response body.
- Manually aggregating the body with `join` or storing buffers for deferred processing.
- Inserting filters that can drop or delay DataBuffers.

### 15.1. Reading the Request Body in a Filter

Do not read the body to log it and then call the handler as if the body were still intact. The request body is a stream; consuming it can leave downstream handlers with nothing to read.

If inspecting the body is required:

- Consider using codecs/DTOs at the controller layer if sufficient.
- If reading raw bytes is required, enforce a size limit with `DataBufferUtils.join(body, maxBytes)`.
- After reading, if the request must be forwarded, recreate/replay the body using the appropriate decorator API.
- Manage the resulting buffer and any retained references.
- Never log passwords, tokens, or personal data.

### 15.2. Reading the Response Body in a Filter

The response body can also be a large stream. If a filter reads the body for logging without replaying it properly, the client may receive an empty body or an error.

If you only need to observe the response, prefer status, headers, duration, and byte count. If genuinely needing to inspect the body, use a decorator with bounded buffering/replay and manage DataBuffer ownership and cancellation explicitly.

### 15.3. Do Not Release Buffers Currently Being Written by the Framework

If a handler returns `Flux<DataBuffer>` to the response writer, the buffers are handed over to the writer. Do not add `doOnNext(DataBufferUtils::release)` right before returning the response if the writer still needs to read them.

Identify the final component consuming the buffer and let that consumer release it per contract.

## 16. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Filter drops DataBuffers without a discard hook | Dropped buffers are not released | Add `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` after filter |
| Placing doOnDiscard before filter | Hook does not cover downstream filter | Place hook after the discarding operator |
| Releasing only after successful decode | Exception leaks the current buffer | Use try/finally |
| Using doFinally to replace doOnDiscard | Internal queues may still retain items | Use discard hook and dedicated state cleanup |
| Releasing in doOnNext and still forwarding buffer | Downstream reads a released buffer | Transfer ownership or decode to another type before releasing |
| Manually collecting List<DataBuffer> and forgetting error/cancel | Accumulated buffers leak | Use DataBufferUtils.join or explicit collection cleanup |
| Joining and then releasing both inputs and output | May release the same references multiple times | Join takes input ownership; consumer releases output |
| Unbounded body join | Increases memory pressure or OOM | Use join with maxByteCount or streaming |
| Retaining without releasing | Reference count never reaches 0 | Balance every retain with a release |
| Releasing a buffer twice | IllegalReferenceCountException | Track owners and reference counts explicitly |
| Reading request body in filter and calling next | Handler may lose the body | Buffer/rebuild request per contract or avoid reading raw body |
| Reading response body to log without replaying | Client receives an already-consumed body | Use a decorator with bounded replay |
| Treating doOnDiscard as a global hook | Does not cover out-of-scope operators or manual state | Place hook in the right chain; clean up custom resources separately |
| Assuming every Publisher supports discard | Custom operators may drop items without calling hooks | Implement cleanup directly inside custom operators |
| Disabling Netty leak detection on warnings | Hides symptoms while leak persists | Use advanced/paranoid to investigate |
| Testing only the success path | Misses leaks on error/cancel | Test filter, error, cancellation, and prefetch queues |

## 17. Checklist Before Deploying Custom DataBuffer Pipelines to Production

- [ ] Identify whether the implementation is pooled/reference-counted.
- [ ] Document who owns the buffer at every step.
- [ ] Completely consumed buffers are released in finally.
- [ ] Buffers forwarded downstream are not released early.
- [ ] Every discard-aware filter/skip/prefetch has doOnDiscard placed properly.
- [ ] Buffers currently being processed are cleaned up individually on decode error.
- [ ] Queued buffers are cleaned up on cancellation.
- [ ] Buffers in application-held collections/state have cleanup on complete/error/cancel.
- [ ] Every retain has a matching release.
- [ ] join specifies maxByteCount when bodies can be large or client-controlled.
- [ ] Inputs whose ownership transferred to join are not released individually.
- [ ] Request/response bodies are not consumed without replay when downstream needs to read them.
- [ ] Sensitive payloads are not logged.
- [ ] Pooled buffers are tested and refCnt is verified after success/filter/error/cancel.
- [ ] Appropriate leak detection is enabled in test/debug and direct memory is monitored in operations.

## 18. Self-Check

**Q1.** Why must DataBuffers on Netty be released even though Java has a garbage collector?

Because buffers can hold direct memory in a pool and use dedicated reference counting. Garbage collection does not automatically decrement Netty's reference count.

**Q2.** When filter drops a DataBuffer, which hook should be used?

`doOnDiscard(DataBuffer.class, DataBufferUtils::release)`, placed downstream of the filter in code order so the hook applies to the upstream operator.

**Q3.** What happens if decoding a buffer throws an exception before calling release?

The current buffer can leak. Wrap decoding in try/finally and release in finally.

**Q4.** Does doOnDiscard automatically release buffers stored by the application in a List?

No. It handles items discarded by hook-aware upstream operators; application-managed collections need separate cleanup.

**Q5.** When downstream cancels after publishOn, how are buffers left in the prefetch queue handled?

The discard-aware operator drains the queue; doOnDiscard placed downstream can release the discarded DataBuffers.

**Q6.** After DataBufferUtils.join, do individual input buffers need to be released?

No. Input buffers are combined into the resulting buffer; the consumer releases the resulting buffer after use.

**Q7.** What happens if join is cancelled before emitting a result?

Spring releases the buffers accumulated during join.

**Q8.** What happens if join succeeds, but the consumer reads the result and throws an exception?

The consumer must release the resulting buffer in finally.

**Q9.** When should retain be used?

When an additional reference is needed to hold a buffer across a boundary where the original reference owner may release. The extra reference must be released after use.

**Q10.** Can doFinally replace doOnDiscard?

No. doFinally observes terminal/cancel signals; it does not automatically know which items in internal queues need releasing.

**Q11.** Does a WebFlux controller returning Mono<MyRequest> have to release DataBuffers manually?

Usually no. WebFlux codecs manage DataBuffers when converting bodies into higher-level types. Caution is needed when handling raw DataBuffers or writing custom codecs.

**Q12.** Why should you avoid joining an entire large file upload?

Because join accumulates data in memory before emitting a result. For large files, streaming chunk-by-chunk processing and releasing after consumption is usually more suitable.

## 19. Official References

- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled DataBuffer, reference count, release in decoders/encoders, and doOnDiscard.
- [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): DataBuffer in WebFlux and when applications must manage it manually.
- [Spring Framework — DataBufferUtils JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): release, retain, releaseConsumer, join, skipUntilByteCount, and takeUntilByteCount.
- [Spring Framework — PooledDataBuffer JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html): reference count, retain, release, and allocation state.
- [Spring Framework — NettyDataBuffer JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/NettyDataBuffer.html): DataBuffer backed by Netty ByteBuf.
- [Project Reactor — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html): doOnDiscard, onOperatorError, onNextDropped, and operator-specific cleanup.
- [Netty — Reference Counted Objects](https://netty.io/wiki/reference-counted-objects.html): ownership, retain/release, and troubleshooting buffer leaks.
- [Netty — ResourceLeakDetector.Level](https://netty.io/4.2/api/io/netty/util/ResourceLeakDetector.Level.html): leak detection levels and debugging overhead.

**Key takeaway:** Buffers currently being read must be released in finally; buffers dropped by filters or sitting in queues on cancellation must be released via properly placed doOnDiscard; buffers held manually by the application need dedicated cleanup. DataBufferUtils.join manages accumulated inputs on error/cancel, while the consumer releases the resulting buffer after use. Always define ownership and balance retain/release, because the garbage collector does not replace reference counting for pooled Netty memory.