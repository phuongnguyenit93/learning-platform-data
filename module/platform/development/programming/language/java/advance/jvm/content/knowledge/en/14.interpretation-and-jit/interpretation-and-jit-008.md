# Code Cache, Compiler Threads, and JIT Resource Costs

## 1. Overview

**Just-in-time (JIT) compilation** allows the HotSpot JVM to compile frequently used Java bytecode methods into **native machine code** while the program is running. The interpreter can begin executing a method quickly without waiting for optimizing compilation; after collecting information about which code segments are truly hot, the JIT generates native code to improve performance.

JIT is not free: it consumes **CPU on compiler threads**, uses **native memory** for the compilation process, requires **code cache** to store machine code, has a **warm-up** period, and may have to **deoptimize/recompile** when optimization assumptions no longer hold. In large applications, JIT can create resource pressure even when the Java heap is not full or GC is operating normally.

The **code cache** is HotSpot's internal memory region for storing generated machine code and appropriate VM code blobs; it is **distinct from the Java heap, Metaspace, class-file bytecode, and the run-time constant pool**. This is a HotSpot implementation detail, not a region named Code Cache required to be identical across every JVM in the Java Virtual Machine Specification (JVMS).

After completing this lesson, you will be able to:

- Describe the pipeline **bytecode → interpreter/profiling → compilation queue → C1/C2 compiler threads → compiled nmethod → code cache**.
- Explain **tiered compilation levels**, the differences between C1/C2, OSR, inlining, speculative optimization, and deoptimization.
- Distinguish the partitions of the **segmented code cache**: non-method, profiled methods, non-profiled methods.
- State the sources of CPU/native memory usage by compiler threads and their impact on startup, throughput, and latency.
- Understand **code cache full**, fragmentation, flushing, sweeping, code unloading, and why performance can degrade even when the Java heap still has space.
- Understand HotSpot flags **ReservedCodeCacheSize**, **InitialCodeCacheSize**, **CICompilerCount**, **TieredCompilation**, **TieredStopAtLevel**, and tools for inspecting configuration.
- Use **jcmd Compiler.codecache/queue/codelist**, **PrintCompilation**, **JFR**, **Native Memory Tracking**, and benchmarking within the proper information scope of each tool.
- Avoid confusing **reserved/committed/used**, JIT CPU with application CPU, and the compiler queue with a request queue.

Examples are oriented toward **HotSpot 64-bit Java 17**, using Java 17+ for runnable programs. Flags, code-cache layout, thread policy, and log formats may vary by vendor/JDK/platform; check your specific JVM before drawing conclusions.

## 2. Bytecode to Native Code Diagram

~~~text
                     javac
  MyCode.java --------------------> MyCode.class
                                       |
                                       | Java bytecode / method metadata
                                       v
                               Class loading/linking
                                       |
                                       v
                                JVM Interpreter
                                       |
                           Invocation/backedge counts
                           Type/branch profiling
                                       |
                                       v
                               Compile Task Queues
                                /             \
                               v               v
                         C1 Compiler       C2 Compiler
                         (faster, tiers)  (optimizing)
                               \               /
                                v             v
                                 Native code
                                 nmethod blobs
                                      |
                                      v
                                   Code Cache
                                      |
                                      v
                          CPU executes compiled code
                                      |
                    assumption invalid / uncommon trap?
                                      v
                              Deoptimization
                              Fallback / Recompile
~~~

The diagram is a **behavioral model** and does not guarantee that every method goes through every step. A method may only be interpreted; a loop may be compiled via **on-stack replacement (OSR)**; a callee may be inlined instead of having an independent native code entry. Runtime VM stubs may also be stored in the code cache.

### 2.1. Java Class Files and Code Cache Are Different

| Component | Meaning | Where stored/observed |
| --- | --- | --- |
| **Java source** | Code written by the programmer | .java |
| **Bytecode** | Portable instructions emitted by javac/compiler | Code attribute in .class; read with javap -c |
| **Class metadata** | Names, fields, methods, constant pool, descriptors, and runtime structures | Metaspace/VM structures in HotSpot |
| **JIT native code** | CPU-specific instructions compiled from bytecode | **Code cache** |
| **VM/interpreter stubs** | Generated code serving execution/state transitions | Code cache by code blob type |
| **Java objects/arrays** | Business data/instance state | Java heap |

**javap -c** displays **bytecode**, not the C2 machine instructions generated after runtime. An nmethod in the code cache is not a new .class file, and there is no Java source API to dump it like a Java object.

### 2.2. Code Cache Is Different from Method Area

JVMS §2.5.4 describes the **method area** at an abstract level as containing per-class structures and the code for methods/constructors. HotSpot implements class metadata and JIT native-code memory using multiple separate mechanisms. Do not assume that JVMS requires every JVM to have **Metaspace** and **Code Cache** like HotSpot.

## 3. Why Are Compiler Threads Needed?

Optimizing compilation can be very CPU-intensive due to:

- Parsing bytecode and building an intermediate representation (IR).
- Control-flow/data-flow analysis and speculative type profiling.
- Inlining, devirtualization, constant propagation.
- Escape analysis, scalar replacement in appropriate cases.
- Loop transformations, range-check elimination, and dead-code elimination.
- Instruction selection, scheduling, register allocation.
- Generating machine code and metadata for deoptimization/GC/debugging.

If an application thread were always forced to wait for full compilation, response latency would depend directly on the complexity of new methods. **Background compilation** allows HotSpot to keep running the interpreter or an older compiled version while compiler threads process requests in the queue.

~~~text
Application Thread A       Application Thread B
  calls hot()                runs requests
       |                          |
       +-- counters/profile       |
               |                  |
               v                  |
          Compile Queue           |
             |                    |
      C1 / C2 CompilerThread      |
             |                    |
       compiled code installed    |
             |                    |
             +-- next hot() calls execute compiled version
~~~

Compiler threads still belong to the **same JVM process**; they require CPU and native stacks, and can contend for cache, memory bandwidth, and cgroup CPU quota with mutators and GC threads. Background does not mean zero impact on the application.

### 3.1. A Compiler Thread Is Not javac

**javac** runs in the build toolchain, producing .class bytecode. **C1/C2 compiler threads** run while the JVM is executing the application to produce native code for a specific CPU. Successful javac compilation does not prove that the runtime JIT has compiled all methods.

### 3.2. Compile Task Lifecycle

For a hot method to run as JIT code, it typically must:

1. Have appropriate invocation/backedge counts or profiling information.
2. Be permitted and selected for compilation by the compilation policy.
3. Enter the compilation queue with the corresponding tier/mode.
4. Be picked up by a compiler thread for processing.
5. Complete compilation without errors or task abandonment.
6. Have code-cache capacity to install the new nmethod.
7. Be used by the VM as the entry point for subsequent invocations.

**A hot method is not necessarily compiled immediately.** If CPU quota is low, the queue is backlogged, or the code cache is full, the interpreter/C1 version may continue to be used longer.

## 4. Tiered Compilation: Level 0 to Level 4

HotSpot Java 17 typically uses **tiered compilation**, combining the interpreter, **C1 (client/compiler1)**, and **C2 (server/compiler2)** to balance compilation speed and optimization quality.

| Typical Level | Tool/Operation | Role |
| --- | --- | --- |
| **0** | Interpreter | Executes bytecode, collects counters |
| **1** | C1 code without full profiling | Fast compilation, low profiling overhead |
| **2** | C1 with limited profiling | Partial profile data |
| **3** | C1 with full profiling | C1 code that also accumulates data for C2 |
| **4** | C2 optimizing compiler | Deeply optimized code for hot paths |

This is the **HotSpot tiered compiler** mapping under suitable conditions, **not a mandatory 0→1→2→3→4 sequence for every method**. The JVM can skip levels, jump directly to a tier based on heuristics, or use OSR compilation for loops.

### 4.1. Why Not Compile Everything with C2 from the Start?

C2 can generate fast machine code at runtime, but it costs significant compilation CPU, time, and native memory. A method that only runs twice is not worth 30 ms of optimizing compilation if interpreted execution only takes microseconds.

C1 produces code early at low cost to improve warm-up throughput; C2 focuses on methods whose long-term benefit outweighs compilation cost.

### 4.2. C1 vs C2 Are Not Completely Separate

C1 can produce profiled code, providing the type information that C2 relies on. C2 uses profiling and assumptions to inline/devirtualize/optimize more aggressively. The same method can be compiled at multiple tiers during its runtime lifecycle.

### 4.3. TieredStopAtLevel

Experimental example:

~~~bash
java -XX:+TieredCompilation -XX:TieredStopAtLevel=1 MyMain
~~~

**MyMain** must be an actual main class. Capping at a lower tier can shorten CPU warm-up but yields worse steady-state throughput on hot methods. Do not treat this flag as a default recommendation.

Disabling tiered compilation with **-XX:-TieredCompilation** does not mean disabling JIT. In the HotSpot Server VM, the non-tiered compiler can still run. **-Xint** is used to observe interpreter-only execution in supported environments; **-Xcomp** prioritizes aggressive compilation, which can increase startup/resource costs.

## 5. Profile-Guided Speculative Optimization

Suppose a method processes an interface:

~~~java
// Illustrative snippet, not a standalone runnable file:
long total = 0;
for (Shape shape : shapes) {
    total += shape.area();
}
~~~

If a call site mostly sees the Circle implementation, C2 can use the profile to optimize the call path, even inlining Circle's operations with runtime guards. Later, if a new Shape implementation appears and invalidates the type-profile assumption, the JVM must preserve semantics and may **deoptimize and recompile**.

### 5.1. Inlining: Benefits and Costs

Inlining eliminates call overhead and opens optimization opportunities across method boundaries. However, embedding many callees into a caller can bloat compiled code, increasing:

- Compilation time.
- Native code-cache occupation.
- Instruction cache/iTLB pressure.
- Deoptimization metadata cost.
- Register pressure on some paths.

Therefore, inlining is controlled by HotSpot heuristics/cost models; “inline all methods” is not always better.

### 5.2. Deoptimization Is Not Necessarily an Error

Compiled code based on assumptions can be invalidated by class loading, uncommon control flow, or other runtime information. The VM falls back to a less optimized/interpreted state and recompiles if needed.

~~~text
Optimized nmethod
      |
      +-- assumption invalidated / uncommon trap
                 |
                 v
              Deopt
                 |
           fallback execution
                 |
          more profile data
                 |
             Recompile
~~~

This preserves Java semantics. A few deopts after warm-up are normal; if they happen continuously under the same workload, they can cause code cache churn and increased compiler CPU.

### 5.3. Why Can One Method Have Multiple Compiled Versions?

The same method can have a C1 profiled nmethod, a C2 optimized nmethod, one or more OSR versions, and older versions marked not entrant. Callee code can also be inlined into callers, so **the number of nmethods does not equal the number of methods in source code**.

## 6. On-Stack Replacement (OSR)

A method with a long loop can become hot **before the method returns for the first time**. **OSR** allows HotSpot to switch execution between interpreted/C1 and a compiled version at an appropriate point inside the loop.

~~~java
long value = 0;
for (int i = 0; i < 10_000_000; i++) {
    value += i % 7;
}
~~~

Backedge counters can exceed the threshold while the method is still inside the loop. The VM may request OSR compilation, though there is no guarantee every run of the code above triggers OSR: JIT heuristics, method size, CPU, compile queue, flags, and optimizations can vary.

**-XX:+PrintCompilation** sometimes displays OSR markers; do not rely on a fixed compilation ID or log line. Distinguish an **OSR compiled version** from a **regular method-entry compiled version**.

## 7. What Does the Code Cache Store?

The **code cache** is a HotSpot-managed region for storing **code blobs**, for example:

- Nmethods containing machine instructions generated by C1/C2.
- Runtime stubs/adapters.
- Certain generated code for interpreter/transition paths.
- Metadata accompanying compiled code for execution, GC, and deoptimization.

The code cache is typically native memory with executable page-protection requirements (executable mappings), not Java byte[] or String objects in the managed heap.

~~~text
HotSpot process
  Java Heap       -> objects, arrays
  Metaspace       -> class/method metadata
  Code Cache      -> executable compiled code / VM stubs
  Compiler Memory -> IR graphs, temporary buffers, arenas
  Thread Stacks   -> compiler/application/VM thread execution
  GC Native Mem   -> collector data structures
  Other Native    -> libraries, direct buffers, VM internals
~~~

### 7.1. Reserved, Committed, Used, Free

These sizes must be kept distinct:

| Term | Meaning |
| --- | --- |
| **Reserved** | Virtual address space reserved for the code cache |
| **Committed** | Pages committed by the VM/OS mechanism |
| **Used** | Space occupied by active code blobs and related metadata |
| **Free** | Remaining usable capacity per the allocator/code heap |
| **Fragmented free** | Free space split into multiple blocks, which can make it hard to allocate a large code blob |

If the Code Cache has **reserved=240 MiB** and **committed=40 MiB**, you must not say the cache has used 240 MiB of physical RAM. Virtual reservation, committed memory, and process RSS are different metrics.

### 7.2. Code Cache Is Different from CPU Instruction Cache

The **code cache** is managed by the JVM in virtual memory. The **CPU instruction cache (I-cache)** is hardware storing instruction cache lines when the CPU fetches; the **iTLB** caches translations for virtual instruction addresses.

JEP 197 notes that segmentation can improve instruction cache/iTLB locality; that does not mean the JVM code cache and CPU L1 I-cache are the same memory region.

## 8. Segmented Code Cache: Three Groups in JDK 17

**OpenJDK JEP 197 — Segmented Code Cache** splits the cache into three code heaps with different lifetimes/usages:

| Code heap | Code type | Meaning |
| --- | --- | --- |
| **Non-method** | VM-generated stubs, interpreter/adapter code, and non-nmethod types | Typically long-lived, difficult to reclaim with the regular nmethod sweeper |
| **Profiled method** | Compiled methods with profiling, typically certain C1 tiers | Much of this code may be replaced by a higher tier after warm-up |
| **Non-profiled method** | Methods without profiling in the current code version, typically C2 optimized and non-profiled C1 depending on mode | Concentrates long-lived useful code, locality matters |

~~~text
                 Reserved Code Cache
+-------------------------------------------------------+
|                                                       |
|  +--------------+ +---------------+ +--------------+ |
|  | Non-method   | | Profiled      | | Non-profiled | |
|  | stubs/runtime| | C1 profiled   | | optimized    | |
|  +--------------+ +---------------+ +--------------+ |
|                                                       |
+-------------------------------------------------------+
~~~

**Do not** equate the profiled heap with all C1 nmethods: C1 level 1 can be non-profiled code. Do not assume every code blob has a fixed lifetime matching the box labels in the diagram.

### 8.1. Why Segment?

- Reduces fragmentation when short-lived compiled methods are replaced/removed.
- Separates non-method code that cannot be arbitrarily swept away.
- Reduces certain scanning/code sweeper costs.
- Improves locality of compiled hot code for the CPU instruction cache.
- Helps manage code heap budgets by type.

According to Java 17 documentation, **SegmentedCodeCache** is enabled by default when **TieredCompilation** is enabled and **ReservedCodeCacheSize is 240 MB or more**, in supported configurations. If you change flags, verify the actual state.

### 8.2. Code Heaps Are Not Necessarily Split Equally

Related HotSpot flags include:

- **NonNMethodCodeHeapSize**.
- **ProfiledCodeHeapSize**.
- **NonProfiledCodeHeapSize**.
- **ReservedCodeCacheSize**.

Sizes have limits and alignment; sizing for each segment depends on version/ergonomics. **Do not assume 240 MB is divided into three equal parts**; observe final flags/jcmd.

### 8.3. Segmentation Does Not Eliminate Exhaustion

A specific heap can run out of space or suffer fragmentation even when other heaps still have capacity. Some mandatory VM stubs must be allocated, so cache exhaustion in the non-method segment can have more severe consequences than failing to install an optimized nmethod.

## 9. Nmethod: Native Code Lifecycle

An nmethod represents compiled Java method code or OSR code in HotSpot, along with metadata so GC/deoptimization/runtime can manage it safely.

~~~text
Compile request
     |
     v
Compiled nmethod installed
     |
     v
Entrant (new invocations may execute)
     |
     +-- hot tier recompilation / OSR version
     |
     +-- invalid assumption / deoptimization
     |
     v
Not-entrant / obsolete
     |
     | runtime ensures no unsafe active use
     v
Reclaimed by sweeper/unloading when safe
~~~

HotSpot has internal states such as **in_use**, **not_entrant**, **zombie**, and **unloaded** depending on version. These are **not Java object states** and are not equivalent to Young/Old GC generations.

### 9.1. Old Code Is Not Deleted Immediately

A Java thread may still be executing a compiled frame in an old nmethod when the VM decides not to use that version for new calls. Freeing the machine code immediately would break memory safety. The VM needs safe mechanisms to deopt/finish stack frames and reclaim when no longer in use.

### 9.2. Nmethod Sweeper / Code Cache Flushing

HotSpot has an **nmethod sweeper** and **code cache flushing** mechanism to reclaim cold/obsolete nmethods when safe. The **UseCodeCacheFlushing** flag is relevant on supported JDKs. You should not disable it just to “keep optimized code forever”: doing so can increase code cache pressure.

**Do not assume:** just because heap GC ran, old compiled nmethods are immediately deleted. Class unloading, code unloading/sweeping, and Java heap reclamation are related, but they are not the same event or resource.

## 10. When the Code Cache Is Full

Some HotSpot versions may log a warning like:

~~~text
CodeCache is full. Compiler has been disabled.
Try increasing the code cache size using -XX:ReservedCodeCacheSize=
~~~

This is only an **illustrative message format**, not a claim that every JDK prints the exact same text or that the compiler is always permanently disabled.

Symptoms that may appear:

- Compile tasks are dropped or new nmethods cannot be installed.
- Java methods remain running in the interpreter/C1 instead of the optimized tier.
- Application throughput drops even though request volume has not increased.
- CPU may rise because code runs at a lower tier.
- p99 latency increases after running for a while, especially when many new methods are called.
- Sweeper/code flushing may reclaim space and the JVM may resume compilation depending on actual policy.

**A full code cache does not necessarily cause a Java heap OutOfMemoryError.** Sometimes the application continues serving traffic but slows down, making the issue hard to spot if you only look at heap metrics.

### 10.1. Why Can Positive Free Bytes Still Be Insufficient?

A code blob needs a contiguous space matching its size/alignment and code heap type. When fragmentation occurs or one segment is exhausted, total free space across the whole cache does not guarantee a blob can be allocated. Check **per-code-heap used/free/fragmentation** rather than just the total cache.

### 10.2. Why Does Increasing Xmx Not Fix It?

- **-Xmx** limits Java heap object memory.
- **ReservedCodeCacheSize** relates to the code cache.
- **Metaspace** relates to various types of class metadata.
- **CICompilerCount** affects compiler threads/native stacks.
- Container RSS is the combined result of all regions and OS accounting.

Increasing -Xmx does not automatically grant more space for nmethods. In fact, raising the heap too much in a container can shrink the available native budget.

## 11. ReservedCodeCacheSize and InitialCodeCacheSize

Two JDK 17 options:

- **-XX:ReservedCodeCacheSize=<size>**: configures the maximum/reserved code cache budget.
- **-XX:InitialCodeCacheSize=<size>**: configures the initial code cache size/commit depending on implementation.

According to the Oracle Java 17 manual, the common default code cache has **ReservedCodeCacheSize=240 MB** with tiered compilation; with **-XX:-TieredCompilation**, the corresponding documented default is **48 MB**. The JDK 17 manual also notes a 2 GB code cache reservation limit. These defaults/limits **are version-specific details**, not universal laws across JDK 11–26.

Example:

~~~bash
java -XX:ReservedCodeCacheSize=128m -XX:+PrintFlagsFinal -version
~~~

Configurations that are too small or conflict with segmented heap sizes may be rejected by the JVM. If you increase the cache to test, measure whether space actually ran out first—do not set arbitrary values just because the application has many classes.

### 11.1. Reserved Is Not Committed

Suppose the code cache is:

~~~text
Reserved:  240 MiB
Committed:  48 MiB
Used:       35 MiB
Free committed: 13 MiB (simplified)
~~~

These numbers are illustrative only. Reserved is typically the virtual address space region; committed is the portion with OS backing/commit; used is the space occupied by code. RSS also depends on mappings and physical pages touched. Do not add reserved to used Java heap and report “the process is consuming that much RAM.”

## 12. CPU Cost of Compilation Threads

C1/C2 compiler threads consume CPU cycles, CPU cache, and memory bandwidth, and can contend with:

- HTTP worker threads.
- GC threads.
- Database client/event loop threads.
- JFR/profiling/monitoring threads.
- The OS scheduler under a small CPU quota.

For example, in a container with a **2 vCPU quota**, if the JVM has several compiler threads running C1/C2 tasks: heavy load during warm-up can prevent request threads from being scheduled on the CPU in time.

### 12.1. CICompilerCount

**-XX:CICompilerCount=<n>** adjusts the number of compiler threads within HotSpot's capabilities and constraints. The JVM may choose the count based on CPU ergonomics/tiered policy.

Test check:

~~~bash
java -XX:CICompilerCount=2 -XX:+PrintFlagsFinal -version
~~~

Do not assume compiler throughput scales linearly with threads: contention, queue mix, native memory, thread stacks, and compiler IR allocations can limit it. Adding threads can make JIT faster but worsen service latency due to CPU contention. Reducing them too aggressively can prolong warm-up.

### 12.2. BackgroundCompilation

Normally HotSpot compiles in the background. Options that alter foreground/background compilation should be used for investigation rather than as default optimizations; forcing mutators to wait for the compiler can add large latency to the request path.

### 12.3. Compile Queue

~~~text
Hot methods create compilation requests
               |
               v
        Pending Compile Tasks
               |
        C1/C2 CompilerThreads
               |
               v
      Compiled code installation
~~~

If task arrival rate > service rate, the queue grows and hot methods may run in interpreted/C1 tiers longer. A temporarily long queue during startup is not necessarily an error; a persistently long queue in steady state alongside compiler CPU saturation is a signal to investigate.

A **compiler queue** is not an **HTTP request queue**: requests are not normally turned directly into compile tasks and blocked waiting. The performance impact is indirect, via unoptimized code and CPU contention.

## 13. Native Memory: Compiler, Code, and Other Regions

| Native/resource group | What is in it? | What to avoid |
| --- | --- | --- |
| **Code cache** | Machine instructions, nmethods, stubs | Do not call it the Java heap |
| **Compiler arenas** | IR graphs, temporary buffers, optimizer data | Do not measure directly via used code-cache |
| **Thread stacks** | CompilerThread C1/C2 stacks | Do not count in the live Java object graph |
| **Profiling metadata** | Method profiles, counters, receiver data | Do not assume all data lives in code-cache memory |
| **Compilation queues** | Tasks and bookkeeping | Not Java request queues |
| **Metaspace** | Runtime class/method metadata | Not all native compiler allocations |
| **Java heap** | Java objects/arrays | Does not automatically allocate more code cache via Xmx |

A service with -Xmx=2g can still consume well over 2 GiB of process memory due to code cache, class metadata, stacks, direct buffers, and GC overhead. When running in a container, leave native memory headroom alongside heap max.

### 13.1. Compilation Cost Traded for Long-Term Benefit

A compilation task costing tens of milliseconds of CPU can be worthwhile if the method runs millions of times and saves many cycles per invocation. But if a method runs only a few times, code cache and compiler resources can outweigh the benefit.

That is why compilation thresholds and tiered heuristics exist. Do not force the JVM to “compile everything” to guarantee performance.

## 14. Warm-Up and Steady-State

~~~text
Startup:
  Class loading / init
  Interpreter + initial profiles
  Many C1 requests
  C2 requests for increasingly hot methods
  Code cache occupancy grows

Warm/steady state:
  Most hot paths compiled when beneficial
  Queue may mostly drain
  Deopt/recompile may continue after workload changes
~~~

Warm-up does not always end at a fixed point in time. Workload shifts, new class loaders, generated proxies, and uncommon traps can spawn new tasks hours later.

**Startup benchmarks differ from steady-state benchmarks**: running a 500 ms microbenchmark may mostly measure interpreter/C1, whereas production hot paths after 30 minutes are C2.

### 14.1. JMH and JIT Measurement Pitfalls

Wrapping a loop in System.nanoTime and printing the result does not guarantee an accurate benchmark. The JIT can constant-fold, dead-code-eliminate, inline, or scalar-replace code. Use **JMH** when micro-level benchmarks need proper warm-up/forks/blackholes, and use load tests with realistic data to evaluate services.

## 15. Java 17+ Demo #1: Hot Loop, JIT-Independent Result

Create **JitWarmupDemo.java**:

~~~java
public class JitWarmupDemo {
    static long hotSum(int limit) {
        long total = 0;
        for (int i = 0; i < limit; i++) {
            total += i % 7;
        }
        return total;
    }

    public static void main(String[] args) {
        long checksum = 0;
        for (int round = 0; round < 20; round++) {
            checksum += hotSum(100_000);
        }

        System.out.println("checksum=" + checksum);
        System.out.println("sameResult=true");
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 JitWarmupDemo.java
java JitWarmupDemo
~~~

**Program stdout:**

~~~text
checksum=5999900
sameResult=true
~~~

Reason: each group of 7 numbers i%7 sums to 21. In 100,000 iterations there are 14,285 full groups and 5 remainders 0+1+2+3+4. The sum of hotSum is **299,995**; called 20 times, it becomes **5,999,900**.

If run with the interpreter:

~~~bash
java -Xint JitWarmupDemo
~~~

The Java-level result must be the same. However, running time can differ significantly; the program is too short to decide production collector/JIT options.

### 15.1. Enabling PrintCompilation

~~~bash
java -XX:+PrintCompilation JitWarmupDemo
~~~

Diagnostic compiler logs may interleave with application stdout. Compile IDs, compiler levels, OSR markers, and timings are **not fixed** across machines/runs/JDKs. Do not treat any arbitrary log as standard expected stdout.

### 15.2. Capping at C1 Tier for Testing

~~~bash
java -XX:+TieredCompilation -XX:TieredStopAtLevel=1 JitWarmupDemo
~~~

The application checksum is still 5999900 upon completion; the JIT pipeline may differ. **-XX:-TieredCompilation** is not the same as **-Xint**; to avoid JIT in an interpreter-comparison experiment, use -Xint.

## 16. Java 17+ Demo #2: Keeping the JVM Alive to Run jcmd

Create **CodeCacheTarget.java**:

~~~java
public class CodeCacheTarget {
    static volatile long sink;

    static long work(int value) {
        long x = value;
        for (int i = 0; i < 10_000; i++) {
            x = (x * 31 + i) & 0x7fff_ffffL;
        }
        return x;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("ready");
        for (int round = 0; round < 2_000; round++) {
            sink = work(round);
            Thread.sleep(10);
        }
        System.out.println("completed");
    }
}
~~~

Commands:

~~~bash
javac --release 17 -encoding UTF-8 CodeCacheTarget.java
java -XX:+TieredCompilation CodeCacheTarget
~~~

**Stdout when the application completes normally:**

~~~text
ready
completed
~~~

While the program is running, open another terminal:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> Compiler.codecache
jcmd <PID> Compiler.queue
jcmd <PID> Compiler.codelist
~~~

Replace **<PID>** with the actual PID. jcmd can only attach while the JVM is still running and with appropriate permissions. The **Compiler.codecache**, **Compiler.queue**, and **Compiler.codelist** commands are documented in Java 17 jcmd for HotSpot; output detail and names depend on the build.

### 16.1. Compiler.codecache

Prints code-cache layout/bounds and usage information. In segmented mode, use it to distinguish code heaps instead of only watching the Java heap.

### 16.2. Compiler.queue

Shows compilation requests pending processing at the moment of inspection. An empty queue does not mean JIT compilation never occurred; tasks may have already finished.

### 16.3. Compiler.codelist

Lists live compiled methods in the code cache according to the tool. One method may have multiple compiled versions, and many Java methods have never been JIT-compiled; do not use this count as the number of source methods.

### 16.4. CodeHeap Analytics

Some HotSpot builds include **Compiler.CodeHeap_Analytics**. Check:

~~~bash
jcmd <PID> help
jcmd <PID> help Compiler.CodeHeap_Analytics
~~~

When available, it can show fragmentation, method space, and code heap statistics. Do not assume it is always available across all JDK vendors or has identical subcommands.

## 17. Using Compiler Logs and PrintInlining

HotSpot supports:

~~~bash
java -XX:+PrintCompilation JitWarmupDemo
~~~

With diagnostic options:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining JitWarmupDemo
~~~

Useful information:

- Compilation IDs and tiers.
- OSR vs regular compilation.
- Which methods were compiled.
- Successful/unsuccessful inlining decisions.
- When an nmethod is made not entrant.
- Compile task load during warm-up.

However, **-XX:+PrintInlining** can generate large output and increase overhead. Do not enable it broadly in production without managing log volume.

### 17.1. Unified JVM Logging

~~~bash
java -Xlog:help
~~~

If the codecache tag is supported by the JVM:

~~~bash
java -Xlog:codecache=debug JitWarmupDemo
~~~

JDK versions can differ in tag names and detail levels, so check -Xlog:help first. Do not invent a fixed log format for codecache across every HotSpot release.

## 18. Using CompilationMXBean

Java SE has **java.lang.management.CompilationMXBean**; the bean can provide the compiler name and aggregate compilation time when supported by the JVM.

Create **CompilerBeanDemo.java**:

~~~java
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;

public class CompilerBeanDemo {
    public static void main(String[] args) {
        CompilationMXBean bean =
                ManagementFactory.getCompilationMXBean();

        System.out.println("beanPresent=" + (bean != null));

        if (bean != null) {
            System.out.println("compiler=" + bean.getName());
            System.out.println("timeSupported="
                    + bean.isCompilationTimeMonitoringSupported());
            if (bean.isCompilationTimeMonitoringSupported()) {
                System.out.println("totalCompileMs="
                        + bean.getTotalCompilationTime());
            }
        }
    }
}
~~~

Commands:

~~~bash
javac --release 17 -encoding UTF-8 CompilerBeanDemo.java
java CompilerBeanDemo
~~~

**There is no fixed full stdout**: compiler name and totalCompileMs depend on the JVM/time; the bean may be null if no compiler facility is present, and time monitoring may not be supported. This is an API observation example; do not fabricate an expected result.

## 19. JFR and Native Memory Tracking

### 19.1. Java Flight Recorder

**JFR** can provide compilation events, compiler statistics, and CPU/thread observations when recording settings enable the corresponding events.

~~~bash
java -XX:StartFlightRecording=filename=jit-lab.jfr,duration=20s,settings=profile CodeCacheTarget
~~~

Once a recording exists:

~~~bash
jfr summary jit-lab.jfr
jfr print --events jdk.Compilation jit-lab.jfr
~~~

The absence of jdk.Compilation events **does not mean JIT was disabled**: the event may not have been enabled or may not have occurred during the recording window. JFR and PrintCompilation answer different questions; to inspect the current code cache, use jcmd Compiler.codecache.

### 19.2. Native Memory Tracking (NMT)

On HotSpot Java 17:

~~~bash
java -XX:NativeMemoryTracking=summary CodeCacheTarget
~~~

From another terminal:

~~~bash
jcmd <PID> VM.native_memory summary
jcmd <PID> VM.native_memory baseline
jcmd <PID> VM.native_memory summary.diff
~~~

NMT typically must be enabled at JVM startup and has overhead. Categories can include **Code**, **Compiler**, **Thread**, **Class**, **GC**. Do not lump the Code category into the Java heap, and do not assume all compiler IR memory is in the Code category.

Illustrative example:

~~~text
Code:
  reserved: 240 MiB
  committed: 35 MiB

Compiler:
  committed: 8 MiB
~~~

These numbers are hypothetical, not a real log. They emphasize looking at **reserved vs committed** and native allocations outside the Java heap.

## 20. Code Cache Full Incident

A possible scenario:

~~~text
Startup -> many methods get compiled
After warmup -> C2 code cache grows
After redeploy -> more generated proxies/classes
Code cache near capacity -> sweeper cannot keep up
Log warns: code cache full
Compiler stops installing optimized code
Application throughput declines
~~~

At this point:

1. Confirm **code cache full** via logs/jcmd.
2. Identify **which code heap** is full if segmented.
3. Measure **code cache committed/used/free** and fragmentation.
4. Check whether **Compiler.queue** has a backlog.
5. Use JFR/PrintCompilation to inspect compilation churn/deopts/OSR.
6. Inspect **generated classes**, dynamic proxies, lambdas, and application redeploys.
7. Check class-loader retention/unloading.
8. Check ReservedCodeCacheSize and actual per-heap sizing.
9. Measure process RSS, NMT Code/Compiler, and CPU quota.
10. Only then increase the cache budget or change compilation policy.

### 20.1. Do Not Just Increase CodeCache Indefinitely

- A cache that is too small can fill up, but an overly large cache does not by itself make the compiler faster.
- The native memory budget is finite; increasing code-cache capacity can increase JVM memory usage.
- If the problem is high compiler CPU/queue, increasing the cache does not solve the task service rate.
- If class generation is continuous, fix the root cause.
- If code heap fragmentation/coarsening occurs, examine segmentation and sweeper activity.

### 20.2. Full Code Cache Does Not Mean Java Heap OOME

The JVM may continue with interpreted execution/C1 code, causing **performance degradation** rather than throwing a Java heap space OOME. Native-code allocation failure under some conditions can be more severe; always rely on actual messages and process state.

## 21. High Compiler CPU and Long Warm-Up

A newly started service may show:

- Process CPU rising due to C1/C2.
- Latency fluctuating during warm-up.
- Code cache usage rising quickly and then stabilizing.
- Compiler.queue busy for a period.
- Throughput improving once hot methods are compiled.

This is usually normal behavior. What warrants attention is **compiler CPU remaining high in steady state** due to code churn, class generation, continuous deoptimization/recompilation, or extremely large tasks.

Some approaches:

- Warm up with representative traffic in staging before taking full load.
- Measure CPU quotas on the actual container.
- Compare compilation queue snapshots before/after warm-up.
- Do not force every method to C2 immediately on load.
- Consider TieredStopAtLevel for short-lived workloads **after benchmarking**.
- Do not lower CICompilerCount immediately just because compiler threads appear in a CPU profiler.

## 22. Deoptimization and Code Churn Costs

A framework that continuously generates classes/proxies or experiences shifting runtime type profiles can cause:

~~~text
Profile -> Compile C2 -> Assumption changes
          |
          v
       Deopt
          |
          v
    Recompile new nmethod
          |
          v
    Old code becomes not entrant
          |
          v
     Sweeper later reclaims
~~~

Multiple overlapping live versions can increase code cache occupancy and compiler CPU. A few deopts are normal; an endless repeating loop is worth analyzing.

**Do not attribute every code cache growth to a memory leak.** The cache normally grows during warm-up and then plateaus. Diagnosing a leak/churn requires observing trends, live compiled code, cache pressure, and class-loader lifetimes.

## 23. Misconceptions to Avoid

1. **“Code cache is the Java heap.”** False: it is HotSpot native/generated code memory.
2. **“JVMS requires every JVM to have a code cache like HotSpot.”** False.
3. **“JIT compilation uses no CPU because it runs in the background.”** False: compiler threads use real CPU.
4. **“Compiler threads are javac.”** False: javac compiles before runtime; C1/C2 compile during runtime.
5. **“Every method is compiled by C2.”** False: hotness/heuristics/resources decide.
6. **“Tiered is always 0→1→2→3→4.”** False: the policy has shortcuts.
7. **“Disabling TieredCompilation disables JIT.”** False: use -Xint to test interpreted mode.
8. **“C1 code is always in the profiled heap.”** False: there are non-profiled C1 tiers.
9. **“Code cache has three equal-sized parts.”** False: sizing depends on flags/ergonomics.
10. **“Inlining always makes code smaller.”** False: it can increase code cache footprint.
11. **“One Java method equals one nmethod.”** False: OSR/tiered/recompilation/inlining.
12. **“Deoptimization proves a JVM bug.”** False: it normally preserves speculative assumptions.
13. **“When an nmethod becomes not entrant, its bytes are deleted immediately.”** False: compiled frame safety/sweeper.
14. **“After heap GC finishes, code cache must shrink.”** False: different lifecycles.
15. **“A full code cache always throws OutOfMemoryError immediately.”** False: the compiler may be disabled with interpreter fallback.
16. **“Increasing Xmx increases ReservedCodeCacheSize.”** False: two separate budgets.
17. **“Reserved 240 MiB means 240 MiB of RSS is in use.”** False: reserved, committed, and used are different.
18. **“An empty Compiler.queue means JIT has not run.”** False: tasks may have already completed.
19. **“Compiler.codelist is all Java source methods.”** False: only live compiled code entries.
20. **“PrintCompilation output is always fixed.”** False: compilation timing/IDs/levels vary.
21. **“NMT Code includes all Compiler memory.”** False: different categories.
22. **“Doubling CICompilerCount doubles compilation speed.”** False: CPU contention/queues/memory.
23. **“A 1-second warm-up benchmark represents steady state.”** False: JIT tiering needs time/profiles.
24. **“A full code cache can be fixed with System.gc().”** Not guaranteed.
25. **“One class-file Code attribute equals one nmethod in the code cache.”** False: bytecode differs from machine code.
26. **“Positive free cache means any blob can definitely be allocated.”** False: fragmentation/segment type can block it.
27. **“Compiled code cannot be invalidated.”** False: deopt/unloading/recompile are standard HotSpot mechanisms.
28. **“Increasing code cache has no memory overhead.”** False: allocation/native budget is still finite.
29. **“A service starved of compiler CPU can be fixed by increasing the heap.”** Not directly.
30. **“JIT logs do not need to match the JDK version.”** False: flags/log fields change.

## 24. Exercises with Answers

**Exercise 1.** What does the code cache contain, and is it the Java heap?

**Answer:** It contains HotSpot native code/code blobs, distinct from the managed Java heap containing objects/arrays.

**Exercise 2.** How do javac and C2 differ?

**Answer:** Javac produces Java bytecode; C2 optimizes/compiles hot bytecode into CPU-specific machine instructions at runtime.

**Exercise 3.** Why does HotSpot use background compiler threads?

**Answer:** So mutators can keep executing while compilation proceeds, reducing blocking on hot paths; there are still CPU/native costs.

**Exercise 4.** Why do C1 and C2 coexist?

**Answer:** C1 enables early compilation/warm-up/profiling, while C2 costs more CPU but can improve steady-state performance.

**Exercise 5.** Does using -XX:-TieredCompilation disable JIT?

**Answer:** Not necessarily; non-tiered JIT still exists, whereas -Xint is used to compare against the interpreter.

**Exercise 6.** What is OSR?

**Answer:** It allows switching to compiled code while a method is running a hot loop without having returned yet.

**Exercise 7.** What partitions make up the segmented code cache in HotSpot JDK 17?

**Answer:** Non-method, profiled method, and non-profiled method heaps when segmentation is enabled.

**Exercise 8.** Why is the non-method heap not swept arbitrarily like all C1 nmethods?

**Answer:** It contains runtime/interpreter/compiler stubs that may need to remain long-lived for the JVM to function properly.

**Exercise 9.** Can deoptimized compiler code still remain in the cache?

**Answer:** Yes; reclamation must ensure the code has no unsafe active use.

**Exercise 10.** Reserved 240 MiB, committed 40 MiB; does the code cache definitely occupy 240 MiB of physical RAM?

**Answer:** No; reserved virtual address space differs from committed/used.

**Exercise 11.** If the code cache is full, will the JVM definitely throw a Java heap OOME?

**Answer:** No; the compiler may be disabled, methods fall back to the interpreter, and performance degrades.

**Exercise 12.** Why does larger code cache capacity not always increase throughput?

**Answer:** If it is not exhausted, the bottleneck lies in compiler CPU, application processing, or memory bandwidth; increasing capacity does not make compilation faster on its own.

**Exercise 13.** The compilation queue is long but the cache still has free space—what are possible causes?

**Answer:** Many/complex compiler tasks, low CICompilerCount, CPU starvation, or restrictive quotas.

**Exercise 14.** Which command inspects HotSpot's actual code cache?

**Answer:** jcmd <PID> Compiler.codecache.

**Exercise 15.** Which command inspects pending compiler tasks?

**Answer:** jcmd <PID> Compiler.queue.

**Exercise 16.** How do you view live compiled methods?

**Answer:** jcmd <PID> Compiler.codelist.

**Exercise 17.** With hotSum(100_000) run 20 times, what is the checksum?

**Answer:** 5,999,900.

**Exercise 18.** If switching to -Xint changes Java stdout (not due to timing/concurrency), what should be suspected?

**Answer:** The program has a data race/nondeterministic behavior, native/undefined assumptions, or a runtime bug; JIT must not alter sequential Java semantics.

**Exercise 19.** What is NMT used to measure?

**Answer:** Native allocations by VM categories such as Code, Compiler, Thread, Class; it does not replace a CPU profiler or heap dump.

**Exercise 20.** Why must p99 be measured both before and after JIT tuning?

**Answer:** Reducing compilation CPU can prolong interpreted execution; adding compiler threads can contend for CPU; measuring only average throughput can miss tail latency.

## 25. Practical Deployment and Tuning Workflow

1. **Confirm the runtime:** HotSpot vendor, JDK 17 build, architecture, container limits.
2. **Measure baseline:** p95/p99, throughput, CPU usage, startup time, heap/RSS.
3. **Check final flags:** SegmentedCodeCache, ReservedCodeCacheSize, TieredCompilation, CICompilerCount.
4. **Observe code-cache segments:** Compiler.codecache and per-heap usage.
5. **Observe compilation backlog:** Compiler.queue across multiple timestamps.
6. **Read compilation events:** PrintCompilation/JFR when needed.
7. **Distinguish normal warm-up from abnormal code churn.**
8. **Inspect deoptimization/recompilation caused by runtime profiles/new classes.**
9. **Measure native memory:** NMT Code/Compiler/Thread/Class and actual RSS.
10. **If code cache is full:** investigate which heap/fragmentation; increase budget only with evidence.
11. **If compiler CPU is too high:** distinguish startup load from sustained backlog; do not arbitrarily lower/raise compiler threads.
12. **Benchmark with real workloads and JMH at the micro level**, with warm-up and multiple runs.
13. **Change only one tuning variable at a time**, record results, and roll back on regression.
14. **Do not use -Xmx as a substitute for the code-cache budget.**
15. **Re-verify when upgrading the JDK**, as compiler implementations/flags/defaults may change.

### Official Documentation

- **Oracle JDK 17 — java command, ReservedCodeCacheSize, SegmentedCodeCache, TieredCompilation:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Oracle JDK 17 — jcmd Compiler.codecache/queue/codelist:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **Oracle JDK 17 — Native Memory Tracking:** https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html
- **OpenJDK JEP 197 — Segmented Code Cache:** https://openjdk.org/jeps/197
- **Oracle HotSpot Performance Enhancements — Tiered Compilation/Code Cache:** https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html
- **OpenJDK JDK 17 HotSpot Code Cache source:** https://github.com/openjdk/jdk17u/tree/master/src/hotspot/share/code
- **OpenJDK JDK 17 HotSpot Compiler source:** https://github.com/openjdk/jdk17u/tree/master/src/hotspot/share/compiler
- **Java SE 17 — CompilationMXBean:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/CompilationMXBean.html
- **Java SE 17 — jfr command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- **JVMS 17 — Method Area abstraction:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.4

**Conclusion:** JIT accelerates hot code but consumes **compiler CPU, native temporary memory, and code-cache capacity**. HotSpot JDK 17 typically uses tiered C1/C2 compilation and a segmented code cache consisting of non-method, profiled, and non-profiled heaps. Native nmethods can be replaced, deoptimized, and safely reclaimed. **A full code cache can slow down the application without causing a Java heap OOME.** Tuning requires observing **code cache, compilation queues, warm-up, GC/native memory, and CPU contention**, not just changing -Xmx or measuring a single small run.