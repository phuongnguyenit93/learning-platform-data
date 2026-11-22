# `Channels.newChannel()`, `newInputStream()`, and `newOutputStream()` in Java NIO

## 1. Goal and Context

Java provides two common I/O API families:

- **`java.io.InputStream` / `OutputStream`:** works with byte streams via `read()`, `read(byte[])`, `write(int)`, `write(byte[])`.
- **`java.nio.channels.ReadableByteChannel` / `WritableByteChannel`:** works with bytes through `ByteBuffer` via `read(ByteBuffer)` and `write(ByteBuffer)`.

When a legacy library expects a stream while your application holds a channel, or vice versa, you do not need to copy the entire file into RAM just to switch API types. The utility class **`java.nio.channels.Channels`** provides adapters that stay connected to the underlying I/O source/destination.

This lesson helps you:

1. Choose the right overload of `Channels.newChannel(InputStream/OutputStream)`, `Channels.newInputStream(ReadableByteChannel)`, and `Channels.newOutputStream(WritableByteChannel)`.
2. Understand byte flow, `ByteBuffer.flip()/clear()` rules, and partial read/write behavior.
3. Manage lifecycles properly: closing the adapter closes the underlying I/O source/sink.
4. Recognize blocking/nonblocking constraints, the absence of extra buffering, encoding when converting bytes to text, and the fact that an adapter does not turn a stream into a random-access channel.
5. Run Java 17+ examples bridging both directions, including `FileChannel` and `ByteArrayInputStream`.

This article is about **bridging byte I/O APIs**, not inventing a new filesystem or comparing the entire stream vs. channel architectures.

## 2. Bidirectional Conversion Map

```text
                    Channels.newChannel(...)
  InputStream  ---------------------------------->  ReadableByteChannel
   read(byte[])                                      read(ByteBuffer)

                    Channels.newChannel(...)
  OutputStream ---------------------------------->  WritableByteChannel
   write(byte[])                                     write(ByteBuffer)


                    Channels.newInputStream(...)
  ReadableByteChannel -------------------------->  InputStream
   read(ByteBuffer)                                  read(byte[])

                    Channels.newOutputStream(...)
  WritableByteChannel -------------------------->  OutputStream
   write(ByteBuffer)                                 write(byte[])
```

Types and methods:

| Input | Adapter Method | Result | Byte Direction |
| --- | --- | --- | --- |
| `InputStream` | `Channels.newChannel(in)` | `ReadableByteChannel` | Reads from stream into `ByteBuffer` |
| `OutputStream` | `Channels.newChannel(out)` | `WritableByteChannel` | Writes from `ByteBuffer` to stream |
| `ReadableByteChannel` | `Channels.newInputStream(ch)` | `InputStream` | Reads from channel into byte array or single byte |
| `WritableByteChannel` | `Channels.newOutputStream(ch)` | `OutputStream` | Writes byte array or single byte to channel |

`Channels` is a **utility class with static methods**; e.g. `Channels.newChannel(input)`, never `new Channels()`. These methods do not seek a file cursor back to the start, clone files, or open another network connection. They create a view over an existing source/destination.

Adapters still obey the direction of the underlying interface. `newChannel(InputStream)` gives you only a **readable** interface; you cannot call `write()` on that result. Similarly, `newChannel(OutputStream)` returns only a **writable** interface.

## 3. `Channels.newChannel(InputStream)`: Stream to Readable Channel

Signature:

```java
public static ReadableByteChannel newChannel(InputStream in)
```

This adapter lets code accepting a `ReadableByteChannel` consume an existing `InputStream`. Instead of reading into `byte[]`, the caller reads into a `ByteBuffer`:

```java
byte[] bytes = "ABC".getBytes(StandardCharsets.US_ASCII);
InputStream source = new ByteArrayInputStream(bytes);
ReadableByteChannel channel = Channels.newChannel(source);

ByteBuffer buffer = ByteBuffer.allocate(8);
int count = channel.read(buffer); // 3 bytes in this example
buffer.flip();
while (buffer.hasRemaining()) {
    System.out.print((char) buffer.get());
}
channel.close(); // also closes source
```

This snippet is **illustrative and requires imports** (not a standalone program). It shows the path of bytes:

1. `InputStream` supplies the bytes `A`, `B`, `C`.
2. `ReadableByteChannel.read(buffer)` puts bytes into the free `[position, limit)` region and advances `position` by the bytes placed.
3. `buffer.flip()` prepares to read back the newly loaded bytes via `get()`.
4. `channel.close()` closes the underlying source stream per the adapter contract.

`read(ByteBuffer)` returns the actual bytes read, which can be fewer than `buffer.remaining()` before the call. `-1` indicates end of input (EOF). If the buffer has no space left to receive data, a zero-byte read request may return 0; that does not mean EOF was reached. Do not assume every `read()` fills the buffer, even when the source has more data.

**The adapter adds no buffering of its own.** If the source is a `BufferedInputStream`, `BufferedInputStream`'s own buffer still exists; saying the adapter “adds no buffering” means it does not introduce another buffering layer with an independent caching policy.

## 4. `Channels.newChannel(OutputStream)`: Stream to Writable Channel

Signature:

```java
public static WritableByteChannel newChannel(OutputStream out)
```

When an API expects a `WritableByteChannel` but you only have an `OutputStream`, create an adapter:

```java
ByteArrayOutputStream destination = new ByteArrayOutputStream();
WritableByteChannel channel = Channels.newChannel(destination);

ByteBuffer buffer = ByteBuffer.wrap(new byte[] {65, 66, 67});
while (buffer.hasRemaining()) {
    int written = channel.write(buffer);
    if (written == 0) {
        throw new IOException("Write made no progress");
    }
}
channel.close(); // also closes destination
System.out.println(destination.toString(StandardCharsets.US_ASCII));
```

This snippet is illustrative and requires imports and `IOException` handling; with `ByteArrayOutputStream`, closing does not discard the bytes already written. Output:

```text
ABC
```

`write(ByteBuffer)` returns the actual number of bytes written and advances the buffer's position. Per the general `WritableByteChannel` contract, callers must handle **partial writes** when the result is smaller than the initial remaining bytes. Use `while (buffer.hasRemaining())` with a strategy for zero progress, avoiding infinite loops on non-blocking channels. The `OutputStream` adapter forwards writes to the underlying stream; it does not turn an `OutputStream` into a `FileChannel` with `position(long)`, `truncate()`, or `transferTo()`.

If the program only needs to copy an `InputStream` to an `OutputStream`, `InputStream.transferTo(OutputStream)` can be simpler. The adapter is useful when **an API signature requires a channel** or you are already processing data through `ByteBuffer`.

## 5. Complete Java 17+ Example: Stream → Channel → Destination Stream

Save the following program as **`StreamToChannelDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Channels;
import java.nio.channels.ReadableByteChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;

public class StreamToChannelDemo {
    public static void main(String[] args) throws IOException {
        byte[] input = "Xin chào NIO".getBytes(StandardCharsets.UTF_8);

        ByteArrayInputStream source = new ByteArrayInputStream(input);
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (ReadableByteChannel from = Channels.newChannel(source);
             WritableByteChannel to = Channels.newChannel(destination)) {

            ByteBuffer buffer = ByteBuffer.allocate(4);

            while (true) {
                int read = from.read(buffer);
                if (read == -1) {
                    break;
                }
                if (read == 0) {
                    throw new IOException("Unexpected read without progress");
                }

                buffer.flip();
                while (buffer.hasRemaining()) {
                    int written = to.write(buffer);
                    if (written == 0) {
                        throw new IOException("Write made no progress");
                    }
                }
                buffer.clear();
            }
        }

        System.out.println("bytes=" + destination.size());
        System.out.println("text="
                + destination.toString(StandardCharsets.UTF_8));
    }
}
```

Compile and run with JDK 17+:

```bash
javac StreamToChannelDemo.java
java StreamToChannelDemo
```

Stdout (UTF-8):

```text
bytes=13
text=Xin chào NIO
```

Explanation:

- The string `Xin chào NIO` has 12 Java characters at the normal code-point level, yet UTF-8 encodes `à` as two bytes; hence the data is **13 bytes**. Sizing relies on the actual `byte[]` rather than assuming `String.length()` equals byte count.
- The buffer is only 4 bytes to illustrate **multiple loop iterations**; UTF-8 characters can be split mid-character while transferring chunks. This **does not corrupt data** because the program reassembles the exact bytes first and decodes only at the end.
- `from.read(buffer)` advances position; `flip()` switches from loading into the buffer to reading from it; `to.write(buffer)` consumes the bytes; `clear()` prepares for the next chunk.
- `try-with-resources` closes both channels, which in turn closes the underlying streams per the adapter contract. `ByteArrayOutputStream.size()` and `toString(...)` remain usable after `close()` because this stream type retains its in-memory bytes.

**Do not call `new String(buffer.array(), UTF_8)` across the entire capacity after every `read()`:** the rest of the array may not contain newly received bytes, and a UTF-8 character may straddle two chunks. If an application must convert **bytes to text while streaming**, use a stateful `CharsetDecoder` or an appropriate `Reader` class.

## 6. `Channels.newInputStream(ReadableByteChannel)`: Channel to Readable Stream

Signature:

```java
public static InputStream newInputStream(ReadableByteChannel ch)
```

This adapter is useful when newer code opens data via `FileChannel` or a `ReadableByteChannel`, while a library requires an `InputStream` parameter:

```java
ReadableByteChannel channel = FileChannel.open(path, StandardOpenOption.READ);
try (InputStream input = Channels.newInputStream(channel)) {
    byte[] bytes = input.readAllBytes();
    // Process bytes; closing input also closes channel.
}
```

This is a non-standalone illustration; it assumes `path` is declared and points to a valid file, required imports are present, and the enclosing method handles `IOException`. `readAllBytes()` is reasonable for **small, bounded data**; avoid using it to pull huge files or unbounded network input into memory. You can replace it with a fixed-chunk `byte[]` read loop.

Important contract details of this stream adapter:

- `read()` and `read(byte[], off, len)` transfer bytes from the channel; when the channel reaches EOF, `read()` returns `-1` per the stream contract.
- The resulting stream has **no extra buffering**.
- The resulting stream **does not support `mark()` and `reset()`**; `markSupported()` returns `false`. If marking support is genuinely needed, consider `BufferedInputStream` and understand its `readlimit`.
- The stream is documented as **thread-safe across concurrent calls to the adapter's methods**; this does not make the entire resource, protocol, or uncoordinated I/O from other references thread-safe.
- **Closing the stream closes the underlying channel**. Do not reuse that channel after the stream is closed.

If a `FileChannel` currently has a non-zero position, the adapter reads starting from that current position; it does not proactively call `position(0)` or interpret record layouts for you. If the same channel is accessed through multiple references, changing the position can affect the next byte the adapter reads.

## 7. `Channels.newOutputStream(WritableByteChannel)`: Channel to Writable Stream

Signature:

```java
public static OutputStream newOutputStream(WritableByteChannel ch)
```

Now a library that only knows `OutputStream.write(byte[])` can still write to an existing channel:

```java
WritableByteChannel channel = FileChannel.open(
        path, StandardOpenOption.WRITE, StandardOpenOption.CREATE);

try (OutputStream output = Channels.newOutputStream(channel)) {
    output.write("hello".getBytes(StandardCharsets.UTF_8));
}
```

This illustration snippet needs `path`, imports, and `IOException` handling. Rules:

- `OutputStream.write(byte[], offset, length)` forwards bytes to the underlying channel; the adapter handles writes per the stream and byte-channel contracts.
- `newOutputStream` **adds no buffering of its own**, so if you want to batch many small writes, consider wrapping with `BufferedOutputStream` while understanding its `flush()/close()` semantics.
- **Closing the `OutputStream` closes the `WritableByteChannel`**.
- `flush()` at the stream layer does not mean the file has been durably synced to physical storage. When durability is required, evaluate `FileChannel.force(boolean)` or an appropriate API, as well as filesystem characteristics.
- If the underlying channel sits at some position and is seekable, bytes are written according to the channel's position/state; the adapter does not reopen the file in append mode or reset its position.

`OutputStream` has no `position(long)` method: the adapter does not turn a seekable channel into a seekable stream. If business logic requires modifying bytes at an offset, use `SeekableByteChannel` or `FileChannel` directly.

## 8. Complete Java 17+ Example: `FileChannel` → `OutputStream` / `InputStream`

Save as **`ChannelToStreamDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ChannelToStreamDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("channel-stream-", ".txt");

        try {
            byte[] bytes = "café".getBytes(StandardCharsets.UTF_8);

            FileChannel writable = FileChannel.open(
                    file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);

            try (OutputStream output = Channels.newOutputStream(writable)) {
                output.write(bytes);
            }
            System.out.println("write channel open=" + writable.isOpen());

            FileChannel readable = FileChannel.open(
                    file, StandardOpenOption.READ);

            byte[] copy;
            try (InputStream input = Channels.newInputStream(readable)) {
                copy = input.readAllBytes(); // only because this example is tiny
            }
            System.out.println("read channel open=" + readable.isOpen());
            System.out.println("UTF-8 bytes=" + copy.length);
            System.out.println("text=" + new String(copy, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac ChannelToStreamDemo.java
java ChannelToStreamDemo
```

Stdout when I/O operations succeed:

```text
write channel open=false
read channel open=false
UTF-8 bytes=5
text=café
```

`café` has 5 UTF-8 bytes: `c`, `a`, `f` take one byte each, while `é` takes two bytes. The two `isOpen=false` lines directly verify the resource-closing relationship: the adapter is what `try-with-resources` closes, yet the channel it wraps also transitions to closed.

The purpose of `Files.createTempFile` is to create test data in the temp area and delete it only after both channels close. If write permissions, read permissions, file deletion, or storage capacity fail, `IOException` may occur; these are I/O error cases that must be handled in real applications.

## 9. Blocking vs. Nonblocking: The Most Important Boundary

Some channels support **nonblocking** mode—for example, `SocketChannel` or `Pipe.SourceChannel` / `Pipe.SinkChannel`, which are `SelectableChannel`s. In nonblocking mode, `read(ByteBuffer)` / `write(ByteBuffer)` can return 0 when no data is available or writing is not possible yet.

Meanwhile, the adapters:

- `Channels.newInputStream(ReadableByteChannel)`
- `Channels.newOutputStream(WritableByteChannel)`

are designed for the standard stream interface. Per the Java 17 API, `read` / `write` calls on these adapters throw **`IllegalBlockingModeException`** if the underlying channel is in **nonblocking mode** at the time of the operation.

Therefore, you cannot use `Channels.newInputStream(nonblockingSocketChannel)` as a shortcut to bypass the `Selector` workflow. If the application has an event loop and nonblocking channels, keep using the channel API with a proper readiness strategy; switching to streams only fits when blocking access genuinely matches the design.

### Example Confirming `IllegalBlockingModeException` (Java 17+)

Save as **`NonBlockingAdapterDemo.java`**:

```java
import java.io.InputStream;
import java.nio.channels.Channels;
import java.nio.channels.IllegalBlockingModeException;
import java.nio.channels.Pipe;

public class NonBlockingAdapterDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);

            try (InputStream input = Channels.newInputStream(source)) {
                try {
                    input.read();
                    System.out.println("unexpected read");
                } catch (IllegalBlockingModeException expected) {
                    System.out.println("nonblocking channel rejected");
                }
            }
        }
    }
}
```

```bash
javac NonBlockingAdapterDemo.java
java NonBlockingAdapterDemo
```

Expected stdout per contract on successful run:

```text
nonblocking channel rejected
```

`Pipe` is created with no bytes written to `sink`; there is no wait for data at all: the adapter over a nonblocking channel immediately rejects the read call. `try-with-resources` closes the stream and also closes `source`; closing `source` again in the outer `try` remains valid.

The right fix if the application truly needs to wait for data is calling `source.configureBlocking(true)` before stream-style access (ensuring no conflict with selector registrations or other threads), or continuing to read using the nonblocking model with proper readiness/event-loop handling. **Never** loop calling `input.read()` while catching `IllegalBlockingModeException` to wait for I/O.

## 10. Overloads for `AsynchronousByteChannel`

In addition to adapters for `ReadableByteChannel` and `WritableByteChannel`, `Channels` in Java 17 also provides:

```java
InputStream  Channels.newInputStream(AsynchronousByteChannel ch)
OutputStream Channels.newOutputStream(AsynchronousByteChannel ch)
```

For instance, `AsynchronousSocketChannel` implements `AsynchronousByteChannel` and works directly with those overloads. By contrast, **`AsynchronousFileChannel` does not implement `AsynchronousByteChannel`**: its asynchronous read/write methods require a file position (`read(buffer, position)` / `write(buffer, position)`), so it cannot be passed directly to the two `AsynchronousByteChannel` overloads. When a program needs to pair an asynchronous byte channel with a library accepting only `InputStream` / `OutputStream`, these adapters supply the compatible stream interface.

Important semantic note: **stream APIs block synchronously on the thread using the stream**; wrapping an asynchronous channel does not turn `InputStream.read()` / `OutputStream.write()` calls into a nonblocking event-driven API. If you want to leverage callbacks or `Future`, use the channel's asynchronous methods directly.

Four points still apply to these overloads: there is no extra buffering, `newInputStream` does not support `mark/reset`, closing the stream closes the asynchronous channel, and I/O errors must be handled per the stream contract. Do not confuse these two overloads with wrapping a `SelectableChannel` configured in nonblocking mode as in the previous section.

## 11. Encoding and Buffering When Converting to Text APIs

`InputStream`, `OutputStream`, and byte channels **only transport bytes**. `Channels.newInputStream` / `newOutputStream` do not take a charset parameter and do not decode or encode UTF-8 for the application.

To read UTF-8 text when a library requires a `Reader`:

```java
Reader reader = new InputStreamReader(
        Channels.newInputStream(channel),
        StandardCharsets.UTF_8);
```

This is an illustrative snippet: it needs imports for `Reader`, `InputStreamReader`, `StandardCharsets`, `channel` declared as `ReadableByteChannel`, and proper closing of `reader`. Another option is `Channels.newReader(channel, StandardCharsets.UTF_8)`.

To write UTF-8 text when a library requires a `Writer`:

```java
Writer writer = new OutputStreamWriter(
        Channels.newOutputStream(channel),
        StandardCharsets.UTF_8);
```

This is likewise an illustrative snippet needing imports, `channel` as `WritableByteChannel`, and proper closing/flushing of `writer`. You can use `Channels.newWriter(channel, StandardCharsets.UTF_8)` where appropriate.

Why not call `new String(chunk, UTF_8)` after each channel read? A multi-byte character can be split across two chunks. `InputStreamReader`/`Channels.newReader` uses a stateful decoder that processes incoming bytes across chunk boundaries.

Note the multi-layer relationship:

```text
Channel <- Channels.newInputStream(channel) <- InputStreamReader <- BufferedReader
                                         close cascades from outside inward
```

Closing `BufferedReader` closes `InputStreamReader`, which closes the `InputStream` adapter, and finally closes the underlying channel. If another component still needs to use the channel, do not hand close authority to the outer layer or design an explicit resource ownership mechanism.

## 12. Resource Ownership and Cascading Close

`Channels.newChannel`, `newInputStream`, and `newOutputStream` do not create an independent copy of the source/destination. They typically share **the same byte stream and underlying source/destination state**; thus changing file position, reading ahead, flushing, or closing via one access path affects the other.

Closing contract:

| Adapter Created | Calling `close()` On | Effect |
| --- | --- | --- |
| `Channels.newChannel(InputStream)` | Returned channel | Closes underlying `InputStream` |
| `Channels.newChannel(OutputStream)` | Returned channel | Closes underlying `OutputStream` |
| `Channels.newInputStream(ReadableByteChannel)` | Returned stream | Closes underlying `ReadableByteChannel` |
| `Channels.newOutputStream(WritableByteChannel)` | Returned stream | Closes underlying `WritableByteChannel` |
| `newInputStream/newOutputStream(AsynchronousByteChannel)` | Returned stream | Closes underlying asynchronous channel |

If an object is managed elsewhere, decide clearly **who owns the right to close it**. For example, do not wrap `System.out` with `Channels.newChannel(System.out)` and close that channel inside a small helper if the program still needs to log via `System.out` afterward. Closing the adapter by design closes that stream too.

Helpful guidelines:

- Use `try-with-resources` on the **outermost owning adapter object**; avoid accidentally closing the underlying resource prematurely.
- Do not assume `flush()` on a stream equals durable persistence to disk. For critical data, consider `FileChannel.force(...)` and transaction/durability strategies.
- Do not call `read` or `write` from multiple paths into the same channel/stream without a coordination protocol, especially if the read/write position is shared.
- Thread-safety documented on the stream adapter **does not guarantee** upper-layer objects behave correctly if application state is mutated concurrently without synchronization.

## 13. Adapters Solve API Types, Not Every Channel Capability

Comparison table:

| Need | Choice |
| --- | --- |
| API takes only `ReadableByteChannel` but you have `InputStream` | `Channels.newChannel(input)` |
| API takes only `WritableByteChannel` but you have `OutputStream` | `Channels.newChannel(output)` |
| API takes only `InputStream` but you have `ReadableByteChannel` | `Channels.newInputStream(channel)` |
| API takes only `OutputStream` but you have `WritableByteChannel` | `Channels.newOutputStream(channel)` |
| Random-offset read/write in a file | Use `FileChannel` or `SeekableByteChannel` directly |
| Nonblocking sockets and many connections | Use `SelectableChannel` with `Selector` and readiness handling |
| Charset-aware text read/write | Use `Reader`/`Writer` and an explicit `Charset` |
| Load an entire small file into RAM, simple processing | `Files.readAllBytes` / `Files.readString` when within size limits |
| Copy large files between file channels | Consider `FileChannel.transferTo/transferFrom` where supported |

Adapters do not turn an `InputStream` into a `SeekableByteChannel`, do not provide `FileLock`, do not guarantee atomic operations, and do not create a `Selector`-registrable channel. They solely expose the matching read/write interface over the original source/destination.

If you need to use both an `InputStream` and a channel to read one file, how the read position is shared depends strictly on the underlying source and adapter. Avoid assuming both sides have independent cursors or coordinating I/O by switching APIs arbitrarily.

## 14. Common Mistakes, Symptoms, and Fixes

### Mistake 1: Choosing the Wrong Read/Write Direction

`Channels.newChannel(new FileInputStream(...))` returns `ReadableByteChannel`. If code needs a `WritableByteChannel`, supply an appropriate `OutputStream`. The compiler catches mismatched interface assignments.

### Mistake 2: Forgetting `flip()` or `clear()` When Copying via `ByteBuffer`

After `read(buffer)`, `position` points to the end of the loaded data. Without `flip()`, `write(buffer)` may write from the wrong region. After writing everything without `clear()`, the next read sees zero free space. Follow `read → flip → write all → clear`, or `compact` when preserving unconsumed bytes.

### Mistake 3: Assuming `write(buffer)` Consumes Everything

A single `WritableByteChannel.write(buffer)` call may write only part of the data. Use:

```java
while (buffer.hasRemaining()) {
    int written = channel.write(buffer);
    if (written == 0) {
        // For nonblocking channels: wait for OP_WRITE via Selector.
        // For blocking channels: diagnose lack of progress.
        throw new IOException("No write progress");
    }
}
```

This is a snippet; replace the `written == 0` branch with a policy suited to the channel type. Never CPU-spin when a channel is not ready.

### Mistake 4: Wrapping a Nonblocking Channel as a Stream and Calling `read()/write()`

`Channels.newInputStream` and `newOutputStream` for `ReadableByteChannel` / `WritableByteChannel` throw `IllegalBlockingModeException` when the underlying channel is in nonblocking mode. Continue using channel APIs and selectors for event-driven processing.

### Mistake 5: Assuming the Adapter Buffers or Transcodes Text

Byte adapters neither add buffering nor encode UTF-8. To reduce small I/O calls, add buffering at the appropriate layer; to work with characters, use `Reader`/`Writer` and an explicit charset.

### Mistake 6: Closing the Adapter and Continuing to Use the Source/Destination

`try-with-resources` closes the adapter and cascades to the underlying resource. Manage lifecycle and ownership carefully, especially with `System.in`, `System.out`, sockets, or shared channels.

### Mistake 7: Extrapolating Thread-Safety into Correct Application Logic

Adapter streams supporting concurrent calls do not automatically make record ordering, decoder state, transactions, or application locks thread-safe. A dedicated reader thread or explicit synchronization may be required.

### Mistake 8: Using `readAllBytes()` on Very Large Files or Unbounded Sources

`InputStream.readAllBytes()` can consume massive amounts of RAM. When size is unbounded, process in fixed chunks or use a streaming parser.

### Mistake 9: Wrapping Through Many Layers Without Tracking Who Flushes/Closes

A chain like `BufferedWriter(OutputStreamWriter(Channels.newOutputStream(ch)))` has multiple layers. Calling `flush` on the outer layer pushes buffered data down to lower layers without promising physical durability; calling `close` on the outer layer cascades all the way down to the channel. Only one component should own the final close decision.

### Mistake 10: Expecting Switching Adapters to Reset File State

Wrapping a `FileChannel` in an `InputStream` does not reset its position or reopen the file. When you need to read from a specific offset, set the position via the channel API (if permitted) or open a fresh resource with its own semantics.

## 15. Practice Questions and Exercises

1. An API expects `ReadableByteChannel`, while you have a `BufferedInputStream`. Which method should you call? How does closing the returned object affect the original stream?
2. An API expects `OutputStream`, while you have a `FileChannel` opened with `WRITE`. Which adapter do you choose? Where will the next bytes be written?
3. Why doesn't `Channels.newChannel(InputStream)` automatically add `seek`, `truncate`, or `FileLock` capabilities?
4. If a capacity-4 buffer holds the first 4 UTF-8 bytes of a piece of text, how can printing `new String(chunk)` in isolation corrupt characters?
5. What risk does `while (buffer.hasRemaining()) channel.write(buffer)` carry when a nonblocking channel makes no progress? Which mechanism should you use to wait?
6. What happens if you close `Channels.newInputStream(fileChannel)` and then call `fileChannel.read(...)`?
7. Why can't a stream adapter over a nonblocking `SocketChannel` replace `Selector`?
8. For a 100 GiB input, why is `InputStream.readAllBytes()` an unsuitable design? Write how to process it in bounded chunks.
9. Does `Channels.newInputStream(AsynchronousByteChannel)` return an async API that callers await with `Future`? Which interfaces should be used if callbacks/Futures are desired?
10. Try reducing the buffer capacity in `StreamToChannelDemo` from 4 down to 1. Does the final text remain intact? Explain the condition that preserves bytes.

## 16. References

- [Java SE 17 API — `java.nio.channels.Channels`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Channels.html)
- [Java SE 17 API — `java.nio.channels` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html)
- [Java SE 17 API — `java.nio.ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)

## 17. Takeaways

**`Channels.newChannel(stream)`** adapts a byte stream into a same-direction byte channel; **`Channels.newInputStream(readableChannel)`** and **`newOutputStream(writableChannel)`** adapt byte channels into streams in their respective directions. Adapters transport bytes through the same underlying resource, add no buffering or encoding of their own, and closing an adapter closes the underlying source/destination.

When working with NIO, manage `ByteBuffer` phases properly with `flip()/clear()`, check `read/write` return counts, account for partial writes, and do not wrap nonblocking-configured channels with stream adapters. For text, use an explicit charset with `Reader/Writer`; for positional I/O or true readiness/async operations, stick to specialized channel APIs.
