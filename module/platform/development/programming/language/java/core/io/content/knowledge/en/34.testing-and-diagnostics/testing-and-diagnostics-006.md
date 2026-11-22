# Simulating Partial Reads, Partial Writes, and Mid-Stream Failures in Java I/O

## 1. Why Test Partial I/O?

In Java NIO, `ReadableByteChannel.read(ByteBuffer)` and `WritableByteChannel.write(ByteBuffer)` return **the number of bytes actually transferred in the current call**, without promising to process all of `ByteBuffer.remaining()`. For small files on a local drive, a single read/write may happen to finish everything. However, non-blocking sockets, bandwidth-throttled streams, nearly full buffers, device I/O, or a test double can cause a call to transfer only a **partial** chunk, transfer zero bytes, or throw an `IOException` mid-sequence.

If you only test the "read all at once, write all at once" case, code easily hides bugs such as:

- Dropping the unwritten tail of a `ByteBuffer`, causing **data loss**.
- Treating `read() == 0` as EOF, stopping prematurely.
- Treating `write() == 0` as success and discarding untransferred bytes.
- Forgetting `flip()`/`clear()` or `compact()`, writing the wrong buffer region.
- Retrying the entire request/file after an error and **duplicating** already written parts.
- Assuming `IOException` can only occur before any byte has been transferred.
- Using `Thread.sleep` in tests instead of controlling a deterministic failure schedule.

The goal of this lesson is to **produce failure scenarios deliberately and reproducibly** using simulated channels, rather than waiting for slow networks or corrupting real files. You will learn how to test read-fully/write-fully loops, distinguish `0`/EOF/exceptions, observe buffer state, and design recoverable retries.

## 2. Read and Write Contracts to Memorize

For `ReadableByteChannel.read(dst)`, check `dst.remaining()` before reading to know the maximum bytes the buffer can accept.

| Result | Meaning | How to Handle |
| --- | --- | --- |
| `n > 0` | Placed `n` bytes into `dst`, advancing `position` accordingly. | Update byte count; continue if reading a fixed frame. |
| `n == 0` | No bytes read on this call; I/O may not be ready or buffer has no space left. | Do **not** assume EOF; check blocking mode, readiness, and deadline. |
| `n == -1` | End-of-stream (EOF) reached. | If `N` exact bytes were required and not met, report a truncated frame. |
| `IOException` | Read failed. | Do not treat as EOF or "certainly zero bytes read"; apply error/recovery policy. |

For `WritableByteChannel.write(src)`:

| Result | Meaning | How to Handle |
| --- | --- | --- |
| `n > 0` | Consumed `n` bytes from `src`, advancing `position` accordingly. | Continue writing while `src.hasRemaining()`. |
| `n == 0` | No bytes transferred on this call. | Keep buffer, wait for writability / enforce deadline; avoid busy-looping. |
| `IOException` | Call failed. | Do not ACK success and do not blindly retry if partial writes may have occurred. |

`write` **does not use `-1` to signal EOF** like `read` does. Some channels behave in blocking mode and wait until progress is made, whereas channels like `SocketChannel` in non-blocking mode may routinely return `0`. The `ReadableByteChannel` interface permits returning fewer bytes than available space in the buffer; one read does not equate to one TCP message.

### `ByteBuffer.position`, `limit`, and `remaining`

Suppose `ByteBuffer.allocate(8)`: initially, `position=0`, `limit=8`, `remaining=8`.

```text
After reading 3 bytes:
  position=3, limit=8
  [A B C _ _ _ _ _]
   ^ received data   ^ free space

After flip():
  position=0, limit=3
  [A B C] -> region ready to transmit/read

After writing 2 bytes:
  position=2, limit=3
  [A B | C] -> byte C still pending send

After writing remaining byte C:
  position=3, limit=3; remaining=0
```

`flip()` switches a buffer from filling mode to consuming mode. `clear()` resets `position` to 0 and `limit` to `capacity`, but **does not physically erase bytes**. `compact()` retains unconsumed bytes and shifts them to the front so more data can be read; useful for TCP parsers receiving incomplete frames.

Calling `clear()` immediately after a short `write` marks unwritten bytes as gone from the buffer and risks data loss. Always calling `flip()` after every `read` without checking state can resend a segment or corrupt parser state.

## 3. Designing Test Doubles for Partial I/O

A good unit test does not need Internet sockets or real disk writes. You can implement two Java NIO interfaces:

- `ReadableByteChannel` reading from a byte array and copying at most 2 bytes into the buffer per call.
- `WritableByteChannel` writing into a `ByteArrayOutputStream` and taking at most 3 bytes from the buffer per call.
- On the very first call, each channel returns `0` to verify code does not confuse "not ready" with EOF or success.
- Counting calls to verify code genuinely exercised the partial-I/O paths.

With test doubles, the numbers 2 and 3 are **deliberate test constraints**, not predictions about the filesystem or OS byte counts. The biggest benefit is complete determinism: running a hundred times follows the exact same event schedule.

### Runnable Java 17 Example: `ShortIoDemo`

Create file `ShortIoDemo.java`:

```java
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;

public class ShortIoDemo {
    static final class ShortReader implements ReadableByteChannel {
        private final byte[] data = "ABCDEFG".getBytes(StandardCharsets.US_ASCII);
        int pos, calls;
        boolean firstZero, open = true;
        @Override public int read(ByteBuffer dst) throws IOException {
            if (!open) throw new ClosedChannelException();
            calls++;
            if (!firstZero) { firstZero = true; return 0; }
            if (pos == data.length) return -1;
            int n = Math.min(2, Math.min(dst.remaining(), data.length - pos));
            dst.put(data, pos, n);
            pos += n;
            return n;
        }
        @Override public boolean isOpen() { return open; }
        @Override public void close() { open = false; }
    }
    static final class ShortWriter implements WritableByteChannel {
        private final ByteArrayOutputStream saved = new ByteArrayOutputStream();
        int calls;
        boolean firstZero, open = true;
        @Override public int write(ByteBuffer src) throws IOException {
            if (!open) throw new ClosedChannelException();
            calls++;
            if (!firstZero) { firstZero = true; return 0; }
            int n = Math.min(3, src.remaining());
            byte[] chunk = new byte[n];
            src.get(chunk);
            saved.write(chunk);
            return n;
        }
        String content() { return saved.toString(StandardCharsets.US_ASCII); }
        @Override public boolean isOpen() { return open; }
        @Override public void close() { open = false; }
    }
    public static void main(String[] args) throws Exception {
        try (ShortReader source = new ShortReader();
             ShortWriter target = new ShortWriter()) {
            ByteBuffer buffer = ByteBuffer.allocate(4);
            int total = 0;
            while (true) {
                int n = source.read(buffer);
                if (n < 0) break;
                if (n == 0) continue; // Fixture returns 0 exactly once.
                buffer.flip();
                while (buffer.hasRemaining()) {
                    int written = target.write(buffer);
                    if (written == 0) continue; // Fixture returns 0 exactly once.
                    total += written;
                }
                buffer.clear();
            }
            System.out.println("content=" + target.content());
            System.out.println("copied=" + total);
            System.out.println("read-zero=" + source.firstZero);
            System.out.println("write-zero=" + target.firstZero);
            System.out.println("read-calls=" + source.calls);
            System.out.println("write-calls=" + target.calls);
        }
    }
}
```

Compile/run with Java 17+:

```bash
javac --release 17 ShortIoDemo.java
java ShortIoDemo
```

Verified output:

```text
content=ABCDEFG
copied=7
read-zero=true
write-zero=true
read-calls=6
write-calls=5
```

**Interpreting the I/O schedule:**

1. The first `read` returns `0`; the loop transfers no bytes and continues only because the fixture guarantees forward progress.
2. The next four `read` calls return `2, 2, 2, 1` bytes. Each uses `dst.remaining()` and advances `position` by that exact count.
3. The final `read` returns `-1` to signal EOF. Total of **6** calls.
4. The first `write` returns `0`. Four subsequent progressive writes consume `2, 2, 2, 1` bytes. Total of **5** write calls.
5. `flip()` switches the 2 or 1 newly read bytes to read mode for the writer; `while (buffer.hasRemaining())` ensures no byte is lost before `clear()`.
6. `copied=7` and `content=ABCDEFG` prove all bytes passed through the fixture in exact order.

**Important warning:** Both `if (n == 0) continue` branches here are safe solely because the fixture deliberately returns `0` **only once**. Never copy this loop verbatim onto a production non-blocking channel: a channel can return `0` repeatedly, causing CPU spin. Use `Selector`/readiness, bounded waits, and timeouts suited to the architecture.

### An easily missed test bug

If a fixture always fulfills "every byte requested", this buggy code still passes:

```java
// Anti-pattern: broken because short writes are unhandled.
ByteBuffer src = ByteBuffer.wrap(payload);
channel.write(src);               // May write only part of it.
System.out.println("finished");   // Prematurely reports success.
```

This is an illustrative snippet with assumed `payload` and `channel`. A test using `ShortWriter` immediately exposes this bug: `src.hasRemaining()` remains true after the first progressive call, or the very first call returns `0` with no bytes written at all.

## 4. Simulating Mid-Stream Errors: Partial Transfer Followed by `IOException`

The next goal is testing not just short I/O, but **errors arriving after several successful calls**:

- The reader provides exactly 2 bytes `HE`, then throws `IOException` while the application still needs 3 bytes.
- The writer accepts exactly 2 bytes `HE`, then throws `IOException` on the next write; 3 bytes `LLO` remain in the example's buffer.
- The application must record the data as **incomplete**, never reporting success.
- You cannot infer from the error that the receiver or storage **never received any bytes**.

### Java 17 Example: `MidStreamFailureDemo`

Create file `MidStreamFailureDemo.java`:

```java
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;

public class MidStreamFailureDemo {
    static final class FaultyReader implements ReadableByteChannel {
        boolean open = true;
        int calls;
        @Override public int read(ByteBuffer dst) throws IOException {
            if (!open) throw new ClosedChannelException();
            if (++calls == 1) {
                dst.put((byte) 'H').put((byte) 'E');
                return 2;
            }
            throw new IOException("injected read failure");
        }
        @Override public boolean isOpen() { return open; }
        @Override public void close() { open = false; }
    }
    static final class FaultyWriter implements WritableByteChannel {
        boolean open = true;
        int calls;
        final ByteArrayOutputStream saved = new ByteArrayOutputStream();
        @Override public int write(ByteBuffer src) throws IOException {
            if (!open) throw new ClosedChannelException();
            if (++calls == 1) {
                int n = Math.min(2, src.remaining());
                byte[] chunk = new byte[n];
                src.get(chunk);
                saved.write(chunk);
                return n;
            }
            throw new IOException("injected write failure");
        }
        @Override public boolean isOpen() { return open; }
        @Override public void close() { open = false; }
    }
    public static void main(String[] args) throws Exception {
        ByteBuffer received = ByteBuffer.allocate(5);
        try (FaultyReader source = new FaultyReader()) {
            try {
                while (received.hasRemaining()) {
                    int n = source.read(received);
                    if (n < 0) throw new EOFException("truncated frame");
                }
            } catch (IOException e) {
                System.out.println("read-error=" + e.getMessage());
            }
        }
        System.out.println("read-before-error=" + received.position());

        ByteBuffer pending = ByteBuffer.wrap(
                "HELLO".getBytes(StandardCharsets.US_ASCII));
        try (FaultyWriter target = new FaultyWriter()) {
            try {
                while (pending.hasRemaining()) {
                    int n = target.write(pending);
                    if (n == 0) throw new IOException("write stalled");
                }
            } catch (IOException e) {
                System.out.println("write-error=" + e.getMessage());
            }
            System.out.println("written-prefix=" +
                    target.saved.toString(StandardCharsets.US_ASCII));
            System.out.println("remaining=" + pending.remaining());
        }
    }
}
```

Compile/run:

```bash
javac --release 17 MidStreamFailureDemo.java
java MidStreamFailureDemo
```

Verified output:

```text
read-error=injected read failure
read-before-error=2
write-error=injected write failure
written-prefix=HE
remaining=3
```

The output is completely controlled by the fixture: the first read raises `received.position()` to `2`; the first write raises `pending.position()` to `2`. Then the error fires on the **next call** before the fixture modifies the buffer again, so the sink received the exact prefix `HE` while `3` bytes remain unwritten.

**Do not extrapolate to every real channel:** if an I/O call **itself** throws `IOException` while accessing the OS/device, the amount of progress durably saved or processed by a peer may be **indeterminate** at the application layer. The fixture's `ByteBuffer` position is measurable because we wrote it ourselves; the API provides no guaranteed "bytes safely committed to peer/database" count after arbitrary exceptions. Never assume a retry is safe based solely on `position()` after an error.

## 5. Mid-Frame EOF vs Mid-Frame `IOException`

When a protocol specifies a frame of **N bytes**, the reader must distinguish:

- Exactly `N` bytes read: complete frame.
- `-1` received with fewer than `N` bytes: **truncated frame**, even though EOF itself is normal stream termination.
- `IOException` thrown: read failure, never interpret as EOF.
- `0` returned: no progress yet; cannot conclude the frame is broken or complete.

A read-fully helper in a **blocking context** (illustrative code, not standalone):

```java
static void readFully(ReadableByteChannel input, ByteBuffer dst)
        throws IOException {
    while (dst.hasRemaining()) {
        int n = input.read(dst);
        if (n < 0) {
            throw new EOFException("Unexpected EOF: missing "
                    + dst.remaining() + " bytes");
        }
        if (n == 0) {
            throw new IOException("No progress; use readiness/deadline policy");
        }
    }
}
```

This helper intentionally **fails fast on `0`** when used in controlled tests to prevent infinite loops. On a non-blocking `SocketChannel`, `0` is valid; production handlers keep `dst` and register `OP_READ` rather than failing immediately. On normal blocking channels with buffer space remaining, `read` typically blocks until progress or EOF; still handle channel state and timeouts as appropriate.

When a frame has a **length prefix**, bound the length before allocating buffers to prevent security/resource exhaustion:

```text
[4-byte length][payload length bytes][optional checksum]
```

Test sequentially: "header short 1 byte", "payload short 1 byte", "negative/oversized length", "multiple frames delivered in one read", "one frame spanning multiple reads", and "repeated zero reads". These test the parser/protocol, complementing Channel API tests.

## 6. Writing Everything Does Not Mean an Atomic Transaction

A progressive write loop is commonly written as:

```java
// Illustrative snippet for channels guaranteeing progress per policy.
static void writeAll(WritableByteChannel output, ByteBuffer src)
        throws IOException {
    while (src.hasRemaining()) {
        int n = output.write(src);
        if (n == 0) {
            throw new IOException("No write progress");
        }
    }
}
```

This works well for **fixtures or blocking paths** expected to make progress. For non-blocking sockets, wait for `OP_WRITE` instead of throwing right away; do not leave `OP_WRITE` enabled continuously when no bytes are pending, because writable sockets will wake the event loop nonstop.

Even after `writeAll` finishes:

- For sockets, it **does not prove the remote application parsed/committed the data**; protocol-level acknowledgements are required.
- For files, it **does not prove bytes are durable across power loss**; check `FileChannel.force` and filesystem contracts.
- For large records, an operation may involve multiple small writes; crashing mid-way leaves an incomplete prefix on disk. You need checksums/versioning/journaling/atomic replacement or a storage engine.
- For non-idempotent network requests, a connection failure after a partial write creates **uncertainty about how far the receiver progressed**. Blind retries risk duplicate execution or double charges.

## 7. Safe Retry Strategies After Failure

A useful separation is distinguishing three levels:

| Level | What Can Be Known After a Successful Call? | What Cannot Be Concluded? |
| --- | --- | --- |
| `ByteBuffer` | `position` advanced by bytes the channel reported transferring. | That the peer processed them or disk committed them. |
| TCP connection | `write` accepted part of the byte stream into the local stack. | That the remote app received the full logical message. |
| Business application | Only an application-protocol response/ACK confirms completion. | If an ACK is lost, you cannot assume the server did no work. |

When an `IOException` occurs:

1. Log the **operation, offset/frame ID, expected size, bytes reported as transferred by prior successful calls**, exception type, and channel state.
2. Mark the request/file as **incomplete or uncertain**; never report success.
3. Check data semantics: temporary files can be deleted and rebuilt; append logs need record framing/checksums; network requests need idempotency keys or transaction status queries.
4. Enforce a retry budget, backoff, and deadline; avoid infinite retries when the device or network is down.
5. When the committed offset cannot be proven, **never** arbitrarily send just the remainder or resend from the beginning if the protocol lacks resume/deduplication support.

For example, an import file can be written to `incoming.tmp` and published via `ATOMIC_MOVE` after checksum verification; consumers never read temporary files. For logs preserving every record, use length/checksum/commit markers and discard any incomplete trailing record during recovery. This is a durability/transaction problem, **not solved merely by a write loop**.

## 8. Minimum Test Matrix to Run

| Test Case | Simulated Schedule | Result to Verify |
| --- | --- | --- |
| Immediate full read | `read -> N` | Correct byte contents and count. |
| Partial read | `read -> 2, 2, 1` | Accumulates all `N`, no drops or reordering. |
| Temporary 0 read | `read -> 0, N` | Does not treat `0` as EOF; no CPU spin in production. |
| EOF before `N` | `read -> 2, -1` | Reports truncated frame, does not parse partial data. |
| Read error after prefix | `read -> 2, IOException` | Reports error, preserves byte context, no ACK. |
| Immediate full write | `write -> N` | `hasRemaining == false`, exact bytes. |
| Partial write | `write -> 1, 2, ...` | Loops until buffer empties, no early `clear`. |
| Temporary 0 write | `write -> 0, N` | Retains pending bytes, waits for readiness/deadline. |
| Mid-stream write error | `write -> 2, IOException` | Prefix may have transferred; handles uncertain state. |
| Error on first call | `read/write -> IOException` | Does not misclassify as EOF, no infinite retry. |
| Tiny buffers | Capacity 1, 2, 3 | Preserves `flip`/`clear` state and byte order. |
| Empty / boundary payloads | 0, 1, N-1, N, N+1 | Never accesses past buffer limit. |
| Multiple messages | Frames split or coalesced | Parser retains state, never assumes 1 read = 1 message. |
| Client cancel / timeout | Deadline expires mid-I/O | Cleanup, close, no double-completion. |
| Retry after error | Retry with same ID | Idempotency/recoverability, no duplicate side effects. |

Use a test double with a **scripted return schedule** (`0, 2, 1, -1, exception`) rather than relying on `Thread.sleep` or live traffic to hit code paths. Integration tests should then run against local files, loopback TCP, and target volumes/OSes with realistic network delays and restart simulations.

### How to write assertions

Never assert only "no exception thrown". A strong suite verifies:

- **Exact content**: compare byte arrays (`Arrays.equals`), not just byte counts.
- **No dropped or duplicated bytes**: total bytes written equals payload length upon completion.
- **No infinite loops**: bound call counts or deadlines; tests must fail explicitly if a channel keeps returning `0`.
- **Buffer state**: `position, limit, remaining` match expected semantics at each step.
- **Error paths**: capture exceptions and ensure no commit/ACK executes after failure.
- **Resources**: both channels close inside `try-with-resources` on success and on exception.
- **Re-execution**: under retries, business state is not duplicated and uncommitted vs committed states remain distinguishable.

## 9. Observability and Diagnostics in Production

When issues occur only under load, logs should separate **normal short I/O** from **I/O failures**:

- Operation ID, channel type, local/remote endpoint, or sanitized path.
- Offset and total expected bytes of the file/record/frame.
- Bytes returned per call; count of `0` returns and short reads/writes.
- `ByteBuffer.position`/`limit`/`remaining` **before and after successful calls**, keeping in mind that buffer state may not reliably indicate commit status after an exception depending on the API.
- Readiness wait time, deadline, pending byte count, queue length, and retry count.
- Exception class, cause, and socket/file lifecycle; do not swallow stack traces needed for diagnosis.

Avoid logging full payloads containing tokens, PII, or huge binaries. Log samples or metadata sufficient to reproduce the issue; use record-level checksums when integrity verification is needed.

A brief example of structured logging:

```text
op=send-order-142 expected=1024 written=512 remaining=512 result=SHORT_WRITE
op=send-order-142 expected=1024 written=768 remaining=256 result=SHORT_WRITE
op=send-order-142 result=IO_ERROR error=IOException commit=UNKNOWN
```

This is a **hypothetical illustrative log**, not stdout from the program above. The `commit=UNKNOWN` field highlights that local byte counts cannot prove the peer did no business work.

## 10. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Proper Approach |
| --- | --- | --- |
| One `read` equals a full message | TCP and channels can short-read | Accumulating parser, length framing. |
| One `write` sends the whole buffer | Channels can short-write or return 0 | Check `hasRemaining` and continue on readiness. |
| Treating `read == 0` as EOF | EOF is `-1` | Handle `0` as no progress yet. |
| Busy-loop `while(write==0)` | 100% CPU when output buffer isn't ready | `Selector`/backpressure/deadline. |
| Calling `clear` with unwritten bytes left | Loses unsent bytes | `clear` only after full consumption; use `compact` if needed. |
| Treating `IOException` like EOF | Failures and normal completion have different semantics | Distinguish exception, EOF, and timeout. |
| Retrying payload from start after failure | Can duplicate side effects | Idempotency/resume/protocol ACK. |
| Assuming `position()` bytes were committed remotely after failure | Local buffer doesn't measure peer commit | Track state at the protocol level. |
| Tests based on sleeps/flaky networks | Flaky, hard to reproduce | Scripted fake channels/fault injection. |
| Testing only the happy path | Misses partial I/O and truncation | Matrix of `0`/short/EOF/error/boundaries. |
| Sharing a buffer object across concurrent ops | Data races and corrupted buffer state | Single owner per buffer until completion. |
| Calling `force` and assuming atomic file transactions | Durability is not atomicity | WAL/checksum/atomic publication/recovery. |

## 11. Practice Checklist

1. Have you identified whether the channel is **blocking or non-blocking**?
2. Have you clearly defined stop conditions: `N` bytes, `EOF`, deadline, or protocol marker?
3. Did you distinguish `0` from `-1` and `IOException`?
4. Do you preserve `ByteBuffer.remaining()` after a short write?
5. Do you call `flip` after `read` and `clear`/`compact` after write at the right times?
6. Are byte/frame limits enforced to guard against invalid input and OOM?
7. Are retry loops bounded by deadlines/readiness with no busy-looping?
8. Can fixtures deterministically replay schedules of partial transfers + `0` + EOF + `IOException`?
9. Do tests assert **byte content** and progress counts rather than just console output?
10. After failure, does the app enter uncertain/recovery/idempotency handling instead of falsely ACKing?
11. Are offsets/bytes/exceptions logged safely and resources closed properly throughout their lifecycle?
12. If real files or networks are used, are there integration tests on the target provider/OS?

## 12. Self-Check Questions

**1. Is `read(dst)` returning `2` when the buffer has room for 8 bytes an error?** No; short reads are valid behavior.

**2. Does `read(dst)` returning `0` mean EOF?** No. EOF on a readable channel is signaled by `-1`.

**3. If `write(src)` returns `0`, can you call `src.clear()`?** No, because bytes are still pending in the buffer.

**4. Reading a 5-byte frame, getting 2 bytes then `-1`: what is the result?** A truncated frame, typically throwing `EOFException`.

**5. After an `IOException` from a network write, can you be sure the server hasn't processed the request?** No; application-level acknowledgements/idempotency are required.

**6. Why are fake-channel tests more useful than just throttling real network bandwidth?** Because fake channels deterministically control `0` returns, partial counts, EOF, and exceptions, making error branches repeatable.

**7. Should you run a tight `while (channel.write(buf) == 0)` loop on a non-blocking socket?** No; wait for readiness with a timeout to prevent CPU spin.

**8. When a `write` call throws `IOException`, is `ByteBuffer.position` guaranteed to equal the bytes that reached disk/peer?** No. Buffer state is not evidence of application commit.

## Official Documentation

- [Java SE 21 — ReadableByteChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ReadableByteChannel.html): `read` may return fewer bytes than requested, `0`, or `-1`.
- [Java SE 21 — WritableByteChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/WritableByteChannel.html): `write` may write partially or `0`.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `clear`, `compact`, position/limit.
- [Java SE 21 — SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking network read/write.
- [Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): positional file I/O, IOException, `force`.
- [Java SE 21 — Selector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): readiness-based non-blocking I/O.

**Summary:** Do not test I/O assuming every read and write completes in full. Actively simulate **short reads**, **short writes**, `0`, EOF, and mid-stream failures; track `ByteBuffer` boundaries carefully and design recovery/idempotency when partial data has been transferred.