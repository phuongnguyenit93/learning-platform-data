# Write barrier, card table, and remembered set when tracking references

## 1. The core problem

A Java heap contains millions of objects and references between them. While the application is running, assignments such as **holder.child = newChild** continuously mutate the object graph. If the garbage collector (GC) only collects part of the heap or marks concurrently with application threads, it needs to know **which reference edges may have changed** without being forced to scan the entire heap after every assignment.

Three concepts solve most of the story in generational/region-based tracing collectors:

- **Write barrier:** internal GC logic executed around a reference write operation (before or after the write), helping maintain information about heap graph mutations.
- **Card table:** a metadata structure that divides heap addresses into small **cards**; when writing to a location with a reference of interest, the collector can mark the corresponding card as **dirty** for re-scanning.
- **Remembered set (RSet):** a structure summarizing **source locations outside the region being collected** that may reference **into that region**; enabling collecting an individual region without scanning the rest of the heap.

With the HotSpot **G1 Garbage Collector**, there are also two barrier roles that should be clearly distinguished:

1. **Post-write barrier** serves **tracking cross-region references**, contributing to card/remembered-set maintenance.
2. **Pre-write barrier** serves **Snapshot-At-The-Beginning (SATB)** during concurrent marking, mainly handling **the old reference about to be overwritten**.

Both barriers relate to write operations, but **they are not the same algorithm, do not record the same data, and do not exist solely to track old-to-young**.

After this lesson, you will be able to read a reference graph, predict which card must be examined, explain the meaning of an inbound RSet, distinguish SATB pre-/G1 post-barriers, understand synchronization costs with the mutator, use GC logs properly, and avoid drawing wrong conclusions about reachability from a dirty card.

This lesson uses **HotSpot G1 on JDK 17** as a concrete example and clearly distinguishes **tracing GC principles** from **collector implementation details**. The JVMS **does not require** a JVM to use a card table, RSet, or G1's exact barriers.

## 2. Foundations: GC roots, object graph, and partial collection

In the object graph model:

- An **object/array** is a vertex.
- A **reference field/array element** creates a directed edge.
- **GC roots** are live reference sources.
- An object is **strongly reachable** if there is a valid strong reference path from roots to it.

Example:

~~~text
Root --> Old object A --> Young object Y
             |
             +----------> Old object B

Root --> Young object Z
~~~

If collecting the entire heap, the collector can start at all roots and traverse edges as designed. However, a **minor/young collection** only wants to process young objects. The problem: **Y may be alive because old object A points to it**. Scanning only young regions and thread roots while ignoring old-to-young edges would risk treating Y as garbage when it is actually still reachable.

### 2.1. Why not scan the entire old generation every time?

Suppose the old heap is 12 GiB while the young generation is only a few hundred MiB. Re-scanning all old objects on every young GC can be very expensive, defeating the goal of quickly collecting short-lived objects.

The GC needs a **summary source of information** stating: "Which regions/locations outside the collection set might contain references pointing into the collection set?"

This is why **remembered sets and card marking** exist. They allow a collector to process part of the heap while still considering **edges from outside the collected part**.

### 2.2. G1 does not only have two contiguous young/old spaces

G1 divides the heap into **regions** (heap address segments of uniform size in a specific configuration). At any given time, a region may hold Eden, Survivor, Old, or special data such as humongous objects according to the collector's mechanism.

~~~text
G1 heap (logical diagram):
 +--------+--------+--------+--------+--------+--------+
 | Eden A | Old B  | Old C  | Surv D | Eden E | Old F  |
 +--------+--------+--------+--------+--------+--------+
           |         |                  ^
           +----------------------------+
                     |
           There may be cross-region refs
~~~

G1 can collect a **collection set (CSet)** consisting of selected regions. In a young GC, the CSet typically contains young regions; a mixed collection can also include some old regions. Therefore, **tracking cross-region references** is a broader goal than only tracking old-to-young.

## 3. What is a write barrier?

A **write barrier** in GC is a piece of work that the runtime/compiler inserts into the execution path of **certain reference write operations**. It may inspect the old/new reference, the memory slot address being written, marking state, region membership, and update metadata/queues.

Java expression:

~~~java
owner.child = newChild;
~~~

logically:

~~~text
Pre-write info: oldValue = owner.child
                  |
       [Possible pre-write barrier]
                  |
       STORE owner.child = newChild
                  |
       [Possible post-write barrier]
                  |
             Continue running
~~~

This is a behavioral model, **not** a guarantee that every object field store always emits two separate Java method calls. Barriers are typically generated at a low level by JIT/interpreter/VM intrinsics; the compiler can optimize when it knows a store does not require certain bookkeeping.

### 3.1. Pre-write vs post-write

| Characteristic | Pre-write barrier | Post-write barrier |
| --- | --- | --- |
| Conceptual point | Before overwriting a reference slot | After storing the new reference |
| Data of interest | Typically the **old referent** being replaced | Typically the **slot/source location** just modified and/or the new referent |
| Example in G1 | Recording the old value for **SATB concurrent marking** | Card marking/dirty-card queue for cross-region RSet |
| Why needed? | Avoid losing an edge belonging to the snapshot being marked | Do not miss a new reference source pointing into a collection region |
| Always needed? | Depends on marking phase and other checks | Depends on kind of store, source/target regions, and runtime conditions |

There is **no universal definition** that pre-write is always used for SATB or post-write is always used for remembered sets across all collectors. This division of roles is **typical of HotSpot G1 in JDK 17**. Other collectors use different barriers, and even reading references can have **load/read barriers**.

### 3.2. Write barrier differs from Java Memory Model memory barrier

A GC write barrier **is not synonymous with** a CPU memory fence, volatile semantics, or monitor synchronization.

- **GC write barrier:** keeps information accurate for the collector.
- **Memory barrier/fence/JMM ordering:** serves visibility/ordering/happens-before between threads.
- **Card table:** GC metadata, not a mechanism for publishing objects to other threads.

An ordinary **owner.child = x** may alter card metadata, but **does not thereby** create a happens-before relationship between threads. If thread safety is needed, you must still use volatile, locks, atomics, or appropriate synchronization.

## 4. Card table: a map marking small blocks of the heap

A **card** is a small portion of the heap address space divided uniformly according to the collector's card-table mechanism. In HotSpot G1, the typical card size is documented as **512 bytes**, though this should be treated as a **version/implementation detail**, not a constant of the Java language.

Hypothetical example:

~~~text
Heap base = 0
Card size = 512 bytes

  Card 0: [    0,   511]
  Card 1: [  512,  1023]
  Card 2: [ 1024,  1535]
  Card 3: [ 1536,  2047]
  ...
~~~

A simple mapping model:

~~~text
cardIndex = floor((slotAddress - heapBase) / cardSize)
~~~

If a reference field is located at offset address **760**, then:

~~~text
floor(760 / 512) = 1
~~~

The collector cares about **card 1** so it can re-scan reference slots within the relevant address range.

### 4.1. What does the card table store?

A simple educational model:

~~~text
Heap:
  card 0  card 1  card 2  card 3
    |       |       |       |
    v       v       v       v
   [0..] [.. ]  [.. ]  [.. ]

Card-table metadata:
   CLEAN  DIRTY   CLEAN  CLEAN
~~~

In real implementations, a card can have multiple states/bits or different buffering mechanisms; it is not necessarily just a Java boolean.

**Dirty** only means "this area should be re-examined"; it **does not mean**:

- Exactly one reference changed.
- The target object is alive or newly created.
- The card definitely contains an old-to-young reference at GC time.
- The card is inside the collection set.
- Every byte in the card is a Java reference.
- One dirty event corresponds to one new RSet record.

One card contains multiple objects/reference slots; writing to the same card hundreds of times can still be coalesced into few bookkeeping entries.

### 4.2. Why is granularity a card instead of each reference slot?

If every byte/slot store had to update an exact index per object reference, metadata and synchronization could be very expensive. Marking a **small region** is a trade-off:

- **Pro:** mutator-side updates are cheap, metadata is small, many writes can be batched.
- **Con:** the collector may have to scan a whole card even if only one reference field changed, meaning **false positives/coarse precision**.

This is an example of optimizing **write-time overhead vs scan-time overhead**, not "losing information leading to erroneous reclamation." The collector must preserve sufficient correctness so as not to miss live references.

## 5. Remembered set: which sources reference into a region?

A **Remembered set (RSet)** is metadata that helps the collector find references from **outside the region to be collected** pointing inside. In the JDK 17 G1 model, a convenient interpretation is an **inbound RSet** for a target region: a set of source locations/cards that may contain pointers into the target.

Example:

~~~text
             outside collection set
  Old Region R1                  Old Region R2
  +-------------------+          +-------------------+
  | Object A          |          | Object B          |
  | field x ----------+--------+ | field y ----------+-------+
  +-------------------+        | +-------------------+       |
                               |                             |
                               v                             v
                        Young Region R3 (CSet)
                        +----------------------+
                        | Object P   Object Q  |
                        +----------------------+

Inbound RSet for R3 (illustration):
    possible source cards in R1, R2
~~~

When collecting R3, the collector does not need to scan all of R1 and R2; it can inspect the designated source cards and check actual references.

### 5.1. An RSet is not a list of all live objects

An RSet typically contains **candidate locations** — which may be represented by cards, ranges, or compressed structures depending on the implementation. When scanning:

- A candidate card may contain a pointer into R3.
- A candidate card may no longer have the relevant pointer because the reference slot was modified/nulled.
- A card may contain multiple pointers belonging to multiple objects.
- An actual pointer must still be checked to see if its target belongs to the collection set and how it should be handled.

Therefore, an RSet is used as a **source for finding incoming edges**, not a "byte-exact complete object identity graph" nor a reachability proof for every object.

### 5.2. RSet is inbound, not outbound

For the edge **A in R1 → B in R3**:

- This is an **outbound edge** from R1's perspective.
- But it is an **inbound edge** from R3's perspective.
- **Target R3's** RSet records **source locations from R1 that may reference into R3**.

Saying "R1's RSet records references that R1 points elsewhere" is not the standard interpretation of the **per-target inbound RSet** being discussed. Another collector might have different data structures, so always state the RSet direction clearly.

### 5.3. Old-to-young is the common case, not the only one

In generational GC:

~~~text
Old O ----> Young Y
~~~

This is a very important path in young GC. However, G1 also tracks **old region A → old region B** edges when B needs to be collected in a mixed collection, and there are cross-region edges between young regions.

Do not reduce the G1 remembered set to "a list of all old objects pointing to young objects." It is a structure organized by **regions/locations** with maintenance policies depending on the collector.

## 6. G1 pipeline: write → dirty card → refinement → RSet

Suppose a reference field in source region R1 is updated to point to target region R3:

~~~text
(1) Mutator thread:
    A.child = P       A is in R1, P is in R3
          |
          v
(2) G1 post-write barrier (appropriate conditions)
    identifies reference/source slot of interest
    marks source card as dirty
    may enqueue card into dirty-card queue
          |
          v
(3) Concurrent refinement / GC pause processing
    takes recorded dirty cards
    scans appropriate references in the card
    determines actual cross-region targets
          |
          v
(4) Update remembered set metadata
    R3's inbound RSet records source location/card
          |
          v
(5) When collecting collection set containing R3:
    scans incoming candidates from RSet
    checks actual references and handles moved objects
~~~

Actual components add filtering policies, buffering, card states, collection-set handling, queue thresholds, forwarding pointers, remembered-set coarsening, and other phases. This is a **pipeline for understanding responsibilities**, not a mandatory exact flow diagram across every G1 build.

### 6.1. Why not update the RSet immediately on every assignment?

The main reason is to reduce mutator overhead:

- There may be multiple field writes on the same card.
- A card may change targets multiple times before the collector scans it.
- The mutator may only need to write metadata/queue; other threads perform refinement in batches.
- Updating a concurrent RSet directly per reference could require expensive synchronization, allocation, or random memory accesses.

G1 uses **dirty card buffers/queues** and **concurrent refinement** to offload work from the application's hot path. However, if the backlog grows large, a GC pause may have to process pending RSet updates before scanning candidates.

### 6.2. What if a write changes a reference and then clears it before refinement?

~~~text
t0: A.child = null
t1: A.child = P (P in R3)     -> card dirty
t2: A.child = null            -> card may be recorded again
t3: refinement scans current slot
    A.child == null
~~~

If only this slot is considered and there are no other pointers into R3 in the card, the collector can remove/omit the corresponding candidate according to implementation policy. **A dirty card does not prove that the reference value just written still exists**.

This is also why RSet processing often has to check **current references** when appropriate, rather than trusting a historical assignment event alone.

## 7. G1 pre-write barrier: SATB and the old reference

G1 also performs concurrent marking to identify live objects in old-generation areas for selecting regions for mixed collections. Marking occurs while mutators may be modifying the reference graph.

**SATB — Snapshot-At-The-Beginning** uses the concept of "retaining objects present in the initial snapshot" according to the algorithm. A relationship existing at the start of marking might be deleted by a mutator before the marker thread traverses that edge.

Example:

~~~text
At start of marking (logical snapshot):
  Root ---> A ---> X

Mutator is about to write:
  A.child = Y

Before STORE:
  oldValue = X
  G1 pre-barrier may enqueue X (if SATB marking is active)

After STORE:
  A.child = Y
~~~

If X is only reachable through the old edge **A.child**, deleting the edge mid-mark could prevent the marker from seeing X via normal traversal. Enqueuing the old reference in the **SATB buffer** helps preserve the concurrent mark's snapshot invariant, avoiding missing an object that must be considered live by the algorithm.

Points to remember:

- **The pre-barrier cares about the old value** before it is overwritten, **not just the new value**.
- Typically only active when SATB concurrent marking needs it; has fast-path guards.
- Some writes can be optimized by the compiler/VM and not emit a separate pre-barrier execution if proven safe.
- Objects kept live by the snapshot even though no current path remains afterward can create **floating garbage**, which is collected in subsequent cycles.

### 7.1. Does the SATB pre-barrier use the card table to record the old value?

They should not be conflated. G1's SATB pre-barrier typically pushes the **old referent** into an **SATB marking queue/buffer** when appropriate conditions hold. Meanwhile, the post-write barrier serves **card/RSet tracking**. Both can be involved in the same assignment, but **their data and invariants are different**.

### 7.2. Risk if deleted edges are not handled during concurrent mark

Tri-color diagram:

- **White:** not yet marked/discovered.
- **Grey:** discovered, but edges not yet fully scanned.
- **Black:** processed in the marking model.

If a mutator deletes a path to a white object belonging to the snapshot before the marker discovers it, SATB bookkeeping may be needed to avoid inconsistency. This is only the intuition; the actual algorithm handles post-snapshot allocations, barriers, termination checks, and GC-specific invariants.

Do not conclude that "X has become unreachable so it is immediately reclaimed in that same mark cycle" — SATB may intentionally keep X alive through the current cycle to preserve safety.

## 8. G1 post-write barrier: card marking for cross-region pointers

Conversely, the post-write barrier focuses on the **newly stored reference** and the **source slot address** that just changed. At that point, the collector needs to know that an edge from one region to another may have appeared.

Diagram:

~~~text
Before:
    A is in R1
    A.child = null

Write:
    A.child = P;  // P is in R3

After:
    R1 --(reference slot of A)--> R3
                   |
                   v
         Dirty source card (candidate)
                   |
                   v
         Refine updates R3's inbound RSet
~~~

In G1, the post-barrier may use filtering conditions such as null references, same-region source/target, card state, young generation regions, and other optimizations. **Not every assignment of a Java reference dirties a card**.

### 8.1. Pedagogical pseudo-code of the two barriers

~~~text
function storeReference(slot, newReferent):
    oldReferent = slot.currentReferent

    // Pre-write: when SATB marking is active and old value is relevant
    if satbMarkingActive and oldReferent != null:
        enqueueSATBCandidate(oldReferent)

    // Java-level store
    slot.currentReferent = newReferent

    // Post-write: when cross-region tracking policy requires
    if newReferent != null and crossesRelevantRegionBoundary(slot, newReferent):
        dirtyCard(slot.address)
        enqueueCardForRefinementIfNeeded()
~~~

**This is pseudo-code about responsibilities**, not exact HotSpot C++. Null write paths, array copies, initialization barriers, concurrent races, card-queue coalescing, oop compression, GC barriers, and compiler optimizations make the actual implementation more complex.

More importantly, **marking a card and adding to the inbound RSet do not necessarily happen together immediately during the mutator write**.

## 9. G1 collection set and inbound scanning

G1 selects a set of regions to collect, called the **collection set/CSet**. For references from outside the CSet pointing to objects inside the CSet, the collector needs to find and update them if live objects are relocated.

~~~text
Outside CSet:                         Inside CSet:
  R1 [A.child -----------]-----> R3 [P]
  R2 [B.entry ----------]-----> R3 [Q]

R3 inbound RSet (candidates):
  Card containing A.child in R1
  Card containing B.entry in R2
~~~

During a GC pause, the collector:

1. Obtains roots and incoming candidates into the CSet.
2. Traverses/checks appropriate actual references.
3. Relocates live objects if collector evacuation permits.
4. Updates references pointing to old locations according to the GC mechanism.
5. Handles metadata/remembered-set states appropriately for the next cycle.

**The RSet does not replace all GC roots.** Roots such as thread stacks, static/JNI handles, and GC-specific sources still need to be processed. The RSet supplements paths for **heap-to-heap references from outside the CSet**.

### 9.1. Must not scan only the target region

If R3 only contains Y while A in old region R1 points to Y, keeping Y alive through evacuation requires knowing the path from A. The fact that "Y is in young" does not mean Y is live; the RSet provides a way to find external incoming edges so GC can handle them properly.

### 9.2. An RSet candidate can be stale or coarse

Suppose R3's RSet says card K in R1 "may contain a pointer into R3." After many updates, it may no longer contain that pointer. Scanning will check and skip unnecessarily. False positives increase scan cost, but **do not cause a dead object to be mistaken as unsafe to reclaim** in the collector's correctness model.

In contrast, **a false negative is dangerous**: a real pointer from outside the CSet into the CSet that is missed could cause the collector to lose a liveness-preserving path or fail to update a reference after relocation. Barrier/queue synchronization is designed to prevent this.

## 10. Java 17+ example: simulating card table and inbound RSet

This is **a runnable Java program for simulation only**; it does not interfere with real G1. It intentionally marks a card whenever a reference slot is written, then scans existing slots to update candidate inbound cards. This demonstrates that dirty cards are not an exact log of final values.

Create file **CardRememberedSetModel.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CardRememberedSetModel {
    private static final int CARD_BYTES = 512;

    static final class RefSlot {
        final int heapOffset;
        final int sourceRegion;
        int targetRegion; // -1 represents null

        RefSlot(int heapOffset, int sourceRegion) {
            this.heapOffset = heapOffset;
            this.sourceRegion = sourceRegion;
            this.targetRegion = -1;
        }
    }

    private static final List<RefSlot> SLOTS = new ArrayList<>();
    private static final Set<Integer> DIRTY = new TreeSet<>();
    private static final Map<Integer, Set<Integer>> INBOUND =
            new TreeMap<>();

    static void write(RefSlot slot, int newTargetRegion) {
        slot.targetRegion = newTargetRegion;
        DIRTY.add(slot.heapOffset / CARD_BYTES);
    }

    static void refine() {
        for (int card : DIRTY) {
            // Remove old entries of the card in the model.
            for (Set<Integer> sourceCards : INBOUND.values()) {
                sourceCards.remove(card);
            }

            // Scan current reference slots belonging to the card.
            for (RefSlot slot : SLOTS) {
                int slotCard = slot.heapOffset / CARD_BYTES;
                if (slotCard == card
                        && slot.targetRegion >= 0
                        && slot.sourceRegion != slot.targetRegion) {
                    INBOUND.computeIfAbsent(
                            slot.targetRegion, key -> new TreeSet<>()
                    ).add(card);
                }
            }
        }
        DIRTY.clear();
    }

    static Set<Integer> inbound(int region) {
        return INBOUND.getOrDefault(region, Set.of());
    }

    public static void main(String[] args) {
        RefSlot first = new RefSlot(600, 0);
        RefSlot second = new RefSlot(620, 0);
        SLOTS.add(first);
        SLOTS.add(second);

        write(first, 2);
        write(second, 2);
        System.out.println("dirty=" + DIRTY);

        refine();
        System.out.println("inbound2=" + inbound(2));

        write(first, -1);
        refine();
        System.out.println("afterOneNull=" + inbound(2));

        write(second, -1);
        refine();
        System.out.println("afterBothNull=" + inbound(2));
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 CardRememberedSetModel.java
java CardRememberedSetModel
~~~

**Fixed stdout:**

~~~text
dirty=[1]
inbound2=[1]
afterOneNull=[1]
afterBothNull=[]
~~~

**Reason:**

1. Heap offsets 600 and 620 both fall into **card index = 1** because 512 ≤ offset ≤ 1023.
2. Two writes to target region 2 cause the model to place only a single **dirty card 1**.
3. Refine scan sees two refs from source region 0 to target region 2; target 2's inbound RSet has candidate **card 1**.
4. Clearing the first reference leaves the second, so inbound card 1 still remains.
5. Clearing the second and refining leaves the current card with no refs to region 2, so the inbound set becomes [].

**Differences from real G1:**

- The model stores **source/target region IDs** specified by Java code, rather than measuring actual region membership.
- The model dirties every write and updates the RSet immediately upon refine; G1 has guards/queues/coarsening, race protocols, and different handling.
- The model clears stale candidates by scanning the full card; G1 does not necessarily maintain the exact TreeMap structure or clear all entries with such a Java algorithm.
- The model has no GC roots, object liveness, evacuation, SATB, concurrent refinement, or actual heap addresses.

Therefore, the program explains **metadata logic**, not an API for controlling G1.

## 11. Java 17+ example: simulating SATB pre-barrier

Create file **SATBPreWriteModel.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SATBPreWriteModel {
    static final class RefSlot {
        String value;

        RefSlot(String value) {
            this.value = value;
        }
    }

    static final List<String> SATB_QUEUE = new ArrayList<>();
    static boolean marking = true;

    static void overwrite(RefSlot slot, String newValue) {
        String oldValue = slot.value;

        // Pre-write logging: old reference, before store.
        if (marking && oldValue != null) {
            SATB_QUEUE.add(oldValue);
        }

        slot.value = newValue;
    }

    public static void main(String[] args) {
        RefSlot ref = new RefSlot("A");
        overwrite(ref, "B");
        overwrite(ref, null);

        System.out.println("oldCandidates=" + SATB_QUEUE);
        System.out.println("current=" + ref.value);

        marking = false;
        overwrite(ref, "C");
        System.out.println("afterMarking=" + SATB_QUEUE);
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 SATBPreWriteModel.java
java SATBPreWriteModel
~~~

**Exact stdout:**

~~~text
oldCandidates=[A, B]
current=null
afterMarking=[A, B]
~~~

Interpretation:

- Writing A→B while marking is active can record **A**, which is the old reference.
- Writing B→null can record **B**, not null.
- When marking=false, the model does not queue the old value.
- **A, B, C here are only String labels**, not heap addresses; the model's queue uses an ArrayList and is not HotSpot's buffer at all.

**Important:** In real G1, SATB queue references must follow marking and filtering conditions; having an old candidate does not prove it is still reachable in the current graph. The demo does not trigger a GC cycle or prove any String is collected.

## 12. Java 17+ example: Java behavior is unchanged by barriers

Write barriers are generated by the VM and do not create new Java keywords. The program below demonstrates ref field and array slot operations that G1 can observe internally.

Create file **ReferenceMutationDemo.java**:

~~~java
public class ReferenceMutationDemo {
    static final class Box {
        Box next;
        final int id;

        Box(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Box root = new Box(1);
        Box first = new Box(2);
        Box second = new Box(3);
        Box[] slots = new Box[2];

        root.next = first;
        slots[0] = root;
        slots[1] = second;

        System.out.println("first=" + root.next.id);
        root.next = second;
        System.out.println("replaced=" + root.next.id);

        slots[1] = null;
        System.out.println("slotCleared=" + (slots[1] == null));
        System.out.println("sameObject=" + (root.next == second));
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 ReferenceMutationDemo.java
java -XX:+UseG1GC ReferenceMutationDemo
~~~

**Stdout:**

~~~text
first=2
replaced=3
slotCleared=true
sameObject=true
~~~

With this program, **it cannot be asserted** from the source that root is in an old region while first/second are in a young region at a fixed time: lifetimes/generations depend on allocations, JVM/GC, and triggers. These are simply **Java reference writes** that may go through the appropriate barrier infrastructure.

Switching collectors may change the algorithm/barrier strategy, but must still preserve **Java-level output** and memory safety. Do not use stdout as proof of which cards were dirtied.

## 13. Card marking does not mean a reference to a new object

In the case:

~~~java
holder.child = other;
holder.child = null;
holder.child = previous;
~~~

The collector may record the source card multiple times, yet the final state only has a reference to previous. Similarly, writing the **same value** into a slot may be handled differently by the compiler/VM depending on the execution path.

Invalid conclusions:

- "Three assignments = three RSet entries."
- "Dirty card = old-to-young currently exists."
- "Clean card = never had an assignment in history."
- "RSet has a candidate = target object is alive."
- "Same card has two refs into two regions, so only one target RSet is updated."

Distinguish between an **event log/dirty hint** and a **snapshot of reference slots at scan time**.

### 13.1. False positives and false negatives

For example, a card becomes dirty due to a reference into R3 that is then overwritten with null. The RSet may still hold a candidate for a period; that is a **false positive candidate** and causes scan overhead, but GC will check the actual slot.

If there is a real reference from outside the CSet pointing to an object in the CSet that the collector fails to record through any appropriate root/remembered metadata path, that could be a **dangerous false negative**. Barrier correctness is a safety condition, more important than absolute precision of every candidate.

## 14. Concurrent refinement, queues, and GC pause

G1 can perform part of RSet updating **concurrently with mutators**. When card marking creates a backlog:

~~~text
Mutator threads
  | dirty cards / buffers
  v
Pending work queues
  |
  +-- Concurrent refinement workers
  |       |
  |       +--> Update RSet metadata
  |
  +-- Pending work at collection pause
          |
          +--> Process/merge/update needed metadata
          +--> Scan incoming candidates for CSet
~~~

HotSpot versions may change phase names, queues, and processing strategies. In JDK 17, **Update RS / Scan RS** are common concepts when explaining pause costs: updating outstanding remembered-set work and scanning candidates.

### 14.1. When does overhead increase?

Several factors increase write-barrier/card/RSet cost:

- High mutation rate with very many reference field/array element writes.
- Object graph with many **cross-region edges**.
- Certain regions having dense incoming candidates.
- Cards frequently dirtied and refined repeatedly.
- Dirty card backlog not processed in time before a GC pause.
- High card scan ratio due to **coarse-grained metadata** or stale candidates.
- Allocation/promotion patterns causing many old-to-young references to arise.
- Memory pressure, region sizing, and live set changing CSet composition.

Do not guess from the number of field assignments in source: JIT, escape analysis, array-copy barriers, null stores, VM safepoints, and region placements affect the actual number of barrier actions.

### 14.2. RSet coarsening

To avoid using excessive metadata, a remembered-set implementation may switch from a very precise representation (e.g., card indices) to a **coarser** representation for a source area/region. This saves metadata but causes the collector to scan more broadly when needed.

It is a trade-off:

~~~text
Precise remembered set:
  many entries / high selectivity / large metadata

Coarser remembered set:
  less metadata / may scan more cards or regions
~~~

Not every GC has the same thresholds or hash table/bitmap structures; flags can change across JDKs. On Java 17, measure metrics before choosing manual tuning.

## 15. Avoid equating G1 with every other collector

| Collector/mechanism | Appropriate understanding |
| --- | --- |
| **Serial/Parallel generational GC** | Has remembered/card-style tracking mechanisms for the generational boundary, but specific algorithms differ from G1 |
| **G1** | Region-based, remembered-set candidates, post-write card marking, concurrent SATB pre-barrier during marking |
| **ZGC Java 17** | Low-latency collector with load barriers/colored pointers and different concurrency mechanisms; does not copy the G1 RSet model |
| **Shenandoah** | Low-pause/concurrent collector with a different barrier set and forwarding/load-reference handling; depends on distribution/build |
| **No GC or special collector** | Should not assume a G1-like card table exists |

**GC barriers are an implementation detail.** Java source still has **Object**, **String**, reference fields, and array components; there is no mandatory **CardTable** type in the Java language spec.

### 15.1. Where do barriers take effect?

Barriers can be implemented by the interpreter, C1/C2 JIT, stubs/runtime, array-copy paths, or special write paths. A Java assignment being completely optimized/eliminated if an object does not escape and has no side effects can also result in no corresponding heap write needing card marking.

Do not conclude "every Java reference assignment line → always 2 barriers."

## 16. Relationships that commonly cause confusion in diagrams

### 16.1. Source vs target region

Given:

~~~text
A belongs to Region 1
B belongs to Region 4
A.child = B
~~~

- **Source card** is at slot **A.child**, i.e., in Region 1.
- **Target object** B is in Region 4.
- **Region 4's inbound RSet** may record the source card of Region 1.
- The card table is typically indexed by **source slot address** (where the field is written), not simply by target address.

### 16.2. Old-to-young vs young-to-old

~~~text
Old A ---> Young B
Young C ---> Old D
~~~

In a young collection:

- **Old→Young** is an edge from outside the collected area into young; requires appropriate root/remembered processing.
- **Young→Old** is not itself an incoming root from old into young. When scanning live young object C, it has reference D in old; that is an edge in the opposite direction.
- With region-based G1, one must consider region membership/CSet rather than just young/old labels.

### 16.3. One card with two target regions

~~~text
Source card K:
  field x ---> Region 4
  field y ---> Region 7
~~~

Refinement can find references relevant to both Region 4 and Region 7; inbound metadata of both targets may record card K or a corresponding representation. **A dirty card event does not necessarily contain a single target region**.

### 16.4. Source object moved by GC

When evacuation moves an object, source/target addresses change. GC must update pointers and related metadata; an "object's card index" cannot be treated as a permanent identifier tied to Java object identity.

## 17. Observing G1 on HotSpot Java 17

### 17.1. Confirming the collector

You can launch a program with G1:

~~~bash
java -XX:+UseG1GC ReferenceMutationDemo
~~~

If the compile command and classpath are valid, this example prints stdout as in section 12. Enabling G1 does not automatically make a Java program print dirty-card events.

Check actual JVM flags:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Look for **UseG1GC**, **G1HeapRegionSize**, **MaxGCPauseTimeMillis**, and other relevant flags. Each JDK/VM has different ergonomics and display formats; do not infer the final collector solely from a tutorial.

### 17.2. Using Unified JVM Logging

In HotSpot Java 17:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=info ReferenceMutationDemo
~~~

A program that runs too fast or allocates very little may **perform no young/mixed GC at all** in a run; thus there is no fixed number of events to predict.

To see available tags:

~~~bash
java -Xlog:help
~~~

A more informative test configuration in an environment that accepts more logs:

~~~bash
java -XX:+UseG1GC -Xlog:gc*,gc+remset=debug ReferenceMutationDemo
~~~

It is **not guaranteed** that all output or tag availability is identical across every JVM/JDK build. Check **java -Xlog:help**, then adjust log levels/tags. Do not run high-volume trace logs in production before evaluating overhead/storage.

### 17.3. What can be seen from logs?

Depending on the JDK build and logging configuration, you can see:

- Pause type (young evacuation, concurrent start, mixed...).
- Pause duration, collection set composition/regions.
- Time spent on root scanning, remembered-set processing/merging, and object copying.
- Number of scanned cards/remembered-set statistics at appropriate log levels.
- Concurrent refinement/marking events and GC pause data.

**GC logs are aggregate diagnostics**, not an exact printout of every Java field assignment. You cannot deduce from a "Scan RS" line which field the application modified at which Java source line.

### 17.4. Combining profiling and heap graph

If pause cost related to remembered sets increases, check:

1. Allocation rate and promotion rate.
2. Object structures with very many cross-region pointers.
3. Mutable collections/arrays containing many references.
4. Caches retaining old objects and continuously adding young references.
5. Card refinement backlog and pause breakdown.
6. Actual heap region size chosen by ergonomics.
7. GC algorithm and CPU resources allocated to concurrent workers.

If the issue is a memory leak, use a **heap dump/path-to-GC-root** to identify the still-reachable graph. Write barrier/RSet logs **do not replace** reachability analysis.

## 18. Step-by-step guide to analyzing an "A points to B" exercise

Suppose:

~~~text
Region O1: old object A
Region O2: old object C
Region Y3: young object B
Region Y4: young object D

A.ref = B
C.ref = D
B.ref = C
~~~

Steps:

1. Identify the **source slot** of each edge: A.ref in O1; C.ref in O2; B.ref in Y3.
2. Identify the **target region**: B in Y3, D in Y4, C in O2.
3. Mark **cross-region**: all three edges are crossing because source/target regions differ.
4. With the G1 post-write barrier, consider appropriate guards/card marking when each store occurs; do not assert the same number of queue entries as edges.
5. Upon refinement, **Y3's inbound RSet** may record O1's source card; **Y4's inbound RSet** may record O2's source card; **O2's inbound RSet** may record Y3's source card when policy/phase maintains that metadata.
6. When the young CSet includes Y3/Y4, the collector pays special attention to incoming edges from **outside the CSet** (O1 and O2). The edge Y3→O2 is not incoming from outside into the young CSet.
7. If SATB marking is simultaneously active and a slot is overwritten, the **pre-barrier** may enqueue the old referent, independent of RSet semantics.
8. If A.ref later becomes null, the card/RSet candidate may be stale for a while; GC must check the actual reference.

**Important:** Some portions of metadata for targets may be maintained selectively. Do not treat the diagram in step 5 as a guarantee that "G1 always has a stored RSet entry for every cross-region edge at all times."

## 19. Write barriers and properties of Java programs

### 19.1. Does not alter Java reference identity

~~~java
Object a = new Object();
Object b = a;
System.out.println(a == b); // true
~~~

Even though G1 executes barrier operations on relevant reference writes, Java-level **==**, **equals()**, **getClass()**, and memory-safety guarantees remain unchanged. The runtime must not allow collector bookkeeping to produce different object identity.

### 19.2. Does not replace thread synchronization

If two threads update an ordinary non-volatile/unsynchronized reference field, a data race can still occur under the Java Memory Model. GC barriers do not turn that field into an atomic/volatile publication contract. Thread-safe design must use dedicated Java concurrency mechanisms.

### 19.3. Not Java objects for the application to edit

The card table/RSet is not a public Collection or Map for the application. You should not write code to manually modify GC metadata via JNI/Unsafe. The Java examples in this lesson are **simulations only**; never manipulate the internals of a live collector.

## 20. Performance optimization: when should you pay attention?

**Do not start by tweaking RSet/card flags** without measurements. If GC logs show that remembered-set work/scanning is a significant component of pauses, examine the cause in the **application object graph** and heap ergonomics.

Some directions:

- Reduce reference churn in long-lived arrays/containers if unnecessary.
- Limit graph structures with excessive cross-region pointers when they provide no business value.
- Review cache/queue ownership; improve locality through appropriate data structure design.
- Set heap/region/GC goals based on actual throughput/latency, not just a single log line.
- Evaluate CPU cycles spent in mutator barriers versus GC refinement/scanning.
- Do not force "fewer references" by cramming data into off-heap or primitive buffers if it introduces greater complexity/risk; benchmark the whole system.

### 20.1. Trade-offs from region size

Larger regions can reduce the number of cross-region boundaries in some workloads, thereby reducing metadata/refinement work. However, larger regions can also alter the amount of live data needing evacuation, humongous object handling, and pause behavior. **G1HeapRegionSize** is a tuning flag for cases with clear evidence, not "the bigger the better."

### 20.2. Changing collectors

If the goal is very low latency, you can evaluate another collector suited to the JDK/workload. However, each collector has different barrier strategies, CPU/memory overhead, requirements, and maturity; do not switch collectors based on the claim that "write barriers are always expensive so ZGC doesn't use barriers."

## 21. Misconceptions to avoid

1. **"A write barrier is a Java volatile/memory fence."** No: GC barriers and JMM synchronization serve different problems.
2. **"Every reference assignment always executes exactly two barrier functions."** No: there are phase guards/optimizations.
3. **"G1 pre-write records the new reference."** Wrong in the SATB role: it cares about the **old value** about to be overwritten.
4. **"G1 post-write records the old reference for SATB."** Wrong: its main role here is cross-region/card/RSet tracking.
5. **"Dirty card = there is a live young object."** Wrong: dirty is only a candidate; the card may be stale.
6. **"Card table stores a complete list of Java objects."** Wrong: it describes candidate regions/slots.
7. **"RSet contains all outgoing edges of the target region."** Wrong for an inbound RSet; sources are outside the region.
8. **"RSet is an exact list of all live objects in the region."** Wrong.
9. **"One assignment corresponds to exactly one RSet entry."** Wrong: batching, card granularity, coalescing.
10. **"G1 only tracks old-to-young."** Wrong: region-based cross-region edges serve young/mixed CSets.
11. **"Old→Young can be skipped because old objects were already scanned in the past."** Wrong: the graph can change afterward.
12. **"Scanning the remembered set means scanning the entire old heap."** No: the goal is to scan relevant candidate regions.
13. **"Concurrent refinement always finishes immediately when the Java store finishes."** Wrong: there are pending queues.
14. **"Card/RSet false positives mean broken memory safety."** Wrong: they may only increase scan work.
15. **"SATB keeps the graph identical to the present at every nanosecond."** No: it is a logical snapshot approximation per the marking invariant.
16. **"If an old edge is deleted, the object is definitely collected immediately in that marking."** No: SATB can create floating garbage.
17. **"GC logs tell which Java source statement dirtied a card."** Not a default feature like that.
18. **"A dirty card is an independent GC root like a static field."** No: metadata supporting root/incoming scanning.
19. **"To fix a memory leak, disable write barriers."** No: barriers are part of ensuring collector safety; fix ownership/root paths.
20. **"Reducing card size is always faster."** No: metadata, writes, refinement, and scanning have trade-offs.
21. **"RSet precision is always absolute."** No: there are stale/coarse candidates; what matters is not missing necessary references.
22. **"ZGC/Shenandoah must use the exact same G1 cards."** No: barrier implementations differ.
23. **"Just running java -XX:+UseG1GC will produce GC logs on every run."** No, not without enabling appropriate logging or having a collection occur.
24. **"G1 pre-barrier only operates on old-to-young writes."** No: SATB's purpose is snapshot preservation during concurrent marking.
25. **"The collector has the right to alter Java reference semantics for faster tracking."** No: Java semantics must be preserved.

## 22. Exercises with answers

**Exercise 1.** Old object O references Young object Y. Young GC only scans thread roots and young regions, without scanning old-to-young candidates. What is the risk?

**Answer:** A path keeping Y alive through O could be missed. A generational collector needs to consider old-to-young references via remembered/card/barrier or an equivalent mechanism.

**Exercise 2.** Suppose card size is 512 bytes, source slot address offset is 1300 from heap base 0. What is the card index?

**Answer:** floor(1300/512)=**2**; card 2 has byte range [1024,1535].

**Exercise 3.** A card has two fields pointing to Region 5 and Region 8 respectively. Do both need to be considered during refinement?

**Answer:** Possibly. A dirty card is not limited to one target; inbound metadata for both regions may need updating according to collector policy.

**Exercise 4.** Source object A in Region 1 points to target B in Region 7. Which region's inbound RSet records the source card?

**Answer:** **Region 7** under the per-target inbound RSet model.

**Exercise 5.** Assigning A.ref from B to null while G1 SATB concurrent marking is active. What does the pre-barrier care about?

**Answer:** Old referent **B**, which may be enqueued before overwriting to preserve the SATB snapshot invariant.

**Exercise 6.** Assigning A.ref to C in another region when there is no concurrent marking. Must G1 pre SATB enqueue the old value?

**Answer:** Not as an always-on rule; the pre-barrier has a marking-active check, while the post-barrier may still track the cross-region reference as appropriate.

**Exercise 7.** Writing to a field 100 times, but only on one source card. Are 100 RSet entries guaranteed?

**Answer:** No. Card-level metadata, duplicate filtering, and batch refinement can coalesce work.

**Exercise 8.** A dirty card after refinement no longer has a reference to the target region. Does the earlier dirty event mean a memory leak?

**Answer:** No. It could be a stale/false-positive candidate; GC must check actual slots as appropriate.

**Exercise 9.** Why can G1 process old→old region references?

**Answer:** Because mixed collections can select some old regions into the CSet; incoming edges from other old regions still need to be considered.

**Exercise 10.** Can one conclude from an RSet containing a card that the target object is definitely live?

**Answer:** No. The RSet is metadata of potential source locations; live/dead depends on roots/tracing and GC conditions.

**Exercise 11.** Does card marking belong to the compiler/runtime or is it written manually by programmers in Java?

**Answer:** Runtime/JIT/interpreter/VM barrier infrastructure; Java source writes normal assignments.

**Exercise 12.** Does a GC barrier replace volatile publication between threads?

**Answer:** No. GC bookkeeping is independent of happens-before/thread synchronization.

**Exercise 13.** In SATB, why might the marker need the old reference when the mutator overwrites a field?

**Answer:** An edge belonging to the logical snapshot may be deleted before the marker scans it; the old reference helps avoid missing objects that must be considered live per the snapshot.

**Exercise 14.** A 512-byte card has 32 reference slots, but only one slot points into the CSet. Why does the collector still scan additional slots?

**Answer:** Card granularity prioritizes metadata/write efficiency; scanning a card may include unrelated slots.

**Exercise 15.** Must G1 use the exact same queue layout/tracing code as a JDK 8 tutorial in JDK 17/26?

**Answer:** No. Internal mechanisms and flags change; keep the invariant model and read version-accurate docs/source.

**Exercise 16.** When a GC pause is dominated by remembered-set scanning, what should be done first?

**Answer:** Re-measure with G1 GC logs, examine cross-region connectivity/dirty-card rate/region sizing/live set and workload. Avoid arbitrary flag tweaking.

**Exercise 17.** Why did the CardRememberedSetModel print inbound2=[1] even though there were two writes on the same card?

**Answer:** The model's RSet stores **source card candidates**, not a count of references; both fields belong to card 1.

**Exercise 18.** The model nulled first but still printed afterOneNull=[1]; why?

**Answer:** Field second in the same card still points to target region 2; when refine scans the card, the candidate is still valid.

**Exercise 19.** A source card outside the CSet points to two targets inside the CSet. Does using a shared inbound RSet necessarily lose information?

**Answer:** No; metadata can map candidate cards to targets or merge them into a set to scan. GC must ensure every necessary incoming reference is still examined.

**Exercise 20.** Can GC work be reduced by omitting the SATB pre-barrier during concurrent marking?

**Answer:** No, not without a correct replacement algorithm/solution. Disabling a required mechanism can break the marking invariant; application authors do not manage this barrier.

## 23. Checklist when reading code or analyzing incidents

- Start with the **GC type** and specific JDK build.
- Draw **edges from source slot → target object**; clearly note region membership.
- For young/mixed CSets, identify **incoming edges from outside the CSet**.
- Distinguish **card table** (dirty candidate marker) and **remembered set** (incoming sources that may need scanning).
- Remember **source card index** is based on where the field is written, not just the target address.
- G1 **post-barrier** serves tracking source cards/cross-region updates.
- G1 **pre-barrier** serves SATB concurrent marking with the old referent.
- Queues/refinement can batch/delay; do not assume the RSet is updated instantaneously after a Java assignment.
- Use **false positive vs false negative** to evaluate correctness.
- RSets can be coarse/stale, but must be sufficient to avoid losing incoming edges.
- Distinguish **liveness tracing** from **card bookkeeping** and **object relocation**.
- When GC logs look bad, measure remembered-set work/scanning, object graph topology, and mutation rate.
- Do not treat a JMM memory barrier as a GC write barrier.
- Do not think a static cache leak can be fixed by tuning RSet; fix the root/ownership path.
- When switching collectors, check the new barrier mechanisms; do not mechanically apply G1 docs to ZGC.
- With Java 17, use Oracle 17 docs/HotSpot logs directly to avoid relying on internal details from other versions.

### Standard and in-depth references

- **Oracle Java SE 17 — Garbage-First (G1) Garbage Collector:** https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html
- **Oracle Java SE 17 — G1 Tuning:** https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html
- **Oracle Java SE 17 — Unified JVM Logging in the java command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **OpenJDK JDK 17 HotSpot — G1 barrier implementation/source tree:** https://github.com/openjdk/jdk17u/tree/master/src/hotspot/share/gc/g1
- **OpenJDK JDK 17 HotSpot — Card table infrastructure:** https://github.com/openjdk/jdk17u/tree/master/src/hotspot/share/gc/shared
- **JVMS Java SE 17 — Run-Time Data Areas/Heap:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3
- **Java SE 17 — java.lang.ref reachability semantics:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html

**Core takeaway:** **Write barriers** retain information about reference mutations so a collector does not miss important edges. The **card table** marks source areas needing inspection; **remembered sets** describe incoming candidates from outside the regions being collected to reduce full-heap scanning. In HotSpot G1, **post-write** serves cross-region card/RSet tracking, while **pre-write** preserves the SATB snapshot during concurrent marking. Dirty cards and RSet entries are **candidate metadata**, do not prove liveness on their own, and storage/queue/barrier optimization details depend on the collector/version.
