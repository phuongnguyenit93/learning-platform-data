# Memory-Mapped Files and MappedByteBuffer in Java NIO

## 1. Overview: Mapping a File into Memory

A **memory-mapped file** is a technique that asks the operating system to map a byte region of a file into a process's memory address space. The application can read or modify data in that region via memory access operations, instead of repeatedly calling `read`/`write` to transfer byte blocks between the file and a buffer.

In Java NIO, the core API consists of:

- `FileChannel.map(FileChannel.MapMode mode, long position, long size)`: maps a **region** of the file.
- `MappedByteBuffer`: a type of direct `ByteBuffer` representing the mapped file region; use `get`, `put`, `getInt`, `slice`, `duplicate`, etc. just like a regular `ByteBuffer`.
- `MappedByteBuffer.force()`: requests that changes made to a read/write mapping be written to the storage device.
- `load()` and `isLoaded()`: hint/approximate check APIs regarding whether the mapping data is resident in physical memory.

Memory mapping is often useful when you need repeated access to sections of a relatively large binary file or convenient random access by index. **There is no rule that memory mapping is always faster than `FileChannel.read/write`**: creating mappings, page faults, memory pressure, and data flushing mechanisms all have their own costs.

### Visualizing the Difference

```text
Regular I/O:
File on disk -- FileChannel.read(buffer) --> ByteBuffer --> program
Program -- FileChannel.write(buffer) --> file on disk

Memory mapping:
File on disk <-- page/cache management by the OS -->
Mapped memory address region <-- MappedByteBuffer.get/put --> program
```

The diagram illustrates only the **programming model**. Data is not automatically loaded entirely into RAM when calling `map`; the operating system typically loads pages on demand, and actual data transfer depends on the system.

## 2. Creating a Mapping with FileChannel.map

Syntax:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY,
        startOffset,
        regionLength);
```

The snippet above is illustrative, assuming `channel` is already open with appropriate permissions. Parameters:

| Parameter | Meaning |
|---|---|
| `mode` | Specifies permissions and how changes are reflected: `READ_ONLY`, `READ_WRITE`, or `PRIVATE` |
| `position` / `startOffset` | Byte offset **in the file** where the mapped region begins; type `long`, non-negative |
| `size` / `regionLength` | Number of bytes to map; type `long`, but no greater than `Integer.MAX_VALUE` |
| Return value | `MappedByteBuffer` with `position() == 0`, `limit() == capacity() == size`, and an undefined mark |

For example, a file with ten bytes `ABCDEFGHIJ`, mapped starting from offset 3 with length 4:

```text
File:             A B C D E F G H I J
File offset:      0 1 2 3 4 5 6 7 8 9
                        |-------|
Mapping:                D E F G
Mapping index:          0 1 2 3

mapped.get(0) corresponds to the file byte at offset 3.
mapped.get(3) corresponds to the file byte at offset 6.
```

The general formula for an unaltered mapping view:

```text
fileOffset = mappingStartOffset + mappedBufferIndex
```

With `map(mode, 3L, 4L)`, the capacity of the mapped buffer is **4**, not the size of the entire file. Valid indices for reading with `get(index)` are 0 through 3, as long as `limit` remains 4.

A common point of confusion: `FileChannel.map` **does not change the current position of the FileChannel**. This differs from `channel.read(buffer)` or `channel.write(buffer)`, which operate relative to the current position.

## 3. The Three Mapping Modes: READ_ONLY, READ_WRITE, PRIVATE

| Mode | Readable? | Can `put` via mapping? | Do mapping changes write back to file? | FileChannel permissions |
|---|---|---|---|---|
| `FileChannel.MapMode.READ_ONLY` | Yes | No; throws `ReadOnlyBufferException` | No mapping changes to write | Open for `READ` |
| `FileChannel.MapMode.READ_WRITE` | Yes | Yes | Changes are propagated to the file; timing is unspecified if not synchronized | Open for **both `READ` and `WRITE`** |
| `FileChannel.MapMode.PRIVATE` | Yes | Yes | **Does not** write private changes back to the file; copy-on-write | Open for **both `READ` and `WRITE`** |

### READ_ONLY

`READ_ONLY` is the clear choice when a program only looks up or parses file contents. Calling a mutating method such as `put` or `compact` on a read-only mapping throws `ReadOnlyBufferException`. You can still adjust `position`, `limit`, and `mark` to traverse the data.

Do not interpret "read-only" as an immutable snapshot: if another program modifies the mapped file, the content read through the view may change, and how and when those changes become visible depends on the operating system.

### READ_WRITE

`READ_WRITE` allows modifying bytes via `put` and corresponding operations. The system synchronizes changes between the mapping and the file according to OS semantics; changes may reside in memory/cache before being written to the storage device. Call `mapped.force()` if the API contract requires **flushing mapping data to storage**, especially before checkpoints or data handoffs.

Do not equate "reading a byte back shows the new value" with "safe against power loss". Data durability is a matter of `force`, the filesystem, and the storage subsystem.

### PRIVATE (copy-on-write)

`PRIVATE` allows modifying content **in a private view**, without propagating those changes back to the underlying file; the system may create copies of modified pages (copy-on-write). This is useful when you need to transform mapped content for trial computations without intending to update the file.

Do not use `PRIVATE` as a substitute for a globally consistent snapshot: visibility of external modifications, especially under concurrency, is OS/provider-dependent and should not be relied upon implicitly. Calling `force()` on a `PRIVATE` mapping does not "commit" private changes back to the file.

## 4. OS-Level Mechanics: Page Faults and Page Cache

Virtual memory is typically managed in **pages**. When a byte in a mapping is accessed for the first time, the corresponding data might not yet be in RAM; the operating system resolves a page fault to bring the file page into memory. Pages may be evicted or reloaded according to memory management policies.

Several consequences follow:

1. **`map` does not mean loading the entire file region into RAM.** It establishes the mapping; data may only be loaded when accessed.
2. Repeated reads of hot regions can benefit from the OS page cache.
3. Dense random access into a file larger than physical memory can cause frequent page faults and degrade performance.
4. Writing with `READ_WRITE` modifies memory-mapped pages; normal flush timing is decided by the OS unless a synchronization API is called.
5. Java does not guarantee that accessing a mapped byte never involves physical I/O. Memory-like access can still trigger page faults.
6. Memory mapping incurs OS and address-space management overhead, so it is not automatically advantageous for very small operations or short files.

Memory mapping **does not eliminate disk I/O**: it delegates most page loading/flushing decisions to the OS. The right approach depends on file size, read/write patterns, access frequency, and the operating system.

## 5. Complete Java 17+ Example and Exact Output

The program below:

- Creates a file `mapped-demo.bin` containing six ASCII bytes `ABCDEF`.
- Opens a `FileChannel` with `READ` and `WRITE` permissions.
- Maps the region starting at offset 1, four bytes long, i.e., `BCDE`.
- Accesses bytes by **mapping-relative index** and modifies two positions.
- Verifies that changing `MappedByteBuffer.position()` does not alter `FileChannel.position()`.
- Calls `force()` to synchronize mapping changes, then closes the channel.
- Reads the file back from the filesystem to verify its contents.

Save as **`MemoryMappedDemo.java`**:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MemoryMappedDemo {
    public static void main(String[] args) throws IOException {
        Path file = Path.of("mapped-demo.bin");
        Files.writeString(file, "ABCDEF", StandardCharsets.US_ASCII);

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 1L, 4L);

            System.out.println("capacity=" + mapped.capacity());
            System.out.println("first=" + (char) mapped.get(0));
            System.out.println("channelPosition=" + channel.position());

            // mapped index 0 corresponds to file offset 1: B -> x
            mapped.put(0, (byte) 'x');

            // mapped index 2 corresponds to file offset 3: D -> y
            mapped.position(2);
            mapped.put((byte) 'y');

            System.out.println("mappedPosition=" + mapped.position());
            System.out.println("channelPosition=" + channel.position());

            mapped.force();
        }

        System.out.println("result=" +
                Files.readString(file, StandardCharsets.US_ASCII));
    }
}
```

Compile and run in the directory containing `MemoryMappedDemo.java`:

```bash
javac MemoryMappedDemo.java
java MemoryMappedDemo
```

**Stdout when I/O operations are permitted by the OS:**

```text
capacity=4
first=B
channelPosition=0
mappedPosition=3
channelPosition=0
result=AxCyEF
```

Explanation of each output line:

- The mapping `(offset=1, size=4)` represents `BCDE` and has `capacity=4`, with an initial private position of 0.
- `mapped.get(0)` reads the character `B` at file offset 1. This is an **absolute get**, so it does not increment `mapped.position()`.
- `channel.position()` remains 0 even after calling `map` and `mapped.get/put`.
- `mapped.put(0, 'x')` changes byte `B` to `x`. Then `mapped.position(2)` and `mapped.put('y')` write at mapping index 2, corresponding to file offset 3, changing `D` to `y`. The relative `put` advances position to 3.
- Reading the whole file back yields `AxCyEF`, because only the bytes at file offsets 1 and 3 were modified.
- `force()` requests synchronization of the `READ_WRITE` mapping changes to the storage device according to the API rules.

The program intentionally leaves `mapped-demo.bin` on disk so you can inspect it with a hex editor or read it after the JVM exits. You can delete that file after the program finishes. Doing so avoids depending on when the OS releases the memory mapping, especially when deleting a file that is still mapped on Windows.

## 6. Reading/Writing Primitives, Byte Order, and Indices

`MappedByteBuffer` inherits most of the `ByteBuffer` API. Core operations:

| Call | Behavior |
|---|---|
| `get()` | Reads 1 byte at the mapped position, increments position by 1 |
| `get(int index)` | Reads 1 byte at mapping index, leaves position unchanged |
| `put(byte value)` | Writes 1 byte at the mapped position, increments position by 1 |
| `put(int index, byte value)` | Writes at mapping index, leaves position unchanged |
| `getInt()` / `putInt(int)` | Reads/writes 4 bytes using the current byte order |
| `getLong()` / `putLong(long)` | Reads/writes 8 bytes using the current byte order |
| `position()`, `limit()`, `capacity()` | Manages the state of the mapped buffer itself |
| `slice()` / `duplicate()` | View sharing bytes in the mapped region, with independent position/limit/mark |

Offsets in `MappedByteBuffer` are **offsets from the start of the mapped region**, not automatically whole-file offsets.

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 1024L, 16L);

mapped.putInt(4, 2026); // Writes at file offset 1024 + 4 = 1028.
```

This is an **illustrative** snippet, assuming the file is long enough and the channel has appropriate permissions.

`ByteBuffer` defaults to **BIG_ENDIAN**. If your file format is little-endian:

```java
mapped.order(java.nio.ByteOrder.LITTLE_ENDIAN);
mapped.putInt(4, 2026);
int same = mapped.getInt(4);
```

Keep byte order consistent across all code reading/writing the same format. When creating a new `slice/duplicate` from a `ByteBuffer/MappedByteBuffer`, Java 17 initializes the new view's byte order to `BIG_ENDIAN`; if using multi-byte primitives, set `order(...)` explicitly on the view.

**Do not confuse file byte offsets with UTF-8 character positions.** A UTF-8 character can span multiple bytes, so `mapped.get(10)` is the 11th byte of the mapping, not the 11th character of text.

## 7. force(), load(), and isLoaded(): Three Different Purposes

### `force()`: pushing changes to the storage device

```java
mapped.force();
mapped.force(100, 200); // Requests synchronization of mapping range [100, 300).
```

This is an illustrative snippet; the mapping must have sufficient capacity for the specified range.

- `force()` applies to the entire mapped region; the `force(int index, int length)` overload targets a specific byte range.
- For a `READ_WRITE` mapping on a local storage device, the Java API specification states that when `force` returns successfully, changes within the requested range have been written to the device per the API contract.
- For filesystems/devices that are not local storage, the same guarantee does not apply.
- The OS may write additional data beyond the exact requested range in page/block units.
- For `READ_ONLY` or `PRIVATE`, `force` has no effect in writing private modifications back to the file.
- `force` may throw `UncheckedIOException` when a synchronization error occurs.

`force` **does not turn multiple changes into an atomic transaction**. If you need corruption-resistant updates mid-flight, you need a suitable format and update protocol (such as journaling, checksums, double-write, or a transactional mechanism), rather than merely adding a `force` call.

### `load()`: proactively requesting page loading

```java
mapped.load();
```

`load()` attempts to bring the mapping's pages into physical memory. This is best-effort, can trigger page faults/I/O, and consumes resources. Do not unconditionally call `load()` on every large file, as it can increase memory pressure and provides no indefinite residency guarantee.

### `isLoaded()`: approximate signal

```java
boolean likelyResident = mapped.isLoaded();
```

`true` only indicates that it is **highly likely** the entire region is resident in physical memory at the time of the check. `false` does not prove the data is definitely unloaded. The state can change immediately after the check. Therefore `isLoaded()` is an observational hint, not a prerequisite for calling `get()` safely.

| Method | Focus | Should NOT be interpreted as |
|---|---|---|
| `load()` | Tries to load data into physical memory | A guarantee that all pages stay in RAM |
| `isLoaded()` | Hint of resident status | Proof that no page faults will occur |
| `force()` | Synchronizes read/write mapping changes to storage | Creating a snapshot, lock, or atomic transaction |

## 8. Mapping Lifecycle and Closing FileChannel

An important difference from regular buffer-based I/O:

**A mapping does not become invalid merely because the `FileChannel` that created it is closed.** By API specification, the mapping and `MappedByteBuffer` remain valid until the buffer itself is garbage collected, provided the backing file region remains accessible.

Conceptual example:

```java
MappedByteBuffer mapped;
try (FileChannel channel = FileChannel.open(
        Path.of("data.bin"), StandardOpenOption.READ)) {
    mapped = channel.map(FileChannel.MapMode.READ_ONLY, 0, channel.size());
}
// Channel is closed; mapped can still be read if the file region remains valid.
```

This is only an illustrative snippet, since `data.bin` must exist and have an appropriate size. The JVM retaining the mapping does **not** prevent all risks if the file is deleted, truncated, or modified externally.

Consequences:

1. **Closing the channel does not immediately unmap**; the mapped region may still hold OS resources.
2. Do not rely on `System.gc()` as a deterministic unmapping mechanism.
3. On some operating systems, especially Windows, a currently mapped file can be difficult to delete or rename immediately.
4. Java 17 `MappedByteBuffer` does not provide a public `close()` method to proactively release the mapping like closing a stream or channel.
5. If a program creates many consecutive mappings, you must consider reference lifetimes, virtual address space usage, and resource limits.
6. If another party truncates the file after mapping, accessing the unbacked region can cause unspecified errors per the API; avoid letting that situation occur.

For requirements demanding very strict lifecycle control, consider alternative designs or newer APIs suited to the target JDK; do not rely on tricks calling internal/undocumented JDK APIs to force unmapping in portable Java 17 code.

## 9. Per-Mapping Limit and Handling Very Large Files

Although `FileChannel.map` accepts `long` for `position` and `size`, the result is a `ByteBuffer` using `int` indices and capacity. Thus each `map` call supports a maximum `size` of **`Integer.MAX_VALUE` bytes** (roughly 2 GiB minus 1 byte), which does not mean you cannot process **entire files larger than 2 GiB**.

The strategy for large files is **windowed/chunked mapping**:

```java
long fileSize = channel.size();
long offset = 0L;
int windowSize = 64 * 1024 * 1024; // 64 MiB, example.

while (offset < fileSize) {
    long size = Math.min((long) windowSize, fileSize - offset);
    MappedByteBuffer window = channel.map(
            FileChannel.MapMode.READ_ONLY, offset, size);

    // Parse the window within [0, window.limit()).
    // Read example: while (window.hasRemaining()) { byte b = window.get(); }

    offset += size;
}
```

The snippet above is illustrative; it requires a channel opened for `READ` and imports for `MappedByteBuffer` and `FileChannel`. In a real system:

- Do not retain all windows indefinitely if unnecessary; releasing mappings depends on buffer lifetime/GC.
- Watch out for **records spanning window boundaries**; carry over the remainder or align chunk boundaries with record boundaries.
- Do not assume `fileSize` is immutable if the file is modified by another party; choose appropriate coordination or snapshot mechanisms.
- `offset` uses `long`, while the index inside a window is `int`. Do not cast a very large file offset down to `int`.
- Mappings are subject to OS resource limits, not just Java heap limits.
- Choose the window size via real measurements; 64 MiB is just a design example.

Mapping multiple consecutive chunks allows processing files tens of GiB in size, though no single strategy is guaranteed optimal across all operating systems.

## 10. Mapping Range, File Size, and Access Safety

`map(mode, offset, length)` requires `offset >= 0`, `length >= 0`, and `length <= Integer.MAX_VALUE`. Java may throw `IllegalArgumentException` if these conditions are violated. Mapping a region not entirely within the file size at the time of the call has system/specification-dependent behavior; **prepare the file and ensure the mapping range is valid before mapping**.

Example range check for a file with a stable size:

```java
long fileSize = channel.size();
long offset = 1024L;
long length = 256L;

if (offset < 0 || length < 0 ||
        length > Integer.MAX_VALUE ||
        offset > fileSize ||
        length > fileSize - offset) {
    throw new IllegalArgumentException("Mapping range outside the file");
}

MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY, offset, length);
```

This snippet is not a standalone program; it uses the check `length > fileSize - offset` to avoid integer overflow when computing `offset + length`. For files concurrently modified by another process, pre-checking does not guarantee the file won't change right before or after `map`: manage concurrency with another mechanism.

**Do not truncate a file while an active mapping is still being accessed.** Under Java's contract, a mapped buffer may become inaccessible if the backing file is shrunk; accessing it can throw an unspecified exception either at access time or later. Do not rely on catching a specific exception for safe recovery.

## 11. MappedByteBuffer, Views, and Independent State

`MappedByteBuffer` inherits `ByteBuffer` semantics: `position`, `limit`, and `mark` are instance state; they are independent of `FileChannel.position()`.

- `mapped.get()`: reads a byte at the mapped position and advances the mapped position.
- `mapped.get(index)`: absolute read, leaving the mapped position unchanged.
- `mapped.put(index, value)`: modifies the byte at `index` in the mapping without changing the mapped position.
- `mapped.slice()`: sub-view over the remaining region; the slice's index starts at 0.
- `mapped.duplicate()`: view over the same backing storage, copying initial position/limit/mark with independent pointers thereafter.
- `mapped.asReadOnlyBuffer()`: read-only view of the same data; not an immutable snapshot.

In Java 17, the overrides `MappedByteBuffer.slice()` and `duplicate()` return `MappedByteBuffer`, so mapping features like `force`/`load` are also available on those views. Each view bounds a byte range and has its own cursors, while sharing the same underlying mapping/backing data.

Example:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0L, 16L);
mapped.position(4);
mapped.limit(8);

MappedByteBuffer part = mapped.slice();
// part.capacity() == 4, part.position() == 0.
// part.get(0) sees file offset 4.
```

This snippet is illustrative and requires a file of at least 16 bytes. `part` does not create an independent copy. When distributing views across multiple threads, establish a partitioning policy and synchronization; **separate positions do not make concurrent reads/writes to shared regions thread-safe**.

## 12. When Should You Use Memory Mapping?

### Worth considering

- Repeatedly reading different regions of a large binary file (e.g., binary indices, fixed-offset records).
- Accessing scattered offsets within a file region and wanting to work via `get(index)`.
- On-disk data layouts closely matching in-memory binary representations; requires explicit byte order/offset design.
- Data volume or access frequency is high enough that mapping creation overhead is offset by the benefits.
- The application can accommodate mapping lifecycle management and OS dependencies.

### Often better to use FileChannel.read/write or Files

- Small files, single-pass reads, or short operations; `Files.readAllBytes`, `Files.newBufferedReader`, or `FileChannel.read` may be simpler.
- Streaming/parsing sequential records without needing to hold a long-lived mapping.
- Needing tight cross-platform control over when files are closed, deleted, or renamed.
- Files frequently resized by other processes; mappings risk validity issues upon truncation.
- Needing clear semantics for I/O loops, memory/resource bounds, and write ordering.

**Choose based on benchmarks and your actual data model**, rather than assuming "memory mapping is zero-copy so it's always fast." Mapping still incurs page faults and disk I/O, as well as overhead if mappings are repeatedly created and discarded for small tasks.

## 13. Synchronization, Consistency, and Safety Limits

1. **Concurrent modifications:** If another actor writes to or truncates the same file, Java does not guarantee exactly when a mapped view observes the change. Do not rely on mappings as an inter-process synchronization mechanism.
2. **Multi-byte reads/writes are not automatically atomic:** Methods like `getInt/putInt` on a mapping do not replace atomics, locks, or a safe synchronization protocol.
3. **force is not a transaction:** Flushing pages does not ensure multiple records succeed together or roll back automatically.
4. **File locks:** `FileChannel.lock/tryLock` can coordinate cooperating parties that respect locks, but enforcement depends on the OS/filesystem. Control writers by application design.
5. **PRIVATE is not a global immutable snapshot:** copy-on-write protects the file from modifications made through the mapping, but does not establish snapshot isolation against concurrent external modifications.
6. **Handling untrusted input files:** Validate sizes, offsets, lengths, record layouts, and byte order, and prevent offset arithmetic overflow. Use `Math.addExact` or safe difference checks.
7. **Resources do not live entirely in the heap:** Mappings consume virtual address space and OS resources; low heap usage does not mean mappings are free.
8. **Data durability:** When durability is required, decide when to call `force`, handle exceptions, and plan recovery instead of assuming every `put` is immediately safe.
9. **File deletion capability:** Do not require immediate deletion or renaming while a mapping reference is still held, especially if the application must run on Windows.

## 14. Common Mistakes

| Mistake | Consequence | How to avoid |
|---|---|---|
| Thinking `map` reads the whole file into heap | Wrong resource and performance estimates | Understand OS mapping/page fault mechanics |
| Passing whole-file indices to `mapped.get(index)` | Reading wrong data or `IndexOutOfBoundsException` | Convert via `fileOffset - mapStartOffset` |
| Assuming `channel.position()` tracks `mapped.get/put` | Logic relies on the wrong cursor | Track file position and mapped position separately |
| Omitting `force` when durability is needed | Risk that changes haven't reached the device | Call `force` at proper checkpoints and handle errors |
| Using `PRIVATE` and expecting writes to reach the file | Changes are not committed to the file | Use `READ_WRITE` to persist edits to the file |
| Attempting `put` on `READ_ONLY` | `ReadOnlyBufferException` | Choose the mode matching your access needs |
| Mapping > `Integer.MAX_VALUE` in one buffer | Invalid arguments | Split into mapping windows |
| Assuming `close(channel)` unmaps immediately | File still holds resources / hard to delete | Design mapping lifecycle explicitly |
| Truncating a file while a mapping is still in use | Unspecified access failures | Coordinate size changes and backing file protection |
| Thinking `isLoaded() == true` guarantees no page faults | Incorrect runtime assumptions | Treat `isLoaded` as a hint |
| Mapping per tiny operation in a loop | Overhead and many lingering mappings | Reuse mappings sensibly or use regular I/O |
| Misunderstanding Java view byte order | Wrong multi-byte number reads/writes | Set `order(...)` explicitly |
| Treating a read-only mapping as a snapshot | Can see external modifications | Use an appropriate storage design if snapshots are needed |

## 15. Self-Check Questions

**Question 1.** A file has ten bytes `ABCDEFGHIJ`. You call `channel.map(READ_ONLY, 3, 4)`. Which byte does `mapped.get(0)` return, and what is the capacity?  
**Answer:** Byte `D`, capacity=4. Index 0 in the mapping corresponds to offset 3 in the file.

**Question 2.** After creating a mapping and running `mapped.position(2); mapped.get();`, does `channel.position()` change automatically?  
**Answer:** No. The mapped buffer and `FileChannel` maintain separate positions; mapping access is not a relative `FileChannel.read/write`.

**Question 3.** Can a `READ_ONLY` mapped view call `position(10)` within valid bounds? What about `put(...)`?  
**Answer:** It can validly change `position`/`limit`; byte-modifying operations like `put` throw `ReadOnlyBufferException`.

**Question 4.** Modifying a byte via a `READ_WRITE` mapping and reading it back shows the new value. Does that prove it has been safely written to disk against power loss?  
**Answer:** No. You must consider `force()` and the durability guarantees provided by the OS/filesystem/device.

**Question 5.** A `PRIVATE` mapping has a byte modified via `put`. Is that change written to the underlying file when `force()` is called?  
**Answer:** No. A private mapping uses copy-on-write; `force` does not commit private contents to the file.

**Question 6.** Can a 5 GiB file be processed using Java 17 `MappedByteBuffer`?  
**Answer:** You can map it in parts using multiple windows, each with size not exceeding `Integer.MAX_VALUE` and using `long` file offsets. You cannot map all 5 GiB into **one** `MappedByteBuffer`.

**Question 7.** Does closing `FileChannel` immediately release the mapping?  
**Answer:** No. Once created, the mapping is independent of the channel's lifecycle; per the Java 17 API it persists until the buffer is garbage collected, provided the backing region remains valid.

**Question 8.** Why is truncating a file while a thread is accessing a mapping dangerous?  
**Answer:** The mapped region can lose its valid backing; Java does not guarantee a specific exception type or failure timing. Resizing and access must be coordinated.

## 16. Key Takeaways

- **`FileChannel.map` turns a file region into a `MappedByteBuffer`**, accessing bytes like a direct `ByteBuffer` with indices relative to the mapping start.
- Three modes: **`READ_ONLY` for reading**, **`READ_WRITE` for updating the file**, **`PRIVATE` for private copy-on-write edits**.
- `MappedByteBuffer.position/limit` are independent of `FileChannel.position`; `map`/`get`/`put` do not advance `FileChannel.position`.
- **`force()` handles requests to synchronize modifications**, while `load/isLoaded` relate to memory residency and only provide best-effort/hints.
- Each mapping in Java 17 has a maximum size of **`Integer.MAX_VALUE`**; to handle larger files, map in windows.
- **Closing the channel does not immediately free the mapping**; pay attention to GC, file truncation, concurrency, portability, and OS resources.
- Choose memory mapping when access patterns and benchmarks prove it beneficial; regular I/O remains a great choice for many simpler tasks.

### References

- Oracle Java SE 17 — `FileChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Oracle Java SE 17 — `MappedByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html
- Oracle Java SE 17 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
