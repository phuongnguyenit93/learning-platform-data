# 13.5 Setting a Baseline and Reading `summary.diff` or `detail.diff`

## Lesson Objectives

When a Java process's memory grows, a point-in-time snapshot is not enough to know **when memory started growing, in which category, and whether it keeps growing after load returns to normal**. HotSpot's Native Memory Tracking (NMT) provides a **baseline** mechanism to compare JVM-managed memory across different points in time.

After this lesson, you will be able to:

1. Enable the appropriate NMT level at JVM startup and verify it is active.
2. Choose a baseline time after warm-up, collect `summary.diff` across load phases, and interpret `+`/`-` signs accurately.
3. Use `detail.diff` to drill down from a growing memory category to the HotSpot-recorded allocation sites/memory mappings.
4. Distinguish `reserved`, `committed`, allocation counts, and physical RSS memory; recognize NMT's limitations.
5. Write evidence-backed diagnostic conclusions without labeling every positive delta a native memory leak.

> **Scope:** This lesson focuses on measuring native memory changes in the **HotSpot JVM** using NMT in Java 17+/21. NMT also lists the Java Heap reserved/committed by the VM, but does not replace heap profilers, GC logs, or OS RSS measurements.

## 1. What Is a Baseline, and Why Do You Need a Diff?

NMT records memory used/reserved by the **HotSpot JVM itself**, aggregated into categories such as `Java Heap`, `Class`, `Thread`, `Code`, `GC`, `Compiler`, `Internal`, `Other`, and `Native Memory Tracking`. Category names, structure, and level of detail may vary between JDK versions.

When invoking:

- `VM.native_memory summary`: view the **current snapshot** by category.
- `VM.native_memory baseline`: store a **reference checkpoint** inside the running JVM process.
- `VM.native_memory summary.diff`: view current values **and deltas relative to the most recent baseline**, by category.
- `VM.native_memory detail.diff`: view more detailed deltas by call site/virtual memory region if the JVM was started with `detail`.

Distinguish three points in time:

| Time | Event | How to Interpret |
| --- | --- | --- |
| T0 | Application finishes warm-up; baseline created | Reference point for computing deltas |
| T1 | Just ran one load cycle | `summary.diff` at T1 gives `T1 - T0` |
| T2 | Load reduced, queues drained | `summary.diff` at T2 is still `T2 - T0`, **not `T2 - T1`** |

**A baseline is a delta comparison within the same JVM, not an OS snapshot or proof of a leak.** Calling `summary.diff`/`detail.diff` does not automatically set a new baseline. Calling `baseline` again **replaces the old reference point**; from then on, all new diffs are computed against the newly created checkpoint. When the JVM restarts, the previous process's baseline is no longer valid.

A positive delta proves **NMT-tracked usage at measurement time is higher than at the baseline**, not that the data is useless or unfreeable. Conversely, a near-zero delta does not rule out temporary memory spikes between two measurements.

## 2. Before Measuring: Enable NMT at the Right Level

NMT is disabled by default; it must be enabled with a JVM flag **at process startup**. You cannot use `jcmd` to enable or re-enable disabled NMT on an already running process.

| NMT Level | JVM Flag | What Can Be Read | When to Use |
| --- | --- | --- | --- |
| Off | `-XX:NativeMemoryTracking=off` (default) | No useful NMT report | When collection is not needed |
| Summary | `-XX:NativeMemoryTracking=summary` | Category summaries and `summary.diff` | Initial investigation, lower overhead than detail |
| Detail | `-XX:NativeMemoryTracking=detail` | Summaries, call sites/mapped regions, `summary.diff`, and `detail.diff` | Problem category narrowed down and deeper source tracing needed |

Example **launching an actual JAR application** with summary mode:

```bash
java -XX:NativeMemoryTracking=summary -Xms256m -Xmx1g -jar app.jar
```

`app.jar` is only an illustrative name; use your real application JAR and keep the environment's other JVM settings intact when designing experiments. When `detail.diff` is needed, start a **new** JVM with:

```bash
java -XX:NativeMemoryTracking=detail -Xms256m -Xmx1g -jar app.jar
```

NMT has a cost: Oracle JDK documentation describes roughly **5–10%** performance overhead when enabled, and tracking consumes its own memory. Thus, NMT measurements are useful for analyzing **trends and category breakdowns**, but overhead must be accounted for—especially when comparing against a process without NMT or running in production.

### Verifying PID, NMT Level, and Attach Capability

In another terminal, use a compatible JDK `jcmd` and a user account authorized to attach to the process:

```bash
jcmd -l
jcmd 12345 VM.native_memory summary scale=KB
jcmd 12345 help VM.native_memory
```

**Replace `12345` with the real Java PID**; do not run the illustrative number literally. `jcmd -l` lists visible Java processes; inside containers, PID namespaces and attach permissions may differ from the host. If the command reports NMT is not enabled, restart the application with the appropriate flag. If `detail.diff` is unavailable because tracking is at `summary`, you cannot upgrade that level via `jcmd` on the current JVM.

## 3. Choosing a Baseline for a Meaningful Measurement

The starting point does not have to be immediately at JVM launch. Class loading, JIT compilation, connection pools, cache initialization, and the GC subsystem can grow categories rapidly during warm-up; if you baseline too early, subsequent diffs mainly measure **startup** rather than the workload under investigation.

Controlled workflow:

1. **Fix the environment:** record JDK/vendor/version, GC, `-Xms`/`-Xmx`, memory-related flags, container limits, thread count, and application version.
2. **Warm up to steady state:** process a representative volume of requests and confirm pools/caches/class loading are relatively stable; this is state T0.
3. **Save an absolute report before the checkpoint:** `summary` or `detail` helps provide context when reading deltas.
4. **Create a baseline once at T0.** Record the timestamp externally or in your experiment log.
5. **Apply controlled load:** record RPS, concurrency, payload size, queue depth, class/session/cache counts, and scaling factors.
6. **Read diffs periodically at T1, T2…** without calling `baseline` again, so all compare against T0.
7. **Reduce load and wait for in-flight work to finish**, then read T3. If any category remains elevated, verify owner/lifecycle before concluding.
8. Only **rebaseline** when intentionally starting a new investigation window (e.g., measuring solely from T2 to T3); clearly note the changed reference point.

The recommended sequence is **baseline after warm-up → measure steady load → increase load → reduce load → measure post-recovery**. Repeat the same type of workload long enough to distinguish a sustained upward trend from temporary allocations.

### Practical Command Sequence with `summary`

Suppose the JVM is running with `-XX:NativeMemoryTracking=summary` and the real PID is `12345`. The following commands are examples for a Linux/macOS terminal or Bash shell:

```bash
PID=12345

# T0: application warmed up, save absolute snapshot.
jcmd "$PID" VM.native_memory summary scale=KB > nmt-t0-summary.txt

# Set checkpoint. This resets the baseline used by subsequent diffs.
jcmd "$PID" VM.native_memory baseline

# T1: after a steady-load phase.
jcmd "$PID" VM.native_memory summary.diff scale=KB > nmt-t1-summary.diff.txt

# T2: after increasing load without changing the baseline.
jcmd "$PID" VM.native_memory summary.diff scale=KB > nmt-t2-summary.diff.txt

# T3: after reducing load, waiting for queues/tasks to drain, and reading again.
jcmd "$PID" VM.native_memory summary.diff scale=KB > nmt-t3-summary.diff.txt

# View current absolute values when needed to explain deltas.
jcmd "$PID" VM.native_memory summary scale=KB > nmt-t3-summary.txt
```

The comments `T1/T2/T3` represent load ramp-up/ramp-down actions performed **between commands**; the NMT commands themselves do not generate workload, wait for queues to drain, or measure RSS. On PowerShell, replace Bash variable syntax with the literal PID (e.g., `jcmd 12345 ...`) or a PowerShell variable `$pidOfJava`, avoiding PowerShell's special `$PID` variable.

**Why choose `scale=KB`?** For small deltas, using MB/GB can round some entries down to 0. Save reports in KB for comparison and convert to MB/GB only when presenting. `scale` changes the display unit, not the underlying memory amount.

## 4. Reading `summary.diff` Correctly

NMT generally presents two independent concepts:

| Field | Meaning | Misconception to Avoid |
| --- | --- | --- |
| `reserved` | Size of **pre-reserved virtual address space** | Does not equal physical RAM in use |
| `committed` | Size of memory regions the VM has **committed** under its memory management | Does not equal RSS, nor live Java object size |
| `malloc` | Memory allocated via HotSpot-tracked malloc paths | Does not cover all native libraries outside HotSpot |
| `mmap` | Mapped/reserved regions and associated commits | Read reserved and committed separately; do not blindly double-count with category total |
| `#` after items like `thread`, `classes`, `malloc` | Number of threads, classes, or allocations reported in context | Not always Java object count or request count |

**Mock output example for practicing reading**; many categories are omitted, and it is not a snapshot of a specific application:

```text
Native Memory Tracking:

Total: reserved=4000000KB +65536KB, committed=500000KB +28672KB

-                 Java Heap (reserved=2097152KB, committed=262144KB)

-                    Thread (reserved=256000KB +32768KB,
                            committed=22000KB +4096KB)
                            (thread #250 +32)

-                     Class (reserved=1060000KB +8192KB,
                            committed=40000KB +6144KB)
                            (classes #6000 +900)

-                     Other (reserved=30000KB +16384KB,
                            committed=30000KB +16384KB)

... (remaining categories omitted)
```

Line-by-line interpretation:

- `Total committed=500000KB +28672KB`: at measurement time NMT reports total committed of 500,000 KB, **28,672 KB higher than the baseline**; it does not mean "just increased by 28,672 KB since the previous diff".
- `Thread reserved +32768KB` with `thread #250 +32`: there are 32 more threads than at baseline and more stack/thread space reserved. This points to checking thread pools, thread dumps, and thread lifecycles. **Higher reserved does not prove 32 MB of RAM is resident.**
- `Class committed +6144KB` and `classes +900`: more classes are retained/loaded than at baseline; this could be warm-up, valid dynamic/plugin class loading, or uncollected class loaders. Count class loaders, check class unloading, and inspect metaspace before calling it a leak.
- `Other committed +16384KB`: the `Other` category grew by 16 MB. This signals checking relevant JVM allocations, **not automatically blaming direct buffers or a specific library** based on the name alone.
- `Java Heap reserved` at a fixed value: may simply be stable `-Xmx`/heap reservation. NMT does not tell you which Java objects are alive; use GC/heap-used metrics if Java heap retention is suspected.

### Reading `+` and `-` Signs

- `committed=12000KB +4096KB`: currently 12,000 KB, **net increase of 4,096 KB relative to baseline**.
- `committed=12000KB -2048KB`: currently 12,000 KB, **net decrease of 2,048 KB relative to baseline**.
- `committed=12000KB` with no delta suffix in a diff line: typically no visible change at that display resolution.
- `classes #6000 +900`: currently 6,000 classes per the report's counter, 900 more than at baseline.

`+`/`-` signs per category represent **net change at sampling time**, which can combine allocations and deallocations that occurred in the interval. Do not add a category's sub-lines and its total line into a new total; they usually show **the same memory at different levels of breakdown**. The JVM-wide total also includes categories not shown in the excerpt.

### Comparing Three Diffs Against the Same Baseline

**Illustrative** log table (all deltas relative to T0, in MB; hypothetical workload):

| Checkpoint | Active Threads | Delta Thread Committed | Delta Class Committed | Delta Other Committed | What to Check |
| --- | ---: | ---: | ---: | ---: | --- |
| T0: baseline | 80 | 0 | 0 | 0 | Reference checkpoint |
| T1: steady load | 100 | +3 | +2 | +12 | Growth with workload |
| T2: increased load | 150 | +8 | +3 | +30 | Concurrency and allocations increased |
| T3: load back to baseline | 82 | +1 | +3 | +1 | Thread/Other nearly recovered; Class still retains +3 MB |

Reasonable preliminary conclusion: `Thread` and `Other` appear **reversible with load**, showing no evidence of sustained post-recovery growth yet; `Class` remains above baseline and needs comparison between legitimate class loading and live class loaders. Do **not** infer "Class +3 MB = leak" without evidence that classes should have unloaded.

If T3 still held `Other +30 MB` despite empty queues, that is a **suspect point**, not yet a verdict. Repeat cycles, inspect `detail.diff` (if enabled), and verify owner/allocator.

## 5. When to Use `detail.diff` and How to Read It

`summary.diff` answers "**which category** is growing?". When a category grows consistently across comparable measurements, `detail.diff` answers more deeply "**which allocation site or virtual address region** changed?". To use this report, the JVM must start with:

```bash
java -XX:NativeMemoryTracking=detail -Xms256m -Xmx1g -jar app.jar
```

In another terminal, after warm-up:

```bash
PID=12345
jcmd "$PID" VM.native_memory detail scale=KB > nmt-t0-detail.txt
jcmd "$PID" VM.native_memory baseline

# After running the recorded workload:
jcmd "$PID" VM.native_memory summary.diff scale=KB > nmt-t1-summary.diff.txt
jcmd "$PID" VM.native_memory detail.diff scale=KB > nmt-t1-detail.diff.txt
```

At `detail` level, you can read **both** summary and detail. If only `summary` was enabled, do not expect `detail.diff` just because `baseline` was called.

A **simulated** snippet of call-site content (addresses, function names, and allocation sizes are illustrative only):

```text
[0x00007fff01234567] ExampleHotSpotAllocator::allocate(...)
                 (malloc=20480KB type=Other +16384KB #480 +384)

[0x00007fff07654321] ExampleVMRegion::reserve(...)
                 (reserved=65536KB +32768KB, committed=8192KB +4096KB)
```

How to approach it:

1. On the `malloc` line: 20,480 KB is the current total at this call site; `+16384KB` is the increase over baseline. `#480 +384` shows the allocation count NMT reports for this context, up by 384—**not 384 Java objects or 384 requests**.
2. On the address-region line: separate `reserved +32768KB` from `committed +4096KB`. Looking only at reserved easily exaggerates real RAM impact.
3. Look for **call sites with steadily growing committed/malloc deltas** across measurements with the same workload; category totals are only the starting point.
4. Connect the call site to the corresponding Java/HotSpot subsystem and operational metrics: thread counts, class loaders, direct/mapped buffers, queues, workers/caches.
5. Check deallocation when the workload stops and watch trends across multiple cycles. A call site with a positive delta while the app holds legitimate data is not automatically a leak.

`detail` content depends on JDK version, debug symbols, platform, and allocation type. Some lines may show internal HotSpot call stacks or `mmap`/virtual memory maps rather than `malloc`. **A growing allocation site is where to investigate, not automatically a bug in that exact function.** A higher-level owner may legitimately need the memory; conversely, an unintentionally long-lived owner can keep the allocation alive.

Detail tracking uses more resources than summary and generates long reports. For critical environments, plan measurement duration, storage space for outputs, and operational impact.

## 6. From `summary.diff` to Root-Cause Hypotheses

Once you know which category is growing, connect NMT data with other measurements:

| Growing NMT Category | Next Question | Additional Evidence Sources |
| --- | --- | --- |
| `Thread`: reserved/committed and `thread #` rising | Is a thread pool scaling with load, or are threads failing to terminate? | `jcmd <pid> Thread.print`, live thread metrics, executor pool/queue, lifecycle |
| `Class`: class count, metaspace committed rising | Are new classes/lambdas/proxies continuously loaded? Which class loader should have unloaded? | JFR class load/unload, `jcmd <pid> VM.classloader_stats`, class loader retention |
| `Code`/`Compiler` rising | Is JIT still warming up, or is there abnormal compilation activity? | Code cache, compilation metrics/JFR, stabilization time |
| `GC` rising | Is the JVM/collector expanding GC structures to match heap/workload? | GC logs, heap committed, collector/config |
| `Other`/`Internal` rising | Are buffers/off-heap or HotSpot allocations involved? | `detail.diff`, direct/mapped `BufferPoolMXBean`, JFR, native-using components |
| `Java Heap` committed rising | Is the VM committing more heap, or are live Java objects growing? | GC logs, heap used after comparable GCs, heap dump/histogram |
| `Native Memory Tracking` rising | Is this overhead of the measurement tool itself? | NMT tracking overhead, snapshots under same config |

In Java, checking direct/mapped buffers via `java.nio:type=BufferPool` (JMX) or `BufferPoolMXBean` helps cross-check. **Do not assume** every byte in NMT `Other` is a direct buffer: categorization depends on the allocation path and JVM version. Also, `BufferPoolMXBean` only reflects pools exposed by the JVM, not every `malloc` in JNI code.

### Three Diagnostic Scenarios

**Scenario A — Thread grows as traffic rises.** T1 shows `Thread reserved +64 MB`, thread count `+64`; when traffic returns to normal and the executor scales down threads, T3 drops to `+2`. This may be load-driven scaling. Verify with thread dumps and pool config; if thread counts keep climbing across identical load cycles even after work finishes, check thread creation and cleanup.

**Scenario B — Class grows across repeated plugin reloads.** After each reload, `Class committed` and class/class-loader counts grow together; T3 does not drop even though old versions should no longer be used. This suggests class loader retention. NMT only isolates the category; check classloader stats, references holding old loaders, threads, registries/listeners, and verify after fixing. Do not automatically call warm-up a `metaspace leak`.

**Scenario C — RSS grows while NMT barely changes.** Process RSS grows by 300 MB while NMT-tracked total `committed` stays nearly flat. This **does not rule out** a native memory issue: NMT does not cover allocations outside HotSpot (e.g., JNI libraries calling malloc directly), and committed is not identical to RSS. Inspect `/proc/<pid>/smaps`, `smaps_rollup`, `pmap`/native profilers depending on OS, memory mappings, thread stacks, container/cgroup, and relevant native libraries.

## 7. Step-by-Step Practical Investigation Workflow

**Step 1 — Define the exact symptom.** Is RSS/cgroup rising, Java heap used rising, native allocation OOMing, or just a large `reserved` region? Plot at least one representative workload interval rather than relying on a single number.

**Step 2 — Choose the NMT mode.** Start with `summary` if the category is unknown. Choose `detail` when reproducible and allocation sites are needed; planning a restart with `detail` is part of the test.

**Step 3 — Record a meaningful baseline.** Only after warm-up matching your test goal. Save absolute values, timestamp, PID, JDK version and config, and current workload.

**Step 4 — Measure multiple checkpoints on the same baseline.** Capture `summary.diff` at steady load, peak load, after load drop, and after reasonable recovery. Place deltas next to request concurrency, active threads, queue depth, class counts, and buffer usage.

**Step 5 — Pick the category with sustained growth.** Watch `committed` and relevant `malloc`/`mmap`, without equating `reserved` to RSS; check whether growth matches warm-up or a bounded working set.

**Step 6 — Drill down with detail and complementary tools.** Trace call sites with growing deltas and check allocation owner and lifecycle. Where NMT lacks coverage, switch to OS metrics/native profilers or JNI-specific tools.

**Step 7 — Form a falsifiable hypothesis.** For example, "every 1,000 plugin reloads, old class loader count rises and Class committed increases even when no requests use old plugins." Design a load-drop/cleanup test for the hypothesis.

**Step 8 — Fix and re-measure under identical conditions.** Set a new baseline after warm-up on the fixed version and compare delta trends across *the same duration, same traffic, and same sequence*. You can compare absolute snapshots between two JVMs, but **never apply an internal diff of JVM A against JVM B's baseline**.

### Session Measurement Log Template

| Field to Record | Example |
| --- | --- |
| JVM, PID, NMT | JDK 21, PID 12345, `detail` |
| Heap/config | `-Xms256m -Xmx1g`, collector and container limits noted separately |
| Baseline | T0 after 5 minutes of representative warm-up |
| Workload | RPS, concurrency, payload size, key cardinality, queue length |
| Checkpoints | T1 after steady load, T2 after stress, T3 after load drop |
| Saved reports | `nmt-t0-detail.txt`; `summary.diff`/`detail.diff` files |
| Changing categories | Reserved and committed deltas, thread/class/allocation counts |
| Hypothesis | Pool scaling, legitimate cache/buffer, or uncleaned owner |
| Verification test | Compare lifecycles/counters, drop load, repeat cycles, and take extra snapshots |

## 8. Common Mistakes When Reading Diffs

**1. "`reserved +1 GB` means the JVM uses 1 GB more RAM."** False. Reserved is virtual address space; check committed and RSS/cgroup. Java heap or compressed class space can reserve large areas early without corresponding commits.

**2. "`committed +100 MB` is definitely a memory leak."** Insufficient. Heap expansion, pool/cache warm-up, JIT, or concurrency-driven thread growth could explain it. Ask whether memory returns to baseline/plateaus after workload ends and has a legitimate owner.

**3. "Running `summary.diff` twice gives the change between those two runs."** False. Both compare against the most recent baseline. To compare T2 against T1 specifically, set a new baseline at T1 and note the reference change, or subtract absolute figures using consistent units/rules.

**4. "You can enable `detail.diff` mid-flight without restarting."** No. The NMT tracking level is set at startup. If the current level is `summary`, you need another JVM started with `detail`.

**5. "Rising class count means a class loader leak."** Not necessarily. Startup/JIT, dynamic proxies/lambdas, and legitimate modules can all raise class counts. Check class unloading, unused loaders, and retention paths keeping old loaders alive.

**6. "If NMT is stable, there is no JNI/native leak."** False. NMT does not track all allocations performed by native libraries outside HotSpot. RSS or cgroup memory can grow independently of NMT reports.

**7. "`detail.diff` points straight to the leaking Java line."** No. It shows **HotSpot call sites** and tracked virtual memory regions, not a direct answer for the Java owner graph or every native library. Correlate with stacks, subsystems, and object lifecycles.

**8. "A negative diff proves all memory was freed."** No. It shows a **net decrease relative to baseline** in that category/unit; long-lived allocations, fragmentation, or memory outside NMT's scope can still remain.

**9. "Baselining right at process start always measures everything better."** Not necessarily. If the goal is post-warm-up workload growth, an overly early checkpoint mixes in class loading, code cache, and pool initialization. Choose the baseline to match your question, and record the timestamp.

**10. "Switching to `scale=MB` saves more memory."** No. It is only a display unit; for small deltas it can round away the signal. Use KB when tracking small but persistent growth.

## 9. Conclusion Sign-Off Checklist

Before writing a "native memory leak" report, confirm:

- [ ] Correct PID/JDK; JVM started with `-XX:NativeMemoryTracking=summary` or `detail` **from launch**.
- [ ] T0 set after appropriate warm-up; all `baseline` calls are known and which checkpoint each diff references.
- [ ] Multiple checkpoints under comparable load and load-drop phases; no trend inferred from a single snapshot.
- [ ] `reserved` and `committed` interpreted separately, not equated with RSS or live Java heap objects.
- [ ] Growing category shows repeatable deltas and is cross-checked with thread/class/buffer/queue/workload metrics.
- [ ] Where needed, `detail.diff` identified HotSpot call sites/VM regions to investigate; out-of-scope NMT regions were considered.
- [ ] Clear hypothesis on owner, bounds, and release timing, with a test to falsify or confirm it.
- [ ] After the fix, the same test shows memory plateauing or returning to expected baseline while performance/functionality remain acceptable.

**Core message:** `baseline` fixes the comparison timestamp; `summary.diff` shows **which memory category changed**; `detail.diff` brings you closer to **where HotSpot allocated/mapped memory**. All three are evidence-gathering tools, while confirming a leak requires time-series trends and owner-lifecycle verification.

### Official References

- Oracle JDK 21 — *Native Memory Tracking*: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
- Oracle JDK 21 — *Diagnostic Tools / Native Memory Tracking*: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 — *Troubleshoot Memory Leaks*: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html
