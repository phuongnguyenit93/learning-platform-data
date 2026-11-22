# Legacy, NIO, NIO.2 APIs and Java Version Milestones Table

Java has multiple coexisting I/O layers because the platform expanded across JDK releases. **Traditional `java.io`**, **NIO (Java 1.4)**, and **NIO.2 (Java 7)** are API families with different strengths; NIO.2 added a modern file system API and several asynchronous APIs, **rather than replacing all of `java.io` or NIO**. This reference table helps locate the right classes, understand version milestones, and choose suitable APIs for Java 17+ programs.

## 1. Map of the Three API Generations

| Group | Introduced | Representative packages/classes | Core model | Suitable problems |
|---|---|---|---|---|
| Traditional I/O | Java 1.0; Reader/Writer added in Java 1.1 | `java.io.InputStream`, `OutputStream`, `Reader`, `Writer`, `File`, `RandomAccessFile` | Byte or character streams, sequential processing; ordinary read/write calls may block | Stream reading/writing, simple protocols, filtering/buffering, long-standing compatible APIs |
| NIO (New I/O) | Java 1.4 | `java.nio.Buffer`/`ByteBuffer`, `java.nio.channels.FileChannel`/`SocketChannel`/`Selector`, `java.nio.charset.Charset` | Buffers, channels, charsets; supports multiplexing and non-blocking for **certain** channels | Binary data, buffer-based I/O, many network connections with a selector, channel operations |
| NIO.2 (often called NIO.2/JSR 203) | Java 7 | `java.nio.file.Path`, `Files`, `FileSystem`, `WatchService`, `FileVisitor`; `java.nio.channels.AsynchronousFileChannel` | Feature-rich file system, file attributes, tree walking, change watching, asynchronous I/O | Managing files/directories, copy/move/delete, metadata, symbolic links, watching directories, async channels |

**Name distinction:** NIO stands for *New I/O*, not a promise that every operation is *non-blocking*. `FileChannel` has read/write operations that are generally blocking; `SocketChannel` can be configured as blocking or non-blocking. `Selector` works only with suitable `SelectableChannel` implementations (such as `SocketChannel`); you cannot register a `FileChannel` to monitor a regular file.

**Both things can be true at once:** `Files.newInputStream(path)` belongs to the NIO.2 utilities yet returns `java.io.InputStream`; an application can combine `Path`, `Files`, streams, and channels in the same processing flow. The classification reflects *which milestone introduced an API*, not mutually exclusive technologies.

## 2. Timeline of Key Milestones

| Java milestone | Representative APIs/features | Significance for codebases |
|---|---|---|
| **JDK 1.0 (1996)** | `InputStream`, `OutputStream`, `File`, `FileInputStream`, `FileOutputStream`, `RandomAccessFile` | Foundation for byte streams and traditional file paths |
| **JDK 1.1 (1997)** | `Reader`/`Writer` hierarchy, `InputStreamReader`, `OutputStreamWriter` | Byte ↔ character conversion layer by character encoding |
| **JDK 1.4 (2002)** | `ByteBuffer`/`CharBuffer`, `Channel`, `FileChannel`, `SocketChannel`, `Selector`, `Charset` | NIO 1: buffers/channels, character encoding, socket multiplexing |
| **Java 7 (2011)** | `Path`, `Paths`, `Files`, `FileSystem`, `WatchService`, `FileVisitor`, `StandardOpenOption`; `AsynchronousFileChannel`/`AsynchronousSocketChannel` | NIO.2: new file system API, async file I/O, and directory watching |
| **Java 8 (2014)** | `Files.list`, `Files.walk`, `Files.find`, `Files.lines` | Integrates `Stream` for lazy listing/finding/line reading; streams hold resources that must be closed |
| **Java 9 (2017)** | `InputStream.readAllBytes`, `readNBytes`, `transferTo` | Adds utilities to traditional streams; **distinct from** `Files.readAllBytes` from Java 7 |
| **Java 11 (2018)** | `Path.of`; `Files.readString`, `Files.writeString` | Convenient for reading/writing UTF-8 text files; `Paths.get` remains the Java 7-compatible option |
| **Java 12 (2019)** | `Files.mismatch` | Returns the index of the first differing byte between two files, or `-1` if no difference |
| **Java 21 (2023)** | Standardized virtual threads (JEP 444), usable with many blocking I/O idioms | Improves concurrency programming model; **does not create an "NIO.3" API generation** |

Dates/versions in the table indicate **when an API first appeared**, not when an older class stopped working. In Java 17/21, `java.io`, NIO, and NIO.2 remain supported. Check the exact **method**, not just the **class name**: `InputStream` has existed since Java 1.0, yet `InputStream.transferTo` did not arrive until Java 9; `Path` arrived in Java 7, yet `Path.of` only arrived in Java 11.

## 3. Class/Method Lookup Table by Need

| Need | Traditional `java.io` | NIO (Java 1.4) | NIO.2 (Java 7+) and later additions |
|---|---|---|---|
| Represent a path | `File` | — | `Path`/`Paths.get` (7), `Path.of` (11) |
| Create directories, check, get size | `File.mkdir`/`mkdirs`, `exists`, `length` | — | `Files.createDirectory`/`createDirectories`, `exists`, `size` |
| Open a byte stream from a file | `FileInputStream`/`FileOutputStream`, buffered via `BufferedInputStream`/`BufferedOutputStream` | `FileChannel`, `ByteBuffer` | `Files.newInputStream`/`newOutputStream`, `Files.newByteChannel` |
| Read/write characters with charset | `InputStreamReader`/`OutputStreamWriter`, `BufferedReader`/`BufferedWriter` | `Charset`, `CharsetDecoder`/`CharsetEncoder` | `Files.newBufferedReader`/`newBufferedWriter` (7); `readString`/`writeString` (11) |
| Read an entire small file | `FileInputStream` and read loop | Channel and buffer | `Files.readAllBytes` (7); `Files.readString` (11) |
| Read lines of a large file | `BufferedReader.readLine` | `FileChannel` + manually managed decoder | `Files.lines` (8) creates a line stream; stream must be closed |
| Read/write data at an arbitrary position | `RandomAccessFile.seek` | `FileChannel.position`, `read/write(ByteBuffer, position)`, `map` | `Files.newByteChannel` → `SeekableByteChannel` |
| Copy/move/rename files | Copy via streams; `File.renameTo` has platform-dependent behavior | `FileChannel.transferTo`/`transferFrom` | `Files.copy`, `Files.move`, `CopyOption` options |
| Delete a file and learn the failure reason | `File.delete` returns `boolean` | — | `Files.delete` throws specific exceptions; `deleteIfExists` |
| List or traverse directories | `File.listFiles` | — | `DirectoryStream`, `Files.walkFileTree` (7); `Files.list/walk/find` (8) |
| Read metadata/permissions/symbolic links | `File.lastModified`, `canRead` ... limited | — | `Files.readAttributes`, `BasicFileAttributes`, `PosixFileAttributes`, `FileOwnerAttributeView`, `Files.readSymbolicLink` |
| Detect file creation/changes | Manual polling with `File` | — | `WatchService` and `WatchKey` (7) |
| Traditional socket networking | `java.net.Socket`/`ServerSocket` + streams | `SocketChannel`, `ServerSocketChannel`, `Selector` | `AsynchronousSocketChannel`/`AsynchronousServerSocketChannel` (7) |
| Asynchronous file I/O | No direct counterpart in classic stream family | `FileChannel` generally reads/writes synchronously | `AsynchronousFileChannel` (7), `Future` or `CompletionHandler` |

**Do not infer performance solely from API names.** `Files.copy` can be convenient and less error-prone; `FileChannel.transferTo` can enable OS-level optimizations without guaranteeing zero-copy on every platform; `ByteBuffer.allocateDirect` carries its own allocation and management costs. Measure against real workloads, data sizes, and file systems.

## 4. Exact Method Version Milestones: Avoiding Build Surprises

| Statement/feature | Minimum Java | Notes |
|---|---:|---|
| `new File("a.txt")`, `new FileInputStream(...)` | 1.0 | `File` only represents a path; does not open a stream itself |
| `new InputStreamReader(in, charset)` | 1.1 (Reader/Writer family) | Always specify the charset instead of relying on platform default |
| `ByteBuffer.allocate(1024)`, `FileInputStream.getChannel()` | 1.4 | `FileChannel`/`ByteBuffer` belong to NIO 1 |
| `Paths.get("a.txt")`, `Files.readAllBytes(path)` | 7 | Part of NIO.2; loading all bytes can consume significant RAM |
| `Files.copy(source, target, ...)`, `Files.walkFileTree(root, visitor)` | 7 | Operates on `Path`; has dedicated options and exceptions |
| `FileChannel.open(path, options...)` | 7 | The `FileChannel` class predates this `open` convenience method |
| `Files.lines(path)`, `Files.walk(root)` | 8 | Streams generally hold I/O resources and require `try-with-resources` |
| `in.transferTo(out)`, `in.readAllBytes()` on `InputStream` | 9 | Do not confuse `InputStream.transferTo` (9) with `FileChannel.transferTo` (1.4) |
| `Path.of("a.txt")`, `Files.readString(path)`, `Files.writeString(path, text)` | 11 | Defaults to UTF-8 when using overloads without a charset parameter |
| `Files.mismatch(path1, path2)` | 12 | Result is the index of the first differing byte, not a boolean |
| Virtual threads for I/O tasks | 21 | Concurrency feature; does not alter NIO.2's introduction history |

When building applications targeting multiple JDKs, use `javac --release 8` (or equivalent build configuration) so the compiler checks both language syntax and APIs present in Java 8; merely setting `-source`/`-target` to 8 on a newer JDK does not provide the same API verification. For example, `Files.readString` will not compile with `--release 8` because it requires Java 11.

## 5. Relationships Among Streams, Channels, Buffers, and File Systems

~~~text
java.io
  InputStream / OutputStream        Reader / Writer
           │                              │
           └──────────── data ────────────┘
                          │
java.nio                  │
  ByteBuffer ←→ Channel   │   Charset: decode/encode bytes ↔ characters
  SelectableChannel → Selector (when using a suitable socket)
                          │
java.nio.file (NIO.2)
  Path → Files (copy, move, attributes, tree, stream factories)
             │
             ├── Files.newInputStream(...) → java.io.InputStream
             ├── Files.newByteChannel(...) → SeekableByteChannel
             ├── Files.newBufferedReader(...) → java.io.BufferedReader
             └── FileSystem / WatchService / FileVisitor
~~~

- **Streams** model sequential data flows. `InputStream`/`OutputStream` process **bytes**; `Reader`/`Writer` process **char**s (UTF-16 units at the Java level). Converting between bytes and text requires a charset; `BufferedReader` is a character-layer buffer, not a replacement for a decoder.
- **Channel + Buffer** model data exchange through a memory region with `position`, `limit`, and `capacity`. After writing into a buffer to read it back, call `flip()`; after consuming it, call `clear()` or `compact()` depending on whether unprocessed bytes must be kept.
- **Path + Files** model objects in the file system and operations on them. A `Path` may refer to a non-existent file; `Files` performs actions that may throw `IOException`.
- **Bridges:** `File.toPath()` and `Path.toFile()` convert between legacy code and NIO.2 for the default file system. `Path.toFile()` is not necessarily supported by custom providers (such as a ZIP file system).
- **Blocking / non-blocking / asynchronous** are properties of **specific operational mechanisms**. You cannot deduce them from the package alone: NIO contains `FileChannel` which is normally blocking; NIO.2 contains synchronous `Files.readAllBytes`; network channels can be non-blocking; asynchronous channels deliver results via futures or callbacks.

## 6. Java 17+ Example: One File, Four Access Ways Across API Milestones

This program creates a temporary file and writes data using `FileOutputStream`, then reads it using (1) a traditional stream, (2) NIO 1's `FileChannel` + `ByteBuffer`, (3) NIO.2 Java 7's `Files.readAllBytes`, and (4) Java 11's `Files.readString`. The temporary file and directory are deleted in `finally`.

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

The same data is read through APIs from different milestones. The program **runs on Java 17+**: the source file itself is not meant to run unchanged on Java 7, because `Files.readString` in the final example requires Java 11. The NIO section intentionally uses a four-byte buffer to illustrate handling multiple `read` calls; no buffer is needed when you simply want to read small text with `Files.readString`.

## 7. Which API Should You Choose in Each Scenario?

| Scenario | Preferred choice | Rationale/implementation rule |
|---|---|---|
| Read a small UTF-8 configuration file on Java 11+ | `Files.readString(path, UTF_8)` | Short, explicit charset; use only when size is small enough to fit in memory |
| Write a small text file on Java 11+ | `Files.writeString(path, text, UTF_8)` | Easy to use; check `OpenOption` if appending or avoiding overwrites |
| Process a large text file line by line | `Files.newBufferedReader` or `Files.lines` | Reads sequentially; close reader/stream with `try-with-resources` |
| Copy, move, create directories | `Files.copy`, `Files.move`, `Files.createDirectories` | Specific exceptions on failure; consider replacement, atomicity, symlinks |
| Scan large directory trees / control per-branch errors | `Files.walkFileTree` + `FileVisitor` | Actively handles errors, branching, and visitation timing |
| Monitor changes in a directory | `WatchService` | Receives events, handles `OVERFLOW`, and re-registers when needed; do not treat as an exact audit log |
| Read a file at a specific offset or memory-map a file | `FileChannel` / `SeekableByteChannel` | Provides position operations and appropriate byte access |
| Many socket connections on few threads | `SocketChannel` + `Selector` | Requires non-blocking configuration and manual handling of partial reads/writes |
| Want callbacks for asynchronous I/O | `AsynchronousFileChannel` / `AsynchronousSocketChannel` | Uses `Future`/`CompletionHandler`; verify platform support |
| Application depends on legacy libraries accepting `InputStream`/`Reader` | Keep `java.io` interfaces; create via `Files` if convenient | No need to rewrite API signatures just to "migrate to NIO.2" |

**Selection rules:** use `Path`/`Files` for most new *file system* tasks; use `InputStream`/`OutputStream` or `Reader`/`Writer` when you need *streams*; use channels and buffers when you need byte positions or specific network/I/O capabilities. "Newer" does not mean "faster", and upgrading the JDK does not force deleting valid `java.io` code.

## 8. Common Compatibility Traps and Behavioral Pitfalls

1. **A path is different from its content:** `new File(path)` and `Path.of(path)` do not create an actual file. `Files.exists(path)` can also return `false` when existence cannot be determined; do not assume `false` always proves no file exists. Open/read operations must still handle `IOException`.

2. **Charsets:** `FileInputStream` only creates a byte stream; it does not automatically "read UTF-8". When turning bytes into text, specify `StandardCharsets.UTF_8`. NIO `Charset` handles encoding/decoding; the default charset can vary across JDKs/runtime configurations. `Files.readString`/`writeString` without a charset parameter use UTF-8.

3. **Resources:** close streams, readers, channels, `DirectoryStream`, and streams returned by `Files.list`/`walk`/`lines`. `Files.readAllBytes`/`readString` close the file automatically after the operation; in return, all data is loaded into memory.

4. **Copy/move options:** `Files.copy` and `Files.move` have default rules and `CopyOption` options; `REPLACE_EXISTING` requests replacement behavior. `ATOMIC_MOVE` only requests an atomic move and may fail with `AtomicMoveNotSupportedException`, especially across different file systems. Never claim copy/move steps are fully transaction-safe.

5. **Symbolic links and file attributes:** many `Files` operations follow symbolic links by default, though certain APIs or options have different rules. Use `LinkOption.NOFOLLOW_LINKS` where supported and required by semantics. POSIX/ACL permissions depend on the provider/OS; do not apply POSIX assumptions to every Windows drive.

6. **WatchService:** events can be coalesced, lost due to overflow, or arrive while a writer is still updating the file. You often need to re-scan directory state upon receiving `OVERFLOW`. Do not expect WatchService to automatically recurse into all subdirectories.

7. **Non-blocking is not asynchronous:** `SocketChannel.configureBlocking(false)` requires the application to handle partial reads/writes and `Selector`; `AsynchronousSocketChannel` delivers results via `Future`/`CompletionHandler`. An asynchronous API does not automatically guarantee a non-blocking kernel call on every OS.

8. **Do not use file size to issue exactly one `read`:** both streams and channels may return fewer bytes than requested. When all bytes are needed, loop while checking bytes read/EOF. Writing through a channel may also consume only part of a buffer. When handling fragmented network messages, use `compact()` to preserve undecoded bytes.

9. **`File` and `Path` share no inheritance relationship:** convert via `file.toPath()` or `path.toFile()` (with the default file-system provider). Other providers such as a ZIP file system may not support `toFile()`.

10. **When building for older JDKs:** distinguish APIs available on the **compiling JDK** from APIs available on the **runtime JDK**; verify *method* milestones, not just package milestones. Do not call `InputStream.readAllBytes` when targeting Java 8, even though `InputStream` itself has existed since the beginning.

## 9. Quick-Lookup Summary

| If you see code like… | Correct identification |
|---|---|
| `new FileInputStream(file)`, `BufferedReader`, `OutputStream` | Traditional `java.io`; still works well in modern JDKs |
| `ByteBuffer.flip()`, `FileChannel`, `Selector` | NIO from Java 1.4; buffers/channels, only certain channels are non-blocking |
| `Path`, `Files.copy`, `Files.walkFileTree`, `WatchService` | NIO.2 from Java 7; file system and extended APIs |
| `Files.lines`, `Files.walk` | Stream-based convenience APIs added in Java 8 |
| `InputStream.transferTo` | `java.io` utility added in Java 9 |
| `Files.readString`, `Path.of` | `java.nio.file` utilities added in Java 11 |
| `Files.mismatch` | Added in Java 12 |

**Core principle:** look up **class + method + minimum version**; choose by the problem shape (streams, buffers/channels, or filesystem). Java 7 is the NIO.2 milestone, yet APIs in `java.nio.file` continued to be added in Java 8/11/12.

### Official API Documentation

- [`java.io` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/package-summary.html)
- [`java.nio` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/package-summary.html)
- [`java.nio.channels` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html)
- [`java.nio.file` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/package-summary.html)
- [`java.nio.file` — Java SE 7](https://docs.oracle.com/javase/7/docs/api/java/nio/file/package-summary.html)
