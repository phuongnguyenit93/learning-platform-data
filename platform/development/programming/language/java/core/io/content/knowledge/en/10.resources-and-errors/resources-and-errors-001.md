# IOException and Common Errors When Opening, Reading, or Writing in Java I/O

## 1. Goal: Understand Where I/O Errors Occur and Handle Them Properly

A Java program that reads a file might seem to consist of only three steps: open, read, and close. In reality, each step can fail independently because I/O data lies outside the JVM's complete control: the file may be moved, permissions may change, the device may run out of space, the connection may drop, the path may point to a directory instead of a file, or the close operation may discover that buffered data cannot be written.

`IOException` is the foundational *checked exception* of `java.io` and many `java.nio.file` APIs, signaling that an input/output operation has failed or been interrupted according to the API's contract. This lesson helps distinguish:

- **Open errors**: inability to obtain a stream/channel or create a file as requested.
- **Read errors**: the resource is open, but further data cannot be obtained or the data does not conform to the read contract.
- **Write errors**: inability to deliver data to the destination, possibly after part of it has already been written.
- **Flush/close errors**: completing the operation can fail; do not assume "calling write" means the data has been safely saved.
- **Program response**: record the cause, clean up resources, decide whether to retry, verify postconditions, and avoid corrupting data.

A typical processing flow looks like this:

~~~text
Path / I/O source
    |
    v
OPEN  --IOException--> classify open error (not found, permission, name collision...)
    |
    v
READ / WRITE --IOException--> know whether partial data was processed or not?
    |
    v
FLUSH / CLOSE --IOException--> must not lose the primary error
    |
    v
Evaluate postconditions / log / report error to the user
~~~

Not every error occurring around an I/O operation is an `IOException`. For example, `NullPointerException` when passing a null argument, `IllegalArgumentException` when configuration is invalid, and `SecurityException` due to access policies can be runtime exceptions. Do not catch `IOException` and assume you have handled every possible error in the program.

## 2. Exception Hierarchy You Should Know

`IOException` extends `Exception`, so it is a **checked exception**: a method that throws it must normally handle it with `try/catch` or declare `throws`. Some common classes:

| Type | When commonly encountered | Notes |
| --- | --- | --- |
| `IOException` | I/O error without a more specific subtype or when abstraction is needed | Should not infer the cause solely from the message |
| `FileNotFoundException` | Opening a file via `FileInputStream`/`FileOutputStream` fails | May be due to non-existence **or** other causes such as permissions or a contextually invalid path |
| `NoSuchFileException` | `java.nio.file.Files` cannot find the required file/component | Subtype of `FileSystemException` |
| `AccessDeniedException` | Access denied at the filesystem layer | Subtype of `FileSystemException`; the environment may report a different type |
| `FileAlreadyExistsException` | Attempting to create an already existing file in an operation that forbids overwriting | Commonly associated with `CREATE_NEW` or `Files.createFile` |
| `FileSystemException` | Filesystem error carrying file, other file, and environment-dependent reason details | Suitable for diagnosing NIO errors |
| `EOFException` | API requires a mandatory amount of data, but the stream ends prematurely | Different from normal EOF where `read() == -1` |
| `UTFDataFormatException` | UTF data error relative to the format expected by a specific API | Commonly seen when `DataInput.readUTF()` encounters invalid modified UTF-8 data |
| `CharacterCodingException` | Character encoding/decoding error under an error-reporting policy | May have subclasses such as `MalformedInputException` |
| `SocketException` | Socket error during network communication | Depends on context and connection state |
| `InterruptedIOException` | I/O interrupted according to the contract of certain APIs | Do not equate all thread interruptions with this exception |

The classes above do not replace reading the contract of the method being called. For the exact same "file does not exist" scenario, `Files.newInputStream(path)` typically throws `NoSuchFileException`, whereas `new FileInputStream(file)` typically throws `FileNotFoundException`. The specific type and message can differ across filesystem providers, OSes, and APIs.

### 2.1. `throws IOException` or `catch IOException`?

Low-level methods typically **declare `throws IOException`** so the calling layer knows the operation can fail:

~~~java
static byte[] load(Path path) throws IOException {
    return Files.readAllBytes(path);
}
~~~

This is an illustrative method snippet; it requires importing `java.nio.file.Files`, `java.nio.file.Path`, and `java.io.IOException`, and is not a standalone program. Even though short, this is still an API design decision: the caller must handle the error rather than silently receiving an empty `byte[]` when reading fails.

At the application orchestration layer, **catch where there is enough context to decide**: retry, return an HTTP error, display a message, or abort processing. There is no need to add a catch block in every layer just to print a stack trace and rethrow.

### 2.2. An Error Usually Has No Cross-Platform Invariant "Error Code"

You should not write business logic by searching for strings like `"Permission denied"` or `"The system cannot find the file specified"` in `getMessage()`. Messages depend on the operating system, provider, locale, and version.

If an API returns a stable subtype such as `NoSuchFileException` or `FileAlreadyExistsException`, catch that specific type. If you only receive a general `IOException`, preserve the `cause` and log full context for diagnosis instead of guessing from the message text.

## 3. Errors During the Resource Open Phase

### 3.1. Missing Path or Invalid Component

With NIO:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    // Read file...
} catch (NoSuchFileException e) {
    // File or required component not found.
}
~~~

This is an illustrative snippet, assuming an existing `Path path` and imports `java.io.InputStream`, `java.nio.file.Files`, and `java.nio.file.NoSuchFileException`. A non-existent path is not always an error: when **writing to create a new file**, the program may intentionally use `CREATE` or `CREATE_NEW`. The important thing is to distinguish **opening for reading** from **opening for writing/creating**.

Do not call `Files.exists(path)` and treat it as a guarantee that the file will still exist at `open` time. Between the two operations, another process might delete or move the file. This is the **time-of-check to time-of-use (TOCTOU)** problem. Handle the exception from the actual open operation instead of relying solely on a prior check.

### 3.2. Access Denied

`AccessDeniedException` can occur when the user running the program lacks required permissions, a directory denies access, or a filesystem policy rejects the operation. However, effective permissions also depend on ACLs, ownership, sandboxes, file locks, and providers.

Good handling usually involves reporting the relevant path and requesting valid permissions; **do not** automatically change permissions on batches of files or run the program with elevated privileges simply because an operation failed. In a server environment, internal logs may include detailed paths, while user-facing messages should avoid exposing sensitive directory structures.

### 3.3. File Already Exists and Overwrite Choices

`Files.createFile(path)` and `Files.newOutputStream(path, StandardOpenOption.CREATE_NEW)` require creating a new entry; if it already exists, you typically receive `FileAlreadyExistsException`.

~~~java
try (OutputStream out = Files.newOutputStream(
        path, StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    out.write(data);
} catch (FileAlreadyExistsException e) {
    // Do not overwrite existing data.
}
~~~

This illustrative snippet uses existing `Path path` and `byte[] data`, along with imports from `java.io` and `java.nio.file`. For applications that need to protect existing files, `CREATE_NEW` is better than the "check `exists` then open" pattern because the non-existence check and creation operation are requested atomically under the API contract for supporting providers.

Conversely, when calling `Files.newOutputStream(path)` **without passing options**, the default usually corresponds to creating if needed and truncating the file if it already exists. This can be destructive if a developer mistakes it for "open for appending".

### 3.4. File Is a Directory, Invalid Paths, and Filesystem Issues

Sources of open errors are not limited to missing files:

- The target is expected to be a regular file, but is actually a directory.
- A parent directory component does not exist yet.
- The path is too long or unsupported by the provider.
- The file is locked or in use by another application in an incompatible way.
- An external drive is disconnected or the filesystem switches to read-only state.

The exact exception type is not necessarily identical across all OSes. Rather than writing numerous speculative conditions for every case, handle useful causes by type where possible and let the remaining `IOException` flow through the full error-reporting path.

## 4. Java 17 Example: Distinguishing Missing Files from Existing Files

Save as **OpenFileFailuresDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class OpenFileFailuresDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("io-errors-demo-");
        Path file = directory.resolve("data.txt");

        try {
            try {
                Files.readString(file, StandardCharsets.UTF_8);
            } catch (NoSuchFileException e) {
                System.out.println("Missing file: true");
            }

            Files.createFile(file);
            try {
                Files.createFile(file);
            } catch (FileAlreadyExistsException e) {
                System.out.println("Already exists: true");
            }

            Files.writeString(file, "Java I/O", StandardCharsets.UTF_8);
            System.out.println("Content: " +
                    Files.readString(file, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 OpenFileFailuresDemo.java
java OpenFileFailuresDemo
~~~

Output on a standard filesystem supporting the operations above:

~~~text
Missing file: true
Already exists: true
Content: Java I/O
~~~

The program creates a new temporary directory automatically, so the specific directory name does not affect the output. The first read opens a file never created in that directory, demonstrating `NoSuchFileException`. The second creation calls `Files.createFile` on the existing file, demonstrating `FileAlreadyExistsException`. Finally, the program writes and reads the content normally.

The `finally` block cleans up the test resources. If deletion fails, it can also throw `IOException`; this small example allows the cleanup error to propagate to the caller. In production systems, cleanup exceptions should be managed so they do not mask the primary cause, as shown in the `try-with-resources` section below.

## 5. Errors When Reading: Normal EOF vs. IOException

### 5.1. EOF Is Not an Error in a Read-to-End Loop

With `InputStream.read()`, the value `-1` represents **end of data** (EOF). Values `0..255` are valid bytes. A typical loop:

~~~java
int value;
while ((value = input.read()) != -1) {
    // Process value.
}
~~~

This is an illustrative snippet with an already open `InputStream input`. Normal EOF does not require throwing `EOFException`: it is the valid termination condition when the goal is to "read until the end".

With `read(byte[])`, the method returns the actual number of bytes read or `-1` when no more data remains. **Do not treat a read shorter than the buffer as an error**: file streams, sockets, and wrappers may return fewer bytes than requested even when more data is available. Always rely on `count` to process the valid portion.

### 5.2. EOFException: Mandatory Data Is Missing

Another scenario is a protocol that requires reading **exactly N bytes**, such as 4 leading bytes representing an integer. `DataInputStream.readInt()` requires all four bytes; if the source only has two bytes before EOF, the method throws `EOFException`.

~~~java
try (DataInputStream in = new DataInputStream(
        new ByteArrayInputStream(new byte[] {0x01, 0x02}))) {
    int number = in.readInt(); // Missing two bytes: EOFException.
}
~~~

This illustrative snippet requires importing `java.io.DataInputStream` and `ByteArrayInputStream`, as well as handling `IOException`. This is not `read() == -1` in the usual sense: **the contract to read the mandatory amount of data was not satisfied**.

`InputStream.readNBytes(n)` can return an array shorter than `n` on premature EOF; `readNBytes(byte[], off, len)` returns the actual number of bytes read. If business logic demands exactly N bytes, the caller must check the count and throw `EOFException` or report a missing-data error itself. Do not assume all "read N" APIs throw the exact same exception type.

### 5.3. Mid-Stream IOException Is Not EOF

A source may successfully read several bytes and then fail because the connection drops or the device malfunctions. For example:

~~~text
Pass 1: read(buffer) -> 100 valid bytes
Pass 2: read(buffer) -> 72 valid bytes
Pass 3: read(buffer) -> IOException
~~~

If the program catches the exception and treats it as EOF, it will keep **truncated** data without reporting an error. This is a dangerous logic bug when reading images, configuration files, transaction records, or formatted data packets.

A sound strategy:

- Read until `-1` if the contract allows data of unknown length.
- If you need to verify size, checksum, or an end marker, check them **after reading succeeds**.
- When reading throws `IOException`, keep the result status as **failed**, not "succeeded with less data".
- Only use the prefix of data already read if the business logic explicitly defines partial results as valuable and provides a corresponding flag/status.

### 5.4. read() Can Block

For live sources like sockets, `read()` may wait for data. Not returning bytes immediately is not an `IOException`, and some APIs have their own timeout mechanisms. Do not use `available() == 0` to decide EOF: that is the number of bytes readable immediately under the class contract, **not** necessarily the entire remaining content. With non-blocking I/O, a value of 0 can also mean no data is temporarily available, unlike `-1` which means end of stream.

## 6. Java 17 Example: Read Failure After Partial Data Has Been Read

To test the logic without relying on real hardware, you can create a custom `InputStream` that always reads two bytes and then intentionally throws `IOException`. The demo proves that the error is not treated as EOF.

Save as **ReadFailureDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

public class ReadFailureDemo {
    static class FailingInput extends InputStream {
        private int position;

        @Override
        public int read() throws IOException {
            if (position == 0) {
                position++;
                return 'O';
            }
            if (position == 1) {
                position++;
                return 'K';
            }
            throw new IOException("Simulated read failure");
        }
    }

    public static void main(String[] args) {
        try (InputStream input = new FailingInput();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {

            int next;
            while ((next = input.read()) != -1) {
                output.write(next);
            }
            System.out.println("Read completed");
        } catch (IOException e) {
            System.out.println("Read failed: " + e.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReadFailureDemo.java
java ReadFailureDemo
~~~

Output:

~~~text
Read failed: Simulated read failure
~~~

The two bytes `O` and `K` were read before the error, yet the program does not print `Read completed` because the loop did not terminate at EOF. In a real application, policy might return a result object carrying a `PARTIAL_FAILURE` status, or abort all processing to avoid presenting incomplete data as a success.

**Note:** This is a simulated-failure `InputStream` designed for testing, not a way to trigger an operating system error. It also writes one byte at a time so the demo is easy to verify; when reading large amounts of data, buffered arrays should generally be used.

## 7. Errors When Writing: Data May Have Been Partially Written

### 7.1. write Does Not Return the Number of Bytes Written

By API signature, `OutputStream.write(byte[], off, len)` returns `void`. When it completes successfully, it is expected to have written the requested slice under its contract; when it fails, it can throw `IOException`. If an error occurs after part of the data, **the general API does not return a reliable count of "how many bytes were written"**.

Therefore, you should not do this:

~~~java
try {
    output.write(payload);
} catch (IOException e) {
    output.write(payload); // Wrong: may duplicate the portion that already succeeded.
}
~~~

This snippet illustrates an **unsafe practice**, with existing `output` and `payload`. If the first call pushed some bytes before failing, rewriting the entire payload risks duplicating data. Over a network, even whether the client sees an `IOException` is not enough to conclude whether the server received the message or not.

Retrying must depend on **operation and protocol properties**:

- **Idempotent**: repeating the request multiple times yields an equivalent final effect. For example, replacing a temporary file's complete contents and renaming it under a deterministic protocol when properly designed.
- **Non-idempotent**: each write is a new event, or appending can duplicate data. Do not blindly retry the whole operation.
- **Acknowledged**: the protocol includes request IDs, offsets/positions, checksums, or acknowledgments to reconcile state and recover safely.

### 7.2. Disk Full, Read-Only File, Closed Connection

Common causes:

- The filesystem is out of space or over quota.
- Write permission is no longer held at the time of the operation.
- A drive/device is removed and the file becomes unavailable.
- The destination is a closed socket or a failed network connection.
- The new path name is invalid or the directory structure does not exist.
- The stream/channel was already closed earlier (depending on the API, this may throw `IOException` or another exception).

An easily misunderstood example is `Files.writeString(path, text)`: a successful call indicates the API completed the write operation under its contract, **not necessarily** that the data has been synced to physical durable storage. If the problem requires durability across power loss, synchronization levels and filesystem guarantees must be considered separately.

### 7.3. Overwrite vs. Append Is a Business Decision

A write operation must be designed explicitly: create exclusively new, replace completely, or append:

~~~java
Files.writeString(path, "hello", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
~~~

This illustrative snippet uses `Path path` and the necessary NIO imports. With the options above, an already existing file typically causes `FileAlreadyExistsException`. To append instead:

~~~java
Files.writeString(path, "append", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE, StandardOpenOption.APPEND);
~~~

This is also an illustrative snippet, not standalone. `APPEND` does not automatically add a newline and does not make every write an atomic transaction across all filesystems. If logic requires "each record complete or nothing at all", a more appropriate solution than a plain append call is needed.

## 8. Buffered I/O: flush() and close() Can Also Report Errors

`BufferedWriter` and `BufferedOutputStream` commonly hold data in memory before passing it to the underlying destination. Consequently:

1. A `write` call may only write to the application buffer and succeed.
2. `flush()` requests pushing the buffered data down to the underlying stream; this is where an `IOException` may surface.
3. `close()` may flush/close the resource and report an error.
4. Do not equate `flush()` with guaranteeing **durable persistence on disk**. Physical synchronization, if needed, involves APIs and filesystems such as `FileChannel.force(...)`, which still cannot provide absolute guarantees for every hardware context.

Example:

~~~java
try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Tài liệu quan trọng");
} // writer.close() is called here and can throw IOException.
~~~

Illustrative snippet with an existing `Path path`. If `writer.write(...)` succeeds but closing fails, you must not record the entire operation as definitely successful; errors from both writing and closing must be handled.

### 8.1. Do Not Manually Call close Inside try-with-resources

There is no need to write:

~~~java
try (OutputStream out = Files.newOutputStream(path)) {
    out.write(payload);
    out.close(); // Redundant; makes lifecycle management harder to follow.
}
~~~

This is an illustrative snippet. `try-with-resources` automatically calls close at the end of the scope, even when the `try` body throws an exception. Closing early can be inappropriate if the stream might still be used afterward and can make error handling harder to trace.

## 9. try-with-resources: Preserving the Primary Error and Suppressed Exceptions

The `try-with-resources` syntax is preferred for resources implementing `AutoCloseable`, which generally applies to `InputStream`, `OutputStream`, `Reader`, and `Writer`.

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(target)) {
    input.transferTo(output);
}
~~~

Illustrative snippet with `Path source` and `Path target`. Resources are closed **in reverse order of declaration**: `output` first, then `input`.

Suppose:

- Inside the `try` body, a read error `IOException("read failed")` occurs.
- When closing `output`, another error `IOException("close failed")` occurs.

With `try-with-resources`, the exception from the `try` body is the primary error, while the close error is attached to the **suppressed exceptions** list accessible via `Throwable.getSuppressed()`. This allows diagnosing both causes without losing the initial error.

### 9.1. Java 17 Example: Simulating an Error on Close

Save **SuppressedExceptionDemo.java**:

~~~java
import java.io.IOException;

public class SuppressedExceptionDemo {
    static class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("read failed");
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed count: " +
                    e.getSuppressed().length);
            for (Throwable problem : e.getSuppressed()) {
                System.out.println("Suppressed: " + problem.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SuppressedExceptionDemo.java
java SuppressedExceptionDemo
~~~

Output:

~~~text
Primary: read failed
Suppressed count: 1
Suppressed: close failed
~~~

This is a controlled simulation that does not depend on real device failures. It demonstrates that an exception thrown during `close()` is still preserved in diagnostic information even when the `try` body already failed beforehand.

If **the `try` body completes normally** but `close()` throws an exception, the close error becomes the primary exception. When multiple resources are opened, multiple suppressed exceptions can appear. When handling and logging, retain the full stack trace/cause rather than saving only `getMessage()`.

### 9.2. Why You Should Not Carelessly Write finally with close

Legacy pattern:

~~~java
InputStream in = null;
try {
    in = Files.newInputStream(path);
    // Read...
} finally {
    if (in != null) {
        in.close();
    }
}
~~~

This illustrative snippet can cause an error from `close()` in `finally` to **mask** the original error from the `try` body. Manually preserving both exceptions is error-prone. In modern Java, prefer `try-with-resources` whenever possible. If you must use `finally`, actively preserve the primary exception, suppressed exceptions, and ensure every resource gets a chance to be closed.

## 10. Designing catch Blocks: When to Catch Specifically, When to Rethrow

### 10.1. Catch Specific Types Before General Types

Suppose an API needs to distinguish three scenarios:

~~~java
try {
    Files.readString(path, StandardCharsets.UTF_8);
} catch (NoSuchFileException e) {
    // Missing file: can return "not found" error code.
} catch (AccessDeniedException e) {
    // No permission: report "permission denied".
} catch (IOException e) {
    // Other I/O errors.
}
~~~

This is an illustrative snippet with `Path path` declared and Java NIO imports. The first two classes are subtypes of `IOException`, so they must be caught first. Placing `catch(IOException)` at the top makes the catches below unreachable, and Java will refuse to compile.

Each catch needs an **appropriate action**; do not catch multiple types only to print the same message and silently let the program continue as if nothing went wrong.

### 10.2. Rethrowing While Adding Context

A file-handling layer that knows the resource name or current operation can add context:

~~~java
static byte[] readDocument(Path path) throws IOException {
    try {
        return Files.readAllBytes(path);
    } catch (IOException e) {
        throw new IOException("Failed to read document: " + path, e);
    }
}
~~~

This is an illustrative method snippet; not a standalone program. The constructor form `new IOException(message, cause)` preserves the original exception via `getCause()`. Note: if an upper layer needs to distinguish `NoSuchFileException` using `catch`, wrapping every error in a plain `IOException` loses the **specific type at the outer layer**. Therefore, wrap only when crossing an abstraction boundary, or use a strategy that preserves the specific exception type when needed.

Do not wrap and discard the cause:

~~~java
catch (IOException e) {
    throw new RuntimeException("Failed"); // Missing e as cause.
}
~~~

This is an example to avoid: the original stack trace information becomes harder to trace. If an API requires an unchecked exception, use `new UncheckedIOException("...", e)` for `IOException` or a domain exception carrying `cause`.

### 10.3. Checking Logs and Messages

Useful logs should contain the **operation**, a **safely formatted path/destination**, the **exception type**, the **stack trace/cause**, and when relevant the **number of bytes processed**. Avoid logging full sensitive data payloads just for diagnostics.

Example user-facing message: "Unable to save the report file. Please check disk space and folder permissions." Meanwhile, the internal log can retain the full `IOException`. There is no need to expose internal system paths to end users in environments with security requirements.

## 11. Is Retrying Appropriate?

Retrying is only appropriate when the error is **transient** and the operation can be safely repeated. Guideline table:

| Scenario | Auto-retry? | Reason |
| --- | --- | --- |
| `NoSuchFileException` because the user picked a wrong filename | Usually no | Input needs to be fixed or source verified |
| `AccessDeniedException` due to fixed permissions | Usually no | Repeating will not grant new permissions |
| `FileAlreadyExistsException` with `CREATE_NEW` | Should not auto-overwrite | Violates the goal of protecting existing files |
| Temporary network disconnect before transmitting anything | Possible, depending on protocol | Must verify state and retry conditions |
| Append write fails midway | Do not retry the whole payload without deduplication protocol | Can insert duplicate data |
| Reading an unchanged file from the beginning after a transient error | Possible, if source/version is controlled | Cannot assume the file still holds the old content |
| Insufficient disk space | Usually not immediately | Space must be freed or destination changed |

If retrying, you should:

1. Limit the number of attempts and total elapsed time.
2. Include an appropriate delay; for distributed services, exponential backoff and jitter can be used.
3. Define **safety/idempotence conditions**.
4. Record the cause of failed attempts and the final outcome.
5. Do not retry when canceled/stopping, and do not use retries to mask format errors or missing permissions.

For example, if writing a file via a temporary file and replacing the destination, each attempt must create a fresh temporary file or properly handle the previous temporary file's state. When sending data to a server, an idempotency request key or protocol acknowledgment is needed to prevent duplicating work.

## 12. Safer File Writing When Mid-Write Errors Occur

Directly overwriting a destination file carries risk: if the process fails after the file has been truncated but before finishing, the old data is lost and the new data is incomplete.

A common strategy for **a single file**:

1. Create a **separate temporary file** in the same directory/filesystem as the target.
2. Write the entire new content to the temporary file; close the resource and verify postconditions.
3. Only after writing/closing succeeds, attempt to **move the temporary file to the target**.
4. When an atomic rename guarantee is required, request `StandardCopyOption.ATOMIC_MOVE` and handle `AtomicMoveNotSupportedException` instead of silently downgrading when business contracts forbid it.
5. If durability across power loss is required, consider `FileChannel.force`, data/metadata synchronization, and filesystem characteristics; **atomic rename is not synonymous with fsync or a full-system transaction**.
6. If any step fails, report failure and clean up the temporary file using a strategy that preserves error information.

Illustrative move snippet:

~~~java
Files.move(temp, target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
~~~

This snippet uses `Path temp` and `Path target`. `ATOMIC_MOVE` can only be used when supported by the provider, and behavior when the target exists has provider-dependent nuances per the API contract. Do not assume this statement guarantees that all content and metadata are durably written in the event of a power failure.

This is a **design pattern**, not a replacement for database transaction mechanisms or a guarantee of updating multiple files atomically together. Choose a safety level proportional to the criticality of the data.

## 13. Java 17 Example: Copying with try-with-resources and Verifying the Result

Save as **SafeCopyDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class SafeCopyDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("safe-copy-");
        Path source = folder.resolve("source.bin");
        Path target = folder.resolve("target.bin");

        try {
            byte[] original = "Java IO 17".getBytes(
                    StandardCharsets.US_ASCII);
            Files.write(source, original);

            long copied;
            try (InputStream in = Files.newInputStream(source);
                 OutputStream out = Files.newOutputStream(target)) {
                copied = in.transferTo(out);
            }

            byte[] result = Files.readAllBytes(target);
            System.out.println("Copied bytes: " + copied);
            System.out.println("Matches: " +
                    Arrays.equals(original, result));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeCopyDemo.java
java SafeCopyDemo
~~~

Output:

~~~text
Copied bytes: 10
Matches: true
~~~

Key points:

- `transferTo` returns the number of bytes transferred and does not close the streams itself; `try-with-resources` closes `out` then `in`.
- After closing succeeds, the program reads the destination and compares the actual bytes, avoiding the assumption that "calling write" equals "all content completed" if errors occurred.
- The example does not inject an intentional I/O error; if the filesystem forbids creating/deleting/writing in the temp directory, the exception is thrown rather than swallowed.
- The `finally` block in the example only cleans up temporary files. In production systems, if cleanup can also fail when a primary error already exists, design separate reporting or attach suppressed exceptions to preserve the first cause.
- This is a demo copy operation; it **does not** guarantee writing the destination file via an atomic replacement strategy. For critical business content, apply an appropriate temporary-file-and-move workflow.

## 14. FileInputStream/FileOutputStream vs. Files/NIO: Differences in Error Reporting

Legacy Java APIs and NIO can express errors using different types:

~~~java
new FileInputStream("missing.txt");   // Typically FileNotFoundException.
Files.newInputStream(Path.of("missing.txt")); // Typically NoSuchFileException.
~~~

This is an illustrative snippet, not a standalone program. The example filename is assumed not to exist; in practice, environmental conditions determine the outcome. Appropriate imports are required.

`FileNotFoundException` does not necessarily only mean the file is missing; it can also be thrown when opening fails due to permissions or similar causes. When you want to distinguish filesystem reasons, NIO classes such as `NoSuchFileException`, `AccessDeniedException`, `FileAlreadyExistsException`, and `FileSystemException` generally provide clearer handling, though you must not assume every provider always reports the exact same type.

When migrating legacy code to NIO, review your `catch` blocks: if you only catch `FileNotFoundException`, you may miss `NoSuchFileException`. Using `catch(IOException)` at an appropriate layer still handles most checked I/O errors.

## 15. IOException with Text: Charset Errors Are Not Missing Files

Reading a text file involves at least **two logical steps**: fetching bytes from the source and **decoding** those bytes using a charset. If the source contains bytes invalid for the charset and the API/decoder is configured to report errors, `MalformedInputException` (a subtype of `CharacterCodingException` and `IOException`) can be thrown.

Example:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Illustrative snippet with `Path path`. If the file contains invalid UTF-8 data, this read can throw a decoding exception. Do not catch any `IOException` and report "File not found"; the file may exist and be readable at the byte level, yet contain invalid text.

The differences:

- **NoSuchFileException**: resource not found by the filesystem operation.
- **AccessDeniedException**: insufficient access permissions.
- **MalformedInputException**: byte sequence invalid for the charset when using error-reporting decoding.
- **EOFException**: insufficient data for a mandatory field under a formatted read contract.

When using `InputStreamReader` or `CharsetDecoder`, behavior on malformed data also depends on `CodingErrorAction.REPORT`, `REPLACE`, or `IGNORE`. If you need to distinguish data errors, choose the appropriate `REPORT` policy; if using replacement mode, be aware that data may be altered to `�` instead of throwing an error.

Do not use `new String(bytes)` with the default charset when the source specifies UTF-8: reading "garbled characters" is sometimes a charset selection mistake rather than a missing-file or hardware I/O error.

## 16. IOException in Networking and Wrapped Streams

`IOException` can also originate from sockets, compression streams, decoding streams, buffering wrappers, or other I/O sources. With TCP, messages such as "connection reset" or "broken pipe" can appear depending on the OS and timing. Do not rely on a fixed message string to deduce how much data the server actually processed.

Some rules:

- `read() == -1` on a socket stream represents normal end of input under the contract; `IOException` is a failure, not a normal termination.
- A connection can close mid-write; the outcome on the receiving side still requires protocol acknowledgment.
- `flush()` only pushes data out of the buffering layers it manages, which does not mean the remote side has processed the transaction.
- If the API supports timeouts, handle timeouts according to **business state**, rather than blindly retrying by default.
- When wrapping streams (`BufferedInputStream`, `GZIPInputStream`, `InputStreamReader`), closing the outer wrapper normally closes the underlying source. Establish ownership before using `try-with-resources`.

For compressed streams, incomplete data may be detected well after reading begins or only at the end, depending on the format/checksum. Therefore, allow the stream to report errors throughout its entire lifecycle and do not treat a successfully decompressed prefix as proof that the entire payload is valid.

## 17. Designing APIs to Preserve Error Information

A file-reading method typically returns its result in one of two clear ways:

**Approach A — checked exception:**

~~~java
byte[] load(Path source) throws IOException
~~~

The caller catches or propagates `IOException`. This is an illustrative signature, not a complete method.

**Approach B — explicit result:** a result object can hold success/failure status and necessary metadata, suitable when batch-processing many files where one failure should not stop the entire batch. Whichever approach you choose, never return an empty array or empty string to represent both a "valid empty file" and a "failed read".

Example of a practice to avoid:

~~~java
static String readOrEmpty(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        return ""; // Fails to distinguish a truly empty file from a read error.
    }
}
~~~

This is an illustrative method snippet of an **anti-pattern**. It turns an infrastructure failure into fake business data, making debugging and result verification harder.

When catching `IOException` solely to convert it into a domain exception, preserve `cause`. If the caller needs to know the specific error kind, attach a structured error code or let the original exception propagate through the appropriate layer.

## 18. I/O Error Checklist

Before marking an operation complete, check yourself against these questions:

1. **Which source/destination?** File, network, memory, or wrapper? Is resource ownership clear?
2. **Which operation failed?** Open, read, write, flush, or close? Are the stage and context recorded?
3. **What is the exception type?** NoSuchFile, AccessDenied, AlreadyExists, EOFException, CharacterCodingException, or general IOException?
4. **Was partial data processed?** Is that partial data allowed to be used or must it be discarded?
5. **Were resources cleaned up?** Did `try-with-resources` preserve close exceptions as suppressed?
6. **Is EOF confused with an error or vice versa?** `-1` is normal termination of a read-all loop; `EOFException` is different.
7. **Could old data be overwritten accidentally?** Are the open mode and options explicitly specified?
8. **Are postconditions checked?** Size, checksum, content, acknowledgment protocol, or target file state where appropriate?
9. **Is retry safe?** Are there retry limits, idempotency mechanisms, or state-based decisions?
10. **Are logs useful and safe?** Do they include context and stack trace/cause without leaking sensitive data?
11. **Are there durability rules?** If crash/power-loss resilience is needed, have fsync/force and filesystem guarantees been evaluated?
12. **Are error scenarios tested?** Missing file, duplicate file, short read, premature EOF, read failure after partial data, close failure, and charset errors.

## 19. Common Mistakes to Avoid

| Developer Mistake | Consequence | Fix |
| --- | --- | --- |
| Catching `IOException` and returning `""` or empty `byte[]` | Masks failure behind a seemingly valid result | Rethrow or return an explicit error status |
| `catch(IOException)` doing only `printStackTrace()` then continuing as success | Corrupted program state | The handling layer must decide recovery or termination |
| Treating `read() == -1` as an exception | Unnecessary error handling | Use `-1` as normal EOF |
| Treating a mid-stream `IOException` as normal EOF | Accepts truncated data | Report failure status and do not assume complete payload |
| Assuming `read(buffer)` always fills the buffer | Short reads or processing stale data | Always use the returned `count` |
| Using `available() == 0` to terminate reading | Stops prematurely on live streams | Read until `-1` or per protocol |
| Assuming a successful write means fsynced to disk | Overestimates durability | Clarify required durability guarantees |
| Retrying an entire append operation after `IOException` | May duplicate partial data | Retry only when a safe mechanism exists |
| Calling close in `finally` and masking the primary error | Loses the original root cause | Prefer `try-with-resources` |
| Logging only `e.getMessage()` | Missing stack trace/cause/suppressed exceptions | Preserve full exception details |
| Catching `FileNotFoundException` for all NIO APIs | Misses other NIO error types | Catch API-appropriate subtypes or `IOException` |
| Using `Files.exists` to "guarantee" open succeeds | TOCTOU allows conditions to change | Handle exceptions from the actual open call |
| Using `CREATE_NEW` then manually overwriting if it exists | Defeats data-protection intent | Decide an explicit conflict policy |
| Using the wrong charset and reporting "corrupted file" unchecked | Confuses encoding errors with data/file issues | Choose the right charset and check decoder policy |
| Completely hiding cleanup exceptions | Misses impactful cleanup failures | Keep secondary errors as suppressed or log with context |

## 20. Self-Check Exercises

**Exercise 1 — EOF or error?** An `InputStream.read()` loop reads 10 bytes and then returns `-1`. Should `EOFException` be thrown?

**Answer:** No, if the goal is to read the entire stream. EOF is a valid stop condition. If the protocol requires 20 bytes, you must report a missing-data error because insufficient data was received.

**Exercise 2 — Missing file.** Are `new FileInputStream(path)` and `Files.newInputStream(path)` required to throw the exact same subtype?

**Answer:** No. The legacy API typically throws `FileNotFoundException`; NIO typically throws `NoSuchFileException`. Choose catch blocks matching the actual API and still keep a general `IOException` handling path.

**Exercise 3 — After a write fails, can you automatically rewrite the entire payload?**

**Answer:** Not by default. Part of the payload may have already been sent or saved, and rewriting from the start can cause duplication. You need an idempotent/offset/ack protocol or a safe replacement workflow.

**Exercise 4 — Two errors at once.** In `try-with-resources`, the body throws `IOException("read failed")` and close throws `IOException("close failed")`. Which is the primary exception?

**Answer:** `read failed` is the primary error; `close failed` is placed in `getSuppressed()`, as shown in `SuppressedExceptionDemo`.

**Exercise 5 — Reading UTF-8.** A file exists and is readable, but its internal bytes do not form valid UTF-8 text. Why do you still get an `IOException`?

**Answer:** The error occurs during the **character decoding** step, such as `MalformedInputException` under the REPORT policy, rather than during file opening. Do not misreport this as "file does not exist".

**Exercise 6 — Is a successful write enough to guarantee durable data?**

**Answer:** Not sufficient for all requirements. `write`, `flush`, `close`, and physical data synchronization have different contracts; if the system requires durability across power loss, design specifically for it and examine filesystem/device guarantees.

### Advanced Practice Exercises

1. Modify `OpenFileFailuresDemo` to also catch general `IOException` and print the **exception class name** if thrown, without classifying by message strings.
2. Add `FileAlreadyExistsException` handling to a report-generation program: if the destination already exists, the application must stop with a clear message without deleting or overwriting it.
3. Write a test `InputStream` that throws `IOException` at the Nth byte and verify the result is marked **failed**, not successful with a truncated payload.
4. Add a second resource that also fails on `close()` to `SuppressedExceptionDemo`; verify the reverse closing order and the suppressed list.
5. Design pseudocode for "write temp file -> verify -> move to target" including a branch for when `ATOMIC_MOVE` is unsupported, an error-cleanup branch, and rules to avoid losing existing data.

## Conclusion

`IOException` does not just mean "file not found": it can occur during **open, read, write, flush, or close**, with each stage carrying a distinct kind of risk. A reliable Java I/O application must:

- Distinguish **normal EOF** from **missing mandatory data** and **genuine read errors**.
- Catch specific subclasses where helpful, while preserving a general `IOException` path and the root cause.
- Use `try-with-resources` to close resources and inspect `getSuppressed()` when multiple errors occur.
- Never silently turn failure into an empty result; never blindly retry writes because output may have been partially written.
- Establish clear policies on overwriting, appending, temporary data, postconditions, durability, and failure safety.

### Java SE 17 Documentation

- [IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html)
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [FileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html)
- [NoSuchFileException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html)
- [AccessDeniedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AccessDeniedException.html)
- [FileAlreadyExistsException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileAlreadyExistsException.html)
- [Throwable.getSuppressed()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed())
- [Java try-with-resources — Oracle Tutorial](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html)
