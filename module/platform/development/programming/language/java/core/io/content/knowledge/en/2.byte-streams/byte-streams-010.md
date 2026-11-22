# FileInputStream, FileOutputStream, and Append Mode in Java

`FileInputStream` and `FileOutputStream` are two byte streams used to work directly with files in the `java.io` package. One reads existing bytes from disk, while the other writes bytes to a file. When writing, choosing whether to **write from the beginning of the file** or **write by appending to the end of the file (append)** is a very important decision: opening `FileOutputStream` without append enabled on an existing file can cause all existing data to be lost the moment the stream is opened.

This article focuses on how to open, read, write, append, close, and handle errors for both classes; the examples apply to Java 17+.

## 1. How Do Byte Streams Work with Files?

- **`FileInputStream`** extends `InputStream`: opens a file to retrieve bytes in sequence, with the read position advancing across calls to `read(...)`. Reading at the end of the file returns `-1`.
- **`FileOutputStream`** extends `OutputStream`: opens a file to write bytes using `write(...)`; it does not provide read operations. The open mode determines whether existing data is preserved for appending or replaced.
- Both classes process **raw bytes**; they do not automatically decode UTF-8, nor do they understand lines, integers, images, or JSON. Interpreting the data is the responsibility of the layer above.
- Both are I/O streams tied to operating system resources. Opening can fail and operations can throw `IOException`; the resources must be closed when finished.

| Need | Option | Main Behavior |
|---|---|---|
| Read a file | `new FileInputStream(file)` | Opens for reading; does not create a missing file |
| Create or replace file contents | `new FileOutputStream(file)` | If a valid file does not exist, creates it; if it exists, **erases the old contents (truncate)** |
| Append bytes to the end of a file | `new FileOutputStream(file, true)` | If the file does not exist, creates it; if it already exists, keeps old data and writes after it |
| Write from the beginning with an explicit parameter | `new FileOutputStream(file, false)` | Same meaning as not passing the append flag |

Here `file` can be a `File` object; similar constructors also accept a `String` path. It is good practice to construct paths explicitly using `Path` and convert to `File` when using classic APIs:

~~~java
Path path = Path.of("data.bin");
File file = path.toFile();

// The following lines are illustrative; do not open all three write streams at the same time:
FileInputStream input = new FileInputStream(file);
FileOutputStream overwrite = new FileOutputStream(file);
FileOutputStream append = new FileOutputStream(file, true);
~~~

The snippet above only illustrates the constructors and is **not** a standalone runnable program. In real code, choose the exact mode suited to your purpose, manage closing the stream, and avoid opening a write stream when you do not yet intend to write data. Merely creating `new FileOutputStream(file)` can already truncate the file.

## 2. Distinguishing Overwrite and Append

Suppose a file currently contains three bytes in order:

~~~text
A B C
~~~

After opening `new FileOutputStream(file)` and writing two bytes `X Y`, the final contents are:

~~~text
X Y
~~~

Conversely, opening `new FileOutputStream(file, true)` and then writing `X Y` produces:

~~~text
A B C X Y
~~~

Important notes:

1. `append = true` means **writing new bytes at the end of the file**. It does not automatically add a newline character, space, delimiter, or header.
2. `append = false` is the default. On an existing regular file, a constructor opening output in this mode truncates the file; closing it immediately afterward does not restore the old data.
3. Both modes can create a new file if the file does not exist and the path and permissions are valid. They **do not automatically create parent directories**.
4. Failure to open—for example because the file does not exist when reading, the path is an invalid directory target, or permissions are missing—raises an error (typically `FileNotFoundException` when creating the stream), rather than returning an empty stream.
5. Append does not inherently guarantee that multiple threads or multiple processes writing concurrently will produce intact **atomic business records**. If synchronized access or file locking is needed, it must be designed separately; data delimiter rules must also be clearly defined.

To add a line of text to a file, the application itself must decide whether to write `"\n"` or not. Append is only a write-positioning behavior, not a line-management API.

## 3. Java 17+ Example: Writing New Data, Appending, and Overwriting

Create the file **`FileAppendDemo.java`** with the complete code:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class FileAppendDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("append-demo-", ".bin");

        try {
            // Without append: start the file contents with 3 bytes.
            try (FileOutputStream out = new FileOutputStream(path.toFile())) {
                out.write(new byte[] {10, 20, 30});
            }

            // Append: keep the existing 3 bytes and append the next 2 bytes.
            try (FileOutputStream out = new FileOutputStream(path.toFile(), true)) {
                out.write(new byte[] {40, 50});
            }
            System.out.println("Sau append: " + Arrays.toString(readAll(path)));

            // Without append: the previous file is truncated.
            try (FileOutputStream out = new FileOutputStream(path.toFile(), false)) {
                out.write(7);
            }
            System.out.println("Sau overwrite: " + Arrays.toString(readAll(path)));
        } finally {
            Files.deleteIfExists(path);
        }
    }

    private static byte[] readAll(Path path) throws IOException {
        try (FileInputStream in = new FileInputStream(path.toFile());
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[3];
            int n;
            while ((n = in.read(buffer)) != -1) {
                out.write(buffer, 0, n);
            }
            return out.toByteArray();
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac FileAppendDemo.java
java FileAppendDemo
~~~

Expected output:

~~~text
Sau append: [10, 20, 30, 40, 50]
Sau overwrite: [7]
~~~

Key observations:

- The program creates a new temporary file with `Files.createTempFile(...)` to avoid accidentally overwriting existing documents.
- On the first open, `FileOutputStream(path.toFile())` writes three bytes. Opening with `true` appends two more bytes; reading it back shows all five bytes.
- The final open with `false` truncates the old data and writes a single byte with value `7`; therefore the entire file contains only `[7]`.
- `readAll(...)` loops until EOF; each iteration transfers only the `n` bytes actually read to `ByteArrayOutputStream`. It does not assume the buffer size of 3 is always the number of bytes read.
- All three write streams, the read stream, and the memory stream are closed using `try-with-resources`. The `finally` block deletes the temporary file after the streams are closed.

In this example, the `readAll` method collects data into RAM for convenient printing; for very large files, you should process or copy in chunks rather than holding the entire contents in memory.

## 4. Reading Properly with FileInputStream

Common methods inherited from `InputStream`:

| Call | What You Get |
|---|---|
| `int value = in.read()` | A single byte as an `int` in the range `0..255`, or `-1` at EOF |
| `int n = in.read(buffer)` | Reads up to `buffer.length` bytes, starting at index 0 |
| `int n = in.read(buffer, offset, length)` | Reads up to `length` bytes into the array at index `offset` |
| `byte[] data = in.readAllBytes()` | Reads all remaining bytes into an array, suitable when the data is small enough |
| `long n = in.transferTo(out)` | Transfers bytes from input to an `OutputStream` until EOF |

`read(buffer, off, len)` returns **the actual number of bytes read**, which may be less than `len`, or `-1` if already at EOF (when `len > 0`). If `len == 0`, the call returns `0`. `off` is only an index in the **destination array**, not a position on disk. A valid range must satisfy `0 <= off <= buffer.length` and `0 <= len <= buffer.length - off`.

A read/copy loop is typically written as:

~~~java
byte[] buffer = new byte[8192];
int n;
while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
}
~~~

This is an **illustrative code snippet** requiring the two variables `input` and `output` to be open streams. Do not use `output.write(buffer)` instead of `output.write(buffer, 0, n)`: the last read may receive fewer bytes than the buffer size, causing stale leftover data to be written erroneously.

If processing each byte individually, always compare the `int` result with `-1` **before casting to `byte`**. A valid `0xFF` byte appears as `-1` when represented as a signed `byte`, whereas `in.read()` returns the integer `255` when reading it successfully; only an `int` `-1` signals EOF.

Calling `available()` does not reliably indicate the total number of bytes remaining in a file/stream under the general contract of `InputStream`; do not use it as a completion condition for reading. Always rely on `read()` returning `-1`, a known protocol length, or a dedicated full-read API.

## 5. Writing Bytes with FileOutputStream

Commonly used methods inherited from `OutputStream`:

- `out.write(int b)` writes the **low 8 bits** of the integer: `out.write(65)` writes exactly one byte `0x41` (the letter A when interpreted as ASCII).
- `out.write(byte[] bytes)` writes the entire array.
- `out.write(byte[] bytes, int offset, int length)` writes exactly `length` bytes starting at index `offset` in the source array.
- `out.close()` closes the stream and releases associated resources; prefer `try-with-resources` so it closes even when an exception occurs.

Unlike `read(...)`, `write(byte[], off, len)` returns `void`; if it completes normally, the call has performed the request to write `len` bytes to the stream according to the API contract. If a write failure occurs, the method may throw `IOException`. Do not use the return value of `read(...)` as `length` before checking that it is positive.

Example with an existing byte array:

~~~java
byte[] payload = {11, 22, 33, 44, 55};
out.write(payload, 1, 3); // Write three bytes 22, 33, 44
~~~

This is an illustrative code snippet; `out` must be a valid open `FileOutputStream`. The third argument is the **number of bytes**, not the ending index.

When you need to improve performance for writing many small chunks, you can wrap it with `BufferedOutputStream`. In that case, `flush()` pushes data currently in Java's buffer down to the underlying stream; it does not mean the data has been durably persisted on the storage device. Calling `close()` on the wrapping stream also closes the underlying stream, so manage closing only on the outer wrapper once ownership has been handed over to it.

## 6. Java 17+ Example: Appending Text with Explicit Encoding

`FileOutputStream` is a byte stream. When you need to store text, you must convert the `String` into bytes yourself using an explicit charset; for UTF-8 data, use `StandardCharsets.UTF_8`. This example intentionally writes a newline character at the end of each record because the append flag by itself does **not** add a newline.

File **`AppendUtf8Demo.java`**:

~~~java
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class AppendUtf8Demo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("append-lines-", ".txt");

        try {
            try (FileOutputStream out = new FileOutputStream(path.toFile())) {
                out.write("Dong 1\n".getBytes(StandardCharsets.UTF_8));
            }

            try (FileOutputStream out = new FileOutputStream(path.toFile(), true)) {
                out.write("Dong 2\n".getBytes(StandardCharsets.UTF_8));
            }

            try (FileInputStream in = new FileInputStream(path.toFile())) {
                String text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
                System.out.print(text);
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

~~~bash
javac AppendUtf8Demo.java
java AppendUtf8Demo
~~~

Output:

~~~text
Dong 1
Dong 2
~~~

The example keeps ASCII in its content so stdout looks consistent across common terminals; the encoding conversion still genuinely uses UTF-8. For large text files or line-by-line processing, prefer `BufferedReader`/`BufferedWriter`, `InputStreamReader`/`OutputStreamWriter`, or `Files.newBufferedReader`/`Files.newBufferedWriter`. You should not convert each read byte array independently to a `String` if a UTF-8 character could be split across two reads.

## 7. Resource Management and File Errors

Prefer `try-with-resources` for both reading and writing:

~~~java
try (FileInputStream in = new FileInputStream(sourceFile);
     FileOutputStream out = new FileOutputStream(targetFile)) {
    in.transferTo(out);
}
~~~

This is an illustrative code snippet: `sourceFile` and `targetFile` are valid `File` variables that have already been defined. This pattern automatically closes both streams when the block exits, even if reading or writing throws an error; there is no need to call `close()` manually in `finally`. Note that opening the destination with a non-append constructor **will truncate the destination**, and copying a file onto itself in this way can destroy data; verify that the source and destination are two appropriate files before opening.

Situations to handle proactively:

| Situation | Consequence and Handling Approach |
|---|---|
| Reading a nonexistent file | `FileInputStream` may throw `FileNotFoundException`; check the path or handle the error |
| Writing into a nonexistent parent directory | The constructor does not automatically create directories; create the directory beforehand if the application allows |
| Missing read/write permissions or locked file | May throw an I/O exception; report the error with proper context rather than pretending success |
| Opening output without append on a file with data | Truncates immediately upon opening; consider append, saving a backup copy, or a safe write mechanism |
| Reading with an array and ignoring `n` | May emit stale data at the end of the buffer; use the exact number of bytes actually received |
| Appending multiple records concurrently from multiple processes | Records may interleave depending on the system and write method; synchronization/locking or a centralized writing architecture is needed when integrity matters |
| Loading a large file with `readAllBytes()` | Can consume a large amount of RAM; read in fixed-size chunks |
| Writing text without specifying a charset | Prone to encoding mismatches across machines; use UTF-8 or an appropriate text reading/writing API |

Some write operations may pass data through the operating system's buffer. Closing the stream after writing guarantees resource closure per the API contract, but **does not by itself guarantee durability on disk during a power loss**. If the application requires that level of guarantee, you must design an appropriate data synchronization mechanism such as `FileDescriptor.sync()` and consider atomicity when replacing files; this concern is separate from the meaning of append.

## 8. FileInputStream/FileOutputStream vs. the Files API

The classic classes are very useful for understanding byte streams and maintaining compatibility with legacy code. In modern Java, `java.nio.file.Files` provides additional ways to open streams with explicit intent:

~~~java
Path path = Path.of("data.bin");

// These expressions only illustrate how to choose the API.
InputStream in = Files.newInputStream(path);
OutputStream fresh = Files.newOutputStream(path);
OutputStream append = Files.newOutputStream(
        path, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
~~~

This is an **illustrative code snippet** requiring imports for `java.io.InputStream`, `java.io.OutputStream`, `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.file.StandardOpenOption`. Each stream must be closed separately; you should not simultaneously open `fresh` and `append` on the same file in a real usage example.

- By default, `Files.newOutputStream(path)` has the effect of `CREATE`, `TRUNCATE_EXISTING`, and `WRITE`: create a new file or truncate an existing one, then write.
- To append data, specify `StandardOpenOption.APPEND`; add `CREATE` when you want to create the file if it does not yet exist, as shown in the example.
- If overwriting an existing file is not allowed, consider `CREATE_NEW` instead of the default create/truncate behavior.
- `Files.copy(...)` and `Files.write(...)` can be suitable for short file operations, though you still need to understand open options and overwrite risks.

Do not confuse `APPEND` with `CREATE` or `TRUNCATE_EXISTING`. They describe different decisions: write position, whether to create the file, and whether to erase existing contents. Avoid combining open options that have conflicting meanings.

## 9. How to Choose a Mode in Practical Scenarios

**Creating a new binary output:** write with `FileOutputStream` after verifying the destination path. If the application must not overwrite, use an API with the `CREATE_NEW` option.

**Adding log records:** use append mode, and write an appropriate delimiter and charset. For concurrent-write systems or reliable logging requirements, consider a dedicated logger and synchronization mechanism.

**Reading and copying a file:** use `FileInputStream` to read in chunks, and `FileOutputStream` to write the exact number of bytes received. There is no need to decode the data if only copying bytes.

**Reading a text file:** you can read bytes via `FileInputStream` and decode them, but `Files.newBufferedReader` or `InputStreamReader` usually expresses the intent better, especially when the content is large.

**Updating a byte in the middle of a file:** these two stream classes do not provide random positional access. Look at `RandomAccessFile` or `FileChannel` if you truly need to read/write by file offset; the offset in `read(byte[], off, len)` is only an offset **within the array**.

## 10. Knowledge Checklist

1. `FileInputStream` is read-only and returns `-1` at EOF; `FileOutputStream` is write-only.
2. `new FileOutputStream(file)` or `(..., false)` **truncates** an existing file; `(..., true)` **appends to the end**.
3. Append does not automatically add a newline, does not create parent directories, and does not guarantee atomicity of business records when multiple writers operate concurrently.
4. When reading into a `byte[]`, process only the `n` bytes that `read(...)` actually returns.
5. Close streams with `try-with-resources` and handle `IOException`; opening an output stream is also an operation with side effects.
6. Raw bytes differ from text: if you want to write text, specify a charset such as UTF-8.
7. For real applications, choose explicitly between creating a new file, replacing, and appending before opening the destination; use `Files` and `StandardOpenOption` when you need to express these policies.
