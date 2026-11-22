# `force()` for Changes in Mapped Memory Regions (Java NIO)

## 1. The Problem: Have Changes in a Memory-Mapped File Been Persisted Durably?

In Java NIO, `FileChannel.map(...)` maps part of a file into memory and returns a `MappedByteBuffer`. You can modify contents through `mapped.put(...)`, `mapped.putInt(...)`, or other `ByteBuffer` write methods. Crucially, **seeing new bytes in memory does not mean the storage subsystem has received a request to persist those bytes durably**.

For example, an application writes a binary record directly into a mapped region:

~~~java
// Illustration: channel opened for reading and writing, mapped region is long enough.
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, 4096);
mapped.putInt(100, 42);
mapped.force();
~~~

The `force()` method requests that modifications made to the mapped buffer's contents be written to the storage device. This is essential when establishing a **data durability checkpoint**, rather than waiting for the operating system to flush dirty pages on its own schedule.

Distinguish clearly between:

- **Modifications in the mapping:** the application has edited the contents visible through the buffer; memory pages may not yet be persisted durably.
- **`force()` returns successfully:** for files on a **local storage device**, the Java specification guarantees that changes within the forced range have been written to the device.
- **Transactional crash consistency:** a broader problem. `force()` does not by itself provide atomic transactions, isolation, rollback, checksums, journaling, or multi-step recovery.

This article focuses on `MappedByteBuffer.force()` and `force(int index, int length)`, compares them with `FileChannel.force(boolean)`, analyzes their limitations, and provides a standalone Java 17+ example.

## 2. Which Byte Region Does File Mapping Create?

To create a mapping, use:

~~~java
MappedByteBuffer mapped =
        channel.map(FileChannel.MapMode.READ_WRITE, 4L, 8L);
~~~

`4L` is the **byte offset within the file**, and `8L` is the number of mapped bytes. The returned buffer has `position=0`, `limit=8`, `capacity=8` (with an initially undefined mark).

~~~text
File offset:      0  1  2  3 |4  5  6  7  8  9 10 11|12 13
                              8-byte mapped region
Buffer index:                 0  1  2  3  4  5  6  7
                              ^                 ^
                         first index        last index
~~~

Conversion table:

| Buffer index | File offset when mapped from offset 4 |
|---:|---:|
| 0 | 4 |
| 1 | 5 |
| 4 | 8 |
| 7 | 11 |

Thus `mapped.putInt(0, value)` writes to **file bytes 4–7**; `mapped.putInt(4, value)` writes to **file bytes 8–11**. Indices passed to `putInt(index, ...)` or `force(index, length)` are **mapped buffer indices**, not absolute file offsets.

`MappedByteBuffer` inherits relative and absolute access from `ByteBuffer`. Calling `putInt(index, value)` **does not change position**, whereas relative `putInt(value)` uses the current position and advances it by four bytes.

### The Three `FileChannel.MapMode` Modes

| Mode | Writable via mapped buffer? | Effect on actual file | Effect of `force()` |
|---|---|---|---|
| `READ_ONLY` | No; `put(...)` throws `ReadOnlyBufferException` | No changes made through buffer | No effect |
| `READ_WRITE` | Yes | Changes propagate to file; timing determined by the system | **Requests durable writeback of mapping changes** |
| `PRIVATE` | Yes, via copy-on-write | Changes stay in a private copy, **not propagated to the underlying file** | No effect in saving private changes to the file |

`READ_WRITE` and `PRIVATE` require `FileChannel` opened for **reading and writing**; `READ_ONLY` requires read access. Calling `force()` on a `PRIVATE` mapping does not turn private edits into data written to the original file.

## 3. Contract of `MappedByteBuffer.force()`

Java 17 signature:

~~~java
public final MappedByteBuffer force()
~~~

Key characteristics:

1. Requests forcing modifications of the **mapped buffer's contents** to the device containing the file.
2. The range is **the entire `[0, capacity())`**, equivalent to `force(0, capacity())`. It **does not process only `[position, limit)`**.
3. If the file resides on **local storage**, Java guarantees that when the method returns normally, changes within the requested range made since the buffer was created or since the previous corresponding `force` call have been written to the device.
4. If the file resides on **non-local storage** (e.g., certain network filesystems), the specification provides no equivalent guarantee.
5. For `READ_ONLY` and `PRIVATE`, the method has no effect; provider-specific modes may behave differently.
6. It returns **the `MappedByteBuffer` itself**, not a flushed byte count or boolean.
7. An I/O error while writing contents may throw **`UncheckedIOException`**.

### Force does not change position, limit, or capacity

~~~java
// Illustrative example: mapped is READ_WRITE mapped for 128 bytes.
mapped.put(10, (byte) 7);
mapped.position(100);
mapped.limit(101);
mapped.force();
~~~

The requested synchronization range is **the entire mapping `[0,128)`**, not merely byte 100. After `force`, `position()` remains 100 and `limit()` remains 101. `force()` neither alters the mark nor moves the read/write cursor to perform synchronization.

**Note:** a program reading back a modified byte right after `put` or `force` only proves that the visible data has the expected value in that session. A successful readback **is not a power-loss simulation test**.

## 4. `force(index, length)`: Forcing Changes of a Sub-Region

Java 17 provides the overload:

~~~java
public final MappedByteBuffer force(int index, int length)
~~~

- `index` is the **starting index in the mapped buffer**.
- `length` is the **number of bytes** in the requested region.
- Half-open range: **`[index, index + length)`**.
- Requires `index >= 0`, `length >= 0`, and `index <= capacity() - length`. Invalid arguments throw **`IndexOutOfBoundsException`**.
- The method does not alter `position`/`limit`. It does not restrict the system to writing strictly the selected bytes: adjacent bytes may also be written due to memory page or device block granularity.

Example with a 16-byte mapping:

~~~java
// Illustrative example: mapped is READ_WRITE, capacity >= 16.
mapped.put(2, (byte) 0x11);
mapped.put(3, (byte) 0x22);
mapped.put(10, (byte) 0x33);
mapped.put(11, (byte) 0x44);

mapped.force(2, 2);   // Requests synchronization of region [2,4).
mapped.force(10, 2);  // Requests synchronization of region [10,12).
~~~

The two `force` calls specify different **required ranges**; do not infer that bytes outside the selected range definitely have not reached the device. The OS may write more.

### Converting ranges when the mapping starts mid-file

Suppose `FileChannel.map(READ_WRITE, 4096, 2048)`.

| Call | Buffer range | Corresponding file bytes |
|---|---|---|
| `force(0, 128)` | [0,128) | [4096,4224) |
| `force(512, 256)` | [512,768) | [4608,4864) |
| `force()` | [0,2048) | [4096,6144) |

All indices are measured in bytes. Java handles system page/block details; never add the file offset yourself to `force(index, length)` arguments.

### Whole-region force or sub-region force?

`force()` is simple and avoids tracking dirty-range lists. `force(index, length)` expresses the exact region to synchronize, which can fit cases where only a few records in a large mapping are updated. **Do not assume** the sub-region overload is always faster across all OSes and devices; the kernel may operate in pages larger than the specified range. Performance must be measured with realistic workloads.

## 5. Runnable Java 17+ Program

The program creates a 16-byte temporary file, maps 8 bytes starting at file offset 4, writes two integers, requests a partial force followed by a full force, inspects buffer state, and reads the file contents back as hex.

Save as **`MappedForceDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HexFormat;

public class MappedForceDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mapped-force-", ".bin");
        Files.write(file, new byte[16]);

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            // Buffer indices 0..7 correspond to file offsets 4..11.
            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 4, 8);

            mapped.putInt(0, 0x01020304);
            mapped.putInt(4, 0x0A0B0C0D);

            // Intentionally constrain the range for relative get/put.
            mapped.position(6);
            mapped.limit(7);

            System.out.println("state=" + mapped.position()
                    + "/" + mapped.limit()
                    + "/" + mapped.capacity());

            // Requests writing indices 0..3, corresponding to file offsets 4..7.
            mapped.force(0, 4);
            System.out.println("partial-force-done");

            // Requests writing all changes in the mapping.
            mapped.force();
            System.out.println("full-force-done");

            System.out.println("state-after=" + mapped.position()
                    + "/" + mapped.limit()
                    + "/" + mapped.capacity());
        }

        byte[] actual = Files.readAllBytes(file);
        System.out.println("file-hex=" + HexFormat.of().formatHex(actual));

        // Best-effort cleanup on JVM exit: the mapping may remain valid
        // after FileChannel closes (depends on GC/OS).
        file.toFile().deleteOnExit();
    }
}
~~~

Compile and run in the directory containing the source:

~~~bash
javac MappedForceDemo.java
java MappedForceDemo
~~~

**Stdout when I/O succeeds:**

~~~text
state=6/7/8
partial-force-done
full-force-done
state-after=6/7/8
file-hex=00000000010203040a0b0c0d00000000
~~~

Step-by-step explanation:

1. The file starts as 16 zero bytes; the mapping starts at offset 4 with size 8.
2. `putInt(0, 0x01020304)` replaces file bytes 4–7 with `01 02 03 04`, and `putInt(4, 0x0A0B0C0D)` replaces file bytes 8–11 with `0A 0B 0C 0D`. `ByteBuffer` uses **big-endian** by default.
3. Both `putInt(index, value)` calls are absolute accesses and do not advance `position`. The program sets `position=6, limit=7, capacity=8`.
4. `force(0, 4)` targets the first region; `force()` targets all 8 bytes regardless of `limit` being 7.
5. After forcing, state `6/7/8` remains intact.
6. The hex output shows four leading zero bytes, eight updated bytes, and four trailing zero bytes.

**What the program tests:** buffer contents and state. **What the program does not test:** crash recovery, atomicity across multiple `put`s, and remote storage guarantees.

### Mapping lifecycle and temporary files

`try-with-resources` closes `FileChannel`. Yet `MappedByteBuffer` and the mapping can persist **after the channel closes**, until the buffer is garbage collected. There is no standard public `unmap()` method on `MappedByteBuffer` in Java 17. On some OSes, deleting or truncating a file that still has a mapping may be restricted. `deleteOnExit()` is a best-effort cleanup when the JVM exits, not a promise to delete the file the moment the channel closes.

## 6. Key Differences from `FileChannel.force(boolean)`

`MappedByteBuffer.force()` and `FileChannel.force(boolean)` serve **two different data modification paths**:

| API | Requested scope | Metadata | Guaranteed to force bytes modified via `mapped.put(...)`? |
|---|---|---|---|
| `mapped.force()` | Entire mapped region contents | No metadata parameter | **Yes**, within the API's scope and conditions |
| `mapped.force(index, length)` | A sub-region of the mapped region | No metadata parameter | **Yes** for the specified sub-region |
| `channel.force(false)` | File content updates via channel API per contract | Does not request metadata | **Not guaranteed** |
| `channel.force(true)` | Content **and metadata** updates via channel API per contract | Requests metadata | **Still not guaranteed** |

According to the `FileChannel.force(boolean)` documentation, the method **is only guaranteed** to force file changes made via methods belonging to `FileChannel`'s contract (and specified related cases). It **may** or **may not** force changes made through a mapped byte buffer created by `map(...)`.

~~~java
// Illustrative example: mapped and channel are both valid.
mapped.put(10, (byte) 99);

channel.force(true); // Does not substitute for forcing the mapped buffer.
mapped.force();       // Appropriate method for changes made via mapped.put.
~~~

**Do not assume `channel.force(true)` is an all-encompassing upgrade for every kind of write.** Passing `true` requests metadata synchronization within `FileChannel`'s scope, but does not turn mapped buffer contents into changes guaranteed to be flushed through the channel.

If an application both modifies mmap contents and updates metadata or writes directly via the channel, design a synchronization policy for **each update path**. Additionally, creating files, renaming, modifying directory entries, or committing multiple related files may require extra rules depending on OS and filesystem.

## 7. `load()` and `isLoaded()` Are Not Persistence Mechanisms

The three APIs serve distinct goals:

- `mapped.load()`: makes a best-effort attempt to bring mapping pages into **physical memory** to reduce page faults on access, **not to flush to disk**.
- `mapped.isLoaded()`: returns a hint as to whether mapped pages are likely in physical memory; this status can change right after checking.
- `mapped.force()`: requests pushing **mapped modifications** to the device.

~~~java
// Illustrative code.
mapped.load();                   // Helps bring data from the file into memory.
boolean likelyLoaded = mapped.isLoaded();

mapped.put(0, (byte) 7);
mapped.force();                  // Requests writing changes to storage.
~~~

`isLoaded() == true` does not prove dirty data is durable. Calling `load()` after `put` does not substitute for `force()` either.

## 8. Limits of Durability After Force

### 8.1. Local vs. remote devices differ

Java 17 specifies the guarantee when `MappedByteBuffer.force()` succeeds **if the file is on a local storage device**. For non-local storage (such as certain network filesystems), Java **provides no equivalent guarantee**. If data traverses network caches, replication, or cloud volumes, durability depends on that storage system's contract and implementation.

### 8.2. No atomicity across multiple updates

~~~java
mapped.putInt(0, newValue);
mapped.putInt(4, newChecksum);
mapped.force();
~~~

*This is an illustrative snippet* with two defined values. If the process crashes after the first `putInt` but before the second, the format can become inconsistent. `force()` also does not make the two fields appear updated **simultaneously** to concurrent readers.

For critical data, consider versioning, checksums, write-ahead logs, double buffering, commit markers, and recovery protocols. Calling `force` alone **provides no rollback**.

### 8.3. Content differs from metadata

`MappedByteBuffer.force()` provides guarantees for **the contents of the mapped region** under the stated conditions. It has no `metaData=true` option. If a program extends a file, creates a new file, modifies attributes, or renames it, do not conclude that a single `mapped.force()` call makes all related metadata and directory entries durable in every scenario.

### 8.4. Concurrent writers and truncation

A mapped buffer can be affected by another program or thread. If the underlying file is truncated while a mapping is alive, part of the mapped region can become **inaccessible**; the specification allows an unspecified exception to occur at the time of access or later. Therefore, you should:

- Coordinate file modification/truncation rights for the entire lifetime of any mapping.
- Control multiple writers touching the same bytes/records via locks or a suitable synchronization protocol.
- Never treat `force()` as a file lock or a transaction providing isolation.
- Never treat being able to read back a new value as proof that concurrency and crash consistency are solved.

## 9. Force Checkpoints: Every Record or Batched?

| Strategy | Advantages | Drawbacks |
|---|---|---|
| `force()` after each critical update | Early durable checkpoint after every successful update | Increases I/O request count |
| `force()` after a batch of updates | Fewer calls, can improve throughput | Changes since the last checkpoint may not survive a crash |
| `force(index, length)` on dirty sub-regions | Expresses the exact region to sync | Must compute indices accurately; OS may write wider pages |
| No proactive `force` | Low immediate sync overhead | No durability checkpoints guaranteed by `MappedByteBuffer.force` |

**There is no rule that "forcing more often is always right in all cases."** Choose checkpoints based on acceptable maximum data loss, application transaction boundaries, and real-device performance. In particular, do not assume `force(index, length)` is always faster than `force()`: dirty pages, page size, filesystem, and I/O controllers can behave differently.

### When multiple mapped regions or views exist

One file can be mapped into multiple `MappedByteBuffer`s with different ranges. When forcing modified portions, identify **which mapping owns the region** and the index **relative to that mapping**. Avoid calling `force` on an unrelated mapping and assuming all edits from another mapping share the same guarantee.

With `slice()` and `duplicate()`, views can share underlying data while maintaining separate positions/limits. A view's index range must be calculated relative to that view; if the application manages synchronization through the original mapping, convert indices back to the corresponding region.

## 10. Error Handling: Never Report Success If Force Fails

Situations to watch for:

| Situation | Consequence / exception |
|---|---|
| `force(index, length)` exceeds capacity or uses negative index | `IndexOutOfBoundsException` |
| I/O error flushing mapped region | `UncheckedIOException` |
| `put(...)` on a `READ_ONLY` mapping | `ReadOnlyBufferException` |
| File truncated, mapped region no longer accessible | Platform-dependent exception may occur, not specified precisely by API |
| `force()` on a `PRIVATE` mapping | Does not write private edits to the real file |
| `FileChannel.map(...)` with invalid permissions/file conditions | May throw permission error, `IOException`, or argument exception depending on case |

Illustrative `force` error handling:

~~~java
try {
    mapped.putInt(recordIndex, value);
    mapped.force(recordIndex, Integer.BYTES);
} catch (java.io.UncheckedIOException e) {
    // Do not confirm durability of this record.
    // Propagate the error so the application layer decides on recovery/retry.
    throw e;
}
~~~

The exception above handles only **I/O sync errors**; writing or indexing can fail in other ways. If the application retries, design idempotency and contention handling beforehand.

### Content verification and durability verification are two kinds of tests

- **Content tests:** create a temporary file, map, put, force, close channel, read bytes back, and compare against expectations. This is a valid test for read/write behavior, like the program in section 5.
- **Fault-injection tests:** simulate storage-path failures at a suitable abstraction; ensure the application never marks a commit as successful when `force` fails.
- **Crash-recovery tests:** require controlled crash/reboot environments, followed by checking data/metadata and recovery. This is a stronger test class; reading back a file in the current JVM **does not prove** crash durability.
- **Concurrency tests:** multiple writers accessing a shared mapping, exercising tricky interleavings to verify lock/record protocols do not corrupt data.

## 11. Common Mistakes

| Mistake | Fix |
|---|---|
| "`put(...)` means saved durably" | `put` modifies mapped memory; call `MappedByteBuffer.force()` when a checkpoint is needed. |
| "`FileChannel.force(true)` always flushes all mmap edits" | Not guaranteed by spec; use `mapped.force()` for mapped changes. |
| "`force()` only processes from position to limit" | It processes the whole `[0, capacity)` range; use the overload to target a sub-range. |
| "The `index` parameter in `force(index, length)` is a file offset" | Index is buffer-relative; add the mapping offset when interpreting file offsets. |
| "Forcing a sub-region writes strictly that sub-region" | The OS may write more bytes due to page/block granularity. |
| "`load()` means flush" | `load()` is for prefetching into memory; `force()` is for writing from mapping to storage. |
| "`MapMode.PRIVATE` can be forced to update the underlying file" | Copy-on-write edits do not propagate to the real file. |
| "Force creates a two-step transaction" | Requires dedicated protocol/locks/versions/WAL. |
| "Closing FileChannel immediately destroys the mapping" | The mapping has an independent lifecycle from the channel. |
| "Returning from force on a network filesystem has the same guarantee as local" | Java provides no such guarantee. |

## 12. Self-Check Scenarios

1. `map(READ_WRITE, 1000, 100)` then `force(10, 5)`: which file bytes belong to the requested range? **[1010,1015)**.
2. `position=70, limit=80, capacity=100` then `force()`: what range is forced? **[0,100)**. `position`/`limit` stay 70/80.
3. Capacity 100, calling `force(98, 4)`: result? **`IndexOutOfBoundsException`**.
4. A `PRIVATE` mapping is modified and forced: does the underlying file save private edits? **No**.
5. Can calling `mapped.load()` after `put` replace `force`? **No**.
6. Is `channel.force(true)` after `mapped.put(...)` sufficient guarantee? **Not guaranteed by the API**; force the mapped buffer instead.
7. If `force` succeeds on a local file, does the program gain atomicity across two `putInt` calls? **No**.
8. Does a network file have the same `force` guarantee as a local one? **No, per the Java 17 specification**.
9. A buffer is mapped and the channel closes; is the mapping guaranteed to vanish immediately? **No**.
10. Does reading back the expected bytes after `force` prove power-loss recovery? **No**.

## 13. Official References

- [Java SE 17 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): `force()`, `force(index, length)`, exceptions, local/remote guarantee conditions, `load()`, and `isLoaded()`.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `map(...)`, `MapMode`s, and the difference between `force(boolean)` and mapped buffer force.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position/limit, absolute indexed access, `putInt`, and byte order.
