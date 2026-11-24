# Buffers, Pooled Data, and Release Responsibility in Low-Level APIs

In RSocket, data passes through multiple layers: Spring APIs, the `DataBuffer` abstraction, RSocket's `Payload` API, and Netty byte buffers. When an application uses `RSocketRequester` with `Encoder`/`Decoder`, most of the buffer lifecycle is managed by the framework. When writing a custom `Decoder`, handling `Payload` directly, or keeping data across an asynchronous boundary, developers must clearly understand who owns each reference and when it needs to be released.

This lesson focuses on Spring Framework 6.2/7.x, RSocket Java, and Netty. Reference-counting rules also apply to Spring versions providing the corresponding APIs.

## 1. Where do buffers live in RSocket?

An RSocket message has a data section and an optional metadata section. In the low-level Java API, the object representing a message is `io.rsocket.Payload`; data and metadata are provided as byte buffers. RSocket Java is built on Project Reactor, and its TCP/WebSocket transports typically use Reactor Netty.

Spring provides two API levels:

- `RSocketRequester`, `@MessageMapping`, and `@RSocketExchange` work with Java objects. `RSocketStrategies` selects `Encoder`/`Decoder` to convert between objects and data on the wire.
- The low-level RSocket API works directly with `io.rsocket.RSocket` and `io.rsocket.Payload`. At this level, the application sees byte buffers and must manage the lifecycle of reference-counted objects.

In Spring, `DataBuffer` is the abstraction representing a byte region. `DataBufferFactory` allocates or wraps buffers. When the transport uses Netty, the factory is typically `NettyDataBufferFactory`, and `DataBuffer` may be backed by a Netty `ByteBuf`. With another factory, the buffer may not be pooled. Therefore, do not assume that every `DataBuffer` is reference-counted.

## 2. Pooling and reference counting

Allocating a fresh direct buffer carries significant cost. Direct memory can live off the Java heap and is often useful for network I/O because it reduces certain copies. Netty and networking libraries can reuse memory regions via a pool instead of repeatedly allocating and waiting for the garbage collector to reclaim them.

The pool needs to know precisely when a buffer is no longer in use. Spring's `PooledDataBuffer` adds a reference-counting mechanism:

1. A newly allocated pooled buffer starts with a reference count of 1.
2. `retain()` increments the reference count by 1.
3. `release()` decrements the reference count by 1.
4. When the reference count reaches 0, the buffer is freed or its memory region is returned to the pool.

For example, a buffer starts with a count of 1. After one `retain()`, the count is 2. The first `release()` lowers the count to 1 so the buffer remains alive; the second `release()` brings the count to 0 and frees the buffer.

This differs from standard Java object lifecycles. The garbage collector can reclaim the wrapper object when no strong references remain, but it does not automatically replace Netty's `release()` call. If the reference count stays above 0, pooled memory may not be returned on time. Consequently, the heap may look normal while direct memory grows steadily.

`DataBufferUtils` is a convenient way to manage Spring buffers without casting to `PooledDataBuffer`:

- `DataBufferUtils.retain(buffer)` acquires an additional reference if the buffer supports pooling.
- `DataBufferUtils.release(buffer)` releases a reference if needed. The API also handles `CloseableDataBuffer`.
- `DataBufferUtils.touch(buffer, hint)` attaches hint information for leak tracking if the implementation supports it.
- `DataBufferUtils.releaseConsumer()` returns a `Consumer` that can be used to release buffers in a stream.

The boolean return value from `release()` or `DataBufferUtils.release()` indicates whether the buffer was freed on that call. Returning `false` does not automatically mean an error: another reference may still exist, or the implementation may not require a release operation.

## 3. Ownership rules: whoever uses it last is responsible

Track ownership of each reference, not just ownership of the Java variable.

- When code allocates a pooled buffer, that code starts with one reference that must be released.
- When retaining a buffer beyond the current lifecycle or sharing it with an independent consumer, `retain()` creates an extra reference. Every retained reference must have a matching release.
- When transferring buffer ownership to the next component, the sending component normally does not release the transferred reference. The receiving component becomes responsible after finishing, unless the API contract states otherwise.
- When reading or forwarding a view of a buffer, know whether that view shares the underlying memory and reference count with the original buffer.
- Success paths, exceptions, cancellations, and discards must all have a clear release path.

In Netty, `slice()` and `duplicate()` typically create views sharing memory and reference count with the original buffer; they do not automatically increment the count. If a view must outlive its parent buffer, call `retain()` before passing the view to another component, or create an independent copy. `copy()` allocates separate memory, and that copy has its own lifecycle.

Do not release merely because a method is returning if the buffer has been handed off to another consumer. Conversely, do not store a buffer in a cache, queue, callback, or lambda without clearly specifying where it will be released. Two common bugs are leaks from missing releases and `IllegalReferenceCountException` from over-releasing or using a buffer after its count reaches 0.

## 4. Managing DataBuffer in Spring

### 4.1. Consumer reads immediately and finishes

When a `Decoder` reads the entire buffer and turns the data into an independent object, the `Decoder` should release the buffer in a `finally` block so both success and exception paths are handled.

~~~java
static String decodeUtf8(DataBuffer buffer) {
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

This pattern is for a consumer that owns the incoming buffer. If the buffer is forwarded to another component, do not release here; ownership must transfer along with the buffer.

### 4.2. Keeping a buffer across an asynchronous boundary

If async work needs the buffer after the current callback ends, retain an additional reference for that task. The current consumer releases the initial reference; the async task releases the retained reference upon completion. You must also handle the case where the executor rejects the task.

~~~java
DataBuffer retained = DataBufferUtils.retain(buffer);
try {
    executor.execute(() -> {
        try {
            decodeAndStore(retained);
        }
        finally {
            DataBufferUtils.release(retained);
        }
    });
}
catch (java.util.concurrent.RejectedExecutionException ex) {
    // Executor rejected the task: release the retained reference.
    DataBufferUtils.release(retained);
    throw ex;
}
finally {
    // Current consumer releases the initial reference.
    DataBufferUtils.release(buffer);
}
~~~

The snippet assumes the executor does not accept a task and then silently drop it. If a queue has a rejection/drop policy, that drop path must also release the reference the task would have used. For non-pooled buffers, `retain`/`release` via `DataBufferUtils` does not alter a reference count, yet the same code pattern still works.

### 4.3. Reactor may discard buffers

Operators such as `filter`, `skip`, `flatMap`, or `reduce` may hold, skip, or discard elements in certain situations. When an element is discarded, a downstream `map` may never receive the buffer to release it. For operators supporting discard hooks, add `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` to the chain. The consumer must still release buffers it actually processes.

~~~java
Flux<Command> commands = inboundBuffers
    .filter(this::isCandidate)
    .map(buffer -> {
        try {
            return decodeCommand(buffer);
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    })
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

In the example, `map` releases buffers delivered to it; `doOnDiscard` handles buffers dropped by upstream operators. Place the hook downstream of operators that can discard so the hook context propagates upstream. When using operators with prefetch or caching, verify whether the operator supports discard hooks and ensure both cancellation and errors clean up properly.

### 4.4. Joining multiple buffers

`DataBufferUtils.join(source, maxByteCount)` is a safe way to join a `Publisher<DataBuffer>` into a single `DataBuffer`. Depending on the implementation, the result may be a composite buffer without copying all bytes. If upstream errors or is cancelled during joining, accumulated buffers are released by `join`. Input buffers do not need to be released again separately.

The resulting buffer from `join` remains the consumer's responsibility. After decoding completes, release it in `finally`. Set a `maxByteCount` limit to avoid accidentally buffering an unbounded payload in memory.

~~~java
Mono<Message> message = DataBufferUtils.join(inboundBuffers, 1_048_576)
    .map(buffer -> {
        try {
            return decodeMessage(buffer);
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    });
~~~

### 4.5. InputStream and leak tracking

`DataBuffer.asInputStream()` does not release the buffer by default when the `InputStream` closes. If closing the stream should release the buffer, use the `asInputStream(true)` overload and do not release the same buffer again elsewhere. Likewise, `DataBufferUtils.touch(buffer, "rsocket inbound decode")` can add a helpful hint when investigating leaks on implementations supporting tracking.

## 5. Managing Payload in the low-level RSocket API

An RSocket `Payload` contains data and optionally metadata. In RSocket Java, `Payload` is a reference-counted object; `ByteBuf` instances obtained from `Payload` may share their lifecycle with `Payload`.

- When code owns a `Payload` and finishes reading it, release `Payload` exactly once.
- Do not release `data()` or `metadata()` separately and then release `Payload` again if those views share a reference count. Doing so can over-decrement the count.
- `data()` and `metadata()` may return the underlying buffers directly when possible; RSocket documentation recommends `sliceData()` and `sliceMetadata()` when views are needed. Slices still share the reference count and do not create independent ownership.
- If data must be kept after `Payload` is released, retain the appropriate reference or copy bytes to independent memory.

### 5.1. Converting Payload to DataBuffer

Spring provides `PayloadUtils.retainDataAndReleasePayload(payload, bufferFactory)`. This helper slices the data section, retains and wraps it as a `DataBuffer`, and releases `Payload`. Metadata must be read before calling this helper. Afterward, downstream code works only with `DataBuffer` and must release `DataBuffer` when done reading.

~~~java
DataBuffer data = PayloadUtils.retainDataAndReleasePayload(payload, bufferFactory);
try {
    return decoder.decode(data);
}
finally {
    DataBufferUtils.release(data);
}
~~~

This is a synchronous decode example. If a decoder returns a `Mono` or `Flux` that still reads `DataBuffer` after the current method returns, do not release immediately in `finally`. Tie cleanup to when the reactive work completes, errors, or is cancelled; or copy the data into an independent object before returning the publisher.

### 5.2. Creating Payload from DataBuffer

`PayloadUtils.createPayload(data)` and `createPayload(data, metadata)` create a `Payload` from `DataBuffer`. If a `NettyDataBuffer` is present, the helper can create a `ByteBufPayload` backed by the native `ByteBuf` or wrapped `ByteBuffer`; if both buffers are `DefaultDataBuffer`, the helper creates a `DefaultPayload`. This means you should not assume conversion always makes an independent copy. Track ownership of the original buffer and `Payload` according to your version's contract, avoiding freeing the same memory region via two ownership paths.

### 5.3. When is manual Payload management unnecessary?

With `RSocketRequester`, `@MessageMapping`, `@RSocketExchange`, and `RSocketStrategies`, applications typically exchange Java objects and let `Encoder`/`Decoder` handle conversion. The framework manages most of the `Payload` and buffer lifecycle inside its pipeline. Do not manually call `release` on internal `Payload` objects that the framework already owns. Manual management generally appears only when writing custom `Encoder`/`Decoder` implementations, interacting directly with `io.rsocket.RSocket`, or holding buffers outside the standard pipeline.

## 6. Java 17 example: reading and releasing an application-created Payload

The following example creates a text `Payload`, reads its content, and releases the `Payload` in `finally`. It illustrates the lifecycle of a `Payload` owned by the program itself; this is not yet a client/server RSocket connection.

Create a Maven project with the following dependencies and plugins:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>payload-release-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.rsocket</groupId>
            <artifactId>rsocket-core</artifactId>
            <version>1.1.5</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create `src/main/java/example/PayloadReleaseDemo.java`:

~~~java
package example;

import io.rsocket.Payload;
import io.rsocket.util.ByteBufPayload;

public class PayloadReleaseDemo {

    public static void main(String[] args) {
        Payload payload = ByteBufPayload.create("hello");

        try {
            System.out.println(payload.getDataUtf8());
        }
        finally {
            payload.release();
        }
    }
}
~~~

Run with Java 17 or later:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.PayloadReleaseDemo
~~~

Exact stdout:

~~~text
hello
~~~

The `Payload` is created in `main`, so the program owns the initial reference and releases it after the final read. If `retain()` is called before passing the `Payload` to an independent consumer, each additional reference must be released once. Never retain a `Payload` or `ByteBuf` after it has been released.

### 6.1. Verifying reference count with Spring DataBuffer

The snippet below illustrates the Spring API when the factory uses Netty's pooled allocator. `spring-core` and a compatible Netty buffer dependency are required in the project.

~~~java
NettyDataBufferFactory factory =
        new NettyDataBufferFactory(PooledByteBufAllocator.DEFAULT);

DataBuffer buffer = factory.allocateBuffer(16);
DataBufferUtils.retain(buffer);

System.out.println(DataBufferUtils.release(buffer));
System.out.println(DataBufferUtils.release(buffer));
~~~

Output:

~~~text
false
true
~~~

The first release only decrements the count from 2 to 1, so the buffer is not yet deallocated. The second release brings the count to 0. This result applies only to the pooled buffer in the example; for non-pooled buffers, `DataBufferUtils.release` may return `false` because no deallocation operation is needed.

## 7. Common errors and investigation

| Symptom | Common Cause | How to Investigate |
|---|---|---|
| Direct memory climbs steadily, LEAK logs appear | Missing release on a processing branch | Check success, error, cancel, discard, and rejected queue paths |
| IllegalReferenceCountException | Using a buffer after count reaches 0 or over-releasing | Trace retain/release locations and slice/duplicate views |
| Error appears only under high load | Prefetch, buffering, or concurrency exposes discard paths | Check `doOnDiscard`, buffer limits, and cancellation |
| Data corrupted after moving to async | Original buffer was released before consumer finished reading | Retain before handoff or copy the data |
| Heap is stable but process runs out of native memory | Pooled/direct buffers not returned to pool | Enable leak detection and audit ownership |

When running tests or investigating leaks with Netty, you can enable `ResourceLeakDetector` at `ADVANCED` or `PARANOID` level. Example configuration in code:

~~~java
ResourceLeakDetector.setLevel(ResourceLeakDetector.Level.ADVANCED);
~~~

You can use `DataBufferUtils.touch(buffer, "route=orders.stream")` to attach hints for the leak tracker. Leak detection carries overhead, so increase verbosity only in tests or during targeted investigations.

## 8. Checklist before merging buffer-handling code

- Identify the `DataBuffer` implementation: pooled or non-pooled; Netty or another implementation.
- Document who allocates, who receives ownership, who forwards, and who releases.
- Every `retain` has a corresponding `release`; never release the same reference twice.
- Discarded buffers, errors, cancellations, or rejected tasks are all cleaned up.
- Do not assume `slice`/`duplicate` creates an independent reference count.
- When using `DataBufferUtils.join`, do not re-release input buffers; release the resulting buffer after use.
- When using `PayloadUtils.retainDataAndReleasePayload`, read metadata first and release the resulting `DataBuffer` after use.
- When using `RSocketRequester` and standard codecs, let the framework manage internal `Payload` lifecycles.
- Never keep `ByteBuf`/`DataBuffer` in a cache or callback after it has been released.

## References

- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc — PayloadUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/PayloadUtils.html)
- [Spring Framework Javadoc — DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [RSocket Java Javadoc — ByteBufPayload](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/util/ByteBufPayload.html)
- [Netty — Reference counted objects](https://netty.io/wiki/reference-counted-objects.html)
