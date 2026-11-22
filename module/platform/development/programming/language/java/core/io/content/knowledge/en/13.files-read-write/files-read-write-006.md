# `Files.newInputStream`, `Files.newOutputStream` and File Open Options in Java

When a Java application needs to **read or write file bytes** as a stream, `java.nio.file.Files.newInputStream(Path, OpenOption...)` and `Files.newOutputStream(Path, OpenOption...)` provide a way to open a file using a `Path` object and return standard Java I/O `InputStream`/`OutputStream` instances.

An issue even more important than syntax is **choosing how to open the file**: reading an existing file, creating a new one, overwriting old content, appending to the end, or failing if the path already exists. Getting a single `OpenOption` wrong can lead to **data loss**, overwriting a user's file, thinking you appended while actually erasing prior content, or writing half a file without detecting the failure.

This lesson belongs to the **Files Read and Write** series in Java Core I/O. The goal is to understand the default and optional behavior of both APIs, combine them with buffering and text transcoding, handle errors/resources, and pick the right solution for real-world scenarios.

## 1. Three Components: `Path`, `Files`, and Byte Streams

**`Path`** is Java NIO.2's path model, for example `Path.of("data", "input.bin")`. Creating a `Path` neither creates nor opens a file. It simply describes a file location according to filesystem/provider rules.

**`Files`** is a utility class with static methods operating on paths. The two main methods in this lesson:

```java
InputStream in = Files.newInputStream(path);
OutputStream out = Files.newOutputStream(path);
```

This is **illustrative code** requiring imports for `java.io.InputStream`, `java.io.OutputStream`, `java.nio.file.Files`, and `java.nio.file.Path`; variable `path` must be declared and opening can throw `IOException`.

**`InputStream` and `OutputStream`** operate on **bytes**, and have no built-in knowledge of text, charsets, newlines, or file formats. `InputStream.read()` returns a byte as an integer `0..255` or `-1` at EOF. `OutputStream.write(int)` writes one byte (the low 8 bits).

Diagram:

```text
Read:
Path -- Files.newInputStream(...) --> InputStream -- read() --> bytes
                                                                   |
                                                 decode if text is needed
                                                                   v
                                                        String / application data

Write:
String / application data -- encode if text --> bytes
                                                  |
Path -- Files.newOutputStream(...) --> OutputStream -- write() --> file
```

`Files.newInputStream` **is not like** `Files.readAllBytes`: it does not require loading the entire file into RAM before processing. Similarly, `Files.newOutputStream` is convenient for writing sequentially byte by byte or chunk by chunk, without allocating a single byte array containing the entire output upfront.

## 2. Syntax and Java Version

General declarations:

```java
public static InputStream newInputStream(Path path, OpenOption... options)
        throws IOException;

public static OutputStream newOutputStream(Path path, OpenOption... options)
        throws IOException;
```

Above, `OpenOption` is a marker interface for file open options, while `StandardOpenOption` is an enum containing common choices like `READ`, `WRITE`, `APPEND`, `CREATE`, and `CREATE_NEW`. Both APIs have been available since **Java 7** in NIO.2 and work directly in Java 17.

Common code example:

```java
try (InputStream input = Files.newInputStream(Path.of("input.bin"))) {
    // Read bytes.
}

try (OutputStream output = Files.newOutputStream(Path.of("output.bin"))) {
    // Write bytes.
}
```

This is **illustrative code** that must be placed inside a method declaring or handling `IOException`. `try-with-resources` automatically closes the stream upon exiting the block, even when an exception occurs.

Important point: `OpenOption...` is a **varargs** parameter, so you can omit it or pass multiple options. **Passing nothing** does not mean "no default behavior"; in particular, **the default for input differs from output**.

## 3. Default Behavior of `Files.newInputStream`

Calling:

```java
InputStream input = Files.newInputStream(path);
```

defaults to **opening for reading** with `StandardOpenOption.READ`. The target file must be readable; the API **does not automatically create a file if it does not exist**.

Example:

```java
try (InputStream input = Files.newInputStream(Path.of("existing.dat"))) {
    byte[] buffer = new byte[4096];
    int n;
    while ((n = input.read(buffer)) != -1) {
        // Process buffer[0..n), not all 4096 elements.
    }
}
```

This is an **illustrative snippet** that can throw `IOException`, using an existing file `existing.dat`. When a `read(buffer)` call returns a positive number smaller than the buffer length, it may be a **valid short read**, not necessarily EOF. Only `-1` indicates EOF by contract.

### Options for Input

`StandardOpenOption.READ` is the standard, clearest option to pass explicitly:

```java
try (InputStream input = Files.newInputStream(
        path, StandardOpenOption.READ)) {
    // Process bytes.
}
```

This is **illustrative code**; import `StandardOpenOption`, `Files`, `InputStream` and prepare variable `path`. For `newInputStream`, the standard contract only requires supporting `READ`, though an implementation/provider may support custom options. **Do not** use `APPEND`, `TRUNCATE_EXISTING`, or `CREATE_NEW` as if they were standard supported read options; they belong to write-open contexts.

If an invalid or unsupported option is passed, the API may throw `UnsupportedOperationException`, `IllegalArgumentException`, or another exception per contract/provider. If the file does not exist, a typical filesystem throws `NoSuchFileException`; if access is denied, you may get `AccessDeniedException` or another `IOException`.

**`InputStream` does not provide random access.** It reads sequentially from the start per stream semantics; if you need `position()`/`seek`, look at `FileChannel` or `SeekableByteChannel`, rather than trying to simulate random access with `skip()` in all cases.

## 4. Default Behavior of `Files.newOutputStream` — Where Data Is Easily Lost

Calling:

```java
OutputStream output = Files.newOutputStream(path);
```

when **no options are passed** is equivalent to:

```java
Files.newOutputStream(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE);
```

Three combined meanings:

1. **`CREATE`:** if the file does not exist yet, allow creating a new file.
2. **`TRUNCATE_EXISTING`:** if the file already exists and is opened for writing, **truncate old content to length 0** upon opening.
3. **`WRITE`:** open the file for writing bytes.

Therefore, `Files.newOutputStream(path)` **does not append**. If the file already has data, its content can be wiped **as soon as the stream opens successfully**, even before the program calls `write()` once.

Example:

```java
try (OutputStream output = Files.newOutputStream(path)) {
    output.write("Mới".getBytes(StandardCharsets.UTF_8));
}
```

This is **illustrative code**: variable `path` must exist, and you need imports for `Files`, `OutputStream`, and `StandardCharsets`. If the old file held `"Dữ liệu quan trọng"`, the default call can replace the entire content with the UTF-8 bytes of `"Mới"`.

**If you do not want to overwrite**, choose `CREATE_NEW` instead of the default. **If you want to append**, use `APPEND` and decide whether to include `CREATE`. **If you want to replace an important file while minimizing partial-file risks**, consider writing to a temporary file and moving it safely rather than mistaking `newOutputStream` for a transaction.

## 5. Key `StandardOpenOption` Values Used with Output

| Option | Behavior | Use when |
|---|---|---|
| `WRITE` | Opens for writing; does not truncate or create on its own | File already exists; want to write from the start without auto-truncating |
| `APPEND` | Writes bytes at the end of the file; concurrent write semantics depend on provider | Append-only logs or adding data to end of file |
| `TRUNCATE_EXISTING` | When opening an existing file for write, truncates to 0; check contract if combined differently | Intentionally replacing all prior content |
| `CREATE` | Creates file if absent, or opens existing file per other write options | Creating or opening for writing |
| `CREATE_NEW` | Create new only; fails if path already exists; check-and-create is atomic by contract | Must never overwrite an existing file |
| `SYNC` | Requests synchronous updates to content **and metadata** per provider semantics | Tasks requiring synchronized storage |
| `DSYNC` | Requests synchronous updates to file content per provider semantics | When durability at this option level is required |

**`APPEND` and `TRUNCATE_EXISTING` are not a valid pair to combine.** One asks to write after existing content, while the other erases existing content before writing. This combination is invalid under the `newOutputStream` contract and can throw `IllegalArgumentException`.

### Special Note on Standalone `WRITE`

One of the most dangerous mistakes is thinking:

```java
Files.newOutputStream(path, StandardOpenOption.WRITE)
```

will **replace the entire file content**. In fact, for a regular file on the default provider, the stream starts at the **beginning of the file**; if you write fewer bytes than the old content without `TRUNCATE_EXISTING`, **the old tail may remain**.

For example, if a file initially holds ASCII bytes `ABCDEF`, opening with `WRITE` alone and writing `XY` can leave **`XYCDEF`**, not `XY`. This produces subtly corrupted files that are easy to miss.

### `CREATE` vs. `CREATE_NEW`

- `CREATE` allows creating if absent **or** opening an existing file. The existing file's length/content then depends on `TRUNCATE_EXISTING`, `APPEND`, and other options.
- `CREATE_NEW` requires creating a new file and **fails when the path already exists**. By contract, the presence of a symbolic link at that path can also cause failure, even if the link target does not exist.
- `CREATE_NEW` is useful when you need "do not overwrite". Putting `if (!Files.exists(path)) ...` before `CREATE` still suffers from a **TOCTOU race** because another process can create the path concurrently.
- `CREATE_NEW` does not guarantee that the entire **content writing process** is atomic; it only handles the creation check atomically. A mid-write failure can still leave an incomplete file.

### `SYNC`/`DSYNC` Do Not Replace Storage Design

Sync options can heavily impact performance and depend on the provider/filesystem. `DSYNC` covers data, while `SYNC` also covers metadata per contract; do not enable them just to "feel safer" without knowing the requirements. And do not equate `flush()` with power-loss durability guarantees.

## 6. Quick Output-Opening Lookup Table

| Intent | Suggested call | Things to remember |
|---|---|---|
| Create if missing and **replace all** old content | `Files.newOutputStream(path)` | Default `CREATE + TRUNCATE_EXISTING + WRITE` |
| Create new file only, never overwrite | `newOutputStream(path, CREATE_NEW, WRITE)` | Fails if path already exists |
| Append to an existing file | `newOutputStream(path, APPEND)` | May fail if file does not exist |
| Append, creating file if missing | `newOutputStream(path, CREATE, APPEND)` | Does not add a newline automatically |
| Write from start while keeping unwritten tail | `newOutputStream(path, WRITE)` | Usually requires great caution |
| Open existing file to **fully replace** content | `newOutputStream(path, WRITE, TRUNCATE_EXISTING)` | Does not create new file without `CREATE` |
| Read existing file | `Files.newInputStream(path)` | Default read; does not create file |

These patterns apply to typical filesystems. Any operation can throw `IOException` due to permissions, filesystem state, files in use, hardware errors, or other reasons. If an application has strict requirements around concurrent writes, atomicity, or symlinks, consult the provider contract and design beyond choosing a single option.

## 7. Example 1 — `WRITE`, `APPEND`, Default, `CREATE_NEW`, and Missing File Errors

Create `OpenOptionsDemo.java` (Java 17+):

```java
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class OpenOptionsDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("options-");
        Path file = dir.resolve("demo.txt");
        try {
            try (OutputStream out = Files.newOutputStream(file)) {
                out.write("ABCDEF".getBytes(StandardCharsets.UTF_8));
            }
            try (OutputStream out = Files.newOutputStream(file, StandardOpenOption.WRITE)) {
                out.write("XY".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("WRITE only=" + Files.readString(file, StandardCharsets.UTF_8));

            try (OutputStream out = Files.newOutputStream(file, StandardOpenOption.APPEND)) {
                out.write("Z".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("APPEND=" + Files.readString(file, StandardCharsets.UTF_8));

            try (OutputStream out = Files.newOutputStream(file)) {
                out.write("Q".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("default output=" + Files.readString(file, StandardCharsets.UTF_8));

            try (OutputStream ignored =
                    Files.newOutputStream(file, StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE)) {
                System.out.println("unexpected new file");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("CREATE_NEW existing=FileAlreadyExistsException");
            }

            try (var ignored = Files.newInputStream(dir.resolve("missing.txt"))) {
                System.out.println("unexpected missing input");
            } catch (NoSuchFileException expected) {
                System.out.println("missing input=NoSuchFileException");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 OpenOptionsDemo.java
java OpenOptionsDemo
```

Verified output on Java 17 with the default filesystem:

```text
WRITE only=XYCDEF
APPEND=XYCDEFZ
default output=Q
CREATE_NEW existing=FileAlreadyExistsException
missing input=NoSuchFileException
```

Step-by-step explanation:

1. Creates an isolated temporary directory and `demo.txt` containing `ABCDEF`.
2. Reopens with `WRITE` only; writes `XY` at the start **without truncating**, leaving the tail `CDEF`.
3. Opens with `APPEND`; writes `Z` at the end, yielding `XYCDEFZ`.
4. Opens `newOutputStream(file)` with no options and writes `Q`. By default the file is **truncated upon open**, so only `Q` remains.
5. `CREATE_NEW` rejects opening the already-existing path and throws `FileAlreadyExistsException`, preventing accidental overwrite.
6. `newInputStream` on a missing file throws `NoSuchFileException` on the default provider, because the input stream **never creates the source**.
7. The `finally` block cleans up the temporary file and directory created by the program, touching no user data.

**Exception note:** the example demonstrates specific subtypes on a standard filesystem; other OSes/providers may reject operations with `IOException` depending on context. Do not write business logic assuming every error is `NoSuchFileException` or `FileAlreadyExistsException`.

## 8. Example 2 — Streaming Byte Copy Without Loading the Whole File into RAM

Use `newInputStream` and `newOutputStream` to transfer bytes in bounded chunks. This fits large files, such as copying binary files or processing content before saving.

Create `StreamingCopyDemo.java`:

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class StreamingCopyDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("copy-stream-");
        Path source = dir.resolve("source.txt");
        Path dest = dir.resolve("dest.txt");
        String text = "Line 1\nTiếng Việt 😊\n";
        byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
        try {
            try (OutputStream output = Files.newOutputStream(
                    source, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
                output.write(encoded);
            }

            long copied = 0;
            try (InputStream input = Files.newInputStream(source);
                 OutputStream output = Files.newOutputStream(
                         dest, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
                byte[] buffer = new byte[4];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    output.write(buffer, 0, count);
                    copied += count;
                }
            }

            System.out.println("copied all bytes=" + (copied == encoded.length));
            System.out.println("files equal=" + (Files.mismatch(source, dest) == -1));
            System.out.println("text preserved=" + text.equals(
                    Files.readString(dest, StandardCharsets.UTF_8)));
            System.out.println("bytes exceed UTF-16 units=" + (encoded.length > text.length()));
        } finally {
            Files.deleteIfExists(dest);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 StreamingCopyDemo.java
java StreamingCopyDemo
```

```text
copied all bytes=true
files equal=true
text preserved=true
bytes exceed UTF-16 units=true
```

Although the example initializes a short string as test data, the **copy loop** needs only a 4-byte buffer at runtime; when the source is a huge file, the algorithm does not need to read the entire file into a single array.

Key principles:

- `input.read(buffer)` may return fewer than `buffer.length` bytes. **Always write `output.write(buffer, 0, count)`**, never `output.write(buffer)` if the tail of the buffer holds stale bytes.
- EOF is `-1`; do not use `available() == 0` to conclude the source has ended.
- Data is copied at the **byte layer**, preserving UTF-8 byte order even if a multi-byte character is split across two reads. Do not decode each chunk and re-encode arbitrarily when exact binary copying is required.
- `Files.mismatch(source, dest)` (Java 12+) returns `-1` if no differing byte position is found between two files at comparison time. For files that may be modified concurrently, the comparison does not guarantee a consistent snapshot.
- `Files.size(path)` returns **bytes**; `text.length()` returns UTF-16 code units. Vietnamese text and emojis illustrate why these two counts differ.
- Streams must be closed. If copying fails mid-way, `dest` may **already exist with incomplete content**; use a temporary file + commit strategy when integrity is required.

The 4-byte buffer is just for easy observation and testing; in production performance-sensitive code, a buffer of several KB or larger is usually more suitable, depending on source and workload.

### When You Just Need a Whole-File Copy: `Files.copy`

`Files.copy(source, target)` can be simpler than opening two streams yourself, especially when no content transformation is needed. `Files.copy` still requires deciding overwrite, metadata, symlink, and option settings appropriately.

If you need to **filter, encrypt, compress, compute per-chunk checksums**, or frame data per a protocol, streams are valuable because the caller controls every byte chunk. Only write the loop manually when that control adds value, not out of habit to reimplement built-in copy functionality.

## 9. Input/Output Streams Are Byte-Based; Reading/Writing Text Needs a Charset

`Files.newInputStream` returns an `InputStream`; it **has no `readLine()`** and does not decode Unicode. `Files.newOutputStream` returns an `OutputStream`; `write` only writes bytes.

To read/write text using these streams, wrap them with:

- `InputStreamReader(input, charset)`: **decodes bytes into UTF-16 `char`s**.
- `OutputStreamWriter(output, charset)`: **encodes UTF-16 `char`s into bytes**.
- `BufferedReader`/`BufferedWriter`: optimizes small character operations and supports reading lines/`newLine()`.
- If you do not need low-level byte control, `Files.newBufferedReader(path, charset)` and `Files.newBufferedWriter(path, charset, options...)` are usually more concise.

**Do not write `writer.write("Tiếng Việt".getBytes())` relying on an ambiguous default charset.** Specify the charset per format/protocol, typically `StandardCharsets.UTF_8`. The default charset can vary across Java versions, runtime configurations, or specific APIs; explicitness beats hoping every environment matches your dev machine.

### Example 3 — Wrapping Byte Streams with UTF-8 Reader/Writer

Create `StreamTextBridgeDemo.java`:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class StreamTextBridgeDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("charset-bridge-");
        Path file = dir.resolve("lines.txt");
        String first = "Xin chào";
        String second = "Java 😊";
        try {
            try (BufferedWriter writer = new BufferedWriter(
                    new OutputStreamWriter(Files.newOutputStream(
                            file, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE),
                            StandardCharsets.UTF_8))) {
                writer.write(first);
                writer.write('\n');
                writer.write(second);
            }

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(Files.newInputStream(file),
                            StandardCharsets.UTF_8))) {
                System.out.println("first matches=" + first.equals(reader.readLine()));
                System.out.println("second matches=" + second.equals(reader.readLine()));
                System.out.println("EOF=" + (reader.readLine() == null));
            }
            System.out.println("byte length larger than char count="
                    + (Files.size(file) > (first + "\n" + second).length()));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 StreamTextBridgeDemo.java
java StreamTextBridgeDemo
```

```text
first matches=true
second matches=true
EOF=true
byte length larger than char count=true
```

**Explanation:**

1. `newOutputStream` opens a new file, `OutputStreamWriter` encodes characters in UTF-8, and `BufferedWriter` buffers text writes.
2. The program writes the literal `'\n'`, so the line terminator is **LF** regardless of OS. If you want platform-dependent line endings, choose `BufferedWriter.newLine()` instead of `'\n'`.
3. On exiting `try-with-resources`, closing `BufferedWriter` flushes buffered data and closes the underlying writer/stream layers. Afterward, the source is opened for reading.
4. `InputStreamReader` decodes UTF-8 properly; `BufferedReader.readLine()` reads line by line and **strips line terminators**. The third call returns `null` at EOF.
5. `Files.size(file)` measures bytes; with Vietnamese text and emojis, UTF-8 bytes outnumber the UTF-16 code units of the corresponding Java strings.

**Key distinction:** byte stream APIs do not insert newlines, switch encodings, or validate business formats automatically. Wrapping with readers/writers is the program's responsibility.

## 10. `try-with-resources`, `close()`, `flush()`, and File Lifecycle

`InputStream` and `OutputStream` implement `AutoCloseable`/`Closeable`, so use `try-with-resources` to guarantee closing:

```java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(
             target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
    in.transferTo(out);
}
```

This is an **illustrative snippet** requiring `Path source`, `Path target`, imports, and `IOException` handling. `InputStream.transferTo(OutputStream)` (Java 9+) transfers remaining bytes until EOF and returns total bytes transferred; the method **does not close** input or output automatically, so `try-with-resources` is still required.

### When Is `flush()` Needed?

`OutputStream.flush()` pushes buffered data (if the stream/wrapper buffers) down to the underlying layer. Some streams have a near no-op `flush` implementation; wrappers like `BufferedOutputStream` hold buffered data that must be pushed out.

**`flush()` does not mean data has been durably written to disk**. If the application requires durability across power loss, consider filesystem behavior, `FileChannel.force(...)`, or `SYNC`/`DSYNC` per provider contract and capabilities.

`close()` closes the stream. When a stream is a wrapper owning an underlying stream, closing the wrapper normally closes the underlying source as well; for example, `BufferedOutputStream` or `OutputStreamWriter` wrapping `newOutputStream`.

### What If a Write Error Occurs Mid-Way?

If `OutputStream.write` throws `IOException` after writing part of the data, never report "file saved successfully". The destination file may contain only the **initial portion of content**. For critical files, write to a temporary file, validate completion, and publish via a controlled move strategy.

**Do not rely on `close()` succeeding as content validation.** Success at the I/O layer does not substitute for expected byte count, checksums, file syntax, or business record verification.

## 11. Buffering: When Should You Wrap with `BufferedInputStream`/`BufferedOutputStream`?

`Files.newInputStream` and `newOutputStream` provide byte streams. When a program reads/writes small segments repeatedly, buffering can reduce calls down to the filesystem:

```java
try (InputStream in = new BufferedInputStream(Files.newInputStream(source));
     OutputStream out = new BufferedOutputStream(Files.newOutputStream(
             target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE))) {
    byte[] block = new byte[8192];
    int n;
    while ((n = in.read(block)) != -1) {
        out.write(block, 0, n);
    }
}
```

This is **illustrative code** requiring imports for `BufferedInputStream`, `BufferedOutputStream`, `InputStream`, `OutputStream`, `Files`, `StandardOpenOption` and declarations for `source`/`target`.

- Buffering changes **how I/O calls are batched**, not the meaning of the bytes.
- Write with `write(buffer, 0, n)` to avoid stale trailing bytes in the array.
- Do not assume larger buffers are always better. With many concurrent streams, buffer memory is also a resource.
- When already using `Files.newBufferedReader`/`newBufferedWriter` for text, the API provides character buffering; do not stack redundant buffer layers without measurement.
- `BufferedInputStream` supports `mark/reset` within an appropriate limit, whereas arbitrary `InputStream` instances do not generally support rewinding.

For copying whole files, consider `Files.copy`, `InputStream.transferTo`, or appropriate channel methods instead of writing complex custom buffering by default.

## 12. Choosing `newInputStream/newOutputStream` vs. Other `Files` APIs

| Requirement | Typical choice | Why |
|---|---|---|
| Read a small file into a byte array | `Files.readAllBytes(path)` | Concise, though holds all data in RAM |
| Write an existing byte array | `Files.write(path, bytes, options...)` | Direct, no manual loop |
| Read a large file in byte chunks | `Files.newInputStream(path)` | Controls memory and chunking |
| Write byte data generated incrementally | `Files.newOutputStream(path, options...)` | No need to hold entire output upfront |
| Copy a file without transformation | `Files.copy(source, target, options...)` | Direct copy API with clear options |
| Read small text | `Files.readString(path, UTF_8)` | Concise, explicit charset |
| Write small text | `Files.writeString(path, text, UTF_8, options...)` | Concise, supports open options |
| Read text line by line | `Files.newBufferedReader(path, UTF_8)` or `Files.lines` | Text/line API, not byte API |
| Write text line by line | `Files.newBufferedWriter(path, UTF_8, options...)` | Buffered character writer |
| Seek/move read/write position | `Files.newByteChannel`/`FileChannel` | Supports position/seek |
| File locking or channel-level sync | `FileChannel` and related APIs | Capabilities beyond `InputStream`/`OutputStream` |
| Temporary file operations | `Files.createTempFile`, `createTempDirectory` | Avoids predictable manual filenames |

### Do Not Use `newInputStream` for "Reading Text Records"

One byte in UTF-8 is not always one character. If a file contains Vietnamese text and you want to process **lines**, use `BufferedReader` or `Files.newBufferedReader`. If reading bytes for a binary/wire protocol, let the parser handle framing and charset.

### When You Need Simultaneous Read-Write, Random Positioning, or File Locking

`OutputStream` expresses sequential writing; `InputStream` expresses sequential reading. If business logic needs to open the same file for both reading and writing at specific offsets or requires `seek`, inspect `SeekableByteChannel`/`FileChannel` with the corresponding `StandardOpenOption` set. **Do not assume channel open options have identical semantics when used with `newInputStream`/`newOutputStream`**.

## 13. Missing Files, Permissions, and Exceptions

Distinct error conditions should be separated clearly:

- `NoSuchFileException`: an operation requiring an existing file cannot find the target.
- `FileAlreadyExistsException`: `CREATE_NEW` encounters an already-existing path.
- `AccessDeniedException`: provider reports permission denied.
- `IOException`: general exception for file, device, or filesystem errors.
- `UnsupportedOperationException` / `IllegalArgumentException`: may occur for unsupported options or invalid option combinations.
- `SecurityException`: may arise from environment/provider security checks, though modern Java has changed the role of Security Manager.

Do not catch `IOException` broadly and return an empty string or `false`, because callers lose the distinction between "genuinely empty input" and "could not read file".

Example of targeted error handling (illustrative code, requires `target`):

```java
try (OutputStream out = Files.newOutputStream(
        target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
    out.write(data);
} catch (FileAlreadyExistsException e) {
    // Inform the user: do not overwrite the existing file.
} catch (IOException e) {
    // Report or log the I/O cause and handle the failure.
}
```

This snippet requires `byte[] data` and imports. **Note:** `CREATE_NEW` guarantees not replacing an old file, but if an error happens mid-write, the newly created file may remain with partial data; cleanup policy depends on requirements.

Some filesystems or providers may not report identical subtypes, so keep a fallback `IOException` handler.

## 14. Parent Directories, File Types, and Filesystem Permissions

Opening output with `CREATE` or `CREATE_NEW` **does not automatically create missing parent directories**. If `Path.of("reports", "daily", "out.bin")` points to a non-existent `reports/daily` directory, `newOutputStream` can fail even with `CREATE`.

When directory creation is permitted, do it explicitly:

```java
Path parent = target.toAbsolutePath().getParent();
Files.createDirectories(parent);
try (OutputStream out = Files.newOutputStream(
        target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
    out.write(data);
}
```

This is **illustrative code**; declare `target`, `data`, and handle `IOException`. Not every user-supplied path should be allowed to create directories; validate root boundaries and ownership first.

`Files.isRegularFile(path)`, `Files.isDirectory(path)`, and `Files.isReadable(path)` can help UIs report preliminary status, yet they **do not guarantee** the file remains in that state until open time. Handle the actual outcome of `newInputStream`/`newOutputStream`.

In environments with symbolic links, paths can change between check and operation. In particular, `CREATE_NEW` protects the condition that the target filename does not exist at creation time, but does not solve directory traversal, parent-directory symlinks, or filesystem permission issues on its own.

## 15. `CREATE_NEW`, Avoiding TOCTOU, and Protecting Existing Data

An anti-pattern:

```java
if (!Files.exists(target)) {
    try (OutputStream out = Files.newOutputStream(target)) {
        out.write(data);
    }
}
```

This is **WRONG illustrative code if the goal is never overwriting**: between `exists` and opening, another process can create the file. Default `newOutputStream(target)` (`CREATE + TRUNCATE_EXISTING + WRITE`) will truncate that newly created data.

Better approach when you only want to create new:

```java
try (OutputStream out = Files.newOutputStream(
        target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
    out.write(data);
}
```

This is **illustrative code that correctly enforces creation**, requiring `target`, `data`, and exception handling. `CREATE_NEW` requires existence-check and creation to be atomic per contract. It is not a "full-duration file lock", does not protect against parent directory changes, and does not guarantee the entire write succeeds.

When publishing critical files for others to consume, also verify payload completeness, checksums, or business constraints before moving the file into its final location. Do not equate "file created" with "complete valid data".

## 16. Writing to a Temporary File Then Publishing: Truncate vs. Atomic Move

`Files.newOutputStream(path)` truncates the existing file directly. If the application crashes halfway through writing, the target file can lose its original content and leave only an incomplete version.

A practical strategy for critical configs or artifacts:

1. Create a temporary file in a suitable directory (`Files.createTempFile`), ideally on the same filesystem as the target.
2. Open the temporary file to write the full content; close the stream and handle write errors.
3. Verify size, checksum, or test-parse if the format requires it.
4. Use `Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE)` when needed and supported by the filesystem.
5. If `AtomicMoveNotSupportedException` is thrown, decide explicitly: **fail** if atomicity is mandatory, or perform a non-atomic fallback if the contract allows.
6. Clean up the temporary file on failure, while not accidentally deleting an already-published version.

**Warning:** `ATOMIC_MOVE` does not equal `fsync`/durability. When protecting against power-loss data loss, evaluate synchronous file/directory writes and filesystem behavior. With `ATOMIC_MOVE`, replacement behavior for an existing target can also vary by provider, so check the contract when safeguarding critical data.

You can use `Files.writeString` to a temp file with explicit encoding and then move, or use `newOutputStream` for streaming payloads. Do not default to `REPLACE_EXISTING` or fallbacks that silently break a "no overwrite" guarantee.

## 17. `APPEND` and Concurrent Writing Issues

`APPEND` positions writes at the **end of the file** per provider semantics. It is an option for logs or appending new content to an existing file. However, clarify these points:

- Does `APPEND` **create the file automatically**? To create when missing, pass `CREATE, APPEND`. With `APPEND` alone, opening a non-existent file may fail.
- `APPEND` **does not automatically insert a newline**. Two writes `"hello"` and `"world"` become `"helloworld"` unless the caller inserts a delimiter.
- Whether positioning at EOF and writing content when **multiple processes/threads** append simultaneously is atomic depends on the filesystem/provider. You cannot blindly assume a log line written across multiple `write` calls won't interleave with another writer's output.
- If record ordering must be preserved, use a single dedicated writer, locking, or a dedicated logging/queue mechanism.
- If crash durability is required, design flush/sync explicitly; `APPEND` alone does not mean durable storage.

On an existing file, passing `APPEND` appends to the end; passing `CREATE, APPEND` creates it if missing. Never combine `APPEND` with `TRUNCATE_EXISTING`.

## 18. EOF, Partial Reads, and Incomplete Output

`InputStream.read(buffer)` may return fewer bytes than the buffer size without error. A correct loop only stops at `-1` (when requesting a positive length); output must use only the `n` bytes actually read.

If a **protocol** requires a fixed-length header or an N-byte payload, reading until EOF may not be enough: the application must count bytes and verify `actual == expected`. `InputStream.readNBytes(n)` can return fewer than `n` bytes at EOF; `DataInputStream.readFully(...)` throws `EOFException` if insufficient bytes remain. These are **format-layer** constraints, not consequences of choosing `newInputStream`.

Similarly, `OutputStream.write(...)` can throw after writing a partial chunk. On failure, do not publish the output as a valid file if completeness is required. Check size and integrity after closing, depending on the scenario.

**`InputStream.available()` is NOT an EOF check or "remaining bytes in the entire file".** It mainly indicates bytes readable without blocking per stream characteristics; never use it as a stop condition or to conclude the file has been fully read.

## 19. Files Modified While Reading or Writing

A stream opened from a file does not automatically create an **immutable snapshot** of the content. If another process edits, truncates, or moves the file during the operation, what the caller observes depends on the filesystem, open mode, and timing. Short reads, altered content, or exceptions can occur; never assume a single `Files.newInputStream` call guarantees a consistent view frozen at open time.

If an exact snapshot or version is needed, consider:

- Application-level snapshot/immutable-versioning mechanisms.
- Checking length and hash against trusted expected values.
- Conventions against modifying files while being read, or file locking in appropriate environments.
- Temporary files and atomic publishing when writing new versions, keeping the atomicity/durability limits noted earlier in mind.

`Files.size(path)` reads length at one point in time; the file can change immediately afterward. Do not rely solely on `Files.size` to guarantee reading will always yield the expected byte count.

## 20. Common Mistakes and How to Avoid Them

1. **Forgetting that default output truncates.** `Files.newOutputStream(path)` can erase an existing file's content as soon as it opens. Use `CREATE_NEW` if you must never overwrite.
2. **Thinking `WRITE` alone replaces the entire file.** It usually writes from the start while leaving any old tail intact unless truncated.
3. **Using `APPEND` expecting it to create a new file.** Add `CREATE` when the contract requires creating if missing.
4. **Combining `APPEND` with `TRUNCATE_EXISTING`.** Conflicting intents; invalid combination.
5. **Using `CREATE` instead of `CREATE_NEW` to avoid overwriting.** `CREATE` does not reject an existing file.
6. **Forgetting to validate parent directories.** `CREATE` does not create missing parent directories; call `Files.createDirectories` only after verifying permission to create them.
7. **Forgetting to close streams.** File descriptors/handles can leak; use `try-with-resources`.
8. **Forgetting `flush`/`close` on buffered writers.** Buffered data may not have reached the underlying target. Respect wrapper ownership and lifecycle.
9. **Thinking `flush` means durable disk write.** Durability requires dedicated mechanisms; `SYNC`/`DSYNC` do not mean every system gives identical guarantees.
10. **Calling `out.write(buffer)` after a short read.** Stale elements in the buffer tail can be written by mistake; use `write(buffer, 0, n)`.
11. **Using `newInputStream` to read text and casting each byte to `char`.** UTF-8 has multi-byte characters; decode with `InputStreamReader` or `Files.newBufferedReader`.
12. **Relying on the default charset unknowingly.** Pick `StandardCharsets.UTF_8` or the format-specified charset.
13. **Reading huge files with `Files.readAllBytes` without measuring memory.** Chunked streaming is usually far more appropriate.
14. **Using `available() == 0` as EOF.** Unsafe; read until `-1` or use format framing/lengths.
15. **Treating stream I/O as random access.** Use `SeekableByteChannel`/`FileChannel` when you must seek.
16. **Using `try-with-resources` without handling exceptions.** Automatic closing does not turn I/O failures into success; still handle `IOException`.
17. **Assuming an output stream writes atomically.** A file may be only partially written when a failure occurs.
18. **Thinking `CREATE_NEW` solves every symlink race.** It only enforces new-creation at the target name; parent paths and environment still need protection.
19. **Not testing on real target filesystems.** Permissions, provider behavior, symlinks, and append/move atomicity can vary across platforms.
20. **Using one set of `OpenOption`s across every API.** `newInputStream`, `newOutputStream`, and `newByteChannel` have different option sets and contracts.

## 21. Pre-Implementation Checklist

| Question | If the answer is... | Choose or check |
|---|---|---|
| Is the data bytes or text? | Text | Reader/writer with explicit charset or `Files.readString/writeString` |
| Must the input file already exist? | Yes | `newInputStream`, handle missing/permission errors |
| Is output allowed to overwrite? | No | `CREATE_NEW`, handle `FileAlreadyExistsException` |
| Must output replace all prior content? | Yes | `TRUNCATE_EXISTING + WRITE`; consider temp file if critical |
| Must output append? | Yes | `APPEND`; add `CREATE` if creation is allowed |
| Is the file large or generated incrementally? | Yes | `newInputStream`/`newOutputStream` + chunking/transfer |
| Need to read/write at arbitrary offsets? | Yes | `SeekableByteChannel`/`FileChannel` |
| Multiple writers writing concurrently? | Yes | Define concurrency strategy and atomic-record design |
| Require power-loss durability? | Yes | Review `SYNC`/`DSYNC`, `force`, filesystem, and recovery strategy |
| Require publishing only a complete version? | Yes | Temp file, validate, controlled move/publish |
| Path supplied by user? | Yes | Validate root, symlinks, permissions, races, and write limits |
| Must result be exact N bytes? | Yes | Count bytes, verify EOF/integrity; do not rely solely on closing stream |

## 22. Self-Check Knowledge Quiz

**Q1.** Calling `Files.newOutputStream(path)` when the file already has data, before calling `write` at all: can the old file content already be affected?  
**Answer:** Yes. Default output uses `TRUNCATE_EXISTING` and can erase existing content immediately upon successful open.

**Q2.** File initially has `ABCDEF`, opened with `StandardOpenOption.WRITE` and two bytes `XY` are written. What is the typical result?  
**Answer:** `XYCDEF` (opens at start of file without auto-truncating); different from opening with default options.

**Q3.** To create a new file **without overwriting** an existing entry, choose `CREATE` or `CREATE_NEW`?  
**Answer:** `CREATE_NEW`, because it fails when the path already exists and the check-and-create condition is atomic per contract.

**Q4.** Does `Files.newInputStream(path)` create the file if missing?  
**Answer:** No. It is a read-open API; callers must handle missing-source errors.

**Q5.** For output, can you combine `APPEND` and `TRUNCATE_EXISTING` to "clear then append"?  
**Answer:** No. The two options conflict and are not a valid combination. To replace content, use truncate; to append, use append.

**Q6.** Does reading a Vietnamese file with `Files.newInputStream` automatically return a `String`?  
**Answer:** No. The API returns a byte stream; you must know the charset and decode when text is desired.

**Q7.** A `read(buffer)` loop returns 7 while buffer length is 4096. Should you write the whole array to output?  
**Answer:** No. Write only `write(buffer, 0, 7)`.

**Q8.** Does closing the stream guarantee the output file has the complete protocol payload and survives power loss?  
**Answer:** No. Verify byte count/format/integrity and use synchronization mechanisms suited to durability needs.

**Q9.** For large files, when is `Files.readAllBytes` less suitable than `newInputStream`?  
**Answer:** When you do not want to hold the whole file in RAM, need chunked processing, or pass data through a streaming pipeline.

**Q10.** When needing to open a file for random-position reading/writing, should `InputStream`/`OutputStream` be the primary API?  
**Answer:** Usually no. Use `SeekableByteChannel` or `FileChannel` for position/seek operations.

## Conclusion

**`Files.newInputStream(path)`** defaults to opening a file **for reading**, without creating missing files. **`Files.newOutputStream(path)`** defaults to **`CREATE + TRUNCATE_EXISTING + WRITE`**, so it can create a new file **or erase prior content upon opening**. When different behavior is needed, pass `StandardOpenOption` explicitly: `CREATE_NEW` to forbid overwriting, `APPEND` to write at the end, `CREATE` when creation is allowed, and `WRITE` with `TRUNCATE_EXISTING` when intentionally replacing content.

Choose byte streams for binary data or large streaming workloads, and pair with readers/writers and explicit charsets for text. Always use `try-with-resources`, check for read/write failures, distinguish `flush` from durability, and never equate opening a stream successfully with final file integrity.

### Java SE 17 Documentation

- [`Files` — `newInputStream` and `newOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [`OpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/OpenOption.html)
- [`InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [`OutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [`BufferedInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html) and [`BufferedOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html)
- [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html) and [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html)
- [`FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html), [`SeekableByteChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SeekableByteChannel.html)