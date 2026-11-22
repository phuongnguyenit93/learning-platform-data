# Traditional API, NIO, NIO.2, and Java Version Milestones Table

Multiple I/O classes coexist in Java because the platform evolved across JDK releases. **Traditional `java.io`**, **NIO (Java 1.4)**, and **NIO.2 (Java 7)** are API groups with different strengths; NIO.2 adds a modern file system API and several asynchronous APIs, **without replacing all of `java.io` or NIO**. This reference table helps you find the right class, understand version milestones, and choose the right API for Java 17+ programs.

## 1. Map of the Three API Generations

| Group | Introduced | Representative packages/classes | Core model | Suitable problems |
|---|---|---|---|---|
| Traditional I/O | Java 1.0; Reader/Writer added in Java 1.1 | `java.io.InputStream`, `OutputStream`, `Reader`, `Writer`, `File`, `RandomAccessFile` | Byte or character streams, sequential processing; ordinary read/write calls may block | Stream I/O, simple protocols, filtering/buffering, legacy-compatible APIs |
| NIO (New I/O) | Java 1.4 | `java.nio.Buffer`/`ByteBuffer`, `java.nio.channels.FileChannel`/`SocketChannel`/`Selector`, `java.nio.charset.Charset` | Buffers, channels, charsets; supports multiplexing and non-blocking mode for **some** channels | Binary data, buffer-based I/O, many network connections with a selector, channel operations |
| NIO.2 (often called NIO.2/JSR 203) | Java 7 | `java.nio.file.Path`, `Files`, `FileSystem`, `WatchService`, `FileVisitor`; `java.nio.channels.AsynchronousFileChannel` | Rich file system API, file attributes, tree walking, change monitoring, asynchronous I/O | File/directory management, copy/move/delete, metadata, symbolic links, watching directories, async channels |

**Name distinction:** NIO stands for *New I/O*, not a promise that every operation is *non-blocking*. `FileChannel` read/write operations are typically blocking; `SocketChannel` can be configured as blocking or non-blocking. `Selector` works only with compatible `SelectableChannel`s (such as `SocketChannel`); you cannot register a `FileChannel` to watch regular files.

**Two things can be true at once:** `Files.newInputStream(path)` belongs to NIO.2 utilities yet returns `java.io.InputStream`; an application can combine `Path`, `Files`, streams, and channels in the same processing pipeline. The classification reflects *when an API was added*, not mutually exclusive technologies.

## 2. Timeline of Key Milestones

| Java Milestone | Representative APIs/features | Significance for source code |
|---|---|---|
| **JDK 1.0 (1996)** | `InputStream`, `OutputStream`, `File`, `FileInputStream`, `FileOutputStream`, `RandomAccessFile` | Foundation for byte streams and traditional file paths |
| **JDK 1.1 (1997)** | `Reader`/`Writer` family, `InputStreamReader`, `OutputStreamWriter` | Byte ↔ character conversion layer using character encodings |
| **JDK 1.4 (2002)** | `ByteBuffer`/`CharBuffer`, `Channel`, `FileChannel`, `SocketChannel`, `Selector`, `Charset` | NIO 1: buffers/channels, character encoding, socket multiplexing |
| **Java 7 (2011)** | `Path`, `Paths`, `Files`, `FileSystem`, `WatchService`, `FileVisitor`, `StandardOpenOption`; `AsynchronousFileChannel`/`AsynchronousSocketChannel` | NIO.2: new file system API, async files, and directory watching |
| **Java 8 (2014)** | `Files.list`, `Files.walk`, `Files.find`, `Files.lines` | `Stream` integration for listing/finding/reading lines lazily; streams hold resources that must be closed |
| **Java 9 (2017)** | `InputStream.readAllBytes`, `readNBytes`, `transferTo` | Added utilities to traditional streams; **distinct from** `Files.readAllBytes`, which existed since Java 7 |
| **Java 11 (2018)** | `Path.of`; `Files.readString`, `Files.writeString` | Convenient for reading/writing UTF-8 text files; `Paths.get` remains an option for Java 7 compatibility |
| **Java 12 (2019)** | `Files.mismatch` | Returns the index of the first differing byte between two files, or `-1` if identical |
| **Java 21 (2023)** | Standardized virtual threads (JEP 444), usable with many blocking I/O idioms | Improves concurrency programming model; **does not create an "NIO.3" API generation** |

Dates/versions in the table indicate **when an API first appeared**, not when older classes stopped working. In Java 17/21, `java.io`, NIO, and NIO.2 are all supported. Check the exact **method**, not just the **class name**: `InputStream` dates from Java 1.0, yet `InputStream.transferTo` arrived in Java 9; `Path` dates from Java 7, yet `Path.of` only exists from Java 11.

## 3. Class/Method Lookup Table by Need

| Need | Traditional `java.io` | NIO (Java 1.4) | NIO.2 (Java 7+) and later additions |
|---|---|---|---|
| Represent a path | `File` | — | `Path`/`Paths.get` (7), `Path.of` (11) |
| Create directories, check existence, get size | `File.mkdir`/`mkdirs`, `exists`, `length` | — | `Files.createDirectory`/`createDirectories`, `exists`, `size` |
| Open a byte stream from a file | `FileInputStream`/`FileOutputStream`, buffered with `BufferedInputStream`/`BufferedOutputStream` | `FileChannel`, `ByteBuffer` | `Files.newInputStream`/`newOutputStream`, `Files.newByteChannel` |
| Read/write characters with charset | `InputStreamReader`/`OutputStreamWriter`, `BufferedReader`/`BufferedWriter` | `Charset`, `CharsetDecoder`/`CharsetEncoder` | `Files.newBufferedReader`/`newBufferedWriter` (7); `readString`/`writeString` (11) |
| Read an entire small file | `FileInputStream` with a read loop | Channel and buffer | `Files.readAllBytes` (7); `Files.readString` (11) |
| Read lines of a large file | `BufferedReader.readLine` | `FileChannel` + manually managed decoder | `Files.lines` (8) returns a line stream; stream must be closed |
| Read/write data at an arbitrary position | `RandomAccessFile.seek` | `FileChannel.position`, `read/write(ByteBuffer, position)`, `map` | `Files.newByteChannel` → `SeekableByteChannel` |
| Copy/move/rename a file | Copy via stream; `File.renameTo` has platform-dependent behavior | `FileChannel.transferTo`/`transferFrom` | `Files.copy`, `Files.move`, `CopyOption` values |
| Delete a file and know failure reason | `File.delete` returns `boolean` | — | `Files.delete` throws specific exceptions; `deleteIfExists` |
| List or walk a directory | `File.listFiles` | — | `DirectoryStream`, `Files.walkFileTree` (7); `Files.list/walk/find` (8) |
| Read metadata/permissions/symbolic links | `File.lastModified`, `canRead`, etc. (limited) | — | `Files.readAttributes`, `BasicFileAttributes`, `PosixFileAttributes`, `FileOwnerAttributeView`, `Files.readSymbolicLink` |
| Detect file appearance/changes | Manual polling with `File` | — | `WatchService` and `WatchKey` (7) |
| Traditional socket networking | `java.net.Socket`/`ServerSocket` + streams | `SocketChannel`, `ServerSocketChannel`, `Selector` | `AsynchronousSocketChannel`/`AsynchronousServerSocketChannel` (7) |
| Asynchronous file I/O | No direct equivalent in classic stream family | `FileChannel` normally reads/writes synchronously | `AsynchronousFileChannel` (7), `Future` or `CompletionHandler` |

**Do not infer performance from API names alone.** `Files.copy` can be convenient and less error-prone; `FileChannel.transferTo` may enable OS optimizations without guaranteeing zero-copy on every platform; `ByteBuffer.allocateDirect` carries its own allocation and management costs. Measure under realistic workloads, data sizes, and file systems.

## 4. Method-Level Version Milestones: Avoiding Build Mistakes

| Statement/feature | Minimum Java | Notes |
|---|---:|---|
| `new File("a.txt")`, `new FileInputStream(...)` | 1.0 | `File` only represents a path; it does not open a stream by itself |
| `new InputStreamReader(in, charset)` | 1.1 (Reader/Writer family) | Always specify charset instead of relying on platform default |
| `ByteBuffer.allocate(1024)`, `FileInputStream.getChannel()` | 1.4 | `FileChannel`/`ByteBuffer` belong to NIO 1 |
| `Paths.get("a.txt")`, `Files.readAllBytes(path)` | 7 | Part of NIO.2; loading all bytes can consume significant RAM |
| `Files.copy(source, target, ...)`, `Files.walkFileTree(root, visitor)` | 7 | Operates on `Path`; has its own options and exceptions |
| `FileChannel.open(path, options...)` | 7 | The `FileChannel` class predates this `open` convenience method |
| `Files.lines(path)`, `Files.walk(root)` | 8 | Returned streams typically hold I/O resources and require `try-with-resources` |
| `in.transferTo(out)`, `in.readAllBytes()` on `InputStream` | 9 | Do not confuse `InputStream.transferTo` (9) with `FileChannel.transferTo` (1.4) |
| `Path.of("a.txt")`, `Files.readString(path)`, `Files.writeString(path, text)` | 11 | Defaults to UTF-8 when using overloads without a charset parameter |
| `Files.mismatch(path1, path2)` | 12 | Result is the index of the first differing byte, not a boolean |
| Virtual threads for I/O tasks | 21 | Concurrency feature; does not change when NIO.2 was introduced |

When building an application targeting multiple JDKs, use `javac --release 8` (or equivalent build configuration) so the compiler verifies both language features and APIs present in Java 8; merely setting `-source`/`-target` to 8 on a newer JDK does not provide the same API verification. For example, `Files.readString` will not compile with `--release 8` because it requires Java 11.

## 5. Relationships Between Stream, Channel, Buffer, and File System

~~~text
java.io
  InputStream / OutputStream        Reader / Writer
           │                              │
           └──────────── data ────────────┘
                         │
java.nio                 │
  ByteBuffer ←→ Channel  │   Charset: decode/encode byte ↔ character
  SelectableChannel → Selector (when using compatible sockets)
                         │
java.nio.file (NIO.2)
  Path → Files (copy, move, attributes, tree, stream factories)
             │
             ├── Files.newInputStream(...) → java.io.InputStream
             ├── Files.newByteChannel(...) → SeekableByteChannel
             ├── Files.newBufferedReader(...) → java.io.BufferedReader
             └── FileSystem / WatchService / FileVisitor
~~~

- **Stream** models a sequential flow of data. `InputStream`/`OutputStream` process **bytes**; `Reader`/`Writer` process **char** values (UTF-16 code units at the Java level). Converting between bytes and text requires a charset; `BufferedReader` buffers at the character layer and does not replace a decoder.
- **Channel + Buffer** models exchanging data through a memory region with `position`, `limit`, and `capacity`. After writing into a buffer to read back out, normally call `flip()`; after consuming data, use `clear()` or `compact()` depending on whether unprocessed bytes must be retained.
- **Path + Files** models file system entries and operations on them. `Path` can point to a file that does not exist yet; `Files` performs actions that may throw `IOException`.
- **Bridge**: `File.toPath()` and `Path.toFile()` convert between legacy code and NIO.2 for the default file system. `Path.toFile()` is not necessarily available for custom providers (such as a ZIP file system).
- **Blocking / non-blocking / asynchronous** are properties of **specific operation mechanisms**. You cannot deduce them from package names alone: NIO contains `FileChannel` which is typically blocking; NIO.2 contains synchronous `Files.readAllBytes`; network channels can be non-blocking; asynchronous channels use future results or callbacks.

## 6. Java 17+ Example: One File, Four Access Ways Across API Milestones

This program creates a temporary file and writes data with `FileOutputStream`, then reads it using (1) a traditional stream, (2) NIO 1's `FileChannel` + `ByteBuffer`, (3) NIO.2 Java 7's `Files.readAllBytes`, and (4) Java 11's `Files.readString`. The temporary file and directory are deleted in `finally`.

Save the file as **`IoApiTimelineDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class IoApiTimelineDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("io-api-demo-");
        Path file = dir.resolve("example.txt");
        try {
            try (OutputStream out = new FileOutputStream(file.toFile())) {
                out.write("Hello IO!\n".getBytes(StandardCharsets.UTF_8));
            }

            ByteArrayOutputStream legacy = new ByteArrayOutputStream();
            try (InputStream in = new FileInputStream(file.toFile())) {
                byte[] bytes = new byte[4];
                int count;
                while ((count = in.read(bytes)) != -1) {
                    legacy.write(bytes, 0, count);
                }
            }
            System.out.println("java.io: "
                    + new String(legacy.toByteArray(), StandardCharsets.UTF_8).trim());

            ByteArrayOutputStream nio = new ByteArrayOutputStream();
            try (FileInputStream in = new FileInputStream(file.toFile());
                 FileChannel channel = in.getChannel()) {
                ByteBuffer buffer = ByteBuffer.allocate(4);
                while (channel.read(buffer) != -1) {
                    buffer.flip();
                    while (buffer.hasRemaining()) {
                        nio.write(buffer.get());
                    }
                    buffer.clear();
                }
            }
            System.out.println("NIO 1.4: "
                    + new String(nio.toByteArray(), StandardCharsets.UTF_8).trim());

            System.out.println("NIO.2/JDK 7: "
                    + new String(Files.readAllBytes(file), StandardCharsets.UTF_8).trim());
            System.out.println("Java 11+: "
                    + Files.readString(file, StandardCharsets.UTF_8).trim());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac IoApiTimelineDemo.java
java IoApiTimelineDemo
~~~

Stdout:

~~~text
java.io: Hello IO!
NIO 1.4: Hello IO!
NIO.2/JDK 7: Hello IO!
Java 11+: Hello IO!
~~~

The same data is read through APIs from different milestones. The program **runs on Java 17+**: the source file itself does not automatically run unchanged on Java 7, because `Files.readString` in the last example requires Java 11. The NIO section manually uses a four-byte buffer to illustrate handling multiple `read` calls; no buffer is needed when you simply want to read small text with `Files.readString`.

## 7. Which API Should You Choose for Each Scenario?

| Scenario | Preferred choice | Reason/implementation rule |
|---|---|---|
| Reading a small UTF-8 configuration file on Java 11+ | `Files.readString(path, UTF_8)` | Concise, explicit charset; use only when small enough to load into memory |
| Writing a small text file on Java 11+ | `Files.writeString(path, text, UTF_8)` | Easy to use; check `OpenOption` if appending or preventing overwrites |
| Processing a large text file line by line | `Files.newBufferedReader` or `Files.lines` | Reads sequentially; close reader/stream with `try-with-resources` |
| Copying, moving, creating directories | `Files.copy`, `Files.move`, `Files.createDirectories` | Specific failure exceptions; consider replacement, atomicity, symlinks |
| Scanning a large directory tree/per-branch error control | `Files.walkFileTree` + `FileVisitor` | Actively handles errors, branching, and when files are visited |
| Watching changes in a directory | `WatchService` | Receive events, handle `OVERFLOW`, and re-register as needed; do not treat as a strictly exact audit log |
| Reading a file at a specific offset or mapping a file | `FileChannel` / `SeekableByteChannel` | Provides positional operations and suitable byte access |
| Many socket connections on few threads | `SocketChannel` + `Selector` | Requires non-blocking configuration and manual handling of partial reads/writes |
| Wanting callbacks for asynchronous I/O | `AsynchronousFileChannel` / `AsynchronousSocketChannel` | Uses `Future`/`CompletionHandler`; check platform support |
| Application depends on legacy library accepting `InputStream`/`Reader` | Keep `java.io` interfaces; create from `Files` if convenient | No need to change API signatures just to "switch to NIO.2" |

**Selection rules:** use `Path`/`Files` for most new *file system* tasks; use `InputStream`/`OutputStream` or `Reader`/`Writer` when you need *streams*; use channels and buffers when you need byte positions or specific network/I/O characteristics. "Newer" does not mean "faster", and upgrading the JDK does not require deleting valid `java.io` code.

## 8. Common Compatibility Traps and Behaviors

1. **A path is distinct from its content:** `new File(path)` and `Path.of(path)` do not create an actual file. `Files.exists(path)` can also return `false` when existence cannot be determined; do not assume `false` always proves no file exists. Open/read operations must still handle `IOException`.

2. **Charset:** `FileInputStream` only creates a byte stream; it does not automatically "read UTF-8". When turning bytes into text, specify `StandardCharsets.UTF_8` explicitly. NIO `Charset` is the encoder/decoder; the default charset can vary across JDKs/runtime configurations. `Files.readString`/`writeString` without a charset argument use UTF-8.

3. **Resources:** close streams, readers, channels, `DirectoryStream`, and streams returned by `Files.list`/`walk`/`lines`. `Files.readAllBytes`/`readString` close the file automatically after the operation; in return, all data is loaded into memory.

4. **Copy/move options:** `Files.copy` and `Files.move` have default rules and `CopyOption` parameters; `REPLACE_EXISTING` requests replacement behavior. `ATOMIC_MOVE` only requests an atomic move and may fail with `AtomicMoveNotSupportedException`, especially across different file systems. Do not claim copy/move steps are completely transaction-safe.

5. **Symbolic links and file attributes:** many `Files` operations follow symbolic links by default, while some APIs or options follow different rules. Use `LinkOption.NOFOLLOW_LINKS` when the API supports it and semantics require it. POSIX/ACL permissions depend on the provider/OS; do not apply POSIX rules to all Windows drives.

6. **WatchService:** events may be coalesced, dropped due to overflow, or arrive while a writer is still updating the file. You usually must re-scan directory state upon receiving `OVERFLOW`. Do not expect `WatchService` to recurse automatically into all subdirectories.

7. **Non-blocking is not asynchronous:** `SocketChannel.configureBlocking(false)` requires the application to handle partial reads/writes and `Selector` itself; `AsynchronousSocketChannel` delivers results via `Future`/`CompletionHandler`. Asynchronous completion does not automatically prove a single non-blocking kernel call on every OS.

8. **Do not use file size to call `read` exactly once:** both streams and channels may return fewer bytes than requested. When a full count is required, loop while checking bytes read and EOF. Writing through a channel may also consume only part of a buffer. When handling fragmented network data, use `compact()` to retain undecoded bytes.

9. **`File` and `Path` share no inheritance relationship:** convert using `file.toPath()` or `path.toFile()` (with the default file-system provider). Other providers such as ZIP file systems may not support `toFile()`.

10. **When building for older JDKs:** distinguish APIs existing on the **compile JDK** from APIs existing on the **runtime JDK**; verify *method* milestones, not just package milestones. Do not call `InputStream.readAllBytes` when targeting Java 8, even though `InputStream` itself has existed since the beginning.

## 9. Quick-Lookup Summary

| If you see code like… | Identify it accurately as |
|---|---|
| `new FileInputStream(file)`, `BufferedReader`, `OutputStream` | Traditional `java.io`; still works well in modern JDKs |
| `ByteBuffer.flip()`, `FileChannel`, `Selector` | NIO from Java 1.4; buffers/channels, only some channels are non-blocking |
| `Path`, `Files.copy`, `Files.walkFileTree`, `WatchService` | NIO.2 from Java 7; file system and accompanying APIs |
| `Files.lines`, `Files.walk` | Stream-based convenience APIs added in Java 8 |
| `InputStream.transferTo` | `java.io` utility added in Java 9 |
| `Files.readString`, `Path.of` | `java.nio.file` utilities added in Java 11 |
| `Files.mismatch` | Added in Java 12 |

**Core principle:** look up **class + method + minimum version**; choose according to the problem (stream, buffer/channel, or filesystem). Java 7 marks the arrival of NIO.2, yet APIs in `java.nio.file` continued to be added in Java 8/11/12.

### Official API Documentation

- [`java.io` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/package-summary.html)
- [`java.nio` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/package-summary.html)
- [`java.nio.channels` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html)
- [`java.nio.file` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/package-summary.html)
- [`java.nio.file` — Java SE 7](https://docs.oracle.com/javase/7/docs/api/java/nio/file/package-summary.html)
