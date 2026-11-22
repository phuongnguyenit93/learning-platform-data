# Do Not Modify or Reuse a Buffer While an Operation Is Unfinished in Asynchronous Java NIO

## 1. The Most Important Rule

With synchronous I/O, a call like `channel.write(buffer)` usually returns after **that write pass** finishes, so the program can inspect the byte count written and continue adjusting the buffer. With asynchronous I/O, APIs such as `AsynchronousFileChannel.write(...)` or `AsynchronousSocketChannel.read(...)` **initiate** an operation and return a `Future` or accept a `CompletionHandler`. Use of the buffer may continue **after the initiating call has returned**.

Therefore, an ownership rule is required:

> **From the start of an asynchronous read/write operation until that exact operation completes, the passed-in buffer must be dedicated solely to that operation: do not read, modify, change its position/limit, or reuse it, and do not let another asynchronous I/O operation access the same backing memory.**

This rule applies to all of the following:

- **Writing (`write`):** source bytes must remain stable; a thread must not `put`, `clear`, `flip`, or alter `position/limit` on the source buffer while the write operation is still pending.
- **Reading (`read`):** the destination region is being updated by the system; do not read data before completion, do not write into the same region, and do not `flip` or reuse the destination buffer while the read operation is still pending.
- **Heap vs. direct buffers:** choosing `ByteBuffer.allocate` vs. `allocateDirect` does not alter the concurrency rule.
- **Buffer views:** `duplicate()`, `slice()`, and `asReadOnlyBuffer()` can still share **the same backing storage**; independent cursors **do not** make the underlying byte region independent.

This is not merely a "clean code" guideline. The Java SE documentation explicitly states that `ByteBuffer` is not safe for concurrent access while asynchronous I/O is in progress. Violating this can send corrupted payloads, receive overwritten data, miscalculate byte counts, trigger exceptions, or introduce bugs that are very difficult to reproduce.

## 2. A Buffer Handed Off by the Application to an I/O Operation

A `ByteBuffer` has two components to keep in mind:

1. **Control state:** `position`, `limit`, `capacity`, `mark`, and related attributes.
2. **Data region:** bytes on the heap or off-heap viewed by the buffer; may be shared across multiple views.

Example:

```java
ByteBuffer source = ByteBuffer.wrap(new byte[]{10, 20, 30, 40});
source.position(1);
source.limit(3); // remaining = 2 bytes: 20 and 30
```

This is an illustrative snippet with `import java.nio.ByteBuffer;`.

Suppose `write(source)` is initiated at this point. The I/O operation reads bytes from `[position, limit)` per the channel's contract; upon completion, `position` is updated according to the bytes transferred. If another thread manually alters `source.position(0)`, `source.limit(4)`, or `source.put(1,(byte)99)` before the operation ends, the program breaks assumptions about **the source data and remaining range** used by the I/O operation. There is no guarantee that the channel copied all bytes at the exact moment of the call.

### 2.1. "The Call Returned" Differs from "The Operation Completed"

```text
Application thread                      I/O system / completion thread
----------------                        ----------------------------
create ByteBuffer B
initiate async write(B)  ────────────►  operation is pending
receive Future F
  │                                          │
  ├── DO NOT modify or reuse B               ├── read bytes of B
  │                                          └── signal completion
  ▼
F.get() completes successfully ◄──────  result: number of bytes written
  │
  └── safe to check remaining, continue writing, or reuse B
```

While pending, even reading `buffer.position()` to "watch progress" from another thread is not a safe mechanism: byte buffers are not designed as concurrent progress trackers. `Future.isDone()` can help check Future status, though canceled/failed cases must be accounted for; **a successful `Future.get()` on that operation** or the `completed` callback is the standard boundary for handing buffer ownership back.

### 2.2. `read` and `write` Results Can Be Partial

With `AsynchronousFileChannel` and `AsynchronousSocketChannel`:

- Reading into `ByteBuffer dst` may read only **part** of `dst.remaining()`. A positive `result` reports the actual byte count; `-1` indicates EOF under contract conditions.
- Writing from `ByteBuffer src` may write only **part** of `src.remaining()`; the result returns the actual byte count.
- When `n > 0`, the buffer's position is updated to reflect the `n` bytes processed; limit typically remains unchanged per the API specification.
- If a full message must be completed, the caller must design a **chain of subsequent operations**, starting the next operation with the same buffer **only after the previous operation has completed**.

Diagram:

```text
Outbound buffer:     [A B C D E F]
                     ^           ^
                  position      limit

async write #1 ── completes 2 bytes ──► remaining = [C D E F]
async write #2 ── completes 4 bytes ──► remaining = []
                                                     ↑
                                               safe to reuse
```

Do not set `position` manually based on an operation still pending, or assume "calling `write` once will write everything."

## 3. Related Asynchronous APIs

### 3.1. `AsynchronousFileChannel`

`AsynchronousFileChannel` operates on files using explicit offsets:

```java
Future<Integer> writeFuture = file.write(src, fileOffset);
Future<Integer> readFuture  = file.read(dst, fileOffset);
```

These are two **independent illustrative calls**; `file` must be an `AsynchronousFileChannel` opened with appropriate options and `src`/`dst` must be suitable ByteBuffers. This class **has no shared file position**: each `read/write` passes its own `long fileOffset`. That does not make `ByteBuffer.position()` meaningless; the file offset and the position within the buffer are **two distinct coordinates**.

Callback overloads:

```java
file.write(src, fileOffset, attachment, handler);
file.read(dst, fileOffset, attachment, handler);
```

These two lines illustrate signatures (not a standalone compilable program): `attachment` is an application-provided object, and `handler` is an appropriate `CompletionHandler<Integer,A>`. Java documentation allows multiple outstanding reads/writes on the same `AsynchronousFileChannel`, **but the same ByteBuffer must not be used for multiple concurrent I/O operations**. Furthermore, completion order of operations and callbacks is not guaranteed to follow initiation order. If operations overwrite overlapping file regions, a dedicated protocol is required.

### 3.2. `AsynchronousSocketChannel`

Asynchronous sockets provide:

```java
Future<Integer> fRead  = socket.read(dst);
Future<Integer> fWrite = socket.write(src);
```

Illustrative snippet where `socket` is a connected `AsynchronousSocketChannel`. With this socket, there can be **at most one outstanding read and one outstanding write at the same time**. Initiating a second read while the previous read has not completed may throw `ReadPendingException`; similarly `WritePendingException` for a second write.

One read and one write may proceed concurrently **when they use separate buffers and the application coordinates state properly**. Thread safety at the channel level **does not mean** the passed-in `ByteBuffer` is thread-safe.

### 3.3. `ByteBuffer` Has No Knowledge of Channel Lifecycles

`ByteBuffer` has no built-in `isInFlight()` or `awaitIo()` state. If you call `src.clear()` or `src.put(...)`, the `ByteBuffer` does not know a Future is currently using it and will not stop you. Hence managing **ownership** belongs to the application.

## 4. Incorrect Example: Modifying the Buffer Right After Starting Async Write

The following code intentionally illustrates **a bug**, not a program to run in production:

```java
ByteBuffer payload = ByteBuffer.wrap("FIRST".getBytes(StandardCharsets.US_ASCII));

Future<Integer> pending = channel.write(payload, 0L);

// WRONG: the previous operation may still be using payload.
payload.clear();
payload.put("LATER".getBytes(StandardCharsets.US_ASCII));
payload.flip();

int written = pending.get(); // Waiting here is already too late.
```

This illustrative snippet assumes `channel` is an `AsynchronousFileChannel` and `ByteBuffer`, `Future`, and `StandardCharsets` are imported. On a fast machine, the operation might finish before `clear()` runs so the bug **does not manifest** in that test run; yet the code is still wrong because there is no synchronization rule and I/O completion is not guaranteed when the buffer is modified.

What can be affected:

- The written content may not be `FIRST`.
- Position/limit of the same buffer are mutated by two sides.
- `pending.get()` returns the byte count written without providing a snapshot of the original bytes once the buffer was mutated.
- A test passing 10,000 times does not prove the code is safe across every OS, executor, and system load.

**Proper fix:** wait for `pending.get()` to succeed before calling `clear()/put()/flip()` for the next write.

### 4.1. Why Is `duplicate()` Also Not a Solution If Original Bytes Are Still Modified?

```java
byte[] data = "FIRST".getBytes(StandardCharsets.US_ASCII);
ByteBuffer original = ByteBuffer.wrap(data);
ByteBuffer view = original.duplicate();

Future<Integer> f = channel.write(view, 0L);

// WRONG: view and original share the same bytes.
original.put(0, (byte) 'L');
```

`duplicate()` has an independent position/limit, yet **shares backing storage**. Similarly:

- `slice()`: a window into shared data.
- `asReadOnlyBuffer()`: a read-only view **through that alias**, which does not prevent the original buffer or backing array from changing bytes.
- `ByteBuffer.wrap(data)`: holds a reference to the original array without copying.
- `buffer.array()`: if accessible, returns the backing array, not a copy.

If a producer needs to modify source data while a consumer writes asynchronously, create an **isolated data snapshot**:

```java
byte[] snapshot = originalBytes.clone();
ByteBuffer owned = ByteBuffer.wrap(snapshot);
Future<Integer> f = channel.write(owned, position);
// Keep owned and snapshot unmodified until f completes.
```

This snippet assumes `originalBytes` and `channel` are declared; cloning `byte[]` produces an independent byte copy, though the caller must still ensure no other alias mutates `snapshot`. For an arbitrary `ByteBuffer` (potentially direct or read-only), copy `remaining()` via `duplicate().get(...)` **before starting the operation**, while the source is stable and validly owned.

## 5. Runnable Java 17+ Example: `Future.get()` Before Reuse

The complete example below writes a byte sequence to a temporary file using `AsynchronousFileChannel`; each write awaits completion and inspects the actual byte count before continuing. Then it reads back, awaits each read operation's completion, and **only at the very end reuses the source buffer**.

**File:** `AsyncBufferOwnershipDemo.java`

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Future;

public class AsyncBufferOwnershipDemo {
    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempFile("async-buffer-", ".bin");

        try {
            try (AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            temp,
                            StandardOpenOption.READ,
                            StandardOpenOption.WRITE)) {

                ByteBuffer outgoing = ByteBuffer.wrap(
                        "ASYNC".getBytes(StandardCharsets.US_ASCII));

                long writePos = 0L;
                while (outgoing.hasRemaining()) {
                    Future<Integer> operation = channel.write(
                            outgoing, writePos);

                    // From here until get() succeeds: DO NOT access outgoing.
                    int count = operation.get();

                    if (count <= 0) {
                        throw new IOException("No write progress");
                    }
                    writePos += count; // Update only after completion.
                }

                System.out.println("written bytes: " + writePos);
                System.out.println("write remaining: "
                        + outgoing.remaining());

                ByteBuffer incoming = ByteBuffer.allocate(16);
                long readPos = 0L;

                while (readPos < writePos) {
                    Future<Integer> operation = channel.read(
                            incoming, readPos);

                    // Likewise: do not read/flip incoming while I/O is pending.
                    int count = operation.get();

                    if (count <= 0) {
                        throw new IOException(
                                "Unexpected EOF/no progress");
                    }
                    readPos += count;
                }

                incoming.flip(); // After the final read pass finishes.
                System.out.println("read bytes: " + readPos);
                System.out.println("content: "
                        + StandardCharsets.US_ASCII.decode(incoming));

                // Now that writing has completed, reusing outgoing is safe.
                outgoing.clear();
                outgoing.put(
                        "LATER".getBytes(StandardCharsets.US_ASCII));
                outgoing.flip();
                System.out.println("reused: "
                        + StandardCharsets.US_ASCII.decode(outgoing));
            }
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

Compile/run on JDK 17+:

```bash
javac AsyncBufferOwnershipDemo.java
java AsyncBufferOwnershipDemo
```

**Stdout (with normal temporary filesystem behavior):**

```text
written bytes: 5
write remaining: 0
read bytes: 5
content: ASYNC
reused: LATER
```

### 5.1. Precise Analysis

1. `Files.createTempFile` creates a dedicated file for the demo without needing a network or external processes.
2. `channel.write(outgoing, writePos)` returns `Future<Integer>`. Do **not** modify `outgoing` while waiting. `get()` returns the bytes written and guarantees the operation has completed successfully at this point.
3. If a write pass processes only part of the data, `outgoing.position()` has already advanced by the bytes written. The next iteration uses `writePos` incremented by that exact count, avoiding overwriting previously written bytes.
4. The read loop works similarly, using `incoming` as the destination and per-iteration file offsets. Only after the expected bytes are read and the last read finishes does it call `flip()` to decode.
5. Reusing `outgoing` via `clear()/put()/flip()` at the end is **valid** because all write Futures completed beforehand. Printing `LATER` only displays the new buffer content; the demo **does not write `LATER` to the file**.
6. `try-with-resources` closes the channel after all Futures have finished. `finally` cleans up the temporary file. If `get()` throws `InterruptedException` or `ExecutionException`, the example fails rather than continuing as if it succeeded; production apps need a cleanup/cancellation coordination protocol before reusing or returning buffers to a pool.

**Important note:** the loop calls `get()` immediately, so in this example the calling thread actually **waits** for completion. The API is still asynchronous; this sequential style teaches ownership rather than demonstrating peak throughput. In real programs, you can use handlers or pipeline multiple **independent buffers** to continue other business work while I/O is pending.

## 6. The Right Way with `CompletionHandler`: Handing Ownership to the Callback

With the callback API:

```java
channel.write(payload, 0L, context,
        new CompletionHandler<Integer, Context>() {
            @Override
            public void completed(Integer written, Context ctx) {
                // This operation has completed.
                // Check written, update offset and ownership.
            }

            @Override
            public void failed(Throwable error, Context ctx) {
                // Report error and clean up operation/context.
            }
        });
```

This is an **API illustration**, not a standalone compilable program: `Context`, `channel`, `payload`, and `context` must be declared, with `import java.nio.channels.CompletionHandler;`. The idea:

- **Before calling:** prepare valid bytes, set position/limit, maintain a policy holding references to the buffer.
- **Right after initiation:** buffer state belongs to the operation. The producer must not modify, `flip`, `clear`, or return it to a pool.
- **Inside `completed`:** inspect the successful byte count, optionally continue writing the remainder with a **new operation on the same buffer**, or hand ownership back to the producer once finished.
- **Inside `failed`:** report the error and resolve operation state. For special timeout/cancellation cases, consult the contract and do not recycle buffers recklessly.
- **At the application layer:** notify the caller that the buffer is free only when its usage has truly ended, not merely because `channel.write(...)` returned.

### 6.1. Compilable Helper Example: Chaining Writes for an Entire `ByteBuffer`

To handle partial writes without blocking the caller, the helper below uses a callback to keep writing `remaining`, completing a `CompletableFuture<Void>` only when all bytes are written (or an error is detected).

**File:** `AsyncWriteAll.java`

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.util.concurrent.CompletableFuture;

public final class AsyncWriteAll {
    private AsyncWriteAll() {}

    public static CompletableFuture<Void> writeAll(
            AsynchronousFileChannel channel,
            ByteBuffer owned,
            long startOffset) {

        CompletableFuture<Void> done = new CompletableFuture<>();

        if (startOffset < 0) {
            done.completeExceptionally(
                    new IllegalArgumentException("negative offset"));
            return done;
        }

        if (!owned.hasRemaining()) {
            done.complete(null);
            return done;
        }

        CompletionHandler<Integer, Long> handler =
                new CompletionHandler<>() {
            @Override
            public void completed(Integer count, Long pos) {
                if (count == null || count < 0) {
                    done.completeExceptionally(
                            new IOException("Invalid write result"));
                    return;
                }
                if (count == 0) {
                    // Avoid infinite immediate recursive retries when making no progress.
                    done.completeExceptionally(
                            new IOException("No write progress"));
                    return;
                }

                if (!owned.hasRemaining()) {
                    done.complete(null);
                    return;
                }

                try {
                    channel.write(owned, pos + count,
                                  pos + count, this);
                } catch (Throwable failure) {
                    done.completeExceptionally(failure);
                }
            }

            @Override
            public void failed(Throwable error, Long pos) {
                done.completeExceptionally(error);
            }
        };

        try {
            channel.write(owned, startOffset, startOffset, handler);
        } catch (Throwable failure) {
            done.completeExceptionally(failure);
        }

        return done;
    }
}
```

This is a **compilable helper class** via `javac AsyncWriteAll.java`, with no `main` and no stdout. To use it:

```java
ByteBuffer owned = ByteBuffer.wrap(payload.clone());
CompletableFuture<Void> finished =
        AsyncWriteAll.writeAll(channel, owned, 0L);

// Do not touch owned while finished has not completed.
finished.join(); // Only illustrates waiting at the caller.
owned.clear();   // After successful completion: safe to reuse.
```

The caller snippet is an example, requiring `payload` to be a populated `byte[]`, `channel` to be a valid `AsynchronousFileChannel`, imports, and failure-state handling. The helper **assumes a single owner** for `owned`: no one else accesses its bytes or cursor while `writeAll` is using it.

**Practical caution:** this helper demonstrates callback chaining, not a full retry engine. It errors out if write reports 0 to avoid infinite retry loops; production code needs timeouts, backoff/monitoring, and proper error policies. If a caller invokes `finished.cancel(...)`, canceling the outer `CompletableFuture` **does not automatically cancel already-initiated writes**; do not use the canceled state to conclude the buffer memory is free. For errors occurring while scheduling the next operation or closing the channel mid-flight, design buffer handback around actual I/O state rather than just the application's Future flag.

### 6.2. Which Thread Runs the Callback?

For `AsynchronousFileChannel`, completion handlers are executed by threads in the thread pool associated with the channel; under certain conditions when an operation completes immediately and the caller belongs to the pool, the handler may run directly on that thread. Do not rely on a callback always running on the UI thread, main thread, or a single dedicated thread.

If a callback must update a UI, application queue, or shared state, hand off to an appropriate executor/loop and ensure synchronization. A common bug is a callback completing I/O properly and then mutating non-thread-safe application objects.

## 7. Buffer Pools: Never Return a Buffer Too Early

Buffer pools help reuse allocated memory regions, especially direct buffers. However, **returning a buffer to the pool while an operation is still pending** allows another task to lease it and overwrite the byte region currently used by I/O.

**Incorrect example:**

```java
ByteBuffer leased = pool.acquire();
prepare(leased);
channel.write(leased, fileOffset); // returns an incomplete Future
pool.release(leased);              // WRONG: released too early
```

This is illustrative pseudo-code with application-defined `pool`/`prepare`; not a standalone Java class. If the buffer is handed to another task, both position and bytes can be mutated while the write is still pending.

**Correct flow:**

```text
FREE (in pool)
  └── acquire ──► OWNED_BY_PRODUCER
                      │ prepare
                      └── submit I/O ──► IN_FLIGHT
                                            │
                                            ├── completion + result handling
                                            ▼
                                    OWNED_BY_CONSUMER
                                            │ only when no pending references remain
                                            └── release ──► FREE
```

Principles:

- A physical buffer has **one exclusive owner** for the duration an operation uses it.
- Return the buffer to the pool at the **actual completion point** (and when no other operation shares the storage), not in a `finally` block right after initiating async I/O.
- If a logical record requires multiple writes due to partial results, the buffer still belongs to **that same logical operation chain** until the chain truly finishes.
- If a pool hands out `slice()/duplicate()` views of the same backing storage, they do **not** become independent buffers for concurrent assignment. Avoid memory overlap and enforce ownership at the backing-storage level.
- Failures, timeouts, and cancellations need dedicated return paths; do not treat "operation threw an exception" as proof that all I/O agents have stopped touching the buffer.

### 7.1. When Should You Copy the Payload?

Suppose a producer uses a `byte[]` that may be mutated continuously, while I/O must write a snapshot of the current version. Copy at the handoff boundary:

```java
byte[] snapshot = producerBytes.clone();
ByteBuffer pendingWrite = ByteBuffer.wrap(snapshot);

Future<Integer> f = asyncFile.write(pendingWrite, 0L);

// Producer keeps modifying producerBytes; pendingWrite retains its own snapshot.
```

This illustrative snippet requires the producer **not to modify the source while cloning runs** if a consistent snapshot is needed; cloning and handoff still require proper coordination. The snapshot is a separate `byte[]`, yet no other task may modify `snapshot` while I/O uses it. Copying has a cost and is not always necessary; if the producer can transfer ownership of the original buffer, copying can be avoided.

## 8. Do Not Use `slice`/`duplicate`/`asReadOnlyBuffer` to Bypass Pending Constraints

Comparing buffer creation methods:

| Creation Method | Independent Cursor? | Shared Bytes? | Solves In-Flight Ownership Automatically? |
|---|---|---|---|
| Two separate `ByteBuffer.allocate(n)` calls | Yes | No | Allows assigning two separate regions to two operations |
| `ByteBuffer.wrap(byte[])` | View's own cursor | Yes, with original array | No |
| `buffer.duplicate()` | Yes | Yes, with original buffer | No |
| `buffer.slice()` | Yes | Yes, with original buffer (relevant subrange) | No |
| `buffer.asReadOnlyBuffer()` | Yes | Yes, with other writable aliases | No |
| Two separate `ByteBuffer.allocateDirect(n)` calls | Yes | No, between two independent allocations | Does not manage per-operation lifecycles automatically |
| Copy bytes into a new `byte[]`/separate `ByteBuffer` | Yes | No, with source (if copied properly) | Useful, yet must still keep copy unmodified while pending |

Example:

```java
ByteBuffer original =
        ByteBuffer.wrap("HELLO".getBytes(StandardCharsets.US_ASCII));
ByteBuffer view = original.asReadOnlyBuffer();

Future<Integer> f = channel.write(view, 0L);

// WRONG: the read-only view still shares bytes with original.
original.put(0, (byte) 'X');
```

Read-only only prevents `view.put(...)`; it does not prevent the owner from modifying bytes through `original`. For buffers with an accessible `array()`, anyone holding a reference to the array can also modify bytes despite the read-only wrapper; hence the underlying source must be controlled.

### 8.1. Do Not Convert a ByteBuffer to `byte[]` by Blindly Calling `array()`

`buffer.array()` only works when a backing array is accessible; direct buffers or read-only heap buffers may disallow it. Moreover, the array may be larger than the `remaining()` region to send, and it is shared storage itself.

If you need an exact independent copy of the remaining region before I/O:

```java
static ByteBuffer copiedRemaining(ByteBuffer source) {
    ByteBuffer reader = source.duplicate();
    byte[] snapshot = new byte[reader.remaining()];
    reader.get(snapshot);
    return ByteBuffer.wrap(snapshot);
}
```

The snippet above is a **helper method**, usable in a class importing `ByteBuffer`. It does not alter `source`'s cursor and works with both direct and read-only buffers; however, **the caller must ensure `source` is not concurrently modified during the copy itself**. The independent copy may be handed to the operation only once copying is complete.

## 9. Timeouts, Cancellation, and Failure: Dangerous Edge Cases

### 9.1. `Future.get(timeout, unit)` Timing Out Does Not Mean I/O Ended

```java
Future<Integer> f = channel.write(buf, 0L);
try {
    f.get(100, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    // Only means the waiting thread has no result within 100 ms.
    // Must NOT call buf.clear() or return buf to pool here.
}
```

Illustrative snippet where `channel` is an `AsynchronousFileChannel`, `buf` belongs exclusively to the operation, and `Future`, `TimeUnit`, and `TimeoutException` are imported. `TimeoutException` here belongs to **the Future wait call**, not meaning system I/O was canceled. The operation may still be reading/writing the buffer.

Reasonable steps: continue tracking the Future or execute a coordinated cancellation/channel-closing policy; release the memory region only when certain no activity still uses it. Do not use `f.isDone()==false` or elapsed time as a release trigger.

### 9.2. Does `Future.cancel(...)` Cancel I/O Immediately?

Do not assume so. `Future.cancel(...)` requests cancellation under the Future contract; whether an I/O operation already submitted to the OS can be canceled depends on the implementation and actual state. Even when a Future transitions to the canceled state, the application should be **conservative** about backing memory safety unless there is a specific guarantee that background I/O has stopped accessing the buffer.

Specifically for `AsynchronousSocketChannel`, Java documentation notes cases where timeouts can leave the channel or connection in an implementation-dependent error state; upon timeout, the state of the `ByteBuffer` may be **undefined**. The safe course in such cases is typically to close the channel per policy, retire the buffer from the pool so it is not reused immediately, and establish a new connection when needed.

**Do not** argue that "timed out/canceled" = "zero bytes were read/written" or "the buffer is untouched."

### 9.3. `ExecutionException`, `InterruptedException`, and Completion Status

- `future.get()` succeeds: the operation completed and returned a result; the application may process the buffer.
- `ExecutionException`: the operation ended in failure; inspect the cause—the byte count may have changed depending on the API and recovery policy. Do not always assume 0 bytes transferred.
- `InterruptedException` while a thread is in `get()`: **the wait was interrupted**; the I/O itself may continue. Do not resume mutating the buffer merely because the thread stopped waiting. Typically restore the interrupt flag per policy and preserve lifecycle management.
- `CancellationException`: the Future reports canceled status; do not infer it is safe to reuse the buffer if there is any risk background I/O has not fully terminated.
- Closing a channel while an operation is pending may terminate the operation with `AsynchronousCloseException` or a related contract error; ensure cleanup is coordinated.

A good API structure often returns an **operation handle** bundling both the Future/callback and buffer ownership, rather than releasing the buffer to a pool inside a catch branch.

## 10. "Using Different Buffers" Must Still Account for Shared Memory

Suppose there are two distinct view objects:

```java
byte[] bytes = new byte[1024];
ByteBuffer a = ByteBuffer.wrap(bytes);
ByteBuffer b = ByteBuffer.wrap(bytes);
```

The two objects `a` and `b` have separate positions yet view **the same `byte[]`**. Passing them to two concurrent async I/O operations can cause data races, especially one read and one write or two writes while a producer still modifies the array.

Similarly, slicing a `ByteBuffer` from a larger region can be valid for multiple operations **only when** the physical subregions are strictly non-overlapping and the code accurately manages bounds, owner, state, and lifecycle of each slice. Do not treat object identity `a != b` as proof that memory regions do not overlap.

### 10.1. Multiple Operations on the Same AsynchronousFileChannel

Java allows multiple file read/write operations to exist concurrently and does not define start/completion ordering. If you want parallel I/O:

- Allocate **independent** buffers per operation or partition non-overlapping regions with clear ownership.
- Assign **distinct** file offsets, avoiding overlapping writes to the same file region unless business rules allow it.
- Do not assume callback A fires before callback B simply because `write(A)` was called before `write(B)`.
- When assembling data, rely on file offsets and results, not completion order alone.
- If building a sequential stream/log, you may need a writer queue instead of firing a burst of async writes at the same offset hoping the system orders them automatically.

### 10.2. One Read and One Write Simultaneously on a Socket

`AsynchronousSocketChannel` supports at most one read and one write concurrently at the same time, yet **both buffers must have independent ownership**. Using a single buffer for both input and output simultaneously is a bug even though the socket allows two opposite-direction operations concurrently.

Use separate input/output state:

```text
ConnectionState:
   inboundBuffer  → pending read → completed → decode → prepare next read
   outboundBuffer → pending write → completed → update remaining → write next
```

If you want to echo newly read bytes back to the client, wait for the read to complete, `flip` the input region at the right time, and then **transfer ownership** of it to the write or copy it into an output buffer. Never initiate a new read on the same backing bytes while the echo write is still pending.

## 11. Comparing Buffer Lifecycles Between Read and Write

| Phase | Read Buffer (Destination) | Write Buffer (Source) |
|---|---|---|
| Preparation | `clear()` or set position/limit to the writable range | `flip()` after populating payload, or `wrap(bytes)` |
| Initiation | `read(dst, ...)` | `write(src, ...)` |
| Pending | **Do not read, modify, flip, clear, or reuse** | **Do not read, modify, flip, clear, or reuse** |
| Successful completion | Check byte count `n`, position has advanced; `flip()` when ready to consume | Check byte count `n`, position has advanced; if `hasRemaining()`, continue writing |
| End of logical operation | Consume data and release ownership once parser finishes | Return to pool or reuse once no bytes remain to write |
| Timeout/cancel/error | Handle per contract; do not assume buffer is untouched or background I/O stopped | Same; maintain policy preventing premature reuse |

**Incorrect read-side example:**

```java
ByteBuffer receive = ByteBuffer.allocate(4096);
Future<Integer> f = socket.read(receive);

receive.flip();  // WRONG: read may not have written bytes into receive yet.
parse(receive);  // WRONG: parsing incomplete data.
```

Non-standalone snippet with `socket` of type `AsynchronousSocketChannel` and an application method `parse`. Wrong behavior does not necessarily throw an exception; it may parse empty or stale data, and changing `limit` breaks the contract for the ongoing read result.

**Fix:**

```java
Future<Integer> f = socket.read(receive);
int n = f.get(); // Wait for successful completion.
if (n > 0) {
    receive.flip();
    parse(receive);
}
```

This snippet illustrates a synchronous caller waiting for the result; imports and checked-exception handling are needed. If `n = -1`, handle EOF/connection close instead of parsing new data. If `n = 0`, handle retry/event state instead of assuming a message arrived.

## 12. Asynchronous I/O Does Not Mean Every Piece of Code Must Be Multithreaded

`Future.get()` creates a controlled wait point; useful for teaching ownership rules, though it can block an event loop if used continuously. `CompletionHandler` allows the caller to do other work; however, callbacks must handle thread safety and resource lifecycles.

You can design a `PendingOperation` queue:

```text
Producer:
    create new payload/buffer
    enqueue request with ownership
    signal I/O worker

I/O worker / async API:
    take request
    initiate read/write
    retain reference and mark IN_FLIGHT

Completion callback:
    process result
    if bytes remain → initiate next operation, keeping buffer
    if finished → signal completion + transfer ownership / return to pool

Error/cancel:
    go through dedicated cleanup state machine, avoiding premature release
```

When transferring ownership across threads, use proper Java Memory Model tools: `BlockingQueue`, `CompletableFuture` with coordinated callbacks, or executors/locks. Using a plain boolean variable (without `volatile`/synchronization) for another thread to "see" a buffer is free can cause data races and missing memory visibility.

### 12.1. Backpressure to Prevent Unbounded Pending Buffers

If a producer generates data faster than the channel writes, the system can accumulate thousands of buffers and Futures:

- Cap outstanding operations and total pending bytes.
- Block, throttle, or reject the producer when quota is exceeded.
- Use a fixed pool, **issuing only buffers that have been safely released**.
- Distinguish "enqueued", "I/O pending", "completed", and "application-acknowledged".
- For TCP, write completion means bytes were accepted under channel semantics, **not** that the peer read and processed the entire message; application-level acknowledgment requires its own protocol.

## 13. Common Pitfalls

1. **Calling async `write` and immediately calling `clear()`.** I/O may still be using the old bytes and cursor.
2. **Calling async `read` and calling `flip()` before completion.** May change `limit` while the system is writing into the buffer.
3. **Modifying the original `byte[]` after `wrap(array)`** while the ByteBuffer is used by an async write. Wrap does not copy.
4. **Assuming `duplicate()` creates independent storage.** It only separates cursors while sharing backing bytes.
5. **Assuming `asReadOnlyBuffer()` freezes the payload.** Another writable alias can still modify the bytes.
6. **Using direct buffers to bypass concurrent access rules.** Both heap and direct buffers require ownership.
7. **Assuming that because a Java channel is thread-safe, `ByteBuffer` is also thread-safe.** Those are two separate contracts.
8. **Issuing two socket reads or two socket writes while the previous one is pending.** `ReadPendingException`/`WritePendingException`.
9. **Writing to a socket once and concluding the entire message was sent.** Partial writes can occur; remaining bytes must be kept.
10. **Reusing a file buffer across multiple outstanding writes.** `AsynchronousFileChannel` allows multiple operations, not safe concurrent use of one buffer.
11. **Relying on initiation order for callbacks.** File completion handlers may execute out of submission order.
12. **Returning a buffer to a pool in a `finally` block wrapping the initiating call.** `finally` executes as soon as the initiating method returns, without waiting for async completion.
13. **Treating an expired `get(timeout)` as proof the operation stopped.** It only reports the wait did not finish.
14. **Canceling a Future and immediately recycling the buffer.** Cancellation does not by default guarantee the backend stopped accessing memory.
15. **Treating `Future.isDone()` as if every terminal state were as safe as success.** Canceled/failed states require different policies.
16. **Swallowing `InterruptedException` and modifying the buffer.** The waiting thread being interrupted does not mean I/O completed.
17. **Closing a channel and immediately sending the buffer to another I/O operation without considering lifecycle/callbacks.** Outstanding operations must be cleaned up and status confirmed per contract.
18. **Failing to manage file offsets during partial file writes.** Easily writes duplicates, overwrites data, or creates holes.
19. **Using the same backing array concurrently with two different views.** Distinct object identity does not guarantee independent storage.
20. **Calling `read` with a read-only ByteBuffer.** Destination must be writable; otherwise `IllegalArgumentException` may be thrown.
21. **Assuming write completion means file data is durable across power loss.** I/O completion differs from `force(true)` and durability policies.
22. **Assuming TCP write completion means the peer received/ACKed.** That is transport semantics, not application acknowledgment.
23. **Not checking the completed byte count.** If the result differs from expected bytes, continue or record EOF/error.
24. **Not distinguishing an application queue from an in-flight operation.** A buffer may still be used by callbacks in a `writeAll` chain.
25. **Using a socket timeout and still guessing the buffer is untouched.** The timeout contract may leave the buffer/channel in an undefined state.

## 14. Self-Check

**Question 1.** `AsynchronousFileChannel.write(buffer,pos)` returned a `Future`. Can `buffer.clear()` be called immediately?  
**No.** The Future represents a pending operation; it is safe only after the operation completes and ownership is returned.

**Question 2.** Is `ByteBuffer duplicate = buffer.duplicate()` safe for a writer if a producer continues modifying the original bytes?  
**No.** `duplicate` has its own cursor, yet shares backing storage.

**Question 3.** Can one read and one write be started concurrently on `AsynchronousSocketChannel`?  
**Yes**, within the limit of one outstanding read and one outstanding write, provided independent buffers and proper connection coordination are used.

**Question 4.** `Future.get(100, MILLISECONDS)` throws `TimeoutException`. Can the buffer be returned to the pool immediately?  
**No.** The I/O operation may still be running; a wait timeout is not completion.

**Question 5.** `Future.get()` returns 2 for a buffer initially holding 5 bytes. Can the buffer be reused for another payload immediately?  
**Not yet** if the logical write must send all 5 bytes. After completion, 3 bytes remain in the buffer; continue with a new operation at the updated offset, wait for everything to finish, and only then reuse.

**Question 6.** Why isn't `channel.isOpen() == false` a signal to free all pooled buffers without checking?  
**Because** closing, cancellation, and callbacks/errors of outstanding operations have their own lifecycles. You must handle I/O/callback states and verify no concurrent access remains.

**Question 7.** Does `ByteBuffer.wrap(byte[])` copy the array automatically?  
**No.** It shares the array. If the caller needs an isolated byte snapshot, copy before handing it to I/O.

**Question 8.** After calling `read(dst)` and receiving a `Future`, when should `dst.flip()` be called to parse?  
**After** the read operation completes successfully (and after checking the result/EOF), not immediately after the initiating call.

**Question 9.** Two file writes have separate buffers and separate file offsets; are callbacks guaranteed to fire in submission order?  
**No.** `AsynchronousFileChannel` does not guarantee completion order for outstanding operations.

**Question 10.** To allocate buffers from a pool without growing memory indefinitely, what is required?  
**Quotas/backpressure** and a rule returning a buffer only when no operation or alias is still using it.

## 15. Practical Summary and Official Documentation

**Checklist before reusing a ByteBuffer:**

1. Has every asynchronous operation holding the buffer (or any shared view/backing array) **actually completed**?
2. Have the result `n`, partial read/write, EOF, errors, and timeouts/cancellations been handled per contract?
3. Does a subsequent operation in a logical read/write chain still need to hold the buffer?
4. Does any other thread, callback, attachment, or alias still have concurrent read/write access to the same bytes?
5. Only once ownership has returned to the application/pool should you `clear()`, `flip()`, modify contents, or assign the buffer to a new task.

One sentence to remember: **"Asynchronous I/O borrows the buffer until completion; returning from the initiating call does not end the borrow."**

Java SE 21 Documentation:

- `AsynchronousFileChannel` — multiple operations, completion ordering, warning against accessing ByteBuffer before completion: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html
- `AsynchronousByteChannel` — partial read/write, buffer ownership, and pending exceptions: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html
- `AsynchronousSocketChannel` — one outstanding read/write, timeouts, and buffer state: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html
- `CompletionHandler` — `completed`/`failed`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html
- `ByteBuffer` — `position`, `limit`, `duplicate`, `slice`, backing array: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- `Future` — `get`, cancellation, and timeout: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html
