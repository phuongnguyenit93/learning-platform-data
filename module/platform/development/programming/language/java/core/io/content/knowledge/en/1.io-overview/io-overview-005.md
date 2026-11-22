# Map of `java.io`, `java.nio`, and NIO.2

## Lesson Objectives

After this lesson, you can choose the right API for reading/writing files, processing text, binary data, network connections, and monitoring the filesystem; understand the roles of **stream**, **reader/writer**, **buffer**, **channel**, **selector**, **`Path`**, and **`Files`**; and distinguish between blocking, non-blocking, and asynchronous I/O.

The three names often appear together, but they are not three mutually exclusive systems:

- **`java.io`**: traditional stream/reader/writer API, oriented toward sequential data processing.
- **`java.nio`** (along with `java.nio.channels`, `java.nio.charset`): buffers, channels, selectors, and charset conversion.
- **NIO.2**, introduced in Java 7: the name for the I/O extensions, most notably `java.nio.file` with `Path`, `Files`, `FileSystem`, file attributes, and `WatchService`, along with asynchronous channels. There is no standard `java.nio2` package.

## 1. Ecosystem Map

```text
I/O Problem
├── Sequential byte reading/writing
│   ├── java.io.InputStream / OutputStream
│   └── java.nio.file.Files.newInputStream / newOutputStream
├── Text reading/writing
│   ├── java.io.Reader / Writer, BufferedReader / BufferedWriter
│   ├── java.nio.charset.Charset / CharsetDecoder / CharsetEncoder
│   └── java.nio.file.Files.newBufferedReader / newBufferedWriter
├── Paths, files, directories, metadata
│   ├── java.io.File (legacy)
│   └── java.nio.file.Path / Files / FileSystem / FileStore / attributes
├── Byte access with buffer, position, mapping
│   └── java.nio.ByteBuffer + java.nio.channels.FileChannel
├── Network connections
│   ├── java.net.Socket + InputStream / OutputStream
│   └── java.nio.channels.SocketChannel / ServerSocketChannel /
│       DatagramChannel + ByteBuffer
├── Event-driven management of multiple sockets
│   └── SelectableChannel + Selector
└── File reading/writing with asynchronous results
    └── java.nio.channels.AsynchronousFileChannel
```

There are three independent questions:

1. **Is the data bytes or text?** Streams handle bytes; Reader/Writer handle characters and use a charset to relate to bytes. `ByteBuffer` holds bytes in memory.
2. **What is the source/destination?** The filesystem uses `Path`/`Files`; sockets have their own channels; no single API replaces every type of data source.
3. **Which execution model?** Blocking, non-blocking, or asynchronous completion? The name NIO does not guarantee that every operation is non-blocking.

## 2. `java.io`: streams, reader/writer, and wrapper classes

### Byte streams

`InputStream` reads bytes; `OutputStream` writes bytes. Typical APIs:

| API | Purpose |
|---|---|
| `FileInputStream` / `FileOutputStream` | Byte I/O from files |
| `BufferedInputStream` / `BufferedOutputStream` | Reduce the number of small I/O operations |
| `DataInputStream` / `DataOutputStream` | Read/write primitive types in binary format |
| `ByteArrayInputStream` / `ByteArrayOutputStream` | Data in a byte array |
| `PrintStream` | Output text data, such as `System.out` |
| `ObjectInputStream` / `ObjectOutputStream` | Java serialization; avoid deserializing untrusted data |

`InputStream.read()` returns `0..255` or `-1` at end of data. `read(byte[])` **may read fewer** bytes than requested; never treat a single read call as a complete record/message. `flush()` pushes data out of the stream's buffer, but does not by default mean durable write to the storage device.

Use try-with-resources to close the source/destination even when an exception occurs:

```java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(destination)) {
    in.transferTo(out);
}
```

This is an **illustrative snippet** (it assumes two variables `Path source`, `Path destination`; imports `java.io.*` and `java.nio.file.*`). `transferTo` has been available since Java 9. `Files.newInputStream` belongs to NIO.2 but **returns a `java.io.InputStream`**: the API families are designed to work together.

### Character streams and charsets

`Reader`/`Writer` work with characters; `InputStreamReader`/`OutputStreamWriter` convert back and forth between byte streams and character streams using a charset. `BufferedReader.readLine()` reads a line while **stripping line-ending characters**, and `BufferedWriter` is useful for incrementally writing large amounts of text.

```text
file bytes → InputStream → UTF-8 decoder → Reader → char
char → Writer → UTF-8 encoder → OutputStream → file bytes
```

Prefer an explicit charset, for example `StandardCharsets.UTF_8`. On **Java 17**, the default charset can depend on the operating system/configuration; since Java 18, JEP 400 made UTF-8 the default. For data formats requiring portability, still specify the charset explicitly.

One Unicode detail: `String` length counts UTF-16 `char` units, not the number of UTF-8 bytes or code points. Characters outside the BMP may use two `char` values (a surrogate pair).

### `java.io.File`

`File` represents a path in the legacy API, not the file content itself. In new code, `Path`/`Files` are usually preferred because they provide more filesystem operations and more specific I/O exceptions. When bridging with legacy APIs:

```java
Path path = oldFile.toPath();
File oldFileAgain = path.toFile();
```

This snippet assumes `oldFile` is a `java.io.File`; `toFile()` is only guaranteed for a `Path` belonging to the default filesystem provider.

## 3. `java.nio`: Buffer + Channel + Charset + Selector

### Stateful `ByteBuffer`

`ByteBuffer` stores bytes and manages three values:

| Value | Meaning |
|---|---|
| `capacity` | Fixed capacity |
| `position` | Index of the next byte to be written/read |
| `limit` | Boundary allowed for access in the current phase |

Invariant: `0 <= position <= limit <= capacity`. Phase transition model:

```text
put(...) ──> buffer in write mode ── flip() ──> get(...)
                                     │
                               hasRemaining()
                                     │
                           ┌─────────┴─────────┐
                           │                   │
                   clear() rewrite      compact() keep unread
                   from buffer start    data, write more
```

- `put(...)` advances `position` when writing into the buffer.
- `flip()` sets `limit = position`, `position = 0` to read what was just written.
- `get()` advances `position` when reading.
- `clear()` sets `position = 0`, `limit = capacity`, **without erasing bytes from memory**.
- `compact()` moves unread bytes to the beginning and sets the position to append more bytes.
- `rewind()` sets `position = 0` without changing `limit`.

Standalone Java 17 program, saved to **`ByteBufferStateDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

public class ByteBufferStateDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(5);
        buffer.put(new byte[] {10, 20, 30});
        System.out.printf(
            "write: position=%d, limit=%d, capacity=%d%n",
            buffer.position(), buffer.limit(), buffer.capacity()
        );

        buffer.flip();
        System.out.println("read: " + buffer.get() + ", " + buffer.get());

        buffer.compact();  // Keep 30, prepare to write more
        buffer.put((byte) 40);
        buffer.flip();

        List<Integer> remaining = new ArrayList<>();
        while (buffer.hasRemaining()) {
            remaining.add(Byte.toUnsignedInt(buffer.get()));
        }
        System.out.println("remaining: " + remaining);
    }
}
```

Run:

```bash
javac ByteBufferStateDemo.java
java ByteBufferStateDemo
```

Stdout:

```text
write: position=3, limit=5, capacity=5
read: 10, 20
remaining: [30, 40]
```

The output proves that `compact()` preserves the unread value 30. If `clear()` were called instead of `compact()`, that byte range would no longer be marked to be kept.

`ByteBuffer.allocate` allocates a heap buffer; `allocateDirect` creates a direct buffer that can reduce some copying steps in native I/O, though allocation/reclamation costs and memory limits differ. Do not assume direct buffers are always faster. `ByteOrder` defines the byte order for multi-byte numbers, which is distinct from text charsets.

### `Channel` transports; `Buffer` holds bytes

`Channel` represents an I/O connection. Byte channels read into a `ByteBuffer` or write from a `ByteBuffer`:

```text
Read: source → channel.read(buffer) → buffer written → flip() → get()
Write: put(...) → buffer has data → flip() → channel.write(buffer) → destination
```

`FileChannel` supports positional read/write, `position`, `size`, `truncate`, `transferTo`, `transferFrom`, `map`, and `force`. A `read(buffer)` call may return `-1` at EOF, `0`, or a positive byte count smaller than capacity; a `write(buffer)` call may write fewer than all remaining bytes. When all data needs to be transferred, check the result and loop based on `hasRemaining()`.

`FileChannel.map` returns a `MappedByteBuffer` to map a file region into memory. It helps with certain large/random-access data patterns, but brings mapping management, native resources, and data consistency considerations; it is not the default way to read files.

### Charsets and chunk boundaries

`java.nio.charset.Charset`, `CharsetDecoder`, and `CharsetEncoder` handle character representations. `StandardCharsets.UTF_8.decode(buffer)` is convenient when the buffer contains the **entire** UTF-8 byte sequence. When data arrives in multiple chunks, bytes of the same character may be split across two chunks; use a streaming decoder, retain incomplete bytes, and avoid converting each chunk independently into a String, which would produce corrupted characters.

### Selector and non-blocking networking

`Selector` allows a single thread to wait for readiness events on multiple **`SelectableChannel`** instances:

1. Open a `Selector`, create a `SocketChannel`, and call `configureBlocking(false)`.
2. Register the channel with the appropriate operations such as `OP_CONNECT`, `OP_READ`, `OP_WRITE`.
3. In the event loop, call `select()` or `select(timeout)`, process ready `SelectionKey` instances, and remove handled keys from the selected-key set.
4. Maintain partial read/write state across events, handle errors, close resources, and manage backpressure.

`SocketChannel`, `ServerSocketChannel`, `DatagramChannel`, and some pipe channels can use a selector. **`FileChannel` is not a `SelectableChannel` and cannot be registered with a selector.** Keeping `OP_WRITE` registered continuously can cause a busy loop because sockets are usually ready for writing; only register it when pending data remains, depending on the event loop design.

A selector does not automatically handle protocol framing, timeouts, thread safety, or backpressure. TCP is a **byte stream**: a single `read` may receive half a message or multiple messages; the application must define message framing.

## 4. NIO.2: `Path`, `Files`, and filesystem services

### `Path` represents paths; `Files` performs operations

`Path` represents path components belonging to a `FileSystem`; it does not imply the file already exists. `Files` is a set of methods for file/directory operations.

| Need | API |
|---|---|
| Create a path | `Path.of(...)`; `base.resolve("name.txt")` |
| Normalize syntax | `path.normalize()` |
| Check file type | `Files.isRegularFile`, `Files.isDirectory` |
| Read a small text file | `Files.readString(path, UTF_8)` |
| Write a text file | `Files.writeString(path, value, UTF_8)` |
| Process text as a stream | `Files.newBufferedReader`, `newBufferedWriter` |
| Process bytes | `Files.newInputStream`, `newOutputStream` |
| Create directory tree | `Files.createDirectories` |
| Copy/move | `Files.copy`, `Files.move` with options |
| List directory | `Files.list`, `Files.newDirectoryStream` |
| Traverse recursively | `Files.walk`, `Files.walkFileTree` |
| Attributes | `Files.readAttributes`, `BasicFileAttributes` |
| Watch for changes | `WatchService`, `Path.register` |

`Path.of("data", "file.txt")` is typically relative to the process working directory. `toAbsolutePath()` converts to an absolute path; `toRealPath()` also queries the filesystem and may resolve symbolic links. `normalize()` only cleans up syntactic elements like `.`/`..`, does not query disk, and does not guarantee safety.

Both `Files.exists(path)` and `Files.notExists(path)` can return `false` when the status cannot be determined. Checking first and then opening a file has a race condition (TOCTOU); handle the `IOException` of the operation itself instead of trusting that initial state remains unchanged.

### Practical example combining all three API families

Standalone Java 17 program, saved to **`IoMapDemo.java`**. It creates a file using `Path`/`Files` (NIO.2), reads text using `BufferedReader` (`java.io`), and reads bytes using `FileChannel`/`ByteBuffer` (NIO).

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class IoMapDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("io-map-");
        Path file = dir.resolve("message.txt");

        try {
            Files.writeString(file, "Xin chào Java\n", StandardCharsets.UTF_8);

            try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                System.out.println("Reader: " + reader.readLine());
            }

            try (FileChannel channel =
                     FileChannel.open(file, StandardOpenOption.READ)) {
                ByteBuffer buffer = ByteBuffer.allocate(64);
                int bytesRead = channel.read(buffer);
                buffer.flip();

                String text = StandardCharsets.UTF_8.decode(buffer)
                    .toString().stripTrailing();

                System.out.println("Channel bytes: " + bytesRead);
                System.out.println("Channel text: " + text);
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

Run:

```bash
javac IoMapDemo.java
java IoMapDemo
```

Stdout:

```text
Reader: Xin chào Java
Channel bytes: 15
Channel text: Xin chào Java
```

`Xin chào Java` with `\\n` has 14 `char` values but occupies **15 UTF-8 bytes** because `à` uses two bytes. A 64-byte buffer is large enough to hold all the data in this example. For larger files, you must loop reads and manage UTF-8 boundaries across chunks. The `finally` block cleans up the exact directory/file created in the example; do not apply similar deletion to user files.

### Directory traversal and attributes

`Files.list(dir)` returns a `Stream<Path>` of direct entries; `Files.walk(dir)` can descend into the tree. Streams created by these two APIs hold filesystem resources: they must be closed.

```java
try (var paths = Files.list(dir)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
```

The illustrative snippet requires a `Path dir` variable and `import java.nio.file.Files`; stdout depends on actual contents. `Files.walkFileTree` with a `FileVisitor` is suitable when error handling, deep traversal, and per-node behavior control are needed.

Support for `Files.size`, `BasicFileAttributes`, `PosixFileAttributes`, and `DosFileAttributes` depends on the filesystem provider/operating system. Do not assume POSIX attributes exist on Windows, or that symbolic links behave identically everywhere. `Files.readSymbolicLink`, `Files.isSymbolicLink`, and `LinkOption.NOFOLLOW_LINKS` help distinguish certain operations on links. If following links during tree traversal, handle link cycles and access permissions.

### `WatchService`

`FileSystem.newWatchService()` creates a watcher; call `directory.register(watcher, ENTRY_CREATE, ENTRY_MODIFY, ENTRY_DELETE)` to register a directory. The loop receives a `WatchKey`, reads `pollEvents()`, handles `OVERFLOW`, and calls `reset()`; when `reset()` returns false, the key is no longer valid. Watching a directory does not automatically watch its entire subtree. Events may be coalesced, delayed, or lost due to queue overflow or provider/OS behavior; applications must reconcile against actual state when accuracy is required.

## 5. Blocking, non-blocking, and asynchronous are different mechanisms

| Model | Example API | Characteristics |
|---|---|---|
| Synchronous, usually blocking | `InputStream.read`, `Files.readString`, regular `FileChannel` operations | The calling thread waits for the operation to complete per API semantics |
| Non-blocking | `SocketChannel.configureBlocking(false)` + `Selector` | A single read/write may make no progress; maintain state and handle events yourself |
| Asynchronous completion | `AsynchronousFileChannel.read` with `Future` or `CompletionHandler` | Initiate I/O and receive the result later; the implementation may be thread-pool based |

Short async example, **not a standalone program** (assuming a `Path path` variable and a method that allows `throws Exception`):

```java
try (AsynchronousFileChannel channel =
         AsynchronousFileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(1024);
    Future<Integer> pending = channel.read(buffer, 0L);
    int count = pending.get();  // Current thread waits here
    if (count > 0) {
        buffer.flip();
        // Process the bytes just read
    }
}
```

Requires importing `java.nio.ByteBuffer`, `java.nio.channels.AsynchronousFileChannel`, `java.nio.file.StandardOpenOption`, and `java.util.concurrent.Future`. Calling `pending.get()` immediately after `read` still makes the calling thread **wait**; to avoid waiting directly, you can use `CompletionHandler`. Providers are not required to use native kernel asynchronous I/O.

NIO.2 also adds `AsynchronousSocketChannel` and `AsynchronousServerSocketChannel` for networking; their callback/completion model differs from an event loop with `Selector`.

## 6. Important bridges (adapters)

```text
java.io.File ──────────── .toPath() ──> Path
default Path ──────────── .toFile() ──> java.io.File
Path ───────── Files.newInputStream ──> InputStream
Path ─── Files.newBufferedReader ──> BufferedReader
Path ──────── FileChannel.open ──> FileChannel ↔ ByteBuffer
Channel ─── Channels.newInputStream ──> InputStream
InputStream ─── Channels.newChannel ──> ReadableByteChannel
```

`java.nio.channels.Channels` is where stream/channel adapters live. Wrapping a stream as a channel **does not automatically turn it into a selectable channel**. `Files.newByteChannel` can provide a `SeekableByteChannel` for positional byte access; `FileChannel` has additional file features such as transfer, mapping, and force.

When a library expects an `InputStream`, `Reader`, `Path`, or `ByteBuffer`, use the type the library accepts and convert at the appropriate boundary. There is no need to rebuild a complex buffer/channel pipeline just to use a newer API.

## 7. API selection table by use case

| Use case | Typical choice | When to change |
|---|---|---|
| Read small text with a known charset | `Files.readString(path, UTF_8)` | Large text: `newBufferedReader` to read incrementally |
| Write text | `Files.writeString` or `newBufferedWriter` | Long/incremental writes: writer and buffer |
| Copy files | `Files.copy` | Non-file data: streams/channels |
| Sequential binary processing | `InputStream`/`OutputStream` | Offset-based access: `FileChannel` |
| Update a region of a file | `FileChannel`/`SeekableByteChannel` | Measured large mapping: `MappedByteBuffer` |
| File listing, metadata | `Path`, `Files`, `FileVisitor` | Legacy API needing `File`: use adapter |
| Simple networking | Socket + streams | Many sockets: consider channels + selector |
| Watch directory changes | `WatchService` | Need accurate state: combine with verification scan |
| File I/O with async completion | `AsynchronousFileChannel` | Only need synchronous I/O: `FileChannel`/`Files` |

Always consider **data type, size, access pattern, connection count, and concurrency needs** before choosing. `Files.readAllBytes` and `Files.readString` hold contents in memory, easily causing heap pressure with input files of uncontrolled size.

## 8. Common pitfalls and limitations to remember

1. **Confusing bytes and characters.** Do not rely on `String` length to infer UTF-8 byte count, and do not decode each chunk independently when a character may span multiple chunks.
2. **Equating NIO with non-blocking.** `Files.readString` and regular `FileChannel` are synchronous; `FileChannel` cannot be registered with a `Selector`.
3. **Assuming a single read/write completes everything.** Handle EOF `-1`, partial reads/writes, backpressure, and protocol framing.
4. **Forgetting `flip()`, or calling `clear()` too early.** `compact()` retains unread bytes when more data needs to be appended.
5. **Resource leaks.** Use try-with-resources for streams, readers/writers, channels, `DirectoryStream`, `Files.list`/`walk` streams, and `WatchService`.
6. **Confusing flush/close with durability and atomicity.** `Files.move(..., ATOMIC_MOVE)` may throw `AtomicMoveNotSupportedException`; `flush` does not automatically guarantee `fsync`. Critical data requires a temporary-file, sync, move, and platform-verified fallback workflow.
7. **Assuming paths behave the same everywhere.** Differences in case sensitivity, permissions, separators, symlinks, metadata, default charset, and filesystem providers can all make code non-portable.
8. **Checking state and assuming it does not change.** `Files.exists`, `isReadable`, and path normalization do not prevent TOCTOU, symlink swaps, or permission errors; you must handle exceptions from the actual operation.
9. **Unbounded resource usage.** Limit open files/channels, native buffers, traversal depth, and data sizes; file mappings have their own lifecycle.
10. **Deserializing untrusted data.** `ObjectInputStream` carries security risks with untrusted sources; prefer formats/protocols with explicit input validation.

## 9. Self-check questions

1. You need to read a 2 GB UTF-8 CSV. Why is `Files.readString` usually unsuitable? Choose `Files.newBufferedReader` and explain resource closing and record-by-record processing.
2. A `ByteBuffer` has `capacity=8`, and 5 bytes have been written. After `flip()`, `position=0, limit=5`. After reading 2 bytes and calling `compact()`, **`position=3, limit=8`**. Why?
3. A server needs to serve many TCP connections. What problem does `SocketChannel` + `Selector` solve, and how do you still need to handle protocol framing/backpressure yourself?
4. Can you register a `FileChannel` with a `Selector`? **No**, because it is not a `SelectableChannel`.
5. Can `WatchService` be treated as a complete event history? **No**, because events can be coalesced/lost and `OVERFLOW` can occur; you need to reconcile with the filesystem.

**Key takeaway:** `java.io` provides streams and readers/writers; `java.nio` provides buffers, channels, charsets, and selectors; NIO.2 extends them with `Path`, `Files`, filesystem services, and asynchronous APIs. They complement one another and are chosen based on the nature of the application's I/O.
