# How Does a Channel Differ from InputStream and OutputStream in Java?

In Java, **`InputStream` / `OutputStream`** in `java.io` and **Channel** in `java.nio.channels` can both transport **bytes**, but they organize I/O operations around different models. Understanding the differences helps you choose the right API when reading files, sending data over sockets, processing large files, or needing to access specific positions in a file.

- **Stream** represents a flow of bytes read from a source (`InputStream`) or written to a destination (`OutputStream`), with methods centered around `int` and `byte[]`.
- **Channel** represents an I/O connection whose capabilities are expressed through interfaces: reading, writing, both, seeking, direct transfer, or event-selection mechanisms if it is the *right kind of channel*. The typical byte read/write API uses **`ByteBuffer`**.
- **Not every Channel is bidirectional, not every Channel is non-blocking, and Stream does not mean always slow.** Capabilities depend on the specific channel/stream type, where the data is stored, and how it is used.

A small text file is often a great fit for `Files.readString`, `BufferedReader`, or `InputStream`. Meanwhile, reading part of a file by offset, writing a record at a specific position, transferring bytes between two channels, or network programming with `Selector` are cases where NIO channels show their distinct strengths.

## 1. Foundations: Stream Is Byte-Oriented, Channel Is I/O Capability

### `InputStream` and `OutputStream`

`InputStream` is the abstract class for **reading bytes**; `OutputStream` is the abstract class for **writing bytes**:

```java
int one = in.read();                   // 0..255 or -1 at EOF
int n = in.read(data, 0, data.length); // actual bytes read or -1 at EOF
out.write(data);                       // attempts to write the entire array or throws IOException
out.flush();                           // flushes buffered data if the stream has a buffer
```

This is an **API illustration snippet**, assuming `in`, `out`, and `data` have already been initialized. Do not assume a single `read(byte[])` call always fills the array: it can return fewer bytes than requested. Even though `OutputStream.write(byte[])` does not return a byte count, calling it can fail with `IOException`; you should not interpret it as an atomic write transaction or a guarantee that the data is already on disk.

Streams are commonly composed with wrapper classes:

- `BufferedInputStream` / `BufferedOutputStream` add a buffer to reduce the number of calls to the underlying source/destination.
- `DataInputStream` / `DataOutputStream` read/write primitive values using their own format; they do not turn a stream into a random-access store.
- `InputStreamReader` / `OutputStreamWriter` convert bytes ↔ characters according to a `Charset`. `BufferedReader` processes line by line after characters have been decoded.
- `FileInputStream` / `FileOutputStream` use files; `ByteArrayInputStream` / `ByteArrayOutputStream` use in-memory data; sockets can also provide streams.

You can use streams from start to finish without creating or managing a `ByteBuffer`. Sequential reading and wrapping with filters/decoders are key advantages of this model.

### Channel

The interfaces in `java.nio.channels` distinguish capabilities more explicitly:

| Interface / Class | Core Contract | Examples |
| --- | --- | --- |
| `Channel` | Has open/closed state, `isOpen()` and `close()`; **does not yet promise read/write capability**. | Base for other channels. |
| `ReadableByteChannel` | `read(ByteBuffer dst)` reads bytes into a buffer. | `FileChannel`, `SocketChannel`, `Pipe.SourceChannel`. |
| `WritableByteChannel` | `write(ByteBuffer src)` writes remaining bytes from a buffer. | `FileChannel`, `SocketChannel`, `Pipe.SinkChannel`. |
| `ByteChannel` | Combines read and write capabilities; **adds no new methods of its own**. | `FileChannel`, `SocketChannel`. |
| `SeekableByteChannel` | `position()`, `position(long)`, `size()`, `truncate(long)` for a variable-length byte sequence entity. | `FileChannel` or a channel returned by `Files.newByteChannel` if supported. |
| `FileChannel` | Channel bound to a file: absolute-offset access, `map`, `transferTo/transferFrom`, `force`, file locking, etc. | File read/write, random access. |
| `SelectableChannel` | Can be registered with a `Selector`; can be configured blocking/non-blocking when the channel type supports it. | `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`. |
| `AsynchronousFileChannel` | Asynchronous API with `Future` or callbacks, distinct from standard synchronous `FileChannel`. | Asynchronous file access. |

Do not see the name “NIO” and assume all channels use `Selector` or are non-blocking. `FileChannel` is not a `SelectableChannel` and cannot be registered directly with a `Selector`. Conversely, a `SocketChannel` can be configured with `configureBlocking(false)` and combined with a `Selector`.

## 2. Accurate Comparison of Important Differences

| Criterion | `InputStream` / `OutputStream` | NIO Channel |
| --- | --- | --- |
| API unit | Single byte or `byte[]` array. | Usually `ByteBuffer`; some channels support multiple buffers. |
| Data direction | Two separate classes: read or write. | Capabilities determined by interface: read, write, both, or other capabilities. |
| Read result | `read()` returns byte `0..255` / `-1`; `read(byte[])` returns byte count or `-1`. | `read(ByteBuffer)` returns byte count or `-1`; may return `0` depending on buffer/state/blocking. |
| Write result | `write(...)` returns `void` per stream contract. | `write(ByteBuffer)` returns actual bytes written; may be a short write or `0`. |
| Buffer management | `byte[]` and optional `Buffered*Stream`. | `ByteBuffer` has `position`, `limit`, `capacity`; has heap/direct buffers. |
| Offset movement | `InputStream` has no general “set file position by offset” method (some streams have `skip` or conditional `mark/reset`). | Only **seekable** channels have `position(long)`; `FileChannel` also supports absolute-offset read/write. |
| Non-blocking/selector | The core stream API is typically used in a blocking manner; no `register(selector)`. | Certain **selectable** channels support non-blocking/`Selector`; not universally applicable. |
| File specifics | Can read/write files via streams; a few file streams have `getChannel()`. | `FileChannel` specializes in file mapping, transfer, locking, force, and positional I/O. |
| Convenient operations | Stream wrappers, `readNBytes`, `transferTo(OutputStream)`, `Reader/Writer`. | Positional I/O, scattering/gathering, file channel transfer, event-driven socket I/O. |
| Resource closing | `Closeable` / `AutoCloseable`; `try-with-resources` recommended. | `Channel extends Closeable`, `try-with-resources` also recommended. |

The two columns only compare **API contracts**, not performance across all workloads. A `BufferedInputStream` reading a small file can be faster and simpler than manually allocating and managing a `ByteBuffer`. `FileChannel.transferTo` can be optimized by the OS to reduce data copies, yet it can still transfer fewer bytes than requested or use a fallback path depending on the environment.

## 3. Buffer Differences: `byte[]` vs. `ByteBuffer`

With streams, the buffer is typically an array passed in by the caller:

```java
byte[] block = new byte[4096];
int n = in.read(block);
if (n > 0) {
    // Only block[0..n-1] contains the newly read data.
}
```

This is an illustration snippet; the variable `in` is declared externally. After reading, `n` indicates the meaningful data in the array; the API does not store `position/limit` on the array itself.

With channels, the buffer carries its own **positional state**:

```java
ByteBuffer buffer = ByteBuffer.allocate(4096);
int n = channel.read(buffer); // writes into buffer from position to limit
buffer.flip();                // switches to mode for reading the data that was read
// ... read data from buffer using get() / decoder ...
buffer.clear();               // prepares the region for the next read
```

This is an illustration snippet; the variable `channel` is an open `ReadableByteChannel`. Explanation of the three properties:

- `capacity`: fixed capacity of the buffer.
- `position`: index of the next read/write.
- `limit`: boundary of what can be read/written in the current operation.

For example, a buffer of capacity `8` receives `3` bytes from a channel read: after reading, `position=3`, `limit=8`; after `flip()`, `position=0`, `limit=3`; after calling `get()` three times, `position=3`. `clear()` does not zero out bytes; it only resets the state to accept new data. If unprocessed bytes remain when you want to receive more data, use `compact()` to move the remaining bytes to the beginning and continue receiving.

**Very common mistake:** calling `StandardCharsets.UTF_8.decode(buffer)` right after `channel.read(buffer)` and forgetting `flip()`; the decoder will inspect the range from the current `position` to `limit`, often resulting in missing data or an empty/wrong result. Conversely, `flip()` is not something to call at every step: with `ByteBuffer.wrap(bytes)`, the buffer initially has `position=0` and `limit=bytes.length`, already ready for a channel to **write out**.

`ByteBuffer.allocate(...)` creates a heap buffer; `ByteBuffer.allocateDirect(...)` creates a direct buffer which can be helpful for certain native I/O paths, though allocation has overhead and is not guaranteed to always be faster. Measure with your actual workload. A `ByteBuffer` shared across multiple threads is also not thread-safe on its own because `position`/`limit` are mutable.

## 4. Position Differences: Sequential Stream vs. Potentially Random-Access Channel

`InputStream` advances as data is read. The `skip(long)` method only requests skipping bytes forward and may skip fewer than requested; `mark/reset` is not supported by every stream and does not represent an arbitrary absolute offset in a file. `OutputStream` has no standard API to “write at byte 100” of the same stream object.

`FileChannel` can:

```java
channel.position(100);        // sets current file position
channel.read(buffer);         // reads from current position; position advances by bytes read

channel.read(buffer, 500);    // reads from byte 500, does NOT change current position
channel.write(buffer, 200);   // writes at byte 200, does NOT change current position
```

This is an illustration snippet when `channel` is a `FileChannel` and the buffer is properly prepared; calls may still read/write fewer bytes than expected. Both `channel.position(100)` and the positional overloads only make sense for **channel types that support them**. `SocketChannel` has no `position(long)` method because a socket is a network byte stream connection, not a seekable file.

When using `FileInputStream.getChannel()` / `FileOutputStream.getChannel()`, the channel is tied to that stream and shares the file position of the same file descriptor: changing the position or reading/writing from one side can affect the position observed through the other side. **Do not assume a stream and the channel obtained from it have two independent cursors.** If multiple operations share the current position, they must coordinate according to application requirements. Opening two separate handles creates separate cursor states, but it does not turn the file data into two separate copies.

### Standalone Example: Sequential Stream Read, Offset FileChannel Read/Write

Create `StreamChannelComparison.java`:

```java
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class StreamChannelComparison {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("nio-contrast-", ".txt");
        try {
            Files.writeString(file, "ABCDEFG", StandardCharsets.US_ASCII);

            try (InputStream in = Files.newInputStream(file)) {
                byte[] first = in.readNBytes(3);
                System.out.println("stream=" + new String(first, StandardCharsets.US_ASCII));
            }

            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                ByteBuffer receive = ByteBuffer.allocate(3);
                int n = channel.read(receive, 4);
                receive.flip();
                System.out.println("channel-bytes=" + n);
                System.out.println("channel-data=" +
                        StandardCharsets.US_ASCII.decode(receive));
                System.out.println("current-position=" + channel.position());

                ByteBuffer replacement = ByteBuffer.wrap(
                        "xy".getBytes(StandardCharsets.US_ASCII));
                long offset = 1;
                while (replacement.hasRemaining()) {
                    int written = channel.write(replacement, offset);
                    if (written == 0) throw new IOException("Write stalled");
                    offset += written;
                }
            }
            System.out.println("final=" + Files.readString(file, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Run on Java 17+:

```bash
javac --release 17 StreamChannelComparison.java
java StreamChannelComparison
```

Output:

```text
stream=ABC
channel-bytes=3
channel-data=EFG
current-position=0
final=AxyDEFG
```

**Why does it produce this output?**

1. `Files.newInputStream` reads three consecutive bytes starting from the beginning of the file, producing `ABC`.
2. `channel.read(receive, 4)` reads three bytes at offset `4..6` giving `EFG`, but **does not move** the channel's current position, so it remains `0`.
3. `receive.flip()` allows the decoder to read the three bytes just read.
4. `channel.write(replacement, offset)` writes `xy` at offset `1..2`; the loop guards against a single write not draining the entire buffer. The final content is `AxyDEFG`.
5. `try-with-resources` closes the stream and channel. The temporary file is deleted in `finally`.

The program intentionally uses ASCII so that a one-byte offset corresponds to one character. With UTF-8, positional read/write must handle character byte boundaries properly and use a clear record/encoding format.

## 5. Blocking vs. Non-Blocking: Differs by *Channel Type*, Not by the NIO Name

A common misconception is “`java.io` is blocking, `java.nio` is always non-blocking”. Java NIO has both **blocking** channels and channels that can be **non-blocking**.

- A regular `FileChannel` performs synchronous reads/writes with `read/write` calls; it is not a `SelectableChannel` and cannot use a `Selector` to wait for a file to become readable as with sockets.
- `SocketChannel` can be in blocking mode by default or configured with `configureBlocking(false)`, in which case `read/write` may return `0` if no data is available yet or it cannot write yet. Combining with `Selector` avoids dedicating a separate waiting thread per connection, depending on server architecture.
- `AsynchronousFileChannel` is a separate class providing asynchronous file operations with completion callbacks or `Future`; seeing “channel” in the name does not turn regular `FileChannel` into an asynchronous API.
- `InputStream.read` under its general contract waits for data, EOF, or an error when no bytes are available; however, the exact behavior of a specific stream wrapper/provider still has to be understood from its API.

`Selector` also **does not automatically speed up file reads** or turn every byte stream into events. For large files on disk, `FileChannel` is chosen mainly for byte buffer operations, offsets, transfers, mapping, or file control. For thousands of sockets, selectable/non-blocking channels can provide a very different I/O model than streams paired with thread-per-connection.

## 6. Read/Write Calls Do Not Guarantee the Same Byte Count

Distinguish the I/O contracts to avoid losing data:

### With `InputStream`

- `read()` returns `0..255` for one byte or `-1` at EOF. A byte with value `0xFF` becomes `255`, **not** `-1`.
- `read(byte[])` returns the actual bytes read or `-1` at EOF; do not assume one call always fills the array.
- `readNBytes(length)` is convenient when you want at most a given number of bytes; it may return fewer if EOF arrives first. `readAllBytes()` is convenient for small bounded data, but unsuitable when file/response size is untrusted and could be huge.
- If you need exactly `N` bytes in a binary protocol, loop until enough are read or use an API with “read fully or error” semantics, such as `DataInputStream.readFully(byte[])`; EOF must be handled appropriately.

### With Channel

- `ReadableByteChannel.read(ByteBuffer)` can return a positive number smaller than `remaining`, return `0` when no bytes are transferred in certain cases, or `-1` at EOF.
- `WritableByteChannel.write(ByteBuffer)` returns **the number of bytes consumed** from the buffer; it may be `0` or less than `remaining`.
- After reading, you need `flip` before consuming; after partial processing, you need `compact` if you want to keep remaining data; when writing, loop until `!buffer.hasRemaining()` or apply an appropriate non-blocking/backpressure policy.
- With non-blocking channels, do not busy-loop when `read/write == 0`: register events with `Selector` or reschedule appropriately.

Synchronous write loop pattern (illustration snippet, `out` is an open `WritableByteChannel`):

```java
while (buffer.hasRemaining()) {
    int n = out.write(buffer);
    if (n == 0) {
        throw new IOException("Blocking write made no progress");
    }
}
```

This pattern fits blocking channels / small-data examples where `0` is abnormal. **Do not copy the “throw on 0” policy verbatim into non-blocking network channels**, where `0` is a normal condition and you must manage `OP_WRITE`/backpressure instead of throwing an error or spinning the CPU.

## 7. Streams and Channels Can Connect to Each Other

You do not need to rewrite an entire application to bridge between the two API families: `java.nio.channels.Channels` provides adapters.

| What You Want | API | Things to Remember |
| --- | --- | --- |
| `ReadableByteChannel` from `InputStream` | `Channels.newChannel(input)` | Adapter reads through the underlying stream; does not add seek/random access or non-blocking. |
| `WritableByteChannel` from `OutputStream` | `Channels.newChannel(output)` | Adapter writes through the underlying output stream; does not create a file channel. |
| `InputStream` from `ReadableByteChannel` | `Channels.newInputStream(channel)` | Stream reads via the underlying channel; shares state/resource closing. |
| `OutputStream` from `WritableByteChannel` | `Channels.newOutputStream(channel)` | Stream writes via the channel; does not turn the channel into durable storage. |
| `Reader` / `Writer` from a byte channel | `Channels.newReader(...)` / `newWriter(...)` | Decodes/encodes characters per charset; be careful with Vietnamese characters and characters split across buffers. |

Some adapters used on a selectable channel require the channel to be in **blocking mode** for the bridged call; otherwise you may encounter `IllegalBlockingModeException` depending on the API. Using an adapter does not mean asynchronous or non-blocking; when designing networking around `Selector`, you usually want to use `ByteBuffer`/`SocketChannel` directly.

**Ownership:** the wrapper and the underlying channel/stream typically share lifecycle ownership. Closing the adapter may close the source channel/stream, so you must not assume you can continue reusing the original resource after closing the wrapper. Avoid giving two parts of a program authority to independently close the same connection while one part is still using it.

### Standalone Example: stream ↔ channel and UTF-8

Create `ChannelBridgeDemo.java`:

```java
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;

public class ChannelBridgeDemo {
    public static void main(String[] args) throws IOException {
        byte[] encoded = "học Java".getBytes(StandardCharsets.UTF_8);

        try (ReadableByteChannel input =
                Channels.newChannel(new ByteArrayInputStream(encoded))) {
            ByteBuffer buffer = ByteBuffer.allocate(encoded.length);
            while (buffer.hasRemaining()) {
                int n = input.read(buffer);
                if (n < 0) break;
                if (n == 0) throw new IOException("Read stalled");
            }
            System.out.println("bytes=" + buffer.position());
            buffer.flip();
            System.out.println("decoded=" + StandardCharsets.UTF_8.decode(buffer));
        }

        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (WritableByteChannel output = Channels.newChannel(sink)) {
            ByteBuffer buffer = ByteBuffer.wrap(
                    "OK".getBytes(StandardCharsets.UTF_8));
            while (buffer.hasRemaining()) {
                if (output.write(buffer) == 0) throw new IOException("Write stalled");
            }
        }
        System.out.println("sink=" + sink.toString(StandardCharsets.UTF_8));
    }
}
```

```bash
javac --release 17 ChannelBridgeDemo.java
java ChannelBridgeDemo
```

Output:

```text
bytes=10
decoded=học Java
sink=OK
```

The phrase `học Java` has **8 characters** but is UTF-8 encoded into **10 bytes**: the letter `ọ` takes three UTF-8 bytes; the remaining characters in the example each take one byte. `ByteBuffer.position()` after reading shows 10 bytes were received; `flip()` prepares it for `UTF_8.decode(...)` to reconstruct the text. On the write side, `Channels.newChannel(sink)` wraps `ByteArrayOutputStream` as a `WritableByteChannel`, then decodes what was written without needing a real file.

The example uses an in-memory byte source so the byte count and output are deterministic. With a real socket or stream where data arrives in multiple chunks, accumulation and decoding must manage incomplete UTF-8 bytes across read boundaries; you should not decode each chunk in isolation assuming it always ends on a character boundary.

## 8. Extra Features of Some Channels Not Directly Present on Core Streams

### `FileChannel.transferTo / transferFrom`

`FileChannel.transferTo(position, count, target)` transfers data from a file region to a `WritableByteChannel`. `transferFrom(src, position, count)` receives data from a `ReadableByteChannel`. These are useful APIs when moving large amounts of bytes between files and I/O channels.

```java
long moved = sourceFileChannel.transferTo(offset, remaining, targetChannel);
```

The snippet above is illustrative; `sourceFileChannel`/`targetChannel` are already open. **Do not assume `moved == remaining`**: the result may be smaller (including `0`), so the application must handle remaining bytes, EOF, and lack-of-progress situations. Some OSes have zero-copy-style optimizations, but there is no guarantee of “always zero-copy” or “always faster than every stream”.

### File mapping

`FileChannel.map(...)` creates a `MappedByteBuffer` for a region of a file, which can reduce copy operations or support accessing data with a memory-mapping model. This is a capability **of `FileChannel`**, not of every `Channel`. You must consider mapping limits, mapping lifecycle, consistency with other writers, flushing, and off-heap memory resources; do not choose mapping by default for every file.

### Scattering / gathering

A `ScatteringByteChannel` can read sequentially into multiple `ByteBuffer`s in a single operation; a `GatheringByteChannel` can write from multiple buffers. For example, a record format consisting of a header and payload can use separate buffers and combine them. A single call can still process fewer bytes than requested, so you must check the actual byte count and each buffer's state. Not every `ByteChannel` supports these interfaces.

### File locking and metadata

`FileChannel.lock`/`tryLock` supports locking file regions when the runtime environment and file store satisfy the contract; they **do not replace in-JVM synchronization locks** for protecting multi-threaded sequences of record updates. `Files`/`Path` and file attribute views handle most metadata operations; having a `FileChannel` does not mean every file property is a method on the channel.

## 9. Performance: Choose by Workload, Not by Slogan

There is no rule that “NIO is always faster than IO”:

1. **Small files, single thread, simple code:** `Files.readString`, `Files.writeString`, `BufferedInputStream`, `BufferedReader` are usually easy to read and completely appropriate.
2. **Large data processed sequentially:** chunked processing with either `BufferedInputStream` or `FileChannel` can be efficient. Avoid `readAllBytes()` on an unbounded-size source.
3. **Need fixed offsets / random access:** `FileChannel` or `SeekableByteChannel` has `position`; `FileChannel` has explicit offset read/write overloads.
4. **Transferring file regions across channels:** evaluate `transferTo` / `transferFrom`, handle partial transfers, and measure on the target OS.
5. **Many concurrent sockets:** `SocketChannel` + `Selector`/non-blocking can help when networking requirements lean toward an event loop; complexity is higher with partial reads/writes, backpressure, and scheduling.
6. **Text encoding / line reading:** `Reader`/`Writer`, `BufferedReader`, or `Channels.newReader/newWriter` handle charsets; a raw `ByteBuffer` does not know where character boundaries lie.

To compare performance you need to identify throughput, latency, number of I/O calls, buffer size, heap/direct allocation, OS file cache, read-ahead, SSD/network, and decode/copy costs. Some high-level APIs in `Files` may use NIO mechanisms underneath; comparing “packages” is no substitute for actual measurement. If the operation is simply copying a file, `Files.copy(source, target)` may be even more suitable than writing a custom stream/channel loop.

## 10. Common Mistakes When Moving from Stream to Channel

| Symptom | Cause | Fix |
| --- | --- | --- |
| Reading into a buffer then decoding produces an empty/wrong string | Forgot `flip()`; `position` is at the end of the newly written region. | Call `flip()` before reading from the buffer; `compact()` when retaining leftover data. |
| Only part of the payload is written | Assumed `channel.write(buffer)` handles all data in one call. | Loop on `buffer.hasRemaining()` following the blocking/non-blocking contract. |
| High CPU when socket cannot read/write yet | Busy-looping when non-blocking `read/write` returns `0`. | Use `Selector`/interest ops and proper backpressure. |
| Reading wrong bytes after changing offset | Sharing current position of the same channel or a stream obtained from the channel. | Positional read/write, locking, or clear ownership per connection. |
| `IllegalBlockingModeException` with an adapter | Wrapping a selectable channel not in the blocking mode required by the adapter. | Understand modes; choose direct channel APIs when operating non-blocking. |
| Assuming every channel supports `position` | Only `SeekableByteChannel` has the seek contract. | Use the right interface for files; do not seek `SocketChannel`. |
| Corrupted Unicode when reading a file | Using byte offset as character index, splitting UTF-8 mid-code-point, or using an implicit charset. | Choose `StandardCharsets.UTF_8` and boundary-aware decoding; use `Reader` when character-oriented. |
| Calling `flush()` thinking data is synced to disk | `OutputStream.flush` only pushes bytes remaining in implementation-level buffers. | Consider `FileChannel.force` or an appropriate API/FS when durability is truly required; verify platform contract. |
| Closing stream renders channel unusable | Wrapper and underlying resource share ownership/lifecycle. | Have a single owner for the resource; use `try-with-resources` at the right scope. |
| `transferTo` transfers fewer bytes than expected | Contract permits partial transfer/`0` depending on source and target state. | Controlled loop, check EOF, and handle lack of progress. |

Useful exceptions to know when working with channels include `ClosedChannelException`, `NonReadableChannelException`, `NonWritableChannelException`, and `IOException`. When changing network modes, `IllegalBlockingModeException` relates to how blocking and adapters/selectors interact; do not handle them by swallowing errors and assuming all bytes were transferred.

## 11. Decision Matrix: Which API to Choose?

| Need | Reasoned Choice |
| --- | --- |
| Read a small config file as text | `Files.readString(path, UTF_8)` — concise, clear intent. |
| Read a CSV file line by line | `Files.newBufferedReader(path, UTF_8)` or `BufferedReader` — decodes characters and reads lines. |
| Read a sequential binary stream from a network/library that already exposes `InputStream` | `InputStream` + appropriate buffer — leverage the existing API. |
| Write a binary stream to an API accepting `OutputStream` | `OutputStream` (`BufferedOutputStream` if needed) — avoid unnecessary adapters. |
| Operate at byte offsets or read disjoint parts of a file | `FileChannel.read/write(ByteBuffer, position)` or `SeekableByteChannel`. |
| Need to read and write the same file through one resource | `FileChannel` with `READ` and `WRITE` — bidirectional, explicit position. |
| Handle many sockets non-blocking with an event loop | `SocketChannel`/`ServerSocketChannel` + `Selector` — coordinate readiness. |
| Transfer a file region to a writable channel | `FileChannel.transferTo(...)` — may optimize transfer path, but handle partial transfers. |
| Already have an `InputStream` but library only accepts `ReadableByteChannel` | `Channels.newChannel(input)` — interface conversion with controlled lifecycle. |

### Self-Check Questions

**1. Why is a `FileChannel` a `ByteChannel` while a `Pipe.SourceChannel` is not a writable channel?**

Because `ByteChannel` unifies both `ReadableByteChannel` and `WritableByteChannel`. A pipe source's role is only to receive bytes from the source end and does not promise write capability; functionality depends on the actual interfaces implemented.

**2. What is the job of `ByteBuffer.flip()`?**

It sets `limit` to the current `position` and then resets `position` to `0`, preparing to consume the bytes just written into the buffer. It does not alter the byte contents and is not a flush command to disk.

**3. Why does `write(ByteBuffer)` often require a loop while `OutputStream.write(byte[])` does not return a byte count?**

The two APIs have different contracts. A writable channel returns the actual number of bytes transferred and may perform a short write or zero write; an output stream returns no byte count and may report failure via `IOException`. You cannot infer from that that an output stream guarantees atomicity or durability.

**4. Is `FileChannel` non-blocking like `SocketChannel`?**

Not in the sense of selectable non-blocking I/O. A regular `FileChannel` is a synchronous file-access channel and does not register with a `Selector`; `SocketChannel` can be configured non-blocking.

**5. Does `Channels.newChannel(InputStream)` turn an `InputStream` into a random-access file?**

No. It provides a channel-style reading adapter over the existing source; it does not create a `FileChannel` or add seek capability.

**6. When should you keep `InputStream` instead of switching to NIO?**

When the task is sequential reading, library interfaces already fit, performance is acceptable, and no channel-specific features are needed; simpler code is usually easier to maintain and test.

## Official Documentation

- [Java SE 21 — `InputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html) and [`OutputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/OutputStream.html): byte stream contracts.
- [Java SE 21 — `java.nio.channels` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/package-summary.html): interface hierarchy and channel model.
- [Java SE 21 — `FileChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): file positioning, positional I/O, transfer, mapping, and file locking.
- [Java SE 21 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip`, `clear`, `compact`.
- [Java SE 21 — `Channels`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Channels.html): adapters between channels, streams, readers, and writers.
- [Java SE 21 — `SocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): socket channel and blocking mode.

**Takeaway:** choose an API based on the capabilities you need and the contracts for bytes, buffers, offsets, blocking, and resource lifecycle. Streams are convenient for sequential processing; channels expand capabilities for operating on `ByteBuffer` and features specific to file/network channels, but neither choice is automatically better in every situation.
