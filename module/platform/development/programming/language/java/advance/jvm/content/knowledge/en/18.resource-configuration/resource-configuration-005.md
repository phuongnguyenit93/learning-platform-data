# Limiting Metaspace, Direct Memory, and Code Cache Based on Observation Needs

## 1. Why can't configuring these three memory regions rely on a single common number?

In the **HotSpot JVM**, `-Xmx` only limits the **Java heap**, not the entire memory that the Java process can use. Beyond the heap, there is class metadata, off-heap allocated buffers, JIT-generated code, thread stacks, GC structures, JNI/native libraries, and other memory consumers.

The three groups that usually need observation and limit consideration are:

1. **Metaspace:** where HotSpot stores class metadata; affected by the number of classes, class loaders, and the unloading mechanism.
2. **Direct memory:** within the scope of the `-XX:MaxDirectMemorySize` flag, HotSpot's allocation of **NIO direct buffers**; not synonymous with all native memory.
3. **Code cache:** the region storing generated native code/JIT compiled methods and some HotSpot runtime code; can experience pressure when the application has many hot methods.

Each region has its own **growth pattern, observation metrics, limits, and failure manifestations**. Setting `MaxMetaspaceSize=128m`, `MaxDirectMemorySize=128m`, and `ReservedCodeCacheSize=128m` **does not make "non-heap JVM memory" automatically equal 384 MiB**, nor does it mean the total RSS of the Java process is guaranteed to stay below `Xmx + 384 MiB`.

```text
                   Java process address space
    +------------------------------------------------------+
    | Java heap (-Xms, -Xmx)                               |
    |   objects, arrays, direct buffer wrapper objects      |
    +------------------------------------------------------+
    | Metaspace / class metadata                            |
    |   classes, methods, class loader lifecycles           |
    +------------------------------------------------------+
    | Direct NIO buffer backing storage (off-heap/native)   |
    +------------------------------------------------------+
    | Code cache (generated JIT/native runtime code)        |
    +------------------------------------------------------+
    | Java thread stacks, GC structures, VM internal memory |
    | JNI / third-party native allocations, mapped files... |
    +------------------------------------------------------+

             Total process memory != -Xmx
             Three limits do not replace a native RAM budget.
```

### Lesson Objectives

- Understand what **Metaspace**, **direct buffers**, and **code cache** store, and what they do not store.
- Distinguish **reserved / committed / used / resident**.
- Correctly use the HotSpot flags `MaxMetaspaceSize`, `MaxDirectMemorySize`, `ReservedCodeCacheSize`, and related options.
- Know how to observe via `jcmd`, **Native Memory Tracking (NMT)**, **MXBeans**, logs, and OS/container metrics.
- Separately analyze **Metaspace OOME**, **direct buffer OOME**, and **code cache full/JIT disabled**.
- Choose limits **from data under representative load**, leave headroom for fluctuations, and avoid starving the VM.
- Practice a compilable **Java 17+** program with stable stdout for the logic portion.

**Scope:** this lesson prioritizes **HotSpot JDK 17+**, and does not claim that HotSpot's names/flags/pools are mandatory APIs of every JVM implementation.

## 2. Short Map: Regions, Limit Flags, and Diagnostic Signals

| Region / source | Nature | HotSpot limit | Useful metrics | Prominent symptoms |
| --- | --- | --- | --- | --- |
| **Java heap** | Runtime objects/arrays | `-Xmx` | Heap used/committed, GC, live-set | `OutOfMemoryError: Java heap space` |
| **Metaspace** | Class metadata | `-XX:MaxMetaspaceSize` | Metaspace used/committed, class count, loader count | `OutOfMemoryError: Metaspace` |
| **Compressed Class Space** | Metadata portion related to compressed class pointers | `-XX:CompressedClassSpaceSize` | Class-space used/committed/reserved | `OutOfMemoryError: Compressed class space` |
| **NIO direct buffers** | Backing memory typically located off-heap | `-XX:MaxDirectMemorySize` | BufferPoolMXBean direct count/capacity/memoryUsed | `OutOfMemoryError` when buffer memory cannot be reserved |
| **Code cache** | JIT code and runtime code blobs | `-XX:ReservedCodeCacheSize` | `Compiler.codecache`, CodeHeap/CodeCache MXBeans, codecache logs | Code cache full warning, compilation may be affected |
| **Threads** | Native/JVM stacks and structures | `-Xss` and OS limits, thread count | thread count, NMT Thread, OS | `unable to create native thread` / process resource failures |
| **Native libraries / JNI** | C/C++/OS allocations | Not covered by a single common cap from the three flags above | OS RSS/maps, native profilers | Native OOM, process killed/crash |
| **Mapped files** | Memory mappings such as `MappedByteBuffer` | Not in the same budget as plain direct allocations | mapped buffer pool, OS maps | Mapping/OS resource failures |

**Do not use a single "max memory" for everything.** Each limit protects against a specific type of pressure and can trigger different failure mechanisms.

## 3. Reserved, Committed, Used, and RSS Are Not the Same Number

When viewing NMT, MXBeans, logs, and OS tools, you will commonly see:

- **Reserved:** the portion of **virtual address space** held/reserved by the VM so it can be used. **Not synonymous** with that many bytes residing in physical RAM.
- **Committed:** the portion of memory for which the VM has requested/allocated usable backing according to the VM/OS management model. Cannot be converted to RSS by a simple equality.
- **Used:** the portion allocated for metadata/code/buffers as defined by the pool. Can be smaller than committed due to chunks/free space/fragmentation.
- **Resident Set Size (RSS):** the amount of physical pages currently resident and charged to the process according to OS tools; may include shared mapped pages, and cannot be inferred directly from VM used.
- **PSS (Proportional Set Size):** on supported systems, divides shared pages proportionally among processes, useful when total memory footprint matters.
- **Virtual size/address space:** not the amount of actual RAM used.

For example, output of the form:

```text
Class: reserved=112MB, committed=1MB
Metaspace: used=900KB
Code: reserved=64MB, committed=3MB
```

This is an **illustrative format/unit sample**, not the default state of every machine. **Do not add 112 MB reserved Class + 64 MB reserved Code and conclude that 176 MB of physical memory has been consumed.**

### 3.1. Why does Metaspace have large reserved but small committed?

HotSpot can reserve virtual address ranges for future metadata allocations while committing only the small portion currently needed. JEP 387 (*Elastic Metaspace*) improved how committed memory that is no longer needed is returned, depending on loader lifecycle and fragmentation.

### 3.2. Why is CodeCache pool max not the same as used?

The code cache typically reserves capacity for future compiled code; the number of bytes used depends on the compilation workload. Setting a maximum does not mean the JVM commits the entire maximum immediately at startup.

### 3.3. Do not use the three limits to calculate absolute container memory

A container can be OOMKilled because total RSS/cgroup charge increases due to heap, native memory, page cache, thread stacks, committed heap/metaspace, and concurrent workloads. Cgroup accounting and host policies can differ; you need to observe **actual container memory metrics**, not just VM max numbers.

## 4. What Is Metaspace?

**Metaspace** is the native-memory management system that HotSpot uses to store **class metadata** from JDK 8 onward, replacing the Permanent Generation (PermGen) that existed in older HotSpot versions.

Its contents can include metadata about:

- Runtime classes/interfaces.
- Methods/fields/signatures.
- Runtime constant pools and related class structures.
- Class loader–scoped metadata allocations.

**Do not** confuse it with application heap objects: a regular `new Customer()` resides on the Java heap at runtime, whereas the metadata describing the `Customer` class is managed by HotSpot through metadata structures.

### 4.1. Metaspace belongs to native memory, not directly limited by `-Xmx`

For example:

```bash
java -Xmx256m -XX:MaxMetaspaceSize=192m MyApplication
```

`MyApplication` is a placeholder application class. `-Xmx256m` does not force Metaspace to fit inside that 256 MiB heap; the 192 MiB limit is a **separate** configuration for class metadata.

### 4.2. Why does Metaspace grow?

Some sources:

- Loading more application classes.
- Frameworks/proxies/bytecode generation creating additional classes.
- Multiple class loader instances holding separate sets of class metadata.
- Hot redeploy/plugin architectures creating new class loaders while old loaders are not yet collectible.
- Class initialization and reflection can pull in more loaded classes.

**The number of live classes and still-reachable loaders** matters greatly. Metaspace growth is not automatically a memory leak: the application may still be warming paths or preloading modules as designed.

### 4.3. Class unloading and Metaspace reclamation

HotSpot can reclaim metadata when the corresponding classes/loaders become eligible for unloading, based on GC and runtime reachability. If the application accidentally holds a reference to an old class loader via static registries, threads, caches, or `ThreadContextClassLoader`, it can **prevent class unloading**, causing Metaspace to grow long-term.

Do not solve a class-loader leak merely by increasing `MaxMetaspaceSize`; you need to find what is retaining the loaders.

## 5. `-XX:MaxMetaspaceSize`: Limiting the Right Scope

The flag:

```bash
-XX:MaxMetaspaceSize=192m
```

limits the amount of class metadata memory that HotSpot can use/commit under Metaspace accounting. If the limit is reached and not enough can be reclaimed, the JVM may report:

```text
java.lang.OutOfMemoryError: Metaspace
```

Oracle JDK 17 documents that by default **MaxMetaspaceSize has no upper bound set by this flag**, though it is still bounded by address space/OS/container resources.

### 5.1. `MaxMetaspaceSize` is not the capacity committed at startup

`MaxMetaspaceSize=192m` is a **cap**, not an instruction for the JVM to pre-allocate/commit 192 MiB of native memory at startup.

### 5.2. `-XX:MetaspaceSize` differs from `MaxMetaspaceSize`

`MetaspaceSize` is an **initial threshold/GC trigger related to metadata usage**, not an initial committed RAM amount that a user can add directly to RSS, nor is it a maximum.

For example:

```bash
java -XX:MetaspaceSize=32m -XX:MaxMetaspaceSize=192m MyApplication
```

Do not interpret this as "Metaspace always uses 32 MiB and cannot go lower or higher before GC." The threshold is adjusted by HotSpot according to policy.

### 5.3. What harm does setting the cap too low cause?

- Class loading/verification/metadata allocation can fail.
- GC/class unloading is triggered aggressively to reclaim Metaspace.
- Frameworks/proxies/plugins cannot load the required classes.
- Startup or a rarely used feature may break late in production.

A configuration that is only enough when the **service just comes up** is not guaranteed to be enough when traffic triggers additional classes hours later.

### 5.4. Should you set a very large cap to avoid OOME?

An overly large limit can make class-loader leak issues harder to detect early and create a risk of exceeding the container's memory limit. The cap should be based on **actual peak class metadata usage**, deploy/plugin/lazy-loading scenarios, and headroom.

## 6. Compressed Class Space Differs from Non-Class Metaspace

With compressed class pointers on 64-bit HotSpot, class metadata can be divided into groups:

- **Class space:** the portion for class pointer-related metadata.
- **Non-class Metaspace:** other metadata.

The flag:

```bash
-XX:CompressedClassSpaceSize=128m
```

adjusts the limit of the **compressed class space** region when the corresponding feature is active. If this portion is exhausted, you may encounter:

```text
java.lang.OutOfMemoryError: Compressed class space
```

**Do not confuse `CompressedClassSpaceSize` with `MaxMetaspaceSize`**. The two values affect different limiting mechanisms; when limiting both, you need to understand the accounting relationship between total metadata and the sub-regions according to your JDK.

### 6.1. Reserved class space can be large

In some HotSpot builds, compressed class space by default reserves a fairly large amount of virtual memory (for example, 1 GiB); **virtual reservation is not 1 GiB of committed physical RAM**.

### 6.2. Making class space larger does not automatically save non-class Metaspace

If non-class metadata is the source of pressure, increasing only `CompressedClassSpaceSize` will not solve it. You must inspect NMT Class, `VM.metaspace`, and the corresponding `MemoryPoolMXBean`.

### 6.3. Check the limit relationship on your specific JDK

HotSpot may normalize/adjust combined flags, for example when `MaxMetaspaceSize` is smaller than the default compressed class space. Check **`java -XX:+PrintFlagsFinal -version`** rather than assuming exact numbers you have not verified.

## 7. Direct Memory: What Is It Exactly?

A **Direct `ByteBuffer`** is an NIO buffer whose backing storage is allocated by the JVM outside the regular Java heap on HotSpot. A **Java wrapper object** still exists on the Java heap, but the data bytes of the direct buffer typically reside in off-heap/native memory.

For example:

```java
java.nio.ByteBuffer b =
        java.nio.ByteBuffer.allocateDirect(1024 * 1024);
b.putInt(0, 42);
```

This is a snippet that can be placed inside a method; it allocates a 1 MiB direct buffer, then writes an integer at offset 0.

### 7.1. Direct buffer differs from heap buffer

```java
java.nio.ByteBuffer heapBuffer =
        java.nio.ByteBuffer.allocate(1024 * 1024);
java.nio.ByteBuffer directBuffer =
        java.nio.ByteBuffer.allocateDirect(1024 * 1024);
```

- `allocate` typically uses a Java heap array as backing.
- `allocateDirect` uses native/off-heap backing storage in HotSpot.
- Both still have Java-level object metadata/wrapper.
- Direct buffers can reduce copy overhead in some native I/O paths, but allocate/free can be more expensive; not every workload is faster.

### 7.2. Direct buffer memory is not all native memory

A process's native memory also includes:

- JNI libraries and native `malloc`.
- VM internal arenas.
- Thread stacks.
- Code cache.
- Metaspace.
- Mapped files, filesystem mappings.
- Native memory managed by libraries outside Java.

**`MaxDirectMemorySize` does not set a global cap for those sources.**

### 7.3. `MappedByteBuffer` cannot be unconditionally lumped together with direct buffers

`FileChannel.map` creates mapped byte buffers, involving memory-mapped files and OS VM mappings. MXBeans usually have a separate **`mapped`** pool. Do not assume all mmap bytes fall under the same accounting as `MaxDirectMemorySize`.

## 8. `-XX:MaxDirectMemorySize`: Limiting NIO Direct Buffers

The HotSpot flag:

```bash
-XX:MaxDirectMemorySize=64m
```

sets the maximum for **direct-buffer allocations under `java.nio`/HotSpot accounting**. According to the JDK 17 `java` documentation, if not explicitly set, the VM chooses a suitable size; a `MaxDirectMemorySize=0` field when printing flags can often indicate **ergonomic/default handling**, not "Java is allowed to allocate exactly 0 bytes of direct memory."

### 8.1. Example of a safe configuration for the demo program

```bash
java -Xmx128m -XX:MaxDirectMemorySize=16m MemoryBudgetDemo
```

The demo allocates a 1 MiB direct buffer, below the 16 MiB limit in a normal environment.

### 8.2. When hitting the limit

A program holding many large direct buffers may receive an `OutOfMemoryError` with a message related to being unable to reserve/add **direct buffer memory**, for example of the form:

```text
java.lang.OutOfMemoryError: Cannot reserve ... bytes of direct buffer memory
```

**The exact message** depends on the JDK; it is not necessarily literally "Direct buffer memory" on every release. OS/native allocator errors can also occur without being directly related to this cap.

### 8.3. Why does increasing `-Xmx` sometimes not solve a direct OOME?

`-Xmx` limits the Java heap, while direct buffer backing storage uses memory outside the heap. A heap that still has free space can still encounter a direct allocation failure when `MaxDirectMemorySize` or OS/container resources are exhausted.

### 8.4. GC and direct buffer lifetime

HotSpot direct buffers are managed through Java object reachability and appropriate cleanup mechanisms (such as `Cleaner`). **Dropping a reference does not guarantee that native memory is freed immediately on the next line of code.**

You need to distinguish:

- Buffers still referenced by the application/caches: native memory is **still validly in use or leaked by reference**.
- Buffers no longer reachable, but cleanup/GC has not yet occurred: allocation pressure can rise temporarily.
- Native allocations from JNI/Unsafe libraries: have their own lifecycle and diagnostic tools, and do not automatically use the direct-buffer cleaner.

### 8.5. Pool capacity differs from `memoryUsed`

`BufferPoolMXBean.getTotalCapacity()` reports an **estimate of total capacity** of buffers in the pool. `getMemoryUsed()` reports an **estimate of bytes of memory the VM is using** and may differ from capacity due to allocation/alignment/overhead, or return -1 if no estimate is available.

Do not use these two numbers as guaranteed exact native-address accounting.

## 9. Code Cache: Where the JVM Stores Compiled Code

The **HotSpot code cache** is the runtime memory region containing compiled code (**nmethods**) generated by the JIT and some non-method runtime code/stubs/adapters.

When code becomes hot enough:

```text
Java bytecode
     |
 interpreter / runtime profiling
     |
 JIT compiler C1/C2
     |
 machine code + runtime metadata
     |
 CODE CACHE
     |
 JVM runs optimized native code when appropriate
```

Code cache is **different from the Java heap**, **different from Metaspace**, and **different from direct buffer backing storage**.

### 9.1. Why does code cache grow?

- Many hot methods/loops get JIT compiled.
- Framework code and libraries are loaded on demand.
- Inlining/optimization changes method code size.
- Deoptimization and recompilation can create new compiled versions.
- Method adapters/runtime stubs also use code-cache space.

The JIT can reclaim/mark nmethods and the sweeper can do work, but reclamation depends on runtime state; old code is not always returned immediately.

### 9.2. What is the problem when the code cache is full?

When the code cache no longer has enough space for eligible compiled code, the JVM may log warnings such as:

```text
CodeCache is full. Compiler has been disabled.
```

That is **a HotSpot message pattern**, not a mandatory fatal Java exception. When no more code can be compiled, the Java application may still continue running, but latency/throughput may drop or compilation may be stopped/restarted depending on implementation/version.

**Do not assume every code cache full event throws `OutOfMemoryError: Java heap space`.** This is a different region with a different failure mechanism.

### 9.3. Code cache is not a CDS archive

CDS helps reuse class metadata across JVM processes. The code cache holds generated code/runtime blobs specific to the process and is not automatically shared via a default AppCDS `.jsa`.

## 10. `-XX:ReservedCodeCacheSize` and Segmented Code Cache

The flag:

```bash
-XX:ReservedCodeCacheSize=128m
```

sets the maximum **reserved code cache size** that the JVM uses for the compiled/runtime code cache in HotSpot. Oracle JDK 17 documentation notes the default is typically **240 MiB** when tiered compilation is enabled; do not assume every release/config always has the exact same number. When tiered compilation is disabled, the default can be smaller.

### 10.1. The word "reserved" does not mean all of it is committed

A JVM can reserve 128 MiB of virtual code cache while having committed/operating only a few MiB. `Compiler.codecache` and NMT Code help distinguish this.

### 10.2. Segmented Code Cache (HotSpot)

When enabled, the code cache can be split into regions:

- **Non-nmethod heap:** runtime stubs/adapters and code not directly attached to a compiled Java method.
- **Profiled nmethods heap:** C1 compiled code at profiling tiers.
- **Non-profiled nmethods heap:** C2/compiled code with less profiling.

With some other configurations, the JVM may not split into three segments and instead report a single **`CodeCache`** pool. Therefore, when reading MXBeans:

```text
CodeHeap 'non-nmethods'
CodeHeap 'profiled nmethods'
CodeHeap 'non-profiled nmethods'
```

or:

```text
CodeCache
```

can both be valid output depending on HotSpot options/build. **Do not hardcode a test assuming there must always be exactly three CodeHeap pools.**

### 10.3. `SegmentedCodeCache` and thresholds

HotSpot documentation states that segmentation is enabled based on tiered compilation and code cache size policy (JDK 17 typically above a certain threshold, e.g., 240 MiB). When lowering `ReservedCodeCacheSize` to 64 MiB, the output may switch to a single unsegmented **`CodeCache`**.

### 10.4. Setting the cache too small

An overly low limit can:

- Fill the code cache during startup/steady workload.
- Limit JIT compilations and nmethod replacements.
- Increase the risk of latency/throughput regressions.
- Force the runtime to manage the code cache too aggressively.

**Do not recommend lowering the code cache to save virtual reserved pages without OS RSS/PSS and code-cache usage evidence.**

## 11. A "Minimal" Configuration Is Not an Addition Formula

Full example syntax:

```bash
java -Xms64m -Xmx128m \
     -XX:MaxMetaspaceSize=128m \
     -XX:MaxDirectMemorySize=16m \
     -XX:ReservedCodeCacheSize=64m \
     MemoryBudgetDemo
```

The `\` line continuation is for Bash. In PowerShell, use a single line:

```powershell
java -Xms64m -Xmx128m -XX:MaxMetaspaceSize=128m -XX:MaxDirectMemorySize=16m -XX:ReservedCodeCacheSize=64m MemoryBudgetDemo
```

**This is a configuration for a small demo program, NOT a preset for production services.** A service using Netty/WebFlux may need much more direct buffers; a framework/plugin system may have a larger Metaspace; a JIT-heavy workload may need a larger code cache.

### 11.1. Why can't you add them up to say "the JVM will use at most 336 MiB"?

- These flags are caps/reservations for different groups, not actual committed usage.
- Java thread stacks, GC, JNI, native allocators, runtime libraries, and mapped files are not counted.
- Native memory or Linux RSS can exceed the summed components.
- Some flags limit according to internal accounting rather than physical maximums in the same way.
- **Reserved** code cache is virtual space, different from committed/resident.

A proper budget needs to sum **actually observed peak committed/native/heap/threads** with headroom, then compare against container/OS limits.

## 12. A Sensible Order When Deciding Limits

Do not start with "Metaspace 128m, direct 128m, code 128m because it's easy to remember." Instead:

1. Define the **SLO**: latency, throughput, pod/container limit, startup deadline.
2. Record the JDK/HotSpot version and **current JVM flags**.
3. Record **baseline** NMT, MemoryPoolMXBeans/BufferPoolMXBeans, and code cache.
4. Generate **representative load**, including peak concurrency and rare but important code paths.
5. Track **used/committed/reserved trends**, class count, direct pool capacity/count, and compile status.
6. Distinguish startup/warm-up from steady-state.
7. Identify peak + variance + deploy/redeploy scenarios.
8. Choose a **cap with headroom**, never lower than peak measured usage.
9. Re-verify on real container/VM resources.
10. Decrease/increase each flag **one variable at a time**, collecting rollback criteria.

### 12.1. Headroom has no universal percentage

An application with very few dynamic classes has a stable Metaspace; a hot-reload/plugins service can spike. A gateway's direct buffers under traffic bursts differ from a CPU-bound batch job. Code cache demand varies by class count/hot methods/JIT policy.

Therefore, do not put promises like "+20% is always enough" into a runbook. Headroom must be based on **percentiles, spikes, deployment patterns, GC response, and incidents**.

## 13. Native Memory Tracking (NMT): Seeing HotSpot Memory by Subsystem

**NMT** is a HotSpot tool that tracks a portion of **VM-managed native memory allocations**, helping break down usage by categories such as Class, Code, Thread, GC, Compiler, Internal, etc.

Enable at startup:

```bash
java -XX:NativeMemoryTracking=summary MemoryBudgetDemo
```

There are two commonly used levels:

- `-XX:NativeMemoryTracking=summary`: statistics by JVM subsystems.
- `-XX:NativeMemoryTracking=detail`: adds call sites/virtual memory regions; incurs higher overhead.

According to Oracle, **NMT is off by default** and typically needs to be enabled right when the VM starts; do not assume you can request full NMT history from a process that was not started with it enabled.

### 13.1. NMT does not track every `malloc` outside the VM

An important point from Oracle documentation: NMT focuses on **HotSpot/JVM-managed native memory**, and **is not a comprehensive native profiler for JNI code or third-party native libraries**.

Therefore, the NMT total **does not necessarily equal RSS or all native bytes**; if investigating a native memory leak outside HotSpot, you may need OS maps, allocators/profilers, or specialized libraries.

### 13.2. NMT summary is not "one line for direct memory"

Direct-buffer backing allocations may appear under one or more NMT categories depending on the HotSpot version and allocator path; NMT **does not guarantee a separate line named `Direct buffer memory`** that matches direct pool capacity.

When suspecting direct buffer pressure, use **BufferPoolMXBean** first, and NMT/OS metrics for additional context.

### 13.3. Overhead impact

Oracle notes that NMT can reduce performance and increase memory overhead (troubleshooting docs cite roughly 5–10% for some workloads). Enable it deliberately on measurement/diagnostic environments, and do not leave `detail` enabled in production forever by default.

## 14. `jcmd VM.native_memory`: Summary and Delta Comparison

First identify the JVM process:

```bash
jcmd -l
```

For example, with a known PID:

```bash
jcmd <pid> VM.native_memory summary scale=MB
```

`<pid>` is a placeholder and must be replaced with the actual PID; **do not copy `<`/`>` into the shell as some shells treat them as redirect syntax**.

If the JVM was started with NMT summary/detail, you can take a baseline:

```bash
jcmd <pid> VM.native_memory baseline
```

after running a workload or waiting for the state you want to observe:

```bash
jcmd <pid> VM.native_memory summary.diff scale=MB
```

### 14.1. Where is a baseline useful?

You can compare:

- After startup/ready.
- After a test load.
- After opening/closing a plugin.
- After redeploy.
- After idle and GC/class unloading, when appropriate.

Sample output structure:

```text
Total: reserved=..., committed=...
- Java Heap (reserved=..., committed=...)
- Class (reserved=..., committed=...)
- Code (reserved=..., committed=...)
- Thread (reserved=..., committed=...)
```

This is an **illustrative structure**. Units, plus/minus signs, and categories depend on the VM/report.

### 14.2. Do not assume every increasing delta is a leak

Class metadata growing during lazy loads is normal; code cache growing during warm-up is also normal. A leak is suspicious when usage grows continuously **under a workload/class-loader lifecycle that is expected to be stable**, especially after appropriate unloading/releasing.

### 14.3. If `VM.native_memory` reports disabled

NMT needs to be enabled from JVM startup via `-XX:NativeMemoryTracking=summary` or `detail`. Do not re-run the query 10 times on the same process expecting it to appear retroactively.

## 15. `jcmd VM.metaspace`: Dedicated Class Metadata Observation

Per the relevant HotSpot/JDK documentation:

```bash
jcmd <pid> VM.metaspace basic
```

The report can provide information on:

- Class/non-class metadata usage.
- Reserved/committed.
- Virtual space, chunks, fragmentation.
- Class loader usage and class counts depending on options.

Depending on the JDK/build, additional diagnostics may be available:

```bash
jcmd <pid> VM.metaspace show-loaders
```

Check capabilities with:

```bash
jcmd <pid> help
jcmd <pid> help VM.metaspace
```

### 15.1. Why inspect class loaders?

If Metaspace grows after each hot redeploy, some old class loaders may still be reachable. Use the per-loader breakdown to see whether class counts and memory of the loaders drop as expected on unload.

### 15.2. Do not look only at `Metaspace used` and ignore class space

With compressed class pointers, the JVM has non-class and class metadata spaces. Those caps can be hit differently; check both Metaspace and **Compressed Class Space**.

### 15.3. Not every `jcmd` command exists on every VM

HotSpot/JDK release or attach permissions/container policies may restrict commands. Do not infer from a failed command that Metaspace does not exist.

## 16. `jcmd Compiler.codecache`: How to Know If Code Cache Still Has Room

The command:

```bash
jcmd <pid> Compiler.codecache
```

on HotSpot typically yields numbers like:

```text
CodeCache: size=65536Kb used=2701Kb max_used=2701Kb free=62834Kb
...
Compilation: enabled, stopped_count=0, restarted_count=0
```

This is **a sample output observed from a test environment**, not numbers that must be identical on every JVM. With a segmented code cache, the output may show each CodeHeap separately.

### 16.1. Which numbers to read?

- **size:** capacity of the code cache/segment.
- **used/free:** current state under code cache accounting.
- **max_used:** peak usage during the run.
- **Compilation status:** whether the compiler is still enabled or has stopped/restarted according to the VM.

### 16.2. Deeper analysis

Some HotSpot builds support:

```bash
jcmd <pid> Compiler.CodeHeap_Analytics
```

The output can detail code heaps/free space/method counts. This is a diagnostic operation; depending on version/permissions and workload, it has overhead.

### 16.3. If Code Cache is repeatedly full

Do not just increase `ReservedCodeCacheSize` immediately. Check:

- Hot methods/JIT levels and code cache occupancy.
- Possible bursts of class loading/code generation.
- Compiler stop/restart warnings.
- Code cache fragmentation/method sweeping.
- Heap/native memory pressure and container limits.
- Startup/steady-state difference.

You may need to increase the limit **if actual usage is approaching the cap**, while keeping sufficient memory headroom.

## 17. `-Xlog`: Class, Metaspace, and Code Cache Events

HotSpot Unified Logging provides relevant tags for observation, depending on version:

```bash
java -Xlog:gc+metaspace=info MemoryBudgetDemo
```

You can log Metaspace details at supported levels:

```bash
java -Xlog:metaspace=info MemoryBudgetDemo
```

Code cache events via tags supported by the runtime:

```bash
java -Xlog:codecache=info MemoryBudgetDemo
```

**Important:** each tag/tag combination and level must be checked:

```bash
java -Xlog:help
```

If a tag above is not supported by the VM in the release being used, do not claim every JVM must print the exact sample lines. Some CodeCache information is also emitted via compiler logs or `jcmd`.

### 17.1. Logging is an explanatory tool, not a clean timing baseline

Verbose logs have CPU/I/O overhead and can alter scheduling. Collect performance metrics in separate runs without diagnostics when serious benchmarking is needed.

### 17.2. OOME logs do not always give the full root cause

An `OutOfMemoryError` may report the region name, but to know why the region grew, you must inspect class-loader retention, buffer ownership, code cache activity, and OS native allocations.

## 18. `MemoryPoolMXBean`: Measuring Metaspace and Code Cache from Java

The JDK provides **`java.lang.management.MemoryPoolMXBean`**, accessible via:

```java
ManagementFactory.getMemoryPoolMXBeans()
```

Some pool names on HotSpot:

```text
Metaspace
Compressed Class Space
CodeHeap 'non-nmethods'
CodeHeap 'profiled nmethods'
CodeHeap 'non-profiled nmethods'
CodeCache
```

Not all appear together. With segmentation, there are usually `CodeHeap` pools; with a small code cache configuration, there may be a single `CodeCache` pool.

### 18.1. What does `MemoryUsage` contain?

`MemoryPoolMXBean.getUsage()` can return:

- `getUsed()`: bytes used according to the pool.
- `getCommitted()`: bytes committed according to the pool.
- `getMax()`: maximum according to the pool, **-1** if undefined.
- `getInit()`: initial allocation estimate if available.

**Do not take `getMax() == -1` to mean the pool has "unlimited physical RAM."** It simply means the management interface does not define a specific maximum.

### 18.2. MXBeans are approximate snapshots

Values can change immediately as the program/JVM continues running. They are useful for tracking trends, not as an atomic snapshot of all native allocations across all pools.

## 19. `BufferPoolMXBean`: Measuring NIO Direct Memory from Java

The JDK has the interface:

```java
java.lang.management.BufferPoolMXBean
```

Retrieve the pools:

```java
ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)
```

Some HotSpot pool names:

- `direct`.
- `mapped`.
- `mapped - 'non-volatile memory'` on supported platforms/configurations.

For each pool:

- `getCount()` — estimate number of buffers.
- `getTotalCapacity()` — estimate aggregate buffer capacity bytes.
- `getMemoryUsed()` — estimate memory bytes, **may be -1** or differ from capacity due to alignment/allocator overhead.

**Select pools by name and check for existence**; do not hardcode "every JVM has exactly one direct pool and no mapped pool."

### 19.1. A growing direct pool is not necessarily a leak

A server may validly retain pooled direct buffers to avoid frequent allocations. You need to know pool ownership, idle reclamation policy, and traffic concurrency. Check for a plateau after warm-up/peak load rather than demanding usage return to 0 after every request.

### 19.2. Off-heap libraries may not appear in the direct pool

Native allocations from outside the Buffer APIs may not be managed through the same pool. If process RSS rises while `BufferPoolMXBean` stays stable, also check NMT, JNI/native libraries, thread stacks, and OS maps.

## 20. Standalone Java 17+ Example to Inspect All Three Regions

Create the file **`MemoryBudgetDemo.java`**:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.nio.ByteBuffer;
import java.util.Locale;

public final class MemoryBudgetDemo {
    private static volatile long sink;

    static int transform(int x) {
        return (x * 31) ^ (x >>> 3);
    }

    public static void main(String[] args) throws Exception {
        ByteBuffer direct = ByteBuffer.allocateDirect(1024 * 1024);
        direct.putInt(0, 424242);
        System.out.println("directValue=" + direct.getInt(0));

        long sum = 0;
        for (int i = 0; i < 100_000; i++) {
            sum += transform(i);
        }
        sink = sum;
        System.out.println("checksum=" + sum);
        System.out.println("sinkMatches=" + (sink == sum));

        boolean metaspaceFound = false;
        boolean codeCacheFound = false;
        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            String name = pool.getName();
            if (name.equals("Metaspace")) metaspaceFound = true;
            if (name.startsWith("CodeHeap")
                    || name.startsWith("CodeCache")) {
                codeCacheFound = true;
            }

            if (name.equals("Metaspace")
                    || name.equals("Compressed Class Space")
                    || name.startsWith("CodeHeap")
                    || name.startsWith("CodeCache")) {
                MemoryUsage usage = pool.getUsage();
                if (usage != null) {
                    System.out.printf(Locale.ROOT,
                            "%s: usedKiB=%d committedKiB=%d maxKiB=%d%n",
                            name,
                            usage.getUsed() / 1024,
                            usage.getCommitted() / 1024,
                            usage.getMax() < 0
                                    ? -1 : usage.getMax() / 1024);
                }
            }
        }

        boolean directPoolFound = false;
        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            if (pool.getName().equals("direct")) {
                directPoolFound = true;
                System.out.println("directPoolCount=" + pool.getCount());
                System.out.println("directPoolCapacityBytes="
                        + pool.getTotalCapacity());
                System.out.println("directPoolUsedBytes="
                        + pool.getMemoryUsed());
            }
        }

        System.out.println("metaspacePoolFound=" + metaspaceFound);
        System.out.println("codeCachePoolFound=" + codeCacheFound);
        System.out.println("directPoolFound=" + directPoolFound);

        if (args.length != 0 && args[0].equals("hold")) {
            System.out.println("pid=" + ProcessHandle.current().pid());
            System.out.println("waitingForDiagnostics=true");
            Thread.sleep(15_000);
        }
    }
}
```

### 20.1. Compile

```bash
javac --release 17 MemoryBudgetDemo.java
```

### 20.2. Run with defaults

```bash
java MemoryBudgetDemo
```

**The first three lines have fixed values when the program runs properly:**

```text
directValue=424242
checksum=154999801808
sinkMatches=true
```

The next part is **pool metadata**, which may include:

```text
Metaspace: usedKiB=... committedKiB=... maxKiB=...
Compressed Class Space: usedKiB=... committedKiB=... maxKiB=...
CodeHeap 'non-nmethods': usedKiB=... committedKiB=... maxKiB=...
...
directPoolCount=...
directPoolCapacityBytes=...
directPoolUsedBytes=...
metaspacePoolFound=true
codeCachePoolFound=true
directPoolFound=true
```

The `...` in this block are **placeholders illustrating non-fixed metrics**, **not exact stdout**. The pool-presence booleans were verified on local HotSpot; **non-HotSpot JVMs may use different names**.

### 20.3. Run with the three limits

```bash
java -Xmx128m -XX:MaxMetaspaceSize=128m \
     -XX:MaxDirectMemorySize=16m \
     -XX:ReservedCodeCacheSize=64m \
     MemoryBudgetDemo
```

On Windows PowerShell:

```powershell
java -Xmx128m -XX:MaxMetaspaceSize=128m -XX:MaxDirectMemorySize=16m -XX:ReservedCodeCacheSize=64m MemoryBudgetDemo
```

**The three fixed checksum lines do not change.** The `CodeHeap` pool may switch to `CodeCache` because segmentation changes with configuration; the example accounts for both.

### 20.4. Why is there one direct allocation while the memory pool only "estimates"?

The demo allocates 1 MiB using `ByteBuffer.allocateDirect` and keeps a local reference to the buffer in `main`. The buffer pool normally records at least this allocation. However, other GC/VM/library allocations can cause `getCount()` and `getMemoryUsed()` to vary over time.

**Do not compare exact `directPoolCount` to the constant 1 across all JVMs/runtimes.**

### 20.5. How is `checksum` calculated?

`transform(i)` computes `(i*31) ^ (i>>>3)` using 32-bit Java integer arithmetic. The result is accumulated into a `long` over 100,000 iterations, producing the deterministic value **154999801808** for the demo input.

`volatile sink` creates an observable side effect that prevents some compiler optimizations from eliminating the computation entirely; do not use this demo as a performance microbenchmark instead of JMH.

## 21. Diagnosing with `jcmd` on the Same Process

The program supports the `hold` argument to keep the JVM running for a short window so learners can attach diagnostics:

```bash
java -XX:NativeMemoryTracking=summary -Xmx128m \
     -XX:MaxMetaspaceSize=128m \
     -XX:MaxDirectMemorySize=16m \
     -XX:ReservedCodeCacheSize=64m \
     MemoryBudgetDemo hold
```

In another terminal, while the process is still running, get the PID printed by the demo or run:

```bash
jcmd -l
```

Then:

```bash
jcmd <pid> VM.native_memory summary scale=MB
jcmd <pid> VM.metaspace basic
jcmd <pid> Compiler.codecache
```

Where `<pid>` is the actual PID.

### 21.1. This is a test window, not a production server

`Thread.sleep(15_000)` only holds the demo process for about 15 seconds after printing the metrics. The `jcmd` commands must be run while the process is still alive. If you miss the window, start a new demo run; **do not keep the process running indefinitely** just to observe it.

### 21.2. Practically verified example

On **OpenJDK HotSpot 24.0.2** (code compatible with **Java 17** and compiled with `javac --release 17`), testing showed:

- `MemoryBudgetDemo` ran successfully with the flags above, with the correct checksum.
- `MemoryPoolMXBean` displayed Metaspace, Compressed Class Space, and code cache.
- When code cache was limited to 64 MiB, the VM displayed the **`CodeCache`** pool, not necessarily three `CodeHeap` pools.
- `BufferPoolMXBean` had the `direct` pool, reporting the 1 MiB direct buffer during measurement.
- `jcmd VM.native_memory summary` provided Class/Code/Heap/Thread categories.
- `jcmd VM.metaspace basic` displayed metadata usage.
- `jcmd Compiler.codecache` reported compilation status and code cache occupancy.

This is a **local test**; used/committed/reserved numbers differ in real environments. Do not confuse "Java 17-compatible" with a claim that the test was run on an actual JDK 17 binary.

## 22. Scenario A — Metaspace Keeps Growing After Every Redeploy

**Symptom:** after each deploy/hot reload, loaded class count/Metaspace does not return to the expected level; eventually hits `OutOfMemoryError: Metaspace`.

Reasoning steps:

1. Record class count and Metaspace used/committed before deploy.
2. Deploy/reload, wait for/observe class unloading via GC.
3. Use `jcmd VM.metaspace` and class-loading/unloading logs.
4. Check whether old class loaders are still reachable.
5. Search for references via static registries, thread local values, executors, caches, TCCL, and lingering threads.
6. Fix ownership/cleanup; only increase the cap if the workload genuinely needs it and has been measured.

### 22.1. Do not treat a single GC not immediately reducing usage as proof of a leak

Class unloading depends on the GC cycle, loader reachability, and VM policies. There can be delayed reclamation or fragmentation. A stronger sign of a leak is when **across multiple similar lifecycle cycles**, the number of retained loaders/classes grows without business justification.

### 22.2. Does a larger `-Xmx` cure a Metaspace leak?

Not directly. The remaining native memory budget may even come under more pressure. The root cause is metadata/lifecycle, not just the object heap cap.

## 23. Scenario B — Direct Buffers Grow with Network Connections

**Symptom:** an NIO/Netty/network-stack service receives traffic; direct pool `count/totalCapacity/memoryUsed` grows, followed by `OutOfMemoryError` when reserving direct buffer memory or container OOM.

Checklist:

- Measure **active connections × buffers per connection × average capacity**, plus pipeline caches/pooling.
- Read `BufferPoolMXBean` direct pool and application buffer pool diagnostics.
- Check pooling: are buffers returned to the pool on time?
- Check whether requests/errors/cancellation paths retain references.
- Check burst/retry/queue backlog and container memory limit.
- Do not just increase `MaxDirectMemorySize` if buffer references are not being released.

### 23.1. A real leak and valid pooling are different

A pool retaining several hundred MiB for reuse can be an intentional design, not automatically a leak. However, if the direct pool does not plateau under steady load, investigate.

### 23.2. Native allocations outside `DirectByteBuffer`

If `BufferPoolMXBean` direct stays nearly stable while RSS increases, expand diagnostics to JNI/native allocators, mapped pages, native arenas, stacks, GC, and OS metrics.

## 24. Scenario C — Code Cache Fills Up as Hot Methods Increase

**Symptom:** HotSpot reports code cache full/compiler disabled, application throughput drops after warm-up, or code cache usage is near the limit.

How to check:

1. `jcmd <pid> Compiler.codecache`.
2. Check `Compilation: enabled/stopped_count/restarted_count` if available.
3. Observe `-Xlog:codecache`/compiler events at supported levels.
4. Check whether JVM code generation/proxies/lambdas/framework classes are creating many methods.
5. Compare code cache demand against `ReservedCodeCacheSize`, segmented configuration, and container budget.
6. Try increasing the limit incrementally if code cache is a proven bottleneck.

### 24.1. Do not assume code cache full is a Java heap OOME

The code cache region has its own exhaustion behavior. The JVM can still continue in the interpreter/remaining compiled code; performance degradation is the noticeable symptom, not necessarily an immediate crash.

### 24.2. High code cache usage during warm-up is common

As hot code is compiled early on, used code cache increases. If it plateaus well below the cap and compilation remains enabled, there is no reason to automatically increase the reserve just because the value is higher than yesterday.

## 25. Configuring for Container Resources: Budgeting Instead of Independent Caps

Suppose a container is constrained to a known memory budget. The right approach is not:

```text
container_limit = Xmx + MaxMetaspaceSize
                  + MaxDirectMemorySize + ReservedCodeCacheSize
```

this equation is **wrong** because it mixes **virtual reserve**, **committed**, and **potential allocations**, while omitting many memory sources.

A budgeting worksheet might look like:

| Component | What to investigate | Workload-dependent? |
| --- | --- | --- |
| Heap | Peak live set, GC overhead, Xmx | Very much |
| Metaspace | Class count, loaders, peaks, MaxMetaspace | Yes |
| Direct buffers | Peak outstanding bytes, pooling, bursts | Yes |
| Code cache | Max used, compiler enabled, hot code footprint | Yes |
| Threads | Number × stack usage/native footprint | Yes |
| GC/compiler/native/JNI | NMT + OS metrics + library diagnostics | Yes |
| Mapped/shared pages | RSS/PSS/cgroup accounting | Yes |
| Headroom | traffic spikes, deploy change, instrumentation | Yes |

### 25.1. Do not set every cap right next to idle used values

Metaspace can grow after running a rare feature; direct memory grows when concurrent requests are high; code cache can grow when JIT profiling completes. Measuring only idle and setting limits close to idle usage leads to late failures.

### 25.2. Limiting itself can affect behavior

If you lower `MaxMetaspaceSize`, GC/class unloading policy may run more frequently. If you lower code cache, JIT compilation may slow down or stop. If you lower direct memory, buffers may cause OOME/GC pressure. Cap changes must be **load tested**, not just checked with `java -version`.

## 26. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "`-Xmx` is the maximum memory of the entire Java process." | It limits the Java heap, not all native memory. |
| "Metaspace resides inside the Java heap." | HotSpot manages class metadata in native memory. |
| "`MaxMetaspaceSize=128m` commits 128m at startup." | It is a cap, not an upfront allocation. |
| "`MetaspaceSize` and `MaxMetaspaceSize` mean the same thing." | One relates to a threshold, the other is a maximum. |
| "Metaspace growth always proves a leak." | Lazy class loading/initialization also increases usage. |
| "Compressed Class Space is just another name for all of Metaspace." | It has a specific class metadata scope with its own cap. |
| "`CompressedClassSpaceSize` reserved 1 GiB = 1 GiB of RAM in use." | Virtual reservation differs from committed/RSS. |
| "Direct `ByteBuffer` wrapper means all storage is on the heap." | The backing data of a direct buffer is typically off-heap. |
| "`MaxDirectMemorySize` blocks all JNI `malloc`." | This flag mainly governs NIO direct-buffer accounting. |
| "Direct buffers do not need GC/reachability to be reclaimed." | Cleaner/lifetime depends on reachability/VM mechanisms. |
| "Capacity equals `memoryUsed` in all cases." | MXBean values are estimates, with alignment/allocator overhead. |
| "`MappedByteBuffer` always shares the same pool/limit as direct buffers." | Mapped buffers have a different scope/accounting. |
| "Code cache and Metaspace are the same region." | Metadata and generated code are two different regions. |
| "`ReservedCodeCacheSize=64m` means RSS immediately increases by 64m." | Reservation does not mean committed/resident. |
| "`CodeCache` must always consist of exactly three `CodeHeap` MXBeans." | Segmentation depends on JVM build/config. |
| "Code cache full always throws Java heap `OutOfMemoryError`." | Usually involves compilation disabled/warnings and performance. |
| "A level-4 compiled method proves the code cache is full." | Compilation level and memory occupancy are two different metrics. |
| "NMT total always equals process RSS." | NMT does not measure every native allocation/OS memory. |
| "NMT summary must have a `Direct buffer memory` line." | Direct buffers can appear under VM categories without that name. |
| "NMT is always enabled by default." | Off by default in HotSpot JDK 17. |
| "A single increase in code cache used is a leak." | JIT warm-up can be normal growth. |
| "Adding `Xmx` + the three maxes gives the exact memory limit." | No; thread stacks, native/GC/JNI, and committed/reserved differ. |
| "Smaller limits always reduce latency." | Can trigger GC/compilation stops/OOME. |
| "A demo showing `poolFound=true` proves every JVM has that pool name." | This is HotSpot-specific naming/behavior. |
| "JDK version does not affect default flags." | VM ergonomics/options change across builds and architectures. |

## 27. Self-Check Questions with Answers

**Q1.** Does `-Xmx` limit Metaspace?

**Answer:** No. The heap and Metaspace class metadata have separate limiting mechanisms in HotSpot.

**Q2.** Which flag sets the cap for class metadata?

**Answer:** `-XX:MaxMetaspaceSize=...`.

**Q3.** Is `MetaspaceSize` a maximum?

**Answer:** No. It relates to a threshold/GC trigger, unlike `MaxMetaspaceSize`.

**Q4.** When does `OutOfMemoryError: Compressed class space` appear?

**Answer:** When the compressed class space region exhausts its configured capacity and the VM cannot satisfy an eligible allocation.

**Q5.** Does 1 GiB reserved mean RSS increases by 1 GiB?

**Answer:** No. Reserved virtual address space differs from committed/resident physical memory.

**Q6.** Does a Direct `ByteBuffer` reside completely inside the Java heap?

**Answer:** No. The wrapper is a Java object, while direct buffer backing storage on HotSpot is typically off-heap.

**Q7.** Does `MaxDirectMemorySize` limit all native/JNI `malloc` libraries?

**Answer:** No. It targets NIO direct-buffer memory accounting.

**Q8.** Why doesn't direct pool count/capacity drop immediately after `buffer = null`?

**Answer:** Cleanup depends on reachability, GC/Cleaner, and VM pooling; there is no immediate-free guarantee.

**Q9.** Which API reads the direct pool?

**Answer:** `BufferPoolMXBean` via `ManagementFactory.getPlatformMXBeans`.

**Q10.** Can `getMemoryUsed()` differ from `getTotalCapacity()`?

**Answer:** Yes. Alignment/allocator overhead and implementation-specific estimates cause differences.

**Q11.** What kind of data does the code cache contain?

**Answer:** JIT-generated nmethods and VM runtime code/stubs, distinct from heap and class metadata.

**Q12.** What is the usual flag for the maximum code cache?

**Answer:** `-XX:ReservedCodeCacheSize=...`.

**Q13.** Does a full code cache force the application to throw a Java heap OOME?

**Answer:** No. The VM may warn/stop compilation, affecting throughput/latency.

**Q14.** Why do we sometimes see `CodeHeap` and sometimes `CodeCache`?

**Answer:** HotSpot can use a segmented or unsegmented code cache depending on runtime flags/build.

**Q15.** How do reserved and committed differ?

**Answer:** Reserved holds a virtual address range; committed is memory that has requested backing via the VM/OS mechanism.

**Q16.** Which flag enables NMT?

**Answer:** `-XX:NativeMemoryTracking=summary` or `detail` at startup.

**Q17.** Which `jcmd` command shows the JVM native memory breakdown?

**Answer:** `jcmd <pid> VM.native_memory summary` if NMT is enabled.

**Q18.** Command to view detailed class metadata?

**Answer:** `jcmd <pid> VM.metaspace basic` on supported HotSpot builds.

**Q19.** Command to view code cache usage/compilation status?

**Answer:** `jcmd <pid> Compiler.codecache`.

**Q20.** Why don't NMT and RSS necessarily match?

**Answer:** NMT's scope covers only certain VM allocations; RSS also includes OS residency/shared pages and native allocations outside VM tracking.

**Q21.** Can total process RAM be calculated as `Xmx + MaxMetaspaceSize + MaxDirectMemorySize + ReservedCodeCacheSize`?

**Answer:** No, these metrics/caps have different definitions and many native areas are not included.

**Q22.** What does Metaspace growing across redeploys suggest checking?

**Answer:** Class loader retention/unloading, proxy class generation, cache/thread references, class counts, and NMT/`VM.metaspace`.

**Q23.** What does direct memory growing under traffic suggest checking?

**Answer:** Buffer pooling/ownership, outstanding buffers/connections, async cancellation paths, and `BufferPoolMXBean` direct usage.

**Q24.** What does code cache nearing full under load suggest checking?

**Answer:** `Compiler.codecache`, compiler logs, hot code footprint, code sweeper/fragmentation, and JVM flags.

**Q25.** Why shouldn't memory caps be chosen solely from idle metrics?

**Answer:** Regions experience spikes from class lazy-loading, request concurrency, and JIT warm-up, requiring peak/load data and headroom.

**Q26.** Does running the demo on JDK 24 automatically prove every JDK 17 build supports the exact same pool names?

**Answer:** No. The code uses Java 17 APIs and JDK 17-compatible flags; specific names/metrics belong to the HotSpot implementation.

## 28. Production Readiness Checklist

1. Confirm **Java/JVM vendor, build, architecture**, and current flags.
2. Identify the **container/OS memory budget**, OOMKilled policy, and how RSS/PSS is measured.
3. Measure heap live set, Metaspace used/committed, compressed class space, direct pool, and code cache.
4. Enable NMT summary **deliberately** in an appropriate diagnostic environment.
5. Take an NMT baseline and diff across startup/steady/peak/redeploy phases.
6. Use `VM.metaspace` to observe loaders and class metadata when growth appears.
7. Use `Compiler.codecache` to observe compilation enabled/stopped/usage.
8. Use `BufferPoolMXBean` for `direct` and `mapped` pools if present.
9. Do not equate `MaxDirectMemorySize` with all native allocations.
10. Do not compare reserved virtual code cache to RSS as if they were the same unit of consumption.
11. Run a representative workload including peak concurrency and lazy/rare code paths.
12. Look for leaks/non-plateauing pools before increasing caps.
13. Keep headroom for thread stacks/GC/JNI and non-VM allocations.
14. Change one flag independently at a time and record outcome/latency/GC/OOME.
15. Do not set caps right next to idle used.
16. Check error/alert rules for Metaspace OOME, direct OOME, and code cache warnings separately.
17. Avoid leaving NMT detail or verbose logging enabled forever if the overhead is unacceptable.
18. Benchmark performance without diagnostic I/O before concluding benefits.
19. Have a rollback plan and memory incident playbook.
20. Do not treat the 128/16/64 MiB demo configuration as a default production recommendation.

### Quick Reference Diagram

```text
                       JVM memory observation
                                 |
             +-------------------+-------------------+
             |                   |                   |
         Metaspace           Direct NIO            Code Cache
        class metadata       ByteBuffer             JIT/native
             |               backing                 blobs
             |                   |                   |
    MaxMetaspaceSize    MaxDirectMemorySize    ReservedCodeCacheSize
             |                   |                   |
     VM.metaspace         BufferPoolMXBean       Compiler.codecache
       / NMT Class          / NMT + OS             / NMT Code
             |                   |                   |
        Class loader        Pool lifetime          Compiler status
         growth/leaks      burst/caching            occupancy
             |                   |                   |
             +-------------------+-------------------+
                                 |
                   measured under real workload
                   compare used / committed / RSS
                   headroom + native/GC/thread costs
                                 |
                     change limits with evidence

Three independent controls != complete process memory cap.
```

**Conclusion:** Limit Metaspace, NIO direct memory, and code cache **only based on observed data and operational requirements**. Metaspace follows class metadata/class loader lifecycles; direct-buffer budgets follow buffers/traffic/pooling; code cache follows hot methods/JIT behavior. All three differ from `-Xmx` and from total process native/RSS memory. Use **NMT + the right MXBean/jcmd for each region + OS/container metrics**, then set limits with sufficient headroom and load-test to verify, rather than copying any three arbitrary default numbers.

### Official Documentation and Technical Sources

- [Oracle JDK 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `MaxMetaspaceSize`, `MaxDirectMemorySize`, `ReservedCodeCacheSize`, `NativeMemoryTracking`, segmented code cache, and related VM flags.
- [Oracle JDK 17 — Troubleshooting Memory Leaks](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html): forms of Java heap/Metaspace/Compressed Class Space OOME, native-memory diagnostics, NMT limits.
- [Oracle JDK 17 — GC Tuning, Other Considerations](https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html): Metaspace, class metadata allocations, class space.
- [Oracle JDK 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): NMT summary/detail, baseline/diff, overhead, and scope.
- [Oracle JDK 17 — `jcmd` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.native_memory`, `VM.metaspace`, `Compiler.codecache`.
- [BufferPoolMXBean API, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): direct/mapped pool metrics and estimation caveats.
- [MemoryPoolMXBean API, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): used/committed/max/usage thresholds.
- [ByteBuffer API, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `allocate` vs `allocateDirect`.
- [OpenJDK JEP 387 — Elastic Metaspace](https://openjdk.org/jeps/387): reclaim/uncommit and native class metadata management.
- [OpenJDK JEP 197 — Segmented Code Cache](https://openjdk.org/jeps/197): non-nmethods, profiled, and non-profiled compiled code.
