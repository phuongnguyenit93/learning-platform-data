# 17.6 Compiler.queue, Compiler.codecache, and Compilation Events in JFR

## Objectives

When CPU spikes during warm-up, latency fluctuates after deployment, or the JVM warns that the code cache is nearly full, operators need to distinguish **pending compilation work**, **storage for compiled machine code**, and **the history of compilations**. The three corresponding views in HotSpot are:

- **jcmd PID Compiler.queue**: snapshot of methods currently **queued for JIT compilation**.
- **jcmd PID Compiler.codecache**: snapshot of **code cache layout, usage, and bounds** at the time of invocation, depending on JVM version.
- **JFR compiler/code-cache events**: a sequence of events **over time**, showing which methods were compiled, compilation durations, which compiler participated, code cache changes, and whether code cache full events occurred.

After this lesson, you will know how to run these commands safely, interpret key fields accurately, select relevant JFR events, correlate by timestamp, avoid confusing compile CPU with application CPU, and practice with Java 17+.

**Primary scope:** HotSpot/OpenJDK 17–21, preferring JDK 21 command and event names. Event names, fields, thresholds, code cache segmentation, and output formatting may vary by JDK build/vendor and configuration. During real investigations, query the JVM directly with **jcmd PID help** and the JFR file with **jfr metadata**.

## 1. From Bytecode to JIT and the Code Cache

Java source is compiled to bytecode. In HotSpot, the JVM may execute bytecode with the interpreter first, track method/loop "hotness," and send qualifying regions to **JIT compilation** to produce machine code. That machine code is managed in the **code cache**. This is one of the mechanisms explaining why the same workload can speed up after the JVM warms up.

~~~text
Application calls method / runs loop
                |
                v
     Interpreter and profiling
                |
     Hot method / OSR candidate
                |
                v
          Compile queue
                |
        Compiler thread(s)
           C1 or C2
                |
                v
    JIT machine code (nmethod)
                |
                v
            Code cache
                |
           CPU executes
~~~

The diagram above is a conceptual model; HotSpot involves more complex optimizations, tier transitions, recompilations, OSR, and deoptimizations. **C1** typically prioritizes compilation speed and profiling; **C2** invests in deeper optimizations at potentially higher compile cost. With tiered compilation, a method may be compiled at multiple levels, and levels do not necessarily increase monotonically for every method.

- A **Compile task** is a pending or in-progress compilation job.
- A **Compiled method/nmethod** is the machine-code artifact, which can be used, become not entrant/zombie, be deoptimized, or eventually be reclaimed.
- The **Code cache** is the region reserved for JVM-generated code and runtime support code; it is **not the Java heap** and does not hold object instances like a heap histogram.
- **JFR** records events about this process when enabled and above threshold; it is not an automatic transcript of `jcmd` output.

### Why Do You Need All Three Sources?

A momentarily long queue does not tell you how much free space remains in the code cache. A nearly full code cache does not tell you which method is compiling slowly. A long JFR Compilation event does not prove users experienced latency at that exact instant. **Always combine snapshots (`queue`/`cache`) with timelines (`JFR`) and CPU/latency metrics.**

## 2. Compiler.queue: Which Methods Are Waiting to Compile?

On a running HotSpot JVM, find the PID and query help:

~~~bash
jcmd -l
jcmd <PID> help Compiler.queue
jcmd <PID> Compiler.queue
~~~

Replace **<PID>** with the real process ID; in a Linux/macOS shell you can set **PID=12345** and run **jcmd "$PID" Compiler.queue**. The **jcmd** tool requires access to the target JVM with appropriate permissions. For JVMs in containers, identify the right PID/namespace and attach mechanism.

Per **JDK 21 `jcmd` documentation**, **Compiler.queue** prints methods queued for compilation; its impact is rated **Low**. It is a **brief snapshot**, not a historical log, and does not include methods that have already finished compiling.

### How to Read It

An illustrative output may show C1/C2 compilation queues and a list of compile tasks; actual column names, ordering, and details vary by JVM:

~~~text
C1 compile queue:
  ...  app.service.Worker::handle (... bytes)

C2 compile queue:
  ...  app.core.Parser::parse (... bytes)
~~~

The lines above are **not exact expected stdout**. A JVM may print **queue empty** or only one compile queue type. The item count at snapshot time can be 0 even when dozens or hundreds of compilations occurred during the preceding second.

### When Is a Long Queue Notable?

When repeated samples under similar load show the queue growing and failing to drain, it may indicate a **compiler backlog**: hot code is waiting to be optimized, forcing the JVM to stay in the interpreter or lower tiers longer. Causes can include a burst of new methods after startup, dynamic code generation, class loading, CPU limits/container CPU throttling, busy compiler threads, or workloads touching many compilable methods.

**Do not conclude from a single queue snapshot that the JIT is hung.** A queue can grow temporarily during warm-up and then drain. Sample repeatedly across the incident window, recording timestamps, CPU, completed compilations, and code cache status. In a steady-state app, an empty queue is normal.

**The queue does not show how long every task has waited.** To analyze what actually compiled and how long it took, you need JFR **jdk.Compilation** and related events if enabled.

## 3. Compiler.codecache: Where Compiled JIT Code Lives

Commands:

~~~bash
jcmd <PID> help Compiler.codecache
jcmd <PID> Compiler.codecache
~~~

In JDK 21, this command prints the layout and bounds of the code cache, with **Low** impact. Many HotSpot builds also print capacity, used, `max_used`, free, and address ranges.

Illustrative output structure **for recognition only**, with hypothetical numbers:

~~~text
CodeHeap 'non-profiled nmethods': size=120000Kb used=40000Kb max_used=42000Kb free=80000Kb
CodeHeap 'profiled nmethods':     size=120000Kb used=25000Kb max_used=28000Kb free=95000Kb
CodeHeap 'non-nmethods':           size=5000Kb used=3000Kb max_used=3200Kb free=2000Kb
...
~~~

Do not treat those hypothetical numbers as JDK defaults. JDK configurations without segmented code cache may report a single area; units may be bytes/Kb and additional statistics may appear.

### 3.1. Segmented Code Cache

When **-XX:+SegmentedCodeCache** is enabled, HotSpot can divide the cache into:

| Code Heap | Basically Contains | How to Read |
| --- | --- | --- |
| **non-nmethods** | Runtime support code, adapters, stubs, or non-nmethod code | Do not treat all of this as application Java methods |
| **profiled nmethods** | JIT code with instrumentation/profiling, usually associated with lower tiers | Grows while the JVM learns workload characteristics |
| **non-profiled nmethods** | Optimized code, usually associated with higher levels | Grows during compilation of hot methods |

According to Oracle JDK 21, segmented code cache is enabled by default when tiered compilation is enabled and **ReservedCodeCacheSize is 240 MB or more**; other configurations may not segment it this way. Segments have independent limits and **do not resize at runtime**.

Therefore, "plenty of total free space" does not rule out pressure in **one specific code heap**. When the code cache is segmented, inspect each segment individually, not just the sum.

### 3.2. used, max_used, free, reserved, and committed

- **used** in code cache output reflects space occupied by code blobs/nmethods as reported by HotSpot at measurement time.
- **max_used** is usually the peak usage recorded by the VM over the relevant lifetime, not the configured maximum capacity.
- **free** is remaining space in the code heap as calculated by HotSpot; it does not fully reflect fragmentation or whether a blob with specific size/alignment can be allocated.
- **ReservedCodeCacheSize** is the reserved address-space limit for the code cache; it does not equal resident RAM.
- **reserved**, **committed**, and **resident** are distinct concepts. When comparing against NMT/OS, align metric types and scopes.

**The code cache is not the Java heap**: reducing heap object usage does not directly free compiled machine code, and ordinary heap GC is not a general cure for code cache pressure.

### 3.3. What Happens When the Code Cache Fills Up?

HotSpot may fail to allocate another code blob in the target code heap; the JVM may emit a code cache full warning, temporarily halt/reduce JIT compilation, reclaim obsolete code via the code sweeper, and possibly recover depending on version/configuration.

Observable consequences can include:

1. Newly hot methods fail to compile up to the desired tier.
2. Application CPU and latency shift because execution stays in the interpreter or less-optimized compiled code.
3. The compiler queue and compilation activity may behave abnormally.
4. The JFR event **jdk.CodeCacheFull** may appear, and when JIT resumes, **jdk.JITRestart** may appear.

**Do not conclude the code cache is full solely from low free space**: combine warnings/JFR events, runtime status, per-segment figures, sweeper activity, and trends. Hitting a threshold once and recovering does not equal "JIT is permanently disabled."

### 3.4. Related Limits and Configuration

Oracle JDK 21 documents **-XX:ReservedCodeCacheSize**, **-XX:+SegmentedCodeCache**, and when segmented, **-XX:NonNMethodCodeHeapSize**, **-XX:ProfiledCodeHeapSize**, and **-XX:NonProfiledCodeHeapSize**.

**Do not increase ReservedCodeCacheSize reflexively.** Adjustments should rest on cache usage metrics, code sweeper behavior, compilation demand, host/container native memory limits, and controlled experiments. A higher limit can expand reserved address space without immediately causing RSS to equal the reserved size.

## 4. JFR: History of Compiler and Code-Cache Events

JFR adds a **timeline** that explains what happened before and after a `jcmd` snapshot. The event names below are common in HotSpot/JDK 17–21; verify the exact set and fields using the file's metadata or target JDK.

| Common Event Type | Role | What to Inspect |
| --- | --- | --- |
| **jdk.Compilation** | Outcome of one compilation attempt | Timestamp, duration, method, compiler, compile level, compile ID, success, OSR if present |
| **jdk.CompilerPhase** | One phase inside compilation | Which phase took long, compile ID linking back to compilation |
| **jdk.CompilerStatistics** | Compiler activity statistics | Compile count, compile time, bailouts/invalidations, etc., per schema |
| **jdk.CompilerConfiguration** | Compiler configuration settings | How the JVM/tiered compiler is configured |
| **jdk.CompilationFailure** | Compilation failure details | Compile ID and reason, when enabled |
| **jdk.CodeCacheConfiguration** | Configuration of code heaps | Capacities and related components per schema |
| **jdk.CodeCacheStatistics** | Code heap metrics at checkpoints | Code heap type, capacity, unallocated/free, entry count, full count, etc. |
| **jdk.CodeCacheFull** | Event when a code heap lacks suitable space | Timestamp, heap/type, capacity, and exhaustion signals |
| **jdk.JITRestart** | JIT restarts after stopping | Correlate with sweeping/code cache reclamation |
| **jdk.CodeSweeperStatistics** | Sweeping/reclamation of compiled code | Check whether the code sweeper is reclaiming space |
| **jdk.Deoptimization** | Compiled method hits invalidated assumption and deopts | Correlate with tier changes or performance shifts |

**Caveat:** some events may be **disabled**, have **high thresholds**, emit only **periodic/everyChunk**, or be unsupported by a given JDK version. Seeing an event type in metadata **does not guarantee instances exist in the recording**. Do not rely on this table to assume Count must be > 0.

### 4.1. Compile ID and Method

Compilation events may carry **compileId**, **method**, **compiler**, **compileLevel**, **duration**, and success status. **compileId** lets you join a Compilation to CompilerPhase or CompilationFailure **within the same JVM/recording context** when those types are recorded. Never use `compileId` as a global key across JVM restarts or files from different processes.

In some older HotSpot schemas, the success field of **jdk.Compilation** is spelled **succeded** (unlike standard English **succeeded**). **Do not "fix" field names in your parser**: run **jfr metadata --events jdk.Compilation file.jfr** to get the exact verbatim field names for that version.

**One method can have multiple compilation IDs** due to recompilation, tier changes, OSR, or invalidation. Do not count each Compilation event as a "distinct method."

### 4.2. Is Compilation Duration Equal to Slow Request Time?

No. The duration of **jdk.Compilation** is the execution time of a compilation attempt per event semantics, not the method's runtime duration when executed by the application. Compilation work usually runs on dedicated compiler threads.

For example, a 300 ms C2 compilation does not mean requests calling that method took 300 ms. However, compilation can consume CPU, contend for resources in CPU-constrained containers, and affect warm-up. Correlate **compiler activity**, CPU load/thread CPU, **request latency**, and timestamps.

### 4.3. Compiler Statistics Can Be Cumulative Counters

Statistics events may report **monotonically increasing counters** or periodic/chunk snapshots. When comparing two points, take the **delta between checkpoints** within the same JVM; do not treat a final counter value as compilations occurring in a single second. If a file misses the JVM's early lifetime, counters may already be large before the recording started.

`CodeCacheStatistics` may also be periodic snapshots. Spacing between instances is governed by **period** or chunk rotation; do not assume 1-second resolution.

### 4.4. Interpreting CodeCacheFull and CompilerPhase

**jdk.CodeCacheFull** is a very strong indicator for investigating code cache exhaustion during the recorded window. Conversely, **Count=0 does not prove the code cache never filled up**: the event may be disabled, the recording may miss the incident, or no event instance was written.

**jdk.CompilerPhase** can generate high data volume and has a threshold; enable only at the needed detail when investigating specific compiler latency. It does not automatically capture every optimization decision and does not replace dedicated compiler logs.

## 5. Working with JFR: Inspect the File Before Concluding

Once you have **compiler.jfr**, start with:

~~~bash
jfr summary compiler.jfr
jfr metadata --events jdk.Compilation,jdk.CompilerStatistics,jdk.CodeCacheStatistics,jdk.CodeCacheFull compiler.jfr
jfr print --events jdk.Compilation compiler.jfr
jfr print --events jdk.CodeCacheStatistics,jdk.CodeCacheFull compiler.jfr
~~~

- **summary** confirms Start, Duration, event types, **Count**, and serialized event record size (**Size**).
- **metadata** reveals actual type names, categories, and field schemas.
- **print** shows instances with timestamps, durations, and fields.
- **--events** restricts which event types print; no need to dump an entire huge file.

An event with **Count=0** means the file contains no instances of that event; it does not mean the activity never happened in reality. Check recording settings and capture timing.

**Size in `jfr summary` is the serialized event data size in the recording**, not how many bytes the code cache used; to measure code cache bytes, inspect `Compiler.codecache` output or the corresponding memory fields in JFR.

### 5.1. Read the Type Schema Directly

~~~bash
jfr metadata --events jdk.Compilation compiler.jfr
jfr metadata --events jdk.CodeCacheStatistics compiler.jfr
jfr metadata --events jdk.CodeCacheFull compiler.jfr
~~~

In particular, verify fields, units, categories, and whether the type is supported on the recording JDK. If you omit the file argument, **jfr metadata** describes types for **the JDK running the `jfr` tool**, which can differ from the schema inside a recording sent from another JVM.

### 5.2. Check Effective Settings

For a JVM currently recording JFR:

~~~bash
jcmd <PID> JFR.check verbose=true
~~~

This displays recording info and settings (when supported). Verify **jdk.Compilation enabled/threshold**, **jdk.CompilerPhase threshold**, **jdk.CodeCacheStatistics period**, and recording name. The **default.jfc** and **profile.jfc** profiles are useful baselines, yet do not automatically enable every event or set threshold=0.

When using **jcmd JFR.start**, per JDK 21 documentation you can pass event settings as **eventName#setting=value** when needed. Every threshold change carries data-recording cost, however; pick a level suited to the incident duration and scope.

### 5.3. Time-Based Correlation

A consistent workflow:

1. Record **timestamps**, timezone, PID/JVM instance, and workload.
2. Capture **jcmd Compiler.queue** and **Compiler.codecache** at T0/T1/T2.
3. Confirm the JFR file covers T0–T2 for that exact JVM.
4. Inspect **CompilerStatistics/Compilation** around when the queue grew.
5. Inspect **CodeCacheStatistics/CodeCacheFull/JITRestart** around when free space fell or code cache filled.
6. Correlate **CPU load**, CPU throttling, and response latency at the same timestamps.
7. Only conclude a root cause when data aligns into one coherent chain and repeated measurements confirm it.

### An Illustrative Example

~~~text
09:10:00  deploy; application load rises
09:10:08  Compiler.queue: many pending tasks
09:10:10  JFR: many Compilation events, substantial compile time
09:10:15  Compiler.queue: nearly empty, code cache used increased
09:10:35  request latency drops as workload stabilizes
~~~

This pattern is *consistent with JIT warm-up* yet **not yet proof** it is the sole cause. If cgroup CPU throttling, GC pauses, or database latency also rose at the same time, investigate further.

## 6. Scenario-Based Diagnostic Workflows

### 6.1. High CPU Immediately After Startup

1. Check the compiler queue repeatedly during warm-up; see whether it drains or grows indefinitely.
2. Check Compilation events/JFR stats and compiler-thread CPU if available.
3. Check application CPU, request throughput, GC, and code cache usage.
4. If CPU spikes transiently and then stabilizes, it may be normal JIT cost. If the queue keeps swelling and throughput drops, investigate **CPU resources**, class/method churn, code generation, compiler flags, and warm-up strategy.

Do not assume "high CPU after deploy" is automatically JIT; it could also involve startup I/O, dependency injection, cache warm-up, GC, or connection initialization.

### 6.2. Latency Rises After Long Steady Operation

1. Capture **Compiler.codecache** and inspect every code heap.
2. Check JFR for **CodeCacheFull** or shifts in **CodeCacheStatistics**.
3. Look for **JITRestart**, code sweeper activity, compiler queue, and Compilation events before/after the latency inflection.
4. Check deoptimization/class redefinition or new workloads forcing recompilation.
5. Avoid blaming the code cache without correlation. Heap/GC/lock contention/I/O can produce similar symptoms.

### 6.3. Queue Is Empty Yet the Application Is Slow

An empty queue only says no compile tasks were waiting at snapshot time. The application can still be slow due to I/O, locks, GC, CPU throttling, suboptimal code, deoptimization, or JIT compilation having been disabled so no new tasks are enqueued.

Check **compiler status**, codecache, JFR CodeCacheFull/Compilation events, CPU/JFR ExecutionSample, and application metrics. Never use **queue empty** as proof that "JIT is healthy" or "there is no bottleneck."

### 6.4. Code Cache Very Full Yet No CodeCacheFull Event

Possible reasons include no allocation failure actually occurring, the sweeper freeing code, the recording missing the incident, the event being disabled, or the code heap merely sitting near threshold. Inspect **multi-point snapshots**, per-heap free space, event settings, and JVM warnings.

"90% full" is not a universal failure threshold. Evaluate based on growth rate, code heap type, sweeper activity, reserved size, and business impact.

### 6.5. Compiler Event Count Rises While Code Cache Used Drops

No contradiction. New code may be compiled while older code is reclaimed by the code sweeper; code after deoptimization or replacement also has its own lifecycle. Compilation count is not the count of live code blobs. Inspect **CodeCacheStatistics**, **CodeSweeperStatistics**, codelist if needed, and time correlation.

## 7. Quick Comparison of the Three Tools

| Criterion | Compiler.queue | Compiler.codecache | JFR compilation/code-cache events |
| --- | --- | --- | --- |
| Data type | Current snapshot | Current snapshot | Multi-event timeline |
| Subject | Pending compile tasks | Code heaps and stored code | Attempts, stats, failures, code-cache events |
| Has method names | Possible | Usually insufficient detail; use codelist | Possible in jdk.Compilation |
| Has compile duration | No | No | Yes in duration events if captured |
| Shows code cache exhaustion | Not directly | Free/used/bounds signals | CodeCacheFull and Statistics |
| Shows history before now | No | `max_used` hints peak; no full timeline | Yes, within the recording window |
| Proves CPU root cause | Insufficient | Insufficient | Must correlate with CPU/latency metrics |
| When to use | Asking "what is waiting?" | Asking "is there room for code?" | Asking "what happened and when?" |

## 8. Java 17+ Hands-On: Generating a Workload That Can Trigger JIT

The example below repeatedly calls an arithmetic method. It needs no external dependencies beyond the JDK, prints deterministic milestones, and keeps the JVM running so you can take `jcmd` snapshots. **It is not guaranteed that a method compiles to a specific tier or that the queue is non-empty**: JIT decisions depend on flags, JVM, CPU, timing, and optimization.

Create **`JitCompilerProbe.java`**:

~~~java
public final class JitCompilerProbe {
    private static volatile long result;

    private static long compute(long seed) {
        long value = seed;
        for (int i = 0; i < 120; i++) {
            value = (value * 1_664_525L + 1_013_904_223L)
                    ^ (value >>> 11);
        }
        return value;
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("START: prepare to inspect JIT");
        Thread.sleep(5_000L);

        System.out.println("WORK: running repeated methods");
        for (int pass = 0; pass < 40; pass++) {
            for (int i = 0; i < 20_000; i++) {
                result ^= compute(i + pass);
            }
            Thread.sleep(100L);
        }

        System.out.println("END: workload finished");
        Thread.sleep(20_000L);
    }
}
~~~

Compile with **JDK 17+**:

~~~bash
javac JitCompilerProbe.java
~~~

Run with JFR profile on HotSpot. In a typical shell, quote the entire `StartFlightRecording` option so the **#** character in event settings passes through intact:

~~~bash
java "-XX:StartFlightRecording=filename=jit-compiler-demo.jfr,settings=profile,dumponexit=true,jdk.Compilation#enabled=true,jdk.Compilation#threshold=0ms" JitCompilerProbe
~~~

The program sleeps before/after the workload so you can run `jcmd` from a second terminal. **Output from the program itself** in exact order, ignoring JVM messages that may print when JFR starts:

~~~text
START: prepare to inspect JIT
WORK: running repeated methods
END: workload finished
~~~

**It does not print `result`** because that value is not the measurement target, yet the `volatile` field keeps the computation observable and helps prevent the optimizer from eliminating the entire loop. Do not expect identical Compilation event counts or code cache sizes on every machine.

### 8.1. Second Terminal: Inspect Queue and Cache While the JVM Is Alive

~~~bash
jcmd -l
jcmd <PID> Compiler.queue
jcmd <PID> Compiler.codecache
jcmd <PID> JFR.check verbose=true
~~~

Repeat **Compiler.queue** several times while the program prints WORK; the queue can empty between very brief bursts. If possible, record timestamps for each snapshot.

**Questions to observe**: are there queued tasks, which code heap grows in `used`, how much `free` remains in each segment, and does the recording have `jdk.Compilation` enabled at the requested threshold?

### 8.2. After the Program Exits: Inspect the JFR File

~~~bash
jfr summary jit-compiler-demo.jfr
jfr metadata --events jdk.Compilation,jdk.CompilerStatistics,jdk.CodeCacheStatistics,jdk.CodeCacheFull jit-compiler-demo.jfr
jfr print --events jdk.Compilation jit-compiler-demo.jfr
jfr print --events jdk.CodeCacheStatistics,jdk.CodeCacheFull jit-compiler-demo.jfr
~~~

There is no fixed stdout for these commands, because the JVM may compile library methods alongside **JitCompilerProbe.compute**, event counts vary by workload and JFR settings, and timestamps differ. A profile may not enable every event type listed in the table; **summary** confirms what the file actually contains.

**If no compilations appear**: check whether the JFR file covers the WORK window, targets the right JVM, supports the event type, has effective event settings, and whether the JVM is running interpreter-only (**-Xint**), AOT/special mode, or impacted by code cache JIT settings. Do not guess one cause from an empty file.

### 8.3. Optional Experiment with Compiler Logging

In a **demo** environment, you can run with:

~~~bash
java -XX:+PrintCompilation JitCompilerProbe
~~~

The JVM will print compile task logs to stdout/stderr alongside the program's three lines, letting you match compile IDs, levels, and method names with JFR observations. Log volume depends on the runtime, and it is **not a replacement for JFR**. Do not turn on `PrintCompilation` broadly in production because logs can become huge; verify in a controlled environment.

## 9. Reading JFR by Linking compileId and Timeline

A hypothetical example (not actual output):

~~~text
T0: jdk.Compilation
    compileId = 150
    compiler = C2
    method = app.Parser::parse
    compileLevel = 4
    duration = 125 ms

T1: jdk.CompilerPhase
    compileId = 150
    phase = ... optimization ...
    duration = 80 ms

T2: jdk.CodeCacheStatistics
    code heap = non-profiled nmethods
    unallocated/free trending down
~~~

How to read:

1. **Compilation** shows the attempt for `parse` took about 125 ms per the event.
2. **CompilerPhase** with the same `compileId` can explain which phase took time, if the recording actually enabled/recorded those phases.
3. **CodeCacheStatistics** shows code heap state at a checkpoint. It does not require per-nmethod events, so do not infer "125 ms of compilation consumed exactly X bytes of cache" without matching fields/evidence.
4. Combine with **CPU load/latency** to assess end-to-end impact.

**Do not assume `compileLevel=4` always means "successfully optimized" across every JDK/vendor.** In standard HotSpot tiered compilation, level 4 typically corresponds to C2 optimized, yet check compiler and success status in the actual schema.

## 10. When Suspecting Code Cache Full: Which Evidence Is Strong Enough?

Suppose JFR shows `CodeCacheFull` events, `CodeCacheStatistics` reports `non-profiled` near zero unallocated capacity, and latency rises as the JVM stops using newly compiled methods.

That is a **chain of evidence worth investigating**. To confirm code cache as the primary cause, continue:

- Inspect **Compiler.codecache** per segment and timestamp.
- Inspect warnings/logs about code cache/JIT stopped, **JITRestart**, and code sweeper statistics if available.
- Verify request latency/CPU changed in **the same window** and is not better explained by GC/IO/network.
- Check **ReservedCodeCacheSize**, segmented code heap sizes, and whether the workload increased class/method generation.
- Run a controlled experiment on cache sizing or workload and re-measure.

**Remediation must follow the cause**: for example, if the app generates classes/methods dynamically without bound, fix lifecycle/code generation; or code heap sizing does not fit the number of methods genuinely needing compiled code. Simply raising limits only delays symptoms if demand keeps growing unboundedly.

## 11. Common Reasoning Traps

1. **"`Compiler.queue` is empty so there is no JIT activity."** False: the queue drains rapidly; completed compilations leave the snapshot.
2. **"One long queue snapshot means the JVM is hung."** False: may be normal warm-up. Check trends across multiple points.
3. **"`Compiler.codecache` used is Java heap used."** False: code cache stores machine code and runtime code, not heap objects.
4. **"`ReservedCodeCacheSize` is physical RAM currently consumed."** False: reserved, committed, and resident are distinct quantities.
5. **"Plenty of total free means every segment has room."** False if segmented code cache has one segment nearly full.
6. **"JFR Compilation duration is request latency."** False: duration measures a compiler attempt; correlate with requests and CPU.
7. **"Each compilation event corresponds to one unique method."** False: the same method can compile at multiple tiers and multiple times.
8. **"JFR Count=0 proves no compilation happened."** False: events may be disabled, filtered by threshold, outside the recording window, or missing.
9. **"Absence of `CodeCacheFull` means the cache is healthy."** False: check settings, coverage, and codecache snapshots.
10. **"`CompilerPhase` always includes every phase."** False: events may be disabled/filtered by threshold, and schemas/implementations change.
11. **"`CompilerStatistics` `compileCount` is compilations only during the recording."** Potentially false because counters are cumulative; read the schema and compare **deltas**.
12. **"Nearly full code cache proves a memory leak."** False: compiled code has a lifecycle and sweeper reclamation; inspect code demand over time.
13. **"Increasing code cache size always makes CPU faster."** False: depends on workload, memory pressure, tiered compilation, and optimization effectiveness; test first.
14. **"Slow JIT compilation definitely burns request-thread CPU."** False: compiler threads are usually separate; total system CPU contention can still affect requests, especially in CPU-capped containers.
15. **"Compile IDs can be merged directly across multiple JVMs."** False: IDs are meaningful only within a single VM/session context.
16. **"Running `jcmd` with any PID or host container PID is equivalent."** False: proper namespace/attach permissions are needed to query the intended JVM.
17. **"A method appearing in `codelist` means it is currently executing."** False: `codelist` reports existing compiled code, not CPU sampling.
18. **"`PrintCompilation` gives the same historical data as JFR."** False: it is a compiler log; JFR provides event metadata, timestamps, and a structured timeline.

## 12. Self-Assessment Exercises

**Question 1.** A newly started JVM shows 30 tasks in `Compiler.queue`, then 10 seconds later the queue is empty, `CodeCache.used` rose, and latency dropped. Reasonable hypothesis?  
**Answer:** JIT warm-up completing. Cross-check JFR Compilation events, CPU, and traffic to verify; do not yet treat it as a bug to fix.

**Question 2.** Profiled CodeHeap has 3 MB free and non-profiled has 90 MB free. Can we say "code cache has 93 MB left so there is no risk"?  
**Answer:** No. Code heaps have independent bounds; check which heap needs allocations and watch for code cache full events.

**Question 3.** `jfr summary` shows `jdk.Compilation Count=0` yet `Compiler.codecache` used is already 60 MB. Contradiction?  
**Answer:** No. Code may have compiled before the recording started, or the event was disabled or filtered by threshold. Summary does not describe history outside the file.

**Question 4.** One method appears three times in JFR Compilation with different compile IDs and levels. Does the app have three differently named Java methods?  
**Answer:** No. The same method can be compiled multiple times across tiers, OSR, or recompilations.

**Question 5.** `CodeCacheFull` occurs at the same time latency spikes. Is causality proven?  
**Answer:** Not yet. That is a strong correlation; inspect JIT status, compiler queue, CPU/GC/I/O, code cache sweeping effectiveness, and controlled experiments.

**Question 6.** What do you use to see **pending** compiler tasks? What to see **how long compilation took**? What to see **remaining code cache space**?  
**Answer:** `Compiler.queue`; JFR `jdk.Compilation` duration; `Compiler.codecache`/JFR `CodeCacheStatistics`.

**Question 7.** `CodeCacheStatistics` reports free dropping and then rising again while Compilation Count keeps increasing. Is the metric broken?  
**Answer:** Not necessarily; the code sweeper may be reclaiming old code while the compiler generates new code.

**Question 8.** JFR `CompilerPhase` shares a `compileId` with a `Compilation` event, yet not all phases appear. What should you check?  
**Answer:** Settings/thresholds/event coverage and schema; do not assume the file captures every internal phase.

## 13. References

- [Oracle JDK 21 — `jcmd`: `Compiler.queue`, `Compiler.codecache`, `Compiler.codelist`, `JFR.check`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `java` launcher: `ReservedCodeCacheSize`, `SegmentedCodeCache`, code-heap size flags, `PrintCompilation`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 21 — `jfr` command: `summary`, `metadata`, `print`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — `jdk.jfr` package: event settings and thresholds](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Oracle Java Mission Control — JFR Event Constants: compiler/cache event type names](https://docs.oracle.com/javacomponents/jmc/api/flightrecorder/constant-values.html)
- [OpenJDK JFR event metadata definitions](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/jfr/metadata/metadata.xml) — check against the **exact JDK version tag** to avoid schema differences.
