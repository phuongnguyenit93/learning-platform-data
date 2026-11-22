# G1: region-based heap and collection set selection

## 1. The problem G1 aims to solve

**Garbage-First Garbage Collector (G1 GC)** is a garbage collector in HotSpot aimed at balancing **throughput** and **pause-time goals** for large heaps or workloads requiring good pause-time predictability. Instead of treating the heap as a few large contiguous physical ranges and selecting an entire range each time, G1 **divides the Java heap into many equal-sized regions**. Regions can be assigned roles such as Eden, Survivor, Old, Humongous, or Free, and are then managed across collection cycles.

The name **Garbage-First** suggests its priority: when Old needs to be reclaimed, the collector evaluates **regions with high reclamation efficiency** — a lot of memory that can be reclaimed relative to the cost of processing them — and then selects a **collection set (CSet)** that fits the pause-time goal.

This article distinguishes:

1. **Heap regions** (units of organization/allocation/reclamation) from **objects** (application objects) and **Java generations** (Young/Old management roles).
2. **Collection set (CSet)**: the set of source regions selected for **evacuation/reclamation** in a GC pause.
3. **Young-only collections** and **mixed collections**: when the CSet contains Young, and when Old candidates are added.
4. **Concurrent marking**, region liveness, and the mechanism for selecting **Old collection-set candidates** based on efficiency, reference connectivity, and predicted pause time.
5. **Remembered sets (RSets)** and **write barriers**: why G1 can collect a subset of regions without rescanning the entire heap in every pause.
6. **Humongous regions**, evacuation failure, Full GC fallback, logging, and caveats when reading region counts.
7. A **runnable Java 17+ example**, with deterministic stdout while GC logs/region counts depend on runtime reality.

**Important caveat:** G1 is a specific collector of **HotSpot/OpenJDK**. JVMS `2.5.3 only requires a heap for class instances/arrays and automatic storage management; it does not mandate every JVM to use G1, region size, or the CSet algorithm.

## 2. Heap regions: dividing the heap into many equal regions

The Oracle JDK 25 G1 guide describes the heap as partitioned into **uniformly sized regions**, each being a contiguous range of **virtual memory**. Regions are the basic units G1 uses to manage allocation/reclamation.

~~~text
An illustrative heap divided into 12 equal regions:

+------+--------+--------+------+----------+-------+
| E    | Old    | Free   | S    | E        | Old   |
+------+--------+--------+------+----------+-------+
| E    | H-start| H-cont | Free | Survivor | Old   |
+------+--------+--------+------+----------+-------+

E      = Eden region
S      = Survivor region
Old    = Old region
H      = Humongous sequence (very large object)
Free   = Region not currently assigned to an active allocation
~~~

All cells represent **the same amount of virtual memory addresses** at the region level; in a text diagram, cell width does not necessarily represent exact scale.

### Key characteristics to remember

- A region can be assigned the role of **Eden**, **Survivor**, **Old**, **Humongous**, or be **free**, depending on collector state.
- **Young generation** consists of **Eden and Survivor regions**; **Old generation** consists of Old regions and appropriate special classifications.
- Eden/Survivor/Old regions **do not need to be contiguous** in address space. G1 can still treat scattered regions as one young generation logically.
- **Region size is equal within a specific G1 heap**; this does not mean every G1 process uses the same region size.
- **A region's role is not necessarily fixed for the lifetime of the process**: once freed, a free region can be reassigned as needed.
- A region **is not an object**: it can contain many small objects, or be part of a Humongous sequence.

### Region size

HotSpot has the `-XX:G1HeapRegionSize=...` option. Oracle JDK 25 describes G1 choosing the size ergonomically from the maximum heap, aiming for around **2,048 regions** under normal conditions, with version-dependent valid size constraints. **Do not memorize a single region size number as a JVM truth.**

Configuration example:

~~~bash
java -Xms256m -Xmx256m -XX:+UseG1GC -Xlog:gc+init=info MyApplication
~~~

`MyApplication` is a **sample** name and must be replaced with a real application class. Initialization logging may record **Heap Region Size** depending on version/tag. To check the region size and available flags, use `java -Xlog:help` and `java -XX:+PrintFlagsFinal -version` on the running JVM.

**Do not manually set `G1HeapRegionSize` to "speed things up" without checking** its impact on region count, remembered set granularity, waste, humongous threshold, and pause behavior.

## 3. A region is not a generation and CSet is not the whole heap

Three distinct concepts:

| Concept | Unit/meaning | Example |
| --- | --- | --- |
| **Region** | A uniformly sized unit of heap memory | Region 17 |
| **Generation** | Logical group of regions based on role/age | Eden + Survivor is Young |
| **Collection set (CSet)** | **Set of source regions** selected by G1 for a collection pause | 10 Eden, 2 Survivor, 3 Old in mixed GC |

A GC pause **does not** mean the entire Java heap is in the CSet. For G1, a **young-only CSet** focuses on young regions; whereas a **mixed CSet** contains Young and a selected set of Old regions.

~~~text
Current heap:
 [E1][E2][S1][O1][O2][O3][O4][FREE][FREE][H1]

Young-only CSet:  {E1, E2, S1}
Mixed CSet:       {E1, E2, S1, O2, O4}  (illustrative example)
Not in CSet:      O1, O3, H1, Free ...
~~~

**The sets above are hypothetical examples**, not specific G1 decisions. Humongous regions have their own reclamation handling and usually **do not move like normal regions**; do not interpret not being in the CSet as never being reclaimed by GC.

## 4. Evacuation: collecting selected regions by moving live objects

For regions that can be evacuated, G1 uses **copying/evacuation**: identifying **live objects** in source regions, copying them to appropriate destination regions, and updating necessary references. Once properly processed, the source regions can be freed for reuse.

~~~text
Before G1 evacuation:

CSet source region R1
+-----------------------------------+
| A live | B dead | C live | D dead |
+-----------------------------------+

Destination region(s):
+-----------------------------------+
| A' live | C' live |    free ...   |
+-----------------------------------+

After references updated:
- References to A point to A'
- References to C point to C'
- R1 can become a free region
- B and D do not need to be copied
~~~

**This is a conceptual diagram.** The Java program still observes correct object identities; GC can change an object's physical location without breaking `a == b` or hash/field semantics. Memory barriers, forwarding metadata, and root updates are handled by HotSpot, not by assignments you have to write in Java source code.

### Where do objects from different sources go?

According to the Oracle JDK 25 G1 guide:

- **Eden/Survivor live objects** can be moved to **Survivor or Old**, depending on age/promotion policy.
- **Old live objects** are evacuated from an Old region to an **Old destination region**.
- **Humongous objects** have special handling; G1 normally does not move them via evacuation like small objects, but determines liveness and reclaims them when no longer live through an appropriate mechanism.

**Evacuation does not mean keeping only objects whose fields were recently read.** GC determines liveness by reachability and runtime semantics, not based on application object timestamps.

## 5. Why is a collection set needed?

You cannot simply pick an arbitrary old region and copy objects out of it while ignoring references pointing to it from thread stacks, static fields, code roots, or objects in other regions. The collector must have a defined set of sources along with root/reference information to ensure the entire object graph remains valid.

G1 uses **CSet** to decide:

1. Which regions to consider/reclaim in the current collection.
2. Which objects are still live in those regions.
3. Which roots and **incoming references from outside the CSet** must be updated when live objects move.
4. Whether the predicted pause time fits within the pause target and collector constraints.
5. When to spend time on additional **Old candidate regions** rather than making the pause too long.

The collection set allows G1 to do work **in groups of regions**, instead of collecting the entire heap on every pause.

### CSet is the set of source regions, not where objects are copied to

In the source-oriented collection model:

~~~text
CSet (source):  E1, E2, S1, O3
                 |      |
                 v      v
Destination:    New/appropriate Survivor and Old regions

Result: source regions can be reclaimed (if evacuation succeeds),
destination regions continue to hold live objects.
~~~

**Do not call a destination region "a region in the CSet to be collected" just because objects were just moved into it.** In G1 documentation, CSet refers only to the source regions currently selected for evacuation/reclamation.

## 6. Collecting Young first: Young-only collection

Because most new objects have short lifetimes, G1 typically performs **young-only GC pauses**. Young regions include Eden and Survivor belonging to the current young generation.

Conceptually, a cycle may proceed as:

1. The application allocates objects, using Eden regions/TLABs per the allocator.
2. Eden resources approach a threshold, and the VM starts a Young GC according to appropriate scheduling.
3. G1 pauses application threads at a Stop-the-World phase.
4. Collects roots and **incoming references to the young collection set**.
5. Copies/evacuates live young objects to Survivor or Old based on age.
6. Frees the corresponding source Eden/Survivor regions and updates regions for further allocation.
7. Resumes the program.

~~~text
Young collection:
  CSet = all Young regions eligible for that collection

  Eden A      -> dead: reclaim, live: Survivor/Old
  Eden B      -> dead: reclaim, live: Survivor/Old
  Survivor C  -> live: Survivor/Old, dead: reclaim

  Old regions are normally not in the CSet of a young-only pause.
~~~

**Young-only GC does not remove all unreachable objects in Old.** Old regions may contain garbage, which will be reclaimed in appropriate phases. Therefore, after a young pause, heap/old occupancy does not necessarily drop to its lowest level.

### G1 adjusts Young size according to pause goals

The Young size (number of Eden/Survivor regions) can be **automatically adjusted** by G1 based on allocation rate, live bytes, evacuation cost, and pause-time prediction. This creates a trade-off:

- Larger Young: usually reduces young GC frequency, but each pause may need to process more live data.
- Smaller Young: may yield shorter pauses, but usually requires more frequent GCs.
- Survivor pressure: many live young objects can cause early promotion, filling Old quickly.

Do not force Young size using flags from Java 8 experience without knowing the current collector/Java version.

## 7. From Young-only to Space-Reclamation/Mixed phase

G1 does not only clean up Young. When Old occupancy and heap state indicate that significant memory needs to be reclaimed in Old, G1 can start **concurrent marking** to find Old regions with low live data that can be reclaimed efficiently.

According to the Oracle JDK 25 G1 guide, a major cycle consists of:

~~~text
Young-Only Phase
  |
  +-- Regular Young GCs
  |
  +-- Concurrent Start young collection
  |      starts concurrent marking
  |
  +-- Concurrent marking work (mostly while app is running)
  |
  +-- Remark pause (completes marking/reference processing)
  |
  +-- Cleanup pause (evaluates candidate regions)
  |
  +-- Prepare Mixed young collection (when appropriate)
  v
Space-Reclamation Phase
  |
  +-- Mixed Collection 1: Young + a portion of Old candidates
  +-- Mixed Collection 2: Young + additional Old candidates
  +-- ...
  |
  +-- Ends when no sufficiently efficient candidates remain or policy stops
  v
Return to Young-Only Phase
~~~

The diagram is a logical overview for learning; the number and names of pauses depend on the version and VM state. G1 may use a Full GC fallback when reclamation progress is insufficient or allocation cannot proceed under required conditions.

### What information does concurrent marking determine?

- **Live data** in Old regions.
- Regions with **a lot of reclaimable space** if evacuated.
- Reachability/connectivity information needed for efficiency evaluation.
- Candidates for the upcoming mixed collections.

**Concurrent** does not mean the entire cycle has no Stop-the-World pauses. G1 still has **Remark, Cleanup, and Evacuation pauses** along with other components; concurrent marking only means certain phases work concurrently while the application runs.

### Snapshot-at-the-Beginning (SATB)

During marking, G1 uses the **SATB** technique to preserve the correctness of a logical reachability snapshot. Reference changes while mutators run are recorded via barriers and appropriate collector processing. Therefore, concurrent marking should not be described as a "frozen" graph traversal that needs no updates.

**SATB marking and remembered-set maintenance have different responsibilities**, even though both involve GC barriers: one serves the marking snapshot, while the other helps find incoming references/heap roots for the collection set.

## 8. Selecting Old regions: what does "Garbage-First" really mean?

This is the core point of the topic: after marking, G1 has data to estimate the **reclamation efficiency** of Old regions. A region with many reclaimable bytes and little live data/cross-region work is usually more worth selecting than a region nearly full of live objects.

G1 selects **Old collection-set candidate regions** based on predicted benefit, taking into account:

- **Reclaimable bytes/space**: the amount of memory that can be reclaimed.
- **Live occupancy**: more live bytes to evacuate generally increases copy cost.
- **Connectivity/cross-region references**: many incoming references can increase remembered-set/heap-root processing.
- **Predicted pause time**: whether the total required Young work and predicted Old candidates fit the pause goal.
- **Minimum/optional heuristics** to ensure progress and limit overhead.

In Oracle JDK 25 documentation, candidates with less live data and lower connectivity are prioritized over nearly full candidates or those with high scan cost. G1 does not necessarily pick **the region with the most absolute garbage bytes while ignoring cost**.

### Old region comparison example (hypothetical, not a HotSpot formula)

Suppose each region is 8 MiB:

| Old region | Live | Reclaimable | Predicted evacuation cost | Assessment |
| --- | ---: | ---: | ---: | --- |
| A | 1 MiB | 7 MiB | 2 ms | Very promising |
| B | 6.5 MiB | 1.5 MiB | 8 ms | Less efficient |
| C | 2 MiB | 6 MiB | 3 ms | Promising |
| D | 7.5 MiB | 0.5 MiB | 12 ms | Usually unattractive |

These figures are **made up by the lesson**, not specific G1 data, and actual cost does not depend solely on live bytes. Conceptually: regions A/C provide more reclaimable bytes at lower cost than B/D, so they align better with the garbage-first spirit.

**The algorithm is not simply "sort a table by garbage/live and take the top K"**. Oracle JDK 25 describes candidates having mandatory/optional classifications, pause predictions, and space-reclamation phase policies; the collector also considers limits and the number of regions to process per pause.

## 9. How is the CSet built in Mixed GC?

A **mixed collection** is a young collection **that also adds a number of Old regions** evaluated as candidates.

~~~text
Young regions (mandatory per young collection):
  E1 E2 E3 S1 S2

Old candidate regions after concurrent marking:
  O7 O9 O14 O16 O21 ...

Example of a Mixed CSet:
  {E1, E2, E3, S1, S2, O7, O14}

Remaining Old regions may be saved for later mixed pauses
or not selected if cost/reclaim efficiency is not worthwhile.
~~~

Policy-level steps in JDK 25:

1. **Select Young regions** according to young collection policy.
2. **Calculate remaining predicted time budget** in the pause after Young work and fixed/base costs.
3. **Select minimum (mandatory) Old candidates** to guarantee space-reclamation progress, distributing work based on settings like `G1MixedGCCountTarget`.
4. **Add additional Old candidates when predicted time remains**, potentially using **optional candidates** to utilize the remaining margin.
5. **Stop adding** if predictions indicate it will no longer fit the time budget or other efficiency/reclamation policy criteria do not allow it.

According to the Oracle guide, G1 has an **initial pass** mechanism and additional passes for **optional old regions** if predicted pause time remains. Thus, CSet selection is a benefit/cost problem under a pause budget, not a command to "GC all of Old".

### The pause goal is a soft target

HotSpot provides `-XX:MaxGCPauseMillis=...` to **set a target** for G1. This is **not an absolute deadline** for every GC pause. Certain situations such as an unusual live-set spike, many references, allocation pressure, or evacuation failure can still cause pauses to exceed the target.

Example:

~~~bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 MyApplication
~~~

The command is a **sample** and cannot run without `MyApplication.class`. The value `200` here is a 200 ms target, **not a promise to "never pause for more than 200 ms"**.

## 10. An example table of CSet selection under a pause budget

Imagine G1 has a 40 ms pause target, and Young work + fixed costs are predicted to need 20 ms; about 20 ms remains for Old candidates. The following numbers are **purely hypothetical for learning**, not reflecting G1's actual formulas/interpolation:

| Candidate | Reclaimable memory | Estimated cost |
| --- | ---: | ---: |
| Old A | 8 MiB | 7 ms |
| Old B | 3 MiB | 4 ms |
| Old C | 9 MiB | 13 ms |
| Old D | 0.5 MiB | 6 ms |

One hypothetical choice is **A+B = 11 MiB reclaimed for 11 ms**, which may leave budget for some other work; **A+C = 17 MiB for 20 ms** hits the remaining limit. Which combination is chosen also depends on **mandatory candidates, connectivity, prediction uncertainty, and policy**, rather than simply optimizing a knapsack problem on these exact numbers.

The lesson does not require you to implement HotSpot's exact CSet selection algorithm. What to remember is that G1 tries to **maximize reclaim benefit within the predicted pause budget**, using multiple criteria rather than just ranking regions by raw garbage amount.

## 11. Remembered sets: finding references from outside the CSet

Suppose G1 evacuates region R, while an Old object in region S (not in the CSet) still has a field pointing to object X in R:

~~~text
Region S (outside CSet)               Region R (in CSet)
+----------------------+              +----------------------+
| OtherObject          | -----------> | X (live object)      |
+----------------------+              +----------------------+

Evacuation:
  X is copied to X' in a destination region.
  The reference in S must be updated to point to X'.
~~~

If the collector ignores **incoming references from outside the CSet**, it could miss live objects or leave invalid references after a moving GC. Scanning the entire heap on every partial collection would defeat the purpose of selecting a small set of regions.

A **Remembered set (RSet)** stores information about **external locations that have references pointing into the CSet/regions**. Oracle JDK 25 describes RSet entries in terms of **cards**, which are small logical areas of the heap (typically 512 bytes by default depending on version), rather than one entry per individual pointer.

### Granularity and trade-offs

- Card-based representation reduces memory overhead.
- An RSet entry for a region/card can be **approximate**, requiring inspection of actual references within the area.
- Merging/deduplicating entries helps reduce root scanning work.
- RSets must be updated or rebuilt via barriers/refinement/rebuild depending on phase.
- The larger the CSet or the higher the connectivity, the more work processing incoming references may take.

**RSets are not a Java `Set`, and they are not the set of all live objects.** They are internal metadata supporting the correctness and efficiency of **partial region collection**.

### Merge Heap Roots

Oracle JDK 25 describes that during a GC pause, G1 has a **Merge Heap Roots** phase to create a unified set of incoming heap roots for the CSet from remembered-set information, remove duplicates, and prepare for parallel evacuation work.

An outline of a pause cycle:

~~~text
Pre Evacuate Collection Set
    |
    v
Merge Heap Roots
    |
    v
Evacuate Collection Set
    |
    v
Post Evacuate Collection Set / Other work
    |
    v
Mutators resume running
~~~

Phase names may vary by release/logger, but the core functions remain the same: **select regions**, **identify roots/incoming references**, **copy live objects**, and then **complete post-processing**.

## 12. Humongous objects: an important exception

G1 calls a very large object **humongous** when its size reaches a threshold relative to the region size (in typical G1 releases, an object larger than **half a region size** takes the humongous allocation path).

Instead of sitting inside a regular Eden region, a humongous object typically occupies one or more **contiguous regions**:

~~~text
Hypothetical region size: 8 MiB

Array object of about 18 MiB:
+----------------+----------------+----------------+
| Humongous start| Humongous cont | Humongous cont |
|     object =====================================      |
+----------------+----------------+----------------+

These regions are tied to the large object's allocation sequence.
~~~

**The 8/18 MiB figures are illustrative.** Actual object layout includes headers/alignment and GC size calculations; do not use hypothetical numbers to assert the exact real region count from an array length.

### Why are humongous objects different?

- G1 usually **does not evacuate/move** humongous objects in the normal way.
- An object can hold unused space at the end of the last region in the sequence until the object is reclaimed, leading to internal fragmentation.
- Humongous allocations can accelerate the need for concurrent marking or GC depending on occupancy.
- Some humongous objects, especially primitive arrays under supported conditions, can be **eagerly reclaimed** according to G1 policy.

**Do not conclude that "humongous objects are immortal"**, nor say that "all humongous objects must wait for Full GC". Oracle's guide documents reclamation mechanisms outside Full GC depending on the object and GC phase.

## 13. Evacuation failure and Full GC fallback

A planned mixed/young collection needs somewhere to copy live objects. If G1 cannot find enough destination space or encounters another collector-specific condition, an **evacuation failure** can occur.

Consequences may include:

- Not all planned source regions are successfully evacuated.
- G1 must use recovery/failure-handling mechanisms to preserve object correctness.
- It can cause longer pauses, increased old regions, or force G1 to use heavier collection methods.
- In severe situations, a stop-the-world **Full GC** may be used as a fallback to compact/recover memory.

**Do not say "every evacuation failure = immediate OOME".** OOME occurs when the VM cannot satisfy an allocation request after valid mechanisms; the collector may recover or collect further.

### Why is reserve/to-space headroom needed?

If the CSet has many live objects, destination regions need enough room. G1 can reserve some headroom per policy to reduce the risk of failing to evacuate during a pause. During tuning, nearly full old occupancy, a very large live-set, or humongous allocations can worsen the problem.

Flags for heap reserve/occupancy are **implementation tuning knobs**, not something you must tweak to explain CSet selection principles; check the documentation for the running version before changing them.

## 14. Java 17+ program: creating young garbage and retaining some objects

The lab does not try to "command" G1 to pick specific regions — Java code **has no API to select the CSet**. Instead, it creates a workload with temporary objects and a retained group, then observes HotSpot's GC logs.

Create the file **`G1RegionLab.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class G1RegionLab {
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile Object latest;

    public static void main(String[] args) {
        for (int i = 0; i < 12; i++) {
            byte[] block = new byte[8192];
            block[0] = (byte) i;
            RETAINED.add(block);
        }

        int count = 0;
        for (int batch = 0; batch < 12; batch++) {
            for (int i = 0; i < 10_000; i++) {
                byte[] temporary = new byte[512];
                temporary[0] = (byte) i;
                latest = temporary;
                count++;
            }
        }

        latest = null;

        System.out.println("temporary-count=" + count);
        System.out.println("retained-count=" + RETAINED.size());
        System.out.println("retained-size=" + RETAINED.get(0).length);

        RETAINED.clear();
        System.out.println("after-clear=" + RETAINED.size());
        System.out.println("gc-regions-are-runtime-dependent");
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -g G1RegionLab.java
java G1RegionLab
~~~

**Deterministic stdout if the program completes normally:**

~~~text
temporary-count=120000
retained-count=12
retained-size=8192
after-clear=0
gc-regions-are-runtime-dependent
~~~

**Explanation:**

- `12 × 10_000 = 120_000` temporary arrays in the loop.
- `RETAINED` holds 12 arrays, each 8192 bytes.
- `RETAINED.clear()` empties the list, **and does not force the garbage collector to run immediately**.
- `latest` is a volatile field that creates a reference path with an observable effect during execution, though the output cannot be used to verify individual allocation paths or specific region locations.
- There is no thread scheduling race in stdout because only the main thread prints.
- Multiple Young collections may occur in a single run and vary between runs, depending on heap/JVM/collector. **There is no fixed number of GCs that must appear.**

### Running with G1 and GC logging

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc=info G1RegionLab
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc+heap=info G1RegionLab
~~~

Total temporary allocation in the code can exceed 64 MiB over time, **which does not mean 64 MiB of live objects exist simultaneously**. The collector can reclaim unreachable objects to continue allocating. If the environment is constrained or JVM/OS differs, use a larger heap or test a smaller workload; **do not try to force an OutOfMemoryError**.

**GC logs do not have fixed exact stdout.** GC timing, pause reasons, region counts, timings, and byte counts depend on runtime state. Only the five output lines of `G1RegionLab` are deterministic upon normal completion.

## 15. Reading G1 logs: how to look at region counts and CSet

HotSpot unified logging has tags such as `gc`, `gc+heap`, `gc+ergo+cset`. Use `java -Xlog:help` to check supported tags/levels.

~~~bash
java -Xlog:help
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info G1RegionLab
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc+ergo+cset=debug G1RegionLab
~~~

### Sample logs for regions

Oracle JDK 25 docs show G1 log examples with `Eden regions`, `Survivor regions`, `Old regions`. A **hypothetical sample for explanation**, not this program's output:

~~~text
[gc,heap] GC(12) Eden regions: 20->0(15)
[gc,heap] GC(12) Survivor regions: 2->4(5)
[gc,heap] GC(12) Old regions: 10->11
[gc]      GC(12) Pause Young (Normal) (G1 Evacuation Pause) ...
~~~

Reading it:

- `Eden regions: 20->0(15)`: the number of Eden regions changed across GC along with the related target value. It does not mean only 20 Java objects were created.
- `Survivor regions: 2->4(5)`: the number of regions with the Survivor role changed.
- `Old regions: 10->11`: the number of Old regions increased by one, **not that one object** was promoted.
- `Pause Young`: cleans up Young; **not synonymous with Full GC**.

With a small workload, you may **not see any Mixed GC**. G1 only enters the space-reclamation/mixed phase when marking and policy require it; do not invent a fixed "expected mixed GC count" for the sample Java file.

### CSet decision logs

According to the Oracle JDK 25 tuning guide, the `gc+ergo+cset=debug` tag can provide:

- Predicted **Young/Eden time** and **base time** in the pause.
- Predicted time for **initial/optional** Old candidates.
- Selection of the number of Old regions into the CSet during mixed collections.

Example of a log line pattern (only to illustrate structure, **not predicted output**):

~~~text
[gc,ergo,cset] Added young regions to CSet ... predicted eden time: ... target pause time: ...
[gc,ergo,cset] Finish choosing collection set old regions ... predicted initial time: ...
~~~

**Do not believe that the log lists a specific object that was moved.** `gc+ergo+cset` is collector ergonomics/decision logging at the region/CSet prediction level; object-level movements are not fully presented by these few lines.

## 16. G1 pause goal, heap sizing, and notable flags

| Flag (HotSpot) | General meaning | Caveat |
| --- | --- | --- |
| `-XX:+UseG1GC` | Selects the G1 Collector | Use only when supported by the JVM |
| `-XX:MaxGCPauseMillis=N` | Sets a **soft goal** for pause duration | Does not guarantee every pause ≤ N ms |
| `-XX:G1HeapRegionSize=...` | Selects a valid region size | Affects region count, humongous threshold, and overhead |
| `-XX:G1MixedGCCountTarget=...` | Influences the target distribution of old candidates across multiple mixed GCs | Does not dictate the exact number of mixed pauses |
| `-XX:G1MixedGCLiveThresholdPercent=...` | Occupancy condition for considering old regions in the space-reclamation phase | Raising/lowering trades off cost vs reclaim |
| `-XX:G1HeapWastePercent=...` | Policy to evaluate whether it is still worth reclaiming Old space | Not an "object leak rate" |
| `-XX:G1NewSizePercent`/`G1MaxNewSizePercent` | Limits for policy-based Young adjustment | Should not be fixed if ergonomics work well |
| `-XX:+G1UseAdaptiveIHOP` | Adaptive initiating occupancy heuristic for marking | Relates to when marking starts, does not directly select CSet |
| `-Xlog:gc+ergo+cset=debug` | Logging of G1 building the CSet | Content depends on JDK version/GC events |

**Do not treat default values as invariant across releases.** Oracle JDK 25 docs have a flags table for that exact version; other HotSpot/JDK builds may differ. Check in practice with:

~~~bash
java -XX:+PrintFlagsFinal -version
java -Xlog:help
~~~

A rule of thumb: with G1, usually **start with heap size, pause goal, and workload measurements**; only intervene with intricate tuning flags when logs show the cause. Guessing optimizations easily reduces throughput or increases other pauses.

## 17. When Mixed GC is too slow: where to investigate?

The Oracle JDK 25 tuning guide recommends comparing **predicted young time** versus **old-region contribution** in `gc+ergo+cset=debug`:

1. **If Young work dominates**, consider Young sizing and survival rate; do not blame Old candidates entirely.
2. **If Old contribution is large**, analyze old region occupancy/connectivity and the strategy for spreading work across multiple mixed collections.
3. **If Merge Heap Roots/Scan Heap Roots takes a lot of time**, check the cost of remembered sets/incoming cross-region references.
4. **If Object Copy is the bulk of the pause**, measure evacuated live bytes, survivor/promotion pressure, and collection-set size.
5. **If humongous allocations are frequent**, check array/object sizes and region-size trade-offs.
6. **If Full GC occurs**, investigate headroom/evacuation failure, Old live-set, allocation patterns, and heap policy before tweaking flags.

**Limitation:** tuning to reduce pauses may increase pause frequency or reduce throughput. You need to compare P95/P99 latency, throughput, allocation rate, live-set, and GC CPU under a consistent workload, not just one short pause.

## 18. Young-only, Mixed, and Full GC: common misconceptions

| Misconception | Correction |
| --- | --- |
| "G1 divides the heap into regions of different sizes by generation." | Regions are **equal in size within the heap**, though they have different roles. |
| "All Eden regions must be contiguous." | G1 regions can be scattered. |
| "Each region contains exactly one Java object." | A region usually contains many objects; humongous objects can span multiple regions. |
| "CSet is the entire heap." | CSet is the set of **selected source regions** for the current GC pause. |
| "Young-only CSet cleans up every Old region." | No; Young-only processes young regions. |
| "Mixed GC only collects Old, not Young." | Mixed CSet consists of **Young + a subset of Old candidates**. |
| "Garbage-first means the region with the most garbage bytes is always chosen." | It must also consider **live bytes, connectivity, efficiency, pause predictions, and policy**. |
| "All Old regions are collected in a single Mixed GC." | G1 selects a **subset** across multiple collections when appropriate. |
| "CSet selection is unrelated to pause time." | G1 uses pause-time predictions and a soft goal. |
| "`MaxGCPauseMillis=200` is a hard deadline." | It is a target; GC pauses can still exceed it. |
| "Concurrent marking means no STW." | G1 still has Remark/Cleanup/Evacuation pauses. |
| "G1 does not need to check refs from outside the CSet." | It must use roots/RSets to protect live objects and update references. |
| "RSet is a list of all live objects." | It serves **incoming reference locations**, not a heap census. |
| "An Old region with lots of garbage is guaranteed to be reclaimed immediately." | It requires marking/candidate evaluation and an appropriate collection. |
| "`Old regions: 10->11` means 1 object was promoted." | Logs count **regions**, not object count. |
| "Humongous objects always move like small objects." | G1 usually uses separate handling/reclamation and avoids moving them. |
| "Full GC happens in every mixed cycle." | It is a different path/fallback, not the regular default. |
| "A Java application calls an API to choose the CSet." | CSet is decided by HotSpot GC; there is no standard Java API for this. |
| "GC logs are identical on Java 8, 17, and 25." | Logging tags and G1 implementation change across versions. |
| "Simply lowering the pause target always makes the application faster." | There are trade-offs in throughput/frequency/overhead. |

## 19. Self-check questions (with answers)

**1.** What roles can a G1 heap region hold?  
**Answer:** Free, Eden, Survivor, Old, or a special humongous role per policy, and the role can change when the region is reclaimed/reassigned.

**2.** What is a CSet?  
**Answer:** The set of **source regions** G1 selects to process/evacuate in a collection pause; not the entire heap.

**3.** Does a Young-only CSet normally contain Old candidates?  
**Answer:** Not per young-only functionality; G1 may perform concurrent/metadata tasks outside evacuation as needed, but a young-only collection set is not a mixed Old evacuation set.

**4.** What regions does a Mixed CSet include?  
**Answer:** Young regions and a **subset of Old candidates** selected according to policy.

**5.** How does G1 know which Old regions are worth collecting?  
**Answer:** Concurrent marking and metadata on liveness/connectivity/reclaim efficiency; the collector also evaluates predicted pause costs.

**6.** If Object A in a region is evacuated, but an object outside the CSet points to A, what happens?  
**Answer:** G1 uses roots/remembered-set information to find the reference, keeps A live, copies it if needed, and updates the pointer to the new location.

**7.** Is an RSet a list of all objects in a region?  
**Answer:** No. It records relevant **incoming reference locations**, typically by cards.

**8.** Why doesn't G1 collect all Old candidates in a single pause?  
**Answer:** Because of the pause-time goal, predictions, reclaim-efficiency heuristics, mandatory/optional sets, and the policy of spreading work across multiple mixed collections.

**9.** Is the Old region with the largest reclaimable space always guaranteed to be chosen first?  
**Answer:** No. G1 considers multiple factors including copy/root costs and liveness/connectivity.

**10.** Does `-XX:MaxGCPauseMillis=100` guarantee every GC pauses for under 100 ms?  
**Answer:** No; this is a soft goal.

**11.** Is a humongous object always evacuated like a small object?  
**Answer:** No. G1 uses separate humongous allocation/reclamation and avoids moving them.

**12.** From `Old regions: 10->11`, can you conclude that exactly one object was promoted?  
**Answer:** No. A region holds many objects, and the collector log is not an object-level count.

**13.** Does a workload finishing `RETAINED.clear()` force G1 GC to run immediately?  
**Answer:** No. Losing references does not create a deadline for GC.

**14.** What flag can be used to study G1 CSet prediction in a supported HotSpot?  
**Answer:** Try `-Xlog:gc+ergo+cset=debug` and check `java -Xlog:help`; results depend on whether corresponding mixed/young events occur.

## 20. Official references

- [Oracle JDK 25 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): heap layout/regions, young-only vs space-reclamation, CSet, RSets, humongous allocations, GC process, and policy selection.
- [Oracle JDK 25 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): CSet candidate selection/pauses, tuning Young/Mixed/Old, `gc+ergo+cset`, and G1 parameters.
- [Oracle JDK 25 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-collector-implementation.html): examples of `Eden regions`, `Survivor regions`, `Old regions` statistics in GC logs.
- [Oracle JDK 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+UseG1GC`, `-XX:MaxGCPauseMillis`, unified GC logging.
- [Oracle JDK 25 — Heap Sizing](https://docs.oracle.com/en/java/javase/25/gctuning/heap-sizing.html): goals and how the VM adjusts heap regions.
- [JVMS Java SE 25 — 2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.3): abstract heap area, does not require a specific collector.
- [OpenJDK JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248): context on G1 becoming the default in HotSpot server configurations.
- [OpenJDK HotSpot G1 Sources](https://github.com/openjdk/jdk/tree/master/src/hotspot/share/gc/g1): G1 implementation code; the master branch may differ from the version in use.
- [OpenJDK JEP 318 — Epsilon: A No-Op Garbage Collector](https://openjdk.org/jeps/318): reminds us that the JVMS does not mandate GC generation structures like G1.

**Conclusion:** G1 divides the heap into **equal-sized regions**, assigns Young/Old/Humongous roles depending on state, and **does not require regions of the same generation to be contiguous**. In a pause, **the CSet identifies the source regions to collect**, with **Young regions** in young-only collections and adding **a subset of Old candidates** in mixed collections. "Garbage-first" means G1 tries to take advantage of regions with **high reclamation efficiency** within the **predicted pause budget**, based on concurrent marking, connectivity/remembered sets, and collector ergonomics — not always scanning the entire heap or picking regions solely by the largest garbage volume.