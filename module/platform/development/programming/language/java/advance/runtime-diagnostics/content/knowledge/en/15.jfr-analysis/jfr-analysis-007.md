# 15.7. Analyzing allocation samples, GC, heap summary, and OldObjectSample with JFR

When a Java service uses more memory or spends significant time in garbage collection, the first question is often "which class is creating so many objects?". However, **creating many objects (allocation pressure)**, **heavy GC activity**, **high post-GC heap occupancy**, and **long-lived object retention** are four distinct phenomena. Java Flight Recorder (JFR) provides event groups to investigate them in order instead of looking at one table and jumping to a memory leak conclusion.

This lesson focuses on four layers of evidence in modern HotSpot/JDK:

1. **Allocation samples:** `jdk.ObjectAllocationSample` helps identify object types, threads, and call stacks driving allocation pressure.
2. **GC:** `jdk.GarbageCollection` together with pause/phase events show frequency, collector type, and collection cost.
3. **Heap summary:** `jdk.GCHeapSummary` tracks heap usage before and after GC, helping identify a rising live set or residual occupancy.
4. **OldObjectSample:** `jdk.OldObjectSample` provides samples of long-lived objects, allocation timestamps, and—when collected—reference paths back to GC roots.

The right output of an investigation is not "there is a lot of `byte[]`, so it's a leak," but a **concrete hypothesis supported by events from the same time window**—for example: request parsing drives most allocations → GCs run frequently → post-GC heap remains stable → this is **temporary churn**, not a leak; or a cache holds objects across load cycles → post-GC heap floor rises → `OldObjectSample` shows objects reachable from an unbounded cache.

## 1. Four perspectives, four different questions

| Event / perspective | Question it helps answer | Data typically observed | What must not be inferred directly |
| --- | --- | --- | --- |
| `jdk.ObjectAllocationSample` | **Where** are objects created? Which component creates allocation pressure? | `objectClass`, `weight`, event thread, stack trace if enabled | Exact instance counts; that those instances are still alive; retained heap |
| `jdk.GarbageCollection` and pause/phase events | When did GC run, for how long, and why? | `gcId`, `name`/`cause` when present, `duration`, GC phases | That every `duration` is stop-the-world time; the root cause of a leak |
| `jdk.GCHeapSummary` | How much heap is used **before/after a GC**? | `gcId`, `when`, `heapUsed`, `heapSpace` (reserved/committed) | That post-GC heap is all leaked; or that this event alone classifies retained objects |
| `jdk.OldObjectSample` | Which objects **lived long enough to investigate**, when were they allocated, and who might hold them? | `allocationTime`, `objectAge`, `object`, `root`, stack trace when available | List of all live objects; full heap histogram; definitive proof of a leak |

**Remember the core distinctions:**

- **High allocation rate**: many bytes/objects created per second; many objects may die very quickly.
- **GC pressure**: GC has to run frequently or causes noticeable pauses; may stem from allocation churn, small heap, large live set, or GC tuning.
- **Heap occupancy**: amount currently in use at measurement time; a "sawtooth" rise/drop cycle is normal.
- **Retention**: objects remaining reachable over time/GC cycles; only suspicious when lifetimes exceed design intent and cause the live set to grow uncontrollably.

JFR is a **stream of sampled or point-in-time events**, not a full dump of the entire object graph. When you need to prove the exact retained object structure and retained sizes, HPROF/heap dumps and tools like Eclipse MAT add essential value.

## 2. Preparing and verifying a recording with suitable data

Suppose you have a file named `memory-investigation.jfr`. Before analyzing, use a compatible JDK to inspect it:

~~~bash
jfr summary memory-investigation.jfr
jfr metadata --events jdk.ObjectAllocationSample,jdk.GarbageCollection,jdk.GCHeapSummary,jdk.OldObjectSample memory-investigation.jfr
~~~

- `jfr summary` shows the recording time span, sizes, and counts per event type; **an absent event may mean it was disabled, did not occur, or was not captured in this window**.
- `jfr metadata` describes field names and types, avoiding schema guesswork when comparing files from different JDK versions.
- Correlate the recording window with **spike timestamps**, request rate, load, deployments, `-Xmx` setting, and JVM/collector version. A tiny file or short capture window can miss the issue.
- If multiple recordings run concurrently, verify the recording name and scope when dumping; do not assume a file holds exactly one session if `name` was omitted on dump.

When capturing fresh data on HotSpot JDK 21, confirm the right PID via `jcmd -l` and the app's PID, e.g., **12345** (illustrative PID only; replace with the actual PID):

~~~bash
jcmd 12345 help JFR.start
jcmd 12345 help JFR.dump
jcmd 12345 JFR.start name=memory-investigation settings=profile disk=true maxage=15m maxsize=256m
jcmd 12345 JFR.check name=memory-investigation verbose=true
~~~

Wait for the application to experience the workload under study, then dump using a **path writable by the target JVM**:

~~~bash
jcmd 12345 JFR.dump name=memory-investigation filename=/var/tmp/jfr/memory-investigation.jfr
jcmd 12345 JFR.check name=memory-investigation
~~~

`JFR.dump` creates a snapshot **without stopping the recording**. `settings=profile` generally provides more detailed allocation/stack info than `default` and may consume extra resources. `maxage`/`maxsize` limits are **retention policies**; evicted intervals cannot be recovered.

When no longer needed, save final data and stop the specific session:

~~~bash
jcmd 12345 JFR.stop name=memory-investigation filename=/var/tmp/jfr/memory-investigation-final.jfr
~~~

Avoid reusing the same filename across dump/stop calls. If the app runs in a container, files are written in the **target JVM's** filesystem, which may differ from the caller's host. Check attach permissions, quotas, disk space, artifact storage, and data sensitivity before capturing in production.

### Enabling events with the right scope

JFR ships with default configs `default.jfc` and `profile.jfc` in the JDK; event settings can be toggled or their sampling thresholds adjusted. To see which events are **actually** being recorded, inspect `JFR.check ... verbose=true` or the `.jfc` file. On JDK 17+, event settings can be passed via startup options/`JFR.start`; for precision, check the target JVM's documentation before configuring.

Distinguish carefully:

- `jdk.ObjectAllocationSample` is a **sampled allocation distribution**. It is generally better suited for analyzing where objects are created with controllable overhead. `jdk.ObjectAllocationInNewTLAB` and `jdk.ObjectAllocationOutsideTLAB` also exist in many HotSpot JDKs, with different sampling semantics and configurations; never count events as if one event equals one object.
- `jdk.GarbageCollection` and `jdk.GCHeapSummary` are commonly present in standard JFR profiles; collector-specific events like `jdk.G1HeapSummary` depend on the collector/JDK. Not seeing `G1...` while running a different collector is not an error.
- `jdk.OldObjectSample` relies on sampling conditions and object lifetimes; **simply enabling JFR does not guarantee events will be emitted**. `root` info may be absent unless GC root path collection was requested.

## 3. Allocation samples: identifying "who creates allocation pressure"

Extract the sample events:

~~~bash
jfr print --events jdk.ObjectAllocationSample --stack-depth 15 memory-investigation.jfr
~~~

On HotSpot JDK 21, `jdk.ObjectAllocationSample` has notable fields:

- `objectClass`: class of the sampled object, such as `byte[]`, `java.lang.String`, or an application class.
- `weight`: **sample weight** representing a statistically sampled allocation amount. Summing weights across many samples by class/thread/stack helps **estimate allocation pressure trends**, though **a single sample's weight does not necessarily equal the size of the sampled object itself**.
- `eventThread`: thread associated with the sample, when available.
- `stackTrace`: allocation site, when collection settings allow saving stacks.

**Avoid confusing sample counts with object counts:** 150 samples does not mean exactly 150 objects were created. Nor can you multiply sample count by "average instance size" to claim actual bytes allocated. When comparing runs, use equivalent time spans and sampling policies, and account for throughput.

### 3.1. How to read the stack trace

Suppose (**illustrative** data) many `byte[]` samples show the stack:

~~~text
HttpDecoder.decode(...)
  -> PayloadParser.parse(...)
     -> Arrays.copyOf(...)
~~~

This points to an **allocation site**: payload-parsing code copies arrays frequently. It does **not** tell you whether those arrays are retained for long. Most may be reclaimed by GC right after the request. The next step is checking GC frequency, post-GC heap levels, and—if retention is suspected—`OldObjectSample`/heap dump.

In JDK 21, `jfr view` can aggregate several event types into tables:

~~~bash
jfr --help view
jfr view types memory-investigation.jfr
~~~

Pick **views that actually exist** in that JDK version's help output, because view names and aggregation capabilities change across versions. Do not assume an arbitrary view name is available across all JDK 17/21 builds. Beyond the CLI, Java Mission Control (JMC) groups allocation samples by **class, thread, and stack trace** and plots heat maps over time.

### 3.2. Valid conclusions from allocation samples

You can state: "Under the same load, the `PayloadParser.parse` stack accounts for most of the *estimated allocation weight*, corresponding to heavy `byte[]` creation." You cannot yet state: "`PayloadParser.parse` retains those arrays in the heap" unless independent retention evidence exists.

A high allocation rate can keep GC busy even when **the post-GC heap floor is stable**. Optimizing this case may focus on buffer reuse, reducing copies, sensible batching, or avoiding intermediate objects; re-measure latency/throughput after changes to avoid futile optimizations.

## 4. GC events: inspecting frequency, duration, and GC type

Commonly used events:

~~~bash
jfr print --events jdk.GarbageCollection memory-investigation.jfr
jfr print --events jdk.GCPhasePause memory-investigation.jfr
~~~

`jdk.GarbageCollection` represents a GC operation recorded by the JVM, usually with `gcId`, collector name/cause, and `duration`. `jdk.GCPhasePause` adds details on associated pause phases. Distinguish **GC operation duration** from **actual stop-the-world application pause time**: with concurrent collectors, the total GC operation includes phases running concurrently alongside application threads; never treat every `GarbageCollection.duration` as total STW pause.

What to inspect over time:

1. Do GCs **repeat more densely** right when traffic or allocation weight rises?
2. Do p95/max pauses increase, driving request tail latency? Inspect individual pauses, not just averages.
3. Which `gcId` corresponds to heap drops in `GCHeapSummary`?
4. Does the collector trigger more concurrent cycles, full/old collections, or change behavior? Event names and collection types depend on JDK/collector.
5. Are there frequent GCs while post-GC heap drops low and stays flat? Then allocation churn is a stronger suspect than a retention leak.

**Hypothetical example:**

| Minute | Allocation pressure | GC count/min | Post-GC heap | Initial interpretation |
| --- | ---: | ---: | ---: | --- |
| 10:00 | Low | 2 | 180 MiB | Normal |
| 10:01 | High | 13 | 185 MiB | Many short-lived objects; GC is keeping up |
| 10:02 | High | 15 | 184 MiB | Churn still high; no live-set growth seen yet |
| 10:03 | Low | 2 | 181 MiB | Load drops; heap floor returns to normal |

Data like this **does not prove a leak**, even if total allocated bytes are huge. If latency degrades at 10:01–10:02, prioritize hot allocation sites and pause metrics.

### GC ID and event correlation

GC/heap events can share a `gcId` linking *before GC → GC progress → after GC*. Base analysis on IDs and timestamps from the specific recording; do not blindly pair adjacent "before" and "after" events if events are missing or cycles run concurrently.

## 5. Heap summary: spotting trends in the "post-GC heap floor"

Command to inspect:

~~~bash
jfr print --events jdk.GCHeapSummary memory-investigation.jfr
~~~

For `jdk.GCHeapSummary` on HotSpot, key fields are:

- `gcId`: identifier of a GC cycle/collection in the data.
- `when`: indicates **Before GC** or **After GC**.
- `heapUsed`: heap bytes reported in use by the JVM at that snapshot point.
- `heapSpace`: heap space info, including reserved and committed regions per the event model.

The right analysis is **pairing before/after entries by `gcId`**. Purely hypothetical example:

| GC ID | Heap before GC | Heap after GC | Delta | Initial meaning |
| --- | ---: | ---: | ---: | --- |
| 41 | 730 MiB | 260 MiB | 470 MiB | Large amount reclaimed |
| 42 | 740 MiB | 262 MiB | 478 MiB | Live set appears stable |
| 43 | 780 MiB | 320 MiB | 460 MiB | Worth checking as floor rose |
| 44 | 820 MiB | 390 MiB | 430 MiB | Possible retention or changed workload |

The drop between before/after reflects occupancy change during one collection, **not** an exact count of "dead objects" or "leaked bytes." Committed heap can vary independently; some GCs only collect **part of the heap**, so `After GC` of a young collection is not "the entire heap was swept clean." With G1 or concurrent collectors, understand collection scope and application state; do not conclude old gen is growing from just a few young GCs.

### 5.1. Distinguish used, committed, reserved, and max

- **Used:** heap space currently in use as measured at the event timestamp.
- **Committed:** heap memory the JVM has committed; not necessarily equal to `used` or RSS.
- **Reserved:** virtual address space reserved for the heap; does not mean all of it is resident in RAM.
- **Max heap:** configured JVM limit, typically tied to `-Xmx`; distinct from used/committed/reserved.

Neither `jdk.GCHeapSummary` nor JFR metadata replaces checking actual `-Xmx`, non-heap, native memory, and container memory. When process RSS rises while post-GC `heapUsed` stays flat, check thread stacks, direct buffers, Metaspace, and NMT/OS metrics instead of calling it a Java heap leak.

### 5.2. What does a "rising post-GC floor" mean?

If Full/mixed/old GCs under comparable load show **after-GC heap** rising steadily and not dropping after load subsides, that is a suspicious sign of **retention**. However, it could also stem from legitimate cache warm-up, more connections/sessions, dataset changes, request backlogs, or collectors not having swept all regions yet. Find what retains the objects and compare against design limits/lifetimes.

GC heap summary is **not** a per-class histogram; it does not identify classes or paths to GC roots. That is why you combine it with allocation samples, `OldObjectSample`, and potentially HPROF.

## 6. OldObjectSample: investigating long-lived objects and reference roots

Print the events:

~~~bash
jfr print --events jdk.OldObjectSample --stack-depth 20 memory-investigation.jfr
~~~

A `jdk.OldObjectSample` may contain:

| Field | Interpretation |
| --- | --- |
| `allocationTime` | When the object was allocated, helping distinguish old objects from newly created ones |
| `objectAge` | Age of the sampled object when the JVM recorded the event |
| `object` | The object and part of its reference chain as described by the tool; not the full heap graph |
| `root` | GC root information if GC root path collection was enabled and data exists |
| `stackTrace` | Allocation-site stack when profile/settings support it |
| `lastKnownHeapUsage` | Most recent heap usage associated with the sample; read as a trend, not the retained size of this single object |
| `eventThread` | Thread that recorded the event, aiding context tracing |

**A long-lived object is not automatically a leak.** Singletons, bounded caches, configuration data, runtime class metadata, and application-lifetime objects are meant to live long. A leak is **retention that no longer serves a purpose yet continues growing the live set**.

### 6.1. To get paths to GC roots: capture at the right time

Per **JDK 21** `jcmd`, the exact dump option is **`path-to-gc-root=true`** (singular `root`):

~~~bash
jcmd 12345 JFR.dump name=memory-investigation filename=/var/tmp/jfr/memory-roots.jfr path-to-gc-root=true
~~~

Collecting paths to GC roots can cause noticeable pauses and processing overhead. Enable it only when you have a concrete leak hypothesis, on the right recording, and in an appropriate operational window. JVM startup docs or other versions may use different option names across contexts; **always check `jcmd 12345 help JFR.dump` on the target JVM** rather than copying flags verbatim from elsewhere.

If the file has no `OldObjectSample`, it does not mean "no leak." Causes can include too short a recording, too few surviving samples, collector/JDK limitations for that case, disabled event in the profile, or a poorly timed snapshot. Nor can it reconstruct allocation stacks missed before JFR started recording.

### 6.2. Reading reference chains

**Illustrative** example of a `com.example.Session` sample held via:

~~~text
GC Root (static field)
  -> SessionRegistry.INSTANCE
  -> ConcurrentHashMap.values
  -> Session(id=...)
~~~

This path suggests `SessionRegistry` holds sessions after users log out, though it is still a **hypothesis**. Verify cleanup/TTL policies, valid session counts, map size trends, and GC root paths across multiple samples. If the same registry grows steadily hour over hour alongside rising after-GC heap, retention evidence becomes much stronger.

Conversely, if a large sample is held by a size-bounded cache and memory is reclaimed on eviction, high `objectAge` is not a leak. Do not treat `OldObjectSample` as an exact per-class instance table; sampling omits objects.

### 6.3. Comparing OldObjectSample with a heap dump

| Criterion | JFR `OldObjectSample` | HPROF heap dump |
| --- | --- | --- |
| Object coverage | Sample of long-lived/potentially retained objects | Broad point-in-time snapshot of the Java heap |
| Time information | Can include allocation time, object age, and capture context | Primarily state graph at dump time |
| Path to GC root | Can be recorded when requested and supported by the JVM | Tools like MAT analyze from the full snapshot |
| Level of detail | Sampled; may miss the culprit | Computes full histograms and broader retained graphs |
| Impact | Sampling is usually lighter than a heap dump, though computing GC roots can be costly | Heap dumps are often heavy, can cause long pauses, and create huge files |

If JFR points to a suspicious class or cache without conclusive proof, take a well-timed heap dump to inspect dominator trees/retained sizes. Never add `weight` from allocation samples to `lastKnownHeapUsage` and call it retained heap.

## 7. Investigation workflow linking all four evidence sources

**Step 1 — confirm symptom and timing.** Record latency, throughput, heap occupancy, GC pauses, container memory, and release timestamps. An allocation spike during warm-up may be completely benign.

**Step 2 — read `jfr summary`.** Verify the recording window covers the incident; check for sufficient `ObjectAllocationSample`, `GarbageCollection`, `GCHeapSummary`, and (when needed) `OldObjectSample`. Zero events is not a conclusion about app behavior until settings and sampling are checked.

**Step 3 — locate allocation hotspots.** Group samples by stack/class/thread, prioritizing **total sampled weight over the same time window** rather than raw event counts. Identify allocating code paths and how they vary with load.

**Step 4 — cross-check GC.** Count GCs per unit time, inspect causes, collector phases, and **pause durations**; check whether load spikes align with rising allocation, GC, or latency.

**Step 5 — pair heap before/after by `gcId`.** If after-GC is stable, suspect temporary churn; if the live set climbs uncontrollably after appropriate GCs, shift focus to retention.

**Step 6 — inspect `OldObjectSample` and GC roots.** Examine `objectAge`, `allocationTime`, object class, owner chain, `root`, and app lifecycle policies. If root data is missing, plan a dump with `path-to-gc-root=true` after weighing pause impact.

**Step 7 — test the hypothesis.** Inspect queue/cache/session metrics, relevant source code, and a heap dump if needed; change storage logic, TTLs, cache bounds, or reduce allocations and **re-measure under the same load**. If allocation weight drops afterward while after-GC heap stays unchanged, you improved churn, not necessarily fixed a leak.

### Evidence-pattern decision matrix

| Allocation weight | GC frequency/pauses | Post-GC heap | Old objects/roots | How to prioritize investigation |
| --- | --- | --- | --- | --- |
| High | Rising | Stable | No retention evidence | Look for allocation churn; optimize copies/intermediate objects |
| Normal | Rising, long pauses | Near max | Rising old objects and unexpected retaining roots | Suspect retention/leak or large live set |
| High | High | Rises, then returns when load drops | Surviving objects match request/cache lifetime | Load or heap sizing; do not call it a leak without proof |
| Not rising | Not rising | Stable | No suspects visible | If RSS still climbs, investigate native/off-heap |
| Low | Few GCs | Climbing steadily | Roots into unbounded map/list | Suspect cache/collection retaining objects despite modest new allocation |

These rows are **reasoning patterns**, not rigid laws. In practice, GCs may collect regionally, collectors differ in semantics, and sampling has variance.

## 8. Java 17+ hands-on: generate allocation load and retain some objects

The following example creates temporary arrays and retains a few arrays in a static list to illustrate **allocation** vs. **retention**. It does not fully simulate a production memory leak, and data size is intentionally bounded to avoid exhausting the heap.

Create **`JfrMemoryLab.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class JfrMemoryLab {
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile int checksum;

    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());

        for (int i = 0; i < 1_500; i++) {
            byte[] temporary = new byte[128 * 1024];
            temporary[0] = (byte) i;
            checksum += temporary[0];

            if (i % 100 == 0) {
                byte[] retained = new byte[256 * 1024];
                retained[0] = (byte) i;
                RETAINED.add(retained);
            }

            if (i % 150 == 0) {
                Thread.sleep(20L);
            }
        }

        System.out.println("Retained arrays=" + RETAINED.size());
        Thread.sleep(30_000L);
        System.out.println("Finished");
    }
}
~~~

Compile and run with JDK 17+ (HotSpot with JFR):

~~~bash
javac JfrMemoryLab.java
java -Xms32m -Xmx96m -XX:StartFlightRecording=name=memlab,settings=profile,filename=memlab.jfr,dumponexit=true JfrMemoryLab
~~~

Stdout lines printed by the **program itself**:

~~~text
PID=<actual PID for this run>
Retained arrays=15
Finished
~~~

PID differs on every launch; `Retained arrays=15` is deterministic because `i=0,100,...,1400` satisfy the retention condition. `Finished` appears after roughly a 30-second sleep unless the JVM is interrupted. Total temporary arrays created is 1,500, though JFR **does not necessarily record 1,500 `ObjectAllocationSample` events** since it is a sampled event. `-Xmx96m` sets a small-heap example without guaranteeing a fixed GC count across all JVMs.

After the program exits normally, inspect:

~~~bash
jfr summary memlab.jfr
jfr print --events jdk.ObjectAllocationSample --stack-depth 10 memlab.jfr
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary memlab.jfr
jfr print --events jdk.OldObjectSample memlab.jfr
~~~

- `memlab.jfr` is written at exit due to `dumponexit=true`; the path is resolved against the JVM's working directory.
- Depending on GC, JDK, event settings, and sampling timing, **there is no single fixed event set or sample/GC count**. If `OldObjectSample` is empty, that is not a test failure.
- During the 30 seconds while the JVM is still running, you can run `jcmd <PID> JFR.check` and trigger `JFR.dump` with `path-to-gc-root=true` if you want to test root capture; weigh the cost and use a different filename.
- After exit, you cannot attach to the old PID; launch a new run if you want further live actions.

### 8.1. Analyzing the file with the JFR Consumer API

This is a **second standalone program** with no dependency on `JfrMemoryLab`. It streams events sequentially instead of loading a large file into memory and prints counts by event group. Create **`JfrMemoryReport.java`**:

~~~java
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import jdk.jfr.consumer.RecordedClass;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrMemoryReport {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java JfrMemoryReport <file.jfr>");
            return;
        }

        long allocationSamples = 0;
        long totalSampleWeight = 0;
        long gcEvents = 0;
        long heapSummaries = 0;
        long oldObjectSamples = 0;
        Map<String, Long> weightByClass = new HashMap<>();

        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                String type = event.getEventType().getName();

                switch (type) {
                    case "jdk.ObjectAllocationSample" -> {
                        allocationSamples++;
                        long weight = event.getLong("weight");
                        totalSampleWeight += weight;

                        RecordedClass clazz = event.getClass("objectClass");
                        String name = clazz == null ? "<unknown>" : clazz.getName();
                        weightByClass.merge(name, weight, Long::sum);
                    }
                    case "jdk.GarbageCollection" -> gcEvents++;
                    case "jdk.GCHeapSummary" -> heapSummaries++;
                    case "jdk.OldObjectSample" -> oldObjectSamples++;
                    default -> { /* Other JFR event types are ignored. */ }
                }
            }
        }

        System.out.println("Allocation samples=" + allocationSamples);
        System.out.println("Sample weight (bytes)=" + totalSampleWeight);
        System.out.println("GC events=" + gcEvents);
        System.out.println("Heap summary events=" + heapSummaries);
        System.out.println("Old object samples=" + oldObjectSamples);
        weightByClass.entrySet().stream()
                .sorted((a, b) -> Long.compare(b.getValue(), a.getValue()))
                .limit(5)
                .forEach(e -> System.out.println(
                        e.getKey() + " => " + e.getValue()));
    }
}
~~~

Compile and run:

~~~bash
javac JfrMemoryReport.java
java JfrMemoryReport memlab.jfr
~~~

The program prints labels `Allocation samples=...`, `GC events=...` along with the top 5 classes. **Counts and class names are runtime data**, so no fixed numeric stdout is guaranteed. `Sample weight (bytes)` is simply a way to **sum sample weights to compare allocation pressure**, not exact "live bytes" or exact total bytes allocated; when comparing two builds, keep profile, capture window, and workload identical.

Note: this simple report only **counts** GC and heap events; serious analysis also reads `getDuration()` on GC events, `gcId`/`when`/`heapUsed` on `GCHeapSummary`, timestamps, and stack traces. Input must be a trusted JFR file; do not open files from untrusted sources in privileged tools.

## 9. Three diagnostic scenarios and how to avoid premature conclusions

### A. High allocation, frequent GC, but stable post-GC heap

JMC shows huge `byte[]` allocation weight in an HTTP decoder. GCs/min climb as request throughput rises, yet after-GC heap stays around 250 MiB. `OldObjectSample` shows no abnormal object retention. This looks like **allocation churn**. Measure per-request copying, batch parsing, and buffer management; test optimizations and compare throughput, GC pauses, and allocation weight under matched load.

### B. Unremarkable allocation, steadily rising post-GC heap

Total sample weight in request handlers is no higher than before, yet heap after relevant GCs climbs 200 → 400 → 650 MiB while active user count is unchanged. `OldObjectSample` repeatedly traces to a static `ConcurrentHashMap` holding old session data. This is a **retention suspect**: inspect TTLs, cleanup jobs, key cardinality, map entry counts, and removals, verifying with a heap dump/MAT if needed. Do not declare a definite leak before distinguishing cache warming from invalid sessions.

### C. RSS climbing, post-GC heap unchanged

When JFR shows flat after-GC heap and steady allocation pressure while OS/container metrics report growing process memory, there is no evidence of a Java heap leak. Inspect **direct buffers, thread stacks, Metaspace, and JNI/native allocations** using NMT/OS/cgroup tools instead of expecting `OldObjectSample` to explain every kind of memory.

## 10. Common mistakes and limitations

| Symptom | Explanation / handling |
| --- | --- |
| No `ObjectAllocationSample` | Event disabled, window too short, insufficient workload samples, or recording missed the target period. Check `jfr summary` and settings |
| Samples exist but no stack traces | Event stack trace may be disabled/truncated; check `verbose` settings or `jfr print --stack-depth` |
| `ObjectAllocationSample.weight` differs from object size | By design: weight represents statistically sampled allocation; do not treat it as the object's exact size |
| Many `GCHeapSummary` events but cannot pair them | Need `gcId` and `when`; some pairs are missing due to recording boundaries/filtering, or partial-heap GC reporting |
| High after-GC heap after young GC | Young GC may not collect old objects; check GC type and trends across appropriate collections |
| Large `GarbageCollection.duration` | With concurrent collectors, duration is not purely STW; also inspect pause/phase events |
| `OldObjectSample` empty | Insufficient long-lived samples, event disabled, unsupported runtime/collector, or mistimed capture; do not infer "no leak" |
| `OldObjectSample.root` missing | GC roots not requested or not captured; consider `JFR.dump ... path-to-gc-root=true` and pause cost |
| `.jfr` file huge / missing history | Balance profile, duration, and `maxage`/`maxsize` retention; evicted history cannot be recovered |
| `jcmd` cannot attach | Check PID, user/group, container namespace, runtime, and whether JVM is alive; use startup JFR flags if attach is blocked |
| Mistaking `.jfr` for HPROF | JFR is an event timeline; HPROF is a heap snapshot. Use the right tool for each |
| Counting raw events to infer performance | Sampling and trigger conditions vary; normalize by time, workload, and settings |

**Final decision rule:** ask **"who allocates?"** using allocation samples; **"what did GC do and how long did it take?"** using GC events; **"how much heap remains after GC?"** using heap summary; **"who still holds long-lived objects?"** using `OldObjectSample` and GC roots. Combining these views on the same timeline is what separates allocation churn, GC pressure, and memory retention.

## References

- Oracle Java SE 21 — *The jfr Command* (summary, print, metadata, view): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java SE 21 — *The jcmd Command* (JFR.start/JFR.dump, `path-to-gc-root`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java SE 21 — *Troubleshoot Memory Leaks* (explaining `OldObjectSample`, allocation time, GC roots): https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html
- Oracle Java SE 21 — *Diagnostic Tools* (GC, allocation, JMC analysis): https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Java SE 21 — *RecordingFile* in the JFR Consumer API: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html
- Dev.java — *Configuring the JDK Flight Recorder* (`default.jfc`, `profile.jfc`, event settings, and GC roots): https://dev.java/learn/jvm/jfr/configure/
