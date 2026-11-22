# Warm-up, steady state, and the difference between startup time and peak performance

## 1. Why does the same Java method run slower at first than later?

With the **HotSpot JVM**, Java bytecode can be executed by the **interpreter**, after which beneficial methods or loops are translated into optimized machine code by the **JIT (Just-in-Time) compiler**. While the program runs, the JVM also collects information about object types, conditional branches, and call frequencies, loads classes, resolves links, initializes data, opens connections, warms up caches, and performs garbage collection (GC).

Therefore, two runs of **the same piece of source code** can take different amounts of time:

- **Cold start:** the JVM process has just started, many classes are not yet loaded/initialized, many methods are not yet JIT compiled, and business caches are not ready.
- **Warm-up:** one or more components are transitioning states: JIT is compiling and recompiling, profiling is maturing, the code cache is growing, thread pools and connection pools are forming, and data or the OS page cache is being warmed.
- **Steady state:** the system operates within a measurement interval where the distribution of throughput/latency, allocation, GC, CPU, compilation, and workload no longer shows a major transitional trend; natural noise and variability still exist.
- **Peak performance:** the highest throughput or lowest latency under a **specific definition and resource budget**, achieved during a phase of an experiment. It **does not by itself prove** that the system is stable, meets SLOs, or can sustain that level in production.

**The problem is not just asking “is JIT faster than the interpreter”.** It is necessary to understand *when* the system begins serving, *when* measurement results are trustworthy, *why* a fast run is not a sustainable result, and *which target* needs to be optimized for a specific application type.

> **Golden rule:** `time to first useful result`, `time to readiness`, `time to steady-state throughput`, and `peak throughput` are **four different measurements**. Do not equate startup time with the speed of an already-hot loop.

## 2. A typical timeline from process launch to steady state

~~~text
Time →
OS start Java process
      |
      +-- JVM initialization, class loading, verification/linking
      |
      +-- Application/bootstrap/static initializers
      |
      +-- First successful request / first useful result
      |         |
      |         +-- Classes/methods loaded additionally along the actual execution path
      |         +-- Interpreter/C1, profiling, C2 compilation (HotSpot-dependent)
      |         +-- Cache, connection pool, GC/heap occupancy change
      |         |
      +-- Readiness signal (defined by the application)
      |         |
      +-- Warm-up workload, JIT/code cache/GC progress toward operating rhythm
      |         |
      +-- Candidate steady-state measurement windows
      |         |
      +-- Peak throughput point or target latency
~~~

**The milestones do not strictly have to follow the exact order shown in the diagram.** A service may report readiness before all routes are hot; another system only becomes ready after preloading data; background class loading or recompilation can occur **after** an interval that seemed stable. The throughput peak may appear before or after the steady-state window, or even at a saturation point where p99 latency is very bad.

### 2.1. Startup latency

A definition must have **two clear milestones**:

- `process_start → main entry`: from the launch command until entering `main`.
- `process_start → first result`: from process launch to the first successful request / first business result.
- `process_start → ready`: until the readiness probe satisfies the system contract.
- `deploy → ready`: also includes image pull, container create, scheduling, network, and orchestration; **it is no longer just JVM startup**.

A JVM can enter `main` very quickly while the application takes several seconds to create a connection pool or load a model. Conversely, an application may report ready early while the first requests after ready are slow because classes/JIT are still cold.

**Do not treat `main` printing `READY` as proof that the entire service is ready**, unless the real program has a readiness protocol reflecting dependencies, routes, and target serving capability.

### 2.2. Warm-up duration — the transition period

Warm-up can be defined as **a set of requests or a duration of time** run before collecting the main metrics. However, `warmup = 5s` is only an *experimental policy*, **not a guarantee that the JVM has JIT-compiled every method after 5 seconds**.

A service with dozens of routes can warm up route A while route B remains cold when the traffic mix changes. A method profiled earlier with `Cat` inputs can deoptimize the first time it encounters `Dog`. A valid warm-up must be paired with a **representative workload** and actual runtime verification, not just waiting on a clock.

### 2.3. Steady state — must be measured and verified

A measurement interval is a steady-state candidate when at least:

1. **Offered workload is stable** (arrival rate, request mix, payload, concurrency, data sizes).
2. **Throughput, p50/p99, CPU/GC metrics** show no clear phase-transition trend beyond expected noise.
3. **The number of JIT compilations and deoptimizations** does not exhibit prolonged, high-impact bursts.
4. **Live set and heap occupancy** have a relatively stable rhythm; no silent leak accumulation.
5. **External state** such as DB cache, TLS sessions, page cache, and thread pools has entered a representative state.
6. Measured across **multiple time windows**, not just a single average aggregated from app startup.

This is a **verifiable practical definition**, not a JVM flag that flips on to report `STEADY_STATE=true`. A service using different features by hour/day may **never reach a single global steady state**; in that case, measure each load regime separately.

## 3. Interpreter and tiered compilation mechanisms on HotSpot

### 3.1. The interpreter enables immediate execution

Bytecode is executed by the JVM according to the language contract, and HotSpot has an interpreter. The interpreter does not need to compile every method into optimized native code before running. That benefits startup/fallback, while code executed repeatedly often gets the opportunity to be optimized by the JIT.

Do not infer that **an entire application always stays in the interpreter for the first X requests**, then switches all at once to compiled. Methods can be JIT-compiled at **different times**; part of the code may be interpreted while another part is already compiled.

### 3.2. C1 and C2 — the compilation cost and code quality trade-off

In the HotSpot tiered compilation model commonly used with JDK 17:

- **C1** aims for relatively fast compilation, with tiers that collect or utilize profiling at different levels.
- **C2** can use profile information to perform more aggressive optimizations, costing more CPU/compile time but typically producing better code for hot paths.
- The JVM selects compilation policy based on invocation counts, loop backedges, profile data, compiler queues, and runtime conditions.

It can be visualized simply:

~~~text
                 Bytecode / interpreter (tier 0)
                              |
                    profiling and hotness
                              |
               C1 tiers (1 / 2 / 3, depending on the path)
                              |
                   more profiling / hotness
                              |
                C2 optimized code (tier 4)

Afterward, there can still be:
  - deoptimization → interpreter / another compiled tier
  - recompilation after the profile changes
  - code invalidation / code cache cleanup
~~~

**This is not a rigid mandatory pipeline for every method.** There can be different tier transitions, inlining and OSR, very small methods, rarely used code, and differing VM flags. Do not demand that “every method must go through all of 0→1→2→3→4”.

A JDK/implementation may use different compilers or organization; **C1/C2/tiered** are notable details of HotSpot, not mandatory structures of the Java Virtual Machine Specification.

### 3.3. Hot code, call counters, backedges, and OSR

HotSpot uses profiling and hotness estimates, including **method invocation count** and **loop backedge activity**. A long-running loop inside a single call can become hot even when the method is called only once. **On-Stack Replacement (OSR)** lets the VM transition a running loop into optimized compiled code at an appropriate point, instead of waiting for the method to finish and be called again.

Therefore:

- “Calling a method only once means it will never be JIT-compiled” is **false** for sufficiently hot loops.
- “Calling 10,000 times guarantees C2” is also **false**; compiler thresholds/policies are not portable constants.
- `-XX:CompileThreshold` and JIT flags have semantics/scopes that depend on tiered mode and JDK; do not treat a single value as a universal law.

### 3.4. Speculative optimization and deoptimization

The JIT can rely on the current profile. For example, a virtual call site during warm-up only receives objects of one class; the runtime can optimize devirtualization and inlining under a guarded assumption. When an input of another type appears or the assumption no longer holds, the code can **deoptimize** and execute safely according to Java semantics, then be recompiled when needed.

~~~text
Warm-up: 99.9% PaymentCard
        |
        v
JIT has a nearly monomorphic profile, optimizing the common branch
        |
        v
New traffic: PaymentCrypto or an unseen edge case
        |
        v
Uncommon trap / deoptimization / recompilation may occur
        |
        v
Short-term latency spike, behavior changes afterward
~~~

This is an **illustrative scenario**, not a claim that every input type change definitely deoptimizes or always produces a spike of the same duration.

**Warming up with non-representative data** can produce a nice-looking optimized code path that makes subsequent measurements noisy or even worse under real traffic.

## 4. Warm-up is affected by many factors beyond JIT

| Component | When cold | During warm-up | What can stabilize |
| --- | --- | --- | --- |
| **Class loading/linking** | Rarely used classes not yet loaded | Loaded when routes/features are called | Fewer unexpected class loads on hot paths |
| **Static initialization** | Some `<clinit>` not yet run | Initializing lazy singletons, registries | Fewer sudden init spikes on request path |
| **Interpreter/JIT** | Many methods interpreted/C1 | Compilation/profiling, OSR, inlining | Fewer high-impact transitions |
| **Code cache** | Native code cache has few compiled methods | Compiled code added/swept | Metrics do not continuously spike |
| **GC/heap** | Heap has few live objects | Promotion, aging, retained caches, GC frequency shifts | Representative live set/GC pattern |
| **Application caches** | Empty/cold | Loading DB rows, templates, regex, config, class metadata | Representative cache-hit rate |
| **Thread/connection pools** | Not yet created or few active | Spawning, handshakes, connections, TLS sessions | Relatively stable capacity/queueing |
| **OS page cache** | Disk pages not yet resident | Files/resources accessed | Fewer disk misses under similar workload |
| **External dependencies** | DB/cache/server in initial state | Connection establishment/prepared statements | Response times matching real load |

**Observing latency drop during the first 20 seconds is not enough to prove it is caused by JIT.** You must decompose the time and use compilation logs/JFR, allocation profiles, class-load logs, and dependency metrics.

### `static` and lazy initialization make first-hit differ from steady-state

An expression like `Pattern.compile`, loading a JDBC driver, initializing a JSON serializer, opening a TLS connection, or calling a complex dependency for the first time can dominate CPU/I/O and class loading. JIT may not be the dominant factor.

This is especially clear in serverless applications, command-line tools, and autoscaling bursts: **each new process hits startup/cold paths again**. “The service is fast after 5 minutes” may not save the first-response SLO when instances are continuously created and destroyed.

### CDS and AOT: do not extrapolate across versions

**Class Data Sharing (CDS)** and application preloading/class sharing can improve parts of class loading/startup, but do not automatically bring all application methods to **C2 peak**. AOT and VM warm-startup techniques continue to evolve across JDK releases; **do not assume a newer JDK feature has the same behavior on JDK 17**.

If enabling CDS/AppCDS or specific flags, benchmark **the same JVM build, the same artifact, and the same configuration**; measure startup and peak separately.

## 5. Java 17 runnable lab: observing batches before and after warm-up

The program below:

1. Runs **4 warm-up batches**.
2. Measures **6 measured batches** using the same compute function and the same number of operations.
3. Publishes a constant iteration count, a fixed output checksum, and per-batch timings that **depend on the environment**.
4. Explicitly notes that a faster batch **does not by itself prove steady state has been reached**.

Create the file **`WarmupLab.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class WarmupLab {
    private static volatile long published;

    static long compute(int seed) {
        long x = seed + 0x9E3779B97F4A7C15L;
        for (int i = 0; i < 256; i++) {
            x ^= x >>> 27;
            x *= 0x3C79AC492BA7B653L;
            x ^= x >>> 33;
        }
        return x & 0xffL;
    }

    static long runBatch(int firstSeed, int ops) {
        long sum = 0;
        for (int i = 0; i < ops; i++) {
            sum += compute(firstSeed + i);
        }
        published = sum;
        return sum;
    }

    public static void main(String[] args) {
        final int warmupBatches = 4;
        final int measuredBatches = 6;
        final int operationsPerBatch = 6000;
        final long[] elapsedNs = new long[measuredBatches];

        System.out.println("warmupBatches=" + warmupBatches);
        System.out.println("measuredBatches=" + measuredBatches);
        System.out.println("operationsPerBatch=" + operationsPerBatch);

        for (int i = 0; i < warmupBatches; i++) {
            long start = System.nanoTime();
            runBatch(100_000 + i * operationsPerBatch, operationsPerBatch);
            long elapsed = System.nanoTime() - start;
            System.out.println("warmup" + i + "Ns=" + elapsed);
        }

        long checksum = 0;
        for (int i = 0; i < measuredBatches; i++) {
            long start = System.nanoTime();
            checksum += runBatch(
                    200_000 + i * operationsPerBatch, operationsPerBatch);
            elapsedNs[i] = System.nanoTime() - start;
            System.out.println("measured" + i + "Ns=" + elapsedNs[i]);
        }

        long[] ordered = elapsedNs.clone();
        Arrays.sort(ordered);
        long totalNs = 0;
        for (long n : elapsedNs) totalNs += n;

        System.out.printf(Locale.ROOT, "avgBatchMs=%.3f%n",
                totalNs / (measuredBatches * 1_000_000.0));
        System.out.println("checksum=" + checksum);
        System.out.println("lastBatchPublished=" + published);
    }
}
~~~

### 5.1. Compile/run

~~~bash
javac --release 17 WarmupLab.java
java WarmupLab
~~~

**Output lines with deterministic values according to the program:**

~~~text
warmupBatches=4
measuredBatches=6
operationsPerBatch=6000
~~~

Then the program prints `warmup0Ns=...` through `warmup3Ns=...`, `measured0Ns=...` through `measured5Ns=...`, and `avgBatchMs=...`. **These timings are dynamic numbers; there is no fixed nanosecond stdout** across all CPUs/JITs/OSes.

**Two fixed computation result lines:**

~~~text
checksum=4596631
lastBatchPublished=763004
~~~

The code was **compiled with `javac --release 17` and run on OpenJDK 24**, in default HotSpot JIT mode and `-Xint`. Both modes produce the three configuration lines and the two checksum lines above.

**One local measurement observed** approximately `avgBatchMs=2.023` with default JIT and `avgBatchMs=18.018` with `-Xint`. This only illustrates that execution mode can affect performance; **it is not a standard Java 17 runtime benchmark, not an average speed across all machines, and not sufficient to claim peak/steady state**. Subsequent runs may differ.

### 5.2. Why `volatile` and checksum?

`compute` returns a value depending on `seed`; `runBatch` sums the results and writes to the `volatile published` field, giving the computation an observable effect. This reduces the risk of the JVM eliminating the entire test body as dead code. However, `volatile` **does not turn a hand-written loop into a proper microbenchmark**; profiling, inlining, loop optimization, caches, scheduling, and `nanoTime()` resolution can still skew measurements.

`Arrays.sort(ordered)` happens **after** the measured batches and is not included in the recorded elapsed durations; it illustrates that samples can be processed after measurement, even though this demo only prints the average and does not report percentiles. If you want to compare **per-request p99**, you must measure each request, not interpret `avgBatchMs` as p99.

### 5.3. Inferences that can and cannot be drawn

**Can conclude:** in the specific environment/run, HotSpot mixed-mode and interpreter-only have different throughput/timing; business-logic program output such as checksum does not change.

**Cannot conclude:** that four warm-up batches definitely caused C2 to compile every method; that six batches prove steady state; that JIT will be exactly 8.9× faster in production; that the first request is slow solely because of the interpreter; or that `-Xint` is an accurate simulation of a default cold start.

## 6. Observing JIT with diagnostic flags instead of guessing

### 6.1. `-XX:+PrintCompilation`

On HotSpot/JDK 17:

~~~bash
java -XX:+PrintCompilation WarmupLab
~~~

The JVM can print lines reporting compiled methods along with fields such as time since JVM start, compilation ID, tier level, and method name. **Format/IDs/timing vary by JVM build and load state**, so an invariant verbatim stdout cannot be given. Diagnostic output can interleave with the application's `System.out`, so **do not use a logging run to infer standard benchmark throughput**.

Look for the relevant compilation entries:

~~~text
WarmupLab::compute
WarmupLab::runBatch
WarmupLab::main
~~~

A method appearing in the log does not guarantee it was compiled **only once**, compiled at the final tier, or that all code immediately uses that version. The JVM can print multiple entries, OSR compilations, made-not-entrant, or deoptimization events.

### 6.2. Comparing with interpreter-only `-Xint`

~~~bash
java -Xint WarmupLab
~~~

`-Xint` forces interpreter-only mode per the HotSpot/Java launcher contract and disables JIT compilation benefits. It can run much slower on compute loops.

**Do not use `-Xint` as a measurement of production cold startup**: on a cold JVM running with defaults, the VM can still compile hot methods while serving. `-Xint` actively disables that mechanism, so it is only a **mechanism experiment**, not an inferred production configuration.

### 6.3. Stopping tiered compilation at C1

With HotSpot and a supporting configuration:

~~~bash
java -XX:TieredStopAtLevel=1 WarmupLab
~~~

This flag is commonly used to limit the compiler pipeline to the corresponding C1 level, useful for observing the trade-off between **compilation time versus compiled code quality**. It is **not an “always faster startup” switch**, makes no output/timing guarantees, and semantics can change across releases. Both first-response latency and sustained throughput must be measured.

### 6.4. Do not use `-Xcomp` to automatically claim peak

`-Xcomp` requests compilation-first in HotSpot and can make startup/compilation times very different from normal. It **is not synonymous** with a JVM having been warmed up with a representative workload or all branch profiles having matured. Do not use `-Xcomp` as a shortcut to compute “maximum possible Java speed”.

### 6.5. Code cache and compiler queues

JIT-compiled machine code resides in the **code cache**. If the code cache is overly constrained or compiler queues are overloaded, hot paths may lose opportunities to compile/recompile as expected; throughput and the warm-up profile are affected.

You can use `jcmd` to inspect commands the VM actually supports; for example, some HotSpot builds provide compiler/code cache info:

~~~text
jcmd
jcmd <PID> help
jcmd <PID> Compiler.codecache
~~~

**`<PID>` is a placeholder in the instructions**—replace it with the actual process ID before running, without pasting the literal `< >` brackets into the shell. Command names and attach permissions depend on the JDK/VM. Do not assume a `jcmd` subcommand exists on every vendor.

## 7. Measuring startup from outside the JVM: choosing the exact milestones

Java code inside `main` cannot alone fully measure **OS launch → JVM initialization → application startup** by starting `System.nanoTime()` when `main` runs: the steps before `main` have already passed.

### 7.1. Measuring the total runtime of a CLI process

Bash/Linux/macOS:

~~~bash
time java -cp . WarmupLab
~~~

PowerShell:

~~~powershell
Measure-Command { java -cp . WarmupLab | Out-Null }
~~~

**Note**: the commands above measure **both warm-up time and measured batches inside `main`**, plus JVM startup and process shutdown. They **cannot** separate individual startup/ready/steady-state milestones. In PowerShell, `Measure-Command` also includes shell/pipeline overhead; when comparing runs, keep the same wrapper.

To measure **time to first response** of a service, use a load generator/client that timestamps before sending the request and after receiving the result. To measure **time to readiness**, read the readiness event actually emitted by the service in its lifecycle, not just when the port opens or the process exists.

### 7.2. Measuring a fresh run every time

Each `java ...` invocation is a new process with a fresh JIT/code cache state. This helps compare cold processes, but **the OS filesystem page cache, JIT artifacts in shared/runtime facilities, containers, and external databases may still be warm**. A cold JVM process does not mean the entire system is cold.

If testing startup multiple times:

1. Fix the **JDK build, image, flags, classpath, and environment**.
2. Use a new process each iteration; do not reuse an already-serving JVM.
3. Keep the dataset and external dependencies identical, or explicitly label warm/cold external cache.
4. Run enough repetitions and randomize candidate order to reduce OS/noisy-neighbor effects.
5. Report median, p95/p99, variability, and outliers; not just the fastest run.

**Do not drop OS caches in production** or perform dangerous system operations to “cool down” a test. You can provision a dedicated controlled node/VM or benchmark warm-OS-cache and cold-OS-cache as two labeled scenarios.

## 8. Why warm-up is not just “running a loop enough times”

### 8.1. Profile mismatch

Warm-up runs 100% short inputs, while measurement uses very long inputs with different branches/allocations. The JIT may have optimized code primarily for the short hot branch, leaving the long path cold or needing deoptimization. Keep **data shapes and type distributions representative**.

### 8.2. Dead-code elimination

~~~java
for (int i = 0; i < 1000000; i++) {
    Math.sqrt(123.456);
}
~~~

This is only an **illustrative snippet**, without a class/main. The result of `Math.sqrt` is unused; the optimizer may remove the call or the entire loop. Timing this snippet does not measure 1 million square root operations.

### 8.3. Constant folding

~~~java
double value = 100 * 200.0;
~~~

The compiler can compute constant values at compile/optimization time. A benchmark of “one million multiplications” with compile-time constant operands can turn into an assignment benchmark, not runtime multiplication.

### 8.4. Escape analysis and allocation elimination

An object created and used only locally, without escaping the scope observed by the optimizer, may be scalar-replaced or have its allocation eliminated in some cases. If the real application has objects surviving across request boundaries, a benchmark with easily escape-analyzed objects may not represent production allocation pressure.

### 8.5. Inlining and call-site profile

A method that is very fast when JIT-inlined into its caller can be slower when measured as a virtual interface call with multiple concrete receiver types. Simulate the **call-site polymorphism** of the real workload.

### 8.6. Warm-up affects GC/lifetime

Heap occupancy, object ages, young/old generations, and GC frequency can change after thousands of requests. A benchmark intended only to examine JIT compilation that also allocates large objects may measure mixed GC; enable GC logs to explain it.

### 8.7. OS, CPU, and JIT background compilation

The OS scheduler, CPU turbo/frequency scaling, thermal throttling, CPU affinity, process priority, heap page faults, and background compiler threads all introduce noise. These factors can create apparent “speedups” or “slowdowns” without machine-level code changing.

**A good measurement always describes the workload and environment, not just the Java code.**

## 9. JMH: a more suitable tool than hand-rolled `nanoTime()` loops

**Java Microbenchmark Harness (JMH)** is a tool from the OpenJDK project for benchmarking small Java snippets. It supports forks, warm-up iterations, measurement iterations, modes, output units, parametrization, and mechanisms to avoid common pitfalls.

Example **illustrating the JMH API, not a standalone Java SE 17 file** because it requires JMH dependencies/build plugin:

~~~java
@State(Scope.Thread)
public class ComputeBenchmark {
    private int seed = 12_345;

    @Benchmark
    public long compute() {
        return transform(seed++);
    }

    private static long transform(int s) {
        long x = s;
        for (int i = 0; i < 256; i++) {
            x = (x ^ (x >>> 13)) * 31 + i;
        }
        return x;
    }
}
~~~

Compiling this JMH snippet requires `org.openjdk.jmh.annotations.*` and the JMH library on the classpath; the snippet only shows the `@State`/`@Benchmark` structure and **does not promise that plain JDK `javac` can compile it**.

**Why do forks matter?** Each fork has its own JVM, avoiding running candidate B on a heap/code cache already warmed up by candidate A in the same process. JMH warm-up can also be configured by time/iterations to clearly define which phase is excluded from the main measurement.

**However, JMH does not solve everything:**

- Microbenchmarks do not automatically simulate HTTP queueing, DB, network, thread contention, or load distribution.
- Warm-up in JMH still requires the right input distribution.
- JMH does not define business SLOs or production readiness.
- A good benchmark still needs multiple forks/repetitions and proper statistics.

For services, use **JMH for hot functions** and **end-to-end load testing for application latency/throughput**.

## 10. Throughput, average latency, and tail latency during warm-up

Suppose a service has just started:

~~~text
Window 1 (0–10s): throughput  700 req/s, p99 300ms
Window 2 (10–20s): throughput 1400 req/s, p99 120ms
Window 3 (20–30s): throughput 1800 req/s, p99  75ms
Window 4 (30–40s): throughput 1850 req/s, p99  72ms
Window 5 (40–50s): throughput 1830 req/s, p99  78ms
~~~

**This table is illustrative only, not real measured benchmark results.** You might consider windows 4–5 as steady-state candidates, but **cannot confirm it from these five numbers alone**: you still need to check offered load, CPU, GC, JIT events, memory retention, and statistical properties.

If you only take the **average throughput across all 50 seconds**, you mix warm-up with near-steady-state time. That may be right if the question asks for **total requests processed over a short lifecycle**, but it is the wrong metric if you want to compare **steady-state capacity**.

Conversely, discarding all initial runs and reporting the **best stable 10 seconds** can cause cherry-picking and excessive optimism. Warm-up/measurement separation criteria must be defined in advance.

### Peak throughput can violate latency SLOs

A service might reach **3,000 req/s maximum** while p99 latency at that point is 900 ms due to queueing. If the requirement is p99 ≤ 100 ms, the **SLO-compliant sustainable throughput** might only be 2,100 req/s. Therefore:

- **Unconstrained peak throughput:** highest measured ops/s, possibly at bad latency or high error rate.
- **SLO-constrained sustainable throughput:** highest load meeting p99/error/memory/CPU constraints over a sufficiently long measurement interval.
- **Steady-state throughput:** processing rate in a relatively stable regime; may be lower than peak.
- **Startup average throughput:** work completed in the window starting at process launch, including cold/warm transitions.

Do not write a performance table with only a single `ops/s` column without recording the phase, SLO, and measurement duration.

### Coordinated omission

A **closed-loop** load generator sends a new request after the previous one completes, so when the server pauses, the client can issue fewer requests, hiding tail latency caused by queueing. When aiming to measure a fixed arrival rate, use an **open-loop/rate-controlled** workload, record offered, completed, failed, and timed-out requests, and apply histogram recording based on scheduled arrival time where appropriate to reduce coordinated omission.

Do not discard timeouts/failed requests and report p99 only on successful requests, because a service that processes slowly or drops requests can artificially look “fast”.

## 11. JIT logs and JFR to verify real warm-up

### `-XX:+PrintCompilation`

Useful for labs to inspect **which methods** are compiled and tier activity. However, output can be voluminous and alter timing; run a separate **diagnostic** pass, while benchmark runs use consistent logging with controlled overhead.

### Java Flight Recorder

JFR on JDK 17 can record events for compilation, deoptimization, CPU samples, GC, allocation, classes, and thread activity when **enabled with appropriate settings**. Events such as `jdk.Compilation` or `jdk.Deoptimization` can be useful depending on the JDK build and recording configuration. **Not all events are enabled by default** in `default.jfc`/`profile.jfc`.

Example starting a recording for a real application:

~~~bash
java '-XX:StartFlightRecording=filename=warmup.jfr,settings=profile' \
  -jar app.jar
~~~

This illustrative command requires the application's actual `app.jar`; with `WarmupLab`, you can use:

~~~bash
java '-XX:StartFlightRecording=filename=warmup.jfr,settings=profile' WarmupLab
~~~

Inspect metadata/events with:

~~~bash
jfr summary warmup.jfr
jfr print --events jdk.Compilation,jdk.Deoptimization warmup.jfr
~~~

A short JFR recording may have few or no desired events due to thresholds/settings. Do not use “no events” as proof that “JIT did not run at all” without verifying event enablement.

### GC and class loading

~~~bash
java '-Xlog:gc=info,class+load=info:file=runtime.log:uptime,level,tags' WarmupLab
~~~

The log can show GC events/class loading activity in the process. **Class load is not synonymous with class initialization**; GC elapsed pause is also not the entire stop interval. When safepoint timings are needed, add the `safepoint=info` tag if supported by the JVM.

### `CompilationMXBean` has limitations

`java.lang.management.CompilationMXBean` has the `getTotalCompilationTime()` method, but the JVM may not support monitoring this (the API indicates when unsupported). The total value also **does not by itself prove all hot methods are at tier 4**, or that the application has reached steady state. Do not use total compilation milliseconds as a standalone readiness condition.

## 12. Designing three separate benchmarks instead of one aggregate number

### Experiment A — Cold-start / readiness latency

**Question:** how long does a new instance take from process launch until it can handle the first request at acceptable quality?

- Each sample: **a fresh JVM process**.
- Measurement milestone: timestamp from outside the process; clearly define successful probe/response.
- Keep the same JDK, image, memory/CPU budget, and dependency state.
- Measure cold image/cache scenarios separately if important for autoscaling/serverless.
- Report p50/p95/p99 startup + first response; record failure rate.

**Do not use** `WarmupLab.avgBatchMs` as time-to-ready.

### Experiment B — Time to steady state

**Question:** after how long does the application reach relatively stable throughput/latency under a representative workload?

- Issue requests at a controlled arrival rate, starting from the application-ready milestone.
- Measure continuously across fixed windows (e.g., every 5 or 10 seconds).
- Check throughput, p99, JIT/deopt events, GC, CPU, and memory.
- Define stability criteria before the experiment, such as three consecutive windows with no major trend and passing SLO; thresholds must fit variability.
- Report **time to meet criteria** and the proportion of runs that actually meet it, not just a good-looking sample.

**Caution:** the runtime stopping compilations for a while is **not sufficient** to call steady state if the DB cache is still growing, the live set is still drifting, or the load generator is changing the offered rate.

### Experiment C — Sustainable steady-state throughput / peak

**Question:** within the same CPU/memory budget, under a given SLO, how much stable load can the system serve?

- Warm up with representative traffic.
- Use multiple offered rates: below target, at target, near saturation.
- Do not remove timed-out/failed requests when computing results.
- Measure p95/p99/p99.9, achieved throughput, CPU, RSS/cgroup, and GC/JIT cost.
- Run a long soak to observe rare GC, native retention, thermal/CPU throttling, and leaks.
- Publish **SLO-constrained sustained throughput** and unconstrained peak as two separate columns.

If an application is short-lived, such as a CLI that runs for 2 seconds and exits, experiments B/C may matter less than **total job elapsed** on a cold process. Choose KPIs according to product lifecycle.

## 13. Warm-up in microservices/autoscaling systems

Java applications running in deployments have a specific problem: you cannot take the steady-state capacity of **an instance that has been running for 3 hours** and assume a newly autoscaled cold instance will immediately serve full traffic.

### Readiness, liveness, and traffic shifting

- **Liveness:** the process/service is still alive under basic checks.
- **Readiness:** the instance is eligible to **receive traffic** per the deployment protocol; do not assume every JIT path is already at peak.
- **Internal warm-up status:** optional signal based on route/request mix and ability to serve target workload.
- **Traffic ramp:** gradually increase load to avoid many cold instances simultaneously causing request latency spikes or compiled-code CPU pressure.

Do not delay readiness indefinitely just to wait for “C2 to compile everything,” because that is not a milestone the JVM can guarantee. Instead, set **finite acceptance criteria** for required readiness functionality, preload critical dependencies, warm representative hot routes if worthwhile, and use a monitored traffic ramp.

### Scale-out and warm-up cost

When workload suddenly increases, the autoscaler creates many new pods/JVMs. They may simultaneously:

- Load classes and create connection pools.
- Compile code in the background, competing for CPU quota with requests.
- Warm DB/caches, creating a burst of load on downstream systems.
- Experience GC heap occupancy transitions.
- Achieve lower throughput during the first few tens of seconds.

If a capacity planner multiplies **steady-state req/s per pod** immediately by the number of new pods, initial capacity forecasts can be overly optimistic. You must profile the **warm-up ramp curve** and use an appropriate autoscaler readiness strategy.

### Serverless, short-lived jobs, and peak JIT

A 300 ms CLI task may finish before many hot paths are heavily optimized. In such workloads, **minimizing class loading/bootstrapping** can matter more than C2 peak throughput. That is why “configurations that increase peak throughput” do not automatically help startup.

## 14. Multiple scenarios to distinguish when reporting results

### Scenario 1 — Version A has faster startup but lower peak

Version A is ready after 700 ms and stably handles 2,000 req/s; version B is ready after 1.8 seconds but after warm-up handles 2,500 req/s. If serverless runs for only 4 seconds, A may win on total work; if running for 24 hours with a suitable CPU budget, B may win. There is no universal conclusion without **lifecycle and SLO**.

### Scenario 2 — First request is slow due to lazy class initialization

A class is only loaded/initialized when the `/generate` route is first called. The `/health` readiness probe responds immediately, but the first `/generate` request incurs extra cost. Warm up the right route or measure the cold path separately; do not blame all costs on JIT.

### Scenario 3 — Warm-up input differs from production

During warm-up, 100% of requests use small JSON. Production contains 30% large payloads and multiple receiver types. C2 optimization may favor the old profile, while real workload takes different paths; warming up with 5,000 requests still does not guarantee representativeness.

### Scenario 4 — Nice peak but unsustainable GC/CPU

A 30-second experiment hits 100k ops/s, but after 30 minutes the heap live set grows and Full GC appears. The 30-second peak is not sustainable throughput; a soak test is needed to detect nonstationarity/memory leaks.

### Scenario 5 — C1-only improves the first request

If `TieredStopAtLevel=1` makes the first response faster in one run, you cannot yet conclude the flag is always better. It may reduce initial compilation overhead while making steady peak worse. Run A/B tests multiple times with separate startup and sustained SLOs.

### Scenario 6 — `-Xint` is very slow

This shows that JIT provides benefits for that specific hot kernel; it does not prove that a production cold start is interpreter-only, nor that whole-application speedup equals kernel speedup.

### Scenario 7 — JIT log still shows compilations during steady measurement

A rarely used route may just be warming up, or the runtime may be compensating with recompilation. Check the magnitude and correlation with p99; not every compilation violates steady state, though a large burst may require re-segmenting the window.

### Scenario 8 — CPU quota prolongs warm-up

JIT compiler threads and Java workers compete for a 1 vCPU quota; the instance may take much longer to reach a candidate steady state than in a benchmark on 16 unrestricted cores. Measure under the same container CPU quota and record CPU throttling; `ActiveProcessorCount` does not itself set a cgroup quota.

## 15. Checklist for trustworthy warm-up/peak results

- [ ] Clearly define `process start`, `first useful result`, `ready`, `warm-up end`, `measurement start/end`.
- [ ] Record JDK vendor/build, VM flags, OS, vCPU quota, heap, and memory cap.
- [ ] Do not mix cold startup with steady-state throughput.
- [ ] Representative request mix, object lifetimes, and data shapes.
- [ ] Do not exclude failures/timeouts/dropped requests from latency accounting.
- [ ] Have multiple process forks/repetitions and randomized run order.
- [ ] Have pre-defined warm-up time windows/criteria; do not manually pick the fastest segment.
- [ ] Check JIT compilation/OSR/deoptimization during analysis.
- [ ] Check GC, class loading, pools, caches, external dependencies, and CPU.
- [ ] Distinguish `-Xint` diagnostic from actual cold startup.
- [ ] Use JMH for microbenchmarks, production-like load generator for services.
- [ ] Report achieved vs offered load; avoid coordinated omission.
- [ ] Report p50/p95/p99/p99.9 alongside throughput and resource footprint.
- [ ] Have separate cold-path, warm-up ramp, and long steady-state experiments.
- [ ] Do not conclude from a short JVM with 4 warm-up batches that C2 peak is reached.
- [ ] Label all timing outputs and compilation logs as **environment-dependent**.

## 16. Self-check questions

1. **What is warm-up?** The process where the runtime/application changes state while executing a workload: JIT profiling/compilation, class loading/init, caches, pools, heap/GC, etc.
2. **Is a Java method guaranteed to be at C2 after 10,000 calls?** No; VM policy, JIT tiers, hotness, compiler queues, and flags vary.
3. **Can a very long loop inside a method called only once be JIT-compiled?** Yes; HotSpot can use OSR/backedge hotness.
4. **Is `-Xint` equivalent to the first request of a default JIT JVM?** No; it actively disables JIT.
5. **Do C1 and C2 have the same goal?** Not entirely; C1 compiles faster, while C2 can optimize more deeply at the cost of compilation overhead.
6. **Does compiled code always remain unchanged until process exit?** No; there can be deoptimization, code invalidation, recompilation, and code cache management.
7. **Does successful readiness mean JIT is already at peak?** No.
8. **Is steady state a JVM flag that can be checked once to know?** No; it requires multiple metrics/windows and a workload definition.
9. **Does peak throughput guarantee meeting the request p99 SLO?** No; peak can occur at saturation with bad queueing/latency.
10. **Is a 5-second warm-up guaranteed by the JVM?** No.
11. **Does a silent JIT compilation log prove there is no more JIT?** Not without checking settings and timing.
12. **Is a benchmark containing computations with unused results trustworthy?** No; dead-code elimination can remove the work.
13. **Why use process forks?** So each experiment has a fresh JVM/JIT/heap state.
14. **What does `time java WarmupLab` measure?** Total OS process invocation to exit, including startup + all work in `main` + shutdown/overhead.
15. **Does JMH replace an HTTP end-to-end load test?** No; JMH measures micro-workloads and does not automatically reflect network/queueing/DB.
16. **If route A is warmed up but production hits route B, is JIT representative?** Not necessarily; type/branch/class paths may differ.
17. **Does GC contribute to warm-up?** Yes; live-set/heap occupancy/GC cadence can change.
18. **Is the single `avgBatchMs` number in the lab the p99 request latency?** No, it is only the average duration of the selected batches.
19. **When compiling JDK 17 code with `--release 17` and running on JDK 24, is the runtime JDK 17?** No; the bytecode/API target is 17, while the compiler/runtime VM is still JDK 24.
20. **For a CLI living 0.3 seconds, prioritize startup or C2 peak?** Depends on SLO; startup/total job time is usually more important than peak of a hot method.
21. **Does CDS guarantee C2 peak as soon as a new process runs?** No.
22. **Why is a production-like CPU quota needed?** Compiler threads and app threads compete for resources; warm-up/throughput change with quota.
23. **An app achieves stable p99, but the heap live set keeps growing?** Not yet worthy of being considered long-term steady state; soak testing and leak analysis are needed.
24. **Is a configuration with high throughput that violates memory/CPU/latency budgets a winner?** No; you must look at SLO-constrained sustained performance.

## 17. Standard references and further reading

- Oracle JDK 17 `java` launcher: `-Xint`, `-XX:+PrintCompilation`, `-XX:-TieredCompilation`, `-Xlog`, JFR, and VM flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle — Understanding Java JIT Compilation with JITWatch (C1/C2, tiered compilation, optimization): https://www.oracle.com/technical-resources/articles/java/architect-evans-pt1.html
- OpenJDK HotSpot — JIT compilation policy and compiler infrastructure (JDK source): https://github.com/openjdk/jdk17/tree/master/src/hotspot/share/compiler
- Oracle JDK 17 `jcmd`: compiler diagnostics, JFR, and process introspection: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle JDK 17 `jfr`: inspection of Java Flight Recorder recordings: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Java SE 17 JFR API/module: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html
- Java SE 17 `CompilationMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/CompilationMXBean.html
- OpenJDK Java Microbenchmark Harness (JMH): https://openjdk.org/projects/code-tools/jmh/
- Oracle JDK 17 Garbage Collection Tuning Guide (GC effects, throughput/latency): https://docs.oracle.com/en/java/javase/17/gctuning/

**Technical conclusion:** **Fast startup does not mean high peak performance; high peak performance does not mean steady state; steady state does not mean meeting SLOs**. HotSpot progresses from the interpreter through profiling and tiered JIT, and can OSR, deoptimize, and recompile, while class loading, heap/GC, caches, and dependencies all affect warm-up. Measure **cold process startup, time-to-ready, warm-up ramp, steady-state throughput, and SLO-constrained peak** as clear KPIs, using multiple repetitions, representative workloads, JMH/JFR, and appropriate tracing. Do not treat a single fast batch or a single JIT compilation event as proof of optimal performance.
