# InputStream and OutputStream in Java: Reading and Writing Byte Streams

## 1. The Big Picture

In Java I/O, a **byte stream** is a way to read a sequence of bytes from a **source** or write bytes to a **destination** without requiring the program to know how the source or destination is implemented. The two core abstract classes in the `java.io` package are:

- **`InputStream`**: reads bytes from a source into the program.
- **`OutputStream`**: writes bytes from the program to a destination.

```text
Source (file / memory / connection ...)
              │
              ▼
         InputStream
              │ read bytes
              ▼
         Application
              │ write bytes
              ▼
         OutputStream
              │
              ▼
Destination (file / memory / connection ...)
```

These are **two abstract classes**, not two classes dedicated solely to files. The same byte-copying loop can work with `FileInputStream`, `ByteArrayInputStream`, or a stream provided by another API. Those objects have different data sources, but share the same `InputStream` contract. The same applies to output.

**When should you choose a byte stream?** When you need to preserve raw bytes: copying files, downloading binary data, image processing, compression, binary formats, or byte-transfer protocols. If the goal is to process **characters/text** according to an encoding, prefer `Reader`/`Writer` or text APIs with an explicit `Charset`; a byte stream does not by itself decode UTF-8, UTF-16, or any other encoding.

### Key Terms to Distinguish

| Term | Meaning |
| --- | --- |
| Source | The provider of bytes to an `InputStream` |
| Sink | The receiver of bytes from an `OutputStream` |
| EOF (end of stream) | The input stream has no more data; `read()` returns `-1` |
| Buffer | A temporary memory area used to read/write in batches, reducing the number of I/O calls |
| Wrapper/decorator | A stream that wraps another stream to add behavior such as buffering or reading typed data |

A stream can **block the execution thread (blocking)** when no data is available to read or when writing must wait for the device/destination. Each `read` or `write` call should not be treated as a "packet" or an application record.

## 2. InputStream: The Byte-Reading Contract

`InputStream` is an abstract class. Its fundamental `read()` method returns an `int` representing **an unsigned byte from 0 to 255**, or `-1` if the end of the stream has been reached. The return type is `int` because the byte `0xFF` is also valid data (value 255) and must be distinguishable from `-1`, which signals EOF.

```java
int value = in.read();
if (value == -1) {
    // End of stream reached.
} else {
    // A valid byte: 0..255.
}
```

In this snippet, `in` is an already opened `InputStream`; this is an **illustrative snippet**, not a standalone runnable program.

Common reading operations:

| Method | Primary Behavior |
| --- | --- |
| `int read()` | Reads at most one byte; returns `0..255` or `-1` |
| `int read(byte[] b)` | Reads into an array; returns the number of bytes read or `-1` |
| `int read(byte[] b, int off, int len)` | Reads into `b[off .. off+len)`; returns the number of bytes actually received or `-1` |
| `byte[] readNBytes(int len)` | Attempts to read up to `len` bytes; the returned array may be shorter if EOF is reached |
| `int readNBytes(byte[] b, int off, int len)` | Attempts to read `len` bytes, stopping on EOF or error; returns the number of bytes read |
| `byte[] readAllBytes()` | Reads all remaining bytes into RAM; should only be used when the size is controlled |
| `long transferTo(OutputStream out)` | Transfers the remaining bytes to the destination stream; returns the number of bytes transferred |
| `long skip(long n)` | Requests to skip up to `n` bytes; may skip fewer |
| `void skipNBytes(long n)` | Skips exactly `n` bytes or throws an exception if unable to do so |
| `int available()` | Estimates the number of bytes that can be read immediately without blocking; **not the total stream size** |
| `boolean markSupported()`, `mark(int)`, `reset()` | Supports marking/rewinding **if** the implementation allows it |
| `void close()` | Closes the stream and releases associated resources |

Most I/O operations can throw `IOException`. With `read(b, off, len)`, the number of bytes actually received is **not necessarily equal to `len`**; for instance, requesting 8192 bytes may yield only 300 bytes. Only the region `b[off .. off+bytesRead)` contains new data from that read. For `len == 0`, the result is `0`.

### The Correct Reading Loop

```java
byte[] buffer = new byte[8192];
int count;
while ((count = in.read(buffer)) != -1) {
    // Process only buffer[0] through buffer[count - 1].
}
```

This is a **code pattern in a context** where an `InputStream in` already exists. The condition relies on the result of `read`, not on `available()`, and does not require filling the entire array. For a buffer of positive length, a standard `InputStream` typically waits until it receives at least one byte, EOF, or an error.

## 3. OutputStream: The Byte-Writing Contract

`OutputStream` is also an abstract class. Common methods:

| Method | Primary Behavior |
| --- | --- |
| `void write(int b)` | Writes the **low 8 bits** of `b` as a single byte |
| `void write(byte[] b)` | Writes all bytes in the array |
| `void write(byte[] b, int off, int len)` | Writes `len` bytes starting at `off` |
| `void flush()` | Requests that data held in the stream's buffers be pushed out to the destination layer |
| `void close()` | Closes the stream; implementations may flush before releasing resources |

Unlike `InputStream.read(...)`, `OutputStream.write(...)` returns `void`; when the call completes normally, it is expected to have processed the requested number of bytes according to the stream's contract. If it fails to write, an `IOException` is normally thrown. There is no "partially written" return value for the caller to resume from a different offset.

For example, `out.write(0x1FF)` writes a single byte `0xFF` because only the low eight bits are taken. For example, `out.write(buffer, 0, count)` writes only the number of bytes actually read in the current iteration.

**`flush()` differs from `close()`:** `flush` is useful when you want data written through a `BufferedOutputStream` to be passed down to the underlying stream while continuing to use the stream. `close` ends the stream's lifecycle and releases resources. `flush` **does not guarantee that the data has been synchronized to persistent storage**; that still depends on the operating system and storage mechanism.

## 4. Example 1: Recognizing Byte 255 and Copying in Memory

The standalone program below uses `ByteArrayInputStream` as the source and `ByteArrayOutputStream` as the destination. It simultaneously demonstrates three points: `read()` returns `int`, EOF is `-1`, and byte streams preserve binary data.

**File `ByteBasics.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;
import java.util.StringJoiner;

public class ByteBasics {
    public static void main(String[] args) throws IOException {
        byte[] payload = {0, 65, (byte) 0xFF};
        StringJoiner numbers = new StringJoiner(", ");

        try (InputStream in = new ByteArrayInputStream(payload);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {

            int value;
            while ((value = in.read()) != -1) {
                numbers.add(Integer.toString(value));
                out.write(value);
            }

            System.out.println("read(): " + numbers);
            System.out.println(
                    "same bytes: " + Arrays.equals(payload, out.toByteArray()));
        }
    }
}
```

Run with Java 17 or later:

```bash
javac ByteBasics.java
java ByteBasics
```

**Exact stdout:**

```text
read(): 0, 65, 255
same bytes: true
```

Why does `(byte) 0xFF` print 255 when read? In a Java array, `byte` is signed, so `(byte) 0xFF` has the numeric value `-1`. However, `InputStream.read()` returns that byte's data as an unsigned `int` value of `255`. If you check `byte value == -1` to detect EOF, you can mistake valid `0xFF` data for the end of the stream. **Always keep the result of `read()` as an `int` until you have checked for `-1`.**

`ByteArrayOutputStream.toByteArray()` creates a copy of the bytes that were written. Because the data resides entirely in memory, this example does not need to touch the filesystem; `try-with-resources` still demonstrates a consistent stream-management habit.

## 5. Example 2: Copying a Binary File Using a Buffer

When working with files, you can open streams via `Files.newInputStream(Path)` and `Files.newOutputStream(Path)` from `java.nio.file`. Both return the abstract types `InputStream`/`OutputStream`, so the copying algorithm is independent of how the file is opened. An 8192-byte buffer helps avoid making outer-layer I/O calls one byte at a time.

**File `CopyBytes.java`:**

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyBytes {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Usage: java CopyBytes <source> <target>");
            return;
        }

        Path source = Path.of(args[0]).toAbsolutePath().normalize();
        Path target = Path.of(args[1]).toAbsolutePath().normalize();

        if (source.equals(target)
                || (Files.exists(target) && Files.isSameFile(source, target))) {
            throw new IllegalArgumentException(
                    "Source and target must be different files");
        }

        try (InputStream in =
                     new BufferedInputStream(Files.newInputStream(source));
             OutputStream out =
                     new BufferedOutputStream(Files.newOutputStream(target))) {

            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) != -1) {
                out.write(buffer, 0, count);
            }
        }

        System.out.println("Copied bytes: " + Files.size(target));
    }
}
```

Compile and run:

```bash
javac CopyBytes.java
java CopyBytes input.bin output.bin
```

The file `input.bin` must exist; `output.bin` will be created if it does not yet exist, or **overwritten** if it already exists. The stdout line is `Copied bytes: N`, where `N` equals the output size in bytes; `N` depends on the input file, so no fixed result is assigned. The names `input.bin`/`output.bin` can be replaced with actual file paths.

Step-by-step breakdown:

1. **Opening source and destination:** `Files.newInputStream(source)` reads from the file; `Files.newOutputStream(target)` by default creates the file if missing and overwrites (truncates) it if it exists.
2. **Wrapping with buffers:** `BufferedInputStream`/`BufferedOutputStream` add internal buffering. The `buffer` array in the program still serves a clear purpose: batching multiple bytes per processing iteration.
3. **Reading then writing:** `count` is the number of valid bytes from that read. `out.write(buffer, 0, count)` avoids writing stale bytes left over in the array.
4. **Automatic closing:** `try-with-resources` closes `out` and then `in` in the reverse order of declaration, even if an exception occurs. When `BufferedOutputStream` is closed, any remaining buffered data is flushed down to the underlying stream.
5. **Checking the result:** the program prints the output size. To verify that the bytes are identical, you can compare bytes or checksums; equal sizes **do not prove** equal contents.

Checking `Files.isSameFile` when the target exists prevents opening a destination that points to the source itself and losing data. With complex aliased paths, checking beforehand is not an atomic transaction: if the code needs to run in an environment where another party modifies paths concurrently, design appropriate additional safeguards. The example also **does not automatically create parent directories** for the destination.

### A Cleaner Solution with transferTo

For the task of transferring all remaining bytes from a source to a destination, `InputStream.transferTo(OutputStream)` (Java 9+) replaces the manual loop:

```java
// Snippet in a context where valid Path source and Path target already exist,
// and have been checked not to be the same file.
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    long transferred = in.transferTo(out);
    System.out.println("Transferred bytes: " + transferred);
}
```

In this snippet, `Files`, `Path`, `InputStream`, and `OutputStream` are types in `java.nio.file` and `java.io` that must be imported. `transferTo` reads until EOF and returns the number of bytes transferred; it does not guarantee using the operating system's zero-copy mechanism. If you need to process, limit, meter, or transform byte chunks individually, the `read(buffer)` loop remains clear and flexible.

## 6. Common Implementations and How They Relate

| Category | Input | Output | Purpose |
| --- | --- | --- | --- |
| Files | `FileInputStream` or `Files.newInputStream` | `FileOutputStream` or `Files.newOutputStream` | Reading/writing bytes of a file |
| Memory | `ByteArrayInputStream` | `ByteArrayOutputStream` | Testing, accumulating small/medium data |
| Buffered | `BufferedInputStream` | `BufferedOutputStream` | Reducing I/O calls on the underlying stream |
| Primitive values | `DataInputStream` | `DataOutputStream` | Reading/writing values such as `int`, `long`, `double` in a defined binary format |
| Other wrapper streams | `GZIPInputStream` (in `java.util.zip`) | `GZIPOutputStream` | Decompressing/compressing bytes passing through the stream |

One implementation can **wrap** another: `new BufferedInputStream(Files.newInputStream(path))`. The outer stream gains additional behavior while still adhering to the `InputStream` contract. For structured data types, `DataInputStream` and `DataOutputStream` must be used in the **same order and format** on both sides. If you write `writeInt(42)`, the reading side needs `readInt()`, rather than manually splitting bytes using a text encoding.

**Not every stream is seekable.** `InputStream` provides sequential reading. If you need random access to arbitrary positions in a file, consider `SeekableByteChannel` or `RandomAccessFile`. `mark/reset` is optional: always check `markSupported()`; `BufferedInputStream` supports it, whereas `FileInputStream` does not support marking/resetting in that way.

## 7. Resource Management and I/O Errors

Streams attached to files or connections typically hold operating system resources. Use **`try-with-resources`** when creating and owning a stream:

```java
try (InputStream in = Files.newInputStream(source)) {
    // Read data here.
} // close() is called automatically.
```

This snippet assumes `Path source` and the required imports are present. Do not call `close()` early while access is still needed; operating on a closed stream can throw `IOException` (depending on the implementation). An exception thrown in the processing block is still propagated; if `close()` also fails, Java attaches the closing error as a **suppressed exception** so it does not mask the primary error. You can inspect them via `Throwable.getSuppressed()` when debugging.

Distinguish **ownership**: code that opens a stream typically closes it; code that receives a stream from a caller should agree on a contract for who closes it. Avoid arbitrarily closing `System.in` or `System.out`, as these are shared resources of the running process.

`IOException` can occur when a file does not exist, permissions are insufficient, a device fails, or an external stream is interrupted. A copy operation that fails mid-way can leave behind a **partial destination file**; `try-with-resources` closes resources but does not guarantee rollback. If an application needs to replace a file safely, it can write to a temporary file on the same filesystem, verify it, and then replace/move it according to system capabilities and conditions; that is a separate concern outside the `InputStream`/`OutputStream` contract.

## 8. Reading Text via Byte Streams: Always Specify a Charset

Byte streams have no concept of characters. When converting between strings and bytes, **choose an explicit `Charset`**:

```java
// Illustrative snippet; requires importing java.nio.charset.StandardCharsets.
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);
```

Arbitrarily splitting a UTF-8 byte array and decoding each part can split a multi-byte character's encoded sequence in half and cause errors or replacement characters. If processing structured text, use `InputStreamReader`/`OutputStreamWriter` with an explicit charset, or `Files.newBufferedReader`/`Files.newBufferedWriter`. For raw bytes, keeping them as bytes through the end of the copy process avoids encoding issues altogether.

For example, **when copying a PNG image via `InputStream`/`OutputStream`, do not convert the image into a `String`**. Converting binary bytes through a `String` with an unsuitable charset can alter bytes and corrupt the file.

## 9. API Edge Cases Often Misunderstood

**`available()` does not measure the source size.** It is an estimate of the number of bytes that can be read immediately without blocking, and may return 0 even when more data will arrive later. Do not use `new byte[in.available()]` as a strategy to read the entire contents, especially with network streams.

**`skip(n)` is not guaranteed to skip the full `n` bytes.** It returns the number of bytes actually skipped. If you need to guarantee skipping exactly `n` bytes, modern Java provides `skipNBytes(n)`, which can throw `EOFException` if the stream ends early.

**`readAllBytes()` trades memory for convenience.** With very large or unbounded inputs, the data can exceed available RAM. Use a chunked loop when the size is unknown or when streaming is needed.

**A single `read(buffer)` call does not correspond to one message.** Byte streams do not preserve record boundaries. If a protocol has records, the application must define how boundaries are framed: fixed length, a length-prefix field, delimiters with escape rules, or another encoding scheme.

**`flush()` does not replace `close()`.** Flushing requests that buffered data be transferred, whereas closing releases resources. With nested wrapper streams, closing the outer stream usually closes the inner stream as well; there is no need to declare both the outer stream and the underlying stream as two separate resources to close them twice.

**`write(int)` does not write all four bytes of an `int`.** It only writes the low 8 bits. If you want to represent an `int` as 4 bytes in a defined format, use `DataOutputStream.writeInt` or specify the encoding yourself; the reader must use the same format.

**Java's `byte` is signed, whereas bytes on a stream are unsigned.** When you need to convert a `byte b` to an integer in `0..255`, use `b & 0xFF`. Conversely, `InputStream.read()` already returns an `int` in `0..255`, so that operation is unnecessary.

## 10. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| `byte b = (byte) in.read(); if (b == -1) ...` | The data value `0xFF` is mistaken for EOF | Use `int value = in.read()`, check `value == -1` |
| `out.write(buffer)` right after `read(buffer)` | The final iteration may read fewer bytes than the buffer size, writing stale bytes | `out.write(buffer, 0, count)` |
| Assuming `read(buffer)` always fills the array | `read` may return a positive count smaller than requested | Rely on the returned byte count; accumulate if a full-length block is required |
| Looping `while (in.available() > 0)` to read until the end | `available` is neither an EOF nor a total-size signal | Loop until `read` returns `-1` |
| Using `readAllBytes()` for unbounded files | Risks running out of memory | Read/write in chunks |
| Forgetting to close a file stream | Can leak file descriptors or miss flushing | `try-with-resources` |
| Decoding binary bytes into a String and then writing them back | The charset can alter the data | Keep bytes unchanged; decode only when the data is actually text |
| Opening the output on the same file as the source | Output truncates by default, losing the source data | Check both paths and design a safe replacement workflow |
| Treating `flush()` as confirmation of durable disk write | Flush does not carry an `fsync` guarantee | Use a dedicated storage synchronization mechanism when durability is required |
| Comparing only `Files.size` to verify a copy | Files with different contents can still have the same size | Compare bytes, use an appropriate hash, or use `Files.mismatch` when verification is needed |

## 11. Choosing the Right API in Practice

- **Copying unbounded byte streams:** `read(buffer)` + `write(buffer, 0, count)`, or `transferTo` if you only need an exact copy.
- **Small files with a known bound:** `Files.readAllBytes`/ `InputStream.readAllBytes` can be convenient, though they use RAM proportional to the content size.
- **Reading/writing text:** `Reader`/`Writer` or the `Files` API with `StandardCharsets.UTF_8` when appropriate.
- **Reading/writing integers/primitive values in a binary format:** `DataInputStream` and `DataOutputStream`, keeping the read/write order in sync.
- **Sequential I/O with many small operations:** add `BufferedInputStream`/`BufferedOutputStream` when adequate buffering is not already present at a lower layer.
- **Random access to file positions:** choose random-access/channel APIs instead of trying to use a sequential byte stream.

It is generally good practice to declare variables using the **abstract types** `InputStream`/`OutputStream` and instantiate a concrete implementation at the application boundary. This makes it easy to swap files for in-memory data in tests without changing the processing logic.

## 12. Hands-On Practice and Review Questions

1. Run `ByteBasics`, replacing `payload` with `{(byte) 0x80, (byte) 0xFF, 0}`. Predict which numbers `read()` will return (answer: `128, 255, 0`).
2. Use `CopyBytes` with a small binary file and a large one. Verify the contents using `Files.mismatch(Path, Path)` (Java 12+): a result of `-1` means no differing byte was found; a non-negative value is the position of the first differing byte.
3. Explain why `out.write(buffer, 0, count)` is needed in the copy loop and what happens if the final read returns only 7 bytes in an 8192-byte buffer.
4. Write a version using `transferTo`, then modify it into a version that copies at most the first 1024 bytes. For a bounded task like that, you need to control the number of bytes requested to be read in each iteration yourself.
5. Answer for yourself: Is `read()` returning `-1` the same as the byte `0xFF`? Does `flush()` mean closing the stream? Does `available()` indicate how many bytes remain in the file?

**Remember:** `InputStream` supplies bytes and an EOF signal; `OutputStream` receives bytes; loops must use **the exact number of bytes just read**; resources must have a clear lifecycle. Mastering these four points will help you apply the same mindset to files, memory, and many other types of byte sources and destinations in Java.
