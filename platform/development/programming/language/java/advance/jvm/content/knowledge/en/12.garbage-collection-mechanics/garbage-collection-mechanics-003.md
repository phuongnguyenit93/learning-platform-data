# The Generational Hypothesis: Short-Lived Objects, Aging, and Promotion

## 1. Core idea: “most objects die young”

The **generational hypothesis** is an empirical observation across many types of programs: **most created objects have a short lifetime**, while a small fraction are kept for a very long time. We create iterators, temporary strings, request objects, buffers, or intermediate calculation results very frequently; many objects are no longer reachable after a brief operation. Objects such as application configuration, valid shared caches, sessions, or indexes can live very long.

**Generational garbage collection** uses this observation to partition heap management by relative lifetime:

1. **Young generation** is for new objects or objects that have not survived through many young GCs.
2. **Survivor** holds objects that are still reachable after a young GC to avoid moving everything to Old too early.
3. **Old generation** manages data that has lived long enough or has been moved there by collector policy.
4. **Promotion/tenuring** is the process of moving a surviving object from Young to Old.

The goal is to collect frequently where there is a lot of garbage and a relatively small amount of live data, instead of being forced to scan every object in the entire heap for every temporary allocation.

**To be clear:** this is a **strategy of garbage collectors**, not a hard requirement of the Java language or the JVMS that every JVM must have Eden, Survivor, and Old. **JVMS `2.5.3`** describes the heap for class instances/arrays and automatic memory management, while organizing generations depends on the VM and collector.

### A hypothesis, not a promise for every application

| Workload / object | Typical lifetime | Meaning for generational GC |
| --- | --- | --- |
| Temporary string/iterator | Very short | May die before the first young collection |
| Request-serving DTO | Short | Often has a high chance of being reclaimed in Young |
| Asynchronous task buffer | Medium | May survive through a few young collections |
| Some session/cache entries | Medium or long | May age and then be promoted |
| Configuration or shared registry | Long | May contribute to the old live-set |
| Unbounded cache holding stale data | Too long relative to actual need | May cause memory retention/old pressure |

These are examples of tendencies, **not rules of class names**. A `String` can also live for the entire lifetime of the program, while a `Session` object can die immediately.

## 2. Illustrating the lifetime distribution

~~~text
Number of objects with corresponding lifetime
  ^
  | #################
  | #################
  | ####################
  | ########################           ##
  | ################################ #######
  +---------------------------------------------------->
       very short             medium            very long
                             lifetime
~~~

This is a **qualitative illustration**, not a statistical chart of a specific application. The Oracle source on the *weak generational hypothesis* explains that most objects typically live only for a very short period, even though some workloads have significantly different distributions.

**“Dead” in GC terms means becoming no longer reachable according to the appropriate semantics**, not simply that Java source just ran `obj = null` or passed a `}`. If an object is still in a field, collection, task queue, or cache that is reachable, GC must still keep it. Conversely, as soon as an object becomes unreachable, GC does not necessarily run immediately.

## 3. Generational heap: Eden, Survivor, and Old

In the classic generational copying collector model:

~~~text
                    JAVA HEAP
+-------------------------------------------+--------------------+
| YOUNG GENERATION                          | OLD GENERATION     |
|                                           |                    |
| +---------------+ +----------+ +---------+| +----------------+ |
| | Eden          | | Survivor | |Survivor || | Long-lived /   | |
| | New objects   | | From     | |To       || | promoted objects| |
| +---------------+ +----------+ +---------+| +----------------+ |
+-------------------------------------------+--------------------+

new -> Eden
Young GC: dead -> reclaim; live -> Survivor or Old
Surviving multiple collections -> eligible for promotion -> Old
~~~

In traditional collectors that use two survivor spaces, they can swap **From/To** roles after GC. However, **not every object has to visit both Survivor spaces** and not every collector has exactly two contiguous Survivor blocks.

### G1 in HotSpot JDK 25

G1 is a case that needs to be distinguished from the old diagram. G1 divides the heap into **regions**, assigning roles such as Eden, Survivor, Old, or Humongous; regions of the same generation are **not required to be contiguous** in memory.

~~~text
Illustrative heap region sequence (not mandatory addresses):

[Old][Free][Eden][Survivor][Eden][Old][Humongous][Survivor]
           \        |        /
                  YOUNG
~~~

According to the **Oracle JDK 25 G1 guide**, surviving young objects can be copied from Eden/Survivor to **survivor or old regions depending on age**; old objects belonging to the collection set, when evacuated, are moved according to old region rules. G1 uses young-only phases and mixed collections, and does not equate young GC with a full collection.

**Do not confuse “Old” with “Metaspace”:** Old generation in this article is a **Java object heap region** of the collector. Metaspace is a HotSpot detail for class metadata; they are not the same area.

## 4. Why is collecting Young usually efficient?

Suppose **100,000 objects** were just allocated and at the time of young GC:

- 96,000 objects are no longer reachable;
- 4,000 objects still need to be kept.

If the collector only has to copy/evacuate the relevant live data, a very large portion of memory from the young object group can be reclaimed in one pass without having to scan/reclaim all of Old.

~~~text
100,000 new objects
       |
       v
   Young GC
    /      \
dead       live
96,000     4,000
  |          |
reclaim   copy/evacuate -> Survivor or Old
~~~

**These numbers are completely hypothetical** to illustrate the benefit of many objects dying young. Actual GC cost also includes roots, reference graphs, remembered sets, synchronization, stop-the-world/concurrent tasks, and specific policies.

If a workload has a **high survival rate**, young GC may have to copy many live bytes, causing the generational hypothesis to yield lower benefits. Therefore, tuning must start with **measured allocation rate and survival rate**, not based on a nice ratio on a slide.

## 5. What is object “age” in GC?

**Object age** in generational GC is usually information about **how many relevant young collections the object has survived**. It is **not** the number of seconds/minutes since `new`, nor the number of loops or method calls.

An illustrative progression:

~~~text
When X is created in Eden:       age ~ 0
Young collection #1: X live -> Survivor, age increases
Young collection #2: X live -> Survivor/Old, per policy
Young collection #3: X live -> may be promoted if threshold is reached
Old generation:                  X can still die and be reclaimed by GC later
~~~

**Do not infer** that “after exactly 3 young collections every object moves to Old”: the example above intentionally does not assign a fixed threshold. The number of age increments, promotion timing, and how age is represented depend on the collector.

### Distinguishing GC-measured age and wall-clock time

~~~text
Object A: lives 30 minutes, but no young GC occurs during that time.
Object B: lives 2 seconds, but the workload creates many temporary objects,
          causing many young collections and B survives all of them.

B may have accumulated more age than A under GC policy.
~~~

This is a conceptual scenario; the duration of A/B does not predict a specific object location.

| Statement | True? |
| --- | --- |
| “An object living 10 minutes is definitely in Old” | **No** |
| “An object only a few milliseconds old cannot be promoted” | **No**, there are special policy/pressure cases |
| “Once promoted, an object will no longer be GC'd” | **False**, Old is still collected |
| “Age increases when a thread calls `Thread.sleep`” | **Not directly** |
| “A young object that is still reachable will be reclaimed as garbage” | **False**, the collector must protect live objects |

## 6. How does promotion / tenuring work?

**Promotion** is moving a **live object** from the young generation to the old generation. Depending on the collector, the move can be performed via object evacuation/copying, updating references/barriers, or an equivalent mechanism.

There are three important groups of causes:

1. **Age threshold:** the object has survived enough collections according to policy.
2. **Survivor capacity pressure:** the survivor destination does not have enough space to hold all live young objects; the collector may promote early.
3. **Collector-specific cases:** large/humongous allocations, GC ergonomics, and special handling paths may not follow the classic Eden → Survivor → Old journey.

### Example with an age threshold of 4 (for learning only)

| Event | Illustrative age | Possible location |
| --- | ---: | --- |
| Just created | 0 | Eden |
| Survived young GC 1 | 1 | Survivor |
| Survived young GC 2 | 2 | Survivor |
| Survived young GC 3 | 3 | Survivor |
| Survived young GC 4, met threshold 4 | 4 | Old |

**The threshold of 4 is hypothetical for the example**, not a default value of G1. In a real runtime, survivor pressure or other policy decisions may move the object earlier.

### Does MaxTenuringThreshold mean “exact N GCs”?

**No.** For HotSpot collectors that use age-based tenuring, the `-XX:MaxTenuringThreshold` flag is an **upper bound for the appropriate threshold**, not a requirement that every object wait for that exact value. The collector can choose a lower **desired tenuring threshold** based on survivor occupancy and age distribution.

In addition, different collectors have different tenuring mechanisms and flags. A value in `-XX:+PrintFlagsFinal` is not a promise that every object survives that many GCs before promotion.

## 7. Survivor space/region, dynamic threshold, and premature promotion

Suppose at a young GC, the total live young data to keep is 120 MiB, but the planned survivor destination only has room for 32 MiB.

~~~text
Young live data:     120 MiB
Survivor capacity:    32 MiB
--------------------------------
The portion that does not fit in Survivor may need to go to Old or
take another collector-specific path.
~~~

These are hypothetical numbers. **Insufficient Survivor does not mean the JVM immediately throws OOME**: the collector can promote or handle the allocation through another path if the total heap/Old still has capacity.

**Premature promotion** is moving many objects to Old before the desired age, for example due to a high survival rate or insufficient survivor space. Impacts can include:

- Increased Old occupancy;
- Increased marking/mixed/old collection cost;
- Medium-aged objects dying in Old before an appropriate Old reclaim cycle;
- Increased memory pressure and difficulty meeting pause time goals.

**Do not automatically conclude this is a collector bug.** Sometimes early promotion is a necessary decision to ensure allocation progress, and adjusting a single flag does not change the actual object lifetime profile.

## 8. Cross-generation references: Old → Young

If the collector only focuses on young objects, it must still recognize **Old objects holding Young objects**:

~~~text
OLD OBJECT                              YOUNG OBJECT
+----------------+                     +-----------------+
| SessionManager | ------------------> | NewSession      |
| currentSession |                     | still live      |
+----------------+                     +-----------------+
~~~

The Young object **must not be reclaimed** because a reachable old object points to it. To avoid traversing the entire old heap on every young GC, collectors have mechanisms such as:

- **Write barriers**: the JVM/JIT records information when the program modifies reference fields.
- **Card table / remembered sets**: metadata that helps find references pointing to young/collection set from outside the collection set.
- **Root scanning** and graph traversal according to the collector algorithm.

In **G1**, remembered sets are used to record locations outside the collection set that contain references into the collection set, helping maintain accurate live reachability when evacuating Young.

**Do not confuse** a write barrier with Java `synchronized` or `volatile`. A write barrier is an implementation mechanism of the collector; `synchronized`/`volatile` belong to the Java Memory Model and synchronization control, even though the VM may coordinate multiple mechanisms at the machine code level.

## 9. Young-only, mixed, old, and full GC differ

| Work type | Meaning |
| --- | --- |
| **Young-only collection** | Collects young regions according to the appropriate collection set, copying/keeping live objects |
| **Concurrent marking** | Identifies old live data/candidates, with phases running concurrently with the application depending on G1 |
| **G1 mixed collection** | Includes Young and some Old regions selected based on reclaim efficiency |
| **Full GC** | Processes the entire heap via the corresponding collector path; usually has a large pause-cost |
| **Generational ZGC/Shenandoah cycles** | Has young/old handling, but algorithms/concurrency/logging differ from G1 |

**Young GC does not mean “wipe out all garbage in the JVM”**, and **promotion does not mean a Full GC has occurred**. When an object is promoted, it is still live; later, if it becomes unreachable, appropriate Old reclamation can reclaim it.

According to the Oracle G1 tuning guide, G1 has a young-only phase, concurrent mark, and mixed collections aimed at reclaiming Old regions efficiently. A log line “`Pause Young`” must therefore not be read as “`Full GC`”.

## 10. Java 17+ example: temporary objects and retained group

Create the file **`GenerationalWorkload.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenerationalWorkload {
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile Object lastPublished;

    public static void main(String[] args) {
        // A group of arrays is kept reachable by the static list.
        for (int i = 0; i < 16; i++) {
            byte[] array = new byte[4096];
            array[0] = 1;
            RETAINED.add(array);
        }

        int created = 0;

        // Many temporary arrays; only the most recent reference is held by
        // the volatile field; earlier arrays can become unreachable.
        for (int batch = 0; batch < 24; batch++) {
            for (int j = 0; j < 8192; j++) {
                byte[] temporary = new byte[1024];
                temporary[0] = (byte) (j & 127);
                lastPublished = temporary;
                created++;
            }
        }

        lastPublished = null;
        System.out.println("temporary-created=" + created);
        System.out.println("retained-count=" + RETAINED.size());
        System.out.println("retained-length=" + RETAINED.get(0).length);

        RETAINED.clear();
        System.out.println("after-clear=" + RETAINED.size());
        System.out.println("gc-timing-not-guaranteed");
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -g GenerationalWorkload.java
java GenerationalWorkload
~~~

**Exact stdout under normal running conditions:**

~~~text
temporary-created=196608
retained-count=16
retained-length=4096
after-clear=0
gc-timing-not-guaranteed
~~~

Because:

- `24 × 8192 = 196608`;
- There are 16 retained arrays of length 4096;
- `RETAINED.clear()` sets the list size to 0 per API;
- There are no GC measurements in those output lines.

### What does the example prove and what does it not prove?

**Proves:** the program creates high temporary allocation demand while actively keeping a group of objects reachable in a list. After dropping references from the list, GC **still has no deadline** to reclaim the objects.

**Does not prove:** which specific object was promoted at which GC count, what the current tenuring threshold is, how many objects are in Survivor/Old, or whether HotSpot executed a certain allocation instruction. That information is collector/runtime-specific.

`lastPublished` is a volatile field to create an observable escape path for temporary arrays, limiting optimization that eliminates allocations; however, do not assume a strict 1:1 correspondence between each `new` expression in source and an allocation event seen by a profiler, because the JIT/collector can optimize.

## 11. Observing GC on HotSpot: separate program stdout and diagnostics

Try on HotSpot (e.g., an appropriate JDK 17/21/25):

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc=info GenerationalWorkload
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc+heap=info GenerationalWorkload
~~~

Program stdout still has the **five deterministic lines** mentioned above. However, **GC logs do not have fixed output**: GC counts, timestamps, region counts, and bytes before/after pause depend on the JDK/heap/JIT/CPU/collector/workload.

With the workload above, the total bytes of temporary allocations logically exceed the 64 MiB heap limit in a single run, yet many objects can become unreachable and be reclaimed; **`-Xmx64m` is not a limit on the cumulative total bytes that can be allocated**. If the machine/VM is not suitable, adjust the heap to a safe level or omit the flags; do not force OOME on a shared environment.

### Reading G1 region logs

An **illustrative** snippet, not guaranteed output:

~~~text
[gc,heap] GC(12) Eden regions: 20->0(15)
[gc,heap] GC(12) Survivor regions: 2->4(5)
[gc,heap] GC(12) Old regions: 10->11
[gc]      GC(12) Pause Young (Normal) (G1 Evacuation Pause) ...
~~~

- `Eden regions`: region counts before/after collection and the next partition target according to the log format.
- `Survivor regions`: the number of regions assigned the survivor role changes as live objects are evacuated.
- `Old regions`: region count information, **not the number of individual objects promoted**.
- `Pause Young`: G1 young collection label, **not Full GC**.

G1 region sizes and the Young area do not necessarily lie contiguously in address space.

## 12. Observing age and tenuring threshold

HotSpot unified logging enables GC tags related to age on supported versions/collectors:

~~~bash
java -Xlog:help
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc+age=debug GenerationalWorkload
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc+age=trace GenerationalWorkload
~~~

You may see:

- **Desired survivor size**: the survivor size targeted by policy.
- **New threshold / desired tenuring threshold**: the current age threshold, which can be lower than the maximum.
- **Age distribution**: the amount of live bytes belonging to each age group.
- **Total**: cumulative bytes up to an age group in the log sample.

A **completely hypothetical output to teach how to read it**:

~~~text
[gc,age] Desired survivor size 2097152 bytes, new threshold 5 (max threshold 15)
[gc,age] - age   1: 800000 bytes, 800000 total
[gc,age] - age   2: 420000 bytes, 1220000 total
[gc,age] - age   3: 160000 bytes, 1380000 total
~~~

Key points:

- `threshold 5` is **not** identical to `max 15`.
- `age 1: 800000 bytes` does **not** mean “800000 objects”.
- The age table measures characteristics of live survivor data per the collector, and does not indicate which source variable has aged.
- If a short workload/another collector does not emit these lines, check `-Xlog:help` and the version instead of fabricating logs.

You can view flags:

~~~bash
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version
~~~

Look for `MaxTenuringThreshold`, `TargetSurvivorRatio`, and related parameters in the appropriate output. Do not arbitrarily change production flags just because a value looks “small”: adaptive policies may have already chosen appropriately for the workload.

## 13. Why do Old → Young references make GC more complex?

Imagine if young GC did not handle Old → Young references:

~~~text
Old Object (reachable) --> Young Object (no other local var)
~~~

An algorithm that only sees young local roots and forgets the cross-generation edge could wrongly conclude that the Young object is garbage. Therefore, a generational collector must maintain metadata/algorithms to detect relevant edges.

**G1 remembered sets** record references **from outside the collection set pointing into the collection set**, helping process a smaller set of regions than the entire heap. Reference updates can use write barriers, dirty cards, and concurrent refinement depending on the collector.

That is part of the **price paid** to collect Young efficiently. It must not be presented that young GC “does not need to inspect Old in any way”.

## 14. Large/humongous objects and exceptions

Not every object goes through the exact journey:

~~~text
Eden -> Survivor S0 -> Survivor S1 -> Old
~~~

G1 has **humongous objects** that occupy a number of regions according to special rules. Some large objects/arrays can be allocated and handled directly in special regions instead of starting in Eden and incrementing age normally.

Early promotion cases can also come from Survivor capacity; and an optimized method with `new` in bytecode can have physical heap allocation eliminated by JIT escape analysis/scalar replacement. Therefore, **do not count Java `new` statements and infer the exact number of objects in Eden or Old**.

## 15. Different generational collectors do not use the same policy

| Collector | Notable characteristics |
| --- | --- |
| **Serial GC** | Relatively straightforward Eden/Survivor/Old generational model |
| **Parallel GC** | Throughput-focused generational collector; has ergonomics/adaptive sizing |
| **G1 GC** | Uses heap regions, young-only and mixed collection sets, remembered sets |
| **Generational ZGC** | Low-latency concurrent generational collector, policy/barrier/age differ from G1 |
| **Generational Shenandoah** | Generational mode on supported versions/configurations, many concurrent phases |
| **Non-generational collectors/modes** | Do not necessarily use Young/Old or tenuring like the examples |
| **Epsilon GC** | No-op collector, does not reclaim objects; for specialized experiments |

According to modern JDK releases, **ZGC has a generational mode** and on JDK 25 uses generational mode; Generational Shenandoah is present in appropriate JDK releases. However, this does not mean flags like `MaxTenuringThreshold` or `gc+age` logging have the same meaning across all of these collectors.

**Do not infer from Java 8 documentation that G1 in Java 25 must have two physically contiguous Survivor spaces**. Choose the right version of the Oracle/OpenJDK GC guide for the environment you are running.

## 16. Tuning must be based on the real lifetime distribution

When encountering many young GCs or rapidly increasing old occupancy, check:

1. **Allocation rate** (bytes/s), **young GC frequency**, pause time, application throughput, and heap size.
2. **Survival rate** across young collections and **promotion rate**.
3. **Old live-set** after old/mixed collections; is it growing under equivalent load?
4. **Survivor occupancy** and **desired tenuring threshold** via age logs.
5. **Object graph and owners**: caches, long-lived sessions, queues, thread-locals, listeners, unbounded maps.
6. **Humongous allocation**/collector-specific constraints.
7. **JDK/collector/flags version** and differences when testing configurations.

A trade-offs table:

| Change | Potential benefit | Risk |
| --- | --- | --- |
| Larger Young capacity | Can reduce the number of young GCs | Can increase live bytes to process; Old capacity shrinks if heap is fixed |
| Larger Survivor capacity | Reduces premature promotion in some cases | Takes away young capacity meant for Eden |
| Different tenuring threshold | Affects when young objects move to Old | Can increase copy cost or old pressure |
| Larger heap | Adds allocation headroom | Does not automatically fix retention/leaks |
| Reduce unnecessary object allocations | Reduces GC pressure | Can sacrifice code clarity if optimized without benchmarks |
| Release cache entries per lifecycle | Reduces live-set/old pressure | Must ensure correctness and cache policy |

**There is no “standard tenuring threshold for every application”.** Modern garbage collectors have many automatic ergonomic decisions; changing flags should only be done after measuring an equivalent reproducible workload.

## 17. Why is a high promotion rate not necessarily a memory leak?

If an application has many **valid medium-lived objects**, they can survive a few young GCs and move to Old before becoming unreachable. In addition, Survivor capacity pressure can promote early. Therefore, a high promotion rate **does not by itself prove a leak**.

An application-level memory leak is usually **unwanted retention**:

~~~text
Static Cache -> Map -> Session -> Large Object Graph
                     ^
              request has ended,
              but cache still holds reference
~~~

In that situation, GC **cannot reclaim a still-reachable object** simply because it is in Young or Old. The fix is to clarify ownership/eviction, remove unneeded entries, unregister listeners, or close resources at the right lifecycle point. No `MaxTenuringThreshold` can help GC safely delete an object still used by the program.

When evaluating a leak, look at the **live-set after multiple GC cycles** and the paths from GC roots to retained objects, not just total allocated bytes. A program that creates many temporary objects can produce a huge total allocation while keeping the live-set small.

## 18. Misconceptions to correct

| Misconception | What is true |
| --- | --- |
| “Every Java object dies young.” | It is an empirical tendency in many workloads, not a guarantee |
| “The JVMS mandates Eden/Survivor/Old.” | That is a GC implementation design |
| “Age is the number of seconds since `new`.” | Usually based on survival across collections |
| “Every young GC increments every live object's age by exactly one in every collector.” | Depends on collection type/policy |
| “`MaxTenuringThreshold=15` forces a full 15 GCs.” | There is dynamic threshold, survivor pressure, and exceptions |
| “A full Survivor immediately causes OOME.” | Promotion or another handling path can occur |
| “Promotion is collecting an object.” | Promotion **keeps** a live object and moves its generation |
| “A promoted object will never be GC'd.” | Old objects can still be reclaimed later |
| “Young GC means Full GC.” | Young-only does not process the entire heap |
| “Old region increasing by 1 means one object was promoted.” | Region count is not object count |
| “G1 has two hard contiguous Survivor spaces.” | G1 uses survivor regions distributed across the heap |
| “Young GC does not need to consider Old references at all.” | Cross-generation references must be protected |
| “GC provides thread-safety for references.” | No; JMM and synchronization are a different topic |
| “`System.gc()` will age/promote objects as desired.” | There is no guarantee on GC/promotion timing |
| “Every collector has the same age log format/threshold.” | Collector-specific implementation |
| “High promotion rate is always a leak.” | Can be a valid lifetime profile or premature promotion |
| “Every `new` is a real heap object.” | JIT can eliminate allocations |
| “Tuning GC flags is enough to fix a static cache leak.” | No, object retention must be fixed |
| “The generational hypothesis guarantees young GC is always fast.” | Depends on survival rate and heap dynamics |

## 19. Review questions with answers

**1.** What does the generational hypothesis describe?  
**Answer:** In many workloads, most objects do not live long, providing the basis for collecting Young frequently.

**2.** Does an object in Survivor mean it has existed for how many seconds?  
**Answer:** It cannot be inferred from location alone; age is usually based on relevant young collections.

**3.** When does promotion happen?  
**Answer:** When a live object meets the age threshold or other survivor capacity/collector policy conditions.

**4.** Is an object in Old immortal?  
**Answer:** No. If it is no longer reachable, it can be reclaimed in old/mixed/full or collector-specific cycles.

**5.** Why do Old → Young references need to be recorded?  
**Answer:** If missed, young GC could mistakenly collect a Young object still kept alive by an Old object.

**6.** Does `MaxTenuringThreshold=15` mean every object must go through exactly 15 collections?  
**Answer:** No; it is a policy bound when applied by the collector, with a desired threshold and other promotion branches.

**7.** Does G1 have one physical Eden contiguous with all Survivor regions?  
**Answer:** No. G1 partitions the heap into regions with different roles and does not require them to be contiguous.

**8.** Does `Old regions: 10->11` indicate that exactly one object was promoted?  
**Answer:** No. One region contains many objects.

**9.** Does `System.gc()` guarantee triggering a young GC and aging an object?  
**Answer:** No.

**10.** If a static cache holds objects too long, what should be fixed first?  
**Answer:** Identify ownership and eviction/release, rather than just adjusting the tenuring threshold.

**11.** Can a high young allocation rate with a small Old live-set be normal?  
**Answer:** Yes, many short-lived temporary objects produce large total allocated bytes but few retained objects.

**12.** Why not compare G1 age logs directly with Generational ZGC?  
**Answer:** Collector implementations and log semantics are different.

## 20. Reliable references

- [JVMS Java SE 25 — `2.5.3` Heap](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.3): heap and storage management, without prescribing a fixed generational strategy.
- [Oracle Java 8 — Generations / Weak Generational Hypothesis](https://docs.oracle.com/javase/8/docs/technotes/guides/vm/gctuning/generations.html): classic source for “most objects die young”; **layout/collector description is historical**.
- [Oracle JDK 25 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): Eden/Survivor/Old regions, age-based promotion, remembered sets, young/mixed phases.
- [Oracle JDK 25 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-collector-implementation.html): explains how to read G1 region logs.
- [Oracle JDK 25 — Factors Affecting GC Performance](https://docs.oracle.com/en/java/javase/25/gctuning/factors-affecting-garbage-collection-performance.html): survivor sizing, thresholds, and tuning trade-offs.
- [Oracle JDK 25 — java Command / Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xlog:gc+age=debug/trace` and diagnostic flags.
- [OpenJDK JEP 439 — Generational ZGC](https://openjdk.org/jeps/439): meaning of generational division in low-latency ZGC.
- [OpenJDK JEP 474 — ZGC: Generational Mode by Default](https://openjdk.org/jeps/474): generational ZGC mode in relevant releases.
- [OpenJDK JEP 490 — Remove Non-Generational ZGC](https://openjdk.org/jeps/490): roadmap for removing non-generational mode.
- [OpenJDK JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): generational Shenandoah and version scope.
- [OpenJDK HotSpot — gc_globals.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/gc_globals.hpp): HotSpot age/tenuring flags; master code may differ from the actual runtime version.

**Remember:** new objects are typically managed in **Young**; most die before needing to be kept long; objects still reachable can stay in **Survivor**, increase **GC age**, and then be **promoted** to **Old** when policy requires. **Age is not wall-clock time, thresholds can be dynamic, G1 uses regions rather than requiring contiguous spaces, Old is still GC'd, and any conclusions about performance/retention must be based on real workload data.**