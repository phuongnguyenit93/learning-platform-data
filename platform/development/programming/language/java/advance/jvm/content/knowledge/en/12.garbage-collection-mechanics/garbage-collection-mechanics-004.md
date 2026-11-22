# Eden, Survivor, and Old in the JVM Generational Garbage Collector Model

In Java, most objects are created, used for a short time, and then no longer referenced. However, there are also objects that live for minutes or hours: caches, connection pools, session data, and large business structures. **Generational garbage collection** leverages this difference in lifecycle to collect efficiently: prioritizing scanning/reclaiming newly created objects that usually die young, and managing objects that have survived multiple collections separately.

In the classic explanation, the **young generation** consists of **Eden** and **Survivor spaces**; the **old generation** holds objects that have existed longer or are allocated into old according to the collector policy. From there, there are three core questions:

1. Where are new objects usually created, and what happens when Eden no longer has enough space?
2. When surviving after a Young GC, do objects move to Survivor or Old? How do **age**, **tenuring**, and **promotion** differ?
3. Why are **Eden/Survivor/Old in HotSpot G1 Java 17 roles of regions**, rather than simply three fixed memory bands as in many old diagrams?

This lesson focuses on the generational model and its application in **HotSpot G1 on Java 17**, while clearly distinguishing which parts belong to general concepts and which parts are implementation details. It includes diagrams, timelines, runnable Java 17 code, GC logging instructions, common misconceptions, and exercises.

## 1. Why is generational collection needed?

An empirical observation often called the **weak generational hypothesis**: many created objects exist only very briefly, and many objects that have existed for a long time tend to continue existing. This is a **workload tendency**, not a rule that "every young object dies" or "every old object is immortal."

For example, in a web service:

| Object | Common lifecycle | Implication for GC |
| --- | --- | --- |
| Temporary `StringBuilder` during request processing | A few method calls | Can die quickly, worth collecting in young |
| JSON-decoded DTO used only in one request | From a few ms to a few seconds | Can be collected after the response completes |
| Cache entry with TTL | Multiple requests | May survive across Young GCs |
| Map holding long-lived application state | Minutes/hours or throughout runtime | Usually remains reachable in old |
| Object used during bootstrap then discarded | Long/short depending on the application | Age cannot be inferred solely from where in source it is instantiated |

Instead of having the collector process the **entire heap** every time regardless of survival rate, a generational collector can process **young** frequently. It finds young objects that are still reachable, moves/copies live objects to the appropriate area, and reuses most of the Eden capacity containing dead objects.

This is an optimization model, **not a replacement for reachability analysis**. An "old" object with no remaining references is still garbage, and a new object held by a static field is still live.

### 1.1. Objects die from losing reachability, not from "reaching an age"

An object is only considered reclaimable when it is no longer reachable from the GC roots/reference paths that the collector must inspect. GC does not delete an object simply because it has "stayed in Eden for three seconds."

- **Age** is usually used to decide **where to keep a surviving object** after a young evacuation.
- **Reachability** is used to decide **whether an object is still alive or is garbage**.
- **Wall-clock age** (number of seconds since `new`) is not the `age` field that generational GC relies on when tenuring.

Two objects created at the same time can be treated differently if one object is held in a long-lived list while the other has no remaining references.

## 2. Three roles: Eden, Survivor, Old

| Region | Role | What commonly happens |
| --- | --- | --- |
| **Eden** | Where newly created small objects are allocated | Young GC collects Eden; dead objects are discarded, live objects are evacuated |
| **Survivor** | Holds objects that survived a young collection but are not yet old | Objects can continue surviving across multiple young collections and increase in age |
| **Old** | Holds promoted objects, objects specially allocated into old, and some long-lived objects | Old is marked/reclaimed through appropriate collection cycles; it is not a region "GC never touches" |

Easy-to-remember model:

```text
                     YOUNG GENERATION
            ┌──────────────────────────────┐
new objects │          EDEN                │
    ───────►│  allocation, many die young  │
            └────────────┬─────────────────┘
                         │ Young GC / evacuation
                  ┌──────┴──────────┐
             unreachable        reachable
                  │                  │
                  ▼                  ▼
              discard         SURVIVOR  (age increases)
                                     │
                           still young / enough space
                                     │ subsequent Young GC
                                     ▼
                                  SURVIVOR
                                     │
                     old enough or needs promotion by policy
                                     ▼
                            OLD GENERATION
                          (still subject to GC when needed)
```

This is a **conceptual behavior diagram**, not a guarantee that objects always sequentially follow `Eden → Survivor 1 → Survivor 2 → Old`. There are cases where objects are promoted early or enter old via a special allocation path.

### 2.1. Is every Java object allocated in Eden?

**No.** "Normally objects are created in Eden" is a model rule, not a contract applicable to every collector and every allocation. With HotSpot G1, **humongous** objects are allocated directly into **old/humongous regions**. In addition, the JIT can **scalar-replace** some allocations if it proves the object does not escape; in that case the source has `new`, but there is not necessarily an independent heap object that needs GC.

Do not infer the allocation location from seeing the `new` keyword in Java source. You need to check the GC implementation, object size, escape analysis, and runtime behavior.

## 3. Eden: object creation area and allocation pressure

Many allocations by Java threads in HotSpot are optimized using **TLAB — Thread-Local Allocation Buffer**. Each thread is given a small allocation buffer in the appropriate young/eden space. When there is still enough room, allocating an object usually only requires bumping a pointer, avoiding locking the entire heap for each allocation.

```text
Heap young / Eden capacity
    ├─ Thread A's TLAB: fast allocations for A
    ├─ Thread B's TLAB: fast allocations for B
    └─ additional space / slow-path allocations

When TLAB is exhausted:
    thread tries refill/new TLAB or allocation slow path;
    if there are not enough suitable young regions, JVM may need GC.
```

**TLAB is not a separate GC generation**, but an **allocation optimization** mechanism. An object allocated into a TLAB does not have a "private GC for thread A." Objects still belong to heap regions and are managed according to the collector.

### 3.1. Eden being full does not mean the entire heap is out of memory

When Eden/young allocation space is consumed, the collector can perform a **Young GC** to reclaim young garbage and create more allocation capacity. If there are still many free old regions or remaining heap capacity, Young GC occurring is normal, **not in itself a memory leak or OutOfMemoryError**.

If an application creates many short-lived objects, the number of Young GCs may increase. What needs to be measured are allocation rate, live set, pause times, throughput, old occupancy, and SLA, not just counting GCs.

### 3.2. Does GC happen immediately the moment Eden reaches exactly 100%?

Do not assume a fixed threshold. Young generation size can be adjusted by the collector, and TLAB refills and allocation paths have different costs/conditions. G1 also uses **adaptive sizing** with pause time and capacity goals. The formula "Eden 100% → one single event type" is only useful in introductory diagrams, not an absolute state machine for every HotSpot scenario.

## 4. Survivor spaces: holding objects that survive Young GC

A Young GC needs to distinguish:

1. Objects in Eden/Survivor that are no longer reachable: reclaimed along with the source regions.
2. Objects still reachable but not yet needing promotion: **copied/evacuated** to new Survivor regions.
3. Objects still reachable and old enough or unsuitable to keep in the survivor set: **promoted** to old regions according to policy.

In traditional copying collectors, books often draw **Survivor S0 and S1** or **From/To**: one space acts as the source, the other receives copied objects; after the collection, their roles swap.

```text
TWO SURVIVOR SPACES MODEL (classic illustration)
Before Young GC:
     Eden:     [A live][B dead][C live]
     From S0:  [D live][E dead]
     To S1:    [empty]

Young GC:
     A, C, D → To S1 if still eligible
     B, E    → garbage; not copied
     Some surviving objects old enough → Old

After Young GC:
     Old From S0/Eden are reused
     S1 acts as the source survivor for the next cycle
```

**Be careful with G1:** the `S0/S1` model helps understand copying, but G1 uses **a set of survivor heap regions that changes with each collection**, not necessarily exactly two adjacent "fixed Survivor space blocks." On G1, the set of young regions consists of Eden regions and Survivor regions; the collector evacuates live objects into **new survivor regions** or **old regions**.

### 4.1. Survivor holds live objects, not "objects about to die"

An object can be in Survivor because it is **still live** after a young collection. The JVM does not know in advance how much longer that object will live. If it is no longer reachable before the next collection, the object will not be copied again and the capacity of the region holding it is reclaimed.

### 4.2. Does Survivor need two equal-sized spaces?

There is no mandatory rule across all collectors. In older copying diagrams, From/To survivor spaces could be configured with a certain ratio; with G1, the number of **regions** used for Eden and Survivor is adjusted according to collector heuristics. Tuning flags such as `SurvivorRatio` and `NewRatio` in documentation for other collectors **should not be mechanically applied to G1** as if it maintained two identical fixed semispaces.

## 5. Age, tenuring threshold, and promotion to Old

A newly created object does not have a "Java clock" measuring how many seconds until it is moved to Old. Generational collectors usually track **survival age across young evacuations**.

Idealized timeline:

```text
time t0: create Object X → Eden
young GC #1: X live → Survivor, age increases
young GC #2: X live → new Survivor, age increases
young GC #3: X live → may be promoted to Old
... if X becomes unreachable, Old GC will reclaim it later ...
```

The line "#3" in the diagram is an **assumption for learning**, not a fixed threshold value in Java 17. G1 decides the threshold and destination depending on adaptive policy, survivor capacity, age, and GC constraints.

### 5.1. What is the tenuring threshold?

**Tenuring** describes an object surviving enough young collections/meeting conditions to no longer stay in survivor. **Tenuring threshold** is the age threshold the collector uses to decide promotion under suitable conditions.

- **Maximum tenuring threshold** is the upper limit that some HotSpot collectors allow configuring via `-XX:MaxTenuringThreshold`.
- **Desired/effective tenuring threshold** can **change with the workload** because the collector wants to cap the amount of live bytes that need to be held in Survivor.
- If survivor capacity is insufficient, objects may be **promoted earlier** than the expected threshold.
- The "age" in diagnostic logs is **GC age**, not the object's lifetime in seconds or a public Java field.

**There is no standard Java API `getObjectGeneration(object)`** to query exactly whether an object is currently in Eden, Survivor, or Old.

### 5.2. Promotion does not turn an object into a GC root

When an object moves from Survivor to Old:

- Java identity (`==`, `equals`, `System.identityHashCode` semantics) must continue to hold.
- Program references are updated when the collector moves/copies objects; Java code must not manually fix pointers.
- The object can still become unreachable and be reclaimed by the collector later.
- Promotion is a change of **heap management region**, not a promise that the application will keep that object forever.

### 5.3. Survivor overflow and premature promotion

An application with a very high survival rate of young objects can put pressure on Survivor. When survivor capacity is insufficient compared to the live set, the collector may promote objects early.

Consequence: **old occupancy rises rapidly** even though newly created objects have not lived long in wall-clock time. This is not necessarily a memory leak: it can be caused by allocation bursts, temporary object retention, survivor sizing, or caches holding references longer than expected.

Diagnosis requires placing metrics side by side: bytes promoted, survivor usage, old occupancy across multiple cycles, and object lifetime/retained references.

## 6. Old generation: storing long-lived objects while still being collected

Old is the place that typically holds objects that have been promoted or allocated directly according to policy. **Old does not mean "Permanent Generation" and is also not Metaspace**.

| Concept | What does it hold? | Is GC involved? |
| --- | --- | --- |
| **Old generation** | Java heap objects in regions belonging to old | **Yes**; the collector performs corresponding marking/reclamation/evacuation |
| **Metaspace** (HotSpot) | Class metadata in native memory | Separate management/unloading mechanism, not heap old |
| **Java static field** | Field belonging to a class; its reference value may point to a heap object | The target object resides in the heap per collector policy; **it does not automatically reside in old just because the field is static** |
| **GC roots** | Reachability root sources | Not every GC root is a heap object; roots help determine live objects |

For example, a `static List<byte[]> CACHE` can keep arrays alive across many young collections and eventually they get promoted. When `CACHE.clear()` is called and no other refs remain, they can become garbage **even though they are in old**.

### 6.1. Is collecting Old necessarily a Full GC?

**No.** In G1, there are:

- Young-only evacuations focusing only on young regions.
- **Mixed collections** processing young together with **a selected set of old regions** after concurrent marking information is available.
- **Full GC** is a more expensive mechanism, usually involving situations where normal processes cannot satisfy allocation/evacuation; not every reclamation of old is a Full GC.

Do not use "Major GC = Full GC = Mixed GC" as three synonymous names. The terms **minor/major** in older books do not map one-to-one to all GC phases of G1.

## 7. HotSpot G1: Eden/Survivor/Old are roles of heap REGIONS

**G1 (Garbage-First)** divides the Java heap into many **regions**, usually of equal size in a configuration. Regions can be assigned the role of Eden, Survivor, Old, Humongous, or Free. Regions with the same role **do not need to be contiguous next to each other** like a fixed young band.

```text
G1 heap consisting of many regions (illustrative diagram, NOT by actual addresses):
┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│Eden  │Old   │Free  │Eden  │Surv. │Old   │Eden  │
├──────┼──────┼──────┼──────┼──────┼──────┼──────┤
│Humong│Humong│Old   │Free  │Surv. │Eden  │Free  │
├──────┼──────┼──────┼──────┼──────┼──────┼──────┤
│Old   │Eden  │Free  │Old   │Eden  │Free  │Old   │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┘

Young = set of Eden regions + Survivor regions.
Old   = set of Old regions (also with separate humongous management).
Each collection can change the number of regions and their roles.
```

### 7.1. What does a Young GC in G1 actually do?

A typical **G1 Young GC** (stop-the-world evacuation pause):

1. The JVM determines the set of regions to collect (**collection set**, often abbreviated `CSet`): the Eden regions and previous Survivor regions.
2. Finds live objects in that set, including inspecting refs from roots **and incoming references from areas outside CSet** via remembered sets.
3. Evacuates/copies surviving young objects to **new Survivor regions** or **Old regions** based on age/collector policy.
4. Updates the appropriate references to the newly moved objects.
5. All source regions that no longer contain live objects to keep can be returned to **Free** and reallocated.
6. The collector adjusts young size, survivor destinations, and pause targets for subsequent cycles.

With this region-based model, collecting young does not need to "scan every byte of the entire Old" on every pause to find old-to-young references; G1 uses remembered sets and write barriers to manage cross-region reference information. That is an important part of making generational collection safe.

### 7.2. What if an object from Old points to Young?

Example:

```java
static final java.util.List<Object> ROOTS =
        new java.util.ArrayList<>();

static void remember(Object obj) {
    ROOTS.add(obj);
}
```

If `ROOTS` already lives in old and code writes a reference to a new object in Eden, the young object **is still reachable** via the path from Old → Young. Young GC **must account for this reference**, otherwise it would mistakenly reclaim an object still used by the application.

Generational collectors apply **write barriers**, card tables, or remembered-set mechanisms depending on the collector to recognize references that must be considered. **Barriers are not `synchronized` or CPU memory barriers in Java source that developers must call manually**; this is work done by the JVM/GC runtime cooperating with compiled/interpreted code.

### 7.3. Is Young size in G1 fixed?

G1 adjusts the number of regions in the young generation according to pause target, live-data feedback, and heap pressure. Adjusting Eden/Survivor capacity helps balance two goals:

- Young generation too small → frequent young collections, throughput may drop.
- Young generation too large → a single evacuation may copy more live bytes, increasing pause duration and consuming temporary destination space.

There is no mandatory "Eden is always 80% and each Survivor is 10%" ratio in G1 Java 17. The 8:1:1 ratios common in textbooks are only **illustrative examples for some older setups/collectors**, not a JVM contract.

## 8. G1 Mixed GC, concurrent marking, and reclaiming old regions

Old objects still need to be examined when they are no longer reachable. G1 coordinates multiple phases:

```text
Young-only phase:
  Young GC → Young GC → ... 
              │
              ▼
Concurrent marking cycle (includes pauses such as initial mark/remark/cleanup)
              │
              ▼
Obtains live bytes info / candidate old regions
              │
              ▼
Space-reclamation phase:
  Mixed GC #1: Young + some Old regions
  Mixed GC #2: Young + some Old regions
  ...
              │
              ▼
Returns to Young-only phase when enough candidate regions have been processed
```

**Concurrent marking does not mean "old objects are copied immediately as the marking thread scans through."** Marking collects liveness information for selecting regions, while evacuation/reclamation happens in the appropriate phases. "Concurrent" also does not mean all of G1 has no stop-the-world pauses: G1 still has STW young/mixed evacuations and specific marking pauses.

### 8.1. Why does Mixed GC include both Young and Old?

G1 adds **some Old regions worth collecting** into the CSet of a collection that is processing Young. This allows it to reclaim old incrementally instead of forcing the entire heap to be compacted in a Full GC every time.

Not every mixed collection has to reclaim all of Old. Choosing fewer or more candidate regions also depends on the pause target, expected reclaim, and policies.

### 8.2. When does Full GC occur?

In HotSpot G1, **Full GC** is usually a more expensive fallback path when normal young/mixed/concurrent mechanisms can no longer make enough progress to satisfy allocation. It can cause large pauses; you need to inspect **GC cause/logs** to distinguish allocation failure, evacuation failure, or related conditions.

A log line showing "Old occupancy increasing" **does not prove that a Full GC will definitely happen immediately**. Old occupancy is a signal, not a mandatory GC command.

## 9. Humongous objects: an important exception to the Eden → Survivor → Old path

With G1 Java 17, an object is considered **humongous** when its size is **half a region or more** according to G1 documentation (based on region size). These objects have a separate allocation path, directly using **humongous regions belonging to the old generation**.

```text
Normal, small-sized object:
    Eden → Survivor → Old (if surviving/eligible)

Humongous object, e.g., big byte[]:
    allocated directly in contiguous Humongous regions
    belongs to Old generation
    does not necessarily go through Eden and Survivor
```

Consequences:

- An object in old **has not necessarily survived many Young GCs**. It may have been allocated directly due to size.
- Humongous objects often use multiple contiguous regions, and remaining space in the last region may not be usable for other objects until reclaimed.
- G1 has paths to reclaim humongous objects depending on type/conditions, including opportunistic reclaim mechanisms and marking/cleanup phases; one should not claim "only Full GC reclaims humongous objects."
- GC activity/old occupancy can spike unexpectedly due to **large arrays** even if the cache data does not live long.

For example, `new byte[10_000_000]` **may** be humongous depending on region size and heap/VM settings. Do not assert a fixed size like "every 1 MB array is humongous": the threshold is relative to **G1HeapRegionSize**. Object headers/alignment also affect the total size of the object.

### 9.1. Humongous is not synonymous with .NET's Large Object Heap

Different platforms manage large objects differently. In Java G1, the humongous concept depends on region size and G1 collector policy. Do not apply a threshold from the CLR or another VM generation directly to HotSpot.

## 10. From model to metrics: allocation rate, survival rate, and promotion rate

When diagnosing generational GC, it helps to separate three questions:

1. **Allocation rate:** how many new bytes per second does the application create?
2. **Survival rate:** how many bytes in Young remain live after a collection?
3. **Promotion rate:** how many bytes are moved to Old across collections?

| Phenomenon | Common signs | What to investigate |
| --- | --- | --- |
| High allocation, low survival | Frequent young collections; Eden drops sharply after GC | Creating many temporary objects, boxing, serialization, buffer copies |
| High survival | Survivor/Old destinations receive many live bytes | Live object graph, caches, queues, transaction lifetime |
| Premature promotion | Old usage rises even though objects do not live long in the workload | Survivor pressure, tenuring threshold, burst retention |
| Old does not drop across mixed cycles | Long-lived live set or GC has not reclaimed enough | Retained references, heap size, marking, candidate reclaim |
| Humongous pressure | Old/humongous region usage rises | Large arrays/strings, region size, data shape |
| Full GC or evacuation failure | Large pauses/insufficient evacuation destinations | Heap headroom, fragmentation, reserve, live set, workload |

**Do not optimize by a single "GC count" number.** An application with many short Young GCs can achieve better p99 latency than an application with few GCs but long pauses. You need to read logs and latency/throughput results of real workloads.

### 10.1. Allocation ≠ retained heap

If code creates 1 million small objects and then loses all references, total allocations can be large while the live set heap after GC is very small. Conversely, few allocations but a global map holding several GB of data can make old occupancy high.

Generational GC memory managers rely heavily on the gap between **allocated bytes** and **live bytes**: what is no longer live in Eden can be reused by keeping only the surviving objects.

## 11. Java 17 program: generating allocation churn and retaining a small set of objects

Create the file **`GenerationalGcDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class GenerationalGcDemo {
    private static volatile List<byte[]> keepAlive;

    public static void main(String[] args) {
        Set<String> poolNames = new HashSet<>();
        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            poolNames.add(pool.getName());
        }

        System.out.println("g1EdenPool=" + poolNames.contains("G1 Eden Space"));
        System.out.println("g1SurvivorPool=" +
                poolNames.contains("G1 Survivor Space"));
        System.out.println("g1OldPool=" + poolNames.contains("G1 Old Gen"));

        List<byte[]> retained = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 100_000; i++) {
            byte[] block = new byte[2048];
            block[0] = (byte) (i & 127);
            checksum += block[0] & 0xff;
            if (i % 5000 == 0) {
                retained.add(block);
            }
        }

        keepAlive = retained;
        System.out.println("retained=" + retained.size());
        System.out.println("checksumPositive=" + (checksum > 0));
        System.out.println("done");
    }
}
```

Compile and run with **HotSpot Java 17 G1**:

```bash
javac --release 17 GenerationalGcDemo.java
java -XX:+UseG1GC -Xms64m -Xmx64m GenerationalGcDemo
```

**Stdout of the application code in a HotSpot JDK 17 G1 environment:**

```text
g1EdenPool=true
g1SurvivorPool=true
g1OldPool=true
retained=20
checksumPositive=true
done
```

### 11.1. What does this code demonstrate?

- With **HotSpot JDK 17 G1**, `MemoryPoolMXBean` typically exposes the pool names `G1 Eden Space`, `G1 Survivor Space`, `G1 Old Gen`. These are **implementation-specific MXBean names**, not an API requirement for every JVM, collector, or version.
- The loop creates 100,000 `byte[2048]` arrays in Java source. The collector/JIT decides the actual allocation path; do not use the loop to infer that every `new` definitely corresponds to a final object in the heap.
- `retained` keeps **20 arrays** due to the condition `i % 5000 == 0`; the remaining arrays are not stored in that collection. The compiler/JIT and temporary references can affect liveness, though it tends to create a large amount of temporary data.
- `checksumPositive=true` is a result check independent of GC scheduling, not requiring a specific number of collections.
- **The program does not print "Eden→Survivor→Old" per object**; the public Java API does not provide a per-object generation mapping.

### 11.2. Why does the output not record the number of Young GCs?

GC may run different numbers of times depending on JDK build, heap sizing, CPU, JIT, TLAB, and operating system. If we printed `MemoryPoolMXBean.getUsage()` or `GarbageCollectorMXBean.getCollectionCount()`, the numbers would not have a fixed stdout. This lesson intentionally only includes lines that can be inferred from the code and memory pool names in the specified HotSpot G1 environment.

On another collector, the three `g1...Pool` lines might be `false`. This does **not** invalidate the generational GC model; it only shows that the pool management interface differs.

## 12. Observing Eden/Survivor/Old with GC logs on HotSpot JDK 17

Use HotSpot **Unified Logging**:

```bash
# Verbose logging; output will include GC logs and application stdout.
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -Xlog:gc*,gc+age=trace,gc+heap=debug \
  GenerationalGcDemo
```

The command is written in POSIX shell syntax; on Windows PowerShell it can be written on **one line**, removing the trailing `\`:

```text
java -XX:+UseG1GC -Xms64m -Xmx64m -Xlog:gc*,gc+age=trace,gc+heap=debug GenerationalGcDemo
```

**There is no fixed stdout/stderr GC log**. Tags/field names and numbers depend on JDK build, GC activity, heap size, execution schedule, and log level. Information like the following may appear:

```text
[info ][gc,heap] ... Eden regions: N->0(...)
[info ][gc,heap] ... Survivor regions: A->B(...)
[info ][gc,heap] ... Old regions: X->Y
[trace][gc,age ] ... age 1: ... bytes
```

This is a **pattern for reading logs, not the actual output of a specific run**. Values N, A, B, X, Y are all illustrative symbols. Read logs by **gc id** and before/after timestamps, do not stitch together information from different GC events into an imaginary single event.

### 12.1. Interpreting a Young GC event

If the log records an event with values:

```text
Eden regions:       20->0
Survivor regions:    2->3
Old regions:        10->12
```

This is a **simulated data example for reading practice**, not a guaranteed G1 output:

- Eden source regions were collected, usually dropping to count 0 in the old eden-set after evacuation.
- The Survivor destination-set uses 3 regions at the end of the event; you cannot infer "3 regions = 3 objects."
- Old increasing from 10 to 12 regions may be related to promotion/allocations and region policy, **it does not by itself prove a memory leak**.
- You must combine event type, region size, live bytes/heap occupancy, timing, and allocation rate to understand the overall impact.

### 12.2. What does `gc+age=trace` say?

The age table can show the number of bytes of objects by **GC age** and desired survivor size/new threshold information in suitable HotSpot builds. Conceptual example:

```text
age 1: ... bytes
age 2: ... bytes
new threshold ... 
```

**Age 2 does not mean the object has a lifetime of two seconds.** It reflects the object surviving through suitable young processing cycles according to the collector. The age table log is also not an age statistic for **every old object** across the entire heap. Depending on flags/version, some lines do not appear if there is no matching event or level.

### 12.3. Writing GC logs to a file instead of the screen

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -Xlog:gc*,gc+age=trace,gc+heap=debug:file=gc.log:time,uptime,level,tags \
  GenerationalGcDemo
```

This is HotSpot Unified Logging syntax on Java 17: selector, output file, and decorators. The file `gc.log` is written in the working directory; production retention/log rotation management needs separate configuration. Do not leave large `trace` logs running unbounded on busy servers.

### 12.4. Compared to the `jstat` tool

HotSpot has `jstat -gc <pid> 1000` to observe GC/pool capacity/usage statistics of a **running process**. However, the demo in section 11 may finish too quickly to be sampled. If you want real monitoring, use a process/server that lives long enough; do not arbitrarily extend a demo with sleep and assume GC will definitely occur.

Some `jstat` columns are named after older generations; interpretation must be tied to the collector and version. In G1, prefer GC logs and collector-accurate memory pool metrics.

## 13. Reading "Minor", "Major", "Young", "Mixed", "Full" correctly

Java GC documentation often uses the terms:

| Term | Correct understanding in this lesson |
| --- | --- |
| **Minor GC** | Young collection in common/traditional usage; not every collector uses this exact event name |
| **Young GC** | In G1, a young-only evacuation of Eden/Survivor regions |
| **Mixed GC** | In G1, a collection that includes Young and some suitable Old regions |
| **Major GC** | Inconsistent term across collectors/docs; need to identify the actual GC log event |
| **Full GC** | A broader heap collection, usually with different pause levels and execution than young/mixed; not identical to mixed |
| **Concurrent mark** | Liveness-finding phase, partially running concurrently; does not mean reclaiming/copying every old region immediately |

Do not simplify G1 into "Minor GC only cleans young, Major GC scans old whenever Old is full" as if there were only two buttons. G1 typically interleaves Young GC, concurrent marking, mixed reclamation, and only uses Full GC under certain conditions.

## 14. Tuning: prioritize understanding the collector before tweaking generations

G1 is designed to self-adjust many parameters, especially young generation size, to meet the **pause time goal** and balance throughput.

Common knobs in HotSpot Java 17:

- `-XX:+UseG1GC`: select G1 when you want explicit test conditions.
- `-Xms` / `-Xmx`: initial/maximum Java heap; affects headroom and GC frequency.
- `-XX:MaxGCPauseMillis=<ms>`: **pause target**, not a hard deadline.
- `-XX:MaxTenuringThreshold=<n>`: age limit used in tenuring policy when applicable; does not force every object to "stay in Survivor n times then go to Old."
- `-XX:G1HeapRegionSize=<bytes>`: changes region size, affecting region count and the humongous threshold; do not tweak blindly to fix every GC problem.

**Do not blindly copy** an old tuning snippet for Serial/Parallel GC and apply it to G1. For example, the picture `Eden:S0:S1 = 8:1:1` is only a representation of some collectors/setups and may not reflect G1's adaptive young region sizing.

### 14.1. How to experiment when old grows rapidly

1. Capture the actual configuration: JDK vendor/version, `java -version`, collector, heap size, CPU, and GC logs.
2. Measure allocation throughput and young survival rate via age/survivor information.
3. Check promotion pressure and reference retention time in caches, queues, thread-locals, or listeners.
4. Look at old occupancy **across multiple collections**, do not read a single snapshot.
5. If there is humongous pressure, check array sizes and region sizes before tuning `G1HeapRegionSize`.
6. Compare pause times (p95/p99), application throughput, and CPU usage.
7. Change only **one** parameter group per experiment and rerun the same workload; record the results clearly.
8. Prioritize eliminating unnecessary retention and allocation bursts in code before forcing tenuring thresholds.

### 14.2. When is old generation growth normal?

After startup or warmup, structures initialized once and kept long-term (caches, class data structures, connection pools, compiled-code-related references) can make the old live set grow and **stabilize**. What matters is whether old retained memory grows unboundedly with traffic or reaches a plateau.

A sawtooth old usage curve with multiple mixed GCs is not in itself a leak. You need to distinguish **committed/occupied memory** from **unreclaimable live bytes**.

## 15. Object age cannot be inferred from source code

Two snippets:

```java
static byte[] permanentlyHeld = new byte[1024];

static void temporary() {
    byte[] tmp = new byte[1024];
    System.out.println(tmp.length);
}
```

Both have `new byte[1024]`, yet:

- `permanentlyHeld` has a static strong reference, can survive multiple Young GCs, and be promoted.
- `tmp` is no longer needed after the method, can die early, or the JIT can optimize it depending on usage.
- There is no guarantee `permanentlyHeld` starts in Eden on every VM/GC/optimization.
- If the static object is replaced/cleared and has no other references, it can still become garbage even after entering Old.

The core point is runtime **liveness and allocation path**, not variable names.

### 15.1. Can a promoted object return to Eden?

In the common generational model, an object already in Old **is not "rejuvenated" back to Eden** just because the application updates a field or creates a new reference to it. Treat promotion as a step that moves the object's management region, not a countdown timer that resets.

However, object-movement details can differ between collectors. Do not turn this statement into a universal ABI rule about object addresses on the Java heap.

## 16. Common misconceptions

1. **"Young generation always takes exactly 1/3 of the heap."** False; sizing depends on collector/config and G1 is usually adaptive.
2. **"Eden, S0, S1, and Old are always four fixed contiguous address ranges."** False with the G1 region model.
3. **"If Eden is full, OutOfMemoryError is guaranteed."** False; Young GC can free space for further allocations.
4. **"Every object must pass through Survivor exactly twice before Old."** False; age threshold and survivor capacity vary.
5. **"Age 3 means the object has lived three seconds."** False; age relates to the number of young processing cycles survived.
6. **"Having a strong reference means the object must be in Old immediately."** False; reachability and generation location are different.
7. **"Objects in Old are never GC'd."** False; G1 mixed/other collections process old.
8. **"Mixed GC is Full GC."** False; mixed is evacuation of young + a set of old regions.
9. **"Concurrent marking means the entire GC has no pauses."** False; G1 still has STW pauses.
10. **"Every object is allocated into Eden."** False; G1 humongous objects go to old regions, and JIT can eliminate allocations.
11. **"An object in Old must already be very old."** False; there are direct paths into old.
12. **"Old growing after a GC = memory leak."** False; it can be normal promotion.
13. **"Fewer GCs is always better."** Not necessarily; you must balance pauses, throughput, live set, and SLA.
14. **"Minor, Major, and Full GC are identical standard terms across every VM."** False; inspect the actual logs and collector.
15. **"Increasing MaxTenuringThreshold is always better."** False; keeping objects in survivor too long also costs copying and pause time.
16. **"Setting survivor too small has no side effects."** False; it can lead to premature promotion and old pressure.
17. **"Objects in Survivor are definitely about to die."** False; they are live at the time of collection.
18. **"TLAB is a new generation between Eden and Survivor."** False; TLAB is an allocation optimization.
19. **"GC logs saying Eden regions=30 means 30 objects."** False; one region holds many objects.
20. **"Survivor region count increasing always proves a leak."** False; it can be due to the current live set and adaptive sizing.
21. **"A static field always places its object in Old."** False; reference origin does not dictate where an object is allocated.
22. **"Humongous objects must pass through Eden before being promoted."** False with G1.
23. **"G1HeapRegionSize does not affect large object behavior."** False; it affects the humongous threshold.
24. **"Enabling `-Xlog:gc*=debug` produces identical stdout on every machine."** False; logs depend on the JDK and workload.

## 17. Self-check with answers

**Question 1.** Why does generational GC usually process Eden more frequently than Old?

**Answer:** Many newly created objects die early, so collecting young can reclaim a lot of space with lower scanning/copying cost for live objects compared to processing all old data on every event.

**Question 2.** An object in Eden is still reachable via a static list when Young GC happens. What can happen?

**Answer:** It is kept by evacuation/copying, usually to Survivor or Old according to age/policy. It is not deleted just because it is in Eden.

**Question 3.** What does an object's age going from 1 to 2 mean?

**Answer:** In the young copying model, it has survived one more suitable young processing/evacuation cycle; it is not automatically adding one second of lifetime.

**Question 4.** What if Survivor does not have enough room for a live object?

**Answer:** The collector can promote it early to Old or apply another mechanism per policy, if there are enough suitable destination regions.

**Question 5.** Does G1 have exactly two fixed Survivor memory blocks?

**Answer:** No. G1 manages survivor **regions** belonging to the young set, which can change in count/location across cycles. S0/S1 is a classic diagram to help understand copying.

**Question 6.** Why does G1 need remembered sets/write barriers?

**Answer:** Young GC must see references from regions **outside CSet** to objects inside CSet so it does not mistakenly reclaim objects that are still reachable, e.g., Old → Young.

**Question 7.** How does Mixed GC differ from Full GC?

**Answer:** G1 mixed collects young and **some old regions** based on selection, whereas Full GC is a broader/more expensive collection path and is not synonymous with mixed.

**Question 8.** Why can a large `byte[]` array go straight to Old?

**Answer:** If G1 considers it **humongous** based on size relative to a region (half a region or more), it uses humongous regions belonging to the old generation.

**Question 9.** Does `-XX:MaxGCPauseMillis=100` guarantee every GC is under 100 ms?

**Answer:** No. It is a target for G1 heuristics to adjust the collection set/young size, not a hard SLA.

**Question 10.** Why does `GenerationalGcDemo` only print 20 retained arrays even though the loop runs 100,000 times?

**Answer:** The condition `i % 5000 == 0` is true for `i = 0, 5000, ..., 95000`, which is 20 times. The remaining arrays are not added to `retained`.

**Question 11.** After removing all references to cache objects in Old, are they reclaimed immediately?

**Answer:** There is no immediate guarantee; they can be reclaimed in appropriate subsequent collections. Old is not immortal, but GC scheduling is not deterministic.

**Question 12.** Can we assert that a class field declared `static final` causes its object to be allocated in Old from the start?

**Answer:** No. Static strong reachability makes the object likely to live long, it does not by itself determine the allocation generation/location.

## 18. Summary

```text
Most new heap objects
       │
       ▼
     EDEN
       │
       ▼ Young GC
 ┌─────┴─────────────┐
 │ unreachable       │ still reachable
 ▼                   ▼
reclaim          SURVIVOR
                    │
                    ├── live across young evacuations
                    │      → age increases, may copy further
                    │
                    ├── eligible to promote
                    │      → OLD
                    │
                    └── unreachable next time
                           → reclaim
                            
OLD:
  - not synonymous with immortal
  - G1 concurrent marking + mixed reclamation
  - special path for humongous allocations
  - Full GC only when appropriate for runtime conditions

G1:
  Eden/Survivor/Old = roles of REGIONS;
  not three immutable address ranges.
```

**Remember:** Eden is where new allocations typically land; Survivor holds live young objects across young collections; Old holds long-lived/promoted objects and some specially allocated objects. **Promotion is governed by GC age, survivor capacity, and collector heuristics**, not by the number of seconds since `new`. With **G1 Java 17**, these three roles are built on dynamically changing **regions**; G1 has young-only collections, concurrent marking, mixed collections, and special reclamation mechanisms for humongous/old. To tune properly, look at **allocation rate, survival/promotion rates, retained heap, pauses, and GC logs**, instead of trying to guess object age from source code.

### Standard references

- [Oracle Java SE 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): young/old regions, copying, humongous, and GC cycles.
- [Oracle Java SE 17 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector-tuning.html): adaptive sizing and tuning recommendations.
- [Oracle Java SE 17 — HotSpot GC Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/index.html): generational GC and collector-specific behavior.
- [Oracle — Garbage First GC Tuning](https://www.oracle.com/java/technologies/g1gc.html): distinguishing young/mixed/concurrent marking and tenuring.
- [Oracle JDK 17 `java` launcher manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `UseG1GC`, `Xms`/`Xmx`, `Xlog`, and HotSpot flags.
- [Oracle JDK 17 `jstat` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): GC/memory pool statistics.
- [Java SE 17 — `MemoryPoolMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): Java management API for memory pools.
