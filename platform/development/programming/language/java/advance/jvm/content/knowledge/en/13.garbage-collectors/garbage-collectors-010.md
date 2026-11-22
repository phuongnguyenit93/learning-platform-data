# GC Pause-Time Goal Is an Optimization Target, Not a Real-Time Guarantee

`-XX:MaxGCPauseMillis=50` means **the JVM is asked to try to tune the garbage collector so that pauses fit within a 50 ms target**. It does **not** mean “every GC will definitely be shorter than or equal to 50 ms”, and even less does it mean “every Java request will respond within 50 ms”. This is an important boundary between **statistical/heuristic GC tuning** and **real-time guarantees (hard real-time deadline)**.

According to the **Oracle Java SE 17 – Ergonomics** documentation, `-XX:MaxGCPauseMillis=<n>` is a **hint**: the GC adjusts heap, generation sizes, or related parameters to *try* to keep pauses shorter than the target; **in some cases it cannot be achieved**. For Java 17 G1, the default GC pause goal is **200 ms** in the configuration described by the documentation. This default is **not an SLA** and does not guarantee at all that G1 will not have pauses over 200 ms.

This article belongs to the **Garbage Collectors** group in the JVM, focusing on explaining the exact semantics of the pause-time goal, how the GC decides how much work to do in a pause, the trade-offs between **latency – throughput – heap footprint**, reasons for exceeding the target, how to use **GC logs/JFR/safepoint logs**, and the process of evaluating SLAs based on actual metrics. The **Java 17+** examples have deterministic stdout for the business logic part, while GC time values **are recorded rather than fabricated**.

## 1. What Is Pause Time? It Is Not Total Application Latency

**GC pause time** is the duration during which application threads are stopped or unable to continue normal work due to a collection phase requiring stop-the-world (STW). A collector can have several types of work:

- **Stop-the-world pause:** mutator threads pause while the GC performs a phase requiring consistency.
- **Concurrent GC work:** some GC threads work while mutators still run, but they compete for CPU/memory bandwidth.
- **Parallel GC work:** multiple worker threads perform GC work simultaneously; if this is an STW phase, the application is still paused.
- **Non-GC safepoint:** the JVM also has internal activities requiring safepoints or thread handshakes; this stop time is not necessarily counted the same as a GC pause in the log.

**Application latency** or **request response time** is the time between the input event and the result reaching the caller. It can include queuing time, network, thread scheduling, lock contention, I/O, JIT/class loading, CPU processing, and GC impact.

```text
A single request (illustration)
request arrived ──────────────────────────────────────────► response sent

   queue      business code       GC pause      business code   network
   ────┬──────────┬───────────────┬──────────┬───────────────┬──────
       │          │               │          │               │
       └──────────┴───────────────┴──────────┴───────────────┘
                      end-to-end latency

GC pause target = target for one type of JVM pause.
Request SLA     = requirement measured across the ENTIRE request path.
```

Not all GC activity directly pauses every request. Concurrent GC can reduce CPU headroom causing indirect slowdowns; threads not processing a request during a GC pause do not necessarily experience a corresponding request latency spike. However, for a live service, a sufficiently long STW pause can push many requests past the tail-latency budget.

### 1.1. Different Metrics Must Not Be Used Interchangeably

| Metric | What Does It Measure? | What It Does Not Represent |
| --- | --- | --- |
| GC pause duration | An event where the JVM stops mutators to perform GC | Entire request response time |
| Maximum GC pause | Longest pause in the observation window | Guarantee that future pauses will not be higher |
| GC pause p95/p99 | Percentile of measured pause events | Request p95/p99 |
| Total GC pause time | Total duration of multiple pauses in the window | Total CPU time of GC workers |
| GC overhead | Percentage of time spent on GC per measurement/documentation | All application CPU cost and background GC |
| Application p99 latency | Response time at the 99th percentile of requests | GC time alone |
| Deadline miss rate | Percentage of requests missing the deadline | Does not by itself indicate GC is the cause |
| Throughput | Work completed per unit of time | Response time guarantee for each request |

A batch job may tolerate a 500 ms pause if total processing time is low; an endpoint with a 100 ms deadline may not tolerate even a few such pauses.

## 2. The Pause-Time Goal Is a Soft Goal

In Java 17 HotSpot:

```bash
-XX:MaxGCPauseMillis=50
```

means “ask the GC to try to achieve a maximum pause of about 50 milliseconds according to collector policy/behavior”:

- **50** is **milliseconds**, not microseconds, thread count, GC count, or percentage.
- The JVM uses **statistics from previous collections** and collector heuristics to choose certain parameters/workloads.
- The GC can self-adjust young generation size, the set of regions processed in a pause, and decisions appropriate to the collector.
- The goal does not force the GC to unsafely abort work mid-way when the clock hits 50 ms.
- A pause can be **shorter than, equal to, or longer than** the target; the runtime remains valid if it exceeds it.
- There is no standard Java API that turns this flag into a **hard real-time scheduling guarantee**.

Oracle Java 17 describes the HotSpot GC pause goal as using weighted average/variance to track the likelihood of meeting the goal. This is a **tuning decision based on history and prediction**, not an oracle algorithm that knows in advance the live object count, graph edges, CPU scheduler delay, or I/O time.

### 2.1. “Max” in the Flag Name Is Not a Hard Barrier

Some people read the name `MaxGCPauseMillis` and deduce:

```text
Set -XX:MaxGCPauseMillis=20
⇒ JVM never pauses the application for more than 20ms
⇒ requests never exceed 20ms
```

**Both inferences are false.** In the context of tuning, `Max` is a flag name specifying the **desired target value**. If the GC needs to process a phase that cannot be paused/split further without violating correctness, or other real-world conditions cause the time to exceed the prediction, it **can exceed it**.

“Meeting the goal with high probability” in a workload is not “meeting it absolutely for every event” and is not a certification that the system has hard real-time properties.

### 2.2. A 50 ms Goal, Yet One GC Takes 120 ms — Is the JVM Broken?

**Not necessarily.** For example:

```text
GC(10) Pause Young ... 21.8ms
GC(11) Pause Young ... 33.5ms
GC(12) Pause Young ... 120.4ms  ← exceeds 50ms goal
GC(13) Pause Young ... 27.1ms
```

These are **hypothetical numbers for explanation**, not actual output from a program run in this article. A 120.4 ms pause may reflect a larger live set than predicted, CPU starvation, reference processing, remembered-set work, or other factors. To conclude, one must inspect **detailed logs of the same GC id**, CPU/memory resource contention, and collector-specific phase data.

There is no rule that “one exceedance means the flag is not applied” or “increasing GC worker threads will definitely fix it”.

## 3. How Does HotSpot G1 in Java 17 Adjust Pauses?

**G1 (Garbage-First)** divides the heap into many **regions**, and the young generation is a resizable set of Eden/Survivor regions. Instead of collecting the entire Old generation every time, it typically performs:

- **Young-only evacuation pauses** to collect Eden/Survivor.
- **Concurrent marking** to estimate the liveness of old regions (with appropriate stop points in the cycle).
- **Mixed GC pauses** consisting of young + a selected set of old regions after marking.
- **Full GC** or special handling paths when normal progress/allocation capacity is no longer sufficient.

G1 uses cost prediction and **collection set (CSet) selection** to control the expected amount of work processed in a pause; **young region sizing** is one of the primary means.

```text
Observed inputs from previous collections:
  object survival rates
  amount of live bytes to evacuate/copy
  remembered-set scanning work
  region/cset costs
  CPU workers / heap headroom
                 │
                 ▼
        G1 pause prediction
                 │
                 ▼
   Adjust young Eden region count
   Select candidate old regions in mixed phase
                 │
                 ▼
   Actual GC pause (STW) ──► log duration
                 │
                 └── feedback for subsequent decisions
```

**This is a heuristic model**. The collector does not know the future for sure: allocation bursts, a sudden large live set, concurrent workloads, and system pressure can make predictions wrong.

### 3.1. Why Isn’t G1’s Default 200 ms “Every Pause 200 ms”?

According to the Oracle Java 17 G1 GC Guide, `-XX:MaxGCPauseMillis=200` is the **ergonomic default pause-time goal**. It is an input value for G1 to adjust its decisions, not a timer that aborts a collection after 200 ms.

A JVM using default G1 can:

- Typically observe pauses under 200 ms in favorable workloads.
- Occasionally see larger outliers for various reasons.
- Encounter a Full GC or an evacuation pressure situation different from normal young evacuation predictions.
- Have poor application p99 latency even when all measured GC pauses are under 200 ms, because the request bottleneck lies elsewhere.

**When establishing an SLA, you must use the measured pause distribution on the target environment**, not take the default GC flag as a product guarantee.

### 3.2. The Role of Young Generation Sizing

A large young generation:

- Can reduce Young GC frequency because there is more allocation space before collection is needed.
- Can cause each collection to inspect/copy more live objects, increasing pause time.
- Can improve overall throughput if most objects die young.

A small young generation:

- Can reduce the amount of work in a single pause.
- But can cause GC to happen more frequently, increasing total GC overhead.
- Can increase promotion pressure if survivor sizing is unsuitable.

G1 uses adaptive young generation sizing to balance these according to the pause goal. Therefore, Oracle documentation **recommends against forcing a fixed young size with `-Xmn`, `-XX:NewRatio`, or similar flags** when relying on G1 to meet a pause-time target: locking the young size can break an important tuning mechanism of G1.

### 3.3. Mixed GC Can Exceed Predictions Due to Uneven Work

The difficulty of each region is not equal: the same number of bytes containing objects can have different numbers of references and remembered-set scanning costs. Nor do all old regions have the same amount of live data. G1 selects regions to maximize reclaim efficiency within the predicted pause, but **cannot guarantee actual cost matches the model**.

If an application has a complex interconnected object graph, many cross-region pointers, or unexpected liveness changes, pauses can be longer than expected. One must read actual phases/metrics rather than guessing solely from total heap used.

### 3.4. Is Full GC Strictly Bounded by `MaxGCPauseMillis`?

**No.** `MaxGCPauseMillis` is a tuning goal applied by policy. A Full GC may require work across a much broader scope than routine predicted young/mixed CSets, which can cause **much longer pauses** under heap pressure/failure conditions.

There is no “GC timeout” in the Java specification that allows the JVM to preserve the object graph by arbitrarily stopping a collection mid-way and safely returning control if required work is not yet complete.

## 4. Comparing Pause Goals Across Other Collectors

| Collector on HotSpot Java 17 | Basic Design | Pause Goal Impact / Things to Note |
| --- | --- | --- |
| **Serial GC** | Collects mainly with a single worker in STW | Hard to handle large heaps under a very small pause; not real-time |
| **Parallel GC** | STW young/old collection but with multiple GC workers | Has pause/throughput ergonomics; prioritizes throughput and does not guarantee deadlines |
| **G1 GC** | Region-based, STW young/mixed evacuation + concurrent marking | Tries to adjust CSet/young size to meet pause goal with high probability; no hard bound |
| **ZGC** (JDK 17) | Most heavy GC work concurrent with mutators | Low-pause design, but not a hard-real-time contract for the whole application |
| **Shenandoah** (if present in build) | Concurrent evacuation and corresponding GC phases | Low-pause oriented; availability/vendor options vary, does not promise hard deadlines |

Do not infer that a collector with lower pauses **always** has higher throughput. A low-latency-oriented collector may need to dedicate extra CPU or memory headroom for concurrent work. Business goals determine the trade-off.

### 4.1. ZGC Does Not Turn Java Into a Hard Real-Time System Either

ZGC is designed so that STW pauses are very short and most expensive work runs concurrently. However, **request deadlines** can still be affected by:

- Linux/Windows scheduling and CPU starvation.
- Lock contention, thread pools, and queue buildup.
- Network/database/remote services.
- Page faults, I/O, or memory pressure.
- JIT compilation/class loading and other VM activities.
- Concurrent GC CPU cost or allocation stalls under low-headroom conditions.

Even a collector that typically has pauses of a few milliseconds is **not enough** to guarantee a hard real-time Java system if the entire OS, scheduling, libraries, and application do not provide corresponding end-to-end guarantees.

**Version note:** In Java 17, do not project the generational ZGC model of newer JDKs onto ZGC 17. This article focuses on the meaning of the pause goal and low-latency orientation, not equating architectures across releases.

### 4.2. Parallel GC: The Goal Exists, But the Design Prioritizes Differently

Parallel GC (throughput collector) also supports `-XX:MaxGCPauseMillis` under HotSpot ergonomics. In it, criteria are handled in the order of pause goal (if configured), throughput goal, and appropriate footprint. But because young/old collections are mainly STW, if an application needs ultra-low p99 latency, merely setting a small goal number **does not turn Parallel GC into G1/ZGC**.

Comparisons must be based on the workload, rather than assuming `-XX:MaxGCPauseMillis=20` means “equivalent actual latency” across every collector.

## 5. Pause-Time Goal and Throughput Goal Often Trade Off

**Throughput** in terms of time is the fraction of time spent on application work relative to total application + GC time in the observation window:

```text
throughput = app_time / (app_time + gc_time)

If app_time = 95 s, gc_time = 5 s:
  throughput = 95 / 100 = 95%

If app_time = 99 s, gc_time = 1 s:
  throughput = 99 / 100 = 99%
```

**This is an aggregate metric**, not a latency measurement of individual requests. Two programs with similar throughput can still have very different pause distributions.

Suppose G1 collects according to two illustrative policies:

| Policy | Number of Pauses in Window | Average Pause | Total Pause Time | Individual Pause |
| --- | ---: | ---: | ---: | --- |
| A, larger young | 5 | 100 ms | 500 ms | Can be longer |
| B, smaller young | 20 | 35 ms | 700 ms | Shorter, but more frequent |

The numbers above are **only an illustrative scenario to analyze trade-offs**, not actual JVM output. Configuration B reduces average pause, but total STW time is higher and may result in lower throughput.

### 5.1. Why Can Forcing the Pause Goal Down to 5 ms Backfire?

An overly strict goal can cause the JVM to try reducing young size, leading to more frequent collections. Combined costs include:

- More frequent entries into STW GC.
- More rounds of bookkeeping and remembered-set work.
- Increased promotion/survivor pressure if live set and young sizing are unfavorable.
- Increased GC CPU overhead, causing the application to lose throughput.
- The goal **can still be missed** if minimum unavoidable work exceeds 5 ms.

There is no rule that “the smaller the goal, the faster the application”. You must benchmark p95/p99 GC pauses **and** request latency, along with requests/sec/jobs/sec, CPU, and heap occupancy.

### 5.2. Does Increasing Heap Always Reduce Pauses?

No. A larger heap can reduce collection frequency and increase the interval between collections, but it can also change live data volume, object retention, scanning/copying costs, and compaction phases. Across different collectors, the relationship is non-linear.

Increasing `-Xmx` can provide headroom to avoid GC pressure, **but does not guarantee shorter pauses**. Conversely, a heap too small relative to the live set can cause repeated GC, Full GC, or `OutOfMemoryError` even with a very low pause goal set.

## 6. What Does a Hard Real-Time Guarantee Actually Require?

In a **hard real-time** system, a deadline is a mandatory requirement: it must not be missed within the defined operating conditions. That requires **bounds on worst-case execution time**, scheduler, thread priorities, I/O, memory allocation, lock contention, GC pauses, and other sources of jitter.

A single JVM optimization flag choice does not satisfy this requirement.

| Goal Type | Example | Need to Understand |
| --- | --- | --- |
| **Best-effort performance goal** | “Try to keep GC pauses under 50 ms.” | VM tries to achieve via heuristics; no hard guarantee |
| **Service SLO** | “In a month, 99.9% of requests under 100 ms.” | Target policy measured from metrics; has error budget, still has exceptions |
| **Hard real-time deadline** | “Every control cycle must complete before 10 ms under all permitted conditions.” | Requires worst-case proof/architecture, cannot be inferred from GC heuristics |
| **Observed p99 GC pause** | “In one week, 99% of GC events were under 40 ms.” | Historical statistical result; no guarantee for next week |
| **Client timeout** | “HTTP client gives up after 200 ms.” | Client-side handling condition, not a GC pause bound |

**Note:** An SLO can be very tight and still differ from a hard real-time guarantee. “99.99% under 20 ms” has an **error budget** and does not require every single event to be under 20 ms. Conversely, missing a hard deadline even once can be a critical failure in a control system.

### 6.1. Why Do Good GC Logs Not Prove Real-Time Correctness?

A series of 5–15 ms GC pauses does not prove:

- The scheduler will always grant CPU on time.
- The remote database will not time out.
- The JVM will not have to perform an unexpected Full GC.
- Application threads will not suffer lock contention.
- All future live sets will resemble the test load.
- There will be no memory issues, OS pauses, container throttling, or disk hiccups.

GC logs provide **evidence of GC behavior in the observed runs**. They are not by themselves a certificate of worst-case application response time.

## 7. Calculation Example: Missing the Goal Does Not Mean Every Pause Is Bad

Suppose the goal is `-XX:MaxGCPauseMillis=50`. Observe 10 events (hypothetical data):

```text
GC pauses in milliseconds:
  6, 8, 10, 11, 12, 15, 18, 21, 29, 130
```

9/10 pauses are under 50 ms, but one 130 ms event exceeds the goal by a wide margin.

- **Average** = (6+8+10+11+12+15+18+21+29+130)/10 = **26.0 ms**.
- **Max** = **130 ms**.
- **90% of events** do not exceed 50 ms according to this dataset.
- By nearest-rank with n=10: **p90=29 ms**, **p99=130 ms**.
- **Misses** against the 50 ms goal are **1/10**.

If you only report the 26 ms average, you **hide** the 130 ms event. If you only report the 130 ms max, you **do not see the distribution**, which may be mostly short. You must inspect count, distribution, and GC phase context together.

### 7.1. A Percentile From a Small Sample Is Unstable

With 10 samples, nearest-rank p99 coincides with the highest value. In production systems, you need a window with enough events and a consistent calculation method (nearest-rank, histogram buckets, HDR Histogram, etc.). Do not compare two p99 values if each system uses different windows, formulas, and rounding.

### 7.2. Do Not Use GC Event p99 as Request p99

For example, 10 GC events may affect many requests, or occur when there are no requests. Request latency histograms also include scheduling, queue, database, network, and application work. You should maintain **two separate sets of metrics**, then correlate timestamps and traces to find relationships.

## 8. Runnable Java 17 Program: Creating Allocation Pressure and Keeping Results Deterministic

The following program intentionally creates many allocations, retains a portion of objects to simulate a live set, and gives the GC opportunities to run. **No Java code here promises to measure the exact number of GC pauses or total pause time**. Those numbers must be recorded from the actual JVM.

Save the file **`PauseGoalDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PauseGoalDemo {
    private static volatile List<byte[]> keepAlive;

    public static void main(String[] args) {
        long checksum = 0L;
        List<byte[]> retained = new ArrayList<>();

        for (int i = 0; i < 160_000; i++) {
            byte[] block = new byte[1024];
            block[0] = (byte) (i & 127);
            checksum += block[0] & 0xff;

            if (i % 8000 == 0) {
                retained.add(block);
            }
        }

        keepAlive = retained;
        System.out.println("iterations=160000");
        System.out.println("retained=" + retained.size());
        System.out.println("checksumPositive=" + (checksum > 0));
        System.out.println("done");
    }
}
```

Compile on JDK 17:

```bash
javac --release 17 PauseGoalDemo.java
```

Run with G1 (HotSpot Java 17):

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -XX:MaxGCPauseMillis=50 PauseGoalDemo
```

**Deterministic application stdout, when GC logging is disabled and the command completes:**

```text
iterations=160000
retained=20
checksumPositive=true
done
```

Explanation:

1. The loop runs 160,000 times according to the program logic.
2. The condition `i % 8000 == 0` is true at `i = 0, 8000, ..., 152000`, creating **20** retained references.
3. The checksum expression reads data from each array and produces a positive sum; the `true` check result is independent of the number of GCs.
4. The `keepAlive` field (here actually a `List<byte[]>`) keeps the retained blocks reachable after the loop.
5. The JVM/JIT may optimize allocations or choose a GC strategy based on heap state; **do not infer the number of GC pauses from 160,000 `new` calls**.
6. The program does not print pause times or claim that `MaxGCPauseMillis=50` is always satisfied. Collector numbers must be read from GC logs/JFR.

**Shell note:** Multi-line commands use `\` per POSIX shell. In PowerShell/Windows Command Prompt, write them on a single line or use the line-continuation character appropriate for the shell.

### 8.1. Running Two Goals to Observe on the Same Workload

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -XX:MaxGCPauseMillis=20 -Xlog:gc=info PauseGoalDemo

java -XX:+UseG1GC -Xms64m -Xmx64m \
  -XX:MaxGCPauseMillis=200 -Xlog:gc=info PauseGoalDemo
```

The application must maintain the **same business result**, but GC event counts/pause durations may differ. If the command finishes too quickly or JIT eliminates allocations, there may not be enough events to draw conclusions; use a more realistic workload, run long enough, and collect many samples.

Do not interpret “the goal=20 run was shorter than the goal=200 run” from a single run. JVM warmup/CPU scheduling/heap state all cause variance.

## 9. Standalone Java 17 Example: Percentiles and Deadline Misses on Hypothetical Samples

A useful tool is to directly compute p50/p90/p99/max on **measured datasets**, rather than trusting only the average. The following example uses **simulated** data and does not represent real GC.

Create the file **`PauseStatisticsDemo.java`**:

```java
import java.util.Arrays;

public class PauseStatisticsDemo {
    static long nearestRank(long[] sorted, double quantile) {
        int rank = (int) Math.ceil(quantile * sorted.length);
        int index = Math.max(0, rank - 1);
        return sorted[index];
    }

    public static void main(String[] args) {
        long[] samples = {6, 8, 10, 11, 12, 15, 18, 21, 29, 130};
        Arrays.sort(samples);

        long sum = 0;
        int misses = 0;
        for (long pause : samples) {
            sum += pause;
            if (pause > 50) {
                misses++;
            }
        }

        System.out.println("count=" + samples.length);
        System.out.println("averageMs=" + (sum / (double) samples.length));
        System.out.println("p50Ms=" + nearestRank(samples, 0.50));
        System.out.println("p90Ms=" + nearestRank(samples, 0.90));
        System.out.println("p99Ms=" + nearestRank(samples, 0.99));
        System.out.println("maxMs=" + samples[samples.length - 1]);
        System.out.println("above50Ms=" + misses);
    }
}
```

Run:

```bash
javac --release 17 PauseStatisticsDemo.java
java PauseStatisticsDemo
```

**Exact stdout:**

```text
count=10
averageMs=26.0
p50Ms=12
p90Ms=29
p99Ms=130
maxMs=130
above50Ms=1
```

Meaning:

- Nearest-rank `p50` is the 5th element, **12 ms**.
- Nearest-rank `p90` is the 9th element, **29 ms**.
- Nearest-rank `p99` is the 10th element, **130 ms**.
- Average is **26 ms**, but the tail has a 130 ms event.
- `above50Ms=1` is a **count of events exceeding the hypothetical goal**, not proof that the Java 17 JVM violated a flag in this run.

In real operations, you also need **time window, collector/event type, histogram resolution, sample size, max, and SLO threshold** to make decisions.

## 10. Collecting Actual GC Pauses With HotSpot Unified Logging

### 10.1. Writing GC Events to a File

On HotSpot Java 17:

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -XX:MaxGCPauseMillis=50 \
  -Xlog:gc*,safepoint=info:file=gc-pause.log:time,uptime,level,tags \
  PauseGoalDemo
```

Logs are written to `gc-pause.log`. Actual content depends on the JVM build, GC activity, OS scheduling, and workload. You must not claim the pause time is “obviously 50 ms” without reading the file.

An event can have an *illustrative* format:

```text
[...][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) ... 13.7ms
[...][info][gc] GC(13) Pause Young (Normal) (G1 Evacuation Pause) ... 72.4ms
[...][info][safepoint] Safepoint "G1CollectForAllocation", ... Total: ... ns
```

These are **structural simulation lines to know what to read**, not actual logs from the program. Times on the same line may have units `ms`, `us`, or `ns` depending on the log field and configuration.

**Do not mix the duration of a `gc` event with the “Total” of `safepoint` and add them twice**: measurements can overlap or measure different intervals of the same operation.

### 10.2. Reading Timestamp Scopes Accurately

- The `time` decorator provides wall-clock timestamps, convenient for correlating with app traces.
- `uptime` gives time since JVM startup, useful if wall-clock changes.
- `level`/`tags` indicate event types, avoiding confusion between GC vs safepoint.
- `GC(id)` helps group log lines belonging to the same GC cycle/pause.
- Lines containing “Pause” are usually a good starting point, but **a GC cycle can have multiple events/phases**; not every text line is an independent pause.

When computing pause percentiles, clearly choose **which events** are included in the sample (young, mixed, full, remark...). Some phase breakdown lines only describe **components of the same pause**; mistakenly summing them as independent events will double-count.

### 10.3. Why Are `safepoint` Logs Needed?

Sometimes an application slows down due to waiting for threads to reach a safepoint, OS scheduling, or a VM operation, not just the GC work recorded as a pause. Safepoint logging helps investigate:

- Time until threads can cooperate for a safepoint.
- Duration of the operation while at the safepoint.
- Total time according to JVM accounting.
- VM operations that are not a garbage collection but can still cause delays.

**Do not use safepoint time as an absolute substitute for GC pause time**: they have different scopes and measurement definitions; correlate them using timestamp/GC id or operation name.

### 10.4. Choosing a Log Level With Enough Detail Without Excessive Overhead

```bash
# Minimal info, suitable for initial observation:
java -XX:+UseG1GC -Xlog:gc=info PauseGoalDemo

# Add more detailed breakdown for experiments:
java -XX:+UseG1GC -Xlog:gc*,gc+phases=debug PauseGoalDemo

# Can write to a file with decorators:
java -XX:+UseG1GC \
  -Xlog:gc*,safepoint=info:file=gc-pause.log:time,uptime,level,tags \
  PauseGoalDemo
```

`debug/trace` can generate large logs and increase CPU/I/O overhead, so do not enable it indefinitely in production. Inspect pause logs at `info` level first, then enable additional tags/levels only as needed for suspected causes.

## 11. Using JFR to View GC and Requests on the Same Timeline

**Java Flight Recorder (JFR)** can collect events about GC, safepoints, allocations, and application behavior depending on configuration. This is a useful way to combine:

- When did the GC pause occur and how long did it last?
- Which thread was processing a request at that exact moment?
- Are there signs of lock contention, thread parking, or a CPU bottleneck?
- Are there allocation hotspots or pause outliers related to a specific phase?

Startup command on JDK 17:

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -XX:MaxGCPauseMillis=50 \
  -XX:StartFlightRecording=filename=gc-pause.jfr,settings=profile \
  PauseGoalDemo
```

The application still prints normal Java stdout; the **`gc-pause.jfr` file** is a recording to analyze separately with JDK Mission Control/JFR tooling. A very short program may not provide a large enough number of events for statistics; benchmark a service/workload with a representative duration.

**JFR also has overhead and sampling policies**. Data in the recording must be interpreted according to event types/settings; do not assume every GC activity or every request is recorded completely with infinite precision.

### 11.1. Do Not Look at One GC Log and Infer Request Latency

An 80 ms GC event near a 120 ms request **does not by itself prove** GC is the sole cause. You need to correlate timing:

1. Request start/end timestamps or trace spans.
2. GC pause start/end and event type.
3. Queue latency before the request handler.
4. CPU throttling/scheduling/lock contention and I/O.
5. Whether other requests were also affected at the same time.

When there is exact overlap and many similar observations, the hypothesis that GC affects request latency is stronger. Still, control for other causes before “fixing with a GC flag”.

## 12. Why Can GC Pauses Exceed the Goal in Practice?

### 12.1. More Live Objects Than Predicted

In a copying collector, pause cost depends much more on **how many live bytes must be copied/scanned** than on total allocation volume alone. When a request batch retains many objects across a Young GC, liveness is higher than historical data and pauses can increase.

For example, a cache just warmed up or a queue holds many temporary objects past the collection point; that is an actual graph change, not the collector “ignoring the flag”.

### 12.2. Phases Not Fully Controlled Directly by Heuristics

A pause has many items:

- Root scanning.
- Remembered-set updates/scans.
- Object copying/evacuation.
- Reference processing such as weak/soft/phantom references.
- Specific GC marking/cleanup/compaction operations.
- Coordination overhead among GC worker threads.
- Waiting for threads/safepoints and CPU scheduler delays depending on measurement.

The collector cannot always split or defer every subtask just because it has a small pause budget. If consistency is required or memory is low, it may need to execute steps exceeding the predicted time.

### 12.3. Full GC, Allocation Failure, and Evacuation Pressure

When the application heap is near its limit or there are not enough suitable regions to copy live objects, G1 may encounter situations requiring heavier handling (e.g., Full GC). These can create pause outliers even if previous young collections were short.

**Do not increase the heap indefinitely** as a “real-time solution”: more memory headroom can reduce failure pressure, but reachable live objects still need to be processed and other latency sources remain.

### 12.4. Humongous Allocations and Region Fragmentation

In G1, objects sized at **half a region or larger** belong to the humongous category, having a special allocation path in old/humongous regions. These large allocations can put pressure on contiguous regions, triggering events and corresponding fragmentation.

A very large byte array or an object graph with large buffers can make the GC pattern completely different from a small-object workload. When seeing pause outliers related to humongous objects, inspect sizes/allocations/region logs instead of just lowering `MaxGCPauseMillis`.

### 12.5. CPU Throttling and Resource-Starved Systems

A CPU-limited container or a host contended by many processes can prevent GC worker threads from running fully. Wall-clock pauses lengthen even when the amount of GC work is similar.

Monitor:

- CPU quota/cgroup throttling.
- Run queue and OS scheduling.
- Appropriate GC worker threads count.
- Page faults/memory pressure.
- JVM process RSS and native memory.
- Concurrent collector CPU consumption.

Do not assume `Pause Young 120ms` is always due to liveness or the GC algorithm; in container environments, **CPU starvation** can be the primary factor.

### 12.6. Explicit GC and Interfered Benchmark Environments

Calling `System.gc()` in application code, libraries, or test harnesses can request a special collection depending on collector/flags. Do not use repeated `System.gc()` as a tool to “force pauses to match the target”. Non-representative benchmark-generated GC pressure can lead to wrong tuning conclusions.

If the log shows cause `System.gc()`, find the caller/instrumentation and check appropriate JVM flags; do not confuse this cause with normal allocation-driven young pauses.

## 13. Experimental Configurations and What Not to Do

### 13.1. Baseline Before Tuning

```bash
java -XX:+UseG1GC -Xms512m -Xmx512m \
  -Xlog:gc*:file=g1-baseline.log:time,uptime,level,tags \
  MyApp
```

`MyApp` is just a **placeholder class name for a real application**, not the `PauseGoalDemo.java` file provided in this article. To run the standalone example, replace it with `PauseGoalDemo` as in section 8.

Lock down the JDK vendor/build, workload, CPU limits, request sample window, p99, throughput, heap headroom, and GC event metrics. From there you have a real baseline.

### 13.2. Change Only the Pause Goal at One Time

```bash
java -XX:+UseG1GC -Xms512m -Xmx512m \
  -XX:MaxGCPauseMillis=50 \
  -Xlog:gc*:file=g1-goal50.log:time,uptime,level,tags \
  MyApp
```

Compare against the baseline on the same hardware/load/dataset. A lower target **may** reduce pauses but increase GC frequency or CPU overhead. Re-measure request p95/p99, throughput, and GC time fraction to see if the trade-off is acceptable.

### 13.3. Avoid Locking Young Generation When Tuning G1 Pauses

```bash
# Example of a configuration that should NOT be applied mechanically when relying on G1 pause control:
java -XX:+UseG1GC -Xmn256m -XX:MaxGCPauseMillis=20 MyApp
```

`-Xmn` restricts the young generation size in a way that can disable/reduce G1’s ability to self-adjust young size. This command is a tuning anti-pattern example; **not recommended for production** without appropriate study.

### 13.4. Avoid Forcing a Tiny Goal to Hide Code Issues

If 80% of object allocations are temporary buffers from continuous encoding/decoding, this can be solved by reducing allocations or changing data representation. If a cache holds a multi-GB live set uncontrollably, check the retention policy. If a service lacks CPU, changing the pause goal does not create more processor time.

**Setting a goal is only one parameter**. Code optimization, heap sizing, and deployment infrastructure can be more important.

## 14. Reading SLA/SLO Properly: Frequency, Percentiles, and Tail

Suppose a service has an SLO:

> 99.9% of HTTP responses under 100 ms over a rolling 30 days.

This is a **service-level objective** measured from **requests**, not `MaxGCPauseMillis=100`. It can be missed due to a 120 ms network delay even if GC is not running; or it can be met if most GC pauses occur outside request processing moments.

### 14.1. Simulated Example of Two Systems

| Attribute | System A | System B |
| --- | --- | --- |
| GC goal | 30 ms | 100 ms |
| Measured GC pause p99 | 70 ms | 80 ms |
| Measured request p99 | 400 ms | 95 ms |
| Throughput | 1,000 req/s | 2,000 req/s |
| Meets request SLO p99 under 100 ms? | No | Yes |

**Simulated data.** System A has a smaller goal but worse request latency. A might suffer from CPU starvation, long-running locks, network, or a different workload. Do not use the simulated table to conclude goal=100 is always better than goal=30; it only proves **flag value does not determine SLA outcome**.

### 14.2. Miss Rate and Error Budget

If there are 1,000,000 requests in a window and the SLO is 99.9% meeting the deadline, the maximum budget of 0.1% failures corresponds to **1,000 requests** outside the target by simple counting. In practice, you need to precisely define “successful request”, timeouts, retries, and synthetic probes.

GC pause targets do not calculate that error budget for you. A JVM can have GC outliers while request deadlines are still met during low-traffic periods; conversely, request deadlines can be missed continuously because an upstream service is slow while GC is completely normal.

## 15. Diagnostic Workflow When p99 Increases and GC Pauses Are Long

**Step 1 — Confirm the symptom.** Check request p99, timeout rate, CPU, RSS, GC pause p99/max, and time window.

**Step 2 — Check collector, flags, and heap.** Get `java -version`, `-Xms/-Xmx`, actual `UseG1GC`/`UseParallelGC`/`UseZGC`, `MaxGCPauseMillis` (do not just read deployment manifests).

**Step 3 — Separate GC causes/types.** Count young/mixed/full/explicit GCs separately. Full GC outliers are very different from steady young evacuations.

**Step 4 — Check time correlation.** Place GC log timestamps next to request traces and safepoint events. Distinguish overlapping start/end from coincidental proximity.

**Step 5 — Inspect live set, allocations, and promotion.** High live data, large buffers, and object retention pressure often determine copy/scanning cost and heap headroom.

**Step 6 — Observe CPU/runtime/container.** Check cgroup throttling, run queue, thread count, contention, and memory pressure.

**Step 7 — Choose one hypothesis-driven change.** This could be reducing allocations, increasing heap headroom, adjusting the G1 pause goal, or trying a low-latency collector.

**Step 8 — Repeat benchmarks with a representative workload.** Measure at least pause distributions, request p95/p99, total throughput, CPU, and memory simultaneously. A single run is not enough.

**Step 9 — Compare against the actual SLO.** If request p99 improves but throughput drops by 30%, weigh product goals. If GC p99 drops while service p99 stays unchanged, the bottleneck may be elsewhere.

**Step 10 — Revisit causes when the environment changes.** When CPU quotas, traffic shape, or JDK version change, re-measure; do not permanently apply flag tuning from an old benchmark machine.

## 16. Common Misconceptions

1. **“`MaxGCPauseMillis=20` guarantees every GC is under 20 ms.”** False; it is a target/hint, not a hard bound.
2. **“Just setting the goal equal to the request SLA will meet the SLA.”** False; request latency includes many components other than GC.
3. **“G1’s default 200 ms means G1 always pauses for exactly 200 ms.”** False; it is the **default goal value in Java 17**, not a measured result.
4. **“If there is a 201 ms pause when goal=200, the JVM violates the specification.”** False; goals can be missed.
5. **“GC pause goal can be used to prove hard real-time.”** False; worst-case guarantees across the entire system are required.
6. **“G1 is a concurrent collector so it never does STW.”** False; G1 has young/mixed evacuations and some phases that stop the application.
7. **“G1 has GC workers running in parallel so the application also always runs in parallel with GC.”** False during STW phases.
8. **“The lower the goal, the higher the throughput always.”** False; young size may be shrunk and GC frequency/overhead may increase.
9. **“The lower the goal, the lower every pause always.”** False; outliers and non-predictable phases can exceed it.
10. **“A Full GC will also stop itself when the 50 ms budget runs out.”** False; there is no hard pause interrupt contract.
11. **“`-Xmn` always helps G1 control pauses better.”** False; a fixed young size can break adaptive control.
12. **“More frequent Young GCs definitely mean a memory leak.”** False; allocation churn can be high while the live set is low.
13. **“GC event average=10ms means p99=10ms.”** False; the tail can be much longer.
14. **“GC pause p99 is HTTP response p99.”** False; they are two different sample sets and measurements.
15. **“CPU starvation does not affect GC pauses.”** False; GC workers also need CPU time.
16. **“Increasing `ParallelGCThreads` always reduces pauses linearly.”** False; bandwidth and coordination overhead limit it.
17. **“ZGC is a hard real-time JVM.”** False; a low-latency design does not by itself guarantee OS/app deadlines.
18. **“Every GC log line is an independent GC pause.”** False; phase details may belong to the same event.
19. **“Safepoint Total time and GC pause time are always two independent numbers that can be added together.”** False; they can overlap.
20. **“Running `System.gc()` is how to test whether the goal flag is guaranteed.”** False; explicit GC may take a different path from normal workloads.
21. **“Measuring one benchmark run is enough to choose a collector.”** False; workload warm-up, JIT/GC heuristics, and OS conditions vary.
22. **“Every JVM vendor supports HotSpot flags identically.”** False; options are implementation-specific.
23. **“A larger heap always has shorter pauses.”** False; the relationship depends on live data/collector.
24. **“Just looking at the GC log reveals every cause of request timeouts.”** False; you need app traces, CPU, network, and I/O metrics.
25. **“When the GC goal is met most of the time, there can be no outliers.”** False; a soft goal allows exceptions.
26. **“Pause-time optimization is a problem that doesn’t require understanding overhead/throughput.”** False; latency, throughput, and footprint must be balanced.
27. **“A p99 percentile from 10 events is as reliable as from millions of samples.”** False; sample size and calculation method affect conclusions.
28. **“Setting `MaxGCPauseMillis=0` means GC has zero pauses.”** Incorrect; valid values/effects depend on option parsing/runtime and do not turn GC into zero-pause real-time.
29. **“Concurrent GC work does not affect performance outside pauses.”** False; it can compete for CPU/memory bandwidth.
30. **“Missing a request deadline is definitely caused by GC.”** False; multi-layer root-cause analysis is required.

## 17. Self-Check (With Answers)

**Question 1.** Is the statement “`-XX:MaxGCPauseMillis=50` guarantees GC is under 50 ms” true?

**Answer:** No. The flag represents a **goal/hint** for the collector to try to tune toward, not a hard deadline.

**Question 2.** Why can a G1 Young GC exceed the goal?

**Answer:** Predicted live bytes, remembered-set work, CPU headroom, or a specific phase may differ from assumptions; the collector does not arbitrarily cut off required work.

**Question 3.** What is Java 17 G1’s default pause goal according to the Oracle guide?

**Answer:** **`-XX:MaxGCPauseMillis=200`**, which is a goal, not a guaranteed max pause.

**Question 4.** Can Parallel GC process multiple GC tasks in parallel while still pausing the application?

**Answer:** Yes. **Parallel** among GC workers is different from **concurrent** between GC and the application.

**Question 5.** A service has p99 300 ms, GC pause p99 15 ms. Will lowering the GC goal definitely improve service p99?

**Answer:** No. You must inspect queue time, locks, CPU, remote I/O, and correlation between GC and requests.

**Question 6.** If the young size is smaller, is total GC time always smaller?

**Answer:** No. A single pause may be shorter, but the number of events increases and throughput may decrease.

**Question 7.** Does a 900 ms Full GC when goal=50 ms violate the Java Language Specification?

**Answer:** Not because of this flag; the goal is a VM heuristic, with no hard real-time requirement.

**Question 8.** What average and max does `PauseStatisticsDemo` produce?

**Answer:** Average **26.0 ms**, max **130 ms** on the 10 hypothetical samples.

**Question 9.** How many arrays does `PauseGoalDemo` retain?

**Answer:** **20**, due to 160,000 iterations and retaining each time `i` is divisible by 8,000.

**Question 10.** Why are GC logs and safepoint logs needed together?

**Answer:** To distinguish GC work from the time to bring threads to a safepoint and other VM operations; measurement scopes must be checked to avoid double-counting.

**Question 11.** Why are GC event p99 and request p99 not from the same sample?

**Answer:** One samples **pause events**, the other samples **requests**; counts, durations, and overlap differ.

**Question 12.** When lowering the GC goal reduces throughput, should you conclude the flag is buggy?

**Answer:** No. This may be an expected trade-off due to smaller young size/more GC events; compare against SLO and CPU/heap metrics.

**Question 13.** In a hard real-time system, can `-XX:MaxGCPauseMillis` alone be used as proof of meeting deadlines?

**Answer:** No. Bounds on the scheduler, worst-case app processing, allocation, GC, OS, and external dependencies are required.

**Question 14.** Why should you avoid fixing `-Xmn` when using G1 and expecting the GC pause target to self-adjust?

**Answer:** Because young-generation sizing is a primary tool for G1 to balance pause durations; fixing it can severely restrict heuristic control.

## 18. Summary Decision Map

```text
DO YOU WANT TO REDUCE GC PAUSE / REQUEST LATENCY?
                   │
                   ▼
          Identify target metric
            ├─ GC pause p95/p99/max?
            ├─ request p99/SLO?
            └─ hard real-time deadline?
                   │
                   ▼
            Collect real data
            ├─ GC logs + GC ids/events
            ├─ safepoint logs / JFR
            ├─ request tracing & histograms
            └─ CPU/heap/container metrics
                   │
                   ▼
        Analyze cause & trade-offs
            ├─ Long Young GCs? → CSet/young/live data
            ├─ Full GC? → heap headroom/retention
            ├─ CPU throttling? → resource limits
            ├─ request queue/DB? → non-GC bottleneck
            └─ throughput too low? → overly aggressive goal
                   │
                   ▼
       Choose a hypothesis-driven change
            ├─ Reduce allocations/retention
            ├─ Provide appropriate heap and CPU headroom
            ├─ Adjust soft GC pause goal
            └─ Switch collector when latency requires it
                   │
                   ▼
     Benchmark repeatedly on real workload
                   │
            ┌──────┴──────┐
        SLO met?       Not met?
            │             │
        Monitor        Re-investigate cause,
        continuously   do not promise deadlines via flags
```

**Remember:** `-XX:MaxGCPauseMillis` is an **optimization target the GC tries to achieve**, **not an enforced limit**, **not a real-time promise**, and **not a request SLA**. G1 adjusts young/CSet sizes based on workload predictions; trade-offs typically lie between **pause length, GC frequency, throughput, and footprint**. Full GCs, live-set spikes, CPU throttling, or safepoint delays can cause actual times to exceed the target. Evaluate **measured distributions**, correlate GC with end-to-end latency, and choose configurations/collectors based on SLOs rather than relying on a single command-line number.

### Standard References

- [Oracle Java SE 17 — Ergonomics / Maximum Pause-Time Goal](https://docs.oracle.com/en/java/javase/17/gctuning/ergonomics.html): confirms `MaxGCPauseMillis` is a *hint* and may not be achieved.
- [Oracle Java SE 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): G1 region model, 200 ms default pause-time goal, evacuation, and concurrent phases.
- [Oracle Java SE 17 — Garbage-First GC Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html): pause/throughput tuning, young-size interactions, diagnosis.
- [Oracle Java SE 17 — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): Serial, Parallel, G1, ZGC, and their different goals.
- [Oracle Java SE 17 — `java` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `UseG1GC`, `MaxGCPauseMillis`, `-Xlog`, heap options, `StartFlightRecording`.
- [Oracle JDK 17 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.html): event recording/observability.
- [Oracle JDK 17 — `jcmd` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): inspecting JVM/GC/JFR and diagnostic commands.
