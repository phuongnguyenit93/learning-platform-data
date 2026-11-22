# Avoiding Unintended Data Overwrites When Opening or Copying Files in Java

Data loss during file processing rarely starts with an explicit delete call. Simply opening a path with an API that defaults to **truncating content**, misusing `REPLACE_EXISTING`, or writing to an existing file at byte offset 0 can corrupt user data even without ever calling `Files.delete()`. In Java I/O and NIO.2, **choosing the right file creation/open mode, checking ownership, and handling mid-operation errors** are essential steps of safe design.

This lesson explains when Java creates, truncates, overwrites, or rejects an existing target; distinguishes `CREATE` from `CREATE_NEW`, `TRUNCATE_EXISTING` from `APPEND`, the behavior of `Files.copy()`, the limitations of calling `Files.exists()` before writing, and how to reduce risks when updating an important file.

The goal is choosing a strategy of **"never alter existing content unless explicitly intended,"** rather than assuming every file operation is safe simply because no replacement option was declared.

## 1. Properly Defining Forms of "Overwrite"

There are at least four distinct scenarios:

1. **Truncate on open:** A file with existing content is reset to length 0 immediately upon opening, before the application writes any new data.
2. **Overwrite at offset:** The file keeps its original length or grows, but existing bytes are replaced by new bytes, commonly starting at `position = 0`.
3. **Replace the target file object/path:** A copy/move operation replaces the file at the target path with another file, potentially losing old content or metadata.
4. **Write outside the intended area:** An improperly normalized path or a followed symbolic link causes data to be written to a different file than the business target.

To prevent data loss, distinguish all four. For instance, `StandardOpenOption.WRITE` **does not clear a file upon opening**, yet a single `write()` at offset 0 can still **overwrite the leading bytes**. Conversely, `TRUNCATE_EXISTING` empties the file as soon as opening succeeds, even if the `try` body has not written a single byte yet.

## 2. Open and Write Behavior Table: Dangerous Defaults

| API / configuration | If target file already exists | If file does not exist | Risk |
| --- | --- | --- | --- |
| `Files.newOutputStream(path)` | **Truncates file** on open | Creates new file | Easy to lose content because default equals `CREATE + TRUNCATE_EXISTING + WRITE` |
| `Files.newBufferedWriter(path, charset)` | **Truncates file** on open | Creates new file | Also defaults to create or truncate |
| `Files.write(path, bytes)` / `Files.writeString(path, text)` | **Replaces file content** (truncates by default) | Creates new file | Do not use directly on names that might exist when preservation is required |
| `new FileOutputStream(file)` | **Truncates file** | Creates file | Default is not append |
| `new FileOutputStream(file, true)` | Opens for appending | Creates file if missing | May append data to an unintended file |
| `FileChannel.open(path)` | Opens read-only | Fails if missing | Does not allow writing itself |
| `FileChannel.open(path, WRITE)` | Allows writing to existing file, starting position 0 | Usually fails if missing | Overwrites from start when `write()` is called |
| `FileChannel.open(path, WRITE, CREATE)` | Keeps content on open; `write()` can still overwrite | Creates file | Does not guarantee "create only if missing and never modify existing file" |
| `FileChannel.open(path, WRITE, CREATE, TRUNCATE_EXISTING)` | **Truncates to 0 bytes on open** | Creates file | Suitable only when intentionally replacing all data |
| `FileChannel.open(path, WRITE, CREATE_NEW)` | **Fails, does not open for writing** | Creates new file | Appropriate for "never touch an existing file" |
| `FileChannel.open(path, WRITE, APPEND)` | Appends to end | Fails if missing, unless `CREATE` is added | Does not imply exclusive locking across multiple writers |

Default descriptions apply to standard Java file providers; specific operations can still fail due to permissions, path type, filesystem, or I/O errors. When the goal is **never modifying an existing file**, enforce policy with an exclusive creation operation like `CREATE_NEW`, rather than relying on opening with `CREATE`.

### Why Can `Files.writeString` Be Dangerous?

The code:

```java
Files.writeString(Path.of("config.txt"), "new");
```

if `config.txt` already exists and is writable, the API defaults to **creating if missing and truncating if present**. A long configuration file can be reduced to just the three bytes `new`. If the goal is only creating a new file, specify explicitly:

```java
Files.writeString(
        Path.of("config.txt"),
        "new",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
```

This is an **illustrative snippet** requiring imports for `Files`, `Path`, `StandardCharsets`, `StandardOpenOption`, and `IOException` handling. If the file already exists, the operation fails, typically with `FileAlreadyExistsException`, instead of overwriting.

## 3. How Do `CREATE` and `CREATE_NEW` Differ?

`CREATE` means **create the file if absent**, yet if the file already exists and the channel is opened for writing, the program can still open that file to modify it. Conversely, `CREATE_NEW` requires **creating a new file**; if the path already exists, it fails. The existence check and creation are performed **atomically with respect to each other** per the API contract.

```java
// Illustrative: path is a controlled Path; caller handles IOException.
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    // Only reaches here if creating a new file succeeded.
}
```

For `Files.newOutputStream()`:

```java
// Illustrative: do not allow writing to an existing file.
try (OutputStream out = Files.newOutputStream(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    out.write(payload);
}
```

`payload` must be a `byte[]` prepared by the caller; this is an illustrative snippet, not a standalone program.

Key points to remember:

- `CREATE_NEW` rejects an **existing path**, including when the path is a **symbolic link** even if the link target no longer exists. This helps avoid "following an old symlink and writing elsewhere" during creation.
- `CREATE_NEW` does not automatically create **parent directories**. If `parent` is missing, the call still fails; create parent directories only when that path is permitted.
- `CREATE_NEW` does not verify that the parent path is not concurrently altered by another actor. In public or externally writable directories, filesystem ownership and path protection measures are required.
- If the new file holds sensitive content, you must also choose appropriate **permissions for the new file**, `FileAttribute`/umask policies, and storage location.
- `CREATE_NEW` resolves the **existence vs. creation** race at the target path, but does not turn a sequence of multiple write calls into an atomic transaction.

### `Files.createFile` Also Rejects Existing Names

```java
Path file = Files.createFile(target);
```

`Files.createFile()` atomically creates an empty new file if absent, accepting `FileAttribute<?>...` when supported by the system. However, pre-creating an empty file and then calling `Files.writeString(file, text)` **does not guarantee another writer will not modify the file between the two steps**, and default `Files.writeString` still truncates the file on open. When you want to enforce exclusive creation and write data, it is usually simpler to **open directly with `CREATE_NEW + WRITE` and write through that same stream/channel**.

## 4. Checking `Files.exists()` Before Writing Is Not Safe Enough

An anti-pattern:

```java
if (Files.notExists(target)) {
    Files.writeString(target, content);
}
```

Between `notExists()` and `writeString()`, another thread or process can create a file with the same name. The subsequent write uses default truncation and can **overwrite the newly appeared file**. This is a **TOCTOU** (*time-of-check to time-of-use*) bug.

```text
Time      | Process A                          | Process B
--------- | ---------------------------------- | -------------------
T1        | notExists(target) -> true          |
T2        |                                    | creates target, writes "B"
T3        | writeString(target, "A")           |
T4        | target contains "A" (lost "B")     |
```

The right approach when business logic requires "no overwrite" is an operation where **the existence check is bound to creation**:

```java
try {
    Files.writeString(target, content, StandardCharsets.UTF_8,
            StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE);
} catch (FileAlreadyExistsException exists) {
    // Do not overwrite: report name conflict or pick a new name per business rules.
}
```

This is an illustrative snippet requiring `target` and `content` declarations, type imports, and handling for other `IOException` cases. **Do not immediately switch to `TRUNCATE_EXISTING` inside the catch block just to "make it succeed,"** as that breaks the no-overwrite policy.

`Files.exists()` remains useful for displaying UI status or preparing output, but **never use a prior check result as a guarantee of exclusive write**. `notExists()` returning `false` can also mean status could not be determined, not necessarily that the file exists.

## 5. `Files.copy()`: Refuses Existing Targets by Default

When copying with Java NIO:

```java
Files.copy(source, target);
```

With `Path source` and `Path target`, **if the target file already exists, an ordinary copy fails** (typically with `FileAlreadyExistsException`), except for special cases defined by the API such as both paths referring to the exact same file. You do not need to call `Files.exists(target)` beforehand to avoid overwriting.

If you intentionally allow replacement:

```java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

then that is an **intentional data-destructive decision**, requiring authorization and error handling. `Files.copy()` **is not guaranteed to be atomic**, even without `REPLACE_EXISTING`. If an `IOException` occurs mid-copy, the new target file or the target being replaced can remain in an incomplete state. Therefore, **"not touching the old file"** and **"the new file is always complete"** are two separate requirements.

### `COPY_ATTRIBUTES` and `NOFOLLOW_LINKS` Are Not "Absolute Safety Modes"

A call like:

```java
Files.copy(source, target,
        StandardCopyOption.COPY_ATTRIBUTES,
        LinkOption.NOFOLLOW_LINKS);
```

is an **illustrative snippet**. `COPY_ATTRIBUTES` requests copying certain provider-supported metadata and may fail. `NOFOLLOW_LINKS` instructs the copy operation **not to follow symbolic links on the source**; when the source is a symbolic link, the API may copy the link itself rather than the target's content if supported. Neither option **replaces** safe target creation policies, permission controls, or path traversal protection.

To prevent overwrites, **omit `REPLACE_EXISTING`** and preserve the target's existing content when `FileAlreadyExistsException` is thrown.

### `Files.copy(InputStream, Path)` Also Requires Caution

```java
Files.copy(networkInput, target);
```

This is an illustrative snippet with an `InputStream networkInput`. This overload does not take a `Path source`, yet it still supports `REPLACE_EXISTING` and can leave partially copied data if reading or writing fails mid-way. When input comes from an untrusted source, limit size and rate, and never use a filename supplied by the input directly to write outside the allowed region.

## 6. Complete Java 17+ Program: Never Overwrite When Copying or Creating

This example creates its own temporary directory so it does not touch any real user files. The program:

- Writes a source file containing `NEW DATA` and an existing target file containing `KEEP`.
- Attempts `Files.copy(source, existing)` without `REPLACE_EXISTING`; verifies it is rejected and the target remains intact.
- Copies to a new, non-existent name.
- Creates another file via `FileChannel.open(..., CREATE_NEW, WRITE)`; attempts creating it a second time and verifies rejection with unchanged content.
- Closes all channels before deleting temporary files and directories.

Create file **`SafeOpenCopyDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class SafeOpenCopyDemo {
    private SafeOpenCopyDemo() {}

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("safe-copy-demo-");
        Path source = directory.resolve("source.txt");
        Path existing = directory.resolve("existing.txt");
        Path copied = directory.resolve("copied.txt");
        Path created = directory.resolve("created.txt");

        try {
            Files.writeString(source, "NEW DATA\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
            Files.writeString(existing, "KEEP\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            try {
                Files.copy(source, existing);
                throw new AssertionError("Copy should not replace existing");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("copy-existing=refused");
            }
            System.out.println("existing-still="
                    + Files.readString(existing, StandardCharsets.UTF_8)
                            .strip());

            Files.copy(source, copied);
            System.out.println("copied="
                    + Files.readString(copied, StandardCharsets.UTF_8)
                            .strip());

            try (FileChannel channel = FileChannel.open(created,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                ByteBuffer bytes = ByteBuffer.wrap(
                        "SAFE\n".getBytes(StandardCharsets.UTF_8));
                while (bytes.hasRemaining()) {
                    if (channel.write(bytes) == 0) {
                        throw new IOException("No write progress");
                    }
                }
            }
            System.out.println("created="
                    + Files.readString(created, StandardCharsets.UTF_8)
                            .strip());

            try (FileChannel ignored = FileChannel.open(created,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                throw new AssertionError("Create should refuse existing");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("create-new-existing=refused");
            }
            System.out.println("created-still="
                    + Files.readString(created, StandardCharsets.UTF_8)
                            .strip());
        } finally {
            Files.deleteIfExists(created);
            Files.deleteIfExists(copied);
            Files.deleteIfExists(existing);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac SafeOpenCopyDemo.java
java SafeOpenCopyDemo
```

Output when temporary directory operations succeed on a standard filesystem:

```text
copy-existing=refused
existing-still=KEEP
copied=NEW DATA
created=SAFE
create-new-existing=refused
created-still=SAFE
```

Analysis:

1. `Files.writeString(..., CREATE_NEW, WRITE)` creates the first two files with no risk of accidentally truncating a same-named file.
2. `Files.copy(source, existing)` preserves `existing.txt` by default; the expected exception is caught explicitly without swallowing other `IOException`s.
3. `Files.copy(source, copied)` succeeds because `copied.txt` does not yet exist. It is still not an atomic copy against mid-way I/O errors.
4. `FileChannel.open(created, CREATE_NEW, WRITE)` opens the new file exclusively, and the `ByteBuffer.hasRemaining()` loop ensures all accepted bytes are written.
5. Attempting to open `created.txt` again with `CREATE_NEW` throws `FileAlreadyExistsException`, leaving the old file `SAFE` untouched.
6. `try-with-resources` closes the channel before cleanup. `finally` attempts to delete the example-owned temporary files.

The example demonstrates **protecting existing files**; it does not prove an entire copy/write process will automatically roll back on power loss or I/O failure. In real applications, if an operation fails after creating a new file, you must have a policy to detect and clean up **only the new file owned by the application**, never blindly deleting a path that another actor might have swapped.

## 7. What If You Still Need to Replace an Existing File's Content?

There are legitimate needs such as updating configuration, replacing an export, or writing a new version of a report file. In such cases, **avoiding unintended overwrites** means replacement must be **intentional, controlled, and recoverable**, not forbidden in every scenario.

### Avoid Truncating the Target File Upfront

Risky approach:

```java
Files.writeString(target, newlyGeneratedContent);
```

If the old file is critical, `Files.writeString()` truncates the target by default and the process might die before finishing writing. Instead of writing directly to `target`, consider this strategy:

1. Create a **new temporary file** on the same filesystem and in an appropriate directory; its name must be safely allocated, e.g., `Files.createTempFile(parent, prefix, suffix)`.
2. Write all new data to the temporary file, validate it, close the stream/channel, and optionally call `FileChannel.force(true)` to request syncing content and metadata.
3. Only once the content is ready, perform a `Files.move()` from the temporary file to the target **using an explicitly permitted replacement policy**.
4. If atomicity is needed, try `StandardCopyOption.ATOMIC_MOVE` on a supporting filesystem, handling `AtomicMoveNotSupportedException` explicitly.
5. Log the outcome, test crash/recovery scenarios, and clean up leftover temporary files.

**Important:** `ATOMIC_MOVE` does not mean "strictly no overwrite." When `ATOMIC_MOVE` is specified, **behavior if the target already exists is implementation-specific** and other options may be ignored per the `Files.move()` contract. Therefore, never use `Files.move(temp, target, ATOMIC_MOVE)` as universal proof that an existing target cannot be replaced. If the requirement is **strictly never touching an existing target**, exclusive creation `CREATE_NEW` or a platform-verified no-replace publishing mechanism is more appropriate.

### Controlled Intentional Replacement Example

```java
// Sketch: application already verified permission to replace target,
// temporary contains complete content, on an appropriate same FileStore.
try {
    Files.move(temporary, target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} catch (AtomicMoveNotSupportedException unsupported) {
    // Choose own policy: fail safely or use an approved fallback.
}
```

This is a **non-standalone** sketch; it requires `temporary`/`target` variables, `IOException` handling, and a fallback policy. With `ATOMIC_MOVE`, whether an existing target is replaced depends on the implementation; **do not assume simply adding `REPLACE_EXISTING` to an atomic move yields full portable semantics**. On systems without atomic move support, a non-atomic fallback can increase the risk of another application observing an intermediate state. If that is unacceptable, **stop and report an error** instead of silently falling back.

`FileChannel.force(true)` requests syncing file content and metadata per API contract; it does not guarantee that a rename or directory entry update containing the filename is durable across all power failures on every OS/filesystem. Strict durability requires system-level strategies and recovery testing.

## 8. Protecting Against Path Traversal, Symlinks, and Wrong Directories

`CREATE_NEW` protects against an existing file or symlink at the **final target path**, but does not automatically protect all path components or all race conditions. Suppose the application intends to create:

```text
/app/export/report.txt
```

If `/app/export` can be replaced with a symbolic link pointing to another directory, file creation can still write outside the intended area. Choose a root directory owned by the application, validate and constrain filename inputs, and protect directory entries from untrusted actors.

A basic path normalization step:

```java
// Illustrative: root is a trusted directory, userName comes from input.
Path base = root.toAbsolutePath().normalize();
Path candidate = base.resolve(userName).normalize();
if (!candidate.startsWith(base) || candidate.equals(base)) {
    throw new IllegalArgumentException("Unsafe target path");
}
```

This blocks some lexical `../` escapes, yet **does not fully block symlinks or races on directory components**. In environments where an adversary actively modifies paths, use access patterns anchored on securely opened directories, filesystem permissions, or `SecureDirectoryStream` when supported by the provider. Never claim `normalize() + startsWith()` alone is a complete path traversal solution.

For `Files.copy(source, target)`, also consider `Files.isSameFile(source, target)` when designing workflows: two paths may refer to the same file via hard links or symlinks. On the same file object, a copy operation may do nothing per the API contract; this does not prove data was duplicated into an independent file.

### Ownership and Temporary Files

- Only clean up files that the process **actually created and still owns**; never blindly call `Files.deleteIfExists(target)` in a `catch` block after a `CREATE_NEW` failure.
- Never create temporary files with predictable names and open them in a way that could truncate an existing file.
- Avoid untrusted shared temp directories for operations involving user-defined paths; `Files.createTempFile()` avoids name collisions, but does not by itself make an entire workflow race-free.
- For sensitive files, set permissions on both the file and directory, especially when data is written before renaming into a public location.
- When using `Files.copy(..., REPLACE_EXISTING)`, remember replacing a file can change the target's metadata or permissions. Check whether attributes/ownership preservation is needed per provider.

## 9. When Should You Use `APPEND` Instead of `CREATE_NEW`?

Sometimes the goal is neither creating a brand-new file nor replacing an entire old file, but **appending a record to an existing log**:

```java
try (FileChannel channel = FileChannel.open(
        logPath,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND)) {
    ByteBuffer data = StandardCharsets.UTF_8.encode("record\n");
    while (data.hasRemaining()) {
        channel.write(data);
    }
}
```

This is an illustrative snippet with `Path logPath`, importing `FileChannel`, `ByteBuffer`, `StandardOpenOption`, `StandardCharsets`, and handling `IOException`. `APPEND` routes each write to end-of-file semantics, avoiding opening with `WRITE + CREATE` and writing from byte 0. However, `APPEND` is not a distributed lock, does not guarantee atomicity across concurrent appending processes on every filesystem, and does not recover data on failure.

If logs require indivisible records, define framing, synchronize writers, check write results, and apply an appropriate durability strategy. Never combine `APPEND` with `TRUNCATE_EXISTING` in `FileChannel.open()`; that combination is invalid.

## 10. Proper Exception Handling to Prevent Data Corruption

| Scenario | Common exception | Safe handling |
| --- | --- | --- |
| `CREATE_NEW` hits an existing name | `FileAlreadyExistsException` | Keep existing file intact; return conflict error or generate a new name per policy |
| `Files.copy()` hits an existing target | `FileAlreadyExistsException` | Do not automatically retry with `REPLACE_EXISTING` |
| Missing parent directory | `NoSuchFileException` or `IOException` | Verify allowed root; create parent only if valid |
| Insufficient permissions | `AccessDeniedException` or `IOException` | Report permission error; do not fall back to an arbitrary path |
| Out of space or mid-write/copy failure | `IOException` | Mark output incomplete, clean up owned resources, never report success |
| Atomic move unsupported | `AtomicMoveNotSupportedException` | Fail safely or use an explicitly approved fallback |
| Source/target altered externally mid-way | Altered result or `IOException` per provider | Design ownership/locking and never treat pre-checks as guarantees |
| Target is an unexpected directory/link | OS/provider-dependent exception | Validate file/path type and permissions; never force overwrite |

Distinguish **"file already exists"** from other I/O errors. An overly broad `catch (Exception ignored) { ... }` can hide a partial copy failure and cause the application to record "success" metadata while actual data is incomplete.

If a new file was already created and writing failed, the application may need to remove the **incomplete new file**. However, this cleanup must never delete a pre-existing file or someone else's file just because of a name match; ownership models, private directories, or resource tracking tokens are vital.

## 11. Non-Overwrite Design Checklist

Before writing or copying, verify:

1. **Policy:** Should this task only create a new file, append to an old file, modify part of it, or replace it completely? Never use one API for every case.
2. **Target name:** Is the path built from a trusted root? Are escaping paths and suspicious symlinks blocked? Does the application own the parent directory?
3. **Opening files:** Did you choose `CREATE_NEW` when existing names must strictly be rejected? Did you accidentally use an API that truncates by default?
4. **Copying:** Did you deliberately add `REPLACE_EXISTING`? If so, who authorized discarding old content?
5. **TOCTOU:** Are you calling `Files.exists()` and relying on that stale result to open with a dangerous API?
6. **Mid-operation I/O errors:** Do you write to a temporary file, track partial files, clean up only owned objects, and surface errors clearly?
7. **Atomicity & durability:** Does the application need the target file always complete, strict no-overwrite, or survival across power loss? These are distinct requirements.
8. **Concurrency:** Do multiple writers or other processes access it concurrently? Are exclusive ownership, locking, or version checks needed?
9. **Permissions and metadata:** Does the new file have proper permissions, and must a replaced file preserve attributes/owner?
10. **Testing:** Have you tested existing targets, symlinks, missing parent directories, permission denied, `ENOSPC`, mid-copy crashes, concurrent two-process operations, and target deployment platform behavior?

## 12. Common Mistakes to Avoid

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `Files.writeString(path, text)` with a user-supplied filename | Can truncate an old file | `CREATE_NEW + WRITE` if creating only |
| Using `new FileOutputStream(file)` thinking it appends | Empties existing content | Use explicit append if business logic intends appending |
| Using `WRITE + CREATE` thinking it never modifies existing files | Overwrites from offset 0 | Use `CREATE_NEW` or intentional offset writes |
| Checking `Files.notExists()` first then writing with defaults | TOCTOU race overwrites a file created by another process | Use an exclusive creation primitive |
| Adding `REPLACE_EXISTING` to "copy reliably" | Deletes/replaces existing target file | Omit unless replacement is an approved business requirement |
| Assuming `Files.copy()` is atomic | New or replaced file can be incomplete on error | Staging + validation + publish strategy |
| Believing `ATOMIC_MOVE` guarantees portable no-overwrite | Old target may be replaced depending on implementation | Never equate atomic rename with create-if-absent |
| Passing paths from ZIP/users without checking | Writes outside intended target area | Trusted root, path validation, and symlink/race checks |
| Deleting `target` in `catch` when `CREATE_NEW` fails | Deletes another user's existing file | Clean up only files created and owned by this operation |
| Treating a single `FileChannel.write()` as writing everything | New file can miss bytes | Loop on `ByteBuffer.hasRemaining()` |
| Writing to the same file via two different hard links | Unintended data changes despite different names | Verify file identity and permissions |
| Ignoring `IOException` after creating a new file | Leaves corrupt file behind and reports success | Clean up owned partial output; raise error clearly |

**Remember:** "Do not overwrite" must be enforced by **the contract of the open/copy operation itself**, not by a prior existence check. Use `CREATE_NEW` for exclusive creation and to reject existing files; keep `Files.copy(source, target)` without `REPLACE_EXISTING` when the target must remain intact; avoid the default truncation of `Files.writeString()`, `newOutputStream()`, and `FileOutputStream`. When an old file must be replaced, use temporary files and explicit publish and recovery workflows; never conflate "no overwrite," "atomic operation," and "durable write" as the same property.