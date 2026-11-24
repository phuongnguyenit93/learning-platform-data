# retain, release, and Responsibilities When Manipulating Buffers Directly in Spring WebFlux

## 1. Why Do Buffers Need Separate Lifecycle Management?

In Spring WebFlux, HTTP data typically flows across layers as a **Flux<DataBuffer>** stream. DataBuffer is Spring's abstraction for byte buffers; depending on the server and factory, it may be backed by a heap buffer, a direct buffer, or a pooled buffer.

With Reactor Netty, DataBuffer typically wraps a Netty **ByteBuf**. ByteBuf may reside outside the Java heap and be reused from a memory pool. The Garbage Collector only manages Java object lifecycles; it does not automatically decrement a ByteBuf's reference count. Therefore, code using pooled buffers must obey **retain/release** rules.

If you forget to release, the buffer may not return to the pool even after the Java object is no longer referenced. If you release too early or multiple times, other code may read already-freed memory or encounter IllegalReferenceCountException.

When manipulating DataBuffers directly, you must clearly establish **who owns the buffer, when ownership is transferred, and who must release it**.

## 2. DataBuffer, PooledDataBuffer, and Netty ByteBuf

### 2.1. DataBuffer Is Spring's Abstraction

Spring Core provides the main types:

| Type | Role |
| --- | --- |
| **DataBuffer** | Interface for reading/writing bytes, with independent read/write positions and optional pooling |
| **DataBufferFactory** | Allocates or wraps DataBuffers |
| **PooledDataBuffer** | Extends DataBuffer with reference counting |
| **DataBufferUtils** | Utilities for retain, release, join, reading/writing, and buffer management |
| **NettyDataBuffer** | DataBuffer wrapping a Netty ByteBuf |
| **NettyDataBufferFactory** | Allocates DataBuffers backed by a Netty ByteBufAllocator |

Not every DataBuffer is pooled. For example, DefaultDataBufferFactory can create buffers without reference counting. NettyDataBuffer implements PooledDataBuffer and delegates to the underlying ByteBuf's reference count.

Because applications may run across different servers/runtimes, Spring code should prefer DataBufferUtils rather than casting every buffer to NettyDataBuffer.

### 2.2. PooledDataBuffer

PooledDataBuffer adds the following methods:

- **retain()**: increments the reference count by one.
- **release()**: decrements the reference count by one; at 0, the buffer is freed or returned to the pool.
- **isAllocated()**: indicates whether the buffer is still allocated or already deallocated.
- **touch(hint)**: attaches a hint for leak tracking when supported by the implementation.

When a PooledDataBuffer is allocated, its initial reference count is **1**. This is the initial reference for which the allocating party is responsible.

### 2.3. Netty ByteBuf

Netty ByteBuf provides corresponding APIs:

- refCnt() reads the current reference count.
- retain() increments the reference count.
- release() decrements the reference count.
- touch(hint) records an access location to aid leak investigation.
- slice() and duplicate() create views sharing the same memory region.
- copy() creates an independent memory region.

When the reference count reaches 0, the memory region can be returned to the allocator/pool. It is not necessarily returned immediately to the operating system.

## 3. How Does Reference Counting Work?

Suppose a buffer is created with a reference count of 1:

~~~text
allocate
   |
   v
refCnt = 1
   |
   +-- retain()  ---> refCnt = 2
   |
   +-- release() ---> refCnt = 1
   |
   +-- release() ---> refCnt = 0
                           |
                           v
                    deallocate / pool
~~~

| Operation | Reference count | Meaning |
| --- | ---: | --- |
| Allocate | 1 | Initial owner holds one reference |
| retain() | 2 | An additional right to use the buffer exists |
| release() | 1 | One owner finished |
| release() | 0 | Last reference returned; buffer is deallocated/returned to pool |

**retain does not copy data.** It merely keeps the memory region alive longer by incrementing the reference count.

**release does not immediately zero out bytes in the Java array sense.** It ends one ownership lease. When the count reaches 0, the implementation may reuse the memory; any subsequent access is invalid.

Accessing a buffer after its count reaches 0 can cause Netty to throw **IllegalReferenceCountException**. Calling release more times than retain/allocate allows can also drive the count negative and trigger a similar error.

### 3.1. Reference Count Is Not the Number of Java Variables Pointing to the Buffer

Example:

~~~java
DataBuffer first = buffer;
DataBuffer second = buffer;
~~~

Those two variables are merely two aliases pointing to the same object. They **do not automatically increment** the reference count. If two independent owners are needed, you must retain once more and each owner must release exactly one reference.

Creating extra variables or passing the same object into a method does not automatically create extra ownership.

## 4. Ownership Rules: Who Must Release?

### 4.1. Transferring Ownership

One component receives a buffer, finishes its work, and passes the buffer to the next component. When ownership is transferred completely, the sending component usually no longer releases; the final receiving component is responsible.

~~~text
Component A creates buffer
        |
        v
A passes buffer to B
        |
        v
B finishes read / write / consume
        |
        v
B releases
~~~

Example: an encoder allocates a DataBuffer and emits it down to the response writer. The encoder has handed the buffer over to the consumer; the writer is responsible for releasing it after writing.

### 4.2. Sharing Ownership

If component A still needs to use the buffer while B also needs to hold the buffer, A must retain before sharing:

~~~text
allocate: refCnt = 1
        |
        v
retain for B: refCnt = 2
        |
        +------------------+
        |                  |
        v                  v
A finishes, releases    B finishes, releases
        |                  |
        +--------+---------+
                 |
                 v
             refCnt = 0
~~~

Each retained reference must have exactly one matching release. Never release another component's reference.

### 4.3. Decision Table

| Scenario | Responsibility |
| --- | --- |
| Receive buffer and read/consume completely | Release after processing |
| Forward buffer intact downstream | Transfer ownership; do not release in sender |
| Hold buffer past callback or across async task | Retain before keeping; release extra reference when done |
| Allocate new buffer then emit to writer | Writer/consumer receives ownership and releases |
| Allocate new buffer but serialization fails before emit | Creator must release the untransferred buffer |
| Create view sharing memory | Check reference semantics; retain if view must outlive original owner |

Never decide ownership based solely on method names. Read the contract of the API creating, receiving, or emitting the DataBuffer.

## 5. Prefer DataBufferUtils Over Calling retain/release Directly

Spring provides utility methods:

~~~java
DataBufferUtils.retain(buffer);
DataBufferUtils.release(buffer);
DataBufferUtils.touch(buffer, "processing-stage");
~~~

- **DataBufferUtils.retain(buffer)** retains if the buffer is a PooledDataBuffer; if the implementation is unpooled, no reference count increment is needed.
- **DataBufferUtils.release(buffer)** frees the buffer per the implementation's contract; supports PooledDataBuffer and CloseableDataBuffer.
- **DataBufferUtils.touch(buffer, hint)** attaches a hint for pooled buffers that support leak tracking.

These helpers are useful when code works against the DataBuffer abstraction without knowing whether the server uses Netty or another implementation.

The boolean returned by release indicates whether the operation actually freed the buffer. For pooled buffers, false typically means the reference count is still above 0; for unpooled implementations, the result does not imply a leak either. Do not use that boolean as a general ownership counter.

## 6. Synchronous Buffer Consumption: Release in finally

If your code is the final consumer and only needs to read bytes immediately inside the callback, release after reading. Use finally to guarantee release even when processing throws an error:

~~~java
byte[] copyAndRelease(DataBuffer buffer) {
    try {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return bytes;
    } finally {
        DataBufferUtils.release(buffer);
    }
}
~~~

After copying, the byte[] is independent of the original buffer. The buffer can be released even if subsequent logic continues processing the byte[].

If you only read and forget to release, pooled memory can remain pinned and cause a memory leak.

### 6.1. Never Release Before the Consumer Finishes Reading

~~~java
DataBufferUtils.release(buffer);
byte firstByte = buffer.read();
~~~

This is use-after-release. After the final release, never read, write, slice, or pass the buffer to another consumer.

### 6.2. Never Release the Same Reference Twice

~~~java
DataBufferUtils.release(buffer);
DataBufferUtils.release(buffer);
~~~

If the buffer has only one reference, the first call may drop the count to 0; the second call is an extra release and may throw IllegalReferenceCountException.

If an additional reference was retained, two releases can be valid, but they must correspond to two distinct ownerships. Never call release twice simply because code has two cleanup branches without a clear ownership ledger.

## 7. Retaining When Holding a Buffer Across an Async Boundary

A callback may receive a buffer briefly yet need to keep using its data after the callback finishes, such as sending the buffer to an asynchronous file write task, moving data to another queue, or staging it to assemble frames.

If the source will release the initial reference after the callback returns, a consumer wanting to keep the buffer must **retain before the callback ends**.

Example with an additional reference:

~~~java
DataBuffer retained = DataBufferUtils.retain(buffer);

return writeAsync(retained)
        .doFinally(signal -> DataBufferUtils.release(retained));
~~~

Meaning:

1. retain creates a separate reference for the async task.
2. The original owner still handles the original reference per the source contract.
3. The async task releases the retained reference on complete, error, or cancel.
4. writeAsync must not release that same reference a second time if doFinally already owns that responsibility.

This snippet assumes the Publisher is subscribed to and the task can terminate via complete/error/cancel. If a Publisher might be abandoned without subscribing, never retain eagerly at assembly time and leave an orphaned reference. Place retain within a lifecycle guaranteeing cleanup and clearly identify who owns the initial reference.

**retain does not replace cancellation handling.** If the task is cancelled, the held extra reference must still be released. If the task transfers the buffer to another component, ownership must be explicitly transferred to that component.

## 8. Reactor Operators That Drop Buffers: Use doOnDiscard

Some operators can drop elements without downstream ever seeing them:

- filter drops elements failing a predicate.
- skip discards leading elements.
- take/cancel terminates the stream while prefetched elements remain.
- flatMap, reduce, and certain operators can prefetch/cache internally.
- Errors or cancellation can cause queued buffers to be discarded.

If dropped elements are pooled DataBuffers, they still must be released.

Example: keep only buffers whose first byte is '{', copy kept buffers, and release:

~~~java
Flux<byte[]> jsonChunks = inbound
        .filter(this::startsWithJsonObject)
        .map(this::copyAndRelease)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

- Buffers kept by filter flow into copyAndRelease and are released in finally.
- Buffers dropped by filter are released by the doOnDiscard hook.
- Buffers discarded by upstream discard-aware operators are also handled if the hook is placed properly in the chain.

**doOnDiscard does not replace cleanup of normally consumed buffers.** It handles elements dropped by operators. The consumer must still release buffers it receives and reads.

Place doOnDiscard in the composition chain so it applies to operators capable of discarding. Do not add it mechanically to every Flux; check which operators support discard and who owns each buffer.

## 9. Decoder, Encoder, and Responsibilities in WebFlux

### 9.1. Decoder Is the Final Consumer of Input DataBuffers

A Decoder reads bytes from DataBuffers and converts them into higher-level objects. Once reading finishes, the decoder must release input buffers.

If a decoder only reads one buffer and releases immediately, it can use:

~~~java
DataBufferUtils.release(dataBuffer);
~~~

If a decoder uses operators that can prefetch, cache, or drop elements such as filter/skip, add doOnDiscard to release dropped buffers. If a decoder holds buffers across multiple steps, it must release on completion as well as when errors/cancellation occur before reading finishes.

### 9.2. Encoder Allocates Output DataBuffers

An Encoder allocates DataBuffers to write data. If serialization fails before the buffer is emitted downstream to the consumer, the encoder must release the buffer:

~~~java
DataBuffer buffer = factory.allocateBuffer();
boolean transferred = false;

try {
    serializeInto(buffer);
    transferred = true;
    return buffer;
} finally {
    if (!transferred) {
        DataBufferUtils.release(buffer);
    }
}
~~~

This is an illustrative pattern using serializeInto. Once the buffer is returned to the Publisher, ownership transfers to the next consumer. In WebFlux, the writer writing the response or client request is responsible for releasing received buffers.

Never release an output buffer immediately after emitting it; the writer still needs to read it.

### 9.3. Filters and Handlers

For WebFilters or handlers directly manipulating request bodies:

- If only inspecting metadata and passing the buffer intact down the chain, do not release the transferred buffer.
- If the filter reads and consumes the buffer, the filter must release after reading.
- If the filter retains the buffer for deferred processing, retain and plan cleanup for complete/error/cancel.
- If the filter drops the buffer, clean up per contract; doOnDiscard fits when operators discard buffers.
- If the filter allocates a new buffer to replace an old one, release the old buffer once consumed and pass the new buffer downstream.

Never release a DataBuffer that the framework or next consumer still has the right to use.

## 10. Working Directly with Netty ByteBuf

### 10.1. When Is Access to the Native Buffer Needed?

NettyDataBuffer provides:

~~~java
ByteBuf nativeBuffer = nettyDataBuffer.getNativeBuffer();
~~~

This is useful when integrating low-level Netty libraries or needing ByteBuf-specific APIs. However, it couples code to the Reactor Netty/Netty implementation. Never cast an arbitrary DataBuffer to NettyDataBuffer without knowing the actual factory/runtime.

In normal Spring code, prefer DataBuffer and DataBufferUtils. Drop down to ByteBuf only when necessary and when native object ownership is clear.

### 10.2. slice, duplicate, and copy

With Netty ByteBuf:

| API | Memory region | Reference count |
| --- | --- | --- |
| slice() | Shares memory region with original buffer | Does not increment automatically |
| duplicate() | Shares memory region with original buffer, with independent reader/writer indices | Does not increment automatically |
| retainedSlice() | Shares memory region with original buffer | Increments reference count |
| copy() | Creates an independent memory region | New buffer has its own reference count |

A slice/duplicate does not automatically create a new ownership. If passing that view to a consumer with a longer lifecycle than the original buffer, retain before passing. The consumer receiving the view must release the retained reference.

Example:

~~~java
ByteBuf view = source.retainedSlice(offset, length);

try {
    inspect(view);
} finally {
    view.release();
}
~~~

This suits cases where current code is the final consumer of the view. If passing the view to another component, transfer release responsibility to the receiving component as well.

### 10.3. Note on DataBuffer.slice and retainedSlice

In Spring Framework 6, DataBuffer.slice(index, length) and retainedSlice(index, length) were deprecated in favor of the split(int) API with different semantics. Do not copy old slice examples into new code without checking version and contract.

When using newer APIs, read the Javadoc for your exact Spring Framework version. Never assume every created view increments reference count or has an independent lifecycle.

### 10.4. Do Not Release Both Wrapper and Native Buffer for the Same Reference

NettyDataBuffer wraps ByteBuf and both represent the same memory region with a shared reference count. If calling nativeBuffer.release() to return the final reference, do not also call DataBufferUtils.release(nettyDataBuffer) for that same reference.

Use one consistent API per reference. Avoid mixing wrapper-level and native-level cleanup without tracking every retain/release.

## 11. Runnable Java 17+ Example: Observing retain and release

The example uses Spring Boot 3.5.5, Java 17+, and the Netty dependency from spring-boot-starter-webflux. The program allocates a NettyDataBuffer using a pooled allocator, increments the reference count, and simulates two owners releasing in turn.

Structure:

~~~text
buffer-ownership-demo/
├── pom.xml
└── src/main/java/example/buffer/BufferOwnershipDemo.java
~~~

### 11.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>buffer-ownership-demo</artifactId>
    <version>1.0.0</version>

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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.buffer.BufferOwnershipDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.2. BufferOwnershipDemo.java

~~~java
package example.buffer;

import java.nio.charset.StandardCharsets;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.PooledByteBufAllocator;

import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.NettyDataBuffer;
import org.springframework.core.io.buffer.NettyDataBufferFactory;

public class BufferOwnershipDemo {

    public static void main(String[] args) {
        NettyDataBufferFactory factory =
                new NettyDataBufferFactory(PooledByteBufAllocator.DEFAULT);

        NettyDataBuffer buffer = factory.allocateBuffer(16);
        buffer.write("hello".getBytes(StandardCharsets.UTF_8));

        ByteBuf nativeBuffer = buffer.getNativeBuffer();

        System.out.println("initial refCnt = " + nativeBuffer.refCnt());

        // Give a second consumer its own reference.
        DataBufferUtils.touch(buffer, "async consumer");
        DataBufferUtils.retain(buffer);

        System.out.println("after retain = " + nativeBuffer.refCnt());

        // The original owner is finished with its reference.
        boolean senderReleased = DataBufferUtils.release(buffer);

        System.out.println(
                "sender release deallocated = " + senderReleased);
        System.out.println("after sender release = " + nativeBuffer.refCnt());

        // The second consumer releases the retained reference.
        boolean consumerReleased = DataBufferUtils.release(buffer);

        System.out.println(
                "consumer release deallocated = " + consumerReleased);
        System.out.println("after consumer release = " + nativeBuffer.refCnt());
    }
}
~~~

### 11.3. Running the Program

In the directory containing pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Stdout:

~~~text
initial refCnt = 1
after retain = 2
sender release deallocated = false
after sender release = 1
consumer release deallocated = true
after consumer release = 0
~~~

Explanation:

1. The factory allocates a NettyDataBuffer so the reference count starts at 1.
2. DataBufferUtils.retain adds another reference, bringing the count to 2.
3. The original owner releases its reference; count drops to 1 so it is not yet deallocated.
4. The second consumer releases the retained reference; count reaches 0 and the buffer is deallocated/returned to the pool.

The example directly inspects Netty ByteBuf's reference count via NettyDataBuffer. For DataBuffers from other servers or unpooled factories, never assume the same refCnt behavior.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Forgetting to release a buffer after reading | Pooled memory stays pinned, risking leaks | Release after consumption |
| Releasing before downstream reads | Downstream uses a deallocated buffer | Release only after final consumer finishes |
| Creating another variable and thinking refCnt increases | Two aliases share one reference | Retain when genuinely sharing ownership |
| Retaining without releasing | Reference count never reaches 0 | Attach cleanup to complete/error/cancel |
| Releasing the same reference twice | Reference count can go negative | Track each ownership lease |
| Using slice/duplicate and passing to async consumer | View can die with parent | Retain view before handoff |
| Using copy and forgetting to release the copy | New buffer leaks | Final consumer releases the copy |
| Filter/skip dropping DataBuffers without cleanup | Discarded buffers still hold references | Place doOnDiscard in the right spot |
| Handling only onComplete | Error/cancel skips cleanup | Handle complete, error, and cancel |
| Releasing both ByteBuf and DataBuffer wrapper | Double release of the same reference | Pick one cleanup API per reference |
| Casting every DataBuffer to NettyDataBuffer | Fails when runtime does not use Netty | Use DataBufferUtils and common abstractions |
| Storing DataBuffer in a singleton field | Concurrent requests share buffer/lifecycle | Keep per request/task and manage ownership separately |
| Relying on GC to free pooled memory | Ref count does not drop when object becomes unreachable | Release explicitly |

## 13. Finding Memory Leaks and Use-After-Release

### 13.1. Common Symptoms

- Netty reports that a ByteBuf was garbage-collected before release was called.
- Native memory or pooled allocator usage climbs steadily.
- Under load, OutOfDirectMemoryError appears.
- IllegalReferenceCountException when code reads/writes a deallocated buffer or over-releases.
- Bugs appear only under cancellation, retries, timeouts, or concurrent requests.

A buffer leak does not necessarily surface in the request that created it. The pool may keep holding memory long after the request ends.

### 13.2. Netty Leak Detection

Netty provides leak detection levels:

| Level | Meaning |
| --- | --- |
| DISABLED | Disables leak detection; never use to hide bugs |
| SIMPLE | Samples a fraction of allocations, low overhead |
| ADVANCED | Adds access records to trace usage sites |
| PARANOID | Tracks every allocation; useful in tests but high overhead |

You can enable advanced leak detection during investigation via JVM option:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar app.jar
~~~

In dedicated tests you can use PARANOID to catch bugs early, but do not keep this level in production due to high tracking overhead.

### 13.3. Using touch to Add Traces

~~~java
DataBufferUtils.touch(buffer, "upload-filter: before forwarding");
~~~

Hints help the leak detector record the stage where a buffer was accessed. It does not increment the reference count, does not replace retain, and does not replace release.

### 13.4. Testing Cancellation and Error Paths

Do not test only the happy path. Test:

- Buffers processed completely under normal flow.
- Errors occurring mid-read/write.
- Client cancelling the request or subscription cancellation.
- Filter/skip operators dropping buffers.
- FlatMap prefetch followed by upstream error.
- Buffers handed to an async task and task timeout.
- Buffer views passed to another consumer.

Every branch must terminate with valid reference counts and leave no buffers unexpectedly retained.

## 14. Code Review Checklist When Manipulating DataBuffer Directly

Before merging buffer-handling code, trace each buffer:

1. **Creation source:** was the buffer allocated, wrapped, or received from the network?
2. **Initial reference:** who owns the first reference?
3. **Handoff:** which method transfers ownership downstream?
4. **Retain:** is sharing or keeping across callbacks genuinely needed?
5. **Release:** in which complete, error, and cancel branches is each reference released?
6. **Discard:** which operators can drop buffers and where is the doOnDiscard hook placed?
7. **Views:** do slice/duplicate share memory; does reference count increment?
8. **Copies:** which independent copied buffers need separate release?
9. **Runtime:** does the code depend on NettyDataBuffer or work with the DataBuffer abstraction?
10. **Testing:** are there leak/cancel/error tests and appropriate leak detection runs?

A thorough review can tabulate ownership per buffer: initial reference, retains, current owner, and release point. If you cannot answer who will release, the code is unfinished.

## 15. Key Takeaways

- DataBuffer is Spring's abstraction; only PooledDataBuffer has reference counting.
- NettyDataBuffer wraps ByteBuf and shares its reference count with the native buffer.
- Initial reference count is 1; retain increments by one; release decrements by one; at 0 the buffer is deallocated/returned to the pool.
- A new Java variable does not automatically create a new reference.
- When transferring ownership, the receiver is responsible for releasing; when sharing, retain for the additional owner.
- Consumers must release after reading; never release before downstream finishes using it.
- DataBufferUtils.retain/release/touch are the right choice when working at Spring's abstraction layer.
- doOnDiscard handles buffers dropped by operators; it does not replace cleanup of normally consumed buffers.
- Decoders release input after decoding; response/request writers release output emitted by encoders.
- Netty slice/duplicate share ref count; retainedSlice increments reference; copy allocates an independent buffer.
- Handle complete, error, and cancel. Never rely on the Garbage Collector to release pooled buffers.
- Use Netty leak detection and cancellation tests to catch lifecycle bugs.

**Official Documentation:**
- [Spring Framework — Data Buffers and Codecs: PooledDataBuffer, DataBufferUtils, Decoder, and Encoder](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework Javadoc — PooledDataBuffer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html)
- [Spring Framework Javadoc — DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework Javadoc — NettyDataBuffer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/NettyDataBuffer.html)
- [Netty — Reference counted objects and ByteBuf lifecycle](https://netty.io/wiki/reference-counted-objects.html)
- [Netty API — ByteBuf retain, release and touch](https://netty.io/4.1/api/io/netty/buffer/ByteBuf.html)
