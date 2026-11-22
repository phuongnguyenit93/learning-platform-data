# Allocation Rate, Live Data Volume, and Headroom Needed for GC

A Java application can create **very many objects per second** and still run stably if they die quickly and GC can reclaim them; conversely, an application that allocates relatively little can still encounter `OutOfMemoryError` if most objects are **kept alive long-term**. A third phenomenon is that the Java heap may still look “plentiful” in terms of total bytes, yet the collector **no longer has enough suitable free space to move live objects** during a collection.

These three variables must be read separately:

1. **Allocation rate**: how many bytes/objects per second the application creates on the heap.
2. **Live set / retained live data**: how many bytes must actually be preserved according to reachability at the collection point or after GC.
3. **Free-space headroom / evacuation space**: how much usable free space the collector still has to continue allocating, hold survivors/promoted objects, complete concurrent cycles, or handle load fluctuations.

This article is set in the context of **Java 17, HotSpot, and G1** to explain the practical consequences. Simple formulas are explicitly noted as **estimation models**, not JVMS equalities for every garbage collector. Specific terms such as *to-space exhausted*, *mixed collection*, *reserve percent*, and *adaptive IHOP* belong to HotSpot's G1 strategy, not mandatory rules for every JVM.

## 1. High heap usage can be caused by three different reasons

Suppose two applications both have `-Xmx1g` and report heap used around 700 MiB at a given point in time:

| Characteristic | Application A | Application B |
| --- | --- | --- |
| Allocation rate | 500 MiB/second | 20 MiB/second |
| Objects surviving GC | Few; mostly temporary request data | Many; long-lived caches and sessions |
| After GC | Can drop quickly to 200 MiB | May remain at 670 MiB |
| GC behavior | Frequent young collections | Fewer collections but low reclaimability |
| Investigation direction | Allocation hotspots, object lifetime, throughput | Retention, cache size, GC roots, live-set trend |

The values in the table are **hypothetical scenarios**, not benchmarks. Beyond these two cases, **headroom pressure** can also appear: for example, GC needs to copy 180 MiB of surviving objects to a destination area but cannot find enough suitable destination regions, even though a dashboard displays some number of “free” bytes in aggregate.

**Key takeaway:** do not diagnose “GC is slow because heap used is high” without knowing **how fast allocation is happening**, **which objects are still alive**, and **how much effective headroom GC has left to work with**.

## 2. Exact definitions of commonly seen metrics

| Metric | Common units | Meaning |
| --- | --- | --- |
| Allocation rate | MiB/s, GiB/s, objects/s | Amount of new data allocated over a time interval |
| Young allocation rate | MiB/s | Portion of allocations accounted for by the collector in the young region; scope may differ from total heap allocations |
| Live set | MiB/GiB | Objects that must be kept alive at a specific GC phase/snapshot |
| Post-GC occupancy | MiB/GiB | Heap used after a collection; does not default to the live set of the entire heap |
| Survival rate | % | Percentage of live bytes in the set of objects/regions being collected |
| Promotion rate | MiB/s or MiB/GC | Amount of objects/bytes moved to old regions/generation |
| Heap used | Bytes | JVM metric for heap capacity currently recorded as in use |
| Heap committed | Bytes | Heap committed for available use |
| Heap max | Bytes | Maximum usable limit; usually related to `-Xmx` on HotSpot |
| Free within committed | Bytes | `committed - used` in a snapshot of the same scope |
| Uncommitted capacity | Bytes | The difference between max and committed, when max is finite; not guaranteed to expand immediately |
| G1 to-space/headroom | Regions/bytes | Actual destination capacity serving evacuation/promotion under G1 policy |
| GC pause duration | ms | Application pause duration during specific STW phases |
| GC overhead | % CPU or % wall time, depending on source | Share of resources/time spent on GC; the definition must be stated explicitly |

The two measurements **used** and **committed** of `MemoryUsage` have the relationship `used <= committed`; if `max` is finite then `committed <= max`. However, one must not take `max - used` and assume all of it is **immediately usable G1 to-space**, because heap regions, evacuation reserves, generation occupancy, humongous objects, fragmentation, and commit policies are all involved.

### Distinguishing “currently used” from “actually live”

Between two GCs, the heap can contain objects that **are no longer reachable** but have not yet been reclaimed by GC. They contribute to used until appropriately collected. Conversely, a young GC may only collect part of the heap; the **post-young-GC heap used** value still contains old objects that have not been re-traced across the full heap in that cycle. Do not arbitrarily call every post-GC heap occupancy the “exact byte-for-byte live bytes of the entire JVM”.

## 3. Allocation rate: how much garbage does the program create per second?

**Allocation rate** reflects new data created by the application on the heap, typically expressed as:

```text
Allocation rate ≈ bytes allocated over interval Δt / Δt

Example unit:
  600 MiB allocated in 3 seconds -> 200 MiB/second
```

This rate is affected by many sources:

- Creating DTOs, request objects, temporary strings, arrays, JSON trees.
- Boxing, intermediate collections, capturing lambdas/closures, stream pipeline materialization.
- Data compression/decompression, serialization, and copies into buffers.
- Batch transformations, sorting, grouping, and intermediate object graphs.
- Logging and formatting with eager construction, even when the output is not actually needed.
- Actual workload: QPS × bytes allocated/request, across multiple request types of different sizes.

**High allocation is not by itself a memory leak.** If objects die quickly, generational GC can reclaim them very efficiently. Even so, excessive allocations still have a cost: Eden pressure, GC frequency, write barriers, TLAB refills, copying survivors, and CPU spent on the runtime.

### Numerical example: allocation rate by request throughput

Suppose (for estimation only):

- Load: **2,000 requests/second**.
- Each request allocates on average **120 KiB** of objects/arrays on the heap.
- Most live no longer than a single request.

Estimate:

```text
2,000 requests/s × 120 KiB/request
= 240,000 KiB/s
≈ 234.375 MiB/s
```

This figure does not include background jobs, GC/internal allocations, and variations by request payload; nor does it say **how much of the 234 MiB/s will survive GC**. Survival/retention must be measured next.

A processing path with the same QPS but half the allocation can reduce young GC pressure, **but is not guaranteed to reduce p99 latency** if the main bottleneck lies in the database/I/O or the live set is still too large. Always measure end-to-end.

## 4. Thread Local Allocation Buffer (TLAB) and the allocation fast path

HotSpot can give each thread a **Thread Local Allocation Buffer (TLAB)** region so that many small allocations happen quickly by bumping a pointer within the buffer. When the buffer runs out of space, the runtime refills it or uses another allocation path.

Implications:

- Allocation is usually **cheaper** than requesting memory from the OS for each object.
- Allocated bytes must still be managed by GC, even when allocated very quickly.
- Allocation statistics via TLAB/outside TLAB have different accounting perspectives; use the same metric source when comparing rates.
- Some objects may undergo JIT **scalar replacement/escape analysis**, so the observed physical allocations do not necessarily equal the number of `new` expressions in source code.
- TLAB is internal to HotSpot; do not treat it as a Java API requiring every JVM to have the same memory layout.

### Why reducing the number of `new` calls is not necessarily the right optimization

A small, short-lived object can be allocated very quickly and then cheaply reclaimed by GC. Replacing it with a **manual object pool** can make the object live longer, increase synchronization contention, retain larger graphs, and **increase the live set**. Prioritize **measuring allocation hotspots and GC pressure** before reusing objects via pooling.

## 5. Live set: what GC cannot simply ignore

**Live set** is the portion of the object graph considered necessary to keep alive at a point in time/snapshot according to the collector's rules. It may include:

- Objects currently used by active requests.
- Cache entries, session data, singleton registries.
- Queued tasks, pending futures, retries, event listeners.
- Long-lived maps, object graphs of database/application state.
- ThreadLocal values held by worker threads.
- Objects still reachable through multiple owners/GC roots.

Live data matters because the collector must:

1. Determine liveness via tracing/marking and metadata.
2. Preserve object fields, references, and identity.
3. When using evacuation/compaction, **copy or move a portion of live bytes** to a destination area.
4. Continue keeping objects that truly belong to the live set, whether the application intended to keep them that long or not.

You cannot “tune GC” to reclaim an object that is still **strongly reachable** and can be validly used by Java code. If the live set grows because an unsubscribed listener is missing or a cache is unbounded, the problem lies in **ownership/lifecycle**, not just GC flags.

### How does a large live set impact pause/CPU?

- **Marking/scanning:** more live objects and reference edges can increase tracing work.
- **Copy/evacuation:** more live bytes in the collection set means more copying, consuming bandwidth and destination regions.
- **Old occupancy:** long-lived objects move to or reside in old regions, making old regions harder to reclaim.
- **Headroom:** live data occupies capacity that could otherwise serve as destination space or a buffer for allocation while concurrent marking runs.
- **Fragmentation/humongous objects:** live data layout can leave the collector without contiguous space or enough regions for a specific allocation request.

**There is no universal “GC pause = live bytes / bandwidth” formula**: besides copying bytes, there are root scanning, reference processing, synchronization among GC workers, card/remembered sets, OS/JIT, and CPU competition.

## 6. Survival rate and copy volume

In a GC processing a collection set, define the model:

```text
CSet occupancy before collection = live bytes + dead bytes
survival rate (model)            = live bytes / occupancy

Suppose:
  occupancy = 400 MiB
  live      = 40 MiB
  dead      = 360 MiB

survival rate = 40 / 400 = 10%
```

If the evacuating collector has to copy nearly 40 MiB (ignoring optimization details/unmoved objects), reclaiming 360 MiB can be quite worthwhile.

Another collection set with 400 MiB occupancy but 360 MiB live:

```text
survival rate = 360 / 400 = 90%
dead = 40 MiB
```

This time GC has to preserve/potentially copy many bytes to reclaim much less. **Same 400 MiB occupancy, yet vastly different GC efficiency**.

### Why not take `heap used before - heap used after` as the exact live set?

- The collection may only process young regions rather than the entire heap.
- Mutators may run between measurement points, especially in concurrent GC.
- Promotion, surviving objects, metadata, and compaction can change the distribution.
- GC logs may report region occupancy/evacuation according to collector-specific definitions.
- Live data in old regions is not necessarily scanned in full on every young GC.

Only use the before–after difference as a **reclaim estimate under stated conditions**, and do not call it the sole actual live object set of the entire heap.

## 7. Promotion rate: why do long-lived objects put pressure on the old generation?

In generational collection, objects that survive one or more young GCs can be **promoted** from young/survivor to old, depending on the collector, age threshold, survivor capacity, and policy conditions.

Model:

```text
Allocation -> Eden
                |
           Young collection
          /              \
     dead/reclaim       live/copy
                          |
                    survivor / age
                          |
                    promote to old
                          |
                  old occupancy increases
```

**Promotion rate** measures the amount of data moved to old over a time interval or per collection. It differs from allocation rate:

- 500 MiB/s allocation may only promote a few MiB/s if most objects die quickly.
- 50 MiB/s allocation may promote significantly if data is retained across many requests.
- A short promotion spike is not necessarily a leak; it could be a batch/cache warm-up.
- Continuously rising promotion together with rising post-collection old occupancy may indicate a need to investigate retained graphs or collector capacity.

### Survivor capacity and premature promotion

If survivor space/regions are insufficient, some objects may be promoted to old earlier than the collector's ideal design age. This causes **old occupancy to rise rapidly**, even though many objects soon die in old. GC must then organize additional marking/mixed collections to reclaim old garbage.

There is no rule that “every object must survive exactly N young GCs before promotion”: age thresholds/regions are dynamic and change with flags/workload.

## 8. Free space, committed, and max are three different layers of limits

A set of Java heap metrics might look like:

```text
Heap max       = 2048 MiB
Heap committed = 1536 MiB
Heap used      = 1200 MiB

In the same snapshot:
  committed - used = 336 MiB
  max - committed  = 512 MiB
  max - used       = 848 MiB
```

However, **848 MiB does not automatically equal “space available for G1 evacuation”**.

- `committed - used` is the unused portion within committed; it may be distributed across regions/segments with different roles.
- `max - committed` is expansion capacity **by metric**, with no guarantee it can be committed immediately due to OS/container physical/native budgets or GC decisions.
- `max - used` is an aggregate difference that does not describe fragmentation, pinned/humongous regions, or reservation policy.
- G1 selects **destination regions/to-space** based on region structure and policy. Enough free regions are needed to copy survivors/promoted objects belonging to the CSet.
- The collector must also maintain **headroom for allocations occurring while concurrent marking or background reclamation has not yet finished**.

### Why can a heap with “free” space still fail to allocate an object?

A collector may not find **contiguous space or the right kind of regions** large enough to hold an object; or it must keep regions as a GC reserve; or it is suffering **to-space exhaustion** while copying live objects. Similarly, the JVM may encounter an allocation failure and attempt GC/heap expansion before throwing OOME.

**Do not equate** “heap used is below max” with “GC is guaranteed to succeed in the next pause”.

## 9. Headroom: the buffer GC needs to keep making progress

**Headroom** is the available or reserved capacity that helps the collector handle situations **while garbage has not yet been reclaimed**. For a relocating collector, it has two major roles:

1. **Mutator allocation headroom:** the application continues creating new objects between collections/during concurrent phases.
2. **Evacuation/relocation headroom:** destination memory is needed for live objects being copied/promoted, before source regions can be safely reclaimed.

A minimal budget model:

```text
Suppose (illustrative):
  H = suitable total heap capacity
  L = occupied live data after collection
  G = new allocation volume to absorb while waiting for GC
  E = destination/to-space requirement + GC reserve
  M = safety margin

To avoid pressure during that interval:
  H must be enough for L + G + E + M
```

**Do not use this as a JVMS necessary-and-sufficient condition.** Terms can overlap across GC phases, part of the source heap is reused, collectors have different policies, and `L`/`G` are not necessarily measured at the same point. The formula is useful for **remembering the categories of demand**, not as an automatic heap size calculator.

### To-space illustration

```text
Before evacuation:
  Region R0 (CSet) [live A B C + dead objects]
  Region R1 (CSet) [live D E + dead objects]
  Region R2 (free)
  Region R3 (free)
  Region R4 (old, outside CSet)

GC copies A,B,C,D,E to R2,R3 (when there is enough space).
Afterward R0,R1 become free and can be reused.

If R2,R3 do not have enough destination space for live data,
reclaiming R0,R1 may not proceed as planned.
```

In cases where source and destination overlap improperly or no suitable free regions remain, the collector must have a fallback plan rather than overwriting live objects.

### G1 and `-XX:G1ReservePercent`

On HotSpot G1, `-XX:G1ReservePercent` is a percentage of the heap **reserved as a false ceiling** to reduce the risk of promotion/evacuation failure. Example configuration depending on purpose:

```bash
java -Xms512m -Xmx2g -XX:+UseG1GC -XX:G1ReservePercent=15 -jar app.jar
```

`app.jar` is an illustrative name; the command is only valid if you have a corresponding application JAR. **Do not understand 15% as a fixed physical RAM area locked away and never used.** This is a **GC policy reserve** within the heap managed by HotSpot; its effect, default, and relationship to adaptive IHOP/young sizing depend on the JDK build.

**Do not adjust reserve in isolation by a mechanical rule.** Increasing reserve can reduce the likelihood of eviction/to-space exhaustion in a workload, but it reduces effective heap capacity available to the application and may require adjusting the total heap budget. GC logs and benchmarks are required.

## 10. G1 Java 17: allocation rate drives young GC cadence

G1 divides the heap into regions, using young/old/survivor regions according to policy. A sequence of operations can be:

1. Application allocation creates objects, mostly into Eden/young regions; there are other cases such as humongous allocations.
2. When a young collection is triggered, G1 selects the collection set, performs root scan/remembered-set processing, and **evacuates live objects** to survivor/old destinations during an STW pause.
3. Source regions are reclaimed; the application resumes allocation.
4. Rising old occupancy/projections cause G1 to start **concurrent marking** to prepare for reclaiming old regions.
5. After marking, **mixed collections** can reclaim selected old regions alongside young collections.

With a high allocation rate, Eden/young capacity can be consumed faster → young GC may occur more frequently. This is a trend, **not a 1:1 formula**: G1 adapts young-generation sizing, pause goals, GC causes, and space availability.

### Relationship between Eden size, allocation rate, and GC cycle

A very rough estimate during a steady workload segment:

```text
Time to fill an equivalent Eden budget
≈ allocatable budget in young / allocation rate

Example:
  usable budget ≈ 240 MiB
  allocation rate ≈ 120 MiB/s
  time ≈ 2 s
```

**This is not an exact Young GC timing prediction.** There are TLABs, humongous allocations, survivor occupancy, young sizing, pretenuring/other allocation paths, and other GC triggers. If actual logs show 0.5 s between young GCs, do not “fudge the numbers” to match the formula; investigate the real cause.

## 11. G1 concurrent marking: must finish before old fills up

One thing G1 needs to avoid: old regions keep growing due to promotion/allocation, while **concurrent marking does not finish early enough** for mixed collections to reclaim old regions that are no longer live.

When preparing old-space reclamation lags behind the rate of occupancy growth:

- Young collections can still occur while concurrent marking is running.
- Old occupancy can continue rising through promotion/humongous allocations.
- Space for evacuation/to-space and new allocations shrinks.
- If marking/reclamation cannot keep up, **evacuation failure/to-space exhausted**, Full GC, and in severe cases OOME can occur.

G1 uses an **Initiating Heap Occupancy Percent (IHOP)** mechanism and can adapt the marking start threshold based on predictions. What matters is **marking early enough for GC to finish and begin reclaiming old regions before running out of headroom**, not simply lowering a flag to a very low value.

### Liveness in G1 Concurrent Marking is not always “right-now” liveness

G1 uses **Snapshot-At-The-Beginning (SATB)** for concurrent marking. An object still live at the start of the snapshot may be treated as live during the marking cycle even if it later ceases to be strongly reachable. Therefore:

- Liveness accounting within a cycle can be **conservative**.
- Some objects that die after the snapshot may only be effectively reclaimed in a later cycle.
- Heap occupancy does not drop immediately when code drops a reference.
- “An object was just dereferenced” does not mean “G1 will immediately return all memory to the allocator”.

This is one reason to compare **trends across multiple cycles**, not just a single number after one marking phase.

## 12. Evacuation failure, to-space exhaustion, and Full GC

According to Java 17 G1 documentation, when a collection keeps so many bytes live that **not enough destination space can be found to copy them**, G1 can experience an evacuation failure. The collector maintains correctness by handling moved and unmoved objects via a fallback mechanism; the GC phase can take extra time.

If the application still lacks enough headroom to continue until old space reclamation succeeds, G1 may have to resort to a **Full GC, in-place compaction**, which is usually more expensive than normal young/mixed collections.

Signs in GC logs depending on the JDK build:

- `to-space exhausted` or evacuation failure indicators.
- `Pause Full (Allocation Failure)` / Full GC variants.
- Old regions rising rapidly, free regions dropping, frequent young/mixed collections.
- Concurrent marking dragging on relative to the rate of old occupancy growth.
- Many humongous regions, fragmentation/region pressure.

**Do not assume that seeing a Full GC means a Java heap leak.** A Full GC can be caused by a large retained live set, allocation spikes, insufficient to-space, concurrent marking falling behind, or humongous allocations; it can also be `System.gc()`/a diagnostic action depending on configuration. Inspect the **GC cause and timeline**.

### Humongous objects create unusual pressure

In G1, objects that are large relative to the region size threshold are handled specially as **humongous objects/regions**. They can occupy multiple contiguous regions and hurt region utilization, not necessarily following the usual young object path.

- Allocating a large array can consume an integer number of regions, while the unused tail does not immediately become general free space.
- Many humongous objects can drive up old occupancy and create region-level fragmentation.
- G1 may need to trigger marking or use special reclamation mechanisms depending on the version.
- Adjusting region size to change the humongous threshold must be based on an **object size histogram and actual GC logs**, not as a default fix.

## 13. A numerical exercise: allocation, live bytes, and destination pressure

Suppose (all numbers are illustrative):

- A collection area contains **300 MiB allocated**.
- Of which **30 MiB is live** and **270 MiB is dead**.
- Before evacuation there is **80 MiB of destination capacity** by assumption.

Here GC may need to copy about 30 MiB, and 80 MiB of destination space **appears sufficient** in the simple model. After evacuation, it can reclaim 300 MiB of source regions and have roughly 50 MiB of hypothetical destination capacity left, ignoring overhead.

If the survival rate increases:

- The collection set is still 300 MiB.
- Live data becomes **250 MiB**.
- Destination capacity is still 80 MiB.

An evacuating collector **cannot copy 250 MiB of live data into only 80 MiB of destination space under that model**. It must change the CSet/policy or fall back; with G1, some form of evacuation failure/to-space exhaustion can occur when headroom is too low.

**Important:** this example is not an exact formula for G1 to-space because the collector can reuse regions, update schedules, mix the CSet, and use other reserves. It illustrates **why live bytes and destination capacity must be considered together**.

### Same data set, different copy demand

```text
Case A:
  CSet occupied  = 300 MiB
  live           = 30 MiB
  dead/reclaim   = 270 MiB
  survival       = 10%

Case B:
  CSet occupied  = 300 MiB
  live           = 250 MiB
  dead/reclaim   = 50 MiB
  survival       ≈ 83.33%
```

The application's allocation rate can even be identical in both cases; the difference in survival creates a completely different level of GC difficulty.

## 14. Java 17 program: computing the model numbers deterministically

Create the file **`GcBudgetMath.java`**:

```java
public class GcBudgetMath {
    private static final long MIB = 1024L * 1024L;

    static long allocatedPerSecond(long requestsPerSecond,
                                   long bytesPerRequest) {
        return requestsPerSecond * bytesPerRequest;
    }

    static long deadBytes(long occupied, long live) {
        if (live < 0 || occupied < live) {
            throw new IllegalArgumentException("invalid liveness");
        }
        return occupied - live;
    }

    public static void main(String[] args) {
        long rateBytes = allocatedPerSecond(1024L, 128L * 1024L);
        long occupied = 300L * MIB;
        long live = 30L * MIB;
        long destination = 80L * MIB;

        System.out.println("rateMiBps=" + rateBytes / MIB);
        System.out.println("occupiedMiB=" + occupied / MIB);
        System.out.println("liveMiB=" + live / MIB);
        System.out.println("deadMiB=" + deadBytes(occupied, live) / MIB);
        System.out.println("survivalPercent=" + live * 100 / occupied);
        System.out.println("destinationEnough=" + (destination >= live));
    }
}
```

```bash
javac --release 17 GcBudgetMath.java
java GcBudgetMath
```

**Exact stdout:**

```text
rateMiBps=128
occupiedMiB=300
liveMiB=30
deadMiB=270
survivalPercent=10
destinationEnough=true
```

Explanation:

- `1024 requests/s × 128 KiB = 128 MiB/s`.
- The 30 MiB live portion out of 300 MiB is 10%, and the dead portion is 270 MiB.
- `destinationEnough=true` **is only a numerical comparison in the model**, not an actual G1 check result. The runtime also has region granularity, collector reserve, object alignment, old occupancy, humongous allocations, and many other states.
- The expression `live * 100 / occupied` is **integer arithmetic** and truncates downward if the percentage is not a whole number. Do not use it in place of measurement precision for real GC metrics.

## 15. Java 17 program: allocation churn does not mean a retention leak

Create the file **`AllocationChurnDemo.java`**:

```java
public class AllocationChurnDemo {
    static volatile Object sink;

    public static void main(String[] args) {
        final int count = 4000;
        final int bytesPerAllocation = 32 * 1024;

        for (int i = 0; i < count; i++) {
            byte[] block = new byte[bytesPerAllocation];
            block[0] = (byte) i;
            sink = block;
        }

        long totalBytes = (long) count * bytesPerAllocation;
        System.out.println("iterations=" + count);
        System.out.println("nominalAllocatedMiB="
                + totalBytes / (1024 * 1024));
        System.out.println("lastBlockLength="
                + ((byte[]) sink).length);
    }
}
```

```bash
javac --release 17 AllocationChurnDemo.java
java AllocationChurnDemo
```

**Stdout of the normal path, when allocation succeeds:**

```text
iterations=4000
nominalAllocatedMiB=125
lastBlockLength=32768
```

In the loop, `sink` only holds the **latest block**; older blocks are no longer reachable through `sink` (barring other special retention paths). Thus the code creates **125 MiB of cumulative nominal array capacity** without retaining 125 MiB of arrays in a normal collection.

**Do not treat 125 MiB as an exact allocation profiler measurement**: object headers, alignment, and runtime optimizations/costs may differ, and the application also allocates many other objects. Making `sink` volatile causes reference publication to happen semantically, but **does not guarantee exactly N GCs** or a fixed allocation optimization.

### Trying with a small heap and GC logs

On HotSpot Java 17:

```bash
java -Xms32m -Xmx64m -XX:+UseG1GC -Xlog:gc AllocationChurnDemo
```

The number of collections, GC IDs, regions, and pauses in the log **are not fixed**; no single stdout is given for the GC lines. The three lines from `System.out.println` in the code remain as above if the program finishes without OOME/resource failure.

## 16. Java 17 program: intentionally retaining a lot of data

Create the file **`RetainedDataDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RetainedDataDemo {
    static final List<byte[]> KEEP = new ArrayList<>();

    public static void main(String[] args) {
        for (int i = 0; i < 8; i++) {
            byte[] block = new byte[1024 * 1024];
            block[0] = 1;
            KEEP.add(block);
        }

        System.out.println("retainedEntries=" + KEEP.size());
        System.out.println("retainedNominalMiB="
                + KEEP.size() * 1024 * 1024 / (1024 * 1024));

        KEEP.clear();
        System.out.println("afterClear=" + KEEP.size());
    }
}
```

```bash
javac --release 17 RetainedDataDemo.java
java RetainedDataDemo
```

**Exact stdout:**

```text
retainedEntries=8
retainedNominalMiB=8
afterClear=0
```

In this case, static `KEEP` holds **8 entries** until `clear()` removes the references. This is a simple retention model; a real cache might hold millions of entries with much larger graphs.

**Do not infer from `afterClear=0` that GC has run or that RSS must drop immediately.** `clear()` only cuts the reference paths from the list; other references may still exist, and GC has its own schedule for doing work.

### High retention is not always a leak

If these 8 MiB are model data that the application needs to reuse throughout its entire lifecycle, keeping them is correct. A problem occurs when retention exceeds the **business lifecycle or memory budget**, such as an unbounded cache, an unregistered listener, or a `ThreadLocal` holding an old request. The way to distinguish is **ownership + lifecycle + post-GC occupancy trend**, not whether an object still exists after a single collection.

## 17. Measuring actual heap with `MemoryMXBean`

The Java Management API provides heap snapshots:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public class HeapSnapshotDemo {
    private static final long MIB = 1024L * 1024L;

    public static void main(String[] args) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();

        System.out.println("usedMiB=" + heap.getUsed() / MIB);
        System.out.println("committedMiB=" + heap.getCommitted() / MIB);
        System.out.println("maxMiB=" +
                (heap.getMax() < 0
                        ? "undefined"
                        : Long.toString(heap.getMax() / MIB)));
    }
}
```

```bash
javac --release 17 HeapSnapshotDemo.java
java -Xms64m -Xmx256m HeapSnapshotDemo
```

**The output has three lines, but the values depend on JVM/OS/timing**; there is no “universal exact stdout” for heap used. `MemoryMXBean` also **does not return allocation rate** directly; it is an occupancy/commit/max snapshot, not a substitute for a profiler or cumulative allocation counters.

To estimate allocation rate by taking the delta of **properly defined allocation counters**, make sure the metric actually **counts allocated bytes**, not just a used heap snapshot that can drop due to GC. **Do not compute `(used2-used1)/seconds` as the allocation rate**: GC and object reclamation can make the difference negative even while the application is allocating rapidly.

## 18. Which tools measure allocation rate, live set, and GC pressure?

| Question | Appropriate observation | What not to use mechanically |
| --- | --- | --- |
| Which method is causing high allocation? | JFR allocation events, allocation profiling (async profiler/YourKit/JMC...) | Looking only at `-Xmx` |
| Allocation rate over time? | JFR/GC logs/counters with clear allocation semantics | `Δ(heap used)/Δt` when GC occurs |
| Are young collections happening frequently? | `-Xlog:gc`, `jstat -gc` with the right collector | Deriving a fixed frequency from source code |
| Are survivors/promotions increasing? | GC logs for Eden/Survivor/Old; collector-specific counters | Calling all survivor bytes old allocation |
| Is the post-GC live set steadily rising? | Occupancy after representative collections; heap dump/histogram | An arbitrary used heap number before GC |
| Why are objects still alive? | Heap dump, dominator tree, paths to GC roots | Blaming `byte[]` just because it has large shallow bytes |
| Does G1 still have to-space/headroom? | GC logs for free regions, evacuation failures, heap/region state | Treating `-Xmx - heapUsed` as exact to-space |
| What caused Full GC/OOME? | GC cause, full GC timeline, object retention, memory limit | Assuming “GC is too weak” |
| Does the container have enough total memory? | Cgroup memory metrics, RSS/PSS, heap + native budget | Treating `-Xmx` as representing the entire process |

**JFR (Java Flight Recorder)** is useful when you need to correlate allocation hotspots with CPU/time and GC events. Recording has runtime overhead, sampling granularity, and event thresholds; an allocation profiling view does not necessarily capture every physical allocation with absolute byte accuracy.

### A simple workflow for measuring a Java 17 service

First, record:

- `java -version`, JVM vendor/build, and the GC in use.
- `-Xms`, `-Xmx`, relevant G1 flags, and container memory limit.
- Actual load: requests/s, concurrency, bytes/request, batch sizes.
- GC logging and metric timestamps aligned to the same PID.
- Post-collection heap occupancy, young/old regions, promotion, pauses, and percent time in GC.

Measure at least three phases: **warm-up**, **steady state**, and **peak/burst**. Do not take a single startup run that has just finished JIT/cache initialization as representative of steady state.

## 19. Java 17 Unified GC Logging: how to read GC cadence

On HotSpot:

```bash
java -Xms256m -Xmx1g -XX:+UseG1GC -Xlog:gc* -jar app.jar
```

To focus on GC phases/heap with build-dependent detail:

```bash
java -Xms256m -Xmx1g -XX:+UseG1GC \
  -Xlog:gc*,gc+heap=info,gc+phases=debug \
  -jar app.jar
```

This is a **sample command for shells that support backslash line continuation**; on Windows PowerShell 5.1 it must be written on one line or use PowerShell's line continuation syntax. `app.jar` is an illustrative name for a real application, not a file pre-created in this article.

In G1 logs, look for:

- **Young GC cadence:** time interval between collections and Eden bytes/regions used.
- **Eden/Survivor/Old regions:** which areas grow/shrink after pauses.
- **Evacuation time:** phases for scanning/merging heap roots, object copying, reference processing (names vary by JDK).
- **Concurrent Start/Remark/Cleanup:** whether marking starts and completes early enough.
- **Mixed GC:** whether old region reclamation occurs and reclaims a significant amount.
- **Humongous regions:** regions held by very large objects, and whether they trend upward.
- **Evacuation Failure / to-space exhausted:** whether the collector ran out of destination memory.
- **Full GC:** reason/cause and pause duration, and how much heap was reclaimed afterward.

**Do not treat a single symptom as the root cause conclusion.** For example, frequent young GCs can be caused by high allocation rate, small young sizing, heap pressure, or collector policy; you also need to check allocation histograms/throughput/live set.

### Using `jcmd` and `jstat` in context

```bash
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jstat -gc <PID> 1000 5
```

`<PID>` is a placeholder for a Java process running long enough. Units/counters of `jstat` can differ by collector, and some fields do not apply. Do not assume that `S0U`/`S1U` or `OU` numbers in modern collectors always correspond to a single contiguous memory block as in the classic Serial GC model.

## 20. How to estimate a memory budget for headroom

Set clear targets:

- How much do peak concurrent requests/batches increase the live working set?
- What is the allocation rate in steady state and at peak burst?
- How does the young survival rate vary across request types?
- What is the old live occupancy after marking/mixed cycles?
- What percentage of the heap needs to be maintained as appropriate GC reserve/evacuation space?
- Does the container still have headroom for **native memory, metaspace, code cache, thread stacks, direct buffers, OS/cgroup accounting**?

Operational budget model (not an exact sum of all metrics):

```text
Space is needed for:
  - steady: live objects still needed by the application
  - variable: allocations while the collector is working
  - relocation: survivors/promotion/to-space
  - uncertainty: spikes, humongous objects, fragmentation, reserve
  - off-heap: native memory + container headroom
```

When `-Xmx` is set very close to the container limit, even if the heap has not hit max, the process can still be OOMKilled due to **native/process total memory**. Increasing the heap to cure to-space pressure may require increasing the container budget, reducing native usage, or adjusting other memory consumers simultaneously.

### Why increasing the heap does not always improve pauses

A larger heap can reduce GC frequency by providing more allocation headroom, but it can increase the amount of memory that certain phases must scan/mark/reclaim, increase the native/physical footprint, and allow garbage to linger longer between cycles. Results depend on the GC and workload; you must measure **throughput, p95/p99 pauses, and footprint** before and after, not just look for “fewer GCs”.

## 21. Optimizing allocation rate: low-risk strategies

First, find hot paths with **high, unnecessary allocation**:

1. Reduce intermediate object creation in serialization/parsing when suitable streaming/buffer APIs already exist.
2. Avoid copying `String`/arrays/collections multiple times if a view or safe immutable reference can be used.
3. In hot-path loops, avoid unintended boxing/unboxing and temporary collections that can be replaced with primitive data structures when proven worthwhile.
4. If logging is disabled, avoid eager formatting/concatenation that causes unnecessary allocations; use appropriate parameterized logging.
5. Limit batch sizes, preferring streaming/backpressure instead of reading all data into RAM.
6. If reusing buffers, clearly define ownership/size limits and avoid keeping oversized buffers for small workloads.
7. Optimize for **allocation bytes/op + CPU + latency + retained heap**, not merely reducing the number of `new` statements in source code.
8. Be cautious with object pooling: holding objects longer increases the live set, fragments memory, or adds contention.

**Principle:** reduce **useless** allocation, not necessarily every short-lived allocation. Young GC is designed to handle many short-lived objects.

## 22. Optimizing live set and avoiding retention leaks

A large live set can be completely legitimate (e.g., model data actively serving users), but if it grows unboundedly over time, check:

- Caches without maximum size/weight/TTL or invalidation.
- Registered listeners/observers that are never unsubscribed.
- `ThreadLocal` holding request context in a worker thread pool due to missing `remove()` in `finally`.
- Unbounded pending tasks/futures/queues/backpressure.
- Static singletons retaining entire session, transaction, or plugin data.
- References from long-lived class loaders/TCCL/JNI handles retaining class metadata/object graphs.
- A heap dump pointing to an object root or retention path with an unusually large retained size.

Do not force `System.gc()` to clear an object that is still strongly reachable. Fix it at the **owner of the reference path** via bounded caching, unsubscribing, canceling/releasing resources, or completing the lifecycle.

### Example distinguishing an allocation spike from retained growth

- **Spike 1:** The service temporarily creates 500 MiB of buffer data while processing a batch and then drops all of it. Heap used may rise quickly, GC then reclaims it, and the live set stays stable.
- **Spike 2:** The service adds a 20 MiB entry per batch into a static cache with no eviction. After 20 batches, the cache holds an additional 400 MiB of live data. GC does not reclaim those entries, even when no requests are running.
- **Spike 3:** The service holds exactly 400 MiB of necessary state throughout the session. This is not a leak if the budget/lifecycle is acceptable, though GC headroom is still required.

All three can look like “heap increased 400–500 MiB” on a dashboard at a point in time, but the fixes are completely different.

## 23. GC frequency, pause time, and overhead: reading them together

Increasing the allocation rate usually makes young collections occur more frequently **if capacity and policy are equivalent**, yet pause duration may not increase proportionally when the survival rate is low. Conversely, large live data in the CSet can make a pause expensive even when young collections are not very frequent.

Example of two hypothetical profiles:

| Metric | Profile X | Profile Y |
| --- | ---: | ---: |
| Allocation rate | 600 MiB/s | 100 MiB/s |
| Young survival ratio | 3% | 60% |
| Young GC frequency | High | Possibly lower |
| Bytes to copy per collection | Low relative to occupancy | High relative to occupancy |
| Risk | CPU/throughput due to GC cadence | Pause/to-space pressure and old occupancy |

Any conclusion about p99 latency also needs to examine **actual pauses**, thread scheduling, and workload. A collector may incur concurrent CPU overhead even when the number of STW pauses is small.

### Little’s Law is a hint, not an exact live set measurement

You can use the intuition **bytes in-flight ≈ input rate × average time kept**, analogous to Little’s Law, if the system is steady and units/ownership are well-defined:

```text
100 MiB/s object payload
× 2 s average retention
≈ 200 MiB of data currently in-flight (model)
```

This calculation **is not the live heap measured by GC**, because object graph size, duplication, caching, peak concurrency, and JVM layout make the number different. It is useful for deducing that if request latency doubles while throughput stays the same, **the amount of simultaneously live data** can increase.

## 24. Diagnostic scenario: high allocation, low live set

**Symptoms:** many young GCs but stable old generation; post-young-GC occupancy drops sharply; Full GCs are rare; GC CPU is noticeable.

**Hypothesis:** the application creates many short-lived intermediates; GC reclaims well but has to run too frequently.

**Action plan:**

1. Use JFR/allocation profiler to identify methods allocating many bytes/op.
2. Correlate GC rate with QPS and request types; identify requests or payloads causing bursts.
3. Optimize the allocation hot path (reduce temporary objects/copies) or consider young sizing/heap capacity after benchmarking.
4. Re-measure CPU/throughput, p99, and live set to ensure the optimization does not retain data longer.
5. Do not increase the heap indefinitely just to avoid a few young GCs; check footprint and latency budgets.

## 25. Diagnostic scenario: moderate allocation, growing live set

**Symptoms:** old occupancy grows across cycles, post-GC heap used does not return to baseline, GC reclaim ratio drops, eventually heap nears max.

**Hypothesis:** a cache/listener/ThreadLocal/queue is retaining object graphs no longer needed, or the legitimate working set is growing with user data.

**Action plan:**

1. Capture a heap dump/histogram at an appropriate point, and inspect retained size and paths to GC roots.
2. Compare against the business lifecycle: objects should probably end after request/logout/component close.
3. If it is a leak, break the reference path from the longer-lived owner.
4. If it is valid live data, adjust the retention policy, sharding/batching, or capacity budget appropriately.
5. Re-verify post-GC occupancy under an equivalent workload after the fix.

**Do not automatically conclude that a large static map is a leak.** If it is a bounded cache with a good hit rate, the retained memory may be a purposeful working set.

## 26. Diagnostic scenario: insufficient to-space even when heap does not report 100%

**Symptoms:** G1 logs show `to-space exhausted`/evacuation failure, high old regions, mixed collections falling behind, Full GC, or pause spikes.

**Hypothesis:** many survivors need copying, effective free regions are insufficient, or old marking/reclamation arrived too late. There may also be humongous region pressure.

**Action plan:**

1. Read the **GC cause**, old/young/humongous regions, and evacuation/marking timeline.
2. Determine whether **live bytes and promotion rate** are rising; check retained objects with a heap dump if a leak is suspected.
3. Check allocation bursts/humongous allocations and workload concurrency.
4. Use documentation for the exact JDK/GC to review `G1ReservePercent`, adaptive IHOP, heap sizing, and concurrent marking capacity.
5. Consider increasing heap/headroom **alongside an appropriate container limit** after verifying the application genuinely needs that live set.
6. Re-benchmark p99 pauses, throughput, and memory footprint; avoid changing multiple flags at once where causality cannot be attributed.

A Full GC may temporarily resolve fragmentation and restore headroom, but it cannot fix an unboundedly growing retained graph.

## 27. Misconceptions to eliminate

| Misconception | Accurate understanding |
| --- | --- |
| “High allocation rate is a memory leak” | Allocation can be short-lived churn; a leak is unneeded retention |
| “More frequent GC means a larger live set” | GC frequency also depends on rate, young sizing, and policy |
| “Heap used is all live bytes” | Used also contains unreclaimed garbage; partial collections do not measure the whole heap |
| “After a young GC, old occupancy is the exact live set” | Old regions contain objects not fully traced at that point |
| “Total free heap equals total G1 to-space” | G1 uses regions, reserves, policies, and destination constraints |
| “`-Xmx - used` is immediately usable headroom” | Ignores committed, OS limits, fragmentation, and GC reserves |
| “Copying collectors need no extra space” | Evacuation requires destination space for live objects |
| “High survival rate is always good because objects are still alive” | It causes high copy/retention cost and low reclaim ratio |
| “Promotion is always a bug” | Some legitimate data is long-lived and needs old storage |
| “Increasing `-Xmx` always reduces pauses” | It can reduce frequency but increase footprint or work per cycle |
| “Increasing reserve always increases throughput” | Reserve reduces usable application capacity and requires benchmarking |
| “`System.gc()` frees objects still held by a cache” | GC does not ignore strong reachability |
| “Allocation rate = change in heap used per second” | Heap used can drop due to GC and does not count cumulative allocated bytes |
| “Having a Full GC guarantees a leak” | Must analyze GC cause, live data, to-space, and OS limits |
| “G1 concurrent marking means object copying is fully concurrent” | Java 17 G1 evacuates the CSet primarily during STW pauses |
| “Humongous objects are like small objects in Eden” | G1 has special region allocation/reclamation policies |
| “Measuring one snapshot is enough to know the trend” | A timeline across equivalent workloads/GC cycles is required |
| “The fastest collector is the one with the fewest GC events” | Throughput, tail latency, CPU, and footprint must all be considered |

## 28. Practical checklist when choosing how to handle GC pressure

Before tuning flags, be able to answer:

1. What is the **current allocation rate** in MiB/s and how is it distributed by endpoint/job?
2. Is the workload **steady-state or bursty**? Do QPS/concurrency and payload sizes fluctuate?
3. Are the **survival rate/bytes copied** of collection sets unusually high?
4. Are the **promotion rate** and old occupancy rising, stable, or falling?
5. Is **post-GC live data** stable across equivalent cycles?
6. Is there an invalid **heap retention graph** (cache/listener/ThreadLocal/queues)?
7. Does G1 have enough **free regions/to-space** for survivors/promotions?
8. Does concurrent marking start **early enough** for mixed collections to reclaim old space?
9. Are there many **humongous objects**, fragmentation, or to-space exhaustion?
10. Is the phenomenon occurring in the JVM heap or in **native/container memory** outside `-Xmx`?
11. What % of CPU/wall time does GC time take; do **p95/p99 pauses** violate the SLO?
12. Can **unnecessary allocation**, retention, and concurrency be reduced before increasing the heap?
13. Are the flags supported by the running **JDK 17 build**?
14. Have changes been **benchmarked one variable at a time** with a rollback plan if p99/footprint worsens?

## 29. Self-check questions

**Question 1:** Service A creates 800 MiB/s, but the post-GC live set stays steady at 200 MiB. Can we conclude there is a leak?

**No.** This may be very high allocation churn; check GC frequency/CPU and allocation hotspots rather than asserting the retained graph is growing.

**Question 2:** Service B creates 20 MiB/s, yet after every cycle old occupancy increases. Investigation direction?

**Retention and promotion**, possibly a cache/ThreadLocal/listener or a growing legitimate working set; use a heap dump and owner/lifecycle analysis.

**Question 3:** A 400 MiB CSet has 40 MiB live and 360 MiB dead. Model survival rate?

**10%**. Roughly 40 MiB live must be preserved; 360 MiB is reclaimable in the model.

**Question 4:** Heap max is 2 GiB, used is 1.6 GiB. Is 0.4 GiB guaranteed to be free G1 to-space?

**No.** That is only the aggregate difference; committed, regions, reserve, and other constraints must be checked.

**Question 5:** Why can G1 trigger a Full GC after to-space exhausted?

The collector lacks destination space or did not reclaim old space in time; a fallback full-heap compaction may be used to make progress.

**Question 6:** Is `G1ReservePercent` a separate physical RAM reservation outside `-Xmx`?

**No.** It is a policy reserve/false ceiling relative to heap capacity aimed at reducing the risk of to-space/promotion failure.

**Question 7:** Why might concurrent marking not yet reclaim an object that just became unreachable?

G1 SATB may still treat the object as snapshot-live during the ongoing marking cycle; reclamation may occur in the next cycle.

**Question 8:** Two applications have the same allocation rate, but survival is 5% and 90%. Can evacuation cost differ?

**Yes.** The live set to preserve/copy differs substantially, affecting GC CPU, pauses, and destination space.

**Question 9:** Does `(heapUsed2 - heapUsed1)/Δt` accurately measure allocation rate?

**No.** GC may reclaim between the two reads, so the difference is occupancy change rather than cumulative allocation.

**Question 10:** A heap dump shows many large `byte[]` arrays. Does that prove their allocation site is a bug?

**Not yet.** You must trace paths to GC roots/retained owner and inspect lifecycle; where bytes are created may be reasonable, while where they are held too long is the bug.

## 30. References

- [Oracle Java SE 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): collection phases, SATB marking, mixed collections, regions, evacuation failure, and reclamation policies.
- [Oracle Java SE 17 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html): allocation pressure, Full GC, to-space exhaustion, reserve/IHOP, and diagnostics.
- [Oracle Java SE 17 — Introduction to Garbage Collection Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/introduction-garbage-collection-tuning.html): throughput, pause goals, allocation/reclamation, and GC mechanics.
- [Oracle Java SE 17 — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): Serial, Parallel, G1, ZGC, and collector selection.
- [Java SE 17 — `MemoryUsage` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): used, committed, max, and init.
- [Java SE 17 — `MemoryMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap usage.
- [Java SE 17 — `ThreadMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread diagnostics.
- [Java SE 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xms`/`-Xmx`, `-Xlog`, `G1ReservePercent`, and VM flags.
- [Java SE 17 — `jcmd` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html) and [`jstat` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): heap/GC runtime diagnostics.
- [Java SE 17 — Flight Recorder API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html): runtime event collection platform and allocation/GC observation support.

**Remember:** **Allocation rate** explains how fast the heap is consumed; **live set/survival** explains how much data GC must keep or copy; **headroom/to-space** explains whether the collector has enough room to continue while source space cannot yet be reclaimed. Only by measuring and correlating all three with **GC phases, old occupancy, promotion, humongous regions, pause/throughput, and process/container limits** can you distinguish normal allocation churn, memory retention leaks, and evacuation pressure.
