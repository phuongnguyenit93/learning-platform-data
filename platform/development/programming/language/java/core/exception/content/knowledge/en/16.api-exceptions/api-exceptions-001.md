# IOException, FileNotFoundException, and Read/Write Errors in Java

## 1. Overview

Reading and writing data are tasks that frequently interact with **external resources**: files, devices, sockets, network file systems, data streams, or APIs providing input/output. These operations can fail for reasons not entirely under the program's control: a missing file, lost access permissions, an invalid path, a disconnected device, out of storage space, decoding errors, or failures even when closing the resource.

In Java, this group of errors is prominently represented by **`java.io.IOException`**, which is a **checked exception**. A familiar subclass is **`java.io.FileNotFoundException`**, which commonly appears when code uses classic I/O APIs and fails to open a file. In the modern **NIO.2** API (`java.nio.file.Files`, `Path`), specific errors are often expressed by other classes such as `NoSuchFileException`, `AccessDeniedException`, or `FileAlreadyExistsException`, which also reside under the `IOException` hierarchy.

Learning objectives:

- Distinguish `IOException`, `FileNotFoundException`, and several file-related exceptions in `java.nio.file`.
- Understand **checked exceptions**: method callers must `catch` or declare `throws` when required.
- Know why `FileNotFoundException` is not the only explanation for every I/O failure and why Java NIO.2 may throw `NoSuchFileException`.
- Distinguish **normal end of data (EOF)** from an **actual read error**.
- Safely open, read, write, and close files using `Files`, `InputStream`, `OutputStream`, `Reader`, `Writer`, and `try-with-resources`.
- Preserve the primary error, cleanup error, and `cause` when multiple failures occur.
- Know the situations where you need to check paths, charsets, resource ownership, write modes, and recovery strategies.
- Write error messages/logs with clear context without guessing the wrong cause.

Complete examples use **Java 17+**, with deterministic filenames, `javac`/`java` commands, and `stdout`. Non-standalone illustrative snippets are explicitly noted.

## 2. Inheritance Hierarchy of Common I/O Exceptions

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.io.IOException                 [checked]
        ├── java.io.FileNotFoundException
        ├── java.io.EOFException
        ├── java.io.UTFDataFormatException
        ├── java.io.InterruptedIOException
        ├── java.io.CharConversionException
        ├── java.io.UnsupportedEncodingException
        └── java.nio.file.FileSystemException
            ├── java.nio.file.NoSuchFileException
            ├── java.nio.file.AccessDeniedException
            ├── java.nio.file.FileAlreadyExistsException
            └── java.nio.file.DirectoryNotEmptyException
```

The diagram lists only **part** of the exception tree, not all subtypes of `IOException`. In practice, each API may choose the specific error type that matches its semantics.

| Exception Type | Typical Meaning | Context Example |
| --- | --- | --- |
| `IOException` | General input/output operation failure | Read, write, close, or data transfer failure |
| `FileNotFoundException` | Failed to open a file via classic I/O APIs; not necessarily just because it "does not exist" | `new FileInputStream(file)` |
| `NoSuchFileException` | An NIO operation reports that the target file/path does not exist | `Files.readString(path)` on a non-existent file |
| `AccessDeniedException` | The file system reports insufficient access permissions | Opening or writing to a denied path |
| `FileAlreadyExistsException` | The API requires creating a new target, but it already exists | `Files.createFile(existingPath)` |
| `DirectoryNotEmptyException` | Cannot delete a directory that still contains entries | `Files.delete(nonemptyDir)` |
| `EOFException` | Some APIs require reading enough structured data but hit end-of-data too early | `DataInputStream.readInt()` when bytes are missing |
| `MalformedInputException` | Byte data is invalid for the charset being decoded | Reading malformed UTF-8 data |

**Important point:** `MalformedInputException` is a subtype of `CharacterCodingException`, which in turn extends `IOException`; the simplified diagram above does not list every intermediate branch. When precise handling is needed, check the inheritance hierarchy in the specific API.

### `IOException` Is a Checked Exception

`IOException` extends `Exception` and does **not** belong to the `RuntimeException` branch, so the compiler checks the propagation path of checked exceptions. A method calling an API that can throw `IOException` must either:

1. **Catch** it with `try/catch` and handle it appropriately; or
2. **Declare** `throws IOException` (or a compatible broader checked type) so the caller assumes responsibility.

Unlike `ArithmeticException` or `IllegalArgumentException`, `IOException` is **not an unchecked exception**. There is no need to force-convert it into a `RuntimeException` just to bypass the responsibility of designing error handling.

## 3. `IOException` and `FileNotFoundException`: Parent–Child Relationship

`FileNotFoundException extends IOException`, so any `catch (IOException e)` handler can also catch `FileNotFoundException`. However, the reverse is not true: a `catch (FileNotFoundException e)` handler **does not** catch an arbitrary `IOException`.

**Code snippet** example:

```java
try {
    java.io.InputStream input =
            new java.io.FileInputStream("data.txt");
    input.close();
} catch (java.io.FileNotFoundException notFound) {
    System.out.println("Cannot open the file");
} catch (java.io.IOException otherIo) {
    System.out.println("Another I/O failure");
}
```

The snippet above has a resource management risk: if an error occurs between opening and closing, closing may be skipped. The goal here is only to illustrate **catch ordering**. In real code, use `try-with-resources` instead of manually opening and closing as shown above.

Handlers must place **the subclass before the superclass**. If `catch (IOException)` is placed before `catch (FileNotFoundException)`, the specific branch afterward can never receive an exception not already caught by the parent branch, and `javac` may report an unreachable handler.

### Standalone Program: Inheritance Relationship

Create the file **`IOExceptionHierarchyDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class IOExceptionHierarchyDemo {
    static void simulate() throws IOException {
        throw new FileNotFoundException("report.csv");
    }

    public static void main(String[] args) {
        try {
            simulate();
        } catch (FileNotFoundException failure) {
            System.out.println("specific="
                    + failure.getClass().getSimpleName());
            System.out.println("also IOException="
                    + (failure instanceof IOException));
        } catch (IOException failure) {
            System.out.println("other IO error");
        }
    }
}
```

Compile and run:

```bash
javac IOExceptionHierarchyDemo.java
java IOExceptionHierarchyDemo
```

`stdout`:

```text
specific=FileNotFoundException
also IOException=true
```

In this program:

- `simulate()` declares the broader type `throws IOException` but actually throws `FileNotFoundException`.
- `catch (FileNotFoundException)` handles the specific error first.
- `instanceof IOException` returns `true` due to the inheritance relationship.
- The `catch (IOException)` branch serves as a fallback for `IOException`s that do not match the earlier specific type.

When an API declares `throws IOException`, it can throw **many different subclasses**, not only `FileNotFoundException`.

## 4. `FileNotFoundException` Does Not Strictly Mean "File Does Not Exist"

The class name can easily be misleading. With classic `FileInputStream` or `FileOutputStream`, a `FileNotFoundException` can occur when **the file cannot be opened** because the path does not exist, the file is inaccessible, it points to a directory, or due to an OS-dependent file-opening issue.

Example:

```java
try (java.io.FileInputStream input =
        new java.io.FileInputStream("orders.csv")) {
    int firstByte = input.read();
}
```

This is a **snippet inside a method that handles or declares `IOException`**. If the file cannot be opened, the constructor can throw `FileNotFoundException` right before entering the `try` body.

Possible causes include:

- The file does not exist at the **path being used by the program**.
- A relative path resolves against a different working directory than expected.
- The file is inside an inaccessible directory.
- The operating system denies permission to open it in the requested mode.
- The path points to an object unsuitable for the API (e.g., a directory instead of a regular file).
- The file is locked or shared incompatibly on certain platforms.

Do not assume that **every `FileNotFoundException` can be fixed by creating a new file**. If the cause is insufficient permissions or an incompatible open mode, automatically creating/overwriting can make data worse.

## 5. Classic `FileNotFoundException` vs. NIO.2 `NoSuchFileException`

Java supports multiple API groups:

**Classic I/O (`java.io`):**

```java
new java.io.FileInputStream("missing.txt");
```

**NIO.2 (`java.nio.file.Files`):**

```java
java.nio.file.Files.readString(
        java.nio.file.Path.of("missing.txt"));
```

Both expressions above are **illustrative snippets**. For a file that genuinely does not exist, `FileInputStream` typically throws `FileNotFoundException`; `Files.readString` on the default file system typically throws `NoSuchFileException`. Both fall under `IOException`.

The difference lies in the **API and error classification**: you should not assume every way of opening a file emits the same subclass.

### Runnable Program: Same Missing File, Different Subclass

Create the file **`MissingFileApisDemo.java`**:

```java
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class MissingFileApisDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("io-example-");
        Path missing = directory.resolve("not-created.txt");

        try {
            try (FileInputStream input =
                    new FileInputStream(missing.toFile())) {
                System.out.println(input.read());
            } catch (FileNotFoundException failure) {
                System.out.println("classic="
                        + failure.getClass().getSimpleName());
            }

            try {
                Files.readString(missing);
            } catch (NoSuchFileException failure) {
                System.out.println("nio="
                        + failure.getClass().getSimpleName());
            }
        } finally {
            Files.delete(directory);
        }
    }
}
```

```bash
javac MissingFileApisDemo.java
java MissingFileApisDemo
```

`stdout` in a normal execution environment with a default file system supporting temporary directories:

```text
classic=FileNotFoundException
nio=NoSuchFileException
```

The program creates **a new temporary directory** to guarantee that `not-created.txt` is not present there. Thus, the output does not depend on whether a file named `missing.txt` happens to exist in the working directory.

Notes:

- `Files.createTempDirectory` can itself throw `IOException` due to environmental issues. This is not a case of "guaranteed to succeed regardless of machine permissions."
- `Files.delete(directory)` can throw `IOException` if the environment interferes; the example uses a temporary resource in a permissive environment.
- `NoSuchFileException` extends `FileSystemException`, then `IOException`; **it is not a subclass of `FileNotFoundException`**.
- To accommodate different APIs, `catch (IOException)` is often the common boundary; branch by subclass only when distinct recovery behavior is truly needed.

## 6. `NoSuchFileException`, `AccessDeniedException`, and Other NIO Errors

NIO.2 provides subclasses with more detailed file-system information than the generic `FileNotFoundException`.

Illustrative signature example:

```java
static String load(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
```

The caller can organize `catch` blocks with **subclass first, superclass later**:

```java
try {
    String content = load(path);
    System.out.println(content);
} catch (java.nio.file.NoSuchFileException failure) {
    System.out.println("File missing");
} catch (java.nio.file.AccessDeniedException failure) {
    System.out.println("Access denied");
} catch (java.io.IOException failure) {
    System.out.println("Other I/O failure");
}
```

This is an **illustrative snippet** assuming a `Path` variable `path` and the `load` method from the previous snippet. It does not replace OS-level authorization, logging/monitoring, or input validation.

### Do Not Guess the `IOException` Kind from `getMessage()` Text

System messages can contain paths, error codes, and wording that vary across operating systems, providers, locales, and JDKs. **Do not use `failure.getMessage().contains("No such file")` as an error classification mechanism**, because the message text is not a stable contract.

If you need to distinguish access-denied cases, use `instanceof AccessDeniedException` or a specific `catch` branch. However, also accept that providers are not required to distinguish every situation with the exact same subclass in every environment.

### What Information Does `FileSystemException` Provide?

`FileSystemException` can provide `getFile()`, `getOtherFile()`, and `getReason()`. These are useful for diagnosing **the source file, target file, and reason** in operations such as `Files.move` or `Files.copy`.

Consider security when logging paths; user paths and filenames may contain private data. Distinguish between internal logs and externally visible messages.

## 7. Successful Reading/Writing with `Files` and UTF-8

For text files, `Files.writeString`, `Files.readString`, or `newBufferedReader`/`newBufferedWriter` are usually clearer than manually managing byte arrays. Specify the charset explicitly to avoid relying on the default encoding.

### Complete Program: Create, Write, Read, and Delete a Temporary File

Create the file **`SuccessfulFileIODemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SuccessfulFileIODemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("java-io-", ".txt");

        try {
            Files.writeString(
                    file, "alpha\nbeta\n", StandardCharsets.UTF_8);

            try (BufferedReader reader = Files.newBufferedReader(
                    file, StandardCharsets.UTF_8)) {
                System.out.println("line1=" + reader.readLine());
                System.out.println("line2=" + reader.readLine());
                System.out.println("end=" + reader.readLine());
            }

            System.out.println("full="
                    + Files.readString(file, StandardCharsets.UTF_8)
                            .replace("\n", "|"));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac SuccessfulFileIODemo.java
java SuccessfulFileIODemo
```

`stdout`:

```text
line1=alpha
line2=beta
end=null
full=alpha|beta|
```

Because the file is newly created and written with deterministic text, the data does not depend on any pre-existing file. `StandardCharsets.UTF_8` is specified for both reading and writing.

Key points to remember:

- Both `Files.createTempFile` and `Files.writeString` can throw `IOException`; `main throws IOException` is an appropriate propagation policy for a **demo program**, though it does not recover from errors itself.
- `BufferedReader.readLine()` returns `null` when there are no more lines — that is a **normal end-of-data condition**, not an exception.
- `try-with-resources` automatically closes the reader even if `readLine()` fails.
- `Files.deleteIfExists` in `finally` can fail; if cleanup is critical, use an appropriate error management/recording scope so the primary error is not lost.
- In real applications, you usually do not immediately delete a newly created file: the example deletes it to avoid leaving temporary data behind after running.

### When to Use Streams vs. Readers?

- `InputStream` / `OutputStream`: work with **bytes**; suitable for binary files, protocols, images, and compressed data.
- `Reader` / `Writer`: work with **characters** and charsets at the conversion layer.
- `BufferedReader`: convenient for reading text line by line.
- `Files.readString` / `Files.writeString`: convenient for high-level text operations when the data size is appropriate.
- `Files.newInputStream` / `newOutputStream`: work directly with file-system byte streams.

Do not use `Reader` to process arbitrary binary files: improper character decoding can corrupt bytes or trigger decoding errors.

## 8. Normal EOF Is **Not** an `IOException`

One of the most common misconceptions is: "When `read()` has no more data, it throws an exception." For many basic stream APIs, that is **false**.

For example, `InputStream.read()`:

- Returns a value `0..255` if a byte is read.
- Returns `-1` if the normal end of the stream has been reached.
- Can **throw `IOException`** if the read operation actually fails.

Similarly, `Reader.read()` typically returns a character code or `-1` at EOF; `BufferedReader.readLine()` returns `null` when no more lines remain. These are **sentinel values**, not checked exceptions.

### Runnable Program: EOF vs. Actual Read Error

Create the file **`EofVersusIOExceptionDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class EofVersusIOExceptionDemo {
    static class BrokenInput extends InputStream {
        @Override
        public int read() throws IOException {
            throw new IOException("device disconnected");
        }
    }

    public static void main(String[] args) throws IOException {
        try (InputStream input = new ByteArrayInputStream(
                "A".getBytes(StandardCharsets.US_ASCII))) {
            System.out.println("first=" + input.read());
            System.out.println("second=" + input.read());
        }

        try (InputStream broken = new BrokenInput()) {
            System.out.println(broken.read());
        } catch (IOException failure) {
            System.out.println("error=" + failure.getMessage());
        }
    }
}
```

```bash
javac EofVersusIOExceptionDemo.java
java EofVersusIOExceptionDemo
```

`stdout`:

```text
first=65
second=-1
error=device disconnected
```

Analysis:

1. ASCII `A` has byte value 65. The first read returns 65.
2. The second read returns `-1`, signaling **end of data**, not an error.
3. `BrokenInput` intentionally throws `IOException("device disconnected")` to simulate a device failure. The handler catches the exception properly.
4. `ByteArrayInputStream` is an in-memory resource to demonstrate EOF deterministically; `BrokenInput` is a simulated failing resource requiring no real hardware.

### Does `EOFException` Contradict This?

No. `EOFException` is a subclass of `IOException` thrown by **APIs that require a complete data structure**, for example `DataInputStream.readInt()` needing to read exactly 4 bytes. If the stream ends after 1 byte, it cannot return a valid `int`, so it throws `EOFException`.

Even though both involve running out of data, **the method contracts differ**:

| API | Normal End of Data / Insufficient Data | How It Reports |
| --- | --- | --- |
| `InputStream.read()` | No more bytes | Returns `-1` |
| `Reader.read()` | No more characters | Returns `-1` |
| `BufferedReader.readLine()` | No more lines | Returns `null` |
| `DataInputStream.readInt()` | Fewer than 4 bytes to decode `int` | Throws `EOFException` |
| `InputStream.readNBytes(int)` | May return fewer bytes than requested at EOF | Returns a shorter array |
| `DataInputStream.readFully(byte[])` | Not enough bytes to fill the buffer | Throws `EOFException` |

Therefore, do not write a `catch (EOFException)` handler for `BufferedReader.readLine()` expecting it to trigger on normal end-of-file.

## 9. Standalone Program: `DataInputStream` and `EOFException`

Create the file **`EofExceptionDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.IOException;

public class EofExceptionDemo {
    public static void main(String[] args) throws IOException {
        byte[] incomplete = {1, 2};

        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(incomplete))) {
            System.out.println("reading int");
            System.out.println(input.readInt());
        } catch (EOFException failure) {
            System.out.println("not enough bytes for int");
        }
    }
}
```

```bash
javac EofExceptionDemo.java
java EofExceptionDemo
```

`stdout`:

```text
reading int
not enough bytes for int
```

`DataInputStream.readInt()` requires reading exactly four bytes according to its format. The example intentionally provides only two bytes, so the method cannot return an `int` and throws `EOFException`.

Do not use `EOFException` generically for missing files. `FileNotFoundException`/`NoSuchFileException` relate to **opening or accessing a file**, whereas `EOFException` in this example relates to **data inside an already-open stream** being insufficient for the requested operation.

## 10. Write Errors: `IOException` Can Occur Late

With `OutputStream`, a `write` call may fail immediately during the write. With a buffered writer/stream, the error may only surface at `flush()` or `close()` time, depending on buffer structure and implementation. Do not assume that only `write` needs exception handling.

### Runnable Program: Simulating a `write()` Error

Create the file **`WriteIOExceptionDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;

public class WriteIOExceptionDemo {
    static class BrokenOutput extends OutputStream {
        @Override
        public void write(int value) throws IOException {
            throw new IOException("write failed");
        }
    }

    public static void main(String[] args) {
        try (OutputStream output = new BrokenOutput()) {
            output.write(65);
            System.out.println("unexpected success");
        } catch (IOException failure) {
            System.out.println("error=" + failure.getMessage());
        }
    }
}
```

```bash
javac WriteIOExceptionDemo.java
java WriteIOExceptionDemo
```

`stdout`:

```text
error=write failed
```

`BrokenOutput` intentionally throws an error when writing a byte, so `unexpected success` does not run. This is a **write** error, not EOF, and not automatically `FileNotFoundException`.

### Buffered Output and the Meaning of `flush()`

A buffered output stream can accumulate data in RAM before passing it to its delegate or the operating system. Therefore:

- `write(...)` may only write into the buffer.
- `flush()` requests pushing buffered data down to the underlying layer, but **does not guarantee** that data is durably persisted to disk on every system.
- `close()` typically performs cleanup and may flush before closing, depending on the API.
- Errors can arise during **flush/close** even when earlier `write` calls reported no errors.
- For file data durability, APIs like `FileChannel.force(...)` or commit/rename designs may need to be considered depending on requirements; do not infer that "no IOException" means a safe transaction.

When handling critical data, complete closing/flushing according to the contract before reporting that a write operation succeeded.

### `PrintStream` and `PrintWriter` Are Special Cases

Not every write API **throws a checked `IOException` to the caller**. `PrintStream` and `PrintWriter` generally **do not throw `IOException` directly from normal print methods**; they provide an error-state mechanism such as `checkError()`.

Consequently, `System.out.println(...)` will not report a checked `IOException` like a typical `OutputStream.write(...)`. When choosing an output API, understand the specific class's contract rather than assuming all "write" operations share the same exception behavior.

## 11. Encoding and Decoding Errors: Still Part of I/O

Reading text means converting **bytes** into **characters** according to a charset. If a file does not contain valid bytes for the selected charset, decoding APIs configured to report errors can throw exceptions in the `IOException` family, such as `MalformedInputException`.

A program can open a file successfully yet still fail **when it starts reading and decoding**. Thus, "able to open the file" does not mean "the file is validly formatted."

### Runnable Program: Invalid Bytes for UTF-8

Create the file **`MalformedUtf8Demo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class MalformedUtf8Demo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("invalid-utf8-", ".txt");

        try {
            Files.write(file, new byte[] {(byte) 0xC3, (byte) 0x28});

            try (BufferedReader reader = Files.newBufferedReader(
                    file, StandardCharsets.UTF_8)) {
                System.out.println(reader.readLine());
            } catch (MalformedInputException failure) {
                System.out.println("invalid UTF-8");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac MalformedUtf8Demo.java
java MalformedUtf8Demo
```

`stdout`:

```text
invalid UTF-8
```

`0xC3 0x28` is a byte pair that does not form a valid UTF-8 sequence: a leading byte `0xC3` must be followed by a valid continuation byte, whereas `0x28` is not one. `Files.newBufferedReader(path, UTF_8)` uses a decoder configured to **report errors** rather than silently replacing invalid bytes with another character.

Points to distinguish:

- `FileNotFoundException`/`NoSuchFileException`: usually relate to **file existence/opening**.
- `MalformedInputException`: the file may exist and open, but **its byte content is invalid** for the charset.
- Other decoding APIs can be configured with `CodingErrorAction.REPLACE` to substitute invalid characters instead of throwing. Do not assume every text-reading method throws the same exception.

If files come from untrusted sources, choose the charset deliberately, handle invalid data according to policy, and do not blindly rely on the environment-dependent default charset.

## 12. `try-with-resources`: Closing Resources Even When Read/Write Fails

I/O resources typically implement `Closeable` (a subtype of `AutoCloseable`). When `close()` is called at the wrong time or not called at all, handle leaks, lingering file locks, unreleased sockets, or incomplete buffered data can occur.

Recommended pattern:

```java
try (java.io.InputStream input =
        java.nio.file.Files.newInputStream(path)) {
    // Read data.
}
```

This is a **code snippet** assuming `path` and a context that handles or declares `IOException`. TWR automatically calls `input.close()` when the block completes normally or via an exception.

### When `close()` Also Fails: `getSuppressed()`

If the `try` body throws `IOException("read failed")` and `close()` throws `IOException("close failed")`, Java keeps the read error as the **primary** exception and attaches the close error as a **suppressed exception**, observable via `getSuppressed()`.

### Runnable Program: Preserving Both Processing and Closing Errors

Create the file **`IoSuppressedDemo.java`**:

```java
import java.io.IOException;

public class IoSuppressedDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("read failed");
        } catch (IOException failure) {
            System.out.println("primary=" + failure.getMessage());
            System.out.println("suppressed count="
                    + failure.getSuppressed().length);
            System.out.println("suppressed="
                    + failure.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac IoSuppressedDemo.java
java IoSuppressedDemo
```

`stdout`:

```text
closing
primary=read failed
suppressed count=1
suppressed=close failed
```

If the `try` body completes **normally** but `close()` fails, the close error becomes the primary exception rather than suppressed.

**Important:** do not write `finally { resource.close(); }` again for a resource already managed by TWR. Repeated closing is not guaranteed to be safe for every `AutoCloseable`.

### Close Only Resources **You Own**

If a method receives an `InputStream` **borrowed from its caller**, writing `try (input)` (Java 9+) will close the caller's stream, potentially breaking subsequent operations. TWR closes syntactically and **does not know who owns the resource**. Document ownership clearly in the method contract and place TWR in the scope responsible for releasing the resource.

## 13. Do Not Use `Files.exists` to "Guarantee No FileNotFoundException"

Misleading code:

```java
if (java.nio.file.Files.exists(path)) {
    return java.nio.file.Files.readString(path);
}
return "";
```

This is an illustrative method snippet. It suffers from a **time-of-check to time-of-use (TOCTOU)** issue: the file can be deleted, have its permissions changed, or be replaced **between the check and the read**. `Files.exists(path)` is also not proof that the file can be opened/read.

Therefore:

- If the operation requires reading the file, **perform the operation** and handle `IOException` from that call itself.
- Pre-checks can be useful for UX or validation, but they **do not replace** error handling at I/O time.
- Do not design infinite retries if the file truly does not exist; enforce limits and an error policy.
- Guard against untrusted path risks such as symlinks or path traversal if paths come from user input.

Example of a simple pattern:

```java
try {
    String text = java.nio.file.Files.readString(path);
    consume(text);
} catch (java.nio.file.NoSuchFileException failure) {
    reportMissingFile();
} catch (java.io.IOException failure) {
    reportIoFailure(failure);
}
```

This is an **illustrative snippet** requiring `consume`, `reportMissingFile`, and `reportIoFailure` to be defined. Classifying errors by exception type makes code more reliable than parsing `getMessage()`.

## 14. Paths, Working Directory, and Access Permissions

Many `FileNotFoundException` errors stem from **relative paths**. For example, `Path.of("config.txt")` does not automatically look in the directory containing your source code; it resolves against the process's **working directory** in the default file system.

```java
java.nio.file.Path path =
        java.nio.file.Path.of("config.txt").toAbsolutePath();
System.out.println(path);
```

This is an **illustrative snippet**; output is machine-dependent, so no specific path is shown. Use `toAbsolutePath()` to aid diagnostics, but do not use it to construct a safe path from untrusted input.

### Distinguish "File Exists" from "Read/Write Permission"

A file can exist yet the operation still fails:

- The caller lacks read or write permission.
- The resource resides on a mount with restrictive policies.
- The path is not a regular file as expected by the API.
- The file system has errors, becomes unavailable, or lacks quota/disk space.
- Sharing/locking behavior differs by platform.
- Another process modifies the file while the operation is running.

Methods such as `Files.isReadable`, `isWritable`, or `exists` are only **point-in-time checks** that can depend on the provider and permissions; they are not a guarantee that the next operation will succeed. Handle exceptions from the actual operation.

### Do Not Hardcode One Permission Error Type Across All Operating Systems

NIO's `AccessDeniedException` is used when the provider specifically reports that error type, but the same permission issue may be represented differently depending on the API/provider. With classic `FileInputStream`, some permission situations may surface as `FileNotFoundException`. Do not design logic that only works if every system throws the exact same subtype for every cause.

## 15. Opening Files for Writing: Overwrite, Append, and Create-New

Serious data bugs can come not from exceptions, but from **choosing the wrong file-open mode**.

With `Files.newOutputStream` and `Files.writeString`, `StandardOpenOption` flags control creation and writing:

- `CREATE`: create if it does not exist, if permitted.
- `CREATE_NEW`: create new only; if it already exists, fail instead of overwriting.
- `TRUNCATE_EXISTING`: when opened for writing, truncates an existing file to empty before writing new content.
- `APPEND`: append to the end of the file according to provider semantics.
- `WRITE`: open for writing.

Read each API's specific contract regarding **defaults when no options are passed**. For example, `Files.writeString` by default creates the file if missing and overwrites existing content (truncation), rather than appending by default.

### Illustrative Snippet: Create Only If Not Present

```java
java.nio.file.Files.writeString(
        path,
        text,
        java.nio.charset.StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE_NEW,
        java.nio.file.StandardOpenOption.WRITE);
```

This snippet assumes `Path path` and `String text` in a method declaring/handling `IOException`. If the file already exists, `CREATE_NEW` is designed **not to silently overwrite**.

### Illustrative Snippet: Append Content

```java
java.nio.file.Files.writeString(
        path,
        additionalText,
        java.nio.charset.StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.APPEND);
```

This is a code snippet, not a standalone program. `writeString` can still throw `IOException` when opening the file, writing data, or closing the stream.

Do not try to use `catch (FileNotFoundException)` to fix an accidental overwrite: if you pick the wrong open mode and the operation succeeds, **no exception will save the old data**.

## 16. Copying Streams: Read, Write, and Close Errors Can All Occur

When copying data, there are at least three stages:

1. Opening the source and target.
2. Reading from the source and writing to the target.
3. Closing/flushing resources and finalizing the operation.

An `IOException` can occur at **any stage**. Examples:

- Opening source: `NoSuchFileException` or permission error.
- Opening target: path error, permission error, or creation-mode error.
- `read`: source I/O fails mid-stream.
- `write`: target device fails, runs out of space, or loses connection.
- `close`: cleanup/flush failure.
- Cleaning up a partially written target file: can also fail.

### Runnable Program: Copying with `InputStream.transferTo`

Create the file **`CopyStreamsDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyStreamsDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("copy-demo-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("target.txt");

        try {
            Files.writeString(source, "hello", StandardCharsets.UTF_8);

            long copied;
            try (InputStream input = Files.newInputStream(source);
                 OutputStream output = Files.newOutputStream(target)) {
                copied = input.transferTo(output);
            }

            System.out.println("bytes=" + copied);
            System.out.println("target="
                    + Files.readString(target, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.delete(directory);
        }
    }
}
```

```bash
javac CopyStreamsDemo.java
java CopyStreamsDemo
```

`stdout` when the environment provides temporary files normally:

```text
bytes=5
target=hello
```

`"hello"` in UTF-8 is 5 bytes. `InputStream.transferTo(OutputStream)` can throw `IOException` from reading the source or writing the target. TWR closes both `output` and `input` in reverse order of their declaration in the header. Re-reading the target file is a content verification step, not a transaction mechanism.

**Limitation:** if writing fails midway, the target may already contain **partial data**. Exception handling does not automatically roll back written content. For critical data, consider writing to a temporary file, verifying success, and moving/renaming according to file-system conditions; do not assume every move is atomic across all providers.

## 17. Wrapping `IOException` While Preserving the Cause

At the application layer, you may want to convert `IOException` into a domain exception with a clearer name/meaning. When doing so, **do not lose the original throwable**.

### Correct Snippet

```java
try {
    loadConfiguration();
} catch (java.io.IOException original) {
    throw new IllegalStateException(
            "Application configuration cannot be loaded", original);
}
```

This is an illustrative snippet requiring `loadConfiguration()` to be defined. `IllegalStateException` is unchecked, so callers are not forced to catch/declare it at compile time, yet the I/O error remains **preserved in `getCause()`**.

### Diagnostic Anti-Pattern Snippet

```java
try {
    loadConfiguration();
} catch (java.io.IOException original) {
    throw new IllegalStateException(original.getMessage());
}
```

This snippet intentionally demonstrates an anti-pattern: copying only the message. The original `IOException`, its stack trace, and its suppressed exceptions are not linked to the wrapper.

### Runnable Program: Preserving `cause`

Create the file **`IOExceptionCauseDemo.java`**:

```java
import java.io.IOException;

public class IOExceptionCauseDemo {
    static class ImportException extends Exception {
        ImportException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void readData() throws IOException {
        throw new IOException("storage unavailable");
    }

    static void importData() throws ImportException {
        try {
            readData();
        } catch (IOException original) {
            throw new ImportException("import failed", original);
        }
    }

    public static void main(String[] args) {
        try {
            importData();
        } catch (ImportException failure) {
            System.out.println("outer=" + failure.getMessage());
            System.out.println("cause="
                    + failure.getCause().getClass().getSimpleName());
            System.out.println("cause message="
                    + failure.getCause().getMessage());
        }
    }
}
```

```bash
javac IOExceptionCauseDemo.java
java IOExceptionCauseDemo
```

`stdout`:

```text
outer=import failed
cause=IOException
cause message=storage unavailable
```

`super(message, cause)` in the custom exception ensures logging tools and callers can trace `getCause()`. There is no need to construct a new `IOException` just to "keep the message."

### When Should You Not Wrap?

If the method contract is already `throws IOException` and the current layer **adds no useful context**, let the `IOException` propagate as-is. Wrapping at every layer without abstraction boundaries makes error chains long and hard to read.

## 18. Retries: Not Every `IOException` Should Be Retried

An I/O error can be **transient** or **permanent (configuration/data-related)**. You cannot decide on a retry policy solely from the fact that the object is an `IOException`.

Examples:

- Brief network drop: some operations **may** recover on retry if the request is safe to repeat.
- File not yet created by another process preparing it: bounded waiting may work if the application has a clear synchronization contract.
- Wrong file path, corrupted UTF-8 data, lack of access permissions: retrying with unchanged input/configuration usually will not help.
- Partial data write followed by an exception: blind retrying can cause **duplicate writes**, especially with append or non-idempotent requests.
- Out of disk space at the destination: may require intervention and should not be retried continuously.

If you want to retry, determine:

1. **Error classification** from context and reliable subtypes.
2. **Idempotency** of the operation (read, conditional overwrite, append, transaction).
3. **Bounded attempts**, timeouts, and appropriate backoff.
4. **Remaining state after failure**, especially a partially written target file or transaction.
5. When to return the original error to the caller instead of continuing to mask it.

Design to avoid:

```java
while (true) {
    try {
        writeImportantData();
        break;
    } catch (java.io.IOException ignored) {
        // Do not retry infinitely or swallow all IOExceptions.
    }
}
```

This snippet **intentionally demonstrates an anti-pattern**. It can hang indefinitely, hide permission/disk errors, and cause duplicate writes in some cases. Only implement retries with an explicit policy and the ability to determine the outcome of the prior attempt.

## 19. Distinguishing API Exceptions from Other Programming Errors

Not every error when working with paths, streams, and files is an `IOException`:

- `NullPointerException`: passing `null` to an API that does not accept it.
- `IllegalArgumentException`: passing invalid arguments.
- `InvalidPathException`: invalid string for constructing a `Path`; this is an unchecked exception.
- `SecurityException`: may occur if an access-control mechanism enforces restrictions in relevant environments.
- `UnsupportedOperationException`: requesting an operation not supported by the provider/API.
- `ClosedChannelException`: an example of a **checked `IOException`** when accessing a closed channel, unlike the unchecked exceptions listed above.

Thus, `catch (IOException)` is not a handler for **every file-related issue**. Do not catch overly broad `Exception` and claim all failures are read/write errors; many reflect bugs or misconfigurations requiring different handling.

### Filenames, Paths, and External Data

When accepting paths from users:

- Choose an allowed base directory and normalize/validate paths according to your security model.
- Do not blindly trust manual path string concatenation.
- Do not embed sensitive details directly in messages or logs unnecessarily.
- Use agreed-upon charsets and data formats.
- Do not turn an arbitrary `IOException` into a "file not found" message without knowing the cause.

## 20. Utility Class Example: Contextual Error Handling and Proper TWR Scope

Create the file **`SafeTextLoaderDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class SafeTextLoaderDemo {
    static String readFirstLine(BufferedReader reader)
            throws IOException {
        // Reader is borrowed from the caller; DO NOT close it here.
        return reader.readLine();
    }

    static String loadOwnedText(String data) throws IOException {
        try (BufferedReader reader =
                new BufferedReader(new StringReader(data))) {
            return readFirstLine(reader);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("result="
                    + loadOwnedText("first\nsecond"));
        } catch (IOException failure) {
            System.out.println("IO failure="
                    + failure.getMessage());
        }
    }
}
```

```bash
javac SafeTextLoaderDemo.java
java SafeTextLoaderDemo
```

`stdout`:

```text
result=first
```

The notable point is **resource ownership**:

- `readFirstLine` receives a `BufferedReader` supplied by the caller; it only **borrows** the reader to read and leaves closing decisions to the caller.
- `loadOwnedText` **creates its own** reader and uses TWR within the owning scope.
- Both methods declare `throws IOException` to preserve the checked-exception contract, even though `StringReader` in the example does not touch the file system.

If a helper uses `try (reader)` (Java 9+) on a **borrowed** reader, it will close the caller's resource before the caller expects it. TWR does not infer ownership.

## 21. Quick Troubleshooting Reference

| Situation | Symptom / API | Usually Appropriate Handling |
| --- | --- | --- |
| File missing with `FileInputStream` | `FileNotFoundException` | Check configuration/path; distinguish from permission errors |
| File missing with `Files.readString` | `NoSuchFileException` | Classify missing file without guessing from message text |
| File exists but lacks permission | `AccessDeniedException` or another `IOException` | Fix permissions/configuration; do not retry infinitely |
| `InputStream.read()` returns `-1` | Normal EOF | End the read loop; do not throw a fake error |
| `DataInputStream.readInt()` lacks bytes | `EOFException` | Validate that structured data is complete |
| `write`/`flush`/`close` fails | `IOException` | Report failure, preserving primary and suppressed exceptions |
| Text file has invalid bytes for charset | `MalformedInputException` | Use the right charset and an explicit decode policy |
| `CREATE_NEW` when file already exists | `FileAlreadyExistsException` (NIO) | Decide whether overwriting is permitted |
| Partial write followed by disconnect | `IOException`, target may be modified | Check idempotency before retrying |
| Wrapping error for domain layer | `new DomainException(context, original)` | Preserve `cause`; do not copy only the message |
| Resource closed inside helper using borrowed stream | Lifecycle errors may occur later | Close in the owner scope, not in the helper |
| Reading/writing from untrusted source | Various errors | Validate path, encoding, permissions, errors, and security policy |

This table only lists **common** possibilities. File-system providers or libraries may throw other subtypes; reading the specific method contract remains essential.

## 22. Common Mistakes and Misconceptions

**"`IOException` is unchecked, so `throws` is unnecessary."** False. It is a checked exception.

**"`FileNotFoundException` is not an `IOException`."** False. It is a direct subtype of `IOException`.

**"Whenever a file is missing, every Java API throws `FileNotFoundException`."** False. NIO.2 typically uses `NoSuchFileException`.

**"`FileNotFoundException` only occurs if the file truly does not exist."** False. Opening a file can fail due to permissions, an invalid path for the operation, or platform restrictions.

**"Placing `catch (IOException)` before `catch (FileNotFoundException)` is better."** False. The subclass must precede the superclass if you want to handle it separately.

**"EOF always produces `EOFException`."** False. `InputStream.read()` typically returns `-1`, and `BufferedReader.readLine()` returns `null` at normal end of data.

**"`DataInputStream.readInt()` returns `-1` when bytes are missing."** False. It throws `EOFException` if fewer than four bytes can be read.

**"Reading a file successfully once guarantees no `IOException` next time."** False. The file can be modified and the file system can fail between operations.

**"If `Files.exists(path)` returns true, `Files.readString(path)` is guaranteed to succeed."** False. Pre-checking does not eliminate race conditions or permission errors.

**"You can rely on `getMessage()` to distinguish permission errors from missing-file errors."** Unsafe; message wording varies by OS/provider.

**"No error in `write()` means the write is complete and durable."** False. Errors can occur at flush/close; durability also requires its own contract.

**"`PrintWriter` and `OutputStream` throw checked `IOException` identically on all methods."** False. `PrintWriter` uses a different error-reporting mechanism, such as `checkError()`.

**"Reading invalid text bytes always replaces them with a replacement character."** Not necessarily. A decoder can be configured to throw `MalformedInputException`.

**"When using TWR, close errors don't matter."** False. They can be the primary or a suppressed error; data may still be unwritten.

**"TWR on a borrowed stream parameter does not close the caller's stream."** False. It closes the exact object passed into the header unless an adapter has special semantics.

**"Wrapping `IOException` with `new RuntimeException(original.getMessage())` preserves the original error."** False. Pass `original` as the `cause`.

**"Any `IOException` can be immediately retried multiple times."** False. Some errors are permanent, and some operations have non-idempotent side effects.

**"A failed write automatically rolls back the target file."** False. The target file may already be partially written.

**"`InvalidPathException` is a subclass of `IOException`."** False. It is an unchecked exception.

**"To be sure a file is always closed, just call `close()` twice."** False. Some `AutoCloseable` implementations do not guarantee idempotent closing without side effects.

## 23. Self-Check Exercises

1. **Is `IOException` checked or unchecked?** Checked.
2. **Is `FileNotFoundException` caught by `catch (IOException)`?** Yes.
3. **Is `NoSuchFileException` a subclass of `FileNotFoundException`?** No; both belong to the `IOException` family via different branches.
4. **What does `FileInputStream` usually throw when opening a non-existent file?** `FileNotFoundException`.
5. **What does `Files.readString` usually throw when a file is not found?** `NoSuchFileException` on the default provider.
6. **What does `InputStream.read()` returning `-1` mean?** Normal EOF.
7. **What does `BufferedReader.readLine()` returning `null` mean?** End of lines, not automatically an I/O error.
8. **What does `DataInputStream.readInt()` throw when only two bytes remain?** `EOFException`.
9. **When a write operation has updated half a file and throws `IOException`, should you blindly retry?** No; evaluate target state and idempotency.
10. **Does `try-with-resources` close the reader when `readLine()` throws an error?** Yes, per TWR semantics when the resource was initialized successfully.
11. **If `close()` also throws while the body already threw, where do you inspect the cleanup error?** Usually in `getSuppressed()` of the primary exception.
12. **If only `close()` fails while the body succeeds, is the close error always suppressed?** No; it can become the primary exception.
13. **Can you find the cause of an `IOException` solely from `getMessage()` and ignore the stack trace?** No; inspect the `Throwable`, `cause`, and `suppressed` exceptions when diagnosing.
14. **What is the effect of wrapping a lower-layer error with `new ImportException("...", original)`?** It adds context while preserving `original` as the `cause`.
15. **Does `Files.exists` replace `catch (IOException)`?** No.
16. **If you mistakenly pick `TRUNCATE_EXISTING` and the operation succeeds, will an `IOException` be thrown to save the old content?** No.
17. **Why should you specify UTF-8 when reading/writing text?** To match the data encoding and avoid ambiguous charset assumptions.
18. **What exception type can invalid UTF-8 bytes trigger?** `MalformedInputException` if the decoder is configured to report errors.
19. **If a helper receives an input stream from a caller that still needs it, should the helper use `try (stream)`?** No, if ownership remains with the caller.
20. **When NIO reports `AccessDeniedException`, should you always create a new file to fix it?** No; resolve permissions/access according to the contract.
21. **Does `PrintWriter.println` necessarily throw `IOException` directly like `OutputStream.write`?** No; check `PrintWriter`'s contract and inspect its error state when needed.
22. **Can an `IOException` appear in `close()` without appearing in `read()`/`write()`?** Yes.
23. **Can an error from `Files.createTempFile` occur before entering the `try` that closes a reader?** Yes; consider the exact point where resources are created and which scope is responsible.
24. **Why is a generic `catch (Exception)` not a good default for all I/O errors?** It bundles unrelated error types, can hide bugs, and loses type-specific recovery policies.

## 24. Official Java 17 Documentation

- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): general checked exception for I/O failures.
- [Java SE 17 — FileNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html): file-opening error in classic APIs.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): NIO.2 operations for reading, writing, creating, deleting, and copying.
- [Java SE 17 — NoSuchFileException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html): NIO type indicating a missing file.
- [Java SE 17 — AccessDeniedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AccessDeniedException.html): file access permission error.
- [Java SE 17 — FileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html): file/reason details for file-system errors.
- [Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `read()`, EOF via `-1`, and `transferTo`.
- [Java SE 17 — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): `readLine()` and `null` result at EOF.
- [Java SE 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt()`, `readFully()`, and `EOFException`.
- [Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): `write`, `flush`, `close`.
- [Java SE 17 — PrintWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html) and [PrintStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html): `checkError()` and exception contracts.
- [Java SE 17 — MalformedInputException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/MalformedInputException.html): invalid byte data for charset.
- [Java Language Specification 17 — `11 Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked exceptions and catch/throws rules.
- [Java Language Specification 17 — `14.20.3 Try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): automatic resource closing and suppressed exceptions.

**Key takeaway:** `IOException` is a **checked exception** for I/O failures. `FileNotFoundException` is a common subtype when **opening files with classic APIs**, whereas NIO.2 can return more specific types like `NoSuchFileException` or `AccessDeniedException`. Do not confuse **normal EOF** (`read() == -1`, `readLine() == null`) with an **I/O error**, and do not treat opening a file as a guarantee that reading, writing, or closing will succeed. Choose the appropriate API, charset, and open mode; use `try-with-resources` when you own the resource; preserve `cause` and `suppressed` exceptions for diagnostics; and build retry/cleanup strategies based on actual contracts.
