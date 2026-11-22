# Avoiding Unintended Overwrites When Opening or Copying Files in Java

Data loss during file handling often does not begin with an explicit delete command. Simply opening a path with an API that defaults to **truncating content**, misusing `REPLACE_EXISTING`, or writing to an existing file at byte offset 0 can corrupt user data without ever calling `Files.delete()`. In Java I/O and NIO.2, **choosing the right create/open mode, checking ownership, and handling mid-operation errors** are essential steps of safe design.

This article explains when Java automatically creates, truncates, overwrites, or rejects an existing target; distinguishes `CREATE` from `CREATE_NEW`, `TRUNCATE_EXISTING` from `APPEND`, the behavior of `Files.copy()`, the limitations of calling `Files.exists()` before writing, and how to reduce risk when an important file genuinely must be updated.

The goal is choosing a policy of **“do not alter existing content unless explicitly intended”**, rather than assuming every file operation is safe just because no replacement option was declared.

## 1. Properly Defining the Forms of “Overwrite”

There are at least four distinct scenarios:

1. **Truncate on open:** A file with existing content is reset to length 0 right upon opening, before the application even writes new data.
2. **Overwrite at an offset:** The file keeps its original size or is extended, yet some existing bytes are replaced with new bytes, typically when `position = 0`.
3. **Replace the target file object/path:** A copy/move operation replaces the file sitting at the destination path with another file, potentially losing old content or metadata.
4. **Write outside the intended area:** An improperly normalized path or following a symbolic link causes data to be written to a different file than the business target.

To prevent data loss, you must distinguish all four. For instance, `StandardOpenOption.WRITE` **does not clear the file on open**, yet a single `write()` at offset 0 can still **overwrite the leading bytes**. Conversely, `TRUNCATE_EXISTING` empties the file immediately upon successful open, even if the `try` body has not written a single byte yet.

## 2. Open and Write Behavior Table: Dangerous Defaults

| API / Configuration | If Target File Exists | If File Does Not Exist | Risk |
| --- | --- | --- | --- |
| `Files.newOutputStream(path)` | **Truncates file** on open | Creates new file | Easy to lose content because default equals `CREATE + TRUNCATE_EXISTING + WRITE` |
| `Files.newBufferedWriter(path, charset)` | **Truncates file** on open | Creates new file | Also defaults to create-new or truncate |
| `Files.write(path, bytes)` / `Files.writeString(path, text)` | **Replaces file content** (truncates by default) | Creates new file | Do not use directly on potentially existing names when preservation is needed |
| `new FileOutputStream(file)` | **Truncates file** | Creates file | Default is not append |
| `new FileOutputStream(file, true)` | Opens for appending | Creates file if missing | May append data into an unintended file |
| `FileChannel.open(path)` | Opens read-only | Fails if missing | Does not allow writing on its own |
| `FileChannel.open(path, WRITE)` | Allows writing to old file; initial position is 0 | Usually fails if file is missing | Overwrites from the beginning when `write()` is called |
| `FileChannel.open(path, WRITE, CREATE)` | Preserves content on open; `write()` can still overwrite | Creates file | Does not guarantee “create only if missing and never touch old file” |
| `FileChannel.open(path, WRITE, CREATE, TRUNCATE_EXISTING)` | **Truncates to 0 bytes on open** | Creates file | Suitable only when intentionally replacing all data |
| `FileChannel.open(path, WRITE, CREATE_NEW)` | **Fails, does not open for writing** | Creates new file | Suitable for the “never touch existing files” goal |
| `FileChannel.open(path, WRITE, APPEND)` | Appends at end | Fails if missing, unless `CREATE` is added | Does not imply exclusive locking across multiple writers |

The default descriptions assume standard Java file providers; specific operations can still fail due to permissions, path type, filesystem, or I/O errors. When the goal is **never modifying an existing file**, enforce policy with an exclusive creation option like `CREATE_NEW`, rather than relying on opening with `CREATE`.

### Why Can `Files.writeString` Be Dangerous?

The code:

```java
Files.writeString(Path.of("config.txt"), "new");
```

if `config.txt` already exists and is writable, the API defaults to **create if missing and truncate if present**. A long configuration file can be reduced to just the three bytes `new`. If the goal is only to create a new file, specify it explicitly:

```java
Files.writeString(
        Path.of("config.txt"),
        "new",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
```

This is an **illustrative snippet** requiring imports for `Files`, `Path`, `StandardCharsets`, `StandardOpenOption`, and `IOException` handling. If the file already exists, the operation fails, typically with `FileAlreadyExistsException`, instead of overwriting.

## 3. Where Do `CREATE` and `CREATE_NEW` Differ?

`CREATE` means **create the file if absent**, yet if the file already exists and the channel is writable, the program can still open that file to modify it. Conversely, `CREATE_NEW` requires **creating a new file**; if the path already exists, it fails. Existence check and creation are performed **atomically with respect to each other** per the API contract.

```java
// Illustrative: path is a controlled Path, IOException handled by caller.
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    // Reached only if creating the new file succeeded.
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

Several characteristics to remember:

- `CREATE_NEW` rejects an **existing path**, including when the path is a **symbolic link** even if the link target no longer exists. This avoids “following an old symlink and writing elsewhere” in create-new cases.
- `CREATE_NEW` does not automatically create **parent directories**. If `parent` is missing, the call still fails; only create parent directories when that path is permitted.
- `CREATE_NEW` does not verify that the parent path was not concurrently altered by another actor. In public directories or directories writable by others, ownership and filesystem-level path protection are needed.
- If the newly created file contains sensitive content, you must also choose the **new file's access permissions**, `FileAttribute`/umask policy, and an appropriate storage location.
- `CREATE_NEW` solves the **existence vs. creation** race at the destination path, but it does not turn a sequence of multiple write calls into a complete atomic transaction.

### `Files.createFile` Also Rejects Existing Names

```java
Path file = Files.createFile(target);
```

`Files.createFile()` is an atomic create-new operation if absent, accepting `FileAttribute<?>...` when supported by the system. However, creating an empty file first and then calling `Files.writeString(file, text)` **does not automatically guarantee no other writer modifies the file between the two steps**, and `Files.writeString` still truncates the opened file by default. When you need both exclusive creation and writing data, it is usually simpler to **open directly with `CREATE_NEW + WRITE` and write through that very stream/channel**.

## 4. Checking `Files.exists()` Before Writing Is Not Safe Enough

An anti-pattern:

```java
if (Files.notExists(target)) {
    Files.writeString(target, content);
}
```

Between `notExists()` and `writeString()`, another thread or process can create a file with the same name. The subsequent write defaults to truncating and can **overwrite the file that just appeared**. This is a **TOCTOU** (*time-of-check to time-of-use*) bug.

```text
Time      | Process A                          | Process B
--------- | ---------------------------------- | -------------------
T1        | notExists(target) -> true          |
T2        |                                    | creates target, writes "B"
T3        | writeString(target, "A")           |
T4        | target contains "A" (lost "B")     |
```

The right approach when business rules require “never overwrite” is using a single operation with **existence checking bound to creation**:

```java
try {
    Files.writeString(target, content, StandardCharsets.UTF_8,
            StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE);
} catch (FileAlreadyExistsException exists) {
    // Do not overwrite: report name collision or pick a new name per business rules.
}
```

This is an illustrative snippet requiring declarations for `target` and `content`, type imports, and handling other `IOException`s. **Do not switch to `TRUNCATE_EXISTING` inside the `catch` branch just to “make it succeed”**, as that breaks the no-overwrite policy.

`Files.exists()` remains useful for displaying info to users or preparing UI, but **never use a stale check result as an exclusive-write guarantee**. `notExists()` returning `false` can also mean the status could not be determined, not necessarily that the file exists.

## 5. `Files.copy()`: Refuses an Existing Target by Default

When copying with Java NIO:

```java
Files.copy(source, target);
```

With `Path source` and `Path target`, **if the target file already exists, the normal copy operation fails** (typically with `FileAlreadyExistsException`), except in special API-defined cases such as both paths actually referring to the same file. You do not need to check `Files.exists(target)` beforehand to prevent overwriting.

If you intentionally allow replacement:

```java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

that is an **intentional decision to destroy old data**, requiring approval and error handling. `Files.copy()` **is not guaranteed atomic**, even without `REPLACE_EXISTING`. If an `IOException` occurs mid-copy, the new destination file or the destination file being replaced may be left in a partial state. Therefore **“do not alter the old file”** and **“the new file is always complete”** are two separate requirements.

### `COPY_ATTRIBUTES` and `NOFOLLOW_LINKS` Are Not an “Absolute Safe Mode”

A call like:

```java
Files.copy(source, target,
        StandardCopyOption.COPY_ATTRIBUTES,
        LinkOption.NOFOLLOW_LINKS);
```

is an **illustrative snippet**. `COPY_ATTRIBUTES` requests copying certain provider-supported metadata and may fail. `NOFOLLOW_LINKS` controls **not following symbolic links on the source** during the copy; when `source` is a symbolic link, the API may copy the link itself rather than the linked target's content if supported. Neither option **replaces** a safe target-creation policy, permission controls, and path traversal defense.

To avoid overwriting, **omit `REPLACE_EXISTING`** and inspect/preserve the destination's content when catching `FileAlreadyExistsException`.

### `Files.copy(InputStream, Path)` Also Requires Caution

```java
Files.copy(networkInput, target);
```

This is an illustrative pattern with `networkInput` of type `InputStream`. This overload does not take a `Path source`, yet it also supports `REPLACE_EXISTING` and can leave partially copied data if an error occurs during read/write. When the input is untrusted data, bound size/rate and never use a client-supplied filename directly to write outside the allowed area.

## 6. Complete Java 17+ Program: Never Overwriting on Copy or Create

The example creates its own temporary directory so it never touches the learner's real files. The program:

- Writes a source file containing `NEW DATA` and an existing target containing `KEEP`.
- Attempts `Files.copy(source, existing)` without `REPLACE_EXISTING`; verifies refusal and that the target stays intact.
- Copies to a new, non-existent name.
- Creates another file via `FileChannel.open(..., CREATE_NEW, WRITE)`; attempts creating it a second time and verifies refusal while content stays unchanged.
- Closes all channels before deleting temporary files/directories.

Create the file **`SafeOpenCopyDemo.java`**:

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

Result when operations in the temporary directory succeed on a normal filesystem:

```text
copy-existing=refused
existing-still=KEEP
copied=NEW DATA
created=SAFE
create-new-existing=refused
created-still=SAFE
```

Analysis:

1. `Files.writeString(..., CREATE_NEW, WRITE)` creates the first two files with no chance of accidentally truncating an identically named file.
2. `Files.copy(source, existing)` leaves the destination `existing.txt` untouched by default; the exception is caught explicitly without swallowing other `IOException`s.
3. `Files.copy(source, copied)` succeeds because `copied.txt` did not exist yet. It is still not an atomic copy operation against mid-way I/O failures.
4. `FileChannel.open(created, CREATE_NEW, WRITE)` exclusively creates and opens the new file, and the `ByteBuffer.hasRemaining()` loop ensures all accepted bytes are written.
5. Attempting to open `created.txt` again with `CREATE_NEW` throws `FileAlreadyExistsException`, leaving the existing file `SAFE` untouched.
6. `try-with-resources` closes the channel before cleanup. `finally` attempts to delete the temporary files owned by the example.

The example demonstrates **protecting already-existing files**; it does not prove that the entire copy/write process automatically rolls back on power loss or I/O errors. In real applications, if an operation fails after creating a new file, there must be a policy to detect and clean up **the exact new file owned by the application**, without blindly deleting a path that another actor might have swapped.

## 7. What If You Still Need to Replace an Old File's Content?

There are legitimate needs such as updating configuration, replacing an export, or writing a new version of a report file. In those cases, **avoiding unintended overwrites** means replacement must be **intentional, controlled, and recoverable**, not necessarily forbidden in every situation.

### Avoid Truncating the Target File at the Start

Risky approach:

```java
Files.writeString(target, newlyGeneratedContent);
```

If the old file is important, `Files.writeString()` truncates `target` by default and the process could die before finishing the write. Instead of writing straight to `target`, consider this strategy:

1. Create a **new temporary file** on the same filesystem and in an appropriate directory; the temp filename must be allocated safely, e.g., `Files.createTempFile(parent, prefix, suffix)`.
2. Write all new data into the temporary file, validate it, close the stream/channel, and optionally call `FileChannel.force(true)` to request syncing content/metadata if required.
3. Only when the content is ready, perform `Files.move()` from the temporary file to the target file **according to the authorized replacement policy**.
4. If atomicity is required, attempt `StandardCopyOption.ATOMIC_MOVE` on a supporting filesystem, handling `AtomicMoveNotSupportedException` explicitly.
5. Log outcomes, test crash/recovery, and clean up leftover temporary files.

**Important:** `ATOMIC_MOVE` does not mean “absolutely never overwrite”. When `ATOMIC_MOVE` is selected, **behavior if `target` already exists is implementation-specific** and other options may be ignored per the `Files.move()` contract. Therefore, do not use `Files.move(temp, target, ATOMIC_MOVE)` as universal proof that an existing target cannot be replaced. If the requirement is **strictly never touch an existing target file**, exclusive creation with `CREATE_NEW` or a publish mechanism with a platform-verified no-replace contract is more appropriate.

### Example of Intentional, Controlled Replacement

```java
// Outline: application has verified permission to replace target,
// temporary holds complete content, on a suitable same FileStore.
try {
    Files.move(temporary, target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} catch (AtomicMoveNotSupportedException unsupported) {
    // Choose explicit policy: fail safely or use an approved fallback.
}
```

This is a **non-standalone** outline; it requires `temporary`/`target` variables, `IOException` handling, and a fallback policy. With `ATOMIC_MOVE`, whether an existing target is replaced depends on the implementation; **do not assume simply adding `REPLACE_EXISTING` to an atomic move gives full portable semantics**. On systems lacking atomic move support, a non-atomic fallback can increase the risk of other applications observing an intermediate state. If that is unacceptable, **stop and report an error** rather than silently falling back.

`FileChannel.force(true)` requests syncing file content/metadata per API contract; it does not guarantee that the entire rename or parent-directory name update is durable across every power-loss event on every OS/filesystem. Strict durability requirements call for system-level strategies and recovery testing.

## 8. Protecting Against Path Traversal, Symbolic Links, and Wrong Directories

`CREATE_NEW` protects against an existing file/symlink right at **the destination path**, yet it does not automatically protect every path component or every kind of race. Suppose an application intends to create:

```text
/app/export/report.txt
```

If `/app/export` can be replaced with a symbolic link pointing to another directory, creating the file can still write outside the intended area. You must choose an application-owned root directory, validate and constrain filename inputs, and protect directory entries from untrusted actors.

A basic path-normalization check:

```java
// Illustrative: root is a trusted directory, userName comes from input.
Path base = root.toAbsolutePath().normalize();
Path candidate = base.resolve(userName).normalize();
if (!candidate.startsWith(base) || candidate.equals(base)) {
    throw new IllegalArgumentException("Unsafe target path");
}
```

This blocks some lexical `../` escapes, yet **does not completely block symlinks or races on directory components**. In environments where an adversary actively alters paths, use safely opened directory handles, filesystem permissions, or `SecureDirectoryStream` when supported by the provider. Never claim `normalize() + startsWith()` is a complete anti-path-traversal solution.

For `Files.copy(source, target)`, also consider `Files.isSameFile(source, target)` when designing workflows: two paths can refer to the same file via hard links/symlinks. For the same file object, a copy operation may do nothing per API contract; that does not prove data was duplicated into an independent file.

### Ownership and Temporary Files

- Only clean up files the process **actually created and still owns**; never blindly call `Files.deleteIfExists(target)` in a `catch` block after `CREATE_NEW` fails.
- Never create a temporary file under a predictable name and then open it in a way that could truncate an existing file.
- Avoid untrusted shared temporary directories for operations with user-defined paths; `Files.createTempFile()` avoids name collisions but does not automatically make the whole workflow race-free.
- For sensitive files, set permissions on both the file and directory, especially when data is written before renaming into a public location.
- When using `Files.copy(..., REPLACE_EXISTING)`, remember that replacing a file can alter destination metadata or permissions. Check whether attributes/ownership preservation is needed per provider.

## 9. When Should You Use `APPEND` Instead of `CREATE_NEW`?

Sometimes the goal is neither creating a new file nor replacing the entire old file, but **appending a record to an existing log**:

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

This is an illustrative snippet with `logPath` of type `Path`, imports for `FileChannel`, `ByteBuffer`, `StandardOpenOption`, `StandardCharsets`, and `IOException` handling. `APPEND` gives end-of-file write semantics, avoiding opening `WRITE + CREATE` and writing from byte 0. However, `APPEND` is not a distributed lock, does not guarantee atomicity across multiple appending processes on every filesystem, and does not recover data on errors.

If a log requires indivisible records, define framing, synchronize writers, verify results, and apply an appropriate durability strategy. Never combine `APPEND` with `TRUNCATE_EXISTING` in `FileChannel.open()`; that combination is invalid.

## 10. Proper Exception Handling to Avoid Corrupting Data

| Scenario | Common Exception | Safe Handling |
| --- | --- | --- |
| `CREATE_NEW` encounters an existing name | `FileAlreadyExistsException` | Keep existing file intact; return collision error or generate a new name per policy |
| `Files.copy()` encounters an existing target | `FileAlreadyExistsException` | Do not automatically retry with `REPLACE_EXISTING` |
| Missing parent directory | `NoSuchFileException` or `IOException` | Verify allowed root; create only valid parents |
| Permission denied | `AccessDeniedException` or `IOException` | Report permission error; do not fall back to a random path |
| Out of space or mid-write/copy error | `IOException` | Mark output incomplete, clean up owned resources, never report success |
| Atomic move unsupported | `AtomicMoveNotSupportedException` | Fail safely or use an explicitly approved fallback |
| Source/target altered by someone else between steps | Changed result or `IOException` depending on provider | Design ownership/locking and do not treat pre-checks as guarantees |
| Destination is a directory/unusual link | OS/provider-dependent exception | Validate file/path type and permissions; do not overwrite recklessly |

Distinguish **“file already exists”** errors from other I/O errors. An overly broad `catch (Exception ignored) { ... }` can hide an incomplete copy and cause the application to record “success” metadata while actual data is truncated.

If a new file was created and writing failed, the application may need to remove the **incomplete new file**. However, this cleanup must never delete a pre-existing file or someone else's file just because names collided; an ownership model, dedicated directory, or resource tracking token is essential.

## 11. Checklist for Designing Non-Overwriting Operations

Before writing or copying, check:

1. **Policy:** Should this task only create a new file, append to an old file, modify part of it, or replace the whole file? Never use one API for all cases.
2. **Destination name:** Is the path constructed from a trusted root? Are escaping paths or suspicious symlinks blocked? Is the parent directory application-owned?
3. **Opening the file:** Did you choose `CREATE_NEW` when existing names must strictly be rejected? Did you accidentally use a truncating default API?
4. **Copying:** Did you intentionally add `REPLACE_EXISTING`? If so, who authorized losing the old content?
5. **TOCTOU:** Are you calling `Files.exists()` and relying on the stale result to open with a dangerous API?
6. **Mid-way I/O errors:** Do you write to a temp file, handle partial files, clean up only the right object, and report errors clearly?
7. **Atomicity & durability:** Does the application need the destination file always complete, strict no-overwrite, or survival across power loss? These are distinct requirements.
8. **Concurrency:** Do multiple writers or other processes access it concurrently? Are exclusive ownership, locking, or version checks needed?
9. **Permissions and metadata:** Does a new file get proper permissions, and does a replaced file need preserved attributes/ownership?
10. **Testing:** Have you tested existing target files, symlinks, missing parent directories, permission denied, ENOSPC, mid-copy crashes, two concurrent processes, and target deployment platform behavior?

## 12. Common Mistakes to Avoid

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `Files.writeString(path, text)` with a user-supplied filename | Can truncate an old file | `CREATE_NEW + WRITE` if creating only new files |
| Using `new FileOutputStream(file)` thinking it appends at the end | Empties old content | Use explicit append if business logic requires it |
| Using `WRITE + CREATE` thinking it never modifies an existing file | Overwrites from offset 0 | Use `CREATE_NEW` or intentional offset writes |
| Checking `Files.notExists()` first and then doing default write | TOCTOU race overwrites a file created by another process | Use a single exclusive creation operation |
| Adding `REPLACE_EXISTING` just to "copy reliably" | Deletes/replaces existing destination file | Omit unless replacement is an approved business action |
| Thinking `Files.copy()` is atomic | New or replaced file may be partial on error | Staging + validation + publish strategy |
| Believing `ATOMIC_MOVE` guarantees portable no-overwrite | Existing target may be replaced depending on implementation | Do not equate atomic rename with create-if-absent |
| Passing paths from ZIP/users without checking | Writes outside intended destination area | Trusted root, path validation, and symlink/race checks |
| Deleting `target` inside `catch` when `CREATE_NEW` fails | Deletes someone else's existing file | Clean up only files you created and own |
| Treating a single `FileChannel.write()` as writing everything | New file may miss bytes | Loop checking `ByteBuffer.hasRemaining()` |
| Writing to the same file via two different hard-link names | Unintended data changes despite different names | Verify file identity and permissions |
| Ignoring `IOException` after creating a new file | Leaves a corrupted file while reporting success | Clean up owned partial output, raise error clearly |

**Remember:** “Do not overwrite” must be enforced by the **contract of the open/copy operation itself**, not by a prior existence check. Use `CREATE_NEW` to create exclusively and reject existing files; use `Files.copy(source, target)` without `REPLACE_EXISTING` when the target must remain untouched; avoid the truncating defaults of `Files.writeString()`, `newOutputStream()`, and `FileOutputStream`. When replacing an old file is unavoidable, work with temporary files and clear publish and recovery plans; never confuse “no overwrite”, “atomic operation”, and “durable write” as the same property.