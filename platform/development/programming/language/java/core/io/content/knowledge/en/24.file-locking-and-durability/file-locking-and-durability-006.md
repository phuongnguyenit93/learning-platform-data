# Distinguishing `flush()`, `FileDescriptor.sync()`, and `FileChannel.force()` in Java

## 1. The Problem: Does "Written" Mean Durable?

An application writes a transaction record, a configuration file, or a recovery log. The `write()` call returns, and the program can read the data back, yet the machine loses power immediately afterward. Are those bytes guaranteed to still be intact upon reboot?

In Java I/O, you must distinguish between **data leaving application-managed buffers** and **requesting synchronization of data down to the storage device**. Three commonly confused APIs are:

- `flush()` on `OutputStream`/`Writer`: pushes data currently buffered by the stream/writer classes down to the underlying sink, according to the implementation's contract; **does not itself guarantee persistence to physical disk**.
- `FileDescriptor.sync()`: requests the system to synchronize buffers associated with the **descriptor** down to the device; can only affect data that has already reached below the descriptor.
- `FileChannel.force(boolean metaData)`: requests synchronization of updates for the **file associated with the channel** down to the device. The `metaData` parameter determines whether metadata synchronization is requested alongside content.

The goal of this lesson is to understand the exact **data path**, operation ordering, guarantees, and limitations of each API, and then apply them to writes requiring durability.

## 2. Buffer Layers from Application to Storage

A simple byte write path can traverse multiple layers:

```text
Application: write("ABC")
        |
        v
BufferedWriter / OutputStreamWriter / BufferedOutputStream
(character buffer, encoder state, or byte buffer inside JVM)
        |                 ^
        | flush()         | unflushed data may still sit here
        v
FileOutputStream / file descriptor / FileChannel
        |
        v
Operating system, filesystem, and page cache
        |
        | sync() or force(...)
        v
Actual storage device / storage service
        |
        v
Survival across system failures
(depends on Java contract, OS, driver, device, and environment)
```

This is a conceptual diagram, not a claim that every program includes all layers. For example, writing directly via `FileChannel` needs no `BufferedOutputStream`; writing via `BufferedWriter` can pass through both a character buffer and an encoding step.

Two distinct questions:

1. **Visibility:** can another reader or a new file handle observe bytes already handed to the filesystem?
2. **Durability:** has the system completed the synchronization call per contract, to reduce the risk of losing updates on failure/crash?

Seeing data via `Files.readString(path)` immediately after `write()` **does not prove** the data has been synchronized to the device. The data could be served from the operating system's page cache.

## 3. Quick Comparison Table

| API | Direct Target Layer | When to Use | What Not to Infer |
| --- | --- | --- | --- |
| `BufferedOutputStream.flush()` | Stream's byte buffer and invokes underlying `flush()` | When pushing JVM-buffered data to the underlying sink | Not an `fsync` guarantee or power-loss immunity |
| `BufferedWriter.flush()` / `OutputStreamWriter.flush()` | Character/encoder buffer and underlying stream per contract | When finishing transfer of buffered text down to the byte stream | Does not confirm file durability on storage |
| Default `OutputStream.flush()` | Default implementation does nothing | Extension point for subclasses | Does not inherently have a buffer to drain |
| `FileOutputStream.flush()` | Inherits behavior from `OutputStream` | Not a device-sync API | Calling it alone is not equivalent to `FileDescriptor.sync()` |
| `FileDescriptor.sync()` | System buffers associated with the descriptor | When synchronizing writes via descriptor to the device | Does not flush an unflushed `BufferedOutputStream` for you |
| `FileChannel.force(false)` | File data updated by the channel within guarantee scope | When forcing content is needed | Does not require full metadata sync per contract |
| `FileChannel.force(true)` | Content and metadata within guarantee scope | When metadata is also needed | Not a multi-file transaction commit or directory-entry sync |
| `StandardOpenOption.DSYNC` / `SYNC` | Synchronization policy when opening a file | When content / content-and-metadata updates should be written synchronously | Does not flush separate app-level byte buffers not yet written to the channel |

**Key point:** `flush()` addresses "have bytes passed through the wrapper layer?", whereas `sync()/force()` addresses "have updates been requested to be pushed to storage?". In multi-layer pipelines, you must typically **flush first, then sync/force**.

## 4. `flush()`: Pushing Application Buffers to Lower Layers

### 4.1. General Contract of `OutputStream.flush()`

`OutputStream` implements `Flushable`. Per Java SE 17, `flush()` signals that any bytes currently held in internal buffers by the stream implementation should be written immediately to the destination managed by that stream. When the destination is an OS abstraction such as a file, **flush only guarantees that bytes have been handed to the operating system per contract, not that they have been written to the physical device**.

The default implementation of `OutputStream.flush()` does nothing. Thus, claiming "every `flush()` pushes the page cache to disk" is false.

### 4.2. `BufferedOutputStream` Has an Actual Byte Buffer

`BufferedOutputStream` maintains an internal byte array. When `write(int)` is called, bytes may reside solely in that array. `flush()` writes those buffered bytes to the underlying `OutputStream` and then calls `flush()` on it.

```java
FileOutputStream raw = new FileOutputStream(file);
BufferedOutputStream buffered = new BufferedOutputStream(raw);

buffered.write('A');
// 'A' may still sit in buffered's internal buffer; raw has not received the byte yet.

buffered.flush();
// Buffer has pushed 'A' down to raw/FileOutputStream,
// though there is still no fsync-equivalent guarantee.

// Manage close via try-with-resources in a real program.
```

*The snippet above is illustrative only*: `file` must be a valid `File`, with required imports and `IOException` handling. `flush()` can throw `IOException` if the underlying layer cannot accept the data.

When writing a very large array, some streams may pass bytes directly to the underlying stream without buffering everything; this **does not change the meaning** of `flush()`.

### 4.3. Writer Flushing Also Involves Character Encoding

`BufferedWriter` buffers characters; `OutputStreamWriter` converts characters into bytes per a charset. When data flows through multiple layers:

```text
BufferedWriter
     |
     v
OutputStreamWriter (UTF-8)
     |
     v
BufferedOutputStream
     |
     v
FileOutputStream
```

Calling `writer.flush()` at the outermost layer pushes buffered data through the wrapper chain down to lower layers. When completing a standalone text file, `close()` after finishing writes handles the writer lifecycle; afterward, storage durability requirements must still be addressed separately if business logic demands them.

Do not call `flush()` on an inner stream rather than the outermost layer holding the data and assume all bytes have reached the descriptor. For instance, `fileOutputStream.getFD().sync()` does **not** reach into and drain the array inside a wrapping `BufferedOutputStream`.

### 4.4. `flush()` Is Not `close()`

- `flush()` pushes buffered data while keeping **the stream open**.
- `close()` closes the resource; many buffered/writer classes flush data upon closing.
- `close()` is not a portable API promising every file has been synced to the device.
- For streams remaining in use, `flush()` is appropriate when a protocol needs the receiver to see bytes promptly, but it does not replace sync.
- For resources that must finish, use `try-with-resources` for disciplined closing and handle `IOException` that may arise during `write`, `flush`, or `close`.

## 5. `FileDescriptor.sync()`: Synchronizing Descriptor Buffers

`java.io.FileDescriptor` represents a low-level connection to an OS-managed file, socket, or resource. `FileOutputStream.getFD()` returns the descriptor for that file stream.

Method:

```java
public void sync() throws SyncFailedException
```

Per the Java SE 17 contract, `sync()` requests that **all system buffers associated with the FileDescriptor** be synchronized with the underlying device. When successful for a file on physical storage, the intent is to push system-managed in-memory modifications to the underlying media, within the guarantees the environment can provide.

**Very important limitation:** `sync()` affects only buffers **below the FileDescriptor**. Bytes still sitting in `BufferedOutputStream`, `BufferedWriter`, or application-managed buffers must be **flushed** or written down to the descriptor first.

Therefore, with `BufferedOutputStream`:

```java
buffered.write(recordBytes);
buffered.flush();       // 1. JVM buffer -> FileOutputStream/OS
file.getFD().sync();    // 2. Ask OS to synchronize descriptor
```

This snippet illustrates ordering logic and requires declaring objects, imports, and handling checked exceptions. It also assumes `file` is the `FileOutputStream` directly underneath `buffered`.

### What Does `SyncFailedException` Mean?

`FileDescriptor.sync()` can throw `SyncFailedException` when buffers cannot be flushed or the system cannot guarantee that buffers are synchronized with the device. Never catch it and silently treat a critical transaction as successful; the application must propagate the error to the appropriate layer (controlled retry, error reporting, no commit confirmation).

`FileDescriptor.valid()` only checks whether the descriptor represents an open/valid connection; it **does not prove** a sync request succeeded.

## 6. Runnable Java 17+ Example: Flush First, Sync After

The following experimental example demonstrates **byte visibility through another file handle** while bytes remain in a Java buffer. It does **not** test power loss or guarantee durability; file reads only confirm that bytes have moved down to lower layers.

Create **`FlushAndSyncDemo.java`**:

```java
import java.io.BufferedOutputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FlushAndSyncDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("flush-sync-", ".dat");

        try {
            try (FileOutputStream raw = new FileOutputStream(path.toFile());
                 BufferedOutputStream buffered =
                         new BufferedOutputStream(raw, 8192)) {

                buffered.write('A');
                System.out.println("before flush="
                        + Files.size(path));

                buffered.flush();
                System.out.println("after flush="
                        + Files.readString(path, StandardCharsets.US_ASCII));

                // 'B' is currently only inside BufferedOutputStream.
                buffered.write('B');

                // sync() does not drain bytes still held in buffered.
                raw.getFD().sync();
                System.out.println("sync before second flush="
                        + Files.readString(path, StandardCharsets.US_ASCII));

                buffered.flush();
                raw.getFD().sync();

                System.out.println("flush then sync="
                        + Files.readString(path, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Compile/run in the directory containing the file:

```bash
javac FlushAndSyncDemo.java
java FlushAndSyncDemo
```

Stdout when both I/O operations and `sync()` succeed:

```text
before flush=0
after flush=A
sync before second flush=A
flush then sync=AB
```

Order explanation:

1. `Files.createTempFile` creates an empty file. `FileOutputStream` opens the file for writing; `BufferedOutputStream`'s 8192-byte buffer retains the ASCII byte `A`, so the file stays length 0 before flushing.
2. `buffered.flush()` pushes `A` down to `FileOutputStream`. Another read can now see `A`, though that **does not prove** the byte survives device power loss.
3. `buffered.write('B')` keeps `B` in JVM memory. `raw.getFD().sync()` syncs whatever has reached the descriptor, **without** moving `B` out of the application buffer; hence the read still shows `A`.
4. `buffered.flush()` sends `B` down to the descriptor; `raw.getFD().sync()` then requests synchronization. Now the file contains `AB` via normal reads.
5. `try-with-resources` closes the streams and `finally` deletes the temp file.

If `sync()` is rejected by the system, the program throws an error and stdout may stop before the final line. Do not infer from this output that you have simulated power loss; Java has no standard API to simulate power loss and prove durability in a single ordinary test.

## 7. `FileChannel.force(boolean metaData)`: Channel-Level Synchronization

`java.nio.channels.FileChannel` provides:

```java
public abstract void force(boolean metaData) throws IOException
```

Its purpose is to request that updates to the **file associated with the FileChannel** be written to the device containing the file. Per Java SE 17:

- If the file resides on a **local storage device**, upon successful completion of `force`, Java guarantees that relevant changes made since the channel was created or since the last `force` call have been written to that device, within **the scope of API-guaranteed operations**.
- If the file does not reside on a local device (such as certain network filesystems), Java does **not** make that same guarantee.
- `force(false)` requests synchronization of file **contents**; it is **not required** to fully synchronize metadata.
- `force(true)` requests synchronization of both file **contents and metadata**. Choosing `true` may incur additional I/O; the exact effect of the flag is OS-dependent.
- `force` may perform I/O even when the channel was opened read-only because the OS may update metadata such as last-access time.
- `force` can throw `ClosedChannelException` if the channel is closed or `IOException` on I/O errors.

### 7.1. `metaData = false` vs. `metaData = true`

Metadata can include file size, timestamps, and attributes managed by the filesystem. Do not rely on how a specific OS treats certain attributes as "required" or "optional" when calling `force(false)`; the Java contract only specifies the category of updates requested to be forced.

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.WRITE)) {

    // Assume write(...) has passed all required content to the channel.
    channel.force(false); // Request content force
    channel.force(true);  // Request content + metadata force
}
```

This is a snippet (requiring `path` and appropriate `write` calls). Calling both back-to-back is **usually unnecessary**: pick the appropriate level for your business-logic sync point. If the operation already calls `force(true)` at the commit point, there is no need to also call `force(false)` just to be "doubly safe".

### 7.2. Which Updates Are Covered by `FileChannel.force()`

Java SE 17 guarantees `FileChannel.force()` for changes made through **methods defined by `FileChannel`**. If a channel is obtained via `getChannel()` from `FileOutputStream` or `RandomAccessFile`, do not assume guarantees beyond the API documentation; for critical code, use a single explicit write/force pipeline and verify the implementation contract.

Specifically, modifications to a **`MappedByteBuffer`** obtained from `FileChannel.map` follow separate rules: `FileChannel.force()` **may or may not** force updates made via a mapped buffer. Use **`MappedByteBuffer.force()`** to request synchronization of changes in a mapped region per the mapped buffer's API contract.

`force()` does not read or drain an application-managed buffer. If your application places a `BufferedOutputStream` above it, always push bytes down to the filesystem before calling `force` on the associated channel.

## 8. Runnable Java 17+ Example: Forcing Content and Metadata

Create **`FileChannelForceDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelForceDemo {
    private static void writeAll(FileChannel channel, String text)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(
                text.getBytes(StandardCharsets.US_ASCII));

        while (buffer.hasRemaining()) {
            int written = channel.write(buffer);
            if (written == 0) {
                throw new IOException("FileChannel made no progress");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("file-force-", ".txt");

        try {
            try (FileChannel channel = FileChannel.open(
                    path,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                writeAll(channel, "DATA");
                channel.force(false); // force content

                writeAll(channel, "!");
                channel.force(true);  // force content + metadata

                System.out.println("size=" + channel.size());
            }

            System.out.println("text="
                    + Files.readString(path, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac FileChannelForceDemo.java
java FileChannelForceDemo
```

Stdout when both `force` calls succeed:

```text
size=5
text=DATA!
```

Key points:

1. `FileChannel.open` opens the existing file for writing, with `TRUNCATE_EXISTING` resetting length to 0. Depending on the environment, open/write/force can throw `IOException`.
2. `writeAll` loops until all bytes in `ByteBuffer` are written; it does not assume a single `channel.write` writes everything.
3. The first `force(false)` requests synchronization of the `DATA` content.
4. After writing `!`, `force(true)` requests synchronization of the new content and metadata per contract.
5. `size()` and the post-close read confirm the file's logical content is `DATA!`. **They do not test power-loss survival.**

Never treat `System.out.println("text=DATA!")` as proof that the device successfully executed every power-loss protection mechanism. The evidence here is **`force` returning without throwing an error**, within the exact guarantee scope of the API and storage environment.

## 9. Three APIs at Three Different Levels, Not Direct Substitutes

Consider the same payload `"ORDER=42"` handled in three ways:

**Write then flush only:**

```java
buffered.write(bytes);
buffered.flush();
```

Meaning: pushes bytes from the application buffer down to the underlying stream so the receiver/OS observes them sooner. Suitable when handing data to the next layer is required, **insufficient** to promise data survives a system crash.

**Write, flush, then sync descriptor:**

```java
buffered.write(bytes);
buffered.flush();
rawFileOutputStream.getFD().sync();
```

Meaning: once bytes have reached the file descriptor, requests synchronization of system buffers associated with the descriptor.

**Write directly via FileChannel then force:**

```java
ByteBuffer buffer = ByteBuffer.wrap(bytes);
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
channel.force(true);
```

Meaning: with a file channel, requests synchronization of file updates including metadata per Java's contract. This snippet assumes the file channel is opened with `WRITE`, `bytes` is ready, and no uncoordinated parallel write path exists.

These three snippets are **not standalone programs**; they illustrate application patterns chosen based on the underlying API. Never randomly pair the descriptor of file A with the channel of file B and assume all data has been synchronized.

## 10. When to Choose `StandardOpenOption.SYNC` or `DSYNC`?

Besides calling `force()` after a batch of operations, Java NIO offers file-open options requesting synchronous writes:

- `StandardOpenOption.DSYNC`: requires every update to file **content** to be written synchronously to the device.
- `StandardOpenOption.SYNC`: requires every update to file **content or metadata** to be written synchronously to the device.

Example:

```java
try (FileChannel ch = FileChannel.open(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.DSYNC)) {

    // Calls to ch.write(...) operate under DSYNC mode.
}
```

This is a snippet; it requires `Path path`, imports, and `IOException` handling. Selecting `DSYNC` makes no difference on a `BufferedOutputStream` if bytes have not yet been passed down to `FileChannel`: an option on the file channel does not force a separate app-layer buffer to flush.

**Performance difference:** calling `force` per batch usually performs fewer sync operations than requiring sync on **every single update**. In exchange, if a crash happens before a `force` checkpoint, changes since the prior checkpoint may not be durable. `SYNC/DSYNC` modes can increase latency per individual write. Base the decision on maximum acceptable data loss, batch size, latency, and filesystem characteristics.

If running on a special provider or filesystem that does not support the requested option, `FileChannel.open` may throw an exception. Do not assume identical durability and performance across network volumes, tmpfs/in-memory mounts, virtual devices, or containers.

## 11. The `MappedByteBuffer` Case: Understand Map `force()` Properly

A mapped file region obtained from `FileChannel.map` can allow direct reads/writes via `MappedByteBuffer`:

```java
try (FileChannel ch = FileChannel.open(
        path,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    MappedByteBuffer map = ch.map(
            FileChannel.MapMode.READ_WRITE, 0, 4096);

    map.put(0, (byte) 42);
    map.force();
}
```

**Illustrative snippet, not standalone**; it assumes the file/OS supports the mapped region (mapping may extend the file per API semantics as needed), and requires imports and exception handling. Importantly:

- `FileChannel.force()` is described by Java 17 as **may or may not** cover updates made through a mapped buffer.
- `MappedByteBuffer.force()` is specifically designed to request that changes to the mapped buffer be written to the device holding the mapped file (with similar device/OS/provider caveats).
- In real programs, check how map lifecycles, mapping limits, thread synchronization, and errors when the device/region becomes inaccessible are handled.

Do not rely on a `channel.force(true)` call as a blanket guarantee for all modifications made via `MappedByteBuffer`.

## 12. Durability Does Not Mean Transactions or Atomicity

`sync()` or `force()` addresses **data synchronization**, and does not replace:

1. **Atomicity of multiple writes:** a large write or multiple records can be partially written if the app/system fails midway. `force()` does not make a write sequence "all-or-nothing".
2. **Format consistency:** headers and payloads can become mismatched after a crash unless write ordering, versions, checksums, or a recovery log are designed.
3. **Atomic file replacement:** to publish a new config, a common strategy writes a temp file in the same directory, forces content, and renames/moves appropriately. `Files.move` with `ATOMIC_MOVE` only guarantees the rename/move step is atomic **if the filesystem supports it**, and does not automatically persist the directory entry durably.
4. **Directory metadata durability:** forcing a file is not a portable promise that a new filename, creation, or rename in the parent directory has also been synchronized. Java SE offers no simple cross-platform API guaranteeing `fsync(parent-directory)` across all providers.
5. **Multi-file transactions:** syncing individual files does not provide an atomic commit across a set of files. A transaction protocol or storage engine designed for that requirement is needed.

A crash-safe protocol may require record headers, checksums, a write-ahead log, commit markers, and recovery logic. `flush/sync/force` is only **one part of that design**.

### Example Safer Config-Saving Workflow

For a configuration file replacing an older version:

```text
1. Create a temporary file in the same directory as the target file.
2. Write the entire new content and check for errors.
3. FileChannel.force(true) on the temp file (after all data has reached the channel).
4. Close the temp channel/file.
5. Files.move(temp, target, ATOMIC_MOVE, ...), if supported by the provider.
6. Address rename/directory durability according to OS,
   filesystem, and application requirements.
```

This is a **design flow**, not a guarantee of portable crash-safety from the first five steps alone. If `ATOMIC_MOVE` is unsupported, `AtomicMoveNotSupportedException` can occur. Target replacement behavior and extra options must be verified against the contract and filesystem; do not assume automatic rollback or zero data loss at every crash point.

## 13. Write Paths and Responsibilities Across Multiple Layers

Three common architectural patterns:

### A. Text Log Buffered in the JVM

```text
BufferedWriter --> OutputStreamWriter --> BufferedOutputStream
                  --> FileOutputStream --> file descriptor --> filesystem
```

If business requirements mandate syncing each log group, flush **the outermost writer layer**, then call `FileDescriptor.sync()` on the exact underlying `FileOutputStream`. Calling `sync` before `flush` misses bytes still in the writer or buffered output stream.

### B. NIO File Batch Writer

```text
domain records --> encode into ByteBuffer --> FileChannel.write(...)
                                       --> FileChannel.force(true/false)
```

There is no `BufferedOutputStream`, so `flush()` does not exist in that API style. `ByteBuffer.flip()` / `clear()` are **buffer-state management operations**, not file sync requests. Ensure all bytes have been completely `write`-n before calling `force`.

### C. Mixing FileOutputStream and Its Associated Channel

`FileOutputStream.getChannel()` returns the channel attached to the stream. Writes via the stream and channel share the same file position/connection and must be coordinated. If wrapping the stream in a `BufferedOutputStream`, **flush the buffered layer** before calling any sync request on the descriptor/channel.

Avoid writing bytes concurrently across multiple threads using both API styles without ordering control; `flush` and `sync` are meaningful only when the application clearly defines which set of bytes belongs to the checkpoint being committed.

## 14. Performance, Checkpoint Batching, and Environment Limits

`force` incurs I/O cost; call frequency can significantly impact latency and throughput. When designing a batch writer, options include:

- **High durability, every critical record:** write the full record and sync/force before reporting "committed" to the caller.
- **Group commit:** gather a batch of valid records, then `force` once; acknowledge those corresponding records only after the checkpoint completes.
- **Best-effort output/log:** flush in batches so data becomes visible promptly; if losing the tail of logs on a crash is acceptable, syncing on every batch may be unnecessary.

The choice depends not just on speed, but on data criticality: payment records, checkpoint files, regenerable caches, or diagnostic logs have different priorities.

Explicitly stated limitations:

- On **non-local** filesystems, `FileChannel.force`'s contract does not make the same promise as local devices; storage servers, caches, replication, and networks have their own policies.
- On devices/drivers with volatile write caches or unreliable sync reporting, Java APIs do not replace evaluating the entire storage stack's durability.
- Do not verify durability by running `Files.readAllBytes` right after writing and concluding "safe against power loss"; the OS page cache can serve the new bytes.
- `IOException` or `SyncFailedException` means the sync request could not be confirmed; never report "committed" when data guarantees are required.
- `force(true)` does not fix missing atomicity across multi-file updates or multi-step workflows.

## 15. Common Mistakes to Avoid

1. **"`flush` is equivalent to `fsync`."** False. Stream `flush` generally pushes application buffers to the underlying sink; it does not promise physical storage has finished writing.
2. **"Calling `FileDescriptor.sync` before flush still persists all new records."** False for bytes still sitting in `BufferedOutputStream` or writers. Flush the proper outermost layer first.
3. **"`FileOutputStream.flush` is a special method for disk sync."** False; `FileOutputStream` inherits the default no-op `OutputStream.flush`, not an alternative to `getFD().sync()`.
4. **"Using `force(false)` always makes metadata durable."** The `false` flag carries no guarantee of requesting full metadata synchronization.
5. **"`force(true)` is a system-wide transaction commit."** No. It covers updates for a single file within contract scope, not atomic multi-file/directory commits.
6. **"`FileChannel.force` always covers mapped buffers."** Not guaranteed. Modifications via `MappedByteBuffer` should use the mapped buffer's `force()` API.
7. **"Seeing the content from another JVM means the file is synced."** False. Visibility can come from the page cache.
8. **"`close` means force."** Do not infer this; issue an explicit sync call when durability is required.
9. **"One `FileChannel.write(ByteBuffer)` call always writes the entire buffer."** Not guaranteed. Check `hasRemaining()` and bytes actually written, handling errors before calling `force`.
10. **"Sprinkling `force(true)` everywhere just makes things safer."** It can degrade throughput and increase latency while still not solving atomicity or recovery protocols.
11. **"`SYNC` and `DSYNC` automatically flush buffered writers."** False. These are file-open options; bytes in application buffers must still be pushed down to the channel first.
12. **"If `sync` succeeds, data consistency checks are unnecessary."** Insufficient. Crashes mid-way across multiple records still require a recoverable format.

## 16. Practice Exercises

### Exercise A — Predicting Visible Data

An initially empty file is wrapped by a `BufferedOutputStream` with capacity greater than 100 bytes. After:

```java
buffered.write('X');
raw.getFD().sync();
```

At this moment, you **cannot assert** that `'X'` has reached the descriptor. Why? Add the missing operation at the right position and explain the difference between visibility and durability.

### Exercise B — Writing a Batch of Records

A program writes 100 records to a `FileChannel`, then calls `force(true)` and only then confirms to the user. If a failure occurs after record 90, before `force`, which records can be considered committed under this policy? What metadata design helps distinguish complete records from partial ones?

### Exercise C — The Metadata Flag

If a system only cares about content bytes, what does `force(false)` suffice for? If metadata must also be requested per contract, which flag should be chosen? Does `force(true)` guarantee the directory entry for a separate file-rename operation?

### Exercise D — Logs in Mapped Memory

A file is modified using `MappedByteBuffer.put`. Can you call only `FileChannel.force(true)` to guarantee that changes in the mapping were forced? Which API is directly responsible for synchronizing updates from a mapped buffer?

### Exercise E — Opening a File with `DSYNC`

If you write one million bytes through `BufferedOutputStream` on a file opened with `DSYNC` without flushing the buffer, can you conclude every byte has reached the device? Analyze the boundary between application buffers and file open options.

## 17. Self-Check Knowledge Questions

1. Does default `OutputStream.flush()` perform any operation? When must concrete implementations like `BufferedOutputStream` override it?
2. Through which method is `FileDescriptor.sync()` accessed from `FileOutputStream`, and what specialized exception can it throw?
3. Explain why `buffered.flush()` is needed **before** `raw.getFD().sync()`.
4. How do `FileChannel.force(false)` and `FileChannel.force(true)` differ? Why does passing `false` not mean all metadata is forced?
5. What guarantee does `FileChannel.force` provide for files on a local device? What about remote filesystems?
6. Why does `MappedByteBuffer.force()` exist when modifying memory-mapped file regions?
7. Does `Files.readString(path)` returning the expected text right after writing prove the data survives power loss?
8. Why does syncing a temp file followed by an atomic rename still require thinking about parent-directory durability?
9. When does group commit help reduce sync I/O, and how does it change when "committed" is acknowledged?
10. Contrast `SYNC/DSYNC` at file open time with checkpointed `force` calls after multiple writes.

## 18. Official References

- [Java SE 17 — `OutputStream.flush()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html#flush()).
- [Java SE 17 — `BufferedOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html).
- [Java SE 17 — `FileDescriptor.sync()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileDescriptor.html#sync()).
- [Java SE 17 — `FileChannel.force(boolean)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#force(boolean)).
- [Java SE 17 — `StandardOpenOption.SYNC` and `DSYNC`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html).
- [Java SE 17 — `MappedByteBuffer.force()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html#force()).

## 19. Key Takeaways

`flush()` answers the question **"have bytes buffered at the application layer been handed down to the underlying sink?"**. `FileDescriptor.sync()` and `FileChannel.force()` request **synchronization of updates that have reached the file/descriptor layer with the storage device** under specific contracts and limitations.

When application buffering is present, the fundamental order is **write completely → flush the right outer layer → sync/force the right resource → acknowledge only after sync succeeds**. `force(false)` focuses on content while `force(true)` also requests metadata; for memory-mapped files, use `MappedByteBuffer.force()` for updates made through the mapping. For operations that must survive crashes, you must also account for atomicity, record framing, recovery, directory durability, and storage-stack limitations.