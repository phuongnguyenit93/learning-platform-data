# Heap Buffers, Direct Memory, and Memory Pressure in Java NIO

## 1. The Practical Problem: Large Files and Memory Not Only in the Heap

When reading or writing large files with Java NIO, programs typically create `ByteBuffer` objects. There are two obvious allocation methods:

- `ByteBuffer.allocate(capacity)`: creates a **heap byte buffer**, whose data region resides in the JVM heap.
- `ByteBuffer.allocateDirect(capacity)`: requests a **direct byte buffer**, whose data resides in a memory region that native I/O can access more directly, commonly called *off-heap/direct memory*.

A common mistake is thinking that increasing `-Xmx` solves all memory errors. In reality, a Java application also consumes direct buffers, memory-mapped files, thread stacks, metaspace, JIT code cache, native libraries, OS page cache, and many other resources. A program with **plenty of free Java heap** can still fail to allocate a direct buffer or hit the OS/container total memory limit.

Conversely, one should not conclude “direct is always faster than heap.” Direct buffers help in certain native I/O transfer paths, but allocation/reclamation costs, cache locality, copying data from Java objects, and usage patterns can make them less efficient than heap buffers.

Lesson objectives:

1. Distinguish how heap/direct buffers are organized and the APIs to identify them.
2. Understand how direct memory is managed differently from the heap and how buffer lifecycles affect memory pressure.
3. Know when direct buffers can reduce copies in `FileChannel`/`SocketChannel` and when they cannot.
4. Read `BufferPoolMXBean`, Java heap, and RSS/container memory metrics properly.
5. Design pools, buffer size limits, and backpressure for large files/high load.
6. Write runnable Java 17+ examples with proper read/write loops and clear cleanup.

## 2. What Is a Heap ByteBuffer?

`ByteBuffer.allocate(n)` allocates a `ByteBuffer` with a capacity of `n` bytes. For a heap buffer from `allocate`, the backing storage is typically a `byte[]` array managed by the GC heap.

~~~java
ByteBuffer heap = ByteBuffer.allocate(1024);
System.out.println(heap.isDirect()); // false
System.out.println(heap.hasArray()); // true
~~~

This is an illustrative snippet inside a method with `import java.nio.ByteBuffer`. Properties:

- The actual data is stored in a `byte[]` array on the Java heap; the `-Xmx` heap limit governs how much can be allocated.
- `hasArray()` indicates whether the current buffer's backing array can be accessed via `array()`; for writable heap buffers from `allocate`, it is `true`.
- Both `arrayOffset()` and `position()` matter when passing a buffer region to an array-taking API. Do not assume valid bytes start at offset 0.
- `ByteBuffer.wrap(byte[])` creates a buffer backed by the **caller-supplied array**; it does not make a copy of that array.
- GC manages the backing array; once no longer reachable, the data may be reclaimed over GC cycles per runtime policy, not immediately when `clear()` is called.

Heap buffers suit pure Java parsers, integration with `byte[]`-based APIs, short-lived buffers, or workloads where direct I/O benefits do not outweigh native memory management costs.

**Not every buffer with `isDirect()==false` has `hasArray()==true` usable from outside.** For instance, a read-only heap buffer may disallow access to its backing array. Check `hasArray()` before calling `array()` rather than relying on `!isDirect()`.

## 3. What Is a Direct ByteBuffer?

`ByteBuffer.allocateDirect(n)` creates a direct buffer with backing storage intended for native I/O, not residing in a `byte[]` on the Java heap.

~~~java
ByteBuffer direct = ByteBuffer.allocateDirect(1024);
System.out.println(direct.isDirect()); // true
System.out.println(direct.hasArray()); // false
~~~

A direct buffer is still a Java object with `position`, `limit`, `capacity`, and read/write methods, while its data storage typically lives in native memory. Distinguish:

- **Java wrapper object**: visible to GC, which manages the object lifecycle.
- **Off-heap backing memory**: holds the buffer's bytes, outside the heap bounded by `-Xmx`.
- **Reference graph**: if the application retains a reference to a direct buffer or a view like `slice()/duplicate()`, the underlying memory may still have to be retained.
- **Native address**: an implementation detail; the `ByteBuffer` API does not expose a portable interface to free or manipulate arbitrary native addresses.

`direct.array()` cannot be used because direct buffers do not expose a public backing `byte[]`. If code needs to call an API that only accepts arrays, you must copy bytes into an array or switch to an API accepting `ByteBuffer`.

### Direct Does Not Mean “Completely Outside GC”

Direct memory **does not consume array space in the heap**, yet its lifecycle is usually tied to the reachability/cleaner of Java objects. On common JDK implementations, native memory is freed when the runtime determines there are no remaining relevant references and runs cleanup. **There is no guarantee it is reclaimed immediately when a local variable leaves scope.**

Therefore, in applications needing rapid allocation/deallocation, creating a new `allocateDirect` per request can cause memory and GC pressure despite low heap usage. Using a bounded number of direct buffers and reusing them helps reduce this pressure.

### Direct Allocation Can Fail When Heap Has Free Space

When the direct memory quota is exceeded or the runtime/OS cannot allocate native backing, allocation can throw an `OutOfMemoryError` related to direct buffer memory. Never assume `OutOfMemoryError` only relates to `Java heap space`. Also never blindly increase `-Xmx` and consider the issue solved.

## 4. ByteBuffer Still Has position, limit, capacity, and mark

Heap and direct buffers follow the same cursor model:

- `capacity`: size of the initially allocated data region, immutable for the buffer's lifetime.
- `position`: index of the next read/write in relative operations.
- `limit`: boundary of positions currently permitted for operations.
- `mark`: an optional saved position.

Write-then-read pattern:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(16);
buffer.put(new byte[] {65, 66, 67}); // Write A B C; position=3.
buffer.flip();                       // limit=3, position=0.
while (buffer.hasRemaining()) {
    System.out.print((char) buffer.get());
}
buffer.clear(); // Prepare for next writes; DOES NOT free native memory.
~~~

This is an illustrative snippet. Calling `clear()` **does not erase bytes**, does not guarantee zeroization of sensitive data, and **does not free backing storage**. It only updates state indices.

Similarly, `compact()` shifts unread bytes to the start of the buffer and resets indices to continue writing. On large buffers, moving bytes also carries a cost. Parser/queue designs should avoid compacting data unnecessarily.

### Views Share Storage Despite Independent Cursors

`duplicate()`, `slice()`, and `asReadOnlyBuffer()` create views with their own cursor state while still sharing backing bytes with the original buffer.

~~~java
ByteBuffer root = ByteBuffer.allocateDirect(4);
root.put(new byte[] {1, 2, 3, 4});
ByteBuffer view = root.duplicate();
view.put(0, (byte) 9);
System.out.println(root.get(0)); // 9
~~~

This is an illustrative snippet. Two separate objects are not two separate native allocations. If one thread manipulates the byte region via `root` and another via `view`, separate cursors **do not** automatically make the backing storage thread-safe.

A read-only view forbids writes through that view, yet does not make the backing bytes immutable if a writable alias still exists. Thus, when handing a buffer to a worker or socket operation, you must define ownership and when the producer may reuse it.

## 5. How Do Heap and Direct Affect I/O Performance?

Some channel/native I/O APIs can transfer data to/from direct memory without copying through an intermediate heap array. This is **why direct buffers are recommended for consideration in intensive I/O operations**, not a promise that every operation is zero-copy.

In some implementations, passing a heap buffer to `FileChannel`/`SocketChannel` may cause the runtime to use a temporary native region to pass data into a syscall, incurring a copy. Using a direct buffer can avoid some of those internal copies.

However:

1. If the original data is a `byte[]` or `String`/object on the heap, copying into a direct buffer is still a copy. Do not ignore the initial data transfer cost.
2. Reading a file from disk typically involves the **kernel page cache** and copying between kernel/user memory; a direct `ByteBuffer` does not automatically enable kernel zero-copy.
3. APIs like `FileChannel.transferTo/transferFrom` may use optimized paths or fallbacks depending on OS, filesystem, channel, and runtime conditions. They differ from merely using `allocateDirect`.
4. Direct allocation/cleanup is more expensive than heap allocation in many scenarios. Small, short-lived buffers may run slower when using direct memory.
5. CPU cache, paging, memory pressure, container memory, and `get/put` access patterns all affect throughput.
6. For small files or parsers working on heap data, direct buffers are not guaranteed to yield measurable gains.
7. Reading a very large file does not mean allocating one giant direct buffer. Streaming with moderately sized chunks and a bounded queue is usually more effective.

Hence, benchmark **your actual production pipeline**: file size, I/O pattern, OS, filesystem, SSD/HDD, concurrency, buffer size, and GC load. Do not use a simple microbenchmark to claim “direct is X% faster” across all systems.

## 6. A Standalone, Compilable/Runnable Java 17+ Example

The program below demonstrates: identifying heap/direct buffers via `isDirect()/hasArray()`; `duplicate()` sharing bytes while having an independent position; using a direct buffer with `FileChannel.write` and a heap buffer for reading back; and finally retrieving direct buffer pool metrics from the management API.

Save as **`BufferMemoryDemo.java`**:

~~~java
import java.io.IOException;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class BufferMemoryDemo {
    public static void main(String[] args) throws IOException {
        ByteBuffer heap = ByteBuffer.allocate(16);
        ByteBuffer direct = ByteBuffer.allocateDirect(16);
        System.out.println("Heap: direct=" + heap.isDirect()
                + ", hasArray=" + heap.hasArray());
        System.out.println("Direct: direct=" + direct.isDirect()
                + ", hasArray=" + direct.hasArray());

        heap.put("ABCD".getBytes(StandardCharsets.UTF_8));
        ByteBuffer duplicate = heap.duplicate();
        duplicate.put(0, (byte) 'Z');
        duplicate.position(2);
        System.out.println("Shared bytes: " + (char) heap.get(0));
        System.out.println("Independent positions: " +
                (heap.position() != duplicate.position()));

        Path file = Files.createTempFile("nio-direct-", ".dat");
        try {
            direct.put("DATA".getBytes(StandardCharsets.UTF_8));
            direct.flip();
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                while (direct.hasRemaining()) {
                    channel.write(direct);
                }
                channel.position(0);
                ByteBuffer received = ByteBuffer.allocate(16);
                while (true) {
                    int n = channel.read(received);
                    if (n == -1 || !received.hasRemaining()) break;
                }
                received.flip();
                System.out.println("File: " +
                        StandardCharsets.UTF_8.decode(received));
            }
        } finally {
            Files.deleteIfExists(file);
        }

        for (BufferPoolMXBean bean : ManagementFactory
                .getPlatformMXBeans(BufferPoolMXBean.class)) {
            if ("direct".equals(bean.getName())) {
                System.out.println("Direct pool observable: " +
                        (bean.getCount() >= 1));
            }
        }
    }
}
~~~

Run commands:

~~~bash
javac BufferMemoryDemo.java
java BufferMemoryDemo
~~~

**Actual stdout compiled and executed on the test JDK:**

~~~text
Heap: direct=false, hasArray=true
Direct: direct=true, hasArray=false
Shared bytes: Z
Independent positions: true
File: DATA
Direct pool observable: true
~~~

Explanation:

- `allocate(16)` creates a heap buffer with an accessible backing array; `allocateDirect(16)` creates a direct buffer that does not expose a `byte[]`.
- After `heap.put("ABCD")`, `heap.position()` is 4. `duplicate.position(2)` does not alter the original heap buffer's position, whereas `duplicate.put(0, 'Z')` mutates the shared storage, so `heap.get(0)` returns `Z`.
- `FileChannel.write(direct)` may write only **a portion** of the remaining bytes, so `while (direct.hasRemaining())` is right instead of assuming one write always suffices. After writing, the code sets `channel.position(0)` and reads into a heap buffer.
- `received.flip()` switches from buffer filling to decoding; `StandardCharsets.UTF_8.decode(received)` yields `DATA`.
- `Files.createTempFile` creates an isolated test file; `finally` deletes it, and `try-with-resources` closes the channel.
- The `BufferPoolMXBean` named `direct` observes the native/direct buffer pool managed by the JDK. The last line only checks that at least one direct buffer exists in the pool at the time of observation; it **must not be used as a fixed-count rule across all JDKs/versions**.

In the demo, `FileChannel` performs blocking file I/O on a tiny file, so the final read loop does not need a selector or non-blocking networking algorithm. In production, to reduce the risk of a non-advancing loop if a provider repeatedly returns 0, check `n==0`, apply timeouts/budgets, or follow mode/provider-specific rules. This code does not call `FileChannel.force()`, so it does not demonstrate data durability.

## 7. Accounting Memory Properly: Heap, Direct, Mapped, and Other Native

A simplified diagram:

~~~text
Java process
  |
  +-- Java heap: objects, byte[], heap ByteBuffer backing arrays
  |
  +-- Native/off-heap:
  |     +-- Direct ByteBuffer backing memory
  |     +-- MappedByteBuffer mappings (memory-mapped regions)
  |     +-- Thread stacks
  |     +-- Metaspace / code cache / JVM internals
  |     +-- JNI/native libraries, allocators, other buffers
  |
  +-- Process virtual address space / resident memory (RSS)
  |
OS:
  +-- Filesystem page cache and kernel-managed memory
  +-- Container/cgroup memory accounting depending on system
~~~

This diagram is for orientation only, not an exact arithmetic addition table. Memory mapping can cause the same physical file pages to appear in both RSS statistics and page cache per kernel accounting rules; never sum all figures from monitoring tools as disjoint memory pools to claim a total.

Key concepts:

- **Heap used:** amount of objects/data used inside the GC-managed heap.
- **Heap committed:** heap memory committed by the JVM; may differ from `-Xmx`.
- **Direct buffer capacity:** total logical capacity of direct buffers tracked by the JVM buffer pool; does not necessarily equal the process's entire native memory.
- **Direct buffer memory used:** native backing bytes reported by the management bean; may differ from total capacity due to alignment/implementation.
- **Mapped buffer capacity/used:** mapping stats tracked by the JVM; it does not mean all pages are resident in RAM.
- **RSS:** resident pages of the process per the OS, containing many memory categories, not just heap/direct.
- **Container memory usage:** may also reflect how the kernel accounts for page cache/anonymous memory; varies across container/cgroup runtimes.

**Never infer “heap usage is 30% so 70% of RAM is left for direct.”** Heap limit, direct limit, process RSS, and container memory limit are separate constraints.

## 8. Direct Memory Limits and Allocation

Depending on the runtime, HotSpot provides the JVM option `-XX:MaxDirectMemorySize=<size>` to control the limit on direct buffer allocations managed by the JDK's direct buffer mechanism. Example specification:

~~~bash
java -XX:MaxDirectMemorySize=256m -Xmx512m MyApplication
~~~

This command is **illustrative**; `MyApplication` must be a real main class. This flag is a HotSpot/implementation option, not a portable specification for every JVM.

Do not assume the default value of `MaxDirectMemorySize` is identical across JDK vendors, versions, and configurations. Check the actual runtime and relevant documentation.

Raising the direct memory limit allows the application to use more direct buffers, yet **does not create extra physical RAM**. Inside a memory-limited container, setting heap + direct limits too high relative to the budget can cause the OOM killer to terminate the process before the application catches errors or runs cleanup.

Example budget to calculate:

~~~text
Total process / container budget:
    Java heap committed
  + direct buffer backing allocations
  + metaspace and code cache
  + thread stacks
  + native/JNI allocations
  + mapped/resident pages and OS overhead
  + headroom for burst, GC, runtime, monitoring
~~~

This is a budgeting model, not an exact sum of measured metrics since accounting can overlap. Leave **practical headroom** rather than setting each independent limit right against the container ceiling.

### Failures from Over-Allocation

`ByteBuffer.allocateDirect(n)` can throw `OutOfMemoryError` when the JDK-managed direct memory limit is reached or native allocation fails. Another symptom can be latency spikes as the JVM tries to reclaim unused direct regions.

If you see an OOME such as *Cannot reserve ... bytes of direct buffer memory* on a HotSpot build, investigate buffer size/count/lifetime and current limits instead of only raising heap size. The exact message text is not part of the Java SE API contract; do not parse logs against one fixed string to diagnose all causes.

## 9. Lifecycle and Why Pooling Often Matters

There are two ways to use direct buffers:

**No reuse, allocation per request:**

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);
try {
    // Process a single request.
} finally {
    // There is no portable close() method on ByteBuffer.
}
~~~

This is an illustrative snippet. Creating many buffers for fast requests can generate bursts of native allocations. `ByteBuffer` **does not implement `AutoCloseable`**, so `try (ByteBuffer buffer = ...)` cannot be used to close direct memory via a standard API.

**Using a bounded pool:**

~~~text
Application starts:
  allocate N direct buffers of size S
Request:
  acquire one buffer -> use -> clear -> return to pool
On overload:
  wait bounded / reject / backpressure
Application shutdown:
  stop using buffers, drop references, let supported runtime clean up
~~~

A pool enables allocation reuse, yet **a pool does not reduce usage automatically**: holding 100 1-MiB direct buffers means keeping the corresponding backing memory even when load drops. Use size classes, high-watermarks, and trim/evict policies where appropriate. Never create an unbounded pool.

An example pool capacity calculation (budgeting math only): 128 buffers × 256 KiB = **32 MiB** of total backing data capacity, excluding object/native overhead/alignment and other application buffers. If actual concurrency exceeds 128, wait/fail/apply backpressure instead of allocating unboundedly.

### Ownership When Returning Buffers to a Pool

Never return a buffer to the pool **before async I/O completes**. If one task is writing from a buffer while another thread calls `clear()` and reuses that buffer for the next request, transmitted data can be corrupted or reordered.

A proper protocol requires:

1. The buffer is leased exclusively to a request/operation.
2. While handed to a channel operation/worker, the producer must not modify content or cursors.
3. With non-blocking `write`, the buffer still has pending bytes until `hasRemaining()==false`.
4. Only when all users are done and no live views still need references does the owner return the buffer to the pool.
5. The buffer is `clear()`ed/zeroized if security requires before leasing to a new tenant/request.
6. A bounded pool handles overload, shutdown, and leak detection (unreturned leases).

Specifically, `duplicate()/slice()/asReadOnlyBuffer()` share backing memory. If a view is still being used by a worker after the root buffer was returned to the pool, data overwrite is a risk. Independent cursors do not replace byte ownership.

## 10. Memory Pressure with Many Connections and Large Files

A design like “one 1-MiB direct buffer per connection” can quickly consume huge amounts of native memory. With 10,000 connections, nominal 1-MiB input buffers alone total roughly **9.77 GiB** of buffer data, excluding outbound queues, TLS buffers, heap, thread stacks, and native runtime.

You do not need a full-file buffer for every file:

- Use **bounded chunk buffers** of 8 KiB–1 MiB depending on benchmarks/load, without hardcoding one size.
- **Stream** files through chunks, sending or writing as each chunk finishes.
- For per-connection buffers, allocate lazily when needed, bound queued bytes, and apply a reclamation policy.
- If data can be very large, never call `Files.readAllBytes(path)` on the whole file if it risks exceeding the memory budget.
- When producers outpace consumers, apply **backpressure**: pause reading temporarily, block on bounded queues, cap concurrency, or fail fast.
- With async/non-blocking I/O, handle partial reads/writes and never reuse a buffer while an operation is still pending.

The core point is that **buffer count × capacity × concurrency × retention time** determines native footprint, not individual file size alone.

### Indirect Heap Pressure Even When Using Direct Buffers

Direct buffers have wrapper objects on the heap and references in collections/pools. Long-lived objects holding native memory may look tiny on the heap yet “pin” large off-heap regions. Thus, a heap dump with very few byte objects may fail to explain why direct memory is nearly exhausted.

Moreover, converting bytes to `String`, UTF-8 encoding, JSON parsing, and creating array copies still allocate on the heap. Using direct buffers for `FileChannel` does not eliminate all heap allocations in an application.

## 11. FileChannel: Correct Read/Write Without Confusing Zero-Copy

When writing from a `ByteBuffer`:

~~~java
while (buffer.hasRemaining()) {
    int written = channel.write(buffer);
    if (written == 0) {
        // No progress yet: wait or switch strategy depending on channel/mode.
    }
}
~~~

This is an illustrative snippet. One `write` call **must not be assumed** to transfer all of `buffer.remaining()`. With a non-blocking `SocketChannel`, `write()==0` can happen frequently; wait for `OP_WRITE` instead of busy-spinning. With traditional `FileChannel`, behavior depends on provider/mode and I/O conditions; production code should still handle errors and progress.

When reading:

~~~java
int n = channel.read(buffer);
if (n == -1) {
    // EOF.
} else if (n > 0) {
    buffer.flip();
    // Process received bytes.
    buffer.compact(); // Retain unconsumed frame bytes, if any.
} else {
    // 0 bytes this time: do not conclude EOF.
}
~~~

This is also an illustrative snippet requiring valid `channel` and `buffer`. If all received bytes were consumed, `clear()` may be suitable; if an incomplete frame remains, `compact()` preserves the remainder.

**Zero-copy is not synonymous with direct buffers:** the term usually refers to data paths that avoid copies between kernel/user space, such as some implementations of `FileChannel.transferTo/transferFrom`. Check the limits and return counts of those methods; they may transfer only part of the data or use a fallback. `allocateDirect` does not guarantee kernel zero-copy.

## 12. Memory-Mapped Files Differ from Regular Direct Allocations

`FileChannel.map(...)` creates a `MappedByteBuffer` representing a region mapped to a file. It is a type of direct buffer, yet **differs in memory model** from `ByteBuffer.allocateDirect()`:

- Storage is tied to an OS-managed memory-mapped region.
- Accessing the buffer can fault file-backed pages into resident memory on demand (page faults).
- A very large mapping does not necessarily make the entire file immediately resident in RAM.
- Mapping lifecycle and memory release depend on reachability/runtime; Java 17's `MappedByteBuffer` API does not provide a standard `close()` for the mapping.
- Closing `FileChannel` does not mean the mapping was immediately unmapped.
- If the file is abnormally truncated/modified or the OS returns a mapping error, behavior can depend on platform and accessed region.

Illustrative example:

~~~java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    MappedByteBuffer mapped = channel.map(FileChannel.MapMode.READ_ONLY, 0, size);
    // Access bytes in mapped; do not assume the entire file is already resident.
}
~~~

This is an illustrative snippet; `path` must exist, `size` must be valid within mapping buffer limits, and `MappedByteBuffer`, `FileChannel`, and `StandardOpenOption` must be imported. To process a file larger than a single `ByteBuffer`'s addressable limit, map across multiple windows or use chunked `read`/`write`. Never try to map a multi-terabyte file into a single buffer expecting `capacity()` to hold more than an `int` range.

### When to Use Mapped Files?

Memory mapping can be useful for random access, large indexes, or repeated access across multiple file regions with suitable patterns. However, for a file only needing a single sequential copy, `FileChannel.read` or `transferTo` can be simpler and sometimes faster; measure in practice.

Mapped buffers also introduce distinct concerns: page cache control, mapping lifecycle, truncation races, virtual memory address usage, and metadata/durability flushing. `MappedByteBuffer.force()` requests writing changes in the mapped region to storage per the API contract; it is not a transaction and does not apply identically to all direct buffers.

## 13. Observing Direct Memory via BufferPoolMXBean

The Java Management API provides `java.lang.management.BufferPoolMXBean` to observe VM-managed buffer pools. You can retrieve the list via:

~~~java
for (BufferPoolMXBean pool : ManagementFactory.getPlatformMXBeans(
        BufferPoolMXBean.class)) {
    System.out.printf("%s: count=%d, capacity=%d, used=%d%n",
            pool.getName(),
            pool.getCount(),
            pool.getTotalCapacity(),
            pool.getMemoryUsed());
}
~~~

This is an illustrative snippet requiring imports `BufferPoolMXBean` and `ManagementFactory`, suitable for placement inside a method. Common pool names on HotSpot include `direct` and `mapped`, though the set of names/counters is specific to the implementation and JDK version.

- `getCount()`: number of buffers managed by the pool.
- `getTotalCapacity()`: sum of `capacity` of buffers in the pool in bytes.
- `getMemoryUsed()`: estimated bytes of memory used by the pool, which can differ from capacity due to management/native alignment. **The value may be -1** if the implementation lacks a measurement.
- These metrics **do not cover all native memory**. JNI `malloc`, thread stacks, or C library allocations may not be included in the direct buffer pool.
- Numbers can fluctuate due to GC/cleaners, temporary direct buffer caches, I/O activity, and sampling timing.

Use these metrics alongside heap metrics, GC logs, and RSS/container metrics instead of relying on one counter to decide whether an issue is a leak or a workload peak.

### Native Memory Tracking (NMT)

Some HotSpot builds offer **Native Memory Tracking**, enabled on JVM startup like:

~~~bash
java -XX:NativeMemoryTracking=summary -Xmx512m MyApplication
~~~

You can then run a JDK tool like `jcmd <pid> VM.native_memory summary` on an eligible process if configuration and permissions allow. This is an illustrative command with a placeholder PID, not a measurement result for the demo program.

NMT categorizes many JVM-tracked allocations, yet **is not a system for tracking every native allocation made by libraries outside the JVM**. RSS, procfs, container metrics, native profilers, and allocation tracing may be required to track regions outside its scope.

## 14. Reading OOME Symptoms and Memory Pressure

Some symptoms:

| Symptom | Possibilities to check | Investigation direction |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Heap objects/arrays exceed `-Xmx` | Heap dump, GC logs, object retaining paths |
| OOME related to `direct buffer memory` | Direct buffer allocations exceed budget or aren't freed in time | `BufferPoolMXBean`, pool leases, `MaxDirectMemorySize`, retention |
| Container killed without a clear Java stacktrace | Total RSS/cgroup memory exceeded limit | Container events, RSS, page cache, heap+native budget |
| Low heap yet high RSS | Direct/native/mmap/code cache/thread stacks | JMX buffer pools, NMT, OS profiler |
| Heavy GC activity as direct allocations rise | Native cleanup/allocator pressure or heap refs | GC logs, allocation profile, object references |
| Latency rises under high load | Pool exhaustion, allocation cost, page faults, missing backpressure | Per-connection metrics, queue depth, timeouts |
| Large mapped memory yet low heap | Virtual space mapping / file-backed pages | Mapped buffer counters, RSS/maps, page residency |

Seeing direct buffer count rise is not automatically a memory leak. A pool designed to retain buffers up to a high-watermark will cause count to rise and then plateau. A **leak** typically shows buffers/leases/retained references growing without dropping per their expected lifecycle, or held buffers out of proportion to workload.

### Troubleshooting Order

1. Measure heap used/committed/max, GC pauses, and object retention.
2. Measure direct/mapped buffer count/capacity/memory used over time.
3. Measure RSS/process virtual memory and container limit/usage.
4. Inspect actual runtime JVM flags like `-Xmx` and `-XX:MaxDirectMemorySize`.
5. Locate where `allocateDirect` is called heavily or pool leases are not returned.
6. Correlate connection count, leased buffers, pending output, worker queues, and file mapping count.
7. Try bounding concurrent operations and buffer sizes to verify causal relationships.
8. Only after understanding the root cause should you tune memory budgets or allocator structure.

Calling `System.gc()` regularly as a workaround to “clean up direct memory” is an anti-pattern: GC is not a deterministic direct-buffer release API, can add latency, and masks improper buffer management.

## 15. ByteBuffer and Multithreading Safety

`ByteBuffer` is mutable. Heap vs. direct does not change this. Two threads mutating `position/limit` on the same object without ownership/synchronization can corrupt cursors. Two distinct view objects can also share backing bytes, so concurrent writes still risk data races.

Safe options:

- **Thread confinement**: one buffer owned by one event loop/thread at any given time.
- **Per-connection buffers**: each connection has its own input/decoder state and outbound queue.
- **Ownership transfer**: hand the buffer to a worker and do not reuse it until the worker finishes.
- **Copy immutable payloads**: copy small byte slices into a dedicated `byte[]` or immutable object to reduce coupling.
- **Read-only views**: prevent writes through that view while still ensuring no writable alias mutates from another thread.
- **Partitioned buffer slices**: two views over non-overlapping byte regions can be safer when ownership is well-defined; shared storage and shared lifetime still need full management.

In particular, when a buffer is handed to `AsynchronousFileChannel` or an async I/O API, never mutate contents/position or return it to a pool before the operation completes. Prematurely reusing a buffer can cause bytes written to file to differ from the original payload without throwing any exception.

## 16. When to Choose Which Buffer Type?

| Scenario | Reasonable starting point | What to test |
| --- | --- | --- |
| Java parser handling small bytes, needs `byte[]` | Heap `ByteBuffer.allocate` or byte array | Allocation/GC, parser throughput |
| High-throughput Socket/FileChannel, reused buffers | Bounded pool of direct `ByteBuffer`s | Native memory pressure, copy count, throughput |
| Very small, ultra-short-lived requests | Heap buffer, or an appropriate pool | Whether direct allocation cost outweighs benefits |
| Very large sequential file copy | `FileChannel` streaming, consider `transferTo` | Copy path, OS/filesystem behavior |
| Random access in a large file | Windowed `MappedByteBuffer` or positional `FileChannel` reads | Page faults, map lifetime, truncation risk |
| Many slow clients | Bounded queues/buffers and backpressure | Memory per connection, high/low watermarks |
| Cross-language library requiring `byte[]` | Heap or explicit copy from direct | Total copies and API integration |
| Low container memory | Set heap and native budgets; measure directly | RSS, direct pool metrics, OS kills |

**Do not choose direct just because of the word “performance.”** When both source and consumer work with heap objects/arrays, direct buffers can increase copies. When native I/O repeats heavily on the same buffers, direct can help. Decide based on measurements.

## 17. Realistic Benchmarking: Avoid Wrong Conclusions

An NIO benchmark should measure:

1. **Warmup/JIT**: avoid comparing unoptimized cold code against warmed code.
2. **Allocation path**: separate direct/heap allocation speed from read/write speed when buffers are reused.
3. **Real I/O**: use file sizes, access patterns, storage, and concurrency close to production.
4. **Cold vs. warm page cache**: the first read may measure storage while later reads measure cache.
5. **GC + native stats**: high throughput coupled with OOMEs or latency spikes is not a good result.
6. **CPU, RSS, and memory bandwidth**: copy costs, context switches, and page faults can change.
7. **Buffer size**: test multiple sizes, e.g. ranges around 8 KiB, 64 KiB, 1 MiB on your workload; do not treat one size as universally optimal.
8. **Overload scenarios**: slow clients, large files, high request rates, full queues, cancellation.
9. **JMH for CPU microbenchmarks** and a dedicated I/O harness for end-to-end benchmarks; do not generalize from a single `System.nanoTime()` loop.

If a benchmark uses `ByteArrayOutputStream` as the destination, it does not test real `FileChannel`/`SocketChannel` behavior and cannot confirm native I/O benefits of direct buffers. If data sits entirely in the page cache, results cannot represent cold disk.

## 18. Design and Operations Checklist

- [ ] Distinguished heap limits, direct buffer limits, and total container/RSS budget?
- [ ] Known max concurrent connections/operations and maximum retained buffers?
- [ ] Defined capacity per buffer, size classes, and queue bounds?
- [ ] Implemented backpressure when producers outpace consumers?
- [ ] Ensured `flip/clear/compact` match data state, without treating `clear()` as freeing memory?
- [ ] Clarified which views share backing storage and pool lease lifecycles?
- [ ] Prevented buffer reuse before async/partial writes complete?
- [ ] Added metrics for `direct`/`mapped` buffer pools and RSS/container memory?
- [ ] Accounted for mapped pages, thread stacks, metaspace, and native libraries, not just heap?
- [ ] Checked error paths and cleanup for native allocations, channel closes, and mapping lifecycles?
- [ ] Benchmarked realistic workloads comparing heap/direct/mapped/transfer approaches?
- [ ] Enforced large-file bounds instead of loading all bytes into one array or direct buffer?
- [ ] Avoided `System.gc()`/reflection/private Cleaner APIs as default workarounds?
- [ ] Considered stale data risk when leasing buffers across requests/tenants and whether zeroization is needed?
- [ ] Reserved headroom for bursts/GC/JVM/OS instead of summing limits right up to the ceiling?

## 19. Self-Check Questions

1. Does `ByteBuffer.allocateDirect(1024)` allocate a `byte[]` backing array on the Java heap? **No**, it is a direct buffer with backing memory intended for native I/O.
2. What are `direct.isDirect()` and `direct.hasArray()` typically, respectively? **true and false**.
3. What does `hasArray()` usually return on a heap buffer from `ByteBuffer.allocate(1024)`? **true**; however, read-only or special buffers do not necessarily expose an accessible backing array.
4. Does `clear()` on a direct buffer free native memory? **No**, it only resets the cursors.
5. Can a direct buffer remain live after a method scope ends if a view still holds a reference? **Yes**, because lifetime depends on reachability, not lexical scope alone.
6. Why does `duplicate()` not fully isolate data between two threads? Because the view has separate cursors yet **shares the same backing bytes**.
7. Are direct buffers always zero-copy with disk? **No**; benefits depend on the native I/O path, OS, and actual API.
8. What can cause container RSS to be high while heap used is low? Direct/mapped memory, native allocations, thread stacks, code cache, and other categories.
9. Does `BufferPoolMXBean.getMemoryUsed()` cover every JNI `malloc`? **No**; it only reports statistics for the corresponding JVM-managed pool.
10. Does `-XX:MaxDirectMemorySize` give the machine more RAM? **No**; it is an allocation limit/configuration in supporting JVM implementations.
11. Why can a 256 MiB buffer pool hold native memory even when there are no requests? Because the buffers remain reachable via the pool for reuse.
12. When should an output buffer be returned to a pool in non-blocking writes? **After all pending bytes have been transferred / the operation completes**, per the ownership protocol.
13. Does `FileChannel` reading a 100 GiB file need a 100 GiB direct buffer? **No**, use streaming/chunking or windowed mapping.
14. How does `MappedByteBuffer` differ from `allocateDirect`? It maps a **file region** through the OS memory-mapping mechanism and has a different lifecycle/page residency model.
15. Is `FileChannel.transferTo` just another name for `allocateDirect`? **No**, it is an API for transferring bytes between channels that may use different optimizations.
16. If an output queue grows without bound, can adding more direct buffers permanently fix it? **No**; you need backpressure and bounded queues.
17. Is a Java heap dump enough to explain every native leak? **No**, you need buffer pool/NMT/OS metrics and corresponding reference analysis.
18. Should you benchmark once on a small file after JIT and conclude direct is better than heap? **No**, you must test diverse workloads, allocation patterns, and native memory behavior.
19. If a direct buffer comes from a pool and a `slice()` is still being read by a worker, is it safe to return the root to the pool immediately? **No**, the alias still references the same backing storage.
20. What is the most important practice with direct memory? **Bound capacity × concurrency × lifetime, enforce ownership, measure native memory, and use direct only when benefits are verified**.

## API Reference Documentation

- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `allocate`, `allocateDirect`, `isDirect`, `hasArray`, views, and buffer cursor semantics.
- [Java SE 17 — Buffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): `position`, `limit`, `capacity`, `flip`, `clear`.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `read/write`, `map`, `transferTo/transferFrom`.
- [Java SE 17 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): `force`, mapping-backed memory, and synchronization.
- [Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): `getCount`, `getMemoryUsed`, and `getTotalCapacity`.
- [Java SE 17 — ManagementFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): retrieving platform management beans.
- [Oracle Java Troubleshooting Guide — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): HotSpot native memory observation tools.
