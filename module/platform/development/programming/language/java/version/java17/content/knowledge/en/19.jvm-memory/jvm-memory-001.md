# Heap, Stack, Metaspace, and Off-Heap Memory in Java 17

> **Topic:** Java 17  
> **Chapter:** JVM and Memory  
> **Scope:** Runtime data areas per the JVM Specification and how HotSpot manages heap, stack, metaspace, and common native memory regions in Java 17.

## 1. The JVM uses multiple memory regions

A Java process does not have just a single memory region. When the JVM runs, it manages several types of data with different lifecycles and purposes:

- **Heap:** the area that stores objects and arrays; shared across threads and managed by the garbage collector.
- **Java stack:** each thread has its own stack to store method call frames, local variables, and the operand stack.
- **Metaspace:** the native memory region that HotSpot uses to store class metadata and class-loader-related information.
- **Off-heap / native memory:** a general term for memory regions outside the Java heap, such as direct buffers, memory-mapped files, thread stacks, the code cache, internal JVM structures, and memory allocated by native libraries.

High-level diagram:

```text
Java Process
|
+-- Java heap (shared across threads)
|     +-- Objects
|     +-- Arrays
|     +-- Per-thread TLAB (still inside the heap)
|
+-- Metaspace (native memory)
|     +-- Class metadata
|     +-- Class-loader-related metadata
|
+-- Threads
|     +-- Thread A's Java stack
|     +-- Thread B's Java stack
|     +-- Native stack / related native regions
|
+-- Code cache (native memory)
|
+-- Direct buffers / mapped regions
|
+-- JVM, GC, JIT, and other native libraries
```

This diagram only illustrates conceptual groups. The exact physical layout depends on the JVM implementation, operating system, architecture, and runtime configuration.

## 2. Distinguishing the JVM Specification model from HotSpot's implementation

The JVM Specification describes the **runtime data areas** that a JVM must provide semantically. It does not require every implementation to use the exact same physical memory layout.

The described runtime data areas include:

| Runtime data area | Scope | Role |
|---|---|---|
| PC register | Per thread | Tracks the location of the bytecode instruction currently being executed |
| Java Virtual Machine stack | Per thread | Holds frames for method invocations |
| Heap | Shared | Allocates objects and arrays |
| Method area | Shared | Stores per-class structures such as metadata, runtime constant pool, and method code according to the specification model |
| Runtime constant pool | Per class/interface, part of the method area per specification | Holds constants and symbolic references used during linking |
| Native method stack | Per thread | Supports native method execution; implementation depends on the JVM |

In HotSpot Java 17:

- The heap is the managed memory region handled by the garbage collector.
- Class metadata is stored in **Metaspace**, outside the heap.
- Machine code compiled by the JIT is stored in the **Code Cache**, outside the heap.
- Direct buffers can use native memory.
- Each platform thread has its own stack region.

You should not equate a name in the JVM Specification with a specific physical allocation region in HotSpot. For example, the **method area** is an abstract concept in the specification; **Metaspace** is how HotSpot implements most of class metadata.

## 3. Heap: the storage area for objects and arrays

### 3.1. What is the heap?

The heap is a memory region shared across threads in a JVM process. When a program creates an object or array, memory for the object is typically allocated on the heap:

```java
public class HeapDemo {
    public static void main(String[] args) {
        User user = new User("An");
        int[] scores = new int[1_000];
    }
}

class User {
    private final String name;

    User(String name) {
        this.name = name;
    }
}
```

In this example:

- The local variable `user` holds a reference to a `User` object.
- The `User` object is typically allocated on the heap.
- The local variable `scores` holds a reference to an array.
- The `int[]` array is allocated on the heap.

A reference variable can reside in a stack frame, in a field of another object, or in another data area. **A reference and the referenced object are two different things.**

This is a useful mental model for understanding a program. The JVM can optimize via escape analysis, scalar replacement, or allocation elimination as long as observable behavior does not change. Therefore, you should not assume that every `new` expression necessarily results in a physical heap allocation in every case.

### 3.2. The heap is shared across threads

Threads in the same JVM can hold references to the same object:

```java
class Counter {
    int value;
}

Counter shared = new Counter();

Thread first = new Thread(() -> shared.value++);
Thread second = new Thread(() -> shared.value++);

first.start();
second.start();
```

Both threads access the same `shared` object. Because the heap is shared, concurrent access must follow the Java Memory Model. If multiple threads write to a field without proper synchronization, the program can encounter a race condition.

Mechanisms such as `synchronized`, `volatile`, locks, or synchronization constructs in `java.util.concurrent` are used to control access and visibility. Placing an object on the heap does not automatically make it thread-safe.

### 3.3. The garbage collector manages the heap

Java has a garbage collector (GC) to reclaim heap memory from objects that are no longer reachable from GC roots. Common roots include:

- References from the stacks of running threads.
- References from static fields held by live classes.
- JNI references and certain internal JVM roots.

When an object no longer has a reference path from any root, it can become eligible for collection. The timing of collection is decided by the JVM/GC; a program cannot request exactly which object is freed at an exact moment.

Example:

```java
User user = new User("An");
user = null;
```

After assigning `null`, the variable `user` no longer references the old object. If no other references remain, the object can become unreachable. That **does not mean GC runs immediately**.

### 3.4. Object lifecycle and memory leaks in Java

Java automatically collects objects that are no longer reachable, yet an application can still suffer from a memory leak when it retains references to objects that are no longer needed:

```java
static final List<byte[]> CACHE = new ArrayList<>();

static void addPayload() {
    CACHE.add(new byte[1024 * 1024]);
}
```

Each call to `addPayload()` keeps an additional 1 MiB array in the static list. The arrays remain reachable via `CACHE`, so GC cannot reclaim them even when business logic no longer uses them.

Common causes include:

- Unbounded collections/caches or missing eviction policies.
- Listeners/callbacks that are registered but never unregistered.
- Thread-locals holding large objects for too long.
- Static fields holding objects for the entire application lifecycle.
- Class loaders not being released because references remain elsewhere.

A heap memory leak is a **reference lifecycle** problem, not necessarily a garbage collector bug.

### 3.5. Sizing the heap in Java 17

Common JVM options:

| Option | Meaning |
|---|---|
| `-Xms<size>` | Initial heap size |
| `-Xmx<size>` | Maximum heap size |
| `-XX:MaxRAMPercentage=<n>` | Maximum percentage of RAM the JVM uses to derive the heap limit when `-Xmx` is not set directly |

Example:

```bash
java -Xms512m -Xmx2g -jar app.jar
```

This example sets the initial heap to 512 MiB and the maximum limit to 2 GiB. It does not mean the entire Java process uses at most 2 GiB; Metaspace, thread stacks, direct buffers, the code cache, and other native regions still require their own memory.

When choosing a heap size, consider the number and size of concurrently live objects, allocation rate, object survival rate across GC cycles, acceptable GC latency, and the actual RAM limit of the machine or container.

Increasing `-Xmx` can allow the application to hold more live objects, but it does not fix a memory leak on its own and can cause the process to exceed the container's RAM limit.

## 4. Stack: a thread-private data area

### 4.1. What does the Java stack contain?

Each thread has its own Java Virtual Machine stack. The stack holds **frames** corresponding to active method invocations.

A frame has these main components:

- Local variable array: the method's parameters and local variables.
- Operand stack: an intermediate area where bytecode performs operations and invokes methods.
- Information supporting dynamic linking and method return.

Example:

```java
static int calculate(int base) {
    int factor = 3;
    int result = base * factor;
    return result;
}

public static void main(String[] args) {
    int answer = calculate(10);
    System.out.println(answer);
}
```

When `main` calls `calculate`, the JVM creates a frame for the `calculate` invocation. When the method finishes, its frame is popped from the stack and control returns to the caller.

Conceptual diagram:

```text
Thread A - Java stack

Top of stack
  +---------------------------+
  | Frame calculate()         |
  | local: base, factor,      |
  |        result             |
  | operand stack             |
  +---------------------------+
  | Frame main()              |
  | local: args, answer       |
  | operand stack             |
  +---------------------------+
Bottom of stack
```

A frame exists only as long as the corresponding method invocation is active. That is why the stack fits data whose lifecycle is tied to the call chain.

### 4.2. A local variable does not mean the object lives on the stack

Example:

```java
void process() {
    int count = 10;
    User user = new User("An");
}
```

`count` is a local primitive value and `user` is a local reference variable. Under the JVM model, they belong to the frame's local variables area. The `User` object is normally on the heap.

You should not conclude that every local variable is "stack memory" in the sense that every value is always stored in a physical stack slot. The JIT can keep values in registers or optimize frames; the specification defines behavior rather than forcing every physical layout detail.

### 4.3. Stack overflow

Each thread has a stack limit. When a call chain is too deep or recursion has no stopping condition, the stack can be exhausted:

```java
public class StackOverflowDemo {
    static void recurse() {
        recurse();
    }

    public static void main(String[] args) {
        recurse();
    }
}
```

The program can throw `StackOverflowError`. This error commonly occurs due to infinite/excessively deep recursion or overly nested call chains.

The right fix is to correct the algorithm, add a base case, switch to a loop when appropriate, or reduce call depth. Increasing the stack size only helps when valid stack demand exceeds the default; it does not fix infinite recursion.

### 4.4. Adjusting the stack size

Commonly used option:

```bash
java -Xss1m -jar app.jar
```

`-Xss` sets the stack size per platform thread, subject to the JVM implementation and operating system. The default value depends on the environment and should not be assumed identical across all machines.

Total stack memory can become significant when an application creates many threads. Illustrative example: if there are 300 threads and each stack is configured at 1 MiB, total reserved stack space can reach hundreds of MiB, not counting other native regions. This is a budgeting estimate; actual RSS depends on how much stack is actually touched and how the operating system allocates memory.

### 4.5. Differences between stack and heap

| Criterion | Stack | Heap |
|---|---|---|
| Scope | Private to each thread | Shared across the JVM |
| Typical contents | Frames, local variables, operand stack | Objects and arrays |
| Lifecycle | Tied to method invocations / thread | Tied to reachability and GC |
| Management | Frames are pushed/popped on call/return | Garbage collector manages objects |
| Common error | `StackOverflowError` | `OutOfMemoryError: Java heap space` |
| HotSpot tuning | `-Xss` | `-Xms`, `-Xmx` |

## 5. Metaspace: class metadata in HotSpot

### 5.1. What is Metaspace?

Metaspace is the native memory region HotSpot uses to store metadata for loaded classes. Metadata can include information about:

- Class/interface structure and inheritance hierarchy.
- Methods, fields, and related attributes.
- The runtime constant pool and data supporting class linking as implemented by HotSpot.
- Information used by reflection, the verifier, and the runtime.

Metaspace is **not where ordinary instances** of a class are stored. For example, a `User` object created via `new User(...)` normally resides on the heap; the metadata describing the `User` class resides in the metadata area managed by HotSpot.

### 5.2. Metaspace is outside the Java heap

In HotSpot Java 17, Metaspace uses native memory. Therefore:

- Increasing `-Xmx` does not directly increase the Metaspace limit.
- The heap can still have free space while the JVM runs out of Metaspace.
- The process can consume more RAM than `-Xmx` because of Metaspace and other native regions.

Since Java 8, HotSpot has used Metaspace instead of the PermGen area from older Java versions. When configuring Java 17, work with Metaspace; PermGen options are no longer the appropriate way to manage memory.

### 5.3. Class loaders affect metadata lifecycle

Metadata is tied to the loaded class and the class loader that manages it. When a class loader becomes eligible for collection, the classes defined by that loader can be unloaded, and their corresponding metadata can be reclaimed.

A common example is an application server that redeploys an application multiple times. Each deploy creates a new class loader. If a long-lived component (static registry, thread, ThreadLocal, listener, cache, or native library) still holds a reference to an old class loader, that loader cannot be collected. Metadata for the old classes continues to occupy Metaspace.

This is one cause of a **class loader leak** and can lead to:

```text
java.lang.OutOfMemoryError: Metaspace
```

You should not treat raising the Metaspace limit as the default final solution. Investigate why the class loader is not being unloaded or why the application is loading too many classes.

### 5.4. Tuning Metaspace

Common HotSpot options:

| Option | Meaning |
|---|---|
| `-XX:MetaspaceSize=<size>` | Initial threshold related to triggering GC to process class metadata; not the maximum limit |
| `-XX:MaxMetaspaceSize=<size>` | Maximum limit for Metaspace |
| `-XX:CompressedClassSpaceSize=<size>` | Size of the address space reserved for compressed class space when compressed class pointers are used |

Example:

```bash
java -XX:MetaspaceSize=128m -XX:MaxMetaspaceSize=512m -jar app.jar
```

The values above illustrate syntax only, not a recommended configuration for all applications. `MetaspaceSize` is a GC threshold that the JVM can adjust, and should not be interpreted as "the JVM allocates only 128 MiB for metadata." `MaxMetaspaceSize` is the actual upper limit.

## 6. Off-heap / native memory

### 6.1. Off-heap is a broad concept

"Off-heap" is commonly used to refer to memory used by the application/JVM outside the Java heap. It is not a single region with a single manager. Sources of consumption can include:

- Thread stacks and native stacks.
- Metaspace.
- JIT code cache.
- Direct byte buffers.
- Memory-mapped files.
- Garbage collector and runtime data structures.
- Native/JNI libraries.
- Native allocator, TLS, socket buffers, and related OS components.

Therefore, when measuring process RAM, you cannot look only at heap usage.

### 6.2. Direct ByteBuffer

`ByteBuffer.allocateDirect()` creates a direct buffer whose data is stored in a memory region suitable for native I/O:

```java
import java.nio.ByteBuffer;

public class DirectBufferDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
        buffer.putInt(42);
        buffer.flip();

        System.out.println(buffer.getInt());
    }
}
```

The `ByteBuffer` wrapper object is a Java object on the heap, whereas the direct buffer's data region is allocated off-heap. This can reduce extra copies in I/O paths, depending on the API and operating system.

Direct buffers are not free:

- The native memory region still consumes RAM/address space.
- Allocation and reclamation have overhead.
- Creating too many direct buffers or holding references too long can exhaust native memory.
- Reclaiming native memory is tied to the buffer's lifecycle/cleaner; you should not rely on `System.gc()` to free it deterministically.

The total direct buffer limit can be configured with:

```bash
java -XX:MaxDirectMemorySize=512m -jar app.jar
```

When the limit is exceeded, the application may encounter:

```text
java.lang.OutOfMemoryError: Direct buffer memory
```

Choose the limit based on the total number of concurrent buffers, the size of each buffer, their lifecycle, and the process's native memory budget.

### 6.3. Memory-mapped files

`FileChannel.map()` creates a memory region mapped to a file:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedFileDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.bin");

        try (FileChannel channel = FileChannel.open(
                path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, channel.size());

            mapped.put(0, (byte) 42);
        }
    }
}
```

The mapped region is tied to the file and the operating system. Data pages can be faulted into RAM on demand; they are not accounted for like ordinary heap objects. A large mapping can increase virtual address space and OS memory pressure, even if not all of the mapping is resident in RAM at once.

When using mappings:

- Limit file sizes and mapped regions.
- Close `FileChannel` when normal I/O operations finish.
- Understand that a mapping's lifecycle has its own rules; closing the channel does not necessarily make the mapped region disappear immediately.
- Monitor OS address space, page cache, and file resource limits.

### 6.4. Code Cache

The HotSpot JIT compiles bytecode into machine code to speed up frequently executed code paths. Machine code is stored in the **Code Cache**, which is a native memory region.

The Code Cache can grow as the application runs and the JIT compiles more methods. If the code cache is too small or full, the JVM may restrict or stop compiling additional methods, degrading performance. This is not the Java heap, and heap GC does not reclaim code cache space like ordinary objects.

A related option:

```bash
java -XX:ReservedCodeCacheSize=256m -jar app.jar
```

Adjust this only when diagnostic data shows the Code Cache is a bottleneck. Do not raise every native limit just because RSS is high.

### 6.5. Threads and native memory

Each platform thread requires operating system resources and a stack region. Creating too many threads can:

- Increase total reserved stack space.
- Increase JVM and OS thread management structures.
- Increase context switching and scheduler pressure.
- Cause `Thread.start()` to fail with a native thread creation error.

Example error you may see:

```text
java.lang.OutOfMemoryError: unable to create native thread
```

This error is not necessarily caused by a full heap. Check thread count, OS/container process limits, stack size, native memory, and user resource limits.

## 7. How do heap, Metaspace, and off-heap interact?

An application can have free space on the heap and still fail to allocate new objects or threads because another region is exhausted. Conversely, the heap can be full while Metaspace still has plenty of room.

| Area | Primary contents | Manager / Reclaimer | Common options or tools |
|---|---|---|---|
| Heap | Objects, arrays | GC | `-Xms`, `-Xmx`, GC logs, heap dump |
| Java stack | Per-thread frames | Push/pop per call | `-Xss`, thread dump |
| Metaspace | Class metadata | Class unloading / HotSpot | `-XX:MaxMetaspaceSize`, `jcmd VM.metaspace` |
| Direct memory | Direct ByteBuffer data | Buffer cleaner/lifecycle and JVM | `-XX:MaxDirectMemorySize`, NMT |
| Code Cache | JIT compiled code | JVM code cache management | `-XX:ReservedCodeCacheSize`, compiler/code cache logs |
| Native libraries | Regions allocated via JNI / native allocator | Managed by the library or native code | Partial NMT, profiler / OS tools |
| Memory mapping | File-mapped pages | OS and mapping lifecycle | OS memory maps, process tools |

One way to budget memory:

```text
Total process RAM
  ≈ Java heap
  + Metaspace
  + thread stacks
  + resident direct/mapped memory
  + Code Cache
  + GC/JVM/native structures
  + native libraries
  + OS regions charged to the process
```

This is a budgeting model, not an exact addition formula: reserved, committed, shared pages, and resident pages are measured differently.

## 8. Why is process RSS larger than -Xmx?

`-Xmx` only caps the maximum Java heap size. It does not set a total memory limit for the Java process.

Suppose an application has:

- Maximum heap of 2 GiB.
- Maximum Metaspace of 300 MiB.
- Maximum direct buffers of 512 MiB.
- 200 threads with stacks configured at 1 MiB.
- Code cache and other JVM/native structures.

The total budget can easily exceed 2 GiB. Therefore, a container with a 2 GiB memory limit is not safe just because the JVM sets `-Xmx2g`; native regions will need additional space.

When running in a container, leave headroom for native memory and the operating system. Java 17 on supported platforms can detect container limits for ergonomics, but an explicit `-Xmx` setting still needs to fit within the overall budget. Check actual container limits and process RSS metrics rather than inferring from heap usage alone.

## 9. Common memory errors

| Message / Error | Commonly involved region | Initial investigation direction |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Heap | Heap dump, dominator tree, retained size, allocation rate, caches, and reference leaks |
| `OutOfMemoryError: GC overhead limit exceeded` | Heap / GC pressure | Check live set, allocation, GC logs, and whether the application is nearing heap exhaustion |
| `OutOfMemoryError: Metaspace` | Metaspace | Class count, class loaders, redeploy leaks, Metaspace limit |
| `OutOfMemoryError: Direct buffer memory` | Direct memory | Count/size of direct buffers, buffer lifecycle, and direct memory limit |
| `OutOfMemoryError: unable to create native thread` | Native / thread resources | Thread count, `-Xss`, OS/container limits, native memory |
| `StackOverflowError` | Thread stack | Recursion, deep call chains, repeated callbacks |
| `OutOfMemoryError: Requested array size exceeds VM limit` | Array size / VM limit | Input size, length overflow calculation, and chunking design |

An error message is only an initial symptom. Correlate logs, heap dumps, thread dumps, and native memory metrics to determine the actual root cause.

## 10. Memory observation tools in Java 17

### 10.1. Viewing VM settings

```bash
java -XshowSettings:vm -version
```

This command prints several VM configuration details, useful for confirming the JVM in use and general limits.

### 10.2. Using jcmd

`jcmd` is a diagnostic tool included with the JDK. For example, given the Java process PID:

```bash
jcmd <pid> GC.heap_info
jcmd <pid> VM.metaspace
jcmd <pid> Thread.print
```

Meaning:

- `GC.heap_info`: overview of heap and GC information.
- `VM.metaspace`: Metaspace statistics.
- `Thread.print`: prints thread stack traces.

Command names and detail levels depend on the JVM build; use `jcmd <pid> help` to see available commands.

### 10.3. Native Memory Tracking

HotSpot includes **Native Memory Tracking (NMT)** to track several categories of native memory managed by the JVM. It must be enabled at JVM startup:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Or choose `detail` for more granular information, at a higher tracking overhead:

```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Once enabled, you can query it:

```bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory detail
```

NMT is useful for comparing categories such as Java Heap, Class/Metaspace, Thread, Code, GC, and Internal. NMT does not measure every native allocation from every third-party library; cross-check with OS tools or profilers when RSS does not match.

### 10.4. Enabling GC logs in Java 17

Java 17 uses Unified Logging:

```bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

GC logs help you inspect:

- Heap before/after GC runs.
- Pause frequency and duration.
- GC phases.
- Occupancy changes over time.

Do not use a single heap usage number to conclude there is a memory leak. Observe the post-GC trend and correlate with workload.

### 10.5. Creating a heap dump on OutOfMemoryError

You can instruct the JVM to write a heap dump when an OOME occurs:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./dumps -jar app.jar
```

A heap dump helps analyze which objects are retaining large amounts of memory. It does not capture all types of native memory; if the error involves Metaspace, direct memory, or native threads, you also need NMT, thread dumps, and appropriate tools.

Heap dumps can be large and contain sensitive application data. Store the files in a location with sufficient disk space and controlled access permissions.

## 11. Example scenario analyses

### Scenario A — Heap grows continuously after every request

Symptoms:

- Heap occupancy increases over time.
- After Full GC, live object volume keeps growing.
- Eventually `Java heap space` may occur.

Investigation steps:

1. Capture heap dumps at appropriate intervals.
2. Compare histograms/dominator trees between dumps.
3. Find collections/caches/static fields retaining objects.
4. Check listeners, ThreadLocals, and reference chains.
5. Set cache size limits or unregister resources promptly.

Increasing `-Xmx` can delay the failure, but if the live set keeps growing without bound, the root cause remains.

### Scenario B — Heap is stable, but the container is OOM killed

Symptoms:

- Heap usage is below `-Xmx`.
- Process RSS is high.
- The container exceeds its memory limit and is terminated by the OS.

Investigation steps:

1. Check direct buffers and memory mappings.
2. Check Metaspace, Code Cache, and NMT.
3. Check thread count and `-Xss`.
4. Check JNI/native libraries.
5. Compare RSS with cgroup/container metrics.

Do not increase `-Xmx` in this scenario before identifying the native memory consumer.

### Scenario C — Repeated redeploys lead to Metaspace OOME

Symptoms:

- With each redeploy, class count or Metaspace usage grows.
- Old class loaders are not collected.

Investigation steps:

1. Use `jcmd <pid> VM.metaspace` and class histograms to inspect.
2. Look for threads or ThreadLocals retaining old class loaders.
3. Check static registries, logging/plugin frameworks, and listeners.
4. Check dependencies that spawn threads or register callbacks without cleanup.
5. Fix class loader lifecycles; only increase `MaxMetaspaceSize` when legitimate usage genuinely requires more space.

### Scenario D — Unable to create more threads

Symptoms:

```text
OutOfMemoryError: unable to create native thread
```

Investigation steps:

1. Count threads using a thread dump or process management tools.
2. Check whether thread pools are bounded or spawning threads unchecked.
3. Check OS and container process/thread limits.
4. Check stack size and total native memory.
5. Prefer bounding concurrency and using properly configured executors.

Increasing the heap usually does not resolve native thread creation failures.

## 12. Principles for configuring memory in Java 17 applications

### 12.1. Plan the total budget, not just Xmx

Before deploying, determine:

- Machine/container RAM limit.
- Expected maximum heap.
- Expected Metaspace and limit if needed.
- Maximum thread count and stack per thread.
- Direct buffer/mapped memory.
- Code Cache and JVM native structures.
- Native memory of third-party libraries.
- Headroom for the OS and load fluctuations.

### 12.2. Measure before tuning

Do not raise all limits at once. Collect GC logs, heap dumps, NMT, and thread dumps to identify which region is under pressure.

### 12.3. Distinguish capacity from leaks

- **Capacity issue:** legitimate workload needs more memory than the current limit.
- **Leak:** memory is not freed because references remain or resources are not closed.
- **Native pressure:** memory outside the heap grows even though the heap does not grow proportionally.

These three situations require different fixes.

### 12.4. Bound resources at the application layer

- Limit caches, queues, and batch sizes.
- Use bounded thread pools.
- Close files, sockets, and resources on time.
- Manage direct buffers with an appropriate lifecycle.
- Limit request sizes and input payloads.
- Avoid creating large unnecessary objects in hot loops.

## 13. Common misconceptions

| Misconception | Reality |
|---|---|
| `-Xmx` is the RAM limit of the entire process | `-Xmx` only limits the Java heap |
| An object is always physically on the heap because code uses `new` | The JVM can optimize allocations if observable behavior does not change |
| A local variable is an object on the stack | A local variable can be a primitive or a reference in a frame; the referenced object is normally on the heap |
| The stack is shared across threads | Each thread has its own JVM stack |
| Increasing `-Xss` always solves StackOverflowError | It only increases stack capacity; infinite recursion still fails and each thread requires more resources |
| GC reclaims every kind of process memory | GC manages heap objects; native memory has its own lifecycle/management |
| Metaspace holds all objects of a class | Metaspace holds class metadata; ordinary instances are on the heap |
| Metaspace is part of `-Xmx` | In HotSpot, Metaspace uses native memory outside the heap |
| DirectByteBuffer does not use RAM | The direct buffer's data region still consumes native memory |
| If the heap has free space, OOME cannot happen | Metaspace, direct memory, native threads, or stacks can still be exhausted |
| RSS must be less than or equal to `-Xmx` | RSS includes resident heap plus many other native regions |
| NMT measures all native memory of every library | NMT tracks many regions managed by HotSpot but does not cover every external allocator |

## 14. Practice exercises

### Exercise 1 — Classify memory regions

For each item below, identify the most appropriate memory region:

1. A `Customer` object created with `new`.
2. An `int count` variable in a method call.
3. Metadata describing the `Customer` class in HotSpot.
4. Data of `ByteBuffer.allocateDirect(4096)`.
5. The frame of an actively executing method on a thread.
6. Machine code compiled by the JIT.

**Hint:** Heap; local variable/frame; Metaspace; direct/native memory; Java stack; Code Cache.

### Exercise 2 — Error analysis

An application has `-Xmx4g`, heap usage is only around 1.5 GiB, yet it still hits:

```text
java.lang.OutOfMemoryError: Metaspace
```

Explain why increasing `-Xmx` does not directly solve the error. List the metrics to collect and several causes of a class loader leak.

### Exercise 3 — Calculate stack budget

A service has at most 250 platform threads and is configured with `-Xss1m`.

- Estimate the total stack space reserved according to the configuration.
- Why might actual RSS be lower than or different from this product?
- If the thread count doubles, what changes?

### Exercise 4 — Read JVM configuration

Explain the meaning of:

```bash
java -Xms512m -Xmx2g -Xss1m \
     -XX:MaxMetaspaceSize=512m \
     -XX:MaxDirectMemorySize=256m \
     -XX:NativeMemoryTracking=summary \
     -jar app.jar
```

Name at least three memory groups that can still cause total process RAM to exceed 2 GiB.

### Exercise 5 — Choose diagnostic tools

Choose the right tool for each goal:

- Inspect heap and GC.
- Inspect Metaspace.
- Inspect thread stack traces.
- Inspect native memory groups managed by HotSpot.
- Find objects retaining large amounts of heap.

**Hint:** `jcmd GC.heap_info`, `jcmd VM.metaspace`, `jcmd Thread.print`, `jcmd VM.native_memory summary`, heap dump and heap analysis tools.

### Exercise 6 — Design limits

An API creates a direct buffer of a size sent by the client. List the limits that should be placed at the request and JVM layers to prevent uncontrolled native memory allocation. Explain why setting `-Xmx` alone is not enough.

## 15. Official Java 17 documentation

- [Java Virtual Machine Specification 17 — Chapter 2: The Structure of the Java Virtual Machine](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html): runtime data areas, heap, stack, method area, PC register, and native method stack.
- [Java SE 17 API — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): heap memory information reported by the runtime.
- [Java SE 17 API — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): heap buffers and direct buffers.
- [Java SE 17 API — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): memory-mapped files via `map`.
- [Java 17 HotSpot Virtual Machine Options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): JVM options such as heap, stack, Metaspace, and direct memory.
- [Java 17 jcmd man page](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): diagnostic tool for JVM processes.
- [JEP 122 — Remove the Permanent Generation](https://openjdk.org/jeps/122): background on moving class metadata to native memory; when configuring Java 17, use Metaspace instead of old PermGen options.

**Key takeaway:** The heap holds objects and arrays and is managed by GC; each thread has its own Java stack holding call frames; HotSpot's Metaspace stores class metadata in native memory; and off-heap is a broad group including direct buffers, the code cache, thread/native stacks, memory mappings, and other JVM/native regions. `-Xmx` does not cap total process RAM. To investigate accurately, combine GC logs, heap dumps, thread dumps, Metaspace statistics, Native Memory Tracking, and operating system metrics.
