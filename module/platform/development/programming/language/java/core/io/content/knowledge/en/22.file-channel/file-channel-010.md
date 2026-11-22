# FileChannel: Append and OS-Dependent Behaviors

When writing to the end of a file with Java NIO, choosing `StandardOpenOption.APPEND` directly affects the **write position**, **multi-process concurrent writing**, and **data consistency**. A program that runs fine on a development machine does not necessarily exhibit the same atomicity, file locking, data durability, or access permissions when running on another operating system and filesystem.

This article focuses on `java.nio.channels.FileChannel`: how append differs from `position(size())`, how to open a channel safely, loops that write all bytes, atomicity limits, file locking, `force`/`SYNC`/`DSYNC`, and common differences across local filesystems, network filesystems, and deployment platforms.

## 1. What Does Append Actually Mean?

`FileChannel` works with two distinct positions:

- **File position**: the channel's next byte offset, accessed via `channel.position()` and adjusted with `position(long)`.
- **Buffer position**: the next byte in the `ByteBuffer` passed to `write(buffer)`; increases by the number of bytes actually written.

In normal mode (without `APPEND`), a `write(buffer)` call starts at the **FileChannel's current position**. In `APPEND` mode, each **relative write** call moves the file position to the **current end of the file** and then writes the data.

```text
Initial file:       [A][B][C]
                    0  1  2   EOF=3

Normal WRITE, position(1), write "X":
                    [A][X][C]
                    Does not automatically append at the end.

APPEND, write "X":
                    [A][B][C][X]
                    Write moves to the end of the file before writing.
```

Important point: the API specification **does not guarantee** that "positioning to EOF + writing data" occurs as **one atomic operation** across all operating systems. Therefore, you cannot deduce that two concurrent writers will automatically write independent, complete, non-interleaved records.

## 2. Opening FileChannel: APPEND and Related OpenOptions

Common form:

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND)) {
    // Write to the end of the file using channel.write(buffer).
}
```

This is a snippet: `path` is a valid `Path`, and you must import `java.nio.channels.FileChannel` along with `java.nio.file.StandardOpenOption`. The `APPEND` argument already implies opening for writing; adding `WRITE` makes the intent clearer.

| Option | Behavior | Notes |
| --- | --- | --- |
| `WRITE` | Allows writing to the file; normally starts at offset 0 without APPEND. | Writing from the start **overwrites corresponding bytes**, without erasing all old contents. |
| `APPEND` | Each relative `write` writes starting at the current end of the file. | Atomicity of seeking to EOF then writing depends on the system. |
| `CREATE` | Opens an existing file or creates it if missing when opened for writing. | Does **not** mean truncating an existing file. |
| `CREATE_NEW` | Creates a new file and fails if it already exists. | Existence check and creation are atomic per the API/provider contract. |
| `TRUNCATE_EXISTING` | Clears an existing file's content to length 0 when opened for writing. | **Cannot be used with APPEND**. |
| `READ` | Allows reading the file. | **Cannot be used with APPEND** per the `FileChannel.open` contract. |
| `SYNC` | Requests synchronizing both content and metadata updates to the storage device. | Can be slow; actual effect depends on the I/O environment. |
| `DSYNC` | Requests synchronizing content updates to the storage device. | Do not infer that all metadata is durable. |
| `DELETE_ON_CLOSE` | Attempts to delete the file when closing the channel. | *Best-effort* behavior, not guaranteed to delete on every OS. |
| `SPARSE` | Hints to use a sparse file when creating a new file. | Hint only; the provider/filesystem may ignore it. |

**Invalid** combinations:

```java
// Invalid: APPEND cannot be combined with READ.
FileChannel.open(path, StandardOpenOption.APPEND,
        StandardOpenOption.READ);

// Invalid: APPEND cannot be combined with TRUNCATE_EXISTING.
FileChannel.open(path, StandardOpenOption.APPEND,
        StandardOpenOption.TRUNCATE_EXISTING);
```

These are **anti-examples** showing misconfigurations, not to be run in production code. Invalid combinations typically throw `IllegalArgumentException` when opening the channel. If you want to read and then append, read via a separate channel first, then close and open an append channel; or design an appropriate processing flow without placing `READ` into the APPEND option set.

**Note:** `CREATE_NEW` serves to avoid overwriting on **initial creation**. It does not help multiple concurrent writers serialize appends **after the file already exists**.

## 3. Java 17+ Example: Append Two Lines, Then Overwrite the Start of the File

The program below creates a dedicated temporary file and exercises both mechanisms so their differences are clear:

1. Write initial content `seed\n`.
2. Use `APPEND` to add `one\n` and `two\n`.
3. Close the channel, reopen with `WRITE` only, set file position to 0, and write `HEAD\n`; because it has the same byte count as `seed\n`, the appended tail remains intact.
4. Read back the contents, check byte size, and delete the file after handles are closed.

Save as **`FileChannelAppendDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelAppendDemo {

    private static ByteBuffer utf8(String value) {
        return ByteBuffer.wrap(
                value.getBytes(StandardCharsets.UTF_8));
    }

    private static void writeFully(FileChannel channel, ByteBuffer data)
            throws IOException {
        while (data.hasRemaining()) {
            int written = channel.write(data);
            if (written == 0) {
                throw new IOException("Ghi file không có tiến triển");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("filechannel-append-", ".txt");
        try {
            Files.writeString(file, "seed\n", StandardCharsets.UTF_8);

            try (FileChannel append = FileChannel.open(
                    file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND)) {
                writeFully(append, utf8("one\n"));
                writeFully(append, utf8("two\n"));
                append.force(true);
            }

            // WRITE without APPEND: can choose an offset to overwrite.
            try (FileChannel overwrite = FileChannel.open(
                    file, StandardOpenOption.WRITE)) {
                overwrite.position(0);
                writeFully(overwrite, utf8("HEAD\n"));
            }

            String result = Files.readString(
                    file, StandardCharsets.UTF_8);
            System.out.println("content=" + result.replace('\n', '|'));
            System.out.println("bytes=" + Files.size(file));
            System.out.println("correct="
                    + "HEAD\none\ntwo\n".equals(result));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run with Java 17+:

```bash
javac FileChannelAppendDemo.java
java FileChannelAppendDemo
```

Stdout for a standalone run on a filesystem supporting the used options:

```text
content=HEAD|one|two|
bytes=13
correct=true
```

**Detailed explanation:**

- `Files.createTempFile` allocates an isolated file; no second process writes concurrently, so the write order in the demo is deterministic.
- `Files.writeString` by default writes/truncates existing content of the file, creating the exact 5 initial ASCII bytes.
- `FileChannel.open(..., APPEND)` directs subsequent relative `write` calls to EOF regardless of prior file position. `writeFully` handles cases where a single `write` transfers only part of the buffer; after each pass, the channel advances `ByteBuffer.position()`.
- The two appends add 4 + 4 bytes respectively, totaling 13 bytes. The strings here are ASCII so UTF-8 byte count matches code-unit count; with Vietnamese text, compute bytes via `getBytes(UTF_8)`.
- `force(true)` requests flushing updates made by the append channel to the device on a local file, subject to the API contract; it does **not** turn appending into a multi-process transaction.
- Channel `overwrite` does not enable append, so `position(0)` and writing `HEAD\n` replaces the exact first 5 bytes. The file stays 13 bytes long because `TRUNCATE_EXISTING` is not used.

**Limitation of this example:** `writeFully`'s "no progress" exception is a *fail-fast* policy to avoid accidental infinite loops; a FileChannel writing regular files does not use `SocketChannel`'s non-blocking model. For other channel types, a return value of 0 may require waiting for readiness. Do not copy this policy blindly to every channel type.

## 4. APPEND Is Not Equivalent to position(size())

Another way to write at the end of a file is:

```java
// Snippet: channel opened with WRITE, without APPEND.
channel.position(channel.size());
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
```

This approach **can be correct when only a single writer owns the file**, but with multiple writers, reading `size()`, setting `position()`, and writing are **several separate steps**. Another writer could extend or modify the file in between, so the program might overwrite newly added data or use a stale offset.

In `APPEND` mode, the provider attempts to ensure each relative `write` goes to EOF right before writing, yet the Java contract still leaves atomicity OS-dependent. On some systems, a single kernel append call executes atomically with respect to offset updates; on other systems, especially with network filesystems, semantics may differ. **Never generalize multi-writer behavior from a single run on a laptop.**

Additionally:

- `FileChannel.write(ByteBuffer src, long position)` is a **positional write**. When a channel has `APPEND` enabled, **the effect of positional writes is not uniformly defined per the Javadoc**. Do not use this combination to "patch" a byte at a fixed offset in an append channel.
- Calling `position(0)` on an append channel is not a strategy for updating a header: relative writes still follow append mode.
- To edit a header at offset 0, use a channel **without** `APPEND` enabled that has write permission, separated from the append stream if needed.

Comparison table:

| Write method | Starting position | Should it be treated as multi-writer safe append? |
| --- | --- | --- |
| `WRITE` then `position(size())` | EOF offset read when `size` was called | No; races can occur between steps. |
| `WRITE + APPEND`, `write(buffer)` | EOF on each relative write | No universal atomicity guarantee across all OSes/providers. |
| `WRITE` then `write(buffer, offset)` | Explicit offset managed by application | Safe only if write regions and writers are properly coordinated. |
| `APPEND` then `write(buffer, offset)` | **No portable semantics** | Avoid using. |

## 5. "One Record" May Consist of Multiple Writes

Suppose a record has a length header and a payload:

```java
// Snippet: APPEND channel, buffers fully prepared.
writeFully(channel, header);
writeFully(channel, payload);
```

Even if each individual `write` were atomic on a specific filesystem, **there is no guarantee two consecutive calls are merged into a single transaction**. Another writer can insert data between the header and payload. Moreover, `writeFully` may have to call `write` multiple times if partial writes occur.

When each record must appear as a unified block:

1. Encode the record into a single `ByteBuffer` before writing when size permits; this reduces write calls yet **does not create portable atomicity**.
2. Designate a **single writer** or a coordinated write queue inside one JVM; ensure one record finishes completely before the next begins.
3. If multiple JVMs/processes exist, use a coordination mechanism tested on the **target filesystem**, such as a single writer service or an agreed-upon lock protocol; do not assume Java automatically serializes all programs.
4. Define clear record framing (magic, length, checksum/CRC, version), verify on read, and maintain a strategy to detect/truncate incomplete tails.
5. If multi-record transactions, rollback, or high concurrency are needed, consider a database or an append-only log with a dedicated commit mechanism.

A single `write(ByteBuffer[])` (gathering write) can likewise transfer fewer bytes than the total `remaining()` and carries no promise that every OS writes the entire record atomically. You still must inspect the return value and each buffer's position.

## 6. Concurrency Within One JVM: What Is Serialized?

`FileChannel` is safe for concurrent method calls from multiple threads regarding channel-object thread safety. However, it **does not provide transactions or record boundaries** for the application. By the JDK contract:

- On **one FileChannel**, at most one operation involving the file position or capable of changing file size proceeds at a time; a second operation of this kind must wait. This does **not** mean a sequence of multiple `write` calls for a record becomes atomic.
- Positional operations at explicit offsets can proceed concurrently; actual parallel execution depends on the implementation.
- Multiple separate FileChannels, and especially multiple separate processes, need their own coordination mechanism when writing to the same file.

For example, if multiple threads call an `appendRecord` helper consisting of 3 writes, calls from different threads can still interleave at write boundaries. Lock the **entire record-writing block** or funnel records through a queue to a single writer. Never use a local variable `long localOffset = channel.size()` to hand out offsets yourself while other writers have the file open.

When coordinating multiple processes, concurrency tests must involve **multiple real OS processes**, not merely multiple threads sharing one channel object.

## 7. FileLock: Useful, Yet Not a Replacement for Transactions

`FileChannel.lock()` requests an exclusive lock, typically covering `[0, Long.MAX_VALUE)`. You can use `tryLock()` to attempt acquiring the lock without waiting; it may return `null` if another process holds a conflicting lock.

Illustrative example (not a standalone program):

```java
// channel: FileChannel opened with WRITE.
// Policy: every cooperating writer must follow the same locking convention.
try (FileLock ignored = channel.lock()) {
    writeFully(channel, recordBuffer);
}
```

Requires importing `java.nio.channels.FileLock`; `writeFully` is a helper like in the full example. Notes:

- Locks on some OSes are **advisory**, whereas elsewhere they may be mandatory; do not assume uncooperative processes will obey them.
- Some filesystems may not support shared locks or may upgrade shared requests to exclusive. Check `FileLock.isShared()` when that matters.
- Locks are held on behalf of the **entire JVM**, so they are unsuitable as a mutex between threads within the same JVM; use application-level synchronization.
- `OverlappingFileLockException` can occur if the JVM already holds or has a pending overlapping lock. `lock()` may block; `tryLock()` does not necessarily replace safe timeout and retry strategies.
- For a file that keeps growing, ensure the chosen lock range covers the region that may grow; locking only the first few bytes does not lock bytes outside that range.
- Locking behavior on network filesystems depends on protocol/mount/server and network conditions. Test on the actual deployment environment.

A well-coordinated lock can prevent cooperating writers from interleaving when writing records; it does **not** automatically roll back a record if a process dies mid-write.

## 8. force(true), force(false), SYNC, and DSYNC

`FileChannel.force(boolean metaData)` requests updates be written to the storage device; on a **local device**, the Javadoc provides a guarantee for eligible updates made by that channel. For **non-local devices**, there is no equivalent commitment.

| Mechanism | Scope per API contract | When invoked | Limitations |
| --- | --- | --- | --- |
| `force(false)` | Requests flushing **content** changes. | After writing critical data. | Metadata may not yet be synced; exact effect is platform-dependent. |
| `force(true)` | Requests flushing both **content and metadata**. | When related size/timestamp info must also be synced. | Does not make multiple writes atomic. |
| `SYNC` | Requests syncing content and metadata on each update. | Selected when opening the file. | I/O overhead can be high. |
| `DSYNC` | Requests syncing content on each update. | Selected when opening the file. | Must not be read as guaranteeing all metadata is durable. |

`force` only commits the kinds of changes specified by the API. For a `MappedByteBuffer` modified directly, consider `MappedByteBuffer.force()`; do not assume `FileChannel.force()` guarantees changes made through memory mapping.

**Durability differs from atomicity:** you can flush an **incomplete** record to disk. `force(true)` cannot rescue a format lacking framing/CRC and cannot coordinate multiple writers. In a workflow that creates a **new file then replaces an old file**, atomic move support and directory metadata durability are separate concerns requiring provider/OS-appropriate design.

Flushing Java buffers, closing `FileChannel`, calling `force`, and using `SYNC` must none of them be confused with a multi-step data transaction capable of rollback.

## 9. OS- and Filesystem-Dependent Behaviors

Important differences when moving code to production:

### 9.1 Append Atomicity and Network Filesystems

On systems supporting atomic append in a single system call, each write may be protected from certain inter-process races. Even so, the JDK does not promise that on **every** system. Network filesystems (such as NFS/SMB depending on configuration) introduce client caches, cross-client synchronization, and protocol layers; never assume ext4 behavior on one machine matches a network volume.

### 9.2 Visibility of New Data in Other Processes

FileChannels within the **same Java program** have view-consistency guarantees as described by the JDK. For another process, visible data may be affected by OS caching or network filesystem protocol delays. A reader reading while a writer is updating can still observe an **incomplete record** according to the application schema.

### 9.3 Open Files and Deleting, Renaming, Replacing

On POSIX platforms, unlinking an open file can succeed: the old handle keeps accessing the underlying object until closed. On Windows, deleting/renaming an open file may fail depending on sharing modes and active handles. Never design a log-rotation/replacement mechanism assuming a single platform. Close unneeded handles, catch `IOException`, and test replacement/moves on the target volume, filesystem, and OS.

### 9.4 Permissions, Timestamps, and Symbolic Links

POSIX permissions, Windows ACLs, metadata timestamps, symbolic link handling, and case sensitivity differ across providers and filesystems. `CREATE` does not bypass permissions. `FileChannel.open` can fail due to insufficient permissions, path pointing to a directory, file held by another process in an incompatible share mode, quotas, or a read-only filesystem.

If paths come from user input, enforce access controls, allowed directories, and symbolic link rules per security policy. Never build log filenames from external input without normalizing and validating the path.

### 9.5 Longer Files, Data Gaps, and Sparse Files

`channel.position(channel.size() + gap)` **does not automatically extend** the file. When writing at the new position afterward, the file expands and the bytes in the gap between the old EOF and the new region have values **not guaranteed** by the FileChannel contract. If a binary format needs blank regions, initialize data explicitly and define a policy. `SPARSE` is only a hint at creation time, not a promise of reduced disk usage.

### 9.6 DELETE_ON_CLOSE and Resource Cleanup

`DELETE_ON_CLOSE` is best-effort only. Availability and deletion timing can depend on platform, open handles, or permissions. For temporary data that must be cleaned up, use a dedicated temp directory, close all streams/channels, handle deletion errors, and have a supplementary cleanup procedure.

## 10. Avoid Confusing "Atomic" Concepts

In a logging or journaling system, there are multiple independent levels:

| Concept | Achievable via | What is **not** guaranteed |
| --- | --- | --- |
| Create new file if absent | `CREATE_NEW` | That appending a record is automatically safe across writers. |
| Append on each write call | `APPEND` | That seeking EOF + writing is atomic on every OS. |
| Prevent cooperating writers from writing simultaneously | Shared lock protocol or single writer | Uncooperative processes cannot modify the file; no rollback. |
| Push bytes to device | `force` or `SYNC/DSYNC` | Well-formed, untorn records, or multi-record transactions. |
| Replace a path with another file | `Files.move(..., ATOMIC_MOVE)` if provider supports | All metadata/data is durable or atomic across filesystems. |
| Verify a complete record | Header/length/checksum/trailer checked on read | File wasn't tampered with by unauthorized actors; checksum is not authentication. |

`Files.move(..., StandardCopyOption.ATOMIC_MOVE)` may throw `AtomicMoveNotSupportedException`, and behavior when replacing an existing target depends on provider/OS. If real guarantees are required, never ignore the exception and falsely claim file replacement was atomic.

## 11. Implementation Strategies by Need

**Simple application, single writer only:** open `APPEND + CREATE + WRITE`, use one buffer containing the complete record, `while (hasRemaining())` to write all bytes, and close the channel. Choose `force` frequency per durability requirements; avoid calling `force` after every record if the cost is unacceptable.

**Multiple threads in the same JVM:** send all records through a queue drained by a single writer thread, or lock the entire record-writing block inside the application. Do not rely on `FileChannel` thread safety to turn 2–3 write calls into a transaction.

**Multiple processes on the same machine:** coordinate via a single-writer process or a lock obeyed by all processes, paired with framing and recovery. Verify the exact filesystem; on failure, determine which records committed based on the format rather than guessing from a single successful `write`.

**Multiple hosts / network filesystem:** avoid relying on atomic append without a clearly verified contract. Consider a centralized writer service, message broker, or transactional database, accounting for retries, network partitions, and recovery.

**Writing config files or snapshots for replacement:** typically create a new file in the target directory, write completely, flush/force as needed, then move/replace while checking atomicity support and handling errors. This is a **different** workflow from log appending.

**Many short writes:** consider application-level buffering while flushing on time and managing crash recovery. Batching multiple records into one buffer can improve throughput; it does not automatically ensure all records commit atomically together.

## 12. Common Mistakes and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Opening channel throws `IllegalArgumentException` | Combining `APPEND + READ` or `APPEND + TRUNCATE_EXISTING`. | Use valid open options; separate read and append flows. |
| Old content gets altered | Opened `WRITE` and wrote from offset 0 thinking it appends. | Choose `APPEND` when appending to the end of the file. |
| File is not emptied | Used `CREATE` without `TRUNCATE_EXISTING`. | Use truncate when genuinely rewriting the whole file, without APPEND. |
| Overwrites new data from another process | Computing `size()` then `position(size)` has a race. | Single writer/lock; do not treat seeking EOF as atomic append. |
| Corrupt log or interleaved records | Multiple writes per record or interleaved writers. | Framing, writer coordination, recovery on restart. |
| Written data is incomplete | Called `write(buffer)` only once. | Loop until `!buffer.hasRemaining()`. |
| Enabling APPEND while trying to write a header at a fixed offset | Positional write under APPEND lacks portable semantics. | Use a non-APPEND channel for positional updates with coordination. |
| File locks behave differently than on dev machine | Advisory/mandatory differences; network shares behave differently. | Agree on lock protocol; test multi-process on the real system. |
| Called `force(true)` yet reader sees partial record | `force` does not provide transactions. | Design commit framing/checksums and reader synchronization. |
| Deleting/renaming an open file fails | Differences in OS/file-sharing modes/providers. | Close handles, handle `IOException`, test rotation workflow. |
| File byte count does not equal character count | UTF-8 text contains multi-byte Unicode. | Measure `ByteBuffer.remaining()` or `getBytes(UTF_8).length`. |

## 13. Practice and Evaluation Questions

**Exercise 1 — Observe overwrite vs. append.** Run the sample program after removing `APPEND` from the first channel open while keeping the `writeFully` calls unchanged. Predict the resulting file: writes start at position 0 and continue from the post-write position; old content may be replaced and file size depends on bytes written. Explain why `CREATE` does not alter positioning behavior.

**Exercise 2 — Separate header from log.** A file has a fixed version/count header in the first 16 bytes and a log section afterward. Design a two-phase approach: update the header using a normal `WRITE` channel (without APPEND) and close it; write new records via an `APPEND` channel. State the risks if both happen concurrently and why a commit protocol is needed instead of relying on two independent operations.

**Exercise 3 — Test concurrent writers.** Create two independent programs, each appending 1,000 records formatted as `length + payload + CRC`. Run on a local filesystem and then on a network filesystem (if available). Compare valid record counts, interleaved slices, short writes, and append behavior; never treat a single test run as proof of portable atomicity.

**Exercise 4 — Simulate a crash.** Write header and payload with two write calls, deliberately terminating the program mid-way in a test environment. Build a reader that scans the file up to the last fully verified record, detects the incomplete tail, and implements a controlled truncate/recovery policy.

**Exercise 5 — Compare `force`.** Use three configurations: no force, `force(false)`, `force(true)`. Measure write latency on a file in a dedicated test environment; explain how performance, caching, metadata, and storage devices influence the numbers. Never run crash/power-cut tests on systems holding real data.

**Self-check:**

1. Why does `APPEND` differ from `channel.position(channel.size())` in a multi-writer environment?
2. Why shouldn't `FileChannel.write(buffer, offset)` be used when APPEND is enabled?
3. Does calling `force(true)` guarantee that 3 write calls become a transaction?
4. Does `FileLock` resolve contention between threads inside the same JVM?
5. Why does a large record split across multiple writes still need framing and recovery?
6. Which OS/filesystem differences can affect log rotation, shared locks, and visibility?

## 14. References

- [Java SE 21 — FileChannel API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): official specification of APPEND, file position, `force`, locks, concurrency, and system-dependent behavior.
- [Java SE 21 — StandardOpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html): definitions of `APPEND`, `CREATE_NEW`, `SYNC`, `DSYNC`, and file-open options.

**Takeaway:** `APPEND` specifies **moving to EOF before each relative write**, yet provides no OS-independent multi-writer atomicity guarantee. Only by combining `writeFully`, appropriate file-ownership/locking protocols, recoverable record formats, a durability strategy, and testing on the real deployment filesystem can you build a reliable append mechanism.
