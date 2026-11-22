# Scattering Read and Gathering Write in Java NIO Channels

## 1. Goal and Problem

In Java NIO, data is usually transported through a **Channel** and placed in **Buffers**. When a message consists of multiple parts—such as a **header** and a **payload**—an application can perform:

- **Scattering read:** read consecutive bytes from a single channel and **scatter** them sequentially across multiple `ByteBuffer`s.
- **Gathering write:** take the remaining bytes from multiple `ByteBuffer`s and **gather** them into a single contiguous byte sequence written out to a channel.

This is a **vectored buffer** I/O mechanism: one call operates on an array of buffers, making data structure explicit and potentially reducing I/O calls depending on the system. However, **one call does not guarantee reading/writing all bytes**, does not represent a complete network message, and does not create an atomic transaction on its own.

Imagine a simple frame with a **4-byte header** containing the payload length, followed by a **3-byte payload** containing the ASCII characters `ABC`:

~~~text
Byte stream on file/socket:
  00 00 00 03  41 42 43
  └─ header ─┘ └─ body ┘
  4 bytes       3 bytes

Scattering read:
  Channel ───────────────┬──> ByteBuffer header [00 00 00 03]
                         └──> ByteBuffer body   [41 42 43]
                             (in array order, header before body)

Gathering write:
  ByteBuffer header [00 00 00 03] ─┐
                                   ├──> Channel: 00 00 00 03 41 42 43
  ByteBuffer body   [41 42 43] ────┘
~~~

Important condition: **the sizes of the header and body regions must be prepared accurately**. When the body length is unknown until after reading the header, the program typically needs **two read phases** or a stateful parser rather than assuming a single scattering call can allocate the exact payload buffer automatically.

## 2. Which APIs Support This?

Two interfaces in the `java.nio.channels` package:

- `ScatteringByteChannel`: sequentially reads bytes from a channel into **an array of `ByteBuffer`s**.
- `GatheringByteChannel`: sequentially writes data from **an array of `ByteBuffer`s** out to a channel.

Core overloads:

~~~java
// API signatures (not a standalone program):
long read(ByteBuffer[] dsts) throws IOException;
long read(ByteBuffer[] dsts, int offset, int length) throws IOException;

long write(ByteBuffer[] srcs) throws IOException;
long write(ByteBuffer[] srcs, int offset, int length) throws IOException;
~~~

Note: the `read` methods belong to `ScatteringByteChannel`, and the `write` methods belong to `GatheringByteChannel`; not every `Channel` type supports both. Representative types that support them include:

| Channel | Scattering Read | Gathering Write | Typical Context |
|---|---|---|---|
| `FileChannel` | Yes | Yes | Reading/writing files with headers, payloads, binary records |
| `SocketChannel` | Yes | Yes | Reading/writing TCP byte streams, protocol frames |
| Arbitrary `ReadableByteChannel` / `WritableByteChannel` | Not certain | Not certain | Check the concrete interfaces the object implements |

The examples use `FileChannel` for reproducible results; the buffer rules still apply when using `SocketChannel`, though network I/O may return fewer bytes than expected, especially when non-blocking.

### `offset` and `length` Are Positions in the **Buffer Array**

Given `ByteBuffer[] buffers = {a, b, c, d};`, calling `read(buffers, 1, 2)` inspects only **b** and then **c**:

- `offset = 1`: starts at element index 1 of the **array**.
- `length = 2`: processes exactly two elements of the **array**; the exclusive end index is 3.
- They are not file byte offsets, not buffer positions, and not the number of bytes to read.

If `offset < 0`, `length < 0`, or `offset + length` exceeds the array bounds illegally, Java throws `IndexOutOfBoundsException`. Passing `length=0` selects no buffers and the operation returns 0. When passing the entire array, the overloads without `offset,length` are more convenient.

## 3. Recap of `ByteBuffer` State

A `ByteBuffer` has three main indices:

- `capacity`: total number of bytes it can hold, immutable.
- `limit`: exclusive upper bound of the active region.
- `position`: index of the next relative operation.

Always holds: `0 <= position <= limit <= capacity`. Remaining elements: `remaining() = limit - position`.

Two common usage states:

| Stage | Target Buffer for **Channel Read** | Source Buffer for **Channel Write** |
|---|---|---|
| Preparation | Usually `clear()` or `compact()` so space exists to receive data | `put(...)` then `flip()` so only the outgoing payload remains |
| During I/O call | Channel places bytes in `[position, limit)` and advances `position` | Channel reads bytes from `[position, limit)` and advances `position` |
| After call | Call `flip()` to read newly received data (when ready) | If `hasRemaining()`, unwritten data still remains |

Example:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);   // p=0, l=4, c=4
ByteBuffer body = ByteBuffer.allocate(8);     // p=0, l=8, c=8

// Both can serve as target buffers for a scattering read.

ByteBuffer outgoing = ByteBuffer.allocate(4);
outgoing.putInt(3);                            // p=4, l=4
outgoing.flip();                               // p=0, l=4
// outgoing is ready as a source buffer for a gathering write.
~~~

**Careful:** `flip()` sets `limit` to the old `position` and `position=0`. Calling `flip()` too early on a newly allocated empty buffer sets `limit` to 0, preventing the channel from loading/reading any bytes into the target buffer via relative operations.

## 4. Scattering Read: Distributing Data Across Multiple Buffers

The call:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
ByteBuffer payload = ByteBuffer.allocate(3);

long bytesRead = channel.read(new ByteBuffer[] {header, payload});
~~~

This is an **illustrative snippet** assuming `channel` is an open `ScatteringByteChannel`. A complete Java 17 program appears in Section 7.

Mechanism:

1. The channel begins reading bytes from its current read position.
2. Places received bytes into the first buffer, from `header.position()` up to before `header.limit()`.
3. Only after the first buffer's `remaining()` region is filled does it advance to the next buffer.
4. The `long bytesRead` return value is **the total number of bytes actually transferred into the buffers**.
5. The `position` of each buffer that received bytes increases accordingly; `limit` does not change automatically.

Suppose the channel holds 7 bytes and the actual read returns 5 bytes:

~~~text
Before read:
  header: p=0, l=4, 4 bytes free
  body:   p=0, l=3, 3 bytes free

Received 5 bytes:
  header = [00 00 00 03], p=4, l=4
  body   = [41 .. ..],    p=1, l=3
  return = 5L

Still missing 2 payload bytes:
  header.remaining() = 0
  body.remaining()   = 2
~~~

If you call `channel.read(new ByteBuffer[]{header, body})` again while the remaining 2 bytes `42 43` sit in the source, the channel **skips `header` since it has no space left** and continues filling `body`. Only once everything is received do you `flip()` the buffers for the parser to read.

### A Single Read Does Not Guarantee “Reading Everything”

- It may return a **positive number smaller than total remaining**; this is normal behavior.
- It may return **0** if no bytes can be read right then, especially on non-blocking channels.
- It may return **-1** if end-of-stream (EOF) is reached before receiving any bytes in that call.
- With a read-only target buffer, passing it to a scattering read may throw `ReadOnlyBufferException`; target buffers must be writable.
- If the first buffer reaches its `limit` while a protocol header requires more bytes than its size, bytes will spill into the second buffer even though **by protocol meaning** they are still part of the header. Scattering strictly follows **buffer capacity**, without understanding header/payload semantics.

Therefore, if the protocol specifies a 4-byte header, prepare the first buffer with **`remaining` equal to exactly 4**, not 8, and do not assume the parser will somehow stop after 4 bytes on its own.

### Reading Loop Until All Required Regions Are Full

With a **blocking `FileChannel`** and a file known to have sufficient content, you can loop until all buffers are full:

~~~java
static long readExactly(FileChannel channel, ByteBuffer[] dsts)
        throws IOException {
    long total = 0;

    while (hasRemaining(dsts)) {
        long count = channel.read(dsts);
        if (count < 0) {
            throw new EOFException("Tep ket thuc truoc khi doc du");
        }
        if (count == 0) {
            throw new IOException("Khong co tien trien khi doc tep");
        }
        total += count;
    }
    return total;
}

static boolean hasRemaining(ByteBuffer[] buffers) {
    for (ByteBuffer b : buffers) {
        if (b.hasRemaining()) return true;
    }
    return false;
}
~~~

This is an illustrative method snippet requiring imports `java.io.*`, `java.nio.*`, and `java.nio.channels.*`; Section 7 provides a standalone program.

For a **non-blocking `SocketChannel`**, do **not** run a tight loop when `read(...) == 0`. Integrate a readiness/`Selector` mechanism or schedule when data arrives, then resume reading at the preserved `position`. To bound memory usage, always cap the size of frames/buffers accepted from external sources.

### Buffers Receiving Zero Bytes Keep Their Position

If the source runs out of data before reaching a later buffer in the array, that buffer's `position` stays unchanged. Once a buffer has `remaining() == 0`, it receives no further bytes even though it remains in the array. If total `remaining()` is 0, scattering read has no destination space to receive data; re-prepare the buffers before continuing.

## 5. Gathering Write: Combining Multiple Buffers into One Write Stream

The call:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
header.putInt(3);
header.flip(); // Header: 4 valid bytes.

ByteBuffer payload =
        ByteBuffer.wrap(new byte[] {65, 66, 67}); // "ABC"

long bytesWritten = channel.write(
        new ByteBuffer[] {header, payload});
~~~

This is an illustrative snippet assuming `channel` is a writable `GatheringByteChannel`.

Mechanism:

1. Reads bytes from the `[position, limit)` region of the first buffer.
2. When the first buffer runs out of remaining bytes, moves to the second buffer and continues.
3. Concatenates bytes **in exact array order** when writing out to the channel.
4. The `long bytesWritten` return value is the number of bytes **actually accepted for writing by the channel in that call**.
5. The `position` of buffers whose data was consumed increases; `limit` stays unchanged.

Suppose the header buffer has 4 bytes and the body buffer has 3 bytes, yet the channel accepts only 5 bytes:

~~~text
Before write:
  header: p=0, l=4, remaining=4
  body:   p=0, l=3, remaining=3

After write returns 5:
  header: p=4, l=4, remaining=0
  body:   p=1, l=3, remaining=2
  bytes written: 00 00 00 03 41

Next write begins at:
  header has no bytes left -> skipped
  body resumes at 42, 43
~~~

This is a very useful property: **keep the buffers intact** after a partial write and call `write` again—their `position`s accurately remember what remains unsent. **Do not `rewind()` buffers after a partial write**, as that can cause **duplicate data** to be written/sent.

### Write Loop for `FileChannel`

~~~java
static long writeAll(FileChannel channel, ByteBuffer[] srcs)
        throws IOException {
    long total = 0;

    while (hasRemaining(srcs)) {
        long count = channel.write(srcs);
        if (count == 0) {
            throw new IOException("Khong co tien trien khi ghi tep");
        }
        total += count;
    }
    return total;
}
~~~

With `FileChannel` as used in the example, this loop demonstrates writing all data before completing. With a non-blocking `SocketChannel`, `write(...) == 0` is a normal condition; **wait until the channel is writable** (e.g., via `Selector.OP_WRITE`), preserve the buffers/positions across events, and call again. Do not close or reuse buffers while `hasRemaining()` is still true.

### No Automatic Guarantee of Atomicity

A single gathering write call does not create message boundaries on TCP. Data can be transmitted in multiple segments, and the receiver may read it in any split. Two records written by two different actors do not automatically form a protected transaction; if interleaving must be avoided, coordinate write access or protocol framing appropriately.

Do not assert that one gathering call always maps to **exactly one `writev` system call**: Java specifies the **data and buffer contract**, while the implementation and OS decide how it is executed underneath.

## 6. Behavior of `position`, `limit`, `mark`, and Return Values

| Aspect | Scattering Read | Gathering Write |
|---|---|---|
| Data direction | Channel → multiple target buffers | Multiple source buffers → Channel |
| Valid bytes transferred | Into `[position, limit)` of each buffer | Out from `[position, limit)` of each buffer |
| Order | Low buffer index to high | Low buffer index to high |
| `position` | Advances by bytes loaded | Advances by bytes sent |
| `limit`, `capacity` | Not adjusted automatically | Not adjusted automatically |
| Mark | May be invalidated if position rules are violated; I/O does not set a new mark | Same |
| Return value | `long` bytes received; 0 if none ready; -1 on EOF | `long` bytes accepted for write; may be 0 |
| Read-only buffer | Cannot be used as a target to receive bytes | Can be a source because the channel only reads buffer contents |
| When finished | Usually `flip()` buffers the parser needs to read | Check `hasRemaining()`; once empty, can `clear()`/refill |

`read/write` methods do not call `flip()` or `clear()` on the application's behalf.

**Note on `mark`:** since position normally moves forward after I/O, an old valid mark often remains valid. Still, never assume a mark acts as a rollback point for data already consumed on a channel: `reset()` only changes the **buffer's** position—it does not rewind bytes on a socket or source channel. Rewinding a buffer also does not retrieve bytes already accepted for output by the operating system.

## 7. Complete Java 17+ Program

The program performs these steps:

1. Create a temporary file.
2. Create a 4-byte header buffer containing the integer `3` (big-endian) and a 3-byte payload buffer containing `ABC`.
3. Write using **gathering write** until both buffers have no `remaining()`.
4. Open the file for reading; create two target buffers with capacities 4 and 3 bytes.
5. Read using **scattering read** until all 7 bytes are received.
6. `flip()` the target buffers, decode the header and payload, and verify the output.

Save the file as **`ScatteringGatheringDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ScatteringGatheringDemo {

    private static boolean hasRemaining(ByteBuffer[] buffers) {
        for (ByteBuffer b : buffers) {
            if (b.hasRemaining()) {
                return true;
            }
        }
        return false;
    }

    private static long writeAll(
            FileChannel channel, ByteBuffer[] sources)
            throws IOException {
        long total = 0;
        while (hasRemaining(sources)) {
            long count = channel.write(sources);
            if (count == 0) {
                throw new IOException("No progress while writing");
            }
            total += count;
        }
        return total;
    }

    private static long readExactly(
            FileChannel channel, ByteBuffer[] destinations)
            throws IOException {
        long total = 0;
        while (hasRemaining(destinations)) {
            long count = channel.read(destinations);
            if (count < 0) {
                throw new EOFException("Incomplete record");
            }
            if (count == 0) {
                throw new IOException("No progress while reading");
            }
            total += count;
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("gather-scatter-", ".bin");
        try {
            ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
            header.putInt(3);
            header.flip();

            ByteBuffer body = ByteBuffer.wrap(
                    "ABC".getBytes(StandardCharsets.UTF_8));

            try (FileChannel out = FileChannel.open(
                    file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
                long count = writeAll(
                        out, new ByteBuffer[] {header, body});
                System.out.println("gathered=" + count);
            }

            System.out.println(
                    "source positions="
                    + header.position() + "/" + header.limit()
                    + "," + body.position() + "/" + body.limit());

            ByteBuffer readHeader =
                    ByteBuffer.allocate(Integer.BYTES);
            ByteBuffer readBody = ByteBuffer.allocate(3);

            try (FileChannel in = FileChannel.open(
                    file, StandardOpenOption.READ)) {
                long count = readExactly(
                        in, new ByteBuffer[] {readHeader, readBody});
                System.out.println("scattered=" + count);
            }

            System.out.println(
                    "target positions="
                    + readHeader.position() + "/" + readHeader.limit()
                    + "," + readBody.position() + "/" + readBody.limit());

            readHeader.flip();
            readBody.flip();

            int bodyLength = readHeader.getInt();
            byte[] bytes = new byte[readBody.remaining()];
            readBody.get(bytes);

            System.out.println("header length=" + bodyLength);
            System.out.println(
                    "payload=" + new String(bytes, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run in the directory containing the source file:

~~~bash
javac ScatteringGatheringDemo.java
java ScatteringGatheringDemo
~~~

**Stdout when the program succeeds:**

~~~text
gathered=7
source positions=4/4,3/3
scattered=7
target positions=4/4,3/3
header length=3
payload=ABC
~~~

**Explanation:**

- The header is `00 00 00 03`; the payload is `41 42 43` (UTF-8 for ASCII `ABC`). Total bytes is `4 + 3 = 7`.
- `gathered=7` because the helper loops until all bytes are written; afterward both source buffers have `position == limit`.
- Both target buffers start at `position=0`; `scattered=7` because the helper loops until all 4 and 3 bytes are received.
- Before `flip()`, the target buffers have `position=4` and `position=3`. `flip()` resets `position=0` to read the exact newly populated region.
- `getInt()` decodes the header using `ByteBuffer`'s default big-endian order, yielding 3; the next three bytes produce the string `ABC`.

This demo knows in advance that the body length is 3, so it allocates `ByteBuffer.allocate(3)`. **A real protocol parser must never allocate body capacity from untrusted data without validating it first**, and must handle EOF, timeouts, and missing data.

## 8. Variable-Length Frames: When Not to Use a Single Scattering Call

Suppose a protocol sends:

~~~text
[4-byte unsigned/signed length] [N-byte payload]
~~~

The payload size is only known **after reading the header**. If you try guessing `ByteBuffer.allocate(4096)` for the body in a single scattering read, three problems arise:

1. The actual body may be **shorter than 4096**; the buffer does not automatically detect message boundaries. It could also pull in bytes from the next message.
2. The actual body may be **longer than 4096**; the target buffer lacks space and needs additional buffers.
3. Data may arrive in multiple fragments regardless of whether the sender used gathering write. This is a **byte stream** (especially on TCP), not a “one `write` ↔ one `read`” sequence.

Common approach:

1. Allocate `ByteBuffer.allocate(4)` for the header and read **until all 4 bytes arrive** using regular reads or scattering inside a state machine.
2. `flip()`, decode the length (e.g., `getInt()`), and **validate** `0 <= n <= MAX_FRAME_SIZE`.
3. Allocate a body buffer sized `n` or read incrementally in bounded chunks; read the body until complete.
4. Only after decoding one frame start the next frame, keeping any unconsumed bytes if you read past the boundary.

Simple validation snippet:

~~~java
// Illustrative; header has all 4 bytes read and flip()ped for reading.
int size = header.getInt();
int maxFrame = 1024 * 1024;
if (size < 0 || size > maxFrame) {
    throw new IOException("Invalid frame length: " + size);
}
ByteBuffer payload = ByteBuffer.allocate(size);
~~~

If you must handle multiple frames in a stream, you can use one overall buffer with a parser or a `READ_HEADER → READ_BODY → PROCESS_FRAME` state machine. Scattering read is very useful when **fixed parts are known upfront** or corresponding capacities have been determined; it **does not replace framing logic**.

### Handling Non-Blocking Mode with a State Machine

With `SocketChannel.configureBlocking(false)`:

- `read(buffers) == 0`: no new bytes yet; **preserve `position`**, await `OP_READ`, and retry later.
- `read(buffers) > 0`: update received byte count, check whether header/body is complete, and transition parser state accordingly.
- `read(buffers) == -1`: the peer closed its output stream; handle any incomplete frame per the protocol.
- `write(buffers) == 0`: the OS cannot accept more bytes yet; retain the buffers in an outbound queue, register `OP_WRITE` as needed, and resume from the current `position`.

Avoid keeping `OP_WRITE` registered continuously when no outbound data is pending, because sockets are usually writable and the selector can wake repeatedly, wasting CPU.

## 9. Scattering/Gathering vs. Multiple Read/Write Calls

Both approaches can produce the same byte sequence:

~~~java
// A. Multiple calls, using separate ByteBuffers.
channel.write(header);
channel.write(body);

// B. Gathering write.
channel.write(new ByteBuffer[] {header, body});
~~~

The **illustrative snippet** above assumes the source buffers are properly `flip()`ped. Do not run both approaches back-to-back on the **same buffers** to compare them, because approach A already advances `position` to the end, leaving 0 bytes for B.

A buffer-array API often helps by:

- Avoiding a **manual merge/copy** of header and body into one large array before writing.
- Keeping components in separate buffers, convenient for updating individual fields when building messages.
- Potentially leveraging OS-supported scatter/gather I/O to reduce overhead under certain conditions.

However, do not conclude:

- Every scattering/gathering call always maps to a single syscall.
- Performance is always higher than multiple individual calls. Payload size, buffer count, channel type, OS, kernel, buffering, and network state all affect results.
- There is an “all-or-nothing” guarantee: buffers may still be partially read or written.
- Using gathering write alone makes the receiver automatically separate header/body. **The receiver must apply the same protocol and framing rules**.

Benchmark on realistic data when optimizing performance; prioritize correct code and partial I/O handling first.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
|---|---|---|
| Calling `write(srcs)` and assuming all data was sent | Unwritten data is lost when closing/reusing buffers | Check total `remaining`; resume when channel is ready |
| Calling `read(dsts)` once and parsing immediately | Header/body missing bytes, `BufferUnderflowException`, or corrupted data | Maintain state and read completely per protocol |
| Forgetting `flip()` on source buffer after `put(...)` | Gathering write pulls uninitialized/wrong region of buffer | `flip()` before writing |
| Forgetting `flip()` on target buffer after reading completes | Parser reads from the end of the newly received region | `flip()` target buffer before parsing |
| Calling `rewind()` after a partial write | Re-sends bytes already consumed by the channel | Keep `position`; write only the remaining portion |
| Header buffer larger than actual header | Header “eats” into body due to sequential fill rule | Set `remaining` to the exact expected header size |
| Confusing `offset,length` with file offset/byte count | Reads/writes wrong buffers in the array | Remember they are **array start index and element count** |
| Allowing huge/negative body sizes from the network | Massive allocation, memory errors, broken parser | Validate frame size limits before `allocate` |
| Spinning when non-blocking read/write returns 0 | High CPU despite zero progress | Use readiness/`Selector` and preserve buffer state |
| Sending over TCP and expecting one read to receive one frame | Truncated reads or coalesced frames | Use length-prefix/delimiter and a state machine |
| Passing a read-only buffer as target | Failure when attempting to load bytes into the buffer | Use writable buffers for scattering read |
| Sharing a buffer array across unsynchronized threads | Each buffer's `position` and message ordering race | Single owner per session/buffer or explicit synchronization/queue |

## 11. Self-Check Questions

1. Two target buffers have `remaining()` of 4 and 3 respectively. A scattering read receives 5 bytes. How much does each `position` advance? **4 on the first buffer, 1 on the second**; 2 bytes still remain to be read.
2. Gathering write with two source buffers having `remaining` 4 and 3, but `write` returns 2. Which bytes will be written next? **The remainder of the first buffer first**, then the second buffer.
3. Calling `read(buffers, 1, 2)` on an array of four buffers—which buffers does the operation inspect? **Index 1 and index 2**, ignoring 0 and 3.
4. Does `write(new ByteBuffer[]{header, payload})` guarantee sending the entire frame in one call over TCP? **No.** Partial writes and framing still must be handled.
5. When `channel.read(dsts) == 0` in non-blocking mode, should you loop repeatedly without waiting? **No.** Keep state and wait for readiness.
6. Can a scattering read automatically separate a 4-byte header and a variable-length N-byte payload without knowing N? **No.** Buffers are filled strictly by `remaining`; the application must read the header, decode, and validate N.
7. After a scattering read fills both buffers, what must be done before calling `getInt()` on the header? **`header.flip()`** (and `body.flip()` to read the body).
8. A gathering write completes partially; should you call `rewind()` on all source buffers to retry? **No.** Doing so would send duplicate data.
9. Does a gathering write automatically clear, close, or change the `limit` of buffers? **No.** It primarily advances `position` by the actual bytes transferred.
10. Why can scattering/gathering be useful yet still require benchmarking? **It can reduce copying and I/O overhead**, though actual cost and syscall counts depend on implementation and environment.

## 12. Official API References

- [Java SE 17 — ScatteringByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ScatteringByteChannel.html): contract on buffer ordering, `long` return value, and partial reads.
- [Java SE 17 — GatheringByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/GatheringByteChannel.html): contract on write ordering, `position`, and partial writes.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): file I/O API supporting read/write over buffer arrays.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): socket I/O, blocking/non-blocking modes, and buffer operations.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip`, `remaining`, binary read/write.
