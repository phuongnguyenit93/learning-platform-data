# FileChannel.force(boolean) and Scope of Guarantees with Storage Devices

When writing a file in Java, a successful return from `FileChannel.write(...)` **does not mean** the data has reached a persistent storage device. Operating systems and devices routinely use caching layers to boost speed. The `FileChannel.force(boolean metaData)` method requests flushing changes covered by the channel's contract down to the storage device containing the file. It is an important tool when an application stores data that must survive system crashes, yet it is **not a transaction, not a write lock, and not an absolute guarantee against all hardware failures or remote storage issues**.

Goals after this lesson:

1. Understand what `force(false)` and `force(true)` request to be written.
2. Distinguish file data, file metadata, and directory name entries.
3. Identify the exact boundary of guarantees across local storage, remote storage, OS, filesystem, controller, and caches.
4. Use `FileChannel.force`, `MappedByteBuffer.force`, and `SYNC`/`DSYNC` options in the right situations.
5. Design an appropriate write sequence and testing strategy when both *durability* and *atomicity* are required.

## 1. Why Can Data Still Be Lost After Calling write?

A file write operation typically passes through multiple layers:

```text
Java Application
    |
    | FileChannel.write(ByteBuffer)
    v
JDK / OS system call
    |
    v
OS buffer / page cache
    |
    v
Filesystem / block layer / driver
    |
    v
Controller or device cache
    |
    v
Actual storage device
    (SSD, HDD, persistent memory, network device...)
```

This diagram is a conceptual model for understanding layers of responsibility; the actual I/O path depends on the OS, filesystem, and device type. A `write` call may complete as soon as data is accepted into the OS cache, before being confirmed durably written on the device. Caching makes an immediate read-back right after writing typically see the new data, even though a subsequent power loss could lead to a different outcome.

Distinguish these states:

- **Data accepted by the write operation:** `channel.write(buffer)` returns the number of bytes actually processed; looping is still required if the buffer is not yet empty.
- **Data visible on read-back:** reads through the same OS may read from cache. That proves current logical content, **not power-loss recoverability**.
- **Data requested to sync to the device:** `channel.force(...)` completes per Java's contract for files on local storage and covered modifications.
- **Application recovers consistently after a crash:** beyond flushing, you must handle incomplete transactions/records, directory metadata, and write ordering. `force` alone does not create a transaction.

**`OutputStream.flush()` and `FileChannel.force(...)` do not share the same meaning.** `flush` pushes bytes buffered at the stream layer per the implementation's contract; it makes no promise that data is on the storage device. `FileChannel` has no analogous `flush()` method: use `force` for file synchronization requests.

## 2. Official Contract of FileChannel.force

Signature:

```java
public abstract void force(boolean metaData) throws IOException
```

The method returns **`void`**; normal completion indicates the force operation was executed per contract, without reporting flushed byte counts or physical data locations. `ClosedChannelException` may occur if the channel is closed; other I/O errors are reported via `IOException`.

Per the Java SE 21 Javadoc:

- If the file resides on a **local storage device**, when `force` returns normally, all changes within the API-guaranteed scope since channel creation or the last `force` call are requested to be written to that device.
- If the file **does not reside on a local device**, Java **does not provide the same guarantee**. Network drives and some virtual/distributed filesystems are situations requiring careful examination.
- `metaData=false`: only **file content** is required to be forced as requested.
- `metaData=true`: both **file content and metadata** must be forced. The exact effect of the parameter depends on the OS and may incur additional I/O.
- The contract covers modifications made through **FileChannel methods**, or through an associated `FileOutputStream`/`RandomAccessFile` if the channel was obtained via `getChannel()`. Changes through a `MappedByteBuffer` follow separate rules.

The phrase "written to that device" should be understood **within the bounds of the OS/device interface honoring the contract**. Java itself cannot verify that firmware actually protected data against every controller failure, buggy firmware, power loss on systems without cache protection, or hardware destruction.

### `force(false)` vs. `force(true)`

| Call | Part requested to synchronize | Usage scope and notes |
| --- | --- | --- |
| `channel.force(false)` | Modified content bytes within API scope. | Suitable when only file content needs confirmation without syncing all metadata. **Does not imply** new file size or directory info is as durable as content. |
| `channel.force(true)` | Content **and file metadata**. | May be needed when changing size, timestamps, or accompanying metadata. Does not mean all parent directory info, renames, or the entire filesystem was forced. |
| `channel.close()` | Releases resources. | Not a replacement API for `force` with the same durability sync contract. Do not rely on `close` alone for crash safety. |
| `OutputStream.flush()` | Pushes buffered bytes at the stream layer. | Carries no `FileChannel.force` durability contract. |
| `MappedByteBuffer.force()` | Requests forcing changes of the *mapping* (see Section 5). | Not identical to `channel.force` when data is modified via mapped memory. |

For example, when an application updates a fixed-size record in an existing file: `force(false)` clearly expresses the intent to ensure content. When extending file length or creating a new file, `force(true)` is usually a prudent choice to request syncing related metadata. However, **choosing this parameter does not turn a sequence of updates across multiple files or a directory into a transaction**.

## 3. What FileChannel.force Covers — and What It Does Not

### 3.1. Changes via the Channel and Associated I/O Objects

`force` is defined for file changes made through `FileChannel`. If `FileOutputStream.getChannel()` or `RandomAccessFile.getChannel()` created the channel, changes made via the associated stream/random-access file fall within the force-write contract described in the Javadoc.

```java
// API illustration (not a standalone program).
try (RandomAccessFile raf = new RandomAccessFile(path.toFile(), "rw")) {
    raf.seek(0);
    raf.writeInt(42);
    raf.getChannel().force(true);
}
```

Here `path` is an existing/writable `Path`; `RandomAccessFile`'s `getChannel()` shares the same file handle. Conversely, **do not automatically infer** that calling `force` on a separate channel covers changes made by another program, an independent handle, another API, or another process. You must know the exact writers and coordination protocol.

### 3.2. Does Not Automatically Make Writes Atomic

Suppose you write a 4 KB record and then call `force(true)`:

- If the writer wrote **part of the record** and hit an exception before reaching 4 KB, `force` does not repair the missing data.
- If two threads write overlapping byte regions without locking, `force` does not decide which thread's bytes win.
- If an application must update two files consistently together, calling `force` on each file does not provide a two-file transaction.
- If the device loses power **while** the record is being written/forced, the file may need format-level recovery: length + checksum, versioning, logs, or multiple copies with commit markers.

**Durability** means preserving committed updates according to policy. **Atomicity** means an update is observed completely or not at all. **Consistency** means data invariants remain valid. `force` aids the durability part within its scope; it does not provide application atomicity or consistency on its own.

### 3.3. Does Not Imply Forcing *Directory* Metadata

File metadata (such as size and modification timestamp) differs from the **directory entry** mapping a filename to the file. When an application creates a new file or renames a file with `Files.move`, file data and directory-entry durability are two separate issues to examine.

Example of saving configuration safely following a general pattern:

```text
1. Create a temporary file in the target directory.
2. Write the full new content into the temporary file.
3. Call FileChannel.force(true) on the temporary file; handle any IOException.
4. Close the channel.
5. Rename/replace to the target path using an atomic operation if the filesystem supports it.
6. If durability across power loss also applies to the rename operation:
   examine OS/filesystem-specific directory synchronization mechanisms.
```

This is a **protocol sketch**, not a cross-platform promise. `Files.move(..., StandardCopyOption.ATOMIC_MOVE)` requests an atomic move at the filesystem level; it **does not automatically carry a durability guarantee for the directory entry**. With `ATOMIC_MOVE`, behavior when replacing an existing target depends on the implementation; do not assume combining `REPLACE_EXISTING` works identically on every filesystem. Standard Java **has no portable API guaranteeing directory fsync across every operating system**. If business requirements demand crash protection at the filename level, verify the target platform thoroughly and you may need native APIs or dedicated storage protocols.

## 4. Runnable Example: Calling force After Finishing Writes

Create file `ForceWriteDemo.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class ForceWriteDemo {
    private static void writeAll(FileChannel channel, String text) throws IOException {
        ByteBuffer data = ByteBuffer.wrap(text.getBytes(StandardCharsets.UTF_8));
        while (data.hasRemaining()) {
            int n = channel.write(data);
            if (n == 0) throw new IOException("Write made no progress");
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("force-demo-", ".txt");
        try {
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                writeAll(channel, "first");
                channel.force(false);
                System.out.println("content-after-force-false=" +
                        Files.readString(file, StandardCharsets.UTF_8));
                System.out.println("size=" + channel.size());

                channel.truncate(0);
                channel.position(0);
                writeAll(channel, "second");
                channel.force(true);
                System.out.println("content-after-force-true=" +
                        Files.readString(file, StandardCharsets.UTF_8));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run on Java 17+:

```bash
javac --release 17 ForceWriteDemo.java
java ForceWriteDemo
```

Verified output:

```text
content-after-force-false=first
size=5
content-after-force-true=second
```

**Analysis**:

1. `Files.createTempFile` creates a new file. `FileChannel.open` opens a read/write channel.
2. `writeAll` loops until the entire `ByteBuffer` is consumed, avoiding the assumption that a single `write` call writes all bytes. If writing makes no progress, the example reports an error.
3. After writing `first`, `force(false)` requests flushing content within `FileChannel`'s scope.
4. `size()` returns `5` bytes because the example text contains only 5 ASCII characters.
5. `truncate(0)` shrinks the file to length 0; `position(0)` resets the position to write `second`. `force(true)` requests synchronizing both content and metadata.
6. Reading the file back verifies logical bytes, **not a test proving data will survive a crash**. Nor should `force(true)` be treated as proof that a new file's directory entry is durable after power loss.

The program throws `IOException` when write/force operations fail; never catch the exception and print a "saved successfully" message. Use `try-with-resources` to close the channel and `finally` to delete the temporary file in the example; the delete-after-test rule does not apply to application files meant for long-term storage.

### Why Must `force` Be Placed at the Right Commit Point?

If you write data `A`, call `force`, and then write `B`, the earlier force makes no promise that `B` is synchronized. In a multi-record writing system, the `force` call site is the chosen commit boundary:

```text
write(record1)
write(record2)
force(true)    <- request synchronization for this batch
ACK batch      <- report committed only if force does not throw
write(record3)
...            <- record3 has not been committed by the force above
```

This assumes the application has a clear record protocol, no other writer corrupts the data, and the underlying local filesystem/device honors synchronization requests. **ACK** is not data automatically emitted by Java; it is a system decision using `force`.

## 5. With Memory-Mapped Files: Remember MappedByteBuffer.force

`FileChannel.map(FileChannel.MapMode.READ_WRITE, position, size)` creates a `MappedByteBuffer` pointing to a file region. When modifying contents through the mapped buffer, changes go through the memory-mapping mechanism; the `FileChannel.force` Javadoc **does not guarantee that changes made via `put` on a mapped buffer are forced**.

Use:

```java
MappedByteBuffer mapped = channel.map(FileChannel.MapMode.READ_WRITE, 0, size);
mapped.put(0, (byte) 'A');
mapped.force(); // requests syncing changes made via mapping
```

This is an **illustrative snippet** with `channel` opened READ/WRITE and a valid `size`. Do not substitute `channel.force(false)` for `mapped.force()` just because the mapped buffer came from that channel. Remember that a mapping's lifetime can **outlive** the file channel; closing the channel does not immediately unmap on every platform.

### Standalone Example: Writing Through a Mapped Buffer

Create `MappedForceDemo.java`:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class MappedForceDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mapped-force-", ".bin");
        try {
            Files.writeString(file, "0000", StandardCharsets.US_ASCII);
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                MappedByteBuffer mapped =
                        channel.map(FileChannel.MapMode.READ_WRITE, 0, 4);
                mapped.put(0, (byte) 'A');
                mapped.put(1, (byte) 'B');
                mapped.force();
                System.out.println("mapped-view=" +
                        StandardCharsets.US_ASCII.decode(mapped.duplicate().position(0)));
            }
        } finally {
            // On some OSes, the mapping outlives the channel.
            // The test file is cleaned up when the OS permits.
            try { Files.deleteIfExists(file); } catch (IOException ignored) { }
        }
    }
}
```

```bash
javac --release 17 MappedForceDemo.java
java MappedForceDemo
```

Verified output:

```text
mapped-view=AB00
```

The example edits two bytes in the mapping, calls `mapped.force()`, and then reads back **a view of the buffer itself**. The result `AB00` verifies logic in mapped memory; **this output cannot be used to prove power-loss resilience**. `duplicate().position(0)` sets the cursor of the *copied buffer* back to the start without affecting the channel's file pointer. When using mappings in long-running applications, control the mapped region size, consistency with other writers, permissions, and resource lifetimes.

## 6. SYNC, DSYNC, and force Differ in When Synchronization Is Requested

Java provides file open options `StandardOpenOption.SYNC` and `StandardOpenOption.DSYNC`, suitable when frequent synchronization is desired:

| Mechanism | When is it synchronized? | Meaning |
| --- | --- | --- |
| `FileChannel.force(false)` | **At the `force` call site** | Requests syncing updated file content within API scope. |
| `FileChannel.force(true)` | **At the `force` call site** | Requests syncing file content and metadata. |
| `StandardOpenOption.DSYNC` | On every update performed via a channel opened with this option | Requests **content** updates be written synchronously to the device, per the NIO contract. |
| `StandardOpenOption.SYNC` | On every update performed via a channel opened with this option | Requests **content and metadata** updates be written synchronously to the device. |
| `MappedByteBuffer.force()` | **At the `force` call site on the mapping** | Synchronizes mapped buffer changes per its contract. |

`SYNC` / `DSYNC` can increase latency and I/O operation counts due to continuous synchronization. `force` lets you batch multiple writes before syncing (group commit) at the cost of widening the window of unforced changes between commits. There is no "best" choice independent of acceptable data loss, latency, throughput, and filesystem.

```java
// API illustration snippet: path is a valid, writable Path.
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    ByteBuffer data = ByteBuffer.wrap(new byte[] {1, 2, 3});
    while (data.hasRemaining()) {
        int n = channel.write(data);
        if (n == 0) throw new IOException("Write stalled");
    }
}
```

The `SYNC` option requires environment/implementation support; it may throw `UnsupportedOperationException` or `IOException` depending on cause. The snippet above illustrates mode selection, **not standalone Java source** (requires imports and declaring `path`). Do not blindly add `APPEND` or `TRUNCATE_EXISTING` when business logic does not call for them: they alter file semantics and recovery conditions.

### Should You Call force After Every Record?

It depends on the commit guarantee:

- **Single record needing immediate confirmation:** write completely, force, and only then return success if the data contract requires durability up to that point.
- **Multiple records confirmable in batches:** write records and recovery metadata, force per batch, and ACK only the records included in the completed force.
- **High-throughput log:** use a write-ahead log or dedicated database durability mechanism with group commit/CRC/checkpoint; do not replace a protocol with arbitrary `force` calls.

Calling `force` frequently is typically more expensive when sync requests increase latency; measure on the real environment, including NVMe drives, network filesystems, containers, and volume orchestration. Never promise absolute fast/slow numbers upfront.

## 7. Scope of Guarantees Across Operating Systems and Device Types

| Environment | What can be concluded? | What must be verified |
| --- | --- | --- |
| **Files on a local filesystem** such as ext4/XFS/APFS/NTFS with a local storage device | The `FileChannel.force` Javadoc states a force contract with the local device for supported updates. | Whether the OS, filesystem, driver, controller, and flush/cache mechanisms actually honor sync commands on the device. |
| **NFS/SMB/network drives** | Java **does not guarantee equivalence to a local device**. | Whether the server truly commits durable writes or only buffers in cache; network reconnect, mount options, server-side sync behavior. |
| **Virtual disks/cloud volumes/container mounts** | The write path may traverse hypervisors, drivers, overlay layers, networks, or other devices. | What counts as local per the implementation; infrastructure-layer durability contracts and their specific limitations. |
| **In-memory filesystems** such as RAM-backed tmpfs | API synchronization does not turn volatile data into data that survives power loss. | Is the goal surviving crashes or only process restarts? Design durable storage appropriately. |
| **Devices with write-back cache** | Data may pass through controller/SSD caches. | Power-loss protection, firmware, and the flush mechanisms the physical device genuinely executes. |

The table describes how to **assess risk levels**, without claiming every setup maps neatly into one simple physical category. For example, a cloud volume may appear as a "local" block device to the JVM while actual backing storage is served over the network; read the storage service's exact SLA/contract.

With drives having caches unprotected against power loss, `force` cannot conjure a UPS or fix dishonest firmware. Conversely, on devices and filesystems that honor flush commands, `force` is Java's standard way of expressing a data synchronization request. Saying "data can definitely never be lost" is a stronger claim than Java's contract and hardware reality allow.

### Application Crash, OS Crash, and Power Loss Differ

- **Java process exits abruptly:** the OS keeps running, and OS caches may continue flushing to disk. This is **not** a sufficient test for `force`.
- **Kernel/system crash:** OS caches may be lost before flushing; `force` and filesystem recovery become critical.
- **Power loss or device loss:** additionally depends on controller caches, storage firmware, power infrastructure, and backing storage hardware.

Therefore, testing with `System.exit` or killing the process and seeing data intact **does not prove** data will survive when the machine loses power at the critical moment.

## 8. Limitations That Must Not Be Inferred from force

### Does Not Cover Multiple Objects in One Transaction

Calling `force(true)` on file A does not mean file B was flushed. Two files updated sequentially A → B can recover in a state where only one side changed if the system crashes mid-way. Updating multiple files as a single logical unit requires a transaction protocol such as a WAL, manifest + version, commit marker, or a database solution.

### Does Not Automatically Ensure Logical Ordering Across Multiple Writers

If multiple threads or processes write concurrently, you need locks/ownership/disjoint offsets or a record structure to prevent overlaps. `FileChannel.force` does not lock the file, does not stop other tasks from modifying the file during `force`, and does not commit an application-level transaction order. Clearly define "who is the writer", "when is a record considered committed", and "how incomplete records are detected on restart".

### Does Not Guarantee Consistent Reads While a Record Is Being Modified

`Files.readString` after `force` may observe valid data in a normal run, yet a reader running while a writer updates multiple offsets may read a mix of old and new data. Use snapshots, temp file + rename, read/write locks, or versioned records with checksums/sequences if logic requires a consistent snapshot.

### Does Not Prove Full Durability via a Single Test Output

No standard output like `"durable=true"` is returned by `force`. Normal completion or an exception only tells the outcome of the call under current conditions. A realistic test suite can verify byte readback, I/O errors, sync timings, and recovery after fault injection, yet a single test run cannot turn into a guarantee for every disk.

## 9. Workflow for Saving a Record More Durably

A simple log record format might look like:

```text
[magic/version][length][payload][checksum][commit marker/sequence]
```

This format is only an outline: layout, checksum, and commit ordering must be designed to distinguish a complete record from a torn record after a crash. A system might:

1. Allocate the record offset and write the full header/payload/checksum; check every write, short write, and error.
2. `force` the required bytes per protocol, then write the commit marker or update the manifest if the design requires it.
3. Perform a final `force` for the commit-marker data and related metadata.
4. ACK the record only after `force` completes and the protocol is consistent; if `force` fails, mark the state as indeterminate/unconfirmed.
5. On restart, scan valid records by length, checksum, version, or marker; stop at any incomplete record and apply a repair policy.

Actual synchronization ordering depends on the protocol; for instance, writing the marker and payload under a single `force` does not guarantee an application can rule out partial/torn writes on mid-way power loss. Use an existing database/WAL solution when durability and recovery requirements become complex.

## 10. Common Mistakes and How to Handle Them

| Mistake | Why it is wrong | How to handle it |
| --- | --- | --- |
| `write` returns a positive byte count, so reporting "saved durably". | Bytes may still sit only in the OS cache. | Write completely, call `force` at the proper commit point, ACK only upon completion. |
| Treating one `channel.write(buffer)` as sufficient. | FileChannel can short-write; bytes remain in buffer. | Check `buffer.hasRemaining()` and loop; check for `0`/exceptions. |
| Treating `channel.force(false)` as equivalent to `force(true)`. | False only requests forcing content; metadata has a different scope. | Choose based on actual updates; distinguish file metadata from directory entries. |
| Calling `Files.writeString` then opening another channel just to force and assuming all writes are guaranteed. | The `FileChannel.force` contract limits which changes are committed. | Use a consistently managed writer/channel or the chosen API's explicit sync mechanism. |
| Modifying data via `mapped.put(...)` then calling only `channel.force`. | Channel force does not necessarily cover mapped buffer updates. | Call `mapped.force()` per the mapping contract. |
| Using `close`/`flush` instead of `force`. | Different durability contracts. | Use `FileChannel.force` or `SYNC`/`DSYNC` when file synchronization is required. |
| Calling force on a temp file then renaming and assuming the filename itself is power-loss safe. | Directory metadata/rename has a separate contract. | Check atomic rename, directory fsync / OS-specific mechanisms when filename durability is needed. |
| Using `force` as a lock or transaction. | Does not protect overlapping byte regions or read-modify-write. | Use separate locks/update protocols; force after reaching a consistent state. |
| Assuming remote/network filesystems give local-like guarantees. | Javadoc promises no equivalent semantics. | Verify server, provider, mount, and storage service behavior. |
| Ignoring `IOException` during `force`. | Cannot claim a successful commit after a sync error. | Return error, log with context, recover or mark state indeterminate. |

### Proper Error Handling at the Force Point

```java
// Illustrative snippet: channel is open and all data has been written.
try {
    channel.force(true);
    // Only here can commit be reported within force's guarantee scope.
} catch (IOException e) {
    // Do not report success; transition to I/O failure/recovery handling.
    throw e;
}
```

If an exception occurs mid-force, **you cannot infer that zero bytes reached storage**, nor can you claim all of them did. Apply a recovery policy based on logs/checksums/transaction IDs to avoid duplicating or losing transactions upon retry.

## 11. Pre-Production Checklist

1. **What must be durable?** Payload bytes, file size, metadata, filename after rename, one file or multiple files?
2. **Where is the commit point?** Before or after ACK? What batch size? What data-loss window is acceptable?
3. **Which API does the writer use?** `FileChannel`, `FileOutputStream`/`RandomAccessFile.getChannel`, mapped memory, or another handle? Choose the matching force scope.
4. **Are writes complete?** Check short writes, `ByteBuffer`, offsets, overlaps, and write order; `force` does not fix races.
5. **What is the storage?** Local file, NFS/SMB, tmpfs, cloud volume, container overlay? Read platform guarantees instead of guessing from OS name.
6. **Are atomicity and recovery needed?** If so, design WAL/manifest/checksums, atomic rename, and directory sync if supported.
7. **How are force errors handled?** No false ACKs; log context, mark transactions indeterminate, and recover safely.
8. **How is performance?** Measure p95/p99 latency, throughput, and sync frequency; evaluate `SYNC`, `DSYNC`, or group commit.
9. **Which failure levels are tested?** Unit tests verifying bytes, integration tests on the target file store, fault injection/crash recovery for business data. Do not treat readback or killing the JVM as proof of power-loss durability.
10. **Who owns resources?** Use `try-with-resources`, do not close the channel prematurely while another task is forcing/writing; control mapping lifetimes.

## 12. Knowledge Self-Check

**Question 1.** After `channel.write(buffer)`, calling `Files.readAllBytes(path)` sees the new bytes. Does that prove the data is resilient to power loss?

**No.** Reading back may hit the OS cache. You need a force/sync mechanism with an appropriate contract and verification of the storage layer.

**Question 2.** Does `force(false)` request forcing file metadata?

**No.** Only content must be forced per contract. `force(true)` requests both content and metadata, though the actual effect of the parameter depends on the OS.

**Question 3.** Can a file stored on NFS receive the same durability guarantee as a local device from the `FileChannel.force` Javadoc?

**No.** The Javadoc explicitly states that if it is not a local storage device, equivalent guarantees are not provided; you must examine server/OS/provider semantics.

**Question 4.** If content is modified via `MappedByteBuffer.put`, which force method should be used?

**`MappedByteBuffer.force()`.** `FileChannel.force` may or may not synchronize changes made through a mapping.

**Question 5.** Does `force(true)` guarantee that after a crash, `Files.move(temp, final, ATOMIC_MOVE)` persists under the name `final`?

**That cannot be inferred from `force(true)` on the file alone.** Atomic move and directory-entry durability are separate concerns; filesystem/OS-specific workflows and verification are required.

**Question 6.** To reduce `force` calls, can 100 records be batched and forced once?

**Yes, if business requirements accept a batch commit boundary.** All records must be written completely in a consistent format, and you must ACK only records covered after the `force` succeeds. If the application crashes before `force`, that batch is not committed under that policy.

**Question 7.** Does `force` resolve two writers updating the same offset?

**No.** You must coordinate writers/locks/data protocols; `force` only addresses requesting synchronization for changes within its scope.

## Official Documentation

- Oracle Java SE 21 — [`FileChannel`: `force(boolean)`, write, map, and lock methods](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html).
- Oracle Java SE 21 — [`MappedByteBuffer`: `force()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/MappedByteBuffer.html).
- Oracle Java SE 21 — [`StandardOpenOption`: `SYNC` and `DSYNC`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html).
- Oracle Java SE 21 — [`Files`: `newByteChannel` / `move` and `ATOMIC_MOVE`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html).

**Practical conclusion:** `FileChannel.force` is a request to synchronize file changes down to the storage device within Java's contract scope; `metaData` controls the content/metadata scope. Achieving a truly durable storage system requires pairing `force` at the proper commit point with complete writes, recoverable formats, writer coordination, and verification of the target OS/filesystem/infrastructure.
