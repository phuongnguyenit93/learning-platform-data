# Closing FileChannel Does Not End the Mapped Region's Lifecycle

When using Java NIO to map a file's contents into memory, developers typically call `FileChannel.map(...)` to obtain a `MappedByteBuffer` and then close the `FileChannel` via `try-with-resources`. **The mapped region can continue to exist and remain accessible through the buffer after the channel is closed.** This is specified in `FileChannel.map`'s contract: once established, the mapping does not depend on the channel that created it; closing the channel does not invalidate the mapping.

This point is critical for resource lifecycles, the ability to delete or rename files, native memory usage, and ensuring edits made via the mapped region are written to the storage device. Closing the channel is right, but **closing a channel and ending a memory mapping are two different things**.

## 1. Distinguishing the Channel, Mapped Region, and Mapped Buffer

Identify three resource layers:

1. **`FileChannel`:** The I/O channel bound to a single file open operation. It provides `read`, `write`, `position`, `size`, `map`, `force`, and `close`. Once the channel is closed, operations on the channel itself are no longer valid.
2. **Memory-mapped region (memory mapping):** The association established by the OS/provider between a virtual address range and a segment of a file. The mapping has its own resource lifecycle. Data pages may be brought into RAM on demand; do not equate the entire mapping size with allocated physical RAM.
3. **`MappedByteBuffer`:** The Java object representing the mapped region and providing `get`, `put`, `position`, `limit`, `force`, and buffer operations. This is the Java handle for accessing the mapped region after `map` returns.

You can visualize it as:

```text
FileChannel (open)
       |
       | map(MapMode.READ_WRITE, offset, size)
       v
MappedByteBuffer -----> mapped address region -----> file data
       ^
       | continue using get/put/force
FileChannel (closed)
```

The arrows illustrate resource relationships, not the exact object-ownership graph of every JVM.

**Closing the channel releases the channel's resources; it does not automatically reclaim the mapped region.** While valid, `MappedByteBuffer` can still read and, if permitted by the mode, write data without keeping `FileChannel` open. Conversely, you cannot call `channel.force(...)` on a closed channel simply because a buffer created from that channel still exists.

## 2. Creating a Mapped Region with `FileChannel.map`

Common signature:

```java
MappedByteBuffer map(FileChannel.MapMode mode,
                     long position,
                     long size) throws IOException
```

This is an illustrative signature, not a standalone program.

- `mode` specifies the mapping mode: `READ_ONLY`, `READ_WRITE`, or `PRIVATE`.
- `position` is the **byte offset in the file** where the mapping starts; not `ByteBuffer.position()`.
- `size` is the number of bytes mapped. For the overload returning `MappedByteBuffer`, buffer capacity is an `int`, so the mapped region for a single buffer must fit within `int` capacity limits; split into multiple regions when handling very large files.
- On Java 17, the mapping must be established via an open channel with appropriate permissions. Once `map` succeeds, the channel can be closed independently.

Modes:

| `MapMode` | Access manner | Effect when writing via buffer |
| --- | --- | --- |
| `READ_ONLY` | Reads mapped data | `put` is rejected with `ReadOnlyBufferException` |
| `READ_WRITE` | Reads and modifies file data through the mapping | Changes may be reflected to the file; use `MappedByteBuffer.force()` when needed to request pushing updates per the API contract |
| `PRIVATE` | Copy-on-write mapping | Private changes are not written back to the file per private mapping semantics |

`READ_WRITE` requires a channel opened with read and write permissions. `READ_ONLY` requires read permission. Do not infer the mapping mode from whether the channel happens to allow `write()`; always choose the right mode and `StandardOpenOption`s before calling `map`.

A successful `map` creates the mapping; this operation **does not** mean all bytes have been copied onto the Java heap or are already resident in RAM. The OS may page them in on demand, and the JVM may consume native resources outside the Java heap.

## 3. Runnable Java 17+ Program: Channel Closed, Buffer Still Usable

This program creates a temporary file with five ASCII bytes, maps it with `READ_WRITE`, closes `FileChannel` upon exiting the `try` block, and **only then reads, modifies, and forces via `MappedByteBuffer`**. It avoids printing random temp filenames to stdout so the output remains deterministic.

Create **`MappedLifetimeDemo.java`**:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class MappedLifetimeDemo {
    private MappedLifetimeDemo() {}

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mapped-lifetime-", ".txt");
        // Request temporary file cleanup when the JVM exits; this is best-effort.
        file.toFile().deleteOnExit();

        Files.writeString(file, "ABCDE", StandardCharsets.US_ASCII);
        MappedByteBuffer mapped;

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {
            mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 5);
            System.out.println("inside: channelOpen=" + channel.isOpen());
        } // Only the channel is closed here.

        // The mapped region can still be read, even though the channel is closed.
        System.out.println("after close: first=" + (char) mapped.get(0));

        // Write through the mapping without reopening FileChannel to write.
        mapped.put(1, (byte) 'Z');
        System.out.println("mapped second=" + (char) mapped.get(1));

        // Request synchronizing mapping changes with the storage device.
        mapped.force();
        System.out.println("file after force="
                + Files.readString(file, StandardCharsets.US_ASCII));
    }
}
```

Compile and run:

```bash
javac MappedLifetimeDemo.java
java MappedLifetimeDemo
```

Output when the temporary file is created and accessed successfully:

```text
inside: channelOpen=true
after close: first=A
mapped second=Z
file after force=AZCDE
```

Why does this output make sense?

1. The file `ABCDE` is 5 bytes long, so `map(READ_WRITE, 0, 5)` maps the entire file.
2. `MappedByteBuffer mapped` is declared outside `try`; after the closing `}`, the channel closes, yet the buffer object remains referenced and the mapped region stays valid.
3. `mapped.get(0)` reads byte `A` from the established mapping. If you tried `channel.read(...)` outside the `try` block (assuming a reference remained), the operation on the closed channel would fail.
4. `mapped.put(1, 'Z')` modifies the byte at offset 1. Because this is `READ_WRITE`, the change can be synchronized back to the file. `mapped.force()` requests flushing mapping changes even though the original channel is closed.
5. `Files.readString(...)` reopens the file for reading and observes `AZCDE`. Calling `deleteOnExit()` requests file cleanup when the JVM terminates, though it is not an unmap operation or a guarantee of immediate deletion across every OS.

**Practical note:** Do not place `Files.delete(file)` before the mapped region is no longer in use and assume deletion is guaranteed on Windows. Some systems may hold file resources because the mapping is still alive. The example uses `deleteOnExit()` to keep unmap timing from breaking the demonstration; exit cleanup is likewise only best-effort.

## 4. How Does `close()` Differ from Unmapping?

`FileChannel.close()` closes the channel and releases resources owned by that channel open handle. Depending on the platform, in-flight I/O requests may be affected. After closing, `channel.isOpen()` returns `false` and calls requiring an open channel may throw `ClosedChannelException`.

**Unmapping** terminates the mapping, returning associated resources such as the virtual address region and OS-managed references to the file object. In Java 17, `MappedByteBuffer` **has no standard public `close()` or `unmap()` method** that callers can invoke like closing a channel.

The `FileChannel.map` documentation states that the mapped region remains valid until the buffer itself becomes eligible for garbage collection. Do not infer that merely having a local variable leave scope, setting `mapped = null`, or triggering a single GC forces the mapping to be torn down *immediately*. Unreachability and actual reclamation timing are two separate things.

Views such as `slice()`, `duplicate()`, or `asReadOnlyBuffer()` can share data with the original mapping. Passing a view to other code can keep the underlying mapping resources alive; do not treat dropping the original buffer reference as proof that every object referencing the data is gone.

Comparison:

| Action | Channel | Mapping / buffer |
| --- | --- | --- |
| Exiting `try (FileChannel ch = ...)` | Channel closes automatically | Mapping can continue operating |
| `ch.close()` | Cannot continue I/O through `ch` | Does not automatically unmap the mapped region |
| `mapped.clear()` | Does not affect channel | Only resets position/limit, **does not erase bytes or unmap** |
| `mapped.flip()` | Does not affect channel | Only changes buffer state |
| `mapped.force()` | Does not require original channel to stay open | Requests synchronizing modified mapped contents, **does not release the mapping** |
| No remaining references using the mapping | Channel may already have been closed earlier | Mapped region may later be reclaimed by JVM/GC mechanics at a non-deterministic time |

In resource-management code, treat **the `FileChannel` lifecycle** and **the lifecycle of all objects using the mapping** as two distinct boundaries.

## 5. Does Closing the Channel Automatically Write Data to Disk?

Do not equate **being able to read newly modified data**, **when the OS transfers dirty memory pages to the device**, and **data durability across power loss**.

When modifying a `READ_WRITE` mapping, changes propagate to file contents via memory-mapping mechanics, but the JVM does not promise every byte is durably stored simply because `put()` returned. For files on local storage devices, `MappedByteBuffer.force()` is the API for requesting that mapping edits be written to the device per Java's contract. For mappings on some other file/device types, guarantees may differ or be less strictly defined.

**Closing `FileChannel` does not substitute for `MappedByteBuffer.force()`.** After the channel closes, a live buffer can still call `force()`. Conversely, `channel.force(true)` must be called while the channel is open and pertains to file updates made via the channel; do not mistake it for a method that releases the mapped region.

Modes also differ:

- `READ_WRITE`: edits the mapped region to affect file contents; may require `mapped.force()` depending on durability needs.
- `READ_ONLY`: does not modify data via buffer; `put` is forbidden. Calling `force` does not make it writable.
- `PRIVATE`: writes via private copy-on-write, never writing private mapping changes back to the file. Do not call `force()` expecting private mapping data to persist into the underlying file.

When designing critical updates, you need policies for **preventing overlapping writes**, **I/O error handling**, **content validation**, and **durability**. `force()` does not turn a complex sequence of byte modifications into an atomic transaction.

## 6. Why Might a File Not Yet Be Deletable or Renamable?

Memory mappings are managed by the operating system. A file may remain referenced by an active mapping even though the application has closed the initial descriptor/channel.

Behavior when calling `Files.delete(path)`, `Files.move(path, ...)`, or truncating a mapped file **varies across systems**:

- On some Unix-like systems, a pathname may be unlinked while a mapping persists, and the mapped data pages may continue to be accessible under OS semantics. This is not a guaranteed contract for every Java provider or scenario.
- On Windows, an active mapping can cause file deletion, moves, or replacements to fail because OS resources still reference the file. Closing the channel alone does not guarantee releasing that constraint.
- Network filesystems, containers, antivirus scanners, file locks, and file-sharing policies can introduce additional behavior.

Therefore, **"the channel is closed" is insufficient to prove a file can be deleted immediately.** If a workflow must periodically replace a file, design the lifecycle so old mappings are no longer used before the delete/rename step, and handle real exceptions from `Files.delete/move`.

Do not use `System.gc()` with polling loops to "force" unmapping: `System.gc()` is only a hint/request to the JVM, not a promise that mappings will be reclaimed at a deterministic time. Invoking non-standard internal APIs like `Unsafe.invokeCleaner` to force release can be implementation-dependent, break safety if a mapping is still in use, and is unsuitable as a default solution.

### Do not truncate a file while a mapping is in use

If a region is mapped and the underlying file is truncated or the associated region becomes inaccessible, subsequent `get/put` calls may fail with an exception **not specifically prescribed by Java**. You cannot rely on catching a single specific exception type across all platforms.

Applications must coordinate lifecycles with code that writes, truncates, or deletes files. If multiple processes operate concurrently, in-JVM locking alone cannot protect against an external process that ignores locks.

## 7. What Resources Do Live Mappings Consume?

A memory mapping can consume **virtual address space**, native metadata, and RAM pages as they are touched. Do not infer that a 1 GiB mapped region always occupies 1 GiB of physical RAM the moment `map` returns. On many systems, pages are faulted in on demand and subject to OS caching/page-replacement policies.

Splitting a large file into hundreds of mappings and holding all buffers/views in a cache can cause resource pressure even when every `FileChannel` that created them has closed:

- The number of mappings / virtual memory ranges and total virtual address space are bounded.
- Active pages can affect page faults, the page cache, physical memory, and swap behavior.
- Mapped buffers still carry Java objects/metadata; retaining references long-term prevents mapping resource reclamation.
- Monitoring only the Java heap misses native and memory-mapped resources. On JVMs that support it, `BufferPoolMXBean` for the `mapped` pool gives partial metrics; combine it with process/OS memory stats for the full picture.

Example measuring `BufferPoolMXBean` metrics (illustrative snippet, place inside a Java class/method):

```java
for (java.lang.management.BufferPoolMXBean pool :
        java.lang.management.ManagementFactory.getPlatformMXBeans(
                java.lang.management.BufferPoolMXBean.class)) {
    if ("mapped".equals(pool.getName())) {
        System.out.println("mapped count=" + pool.getCount());
        System.out.println("mapped capacity=" + pool.getTotalCapacity());
        System.out.println("mapped memoryUsed=" + pool.getMemoryUsed());
    }
}
```

These metrics **are not equivalent** to RSS, page cache usage, open descriptor counts, or total native memory; values may depend on the JVM. If mappings accumulate unexpectedly, locate retained objects/views and inspect caching/pooling strategies rather than only checking open `FileChannel` counts.

## 8. Managing Lifecycles According to Application Needs

Several design approaches avoid relying on exact mapping-reclamation timing:

### 8.1. Keep usage scopes clear

Create the mapping, complete processing, and stop sharing the buffer once the task finishes. If you hand a `MappedByteBuffer` to another thread or store it in a cache, treat that as extending the mapping's lifetime, even if the channel that created it closed long ago.

```java
// Illustrative snippet: Path file already exists, read completely within a clear scope.
try (FileChannel channel = FileChannel.open(
        file, java.nio.file.StandardOpenOption.READ)) {
    MappedByteBuffer mapped =
            channel.map(FileChannel.MapMode.READ_ONLY, 0, channel.size());
    while (mapped.hasRemaining()) {
        process(mapped.get()); // Illustrative business logic handler.
    }
}
// Channel is closed; mapped is no longer actively used.
// There is no promise that GC/unmap occurs right at the closing brace }.
```

The snippet above **is not standalone**: it requires importing `MappedByteBuffer`, `FileChannel`, declaring `file` and `process`, and handling `IOException`. For files too large for one `MappedByteBuffer`, split into appropriate regions. For potentially empty files, decide how the application should handle a 0-byte region.

### 8.2. Use `FileChannel.read/write` when predictable resource closing is needed

If the requirement is "once finished processing, immediately close and replace/delete the file" and the application has no clear need for memory mapping, block-based reading/writing via `FileChannel` with a regular `ByteBuffer` is worth considering. A channel closed cleanly by `try-with-resources` provides simpler resource ownership than a mapping.

However, `FileChannel` and regular buffers still require concurrency, exception, and read/write state management. Do not assume switching to `read/write` automatically fixes all data-sharing bugs.

### 8.3. Split large regions and avoid retaining unused mappings

When you must memory-map large files, map reasonably sized regions needed for processing; keep only the regions actively in use. Avoid storing every mapping in an unbounded long-lived list. If reusing mappings across requests, bound their count, ownership, and cache invalidation when underlying data changes.

### 8.4. Avoid non-standard "explicit unmap" hacks

Newer Java versions offer different memory-region management mechanisms, yet within **Java 17**'s `MappedByteBuffer` API, there is no public `unmap()` operation guaranteeing synchronous teardown. Do not write libraries relying on reflection into JDK internals merely to release a mapping at an exact instant; choose an alternative API and resource architecture if deterministic lifecycle is a hard requirement.

## 9. Key Misconceptions

| Misconception | Reality and how to handle it |
| --- | --- |
| "Exiting `try(FileChannel ...)` invalidates the mapping." | The channel is closed, yet `MappedByteBuffer` can still access the mapped region; the example above demonstrates this directly. |
| "`MappedByteBuffer.clear()` releases the file mapping." | `clear()` only resets position and limit; it does not unmap. |
| "Closing the channel always makes mapped edits durable on disk." | Data durability is separate; call `MappedByteBuffer.force()` when needed per contract. |
| "Once the channel is closed, the file can always be deleted/renamed." | A live mapping may block the operation on some OSes; check and handle errors. |
| "Calling `System.gc()` unmaps immediately." | There is no guarantee of immediate reclamation; never rely on GC as a deterministic resource-closing protocol. |
| "A 2 GiB mapping means 2 GiB of physical RAM is used." | Mapped address space size does not equal actual resident RSS or page cache usage. |
| "`MappedByteBuffer.force()` ends the mapping." | `force()` requests flushing modified data, without tearing down the mapping. |
| "You can truncate a file underneath a mapping and keep reading bytes as before." | Accessing an invalidated region can fail with an unspecified exception. |
| "Private mappings save edits to the file on force." | `MapMode.PRIVATE` uses private copy-on-write and has no semantics for persisting edits to the original file. |

## 10. How to Test Lifecycle Behavior Yourself

You can extend `MappedLifetimeDemo` to verify assumptions in a controlled way:

1. Print `channel.isOpen()` inside the `try` block, then **after exiting the block** read from the buffer. Observe that the channel ends its lifecycle first while the buffer remains accessible.
2. Switch `READ_WRITE` to `READ_ONLY` and perform only `get()`; attempt `put()` separately to observe `ReadOnlyBufferException`.
3. Create a `slice()` view and modify data through the view within valid bounds; note that views share contents and can extend the mapped region's lifetime.
4. Test delete/rename operations **on a dedicated temporary file** while a mapping is still alive to observe OS behavior; handle `IOException` instead of assuming identical outcomes everywhere. Never test this on real production data.
5. Monitor the `mapped` memory pool metrics and OS process memory when creating/releasing references to multiple mappings; never use a single GC call to assume guaranteed unmap timing.

**Key takeaway:** `FileChannel.map()` creates a mapped region whose lifecycle is independent of the `FileChannel` that created it. `try-with-resources` closes the channel properly, yet **does not automatically close `MappedByteBuffer`**, does not force immediate unmapping, and does not by itself guarantee you can delete/move the file or that edits are durably persisted. Design separately for mapping usage duration, data synchronization policy, and file maintenance operations.
