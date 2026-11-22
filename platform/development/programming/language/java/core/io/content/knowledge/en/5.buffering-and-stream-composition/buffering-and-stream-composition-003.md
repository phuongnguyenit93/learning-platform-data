# Decorator: Wrapper Classes That Add Behavior to Streams in Java I/O

An `InputStream` can read bytes from a file, but what if you want **buffered reading**, **reading primitive data types**, or **counting bytes read**? Java I/O solves many such needs by **wrapping one stream inside another**. The outer class keeps the same basic read/write interface, while adding behavior before or after delegating work down to the inner stream. This is a practical application of the **Decorator pattern**.

Stream composition example:

~~~text
PROGRAM
      |
      v
DataInputStream       <-- adds readInt(), readLong(), readFully()...
      |
      v
BufferedInputStream   <-- adds buffering for byte reads
      |
      v
FileInputStream       <-- actually reads bytes from the file
      |
      v
SOURCE FILE
~~~

On the write side, the same idea operates from the outer layer to the inner layer: `DataOutputStream` writes values in binary representation, `BufferedOutputStream` batches the bytes, and `FileOutputStream` sends the bytes down to the target file.

After this lesson, you should be able to explain **the role of each layer**, **composition order**, **how calls are forwarded**, **who closes the resource**, and **why wrapping a stream will not transform data the way you expect if ordered incorrectly**.

## 1. What Is the Decorator Pattern in the Context of Streams?

Decorator is a structural design pattern: you create an object that **wraps** another object sharing the same interface, letting the wrapper supply additional behavior without modifying the source class directly. In Java I/O:

- **Component:** the shared type, such as `InputStream` (byte reading) or `OutputStream` (byte writing).
- **Concrete component:** the base stream supplying or accepting data, such as `FileInputStream`, `ByteArrayInputStream`, or `FileOutputStream`.
- **Decorator:** the wrapping stream, such as `BufferedInputStream`, `DataInputStream`, `BufferedOutputStream`, or `DataOutputStream`.
- **Client:** code that calls only the outermost object without orchestrating each layer manually.

Visualization:

~~~text
Client -> Decorator C -> Decorator B -> Decorator A -> Base Stream
          [same InputStream or OutputStream contract]
~~~

A decorator **holds a reference to another stream** and typically delegates the underlying operations to it, potentially altering, buffering, converting, or measuring the data. Architecturally, this changes behavior through **composition (wrapping objects)** instead of generating subclasses for every possible combination of features.

Example of building a read chain:

~~~java
InputStream input = new DataInputStream(
        new BufferedInputStream(
                new FileInputStream("payload.bin")));
~~~

All participating classes are compatible with `InputStream`, so `input` can be passed to methods expecting an `InputStream`. However, specialized methods like `readInt()` are only visible if the variable is typed as `DataInputStream` or you hold a reference to that decorator:

~~~java
try (DataInputStream input = new DataInputStream(
        new BufferedInputStream(new FileInputStream("payload.bin")))) {
    int version = input.readInt();
}
~~~

This is an **illustrative snippet** (it will not run standalone without `payload.bin` and imports). The file must actually contain at least four bytes in the format `readInt` expects; `DataInputStream` does not auto-detect file formats.

## 2. Common Byte-Stream Decorator Classes

| Class | What Does It Wrap? | Added Behavior |
|---|---|---|
| `FilterInputStream` | `InputStream` | Base class for input filters/wrappers; by default forwards most operations to the inner stream. |
| `BufferedInputStream` | `InputStream` | Maintains an internal byte buffer to reduce reads from the underlying source; supports `mark`/`reset` per its contract. |
| `DataInputStream` | `InputStream` | Reads typed binary values via `readInt()`, `readLong()`, `readDouble()`, `readFully()`, etc. |
| `PushbackInputStream` | `InputStream` | Allows pushing back one or more bytes via `unread()` so subsequent reads receive them again. |
| `FilterOutputStream` | `OutputStream` | Base class for output filters/wrappers. |
| `BufferedOutputStream` | `OutputStream` | Batches bytes in a buffer before passing them down to the underlying output. |
| `DataOutputStream` | `OutputStream` | Writes typed values like `writeInt()`, `writeLong()`, `writeDouble()` in Java's binary format. |

In addition, compression classes like `GZIPInputStream` and `GZIPOutputStream` in Java's I/O/ZIP packages provide **decompression/compression** behavior when wrapping a stream. They help illustrate that a decorator is not limited to buffering: it can perform data transformations as well.

Viewed by common inheritance hierarchy:

~~~text
InputStream
  +-- FilterInputStream
        +-- BufferedInputStream
        +-- DataInputStream
        +-- PushbackInputStream

OutputStream
  +-- FilterOutputStream
        +-- BufferedOutputStream
        +-- DataOutputStream
~~~

Not **every** wrapper stream must extend `FilterInputStream`/`FilterOutputStream`. What defines the decorator pattern here is **the structure of wrapping an object and adding behavior through a shared contract**, not merely the class name or inheritance tree.

## 3. Wrapper Mechanics: How Calls Flow Through the Layers

Suppose the source is a file containing bytes and the program calls:

~~~java
int value = input.read();
~~~

If `input` is a `BufferedInputStream` wrapping a `FileInputStream`, the call enters the buffer layer first. While the buffer still holds bytes, it can return a buffered byte immediately. When it needs to refill, it reads a block of bytes from `FileInputStream` and returns one byte to the caller. This **reduces calls down to the underlying I/O layer**, without necessarily changing the bytes output.

With `DataInputStream` as the outermost layer:

~~~java
int version = dataInput.readInt();
~~~

`readInt()` obtains **four bytes** from the underlying input layer and assembles them into an `int` according to `DataInput`'s defined format (big-endian for multi-byte integers). The inner `BufferedInputStream` may pre-fetch extra bytes into its buffer, but the logical value `readInt` returns still comes from the exact four bytes of this field.

**Do not confuse bytes read from the physical source with bytes consumed by the client.** Because of prefetching, `BufferedInputStream` may read many bytes from the underlying file even when the caller has only requested one byte or one value. If you place a byte-counting decorator **below** the buffer, the count may be higher than what the client has consumed at the time of measurement. If you place the counter **above** the buffer, the count reflects bytes that have passed through the counting layer. Wrapping order therefore affects observability as well.

### Wrapping Order Is Part of the Design

Consider two ways to place a counting layer:

~~~text
A) Client -> CountingInputStream -> BufferedInputStream -> FileInputStream
    counts bytes pulled by the client through the Counting layer

B) Client -> BufferedInputStream -> CountingInputStream -> FileInputStream
    counts bytes Buffered pulled from the base stream, including prefetched bytes
~~~

If every layer merely forwards calls, the difference is hard to notice; if a layer **buffers, compresses, encrypts, decodes, or counts**, the order can alter the output or metrics. Design the pipeline starting from the **actual byte format on the source/destination**, then place processing layers accordingly.

## 4. Runnable Java 17 Example: Composing Multiple Decorators

This example intentionally avoids external files. We define a small binary format:

~~~text
4 bytes: version (int)
4 bytes: content byte length
N bytes: UTF-8 encoded text
~~~

**Write pipeline**: `DataOutputStream -> BufferedOutputStream -> ByteArrayOutputStream`.  
**Read pipeline**: `DataInputStream -> BufferedInputStream -> CountingInputStream -> ByteArrayInputStream`.

`CountingInputStream` is a custom decorator extending `FilterInputStream` to count bytes passing through it. Source file **`StreamDecoratorDemo.java`**:

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class StreamDecoratorDemo {
    static final class CountingInputStream extends FilterInputStream {
        private long count;

        CountingInputStream(InputStream wrapped) {
            super(wrapped);
        }

        @Override
        public int read() throws IOException {
            int value = super.read();
            if (value != -1) count++;
            return value;
        }

        @Override
        public int read(byte[] bytes, int offset, int length) throws IOException {
            int number = super.read(bytes, offset, length);
            if (number > 0) count += number;
            return number;
        }

        long getCount() {
            return count;
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] message = "Xin chào".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream storage = new ByteArrayOutputStream();

        try (DataOutputStream output = new DataOutputStream(
                new BufferedOutputStream(storage))) {
            output.writeInt(3);
            output.writeInt(message.length);
            output.write(message);
        }

        byte[] wire = storage.toByteArray();
        CountingInputStream counted = new CountingInputStream(
                new ByteArrayInputStream(wire));
        try (DataInputStream input = new DataInputStream(
                new BufferedInputStream(counted))) {
            int version = input.readInt();
            int length = input.readInt();
            byte[] body = new byte[length];
            input.readFully(body);

            System.out.println("Version: " + version);
            System.out.println("Text: " + new String(body, StandardCharsets.UTF_8));
            System.out.println("Body length: " + length);
        }

        System.out.println("Encoded bytes: " + wire.length);
        System.out.println("Read from source: " + counted.getCount());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 StreamDecoratorDemo.java
java StreamDecoratorDemo
~~~

Expected output when the terminal supports UTF-8:

~~~text
Version: 3
Text: Xin chào
Body length: 9
Encoded bytes: 17
Read from source: 17
~~~

If your environment's console uses an encoding other than UTF-8, accented characters may render incorrectly even though byte conversion and read values are accurate. The rest of the output still verifies the byte counts and wrapping process.

**Layer-by-layer breakdown:**

1. `ByteArrayOutputStream storage` is the **final byte sink** in memory. `BufferedOutputStream` acts as the buffer, while `DataOutputStream` provides `writeInt` to encode the two integers in exact binary format.
2. `message` is **9 UTF-8 bytes**: `Xin` is three bytes, the space is one byte, and `chào` is five bytes because `à` requires two bytes. `writeInt(3)` writes four bytes; `writeInt(9)` writes four bytes; `write(message)` writes nine bytes, totaling **4 + 4 + 9 = 17 bytes**.
3. Closing `DataOutputStream` at the end of `try-with-resources` flushes any remaining bytes in `BufferedOutputStream` down to the lower layer. Then `storage.toByteArray()` retrieves the accumulated bytes; closing `ByteArrayOutputStream` does not discard its in-memory contents.
4. `ByteArrayInputStream` provides the 17 bytes to read back. `CountingInputStream` records bytes actually delivered by the source; `BufferedInputStream` wraps it for buffering; `DataInputStream` on the outside decodes the two `int` fields.
5. `readFully(body)` reads all `length` bytes or throws `EOFException` if there are not enough. It fits fixed-length formats—unlike a single `read(body)` call, which may return fewer bytes than requested.
6. In this particular case, all 17 bytes are consumed, so the counted total is 17. If a file had trailing data, the buffer might prefetch more than `DataInputStream` used.
7. `try-with-resources` closes the **outermost layer**. The standard wrapper classes in this chain propagate closing down to the inner stream per their contracts.

This example illustrates **stream composition mechanics and a custom binary format**; it is not a standard file format. When receiving data from untrusted sources, validate `length` (negative, oversized, exceeding allowed bounds) **before allocating `new byte[length]`**. Never allocate arbitrary arrays solely because an integer in the input declares that size.

### Why Does the Custom Decorator Override Two `read` Overloads?

A counting decorator must decide **which bytes to measure** and cover the read methods used by client code. `read()` returns one byte or `-1` at end of stream; `read(byte[], offset, length)` returns the count of bytes read. The class above increments the counter only when actual data is read. It inherits `read(byte[])` handling such that calls delegate through the three-argument overload.

Do not equate the number of **method calls** with the number of bytes read. A single `read(byte[], off, len)` call can receive anywhere from 1 to `len` bytes (or special values per its contract). Any custom decorator must also consider methods such as `skip()`, `mark()`, and `reset()` if the counter needs to reflect another definition—such as "total bytes pulled from source," "bytes delivered to client," or "current position." The simple counter here **does not count `skip` and does not rewind its count on `reset`**; because the program does not call those methods, the example output is unaffected.

## 5. Closing Wrapped Streams and Resource Ownership

With standard Java I/O decorators, when closing the **outermost decorator**, `close()` is forwarded to the inner stream, continuing down to the base stream:

~~~text
try (DataOutputStream out =
         new DataOutputStream(
             new BufferedOutputStream(
                 Files.newOutputStream(path)))) {
    // Write data
}

Exiting try:
DataOutputStream.close()
     -> BufferedOutputStream.close()
           -> OutputStream from Files.newOutputStream(...).close()
~~~

Therefore, if the method itself creates and owns the decorator chain, you typically only need to declare the **outermost object** in `try-with-resources`. You do not need to list every layer as separate resources and close them repeatedly. Still, verify the `close` contract of any specific wrapper; a library might design a wrapper that does not close the underlying stream.

**Distinguish ownership clearly:**

- **Outermost layer owns the chain:** the method creates the base stream and decorators and is responsible for closing them; `try-with-resources` on the outermost layer is convenient.
- **Wrapper borrows a caller's stream:** if code puts the wrapper in `try-with-resources`, closing the wrapper can **also close the caller's stream**. Only do this when the contract transfers ownership or the caller will no longer use the stream.
- **Shared streams (`System.in`/`System.out`) or framework-managed streams:** do not close them recklessly just for the convenience of `try-with-resources`. Define clearly who terminates the stream.
- **Buffered output streams:** data may not have reached the destination yet if not flushed or closed in time. `flush` requests pushing buffered data down to the lower layer, but does not by itself guarantee disk durability or processing by the receiving application.

Example of a helper that accepts an output from the caller and only borrows it:

~~~java
static void writeRecord(DataOutputStream output, int value)
        throws IOException {
    output.writeInt(value);
    // Do not close: caller may still write more records.
}
~~~

This is an **illustrative method** placed inside a Java class that imports `DataOutputStream` and `IOException`. For buffered streams, the caller decides when to flush/close based on lifecycle and protocol.

## 6. Wrappers Must Match the Data Type

### Byte Streams with Byte Streams

`BufferedInputStream`, `DataInputStream`, and `PushbackInputStream` wrap an `InputStream` and stay on the **byte** side; `BufferedOutputStream` and `DataOutputStream` wrap an `OutputStream` and stay on the **byte** side.

### The Byte-to-Character Bridge Is an Adapter

`InputStreamReader` takes an `InputStream` and decodes bytes into **characters**; `OutputStreamWriter` takes an `OutputStream` and encodes characters into bytes. Architecturally, they are **adapters between byte streams and character streams**, not same-type `InputStream` ↔ `InputStream` decorators.

~~~java
Reader reader = new BufferedReader(
        new InputStreamReader(input, StandardCharsets.UTF_8));
~~~

This illustrative snippet requires the corresponding imports. `input` is an existing `InputStream`; `InputStreamReader` converts bytes to UTF-8 characters, and `BufferedReader` buffers characters / adds `readLine()`. `BufferedReader` is not `BufferedInputStream`: one buffers **characters**, the other buffers **bytes**. When binary fidelity must be preserved strictly, avoid passing data through character decoders/encoders.

### Typed Data Must Be Read the Same Way It Was Written

`DataOutputStream.writeInt(123)` writes **4 binary bytes**; the matching read call is `DataInputStream.readInt()`. Do not open a file written with `writeInt` as a UTF-8 text file expecting to see the digits `"123"`.

One common pitfall: `DataOutputStream.writeUTF(String)` uses **modified UTF-8** with a length prefix, which does **not produce the exact same bytes as `string.getBytes(StandardCharsets.UTF_8)` in all cases**. To encode a **standard UTF-8** string with an explicit length, you can use `writeInt(bytes.length)` followed by `write(bytes)` as in the example, and read it back with `readInt()` + `readFully()`. Both sides must agree on the format and field order.

## 7. Compression Layers Also Show Why Composition Order Matters

When storing binary data encoded by `DataOutputStream` and compressing it with GZIP, a sensible order is:

~~~java
// Illustration; path is an already declared Path.
try (DataOutputStream out = new DataOutputStream(
        new GZIPOutputStream(
                new BufferedOutputStream(
                        Files.newOutputStream(path))))) {
    out.writeInt(123);
}
~~~

Data flows in order: `DataOutputStream` produces the integer's binary bytes → `GZIPOutputStream` **compresses** the bytes → `BufferedOutputStream` buffers compressed bytes before writing them to the file. To read it back, build the stream in the symmetric order:

~~~java
try (DataInputStream in = new DataInputStream(
        new GZIPInputStream(
                new BufferedInputStream(
                        Files.newInputStream(path))))) {
    int value = in.readInt();
}
~~~

These are **illustrative snippets** requiring imports from `java.io.*`, `java.nio.file.*`, `java.util.zip.GZIPInputStream`, and `java.util.zip.GZIPOutputStream`; `path` is supplied by the application. They do not form a standalone `main` program.

If you place the decompression layer on the wrong side—for example trying to call `readInt()` directly on uncompressed GZIP bytes—you will not recover the `123` that was written. If you alter the order of filters that **transform data**, you must update the reader pipeline to match. Simply stacking wrappers without understanding the protocol is not enough.

## 8. Decorators vs. Alternatives

Decorators fit well when you need to **reuse the same source/destination and add behavior layer by layer**. However, not every I/O task requires building a wrapper chain manually:

- `Files.readString(path, UTF_8)` or `Files.writeString(path, text, UTF_8)` is concise when handling a small text file with a known charset.
- `Files.copy(source, destination)` fits when you just need to copy a file by path without touching the data in between.
- `InputStream.transferTo(output)` copies remaining bytes from input to output; it works even when input/output already have multiple wrapper layers.
- `BufferedReader` is useful when reading text line by line; it is a character layer, so pair it with the proper decoding charset.
- For high-throughput workloads or complex random access, `java.nio.channels` offers specialized channel/buffer options; do not assume decorators solve every need.

The trade-off of stacking many layers is **more configuration, more internal state, and resource-closing responsibility**. Use only the layers required and check built-in APIs, rather than reflexively adding `BufferedInputStream` without measuring or when an API already reads in suitable blocks.

## 9. Common Mistakes

| Misconception | Consequence | Right Approach |
|---|---|---|
| "Adding `BufferedInputStream` changes file content." | Buffering only changes the byte-fetching strategy, not the underlying format. | Keep **buffering** separate from **transformation**. |
| "`DataInputStream` understands text/JSON files automatically." | This API reads the binary format of `DataInput` methods; it does not guess structure. | You must know the binary schema and field order written. |
| "Decorator order doesn't matter." | Compression, encryption, buffering, and counting layers can change metrics or output. | Design the path from producer to consumer and mirror the order. |
| "Closing the outer wrapper won't affect the original stream." | Many wrappers forward `close` downward, unintentionally closing someone else's stream. | Design ownership clearly; use `try-with-resources` on the owning side. |
| "`flush` and `close` are the same." | `flush` pushes buffered bytes, while `close` terminates the resource; they are not interchangeable. | Flush/close according to contract when records or streams finish. |
| "One `read(byte[])` call always fills the array." | A single read may return fewer bytes than requested. | Use a loop or `DataInputStream.readFully` when length is known. |
| "`CountingInputStream` in the example always counts bytes processed by the client." | Placed below a buffer, the counter also sees prefetched bytes. | Place measurement at the layer matching the metric you want. |
| "Reading text via byte streams needs no charset." | Whenever bytes become characters, a charset still governs the content. | Use `InputStreamReader` with an explicit charset when text is needed. |
| "`new byte[length]` is safe for any file." | Lengths in untrusted input can be wrong, negative, or huge. | Validate length bounds before allocating; handle EOF and format errors. |

## 10. Self-Check Exercises

**Exercise 1.** A program reads UTF-8 lines from a file. Describe the appropriate layers.

> **Answer:** `FileInputStream` (source bytes) → `InputStreamReader(..., UTF_8)` (decode bytes to characters) → `BufferedReader` (buffer characters and provide `readLine()`). Or use `Files.newBufferedReader(path, UTF_8)` to construct the proper reader directly.

**Exercise 2.** Why can you hold the outermost variable as an `InputStream` yet be unable to call `readInt()` directly?

> **Answer:** `InputStream` is the general byte-reading contract; `readInt()` is an additional method on `DataInputStream`. To call it directly, you need a reference typed as `DataInputStream` (or a compatible interface), regardless of the wrapped runtime object.

**Exercise 3.** When code opens a `FileInputStream` itself and wraps it in a `BufferedInputStream`, where should it be closed?

> **Answer:** Use `try-with-resources` on the outermost wrapper owned by that method. By the contract of these standard classes, closing the wrapper closes the base stream. Do not do that automatically if the base stream is owned by a caller or framework.

**Exercise 4.** A counter is placed below `BufferedInputStream`. The caller calls `read()` once, yet the counter jumps by many bytes. Is that necessarily a bug?

> **Answer:** No. `BufferedInputStream` can prefetch a block of bytes. A counter underneath measures bytes **pulled from the source**, not necessarily bytes consumed by the caller.

**Exercise 5.** `writeInt(123)` is written through `GZIPOutputStream`. Is calling `readInt()` directly on the GZIP file valid?

> **Answer:** No. You must place `GZIPInputStream` on the source side to **decompress** the bytes first, and then `DataInputStream` can interpret them with `readInt()`.

## Takeaways

Decorator streams are a way to **add behavior through wrapper layers sharing the same I/O interface**. When composing them, ask yourself: **what is the real source/destination; which layer handles buffering, formatting, or byte transformation; does the layer order match the protocol; and who owns and closes the chain?** Answering these questions helps you build Java I/O pipelines that are both extensible and safe with respect to data fidelity and resource lifecycles.

**References:** [Java SE 17 — `FilterInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilterInputStream.html), [`BufferedInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html), [`DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html), [`DataOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html).