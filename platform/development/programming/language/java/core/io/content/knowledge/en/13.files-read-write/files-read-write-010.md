# `Files.copy` Combined with `InputStream` or `OutputStream` in Java

`java.nio.file.Files` does not only copy **file to file**. It also provides two overloads to transfer data between a **file path (`Path`)** and a **byte stream (`InputStream` or `OutputStream`)**:

~~~java
long bytesToFile = Files.copy(inputStream, destinationPath);
long bytesFromFile = Files.copy(sourcePath, outputStream);
~~~

With these, a program can save content from an input stream into a file, or send a file's content to an existing output stream. Examples include downloading bytes from a source into a file, writing a report to a caller-managed destination, sending a file over a socket, or exporting a file into an in-memory stream for testing.

To use them correctly, distinguish **data direction**, **return value**, **existing-target policy**, **stream ownership**, and **errors that can happen after partial writes**.

## 1. Three Easily Confused `Files.copy` Overloads

`Files` has three commonly used copy directions:

| Short signature | Where does data flow? | Return value |
|---|---|---|
| `Files.copy(InputStream in, Path target, CopyOption... options)` | **Input stream → target file** | `long` — number of bytes copied |
| `Files.copy(Path source, OutputStream out)` | **Source file → output stream** | `long` — number of bytes copied |
| `Files.copy(Path source, Path target, CopyOption... options)` | **Source file → target file** | `Path` — path to target file |

Crucially, the overload is chosen by **parameter types**, not variable names.

~~~text
1) InputStream ---- Files.copy ----> Path (new or replaced file)
2) Path (file) ---- Files.copy ----> OutputStream
3) Path (file) ---- Files.copy ----> Path (file)
~~~

Example:

~~~java
// in is InputStream; file is Path; out is OutputStream.
long first = Files.copy(in, file);
long second = Files.copy(file, out);
~~~

This is an **illustrative snippet**; it does not run standalone without declaring `in`, `file`, `out` and handling `IOException`. In the first overload, `file` serves as the **destination**; in the second, that same `file` serves as the **source**. Both `long` results measure **bytes**, not characters or lines.

## 2. `Files.copy(InputStream, Path)`: Saving Stream Bytes to a File

Syntax:

~~~java
long count = Files.copy(sourceStream, targetPath);
~~~

Behavior per API contract:

1. `sourceStream` is a byte source at its **current read position**.
2. `targetPath` identifies the destination file `Files` will create/write.
3. The method copies bytes from the source until **end of stream** into the target file.
4. Returns the number of bytes transferred upon completion.
5. **Does not close `sourceStream`**. The caller remains responsible for that byte source's lifecycle.

If `InputStream` was partially read beforehand, only the **remaining bytes** are copied. If the source is already at EOF, the copied byte count can be `0`, though note the target file is still subject to the corresponding creation/replacement policy.

Example:

~~~java
try (InputStream source = new ByteArrayInputStream(
        "Hello".getBytes(StandardCharsets.UTF_8))) {
    long bytes = Files.copy(source, Path.of("hello.txt"));
    System.out.println(bytes); // 5
}
~~~

This is a **snippet that must be placed inside a method** able to throw `IOException`, with imports for `java.io.*`, `java.nio.file.*`, and `java.nio.charset.StandardCharsets`. `ByteArrayInputStream` uses no OS file resource; `try-with-resources` here illustrates that the **caller**, not `Files.copy`, decides when to close the input.

### What If the Target File Already Exists?

For the `InputStream → Path` overload, by default if the target file **already exists**, the copy operation **fails**, typically with `FileAlreadyExistsException`. You can explicitly allow replacement with:

~~~java
long count = Files.copy(
        sourceStream,
        targetPath,
        StandardCopyOption.REPLACE_EXISTING);
~~~

This is an **illustrative snippet** where `sourceStream` is provided by the caller. `REPLACE_EXISTING` allows replacing the target file per `Files.copy` contract. This can **erase old content** if you have no backup. Do not mistake it for appending to the end of the file.

For the **`Files.copy(InputStream, Path, ...)` overload specifically**, `REPLACE_EXISTING` is the supported copy option under the Java SE 17 contract; do not mechanically apply `Path → Path` options such as `COPY_ATTRIBUTES` or `NOFOLLOW_LINKS` to this overload. Unsupported options can throw `UnsupportedOperationException`.

If the target file exists but cannot be written, or the parent directory does not exist/lacks permissions, the operation can still fail with an I/O error. `REPLACE_EXISTING` is not a command to "bypass all permission and path issues".

### Does `Files` Close the Output File It Opened Internally?

For `InputStream → Path`, `Files` opens and writes the target file within its own operation scope. **The caller does not receive a target file `OutputStream` to close.** Conversely, `sourceStream` is an external stream passed in, so `Files.copy` **does not close** it. If the source is a resource you opened yourself such as `Files.newInputStream(...)` or a network stream, the caller closes it promptly according to ownership.

## 3. `Files.copy(Path, OutputStream)`: Sending Bytes from a File to a Stream

Syntax:

~~~java
long count = Files.copy(sourcePath, destinationStream);
~~~

Meaning:

- `sourcePath` is the path to the **source** file.
- `destinationStream` is a **byte** receiver already created by the caller or supplied by another layer.
- `Files` reads the source file's content and writes it to the output stream.
- The `long` return value is the number of bytes written.
- **`destinationStream` is NOT closed by `Files.copy`**.

Example:

~~~java
ByteArrayOutputStream captured = new ByteArrayOutputStream();
long bytes = Files.copy(Path.of("hello.txt"), captured);
System.out.println("Copied: " + bytes);
System.out.println(captured.toString(StandardCharsets.UTF_8));
~~~

This is an **illustrative snippet** requiring an existing `hello.txt` file, imports, and `IOException` handling. `ByteArrayOutputStream` stores bytes in RAM for testing or forwarding to further processing.

When the output is `System.out` or a socket output stream, the ownership principle matters even more:

~~~java
Files.copy(Path.of("report.bin"), System.out);
System.out.flush(); // Flush only when the destination's contract requires it.
// Do not call System.out.close() in a temporary helper.
~~~

This snippet is illustrative only: it can **print unreadable binary bytes** to the terminal if the file is not text. `Files.copy` performs no decoding or charset conversion.

### The Output Stream May Already Contain Data

`Files.copy(Path, OutputStream)` writes bytes at the **current position and state** of `destinationStream`; it does not mean "clear the output and start a fresh file". With `ByteArrayOutputStream`, if a `prefix` was already written, copied bytes are appended after `prefix`. With a file output stream, overwriting or appending depends on how the caller **opened the output** (`CREATE`, `TRUNCATE_EXISTING`, `APPEND`, ...), not on parameters of `Path → OutputStream`.

Nor should you assume `Files.copy` automatically calls `flush()` on the caller-supplied stream. If the output is buffered, flushing/closing according to protocol and ownership is the owner's responsibility.

## 4. Complete Java 17 Example: Two-Way Copy and Stream Ownership

The following program proves in code that:

- `Files.copy(InputStream, Path)` writes bytes from input to file, yet **does not close input**.
- `Files.copy(Path, OutputStream)` sends file bytes to output, yet **does not close output**.
- The caller can still write more data to output after copying.
- Writing to an already-existing target file **without `REPLACE_EXISTING`** throws `FileAlreadyExistsException`.
- With `REPLACE_EXISTING`, the file content is replaced.
- All temporary files/directories created by the program are cleaned up after use.

Save as **`FilesCopyStreamsDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class FilesCopyStreamsDemo {
    static final class TrackedInput extends FilterInputStream {
        boolean closed;

        TrackedInput(InputStream source) {
            super(source);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static final class TrackedOutput extends FilterOutputStream {
        boolean closed;

        TrackedOutput(OutputStream destination) {
            super(destination);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("copy-streams-");
        Path targetFile = directory.resolve("target.txt");

        try {
            TrackedInput input = new TrackedInput(
                    new ByteArrayInputStream(
                            "Java I/O".getBytes(StandardCharsets.UTF_8)));
            try (input) {
                long bytes = Files.copy(input, targetFile);
                System.out.println("To file: " + bytes);
                System.out.println("Input closed by copy: " + input.closed);
            }
            System.out.println("Input closed by owner: " + input.closed);

            ByteArrayOutputStream captured = new ByteArrayOutputStream();
            TrackedOutput output = new TrackedOutput(captured);
            try (output) {
                long bytes = Files.copy(targetFile, output);
                System.out.println("From file: " + bytes);
                System.out.println("Output closed by copy: " + output.closed);

                output.write('!');
                output.flush();
            }
            System.out.println("Output closed by owner: " + output.closed);
            System.out.println("Captured: "
                    + captured.toString(StandardCharsets.UTF_8));

            try (InputStream second = new ByteArrayInputStream(
                    "Updated".getBytes(StandardCharsets.UTF_8))) {
                try {
                    Files.copy(second, targetFile);
                } catch (FileAlreadyExistsException ex) {
                    System.out.println(
                            "Existing target: FileAlreadyExistsException");
                }
            }

            try (InputStream replacement = new ByteArrayInputStream(
                    "Updated".getBytes(StandardCharsets.UTF_8))) {
                long bytes = Files.copy(replacement, targetFile,
                        StandardCopyOption.REPLACE_EXISTING);
                System.out.println("Replaced bytes: " + bytes);
            }
            System.out.println("File after replace: "
                    + Files.readString(targetFile, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(targetFile);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 FilesCopyStreamsDemo.java
java FilesCopyStreamsDemo
~~~

**Expected output** in an environment permitting temp directory creation/deletion:

~~~text
To file: 8
Input closed by copy: false
Input closed by owner: true
From file: 8
Output closed by copy: false
Output closed by owner: true
Captured: Java I/O!
Existing target: FileAlreadyExistsException
Replaced bytes: 7
File after replace: Updated
~~~

Explanation:

1. `"Java I/O"` has 8 ASCII/UTF-8 bytes. `Files.copy(input, targetFile)` copies 8 bytes into the new file and returns `8L`.
2. `TrackedInput.closed` is `false` immediately after copying because `Files.copy` **does not close the supplied input source**. Upon leaving `try (input)`, the caller closes input and the flag becomes `true`.
3. `Files.copy(targetFile, output)` copies the 8 bytes of the file to output. Before the caller closes output, the flag remains `false` and `output.write('!')` continues to work.
4. Closing `TrackedOutput` via `try (output)` sets the flag to `true`. `ByteArrayOutputStream` allows reading written content even after closing; do not generalize that behavior to files/sockets.
5. Copying a second time to the **same existing file** without a replacement option throws `FileAlreadyExistsException`. The example catches the expected exception specifically to continue.
6. `REPLACE_EXISTING` lets `Updated` (7 bytes) overwrite the old content. `Files.readString(targetFile, UTF_8)` reads it back to verify.
7. `finally` removes the temporary file and directory if the environment permits. If the filesystem fails, `IOException` must still be handled; the example does not assume every system allows writing to the temp directory.

This is a standalone `main` example for Java 17+, using a temporary path so no pre-existing input file is needed. It checks **close calls on wrappers** via the `closed` flag, not OS file descriptor state.

## 5. Comparison with `InputStream.transferTo(OutputStream)`

Another copy option available since Java 9 is:

~~~java
long count = input.transferTo(output);
~~~

`transferTo` copies **remaining bytes** from `InputStream` to `OutputStream`, without closing either stream. It differs from `Files.copy` overloads in source/target types:

| Task | Concise approach | Who manages external streams? |
|---|---|---|
| Existing `InputStream` → target file | `Files.copy(input, path)` | Caller manages **input** |
| Source file → existing `OutputStream` | `Files.copy(path, output)` | Caller manages **output** |
| Existing `InputStream` → existing `OutputStream` | `input.transferTo(output)` | Caller manages **both** |
| Source file → target file | `Files.copy(from, to)` | `Files` manages operations via two `Path`s |

If you open both ends of a copy operation yourself, you might write:

~~~java
try (InputStream input = Files.newInputStream(from);
     OutputStream output = Files.newOutputStream(to)) {
    input.transferTo(output);
}
~~~

This is an **illustrative snippet**: `from` and `to` are `Path`s, and `Files.newOutputStream(to)` has a default create/truncate policy **different** from `Files.copy(InputStream, to)` when the target file already exists. Thus the two approaches are not strictly equivalent regarding **handling an existing target file**, even though both transfer the same bytes.

Use the right `Files.copy` overload when you want **`Files` to manage the file side** and the caller only manages the stream side it owns.

## 6. Resource Ownership and Closing Streams

When working with streams, the key question is: **who opens, who owns, and who is allowed to close?**

### `InputStream` Passed to `Files.copy(input, path)`

~~~java
static long save(Path target, InputStream source) throws IOException {
    return Files.copy(source, target);
}
~~~

If this method merely **borrows** `source` from the caller, it **does not close** the source. The caller may have opened a file, socket, or supplied a data stream with its own lifecycle. When writing Javadoc for the method, state clearly: "Copies remaining bytes and **does not close `source`**."

If the application **intentionally transfers ownership** of `source` to the method, the method can be designed to close `source` when finished, provided the contract is explicit; never arbitrarily add `try (source)` inside a helper that follows borrowing rules.

### `OutputStream` Passed to `Files.copy(path, output)`

~~~java
static long send(Path source, OutputStream destination)
        throws IOException {
    return Files.copy(source, destination);
}
~~~

This method also **does not close** output when merely borrowing it. For instance, `send(file, System.out)` must never close `System.out`, because other parts of the program may still print logs or output afterward.

If output is wrapped in `BufferedOutputStream`, the caller owns the wrapper and decides when to `flush`/`close`. `Files.copy` has no authority to terminate the entire destination.

### Why Must `try-with-resources` Be Placed at the Right Layer?

**Right — caller opens, caller closes:**

~~~java
try (InputStream in = Files.newInputStream(sourceFile)) {
    long count = Files.copy(in, newFile);
}
~~~

**Wrong if a helper is borrowing someone else's stream:**

~~~java
static long saveBorrowed(InputStream fromCaller, Path target)
        throws IOException {
    try (InputStream borrowed = fromCaller) {
        return Files.copy(borrowed, target);
    } // Closes the caller's stream as well!
}
~~~

`try-with-resources` does exactly what it was designed for: closing resources declared in it. However, **declaring a borrowed resource inside `try`** violates ownership. Renaming it to `borrowed` does not create a new stream or transfer ownership.

## 7. Copy Is Byte I/O, Not Automatic Text Transcoding

`Files.copy` with `InputStream` or `OutputStream` copies **bytes verbatim**. It does not distinguish whether a file is an image, ZIP, PDF, CSV, or plain text; it does not decode characters.

Vietnamese string example:

~~~java
byte[] bytes = "Cà phê".getBytes(StandardCharsets.UTF_8);
try (InputStream input = new ByteArrayInputStream(bytes)) {
    Files.copy(input, Path.of("coffee.txt"));
}
~~~

The target file receives the **UTF-8 bytes produced by the code itself**, not because `Files.copy` picked a charset. If the input was encoded in another charset, `Files.copy` still copies that charset's exact bytes; to read it back as a `String`, you must know the source charset.

When you need to **transcode** from one charset to another, decode bytes into characters and re-encode in the target charset, for example using `InputStreamReader`/`OutputStreamWriter` with explicit charsets. Never use character conversion when your goal is verbatim binary copying.

## 8. Copying Large Files, Slow Streams, and Error Handling

A single `Files.copy` call can handle large byte volumes without manually allocating a `byte[]` holding the entire data. However, it is not an atomic operation:

- **Bytes may be partially written before an error occurs.** With `InputStream → Path`, the target file may already exist in an incomplete state when `IOException` is thrown. With `Path → OutputStream`, the caller's output may also have received partial bytes.
- **The operation can block.** Reading from a socket or pipe before the sender finishes can cause `Files.copy(input, path)` to wait. If the input never signals EOF, copying can stall indefinitely.
- **Out of space or permission errors:** can cause target file writes to fail. Plan cleanup, post-write verification, and user feedback.
- **Do not use the `long` return value as a checksum:** two files with equal byte counts are not proven to have identical content. When integrity verification is needed, use checksums/hashes per protocol design.
- **Not an automatic input-size limiter:** these overloads have no parameter to "copy at most N bytes". For untrusted input, design a bounded stream or size-controlled copy loop upfront/afterward as required.

### Avoiding Corrupting Overlapping Source and Target Files

A dangerous mistake is opening an `OutputStream` on the **source file itself**, such as:

~~~java
Path file = Path.of("data.bin");
try (OutputStream output = Files.newOutputStream(file)) {
    Files.copy(file, output); // DANGEROUS!
}
~~~

This is an **illustrative snippet to avoid**. `Files.newOutputStream(file)` by default can **truncate the file immediately upon opening**, before `Files.copy` even reads it. To copy a file to a file, use `Files.copy(Path, Path, ...)` with **distinct source and destination paths** and an appropriate existing-target policy.

### Safe Copying When You Must Not Corrupt an Old File

If you need to write data to a file currently used by users, usually you should:

1. Pick a temporary file in an appropriate directory.
2. Copy all data to the temporary file; handle errors and clean up the temp file if incomplete.
3. Verify/validate data per the application contract.
4. Replace the target file using a mechanism suited to the filesystem and atomicity/durability requirements.

`Files.move` with `ATOMIC_MOVE` can be used when supported by the provider, yet **never assume every filesystem supports atomic moves**. Do not confuse `Files.copy`'s `REPLACE_EXISTING` with an atomic update, and do not treat `flush` as an fsync guarantee.

## 9. Using `Files.copy(Path, Path)` When Both Ends Are Files

If you already have two file paths and do not need stream interception in between:

~~~java
Path result = Files.copy(
        from,
        to,
        StandardCopyOption.REPLACE_EXISTING);
~~~

This is an **illustrative snippet** with two `Path` variables and `IOException` handling. The return value is a `Path`, **not a byte count**. The `Path → Path` overload also supports specific options such as `COPY_ATTRIBUTES` or `LinkOption.NOFOLLOW_LINKS` depending on format and filesystem. Do not confuse these options with the `InputStream`/`OutputStream` overloads.

Note: `Files.copy(Path, Path)` has its own contract when the source is a directory or symbolic link; copying a directory **does not automatically copy the entire tree recursively**. When working with directories or symlinks, read the exact Javadoc of the overload and options.

## 10. Common Mistakes and Fixes

| Mistake | Issue | Fix |
|---|---|---|
| Calling `Files.copy(input, path)` assuming input is closed | API does not close the supplied input stream | Caller manages input via `try-with-resources` when owning it |
| Calling `Files.copy(path, out)` assuming output is closed | Output still belongs to caller | Caller flushes/closes per its own lifecycle |
| Calling `Files.copy(InputStream, Path)` on existing target without `REPLACE_EXISTING` | May throw `FileAlreadyExistsException` | Define clear no-overwrite vs. replace policy |
| Passing `COPY_ATTRIBUTES` to `InputStream → Path` | Not supported by this overload | Use `REPLACE_EXISTING` if needed or use `Path → Path` |
| Confusing return types across all three overloads | `Path → Path` returns `Path`; both stream overloads return `long` | Check method signature and return type |
| Decoding bytes while copying image/ZIP files | Corrupts binary content | Copy raw bytes directly |
| Treating equal byte counts as data integrity | Same size can hold different contents | Verify hash/signature or protocol checks |
| Letting a helper close a caller-supplied stream | Other layers lose read/write access | Define ownership clearly; never close borrowed streams |
| Opening output on the same file before copying from it | Can truncate the source | Keep source/destination separate; never open target destructively over source |
| Using `Files.copy` on unbounded streams without limits | Can block or exhaust disk space | Enforce byte limits and timeouts/cancellation at appropriate layers |
| Assuming target stays intact if copy fails | Partially written bytes may remain | Use temp file/cleanup and a safe update strategy |

## 11. Self-Check

**Q1.** You have an `InputStream` from an HTTP client and want to save it to a non-existent `download.bin`. Which overload should you call? Who closes the input?

> Use `Files.copy(input, path)` to transfer bytes into the target file. **The owner of the HTTP stream** per the client's contract must close `input`; `Files.copy` does not close it automatically.

**Q2.** You have `archive.zip` and want to send raw bytes into an `OutputStream` supplied by the caller. What should you use?

> `Files.copy(Path.of("archive.zip"), output)` returns the number of bytes transferred. Since `output` is managed by the caller, a borrowing helper must not close `output`.

**Q3.** `Files.copy(InputStream, Path)` is writing to an existing file; why consider `REPLACE_EXISTING` carefully?

> By default the operation fails when the target exists. `REPLACE_EXISTING` permits replacement, yet it can destroy old data and does not turn the copy into an atomic update.

**Q4.** Calling `Files.copy(pathA, pathB)` and `Files.copy(pathA, output)` — do both return the same type?

> **No.** `Path → Path` returns the destination `Path`; `Path → OutputStream` returns a `long` byte count.

**Q5.** Does `Files.copy(sourceFile, System.out)` turn a PDF into readable text? Should you close `System.out` right afterward?

> **No.** Copying preserves binary bytes verbatim; a PDF is not converted into text. And `System.out` is a shared stream that helpers must never close arbitrarily.

**Q6.** Calling `Files.copy(input, path)` returns `1024L`. What does this prove, and what does it NOT prove?

> It reports that 1024 **bytes** were copied successfully per the return value. It **does not prove** the content matches an expected checksum, does not guarantee hardware durability, and does not prove the original input had exactly 1024 bytes if the stream was partially read earlier.

## Remember

- **`Files.copy(InputStream, Path, ...)`:** copies bytes from **input stream → file**, returns `long`, **does not close input**, and does not overwrite an existing target by default.
- **`Files.copy(Path, OutputStream)`:** copies bytes from **file → output stream**, returns `long`, and **does not close output**.
- **`Files.copy(Path, Path, ...)`:** copies **file → file**, returns `Path`; options have their own contract.
- **`InputStream.transferTo(OutputStream)`:** for when both ends are already streams; **closes neither end**.
- **Byte copying picks no charset**; whichever party owns a stream owns its lifecycle.
- **I/O can fail after partial writes**: design overwrite, cleanup, and data validation per real requirements.

**References:** [Java SE 17 — `Files.copy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [`InputStream.transferTo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)), [`StandardCopyOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html).