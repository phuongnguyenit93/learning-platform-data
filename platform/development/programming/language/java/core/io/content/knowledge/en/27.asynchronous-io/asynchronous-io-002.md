# AsynchronousFileChannel and Explicit Operation Positions in Java NIO.2

## 1. Objectives and Core Idea

`java.nio.channels.AsynchronousFileChannel` is the **asynchronous** file read/write API in Java NIO.2. Instead of forcing the calling thread to wait until reading/writing finishes, the application can **initiate an I/O operation**, receiving a `Future` object or providing a `CompletionHandler` to process when the task completes.

The defining characteristic of this API: **every read/write call must pass an explicit file position** (`long position`).

```java
Future<Integer> pendingRead = channel.read(destination, 128L);
Future<Integer> pendingWrite = channel.write(source, 512L);
```

The two statements above are illustrative examples with an open channel; they immediately return a `Future<Integer>` representing the eventual result. The resulting integer is the **actual number of bytes processed**, not the new offset. Reading may return `-1` when reaching EOF.

There is no `channel.position()` or offset-less `channel.read(buffer)` API like `FileChannel`. Therefore, each task must track **which position in the file it is working on**. When a call reads or writes only a portion of the data, the application must increment the offset itself and submit the next operation.

This lesson helps you:

1. Distinguish asynchronous I/O from synchronous I/O and non-blocking channels.
2. Open `AsynchronousFileChannel` with the right permissions and manage resources.
3. Use the two ways to receive results: **`Future`** and **`CompletionHandler`**.
4. Calculate offsets accurately, handle partial reads/writes, EOF, and `ByteBuffer`.
5. Understand the risks of sharing buffers, concurrent writes, errors, closing channels, and canceling Futures.
6. Apply a standalone Java 17+ program that can be compiled and run.

## 2. Asynchronous Does Not Mean the File Advances Its Own Cursor

Consider a file with ten ASCII bytes:

```text
File offset:  0 1 2 3 4 5 6 7 8 9 10
Content:      A B C D E F G H I J |EOF|
```

If you want to read four bytes starting at offset 3:

```java
ByteBuffer part = ByteBuffer.allocate(4);
Future<Integer> request = channel.read(part, 3L);
int count = request.get();
```

When the request completes and all four bytes are read, `part` contains `DEFG`. However, **the channel does not have a shared current position that moved from 3 to 7**. To read further, specify **offset 7** in the next call:

```java
ByteBuffer next = ByteBuffer.allocate(3);
Future<Integer> second = channel.read(next, 7L);
```

The difference from `FileChannel.read(buffer)` is that relative synchronous operations can advance `FileChannel.position()`. `AsynchronousFileChannel` always takes an offset for every `read/write`. This design is convenient when independent tasks want to access different file regions without contending over a shared file cursor.

### Mental Model

```text
Application thread                  I/O execution / system

read(dst, offset=3) ----------->   process read starting at byte 3
   |
   +--> Future<Integer>            [may not be completed yet]
   |
   +--> do other work
   |
future.get() ------------------>   wait if not finished
   |
   +--> receive number of bytes read
   +--> update application offset if further reading is needed
```

The asynchronous API **does not promise that every operating system provides native async disk I/O**: the provider may use a thread pool and synchronous file operations underneath. Asynchrony here refers to **the interface for initiation and completion delivery**, not a guarantee of higher performance in every scenario.

## 3. Comparison with FileChannel and SocketChannel

| Criterion | `FileChannel` | `AsynchronousFileChannel` | Non-blocking `SocketChannel` |
|---|---|---|---|
| I/O source | File | File | TCP socket |
| API model | Synchronous read/write in typical usage | Initiate operation, receive `Future` or callback | Call `read/write`, readiness handled via Selector |
| Current file position | Has `position()`/`position(long)` | **Does not have** this kind of current file position | Not a file offset |
| Offset-based read/write | Has `read/write(ByteBuffer,long)` | **Mandatory** to supply `position` in read/write calls | File offsets do not apply |
| When result is received | Returns when the read/write call finishes | Future/callback reports completion | Call returns bytes processed immediately if non-blocking |
| `Selector` | Not a selectable channel | **Cannot register with Selector** | Can register with Selector |
| Buffer | `ByteBuffer` | `ByteBuffer`, must remain stable while pending | `ByteBuffer` |
| Key characteristics to note | Has shared current position in relative I/O | Explicit offset; completion order may differ from initiation order | Readiness is not completion of an individual task |

**Do not call `configureBlocking(false)` on `AsynchronousFileChannel`**: it does not operate under the `SelectableChannel` model. To receive completion, use `Future` or `CompletionHandler`. `Selector` is a readiness tool suited for certain network channels, not every API with "channel" in its name.

## 4. How to Open AsynchronousFileChannel

### Simple Opening

```java
import java.nio.channels.AsynchronousFileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("data.bin");

try (AsynchronousFileChannel channel = AsynchronousFileChannel.open(
        path,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE)) {
    // Initiate I/O and wait for / receive results before closing.
}
```

This is an **illustrative code snippet**; it needs to be placed inside a class/method to run. Common options:

- `READ`: allows reading.
- `WRITE`: allows writing.
- `CREATE`: creates the file if it does not exist when opened for writing.
- `CREATE_NEW`: creates only a new file; fails if the file already exists.
- `TRUNCATE_EXISTING`: when opened for writing, truncates an existing file to empty.
- `DELETE_ON_CLOSE`: deletion mechanism tied to the open/close lifecycle; permissions and filesystem interactions must be understood before using.

**`APPEND` is invalid for `AsynchronousFileChannel`** under the channel opening contract. This API takes an explicit offset per operation; if you need safe appending across multiple writers, do not rely on `size() + write` as an atomic append guarantee.

### Opening with an ExecutorService

`AsynchronousFileChannel.open(Path, Set<? extends OpenOption>, ExecutorService, FileAttribute<?>...)` allows supplying a custom thread pool. Sample code (illustrative):

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
try {
    try (AsynchronousFileChannel channel =
            AsynchronousFileChannel.open(
                    path,
                    Set.of(StandardOpenOption.READ, StandardOpenOption.WRITE),
                    executor)) {
        // Initiate I/O and ensure all pending operations have finished.
    }
} finally {
    executor.shutdown();
}
```

Requires importing `ExecutorService`, `Executors`, `Set`, `AsynchronousFileChannel`, and `StandardOpenOption`. In this overload, the thread pool is supplied by the caller; **the caller is responsible for the `ExecutorService` lifecycle** and must coordinate shutdown with unfinished tasks/callbacks. Do not shut down prematurely while still submitting new operations or waiting for callbacks to process results.

The thread pool can affect throughput/latency. Do not assume 4 threads is always optimal; measure on the actual filesystem, I/O type, and concurrency level. `AsynchronousFileChannel.open` does not automatically turn every disk into a truly non-blocking I/O platform.

## 5. Approach 1 — Receiving Results with Future<Integer>

Simple API:

```java
Future<Integer> future = channel.read(dst, fileOffset);
int n = future.get();
```

`future.get()`:

- **Waits** if the operation has not completed.
- Returns the number of bytes read on success, `-1` on EOF.
- May throw `InterruptedException` if the waiting thread is interrupted.
- May throw `ExecutionException`, with the actual cause inside `getCause()`, if the I/O operation fails.
- A completed `Future` can have its result retrieved via `get` multiple times without re-initiating I/O.

Writing is similar:

```java
ByteBuffer src = StandardCharsets.UTF_8.encode("hello");
Future<Integer> pending = channel.write(src, 0L);
int written = pending.get();
```

The `write` call only transfers bytes in the **remaining region of the buffer** at the time the operation executes. Do not arbitrarily `clear`, `flip`, `put`, or reuse the same buffer for another I/O operation while the operation is pending.

**Design point:** if you call `future.get()` immediately after every `read/write`, the thread actually still blocks waiting. The code is still correct and useful for learning the API or writing helpers that read/write full byte counts, but it does not fully leverage overlapping I/O with other work. To achieve concurrency, you can launch independent operations, do other work, and then inspect the Futures/callbacks upon completion.

### Timeout When Waiting on a Future

```java
int n = future.get(3, TimeUnit.SECONDS);
```

This is an example requiring `TimeUnit` and handling `TimeoutException`, `InterruptedException`, and `ExecutionException`. The timeout on `get` only limits **how long the thread waits**; it **does not by default prove the underlying I/O in the system was canceled**. Even `future.cancel(...)` should not be interpreted as a portable guarantee that all I/O has stopped and the buffer can be modified arbitrarily right away. Manage the pending operation lifecycle according to the implementation contract and protect the buffer until it reaches a safe state.

## 6. Reading/Writing Exactly N Bytes: Offsets Must Be Incremented Manually

A single `read(dst, offset)` or `write(src, offset)` **may return fewer bytes than `remaining()`**. Because there is no current file position to advance automatically, helpers must manage `long fileOffset`.

### Reading an Entire Region

```java
static void readFully(
        AsynchronousFileChannel channel,
        ByteBuffer target,
        long startOffset
) throws Exception {
    long offset = startOffset;

    while (target.hasRemaining()) {
        Future<Integer> pending = channel.read(target, offset);
        int n = pending.get();

        if (n < 0) {
            throw new EOFException("Unexpected EOF at offset " + offset);
        }
        if (n == 0) {
            throw new IOException("Read made no progress");
        }
        offset += n;
    }
}
```

**This is an illustrative method**, requiring imports for `EOFException`, `IOException`, `AsynchronousFileChannel`, `ByteBuffer`, and `Future`. It waits for each request to finish before reusing the buffer. Throwing an error at `n == 0` avoids an infinite loop; systems needing a dedicated retry/backoff policy can use a different strategy.

### Writing an Entire Region

```java
static void writeFully(
        AsynchronousFileChannel channel,
        ByteBuffer source,
        long startOffset
) throws Exception {
    long offset = startOffset;

    while (source.hasRemaining()) {
        Future<Integer> pending = channel.write(source, offset);
        int n = pending.get();

        if (n <= 0) {
            throw new IOException("Write made no progress");
        }
        offset += n;
    }
}
```

Each time `write` completes, the **buffer** position advances by the actual number of bytes processed, and the **application's offset variable** must advance accordingly. If you write a loop that keeps calling `channel.write(source, startOffset)` without adding `n`, the subsequent write may **overwrite the very bytes from the previous write**.

### Why Does the Offset Need Type `long`?

Files can be larger than 2 GiB, exceeding the `int` limit. When computing the position of a fixed-size record:

```java
long offset = Math.addExact(
        headerSize,
        Math.multiplyExact((long) recordIndex, recordSize)
);
```

This is an illustrative snippet; variables must be declared with appropriate types. `Math.multiplyExact`/`addExact` help detect integer overflow when offsets are computed from input, rather than silently producing an incorrect offset. Check that `offset >= 0` and that offset + operation size stays within the allowed format bounds.

## 7. Complete Java 17+ Example: Explicit Positions

The following example:

1. Creates a temporary file.
2. Writes ten ASCII bytes `ABCDEFGHIJ` starting from offset 0.
3. Reads three bytes from offset 0 yielding `ABC`.
4. Reads four bytes from offset 3 yielding `DEFG`.
5. Overwrites bytes at offset 4 with `XY`, turning `EF` into `XY`.
6. Reads the entire file again, receiving `ABCDXYGHIJ`.
7. All helpers use `Future`, wait for completion, and advance the offset manually.

Save with the exact filename **`AsyncFilePositionDemo.java`**:

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Future;

public class AsyncFilePositionDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-position-", ".bin");

        try {
            try (AsynchronousFileChannel channel = AsynchronousFileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer initial = StandardCharsets.US_ASCII.encode(
                        "ABCDEFGHIJ");
                writeFully(channel, initial, 0L);
                System.out.println("Size: " + channel.size());

                ByteBuffer first = ByteBuffer.allocate(3);
                readFully(channel, first, 0L);
                first.flip();
                System.out.println("First: "
                        + StandardCharsets.US_ASCII.decode(first));

                ByteBuffer middle = ByteBuffer.allocate(4);
                readFully(channel, middle, 3L);
                middle.flip();
                System.out.println("Middle: "
                        + StandardCharsets.US_ASCII.decode(middle));

                ByteBuffer replacement = StandardCharsets.US_ASCII.encode("XY");
                writeFully(channel, replacement, 4L);

                ByteBuffer whole = ByteBuffer.allocate(10);
                readFully(channel, whole, 0L);
                whole.flip();
                System.out.println("Final: "
                        + StandardCharsets.US_ASCII.decode(whole));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static void readFully(
            AsynchronousFileChannel channel,
            ByteBuffer target,
            long startOffset
    ) throws Exception {
        long offset = startOffset;

        while (target.hasRemaining()) {
            Future<Integer> future = channel.read(target, offset);
            int n = future.get();
            if (n == -1) {
                throw new EOFException("Unexpected EOF at " + offset);
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
            offset += n;
        }
    }

    private static void writeFully(
            AsynchronousFileChannel channel,
            ByteBuffer source,
            long startOffset
    ) throws Exception {
        long offset = startOffset;

        while (source.hasRemaining()) {
            Future<Integer> future = channel.write(source, offset);
            int n = future.get();
            if (n <= 0) {
                throw new IOException("Write made no progress");
            }
            offset += n;
        }
    }
}
```

Compile and run in the directory containing the source:

```bash
javac AsyncFilePositionDemo.java
java AsyncFilePositionDemo
```

**Stdout when the filesystem permits creating, reading, writing, and deleting temporary files:**

```text
Size: 10
First: ABC
Middle: DEFG
Final: ABCDXYGHIJ
```

This is the exact expected output when all operations complete successfully. The line order is deterministic because each `get()` helper waits for its operation to finish before moving to the next step.

**Step-by-step explanation:**

- Writing `ABCDEFGHIJ` at offset 0 sets the file size to 10.
- `readFully(...,0L)` reads `ABC`; no current position is shifted to 3 on the channel.
- `readFully(...,3L)` reads `DEFG` independently of the previous read.
- `writeFully(...,4L)` writes `XY` at positions 4 and 5, replacing `EF` without inserting bytes; the length remains 10.
- `readFully(...,0L)` reads again from the start without needing to "seek to 0" or reopen.
- `ByteBuffer.flip()` puts the buffer into reading mode for the newly received bytes before ASCII decoding.
- Although the API uses `Future`, these helpers **read/write sequentially step by step because they wait on `get`**. The goal is to clarify offsets and correctness; parallel execution is an additional architectural topic.

## 8. Approach 2 — CompletionHandler: Callback When I/O Completes

Instead of returning a `Future` and waiting on `get()`, `AsynchronousFileChannel` provides overloads taking an `attachment` and a `CompletionHandler`:

```java
channel.read(buffer, offset, attachment, handler);
channel.write(buffer, offset, attachment, handler);
```

For read:

```java
channel.read(
        destination,
        100L,
        "record-25",
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer bytesRead, String recordId) {
                System.out.println(
                        "Completed " + recordId + ": " + bytesRead);
            }

            @Override
            public void failed(Throwable error, String recordId) {
                System.err.println(
                        "Failed " + recordId + ": " + error);
            }
        });
```

This is an **illustrative snippet inside a method**, requiring `CompletionHandler` to be imported and `channel` and `destination` to be declared. `attachment` is application-supplied data (here the String `"record-25"`), helping the callback identify which request completed. An attachment can be an object holding offset, buffer, request ID, deadline, or state; it is not automatically tied to data stored in the file.

Important differences:

- The `completed(result, attachment)` callback receives the number of bytes processed, not the `ByteBuffer` directly unless the application keeps a reference (for example, via the attachment).
- The `failed(exception, attachment)` callback receives asynchronous I/O errors.
- Callbacks may execute on a different thread from the thread that called `read/write`.
- The callback order for multiple independent requests **must not be assumed to match the initiation order**.
- If a read processes only part of the data, the callback must submit a new read with **offset + bytesRead** and the buffer's remaining space, or hand off the missing portion to a coordinator.
- Callbacks must handle exceptions in a controlled manner. An uncaught exception thrown directly inside a callback should not be assumed to propagate automatically to the initiating thread like `Future.get()`.

### Callback Reading a Full Region: Stateful Illustration

```java
record ReadState(ByteBuffer buffer, long nextOffset) {}

static void readNext(
        AsynchronousFileChannel channel,
        ByteBuffer target,
        long offset,
        CompletionHandler<Integer, Long> handler
) {
    channel.read(target, offset, offset, handler);
}
```

This snippet illustrates using **the offset as an attachment**; it needs to be declared inside a class with imports, and uses `record` purely as an example of state modeling. When the callback sees `n > 0`, the next read can call `channel.read(target, oldOffset + n, oldOffset + n, this)`. If `n == -1` before enough bytes are read, it is an EOF error. If `n == 0`, there should be a bounded retry/backoff policy. A real implementation needs a promise/future or final handler to report "the entire record has been read"; it must not mark completion just because one callback succeeded.

**Do not mix Future code and callbacks for the same I/O operation.** The two overloads establish two ways of receiving results; choose one clear completion-management model per request.

## 9. ByteBuffer While Operations Are Pending

This is a very common source of bugs in asynchronous I/O.

`AsynchronousFileChannel.read` writes data into `ByteBuffer`; `write` reads data from the buffer. While I/O has not yet completed:

- Do not alter the buffer's `position`, `limit`, or contents.
- Do not initiate another read/write operation using **the same buffer** without ensuring the previous operation has finished.
- Do not decode/read the received data before completion.
- Do not reuse or return the buffer to a pool before the final result has been processed.
- Once the callback reports completion or `Future.get()` succeeds, safely prepare `flip`/`clear` according to the appropriate workflow.

**Incorrect** example:

```java
ByteBuffer buf = ByteBuffer.allocate(1024);
Future<Integer> first = channel.read(buf, 0L);
buf.clear();                        // Wrong: the first I/O may still be pending.
Future<Integer> second = channel.read(buf, 1024L);
```

Two operations sharing the same buffer can cause position/contents to be accessed concurrently outside the safe contract. `ByteBuffer` does not automatically become synchronized shared memory just because the API call is asynchronous.

**Correct buffer-ownership** example:

```java
ByteBuffer firstBuffer = ByteBuffer.allocate(1024);
ByteBuffer secondBuffer = ByteBuffer.allocate(1024);

Future<Integer> first = channel.read(firstBuffer, 0L);
Future<Integer> second = channel.read(secondBuffer, 1024L);

int n1 = first.get();
int n2 = second.get();
// Only after get() succeeds, process the two corresponding buffers.
```

This is still an illustrative snippet. Before decoding, only the bytes corresponding to the completion result are valid newly read data. If a read is partial, the parser design must handle the missing portion. Do not assume `n1 == 1024` or `n2 == 1024`.

**Concurrency note:** even with two separate buffers, two reads on the same file while another thread writes or truncates the file can still observe inconsistent data. Separate buffers resolve application memory contention, not create a consistent file snapshot.

## 10. Why Is There No Shared Current Position?

In asynchronous I/O, the **initiation** time and **completion** time of requests can differ:

```text
T0: read(A, position=0)   ────────┐
T1: read(B, position=4096)    ──┐ │
T2: write(C, position=8192) ─┐ │ │
T3: write(C) completed       │ │ │
T4: read(B) completed          │ │
T5: read(A) completed            │
```

If every request automatically shared one cursor and incremented it upon completion, operation positions would be unpredictable and dependent on completion order. The API uses an **explicit offset at request submission**, allowing each operation to define its own data region.

However, **an explicit offset does not prove that concurrent I/O at the same region is atomic or deterministically ordered**. When two writes overlap:

```text
write A: offset=100, length=10
write B: offset=105, length=10
              [both write bytes 105..109]
```

The outcome in the overlapping region may depend on scheduling and the provider; the application must avoid overlapping writes or synchronize logically. For multiple tasks needing read-modify-write on the same record, a `read` followed by a `write` does not form an atomic transaction.

### A Safer Parallel Processing Model

- Each task has a **separate computed and validated offset**.
- Each task owns a **separate ByteBuffer** throughout the pending duration.
- No overlapping writes without a coordination mechanism.
- Bound the number of concurrent tasks to avoid overloading thread pools, memory, file descriptors, or I/O queues.
- Have policies for timeouts, retries, cancellation, and cleanup, especially when an error occurs while other Futures are still pending.
- If a consistent snapshot is needed, use an appropriate storage design (versioned immutable files, synchronization locks/latches, or transactions at another layer).

## 11. Completion, Cancellation, and Errors

### Future Exceptions

`Future.get()` can:

- Return `Integer >= 0` on success.
- Return `-1` for a read at EOF.
- Throw `InterruptedException` when the waiting thread is interrupted.
- Throw `ExecutionException` when the operation fails (inspect `getCause()`).
- Throw `CancellationException` when the Future has been canceled under the Future contract.

General handling:

```java
try {
    int n = pending.get();
    // Decide whether to parse, retry, or handle EOF based on n.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Cancel/coordinate cleanup per policy; do not blindly reuse buffer.
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Log/propagate the root cause appropriately for the application layer.
}
```

This snippet assumes `pending` has type `Future<Integer>` and the exceptions are imported. If data must be updated strictly once, retries must also account for the possibility that the prior operation wrote partially.

### Closing the Channel

`AsynchronousFileChannel` is `AutoCloseable`. Try-with-resources closes the channel when exiting scope, yet the application should **ensure requests have been awaited/completed before the scope ends**. Closing the channel while operations are pending can cause those operations to fail with channel-closing errors such as `AsynchronousCloseException` or `ClosedChannelException`, depending on timing and mechanism.

Do not treat `close()` as a business-level command meaning "wait for all callbacks to finish, deliver all results, and flush the file." Design a clear lifecycle: stop accepting new requests → wait for/coordinate in-flight requests → handle callbacks/results → perform storage sync if needed → close channel/executor.

### FileLock

`AsynchronousFileChannel` has asynchronous file locking operations and `tryLock`. File locks help coordinate access at the filesystem/provider level, but do not turn multiple `read/write` calls into a transaction; whether locks are mandatory or advisory depends on the platform. They also must be closed/released according to lifecycle.

If the goal is solely to access non-overlapping file regions, do not add locking arbitrarily: it can increase complexity and contention. Use it only when there is a clear concurrency contract needing protection.

## 12. `size()`, `truncate()`, `force()`, and Data Durability

Alongside `read/write`, `AsynchronousFileChannel` provides file management methods:

| Method | Meaning |
|---|---|
| `size()` | Returns the file size at the time of the call |
| `truncate(long size)` | Truncates the tail of the file when current size exceeds the argument |
| `force(boolean metaData)` | Requests synchronizing content (and metadata if true) to the storage device per the API contract |
| `lock(...)`, `tryLock(...)` | Supports locking the file or a file region with corresponding provider/platform semantics |
| `isOpen()`, `close()` | Manages channel state/lifecycle |

**`truncate` does not automatically extend the file** if the passed size is larger than the current length. To extend it, you must use a write mechanism or appropriate data design; there is no `channel.position(newPosition)` to move a current position because this API has no such shared cursor.

`force(true)` requests syncing updates made through the channel, but does not automatically create a transaction across multiple writes; ultimate durability depends on the filesystem, device, and provider. To ensure a file is complete across a crash during multiple writes, consider writing to a temporary file, verifying, syncing, and replacing the target according to filesystem semantics.

While I/O is pending, do not call `truncate` immediately expecting other reads/writes to execute in the order you imagine. Coordinate related operations before modifying file size.

## 13. Performance and Resource Limits

**Asynchronous is not automatically faster than synchronous.** The primary benefit appears when the application has other work to do while waiting for I/O, or needs to manage many independent tasks without dedicating a waiting application thread to each request.

When evaluating:

1. **Number of pending tasks:** too many Futures/ByteBuffers can create memory and thread-pool pressure.
2. **I/O size:** reading a few bytes at a time asynchronously can incur high overhead compared to reading/sending in suitable blocks.
3. **Executor/provider:** some implementations use a thread pool to execute file I/O; optimize by measuring performance rather than merely changing APIs.
4. **Disk and filesystem:** NVMe/HDD/network filesystem characteristics, caching, flushing, and parallel I/O counts can alter results.
5. **Concurrency and consistency:** running overlapping writes in parallel can corrupt data even if throughput increases.
6. **Completion latency:** keep callbacks fast and offload heavy CPU work to another executor or appropriate processing thread; do not block completion-pool threads for long.
7. **Durability:** `force`, metadata updates, syncing, and locking can significantly change latency; do not omit them just for prettier benchmarks if business requirements demand them.

If you only need to read a small file once and wait immediately, `Files.readAllBytes` or synchronous `FileChannel` may be simpler and sufficient. Choose `AsynchronousFileChannel` when **the completion/parallel requests model** genuinely benefits the architecture.

## 14. Common Pitfalls

1. **Assuming AsynchronousFileChannel has a current position.** It does not; every `read/write` takes an explicit `long position`.
2. **Failing to advance the offset after partial I/O.** The next call may re-read or overwrite old bytes.
3. **Believing one read/write processes the entire buffer.** Check the result, remaining bytes, and EOF.
4. **Calling `future.get()` immediately while still claiming the app is completely non-blocking.** `get` can wait; an async API does not make waiting threads disappear automatically.
5. **Confusing `Future.get()` with `ByteBuffer.get()`.** The former returns the I/O byte count after completion; the latter reads bytes from the buffer at its position.
6. **Reusing a ByteBuffer before completion.** Can corrupt data or violate the buffer access contract while pending.
7. **Using the same buffer for multiple simultaneous requests.** Even with different file offsets, the buffer's position/contents still contend.
8. **Confusing EOF `-1` with read `0`.** `0` can mean zero bytes read yet; `-1` means end of data at that position.
9. **Forgetting `flip()` before decoding a buffer that was read into.** The decoder may see an incorrect remaining range or miss the new data.
10. **Not handling `InterruptedException` properly.** Restore the interrupt flag when not intentionally consuming the interrupt and perform appropriate cleanup.
11. **Assuming callbacks run on the same thread or in submission order.** Completion order is not initiation order.
12. **Closing the channel/executor while I/O is still pending.** Operations may fail; a clear shutdown/lifecycle policy is needed.
13. **Using `Selector` with AsynchronousFileChannel.** This API is not a selectable channel.
14. **Passing APPEND when opening the channel.** `AsynchronousFileChannel` does not support that file-opening append mode.
15. **Using `size()` and writing at size as an atomic append across multiple writers.** Two writers may pick the same offset; coordination is required.
16. **Treating independent offsets as independent data.** Writes to the same region still race; truncate can affect other requests.
17. **Assuming canceling a Future always rolls back partial writes.** There is no transaction/rollback; retries require an idempotent design.
18. **Tuning only thread count while ignoring storage characteristics.** Benchmark on the actual device type, scale, and I/O pattern.

## 15. When Should You Choose AsynchronousFileChannel?

### Case A — Processing Many Records at Independent Offsets

A fixed-size record file has several segments at known positions. You can submit parallel `read(buffer, offset)` calls with a **separate buffer per request**, then process the results once all complete. This pattern helps when the application layer wants concurrency and does not need a shared cursor.

### Case B — Server Needing to Overlap Work with File I/O

A request needs to load a large file segment, while the processing thread still has other work. You can submit the file read and continue handling independent parts, then let the callback/Future signal readiness. Mind backpressure and the number of live buffers.

### Case C — Infrequent Sequential File Edits

If the program reads 100 bytes, processes them, writes 20 bytes, and always waits immediately, `FileChannel` or `RandomAccessFile` may be simpler. `AsynchronousFileChannel` is not mandatory simply because a file is large.

### Case D — Multiple Writers Appending to the End of the Same File

Do not simply call `channel.write(buffer, channel.size())` concurrently and expect orderly appending. `size()` is a snapshot at the moment of the call; two writers can pick the same offset. You need a synchronized offset allocator, a single sequential writer, a purpose-built log record architecture, or a storage mechanism with proper append/transaction support.

### Case E — Wanting Event-Driven Network Streams

If the task is TCP/UDP networking rather than file I/O, choose an appropriate network API such as `SocketChannel` + `Selector` or the `AsynchronousSocketChannel` family; do not try to use `AsynchronousFileChannel` for sockets.

## 16. Self-Check Questions

**Question 1.** Does `AsynchronousFileChannel` have `channel.position(100L)` like `FileChannel`?  
**No.** Every `read/write` takes an explicit `long position`.

**Question 2.** Calling `read(buffer, 100L)` returns a `Future<Integer>`, and `get()` returns 40. At what offset should the next portion be read?  
**Offset 140**, provided the buffer still has remaining space and the format requires further reading.

**Question 3.** Calling `write(source, 500L)`, `get()` returns 10, yet `source` still has 8 bytes remaining. Where should the next write start?  
**Offset 510.** Wait for the previous write to complete, then call `write(source, 510L)`.

**Question 4.** Can you call `buffer.clear()` while the read Future is still pending?  
**You should not;** the buffer belongs to the running operation. Wait for completion or design ownership before changing buffer state.

**Question 5.** If you call `Future.get()` immediately after submitting, is the code necessarily non-blocking?  
**No.** `get()` can block the calling thread until completion.

**Question 6.** Do two reads at offsets 0 and 4096 with two separate buffers always return in submission order?  
**No.** Completion order can differ. If ordered processing is required, the application must coordinate the results.

**Question 7.** Can `AsynchronousFileChannel` register `Selector.OP_READ`?  
**No.** It is not a `SelectableChannel`.

**Question 8.** `channel.size()` is 1000; two writers both submit `write(buffer,1000L)`. Is sequential appending without overlapping bytes guaranteed?  
**No.** The operations use the same offset and may overwrite each other. Offset allocation or serialization is required before submission.

**Question 9.** Does a write returning success mean the data is durable across a power failure?  
**Not necessarily.** A durability policy is needed, such as `force` where appropriate, along with understanding provider/filesystem limits.

## 17. Summary

- `AsynchronousFileChannel` is an asynchronous file I/O API with **explicit offsets for each read/write**; it has no `FileChannel`-style current file position.
- `read/write(ByteBuffer, long)` returns `Future<Integer>`; overloads with an attachment and `CompletionHandler` allow receiving completion via callbacks.
- **Successful byte counts may be less than remaining**; advance the offset by the actual bytes processed and handle EOF.
- **ByteBuffers must remain untouched while operations are pending**; do not reuse a single buffer for overlapping requests.
- **Separate offsets help organize concurrency**, but do not automatically make concurrent data consistent and do not replace locks or transactions.
- Asynchrony is a **programming model**, not a promise of higher speed under all conditions; measure performance and manage bounded resources.

### Java SE 17 API References

- [AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html)
- [CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html)
- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html)
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
