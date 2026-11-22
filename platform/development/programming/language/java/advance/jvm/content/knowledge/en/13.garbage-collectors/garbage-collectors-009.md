# Comparing GCs Under the Same Load, Resource Limits, and Latency Targets

## 1. The right question: which collector meets application requirements within the same budget?

In Java/JVM, a **garbage collector (GC)** does not have a single “fastest” ranking that applies to every system. Results depend on the **actual load**, object lifetime distribution, allocation rate, live-set size, heap, CPU cores, process memory, JDK version, warm-up time, and especially **latency targets**.

A fair comparison is not just running two JVMs and reading the **lowest GC pause** number. You need to fix or explicitly record the controlled factors, put all candidates through the **same success criteria**, and only then evaluate trade-offs:

- **Correctness and availability:** no dropped requests, no OOM, no container kills, same business results.
- **Throughput:** how many operations or successful requests per second are processed under the same offered load.
- **Latency:** p50, p95, p99, p99.9, max, and SLO violation rate; distinguish *request latency* from *GC pause*.
- **Resources:** CPU quota/usage, total process RSS/cgroup memory, heap live/committed, native/direct memory, thread count.
- **GC costs:** total wall-clock STW, pause duration distribution, concurrent GC CPU, allocation rate, full GC, GC overhead, and non-GC safepoints.
- **Stability:** results across multiple independent runs, steady load long enough, not just one lucky winning run.

**Key conclusion:** the collector with the shortest p99 GC pause is **not necessarily** the collector that yields the lowest p99 API latency or achieves the highest throughput. Conversely, a collector with good throughput may violate the tail-latency SLO or exceed the memory budget.

### Do not confuse “same load” with “same number of loop iterations”

Two JVMs processing exactly 10,000 operations do not mean they received the same **load over time**. A slow collector can cause a closed-loop client to issue requests more slowly; therefore, the actual load reaching the server is lower and the observed latency can look artificially good.

For **service** benchmarks, control the **offered arrival rate** (the rate of requests actively issued over time), not just reaching the same total number of requests. For **allocation micro-workload** benchmarks, at minimum fix the iteration count, object size, retention ratio, concurrency, and heap; and explicitly state that this is **not** measuring production request latency.

## 2. Which GCs are candidates worth testing on JDK 17?

This table describes **design orientation**, not a measured ranking. You must verify that the GC is packaged and works on the target distribution/JDK.

| Collector | General orientation | Trade-offs to measure |
| --- | --- | --- |
| **Serial GC** (`-XX:+UseSerialGC`) | Simple, few GC workers, may suit small workloads and constrained CPU | STW pauses can be long with a large live set; throughput on multiple cores can be poor |
| **Parallel GC** (`-XX:+UseParallelGC`) | Prioritizes throughput using multiple GC worker threads | Can incur significant pauses, especially with a large live set |
| **G1 GC** (`-XX:+UseG1GC`) | Region-based GC, attempts to balance throughput and pause goals | Has concurrent/remembered-set overhead; pause goal is a target, not a hard guarantee |
| **ZGC** (`-XX:+UseZGC`) | Concurrent collector, aims for very low pause latency | Must measure native/heap headroom, CPU, and throughput; **JDK 17** behavior is not automatically identical to ZGC in newer JDKs |
| **Shenandoah GC** (`-XX:+UseShenandoahGC`, **if supported by the JDK build**) | Concurrent collector optimized for low pauses | Availability/flags depend on the OpenJDK distribution; CPU/throughput/memory costs must be measured |

**G1** is a reasonable baseline in many HotSpot Java 17 server applications; Oracle JDK 17 recommends first running with the collector chosen by the VM if there are no overly strict pause requirements, then tuning heap/collector when needed. However, **default does not mean optimal** for every workload.

**Do not enable multiple competing `-XX:+Use*GC` flags in the same command**. Each benchmark is a separate JVM process enabling exactly one collector.

**Version note:** Java 17 ZGC is not completely identical to the capabilities of generational ZGC in later JDKs. Shenandoah may not be present in some builds. Do not enable flags that only exist in newer JDKs and call it a “Java 17” benchmark.

## 3. Write down the SLO and resource limits before benchmarking

A **hypothetical template for a Java 17 service**:

| Condition | Example limit |
| --- | --- |
| Request type A | Same request mix/response payload, same data and cache state |
| Offered load | Steady 3,000 requests/second over a measurement window |
| Success rate | At least 99.9%; timeouts/errors still count |
| p99 end-to-end latency | No more than 80 ms at the client measurement point |
| p99.9 | No more than 150 ms |
| Peak container memory | No more than 800 MiB |
| CPU quota | Maximum 2 vCPU, same CPU/CPU affinity configuration |
| JVM maximum heap | 512 MiB for the equal-heap comparison pass |
| Test duration | Warm-up + multiple steady-state windows, minimum sufficient samples |
| Conclusion | Only candidates that **meet all conditions** advance to the trade-off optimization round |

**The numbers above are only to illustrate how to define the problem**, not general production configuration advice. For batch jobs, throughput/deadlines may matter more than request p99; for trading or real-time interaction, tail latency may matter more than throughput.

### SLO is a decision threshold, not an isolated GC target

If the target request p99 ≤ 80 ms, a 100 ms GC pause sometimes still does not cause *every* request to violate, but it is a major risk. It is also possible for GC p99 to be 5 ms while request p99 is 200 ms due to DB/locks/CPU. Therefore, establish:

1. **Primary success gate:** correctness, error rate, request p99/p99.9 at offered load.
2. **Resource gate:** peak RSS/cgroup, CPU throttling, native memory, and OOM status.
3. **Supporting diagnostics:** GC pause distribution, safepoint times, allocation rate.
4. **Tiebreaker:** throughput, CPU cost, footprint, stability, and operational simplicity.

Do not rank solely by `-XX:MaxGCPauseMillis` or by max pause in GC logs.

## 4. Fix variables for a fair comparison

### 4.1. Same workload, data, and concurrency

- Same application binary, dependency versions, JVM bytecode target, and feature flags.
- Same request types, GET/POST or compute/IO ratios, payload sizes, database fixtures, and random data with a fixed seed.
- Same offered arrival rate or same clearly described closed-loop workload, same run duration and measurement window.
- Same number of workers/concurrent connections when part of the problem; avoid one test accidentally using 2 threads while another uses 200.
- Same cache warm state or same prefill/reset procedure; do not compare a warm cache against a cold cache.
- Same external factors: DB connection limit, downstream latency, network, TLS, disk, log level, and tracing sampling.
- Do not change business logic or object sizes between two runs just to make one GC look better.

For object-allocation workloads, specify **bytes allocated per operation**, live-set size, age/lifetime distribution, and % of objects retained across multiple collection cycles. A loop that only creates arrays and discards them is an **allocation stress test**, not representative of every service.

### 4.2. Same CPU and memory budget

Keep CPU quota/cpuset, container memory limit, OS/JDK build, and heap policy fixed. **Actual CPU quota** must be enforced by the OS/container; `-XX:ActiveProcessorCount=2` only affects HotSpot's perception of processor count and **does not enforce an OS quota itself**.

| Resource | What to keep/record | Why |
| --- | --- | --- |
| OS CPU quota & CPU affinity | Same vCPU/quota, host load, no vastly different noisy neighbors | GC parallel/concurrent threads consume CPU like business threads |
| Container memory limit | Same total limit | Equal heap but different native footprint |
| `-Xms`, `-Xmx` | Fixed in equal-heap experiments | Heap size affects GC frequency and cost |
| Direct/native memory | Limit and measure, e.g. `MaxDirectMemorySize` if using NIO | Total RSS is not just Java heap |
| GC/JIT worker ergonomics | Record actual thread counts and inferred flags | Collectors choose different parallelism |
| Process restart | Fresh JVM process for each repetition | Avoids code cache/heap and state from previous runs |
| GC logs & JFR | Same levels/settings across candidates | Instrumentation overhead can bias results |

### Both comparison modes are valid but must be separated

**A. Equal-heap benchmark:** set the same `-Xmx` and `-Xms`, and the same container CPU/memory. It answers “with the same heap size, how does each collector behave?”. If a collector needs larger native headroom, the result may be OOM under the total budget, and that is important information.

**B. Equal-total-memory-budget benchmark:** apply the same container/process memory cap, allowing **valid heap tuning** per collector so all stay under the cap. It answers “within the same total resource limit, which collector configuration delivers the best SLO/throughput?”.

**Do not mix** results where one candidate is given a 4 GiB heap and another has only 512 MiB and conclude one collector is inherently better. If tuning heap separately per collector, publish the **heap of each configuration** and compare under the same total budget.

### 4.3. Version and flags

Record `java -version`, and `java -XX:+PrintFlagsFinal -version` if you need to find effective flags. JDK 17.0.x builds differ from JDK 21/24; in particular, GC/JIT have evolved, so do not lump results into a timeless “Java GC comparison”.

For initial baseline experiments, **do not force a collector-specific knob onto all collectors**. For example, `-XX:MaxGCPauseMillis=50` is a tuning target relevant to G1/supporting collectors; it does not mean every collector interprets the flag the same way. Run defaults first, then tune separately in a **second round** with clearly stated purpose and cost.

## 5. Repeatable A/B execution procedure

1. **Define target SLO and resource caps.** Lock in offered-load levels, latency percentiles, error budget, peak RSS, CPU/throttling, and startup/steady-state duration.
2. **Freeze the environment:** JDK build, host/kernel, image, binary, network, DB snapshots, log/JFR settings, time source.
3. **Smoke test every candidate:** does the JVM support the collector, does startup succeed, is functionality/correctness identical?
4. **Warm-up** until JIT/code cache/connection pools/caches are relatively stable; exclude warm-up time separately or measure startup in a different test.
5. **Run steady-state** at the same offered rate; track achieved throughput, errors/timeouts, and dropped requests.
6. **Collect GC/JFR/OS metrics** alongside client latency histograms.
7. **Repeat independently** (e.g., at least 5 times) with a fresh JVM process. Rotate the order such as G1→Parallel→ZGC→Serial and reverse the order in the next round to reduce host temperature/noisy neighbor bias.
8. **Evaluate multiple loads:** below target, at target, near saturation, and mild overload; identify breaking points and failure modes.
9. **Apply SLO gates**, comparing trade-offs only among qualifying candidates; inspect outliers and confidence intervals.
10. **Production-like verification:** long soak, memory footprint, collector instability, rare Full GC, p99.9/timeouts, and deployment behavior.

**Do not use a single short run to conclude** that a collector wins by 10% throughput or better p99. If run-to-run variance is larger than the difference, there is not enough evidence to pick a winner.

### Startup benchmarks differ from steady-state benchmarks

One collector has different startup/class-loading overhead than another; JIT warm-up and initial heap occupancy also matter. If startup latency is the goal, create a **separate cold-start test** without excluding warm-up. If the goal is steady-state serving p99, **exclude warm-up** and measure for a sufficiently long duration. Do not try to optimize startup and steady state simultaneously while publishing only one combined number.

## 6. Closed-loop, open-loop, and coordinated omission

### Closed-loop generator

~~~text
Client sends request
       |
       v
Wait for response
       |
       v
Send next request
~~~

When the server slows down, the client also sends requests more slowly. **Offered load drops automatically**, which can hide queueing and latency during server overload. Closed-loop is appropriate when the real workload itself follows a synchronous closed-loop model, but it does not replace open-loop when testing service capacity at a fixed arrival rate.

### Open-loop / rate-controlled generator

~~~text
Clock sends requests at target timestamps
   t=0ms, 1ms, 2ms, ...
       |
       +--> if the server is still processing, requests may queue
       |
       +--> measure completed, failed, timed-out, and dropped
~~~

To compare GCs at a 3,000 req/s target, you need a load generator capable of issuing at the target rate **even when responses are slow**, with clear queue limits and error handling. If the generator lacks CPU or network capacity, offered-rate control breaks down; you must also measure the **load generator's** resources.

**Coordinated omission:** when a tool only records the latency of requests actually sent/completed while ignoring requests that should have arrived on schedule during a server pause, the histogram can **underestimate tail latency**. Use an arrival-timestamp-based scheduler or a histogram correction mechanism suited to the workload and document the calculation method. Do not silently drop timeouts/failed requests from p99, making a collector look “fast” because it drops requests.

### Delivered throughput differs from offered load

Record simultaneously:

- `offered_requests_per_second`
- `completed_success_per_second`
- `failed_requests_per_second`
- `timeouts_and_dropped_per_second`
- `in_flight`, queue depth, or backlog.

A collector handling 2,500 req/s in an experiment offered 3,000 req/s **fails to meet the same load requirement**, even if p99 on successful requests looks low.

## 7. Measuring latency percentiles properly

Given `N` latency samples sorted in ascending order, one illustrative presentation is the **nearest-rank percentile**: p99 is at 1-based position `ceil(0.99 × N)`. Tools may choose interpolation or HDR histograms, so when comparing numbers across different tools, agree on the definition.

| Metric | What it tells you |
| --- | --- |
| p50 | Typical request in the middle of the distribution |
| p95 | 95% of requests are at or below the threshold per the percentile method |
| p99 | Tail latency; with 10,000 samples, examines the slowest 1% region |
| p99.9 | Very rare tail; requires enough samples to stabilize |
| Max | Worst event in a specific sample set |
| Latency histogram | Full distribution, preventing averages from hiding outliers |
| Throughput/success/errors | Whether the required load is actually being served |

**A p99 value on 100 samples is not as reliable as p99 on hundreds of thousands of samples** if the workload has rare spikes. You need enough samples per repetition and multiple independent repetitions.

**Timestamp definition:** from client send to receive (client-side), from server accept to response (server-side), or only handler execution? Do not mix measurement types. GC affects many places on the critical path, while client-side latency usually reflects the fuller experience (including network).

## 8. Hands-on Java 17 benchmark: same synthetic allocation workload

This program illustrates a **fixed workload, collector switched via JVM flag, measuring throughput and latency distribution**. It is **not** an open-loop load generator, does not represent an HTTP server, and is **not sufficient** to declare any collector optimal for production. Advantages: simple source, fixed payload/count, partially deterministic results, useful for practicing GC log collection and disciplined comparison.

Create the file **`CollectorLoadLab.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class CollectorLoadLab {
    private static volatile long observed;

    static long percentile(long[] sorted, double q) {
        int rank = Math.max(1, (int) Math.ceil(q * sorted.length));
        return sorted[Math.min(sorted.length - 1, rank - 1)];
    }

    public static void main(String[] args) {
        final int warmup = 3000;
        final int measured = 12000;
        final int payloadBytes = 48 * 1024;
        final byte[][] retained = new byte[16][];
        final long[] latencyNs = new long[measured];
        long checksum = 0L;

        long measuredStart = 0L;
        for (int i = 0; i < warmup + measured; i++) {
            if (i == warmup) measuredStart = System.nanoTime();
            long opStart = System.nanoTime();

            byte[] payload = new byte[payloadBytes];
            payload[0] = (byte) i;
            payload[payloadBytes - 1] = (byte) (i >>> 8);
            retained[i % retained.length] = payload;
            checksum += payload[0] & 0xff;

            if (i >= warmup) {
                latencyNs[i - warmup] = System.nanoTime() - opStart;
            }
        }

        long elapsedNs = System.nanoTime() - measuredStart;
        observed = checksum;
        Arrays.sort(latencyNs);

        System.out.println("warmup=" + warmup);
        System.out.println("measured=" + measured);
        System.out.println("payloadKiB=" + payloadBytes / 1024);
        System.out.printf(Locale.ROOT, "allocatedMiB=%.1f%n",
                (warmup + measured) * (double) payloadBytes
                        / (1024 * 1024));
        System.out.printf(Locale.ROOT, "throughputOpsPerSecond=%.1f%n",
                measured * 1_000_000_000.0 / elapsedNs);
        System.out.printf(Locale.ROOT, "p50Us=%.3f%n",
                percentile(latencyNs, 0.50) / 1000.0);
        System.out.printf(Locale.ROOT, "p99Us=%.3f%n",
                percentile(latencyNs, 0.99) / 1000.0);
        System.out.println("checksum=" + observed);
        java.lang.ref.Reference.reachabilityFence(retained);
    }
}
~~~

### 8.1. Compile

~~~bash
javac --release 17 CollectorLoadLab.java
~~~

### 8.2. Run each collector with the same heap

~~~bash
java -Xms128m -Xmx128m -XX:+UseSerialGC CollectorLoadLab
java -Xms128m -Xmx128m -XX:+UseParallelGC CollectorLoadLab
java -Xms128m -Xmx128m -XX:+UseG1GC CollectorLoadLab
java -Xms128m -Xmx128m -XX:+UseZGC CollectorLoadLab
~~~

**ZGC must be supported on the JDK/OS in use**; if the option is rejected by the VM, mark it **UNSUPPORTED** and do not treat not running as a performance result. Similarly for Shenandoah, only run when the JDK distribution confirms that collector is present.

### 8.3. Invariant stdout part and variable part

Lines from the logic describing the fixed workload:

~~~text
warmup=3000
measured=12000
payloadKiB=48
allocatedMiB=703.1
~~~

Followed by:

~~~text
throughputOpsPerSecond=<varies by JVM/machine/run>
p50Us=<varies by JVM/machine/run>
p99Us=<varies by JVM/machine/run>
checksum=1904596
~~~

The `<...>` part is a **description of variable output**, **not verbatim stdout** of a run. The code was compiled with `javac --release 17` and actually run on JDK 24 with G1 and Serial GC. In **one local measurement**, G1 had throughput around 316,637 ops/s, Serial around 430,597 ops/s; **do not turn these two incidental numbers into a collector conclusion**. The duration is too short, single-threaded only, the workload is overly simple, and the VM build is not a JDK 17 runtime.

**Correctness check:** total cumulative allocation is 15,000 × 48 KiB = 703.125 MiB (printed to one decimal place as 703.1). The `retained` array has 16 slots so it does not hold that many bytes simultaneously. `checksum` prevents completely optimizing away the computation result and shows the same data logic across runs; it does not prove JIT did not optimize away every detail or that the benchmark represents production.

### 8.4. Limitations of the test program

- This benchmark is **single-thread closed-loop**: the next iteration only starts after the current one.
- `System.nanoTime()` itself has overhead; very fast operations are easily noisy due to resolution/scheduling.
- 12,000 measured iterations may be too few for p99.9 or rare GC events.
- A 128 MiB heap and 48 KiB arrays do not represent large live sets, diverse object graphs, or a real server.
- JIT compilation, tiered compilation, and GC ergonomics may not have stabilized yet.
- Without OS-enforced CPU quota/container memory, `-Xmx` alone does not guarantee fairness in process resources.
- For serious microbenchmarking, use JMH appropriately and configure forks/warm-up/measurement; however, JMH also does not replace fixed-arrival server load tests.
- GC work can occur across multiple operations; synthetic allocation p99 is not equivalent to API request p99.

This lab is suitable for **practicing observation tools and comparing output**, not as an official Serial vs G1 ranking.

## 9. Collecting GC logs and JFR with the same configuration

Enable HotSpot Unified Logging when running each collector, writing to **different** files to avoid overwriting. Example for G1:

~~~bash
java -Xms128m -Xmx128m -XX:+UseG1GC \
  '-Xlog:gc=info,safepoint=info:file=g1-gc.log:uptime,level,tags' \
  CollectorLoadLab
~~~

The `\` line continuation is for Bash/Linux/macOS. On PowerShell:

~~~powershell
java -Xms128m -Xmx128m -XX:+UseG1GC '-Xlog:gc=info,safepoint=info:file=g1-gc.log:uptime,level,tags' CollectorLoadLab
~~~

Run Serial with the same options except GC choice and **filename**:

~~~bash
java -Xms128m -Xmx128m -XX:+UseSerialGC \
  '-Xlog:gc=info,safepoint=info:file=serial-gc.log:uptime,level,tags' \
  CollectorLoadLab
~~~

What to compare:

1. GC counts and types (`Young`, `Mixed`, `Full`, concurrent cycle events) per collector.
2. GC pause durations: count, max, histogram, and percentiles.
3. Safepoint reaching/at/leaving/total: **not automatically equal to elapsed GC pause**.
4. Allocation throughput (bytes/s), live set, heap occupancy, and old-gen pressure.
5. JVM process CPU time + OS CPU usage, container throttling.
6. Peak RSS/cgroup memory and native memory.
7. Application throughput, p99/p99.9 latency, errors/timeouts under the same offered load.

**Distinguish wall-clock from CPU time:** GC workers running in parallel can consume total CPU time greater than the elapsed pause. Concurrent GC can consume CPU outside STW pauses, so total STW alone does not reflect the full cost.

### Java Flight Recorder

On JDK 17+ with JFR, you can record a profile recording (event names and settings depend on JDK):

~~~bash
java '-XX:StartFlightRecording=filename=gc-lab.jfr,settings=profile' \
  -Xms128m -Xmx128m -XX:+UseG1GC CollectorLoadLab
~~~

Use separate JFR files for each collector/run; JDK tools allow:

~~~bash
jfr summary gc-lab.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause gc-lab.jfr
~~~

A lab program that finishes too quickly may not have enough events to draw conclusions; increase workload length **equally for all candidates** or use a longer server load test. Recording/JFR has overhead; if used, enable equivalent settings for all candidates.

### Note on HotSpot `-Xlog` tags

Tags/format and log verbosity depend on the JVM build. Use:

~~~bash
java -Xlog:help
~~~

For services needing durable logs, manage file rotation, output volume, and log permissions. Do not enable `trace` logging for one collector and `info` for another and then compare performance as an equal environment.

## 10. Resource fairness: CPU quota differs from ActiveProcessorCount

HotSpot has the `-XX:ActiveProcessorCount=N` option, which affects how the JVM calculates CPU count for choosing certain workers/ergonomics. It is **not an OS CPU quota**.

For example, two processes both run with `-XX:ActiveProcessorCount=2`, but one process is given 2 vCPU by its container and the other is actually given 8 vCPU: this is **not an equivalent resource environment**. GC workers, Java threads, and OS scheduling are still subject to external limits.

In container systems, record:

- cgroup CPU quota/period and cpuset; CPU throttling level.
- memory.max (or cgroup equivalent), memory.current/peak, OOMKilled events.
- Host CPU contention and NUMA/pinning if applicable.
- JVM effective heap sizes and GC/JIT thread counts.
- Native/DirectByteBuffer libraries along with quotas if used by the workload.

**Equal memory cap** does not mean **equal heap cap is already optimal**. A concurrent collector may need headroom to both allocate for mutators and reclaim in the background. If `-Xmx` is forced too low and one collector OOMs, that is a valid result for the equal-heap scenario, but you should also try an equal-total-budget tuned scenario before concluding on suitability.

## 11. Why looking only at `-Xmx` is wrong

The total memory footprint of a JVM process also includes:

~~~text
Java heap
+ native direct buffers / mapped files
+ metaspace / class metadata
+ JIT code cache
+ native thread stacks
+ GC bookkeeping and collector structures
+ JNI/JNA/native library allocations
+ OS memory mappings and allocator overhead
~~~

Dashboard numbers do not necessarily sum exactly to RSS because of differences between **reserved**, **committed**, and **resident** memory as well as potential double-counting of shared pages.

Example pair:

- G1 has good p99 under a 512 MiB heap and 800 MiB container.
- ZGC has very low GC pause p99 but exceeds the memory budget due to workload/collector/native overhead within the same limit.

In a problem with a **hard memory cap**, a candidate that exceeds the cap is a **FAIL** regardless of nice pauses. However, verify that the cap is actually enforced and what factor caused the OOM, rather than blaming every OOM on the collector implementation.

## 12. Comparing with a scorecard that has elimination thresholds

Below is **SIMULATED data for practicing decision-making**, definitely not JDK 17 benchmark results:

| Collector | Throughput (req/s) | p99 client (ms) | Peak memory (MiB) | Example verdict |
| --- | ---: | ---: | ---: | --- |
| Serial | 3,400 | 180 | 530 | FAIL: p99 |
| Parallel | 3,900 | 115 | 630 | FAIL: p99 |
| G1 | 3,600 | 68 | 730 | PASS |
| ZGC | 3,350 | 24 | 920 | FAIL: peak memory |

**Hypothetical SLO:** throughput ≥ 3,000 req/s, p99 ≤ 80 ms, peak memory ≤ 800 MiB, error rate below limit.

According to the simulated table, G1 is the **only candidate passing all three gates**. Choosing Serial for the least memory would violate p99; choosing ZGC just for the best p99 would violate the memory cap. If the memory cap is adjusted to 1,024 MiB, ZGC also passes; at that point, look at p99.9, CPU budget, throughput, and operational cost to choose.

**Do not invent an unfounded “GC total score 8.4/10”** by adding metrics with different units. Set elimination conditions first, then evaluate Pareto trade-offs according to business priority.

### Pareto frontier

An option is **Pareto-dominated** if another option is at least as good on every priority metric, better on at least one metric, and still within the same resources/reliability. However, throughput, latency, and memory have different optimization directions; often multiple points exist where **no option dominates**. In that case, the decision depends on SLO/cost, not on an “absolute winner” collector.

## 13. Variance and reliability analysis

When the p99 difference between G1 and ZGC is only 3% while each run fluctuates by 10%, you cannot declare ZGC the definitive winner. You need:

- Multiple independent process runs and randomized order.
- Median of per-run metrics, min/max, or appropriate confidence intervals.
- A defined warm-up period, long enough for code cache/JIT and heap occupancy to stabilize.
- A large sample size for meaningful p99.9.
- Checking the relationship between throughput and offered load, without dropping failed requests.
- Observing long-tail events: rare full GC, OS noise, background compaction, CPU throttling, OOM pressure.
- Ensuring identical recording/logging settings.

**Beware of percentile aggregation:** the arithmetic mean of p99 across 5 runs does not equal the p99 of all requests pooled from 5 runs, especially when request counts per run differ. If merging histograms, ensure bins, time windows, and sample weights are compatible; or report per-run percentiles with confidence distributions instead of an unexplained “average p99” number.

## 14. Flawed benchmark scenarios and how to fix them

### 14.1. Collector A handles 3,000 req/s, collector B only 2,200 req/s

If the target is 3,000 req/s and offered load is the same, B fails to meet the required throughput. B's p99 over 2,200 completed requests may look artificially good because timeouts were excluded. Record failures and offered-vs-completed; do not credit B with passing the SLO.

### 14.2. Using a single-thread throughput benchmark and concluding on service p99

A single thread allocating arrays quickly does not measure thread pools, request queueing, DB latency, real object graphs, or CPU contention of concurrent GC. Use this lab as an exercise; operational conclusions require a **production-like workload**.

### 14.3. Good GC pause p99, bad request p99

This may be concurrent GC competing for CPU, allocations causing memory bandwidth pressure, CPU throttling, blocking locks, or downstream I/O. Compare JFR CPU/thread events and application tracing. Do not equate GC pause with total latency.

### 14.4. Running on a shared machine with many unrelated processes

Host load and thermal/CPU frequency scaling changes can swamp small differences. Use an isolated worker/node or measure/document noisy neighbors; randomized run order helps reduce bias but cannot replace a stable environment.

### 14.5. Same Xmx but one collector OOMs

That is information about the **equal-heap** test, though it could also be due to the collector needing extra headroom/native memory, startup settings, or load exceeding threshold. Try equal-total-memory tuning if the application allows; still count each scenario's failure properly.

### 14.6. Different cache/JIT warm state

The candidate running later has a warm cache from the DB/filesystem and is faster, even though GC is unrelated. Use identical reset/prefill, separate cold-start tests, and randomize order. Different `-Xms`/`-Xmx` also affect heap commit/GC ergonomics.

### 14.7. Using only GC logs to measure performance

GC logs show GC-related events; they do not measure full request latency, correctness, queue backlog, or native memory. You must have application-side instrumentation and OS metrics.

### 14.8. Using one tuning flag and concluding a collector is bad

A collector can be forced into a heap/pause goal unsuitable for the workload. Baseline defaults to understand cost, then controlled tuning under the same resource budget. Document the flag set and version when publishing.

## 15. A pragmatic two-round procedure

### Round A — Controlled baseline

Keep variables constant:

~~~text
App binary:       identical
JDK build:        identical
Container CPU:    2 vCPU
Memory limit:     800 MiB
Heap:             Xms=Xmx=512 MiB
Workload:         same request mix, data, arrival rate
Warm-up:          same
Measurement:      e.g. 15 minutes steady state
Logging/JFR:      same settings
Runs:             at least 5 times per collector
Change:           GC selection (one collector per run)
~~~

Result: understand which collectors pass or fail the SLO in the baseline configuration.

### Round B — Individually tuned but shared budget

For promising candidates, allow adjusting heap and **documented** collector-specific knobs, such as changing the G1 pause target or ZGC memory headroom; still keep **2 vCPU/800 MiB/arrival rate/SLO** the same. If increasing one collector's heap, another component must be reduced or it must remain under the cap. Optimize only on a training workload set, then re-evaluate on independent workloads/periods to avoid overfitting.

**Why two rounds?** Comparing only equal-heap may not reflect the “best choice within budget”; comparing only tuned-final without a baseline makes unfair or non-reproducible tuning tricks easy.

## 16. Checklist before publishing GC benchmark results

- [ ] Recorded JVM vendor/build/version, GC option, and effective flags.
- [ ] Same application binary, dataset, request mix, caches, warm-up.
- [ ] Same CPU quota/cpuset and OS-enforced container memory cap.
- [ ] Separate equal-heap scenario and, if needed, equal-total-memory-tuned scenario.
- [ ] Offered load measured and target met; errors, timeouts, dropped requests counted.
- [ ] Agreed on latency histogram method, p99/p99.9 sample size, and timestamp scope.
- [ ] Recorded request throughput, correctness, SLO compliance; not just GC pause.
- [ ] GC logs/JFR with same settings and same time window as request metrics.
- [ ] Measured GC STW, safepoints, CPU usage, RSS, and allocation rate.
- [ ] Multiple repeats with fresh processes and randomized order.
- [ ] Checked collector support and startup/compatibility, without ignoring unsupported runs.
- [ ] Checked OOMKilled/cgroup throttling and failure modes.
- [ ] Distinguished synthetic allocation lab from production-like end-to-end tests.
- [ ] Illustrative tables clearly marked as simulated, not treated as empirical results.
- [ ] Selected conclusions using SLO/resource gates before trade-off optimization.

## 17. Self-check questions

1. Are 10,000 requests at different request issuance rates the same load? **No**, different arrival rates can change queueing/latency.
2. Does the collector with the lowest GC pause p99 necessarily yield the best HTTP p99? **No**, there are also CPU, I/O, locks, queueing, and concurrent GC costs.
3. Does `-Xmx512m` cap process RSS at a maximum of 512 MiB? **No**, there are also native/JIT/thread/GC allocations.
4. Does `-XX:ActiveProcessorCount=2` actually limit a container to 2 vCPU? **No**, OS/cgroup quota is required.
5. In a closed-loop benchmark, can a slow server cause offered load to drop? **Yes**.
6. How does coordinated omission affect measured p99? **It can be artificially low because requests that should have arrived during a pause are not measured properly**.
7. Is it necessary to count failed/timeout requests? **Yes**, you must not look only at successful latency.
8. Are equal-heap and equal-total-memory the same experiment? **No**, they answer different questions.
9. Does the G1 pause target hard-bound request p99? **No**.
10. Can a concurrent GC consume CPU while GC pause logs are very short? **Yes**.
11. Can GC CPU time be greater than elapsed pause when multiple workers run in parallel? **Yes**.
12. With 12000 measurements, is it enough to conclude p99.9 in a 10-million-requests/day production system? **No**, there is also tail rarity/representativeness and repetitions.
13. If a collector is not available on the JDK build, should you record a benchmark of 0 ops/s? **No**, classify it as unsupported and consider compatibility.
14. When one JVM runs a single process for 200 ms and measures 5% faster than another JVM, can you conclude immediately? **No**, duration/variance/JIT are not yet suitable.
15. Does `allocatedMiB=703.1` in the lab mean `live set` is 703.1 MiB? **No**, that is total cumulative allocation.
16. If collector B achieves 20 ms p99 but exceeds the memory cap, does it fully pass the SLO? **No**.
17. Can per-run p99s be averaged and treated as pooled p99? **No**, a properly sample-weighted pooled histogram or reporting per-run distributions is required.
18. If GC logging is removed for ZGC while debug logging is enabled for G1, is the experiment fair? **No**, different overhead.
19. Which collector should be chosen before having data? **Do not rank definitively; start with an appropriate default, measure the actual workload, SLO, and budget**.
20. In the simulated scorecard in section 12, which candidate passes all three gates? **G1**, because throughput, p99, and peak memory all pass the hypothetical thresholds.

## 18. Official documentation sources

- Oracle Java SE 17, **Available Collectors** and collector selection guidance: https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html
- Oracle Java SE 17, **G1 Garbage Collector** and pause/throughput goals: https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html
- Oracle Java SE 17, **GC Tuning Guide**: https://docs.oracle.com/en/java/javase/17/gctuning/
- Oracle JDK 17, **`java` launcher options**, GC/heap flags, and JVM Unified Logging: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17, **`jfr`** command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Oracle JDK 17, **`jcmd`** command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle Java SE 17, **Java Flight Recorder API/module**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html
- OpenJDK JMH project (for benchmarking Java methods/micro-workloads): https://openjdk.org/projects/code-tools/jmh/

**Technical conclusion:** Comparing collectors must start from the **same workload and offered load, same CPU/memory budget, same JDK/binary, and same end-to-end latency targets**. GC pause, GC CPU, safepoint total, and request p99 are different metrics. Use **correctness, errors, throughput, p99/p99.9, and peak resource** thresholds to eliminate non-compliant configurations; only then weigh performance, throughput, memory, and operations. Do not crown the fastest collector from a short microbenchmark, a single run, or solely from GC pause logs.
