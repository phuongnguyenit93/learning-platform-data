# JIT, Warm-Up Time, and Performance Variability

When upgrading Java from an older JDK to a newer JDK, an application may run correctly yet display changed performance profiles: high CPU during the first few minutes, slower first requests than normal, throughput rising gradually over time, an endpoint suddenly slowing down and recovering on its own, or benchmarks yielding different results across runs of the exact same commit. Not every fluctuation is a bug; the Java Virtual Machine (JVM) has multiple mechanisms for adapting to load, especially **Just-In-Time compilation (JIT)**, runtime profiling, recompiling code, and invalidating optimization assumptions when actual conditions change.

In **Java Advance Compatibility Migration**, the question to answer is not just "Is the new JDK faster or slower?". You must distinguish **startup**, **warm-up**, **steady state**, **tail latency**, **CPU/memory cost**, and the influence of the runtime environment. For the same application, comparing only throughput after 30 minutes can miss latency risks during autoscaling. Conversely, measuring only the first 10 seconds can lead to false conclusions about the JDK's long-term processing speed.

This lesson focuses on the HotSpot JVM — a common OpenJDK implementation — using principles applicable more broadly: understanding the JIT contract, designing proper experiments, gathering observable evidence, and making migration decisions based on real workloads. Compiler tier names, flags, and observable events can differ across JVMs/JDKs; always verify against the actual runtime in use.

## 1. Mental Model: Java Code Does Not Run at a "Fixed Speed"

### 1.1. Bytecode and machine code

Java code is typically compiled into bytecode inside `.class` files. When executed by the JVM, a method may:

1. Execute through the interpreter.
2. Be compiled into machine code by the JIT compiler.
3. Be recompiled at higher optimization levels based on actual runtime profiles.
4. Undergo deoptimization and fall back to a less optimized state when assumptions no longer hold.
5. Be recompiled once again when the workload changes.

High-level diagram for HotSpot:

```text
Java source
     |
     v
javac / build tool
     |
     v
Bytecode (.class)
     |
     v
Class loading, verification, linking, initialization
     |
     v
Interpreter + runtime profiling
     |
     +--------> JIT compilation (tiers)
     |               |
     |               v
     |         Optimized native code
     |               |
     |     assumption invalidated?
     |               |
     +<--- deoptimization / uncommon trap
```

This is not a pipeline every method is forced to traverse completely. Some methods are rarely called and never receive high-tier optimization; hot loops are handled by the JIT via **on-stack replacement**; some compiled code stays present without being invoked again.

### 1.2. Benefits and costs of JIT

The JIT can optimize based on data a static compiler does not yet know: which object types actually appear, which branches are taken most often, which methods are called frequently, and whether allocations can be eliminated.

However, the JIT also consumes:

- Compiler thread CPU.
- Memory for compiler data structures and code cache.
- Profiling collection time.
- Deoptimization/recompilation cost if assumptions shift.
- Time before a hot path reaches a stable optimized state.

Therefore, there is a trade-off between **fast startup** and **long-term performance**. A JVM that optimizes less aggressively upfront may use less CPU during warm-up; a JVM that optimizes more deeply may reach higher throughput at the cost of startup resources.

### 1.3. Performance is a vector

When evaluating migration, inspect at minimum:

| Metric | Meaning | Common Misinterpretation |
|---|---|---|
| Startup time | Time for the process/JVM/app to start | Equating process started with service ready |
| Time to readiness | When health/readiness reports it can accept traffic | Does not guarantee JIT has warmed up |
| Time to stable throughput | When processing speed enters a defined stable region | Picking a single fixed warm-up duration for every system |
| Throughput | Requests/operations completed per unit of time | Ignoring errors, timeouts, and result quality |
| Mean latency | Average latency | Can hide very slow requests |
| p95/p99 latency | Tail latency | Needs sufficient samples; watch coordinated omission |
| CPU time/utilization | Processing cost | Both compiler CPU and application CPU contribute |
| Allocation rate | Object creation pressure | Does not directly equal GC pause time |
| GC pauses | Stop-the-world / collector pause characteristics | Not every latency spike comes from GC |
| RSS/native/code cache | Off-heap and process memory | Heap usage is not total memory footprint |

A conclusion that "the new JDK is better" must state better on which metrics and under which conditions.

## 2. Interpreter, C1, C2, and Tiered Compilation

### 2.1. Tiered compilation in HotSpot

HotSpot traditionally uses execution levels under **tiered compilation**. These names and mechanisms are helpful for reading logs, though not a mandatory contract across every JVM implementation.

Common description:

| Level | Mechanism | Typical Purpose |
|---|---|---|
| 0 | Interpreter | Execution and initial observation |
| 1 | C1, little or no profiling | Relatively fast compiled code |
| 2 | C1 with limited profiling | Collects partial runtime information |
| 3 | C1 with fuller profiling | Collects profiles for deep optimization |
| 4 | Heavily optimizing C2 | High-performance optimization for hot code |

In some JDKs/configurations, levels and compiler choices differ. Do not assume every method always compiles sequentially 0 → 1 → 2 → 3 → 4; compiler policy can skip tiers depending on call rate, loop backedges, queues, and profiles.

### 2.2. C1 and C2 play different roles

- **C1** usually focuses on fast compilation and profile collection, suited for the warm-up phase.
- **C2** usually invests heavier effort into hot code, producing more deeply optimized machine code from profiles.
- C2 does not inevitably improve every method; optimization changes sometimes carry trade-offs depending on CPU, workload, and code shape.
- Applications not running HotSpot or using a JVMCI compiler may have different mechanisms; record the actual compiler configuration.

To evaluate, ask whether warm-up finishes before heavy traffic arrives, rather than merely asking "has it compiled with C2 yet?".

### 2.3. How does the JIT decide which methods are worth optimizing?

The JVM can use counters and profiling data such as:

- Method invocation count.
- Loop backedge count (iterations returning to loop start).
- Receiver types at virtual/interface call sites.
- Branch execution frequencies.
- Object types and data access patterns at specific sites.
- Speculation outcomes and inputs supporting compiler heuristics.

A frequently called method often becomes a **hot method**, yet "hot" depends on JVM policy, workload, and the compiler queue, rather than a fixed threshold across all JDKs.

### 2.4. Compiler threads compete with the application for CPU

JIT is not free. During startup or sudden traffic spikes, compiler threads can contend for CPU alongside:

- Request worker threads.
- GC workers.
- Class loading/initialization.
- TLS handshakes, DNS, or network I/O.
- Framework proxy/code generation.
- Logging and telemetry pipelines.

In containers with low CPU quotas, many methods becoming hot at once can create compiler queues or CPU contention that prolongs warm-up. That is why the same artifact may warm up rapidly on a laptop yet slowly inside a CPU-constrained Kubernetes pod.

## 3. On-Stack Replacement (OSR): Hot Loops Do Not Always Wait for Method Exit

### 3.1. A very long-running method

For example:

```java
public static long calculate(long rounds) {
    long total = 0L;

    for (long i = 0; i < rounds; i++) {
        total += i & 31L;
    }

    return total;
}
```

Suppose the method is called exactly once while the loop executes many iterations. If the JIT only acted when the method was invoked again, it could hardly optimize this method while the loop was already in progress.

HotSpot provides **on-stack replacement (OSR)** to transition an actively executing frame from the interpreter or a lower compiled tier to a compiled version at a suitable loop point. Thus a long-running loop can benefit while still executing.

### 3.2. Why does OSR matter when measuring benchmarks?

- A very long loop can switch compiler states mid-measurement.
- The first measurement may include tier-transition cost.
- Iteration counts can alter compiler policy decisions.
- The JIT can eliminate or transform loops while preserving semantics, causing a benchmark that thinks it measures computation to actually measure different code.

Therefore, do not write a manual loop wrapped with `System.nanoTime()` before/after and treat it as a scientific microbenchmark.

### 3.3. OSR does not explain every throughput increase

Throughput can rise when:

- The JIT compiles hot methods.
- Caches, connection pools, or serializers warm up.
- JIT inlining/escape analysis reduces allocations.
- CPU frequency boosts when conditions allow.
- External systems complete lazy initialization.

When investigating, separate compiler events from other factors. Observing throughput climb over time alone does not prove OSR is the cause.

## 4. Speculative Optimization and Deoptimization

### 4.1. The JIT uses profile-based assumptions

Suppose the code:

```java
interface PricingRule {
    long calculate(long base);
}

final class FixedRule implements PricingRule {
    @Override
    public long calculate(long base) {
        return base + 100;
    }
}

final class PercentRule implements PricingRule {
    @Override
    public long calculate(long base) {
        return base + base / 10;
    }
}

long total(PricingRule rule, long base) {
    return rule.calculate(base);
}
```

If during warm-up a call site mostly sees `FixedRule`, the JIT can optimize assuming that receiver type predominates, placing a guard and fallback path when another type arrives.

If production traffic later increases the share of `PercentRule`, the profile is no longer representative. The JVM may take the guard/fallback or perform **deoptimization**, returning to a different execution state and recompiling with updated profile data.

### 4.2. Deoptimization does not automatically mean an error

Deoptimization is a legitimate mechanism of an optimizing JIT. It keeps JVM semantics accurate when an optimization assumption is violated.

However, heavy deoptimization/recompilation under load can cause:

- Latency spikes.
- Higher compiler CPU.
- Temporary throughput drops.
- Machine code replacement or invalidation.
- Repeated execution-tier transitions when workloads shift.

Do not treat **every** deoptimization event as a regression. Care about frequency, timing, affected methods, and SLO impact.

### 4.3. Uncommon traps and skewed workloads

The JIT can heavily optimize the common path while handling rare paths via fallbacks/uncommon traps. If benchmarks exercise only the "happy path" while production sees validation errors, large inputs, or varied data shapes, JIT behavior can differ dramatically.

During migration, test workloads should include:

- Both happy paths and error paths.
- Small and large requests.
- Null, empty, and malformed inputs within contract scope.
- Real implementations of interfaces.
- Clients/tenants with distinct data profiles.
- Infrequently called flows that still carry strict SLOs.

### 4.4. Dynamic class loading affects optimization

Frameworks can generate proxies, subclasses, lambda forms, or new classes after runtime is already underway. When loading a new class alters type-hierarchy assumptions, previously compiled optimizations may need re-evaluation or invalidation.

Do not assume benchmark results from a simple microservice represent an application with a complex class-loader/plugin system. Include code loading, reflection, and dynamic instrumentation in the workload when they occur in practice.

## 5. Inlining: A Major Optimization That Does Not Always Happen

### 5.1. Basic idea

With:

```java
static int addTax(int price) {
    return price + 10;
}

static int checkout(int price) {
    return addTax(price) * 2;
}
```

The JIT can replace the `addTax` call with the method body inside the caller (**inlining**). This reduces call overhead and unlocks further constant folding, elimination, or code motion.

Inlining is not guaranteed for every method. The JIT weighs code size, call frequency, type profiles, recursion, and internal budgets.

### 5.2. Why can a small refactor change performance?

Seemingly minor changes can affect:

- Callee bytecode size.
- Number/type of receivers at the call site.
- Exception paths or branch types.
- Compiled method size.
- Class hierarchy stability.
- The compiler's ability to see through abstractions.

For example, adding a logging or metrics check branch to a small method can affect inlining decisions. Do not conclude the JDK has a regression before comparing workload shapes and compiler behavior.

### 5.3. Do not optimize by assuming "shorter methods are always faster"

Splitting methods into smaller helpers improves readability; the JIT is usually strong enough to inline when beneficial. Still, code organization should prioritize correctness and maintainability.

Consider refactoring for the JIT only based on profiling/benchmark evidence. Never write business code as one giant monolithic method to "reduce calls", as that can hinder compiler optimization and raise maintenance costs.

## 6. Escape Analysis and Allocation Elimination

### 6.1. New objects do not always cause real heap allocation

For example:

```java
record Point(int x, int y) {}

static int distanceSquared(int x, int y) {
    Point point = new Point(x, y);
    return point.x() * point.x() + point.y() * point.y();
}
```

If the JIT proves `point` does not escape in ways affecting semantics, it can eliminate the actual allocation or replace it with scalar values under suitable optimizations.

That explains why counting `new` keywords in source does not directly reflect the runtime allocation rate.

### 6.2. Optimization depends on profiles and code shape

Escape analysis can be affected by:

- Method inlining.
- Call graph complexity.
- Interface/virtual dispatch.
- Objects stored into fields or returned to callers.
- Synchronization and native interactions.
- Compiler tier and JVM flags.

A simple snippet is not optimized identically across all JDKs/architectures. When measuring allocations with microbenchmarks, prevent the compiler from optimizing away the entire computation and observe real allocations with appropriate tools.

### 6.3. Relationship with GC

When the JIT eliminates allocations, GC pressure can drop. Conversely, optimization changes that increase allocations can trigger more GC activity. However, **GC and JIT are two distinct systems**: a GC pause spike does not by itself prove a JIT problem, and an optimized allocation path does not mean GC never needs to run.

When analyzing regressions, inspect compiler events, allocation rate, heap occupancy, GC logs, and the latency timeline together.

## 7. Code Cache and Effects of Too Much Compiled Code

### 7.1. What is the code cache?

The JIT stores compiled native code in a memory region called the **code cache**. HotSpot can partition the code cache into segments for code at different optimization levels and non-method code depending on version/configuration.

In applications with many classes, generated proxies, or hot methods, the code cache can become a notable resource. If space runs out, the JVM may stop compiling additional code as desired or emit related warnings.

### 7.2. Signs worth investigating

- Warnings about the code cache being full or compiler disabled/throttled.
- Throughput failing to reach usual levels after warm-up.
- Unusual compiler activity.
- Applications with vast numbers of dynamically generated classes.
- Code cache utilization climbing up to the configured limit.

Do not tune `ReservedCodeCacheSize` arbitrarily just because the JVM uses substantial native memory. Inspect actual metrics, minimum/maximum bounds, and trade-offs against total RSS/container memory.

### 7.3. The compilation queue also matters

If compiler threads cannot keep up with newly hot methods, some code stays on lower tiers longer than expected. This can appear as startup under load issues, though it does not always mean compiler thread count is too low.

Increasing compiler threads can worsen CPU contention in small pods. Compare the warm-up timeline, compiler CPU, and application latency before changing flags.

## 8. Startup, Readiness, Warm-Up, and Steady State Must Be Measured Separately

### 8.1. Distinct phases

A service can pass through:

```text
Process launch
      |
      v
JVM starts + classes load
      |
      v
Framework / application initializes
      |
      v
Readiness endpoint reports ready
      |
      v
Real traffic begins
      |
      v
Caches warm up + JIT compiles hot paths
      |
      v
Performance reaches defined stable region
```

Readiness usually reflects that the app is ready to receive requests under the operational contract; it does not promise the JIT has reached peak throughput. If readiness waits for full warm-up, startup/rollouts can drag out; if readiness fires too early, user traffic may suffer latency spikes.

### 8.2. Warm-up time has no universal constant

"Warm up for 30 seconds" may suit one microbenchmark yet lacks generality. Warm-up depends on:

- Which code paths are invoked.
- Request frequency and distribution.
- JVM tiered compiler policy.
- CPU quota and compiler thread count.
- Class initialization/bytecode generation.
- Connection pools and DNS/TLS caches.
- GC, heap size, and OS page cache.
- Container/resource throttling.
- Input data profiles.

Therefore, define steady state through **metric observation and statistical criteria** rather than a rigid duration applied to every workload.

### 8.3. Defining stability with windows

For example, a team chooses 60-second windows and tracks throughput, p95 latency, allocation rate, and compiler activity. They might define the stable region as metrics remaining within an acceptable band across multiple consecutive windows.

Specific thresholds are a **workload decision**, not a JVM standard. Avoid convenient definitions where only the prettiest time slice enters the report.

### 8.4. Scale-out and cold pods

In Kubernetes or auto-scaling environments, new pods may receive traffic before hot paths are optimized. If a load balancer spreads traffic evenly, users can see elevated p99 during scale-out even when each pod's steady-state throughput is high.

You must test:

- Idle startup.
- Startup under real load.
- Rolling rollout with gradual traffic shifting.
- Cold autoscaling from low replica counts.
- Failure/restart storms.
- Recovery after eviction.
- Periodic deployments or short-lived scheduled jobs.

JIT warm-up matters especially for serverless/short-lived jobs: a task finishing before deep optimization completes may capture none of the steady-state benefit.

## 9. Cold Performance and Steady-State Performance Can Conflict

### 9.1. Why can a one-dimensional conclusion be wrong?

Suppose two hypothetical configurations:

| State | Configuration A | Configuration B |
|---|---:|---:|
| First request | 180 ms | 120 ms |
| First-minute p95 | 90 ms | 75 ms |
| After 20 minutes p95 | 35 ms | 45 ms |
| Steady throughput | 12,000 req/s | 10,500 req/s |

Numbers are illustrative only. Configuration B suits short workloads and startup, while Configuration A is stronger under sustained load. You cannot pick the "faster version" without knowing deployment patterns and SLOs.

### 9.2. Goals can vary by application type

| Workload Type | Focus That Typically Matters |
|---|---|
| Short CLI running seconds | Startup/cold execution, total elapsed time |
| Multi-hour batch job | Steady throughput, memory/cost |
| Long-lived API server | p95/p99, steady throughput, recovery warm-up |
| Serverless function | Cold starts, short-run latency, request concurrency |
| Streaming service | Sustained throughput, GC/JIT pauses, backpressure |
| Desktop app | Time to interactive, responsiveness |
| Autoscaled microservice | Cold pod behavior + post-stabilization throughput/cost |

Do not tune the JIT for a long-running server and then apply the exact same policy to short-lived batch jobs when real goals conflict.

## 10. Non-JIT Sources of Variability

### 10.1. CPU frequency, turbo boost, and thermal throttling

CPUs scale clock frequency based on temperature, power limits, active core counts, and OS policies. Two benchmarks run at different times can run at different frequencies.

When using shared CI runners, noisy background jobs, or throttling laptops, differences are not necessarily the JVM's fault. For serious measurements, pin a controllable environment and record CPU model, host load, and power policy where relevant.

### 10.2. Scheduler and noisy neighbors

In VMs/containers, processes can be preempted by competing workloads. Kubernetes CPU limits/quotas cause CPU throttling, especially when compiler, application, and GC workers contend for CPU.

Observe:

- Requested vs. limited CPU.
- CPU throttled time/count.
- Core count visible to the container.
- GC/JIT thread counts and application thread pools.
- Node-level contention.
- Cgroup/container runtime version.

If a container has a 1-CPU quota yet the JVM spawns too many background workers based on an unexpected active CPU count, warm-up and latency can degrade. Still, do not manually pin every JVM thread count without checking container awareness and JDK version.

### 10.3. GC, heap, and native memory

Upgrading the JDK can also change default GC/algorithm settings, collector versions, or heap sizing. On the same benchmark, GC pauses, allocation rates, and memory pressure can differ; not all latency shifts can be blamed on the JIT.

Record:

- Active GC and flags.
- Intentional heap min/max, region/generation settings.
- Container memory limit.
- Metaspace, direct buffers, and code cache.
- GC cycle timeline and pause logs.

### 10.4. Class Data Sharing and class initialization

**Class Data Sharing (CDS)** or Application CDS can improve startup/class-metadata components in appropriate cases. However, CDS does not mean every method is already JIT-optimized, nor does it put an application into steady state automatically.

If the app adopts CDS or framework AOT optimizations at the same time as a JDK upgrade, separate startup/class-loading effects from JIT effects.

### 10.5. External systems

Realistic HTTP benchmarks are also affected by:

- DNS caching.
- TLS session/connection reuse.
- Database connection pools.
- SQL plan caches.
- Redis/CDN caches.
- Disk page caches.
- Remote server autoscaling.
- Load balancers.
- Message broker backpressure.

If the first request is slow because of connection pool creation or query planning, the JIT may be only a minor piece. Collect multi-layer timelines and metrics.

## 11. Observing the JIT with HotSpot Tools

### 11.1. `-XX:+PrintCompilation`

A simple way to observe compilation activity on HotSpot builds that support it:

```bash
java -XX:+PrintCompilation -jar app.jar
```

Output usually contains timestamps, compilation IDs, tier/level, method names, and compilation state; exact format depends on JDK version. Certain symbols indicate OSR, made not entrant, or compiled code changes.

This command is primarily for diagnostic environments. Compilation logs can grow large and add overhead; do not enable broadly across all production pods without weighing cost.

### 11.2. Inlining diagnostics

In test environments, HotSpot diagnostic options can be used:

```bash
java \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:+PrintCompilation \
  -XX:+PrintInlining \
  -jar app.jar
```

Depending on JDK/flags, output reports inlining opportunities and why a call was or was not inlined. These flags are implementation-specific and may change or be unsupported on other JVMs.

Do not treat a "not inline" line as a bug. Inlining is a heuristic decision; what matters is workload impact.

### 11.3. Java Flight Recorder (JFR)

JFR records JVM events with configurable overhead. Recording can start at launch:

```bash
java \
  -XX:StartFlightRecording=filename=warmup.jfr,settings=profile \
  -jar app.jar
```

Or use `jcmd` against a running process when permissions and runtime support it:

```bash
jcmd <pid> JFR.start name=warmup settings=profile
jcmd <pid> JFR.dump name=warmup filename=warmup.jfr
jcmd <pid> JFR.stop name=warmup
```

Choose recording settings/duration and event categories to match your goal. JFR can supply CPU, allocation, GC, class loading, and some compilation details depending on JDK/settings. Verify whether specific event types are enabled and supported in the target JDK.

**One JFR recording does not automatically prove causality.** Use it to correlate compilation, safepoints, CPU, and latency timelines.

### 11.4. `jcmd` and CodeCache

Some HotSpot builds expose diagnostic commands to inspect compiler/code-cache state, for example:

```bash
jcmd <pid> help
jcmd <pid> Compiler.codecache
jcmd <pid> Compiler.queue
```

Available commands depend on the JDK/VM build. Always run `jcmd <pid> help` to check rather than relying entirely on examples from another release.

### 11.5. GC and container logs

To distinguish JIT from GC or containers:

```bash
java \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -Xlog:os+container=info \
  -jar app.jar
```

These logs assist investigation but do not replace application metrics or OS/container telemetry. Exact unified logging options can differ across releases; verify on the actual JDK.

### 11.6. Profilers

Async-profiler, Java Mission Control, and other CPU/allocation profiling tools can be helpful. When choosing a tool, verify:

- Does it support the current JDK/OS/architecture?
- Does the sampling engine require perf events/attach permissions?
- Does profiling introduce overhead or perturb the workload?
- Do stack traces retain enough symbols/line info?
- Does it distinguish Java, native, JIT/compiler, and GC threads?

Do not start with long-running production profiling without proper scoping and data policies.

## 12. Proper Microbenchmarking: JMH Instead of Hand-Written Loops

### 12.1. Why does naive `System.nanoTime()` often mislead?

An error-prone example:

```java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    int result = calculate(42);
}

long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

Issues:

- The `result` variable is never observed, so the compiler may eliminate the work.
- `42` is a constant so constant folding can occur.
- JIT warm-up happens inside the measured window.
- Loop optimization differs from production call patterns.
- A single run fails to capture variability.
- GC/OS scheduling can intrude.
- No separate fork isolates prior JVM state.

The outcome may measure compiler optimizations or scheduling rather than the intended business operation cost.

### 12.2. JMH is the benchmark harness for the JVM

**Java Microbenchmark Harness (JMH)** helps manage warm-up iterations, measurement iterations, forks, benchmark modes, and state lifecycles. It does not automatically guarantee the benchmark is meaningful in business terms; input/output design still determines validity.

For example:

```java
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class PricingBenchmark {
    private long base = 1_234_567L;

    @Benchmark
    public void calculateTotal(Blackhole sink) {
        long result = (base * 110L) / 100L;
        sink.consume(result);
    }
}
```

The warm-up/measurement/fork counts are illustrative, not optimal rules for every workload. For very fast benchmarks, consider batching and measurement length; for methods performing network I/O, microbenchmarks cannot substitute for real load tests.

### 12.3. Understanding JMH annotations properly

| Annotation | Role |
|---|---|
| `@Benchmark` | Marks an operation to be benchmarked |
| `@State` | Defines state and sharing scope |
| `@Setup` / `@TearDown` | Prepares/cleans up data at a specified level |
| `@Warmup` | Defines the pre-measurement phase |
| `@Measurement` | Defines the sampling phase |
| `@Fork` | Runs the benchmark in a separate JVM process |
| `@BenchmarkMode` | Throughput, average time, sample time, and other modes |
| `Blackhole` | Ensures result values are consumed, reducing dead-code elimination risk |
| `@Param` | Runs across multiple parameter values to simulate input variation |

Do not use `@Setup(Level.Invocation)` for heavy state setup without understanding its overhead and bias. Setup cost might fall outside the primary metric, causing the benchmark to omit work production genuinely pays for.

### 12.4. How important are forks and warm-up?

Each fork is a separate JVM process, reducing profile/JIT state carryover from other runs. Warm-up iterations give hot code a chance to compile before measurement.

However, warm-up is not a "ritual" that always makes benchmarks better:

- If measuring **cold start**, do not discard the entire initial phase.
- If measuring steady state, prove warm-up has actually completed.
- If the workload shifts phases, a profile built from old inputs may not be representative.
- If a benchmark runs too few forks, results remain sensitive to JVM/host noise.

Report cold behavior and steady-state benchmarks separately instead of using one configuration for both.

## 13. Benchmark Design Traps Around JIT

### 13.1. Constant folding

If inputs do not vary and the entire computation is predictable, the JIT can precompute it. A benchmark feeding constants can perform drastically better than diverse production inputs.

The fix is using appropriate state/parameters while avoiding adding non-business work to the measured operation.

### 13.2. Dead-code elimination

If a result goes unused, the compiler may eliminate the computation. Use `Blackhole` or return values per JMH patterns so the computation affects observable results.

### 13.3. Escape analysis eliminating allocations

A benchmark measuring:

```java
new Point(1, 2);
```

may measure zero heap allocations if the object does not escape and code gets optimized. To measure the cost of genuinely retained objects, design state/output reflecting production object usage.

### 13.4. Loop-in-loop

Putting your own 1-million-iteration loop inside `@Benchmark` lets the compiler optimize the loop itself and yields a profile different from one-call-per-request behavior. JMH already provides a harness to drive iterations; do not add inner loops merely to make "the clock numbers big enough" without justification.

### 13.5. Monomorphic benchmarks differ from polymorphic production

A benchmark exercising only one implementation of an interface may be aggressively inlined; production with many implementations may not get the same optimization. If the system is plugin-based or multi-strategy, benchmark with realistic receiver type distributions.

### 13.6. Single-threaded benchmarks differ from multi-threaded workloads

Code with locks, atomics, concurrent collections, or memory locality behaves differently when used by many threads. JMH supports testing varied thread counts while avoiding turning benchmarks into uncontrolled stress tests.

### 13.7. Network I/O benchmarks must not be confused with pure CPU microbenchmarks

If an operation includes HTTP calls, filesystem access, or database queries:

- Remote service variability can dominate Java code costs.
- Connection pooling and TLS/DNS caching change after warm-up.
- Retries/timeouts reshape latency distributions.
- Benchmarks can generate load that triggers throttling on target servers.

In these cases, integration/load tests with realistic traffic models and telemetry provide more value than standalone microbenchmarks.

## 14. Load Testing: Measuring Real-Application Warm-Up

### 14.1. Traffic scenarios must resemble the target

A test workload should describe:

- Request mix across endpoints.
- Input sizes and distributions.
- Concurrency / arrival rates.
- Cache hit/miss ratios.
- Authentication/authorization overhead.
- DB queries and side effects.
- Error path rates.
- Network topology and connection reuse.
- Autoscaling policies and resource limits.

Sending only GET requests to a health endpoint mostly warms that path rather than all business flows.

### 14.2. Measuring by phase

Example measurement plan:

| Phase | Action | Key Metrics |
|---|---|---|
| T0: start | Launch process/container | Startup CPU, class loading, RSS |
| T1: ready | Readiness reports accepting traffic | Time to readiness, initial p95 |
| T2: ramp | Increase traffic per scenario | Compiler activity, CPU, p99 |
| T3: warm | Hold steady workload | Throughput trend, allocation, GC |
| T4: steady | Meets stability criteria | p50/p95/p99, throughput/cost |
| T5: phase shift | Alter traffic mix/data | Deopt, latency spike, recompilation |
| T6: scale/restart | Add pods or restart | Cold pod recovery, SLO impact |

Do not pick whichever time window looks best afterward and call it steady state. Criteria for selecting phases must be defined before viewing results.

### 14.3. Open-loop and closed-loop load generation

A **closed-loop** client typically sends the next request only after the prior one completes. When the server slows down, send rate drops, making latency appear healthier than real user impact under fixed arrival load.

An **open-loop** load generator driven by arrival-rate schedules helps reveal queueing and tail latency when servers slow down, provided it has enough capacity and tracks failed/dropped requests clearly.

Know which pattern your real workload follows and avoid **coordinated omission** in measurements. Never drop timed-out/failed requests when computing throughput or latency without reporting failure rates.

### 14.4. Correlating app metrics and JVM events

Align by timestamp:

```text
Time 00:00 — JVM/application start
Time 00:15 — Readiness = true
Time 00:18 — Load starts; p99 = 400 ms
Time 00:35 — High compiler CPU; many methods compiled
Time 01:20 — p99 = 90 ms; throughput stable
Time 03:00 — Traffic mix changes
Time 03:05 — Short p99 spike + deoptimization events
Time 03:40 — Stable again
```

Numbers are illustrative. Data is meaningful only when timestamps across load generators, JVM/JFR, container metrics, and server tracing are synchronized closely enough for comparison.

## 15. Comparing Old and New JDKs Fairly

### 15.1. One run is not enough

JIT compilation can make metrics vary across process launches due to scheduling, compiler queues, GC, heap layout, and workload timing.

A serious benchmark requires:

1. Running multiple forks/processes.
2. Separating warm-up from measurement when targeting steady state.
3. Recording result distributions, not just single averages.
4. Using confidence intervals or appropriate noise evaluation methods.
5. Running on low-noise environments and balancing A/B order.
6. Saving benchmark code, inputs, and JVM flags.
7. Claiming improvement only when differences clearly exceed noise.

There is no fixed repetition count right for every test. Small effects need more measurements; large, consistent effects confirm faster.

### 15.2. Controlling variables

| Variable | What to Pin or Record |
|---|---|
| Application artifact | Same commit/JAR when isolating JDK |
| Dependency versions | Locked and graphed consistently |
| JDK | Vendor, major, update, build |
| JVM flags | Heap, GC, JIT, logging, native access |
| OS/container | Kernel, image, cgroups, CPU/memory limits |
| Hardware | CPU model, architecture, frequency policy |
| Dataset | Size, distribution, warm/cold cache |
| Traffic | Concurrency, arrival rate, request mix |
| Backend | DB/Redis/network versions/load |
| Measurement | Duration, repetitions, failures, metric definitions |

If changing JDK along with framework/GC/container image, that is a **full-stack comparison**. Do not attribute all differences to the JDK's JIT.

### 15.3. Analyzing results via distributions

For latency, report medians, p95/p99, and sample counts. For throughput, report means/medians across multiple trials along with variability. A 1–2% difference may lie within shared runner noise; a consistent 20% difference across machines warrants deeper investigation.

Do not set a CI gate "fail if throughput drops 1%" when baseline noise already swings ±5%. Set thresholds based on risk, statistics, and false-positive costs.

### 15.4. Explaining cold vs. steady honestly

Reports should contain two independent conclusions, for example:

- "The target JDK has higher p99 during the first 2 minutes on autoscale than baseline."
- "The target JDK achieves higher steady-state throughput at the same CPU limit."

This is not a contradiction. The system may need a warm-up strategy or revised resource budget rather than rolling back the entire JDK.

## 16. JVM Flags Affecting JIT: Understand Them, Do Not Overuse Them

### 16.1. Keep defaults as baseline first

HotSpot provides many compiler and optimization flags. Flags like `-XX:-TieredCompilation` or `-Xint` can deeply alter runtime behavior.

Do not start migration by copying a list of "JVM performance tuning flags" from old blogs. First measure with defaults supported by the target JDK, then test individual flags backed by hypotheses.

### 16.2. Several important flags

| Flag | General Meaning | Caution |
|---|---|---|
| `-Xint` | Interpreter-only mode | Mainly diagnostic; throughput can be very low |
| `-XX:-TieredCompilation` | Disables tiered compilation in HotSpot builds supporting it | Changes warm-up and steady state in non-obvious ways |
| `-XX:TieredStopAtLevel=1` | Caps optimization tier in HotSpot | May help startup on some workloads while hurting long-term throughput |
| `-XX:+PrintCompilation` | Prints compilation events | Logging overhead; format varies by release |
| `-XX:+PrintInlining` | Diagnostic inlining output | Investigation only; requires unlocking diagnostics |
| `-XX:ReservedCodeCacheSize=...` | Limits code cache size | Trades off native memory vs. compilation capacity |
| `-XX:CICompilerCount=...` | Compiler thread count in supporting VMs | Raising threads can trigger CPU contention |
| `-XX:ActiveProcessorCount=...` | Overrides CPU count the JVM uses for multiple policies | Affects many subsystems beyond JIT |

Flag names, defaults, and supported/diagnostic/experimental status can change. Use:

```bash
java -XX:+PrintFlagsFinal -version
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintFlagsFinal -version
```

where appropriate to view flags on the actual runtime. Do not treat output from another JDK as proof for production runtime.

### 16.3. `-Xint` isolates issues within limits

Running interpreter-only can help check whether a runtime bug relates to optimization. If behavior differs between interpreted and compiled execution, that signals deeper investigation is needed, yet **does not suffice to prove a JIT bug** because timing, concurrency, and performance shift dramatically.

Do not use `-Xint` as a production performance workaround. If suspecting a compiler bug, build a minimal reproducer, collect logs, and file an issue with the vendor/JDK through official channels.

### 16.4. Capping JIT tiers to optimize startup

Some short workloads may test capping tiers to cut compilation costs. Yet for continuous long-lived services, this choice can reduce steady throughput or raise CPU/request.

Adjust only after calculating **total work cost** and both cold and steady SLOs. Do not shave off a few initial seconds while raising monthly operating costs.

### 16.5. JVM flags can disappear when upgrading the JDK

Some flags formerly used to force compiler or GC behavior are no longer supported, changed defaults, or were removed. If startup scripts keep old flags, a newer JDK may warn or refuse to start.

Inventory actual flags across:

- Container commands and environment variables.
- Helm/Kubernetes manifests.
- CI scripts.
- `JAVA_TOOL_OPTIONS` and `JDK_JAVA_OPTIONS`.
- Application server startup files.
- Test task JVM args.
- Java agents and instrumentation tooling.

Any flag whose meaning changed must be verified rather than kept simply because it sat in a runbook from years ago.

## 17. JDK 17 → 21: What Should You Expect?

### 17.1. No uniform performance guarantee

HotSpot can change compiler heuristics, intrinsics, code generation, GC integrations, and CPU-specific optimizations across JDK releases/updates. One application may run faster in section A yet slower in section B.

There is no general rule that "Java 21 is x% faster than Java 17" across all workloads. Published external benchmarks do not replace testing your system's workload.

### 17.2. Pin JDK updates/vendors tightly

Comparisons must record:

```text
Baseline:
  JDK vendor: ...
  JDK version/build: 17.x ...
  CPU/OS/container: ...
  Heap/GC/flags: ...

Target:
  JDK vendor: ...
  JDK version/build: 21.x ...
  CPU/OS/container: ...
  Heap/GC/flags: ...
```

If vendors differ, results may reflect distinct build patches or settings. You may need baseline/target runs from the same vendor to isolate the effect.

### 17.3. Virtual threads do not automatically make JIT optimize code faster

JDK 21 introduces virtual threads (JEP 444) for concurrency in blocking workflows. If an application adopts virtual threads, workloads may increase concurrent tasks and change CPU/GC/network pressure.

That is a **concurrency architecture change**, not merely a JIT version change. When measuring, distinguish:

- Upgrading the JDK while keeping the old threading model.
- Upgrading the JDK and switching executors to virtual threads.
- Upgrading frameworks/drivers simultaneously.
- Raising concurrency to the point of saturating backend resources.

If p99 increases after switching to virtual threads, the cause could be higher concurrent request volume, pinning in JDK 21-specific cases, or missing backpressure — not necessarily slower JIT code generation.

### 17.4. Preview/incubator features and JIT

If new source uses vector APIs or foreign-memory/native code whose APIs differ across JDKs, benchmarks must account for feature flags, CPU instructions, and JDK generation. Do not draw general conclusions about HotSpot performance from workloads using preview APIs or native libraries absent on older releases.

## 18. CPU Architecture, Intrinsics, and the JVM Compiler

### 18.1. Same bytecode, different machine code

The JIT emits code for the actual CPU architecture and can leverage matching hardware capabilities/intrinsics. Therefore, the same JAR can perform differently across:

- x86-64 and ARM64.
- Older vs. newer CPU generations.
- Instruction set support.
- Bare-metal servers vs. VMs.
- Containers with differing CPU quotas.
- Hosts with different microcode/kernel updates.

Do not compare Java 17 on an x86-64 host with Java 21 on ARM64 and attribute the entire difference to the JDK version.

### 18.2. Intrinsics are not always selected

Some library methods have JVM intrinsic implementations in certain configurations. The JIT can replace calls with specialized machine instructions when conditions match, depending on JVM version, CPU features, flags, and call shapes.

Even when a new JDK adds an intrinsic, overall application throughput improves noticeably only if the workload exercises that path frequently enough. Profile to identify actual hot methods.

### 18.3. Branch prediction and memory locality

One cache miss or branch misprediction can cost more than many arithmetic instructions. Changes in object layout, allocation patterns, or code generation after migration can affect hardware-level behavior.

If a significant performance regression appears without major changes in JIT events, hardware performance counters/profiling per environment policy may be required. Never deduce microarchitectural root causes solely from a benchmark summary table.

## 19. When Warm-Up Causes Problems in Production

### 19.1. Cold pods receiving traffic before performance readiness

A pod reporting readiness early and immediately taking the same traffic share as hot pods can spike tail latency. Design an appropriate ingress/ramp model:

- Admit traffic only once dependency health suffices.
- Ramp traffic gradually if the load balancer supports it.
- Avoid probes that trigger code paths with side effects.
- Pre-initialize well-known heavy components.
- Warm up with representative workloads in staging/canary if proven effective.
- Measure time-to-SLO rather than time-to-readiness alone.

Proactive warm-up must not send business requests that mutate real data or incur unexpected heavy costs.

### 19.2. A warm-up endpoint cannot warm every path

A `/warmup` endpoint calling a few methods does not guarantee every branch, receiver type, and data size compiles identically to production. It can also create a skewed profile, triggering deoptimizations when real traffic arrives.

If warm-up adds value, identify critical paths, request distributions, safe inputs, and appropriate load levels. Compare cold SLOs with/without warm-up across multiple rollouts.

### 19.3. Bounded synthetic-traffic warm-up

One strategy is sending synthetic traffic to canaries/pods before user traffic. Consider:

- Authentication/authorization and test data.
- Avoiding side effects or using rolled-back transaction environments.
- Not warming caches with data far removed from production.
- Not distorting rate limits, audits, or observability.
- Not overloading backends beyond capacity.
- Setting warm-up timeouts and bounds.
- Having a fail-safe if warm-up does not finish.

Never let a warm-up step block deployments indefinitely.

### 19.4. Short-lived jobs may need different optimizations

A CLI running 5–10 seconds may not benefit from C2 compilation because startup/compile time makes up a large fraction. A better strategy may be trimming unnecessary class loading, dependency initialization, JVM memory footprint, or process launch frequency.

You can test startup-oriented flags or a long-lived worker architecture when business requirements justify it. Do not treat those options as mandatory tuning for every service.

## 20. Workflow for Investigating a Suspected JIT Regression

### Step 1: Describe the symptom with metrics

Instead of "JDK 21 is slow", write:

```text
On JDK 17 baseline:
  p99 checkout latency at 300 req/s: 80 ms after 10 min
On JDK 21 target:
  p99 checkout latency at 300 req/s: 130 ms after 10 min
Errors: both < 0.1%
CPU quota: 2 cores; memory limit: 2 GiB
```

Numbers are examples, not real measurements. Record warm/steady timestamps, workload mix, sample counts, and JDK build.

### Step 2: Isolate changes

Run the exact same application artifact, dependencies, flags, OS/container, and load generator where possible; vary only the JDK. If impossible due to bytecode/API compatibility, document all differences and design a fairer comparison.

### Step 3: Inspect timelines instead of a single endpoint

Collect p95/p99, throughput, CPU, allocation, GC, class loading, and JIT compilation window by window. Check whether the regression occurs:

- Only at startup?
- During traffic phase shifts?
- During GC cycles?
- When the compiler queue grows?
- After the code cache nears capacity?
- Only on one CPU model?
- Only when the container experiences throttling?

### Step 4: Build a small reproducer if a hot path is suspected

Use a profiler to identify methods/operations dominating CPU or allocations, then write a JMH benchmark matching data distributions. Never benchmark by stripping a method of all its dependencies if performance depends on real dispatch/inlining.

### Step 5: Inspect compiler evidence

Use `PrintCompilation`, JFR, or appropriate diagnostics to inspect tiers, compilation, code cache, deoptimization, and inlining when needed. This evidence supports hypotheses; it does not prove root cause on its own.

### Step 6: Separate JIT from GC/OS/backend

Run controlled experiments:

- Same JVM with reduced external I/O to isolate CPU paths.
- Same workload on a quieter host.
- Compare GC timelines.
- Check CPU throttling/frequency.
- Check database/remote service latency.

If the regression disappears when changing OS/container, investigate that layer before blaming the compiler.

### Step 7: Fix at the right layer

Solutions may include:

- Updating a dependency/tool that does not yet support the new JDK.
- Fixing allocations, caches, or input data structures.
- Adjusting startup/ramp/pool sizes.
- Changing code shape backed by profiling evidence.
- Tuning JVM flags in a controlled manner.
- Moving to a JDK update containing a vendor-verified fix.
- Temporarily staying on the older JDK until safe mitigations exist.

Never fix by permanently disabling the JIT or keeping unsupported internal flags.

### Step 8: Regression test and close the issue

After fixing, re-run load/microbenchmarks across multiple trials, compare results, and close with evidence: commits, JDK builds, flags, graphs, JFR snapshots, benchmark inputs, and rollout conditions.

## 21. Setting Up CI Performance Gates Without Generating Useless Noise

### 21.1. Layered testing

| CI Layer | Goal | Appropriate Frequency |
|---|---|---|
| Unit + functional tests | Correctness, API compatibility | Every PR/commit |
| Smoke performance | Catch major regressions | Critical PRs or nightly |
| JMH microbenchmarks | Relatively isolated hot paths | Nightly/on-demand per change |
| Controlled load tests | Warm-up, throughput, p95/p99 | Release candidates/nightly |
| Production canary | SLOs, resource cost, real traffic | Every risky rollout |

Long load tests need not run on every PR if cost is prohibitive. However, if a JDK migration is a major change, run at least one controlled measurement round before release.

### 21.2. Thresholds must reflect noise

Suppose benchmark throughput fluctuates ±4% across repeated runs on a dedicated runner. A gate failing on a 1% drop will trigger constant false alarms.

Define:

- Baseline distribution.
- Minimum detectable regression worth acting on.
- Trial/fork counts.
- Outlier handling rules.
- Appropriate confidence/statistical methods.
- When manual investigation is required.

Never cherry-pick the best trial. Likewise, never discard every outlier if outliers reflect real tail latency experienced by customers.

### 21.3. Performance data needs provenance

Each result should store:

```yaml
benchmark:
  name: checkout-hot-path
  revision: <git-commit>
  tool: JMH
runtime:
  jdk_vendor: <vendor>
  jdk_version: <major-update-build>
  os_arch: <os-arch>
  container_cpu_limit: <cpu-limit>
  heap: <heap-configuration>
  gc: <collector>
measurement:
  forks: 3
  warmup_iterations: 5
  measurement_iterations: 8
  metric: avg-time
  units: ns/op
```

Replace placeholders with real values. Metadata makes results interpretable months later and separates code regressions from test-infrastructure changes.

## 22. Common Mistakes When Evaluating JIT and Warm-Up

| Misconception | Why It Is Wrong | Proper Approach |
|---|---|---|
| "Java methods run at fixed speed from call one" | JVM uses interpreter, tiered compilation, and profiling | Measure cold, warm-up, and steady separately |
| "Newer JDK is guaranteed faster on every workload" | Optimizations depend on code, CPU, JDK update, and config | Benchmark real workloads |
| "Readiness=true means JIT is warm" | Readiness and steady performance differ | Measure time-to-SLO |
| "Warm-up is always 30 seconds" | Depends on workload, tiers, and resources | Determine via metrics |
| "Higher p99 means a JIT bug" | Can stem from GC, throttling, TLS, DB, OS scheduler | Correlate timelines |
| "One System.nanoTime loop is a good enough benchmark" | JIT optimizations/noise distort results | Use JMH with multiple forks |
| "JMH guarantees meaningful benchmarks automatically" | Inputs, state, and outputs can still be flawed | Design to reflect production |
| "new in source always allocates on heap" | Escape analysis/scalar replacement | Inspect real allocations |
| "All virtual calls are slow" | JIT applies type profiling/inlining | Profile real call sites |
| "Deoptimization is a bug" | Mechanism preserving JIT correctness | Evaluate frequency/impact |
| "-Xint fixes performance bugs" | Interpreter-only drastically reduces throughput | Use only for controlled diagnostics |
| "Adding compiler threads always helps" | Can worsen CPU contention | Measure queue and CPU quota |
| "Enabling CDS means code is JIT-optimized" | CDS and JIT operate at different layers | Measure startup and compilation separately |
| "100% CPU means max app work done" | Could be compiler/GC/OS contention | Break down CPU by thread/subsystem |
| "Higher req/s is always better" | Errors/timeouts or p99 may worsen | Report throughput alongside SLOs |
| "Local app benchmarks represent cloud pods" | CPU/OS/container/quota differ | Test in equivalent environments |
| "One measurement after 20 minutes suffices" | Misses autoscaling, cold starts, phase shifts | Measure multiple phases |
| "Same bytecode means same performance" | JIT, CPU, GC, and runtime policies differ | Control variables and test |

## 23. Real-World Scenario: Upgrading JDK 17 to 21 for an API Service

Suppose an order-processing service has:

- 8 replicas running HotSpot JVM.
- Java 17 application targeting Java 21.
- 2-core CPU limit per pod.
- HTTP server, JSON serializer, JDBC pool, and Redis client.
- Regular traffic with occasional pod autoscaling.
- SLO: p99 stays within the business threshold at target throughput.

### 23.1. Baseline on JDK 17

Before migration, the team saves:

- Image checksum, JDK vendor/build, JVM flags.
- Dependency graph and framework version.
- p50/p95/p99, throughput, and error rate over time.
- CPU throttling, GC, heap, and allocations.
- Time to readiness and time to stable p99.
- Startup traces/JFR on several test pods.
- Hot code paths from CPU profiles.

### 23.2. Measuring JDK 21 with the application unchanged

If the same artifact and dependency stack can be used, run on JDK 21 in an identical environment to isolate the runtime delta. If framework upgrades are required, record them as a separate change and run an additional full-stack comparison.

### 23.3. Warm-up scenario

Start fresh pods, wait for readiness, and apply a controlled traffic ramp. Collect per-window metrics and record compilation/GC events. Once stabilized, shift to a traffic mix with more order lines to test profile shifts.

### 23.4. A hypothetical result

Suppose JDK 21 improves steady throughput yet degrades p99 during the first three minutes. Before changing flags:

1. Check for corresponding compiler CPU spikes.
2. Check connection pool and JSON serializer lazy initialization.
3. Check CPU throttling when compiler/GC and request threads contend under load.
4. Try an appropriate traffic ramp and compare tail latency.
5. If needed, test individual JIT policy flags via A/B experiments.
6. Ensure steady-state throughput is not overly sacrificed.
7. Choose rollout based on actual SLOs rather than a single favorable metric.

### 23.5. During canary

Route a slice of traffic to JDK 21 and monitor:

- New/old p99 under matching request mixes.
- Errors/timeouts/HTTP statuses.
- CPU/request and cost/throughput.
- Container CPU throttling.
- GC/logging overhead.
- New pod time-to-SLO.
- Memory RSS/code cache where relevant.

If predefined thresholds are breached, roll back according to plan. Never add JVM flags ad hoc in production and treat the result as verified evidence.

## 24. Real-World Scenario: A Batch Job Running Only 20 Seconds

A CLI program processing a small file and exiting after 20 seconds may spend a substantial share of its time on:

1. JVM bootstrap.
2. Class loading and initialization.
3. Framework DI/config setup.
4. File opening/parsing.
5. JIT compiler activity.
6. Actual computation.
7. Shutdown/cleanup.

For this job, steady-state JMH throughput may matter far less than **total elapsed time**. The team must benchmark from process start to exit, measure cold filesystem/cache conditions, and inspect which components dominate runtime.

Optimizations worth considering may include:

- Trimming unnecessary framework initialization.
- Reducing dependencies/class loading.
- Batching operations to avoid launching the JVM repeatedly.
- Testing startup-oriented JVM settings.
- Evaluating class data sharing or suitable build strategies.
- Switching to a long-running worker if business requirements allow.

Do not conclude "C2 is slow" just because the job is short; compare actual compilation cost against initialization/I/O.

## 25. Verification Dossier and Handover

A JDK migration attentive to JIT/warm-up should include:

1. **Runtime matrix:** vendor, update/build, JDK flags, GC, CPU architecture, OS/container.
2. **Workload contract:** request mix, dataset, arrival/concurrency, SLO, error threshold.
3. **Cold metrics:** startup, readiness, first request, time-to-SLO.
4. **Warm-up evidence:** throughput/latency timeline, compiler activity, allocation/GC.
5. **Steady-state evidence:** repeated trials, throughput, CPU cost, p95/p99.
6. **Phase-shift evidence:** shifting input distributions, request mixes, autoscale/canary.
7. **JIT diagnostics:** JFR/PrintCompilation/code cache when backed by hypotheses.
8. **Confounding factors:** CPU throttling, container quotas, DNS/TLS, caches, and DB.
9. **Microbenchmark report:** JMH version/config, forks, input distributions, raw results.
10. **Regression decision:** concrete metric improvements or regressions with appropriate confidence levels.
11. **Mitigation:** code changes, runtime flags, rollout ramps, resource budgets, or JDK updates.
12. **Release/rollback:** owner, threshold, image/artifact checksums, dashboards, and runbook.

### Pre-Release Checklist

- [ ] Measured startup, readiness, warm-up, and steady state separately.
- [ ] Defined realistic workloads, request mixes, and input distributions.
- [ ] Recorded JDK vendor, update, CPU/OS, container limits, and JVM flags.
- [ ] Checked tiered compilation/C1/C2/OSR for the actual implementation where needed.
- [ ] Checked compiler CPU/queues and code cache when related signs appeared.
- [ ] Distinguished JIT from GC, class initialization, and external systems.
- [ ] Observed p95/p99 and error rates, not just average throughput.
- [ ] Tested cold pods/autoscaling and phase-shift traffic.
- [ ] Avoided dead-code elimination, constant folding, and flawed benchmark loops.
- [ ] Used JMH properly for CPU hot paths requiring microbenchmarks.
- [ ] Ran multiple forks/trials and assessed result variability.
- [ ] Controlled dependency/framework/image differences between old and new JDKs.
- [ ] Tested the final artifact on target runtime/hardware.
- [ ] Reviewed JIT flags based on evidence rather than blindly copying old flags.
- [ ] Defined readiness/ramp strategies without causing side effects.
- [ ] Stored reproducible metrics/traces/profiles and results.
- [ ] Prepared SLO-based rollout/rollback triggers.

**Conclusion:** The JIT is an adaptive optimization system at runtime; it can make the same Java code run progressively faster, switch tiers when workloads shift phase, or consume CPU to compile. Therefore, **warm-up and performance variability are phenomena that must be measured in Java compatibility migration**, not noise to ignore. Rather than asking which JDK is "faster" in absolute terms, define the workload, measure cold and steady state separately, observe JIT alongside GC/OS/containers, use controlled benchmarks, and decide based on SLOs and real operating costs.
