# Risks When a File Is Resized While Memory-Mapped in Java NIO

## 1. Context: File Mapping and File Size Are Two Separate States

In Java NIO, `FileChannel.map(...)` lets you map a region of a file into memory address space and returns a `MappedByteBuffer`. Afterward, the program reads or writes using `ByteBuffer` methods instead of repeatedly transferring data via `FileChannel.read(...)` or `write(...)`.

Example:

~~~java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_ONLY, 0, 8);
    byte firstByte = mapped.get(0);
}
~~~

This is an **illustrative code snippet**: `path` and imports must be defined, the file must have at least 8 bytes when creating the mapping, and the environment must support this operation.

At least three quantities must be distinguished:

- **Current file size** (`channel.size()` or `Files.size(path)`): can change due to appends, truncation, or another actor.
- **Mapping range**: determined when `map(mode, position, size)` is called, e.g., file offsets from 0 up to byte 8. It does not grow or shrink automatically in sync with file size.
- **State of `MappedByteBuffer`**: `position`, `limit`, and `capacity` are buffer state; `capacity` is fixed to the mapping size, not a variable that continuously tracks file size.

Diagram when the file initially has 8 bytes:

~~~text
Initial file, size = 8:
offset:     0   1   2   3   4   5   6   7
         +---+---+---+---+---+---+---+---+
         | A | B | C | D | E | F | G | H |
         +---+---+---+---+---+---+---+---+
                    |  map(0, 8)  |
                    v             v
Mapping: +---+---+---+---+---+---+---+---+
         | A | B | C | D | E | F | G | H |
         +---+---+---+---+---+---+---+---+
         capacity = 8

Another actor truncates the file down to size = 3:
         +---+---+---+
File:    | A | B | C |
         +---+---+---+

Old mapping: still represents a region with capacity = 8,
             but the part corresponding to bytes 3..7 may
             no longer be accessible. DO NOT test this
             yourself by reading those bytes.
~~~

**Key point:** a mapping can still exist while the underlying file region backing it has changed. The fact that a Java operation still permits `get(7)` under `limit` does not prove that position is still backed by the current file in the OS.

## 2. Java 17 Contract: Which Behaviors Are Guaranteed?

According to the Javadoc of `FileChannel.map` and `MappedByteBuffer` in Java 17:

1. A mapped region can become **wholly or partially inaccessible at any time**, for example when the backing file is truncated.
2. When accessing an inaccessible region, the API **does not guarantee a specific exception type**; the failure may be detected immediately on access or later. Therefore you cannot write one specific `catch` block and assume it is safe across all operating systems.
3. When the file's contents **or size** changes, whether and when those changes are reflected in the mapped buffer is **not uniformly specified**.
4. Behavior of `map` if the requested region **does not lie completely within the file** is also not uniformly guaranteed in Java 17.
5. The mapped buffer and channel have **different lifecycles**: closing the channel does not necessarily unmap immediately; the mapping can persist until the buffer is reclaimed by the garbage collector.

Consequently, never treat a successful read on one specific OS or JDK as proof that the operation is safe on another environment.

API contract references:

- [FileChannel.map — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#map(java.nio.channels.FileChannel.MapMode,long,long))
- [MappedByteBuffer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html)

## 3. Most Dangerous Case: Truncating Smaller Than the Mapped Region

Suppose an application mapped region `[0, 4096)` of a file. Another thread or process calls `FileChannel.truncate(1024)`, leaving the file only 1024 bytes long.

On the buffer side, `capacity()` may still be 4096 because capacity is fixed at creation time. Yet when the application continues reading indices 1024 through 4095, part of the mapping may have lost its backing in the file.

~~~text
Time T0:       file = 4096 bytes; map(0, 4096)
Time T1:       application is processing indices 0..1023
Time T2:       another process truncates file to 1024
Time T3:       application attempts to read index 3000 -> risk of
               accessing an unavailable mapped region
~~~

Actual consequences can include:

- Buffer access fails in a way the program cannot predict with a single fixed exception type.
- The process receives an error from the OS memory/mapping protection mechanism; details depend on the runtime and OS.
- An in-progress sequential read workflow can no longer prove data correctness or consistency.
- The file may have been replaced, or metadata already used to validate contents no longer matches the file object the application is using.

**Do not try to read "lost bytes" to diagnose this in production code.** Safe design aims to avoid creating conditions where invalid regions are accessed, rather than relying on a specific error being thrown.

### 3.1. Risky code example — do not run as a lab exercise

~~~java
// RISK ILLUSTRATION SNIPPET: DO NOT RUN to test for failure.
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY, 0, 4096);

// May occur from ANOTHER thread or process:
otherChannel.truncate(1024);

// Never infer get(3000) is safe from capacity() == 4096.
byte value = mapped.get(3000);
~~~

Variables `channel`, `otherChannel`, and the file object are not initialized in this snippet: this is **code illustrating a hazardous scenario**, not a standalone example. It demonstrates a design flaw to avoid and strictly guarantees no specific stdout or exception.

## 4. When a File Grows: The Old Mapping Does Not Expand Automatically

The opposite scenario: the file initially has 8 bytes and the program maps 8 bytes. Later, another actor appends 4 bytes, making the file 12 bytes long.

~~~text
T0: file.size() = 8
    mapped.capacity() = 8

T1: append 4 bytes -> file.size() = 12

T2: mapped.capacity() still = 8
    indices 8..11 are outside the index space of the old buffer.
~~~

`MappedByteBuffer` does not turn into a capacity-12 buffer just because the file became longer. If the application wants to process new bytes beyond the mapped range, it must **create an appropriate mapping** (e.g., mapping the new region or remapping via another instance/range) after confirming a valid data version.

This differs from truncation:

- **File grows**: appended bytes lie outside the old boundary; trying `mapped.get(8)` when `limit=8` violates normal buffer bounds.
- **File shrinks**: an index **can still appear valid in the buffer** while the underlying file region no longer exists, making the risk trickier.

Do not assume appending is safe when a concurrent writer might also overwrite or truncate the earlier part. Ownership and synchronization policies are required whenever multiple actors modify the same file.

## 5. Both Content Edits and Size Changes Affect Consistency

A file that keeps the same size while its contents are overwritten can still cause reads to mix multiple versions.

Suppose a parser reads a header and payload:

~~~text
Version A:
[ header length=8 ][ payload of A ]

Writer updates to version B of the same size:
[ header length=8 ][ payload of B ]

Reader reads header from A, then payload from B
=> Result may correspond to no complete version at all.
~~~

`READ_ONLY` only rejects writes **through that mapped buffer**; it does not lock the file against other writers. `PRIVATE` is likewise not an absolute fixed snapshot against external modifications. In all three modes, data consistency when a file is edited from another source must be solved with additional design.

Attributes such as `FileChannel.size()`, `Files.getLastModifiedTime(...)`, or `BasicFileAttributes.fileKey()` can help detect **observable** changes, but do not prove data was untouched between two checks. Timestamps have varying resolution; `fileKey` may not be supported by a provider; unchanged size does not rule out content overwrites.

## 6. Do the Three MapModes Protect Against File Resizing?

| MapMode | Write behavior via mapping | Automatically protects against external file truncate/resize? |
| --- | --- | --- |
| `READ_ONLY` | `put` is forbidden, throws `ReadOnlyBufferException`. | **No.** The mapped region itself can still be affected when the backing file changes. |
| `READ_WRITE` | `put` can update the file; `force()` supports sync requests. | **No.** An external writer can still truncate or alter the mapped range. |
| `PRIVATE` | Writes via copy-on-write without propagating private changes to the file. | **No.** It does not guarantee an immutable snapshot against all size changes in the backing file. |

Do not try to "fix truncation" with `mapped.force()`, `mapped.load()`, or `mapped.isLoaded()`:

- `force()` handles sync requests for a `READ_WRITE` mapping; it does not restore lost file ranges. It has no commit effect for `PRIVATE`.
- `load()` tries to page mapping pages into RAM. It does not decouple the mapping from the backing file or grant read access to a region that has become unavailable.
- `isLoaded()` is only a hint about resident pages, not a guarantee of safe access when the file is resized.

Rule: **MapMode governs access type and change propagation**, not a file-size locking contract.

## 7. Why Checking Size Before Each get() Is Still Insufficient

An intuitive fix that comes to mind:

~~~java
long currentSize = channel.size();
if (targetOffset < currentSize) {
    return mapped.get(index);
}
~~~

This is an **unsafe illustrative snippet**, with `targetOffset`, `index`, and `mapped` declared elsewhere. Even if the check holds at first, another writer can shorten the file **after the check and before `get()`**.

That is a **TOCTOU** (*time-of-check to time-of-use*) bug:

~~~text
Reader                         Writer
  |                              |
  +-- size() => 4096             |
  |                              +-- truncate(1024)
  +-- mapped.get(3000)           |
         may be unsafe           |
~~~

Therefore:

- Checking `size` and `offset + length` bounds is **necessary** when establishing a mapping, but insufficient in an uncoordinated multi-writer environment.
- Re-checking metadata after every record can help detect changes, yet does not eliminate the race window between operations.
- A `synchronized` block or `ReentrantReadWriteLock` within **one JVM** protects only threads that actually participate in that same lock; another process can still modify the file.
- `FileLock` can help when all actors honor the locking policy, though its effectiveness varies across operating systems and filesystems; do not treat it as a universal cure against resizing during mmap.

## 8. Solution 1: Exclusive Ownership of File Lifecycle and Size

When the program itself creates and controls the file, the simplest approach is **prohibiting size changes for as long as any mapping is still in use**.

A disciplined workflow:

1. Finish writing data and finalize the file size.
2. Publish the file to readers once data is complete.
3. Each reader opens a mapping on the stable file, processes it, and drops references to the mapping upon completion.
4. To release a new version, write to a **new** file with a distinct name/version; do not truncate the version readers are actively using.
5. Reclaim the old file only when no readers remain and the OS allows releasing the associated resources.

If you can control all writers, this is a much stronger risk-reduction foundation than trying to catch exceptions thrown from accessing a lost region.

### 8.1. Do not overwrite a file in place while readers are mapping it

One implementation option is versioned files:

~~~text
data-v001.bin     <- reader A already mapped it, keep intact
data-v002.bin     <- writer creates a complete new version
current.version   <- metadata pointing to the new version

Reader B opens data-v002.bin.
Reader A finishes on data-v001.bin.
Only after all old readers finish, clean up data-v001.bin.
~~~

Ensure metadata/version updates use an appropriate atomic mechanism so readers see only complete files, and maintain reference management (reference counts, leases, epochs, or bounded reader lifetimes).

`Files.move(..., ATOMIC_MOVE)` can assist publish steps **when supported by the filesystem**, though it may throw `AtomicMoveNotSupportedException`; it does not by itself guarantee a consistent snapshot strategy or permission to delete/rename a currently mapped file on every platform.

## 9. Solution 2: Mapping a Stable Copy

If the source can be altered by another writer and the application needs an independent dataset, you can **make a copy and map that copy**. When the copy is privately owned and untouched by other processes, resizing the source file does not affect the copy's size.

~~~text
Source file (mutable):
source.bin (8 bytes) ----- COPY ----- snapshot.bin (8 bytes)
       |                                   |
       |                                   +-- READ_ONLY mapping
       |
       +-- writer truncates to 2 bytes

snapshot.bin still has 8 bytes and its mapping is
unaffected by truncating SOURCE.
~~~

**Important condition:** `Files.copy` does not automatically guarantee a consistent snapshot if a writer is mutating the source **during the copy**. Coordinate ownership/locking, read an already-published immutable source, or use real storage/filesystem snapshots if strong consistency is required. Also ensure no other actor truncates the **copy file** itself while a reader maps it.

### 9.1. Runnable Java 17+ program avoiding truncation of the mapped region

This example resizes only the **source file**. The mapping is created on **a different snapshot file**, yielding deterministic results in a single-threaded program. No attempt is made to access an invalid mapping.

Save as `SafeMappedSnapshotDemo.java`:

~~~java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class SafeMappedSnapshotDemo {

    private static String ascii(MappedByteBuffer mapped) {
        MappedByteBuffer view = mapped.duplicate();
        view.position(0);
        byte[] bytes = new byte[view.remaining()];
        view.get(bytes);
        return new String(bytes, StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("mmap-resize-demo-");
        Path source = dir.resolve("source.bin");
        Path snapshot = dir.resolve("snapshot.bin");

        // Register cleanup on JVM exit, instead of trying to delete a currently mapped file.
        // Entries registered are deleted in reverse registration order.
        dir.toFile().deleteOnExit();
        source.toFile().deleteOnExit();
        snapshot.toFile().deleteOnExit();

        Files.writeString(source, "ABCDEFGH", StandardCharsets.US_ASCII);
        Files.copy(source, snapshot);

        try (FileChannel channel = FileChannel.open(
                snapshot, StandardOpenOption.READ)) {

            long size = channel.size();
            long offset = 2;
            int length = 4;

            // Check via subtraction to avoid overflow when checking offset+length.
            if (offset < 0 || length <= 0 ||
                    offset > size || length > size - offset) {
                throw new IOException("Mapping vượt phạm vi snapshot");
            }

            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_ONLY, offset, length);

            System.out.println("snapshotSize=" + size);
            System.out.println("mappedCapacity=" + mapped.capacity());
            System.out.println("mappedBefore=" + ascii(mapped));

            // Truncate only SOURCE, leaving the mapped SNAPSHOT untouched.
            Files.writeString(
                    source,
                    "XY",
                    StandardCharsets.US_ASCII,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);

            System.out.println("sourceAfterResize=" +
                    Files.readString(source, StandardCharsets.US_ASCII));
            System.out.println("mappedAfter=" + ascii(mapped));
        }
    }
}
~~~

Compile and run:

~~~bash
javac SafeMappedSnapshotDemo.java
java SafeMappedSnapshotDemo
~~~

Deterministic stdout in an environment supporting local file reading and mapping:

~~~text
snapshotSize=8
mappedCapacity=4
mappedBefore=CDEF
sourceAfterResize=XY
mappedAfter=CDEF
~~~

Explanation:

- `source.bin` has 8 bytes `ABCDEFGH`; `Files.copy` creates an independent `snapshot.bin` also having 8 bytes.
- The mapping uses `offset=2`, `length=4`, so the initial readable region is `CDEF`; `capacity=4`, not the full 8 bytes of the snapshot.
- Writing `"XY"` with `TRUNCATE_EXISTING` replaces the source content, shrinking **source** to 2 bytes.
- Snapshot is neither overwritten nor truncated, so the mapping continues to observe `CDEF`.
- The example cleans up files via `deleteOnExit()` because the exact time the mapping is released after closing the channel is unspecified. In real applications, use a dedicated lifecycle strategy; do not treat `deleteOnExit` as a long-term file management system.

The example illustrates only **how to isolate a mutable source**. To obtain a consistent snapshot when a source has concurrent writers, coordinate publishing complete versions or use reliable snapshot features before `Files.copy`.

## 10. Solution 3: Windowed Mapping and Re-establishing Access Ranges by Version

For large files or append-only streams, processing can be split into bounded **mapping windows**:

~~~text
20 MiB file:
  [0..4 MiB) [4..8 MiB) [8..12 MiB) [12..16 MiB) [16..20 MiB)
      window 1    window 2    window 3    window 4     window 5

Each step:
  - map only valid published regions;
  - read through the region and finish work;
  - move to the next region/version under ownership rules.
~~~

Benefits of windowed mapping:

- Each `MappedByteBuffer` has an `int` `capacity`, avoiding requests to map a region larger than `Integer.MAX_VALUE` bytes on Java 17.
- Bounds the amount of data processed per pass.
- If the file is **append-only** and already-published bytes are never altered, readers can map newly appended regions up to the committed length watermark.

However, **windowing alone does not eliminate truncation risk**. If a writer is permitted to shrink or overwrite active regions, any window can lose validity. Creating a new window after reading `channel.size()` can also suffer from TOCTOU if an uncoordinated writer is present.

A stronger system tracks metadata for **committed length** and **file version**, along with the invariant that writers never truncate published data while readers are still using it.

## 11. Synchronization Across Threads and Processes

### 11.1. Within a single JVM

If an application has reader threads and writer threads:

- A `ReadWriteLock` allows multiple concurrent readers while writers wait to resize.
- Writers hold the write lock from the start of resizing until the new version is published.
- Readers hold the read lock while mapping and reading protected data.

However, a Java lock applies only to threads **that actually use that same lock**. If another process has permission to truncate the file, in-JVM locking cannot prevent external risk.

### 11.2. Across processes

You can consider `FileChannel.lock(...)` or `tryLock(...)` as a coordination mechanism when all actors obey the rules. Keep in mind:

- Shared/exclusive lock availability depends on OS and filesystem.
- Some file locks are **advisory**: non-cooperating processes can still modify the file.
- Mapping and locking can interact differently per platform, including cases where locks cannot be acquired or mapping fails.

Therefore, for critical data, **exclusive file-version ownership, immutable snapshots, or new-file publishing protocols** are usually easier to verify than expecting a lock call to block every external edit.

## 12. Using Each API for Its Intended Purpose

| API | What it supports | What it does NOT solve |
| --- | --- | --- |
| `FileChannel.map(mode, offset, length)` | Creates a fixed mapping over the requested range. | Does not automatically track size growth/shrinkage to adjust capacity. |
| `channel.size()` / `Files.size(path)` | Reads file size at call time. | Does not protect against resizing immediately after reading. |
| `channel.truncate(newSize)` | Shortens the file if `newSize` is smaller than current size (when writable). | Does not automatically repair active mappings in readers. |
| `mapped.force()` | Syncs `READ_WRITE` mapping modifications per contract. | Does not restore truncated file regions; does not guarantee a snapshot. |
| `mapped.load()` | Attempts to load mapping pages into memory. | Does not hold the file at its old size or keep pages accessible if backing changes. |
| `mapped.isLoaded()` | Provides a residency status hint. | Not a safety check against truncation. |
| `FileLock` | Coordinates access among cooperating actors on supporting platforms. | Does not stop uncooperative writers across all OSes/filesystems. |
| `Files.copy(...)` | Creates an independent target file when copy succeeds. | Does not guarantee a consistent copy if the source is modified concurrently. |
| `Files.move(..., ATOMIC_MOVE)` | Requests an atomic move if supported by provider. | Does not automatically switch mappings held by path readers; does not release old mappings. |

For `FileChannel.truncate(n)`, if `n` is greater than or equal to the current file size, the API **does not necessarily extend the file**. To grow a file to a larger size, use a write operation or provider-supported mechanism; do not call `truncate(largerSize)` assuming new byte space has been allocated.

## 13. Design Rules for an mmap Reader Tolerant of File Version Changes

A safe production reader should define a clear contract with writers before optimizing with mmap:

1. **Which files are allowed to change?** If a file has active readers, at minimum forbid truncating/overwriting published regions or switch to immutable versions.
2. **How are versions identified?** Use a version ID, manifest, content checksum, or file generation; size and `mtime` alone are insufficient for strong consistency.
3. **Which exact version does a reader open?** Readers resolve a complete version path and keep it stable throughout the pass.
4. **When are old files cleaned up?** Confirm no active readers or leases remain, while accounting for the OS retaining mappings after channel close.
5. **Can you ever map past EOF?** Boundaries must derive from a published size held stable via ownership rules.
6. **Which failure conditions must halt processing?** Distinguish missing files, permission errors, malformed data, revoked versions, and `IOException`.
7. **Is the goal read-only or mutation?** For reading only, pick `READ_ONLY` on immutable files. For mutation, define a commit protocol and durability policy; `READ_WRITE.force()` does not solve concurrent resizing.
8. **Is mmap truly needed?** If another writer resizes data continuously without coordination, reading into independent buffers via `FileChannel.read(...)` can offer simpler error and lifecycle control, though content consistency still needs design.

You cannot simply "catch all mmap errors" and continue as if nothing happened. A reader detecting that data no longer matches a verified version must stop and reload via a designed workflow.

## 14. Common Mistakes to Avoid

### Mistake 1: seeing unchanged capacity and assuming contents still exist

After a file is truncated, `mapped.capacity()` still describes the original mapping size. It **does not** prove every corresponding byte remains available.

### Mistake 2: calling force() to recover lost data

`force()` does not extend a file or reallocate a truncated mapping region. For `READ_WRITE`, it only relates to syncing edits from the mapping to the storage device.

### Mistake 3: thinking PRIVATE is an immutable file snapshot

PRIVATE has copy-on-write semantics for modifications made through that mapping. It does not guarantee isolation from all external content or size changes.

### Mistake 4: believing checking size before get eliminates the risk

Checking size does not lock the file. A writer can truncate immediately afterward. That is TOCTOU; control changes via a protocol or ownership.

### Mistake 5: ignoring mapping lifetime

Closing `FileChannel` does not guarantee immediate mapping reclamation. On some OSes, delete/rename/truncate can be restricted because the file is still mapped.

### Mistake 6: mapping a file replaceable by another version without tracking version

A `Path` is a name that can be bound to a different file object after replacement. An existing mapping is not guaranteed to switch to the new version just because the same path now points to it. Readers must track objects/versions explicitly.

### Mistake 7: assuming newly appended bytes appear automatically in the old buffer

`MappedByteBuffer` has a fixed capacity. New bytes beyond the old mapped region must be read via a new mapping or API with appropriate range.

### Mistake 8: testing by deliberately provoking OS errors on a mapped file

Truncating a mapped file and attempting to read the cut portion can produce consequences beyond handling a single standard exception across platforms. Test ownership policies, valid mapping ranges, and version transitions using tests that do not access invalidated mappings.

## 15. Self-Check Questions

1. **A 4 KiB file is mapped completely, then truncated to 1 KiB. Does `mapped.capacity()` automatically shrink to 1 KiB?** No. Buffer capacity is fixed; the mapped region beyond the new length risks becoming unavailable.
2. **Can you rely on `catch (IndexOutOfBoundsException)` to handle all accesses to a truncated portion?** No. The index may remain valid in the buffer while the underlying mapping is no longer valid; the API does not prescribe a single fixed exception type for this case.
3. **If a file is appended from 8 to 12 bytes, does an 8-byte mapped buffer automatically see indices 8..11?** No; capacity stays 8.
4. **Does `READ_ONLY` prevent another process from truncating the file?** No. It only forbids writes through this buffer.
5. **Does `PRIVATE` guarantee a consistent snapshot when the backing file is resized?** No.
6. **Why is checking `channel.size()` before `mapped.get(i)` insufficient?** A resize can occur between the check and `get`.
7. **Can `FileChannel.force()` or `MappedByteBuffer.force()` "fix" a mapping after truncation?** No. Those are data-synchronization APIs under contract, not tools to re-establish size.
8. **What is the most common way to avoid risks with multiple readers?** Publish immutable/versioned files and never resize a version readers are actively using; clean up old versions according to reader lifetimes.
9. **Is `Files.copy(source, snapshot)` enough for a consistent snapshot under a concurrent writer?** Not yet. Coordinate so copying does not happen mid-modification, or use storage-level snapshots.
10. **Why must old files still be managed even after closing the channel?** Mappings have an independent lifecycle and are not guaranteed to be released immediately upon channel close.
11. **Can a single Java 17 `MappedByteBuffer` map a file larger than 2 GiB into one buffer?** No, due to this API's mapping-size limit; split into regions or choose an appropriate API.
12. **When strong data consistency is required, should you rely solely on `mtime` and file size?** No. They are merely indicators and do not guarantee the file wasn't modified between two checks.

**Key takeaway:** memory mapping binds a buffer to a **file region at mapping creation time**, without freezing the backing file. If the file shrinks, the mapped region can lose accessibility; if the file grows, the old buffer does not increase its capacity. Manage **ownership, versions, and file lifecycles**, keep mapped data stable, or map an immutable copy when readers must be isolated from resizing.
