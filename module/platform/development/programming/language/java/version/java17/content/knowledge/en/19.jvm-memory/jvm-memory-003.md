# G1 with Heap Regions and Latency Goals in Java 17

## 1. What is G1 and why is the heap divided into regions?

**G1 (Garbage-First Garbage Collector)** is a *region-based collector* in the HotSpot JVM. Instead of treating the heap as one contiguous Young space and one contiguous Old space, G1 divides the heap into many **equal-sized regions**. Each region can serve a different role during the garbage collection lifecycle.

This design lets G1 select a subset of regions to collect during each application pause (*GC pause*). The collector prioritizes regions with the most reclaimable space, helping it work toward the pause-time target set by the application.

On server-class configurations, G1 is the default garbage collector in Java 17. You can also specify it explicitly with:

~~~text
java -XX:+UseG1GC -jar app.jar
~~~

G1 aims for a balance between *throughput* and pause duration (*latency*). It suits many server applications with large heaps that need relatively controllable pause intervals. However, G1 is **not a hard real-time collector**: an individual pause can still exceed the configured target.

In this lesson, we focus on the region model, Young/Old/Humongous roles, how G1 collects, and latency goals using options still current in Java 17.

## 2. G1's region model

### 2.1. The heap is a set of regions

G1 splits the Java heap into many equal-sized regions. The region size is chosen by the JVM at startup based on heap size; typically it is a power of 2 between 1 MB and 32 MB, aiming for roughly a few thousand regions across the heap.

Illustrative example with a 4 GB heap and 2 MB regions:

~~~text
Java Heap (illustrative)
+------------------------------------------------------+
| R0 | R1 | R2 | R3 | R4 | R5 | R6 | R7 | ...          |
+------------------------------------------------------+
  Each cell is an equal-sized region

At a given moment, a region may hold the role:
  Eden | Survivor | Old | Humongous | Free
~~~

The number and roles of regions in the diagram are for conceptual explanation only; the JVM manages them dynamically at runtime.

A region is not permanently tied to Young or Old. After live objects are evacuated out of a region, the source region can become a free region and be reused for another role.

### 2.2. Region size is chosen at startup

G1 selects the region size based on maximum heap size. The goal is to balance:

- **Smaller regions:** finer granularity when choosing the collection set, at the cost of managing more regions and metadata.
- **Larger regions:** fewer regions to track, but each region consumes more space; a large object can leave significant unused space in its final region.

You can view the actual region size via GC startup logs:

~~~text
-Xlog:gc+heap=info
~~~

Or set it explicitly with:

~~~text
-XX:G1HeapRegionSize=4m
~~~

This option requires a valid value per G1 rules, typically a power of 2 between 1 MB and 32 MB. The region size is fixed for the heap during that JVM run; it does not continuously resize while the application runs.

Do not change region size merely to reduce Humongous Object counts. Increasing region size also alters collection set granularity and potential wasted space. Measure before tuning.

### 2.3. Region roles change across GC cycles

G1 uses these primary roles:

| Role | Meaning |
|---|---|
| **Eden** | Regions that receive most newly allocated objects in the Young Generation. |
| **Survivor** | Regions holding objects that survived one or more Young GCs. |
| **Old** | Regions holding objects promoted or allocated directly into the Old Generation. |
| **Humongous** | Regions dedicated to large objects meeting G1's size threshold. |
| **Free** | Regions containing no live objects and available to be allocated to any role. |

Eden and Survivor are not two fixed contiguous spaces as in simplified descriptions of some other collectors. They are roles assigned to regions within the heap.

## 3. Young, Survivor, and Old in G1

G1 is still a generational collector: it exploits the observation that many objects have short lifetimes. However, generations are composed of regions rather than fixed address ranges.

### 3.1. Young Generation

New objects are normally allocated in Eden regions. When Eden regions fill up or appropriate collection conditions occur, G1 performs a **Young GC pause**:

1. Pause application threads for a period (*stop-the-world pause*).
2. Identify live objects in the regions belonging to the collection set.
3. Copy live objects to Survivor regions or appropriate Old regions.
4. Reclaim the source regions after evacuation succeeds.

Simplified diagram:

~~~text
Before Young GC
+------------------+------------------+------------------+
| Eden R1          | Eden R2          | Survivor R3      |
| new objects      | new objects      | surviving objs   |
+------------------+------------------+------------------+

              Young GC (pause)
                     |
                     v

After evacuation
+------------------+------------------+------------------+
| Free region      | Free region      | Survivor / Old   |
| reclaimed        | reclaimed        | live objects     |
+------------------+------------------+------------------+
~~~

This illustration is simplified; in practice, live objects may be copied into multiple target regions and source regions are freed once safe.

### 3.2. Survivor and promotion

Objects surviving a Young GC can be moved into Survivor regions. When objects continue to survive or meet age/Survivor-capacity criteria, they can be **promoted** to the Old Generation.

Do not view object age as the sole condition governing promotion. G1 also accounts for object size, Survivor capacity, and overall heap state.

### 3.3. Old Generation

Old regions hold longer-lived objects. G1 does not necessarily collect the entire Old Generation on every pause. After a concurrent marking cycle, it can select a subset of Old regions rich in garbage to collect alongside Young regions in a **Mixed GC**.

This is the essence of the name Garbage-First: G1 prioritizes regions offering the most reclaimable space relative to collection cost, within the pause target budget.

## 4. Humongous Objects and Humongous Regions

An object is considered **humongous** when its size is at least half of a region size.

For example, if the region size is 4 MB:

- Objects smaller than 2 MB do not fall into the humongous category based on this threshold alone.
- Objects 2 MB or larger are handled through the humongous mechanism.

G1 allocates a humongous object directly into one or more contiguous regions. Those regions are marked as Humongous regions; the trailing portion of the allocation may go unused if the object size is not a multiple of the region size.

~~~text
Region size = 4 MB
Humongous object = 9 MB (illustrative)

+----------+----------+----------+
| Region A | Region B | Region C |
| 4 MB     | 4 MB     | 1 MB used|
| object   | object   | + unused |
|          |          | space    |
+----------+----------+----------+
~~~

Humongous allocation has several consequences:

- It may require multiple contiguous regions.
- Remainder space in the last region can be wasted.
- Very large objects can increase allocation pressure and affect marking/collection cycles.
- G1 has mechanisms to reclaim unreferenced humongous objects, but continuous allocation of very large objects still warrants monitoring.

If an application frequently creates large byte arrays, images, buffers, or payloads, review the data design: streaming, chunking, buffer reuse, or avoiding redundant copies can reduce heap pressure.

Do not raise `G1HeapRegionSize` just to push the humongous threshold higher without measuring. Larger regions can reduce humongous object counts, but they also change how G1 selects regions and can increase waste in other allocations.

## 5. Remembered Sets and cross-region references

Because objects are distributed across many regions, G1 needs to know whether a region is referenced from outside. Having to scan the entire heap for incoming references into the collection set on every pause would inflate pause times.

G1 maintains a **Remembered Set (RSet)** per region to record incoming references from other regions. This mechanism works alongside a card table and write barriers:

1. When the application writes an object reference into a field, a write barrier records the relevant memory area.
2. Card information is processed/refined to update the corresponding remembered sets.
3. When a region is in the collection set, G1 can consult its remembered set to find incoming references from other areas without scanning the whole heap.

~~~text
Region A                         Region B
+------------------+             +------------------+
| object X         | --reference->| object Y         |
| field -> Y       |             |                  |
+------------------+             +------------------+
        |                                 ^
        | write barrier / card tracking   |
        +------ B's remembered set -------+
~~~

Remembered sets allow G1 to collect subsets of regions. However, a high volume of cross-region references can increase RSet maintenance cost and root-scanning cost during pauses. Therefore, pause duration depends not only on bytes of garbage reclaimed; it is also influenced by the object graph and cross-region reference density.

## 6. Collection Set and how G1 chooses regions

The **Collection Set (CSet)** is the set of regions selected for collection in a GC pause. G1 evacuates live objects out of these regions.

A CSet can include:

- Eden and Survivor regions during a Young GC.
- Young regions plus selected Old regions during a Mixed GC.

G1 tracks live object volume and estimated collection cost per region. When selecting Old regions for a Mixed GC, it favors regions with high reclaimable space that fit within the pause budget.

~~~text
Heap regions
+------+------+------+------+------+------+------+
| Eden | Eden | Old  | Old  | Old  | Free | Old  |
+------+------+------+------+------+------+------+
           \       \      /
            \       \    /
             +-------------+
             | Collection  |
             | Set (CSet)  |
             +-------------+
                    |
                    v
          Evacuate live objects
          Reclaim source regions
~~~

Not all Old regions are selected in a single Mixed GC. Incremental selection lets G1 split Old Generation collection across several smaller pauses instead of forcing the application to wait for a full Old collection at once.

## 7. Major phases of G1

G1 has two major pause groups:

- **Young-only phase:** collects the Young Generation.
- **Space-reclamation phase:** after Old Generation marking, collects Young regions together with selected Old regions; pauses in this phase are commonly called Mixed GCs.

General cycle:

~~~text
Young-only collections
        |
        | Old occupancy / IHOP threshold
        v
Concurrent marking cycle
        |
        +--> Initial Mark (piggybacked on a Young GC pause)
        |
        +--> Root Region Scan
        |
        +--> Concurrent Mark
        |
        +--> Remark (STW)
        |
        +--> Cleanup (has STW portion)
        |
        v
Mixed collections
        |
        v
Return to Young-only collections
~~~

Phase names and log details can vary by version and GC path; the diagram illustrates the conceptual flow in Java 17 G1.

### 7.1. Initial Mark

Initial Mark identifies GC roots and the starting state for marking. In G1, this work is piggybacked onto a Young GC pause, so it does not necessarily add a standalone pause.

### 7.2. Root Region Scan

G1 scans relevant root regions, particularly Survivor regions, to locate references leading into the object graph to be marked. This runs concurrently with the application but must finish before subsequent Young GCs per the collector's protocol.

### 7.3. Concurrent Mark

G1 marks live objects in the Old Generation while the application continues running. G1 uses **Snapshot-At-The-Beginning (SATB)** to preserve correctness for the object set considered live when marking began.

Concurrent does not mean zero resource cost: marking still consumes CPU and memory bandwidth, which can affect application throughput.

### 7.4. Remark

Remark is a short stop-the-world pause to finish marking, process necessary SATB reference updates, and finalize the live object set.

### 7.5. Cleanup

Cleanup completes post-marking bookkeeping, updates region information, and prepares candidates for Mixed GC. Completely empty regions can be reclaimed immediately in this phase.

### 7.6. Mixed GC

Once liveness information for Old regions is available, G1 can begin Mixed GC pauses. Each pause collects Young regions along with a subset of Old regions. G1 keeps selecting suitable regions according to the pause goal and remaining work.

When reclaimable Old regions have been processed or space-reclamation exit conditions are met, G1 returns to the Young-only cycle.

## 8. Latency goal: MaxGCPauseMillis

G1 lets the application specify a desired maximum pause duration target using:

~~~text
-XX:MaxGCPauseMillis=200
~~~

In Java 17, the default is typically 200 milliseconds. This is a **soft goal**, not a guarantee that every GC pause finishes within 200 ms.

G1 uses this target to adjust the work done in each pause, for example:

- Sizing the Young Generation.
- Estimating how many regions can be collected in one pause.
- Selecting the Old region subset for Mixed GC.
- Balancing required collection work against the pause budget.

If an application sets a lower goal, G1 tends to shrink the work per pause and may increase pause frequency. That can raise overall GC overhead and reduce throughput.

If the goal is set too high, each pause may process more regions, causing the application to wait longer during individual collections.

### 8.1. A pause goal is not a hard cap

For example:

~~~text
-XX:MaxGCPauseMillis=50
~~~

does not guarantee every pause is less than or equal to 50 ms. Causes that can make a pause exceed the target include:

- Too many live objects to copy in the collection set.
- Large remembered sets or heavy cross-region references.
- A large number of GC roots to scan.
- Heap allocation pressure leaving too few free regions.
- Work spikes inside a pause not yet captured by the predictive model.
- OS or CPU resource contention.

Treat `MaxGCPauseMillis` as an optimization target for G1, then measure actual pause distributions using GC logs and metrics.

### 8.2. Latency and throughput trade-offs

| Change | Possible impact |
|---|---|
| Lower pause goal | Individual pauses may be shorter, but GC may run more often and reduce throughput. |
| Raise pause goal | G1 can collect more regions per pause, improving collection efficiency, though pauses may lengthen. |
| Increase heap appropriately | Provides extra room for allocation and GC operation; also increases memory footprint and may lengthen certain phases. |
| Reduce allocation rate | Reduces pressure on Eden and Young GC frequency. |
| Reduce live object volume | Reduces data copied during evacuation and can shorten pauses. |

There is no single right pause target for all applications. Start from your service's actual latency objective, measure p95/p99 request latency and pause durations, and adjust in a controlled manner.

## 9. Common G1 options in Java 17

The options below are current options for configuring or observing G1 in Java 17.

| Option | Purpose |
|---|---|
| `-XX:+UseG1GC` | Select G1 explicitly. |
| `-Xms<size>` | Initial/minimum heap size. |
| `-Xmx<size>` | Maximum heap limit. |
| `-XX:MaxGCPauseMillis=<ms>` | Soft pause-time goal for G1. |
| `-XX:G1HeapRegionSize=<size>` | Set region size when backed by specific measurements. |
| `-XX:InitiatingHeapOccupancyPercent=<percent>` | Initial occupancy threshold to trigger concurrent marking when adaptive IHOP is not used. |
| `-XX:+UseAdaptiveIHOP` | Allow G1 to dynamically adjust the marking initiation threshold based on application behavior. |
| `-XX:G1ReservePercent=<percent>` | Reserve a portion of the heap to reduce the risk of running out of space during evacuation. |

You do not need to set all these flags up front. G1 uses ergonomics to tune many parameters automatically; change an option only when logs or benchmarks point to a specific issue.

### 9.1. Heap size

Example configuration:

~~~text
java -Xms2g -Xmx2g -XX:+UseG1GC -jar app.jar
~~~

Setting `-Xms` and `-Xmx` equal can avoid certain heap expand/shrink cycles, while reserving more memory upfront. Choose heap size based on container/host limits, application needs, and remaining memory required for metaspace, thread stacks, direct buffers, code cache, and native memory.

`-Xmx` limits only the Java heap, not the total process RSS.

### 9.2. InitiatingHeapOccupancyPercent and Adaptive IHOP

G1 must start concurrent marking early enough to reclaim Old regions before the heap runs short of free regions. The occupancy threshold relates to when marking cycles begin.

`-XX:InitiatingHeapOccupancyPercent` provides the initial/fixed threshold value depending on configuration. With Adaptive IHOP, G1 uses allocation rate and marking duration data to adjust when cycles start.

Do not lower the threshold arbitrarily: marking too early can increase concurrent CPU work; marking too late can leave G1 with too little time before the Old Generation faces heavy pressure. Inspect concurrent cycle logs and heap state before modifying it.

### 9.3. G1ReservePercent

G1 needs free regions to copy live objects into during evacuation. `-XX:G1ReservePercent` sets aside a percentage of the heap as reserve space to reduce the risk of running out of target regions.

Increasing the reserve can lower evacuation failure risk in some workloads, but it also shrinks the heap space available for normal allocation. It is no substitute for sizing the heap adequately or reducing allocation/live set.

## 10. Things not to force when using G1

G1 relies on dynamically sizing the Young Generation to balance against the pause target. Therefore, avoid applying fixed generation settings out of habit from older collectors without understanding their impact.

For example, avoid setting `-Xmn` or forcing Young Generation ratios with options like `NewRatio` in a typical G1 configuration. Fixing the Young size restricts G1's ability to adjust how many regions it collects to meet the pause goal.

Also:

- Do not change multiple GC flags at once based on a single long pause.
- Do not expand the heap indefinitely when live set or allocation rate is the root cause.
- Do not use `System.gc()` as a way to control G1 in business logic.
- Do not treat flag tuning as a substitute for reducing unnecessary object allocation.
- Do not use deprecated collectors/flags from outdated documentation as guidance for Java 17.

If a flag is missing from Java 17 documentation or unsupported on your target build/runtime, verify it before deploying to production. Internal HotSpot options can change across releases.

## 11. Observing G1 with Unified JVM Logging

Java 17 uses Unified Logging for GC logs. A common way is to enable logging at launch:

~~~text
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

You can limit log file size and rotation count:

~~~text
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Useful logging tags:

| Configuration | Contents |
|---|---|
| `-Xlog:gc` | General GC overview. |
| `-Xlog:gc+heap=info` | Heap and region information at info level. |
| `-Xlog:gc+phases=debug` | Details of phases within pauses/cycles. |
| `-Xlog:safepoint` | Safepoint information and associated stop times. |

Sample log output may contain lines like:

~~~text
[...][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) 512M->180M(2G) 18.4ms
[...][info][gc] GC(18) Pause Young (Mixed) (G1 Evacuation Pause) 640M->260M(2G) 32.1ms
~~~

These numbers illustrate how to read the log:

- `512M` is the heap occupancy before GC in the sample line.
- `180M` is the heap occupancy after GC.
- `(2G)` is the heap capacity shown in the log.
- `18.4ms` or `32.1ms` is the pause duration.
- `Pause Young (Mixed)` indicates the pause collected Young together with selected Old regions.

Exact log formatting can vary by build and logging setup; analyze actual logs from your JDK 17 runtime.

### 11.1. Questions to answer when reading GC logs

1. Was a long pause Young, Mixed, Remark, or another pause type?
2. How much did the heap shrink after each pause?
3. Did Young GC frequency spike unexpectedly?
4. Did concurrent marking start early enough?
5. Are there many Humongous allocations?
6. Are there signs of evacuation failure or Full GC?
7. Was a long pause caused by copying live objects, scanning remembered sets, root processing, or another phase?
8. Is concurrent GC consuming enough CPU to affect throughput?

Do not judge from a single pause line. Observe over a sufficiently long window and correlate with allocation rate, request latency, CPU, heap occupancy, and application traffic.

## 12. Full GC and Evacuation Failure

G1 strives to collect the heap incrementally by region to avoid overly long whole-heap pauses. However, when free regions run out or evacuation cannot complete as planned, the JVM may fall back to a costlier recovery path.

### 12.1. Evacuation Failure

Evacuation failure happens when G1 lacks enough destination regions to copy live objects out of the collection set. It signals heavy heap pressure or insufficient reserve/free regions for the amount of data being moved.

Consequences can include:

- Longer-than-expected pauses.
- Some regions not being reclaimed as planned.
- Higher risk of triggering a Full GC if the JVM cannot continue normal collections.

Investigation steps:

- Check whether the live set is growing abnormally.
- Check whether the heap has enough headroom for the allocation rate.
- Check the survival ratio of objects in Young/Old collection sets.
- Check Humongous allocations.
- Check whether concurrent marking starts early enough.
- Evaluate whether `G1ReservePercent` needs adjustment after understanding the root cause.

### 12.2. Full GC

A G1 Full GC is something to avoid in latency-sensitive applications because it typically causes a long stop-the-world pause. It can happen when G1 cannot collect/evacuate normally or when the application triggers a global GC through a corresponding mechanism.

When you see a Full GC in the log:

1. Identify the cause immediately preceding the Full GC.
2. Inspect heap before and after the Full GC, especially remaining live data.
3. Check allocation rate and large object sizes.
4. Check for reference leaks or unbounded caches.
5. Check concurrent marking timing and free regions.
6. Change flags only after forming a hypothesis and having a way to measure confirmation.

If a Full GC frees very little heap, the live set may be occupying most of the heap or the application is holding onto objects longer than intended. Increasing the heap can postpone the problem, but it cannot fix a memory leak.

## 13. Workflow for tuning G1 toward latency goals

A practical workflow starts with measurement rather than copying a template of flags.

### Step 1 — Define the application SLO

Determine target request latency, such as p95/p99, and the pause range the system can tolerate. GC pauses are one component of request latency, not total latency.

### Step 2 — Record the current configuration

Capture:

- Specific JDK vendor and Java 17 version.
- Heap `-Xms`/`-Xmx`.
- Actual collector reported in GC startup logs.
- Enabled GC flags.
- Container memory and CPU limits.

### Step 3 — Enable GC logging

Use Unified Logging with file rotation to capture pauses, heap occupancy, phases, and safepoints under realistic load.

### Step 4 — Categorize the cause

Distinguish between:

- High allocation rate causing frequent Young GCs.
- Large live set making evacuation copy many objects.
- Concurrent marking starting too late.
- Humongous allocations pressuring regions.
- Remembered set or root scanning lengthening pauses.
- CPU contention slowing down both GC and the application.

### Step 5 — Change one factor at a time

You may test adjusting:

- Heap size within machine/container memory limits.
- `MaxGCPauseMillis` based on the latency objective.
- `G1ReservePercent` when there is evidence of insufficient evacuation headroom.
- IHOP/adaptive marking when concurrent cycles start at unsuitable times.
- Region size only when backed by humongous allocation data and trade-off analysis.
- Application code to reduce allocations or shorten reference retention.

### Step 6 — Re-measure with the same workload

Compare:

- p50/p95/p99 GC pauses.
- p95/p99 request latency.
- Throughput.
- CPU time spent on GC.
- Allocation rate.
- Post-GC heap occupancy and live set.
- Full GC / evacuation failure counts.

Keep a change only when it improves the overall goal without causing significant regressions in other metrics.

## 14. Basic G1 configuration example for a Java 17 application

A simple starting configuration:

~~~text
java \
  -Xms2g \
  -Xmx2g \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
~~~

This is an illustrative configuration for observing G1, not a universally optimal setup. Choose heap size according to real limits and pause target according to your SLO. If Java 17 on server-class already defaults to G1, `-XX:+UseG1GC` may be unnecessary, though writing it explicitly improves readability across environments.

Do not add `-Xmn`, `NewRatio`, or fixed Young Generation bounds to an initial configuration without clear measurement evidence; letting G1 size generations itself generally helps it pursue the pause target better.

## 15. Practice exercises

### Exercise 1 — Observe region size

Run a Java program with a small heap and enable `-Xlog:gc+heap=info`. Find the region size info in the log. Try running with a larger heap and compare how the JVM picks the region size.

### Exercise 2 — Observe Young GC

Write a loop that allocates many temporary objects, retains a small fraction, and observe Young GCs. Record pre/post-GC heap and pause times.

### Exercise 3 — Distinguish Young and Mixed GC

Run a workload that retains some long-lived objects. Inspect the logs after concurrent marking to find Mixed GCs. Explain why Mixed GC can collect both Young and selected Old regions.

### Exercise 4 — Humongous allocation

Try allocating byte arrays near or above half a region size. Inspect allocation/heap logs. Experiment with changing object sizes and explain why large objects are allocated via the humongous path.

### Exercise 5 — Test pause targets

Run the same workload twice with `-XX:MaxGCPauseMillis=100` and `-XX:MaxGCPauseMillis=300`. Compare pause duration, GC count, and throughput. Do not conclude from a single run; repeat with representative data.

### Exercise 6 — Read a Full GC

Find a log with a Full GC or create a workload that stresses the heap. Identify pre/post live set, allocation rate, humongous regions, and any signs of evacuation failure.

## 16. Key principles to remember

- G1 divides the heap into equal-sized regions; region size is selected at JVM startup and remains fixed for that run.
- Regions can assume Eden, Survivor, Old, Humongous, or Free roles; roles change as objects are moved and regions are reclaimed.
- Young GC copies live objects to target regions and frees source regions; Mixed GC collects Young along with selected Old regions.
- A humongous object is at least half a region size and requires one or more contiguous regions.
- Remembered Sets help G1 find incoming references to collected regions without scanning the entire heap.
- Concurrent marking identifies live objects in the Old Generation; G1 then picks suitable Old regions for Mixed GC.
- `-XX:MaxGCPauseMillis` is a soft goal, not a hard guarantee on maximum pause duration.
- Lowering the pause target can increase GC frequency and reduce throughput; balance it against your SLO.
- G1 dynamically sizes the Young Generation; avoid fixing Young size unless measurements prove a benefit.
- Use Unified Logging to observe pauses, phases, heap, and safepoints before tuning.
- Full GC and evacuation failure signal the need to investigate live set, allocation rate, free regions, humongous objects, and marking timing.
- There is no single optimal GC flag set for every application; change one factor at a time and benchmark with a realistic workload.

### References

- [Oracle Java 17 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector.html).
- [Oracle Java 17 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/).
- [Java SE 17 HotSpot VM Options — G1 Options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248).
