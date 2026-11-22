# Choosing a Garbage Collector: Throughput, Latency, CPU, and Memory Footprint

## Lesson Objectives

There is no single garbage collector (GC) that is always best for every Java application. A batch job may need to **process the most work per minute**, a transactional API may have to keep **p99 response time** low, while a small service container may be subject to strict **CPU quota and RAM** limits. Those requirements can conflict: a concurrent GC can reduce application pause times but uses additional CPU and memory bandwidth; a larger heap can reduce GC frequency but increases memory footprint; a throughput-oriented collector may accept longer pauses.

After this lesson, you will be able to:

- Define and accurately measure **throughput**, **latency (p50/p95/p99)**, **GC pause**, **GC CPU cost**, **allocation rate**, **live set**, **heap footprint**, and **process RSS**.
- Distinguish **Stop-The-World (STW) time fraction** from business throughput; understand why concurrent GC is not fully reflected in the STW fraction.
- Understand the impact of heap headroom, live-object ratio, object lifetime, large allocations, and memory pressure.
- Compare **Serial, Parallel, G1, ZGC, and Shenandoah** in HotSpot along with version/JDK distribution constraints.
- Build an **SLA/SLO-driven selection process**, rather than choosing a collector solely from a "fastest GC" slogan.
- Capture GC logs, JFR, metrics, and jcmd properly; design A/B experiments with warmup, realistic load, and identical CPU/RAM conditions.
- Interpret deterministic Java 17+ examples without fabricating environment-dependent GC numbers.
- Recognize common tuning pitfalls and strategies to reduce allocation/retention before switching collectors.

## 1. The Four Axes of Trade-offs

A collector affects at least four main axes:

| Axis | Operator's Question | Example Metrics |
| --- | --- | --- |
| **Throughput** | In a unit of time, how much useful work does the application complete? | requests/s, jobs/min, records/s, bytes/s |
| **Latency** | How long does a request take, especially at the tail of the distribution? | p50, p95, p99, p99.9, max response time; GC pause distribution |
| **CPU** | How much processing capacity does the collector take from the application and the system? | process CPU time, GC threads CPU, CPU quota throttling, cycles/op |
| **Memory footprint** | How much heap and total process memory is needed to be safe? | -Xmx, live heap, committed heap, RSS, native memory, headroom |

They are related, but **not identical**. For example, a system with very low p99 GC pause can still have high p99 request latency due to database, queueing, locks, CPU contention, or network. Conversely, good throughput does not mean an individual transaction was never paused by GC.

### Three Different Workload Examples

**Batch ETL:** processes 200 million records in the shortest time; can tolerate pauses of hundreds of milliseconds to seconds if the job does not serve immediate interactive requests. Throughput can be prioritized.

**Interactive REST API:** p99 from ingress to response needs to stay below a certain threshold, for example 150 ms. A single 250 ms GC pause can directly cause an SLO miss, yet **GC is not the only source** of tail latency. The full latency path must be observed.

**Many small JVMs on the same host/container:** each process only has 1 vCPU and a tight RAM limit. Dedicating too much CPU to concurrent GC or too much headroom to each JVM can reduce deployment density, even if pauses are small.

**First takeaway:** explicitly state the **useful SLO for users/business**, then choose the GC and heap size.

## 2. Defining Throughput: You Must State What Is Being Measured

In GC documentation, throughput is sometimes roughly described as **the fraction of time the program spends doing work rather than STW collection**. However, in real-world operations, the more important measurement is **the rate of completing useful work** under load and SLO.

Two related but distinct measurements:

~~~text
Application throughput:
  jobs_completed / wall_clock_seconds
  or requests_completed / elapsed_seconds

STW pause fraction (for reference only):
  sum(STW_pause_durations_within_window) / window_duration

Mutator available time fraction (approximate):
  1 - STW_pause_fraction
~~~

For example, in a 10-second window with total STW pauses of 0.3 seconds:

~~~text
Window                  = 10.0 s
Total STW pauses        =  0.3 s
STW pause fraction      =  3%
Approx mutator time     = 97%
~~~

**Do not claim "application throughput = 97%"** from those numbers alone. When GC runs concurrently:
- The collector still consumes CPU cores and memory bandwidth while mutators are not stopped.
- Read/write barriers can add extra instructions to the application's execution path.
- CPU contention can slow down request completion without appearing as an STW pause.
- JIT, application locking, I/O, and tail effects can change overall performance.

To evaluate business throughput, measure **completed work/s** and **saturation point**, while also recording the **error rate**. A program that fails fast may report a high requests/s number without actually completing useful work.

### Keep Load Constant When Comparing

Comparing two collectors at 500 requests/s is meaningless if one collector actually received 1000 requests/s in the other test. Distinguish between:
- **Offered load**: the rate at which clients attempt to send requests.
- **Completed throughput**: the rate at which the server successfully finishes requests.
- **Backlog/queue depth**: the number of waiting requests.
- **Latency distribution**: actual waiting + processing time.
- **Error/timeout rate**: the number of unsuccessful requests.

A collector that increases completed throughput while pushing p99 past the threshold can still **fail the SLO**. Choose according to the goal rather than ranking collectors by a single number.

## 3. Latency: Distinguish GC Pause from Response Time

**GC pause** is the duration for which the collector stops application threads due to a specific GC event (depending on logging format and phase). **Response time** of an HTTP request is the time from when the request is received/measured at a defined start point until the response is returned at a defined end point.

They are not equal.

~~~text
Request timeline (illustrative):

Ingress --> queue wait --> application CPU --> GC STW --> DB wait
        --> serialization --> network send --> response

Response latency = all segments in the measurement definition
GC pause latency = only the separately measured GC-induced pause
~~~

A request can miss p99 because of queueing under CPU throttling even when GC pauses are small. Conversely, a 100 ms GC pause can delay many requests at once and make **tail latency** worse than the individual pause duration due to queue buildup.

### What Are p50/p95/p99 Percentiles?

Given enough samples under the same definition:
- **p50**: approximate median; half of observations are no greater than this threshold under the chosen percentile rule.
- **p95**: approximately 95% of observations do not exceed the threshold.
- **p99**: approximately 99% of observations do not exceed the threshold.
- **p99.9**: focuses on rarer events, requiring a large sample size and an appropriate statistical method.

**Different percentile tools may use different algorithms/interpolation**, so exact numeric results can occasionally differ. When comparing, use the same method, the same time window, and the same request set. Do not mistake **p99 GC pause** for **p99 request latency**.

### A Logically Realistic Incident Example

A collector keeps 99% of GC pauses under 8 ms, yet still has one 400 ms stop-the-world pause in an hour. If the system has a p99.9 SLA under 100 ms or a very sensitive queue, that remaining tail may be enough to cause errors. Conversely, a collector with a few 60 ms pauses might not cause request p99 to miss if the application still has latency budget headroom and stable throughput.

A **necessary condition** is putting GC metrics onto the same timeline as service latency, CPU saturation, queueing, allocation pressure, and errors.

## 4. CPU: Total Cost, Concurrent CPU, and Quota

GC has two main kinds of work (not every collector splits them in the exact same way):

1. **STW work**: stops mutators so part of GC can process roots, references, copy/sweep/compact, etc.
2. **Concurrent/background work**: marking, remapping, refinement, relocation, or housekeeping while application threads continue running.

Two collectors with the same total STW pause fraction can consume very different amounts of CPU.

Hypothetical example:
- Collector A has 4% STW time and does almost no concurrent work.
- Collector B has 0.3% STW time, but uses a significant amount of CPU cores to mark/relocate concurrently.

You cannot conclude B has higher throughput just because STW is lower. If the machine has many idle cores, the concurrent CPU usage may be acceptable. If the container is only given **1 vCPU**, GC threads can contend heavily with application threads, increasing tail latency.

### Distinguish CPU Utilization

A process can use **200% CPU** on a system reporting "100% = one core" when running across two cores. Therefore, record:
- How many logical cores does the host have?
- What is the container CPU quota/cpuset?
- How many active processors did the JVM detect?
- Is CPU usage measured at the **process**, **container**, or **host** level?
- Is there CPU throttling?
- How many dedicated threads does the collector use?

OS/container tools (for example cgroup CPU throttling metrics) must be combined with Java GC data. Do not infer "fewer GC pauses means less CPU used" or "idle host CPU means the JVM is not hitting its quota".

### Memory Bandwidth Is Also a Resource

GC copying/evacuation, root scanning, and write barriers can increase:
- cache misses,
- memory bandwidth,
- work on the reference graph,
- dirty pages,
- CPU contention.

Even when CPU usage does not reach 100%, a system can still suffer from memory-bandwidth pressure or memory stalls. Choosing a GC must consider both **CPU/memory architecture** and how the application allocates data.

## 5. Memory: Heap Size Is Not the Entire Process Footprint

A JVM process needs more than just the Java heap:

~~~text
Process memory / RSS (illustrative)
  |
  +-- Java heap (objects/arrays, GC regions)
  +-- Metaspace / class metadata
  +-- Code cache / JIT-compiled code
  +-- Thread stacks / native thread-related memory
  +-- Direct ByteBuffers / native allocations
  +-- GC native metadata, card tables/remembered sets
  +-- Native libraries, runtime structures, memory mapping ...
~~~

Therefore, **`-Xmx=2g` does not mean process RSS will always stay under 2 GiB**. And a large committed heap does not mean live objects are using every byte. Some collector configurations keep more committed memory for reuse, and some have different uncommit mechanisms.

| Concept | Meaning | Caveat |
| --- | --- | --- |
| **-Xms** | Initial heap size per JVM flags | Not the total RAM used by the process. |
| **-Xmx** | Max Java heap | Does not limit all native memory of the process. |
| **Used heap** | Heap capacity the JVM considers in use | Not always live bytes after a full liveness analysis. |
| **Committed heap** | Memory the JVM has committed for the heap | Can be larger than used. |
| **Live set** | Reachable/live objects that must be retained | Varies by point in time and collector/measurement method. |
| **Allocation rate** | Bytes allocated over time | Can be very high even with a small live set. |
| **Heap headroom** | Margin between the heap budget and memory needed for live data, allocations, and collector work | An operational concept, not just a fixed subtraction. |
| **RSS / working set** | Memory the process/container actually occupies according to the OS | Includes off-heap memory and page reclaim nuances. |

### Headroom for Concurrent Collectors

A concurrent GC must reclaim memory while mutators **keep allocating**. If the rate of new object creation exceeds the collector's ability to finish a cycle or if destination capacity is insufficient, the system can experience **allocation stalls**, forced collections, or out-of-memory errors depending on the specific collector.

Memory that is too tight:
- causes GC to run frequently;
- reduces reserve space for relocated objects;
- increases the risk of falling back to more expensive execution paths;
- makes it harder to keep latency stable.

Conversely, increasing `-Xmx`:
- often reduces GC pressure for some workloads;
- but increases the memory budget, can increase footprint, and reduces deployment density;
- can increase the time needed to process a large live set or change GC behavior;
- does not fix a retention leak if the object graph grows without bound.

**Do not advise "just make the heap really large to reduce GC"** without first checking RAM quota, native memory, live set, and SLA.

## 6. Live/Dead Ratio Matters More Than the `new` Count

GC must process **live objects** according to the chosen algorithm. High allocation where objects die quickly can be handled relatively efficiently by collectors, especially in young-generation workloads. However, allocating too rapidly still consumes CPU/bandwidth and creates pressure.

Two scenarios:

**Workload A:** creates 2 GB of temporary byte arrays per interval, but keeps only 200 MB live. Young collection can reclaim most of the space, though the high allocation rate still causes work.

**Workload B:** low allocation rate, but has 10 GB of long-lived objects in a cache; every major cycle must handle a large amount of live data, which can put heavy strain on heap/headroom.

Therefore, metrics should be viewed together:
- bytes allocated/op and bytes/s,
- live heap after appropriate collections,
- object ages/lifetime histogram when available,
- humongous/large-object allocation rate,
- GC frequency, pause distribution, and CPU,
- total process memory and CPU quota.

**A "memory leak" in Java** is usually unintended retention of references. Switching from G1 to ZGC does not make reachable objects disappear on its own. When the problem is a leak, fixing cache/ownership/lifetime is usually more important than tuning the collector.

## 7. Overview of Serial, Parallel, G1, ZGC, and Shenandoah

The observations below describe **general design directions**, not an absolute ranking table. Algorithms and flags vary by JDK release/HotSpot vendor.

| Collector | Common Priority | Strengths | Trade-offs to Measure |
| --- | --- | --- | --- |
| **Serial GC** | Simplicity, small heap/workload, or very limited CPU | Low GC worker overhead, simple setup | STW and GC work with few threads; unsuitable for large pauses on large heaps |
| **Parallel GC** | Prioritizes **throughput** with parallel collection | Leverages multiple CPU cores for GC, good throughput in many batch workloads | STW pauses can be long; unsuitable for tight tail latency |
| **G1 GC** | Balances throughput and pause-time goal | Region-based, incremental evacuation, concurrent marking, pause target heuristic | Concurrent work, remembered-set/card overhead, evacuation/headroom, and humongous object considerations |
| **ZGC** | **Low-pause/low-latency** via concurrent GC | Heavy parts of marking/relocation are done concurrently; reduces STW contribution | CPU/bandwidth, barrier overhead, enough heap headroom to avoid stalls |
| **Shenandoah** | Low-pause with concurrent evacuation/compaction | Much of GC work executes concurrently with mutators | Increases concurrent/barrier work and memory headroom; availability/modes depend on JDK build |

### Serial GC

`-XX:+UseSerialGC` is a reasonable option to **test** for small programs, small heaps, or when only one CPU is available and pauses do not matter. It is not "a GC for old Java" in the sense that it cannot be used on modern JDKs. However, when the heap is large and latency is sensitive, performing collection in STW can cause long pauses.

### Parallel GC

`-XX:+UseParallelGC` is a throughput-oriented collector. Multiple GC worker threads help complete GC work during pauses; this can yield good throughput when the workload has many cores and can tolerate pauses. **GC parallelism does not turn the entire collection concurrent**; the application can still be stopped.

### G1

`-XX:+UseG1GC` is the default choice on **many modern HotSpot configurations**. G1 is designed to meet a pause target with high probability while maintaining good throughput; the pause target is a **soft goal**, not a hard SLA. G1 collects by regions; young/mixed collections involve evacuation, partially concurrent marking, and remembered-set/barrier overhead.

### ZGC

`-XX:+UseZGC` selects ZGC if supported by the JDK/VM build. ZGC is designed to perform heavy work concurrently to reduce application pause times, making it suitable for latency-sensitive workloads. However, low GC pause **is not free**: concurrent work and heap headroom can reduce throughput or increase RSS depending on the workload.

### Shenandoah

`-XX:+UseShenandoahGC` selects Shenandoah **on builds that support it**. It is a low-pause collector using concurrent work, but availability/flags/modes depend on the OpenJDK vendor and release. Do not assume "Oracle JDK, OpenJDK, and all distributions all have Shenandoah and the same set of flags".

## 8. Warning on Differences Across Java Versions: Especially ZGC

When putting commands into a README or playbook, specify the **target Java version**. For example:

~~~text
JDK 17:
  -XX:+UseZGC                 (non-generational ZGC on JDK 17)

JDK 21:
  -XX:+UseZGC -XX:+ZGenerational
    (selects Generational ZGC on JDK 21)

JDK 23:
  -XX:+UseZGC                 (generational mode by default per JEP 474)

JDK 24 and later with corresponding HotSpot:
  -XX:+UseZGC                 (non-generational ZGC has been removed)
~~~

This is a **version-by-version option map**, not a single monolithic runnable script. JDK 24 removed non-generational ZGC and the `ZGenerational` option, so **do not copy-paste** a JDK 21 command with `-XX:+ZGenerational` onto JDK 24+. Shenandoah also has generational developments and version-dependent flags.

A good practice:

~~~bash
java -version
java -XX:+PrintFlagsFinal -version
~~~

The second command can print a lot of flags. Do not guess the collector from the Java release year; record the **JDK build** and the **actual selected GC**. You can use `-Xlog:gc*=info` or `jcmd PID VM.flags` to aid investigation.

**Do not upgrade Java and reuse an old set of GC tuning flags without checking.** Defaults and algorithms can change significantly between Java 8, 17, 21, 24, and later releases.

## 9. Framing the Problem as an SLO Budget

Instead of asking "Which GC is fastest?", build a budget:

| Criterion | Example Requirement (Hypothetical) |
| --- | --- |
| Sustained throughput | At least 2000 successful requests/s |
| End-to-end p99 latency | No more than 120 ms at 2000 requests/s |
| Error/timeout rate | Under 0.1% |
| CPU budget | Do not exceed 4 vCPU quota, avoid sustained CPU throttling |
| Container RAM limit | 4 GiB |
| Headroom | No allocation stalls/Full GC/OOME during sustained load tests |
| GC pauses | GC-related pauses must not frequently consume most of the latency budget |
| Scale-out density | Number of instances needed to meet load within infrastructure budget |

**This is a pedagogical example, not a target applicable to every application.** All numbers must fit the actual service, container, and SLO. A successful GC decision must **simultaneously** satisfy throughput, latency, stability, and memory/CPU cost; if any critical item fails, you should not pick a collector just because it has a low median pause.

### Latency Budget

Suppose the p99 SLO = 120 ms, of which non-GC logic already typically takes 100 ms at target load. GC plus CPU contention only have a narrow margin before the total exceeds 120 ms. However, you cannot simply compute "p99 app = p99 business + p99 GC" in all situations because **distributions are correlated**, along with queueing and sampling windows. Use request tracing, event correlation, and load testing to measure the final distribution.

## 10. Scenario-Based Selection Matrix

| Scenario | Testing Starting Point | What to Check |
| --- | --- | --- |
| Small CLI tool, very short-lived, small heap | Default; try Serial if appropriate | Startup, overall runtime, GC worker overhead |
| Throughput-first batch, pauses of a few seconds acceptable | Parallel and default/G1 as baseline | Jobs/s, total CPU time, elapsed time, GC pause impact |
| Web API with moderate latency SLO | Default G1 as baseline | p99, pause distribution, remembered-set work, CPU/RSS |
| Transactional API with very tight p99 | Compare tuned G1 against ZGC or Shenandoah if build supports it | **End-to-end** tail latency, CPU/headroom, allocation stalls |
| Low-RAM container, many JVM instances | Baseline default/Serial/G1 depending on heap and CPU | RSS, native memory, memory.max, Full GC, OOME |
| Multi-GB heap, many long-lived objects | G1/ZGC/Shenandoah per SLA | Live set, concurrent work, headroom, marking speed |
| High allocation rate, temporary objects | G1/Parallel/ZGC per SLO; optimize churn first | Bytes/op, throughput, GC CPU, stalls |
| Large arrays/humongous objects | Baseline collector and allocation distribution analysis | G1 humongous regions, fragmentation, headroom |
| Low-latency but tight CPU quota | Do not default to a concurrent GC | CPU throttling, concurrent CPU, backlog, service p99 |

**Default recommendation:** start with the production JDK's default collector and a reasonable heap budget; only switch GC if data shows it fails to meet the SLO or cost target. The Oracle GC tuning guide also recommends starting from the default configuration unless there are specific requirements.

## 11. Heap Size: Both Too Small and Too Large Have Downsides

### When `-Xmx` Is Too Small

- Young/old collections occur frequently.
- Less evacuation/headroom for collectors that need to move objects.
- Allocation stalls or Full GCs may increase.
- For concurrent GCs, there is not enough room to finish a cycle before mutators exhaust memory.
- OOME can occur even without a memory leak, simply because the heap budget cannot accommodate the peak live set.

### When `-Xmx` Is Too Large

- Reserved/committed footprint can be high; deployment density drops.
- The live data set can still be large and GC must do more work.
- The application can hide a memory retention bug longer before it surfaces.
- Total process memory can be pushed past container RAM due to **off-heap** usage.
- With some collectors/configurations, changing the heap changes generation sizing/GC cycles.

Do not conclude "a larger heap always means longer GC pauses" or "a larger heap always means better latency": the relationship depends on the collector and workload. Measure a **range of heap sizes** under real load and find the point that satisfies both headroom and memory cost.

### Should `-Xms` and `-Xmx` Be Equal?

Setting initial/max heap equal can reduce resizing activity and make behavior more predictable in some workloads, but it keeps committed/reserved memory high from the start depending on VM behavior and is not always good for a memory-constrained fleet. Different collectors have different uncommit mechanisms. Do not turn `-Xms=-Xmx` into a universal rule for every application.

## 12. Commonly Used Flags and Their Limits

| Flag | Role | Common Mistake |
| --- | --- | --- |
| `-Xms256m` | Initializes Java heap around 256 MiB | Treating it as total process memory. |
| `-Xmx2g` | Caps max Java heap | Treating it as the RSS/container limit. |
| `-XX:+UseParallelGC` | Selects Parallel GC | Promising lower p99 than G1 across all workloads. |
| `-XX:+UseG1GC` | Selects G1 | Treating the pause target as an SLA guarantee. |
| `-XX:+UseZGC` | Selects ZGC if supported | Assuming zero overhead or that all JDKs have the same mode. |
| `-XX:MaxGCPauseMillis=200` | Pause-time target for supporting collectors, especially G1 | Reading it as "no pause will ever exceed 200 ms". |
| `-XX:MaxRAMPercentage=...` | Uses a percentage of available RAM detected by the JVM to derive the heap limit | Forgetting native memory and cgroup headroom. |
| `-XX:ActiveProcessorCount=...` | Overrides the processor count the JVM uses for some heuristics | Using it to mask a CPU quota instead of finding saturation. |
| `-Xlog:gc*:file=gc.log:time,uptime,level,tags` | Enables GC unified logging with level and file destination | Not limiting log rotation/size on long-running processes. |

This is an **orienting** list, not a requirement to enable everything at once. Flag availability/semantics can change across releases. For example, `MaxGCPauseMillis` is a **heuristic tuning goal**, not a hard timer forcing GC to return.

### Avoid Arbitrary Young-Generation Sizing with G1

G1 uses young generation size as one of its levers to balance pause target and throughput. Forcing `-Xmn` or legacy generation flags can restrict G1's ability to self-adapt. Better approach:
1. Set appropriate heap bounds.
2. Measure logs and latency first.
3. If needed, adjust **one** goal such as `MaxGCPauseMillis`.
4. Check the throughput/CPU/GC frequency trade-off after each change.

**Do not optimize an isolated pause while ignoring overall system efficiency.**

## 13. Java 17+ Example: Computing Throughput and Percentiles from Fixed Data

A small example that **only teaches how to calculate metrics**, without generating machine-dependent GC numbers:

Create the file **`GcMetricMathDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public class GcMetricMathDemo {
    static long nearestRank(long[] sorted, double fraction) {
        int rank = (int) Math.ceil(fraction * sorted.length);
        return sorted[Math.max(0, rank - 1)];
    }

    public static void main(String[] args) {
        long[] latenciesMs = {5, 7, 8, 9, 10, 11, 12, 13, 30, 90};
        Arrays.sort(latenciesMs);

        long completed = 9_500L;
        double windowSeconds = 10.0;
        double stwSeconds = 0.30;

        System.out.printf(Locale.ROOT, "throughput=%.1f req/s%n",
                completed / windowSeconds);
        System.out.printf(Locale.ROOT, "stwFraction=%.1f%%%n",
                100.0 * stwSeconds / windowSeconds);
        System.out.println("p50=" +
                nearestRank(latenciesMs, 0.50) + "ms");
        System.out.println("p90=" +
                nearestRank(latenciesMs, 0.90) + "ms");
        System.out.println("p99=" +
                nearestRank(latenciesMs, 0.99) + "ms");
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 GcMetricMathDemo.java
java GcMetricMathDemo
~~~

**Exact stdout:**

~~~text
throughput=950.0 req/s
stwFraction=3.0%
p50=10ms
p90=30ms
p99=90ms
~~~

Explanation:
- 9,500 completed jobs in 10 seconds → **950 req/s**.
- 0.3 seconds of STW over 10 seconds → **3%** under the simple model.
- With **nearest-rank percentile**, p50 is the 5th element, p90 is the 9th, and p99 is the 10th of the 10 samples.
- **10 samples are not enough** to represent real production p99; this example only clarifies the formula. You need an appropriate time window, sample count, and histogram.
- Do not take 3% STW to mean business throughput would increase by 3% if GC were removed, because concurrent CPU, queueing, cache effects, and other bottlenecks still exist.

## 14. Java 17+ Example: Object-Allocating Workload to Test GC

A program can create many arrays and retain a small fraction to test collectors **on the same logical data**. However, GC scheduling, pause counts, and timings depend on the machine/JDK/heap, so stdout only guarantees the business outputs written deterministically.

Create the file **`GcAllocationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GcAllocationDemo {
    private static volatile byte[] latest;

    public static void main(String[] args) {
        List<byte[]> survivors = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 100_000; i++) {
            byte[] data = new byte[1_024];
            data[0] = (byte) i;
            checksum += Byte.toUnsignedInt(data[0]);

            if ((i % 128) == 0) {
                survivors.add(data);
            } else {
                latest = data;
            }
        }

        System.out.println("survivors=" + survivors.size());
        System.out.println("checksum=" + checksum);
    }
}
~~~

Run on **JDK 17+**:

~~~bash
javac --release 17 GcAllocationDemo.java
java -Xms32m -Xmx128m -XX:+UseG1GC GcAllocationDemo
~~~

**Exact business stdout** (excluding GC logs if enabled):

~~~text
survivors=782
checksum=12742320
~~~

Why this program is meaningful:
- Each iteration creates a byte array; total logical allocation payload is about 100,000 × 1,024 bytes, though **actual allocated bytes** also include object headers, alignment, and JIT effects.
- Every 128 iterations, one array is kept in the list, meaning 782 survivors are referenced by the collection at the end of the loop.
- The `latest` field is declared `volatile` and holds the most recent reference from unretained iterations; it does not guarantee that GC will run at an exact moment or that every array must be physically allocated in every JIT mode.
- The checksum depends only on the repeating byte sequence 0..255, not on the GC collector.
- **Do not compare performance using stdout here**; measuring performance requires a test with setup, warmup, iteration counts, multiple runs, and proper tools.

### Running the Same Program with Different Collectors

For example, on JDK 17+ with G1 and Parallel:

~~~bash
java -Xms32m -Xmx128m -XX:+UseParallelGC GcAllocationDemo
java -Xms32m -Xmx128m -XX:+UseG1GC GcAllocationDemo
~~~

On JDK 21, you can compare Generational ZGC:

~~~bash
java -Xms32m -Xmx128m -XX:+UseZGC -XX:+ZGenerational GcAllocationDemo
~~~

**Warning:** the 128 MiB heap in this example is only a test configuration for a small workload, **not a recommendation of sufficient headroom for ZGC in all situations**. If a JDK/VM does not support that option or fails under a constrained configuration, check the flags/version and increase the budget to match test conditions; do not assume the algorithm itself is always broken.

With JDK 24+ (where generational ZGC is the only mode), use only `-XX:+UseZGC` instead of keeping the removed `-XX:+ZGenerational` flag.

### Can You Force GC an Exact Number of Times?

**No.** `System.gc()` is not a mechanism that guarantees one STW, one compaction, or a fixed GC event type. Do not write textbook examples promising an identical pause count, GC count, or milliseconds across all machines.

## 15. Enabling GC Logs and Reading Them Properly

For the compiled workload, for example:

~~~bash
java -Xms32m -Xmx128m -XX:+UseG1GC -Xlog:gc*:file=gc.log:time,uptime,level,tags GcAllocationDemo
~~~

The GC log file `gc.log` can contain lines about initialization, pauses, region usage, and heap transitions depending on the HotSpot build/flags. **There is no immutable exact GC stdout** because scheduling and allocation behavior depend on the runtime. It is also possible for a program to be too short or the heap large enough that fewer events occur than expected.

You should record:
- The actual selected collector name.
- The JVM build and all JVM args.
- Timestamps, GC IDs, phases, and durations.
- Heap occupancy before/after GC, frequency, and pause maxima/percentiles.
- Concurrent GC cycle work and signs of allocation stalls/failures.
- G1: young/mixed/full events, and remembered-set/ref-processing phases if needed.
- ZGC/Shenandoah: phases/concurrent work/stalls according to the JDK version's tags/format.

**A `Pause Young` line in G1 is normal operation**, not an incident by default. **Repeated Full GCs**, allocation stalls, or unusually long pauses relative to the SLO are what warrant investigation.

### Log Rotation for Long-Running Processes

Example with HotSpot unified logging (adjust to your environment):

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -Xmx512m -XX:+UseG1GC GcAllocationDemo
~~~

Check the syntax of decorators/rotation options for your JDK version. GC logs can grow large, so define retention and access permissions; never write unbounded logs to a production disk.

## 16. JFR, jcmd, and the Metrics to Collect

To see a broader picture than GC pauses alone, use **JFR (Java Flight Recorder)** and HotSpot diagnostics. Example interactive commands for a **running Java process**—replace `PID` with the actual PID before executing:

~~~bash
jcmd PID VM.flags
jcmd PID GC.heap_info
jcmd PID JFR.start name=GCStudy settings=profile duration=60s filename=gc-study.jfr
jcmd PID JFR.check
~~~

This is illustrative syntax with a `PID` placeholder that must be replaced, **not** a literal `PID` command. Diagnostic names and argument syntax can differ between JDK builds.

Another way is to start the recorder at launch (where supported by the JDK):

~~~bash
java -XX:StartFlightRecording=filename=gc-study.jfr,duration=60s,settings=profile -Xmx512m GcAllocationDemo
~~~

These commands can write large JFR files containing application data; protect access permissions just like other diagnostic artifacts. A 60s recording duration may be longer than the demo application runs, so **do not promise a full 60s recording** if the process exits early.

When suspecting **object retention/leak** rather than a pause problem, you can inspect a class histogram:

~~~bash
jcmd PID GC.class_histogram
~~~

Or a heap dump after evaluating the impact on the process:

~~~bash
jcmd PID GC.heap_dump filename=gc-study.hprof
~~~

**Warning:** class histograms and heap dumps can cause high impact/pauses, and heap dumps can contain secrets/PII. Do not capture or copy them in production without authorization and a data-handling plan.

### Which Metric Answers Which Question?

| Tool/Source | Answers Well | Insufficient to Conclude |
| --- | --- | --- |
| GC unified logs | Pause events, heap transitions, GC phase metrics | Request p99, CPU throttling, and total native memory |
| JFR | GC, allocation samples, threads, CPU/runtime events per configuration | Not every event is enabled/sampled at 100% |
| jcmd GC.heap_info | Current heap state | Retained owner graph, p99 |
| Class histogram | Count/bytes by runtime class | Who is keeping objects reachable |
| Heap dump + dominator | Retainers/paths to GC roots | Latency/time spent in requests |
| Service metrics/tracing | Successful RPS, p99, errors, queue depth | GC algorithm root cause if only service metrics are measured |
| Container/OS metrics | CPU quota, throttling, RSS/OOM killer | Distinguishing heap/native/GC phases in isolation |
| Load-testing tool | SLO at a fixed offered load | Production performance if the traffic model is unrealistic |

**Correlate on the same timeline**: did a GC pause at 10:00:03 cause the request spikes, or did the spikes come from DB/network/CPU throttling in the same window?

## 17. Controlled GC Selection Experiment

A reliable A/B process:

**Step 1 — Define constraints:** workload, API SLA, p99/p99.9, desired throughput, error budget, CPU quota, RAM/RSS budget, peak traffic, and sustained load duration.

**Step 2 — Run the baseline:** use the default collector or current production collector, record JDK version, heap flags, CPU limits, traffic distribution, GC logging/JFR. Measure after warmup.

**Step 3 — Change only one primary factor:** test Parallel, G1, ZGC, or Shenandoah (if supported), keeping the application, dataset, offered load, and CPU/memory budget unchanged.

**Step 4 — Test multiple load levels:** typically low load, target load, peak, and burst. Run long enough to observe aging/old-gen cycles, cache growth, and concurrent GC cycles.

**Step 5 — Collect full distributions:** RPS, latency p50/p95/p99/p99.9, error rate, GC pause histogram, GC CPU, total process CPU, throttling, RSS, heap after GC, allocation stalls.

**Step 6 — Repeat runs:** warmup/JIT, CPU frequency, cache/cgroup sharing, and GC scheduling can introduce noise. A single good run is not enough to conclude.

**Step 7 — Select by constraints:** eliminate any configuration that violates an SLO/budget; among the rest, compare total cost and stability.

**Step 8 — Production canary:** verify with real traffic, CPU/GC/OOM alerts, a rollback plan, and ensure diagnostic logs do not exceed the disk budget.

A **Pareto frontier** is more useful than "the best GC": a configuration with higher throughput but worse p99 may not *dominate* another; depending on the SLA, each configuration fits a different goal.

### Avoid Biased Comparisons

- Do not run Parallel with `-Xmx=8g` while limiting ZGC to `-Xmx=512m` and conclude which collector is better.
- Do not compare warmed-up G1 against ZGC on its very first run.
- Do not compare only on a multi-core local machine when the production container has only a 1 CPU quota.
- Do not look only at average latency if the business SLO is p99.
- Do not look only at GC pause time and forget throughput and total CPU.
- Do not look only at heap usage when the container OOMs due to direct buffers, stacks, or metaspace.
- Do not treat a synthetic allocation benchmark as sufficient evidence for a data-access/database workload.

## 18. Analyzing Results with a Hypothetical Matrix

The table below uses **hypothetical numbers for learning how to make decisions**, not real benchmarks or data from any specific JVM:

| Metric at Fixed Offered Load | Parallel | G1 | ZGC |
| --- | ---: | ---: | ---: |
| Successful throughput | 2,300 req/s | 2,180 req/s | 2,050 req/s |
| Application p99 latency | 240 ms | 115 ms | 78 ms |
| Total process CPU | 2.8 cores | 3.1 cores | 3.7 cores |
| RSS | 2.1 GiB | 2.5 GiB | 3.0 GiB |
| Full GC / stalls | Not observed in window | Not observed | Not observed |

Depending on constraints:
- **Batch job without low-latency needs:** Parallel can be good if jobs/s is the primary goal.
- **API p99 must be under 120 ms, CPU ≤3.5 cores, RSS ≤2.8 GiB:** G1 is the **candidate that satisfies the example**; Parallel exceeds p99 and ZGC exceeds CPU/RSS.
- **API p99 under 90 ms, CPU ≤4 cores, RSS ≤3.5 GiB:** ZGC could be a candidate in this hypothetical table, though stability and peak tests are still needed.
- **If all exceed budget at peak:** do not force a GC choice; reduce allocation/retention, scale out, adjust heap/quota, or revisit the SLO/architecture.

This is an exercise in **reading a multi-objective matrix**. Do not use these illustrative numbers as CPU/RAM sizing advice or as predictions of real-world G1/ZGC performance.

## 19. Causes That Often Matter More Than Switching GC

### Creating Too Many Objects

Autoboxing, intermediate collections, serializers, regex/JSON objects, string concatenation patterns, and temporary buffers can inflate the allocation rate. Use JFR allocation profiling, valid benchmarks, and hotspot optimization to reduce work for all collectors.

### Excessive Retention / Caches

Unbounded caches without eviction, long-lived collections, listener registrations, thread locals, and large payload references can keep live heap near `-Xmx`. Every collector must keep reachable objects. Use a heap dump + dominator tree to find the owners.

### CPU Throttling in Containers

If the cgroup frequently throttles CPU, a concurrent collector may fail to finish marking fast enough or may increase queueing in request processing. You must tune quota, concurrency, GC selection, and the application; `MaxGCPauseMillis` alone will not solve it.

### Too Many Threads / Native Memory

Many thread stacks, direct buffers, and metaspace can push RSS past the memory quota even when the Java heap has free space. Measure native memory/OS metrics, review thread management and container limits; do not just increase the heap.

### Large/Huge Allocations

G1 can handle **humongous objects** differently from small objects, putting pressure on contiguous regions and headroom. Reducing temporary large buffers or restructuring data can be more effective than switching collectors. However, do not manually split arrays into chunks if that causes extra copies and application complexity without measuring first.

## 20. Common Mistakes When Choosing a GC

| Claim | Why It Is Incorrect |
| --- | --- |
| "ZGC has low pauses so it is always fastest." | Concurrent CPU, memory headroom, and barrier overhead can reduce throughput. |
| "Parallel prioritizes throughput so every batch job must use it." | Depends on heap/live set/cores; default or G1 can also perform well. |
| "G1 MaxGCPauseMillis=50 means every pause ≤50 ms." | It is a soft target, not a hard deadline. |
| "GC p99 pause=10 ms so API p99 ≤10 ms." | Request latency also includes application work, I/O, queueing, and concurrent CPU. |
| "1% STW fraction means application throughput is 99%." | That is only an available-time approximation, ignoring concurrent GC and other costs. |
| "Heap -Xmx=2g means a 2g container is enough." | RSS includes metaspace, code cache, stacks, direct buffers, and GC native overhead. |
| "High RSS proves a Java heap leak." | Could be native/committed memory or page caching; they must be separated. |
| "Few GC events means a good collector." | Rare but very long events can still cause p99 spikes. |
| "Concurrent GC never stops the application." | There are still short pauses/safepoints/handshakes depending on the collector. |
| "Host CPU is 50% idle so the container is not throttled." | Container quota can throttle independently of host idle cores. |
| "Lowering -Xmx always saves RAM without affecting latency." | Can increase GC frequency and allocation stalls/OOME. |
| "Increasing -Xmx always reduces latency." | Involves trade-offs in footprint, live set, and collector scheduling. |
| "A 30-second benchmark is enough for any long-lived workload." | Misses old-gen cycles, aging, leaks, and peak behavior. |
| "Use the same ZGC flags for JDK 17, 21, 24, and 26." | Generational modes/options changed across releases. |
| "Shenandoah is available on every HotSpot distribution." | Availability depends on build/vendor/version. |
| "G1 is the default so it is always optimal." | The default is balanced, not optimal for every specific workload. |
| "A single System.gc() call measures GC objectively." | Does not guarantee GC type/timing, and affects warmed state and collector policies. |
| "GC logs alone tell you business throughput." | Separate service counters/completed work and latency metrics are required. |
| "Tune GC with a flag while changing code/heap at the same time." | You cannot tell which change had an effect; uncontrolled comparison. |
| "Lowering average pause is enough to meet p99." | Tail latency requires measuring the distribution; the mean can hide outliers. |

## 21. Self-Check Questions

**1.** If total STW time is 0.5 seconds in 10 seconds, can you claim application throughput is 95%?

**Answer:** No. You can say the STW pause fraction is about 5%; application throughput must be measured as successful work/s, and concurrent GC also uses CPU.

**2.** Are p99 GC pause and p99 HTTP response latency the same metric?

**Answer:** No. They measure two different populations; correlation and request SLOs are needed.

**3.** Why can ZGC use more CPU while having lower pauses?

**Answer:** More GC work is done concurrently, along with barrier/coordination overhead and memory bandwidth; reducing STW work can trade off for work while mutators are running.

**4.** When a container only has 1 vCPU, should you default to a GC with many concurrent threads?

**Answer:** No. Measure CPU competition/throttling and application p99 first; throughput or latency may be impacted.

**5.** Can you set `-Xmx=4g` in a container with a 4 GiB RAM limit and guarantee it will not be OOMKilled?

**Answer:** No. Beyond the Java heap, there are native memory, metaspace, code cache, thread stacks, and runtime overhead.

**6.** Why is the G1 pause-time target not treated as an SLA?

**Answer:** `MaxGCPauseMillis` is a heuristic goal, not a mandatory limit for every event.

**7.** Should you choose Parallel or ZGC for a batch job with no latency SLO?

**Answer:** Measure throughput/CPU/RSS on the real workload; Parallel is a throughput-first candidate, though not guaranteed to win.

**8.** What adverse effects can increasing the heap cause?

**Answer:** It can reduce collection frequency, but increases footprint/density cost, changes collector behavior, and masks retention.

**9.** Can a large live set with a low allocation rate still make GC expensive?

**Answer:** Yes. The collector still needs to scan/copy/mark many live objects according to its algorithm and needs headroom.

**10.** What metrics should you collect when suspecting allocation stalls?

**Answer:** GC logs with stall/failure markers, heap before/after, allocation rate, concurrent GC timing, CPU quota, and free headroom.

**11.** When should you use a heap dump instead of only GC logs?

**Answer:** When you need to find object graph retention, dominator/GC-root paths, or suspect a leak. Heap dumps have overhead and contain sensitive data.

**12.** Can the goal "request p99 <100 ms" be proven solely by p99 GC pause <10 ms?

**Answer:** No. You must measure end-to-end p99 at target load and check other bottlenecks.

**13.** Which flag enables generational ZGC on JDK 21?

**Answer:** `-XX:+UseZGC -XX:+ZGenerational` on supported JDK 21. From JDK 24 onward, do not use `ZGenerational` because non-generational mode was removed.

**14.** Why must the same collector still be re-benchmarked between JDK 17 and JDK 25?

**Answer:** GC algorithms, heuristics, flags, JIT/compiler, VM defaults, and container awareness can change.

**15.** Is a test run with high throughput but 5% errors good?

**Answer:** No, if the SLO error budget is lower. Completed successful work and correctness are what matter.

## 22. Memory Map

~~~text
                 APPLICATION GOALS / SLO
                           |
         +-----------------+------------------+
         |                 |                  |
      THROUGHPUT         LATENCY          RESOURCE BUDGET
      requests/s          p99/p99.9         CPU + RAM/RSS
         |                 |                  |
         +-----------------+------------------+
                           |
                     BASELINE DEFAULT GC
                           |
                   MEASURE WORKLOAD
             GC logs + JFR + service metrics
                  + container/OS metrics
                           |
               +-----------+-----------+
               |                       |
         Throughput first          Low latency first
               |                       |
         Parallel candidate        G1 / ZGC / Shenandoah
               |                       |
               +-----------+-----------+
                           |
                    HEADROOM / LIVE SET
                    ALLOCATION / GC CPU
                    ERRORS / STALLS / RSS
                           |
                   RUN CONTROLLED A/B
                           |
                   DOES IT MEET ALL SLOs?
                     /              \
                    NO              YES
                    |                |
             TUNE / FIX /         CANARY + MONITOR
             TRY ANOTHER
                           |
                  OPTIMIZE THE SYSTEM,
                 NOT JUST ONE GC NUMBER
~~~

**Core takeaway:** choosing a GC is a **multi-objective problem**, not minimizing a single pause. Throughput, tail latency, CPU quota, RSS, live set, and heap headroom all interact. **Parallel** is often a throughput-first candidate, **G1** aims for balance, and **ZGC/Shenandoah** are low-pause candidates when supported, but results must be confirmed with real workloads and SLOs. Measurement, budget limits, and controlled comparisons are more reliable than any "fastest collector" promise.

## Official References

- [Oracle Java SE 21 — Available Collectors, GC selection guide](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html).
- [Oracle Java SE 21 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector-tuning.html).
- [Oracle Java SE 21 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html).
- [Oracle Java SE 21 — HotSpot GC Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/).
- [Oracle Java SE 21 — The java Command, GC logging and JVM flags](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle Java SE 21 — jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [OpenJDK JEP 439 — Generational ZGC](https://openjdk.org/jeps/439).
- [OpenJDK JEP 474 — Generational ZGC by Default](https://openjdk.org/jeps/474).
- [OpenJDK JEP 490 — Remove Non-Generational ZGC](https://openjdk.org/jeps/490).
- [OpenJDK JEP 189 — Shenandoah GC](https://openjdk.org/jeps/189).
- [Java Flight Recorder — Java SE 21 documentation](https://docs.oracle.com/en/java/javase/21/jfapi/).
