# Choosing Between InputStream, Reader, Files, or Channel in Java

When working with I/O, do not start by asking "Which API is the fastest?". Identify **whether the data is bytes or text, what the source/destination is, whether random access is needed, and how large the data can grow**. The four names in the title solve different needs; in many cases they are combined together.

> Scope: Java 17+, primarily synchronous I/O. Examples use `java.nio.file.Files`, `java.io.InputStream`/`Reader`, and `java.nio.channels.Channel`.

## 1. Quick Selection Table by Scenario

| Practical need | Preferred choice | Why | Pitfall to avoid |
| --- | --- | --- | --- |
| Read an entire **small text file**, known charset | `Files.readString(path, UTF_8)` | Opens, reads, and closes the resource in one call | Files that are too large will consume a lot of memory |
| Write a text string to a file | `Files.writeString(path, text, UTF_8)` | Simple, controls charset, supports write options | By default it may create a new file or overwrite existing content |
| Iterate line by line over a text file | `Files.newBufferedReader` + `BufferedReader.readLine`, or `Files.lines` | Processes incrementally without loading the whole file | Must close the reader/stream; `readLine` strips line terminators |
| Read/write **raw bytes** from a file, socket, HTTP body, or any source | `InputStream` / `OutputStream` | Continuous byte API, standard for binary data | Do not wrap images/ZIP/PDF in a `Reader` |
| Copy an existing file to another file | `Files.copy(source, target, options)` | Concise, handles paths and files | Do not write a manual copy loop if you only need to copy a file |
| Read a small binary file into a byte array | `Files.readAllBytes(path)` | Convenient when the data is small enough | Large arrays can exhaust memory |
| Need to read/write at a **specific byte position** in a file | `SeekableByteChannel` or `FileChannel` | Has `position(long)`; uses `ByteBuffer` | `InputStream` is generally a forward-reading stream and does not support general seeking |
| Need file locking, memory mapping, or specialized file operations | `FileChannel` | Has `lock`, `map`, `transferTo`, `transferFrom` | Many features depend on the OS/file system |
| Non-blocking network I/O using a selector | `SocketChannel` + `Selector` | Can work with non-blocking `java.nio` | Do not use channels just because of the name "NIO"; the API is more complex |
| Data comes from an `InputStream` but needs **character reading** | `InputStreamReader(in, charset)`, usually wrapped in `BufferedReader` | Decodes bytes to characters with the right charset | Do not assume the machine's default charset |
| Only need to check, create, list, rename, or delete paths/files | `Path` + `Files` methods | These are file system operations, no need to manually open streams | `Path` represents a path; it does not contain the file's data |
| Very large or unknown-size source | Stream/Reader/Channel reading in chunks | Keeps memory usage nearly constant | Avoid unbounded `readAllBytes`, `readString`, `readAllLines` |

**Short rule:** If the problem describes **operations on files and paths**, start with `Path`/`Files`. If the problem describes a **byte stream**, choose `InputStream`. If it describes **characters/text**, choose `Reader` with a charset. If you need **positions, buffers, file channels, or non-blocking I/O**, look at `Channel`.

## 2. Understanding the Four API Groups Accurately

### `InputStream`: sequential byte reading

`java.io.InputStream` provides `read()`, `read(byte[])`, `read(byte[], off, len)`, `readAllBytes()`, and `transferTo(OutputStream)`. The read results are **bytes**, not characters. `read(...)` returns the actual number of bytes read, or `-1` at end of data; you must not assume a single read will fill the buffer.

Common classes are `FileInputStream` (files), `ByteArrayInputStream` (memory), `BufferedInputStream` (buffering), and streams returned by HTTP/ZIP/socket libraries. `InputStream` suits images, audio, ZIP, PDF, protocol formats, and even text **when the goal is only to transport bytes unchanged**. To create a stream from a `Path`, use `Files.newInputStream(path)`.

`OutputStream` is the byte-writing side. `BufferedInputStream`/`BufferedOutputStream` reduce the number of accesses to the source/destination; they do not decode text themselves.

### `Reader`: reading characters after decoding bytes

`java.io.Reader` provides `read()` and `read(char[])`. `InputStreamReader` is the **byte → character** bridge using a specified charset. `BufferedReader` adds `readLine()` and `lines()`; `Files.newBufferedReader(path, charset)` opens a reader for a file.

When working with logs, CSV, JSON, configuration, or source code as text, decide the **charset** first (usually `StandardCharsets.UTF_8`). A single Unicode character can take multiple UTF-8 bytes, so **the number of bytes does not equal the number of characters**. In Java, `char` is a UTF-16 code unit; a Unicode character outside the BMP may consist of two `char`s. Do not split bytes arbitrarily and convert each piece independently into a `String`, because that can cut across a multi-byte UTF-8 sequence.

`Reader` only handles characters; it does not parse JSON/CSV according to format rules. When parsing is needed, use an appropriate parser after the reading layer.

### `Files` and `Path`: utility-level file operations

`Path` (`java.nio.file.Path`) represents a path; `Files` (`java.nio.file.Files`) has many static methods: `readString`, `readAllBytes`, `writeString`, `write`, `copy`, `move`, `delete`, `createDirectories`, `newInputStream`, `newBufferedReader`, `newByteChannel`, and `lines`. As a result, `Files` can serve as a high-level API **or** the entry point to open a low-level stream/channel.

Note that "read all" methods hold data in memory, whereas `newBufferedReader`, `newInputStream`, and `lines` are suited for incremental reading. With `Files.lines`, the `Stream<String>` object is linked to the open file and must be closed via `try-with-resources`.

### `Channel`: buffer-based I/O with specialized capabilities

`java.nio.channels.Channel` is a broad family of interfaces. `ReadableByteChannel`/`WritableByteChannel` read/write with `ByteBuffer`; `SeekableByteChannel` supports `position` and `size`; `FileChannel` supports advanced file operations; `SocketChannel` can use non-blocking mode.

With `ByteBuffer`:
1. `put` or channel `read` advances the **position**.
2. Call `flip()` to switch from writing into the buffer to reading the received data.
3. Read/write data out; if continuing to receive more data, use `clear()` or `compact()` depending on whether unconsumed bytes remain.

`Channel` does not mean "automatically faster". For ordinary file tasks, `Files` or buffered streams are usually simpler and sufficient. A single `channel.read(buffer)` call can also return only partial data; the loop still has to handle the returned byte count and EOF.

## 3. Decision Tree When Facing a New I/O Requirement

```text
Does the requirement involve files/paths?
  ├─ Yes: only create/copy/move/delete/check → Path + Files
  └─ Yes: need to read/write content
       ├─ Text, small content → Files.readString / writeString + charset
       ├─ Text, incremental reading → BufferedReader / Files.lines
       ├─ Small bytes → Files.readAllBytes / write
       ├─ Large bytes/continuous stream → Files.newInputStream / newOutputStream
       └─ Positional access, map/lock/specialized buffer → SeekableByteChannel / FileChannel

Is the source not a file (HTTP response, socket, compressed data, memory...)?
  ├─ Only need bytes → InputStream (or channel if provided by the system)
  ├─ Need text → InputStreamReader(stream, charset) → BufferedReader
  └─ Need non-blocking/multiplexing via selector → SocketChannel + Selector
```

The tree above is a starting point, not an exclusive rule. For instance, `Files.newInputStream(path)` **returns** an `InputStream`; `Files.newByteChannel(path)` **returns** a `SeekableByteChannel`. `Files` is where you open the resource, while stream/reader/channel is how you **consume** the data.

## 4. Standalone Java 17 Example: Choosing Correctly on the Same Set of Files

The following program creates a temporary directory itself, writes a UTF-8 text file and a binary file, and reads each type as required. Commands and output are consistent across platforms supporting Java 17.

Create the file `IoChoiceDemo.java`:

```java
import java.io.BufferedReader;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class IoChoiceDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("io-choice-");
        Path textFile = dir.resolve("notes.txt");
        Path binaryFile = dir.resolve("payload.bin");

        try {
            Files.writeString(textFile, "Xin chào\nJava IO\n",
                    StandardCharsets.UTF_8);
            Files.write(binaryFile, new byte[] {65, 66, 67});

            // Files: read the entire small file into a String.
            String text = Files.readString(textFile, StandardCharsets.UTF_8);
            System.out.println("Files: " + text.split("\\R")[1]);

            // Reader: read text line by line with a known charset.
            try (BufferedReader reader = Files.newBufferedReader(
                    textFile, StandardCharsets.UTF_8)) {
                System.out.println("Reader: " + reader.readLine());
            }

            // InputStream: read the first byte of binary data.
            try (InputStream in = Files.newInputStream(binaryFile)) {
                System.out.println("InputStream: " + (char) in.read());
            }

            // Channel: seek to offset 1 and read the byte at that position.
            try (SeekableByteChannel channel = Files.newByteChannel(
                    binaryFile, StandardOpenOption.READ)) {
                channel.position(1);
                ByteBuffer buffer = ByteBuffer.allocate(1);
                int count = channel.read(buffer);
                if (count != 1) {
                    throw new IllegalStateException("Cannot read byte at offset 1");
                }
                buffer.flip();
                System.out.println("Channel: " + (char) buffer.get());
            }
        } finally {
            Files.deleteIfExists(binaryFile);
            Files.deleteIfExists(textFile);
            Files.deleteIfExists(dir);
        }
    }
}
```

Compile and run from the directory containing the source file:

```bash
javac -encoding UTF-8 IoChoiceDemo.java
java IoChoiceDemo
```

Expected output:

```text
Files: Java IO
Reader: Xin chào
InputStream: A
Channel: B
```

**Explanation:** `Files.readString` returns a `String` because the text file is small; `BufferedReader` reads the first line without holding the whole file; `InputStream.read()` returns byte 65 (ASCII `A`); the channel sets its position to the second byte, receives byte 66 (`B`) into `ByteBuffer`, and calls `flip()` before reading it out. `try-with-resources` closes every reader/stream/channel; `finally` cleans up the temporary files created.

The example uses `throws Exception` to keep the focus on API selection. In real applications, handle `IOException` with context, including the path name and the action being performed.

## 5. Three Common Patterns When Data Grows Large

### 5.1 Copying files: prefer the direct API

If both input and output are `Path`, there is no need to write a loop yourself:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path source = Path.of("data", "source.bin");
Path target = Path.of("data", "backup.bin");
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

This is an **illustrative snippet** placed inside a method that handles/declares `IOException`; the source file and target directory must exist. `REPLACE_EXISTING` allows replacing an existing target file. If you do not want to replace it, omit this option and handle `FileAlreadyExistsException`. The API does not guarantee identical behavior across all file systems for metadata or symbolic links; check `CopyOption` options when needed.

### 5.2 Transferring bytes from an arbitrary source

When the source is an `InputStream` (for example, a response body, ZIP entry, or socket), read byte data and transfer it to an `OutputStream`:

```java
import java.io.InputStream;
import java.io.OutputStream;

// Illustrative snippet inside a method that throws IOException.
// sourceStream is an InputStream already opened by the caller.
try (InputStream in = sourceStream;
     OutputStream out = Files.newOutputStream(Path.of("download.bin"))) {
    in.transferTo(out);
}
```

You also need to import `java.nio.file.Files` and `java.nio.file.Path` if placing this snippet into a standalone program. `transferTo` (Java 9+) transfers all bytes until EOF; it does not decode charsets. When a stream is owned by a library/framework, check **who is responsible for closing it** before putting it inside `try-with-resources`. For untrusted data or large uploads, add size limits, timeouts, and context-based cancellation rules.

### 5.3 Processing large text files line by line

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedReader reader = Files.newBufferedReader(
        Path.of("events.log"), StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        if (line.contains("ERROR")) {
            System.out.println(line);
        }
    }
}
```

This illustrative snippet is placed in a method that declares/handles `IOException`. It processes line by line instead of calling `Files.readAllLines`. `readLine` **does not return** the line separator characters; if you need to preserve original bytes, newline type, or original charset, you must choose another strategy. An individual extremely long line can still consume a lot of memory.

You can also use:

```java
try (var lines = Files.lines(Path.of("events.log"),
        StandardCharsets.UTF_8)) {
    long errors = lines.filter(line -> line.contains("ERROR")).count();
    System.out.println(errors);
}
```

The second snippet also requires importing `Files`, `Path`, `StandardCharsets` and declaring/handling `IOException`; the `Stream` object must be closed. `Files.lines` is lazy, so only a terminal operation (`count`, `forEach`, etc.) triggers reading. I/O errors while consuming the stream may be wrapped in an `UncheckedIOException`.

## 6. When You Must Use Channel: Two Truly Beneficial Scenarios

**Random access within a file:** for example, reading a header at offset 0, then reading a record at offset N. `SeekableByteChannel.position(N)` fits because a general `InputStream` does not have an operation to seek to an arbitrary position. `FileChannel` adds APIs such as `read(ByteBuffer, position)` and `write(ByteBuffer, position)`.

**Non-blocking network I/O:** `SocketChannel.configureBlocking(false)` combined with `Selector` enables managing multiple connections. That mechanism requires connection lifecycle management, partial read/write handling, and readiness state handling. Do not apply a selector design to a simple text file reading task.

Illustrative example of reading in chunks with a channel (placed inside a method `throws IOException`):

```java
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

try (FileChannel channel = FileChannel.open(
        Path.of("large.bin"), StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(8192);
    long total = 0;

    while (true) {
        int n = channel.read(buffer);
        if (n == -1) break;
        if (n == 0) continue;
        total += n;

        buffer.flip();
        // Consume the bytes in [position, limit) here.
        buffer.position(buffer.limit());
        buffer.clear();
    }
    System.out.println("Total bytes: " + total);
}
```

`channel.read` can return `0` even before EOF, so that value must be handled. `flip` makes the newly received byte range ready for reading; `clear` is called after **completely consuming** that range. In real applications, replace `buffer.position(buffer.limit())` with actual data processing and use `compact` if unprocessed bytes remain. Do not assume that `FileChannel.transferTo` always performs zero-copy: optimizations depend on the environment and target channel.

## 7. Memory, Charset, Resources, and Common API Selection Mistakes

| Mistake | Consequence | How to choose/adjust |
| --- | --- | --- |
| Using `Reader` to read images, ZIP, PDF | Byte decoding alters the data | Use `InputStream`, `Files.readAllBytes` if small, or a channel when needed |
| Using `InputStream` and casting each byte to `char` to read Vietnamese text | UTF-8 is multi-byte, causing garbled text | Use `InputStreamReader(in, UTF_8)` / `Files.newBufferedReader` |
| Calling `readString`/`readAllBytes` on an unbounded file | Risk of high heap usage or `OutOfMemoryError` | Read line by line or in chunks with a buffer |
| Relying on the default charset unintentionally | May read differently across systems or data sources | Pass `StandardCharsets.UTF_8` or the source's actual charset |
| Assuming `read(buffer)` always fills `buffer.length` | Data loss when handling partial reads incorrectly | Loop until the required number of bytes is read or `-1` is reached |
| Forgetting `flip()` before reading bytes from a buffer just written to | Wrong position/limit, reading the wrong range | Call `flip` when switching write → read; `clear`/`compact` for the next iteration |
| Not closing `Files.lines`/reader/stream/channel | File descriptor leaks, locked resources | `try-with-resources` |
| Using a channel just to read a small string | Complex code, manual buffer/charset handling | `Files.readString(path, charset)` |
| Checking `Files.exists` and trusting the file still exists | The file can change between check and operation | Perform the operation and handle the exception |
| Judging performance solely by API name | Wrong decisions due to cache, buffering, size, and device | Benchmark under realistic load; use the simple API first |

**Memory limits:** `readAllBytes`/`readString`/`readAllLines` hold all data or result structures in RAM. `BufferedReader` and `InputStream` with a fixed buffer generally keep RAM usage steadier; however, a single very long line or custom logic accumulating results can still cause memory bloat.

**Charset and decoding errors:** UTF-8 is the common choice, but real files may use another charset or include a BOM. Verify the format before reading; do not assume every byte sequence is valid UTF-8. If you need a strict policy when encountering malformed bytes, use a `CharsetDecoder` configured with `CodingErrorAction.REPORT` instead of silently accepting replacement characters.

**Resources:** `Files.readString`, `Files.readAllBytes`, and `Files.copy(Path, Path, ...)` manage opening/closing internally. APIs that return an open resource such as `Files.newInputStream`, `Files.newBufferedReader`, `Files.lines`, or `FileChannel.open` must be closed by the caller. For pipelines that both read and write, clearly establish stream ownership; `flush` does not replace `close`.

**Paths and permissions:** `NoSuchFileException`, `AccessDeniedException`, `FileAlreadyExistsException`, and `IOException` provide useful failure details. Do not infer causes solely from `Files.exists`; permissions, symbolic links, and concurrent modifications can affect the outcome. If an operation must be safe with respect to overwriting or replacing a file, specify `OpenOption`/`CopyOption` explicitly along with atomicity requirements.

## 8. Pre-Coding Checklist

1. Is the **source/destination** a file (`Path`), memory, HTTP body, socket, or library-provided stream?
2. Is the **data meaning** raw bytes or characters needing decoding? If text, which charset?
3. Is the **size** definitely bounded? If not, process line by line or in chunks and enforce input limits.
4. Is the **access pattern** sequential from start to end, line by line, or does it require seek/lock/mapping/non-blocking?
5. Who holds **resource ownership**; what needs to be closed; which options govern overwrite/create/append?
6. Should **error handling** propagate, retry, log, or abort? Is data integrity verification needed?

If a task only needs to "read a few-KB UTF-8 config file", the clear choice is usually `Files.readString`. If you need to "filter 30 GB of logs line by line", use `BufferedReader` or `Files.lines` with a clear lifecycle. If you need to "stream a ZIP file from HTTP to disk", use a byte stream. If you need to "update a binary field at a specific offset", choose `SeekableByteChannel`/`FileChannel`. That is how to choose based on the **shape of the problem** rather than the API name.
