# 17.5 Warm-Up, Tiered Compilation, and Their Impact on Profiling Results

## 1. Why Can the Same Java Code Run Progressively Faster?

On HotSpot, **a Java method is not necessarily executed using one fixed code form throughout the JVM's lifetime**. Initially, the JVM typically uses the interpreter; once a method or loop is invoked often enough, the JIT (*Just-In-Time compiler*) can compile it into machine code and optimize it further based on observed runtime behavior. **Tiered compilation** coordinates fast compilation levels with deep optimization to balance **startup time, internal profiling cost, steady-state performance, and optimization assumption accuracy**.

Consequently, two measurements running the same logic can differ because:

- On the first run, the JVM still has to load/verify/initialize classes, build runtime structures, and touch cold code paths.
- The interpreter and C1-generated code can differ in speed, profiling-instrumentation cost, and stack shape compared to C2.
- Compiler threads may consume CPU in the background, competing for resources with application threads.
- C2 can inline methods, eliminate temporary allocations, reorder computations, or specialize branches based on type profiles.
- Breaking an optimization assumption about types/branches can trigger **deoptimization**, returning the method to a safe execution path and later recompiling it.
- GC, class loading, caches, connection pools, and the OS also produce their own warm-up effects, **which must not all be blamed on the JIT by default**.

**Lesson goal:** accurately explain HotSpot tiers, recognize warm-up state in compilation logs/JFR, avoid wrong conclusions from CPU/latency charts while code is still transitioning, and design measurements separating **startup** from **steady-state**.

Scope is HotSpot on JDK 17+, illustrated with JDK 21. Other JVMs (such as runtimes using different compilers or native images) do not follow every C1/C2 detail below; always verify the actual JVM/version/flags.

## 2. "Cold", "Warming Up", and "Hot" Are Observed States, Not a Fixed Number of Seconds

| Phase | What Typically Happens | Measurable Signals | Confusions to Avoid |
| --- | --- | --- | --- |
| **Cold start** | JVM starts; class loading, initialization; code first runs via interpreter or pre-existing code | Startup time, classes loaded, compilation begins, first-request latency | Attributing all initial latency to JIT |
| **Warm-up** | Frequently used methods/loops cross the "hot" threshold; C1/C2 compile, gather type profiles, caches/pools initialize | Compilation events, code cache growth, throughput/latency shifting across rounds | Assuming the app is warm merely because 30 seconds passed |
| **Relatively steady** | Main code paths are optimized for the current workload; some caches reach steady size | Metrics across consecutive windows under comparable load stay close | Declaring the whole JVM "done with JIT"; rare paths can still warm up later |
| **Re-optimization** | Workload/type distribution shifts; deopt, class loading, recompilation, code cache pressure | CPU/latency spikes, deopt or new compile events | Assuming once-stable means stable forever |

A service running for 2 hours can still be **cold for a rare code path** invoked for the first time. Conversely, a job running for a few seconds can have a loop hot enough to trigger OSR/JIT optimization within that very run.

**Warm-up must be defined according to what you are measuring:** startup latency must include legitimate cold time; peak throughput measurements must explicitly state how warm-up was excluded or report it separately. Never quietly discard startup data and present the remainder as overall product performance.

## 3. Tiered Compilation in HotSpot: Interpreter, C1, and C2

In a typical HotSpot Server VM, tiered compilation is enabled by default. The table below describes **execution tiers**; the numbers are *compilation levels* in diagnostic output, not method invocation counts.

| Level | Mechanism | Profile Data | Purpose |
| ---: | --- | --- | --- |
| **0** | Interpreter | Can collect runtime info to guide compilation decisions | Fast initial execution startup |
| **1** | C1, basic optimizations | No full profiling instrumentation attached | Fast native code generation, suited for simple methods/specific paths |
| **2** | C1, limited profiling | Primarily invocation/backedge counters | Preserve speed while tracking "hotness" |
| **3** | C1, full profiling | Collects dynamic data for further decisions/optimization | Balance speed and profile quality fed to C2 |
| **4** | C2, deep optimization | Uses accumulated profile; does not necessarily keep emitting the same profiling data | Long-term performance on hot code paths |

A **common but non-mandatory** progression:

```text
New method -> Level 0 (interpreter)
               |
               +----> Level 3 (C1 + full profiling)
                           |
                           +----> Level 4 (C2 optimized)
               |
               +----> Level 2 (C1, limited profiling under changing compiler load)
               |
               +----> Level 1 (C1 without profiling, suited for simple methods)

Compiled code --[assumption no longer holds]--> deoptimization
                  |
                  v
          Interpreter / other suitable code
                  |
                  +----> recompilation at appropriate level
```

Not every method follows `0 → 3 → 4`. Policy also considers invocation counters, loop backedge counts, compiler queues, method size, type info, compilability, and VM/configuration thresholds. A rare method may remain in the interpreter; a trivial method may stop at level 1. Transitions, replacements, or reclamation of compiled code can occur throughout execution.

**C1** prioritizes fast compilation with lower compile cost; **C2** can spend more CPU/time for deep optimizations such as inlining and speculative optimizations. This explains why **extra compiler CPU may be spent at startup** while subsequent requests run faster.

### Tiered Does Not Mean "Compile Everything Up Front"

JIT typically compiles based on **observed demand**, rather than running a full-bytecode compile pass before the service accepts requests. Only methods with sufficient hotness enter the compile queue. Thus you cannot measure "startup finished" and assume every endpoint, payload type, and query path is already optimized.

### OSR: A Loop Warms Up Before the Method Returns

**On-Stack Replacement (OSR)** allows transitioning a long-running loop from interpreted/older code to compiled code at a safe point when conditions allow, without waiting for the method to return and be called again.

In `-XX:+PrintCompilation`, the `%` symbol usually marks an OSR compilation. A method called once in a request yet containing a loop of millions of iterations can become hot enough to trigger OSR. When reading profiling results, check whether compilation occurred mid-execution of **a single call**.

## 4. Hotness, Type Profiles, Inlining, and Deoptimization

### 4.1. "Hot" Is Decided by Activity, Not Method Names

Two primary sources matter:

1. **Invocation count:** how many times a method is called.
2. **Backedge count:** how many times execution branches back to the start of a loop.

Load and compiler queues can adjust effective thresholds. Never bake a rigid number like "exactly 10,000 calls means C2" into benchmarks: HotSpot thresholds depend on policy, build, flags, and runtime behavior.

### 4.2. Dynamic Data Profiles Enable Specialization to Reality

Suppose an interface `Parser` has two implementations, `JsonParser` and `XmlParser`. If most call sites only see `JsonParser` initially, JIT can optimize for that type profile, inline the frequent call path, and insert guard checks. When the workload begins sending many `XmlParser` instances, the prior assumption may become unprofitable or invalid; the JVM may deopt and/or recompile to handle the new distribution.

This is a **possible mechanism**, not a guarantee that every interface call deopts whenever a new subtype appears. Always inspect actual compilation/deoptimization evidence.

### 4.3. Inlining Changes Flame Graph Shapes

Example with two methods:

```java
static long process(long x) {
    return transform(x) + 1;
}

static long transform(long x) {
    return x * 31;
}
```

This is an **illustrative snippet**, not a standalone program. After optimization, the compiler may inline `transform` into `process`, removing call overhead and changing how profilers attribute frames/hotspots. A method **appearing less or vanishing** from sample stacks does not prove it stopped running; you must understand inlining, stack reconstruction, and how tools display *inlined frames*.

Do not equate "40% of sampled stacks" with "exactly 40% of invocations or 40% of latency." CPU sampling is point-in-time observation with finite resolution and bias.

### 4.4. Deoptimization Is Not Automatically a Bug

**Deoptimization** is the mechanism ensuring correctness when optimized code relies on an assumption that no longer holds or when the VM must fall back to a safe state. It may be followed by new compilation. In logs, "`made not entrant`" may simply mean one compiled code version was superseded by a higher-tier version or invalidated; it **does not by itself prove** a bug or regression.

Read deopt events alongside **timestamp**, **reason/action**, method/compile id, workload shifts, and latency. A single startup deopt is very different from continuous deopt/recompile loops in steady state.

## 5. Why Profiling Shifts Across Phases

When a profiler samples from startup into steady state, it mixes **multiple execution modes**. Each measurement is affected differently:

| Metric | What Can Cold/Warm-Up Do? | How to Read Correctly |
| --- | --- | --- |
| **Wall-clock latency** | Includes class loading, initialization, interpreter, JIT, queueing, pool/cache init | Separate first-hit/cold vs. warmed; do not mix wait time into "method CPU" |
| **CPU profile / JFR execution samples** | Stacks may be in interpreter/C1/C2; compiler threads active; inlining/OSR shifts attribution | Analyze by time window, thread, event settings, and sample count |
| **JFR compilation events** | Compilations often cluster as code warms; may include C1, C2, OSR | Verify event enabled and threshold; missing events ≠ no compilation |
| **Code cache** | Native compiled code added; sweeping/unloading or pressure may occur | Check capacity/used and `CodeCacheFull`/compiler queue when needed |
| **Allocation/GC profile** | Class init and cache fill raise allocation; C2 may eliminate some allocations | Compare by workload/post-GC; do not blame every allocation delta on JIT |
| **Throughput** | Can rise as C2 completes, yet also depends on GC, CPU frequency, load, and I/O | Report per window, load conditions, and distribution |
| **p99 latency** | Can spike from compiler CPU, safepoints, GC, connection setup, or deopt | Do not conclude causality solely from a JIT timestamp near a spike |

**Core issue:** if you capture a 60-second CPU profile comprising 10 seconds cold and 50 seconds warm, the average represents neither **the first 10 seconds** nor **steady state after 5 minutes**.

If the goal is optimizing startup, **isolate** the cold window and analyze classloading/compilation/initialization; if the goal is long-term stability, measure after warm-up using verifiable criteria. Both are valid because they answer two different questions.

## 6. Using Compilation Logs to See When Methods Change Tiers

In a HotSpot lab environment, enable:

```bash
java -XX:+PrintCompilation TieredWarmupDemo
```

This flag prints method compilation activity to the console, possibly interleaved with application stdout. It increases log volume and incurs overhead, so **do not treat it as an "unobserved" baseline**. Redirect stdout when saving to a file; verify redirection behavior in your shell.

Example **illustrating structure only**, not guaranteed demo output:

```text
[timestamp] [compileId] [flags] [level] [Class::method] [bytecodeSize]
...                    %          3     TieredWarmupDemo::main  (...)
...                               3     TieredWarmupDemo::mix   (...)
...                               4     TieredWarmupDemo::mix   (...)
...                                     made not entrant
```

When reading real output, focus on:

- **Timestamp column:** usually **milliseconds since JVM start**; do not match directly to UTC wall clock without normalizing.
- **Compilation ID:** links trace lines for one compilation; not an object ID or call count.
- **Level:** `3` is typically C1 full profiling, `4` is C2. Do not equate "level 4" with JFR samples.
- **`%`:** OSR compilation for code at a loop backedge.
- **`made not entrant` / `made zombie`:** compiled code states; need context before calling them slow deoptimizations.
- **Method name and bytecode size:** indicates what was compiled; a method may also be inlined into another caller.

Many **JDK/framework** methods are compiled too, not just application methods. One method appearing multiple times may be compiled at different tiers, via OSR, or re-optimized. Never measure "exact method call count" by counting compile lines.

### Writing More Structured Compile Logs

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=hotspot-compile.xml TieredWarmupDemo
```

`-XX:+LogCompilation` and `-XX:LogFile=...` provide detailed recording for JIT analysis, yet carry overhead and create large files; check write permissions and impact before using on a live service. The XML log contains richer detail than console compilation output, yet **does not replace** measuring request performance.

To inspect inlining decisions in a lab:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -XX:+PrintCompilation TieredWarmupDemo
```

Output can be huge; an "inline" message indicates the compiler's decision in that context, and **does not guarantee** the method is inlined at every call site or in every compiled version.

## 7. Observing the Compiler on a Running JVM

When you have the JVM PID, JDK tools, and attach permissions:

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 Compiler.queue
jcmd 12345 Compiler.codecache
jcmd 12345 Compiler.codelist
```

Replace `12345` with the actual PID; do not use the PID of an exited process. Each command serves a different purpose:

| Command | What It Provides | Limitations |
| --- | --- | --- |
| `VM.flags` | Actual JVM configuration, including effective flags | Does not replace per-method optimization history |
| `Compiler.queue` | Compilation tasks waiting at snapshot time | An empty queue at one instant does not prove no prior compilation |
| `Compiler.codecache` | Code cache capacity/usage and related segments | A full cache can impact JIT; a large cache alone is not a leak |
| `Compiler.codelist` | List of live compiled methods in code cache | Snapshot, large output, higher cost than queue/codecache |
| `jcmd PID JFR.check verbose=true` | Active JFR recordings and event settings | Does not show events already dropped from retention or unrecorded |

Attach commands require matching user/namespace. Containerized apps can have a different PID when viewed from the host; the JVM may disable attach or tools may be absent in minimal runtime images. Do not hunt for evidence by arbitrarily altering production namespaces/permissions.

## 8. JFR: Inspecting Compile Times, Code Cache, and Deoptimization

When correlating JIT with CPU/latency/GC on a timeline, capture JFR from **the start** or before the code path of interest warms up. Example startup recording for the program in Section 9:

```bash
java -XX:StartFlightRecording=name=jit_warmup,settings=profile,disk=true,dumponexit=true,filename=warmup.jfr,jdk.Compilation#threshold=0ms TieredWarmupDemo
```

Here `jdk.Compilation#threshold=0ms` is a **specific setting** to avoid dropping short compilations due to duration thresholds. Each JDK's `default.jfc` / `profile.jfc` may filter out brief compilations; **zero events does not mean the JVM performed no JIT**. Check actual settings via `JFR.check verbose=true` (while the JVM is running) or inspect saved `.jfc` configs. Lowering thresholds increases event volume and overhead; use it for experiments needing detail and weigh carefully for long-term use.

After the JVM exits normally, inspect the file:

```bash
jfr summary warmup.jfr
jfr print --events jdk.Compilation,jdk.Deoptimization warmup.jfr
jfr print --events jdk.CompilerStatistics,jdk.CodeCacheStatistics warmup.jfr
```

Verify event names actually exist on **the target JDK** via metadata/`jfr summary`, and confirm they are enabled by recording settings. Useful events:

- **`jdk.Compilation`:** compile duration, compiler, level, method, compilation ID, and possibly an OSR indicator. It measures **compiler work**, not how much faster the method became.
- **`jdk.CompilerStatistics`:** compiler state/activity at statistical intervals when present in the recording.
- **`jdk.CodeCacheStatistics` / `jdk.CodeCacheFull`:** code cache state and signs of native-code storage pressure; gaps may reflect settings/period.
- **`jdk.Deoptimization`:** details when the VM encounters a condition requiring deopt; a single event does not prove a regression.
- **`jdk.ExecutionSample`:** stack samples of executing threads; compare windows before/after warm-up alongside valid sample counts.
- **`jdk.GarbageCollection`, `jdk.CPULoad`, thread/lock events:** check concurrent competing causes.

In **JDK Mission Control (JMC)**, select startup and steady-state ranges separately, filter by application threads vs. compiler threads, and compare JVM activity with independent latency/throughput metrics. Do not compute "CPU% of method X" from sums of disparate JFR events. Compilation events, periodic statistics, and execution samples have **different denominators**.

**Important limitations:** JFR can drop events due to thresholds, disabled events, sampling, retention, or recorder overhead/capacity; a recording started late lacks history from before it began. Both `PrintCompilation` and JFR add overhead; **keep tooling and settings identical when comparing two measurements**.

## 9. Self-Contained Java 17+ Example: Per-Round Latency in One JVM

Save the code below verbatim to **`TieredWarmupDemo.java`**. The program calls a method with data-dependent arithmetic across consecutive rounds, measures *raw* `ns/op` in the same JVM, prints a checksum so results remain observable, and sleeps briefly **outside the timed region** between rounds. This is an example to **observe the phenomenon**, not a rigorous microbenchmark.

```java
import java.time.Instant;
import java.util.Locale;

public final class TieredWarmupDemo {
    private static volatile long sink;
    private static final int OPERATIONS = 120_000;

    private static long mix(long value) {
        long x = value;
        for (int i = 0; i < 32; i++) {
            x ^= x << 13;
            x ^= x >>> 7;
            x ^= x << 17;
        }
        return x;
    }

    public static void main(String[] args) throws InterruptedException {
        int rounds = args.length == 0 ? 20
                : Integer.parseInt(args[0]);

        if (rounds < 1 || rounds > 80) {
            throw new IllegalArgumentException(
                    "rounds must be between 1 and 80");
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("mode=single JVM; rounds=" + rounds);

        for (int round = 1; round <= rounds; round++) {
            long checksum = 0;
            long started = System.nanoTime();

            for (int i = 0; i < OPERATIONS; i++) {
                long input = ((long) round << 32) ^ i;
                checksum ^= mix(input);
            }

            long elapsed = System.nanoTime() - started;
            sink = checksum;

            System.out.printf(Locale.ROOT,
                    "round=%02d end=%s ns/op=%.2f checksum=%d%n",
                    round, Instant.now(),
                    elapsed / (double) OPERATIONS, sink);

            Thread.sleep(75);
        }
    }
}
```

### Compile and Run in Normal Mode

In a terminal with JDK 17+:

```bash
javac TieredWarmupDemo.java
java TieredWarmupDemo
```

Output lines follow this **pattern**:

```text
PID=<JVM PID>
mode=single JVM; rounds=20
round=01 end=<timestamp> ns/op=<measured value> checksum=<integer>
...
round=20 end=<timestamp> ns/op=<measured value> checksum=<integer>
```

This is an **output structure template**; bracketed fields are placeholders for actual runtime values, **not literal stdout**. `ns/op`, timestamps, and checksums vary across runs; never invent fixed speeds or speedup factors. `checksum` depends on inputs/algorithm and should be logically deterministic for the same `round` in the same program, whereas performance numbers vary by environment.

On some machines, early rounds are slower and then drop as interpreter/C1/C2 transitions occur; on others, differences are small, noisy, or later rounds can even be slower due to GC, CPU frequency scaling, OS scheduling, resource contention, or compiler optimization effects. **There is no guarantee** every round gets faster than the previous one. A single rising/falling curve alone does not prove tier transitions.

### Re-Run with Compilation Logging

```bash
java -XX:+PrintCompilation TieredWarmupDemo
```

Look for `TieredWarmupDemo::mix` or `TieredWarmupDemo::main` in the compile output. Correlate compile timestamps and levels/OSR with changes in `ns/op`. Only say "consistent with tier transition" if **real compile evidence exists** and other factors have not been ignored.

### Try Two Comparison Modes in the Lab

```bash
java -XX:TieredStopAtLevel=1 TieredWarmupDemo
java -Xint TieredWarmupDemo
```

- `TieredStopAtLevel=1` caps optimization tiers primarily at C1 level 1: useful to illustrate the effect of not reaching C2. Do not assume it is always slower on every workload; other runtime flags also affect startup.
- `-Xint` runs purely in the interpreter, **without JIT machine code**. It is usually significantly slower on compute-intensive loops, yet this is a mechanism comparison, not a universal speedup ratio for every application.
- `-XX:-TieredCompilation`, if tested separately, **disables tiered compilation**, yet HotSpot can still compile using another compiler/non-tiered policy; it is **not equivalent** to `-Xint`.

Separate invocations create new JVMs, so you cannot treat `round=20` of one JVM as the "next round" of another JVM. Repeat runs and alternate run order to reduce OS/filesystem/cache bias; for serious benchmarking, use JMH with multiple forks.

### When Does `jcmd` Work Against the Demo?

The demo may finish quickly; `jcmd PID Compiler.queue` can only inspect a **living** JVM at execution time. You can run with a higher round count within the program's allowed limit:

```bash
java TieredWarmupDemo 80
```

Then in a second terminal, substitute the printed PID. If the process has already exited, do not infer "JIT didn't run" from a failed attach. For long-running profiling, design a dedicated workload/lifetime rather than turning a small demo into an infinite loop.

## 10. Reading Demo Results Without Misattributing Causes

Record a table for **the same JVM and same flags**:

| Round | Measured ns/op | Compilation Near This Window | GC / CPU / Environment | Working Conclusion |
| --- | ---: | --- | --- | --- |
| 1–2 | Actual value | Present/absent, C1? | Class init? CPU boost? | Cold / warming; insufficient to conclude |
| 3–7 | Actual value | OSR/C1/C2? | GC? Background compiler? | Transitions may be occurring |
| 8–15 | Actual value | Fewer compilations? | Comparable load? | Possibly approaching steady state |
| 16–20 | Actual value | Any deopt/recompile? | External noise? | Verify stability; do not assume |

**Conditional interpretation:**

- If `mix` appears at level 3 then level 4 and subsequent windows show a repeatable drop in `ns/op`, the hypothesis that JIT improved speed has support; still check CPU/GC/overhead before crediting the entire reduction to C2.
- If `ns/op` drops **before** level 4 appears, it may be due to C1, OSR, caches, CPU frequency, or other changes.
- If level 4 appears yet `ns/op` does not drop, the method may already be fast enough at a lower tier, time may be spent elsewhere, or the workload may be too simple/noisy.
- If a round suddenly slows down and recovers, check GC pauses, OS scheduling, compiler queues, CPU throttling, deopts, or code cache pressure; do not immediately blame a "JIT bug."
- If `-Xint` is slower, that shows compiled execution helps this workload; it **does not** tell you how much C2 contributes over C1 without comparing the proper tiers.

**Unit note:** `elapsed/OPERATIONS` in the demo measures **the average time of one `mix` call inside the outer loop**, including loop and checksum overhead; it is not HTTP request latency. Before citing such a number in an application report, specify the measured operation, CPU stability, sample size, confidence, and environment.

## 11. Typical CPU Profiling Biases During Warm-Up

### 11.1. Compiler Threads Can Consume CPU

During startup, C1/C2 compilation consumes CPU **outside request threads**. If total process CPU spikes, part of it may be background compilation; viewing a single request thread's profile may not reflect compiler-thread load. Conversely, a CPU flame graph filtered to application threads alone misses compiler CPU.

Solution: inspect JFR compiler statistics/events, per-thread CPU usage, and OS CPU metrics; separate *compiler CPU* from *application CPU* when forming hypotheses.

### 11.2. Inlining and OSR Shift Stack Attribution

In the interpreter, profilers may observe a clear chain of call frames. Once C2 inlines methods, one or more frames may be presented differently depending on how the profiler reconstructs logical stacks; you cannot subtract sample counts for method A before/after and claim logic A "disappeared." OSR can change execution state mid-loop, mixing multiple code forms in one window.

### 11.3. Sampling Window Length and Denominators

If baseline has only 20 execution samples while steady state has 2,000 samples, differing hot-method shares may simply reflect **uncertainty and selection bias**, not a real profile change. Compare identical JFR settings, observation durations, workloads, and sufficient sample counts; examine both absolute event counts and **the exact denominator of each event type**.

### 11.4. CPU Time Differs from Latency

A method consuming high CPU in a JIT profile does not automatically cause a proportional share of **wall-clock latency**. Requests may wait on DB/network/locks, sit in queues, or hit GC/safepoints; always align traces, request latency, and JVM activity over the same window.

### 11.5. Late-Started Profiles Miss the Startup Story

If recording begins after warm-up, seeing code at tier 4 in JFR **still does not** tell you how much cold-start time went into compilation or class loading. To analyze startup, start recording at JVM launch or early enough before the target events, and check retention/dump settings so the beginning is not overwritten.

## 12. Designing Measurements to Separate Startup and Steady-State

### Goal A — How Fast Does the App Serve Its First Requests?

Metrics to measure:

1. JVM process start → socket/service ready, if startup time actually matters.
2. First successful request latency for each representative code path.
3. p50/p95/p99 of **the first requests** or first 30–60 seconds, with defined traffic/payloads.
4. Concurrent JIT compilation, class loading, GC, and cache/connection-pool initialization.
5. Client-visible errors/timeouts/retries during the cold phase.

Do not discard first-hit latency and publish the rest as startup performance. When cold startup matters to user experience, warm-up must be treated as **part of the problem**, not noise to strip away.

### Goal B — How Much Can the Steady-State Service Handle?

1. Define workload, concurrency, dataset, JVM/GC flags, and CPU/memory limits.
2. Wait for **criteria-based warm-up**: throughput/latency windows fluctuate within acceptable bounds with no continuous burst of compile/deopt activity. This remains an empirical criterion, not "JIT has stopped."
3. Start the **measurement window** only after that threshold, documenting wait duration and warm-up operations.
4. Capture multiple windows under identical load, computing distribution/variance; check GC, compiler, CPU throttling, and I/O.
5. Repeat from **fresh JVMs (forks)** multiple times to capture run-to-run variance; control run order when comparing two variants.
6. Report throughput, p50/p95/p99, and CPU/GC under identical conditions; never conclude from a single `ns/op` number.

**No single warm-up iteration count fits every JVM.** You need matching workloads and evidence of sufficiently stable behavior; sometimes cache/DB/network warm-up takes longer than JIT. For microbenchmarks, use **JMH**, which handles warm-up iterations, measurement iterations, and forks while avoiding common optimization and benchmark-design pitfalls. The demo in Section 9 is only for learning the phenomenon.

### Goal C — Impact of a Small Code Optimization

When comparing **A vs. B**:

- Run both with identical JDK/GC/flags, hardware/CPU quota, data, and workload.
- Define cold vs. steady **before** measuring; capture both separately if the product cares about both.
- Use multiple JVM forks; do not run A first, warm the JVM, then run B in the same process and call it a fair comparison.
- Prevent dead-code elimination by keeping outputs observable, while avoiding flawed side effects/blackholes that distort the task.
- Choose metrics directly answering the goal: CPU, throughput, tail latency, allocation, or startup.
- Compare total operating cost and stability, not just one good p50 run.

If JIT flags differ, treat that as a **runtime policy change**, not a neutral "measurement switch." Document all flags in the report.

## 13. Example Analysis Across Two Windows

Suppose under the **same hypothetical load** and with no deployment changes:

| Window | Requests/s | p95 Latency | Compiler Activity | GC |
| --- | ---: | ---: | --- | --- |
| Cold 0–30 s | 500 | 180 ms | C1/C2 elevated, class init | Active |
| Warm 30–90 s | 500 | 105 ms | Fewer compilations, some code reaches level 4 | Active |
| Stable 90–180 s | 500 | 80 ms | No compilation bursts seen | No abnormal pauses |

These numbers are **purely hypothetical**, only illustrating the method. You may state:

> "Across 3 windows with the same workload, p95 dropped from 180 to 80 ms, a reduction of about 55.6%; meanwhile most observed compilation clustered in the early phase. This is **consistent** with a warm-up effect, though not yet proof that JIT caused the entire drop. We still must check caches/pools/GC, compiler threads, and repeat across multiple runs."

Do not write: "JIT saved exactly 100 ms of p95." That reduction could also stem from warmed connection pools, completed class init, DB caches, or OS variation. Attributing exact shares requires controlled experiments, potentially with experimental flags or isolated component measurements. Never subtract two percentiles and assign the delta to one mechanism.

### "Double the Speed" Comparisons Have Limits Too

A demo loop dropping from `100 ns/op` to `50 ns/op` gives a `100/50 = 2x` ideal throughput ratio on that operation; that is a hypothetical comparison for a **micro-operation** in the **same environment**, and does not mean end-to-end requests run twice as fast. Request models include network/DB/GC and other work; optimizing one part cannot scale total latency by the same factor.

## 14. Common Scenarios in JIT Analysis

| Observation | Open Explanations | Verification Direction |
| --- | --- | --- |
| First request very slow, improves after 30 requests | Class init, cache/pool warm, interpreter→C1/C2, lazy configuration | JFR classloading/compilation, logs, request traces |
| High CPU at startup while request throughput is still low | Compiler threads, class loading, GC, DB warm-up, contention | Thread CPU + JFR compiler stats + non-JVM metrics |
| `PrintCompilation` shows level 4, latency still high | Requests mostly wait on I/O/locks, another method is the bottleneck, not all paths warmed | Request spans, flame graph for exact window, per-endpoint metrics |
| Samples in method A drop after warm-up | Inlining, optimization, workload mix, or sampler changes | JIT logs, stack reconstruction, per-thread sample counts |
| `made not entrant` appears near spike | Compiled code version replaced or assumption shifted; time overlap alone is insufficient | JFR deopt, reason, repeated measurements, GC |
| Every deploy causes bad p99 for a few minutes | JIT, cache/pool warm, traffic shifting, and startup load | Align ready/startup probes, classloading, workload |
| Long-running service suddenly slows when new traffic type arrives | Cold paths, uncommon trap/deopt, cache misses, GC, external dependency | Split traffic mix, compile/deopt events, traces |
| Code cache tight, compiler queue growing | Code cache/compilation pressure, many generated classes, or workload shift | `Compiler.codecache`, `Compiler.queue`, JFR CodeCache events |
| JFR has no compilation events yet compiled methods exist | Recording started late, threshold filtering, disabled event, retention gap | `PrintCompilation` in lab, check settings, codelist |
| `-XX:TieredStopAtLevel=1` wins on a short startup test | C1 starts fast; C2 compile cost not yet amortized | Compare both cold and steady across multiple forks |

## 15. Fourteen Mistakes to Avoid

1. **"Warm-up = sleep 30 seconds."** Without the right workload, critical methods may stay cold.
2. **"Reaching level 4 means the whole service is optimized."** Only one method/version was compiled; other paths remain.
3. **"`TieredStopAtLevel=1` equals `-Xint`."** C1 still generates native code; interpreter-only is a different mode.
4. **"`-TieredCompilation` means no JIT."** Non-tiered HotSpot can still compile; distinguish it from interpreter-only.
5. **"One compile line = one method call."** Compilation is compiler activity, not method invocations.
6. **"Many `made not entrant` lines = JVM bug."** May simply be replacing lower-tier code or other normal transitions.
7. **"No JFR compilation events = no JIT."** Events may be threshold-filtered, disabled, or outside the recording window.
8. **"Fewer methods in sample stacks = less logic running."** Inlining/OSR and attribution change.
9. **"CPU rise during warm-up must be hot app code."** Compiler threads and class initialization also consume CPU.
10. **"Comparing round 1 of A with the last round of B."** Two non-equivalent states.
11. **"One warm JVM run is statistically enough."** JIT/OS/GC variance requires multiple forks/windows.
12. **"Putting `println` inside the timed loop doesn't matter."** I/O inside a hot loop distorts measurements; the demo prints after each round.
13. **"Seeing no deopt in the file guarantees none occurred."** Verify enabled event types, JFR timestamps, and retention.
14. **"The p99 drop equals C2's exact benefit."** Request latency has many components; correlation requires verifying mechanisms.

## 16. Self-Assessment Exercises

**Question 1.** A method appears at level 3 and level 4 in the compilation log. What does this indicate?

*Hint:* There were compilations in C1 full profiling and C2 for that method/code version; this is evidence of tiered activity. It **does not** tell you the call count or endpoint latency improvement.

**Question 2.** JFR records few `jdk.Compilation` events during startup. Can you conclude most code was not JIT-compiled?

*Hint:* Not yet. Check recording start, `enabled`, `threshold`, tool/JDK, and data retention; in some profiles short compilations are filtered out.

**Question 3.** A loop runs once for a very long time yet `PrintCompilation` shows `%`. What does that symbol relate to?

*Hint:* OSR compilation can occur while the loop is already on the stack; no need to wait for the method to be called many times again.

**Question 4.** Code path A is invoked for the first time after a service has been running for 3 hours. Can we call it "warm" because the process has been up a long time?

*Hint:* No. Process uptime differs from the hotness and profiling history of **that specific code path**.

**Question 5.** Why might flame graphs before and after warm-up not show the exact same method frames?

*Hint:* Inlining and OSR alter how code executes; profilers may display/reconstruct frames differently. Workload mix/threads and sampling behavior may also shift.

**Question 6.** When `-XX:TieredStopAtLevel=1` gives better startup yet worse throughput after 10 minutes than default, which setting is "better"?

*Hint:* Depends on application goals: short jobs, FaaS, or long-running services. Report **both startup, steady-state, memory/CPU**, and request distributions under matching conditions; do not choose from one number alone.

**Hands-on:** run `TieredWarmupDemo` in default mode, with `PrintCompilation`, and with `-Xint` in separate JVMs. Record compile times/levels of `mix`, per-round `ns/op`, and note any GC/CPU noise. Then capture JFR from JVM startup, inspect `jdk.Compilation` and `jdk.Deoptimization`, and write an assessment separating *observed evidence* from *performance hypotheses*. Level 4 is not required to appear on every single run.

## 17. Primary Sources for Reference

- [Oracle JDK 21 — Java HotSpot VM Performance Enhancements: Tiered Compilation](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html).
- [Oracle JDK 21 — `java` launcher: `PrintCompilation`, `LogCompilation`, `TieredCompilation`, and JIT flags](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle JDK 21 — `jcmd`: `Compiler.queue`, `Compiler.codecache`, `Compiler.codelist`, `JFR.check`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `jfr`: `summary`, `print`, `metadata`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [Oracle Java 21 — `jdk.jfr`: event settings, `threshold`, `period`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- [Microsoft OpenJDK engineering — How Tiered Compilation Works in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/).
- [OpenJDK — tiered compilation policy and levels/transitions](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp).
- [OpenJDK — `default.jfc` and compiler-related JFR event settings](https://github.com/openjdk/jdk/blob/master/src/jdk.jfr/share/conf/jfr/default.jfc).

**Guiding principle:** every CPU/latency number is produced within a **specific JVM state and workload window**. Know whether methods are still in interpreter/C1/C2 and whether compilation/deopt occurred in the measurement window before comparing profiles. Warm-up is an **observable and verifiable process**, not a fixed waiting period or an excuse to ignore unfavorable data.
