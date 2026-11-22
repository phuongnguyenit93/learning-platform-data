# Read/Write Permissions, Lifetime, Data Flushing, and OS-Imposed Limits When Working with Buffers and Files

## 1. The Problem: Mapping a File into Memory Does Not Turn It into a Normal Java Array

Java has many ways to manipulate file bytes: `Files.readAllBytes`, `InputStream`/`OutputStream`, `FileChannel.read`/`write`, `ByteBuffer`, and **memory-mapped files**. In the Java Foreign Function & Memory API (FFM), a file mapping can be represented by a `MemorySegment`. The big difference: when mapping a file, **the JVM and the operating system coordinate to manage the address space, memory pages, access permissions, and pushing changes back to the storage device**.

Therefore, there are at least four questions that must be answered before using a mapped memory region:

1. **Read/write permissions:** how is the file opened (`READ`/`WRITE`), and is the mapped region created with `READ_ONLY`, `READ_WRITE`, or `PRIVATE`? Can it be read? Can it be written? Do changes go into the original file?
2. **Lifetime:** is the mapping tied to an `Arena` or a `MappedByteBuffer`? Does closing the `FileChannel` invalidate the mapping? When must it be unmapped to release resources?
3. **Flush/durability:** does a `set`/`put` operation into mapped memory guarantee that bytes are safe on disk? When is `MemorySegment.force()`, `MappedByteBuffer.force()`, or `FileChannel.force(...)` needed?
4. **OS limits:** how can the page cache, address space, file size changes, filesystem/network, OS permissions, full disk, file locks, and multiple processes writing concurrently affect it?

These questions are **independent**: a memory region may still be alive and writable, yet changes are not durable; a memory region may still be alive according to the `Arena`, yet the file has been truncated by another process; `force()` may return without creating an atomic data transaction.

**Versions in this article:** FFM `FileChannel.map(MapMode, long, long, Arena)` returning `MemorySegment` was added in **JDK 22**. Java snippets using `java.lang.foreign.` require **JDK 22+** (finalized FFM per JEP 454). The traditional `MappedByteBuffer` and `FileChannel.force` parts can be used on **Java 17+**. Do not copy `MemorySegment` examples into Java 17 without changing the API.

## 2. Data Model: File Bytes, Mapped View, and Page Cache

For example, a 16-byte file is mapped into a `MemorySegment`:

```text
Java Application                  OS / File System
┌────────────────────────┐
│ FileChannel            │
│  .map(READ_WRITE,      │
│       0, 16, arena)    │
│         │              │
│         ▼              │
│  MemorySegment         │         Virtual memory mapping
│  [byte 0 ... byte 15] ├────────► [memory pages/page cache]
│       │                │                    │
│       ├── get/set      │                    │ dirty pages
│       └── force() ─────┼────────────────────┤ flush request
└────────────────────────┘                    ▼
                                         File contents
                                       on storage device
```

`FileChannel.map` differs from `Files.readAllBytes` in that it does not require creating a `byte[]` copy containing the entire file in the Java heap. The operating system establishes a **virtual memory mapping** linking the process's address space to the file's contents; the operating system can load memory pages on access and evict pages according to cache policy.

It is necessary to distinguish:

- **Mapped view:** the address and bounds that Java uses to read/write.
- **Resident pages:** pages currently in physical memory, which may change over time.
- **Dirty pages:** modified pages waiting to be synchronized back to storage per OS mechanisms.
- **Persistent storage:** the data copy on the filesystem/device; may have its own cache/metadata/failure characteristics.
- **File descriptor/channel:** the Java/OS handle used to open, map, and coordinate I/O. Closing it does not mean every mapped view has been destroyed.

**Do not assume** that “reading from a memory map never causes I/O”. A page fault can trigger reading pages from storage. Also do not assume “writing a byte in a mapped view means the disk write is complete”: the operating system usually delays writeback.

## 3. Two Permission Layers: Open Options and Map Mode

### 3.1. Opening FileChannel with Appropriate Permissions

`FileChannel.open(path, options...)` determines whether the Java channel is allowed to read/write. For example:

```java
FileChannel readOnlyChannel = FileChannel.open(
        path, StandardOpenOption.READ);

FileChannel readWriteChannel = FileChannel.open(
        path, StandardOpenOption.READ,
        StandardOpenOption.WRITE);
```

This is a **fragment**, requiring the imports `FileChannel`, `Path`, and `StandardOpenOption` along with the variable `path`. The open permissions must also match actual **filesystem/ACL permissions**: declaring `WRITE` does not bypass OS permissions.

For standard `FileChannel.map`:

| Map mode | Minimum channel per API | Is the mapped region writable? | Are writes propagated to the original file? |
| --- | --- | --- | --- |
| `FileChannel.MapMode.READ_ONLY` | Opened **READ** | **No** | No writes |
| `FileChannel.MapMode.READ_WRITE` | Opened **READ + WRITE** | **Yes** | Modifications are propagated to the file; `force()` may be needed to ensure writeback |
| `FileChannel.MapMode.PRIVATE` | Opened **READ + WRITE** | **Yes** (copy-on-write) | **Does not** propagate private changes to the original file |

**Common point of confusion:** `PRIVATE` still requires the channel to be opened for both READ and WRITE per the Java FileChannel contract, even though writes to a private mapping are **not** written directly to the original file.

If you open a channel only with `READ` and then call `map(READ_WRITE, ...)` or `map(PRIVATE, ...)`, expect `NonWritableChannelException`. Opening a channel without read permission and mapping `READ_ONLY` can cause `NonReadableChannelException`.

These are **permission errors at the Java channel layer**, distinct from `AccessDeniedException` or `IOException` when the OS does not allow opening the file at the filesystem layer.

### 3.2. Segment Permissions After Mapping

In JDK 22+:

```java
MemorySegment readOnly = channel.map(
        FileChannel.MapMode.READ_ONLY, 0L, bytes, arena);

System.out.println(readOnly.isReadOnly()); // true
```

This is a **fragment**, `channel` must be opened for READ, `bytes` is a valid length, and `arena` is alive. Writing to this segment via `set` will be blocked; per the `MemorySegment` API, a read-only write causes `IllegalArgumentException`.

If using NIO `MappedByteBuffer`:

```java
MappedByteBuffer buffer = channel.map(
        FileChannel.MapMode.READ_ONLY, 0L, bytesAsInt);

buffer.put(0, (byte) 1); // ReadOnlyBufferException
```

This is a **fragment**, `bytesAsInt` must be within `int` bounds for the buffer, and the channel has READ permission. The access permission semantics are the same, but **the exception types of buffer and segment are not necessarily identical**.

### 3.3. A Read-Only View Does Not Change Permissions of Other Views

`MemorySegment.asReadOnly()` creates a **read-only view** of the segment; it does **not** modify file permissions on the OS and does **not** turn other aliases of the same backing bytes into read-only.

```java
MemorySegment writable = /* mapped READ_WRITE */;
MemorySegment roView = writable.asReadOnly();

System.out.println(roView.isReadOnly()); // true
System.out.println(writable.isReadOnly()); // false
```

This is a fragment illustrating semantics, not verbatim compilable code since the creation of `writable` is not provided. If another thread/process still has a writable mapping to the file, Java holding `roView` **does not prevent** the other side from modifying data.

## 4. READ_ONLY, READ_WRITE, and PRIVATE: Choosing the Right Purpose

### 4.1. READ_ONLY: Reading and Inspecting File Contents

Suitable when the application only parses files, looks up indexes, or reads metadata/data tables without needing modifications. Commonly used:

```java
try (FileChannel ch = FileChannel.open(path,
        StandardOpenOption.READ);
     Arena arena = Arena.ofConfined()) {

    long length = ch.size();
    MemorySegment mapped = ch.map(
            FileChannel.MapMode.READ_ONLY,
            0L, length, arena);

    // ... Only get/copy data, do not call set ...
}
```

This is a **fragment inside a method that throws IOException**; `path` is available. If the file is empty, a size-0 mapping is not useful for reading; the application needs to handle the `length == 0` case explicitly.

A read-only mapping does not mean the file is **immutable**: another party can modify bytes, truncate, or replace the file in ways whose observation timing depends on the OS. If processing untrusted or concurrently modified files, appropriate snapshot/version/lock mechanisms must be designed additionally.

### 4.2. READ_WRITE: Modifying a File Through Memory

Suitable for indexes, state files, custom databases, or binary data processing that requires in-place updates.

```java
MemorySegment mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        0L, fileLength, arena);

mapped.set(ValueLayout.JAVA_BYTE, 0L, (byte) 42);
mapped.force();
```

This is a fragment; `channel` is opened READ+WRITE, the file is long enough, `arena` is valid. `force()` **pushes modifications of the mapped segment to the storage device per the API contract on local storage**. It does not turn multiple field writes into an atomic transaction or coordinate independent processes.

If the application needs crash consistency for multiple fields, use a journal/WAL, checksum, copy-on-write file format, or a separate transaction protocol instead of relying solely on `force()`.

### 4.3. PRIVATE: Copy-on-Write, Without Writing to the Original File

`MapMode.PRIVATE` creates a **copy-on-write** mapping. When the application modifies the mapped region, the OS may create page copies of the modified bytes for this view. Those changes:

- Can be read back in the program's own private view.
- Are **not** propagated to the original file.
- Are not a commit mechanism; `force()` on a private mapping may have **no effect** per Javadoc.
- Do not replace an immutable/transactional snapshot of the entire file when the original file is concurrently modified by another party; synchronization/visibility details are determined by the OS.

```java
MemorySegment privateView = channel.map(
        FileChannel.MapMode.PRIVATE, 0L, size, arena);

privateView.set(ValueLayout.JAVA_BYTE, 4L, (byte) 99);

// Modifying privateView != writing value 99 into the original file.
```

This is a fragment. On Windows/Linux/macOS, how the OS allocates/copies pages differs; correct code must rely on the contract of **not propagating private writes** rather than guessing how many pages have been copied.

### 4.4. When Should Memory Mapping Not Be Used?

For very small files read only once, `Files.readAllBytes` is simpler. For continuous data streams, network streams, or append-only logging with explicit control requirements, `FileChannel.read/write` or buffered I/O may be easier to manage.

Memory mapping is usually suitable for **random access**, repeated reads, or sharing byte storage between the operating system and the application, but it is not free: mapping lifetime, file changes, and OS constraints must be managed.

## 5. Complete JDK 22+ Example: Permissions, Arena Lifetime, force, and PRIVATE

The example creates **a temporary file of exactly 16 bytes** and maps it three times within the same `Arena`:

1. `READ_WRITE` to write bytes.
2. `READ_ONLY` to inspect values and prove that writing is not possible.
3. `PRIVATE` to change a byte via copy-on-write and confirm **the original file is unchanged**.

So that the output does not depend on CPU endianness, `int` is stored using `ValueLayout.JAVA_INT_UNALIGNED.withOrder(ByteOrder.BIG_ENDIAN)`.

**File `MappedRightsDemo.java`**:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;

public final class MappedRightsDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("mapped-rights-", ".bin");

        try {
            // Specify the exact file length before mapping.
            Files.write(file, new byte[16]);

            var intBE = ValueLayout.JAVA_INT_UNALIGNED
                    .withOrder(ByteOrder.BIG_ENDIAN);

            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE);
                 Arena arena = Arena.ofConfined()) {

                MemorySegment readWrite = channel.map(
                        FileChannel.MapMode.READ_WRITE,
                        0L, 16L, arena);

                System.out.println(
                        "mapped: " + readWrite.isMapped());
                System.out.println(
                        "rw readOnly: " + readWrite.isReadOnly());

                readWrite.set(intBE, 0L, 0x11223344);
                readWrite.set(ValueLayout.JAVA_BYTE, 4L, (byte) 7);

                // Force modifications on the READ_WRITE mapping
                // to local storage per the force() contract.
                readWrite.force();

                MemorySegment readOnly = channel.map(
                        FileChannel.MapMode.READ_ONLY,
                        0L, 16L, arena);

                System.out.println(
                        "readOnly: " + readOnly.isReadOnly());
                System.out.printf(Locale.ROOT,
                        "readOnly int: %08X%n",
                        readOnly.get(intBE, 0L));

                try {
                    readOnly.set(
                            ValueLayout.JAVA_BYTE, 5L, (byte) 9);
                } catch (IllegalArgumentException ex) {
                    System.out.println(
                            "read-only write: rejected");
                }

                MemorySegment privateView = channel.map(
                        FileChannel.MapMode.PRIVATE,
                        0L, 16L, arena);

                privateView.set(
                        ValueLayout.JAVA_BYTE, 4L, (byte) 99);

                System.out.println(
                        "private byte4: " +
                        Byte.toUnsignedInt(privateView.get(
                                ValueLayout.JAVA_BYTE, 4L)));

                System.out.println(
                        "rw byte4: " +
                        Byte.toUnsignedInt(readWrite.get(
                                ValueLayout.JAVA_BYTE, 4L)));
            }
            // Arena closes -> mappings are unmapped;
            // Channel also closes -> OS file handle is released.

            byte[] persisted = Files.readAllBytes(file);
            System.out.println(
                    "file byte4: " +
                    Byte.toUnsignedInt(persisted[4]));
        } finally {
            // Delete the file after all demo mappings have closed.
            Files.deleteIfExists(file);
        }
    }
}
```

**Compile/run with JDK 22+:**

```bash
javac MappedRightsDemo.java
java MappedRightsDemo
```

`--enable-preview` is not needed for the official FFM API since JDK 22. The example does not call restricted FFM methods such as `Linker.downcallHandle` or `MemorySegment.reinterpret`, so `--enable-native-access` does not need to be granted just to use `FileChannel.map(..., Arena)`.

**Expected stdout when the filesystem supports mapping and the command runs successfully:**

```text
mapped: true
rw readOnly: false
readOnly: true
readOnly int: 11223344
read-only write: rejected
private byte4: 99
rw byte4: 7
file byte4: 7
```

### 5.1. Result Explanation

- `Files.write(file, new byte[16])` makes the file exactly 16 bytes long; the code **does not rely** on the behavior of mapping beyond the end of the file.
- `READ_WRITE` creates a writable mapped segment; `isMapped() == true` and `isReadOnly() == false`.
- `set(intBE, 0, 0x11223344)` writes the first four bytes in **big-endian**. `force()` is called to request writing modifications to the storage device.
- `READ_ONLY` maps the same region and reads `11223344`, but `set` on this view is rejected. The error is caught as `IllegalArgumentException` per the `MemorySegment` contract.
- `PRIVATE` stores the value `99` at byte 4 in a **copy-on-write view**, while the original READ_WRITE mapping still sees `7`.
- After closing the arena/channel, `Files.readAllBytes` reads from the file and sees byte 4 is `7`, not `99`: private changes are not propagated.
- All mapped segment objects in the example are used only **inside** try-with-resources; do not store a `MemorySegment` in a static field to read after the arena closes.
- `finally` cleans up the temp file after the mappings have been closed. On a system that does not support this type of mapping, or lacks OS permissions/resources, the program will throw an exception instead of printing all success lines.

### 5.2. Why Use an UNALIGNED Layout in the Example?

A mapped region has page alignment handled by the OS, but **a file format does not necessarily guarantee every field is at a 4/8-byte aligned offset**. `JAVA_INT_UNALIGNED` allows illustrating a 4-byte field per a packed-file contract, while `withOrder(BIG_ENDIAN)` defines the byte ordering.

**Endianness, alignment, access permissions, and lifetime are different concerns**. Replacing `READ_ONLY` with `READ_WRITE` does not fix byte order; replacing `JAVA_INT` with `JAVA_INT_UNALIGNED` does not change write permissions.

## 6. Lifecycle: Arena, FileChannel, and MappedByteBuffer Differ

### 6.1. With FFM MemorySegment: Arena Controls Unmapping

In JDK 22:

```java
try (FileChannel ch = FileChannel.open(
        path, StandardOpenOption.READ);
     Arena arena = Arena.ofConfined()) {

    MemorySegment mapped = ch.map(
            FileChannel.MapMode.READ_ONLY,
            0L, ch.size(), arena);

    // mapped remains valid within the arena scope.
}
// Arena closes -> mapped region is unmapped.
```

This is a fragment with the `path` variable and corresponding imports. `FileChannel.map(MapMode, offset, size, Arena)` ties the **mapping lifetime** to `arena`, not to the Java `FileChannel` variable.

Therefore:

- **Closing FileChannel after mapping** does not automatically invalidate the created mapped segment. The mapped region has its own lifecycle.
- **Closing a closeable Arena** (for example `ofConfined` or `ofShared`) causes mappings belonging to that scope to be unmapped.
- **Accessing a segment after `arena.close()` violates lifetime** and will be detected by `MemorySegment` scope checks; typically `IllegalStateException`.
- If using a confined arena, only the owning thread accesses the segment; other threads may encounter `WrongThreadException`.
- When an application needs multiple threads, `Arena.ofShared()` allows cross-thread access per scope rules, but still requires synchronizing **shared data** and proper shutdown order.

**Do not equate unmap with force.** Close the arena to stop using the mapping; call `force()` to request durability. If explicit durability is needed, **force before closing** and handle I/O errors. Do not treat closing a scope as an automatic transactional commit.

### 6.2. With MappedByteBuffer: No Direct close() for the Mapping

The traditional method:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY,
        0L, (int) fileSize);
```

returns `MappedByteBuffer`. Per JDK documentation, the mapping and buffer typically remain valid **until the buffer is collected by GC**. There is no standard `mapped.close()` to proactively unmap like FFM's arena mapping.

Because of this:

- Closing `FileChannel` does not automatically unmap `MappedByteBuffer`.
- Keeping buffers/slices/duplicates alive can continue to hold the mapping.
- Deleting/renaming the file while a mapping still exists can be blocked on some OSes (especially Windows file-handle/mapping semantics).
- Do not use `System.gc()` as a promise of deterministic unmapping.
- If proactive and precise mapping release is needed in modern Java, consider `MemorySegment` with a closeable `Arena`.

**Note:** `ByteBuffer.clear()` does not release memory. It only resets the buffer's `position/limit/mark` pointers. `MappedByteBuffer.force()` also does not release the mapping.

### 6.3. asByteBuffer of a Mapped MemorySegment Still Follows Arena Scope

`mapped.asByteBuffer()` creates a `ByteBuffer` view to use NIO APIs that accept `ByteBuffer`, but **the view's lifecycle is bound to the original segment**.

```java
// Fragment within a live arena scope:
MemorySegment mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0L, size, arena);

ByteBuffer view = mapped.asByteBuffer();
view.put(0, (byte) 42);
mapped.force();
```

Do not keep `view` and use it after the arena closes. For a confined segment, other threads are also naturally not allowed to access the view. `ByteBuffer` has an `int` capacity so it **cannot** create a view covering a segment with `byteSize() > Integer.MAX_VALUE`; in that case use `MemorySegment` and slices/long byte offsets instead of forcing the whole into a single `ByteBuffer`.

### 6.4. Proper Shutdown Flow in Asynchronous Applications

Suppose an executor is reading a mapped segment. Do not close the arena immediately after submitting tasks:

```text
map region
  │
  ├── start/submit readers
  ├── stop accepting new work
  ├── wait for in-flight readers/writers
  ├── force() if there are durable writes
  ├── close arena (unmap)
  └── close file resources / release locks
```

With `Arena.ofShared`, a shutdown protocol is needed to ensure no thread is still calling `get/set/load/force` when the arena is closed. With `Arena.ofConfined`, other workers must not use the segment directly; data copies/snapshots can be passed or ownership redesigned.

A mapped segment still referenced by Java code **must not be used** after the arena closes: Java object reachability does not extend the scope.

## 7. Flush, force, and Durability: Distinguishing Three Levels

### 7.1. Writing Bytes to Mapped Memory Does Not Mean the Disk Is Durable

`segment.set(...)` modifies bytes of the mapped view. On `READ_WRITE`, the OS may mark pages as dirty and write them to the file later. This differs from calling `force()`:

```java
mapped.set(ValueLayout.JAVA_BYTE, 7L, (byte) 1);

// Flush per the mapped segment contract:
mapped.force();
```

**`MemorySegment.force()` only applies to mapped segments**; calling it on a normal segment from `Arena.allocate` may cause `UnsupportedOperationException`.

Per JDK 22 Javadoc:
- If the file descriptor points to **local storage**, when `force()` returns successfully, changes to the mapped region are guaranteed to have been written to the device within the API scope.
- For **non-local storage** (for example a network filesystem), the Javadoc **does not make the same guarantee**.
- For `READ_ONLY` or `PRIVATE`, `force()` may have **no effect**. PRIVATE changes do not become file changes just by flushing.
- I/O errors in `MemorySegment.force()` are reported as `UncheckedIOException`. Do not swallow the error and claim data was saved.

**Limitation:** even if flushing succeeds on local storage, `force()` does not provide transaction isolation, atomicity across multiple fields, or journal/recovery logic. It does not replace a database transaction or write-ahead log.

### 7.2. FileChannel.force(boolean) Is for Updates via Channel

`FileChannel.force(metaData)` ensures file updates made through the channel are written to the device per the Java contract (on a local device). Parameters:

- `force(false)`: requests synchronizing **file content**.
- `force(true)`: requests synchronizing both **content and file metadata** within the API scope.

For example:

```java
// Fragment: channel opened WRITE and just wrote bytes.
channel.force(false);
```

When modifying through a **mapped segment**, use **`mapped.force()`** for the mapping's modifications; do not assume `channel.force(false)` will flush all dirty pages of a mapping that was created through the channel and has its own lifecycle. When the application also modifies metadata/file structure, add a `channel.force(true)` policy if appropriate.

**Do not confuse `FileChannel.force(true)` with an operation guaranteeing atomic rename and durability of the parent directory entry.** Guarantees regarding directory fsync, atomic move, filesystem journal, and power-fail lie outside a universal FFM transaction promise.

### 7.3. OutputStream.flush() / BufferedOutputStream.flush() Is Not fsync

With `BufferedOutputStream`, `flush()` mainly pushes bytes held in the **Java buffer** to the downstream stream. It does not necessarily mean data has reached persistent storage. Similarly, C `fflush(FILE*)` mainly flushes the C stdio buffer to the OS; it is not identical to OS `fsync`/`FlushFileBuffers`.

Table:

| Call | Primary meaning |
| --- | --- |
| `BufferedOutputStream.flush()` | Pushes Java user-space buffered bytes to the downstream stream |
| `FileChannel.force(false)` | Pushes channel file content updates to storage per contract |
| `FileChannel.force(true)` | Requests synchronizing content and metadata |
| `MappedByteBuffer.force()` | Flushes dirty mapped buffer pages |
| `MemorySegment.force()` | Flushes dirty mapped segment pages |
| `MemorySegment.load()` | Attempts to load pages into RAM; does **not** write to disk |
| `MemorySegment.unload()` | Attempts to evict pages from RAM; is **not** “unmap” or “flush” |
| `Arena.close()` | Ends scope and unmaps arena resources; is not a transaction commit |

### 7.4. A Flush Operation Does Not Guarantee Every Application Sees the Same Snapshot

When process A writes multiple fields to a mapping, process B may observe partial changes mid-way if there is no synchronization protocol. `force()` aims at **durability**, not creating **atomic visibility** or mutual exclusion between readers/writers.

If a file needs a consistent structure after a crash:

1. Define a format with header/version/checksum.
2. Write the new payload to a temporary region.
3. `force` the payload.
4. Commit with a marker/record per a protocol with recovery.
5. `force` the commit state.
6. On restart, read and verify checksum/version, complete or roll back incomplete parts.

The exact order depends on the application; this example is a **mental framework**, not a database protocol proven safe on every filesystem.

## 8. FileChannel.force with Java 17+: Standalone Example Without Mapping

To clearly see the difference between regular buffers and mapped memory, the second example writes four ASCII characters via `ByteBuffer` and `FileChannel.write`, calls `FileChannel.force(true)`, and then reads it back. It runs on **JDK 17+**, without needing `java.lang.foreign`.

**File `ChannelForceDemo.java`:**

```java
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class ChannelForceDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("channel-force-", ".txt");
        try {
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.READ)) {

                ByteBuffer buffer = ByteBuffer.wrap(
                        "DATA".getBytes(StandardCharsets.US_ASCII));

                // FileChannel.write may write fewer bytes than remaining.
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }

                // Synchronize file data + metadata per contract.
                channel.force(true);
            }

            System.out.println("file: " +
                    Files.readString(file, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

**Compile/run:**

```bash
javac ChannelForceDemo.java
java ChannelForceDemo
```

**Expected stdout:**

```text
file: DATA
```

The program does not create a `MemorySegment` or `MappedByteBuffer`; `FileChannel.force(true)` applies to file updates via the channel. Using the `while (buffer.hasRemaining())` loop is important because `FileChannel.write(ByteBuffer)` may not write all bytes in a single call.

Do not use `Files.readString` after write as “proof the disk wrote durably”: it only proves bytes are read back through the current filesystem. `force(true)` carries its own writeback contract.

## 9. Traditional MappedByteBuffer on Java 17+

Before and alongside FFM, Java NIO has:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        0L, fileLength);
```

This is a fragment. `MappedByteBuffer` is a direct `ByteBuffer` with `int` `position/limit/capacity`, fitting many existing NIO APIs. It has:

- `mapped.get(index)` / `mapped.put(index, byte)`: read/write byte.
- `mapped.order(ByteOrder...)`: determines how multi-byte values are interpreted.
- `mapped.force()` and `mapped.force(index, length)`: requests writeback.
- `mapped.load()` / `mapped.isLoaded()`: OS residency hints.
- No public `close()` for the mapping, so unmapping is not explicitly controlled like an arena.

**A comparison snippet:**

```java
// Fragment: channel opened READ+WRITE; file contains at least 16 bytes.
MappedByteBuffer buffer = channel.map(
        FileChannel.MapMode.READ_WRITE, 0L, 16L);

buffer.order(ByteOrder.BIG_ENDIAN);
buffer.putInt(0, 0x01020304);
buffer.force();

int same = buffer.getInt(0); // 0x01020304
```

Do not treat `buffer.clear()` as closing the mapping. `clear()` only sets `position = 0`, `limit = capacity`, and clears the mark (it does not erase bytes).

### 9.1. Size Limits: int for ByteBuffer, long for MemorySegment

NIO buffer capacity uses `int`; `FileChannel.map(MapMode, position, size)` returns `MappedByteBuffer` with `size <= Integer.MAX_VALUE`. Mapping a 4 GiB file into **one** `MappedByteBuffer` is invalid per the API.

Meanwhile, `FileChannel.map(MapMode, long offset, long size, Arena)` returns `MemorySegment` with a `long` size. In principle the API can describe regions over 2 GiB, but **the OS and virtual address space** still determine whether a large mapping succeeds.

Do not therefore call:

```java
// WRONG if mapped.byteSize() > Integer.MAX_VALUE:
ByteBuffer whole = mapped.asByteBuffer();
```

Because `ByteBuffer` has an `int` limit, `asByteBuffer()` on an oversized segment will throw `UnsupportedOperationException` per the API. Instead use `MemorySegment.get`/`set` with `long` offsets or create **small slices** with valid bounds, then create a `ByteBuffer` for each slice.

### 9.2. File Address and Segment Address Are Two Offsets

`channel.map(mode, fileOffset, size, arena)` has:

- `fileOffset`: **byte offset in the file**, not a Java element index.
- `size`: number of bytes mapped.
- `mapped.get(layout, segmentOffset)`: byte offset **from the start of the mapped segment**, not the absolute offset in the file.

For example:

```text
Map fileOffset = 4096, size = 1024
mapped.get(JAVA_BYTE, 0)    -> byte 4096 in the file
mapped.get(JAVA_BYTE, 15)   -> byte 4111 in the file
mapped.asSlice(16, 8)       -> file bytes 4112..4119
```

To read a field at fileOffset 4120, the mapped segment's byte offset is `4120 - 4096 = 24`. Mixing coordinate systems is a common bug when mapping files by window.

## 10. File Size, Truncate, and the Biggest OS-Imposed Risks

### 10.1. Do Not Map Beyond File Size and Rely on the Result

Per JDK 22 Javadoc, the behavior of mapping a region **not completely contained within the current file** is **unspecified**. On some platforms, mapping beyond EOF may result in extending the file or an error; portable code **should not depend** on that.

Before mapping:

- Read `channel.size()` and compare the region.
- Check `offset >= 0`, `size >= 0`, and no overflow on `offset + size`.
- For read-only, map only actually existing bytes.
- For a new file to be written, **create/set the file size explicitly first**; for example `Files.write(path, new byte[n])` for small files or a proper write/allocation mechanism for large files. `FileChannel.truncate(newSize)` **does not automatically extend the file** if `newSize` is greater than the current size.

**A dangerous case:** code sets the channel position at the end and thinks it has extended the file:

```java
channel.position(4096L); // Only changes position, DOES NOT increase size.
```

To grow a file, a **write operation** or an API guaranteed to create a file of the requested length is needed. If using sparse files, check OS policy and actual storage allocation. Do not create a 4 GiB region using a `new byte[4 GiB]` in Java.

### 10.2. File Truncated After Mapping: Can Cause Unspecified Errors

A mapping can be valid and read successfully, yet another process calls `truncate` to shrink the file. JDK docs warn that **all or part of the mapped region may become inaccessible at any time**.

Consequences:

- `mapped.byteSize()` may still report the initial bounds.
- Reading bytes within Java bounds is not necessarily safe if backing pages are lost due to file changes.
- Javadoc only promises an **unspecified exception** may be thrown at the time of access or later; do **not** assume always `IndexOutOfBoundsException`.
- On real operating systems, mmap errors can be severe. Do not design by trying to catch a specific Java exception to recover from concurrent truncate.

**Recommendation:** file mapping must have a contract managing **versioning and size changes**. If a process writes a new file, consider creating a new file, flushing, and then replacing per a stable protocol instead of directly truncating a file that has mapped readers.

### 10.3. Same File, Multiple Processes: Visibility Is Not Fully Controlled by Java

FileChannel Javadoc warns that file views within the same Java program have certain consistency guarantees, but between independent programs they can be affected by **filesystem caches and network protocols**. Concurrent file modifications may be observed at different times; do not assume snapshot isolation.

For a file mapping shared by multiple processes:

- Define who writes and who reads.
- Use version counters/checksums or record states if data must be consistent.
- Use `FileLock` when process coordination is needed, but check OS support and **advisory/mandatory** behavior.
- Do not expect `force()` to pause readers or create a lock.
- Do not use `MapMode.PRIVATE` as a broadcast channel between processes; private writes are not propagated to the file.

## 11. OS Limits: Pages, Virtual Address Space, Handles, and Disk Capacity

### 11.1. Mapping Does Not Mean Immediately Occupying All RAM

The OS can map a large file into **virtual address space** and load pages on demand. Mapping a 10 GiB file **does not mean** Java has allocated 10 GiB of heap or 10 GiB of RAM the moment `map` returns.

However, that does not mean “unlimited mapping”:

- Mapping requires a large enough contiguous **virtual address space** range, and the OS must have page tables/resources.
- 32-bit processes generally have a more restricted address space than 64-bit; virtual fragmentation can also cause `map` to fail.
- Many simultaneously open mappings consume kernel resources, file descriptors, or handle counts.
- Disk quota, filesystem capacity, and I/O state can cause flush/access to fail after the initial `map` succeeded.
- Mapping on a network filesystem has different consistency/durability than local storage.
- The OS may limit mapped address regions, page size alignment, file offsets, or mode support.
- On Windows, a currently mapped file can affect rename/delete/truncate; timely release/unmap is a practical requirement.

**Conclusion:** the API's `long` limit is not a promise that the operating system can allocate any size.

### 11.2. Page Size and Offset Alignment Handled by the Implementation

OS virtual memory mapping typically operates in pages (for example 4 KiB in many environments). Java `FileChannel.map` takes `offset` in bytes, and the implementation must handle internal OS alignment requirements where possible.

Do **not** manually add a page-size offset pad to every `get` when using a Java mapped segment; Java offsets are relative to the start of the requested region. However, when managing raw POSIX `mmap` via C/FFM downcalls yourself, you must separately obey `mmap` requirements for page-aligned offsets. Do not apply conclusions from the low-level C API to the semantics of the high-level `FileChannel.map`.

### 11.3. load, isLoaded, unload Are Only Hints About Residency

An FFM mapped segment provides:

```java
mapped.load();
boolean likelyResident = mapped.isLoaded();
mapped.unload();
```

This is a fragment; `mapped` is a live mapped segment accessible on the current thread.

- `load()` attempts to bring pages into physical memory (prefetch); **best effort**.
- `isLoaded()` returns a **hint** result. `true` only means the data is very likely resident at the time of checking, not that pages are locked in RAM.
- `unload()` attempts to make pages no longer resident; it is **not unmap**, does not close the arena, and is not a procedure to flush durable writes.
- After `unload()`, reading again may cause page faults and the OS reloads pages back.
- Do not use `isLoaded() == true` as a guarantee of zero I/O latency for all subsequent reads.

If optimizing page faults, measure on real workloads/OSes; do not habitually call `load()` every time without benchmarking.

### 11.4. Differences Across Filesystem, SSD/HDD, Remote, and Memory-Backed Files

The specific level of durability depends on the storage layer. For local files, JDK `force()` has a clear contract in the API; remote filesystems do not have the same guarantee. For RAM disks, network shares, encrypted filesystems, cloud-synced directories, or container overlays, actual behavior may differ and requires appropriate testing/operational procedures.

A single `force()` returning successfully also does not mean the application has built a protocol protecting against **logic corruption** when multiple writers write to the same file, or against every type of hardware/controller failure. Durability, consistency, and atomicity are separate properties.

## 12. OS Permissions, FileLock, and Multi-Threaded Synchronization

### 12.1. Java Write Permission Cannot Override Filesystem Permissions

A file with a read-only ACL or located on a read-only mounted filesystem can cause `FileChannel.open(... WRITE)` to fail, typically manifesting as `AccessDeniedException`/`IOException` depending on provider and OS.

Conversely, a file with OS write permissions but a `READ_ONLY` mapping still does not allow Java to write through the view. **The two check layers are not mutually exclusive**.

When debugging:

1. Verify path, owner, and ACL.
2. Check mount state and filesystem provider.
3. Check `FileChannel.open` options.
4. Check `MapMode`.
5. Check `mapped.isReadOnly()`.
6. Check arena alive, thread accessibility, offset/bounds.
7. Check OS error during `map`/`force`.

Do not react to `AccessDeniedException` by switching the map to `PRIVATE` and thinking you have permission to modify the original file; `PRIVATE` does not commit.

### 12.2. FileLock Helps Coordinate but Is Not a RAM Mutex

`FileChannel.lock` and `tryLock` create file locks using OS mechanisms. File locks have limitations:

- May be advisory or mandatory depending on platform.
- Shared locks may not be fully supported; the OS may upgrade them to exclusive.
- Locks apply at the VM/file level per the Java contract, **not for coordinating multiple threads within the same JVM**.
- A lock on a file region does not automatically turn `get/set` on mapped pages into an atomic transaction.
- If an external process ignores advisory locks, it can still modify/truncate the file.

Use Java `synchronized`/`Lock` or a concurrent protocol for threads in the same JVM; use OS inter-process file locks/protocols when needed.

### 12.3. Arena.ofShared Allows Multiple Threads but Does Not Automatically Make Data Thread-Safe

`Arena.ofShared()` allows a segment to be accessed from multiple threads, whereas `Arena.ofConfined()` restricts to the owning thread. **Being allowed to access** does not mean **free of data races**.

Two threads simultaneously calling `set(JAVA_INT, offset, ...)` on a mapped segment without an appropriate protocol can see each other's results according to memory ordering constraints; do not infer from the API name that every multi-byte update has atomicity or cross-process synchronization.

If atomic operations are needed, use appropriate access modes/VarHandle per layout and ABI limits, or separate locks/protocols. Alignment and mapped memory support must be checked, especially when interacting with native processes.

## 13. Common Errors Table

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `NonWritableChannelException` when mapping `READ_WRITE` | Channel opened only `READ` | Open `READ + WRITE` and ensure OS permissions |
| `NonWritableChannelException` when mapping `PRIVATE` | Forgot that PRIVATE also needs a READ+WRITE channel | Open with right modes; understand PRIVATE does not commit |
| `NonReadableChannelException` | Map requires READ but channel lacks it | Open channel with READ |
| `AccessDeniedException` / `IOException` on open | ACL, read-only mount, file share lock, OS provider | Check permissions and filesystem state |
| `IllegalArgumentException` on `MemorySegment.set` | Read-only segment or incompatible layout alignment | Check `isReadOnly()`, mode, alignment |
| `ReadOnlyBufferException` on `MappedByteBuffer.put` | Mapped READ_ONLY | Switch workflow to READ_WRITE when truly permitted |
| `IllegalStateException` after closing arena | Mapped segment out of scope | Do not use after close; manage owner clearly |
| `WrongThreadException` | Confined segment used from another thread | Use only on owner thread or shared arena with synchronization |
| `UnsupportedOperationException` on `force/load` | Segment is not mapped, OS/provider unsupported | Check `isMapped()` and supported features |
| `UncheckedIOException` on `mapped.force()` | Storage write failed | Log, mark not durable, do not swallow exception |
| `mapped.asByteBuffer()` fails | Segment larger than `Integer.MAX_VALUE` or incompatible | Access with MemorySegment/long offsets or split into slices |
| Mapping succeeds then read fails after truncate | Backing file changed/shortened | Prevent concurrent truncate; use versioning/snapshot |
| Flush succeeds yet original file unchanged | Using `PRIVATE` | Use `READ_WRITE` if write-through is needed |
| Closed FileChannel yet file is still held | Mapping is still alive | Close Arena (FFM) or wait for GC (MappedByteBuffer) |
| Large file map size fails | Limits on virtual memory, descriptors, disk, OS | Windowed mapping, reduce number of mappings, handle IOException/OOME properly |
| `isLoaded()==true` yet reads remain slow | Residency is a hint, OS can page | Measure page faults/I/O; do not treat as a guarantee |
| Corrupted data without throwing an exception | Wrong byte order, offset/stride, concurrent writes | Compare golden bytes, schema, and thread/process protocol |

### 13.1. Do Not Confuse FileChannel.close with Releasing a MemorySegment

If you want to “ensure unmapped”, the crucial part in FFM is **closing the arena** and ensuring no references/tasks are still using it. Channel close handles the file descriptor, not the mapping scope. With `MappedByteBuffer`, there is no standard close API, so file locks/renames may last longer than you expect.

### 13.2. Do Not Catch a Single Exception Type for All I/O Errors

Errors can come from:
- `IOException` on `FileChannel.open/map`/file writes.
- `UncheckedIOException` on `MemorySegment.force` or `MappedByteBuffer.force`.
- `IllegalArgumentException` when map region parameters are invalid or writing to a read-only segment.
- `IllegalStateException` / `WrongThreadException` due to scope/thread.
- `UnsupportedOperationException` if the provider does not support mapping or trying to convert a large segment into a ByteBuffer.
- **Unspecified exception** when the mapped region becomes inaccessible due to backing file truncation.

Production applications should classify errors by **stage** and their consequences, not blindly “retry every exception” if the mapped state is unsafe.

## 14. Safe File Storage Architecture: Do Not Use force as a Catch-All Commit

### 14.1. When Data Is Structured

Suppose a file consists of:

```text
[header version][recordCount][records...][checksum]
```

If `recordCount` is written first, then records are written and a crash occurs in the middle, after restart a reader may believe the file contains N records while the data is incomplete. Calling `force()` at the end does not save a crash **occurring between writes**.

A better design direction:

- Use a new/temporary file of sufficient size.
- Write all new content.
- Validate counts, bounds, checksum.
- Flush mapped content with `force()`.
- Mark the file complete using a versioned/generation schema if needed.
- Use replace/rename leveraging **atomic move** capabilities supported by the filesystem.
- Additionally handle metadata/directory durability per OS requirements (do not assume all systems behave identically).
- After restart, parse/verify schema and have recovery rules.

For databases/transactional stores, engines that already solve WAL, crash recovery, locking, and durable commits are generally preferred. Memory mapping is an **I/O primitive**, not a transaction manager.

### 14.2. Multiple Mapped Views and Concurrent Modifications

If the same file has multiple writable views, a write by one view does not require `force()` for other views to **potentially** see it during execution, but visibility/ordering between processes cannot be assumed as an “atomic commit”. `force()` targets storage persistence, not message passing.

When needing multiple readers + one writer:
- Immutable segments can be used and generation/version published.
- Avoid changing file size while readers are still mapped.
- Use a checksum/seqlock-like protocol if lock-free consistent reading is a verified design requirement.
- Define ownership and shutdown; do not let a worker still use a mapped segment when the arena closes.

### 14.3. Byte Order Is Part of the File Format

Mapped bytes do not carry endianness information themselves. For a file with a 32-bit big-endian field:

```java
var i32BE = ValueLayout.JAVA_INT_UNALIGNED
        .withOrder(ByteOrder.BIG_ENDIAN);

int fileValue = mapped.get(i32BE, byteOffset);
```

This is a fragment. Do not read using the default `JAVA_INT` (native order) if the file specification fixes big-endian; and do not confuse `byteOffset` with `getAtIndex` element index. Correct read/write permissions and flushing **cannot fix a misinterpreted schema**.

## 15. Production Deployment Checklist

- [ ] File mapping truly fits the workload; measured against buffered I/O and `FileChannel.read/write`.
- [ ] Using the right API version: `java.lang.foreign` and `FileChannel.map(...,Arena)` require JDK 22+; NIO mapped buffers support older JDKs.
- [ ] Correct channel open options: `READ_ONLY` requires READ, `READ_WRITE`/`PRIVATE` require READ+WRITE; OS permissions are valid.
- [ ] Understand the difference between shared-write mapping (`READ_WRITE`) and copy-on-write (`PRIVATE`).
- [ ] Check `fileOffset`/`size`/`channel.size()`, overflow, and bounds before mapping.
- [ ] Do not depend on mapping beyond EOF; new files are created with sufficient size in a portable way.
- [ ] Manage `Arena` with clear ownership, close after tasks complete; do not use mapped segments after close.
- [ ] For shared segments, use synchronization for data races; do not rely on `FileLock` like a Java thread lock.
- [ ] Call `mapped.force()` for durable writes per contract (local storage); handle `UncheckedIOException`.
- [ ] If writing via channel, consider `channel.force(false/true)` depending on content/metadata needs.
- [ ] Do not treat `load/isLoaded/unload` as commit, prefetch guarantee, or unmap.
- [ ] Have a policy protecting against concurrent truncate/replace for mapped files.
- [ ] Check file locks, rename/delete, disk quota, virtual address space, and memory pressure per OS.
- [ ] Do not try to obtain `asByteBuffer` from a segment over 2 GiB; split into windows/slices.
- [ ] Do not assume network filesystems have the same force guarantee as local storage.
- [ ] Have crash/restart tests, checksum/version/recovery for critical data structures.

## 16. Self-Check Questions

**Question 1.** Is `FileChannel.open(path, READ)` followed by `map(READ_WRITE, 0, size, arena)` valid?  
**Answer:** No; a READ_WRITE mapping requires the channel to be opened for both READ and WRITE. Otherwise, `NonWritableChannelException` typically occurs.

**Question 2.** A PRIVATE mapping allows `set` and calling `force()`. Will the original file be updated?  
**Answer:** No. PRIVATE is copy-on-write; private changes do not propagate to the original file. `force()` on a private mapping may have no effect.

**Question 3.** With what error type is `readOnlySegment.set(...)` rejected in the MemorySegment API?  
**Answer:** `IllegalArgumentException` when attempting to write to a read-only segment. With `MappedByteBuffer.put`, the error is `ReadOnlyBufferException`.

**Question 4.** After creating a `MemorySegment` via `FileChannel.map(..., arena)`, does closing the channel while keeping the arena open immediately expire the segment?  
**Answer:** No. Mapping lifetime is managed by the arena. Closing the channel does not automatically unmap the created segment.

**Question 5.** Is `Arena.close()` equivalent to `mapped.force()` and committing a multi-field transaction?  
**Answer:** No. Close unmaps/invalidates the scope; force targets durable writeback; neither automatically creates a multi-field transaction/atomic commit.

**Question 6.** Does `mapped.isLoaded() == true` guarantee all subsequent reads will have no page faults?  
**Answer:** No. It is a hint about residency at the time of checking; the OS may page out immediately afterward.

**Question 7.** Why is classic `FileChannel.map(mode, offset, size)` difficult for handling a file over 2 GiB with a single buffer?  
**Answer:** `MappedByteBuffer` has an `int` capacity and map size is limited by `Integer.MAX_VALUE`. `FileChannel.map(..., Arena)` returns a `MemorySegment` using a long size, though still subject to OS limits.

**Question 8.** If a `MemorySegment` maps 4 GiB, is calling `mapped.asByteBuffer()` to leverage NIO APIs valid?  
**Answer:** Not for a single ByteBuffer covering the whole region, because `ByteBuffer` capacity is an int. Use long offsets or small slices.

**Question 9.** Another process truncates the file after mapping. Segment bounds are still valid; is it safe to read?  
**Answer:** Cannot be guaranteed. Backing pages may be inaccessible; Javadoc states an unspecified exception may occur on access or later. Concurrent truncate must be prevented/coordinated.

**Question 10.** Are `MappedByteBuffer.force`, `FileChannel.force`, and `BufferedOutputStream.flush` the same?  
**Answer:** No. These APIs flush at different layers: mapped pages, file-channel updates, and Java buffered bytes. They have different contracts regarding durability.

**Question 11.** Does `MemorySegment.load()` guarantee data is written durably to the file?  
**Answer:** No. `load()` attempts to bring pages from the file into RAM; it does not flush dirty pages to storage.

**Question 12.** A file resides on a network filesystem. Does `mapped.force()` returning normally provide the same guarantee as a local disk?  
**Answer:** No. Javadoc only makes specific guarantees for local storage; for non-local it does not make the same guarantee.

**Question 13.** Does `FileChannel.truncate(4096)` always grow a file from 128 bytes to 4096 bytes?  
**Answer:** No. `truncate(size)` does not modify the file if `size` is greater than or equal to the current size. To extend it, an appropriate write/length-setting method must be used.

**Question 14.** Two threads concurrently write fields to an `Arena.ofShared` mapped segment; is it thread-safe thanks to the shared arena?  
**Answer:** Not automatically. A shared arena only changes thread access conditions; memory ordering/locks or a consistent protocol are still needed.

**Question 15.** Is calling `force()` after writing index, payload, and checksum enough to turn three writes into an atomic commit during a mid-way power loss?  
**Answer:** No. A schema with recovery/WAL or a commit protocol designed and tested on the target storage is required.

## 17. Summary

- **Permissions:** `READ_ONLY` reads, `READ_WRITE` shares writes and can flush, `PRIVATE` is copy-on-write without modifying the original file; both open options and OS permissions take effect.
- **Lifetime:** FFM mapped `MemorySegment` belongs to the `Arena`'s scope; closing the arena unmaps; closing `FileChannel` alone is not enough. Legacy `MappedByteBuffer` has no explicit mapping close and persists until GC.
- **Flush:** `MemorySegment.force()`/`MappedByteBuffer.force()` are for mapped writes; `FileChannel.force` is for channel writes; `OutputStream.flush` is for Java buffering. Each API has its own guarantee limits.
- **OS:** page faults, page cache, file size changes, truncate, file locks, virtual address space, quotas, and network filesystems can affect correctness/liveness/durability.
- **Size limits:** `MappedByteBuffer` uses `int` capacity; `MemorySegment` uses `long` size but cannot exceed actual OS capabilities. `asByteBuffer()` cannot accept an entire segment exceeding `Integer.MAX_VALUE`.
- **Design:** check bounds/ownership, synchronize writers, avoid concurrent truncate, distinguish durability and atomicity, and have checksum/version/recovery if the file holds critical data.

### Official Documentation

- [Oracle Java SE 22 — FileChannel](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.html): map modes, open permissions, `map(..., Arena)`, mapped memory lifetime, truncate, `force(boolean)`, and OS consistency.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `isMapped`, `isReadOnly`, `force`, `load`, `unload`, scope/thread rules, and `asByteBuffer`.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared arenas, lifecycle, and explicit close.
- [Oracle Java SE 22 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/MappedByteBuffer.html): force/load/isLoaded, GC-tied lifetime, and effects of truncation.
- [Oracle Java SE 22 — FileChannel.MapMode](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html): READ_ONLY, READ_WRITE, and PRIVATE copy-on-write.
- [Oracle Java SE 22 — ByteBuffer](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/ByteBuffer.html): int capacity, position/limit, read-only exceptions, and byte order.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): official FFM API since JDK 22 and scope management mechanism for native/mapped memory.
