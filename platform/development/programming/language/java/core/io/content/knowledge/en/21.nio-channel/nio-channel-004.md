# Reading or Writing Less Than the Full Buffer in Java NIO Channels

## 1. The Problem: A Single Read/Write Does Not Mean Complete

Java NIO channel APIs transfer bytes via `ByteBuffer`. A call to `read(buffer)` or `write(buffer)` can process **fewer bytes than remain in the buffer**, even when no error occurs. This phenomenon is commonly called a **partial read** or **partial write**.

Example: a buffer has 8 bytes to send, but `channel.write(buffer)` accepts only 3 bytes on the first call. The method returns `3`, leaving 5 bytes unsent. If you discard the buffer or call `clear()` immediately, the application loses data.

~~~text
ByteBuffer before write:
       position=0                    limit=8
            v                            v
         [ A B C D E F G H ]   remaining=8

channel.write(buffer) returns 3:
               position=3             limit=8
                    v                    v
         [ A B C D E F G H ]   remaining=5
              sent ^ ^ ^
                 Bytes D..H are still waiting to be sent.
~~~

The core point is: **the return value** reports how many bytes were actually transferred in that call; the buffer's **`position`** advances accordingly. The program must continue from the remaining position until reaching the completion condition or an event that must be handled such as EOF, temporary unreadiness, timeout, cancellation, or an I/O error.

This topic belongs to the **NIO Channel** family and is not limited to file reading: it matters most with `SocketChannel` in non-blocking mode, yet you must also respect the API contract when working with `FileChannel`, `ReadableByteChannel`, `WritableByteChannel`, and custom channels.

## 2. Read and Write Contracts

### 2.1. Reading from a ReadableByteChannel into a ByteBuffer

With `int n = channel.read(dst)`:

| Result | Meaning | How to Handle |
| --- | --- | --- |
| `n > 0` | Exactly `n` bytes were copied into `dst`; `position` increases by `n`. | Process what was received; continue reading if the message is still incomplete. |
| `n == 0` | No bytes were transferred on this call. | Do not infer EOF; with non-blocking channels, wait for a readiness signal or reschedule. |
| `n == -1` | Channel signals **end-of-stream (EOF)**: no more bytes will arrive. | If expecting a fixed-size message and not enough bytes arrived, report incomplete/truncated; if reading a stream to EOF, finish cleanly. |
| Throws `IOException` | An I/O error occurred. | Handle/close resources per application contract. |

`read(dst)` can read at most `dst.remaining()` bytes. When `dst.remaining() == 0`, the call has no room to receive bytes and should not be used to probe data availability. Even when the buffer has room, there is **no guarantee** a read will fill all available space.

With a `SocketChannel` in **blocking mode**, if the buffer has space, the method normally waits until at least one byte is read, EOF is encountered, or an error occurs, though that does not mean waiting to fill the entire buffer. In **non-blocking mode**, `read` can return `0` when the socket currently has no data.

### 2.2. Writing from a ByteBuffer to a WritableByteChannel

With `int n = channel.write(src)`:

| Result | Meaning | How to Handle |
| --- | --- | --- |
| `n > 0` | Exactly `n` bytes were consumed from `src`; `position` increases by `n`. | If `src.hasRemaining()`, continue sending. |
| `n == 0` | No bytes could be written this time. | If non-blocking, wait for the channel to become writable; avoid spinning in a tight loop making no progress. |
| Throws `IOException` | Data transmission or write error. | Choose controlled retry, failure handling, or closing the connection per business rules. |

**There is no standard `-1` return value for `write` to indicate EOF.** Using `-1` is characteristic of read operations. Even when `write` returns a positive number, that means bytes were accepted by the channel per its contract; do not automatically infer the data is durably persisted on disk or that the remote peer has received/processed the whole message.

For example, `WritableByteChannel.write` is also allowed to write fewer than `src.remaining()` bytes. On sockets, the amount written also depends on network buffer state. On files, bytes written may vary by provider, environment, or I/O errors. **Do not write code assuming `channel.write` always writes everything.**

## 3. How Does ByteBuffer Track I/O Progress?

Relative operations on a buffer rely on three values:

~~~text
0 <= position <= limit <= capacity
remaining() == limit - position
hasRemaining() == (remaining() > 0)
~~~

- With `read(dst)`, the channel **puts data into the buffer** at the current position and advances `position` by the bytes received.
- With `write(src)`, the channel **takes data from the buffer** starting at the current position and advances `position` by the bytes taken.
- `limit` is the exclusive boundary; `capacity` is the physical/logical capacity of the buffer. A channel does not automatically know which bytes are “valid” data just written by the application unless the application sets the buffer state properly.

Common workflow:

~~~text
Reading from a channel into a buffer:
  clear or compact  -> read(...) -> flip() -> process -> clear/compact

Writing existing data out to a channel:
  put(...) -> flip() -> write(...) -> if remaining > 0 keep to finish writing
~~~

**`flip()`** switches the buffer from being written into to being read from: it sets `limit` to the old `position`, then sets `position=0`. **`clear()`** sets `position=0, limit=capacity` to prepare for overwriting with new data; it does not actually erase bytes. **`compact()`** moves unread bytes to the start and prepares for further writes into the buffer, making it useful when a message is incomplete or a socket write consumed only part of it.

Do not call `flip()` repeatedly on a buffer **waiting to finish writing**: after a partial write, the buffer is already in read mode and `position` points right at the next byte. Calling `flip()` again alters the read window, easily causing data to be repeated or lost.

## 4. Reading a Fixed Number of Bytes Completely

Suppose a protocol specifies that each header is exactly 4 bytes long. **One `read(header)` call is not enough**, because it might receive only 1, 2, or 3 bytes. For a blocking channel where the application expects each read to be able to make progress, you can loop on `hasRemaining()`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ReadableByteChannel;

static void readFullyBlocking(ReadableByteChannel channel, ByteBuffer dst)
        throws IOException {
    while (dst.hasRemaining()) {
        int count = channel.read(dst);

        if (count == -1) {
            throw new EOFException("Đã hết luồng trước khi nhận đủ byte");
        }
        if (count == 0) {
            throw new IOException("Không có tiến triển; kiểm tra mode/channel");
        }
    }
}
~~~

This is **a utility method**, not a standalone runnable Java program. It is written for **blocking cases where progress is expected**, and should not be used verbatim as a non-blocking loop or for providers that can legitimately return `0` repeatedly.

Usage example once `channel` and byte order are established:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
readFullyBlocking(channel, header);

header.flip();
int payloadLength = header.getInt();
~~~

If `readFullyBlocking` does not throw, `header` holds all 4 bytes. Calling `flip` sets the limit to the received region before `getInt`. The number `payloadLength` is just an integer read from data: **you must validate it** (non-negative, not exceeding maximum size, not causing overflow or excessive allocation) before using it as the next buffer size.

### 4.1. Reading Exactly N Bytes vs. Reading Until EOF

There are two distinct goals:

- **Reading exactly N bytes:** finishes once N bytes are received; encountering `-1` beforehand means a truncated message.
- **Reading the entire stream until EOF:** receives arbitrary chunks; `-1` can be a completely valid termination.

If reading a file just to total bytes or copy to a target without needing a known size upfront, process buffer chunks until EOF. If the data has framing (length-prefixed, delimiter, fixed-size record), you must perform an additional framing/assembly step; boundaries between `read` calls are **not** message boundaries.

### 4.2. Reading a File Buffer by Buffer

A loop form usable with `FileChannel`:

~~~java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(4096);

    while (true) {
        int n = channel.read(buffer);
        if (n == -1) {
            break;
        }
        if (n == 0) {
            continue; // Fits this blocking file example context.
        }

        buffer.flip();
        while (buffer.hasRemaining()) {
            byte b = buffer.get();
            // Process byte b, e.g. update checksum.
        }
        buffer.clear();
    }
}
~~~

This is an **illustrative snippet**, requiring `java.nio.ByteBuffer`, `java.nio.channels.FileChannel`, `java.nio.file.Path`, `java.nio.file.StandardOpenOption`, and `IOException` handling. This approach assumes every byte in the buffer is processed each pass; when an incomplete frame tail must be preserved, use `compact()` or an appropriate data accumulator.

The `continue` when `n==0` is shown in the context of this **blocking `FileChannel`** example; do not copy it into a non-blocking `SocketChannel`, as it can cause busy-spinning.

## 5. Writing All Data in a Buffer

For a **blocking** channel expected to make write progress, the basic pattern is:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.WritableByteChannel;

static void writeFullyBlocking(WritableByteChannel channel, ByteBuffer src)
        throws IOException {
    while (src.hasRemaining()) {
        int count = channel.write(src);

        if (count == 0) {
            throw new IOException("Không có tiến triển; kiểm tra mode/channel");
        }
    }
}
~~~

Assume the buffer was placed in read state before calling (e.g., `flip()` after `put`):

~~~java
ByteBuffer outgoing = ByteBuffer.wrap(
        "PING".getBytes(java.nio.charset.StandardCharsets.US_ASCII));
writeFullyBlocking(channel, outgoing);
~~~

**Why not call `clear` between writes?** After the first write, `src.position()` has already advanced automatically by the number of bytes consumed by the channel. `src.hasRemaining()` tells you what remains to be sent; repeating `write(src)` resumes right from the unfinished portion.

If the application wants to reuse a buffer after writing **everything**, only then call `clear()` to add new data. If a socket accepted only part of the data and the application needs to append extra data at the end, `compact()` can keep the unsent portion and switch back to write state for appending; byte ordering must be carefully controlled when doing so.

### 5.1. FileChannel and File Output

`FileChannel.write(buffer)` updates the buffer's position by the number of bytes written. The `while (buffer.hasRemaining())` loop remains the right way to express transferring **the entire remaining data region** to the file.

Note the distinction between:

1. Data accepted by `write` through the API.
2. Data flushed by the operating system down to the storage device.

If durability is required, consult the `FileChannel.force(boolean metaData)` contract. That call concerns data synchronization, does **not** replace the partial-write loop, and you should not assume all providers/hardware offer identical guarantees.

## 6. Non-Blocking SocketChannel: 0 Can Be a Normal State

When `SocketChannel.configureBlocking(false)`, a `read` or `write` call may return `0` even though the connection is still open and the buffer still has space/data. The usual reason is that the socket is **not ready at that moment**. A loop calling it repeatedly without waiting burns CPU:

~~~java
// Do NOT do this with a non-blocking channel.
while (out.hasRemaining()) {
    socket.write(out); // May keep returning 0 -> busy-spin.
}
~~~

With a NIO selector, the approach is to **keep the buffer state and wait for the appropriate event**:

- On `OP_READ`, read whatever is available and process the returned byte count; if `read == 0`, stop the current read pass.
- When data is waiting to be written, register `OP_WRITE` and try writing the remaining bytes. If `write == 0`, keep `position/limit` and wait for the next `OP_WRITE` turn.
- Once the write buffer has no `remaining()`, clear `OP_WRITE` interest until more data needs sending; leaving `OP_WRITE` registered continuously causes an almost always writable socket to wake the event loop unnecessarily.
- When `read == -1`, the peer has signaled end-of-read; process any leftover data and connection-closing state per the protocol (for TCP, there is also the concept of half-close).

Short pseudocode illustrating handling one socket ready for writing:

~~~java
// out is in read state, containing data to send.
// key, socket belong to the application's event loop.
if (key.isWritable()) {
    socket.write(out); // May send 0, part, or all.
    if (!out.hasRemaining()) {
        key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
        out.clear(); // Only reuse when no bytes remain to be sent.
    }
}
~~~

This is **pseudocode for integrating into an event loop**, not a standalone runnable program; you need buffer queue management, locks/ownership, and proper deregistration. In applications with multiple queued messages, you typically store **one or more partially sent buffers** rather than a single shared buffer.

**Readiness does not guarantee byte count:** an `OP_READ` signal does not mean an entire frame is available; `OP_WRITE` does not mean all bytes can be sent at once. The selector only notifies you that attempting the operation is possible; actual bytes transferred still come from `read`/`write`.

## 7. Runnable Java 17+ Example: Intentionally Limiting Each Read and Write

To demonstrate partial I/O reliably, this example **does not rely on disk or network luck**. It implements two small channels based on the standard interfaces:

- `ChunkedReadableChannel` intentionally yields **at most 2 bytes** per `read` call.
- `ChunkedWritableChannel` intentionally accepts **at most 3 bytes** per `write` call.

The source data is the ASCII string `HELLO-NIO`, which is 9 bytes. Thus it takes exactly **5 data-bearing reads** (2+2+2+2+1) and **3 writes** (3+3+3).

Save the file `PartialChannelDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.ReadableByteChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;

public class PartialChannelDemo {

    static final class ChunkedReadableChannel implements ReadableByteChannel {
        private final ByteBuffer source;
        private boolean open = true;
        private int calls;

        ChunkedReadableChannel(byte[] bytes) {
            this.source = ByteBuffer.wrap(bytes);
        }

        @Override
        public int read(ByteBuffer dst) throws IOException {
            if (!open) {
                throw new ClosedChannelException();
            }
            if (!dst.hasRemaining()) {
                return 0;
            }
            if (!source.hasRemaining()) {
                return -1;
            }

            int n = Math.min(2, Math.min(dst.remaining(), source.remaining()));
            for (int i = 0; i < n; i++) {
                dst.put(source.get());
            }
            calls++;
            return n;
        }

        int calls() {
            return calls;
        }

        @Override
        public boolean isOpen() {
            return open;
        }

        @Override
        public void close() {
            open = false;
        }
    }

    static final class ChunkedWritableChannel implements WritableByteChannel {
        private final ByteArrayOutputStream output = new ByteArrayOutputStream();
        private boolean open = true;
        private int calls;

        @Override
        public int write(ByteBuffer src) throws IOException {
            if (!open) {
                throw new ClosedChannelException();
            }
            if (!src.hasRemaining()) {
                return 0;
            }

            int n = Math.min(3, src.remaining());
            byte[] batch = new byte[n];
            src.get(batch);
            output.write(batch);
            calls++;
            return n;
        }

        int calls() {
            return calls;
        }

        String text() {
            return output.toString(StandardCharsets.UTF_8);
        }

        @Override
        public boolean isOpen() {
            return open;
        }

        @Override
        public void close() {
            open = false;
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] payload = "HELLO-NIO".getBytes(StandardCharsets.US_ASCII);
        ByteBuffer buffer = ByteBuffer.allocate(payload.length);

        try (ChunkedReadableChannel reader = new ChunkedReadableChannel(payload);
             ChunkedWritableChannel writer = new ChunkedWritableChannel()) {

            // Read all 9 bytes: each read returns at most 2 bytes.
            while (buffer.hasRemaining()) {
                int n = reader.read(buffer);
                if (n == -1) {
                    throw new EOFException("Payload bị thiếu");
                }
                if (n == 0) {
                    throw new IOException("Read không tiến triển");
                }
            }

            System.out.println("readCalls=" + reader.calls());
            System.out.println("readPosition=" + buffer.position());

            buffer.flip();
            System.out.println("writeRemainingBefore=" + buffer.remaining());

            // Write all 9 bytes: each write accepts at most 3 bytes.
            while (buffer.hasRemaining()) {
                int n = writer.write(buffer);
                if (n == 0) {
                    throw new IOException("Write không tiến triển");
                }
            }

            System.out.println("writeCalls=" + writer.calls());
            System.out.println("writeRemainingAfter=" + buffer.remaining());
            System.out.println("output=" + writer.text());
        }
    }
}
~~~

Compile and run:

~~~bash
javac PartialChannelDemo.java
java PartialChannelDemo
~~~

**Exact stdout of the program:**

~~~text
readCalls=5
readPosition=9
writeRemainingBefore=9
writeCalls=3
writeRemainingAfter=0
output=HELLO-NIO
~~~

Result explanation:

1. Initially the buffer has `capacity=9`, `position=0`, and `limit=9`.
2. The reader delivers only 2 bytes per turn (1 byte on the final turn), so it takes exactly 5 turns to reach `position=9`.
3. `flip()` switches the buffer to read mode: `position=0`, `limit=9`, `remaining=9`.
4. The writer consumes 3 bytes per turn; after 3 writes, `position=9` and `remaining=0`.
5. `output=HELLO-NIO` proves no bytes were lost or duplicated even though every I/O call transferred only part of the payload.

The two custom channels exist solely to **demonstrate the contract reproducibly**. They always make progress while data remains and do not simulate non-blocking networking, selectors, timeouts, or remote errors. The `n==0` checks intentionally treat zero progress as abnormal in this verification-oriented blocking example.

## 8. When a Frame Is Incomplete: Keeping Partial Bytes

Network data is a **byte stream**, so one message may be split across multiple `read` calls; conversely, one `read` may receive several consecutive messages. If the protocol uses **fixed-length or framed messages**, the decoder must retain the incomplete bytes until the next pass.

Example of a frame starting with a 4-byte big-endian length followed by `length` bytes of payload:

~~~text
On the wire:
[ 00 00 00 05 ][ H E L L O ]
   length=5       payload

Read pass #1: [ 00 00 00 ]                -> incomplete header
Read pass #2: [ 05 H E ]                  -> complete header, incomplete payload
Read pass #3: [ L L O ]                   -> payload complete
~~~

If the parser discards the three header bytes received on the first pass or decodes the payload before it is complete, the result will be wrong. There are two typical strategies:

1. **State machine + read buffer:** keep state such as “reading header” or “reading payload”, transitioning only when the corresponding part is complete. With blocking channels you can use `readFullyBlocking`; with non-blocking channels preserve state between readable events.
2. **Accumulation buffer + `compact()`:** after `flip()`, the parser consumes complete frames, leaving any incomplete trailing bytes behind; `compact()` retains them so the next `read` appends right after them.

Non-blocking read loop outline:

~~~java
int n = socket.read(input);  // input is in write mode.
if (n == -1) {
    handleEndOfStream();    // Distinguish clean EOF from truncated frame.
} else if (n > 0) {
    input.flip();
    parseAllCompleteFrames(input); // Extract only complete frames.
    input.compact();               // Keep remaining bytes.
}
~~~

`handleEndOfStream` and `parseAllCompleteFrames` are **application-defined functions**, not Java APIs; the code must also handle the case where the buffer fills up without decoding any frame (e.g., growing the buffer within allowed limits or rejecting oversized frames).

### Dangerous Bug: Allocating Based on Unvalidated Length

When receiving a length from the network, validate it before allocating or sizing a buffer. Four length bytes can decode via `getInt()` into a negative number or a huge number. Capping frame sizes, managing backpressure, timeouts, and limiting connections holding buffers are essential parts of sound I/O design.

## 9. Scattering/Gathering and Other APIs Still Have Partial I/O

Some channels provide multi-buffer read/write operations:

~~~java
long n = scatteringChannel.read(new ByteBuffer[] {header, body});
long m = gatheringChannel.write(new ByteBuffer[] {prefix, payload});
~~~

This is an **illustrative snippet**: `scatteringChannel` supports `ScatteringByteChannel`, `gatheringChannel` supports `GatheringByteChannel`, and the buffers are properly prepared. `n` and `m` are **total bytes transferred**, not the number of buffers processed. The channel may fill only part of the first buffer or write only part of the payload; you still need to check each buffer's `position/remaining`.

Similarly, APIs such as `FileChannel.transferTo(...)` and `transferFrom(...)` return **actual bytes transferred**; do not assume one call moves the entire requested `count`. With `AsynchronousByteChannel`, the completion result from `Future` or `CompletionHandler` must likewise be interpreted as a byte count, without automatically inferring the entire message is done.

A message successfully sent over I/O may still require an *application-level acknowledgment* if the application needs proof that the peer received and processed it, beyond the semantics of `write()`.

## 10. Distinguishing Termination Conditions

To control loops safely, you must first define the **true completion condition**.

| Goal | Success Condition | Condition to Handle |
| --- | --- | --- |
| Read exactly `N` bytes | `dst` contains all `N` bytes; `remaining()==0`. | `read==-1` before completion ⇒ EOF/truncated. |
| Read all bytes until EOF | Received chunks processed; then `read==-1`. | `read==0` is not EOF. |
| Write an entire `ByteBuffer` | `src.hasRemaining()==false`. | `write==0` requires waiting/resuming per mode. |
| Write a multi-buffer frame | All buffers have no `remaining()`, in order. | Partial write on any buffer. |
| Non-blocking socket | Complete per application state and event loop. | `0`/readiness, backpressure, timeouts, connection close. |

In production, never let “read until full” run indefinitely on untrusted input. Enforce size limits, deadlines, or protocol timeouts; using `SocketChannel` and `Selector` does not automatically provide application-level timeout/cancellation policies.

## 11. Common Mistakes and Fixes

### Forgetting to Loop After Write

~~~java
out.flip();
socket.write(out);  // May write only part of it.
out.clear();        // WRONG if unsent bytes remain!
~~~

The right approach for a blocking channel capable of making progress is to continue sending until `!out.hasRemaining()`. For a non-blocking socket, keep `out` in a write queue and register `OP_WRITE` to send the rest when ready.

### Using `remaining()` at the Wrong Time

If a buffer was just **read into** by a channel and `position` sits at the end of the data, `remaining()` at that moment tells you **free space left for more writing into the buffer**, not how many new bytes were read. Only after `flip()` does `remaining()` represent the newly received bytes ready for the application to read out.

### Calling `clear()` on a Buffer That Still Holds Data

`clear()` resets logical state, which can cause unconsumed data to be overwritten on the next read. If only part of a frame was parsed, use `compact()` to preserve the remainder.

### Calling `flip()` Twice in a Send Sequence

Calling `flip()` between two `write` calls after a partial write changes `limit` to the post-first-write position and resets `position` to 0, risking re-sending already sent bytes. After a partial write, leave the buffer state intact and continue writing.

### Mistaking `0` for End of Stream

A non-blocking socket returning `0` usually only means *no progress right now*, not disconnection. The EOF condition for `read` is `-1`. Conversely, a loop retrying immediately on `0` wastes CPU.

### Assuming One TCP Read Equals One Message

TCP does not preserve sender `write` boundaries. One message may arrive in multiple fragments; multiple messages may also arrive coalesced in a single `read`. You need a framing protocol (length prefix, delimiter, fixed structure, etc.) and a parser that handles partial data.

### Ignoring Character Encoding

A UTF-8 character can span multiple bytes and be split across two reads. Do not call `new String(chunk, UTF_8)` independently on arbitrary chunks when processing **a continuous text stream**: characters straddling chunk boundaries can decode incorrectly. Use a stateful `CharsetDecoder` with leftover bytes, or accumulate a complete text unit/frame before decoding.

### Confusing Channel Progress with Business Success

`write` returning a positive number only indicates bytes accepted by the channel; in networking, that is not an application-level ACK. If you need guarantees like “the order was processed” or “the message was durably saved”, require explicit confirmation at the appropriate layer.

## 12. Practice Check

1. A buffer has `position=3` and `limit=12`. What is `remaining()`? **9 bytes** if it is a `ByteBuffer`. A single `write` call may accept fewer than 9 bytes.
2. `write(buffer)` returns `4` when `position=3` beforehand. What is the new position? **7**, assuming no other buffer operations intervene.
3. Non-blocking `read(buffer)` returns `0`. Can you conclude the peer closed the connection? **No.** You must wait for readiness or the next condition; `-1` signals EOF.
4. Reading a 4-byte header, the first call reads only 2 bytes. What should you do? **Keep the 2 bytes in the buffer and keep reading** until 4 bytes arrive or EOF/error occurs.
5. While sending 10 bytes, the first write succeeds with 6 bytes; is the next call `flip()` or `write(buffer)`? **`write(buffer)` again**, keeping the buffer state intact with `remaining()==4`.
6. After the parser consumes 7 bytes out of 10 received, what should you call to receive more into the same buffer? **`compact()`**, to preserve the 3 unprocessed bytes.
7. Why might the same payload take 1 read on one machine and 5 reads on another? **The API only returns the actual bytes transferred per call**, depending on provider, data arrival timing, buffering, and runtime conditions.
8. Does `write` having sent the entire buffer prove the peer finished processing it? **No.** If processing confirmation is required, the protocol must provide an explicit application acknowledgment.
9. `ScatteringByteChannel.read(buffers)` returns `long n`. Is `n` the number of buffers filled? **No.** It is the total number of bytes read.
10. How should you prevent a program from reading unboundedly from a malicious client? **Enforce frame limits, deadlines/timeouts, buffer capacity bounds, and connection cancellation/closing mechanisms** per the protocol.

**Takeaway:** Java NIO Channels report **actual bytes transferred per call**; the buffer tracks progress via `position`. To avoid losing or duplicating data, read/write according to `remaining()`, preserve state after partial I/O, distinguish `0` from `-1`, and pair event-waiting mechanisms appropriate for blocking or non-blocking mode.
