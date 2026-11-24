# 11.8 Distinguishing heap growth from load, legitimate data retention, and unintended reference retention

## Learning objectives

When you see the Java heap growing, you need to answer three different questions: **is the application creating more objects due to higher load**, **is the application holding data it still needs**, or **is an overly long-lived reference retaining data that should have been freed**? All three cases can push a heap graph upward; you cannot conclude a "memory leak" from a single memory usage peak.

After this lesson, you can read heap/GC graphs across workload lifecycles, design controlled measurements, analyze reference chains to GC roots, and choose the fix that matches the true mechanism of each case.

## 1. Understand accurately what is growing

The Java heap is the region managed by the JVM to allocate most objects and arrays. GC reclaims **objects that are no longer reachable from GC roots** (for example, references from live thread stacks, `static` fields, or internal JVM structures). An object that is "no longer useful to business logic" **is still not reclaimed** if a strong reference path to it remains.

Distinguish quantities that are often conflated:

| Metric | Meaning | What cannot be concluded |
| --- | --- | --- |
| `heap used` at a point in time | Heap space currently holding objects, including uncollected garbage | Not synonymous with all data being live; one high reading does not prove a leak |
| `heap used` after **comparable** GC phases | Approximates the live dataset after the corresponding collection | A single young GC (`young GC`) may leave garbage in the old region; do not compare arbitrarily against post-`mixed/full GC` |
| `heap committed` | Capacity the JVM has committed from the OS for the heap | Not synonymous with bytes currently needed by objects; the JVM may keep committed regions after load drops |
| `heap max`/`-Xmx` | Allowed heap limit | Does not explain why usage grew |
| `allocation rate` | Rate of allocating new objects | High rate can trigger frequent GCs without necessarily increasing long-retained data |
| `process RSS` | Physical memory currently used by the process | Includes the heap plus many off-heap regions; rising RSS is not automatically a heap leak |

**The two core drivers** are *allocation* (creating new objects) and *retention* (keeping objects reachable). A service can allocate gigabytes per minute and remain stable if objects die quickly, whereas a structure retaining a few extra KB per request can cause the live set to grow without bound over time.

Visualizing pre-GC heap usage typically yields a "sawtooth" curve: allocation pushes used up, GC pulls it down. **Troughs and trends after equivalent GC events**, paired with workload and the actual volume of data that must be retained, are far more informative than a single sawtooth peak snapshot. With concurrent or generational collectors, choosing the right GC event type and matching phase is mandatory.

## 2. Three distinct mechanisms

| Signal to compare | Heap growth from load | Legitimate data retention | Unintended reference retention |
| --- | --- | --- | --- |
| Source of growth | Concurrent requests/tasks, buffers, and temporary objects | Caches, sessions, in-flight state, indexes, data currently being processed | Uncleaned maps/lists, unregistered listeners, `ThreadLocal`, queues or callbacks holding objects |
| Relationship to load | Usually scales with traffic, concurrency, or batch size | Scales with active business items; may rise during cache "warm-up" | Can keep rising across cycles at constant load or after tasks have finished |
| After load drops and sufficient collection time | Temporary data generally returns toward an equivalent baseline | Intentional dataset remains; typically plateaus per policy | Live set trends upward across cycles and does not drop per expected lifecycle |
| Heap dump | Many objects tied to active work in flight | Reference paths from legitimate owners matching counts/TTL/bounds | Retention path from a long-lived owner to business-expired objects |
| Remediation direction | Cap concurrency/batch size, reduce allocations, add backpressure, adjust capacity | Define budgets, TTL, eviction, and business-driven release points | Remove bad reference paths, clean up on lifecycle boundaries, bound data structures |

### 2.1. Growth from load: more active work in progress

For instance, traffic jumps from 100 to 1,000 requests/second; each request parses JSON, holds byte buffers, and creates DTOs briefly. Heap used climbs between GCs; allocation rate and GC frequency may rise as well. When traffic drops back to 100 requests/second, in-flight requests and temporary data gradually subside. That is a reasonable response to a changing workload.

However, **"from load" does not mean "no problem"**: excessive concurrency, huge batches, or unbounded queues can still trigger `OutOfMemoryError`. The fix is to bound in-flight requests, chunk batches, cap queues, apply streaming/backpressure, or raise `-Xmx` after proving real capacity needs—not blindly blaming a GC bug.

If a request has already returned its response while an asynchronous task it spawned is still running, related data can still be held legitimately. Therefore, measure *active work* (in-flight requests, active tasks, and queue depth), not just HTTP requests/second.

### 2.2. Legitimate data retention: memory serving a clear purpose

A cache may grow from 0 to several hundred MB during warm-up and then level off once it hits its maximum entry count; active sessions, search indexes, or data inside a computation window behave similarly. Even though post-GC live set is high, the objects have an owner and a reason to exist.

It should only be called **legitimate retention** after proving that: (1) each item maps to an active business need; (2) lifecycle termination rules exist; (3) explicit memory/entry bounds or capacity math exist; (4) real observations reach a plateau under the defined workload. A cache without TTL, without max size, or with unbounded key cardinality can start as a valid design and turn into a **logical memory leak / capacity bug** over time.

Distinguish carefully:
- High yet stable post-GC `used` with good cache hit rate and within-budget entry count: potentially acceptable.
- A cache growing without bound alongside unique keys even under steady traffic: intentional storage with a **broken retention policy**.
- Cache entries evicted yet committed heap/RSS does not fall immediately: not proof that objects are still referenced.

### 2.3. Unintended reference retention: reference lifetime outlives data lifetime

In Java, a "memory leak" is usually **objects that have outlived their usefulness yet remain reachable**, rather than a forgotten `free` in manual memory management. Typical sources:

- A `static Map` or singleton storing results keyed by request/user ID without removal; key count grows continuously.
- Listeners/observers registered without unregistering, causing a long-lived publisher to retain subscribers and everything subscribers reference.
- `ThreadLocal` without `remove()` in a thread pool: values can linger on long-lived worker threads across many requests.
- Unbounded queues, caches, or retry lists; `Future`/callbacks retaining context and payloads after they should have completed.
- Class loaders still referenced by threads, registries, drivers, or static fields after reloading modules; classes and objects from the old loader cannot be collected.

**You cannot confirm a leak just because you see a large `HashMap`.** Ask who owns the map, whether each entry is still needed, whether a max/TTL exists, how entry count and total retained bytes change over time, and which reference path should have disappeared when the business operation "finished".

## 3. Reading graphs across the workload lifecycle

Structure observations into repeatable phases rather than inspecting a single flat trace:

1. **Baseline/warm-up:** startup, JIT warm-up, class loading, initializing connection pools/caches. Do not treat the first peak or trough as the long-term baseline.
2. **Steady load A:** hold request rate, concurrency, payload size, and key distribution roughly constant; capture heap used, allocation rate, GC events/pauses, active task count, and key entry counts.
3. **Increased load B:** raise one controlled variable (such as concurrency), recording peak heap and GC activity.
4. **Drop load and let work drain:** verify queues have drained and sessions/TTLs have had time to expire; compare points *after equivalent GC events*, without forcing `System.gc()` just to get a neat point.
5. **Repeat load A:** if after identical A rounds the baseline live set and owner/entry counts keep rising, hypothesize unintended retention and inspect a heap dump.

Qualitative examples:

| Observation after two identical load rounds | Likely explanation | Remaining evidence needed |
| --- | --- | --- |
| Peak `used` rises during B, returns to an equivalent baseline when A returns | Temporary objects scaling with load | Active task count dropped, allocation/GC correlated |
| Baseline climbs during warm-up then flattens, cache hits 5,000/5,000 entries | Bounded legitimate retention | Hit rate, eviction policy, TTL, byte budget |
| Post-GC baseline climbs after each A round, map grows 5,000 → 10,000 → 15,000 keys | Suspected unintended retention | Whether keys are still valid, path to GC roots, cleanup timing |
| Heap used drops while committed/RSS stays nearly flat | JVM keeps allocated capacity | Compare live objects and non-heap; do not infer a leak from RSS |

Measuring points under *identical conditions* matters more than a rigid threshold. For example, two post-GC `used` readings of 400 MB and 600 MB cannot be directly compared if the second run has twice as many valid active sessions. Normalize by session count, entries, batch size, and concurrency to evaluate "bytes per unit of work/data".

### Three hypothesis-testing questions

- **Did allocation increase?** Watch allocation rate, request count, and objects created per request. If it spikes while long-term post-GC live set stays flat, prioritize reducing churn/GC cost.
- **Did retention increase for a valid reason?** Count entries/sessions/indexes, data age, and capacity settings. If counts match demand and bounds/eviction exist, test for a plateau.
- **Which object retains expired data?** Compare heap histograms/dumps under matching conditions, trace GC root → long-lived owner → retained objects, and compare against when business logic should have released them.

## 4. Java 17+ illustration: same array allocations, different lifecycles

The standalone example below intentionally uses small arrays to observe **references and entry counts** with deterministic output; it is not a benchmark or exact heap measurement program.

```java
// File: HeapGrowthCases.java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

public class HeapGrowthCases {
    private static final Map<Integer, byte[]> UNBOUNDED = new HashMap<>();

    private static final Map<Integer, byte[]> BOUNDED =
            new LinkedHashMap<Integer, byte[]>(16, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(
                        Map.Entry<Integer, byte[]> eldest) {
                    return size() > 4;
                }
            };

    public static void main(String[] args) {
        int checksum = 0;
        for (int i = 0; i < 10; i++) {
            byte[] temporary = new byte[1024];
            temporary[0] = (byte) i;
            checksum += temporary[0];

            BOUNDED.put(i, new byte[1024]);
            UNBOUNDED.put(i, new byte[1024]);
        }

        System.out.println("temporary checksum=" + checksum);
        System.out.println("bounded entries=" + BOUNDED.size());
        System.out.println("unbounded entries=" + UNBOUNDED.size());

        UNBOUNDED.clear(); // Simulate cleanup when data has expired.
        System.out.println("unbounded after cleanup=" + UNBOUNDED.size());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac HeapGrowthCases.java
java HeapGrowthCases
```

Deterministic stdout:

```text
temporary checksum=45
bounded entries=4
unbounded entries=10
unbounded after cleanup=0
```

Explanation of each case:

1. `temporary` is used only to accumulate `checksum` in a single loop iteration; it is not stored in any long-lived structure. After its last use, the array may become unreachable, though **immediate GC is not guaranteed**.
2. `BOUNDED` is an LRU-style cache holding at most 4 entries via `removeEldestEntry`. Data stays legitimately retained if those 4 entries serve a real need; an entry-count limit **does not replace** a byte budget if each value has variable size.
3. `UNBOUNDED` accepts every new key and remains held by a `static` field. If the loop repeats across requests with distinct keys and no cleanup, old data can stay reachable forever; calling `clear()` at lifecycle end drops references from the map to values, allowing GC to reclaim them if no other owner remains.

A `static` map is not automatically a bug, and `clear()` is not a universal fix: in real applications, define lifecycle policies, TTL, eviction, or owner-scoped release. After `clear()`, `heap used` may not drop until an appropriate GC runs; `committed` may also remain unchanged.

## 5. JVM diagnostic toolset

### 5.1. Collect continuous metrics before taking snapshots

Prefer time-series graphs labeled with version, workload, GC collector, and heap configuration:

- Heap used/committed/max; where available, usage by generation/region and collector-appropriate post-GC baselines.
- Allocation rate, GC count/time/pauses, CPU spent on GC, p95/p99 latency, and throughput.
- Request concurrency, queue depth, batch size, session count, cache size/hits/misses/evictions, and unique key count.
- RSS and non-heap to spot issues outside the Java heap.

Record GC logs from startup, for example on Java 17+:

```bash
java -Xms256m -Xmx1g -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
```

`app.jar` is your application JAR; this is a startup command template, not the command to run `HeapGrowthCases.java`. Analyze the actual collector and GC types: with G1, a single young GC does not prove the entire old generation was cleaned. GC logs align timestamps, collection types, and pauses with workload graphs; they do not by themselves identify which owner retains an object.

### 5.2. `jcmd`: inspect status and gather targeted evidence

Find the PID and inspect heap information:

```bash
jcmd -l
jcmd <pid> GC.heap_info
```

When you need object type distribution:

```bash
jcmd <pid> GC.class_histogram
```

The histogram gives object counts and shallow bytes by class. It helps spot unusually growing object types, yet **does not reveal why objects remain reachable**. Some `jcmd` GC commands can pause the application or trigger costly GC; check `jcmd <pid> help <command>` on the exact running JDK before using in production. Passing `-all` on related commands may include unreachable objects, changing the meaning of the results.

You can record Java Flight Recorder over an observation window:

```bash
jcmd <pid> JFR.start name=heap-check settings=profile duration=120s filename=heap-check.jfr
```

JFR provides timelines for allocations, GC, and JVM events enabled by the recording configuration; verify which events are actually present in the file. JFR is very helpful for locating where allocations occur and when pressure rises, though **an allocation stack trace does not by itself prove where a reference is being retained**.

### 5.3. Heap dump: finding the retention path

Once you have evidence of unexpected live-set growth and can afford the snapshot cost:

```bash
jcmd <pid> GC.heap_dump heap.hprof
```

Heap dumps can be large, cause pauses/disk pressure, and contain sensitive data; capture only in approved windows, and store/delete according to policy. The default dump command may request a Full GC, so do not treat "before/after dump" as a zero-impact experiment.

Open `heap.hprof` in Eclipse Memory Analyzer (MAT) or an equivalent tool and follow this sequence:

1. Check the **histogram**: which classes show growing instance counts/shallow size across snapshots taken under identical conditions?
2. Check the **dominator tree** and **retained size**: which owner holds an entire object graph? Retained size estimates how much memory could become reclaimable if that owner were removed from the analyzed reference graph; this differs from the owner's own shallow size.
3. For suspect objects, inspect **Path to GC Roots**, noting whether weak/soft references are involved when interpreting. Look for `static field`s, threads/`ThreadLocal`s, singleton caches, listeners, queues, or class loaders holding them.
4. Match the owner against business logic: does this object still belong to a valid session/task/cache entry, or has its true lifecycle ended?
5. Find both the creation site **and** where the reference should have been cleared in code. Fix the cleanup policy at the proper lifecycle boundary; repeat measurements to prove live set/entry counts stabilize.

If you only see lots of `byte[]`, `String`, or `HashMap$Node`, do not rush to modify those classes: they are usually **payloads**, not owners. Trace up to the dominator owner and GC roots path. A single heap dump rarely proves a leak *trend*; comparative histograms or multiple snapshots under equivalent load provide stronger proof.

## 6. Investigation workflow and deciding on action

### Step 1 — Isolate the right memory type

Compare heap used, committed/max, RSS, metaspace, direct buffers, and thread stacks. If only RSS rises while heap used/live set remain flat, open a **native/off-heap memory** investigation branch; raising `-Xmx` or hunting for Java object leaks may head in the wrong direction.

### Step 2 — Form falsifiable hypotheses

For example:
- H1: "Heap grows because concurrent requests rose; once queues drain, the live set returns to baseline."
- H2: "Heap grows because a legitimate cache is warming up to its 5,000-entry cap and then plateaus."
- H3: "Each request attaches a payload to a singleton without removing it; post-GC live payloads grow with total requests."

Every hypothesis must specify metrics and a verification test; do not write "suspected leak" as a final conclusion.

### Step 3 — Hold confounding variables constant

Record exact JDK/GC, `-Xms/-Xmx`, build version, traffic pattern, payload size, unique-key cardinality, cache TTL, thread count, and warm-up duration. Increase **one** factor, observe long enough, then lower it. Compare results after the same GC phase type and after work has finished.

### Step 4 — Plot behavior alongside owner counts

If the live set climbs, plot cache entry counts, queue depth, session counts, and expiration/eviction rates simultaneously. A curve rising in lockstep with valid entries supports justified retention; climbing while entries expire or queues sit empty signals a need to trace reference paths.

### Step 5 — Pick the deep-dive tool for the question

- **Too much allocation?** Use JFR allocation profiling, GC logs, and profilers to locate object creation sites and cut churn.
- **Don't know which objects hold the heap?** Heap histogram/dump, dominator tree, GC roots.
- **Cache works functionally yet memory never plateaus?** Check max size, TTL, key cardinality, byte weights, eviction, and load policy.
- **Heap is flat yet process keeps growing?** Measure native/off-heap/mapped memory and thread stacks.

### Step 6 — Fix the right mechanism

| Verified conclusion | Targeted fix | Confirmation criteria |
| --- | --- | --- |
| Burst/concurrency temporarily exceeds budget | Cap peak in-flight work, stream/chunk, add backpressure, reduce allocations, resize after load testing | Throughput/latency meet SLO, heap returns to expected baseline, no OOME |
| Legitimate cache/session/index needs capacity limits | Max entries/weight, TTL, eviction, session limits, state sizing | Plateau demonstrated under high cardinality; hit rate and correctness preserved |
| Owner retains expired objects | Lifecycle-bound `remove`, unregister listeners, `ThreadLocal.remove()` in `finally`, cancel/close resources properly, avoid unbounded queues | Expired objects do not accumulate; owner path disappears; live set stops climbing across cycles |

### Step 7 — Verify by rerunning the original test

Run the same load, duration, and counters, comparing before/after-fix baselines. Ensure you have not broken sessions, caches, data correctness, or throughput. **Raising `-Xmx` only adds buffer room**: it can be valid for a true working set, yet never eliminates unbounded retention. Forcing `System.gc()` or relying on periodic restarts can mask symptoms, not replace fixing reference lifecycles.

## 7. Easily confused cases

**Case A — "Heap grows with RPS; so it must be normal?"** Not necessarily. If concurrency and queues pile up due to slow downstream dependencies, tasks holding payloads can accumulate even when RPS stops rising. Measure queue age/depth and task completion time too. Backlog-driven growth can still cause OOME without being a post-task reference leak.

**Case B — "The cache is designed to store data, so why call it a leak?"** Because having a valid purpose is not enough: if a cache sees ever-new keys with no entry/byte cap, retention becomes unbounded. That is a lifecycle/capacity policy bug; add max size/TTL/eviction and evaluate hit rate.

**Case C — "After clearing the map, RSS did not drop; did cleanup fail?"** Too early to conclude. Objects may not have been GC'd yet, another owner may remain, or the JVM may have freed the objects while keeping committed pages. Inspect object counts and GC root paths, distinguishing `used` from `committed`/RSS.

**Case D — "GC runs continuously, so there must be a leak?"** Frequent GC also appears in applications with high allocation rates and a stable live set. Check allocation rate, GC CPU, pauses, and post-GC baseline. A leak typically enlarges the live set, yet is not the sole source of GC pressure.

**Case E — "The histogram shows tons of String/byte[]; should we optimize those?"** They may just be cache values, HTTP bodies in queues, or parsed results. Inspect dominators and Path to GC Roots to find the owner instead of guessing the culprit from class names.

**Case F — "If we use WeakReference/SoftReference, are we safe?"** Weak/soft references have their own collection policies and do not replace owner lifecycles or memory bounds; if another strong reference path exists, the object stays reachable. In particular, avoid treating `SoftReference` as an eviction policy with predictable capacity.

## 8. Investigation conclusion checklist

Before writing "heap growth from load", "legitimate retention", or "leak", answer all of these:

- **What is being measured?** `used`, post-GC, `committed`, or RSS? Do you know the collector, heap max, and GC type?
- **What is the workload?** RPS, concurrent requests, queues, batches, unique keys, and session/cache entry counts at each checkpoint?
- **Does growth persist?** After warm-up, load drop, queue drain, TTL expiration, and equivalent GC cycles, does the live set return, plateau, or keep climbing?
- **Who holds the objects?** Owner, reference type, path to GC roots, business expiration point, and cleanup policy?
- **Fix verification evidence?** Repeated run under identical workload, object counts/retained size, GC/latency, and business behavior after the change?

**Decision principle:** call it unintended reference retention only after proving that data whose lifecycle has ended remains reachable. Heap growth by itself is only a symptom; load correlation, post-appropriate-GC live set, and owner graphs are what separate the three mechanisms.
