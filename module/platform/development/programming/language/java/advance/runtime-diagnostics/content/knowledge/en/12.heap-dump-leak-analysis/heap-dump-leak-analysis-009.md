# 12.9 Comparing Evidence Over Time Instead of Concluding a Leak from One Histogram

## 1. Goal: Turning a Suspicious Snapshot into Evidence-Backed Conclusions

A Java heap **class histogram** shows how many instances of each class currently exist and their total *shallow* bytes. It is very useful for narrowing down suspects, yet **it does not directly answer** whether a set of objects is leaking, which object keeps them alive, or whether that count is normal for current traffic.

For example, seeing the `byte[]` row occupy lots of memory only tells you there are many byte arrays. They could belong to a bounded cache, in-flight requests, temporary payloads, queues, batch results, or objects genuinely retained unintentionally. A single histogram cannot distinguish among those causes.

**Lesson goal:** build an evidence chain `T0 → T1 → T2` under comparable conditions, examine trends in object counts and post-GC memory at equal workloads, and then use a heap dump and paths to GC roots when you need the root cause. Conclusions must distinguish:

- **Observation:** what was measured at one point in time, such as `[B` instance count and `#bytes`.
- **Trend:** change across multiple checkpoints after normalizing time, load, GC, and measurement mode.
- **Hypothesis:** growing cache, queue backlog, non-expiring sessions, unremoved listeners, or unintended retention.
- **Confirming evidence:** identifying abnormally long-lived objects, the retaining reference source, expected lifecycle, and a release/stabilization test.

In Java, a "memory leak" usually means **references still retaining objects that business logic no longer needs**, preventing GC from reclaiming them; the objects remain *reachable* yet are no longer useful. This differs from **fast allocation** or **high `heap.used` at a single instant**.

## 2. What Does a Histogram Measure, and What Does It Omit?

Common command on HotSpot JDK 17+:

```bash
jcmd 12345 GC.class_histogram
```

`12345` is an **illustrative PID**; replace it with the real PID. A histogram table may look like this (**hypothetical** numbers, not fixed stdout):

```text
 num     #instances         #bytes  class name
--------------------------------------------------
   1:          4000        5242880  [B
   2:          8000         192000  java.lang.String
   3:          1500          48000  java.util.HashMap$Node
Total         13500        5482880
```

These hypothetical numbers only illustrate column layout; do not add these sample rows to infer real JVM memory totals. With real output, read the exact header and row figures.

| Column | Meaning | Do not misinterpret as |
| --- | --- | --- |
| `num` | Rank in the table sorted by size at measurement time | A stable class ID across sampling runs |
| `#instances` | Number of objects of the listed class in this capture | Total allocations since JVM startup |
| `#bytes` | Total **shallow size** of instances of that class, in bytes | Retained size, or total memory indirectly held by that class |
| `class name` | Class/array type name, e.g. `[B` for `byte[]` and `[Ljava.lang.String;` for `String[]` | Proof pointing to this class as the leak cause |

**Shallow size** is the size of the object/array itself, including data stored inside an array; it does **not** add objects referenced by that object. **Retained size** of an object, by contrast, estimates the memory that could be freed if appropriate retention paths were removed and objects dominated by it became unreachable. Evaluating retained size requires analyzing the **reference graph** (heap dump, dominator tree), which a histogram lacks.

Because a histogram groups by class, it also cannot tell you:

- Which request created which object, who owns it, its age, or its release deadline.
- Which objects are temporarily referenced by thread stacks, caches, static fields, or which class loader.
- Whether that usage matches the number of active users, sessions, or messages.
- Whether unreachable objects not yet cleared by GC were counted prior to measurement (depending on tool mode).
- Whether a class has many instances due to thousands of valid items or one collection growing without bound.

### Reachability and `-all` change the meaning of the measurement

With `jcmd GC.class_histogram`, the `-all` option enables **inspecting unreachable objects as well**; the default is `false` per JDK 21 docs. Therefore:

```bash
jcmd 12345 GC.class_histogram
jcmd 12345 GC.class_histogram -all=true
```

**Do not cross-compare** these two modes as if both reflected "live objects." Default mode targets objects remaining after appropriate VM collection activity; `-all=true` can include objects that are dead in terms of reachability yet not reclaimed. In leak investigations, record the exact mode used, collector/JDK, timestamp, and nearby GC activity.

The histogram command is rated **Impact: High** by the JDK, depending on heap size and contents; it can cause pauses/GC activity and perturb what you observe. Sample only at reasonable intervals, especially in production. Never run a tight histogram capture loop as a metrics system.

## 3. Why Does One "Huge" Histogram Often Produce Wrong Conclusions?

| Observation in one snapshot | Open hypotheses | What to measure next |
| --- | --- | --- |
| `byte[]` tops the table | I/O buffers, cache payloads, request bodies, garbage awaiting GC, or abnormal retention | Counts/bytes at T0–T2, traffic type, owner in a heap dump |
| Very many `String`s | Valid dataset, active parser, cache keys, log/trace payloads | Count per request/record; keys/values and holding objects |
| Many `HashMap$Node`s | Large cache/map; could be a valid registry or an uncleaned map | Key count, bound/TTL policy, map owner, and retained graph |
| `Class`/class loaders growing | Library init, valid dynamic class generation, or class-loader retention | Class loader counts across deploy cycles, class unloading/Metaspace |
| High heap yet no obvious "culprit" in histogram | Many small objects, spread-out data, complex retention structure | Post-GC used, dominator tree, grouping by class loader/package |

A high point at the end of a batch looks very different from the same number after the batch finishes and the queue drains. **You cannot judge whether a size is abnormal without knowing the expected lifecycle of the data.**

Furthermore, the table is **ranked by `#bytes`**; row 1 at T0 and row 1 at T1 may be two different classes. To diff properly, match by **class identity (and class loader when needed)**, never subtract by `num` row number.

## 4. Designing Comparable Time-Series Measurements

Treat each capture as a record containing **histogram + operational context**, not just a plain text file. Minimum metadata set:

| Field | How to collect or note | Why it is needed |
| --- | --- | --- |
| PID, JVM start time/uptime, version | `jcmd -l`, `VM.version`, `VM.uptime` | Avoid mixing two JVMs when a PID is reused |
| GC, `-Xms`, `-Xmx`, runtime flags | `VM.flags`, startup config | Collector and heap limits shape measurements |
| Timestamp of each snapshot | Label T0, T1, T2 and log start/end times | Correlate with GC, business logs, and latency |
| Histogram mode | Default vs. `-all=true`, same tool/JDK | Ensure consistent reachability criteria |
| Load | RPS, completed requests, active users, batch size, queue length | Separate useful data growth from abnormal retention |
| Business cycle | Post warm-up? Post batch? Post TTL? Post logout? | Only baselines after stable cycles are comparable |
| GC and heap | GC count/time, post-GC used or GC logs | Avoid confusing temporary allocation with live-object baseline |
| Snapshot anomalies | Pauses, attach errors, capture duration, missing snapshots | Do not draw conclusions from skewed/incomplete samples |

**A sound practice sequence**:

1. **Startup/warm-up:** wait for JIT, initial caches, initial class loading, and startup tasks to stabilize. Set baseline **T0** when business state is well understood.
2. **Operate at load level A:** keep influencing factors relatively steady; if traffic changes, **record it explicitly**. Capture **T1** after enough time for multiple GC cycles or one business cycle.
3. **Sustain or drain load:** allow requests, batches, sessions, queues, or TTLs a chance to finish/expire; capture **T2**. If slow retention is suspected, collect T3 and T4 rather than over-interpreting two points.
4. **Read post-GC samples and metrics:** observe the lowest memory floor after **comparable natural GCs** under matching conditions. If you explicitly trigger a Full GC to normalize in a test environment, label it clearly because the measurement itself altered state.
5. **Compare against business volume:** when throughput/active objects are steady, do live objects plateau or keep accumulating? If request rate doubled, a class doubling in count is not enough to suspect a leak.

There is no universal "5-minute interval" for every app. Pick intervals based on **expected lifetime**: per-request buffers can be measured over minutes; 1-hour session TTLs require watching past an hour; caches with long warm-ups need a post-warm-up baseline.

### How should "post-GC" be understood?

`heap.used` at T0 differs from the post-collection live set: right before GC, unreachable objects may still sit uncollected. With concurrent collectors, "after one young GC" does not mean the entire old generation was scanned and reclaimed. Use GC logs/counters to verify **which collection type ran**, and avoid claiming a figure is "after Full GC" without evidence.

Oracle recommends monitoring the **live set in steady state, under steady load, over time** to detect leaks. A steadily rising post-GC used baseline creates **grounded suspicion**, not a replacement for reference-retention proof.

## 5. Capturing Histograms and GC Evidence on the Same PID

In a terminal with JDK 17+:

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 VM.uptime
jcmd 12345 help GC.class_histogram
```

Replace `12345` with the PID of the JVM under investigation. Capture at planned intervals with distinct filenames. Example in a terminal supporting stdout redirection:

```bash
jcmd 12345 GC.class_histogram > hist_T0.txt
jstat -gcutil 12345 1000 5 > gc_T0.txt

# Run or observe the same load level, recording timestamps.
jcmd 12345 GC.class_histogram > hist_T1.txt
jstat -gcutil 12345 1000 5 > gc_T1.txt

# After load/work has had a chance to complete.
jcmd 12345 GC.class_histogram > hist_T2.txt
jstat -gcutil 12345 1000 5 > gc_T2.txt
```

This is a **procedural sequence**, not a script that sleeps automatically for the right interval: the operator must take T0/T1/T2 at the chosen checkpoints. In Windows PowerShell, output redirection follows the shell's encoding rules; check encoding if parsing automatically. If attaching fails in a container, verify user/permissions, namespace, and attach mechanism rather than silently switching PIDs.

`jstat`'s `YGC`, `FGC`, `YGCT`, `FGCT`, and `GCT` report cumulative GC counts/times from tool counters (times are typically in seconds). `-gcutil` prints `E` and `O` as **percentages of each individual space**; **do not equate `O=80%` with "80% total heap."** Different collectors/JDKs may display different columns; read the header instead of assuming fixed positions.

Save `heap.used/committed/max` separately from `MemoryMXBean`, app metrics, or GC logs. A histogram is an extra layer showing **object distribution by class**, not a substitute for the overall heap picture.

**Production impact:** `GC.class_histogram` has high impact, so schedule it in suitable diagnostic windows, time its execution, and watch latency. Do not call `System.gc()` or `jcmd ... GC.run` after every sample; that alters the system under investigation. If you intentionally ran a Full GC for a controlled experiment, record it as an experimental variable and do not compare directly against normal samples.

## 6. Computing Deltas Properly Across T0, T1, T2

Suppose for the **same class** `com.acme.OrderContext`:

```text
deltaInstances(T0,T1) = instances(T1) - instances(T0)
deltaShallowBytes     = shallowBytes(T1) - shallowBytes(T0)
growthRate           = deltaShallowBytes / elapsedMinutes
bytesPerInstance     = shallowBytes / instances  (when instances > 0)
```

These measure **net change** between snapshots; they do not reflect every allocation in that interval, since millions of objects may have been allocated and reclaimed.

**Hypothetical** example under steady load and identical capture mode:

| Checkpoint | Time from T0 | `OrderContext` instances | Shallow bytes | Post-GC heap used |
| --- | ---: | ---: | ---: | ---: |
| T0 | 0 min | 2,000 | 160,000 B | 120 MiB |
| T1 | 10 min | 3,200 | 256,000 B | 150 MiB |
| T2 | 20 min | 4,400 | 352,000 B | 180 MiB |

We compute:

- T0 → T1: `+1,200` instances, `+96,000 B` shallow, average rate `9,600 B/min`.
- T1 → T2: `+1,200` instances, `+96,000 B` shallow, continuing to climb in the second window.
- Post-GC heap used floor rises `+30 MiB` every 10 minutes.

This is **trend evidence worth investigating** once RPS, concurrency, cache warm-up, batch queues, and business cycles are confirmed steady. **Do not** attribute the entire `30 MiB` growth solely to `OrderContext`: that class's own shallow bytes grew by only `96,000 B`, whereas objects it references or other structures may account for most of it. A histogram does not prove reference-holding relationships.

Conversely, suppose a valid cache shows instance counts `2,000 → 3,200 → 3,200` after warm-up and stays flat across multiple load cycles; that can simply be bounded-cache behavior. If workload at T2 is double T0, normalize counts by requests/sessions/queue size before labeling growth abnormal.

**Never report percentage growth alone**: going from 1 to 10 objects is `+900%` yet may be meaningless; going from 5 GiB to 6 GiB is only `+20%` yet can be critical. Always report **absolute deltas, elapsed time, and load context**.

## 7. Distinguishing Four Trend Shapes Over Time

### 7.1. Temporary allocation: high peaks, baseline returns

After each burst of requests, heap used rises and then drops as GC reclaims short-lived objects. A peak-load histogram may show many `byte[]` or `String` instances, but post-processing and post-GC counts do not climb persistently. The right direction is checking **allocation rate/GC pressure/latency**, not prematurely declaring a "leak."

### 7.2. Warm-up or bounded cache: rises then plateaus

A cache fills gradually from 0 to a 10,000-entry cap and then levels off. Early histograms will always show positive deltas; measure past the cap point, across TTL/eviction cycles, or after stopping load. Inspect limits by **entry count, byte weight, key cardinality**, and actual eviction policy.

### 7.3. Backlog: reversible accumulation

A queue grows because production outpaces consumption while processing slows down. Many messages/contexts coexist concurrently, then drain once consumers catch up. If T0–T2 span peak hours, a steadily climbing histogram can be a **symptom of backlog**. Cross-check queue depth, throughput, retries, and drain time.

### 7.4. Abnormal retention: baseline rises even after input stabilizes/stops

After each cycle finishes, a collection, listener registry, thread-local, unbounded cache, or static field keeps holding objects that are no longer needed. T2 remains elevated after load/TTL ends and climbs with each cycle. This is **stronger leak suspicion**, yet you must open a heap dump to trace **GC root → reference chain → object** and compare with expected lifecycle.

## 8. Runnable Java 17+ Example: Bounded vs. Growing Retention

The experiment creates two retention styles with the same `byte[]` shape; the point is to compare **trends within each process**. `bounded` mode models a capped cache; `growing` mode intentionally retains more and more arrays to simulate the **symptom** a leak can produce. This is a deliberate simulation, not a hidden bug in the code.

Save the full code as **`HistogramTrendDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;

public final class HistogramTrendDemo {
    private static final Deque<byte[]> RETAINED = new ArrayDeque<>();
    private static volatile byte[][] lastBurst;

    public static void main(String[] args) throws InterruptedException {
        if (args.length != 1 ||
                (!"bounded".equals(args[0]) && !"growing".equals(args[0]))) {
            System.err.println("Usage: java HistogramTrendDemo bounded|growing");
            return;
        }

        String mode = args[0];
        System.out.println("PID=" + ProcessHandle.current().pid()
                + " mode=" + mode);

        for (int step = 1; step <= 240; step++) {
            // Temporary allocation: eligible for later GC reclamation.
            byte[][] burst = new byte[8][];
            for (int i = 0; i < burst.length; i++) {
                burst[i] = new byte[128 * 1024];
                burst[i][0] = (byte) step;
            }
            lastBurst = burst;

            // Array with strong reference from static Deque.
            byte[] kept = new byte[128 * 1024];
            kept[0] = (byte) step;
            RETAINED.addLast(kept);

            if ("bounded".equals(mode) && RETAINED.size() > 32) {
                RETAINED.removeFirst();
            }
            lastBurst = null;

            if (step % 20 == 0) {
                MemoryUsage heap = ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();
                System.out.printf(Locale.ROOT,
                        "step=%d retained=%d used=%.1f MiB committed=%.1f MiB%n",
                        step, RETAINED.size(),
                        heap.getUsed() / 1_048_576.0,
                        heap.getCommitted() / 1_048_576.0);
            }
            Thread.sleep(500);
        }
    }
}
```

Compile:

```bash
javac HistogramTrendDemo.java
```

Run **one mode at a time** to avoid PID confusion and resource contention. In Terminal A:

```bash
java -Xms64m -Xmx128m -XX:+UseG1GC HistogramTrendDemo bounded
```

Output always starts with a line formatted like `PID=12345 mode=bounded`. `used` and `committed` numbers are **not fixed**; when printed at steps 20, 40, and 60, the `retained` counter is `20`, `32`, `32` because the code caps at 32 items. The program runs 240 steps spaced by at least 500 ms (around two minutes, potentially longer due to GC or diagnostic commands).

In Terminal B while the process is still running, substitute the actual PID and capture checkpoints roughly after steps 40/80/160:

```bash
jcmd 12345 GC.class_histogram > bounded_T0.txt
jcmd 12345 GC.class_histogram > bounded_T1.txt
jcmd 12345 GC.class_histogram > bounded_T2.txt
```

**These commands are three manual actions at three distinct times**; do not run them back-to-back immediately; wait an adequate sampling interval between runs and note the application's actual step. You can sample GC via `jstat -gcutil 12345 1000 5` in between.

After the `bounded` process exits, run again in Terminal A:

```bash
java -Xms64m -Xmx128m -XX:+UseG1GC HistogramTrendDemo growing
```

Capture using the same protocol for the **new PID**, saving `growing_T0.txt`, `growing_T1.txt`, `growing_T2.txt`. When printed at steps 20/40/60, `retained` is `20`, `40`, `60`, since nothing is evicted.

### Expected observations and how to write conclusions

- **`bounded`:** after warm-up, the number of intentionally retained `byte[]` arrays stabilizes around the cap; other Java/JVM buffers can make total `[B` fluctuate, so the histogram need not be strictly flat.
- **`growing`:** `RETAINED` adds one `128 KiB` array per step, so intentionally retained data grows by roughly `128 KiB/step` (240 steps ≈ 30 MiB of array data, excluding overhead). The `[B` histogram and post-GC floor tend to rise, though exact measurements remain influenced by JVM/GC activity.
- **Key point:** from a growing histogram alone you cannot tell why; reading the source in this exercise reveals the `static RETAINED` reference and the two lifecycle modes. In real projects, you uncover this relationship via a heap dump, business context, and GC root analysis.

Never pair results from two different JVMs as T0/T1 to compute a delta. **Each mode must have its own T0–T2 series inside its own JVM** before comparing trend shapes between modes.

## 9. When Do You Need a Heap Dump Instead of Another Histogram?

Histograms across multiple checkpoints identify **suspect classes and trends**. Asking "which object is retaining this data?" requires moving to the object graph—for example, an HPROF heap dump:

```bash
jcmd 12345 GC.heap_dump heap_T2.hprof
```

Run only after weighing pause impact, disk space, permissions, and sensitive information that may reside in the heap. On HotSpot JDK 21, `GC.heap_dump` is documented as **Impact: High** and **requests a Full GC unless `-all` is used**. Therefore, default dumps and `-all=true` dumps do not share identical reachability semantics. Capture T1/T2 in the same mode and log any shifts caused by the dump/GC.

In **Eclipse Memory Analyzer (MAT)** or an equivalent tool, do the following:

1. **Histogram / Top Consumers:** verify object types and corresponding shallow heap; find classes that grew significantly when comparing two dumps under equivalent conditions.
2. **Dominator Tree:** see which object/structure dominates a large object set; **retained size** estimates memory freed if that anchor is removed.
3. **Path to GC Roots:** trace back from suspect objects to static fields, threads, thread-locals, JNI roots, class loaders, etc., to learn **why objects stay reachable**.
4. **Check business lifecycle:** should that reference still exist at T2? If data was only needed during a completed request, why is it still inside a registry/cache/queue?
5. **Verify via experiment:** bound caches, unregister listeners, expire keys, close resources, etc., in a suitable environment; repeat the same workload and confirm post-GC floor and retained paths stop accumulating.

**A root retaining millions of objects is not automatically a bug.** That structure may be an intentional cache. The final question is: "Is it holding **the right objects that are still needed** for **the right duration**?"

Distinction:

| Tool | Claim it supports | What is still missing |
| --- | --- | --- |
| Single histogram | Class X has N instances, B shallow bytes at time T | Trend, roots, lifecycle, abnormality |
| Multiple histograms under same conditions | Class X has a delta/growth rate across checkpoints | Which specific objects persist, reference paths |
| Heap/GC metrics over time | Post-GC floor rises/stabilizes, GC pressure changes | Specific objects and owners driving growth |
| Heap dump + dominators + GC roots | Retention paths and retained graph at capture time | Business context to conclude improper retention |
| Before/after fix test | Tests causal hypothesis under equivalent load | Confidence across multiple cycles, edge cases, regressions |

## 10. Investigation Report Template and Responsible Phrasing

Use a consistent table to avoid making claims that go beyond the data:

| Checkpoint | Time/PID | Workload | GC context | N of suspect class | Shallow bytes | Post-GC heap used | Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| T0 | ... | post warm-up, load A | ... | ... | ... | ... | Baseline |
| T1 | ... | load A, after 1 cycle | ... | ... | ... | ... | Delta vs. T0 |
| T2 | ... | load A or queue drained | ... | ... | ... | ... | Plateau check |
| T3 (if needed) | ... | after TTL/appropriate GC | ... | ... | ... | ... | Counter-check |

**Good conclusion example (hypothetical numbers):**

> Within the same HotSpot/G1 JVM, using default histograms at a steady load of ~100 requests/s, `OrderContext` count increased 2,000 → 3,200 → 4,400 over 20 minutes; used heap after comparable GC cycles climbed from 120 to 180 MiB. Observed requests completed and queues did not grow. This is a retention signal requiring investigation. Evidence is not yet sufficient to confirm a leak or retaining owner; the next step is locating dominators/GC roots in a heap dump and verifying `OrderContext` TTL/lifecycle.

**Weak conclusion example:** "The histogram has lots of `byte[]`, so the app definitely leaks." This omits traffic, timeframe, measurement mode, GC type, and object ownership.

Do not write "leak proven" just because two histograms grew. Match language to evidence strength: **observation → suspicion → causal reference path → confirmed by experiment**.

## 11. Common Mistakes

1. **Concluding from one histogram:** unknown direction of change, pre/post-business-cycle context, or baseline.
2. **Subtracting by row rank `num`:** ranks shift; match by exact class, accounting for multiple class loaders with the same name.
3. **Reading `#bytes` as retained size:** it is per-class shallow total; it does not prove those objects retain an entire reference subtree.
4. **Comparing default histogram with `-all=true`:** one side may count unreachable objects; the measurements mean different things.
5. **Misaligned time/load:** one snapshot mid-batch and another while idle do not form a representative delta.
6. **Ignoring collector and recent GC activity:** comparing pre-GC `used` with post-GC `used` and declaring "leak fixed" or "leak worsened."
7. **Confusing `heap.committed` or RSS with live set:** committed is memory reserved by the JVM; RSS also includes native/stack/direct memory; histograms do not explain all of RSS.
8. **Ignoring cache warm-up and TTL:** object growth during cache population or valid session lifetime may be completely expected.
9. **Focusing on ubiquitous classes while ignoring owners:** `String`/`byte[]` appear in countless libraries; you need root paths and business context.
10. **Citing percentages without byte/count deltas:** huge percentages can correspond to trivial absolute changes.
11. **Capturing histograms too frequently in production:** the command is High Impact and can perturb latency/GC itself.
12. **Forcing Full GC without logging it:** alters live set and latency, turning the experiment into a different condition.
13. **Comparing class counts across different versions/deployments:** schemas, traffic, code paths, GC, caches, and class loaders may differ.
14. **Assuming linear early growth proves unbounded growth:** many caches grow linearly during warm-up before hitting their cap.
15. **Skipping experimental verification:** even a path to a static cache is insufficient if that data is genuinely supposed to stay live.

## 12. Self-Assessment Exercises

**Scenario A:** T0 shows 10 MiB shallow `byte[]`, T1 shows 18 MiB while a queue grows from 200 to 2,000 items, and T2 returns to 11 MiB after the queue drains and GC runs. Which conclusion fits?

Hint: numbers fit **temporary backlog/retention**; no evidence of a leak. Confirm queue completion and corresponding array lifecycles.

**Scenario B:** under identical workload and config, T0/T1/T2 are spaced 30 minutes apart; post-GC used rises 300 → 390 → 480 MiB, `SessionRecord` and `HashMap$Node` grow steadily, and old sessions have already expired. What do you do?

Hint: report **sustained retention suspicion**, capture a heap dump at an appropriate time, locate the map/registry holding `SessionRecord` and its paths to GC roots, and inspect TTL. Only after confirming unneeded objects remain referenced and fixing eviction stabilizes the trend can you attribute a leak mechanism.

**Scenario C:** two histograms report `byte[]` doubled, but T0 used default mode while T1 used `-all=true`. Should you compute `Δ` to draw conclusions?

Hint: **no**; reachability conditions differ, so re-sample using the same mode.

**Practice:** run both `bounded` and `growing` modes from Section 8, capture three time-series histograms, extract `[B` counts/bytes, and record both `retained` from stdout and `heap.used`. Write a 5-sentence report covering: conditions, T0–T2 metrics, deltas, lifecycle explanation, and next verification step. Claim only what the data supports.

## 13. Authoritative Reference Documentation

- [Oracle JDK 21 — `jcmd`, `GC.class_histogram` / `GC.heap_dump`, and impact levels](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — Troubleshoot Memory Leaks: live set, serial histograms, and leak hypotheses](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html).
- [Oracle JDK 21 — Diagnostic Tools: JFR, JMX, and GC evidence](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html).
- [Eclipse MAT — Dominator Tree: retained graph](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html).
- [Eclipse MAT — Finding Memory Leak: Top Consumers and Paths to GC Roots](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html).

**Guiding principle:** one histogram tells *what is present*; multiple checkpoints under matching conditions tell *what is changing*; heap dumps, GC roots, and business lifecycle explain *why objects remain held*, and controlled experiments confirm the hypothesis.
