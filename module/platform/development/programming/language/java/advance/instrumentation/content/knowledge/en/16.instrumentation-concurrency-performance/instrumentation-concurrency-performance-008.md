# Impact on Startup Time, JIT, Inlining, GC, and Latency

> **Key Thesis:** A Java agent can increase **startup time**, prolong **class loading**, alter **JIT and inlining** decisions, generate additional **allocation/GC**, increase **CPU or contention** on the hot path, and ultimately impact **p95/p99 latency**. There is no universal overhead percentage for all agents. To evaluate accurately, you must separate **the cost when the JVM transforms classes** from **the recurring cost each time instrumented bytecode executes**, and then compare them under the same JVM, load, JIT warmup, and exporter configuration.

This lesson belongs to the **Concurrency and Performance** group in Java Advance – instrumentation. The content progresses from JVM mechanisms to measurement methodology, benchmark pitfalls, overhead reduction capabilities, and a Java 17+ experiment using a **real `ClassFileTransformer` startup agent**. The experiment has three cases: no agent, an agent that only observes class loading, and an agent that actually replaces a method's bytecode. Timing metrics are left to vary by machine; only stdout verifying logic and measurement counts are recorded as exact.

## 1. Two Types of Costs to Measure Separately

Overview diagram:

~~~text
                    COLD START
Process start
    |
    v
JVM startup -> load agent JAR -> premain -> application bootstrap
                                  |
                                  +-- config/helper/JAR I/O, classloader
                                  |
                                  +-- register transformer
                                             |
                                             v
                   class definition -> transform -> verify/link
                                             |
                                             v
                                          READY
                                             |
                                             v
                    STEADY STATE
              Hot business method invocation
                 |                   |
                 +-- business bytecode
                 +-- injected hook (timer/context/metric/log)
                 +-- JIT compilation & possible inlining decisions
                 +-- allocation, locks, CPU, exporter queue
                                    |
                                    v
                          response latency
~~~

| Cost Type | Where Does It Occur? | Evidence to Collect |
| --- | --- | --- |
| Agent startup | When the JVM processes `-javaagent`, calls `premain`, and initializes helpers | External process-to-ready time, premain duration, startup CPU |
| Class transform | When the JVM loads/defines/redefines/retransforms a class | Callback count, transformation time, class-loading logs |
| JIT/inlining | When a method reaches appropriate hotness and passes through compilation tiers | Compilation events, inlining decisions, time-to-steady-state |
| Per-invocation | Each method invocation after the hook has been injected | Count, CPU/op, ns/op, throughput, lock contention |
| Allocation/GC | Hook creates spans, strings, buffers, contexts, or retains references | Bytes/op, allocation rate, pauses/safepoints, retained heap |
| Tail latency | Across the entire request/job from ingress to completion | p50/p95/p99, queue time, errors/timeouts, exporter backpressure |

These costs can **interact**: a larger method may change inlining decisions, increasing CPU; higher CPU lengthens queues; higher allocation triggers more GC; a slow exporter causes blocking. However, these are only **possible mechanisms**, not a claim that every JVM produces the same outcome.

Distinguish between two measurements:

- **Time-to-ready:** includes process start, JVM initialization, agent initialization, application boot, and class loading before readiness.
- **Operation latency:** measures the exact boundary of a transaction or method. If measured from ingress, it includes the service's queue at that ingress point; if a timer is placed only inside `checkout()`, it does not include steps before/after the method.

Do not use a timer inside `premain` to represent the entire startup; nor should you use the latency of a single `ClassFileTransformer.transform()` call as the cost for **every method invocation**.

## 2. Impact on JVM Startup Time

### 2.1. Startup Agents Run Before `main`

A typical startup invocation:

~~~bash
java -javaagent:agent.jar=options -jar application.jar
~~~

With an appropriate manifest and JVM, the agent's `premain(String, Instrumentation)` is called before the application's `main`. In practice, startup also involves work not covered by a timer inside `premain`:

- The JVM locates and loads the agent JAR, verifies the manifest, and loads agent classes and dependencies.
- `premain` reads configuration, creates helpers, initializes logger/metrics exporters, and registers transformers.
- The application loads many initial classes; each transformer may inspect or transform the necessary classes.
- The new bytes are checked/verified/linked by the JVM and later warmed up by the JIT; the transformer is not the only step.
- Some libraries are loaded earlier because instrumentation/helpers themselves invoke them.

If an agent establishes exporter connections or performs synchronous DNS lookups in `premain`, timeouts can slow down startup even when **no classes are transformed**. If an agent scans the entire classpath/JARs or parses every class unconditionally, startup latency grows with the number of classes and callback work.

**Strategy:** keep `premain` minimal, set timeouts for external operations, initialize only what is strictly necessary to avoid missing instrumentation points, filter classes before parsing bytecode, avoid disk/network I/O in callbacks, and record bounded startup telemetry. Deferring initialization is not always right: a helper needed before the first class is defined may force early initialization.

### 2.2. First Class Load Is a Notable Synchronous Path

When the JVM is about to define a class, the callback may be invoked:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> beingRedefined, ProtectionDomain domain, byte[] bytes) {
    if (className == null || !className.startsWith("com/acme/orders/")) {
        return null;
    }
    return weaveOnlySelectedMethods(bytes);
}
~~~

**Illustrative code snippet**, not standalone-runnable because `weaveOnlySelectedMethods` belongs to the agent's bytecode library. The idea is to return `null` as early as possible for classes outside the allowlist. Returning `null` means this transformer **does not modify bytes** on that call; it does not mean the callback is free.

A time-consuming callback can sit on the **critical path of class loading**. When multiple threads load different classes, multiple callbacks can run concurrently; a global lock, loading helper classes from inside a transformer, or exporter operations can cause contention/recursion/deadlock. Use thread-safe state, but avoid funneling all calls through the same monitor.

Total callback cost depends on:
- The frequency at which classes are defined (startup and lazy loads).
- The number of transformers and transformation order.
- Bytecode parsing/generation, number of selected methods, and classfile size.
- I/O/resource lookups inside callbacks, caching, and classloader behavior.
- Verify/link/JIT consequences of the final bytes.

**Note on lazy initialization:** A service may report ready before classes for an endpoint or serialization library are actually loaded. When the first request arrives, it bears class loading, transformation, and JIT all at once. Therefore, you may see startup almost unchanged while **first-request p99** degrades.

### 2.3. Do Not Confuse Registration with Instrumented Code

`Instrumentation.addTransformer(transformer)` registers a callback; a `ClassFileTransformer` may return `null`, merely gathering class-loading statistics without modifying method bodies. Conversely, if a transformer returns new classfile bytes and the JVM defines the class successfully, **the injected bytecode continues executing in the loaded class** even if the transformer is later removed.

`removeTransformer` only cancels registration; it **does not automatically revert instrumentation**. Thus, method execution overhead can persist long after no new callbacks occur.

## 3. How Can JIT Compilation and Inlining Change?

### 3.1. Bytecode Shape Matters

The JIT uses runtime profiles, tiered compilation, bytecode size, hotness, type profiles, and many heuristics to make optimization decisions. A small method might initially be inlined into its caller; when a timer/trace hook is injected, the method gains extra calls, branches, an exception handler, and bytecode:

~~~java
// Before instrumentation, illustrative method snippet:
public int calculate(int x) {
    return (x * 31) ^ (x >>> 3);
}
~~~

~~~java
// After instrumentation, illustrative method snippet:
public int calculate(int x) {
    long started = System.nanoTime();
    try {
        return (x * 31) ^ (x >>> 3);
    } finally {
        ProbeRecorder.record(System.nanoTime() - started);
    }
}
~~~

If the new version is longer, at some compilation/call sites the JIT may skip inlining due to size limits, complexity, or profile. When not inlined, the compiler can lose constant propagation or cross-method optimization opportunities. However, there is **no** rule that "adding a hook guarantees no inlining": the compiler can still inline the method/hook when it is hot enough or other conditions are favorable.

An inlining decision is not an immutable truth:

~~~text
tier / call-site A:  failed to inline: callee is too large
tier / call-site B:  inline (hot)
helper call:         inline (hot)
~~~

The lines above describe **the form of diagnostic output**, not fixed stdout for any particular JVM. In this lesson's experiment, `PulseWork::calculate` itself had different inlining states across JIT runs.

### 3.2. JIT Warmup and Throughput

Before becoming hot, code may run through the interpreter/C1 and later be optimized by another compiler such as C2 on HotSpot. Conditions depend on the JVM/JDK/options and are not a fixed process for all VMs. Instrumentation can:
- Change the bytecode count and number of calls the compiler must inspect.
- Alter call-site type/profiles and inlining.
- Generate code for helpers or different compiled variants.
- Increase compilation CPU and code-cache usage.
- Change the time needed for throughput to reach a relatively stable region.

Therefore, measuring the first 100 requests of a warmed-up baseline against the first 100 requests of a freshly started agent is **unfair**. You must compare **cold start separately**, **warmup separately**, and **steady state separately**, under identical input conditions.

### 3.3. Inspecting JIT Logs on HotSpot

Example:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining WindowExperiment
~~~

With the practice section's agent:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining -javaagent:probe-agent.jar=inject WindowExperiment
~~~

`PrintCompilation` shows method compilations, and `PrintInlining` shows per-call-site decisions. `-XX:+UnlockDiagnosticVMOptions` is a prerequisite for `PrintInlining` on the corresponding HotSpot build. These are **diagnostic runs**; the volume of logs/formatted output can be very large, and logging itself introduces overhead, so do not enable it during primary timing benchmarks.

In an OpenJDK 24 verification run, the instrumented `PulseWork::calculate` was logged as **47 bytes** and at times showed `failed to inline: callee is too large`, and later `inline (hot)`; `ProbeRecorder::record` also showed `inline (hot)`. Do not generalize 47 bytes as a universal threshold across all JVMs: heuristics, tiers, and call sites can differ.

**Important distinction:** The JIT may inline the hook itself, yet writing counters, reading clocks, or storing context **does not become zero-cost**. Inlining removes part of the call overhead and opens optimization opportunities, but it does not eliminate the work of recording the measurement.

## 4. Redefinition, Retransformation, and Deoptimization

A startup agent may transform classes only at **initial definition**. However, an agent attached late or needing to toggle rules at runtime can call `retransformClasses`/`redefineClasses` on already-loaded classes. This scenario adds **another kind of cost** beyond startup and per-call hooks.

A sequence that can occur:

~~~text
Method is already JIT-compiled, possibly inlined into callers
    |
    v
retransformClasses(target) / redefineClasses(definition)
    |
    v
JVM runs transformer / verifies / installs new definition
    |
    v
Compiled dependencies may require invalidation/deoptimization
    |
    v
New profiles/compilation, latency may fluctuate
~~~

Several behaviors are **defined by the Java Instrumentation contract**:

- Methods with active stack frames may continue executing bytecode **from the old definition** in those frames.
- New invocations use the new method definition.
- Class initialization does not re-run automatically; static fields retain their current values.
- Existing object instances remain the same objects.
- `removeTransformer` does not automatically roll back already-installed method definitions.

Whether safepoints, deoptimization, or compiled dependency invalidation occur and their exact cost are **implementation/situation-specific details**. Do not claim that every retransform pauses the entire JVM for X ms or always recompiles every method.

If production enables dynamic instrumentation:
1. Record the exact timestamp when invoking the API.
2. Measure the API call duration and error status separately.
3. Monitor p95/p99, JIT logs/safepoints, and warmup after definition changes.
4. Perform changes in small batches or canaries when appropriate, avoiding retransforming thousands of classes simultaneously just to test a hypothesis.
5. Distinguish the **one-time spike** of class processing/JIT from the **steady-state overhead** of the installed hook.

## 5. Allocation, GC, Metaspace, and Lifetime References

### 5.1. Not All Hooks Have the Same Allocation Cost

| Hook or Implementation Pattern | CPU/Allocation Risk | Notes |
| --- | --- | --- |
| `System.nanoTime()` + subtraction | Clock call cost, no object allocation in source | Measures elapsed time, not CPU time |
| `LongAdder.increment()` | Atomic/striped updates and memory traffic | Has overhead; no new object per invocation in source |
| Creating `Span`/context objects | Can allocate objects | Use sampling and a fast path when disabled |
| `String.format`, dynamic log messages | Can allocate strings/buffers/varargs | Check logging guard before formatting |
| Stack trace on every call | Very high cost, large allocation | Appropriate only for exceptional events |
| `ThreadLocal` context | State access, can retain objects long-term on pooled threads | Must `remove()`/restore properly per lifecycle |
| Queue/export telemetry | Allocation, scheduling, backpressure | Avoid synchronous I/O on the request hot path |
| JVM-wide `Class<?>`/`ClassLoader` cache | Retained references, classloader leak risk | Cache must have clear ownership/teardown |

Two concepts are often conflated:

- **Heap pressure:** short-lived spans, strings, trace contexts, exporters.
- **Metaspace/class metadata:** long-lived classes/loaders, dynamic proxies, helper classes; a static cache holding strong references to `Class<?>` from an old loader can prevent class unloading across redeploys.

An agent that increases allocation rate may still have acceptable latency if the collector has sufficient headroom; on another system, increased GC pauses or concurrent GC CPU will worsen p99. **Do not draw conclusions solely from the number of classes transformed.**

### 5.2. Causal Chain to Measure, Not Guess

~~~text
Hook allocates many objects on the hot path
       |
       v
Allocation rate may increase
       |
       +-- Young GC / promotion / concurrent work changes
       +-- Additional CPU and memory bandwidth consumed
       +-- Heap occupancy or retained data may change
       |
       v
Throughput and latency tails may be affected
~~~

Track **allocation bytes/op**, GC count/pauses, live heap/heap occupancy, metaspace/classloader counts, and safepoint time; but also measure **CPU and throughput** to uncover non-GC costs. For instance, atomic contention can lengthen requests without allocating many objects.

If class unloading is needed, do not retain all `Class<?>[]` objects or `Map<ClassLoader, ...>` in the agent's static registry just for reporting. Measure counts/categories and release references; use per-class or lifecycle-aware caches only when truly necessary. `System.gc()` does not guarantee class unloading within a deterministic deadline.

### 5.3. GC Logs and JFR

On HotSpot/OpenJDK, you can use:

~~~bash
java -Xlog:gc*,safepoint=info -javaagent:agent.jar -jar application.jar
~~~

This is a **sample command**; replace the JAR names before running. When evaluating, compare against a baseline using the **same collector/JDK/heap/CPU quota**. Do not attribute every GC variation to the agent; traffic, object lifetimes, and heap sizing also affect it.

Use Java Flight Recorder (JFR) for allocation, CPU, GC, locks/contention, and other runtime events:

~~~bash
java -XX:StartFlightRecording=filename=agent.jfr,settings=profile,dumponexit=true -javaagent:agent.jar -jar application.jar
~~~

For an already-running Java process:

~~~bash
jcmd 12345 JFR.start name=agent-check settings=profile duration=60s filename=agent-check.jfr
~~~

`12345` is an **illustrative PID**. The JDK includes the `jfr` tool, so you can read `jfr summary agent.jfr`, or use JDK Mission Control. The JFR `profile` configuration also has overhead and its coverage depends on event settings: record the settings used, run for a sufficient duration, and if you need to measure **JFR's own overhead**, compare identical runs with JFR enabled vs. disabled.

## 6. Latency: p95/p99, Blocking, and Concurrency

### 6.1. Method-Level Timers Measure Intervals, Not CPU

`System.nanoTime()` is suitable for obtaining **relative elapsed time** between two points in the same JVM:

~~~java
long started = System.nanoTime();
try {
    businessOperation();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    // Record elapsed; do not treat this as pure CPU time.
}
~~~

This is an illustrative snippet, not standalone because `businessOperation` is omitted. If the method blocks on a lock, sleeps, performs I/O, loses scheduler time, or experiences a GC pause, the elapsed timer still includes that **wall-clock interval**. If you need on-CPU vs. off-CPU time, use an appropriate profiler/JFR rather than treating `nanoTime` as a CPU clock.

### 6.2. A Small Cost Can Be Amplified

If a hook adds an average cost `c` to a hot method called `N` times per request, a first-order model is:

~~~text
extra_work_per_request  ~  N * c
~~~

This is a **simplified model**, not an exact wall-latency equation. Actual cost also depends on JIT optimization, concurrency, queueing, GC, locks, and exporters. Do not assume a fixed `c = 20 ns` without measuring on the target JVM.

For example, adding a shared lock or a synchronous exporter creates a queue. At low concurrency, mean latency may barely change; under high load, requests contend for the lock/queue → p99 spikes sharply. Therefore, **measure both throughput and p50/p95/p99** under the same client concurrency, rate, payload, and dependency state.

### 6.3. Do Not Double-Count Nested Intervals

If a checkout span contains a payment span, do not add the durations of checkout and payment directly to derive end-to-end time: payment is already inside checkout. Similarly, with `CompletableFuture`, a timer around the call that creates the future measures only scheduling, **not** until the future completes. Measuring with the wrong boundary can produce "numbers" that fail to answer operational questions.

**Instrumentation point design:** place hooks at meaningful business/dependency boundaries; do not instrument every getter/helper/iterator just because you can. If you need CPU hotspots inside pure computation logic, use profiling/sampling first before deciding whether deep hook injection is worthwhile.

## 7. Java 17+ Experiment: Three Modes (Baseline / Observe / Inject)

This example uses a real startup agent. To avoid requiring ASM/Byte Buddy, it compiles two `PulseWork.class` files with **the same binary name and structure** into two different directories. The transformer returns the timer-instrumented classfile only when the mode is `inject`. This is a way to build a fixture to understand the mechanism, **not** a safe method for replacing arbitrary classfiles in production systems with multiple loaders/modules.

### 7.1. Original File `PulseWork.java`

~~~java
public final class PulseWork {
    public int calculate(int x) {
        int a = (x * 31) ^ (x >>> 3);
        return a + (x & 7);
    }
}
~~~

This is a tiny computational hot method that easily highlights the relative overhead of a timer/hook. It has no I/O and no network calls, and is not representative of an entire payment/HTTP service.

### 7.2. Recorder `ProbeRecorder.java`

~~~java
import java.util.concurrent.atomic.LongAdder;

public final class ProbeRecorder {
    private static final LongAdder CALLS = new LongAdder();
    private static final LongAdder TOTAL_NANOS = new LongAdder();

    private ProbeRecorder() {}

    public static void record(long elapsedNanos) {
        CALLS.increment();
        TOTAL_NANOS.add(elapsedNanos);
    }

    public static long calls() { return CALLS.sum(); }
    public static long totalNanos() { return TOTAL_NANOS.sum(); }
}
~~~

`LongAdder` stores the total observation count and total `elapsedNanos`. `sum()` is not an atomic snapshot across concurrent updates, but the demo only reads it after all loops have finished in a single thread. **Total time/count cannot compute p95/p99**; if you need percentiles in production, use histograms with appropriate buckets and labels.

### 7.3. Variant File `variant/PulseWork.java`

~~~java
public final class PulseWork {
    public int calculate(int x) {
        long started = System.nanoTime();
        try {
            int a = (x * 31) ^ (x >>> 3);
            return a + (x & 7);
        } finally {
            ProbeRecorder.record(System.nanoTime() - started);
        }
    }
}
~~~

This is the **method-body-replacement version**. The agent returns the variant bytes at **initial class definition**, without needing redefine/retransform permissions. `finally` ensures one observation per invocation even if an exception occurs; the demo method does not intentionally throw exceptions. The recorded time per invocation **does not include all external overhead** of the agent (class loading, JIT compilation, queueing outside the method).

### 7.4. `ScopedTransformer.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ScopedTransformer implements ClassFileTransformer {
    private final byte[] replacement;

    public ScopedTransformer(byte[] replacement) {
        this.replacement = replacement == null ? null : replacement.clone();
    }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> beingRedefined, ProtectionDomain domain, byte[] original) {
        if (!"PulseWork".equals(className)) return null;
        System.out.println("transform=PulseWork");
        return replacement == null ? null : replacement.clone();
    }
}
~~~

Only the target `PulseWork` is transformed. If `replacement == null` (`observe` mode), the callback returns `null` and the original method body is preserved. In `inject` mode, the transformer returns the variant classfile. Do not call `System.out.println` for every class in production; printing once in the demo is only to verify that the callback ran.

`className` in the callback is the **JVM internal name**; for a class in package `com.acme`, the name is typically `com/acme/PulseWork`. In production, you must check the classloader/module/descriptor and patch the incoming class bytes rather than returning a precompiled file for every loader with the same name.

### 7.5. Startup `ProbeAgent.java`

~~~java
import java.io.IOException;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ProbeAgent {
    public static void premain(String args, Instrumentation inst) throws IOException {
        String mode = args == null ? "observe" : args;
        if (!"observe".equals(mode) && !"inject".equals(mode)) {
            throw new IllegalArgumentException("Expected observe or inject");
        }
        byte[] replacement = "inject".equals(mode)
            ? Files.readAllBytes(Path.of("variant/PulseWork.class"))
            : null;
        inst.addTransformer(new ScopedTransformer(replacement));
        System.out.println("agent-mode=" + mode);
    }
}
~~~

The agent reads the bytes before registering the transformer. This keeps the callback from touching disk; however, **reading the file in `premain` is still startup cost in `inject` mode**. The manifest must point to the correct `Premain-Class`. `addTransformer` does not enable `canRetransform=true`, because the demo only handles initial class definition.

### 7.6. Workload `WindowExperiment.java`

~~~java
public final class WindowExperiment {
    private static final int WARMUP = 80_000;
    private static final int MEASURE = 120_000;

    public static void main(String[] args) {
        PulseWork work = new PulseWork();
        long checksum = 0;

        for (int i = 0; i < WARMUP; i++) checksum += work.calculate(i);
        long started = System.nanoTime();
        for (int i = 0; i < MEASURE; i++) checksum += work.calculate(i);
        long elapsed = System.nanoTime() - started;

        System.out.println("warmup_ops=" + WARMUP);
        System.out.println("measure_ops=" + MEASURE);
        System.out.println("checksum=" + checksum);
        System.out.println("window_positive=" + (elapsed > 0));
        System.out.println("probe_calls=" + ProbeRecorder.calls());
        System.out.println("probe_time_positive=" + (ProbeRecorder.totalNanos() > 0));

        if (Boolean.getBoolean("showTimes")) {
            System.out.println("window_ns=" + elapsed);
            System.out.println("window_ns_per_op=" + ((double) elapsed / MEASURE));
        }
    }
}
~~~

Result explanation:

- There are **80,000 warmup** and **120,000 measured calls**; the hook in `inject` mode records **200,000** observations because it is placed directly inside the method, not only in the measured loop.
- `checksum` verifies the business output and limits certain forms of dead-code elimination; it **does not** eliminate all compiler benchmark bias.
- `window_positive` avoids treating irreproducible timing numbers as "standard stdout".
- `showTimes=true` provides actual numbers, but a single run with an outer loop timer is **not enough** to measure statistically meaningful overhead.
- `ProbeRecorder` records the sum of method nanos per invocation boundary; that total **differs** from the timing of the whole measured loop.

### 7.7. Manifest `agent.mf` and Directory Structure

~~~text
Manifest-Version: 1.0
Premain-Class: ProbeAgent
~~~

The manifest must end with a trailing newline. Structure:

~~~text
demo/
  PulseWork.java
  ProbeRecorder.java
  ScopedTransformer.java
  ProbeAgent.java
  WindowExperiment.java
  agent.mf
  variant/
    PulseWork.java
~~~

The two versions of `PulseWork.java` must **not** be compiled into the same output directory. The original is on the application classpath `.`; the instrumented version in `variant/` is only read by the agent as raw data bytes.

### 7.8. Compiling and Running

~~~bash
javac --release 17 PulseWork.java ProbeRecorder.java ScopedTransformer.java ProbeAgent.java WindowExperiment.java

javac --release 17 -classpath . -d variant variant/PulseWork.java

jar --create --file probe-agent.jar --manifest agent.mf ProbeAgent.class ScopedTransformer.class

java WindowExperiment

java -javaagent:probe-agent.jar=observe WindowExperiment

java -javaagent:probe-agent.jar=inject WindowExperiment
~~~

Use JDK 17+ and run from the `demo` directory containing these files. These commands were actually tested with `javac --release 17` on OpenJDK 24.

### 7.9. Actual Stdout

**Baseline (no agent):**

~~~text
warmup_ops=80000
measure_ops=120000
checksum=322399513344
window_positive=true
probe_calls=0
probe_time_positive=false
~~~

**Observe-only:**

~~~text
agent-mode=observe
transform=PulseWork
warmup_ops=80000
measure_ops=120000
checksum=322399513344
window_positive=true
probe_calls=0
probe_time_positive=false
~~~

**Inject:**

~~~text
agent-mode=inject
transform=PulseWork
warmup_ops=80000
measure_ops=120000
checksum=322399513344
window_positive=true
probe_calls=200000
probe_time_positive=true
~~~

These lines are **logic verification output**, not a performance report. The business result `checksum` is identical across all three modes, while the number of timer observations changes as designed.

| Comparison | Question You Can Investigate | Avoid Over-Inferring |
| --- | --- | --- |
| Baseline vs Observe | Agent startup cost, transformer registration, and callbacks without byte changes | Do not infer "observe mode overhead is always 0" |
| Observe vs Inject | Cost of added bytecode hooks and JIT/GC changes | A single run does not prove production overhead percentage |
| First request vs steady state | Lazy class loading / JIT warmup cost | Do not use the first request to represent steady state |
| Inject enabled vs disabled-fast-path | Overhead of the disabled check branch and real telemetry | A disabled hook still leaves bytecode and incurs check cost |

## 8. Measuring Timing, Reading JIT, and Checking GC on the Demo

### 8.1. Displaying Timing Numbers If Needed

~~~bash
java -DshowTimes=true WindowExperiment

java -DshowTimes=true -javaagent:probe-agent.jar=observe WindowExperiment

java -DshowTimes=true -javaagent:probe-agent.jar=inject WindowExperiment
~~~

This additionally prints `window_ns=...` and `window_ns_per_op=...`; `...` represents **actual varying numbers**, not fixed stdout. With a tiny method and a single JVM fork, results are affected by JIT tiers, CPU frequency, clock resolution, scheduling, GC, heap, and workload optimizations.

**Do not use this output to conclude "inject is 30% slower" based on one pair of numbers.** For a more reliable microbenchmark, use JMH with multiple forks, warmup/measurement iterations, proper state/blackholes, and compare on a controlled workload. Nor does JMH **replace** an end-to-end p99 load test.

### 8.2. Inspecting Bytecode/JIT

~~~bash
javap -c -p -classpath . PulseWork

javap -c -p -classpath variant PulseWork

java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining -javaagent:probe-agent.jar=inject WindowExperiment
~~~

The two `javap` commands show the difference in the method body: the variant has `System.nanoTime()`, `ProbeRecorder.record()`, and the `finally`/exception handler path. The diagnostic command may print `inline (hot)`, `callee is too large`, or compiled code `made not entrant`; do not assume identical output or ordering across different JDKs.

In this lesson's test run, the instrumented `PulseWork::calculate` was **47 bytes** and the same method name appeared in the inlining log with different decisions at different call sites/tiers. That shows **hotness and compiler decisions**, not a simple "agent present" state.

### 8.3. Measuring Full Process Time for Startup, Not Method Latency

On PowerShell:

~~~powershell
Measure-Command { java WindowExperiment | Out-Null }

Measure-Command { java -javaagent:probe-agent.jar=observe WindowExperiment | Out-Null }

Measure-Command { java -javaagent:probe-agent.jar=inject WindowExperiment | Out-Null }
~~~

These commands measure **total process wall time**, including JVM startup, agent, workload, output, and shutdown; they do not measure "`premain` only". To evaluate a server application, replace this with the **process start → readiness/first successful request** milestone measured by an external monitoring system. Run multiple trials with interleaved order to reduce filesystem cache and CPU warmup bias.

### 8.4. GC/JFR Diagnostics

~~~bash
java -Xlog:gc*,safepoint=info -javaagent:probe-agent.jar=inject WindowExperiment

java -XX:StartFlightRecording=filename=inject.jfr,settings=profile,dumponexit=true -javaagent:probe-agent.jar=inject WindowExperiment
~~~

JFR/GC logs are only useful when the workload is large enough or produces relevant events. The demo runs very fast and does not intentionally allocate many objects, so **do not expect** clear GC event differences or enough profiling samples to analyze p99. Use the same configuration as the baseline and run a realistic workload for a sufficient duration, rather than assuming "no GC seen" means "the agent adds no overhead".

## 9. Benchmarking Methodology for Reliable Conclusions

Ask three **separate** questions and choose the corresponding tools:

### 9.1. Cold Start and First-Request

- Use a **fresh JVM process for each trial**, rather than re-running `main` in the same JVM.
- Keep the same JDK vendor/version, args, CPU/memory limits, GC, heap, classpath, disk/container image, and dependencies.
- Measure **time-to-ready** from outside the JVM plus first-successful-request; use a real readiness probe.
- Run multiple trials, interleaving baseline/observe/inject, while tracking warm filesystem/JIT caches and host noise.
- Separate agent `premain`, app initialization, and first-request lazy class loading when appropriate traces are available.

### 9.2. Steady-State

- Warm up long enough; 80,000 loops do not necessarily reach steady state.
- Drive production-like traffic: request mix, payloads, retries, concurrent clients, and dependency latencies.
- Measure throughput, errors/timeouts, p50/p95/p99/p99.9, CPU, allocation rate, GC, JIT compilation, queue depth, and dropped telemetry.
- Ensure **business output and error behavior are identical** across configurations; instrumentation must not swallow exceptions.
- Each configuration must have multiple forks/trials and result distributions, not just a single mean or single-shot ns/op.

### 9.3. Dynamic Retransformation

If the agent modifies already-loaded classes at runtime, mark the exact **time when `retransformClasses`/`redefineClasses` is invoked** and measure:

- The API call's own duration and errors.
- p99 latency during the class-change window.
- JIT compiled code invalidation/compilation and safepoints if the VM provides events.
- Post-change warmup and behavior when methods have active stack frames.
- Steady-state overhead after all target classes are instrumented.

This is a separate test and cannot be extrapolated from a demo that only uses a startup initial-load transformer.

### 9.4. Important Controls

| Variable | Must Be Held Constant or Explicitly Recorded |
| --- | --- |
| JVM/GC | Version, vendor, collector, tiered flags, heap, code cache |
| Hardware | CPU quota, core count, virtualization, frequency governor, host noise |
| Application | Binary/JARs, loaded class count, config, startup path |
| Workload | Input/traffic mix, concurrency, cache hit rate, network/dependency state |
| Agent | Class/method allowlist, sampling, exporter settings, helper version |
| Trials | Fork count, warmup time, measurement length, run order |
| Diagnostics | JFR/GC/JIT logging on/off, since they have their own overhead |
| Reporting | p50/p95/p99, confidence/variability, correctness, and failure rate |

**One flawed measurement:** running the baseline warm for 10 minutes, running `inject` for 15 seconds, and taking the throughput difference as the agent's overhead. Different JIT states make the conclusion unreliable.

**Another flawed measurement:** writing "the in-method timer measures 40 ns, so the agent overhead is only 40 ns." An in-method timer does not fully measure the added timer/record call cost, JIT effects, GC, CPU contention, and external queueing.

## 10. Optimizing in the Right Place Based on Symptoms

| Symptom | What to Inspect First | How to Reduce Cost |
| --- | --- | --- |
| Increased time-to-ready | `premain`, helper/library loading, transformer callbacks | Controlled lazy init, early filtering, avoid blocking I/O/network |
| Slow first request | Lazy class loading, verification, JIT warmup | Proper warmup, lifecycle-aware caching, narrow instrumentation scope |
| Higher steady-state CPU | Hot hook frequency, counter contention, inlining | Reduce instrumentation points, disabled fast path, simpler helpers |
| Degraded p99 with similar mean | Locks, queue/exporter, GC, safepoints | Bounded queue, async export, sampling, GC/lock profiling |
| Increased allocation rate | Spans/contexts/strings/boxing/stack traces | Avoid unnecessary object creation and dynamic log formatting |
| Growing metaspace across redeploys | `ClassLoader`/`Class<?>` retention, helper caches | Clean up registrations/listeners/`ThreadLocal`, leak analysis |
| JIT stops inlining a method as before | Bytecode bloat or altered profile | `javap` + `PrintInlining`, try shrinking the hook |
| Spike during retransform | JVM installing new classes + compiled code effects | Canaries, small batches, avoid bulk operations at peak load |
| Hooks still visible after disabling agent | Previously instrumented bytecode remains in classes | Disabled guard, explicit rollback/redeploy, not just removing the transformer |

**Avoid I/O on the hot path** whenever possible: an event exporter may return quickly on average yet block for a long time when queues fill up or networks fail. Even with an asynchronous exporter, you must enforce memory bounds and a backpressure/drop policy; otherwise, you turn a latency problem into memory pressure.

**Do not add high-cardinality metric labels** (`userId`, `orderId`, raw URL, request ID) per invocation just for debugging. This can create millions of metric series and backend backpressure, even if the hook code is very short.

**Do not optimize bytecode before knowing what question you need to answer:** One meaningful metric at `CheckoutService.checkout()` is usually cheaper and more useful than creating spans on every getter. If you need to find unknown CPU hotspots, JFR/sampling profilers are a better fit than bulk-injecting timers.

## 11. Common Misconceptions About Agent Impact

1. **"Transformers only run at load time, so steady state is unaffected."** False when the transformer injects hooks into method bodies: hooks execute on every call.
2. **"Returning `null` from a transformer means agent overhead is 0."** False: agent initialization and callbacks/filtering still have costs.
3. **"Adding method calls guarantees the JIT will not inline."** False: the JIT may still inline at other call sites/tiers; you must read logs and measure.
4. **"Removing a transformer removes all bytecode hooks."** False: removal only cancels registration; it does not revert already-installed definitions.
5. **"A high transformed class count guarantees GC will increase."** False: GC increases typically relate to allocation/live set, not just callback count.
6. **"A `nanoTime` timer measures a method's CPU time."** False: it measures elapsed time including blocking, scheduling, and pauses.
7. **"Unchanged mean latency proves there is no impact."** False: p99, timeouts, and queueing may degrade.
8. **"Add child trace durations to the parent duration to get the request total."** False: nested intervals are double-counted.
9. **"A single run of 120,000 loops is a stable JIT benchmark."** False: you need warmup, trials/forks, and controls for compiler optimizations.
10. **"JFR/PrintInlining have zero overhead."** False: diagnostics have their own overhead and can skew timing.
11. **"A disabled agent is free."** If bytecode still contains a disabled branch, that branch still has a cost; measure it.
12. **"Latency after retransform must immediately reflect the new version on all active frames."** False: active frames can continue running old code.
13. **"`LongAdder` always gives a consistent snapshot while other threads write."** False: `sum()` under concurrent updates is not necessarily atomic.
14. **"Seeing one long GC pause is enough to conclude the agent caused a bug."** False: you need root-cause analysis, workload context, logs, and controls.
15. **"Use a single universal overhead percentage for all Java agents."** False: cost depends on hook type, frequency, JVM, workload, and sampling/export settings.

## 12. Self-Check and Pre-Rollout Checklist

**Question 1.** An agent only registers a transformer whose callback returns `null`. Can it slow down startup without adding per-call bytecode to a class?

**Answer:** Yes. Agent startup, class loading, and callbacks/filtering have costs; class bytes remain unchanged if that transformer returns `null`.

**Question 2.** The JIT log first reports `callee is too large`, and later reports `inline (hot)`. Is this a contradiction?

**Answer:** No. Inlining depends on call site, tier, hotness, and profile. You must analyze the timing and code version.

**Question 3.** In the demo, `MEASURE=120000` yet `probe_calls=200000`. Is the count wrong?

**Answer:** No. The bytecode hook runs for both the **80,000 warmup** and **120,000 measured** calls.

**Question 4.** Can `TOTAL_NANOS / calls` compute p99?

**Answer:** No. That is an average per boundary and contains no distribution. You need a histogram or the set of observations.

**Question 5.** After `removeTransformer`, the agent still slows down the method. Is this an API violation?

**Answer:** No. Already-injected bytecode continues running; removal does not automatically revert class definitions.

**Question 6.** When GC barely changes but CPU/op increases, could instrumentation be the cause?

**Answer:** Possibly: clock reads, contention, context lookups, lost inlining, or compiled code growth can increase CPU without noticeably increasing allocation. Profile CPU/JIT.

**Question 7.** Can the demo's `checksum` stdout be used to claim an exact overhead percentage?

**Answer:** No. Checksum proves logic is unchanged; measuring performance requires multiple runs, JIT warmup, controlled conditions, and distributions.

**Checklist:**

- [ ] Measured process-to-ready, first request, steady state, and (if applicable) dynamic retransform separately?
- [ ] Included a no-agent baseline and an observe-only configuration to separate class loading from hooks?
- [ ] Verified identical business results, exceptions, and timeout behavior across configurations?
- [ ] Confirmed the transformer only instruments target classes/methods, filters early, and performs no blocking I/O in callbacks?
- [ ] Compared method bytecode with `javap` and checked JIT/inlining diagnostics if code growth is suspected?
- [ ] Measured CPU, allocation, GC/safepoints, throughput, and p95/p99 instead of just the mean?
- [ ] Used sufficient warmup, multiple JVM forks, randomized/interleaved order, and identical JDK/heap/GC/load?
- [ ] Configured bounded exporter queues, a sampling policy, a disabled fast path, and rollback capability?
- [ ] Verified that agents/helpers/caches do not retain old `Class<?>` or classloader references long-term?
- [ ] Prepared a canary/monitoring plan and a threshold to disable hooks if overhead becomes unacceptable?

**Conclusion:** Java instrumentation overhead is a **multi-layered phenomenon**. Class transformers add work on the startup/class-loading path; new bytecode can alter JIT/inlining and add per-invocation cost; allocation, GC, locking, and exporters can amplify tail latency. Draw conclusions only after **measuring the right boundaries with a baseline, identical workload/JVM, and JIT/GC/latency evidence**, rather than using a single benchmark number as a blanket guarantee.

### References

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer`, `retransformClasses`, `redefineClasses`, and active stack frames.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transform callback, output bytes, and transformation chaining rules.
- [Java SE 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-javaagent`, `PrintCompilation`, `PrintInlining`, code cache, and runtime flags.
- [Java SE 17 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): JDK Flight Recorder, `profile`/`default` settings, and `jcmd`.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): Java Microbenchmark Harness and benchmarks with forks/warmup/measurement.
