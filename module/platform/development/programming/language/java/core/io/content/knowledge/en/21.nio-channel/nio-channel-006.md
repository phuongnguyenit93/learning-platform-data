# NIO Channel: Read/Write Loops Based on `position` and `remaining`

In Java NIO, a single call to `ReadableByteChannel.read(ByteBuffer)` or `WritableByteChannel.write(ByteBuffer)` **does not mean all data has been read or written**. The channel transfers some number of bytes and updates the `ByteBuffer`'s `position`. Therefore, a program must loop based on **`position()`, `limit()`, `remaining()`, and the read/write return value**.

This is the foundation for copying files accurately, transmitting messages over sockets, processing fixed-size records, and designing programs that never lose bytes when I/O returns fewer bytes than requested.

## 1. The Three Most Important Rules

**Rule 1: `read(buffer)` writes into the buffer at its current position.** The method returns the number of bytes read `n`; if `n > 0`, `position` increases by exactly `n`. Never assume every `read` fills the buffer.

**Rule 2: `write(buffer)` reads bytes from the current position up to before `limit`.** The method returns the number of bytes written `n`; if `n > 0`, `position` increases by exactly `n`. Never discard remaining bytes if a single write call did not consume the whole buffer.

**Rule 3: Transition phases properly.** After a channel reads **into** a buffer, call `flip()` to begin consuming the data. After consuming it all, call `clear()` to accept the next batch; or `compact()` if unprocessed data still remains.

The scope of this article covers synchronous channels in `java.nio.channels`, especially `FileChannel` and `SocketChannel`. With non-blocking channels, you must also coordinate with `Selector` when a call returns 0.

## 2. The `position`, `limit`, `capacity`, `remaining` Model

Every `Buffer` tracks:

| Property | Meaning |
| --- | --- |
| `capacity()` | Maximum capacity in **buffer elements**; for `ByteBuffer`, bytes. |
| `limit()` | *Exclusive* boundary of elements allowed for the next read/write. |
| `position()` | Next index for a relative operation, updated by the channel when bytes are transferred. |
| `remaining()` | Number of elements in the actionable region: `limit() - position()`. |
| `hasRemaining()` | `true` when `remaining() > 0`. |

Mandatory invariant:

```text
0 <= position <= limit <= capacity
remaining = limit - position
```

A `ByteBuffer.allocate(8)` has this initial state:

```text
capacity = 8, limit = 8, position = 0, remaining = 8
[ .  .  .  .  .  .  .  . ]
  ^
  next byte written by channel.read(buffer)
```

Suppose `read` returns 3: three bytes are placed in the buffer, `position = 3`. After `flip()`, the state becomes `position = 0, limit = 3, remaining = 3`. If `write` consumes 2 bytes, `position = 2, remaining = 1`: **the last byte still needs to be written**.

```text
After read returns 3:           After flip:                  After write returns 2:
position=3, limit=8             position=0, limit=3          position=2, limit=3
[A  B  C  .  .  .  .  .]       [A  B  C | .  .  .  .  .]     [A  B | C  .  .  .  .  .]
         ^                      ^                                  ^
                              3 bytes pending write            1 byte remaining
```

The right condition to write the remaining portion is `while (buffer.hasRemaining())`, **not** checking `buffer.position() < buffer.capacity()`: `capacity` can be greater than `limit` after `flip()`.

## 3. Understanding `read` and `write` Return Values

With `ReadableByteChannel.read(ByteBuffer dst)`:

- **`n > 0`**: read `n` bytes, advancing `dst.position()` by exactly `n`.
- **`n == 0`**: no bytes were transferred on this call. On a non-blocking `SocketChannel`, this is completely normal when no data has arrived yet; wait for readiness rather than running an unbounded busy loop.
- **`n == -1`**: end of input stream (EOF). No more bytes to read. For a file channel, EOF is the normal stopping point; for a framed protocol, EOF mid-frame can be a truncated-data error.

For `WritableByteChannel.write(ByteBuffer src)`:

- **`n > 0`**: wrote `n` bytes and advanced `src.position()` by that count.
- **`n == 0`**: no bytes transferred. This can happen when a non-blocking channel is not ready to accept writes yet. Retrying immediately in a tight loop burns CPU.
- `write` has no `-1` return value to signal EOF like `read` does. Write failures are expressed through `IOException` or channel state, depending on the type.

If the buffer has no bytes left to write (`!src.hasRemaining()`), there is generally no reason to call `write`. If the destination of `read` is already full (`!dst.hasRemaining()`), consume or switch phases first instead of continuing to read into a buffer with no room.

**Blocking does not mean each call finishes the entire buffer.** A blocking channel may still perform a partial read or partial write; blocking only describes a waiting guarantee of the channel, not a promise that a single call transfers all `remaining()` bytes. Conversely, non-blocking channels often return 0 when not yet ready.

## 4. Proper Write Loop Pattern for Blocking Channels

Once the buffer is in its **read phase** (usually after `flip()`), the basic pattern is:

```java
// Snippet: channel is an open WritableByteChannel;
// buffer holds bytes to send in [position, limit).
while (buffer.hasRemaining()) {
    int n = channel.write(buffer);
    if (n == 0) {
        throw new IOException("Không có tiến triển khi ghi");
    }
}
```

The snippet above assumes `channel` and `buffer` are declared externally and `IOException` is handled. It **intentionally fails fast** if there is no progress, fitting a blocking I/O task where the application chooses to error rather than wait. It is **not a general algorithm for non-blocking channels**, where 0 can be normal; in the non-blocking section below, we wait for the `OP_WRITE` event instead.

Why is the `while` loop needed? Suppose `buffer.remaining() == 10` and the first `write` returns 4. The channel already advanced `position` by 4; 6 bytes remain unsent. Calling `write` again on **that same buffer** starts at the fifth byte. If the program called `clear()` right after the first write, the remaining six bytes would be lost from the application's output stream.

**Do not manually add `n` to `position`** after `write(buffer)`: the channel already did that. Adding it again causes the application to skip bytes. Do not use `buffer.array()` to send in place of `buffer` if you want to respect `position`, `limit`, and support direct buffers.

## 5. Proper Read Loop Pattern for `FileChannel`

When `FileChannel` reads a regular file and data is processed immediately:

```java
// Snippet: channel is a FileChannel opened for READ;
// consume receives data currently in read phase [position, limit).
ByteBuffer buffer = ByteBuffer.allocate(8192);
while (true) {
    int n = channel.read(buffer);
    if (n == -1) {
        break;
    }
    if (n == 0) {
        throw new IOException("Đọc file không có tiến triển");
    }

    buffer.flip();
    consume(buffer);
    buffer.clear();
}
```

This is **illustrative code**, not a standalone program; it assumes `consume` processes **all bytes** in the buffer. If `consume` consumes only part of it because a full frame has not arrived yet, replace `clear()` with `compact()` and manage state as shown in Section 8. When processing ordinary static files, each `read` may return fewer bytes than `capacity`, especially at the end of the file.

The general pattern for reading **at least/exactly N bytes** is tracking how many remain and continuing to call `read`. Never use a single `read` and assume the input already contains all N bytes. With NIO, `ByteBuffer.position()` is a direct indicator of how many bytes have been added since the initial position was set.

## 6. Complete Java 17+ Example: Copying a File and Verifying Every Byte

The example below creates two temporary files, writes `Hello NIO!` to the source file, copies it using `FileChannel` through a buffer of only **4 bytes**, verifies the result, and cleans up the files. The small capacity makes repeated looping obvious; the code also handles the case where a single `write` writes only part of the data.

Save as **`ChannelLoopDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ChannelLoopDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("channel-source-", ".bin");
        Path target = Files.createTempFile("channel-target-", ".bin");

        try {
            Files.writeString(source, "Hello NIO!", StandardCharsets.UTF_8);

            long totalRead = 0;
            long totalWritten = 0;
            ByteBuffer buffer = ByteBuffer.allocate(4);

            try (FileChannel in = FileChannel.open(
                         source, StandardOpenOption.READ);
                 FileChannel out = FileChannel.open(
                         target, StandardOpenOption.WRITE,
                         StandardOpenOption.TRUNCATE_EXISTING)) {

                while (true) {
                    int n = in.read(buffer);
                    if (n == -1) {
                        break;
                    }
                    if (n == 0) {
                        throw new IOException("Không có tiến triển khi đọc");
                    }

                    totalRead += n;
                    buffer.flip(); // position=0, limit=number of bytes just read

                    while (buffer.hasRemaining()) {
                        int written = out.write(buffer);
                        if (written == 0) {
                            throw new IOException("Không có tiến triển khi ghi");
                        }
                        totalWritten += written;
                    }

                    buffer.clear(); // all bytes transferred; ready to read next batch
                }
            }

            System.out.println("read=" + totalRead
                    + " written=" + totalWritten);
            System.out.println("result="
                    + Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("identical="
                    + (Files.mismatch(source, target) == -1));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
        }
    }
}
```

Run:

```bash
javac ChannelLoopDemo.java
java ChannelLoopDemo
```

Stdout:

```text
read=10 written=10
result=Hello NIO!
identical=true
```

**Sequence explanation:**

1. `Files.writeString` creates a 10-byte ASCII payload; the app opens an input `FileChannel` for reading and an output `FileChannel` for writing.
2. `in.read(buffer)` adds from 1 up to 4 bytes at the current position; `totalRead` adds the exact actual count. Do not use `buffer.capacity()` in place of `n`.
3. `buffer.flip()` switches to the **write out to channel** phase: `limit` is set to the old `position` (the number of bytes just read), and `position` resets to 0.
4. `out.write(buffer)` takes bytes from `position` to `limit`; a single call may not empty it, so `while (buffer.hasRemaining())` writes until the buffer is empty.
5. Only when **every byte has been written** is `buffer.clear()` safe: it resets state to position 0, limit capacity to receive the next block.
6. When `read` returns `-1`, the loop stops; both channels are closed. `Files.mismatch(source, target) == -1` confirms both files have identical byte contents, not just matching printed strings.

In this blocking file example, if read/write unexpectedly returns 0, the program throws an explicit error to avoid a busy loop. In real applications, the no-progress policy depends on channel type, deadlines, and I/O wait requirements; never assume a spinning `while` loop is safe for every channel.

## 7. Classic Mistake: Assuming One Write Is Enough

The following buggy code can lose data when the output channel accepts only part of the buffer:

```java
int n = in.read(buffer);
if (n > 0) {
    buffer.flip();
    out.write(buffer); // WRONG: not guaranteed to write all remaining()
    buffer.clear();    // Unwritten bytes may be skipped.
}
```

Fix it as:

```java
int n = in.read(buffer);
if (n > 0) {
    buffer.flip();
    while (buffer.hasRemaining()) {
        int written = out.write(buffer);
        if (written == 0) {
            throw new IOException("Ghi không có tiến triển");
        }
    }
    buffer.clear();
}
```

Both blocks are **snippets with `in`, `out`, `buffer` in scope**, not standalone runnable programs; if not running blocking, adjust the zero-return branch to wait for readiness rather than throwing. When `read` returns `-1`, exit the outer read loop.

A similar mistake occurs when reading once into a buffer and assuming those bytes represent **one complete message**. In protocols over TCP, a `read` may return part of a frame, multiple frames, or zero bytes; TCP is a byte stream and does not preserve message boundaries of individual `write` calls.

## 8. Using `compact()` When a Frame Is Not Fully Consumed

If the buffer contains incomplete data, `clear()` logically discards the unprocessed bytes. Use `compact()` to keep the `[position, limit)` region, shift those bytes to the beginning of the buffer, and prepare to append more bytes.

Example where input consists of fixed **4-byte** records:

```java
// Snippet: buffer is a ByteBuffer in write phase.
// Depending on channel and app, handle n == 0/-1 externally.
buffer.flip();

while (buffer.remaining() >= Integer.BYTES) {
    int value = buffer.getInt(); // Consumes 4 bytes.
    handle(value);
}

buffer.compact(); // Keeps 0..3 bytes that do not yet form a complete int.
```

Once `compact()` finishes, unread data sits at the front of the buffer; `position` equals the number of preserved bytes and `limit` returns to `capacity`. The next `read(buffer)` appends new data **right after the preserved portion**, so the parser never loses a record split across two reads.

A complete loop for fixed records needs additional checks:

- In the read phase, call `getInt()` only when `remaining() >= 4`, avoiding `BufferUnderflowException`.
- If EOF arrives while 1–3 bytes remain unformed into a record, the file/protocol was cut off mid-record; decide clearly whether to throw an error or accept the trailing remainder.
- For length-prefixed frame parsers, validate that length is non-negative, within quota, and all bytes are present before allocating/decoding.
- Buffer capacity must hold at least the minimum header unit to parse, or the parser must track state to gather headers incrementally. If the buffer runs out of space without being able to process an oversized record, expand or stream the payload according to policy.

**`compact()` vs. `clear()`:** `compact` copies unread bytes to the start and adjusts `position`; `clear` only resets state—it does not erase bytes, though it allows the next read to overwrite the old data region.

## 9. Example of EOF While Accumulating a Frame

Suppose a protocol defines each frame as **4 length bytes + N payload bytes**. If `read` returns `-1` before all 4 header bytes arrive or before all N payload bytes arrive, that is an **incomplete frame**, not a valid end of a frame.

It cannot be handled by a single `channel.read(headerBuffer)` call. Sketch for a blocking channel:

```java
// Snippet: channel is a synchronous ReadableByteChannel;
// header is ByteBuffer.allocate(4).
while (header.hasRemaining()) {
    int n = channel.read(header);
    if (n == -1) {
        throw new EOFException("Thiếu dữ liệu header");
    }
    if (n == 0) {
        throw new IOException("Đọc header không có tiến triển");
    }
}
header.flip();
int payloadSize = header.getInt();
if (payloadSize < 0 || payloadSize > 1_048_576) {
    throw new IOException("Payload size không hợp lệ");
}
```

This is a **snippet** requiring `import java.io.EOFException`, `java.io.IOException`, and pre-initialized variables. If EOF happens **before any new header starts**, a protocol may treat it as a clean termination; whereas EOF mid-header/mid-payload must be reported as truncation. Distinguish the two cases using parser state or how many bytes have been collected for the current frame.

Validating `payloadSize` prevents allocating based on a malicious length. For large payloads, design chunked streaming to bound memory rather than forcing every message into one giant buffer.

## 10. Non-Blocking `SocketChannel`: Do Not Spin When Returning 0

After `SocketChannel.configureBlocking(false)`:

- `read(buffer) == 0` means no bytes are currently available to read; return to other work or wait for `SelectionKey.OP_READ` via `Selector`.
- `write(buffer) == 0` means no bytes can currently be sent; keep the buffer and its position intact, and wait for writability with `OP_WRITE`.
- `read(buffer) == -1` means input has ended; handle EOF/half-close and protocol state as designed.
- After reading/writing `n > 0`, both APIs have already advanced `position`. Before reading again, the parser must process newly received data and call `compact()` or `clear()` appropriately.

Sketch for **one outbound buffer**:

```java
// Snippet: socket is a non-blocking SocketChannel,
// pending is a flipped ByteBuffer ready to send.
// Runs when Selector signals writability.
while (pending.hasRemaining()) {
    int n = socket.write(pending);
    if (n == 0) {
        break; // Keep pending intact; wait for the next OP_WRITE.
    }
}
if (!pending.hasRemaining()) {
    // Remove OP_WRITE interest if no outbound data remains.
}
```

This is **illustrative code**, omitting Selector/SelectionKey configuration and message queue management. A real application must retain `pending` across event loop ticks rather than recreating it when writing is incomplete; update interest ops based on backlog to avoid spinning CPU because `OP_WRITE` stays ready whenever the socket can accept writes.

**Never write `while (socket.write(pending) == 0) { }`**: waiting for readiness or timeouts is the event loop's job. In NIO, avoiding busy-spinning is part of operational correctness.

## 11. `FileChannel`: File Position Differs from Buffer Position

Both `FileChannel` and `ByteBuffer` have a `position` concept, yet they are **two separate cursors**:

| Cursor | What Does It Manage? | Example APIs |
| --- | --- | --- |
| `buffer.position()` | Index of the next byte in the buffer. | `buffer.position()`, `flip()`, `clear()` |
| `channel.position()` | Current byte offset in the file. | `FileChannel.position()`, `position(long)` |

When calling the non-offset form `channel.read(buffer)`, `FileChannel` normally updates both the file position by the number of bytes read and the buffer position by the same count. Conversely, positional calls:

```java
int n = channel.read(buffer, 100L);
int m = channel.write(buffer, 200L);
```

are **snippets** applicable to an open `FileChannel` with appropriate permissions. They use the **specified** file position and do not alter the current `channel.position()`, yet they **still update `buffer.position()`** by the actual bytes transferred. Do not confuse not moving the file position with not moving the buffer position.

`FileChannel.transferTo`/`transferFrom` can support efficient data transfer, yet they **can still transfer fewer bytes than requested**; the program still needs to loop, check bytes transferred, and handle `0` appropriately. Do not drop partial I/O checks just because you use a higher-level API.

## 12. Stopping Conditions, Progress, and Total Byte Counts

A reliable I/O loop needs:

1. **Clear goal:** Read to EOF, collect N bytes, send all `remaining()`, or process until the parser has no more complete frames.
2. **Valid stopping condition:** `read == -1` for files, buffer drained of outgoing data, payload length satisfied, or protocol end.
3. **Wait condition:** `read/write == 0` means no progress; non-blocking must await readiness, while blocking needs an appropriate timeout/fail-fast policy.
4. **Exception handling:** `IOException`, closed channels, and malformed payload errors; release resources via `try-with-resources`.
5. **Resource limits:** size, time, frame count, and total byte quotas when processing untrusted input.

If you must read exactly N bytes, use a `long` counter or a buffer with an appropriately set `limit`. Never rely entirely on a single `read` returning `buffer.capacity()` bytes; the final read may return less, and the buffer still holds old data in the unwritten portion.

In real networking, deadlines/timeouts should apply to the **overall operation** rather than just individual read/write calls; this prevents slow peers from dripping one byte at a time to keep connections alive indefinitely. For large files, track totals in a `long` counter to prevent overflow when total bytes exceed `Integer.MAX_VALUE`.

## 13. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Target file is shorter than source | Called `write(buffer)` only once before `clear()`. | Loop `while (hasRemaining())` to write the whole buffer. |
| Target file contains zero bytes or stale bytes | Forgot `flip()` after `read`, or used `capacity` as valid byte count. | Call `flip()` to bound the newly received data region. |
| Infinite loop, high CPU | Channel keeps returning 0, loop has no wait/fail-fast. | Use a no-progress policy for blocking; await Selector for non-blocking. |
| Parser loses part of a message | Called `clear()` while unread bytes remained. | Use `compact()` and accumulate the missing part in the parser. |
| `BufferUnderflowException` | Called `getInt()` before 4 bytes were present. | Check `remaining() >= Integer.BYTES`. |
| `BufferOverflowException` | Read into a full buffer / wrote past limit. | Manage buffer phases and payload quotas. |
| Treating EOF as 0 | Not distinguishing `-1` and `0`. | `-1` ends input; `0` means no bytes transferred yet. |
| Socket drops messages | Assumed one `read` equals one message. | Use framing: fixed-size, delimiter, or length-prefix. |
| Bytes duplicated or lost | Manually added to `buffer.position()` after `channel.write/read`. | Let the channel advance `position`; reset only on intentional phase transitions. |
| Unintentionally reading the same bytes repeatedly | Calling `flip()` or `rewind()` at the wrong time. | Document the state machine and inspect `position`/`limit` before and after. |

One thing to verify during code review is: **does every buffer phase-transition call truly reflect that all data from the previous phase was handled?** In particular, placing `clear()` right after a `write` without a `remaining` loop is a classic sign of data loss.

## 14. Exercises and Self-Check Questions

**Exercise 1 — Simulate partial write.** A buffer holds 10 bytes, `position=0, limit=10`. The channel writes 4, 3, and 3 bytes across successive calls. Write `(position, remaining)` after each step: `(4,6)` → `(7,3)` → `(10,0)`. Explain why `while (hasRemaining())` stops at the right moment.

**Exercise 2 — Copy an arbitrary file.** Change the example to use buffer capacity 7 or 8192 and a source file containing multiple lines of Unicode text. Verify with `Files.mismatch` that the bytes match. Why can't UTF-8 byte length be inferred from `String.length()` alone?

**Exercise 3 — `int` parser with `compact`.** Feed a byte stream containing three big-endian `int` values through read turns returning 3, 2, 4, and 3 bytes. Write the `flip()` → `while (remaining() >= 4) getInt()` → `compact()` loop and trace the remaining bytes after each batch.

**Exercise 4 — EOF mid-frame.** Design `readExactly(channel, buffer)` for a blocking channel with a 4-byte header, distinguishing a clean EOF before a new frame from an unexpected EOF after only 1–3 bytes arrive. Add a no-progress check.

**Exercise 5 — Non-blocking send.** Suppose a socket sends only 2 bytes, then returns 0, and later receives an `OP_WRITE` event. Describe the buffer state that must be preserved between events; why would recreating the buffer from scratch on each event send duplicate data?

**Quick check questions:**

- After `read(buffer)` receives 5 bytes, why must you call `flip()` before writing those bytes out to a channel?
- How does `remaining()` differ from `capacity()` after `flip()`?
- When `write` returns 2 while `remaining = 8`, how many bytes remain unsent?
- When `read == 0`, can you conclude EOF?
- If the parser processed only 4 out of 7 bytes, should you call `clear()` or `compact()`?
- Why can `FileChannel.read(buffer, offset)` leave `channel.position()` unchanged while still changing `buffer.position()`?

**Takeaway:** `position` and `remaining` tell you **how many bytes remain to be processed**; the return value of `read/write` tells you **how many bytes actually moved on this turn**. Combining those two facts with `flip/clear/compact` and explicit policies for `-1`/`0` is the foundation of every correct NIO Channel read/write loop.
