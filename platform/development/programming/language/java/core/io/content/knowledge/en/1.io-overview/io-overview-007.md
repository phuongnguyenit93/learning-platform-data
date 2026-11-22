# Prerequisites and Recommended Learning Sequence for Java I/O

> Scope: Java Core I/O. This article identifies the prerequisite knowledge, why it matters, and the learning path from simple file operations to safe data stream design. This is a learning roadmap; advanced APIs are introduced at the right points, with no need to master them before starting.

## 1. Goals of Learning I/O

**Input/Output (I/O)** is when a program receives data from or sends data to a source/destination outside active processing memory: keyboard, file, buffer, network connection, or another stream. In Java, it is necessary to distinguish **byte** data from **character** data, **read/write** operations from **resource** lifecycles, and how to handle small data versus large data.

After this roadmap, learners should be able to:

- Choose the right API to read/write UTF-8 text files and binary data.
- Explain the differences between `InputStream`/`OutputStream`, `Reader`/`Writer`, `Path`/`Files`, and `Channel`/`Buffer`.
- Use `try-with-resources` to close resources; handle `IOException` intentionally.
- Process large files in chunks instead of loading the entire file into RAM by default.
- Recognize risks related to paths, encoding, untrusted data, partial writes, and concurrent multi-thread access.
- Independently verify read/write results using runnable examples and tests for error cases.

## 2. Prerequisites: What Should You Know First?

| Foundation | Required level | Direct connection to I/O |
| --- | --- | --- |
| Basic Java syntax | Variable declarations, operators, `if`, `for`, `while`, method calls | Repeatedly reading line by line / byte block by block, stopping when data ends |
| Data types and arrays | `byte`, `char`, `int`, `String`, `byte[]`, array indexing | Byte buffers; distinguishing Unicode characters from encoded bytes |
| Classes and objects | `new`, constructors, interfaces, inheritance, method calls | Stream, reader, writer abstractions and wrapper classes like `BufferedReader` |
| Exceptions | `try`, `catch`, `finally`, `throws`, checked exceptions | Reading/writing can fail due to missing files, permission loss, device issues, or connection failure |
| Resources and variable scope | `AutoCloseable` at usage level, `try-with-resources` | Closing file handles/streams even when errors occur |
| Basic Collections | `List`, iterating over elements; awareness of memory limits | Storing small lines when needed, considering sequential processing for large data |
| JDK tools | Running `java -version`, `javac`, `java`, checking working directory | Compiling, running, and observing real files on the operating system |

**Should reinforce first if not yet comfortable:** `while` loops with conditions returning `null` or `-1`; the meaning of `throws IOException`; how to match the source file name with `public class`; and distinguishing immutable `String` from mutable byte arrays.

**Not required at the starting point:** multithreading, sockets, serialization, selectors, memory-mapped files, or web frameworks. They become useful in later stages once basic reading/writing is solid.

## 3. Core Concepts to Understand Immediately

### 3.1 Bytes, Characters, and Charsets

- A **byte** is a unit of binary data (8 bits); images, compressed files, and protocol data must be treated as bytes, not automatically decoded into `String`.
- **Characters** are decoded text data. `String` holds a sequence of Java characters (UTF-16 code units); a Unicode character outside the BMP may take two `char` values.
- A **charset** determines how text is converted into bytes and vice versa. You should explicitly choose `StandardCharsets.UTF_8` when the file format or protocol requires UTF-8; do not assume every machine has the same default charset.
- Line break characters may use `\n`, `\r\n`, or `\r`. `BufferedReader.readLine()` strips line-ending characters; if bytes or line endings must be preserved exactly, do not use that reading method to reconstruct content verbatim.

Mental exercise: the texts `"é"` and `"😀"` have `String.length()` values of 1 and 2 UTF-16 code units respectively, yet when encoded in UTF-8 they have 2 and 4 bytes respectively. Therefore, **character count, `char` count, and byte count are not equivalent**.

### 3.2 Data Sources/Destinations and API Families

| Problem to solve | API group to recognize |
| --- | --- |
| Reading/writing bytes | `InputStream`, `OutputStream` (`java.io`) |
| Reading/writing characters | `Reader`, `Writer`; `BufferedReader`, `BufferedWriter` |
| File, directory, and path operations | `Path`, `Files` (`java.nio.file`) |
| I/O with buffers, positions, and channels | `ByteBuffer`, `FileChannel` (`java.nio`) |
| Sockets and multiplexing at an advanced level | `SocketChannel`, `Selector` when the problem requires them |

`java.io.InputStream` is a byte stream; it is **not** `java.util.stream.Stream<T>` used for functional-style data operations. `Path` describes a path; `Files` provides operations on the file system. A `Path` by itself does not open or close a file.

### 3.3 Resource Lifecycle and Errors

A reading path typically has three steps: **open source → read and process → close resource**. Use `try-with-resources` for objects implementing `AutoCloseable`: Java calls `close()` upon exiting the block, even if reading throws an exception. Successful closing still does not guarantee every business error has been handled; for example, writing an important target file needs an additional strategy such as writing to a temporary file and replacing according to file system requirements.

`IOException` is a common checked exception; API callers need to catch it or declare `throws`. You must distinguish a read failure error from the **end-of-data** signal: `InputStream.read()` returns `-1` at EOF, whereas `BufferedReader.readLine()` returns `null` at EOF. Do not use `available()` as a condition for reading a stream completely.

## 4. Recommended Learning Sequence

Follow the order below; each stage has a competency to achieve before moving to the next stage. There is no need to learn every class at once.

### Stage 0 — Environment Setup and Java Fundamentals

**Learn:** check JDK 17+, compile/run a `.java` file, understand working directory, relative and absolute paths; review exceptions, loops, `String`, `byte[]`, and `try-with-resources`.

**Practice:** a program that accepts a string and prints it to the console; intentionally pass a non-existent filename in the next test and observe the `IOException` details.

**Achieved when:** you can explain why relative paths depend on the working directory and why `try-with-resources` differs from simply calling `close()` at the end of a normal execution flow.

### Stage 1 — Files and Paths Before Learning Many Stream Types

**Learn:** `Path.of(...)`, `resolve(...)`, `normalize()`, `Files.exists(...)`, `Files.isRegularFile(...)`, `Files.createDirectories(...)`, `Files.readString(...)`, `Files.writeString(...)`, `Files.copy(...)`, `Files.move(...)`, `Files.deleteIfExists(...)`.

**Practice:** create a dedicated directory for the exercise, write a UTF-8 file, read it back and compare contents, copy to another name, then clean up the file. Use `resolve` to join paths instead of manually inserting `/` or `\`.

**Achieved when:** you can choose the API for reading/writing **small** text and know that a prior `Files.exists` check does not guarantee the next operation will succeed: the file may change between the two operations.

### Stage 2 — Byte Streams and Character Streams

**Learn:** `InputStream`/`OutputStream`, `Reader`/`Writer`, `InputStreamReader`/`OutputStreamWriter`, `BufferedInputStream`/`BufferedOutputStream`, `BufferedReader`/`BufferedWriter`.

**Practice:** copy an image in byte chunks using `InputStream.transferTo(OutputStream)` or a `read(byte[])`/`write(...)` loop; read text line by line with `BufferedReader`; compare with reading the whole string via `Files.readString`.

**Achieved when:** you know how to choose bytes for binary data and characters for text, specify the charset explicitly at the byte ↔ text conversion boundary, and understand that buffering reduces the number of I/O calls in many situations.

### Stage 3 — Memory Management, Errors, and Reliability

**Learn:** streaming large data; `try-with-resources`; flush and close; exceptions when opening/reading/writing; missing files, access permissions, invalid paths, incomplete data.

**Practice:** process a large log file line by line without calling `Files.readAllLines` or `Files.readAllBytes`; simulate an error by pointing to a non-existent file; verify that resources are closed.

**Achieved when:** you can explain that `flush()` pushes data from the buffer layer down to the underlying layer but does not by itself guarantee data has been durably persisted on the device; `close()` releases resources and can throw errors.

### Stage 4 — File Trees and Metadata

**Learn:** `Files.list(...)`, `Files.walk(...)`, `Files.walkFileTree(...)`, `BasicFileAttributes`, symbolic links; distinguish filtering file names from reading file contents.

**Practice:** list files by suffix and calculate total size in an exercise directory; use `try-with-resources` with the stream returned by `Files.list`/`Files.walk`.

**Achieved when:** you know how to limit scan scope, handle permission errors, and avoid accidentally following symlinks outside the intended directory.

### Stage 5 — NIO Buffers and Channels

**Learn:** `ByteBuffer` with `position`, `limit`, `capacity`, `flip()`, `clear()`; `FileChannel` for positional reading/writing; distinguish common blocking I/O from non-blocking I/O in cases where the channel supports it.

**Practice:** read a binary file using `FileChannel` and `ByteBuffer`; write or read a specific region of a file; compare with streams in stage 2.

**Achieved when:** you can explain why `flip()` must be called before reading data just written into a buffer, and do not assume every `Channel` is non-blocking.

### Stage 6 — Applying by Data Type and Complexity

**Learn as needed:** `DataInputStream`/`DataOutputStream` for primitives in a defined format; `ObjectInputStream`/`ObjectOutputStream` at a risk-awareness level, not treating Java serialization as a default exchange format; socket I/O, selectors, and asynchronous channels only when the problem requires them.

**Practice:** write a small binary record format with documented field order, version, and charset; test reading it back. For inter-system data exchange, consider a format with an explicit schema/constraints instead of Java deserialization from untrusted sources.

**Achieved when:** you can give technical reasons for the chosen API based on data type, size, performance needs, reliability, and maintainability.

## 5. Complete Java 17 Example: Safe UTF-8 Writing and Reading

The example below illustrates **stages 1–3**: creating a temporary file, writing UTF-8, reading line by line, closing the reader automatically, and deleting the file in `finally`. The temporary file name is generated by the system, so the program does not depend on the working directory.

Save the file as **`IoRoadmapDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class IoRoadmapDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-roadmap-", ".txt");

        try {
            Files.writeString(file, "Xin chào\nJava I/O\n", StandardCharsets.UTF_8);

            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                int lineNumber = 0;
                while ((line = reader.readLine()) != null) {
                    System.out.println(++lineNumber + ": " + line);
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run with JDK 17+ (save the source code in UTF-8):

```bash
javac -encoding UTF-8 IoRoadmapDemo.java
java IoRoadmapDemo
```

Exact stdout output on a successful run:

```text
1: Xin chào
2: Java I/O
```

**Why the program is correct:** `Files.writeString` converts text into UTF-8 bytes; `Files.newBufferedReader` converts UTF-8 bytes back into character lines; `readLine()` returns `null` after the last line; `try-with-resources` closes the reader; `finally` attempts to delete the temporary file even if reading fails. `main throws IOException` allows I/O errors to propagate so the runner sees them instead of swallowing the error. In real-world applications, choose an appropriate logging/notification/recovery policy.

**Limitations of the example:** this is a small file and a single-threaded application; it does not yet demonstrate binary copying, processing multi-GB data, concurrent writers, or writing critical files using atomic replacement.

## 6. Choosing Tools by Situation

| Situation | Starting choice | Important warning |
| --- | --- | --- |
| Read/write small text files | `Files.readString` / `Files.writeString` with charset | Large content can consume a lot of RAM |
| Read text line by line | `Files.newBufferedReader` or `Files.lines` | Close the reader/stream; remember line endings are not preserved |
| Copy regular files | `Files.copy` | Choose existing target file policy, handle errors; do not assume the operation is always atomic |
| Copy bytes between two sources/destinations | `InputStream` + `OutputStream`, `transferTo` | Close both resources; do not convert binary to text |
| Traverse many files in a directory | `Files.walk` or `walkFileTree` | Limit depth/permissions/symlinks; close the stream |
| Random access to byte regions | `FileChannel` and `ByteBuffer` | Understand `position`/`limit` and that `read`/`write` results may be partial |
| Many simultaneous network connections | NIO selector / asynchronous API when measurements prove it is needed | More states and errors; do not use just because of the name “NIO” |

## 7. Practice Order and Self-Check Criteria

1. **Text exercise:** write a UTF-8 `notes.txt` file containing Vietnamese characters and emoji; read it back; verify for yourself that bytes and characters have different lengths.
2. **Binary exercise:** copy an image/ZIP file using byte streams; compare the size and byte contents between the two files, without using `Reader`.
3. **Large file exercise:** count lines using `BufferedReader` or `Files.lines` with resources closed; explain why not to use `readAllLines` for large files.
4. **Error exercise:** test an invalid path and a path without access permission (if the environment allows); distinguish user-facing messages from diagnostic logs; ensure exceptions are not ignored.
5. **Organization exercise:** traverse subdirectories, list names/sizes, handle entries deleted during traversal.
6. **NIO exercise:** read a file using `FileChannel` and a buffer, note the buffer state before and after `flip()`; compare with the stream APIs already learned.

You can use the following questions as checkpoints:

- Why should you not open an image with `BufferedReader` to copy it?
- How does `read()` returning `-1` differ from an exception?
- Under what condition does `readLine()` return `null`? Does it preserve `\r\n`?
- When is `Files.readString` convenient, and when should you read line by line / chunk by chunk?
- What does `try-with-resources` close, and does `Path` need to be closed?
- Why can calling `Files.exists(path)` before writing still result in an error?
- When using `Files.lines` or `Files.walk`, whose responsibility is it to close the resource?
- In a ByteBuffer write-then-read example, what state does `flip()` change?

If you are still confused about the first two questions regarding **bytes/text** and **EOF/exceptions**, reinforce stages 1–2 before learning channels or selectors.

## 8. Common Mistakes to Avoid Throughout the Roadmap

- **Using an implicit charset:** may produce different results across environments or corrupt data; explicitly specify UTF-8 at conversion boundaries when the format requires it.
- **Using `readAllBytes`/`readAllLines` for every file:** large data can cause heap pressure; prefer reading by chunks/lines if keeping everything is unnecessary.
- **Forgetting to close resources:** causes file descriptor leaks or holds resource locks; use `try-with-resources` matching the actual lifecycle.
- **Not checking the actual number of bytes read:** `read(byte[])` may read fewer bytes than the array length, even before EOF; only process the number of bytes the method actually returns.
- **Assuming a single write always completes all bytes with an NIO channel:** check the return value of `write` and loop if the protocol/operation requires writing completely.
- **Swallowing `IOException`:** loses the root cause and makes output appear successful; report errors at the right layer, include contextual information, and preserve the cause when wrapping exceptions.
- **Passing user-provided paths into sensitive operations without validation:** normalize, determine the allowed root directory, consider symlinks, and enforce access control; `normalize()` only handles syntax and does not prevent path traversal by itself.
- **Treating `flush` or `close` as synonymous with absolute durable writes:** high durability requirements need consideration of filesystem characteristics, data synchronization, and replacement/recovery strategies.
- **Learning selectors/async too early:** obscures basic errors with charsets, EOF, and cleanup; only advance when foundational exercises are solid.

## 9. When Are You Ready for the Next I/O Topic?

You can move from the overview to in-depth articles once you can independently write a Java 17 program that reads/writes UTF-8, copies binary files without altering data, handles EOF accurately, and closes resources even when exceptions occur. From that foundation, learning `Path`/`Files` → byte/character streams and buffering → handling large data/errors → traversing file trees → `ByteBuffer`/`Channel` → networking/serialization/async according to problem requirements will tie each new API to a concrete problem.