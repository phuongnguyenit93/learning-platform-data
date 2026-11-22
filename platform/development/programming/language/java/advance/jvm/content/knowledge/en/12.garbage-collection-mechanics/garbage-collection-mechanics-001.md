# Mark, Sweep, Copy, and Compact: Ways to Identify and Reclaim Memory in the JVM

The Garbage Collector (GC) helps Java reclaim the memory of objects that no longer need to be kept alive based on **reachability**. However, "GC runs" does not mean only a single action of deleting objects: a collector may **mark** live objects, **sweep** unused regions, **copy/evacuate** live objects to another region, and/or **compact** live objects to reduce fragmentation. These operations have different purposes and are often combined.

This article accurately explains the foundational algorithms and their impact on **liveness, allocation, fragmentation, reference updating, pause time, throughput**. Then it contrasts them with how HotSpot Java 17 uses these mechanisms in **Serial, Parallel, G1, ZGC, and Shenandoah**. The goal is not to reverse-infer that "each collector equals exactly one algorithm," but to understand why collectors choose to combine multiple steps.

## 1. Two different questions: still alive or need to be moved?

GC must solve two related but non-identical problems:

1. **Liveness/reachability:** which objects can still be accessed by the program through valid references and must be preserved?
2. **Reclamation/placement:** after knowing which objects need to be kept, how to reuse the freed memory and arrange the live objects so that subsequent allocations are efficient?

**Mark** primarily solves the first question. **Sweep**, **copy/evacuation**, and **compaction** solve the second question using different strategies. Real-world GC algorithms also have to handle multiple threads, references, class metadata, the Java Memory Model, JNI, large memory regions, and runtime overhead.

Suppose a small heap is holding objects A, B, C, D:

```text
GC roots
   |
   v
   A ---> B ---> C         D (no longer has a path from root)
           ^
           |
           +---- A

A, B, C: reachable in the graph.
D: not reachable from the considered roots; can be reclaimed.
```

Even though a reference cycle appears in the graph, **tracing GC does not treat a cycle as a leak by itself**. If an entire group of objects no longer has a path from GC roots, the collector can reclaim that group. Conversely, if a cache holds objects with no remaining business value but still has a strong reference from a static root, GC is not allowed to treat it as garbage on its own.

### Some foundational terms

| Term | Meaning in this article |
| --- | --- |
| **GC root** | Starting point for tracking reachability, such as live references in thread frames/VM structures or appropriate static references |
| **Live/reachable object** | Object that needs to be preserved according to reachability rules at the considered GC phase |
| **Garbage/dead object** | Object no longer reachable under the corresponding tracing model and reference-processing |
| **Object graph** | Objects are nodes, referencing fields/array entries are edges |
| **Mark bit/mark bitmap** | Metadata used to record that an object has been discovered as alive |
| **Free list** | List/structure managing free spaces available for allocation |
| **Fragmentation** | Total free capacity may be sufficient, but it is split into small gaps making contiguous allocation difficult |
| **Evacuation/to-space** | Moving/copying live objects out of a region being collected to a destination region |
| **Forwarding information** | Mapping an old object location to its new location to avoid duplicate copying and help update references |
| **Write/load barrier** | Runtime/JIT instrumentation maintaining correctness of marking, remembered sets, or relocation |

Do not equate **Java object identity** with **memory address**. An object can change location due to GC, yet `a == b` must still reflect the same logical identity, and fields must preserve their exact semantics.

## 2. Reachability: the step that decides which objects to keep

A tracing collector starts at **GC roots**, follows the appropriate reference edges, and discovers the set of reachable objects. Root sources in HotSpot typically include live references in **Java thread frames**, registers/JIT metadata, static fields, JNI handles, and necessary runtime structures.

Example:

```text
Root R1 --> A --> B --> C
            |
            +----> E

Root R2 --> B

D --> F     (no path from roots to D or F)
```

If considering only **strong reachability** in this simple example, the marked set is **{A, B, C, E}**. The two objects D, F have no path from roots so they can be reclaimed. B remains **a single object**, even though there are paths from R1 and R2.

In real GC there are also **Reference** types such as `WeakReference`, `SoftReference`, `PhantomReference`, and reference processing rules; therefore, the model of "following every reference edge the same way" is not sufficient for the entire JDK.

### Marking does not necessarily traverse every object in one fixed order

Collectors may perform DFS, BFS, use marking stacks/queues, bitmaps, parallel processing, and leverage heap data structures. **Traversal order** does not change the true reachable set, but it affects locality, work balancing, pause, and concurrency overhead.

**Having marked objects** also does not mean "memory has been reclaimed": marking only identifies a set to preserve. There must be a reclaim/evacuate/compact step or equivalent mechanism for capacity to actually return to the allocator.

## 3. The Mark algorithm: from roots to all reachable objects

Simple marking model:

1. Prepare mark state for objects within the GC scope.
2. Put GC roots into a queue/traversal structure.
3. Loop: take a reference; if the object is not yet marked, mark it and traverse its appropriate reference fields/array entries.
4. When there are no more nodes to process, the set of marked objects is the **live set** according to the snapshot/model the GC is using.
5. Unmarked objects can be handled by sweep or indirectly eliminated during copying/compaction.

Pseudocode:

```text
mark(roots):
    worklist = roots
    while worklist is not empty:
        object = worklist.remove()
        if object == null or alreadyMarked(object):
            continue
        setMarked(object)
        for ref in strongReferencesFrom(object):
            worklist.add(ref)
```

This is **pseudocode for tracing strong references**, not the complete algorithm set of the JDK. Real GC also involves safepoints, object layouts, concurrent updates, reference processing, class unloading, and other root types.

### Three colors: white, gray, black

The tri-color model is commonly used to explain marking:

- **White:** object not yet discovered/marked.
- **Gray:** discovered, but outgoing references have not finished being scanned.
- **Black:** outgoing references have finished being scanned in the model under consideration.

```text
Initially:
  roots --> [A:GRAY] --> [B:WHITE] --> [C:WHITE]

Process A:
  [A:BLACK] --> [B:GRAY] --> [C:WHITE]

Process B:
  [A:BLACK] --> [B:BLACK] --> [C:GRAY]

Process C:
  [A:BLACK] --> [B:BLACK] --> [C:BLACK]
```

**White does not always mean garbage at every point in time**: an object still white while marking is incomplete may yet be discovered. The tri-color model is especially useful for understanding **barriers**: when Java threads mutate the object graph concurrently with marking, the collector must prevent a live object from being missed.

## 4. Java 17 example: simulating reachability with a graph

Create a standalone file **`TraceGraphDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class TraceGraphDemo {
    static Set<String> mark(Map<String, List<String>> edges,
                            List<String> roots) {
        Set<String> marked = new HashSet<>();
        Deque<String> pending = new ArrayDeque<>(roots);

        while (!pending.isEmpty()) {
            String node = pending.pop();
            if (marked.add(node)) {
                for (String next : edges.getOrDefault(node, List.of())) {
                    pending.push(next);
                }
            }
        }
        return marked;
    }

    public static void main(String[] args) {
        Map<String, List<String>> graph = new HashMap<>();
        graph.put("A", Arrays.asList("B", "E"));
        graph.put("B", List.of("C"));
        graph.put("C", List.of("A")); // create a cycle
        graph.put("D", List.of("F"));
        graph.put("E", List.of());
        graph.put("F", List.of());

        Set<String> live = mark(graph, List.of("A"));
        Set<String> all = new TreeSet<>(graph.keySet());
        Set<String> unreachable = new TreeSet<>(all);
        unreachable.removeAll(live);

        System.out.println("live=" + new TreeSet<>(live));
        System.out.println("unreachable=" + unreachable);
    }
}
```

Compile/run with Java 17+:

```bash
javac --release 17 TraceGraphDemo.java
java TraceGraphDemo
```

**Exact stdout:**

```text
live=[A, B, C, E]
unreachable=[D, F]
```

- Marking from root A traverses B, C, E; the cycle A→B→C→A does not cause an infinite loop because `marked.add(node)` only returns `true` the first time.
- D and F are in the graph but not reachable from the chosen root A.
- This is a **graph simulator**, **it does not perform HotSpot GC**. The `HashMap`, `String`, and `Set` objects created by this Java program still have their own actual reachability; the output only reflects the rule *mark from the set of roots defined by the example*.
- Takeaway: before reclaiming, you must determine **reachable paths from roots**, not simply count objects or reference cycles.

## 5. Mark–Sweep: mark and then sweep unused regions

The **mark-and-sweep** algorithm splits into two main stages:

1. **Mark:** identify reachable objects.
2. **Sweep:** scan the heap region/collection scope, identify unmarked allocations, and put those memory spans into a free list/free-space management structure; prepare the mark state for the next collection in an appropriate manner.

Example of a sequence of allocations (each cell is an illustrative block):

```text
Before marking:
| A | B | C | D | E | F | G | H |

After marking:
| A*| B | C*| D | E*| F | G | H |
  * = reachable/live; B,D,F,G,H not reachable

After sweep:
| A | . | C | . | E | . | . | . |

Free runs: [1 block], [1 block], [3 blocks].
A, C, E DO NOT change position in the non-moving mark-sweep model.
```

### Advantages

- Does not require copying live objects; advantageous when most of the heap is **live**, if using a non-moving approach.
- Can reclaim dead blocks and reuse them without needing an additional to-space of size equivalent to the entire collection set.
- When objects are not moved, relocation/reference fix-up overhead for that stage can be avoided.

### Disadvantages

- **External fragmentation:** scattered small gaps prevent the allocator from finding a large enough block even though **total** free bytes may be large.
- **Allocation complexity:** may require size-segregated free lists, coalescing adjacent free blocks, or other allocator strategies; no longer just a "bump pointer" over a contiguous region.
- **Sweep cost:** needs to scan allocations/metadata in scope; many dead blocks can make scanning and free-list management work significant.
- **May need compaction later:** applications with large objects or needing contiguous memory may not be able to use fragmented free capacity.

Do not infer "mark-sweep always has long pauses" or "cannot be concurrent": there are concurrent/parallel marking and sweeping designs. The conceptual algorithm **does not uniquely dictate** how GC scheduling is implemented.

### When does fragmentation really matter?

Suppose a simulated heap has a total of **4 free units**, but the free runs only have lengths 1, 1, and 2. An allocation request for an object of size **3 contiguous units** may **fail in that region**, despite 4 total free units. The GC/allocator may look for another region, expand the heap, trigger collection/compaction, or report an error if no option is available.

This differs from **internal fragmentation**: allocating a block larger than requested due to alignment/size classes, leaving part of the memory **inside the allocated block** unused.

## 6. Mark–Compact: mark, compute new locations, and compact live objects

**Mark-compact** starts by identifying live objects, then arranges/moves them according to a target layout to create large and relatively contiguous free spans.

A simple **sliding compaction** style:

```text
Before:
| A*| . | C*| . | E*| . | . | . |
   ^      ^      ^
   live objects at different old positions

After compact:
| A | C | E | . | . | . | . | . |
            ^  contiguous free region at the end

Illustrative mapping:
  A: old slot 0 -> new slot 0
  C: old slot 2 -> new slot 1
  E: old slot 4 -> new slot 2
```

For a real object graph, a compacting collector may need to:

1. Identify live objects and the size of each object.
2. Compute the **destination address** and store appropriate forwarding/offset metadata.
3. **Update references** from GC roots, object fields, array elements, and VM structures so they point to the new destinations.
4. Move object data in a safe order, preserving Java object identity, monitor state, hash/metadata, and field values.
5. Publish the new free region to the allocator, synchronize, and finish the phase according to collector invariants.

**Mark-compact does not necessarily have a full sweep pass before copying**. It is a family of algorithms: after marking, it can determine destinations and then slide/copy and establish free regions, without having to run a separate free-list sweeping phase like mark-sweep.

### Advantages and trade-offs

- **Reduces external fragmentation:** creates large free regions, making allocation faster and more uniform.
- **Locality:** compacted live objects can improve locality/TLB/cache behavior in appropriate cases.
- **Has relocation cost:** moving live bytes and updating references/metadata; in some workloads, more expensive than non-moving sweep.
- **Pause/concurrency:** a whole-heap STW compact implementation can have long pauses; concurrent/incremental algorithms reduce pauses by adding barriers and complexity.
- **Actual complexity** depends on live bytes, number of reference edges, layout, barriers, parallelism, and the selected part of the heap.

Do not assume every collector labeled "compacting" executes **the exact same sliding algorithm**, or that compact is only used when the heap is completely full.

## 7. Copying/Evacuation: keeping live objects by moving them to a destination region

A **copying collector** selects a source region (from-space/collection set), finds live objects, and **copies** them to **to-space/destination**. Afterward, the source region can be reclaimed relatively quickly once all valid references have been redirected.

```text
From-space before GC:
| A*| B | C*| D | E*| F | ... |
   |      |      |
   +------+------+
          |
          v
To-space after copying:
| A | C | E | free ........ |

From-space can be reused once relocation completes safely.
```

A very familiar mechanism is **forwarding**:

```text
Root R1 ----> A_old
Root R2 ----> A_old

First time encountering A_old:
  copy A_old -> A_new
  forwarding(A_old) = A_new

Second time encountering A_old:
  sees forwarding already exists, DOES NOT create another new Java object A
  updates/redirects R2 to A_new

End of phase:
Root R1 ----> A_new
Root R2 ----> A_new
```

In Java terms, both roots still point to **the same object A**. Forwarding pointers or forwarding tables are **implementation details**, not Java fields allowed to be read in source code.

### Why is copying attractive to many collectors?

- **Allocation after copying** can often use a bump pointer in the destination region with contiguous space, reducing allocator overhead.
- When the dead-object ratio is high, the bytes that must be copied are **live bytes**, which is often much smaller than total allocated bytes in the region.
- To-space can provide a less fragmented layout after each evacuation.
- Fits the **generational hypothesis**: most objects created in a short period have short lifetimes, so the young generation has a relatively small live set in many workloads.

### Disadvantages and limitations

- Requires **sufficient destination space** to move live objects to their new home; this is a resource that cannot be ignored.
- When most objects are still alive, **copy cost** and destination space can be very large.
- Needs to scan/update references, manage forwarding, synchronize between GC workers, and interact with runtime/JIT/JNI.
- "Copy every object" does not apply: usually only objects in selected regions/young generation are processed; objects elsewhere may remain unchanged.
- When to-space is insufficient, the collector must have fallback/failure handling mechanisms. One cannot assume every evacuation always succeeds.

A classic copying collector may use **two semispaces**, alternating from/to roles. **G1 is not a fixed two-half heap model**; it selects multiple regions and evacuates to appropriate regions. Do not equate every copying implementation with "only using 50% of the heap."

## 8. Comparison table of the three main reclamation approaches

| Property | Mark–Sweep | Mark–Compact | Copy/Evacuation |
| --- | --- | --- | --- |
| Distinguish live/dead | Mark reachable objects | Mark reachable objects | Discover/trace reachable objects in source set |
| Handle dead space | Add free blocks to allocator/free lists | Compact live objects, create free span(s) | Reclaim source region after evacuating |
| Must live objects move? | **No** in non-moving model | **May** move | **May** move when in evacuated region |
| External fragmentation | Can remain significant | Usually reduced strongly | Less in newly compacted destination region |
| Cost by live bytes | No need to copy live bytes | Has relocation/compaction work | Has copy/evacuation work |
| Extra destination space | Usually does not need equal-size to-space | Does not necessarily need full second space | Must have space to hold copied objects |
| Reference fix-up | Not needed for non-moving sweep alone | Needed if objects move | Needed or uses appropriate forwarding/barriers |
| Typical allocation strategy | Free lists/size classes | Bump pointer on contiguous free region | Bump pointer in to-space |
| Suitable workload | Large live set, avoid copying, tolerate/control fragmentation | Need to prevent fragmentation, want contiguous allocation | Regions with many dead objects, such as young regions |
| Pause time | Depends on design/parallelism | Depends on amount moved and design | Depends on live bytes, roots, edges, space, barriers |

**This table describes principles**, not a benchmark or guarantee that a specific collector is always faster/slower than another. A modern design can combine **concurrent mark + region evacuation + occasional full compact**, depending on the phase.

## 9. Java 17 example: simulating sweep and compact on slots

Create **`SweepCompactToy.java`**:

```java
import java.util.Arrays;

public class SweepCompactToy {
    static String[] sweep(String[] slots, boolean[] live) {
        String[] copy = slots.clone();
        for (int i = 0; i < copy.length; i++) {
            if (!live[i]) {
                copy[i] = null;
            }
        }
        return copy;
    }

    static String[] compact(String[] swept) {
        String[] result = new String[swept.length];
        int destination = 0;
        for (String item : swept) {
            if (item != null) {
                result[destination++] = item;
            }
        }
        return result;
    }

    public static void main(String[] args) {
        String[] slots = {"A", "B", "C", "D", "E", "F"};
        boolean[] live = {true, false, true, false, true, false};

        String[] swept = sweep(slots, live);
        String[] compacted = compact(swept);

        System.out.println("before=" + Arrays.toString(slots));
        System.out.println("swept=" + Arrays.toString(swept));
        System.out.println("compacted=" + Arrays.toString(compacted));
        System.out.println("freeAfterSweep=" + 3);
        System.out.println("largestFreeRunAfterSweep=" + 1);
        System.out.println("largestFreeRunAfterCompact=" + 3);
    }
}
```

```bash
javac --release 17 SweepCompactToy.java
java SweepCompactToy
```

**Stdout:**

```text
before=[A, B, C, D, E, F]
swept=[A, null, C, null, E, null]
compacted=[A, C, E, null, null, null]
freeAfterSweep=3
largestFreeRunAfterSweep=1
largestFreeRunAfterCompact=3
```

**This is a layout simulation**, not a GC runtime: the actual `String[]` and String literals of the Java program are still managed separately by the GC. The variables `slots`, `swept`, and `compacted` are three Java arrays coexisting at the time of printing; there is no physical HotSpot object movement here.

The model shows that **the total number of free blocks after sweep is 3** but split into three separate positions; after compact, the same total free of 3 is contiguous. It also intentionally omits actually updating object-reference addresses because the strings A/C/E are only **block labels**.

## 10. Updating references: moving an object must not change Java identity

An object can be referenced from many places:

- Local variables/operand stacks/JIT registers still live in thread frames.
- Static fields of classes with a live owner.
- Fields of other objects in the heap.
- Reference-array elements, collections.
- JNI handles and VM runtime structures.

When copying/compacting an object, the GC must ensure that all **still-usable** reference paths go to the right logical object. With a stop-the-world collector, the collector can update relevant slots before mutators resume. With a concurrent relocating collector, forwarding/barriers can allow **lazy remapping**, so not every slot necessarily holds the new address representation at the same time.

```text
Before:
  root1 --> A@old
  root2 --> A@old
  B.ref --> A@old

After relocation:
  root1 --> A@new
  root2 --> A@new
  B.ref --> A@new

A is still A: preserves fields, identity, locking semantics.
```

**`System.identityHashCode(A)` is not a raw address.** It is not allowed to change just because GC moves an object that is still the same object. Two different objects can also collide on identity hash code, so identity hash is not a permanent unique ID.

Terms like compressed oops, object header/mark word, forwarding bits, barriers, and remembered sets are **HotSpot internals**. Portable Java code must not rely on pointer bit layouts.

## 11. Generational GC: why do young/old often have different policies?

Common design hypothesis: **most objects die relatively early**, while some objects have long lifetimes. A generational collector typically organizes object lifetimes into young and old regions for efficient collection.

Conceptual flow example:

```text
Allocation --> Eden (young)
                  |
                  | Young collection
                  v
            Survivor regions / copies
                  |
                  | passes age threshold / collector condition
                  v
              Old regions

Young collection can reclaim many dead objects quickly.
Old collection handles long-lived objects under a different policy.
```

There is no rule that "every Java object always survives exactly N young GCs before promotion." Age thresholds, survivor size, promotion, and whether an object is allocated directly into another region depend on the GC and flags.

### Why does the young generation often use copying?

If 100 MiB is allocated but only 5 MiB survives a young collection, copying around 5 MiB can be cheaper than having to manage tens of thousands of small free blocks. However, this is a **hypothetical example**, not a default Java number/live ratio.

### Does the old generation always use mark-sweep?

No. Each collector chooses its algorithms; Serial Old/Parallel Old typically perform **mark-compact** in appropriate situations; G1 has **region evacuation** and full compaction fallback; ZGC/Shenandoah have **concurrent relocation**. The phrase "young = copying, old = mark-sweep" is an oversimplification for modern HotSpot.

## 12. G1 in Java 17: combining marking, evacuation, and compaction

G1 (Garbage-First) in HotSpot divides the heap into **regions**. Eden, survivor, and old are logical sets of regions; they are not necessarily large contiguous address blocks. G1 is designed to balance throughput and pause-time goals by only collecting appropriate **collection sets (CSet)**.

Main activities:

1. **Young evacuation pauses:** select young regions in the CSet, find roots and references into the CSet, copy live objects out to destination regions, reclaim selected source regions.
2. **Concurrent marking:** track live data of old regions, helping estimate where there is a lot of reclaimable garbage.
3. **Mixed collections:** in addition to young regions, select additional beneficial old regions to evacuate.
4. **Fallback Full GC:** in memory pressure/unable-to-make-progress situations, the collector may need a full-heap STW compaction, which has a longer pause.
5. **Humongous allocations/regions:** very large objects have their own policy, unlike small young objects; region fragmentation and trigger cycles need to be monitored.

### G1 "mark" and "evacuate" are not necessarily at the same time

- **Concurrent marking** evaluates liveness to select regions and prepare collection.
- **Evacuation** copies live objects during **STW pauses** of G1 Java 17 for the selected regions.
- **Remembered sets/card barriers** help track references **from outside the collection set into it**, reducing the need to scan the entire heap at every young pause.
- G1 marking uses the **Snapshot-At-The-Beginning (SATB)** principle and write barriers to maintain an appropriate liveness snapshot while mutators run.

Do not say "because G1 has concurrent marking, G1 always concurrent-copies every object." These are **two different tasks**. Objects outside the CSet generally do not move during that pause.

### Looking at an example region layout

```text
G1 heap (regions, not 50%-50% semispaces):

R0: Eden         [A* B C* D]   <- selected into CSet
R1: Survivor     [E* F G]      <- selected into CSet
R2: Old          [H I* J K*]  <- depends on young/mixed CSet
R3: Old          [L* M]        <- outside CSet
R4: Free         [            ]
R5: Free         [            ]

Evacuate A,C,E... to destination regions;
reclaim R0,R1 when safe;
R3 does not automatically copy just because of a young collection.
```

Actual placement and thresholds are decided by G1. The `*` notation indicates a live object **in the example**, not real heap dump data.

### Evacuation failure

If there is insufficient available to-space, G1 can encounter an **evacuation failure**; the collector must maintain reference correctness even though some live objects could not be copied as intended. Afterward, memory pressure and a Full GC may occur if there is not enough progress. Therefore, **reserve/headroom** is a factor in GC operations, not just "heap used is not full yet is enough."

According to Oracle G1 tuning guidance, policies are always **optimization targets**, with no guarantee that every pause is always lower than a configured number of milliseconds.

## 13. Other collectors in HotSpot Java 17

| Collector | High-level mechanism choices | Trade-offs to understand |
| --- | --- | --- |
| **Serial GC** (`-XX:+UseSerialGC`) | GC work mainly on one collector thread; young copying and old collection/compaction per implementation | Simple, suitable for some small heaps/limited CPUs; STW pauses |
| **Parallel GC** (`-XX:+UseParallelGC`) | GC threads work in parallel; young copying and old **parallel compaction** under standard configuration | Optimizes throughput, can tolerate STW pauses |
| **G1 GC** (`-XX:+UseG1GC`) | Region-based concurrent marking + STW evacuation/mixed collections + fallback compaction | Balances throughput/pause goals and memory overhead |
| **ZGC** (`-XX:+UseZGC`) | Concurrent marking/relocation with load barriers and specific runtime metadata | Prioritizes low latency, has overhead/throughput trade-offs |
| **Shenandoah** (`-XX:+UseShenandoahGC` on supported distributions) | Concurrent marking/evacuation, forwarding/barriers depending on mode | Reduces pauses, trade-offs in CPU/memory/availability by build |

This is an **educational overview** of Java 17, without promising that every JDK 17 distribution enables/bundles all collectors. **The Java SE specification does not mandate a specific collector.**

**Important note on versions:** ZGC in JDK 17 differs from the **Generational ZGC** architectures of newer JDKs. When reading tuning docs or reporting numbers, keep the exact pair **JDK version + collector**; do not apply behavior from newer releases directly to Java 17.

### Do not rank collectors by "absolute speed"

- Throughput: the share of time application code does work instead of GC.
- Latency: length/distribution of pauses affecting request tail latency.
- CPU overhead: marking/evacuation/barriers/JIT work can consume CPU even when pauses are short.
- Memory overhead: remembered sets, bitmaps, to-space/headroom, and metadata.
- Predictability: workload allocation rate/live-set size determines much of this.

A high-throughput collector may have long pauses; a low-latency collector may consume extra CPU/memory. You must measure against the real workload rather than choosing solely by algorithm name.

## 14. Concurrent marking needs barriers to protect correctness

If GC marking happens **concurrently** with application threads (mutators), the object graph can change between when an object is scanned and when the collector scans the next reference.

Tri-color example:

```text
A:BLACK  (finished scanning)
B:GRAY   (waiting to be scanned)
C:WHITE  (not yet discovered)

If a mutator changes the reference graph so C is only reachable
from A after A is already BLACK, the collector risks missing C,
without an appropriate barrier/invariant.
```

Collectors typically use **write barriers** to record/adjust reference field changes:

- **Snapshot-At-The-Beginning (SATB)**: a model that protects a snapshot of objects alive at an appropriate point; for example, needing to record the **old reference value** when an edge is replaced to avoid losing track of a snapshot-live object.
- **Incremental update**: another design family focusing on new edges or object colors to maintain the marking invariant.
- **Card marking/remembered sets**: recording heap cards/regions with reference changes, useful for generational/region collectors when finding cross-region edges.

**Not every write barrier does the same thing**, and not every GC uses all three mechanisms above. G1 in Java 17 uses barrier infrastructure for SATB marking and tracking remembered sets with different roles.

### GC barriers differ from `volatile`/`synchronized`

- **GC barrier** is VM/JIT instrumentation protecting tracing/relocation invariants.
- **Java Memory Model barrier/synchronization** controls visibility and ordering between application threads.
- Both systems may use specific machine operations, but their **purposes/contracts are different**. Do not remove `volatile` or locks because "GC also has barriers."

### Concurrent relocation also needs the right target reference

For ZGC/Shenandoah, when an object is being moved while mutators continue running, the collector uses **forwarding/remapping/load barriers** to ensure accesses reach the right object. Therefore, you cannot use the model "STW fixes all references at once before resuming" to explain all concurrent relocation.

## 15. Stop-the-world, safepoints, and GC phases

**Stop-the-world (STW)** means application threads pause at points/times requested by the VM so that GC or the VM can perform work requiring a sufficiently consistent heap/thread state. GC is not by default a single background thread running alongside the application.

Types of work in a collection may include:

- Root enumeration/initial mark.
- Concurrent marking when supported by the collector.
- Reference processing.
- Evacuation/copying or compaction.
- Root/reference fix-up, remapping.
- Remark/cleanup, class unloading, and bookkeeping.

A collector can have both **concurrent phases** and **STW pauses**. For example, G1 has concurrent marking and STW evacuation. ZGC is designed so most expensive work is concurrent, but that does not mean absolutely zero pauses.

**Safepoint pauses are not caused only by GC.** The JVM may need safepoints/handshakes for other VM operations. When reading latency logs, look at the VM operation type, GC ID, elapsed time, and what the application is running.

## 16. GC roots, reference types, and retention decisions

A tracing collector cannot treat **every edge** like a normal strong reference. Java provides reference objects with distinct semantics:

| Type | Related rule | Effect on GC |
| --- | --- | --- |
| **Strong reference** | Normal reference from fields/locals/arrays | Keeps referent reachable if a valid path from roots exists |
| **SoftReference** | Referent may be cleared by GC based on memory sensitivity | Not a TTL or exact cache bound |
| **WeakReference** | Does not keep referent strong-live; can be cleared when weakly reachable | Suitable for some lookups/canonicalization, no guarantee on clear timing |
| **PhantomReference** | Used for cleanup lifecycle when object reaches corresponding state; `get()` is always null | Not used to read back the object like a cache value |
| **JNI handles** | Have separate local/global/weak global semantics | Native code must follow the contract for GC to manage references |

### Clearing differs from reclaiming and relocation

- **Mark:** determine liveness based on reachability and appropriate reference rules.
- **Clear weak reference:** replace the logical referent with null when GC conditions are met; not the object being copied to a new location.
- **Reclaim dead object:** return the memory of an object no longer needing to be kept to the allocator.
- **Relocate live object:** move a live object to a new location, preserving identity.

These are four different actions. Seeing `weak.get() == null` does not prove "GC compacted the heap"; seeing still-correct output also does not prove the real object was moved.

### Finalization and Cleaner

Do not rely on finalizers to manage files/sockets/database connections. Finalization has many issues and no clear deadline. Use `try-with-resources`, `AutoCloseable`, or explicit lifecycle code; `Cleaner` is a limited option for fallback native cleanup when designed appropriately. GC is not a service that calls `close()` at the exact business-required time.

## 17. Java 17: object identity is preserved regardless of whether GC moves it

Create **`IdentityAcrossGc.java`**:

```java
import java.util.IdentityHashMap;

public class IdentityAcrossGc {
    static final class Node {
        final int id;
        Node child;

        Node(int id) {
            this.id = id;
        }
    }

    static volatile Object allocationSink;

    public static void main(String[] args) {
        Node parent = new Node(10);
        Node child = new Node(20);
        parent.child = child;

        Node alias = parent;
        Node[] roots = {parent};
        IdentityHashMap<Node, String> names = new IdentityHashMap<>();
        names.put(parent, "same-object");

        int hashBefore = System.identityHashCode(parent);

        for (int i = 0; i < 512; i++) {
            allocationSink = new byte[16 * 1024];
        }

        System.out.println("alias=" + (alias == parent));
        System.out.println("array=" + (roots[0] == parent));
        System.out.println("childId=" + parent.child.id);
        System.out.println("lookup=" + names.get(alias));
        System.out.println("hashStable="
                + (System.identityHashCode(parent) == hashBefore));
    }
}
```

```bash
javac --release 17 IdentityAcrossGc.java
java IdentityAcrossGc
```

**Stdout:**

```text
alias=true
array=true
childId=20
lookup=same-object
hashStable=true
```

The program checks **Java reference semantics**, independent of which collector is active. GC **might not run**, or might run without the `parent` object being in the collection set; the array-creation loop **does not prove physical relocation**. `allocationSink` only keeps the most recently written array reachable through the volatile static field; the compiler/GC still has the right to make valid optimizations.

If run with a small heap and GC logging, it may be easier to observe some collections, but the final output must still be correct as long as the application does not encounter memory/resource errors. Do not try to read an address from `System.identityHashCode`.

## 18. Impact of live set, allocation rate, and fragmentation

A collector is not affected solely by **total heap size**. Especially important:

- **Live set size:** amount of bytes and objects to preserve after marking. Copying/compacting a large live set can take more work.
- **Allocation rate:** bytes allocated over time. Fast allocation causes more cycles/young pauses even if the final live set is not large.
- **Survival rate:** fraction of objects still alive when collection occurs; determines copying cost.
- **Reference graph complexity:** number of edges to scan, pointer density, and metadata.
- **Fragmentation:** how many free bytes exist **in sufficiently large spans**; lots of small free spaces may not help allocate a large object.
- **Headroom/to-space:** is there enough space in the destination region for surviving objects?
- **Concurrency/CPU budget:** concurrent marking/relocation contends for resources with the application.
- **Collector tuning/ergonomics:** region sizes, generations, thresholds, pause goals, parallel threads.

### Hypothetical numerical example

Suppose young regions have 300 MiB allocated and only 20 MiB of objects are still alive when collection happens. Copying 20 MiB can be beneficial if root scanning/barrier overhead and destination space are reasonable.

If another workload has 280 MiB of live objects out of 300 MiB, evacuation has to copy almost all live bytes; the cost balance changes. Do not turn an example into a law that "copy is always faster than mark-sweep" or "mark-compact is always slowest."

### Fragmentation does not mean immediate OOME

The allocator/collector can try looking elsewhere, reclaiming, compacting, expanding committed heap, or falling back depending on implementation. An `OutOfMemoryError` may be due to **genuinely running out of free memory**, **insufficient contiguous regions/to-space**, **large retained live set**, metaspace/native memory, or container limits. You must read the error type and logs before concluding.

## 19. Viewing GC logging on HotSpot Java 17

Enable Unified Logging with `-Xlog`:

```bash
java -Xms128m -Xmx512m -XX:+UseG1GC -Xlog:gc IdentityAcrossGc
```

For a more detailed phase breakdown, on builds supporting the corresponding tags/levels:

```bash
java -Xms128m -Xmx512m -XX:+UseG1GC -Xlog:gc*,gc+phases=debug IdentityAcrossGc
```

**There is no fixed GC stdout**: the number of collections, pause timings, phases, and heap occupancy depend on workload, OS, collector, JIT, and build. Running the example with a comfortably sized heap might even **produce no significant GC events**. Use logs to find actual behavior, not to fabricate a trace and present it as measured.

In G1 GC logs, you can see information about:

- Young/normal/mixed collections.
- Eden, survivor, and old regions before/after.
- Evacuate Collection Set / merge heap roots, copy/scan phases, reference processing.
- Concurrent marking phases, Remark/Cleanup.
- Pause durations and memory occupancy.

Log names change across JDK releases. Use **phase meanings** and experiments on the exact JVM being used as your basis, rather than writing a parser rigidly tied to a single log string.

### Other observation tools

```bash
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jstat -gc <PID> 1000 5
```

`<PID>` is a **process ID placeholder**, not a verified process. The `jcmd`/`jstat` commands require a running Java process and sufficient permissions; `IdentityAcrossGc` exits very quickly so there is usually no PID to attach to when you run commands afterward.

- `VM.flags` helps check VM/GC configuration.
- `GC.heap_info` reports heap/collector status per implementation.
- `jstat -gc` provides counters/occupancy/cycle stats per collector/JDK.
- `jcmd` may have other diagnostic commands; run `jcmd <PID> help` to see which commands are actually supported.

**A heap dump** is useful when you want to know why an object is still reachable, rather than fully describing GC copy/compact steps. **GC logs** show how collection behaves, rather than uniquely pointing out which object is the leak root.

## 20. Analyzing a real-world diagnostic scenario

Suppose a service has:

- Heap configured maximum 2 GiB.
- GC log: young collections getting more frequent, mixed cycles afterward, occasional Full GC.
- After-GC heap occupancy rising from 700 MiB to 1.7 GiB under an equivalent workload.
- Evacuation failure/to-space pressure messages at certain times.

A reasonable process:

1. **Check liveness/retention first:** is the live set growing due to caches, listeners, ThreadLocal, request queues, or intentional data growth? Take a histogram/heap dump when safe.
2. **Read GC logs:** is allocation rate increasing, young survival rate increasing, promotion/old occupancy increasing? Why did Full GC appear?
3. **Look for fragmentation/region pressure:** do collection sets still have enough destination space to evacuate? Are there many humongous allocations/regions?
4. **Evaluate GC policy:** are collector/heap sizing/headroom appropriate for pause goals and CPU/container budgets?
5. **Fix the application cause if the live set is no longer needed:** bounded cache, release listeners, remove ThreadLocal, shutdown resource owners.
6. **Re-check both throughput and latency:** fixing only to eliminate `OutOfMemoryError` while increasing pauses to several seconds may still fail operational goals.

**Increasing `-Xmx` can delay running out of space**, but if the application keeps retaining objects indefinitely, it does not fix a logical memory leak. Conversely, if the live set is legitimate and the heap is too small, you need to calculate actual capacity/headroom and off-heap memory in the container.

## 21. Fifteen misconceptions to avoid

| Misconception | Reality |
| --- | --- |
| "Mark frees objects by itself" | Mark only classifies liveness; reclaim/evacuation/compaction is needed |
| "An unmarked object at any time is garbage" | Marking has intermediate states; white may just not be scanned yet |
| "An A↔B cycle prevents tracing GC from freeing it" | A cycle not reachable from roots can still be reclaimed |
| "Mark-sweep always packs live objects together" | Non-moving sweep usually leaves holes and free lists |
| "Having large total free means a large object can be allocated" | External fragmentation may leave insufficient contiguous space |
| "Copy must copy the entire heap" | Usually only selected generation/regions, live objects |
| "Copying must always keep half the heap empty" | Two semispaces is one design; G1 uses selected regions |
| "Compact is sweep but deletes harder" | Compact **moves/packs live objects**, sweep mainly reclaims dead blocks |
| "GC moving an object changes `==` or identity hash" | Java-visible object identity must remain unchanged |
| "All Java 17 GCs use the same algorithm" | Serial, Parallel, G1, ZGC, Shenandoah combine them differently |
| "G1 concurrent marking means G1 concurrent evacuation like ZGC" | G1 Java 17 evacuates CSet mainly in STW pauses |
| "GC write barriers guarantee Java application thread safety" | GC barriers differ from `volatile`, locks, and happens-before |
| "A GC event proves a specific object X moved" | No; collection scope/relocation requires deeper evidence |
| "Mark-compact is always a Full GC" | There is compaction/evacuation by regions or phases depending on collector |
| "Large heap used is a certain heap leak" | Need post-GC live set, retention paths, and workload evidence |

## 22. Decision and performance analysis checklist

Before comparing a collector or reading a GC chart, ask yourself:

1. How many **live bytes** does the object graph have? Are caches/registries holding onto objects?
2. What fraction of objects die right after allocation?
3. Is the collection processing the **whole heap** or **young/old selected regions**?
4. Does **Mark** happen STW, parallel, or concurrent? What barrier model does it use?
5. Is dead memory reclaimed via **sweep/free list**, **evacuation**, or **compact**?
6. If relocating objects, how does the collector find the forwarding destination and **update/read references**?
7. Is there enough **to-space/headroom** for live objects?
8. Is fragmentation **small free blocks**, **humongous regions**, alignment, or allocator metadata?
9. Is most GC time spent on root scanning, reference processing, copying bytes, or compaction?
10. Is the goal to optimize **throughput**, **p99 pause latency**, or footprint?
11. Is the JVM/collector release actually Java 17? Do the docs and flags belong to that exact release?
12. Are conclusions proven with GC logs/JFR/benchmarks on a real workload or only by theory?

## 23. Self-check questions

**Question 1:** An object A has a path from a GC root, object B does not. What is marking used to determine?

**Answer:** A is reachable from the considered roots; B is not in the corresponding live set and can be reclaimed according to reference rules.

**Question 2:** After mark-sweep, total free is 10 MiB, but no free span is larger than 2 MiB. Is a 4 MiB request guaranteed to allocate successfully in that same region?

**No.** If 4 MiB contiguous is needed and there is no other region/compaction/expansion, external fragmentation causes allocation difficulty.

**Question 3:** What is the core difference between mark-sweep and mark-compact?

Mark-sweep generally leaves live objects in place and puts dead blocks into the allocator; mark-compact packs/moves live objects to create contiguous free space.

**Question 4:** A copying collector encounters two roots pointing to A. Does it create two new A objects?

**It must not create two independent Java object identities.** Forwarding/claim logic ensures references arrive at one logical destination.

**Question 5:** Why can copying be effective for the young generation?

Because in many workloads many objects die quickly; only a small live subset needs to be evacuated, source space is reclaimed quickly, and destination allocation can be simple.

**Question 6:** Are G1 concurrent mark and G1 evacuation the same phase?

**No.** Concurrent marking mainly evaluates liveness; selected-region evacuation is generally performed in STW collection pauses in G1 Java 17.

**Question 7:** Does `IdentityAcrossGc` printing all `true` prove `parent` actually changed address?

**No.** The program only checks the Java contract; GC may not have run or the object may not have moved.

**Question 8:** Can a GC write barrier replace `synchronized` to prevent data races?

**No.** GC barriers maintain collector invariants; Java concurrency requires appropriate JMM synchronization.

**Question 9:** How do ZGC and Shenandoah support concurrent relocation while Java still sees the right references?

By using a combination of forwarding metadata and barriers/remapping according to the algorithm/version, instead of requiring every reference slot to be eagerly fixed up in a global STW pause.

**Question 10:** Why can a Full GC be slow even when most objects are still alive?

Because tracing, updating references, and moving/compacting a large amount of live bytes still takes work, especially when memory headroom/parallelism is lacking.

## 24. Standard references

- [JVMS Java SE 17 — Run-Time Data Areas / Heap (`2.5.3`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): heap and object management according to the specification.
- [Java SE 17 Garbage Collection Tuning Guide — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): Serial, Parallel, G1, ZGC, and collector selection.
- [Java SE 17 Garbage Collection Tuning Guide — G1 Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): regions, marking, evacuation, collection sets, compaction fallback, fragmentation.
- [Oracle — Garbage-First Garbage Collector Tuning](https://www.oracle.com/java/technologies/g1gc.html): evacuation, remembered sets, and parallel copying in the G1 model.
- [JEP 333 — ZGC: A Scalable Low-Latency Garbage Collector](https://openjdk.org/jeps/333): concurrent marking/relocation, colored pointers/load barriers.
- [JEP 189 — Shenandoah: A Low-Pause-Time Garbage Collector](https://openjdk.org/jeps/189): concurrent evacuation and low-pause design.
- [Java SE 17 `Reference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html), [`WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html), [`SoftReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/SoftReference.html), [`PhantomReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html): reference reachability and clearing.
- [Java SE 17 `System.identityHashCode` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)): identity is not equivalent to object address.
- [Java SE 17 `jcmd` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html), [`jstat` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): heap diagnostics and GC counters.
- [Java SE 17 `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog`, GC/heap flags.

**Remember:** **Mark** finds objects to keep; **sweep** returns dead blocks to free space; **copy** moves live objects to a destination region; **compact** packs live objects to reduce fragmentation. No single algorithm is the entirety of modern GC: HotSpot combines marking, reference processing, evacuation, forwarding, barriers, and region/heap management per collector. Rely on **reachability, live-set size, fragmentation, memory headroom, and actual GC phases** to explain why a GC run reclaims effectively or runs into trouble.