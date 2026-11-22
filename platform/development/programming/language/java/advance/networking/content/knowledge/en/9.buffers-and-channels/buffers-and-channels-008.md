# Partial Reads or Writes in Java NIO; Distinguishing 0 from End-of-Stream

## 1. Context and Goals

In Java NIO, a call to `SocketChannel.read(ByteBuffer)` or `SocketChannel.write(ByteBuffer)` does not mean an entire **application message** has been processed. TCP provides an **ordered byte stream**; it does not preserve boundaries between `write()` calls, has no built-in knowledge of headers/payloads, and does not guarantee that a single `read()` returns the exact number of bytes sent in a single `write()`.

This lesson focuses on two vital rules:

1. **Reads can be partial.** For `ReadableByteChannel.read(ByteBuffer)`, a **positive** result is the number of bytes transferred, **`0`** means no bytes were transferred in that call, and **`-1`** is **EOF** (end of the input stream).
2. **Writes can be partial.** For `WritableByteChannel.write(ByteBuffer)`, the result is the **number of bytes actually written**, which can be `0` if writing is not yet possible. The unwritten portion remains in the `ByteBuffer`; the write side **does not use `-1` to signal EOF**.

After studying this, you will know how to read/write via `SocketChannel`, use `ByteBuffer.position/limit/flip/compact`, handle a frame split into multiple chunks, distinguish traditional stream I/O from NIO, use `Selector` instead of busy-spinning, and handle a connection closing mid-frame. The Java 17+ example uses `Pipe` to produce **reproducibly verifiable** cases of 0, partial transfer, and EOF, rather than relying on lucky network timing.

## 2. Three Types of Read Results: Positive, 0, -1

`ReadableByteChannel.read(ByteBuffer dst)` and `SocketChannel.read(dst)` return an `int`. Meaning:

| Value | What happened? | Action |
| --- | --- | --- |
| `n > 0` | Read exactly **n bytes** into the buffer; `position` advances by n | Parse the newly arrived bytes or read more if the frame is incomplete |
| `n == 0` | No bytes transferred **in this call** | Check if the buffer still has space; in non-blocking mode, wait for readiness |
| `n == -1` | The source has reached **end-of-stream** | Check for an incomplete frame, close/half-close according to the protocol |

When the channel is in **non-blocking mode**, `0` usually means data is **not ready at that moment**. Another cause: `dst.remaining() == 0` (the buffer is full), so the call cannot accept more bytes even if the socket has data. Therefore, `0` **does not prove the peer has no more data**, nor does it prove there is no traffic on the network.

One TCP endpoint can send 5 bytes and then close its sending side. The receiver might observe:

~~~text
Data sent: 11 22 33 44 55

Valid receive sequence 1:
read -> 5 bytes
read -> -1

Valid receive sequence 2:
read -> 2 bytes
read -> 0 bytes (non-blocking, no new bytes yet)
read -> 3 bytes
read -> -1

Valid receive sequence 3:
read -> 1 byte
read -> 1 byte
read -> 3 bytes
read -> -1
~~~

**`-1` only appears after all bytes received in the stream have been consumed** and the source has closed its sending side. If a TCP reset/connection error occurs, Java may throw `IOException` instead of returning `-1`. If the destination buffer has no space left, even after the peer has sent FIN, a read into a full buffer can return `0`; you must free up space before checking for EOF.

### 2.1. 0 Bytes Transferred Is Different from a Byte with Value 0

Do not confuse the **number of bytes** with the **data byte value**:

~~~text
On the wire there is a byte 00 (numeric value 0).
SocketChannel.read(dst) -> 1  (put 1 byte into dst)
dst.get()               -> 0  (the data byte just received)

No data available right now:
SocketChannel.read(dst) -> 0  (no bytes transferred)

End of input:
SocketChannel.read(dst) -> -1
~~~

A data value of 0 is completely valid in a binary protocol. Do not stop receiving just because a byte in the buffer is `0x00`.

### 2.2. Can a Blocking Channel Perform Partial Reads?

Yes. In blocking mode, `SocketChannel.read(dst)` normally waits until there is **at least one byte** if the buffer has space, or EOF/error; there is no guarantee it will wait to **fill the entire buffer**. For example, if a 4-byte header is needed, read can return `1`, `2`, or `4`. Therefore, even in blocking mode, the application needs a read loop to gather enough bytes when the protocol requires N bytes.

In non-blocking mode, `0` is common even when the buffer has space. Check `channel.isBlocking()` when choosing the loop and timeout mechanism. Do not use a tight spin loop waiting for `read()>0` on a non-blocking channel.

## 3. Distinguishing InputStream from Channel

In Java networking, legacy code may use `Socket.getInputStream()`, while NIO uses `SocketChannel`. The two APIs have **different return contracts across overloads**.

| API | Returns | Case 0 | EOF |
| --- | --- | --- | --- |
| `InputStream.read()` | **Byte value** 0..255 | **A valid `0x00` byte** | `-1` |
| `InputStream.read(byte[],off,len)` | **Number of bytes read** | For `len==0` returns 0; for `len>0`, standard blocking streams normally wait for data/EOF/error | `-1` |
| `ReadableByteChannel.read(ByteBuffer)` | **Number of bytes read** | No bytes transferred; can be due to non-blocking or full buffer | `-1` |
| `SocketChannel.read(ByteBuffer)` | **Number of bytes read** | No progress on that call | `-1` |
| `WritableByteChannel.write(ByteBuffer)` | **Number of bytes written** | No bytes written yet | No `-1` sentinel for writing |
| `OutputStream.write(byte[])` | `void` | No count returned | Succeeds or throws an exception |

Typical mistake:

~~~java
// WRONG for no-arg InputStream.read():
int value = input.read();
if (value == 0) {
    return; // Will give up when encountering a valid 0x00 byte!
}

// CORRECT:
int value2 = input.read();
if (value2 == -1) {
    // EOF.
} else {
    // Actual byte with value 0..255, including 0.
}
~~~

These two snippets illustrate code inside a method with an `InputStream` variable `input` that declares/handles `IOException`. When handling binary streams, avoid mixing API types and assuming "`0` always means EOF".

In addition, `InputStream.available() == 0` **does not prove EOF** and does not tell you the total message size. It only reports an estimate of the number of bytes that can be read immediately without blocking according to the stream type's contract. For TCP protocols, you must use **framing** or actual EOF, not `available()` to decide whether "the message is complete".

## 4. Partial Writes: write Returns the Number of Bytes Consumed

`SocketChannel.write(ByteBuffer src)` may write **fewer** bytes than `src.remaining()`. It updates `src`'s `position` by the number of bytes taken, so the next call starts at the exact **unsent** portion.

~~~text
Source ByteBuffer:
position=0, limit=1000, remaining=1000

Write 1 -> 300:
position=300, remaining=700

Write 2 -> 0 (non-blocking, send buffer cannot accept more yet):
position=300, remaining=700

After writable event:
Write 3 -> 700:
position=1000, remaining=0
~~~

Do not call `src.flip()` again after each partial write: it resets `position` to 0 and can cause you to **re-send bytes that were already sent**. Do not call `src.clear()` while `hasRemaining()==true`, because that loses the unsent offset state. Only when the buffer has no remaining bytes or has been copied to preserve the remainder should you intentionally reuse it.

### 4.1. Write-All Loop Pattern for a Blocking SocketChannel

~~~java
// Illustrative helper method, not a standalone file.
// Requires importing java.io.*, java.nio.*, java.nio.channels.*.
static void writeAllBlocking(SocketChannel channel, ByteBuffer source)
        throws IOException {

    if (!channel.isBlocking()) {
        throw new IllegalArgumentException(
                "Non-blocking channel requires readiness handling");
    }

    while (source.hasRemaining()) {
        int written = channel.write(source);
        if (written == 0) {
            // For a blocking socket with remaining data in the buffer,
            // do not loop infinitely in an abnormal situation.
            throw new IOException("Write made no progress");
        }
    }
}
~~~

With a blocking `SocketChannel` and a non-empty buffer, `write` normally waits until it can write at least a portion; the loop above handles the case where it returns a positive byte count that is not yet everything. A write returning a positive number only means the data was accepted by the channel for sending to the network stack; it does **not** prove the remote server has read or processed it.

With a **non-blocking** channel, `write()==0` is normal. Instead of throwing an error or spinning, **keep the buffer in an outbound queue, register `OP_WRITE` while data is pending, and try again when the channel is writable**.

### 4.2. `write()` Does Not Return -1 Like read

A closed channel, broken output, or unconnected state is normally signaled by an appropriate **exception** such as `ClosedChannelException`, `NotYetConnectedException`, or `IOException`. Never write `if (channel.write(buf) == -1) ...` expecting it to report EOF. The write contract has no `-1` sentinel.

A peer may have closed its receiving side without the sender knowing immediately; the success of a `write` call does not guarantee the other side received everything. When the system detects the error, a subsequent call may throw an exception. The application protocol needs an ACK/response to confirm processing, rather than relying on the count from `write`.

## 5. ByteBuffer: position, limit, and Remaining State

`ByteBuffer` is a **stateful** byte buffer. Key properties to know:

- `capacity()`: total number of bytes the buffer can hold.
- `position()`: index of the next byte for a `put/get` operation or channel `read/write`.
- `limit()`: current bound; operations cannot go past it.
- `remaining() == limit - position`: number of bytes remaining in the active window.
- `hasRemaining()`: checks whether space remains (when receiving bytes) or data remains (when sending bytes), depending on the **phase**.

Two important phases:

1. **Filling/putting:** transferring bytes from the network into the buffer or `put`ting data; `position` advances toward the end.
2. **Draining/getting:** after `flip()`, the buffer is ready for the parser or for `channel.write()` to consume.

### 5.1. Flipping at the Right Time

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[]{10, 20, 30, 40, 50});
// position = 5, limit = 8; in the buffer-writing phase.

buffer.flip();
// position = 0, limit = 5; in the phase of reading 5 bytes.

byte first = buffer.get(); // first == 10
// position = 1, remaining = 4.
~~~

`flip()` **does not erase bytes**; it only sets `limit` to the old position and resets position to 0. To send these 5 bytes over a `SocketChannel`, call `write(buffer)` and keep the buffer untouched between partial writes.

### 5.2. Compacting to Preserve Unread Frame Portions

When receiving data:

~~~text
buffer after read from channel:
[ frame A header ][ payload A ][ first 2 bytes of frame B ][ free space ]

buffer.flip()
  parser consumes frame A, leaving the first 2 bytes of frame B.

buffer.compact()
  moves the 2 partial bytes to the beginning, position=2, limit=capacity.
  The next read appends bytes after those two bytes.
~~~

`compact()` is essential when a single `read` contains multiple frames and the last frame has only partially arrived. If you call `clear()` right after parsing frame A, the two already-received bytes of frame B are treated as disposable data, corrupting the protocol alignment. `clear()` only resets pointers and does not erase physical contents, but it loses track of the old bytes.

### 5.3. Full Buffer and read Returning 0

If `position==limit` on the destination buffer, `read(dst)` has nowhere to place bytes and can return `0` even when the socket has bytes or the peer has sent FIN. That is an **application-side reason for reading 0**, not proof that the endpoint has sent nothing.

Whenever you see `read()==0`, always consider:

- Does the buffer still have `remaining()>0`?
- Is the channel blocking or non-blocking?
- Are we waiting for readiness properly?
- Has the parser consumed data and called `compact()` to make room?
- Is the frame larger than the allocated/buffer limit?

You should not grow memory indefinitely just because a buffer is full; enforce a **max frame size** and reject invalid input.

## 6. A Java 17+ Example with Deterministic Results: 0, partial, -1

Over TCP, you cannot assume that two `write` calls by the sender will be read by the server in exactly two `read` calls. To test byte counts and EOF independently, the following program uses `java.nio.channels.Pipe`: a non-blocking source and a blocking sink. We **deliberately constrain ByteBuffer.limit()** to produce two writes of 2+3 bytes, two reads of 2+3 bytes, then attempt a read before EOF and after closing the write end.

`Pipe` is an internal one-way byte stream, not a TCP socket; however, its return values and ByteBuffer positions belong to the same NIO API family, making it ideal for **precisely demonstrating** how to distinguish read 0 from -1.

Create the file **PartialChannelDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.util.Arrays;

public class PartialChannelDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);

            ByteBuffer received = ByteBuffer.allocate(8);
            System.out.println(
                    "read(empty) = " + source.read(received));

            ByteBuffer sending = ByteBuffer.wrap(
                    new byte[]{10, 20, 30, 40, 50});

            sending.limit(2);
            int sent1 = sink.write(sending);
            sending.limit(5);
            int sent2 = sink.write(sending);
            System.out.println(
                    "sent = " + sent1 + " + " + sent2);

            received.limit(2);
            int first = source.read(received);
            received.limit(5);
            int second = source.read(received);
            System.out.println(
                    "read = " + first + " + " + second);

            received.limit(received.capacity());
            System.out.println(
                    "read(no new data) = " + source.read(received));

            sink.close();
            System.out.println(
                    "read(EOF) = " + source.read(received));

            received.flip();
            byte[] bytes = new byte[received.remaining()];
            received.get(bytes);
            System.out.println(
                    "bytes = " + Arrays.toString(bytes));
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 PartialChannelDemo.java
java PartialChannelDemo
~~~

Exact stdout on a successful run:

~~~text
read(empty) = 0
sent = 2 + 3
read = 2 + 3
read(no new data) = 0
read(EOF) = -1
bytes = [10, 20, 30, 40, 50]
~~~

**Step-by-step walkthrough of the output:**

1. The non-blocking source has no data yet; `source.read(received)` returns **0**. The sink is still open; there is no EOF.
2. Write with a limit of 2 bytes, then raise the limit to 5 bytes. `sending.position` advances automatically by the number of bytes written; result is 2+3.
3. Read with a limit of 2 bytes, then raise to 5. Correspondingly reads 2+3; this is **deliberate** splitting via limit to construct the test, not a property that "TCP splits into 2 and 3 every time".
4. Expand `received`'s limit to its full capacity so there is **room to read**. The sink is still open, but there are no new bytes; result is **0**.
5. Close the sink after all sent bytes have been read; `source.read` gets **-1**, true EOF.
6. `received.flip()` prepares to retrieve the 5 read bytes, printing the array `[10, 20, 30, 40, 50]`.

Try removing `sink.close()`: the last read with no bytes will normally return 0, not EOF. Try removing `received.limit(received.capacity())`: the buffer would already be full up to its current limit, and `read` would return 0 **due to no space left**. Omitting `received.flip()` before `get` would cause the parser to read the wrong valid data range.

The program needs neither Internet access nor a network port to test channel semantics. Over a real TCP connection, the return value structure is the same, but the number of bytes in each read/write depends on the network, OS, channel mode, and peer progress.

## 7. TCP Framing: Insufficient Bytes Is Not a Complete Message

A common binary protocol precedes the payload with a 4-byte integer describing its length:

~~~text
+---------------------------+--------------------------+
| length (int32 big-endian) | payload: length bytes    |
| fixed 4 bytes             | 0 <= length <= 65,536    |
+---------------------------+--------------------------+

Sending ASCII string "ABC":
00 00 00 03 | 41 42 43
header      | payload
~~~

The 4-byte header can be delivered by TCP as 1+3, 2+2, or 4 bytes at once. The same applies to the payload. **Do not call `ByteBuffer.getInt()` before having four valid bytes**; if only two bytes are present, you will get `BufferUnderflowException`.

### 7.1. Blocking SocketChannel: Reading All N Bytes

An illustrative method specifically for a **blocking `SocketChannel`**:

~~~java
// Requires importing java.io.*, java.nio.*, java.nio.channels.*.
static void readFullyBlocking(SocketChannel channel, ByteBuffer target)
        throws IOException {
    if (!channel.isBlocking()) {
        throw new IllegalArgumentException(
                "Use a Selector/readiness loop for non-blocking mode");
    }

    while (target.hasRemaining()) {
        int n = channel.read(target);
        if (n == -1) {
            throw new EOFException("Peer ended stream mid-frame");
        }
        if (n == 0) {
            // Guard: do not spin infinitely when the buffer still has space.
            throw new IOException("Read made no progress");
        }
    }
}
~~~

This is a **helper method**, not a standalone `main`. With a blocking channel and space remaining in the buffer, read will normally wait for bytes/EOF/error; the loop handles the case where the first read only receives 1–3 bytes. Do not use this method with non-blocking channels: `0` in non-blocking mode is a signal to wait for readiness, not an automatic error.

Using the helper to read a frame:

~~~java
// Place in the same class as readFullyBlocking; illustrative snippet.
static ByteBuffer readFrameBlocking(SocketChannel channel)
        throws IOException {
    ByteBuffer header = ByteBuffer.allocate(4)
            .order(ByteOrder.BIG_ENDIAN);

    readFullyBlocking(channel, header);
    header.flip();
    int length = header.getInt();

    if (length < 0 || length > 65_536) {
        throw new IOException("Invalid frame length: " + length);
    }

    ByteBuffer payload = ByteBuffer.allocate(length);
    readFullyBlocking(channel, payload);
    payload.flip();
    return payload;
}
~~~

**Length 0** can be a **valid empty frame** if the protocol allows it. That is known only from **four valid header bytes**, not from a `read()==0` call. If the peer sends 3/4 header bytes and then EOF, that is a **truncated header**. If it sends the full header but an incomplete payload followed by EOF, that is a **truncated payload**.

Subtlety: the `readFullyBlocking` helper currently treats EOF while requesting 4 new bytes as an `EOFException`. In a server receiving **multiple frames on the same connection**, EOF **right at the boundary before a new frame** may be a normal termination; distinguish this with a stateful parser rather than reporting a data error for every boundary EOF.

### 7.2. Blocking SocketChannel: Sending the Full Header and Payload

~~~java
static void writeFrameBlocking(SocketChannel channel, ByteBuffer payload)
        throws IOException {
    int length = payload.remaining();
    if (length > 65_536) {
        throw new IllegalArgumentException("Payload too large");
    }

    ByteBuffer header = ByteBuffer.allocate(4)
            .order(ByteOrder.BIG_ENDIAN);
    header.putInt(length).flip();

    writeAllBlocking(channel, header);
    writeAllBlocking(channel, payload);
}
~~~

The snippet above uses the `writeAllBlocking` helper from section 4 and is **additional illustrative code**, not a standalone program. `payload` must be in the read/ready-to-write-to-network phase. `writeAllBlocking` will advance position up to limit; if you want to keep the buffer for another task, use `duplicate()` or an intentional copy.

If a write fails after sending only part of the payload, the peer may already be holding the header and half a frame. Do not naively resend **the entire frame from the beginning** on the same TCP stream: that can cause the remote parser to mistake the resent bytes for the tail of the old frame. You need an application-layer retry/ACK convention, or close the connection and open a new session.

## 8. Non-blocking SocketChannel and Selector: Handling Result 0

### 8.1. Do Not Busy-Spin When There Is No Progress

Here is a **wrong** example:

~~~java
// WRONG: non-blocking read can return 0 forever, causing 100% CPU.
while (target.hasRemaining()) {
    channel.read(target);
}
~~~

The loop does not check for `-1`; on EOF with a non-full buffer, it can also run forever. Even if you add `if (n == 0) continue`, it still busy-spins. Non-blocking I/O works best when paired with a **readiness/event loop**.

Proper model:

1. `channel.configureBlocking(false)`.
2. `channel.register(selector, SelectionKey.OP_READ, connectionState)`.
3. `selector.select(...)` waits for events instead of spinning continuously.
4. `key.isReadable()`: call read; if n>0, parse; if n==0, keep state; if n==-1, handle EOF.
5. When there is an outbound queue, add `SelectionKey.OP_WRITE` to `interestOps`.
6. `key.isWritable()`: call write until the buffer is empty or `n==0`, then return control to the event loop.
7. When outbound data is exhausted, **disable OP_WRITE** to avoid a continuous readiness loop.

### 8.2. Event Handler Pseudocode with the Correct Mechanism

~~~java
// Java PSEUDOCODE: not a standalone program.
// in/out are per-connection ByteBuffers;
// closeConnection() and parseCompleteFrames() are implemented by the application.
if (key.isReadable()) {
    if (!in.hasRemaining()) {
        throw new IOException("Inbound buffer full");
    }

    int n = channel.read(in);
    if (n == -1) {
        closeConnection();  // Or half-close according to the protocol.
    } else if (n > 0) {
        in.flip();
        parseCompleteFrames(in);
        in.compact();
    } else {
        // n == 0: not EOF, do not reset buffer.
        // Return to Selector and wait for the next event.
    }
}

if (key.isValid() && key.isWritable()) {
    while (out.hasRemaining()) {
        int n = channel.write(out);
        if (n == 0) {
            break; // Do not spin; wait for the next OP_WRITE.
        }
    }

    if (!out.hasRemaining()) {
        key.interestOps(
                key.interestOps() & ~SelectionKey.OP_WRITE);
    }
}
~~~

This is only **illustrative logic**; `parseCompleteFrames`, `closeConnection`, key lifecycle, multi-frame queuing, and event loop errors need separate implementation. The takeaway is **preserving state when getting a 0 result**, and updating OP_WRITE according to the actual data that needs sending.

**Why must OP_WRITE be turned off when there is no more data?** A socket is usually writable almost all the time if the send buffer is not full. Leaving OP_WRITE registered continuously can cause `select()` to wake up nonstop and burn CPU while there is nothing to send. When the outbound queue gets more bytes, re-enable OP_WRITE and call `selector.wakeup()` if another thread modified the interest set or produced new data.

Readiness does not guarantee that every subsequent call will have n>0, because state can change or the buffer may be out of space. Returning 0 is not necessarily an error; return to the select loop and track deadlines and metrics.

### 8.3. Do Not Equate Timeout with read 0

A non-blocking `SocketChannel` returns 0 **immediately** when no bytes are available: it does not mean it waited for a timeout. `Selector.select(timeoutMs)` can wait with a time bound, but a single select timeout is also **not** the overall deadline for a message if the code loops over multiple events. The application must track its own deadline, for example using `System.nanoTime()`, and check remaining time.

`Socket.setSoTimeout()` is typically used to bound blocking `InputStream.read` on traditional sockets; do not assume setting SO_TIMEOUT will turn a non-blocking `SocketChannel.read(ByteBuffer)` into a read that waits for N milliseconds. NIO's mechanism is readiness + application-managed deadlines.

## 9. Stateful Parser When a Frame Is Split into Multiple Chunks

For a length-prefixed protocol, a simple state machine:

~~~text
WAIT_HEADER:
  keep received bytes until 4 bytes are available
  decode length; check 0 <= length <= MAX_FRAME
  if length == 0: complete empty frame
  if length > 0: transition to WAIT_PAYLOAD

WAIT_PAYLOAD:
  accumulate exactly length payload bytes
  when complete: process frame, return to WAIT_HEADER

on read(n > 0):
  append n bytes and parse as many frames as possible

on read(n == 0):
  preserve state and incomplete bytes, wait for readiness

on read(n == -1):
  if at frame boundary: valid EOF per protocol
  if holding partial header/payload: truncated frame
~~~

A single read can receive **multiple consecutive frames** or only half a frame. The parser must consume as many complete frames as possible, then retain the leading bytes of the last frame to process when more arrive. For an inbound ByteBuffer, the common cycle is:

~~~text
channel.read(in)        -> receive bytes at the end of buffer [write mode]
in.flip()               -> bound the valid byte region [read mode]
parseCompleteFrames(in) -> consume complete frames
in.compact()            -> keep unparsed bytes and open space for new reads
~~~

Be careful that `compact` preserves unread data. If the parser cannot proceed because the buffer is full while a large frame is still incomplete, you must **limit/validate length and allocate buffers in a controlled way**, rather than repeatedly calling read on a full buffer and getting 0 infinitely.

### 9.1. Why Must Mid-Frame EOF Not Be Swallowed?

Suppose we read a header with length=100 and only received 70 payload bytes, then the peer closes its sending side. If the next call returns `read()==-1`, that frame **was truncated**. A correct server must report a protocol error or close the session, not hand over the 70 bytes as a complete payload. If all 100 bytes were read and EOF arrived at the new frame boundary, the session can end normally.

Similarly, if the header is 4 bytes and the peer sends 2 bytes then EOF, do not call `getInt()` and do not interpret the 2 missing bytes as length 0.

### 9.2. Half-Close and EOF

In TCP, a peer can call `shutdownOutput()`, ending its **sending side** without closing the other direction. The receiver reads all buffered bytes and then hits `-1`, but depending on the protocol it may still send a response on its own write side. `-1` on `read` means **input EOF**, not just "no data yet"; nor does it necessarily mean all write operations immediately become invalid.

If the connection is reset or encounters an abnormal I/O error, Java may throw `IOException` instead of returning -1. Do not swallow errors as normal EOF: they have important differences for retries, diagnostics, and data reconciliation.

## 10. Backpressure and Memory When Writes Stall

A peer reading very slowly can cause non-blocking `write()==0` because the OS send buffer cannot accept more data. Meanwhile, the application keeps generating new frames. If you keep pushing frames into an unbounded queue, memory can grow until the heap is exhausted.

A safe design should include:

- **Per-connection outbound queue**, storing `ByteBuffer`s and remaining offsets.
- **Limit total unsent bytes** and queued frame count; reject or slow down the producer if the threshold is exceeded.
- Enable `OP_WRITE` only when the queue is non-empty, and disable it when no pending bytes remain.
- **Write-progress timeout**: if the channel stays unwritable or the peer stops reading for too long, close the session per policy.
- **Do not let multiple threads interleave writes of frames.** A single writer/event loop owning the socket is an easily controlled structure.
- **Metrics**: pending bytes, write-0 count, time spent waiting for writable, sessions closed due to overload.

Similarly, if the inbound buffer is full and the parser cannot consume fast enough, you need to temporarily pause `OP_READ` or bound frames/sessions according to application capacity, rather than looping `read` endlessly and accepting `0`.

A `write` returning a positive number means the bytes were accepted by the channel/OS layer; it does **not** confirm the remote application processed them. For messages with side effects, application-level acknowledgment and idempotency matter more than how many bytes the writer counted.

## 11. Common Mistakes Table

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking `SocketChannel.read()==0` is EOF | 0 means no bytes transferred; can be non-blocking/no room | Keep connection, use readiness, manage buffer |
| Thinking `InputStream.read()==0` means no bytes | 0 is a valid `0x00` byte | `-1` is EOF for InputStream.read() |
| Calling `read` once and assuming it is a full frame | TCP does not preserve message boundaries | Accumulate full header/payload |
| Reading 2 bytes then calling `ByteBuffer.getInt()` | Not enough for 4 valid bytes | Check `remaining()>=4` |
| Looping `while(read()==0)` | Busy-spinning spikes CPU | Selector + readiness/deadline |
| Partial `write` then calling `flip` on source | Can re-send bytes | Preserve position and remaining |
| `write()==0` then clearing the buffer | Loses unsent payload | Keep in queue, wait for OP_WRITE |
| Always registering OP_WRITE | Socket is usually writable, waking the loop nonstop | Disable when outbound queue is empty |
| Calling read on a full destination buffer | Returns 0 due to no space | Parse/compact/grow within bounds or reject |
| Calling `clear()` with a partial frame left | Loses incomplete bytes | `flip`, parse, `compact` |
| Confusing a 0-length frame with read 0 | One is a protocol value, the other is an I/O count | Only determine length after full header |
| Processing payload after mid-frame EOF | Frame is truncated | Report error and close/handle per protocol |
| Using `available()==0` to detect EOF | Not an end-of-stream indicator | Read and check `-1` |
| Assuming write returning -1 means closed output | No -1 in the write API | Catch IOException/closed-channel |
| Retrying send from the start after partial write | Peer may have received the first part | Resume from offset or reset per protocol |
| Measuring only byte counts without timeouts | Peer can stop sending and hold the session | Deadline, read/write progress timeout |

## 12. Self-Check Exercises

### Exercise 1: 0, 5, -1

A non-blocking `SocketChannel` returns `0`, then `5`, then `-1` across three `read` calls. What does this mean?

**Answer:** no progress on the first call; received exactly 5 bytes on the second; reached input EOF on the third. Do not close on the first call just for getting 0. Before closing on the last call, the parser must check whether the 5 bytes form a complete frame or not.

### Exercise 2: Buffer has 100 bytes, write returns 60 then 0

**Answer:** 60 bytes were handed to the channel; `position` advanced by 60, leaving 40 bytes. The `write==0` call sent no more bytes and does not prove the peer closed. Keep the buffer as is, wait for readiness, and write the remaining 40 bytes from the current offset.

### Exercise 3: InputStream receives byte 0 then 255

`input.read()` returns `0`, then `255`, then `-1`.

**Answer:** the two valid bytes are `0x00` and `0xFF`; only `-1` is EOF. Do not compare against 0 to decide the end of an InputStream.

### Exercise 4: Header 00 00 00 00

A parser receives all four header bytes `00 00 00 00`, i.e., length 0, but an earlier `read` returned 0. 

**Answer:** length 0 is a **protocol data value**, which can be a valid empty-payload frame; read 0 only indicates that a call transferred no bytes. Do not conclude frame length=0 from a channel's return value.

### Exercise 5: Mid-header EOF

Received 3/4 header bytes, and the next call returns -1.

**Answer:** truncated frame. Do not decode incomplete bytes, and do not keep waiting on an EOF stream. Propagate a contextual error and clean up the socket.

### Exercise 6: Full buffer

`dst.position()==dst.limit()==dst.capacity()` yet read returns 0.

**Answer:** the direct cause may be that the buffer has no space left. Need to parse/flip/compact, or check the frame size limit. Do not infer that the socket is out of data.

### Exercise 7: OP_WRITE causing high CPU

The event loop always registers `OP_WRITE` even when no frames are queued.

**Answer:** the socket is normally writable, so the selector wakes up continuously. Enable OP_WRITE only when there are pending bytes, and disable it as soon as everything is sent.

### Exercise 8: Sent twice, received once

The sender calls write with a 2-byte buffer and a 3-byte buffer; the receiver reads all 5 bytes in one shot.

**Answer:** completely normal. TCP only preserves byte order, not the number of write calls. You must use framing instead of counting network chunks.

## 13. SocketChannel Implementation Checklist

- [ ] Distinguish APIs that return **byte values** from APIs that return **byte counts**?
- [ ] Treat read `-1` as EOF, and do not automatically treat read `0` as EOF?
- [ ] On write `0`, do not discard unsent buffers and do not busy-spin?
- [ ] When n>0, preserve the `ByteBuffer.position` updated by the channel?
- [ ] Do not `flip/clear` after every partial write?
- [ ] For inbound data, use `flip -> parse -> compact` to keep incomplete data?
- [ ] Every frame has a clearly defined header/payload, max length, and memory limit?
- [ ] Mid-frame EOF is treated as truncated; boundary EOF is handled per protocol?
- [ ] Blocking channels read/write fully when needed; non-blocking uses `Selector` and readiness?
- [ ] OP_WRITE is enabled only when the outbound queue has bytes, with queue limits and timeouts?
- [ ] Full buffers are handled rather than repeatedly calling read and getting 0?
- [ ] Test 1+3, 2+2, all-at-once, read 0, write 0, and EOF mid-header and mid-payload?

**Conclusion:** `0` in NIO's byte-count read/write operations only means **the call transferred no bytes**; `-1` on read is **end-of-stream**. Partial reads and writes are normal behavior for buffers/channels, especially with TCP and non-blocking I/O. For a program to be correct, you must **preserve buffer state**, **wait for readiness instead of busy-spinning**, and **process a message only when all bytes according to framing have arrived**.