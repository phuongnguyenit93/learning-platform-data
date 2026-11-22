# MappedByteBuffer.load(), isLoaded(), and Page Fault Impact

## 1. Understanding Memory-Mapped Files Properly

In Java NIO, `FileChannel.map(...)` creates a `MappedByteBuffer` to access a file region as memory. The mapped region resides in the process's **virtual address space**. This does not mean all bytes are immediately copied into RAM.

When reading `mapped.get(index)`, the OS determines whether the page containing the data is in physical memory and properly mapped. If not, a **page fault** may occur; the kernel handles the event, potentially fetching data from cache or performing device I/O before the CPU resumes the access.

Key concepts:

- **Mapping:** association between virtual addresses and the contents of a file region.
- **Resident page:** a data page currently present in physical memory.
- **Page fault:** an event triggered by virtual memory mechanics asking the kernel to resolve a page/mapping.
- **`load()`:** attempts to load the mapped buffer's contents into physical memory (best-effort).
- **`isLoaded()`:** responds with a hint about residency status, not a guarantee.

The last two methods are our main focus. **`load()` does not promise to eliminate future page faults; `isLoaded()` does not promise an infallible residency verdict.**

## 2. Why Do Page Faults Occur After Calling map?

Illustrative example:

~~~java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    MappedByteBuffer mapped =
            channel.map(FileChannel.MapMode.READ_ONLY, 0, channel.size());
    byte first = mapped.get(0);
}
~~~

The snippet above **is not a standalone program**: it requires a valid `Path path`, necessary imports, and a file size within mapping limits. After `map`, the OS may have set up mapping metadata without yet bringing all contents into RAM.

Typical access flow:

~~~text
FileChannel.map(...)
     |
     v
Virtual address <-> file data region
     |
     v
mapped.get(offset)
     |
     +-- Page is resident and mapped --> Fast CPU read
     |
     +-- Page requires page fault -------+
                                         |
                         Kernel handles mapping/page
                              |          |
                      Data in RAM    Needs I/O from storage
                              |          |
                              +----+-----+
                                   |
                           Read instruction resumes
~~~

This is a conceptual diagram. A valid page fault is normally resolved by the kernel and the program continues; a page fault does not mean Java throws an `Exception`.

### 2.1. Minor vs. major page faults

- **Minor/soft page fault:** requires updating mapping state while the data is already in memory, e.g., in the **OS page cache**; does not necessarily require disk reads.
- **Major/hard page fault:** requires waiting for I/O so the data page can be supplied; can cause much higher latency.
- **Already resident page:** the CPU can access it without a new fault at that instant.

Exact classification and counters are OS-specific. **Not every fault is a physical disk read**; the page cache, filesystem readahead, and other applications may already have the data in RAM.

### 2.2. Mapping, heap, and page cache

`MappedByteBuffer` is a **direct byte buffer** representing a mapped file region, unlike creating a `byte[]` on the Java heap via `Files.readAllBytes`. When mapping a file, the kernel may defer bringing data into physical memory until first access. The OS may also automatically readahead subsequent pages when sequential access is detected.

Using `MappedByteBuffer` does not bypass virtual memory, does not automatically pin RAM, and does not make data immune to eviction.

## 3. Exact Contract of MappedByteBuffer.load()

Java 17 defines:

~~~java
public final MappedByteBuffer load()
~~~

Per the Javadoc, the method makes a **best effort** so that the buffer's contents are resident in physical memory when it returns. It may itself trigger **page faults and I/O** during the call.

What you may expect:

1. The system will attempt to prepare the pages of the mapped buffer region.
2. The call may take time due to data loading; it is an active prefetch/warm-up step.
3. The method returns **the buffer itself** so calls can be chained.

What is **not** guaranteed:

1. All pages are actually resident after the call.
2. Pages will remain in RAM when the application accesses them later.
3. Subsequent `get` operations will have zero page faults.
4. The call will be fast or improve end-to-end performance for every workload.
5. Data pages are permanently locked in RAM.
6. Modified contents have been durably saved to the device.

Example:

~~~java
MappedByteBuffer mapped =
        channel.map(FileChannel.MapMode.READ_ONLY, offset, length);

// Preload in advance: best-effort page-in.
mapped.load();

// No guarantee that the operation below will not fault.
byte value = mapped.get(0);
~~~

This is illustrative code requiring a `FileChannel channel` and appropriate `long offset` and `long length` variables.

`load()` neither allocates a `byte[]` nor modifies file contents. Nor is it `MappedByteBuffer.force()`; `force()` relates to flushing modifications to storage.

## 4. Exact Contract of MappedByteBuffer.isLoaded()

Java 17 defines:

~~~java
public final boolean isLoaded()
~~~

`isLoaded()` returns a **hint** as to whether the mapped buffer's contents are in physical memory:

- If **`true`**: it is highly likely the entire buffer's contents are resident and many accesses may proceed without faults/I/O.
- If **`false`**: **does not prove** data is absent from RAM. The OS/provider may use heuristics or decline to assert residency.
- For **both outcomes**: immediately after the method returns, the OS may page out or evict some data. There is no guarantee for the next access.

Bad example to avoid:

~~~java
mapped.load();
if (!mapped.isLoaded()) {
    throw new IllegalStateException("load thất bại");
}
~~~

This is an **anti-example**: returning `false` after `load()` is completely valid under the Java contract. Do not treat these two methods as a success/failure verification protocol.

### 4.1. All value pairs are valid

| isLoaded before load | isLoaded after load | Valid? | Why? |
|---|---|---|---|
| `false` | `true` | Yes | Pages may have been better prepared |
| `true` | `true` | Yes | Data may already have been resident |
| `false` | `false` | Yes | Best-effort does not require the hint to become true |
| `true` | `false` | Yes | Status changed or hint is unstable |

**Do not use `isLoaded()` to infer page fault counts, file read errors, access permissions, or file content integrity.** It is only a point-in-time hint about memory residency status.

### 4.2. If it can't verify residency, why does this API exist?

`isLoaded()` can help observe the **informational** status of a mapping, e.g., for statistics or warm-up diagnostics. It does not replace measuring latency, I/O, RSS, or OS fault counters. A program can still read data successfully even if `isLoaded()` returns `false`.

## 5. How Do Page Faults Affect Latency?

### 5.1. Demand paging: deferring cost until use

~~~text
map ----------------------> get(page A)
                               |
                               +-- Resident: usually fast
                               |
                               +-- Fault: OS must handle,
                                          may wait for I/O
~~~

If an application is latency-sensitive, page fault costs can land right on the critical path of an important request. However, the first read is not always slow: the file may already sit in the page cache.

### 5.2. Preload: shifting part of the cost to warm-up

~~~text
map --> load() --> page faults/I/O may occur --> main processing --> get(page A)
             (warm-up)                                          (may be faster)
~~~

If pages stay resident, subsequent accesses can be faster. Yet I/O cost may simply be **shifted earlier**, not eliminated. The OS can reclaim pages in between, causing `get` to still fault.

### 5.3. Preloading for the wrong workload can be worse

If a file is very large while queries only touch a few pages, loading the entire region wastes I/O, increases page cache pressure, and adds needless startup delay. For sparse random access, demand paging can be more efficient.

Therefore, choose `load()` based on **access frequency/pattern, dataset size, available memory, and latency sensitivity** rather than an intuition that "prefetch is always faster."

## 6. Complete Java 17+ Program

The program below creates a temporary file with deterministic data, maps 4,096 bytes at offset 512, checks `isLoaded()` twice, and reads bytes by absolute index.

**File: `MappedLoadDemo.java`**

~~~java
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedLoadDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("mapped-load-", ".bin");
        try {
            byte[] data = new byte[8192];
            for (int i = 0; i < data.length; i++) {
                data[i] = (byte) (i % 251);
            }
            Files.write(file, data);

            try (FileChannel channel =
                         FileChannel.open(file, StandardOpenOption.READ)) {
                MappedByteBuffer mapped =
                        channel.map(FileChannel.MapMode.READ_ONLY, 512, 4096);
                mapped.position(10);

                boolean before = mapped.isLoaded();
                boolean same = mapped.load() == mapped;
                boolean after = mapped.isLoaded();

                System.out.println("capacity=" + mapped.capacity());
                System.out.println("position=" + mapped.position());
                System.out.println("load returns same=" + same);
                System.out.println("first=" + (mapped.get(0) & 0xFF));
                System.out.println("last=" + (mapped.get(4095) & 0xFF));
                System.out.println(
                        "hint before=" + before + ", after=" + after);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run:

~~~bash
javac MappedLoadDemo.java
java MappedLoadDemo
~~~

An actual run on a JDK produced:

~~~text
capacity=4096
position=10
load returns same=true
first=10
last=89
hint before=false, after=false
~~~

**The last line is only the result of a single run.** It could be `false,false`, `false,true`, `true,true`, or `true,false` depending on the environment and timing. Do not write fixed unit tests asserting specific `isLoaded()` values.

Step-by-step explanation:

1. The mapping starts at byte 512 in the file and has `capacity=4096`.
2. `position(10)` sets the relative read position. `load()` does not change position; the two absolute `get(index)` calls do not change position either, so the program prints `position=10`.
3. `load()` returns the same instance, so `same` is `true`.
4. `data[i] = (byte) (i % 251)`. At offset 512, the value is 10; at offset 512 + 4095 = 4607, the value is 89. Masking with `& 0xFF` prints the byte as an unsigned 0–255 value.
5. `isLoaded()` before and after `load()` only yields observations; they do not guarantee that pages remain resident on the next `get`.

**Resource cleanup note:** `MappedByteBuffer` has a mapping lifecycle separate from `FileChannel`; closing the channel does not automatically unmap. On some operating systems, deleting a file while a mapping still exists may be restricted; `Files.deleteIfExists(file)` in `finally` may throw `IOException` depending on the environment. That is a mapping-lifecycle issue, not evidence that `load()` failed.

## 7. Does load Affect the Whole Buffer or Only Remaining Bytes?

`MappedByteBuffer.load()` applies to **the contents of the mapped buffer region** represented by that object, taking no offset/length arguments. Changing `position` and `limit` on the original mapped buffer does not restrict the preload request to `[position, limit)`.

~~~java
mapped.position(100);
mapped.limit(200);
mapped.load(); // not a command to load only the 100 bytes in [100, 200)
~~~

This is illustrative code. To target a sub-region, Java 17 provides `MappedByteBuffer.slice()` and `slice(index, length)`, returning a mapped view of a **subrange**; `load()` on that view affects the sub-region per the Javadoc.

~~~java
// mapped has capacity of at least 8192 bytes:
MappedByteBuffer part = mapped.slice(4096, 4096);
part.load(); // best effort for the contents of part
~~~

The views share contents without copying data to the heap. Slice index and length must lie within the buffer bounds. Alternatively, map a window directly via `FileChannel.map(mode, offset, length)` when appropriate.

`MappedByteBuffer` has an `int` capacity, so `FileChannel.map(MapMode, long, long)` cannot represent a region exceeding `Integer.MAX_VALUE` bytes in one buffer; very large files typically require splitting into multiple windows.

## 8. Distinguishing load, force, and Read Operations

| API / mechanism | Role | Guarantees avoiding future faults? |
|---|---|---|
| `FileChannel.map` | Maps file into virtual address space | No |
| `MappedByteBuffer.load` | Best-effort page-in | No |
| `MappedByteBuffer.isLoaded` | Residency hint | No |
| `MappedByteBuffer.get` | Actually reads bytes | No |
| `MappedByteBuffer.force` | Requests flushing mapping changes to storage | No |
| `FileChannel.force` | Requests flushing channel updates to device | No |
| OS page cache | Caches file contents in RAM | No |

### 8.1. load vs. force

`load()` serves the direction of **preparing data in RAM** for access. `MappedByteBuffer.force()` serves the direction of **writing changes out to the device**, with commitments depending on mapping mode and storage type.

~~~java
// With mapped created using FileChannel.MapMode.READ_WRITE:
mapped.put(0, (byte) 42);
mapped.force();
~~~

The illustrative snippet above is not standalone. `force()` is meaningful for `READ_WRITE`; for `READ_ONLY` or `PRIVATE`, it has no effect in writing shared data to the file. `force()` is also not an application-level atomic transaction mechanism.

### 8.2. load vs. Files.readAllBytes

`Files.readAllBytes` allocates a data array on the Java heap and reads bytes into it. `load()` does not put the file into a `byte[]` array; it asks the OS to try bringing mapping pages into physical memory. Thus do not compare the two approaches solely by Java object allocation count.

## 9. Benchmarking: What Should You Measure?

The same code can yield very different results depending on:

- Cold vs. warm file in the page cache.
- Filesystem readahead, page size, and sequential vs. random access pattern.
- JVM/JIT warmup state, RAM pressure, and concurrent processes sharing data.
- SSD/HDD, network filesystem, container, or VM.
- The difference between minor faults and major faults, and actual I/O cost.

A measurement plan should:

1. Prepare the dataset and at least two policies: demand paging (no `load`) and calling `load` before processing.
2. Record **total time of map + load + read + processing**, alongside the latency of the read phase alone.
3. Test sequential, random, cold, and warm workloads across multiple iterations; report p50/p95/p99.
4. Observe OS page fault counters and disk I/O if tooling is available; do not rely solely on `isLoaded()` as a metric.
5. Check memory pressure and the overhead of preloading sparsely used data.

On Linux, `perf` can be used, for example:

~~~bash
perf stat -e minor-faults,major-faults java MappedLoadDemo
~~~

This command depends on permissions and tool installation; process-level counters **do not equal** the faults of one specific mapped buffer. Windows/macOS require their corresponding tools.

### Should you use load?

| Pattern | Experimentation approach |
|---|---|
| Scanning an entire large region before a latency-sensitive task | Try calling `load` once during warm-up |
| Accessing a few scattered positions in a large file | Try demand paging / small mapping windows |
| Repeatedly reading many times | Measure whether `load` helps once page cache is warm |
| Machine under RAM pressure | Measure eviction, thrashing, and I/O overhead |
| File can be modified/truncated concurrently | Resolve lifecycle safety before optimizing |

## 10. Lifecycle and Risks When the File Changes

Once successfully created, a mapping **does not directly depend on the lifecycle of the `FileChannel` that mapped it**. Closing the channel does not mean immediately unmapping; Java 17 provides no public `MappedByteBuffer.close()` or `unload()` to force release. The mapping persists until the buffer is reclaimed by memory management.

Java 17 warns that a mapped file region **may become inaccessible** if the file is truncated or improperly modified. When accessing an invalid region, the resulting exception may be unspecified and may not occur immediately at the access call. `load()` and `isLoaded()` do not protect an application from file-size changes, race conditions, or filesystem errors.

Do not rely on `System.gc()` to unmap at an exact moment; in production applications, manage file/mapping lifecycles, readers/writers, and safe access invariants properly.

## 11. Common Misconceptions

1. **"map() reads the whole file into RAM."** False: the OS may use demand paging.
2. **"load() guarantees no more faults."** False: it is only best-effort, and pages can be evicted.
3. **"isLoaded() == false means the file is not in RAM."** False: it is only a hint.
4. **"isLoaded() == true proves the next get will be fast."** False: residency status can change.
5. **"Every page fault costs a physical disk read."** False: minor faults can be satisfied from RAM.
6. **"load() replaces force()."** False: they serve page-in and flush, two opposite directions.
7. **"Calling load() more often makes things faster."** False: excessive prefetching can cause extra I/O and RAM pressure.
8. **"position/limit automatically bounds load()."** False: use a mapped slice or windowed map when needed.
9. **"Closing FileChannel makes the mapping vanish."** False: the mapping has its own lifecycle.
10. **"isLoaded() can verify the file wasn't truncated."** False: residency is not access safety.

## 12. Self-Check

**Question 1:** Calling `load()` and still getting `isLoaded() == false` — is that a bug?

**Answer:** No. `load()` is only best-effort and `isLoaded()` is a hint.

**Question 2:** Does a page fault necessarily trigger disk I/O?

**Answer:** No. A minor fault can be resolved using data already in RAM/page cache. Major faults may need to wait for I/O.

**Question 3:** To request writing changes from a `READ_WRITE` mapping to storage, should you call `load()` or `force()`?

**Answer:** `force()` per the write contract, not `load()`.

**Question 4:** Why can loading an entire file while accessing only a few pages be slower than not calling `load()`?

**Answer:** Preloading can read unnecessary data, waste I/O, and evict useful pages from RAM/page cache.

### Official Documentation

- [Java 17: MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html)
- [Java 17: FileChannel.map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#map(java.nio.channels.FileChannel.MapMode,long,long))
- [Java 17: ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
