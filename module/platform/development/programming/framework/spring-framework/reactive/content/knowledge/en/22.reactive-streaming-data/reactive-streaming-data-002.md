# retain, release, and Responsibilities When Working Directly with Buffers in Spring WebFlux

## 1. Why do buffers need separate lifecycle management?

In Spring WebFlux, HTTP data typically flows through layers as a **Flux<DataBuffer>** stream. DataBuffer is Spring's abstraction for a byte buffer; depending on the server and factory, it may be backed by a heap buffer, a direct buffer, or a pooled buffer.

With Reactor Netty, DataBuffer typically wraps a Netty **ByteBuf**. A ByteBuf may reside off the Java heap and be reused from a memory pool. The Garbage Collector only manages Java object lifecycles; it does not automatically decrement a ByteBuf's reference count. Therefore, code using pooled buffers must follow **retain/release** rules.

If you forget to release, the buffer may never return to the pool even though the Java object is no longer used. If you release too early or too many times, other code may read freed memory or encounter an IllegalReferenceCountException.

When working directly with DataBuffer, you must clearly establish **who owns the buffer, when ownership is transferred, and who must release it**. This is a critical part of correctness, memory safety, and performance.

## 2. DataBuffer, PooledDataBuffer, and Netty ByteBuf

### 2.1. DataBuffer is Spring's abstraction

Spring Core provides the main types:

| Type | Role |
| --- | --- |
| **DataBuffer** | Interface for reading/writing bytes, with read/write positions and optional pooling |
| **DataBufferFactory** | Creates or wraps DataBuffer instances |
| **PooledDataBuffer** | Extends DataBuffer with reference counting |
| **DataBufferUtils** | Utilities for retain, release, join, reading/writing, and buffer management |
| **NettyDataBuffer** | DataBuffer wrapping a Netty ByteBuf |
| **NettyDataBufferFactory** | Creates DataBuffers backed by a Netty ByteBufAllocator |

Not every DataBuffer is pooled. For example, DefaultDataBufferFactory can create buffers that do not use reference counting. NettyDataBuffer implements PooledDataBuffer and uses the underlying ByteBuf's reference count.

Because an application may run on multiple servers/runtimes, Spring code should prefer DataBufferUtils rather than casting every buffer to NettyDataBuffer.

### 2.2. PooledDataBuffer

PooledDataBuffer adds the following methods:

- **retain()**: increments the reference count by one.
- **release()**: decrements the reference count by one; when it reaches 0, the buffer is freed or returned to the pool.
- **isAllocated()**: indicates whether the buffer is still allocated or has been deallocated.
- **touch(hint)**: attaches a hint to assist leak tracking when supported by the implementation.

When a PooledDataBuffer is allocated, its initial reference count is **1**. This is the first reference, for which the allocating party is responsible.

### 2.3. Netty ByteBuf

Netty ByteBuf has corresponding APIs:

- **refCnt()** reads the current reference count.
- **retain()** increments the reference count.
- **release()** decrements the reference count.
- **touch(hint)** records an access location to help find leaks.
- **slice()** and **duplicate()** create views sharing the same memory region.
- **copy()** creates an independent memory region.

When the reference count reaches 0, the memory may be returned to the allocator/pool. It is not necessarily returned to the operating system immediately.

## 3. How does reference counting work?

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
| retain() | 2 | One more right to use the buffer is added |
| release() | 1 | One owner is done |
| release() | 0 | Last reference returned; buffer is deallocated/returned to pool |

**retain does not copy data.** It only keeps the memory region alive longer by incrementing the reference count.

**release does not immediately zero out bytes in the sense of a Java array.** It ends one ownership claim. When the count reaches 0, the implementation may reuse the memory region; any subsequent access is invalid.

If a buffer is accessed after its count reaches 0, Netty may throw **IllegalReferenceCountException**. Calling release more times than retain/allocate can also drive the count negative and cause a similar error.

### 3.1. Reference count is not the number of Java variables pointing to the buffer

Example:

~~~java
DataBuffer first = buffer;
DataBuffer second = buffer;
~~~

The two variables above are merely two aliases pointing to the same object. They **do not automatically increment** the reference count. If two independent owners are needed, you must retain one more time and each owner must release exactly one reference.

Creating another variable or passing the same object into a method does not automatically create additional ownership.

## 4. Ownership rules: who must release?

Netty describes the general rule: the last component to access a reference-counted object is typically responsible for releasing that reference. If a sender passes an object to a receiver, the sender typically transfers ownership as well; the receiver releases after finishing processing. If a component consumes without forwarding, that component itself releases.

### 4.1. Transferring ownership

~~~text
Component A creates buffer
        |
        v
A passes buffer to B
        |
        v
B finishes reading / writing / consuming
        |
        v
B releases
~~~

Example: an encoder creates a DataBuffer and emits it down to the response writer. The encoder has transferred the buffer to the consumer; the writer is responsible for releasing after writing.

### 4.2. Sharing ownership

If component A still needs to use the buffer while B also needs to keep the buffer, A must retain before sharing:

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

Every retained reference must have exactly one corresponding release. Do not release another component's reference.

### 4.3. Decision table

| Situation | Responsibility |
| --- | --- |
| Receive buffer and read/consume completely | Release after processing |
| Pass buffer untouched to downstream | Transfer ownership; do not release in sender |
| Keep buffer past callback or across async work | Retain before keeping; release additional reference upon completion |
| Create new buffer and emit to writer | Writer/consumer receives ownership and releases |
| Create new buffer but serialization fails before emitting | Creator must release the untransferred buffer |
| Create a view sharing memory | Check reference semantics; retain if view must outlive original owner |

Do not decide ownership based solely on method names. Read the contract of the API creating, receiving, or emitting the DataBuffer.

## 5. Prefer DataBufferUtils over calling retain/release directly

Spring provides these utilities:

~~~java
DataBufferUtils.retain(buffer);
DataBufferUtils.release(buffer);
DataBufferUtils.touch(buffer, "processing-stage");
~~~

- **DataBufferUtils.retain(buffer)** retains if the buffer is a PooledDataBuffer; if the implementation is not pooled, it does not need to increment a reference count.
- **DataBufferUtils.release(buffer)** frees the buffer according to the implementation's contract; supports PooledDataBuffer and CloseableDataBuffer.
- **DataBufferUtils.touch(buffer, hint)** attaches a hint for pooled buffers that support leak tracking.

These helpers are useful when code works with the DataBuffer abstraction without knowing whether the server uses Netty or another implementation.

The boolean returned from release indicates whether the buffer was freed by that call. For pooled buffers, false usually means the reference count is still above 0; for non-pooled implementations, the result does not mean there is a leak either. Do not use that boolean as a general-purpose ownership counter.

## 6. Synchronous buffer consumption: release in finally

If your code is the final consumer and only needs to read bytes immediately within the callback, release after reading. Use finally to guarantee release even when errors occur:

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

After copying, byte[] is independent of the original buffer. The buffer can be released even if subsequent logic continues processing byte[].

If you only read and forget to release, pooled memory can remain held and cause a memory leak.

### 6.1. Do not release before the consumer finishes reading

~~~java
DataBufferUtils.release(buffer);
byte firstByte = buffer.read();
~~~

This is use-after-release. After the final release, you must not read, write, slice, or pass the buffer to another consumer.

### 6.2. Do not release the same reference twice

~~~java
DataBufferUtils.release(buffer);
DataBufferUtils.release(buffer);
~~~

If the buffer has only one reference, the first call may drop the count to 0; the second call is an extra release and may throw IllegalReferenceCountException.

If you retained an additional reference, two releases can be valid, but they must correspond to two distinct ownership claims. Do not call release twice just because code has two cleanup branches without a clear ownership ledger.

## 7. Retain when keeping a buffer across an asynchronous boundary

A callback may receive a buffer briefly while needing to continue using the data after the callback ends, such as sending the buffer to an asynchronous file-write task, forwarding data to another queue, or holding it temporarily to assemble frames.

If the source will release the initial reference after the callback returns, a consumer that wants to keep the buffer must **retain before the callback ends**.

Example of an additional reference:

~~~java
DataBuffer retained = DataBufferUtils.retain(buffer);

return writeAsync(retained)
        .doFinally(signal -> DataBufferUtils.release(retained));
~~~

The snippet above illustrates an async task receiving an additional reference and releasing it on complete, error, or cancel. The original owner still handles the initial reference per the source's contract. If writeAsync itself takes ownership and releases, do not add a second cleanup for the same reference.

Pay attention to when retain happens. If a Publisher might never be subscribed to, retaining when building the pipeline and waiting for doFinally is unsafe because doFinally will not run if subscription never occurs. Place retain inside the subscribed lifecycle or use resource-management APIs with explicit cleanup.

**retain does not replace cancellation handling.** If a task is cancelled, the retained reference must still be released. If the task transfers the buffer to another component, ownership must be explicitly handed off to that component.

## 8. Reactor operators can drop buffers: use doOnDiscard

Some operators can discard elements without downstream ever seeing them:

- filter drops elements that do not match the predicate.
- skip drops leading elements.
- take/cancel ends the stream while prefetched elements remain.
- flatMap, reduce, and some other operators may prefetch/cache internally.
- Errors or cancellation may cause queued buffers to be discarded.

If the dropped elements are pooled DataBuffers, they still must be released.

Example: keep only buffers whose first byte is the opening character of JSON, copy kept buffers, and release:

~~~java
Flux<byte[]> jsonChunks = inbound
        .filter(this::startsWithJsonObject)
        .map(this::copyAndRelease)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

- Buffers kept by filter enter copyAndRelease and are released in finally.
- Buffers dropped by filter are released by the doOnDiscard hook.
- Buffers discarded by upstream discard-capable operators are also handled if the hook is placed appropriately in the chain.

**doOnDiscard does not replace cleanup for normally consumed buffers.** It handles elements dropped by operators. The consumer must still release buffers it receives and reads.

Place doOnDiscard in the composition chain where it applies to operators capable of discarding. Do not blindly attach it to every Flux; examine which operators have discard support and who owns each buffer.

## 9. Decoder, Encoder, and responsibilities in WebFlux

### 9.1. Decoder is the final consumer of input DataBuffers

A Decoder reads bytes from DataBuffers and turns them into higher-level objects. Once finished reading, the decoder must release the input buffer.

If a decoder simply reads one buffer and releases immediately, it can use:

~~~java
DataBufferUtils.release(dataBuffer);
~~~

If a decoder uses operators that may prefetch, cache, or drop elements such as filter/skip, add doOnDiscard to release dropped buffers. If a decoder holds buffers across multiple steps, it must release when reading finishes as well as when an error or cancellation happens before completion.

### 9.2. Encoder creates output DataBuffers

An Encoder allocates DataBuffers to write data. If serialization fails before the buffer is emitted to the consumer, the encoder must release the buffer:

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

This is an illustrative pattern with serializeInto. Once the buffer is returned to the Publisher, ownership is transferred to the next consumer. In WebFlux, the writer writing the response or client request is responsible for releasing received buffers.

Do not release the output buffer immediately after emitting; the writer still needs to read it.

### 9.3. Filters and handlers

For WebFilters or handlers working directly with the request body:

- If only inspecting metadata and passing the buffer untouched down the chain, do not release the transferred buffer.
- If the filter reads and consumes the buffer, the filter must release after reading.
- If the filter holds the buffer for later processing, retain and plan cleanup for complete/error/cancel.
- If the filter drops the buffer, clean up per contract; doOnDiscard fits when an operator discards buffers.
- If the filter creates a new buffer to replace the old one, release the old buffer once consumed and pass the new buffer downstream.

Do not release a DataBuffer that the framework or next consumer still has the right to use.

## 10. Working directly with Netty ByteBuf

### 10.1. When is accessing the native buffer needed?

NettyDataBuffer provides access to the underlying ByteBuf:

~~~java
ByteBuf nativeBuffer = nettyDataBuffer.getNativeBuffer();
~~~

This is useful when integrating low-level Netty libraries or needing ByteBuf-specific APIs. However, it ties code to the Reactor Netty/Netty implementation. Do not cast an arbitrary DataBuffer to NettyDataBuffer unless you know the actual factory/runtime.

In ordinary Spring code, prefer DataBuffer and DataBufferUtils. Drop down to ByteBuf only when necessary and when you understand native object ownership.

### 10.2. Netty slice, duplicate, and copy

With Netty ByteBuf:

| API | Memory region | Reference count |
| --- | --- | --- |
| slice() | Shares memory with original buffer | Not incremented automatically |
| duplicate() | Shares memory with original buffer, has independent reader/writer index | Not incremented automatically |
| retainedSlice() | Shares memory with original buffer | Increments reference count |
| retainedDuplicate() | Shares memory with original buffer | Increments reference count |
| copy() | Creates independent memory region | New buffer has its own reference count |

A slice/duplicate does not automatically create a new ownership claim. If passing that view to a consumer with a longer lifecycle than the original buffer, retain the view before passing it. The consumer receiving the view must release the retained reference.

Example:

~~~java
ByteBuf view = source.retainedSlice(offset, length);

try {
    inspect(view);
} finally {
    view.release();
}
~~~

This snippet fits when the current code is the final consumer of the view. If passing the view to another component, also transfer the release responsibility to the receiving component.

### 10.3. Notes on DataBuffer.slice and split

In Spring Framework 6, DataBuffer.slice(index, length) and retainedSlice(index, length) were deprecated in favor of the split(int) API, which has different semantics:

- slice creates a view sharing content without automatically retaining a reference.
- retainedSlice creates a view sharing content and retains a reference.
- split splits the buffer into two non-overlapping parts; the returned buffer contains the part before index, while the original buffer keeps the part after index.

Do not treat split as a new name with the same behavior as retainedSlice. Read the Javadoc for the exact Spring Framework version before replacing the API, and clearly determine which party owns each buffer after splitting.

### 10.4. Do not release both the wrapper and native buffer for the same reference

NettyDataBuffer wraps ByteBuf and both represent a single memory region with a shared reference count. If you call nativeBuffer.release() to return the final reference, do not also call DataBufferUtils.release(nettyDataBuffer) for that exact reference.

Use one consistent API per reference. Avoid mixing wrapper-level and native-level cleanup without tracking each retain/release.

## 11. Runnable Java 17+ example: observing retain and release

This example uses Spring Boot 3.5.5, Java 17+, and the Netty dependency from spring-boot-starter-webflux. The program creates a NettyDataBuffer using a pooled allocator, increments the reference count, and simulates two owners releasing in turn.

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

### 11.3. Running the program

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

1. The factory allocates a NettyDataBuffer, so the reference count starts at 1.
2. DataBufferUtils.retain creates an additional reference, making the count 2.
3. The original owner releases its reference; the count remains 1, so it is not deallocated yet.
4. The second consumer releases the retained reference; the count drops to 0 and the buffer is deallocated/returned to the pool.

This example inspects the Netty ByteBuf reference count directly through NettyDataBuffer. With DataBuffers from another server or a non-pooled factory, do not assume the same refCnt behavior.

## 12. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Forgetting to release buffer after reading | Pooled memory stays held, potentially causing a leak | Release after consuming |
| Releasing before downstream reads | Downstream uses a deallocated buffer | Only release after the last consumer finishes |
| Creating another variable thinking refCnt increments | Two aliases share a single reference | Retain when truly sharing ownership |
| Retaining without releasing | Reference count never reaches 0 | Attach cleanup to complete/error/cancel |
| Releasing the same reference twice | Reference count may go negative | Track each ownership lease |
| Passing slice/duplicate to an async consumer | View may die along with parent | Retain the view before handoff |
| Using copy but forgetting to release the copy | New buffer is leaked | Final consumer releases the copy |
| Filter/skip drops DataBuffer without cleanup | Discarded buffer still holds a reference | Use doOnDiscard in the right position |
| Handling only onComplete | Error/cancel skips cleanup | Handle complete, error, and cancel |
| Releasing both ByteBuf and DataBuffer wrapper | Double release of the same reference | Choose one cleanup API per reference |
| Casting every DataBuffer to NettyDataBuffer | Fails when runtime does not use Netty | Use DataBufferUtils and common abstractions |
| Storing DataBuffer in a singleton field | Concurrent requests share buffer/lifecycle | Keep per request/task and manage ownership separately |
| Relying on GC to free pooled memory | Ref count does not decrement when object becomes unreachable | Release explicitly |

## 13. Finding memory leaks and use-after-release

### 13.1. Common symptoms

- Netty reports a ByteBuf was garbage collected without release being called.
- Native memory or pooled allocator usage climbs steadily.
- Under load, OutOfDirectMemoryError appears.
- IllegalReferenceCountException when code reads/writes a deallocated buffer or releases too many times.
- Errors appear only during cancellation, retry, timeout, or high request concurrency.

A buffer leak does not necessarily surface in the request that created it. The pool may continue holding memory long after that request ends.

### 13.2. Netty leak detection

Netty provides leak detection levels:

| Level | Meaning |
| --- | --- |
| DISABLED | Disables leak detection; should not be used to hide bugs |
| SIMPLE | Samples a subset of allocations, low overhead |
| ADVANCED | Adds access records to trace usage locations |
| PARANOID | Tracks every allocation; useful in tests but carries high overhead |

Advanced leak detection can be enabled during investigation with a JVM option:

~~~bash
java -Dio.netty.leakDetectionLevel=advanced -jar app.jar
~~~

In dedicated tests, PARANOID can be used to catch bugs early, but this level should not be kept in production due to high tracking overhead.

### 13.3. Using touch to add traces

~~~java
DataBufferUtils.touch(buffer, "upload-filter: before forwarding");
~~~

Hints help the leak detector record the stage where the buffer was accessed. It does not increment the reference count, does not replace retain, and does not replace release.

### 13.4. Testing cancellation and error paths

Do not test only the happy path. Test:

- Buffer is processed completely under normal flow.
- An error occurs during reading/writing.
- Client cancels the request or subscription is cancelled.
- Filter/skip operators discard buffers.
- FlatMap prefetches and then upstream errors.
- Buffer is passed to an async task and the task times out.
- A buffer view is passed to another consumer.

Every branch must end with valid reference counts and without leaving buffers held unexpectedly.

## 14. Code review process when working directly with DataBuffer

Before merging buffer-handling code, trace each buffer:

1. **Creation source:** is the buffer allocated, wrapped, or received from the network?
2. **Initial reference:** who owns the initial reference?
3. **Handoff:** which method transfers ownership downstream?
4. **Retain:** is sharing or keeping past a callback truly needed?
5. **Release:** in which complete, error, and cancel branches is each reference released?
6. **Discard:** which operators can drop buffers and where is doOnDiscard placed?
7. **View:** do slice/duplicate share memory; is the reference count incremented?
8. **Copy:** which independent copied buffers need separate releases?
9. **Runtime:** does the code depend on NettyDataBuffer or work with the DataBuffer abstraction?
10. **Testing:** are there leak/cancel/error tests and appropriate leak detection runs?

A thorough review can map out an ownership table for each buffer: initial reference, retains, current owner, and release point. If you cannot answer who will release it, the code is incomplete.

## 15. Key takeaways

- DataBuffer is Spring's abstraction; only PooledDataBuffer has reference counting.
- NettyDataBuffer wraps ByteBuf and shares its reference count with the native buffer.
- Initial reference count is 1; retain increments by one; release decrements by one; at 0 the buffer is deallocated/returned to the pool.
- A new Java variable does not automatically create a new reference.
- When transferring ownership, the receiver is responsible for releasing; when sharing, retain for the additional owner.
- A consumer must release after reading; do not release before downstream finishes using it.
- DataBufferUtils.retain/release/touch are the right choice when working at the Spring abstraction level.
- doOnDiscard handles buffers dropped by operators; it does not replace cleanup of normally consumed buffers.
- Decoders free input after decoding; response/request writers free output emitted by encoders.
- Netty slice/duplicate share ref count; retainedSlice increments the reference; copy creates an independent buffer.
- DataBuffer.slice and retainedSlice were deprecated in Spring Framework 6.0; split(int) has different semantics.
- Handle complete, error, and cancel alike. Do not rely on the Garbage Collector to release pooled buffers.
- Use Netty leak detection and cancellation tests to uncover lifecycle bugs.

**Official documentation:**
- [Spring Framework — Data Buffers and Codecs: PooledDataBuffer, DataBufferUtils, Decoder, and Encoder](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework Javadoc — PooledDataBuffer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html)
- [Spring Framework Javadoc — DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework Javadoc — DataBuffer](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/io/buffer/DataBuffer.html)
- [Spring Framework Javadoc — NettyDataBuffer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/NettyDataBuffer.html)
- [Netty — Reference counted objects and ByteBuf lifecycle](https://netty.io/wiki/reference-counted-objects.html)
- [Netty API — ByteBuf retain, release and touch](https://netty.io/4.1/api/io/netty/buffer/ByteBuf.html)
