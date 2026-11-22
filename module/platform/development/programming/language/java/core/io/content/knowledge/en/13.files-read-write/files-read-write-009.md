# `SYNC`, `DSYNC`, `DELETE_ON_CLOSE`, and Filesystem Provider Support

## 1. Why Do These File Open Options Matter?

When working with `java.nio.file.Files`, `FileChannel`, and other file APIs, an application does not only decide **what to read/write**—it can also specify **how the file is opened and how its lifecycle is managed** via `OpenOption`. Three options frequently misunderstood are:

- **`StandardOpenOption.SYNC`**: requires every update to **file content or metadata** to be written synchronously to the underlying storage device.
- **`StandardOpenOption.DSYNC`**: requires every update to **file content** to be written synchronously to the underlying storage device; differs from `SYNC` in metadata scope.
- **`StandardOpenOption.DELETE_ON_CLOSE`**: asks the provider to **attempt deleting the file when the resource is closed** (*best effort*), suitable mainly for short-lived work files.

These are three `StandardOpenOption` values in `java.nio.file`, belonging to **file-open options**. They do not turn Java into a transactional database system, do not guarantee every provider supports them, and do not remove the need for I/O error handling.

```text
Choose OpenOption
       │
       ▼
Files.newByteChannel / Files.newOutputStream / FileChannel.open
       │
       ├─ SYNC: synchronous content + metadata updates
       │
       ├─ DSYNC: synchronous content updates
       │
       └─ DELETE_ON_CLOSE: request delete on close (best effort)
       │
       ▼
Filesystem provider + OS + filesystem + storage device
       │
       ▼
Actual outcome depends on lower-layer capabilities and contracts
```

Distinguish two sets of concerns:

1. **Durability:** after a successful write call, at what level has the system been asked to synchronize data? `SYNC`, `DSYNC`, and `FileChannel.force` address this question.
2. **Lifecycle (temporary file lifecycle):** when is deletion automatically requested for a file, and is deletion strictly guaranteed? `DELETE_ON_CLOSE` addresses this question.

The examples use **Java 17+**. Remember that the API lets you *request* behavior; whether opening succeeds and what support actually exists depend on the provider, filesystem, and operating system.

## 2. Where Does `StandardOpenOption` Apply?

`StandardOpenOption` is an enum implementing `OpenOption`. You can specify it when opening files through several APIs, for example:

```java
Path file = Path.of("result.bin");

try (OutputStream output = Files.newOutputStream(
        file,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    output.write(new byte[]{1, 2, 3});
}
```

This is an **illustrative snippet**, requiring imports for `Path`, `Files`, `OutputStream`, `StandardOpenOption` and `IOException` handling. `CREATE` creates the file if missing, `WRITE` allows writing, and `SYNC` requests synchronous updates. If the file already exists, this example does not use `TRUNCATE_EXISTING`; writing starts from the beginning rather than wiping old content by default. In real code, choose an explicit overwrite/truncate/append policy intentionally.

Common file-open options:

| OpenOption | Meaning |
| --- | --- |
| `READ` | Open for reading |
| `WRITE` | Open for writing |
| `APPEND` | Write at end of file when opened for writing |
| `TRUNCATE_EXISTING` | Clear existing file content by setting size to 0 if opened for writing |
| `CREATE` | Create file if missing |
| `CREATE_NEW` | Create new file, failing if the name already exists; check-and-create is atomic per contract |
| `SYNC` | Synchronize content or metadata updates |
| `DSYNC` | Synchronize content updates |
| `DELETE_ON_CLOSE` | Attempt to delete file on close |
| `SPARSE` | Hint to create a sparse file; provider may ignore if unsupported |

**`OpenOption`s are not completely independent of one another.** Invalid combinations can throw `IllegalArgumentException`; an option unsupported by the provider can throw `UnsupportedOperationException`. For instance, `FileChannel.open` forbids combining `APPEND` with `READ` or `TRUNCATE_EXISTING` per its contract.

## 3. `SYNC`: Synchronizing Content and Metadata

`StandardOpenOption.SYNC` specifies that **every update to the file's content or metadata** must be written synchronously to the underlying storage device.

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    // Write data to channel...
}
```

This is an **illustrative snippet**, with `Path path` and appropriate imports. `CREATE_NEW` fails if the file already exists, preventing accidental overwrites; `WRITE` specifies access mode; `SYNC` specifies the synchronization requirement.

"Metadata" can include file information such as size, modification time, and related attributes, though the exact scope of metadata updates depends on the filesystem and operation. `SYNC` is broader in scope than `DSYNC`, since it covers more than just file content bytes.

### What Does `SYNC` NOT Guarantee?

- Does not turn multiple `write` calls into **one atomic transaction**.
- Does not guarantee that two threads/processes writing concurrently produce non-interleaved records.
- Does not guarantee valid application data if the process stops mid-way through writing a structured format.
- Does not replicate data to another machine, nor replace replication or backups.
- Does not lock the file or prevent modification by other processes.
- Does not eliminate device failures, hardware corruption, or power loss beyond storage-layer guarantees.
- Does not prove the provider or filesystem truly fulfills a requirement the API/environment does not support.

**Synchronous updates differ from atomicity.** A write can request synchronous flushing to storage while the application has still only written half of a logical record if a failure occurs before the entire sequence of writes finishes.

## 4. `DSYNC`: Synchronizing File Content

`StandardOpenOption.DSYNC` requires updates to the file's **content** to be written synchronously to the underlying storage device. The difference from `SYNC` is that `DSYNC` does not require the same metadata scope per the API specification.

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE,
        StandardOpenOption.DSYNC)) {
    // Write bytes...
}
```

This is an illustrative example requiring imports for `FileChannel`, `Path`, `StandardOpenOption` and `IOException` handling.

An approximate mental model:

- **SYNC:** requires synchronizing content **and** update-related metadata.
- **DSYNC:** requires synchronizing content; does not demand all metadata at the same level as `SYNC`.

However, in real filesystems, some metadata needed to retrieve the newly written content (such as file size on append) may still have to be updated alongside the data to support recovery. Do not use a simplified mental model of metadata to deduce exact disk write counts or universal crash recovery guarantees across all systems.

### Is `DSYNC` Faster Than `SYNC`?

**Possibly**, if the filesystem/OS can skip syncing certain metadata across writes; however, it is not a theorem that `DSYNC` is always faster. Measured results depend on device type, filesystem, write size/frequency, append vs. overwrite, caches, OS, and provider.

If performance matters, benchmark your actual workload and application durability requirements. Do not choose `DSYNC` just because it sounds optimized when business logic demands stronger metadata synchronization.

## 5. Comparing `SYNC` and `DSYNC` with a Decision Table

| Criterion | `SYNC` | `DSYNC` |
| --- | --- | --- |
| Requests synchronous content updates | Yes | Yes |
| Requests synchronous metadata updates per API spec | Yes | Not at the same level as `SYNC` |
| Is it a single `flush()` call? | No; it is a file-open option | No; it is a file-open option |
| Guarantees multi-step atomic transactions | No | No |
| Best suited when | Broader content + metadata sync scope is desired | Focus is on content synchronization |
| Always runs on every provider | Must not be assumed | Must not be assumed |
| Cost | Can increase compared to async writes | Can also increase; sometimes lighter than `SYNC` |

In a logging or write-ahead journal system, choosing between `SYNC`/`DSYNC` should be driven by **acceptable data-loss bounds**, crash recovery design, and filesystem behavior. Never decide based solely on the API while ignoring record framing, commit protocols, or recovery.

## 6. Runnable Example: Writing via `FileChannel` with `SYNC`

This example creates a controlled temporary file, opens it with `SYNC`, writes UTF-8 bytes, and reads back to verify content. The program follows the success path only when the provider supports this option.

**File `SyncWriteDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class SyncWriteDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("sync-write-", ".txt");
        try {
            byte[] content = "hello".getBytes(StandardCharsets.UTF_8);

            try (FileChannel channel = FileChannel.open(
                    file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING,
                    StandardOpenOption.SYNC)) {

                ByteBuffer buffer = ByteBuffer.wrap(content);
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }
            }

            System.out.println("Content: "
                    + Files.readString(file, StandardCharsets.UTF_8));
            System.out.println("Bytes: " + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac SyncWriteDemo.java
java SyncWriteDemo
```

**Exact stdout if file operations and `SYNC` are supported and succeed:**

```text
Content: hello
Bytes: 5
```

Explanation:

1. `Files.createTempFile` creates an isolated file, avoiding overwriting user files.
2. `FileChannel.open(file, WRITE, TRUNCATE_EXISTING, SYNC)` opens for writing and clears old content of the temp file.
3. `ByteBuffer` tracks position and limit. The `while (buffer.hasRemaining())` loop ensures any bytes not written in a single `channel.write` call are handled.
4. `try-with-resources` closes the channel immediately after writing, then `Files.readString` reads it back.
5. The temporary file is deleted in `finally`.

This example **does not prove by measurement** that data reached physical hardware synchronously: it simply uses the right API to **request** `SYNC` behavior. Reading back successfully is not a crash-recovery test; the OS can serve data from cache. That is an essential difference between functional tests and durability verification.

## 7. How Does `FileChannel.force(boolean)` Differ from `SYNC`/`DSYNC`?

`FileChannel.force(boolean metaData)` lets an application **explicitly request synchronization at a chosen point** instead of requesting synchronous updates for every operation on the channel.

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE)) {
    // Write multiple blocks; there may be application-layer buffering.
    channel.force(false); // Request content synchronization.
    // ...
    channel.force(true);  // Request synchronizing both content and metadata.
}
```

This is an illustrative snippet, not a standalone program; `path` exists and relevant imports are needed. If using a buffered wrapper outside the channel, **flush data from application buffers to the channel** before calling `force`, otherwise bytes sitting in application buffers have not yet become channel updates.

Key differences:

| Requirement | Option |
| --- | --- |
| Every content/metadata update must request sync | Open file with `SYNC` |
| Every content update must request sync | Open file with `DSYNC` |
| Write multiple parts then sync at checkpoint/commit | `FileChannel.force(false/true)` |

`force(false)` focuses on content; `force(true)` also requests metadata. Per `FileChannel` documentation, the sync guarantee upon return applies to files residing on a **local storage device**; for non-local storage, the spec **does not provide the same guarantee**. Actual behavior of the metadata flag also depends on the OS.

`force()` applies to updates made through the channel's own methods; for updates through a `MappedByteBuffer`, `MappedByteBuffer.force()` may be required per its separate contract. Do not treat `channel.force()` as a call that forces every cache and writer across the entire JVM.

### Does `force()` Replace `close()`?

No. `force` requests persisting data updates, while `close` releases the resource/channel. The program still must close the channel via `try-with-resources`. Conversely, **closing a channel does not automatically imply** a durability guarantee equivalent to `SYNC` or `force(true)` in every environment.

## 8. `DELETE_ON_CLOSE`: Request Delete on Close, Not an Absolute Guarantee

`StandardOpenOption.DELETE_ON_CLOSE` asks the implementation to **attempt deleting the file when the associated channel/stream is closed**. This is very useful for certain **work files** used only within one JVM.

Per Java's contract:

- When specified, the implementation makes a **best effort** to delete the file during `close()`.
- If `close()` is not called, the JVM may make a best-effort attempt upon termination, if conditions allow.
- Exact timing, deletion mechanism, and other details are **implementation-specific**.
- Should not be used carelessly on files concurrently opened by other entities.
- Some OSes prohibit deleting files currently in use by another process in certain ways.
- With some providers, this option may imply not following symbolic links for security reasons, and opening a link may fail.

The most important keyword is **best effort**. `DELETE_ON_CLOSE` **is not guaranteed proof that the file vanished**, does not ensure secure erasure, and does not replace a temporary-file management policy.

### Why Does `DELETE_ON_CLOSE` Require Proper `close()`?

If a developer forgets to close the stream, when deletion is requested becomes unpredictable. The following pattern is risky:

```java
OutputStream out = Files.newOutputStream(
        tempPath,
        StandardOpenOption.WRITE,
        StandardOpenOption.DELETE_ON_CLOSE);
// ...
// Forgot close: the file may not be cleaned up promptly.
```

This is an illustrative snippet, not a recommended pattern. Prefer:

```java
try (OutputStream out = Files.newOutputStream(
        tempPath,
        StandardOpenOption.WRITE,
        StandardOpenOption.DELETE_ON_CLOSE)) {
    // Write temporary data.
}
```

This is an illustrative snippet with a valid existing file. The resource is closed at scope exit, triggering best-effort deletion.

### Should It Be Applied to Every Temporary File?

Not necessarily. If the file needs to be reopened after closing one channel, or used by another process, `DELETE_ON_CLOSE` can delete it earlier than intended. For temp files shared across processes, define an explicit lifecycle contract.

## 9. Runnable Example: `DELETE_ON_CLOSE` with a Dedicated Temp File

**File `DeleteOnCloseDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.EnumSet;

public class DeleteOnCloseDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("delete-on-close-");
        Path file = directory.resolve("scratch.bin");

        try {
            try (SeekableByteChannel channel = Files.newByteChannel(
                    file,
                    EnumSet.of(
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE,
                            StandardOpenOption.DELETE_ON_CLOSE))) {
                channel.write(ByteBuffer.wrap(new byte[]{1, 2, 3}));
                System.out.println("Open in scope: " + channel.isOpen());
            }

            System.out.println("Exists after close: " + Files.exists(file));
        } finally {
            // Fallback when the provider cannot delete immediately.
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile/run:

```bash
javac DeleteOnCloseDemo.java
java DeleteOnCloseDemo
```

**Typical stdout on a provider supporting and deleting on close:**

```text
Open in scope: true
Exists after close: false
```

Here `CREATE_NEW` creates only a fresh file in the temp directory, `WRITE` writes bytes, and `DELETE_ON_CLOSE` requests cleanup. **Do not rely on `Files.exists(file)` while the channel is still open**, because providers may differ on when deletion occurs. After closing, `Files.exists(file)` is typically `false` when deletion succeeds, though you should not write portable tests demanding this exact result across all providers.

The `finally` block still keeps `Files.deleteIfExists` as explicit cleanup. If the provider does not support the option, opening may throw `UnsupportedOperationException` or an appropriate exception; the program does not silently drop the option and claim deletion occurred.

**Note:** `Files.exists(file)` also returns `false` in certain cases where existence cannot be determined due to access errors; never treat a single `exists` check as forensic proof that all copies of data were permanently wiped from the device.

## 10. Best Effort Does Not Mean Secure Delete

A dangerous mistake is treating `DELETE_ON_CLOSE` as **irrecoverable erasure of sensitive data**. The API only speaks of attempting to remove the file entry, making no guarantee about physically wiping disk blocks, cache copies, snapshots, backups, SSD wear-leveling areas, or remote filesystem contents.

For sensitive data, design per system security policies: restrict access permissions, avoid writing to disk unnecessarily, use encrypted storage, and manage keys properly. `DELETE_ON_CLOSE` can be one cleanup aid, not the entire security solution.

Nor can you assume the JVM will always execute cleanup during abnormal termination (power loss, kernel crash, or process killed without cleanup). Critical temp files may therefore need age-based sweeping or external lifecycle management beyond normal closing.

## 11. `Files.createTempFile` Differs from `DELETE_ON_CLOSE`

`Files.createTempFile` creates a file with a fresh name, typically in the temp directory. By itself, this method **does not configure deletion when subsequent read/write streams close**.

```java
Path temp = Files.createTempFile("job-", ".bin");
try {
    // Open, read/write temp file.
} finally {
    Files.deleteIfExists(temp);
}
```

This is an illustrative snippet handling `IOException`. If you want `DELETE_ON_CLOSE` after creating a temp file, pass that option when opening the channel/stream, keeping in mind the file may no longer be accessible by name once an implementation performs early unlinking.

Selection criteria:

| Requirement | Approach |
| --- | --- |
| Temp file opened once, only needed within scope | May use `DELETE_ON_CLOSE` if supported by provider |
| File must be closed and reopened multiple times | Manage with `Files.createTempFile` and delete explicitly |
| File must be shared with another process | Avoid `DELETE_ON_CLOSE` if lifecycles conflict |
| File must survive crash for recovery or audit | Needs dedicated storage/cleanup policy |
| Sensitive data must be securely erased | `DELETE_ON_CLOSE` is insufficient to guarantee secure erase |

## 12. What Is a Provider and Why Is Support Non-Uniform?

Java NIO.2 allows multiple **filesystem providers** via `java.nio.file.spi.FileSystemProvider`. Each `Path` belongs to a specific `FileSystem`; operations like `Files.newByteChannel(path, options)` are delegated to that Path's provider.

Examples of provider contexts:

- The OS's default filesystem.
- ZIP/JAR filesystems (e.g., via `FileSystems.newFileSystem`).
- Custom providers added by libraries/applications to access other storage backends.

Features supported by the default filesystem are not guaranteed to be identically supported by a ZIP provider or custom provider. A provider might support `CREATE_NEW` yet not support `SYNC`, or might not provide `FileChannel` for every `Path` type.

**Support is part of the runtime contract.** If the user requires high write durability, the application must pick a strategy verifiable on the active provider, or **fail clearly** when it cannot be satisfied. Never silently drop `SYNC`, write normally, and claim data was synchronized.

### How to Inspect the Provider in Code

```java
FileSystemProvider provider = path.getFileSystem().provider();
System.out.println(provider.getClass().getName());
```

This is an illustrative snippet requiring imports for `Path`, `FileSystemProvider`. The class name tells you which provider is active; **it does not prove every file-open option is supported**. A provider may depend on the mounted filesystem, OS, and file-specific constraints.

## 13. Errors to Anticipate When Opening with Special Options

When calling `FileChannel.open(path, options)` or `Files.newByteChannel`, key error categories include:

| Scenario | Exception / handling |
| --- | --- |
| Option not supported by provider | `UnsupportedOperationException` |
| Invalid option combination | `IllegalArgumentException` |
| File already exists with `CREATE_NEW` | May throw `FileAlreadyExistsException` |
| Cannot open/write/delete due to I/O | `IOException` or subclass |
| Insufficient access permissions | Possibly `AccessDeniedException`, `SecurityException` depending on API/environment |
| Error closing resource | `IOException` to handle; try-with-resources attaches as suppressed if a primary error exists |
| File locked by another process or provider cannot delete | Filesystem-dependent; do not assume `DELETE_ON_CLOSE` always succeeds |

**`UnsupportedOperationException` and `IllegalArgumentException` are unchecked**, so a `catch(IOException)` block **will not catch option-configuration errors**. Handle them explicitly if your application plans a fallback or clear error reporting.

Do not catch every exception broadly and continue writing as if nothing happened. In applications requiring durability, if the provider rejects `SYNC`, dropping it is **changing the data guarantee**, which must be a deliberate decision.

## 14. Fallback When a Provider Lacks Support: A Business Choice

Suppose an application wants to open a channel with `SYNC`. Several policies exist:

1. **Fail closed:** if the provider lacks support, reject the operation. Appropriate when synchronization is mandatory.
2. **Fall back to `DSYNC`:** valid only if the business accepts the different metadata scope and `DSYNC` is supported; do not treat the two options as identical.
3. **Open normally and call `force(true)` at checkpoints:** fits some commit designs, but changes "every update synchronous" to "batched synchronization"; document and test carefully.
4. **Downgrade to best-effort writes:** only for data where loss is acceptable; report the degraded policy instead of pretending full durability remains.

Decision skeleton:

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    // Write under SYNC requirement.
} catch (UnsupportedOperationException unsupported) {
    throw new IllegalStateException(
            "Configured filesystem cannot satisfy required SYNC", unsupported);
}
```

This is an illustrative snippet in an application with a valid `Path path` and `IOException` handling. The message makes clear that the mandatory sync requirement could not be met. Do not silently reopen with plain `WRITE` if business rules require `SYNC`.

**Testing support:** a "probe" opening a temp file with the option can show whether the provider/filesystem accepts the setting under current conditions. However, it does not prove all files and mounts behave identically or cover abnormal hardware/OS failures. Always handle errors on **actual operations**, not only at startup.

## 15. Which Options Apply to `Files` APIs and `FileChannel`?

Do not assume every API allows every `OpenOption` in every configuration. For example:

- `Files.newOutputStream(path, options...)` accepts `OpenOption` and has defaults when options are omitted.
- `Files.newByteChannel(path, options, attrs...)` supports read/write via `SeekableByteChannel`.
- `FileChannel.open(path, options...)` has a clearly documented option set including `SYNC`, `DSYNC`, `DELETE_ON_CLOSE`.
- `Files.writeString(path, text, charset, options...)` configures how the file is opened, though supported options must be checked in the specific API docs; do not assume every `FileChannel` option works across all providers.
- `Files.copy` and `Files.move` take their own `CopyOption`s; do not confuse them with `StandardOpenOption`.

**Specifically:** calling `Files.newOutputStream(path)` **without options** uses default write-open semantics, usually equivalent to `CREATE`, `TRUNCATE_EXISTING`, `WRITE`. Once you pass options explicitly, understand the exact option set you specify and its impact on file creation/truncation.

## 16. Example Combining `DSYNC` and `FileChannel.force`

To illustrate two ways of requesting synchronization, this small program writes a new file with `DSYNC`, then another file using batched `force(true)`.

**File `DsyncVsForceDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class DsyncVsForceDemo {
    static void writeAll(FileChannel channel, byte[] bytes) throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("durability-demo-");
        Path dsyncFile = directory.resolve("dsync.txt");
        Path forcedFile = directory.resolve("forced.txt");

        try {
            try (FileChannel channel = FileChannel.open(
                    dsyncFile,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.DSYNC)) {
                writeAll(channel, "one".getBytes(StandardCharsets.UTF_8));
            }

            try (FileChannel channel = FileChannel.open(
                    forcedFile,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                writeAll(channel, "two".getBytes(StandardCharsets.UTF_8));
                channel.force(true);
            }

            System.out.println("DSYNC content: "
                    + Files.readString(dsyncFile, StandardCharsets.UTF_8));
            System.out.println("force content: "
                    + Files.readString(forcedFile, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(dsyncFile);
            Files.deleteIfExists(forcedFile);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile/run:

```bash
javac DsyncVsForceDemo.java
java DsyncVsForceDemo
```

**Stdout if provider supports the operations and succeeds:**

```text
DSYNC content: one
force content: two
```

The example does not measure latency or simulate crashes. Its purpose is showing **how requests are expressed**:

- The first file opens with `DSYNC` from the start, so each content update on the channel carries that sync requirement.
- The second file opens for normal writing, then `force(true)` is called at the final checkpoint to request syncing content and metadata.

If your goal is multi-file durability or directory metadata updates, these single calls do not prove an entire multi-step transaction recovers atomically after a crash.

## 17. `SYNC`/`DSYNC` and Atomicity: Do Not Confuse with `ATOMIC_MOVE`

In Java NIO, `StandardCopyOption.ATOMIC_MOVE` is for moving/renaming files atomically when supported by the provider. It addresses **atomic renaming**, whereas `SYNC`/`DSYNC` request **synchronous file updates**.

```text
Write temp file    ───► sync content (per policy)
       │
       ▼
Close temp file
       │
       ▼
Rename / move to target file ───► may request atomic move
       │
       ▼
Consider durability of directory / filesystem metadata
```

Even when a file has been written synchronously, the **rename** step can have its own durability requirements for the directory entry. A crash-safe transaction requires understanding the filesystem, directory metadata behavior, and recovery design, rather than mechanically adding `SYNC` or `ATOMIC_MOVE`.

`ATOMIC_MOVE` can throw `AtomicMoveNotSupportedException` if unsupported. Never silently fall back to a regular move while claiming the operation remains atomic. Creating the file with `DELETE_ON_CLOSE` also typically complicates renaming workflows, since that option aims to delete the work file on close.

## 18. Logging, Performance, and Consistency

Requesting synchronization after every update can be expensive. For instance, a service writing 10,000 small records with one synchronous syscall/write per record behaves very differently from batching many records and calling `force` at commit points.

**However, batching has trade-offs:** waiting for an interval before calling `force` means data between checkpoints can be lost if the system crashes. Choose based on business requirements:

| Desired characteristic | Common implementation approach |
| --- | --- |
| Prioritize fast sequential writes, minor data loss acceptable | Buffered writes + batched checkpoints |
| Every update needs higher synchronization | `SYNC` or `DSYNC` per policy |
| Control sync timing at transaction boundaries | `FileChannel.force(true/false)` |
| Atomic replacement of a config file | Temp file + atomic move if supported + dedicated durability plan |
| Single-use self-cleaning temp file | `DELETE_ON_CLOSE` when suitable and supported |

Do not benchmark `Files.writeString` and extrapolate directly to every file-open mode. Benchmarks must use representative file types, record sizes, filesystems, hardware, and durability modes.

## 19. Relationship with `try-with-resources` and Wrapper Streams

Options like `DELETE_ON_CLOSE` apply to the **opened resource**. If an output stream is wrapped in `BufferedOutputStream`, closing the outer wrapper normally closes the underlying delegate, thereby triggering best-effort deletion.

```java
try (OutputStream output = new BufferedOutputStream(
        Files.newOutputStream(temp,
                StandardOpenOption.WRITE,
                StandardOpenOption.DELETE_ON_CLOSE))) {
    output.write(payload);
}
```

This is an illustrative snippet with an existing temp file `temp` and `byte[] payload`, requiring relevant imports. `BufferedOutputStream` may hold data in RAM until flush/close, whereas `SYNC`/`DSYNC` on the underlying resource only applies to **updates that actually reach the file layer**. When precise sync timing is required, control wrapper flush ordering before forcing the appropriate channel.

If a resource is **owned by the caller**, never close it arbitrarily just to trigger `DELETE_ON_CLOSE`; keep ownership clear. In particular, never wrap `System.out` or shared streams and call `close()` casually.

## 20. Common Mistakes

| Misconception | Why it is wrong | Correct understanding |
| --- | --- | --- |
| `SYNC` is just like `flush()` | `flush()` handles application buffers; `SYNC` is a file-open sync option | Distinguish buffer layers from storage devices |
| `DSYNC` and `SYNC` are identical | Metadata falls under different scopes | Choose per content/metadata policy |
| `DSYNC` is always faster than `SYNC` | Performance depends on workload/provider/OS | Benchmark in the real environment |
| `SYNC` makes multi-file transactions atomic | There is no general multi-file transaction mechanism | Design commit/rename/recovery explicitly |
| `FileChannel.force(false)` syncs all metadata | `false` requests content only | Use `true` when metadata is required by contract |
| `DELETE_ON_CLOSE` always deletes immediately | Only best effort; timing is implementation-specific | Manage cleanup and verify appropriately |
| `DELETE_ON_CLOSE` is secure erase | Does not guarantee physical wiping or clearing backups | Maintain a dedicated data-security policy |
| `Files.createTempFile` auto-deletes when any stream closes | No such default deletion policy exists | Delete explicitly or open with appropriate options |
| Every provider supports `SYNC`/`DSYNC`/`DELETE_ON_CLOSE` | Not guaranteed | Handle `UnsupportedOperationException` |
| Catching `IOException` covers all open-option errors | Invalid options can throw unchecked exceptions | Handle `IllegalArgumentException`, `UnsupportedOperationException` |
| Probing once at startup proves permanent support | Filesystems/mounts can differ or change | Handle errors on actual operations |
| Falling back by dropping `SYNC` while still reporting "durable" | Changes the durability contract | Fail or explicitly document downgraded guarantees |
| Combining `APPEND`/`TRUNCATE` arbitrarily | Some combinations are invalid or have distinct semantics | Read the API contract and test |
| Reading the file back to verify durability | OS cache can serve the read | Distinguish functional tests from crash recovery |

## 21. Practice Exercises

1. Run `SyncWriteDemo` on your OS/provider. Observe the result and explain why reading the content back successfully does not prove crash durability.
2. Replace `SYNC` with `DSYNC` in `SyncWriteDemo`. Check the output and state the difference in metadata guarantee scope.
3. Run `DsyncVsForceDemo` and try `channel.force(false)` instead of `true`; explain what the parameter means.
4. Measure the time to write many small records with normal writes, `DSYNC`, and `SYNC`. Document the machine, filesystem, write count, and cache/benchmark caveats.
5. Run `DeleteOnCloseDemo`, print existence status before/after `close()` on your current provider, and compare with best-effort semantics.
6. Remove `try-with-resources` in `DeleteOnCloseDemo` and explain why the file lifecycle becomes unreliable; then restore the proper version.
7. Create a temp file with `Files.createTempFile` without `DELETE_ON_CLOSE`. Confirm that closing a normal `OutputStream` does not delete the file.
8. Write a test with `CREATE_NEW`: open an existing file and verify the error; explain why this option helps prevent overwrites.
9. Try another provider (e.g., ZIP filesystem if supported in your environment). Observe if `SYNC` or `DELETE_ON_CLOSE` is rejected; do not ignore errors silently.
10. Design a fallback policy: if `SYNC` is rejected, should the service reject the operation or downgrade? Explain the business impact.
11. Explain why an unflushed `BufferedOutputStream` cannot be synced to disk merely by calling `force` on an underlying `FileChannel`.
12. Distinguish `DELETE_ON_CLOSE` from secure file deletion for sensitive data.
13. Design a configuration-file replacement workflow: temp file, write, sync, close, move, and cleanup. State the limits of `ATOMIC_MOVE` as well as directory metadata durability.
14. Explain why a provider accepting `SYNC` when opening a file does not mean the application automatically gains transactions and recovery logic.

## 22. Key Takeaways

`SYNC`, `DSYNC`, and `DELETE_ON_CLOSE` are **requests about how files are opened and managed**, carried out by the provider/OS/filesystem within specific limits.

1. **`SYNC`:** requests synchronous updates of content or metadata to the storage device.
2. **`DSYNC`:** requests synchronous updates of content; does not match `SYNC`'s metadata scope.
3. **`DELETE_ON_CLOSE`:** requests file deletion on close on a **best-effort** basis, not a guaranteed deletion or secure erase.
4. **`FileChannel.force()`:** requests synchronization at chosen checkpoints; understand local vs. non-local device limits and metadata behavior.
5. **Provider support:** never assume options are universal. Handle `UnsupportedOperationException`, `IllegalArgumentException`, and `IOException` per contract without silently weakening durability guarantees.
6. **Proper lifecycle:** always close resources you own via `try-with-resources`; never rely on finalizers or JVM shutdown to delete temp files.
7. **Proper architecture:** synchronous updates differ from atomicity; single- or multi-file integrity requires a recovery protocol tailored to the problem.

### Official References

- [Java SE 17: `StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html), sections on `SYNC`, `DSYNC`, and `DELETE_ON_CLOSE`.
- [Java SE 17: `FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html), `open` overloads and `force(boolean)`.
- [Java SE 17: `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), file open/write/delete methods.
- [Java SE 17: `FileSystemProvider`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html), filesystem extension point.
- [Java SE 17: `StandardCopyOption.ATOMIC_MOVE`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html), distinguishing atomic move from synchronous write policies.