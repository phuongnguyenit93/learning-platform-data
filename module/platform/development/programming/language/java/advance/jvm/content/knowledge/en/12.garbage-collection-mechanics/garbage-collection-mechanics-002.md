# Memory Fragmentation and the Trade-off Between Moving Objects and Reference Update Cost

## Lesson Objectives

A Java heap can still have many free bytes yet struggle to serve a new allocation request if **the free gaps do not match the allocator's size or policy**. That is the problem of **memory fragmentation**. A garbage collector (GC) can reduce fragmentation by **moving/compacting live objects**, but when an object's location changes, the runtime must ensure **every valid reference still finds that exact object**. Copying data, determining new locations, fixing or redirecting references, and synchronizing with application threads create a real trade-off in CPU, memory bandwidth, pause times, and heap headroom.

This lesson focuses on **GC mechanics and HotSpot**, without equating a Java reference to an immutable physical address. After this lesson, you will be able to:

- Distinguish **external fragmentation**, **internal fragmentation**, free-space topology, wasted capacity, and total free heap.
- Explain **mark–sweep**, **mark–compact**, and **copying/evacuation**, and how each strategy handles free gaps.
- Describe why moving an object forces the collector to handle **root references, references inside objects, and array elements**, and sometimes references outside the collected region.
- Distinguish **forwarding information**, relocation maps, barriers, remembered sets, card tables, and GC-root metadata; without treating them as the same mechanism.
- Understand why **an object with very many references** can be cheap to copy payload-wise yet expensive to maintain reachability/references for, whereas **a very large object with few references** can be expensive to copy even with few reference updates.
- Compare the implementation approaches of **Serial/Parallel, G1, ZGC, and Shenandoah** by specific version and collector.
- Understand the case of **G1 humongous objects**, leftover unusable space, evacuation failure, and Full GC.
- Use Java 17+ to run a compaction simulation and an example proving aliasing/identity remains intact, and read GC logs without relying on non-deterministic GC timing.
- Measure properly using **GC logs, JFR, jcmd, and JDK Mission Control**, avoiding treating high heap usage as definitive proof of fragmentation.

## 1. Where Does Fragmentation Come From?

Suppose an allocator has eight equal slots. After many objects are created and become unreachable, the simulated layout might look like:

~~~text
Before collection / after identifying dead objects:

index:  0   1   2   3   4   5   6   7
        +---+---+---+---+---+---+---+---+
state:  | A | . | B | . | C | . | D | . |
        +---+---+---+---+---+---+---+---+

A, B, C, D: live objects
.         : free memory slot

Total free: 4 slots
Largest contiguous free space: 1 slot
Request: allocate an object needing 3 contiguous slots
~~~

This is a **simulated memory-block model**, not how HotSpot necessarily lays out every object in the heap. For an allocator requiring a contiguous 3-slot region, 4 total free slots is not enough: **there is no gap long enough**. That is an example of **external fragmentation**.

If B, C, and D are moved next to A:

~~~text
After compaction:

index:  0   1   2   3   4   5   6   7
        +---+---+---+---+---+---+---+---+
state:  | A | B | C | D | . | . | . | . |
        +---+---+---+---+---+---+---+---+

Total free: 4 slots (unchanged)
Largest contiguous free space: 4 slots
The 3-slot request can now be satisfied
~~~

**Compaction does not create extra free bytes out of thin air.** It **rearranges live objects** to coalesce gaps into regions favorable for allocation. If dead objects were already identified and reclaimed beforehand, total free bytes can remain unchanged across the move step; the difference lies in **the shape of free space**.

### External Fragmentation

This is the condition where free space is split into many small pieces or into regions that do not satisfy allocation criteria. In a heap using **regions**, the problem also involves the ability to find enough contiguous regions, region selection policy, and the number of regions held by live/pinned/humongous objects.

### Internal Fragmentation

This is the portion of bytes consumed or left empty **inside an allocation unit** even though it holds no useful application data. Examples:
- Padding due to object alignment.
- Slots reserved but unused inside a block/array capacity.
- The remainder of the last region dedicated to a large object, unusable for other objects under that allocator's policy.

**Do not equate** all padding with external fragmentation. External is **hard-to-use gaps between allocations**; internal is **leftover space inside an allocation unit or reserved region**.

### "Free Heap" Has Multiple Meanings

| Metric | What it tells you | What cannot be concluded yet |
| --- | --- | --- |
| Committed heap − used heap | The difference as reported by the VM for used/committed | Do free slots fit a large allocation? |
| Total free bytes in a region | Total unused space | Is there enough contiguous space? |
| Largest contiguous free block | Largest free block according to the allocator | Can allocation succeed after GC/expansion? |
| Number of free regions | Number of completely free regions | Is there a contiguous run of regions for a humongous object? |
| Live-set size | How much memory must hold live objects | How much copy/update work is needed? |
| Heap fragmentation metric of a specific GC | Fragmentation level by the collector's heuristic | Does it have the same meaning as another collector's metric? |

Do not use a single `Runtime.freeMemory()` number to "prove" heap fragmentation. The API reports runtime-level figures and does not accurately represent the free-block topology of every collector.

## 2. Why Can Mark–Sweep Leave Holes?

The classic **mark–sweep** mechanism:

1. Start from **GC roots** and mark reachable objects along the graph.
2. Sweep the memory regions/metadata to be processed.
3. Reclaim objects that are no longer live.
4. Keep live objects at their old locations.

When many dead objects lie interspersed between live objects, mark–sweep can leave behind **many free holes**.

~~~text
Before: [A][X][B][Y][C][Z][D]   X/Y/Z unreachable
Sweep:  [A][ ][B][ ][C][ ][D]

Live objects remain in their old positions.
The free list or allocator needs to manage the holes.
~~~

**Conditional advantage:** it does not have to copy all live-object bytes just to compact. Objects that are not moved do not need reference updates because their addresses remain unchanged (ignoring other GC processing).

**In return:** the allocator may have to use free lists, block classification, coalescing, and face external fragmentation. Anti-fragmentation techniques such as coalescing adjacent free blocks help, but **cannot coalesce across a live object sitting in between** without moving it.

Not every non-moving GC always suffers severe fragmentation: an allocator can use size classes, segregated free lists, region management, allocation policies, and suitable GC heuristics. Nor does a GC having a sweeping phase necessarily mean it "never compacts anywhere".

## 3. Mark–Compact: Coalescing Free Space by Moving Live Objects

**Mark–compact** typically consists of:
1. Identifying live objects.
2. Computing or determining destination locations for live objects.
3. Moving object contents/metadata as needed.
4. Ensuring references pointing to those objects are updated/redirected to point to the right instance.
5. Having a larger free space or suitable free regions after compaction.

~~~text
Before:
  root1 ----> [A @slot0]  [hole]  [B @slot2]  [hole]
                              \____________/
                               fragmentation

Destination planning:
  A: slot0 -> slot0
  B: slot2 -> slot1

After:
  root1 ----> [A @slot0][B @slot1][free][free]
                           ^
                           |
                   old refs to B are handled
~~~

**Benefits:**
- Can reduce external fragmentation, helping serve large allocation requests.
- After compaction, a form of bump-pointer allocation can be efficient.
- Object locality may change positively if the allocator lays them out well, though there is no guarantee all related objects sit next to each other.

**Costs:**
- Reading/writing bytes of live objects that need to move, consuming CPU and memory bandwidth.
- Finding/recording new locations or managing forwarding metadata.
- Handling references to moved objects.
- Coordinating with application threads, which may require **stop-the-world (STW)** or barriers/handshakes for concurrent collectors.
- May require destination space or auxiliary metadata; in-place and copying algorithms have different memory headroom costs.

**There is no mandatory "number of reference updates = number of moved objects".** An object referenced by many roots/fields/array slots can have millions of references. The collector must ensure every valid reference resolves correctly, though the approach can be updating each slot, remapping on read, remembered sets, or other mechanisms depending on the GC.

## 4. Copying Collection and Evacuation

A collector can choose **copying/evacuation**: moving live objects from source regions to other destination regions, then **reclaiming the entire source region** once safety conditions are met.

~~~text
Source region (CSet):             Destination region:

[A live][B dead][C live]  ==>    [A'][C'][free ...]
           |                        ^
           |                        |
           +-- if references point to A/C
               must be redirected to A'/C'
~~~

Advantages of evacuation:
- Leaves the source region completely empty, suitable for **region reuse**.
- Avoids keeping many holes inside the successfully evacuated source region itself.
- Can collect subsets of regions incrementally, rather than always compacting the entire heap.

Costs:
- **Copying live bytes** of the selected regions.
- **Destination space/headroom** to hold live objects while they are being moved.
- **Reference fixing/barrier work**.
- Possible **evacuation failure** if destination space is insufficient or limited by pinning/collector-specific constraints.
- If selection is poor and a region has very many live bytes, the copy cost is large while reclaimed capacity is small.

### Why Does "Garbage-First" Care About the Garbage Ratio?

Suppose two regions have the same size:
- Region P: only 10% live, 90% garbage.
- Region Q: 95% live, 5% garbage.

If evacuating P, the collector copies few live bytes and reclaims a lot of memory. If evacuating Q, it must copy very many bytes to recover little free space. This is an intuitive criterion that makes region-based collectors prioritize regions with **lots of garbage and low connectivity cost**. Actual decisions still rely on many other heuristics such as reference scanning, pause targets, and remembered-set cost.

## 5. Moving an Object Must Not Change Its Identity

In Java source, a reference variable **is not an immutable heap address managed by the application**. For example:

~~~java
Person p = new Person();
Person alias = p;
System.out.println(p == alias); // true
~~~

This is an illustrative snippet requiring a suitable `Person` class. If the GC moves the object that `p` and `alias` refer to, Java must still observe **`p == alias` as true** after the collection, provided no variable reassignment changed the references.

The collector may change where the physical object is stored from "old address" to "new address", but **logical object identity must be preserved**:
- Reference comparisons/`==` for the same object remain true.
- `Object.equals`, if not overridden, retains identity semantics.
- `System.identityHashCode(object)` must remain consistent over the object's lifetime per its contract, not simply "change because the address moved".
- Monitor/lock state and object metadata must preserve correct semantics; how information is preserved depends on HotSpot/collector.
- Field contents must be preserved according to the Java Memory Model and GC rules.

**Do not treat `System.identityHashCode` as a RAM address**, nor use default `toString()` to measure object location. The hash code is not a pointer; it can collide between different objects.

## 6. Which References Are Affected When an Object Moves?

A referenced object can have incoming paths from:

- **Local variables/operand stack** in JVM frames of active threads.
- **Instance reference fields** of other objects.
- **Static reference fields** of runtime classes/interfaces.
- **Reference-array elements**.
- **JNI/native handles** or VM-managed roots/runtime references.
- Internal GC/VM structures, code metadata, and reference types with special contracts.

~~~text
Root: local r -----------+
                         |
Root: static cached -----+----> [Customer OLD]
                         |         |
Object A.ref ------------+         +--> [Address]
                         |
Array refs[19] ----------+

Move Customer OLD -> Customer NEW:

Root r ------------------+
                         |
static cached -----------+----> [Customer NEW]
                         |         |
Object A.ref ------------+         +--> [Address]
                         |
Array refs[19] ----------+
~~~

**The diagram illustrates the logical outcome**, without requiring HotSpot to update every root/field at the exact same instant. A concurrent collector may temporarily use forwarding metadata, load barriers, remapping, and mechanisms ensuring every mutator access sees the right object while relocation is in progress.

### The Cost of Reference Updates Depends on the Graph

If object X is referenced by only one reference in the root set, the number of logical references to handle can be small. If X is a "hot shared object" appearing in a million elements of arrays/collections, there can be very many edges to X. The collector still has to preserve aliasing after relocation; it may pay the corresponding scanning/updating/remapping cost.

Therefore, **number of moved objects**, **bytes copied**, **number of references/edges involved**, **how references are distributed across regions**, and **number of roots** are distinct variables that affect CPU and pauses differently.

## 7. Forwarding: Knowing Where an Object Moved From and To

To redirect references, a moving collector usually needs a way to find the **new location** from the **old location**. There are several strategies:
- Forwarding information written or encoded in an appropriate place.
- Mapping tables/relocation metadata scoped to the collector.
- References carrying metadata or using read/load barriers to redirect to the new object.
- Updating reference slots during scanning or at the time a mutator reads a reference.

A simple diagram:

~~~text
Old location -> New location

0x1000 -> 0x8000  (A moved)
0x2000 -> 0x8020  (B moved)
0x3000 -> 0x9000  (C moved)

reference slot holding old B
    |
    +--> forwarding/relocation info
                 |
                 v
         valid reference to new B
~~~

These are **simulated addresses**, not real VM addresses. HotSpot's reference representation can use compressed oops or its own metadata; do not assume a single pointer width.

### Why Can't You Just Copy the Object and Ignore References?

If you only copy B to a new location while references still point to the old memory location, those references could become dangling or point to reused storage. The JVM needs a GC protocol so every valid reference continues to access the right B.

That **does not mean Java APIs let you see individual references being fixed**. A moving GC is managed by the VM; Java source continues working with object identity, not raw heap addresses.

### Forwarding Alone Is Not Enough for Concurrent Collection

When application threads (mutators) keep running while the collector moves objects, races can occur:
- A mutator reads an old reference right after the collector moves the object.
- A mutator writes a field into an object that is moving or has moved.
- A root/reference is updated concurrently with GC.
- An internal reference from an uncollected region points into a region being evacuated.

A concurrent collector must coordinate using **barriers**, synchronization/handshakes, forwarding/remapping, and proper ordering. Merely creating an old→new mapping is not enough to prove the algorithm thread-safe.

## 8. Roots, Oop Maps, Remembered Sets, and Card Tables Are Different

Terms that are easily conflated:

| Concept | Main purpose | What it is not |
| --- | --- | --- |
| **GC roots** | Starting points of reachability such as thread references, static roots, handles... | A list of every reference field in the heap. |
| **Internal oop maps/stack maps** | Help the VM know where references sit in compiled/interpreted frames at appropriate safepoints | A public, fixed Java API across all collectors. |
| **Forwarding information** | Identifies or leads to the new location of a moved object | The set of all inbound reference edges. |
| **Card table** | Tracks memory portions where writes may have changed reference relationships | An exact list of each individual reference. |
| **Remembered set** | Set of locations/regions that may contain external references into a region/regions to be collected | A tool that automatically fixes all references without scanning. |
| **Read/load barrier** | Handles certain GC conditions when a mutator reads a reference, potentially involving relocation/remapping | Always present in every collector and every JVM. |
| **Write barrier** | Assists GC in tracking updates when a mutator writes refs, e.g., marking or cross-region refs | Not the `volatile` keyword in Java source. |

**Oop** is HotSpot terminology for *ordinary object pointer* or object reference representation. Oop maps let the VM know what needs to be treated as object refs when scanning stacks, which does not mean a source variable necessarily sits at a specific stack address if the JIT has optimized it.

### How Does a Remembered Set Reduce Full-Heap Scanning?

Suppose G1 is evacuating a **collection set (CSet)** consisting of several regions. References to objects in the CSet can reside in:
- Roots/frames/static state.
- Objects inside the CSet itself.
- Objects in **regions outside the CSet**.

If finding incoming references from outside required scanning every object in the entire heap on every young GC, the cost would be huge. **Remembered sets/card marking** help narrow down the locations that need inspection, though work is still required to locate the actual slots/relationships.

G1 uses a **post-write barrier** to track cross-region changes and maintain remembered-set-related metadata per the collector algorithm. This is **GC bookkeeping**, not application synchronization. Its cost exists even when no GC pause is occurring.

Do not say "a remembered set holds every exact location and always updates refs automatically": entries can be **coarse-grained card locations** and require scanning to find specific references.

## 9. Java 17+ Example: Simulating Compaction and Reference Updates

To get reproducible results **without depending on GC timing**, we build a small model:
- An array `slots` simulates eight heap slots; -1 is an empty slot.
- `edges[i]` simulates a reference from the object at slot `i` to another slot.
- `roots` simulates root locations pointing to objects.
- `forward[oldIndex] = newIndex` is the relocation table.
- After compaction, both root indices and edges must be fixed to preserve the graph.

**This is only an algorithmic model in Java**, not how the JVM exposes/fixes raw memory addresses.

Create file **`CompactionSimulation.java`**:

~~~java
import java.util.Arrays;

public class CompactionSimulation {
    static int largestRun(int[] slots) {
        int best = 0;
        int current = 0;
        for (int slot : slots) {
            if (slot == -1) {
                current++;
                best = Math.max(best, current);
            } else {
                current = 0;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        final int empty = -1;

        // Four live objects at indices 0, 2, 4, 6.
        int[] slots = {10, empty, 20, empty,
                       30, empty, 40, empty};

        // Object at 0 -> 4; object at 2 -> 6.
        int[] edges = {4, empty, 6, empty,
                       empty, empty, empty, empty};

        // Two root references, pointing to index 0 and index 4.
        int[] roots = {0, 4};

        System.out.println("before=" + Arrays.toString(slots));
        System.out.println("largestFreeBefore=" + largestRun(slots));

        int[] forward = new int[slots.length];
        Arrays.fill(forward, empty);

        int[] packed = new int[slots.length];
        int[] newEdges = new int[slots.length];
        Arrays.fill(packed, empty);
        Arrays.fill(newEdges, empty);

        int liveCount = 0;
        int movedCount = 0;

        // Step 1: compute new locations and move data.
        for (int oldIndex = 0; oldIndex < slots.length; oldIndex++) {
            if (slots[oldIndex] != empty) {
                forward[oldIndex] = liveCount;
                packed[liveCount] = slots[oldIndex];

                if (oldIndex != liveCount) {
                    movedCount++;
                }
                liveCount++;
            }
        }

        // Step 2: fix root references.
        for (int i = 0; i < roots.length; i++) {
            roots[i] = forward[roots[i]];
        }

        // Step 3: fix links inside moved objects.
        for (int oldIndex = 0; oldIndex < slots.length; oldIndex++) {
            if (slots[oldIndex] != empty) {
                int newIndex = forward[oldIndex];
                int oldTarget = edges[oldIndex];
                newEdges[newIndex] =
                        oldTarget == empty ? empty : forward[oldTarget];
            }
        }

        System.out.println("after=" + Arrays.toString(packed));
        System.out.println("roots=" + Arrays.toString(roots));
        System.out.println("links=" + Arrays.toString(
                Arrays.copyOf(newEdges, liveCount)));
        System.out.println("moved=" + movedCount);
        System.out.println("largestFreeAfter=" + largestRun(packed));
    }
}
~~~

Run:

~~~bash
javac --release 17 CompactionSimulation.java
java CompactionSimulation
~~~

**Exact stdout:**

~~~text
before=[10, -1, 20, -1, 30, -1, 40, -1]
largestFreeBefore=1
after=[10, 20, 30, 40, -1, -1, -1, -1]
roots=[0, 2]
links=[2, 3, -1, -1]
moved=3
largestFreeAfter=4
~~~

**Part-by-part explanation:**

1. Initially there are 4 empty slots, but the largest contiguous free run is only length 1.
2. `forward` receives mappings 0→0, 2→1, 4→2, 6→3. **3 objects change position**.
3. `roots` changes from [0,4] to **[0,2]** so the second root still points to object ID 30, without being confused with another object.
4. The edge of object ID 10 previously pointed to old index 4, and must now point to **new index 2**. The edge of ID 20 pointed to old index 6, and now becomes **new index 3**.
5. `links=[2,3,-1,-1]` shows that **reference updates** are independent of copying data.
6. After compaction there are still 4 free slots, but the contiguous run is length 4, enabling a new allocation needing three slots.

**Intentionally omitted:** real GC roots, object identity metadata, concurrency/barriers, JNI handles, remembered sets, dynamic object sizes, or GC heuristics. The program only illustrates **old→new mapping logic and edge updates**.

### What Bug Is "Forgetting to Update a Reference" in the Model?

If we move ID 30 from index 4 to index 2 while keeping root value 4, the root will look into an **empty slot** after compaction. If we keep the edge from ID 10 to index 4, the logical object graph is already corrupted. A real GC must never let a Java program observe this broken state after a collection completes.

## 10. Java 17+ Example: Identity Unchanged When GC Operates

A Java application **does not need to and must not** fix reference values itself when HotSpot moves objects. An example testing deterministic semantics:

Create file **`IdentityInvariantDemo.java`**:

~~~java
public class IdentityInvariantDemo {
    static final class Node {
        final String label;
        Node next;

        Node(String label) {
            this.label = label;
        }
    }

    public static void main(String[] args) {
        Node first = new Node("first");
        Node second = new Node("second");

        first.next = second;
        Node alias = first;

        // Do not call System.gc(): the test does not rely on GC timing.
        System.out.println("sameRoot=" + (first == alias));
        System.out.println("sameTarget=" + (first.next == second));

        first = null;
        System.out.println("aliasLabel=" + alias.label);
        System.out.println("linkedLabel=" + alias.next.label);
        System.out.println("sameTargetAfter=" + (alias.next == second));
    }
}
~~~

Command:

~~~bash
javac --release 17 IdentityInvariantDemo.java
java IdentityInvariantDemo
~~~

**Exact stdout:**

~~~text
sameRoot=true
sameTarget=true
aliasLabel=first
linkedLabel=second
sameTargetAfter=true
~~~

Notes:
- The line `first = null` only changes **one local reference**; it does not make the `first` object disappear while `alias` still points to it.
- Even when a GC moves objects at an appropriate time, the correctness of references and comparisons must be preserved.
- Running this program **does not prove that a GC or relocation occurred**. It only verifies the Java semantics that the GC must uphold.

Do not use `System.gc()` as a guarantee that compaction will happen or that an object will be relocated. That call promises neither a specific GC cycle nor moving an individual instance.

## 11. Cost of Moving: Not Just Object Count

Cost dimensions that generally need separate consideration:

| Quantity | Primary impact |
| --- | --- |
| **Bytes of live objects to copy** | Memory bandwidth, CPU cycles, cache traffic |
| **Number of objects to relocate** | Forwarding/relocation bookkeeping, header/metadata handling |
| **Number of reference slots/root slots to process** | Scanning, reference remapping, update work |
| **Number of cross-region edges** | Remembered-set/card scanning or equivalent overhead |
| **Live ratio in selected regions** | Reclaimed capacity per byte copied |
| **GC headroom/destination capacity** | Evacuation success likelihood and memory pressure |
| **Mutator write/read rate** | Barrier overhead and complexity when GC runs concurrently |
| **Pinning/humongous regions** | Restrictions on moving/reclaiming certain regions |
| **Pause-time/CPU budget** | Which regions are selected; acceptable level of concurrent work |

### Two Contrasting Scenarios

**Scenario A: large object, few inbound references.** A multi-MB `byte[]` might be referenced by only a single cache entry. Copying the entire payload has high memory bandwidth cost; updating one logical reference can be relatively cheap.

**Scenario B: small object, very many inbound references.** A few-dozen-byte object pointed to by hundreds of thousands of array slots. Copying the object payload is very cheap, but the GC must ensure many references remain valid. Algorithms using remapping/barriers may pay the cost differently compared to updating all slots at STW.

**Do not claim exact O(R) for every GC:** an algorithm that directly scans and fixes all inbound slots does work proportional to the slots examined; another collector may lazy-fix and amortize the cost across mutator reads. Complexity and constant factors depend on the implementation.

### Copy Cost and Locality

Moving objects can improve locality in some cases, but can also:
- Increase cache traffic and pressure on memory bandwidth.
- Dirty many memory pages.
- Cause page faults/memory commits if destination pages are needed.
- Invalidate cache lines holding old data.
- Require synchronization/safepoints so threads do not see an object in a wrong state.

Do not assume "compacting always speeds up access": how well newly grouped objects perform depends on the collector, access patterns, and workload.

## 12. G1: Selecting Regions for Evacuation and Partial Compaction

**G1 (Garbage-First)** is a **region-based, generational** collector in HotSpot. The heap is divided into **regions**; eden/survivor/old are sets of regions by role, without requiring each generation to be a contiguous physical address range.

During young/mixed collections, G1 selects a **Collection Set (CSet)** of target regions and then:
1. Identifies eligible live objects.
2. Copies/evacuates live objects from the CSet to appropriate destination regions.
3. Processes references from roots and outside the CSet, using remembered-set/card tracking and related mechanisms.
4. After successful evacuation, **reclaims the source regions** for reuse.

Moving live objects helps compact collected areas incrementally. G1 tries to balance **reclaimed capacity** and **pause-time target**, though the target is only a soft goal, **not a hard deadline**.

### A Region With Many Live Objects Is Not an Ideal Candidate

Evacuating a 95% live region requires copying nearly the entire region while recovering little garbage. Therefore, the collector uses live fraction and connectivity/work prediction to evaluate collection efficiency. If the heap constantly holds many long-lived objects, copying them on every collection is also expensive.

### Remembered Sets Are a Trade-off

G1 avoids scanning the entire heap when collecting a subset of regions, but pays the cost of **maintaining and scanning remembered sets**. Write barriers and card refinement can increase CPU overhead on application/GC threads. A workload with many cross-region references or dense mutation can increase this kind of cost.

### G1 Evacuation Failure

When destination space is insufficient for objects that need to move or collector-specific constraints apply, evacuation can fail. G1 has failure-handling paths and can fall back to a **Full GC** with expensive compaction if heap pressure is severe.

Do not interpret every log containing the word "evacuation" as an error: **evacuation is normal G1 operation**, whereas `Evacuation Failure` is the signal worth investigating.

## 13. Humongous Objects: G1's Special Fragmentation Case

Per G1 documentation, an object sized **at least half a region** is considered **humongous**. It is normally allocated into a sequence of **contiguous humongous regions** in the old generation and does not move during normal evacuation pauses.

**Illustrative** example with a 2 MiB region size:
- The humongous threshold is around 1 MiB (actual object size includes VM header/layout).
- An object around 1.1 MiB can occupy an entire 2 MiB region, making the remaining ~0.9 MiB hard to use for normal allocations in that region.
- An object around 2.1 MiB can require two contiguous regions, totaling 4 MiB; the remainder of the last region cannot be used as an independent free region.
- Many large arrays living and dying interspersed can make finding contiguous humongous regions harder even when the heap still has free capacity by some metrics.

**The numbers are only illustrative mental math**: actual object sizes have headers/alignment, and heap regions and policies can differ. Do not try to turn the example into a fixed OOME formula.

G1 normally reclaims humongous objects only when it concludes they are dead via appropriate mechanisms; some arrays can be **eagerly reclaimed** by heuristics. Humongous objects are usually **not copied during normal evacuation**; moving them is a rare/last-resort path in certain collection modes/versions.

**Trade-off:** not copying huge arrays reduces copying cost, but can increase **wasted region tail** and limit compaction, leading to pressure on free contiguous regions.

### Do Not Confuse With "The Java Heap Has 2 GiB Free, So a 1 GiB Object Can Definitely Be Allocated"

Success also depends on:
- `-Xmx`, actual committed/free heap.
- Number of available contiguous regions, region size.
- Collector policy for large allocations.
- Live-set occupancy, GC timing, and applicable native/OS constraints.
- Memory headroom for both application allocations and GC work.

Another collector may handle very large objects differently from G1; do not apply G1's humongous rules to every GC.

## 14. Comparing GC Approaches in HotSpot

| Collector / algorithm | Strategy related to moving | Strengths | Costs/risks |
| --- | --- | --- | --- |
| **Classic mark–sweep** | Reclaims dead objects, may keep live objects in place | Little live-data copying | External fragmentation, free-list management |
| **Mark–compact** | Compacts live objects, fixes references | Coalesces free space, helps future allocations | Pause/copy/update work and metadata |
| **Copying / semi-space** | Copies live objects to destination | Source becomes a large free area after copying | Needs destination memory, copies live bytes |
| **Serial GC** | Young collection copying; old collection usually compacts depending on collector/version | Simple, suitable for small workloads in some cases | STW pauses, limited parallelism |
| **Parallel GC** | Parallel young copying and old compaction in appropriate phases | Prioritizes throughput across multiple cores | Has STW and copy/update work |
| **G1** | Region evacuation/partial compaction, remembered sets | Balances throughput and pause time, incremental regions | RSet/barrier overhead, humongous fragmentation, evacuation failure |
| **ZGC** | Concurrent marking/relocation with metadata/barriers by version | Low pause targets on large heaps | Concurrent CPU, barriers, allocation headroom, throughput trade-off |
| **Shenandoah** | Concurrent evacuation/compaction with barriers depending on version | Reduces GC work inside STW | Concurrent CPU/bandwidth, barrier overhead, availability depends on OpenJDK build |

**Version note:** there is no single fixed implementation across all of Java 17/21/26. For ZGC, details of generational mode and barriers/metadata change across JDK releases; for Shenandoah, availability/flags vary by JDK distribution and release. Avoid saying "every concurrent collector never pauses" or "G1 never moves humongous objects".

### Stop-the-World vs. Concurrent Relocation

A **STW moving collector** can pause mutator threads while updating references to avoid races, in return pauses can grow with live/edge workload. A **concurrent moving collector** lets much of the moving work happen concurrently with mutators, but must pay barrier/coordination costs and headroom, while still potentially having short pauses.

This does not mean concurrent is always faster:
- A **throughput-oriented** workload may benefit from longer pauses with lower total overhead.
- A **latency-sensitive** service may prefer a concurrent collector even if it needs more CPU/memory.
- When the system is already near 100% CPU or the heap is too tight, concurrent GC struggles to keep up with the allocation rate.
- Tuning must be measured on the real workload and SLA.

## 15. Pinning and Regions That Cannot Be Moved Immediately

Certain runtime/native interoperability conditions can make a collector **unable to freely move** an object or region at all times. For example, situations involving **JNI critical access** and pinning can place constraints on an array/object currently accessed by native code.

Consequences depend on the collector:
- Keeping the object in place during a collection phase.
- Skipping or delaying evacuation for the affected region.
- Having to process references/memory along another, slower path.
- Making some regions less likely to become free regions immediately.

**Do not claim every JNI reference pins an object**: JNI handles are usually managed by the VM, while specific pinning depends on the API, collector, and version. For example, `GetPrimitiveArrayCritical` has a special contract; how HotSpot implements it requires checking the version/GC.

Do not use a Java object's address as a stable pointer for native code without following the proper JNI/Panama/Memory API contract. Java references are not a raw ABI that allows holding physical heap addresses across arbitrary GCs.

## 16. Fragmentation, OOME, and Differences From a Memory Leak

Fragmentation and leaks can have similar symptoms but different causes:

| Symptom | Possibilities to check |
| --- | --- |
| Live heap very high, many objects still reachable | Retention/leak or legitimately large data |
| Heap has free bytes yet a large allocation still struggles | Fragmentation, contiguous-region requirement, humongous allocation policy |
| Continuous GC and frequent Full GCs | High live-set, high allocation rate, insufficient headroom, evacuation failure |
| OS/RSS memory does not drop after GC | Heap still committed, native memory, collector uncommit policy; does not imply a leak |
| Pauses grow when live ratio is high | Copy/scan/reference update work or other collector heuristics |
| GC logs show many humongous regions | Large-object pressure, wasted tail, allocation/fragmentation risk |
| One large object retains a large graph | Retained heap, not necessarily external fragmentation |

**A memory leak (in Java terms)** is usually a situation where unintended references keep objects reachable. **Fragmentation** is a problem of free-space organization or internal waste, even when some objects have truly died/been reclaimed.

Increasing `-Xmx` can help provide more headroom, but should not be treated as the only or always-correct solution. If live data is too large relative to the heap limit, compaction will not solve the problem; reducing the live set requires changing ownership/lifetime/data representation or the heap budget.

## 17. Measuring Properly With GC Logs, JFR, and HotSpot Tools

Start with **measurements rather than assuming fragmentation**. On HotSpot Java 17+, you can enable Unified GC Logging:

~~~bash
java -Xms256m -Xmx512m -Xlog:gc*:file=gc.log:time,uptime,level,tags CompactionSimulation
~~~

The command illustrates running the compiled Java example from section 9 using the default classpath in the current directory. The `gc.log` file and exact numbers depend on the JVM/OS/heap/load; **there is no single fixed GC log output**. A simulation that allocates little memory may **produce no GC events at all**, which is completely normal.

### Signals in G1 GC Logs

| Log content | Cautious interpretation |
| --- | --- |
| `Pause Young (Normal) (G1 Evacuation Pause)` | Normal young evacuation activity. |
| `Pause Young (Mixed)` | G1 may collect additional selected old regions. |
| `Evacuation Failure` | Collector hit constraints while evacuating; inspect headroom/pinning/collector-specific diagnostics. |
| `Pause Full (G1 Compaction Pause)` | STW full heap compaction, usually worth investigating if it affects SLA. |
| Humongous region counters | Large-object pressure and occupancy per the log, not sole proof of fragmentation. |
| Region/heap usage before-after GC | Suggests live-set and reclaim efficiency, does not show the full object graph. |

**Tag names and messages** can change across JDK/GC flags; do not write a production parser against an unspecified log format unless you control the build and have tests.

### jcmd / JFR / JMC

Example commands supported on HotSpot; replace `PID` with the real process ID:

~~~bash
jcmd PID GC.heap_info
jcmd PID GC.class_histogram
jcmd PID JFR.start name=GCStudy settings=profile duration=60s filename=gc-study.jfr
jcmd PID JFR.check
~~~

- `GC.heap_info`: heap information; not guaranteed to provide a universal "fragmentation percentage".
- `GC.class_histogram`: counts classes/instances/bytes at a point in time; does not by itself determine free-block topology.
- **Java Flight Recorder (JFR)**: events for GC pauses, allocations, and VM activities when enabled per configuration.
- **JDK Mission Control**: analyzes recordings, useful for finding GC/heap/CPU hotspots.
- **Heap dump + dominator tree**: helps find reachable objects and retainers, especially when suspecting a leak rather than fragmentation.

**Warning:** histograms, heap dumps, or recording configurations can impact load; heap dumps contain sensitive application data. Collect only when authorized and protect the files.

### Example Troubleshooting Sequence

1. Identify the actual collector (G1/ZGC/Parallel/...) and JDK build.
2. Record `-Xms`, `-Xmx`, heap usage, allocation rate, live set, and GC pause distribution.
3. For G1, observe humongous regions, collection set, evacuation failure, Full GC, and young/mixed cycles.
4. If the live set is near `-Xmx`, check **retention** and heap headroom first before calling it fragmentation.
5. If fragmentation/humongous pressure is severe, check **large array sizes**, ring buffers/caches, and allocation size distribution.
6. When testing tuning options, save a baseline and compare **throughput, p95/p99 latency, GC CPU overhead, RSS, and OOME risk**.
7. Do not change many JVM flags simultaneously if you want to know which change helped.

## 18. Trade-off Metrics to Compare

A collector or configuration is not just "GC pause time". You need a multi-objective view:

| Goal | What can improve | What trade-off may arise |
| --- | --- | --- |
| Less fragmentation | Copy/compact more frequently | CPU/bandwidth, reference update work |
| Short pauses | Concurrent relocation, choosing smaller regions | Barrier overhead, headroom, higher total CPU |
| High throughput | Fewer barriers, batching STW work | Larger pause tail |
| Small heap | Limiting headroom, reducing committed memory | Evacuation failures, allocation stalls, GC frequency |
| Fast allocation | TLAB/bump pointer, large free regions | Reserve/copy/GC overhead later |
| Reduce large-object pressure | Appropriate reuse/batching/chunking | Code complexity, data may need to be copied differently |
| Less retention | Limiting root references/long-lived caches | Higher cache misses/application compute |
| Increase locality | Compacting or storing data contiguously | Copy cost and representation changes |

**Do not equate throughput with latency.** A service can achieve high throughput yet have long STW pauses causing poor p99 latency. A low-pause collector may consume more CPU and headroom, lowering peak throughput. Decisions must align with operational requirements.

## 19. Common Misconceptions

| Misconception | Accurate explanation |
| --- | --- |
| "If total free bytes are enough, a large allocation will definitely succeed." | A sufficiently large contiguous free space or contiguous regions may be required. |
| "GC collecting dead objects automatically eliminates all fragmentation." | Sweep reclamation differs from compaction; collector policy can leave holes/waste. |
| "Compaction increases total free bytes." | It mainly changes **the shape of free space**; reclaiming garbage is related but distinct work. |
| "Moving an object only requires copying bytes." | References/roots/barriers/metadata must preserve semantic integrity. |
| "When an object is moved, only one reference needs updating." | There can be many aliases and inbound edges from multiple roots/fields/arrays. |
| "Every reference is updated by a full-heap STW scan." | Depends on the GC; there are remembered sets, forwarding, barriers, concurrent remapping. |
| "G1 is just a non-moving mark–sweep." | G1 uses evacuation/copying of live objects in selected regions. |
| "G1 always moves humongous objects just like young objects." | Humongous objects use contiguous regions and are normally not evacuated in regular pauses. |
| "G1 Evacuation Pause means a GC error." | Evacuation is normal operation; *Evacuation Failure* is what needs investigation. |
| "A moving GC changes `System.identityHashCode`." | Identity hash semantics must be preserved; the hash is not an address. |
| "A Java reference is a fixed user-held heap address." | The VM manages reference representation and object relocation. |
| "A remembered set is an exact list of every reference slot." | It can use coarse-grained card info requiring further scanning. |
| "Concurrent GC never needs stop-the-world." | There are still safepoints/pauses/handshakes depending on the collector; it only reduces STW work. |
| "The more aggressively GC compacts, the higher the throughput." | Compaction has copy/CPU/bandwidth/barrier costs; it must be measured. |
| "Small objects are always cheap because only a few bytes are copied." | Many inbound refs/metadata and large object counts still cost. |
| "Large objects with few refs cost GC nothing." | Copying large byte payloads can be very expensive; G1 humongous also has region waste. |
| "High heap usage means fragmentation." | It can be live-set or retained objects; metrics must be checked. |
| "Setting a field to null compacts the heap immediately." | It only severs a reference edge; GC scheduling/compaction is not promised. |
| "Running `System.gc()` gives deterministic compaction." | There is no guarantee of moving objects or collection timing. |

## 20. Thought Exercises With Solutions

**Question 1.** A heap has 200 MiB free scattered across two hundred 1 MiB gaps. An allocator needs 8 MiB contiguous. Is there enough memory?

**Answer:** **Not necessarily**. Total free exceeds the request, but there is no 8 MiB segment. This is an example of external fragmentation in an allocator model requiring a contiguous block.

**Question 2.** Compaction turns 200 MiB of scattered free space into one 200 MiB gap. Has it "reclaimed an extra 200 MiB"?

**Answer:** No. It **coalesced free space**; it did not increase the free-byte count by itself.

**Question 3.** When GC moves B from its old location to a new one, variable `x` and field `a.b` both point to B. Is fixing only `x` enough?

**Answer:** No, the collector must also ensure `a.b` continues to point to the right B, according to the collector's update/remap mechanism.

**Question 4.** One 8 KiB object with one inbound reference and one 32-byte object with one million inbound references. Which object is "more expensive to move"?

**Answer:** You cannot conclude from size or reference count alone. The 8 KiB object is more expensive in bytes copied, while the 32-byte object can be expensive in reference processing; it depends on the GC and algorithm.

**Question 5.** Why can mark–sweep leave holes?

**Answer:** It can reclaim garbage while leaving live objects in place, causing free blocks to be interspersed among live objects.

**Question 6.** How does evacuation help coalesce free space?

**Answer:** By copying live objects out of selected source regions and reclaiming the entire source regions upon success.

**Question 7.** Is G1's concurrent marking completely STW?

**Answer:** No. G1 has phases concurrent with mutators, though evacuation pauses are STW and Full GC can have long STW pauses.

**Question 8.** What is G1's remembered set used for?

**Answer:** It helps narrow down finding refs from outside the collection set into regions being collected, instead of scanning every object in the entire heap on every pause.

**Question 9.** Why can humongous objects increase wasted capacity in G1?

**Answer:** They occupy one or more contiguous regions; the remainder of the last region may be unusable for other allocations until the object is reclaimed.

**Question 10.** Does a program printing `true` from `a == b` before and after GC prove the GC did not move the object?

**Answer:** No. Identity is preserved by the VM even when the object has moved.

**Question 11.** Does a concurrent collector reducing pauses get CPU for free?

**Answer:** No. Barriers/coordination and concurrent work can consume CPU, memory bandwidth, and headroom.

**Question 12.** A heap has a live set at 95% of the limit with few holes. Why can Full GC/OOME still happen?

**Answer:** Insufficient reclaimable space or destination/headroom for allocation/evacuation, even though external fragmentation is not the primary cause.

**Question 13.** When confirming a memory leak, is a class histogram enough?

**Answer:** Not yet. A histogram gives counts and bytes per class, whereas a dominator tree/GC-root paths help identify what holds the references.

**Question 14.** Should you obtain an object's address using non-standard techniques and hold it across a moving GC?

**Answer:** No. A Java reference is not a stable physical pointer; you must use APIs/JNI/native interfaces according to their contracts.

**Question 15.** With a 2 MiB region, what category can an object larger than 1 MiB fall into in G1?

**Answer:** **Humongous**, because its size reaches at least half a region; special allocation/evacuation handling must account for G1 version and policy.

## 21. Memory Map

~~~text
               HEAP HAS FREE SPACE
                         |
                 Is free space fragmented?
                    /             \
                  Yes              No
                  |                 |
        EXTERNAL FRAGMENTATION   May still lack
                  |              live/headroom
                  v
          CHOOSE GC ALGORITHM
            /            \
       NON-MOVING        MOVING
       mark/sweep      compact / copy
            |               |
       less live copy  coalesce free blocks /
       may leave holes reclaim source regions
                            |
                 +----------+-----------+
                 |          |           |
              Copy bytes  Forwarding  Update/remap refs
                 |          |           |
                 +----------+-----------+
                            |
               CPU / bandwidth / pause / headroom
                            |
        G1: regions + RSet + evacuation + humongous
        ZGC / Shenandoah: concurrent relocation + barriers
                            |
                  MEASURE, DO NOT GUESS
                            |
            GC logs + JFR + jcmd + heap dump
                            |
          throughput / p99 latency / GC CPU / RSS
~~~

**Core takeaway:** fragmentation is a problem of **free-space organization**, not necessarily a shortage of total bytes. Moving objects can compact the heap or free whole regions, but valid references must be maintained — via direct updates, forwarding, barriers, or equivalent mechanisms. The trade-off between **less fragmentation** and **copying/reference-handling cost, pauses, concurrent CPU, and memory headroom** depends on the GC type and workload, so always verify on real HotSpot.

## Official Documentation

- [JVMS Java SE 21 — §2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.3).
- [Oracle Java 21 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html).
- [Oracle Java 21 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector-tuning.html).
- [Oracle Java 21 — Available Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html).
- [Oracle Java 21 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html).
- [Oracle Java 21 — The java Command, Unified GC Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle Java 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [OpenJDK JEP 333 — ZGC](https://openjdk.org/jeps/333).
- [OpenJDK JEP 189 — Shenandoah GC](https://openjdk.org/jeps/189).
