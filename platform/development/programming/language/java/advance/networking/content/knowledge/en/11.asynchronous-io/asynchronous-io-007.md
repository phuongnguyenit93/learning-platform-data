# ByteBuffer Ownership While an Operation Is Pending

*Java Advance module – networking; context: asynchronous I/O with `AsynchronousSocketChannel`.*

## 1. The Most Important Rule

When an application calls `AsynchronousSocketChannel.read(dst)` or `AsynchronousSocketChannel.write(src)`, the I/O operation **may still be running after the Java method returns**. These APIs do not behave like synchronous `SocketChannel.read/write`: they initiate an operation and return a `Future<Integer>`, or accept a `CompletionHandler` to notify the result later.

**From the moment an operation is submitted until it completes, the ByteBuffer is handed over to I/O: do not access, modify, `flip`, `clear`, `compact`, reuse, return to a pool, or mutate its backing storage.** Only process the buffer after confirming successful completion, or perform careful cleanup when the operation fails.

This rule is explicitly stated in the `AsynchronousByteChannel` Javadoc: a ByteBuffer is not safe for use by multiple concurrent threads, and accessing the buffer must be avoided from the time a read/write is initiated until the operation completes.

~~~text
APP OWNS THE BUFFER
   |
   +-- Prepare payload or empty space, proper position / limit
   |
   +-- Submit async read(dst) or write(src)
   v
I/O PENDING  (buffer belongs to the operation)
   |
   +-- FORBIDDEN for app/aliases to touch the buffer
   |
   +-- SUCCESS: Future.get() / CompletionHandler.completed()
   |       |
   |       +-- check actual bytes transferred
   |       +-- handle partial read/write
   |       +-- parse / continue I/O / release when truly done
   |
   +-- FAILED / TIMEOUT / CANCELLED
           |
           +-- handle per API contract, do not assume safe state
~~~

Operation speed is unpredictable: it may complete before the next line of code, or it may take a very long time. Seeing a `Future` is **not** proof of completion.

## 2. ByteBuffer Holds Both Data and Cursor State

`ByteBuffer` is byte memory together with markers:

| API | Meaning |
|---|---|
| `capacity()` | Maximum capacity of the buffer; fixed for the object |
| `position()` | Index of the next byte for relative operations |
| `limit()` | **Exclusive** bound that must not be exceeded |
| `remaining()` | `limit - position`: number of bytes in the remaining window |
| `hasRemaining()` | Whether there is at least one byte in the window |
| `flip()` | Sets limit to the old position, position to 0 to read the data just filled |
| `compact()` | Moves unconsumed bytes to the beginning, sets position to the number of retained bytes |
| `clear()` | Sets position to 0 and limit to capacity; **does not erase content** |

~~~text
0 <= position <= limit <= capacity
remaining() = limit() - position()
~~~

For an **asynchronous read**, the buffer is the **destination**: I/O writes into the `position..limit` range and advances position by the number of bytes received. For an **asynchronous write**, the buffer is the **source**: I/O reads bytes from the `position..limit` range and advances position by the number of bytes accepted by the channel.

For example, suppose the source initially contains `HELLO`, `position=0`, `limit=5`. If the write completes after transferring 2 bytes, then `position=2`, `remaining=3`. At this point, the application **is allowed** to send the remaining part in a new operation; before the previous operation completes, it **must not inspect or modify the cursor**.

## 3. Ownership by Phase

| Phase | Who may manipulate the buffer? | Valid decision |
|---|---|---|
| Newly created or acquired from pool | App | Fill data, set position/limit |
| Preparing write/read | App | `flip` write source, create writable destination |
| After `read(dst)`, Future not yet complete | Read operation | App does not access destination/backing array |
| After `write(src)`, Future not yet complete | Write operation | App does not access source/backing array |
| `Future.get()` returns successfully | App regains ownership | Check result, position, and remaining |
| Inside `CompletionHandler.completed(...)` | Callback is granted ownership | Parse, continue I/O, or transfer ownership via queue |
| `Future.get(timeout)` throws `TimeoutException` | I/O may still own it | Do not `clear`/reuse |
| Async operation reports timeout/cancel/error | Cleanup policy required | Do not assume buffer is in a success state |
| Buffer returned to pool | Pool or next consumer | Previous producer no longer uses it |

“Owner” here is an **application concurrency rule**, not a `ByteBuffer.lock()` feature. Java may allow the caller to invoke `clear` while I/O is pending, but the result is **race/undefined application behavior**. There is no valid way to infer “I/O must be done” merely by using `Thread.sleep(...)`.

## 4. Unsafe Actions While I/O Is Pending

### 4.1. Changing position or overwriting the write payload

~~~java
// WRONG snippet; channel is already connected.
ByteBuffer src = StandardCharsets.UTF_8.encode("HELLO");
Future<Integer> pendingWrite = channel.write(src);
src.clear();                                  // WRONG
src.put("WORLD".getBytes(StandardCharsets.UTF_8)); // WRONG
~~~

Meanwhile, I/O may still be reading bytes and updating `position`. If the application modifies `limit`, `position`, or byte data, the peer server may receive a mixed payload or corrupted content. Race behavior depends on timing/implementation, so you cannot write a test expecting the exact same failure to reproduce every time.

### 4.2. Reading/parsing the destination before the read completes

~~~java
// WRONG snippet.
ByteBuffer dst = ByteBuffer.allocate(1024);
Future<Integer> pendingRead = channel.read(dst);
dst.flip();                          // WRONG
String text = StandardCharsets.UTF_8.decode(dst).toString(); // WRONG
~~~

Data may not have arrived yet, may have arrived only partially, or may be updated by I/O after the code above has parsed it. `read` returning a Future does not mean `dst` contains a complete message.

### 4.3. Operating through an alias is still dangerous

~~~java
byte[] bytes = new byte[256];
ByteBuffer view = ByteBuffer.wrap(bytes);
Future<Integer> pendingRead = channel.read(view);

bytes[0] = 42;                        // WRONG: mutating the backing array.
ByteBuffer duplicate = view.duplicate();
duplicate.put(0, (byte) 99);          // WRONG: duplicate shares memory.
~~~

`duplicate()`, `slice()`, and `asReadOnlyBuffer()` create views with separate position/limit **but share the byte region**. A read-only view does not turn the backing array into an immutable snapshot. With direct buffers, you must manage ownership of the underlying memory region in the same way.

**Buffer ownership must cover every alias** that can access the relevant data or cursor. If the producer needs to keep modifying the original array, copy the payload into a **separate buffer** before submitting I/O.

## 5. Safe Usage with Future

`AsynchronousSocketChannel.read(ByteBuffer)` and `write(ByteBuffer)` return `Future<Integer>`:

~~~java
// Snippet: src already has payload and channel is connected.
Future<Integer> pending = channel.write(src);
// Never use src until get() succeeds.
int n = pending.get();
if (n < 0) {
    throw new IOException("Unexpected write result");
}
if (src.hasRemaining()) {
    // Initiate the next write for the remaining bytes.
}
~~~

When `get()` **returns successfully**, the operation has completed and the application is allowed to process the ByteBuffer according to the actual number of bytes transferred. `Future` also provides a memory-consistency guarantee: actions of the asynchronous computation happen-before actions following the retrieval of the result via `Future.get()`.

For **read**:

~~~java
// Snippet: protocol specifies exactly 100 bytes.
ByteBuffer dst = ByteBuffer.allocate(100);
while (dst.hasRemaining()) {
    Future<Integer> pending = channel.read(dst);
    int count = pending.get();   // Only access dst after a successful get().
    if (count == -1) {
        throw new EOFException("Incomplete frame");
    }
}
dst.flip();                     // Received all 100 bytes, safe to parse.
~~~

The snippet above is not a standalone server; channel setup, imports, and timeout handling need to be added. The loop works because **each read is awaited to completion before submitting the next read**. If the protocol does not know the length upfront, separate framing is required (length header, delimiter, or EOF-delimited according to rules).

Do not equate **“one read operation completed”** with **“the entire request is available”**: a read may return 1, 37, or 100 bytes depending on TCP state and buffer bounds.

## 6. Future.get(timeout) Only Limits the Wait Time on the Future

~~~java
// WRONG snippet:
Future<Integer> pending = channel.read(dst);
try {
    pending.get(1, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    dst.clear();                 // WRONG, I/O may still be running.
    bufferPool.offer(dst);      // WRONG, the pool may hand out the memory again.
}
~~~

A `TimeoutException` from `Future.get(timeout, unit)` means **the caller waited past the deadline for the result**; it **does not stop the operation** and does not prove that I/O has finished. The buffer still belongs to the operation if it remains pending.

The application must design a policy: continue tracking completion, or close the channel in a controlled manner; do not recycle the buffer simply because the wait timed out. `Future.get()` may also throw `InterruptedException`, `ExecutionException`, or `CancellationException`: classify them properly, and do not assume data definitely was not transmitted.

| Situation | What is known | What must not be assumed |
|---|---|---|
| `future.get()` returns `n` successfully | This operation has completed | The full message has been sent/received |
| `future.get(2, SECONDS)` returns `n` | Operation completed before the wait deadline | The peer has processed the payload |
| `future.get(2, SECONDS)` throws `TimeoutException` | Waiting timed out | I/O has stopped or the buffer can be reused |
| `future.isDone() == true` | Future is in a finished/cancelled state | Guaranteed success and buffer matches prior state |
| `future.cancel(...)` succeeds | Cancellation request was recorded | Bytes definitely did not cross the channel or buffer was restored |

## 7. Timeout of the Asynchronous Read/Write Operation Itself

`AsynchronousSocketChannel` has overloads that accept a timeout **for the operation**:

~~~java
// Snippet: Context/context is declared by the application.
channel.read(dst, 2, TimeUnit.SECONDS, context,
        new CompletionHandler<Integer, Context>() {
    @Override
    public void completed(Integer count, Context state) {
        // Operation completed successfully, check byte count.
    }

    @Override
    public void failed(Throwable error, Context state) {
        // If InterruptedByTimeoutException: exercise extra caution.
    }
});
~~~

According to the Java 17 documentation:

- If a read/write exceeds the operation's own timeout, it completes with failure with `InterruptedByTimeoutException`.
- The channel or underlying connection may be placed into an **implementation-specific error state** when the implementation cannot guarantee which bytes were or were not transferred.
- **The state of the ByteBuffer (or sequence of ByteBuffers) may be undefined after an I/O timeout.** The Javadoc recommends discarding the buffer or exercising strict caution, not accessing it while the channel remains open.

This is a major difference from `TimeoutException` on `Future.get(timeout)`: one only expires the **wait time for the result**, whereas the other is **the operation itself timing out and leaving the buffer state potentially undefined**.

In a service without a specially designed recovery protocol, the prudent approach is to **close the connection, not abnormally recycle the buffer, and create a new buffer/connection**. Do not read `dst.position()` after a timeout to deduce the exact number of bytes transferred.

## 8. Future.cancel Is Not a Rollback

Cancelling a `Future` does not provide an ACK that bytes were definitely not sent/received; it does not automatically undo transport effects or restore the cursor. Therefore it is wrong to do:

~~~java
// WRONG snippet:
Future<Integer> operation = channel.write(src);
operation.cancel(true);
src.clear();
pool.offer(src);                  // Risk of use-after-release.
~~~

After cancelling, you must handle the lifecycle of the channel and operation according to the contract. With abnormally terminated I/O, part of the data may already have been transmitted; business-level retries can cause duplicates if the application does not use request IDs and idempotency. Do not treat `isCancelled` or `isDone` as confirmation that “the buffer is clean and no operation is touching it” in all situations.

## 9. CompletionHandler: The Callback Owns the Buffer After Success

Overload using a handler:

~~~java
// Snippet: ch is already connected.
ByteBuffer inbound = ByteBuffer.allocate(4096);
ch.read(inbound, inbound,
        new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer count, ByteBuffer buffer) {
        if (count == -1) {
            // EOF; check for incomplete frame, cleanup.
            return;
        }
        buffer.flip();
        // Parse the bytes actually received and keep any partial frame.
        buffer.compact();
        // May submit the next read when state is valid.
    }

    @Override
    public void failed(Throwable error, ByteBuffer buffer) {
        // Classify the error; do not clear/release arbitrarily.
    }
});
~~~

This is **not a standalone program**. The attachment passed to `read` is the object returned in the callback parameter. Using an attachment lets the operation carry its own parser/buffer/session state without needing mutable global variables.

`completed(count, attachment)` means the operation has reported **successful** termination; the callback may process the ByteBuffer afterward if no other consumer is competing for it. `failed(error, attachment)` must have its own cleanup path, especially for operation timeouts.

The callback may be invoked very quickly and may run on a thread belonging to the channel group. **Prepare state before submitting**; do not assume the callback always starts after the caller's submit line has returned. If the callback hands the buffer off to another worker thread, it must use a queue/latch/executor and transfer the lease; you must not let the worker read data while simultaneously calling `clear` and reading again into the same buffer.

## 10. Java 17+ Runnable: Proving the Ownership Rules

This program runs over loopback in a single JVM, requires no Internet, and uses no fixed port. Both server and client use `AsynchronousSocketChannel`. It demonstrates:

1. Starting a pending read and then submitting a second read request, receiving `ReadPendingException` because a read is still outstanding.
2. The client sends the string `HELLO` via sequential Future writes; the server reads all five bytes via one or more Future reads. Buffers are only accessed after a successful `get`.
3. The server initiates a read using a `CompletionHandler` on a **new buffer**; the client sends the character `!`. The callback processes it and notifies main via a `CountDownLatch`.

File **`AsyncBufferOwnershipDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.channels.ReadPendingException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncBufferOwnershipDemo {
    private static final int WAIT_SECONDS = 5;

    private static void sendAll(
            AsynchronousSocketChannel channel, ByteBuffer data)
            throws Exception {
        while (data.hasRemaining()) {
            Future<Integer> pendingWrite = channel.write(data);
            // 'data' belongs to the outstanding operation until get() succeeds.
            int count = pendingWrite.get(WAIT_SECONDS, TimeUnit.SECONDS);
            if (count < 0) {
                throw new EOFException("Write ended unexpectedly");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(loopback, 0));
            Future<AsynchronousSocketChannel> pendingAccept = server.accept();

            try (AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open()) {
                client.connect(server.getLocalAddress())
                        .get(WAIT_SECONDS, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel peer = pendingAccept
                        .get(WAIT_SECONDS, TimeUnit.SECONDS)) {
                    ByteBuffer inbound = ByteBuffer.allocate(5);
                    Future<Integer> pendingRead = peer.read(inbound);
                    System.out.println("readSubmitted=true");

                    try {
                        peer.read(ByteBuffer.allocate(1));
                        System.out.println("unexpectedSecondRead");
                    } catch (ReadPendingException expected) {
                        System.out.println("secondReadRejected=true");
                    }

                    ByteBuffer outbound =
                            StandardCharsets.US_ASCII.encode("HELLO");
                    sendAll(client, outbound);
                    System.out.println("writeRemaining=" +
                            outbound.remaining());

                    int firstCount = pendingRead.get(
                            WAIT_SECONDS, TimeUnit.SECONDS);
                    if (firstCount < 0) {
                        throw new EOFException("Unexpected EOF");
                    }
                    while (inbound.hasRemaining()) {
                        int count = peer.read(inbound)
                                .get(WAIT_SECONDS, TimeUnit.SECONDS);
                        if (count < 0) {
                            throw new EOFException("Truncated message");
                        }
                    }
                    inbound.flip();
                    System.out.println("received=" +
                            StandardCharsets.US_ASCII.decode(inbound));

                    CountDownLatch completed = new CountDownLatch(1);
                    AtomicReference<String> outcome = new AtomicReference<>();
                    AtomicReference<Throwable> error = new AtomicReference<>();
                    ByteBuffer callbackBuffer = ByteBuffer.allocate(1);

                    peer.read(callbackBuffer, null,
                            new CompletionHandler<Integer, Void>() {
                        @Override
                        public void completed(Integer count, Void ignored) {
                            try {
                                if (count != 1) {
                                    throw new IOException(
                                            "Expected one byte, got " + count);
                                }
                                callbackBuffer.flip();
                                outcome.set(Character.toString(
                                        (char) (callbackBuffer.get() & 0xff)));
                            } catch (Throwable failure) {
                                error.set(failure);
                            } finally {
                                completed.countDown();
                            }
                        }

                        @Override
                        public void failed(Throwable failure, Void ignored) {
                            error.set(failure);
                            completed.countDown();
                        }
                    });

                    sendAll(client,
                            StandardCharsets.US_ASCII.encode("!"));
                    if (!completed.await(WAIT_SECONDS, TimeUnit.SECONDS)) {
                        throw new IOException("Completion handler deadline");
                    }
                    if (error.get() != null) {
                        throw new IOException("Callback failure", error.get());
                    }
                    System.out.println("callback=" + outcome.get());
                }
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 AsyncBufferOwnershipDemo.java
java AsyncBufferOwnershipDemo
~~~

**Stdout verified on OpenJDK 24 with `--release 17` compilation:**

~~~text
readSubmitted=true
secondReadRejected=true
writeRemaining=0
received=HELLO
callback=!
~~~

Meaning:

- `readSubmitted=true`: only indicates the read was initiated, **not** that data has finished arriving.
- `secondReadRejected=true`: the second read is rejected while the previous read is pending; there is no need/right to touch the old buffer to verify.
- `writeRemaining=0`: the client **waited for every Future write to complete** and transferred all bytes per the API; it does not mean the peer has processed the business logic.
- `received=HELLO`: the server waited for successful completion of each read to collect all five bytes before calling `flip`.
- `callback=!`: the handler processed the buffer after successful completion; `CountDownLatch` ensures main only reads the result after the callback.

The demo does not print the byte count of each individual read, because TCP may split data into multiple segments at different times. It has wait timeouts so it does not hang forever; on timeout, the demo exits/closes the channel, **never reusing a buffer while I/O might be outstanding**.

## 11. Concurrent Read/Write: Safe Channel Does Not Guarantee Safe Buffer

`AsynchronousSocketChannel` is safe for concurrent use by multiple threads, but specifies **at most one outstanding read and one outstanding write on the same channel**.

| Situation | Assessment |
|---|---|
| One pending read into `input` and one pending write from an independent `output` | Valid per full-duplex channel |
| Two pending reads on the same channel | `ReadPendingException` |
| Two pending writes on the same channel | `WritePendingException` |
| A read and a write using the **same ByteBuffer** | Unsafe |
| Reading into a buffer, writing from `buffer.duplicate()` sharing memory | Unsafe if data regions contend |
| Two channels concurrently writing into the same destination buffer | Unsafe |
| Write source is a read-only view, but producer mutates the backing array | Unsafe |

Therefore, you should have an independent **inbound buffer** and **outbound queue/buffer**. With multiple outbound messages, submit only one write; upon completion, continue the remaining part before moving to the next message. Do not bring Selector's `OP_WRITE` readiness into this logic as if it were `AsynchronousSocketChannel` completion.

## 12. Partial Read/Write and Scatter/Gather

An async read or write may transfer **fewer bytes than `remaining()`** at the start of the operation; valid byte state must be checked **after completion**. `read` returns `-1` on EOF. If `remaining() == 0` when I/O is initiated, the operation may complete immediately with a result of `0`.

With a length-prefixed protocol, a read callback may report only part of a header/body. The parser must preserve state across multiple operations, and not `clear` the buffer while an incomplete frame remains. For writes, continue sending the remaining source in a new operation; a callback returning a positive number does not automatically mean the entire response has been sent.

`AsynchronousSocketChannel` also has **scattering read/gathering write** overloads using `ByteBuffer[]`. All buffers in the submitted array belong to **the same operation lease** until completion; you must not modify the header or body individually while the operation has not finished.

~~~java
// Interface snippet: header/body/state are objects prepared by the app.
ByteBuffer[] parts = {header, body};
channel.write(parts, 0, parts.length,
        0, TimeUnit.MILLISECONDS, state,
        new CompletionHandler<Long, State>() {
    @Override
    public void completed(Long count, State context) {
        // Handle remaining of each buffer after successful completion.
    }

    @Override
    public void failed(Throwable error, State context) {
        // Error cleanup per policy.
    }
});
~~~

This snippet is **not a standalone program**: `State`/`state` must be defined. If using a buffer pool, both `header` and `body` must be retained for the operation; do not return one of them to the pool just because one buffer has run out of bytes before the callback runs.

## 13. Buffer Pool: No Use-After-Release

Pooling saves allocations, but it is very easy to reuse a buffer too early:

~~~text
FREE_IN_POOL
   → LEASED_TO_CONNECTION
   → PREPARED
   → IO_PENDING
   → COMPLETED_SUCCESS
   → PARSE / SEND_REMAINDER / CONSUMER
   → NO_MORE_IO_OR_CONSUMER
   → FREE_IN_POOL

FAILED / TIMEOUT / CANCELLED → cleanup, discard/quarantine as needed.
~~~

A good workflow:

1. **Acquire** a buffer for the right connection/message, tracking who owns it.
2. **Prepare** content and cursors, checking max payload.
3. **Submit**, mark as in-flight, and transfer ownership to the operation.
4. **Complete**, check count/remaining; continue I/O if needed.
5. **Release** to the pool **only** when no I/O is pending and other consumers have finished.
6. On timeout/error, route to a cleanup path; do not `clear` just to “free it quickly”.
7. Prevent double-release using a state machine or lease token, and set a cap on total buffer memory.

`ByteBuffer.allocateDirect()` is not exempt from ownership rules; direct memory can also be overwritten while native I/O is using it. `slice`/`duplicate` do not create an independent buffer that a pool can hand out to another request.

## 14. Synchronizing Results Between Callback and Other Threads

There are three separate concerns: channel thread-safety, buffer ownership, and **result publication**.

- A successful `Future.get()` establishes a happens-before relationship from the asynchronous computation to the thread receiving the result.
- `CountDownLatch.countDown()` and a successful `await()` provide a synchronization point for main to observe callback results.
- `BlockingQueue` or a concurrent collection can be used to hand complete messages to a worker with proper memory visibility.

If a callback wants to pass a buffer to a worker for parsing without copying data, it must **transfer an exclusive lease**; the callback must wait for the worker to release before clearing/submitting the next read using the same memory. If you want the callback to continue reading immediately, you typically **copy the message bytes** into an independent object for the worker, and only then does the callback reuse the input buffer that has finished being processed.

Do not use a busy loop `while (buffer.position() < N)` or `Thread.sleep` to decide whether a buffer is safe: there is no memory synchronization contract and it is prone to timing bugs.

## 15. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Outgoing messages have mixed content | Overwriting source while async write is pending | Do not mutate until completion, use an outbound queue |
| Parser sees stale/empty data | Calling `flip` on destination before async read completion | Wait for Future/handler and check count |
| `ReadPendingException` | Submitting a read while the previous read is still outstanding | Start a new read only after completion |
| `WritePendingException` | Two overlapping writes | One outstanding write at a time, send remainder sequentially |
| `TimeoutException` from `get` followed by returning buffer to pool | Confusing wait timeout with I/O timeout | Keep the lease or close the channel per policy |
| `InterruptedByTimeoutException` | Async operation timeout | Buffer state may be undefined, discard/cleanup |
| `BufferUnderflowException` | Parser reads more bytes than received | Framing, check `remaining` after completion |
| `BufferOverflowException` | Buffer too small or wrong limit | Controlled frame sizing/bounds |
| Duplicate view “changes data on its own” | Aliases sharing the backing array | Copy or manage all aliases |
| Memory leak / pool depletion | Error callback fails to return resources | Dedicated cleanup path, track in-flight leases |
| Duplicate transactions after retry | Timeout assumed to mean definitely not sent | Message ID, idempotency at the business layer |

## 16. Code Review Checklist

Before `read/write`: does the buffer have the right owner, size/position/limit, and backing storage? Is any other writer/reader touching the memory? Is there an outstanding operation in the same direction on the same channel? Do the callback or Future preserve context, error policy, and deadline?

After successful completion: check count (including `-1` for read), whether remaining bytes exist, and whether the frame is complete. If bytes remain, continue with a new operation after completion; release only when no other consumer or operation references it.

On failure: distinguish `TimeoutException` from Future wait, `InterruptedByTimeoutException` from the actual operation, network failures, and cancellation. Do not guess how many bytes were or were not transferred, and do not reuse memory just because a timer expired.

## 17. Self-Check

**1. Once `write(src)` returns a Future, can `src.clear()` be called?** No. A Future does not mean completion.

**2. `Future.get()` returns 3, and the initial source had 10 bytes. Were all 10 bytes sent?** No. Only three bytes were reported in this operation; the remaining bytes must still be sent.

**3. `Future.get(1, SECONDS)` throws a timeout. Can the buffer be recycled?** No; I/O may still be pending.

**4. A timeout of the async operation itself occurs. Can `dst.position` be trusted as the number of bytes received?** No. Per the Javadoc, the buffer state after a timeout may be undefined.

**5. Can two reads run concurrently on the same AsynchronousSocketChannel?** No; `ReadPendingException`.

**6. Can one read and one write run concurrently on the same channel?** Yes, using independent buffers.

**7. Does `ByteBuffer.duplicate()` copy the backing array?** No.

**8. Can the `completed` handler call `flip(dst)` immediately?** Yes, when the operation has reported success and the buffer belongs to the handler, with no competing consumer.

**9. Async read returns 24 bytes, and the protocol requires 100 bytes. Is the message complete?** No; continue reading after completion and preserve parser state.

**10. Does a read-only view automatically guarantee an immutable payload?** No; aliases/backing array can still be mutated.

**11. The callback hands the buffer to a worker for processing; can the callback call `clear` and read again into that buffer?** No, unless the worker has released it or an independent copy is used.

## 18. Official Documentation

- [Java SE 17 – AsynchronousByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html): ByteBuffer ownership and completion.
- [Java SE 17 – AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): concurrent read/write, timeouts, and buffer state.
- [Java SE 17 – AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): asynchronous accept.
- [Java SE 17 – CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): success/failure callbacks.
- [Java SE 17 – Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, cancel, happens-before.
- [Java SE 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): countDown/await synchronization.
- [Java SE 17 – ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): remaining, flip, slice, and duplicate.

**Conclusion:** While asynchronous I/O is pending, the ByteBuffer is **exclusively borrowed by the operation**. Only process it again after successful completion, while still accounting for partial reads/writes. A `Future.get` timeout does not stop I/O, while a timeout of the async read/write itself may leave the ByteBuffer state undefined. Do not reuse the buffer, backing array, or views sharing memory before ownership returns to the application.
