# Comparing Functional Results, Load, GC, and Memory Usage When Upgrading to Java 17

When upgrading an application to Java 17, starting cleanly without exceptions is not enough to declare the upgrade successful. You must prove that **business results remain correct**, the application sustains the same load, response times stay within targets, and memory usage and garbage collection (GC) introduce no new risks.

A reliable comparison runs the current version (baseline) and the Java 17 version (candidate) under comparable conditions: identical workload, data, application configuration, CPU/memory limits, dependent services, and measurement methodology. Then analyze four categories separately:

1. **Functionality:** do outputs, side effects, errors, and business behavior remain equivalent?
2. **Load and performance:** how do throughput, latency, error rate, CPU, and load capacity change?
3. **GC:** what are the frequency, pause times, allocation rate, and heap stability?
4. **Memory:** how do heap, RSS, metaspace, direct memory, thread stacks, and total container memory change?

Never collapse these categories into a single conclusion like "Java 17 is faster." Higher throughput paired with worse p99 latency, or lower heap usage paired with higher RSS from native memory, must be analyzed metric by metric.

## 1. Define targets and baseline before upgrading

Before testing, record the current version, target version, and operating conditions. The baseline captures metrics from the current application in a known environment; the candidate is the same application running on Java 17.

Minimum information to record:

| Category | What to record |
|---|---|
| Application | Service name, version, commit, artifact checksum |
| Baseline Java | Vendor, runtime version, VM version, architecture |
| Candidate Java | JDK 17 vendor, patch/build, VM version, architecture |
| Operating system | Distribution/build, kernel, CPU architecture |
| Hardware | CPU model, core/logical processor count, RAM |
| Container | CPU quota, memory limit, cgroup version |
| JVM | Xms, Xmx, collector, JVM flags, system properties |
| Application | Thread pools, connection pools, caches, timeouts, feature flags |
| Dependent services | Databases, brokers, HTTP services, and versions |
| Workload | Request mix, target throughput, concurrency, payloads |
| Timing | Warm-up duration, steady-state duration, sampling windows |

### 1.1. Compare the two runtimes fairly

If your goal is to isolate the effect of changing the runtime, keep source code and application logic identical across both runs. When the same artifact can run on both the old runtime and Java 17, doing so isolates JVM impact cleanly.

If the application must be rebuilt to target Java 17 APIs, record build changes separately from runtime changes. Never bundle dependency upgrades, code edits, config changes, and a JDK switch into one measurement run and attribute the entire delta to Java 17.

Explicitly record:

- The JDK used to compile.
- The JDK actually used at runtime.
- Whether the exact same artifact was used in both runs.
- Which dependencies or configurations changed.
- Whether any agents, profilers, or instrumentation were enabled or disabled.

### 1.2. Separate two distinct questions

Two comparisons are useful:

**Controlled comparison:** hold heap size, collector, JVM flags, workload, and resource limits constant to measure the impact of the new runtime. This experiment isolates root causes.

**Production-config comparison:** run each version with the configuration it will actually use in production. Default settings differ across JDKs; this test reflects operational behavior rather than isolating JVM-only code differences.

Perform both when a full upgrade evaluation is needed. Never interpret results from the second experiment as a pure JVM runtime benchmark.

## 2. Standardize the measurement environment

A benchmark is meaningful only when variables outside the variable under test are controlled.

### 2.1. Keep hardware and resource limits identical

Ideally run baseline and candidate on the same host or identical machines. In containers, keep identical:

- CPU requests/quotas and CPU limits.
- Memory requests/limits.
- Replica counts and request routing.
- Storage class, mounts, and network paths.
- Autoscaling rules.
- Process user and permissions.

Never compare a run on a 16-core host against an 8-core host simply by scaling CPU percentages. Record CPU model, quotas, and throttling to interpret results accurately.

### 2.2. Control dependent services

Databases, message brokers, caches, and HTTP services can skew JVM measurements. Keep service versions/configs, datasets or snapshots, index/schema/cache states, network paths, pool sizes, timeouts, and retry policies as consistent as possible.

If the database is heavily loaded during the candidate run yet idle during the baseline run, latency differences cannot be attributed to Java.

### 2.3. Normalize time and system environment

Record timezone, locale, charset, environment variables, and system properties affecting the application.

Specifically, Java 17 does not enforce UTF-8 as the default across all environments under JEP 400 (that change belongs to Java 18). Default charsets in Java 17 can still depend on the platform. When processing files or text, specify explicit charsets such as `StandardCharsets.UTF_8` and feed identical input data in both comparisons.

Do not simultaneously alter timezone, locale, charset, database collation, or test datasets between runs.

## 3. Compare functional results

Functional verification answers: given identical inputs and initial state, does Java 17 produce the exact contracted outputs and side effects?

Do not compare only logs or whether a job finishes. Compare outputs and state observed by users and downstream systems.

### 3.1. Define the contracts to preserve

For every critical business flow, record inputs and preconditions, return values/HTTP status codes, database mutations, emitted events/messages, generated files/artifacts, exceptions and error handling, and ordering or consistency guarantees where contracted.

Example:

| Scenario | Expected result | Verification method |
|---|---|---|
| Create valid invoice | Returns invoice and persists expected fields | Compare response and database rows |
| Duplicate invoice code | Rejected per contract | Compare status/error code and verify no extra rows |
| Import UTF-8 file | Reads all characters accurately | Compare persisted text after import |
| Database timeout | Returns controlled failure | Compare timeout, retry, and transaction rollback |
| Emit event | Event matches schema and count | Inspect broker or event store |

### 3.2. Use identical inputs and initial state

Use fixtures or snapshots so both runtimes receive identical inputs. For time-sensitive logic, use a mock clock or fixed test time if supported.

When outputs contain non-deterministic fields such as timestamps, UUIDs, or uncontracted collection ordering, normalize those fields before diffing. Never strip out business-significant differences merely to force a test to pass.

### 3.3. Compare across multiple test layers

- **Unit tests:** verify business rules and boundary cases.
- **Integration tests:** verify databases, files, network I/O, serialization, and transactions.
- **Contract tests:** verify APIs, message schemas, and integration with dependent services.
- **End-to-end tests:** verify complete user journeys.
- **Regression tests:** re-run historical edge cases that failed on earlier runtimes.

Never rely solely on unit tests to conclude a runtime upgrade leaves integration behavior intact.

### 3.4. Verify data and serialization compatibility

If the application stores or exchanges Java-serialized objects, verify reading data produced by the prior version and compatibility with active contracts. Java serialization has strict compatibility rules; successful compilation does not guarantee old payloads deserialize cleanly.

For JSON, XML, CSV, and text files, compare charset/byte encoding, null/missing-field rules, numeric types/precision/rounding, date/time/timezone formatting, field ordering if consumers depend on it, schema versions, and default values.

Java 17 still has a platform-dependent default charset. Use explicit charsets to prevent divergence between Linux, Windows, and deployment environments.

### 3.5. Verify reflection and module access behavior

When upgrading applications or libraries using reflection, test accesses to internal packages, private fields/methods, and JDK internal APIs. Module encapsulation may block accesses that worked in older runtimes or require explicit configuration.

Capture errors such as `IllegalAccessException`, `InaccessibleObjectException`, and framework startup failures. Never treat broad package-opening flags as a default fix; pinpoint the exact packages and modules requiring access.

### 3.6. Define functional pass/fail criteria

A scenario passes only when business outputs match, side effects match in count and content, no corrupted data or leaked transactions occur, exceptions and error responses satisfy contracts, and no regressions appear in related flows.

Archive comparison outputs by scenario ID so every result traces back to its exact inputs and run environment.

## 4. Compare load and performance

Performance is never a single number. Inspect throughput, latency, error rate, CPU, queues, and saturation together.

### 4.1. Key metrics

| Metric | Meaning | Usage |
|---|---|---|
| Throughput | Requests/operations completed per second | Measure processing capacity |
| p50 latency | Median request response time | Typical user experience |
| p95 latency | 95% of requests finish within this time | Monitor tail latency |
| p99 latency | 99% of requests finish within this time | Spot worst-case slow requests |
| Error rate | Fraction of failed/timed-out requests | Ensure higher throughput is not from fast failures |
| CPU utilization | Percentage of CPU used | Identify CPU bottlenecks |
| CPU time per operation | CPU consumed per successful operation | Compare computational efficiency |
| Queue depth | Pending work items | Detect backlogs |
| Rejection rate | Fraction of rejected tasks | Detect pool or system saturation |

Never declare the new runtime better solely because throughput rose. If error rate or p99 climbed sharply, the system may be processing more requests at worse reliability and user experience.

### 4.2. Use identical workloads

Document the load profile:

```text
Warm-up: 3 minutes
Steady load: 15 minutes
Burst: 60 seconds
Target request rate: 250 requests/second
Concurrency: 200
Request mix:
  70% read
  20% update
  10% report
Payload:
  median 4 KB
  p95 80 KB
Metrics:
  throughput
  p50 / p95 / p99
  error rate
  CPU
  queue depth
```

Use identical request mix, data, warm-up duration, and load generation strategy for both baseline and candidate. If workloads include randomness, fix seeds or record input distributions.

### 4.3. Warm-up and JIT compilation

The JVM includes a JIT compiler that optimizes hot code based on runtime profiles. Measurements during the first seconds after startup differ substantially from steady state.

A standard measurement sequence:

1. Start a fresh process.
2. Execute warm-up so class loading, JIT compilation, and caches stabilize.
3. Run steady-state load for the defined window.
4. Run a burst phase if evaluating spike absorption.
5. Record metrics separately per phase.
6. Stop the process and repeat with a fresh JVM.

Never mix warm-up metrics into steady-state data when comparing steady performance. If startup time is also a target, measure time from process launch to genuine readiness separately.

### 4.4. Run multiple iterations and examine distributions

Execute each configuration across multiple independent runs. Compare medians and variance rather than cherry-picking the best run.

Example summary table:

| Metric | Baseline | Java 17 | Difference |
|---|---:|---:|---:|
| Throughput | 1,000 req/s | 1,080 req/s | +8% |
| p50 | 45 ms | 43 ms | -4.4% |
| p95 | 180 ms | 165 ms | -8.3% |
| p99 | 420 ms | 510 ms | +21.4% |
| Error rate | 0.2% | 0.3% | +0.1 percentage points |
| CPU/request | 1.8 ms | 1.7 ms | -5.6% |

These figures merely illustrate reporting format. In the example, throughput and p95 improved while p99 regressed; you cannot declare Java 17 universally better across every dimension.

### 4.5. Avoid load generator bottlenecks

If the load-generating host runs out of CPU, network, or connections, measured throughput will be capped by the generator. Monitor CPU and network on load generator hosts too.

For systems with variable latency, pick the appropriate load model. Closed-loop generators send the next request only after the previous one finishes; when the server slows down, request generation slows down as well. Open-loop or rate-controlled load sustains target arrival rates, though client queues must be monitored to avoid exceeding test-environment capacity.

### 4.6. Measure CPU per completed unit of work

CPU percentage alone is insufficient. One run may use more CPU simply because it served more requests.

Record total CPU time over the measurement window, successful request count, CPU time per successful request, throughput at the target latency bound, and CPU throttling if containerized.

If throughput rose 10% while CPU rose 5%, CPU per request actually fell. If throughput rose alongside a higher error rate, account for failed requests when interpreting CPU efficiency.

## 5. Microbenchmarks vs. system benchmarks

The two benchmark styles answer different questions.

### 5.1. Microbenchmarks with JMH

JMH is suited for measuring small code units such as collection operations, parsers, or algorithms. JMH manages warm-up, measurement iterations, and forks to mitigate common pitfalls.

Example benchmark skeleton:

```java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class StringBenchmark {
    private final String input = "java-17-performance";

    @Benchmark
    public String uppercase() {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

JMH configurations should specify warm-up, measurement, and multiple forks:

```java
@org.openjdk.jmh.annotations.Warmup(
        iterations = 5,
        time = 1
)
@org.openjdk.jmh.annotations.Measurement(
        iterations = 5,
        time = 1
)
@org.openjdk.jmh.annotations.Fork(3)
```

These snippets illustrate annotations only; projects must declare the JMH dependency and runner properly. Never time a loop with `System.nanoTime()` and treat it as a valid JVM benchmark; JIT optimizations, dead-code elimination, and warm-up skew naive loops.

### 5.2. System-level load tests

JMH does not replace full-service load testing. System benchmarks must exercise networking, serialization, thread pools, databases, caches, and dependent services just like production.

Use your team's standard load-testing tool with identical scripts and settings between baseline and Java 17. Record the load tool version and worker concurrency.

### 5.3. Do not extrapolate production speed from microbenchmarks

A method running 15% faster does not mean the end-to-end API runs 15% faster. That method might consume only 2% of total CPU while database or network I/O dominates response time.

Use microbenchmarks to explain a code path already proven to be a bottleneck. Use load tests and production-like telemetry to judge system performance.

## 6. Compare garbage collection (GC)

GC impacts throughput, latency, CPU, and memory. When upgrading Java, inspect actual GC telemetry on both runtimes rather than comparing collector names or a single pause event.

### 6.1. GC metrics to record

| Metric | Meaning |
|---|---|
| GC count | Collection counts by phase/type |
| GC pause duration | Stop-the-world pause durations |
| Total pause time | Sum of pause times in the window |
| Max/percentile pause | Longest pause and pause percentiles |
| Allocation rate | Rate of object allocation |
| Heap before/after GC | Occupancy before and after collection |
| Promotion/old-gen growth | Objects promoted to old generation or live-set growth |
| Concurrent GC CPU | CPU spent on concurrent GC phases |
| Full GC | Count and cause if any occurred |

Do not look at collection counts alone. Many short young collections can be healthy; infrequent collections with long pauses can still breach p99 latency SLAs.

### 6.2. Capture GC logs with unified logging

Java 17 uses unified logging. Enable it with:

```bash
-Xlog:gc*,safepoint:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=20m
```

Meaning:

- `gc*`: GC-related log tags.
- `safepoint`: safepoint timing details.
- `time,uptime,level,tags`: timestamp, uptime, level, and tags.
- `filecount=5`: retain up to 5 rotated files.
- `filesize=20m`: target size limit per file before rotation.

Place this option in the service's JVM arguments and confirm the process user can write to the log directory. Use identical log formatting across both runs for easy comparison.

### 6.3. Verify the active collector

Record the active collector and related flags from the live process:

```bash
jcmd 18420 VM.version
jcmd 18420 VM.flags
jcmd 18420 VM.flags -all
```

Or inspect startup arguments and startup logs. Never assume the active collector purely from the JDK name.

To isolate runtime impact, run one experiment using identical collector and heap settings on both runtimes when both support them. Then run another experiment using the intended production configuration. These two experiments serve different goals.

### 6.4. G1 and default ergonomics

G1 is the default collector on server-class machines in Java 17. Still, verify the actual active collector, because the application may specify another collector or run on an environment outside that class.

Do not blindly copy old GC tuning flags simply because they helped on an earlier runtime. Measure first with sensible Java 17 defaults, then change one parameter at a time only when backed by evidence.

### 6.5. Interpret GC logs in context of the workload

When comparing two logs, use identical steady-state windows and record counts of young/mixed/old/full collections per active collector, total/median/p95/max pause times, post-collection heap occupancy, allocation rate and old-gen trend, concurrent cycle duration, non-GC safepoints if any, and any allocation failure or evacuation failure events.

Exact event names depend on the collector. Never apply G1 terminology to another collector; read tags and events directly from the logs.

### 6.6. Better GC does not mean shorter pauses alone

A collector with shorter pauses that burns more concurrent CPU can lower throughput under a tight CPU quota. Keeping heap occupancy lower via more frequent collections can increase CPU cost.

Evaluate GC alongside throughput, p95/p99 latency, CPU time, allocation rate, heap occupancy, and total process/container memory.

### 6.7. Never force GC to produce neat numbers

Do not call `System.gc()` periodically just to compare post-GC heap sizes. Forced collections distort runtime behavior and introduce artificial pauses unlike real workloads.

Measure under steady workloads using GC logs and JFR to observe natural collections. If heap dumps or class histograms are needed, record when they were taken and their overhead.

## 7. Compare memory usage

Heap is the memory managed by GC, yet total process memory exceeds the heap. "Lower heap usage" is therefore insufficient to conclude the application consumes less RAM.

### 7.1. Memory regions to distinguish

| Region | Contents |
|---|---|
| Java heap | Objects and arrays allocated on the Java heap |
| Metaspace | Class metadata |
| Code cache | Native machine code emitted by the JIT compiler |
| Thread stacks | Per-thread stacks |
| Direct buffers | Off-heap buffers commonly used for I/O |
| Native/JNI memory | Allocations by native libraries and the VM |
| Memory-mapped files | Files mapped into the address space |
| Shared libraries | Shared objects mapped into the process |

Total resident memory (RSS/working set) also reflects OS page cache, shared pages, and accounting rules. Never sum every figure blindly, as regions can overlap or follow different accounting definitions.

### 7.2. Heap: used, committed, and max

Distinguish three metrics:

- **Used:** heap currently occupied at measurement time.
- **Committed:** heap memory currently reserved/committed from the OS by the JVM.
- **Max:** maximum heap the JVM is allowed to use.

Capture a snapshot with:

```bash
jcmd 18420 GC.heap_info
```

Track these over time rather than once. Committed heap can exceed used heap and does not necessarily shrink immediately after a collection.

### 7.3. Total process memory

Linux:

```bash
ps -p 18420 -o pid,rss,vsz,%mem,%cpu,etime
cat /proc/18420/status
```

Windows PowerShell:

```powershell
Get-Process -Id 18420 |
    Select-Object Id, WorkingSet64, PrivateMemorySize64,
                  VirtualMemorySize64, Handles, Threads
```

Windows and Linux metrics are not strictly identical. When comparing two runtimes, use the same OS and measurement method to avoid definitional discrepancies.

### 7.4. Metaspace and class loading

If the application uses many classes, proxies, dynamic class generation, or runtime class-generating frameworks, monitor metaspace and classes loaded/unloaded.

Inspect class loading via JMX or JFR. If metaspace climbs continuously across repeated workload cycles without plateauing, investigate class loader leaks or unbounded dynamic class generation.

Do not diagnose a memory leak merely because metaspace grows during warm-up; observe the trend after reaching steady state.

### 7.5. Direct memory and native memory

Applications using NIO, networking frameworks, or JNI can consume substantial off-heap native memory. If RSS climbs while heap stays flat, inspect direct buffers, thread stacks, native allocations, code cache, and memory-mapped files.

Native Memory Tracking (NMT) breaks down HotSpot JVM allocations, though it must be enabled at startup:

```bash
-XX:NativeMemoryTracking=summary
```

NMT incurs overhead and does not track every native allocation inside third-party native libraries. Enable identically on both baseline and candidate when using it for comparison.

Once running with NMT:

```bash
jcmd 18420 VM.native_memory summary
```

Capture an NMT baseline and diff changes over time:

```bash
jcmd 18420 VM.native_memory baseline
jcmd 18420 VM.native_memory summary.diff
```

The `baseline` command sets a reference point so diffs are meaningful. Follow the exact same procedure on both runs and record the NMT mode.

### 7.6. Thread count and stack memory

Higher thread counts raise native memory through stacks and thread bookkeeping. Record total process threads, thread counts per pool, new thread creation over time, thread states, and configured stack size.

Capture a thread dump:

```bash
jcmd 18420 Thread.print -l
```

Thread dumps reveal thread states and stack traces. Correlate them with thread-pool metrics to distinguish growth from workload, pool sizing, or thread leaks.

### 7.7. Container memory limits and OOM

Inside containers, cgroup memory limits apply to total container memory, not just the Java heap. The JVM can be OOM-killed even when heap usage is well below `Xmx`.

With cgroup v2, inspect:

```bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
```

Record max heap, RSS/process memory, and container `memory.current`. If `memory.events` records OOM or OOM-kill events, correlate timestamps with JFR, GC logs, and process metrics.

## 8. Use JFR to correlate CPU, GC, and memory

Java Flight Recorder (JFR) captures runtime events along a unified timeline. It helps determine whether performance shifts stem from CPU sampling, allocation pressure, GC, thread scheduling, lock contention, or I/O.

### 8.1. Start a recording on a running JVM

```bash
jcmd 18420 JFR.start name=java17-comparison settings=profile duration=15m filename=/var/tmp/java17-comparison.jfr
```

`profile` captures richer detail suited for short diagnostic windows. For longer recordings, consider `default` to reduce event density and file size.

Check active recordings:

```bash
jcmd 18420 JFR.check
```

If a continuous recording is already running, dump the window of interest:

```bash
jcmd 18420 JFR.dump name=continuous filename=/var/tmp/incident-window.jfr
```

### 8.2. Start a recording at JVM startup

When issues occur early, pass:

```bash
-XX:StartFlightRecording=name=java17-startup,settings=profile,duration=15m,filename=/var/tmp/java17-startup.jfr
```

Add the option to the process's JVM arguments. Use matching recording settings on baseline and candidate for direct comparisons.

### 8.3. Inspect summary and events

```bash
jfr summary /var/tmp/java17-comparison.jfr
```

Inspect CPU, GC, and allocation events:

```bash
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad,jdk.ExecutionSample,jdk.GarbageCollection,jdk.GCHeapSummary,jdk.ObjectAllocationSample /var/tmp/java17-comparison.jfr
```

Inspect thread waits and I/O:

```bash
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite /var/tmp/java17-comparison.jfr
```

Event presence depends on recording settings and thresholds. The absence of an event in a recording does not prove it never occurred if the event was disabled or below threshold.

### 8.4. Correlate JFR with application metrics

JFR does not inherently know which request was a checkout versus a report. Correlate timestamps or correlation IDs with application logs/metrics:

- Which endpoint saw increased latency?
- During that exact window, which stacks dominated CPU samples?
- Did monitor waits or thread parks increase?
- Did GC pauses or allocation spikes align with the latency spike?
- Did socket/file I/O durations climb unusually?
- Did queue depth build up before CPU or GC shifted?

JFR explains JVM behavior; application telemetry explains business impact. Both are needed for conclusions.

## 9. Workflow for running baseline vs. Java 17

A repeatable procedure:

### Step 1 — Freeze the test scenario

- Select commit/artifact.
- Prepare identical datasets.
- Fix request mix and load profile.
- Stabilize dependent services or document variance.
- Record expected outcomes and pass/fail thresholds.

### Step 2 — Record runtime configuration

Capture:

```bash
java -version
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

Also record CPU/memory limits, OS build, and application configuration. Redact secrets from command lines and system properties before archiving.

### Step 3 — Run functional tests

Run identical unit, integration, contract, and end-to-end test suites. Save outputs by scenario ID and compare database, event, and file side effects.

Do not move on to performance benchmarking while unexplained serious functional regressions remain.

### Step 4 — Run controlled load tests

- Launch a fresh process.
- Run warm-up.
- Run steady load.
- Run burst load if needed.
- Collect throughput, p50/p95/p99, error rate, CPU, and queue metrics.
- Repeat with fresh processes and record each run individually.

### Step 5 — Collect GC and memory data

Enable identical GC unified logging in both runs. Collect heap snapshots, process RSS/working set, thread counts, and container memory. If using NMT, enable it from startup on both runtimes.

### Step 6 — Capture JFR

Record JFR during the same steady-state window or during observed anomalies. Save recordings and summaries, documenting settings and durations.

### Step 7 — Synthesize results

Compare across each group: functionality, throughput/latency, GC, heap, and total memory. Record both absolute and percentage deltas alongside run count and spread.

### Step 8 — Separate hypotheses and actions

For example:

- Worse p99 despite lower CPU/request: inspect queueing, locks, I/O, or GC pauses.
- Higher RSS despite similar heap: inspect native memory, direct buffers, thread stacks, or shared mappings.
- Shorter GC pauses paired with higher CPU: inspect concurrent GC work and allocation rates.
- Higher throughput paired with higher error rate: inspect saturation, timeouts, retries, and load generators.

Change only one configuration variable per follow-up investigation run to isolate cause and effect.

## 10. Recommended comparison scorecard

Use a consistent scorecard per run while keeping units and measurement windows explicit.

| Category | Metric | Baseline | Java 17 | Delta | Notes |
|---|---|---:|---:|---:|---|
| Function | Passed scenarios |  |  |  |  |
| Function | Failed scenarios |  |  |  |  |
| Load | Throughput (req/s) |  |  |  |  |
| Load | p50 latency (ms) |  |  |  |  |
| Load | p95 latency (ms) |  |  |  |  |
| Load | p99 latency (ms) |  |  |  |  |
| Load | Error rate (%) |  |  |  |  |
| CPU | CPU time / successful request |  |  |  |  |
| GC | Total pause time (ms) |  |  |  |  |
| GC | Max pause (ms) |  |  |  |  |
| GC | GC count by type |  |  |  |  |
| GC | Allocation rate (MB/s) |  |  |  |  |
| Memory | Heap used after steady state (MB) |  |  |  |  |
| Memory | Heap committed/max (MB) |  |  |  |  |
| Memory | Process RSS/working set (MB) |  |  |  |  |
| Memory | Metaspace (MB) |  |  |  |  |
| Memory | Thread count |  |  |  |  |
| Container | Memory current/limit (MB) |  |  |  |  |
| Container | CPU throttling |  |  |  |  |

### 10.1. Calculating deltas

For metrics where higher is better, such as throughput:

```text
delta (%) = (Java17 - Baseline) / Baseline × 100
```

For metrics where lower is better, such as latency or CPU/request, the same formula produces negative numbers when Java 17 improves. Clearly indicate directionality in the table to prevent misreading.

For error rate, record both percentage-point change and relative percentage change. For instance, rising from 0.2% to 0.3% is +0.1 percentage points, a +50% relative increase.

### 10.2. Never report only a single composite score

Avoid collapsing results into one "performance score" that hides trade-offs. Reports should highlight which metrics improved, which regressed, whether deltas repeat across runs, whether any SLA/SLO was breached, and whether any functional or data discrepancies appeared.

## 11. Common scenarios when upgrading to Java 17

### 11.1. Functionality passes yet p99 latency increases

Inspect JFR, GC pauses, thread contention, pool waits, and socket I/O. p50 can remain flat while a tail subset of requests stalls.

### 11.2. Heap shrinks yet RSS grows

Heap can decrease while direct buffers, thread stacks, metaspace, code cache, or native allocations grow. Cross-check `GC.heap_info`, OS RSS, and NMT if enabled.

### 11.3. GC pauses shorten yet CPU rises

Concurrent GC phases run alongside application threads. Shorter pauses do not automatically mean less total CPU. Compare CPU/request, throughput, and total GC work.

### 11.4. Throughput rises yet error rate rises

Inspect timeouts, retries, queue saturation, connection pools, and load generators. The application may be accepting more concurrent work than it can complete reliably.

### 11.5. Fails on only one OS

Check default charset, filesystem semantics, case sensitivity, timezone, locale, native libraries, and file permissions. Java 17 does not erase underlying OS differences.

### 11.6. Framework fails during startup

Inspect reflection into internal packages and module encapsulation. Identify which library needs access, which package needs opening, and whether a Java 17-compatible library release exists.

### 11.7. Memory grows over time

Compare post-GC heap occupancy across matching workload cycles, loaded class count, metaspace, thread count, direct memory, and RSS. Growth during warm-up alone does not prove a leak; examine the trend after steady state is reached.

## 12. Pitfalls that invalidate comparison results

- Running baseline and candidate on different hardware or resource quotas without recording it.
- Checking `java -version` in a shell without verifying the running process's actual JVM.
- Changing JDK, dependencies, JVM flags, heap size, and app config simultaneously.
- Skipping warm-up or mixing warm-up into steady-state numbers.
- Running only one benchmark or picking the best run.
- Relying on average latency while ignoring p95/p99.
- Comparing throughput without checking error rate.
- Comparing heap without checking RSS, native memory, and container limits.
- Comparing GC count without checking pause duration, CPU, and allocation rate.
- Forcing GC during benchmarks for cleaner-looking snapshots.
- Extrapolating whole-system performance from JMH microbenchmarks.
- Enabling different profilers/recordings across runs without documenting them.
- Recording logs or JFR captures containing sensitive data and sharing them without redaction.
- Tweaking GC flags by intuition before establishing a baseline.

## 13. Java 17 upgrade comparison report template

Use the following structure for each test cycle:

```text
Upgrade comparison ID:
Application / version / commit:
Artifact checksum:

Baseline runtime:
  Vendor:
  JDK version:
  VM version:
  OS / architecture:

Candidate runtime:
  Vendor:
  JDK version:
  VM version:
  OS / architecture:

Environment:
  CPU model / quota:
  Memory / container limit:
  Database / broker / cache:
  JVM flags:
  Heap settings:
  GC collector:

Functional results:
  Scenarios passed:
  Scenarios failed:
  Data/API differences:
  Side-effect differences:

Load profile:
  Warm-up:
  Steady duration:
  Request mix:
  Throughput target:
  Concurrency:
  Payload distribution:

Performance:
  Throughput:
  p50 / p95 / p99:
  Error rate:
  CPU time per successful request:
  Queue / pool saturation:

GC:
  Collector:
  GC count by type:
  Total pause:
  Max / p95 pause:
  Allocation rate:
  Heap before/after collection:

Memory:
  Heap used / committed / max:
  Process RSS / working set:
  Metaspace:
  Direct/native memory:
  Thread count:
  Container memory current / limit:

Evidence:
  Test result files:
  Application metrics:
  GC logs:
  JFR recordings:
  Thread dumps:
  NMT output:
  Run timestamps (UTC):

Conclusion:
  Functional compatibility:
  Performance impact:
  GC impact:
  Memory impact:
  Known limitations:
  Follow-up experiments:
```

Base conclusions on thresholds agreed before testing—for example: all critical functional scenarios pass; p95/p99 remain within SLO; error rate stays within budget; and peak memory retains sufficient headroom below container limits. Exact thresholds depend on your application and must be set by the operations team.

## 14. Key takeaways

- Java 17 comparisons require an explicit baseline and repeatable workloads.
- Verify functionality, side effects, serialization, charsets, reflection, and module access.
- Measure throughput alongside p50/p95/p99, error rate, CPU/request, and queue depth.
- Warm up JIT and caches before measuring steady state; repeat using fresh processes.
- Use JMH for microbenchmarks and load tests for whole-system evaluation.
- Capture GC logs with unified logging; analyze pauses, allocation rate, heap occupancy, and CPU together.
- Heap is not all memory; monitor RSS, metaspace, direct/native memory, thread stacks, and container usage.
- Use JFR to correlate CPU, GC, allocations, threads, and I/O along the application timeline.
- NMT requires startup activation and incurs overhead; enable identically across compared runs.
- Separate controlled runtime comparisons from production-configuration comparisons.
- Never conclude from a single metric or a single run; report improvements, regressions, and limitations alike.

## Official Java 17 references

- [Java SE 17 — java launcher and VM options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Java SE 17 — jcmd tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html).
- [Java SE 17 — jfr tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html).
- [Java SE 17 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/).
- [Java SE 17 — JDK Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf).
- [Java SE 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html).
- [Java SE 17 — RuntimeMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html).
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh).
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328).
- [JEP 331 — Low-Overhead Heap Profiling](https://openjdk.org/jeps/331).
- [JEP 400 — UTF-8 by Default (Java 18)](https://openjdk.org/jeps/400).
