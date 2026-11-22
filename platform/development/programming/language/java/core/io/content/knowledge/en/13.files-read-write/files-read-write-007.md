# READ, WRITE, CREATE, CREATE_NEW, and TRUNCATE_EXISTING in Java Files I/O

> **Context:** Java Core → I/O → **Files Read and Write**. This lesson explains the key `StandardOpenOption` values when opening files, the differences between reading and writing, creating new files with or without overwriting, truncating existing file content, and the **defaults** of `Files`. Standalone examples use Java 17, creating and cleaning up temporary files so real data is untouched.

## 1. Why Do File Open Modes Matter?

A single "write a file" requirement can have completely different meanings:

- Write only to an **existing file**, without erasing the remaining tail.
- Create the file if missing and write; if it already exists, overwrite from the beginning.
- Create the file if missing, but **strictly fail** if the path already exists.
- Open an existing file and **clear it before writing**.
- Read data only, with **no** write permission and without modifying content.

In Java NIO.2, these choices are represented by `java.nio.file.StandardOpenOption`, an enum implementing the `OpenOption` interface. They are typically passed as varargs arguments to `Files.newInputStream`, `Files.newOutputStream`, `Files.write`, `Files.writeString`, and channel-opening APIs. Each API has its **own contract**: not every option is valid everywhere, and **defaults when options are omitted can differ**.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("data.txt");
// This is just a fragment; the following must be inside a method that handles IOException.
// Files.writeString(path, "hello",
//         StandardOpenOption.CREATE, StandardOpenOption.WRITE);
~~~

`Path.of(...)` only creates a path identifier object; `Files.writeString(...)` actually performs I/O. Most write operations can modify data permanently, so you must decide the open mode **before** operating.

### 1.1. The Five Core Options

| Option | Meaning when used in the right context | What it does **NOT** mean |
| --- | --- | --- |
| `READ` | Opens **read** access to the file's bytes | Does not create a missing file, does not grant write access. |
| `WRITE` | Opens **write** access to the file's bytes | Does not create the file or clear its content without corresponding options. |
| `CREATE` | **If missing**, creates the file; **if present**, opens that existing file | Does not forbid overwriting and does not mean truncate. |
| `CREATE_NEW` | Creates a **new** file only; if target already exists, opening fails | Not "overwrite file with new content"; does not allow replacing an existing name. |
| `TRUNCATE_EXISTING` | When opening an existing file **for writing**, sets length to **0** upon opening | Does not delete the file from the directory, is not for appending, and is ignored on READ-only open. |

**Memory aid:** `WRITE` answers "may bytes be modified?", `CREATE` answers "if missing, may it be created?", `CREATE_NEW` answers "if it already exists, must it fail?", and `TRUNCATE_EXISTING` answers "if it already exists, should it be cleared upon opening?". `READ` controls read capability and can accompany `WRITE` on channel APIs supporting both directions.

## 2. `READ` — Reading Data Only

Opening a standard input stream:

~~~java
// Fragment inside a method that throws IOException:
try (InputStream in = Files.newInputStream(path)) {
    int firstByte = in.read();
}
~~~

You must import `java.io.InputStream`, `java.nio.file.Files`, and `java.nio.file.Path`. Passing no options to `Files.newInputStream(path)` means **open for reading**. You can also write `Files.newInputStream(path, StandardOpenOption.READ)`. If the file does not exist, you typically get `NoSuchFileException`; if read permission is missing or another error occurs, you get an appropriate `IOException`.

`READ` **does not create a file**. Do not expect `Files.newInputStream(path, CREATE)` to mean "open for reading, and create an empty file if missing"; the input-stream factory has no such semantics. Options unsupported by the API can throw `UnsupportedOperationException`, and invalid combinations can throw `IllegalArgumentException`.

When reading text with an explicit charset:

~~~java
// Java 11+ fragment: method throws IOException.
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

`Files.readString` opens/reads/closes the file internally and does not accept arbitrary `StandardOpenOption...` arguments. To open with fine-grained modes, choose a stream/channel-opening API accepting options.

### 2.1. `READ` Does Not Modify the File

At the `SeekableByteChannel` or `FileChannel` layer, a channel opened **READ-only** does not allow writing; calling `write` can throw `NonWritableChannelException`. `TRUNCATE_EXISTING` is **ignored when opening READ-only** per the channel contract. That does not mean you can use `READ+TRUNCATE` to wipe a file; no content is erased if the channel is read-only.

## 3. `WRITE` — Allows Writing, Does Not Implicitly Create or Truncate

Example opening only for writing an **already-existing** file:

~~~java
// Fragment; method throws IOException.
try (OutputStream out = Files.newOutputStream(
        path, StandardOpenOption.WRITE)) {
    out.write("XY".getBytes(StandardCharsets.UTF_8));
}
~~~

Import `java.io.OutputStream` and `java.nio.charset.StandardCharsets`. If the file initially holds ASCII `ABCDE`, writing `XY` from the start **without** truncating can leave `XYCDE`. The same principle applies to `FileChannel`: when opened normally, the write position starts at the beginning of the file, **not automatically at the end**.

Things to remember:

- `WRITE` **is not equivalent to** `CREATE`: if the file is missing and creation is not requested, opening for write can fail with `NoSuchFileException`.
- `WRITE` **is not equivalent to** `TRUNCATE_EXISTING`: if you write fewer bytes than the old content, the old remainder **can stay behind**.
- `WRITE` **does not mean append**: to write at the end of a file, use `APPEND` in APIs that support it or position the channel explicitly. `APPEND` has its own combination rules.
- The length of a single `write` call **does not guarantee** everything was written in channel APIs: `SeekableByteChannel.write(ByteBuffer)` may write fewer bytes than requested; with channels, loop until `ByteBuffer.hasRemaining() == false`. `OutputStream.write(byte[])` normally writes all bytes of the array or throws `IOException`.
- `WRITE` does not choose text charsets. With `byte[]`, the caller encodes; with `Files.writeString`, you specify the charset or use that API's default.

## 4. `CREATE` — Create if Missing, Use Existing File if Present

`CREATE` commonly accompanies `WRITE`:

~~~java
// Fragment: create missing file, or write from start of existing file.
try (OutputStream out = Files.newOutputStream(
        path, StandardOpenOption.CREATE,
        StandardOpenOption.WRITE)) {
    out.write("hi".getBytes(StandardCharsets.UTF_8));
}
~~~

If the file does not exist and permissions allow, it is created. If the file already exists, it is opened for writing. **`CREATE` and `WRITE` alone do not trigger truncation**; when writing fewer bytes than the existing content, the old tail may remain just like the `XYCDE` example.

`CREATE` does not make parent directories appear automatically: if `path` is `logs/2026/app.log` and `logs/2026` does not exist, file creation can still fail. When the application is responsible for creating directories, call `Files.createDirectories(path.getParent())` after checking that the parent is non-null and validating path policies.

**When to choose it?** An application periodically writing to a fixed file **allowed to already exist** can choose `CREATE + WRITE + TRUNCATE_EXISTING` when replacing the entire content. To preserve existing content and add records, use `CREATE + APPEND` per the API contract. If duplicate names are **forbidden**, use `CREATE_NEW` instead of `CREATE`.

## 5. `CREATE_NEW` — Exclusive Creation and Atomic Existence Check

`CREATE_NEW` is used when you **must not overwrite any existing entry** at the target name:

~~~java
// Fragment: method throws IOException.
Files.writeString(
        path, "new-data", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
~~~

If the target name already exists, including when that entry is a **symbolic link**, opening with `CREATE_NEW` must fail. You typically receive `FileAlreadyExistsException`, though the Javadoc allows an appropriate `IOException` depending on provider; do not catch every `IOException` and assume it means "file already exists".

**Why is `CREATE_NEW` better than `if (!Files.exists(path)) ...`?** Because checking existence and then creating are **two operations** with a race window between them. `CREATE_NEW` puts "create only if it does not exist" into a single open/create operation whose check-and-create step is **atomic with respect to other filesystem operations** per contract.

~~~java
// RACE-PRONE ANTI-PATTERN; do not use as a no-overwrite guarantee.
if (!Files.exists(path)) {
    Files.writeString(path, content);
    // The target name can be created by another thread/process between these two lines.
}
~~~

Replace with:

~~~java
// Fragment: content is a String prepared by the caller.
try {
    Files.writeString(
        path, content, StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
} catch (FileAlreadyExistsException ex) {
    // Business rule: report duplicate name, rename, or reject request.
}
~~~

These snippets require importing `java.nio.file.FileAlreadyExistsException`, `java.nio.file.Files`, and related types. If a provider does not use the exact `FileAlreadyExistsException` subclass here, you still must handle `IOException` at the I/O boundary.

### 5.1. Atomic Creation Is Not Atomic Content Replacement

`CREATE_NEW` only guarantees that the **name check and new entry creation** are atomic per contract. It does **not** guarantee all subsequent written data appears simultaneously, is crash-safe, fsyncs, or forms a transaction. An exception after creating the file can leave the file **already existing with only partial data**. For critical data, design cleanup for failed new files and a protocol to publish complete content.

### 5.2. Combining `CREATE` and `CREATE_NEW`?

When both are present, `CREATE_NEW` **takes precedence** and `CREATE` is ignored per API. It does not mean "create new or overwrite if present": an existing path still fails. Writing only `CREATE_NEW` makes intent clearer.

## 6. `TRUNCATE_EXISTING` — Clearing Old Content Before Writing

`TRUNCATE_EXISTING` is used with write access to set an existing file's length to **0 bytes upon opening**:

~~~java
// Fragment: replace content of an existing file, disallow creating a missing file.
try (OutputStream out = Files.newOutputStream(
        path, StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    out.write("OK".getBytes(StandardCharsets.UTF_8));
}
~~~

If the file previously held `ABCDE`, after the operation succeeds the content is `OK`, not `OKCDE`. If the file does not exist, omitting `CREATE` or `CREATE_NEW` can lead to `NoSuchFileException`.

Common combination to **create if absent, replace entirely if present**:

~~~java
Files.writeString(
    path, "full replacement", StandardCharsets.UTF_8,
    StandardOpenOption.CREATE,
    StandardOpenOption.WRITE,
    StandardOpenOption.TRUNCATE_EXISTING);
~~~

**Major risk:** truncation occurs **at open time**, before you have finished writing the new data. If reading the source fails, the process terminates, disk space runs out, or the writer fails, the old data **may already be lost**. Therefore, `CREATE+TRUNCATE_EXISTING` is not a completely safe update mechanism for critical files.

**`TRUNCATE_EXISTING` is not DELETE:** the filename and directory entry still exist; only size/contents change. When opening read-only with a channel, this option is **ignored**; never expect `READ + TRUNCATE_EXISTING` to shrink a file.

## 7. Scenario Matrix by Business Intent

Assume the target is a regular file on a provider supporting standard options, with no permission conflicts or other I/O errors.

| Intent | Example API and options | If file is missing | If file exists |
| --- | --- | --- | --- |
| Read only | `Files.newInputStream(path, READ)` | Fails | Reads, does not write |
| Overwrite from start **without erasing tail** | `newOutputStream(path, WRITE)` | Fails | Writes from start; remainder may stay |
| Create if missing, write from start without default truncate | `newOutputStream(path, CREATE, WRITE)` | Creates new | Overwrites from start, tail may stay |
| Create new name only, prevent collisions | `newOutputStream(path, CREATE_NEW, WRITE)` | Creates new | Fails |
| Fully overwrite existing file only | `newOutputStream(path, WRITE, TRUNCATE_EXISTING)` | Fails | Resets size to 0 before writing |
| Create if missing or replace content if present | `newOutputStream(path, CREATE, WRITE, TRUNCATE_EXISTING)` | Creates new | Truncates then writes |
| Read and write via one channel | `newByteChannel(path, EnumSet.of(READ,WRITE))` | Fails | Can read/write, does not auto-truncate |
| Concise default write | `Files.writeString(path, text, UTF_8)` | Creates new | Truncates then writes |
| Append content to end | `Files.writeString(path, text, UTF_8, WRITE, APPEND)` | Fails without CREATE | Keeps old data then appends |

**Note:** the last row uses `APPEND` for comparison, rather than one of the five main options. When you want "append, and create if missing", pass `CREATE` as well. An `APPEND` call across multiple processes/threads **does not guarantee** every party's multi-part message is an atomic unit; check the provider contract and coordinate accordingly.

### 7.1. Combinations Worth Remembering

- `CREATE_NEW + WRITE`: create new only; fail if present. No need to add `TRUNCATE_EXISTING` since a brand-new file has no content.
- `CREATE + WRITE + TRUNCATE_EXISTING`: common "create-or-replace" pattern, yet **unsafe on partial write failure**.
- `WRITE` **alone**: opens only an existing file for writing, without auto-truncating.
- `READ + WRITE`: normally used with `FileChannel` or `SeekableByteChannel`, **not** for `Files.newInputStream` or `newOutputStream`.
- `READ + TRUNCATE_EXISTING` (read-only channel): truncate is ignored.
- `APPEND + TRUNCATE_EXISTING`: invalid combination on standard channels.
- `APPEND + READ`: invalid combination on standard channels.
- `CREATE + CREATE_NEW`: `CREATE_NEW` wins, `CREATE` is ignored.
- `CREATE`/`CREATE_NEW` in a **read-only** `newByteChannel` context: ignored per contract; does not create a file just for reading.

## 8. Important Defaults in `Files`

A major cause of accidental data loss is that defaults **vary by method**. Do not read `Files` and assume all methods share the same defaults.

| Method | When no options are passed | Who closes the resource? |
| --- | --- | --- |
| `Files.newInputStream(path)` | Opens for **READ** | Caller closes `InputStream`, usually in try-with-resources |
| `Files.newOutputStream(path)` | **CREATE + TRUNCATE_EXISTING + WRITE** | Caller closes `OutputStream` |
| `Files.write(path, bytes)` | **CREATE + TRUNCATE_EXISTING + WRITE** | API closes internal stream |
| `Files.writeString(path, text)` (Java 11+) | **CREATE + TRUNCATE_EXISTING + WRITE** | API closes internal stream/writer |
| `Files.write(path, lines, charset)` | Default **CREATE + TRUNCATE_EXISTING + WRITE** | API closes internally |
| `Files.newByteChannel(path)` | **READ** if none of READ/WRITE/APPEND | Caller closes channel |
| `FileChannel.open(path)` | Per `FileChannel.open` rules: default **READ** | Caller closes `FileChannel` |

**Crucial note:** When you **pass an explicit list of options**, the **defaults for the no-options call are NOT automatically added**. For example, if old code called `Files.writeString(path, text)` and you change it to `Files.writeString(path, text, UTF_8, WRITE)`, you have specified **WRITE**, no longer requesting creation or truncation as in the default call. If the existing file holds longer content, the result can be completely different.

Text-processing APIs use different overloads: for instance, `Files.writeString(path, text, charset, options...)` is valid since Java 11; `Files.write(path, byte[], options...)` accepts a byte array; line-writing overloads accept a charset and an iterable. When you only need one-way byte reading, do not accidentally open an output stream just to "access the file".

## 9. Complete Example 1: Observing `READ`, `WRITE`, `CREATE_NEW`, `TRUNCATE_EXISTING`

Save as **`FileOpenModesDemo.java`**:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileOpenModesDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("open-options-");
        Path file = dir.resolve("sample.txt");
        try {
            // READ does not create a missing file.
            try (InputStream in = Files.newInputStream(
                    file, StandardOpenOption.READ)) {
                in.read();
            } catch (NoSuchFileException expected) {
                System.out.println("readMissing=true");
            }

            // CREATE_NEW: create only if absent, and do not overwrite.
            Files.writeString(
                    file, "ABCDE", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            try {
                Files.writeString(
                        file, "FAIL", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);
            } catch (FileAlreadyExistsException expected) {
                System.out.println("exclusiveCreate=true");
            }

            // WRITE does not include truncate when options are specified explicitly.
            try (OutputStream out = Files.newOutputStream(
                    file, StandardOpenOption.WRITE)) {
                out.write("XY".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("afterWriteOnly="
                    + Files.readString(file, StandardCharsets.UTF_8));

            // TRUNCATE_EXISTING truncates the file before writing.
            Files.writeString(
                    file, "OK", StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);
            System.out.println("afterTruncate="
                    + Files.readString(file, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac --release 17 FileOpenModesDemo.java
java FileOpenModesDemo
~~~

**Verified stdout:**

~~~text
readMissing=true
exclusiveCreate=true
afterWriteOnly=XYCDE
afterTruncate=OK
~~~

**Analysis:**

1. The file is not created beforehand, so `newInputStream(READ)` throws `NoSuchFileException`.
2. `CREATE_NEW+WRITE` creates the file with `ABCDE` on the first call; the second call fails without writing `FAIL` to the file.
3. `newOutputStream(WRITE)` starts from offset 0 and writes two bytes `XY`. The file originally had 5 bytes; without truncation, `CDE` remains at the end.
4. `WRITE+TRUNCATE_EXISTING` resets the file length to 0 upon open and writes `OK`, so the result is just `OK`.
5. Temporary file and directory are cleaned up in `finally`. This demo uses a fresh temporary file and touches no user files.

This example uses ASCII so byte counts are easy to visualize. If replaced with UTF-8 Unicode text, the **written length** depends on encoded byte count, not `String.length()`. Writing bytes in the middle of a multi-byte UTF-8 sequence can produce invalid text; avoid modifying arbitrary byte offsets inside text files.

## 10. Complete Example 2: Defaults of `Files.writeString` and `newOutputStream`

Save as **`DefaultOpenOptionsDemo.java`**:

~~~java
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class DefaultOpenOptionsDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("default-write-", ".txt");
        try {
            Files.writeString(file, "long-data", StandardCharsets.UTF_8);

            // No options: CREATE + TRUNCATE_EXISTING + WRITE.
            Files.writeString(file, "hi", StandardCharsets.UTF_8);
            System.out.println("defaultWrite="
                    + Files.readString(file, StandardCharsets.UTF_8));

            // OutputStream without options also truncates an existing file.
            try (OutputStream out = Files.newOutputStream(file)) {
                out.write("OK".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("defaultOutput="
                    + Files.readString(file, StandardCharsets.UTF_8));

            // APPEND is specified; do not use TRUNCATE_EXISTING.
            Files.writeString(
                    file, "!", StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND);
            System.out.println("appended="
                    + Files.readString(file, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac --release 17 DefaultOpenOptionsDemo.java
java DefaultOpenOptionsDemo
~~~

**Verified stdout:**

~~~text
defaultWrite=hi
defaultOutput=OK
appended=OK!
~~~

Notice `Files.writeString(file, "hi", UTF_8)` does not keep the `ng-data` tail of the old content: **the default is truncate**. `Files.newOutputStream(file)` behaves the same way. Finally, `WRITE+APPEND` appends `!` to the existing file; if you also want it to work when the file does not exist yet, consider adding `CREATE`.

**Do not confuse** the default of `Files.writeString` with `Files.newByteChannel`: no options on a channel normally means **READ**, not `CREATE+TRUNCATE+WRITE`. Use the table in section 8 as a lookup when switching APIs.

## 11. `READ + WRITE` on a Channel: One Bidirectional Handle

`Files.newByteChannel` accepts a set of `OpenOption`s and returns a `SeekableByteChannel`, which can read/write and seek if opened with both permissions:

~~~java
try (SeekableByteChannel channel = Files.newByteChannel(
        path, EnumSet.of(StandardOpenOption.READ,
                         StandardOpenOption.WRITE))) {
    // Read bytes using channel.read(ByteBuffer).
    // Write bytes using channel.write(ByteBuffer).
    // channel.position(...) to adjust offset.
}
~~~

This is a **fragment**; import `java.nio.channels.SeekableByteChannel`, `java.util.EnumSet`, and `IOException`. `FileChannel.open(path, READ, WRITE)` is another option when `FileChannel`-specific APIs are needed. Do not confuse read+write access with "read then append at the end": the channel position is maintained, advances with reads/writes, and can be set via `position(long)`.

### 11.1. Complete Example 3: A Channel Reading and Writing Without Truncating

Save as **`FileChannelOptionsDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.EnumSet;

public class FileChannelOptionsDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("open-channel-", ".txt");
        try {
            Files.writeString(file, "ABCDE", StandardCharsets.UTF_8);

            try (SeekableByteChannel channel = Files.newByteChannel(
                    file, EnumSet.of(
                            StandardOpenOption.READ,
                            StandardOpenOption.WRITE))) {

                ByteBuffer buffer = ByteBuffer.allocate(2);
                channel.read(buffer);
                buffer.flip();
                System.out.println("prefix="
                        + StandardCharsets.UTF_8.decode(buffer));

                channel.position(2);
                channel.write(ByteBuffer.wrap(
                        "zz".getBytes(StandardCharsets.UTF_8)));
            }

            System.out.println("readWrite="
                    + Files.readString(file, StandardCharsets.UTF_8));

            // TRUNCATE_EXISTING is ignored on a READ-only channel.
            try (SeekableByteChannel channel = Files.newByteChannel(
                    file, EnumSet.of(
                            StandardOpenOption.READ,
                            StandardOpenOption.TRUNCATE_EXISTING))) {
                System.out.println("readOnlySize=" + channel.size());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac --release 17 FileChannelOptionsDemo.java
java FileChannelOptionsDemo
~~~

**Verified stdout:**

~~~text
prefix=AB
readWrite=ABzzE
readOnlySize=5
~~~

Separate the meaning of each step: the channel reads 2 bytes `AB`; `position(2)` moves the offset to the third byte (zero-based); writing `zz` overwrites `CD` without truncating, preserving `E`. When opened with `READ+TRUNCATE_EXISTING` only, truncate is ignored per the channel contract, so size remains 5.

For a buffer that may require multiple writes, production code must loop:

~~~java
// Fragment: channel is open for WRITE and buffer has data.
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
~~~

If a channel is non-blocking in another system, check progress contracts when 0 is returned; for standard file channels, this is the pattern to handle partial writes. The demo above uses 2 bytes of data and was verified in a test environment; do not generalize "a single write always writes everything" to all channels.

## 12. `READ`, `WRITE`, `APPEND`, and Invalid Combinations

Combining more options is not stronger. Each factory validates legal combinations.

| Combination | Verdict |
| --- | --- |
| `READ + WRITE` with `newByteChannel` / `FileChannel.open` | Valid for bidirectional use if supported by provider. |
| `READ` with `Files.newInputStream` | Valid; this is the proper read permission for the API. |
| `READ` with `Files.newOutputStream` | **Invalid** per output-stream factory contract. |
| `WRITE` with `Files.newInputStream` | Not a standard input mode supported by this API. |
| `CREATE + WRITE` | Allows creating missing file, while existing file is not auto-truncated. |
| `CREATE_NEW + WRITE` | Creates if absent; rejects duplicate names. |
| `CREATE + CREATE_NEW + WRITE` | `CREATE_NEW` takes effect, `CREATE` is ignored. |
| `APPEND + TRUNCATE_EXISTING` with channel | **Invalid** because it asks to keep content to append while also wiping it. |
| `READ + APPEND` with channel | **Invalid** per `newByteChannel`/`FileChannel` contract. |
| `TRUNCATE_EXISTING + READ` (no WRITE) with channel | Truncate is **ignored**. |
| `CREATE/CREATE_NEW + READ` (no WRITE/APPEND) with channel | Creation option is **ignored** because opening is read-only. |

**Exceptions and limitations:** Invalid combinations can throw `IllegalArgumentException`; options unsupported by the provider/API can throw `UnsupportedOperationException`; file/permission/I/O issues typically throw `IOException`. Details per API are documented in Javadoc; do not rely on one single exception across all providers.

### 12.1. `Files.newOutputStream` Is Not Necessarily Buffered

The `Files.newOutputStream` Javadoc notes that the returned stream **is not buffered** by this method. For many small writes, wrap it:

~~~java
// Fragment: method throws IOException; use a single owner for the stream.
try (OutputStream out = new BufferedOutputStream(
        Files.newOutputStream(
                path, StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING))) {
    // Write multiple bytes to out...
}
~~~

Import `java.io.BufferedOutputStream` and `java.io.OutputStream`. Closing the outer buffered stream closes the inner stream. However, buffering **does not** alter file-open semantics: `TRUNCATE_EXISTING` still takes effect **at open time**, not after the buffer finishes writing.

## 13. Principles to Prevent Data Loss When Replacing an Entire File

Using `TRUNCATE_EXISTING` directly on the real file suits cases where business logic **tolerates** an empty or partial result after a write failure (e.g., an easily regenerated cache file). For configs, records, or critical data, you usually should not overwrite in place and assume writing is an atomic transaction.

A common strategy:

1. Create a **new temporary file** in the same directory/volume as the target whenever possible.
2. Write all new data to the temporary file, using `CREATE_NEW` or `Files.createTempFile` to avoid colliding with pre-existing names.
3. Close the output (and apply durability mechanisms when required).
4. Try moving the temporary file to the target name via `Files.move` with `ATOMIC_MOVE` if supported by the provider/filesystem.
5. If the filesystem does not support atomic move, decide whether to fall back (potentially losing atomicity) or reject the operation; never silently claim it is "atomic".
6. Clean up the temporary file on failure; enforce permissions, race protections, symbolic-link checks, and overwrite conditions per business requirements.

**Caution:** `Files.move(..., ATOMIC_MOVE)` has rules around other options and existing targets that depend on the provider/implementation; do not treat `ATOMIC_MOVE + REPLACE_EXISTING` as a portable promise that replacing an existing target always succeeds atomically. Furthermore, **atomic rename differs from durable write**: renamed data may still need sync and filesystem/OS-level measures if power-loss protection is required.

### 13.1. `CREATE_NEW` Still Requires Path Security Handling

`CREATE_NEW` blocks overwriting an existing **final path entry**, including a symlink at the final name. However, it does not neutralize symbolic links in parent directories, lock root access, or stop other actors from altering the directory tree. For user-supplied filenames, enforce policies checking relative paths, `..` traversal, symlinks, permissions, and races; do not treat `CREATE_NEW` as a complete sandbox.

## 14. Writing Text vs. Writing Bytes

Open options describe **how to open the file**, independent of how content is encoded.

~~~java
// Two equivalent ways to write the UTF-8 bytes of this string.
byte[] data = "Xin chào".getBytes(StandardCharsets.UTF_8);

Files.write(path, data,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING);

Files.writeString(path, "Xin chào", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING);
~~~

This is a **fragment** where both calls run sequentially; the second overwrites with the same content. Key points:

- `StandardCharsets.UTF_8` ensures an explicit charset; `String.length()` counts UTF-16 code units, not UTF-8 file size.
- The `WRITE/CREATE/TRUNCATE_EXISTING` flags do not choose charsets, convert newlines, or guarantee valid UTF-8 if you manipulate file bytes yourself.
- For large file I/O, do not assume `Files.readAllBytes`/`readString` is a good choice when line/chunk processing is needed. Use buffered readers/streams and manage resource closing for large data.
- Use `Files.writeString(..., Charset, OpenOption...)` from Java 11; in Java 8 you can use `Files.write(path, byte[], OpenOption...)` or `Files.newBufferedWriter(path, charset, options...)`.

### 14.1. Do Not Assume Every File System Supports All Options

In ZIPFS, network mounts, cloud-mounted filesystems, or custom providers, some options may be unsupported, and exact behavior or exception types may differ. The examples focus on the default provider supporting standard `StandardOpenOption` values. Portable APIs must anticipate `UnsupportedOperationException`, `IOException`, and constraints like read-only filesystems; test required options in the deployment environment.

## 15. Proper Exception Handling and Cleanup

When opening/writing files, errors should be distinguished so appropriate messages are returned:

| Scenario | Common error type | Reasonable response |
| --- | --- | --- |
| File missing when only READ/WRITE | `NoSuchFileException` | Report missing path or switch to a flow allowed to create, if valid |
| `CREATE_NEW` encounters existing name | `FileAlreadyExistsException` (typically) | Do not auto-overwrite; handle collision per business rules |
| Insufficient permissions or access denied | `AccessDeniedException`/`IOException` | Report access error; do not escalate permissions automatically |
| Parent directory does not exist | `NoSuchFileException`/`IOException` | Check parent; create directories if policy allows |
| Invalid option combination | `IllegalArgumentException` | Fix programming bug; do not retry indefinitely |
| Provider does not support option | `UnsupportedOperationException` | Choose an alternative strategy suited to the provider |
| Out of space, disk failure, write interrupted | `IOException` | Recognize file may have been created/truncated/partially written; clean up and report error |
| Error during `close()` | `IOException` or resource-specific type | Preserve error info, handle suppressed exceptions |

Skeleton for opening output and closing along all exit paths:

~~~java
// Fragment: method throws IOException.
try (OutputStream out = Files.newOutputStream(
        path, StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    out.write(data); // data prepared by caller.
}
~~~

If an error happens **after the file has already been opened**, `try-with-resources` still calls `close()`, but does not undo written data or truncation. Exceptions raised during `close()` may appear as suppressed exceptions if the body already threw an exception. **Do not** infer "close ran means the write completed safely".

## 16. Quick Decision Model for a File-Writing API

~~~text
Need READ ONLY?
  └── Yes: Files.newInputStream(path) or Files.readString(path, charset)
           Does NOT auto-CREATE.

Need to write a file?
  ├── Must NOT touch an already-existing name
  │     └── CREATE_NEW + WRITE
  ├── Existing file only, want to preserve unwritten trailing data
  │     └── WRITE
  ├── Existing file only, want to clear before writing
  │     └── WRITE + TRUNCATE_EXISTING
  ├── Create if missing, clear and rewrite if present
  │     └── CREATE + WRITE + TRUNCATE_EXISTING
  └── Create if missing, append at end if present
        └── CREATE + APPEND (+ WRITE per API / for clarity)

Need READ and WRITE on the same handle?
  └── Files.newByteChannel(path, EnumSet.of(READ, WRITE))
      or FileChannel.open(path, READ, WRITE).
~~~

**Reminder:** if the file is critical and needs whole-file replacement, a temp-file -> close -> move workflow may be far better than direct `TRUNCATE_EXISTING`. Do not rely on `Files.exists` before `Files.write` to emulate `CREATE_NEW`.

## 17. Common Mistakes When Learning or Reviewing Code

1. **"`WRITE` creates the file automatically."** Wrong: without a creation option, a missing file can fail.
2. **"`WRITE` automatically removes the old tail."** Wrong: clearing old length requires `TRUNCATE_EXISTING` when opening for write.
3. **"`CREATE` only creates a new file."** Wrong: if the file already exists it opens it; it does not prevent overwriting.
4. **"`CREATE_NEW` overwrites the file with new content."** Wrong: if the name exists, it fails.
5. **"`CREATE_NEW` guarantees atomic file writing."** It is only atomic at the name-check/creation step, not for writing all data.
6. **"`TRUNCATE_EXISTING` only takes effect if writing succeeds."** Wrong: truncation happens at open time before writing.
7. **"`TRUNCATE_EXISTING` deletes the file from the directory."** Wrong: it sets length to 0; the file entry remains.
8. **"`READ+WRITE` works on unidirectional InputStream/OutputStream."** Wrong: choose a bidirectional channel.
9. **"Omitting options in every API means READ."** Wrong: `newOutputStream`/`Files.write*` default to `CREATE+TRUNCATE+WRITE`, whereas `newByteChannel` defaults to `READ`.
10. **"Adding `WRITE` to `Files.writeString` has no effect."** It can have an effect: custom options do not inherit default `CREATE`/`TRUNCATE`.
11. **"`Files.exists` followed by `Files.writeString` prevents races."** Wrong: two separate operations are not atomic.
12. **"Combining `APPEND+TRUNCATE_EXISTING` writes then keeps the tail."** Wrong: invalid for standard channels.
13. **"`CREATE+CREATE_NEW` gives priority to CREATE."** Wrong: `CREATE_NEW` takes precedence.
14. **"Passing `TRUNCATE_EXISTING` on pure READ deletes the file."** Wrong: ignored on read-only channels.
15. **"Opening `Files.newOutputStream` without options preserves the old file."** Not the default of `Files.newOutputStream`: it truncates.
16. **"Using `WRITE` and writing a shorter string automatically shrinks the file."** Wrong; old trailing bytes can remain.
17. **"All `Files` APIs returning streams close themselves."** Wrong: methods returning `InputStream`/`OutputStream`/`Channel` for the caller require the caller to close; `Files.writeString` manages itself.
18. **"With `try-with-resources`, data can never be lost."** Wrong: `try` guarantees calling `close()`, not rolling back truncation/partial writes.
19. **"ZIP files or other providers always support all `StandardOpenOption`s."** Not guaranteed; depends on the provider.
20. **"Writing bytes at arbitrary offsets in UTF-8 always preserves valid text."** Wrong: it can split a multi-byte sequence.
21. **"Using `TRUNCATE_EXISTING` makes updates crash-safe."** Wrong: use proper temp file / atomic move / durability design.
22. **"`APPEND` is the same as default `WRITE`."** Wrong: `APPEND` targets the end of the file, while plain `WRITE` normally starts at the beginning.

## 18. Self-Check Exercises

1. File `A.txt` contains `12345678`. `Files.newOutputStream(path, WRITE)` writes two bytes `XY`. What is the expected content?
2. Similarly, add `TRUNCATE_EXISTING` and write `XY`. How does it differ?
3. To **create only a new** uploaded file and reject duplicate names, which option do you choose? Why isn't `if (!exists)` enough?
4. To operate on an existing file while **forbidding creating a new one**, which options must you omit?
5. What does `Files.writeString(file, "A")` with no options do if the file contains `ABCDEFG`?
6. When explicitly adding `StandardOpenOption.WRITE` to `Files.writeString(file, "A", UTF_8, WRITE)`, are default `CREATE` and `TRUNCATE` still implied?
7. If you open `Files.newByteChannel(file, EnumSet.of(READ, WRITE))`, can you read and write using the same handle?
8. Can you request `READ + APPEND` on a standard channel?
9. What does `READ + TRUNCATE_EXISTING` on a read-only channel do to file size?
10. Does `CREATE_NEW` guarantee the entire file is written completely if power fails mid-write?
11. Does `CREATE_NEW` turn a path with a symbolic link in a **parent directory** into a sandbox automatically?
12. Why must `Files.newOutputStream` be closed with try-with-resources whereas `Files.writeString` returns no output stream for the caller to close?
13. If parent directories are missing, does `CREATE` create all directories automatically?
14. To keep existing data and write at the end, which option fits, and why shouldn't `TRUNCATE_EXISTING` be used?
15. A critical config file needs updates minimizing partial-write corruption: is there a better strategy than truncating directly?
16. Why can't calling `write(ByteBuffer)` on a channel always be assumed to consume the entire buffer?

**Guided answers:**

1. `XY345678` because `WRITE` does not truncate.
2. Only `XY` remains after success because length is truncated to 0.
3. `CREATE_NEW+WRITE`; check and file creation happen as one atomic operation per contract.
4. Omit `CREATE` and `CREATE_NEW`; use `WRITE` or `WRITE+TRUNCATE_EXISTING` depending on whether you want to clear old content.
5. Writes using default `CREATE+TRUNCATE+WRITE`, so the file becomes `A`.
6. No; when specifying options explicitly, you must also specify `CREATE`/`TRUNCATE` if you want those behaviors.
7. Yes, on a channel opened with both permissions; file position must be managed.
8. No, invalid combination per channel contract.
9. Does not change size because truncate is ignored when read-only.
10. No, atomic creation differs from atomic/complete writes and durability.
11. No, traversal, symlinks, and permissions must be controlled per your threat model.
12. `newOutputStream` returns an open resource managed by the caller; `writeString` does the work and cleans up internally.
13. No; create parent directories separately when permitted.
14. `APPEND`, often paired with `CREATE` if missing files should be created; do not combine with `TRUNCATE`.
15. Write a temp file in an appropriate location, close it, and replace via atomic move if supported; also check durability and error handling.
16. A channel can perform a partial write; check `ByteBuffer.hasRemaining()` and loop.

## 19. Java SE Official References

- [Oracle Java SE 21 — StandardOpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html): meanings of `READ`, `WRITE`, `CREATE`, `CREATE_NEW`, `TRUNCATE_EXISTING`, `APPEND`.
- [Oracle Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): defaults of `newInputStream`, `newOutputStream`, `newByteChannel`, `write`, `writeString`, exceptions, and handle closing.
- [Oracle Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): bidirectional open options, position, read/write, and combination limits.
- [Oracle Java SE 21 — SeekableByteChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SeekableByteChannel.html): reading/writing/positioning and size/truncate.
- [Oracle Java SE 21 — FileAlreadyExistsException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileAlreadyExistsException.html): common error when `CREATE_NEW` encounters an existing name.
- [Oracle Java SE 21 — Files.move](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): `ATOMIC_MOVE`, `REPLACE_EXISTING`, and provider limitations.
- [Oracle Java SE 21 — StandardCopyOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html): options when moving/copying files.

**Lesson takeaway:** `READ` grants read access; `WRITE` grants write access; `CREATE` creates when missing yet reuses existing files; `CREATE_NEW` creates only a new name and rejects collisions atomically at creation time; `TRUNCATE_EXISTING` clears an existing file immediately upon opening for write. **Do not guess defaults across `Files` APIs**: option-less writes usually default to `CREATE+TRUNCATE+WRITE`, while option-less channels usually default to `READ`. Choose options based on business requirements and data-loss tolerance, not guesswork.