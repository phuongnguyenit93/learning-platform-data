# MapMode READ_ONLY, READ_WRITE, and PRIVATE in Java NIO.2

## 1. What Is a Memory-Mapped File?

In Java NIO.2, the `FileChannel.map(...)` method maps a **byte region of a file** into the process's memory space and returns a `MappedByteBuffer`. Instead of repeatedly calling `read()` to copy bytes from the channel into a separate buffer, the program can access the mapped region using `ByteBuffer`'s `get(...)` and `put(...)` methods.

Consider an example file containing 8 bytes:

~~~text
File example.bin (byte offsets)
  0   1   2   3   4   5   6   7
+---+---+---+---+---+---+---+---+
| A | B | C | D | E | F | G | H |
+---+---+---+---+---+---+---+---+
        |<----- map(2, 4) ---->|
               maps C D E F

New MappedByteBuffer:
  index  0   1   2   3
       +---+---+---+---+
       | C | D | E | F |
       +---+---+---+---+
~~~

In `channel.map(mode, position, size)`:

- `mode` chooses **read/write permissions and how buffer modifications affect the file**.
- `position` is the **starting offset in the file**, in bytes, of type `long`, non-negative.
- `size` is the **number of bytes** of the mapped region, passed as `long` in the API, though a `MappedByteBuffer` on Java 17 has an `int`-represented capacity: a single map call cannot exceed `Integer.MAX_VALUE` bytes.
- The returned buffer has `position() == 0`, `limit() == capacity() == size`; index 0 in the buffer corresponds to file offset `position`.
- `FileChannel.map(...)` does not change the channel's current I/O position cursor. It establishes an independent mapping.

`MappedByteBuffer` is a direct `ByteBuffer`. Therefore, it supports relative or absolute `get`/`put`, byte order, views/slices, and position/limit controls just like a regular buffer. The difference lies in the data backing and how the operating system manages mapped memory pages.

**Scope of this article:** the three constants `FileChannel.MapMode.READ_ONLY`, `READ_WRITE`, and `PRIVATE`. They may look similar when merely reading data, yet exhibit **very different behavior when the application mutates the buffer**.

## 2. Comparing the Three MapModes

| Mode | Read data? | `put` into mapping? | Are mapping changes written back to file? | How must FileChannel be opened? |
| --- | --- | --- | --- | --- |
| `READ_ONLY` | Yes | No; throws `ReadOnlyBufferException` | No changes made by this buffer | With `READ` permission |
| `READ_WRITE` | Yes | Yes | Yes; changes are propagated to the file via mapping mechanics, and `force()` can be called to request flushing to storage | With both `READ` and `WRITE` |
| `PRIVATE` | Yes | Yes, within the mapping's private space | **No**; mapping changes are not propagated back to the file | With both `READ` and `WRITE` |

Key distinctions:

- `READ_ONLY` protects **this view from writes through the buffer API**. It does not make the whole file immutable: another process or thread may still alter the file outside the mapping.
- `READ_WRITE` is used when you want to update file contents via mapped memory. Modified contents may be written back to the file by the OS at another time, so call `MappedByteBuffer.force()` per contract when synchronization control is needed.
- `PRIVATE` is **copy-on-write**: initially reads from the mapped file region; on write, the OS may create a private copy of the modified pages. Only the program sees those private mapping changes; they are not propagated to the file and do not appear to other processes through that private mapping.

Do not treat `PRIVATE` as an immutable snapshot of the entire file. Whether external changes to the underlying file occur, and when those changes are reflected into the mapping, **depends on the operating system and is not guaranteed by the API**. What is explicitly promised is that **changes made through a private mapping are not written back to the file**.

## 3. Opening FileChannel with Appropriate Permissions

Basic syntax:

~~~java
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("example.bin");

try (FileChannel channel =
        FileChannel.open(path, StandardOpenOption.READ)) {

    long length = channel.size();
    MappedByteBuffer mapped =
            channel.map(FileChannel.MapMode.READ_ONLY, 0, length);
    // Read mapped here.
}
~~~

This is an **illustrative snippet**, assuming `example.bin` already exists and is non-empty. `FileChannel.open(path, READ)` permits a `READ_ONLY` map. To map `READ_WRITE` or `PRIVATE`, open the channel with both permissions:

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

    MappedByteBuffer writable =
            channel.map(FileChannel.MapMode.READ_WRITE, 0, channel.size());

    MappedByteBuffer privateView =
            channel.map(FileChannel.MapMode.PRIVATE, 0, channel.size());
}
~~~

**Permission note:** even though `PRIVATE` does not write changes back to the file, the `FileChannel.map` overload in Java 17 still requires the channel to be opened with both `READ` and `WRITE` for this mode. Opening a channel read-only and requesting `READ_WRITE` or `PRIVATE` can throw `NonWritableChannelException`; if required read access is missing, you may encounter `NonReadableChannelException`. OS-level file permissions must also allow the corresponding operations.

Do not open the channel with `TRUNCATE_EXISTING` when the goal is to map existing data for reading or editing: this option can wipe all content immediately upon opening. If you want to create a new file and map it, purposefully prepare its size/content region and handle the empty-file case.

## 4. READ_ONLY: Direct Reading from the File Region, No Writing Allowed

~~~java
try (FileChannel channel = FileChannel.open(file, StandardOpenOption.READ)) {
    MappedByteBuffer readOnly = channel.map(
            FileChannel.MapMode.READ_ONLY, 0, channel.size());

    byte first = readOnly.get(0);
    System.out.println((char) first);

    // Throws ReadOnlyBufferException:
    // readOnly.put(0, (byte) 'X');
}
~~~

This is an **illustrative snippet** where `file` is a `Path` pointing to a non-empty file. Calling `isReadOnly()` on this buffer returns `true`. Operations that mutate data through the buffer such as `put(...)` are rejected.

READ_ONLY is suitable when:

- Scanning a large file for a byte pattern, index, or lookup table without needing to modify it.
- Reading binary structures at fixed offsets in a file.
- Wanting the mapping's API to reject accidental writes caused by programming bugs.

READ_ONLY **does not mean** immunity against changes outside the program. If another process modifies or shrinks the file while the mapping exists, the observed contents may change or the mapped region may become inaccessible. Java does not guarantee a snapshot of the file as of the moment of mapping.

If the application needs unchanging data for processing, control file lifecycle/synchronization, read an independent copy, or use a system-appropriate consistency mechanism.

## 5. READ_WRITE: Buffer Edits Affect the File

~~~java
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

    MappedByteBuffer rw = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, channel.size());

    rw.put(0, (byte) 'J'); // Modifies the first byte of the mapped region.
    rw.force();            // Requests synchronization of changes made via the mapping.
}
~~~

Key points to understand:

1. `put(0, ...)` writes to the mapped region at **buffer index 0**, corresponding to the start position passed to `map`. In the example above, that is the first byte of the file.
2. In `READ_WRITE`, changes are propagated to the file via the operating system's mechanism. **When** changes become visible to other processes can vary by platform.
3. `rw.force()` requests flushing mapping changes to the storage device. According to the Java 17 API, for files on a **local** storage device, this call guarantees that changes from the buffer have been written to the device upon return; for non-local devices, no equivalent guarantee exists.
4. `rw.force(int index, int length)` requests synchronizing a sub-range of the mapped region when range control is desired; this API is present in Java 17. It may perform additional I/O outside the requested range due to physical storage units.
5. Handle I/O errors from `force()`. With `MappedByteBuffer.force`, write errors may be thrown as `UncheckedIOException`.

`MappedByteBuffer.force()` and `FileChannel.force(boolean metaData)` are not completely interchangeable. In Java 17, `FileChannel.force` **is not guaranteed** to synchronize changes made through a `MappedByteBuffer`. For bytes modified via memory mapping, call `mapped.force()` when those changes must be synchronized.

A common misconception: `force()` **is not** a mandatory "save file" command after every `put`. `READ_WRITE` mode already has propagation semantics; `force` is a tool to request synchronization timing per contract, especially when the application has data durability requirements.

## 6. PRIVATE: Copy-on-Write and Isolation from the Underlying File

~~~java
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

    MappedByteBuffer privateView = channel.map(
            FileChannel.MapMode.PRIVATE, 0, channel.size());

    privateView.put(0, (byte) 'P');

    // privateView.get(0) sees 'P'.
    // The byte at position 0 in the file is NOT modified by the put call above.
}
~~~

PRIVATE mode is very different from a read-only buffer: the program **is allowed to write** and read back the modified bytes. However, that effect stays within the mapping's private space.

~~~text
Original file:
      H E L L O
          |
          +--------> PRIVATE mapping
                        |
                    put(0, 'P')
                        |
Private mapping sees:
      P E L L O

Original file remains:
      H E L L O
~~~

A private mapping does not automatically create a "new file version." Privately modified bytes exist only in the mapping and can be lost when the mapping is released. If you want to save the edited version to a new file, the program must explicitly copy the resulting data to a destination file (e.g., via `Files.newOutputStream(...)` or a separate write channel) with consistency rules.

`force()` on `PRIVATE` **does not write privately modified bytes back to the file**; in Java 17, `MappedByteBuffer.force()` has no effect for `READ_ONLY` or `PRIVATE` mappings. Do not use `force` as a way to "commit" private mapping changes.

### 6.1. PRIVATE Does Not Mean "Acting as a Transaction"

A typical transaction has commit/rollback, defined isolation levels, and consistency rules. `MapMode.PRIVATE` only provides **copy-on-write semantics for changes made through that mapping**; it does not on its own provide:

- An interface to commit changes back to the file.
- A guarantee of a completely isolated snapshot against external modifications.
- The ability to undo changes from another `READ_WRITE` mapping.
- Locking/synchronization mechanisms between processes, or conflict resolution.

If you want to experiment with editing a binary dataset before deciding whether to keep it, PRIVATE can be useful for local processing; if you need durable transactions, you must design a dedicated mechanism at the application level.

## 7. Complete Java 17+ Example: Comparing the Three Modes on the Same File

The following program uses a temporary file containing the ASCII string `HELLO`:

1. Opens `READ_ONLY`, reads the content, and demonstrates that `put` is blocked.
2. Opens `PRIVATE`, changes `H` to `P`. The private buffer sees `PELLO`, yet re-reading the file still shows `HELLO`.
3. Opens `READ_WRITE`, changes `E` to `A`, and calls `force()`. Re-reading the file shows `HALLO`.

Save as `MapModeDemo.java`:

~~~java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MapModeDemo {

    static String readAscii(MappedByteBuffer mapped) {
        // Duplicate preserves the original buffer's position/limit.
        MappedByteBuffer copy = mapped.duplicate();
        copy.position(0);
        byte[] bytes = new byte[copy.remaining()];
        copy.get(bytes);
        return new String(bytes, StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("map-modes-", ".bin");

        // Register for deletion on JVM exit. Cleanup of mmap depends on the OS;
        // do not rely on immediate deletion while the buffer still holds a mapping.
        file.toFile().deleteOnExit();
        Files.writeString(file, "HELLO", StandardCharsets.US_ASCII);

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ)) {

            MappedByteBuffer ro = channel.map(
                    FileChannel.MapMode.READ_ONLY, 0, 5);

            System.out.println("readOnly=" + ro.isReadOnly());
            System.out.println("readOnlyText=" + readAscii(ro));

            boolean blocked = false;
            try {
                ro.put(0, (byte) 'X');
            } catch (ReadOnlyBufferException ex) {
                blocked = true;
            }
            System.out.println("readOnlyBlocked=" + blocked);
        }

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

            MappedByteBuffer privateView = channel.map(
                    FileChannel.MapMode.PRIVATE, 0, 5);
            privateView.put(0, (byte) 'P');

            System.out.println("privateView=" + readAscii(privateView));
            System.out.println("fileAfterPrivate=" +
                    Files.readString(file, StandardCharsets.US_ASCII));

            MappedByteBuffer rw = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 5);
            rw.put(1, (byte) 'A');
            rw.force();

            System.out.println("readWriteView=" + readAscii(rw));
            System.out.println("fileAfterReadWrite=" +
                    Files.readString(file, StandardCharsets.US_ASCII));
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac MapModeDemo.java
java MapModeDemo
~~~

**Expected stdout in a typical environment supporting memory-mapped files:**

~~~text
readOnly=true
readOnlyText=HELLO
readOnlyBlocked=true
privateView=PELLO
fileAfterPrivate=HELLO
readWriteView=HALLO
fileAfterReadWrite=HALLO
~~~

Explanation:

- `readOnlyText=HELLO`: the `READ_ONLY` mapping allows reading the original bytes.
- `readOnlyBlocked=true`: `put` throws `ReadOnlyBufferException` and leaves the file untouched.
- `privateView=PELLO` with `fileAfterPrivate=HELLO`: edits on `PRIVATE` affect only the private mapping.
- `readWriteView=HALLO` and `fileAfterReadWrite=HALLO`: the `READ_WRITE` mapping modifies the second byte in the file.
- `force()` is called for `READ_WRITE` before re-checking the file. The example uses single-byte-per-character ASCII data so offsets 0, 1 and size 5 are easy to verify.

**Environment note:** memory mapping depends on the operating system, filesystem, and access permissions. The temporary file is registered for deletion on JVM exit because on some operating systems (especially Windows), deleting a file with an unreleased mapping may be refused. There is no standard Java 17 command guaranteeing "immediate unmap" for every `MappedByteBuffer`.

## 8. Limitations and State of MappedByteBuffer

### 8.1. Buffer indices are not absolute file offsets

~~~java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY, 1_024, 128);

byte first = mapped.get(0); // Byte at file offset 1024.
byte last = mapped.get(127); // Byte at file offset 1151.
~~~

This is an illustrative code snippet with `channel` opened for read access and a file of at least 1152 bytes. For any offset `start`, `mapped.get(i)` corresponds to the byte at file offset `start + i`. Thus `mapped.get(1_024)` in the snippet above is out of bounds, even though offset 1024 exists in the underlying file.

### 8.2. ByteBuffer state still applies

A new mapping has `position=0`, `limit=capacity=size`. Relative `get()` advances position; absolute `get(index)` leaves position unchanged. `flip()`, `rewind()`, `slice()`, and `duplicate()` control views and positions just like other `ByteBuffer`s.

In particular, **`clear()` does not erase bytes in the file or the mapped region**. It only resets position and limit; on a `READ_WRITE` mapping, explicit `put` operations are required to change contents.

### 8.3. load(), isLoaded(), and force() do not serve the same role

| API | Goal | Limitations to remember |
| --- | --- | --- |
| `mapped.load()` | Attempts to load the mapping's pages into physical memory. | Best-effort; can trigger page faults and I/O; does not guarantee pages stay resident afterward. |
| `mapped.isLoaded()` | Queries whether the mapped region appears to be resident. | Only a hint; `false` does not prove data isn't in RAM. |
| `mapped.force()` | Pushes changes from a `READ_WRITE` mapping to storage per contract. | No effect on `READ_ONLY`/`PRIVATE`; guarantee applies to files on local devices. |

Do not call `load()` and assume data has been "flushed to disk": `load` helps bring data **from the file into RAM**; `force` handles writing changes **from the mapping to storage**.

### 8.4. Closing FileChannel does not immediately destroy the mapping

After `FileChannel` is closed, the mapped region can remain alive and usable until `MappedByteBuffer` is garbage collected. This differs from I/O objects where closing means immediately releasing all underlying resources.

Practical consequences:

- The file may be difficult to delete, rename, or truncate while the mapping persists, depending on the OS.
- Do not hold large numbers of unnecessary mappings for long periods.
- Do not build logic relying on predicting GC timing; `MappedByteBuffer` does not implement `AutoCloseable`.
- When precise memory region lifecycle control is required, evaluate alternative designs suitable for your runtime, rather than assuming a public unmap API equivalent to `close()` in Java 17.

## 9. Risks When the File Changes Concurrently or Is Truncated

A mapped file can be modified, resized, or truncated by another process. According to the Java 17 Javadoc, many mapping details depend on the operating system:

- When the underlying file changes, whether and when the buffer's **contents** reflect those changes is not uniformly guaranteed.
- If the file is truncated so that part of the mapping is no longer backed by file data, accessing that region may become unavailable.
- `MappedByteBuffer` may throw an exception when hitting an inaccessible region; do not assume all operating systems report the error identically.
- `READ_ONLY` does not imply immutable data, nor is `PRIVATE` automatically a durable/consistent snapshot against external edits.

If the application needs a consistent read/write protocol, control file ownership, use locks/data versioning, or choose a storage mechanism with transactions as needed. `FileLock` can help coordinate between processes when the filesystem and participating processes honor locks, though it is not an absolute guarantee across all platforms and does not eliminate all synchronization issues.

**Do not map a region past EOF and assume you will always read 0 bytes or that the file will expand properly.** Behavior when a mapped region does not lie entirely within the file is not consistently specified by the Java 17 Javadoc. For `READ_ONLY`, check the current size; for `READ_WRITE`, if you want to extend the file, establish the file length deliberately before mapping.

## 10. Which Mode Should You Choose for Each Need?

| Need | Suitable mode | Reason |
| --- | --- | --- |
| Reading a large binary file, looking up indices, or scanning data without modifying | `READ_ONLY` | View disallows writes, reducing risk of accidental mutation. |
| Modifying an index table or fixed region and saving results to the file | `READ_WRITE` | Changes from the mapping propagate to the file; `force()` can be called when durability is required. |
| Creating a temporary variant to test an algorithm on existing data | `PRIVATE` | Allows editing a private view without writing those changes back to the underlying file. |
| Wanting an immutable snapshot immune to all external modifications | None guarantees this alone | Must add a copy and/or dedicated consistency mechanism. |
| Wanting true commit/rollback transactions | None provides this alone | Needs a transaction layer or appropriate storage protocol. |
| Small file, single-pass read/write | Usually `Files.readAllBytes`/`write` or `FileChannel.read/write` | Mapping setup overhead may offer no benefit. |

Not every large file should necessarily be memory-mapped. Sequential single-pass reading of an entire file can use streams/channels with a sufficiently large buffer and easier resource control. Memory mapping is useful for random access or repeated operations over file regions, but should be benchmarked against the workload.

## 11. Common Mistakes

### Mistake 1: thinking PRIVATE is like READ_ONLY

**Wrong:** "PRIVATE doesn't modify the file, so this buffer must be non-writable."

**Right:** A PRIVATE buffer **is writable**, though private edits do not propagate to the file. Only READ_ONLY throws `ReadOnlyBufferException` on `put`.

### Mistake 2: thinking PRIVATE is like READ_WRITE with force disabled

**Wrong:** "Calling `privateView.force()` or closing the channel will commit the data."

**Right:** PRIVATE has copy-on-write semantics; `force()` does not write PRIVATE changes to the file. To save the private version, copy/serialize the data to another destination.

### Mistake 3: opening FileChannel read-only and then mapping PRIVATE

**Wrong:** "PRIVATE doesn't write the file, so opening `READ` is enough."

**Right:** Java 17 requires both `READ` and `WRITE` to map `PRIVATE`, just like `READ_WRITE`. Only `READ_ONLY` requires just `READ`.

### Mistake 4: calling FileChannel.force() to flush bytes modified via mapping

**Risk:** `FileChannel.force` is not guaranteed to write changes made by `MappedByteBuffer.put`. When you need to synchronize bytes edited through a READ_WRITE mapping, call `mapped.force()` and handle errors per contract.

### Mistake 5: assuming data read from a mapping is a snapshot

**Risk:** Another process can modify or truncate the file. Observed data and valid accessible regions are platform-dependent. Use proper ownership/versioning/locking or copy the data when a consistent snapshot is needed.

### Mistake 6: treating `clear()` as deleting data

**Wrong:** `mapped.clear()` only resets `position/limit` state. It does not change the file or zero out mapped bytes. Writing zeros requires explicit `put` calls and write permissions.

### Mistake 7: ignoring byte order and charset

Memory mapping provides **bytes**, without automatically knowing whether the file stores numbers in big-endian/little-endian or text in UTF-8/UTF-16. When calling `getInt()` or `getLong()`, set the right `ByteOrder`. When reading text, use `CharsetDecoder` or decode byte slices with an explicit charset; do not assume every single byte is one character.

### Mistake 8: mapping a huge file all at once

Each Java 17 `MappedByteBuffer` has an `int`-measured capacity. If a file is larger than `Integer.MAX_VALUE` bytes, map it in **byte-range windows** of suitable size. Each window has its own offset/length, handling record boundaries if data spans two windows. Also account for mapping overhead and how long mapped regions stay alive.

### Mistake 9: deleting/renaming the file immediately upon closing the channel

`close()` on the channel **does not** guarantee the mmap region is invalidated immediately. On some operating systems, delete/rename operations may fail while the mapping still exists. Design lifecycle, file cleanup, and mapping reuse around real-world constraints.

## 12. Practice Exercises

1. Create an 8-byte file containing `ABCDEFGH`. Map `READ_ONLY` at offset 2, size 4. What byte does `get(0)` return? **`C`**, because buffer index 0 corresponds to offset 2 in the file.
2. Call `put(0, 'X')` on READ_ONLY. What happens? **`ReadOnlyBufferException`**; no modification is made by this write attempt.
3. On the `HELLO` file, map PRIVATE and change the first byte to `P`. What does the buffer see and what does the file have? **The buffer sees `PELLO`; the file remains `HELLO`**, assuming no other actor edits the file.
4. Map READ_WRITE and change the second byte `E` to `A`. What is the file result? **`HALLO`** once changes propagate to the file; call `force()` when contract-level synchronization is needed.
5. Can a PRIVATE map be opened on a channel with only `READ`? **Not under the Java 17 API**; both `READ` and `WRITE` are required.
6. Does `MappedByteBuffer.force()` on PRIVATE write to the file? **No**; private changes are not propagated.
7. Does `MappedByteBuffer.load()` replace `force()`? **No**; `load` tries to bring pages into RAM, whereas `force` synchronizes `READ_WRITE` mapping changes to storage.
8. A file is truncated by another process while the application is using a mapping. Can you safely guarantee reading the mapping? **No**; the region may become inaccessible, with OS-dependent behavior.
9. After closing the channel, are you guaranteed to be able to delete the mapped file immediately? **No**; the mapping has its own lifecycle until the buffer is reclaimed by GC.
10. You need to edit a dataset with "commit" and "rollback" across multiple processes. Which MapMode fully satisfies this? **None provides transactions on its own**; a dedicated synchronization/storage layer must be designed.

## 13. Java 17 API References

- [FileChannel.map and MapMode — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): mapping contract, channel open permissions, mapped regions, and OS-dependent behavior.
- [FileChannel.MapMode — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html): the three standard modes READ_ONLY, READ_WRITE, PRIVATE.
- [MappedByteBuffer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): `force()`, `load()`, `isLoaded()`, and mapping lifecycle.

**Key takeaway:** `READ_ONLY` = read, forbid writes via buffer; `READ_WRITE` = edit buffer and propagate to file; `PRIVATE` = read/write on **private copy-on-write changes**, without propagating to the file. When using mmap, also understand `force()`, `FileChannel` permissions, mapping range limits, and a mapping lifecycle that does not end immediately when the channel is closed.
