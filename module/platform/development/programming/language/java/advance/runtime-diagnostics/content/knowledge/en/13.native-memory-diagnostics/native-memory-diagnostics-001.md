# 13.1. Distinguishing Reserved Address Space, Committed Memory, and RSS

## Objectives

After this lesson, you will:

- Distinguish **reserved virtual address space**, **committed memory**, and **Resident Set Size (RSS)**.
- Understand why a JVM with a multi-GiB `-Xmx` can still have a small RSS, and why RSS can be higher than NMT committed.
- Correctly read Native Memory Tracking (NMT), heap metrics, Linux `VmSize`/`VmRSS`/`smaps_rollup`, and container memory.
- Combine metrics to investigate native memory growth, memory pressure, or OOM without confusing "address reserved", "committed", and "resident in RAM".

Java examples run on **Java 17+**. The `/proc` and cgroup commands are for **Linux**; OS metric names and meanings vary by platform.

## 1. Three Memory Measurement Layers Are Three Different Questions

### 1.1. Reserved: How Much Virtual Address Space Has the JVM Reserved?

**Reserved** means a range in the process's **virtual address space** has been set aside for a purpose. It does not by itself prove that a corresponding amount of physical RAM is in use.

For example, with `-Xmx4g`, HotSpot typically **reserves** a virtual address region near 4 GiB for the maximum Java heap. If the JVM has just started and the heap only needs a few hundred MiB, most of the reserved region does not need to be committed or touched yet. On 64-bit systems, the virtual address space is large, so a reservation of several GiB can be normal.

Regions that can reserve significant address space include the Java heap, compressed class space, code cache, platform thread stacks, and GC-related mappings. A class space reserving 1 GiB up front does **not** mean class metadata is consuming 1 GiB of RAM.

Reserved still carries **virtual address** costs and limits. 32-bit processes, virtual memory limits (`ulimit -v` on Linux), memory overcommit policies, address space layout/fragmentation, or other mappings can cause a reservation to fail even when the machine still has free RAM. Thus, "not consuming RAM immediately" does not mean "never carries risk".

### 1.2. Committed: The Portion the JVM Has Prepared for Use

In **HotSpot Native Memory Tracking (NMT)**, `committed` reflects the memory that the JVM has committed/allocated so it can be used. For mappings, it is typically the portion brought into usable state from a reserved region; for `malloc` allocations tracked by NMT, the allocated size is typically counted as both reserved and committed.

Key points:

- **Committed does not mean resident.** The OS may use *demand paging*: pages are backed by RAM when accessed (*first touch*), rather than allocating full RAM immediately when the JVM commits them.
- Pages that have been used can be moved to swap or reclaimed depending on the OS/policy; committed is still not a snapshot of bytes of RAM currently held by the process.
- For the same NMT region, normally `reserved >= committed`. However, this committed figure is **not total process RAM**.
- The term "committed" can mean different things at the OS level: **HotSpot NMT committed** is not the exact same number as Windows *Commit Size* or Linux `Committed_AS`.

Do not confuse committed with **Java heap used**. Heap committed is the portion the JVM has allocated for the heap; heap used is the portion currently holding objects at a given time and is usually lower. The JVM may continue holding committed heap after garbage collection frees objects.

### 1.3. RSS: Which Pages Are Currently in Physical RAM?

**Resident Set Size (RSS)** is the amount of a process's pages **currently present in physical RAM** at the time of measurement.

On Linux, `VmRSS` is composed of three groups:

```text
VmRSS = RssAnon + RssFile + RssShmem
```

- **RssAnon**: anonymous resident pages, such as heap and stacks.
- **RssFile**: resident pages of file mappings, such as shared library code and memory-mapped files.
- **RssShmem**: resident pages of shared memory.

RSS **includes shared pages** mapped into the process, so not all of it represents exclusive private RAM. If two JVMs use the same library page, it may be counted in the RSS of both. When you need to apportion shared memory proportionally, use **PSS (Proportional Set Size)** in `smaps_rollup`.

RSS does not include pages currently swapped out of RAM. The `VmRSS` fields in `/proc/<PID>/status` are quick figures and may not be completely exact when reconciled at the page level; `/proc/<PID>/smaps_rollup` provides a more useful breakdown for detailed analysis.

## 2. How Reserve, Commit, and Resident Relate

For **a single mapping region** in a simplified model:

```text
Reserve address range
    |
    +--> JVM has a virtual address range set aside for the memory region
            |
            v
         Commit
            |
            +--> portion of memory made usable by JVM/OS
                    |
                    v
                Access / first touch
                    |
                    +--> OS brings needed pages into RAM
                          (later may be reclaimed/swapped)
```

This is a **process flow model**, not a direct conversion formula between counters. The OS may preallocate, map files, use shared pages, perform copy-on-write, or change resident status after commit. Distinguish carefully:

- **NMT reserved / committed:** reported within the scope of allocators tracked by **HotSpot NMT**.
- **Linux VmSize / VSZ / VIRT:** size of the **entire virtual address space** of the process according to the OS.
- **Linux VmRSS / RSS:** pages of the **entire process** currently resident, including file mappings and shared pages.

NMT does not cover every allocation in the process (in particular, it can miss third-party/JNI native libraries and some JDK library components). Therefore, **NMT reserved does not have to equal VmSize**, and **NMT committed does not have to be larger or smaller than RSS**.

### An Illustrative Snapshot

| Metric | Hypothetical Value | What Does It Mean? |
|---|---:|---|
| NMT Java Heap reserved | 4,096 MiB | Virtual addresses reserved for maximum heap |
| NMT Java Heap committed | 512 MiB | Portion of heap committed |
| NMT Total reserved | 5,400 MiB | Total NMT-tracked regions reserved |
| NMT Total committed | 760 MiB | Total NMT-tracked regions committed |
| Linux VmSize | 7,100 MiB | All mappings/virtual addresses of the process |
| Linux VmRSS | 630 MiB | Currently resident pages according to the OS |

These values **can completely coexist**. Do not compute `5,400 - 630` MiB and call the result "reserved RAM not yet used". Likewise, do not treat `760 - 630` MiB as "swap" or leaked memory: they measure different scopes.

Several scenarios:

- **Reserved increases, RSS stays nearly flat:** the JVM just reserved more address space, without necessarily using more RAM.
- **Committed increases, RSS has not increased correspondingly:** pages were committed but not yet touched, or the OS handles backing differently.
- **RSS increases, NMT committed does not increase:** previously committed pages were just touched; or library/native allocator/mmap allocations outside NMT scope grew.
- **RSS is larger than NMT committed:** file mappings, shared pages, or allocations from components not tracked by NMT may contribute to RSS.
- **RSS is smaller than NMT committed:** committed portions are not yet resident, were swapped/reclaimed, or follow different accounting rules.

## 3. Placing Next to Java Heap Metrics

| Metric | Scope | What Not to Infer |
|---|---|---|
| `-Xmx` / `Runtime.maxMemory()` | Maximum heap limit the JVM can use | Not a whole-process RSS limit |
| `-Xms` | Initial heap size requested | Does not guarantee startup RSS equals this value |
| `Runtime.totalMemory()` / heap `MemoryUsage.committed` | Portion of Java heap allocated by the JVM for use | Not every page in that portion is resident |
| Heap `used` / `totalMemory() - freeMemory()` (approx.) | Heap memory currently in use | Excludes native memory of many subsystems |
| NMT `Total committed` | Regions tracked by HotSpot NMT | Not OS RSS or all native allocations |
| Process `RSS` | Resident RAM pages of the whole process | Not private-only memory, excludes swap |

In a `-Xms256m -Xmx4g` setup, the JVM may reserve nearly 4 GiB for the heap while initially committing only a few hundred MiB, depending on collector and configuration. After GC, **heap used** drops, but **heap committed** may not drop immediately because the JVM retains that region for future allocations. Consequently, process RSS may remain high.

Components outside the Java heap include **metaspace**, code cache, GC structures, JIT compiler, native thread stacks, **DirectByteBuffer**, memory-mapped files, JNI/native libraries, and C/C++ allocators. The `-Xmx` limit applies only to the heap, not to total JVM/process/container memory.

For threads, a **platform thread** stack may reserve a larger virtual region than the pages actually used. Virtual threads do not map one-to-one to OS stacks; do not multiply the number of virtual threads by platform thread stack size to predict RSS.

## 4. Viewing Reserved and Committed with HotSpot Native Memory Tracking

**Native Memory Tracking (NMT)** is a HotSpot diagnostic feature that groups allocations into categories such as `Java Heap`, `Class`, `Thread`, `Code`, `GC`, `Compiler`, `Internal`, and `Other`. NMT includes Java Heap inside `Total`; do not misread "NMT Total" as "native **outside** Java heap".

NMT is **disabled by default** and must be enabled at JVM startup:

```bash
# Choose one of the two modes:
java -XX:NativeMemoryTracking=summary -jar app.jar
java -XX:NativeMemoryTracking=detail  -jar app.jar
```

`summary` aggregates by subsystem; `detail` adds allocation site/memory region information and incurs higher overhead. According to Oracle documentation, enabling NMT can increase execution overhead by roughly **5–10%** depending on the workload. NMT cannot be enabled via `jcmd` mid-lifecycle for a process started with NMT disabled.

Once you have the PID (obtained via `jcmd -l` or OS tools):

```bash
jcmd -l
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline

# After running a workload over an observation interval:
jcmd <PID> VM.native_memory summary.diff scale=MB
```

Replace `<PID>` with the actual PID. You can use `detail`/`detail.diff` when starting with `detail` level. Take the baseline **after warm-up** if the goal is to detect abnormal native memory growth.

A report has the following general structure (**numbers are illustrative only**):

```text
Native Memory Tracking:

Total: reserved=5400MB, committed=760MB
- Java Heap (reserved=4096MB, committed=512MB)
- Class     (reserved=1024MB, committed=24MB)
...
```

How to read it properly:

1. High `reserved` with low `committed` in `Java Heap` or `Class` may simply be pre-designed reservation.
2. `mmap`, `malloc`, and `arena` inside a category are **breakdowns** of allocations, not amounts to add on top of `Total`. NMT `Total` also **already includes Java Heap**.
3. `summary.diff` shows changes **visible to NMT**; it is not guaranteed to capture native allocations from third-party/JNI libraries, certain JDK libraries, or all class data sharing regions.
4. NMT provides evidence about JVM allocations; **it does not directly measure OS RSS**. To draw conclusions about RAM, combine it with OS tools.

When you see NMT committed rising, identify **which category is growing**. GC, JIT, or class loading can grow during warm-up and then stabilize. Growth across multiple identical workload cycles, after the system has reached steady state, is more worth investigating than a one-time startup increase.

## 5. Measuring VmSize, RSS, PSS, and Swap on Linux

### 5.1. Cross-Checking Process Metrics

Set the actual PID in a Bash variable:

```bash
PID=12345

ps -p "$PID" -o pid,vsz,rss,comm
grep -E '^(VmSize|VmRSS|RssAnon|RssFile|RssShmem|VmSwap):' "/proc/$PID/status"
```

**Replace 12345 with the actual JVM PID.** `VSZ`/`RSS` in `ps` on Linux are typically reported in KiB. `VmSize`/`VmRSS` in `status` also display units. `VmRSS` is an estimate of resident size; `VmSwap` reflects a swapped scope of the process, not the remainder of `VmSize`.

Do not compute `VSZ - RSS` and call it "free RAM of the JVM". That is merely the difference between virtual address size and OS-reported resident memory; it does not directly tell you how much RAM can still be allocated.

### 5.2. When You Need Private/Shared and PSS

```bash
PID=12345

grep -E '^(Rss|Pss|Private_Clean|Private_Dirty|Shared_Clean|Shared_Dirty|Swap):' "/proc/$PID/smaps_rollup"
```

- `Rss`: total resident pages across mappings.
- `Pss`: resident memory apportioned by sharing ratio, useful when comparing multiple processes.
- `Private_Clean`/`Private_Dirty`: pages belonging exclusively to the process; `Shared_Clean`/`Shared_Dirty`: shared pages.
- `Swap`: swapped pages within the counter's scope.

`smaps_rollup` is a more convenient way to read the breakdown than `smaps` when you only need totals; however, it still has query overhead and may require appropriate permissions. OS figures can change continuously due to workload and kernel activity, so sample near the same point in time when cross-referencing.

### 5.3. Container Memory Does Not Equal Java RSS

In **cgroup v2**, `memory.current` counts memory charged to the cgroup, which can include anonymous memory, page cache, kernel structures, and memory of **multiple processes**. It is not Java's RSS alone.

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
```

These paths are common in containers using cgroup v2; in practice they depend on cgroup location and namespaces. If a container is OOM-killed, examine **cgroup usage/limit/events**, heap, NMT, RSS/PSS, page cache, and other processes in the same cgroup. The JVM can hit the container limit even when heap `used` is still low.

**Windows/macOS:** Metrics like *Virtual Size*, *Working Set*, and *Commit Size/Private Bytes* have their own OS contracts. Windows *Commit Size* is not HotSpot NMT `committed`; working set can include shared pages. Always record the OS, tool, and exact metric name when comparing across environments.

## 6. Java Experiment: Java Heap and Direct Native Buffer

This example prints the limit/committed/used of the **Java heap**, then allocates a 64 MiB `DirectByteBuffer` outside the heap. The program writes at every 4 KiB interval to touch the buffer's pages, then pauses so you can measure NMT/RSS from another terminal.

Create **`NativeMemoryLayersDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;

public class NativeMemoryLayersDemo {
    private static final int MIB = 1024 * 1024;

    public static void main(String[] args) throws IOException {
        Runtime runtime = Runtime.getRuntime();
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Heap max MiB: " + runtime.maxMemory() / MIB);
        System.out.println("Heap committed MiB: " + runtime.totalMemory() / MIB);
        System.out.println("Heap used approx MiB: "
                + (runtime.totalMemory() - runtime.freeMemory()) / MIB);

        ByteBuffer direct = ByteBuffer.allocateDirect(64 * MIB);
        for (int offset = 0; offset < direct.capacity(); offset += 4096) {
            direct.put(offset, (byte) 1);
        }

        System.out.println("Direct buffer touched: 64 MiB");
        System.out.println("Press Enter to exit.");
        System.in.read();
        System.out.println("First direct byte: " + direct.get(0));
    }
}
```

Compile/run on Java 17+:

```bash
javac NativeMemoryLayersDemo.java
java -Xms64m -Xmx256m -XX:NativeMemoryTracking=summary NativeMemoryLayersDemo
```

This example was compiled and run with **OpenJDK 24**. PID, heap committed, and heap used may vary across runs/JDKs. One test run printed `Heap max MiB: 256` and `Heap committed MiB: 66`; these values are **not fixed stdout**. The following lines are stable:

```text
Direct buffer touched: 64 MiB
Press Enter to exit.
First direct byte: 1
```

While the program pauses at "Press Enter", open another terminal and substitute the PID:

```bash
jcmd <PID> VM.native_memory summary scale=MB

# Linux only:
grep -E '^(VmSize|VmRSS|RssAnon|RssFile|RssShmem):' /proc/<PID>/status
grep -E '^(Rss|Pss|Private_Dirty|Swap):' /proc/<PID>/smaps_rollup
```

In these illustrative commands, `<PID>` is a **placeholder to replace** with the PID number; in Bash you can write `/proc/$PID/status` after assigning the `PID` variable as in section 5.

Observations:

- `Heap max` is close to `-Xmx`, while `Heap committed` can be noticeably smaller.
- The direct buffer lives **outside the Java heap**, so heap `used` does not increase by 64 MiB.
- Touching pages can raise resident memory, but **does not guarantee RSS increases by exactly 64 MiB**: the outcome depends on page size, allocator, prior page state, RSS accounting, and other JVM activity.
- NMT may record native allocations for certain allocation paths; the **specific category depends on the JDK**, and NMT must not be treated as a complete counter for every direct/JNI/native library allocation.
- The `direct` variable is still used after the pause, so the buffer remains reachable during observation. Press **Enter** so the program prints `First direct byte: 1` and exits.

This example intentionally touches the entire buffer to demonstrate paging. In real applications, do not arbitrarily touch every page just to push RSS up.

## 7. Analyzing Measurements by Symptom

| Observation | Investigation Direction | Data to Collect |
|---|---|---|
| Very large `VmSize`/`VSZ`, small RSS | Possible large heap/class-space/stack reservation or collector-specific mappings | NMT reserved/committed by category, `/proc/<PID>/maps` |
| Reserved jumps sharply, committed stable | JVM just reserved address space | NMT diff, virtual address limits |
| Committed rises, RSS does not change immediately | Not yet first-touched or different paging behavior | NMT diff, RSS/PSS over time, page faults |
| RSS rises, NMT committed barely changes | Previously committed pages just touched, mmap/native library outside NMT, allocator caching | `smaps_rollup`, OS profiler, native allocation tracing |
| Heap `used` drops after GC, RSS stays high | Heap still committed, native allocator retaining memory, other direct/mapped memory | Heap committed, NMT categories, RSS/PSS after GC |
| Java heap not large but container OOMs | Off-heap/native, page cache, kernel memory, other processes, cgroup limit | `memory.current`/`memory.stat`/`memory.events` and JVM metrics |
| NMT category grows across multiple workload cycles | Legitimate native growth or leak | Post-warm-up baseline, identical load, NMT detail/call sites |
| NMT flat while RSS climbs steadily | Untracked NMT regions or committed pages becoming resident | OS maps/smaps, JNI/native profiler, shared/file mappings |

To identify a leak, track the **trend after warm-up across multiple equivalent workload cycles**. JIT compilation, class loading, pools, caches, and GC can legitimately raise memory at first and then plateau. A single high snapshot is not enough to conclude a leak.

## 8. Eight Common Misconceptions

1. **"Reserved 8 GiB = occupying 8 GiB of RAM."** False: reserved primarily refers to address space.
2. **"NMT committed is 2 GiB so RSS must be exactly 2 GiB."** False: NMT scope and OS resident scope differ; committed pages may not be resident, and RSS may include pages NMT does not track.
3. **"RSS is private memory of a single process."** False: RSS can count shared pages across processes; PSS and private breakdowns help when apportioning.
4. **"`-Xmx512m` means the JVM cannot use more than 512 MiB in a container."** False: beyond the heap there are metaspace, stacks, GC, JIT, direct memory, JNI, etc.
5. **"After GC, RSS must drop."** False: the heap/allocator may keep committed regions for reuse; the OS also governs residency.
6. **"If NMT is not growing, there is definitely no native leak."** False: NMT does not fully track third-party native libraries and every allocation.
7. **"`VmSize - VmRSS` is free RAM remaining."** False: subtracting resident size from virtual size is not a measure of usable RAM left.
8. **"Linux `Committed_AS` is the same as NMT committed."** False: `Committed_AS` is a system-wide commit charge estimate used by the kernel for overcommit accounting; NMT is per-JVM accounting.

## 9. Memory Diagnostics Checklist

1. **Identify the scope:** Java heap, HotSpot NMT, entire OS process, or container/cgroup?
2. **Align timing and units:** KiB/MiB/GiB; same PID, timestamp, workload; snapshot vs. diff.
3. **Label accurately:** reserved (virtual addresses), committed (allocation/commit level), heap used, RSS/PSS (resident), swap.
4. **Inspect each NMT category**; remember `Total` already includes `Java Heap` and sub-lines must not be double-counted.
5. **When process RSS/OOM is abnormal:** cross-check heap, native allocators, mapped files, shared memory, cgroup, and native code.
6. **To identify a leak:** take baseline after warm-up, repeat workload, check if growth persists after GC and after load stops.

### Self-Check

- With `-Xms256m -Xmx4g`, why can NMT Java Heap reserved be near 4 GiB while committed/RSS are small?
- Why can RSS be **higher** than NMT Total committed and also **lower**?
- When heap used drops after GC but RSS stays flat, what additional data should you inspect?
- Why does summing the RSS of two JVMs sharing a library not equal the sum of their private memory?
- If a container is OOM-killed despite low Java heap used, which non-heap regions should you investigate?

## Official Documentation

- [Oracle Java SE 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html): NMT summary/detail, tracking scope, baseline, and limitations.
- [Oracle Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.native_memory`, `summary.diff`, `scale`.
- [Oracle Java SE 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): NMT categories and investigation methods.
- [Linux kernel — `/proc` filesystem](https://www.kernel.org/doc/html/latest/filesystems/proc.html): `VmSize`, `VmRSS`, `RssAnon`, `RssFile`, `RssShmem`, `smaps_rollup`, and PSS.
- [Linux kernel — cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `memory.current`, `memory.stat`, `memory.events`.
