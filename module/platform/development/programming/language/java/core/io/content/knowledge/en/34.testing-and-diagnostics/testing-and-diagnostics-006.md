# Simulating Partial Reads, Partial Writes, and Mid-Stream Failures in Java I/O

## 1. Why Must You Test Partial I/O?

In Java NIO, `ReadableByteChannel.read(ByteBuffer)` and `WritableByteChannel.write(ByteBuffer)` return **the number of bytes actually transferred in the current call**, without promising to consume or fill all of `ByteBuffer.remaining()`. With small files on a local disk, a single read or write may happen to transfer everything. However, non-blocking sockets, bandwidth-throttled streams, nearly full buffers, device I/O, or a test double can cause a call to transfer only **part of the data**, transfer zero bytes, or throw an `IOException` partway through a sequence of operations.

If you only test the "read all in one call, write all in one call" scenario, the code easily hides bugs:

- Leaving unwritten bytes behind in `ByteBuffer`, causing **data loss**.
- Treating `read() == 0` as EOF, stopping prematurely.
- Treating `write() == 0` as success and dropping untransferred bytes.
- Forgetting to call `flip()`/`clear()` or `compact()`, writing the wrong buffer slice.
- Retrying the entire request or file after an error and **duplicating** the already-completed portion.
- Assuming `IOException` can only happen before any bytes are transferred.
- Using `Thread.sleep` in tests instead of controlling the failure schedule deterministically.

The goal of this lesson is to **trigger failure conditions proactively and reproducibly** using simulated channels rather than waiting for slow networks or corrupting real files. You will learn how to test read-fully/write-fully loops, distinguish `0`/EOF/exceptions, inspect buffer state, and design recoverable retry strategies.

## 2. Read and Write Contracts to Memorize

For `ReadableByteChannel.read(dst)`, inspect `dst.remaining()` before reading to know the maximum bytes the buffer can accept.

| Result | Meaning | How to Handle |
| --- | --- | --- |
| `n > 0` | Placed `n` bytes into `dst` and advanced `position` accordingly. | Update byte count; continue if reading a fixed-size frame. |
| `n == 0` | No bytes read on this call; I/O may not be ready or the buffer has no space. | **Do not** treat as EOF; respect blocking mode, readiness, and deadlines. |
| `n == -1` | Reached end-of-stream (EOF). | If exact `N` bytes were needed and haven't arrived, report a truncated frame. |
| `IOException` | Read failed. | Do not treat as EOF or assume "no bytes were read"; apply error/recovery policy. |

For `WritableByteChannel.write(src)`:

| Result | Meaning | How to Handle |
| --- | --- | --- |
| `n > 0` | Consumed `n` bytes from `src` and advanced `position` accordingly. | Continue writing while `src.hasRemaining()`. |
| `n == 0` | No bytes transferred on this call. | Retain buffer, wait for writability / enforce deadline; avoid busy loops. |
| `IOException` | Call failed. | Never ACK success and never retry blindly if a partial write may have occurred. |

`write` **does not use `-1` as an EOF signal** the way `read` does. Blocking channels may wait until progress occurs, whereas non-blocking channels like a non-blocking `SocketChannel` may frequently return `0`. The `ReadableByteChannel` interface permits returning fewer bytes than available buffer space; a single read is not equivalent to a single TCP message.

### `ByteBuffer.position`, `limit`, and `remaining`

Suppose `ByteBuffer.allocate(8)`: initially `position=0`, `limit=8`, `remaining=8`.

```text
After reading 3 bytes:
  position=3, limit=8
  [A B C _ _ _ _ _]
   ^ received data    ^ remaining space

After flip():
  position=0, limit=3
  [A B C] -> region ready to transmit/read

After writing 2 bytes:
  position=2, limit=3
  [A B | C] -> byte C still unsent

After writing remaining byte C:
  position=3, limit=3; remaining=0
```

`flip()` switches a buffer from filling mode to draining mode. `clear()` resets `position` to 0 and `limit` to `capacity` without **physically erasing bytes**. `compact()` keeps unconsumed bytes and shifts them to the front so more can be read; this is useful for TCP parsers receiving partial frames.

Calling `clear()` immediately after a short `write` marks the unwritten bytes as gone from the buffer and risks data loss. Always calling `flip()` after every `read` without checking state can re-send a slice or corrupt parser state.

## 3. Designing Test Doubles for Partial I/O

A good unit test does not need an Internet socket or real disk writes. You can implement two Java NIO interfaces:

- `ReadableByteChannel` reading from a byte array and copying at most 2 bytes per call into the buffer.
- `WritableByteChannel` writing into a `ByteArrayOutputStream` and draining at most 3 bytes per call from the buffer.
- On the first call, each channel returns `0` to verify the code does not confuse "not ready yet" with EOF or completion.
- Tracking call counts to confirm the code actually exercised the partial I/O paths.

With test doubles, the numbers 2 and 3 are **deliberate test constraints**, not predictions of filesystem behavior or OS chunk sizes. The biggest advantage is completely deterministic testing: running a hundred times exercises the exact same event schedule.

### Runnable Java 17 Example: `ShortIoDemo`

Create `ShortIoDemo.java`:

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

Compile and run with Java 17+:

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

**I/O trace explanation:**

1. The first `read` returns `0`; the loop transfers nothing and continues only because the fixture is guaranteed to make progress next.
2. The next four `read` calls return `2, 2, 2, 1` bytes. Each consumes `dst.remaining()` and advances `position` by that exact count.
3. The final `read` returns `-1` to signal EOF. Total: **6** read calls.
4. The first `write` returns `0`. Four progressing writes then consume `2, 2, 2, 1` bytes. Total: **5** write calls.
5. `flip()` switches the 2 or 1 newly read bytes to read mode for the writer to consume; `while (buffer.hasRemaining())` guarantees no bytes are lost before `clear()`.
6. `copied=7` and `content=ABCDEFG` prove all bytes passed through the fixture in the exact order.

**Important warning:** the two `if (n == 0) continue` branches here are safe only because the fixture deliberately returns `0` **once**. Never copy this loop directly onto a production non-blocking channel: a channel may return `0` repeatedly, causing CPU spin. Use `Selector`/readiness, bounded queues/waits, and proper timeouts architecturally.

### An Easily Missed Test Bug

If the fixture always returns "all requested bytes," the following buggy code still passes:

```java
// Anti-pattern: buggy because short writes are unhandled.
ByteBuffer src = ByteBuffer.wrap(payload);
channel.write(src);               // May write only part of the buffer.
System.out.println("finished");   // Reports success prematurely.
```

This is an illustrative snippet with assumed `payload` and `channel`. A test using `ShortWriter` exposes this bug immediately: `src.hasRemaining()` remains true after the first progressing call, or the first call even returns `0` with zero bytes written.

## 4. Simulating Mid-Stream Failures: Partial Transfer Followed by `IOException`

The next goal is testing not just short I/O, but **errors arriving after several successful calls**:

- The reader supplies exactly 2 bytes `HE`, then throws `IOException` while the application still needs 3 bytes.
- The writer accepts exactly 2 bytes `HE`, then throws `IOException` on the next write; 3 bytes `LLO` remain in the example's buffer.
- The application must record the data as **incomplete**, never returning success.
- You cannot infer from the error that the receiver or storage **never received any bytes**.

### Java 17 Example: `MidStreamFailureDemo`

Create `MidStreamFailureDemo.java`:

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

Compile and run:

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

The output is completely controlled by the fixture: the first read advances `received.position()` to `2`; the first write advances `pending.position()` to `2`. The error then occurs on the **next call** before the fixture modifies the buffer again, so the sink received the prefix `HE` with `3` bytes left unwritten.

**Do not extrapolate this to every real channel:** if an I/O call **itself** throws `IOException` midway through accessing the OS or device, how much progress was durably stored or processed by the peer can be **indeterminate** at the application layer. The fixture's `ByteBuffer` position is measurable only because we wrote the fixture; the API provides no "guaranteed committed bytes to peer/database" after arbitrary exceptions. Avoid declaring a retry safe based solely on `position()` after an error.

## 5. Mid-Frame EOF vs. Mid-Frame `IOException`

When a protocol specifies a frame of **N bytes**, the reader must distinguish:

- Reading exact `N` bytes: complete frame.
- Receiving `-1` when fewer than `N` bytes arrived: **truncated frame**, even though EOF itself is normal stream termination.
- Receiving `IOException`: read error, never to be interpreted as EOF.
- Receiving `0`: no progress yet; cannot conclude whether the frame is broken or complete.

A read-fully helper in a **blocking context** (illustrative code, not a standalone program):

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

This helper intentionally **fails fast on `0`** when used in controlled tests to avoid infinite loops. With a non-blocking `SocketChannel`, `0` is valid; a production handler should retain `dst` and register `OP_READ` rather than treating it as an immediate error. With ordinary blocking channels, when the buffer has space, `read` typically waits for progress or EOF; still handle channel state and timeouts as appropriate.

When a frame has a **length prefix**, bound the length before allocating a buffer to prevent security and resource exhaustion bugs:

```text
[4-byte length][payload length bytes][optional checksum]
```

Test in turn "header short by 1 byte," "payload short by 1 byte," "negative/oversized length," "multiple frames in one read," "one frame spanning multiple reads," and "multiple zero reads." These are parser/protocol tests complementing Channel API tests.

## 6. Writing Everything Does Not Equal an Atomic Transaction

A progressing write loop is commonly written as:

```java
// Illustrative snippet for a channel guaranteed by policy to make progress.
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

This works for **fixtures or blocking paths** expected to make progress. For non-blocking sockets, wait for `OP_WRITE` instead of throwing immediately; do not keep `OP_WRITE` enabled when no bytes are pending, because sockets are usually writable and will keep the event loop spinning constantly.

Even when `writeAll` finishes:

- Over a socket, it **does not prove the remote application parsed or committed the data**; protocol-level acknowledgments are required.
- On a file, it **does not prove bytes survive power loss**; check `FileChannel.force` and the filesystem contract.
- For large records, an operation may involve multiple small writes; if a crash occurs mid-way, the file can contain a partial prefix. You need checksums, versioning, journaling, atomic replacement, or a storage engine.
- For non-idempotent network requests, a connection error after a partial write can leave **uncertainty about how far the receiver processed the request**. Blindly retrying can cause duplicates or double charges.

## 7. Safe Retry Strategies After Failure

A common confusion is conflating three levels:

| Level | What Is Known After a Successful Call? | What Cannot Be Concluded? |
| --- | --- | --- |
| `ByteBuffer` | `position` advanced by the bytes the channel reported transferring. | Whether the peer processed them or disk committed them. |
| TCP connection | `write` handed part of the byte stream to the local stack. | Whether the remote app received the full logical message. |
| Business application | Only an application-protocol response/ACK. | If the ACK is lost, whether the server did or didn't act. |

When an `IOException` occurs:

1. Log **the operation, offset/frame ID, expected size, bytes reported as transferred by prior successful calls**, exception type, and channel state.
2. Mark the request or file as **incomplete or uncertain**; never report success.
3. Check the data kind: a new temporary file can be deleted and rebuilt; an append log needs record framing/checksums; a network request needs an idempotency key or transaction-status query.
4. Define retry budgets, backoff, and deadlines; avoid infinite retries when the device or network is broken.
5. When the committed offset cannot be proven, **never** arbitrarily send only the remaining bytes or resend from the start unless the protocol supports resume or deduplication.

For example, a file import can write to `incoming.tmp` and publish via `ATOMIC_MOVE` after verifying a checksum; consumers never read the temp file. For a log needing every record, use lengths, checksums, and commit markers, trimming an incomplete trailing record during recovery. This is a durability/transaction concern, **not solved by a write loop alone**.

## 8. Minimum Test Matrix to Run

| Test Case | Simulated Schedule | Result to Verify |
| --- | --- | --- |
| Full immediate read | `read -> N` | Exact byte contents and count. |
| Partial read | `read -> 2, 2, 1` | Accumulates all `N` bytes without dropping or reordering. |
| Temporary zero read | `read -> 0, N` | Does not treat `0` as EOF; no CPU spin in production. |
| EOF before `N` bytes | `read -> 2, -1` | Reports truncated frame; does not parse incomplete data. |
| Read error after prefix | `read -> 2, IOException` | Reports error, preserves byte context, does not ACK. |
| Full immediate write | `write -> N` | `hasRemaining == false`, exact bytes. |
| Partial write | `write -> 1, 2, ...` | Loops until buffer is drained; does not call `clear` early. |
| Temporary zero write | `write -> 0, N` | Retains pending bytes, waits for readiness/deadline. |
| Mid-stream write error | `write -> 2, IOException` | Prefix may have been sent; handles uncertain state. |
| Error on first call | `read/write -> IOException` | Does not interpret as EOF; does not retry infinitely. |
| Tiny buffers | Capacity 1, 2, 3 | Preserves `flip`/`clear` state and byte order. |
| Empty / boundary payloads | 0, 1, N-1, N, N+1 | Never accesses buffer past `limit`. |
| Multiple messages | Split or coalesced frames | Parser keeps state; does not assume one read = one message. |
| Client cancel / timeout | Deadline expires mid-I/O | Cleans up, closes, no double-completion. |
| Retry after error | Retry same ID | Idempotency/recoverability without duplicate side effects. |

Use a test double with a **pre-scripted return schedule** (`0, 2, 1, -1, exception`), rather than relying on `Thread.sleep` or live network traffic to hit logic branches. Integration tests should then run against local files, loopback TCP, and target volumes/OSes with realistic network delays and restart simulations.

### Writing Assertions

Do not merely assert "no exception thrown." A solid test suite verifies:

- **Exact content**: compare byte arrays (`Arrays.equals`), not just byte counts.
- **No lost or duplicated bytes**: total bytes written equals payload length upon completion.
- **No hanging loops**: bounded call counts or deadlines; tests must fail explicitly if a channel keeps returning `0`.
- **Buffer state**: `position`, `limit`, and `remaining` match expectations at each step.
- **Error paths**: capture exceptions; never commit or ACK after failure.
- **Resources**: both channels are closed via `try-with-resources` on both success and failure.
- **Re-execution**: on retry, business state is not duplicated and uncommitted vs. committed states are distinguishable.

## 9. Observing and Diagnosing in Production

When issues occur only under load, logs should separate **normal short I/O** from **I/O failures**:

- Operation ID, channel type, and local/remote endpoints or redacted paths.
- Offset and total expected bytes of the file, record, or frame.
- Bytes returned per call; counts of `0` returns and short reads/writes.
- `ByteBuffer.position`/`limit`/`remaining` **before and after successful calls**, noting that buffer state may not safely indicate commit status after an exception depending on the API.
- Readiness wait times, deadlines, pending byte counts, queue depth, and retry counts.
- Exception class, cause, and socket/file lifecycle; never swallow stack traces needed for diagnosis.

Avoid logging full payloads containing tokens, PII, or huge binaries. Log samples or metadata sufficient to reproduce the issue; use record-level checksums when integrity verification is needed.

A brief example of structured diagnostic logging:

```text
op=send-order-142 expected=1024 written=512 remaining=512 result=SHORT_WRITE
op=send-order-142 expected=1024 written=768 remaining=256 result=SHORT_WRITE
op=send-order-142 result=IO_ERROR error=IOException commit=UNKNOWN
```

This is **illustrative synthetic logging**, not stdout from the program above. The `commit=UNKNOWN` field reminds operators that local byte counts cannot prove the peer's business logic took no action.

## 10. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| One `read` equals a full message | TCP and channels can return short reads | Stateful accumulating parser, length framing. |
| One `write` sends the whole buffer | Channels can write partially or return `0` | Check `hasRemaining` and write when ready. |
| Treating `read == 0` as EOF | EOF is `-1` | Handle `0` as no progress yet. |
| Busy-loop `while(write==0)` | Burns 100% CPU when output buffer is full | `Selector`/backpressure/deadlines. |
| Calling `clear` while unwritten bytes remain | Drops unsent bytes | `clear` only after fully consumed; use `compact` if needed. |
| Treating `IOException` as EOF | Errors and normal termination have different semantics | Distinguish exceptions, EOF, and timeouts. |
| Retrying payload from byte 0 after error | Can cause duplicate side effects | Idempotency, resume, or protocol ACKs. |
| Assuming `position()` bytes were committed remotely after error | Local buffer does not measure peer commits | Track state at the protocol level. |
| Tests relying on sleep or flaky networks | Non-deterministic, hard to reproduce | Scripted fake channels and fault injection. |
| Testing only the happy path | Misses partial reads/writes and truncation | Matrix of `0`/short/EOF/error/boundaries. |
| Sharing a buffer object across concurrent operations | Data races and corrupted buffer state | Single owner per buffer until completion. |
| Calling `force` and assuming atomic file transactions | Durability differs from atomicity | WAL, checksums, atomic publication, recovery. |

## 11. Practice Checklist

1. Do you know whether the channel is **blocking or non-blocking**?
2. Have you specified all stop conditions: `N bytes`, `EOF`, deadline, or protocol marker?
3. Have you distinguished `0` from `-1` and `IOException`?
4. Do you preserve `ByteBuffer.remaining()` after a short write?
5. Do you `flip` at the right time after `read` and `clear`/`compact` at the right time after write?
6. Do you cap byte and frame sizes to prevent invalid inputs and OOM?
7. Do retry loops use bounded deadlines/readiness instead of busy-looping?
8. Can your test fixtures deterministically schedule partial I/O + `0` + EOF + `IOException`?
9. Do tests assert **byte contents** and progress counts rather than just console output?
10. After an error, does the application enter an uncertain/recovery/idempotency path instead of sending a false ACK?
11. Are offsets, bytes, and exceptions logged safely, and are resources closed properly across their lifecycle?
12. When using real files or networks, do you have integration tests on target providers and OSes?

## 12. Self-Check Questions

**1. `read(dst)` returns `2` when the buffer has space for 8 bytes—is that an error?** No; short reads are valid behavior.

**2. Does `read(dst)` returning `0` mean EOF?** No. EOF on a readable channel is signaled by `-1`.

**3. If `write(src)` returns `0`, may you call `src.clear()`?** No, because bytes are still pending in the buffer.

**4. Reading a 5-byte frame, 2 bytes arrive followed by `-1`: what is the outcome?** Truncated frame, usually throwing `EOFException`.

**5. After an `IOException` from a network write, can you be sure the server never processed the request?** No; you need application-level acknowledgments or idempotency.

**6. Why are fake channels more useful in unit tests than throttling real network bandwidth?** Because fake channels deterministically control `0` returns, partial counts, EOF, and exceptions, making error branches easy to reproduce.

**7. Should you spin in `while (channel.write(buf) == 0)` on a non-blocking socket?** No; wait for readiness with timeouts to avoid CPU spin.

**8. When a `write` throws `IOException`, is `ByteBuffer.position` guaranteed to equal the bytes committed to disk or peer?** No. Buffer state is not proof of application commit.

## Official Documentation

- [Java SE 21 — ReadableByteChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ReadableByteChannel.html): `read` may return fewer bytes than requested, `0`, or `-1`.
- [Java SE 21 — WritableByteChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/WritableByteChannel.html): `write` may transfer fewer bytes or `0`.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `clear`, `compact`, `position`/`limit`.
- [Java SE 21 — SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking network reads and writes.
- [Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): positional file I/O, `IOException`, `force`.
- [Java SE 21 — Selector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): readiness-based non-blocking I/O.

**Summary:** Never test I/O assuming every read or write transfers everything at once. Proactively simulate **short reads**, **short writes**, `0`, EOF, and mid-stream failures; track `ByteBuffer` boundaries carefully, and design recovery/idempotency when partial data has already been transferred.