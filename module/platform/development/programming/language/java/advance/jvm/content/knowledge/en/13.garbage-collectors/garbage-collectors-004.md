# The G1 Cycle: Young Collection, Concurrent Marking, and Mixed Collection

## 1. The Big Picture

**G1 (Garbage-First Garbage Collector)** is HotSpot JVM's **generational, region-based** garbage collector. G1 aims to balance throughput with latency, especially when an application has a relatively large heap and needs to control *pause times* at a soft target level.

The most common point of confusion: **young collection**, **concurrent marking**, and **mixed collection** are not three separate garbage collectors. They are **different activities and phases within the lifecycle of the same G1 collector**.

A conceptual cycle on HotSpot/JDK 17:

```text
YOUNG-ONLY PHASE
    |
    +--> Normal Young GC (STW, parallel evacuation)
    |           |
    |           +--> live objects: survivor or promoted to old
    |           +--> young GCs may repeat multiple times
    |
    +--> Old occupancy/IHOP reaches the appropriate threshold
                |
                v
         Concurrent Start
         (young GC + initial-mark work during STW)
                |
                v
         Concurrent marking cycle
           ├── root-region scan / marking (application keeps running)
           ├── Normal Young GCs (STW) may interleave
           ├── Remark (STW)
           ├── preparation work / rebuild candidates (concurrent)
           └── Cleanup (STW)
                |
                +--> Are there enough reclaimable old regions?
                      |
                 +----+----+
                 |         |
                No        Yes
                 |         |
                 v         v
           Young-only   Prepare Mixed young GC
                             |
                             v
                      SPACE-RECLAMATION PHASE
                         Mixed GC (STW):
                         young + selected old regions
                             |
                         may repeat
                             |
                             v
                         Young-only
```

**Note:** this is a **typical flow**, not a mandatory order in which every log line must appear. G1 may not enter mixed collections if there are not enough old regions worth reclaiming; a concurrent cycle may be canceled/undone depending on conditions; abnormal heap pressure may lead to evacuation failure or a Full GC fallback.

According to the Oracle JDK 17 guide, G1 at a high level consists of two alternating phases: **Young-Only** and **Space-Reclamation**. Concurrent marking is the activity that prepares liveness information so the subsequent old-region reclamation phase can decide which objects are still alive and which regions should be selected.

### Learning Objectives

After this lesson, you should be able to:

1. Explain **Eden, Survivor, Old, Humongous regions**, region sizing, and the collection set.
2. Distinguish **Young GC**, **Concurrent Start**, **concurrent mark**, **Remark**, **Cleanup**, **Prepare Mixed**, and **Mixed GC**.
3. Understand why G1 has **both STW pauses and concurrent work**, and why marking does not directly reclaim all old regions.
4. Understand **IHOP**, adaptive marking start, SATB, remembered sets, evacuation/promotion, and pause predictions.
5. Read logs for `Pause Young (Normal)`, `Concurrent Start`, `Concurrent Mark Cycle`, `Pause Remark`, `Pause Cleanup`, `Prepare Mixed`, and `Pause Young (Mixed)` in supported HotSpot versions.
6. Distinguish normal behavior from **evacuation failure, Full GC, humongous pressure, and allocation stalls**.
7. Practice with Java 17+ without turning GC schedules or GC counts into a fixed stdout expectation.

## 2. G1 Partitions the Heap into Regions

Unlike a diagram model that divides the heap into fixed contiguous Eden/Survivor/Old bands, G1 divides the heap into **equal-sized regions**. These regions are assigned **logical roles** over time.

```text
G1 Heap (diagram of equal-sized regions)

+------+-------+------+-------+------+-------+------+
| Eden | Old   | Free | Eden  | Old  | Surv. | Free |
+------+-------+------+-------+------+-------+------+
| Old  | Eden  | Free | Hum.  | Hum. | Old   | Eden |
+------+-------+------+-------+------+-------+------+

Eden / Survivor / Old = states/roles of the regions,
not necessarily contiguous segments in address space.
```

Important region types:

| Region | Role |
| --- | --- |
| **Eden** | Allocates most new objects in the common case |
| **Survivor** | Receives objects that survive young evacuation and do not yet need promotion |
| **Old** | Holds longer-lived/promoted objects; candidates for mixed collection when appropriate |
| **Free** | Unused; can be assigned by G1 to another role |
| **Humongous** | Holds a very large object, using one or more contiguous regions and handled specially |

### 2.1. Region size

On HotSpot JDK 17, region size is typically chosen automatically so that the number of regions is around 2,048, with a power-of-two size in the range of **1–32 MiB** according to the flags/ergonomics of this version.

Experimental tuning example:

```bash
java -XX:+UseG1GC -XX:G1HeapRegionSize=2m -jar application.jar
```

`application.jar` is a **placeholder** for a real application. The `G1HeapRegionSize` flag is a HotSpot option, not a Java specification contract; valid values and heuristics may differ in newer JDKs.

**Do not assume 1 region = 1 MiB** for every Java process. Rely on GC logs or `PrintFlagsFinal` from the actual JVM.

### 2.2. Region roles can change

A region considered Eden at one point can be reclaimed and become Free, and later be used as Old. G1 manages region groups on demand; the idea of "an object in a fixed Eden region from start to end of its life" is inaccurate.

### 2.3. G1 is still generational

Most new objects are allocated in the young generation; objects that survive long enough may be **promoted** to old. Because most objects usually die young, collecting young regions repeatedly can be very efficient. Old regions are handled through different steps because the cost of determining liveness and moving old objects is usually higher.

## 3. Normal Young GC — Collecting the Young Generation

**Young collection** typically occurs when G1 needs to reclaim Eden regions to continue allocation. This activity is primarily a **stop-the-world (STW) evacuation pause**: the application stops, and multiple GC workers can run in parallel to copy live objects.

```text
Before young GC:
  Eden:    [live A] [dead x] [live B] [dead y]
  Survivor:[live C]
  Old:     [live O1]

STW young evacuation:
  Live A, B, C --> Survivor or Old destination regions
  Dead x, y   --> not copied

After young GC:
  Old Eden regions are returned to a reusable state
  Live objects remain reachable via updated references
```

**Important:** G1 is not required to "scan every object and call a destructor." Dead objects do not need to be copied to a new location; source regions are reclaimed for allocation once the collection completes.

### 3.1. Evacuation is not just clearing memory

To preserve Java semantics, G1 must:

- Identify references into the collection set.
- Determine which live objects must be kept.
- Copy live objects into appropriate destination regions.
- Update references according to the algorithm's rules.
- Ensure mutators continue to see the correct objects after the pause.

**Evacuation/copying** also serves to **compact** live data to reclaim free space.

### 3.2. Surviving and promotion

An object that survives a young GC may be placed into a survivor region; after sufficient age or under specific conditions, it is **promoted** to old. The decision depends on age, tenuring distribution, survivor sizing, and heap pressure—not a rigid rule of "exactly N young GCs always promotes to old" for every runtime.

### 3.3. Young GC still occurs during concurrent marking

Marking is generally aimed at preparing to reclaim old regions, but the application continues allocating into young. G1 can interleave **Normal Young GCs (STW)** while concurrent marking has not yet finished. Therefore, do not think that "whenever G1 is marking, all young collections stop until the end."

### 3.4. Why is Young GC usually faster than collecting the whole heap?

G1 processes a selected **collection set**, rather than having to copy all objects in the heap. G1 uses structures such as **remembered sets** to track references from other regions into the regions being collected, avoiding having to scan every old object on every young pause.

However, a young GC can still be long if the collection set is large, the number of live objects is high, many references must be processed, CPU is constrained, or abnormal conditions occur.

## 4. Collection Set (CSet) and Remembered Sets

**Collection Set — CSet** is the set of **source regions** that G1 intends to reclaim in a collection pause.

- In a **Normal Young GC**, the CSet focuses on **young regions**; handling of some humongous objects has a separate reclaim path depending on conditions.
- In a **Mixed GC**, the CSet contains **young regions + some old regions** selected from the candidate list prepared after marking.

Example:

```text
Normal Young CSet:
  {Eden-1, Eden-2, Survivor-3}

Mixed CSet:
  {Eden-4, Survivor-2, Old-7, Old-11}
```

The region names and sets above are illustrative only. G1 makes actual decisions based on heap state, its prediction model, and pause constraints.

### 4.1. Why are remembered sets needed?

An old object may contain a field pointing to an object in a young region:

```text
Old region R1       Young region R9
  [Service] --------> [Request]
```

If young GC only scanned references originating from young, it would risk missing an object that is still reachable from old. G1 uses mechanisms to track cross-region references, commonly explained using **remembered sets** and **card tables/write barriers**.

Thanks to remembered sets, G1 can identify important incoming references without scanning the entire old generation on every young collection.

### 4.2. What is a write barrier?

When the application writes a reference field, the JIT/runtime can perform extra bookkeeping to reflect that update in the GC tracking system. This is a **write barrier** in the collector's algorithm.

A Java statement such as:

```java
holder.child = newChild;
```

is just an illustration inside a method where `holder` and `newChild` are already declared. The application programmer sees a reference assignment; the JVM may execute additional barrier code to manage remembered sets and concurrent marking.

**Do not lump all barriers into one thing:** G1 has different mechanisms for remembered set updates and SATB marking.

## 5. When Does G1 Decide to Start Concurrent Marking?

G1 does not collect old regions via mixed collection merely because the application just performed a young GC. It first needs to evaluate the **liveness of old regions**, to know which regions contain enough garbage worth reclaiming.

An important milestone is the **Initiating Heap Occupancy Threshold**, commonly called **IHOP**.

### 5.1. IHOP is not simply "45% of the whole heap always triggers marking"

In the **Oracle JDK 17 G1** guide, G1 enables **Adaptive IHOP** by default. G1 collects data on:

- The time required to complete a concurrent marking cycle.
- The rate at which old generation occupancy grows during marking.
- Heap headroom/reserve and the ability to complete old-reclamation preparation before running out of space.

Initially, when there are not yet enough measurement samples, the `InitiatingHeapOccupancyPercent` flag (initial value typically 45) can be used as a threshold calculated against the old generation according to the described mechanism. Afterward, G1 **adjusts the threshold adaptively**.

```text
-XX:+G1UseAdaptiveIHOP
-XX:InitiatingHeapOccupancyPercent=45
```

These are **illustrative options/values for HotSpot JDK 17**, not a recommendation to always fix it at 45%, and should not be interpreted as a percentage of **all Java objects** across the entire heap in every version.

If adaptive IHOP is disabled with `-XX:-G1UseAdaptiveIHOP`, threshold usage becomes more fixed according to the configured value, but the risk of starting marking too early or too late needs to be benchmarked.

### 5.2. Why does starting early or late matter?

- **Starting too late:** when old occupancy grows rapidly, marking may not finish before there are too few free regions left for evacuation/promotion; pressure is likely.
- **Starting too early:** may spend CPU on unnecessary concurrent work, reducing application throughput.
- **Adaptive IHOP:** tries to balance starting early enough based on measured time and allocation rate.

Mental picture:

```text
Old occupancy increases ------->
     mark start           mark complete        mixed reclaim
          |                    |                     |
          +--- concurrent -----+--- prepare ---------+

If mark start is too close to a full heap,
the application may not have enough free regions to wait for the cycle to finish.
```

There is no single optimal threshold for every workload or every JDK.

## 6. Concurrent Start — The Transition Step Between Young-Only and Marking

When G1 determines it is time to begin liveness analysis, it can initiate a **Concurrent Start young collection**.

This is a very important learning point:

> **Concurrent Start GC is a young GC pause (STW) that performs the opening work of concurrent marking.** The word "Concurrent" in the name indicates that the concurrent cycle is being triggered, **not that this pause itself runs concurrently with mutators**.

A log line might be named:

```text
Pause Young (Concurrent Start) (G1 Humongous Allocation)
```

or another appropriate cause name. This is an **illustrative log sample**, not guaranteed stdout or a promise of an event that will definitely appear in a small program.

### 6.1. Initial-mark work

Concurrent Start is commonly explained as a young evacuation combined with **initial mark** work. The JVM sets up the necessary state for G1 to begin tracing old generation liveness afterward.

If you only see `Pause Young (Concurrent Start)` in the log, do not conclude that **old garbage has already been reclaimed** in that pause. Marking still has to run, and mixed collection only occurs when sufficient information/suitable candidates exist.

### 6.2. A special trigger: humongous allocation

Very large objects are handled by G1 as **humongous objects**, which can be allocated directly into old/humongous regions. G1 may check IHOP when allocating this type of object and start a concurrent cycle if conditions are met.

Therefore, logs may show `G1 Humongous Allocation` as the cause of a young pause/concurrent start; one should not claim that every concurrent marking only originates from an ordinary Eden allocation failure.

## 7. Root Region Scan and Concurrent Marking

After the concurrent-start pause, G1 performs several activities **concurrently with the application**, including scanning the necessary root regions and concurrent marking.

### 7.1. Concurrent root-region scanning

Young survivor regions may contain references to old objects. In G1's mechanism, scanning survivor/root regions must be coordinated with the next young collection to maintain accurate liveness information.

A conceptual sequence:

```text
Concurrent Start (STW)
      |
      v
Concurrent root region scan
      |
      v
Concurrent mark reachable objects
      |
      v
Remark (STW)
```

**Do not interpret the diagram as "no young GC can interleave in any segment"**; actual runtime scheduling and constraints between root region scan and young pauses follow the HotSpot algorithm.

### 7.2. What does concurrent marking determine?

Marking identifies objects considered **live** according to the algorithm's invariants, specifically to estimate live bytes in old regions. After marking, G1 knows which old regions have the most reclaimable space and can decide on the candidate set for reclamation.

**Marking does not itself copy or delete all old objects.** An "unmarked/dead" object may still physically remain in an old region until the region is reclaimed by cleanup or evacuation according to the mechanism.

### 7.3. SATB — Snapshot-at-the-Beginning

G1 uses a **snapshot-at-the-beginning (SATB)** variant for concurrent marking. Intuition:

1. G1 wants to maintain a consistent view of references that were meaningful at the start of marking.
2. Mutators can change references while GC is running.
3. Write barriers record **old reference values** that are overwritten in tracked cases.
4. GC processes the corresponding buffer/barrier data so liveness is not lost under the snapshot invariant.

Illustrative example:

```text
Before mutation:
  A.child -> B

Mutator:
  A.child = C

SATB marking must appropriately process information about reference B
that was removed from the field while the mark cycle was running.
```

**This does not mean every old reference becomes a permanent GC root**, or that every write enqueues identically. This is a conceptual summary; HotSpot optimizes barriers and buffer processing based on specific state.

### 7.4. Why does concurrent marking have a CPU cost?

G1 must trace data concurrently with mutators, processing SATB buffers, remembered sets, and changes to the reference graph. These CPU cycles are consumed while the application is still running; thus **STW latency may be better, but overall throughput may incur a cost**.

Do not treat concurrent as "free GC."

## 8. Remark — Finalizing Marking Information in STW

When the main concurrent marking phase is nearly complete, G1 performs a **Remark pause**. This is an **STW operation**.

Activities according to the JDK 17 G1 guide may include:

- Completing/finalizing remaining marking information.
- Performing global reference-processing according to JVM mechanisms.
- Performing class unloading under corresponding conditions.
- Reclaiming some regions that have become completely empty.
- Cleaning up/preparing certain internal data structures.

An illustrative log:

```text
GC(17) Pause Remark 45M->45M(128M) 1.234ms
```

The numbers are **purely illustrative**; an actual JVM will print different occupancy, timings, tags, and GC IDs.

### 8.1. Is Remark a mixed collection?

**No.** Remark is the step that finishes marking and performs related processing, not a normal mixed evacuation pause of young + selected old regions.

Some memory may be reclaimed during Remark/Cleanup for fully dead or special regions, but that **does not make Remark a Mixed GC**.

### 8.2. Why does Remark need STW?

Consistent finalization steps of concurrent marking and reference processing require coordination at points where the VM decides to stop mutators. Even though marking ran concurrently for much of the time, the process still has STW phases.

### 8.3. Abnormally long Remark

If `Pause Remark` is large, investigate reference processing, class unloading, the number of live references, and the related workload. Do not just adjust `MaxGCPauseMillis` and expect every remark to shrink proportionally.

## 9. Cleanup — Determining Whether to Proceed to Space-Reclamation

After Remark, G1 computes/prepares suitable old-region candidates; some of this work is performed concurrently. Then there is a **Cleanup pause (STW)** to finalize the decision-making for reclamation.

Diagram:

```text
Concurrent marking
         |
         v
    Remark (STW)
         |
         +-- prepare/sort old-region reclamation candidates
         |     (some work may be concurrent)
         v
    Cleanup (STW)
         |
         +--> mixed reclaim worthwhile? --> Prepare Mixed
         |
         +--> not worth reclaiming? -----> continue Young-Only
```

### 9.1. Why doesn't every marking cycle lead to mixed collections?

Marking only produces **liveness information**. G1 still has to evaluate:

- How many old regions qualify as candidates?
- How many live bytes and reclaimable bytes remain in each region?
- What is the cost of evacuating live data compared to the amount of space reclaimed?
- Does the pause goal allow adding old regions to the CSet?
- Does the heap already have enough free space?

If additional reclamation does not provide commensurate benefit, G1 may **skip the mixed phase**.

### 9.2. Cleanup and fully empty regions

A region determined to have **no live objects** can be reclaimed relatively cheaply. This differs from an old region that still has live objects, because reclaiming an old region with live data usually requires **evacuating** the live objects elsewhere.

## 10. Prepare Mixed Young Collection

If G1 decides it needs to reclaim old regions, Oracle describes the young-only phase ending with a **Prepare Mixed young collection**.

Common point of confusion:

- **Prepare Mixed** is a **young collection** that serves as a transition/preparation before space reclamation.
- **Mixed GC** is the collection whose CSet includes **young + selected old regions**.

The name that may appear in HotSpot logs is:

```text
Pause Young (Prepare Mixed)
```

This is a sample event name, not fixed stdout.

### 10.1. Why not move directly to a Full GC for all old regions?

G1's goal is **incremental reclamation of old regions** rather than necessarily stopping the entire application to process the whole old gen at once. By reclaiming a group of old regions alongside young collections, G1 can spread the cost across multiple pauses based on its prediction model.

A transition step helps prepare the collection set state and sizing according to the G1 strategy of the corresponding JDK.

## 11. Mixed GC — Collecting Young Plus Some Old Regions

**Mixed GC** is called *mixed* because it combines:

- **Young regions** in the CSet, and
- Some **old regions** that marking/cleanup showed can have memory reclaimed efficiently.

Diagram:

```text
Heap before:
  Young regions:  Y1, Y2, S1
  Old candidates: O3 (20% live), O7 (40% live), O9 (90% live)
  Old others:     O1, O2, ...

Illustrative Mixed CSet:
  {Y1, Y2, S1, O3, O7}

STW mixed evacuation:
  - Copy live objects from Y1,Y2,S1 per young rules
  - Copy surviving live objects from O3,O7 to old destinations
  - Update references, return evacuated source regions to free

O9: unlikely to be selected because it has less garbage / higher copy cost.
```

The percentages and selection above **are examples only**, not a mandatory outcome chosen by G1 in every case.

### 11.1. Mixed does not mean "collect the entire old gen"

A Mixed GC only selects **a portion of old regions** as candidates to keep pauses reasonable. Unselected old regions continue to exist; later they may become candidates for other cycles.

### 11.2. Mixed evacuation is STW

Even though old candidates are selected based on **concurrent marking**, **evacuating regions in a mixed collection is STW** on HotSpot G1 JDK 17. Multiple GC workers can run **in parallel with each other** during the pause, but application mutators are stopped.

Therefore:

```text
Concurrent marking (application keeps running)
            ≠
Mixed evacuation (application is stopped during the pause)
```

### 11.3. Why copy live old objects?

G1 wants to reclaim an entire region for reuse. If an old region contains both live and dead objects, copying the live objects elsewhere allows reclaiming the entire source region in a compacting manner.

If a region has **many live bytes**, the copy cost is high while the reclaimable portion is small. G1 therefore typically prioritizes regions with more garbage, leading to the name **Garbage First**.

### 11.4. Mixed collections can repeat multiple times

A space-reclamation phase usually consists of **multiple Mixed GCs**. G1 evaluates the remaining old candidates, pause prediction, and reclaimable memory ratio to decide whether to continue or stop.

There is no guarantee that every marking cycle is accompanied by exactly 8 mixed collections; `G1MixedGCCountTarget` is a **target/heuristic**, not a fixed 8-iteration loop.

## 12. Old Candidate Selection and Collection Set Economics

After marking, G1 has an estimate of the **live occupancy** of old regions. Regions with **fewer live bytes** are usually attractive because there is more garbage space that can be reclaimed with less copying work.

### 12.1. Region efficiency example

Suppose the region size is 2 MiB:

| Old region | Live bytes | Reclaimable bytes (approx.) | Intuition |
| --- | ---: | ---: | --- |
| A | 0.2 MiB | 1.8 MiB | Very worthwhile to select if the pause model allows |
| B | 0.8 MiB | 1.2 MiB | Worth considering |
| C | 1.9 MiB | 0.1 MiB | Little benefit, high copy cost |

This table is a **numerical example**, assuming old regions have no special accounting/representation factors, and only illustrates the live/reclaimable ratio. Actual candidate selection also involves cost models, remembered sets, and other limits.

### 12.2. `G1MixedGCLiveThresholdPercent`

On HotSpot JDK 17, this flag is one of the thresholds for considering **an old region eligible for mixed collection** based on occupancy. For example, the default value stated in JDK 17 documentation is **85%**.

Do not conclude that every old region with exactly 84% live will immediately enter the CSet. It still has to pass candidate filtering, pause prediction, and other limits.

### 12.3. `G1MixedGCCountTarget`

This flag influences the **target number of mixed pauses** used to process candidates after marking. JDK 17 documentation states a typical default of **8**.

Setting a smaller number may require reclaiming more old regions per pause; this can potentially increase pause cost. However, actual results also depend on heap/candidates and policy.

### 12.4. `G1HeapWastePercent`

G1 may decide to stop space-reclamation if the remaining reclaimable garbage in candidates is smaller than what is considered worthwhile relative to the heap. JDK 17 documentation states a default of **5%**.

Do not interpret this as "G1 allows 5% garbage across the entire JVM and then definitely stops GC"; this is a **threshold/heuristic in the mixed candidate space reclamation decision**.

### 12.5. Pause prediction

G1 has a model that estimates the time to process young and optional old regions to choose a CSet that fits the pause goal.

Commonly used flag:

```text
-XX:MaxGCPauseMillis=200
```

This is a **soft pause goal**; G1 does not promise that every Young/Mixed/Remark/Cleanup pause will always be under 200 ms. Overhead, live bytes, remembered-set processing, CPU throttling, and anomalies can cause pauses to exceed the goal.

## 13. Young-Only and Space-Reclamation: Timeline Distinguishing STW/Concurrent

A complete study timeline:

```text
T0           T1            T2             T3              T4          T5
|------------|-------------|--------------|---------------|-----------|---->

Application:
RUN       [STW] RUN    [STW] RUN       [STW] RUN       [STW] RUN  [STW]

G1:
Normal Young    Concurrent Start       Remark        Cleanup   Mixed #1
     ^          + initial mark             ^             ^        ^
     |               |                     |             |        |
  evacuate            +--- concurrent marking ---+        |      young+old
  young                           |                        |
                       normal young STW can interleave    Prepare Mixed
                                                        may precede Mixed
```

The diagram is a **logical model**, not drawn to exact time scale and not listing every pause. In practice, you may see **multiple Normal Young GCs**, one or more mixed collections, and concurrent work between pauses.

What is important when reading logs:

- **Concurrent Mark Cycle**: may span a long wall-clock duration, but mutators keep running most of the time.
- **Pause Young**: the application stops during the pause even though GC work is parallel.
- **Pause Remark / Cleanup**: these have STW pauses, though the main marking work was concurrent.
- **Pause Young (Mixed)**: young + selected old evacuation in STW.

## 14. Humongous Objects: Separate Path and Cycle Impact

G1 classifies objects whose size is **greater than or equal to half a region** as **humongous** in the HotSpot JDK 17 model.

For example, if the region size is 2 MiB, an object with a total size of roughly 1 MiB or more may be considered humongous, depending on header/array allocation accounting.

### 14.1. Why are humongous objects noteworthy?

- They are usually allocated directly into **humongous old regions**.
- A large humongous object can occupy **multiple contiguous regions**.
- The remainder of the last region cannot be used for ordinary allocation while the object remains alive.
- Allocating humongous objects can put pressure on old occupancy and trigger **Concurrent Start** early.
- G1 has special reclamation rules; some dead humongous objects can be reclaimed early during a young GC via eager reclaim.

### 14.2. Do not assume humongous objects are always moved in mixed

In the HotSpot JDK 17 description, G1 **does not move humongous objects** the way it evacuates ordinary young/old regions. It can reclaim the regions when the object is no longer live via appropriate paths, with eager reclaim or cleanup/Full GC paths depending on VM capabilities.

Therefore, a program that creates many large arrays can have very different GC behavior compared to millions of small objects, even with a similar total byte count.

### 14.3. Log cause

Example of a common label:

```text
Pause Young (Concurrent Start) (G1 Humongous Allocation)
```

If you see this label, investigate **allocation sizes and region size** before guessing that G1 is "running mixed" or "the collector is buggy."

## 15. When Does a G1 Cycle Skip Steps?

Textbook diagrams often draw the full **Young → Mark → Mixed → Young**, but in reality:

1. An application may only need young collections; old occupancy never reaches the mark-triggering threshold.
2. A concurrent start may be **undone** when the VM determines further marking is unnecessary, depending on version/configuration.
3. After marking/cleanup, there are no sufficiently beneficial old candidates → **skips the mixed phase**.
4. Most regions were already reclaimed in special handling/fully dead steps → little or no mixed work.
5. Excessively high **allocation pressure** can cause marking and planned mixed reclamation to fall behind, leading to evacuation failure or Full GC.
6. `System.gc()` or JVM-specific triggers can produce collection behavior different from the usual cycle.

**Do not turn a logical diagram into an assertion that "the application must print all phase names every N allocations."** The algorithm is adaptive, based on heap, data survival, JVM/JDK version, and environment.

## 16. Evacuation Failure and Full GC Fallback

### 16.1. To-space pressure

Evacuation requires **free destination regions** to copy live objects. If the heap has too many live objects or insufficient free headroom, G1 may not have space for some objects during evacuation.

The issue may be described as **evacuation failure**, or in some HotSpot versions/historical logs as `to-space exhausted`.

```text
CSet has many live objects
           |
           v
Needs to-space for copying
           |
     enough free regions?
        /         \
      yes          no
      |             |
      v             v
  evacuate     evacuation failure handling,
  normally     may increase GC overhead;
               if pressure continues -> Full GC/OOME
```

This does not prove the Java bytecode is wrong; it indicates insufficient **capacity/GC headroom** for the heap/workload state at that time.

### 16.2. Full GC is the fallback path

When G1 cannot resolve pressure through normal steps, HotSpot may use a **Full GC STW** to compact the heap more broadly. This is a fallback path, not a "mandatory" mixed collection part of every cycle.

**A Full GC on G1 is not a slightly larger Mixed GC**. It has a different goal and scope, usually with the risk of much longer pauses.

### 16.3. Investigating the cause

When logs show evacuation failure/Full GC/OOME:

- Inspect live-set size and the number of old/humongous regions.
- Measure allocation/promotion rate.
- Check heap headroom, `-Xmx`, and container limits.
- Check whether marking started too late or concurrent work could not keep up.
- Look for large arrays/humongous allocations.
- Look for object retention/leaks and unbounded caches.
- Read pause/cause details according to the actual HotSpot version.

**Increasing the heap** can be reasonable when the workload needs capacity, but **it does not fix retention leaks or unbounded data structures**.

## 17. Reading GC Logs by Phase

HotSpot JDK 17 uses **Unified Logging**, for example:

```bash
java -XX:+UseG1GC -Xlog:gc*=info -jar application.jar
```

Here, `application.jar` is just a placeholder. The runnable program below uses a class file instead of a JAR.

### 17.1. Conceptual log sample

```text
[info][gc] GC(1) Pause Young (Normal) (G1 Evacuation Pause) ...
[info][gc] GC(2) Pause Young (Concurrent Start) (G1 Evacuation Pause) ...
[info][gc] GC(3) Concurrent Mark Cycle
[info][gc] GC(3) Concurrent Scan Root Regions ...
[info][gc] GC(3) Concurrent Mark ...
[info][gc] GC(3) Pause Remark ...
[info][gc] GC(3) Pause Cleanup ...
[info][gc] GC(4) Pause Young (Prepare Mixed) ...
[info][gc] GC(5) Pause Young (Mixed) (G1 Evacuation Pause) ...
```

**This is a self-written sample for recognizing keywords, NOT output captured from a real run.** In real HotSpot, GC IDs, timestamps, tag line ordering, and phase formatting may differ; concurrent-phase logs and young pauses may interleave, and not all nine lines above necessarily appear.

### 17.2. Questions to ask from each line

| Log line/pattern | Diagnostic question |
| --- | --- |
| `Pause Young (Normal)` | Is the Young CSet large? What are the pause duration/evacuation costs? |
| `Pause Young (Concurrent Start)` | Which threshold/causes triggered the marking cycle? |
| `Concurrent Scan Root Regions` | How long did root-region scanning take? |
| `Concurrent Mark` | Are GC marking workers keeping up with mutators? |
| `Pause Remark` | Are marking finalization/reference processing/class unloading taking significant time? |
| `Pause Cleanup` | Are old candidates still worth reclaiming? |
| `Pause Young (Prepare Mixed)` | Is G1 transitioning to space reclamation? |
| `Pause Young (Mixed)` | How many old regions were selected, and how much was reclaimed? |
| `Pause Full` | Why was the normal GC path insufficient? |

To view memory by regions, you can enable appropriate tags/levels depending on HotSpot/JDK; first check with:

```bash
java -Xlog:help
```

### 17.3. Do not mistakenly add concurrent time into STW pause

A log line `Concurrent Mark Cycle 400ms` **does not mean the application was stopped for 400ms**. Most of the activity can happen while mutators continue running.

Conversely, a `Pause Young (Mixed) 70ms` is a concrete pause that can contribute to request latency. Analyze **STW pause distribution** and **application latency p95/p99**, not just total GC cycle duration.

## 18. Complete Java 17+ Example: Creating GC Pressure, Retaining Some Objects

This demo creates many byte arrays, retains some arrays so they stay reachable, while letting most arrays become candidates for reclamation. It helps observe **Normal Young GCs** and, depending on heap/collector heuristics, concurrent/mixed phases.

Create the file **`G1CycleDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public final class G1CycleDemo {
    private static volatile byte[] latest;

    public static void main(String[] args) {
        List<byte[]> survivors = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 768; i++) {
            byte[] block = new byte[256 * 1024];
            block[0] = (byte) i;
            block[block.length - 1] = (byte) i;

            checksum += Byte.toUnsignedInt(block[0]);
            latest = block;

            if (i % 32 == 0) {
                survivors.add(block);
            }
        }

        long survivorSum = 0;
        for (byte[] block : survivors) {
            survivorSum += Byte.toUnsignedInt(block[0]);
        }

        System.out.println("iterations=" + 768);
        System.out.println("checksum=" + checksum);
        System.out.println("survivor arrays=" + survivors.size());
        System.out.println("survivor sample sum=" + survivorSum);
    }
}
```

### 18.1. Compile and run

Requires **JDK 17+**; the example was compiled with `javac --release 17` and ran successfully on an OpenJDK supporting G1/Parallel.

```bash
javac --release 17 G1CycleDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC G1CycleDemo
```

**Exact stdout of the application itself when running normally:**

```text
iterations=768
checksum=97920
survivor arrays=24
survivor sample sum=2688
```

Mathematical explanation:

- The loop has 768 iterations, meaning three passes through values `0..255` after `& 0xff`.
- `checksum = 3 × (0 + 1 + ... + 255) = 97920`.
- Values of `i` divisible by 32 in `0..767` total 24 values.
- Each group `0,32,64,96,128,160,192,224` sums to 896; repeated three times → `survivorSum = 2688`.

### 18.2. Why use `volatile latest`?

The demo assigns each `block` to a static volatile field `latest`. That creates an operation with an appropriate side effect, making the workload not just allocations that the JIT could easily see as "unobservable" and optimize away under certain optimizations. Old blocks can still become garbage when replaced; only blocks held in the list or `latest` have clear strong references from the code.

**Do not claim `volatile` guarantees every block will pass through the old generation**. Collector policies and the JIT still have the right to optimize anything that does not affect Java semantics.

### 18.3. Why not assert "there must be exactly one Mixed GC"?

Even though the program allocates a total of about 192 MiB of byte-array payload across many allocation rounds with a 64 MiB heap and some survivors, G1 can choose different collection paths depending on:

- JDK version, heap region size, IHOP history.
- CPU speed and loop speed.
- Allocation rate and amount of live data.
- How many old regions have formed.
- Whether concurrent marking finishes in time.
- Heuristics/humongous thresholds and GC logging configuration.

**G1 does not guarantee a mixed GC will appear in this program.** The demo is for observation, not forcing a phase based on a wrong assumption.

## 19. Practicing Reading G1 Logs and Comparing with Parallel GC

### 19.1. Running G1 with GC logs

```bash
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info G1CycleDemo
```

Observe:

- Does startup report `Using G1`?
- How many `Pause Young (Normal)` events are there?
- Does `Concurrent Start` appear?
- If it appears, are there `Remark` and `Cleanup` afterward?
- If `Mixed` occurs, in which pause are old regions reclaimed?
- Are there any `Full GC` or `Evacuation Failure` events?

**GC log output is not fixed** across workloads/timings, so there is no "exact stdout" for runtime lines. Only the four lines printed by `G1CycleDemo` are deterministic.

### 19.2. Running Parallel GC on the same workload

```bash
java -Xms64m -Xmx64m -XX:+UseParallelGC -Xlog:gc*=info G1CycleDemo
```

Parallel GC organizes phases differently from G1. It primarily performs collection work using multiple GC workers during STW pauses, without G1's Young-Only → Concurrent Mark → Mixed cycle.

Comparison goals:

- The application checksum is **identical**, proving GC does not alter Java program semantics.
- Collector events/logs are **different**.
- Pause distributions, CPU, and throughput may differ.

**Do not label "Parallel GC = Mixed G1"** just because both use multiple GC worker threads.

### 19.3. Comparing across multiple runs

A reliable benchmark requires warm-up, fixed heap, CPU quota, and JDK build, recording multiple runs. A single run is not enough to prove which collector is faster for all cases.

For this lesson, the important thing is **reading G1's phases accurately**, not using a too-short microbenchmark to decide a production GC choice.

## 20. How to Inspect G1 Details Using HotSpot Options

Some flags applicable to JDK 17:

```text
-XX:+UseG1GC
-XX:MaxGCPauseMillis=200
-XX:G1HeapRegionSize=2m
-XX:InitiatingHeapOccupancyPercent=45
-XX:+G1UseAdaptiveIHOP
-XX:G1MixedGCCountTarget=8
-XX:G1HeapWastePercent=5
-XX:G1ReservePercent=10
-XX:ParallelGCThreads=<n>
-XX:ConcGCThreads=<n>
```

**Do not combine all flags into a "default optimization set."** The list above is a reference list; some flags may need availability/rule checks per build. `<n>` is a placeholder, not a valid number to copy verbatim.

### 20.1. Characteristics of the flags

| Flag | Direction of impact | Risk if changed blindly |
| --- | --- | --- |
| `MaxGCPauseMillis` | G1 pause prediction goal | Setting too low can increase GC count and CPU overhead |
| `G1HeapRegionSize` | Region size | Changes humongous threshold, overhead/cardinality |
| `InitiatingHeapOccupancyPercent` | Marking initiation threshold, especially before enough samples | Poor configuration can lead to starting too early/late |
| `G1UseAdaptiveIHOP` | G1 adaptively adjusts mark initiation timing | Disabling without understanding workload loses automatic tuning |
| `G1MixedGCCountTarget` | Target number of mixed collections/cycle | Fewer phases may require reclaiming more old regions per pause |
| `G1HeapWastePercent` | Remaining benefit threshold to continue old reclamation | Can cause too much/too little mixed work |
| `G1ReservePercent` | Reserve/headroom to help avoid running out of destination space | Keeping too much reserve can reduce effective heap capacity |
| `ParallelGCThreads` | Number of workers in parallel GC pauses | More threads does not guarantee pauses shrink proportionally |
| `ConcGCThreads` | Workers for concurrent work | Too many steals CPU from application; too few may fail to mark in time |

### 20.2. Safe tuning workflow

1. Start from HotSpot G1 defaults if there is no evidence needing changes.
2. Collect GC logs/JFR and real application metrics.
3. See whether the problem is in **young STW**, **mixed STW**, **remark/cleanup**, or **marking not keeping up**.
4. Measure allocation rate, live set, promotion, old occupancy, and humongous objects.
5. Change only a small group of flags with a clear hypothesis, comparing before/after.
6. Check request latency and throughput, not just the pause goal.
7. Keep the same workload and resource limits; avoid changing multiple variables at once.

## 21. Common Misconceptions When Learning the G1 Cycle

| Misconception | Correct understanding |
| --- | --- |
| "G1 divides the heap into Eden/Survivor/Old as three fixed address ranges." | G1 uses equal-sized regions, assigning logical roles that can change. |
| "Normal Young GC also collects old regions." | Normal young collection mainly evacuates the young CSet; old regions are placed into a selected mixed CSet in another phase. |
| "Concurrent Start pause runs concurrently with the application." | It is an **STW young pause** that initiates concurrent marking. |
| "Concurrent marking copies old objects to another area." | Marking measures liveness; evacuating selected old regions happens during mixed pauses. |
| "G1 has no STW because it has concurrent mark." | Young/mixed/remark/cleanup have STW pauses. |
| "Remark and Cleanup are both Mixed GC." | They are separate steps of marking/transition. |
| "Every marking cycle must have mixed GC." | No; depends on old-region candidates, reclaimable space, and policy. |
| "Mixed collects the entire old generation." | Mixed only adds **a portion of selected old regions** to the CSet. |
| "Mixed GC runs concurrently with mutators." | Evacuating the CSet in mixed is **STW** in JDK 17 G1. |
| "G1MixedGCCountTarget=8 means strictly 8 mixed collections." | It is a target/heuristic, not a fixed count. |
| "IHOP is always 45% of the whole heap on every JDK." | JDK 17 has Adaptive IHOP and models the threshold based on old-gen occupancy. |
| "G1HeapWastePercent 5 means always leaving exactly 5% dead objects." | It is a policy threshold for old-reclamation benefit, not a heap invariant. |
| "A 90% live region will definitely be selected for mixed." | High live occupancy may make a region ineligible or cost more work than benefit. |
| "Every Young GC definitely promotes a fixed percentage of objects." | Promotion depends on age, survivor sizing, and heap state. |
| "Humongous objects are evacuated like small arrays." | G1 handles humongous specially, generally not moving them like ordinary evacuated regions. |
| "A 1-second elapsed GC cycle means the application stopped for 1 second." | Concurrent phase elapsed time differs from STW pause. |
| "`MaxGCPauseMillis` is a hard SLA." | It is a soft pause goal, not a guarantee. |
| "G1 will never do a Full GC." | Full GC fallback can happen under memory pressure. |
| "Enabling more GC workers always makes it faster." | CPU, overhead, memory bandwidth, and cgroup quotas limit effectiveness. |
| "GC logs of two JVMs must have the same event count." | GC ergonomics/timings are not fixed by the Java Specification. |

## 22. Self-Check Exercises with Answers

**Q1.** What does G1 do during a Normal Young GC?

**Answer:** Evacuates live objects from the young collection set during an STW pause using GC workers, moves survivors/promotions to destination regions, and reclaims source young regions.

**Q2.** Is Young GC necessarily concurrent with the application because it uses multiple GC workers?

**Answer:** No. Multiple workers can run in parallel during **STW**, while mutators are stopped.

**Q3.** Does Concurrent Start mean old regions are mixed-evacuated immediately?

**Answer:** Not yet. It is a young pause with initial-mark work, starting concurrent marking to determine old liveness before selecting candidates.

**Q4.** While concurrent marking runs alongside mutators, what mechanism does G1 rely on to handle reference updates?

**Answer:** A family of mechanisms involving SATB marking/write barriers and metadata structures, according to G1's specific algorithm.

**Q5.** Is Remark STW or concurrent?

**Answer:** Remark is an **STW pause** used to finalize marking and related processing activities.

**Q6.** Does Cleanup always lead to Mixed GC?

**Answer:** No. G1 may conclude there are not enough reclaimable old regions worth collecting, and thus return to young-only.

**Q7.** How does Prepare Mixed differ from Mixed GC?

**Answer:** Prepare Mixed is a transitional young collection when G1 is about to enter the space-reclamation phase; Mixed GC actually has young + selected old regions in the CSet.

**Q8.** Why does G1 prioritize old regions with fewer live bytes?

**Answer:** Because they have more reclaimable garbage relative to the cost of copying live data, making them more efficient to reclaim.

**Q9.** Does mixed evacuation run concurrently with mutators on HotSpot G1 JDK 17?

**Answer:** No. It is an **STW evacuation pause**, even though multiple GC workers can run in parallel.

**Q10.** Why doesn't marking itself reclaim all old regions?

**Answer:** Marking identifies liveness/candidates. Old regions with remaining live objects must be reclaimed by moving live data in appropriate eviction/evacuation steps.

**Q11.** Does `G1MixedGCCountTarget=8` guarantee exactly eight Mixed GCs per cycle?

**Answer:** No. It is a policy target; the actual count depends on candidates, pause predictions, and heap state.

**Q12.** Why can young STW pauses still appear while the application is running during concurrent mark?

**Answer:** Young allocations continue to happen; young collections can interleave while concurrent marking is not yet complete.

**Q13.** What does G1 use remembered sets for?

**Answer:** Tracking necessary cross-region references, allowing selected regions to be collected without scanning the entire heap every time.

**Q14.** If an object is larger than half a region, what does G1 call it?

**Answer:** *Humongous object* (on HotSpot G1 JDK 17, threshold is greater than or equal to half a region), with special allocation/reclamation.

**Q15.** What can an evacuation failure lead to?

**Answer:** G1 lacks sufficient destination space to copy some live objects; the collector handles the failure, which can increase GC cost, and if memory pressure persists it can lead to Full GC/OOME.

**Q16.** Can a line `Concurrent Mark Cycle 500ms` be treated as a 500ms pause?

**Answer:** No. Elapsed time of concurrent work must be separated from individual STW pauses.

**Q17.** Why does the Java example produce the same checksum but different GC logs across runs?

**Answer:** Java semantics mandate consistent logical results, whereas heuristics/timing/number of GC events depend on the collector and environment.

**Q18.** When can mixed collections start without prior normal concurrent marking?

**Answer:** In the normal JDK 17 G1 path, old candidates for mixed require liveness information prepared by a concurrent cycle; other special/fallback GC paths **should not be mislabeled as a normal mixed phase**.

**Q19.** If G1 Full GC appears frequently, what should be checked first?

**Answer:** Heap pressure, live-set size, humongous allocations, marking start, promotion/evacuation headroom, and leaks before just changing a random flag.

**Q20.** Why can lowering `MaxGCPauseMillis` too much reduce throughput?

**Answer:** An overly tight pause goal can cause G1 to organize smaller/more frequent collections and increase GC overhead; the real workload must be measured.

## 23. Checklist for Reading the G1 Cycle on a Real System

1. Confirm the runtime is actually using G1 via startup logs/flags.
2. Record JDK build, `-Xms`, `-Xmx`, CPU quota, and region size.
3. Classify GC events into **Normal Young**, **Concurrent Start**, **Remark**, **Cleanup**, **Prepare Mixed**, and **Mixed**.
4. Distinguish **STW pause duration** from **concurrent phase elapsed time**.
5. Track old occupancy/IHOP and when marking starts.
6. Check young pauses interleaved during concurrent marking.
7. Inspect candidate old regions and the amount of memory reclaimed in the mixed phase.
8. Monitor pause p95/p99/max as well as application request latency p99.
9. Check CPU usage of concurrent GC workers and mutators.
10. Inspect live bytes, survivor/promotion, and to-space headroom.
11. Look for humongous allocations if there are long pauses or early marking.
12. Investigate evacuation failure and Full GC fallback rather than treating them as normal mixed steps.
13. Do not assert that mixed must appear in every program run.
14. Document custom flags; if there is no need, use ergonomic defaults first.
15. When benchmarking, fix the workload, heap/JDK, CPU limits, and repeat across multiple runs.

### Summary and Quick-Reference Diagram

```text
NORMAL YOUNG GC      : STW; evacuate young; may promote to old
CONCURRENT START     : Young STW pause initiating marking
CONCURRENT MARKING   : marks old liveness while mutators keep running
REMARK               : STW; finalizes marking, reference/class processing
CLEANUP              : STW; evaluates and finalizes old-region candidates
PREPARE MIXED        : Transitional Young GC, if preparing to enter mixed phase
MIXED GC             : STW; evacuates young + selected old regions
BACK TO YOUNG-ONLY   : finishes worthwhile old reclamation

WARNING:
- Not every cycle has all events.
- G1 has both parallel STW workers and concurrent marking workers.
- Mixed GC is not Full GC and does not process every old region.
```

**Core message:** G1 collects young regions frequently, marks old liveness mostly **concurrently with the application**, and then, if beneficial, includes **a portion of old regions** in **STW mixed evacuations**. Understanding these phase transitions helps read GC logs, explain pause times, and choose tuning directions without equating marking with reclamation.

### Official Documentation

- [Oracle JDK 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): Young-Only, Concurrent Start, Remark, Cleanup, Prepare Mixed, and Space-Reclamation phases.
- [Oracle JDK 17 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector-tuning.html): pause goals, log analysis, and common performance issues.
- [Oracle JDK 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): HotSpot GC options and Unified Logging.
- [Oracle JDK 17 — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): choosing Serial, Parallel, G1, ZGC by workload.
- [OpenJDK JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248): G1 is the default server-class GC in appropriate HotSpot configurations since JDK 9.
- [OpenJDK JEP 156 — G1 GC: Reduce contention in remembered set maintenance](https://openjdk.org/jeps/156): engineering perspective on remembered sets.
- [JVMS 2.5.3 — Heap (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): JVM specifies automatic storage management without mandating a specific collector.
