# `Files.newBufferedReader` and `Files.newBufferedWriter` in Java

## 1. Overview: Reading and Writing Text via the `Files` API

When processing text files in Java 17+, two very useful methods in `java.nio.file.Files` are:

- **`Files.newBufferedReader(Path, Charset)`**: opens a file for **reading text**, creating a `BufferedReader` with a character buffer.
- **`Files.newBufferedWriter(Path, Charset, OpenOption...)`**: opens/creates a file for **writing text**, creating a `BufferedWriter` with a character buffer.

They bridge the world of files (bytes) and the world of Java strings and characters while using NIO.2 `Path`. When text is read from disk, byte data must be **decoded** according to a `Charset`; when writing, Java characters are **encoded** into bytes.

~~~text
READ
UTF-8 File (bytes) ─► Files.newBufferedReader(path, UTF_8)
                                 │ decode + buffer
                                 ▼
                          BufferedReader
                         ├─ readLine() → String
                         └─ read(char[]) → char chunk

WRITE
String / char[] ─► BufferedWriter
                     │ write(), newLine(), flush(), close()
                     ▼ encode + buffer
                 UTF-8 File (bytes)
                 Files.newBufferedWriter(path, UTF_8, ...)
~~~

This is **text I/O**, not the default choice for images, ZIP files, or binary payloads. If you need to preserve exact bytes without text semantics, use `Files.newInputStream`, `Files.newOutputStream`, or byte-oriented NIO APIs.

### Learning Objectives

After this lesson, you will be able to:

1. Create `BufferedReader` / `BufferedWriter` from a `Path`, specify the charset explicitly, and close resources with proper lifecycle management.
2. Read line by line with `readLine()` and distinguish EOF from blank lines.
3. Read/write `char[]` chunks using the actual character count, avoiding writing stale trailing buffer data.
4. Understand `newLine()`, `flush()`, `close()`, and the boundary between "written to buffer" and "durably persisted".
5. Choose `StandardOpenOption` to create new files, overwrite, append, or prevent overwriting existing files.
6. Recognize file, charset, and read/write errors and handle exceptions at the right stage.
7. Decide when to use `Files.readString` / `Files.writeString`, `Files.lines`, or `newBufferedReader/newBufferedWriter`.

## 2. Related Types and Components

| API/type | Role | Remember |
| --- | --- | --- |
| `Path` | Represents a path on a `FileSystem` | `Path.of(...)` does not create or open a file |
| `Files` | NIO.2 operations on files/directories | Many operations throw `IOException` |
| `Charset` | Rules for decoding/encoding between bytes and characters | Choose per file format, commonly UTF-8 |
| `StandardCharsets.UTF_8` | Built-in UTF-8 Charset | Independent of environment default charset |
| `BufferedReader` | Character-buffered Reader | `readLine()`, `read(char[])`, `lines()` |
| `BufferedWriter` | Character-buffered Writer | `write(...)`, `newLine()`, `flush()` |
| `StandardOpenOption` | Controls how a file is opened for writing | `CREATE`, `CREATE_NEW`, `APPEND`, `TRUNCATE_EXISTING`... |
| `IOException` | Signals I/O failure (checked exception) | Handle or declare `throws` |
| `try-with-resources` | Closes resources automatically | Closes even when the block throws an exception |

Program skeleton example:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
~~~

These imports suffice for simple text read/write operations. When using `StandardOpenOption`, import it from `java.nio.file` or use its qualified name.

**Note:** `Path` is a path descriptor object and does not need `close()`. The resources that must be closed are the `BufferedReader` / `BufferedWriter` opened from the file.

## 3. `Files.newBufferedReader`: Opening a Text File for Reading

### 3.1. Syntax and Meaning

~~~java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);
~~~

This is an **illustrative snippet**; variable `path` is of type `Path`, and the enclosing method must handle `IOException`. `Files.newBufferedReader` opens the file for reading and returns a `BufferedReader`. Bytes in the file are decoded using UTF-8 so the program works with Java characters.

In Java 17 there is also the form:

~~~java
BufferedReader reader = Files.newBufferedReader(path);
~~~

The form without a charset uses **UTF-8** per the `Files.newBufferedReader(Path)` contract, though passing `StandardCharsets.UTF_8` explicitly makes intent clear, especially when the input format has a specified charset.

Do not confuse this with `new FileReader(file)` from the legacy API: charset selection and path representation can differ depending on the constructor, Java version, and context. For new code, using `Path` and an explicit charset reduces environment dependencies.

### 3.2. Reader Reads Characters, Not Raw Bytes

If a file contains the UTF-8 bytes of `"Hà Nội"`, `BufferedReader` yields decoded `char` units. The byte count on disk can exceed `String.length()` due to accented characters or emojis.

`Reader.read()` returns an `int`: a non-negative `char` unit or `-1` at EOF. `Reader.read(char[])` returns the number of **character units actually read** (or `-1` at end), not the number of bytes on disk. Therefore, do not use the return value of `read(char[])` to infer the UTF-8 byte size of a file directly.

### 3.3. `try-with-resources`: Standard Usage

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process line.
    }
}
~~~

The above is an illustrative block with an existing `Path path`. `BufferedReader` implements `Closeable`, so `try-with-resources` calls `close()` at the end of the block even if an exception occurs. Do not reuse `reader` after it has been closed.

Do not rely on the garbage collector to close file resources. A `Reader` can hold OS descriptors/handles; using `try-with-resources` keeps the lifecycle explicit and prevents leaks.

## 4. `BufferedReader.readLine()`: Reading Line by Line

`readLine()` returns a `String` containing the **line content** **without line-termination characters**, or `null` when data is exhausted. Java recognizes lines terminated by `\n`, `\r`, or `\r\n` per the `BufferedReader.readLine()` contract.

This has several consequences:

- A **valid blank line** is represented as `""` (the empty string).
- **End of file** is represented as `null`.
- `readLine()` **strips line terminators**: you cannot rely solely on its return value to reconstruct the exact original line-ending style.
- A file ending with `\n` after a non-empty line **does not automatically produce an extra empty line** after the final terminator.

### 4.1. Standalone Example with CRLF, Blank Lines, and LF

Save the program as **ReadLinesDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadLinesDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("reader-lines-", ".txt");

        try {
            Files.writeString(path, "first\r\n\r\nlast\n",
                    StandardCharsets.UTF_8);

            try (BufferedReader reader =
                    Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String line;
                int lineNumber = 0;
                while ((line = reader.readLine()) != null) {
                    lineNumber++;
                    System.out.println(lineNumber + ":[" + line + "]");
                }
                System.out.println("Lines: " + lineNumber);
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 ReadLinesDemo.java
java ReadLinesDemo
~~~

Output:

~~~text
1:[first]
2:[]
3:[last]
Lines: 3
~~~

Exact explanation: the source string has `first` + CRLF, an empty line + CRLF, and `last` + LF. `readLine()` returns `"first"`, `""`, `"last"`, and then `null`. Writing `while ((line = reader.readLine()) != null)` handles the blank line properly. Conversely, `while (!line.isEmpty())` is wrong in both semantics and EOF handling.

Because the temporary filename is chosen by the system, the example only prints the read content rather than the random path, keeping output deterministic.

### 4.2. You Cannot Preserve Verbatim Line Endings with `readLine`/`newLine`

Suppose the source file contains mixed terminator styles:

~~~text
alpha\r\nbeta\ngamma\r
~~~

This notation represents `alpha` terminated by CRLF, `beta` by LF, and `gamma` by CR. If you read with `readLine()` and write back via `writer.newLine()`, the program will **replace all line endings with the current environment's convention**, instead of keeping each original style.

This makes sense if your goal is **normalizing line endings**, but is wrong if your goal is copying exact character content. When you want to preserve every `\r` and `\n`, use `read(char[])` and `write(char[], off, count)` as shown in the next section.

### 4.3. When Is `readLine` Unsuitable?

`readLine()` is generally suitable for log files, lists, single-line text configs, or data where newlines simply delimit records. It is less suitable when:

- Exact line-ending styles must be preserved.
- A record can span multiple lines under complex syntax, such as CSV with quoted fields containing newlines.
- A line may be so extremely long that memory limits are needed.
- The data is not genuinely text.

Note that `readLine()` may have to accumulate a very long line before returning a `String`. With untrusted input, consider line-length limits or a bounded-memory parser.

## 5. Reading in `char[]` Chunks: Preserving Every Character and Controlling RAM

Besides `readLine()`, `BufferedReader` inherits `Reader.read(char[])` and `read(char[], off, len)`. This is the option when you want to transfer text in chunks without depending on line boundaries.

~~~java
char[] buffer = new char[4096];
int count;

while ((count = reader.read(buffer)) != -1) {
    writer.write(buffer, 0, count);
}
~~~

This is an illustrative snippet with an already-open `BufferedReader reader` and `BufferedWriter writer`. `read` can return a positive count **smaller** than the buffer size; you must write exactly `count` valid character units. Especially on the final read, the remaining elements in the array may contain data from the previous read.

Do not use:

~~~java
while ((count = reader.read(buffer)) != -1) {
    writer.write(buffer); // Wrong: may write stale characters at the end of the array.
}
~~~

Because `write(buffer)` writes the entire array, not just the newly read segment. The correct form is `writer.write(buffer, 0, count)`. The last two integer arguments mean **offset** and **length**, not start index and end index.

### 5.1. Reading by `char` Is Not Code-Point Processing

A Java `char` is a UTF-16 code unit. Characters outside the BMP, such as many emojis, are represented by a surrogate pair (two `char`s). A `char[]` chunk boundary can fall right in the middle of that pair.

If you simply copy `char` units sequentially without modification, the Reader and Writer across one continuous sequence still preserve the content accurately. However, you must not slice individual chunks independently, reverse strings, or assume "one `char` equals one visible character" while ignoring surrogate pairs. For advanced Unicode processing, consider code-point APIs and carry state across chunks.

### 5.2. Reader/Writer Are Not Meant for Binary Byte Preservation

Reading UTF-8 with `newBufferedReader` and writing UTF-8 with `newBufferedWriter` performs decoding and encoding. For valid UTF-8 text, Unicode content can be preserved. Yet this is **not a way to copy arbitrary bytes**: input bytes may be invalid for the charset, or the output may change under transcoding if the two charsets differ.

If you need to copy images, archives, compressed files, or any binary payload, use `Files.copy` or byte APIs. Do not construct `String`s from binary data without a text encoding.

## 6. `Files.newBufferedWriter`: Opening a File for Writing Text

### 6.1. Basic Syntax

~~~java
BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8);
~~~

This is an illustrative snippet: `Path path` exists and the method must handle `IOException`. `newBufferedWriter` creates a writer that encodes text into bytes using the chosen charset and writes to the file with buffering.

Typical usage:

~~~java
try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Xin chào Java!");
    writer.newLine();
    writer.write("Dòng thứ hai");
}
~~~

This is an illustrative block. `newLine()` writes the platform's line separator, whereas `write` does not append a newline automatically. `try-with-resources` ensures the writer is closed when leaving the block, and `close()` flushes buffered data to the underlying destination per the class contract.

### 6.2. Default When No `OpenOption` Is Passed

For the overload accepting `OpenOption...`, if **no options are provided**, default write behavior is equivalent to:

- `StandardOpenOption.CREATE`: create the file if it does not exist.
- `StandardOpenOption.TRUNCATE_EXISTING`: if the file already exists, **truncate old content** before writing.
- `StandardOpenOption.WRITE`: open for writing.

This is one of the most important things to remember: **`Files.newBufferedWriter(path, UTF_8)` does NOT mean "append to the end of an existing file"**. It can erase all existing content because it opens in truncate mode. Before opening, decide your policy: create exclusively, overwrite, or append.

### 6.3. Specifying `OpenOption` Explicitly

Representative options from `StandardOpenOption`:

| Option | Meaning | Scenario |
| --- | --- | --- |
| `CREATE` | Create file if absent | Allow creating new or reusing existing file |
| `CREATE_NEW` | Create new file only, fail if it already exists | Avoid accidental overwrites |
| `TRUNCATE_EXISTING` | When opening for write, shrink existing file size to 0 | Replace entire content |
| `APPEND` | Write at the end of the file | Logs/append-only records |
| `WRITE` | Open for writing | Usually combined with specified mode |
| `SYNC` or `DSYNC` | Request synchronization per I/O/target contract | When higher durability is needed, still review filesystem limits |

When providing options, **do not assume the default trio of options is still added automatically**. Write all needed options explicitly for your goal. Some combinations are invalid, such as `APPEND` with `TRUNCATE_EXISTING`: the two requirements contradict each other.

Append example:

~~~java
try (BufferedWriter writer = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND)) {
    writer.write("bổ sung");
}
~~~

This illustrative snippet requires importing `java.nio.file.StandardOpenOption`. `CREATE` allows creating the file if absent; `APPEND` requests appending at the end instead of clearing prior content. If you need a new line, remember to call `newLine()` at the desired spot — `APPEND` **does not insert a newline automatically**.

Create-new without overwriting example:

~~~java
try (BufferedWriter writer = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    writer.write("Dữ liệu mới");
}
~~~

If the file already exists, `FileAlreadyExistsException` can be thrown. Do not use `if (!Files.exists(path))` before opening to prevent overwrites due to race conditions (*TOCTOU*); `CREATE_NEW` enforces new-file creation atomically within the open call.

## 7. Java 17 Example: Default Overwrite vs. `APPEND` Mode

Save as **WriteModesDemo.java**:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class WriteModesDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("writer-modes-", ".txt");

        try {
            try (BufferedWriter writer =
                    Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
                writer.write("old");
            }

            // No option passed: the existing file is truncated.
            try (BufferedWriter writer =
                    Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
                writer.write("new");
            }

            // Append data without erasing existing content.
            try (BufferedWriter writer = Files.newBufferedWriter(
                    path, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND)) {
                writer.write("+append");
            }

            System.out.println("Content: "
                    + Files.readString(path, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 WriteModesDemo.java
java WriteModesDemo
~~~

Output:

~~~text
Content: new+append
~~~

Explanation:

1. `Files.createTempFile` creates a real temporary file.
2. The first writer writes `old`; the second uses default mode and **replaces the content with `new`**.
3. The third writer uses `CREATE, APPEND`, appending `+append` at the end.
4. Each writer is closed before opening the next; the program does not rely on data lingering in buffers.
5. `finally` cleans up the file. In environments where creating/writing/deleting files is disallowed, operations can throw `IOException` instead of printing output; that is proper error reporting, not a Java language bug.

The source uses ASCII in the data so the output does not depend on console character rendering. You can extend the example with Vietnamese text to practice charsets.

## 8. `readLine`/`newLine` and Line-Ending Normalization Choices

One way to copy a file **line by line**:

~~~java
String line;
while ((line = reader.readLine()) != null) {
    writer.write(line);
    writer.newLine();
}
~~~

This is an illustrative snippet with open Reader/Writer. This approach **alters** line-ending formatting if:

- The source file uses CRLF while the target OS uses LF, or vice versa.
- The last source line **has no** trailing line terminator: the snippet adds one.
- The source mixes CR, LF, and CRLF.

If your goal is converting every line to the current OS's line-ending convention, this can be a valid choice. If your goal is copying character content **unchanged**, use `read(char[])` and `write(buffer, 0, count)`.

When a format requires a fixed newline style (e.g., LF), write it explicitly:

~~~java
writer.write("\n");
~~~

This is an illustrative snippet; it always writes LF instead of platform-dependent `newLine()`. Make sure that choice reflects **the application's format specification**, not a default assumption "valid for every file".

### 8.1. A Blank Line Is Not End of File

Common mistake:

~~~java
while (!(line = reader.readLine()).isEmpty()) {
    // Wrong: stops at blank lines, and may throw NPE when readLine() returns null.
}
~~~

The snippet above is a **wrong** example: `""` is a valid blank line, whereas `null` is EOF. The right way is:

~~~java
while ((line = reader.readLine()) != null) {
    // Blank lines are still processed.
}
~~~

For configuration files using blank lines to separate sections, distinguish these two states clearly.

## 9. Java 17 Example: Copying Text While Preserving Characters and Line Endings

Save as **CopyTextWithBuffersDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class CopyTextWithBuffersDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("copy-text-buffers-");
        Path source = folder.resolve("source.txt");
        Path target = folder.resolve("target.txt");

        String original = "Chào\r\nJava\n😀";

        try {
            Files.writeString(source, original, StandardCharsets.UTF_8);

            try (BufferedReader reader =
                         Files.newBufferedReader(source, StandardCharsets.UTF_8);
                 BufferedWriter writer =
                         Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
                char[] buffer = new char[3];
                int count;

                while ((count = reader.read(buffer)) != -1) {
                    writer.write(buffer, 0, count);
                }
            }

            String restored = Files.readString(
                    target, StandardCharsets.UTF_8);
            boolean sameBytes = Arrays.equals(
                    Files.readAllBytes(source), Files.readAllBytes(target));

            System.out.println("Same text: " + original.equals(restored));
            System.out.println("Same UTF-8 bytes: " + sameBytes);
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CopyTextWithBuffersDemo.java
java CopyTextWithBuffersDemo
~~~

Output when file operations succeed:

~~~text
Same text: true
Same UTF-8 bytes: true
~~~

Why this example is accurate:

- Reader and Writer use the **same UTF-8 charset** for valid text.
- `read(char[])` receives chunks of UTF-16 code units; `write(buffer, 0, count)` passes **only the valid slice** to the writer.
- The program does not strip, replace, or insert `\r`/`\n`, so the mix of CRLF and LF in the string is preserved.
- The non-BMP emoji consists of two `char`s. A 3-unit buffer can split near the surrogate pair; nevertheless, because data is not modified and the writer sees the entire sequential character stream, content is preserved.
- `Arrays.equals` checks the actual bytes on disk in the demo, not just the two decoded strings.

**Limitation:** This is an example of copying a file known to be valid UTF-8. Do not use a character-based strategy to claim preservation for arbitrary binary files. For general byte copying, `Files.copy(source, target)` or byte streams are more appropriate.

## 10. Charsets, Encoding, and Handling Malformed Data

### 10.1. Charset Must Match the Data Format

`StandardCharsets.UTF_8` is a common choice supporting Unicode. However, a file created with another charset (such as UTF-16LE or Windows-1258) must be read with its matching charset.

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_16LE)) {
    // Read UTF-16LE text.
}
~~~

This is an illustrative snippet with `Path path`. Do not arbitrarily try multiple charsets and pick output that "looks right" in systems requiring accuracy. Obtain the encoding from the format contract, reliable metadata, or a well-designed detection process.

For non-UTF-8 data mistakenly read as UTF-8, decoding can fail or produce corrupted text. Using a larger buffer does not fix a wrong charset.

### 10.2. Invalid Bytes Can Cause `MalformedInputException`

By the `Files.newBufferedReader` contract, the Reader reports `IOException` when encountering malformed/unmappable data during decoding. For an invalid UTF-8 byte sequence, you can receive `MalformedInputException` (a subclass of `CharacterCodingException`, which extends `IOException`).

For example, a leading byte `C3` in UTF-8 requires a valid continuation byte next. If byte `28` (ASCII `(`) follows instead, this byte sequence is invalid UTF-8.

### 10.3. Java 17 Demo: Detecting an Invalid UTF-8 File

Save as **InvalidUtf8Demo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class InvalidUtf8Demo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("invalid-utf8-", ".txt");

        try {
            Files.write(path, new byte[]{(byte) 0xC3, (byte) 0x28});

            try (BufferedReader reader =
                    Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                while (reader.read() != -1) {
                    // Read to force the decoding process.
                }
                System.out.println("Decoded successfully");
            } catch (MalformedInputException e) {
                System.out.println("Invalid UTF-8: true");
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 InvalidUtf8Demo.java
java InvalidUtf8Demo
~~~

Output for the data generated in the program:

~~~text
Invalid UTF-8: true
~~~

Key takeaway: **successfully opening a Reader does not mean the entire file has been decoded successfully**. Character errors can arise during `read` calls. Therefore, report "read succeeded" only after processing the entire content and completing required resource closing.

If an application needs a policy that replaces invalid characters with the replacement character (**U+FFFD**) instead of failing, you can configure a `CharsetDecoder` with `CodingErrorAction.REPLACE` and wrap it in an `InputStreamReader`; do not assume `Files.newBufferedReader` has a flag to toggle this policy.

### 10.4. Write Errors: Unencodable Unicode Characters

When an output charset cannot represent a character, encoding can fail if the encoder uses error-reporting policy. For example, if US-ASCII is selected while data contains Vietnamese characters, do not assume the output bytes preserve the content. Choose a charset capable of representing the data (UTF-8 usually fits) or explicitly define a replacement/error policy.

Another issue is unpaired surrogates: if data contains only half of a surrogate pair (not a valid UTF-16 sequence), the encoder can report malformed input. This matters when transforming `char[]` chunks or constructing strings manually.

## 11. `newLine()`, `flush()`, and `close()`: Three Distinct Actions

`BufferedWriter` may keep characters in an in-memory buffer before sending them to the underlying writer. Distinguish three actions:

- **`newLine()`**: *writes line-separator characters* according to the system line separator convention. It does not guarantee data has been sent to the file.
- **`flush()`**: requests pushing buffered content down to the underlying writer. `flush()` **does not guarantee** data has been durably synced to physical disk.
- **`close()`**: ends usage of the writer; for `BufferedWriter`, it flushes remaining buffered data and closes underlying resources. It can throw `IOException`.

Example:

~~~java
try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("A");
    writer.newLine();
    writer.write("B");
    writer.flush();
}
~~~

This is an illustrative snippet. `flush()` is useful when another component needs to read content pushed to the underlying destination **before** the writer closes, but it does not replace `close()`. In programs that simply write and finish, `try-with-resources` handles calling `close()`, usually without needing manual `flush()` on every write.

### 11.1. Data Durability Is More Than `flush`

Do not conclude that:

~~~java
writer.flush();
System.out.println("Permanently saved!");
~~~

proves the file is safe across power loss. OS caches, filesystems, and hardware all play a role. When stronger durability is required, consider synchronization with `FileChannel.force(...)`, appropriate open options, and transactional/safe file-replacement protocols. Even then, understand your environment's durability guarantees rather than claiming absolute safety.

### 11.2. Do Not Call `write` After `close`

Once closed, a `BufferedWriter` must not be used further. Calling `write` or `flush` on a closed writer normally throws `IOException`. Unlike some in-memory streams whose `close()` is a no-op, a file-backed writer must be treated as a resource with a real lifecycle.

## 12. Errors on Open, Read, Write, and Close

The two `Files` methods can report errors at multiple stages:

| Stage | Example causes | How to handle |
| --- | --- | --- |
| Open for read | Missing file or missing read permission | `NoSuchFileException` / `AccessDeniedException` or appropriate `IOException` |
| Open for write | Missing parent directory, missing permission, `CREATE_NEW` on existing file | Verify mode, permissions, directories; catch API-appropriate exceptions |
| Read | Device error, invalid data for charset | Do not turn errors into valid EOF; report failure |
| Write | Out of space, device error, unencodable characters | Do not blindly assume retrying the whole write avoids duplicates |
| Flush | Error pushing buffered data downstream | Handle just like a write error, do not ignore |
| Close | Error flushing remaining buffer/closing handle | Preserve error and avoid treating outcome as guaranteed success |

A modern API does not guarantee a fault-free environment. `Path`, `Files`, `BufferedReader`, and `BufferedWriter` still rely on the underlying filesystem when operating on real files.

### 12.1. Catch in the Right Place

A read/write method can declare `throws IOException` and let a higher layer decide whether to notify the user, retry, or reject the request. Example:

~~~java
static void appendLine(Path path, String line) throws IOException {
    try (BufferedWriter writer = Files.newBufferedWriter(
            path, StandardCharsets.UTF_8,
            StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
        writer.write(line);
        writer.newLine();
    }
}
~~~

This is a **syntactically standalone method snippet that must be placed inside a class** with imports for `BufferedWriter`, `IOException`, `Path`, `Files`, `StandardCharsets`, and `StandardOpenOption`. It actively closes the writer it created.

If an append fails partway through, do not automatically retry writing the entire record without knowing how many bytes/characters were written. Some systems require transactions, locking, or idempotency protocols to avoid duplicate/partial records.

### 12.2. `try-with-resources` Preserves Suppressed Exceptions

If an error occurs in the `try` body and another error occurs during `close()`, `try-with-resources` preserves the body error as the primary exception while attaching the close error via `Throwable.getSuppressed()`. This prevents losing diagnostic details.

Do not write `catch(IOException e) { return ""; }` for a mandatory read operation: an empty string can be valid file content, whereas an I/O error is a different state. Propagate the error, return an error-bearing result type, or handle it explicitly per business contract.

## 13. Differences Between `Files.readString`, `readAllLines`, `lines`, and `newBufferedReader`

When reading text, you do not always need to open a `BufferedReader` yourself. Choose the API based on data volume and processing style.

| API | Result | Characteristics |
| --- | --- | --- |
| `Files.readString(path, charset)` | One `String` containing the whole file | Convenient for small files; holds all content in RAM |
| `Files.readAllLines(path, charset)` | `List<String>` of lines | Convenient for small/medium files; holds all lines in RAM |
| `Files.lines(path, charset)` | `Stream<String>` reading lines lazily | Must **close the Stream** because it holds an I/O resource |
| `Files.newBufferedReader(path, charset)` | `BufferedReader` | Flexible: `readLine`, `read(char[])`, `mark`/`reset` if appropriate |

`Files.readAllLines` returns the list of lines read and strips line terminators similarly to line-reading rules. `Files.lines` allows processing lines as a Stream, yet it is still a resource that must be closed:

~~~java
try (java.util.stream.Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(s -> !s.isBlank()).forEach(System.out::println);
}
~~~

This is an illustrative snippet with `Path path`; closing the Stream closes the resource opened by `Files.lines`.

Conversely, `BufferedReader.lines()` returns a Stream pulling lines from an **existing `BufferedReader`**. Closing that Stream does not replace the responsibility to close the outer Reader. Clear management:

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines().forEach(System.out::println);
}
~~~

This is an illustrative snippet: the Reader is still closed via `try-with-resources`. Do not mix manual `reader.readLine()` calls and the `reader.lines()` Stream concurrently on the same Reader; it is a stateful sequential source.

## 14. Comparing `Files.writeString` and `newBufferedWriter`

`Files.writeString(path, text, charset, options...)` is concise when you already have the entire `String`. It opens, writes, and closes the resource under the call's contract. Example:

~~~java
Files.writeString(path, "Xin chào", StandardCharsets.UTF_8);
~~~

This is an illustrative snippet with an existing `Path path`. `newBufferedWriter` is more useful when you must write multiple times, process lines incrementally, stream long input, or build content gradually without holding everything in a single `String`.

There is no rule that "using `BufferedWriter` is always faster": performance depends on write count, data size, buffer layers, and the filesystem. For a tiny file when a `String` is already at hand, `Files.writeString` can be clearer. For repeated writes across many fragments, `BufferedWriter` avoids reopening the file for each fragment and gives you a writer handle for the entire operation.

### 14.1. Do Not Open a New Writer per Line in Default Mode

Wrong approach:

~~~java
for (String line : lines) {
    try (BufferedWriter writer =
            Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
        writer.write(line);
    }
}
~~~

This is a logically wrong illustrative snippet; `lines` and `path` exist. Because each open in default mode **truncates the file**, the result usually retains only the last line. Additionally, opening/closing per line adds overhead.

Proper approach when writing multiple consecutive lines:

~~~java
try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    for (String line : lines) {
        writer.write(line);
        writer.newLine();
    }
}
~~~

This is an illustrative snippet with an `Iterable<String> lines`. The writer is opened once and closed at the end; the file is intentionally replaced as a whole. If you want to append to an existing file, add the appropriate open options.

## 15. Opening Multiple Resources and Close Order

An operation transferring data from a source file to a target file can open both a Reader and a Writer:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(source, StandardCharsets.UTF_8);
     BufferedWriter writer =
             Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
    char[] buffer = new char[8192];
    int count;
    while ((count = reader.read(buffer)) != -1) {
        writer.write(buffer, 0, count);
    }
}
~~~

This is an illustrative snippet with `Path source` and `Path target`. Resources are closed in **reverse order of declaration**: writer first, reader second.

Do not set `source` and `target` to the **same path** in this overwrite pattern: when the writer opens in default mode, the target file (which is also the source) can be truncated, losing the data you are about to read. To transform a file in place, consider writing to a **separate temporary file**, closing thoroughly, verifying the result, and then moving the temporary file over the target using an appropriate policy.

### 15.1. If Opening One Side Fails

`try-with-resources` also helps when opening multiple resources: if the Reader opens successfully but opening the Writer throws an exception, the already-open Reader is closed during exit. This prevents handle leaks compared to manual variable assignment and manual closing.

### 15.2. Do Not Close Resources Owned by Someone Else

If a method **receives** a `BufferedReader` or `BufferedWriter` from its caller, it generally should not close it unless the contract transfers ownership. Conversely, when a method calls `Files.newBufferedReader` / `newBufferedWriter` itself to open a file for its own task, that method is responsible for closing the resource when done.

## 16. Choosing Buffer Sizes and Performance Notes

`BufferedReader` / `BufferedWriter` have internal character buffers. When using `Files.newBufferedReader` / `newBufferedWriter`, the buffer size is chosen by the API implementation; do not depend on a specific number to predict behavior.

If an application needs its own `char[]` buffer for chunked copying, `new char[4096]` or `new char[8192]` are reasonable starting sizes for testing. No single number is optimal for every workload. Smaller sizes still yield exact results as long as you use `count`; larger sizes may reduce call count at the expense of slightly more memory.

**Issues more important than a few kilobytes of buffer:**

- Do not reopen/reclose the file for every token/line when continuous processing is possible.
- Do not accumulate a massive file into a single `String` when sequential scanning suffices.
- Do not call `readLine` on potentially unbounded lines without a data limit policy.
- Do not flush on every single character unless corresponding display/synchronization requirements exist.
- Distinguish error-handling, charset, and data correctness from speed optimization.

## 17. Common Mistakes with `newBufferedReader`/`newBufferedWriter`

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Choosing the wrong charset | Corrupted accents or decoding errors | Specify charset matching the format |
| Assuming Writer appends by default | Old content gets erased | Use `CREATE, APPEND` when appending |
| Opening a new Writer per line without `APPEND` | Only the last line remains | Open one Writer for the whole task |
| Checking `readLine() == ""` for EOF | Skips blank lines or throws NPE on null | Only `null` means EOF |
| Using `readLine()+newLine()` for verbatim copy | Normalizes/loses original line-ending styles | Use `read(char[])` + `write(...,count)` |
| Writing the entire buffer after a short read | Inserts stale characters from end of array | Use `writer.write(buffer,0,count)` |
| Using Reader/Writer for binary data | Bytes may be transcoded and corrupted | Use byte streams/NIO |
| Not closing Writer | Buffered data may not reach destination; handle leak | Use `try-with-resources` |
| Thinking `flush()` equals `fsync` | Misjudges durability | Distinguish flush/close/force |
| Reading huge files with `readString` | Can run out of heap | Process line by line or chunk by chunk |
| Reading and writing the same path with default writer | Truncates the source being read | Use a temporary file or safe in-place design |
| Ignoring `IOException` from `close` | Can miss final write failure signals | Propagate or handle errors properly |
| Assuming a path exists simply after `Path.of` | Opening for read fails | Handle exceptions during actual open |
| Concluding `readLine` preserves CRLF | Loses line-ending info | Process characters directly if needed |
| Using default charsets inconsistently across layers | Read/written files differ in content | Choose an explicit charset end to end |

## 18. Self-Check Questions

**Q1.** `Files.newBufferedWriter(path, UTF_8)` opens an existing file that has content. Is the old content preserved?

**Answer:** By default, no. When no open option is passed, the writer uses behavior equivalent to `CREATE`, `TRUNCATE_EXISTING`, `WRITE`: the existing file is truncated. To append, specify `CREATE` and `APPEND` appropriately.

**Q2.** If `readLine()` returns `""`, has EOF been reached?

**Answer:** No. That is a blank line. `null` is the indicator for end of data.

**Q3.** Does reading with `readLine` and writing with `newLine` preserve the source file's CRLF on every OS?

**Answer:** No. `readLine` strips line terminators, and `newLine` writes the terminator appropriate for the target environment. To preserve the exact sequence of newline characters, use `read(char[])`/`write(char[],0,count)`.

**Q4.** When `reader.read(buffer)` returns 5 and the array length is 1024, how many characters should be written?

**Answer:** 5, using `writer.write(buffer, 0, 5)`; do not write the entire array.

**Q5.** Does `flush()` guarantee bytes are durably saved on the physical storage device?

**Answer:** No. Flush pushes data past the buffer layer managed by the writer; durability requirements differ from flushing buffers.

**Q6.** Why shouldn't you open `newBufferedWriter(sourcePath, UTF_8)` at the same time to "edit in place" a file currently being read by a Reader?

**Answer:** By default the Writer can truncate the source file itself; original data is lost before reading finishes. Use a temporary file and a safe replacement workflow instead.

**Q7.** Do `Files.lines` and `BufferedReader.lines` share the same resource-closing responsibility?

**Answer:** With `Files.lines`, close the Stream to close the resource opened by the method. With `BufferedReader.lines`, you must still manage/close the underlying `BufferedReader`; do not assume closing the Stream automatically closes the Reader.

**Q8.** Why can a UTF-8 Reader/Writer throw `IOException` after opening succeeds?

**Answer:** Errors can occur while writing to the filesystem, during flush/close, or when transcoding characters invalid for the charset; opening successfully does not guarantee subsequent operations will succeed.

### Practice Exercises

1. **Reading blank lines:** modify `ReadLinesDemo` with source `"A\n\nB"`; predict the line count and each line's value. Verify that blank lines are not conflated with EOF.
2. **Append:** modify `WriteModesDemo` to append `"+1"` and `"+2"` using a single `BufferedWriter`. Compare the result with opening a new writer each time.
3. **Safe overwrite:** try `CREATE_NEW` when the file already exists and catch `FileAlreadyExistsException`. Do not delete the file just to make this test pass.
4. **Charset:** write Vietnamese text in UTF-8 and read it back. Try using a different charset in a test environment to observe why knowing the source encoding matters; do not ship mis-encoded output to production.
5. **Preserving line endings:** use text containing CRLF, LF, and CR, copy it using both strategies (line-by-line and character-chunk), and compare using `Arrays.equals(Files.readAllBytes(a), Files.readAllBytes(b))` to see the difference.
6. **Large files:** design a method taking `Path source` and `Path target` that copies text using a `char[]` buffer without holding the entire file in RAM, and ensures both Reader and Writer are closed when exceptions occur.

## 19. Summary

- **`Files.newBufferedReader(path, charset)`** opens a file for reading decoded text; you can use `readLine()` or read character chunks.
- **`Files.newBufferedWriter(path, charset, options...)`** creates a buffered Writer for writing text; **default mode can erase existing file content**.
- **`readLine()` strips line terminators**, returns `null` at EOF, and returns `""` for blank lines. `newLine()` writes the platform line separator.
- **`read(char[])` and `write(buffer,0,count)`** fit when you need to preserve character sequences verbatim and process large files incrementally.
- **UTF-8 is the charset to specify explicitly** when the file format uses UTF-8; wrong charsets or malformed data can cause read/write errors.
- **`try-with-resources` manages closing**, helping avoid file leaks and preserving close errors; `flush` is not a promise of durable persistence on physical hardware.
- **Choose APIs by goal**: `readString/writeString` for small data, `Files.lines` for line streams, and `newBufferedReader/newBufferedWriter` when explicit read/write control is needed.

### Java SE 17 Documentation

- [Files.newBufferedReader(Path, Charset)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset))
- [Files.newBufferedWriter(Path, Charset, OpenOption...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedWriter(java.nio.file.Path,java.nio.charset.Charset,java.nio.file.OpenOption...))
- [BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [BufferedWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Files.readString, writeString, and lines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)