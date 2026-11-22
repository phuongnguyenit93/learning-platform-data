# ReadableByteChannel, WritableByteChannel, and ByteChannel in Java NIO

## 1. What Is an NIO Channel?

In Java NIO, a **channel** is an object representing an open I/O connection to a data source or destination: a file, a network connection, a pipe, or a source/sink adapted from `InputStream` and `OutputStream`. When working with **byte channels**, the program exchanges data through a `ByteBuffer`.

The three foundational interfaces in the `java.nio.channels` package are:

- **`ReadableByteChannel`**: allows reading bytes from the channel into a `ByteBuffer`.
- **`WritableByteChannel`**: allows writing bytes from a `ByteBuffer` out to the channel.
- **`ByteChannel`**: combines both read and write capabilities through the same object.

A channel typically has an **open/closed** state via the `Channel` interface. A channel is not synonymous with a stream, though it can be adapted to and from streams via `java.nio.channels.Channels`. More importantly, all three interfaces are designed to work with buffers: operations advance the `ByteBuffer`'s **position** by the number of bytes transferred, rather than managing text, charsets, or message boundaries themselves.

This article focuses on **the contracts of these interfaces**, how to handle incomplete read/write results, and how to transition buffer states so data is not lost.

## 2. Inheritance Relationships

Interface diagram:

```text
                         java.nio.channels.Channel
                         + isOpen()
                         + close()
                            ^
                            |
           +----------------+----------------+
           |                                 |
ReadableByteChannel                 WritableByteChannel
+ read(ByteBuffer dst)              + write(ByteBuffer src)
           ^                                 ^
           |                                 |
           +---------------+-----------------+
                           |
                       ByteChannel
              (inherits both read and write)
```

`Channel` extends `java.io.Closeable`, so it can be used with `try-with-resources`. `ByteChannel` is a composite interface that declares no additional read/write methods beyond those inherited.

Key method signatures:

```java
// ReadableByteChannel
int read(ByteBuffer dst) throws IOException;

// WritableByteChannel
int write(ByteBuffer src) throws IOException;

// Channel
boolean isOpen();
void close() throws IOException;
```

These are abbreviated API signatures for study, not a standalone runnable program.

| Interface | Read? | Write? | Characteristics |
| --- | --- | --- | --- |
| `ReadableByteChannel` | Yes | Not required | Transfers bytes from source into the remaining space of `dst` |
| `WritableByteChannel` | Not required | Yes | Takes remaining bytes of `src` and pushes them to the target |
| `ByteChannel` | Yes | Yes | Single object carrying both contracts, still subject to open mode and implementation |
| `SeekableByteChannel` | Yes | Yes | Extends `ByteChannel` with `position()`, `position(long)`, `size()`, `truncate()` |

**Note:** A class may implement `ByteChannel` while actual operations depend on configuration/mode. For example, a `FileChannel` opened read-only does not allow writing; calling `write` may throw `NonWritableChannelException`. Having a `write` method in the Java type does not guarantee the resource was opened with write permission.

## 3. `ReadableByteChannel.read(ByteBuffer dst)`

The call:

```java
int n = channel.read(dst);
```

assumes `channel` is an open `ReadableByteChannel` and `dst` is a writable `ByteBuffer`.

The method attempts to transfer bytes from the channel into the **remaining space of the buffer**: from `dst.position()` up to just before `dst.limit()`. When `n > 0` bytes are transferred, `position` increases by exactly `n`; `limit` and `capacity` remain unchanged because this operation only places additional bytes into the buffer.

The return value has three cases:

| Value | Meaning | Next Action |
| --- | --- | --- |
| `n > 0` | Read exactly `n` bytes | Continue reading or `flip()` to process |
| `n == 0` | No bytes were transferred in this call | Check buffer remaining space, blocking/non-blocking mode, and readiness |
| `n == -1` | Reached **end-of-stream (EOF)** | Stop waiting for more data from an ended source |

**There is no guarantee of filling the buffer in a single call.** If `dst.remaining() == 100`, calling `read(dst)` may return 1, 24, or any other positive number up to 100. If the buffer has `remaining()==0`, there is no room to receive bytes; `read` typically returns 0 when no bytes can be transferred.

With a channel in **non-blocking** mode, `read` may return 0 when no data is ready yet. If the channel is blocking and the buffer has room, the call may wait for data or EOF per the implementation's contract. Do not write a spinning `while (read(...) == 0)` loop on a non-blocking channel: that loop burns CPU without making progress; instead coordinate with readiness/`Selector` or an appropriate wait mechanism.

### Position Before and After Reading

Suppose `dst.capacity()==8`, `position==2`, `limit==6`, and the channel transfers 3 bytes:

```text
Before: [ ? ][ ? ][ _ ][ _ ][ _ ][ _ ][ ? ][ ? ]
                    ^
                   pos=2
                                     ^
                                   limit=6

After:  [ ? ][ ? ][ A ][ B ][ C ][ _ ][ ? ][ ? ]
                                   ^
                                  pos=5
                                     ^
                                   limit=6
```

Only the `[2,5)` range is newly written. `n=3`; `dst.remaining()` after the read is 1. Old bytes outside this range are not automatically cleared or inspected.

A `read` call requires a **writable** buffer. If `dst` is read-only, the call may throw `ReadOnlyBufferException`; if the channel is closed, it may throw `ClosedChannelException` (both must be distinguished from EOF).

## 4. `WritableByteChannel.write(ByteBuffer src)`

The call:

```java
int n = channel.write(src);
```

assumes `channel` is a `WritableByteChannel` and `src` holds the outgoing data in the range `[position, limit)`.

- `write` consumes **at most `src.remaining()` bytes**, starting from `position`.
- Returns **the actual number of bytes written**, never `-1` as `read` does.
- After writing `n` bytes, `src.position()` increases by exactly `n`; `limit` and `capacity` stay unchanged.
- If no bytes could be written yet, it may return **0**, especially on non-blocking channels or when `src` has no remaining bytes.

**Do not assume a single `write` writes the entire buffer.** For example, if `src.remaining()==10` but only 4 bytes are written, `position` advances by 4 and 6 bytes remain waiting to be sent. Calling `clear()` at this point would lose the state of the unsent portion; if you continue using the buffer, keep `position/limit` intact and write again until `remaining` is exhausted, or save the remainder according to your policy.

### Relationship with `ByteBuffer.flip()`

Typically a program prepares bytes to send as follows:

```java
ByteBuffer src = ByteBuffer.allocate(8);
src.put((byte) 65);
src.put((byte) 66);
src.put((byte) 67);
src.flip();   // position=0, limit=3
// WritableByteChannel.write(src) reads 3 bytes from src if the target accepts enough.
```

The snippet above illustrates buffer state; it does not yet include a channel object. Forgetting `flip()` would make the channel try to write from offset 3 to the old limit 8, which is not the region representing the three newly prepared bytes.

## 5. `ByteChannel`: One Object That Can Read and Write

`ByteChannel` inherits from both `ReadableByteChannel` and `WritableByteChannel`. Therefore a variable of type `ByteChannel` can invoke both `read(ByteBuffer)` and `write(ByteBuffer)`.

However, **bidirectional operations do not imply having a file pointer, seek capability, or always-ready full-duplex I/O**:

- `ByteChannel` **does not define** `position()` or `position(long)`.
- If you need to move a file offset, use `SeekableByteChannel` or `FileChannel`.
- If you need a network channel supporting read/write, `SocketChannel` is an implementation that also adds connection management and non-blocking support.
- Whether reading and writing can occur simultaneously, connection state, I/O permissions, and thread-safety depend on the specific class.

In the file system, `Files.newByteChannel(path, options...)` returns a `SeekableByteChannel`; that object is simultaneously a `ByteChannel`. One handle can be used for both reading and writing if opened with the appropriate `StandardOpenOption` flags.

## 6. Standalone Java 17+ Example: Copying Data Across Two Channels

The program creates an in-memory byte source and an in-memory byte sink, then uses the two separate interfaces:

- `ReadableByteChannel` transfers data from `ByteArrayInputStream` into a `ByteBuffer`.
- `WritableByteChannel` transfers data from the `ByteBuffer` into a `ByteArrayOutputStream`.
- `Channels.newChannel(...)` creates adapters from Java IO streams to NIO channels.

No external file or network is needed; output is deterministic on any Java 17+ environment.

**File `ChannelCopyDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Channels;
import java.nio.channels.ReadableByteChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;

public class ChannelCopyDemo {
    public static void main(String[] args) throws IOException {
        byte[] input = "Java NIO!".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (ReadableByteChannel source =
                     Channels.newChannel(new ByteArrayInputStream(input));
             WritableByteChannel target =
                     Channels.newChannel(sink)) {

            ByteBuffer buffer = ByteBuffer.allocate(4);
            int total = 0;

            while (true) {
                int count = source.read(buffer);

                if (count == -1) {
                    break; // EOF
                }
                if (count == 0) {
                    throw new IOException("No progress in blocking demo");
                }

                total += count;
                buffer.flip(); // Prepare the newly received region to be written out.

                while (buffer.hasRemaining()) {
                    int written = target.write(buffer);
                    if (written == 0) {
                        throw new IOException("No write progress in demo");
                    }
                }

                buffer.clear(); // All transferred, prepare to receive the next round.
            }

            System.out.println("Da sao chep: " + total + " byte");
        }

        System.out.println(
            "Noi dung: " + sink.toString(StandardCharsets.UTF_8));
    }
}
```

Compile and run:

```bash
javac ChannelCopyDemo.java
java ChannelCopyDemo
```

**Exact stdout on success:**

```text
Da sao chep: 9 byte
Noi dung: Java NIO!
```

Explanation across iterations with a `capacity=4` buffer:

| Read Pass | Bytes Received | Position After `read` | After `flip` | Written Out |
| --- | --- | ---: | --- | --- |
| 1 | `Java` (4 bytes) | 4 | `position=0, limit=4` | `Java` |
| 2 | ` NIO` (4 bytes) | 4 | `position=0, limit=4` | ` NIO` |
| 3 | `!` (1 byte) | 1 | `position=0, limit=1` | `!` |
| 4 | EOF | No bytes transferred | No `flip` | Exit |

With an adapter over `ByteArrayInputStream`, reads with sufficient data return positive byte counts matching the buffer size in the example. In **real channels**, never rely on receiving a fixed number of bytes as in the illustration table; the core logic is to use the actual `count` returned, `flip`, and write until `remaining` is exhausted.

The program handles `count==0` and `written==0` with exceptions because it uses blocking in-memory stream adapters and always has a non-empty buffer at the point of the call. This is **not the strategy for non-blocking channels**. With a non-blocking `SocketChannel`, you need a readiness-waiting mechanism, preserve unsent data, and resume when the channel is ready.

### Why Is the `while (buffer.hasRemaining())` Loop Needed?

`WritableByteChannel.write` is allowed to consume only **part** of the data. If you call `write` only once and then `clear`, the unwritten portion can be lost. The loop ensures the program does not drop the remainder; in non-blocking applications, the loop is **paused when write returns 0** and resumed after a readiness signal, rather than spinning continuously.

## 7. Standalone Java 17+ Example: `ByteChannel` and File Read/Write

The next example uses a `SeekableByteChannel` created by `Files.newByteChannel`. Because this interface extends `ByteChannel`, we assign the same object to a `ByteChannel io` variable to call `write` and `read`. However, moving the file position back to the start must be called via `SeekableByteChannel`.

**File `ByteChannelFileDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ByteChannel;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ByteChannelFileDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("byte-channel-", ".bin");

        try {
            try (SeekableByteChannel file = Files.newByteChannel(
                    path,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteChannel io = file;
                ByteBuffer outgoing =
                    ByteBuffer.wrap("ABC".getBytes(StandardCharsets.US_ASCII));

                while (outgoing.hasRemaining()) {
                    int n = io.write(outgoing);
                    if (n == 0) {
                        throw new IOException("No file write progress");
                    }
                }

                System.out.println("Kich thuoc tep: " + file.size());

                file.position(0); // ByteChannel does not have position(long).
                ByteBuffer incoming = ByteBuffer.allocate(3);

                while (incoming.hasRemaining()) {
                    int n = io.read(incoming);
                    if (n == -1) {
                        break;
                    }
                    if (n == 0) {
                        throw new IOException("No file read progress");
                    }
                }

                incoming.flip();
                System.out.println(
                    "Doc lai: " + StandardCharsets.US_ASCII.decode(incoming));
                System.out.println("Channel dang mo: " + io.isOpen());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Commands:

```bash
javac ByteChannelFileDemo.java
java ByteChannelFileDemo
```

**Exact stdout if I/O succeeds:**

```text
Kich thuoc tep: 3
Doc lai: ABC
Channel dang mo: true
```

Why can it read the data back?

1. `write` transfers the three bytes `A B C` to the file and advances the file channel's position to offset 3.
2. `file.position(0)` resets the offset before reading. A pure `ByteChannel` **does not have** this positioning method.
3. `read` reads three bytes from the file into `incoming` (allocated with 3 bytes).
4. `incoming.flip()` sets up the data region so the decoder extracts the exact three bytes.
5. `io.isOpen()` returns `true` at the check inside `try`. On exiting `try-with-resources`, the channel is closed.

`SeekableByteChannel` and `FileChannel` maintain file position state, which is distinct from `ByteBuffer.position()`. **These two positions are separate states**: the buffer's position controls which bytes in memory are transferred; the file's position controls the file offset where I/O occurs.

## 8. ByteBuffer Is an Inseparable Part of the Channel Contract

`ReadableByteChannel.read(dst)` and `WritableByteChannel.write(src)` both operate on a properly prepared `ByteBuffer`:

```text
Reading from a channel into a buffer:
  buffer.clear() --> channel.read(buffer) --> buffer.flip()
  --> application calls buffer.get(...)

Writing from a buffer to a channel:
  buffer.clear() --> application calls buffer.put(...) --> buffer.flip()
  --> channel.write(buffer) (loop/wait until the outgoing portion is handled)
```

For a **forwarding loop from source to destination**, such as `ChannelCopyDemo`, each time a chunk of data is received you need:

1. Buffer has write space: `position < limit`.
2. Source channel calls `read(buffer)` and returns the number of bytes received.
3. If bytes were received, `flip()` so `limit` becomes the number of prepared bytes.
4. Target channel calls `write(buffer)` until fully consumed or paused due to unreadiness.
5. Once all bytes are processed, call `clear()`; if unprocessed bytes must be preserved, call `compact()`.

| Buffer Method | Effect on State | When to Use |
| --- | --- | --- |
| `flip()` | `limit=` old `position`, `position=0` | Switching from preparing data to consuming data |
| `clear()` | `position=0, limit=capacity` | Discarding an old completed data region |
| `compact()` | Keeps unconsumed bytes at the start, `position=` old `remaining`, `limit=capacity` | Need to read/write more while keeping the remainder |
| `remaining()` | `limit-position` | Determining how many bytes can be transferred this pass |
| `hasRemaining()` | `position<limit` | Checking whether data/space remains |

**`clear()` does not actually erase bytes.** When a buffer holds sensitive data, memory reuse/zeroing requires an explicit policy.

### Very Common Mistake: Reading Repeatedly Without Freeing Space

Suppose a channel reads 8 bytes into `ByteBuffer.allocate(8)`. At that point `position=limit=8`; the next `read(buffer)` call **has no room left**. To receive more, you must process the available bytes and then call `clear()` or `compact()`. Never conclude a channel reached EOF just because it delivers no more bytes when the buffer is already full.

## 9. Blocking, Non-Blocking, and Zero-Progress Situations

`ReadableByteChannel`, `WritableByteChannel`, and `ByteChannel` themselves **do not provide an API to configure non-blocking mode**. Features like `configureBlocking(false)` belong to `SelectableChannel` and related implementations such as `SocketChannel`. `FileChannel` performs file I/O and is not a `SelectableChannel`.

With blocking channels, calls generally wait for data or sufficient conditions according to that class's contract; **there is no guarantee that every read fills the buffer or every write finishes the entire source data**.

With non-blocking channels:

- `read(dst) == 0`: no bytes may be ready yet; if the buffer has space, register/await `OP_READ` readiness or an equivalent mechanism.
- `write(src) == 0`: the receiving side is not accepting more yet; keep the unsent portion intact and await `OP_WRITE` readiness as appropriate.
- `read(dst) == -1`: EOF; finish/close the read half according to the protocol.

Do not collapse all three cases into a single “done” state. In particular, awaiting readiness must match connection state and protocol conditions; for instance, a `SocketChannel` may still have an incomplete connection or transfer data asynchronously.

### Non-Blocking Send Algorithm Skeleton (Illustration)

```java
// Java-like pseudocode: src is already in read mode, channel is non-blocking.
// This snippet does not handle Selector itself and is not standalone.
while (src.hasRemaining()) {
    int n = channel.write(src);

    if (n == 0) {
        // Save src/position, register for the next write opportunity;
        // end the current processing turn, do not spin.
        break;
    }
}
```

Do not call `src.clear()` after only a partial send. The remaining bytes sit in `[src.position(), src.limit())`. Once notified that writing can continue, reuse the same buffer or preserve equivalent state; if you also need to receive more data beforehand, coordinate `compact()` and `flip()` in the proper phase.

## 10. EOF, Close, and I/O Errors

The **read** and **write** contracts differ:

- **`read` returns `-1`** at end of source; that is a normal API value, not inherently an I/O error.
- **`write` does not use `-1` to signal EOF**. If the peer closes or an error occurs, the operation may throw `IOException` or a more specific exception.
- **`close()`** closes the channel. `isOpen()` reflects the channel's open/closed state; a closed channel cannot be “reopened” by calling `read` or `write`.
- **`ClosedChannelException`** can be thrown when operating on an already closed channel. In some cases, asynchronous closing or thread interruption during I/O can lead to `AsynchronousCloseException` or `ClosedByInterruptException` depending on the implementation.
- **`NonReadableChannelException` / `NonWritableChannelException`** occur on channel types supporting read/write permissions when opened with an incompatible mode.

It is best to manage channel lifecycles with `try-with-resources`:

```java
try (ReadableByteChannel source = /* initialized channel */) {
    // Read from source, handle EOF and IOException.
}
```

This is an **illustrative skeleton** and not a compilable standalone program because the channel creation expression is omitted. Closing a channel can also close the underlying stream/resource when using adapters like `Channels.newChannel(stream)`; design resource ownership clearly.

Do not use `isOpen()` as a guard guaranteeing that the subsequent I/O call will succeed: between the two calls, another thread could close the channel. Always handle exceptions at the read/write operation itself.

## 11. Channel vs. Stream: When to Use Which?

Classic Java IO has `InputStream.read(byte[])` and `OutputStream.write(byte[])`; NIO channels read/write via `ByteBuffer`. Both have their place.

| Aspect | `InputStream` / `OutputStream` | Byte Channels |
| --- | --- | --- |
| Data interface | Single byte, `byte[]` | `ByteBuffer` |
| Transfer region control | Array offset and length | `position`, `limit`, `remaining` |
| NIO integration | Via adapters or other APIs | Native interaction with buffers; some channels support selectors |
| Short reads/writes | Still must be handled per each API's contract | Must handle returned byte count, partial writes, EOF |
| Random positioning | Not a general capability of all streams | Supported by `SeekableByteChannel`/`FileChannel` when needed |

You can convert via `Channels`:

- `Channels.newChannel(InputStream)` → `ReadableByteChannel`.
- `Channels.newChannel(OutputStream)` → `WritableByteChannel`.
- `Channels.newInputStream(ReadableByteChannel)` → `InputStream`.
- `Channels.newOutputStream(WritableByteChannel)` → `OutputStream`.

Adapters help reuse IO components, **without automatically turning sources/sinks into non-blocking** or allowing every channel to join a `Selector`. Choosing streams or channels also depends on format, complexity, blocking policy, buffer reuse, and real performance measurements; do not assume NIO is always faster than traditional IO across every workload.

## 12. Extended Interfaces in the NIO Ecosystem

Once you understand the three fundamental interfaces, you can recognize several extended capabilities:

- **`ScatteringByteChannel`**: reads data from a single channel into multiple `ByteBuffer`s in sequence.
- **`GatheringByteChannel`**: writes data from multiple `ByteBuffer`s out to a single channel in sequence.
- **`SeekableByteChannel`**: adds position and size for a randomly accessible resource.
- **`FileChannel`**: channel for file I/O, extending read/write and positioning capabilities, adding data transfer operations, file locking, and memory mapping.
- **`SocketChannel`**: channel for socket connections, supporting both reading and writing along with non-blocking/selector mechanisms.

These capabilities have **their own contracts**; `ByteChannel` does not itself provide `position(long)`, `transferTo`, `map`, `configureBlocking`, or `register`. When a program needs specific functionality, declare the appropriate interface/class type rather than assuming every channel shares the same API.

## 13. API Pitfalls and How to Avoid Them

| Mistake | Impact | Right Approach |
| --- | --- | --- |
| Calling `channel.read(buffer)` once and assuming everything was read | Data loss if only a partial read occurred | Track returned byte count and loop/wait per protocol |
| Treating `read == 0` as EOF | Premature termination, especially in non-blocking mode | **Only `-1` signals EOF** |
| Using an infinite loop when `read/write == 0` | Busy spin, wasting CPU | Use readiness/selector or an appropriate wait mechanism |
| Calling `write` once then `clear` | Drops unsent bytes | Keep the `remaining` region and continue writing |
| Forgetting `flip` after `put` or after `read` into buffer | Wrong byte region sent out or decoded | Switch to read mode before consuming |
| Calling `read` into a full buffer | No room left to receive bytes | Process first, then `clear` or `compact` |
| Expecting `ByteChannel` to have `seek` | API does not define seek | Use `SeekableByteChannel`/`FileChannel` |
| Calling `write` on a `FileChannel` opened READ-only | `NonWritableChannelException` | Open with `WRITE` if writing is needed |
| Assuming channels are always safe across multiple threads | Depends on implementation and buffer sharing | Check thread-safety contract and manage buffer ownership |
| Not closing channels | Resource leaks | `try-with-resources` |
| Calling `isOpen` and trusting the next I/O call will succeed | Channel can be closed concurrently | Handle exceptions at `read`/`write` |
| Thinking ByteChannel decodes UTF-8 automatically | Channels transfer **bytes**, not text | Use `CharsetDecoder`/`CharsetEncoder` or a suitable codec |

## 14. Self-Check Questions

**Scenario A.** A `ReadableByteChannel` transfers two bytes into a newly created `ByteBuffer.allocate(8)`. What are the buffer's `position` and `limit` after `read`?

**Answer:** If `read` actually returned `2`, `position=2` and `limit=8`. Calling `flip()` produces `position=0`, `limit=2` to read the exact two received bytes. You must not assume these two bytes form a single character or a complete message.

**Scenario B.** `WritableByteChannel.write(src)` returns 3 when `src.remaining()==9` beforehand. How many bytes remain unsent?

**Answer:** `9 - 3 = 6` bytes remain. `src.position()` advances by 3; `src.limit()` stays unchanged. Do not call `clear` and lose the unsent portion.

**Scenario C.** A non-blocking `SocketChannel` has room in its buffer, yet `read(dst)` returns 0. Can you conclude the peer closed the connection?

**Answer:** No. The value 0 can mean no bytes are currently ready. Only `-1` indicates EOF in the read contract. You must use readiness and the corresponding protocol state.

**Scenario D.** Can a variable of type `ByteChannel channel` call `channel.position(0)`?

**Answer:** No, the `ByteChannel` interface does not have that method. If the object is a `SeekableByteChannel`, declare the proper type or use a verified type to call `position(long)`.

## 15. Takeaways

- **`ReadableByteChannel` reads from a source into a `ByteBuffer`**: `>0` gives bytes received, `0` means no progress yet, **`-1` means EOF**.
- **`WritableByteChannel` writes from a `ByteBuffer` to a destination**: returns bytes actually written, which can be less than `remaining()`. Do not discard remaining data.
- **`ByteChannel` combines read and write**, yet **does not itself define seek, non-blocking mode, or guaranteed simultaneous read/write**.
- **`ByteBuffer.position/limit` determine which bytes are exchanged**; `flip`, `clear`, and `compact` are the primary phase-transition tools.
- Use `try-with-resources`, handle `IOException`, distinguish **0 from EOF**, and pick concrete channel classes according to your needs.
- For files requiring positional access, turn to **`SeekableByteChannel` or `FileChannel`**; for non-blocking sockets, properly structure the readiness lifecycle and pending outbound data.

**Standard documentation:** Java SE 17 API: `java.nio.channels.Channel`, `ReadableByteChannel`, `WritableByteChannel`, `ByteChannel`, `SeekableByteChannel`, `FileChannel`, `SocketChannel`, `Channels`, and `java.nio.ByteBuffer`.
