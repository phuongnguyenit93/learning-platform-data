# Measuring Overhead by Running With-Agent and No-Agent Groups Under Identical Conditions

**Technical question:** After attaching a Java instrumentation agent to the JVM with `-javaagent`, how much performance does the application lose? A figure like “the agent is 7% slower” is only meaningful if we know **7% of which metric**, which workload, which JVM version, what concurrency level, which probes the agent has enabled, and whether the result exceeds measurement noise.

The core method is a **controlled A/B experiment**:

- **A – No agent:** the same application, with the JVM started **without `-javaagent`**.
- **B – With agent:** the exact same application, with the same configuration, **with `-javaagent` and instrumentation actually active**.
- **Keep all other variables equivalent:** JDK, JVM flags, code artifacts, data, machine resources, request mix, concurrency, warm-up, measurement window, backend.
- **Run multiple independent JVMs**, alternating or randomizing the A/B order, recording metrics in pairs, and evaluating variance as well.
- **Verify correctness:** both groups must complete the same kind of work with the same quality, errors, and results/checksums; a branch that skips work cannot be called “faster”.

This lesson progresses from experiment design, defining **startup/steady-state/throughput/latency/memory/GC overhead**, and comparison formulas to a **runnable Java 17+ benchmark**: the agent uses `ClassFileTransformer` to change a call site from a no-op to a `LongAdder` probe, while the app JAR **remains 100% identical between the two groups**. At the end of the lesson are a multi-process execution procedure, how to analyze the data, and common pitfalls when measuring Java instrumentation.

## 1. Overhead Is Not a Single Number

An agent can affect multiple components:

| Metric | What does it measure? | Common units |
|---|---|---|
| Startup duration | From JVM start until ready to serve | ms, s |
| Latency / duration | Time to complete one operation/request | ns, µs, ms |
| p50/p95/p99 latency | Latency distribution, especially the slowest requests | ms |
| Throughput | Successful operations/requests per second | ops/s, req/s |
| CPU time | Total CPU time spent to complete a given amount of work | CPU-s / 1,000 req |
| CPU utilization | CPU usage at a specified load | % |
| Allocation rate | Rate of creating objects/telemetry data | bytes/op, MiB/s |
| GC impact | GC frequency, pause time, impact on latency | count, ms |
| Heap / metaspace / RSS | Different memory usage layers | MiB |
| Class-loading / transformer time | Cost of loading/parsing/transforming/verifying classes | ms, class count |
| Exporter impact | Buffering, logging, network, retries, and dropped events | events/s, bytes/s, % |

A complete conclusion might read: **“At the same offered load of 500 req/s, B increases p95 latency by 4% and CPU/1,000 req by 7%; startup is 250 ms slower, and the error rate is unchanged.”** This is a **report formatting example**, not a measurement result from this lesson.

You must ask **before measuring**: do you need to evaluate per-method hot-path overhead, service latency under load, startup cost, or capacity at saturation? Different tests can yield different results without contradicting each other.

## 2. Both Groups Must Truly Be “Identical Except for the Agent”

Here is a preflight checklist for a fair test:

| Factor | A/B Rule |
|---|---|
| Application build | **Same app JAR, class files, and Git commit** |
| JVM | Same Java vendor, Java version, architecture, JIT, and GC implementation |
| Heap / GC flags | Same `-Xms`, `-Xmx`, GC collector, module flags, tuning flags |
| CPU/memory limits | Same machine type, vCPU count, cgroup quota, RAM |
| Payload and data | Same seed, data snapshot, request mix, DB state |
| Throughput driver | Same arrival rate, connections, worker threads, think time |
| Agent | Only B adds **the exact agent JAR**, with the same sampling/exporter/filter config |
| Warm-up | Same warm-up policy and stability criteria |
| Measurement | Same duration, timestamp source, measurement tools, and units |
| Network/backend | Same topology, cache policy, and dependency versions |
| Background noise | Monitor background processes, CPU throttling, temperature, scaling |
| Correctness | Same checksum, success count, error/timeout policy |

The condition that must change intentionally is **whether the agent is present or not**. The mere “presence of the agent” can load additional classes/JARs, create threads, and alter JIT compilation; all of these are part of the effect to be measured. You must not mask the real effect by arbitrarily disabling individual components and then claiming that as full-agent overhead.

**Common mistake:** running A on JDK 17 with a 512 MiB heap but B on JDK 24 with a 2 GiB heap. The difference could be due to GC/JIT and memory pressure, and cannot be attributed to the agent.

When it is impossible to keep the infrastructure strictly identical, you must record the differing conditions and use **matching, randomization, or host swapping**, rather than assuming the confounding factors are controlled.

## 3. A True Baseline Must Not Load the Agent

Three states need to be distinguished:

~~~text
A. no-agent
    JVM without -javaagent, Agent JAR is not loaded.

B0. agent-loaded with probes disabled
    JVM still loads the agent, runs premain, may have helper/exporter threads.

B1. agent-loaded, probes enabled
    JVM runs premain, transforms classes, hot path is instrumented.
~~~

**B0 is not A**. Switching `agent.enabled=false` at runtime can only evaluate the cost of toggling probes on/off; it **does not** eliminate the overhead of agent startup, classloaders, background tasks, or transformations that have already occurred.

To answer the question in the prompt, the primary measurement must be **A versus B1 under the exact agent configuration that will be used in production**. B0 is a supplementary diagnostic group used to break down costs.

An experiment on the same JVM that “turns the agent off at 10:00, turns it on at 10:05” is also affected by prior JIT/GC state, already-transformed classes, and SDK threads. **Use a fresh JVM process for each run**.

## 4. Separating Startup Overhead from Steady-State Overhead

`Premain-Class` in the manifest is invoked by the JVM **before the application's `main`** when using `-javaagent`.

At startup, an agent may:

- Load the agent JAR and its dependencies.
- Register a `ClassFileTransformer` and parse/generate class files.
- Load helper classes and spawn exporter/scheduler threads.
- Alter class loading, verification, JIT warm-up, and metaspace.
- Require module reads/opens, bootstrap helper paths, or retransform support.

A **startup benchmark** must start its timer **outside the JVM process** (in the launcher/process orchestrator), then wait for a **readiness signal**. Starting `System.nanoTime` at the beginning of `main` **does not include `premain`**, and therefore does not measure full startup overhead.

A **steady-state benchmark** warms up and waits for the workload to stabilize before measuring:

~~~text
A: process launch → class loading → warm-up → [measurement] → stop
B: process launch → premain + transform → warm-up → [measurement] → stop
                    ^ separate startup              ^ steady-state
~~~

There can be distinct **cold-start**, **warm-start**, **first-request**, and **steady-state** metrics. Do not mix them into a single ms/op value if the goal is to compare hot-path cost.

## 5. Overhead Formulas with the Right Denominator

For **latency/time per operation**:

~~~text
A = mean or median time/op of the no-agent group
B = same definition in the with-agent group

delta = B - A
time_overhead_% = 100 × (B / A - 1)
~~~

For **throughput**:

~~~text
Q_A = operations/second without agent
Q_B = operations/second with agent

throughput_loss_% = 100 × (1 - Q_B / Q_A)
~~~

Require that A and Q_A are positive; metrics must share the same units and measure the same workload.

**Hypothetical arithmetic example**:

~~~text
Q_A = 20,000 ops/s
Q_B = 18,000 ops/s

Throughput loss = 100 × (1 - 18,000 / 20,000) = 10%

Average time per op:
A ≈ 50 µs/op
B ≈ 55.56 µs/op

Time/op increase ≈ 100 × (20,000/18,000 - 1) = 11.11%
~~~

**A 10% throughput loss does not equal a 10% increase in time/op**, because the denominators differ. If measuring **p95 latency**, do not take the reciprocal of p95 to compute throughput; in services with queueing/concurrency, those quantities do not have a simple reciprocal relationship.

### Do Not Round Before Computing

Keep `elapsedNanos` and `operations` at full precision, then compute:

~~~text
ns_per_op = elapsedNanos / operations
ops_per_second = operations × 1_000_000_000 / elapsedNanos
~~~

If `elapsedNanos <= 0` (due to an overly short measurement window or bad data), **discard that sample according to a pre-defined error rule** and lengthen the workload. Do not turn it into `Infinity ops/s`.

## 6. Warm-Up: Don't Mistake JIT Learning Time for the Conclusion

Java/JVM characteristics that make short benchmarks very error-prone:

- Initially code may run interpreted/C1, after which C2 JIT, inlining, and optimizations change.
- Enabling an agent can add `invokestatic` calls, allocate objects, and affect escape analysis or inlining.
- The transformer may be invoked during class loading, causing class initialization and verification to appear in the first measurement.
- GC depends on allocation history and heap occupancy.
- CPU frequency scaling, thermal throttling, and OS scheduling cause fluctuations.
- If the computed result is recognized by the compiler as unused, the JIT may eliminate most of the workload.

Therefore:

1. **Warm up with the actual workload**, not with a loop that behaves differently.
2. Keep the warm-up policy consistent between A and B; if B takes longer to stabilize, note it separately.
3. Use **sufficiently long measurement windows**; do not measure a single call and report ns/op.
4. Spawn **multiple independent JVM forks**, not just 100 iterations in a single process.
5. Ensure there is an observable result/Blackhole to prevent dead-code elimination.
6. Do not filter out a sample “because GC happened” if GC itself is an effect caused by the agent.
7. Use **JMH** for microbenchmarks requiring nanosecond-level reliability; a hand-written loop is only for illustration.

## 7. Each A/B Run Must Be a Separate JVM

A flawed sequence:

~~~text
A A A A A A
B B B B B B
~~~

If a laptop heats up, the CPU gets throttled, or backend load increases over time, B may be penalized simply for running later.

A better sequence:

~~~text
Pair 1: A → B
Pair 2: B → A
Pair 3: A → B
Pair 4: B → A
...
~~~

Or alternate ABBA / BAAB, or randomize the order with a fixed seed for reproducibility. Each **pair** consists of two **fresh JVM processes**. If two equivalent hosts are available, A and B can be run in parallel **on two resource-isolated hosts**, then the arms swapped between hosts; you should not place two JVMs competing for the same small CPU quota and attribute the difference to the agent.

**The primary independent statistical unit is the fork/pair**, not each operation within the same fork. If one JVM calls `compute` 5,000,000 times, those are not 5,000,000 independent observations of “agent impact” because they share the same JIT, heap, OS, and thread scheduling.

## 8. Runnable Java 17+ Example: An Agent That Actually Changes the Hot Path

The experiment uses an **unchanged app JAR** between both groups. Class `lab.Work` always calls `Hook.empty()` in source code. In group B, the agent's `ClassFileTransformer` modifies a single constant-pool method name entry from **`empty` → `count`** (both ASCII names are 5 bytes), causing the JVM to actually invoke `Hook.count()` and increment a `LongAdder`.

It measures the cost of **a probe enabled via bytecode transformation**, while proving that the computation result remains equivalent. This is a **pre-existing insertion point**, unlike a production agent that can inject entire method instructions. This lesson does not treat this simple parser as a production bytecode tool.

Structure:

~~~text
overhead-lab/
├── src/
│   ├── app/lab/
│   │   ├── Hook.java
│   │   ├── Work.java
│   │   └── BenchMain.java
│   └── agent/agent/
│       ├── CpPatch.java
│       └── ProbeAgent.java
├── AGENT.MF
└── out/
    ├── app/
    └── agent/
~~~

### 8.1. `src/app/lab/Hook.java`

~~~java
package lab;

import java.util.concurrent.atomic.LongAdder;

public final class Hook {
    private static final LongAdder EVENTS = new LongAdder();

    private Hook() { }

    public static void empty() { }

    public static void count() {
        EVENTS.increment();
    }

    public static long calls() {
        return EVENTS.sum();
    }
}
~~~

`empty()` has no side effects and is heavily optimized by the JVM/JIT. `count()` creates a side effect on a `LongAdder`. For a **single-threaded** measurement, we read the counter after the workload finishes. In a concurrent application, `LongAdder.sum()` is not an atomic snapshot if threads are still incrementing, so only use the counter for verification after all workers have completed.

### 8.2. `src/app/lab/Work.java`

~~~java
package lab;

public final class Work {
    private Work() { }

    public static long compute(int value) {
        long x = value * 0x9E3779B1L + 17;
        x ^= x >>> 13;
        x *= 0x85EBCA6BL;
        x ^= x >>> 16;
        Hook.empty();
        return x;
    }
}
~~~

All arithmetic returns a result independent of incrementing the counter. Use the checksum to verify that A and B perform the same computation. This is **not** a real-world application with production instrumentation; it is a minimal model for observing overhead.

### 8.3. `src/app/lab/BenchMain.java`

~~~java
package lab;

import java.util.Locale;

public final class BenchMain {
    private static volatile long sink;

    private static long round(int operations, int seed) {
        long sum = 0;
        for (int i = 0; i < operations; i++) {
            sum += Work.compute(i ^ seed);
        }
        sink = sum;
        return sum;
    }

    public static void main(String[] args) {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "Usage: BenchMain <label> <operations> <warmups> <samples>");
        }
        String label = args[0];
        int operations = Integer.parseInt(args[1]);
        int warmups = Integer.parseInt(args[2]);
        int samples = Integer.parseInt(args[3]);
        if (operations <= 0 || warmups < 0 || samples <= 0) {
            throw new IllegalArgumentException("invalid run config");
        }

        for (int w = 0; w < warmups; w++) {
            round(operations, 1000 + w);
        }

        for (int s = 0; s < samples; s++) {
            long start = System.nanoTime();
            long checksum = round(operations, 2000 + s);
            long elapsed = System.nanoTime() - start;
            double throughput = operations * 1_000_000_000.0 / elapsed;
            System.out.printf(Locale.ROOT,
                    "RESULT,%s,%d,%d,%d,%.2f,%d%n",
                    label, s + 1, operations, elapsed, throughput, checksum);
        }
        System.out.println("HOOK_CALLS=" + Hook.calls());
        System.out.println("SINK=" + sink);
    }
}
~~~

**Behavior explanation:**

- `round` executes the exact number of `operations` provided. The sample's `seed` determines the input data and is **identical between A and B for the same sample index**.
- `System.nanoTime()` is a relative elapsed-time source **within the same JVM**; only the difference `end-start` is meaningful.
- `warmups` actually execute but do not print `RESULT`. Warm-up calls are still counted in `HOOK_CALLS`.
- The computation results are accumulated into `checksum` and written to `volatile sink` to reduce the risk of dead-code elimination. This is still not an optimal harness like JMH.
- Printing `RESULT` is **outside the timed section** so per-sample console I/O cost is not included in elapsed time. Do not print on every operation.
- Each `RESULT` line contains: marker, A/B label, sample, operations, `elapsedNs`, `opsPerSec`, checksum. `elapsedNs` and `opsPerSec` are **unstable** across runs.
- With 200,000 ops, 2 warmups, and 2 measured samples, B must record **800,000 probe calls**, while A must record **0**.

### 8.4. `src/agent/agent/CpPatch.java`

~~~java
package agent;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class CpPatch {
    private CpPatch() { }

    public static byte[] replaceUtf8(
            byte[] source, String before, String after) {
        byte[] oldBytes = before.getBytes(StandardCharsets.UTF_8);
        byte[] newBytes = after.getBytes(StandardCharsets.UTF_8);
        if (oldBytes.length != newBytes.length) {
            throw new IllegalArgumentException("length mismatch");
        }

        byte[] result = source.clone();
        ByteBuffer b = ByteBuffer.wrap(result);
        if (b.getInt() != 0xCAFEBABE) {
            throw new IllegalArgumentException("not a class");
        }
        b.getShort();
        b.getShort();
        int count = Short.toUnsignedInt(b.getShort());
        int changed = 0;

        for (int i = 1; i < count; i++) {
            int tag = Byte.toUnsignedInt(b.get());
            switch (tag) {
                case 1 -> {
                    int length = Short.toUnsignedInt(b.getShort());
                    int offset = b.position();
                    if (length == oldBytes.length
                            && Arrays.equals(
                                Arrays.copyOfRange(
                                    result, offset, offset + length),
                                oldBytes)) {
                        System.arraycopy(
                                newBytes, 0, result, offset, length);
                        changed++;
                    }
                    b.position(offset + length);
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 ->
                    b.position(b.position() + 4);
                case 5, 6 -> {
                    b.position(b.position() + 8);
                    i++;
                }
                case 7, 8, 16, 19, 20 ->
                    b.position(b.position() + 2);
                case 15 ->
                    b.position(b.position() + 3);
                default -> throw new IllegalArgumentException(
                        "unexpected constant pool tag " + tag);
            }
        }
        if (changed != 1) {
            throw new IllegalArgumentException(
                    "expected 1 patch, found " + changed);
        }
        return result;
    }
}
~~~

**Explicit limitations:** This is a **very narrow class-file patcher**, usable only with a constant-length ASCII UTF-8 constant-pool entry. It does not handle general modified UTF-8, code length changes, descriptors, or control flow. `clone()` avoids mutating the buffer supplied by the JVM directly.

For real agents, use ASM, Byte Buddy, or the Java Class-File API (standardized in JDK 24) to produce valid bytes and preserve StackMapTable/exception tables. This experiment only needs to rename `Hook.empty` to `Hook.count` with the same `()V` descriptor; the patch count must be exactly **1**.

### 8.5. `src/agent/agent/ProbeAgent.java`

~~~java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ProbeAgent {
    public static void premain(
            String options, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String name,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classfileBuffer) {
                if (!"lab/Work".equals(name)) {
                    return null;
                }
                byte[] patched = CpPatch.replaceUtf8(
                        classfileBuffer, "empty", "count");
                System.err.println("transformedWork=true");
                return patched;
            }
        }, false);
    }
}
~~~

`premain` is invoked **before `main`**, and the transformer is registered for class loading. The name `"lab/Work"` is the **JVM internal class name**. Returning `null` for other classes means leaving them unchanged.

If the agent JAR is loaded but `transformedWork=true` does not appear or `HOOK_CALLS=0` in B, you cannot conclude “probe overhead is 0”; the filter might not match, the class might have been loaded earlier, or the transformation might have failed. The `ClassFileTransformer` contract allows the JVM to continue invoking other transformers even if one throws an exception; you must verify the **final** behavior.

### 8.6. `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: agent.ProbeAgent

~~~

The manifest has a **trailing blank line**. The agent only transforms the class on **initial load**, so `Can-Retransform-Classes` or `Can-Redefine-Classes` manifest attributes are not needed for this demo.

### 8.7. Compiling and Running

From `overhead-lab`, create directories:

~~~bash
mkdir -p out/app out/agent
~~~

Compile with JDK 17+:

~~~bash
javac --release 17 -d out/app \
  src/app/lab/Hook.java \
  src/app/lab/Work.java \
  src/app/lab/BenchMain.java

javac --release 17 -d out/agent \
  src/agent/agent/CpPatch.java \
  src/agent/agent/ProbeAgent.java

jar --create --file app.jar -C out/app .
jar --create --file agent.jar --manifest AGENT.MF -C out/agent .
~~~

Package **all agent output** (`-C out/agent .`) so that the anonymous class `ProbeAgent$1.class` is not omitted.

Run **two separate JVM processes**, without modifying `app.jar`:

~~~bash
# Group A
java -cp app.jar lab.BenchMain A 200000 2 2

# Group B
java -javaagent:agent.jar -cp app.jar lab.BenchMain B 200000 2 2
~~~

**Verified in practice:** The Java sources were compiled with `javac --release 17`, the app JAR/agent JAR were packaged, and both commands ran successfully on Zulu OpenJDK 24.

Here is **one recorded trial**. The `elapsedNs`/`opsPerSec` numbers are observational only, not fixed results:

**A:**

~~~text
RESULT,A,1,200000,773800,258464719.57,-3469022496391967169
RESULT,A,2,200000,110200,1814882032.67,-3469022496391967169
HOOK_CALLS=0
SINK=-3469022496391967169
~~~

**B:**

~~~text
transformedWork=true
RESULT,B,1,200000,1619200,123517786.56,-3469022496391967169
RESULT,B,2,200000,1175100,170198281.00,-3469022496391967169
HOOK_CALLS=800000
SINK=-3469022496391967169
~~~

`transformedWork=true` is printed by the agent to **stderr** during class loading; the other lines are stdout. Use much longer time windows before comparing overhead. The second A sample took only `110200 ns` for 200,000 operations, a sign that JIT/clock/window effects are huge; **do not draw an overhead percentage conclusion from these two lines**.

What is reliable in the demo is:

- A: no agent, `HOOK_CALLS=0`.
- B: agent properly transformed `Work`, `HOOK_CALLS=800000` matching the total of warm-up and measured iterations.
- **Identical checksums** in A and B, so business computation is preserved.
- Measurement time fluctuates; estimating the effect requires longer runs, multiple forks, and proper statistical methods.

## 9. Multi-Run and Alternating-Order Script

Only after the smoke test passes should you run an A/B experiment with multiple independent JVMs. Create `run-ab.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

printf 'pair,marker,mode,sample,operations,elapsedNs,opsPerSec,checksum\n' > ab.csv

for pair in 1 2 3 4 5 6; do
  if (( pair % 2 == 1 )); then
    order=(A B)
  else
    order=(B A)
  fi

  for arm in "${order[@]}"; do
    if [[ "$arm" == A ]]; then
      java -Xms256m -Xmx256m -cp app.jar \
        lab.BenchMain A 5000000 5 4 |
        awk -F, -v p="$pair" '$1=="RESULT" { print p "," $0 }' >> ab.csv
    else
      java -Xms256m -Xmx256m -javaagent:agent.jar -cp app.jar \
        lab.BenchMain B 5000000 5 4 |
        awk -F, -v p="$pair" '$1=="RESULT" { print p "," $0 }' >> ab.csv
    fi
  done
done
~~~

Run on Bash/Git Bash:

~~~bash
bash run-ab.sh
~~~

`set -o pipefail` helps detect Java errors even when stdout is piped through `awk`. The script builds `ab.csv` solely from `RESULT` lines, prepending a `pair` column for pairing. `HOOK_CALLS`/`SINK` outputs are not in the CSV; **you must verify them via the smoke test** before accepting results. Agent messages on stderr should be observed and not mistaken for throughput metrics.

Notes:

- **Each `java` invocation is a separate JVM fork.** Do not run multiple arms in the same process.
- Both A and B use `-Xms256m -Xmx256m`. Any additional flags must be applied **identically** to both commands.
- `5000000` ops, 5 warmups, and 4 measured samples is an **illustrative setup**, not necessarily long enough for a real workload.
- For noisy systems, increase the number of pairs/forks and measurement duration; you can randomize the order and save the seed.
- This is a **Bash script**. On PowerShell, run the two `java` commands with identical configuration and redirect stdout to separate files; do not copy Bash `awk`/array syntax verbatim.
- Do not measure A and B concurrently on the same small CPU quota. Test sequentially or on separate hosts and swap hosts across runs.

### How to Analyze `ab.csv`

Each row has the fields:

~~~text
pair,marker,mode,sample,operations,elapsedNs,opsPerSec,checksum
~~~

For each A/B pair:

1. Verify that `operations`/seed/workload match; checksums must agree.
2. Compute `ns/op = elapsedNs / operations` for each measured sample.
3. Aggregate **per JVM fork**, e.g., median `ns/op` across the 4 measurement windows.
4. Pair the A and B forks **within the same pair**, computing the ratio `median_B / median_A`.
5. Aggregate the ratios across **independent pairs** (median, geometric mean when appropriate), reporting variance and confidence intervals if estimable.
6. Do not treat the 4 samples within each fork as 4 independent forks; they share JIT/GC state.

Do not simply pool all A samples into one bag and all B samples into another bag and run a t-test assuming each operation/window is independent. If using bootstrap confidence intervals, resample at the **pair/fork** level, not at the individual operation level.

## 10. Paired Analysis and Reporting Uncertainty

Let `L_Ai`, `L_Bi` be the median `ns/op` in the two forks of pair `i`:

~~~text
r_i = L_Bi / L_Ai
overhead_i = 100 × (r_i - 1)
~~~

For throughput:

~~~text
q_i = Q_Bi / Q_Ai
throughputLoss_i = 100 × (1 - q_i)
~~~

Compute **ratios per pair** first, then aggregate. This helps reduce the impact of slow time-varying drift between pairs.

**The geometric mean** of positive ratios can be used to summarize multiplicative effects:

~~~text
geomean_ratio = exp(mean(log(r_i)))
aggregate_time_overhead_% = 100 × (geomean_ratio - 1)
~~~

**Do not report excessive significant digits** when run-to-run variation is large. If median overhead is 0.8% but fork-to-fork variation is typically ±3%, the appropriate conclusion is that **there is insufficient evidence to confirm a stable 0.8% overhead**; a better experiment is needed.

Also report:

- Actual number of pairs/forks, measurement windows, and total operation counts.
- Median, range/percentiles of per-pair ratios, and confidence intervals where appropriate.
- A/B order, host, JVM flags, heap, GC, offered load, run duration.
- Warnings if both A and B are saturating CPU/DB or experiencing request timeouts.
- Correctness checks, error rates, and telemetry drops.

Per-instance p95/p99 values **cannot be simply averaged** to derive the workload-wide p95/p99. When percentiles across multiple JVMs or hosts are needed, raw latencies/histograms must be properly merged.

## 11. Testing Under Concurrency and Production-Like Load

A single-threaded demo helps observe probe cost, but an agent can cause overhead through **lock contention, `ThreadLocal`/context propagation, allocation, GC, exporter queues, and thread scheduling**. Those effects often only become apparent under multiple threads.

A minimal matrix:

| Load level | Target |
|---|---|
| 1 thread | Baseline hot-path and JIT cost |
| 4 threads | `LongAdder` contention, synchronization, GC |
| 16 threads | Scaling, CPU saturation, queueing |
| Normal service load | p50/p95/p99 latency, req/s, error rate |
| Near peak capacity | Headroom, backlog, retries, dropped requests |
| Peak load or bursts | Tail latency, exporter backpressure |

**Keep offered load identical** when comparing latency between A and B. If A receives 200 req/s while B receives 500 req/s, a higher p95 in B may simply be due to higher load.

For HTTP/RPC services, use a **load generator external to the application JVM**. The load generator must also have sufficient capacity so it does not become the bottleneck itself. Keep ramp-up and measurement durations, request mix, payloads, users/think time, and timeout rules identical.

### Closed-Loop vs. Open-Loop

- **Closed-loop driver:** sends the next request after the previous request's response returns. When the server slows down, the driver **automatically reduces** its send rate; measured throughput is affected by latency.
- **Open-loop driver:** sends at a predetermined arrival rate even when the server slows down; suitable for testing capability at a specific incoming rate, though backlog/capacity limits are needed.
- **Coordinated omission:** if a tool pauses sending requests while the server stalls, requests that **should have waited** may not appear in the data, artificially lowering p99. Choose a tool/configuration whose latency recording and request scheduling match your SLA.

Do not measure only `mean latency` when an agent has an exporter or lock contention; p95/p99 can degrade significantly even while the mean looks fine.

## 12. CPU, Allocation, GC, Heap, and RSS

**CPU utilization alone does not tell you the overhead**. 80% CPU in A at 1000 req/s is different from 80% CPU in B at 700 req/s. To compare efficiency, measure **CPU-seconds/1000 successful requests** at the same offered load.

**Allocation rate** is often a strong indicator of tracing overhead: span objects, tags, stacktraces, and context copies. Report `bytes/op` or `MiB/s`, not just “heap used” at a single point in time.

**GC impact**: an agent increasing allocations can trigger more frequent GCs, increasing tail latency. If that is a real effect in B, you must not filter out samples with GC to make the reported overhead look nicer. However, both A and B should have the **same GC logging flags**.

Example using unified JVM logging (JDK 17+):

~~~bash
java -Xms512m -Xmx512m -Xlog:gc*:file=gc-A-%p.log \
  -cp app.jar lab.BenchMain A 200000 2 2

java -Xms512m -Xmx512m -Xlog:gc*:file=gc-B-%p.log \
  -javaagent:agent.jar -cp app.jar lab.BenchMain B 200000 2 2
~~~

`%p` gives each JVM a PID-based log file. Enabling GC logging has its own overhead, but it is applied **equally to A and B**. For extremely short benchmarks, writing logs can have a heavy impact and there will not be enough GC events to analyze.

**Do not conflate memory metrics**:

- **Heap used:** live/allocated objects currently occupying the heap.
- **Heap committed/max:** heap space committed by the JVM / maximum limit.
- **Metaspace:** class metadata; an agent may load many additional helpers/proxies.
- **RSS:** actual physical memory of the process, which also includes code cache, thread stacks, native memory, mmap, JNI, and exporter buffers.

You can use GC logs, JFR, `jcmd`, or Native Memory Tracking for detailed analysis. If enabling `-XX:NativeMemoryTracking=summary`, enable it in **both groups** for that measurement, because NMT itself has overhead; do not substitute RSS and heap used for one another.

## 13. Separating Probe, Sampling, and Exporter Overhead

A production agent's pipeline is typically:

~~~text
JVM startup
  → load agent JAR
  → premain + transformer registration
  → class loading and bytecode generation
  → JIT/inlining/deoptimization effects
  → method entry/exit hooks
  → context propagation and tag extraction
  → sampling
  → batching, queues, aggregation
  → exporter network/retry
  → CPU, allocation, GC, thread contention
~~~

**You cannot attribute all overhead to `System.nanoTime` or the `transform` callback**.

To analyze root causes, create controlled sub-arms:

1. **A:** no agent, baseline.
2. **B0:** agent loaded, probes disabled (measures startup/background overhead).
3. **B1:** probes enabled, export disabled (measures instrumentation cost).
4. **B2:** standard production sampling, normal export.
5. **B3:** full tracing/metrics with real exporter (measures total impact).

The primary comparison for deployment evaluation remains **A versus the actual production B configuration**. The sub-arms serve **diagnostics** and must not alter the definition of A.

A 10% sampling rate does not guarantee that overhead is only 10% of 100% sampling: the agent may always create context or check flags before deciding whether to sample, and the exporter has fixed costs. You must test with the exact production batching policy, queue capacity, backpressure, endpoint, and sample rate.

If the reporter/agent drops telemetry under overload, a test might **look faster** because the tool is discarding records. Report **exported records, dropped records, and errors/retries** alongside performance so you do not accept good performance at the expense of observability.

## 14. JMH for Fine-Grained Benchmarks

**JMH** is the OpenJDK project's Java Microbenchmark Harness. It provides:

- `@Warmup`, `@Measurement`, `@Fork` to reduce errors from warm-up/forking.
- `@BenchmarkMode(Mode.Throughput)` or `Mode.AverageTime`, `Mode.SampleTime`, `Mode.SingleShotTime`.
- `Blackhole` to mitigate dead-code elimination.
- Profilers to observe allocation and GC.

Example **with JMH dependency** (does not compile with a plain JDK alone):

~~~java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.infra.Blackhole;
import java.util.concurrent.TimeUnit;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(3)
public class WorkBenchmark {
    @Benchmark
    public void compute(Blackhole bh) {
        bh.consume(lab.Work.compute(1234));
    }
}
~~~

When using JMH with an agent, the **forked benchmark JVM** must receive `-javaagent`; do not pass the agent only to the `java` process running the JMH coordinator. Group A forks must not have the agent; group B forks must have the agent. Run both groups under identical workload, JDK, threads, heap, and GC conditions.

JMH does not replace a **service load test** with external dependencies, requests, connection pools, and a real exporter.

## 15. Reading Results Correctly and Detecting Anomalous Data

**Warning signs:**

| Symptom | Possible Cause | Response |
|---|---|---|
| `RESULT` A/B have different checksums | Both groups are not doing the same work | Stop drawing conclusions, investigate semantics |
| B lacks `transformedWork=true` | Agent did not transform the target class | Check className, class loader, jar |
| B has `HOOK_CALLS=0` | Probe was not actually triggered | Check transformed bytes and method ref |
| Group A also has `HOOK_CALLS>0` | Baseline already called the recorder | Check JAR, source, and test isolation |
| One A sample is abnormally fast | JIT/loop optimization, window too short | Lengthen window, use JMH |
| GC increases in B | Higher probe/exporter allocation | Record GC as real overhead, profile |
| p99 degrades while mean barely changes | Queue/exporter locks/GC tail | Measure histograms, backlog, errors |
| High throughput but many 5xx responses | Fail-fast instead of doing the same work | Verify successful operations |
| Running B after all A runs on a hot machine | Order causes drift | Interleave or randomize forks |
| A/B on different JDKs | Different JIT/GC | Use the same JDK version/vendor |
| Both on one small host running concurrently | CPU/cache/memory contention | Run sequentially or on separate hosts |
| Agent loader changes class identity | Wrong class instrumented or wrong loader | Log classloader and filter properly |
| Console output inside hot method | I/O overhead dwarfs probe | Move logging outside measurement |
| Using `currentTimeMillis()` for microbenchmark | Low resolution, wall-clock adjustments | Use `System.nanoTime()` differences |
| Subtracting raw `nanoTime` across two JVMs | Different origins | Only compute elapsed within each JVM |
| B fails silently without metrics or exporter disabled | Overhead concluded to be too low | Check enabled state and dropped events |

An unreasonably lower sample time than expected may signal **compiler optimization** or an **overly short window**; do not patch the numbers with a fudge factor. Increase the work, use JMH, and verify side effects/correctness.

## 16. Responsible Performance Reporting

A report template should include:

| Field | Content |
|---|---|
| Artifact | SHA/version of app JAR and agent JAR, exact config |
| Runtime | Java vendor/version, JVM flags, GC, OS, CPU quota/RAM |
| Workload | Data set, request mix, offered load, concurrency, duration |
| Protocol | Warm-ups, measurement windows, forks, A/B order, test hosts |
| Correctness | Checksums or business assertions, errors, timeouts, retries |
| Core results | ns/op, throughput, p50/p95/p99, CPU, allocation, GC, RSS |
| Reliability | Variance across forks, paired ratios, confidence intervals |
| Instrumentation | Enabled probes, sampling/exporter config, dropped events |
| Decision | Comparison against agreed performance budget, measurement limits |

**Example phrasing of conclusions** (the following numbers are hypothetical, not demo results):

> Across 8 independent JVM pairs using the same JDK and load, group B had 4.2% lower median throughput and 5.8% higher p95 latency. P99 was not yet stable across forks, so additional measurements under high load are needed. Business results and error rates were equivalent. CPU cost per 1,000 requests increased noticeably when the exporter was enabled. Before rollout, the team will reduce the number of method probes and re-measure.

If group B is only 0.3% slower while run-to-run jitter is around 2%, the right statement is **“there is insufficient evidence to confirm a 0.3% overhead”**, not a figure reported to four decimal places.

## 17. Checklist Before Finalizing Overhead Numbers

1. **Define the primary metric properly:** startup, steady-state ns/op, req/s, p95/p99, or CPU/op?
2. **Set acceptance thresholds before** looking at results, avoiding cherry-picking the best metric after the test.
3. **Require a true no-agent A group** and a B group with the real agent/config.
4. **Use the same app/JDK/JVM flags** and resource limits.
5. **Equivalent data/traffic**, same offered load, concurrency, and backend state.
6. **Verify agent B actually instruments** the right target; identical business results.
7. **Sufficient warm-up and steady-state measurement** over long windows, separated from startup.
8. **Run multiple JVM forks** and balance A/B ordering.
9. **Use the right formulas** for latency overhead vs. throughput loss.
10. **Save raw data** per sample/fork/pair, not just a single average.
11. **Evaluate variance and confidence**, never treating each operation as an independent fork.
12. **Observe p95/p99, errors, retries, and backlog** at production concurrency.
13. **Measure CPU/allocation/GC/memory**, not just latency.
14. **Document sampling, exporter, filters**, and dropped telemetry.
15. **Do not discard real effects** like agent-induced GC just to lower reported overhead.
16. **State conditional conclusions** and optimization/re-testing actions if over budget.

## 18. Self-Check Questions

1. **What is the main difference between A and B?** B loads the agent and runs the instrumentation configuration under evaluation; A has no agent from JVM startup.
2. **Is an agent-loaded run with disabled probes considered group A?** No.
3. **Why must JDK/heap/GC flags be identical?** Because the JVM and GC themselves can change the results.
4. **What is a paired fork?** One JVM A and one JVM B run close together under identical conditions, each run being a fresh process.
5. **Why alternate A/B order?** To reduce the impact of CPU, thermal, and backend drift.
6. **Does one JVM running 1 million ops produce 1 million independent statistical observations?** No.
7. **Why is warm-up needed?** JIT, class loading, and GC are not yet stable in the initial phase.
8. **Does a 10% throughput loss equal a 10% latency/op increase?** No; if sequential conditions apply, time/op increases by about 11.11%.
9. **Is subtracting raw `System.nanoTime` of A from raw B valid?** No; each JVM's origin is different.
10. **If B has a transformer but zero hook count, has probe overhead been measured?** Not yet; you must inspect the transformed bytes and hot path.
11. **Are identical A/B checksums enough to conclude overhead?** No; that is a correctness check.
12. **Why increase operations when elapsed time is very short?** So that clock/JIT/scheduler overhead does not drown out the signal.
13. **When is JMH appropriate?** Microbenchmarking hot methods and bytecode variants.
14. **When is an external load test important?** Service concurrency/network/DB/exporter, at a controlled offered load.
15. **If B has better p95 but more 5xx responses, has performance improved?** No; performance must go hand in hand with correctness.
16. **Can tail latency degrade even when throughput stays roughly the same?** Yes, due to GC/queues/locks/exporter.
17. **What is coordinated omission?** A driver failing to record requests that should have waited while the server stalled, causing latency to be underestimated.
18. **When the agent causes GC pauses, can those samples be dropped?** No, if GC is a real effect of the agent.
19. **What should you report if the difference is smaller than run-to-run variation?** Insufficient evidence; more forks or better controlled conditions are needed.
20. **Minimum reporting units?** Always specify ns/op, ms/request, ops/s, CPU/op, and measurement definitions.

### Official Documentation

- [OpenJDK JMH](https://github.com/openjdk/jmh): benchmark harness with forks, warm-up, measurement, Blackhole.
- [JMH Sample: Benchmark Modes](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_02_BenchmarkModes.java): throughput, average-time, sample-time, and single-shot.
- [Oracle Java SE 21 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, `Premain-Class`, lifecycle.
- [Oracle Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer registration and callbacks.
- [Oracle Java SE 21 — `System.nanoTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html): elapsed, arbitrary origin, resolution.
- [Oracle Java SE 21 — `java` launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xlog` for logging JVM/GC metrics.
- [Oracle Java SE 21 — `LongAdder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): concurrent counters and `sum()`.

**Conclusion:** To quantify the overhead of a Java agent, compare **the same application/workload across multiple independent JVMs**, one **no-agent** branch and one **with-agent branch that actually instruments properly**, control warm-up/JIT/GC/CPU and concurrency, compute latency/throughput using the right denominators, and report **the effect along with its uncertainty**. Measurements are only meaningful when the A/B design is fair and the application still performs **the same work**.