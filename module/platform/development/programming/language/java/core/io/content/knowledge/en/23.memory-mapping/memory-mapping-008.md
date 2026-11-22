# Memory Mapping Release Limits Across API and JVM Versions

## 1. The Practical Problem: After Closing the File, Has the Mapping Been Released?

When using a **memory-mapped file**, Java maps a region of a file's contents into the process's virtual memory address space. The program can access that region through `MappedByteBuffer` or, on newer JDKs, `MemorySegment`. This mechanism often avoids manually copying data with an application-level `FileChannel.read/write` loop, yet it raises a question about **native resource lifetimes**: when does the operating system stop holding the mapped region?

A common misconception:

```java
MappedByteBuffer mapped = channel.map(
    FileChannel.MapMode.READ_WRITE, 0, length);
channel.close();
// Cannot infer that the mapped region has already been unmapped.
```

This is an illustrative snippet, assuming `channel` and `length` are already declared. `close()` releases the **channel's** resources, whereas the created mapping has its own lifecycle. With the legacy API returning `MappedByteBuffer`, **closing the channel does not destroy the mapping**. The mapping can remain valid while the buffer is still in use.

The Java SE 17 API contract states that a `MappedByteBuffer`'s mapping remains valid until the buffer itself is garbage-collected. However, **when GC occurs is not guaranteed**; Java SE 17 also exposes no standard public `unmap()`/`close()` method on `MappedByteBuffer`. This is a core limitation to understand when designing programs that must release or replace files immediately.

## 2. Distinguishing Four Commonly Confused Operations

| Operation | What it actually does | Guarantees unmapping? |
| --- | --- | --- |
| `FileChannel.close()` | Closes the channel and channel-owned resources | **No** for any `MappedByteBuffer` mapping already created |
| `mapped.force()` | Requests synchronizing changes in a read/write mapping to the storage device per API contract | **No** |
| `mapped.clear()` | Resets `position=0`, `limit=capacity`, clears mark | **No**; does not erase bytes |
| Mapping object becomes unreachable and GC collects it | Can lead to releasing the old buffer's mapping resources | **No deterministic timing** |

Separate these concepts clearly:

- **Flush/persistence**: whether modified data has been pushed down to the storage device.
- **Unmap/release**: the memory-mapped region is no longer held by the process.
- **Close channel**: the channel resource is closed.
- **Delete/rename/truncate**: filesystem operations; behavior with a live mapping depends on the platform.

`force()` serves data durability, **not releasing the mapped region**. `load()` only tries to bring pages into RAM; `isLoaded()` only hints at residency; neither is an unmap API. `System.gc()` only asks the JVM to consider running GC, creating no promise of immediate release.

## 3. Legacy API: `FileChannel.map(mode, position, size)`

Present since older Java versions and still present in Java 17/21/22+, `FileChannel` provides:

```java
MappedByteBuffer map(
        FileChannel.MapMode mode,
        long position,
        long size) throws IOException;
```

The result is `java.nio.MappedByteBuffer`, a direct `ByteBuffer` representing the mapped file region.

**Key contract points:**

1. The mapping can remain accessible **after `FileChannel` has been closed**.
2. When the mapping is released is tied to the buffer becoming eligible for GC; the application **does not control exact GC timing**.
3. `MappedByteBuffer` does not implement `AutoCloseable` and has no standard public `close()` or `unmap()` method.
4. Views such as `slice()` or `duplicate()` can share the underlying content region. Do not assume setting `mapped = null` is enough if views or related references are still alive.
5. Native resources and virtual address space can stay held even when visible heap usage looks small. Relying solely on `Runtime.freeMemory()` to infer the mapping was torn down is wrong.

By API specification, the size of a mapping returning `MappedByteBuffer` is bounded by the buffer's `int` indexing (a mapped region cannot exceed `Integer.MAX_VALUE` bytes). Larger files can be split into multiple smaller mappings by design; each mapping still requires lifecycle management. **Reducing map count or switching to regular read/write I/O** can help when frequent mapping creation/teardown becomes hard to manage.

## 4. Java 17+ Example: Mapping Remains Usable After Channel Close

This program creates a 4-byte temporary file, maps it in `READ_WRITE` mode, closes the channel, and then continues reading and editing via `MappedByteBuffer`. The file is registered for deletion on JVM exit; that is **program-exit file cleanup**, not an unmap operation.

**File `LegacyMappingDemo.java`:**

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class LegacyMappingDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("legacy-map-", ".bin");
        path.toFile().deleteOnExit();
        Files.write(path, new byte[] {10, 20, 30, 40});

        MappedByteBuffer mapped;
        try (FileChannel channel = FileChannel.open(
                path,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {
            mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 4);
            System.out.println("Trong khoi mo: " + mapped.get(0));
        }

        // FileChannel is closed; the mapping can still be accessed.
        System.out.println("Sau close channel: " + mapped.get(1));
        mapped.put(2, (byte) 99);
        mapped.force();

        System.out.println("Byte vua sua: " + mapped.get(2));
        System.out.println("Size: " + Files.size(path));
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac LegacyMappingDemo.java
java LegacyMappingDemo
```

**Stdout when I/O succeeds:**

```text
Trong khoi mo: 10
Sau close channel: 20
Byte vua sua: 99
Size: 4
```

The example demonstrates that **closing the channel does not invalidate `mapped`**. It **does not measure unmap timing** and does not use `System.gc()` to claim immediate resource reclamation. `deleteOnExit()` only registers a one-time deletion on JVM exit, so actual success still depends on the filesystem and resource state; do not use this trick as a long-term cleanup policy for continuously running services.

On Windows, an existing mapping can block file deletion/renaming in certain situations; some Unix systems allow unlinking a pathname while a mapping remains live. Do not write code assuming "if it deletes on my dev machine, it will always delete on every OS."

## 5. By Java Version: When Do You Have Explicit Lifecycle Control?

The table below distinguishes **available standard APIs**, without assuming identical behavior across all JDK vendors and providers:

| Version | Primary standard mapping API | Control over release timing |
| --- | --- | --- |
| Java 8, 11, 17, 21 | `FileChannel.map(MapMode, long, long)` → `MappedByteBuffer` | Tied to reachability/GC; no standard `MappedByteBuffer.close()` |
| Java 22 onward | Overload returning `MappedByteBuffer` still exists | Legacy mappings **still** have GC lifecycle limits |
| Java 22 onward | Adds `FileChannel.map(MapMode, long, long, Arena)` → `MemorySegment` | Can be bound to a **closable arena**; closing the arena releases the segment's mapping per contract |

The **Java 22 milestone** matters because the Foreign Function & Memory API (FFM API, `java.lang.foreign`) was finalized alongside the `FileChannel.map(..., Arena)` overload. This **does not turn legacy `MappedByteBuffer`s into objects with `close()`**. To use arena lifecycles, a program must explicitly choose the API returning `MemorySegment` and run on a supporting runtime/provider.

The specification of the new overload notes that **the default implementation may throw `UnsupportedOperationException`**. Common JDKs provide real implementations supporting arena-based mapping, yet if an application uses a custom `FileChannel` provider, lack of support must still be considered.

Do not claim that "every Java 22+ supports that call on every file provider" or "upgrading Java automatically fixes unmapping in legacy code."

## 6. Java 22+ API: `MemorySegment` and `Arena`

New overload:

```java
MemorySegment map(
        FileChannel.MapMode mode,
        long offset,
        long size,
        Arena arena) throws IOException;
```

- `MemorySegment` represents a memory region with explicit bounds.
- `Arena` defines the lifecycle and access rules for segments bound to it.
- With a **closable arena**, the mapping is unmapped when that arena is **closed successfully** per the `FileChannel.map` contract.
- Operations accessing the segment after the arena closes are rejected, typically with `IllegalStateException`; this enforces *temporal safety*.
- With `Arena.ofConfined()`, only the owning thread may use or close that region; cross-thread access can throw `WrongThreadException`.
- `Arena.ofShared()` fits cases where multiple threads need access while retaining an explicit close lifecycle.

Arenas have important differences:

| Arena | Explicitly closable? | Usable from multiple threads? | Lifecycle |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Yes | No | Ends when closed by the owning thread |
| `Arena.ofShared()` | Yes | Yes | Ends when closed; requires task coordination |
| `Arena.ofAuto()` | No | Yes | Automatically reclaimed when the JVM determines the arena/segment is no longer alive; no deterministic timing |
| `Arena.global()` | No | Yes | Global lifetime; not for scheduling explicit unmapping |

**When you want application-controlled release timing, choose a closable arena.** Using `Arena.ofAuto()` still carries the non-determinism of automatic memory management; `Arena.global()` is even less suitable if mappings must be freed per request.

`Arena.close()` is not idempotent: closing twice can throw `IllegalStateException`. `try-with-resources` prevents duplicate close calls and ensures closing on scope exit, even on exceptions, provided the close itself succeeds.

## 7. Java 22+ Example: Releasing a Mapping by Closing the Arena

The following program uses the official Java 22+ API. The file is mapped into a `MemorySegment` belonging to `Arena.ofConfined()`. Upon exiting `try-with-resources`, the arena closes, the mapping is released per the API contract, and further segment accesses are rejected.

**File `ArenaMappingDemo.java`:**

```java
import java.io.IOException;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ArenaMappingDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("arena-map-", ".bin");
        Files.write(path, new byte[] {1, 2, 3, 4});

        MemorySegment segment;
        try (Arena arena = Arena.ofConfined();
             FileChannel channel = FileChannel.open(
                     path,
                     StandardOpenOption.READ,
                     StandardOpenOption.WRITE)) {

            segment = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 4, arena);

            System.out.println(
                    "Truoc close: " + segment.get(ValueLayout.JAVA_BYTE, 0));
            segment.set(ValueLayout.JAVA_BYTE, 1, (byte) 42);
            segment.force();
        } // Close channel, then close arena => mapping is unmapped.

        try {
            segment.get(ValueLayout.JAVA_BYTE, 0);
            System.out.println("Truy cap van thanh cong");
        } catch (IllegalStateException ex) {
            System.out.println("Segment khong con hieu luc");
        }

        byte[] contents = Files.readAllBytes(path);
        System.out.println("Byte tai 1: " + contents[1]);
        Files.delete(path);
    }
}
```

Use **JDK 22 or newer supporting the mapping overload on the active file provider**:

```bash
javac ArenaMappingDemo.java
java ArenaMappingDemo
```

**Stdout when I/O and mapping release succeed:**

```text
Truoc close: 1
Segment khong con hieu luc
Byte tai 1: 42
```

**Why does this result differ from the Java 17 example?**

1. `segment` is created using the `map(..., arena)` overload, not the one returning `MappedByteBuffer`.
2. Within `arena`'s scope, the segment is valid and allows byte reads/writes.
3. `segment.force()` is used to synchronize edits on the `READ_WRITE` mapping; it **does not** replace `arena.close()`.
4. On exiting `try`, `channel.close()` runs before `arena.close()` because resources close in reverse declaration order.
5. Successfully closing the arena ends the segment's lifecycle; subsequent `segment.get` throws `IllegalStateException`, which is caught to print the message.
6. The file still exists and contains the written byte 42; releasing the mapping does not automatically delete the file. The program deletes the file at the end.

**Limitations:** if the file provider does not support the overload, `UnsupportedOperationException` may be thrown. On permission errors, disk-space issues, I/O errors, or arena-close failures, the program may not print the full example stdout. This example uses a single mapping on one thread; for multi-threaded code, choose the right arena and follow proper handoff/access rules.

## 8. MappedByteBuffer and MemorySegment: Two Resource Management Models

| Aspect | Legacy `MappedByteBuffer` | `MemorySegment` with closable arena |
| --- | --- | --- |
| Creation API | `map(mode, offset, size)` | `map(mode, offset, size, arena)` |
| Official version | Long-standing, usable in Java 17 | Java 22+ |
| Lifecycle control | Buffer GC | `arena.close()` |
| Direct standard `close()` on map result? | No | Do not close the segment directly; close the **arena** |
| When closing `FileChannel` | Mapping remains valid | Does not replace closing the arena |
| When timely release is needed | No direct standard public API | Wrap mapping in `try (Arena arena = ...)` |
| Accessing after resource release | Depends on mapping/GC state; not designed for deterministic unmap | Segment is rejected after arena closes |
| Large mapping support | Limited by `int`-indexed `ByteBuffer` | `MemorySegment` uses `long` sizes, subject to practical limits |

Note that `MemorySegment.asByteBuffer()` only creates a `ByteBuffer` view when the length fits within `int` bounds. This view **does not escape the arena's lifecycle**: accessing the buffer view after the arena closes is likewise disallowed. That differs from the false conclusion that "wrapping a segment into a `ByteBuffer` automatically extends the mapping's lifetime."

The new model provides more predictable resource management, though you must still respect access permissions, data consistency, and OS limits. Never assume by default that a mapped segment can be used freely across threads if it lives in a confined arena.

## 9. Limits That Persist Across All Versions

### 9.1. The file can still be modified, shrunk, or replaced elsewhere

Java does not guarantee consistent behavior if a file is **truncated** or resized while a mapping is in use. Per `MappedByteBuffer` and `MemorySegment` documentation, all or part of the mapped region can become inaccessible; errors thrown on access may **not be precisely specified** across operating systems.

Therefore, do not use opening/closing arenas to infer that an application can arbitrarily truncate a file currently mapped by others. Coordinate writers/readers or design snapshots/versioning, avoiding file truncation while live mappings remain.

### 9.2. Do not equate releasing a mapping with durable write guarantees

With a `READ_WRITE` mapping, edits may be synced to the file per OS mechanics. If business logic requires pushing edits to the storage device before confirming success, use `MappedByteBuffer.force()` or `MemorySegment.force()` as appropriate.

- `force()` is an operation concerning **persistence**.
- `close()` on an arena is an operation concerning **mapping lifecycle**.
- `FileChannel.force(boolean)` concerns **channel** data/metadata, and does not act as an unmap button.

Data durability on remote devices or special filesystems still carries specification limits. Never assume unmapping equals an atomic write transaction.

### 9.3. Deleting/renaming a mapped file varies across OSes

Some OSes allow renaming or unlinking a file while a process still holds a mapping; others may return a "file in use" error or block deletion for the entire lifetime of the mapping. Java NIO **does not provide a uniform cross-platform guarantee** in this situation.

If an application handles temporary files, segment files, or rotating logs and must delete them immediately, choose an API with explicit lifecycle control (JDK 22+), or if stuck on Java 17, consider designs **not relying on immediate unmapping**, such as reading/writing via regular `FileChannel`, scoping task lifetimes, or deferring cleanup under a proper policy.

### 9.4. Off-heap, virtual address space, and mapping limits

Mapping is not like allocating a large `byte[]` on the Java heap. A large volume of mapped data can consume **virtual address space** and page-management resources that heap metrics do not fully reflect. Never conclude a mapping has been released just because heap usage is low.

Limits also depend on 32/64-bit architecture, file descriptors, mmap region count limits, address-space bounds, file state, and filesystem capabilities. When an application creates mappings continuously, monitor mapping counts/lifecycles, observe process resources with appropriate tools, and measure on the actual target OS.

### 9.5. Closing an arena also requires handling in-flight tasks

With `Arena.ofShared()`, multiple threads can access the mapped memory region concurrently. One thread trying to close the arena while another thread is actively using it can trigger exceptions on close or on access per the FFM contract. Complete or cancel active tasks and coordinate lifecycles before closing.

With `Arena.ofConfined()`, only the owning thread may access or close it. Passing the segment to another thread and calling `get` or `set` directly violates thread confinement. If an API requires passing data across threads, use a shared arena or copy data into a separate structure by design.

## 10. "Unmap Tricks" That Need Careful Scrutiny

### 10.1. Calling `System.gc()` to force unmapping

```java
mapped = null;
System.gc();
```

This is **not a deterministic solution**. `mapped = null` drops only one specific reference; views or other references may still keep resources alive. `System.gc()` is merely a hint that the JVM may ignore or execute later. You cannot prove a mapping was unmapped just because `System.gc()` returned.

### 10.2. Using `sun.misc.Unsafe.invokeCleaner` or internal reflection

Some legacy code uses internal APIs to invoke the cleaner on a direct buffer. This approach is **not a portable Java SE solution**: it depends on JVM implementation, module encapsulation, access permissions, build flags, and buffer/view state, and can break on JDK upgrades. Deliberately bypassing JVM safeguards also risks use-after-unmap bugs if resources are still in use.

Do not recommend this trick as a default pattern for libraries targeting multiple vendors/JVMs. When forced to maintain legacy systems, evaluate it specifically for the target runtime, enforce strict ownership, and test thoroughly; prefer standard APIs with explicit lifecycles whenever upgrading is possible.

### 10.3. Thinking closing the channel or calling `clear` lets you delete the file right away

Channel `close()` does not free legacy mappings; buffer `clear()` only adjusts `position/limit`; `force()` synchronizes data. Those three operations serve three distinct purposes. Design bugs commonly arise when an application maps a file, closes the channel, immediately calls `Files.delete(path)`, and assumes it must succeed on every OS.

## 11. Choosing the Right Solution for Production Applications

| Need | Implementation direction |
| --- | --- |
| Java 17 mapping large files, reading repeatedly | Bound live mapping count, control reference scopes; accept GC-driven release or choose unmapped I/O |
| Java 17 needing immediate delete/rename of temp files after a request | Avoid relying on GC timing; consider `FileChannel.read/write` with `ByteBuffer` if suitable |
| Java 22+ needing unmapping at end of processing scope | `FileChannel.map(..., Arena.ofConfined())` with `try-with-resources`, if single-threaded |
| Java 22+ sharing a mapping across multiple threads | `Arena.ofShared()` and coordinate closing after all tasks complete |
| No explicit release needed, automatic lifecycle acceptable | `Arena.ofAuto()` may fit; no guaranteed unmap timing |
| Needing assurance changes reached the storage device | Use `force()` appropriately before reporting completion |
| Needing compatibility across multiple JDK versions | Set clear build/runtime baselines, verify JDK 22 overload and provider support, test on target OSes |

If the goal is merely reading a modestly sized file sequentially, mapping is not necessarily superior to every other option. Designs should weigh file size, reuse frequency, file replacement/deletion needs, native resource limits, and service lifecycles.

## 12. Self-Check Questions

**Question 1.** Java 17: you called `FileChannel.close()` after mapping. Can you immediately call `Files.delete(path)` and be certain it succeeds on every OS?

**No.** The `MappedByteBuffer` mapping can stay alive after the channel closes, and delete/rename behavior on mapped files is OS-dependent.

**Question 2.** Does calling `mapped.force()` tear down the memory mapping?

**No.** `force()` is a request to synchronize data to the storage device, not an unmap operation.

**Question 3.** Java 22+: `FileChannel.map(..., Arena)` exists, so are all legacy `MappedByteBuffer` programs unmapped when closing the channel?

**No.** The legacy API still creates mappings whose lifecycle is tied to GC. Only the `map` overload returning `MemorySegment` bound to a **closable arena** has the contract of closing the arena to unmap by scope.

**Question 4.** Using `Arena.ofAuto()`, can you call `close()` to force immediate unmapping when a request finishes?

**No.** Automatic arenas cannot be explicitly closed under the API model. Choose a confined or shared arena if timely closing is needed.

**Question 5.** After closing `Arena.ofConfined()`, should you keep the `MemorySegment` and continue calling `get` on it?

**No.** The scope is no longer alive; access attempts are rejected with an exception, typically `IllegalStateException`. Closing the arena marks **the end of access permission** to the mapped region.

## 13. Key Takeaways and Official Documentation

- `MappedByteBuffer` from `FileChannel.map(mode, position, size)` **has no standard public unmap/close**; its mapping lifecycle is tied to GC with no guaranteed release time.
- `FileChannel.close()`, `MappedByteBuffer.clear()`, and `force()` **are not unmap operations**.
- **Java 22+** provides the `FileChannel.map(mode, offset, size, arena)` overload returning `MemorySegment`. With a closable arena, **successfully closing the arena unmaps** the region bound to it.
- Choose `Arena.ofConfined()` for single-threaded use and `Arena.ofShared()` when multiple threads are needed; `ofAuto()`/`global()` do not offer explicit unmap scheduling.
- Availability after truncation, device writeback timing, delete/rename behavior, and concurrency all involve OS/JVM/provider dependencies.

**Official documentation for version comparison:**

1. [MappedByteBuffer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html).
2. [FileChannel — Java SE 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.html), especially the `map(..., Arena)` overload and `Since: 22` notes.
3. [Arena — Java SE 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html), arena kinds and scope-closing rules.
4. [MemorySegment — Java SE 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html), mapping access, `force()`, and segment lifecycle.
