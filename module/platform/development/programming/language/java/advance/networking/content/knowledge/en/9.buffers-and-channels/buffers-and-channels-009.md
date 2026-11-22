# Scattering read, gathering write, and combining header with payload

## 1. The problem: sending header and payload on a single channel

In Java NIO, a TCP message typically consists of a **header** (such as length, message type) and a **payload** (the actual content). There are two ways to prepare data for sending:

- **Physical concatenation:** allocate a large `ByteBuffer`, `put` the header and payload into it, and then call `channel.write(buffer)`.
- **Gathering write:** keep the header and payload in **separate `ByteBuffer`s**, and pass a `ByteBuffer[]` array to `channel.write(...)` so the channel consumes their bytes **in exact order**.

On the receiving side, **scattering read** allows `channel.read(ByteBuffer[])` to distribute bytes from the channel into multiple destination buffers **in order**: the first buffer first, then the subsequent buffers. Each `ByteBuffer` has its own `position` and `limit`.

Example of a binary frame:

```text
Protocol: [4-byte length L][1-byte type][L-1 bytes UTF-8 payload]

Example sending "HELLO", type=1:
    length = 6    (1 byte type + 5 bytes text)
    header = 00 00 00 06
    type   = 01
    text   = 48 45 4C 4C 4F

   ByteBuffer header       ByteBuffer type       ByteBuffer payload
   +------------------+    +--------------+      +--------------------+
   | 00 00 00 06      |    | 01           |      | H E L L O          |
   +--------+---------+    +------+-------+      +--------+-----------+
            |                     |                       |
            +---------------------+-----------------------+
                                  |
                                  v
                channel.write(new ByteBuffer[] {
                    header, typeBuffer, payload
                })
                                  |
                                  v
                 TCP byte stream: 00 00 00 06 01 H E L L O
                                  |
                                  v
                  read header first to know L
                                  |
                                  v
                  read(new ByteBuffer[] {
                      typeBuffer, payloadBuffer
                  })
```

**Important distinction:** gathering/scattering is a **vectored I/O** technique that saves the application from manually merging/splitting every byte into an intermediate array. It does **not** turn TCP into a message-bounded protocol, does not guarantee that one `write` becomes one network packet, and does not guarantee that one `read` returns a complete frame.

## 2. Two core Java NIO interfaces

Related APIs:

| API | Meaning |
| --- | --- |
| `GatheringByteChannel.write(ByteBuffer[] srcs)` | Writes remaining data from multiple source buffers to the channel in array order |
| `GatheringByteChannel.write(ByteBuffer[] srcs, int offset, int length)` | Considers only a slice of **`length` elements** in the buffer array, starting at element `offset` |
| `ScatteringByteChannel.read(ByteBuffer[] dsts)` | Reads into multiple destination buffers in array order |
| `ScatteringByteChannel.read(ByteBuffer[] dsts, int offset, int length)` | Considers only a subarray of the **buffer array**, not a byte offset within a single buffer |
| `SocketChannel` | TCP channel capable of both scattering read and gathering write |
| `FileChannel` | File channel also supports reading/writing across multiple buffers; this technique is not exclusive to networking |

For the overloads taking a **`ByteBuffer[]` array**, the returned number of bytes read/written is `long` (unlike single-`ByteBuffer` overloads which typically return `int`).

**Ordering rules:**

- Scattering read: bytes are written into the first buffer **until its `remaining()` space is exhausted**, then into the second buffer, and so on. If a read operation returns early, some trailing buffers may not have received any bytes yet.
- Gathering write: bytes are taken from the `remaining()` region of the first buffer, then from subsequent buffers. If a write only writes a partial amount, the `position` of the buffers shows what remains.
- Both only process bytes within each buffer's `position .. limit` range; `capacity` alone does not determine the number of bytes transferred.

The API documentation does not promise "reading all buffers in a single call". If a complete frame is needed, the application **must loop** and check `hasRemaining()`.

## 3. `ByteBuffer` determines which bytes are sent and how much space remains to receive

A `ByteBuffer` has three key markers:

- `capacity`: the fixed capacity of the buffer.
- `position`: points to the **next read/write** index.
- `limit`: the boundary of the usable region in the current state; indices from `limit` onward cannot be accessed via relative operations.

The number of bytes available for the next operation = **`remaining() = limit - position`**.

### 3.1. Header before sending

```java
ByteBuffer header = ByteBuffer.allocate(4);
header.putInt(6);   // position: 0 -> 4; limit=4
header.flip();      // position=0, limit=4; ready to write
```

`ByteBuffer` uses **big-endian** by default, which matches the network byte order convention in this frame. You can explicitly write `header.order(ByteOrder.BIG_ENDIAN)` to make the specification explicit. If the two sides do not agree on byte order, the header length may be read as a huge number.

### 3.2. Payload before sending

```java
byte[] encoded = "HELLO".getBytes(StandardCharsets.UTF_8);
ByteBuffer payload = ByteBuffer.wrap(encoded);
// position=0, limit=5, remaining=5
```

`ByteBuffer.wrap(...)` does not copy the `encoded` array: the buffer shares storage with that array. Do not modify the array or reuse the buffer prematurely while a write has not yet consumed all the data.

### 3.3. Receiver buffers

```java
ByteBuffer typeBuffer = ByteBuffer.allocate(1);
ByteBuffer bodyBuffer = ByteBuffer.allocate(5);
// Both in write mode: position=0, limit=capacity.

// After the channel has read enough:
typeBuffer.flip();
bodyBuffer.flip();
// Both switch to read mode for the newly received data.
```

Call `flip()` **after writing/receiving is complete** in order to read. If you forget to `flip()` the header after `putInt`, `remaining()==0` and the gathering write may fail to send the four header bytes. If you call `flip()` too early before the server has received enough data, the rest of the frame may be read/decoded incorrectly.

## 4. Complete Java 17+ program: TCP loopback, separate header and payload

This program creates a TCP server/client on loopback within a single JVM. The protocol specifies:

- The first four bytes are a signed 32-bit **big-endian** integer `L`, representing the **total number of bytes after the header**, consisting of one `type` byte and the UTF-8 bytes of `text`.
- `1 <= L <= 1024`; the frame has a one-byte message type.
- The client sends `type=1`, text `HELLO`. The server replies with `type=2`, text `OK`.
- When **sending**, each side uses **a gathering write with an array of header, type, payload** (looping until fully written).
- When **receiving**, each side reads the **4-byte header first**, validates the length, and then uses a **scattering read into two buffers, type and payload**, allocated to the exact sizes. Do not guess the payload length before reading the header.
- The code uses **blocking `SocketChannel`**; if an error or EOF occurs mid-frame, the receive method reports an error rather than treating it as a valid frame.

**File `ScatterGatherFrameDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.GatheringByteChannel;
import java.nio.channels.ScatteringByteChannel;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ScatterGatherFrameDemo {
    private static final int MAX_FRAME_BYTES = 1024;

    record Frame(int type, String text) {}

    private static boolean hasRemaining(ByteBuffer[] buffers) {
        for (ByteBuffer b : buffers) {
            if (b.hasRemaining()) return true;
        }
        return false;
    }

    private static void writeFully(GatheringByteChannel channel,
            ByteBuffer... buffers) throws IOException {
        while (hasRemaining(buffers)) {
            long written = channel.write(buffers);
            if (written <= 0) {
                throw new IOException("No write progress on blocking channel");
            }
        }
    }

    private static void readFully(ScatteringByteChannel channel,
            ByteBuffer... buffers) throws IOException {
        while (hasRemaining(buffers)) {
            long count = channel.read(buffers);
            if (count == -1) {
                throw new EOFException("Peer closed during a frame");
            }
            if (count == 0) {
                throw new IOException("No read progress on blocking channel");
            }
        }
    }

    private static void sendFrame(GatheringByteChannel channel,
            int type, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (type < 0 || type > 255 ||
                bytes.length + 1 > MAX_FRAME_BYTES) {
            throw new IllegalArgumentException("Invalid outgoing frame");
        }
        ByteBuffer header = ByteBuffer.allocate(4);
        header.putInt(1 + bytes.length);
        header.flip();
        ByteBuffer typePart = ByteBuffer.wrap(new byte[] {(byte) type});
        ByteBuffer payload = ByteBuffer.wrap(bytes);
        writeFully(channel, header, typePart, payload);
    }

    private static Frame receiveFrame(ScatteringByteChannel channel)
            throws IOException {
        ByteBuffer header = ByteBuffer.allocate(4);
        readFully(channel, header);
        header.flip();
        int bytesAfterHeader = header.getInt();
        if (bytesAfterHeader < 1 || bytesAfterHeader > MAX_FRAME_BYTES) {
            throw new IOException("Invalid frame length");
        }

        ByteBuffer typePart = ByteBuffer.allocate(1);
        ByteBuffer payload = ByteBuffer.allocate(bytesAfterHeader - 1);
        readFully(channel, typePart, payload);
        typePart.flip();
        payload.flip();
        return new Frame(Byte.toUnsignedInt(typePart.get()),
                StandardCharsets.UTF_8.decode(payload).toString());
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<Frame> server = executor.submit(() -> {
                    try (SocketChannel peer = listener.accept()) {
                        Frame request = receiveFrame(peer);
                        sendFrame(peer, 2, "OK");
                        return request;
                    }
                });

                try (SocketChannel client =
                             SocketChannel.open(listener.getLocalAddress())) {
                    sendFrame(client, 1, "HELLO");
                    Frame reply = receiveFrame(client);
                    Frame request = server.get(5, TimeUnit.SECONDS);
                    System.out.println("server: type=" + request.type()
                            + ", text=" + request.text());
                    System.out.println("client: type=" + reply.type()
                            + ", text=" + reply.text());
                }
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
```

Commands to run (Java 17+):

```bash
javac --release 17 ScatterGatherFrameDemo.java
java ScatterGatherFrameDemo
```

Stdout on a successful run:

```text
server: type=1, text=HELLO
client: type=2, text=OK
```

**Interpreting the output:** the server receives the exact frame `type=1`, payload `HELLO`; the client receives the reply frame `type=2`, payload `OK`. These are **application-layer** messages, not an indication that a single gathering write call automatically creates one TCP packet or TCP ACK.

The code is written for a **blocking channel** and a small loopback demo. It throws `IOException` when an operation makes no progress (returns 0) to avoid an infinite loop in this context; **do not copy this branch as-is into non-blocking mode**, because 0 is a normal result when an I/O operation is not yet ready. The demo also does not set deadlines on all socket operations; production code needs appropriate timeout, cancellation, and error-handling policies.

## 5. Logically combining header and body without copying into a large buffer

With the protocol in the example, when sending the text `HELLO`:

```java
// Code snippet (header/type/body created as in sendFrame).
ByteBuffer[] parts = { header, typePart, payload };
long written = channel.write(parts);
```

Separate buffers can hold data from different sources:

- The header can be created by `ByteBuffer.allocate(4)` in the encode method.
- The type can be a 1-byte buffer or part of a fixed header.
- The payload can be a `ByteBuffer.wrap(bytes)` from a byte array, a `slice()` from another backing region, or a direct buffer.
- The `parts` array only holds **buffer references** and their order; it does not concatenate the byte arrays into a new array.

In a simpler header/body structure (without `type`), you can write:

```java
ByteBuffer header = ByteBuffer.allocate(4);
header.putInt(payload.remaining()); // length in remaining BYTES
header.flip();

ByteBuffer[] parts = { header, payload };
while (header.hasRemaining() || payload.hasRemaining()) {
    long n = channel.write(parts);
    if (n <= 0) {
        throw new IOException("No write progress on blocking channel");
    }
}
```

*This is a code snippet inside a method that has `channel`, `payload`, and `IOException` handling, with the channel in **blocking mode**.* If `payload` has already been read/written so that its `position` changed, `payload.remaining()` is only the number of **unused** bytes from the current position. When computing the frame size, make sure it points to the exact region you intend to send.

**Gathering does not mean "zero-copy from application to NIC".** It avoids the **manual copy step to merge header/body in the JVM**, while the JVM, OS, and TCP stack may still copy or process buffers depending on the implementation. There is also no guarantee of producing **exactly one** system call or one TCP segment for every `ByteBuffer[]` array.

## 6. Scattering read: reading into multiple buffers in order

In the demo code, the receiver must know the body size **after reading the header**:

```text
Step A:
  channel.read([header: capacity 4])
  loop until header has all 4 bytes
  header.flip()
  L = header.getInt()
  validate 1 <= L <= 1024

Step B:
  typePart = ByteBuffer.allocate(1)
  payload  = ByteBuffer.allocate(L - 1)
  channel.read([typePart, payload])
  loop until both buffers have enough bytes
  typePart.flip(), payload.flip()
  decode frame
```

If the client sends 3 bytes of the header and then slows down, a single `channel.read(header)` may return 3 and `header.hasRemaining()` remains `true`. If the remaining bytes never arrive, `read` may keep waiting in blocking mode, or report EOF/error if the connection is closed/broken.

**Dangerous mistake:** pre-allocating `ByteBuffer payload = ByteBuffer.allocate(MAX_BODY)`, calling `read(new ByteBuffer[]{header, payload})`, and only then inspecting `L`. On a long-lived TCP connection, if the actual payload is shorter than `MAX_BODY`, the extra space in the buffer can **swallow bytes belonging to the next frame**. The decoder will then misalign the boundary between the two messages.

You can scattering-read both header and body in a single call **when the sizes of the parts are known in advance**, such as a fixed record with a 4-byte header + 32-byte body. However, with **a dynamic length specified by the header**, you usually need to **read and validate the header first, and only then allocate the appropriate body buffers**. That is still a real use case for scattering read on the body/type parts following the header.

Another concrete case: a protocol defines a fixed frame `[4 bytes sequence][8 bytes data]`. You can create:

```java
ByteBuffer sequence = ByteBuffer.allocate(4);
ByteBuffer data = ByteBuffer.allocate(8);
ByteBuffer[] dsts = { sequence, data };

while (sequence.hasRemaining() || data.hasRemaining()) {
    long n = channel.read(dsts);
    if (n < 0) throw new EOFException("Incomplete fixed record");
    if (n == 0) throw new IOException(
            "No read progress on blocking channel");
}
sequence.flip();
data.flip();
```

*This is a code snippet for a blocking `ScatteringByteChannel` in the `channel` variable; the fixed 8-byte payload is an **upfront agreed-upon constraint**, not an arbitrarily large buffer.* It requires `import java.io.EOFException;`, `IOException`, and `ByteBuffer`.

## 7. A `write(ByteBuffer[])` call may write only part of the data

For gathering write, the return value is the **total number of bytes actually written in that call**, not the initial sum of `capacity` or `remaining()`. If the channel only accepts a partial amount, the buffers' `position` values are updated accordingly. For example:

```text
Before write:
  header: 4 bytes remaining
  payload: 10 bytes remaining

Suppose write(...) returns 6:
  header: 0 bytes remaining   (4 bytes written)
  payload: 8 bytes remaining  (2 bytes written)

The next write must continue from the exact current position.
Do not reset header/payload to position 0.
```

The example above is only an **arithmetic illustration**: there is no guarantee that `write` will always return 6. Actual behavior depends on the channel, socket state, OS, load, and blocking/non-blocking mode.

Note these rules:

1. Use `while (hasRemaining(buffers))` to loop until all source buffers are exhausted, if the protocol requires sending a complete frame.
2. Do not call `clear()` or `rewind()` between incomplete writes; doing so could **resend the header or body from the beginning**.
3. Do not rebuild the header by repeatedly calling `putInt(...)` on each write while a send is in progress; build the frame **once** and preserve its state.
4. Do not treat a positive return value from `write(...)` as meaning the peer application has processed the data; it only reflects writing down to the channel layer of the current process.
5. When a channel is in **non-blocking mode**, 0 is normal when no more data can be written yet; do not busy-loop infinitely—use `Selector`/`OP_WRITE` and keep the partially written buffers intact.
6. Do not write multiple frames to the same channel from multiple threads without serializing writes: bytes of frame A's header can interleave with frame B's payload if writers take turns arbitrarily.

When writing multiple frames consecutively over TCP, the receiver must read according to per-frame framing, even when a gathering write "combined" the header with the body on the sender side.

## 8. A `read(ByteBuffer[])` call may also receive only part of the data

The return value of a scattering read is interpreted as follows:

| Result | Meaning |
| --- | --- |
| `n > 0` | Placed `n` bytes into one or more destinations; still need to check which buffers are not yet full |
| `n == 0` | No new bytes in this call; common in non-blocking mode or when no destination space remains |
| `n == -1` | Reached **end-of-stream** of the read channel; if a frame is in progress, it is a **truncated frame** |
| `IOException` | An I/O error occurred; part of a frame may already have been received before the error was reported |

With a blocking `SocketChannel` and at least one buffer having `remaining()>0`, `read` normally waits until data, EOF, or an error arrives; you must not assume a single read completes the entire header + body. The loop in the demo program checks the buffers and throws `EOFException` if the peer closes before the frame is complete.

**TCP is a byte stream:** a single `write(new ByteBuffer[]{header,body})` on the sender may be observed by the receiver across multiple `read` calls, or multiple frames may arrive back-to-back in the same stream. Gathering write **does not create datagrams** and scattering read **does not automatically delimit frames**.

Conversely, on a file channel such as `FileChannel`, partial read/write results must also be handled via `position/remaining`; EOF means end of file, not that a TCP peer closed.

## 9. Non-blocking `SocketChannel` requires a state machine and `Selector`

The demo's `readFully`/`writeFully` helpers are only for **blocking channels**: they loop directly until buffers are complete and treat `n==0` as no progress. In non-blocking mode, **you must not wait that way**, because:

- `read(ByteBuffer[])` can return `0` when no data is available yet.
- `write(ByteBuffer[])` can return `0` when the socket send buffer cannot accept more data yet.
- Repeatedly calling them when they return 0 can waste CPU in a tight loop (busy spin).

A state machine for receiving dynamic frames should have states like:

```text
READ_LENGTH (4 bytes)
       |
       | all 4 bytes received; flip + getInt(); validate 1..MAX
       v
READ_TYPE_AND_BODY (1 byte + L-1 bytes)
       |
       | both type and body complete; flip + decode
       v
FRAME_COMPLETE
       |
       +----> process; build response; return to READ_LENGTH
```

On the write side:

```text
ENQUEUE_FRAME
    |
    | create header + type + payload, keep ByteBuffer positions
    v
WRITE_PENDING
    |
    | channel.write(parts), may be partial or return 0
    | still has remaining -> keep buffers for the next OP_WRITE
    | no remaining -> clear OP_WRITE interest if queue is empty
    v
FRAME_QUEUED_TO_CHANNEL
```

Register `OP_READ` to continue receiving when the channel is readable; register `OP_WRITE` only when **there is actually data waiting to be written**, to avoid a selector loop continuously reporting writable when the socket is already ready. On a connection with multiple requests, you need a send queue of frames and a backpressure mechanism rather than allocating unbounded buffers.

Note on `ByteBuffer.compact()`: use it when you want to keep **unprocessed** bytes in a single buffer, shifting them to the front before reading more. If you are using **dedicated buffers per frame part** in a state machine, you can continue directly with each buffer's `position` without compacting. `clear()` and `flip()` do not erase physical data; they only change the position and limit.

## 10. `offset/length` of the buffer array and bytes transferred

There are overloads:

```java
long n = channel.write(parts, startIndex, count);
long m = channel.read(destinations, startIndex, count);
```

*These are code snippets inside methods that have `channel`, `parts`, `destinations`, `startIndex`, `count` with the corresponding interfaces.* The two parameters `startIndex` and `count` select **how many ByteBuffer elements in the array** to use; they are not byte offsets and lengths within each buffer.

Example of a three-element array:

```text
parts[0] = header
parts[1] = type
parts[2] = payload

channel.write(parts, 1, 2)
  -> writes only type then payload
  -> skips header
```

When you need to "skip an already-sent header" on the next send, in most cases you can just pass **the entire array**: because `header.remaining()==0`, the channel automatically moves on to the next buffer. There is no need to manually recalculate array indices after each partial write unless you are doing an intentional optimization.

If slicing from a larger buffer, also pay attention to `ByteBuffer.slice()`: the slice has `position=0`, `limit=remaining` at creation time, but **shares the data region** with the original buffer; advancing the slice's position does not advance the original buffer's position. `duplicate()` also creates an object with independent position/limit while sharing the underlying content. When using pooled/direct buffers, you must manage their lifecycle and not reuse backing memory before I/O completes.

## 11. Header defines length in **bytes**, not character count

For UTF-8, the number of bytes can differ from the number of characters:

```java
byte[] payload = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
int byteCount = payload.length;  // use byteCount to write header
```

Do not use `text.length()` to compute UTF-8 byte length, because `String.length()` counts UTF-16 code units rather than UTF-8 bytes. If the sender writes the character count into the header while the receiver allocates/reads by bytes, the frame will be short on data, misaligning the boundaries of subsequent messages.

In the complete example, the value `L` includes **1 byte type + the number of UTF-8 payload bytes**, excluding the four header bytes. The receiver reads the exact declared number of bytes after validating `L`. Both sides must follow this same convention; one side must not compute body length without `type` while the other interprets it as including `type`.

For untrusted messages, you should also add:

- A length bound before `ByteBuffer.allocate(L - 1)`; avoid unbounded allocations, negative numbers, and oversized frames.
- Validation that `type` belongs to an allowed set. `Byte.toUnsignedInt(typePart.get())` yields values 0..255; do not confuse signed `byte` with message types 128..255.
- Valid UTF-8 checking, e.g. a decoder with `CodingErrorAction.REPORT` if the protocol rejects malformed bytes; `StandardCharsets.UTF_8.decode(...)` with its default configuration may substitute replacement characters.
- Limits on frames/connection, timeouts, send rate, number of pending responses, and total memory.
- For requests with side effects, use IDs to match responses to the right requests and design appropriate retry/idempotency handling. A successful `write` does not guarantee the server has processed the request.

## 12. When should you use scattering/gathering instead of a single buffer?

| Scenario | Recommendation |
| --- | --- |
| Small header, payload is already an existing `ByteBuffer` | **Gathering write** sends both in order without creating a new byte array |
| Protocol has type + metadata + payload in separate regions | Combine multiple buffers with `write(ByteBuffer[])`; limit buffer count and measure performance |
| Reading records with **known fixed-size** parts | **Scattering read** into multiple buffers separates destination regions |
| Reading frames with **dynamic length in the header** | Read/validate the header first, then scattering-read the known-size body parts |
| A small payload already in a single buffer | `channel.write(singleBuffer)` may be simpler; do not force gathering at all costs |
| Very large number of very small buffers | Consider platform vectored I/O overhead/limits; benchmark before optimizing |
| Sending a file to a socket | Also consider `FileChannel.transferTo(...)` where appropriate; it is a different API, not default gathering write |
| Non-blocking server | Preserve buffer state across `Selector` events and manage backpressure |

There is no universal speed advantage. The benefit depends on message size, allocation model, number of buffers, TLS/`SSLEngine` if present, CPU, and OS. Especially with TLS, encrypted records, security headers, and internal buffers can make actual data transfer behave differently from a raw TCP frame. Before changing architecture for performance, measure throughput/latency and allocation counts for your actual workload.

## 13. Common mistakes and how to fix them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Building header with `putInt` without calling `flip()` | `remaining()==0`, header is not sent | Call `flip` before putting it into the source array |
| Assuming a single `write(ByteBuffer[])` sends all bytes | On sockets it may write only a partial amount | Loop until all source buffers have no `remaining` |
| Looping writes while calling `rewind()` in between | Header/body may be resent | Keep `position` intact after a partial write |
| Assuming a single `read(ByteBuffer[])` fills all buffers | Decoder reads an incomplete frame | Track `hasRemaining` and EOF |
| `read` returns `-1` mid-frame and still parsing | Truncated frame | Report error / close per protocol |
| Allocating a large body buffer before reading the header | May read into the next frame | Read 4-byte header, validate L, then read exact L bytes |
| Using `String.length()` as UTF-8 byte length | Frame length mismatch with Unicode | Compute via `getBytes(UTF_8).length` |
| Using `capacity` instead of `remaining` when sending | Incorrect actual size | Track `position` and `limit` |
| Forgetting to `flip()` destination after receive | Parser reads from wrong position | Call `flip` once the required data has been received |
| Treating `read/write==0` as EOF in non-blocking mode | Wrongly closes connection | 0 means no progress yet; wait for Selector |
| Busy-looping when non-blocking write returns 0 | Wastes CPU | Wait for `OP_WRITE`, keep buffers queued |
| Multiple threads writing header/body to the same socket | Bytes of multiple frames interleave | Serialize writer/queue and preserve whole frames |
| Treating gathering as a single TCP packet/atomic message | Misunderstands TCP framing | Parser must rely on header length, not write boundaries |
| Not bounding header L from the network | Huge/negative allocation or DoS | Check `1 <= L <= MAX_FRAME_BYTES` before allocating |
| Mistaking `write(parts, 1, 2)` for byte offsets | Skips wrong header/type parts | Understand offset/length at the **buffer array** level |

## 14. Practice exercises

**Exercise 1 — Zero-copy two-part send:** Given `ByteBuffer header` containing a 4-byte length and `ByteBuffer payload` containing data. Write a gathering write loop ensuring both parts are fully sent in blocking mode. When must `flip()` be called?

**Exercise 2 — Partial write:** Header has 4 bytes left, body has 10 bytes left. `channel.write(new ByteBuffer[]{header, body})` returns `6`. Assuming standard sequential writing, how many bytes remain in each buffer? How should the buffers be reused on the next call?

**Exercise 3 — Reading a dynamic frame:** Header declares `L=100` (including type). The receiver wants to scatter into `type` and `payload`. How many bytes should it allocate for each? Should it allocate `payload=ByteBuffer.allocate(1024)` and read until full?

**Exercise 4 — Reading two buffers:** `ByteBuffer a=allocate(4)` and `b=allocate(8)`. A scattering read returns 5 bytes. Assuming both buffers were initially empty, what is `remaining()` for each buffer after the read?

**Exercise 5 — Non-blocking:** A `write(ByteBuffer[])` call returns `0`, and the buffers still have data. What should you do instead of calling `write` repeatedly in `while(true)`?

**Exercise 6 — Wrong length:** The client sends UTF-8 text containing Vietnamese characters, but the header writes `String.length()`. What is the consequence? What calculation should replace it?

**Suggested answers:**

1. `header.flip()` after `putInt`; `payload` must be in read mode. Call `write(new ByteBuffer[]{header,payload})` in a loop until both have `hasRemaining()==false`, without calling `rewind` in between.
2. Header has `0` left, body has `8` left; continue writing the same buffers from their current positions.
3. `type` buffer `1` byte, `payload` `99` bytes; do not arbitrarily read 1024 bytes because it may swallow the next frame.
4. `a.remaining()==0`, `b.remaining()==7` (4 bytes into `a`, 1 byte into `b`).
5. Save the state of pending buffers, register `OP_WRITE` and resume writing when writable; bound the queue/apply backpressure.
6. `String.length()` counts UTF-16 code units, not UTF-8 bytes. Use `text.getBytes(StandardCharsets.UTF_8).length` before writing the header.

## Official Java References

- [Java SE 17 — ScatteringByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ScatteringByteChannel.html): `read(ByteBuffer[])`, buffer ordering, `long` result.
- [Java SE 17 — GatheringByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/GatheringByteChannel.html): `write(ByteBuffer[])`, partial progress.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): TCP channel, blocking/non-blocking modes, and read/write overloads.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip`, `slice`, `duplicate`, `order`.
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): handling readiness for non-blocking channels.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): scattering/gathering on file channels.
