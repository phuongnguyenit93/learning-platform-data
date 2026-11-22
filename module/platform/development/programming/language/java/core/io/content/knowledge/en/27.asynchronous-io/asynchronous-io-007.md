# Continuing Reads and Writes When Asynchronous I/O Results Complete Only Partially

## 1. The Core Problem: One Completed Operation Does Not Equal a Completed Message

In Java NIO.2, **asynchronous I/O** lets an application initiate a `read` or `write` operation and receive results via `Future` or `CompletionHandler`. An I/O operation having **completed successfully** only means that *that particular transfer step* finished according to the API contract. It **does not promise** that all the bytes the application wanted were transferred.

For example, suppose you want to send 100 bytes:

~~~text
ByteBuffer to write: 100 bytes
     |
     +--> async write #1: completed(37)
     |         63 bytes left in buffer
     |
     +--> async write #2: completed(20)
     |         43 bytes left in buffer
     |
     +--> async write #3: completed(43)
               buffer exhausted --> full message sent locally
~~~

The byte counts `37, 20, 43` are illustrative only; actual results depend on the channel, OS, load, and timing. Even when every byte has been accepted by **local writes**, that **does not guarantee** the peer has received or successfully processed them.

The same applies to reading: a request to receive a 100-byte frame might complete the first time with 12 bytes. To obtain all 100 bytes, you must **re-submit read** with remaining buffer space until complete or until hitting EOF/error/deadline.

Central rule:

> **Treat the actual completed byte count as the source of truth, preserve state for the remainder, start the next operation only after the previous one finishes, and define a clear stopping condition.**

## 2. Distinguishing Three Kinds of Completion

| Concept | Meaning | Example |
|---|---|---|
| **I/O operation completed** | A single `read`/`write` call produced a result or failure | `completed(12, attachment)` |
| **Buffer completed** | Destination buffer is full for reading, or source buffer is empty for writing | `!dst.hasRemaining()` or `!src.hasRemaining()` |
| **Message/protocol completed** | An entire protocol-compliant frame/request/response has been processed | Received full length-prefixed body and validated it |

In TCP, the application builds **message framing** itself: length-prefix, delimiter, or fixed-length. A single `AsynchronousSocketChannel.read(dst, handler)` call does not correspond to a message. In files, filling a buffer completes just one chunk; large files require multiple chunks and advancing file offsets.

Notably: **async does not mean `Future.get()` is non-blocking**. The initiating call may return early, yet `future.get()` waits for the result and blocks the calling thread. `CompletionHandler` fits when you want to continue purely via callbacks; `Future` fits coordinating waiting on a thread permitted to block.

## 3. How Should Read and Write Results Be Interpreted?

### 3.1. Reading into a ByteBuffer

For asynchronous read APIs returning `Integer`:

- **`n > 0`:** exactly `n` bytes were read. The destination ByteBuffer's `position` advances accordingly; `limit` does not change automatically.
- **`n == 0`:** this read pass transferred no bytes (for instance, when the buffer has no `remaining`; other cases depend on the API). Do not treat this as EOF and do not create an unbounded hot retry loop.
- **`n == -1`:** end-of-stream when no more bytes are available to read. On a TCP socket, the inbound stream has ended; on a file, EOF was reached for the read condition.
- **Failure:** delivered via `CompletionHandler.failed(Throwable, A)` or `Future.get()` throwing `ExecutionException` (or cancellation/interruption).

For example, an 8-byte buffer starts with `position=0`, `limit=8`; if `completed(3)`, now `position=3`, `remaining=5`. Calling read again on **this same buffer** (after the previous operation finished) appends bytes starting at index 3; do not call `clear()` and lose the already-received state.

### 3.2. Writing from a ByteBuffer

For asynchronous write APIs returning `Integer`:

- **`n > 0`:** `n` bytes were taken from the source buffer for this write pass; `position` advances by `n`.
- **`n == 0`:** no bytes written yet. A controlled retry/deadline policy is needed, avoiding immediate tight callback recursion.
- **`src.hasRemaining() == true` after completion:** not all content has been sent yet; continue using the buffer with its remaining unwritten bytes.
- **`src.hasRemaining() == false`:** all bytes in the buffer have been transferred through successful write calls. On TCP, this is **not** confirmation that the receiver has read them.
- **Failure:** stop the operation chain, report the error, and handle the state where data may have been partially written.

Before sending, the buffer must be in **read mode** (`flip()` if just populated with `put(...)`). Using `StandardCharsets.UTF_8.encode(text)` returns a buffer already ready to read. Never call `clear()` or `rewind()` between partial writes; doing so can resend old bytes.

### 3.3. Avoid Incorrect Checks

~~~java
// Wrong: completed() being invoked does not prove everything was sent.
channel.write(src, null, new CompletionHandler<Integer, Void>() {
    public void completed(Integer n, Void unused) {
        System.out.println("Đã xong toàn message"); // may be wrong
    }
    public void failed(Throwable ex, Void unused) {
        ex.printStackTrace();
    }
});
~~~

This is a **counter-example snippet**, requiring a connected `channel` and proper imports. The correct approach must inspect `n` and `src.hasRemaining()` before deciding whether to continue or finish.

## 4. ByteBuffer: position, limit, flip, and compact Are Part of the Algorithm

The `ByteBuffer` holds the **in-progress read/write state**. Key state transitions to master:

| Operation | Effect | When to Use |
|---|---|---|
| `clear()` | `position=0`, `limit=capacity`; **does not physically erase data** | Start filling a new chunk once old data has been completely processed |
| `flip()` | `limit=position`, `position=0` | Switch a buffer just filled by reading or `put` into read mode |
| `compact()` | Move remaining bytes from `position..limit` to the start and switch to write mode | Parser consumed part of a frame, leaving unprocessed bytes |
| `hasRemaining()` | `position < limit` | Check if bytes remain to write or space remains to read |
| `remaining()` | `limit - position` | Compute remaining bytes, check lengths |
| `get()`/`put()` | Relative read/write and advance position | Parser/serializer |

For **socket reads**, if the application is assembling a 12-byte frame in a buffer of capacity 12:

~~~java
ByteBuffer dst = ByteBuffer.allocate(12);
// read #1 receives 5 bytes -> position = 5
// read #2 receives 4 bytes -> position = 9
// read #3 receives 3 bytes -> position = 12
dst.flip(); // now parse the exact 12 bytes
~~~

This is **state-illustration code**, not a standalone runnable I/O program. The reads are assumed to complete sequentially and the buffer is not touched while I/O is pending.

**Do not call `flip()` after every partial read when trying to fill a fixed buffer.** Flip only once the target region has been filled or when intentionally switching to process currently buffered data. If the parser consumes some bytes while leaving a frame fragment, use `compact()` to retain that fragment.

## 5. Future and CompletionHandler: Two Ways to Continue

### 5.1. Future<Integer>

`AsynchronousFileChannel.read(dst, filePosition)`, `write(src, filePosition)`, and `AsynchronousSocketChannel.read(dst)`/`write(src)` have overloads returning `Future<Integer>`.

A simple flow:

~~~java
Future<Integer> pending = asyncFile.read(dst, fileOffset);
int n = pending.get(); // wait for completion; calling thread blocks
// After get() succeeds, dst.position() reflects received bytes.
// If data is still incomplete, initiate a new read at fileOffset + n.
~~~

This is an illustrative snippet assuming `AsynchronousFileChannel asyncFile`, `ByteBuffer dst`, and `long fileOffset`. `Future.get()` may throw `InterruptedException` or `ExecutionException`; code needs a handling/cancellation policy.

The advantage is easy-to-write sequential loops and straightforward correctness reasoning. The limitation is that the `get()` thread must wait; it does not turn the program into callback-driven non-blocking processing.

### 5.2. CompletionHandler<V,A>

The callback style delivers results through:

~~~java
void completed(V result, A attachment);
void failed(Throwable exc, A attachment);
~~~

`V` is usually `Integer` for a single buffer, `Long` for scattering/gathering multiple buffers, or `Void` for connect. `A` is an application-chosen **attachment** carrying operation state, such as file offset, ByteBuffer, request ID, or session object.

Inside `completed`:

1. If `n > 0`, update the offset by **the actual byte count** (when the API uses offsets).
2. Check `ByteBuffer.hasRemaining()`.
3. If more data remains, issue the next asynchronous read/write with the proper buffer and offset.
4. Once sufficient, complete the operation at the **message** level, notify downstream, and release ownership.
5. If `n == 0` or failure occurs, apply an appropriate retry/deadline policy; never create an infinite loop or swallow exceptions.

Inside `failed`, terminate/transition the request state rather than leaving a `CompletableFuture`/latch hanging forever. Completion handlers should be brief; heavy CPU processing should move to an application executor if needed.

## 6. AsynchronousFileChannel: Offsets Are Mandatory and Independent

Unlike `FileChannel` which has a **current file position**, `AsynchronousFileChannel` **has no shared current position**. Every `read`/`write` call passes a `long` **file position**. For example:

~~~java
Future<Integer> readFuture = input.read(dst, 100L);
int bytesRead = readFuture.get();
// To continue reading sequentially in the file: next position is 100L + bytesRead.
~~~

Illustrative snippet: this is an offset **within the file**, not `ByteBuffer.position()`. You must track two numbers:

- `fileOffset`: byte index in the file.
- `buffer.position()`: index inside the buffer for the next I/O pass.

These two indices do not synchronize with each other automatically. After a write that completes only `n` bytes, **write again at `fileOffset + n`** using the buffer whose position has already advanced by `n`. Keeping the old offset for the next partial write can overwrite the bytes just written. Manually adding `buffer.position()` a second time can create gaps or skip bytes.

`AsynchronousFileChannel` allows **multiple I/O operations to be outstanding simultaneously**, yet completion order and callback order are not guaranteed. Do not launch a batch of writes to overlapping file regions assuming they will execute in submission order. A single `ByteBuffer` is also unsafe when used concurrently by multiple pending I/O operations.

### Progression Illustration

~~~text
Source file:     A B C D E F G H I J
Buffer capacity: 6

read(dst, offset=0)  -> n=4, dst.position=4
read(dst, offset=4)  -> n=2, dst.position=6
flip()               -> prepare to write 6 bytes A..F

write(src, offset=0) -> n=3, src.position=3
write(src, offset=3) -> n=3, src.position=6 (chunk finished)

Read next chunk:
read(dst, offset=6)  -> ... until EOF
~~~

The numbers `4,2,3,3` are examples, with no guarantee they match the byte counts on any specific machine.

## 7. Runnable Java 17+ Program: Copying with Asynchronous File Channels

This program actually copies file contents using `AsynchronousFileChannel`, without assuming every read/write transfers the entire buffer.

- **Intentionally uses a 4-byte buffer capacity** for a 21-byte file, ensuring multiple chunked read/write passes are required.
- Outer loop reads from the source file, advancing the offset by actual `read` bytes.
- Inner loop writes all bytes of the chunk from the buffer, advancing the offset by actual `written` bytes.
- `Future.get()` makes the example easy to observe and **synchronizes at the wait point**. The I/O itself is still initiated through asynchronous channels.
- Because the example does not simulate backpressure, if an I/O call unexpectedly returns 0 while the buffer still has space/data, the program **stops with an error** instead of spinning infinitely; production code can implement retries with deadlines and scheduling.

**File `AsyncPartialDemo.java`:**

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public class AsyncPartialDemo {
    public static void main(String[] args) throws Exception {
        Path source = Files.createTempFile("async-source-", ".txt");
        Path target = Files.createTempFile("async-target-", ".txt");
        byte[] expected =
                "async-data-0123456789".getBytes(StandardCharsets.UTF_8);

        try {
            Files.write(source, expected);
            long copied = 0L;

            try (AsynchronousFileChannel input =
                         AsynchronousFileChannel.open(
                                 source, StandardOpenOption.READ);
                 AsynchronousFileChannel output =
                         AsynchronousFileChannel.open(
                                 target, StandardOpenOption.WRITE,
                                 StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer buffer = ByteBuffer.allocate(4);
                long readOffset = 0L;
                long writeOffset = 0L;

                for (;;) {
                    buffer.clear();
                    int read = input.read(buffer, readOffset).get();

                    if (read == -1) {
                        break; // End of source file.
                    }
                    if (read == 0) {
                        throw new IOException("No read progress");
                    }

                    readOffset += read;
                    buffer.flip();

                    while (buffer.hasRemaining()) {
                        int written =
                                output.write(buffer, writeOffset).get();

                        if (written <= 0) {
                            throw new IOException("No write progress");
                        }
                        writeOffset += written;
                    }
                }
                copied = writeOffset;
            }

            System.out.println("bytes=" + copied);
            System.out.println("equal=" +
                    Arrays.equals(expected, Files.readAllBytes(target)));
            System.out.println("text=" + Files.readString(target));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
        }
    }
}
~~~

Compile and run:

~~~bash
javac AsyncPartialDemo.java
java AsyncPartialDemo
~~~

**Verified stdout on JDK:**

~~~text
bytes=21
equal=true
text=async-data-0123456789
~~~

Significance:

1. 21 bytes cannot fit inside a 4-byte buffer; the program must process multiple chunks.
2. `input.read(buffer, readOffset).get()` awaits **one read operation**. The successful byte count `read` is added to the source offset.
3. `buffer.flip()` prepares the exact bytes read for writing, excluding stale bytes in the buffer.
4. `while(buffer.hasRemaining())` handles **partial writes** if the channel writes fewer bytes than desired; `writeOffset` advances by the actual `written` count.
5. At `read == -1`, the loop terminates due to EOF. After closing the channels, the program verifies the target file has the exact content.

Because the program calls `Future.get()`, each iteration waits for completion before reusing the buffer. In a real callback pipeline, maintain **ownership** of the buffer until the callback finishes processing or reusing it.

## 8. Resubmitting with CompletionHandler: Partial Write Pattern

To avoid blocking a thread with `get()`, the handler can initiate the next write after the previous callback completes. In the following example, `AsynchronousFileChannel` allows passing the file offset explicitly.

**Illustrative snippet placed inside a class with the relevant imports:**

~~~java
static CompletableFuture<Void> writeAll(
        AsynchronousFileChannel channel,
        ByteBuffer src,
        long startOffset) {

    CompletableFuture<Void> done = new CompletableFuture<>();

    if (!src.hasRemaining()) {
        done.complete(null);
        return done;
    }

    CompletionHandler<Integer, Long> handler =
            new CompletionHandler<>() {
        @Override
        public void completed(Integer n, Long offset) {
            if (n <= 0) {
                done.completeExceptionally(
                        new IOException("Write did not progress"));
                return;
            }

            long nextOffset = offset + n;
            if (!src.hasRemaining()) {
                done.complete(null);
                return;
            }

            try {
                channel.write(src, nextOffset, nextOffset, this);
            } catch (RuntimeException ex) {
                done.completeExceptionally(ex);
            }
        }

        @Override
        public void failed(Throwable exc, Long offset) {
            done.completeExceptionally(exc);
        }
    };

    channel.write(src, startOffset, startOffset, handler);
    return done;
}
~~~

This is an **illustrative method, not a standalone Java program**; its enclosing class must import `java.nio.ByteBuffer`, `java.nio.channels.AsynchronousFileChannel`, `java.nio.channels.CompletionHandler`, `java.io.IOException`, and `java.util.concurrent.CompletableFuture`. Input `channel` must be open for writing, `startOffset >= 0`, and `src` must be in read mode.

How it continues partial writes:

- The initial `channel.write(src, startOffset, startOffset, handler)` passes a `Long` attachment holding the file offset of the initiated pass.
- The `completed(n, offset)` callback runs when that operation finishes. `src.position()` has already advanced by the `n` bytes written.
- If data remains, the handler submits `write(src, offset+n, offset+n, this)`.
- If no data remains, `done.complete(null)` marks **the entire buffer** as transferred, not just one pass.
- On failure or no progress in this example, `done.completeExceptionally(...)` lets the caller observe the error.

**Regarding `n == 0`:** the snippet intentionally fails on zero progress instead of creating a busy callback loop. In production applications, you can **schedule a delayed retry**, apply a retry budget/deadline/backoff, or detect a stalled provider/backend. Never treat infinite immediate resubmission on `n==0` as a general solution.

**Regarding recursion/ordering:** callbacks can be dispatched very rapidly and in some implementations may execute directly on the initiating thread per contract. If a callback chain becomes very long, consider hopping to an executor/trampoline to avoid deep recursion or monopolizing completion threads. Also do not modify or reuse `src` from another thread while each operation is pending.

## 9. Continuing Partial Reads in CompletionHandler

To read **exactly N bytes** for a fixed-length TCP frame, the buffer must have its `limit` set so `remaining() == N` at startup. After each completion:

- `n > 0` and the buffer still has space: submit a new `read` on the same buffer.
- `n > 0`, buffer has no space left: full N-byte frame received; `flip()` and process.
- `n == -1` before receiving enough bytes: remote closed its output early; frame is truncated. This is a **framing error** even though EOF is a valid I/O result.
- `n == 0` while space remains: do not declare EOF and avoid tight retries; apply a wait/retry policy with a deadline.
- `failed(exc)`: fail the frame and clean up resources per ownership.

Callback-style Java pseudocode (not a standalone program):

~~~java
channel.read(dst, state, new CompletionHandler<Integer, State>() {
    @Override
    public void completed(Integer n, State s) {
        if (n == -1) {
            s.fail(new EOFException("Incomplete frame"));
            return;
        }

        if (!dst.hasRemaining()) {
            dst.flip();
            s.completeFrame(dst);
            return;
        }

        if (n == 0) {
            s.scheduleRetry(); // application deadline/retry policy
            return;
        }

        channel.read(dst, s, this); // only after previous completion
    }

    @Override
    public void failed(Throwable exc, State s) {
        s.fail(exc);
    }
});
~~~

In this pseudocode, `State` and `scheduleRetry()` are **undefined** application abstractions, so it **cannot compile standalone**. `scheduleRetry()` must know how to resubmit a single read on the right channel/buffer at the right time without creating multiple outstanding operations; it is not a built-in Java method. `s.completeFrame(dst)` must transfer buffer ownership safely.

Another option for **length-prefixed** protocols is to first read the complete header (e.g., 4 bytes), decode the length in the agreed `ByteOrder`, validate the size, and then allocate the body buffer or maintain a state machine to read the complete body. Never trust a length from a peer without enforcing a maximum size limit.

## 10. Differences Between AsynchronousSocketChannel and AsynchronousFileChannel

| Characteristic | AsynchronousSocketChannel | AsynchronousFileChannel |
|---|---|---|
| Data model | TCP stream with no message boundaries | Byte file with file offsets |
| Offset in call | `read(dst)`/`write(src)` takes no explicit file offset | `read(dst, position)`/`write(src, position)` |
| Concurrent I/O count | At most one pending read and one pending write per socket channel | Multiple reads/writes may be pending; order not guaranteed |
| Overlap | New read before old read finishes: `ReadPendingException`; likewise `WritePendingException` | Do not share one ByteBuffer for concurrent I/O; avoid uncoordinated overlapping file writes |
| EOF | `read == -1` when inbound stream ends | `read == -1` when file EOF is reached |
| Deadline | Timed read/write overloads (`CompletionHandler`) | Deadlines/cancellation typically managed at application layer |
| Special failures | `InterruptedByTimeoutException`; channel/buffer state may be undefined after timeout | `ExecutionException` wrapping Future error; closing with pending I/O may end in `AsynchronousCloseException` |

On a socket, **one read and one write can be outstanding concurrently**, yet you must not start a second read while the first read is still pending. When using callbacks to re-read, the completion callback itself is the natural place to initiate the next read; likewise for writes. If other threads also read/write the same socket, a coordinator is required to prevent duplicate operations.

**Especially regarding timeouts:** Java 17 warns that if a timeout occurs when it cannot be determined precisely how many bytes were read/written, the buffer and that I/O direction of the socket may enter an implementation-specific state, and subsequent operations may throw unspecified runtime exceptions. Do not automatically retry on the same buffer/channel as if zero bytes were transferred; typically you must close the connection or intentionally resynchronize the protocol.

## 11. Buffer Ownership and Concurrency Safety

A `ByteBuffer` currently used by an asynchronous read/write **is unsafe if the application concurrently modifies** `position`, `limit`, or contents before the operation completes. This is a source of very hard-to-reproduce bugs.

Key rules:

1. **One owner at a time.** When submitting I/O, transfer buffer ownership to the operation/handler until completion or failure is handled.
2. **Do not `clear`/`flip`/`put` on a pending buffer** from another thread. The buffer's position may be mutated by the operation.
3. **Do not rely on callback ordering across different `AsynchronousFileChannel` operations.** Write non-overlapping regions and manage offsets explicitly.
4. **`AsynchronousSocketChannel` permits only one pending read and one pending write.** This does not mean business state or shared ByteBuffers are thread-safe.
5. **Pass buffer and offset inside a state/attachment object** to avoid colliding over shared variables across connections.
6. **When a request is canceled**, determine per the API contract whether the operation can still complete or touch the buffer; avoid reusing the buffer prematurely. With `Future.cancel`, consequences may depend on whether I/O had already completed or whether cancellation closed the channel.

State machine model for a write buffer:

~~~text
NEW
 |
 +-- submit write ---> PENDING
                          |
                  completed(n > 0)
                          |
                 +--------+---------+
                 |                  |
           hasRemaining         no remaining
                 |                  |
              PENDING            COMPLETE
                 |
         failed / timeout
                 |
               FAILED
~~~

When multiple requests share a TCP connection, outbound messages must be queued so a single coordinating writer preserves **protocol byte order**. Do not fire two asynchronous writes on the same socket assuming they concatenate in the desired order automatically.

## 12. Handling Errors, Zero Progress, EOF, and Cancellation

### EOF Is Not Zero

- **`-1`:** the stream/file has ended under the read contract; if receiving a fixed frame with bytes still missing, report a truncated frame.
- **`0`:** this pass transferred no bytes. Do not conclude the remote closed; choose a sensible retry policy. When a buffer has no remaining space, returning 0 is expected.
- **`n > 0`:** progress was made; continue until the data-completion condition is satisfied.

### Avoiding Infinite Retries When Returning 0

In practice, if the system/backend can return 0 repeatedly, pick one of these strategies: schedule an asynchronous retry at a later time; enforce an operation/request timeout deadline; cap consecutive zero-progress attempts; or wait for readiness using an appropriate API. **Never spin in `while(true)`** immediately re-issuing the same operation from a completion handler whenever `n==0`.

### Separating I/O Errors from Protocol Logic Errors

For example, `read == -1` is valid EOF at the stream level, yet an **application error** if a body has received only 10 of 100 bytes. `write` completing does not mean the peer responded. `ExecutionException` from `Future.get` holds the root I/O cause; inspect `getCause()`. For `InterruptedException`, consider restoring the interrupt flag and stopping the task per policy. For timeout/cancellation, do not assume the buffer is definitely unmodified unless the Javadoc promises it.

### Closing and Resources

`AsynchronousFileChannel`/`AsynchronousSocketChannel` implement `AutoCloseable`. Use `try-with-resources` for the ownership scope. Do not close the channel while callbacks still need it or operations are pending, unless that is the explicit cancellation policy: closing can terminate outstanding operations with `AsynchronousCloseException`. For servers, manage the lifecycles of channel groups, worker executors, and queues independently of buffers/channels.

## 13. Applying to Real-World Protocols

**TCP length-prefixed message:**

1. Read the full 4-byte header using a stateful read loop/callback.
2. `flip` the header, read the length in the agreed `ByteOrder`, and validate against a maximum limit.
3. Allocate the body buffer of the exact capacity (or stream in chunks if the body is large).
4. Continue reading the body until the buffer is full; premature EOF is a frame error.
5. Process the body after I/O completes and ownership is transferred; if multiple messages appear in the stream, retain excess bytes and parser state.

**Sending a response:**

1. Serialize header + body into ByteBuffers ready for reading.
2. Submit the first write.
3. Upon completion, check the byte count and `hasRemaining`; continue with unwritten bytes.
4. Advance to the next message only once current buffers are exhausted or framing rules permit.
5. If a write fails or times out, update request state; do not silently discard unsent bytes.

**Copying a file with async file channels:**

1. Maintain separate source and target file offsets.
2. Read one chunk; increment source offset by `bytesRead`.
3. `flip` the buffer; write until the chunk finishes; increment target offset by `bytesWritten`.
4. `clear` the buffer once the entire chunk is written; read the next chunk.
5. Upon EOF, signal completion only after all writes have been confirmed.

## 14. Common Pitfalls

1. **"`CompletionHandler.completed` means the entire message finished."** False: the result may be smaller than expected.
2. **"`Future.get()` returning means the entire buffer was read."** False: only one operation finished.
3. **"One TCP read equals one message."** False: TCP streams require framing.
4. **"`read()==0` means EOF."** False: EOF uses `-1`.
5. **"`write()` always transfers all of `remaining`."** False: check the byte count and send the rest.
6. **"After a partial write, just `rewind()` and write again."** False: resends already-sent bytes.
7. **"After every partial read, call `clear()` for the next pass."** False: discards newly received fragments.
8. **"`AsynchronousFileChannel` advances a current file position automatically."** False: there is no shared current position; the caller manages offsets.
9. **"After writing `n` bytes, just advance the file offset by buffer capacity."** False: add the exact `n`.
10. **"You can start two async reads on one `AsynchronousSocketChannel`."** False: `ReadPendingException`; likewise for pending writes.
11. **"`AsynchronousFileChannel` callbacks always fire in submission order."** False: ordering is not guaranteed.
12. **"Reusing a pending ByteBuffer on another thread is still safe."** False: preserve ownership until the operation completes.
13. **"On `n == 0`, retry immediately in a tight loop for speed."** False: easily busy-spins; a wait policy is needed.
14. **"Timeout means zero bytes were transferred."** False: some asynchronous socket timeouts leave buffer/I/O state undefined.
15. **"Local writes exhausting all bytes proves the peer processed it."** False: an application-level response/ACK is required.

## 15. Self-Check Questions

**Question 1.** A `ByteBuffer` has `remaining=40`; the write callback returns `12`. What is the next step?

**Answer:** The buffer's position has advanced by 12; 28 bytes remain. Confirm the prior completion is done, initiate the next write for the remainder, and do not `rewind` the buffer.

**Question 2.** A TCP frame requires 100 bytes; read callbacks return `30` and then `-1`. Can it be considered successfully received?

**Answer:** No. The stream hit EOF before the frame reached 100 bytes; it is a truncated frame at the protocol level.

**Question 3.** `AsynchronousFileChannel.write(src, 50)` completes with `n=7`, yet the buffer still has bytes left. What is the next file position?

**Answer:** `57`; the buffer's position has already advanced by 7 to start from the unwritten portion.

**Question 4.** On `AsynchronousSocketChannel`, can you submit a second read while the first read is still pending?

**Answer:** No; `ReadPendingException`. You must chain after completion or coordinate state so only one read is pending.

**Question 5.** Why is the `Future.get()` example still asynchronous I/O at the channel level even though the code looks like blocking?

**Answer:** The operation is initiated on an asynchronous channel and returns a Future. However, the caller invoking `get()` deliberately blocked to wait for completion; callbacks can avoid this kind of waiting.

### Official Documentation

- [Java 17 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html)
- [Java 17 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html)
- [Java 17 — AsynchronousByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html)
- [Java 17 — CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html)
- [Java 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
