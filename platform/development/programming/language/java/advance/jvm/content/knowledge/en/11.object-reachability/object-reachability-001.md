# How does GC determine whether an object is still reachable from roots?

In Java, the **garbage collector (GC)** does not simply delete an object after a local variable goes out of scope, nor does it merely count the number of references pointing to an object. To determine which objects need to be kept alive, JVM tracing collectors start from a set of **GC roots**, follow reference paths that have keep-alive semantics, and build the set of **reachable** objects. Objects that are no longer kept alive according to reachability/reference processing rules can become candidates for reclamation.

This is the foundation of the **reachability** topic: one must distinguish between an **existing reference**, a **programmatically live reference**, an **object reachable from GC roots**, an **object handled under weak/soft/phantom reference rules**, and **memory actually reclaimed by GC**.

Key points right from the start:

- **Reachable** means there is still an appropriate keep-alive path from one or more GC roots under the collector's model.
- **Unreachable** does not mean the object is freed immediately at the last statement: GC runs according to runtime policy, while reference processing, legacy finalization, and concurrency have additional rules.
- **Reference cycles do not automatically keep objects alive forever.** Two objects pointing to each other with no keep-alive path from a root can be reclaimed by GC.
- **Strong, soft, weak, and phantom references do not carry the same keep-alive semantics.** If you traverse all edges without classifying them, you will misinterpret cases using `WeakReference`, `SoftReference`, or `PhantomReference`.
- **GC roots belong to JVM state**, not every variable that ever appeared in Java source code. JIT and liveness analysis can determine which references are actually still needed to preserve semantics.

This article uses Java 17+ for runnable examples and distinguishes between the **graph model for learning** and **specific HotSpot algorithms/metadata**. The JVM Specification does not mandate that every collector use the same marking algorithm or root table structure.

## 1. Reachability is a graph problem

Let us model objects on the heap as **vertices** of a graph. A reference field or an array element containing a reference can form an **edge** from the object holding the field/element to the referenced object.

```text
GC ROOTS
 ├── stack/local reference ──► A ─────► C ────► D
 └── static reference ───────► B ─────► C

                                 E ───► F
                                 ▲      │
                                 └──────┘
```

In this graph, assuming the drawn arrows are **strong reference edges**:

- **A, B** have paths starting from a root, so they are reachable.
- **C** is reachable via A or B; **D** is reachable via C.
- **E and F** point to each other, but there is no path from a root to them. The cycle E ↔ F does not make them reachable.
- If both edges A → C and B → C are later lost, C and D are also no longer reachable from the **drawn** roots, unless in reality other edges or roots not shown still exist.

This graph is an **abstract example**, not a snapshot of all GC roots of a JVM. An object can still be kept alive by other references not shown in the diagram, such as a JNI global handle or a local reference still considered live by the VM.

### Intuitive definition

Let **R** be the set of GC roots, and **E** be the set of **strong reference** edges between objects. The **strongly reachable** set is the objects that can be reached from at least one root by a sequence of zero or more edges with strong keep-alive semantics.

One way to describe the algorithm:

```text
worklist = objects directly referenced by GC roots
marked   = empty set

while worklist is not empty:
    obj = take an object from worklist
    if obj is already marked:
        continue
    add obj to marked
    for each strong reference from obj:
        if referent is not null:
            push referent into worklist

marked = strongly reachable set in this snapshot model
```

This is **pseudocode**, not standalone Java source or a description of a single algorithm used by every GC. Its purpose is **graph traversal with marking**. Without the `marked` set, a cycle A → B → A could cause the traversal to loop infinitely.

### Why not use pure reference counting?

A simple reference counter would see that E has one reference from F and F has one reference from E; both have positive counts even with no root remaining. **Tracing reachability** distinguishes cycles kept alive from a root from isolated cycles.

Do not infer that HotSpot only counts references or only scans fields sequentially once: modern collectors have write barriers, concurrent phases, card tables/remembered sets, and reference processing for both correctness and performance.

## 2. What are GC roots?

A **GC root** is a starting point that the collector can use to discover objects that still need to be kept alive according to the JVM execution state. A root is usually not a "single first object"; the system can have multiple sets of roots from different runtime areas.

Common groups in HotSpot/JVM:

| Root origin | Examples | Notes |
| --- | --- | --- |
| **Live references in Java thread stacks/frames** | References to objects still needed for executing methods | Not every local variable that ever existed remains a root |
| **Live static fields / runtime class state** | Cache objects in a static field of a class still appropriately kept alive | Class loader/class metadata reachability has an effect; not every loaded class is kept forever |
| **JNI handles** | JNI global references, certain JNI local references | JNI **weak global** has different semantics from strong JNI references |
| **VM-internal handles/structures** | Objects used by the VM system, runtime services, references being processed | Exact list depends on collector/implementation |
| **References in native/transition execution paths** | Objects placed into JNI/runtime handle mechanisms | Collector needs to decode those references according to VM rules |
| **Special roots tracked by the collector** | Structures for class unloading, reference processing, code metadata | Organization depends on HotSpot version |

**Do not treat the list above as an immutable contract across collectors.** Some sources are treated by one collector as direct roots, while others are handled via metadata/remembered sets or a related scanning phase. What matters is that **every object that must stay alive under program semantics is protected from erroneous reclamation**.

### 2.1. Live references in the stack

Example:

```java
static void printValue() {
    Object value = new Object();
    System.out.println(value);
}
```

This is an **illustrative method**, which must be placed inside a class to compile. While `value` is still needed for `println`, the VM must preserve the ability to use the object with correct semantics. However, **one cannot assert that the variable `value` is a strong GC root for the entire time the method remains on the call stack**.

The JIT can determine the **last use point** of a reference and optimize liveness intervals. After the last use, an object can become no longer strongly reachable earlier than the end of the block/method, if doing so preserves semantics.

Therefore, the statement "as long as a local variable is in Java scope, the object can definitely never be GC'd" is an **overly strong conclusion**. Java-level scope and the liveness that the VM needs to maintain are not identical.

### 2.2. Static fields and class loaders

```java
class Registry {
    static Object shared = new Object();
}
```

While `Registry` and its runtime state are kept alive, `Registry.shared` can contribute a **keep-alive path** to the object. However, static state is not "immortal memory" in every case: when a **defining class loader** and the classes it defines become eligible for unloading, the associated metadata/static references can also be freed according to VM rules.

**Common memory leak bug:** a static collection of a long-lived class holds strong references to many objects that are no longer needed:

```java
static final java.util.List<Object> CACHE = new java.util.ArrayList<>();
```

This is just an illustrative field inside a class. If the application keeps adding items to `CACHE` without removing them, the elements can remain reachable even though business logic has "forgotten" them. GC cannot know on its own which objects have lost business value when a strong reference path from a root still exists.

### 2.3. JNI global and weak global references

Native code via JNI can hold references to Java objects using JNI handles. A **strong global reference** can contribute to keeping an object alive, whereas a **weak global reference** is handled according to appropriate weak reachability rules.

Important point: if a heap analyzer cannot point to a specific static field or Java local variable yet the object is still reachable, consider **JNI handles**, runtime services, class loaders, thread locals, and sources outside ordinary field references.

## 3. When traversing, which edges does GC follow?

For a reachable object, the collector can identify references in:

- **Instance reference fields**, for example `Node.next`.
- **Reference array elements**, for example slots of `Object[]`.
- **Objects referenced indirectly through metadata/handles** according to VM mechanisms.
- **Special structures** such as `java.lang.ref.Reference` that must be handled under different rules from an ordinary strong field.

Not every byte in an object is a pointer:

```java
class Holder {
    int count;
    long timestamp;
    Object value;
}
```

In this example, `count` and `timestamp` are primitive data, not heap pointers that GC is allowed to arbitrarily interpret. `value` is a reference field and can act as an edge.

HotSpot relies on **layout metadata** to know which positions contain object references in fields, arrays, and runtime frames. JIT-compiled code also provides **oop maps** or equivalent information at points where GC needs to know the locations of live references in registers/stack. That enables precise GC, as opposed to treating every address-shaped word as a definite root.

### 3.1. Not "every reference is strong"

`WeakReference`, `SoftReference`, and `PhantomReference` are Java objects that have an internal field associating them with a referent. However, the collector **must not treat the edge to the referent from these objects identically to an ordinary strong field**.

Example:

```java
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(new Object());
```

This is a snippet inside a method. The variable `weak` may still be strongly reachable, but the object **referenced by `weak`** does not thereby automatically have a strong path. At which GC the referent survives is a separate matter, depending on whether strong/soft reference paths exist elsewhere and on GC timing.

Do not confuse the **reference object** (`WeakReference` instance) with the **referent** (the object that `get()` may return).

## 4. Marking: marking the reachable set

A tracing GC algorithm can divide its work into:

1. **Root discovery/scanning**: identifying references originating from the root set.
2. **Graph traversal**: following edges that must be kept alive, tracking visited objects.
3. **Reference processing**: handling soft/weak/phantom references and special semantics.
4. **Reclamation**: allowing the memory regions of objects no longer needing to be kept alive to be reused, via sweep/copy/compaction or the corresponding mechanism.
5. **Updating pointers/metadata when moving objects**: keeping live references pointing to the correct new addresses, if the collector uses moving/compacting collection.

This is a **conceptual framework**, not a rigid sequence for every JVM. Phases can overlap, run concurrently, or differ among Serial, Parallel, G1, ZGC, Shenandoah, and other collectors.

### 4.1. Tri-color abstraction

In much documentation, tracing is explained using three colors:

| Color | Meaning in the model |
| --- | --- |
| **White** | Not yet discovered/marked |
| **Gray** | Discovered, but still has edges to scan |
| **Black** | Finished scanning the edges that need to be inspected |

```text
Roots → GRAY
             │
             ▼
      take a gray object
             │
       explore children
             │
     white child → gray
             │
             ▼
   scanned object → black
```

At the end of tracing, objects remaining **white** in the set being collected can become candidates for reclamation, **after** satisfying the rules for reference processing, legacy finalization, and the specific collector.

**Tri-color is a reasoning model**, not a guarantee that every collector places exactly three physical color bits in every object header. Mark bitmaps, remembered sets, queues, and more complex metadata may be used.

### 4.2. DFS, BFS, or work stealing can all be correct

A collector can use a stack, queue, bitmap, or multiple parallel worklists to traverse the graph. Whether A is visited before B or B before A does not change the reachable set in an **immutable snapshot** if the algorithm is complete and handles cycles properly.

With concurrent collectors, the graph is **not immutable** because application threads (mutators) continue creating/deleting refs. In that case, additional mechanisms are needed so as not to miss objects that must stay alive.

## 5. How do stop-the-world and concurrent marking differ?

### Stop-the-world (STW)

During STW phases, the JVM pauses application threads at corresponding safepoints so the collector can observe/access a sufficiently consistent state. This makes root scanning and certain object-graph relocation/update operations easier to reason about.

Not every GC is STW throughout the entire cycle. Many collectors have some short STW phases and some concurrent phases; pause length depends on the collector and workload.

### Concurrent marking

During concurrent marking, one or more GC threads scan the graph **while mutator threads are still modifying references**. That creates a problem:

```text
Time 1:
Root → A → B

While marking, the application modifies:
Root → A
       A.child = null
Root → C (newly published object)
```

If the collector ignores critical changes, it could miss an object that still needs to stay alive. Therefore, concurrent collectors use **barriers** and marking-state rules to guarantee correctness.

Two representative ideas:

- **Snapshot-at-the-beginning (SATB):** appropriately tracks old references when the application deletes/overwrites an edge, maintaining an initial snapshot model according to the collector's invariants.
- **Incremental-update:** records new edges/changes that need processing to preserve the invariant when an already-scanned object is updated to point to an unmarked object.

**Do not say that all JVM collectors use SATB or that all use incremental-update in the same way.** These are two families of techniques. A collector may use multiple barriers for different goals (marking, card marking, relocation, load barrier...).

### 5.1. What is a write barrier?

A write barrier in GC is a piece of runtime mechanism executed around **writing a reference** to update information for the collector when needed. It differs from a Java memory-order barrier in JMM discussions, despite the similar name.

Source example:

```java
a.next = b;
```

The compiler/JVM can execute the reference write along with the associated barrier action. **A barrier is not a Java source method that the programmer is required to call manually.** It can be inserted by the JVM/JIT into machine code.

### 5.2. Load barriers and moving collectors

Some concurrent/moving collectors use **load barriers** or special reference-reading mechanisms to ensure Java threads obtain valid references while objects are moving.

Do not assume every reference is updated the same way: a VM strategy may use forwarding pointers, colored pointers, relocation metadata, or other approaches. Java authors mainly need to follow the Java Memory Model and use standard APIs; do not manipulate raw addresses yourself.

## 6. Generational GC: scanning roots and remembering edges from other regions

Many collectors divide the heap into regions by age/lifetime (young/old generations or regions). A **young collection** does not need to treat the entire old generation as a giant root and scan every deep object like a full-heap traversal.

Illustrative problem:

```text
Young region: Y
                 ▲
                 │
Old object O ────┘
```

If an object `O` in the old region holds a reference to `Y` in the young region, a collection focusing only on the young generation **must not ignore the edge O → Y** just because O lies outside the region being collected.

**Remembered sets**, **card tables**, and related mechanisms allow the collector to know which regions outside the collection set may contain references pointing into the region being collected. They supplement root scanning.

| Concept | Meaning |
| --- | --- |
| **Collection set** | The regions/generations being processed in the corresponding collection cycle |
| **Remembered set** | Tracks references/locations from outside the collected region that may point into it |
| **Card table** | Metadata commonly used to track memory regions where a reference write occurred |
| **Post-write barrier** | Mechanism to mark/update metadata after a write as appropriate for the collector |
| **Cross-generational reference** | An edge such as old → young that must be accounted for when collecting young |

**Takeaway:** the logical reachable graph remains the foundation, but an optimized collector does not necessarily scan **the entire heap from scratch** on every young GC. It uses the relevant root set and metadata tracking cross-region edges.

## 7. Strong, soft, weak, and phantom reachability

Java provides the `java.lang.ref` API to work with special reference levels. They cannot be replaced by a simple rule of "either the object is on the heap or not".

| Reference type | General meaning | API example |
| --- | --- | --- |
| **Strong reference** | Ordinary reference path capable of keeping an object alive | `Object x = new Object()`, field, array element |
| **Soft reference** | Allows GC to reclaim the referent according to policy, typically related to memory pressure | `SoftReference<T>` |
| **Weak reference** | Does not prevent the collector from reclaiming the referent if only weak reachability remains | `WeakReference<T>` |
| **Phantom reference** | Supports tracking the stage after an object is no longer reachable at a stronger level, usually paired with `ReferenceQueue` | `PhantomReference<T>` |
| **Legacy finalizer** | Historical finalization mechanism, unreliable for resource management | `finalize()` (deprecated since Java 9; deprecated for removal since JDK 18) |

### 7.1. Strong reference

```java
Object keepAlive = new Object();
```

The reference `keepAlive` has keep-alive semantics for the object **when that reference itself is actually live and lies on a path the VM considers necessary to preserve**. One cannot deduce that a variable once assigned but no longer used will keep the object alive until the end of the method.

Ordinary strong paths are the foundational routes of the marking algorithm presented in section 1.

### 7.2. SoftReference

```java
java.lang.ref.SoftReference<byte[]> soft =
        new java.lang.ref.SoftReference<>(new byte[1_024]);
```

A `SoftReference` allows GC to make reclamation decisions on the referent according to policy. Soft references used to be commonly used for caches, but **a soft cache should not be treated as a precise memory-bounding mechanism or a replacement for controlled cache eviction**.

Per the API, soft references to softly reachable objects have handling guarantees related to `OutOfMemoryError` within the documented scope, but there is no guarantee that "GC will clear soft refs in strict LRU order" or that "`soft.get()` is definitely non-null if the heap still has X MB". Specific heuristics depend on the implementation.

### 7.3. WeakReference

```java
Object strong = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(strong);
```

While `strong` remains a live strong path to the object, the weak referent is not cleared merely because a `WeakReference` exists. If all strong paths are lost and the object is only weakly reachable (with no stronger soft path keeping it), an appropriate GC can **clear the weak reference** and enqueue it according to rules.

For example, having `strong = null` **does not automatically make `weak.get() == null` on the very next line**. GC may not have run yet; JIT liveness and other paths also have an effect.

`WeakHashMap` uses weak references for **keys**, useful in scenarios associating metadata with keys without wanting the map to keep them alive via the map's own key reference. However, if the value holds a strong reference back to the key, the key can still stay alive via the path map → value → key; cache design needs to inspect the actual graph.

### 7.4. PhantomReference

```java
java.lang.ref.ReferenceQueue<Object> queue =
        new java.lang.ref.ReferenceQueue<>();
java.lang.ref.PhantomReference<Object> phantom =
        new java.lang.ref.PhantomReference<>(new Object(), queue);
```

**`phantom.get()` always returns `null`**, regardless of what stage the referent has reached. This API is used with a queue to observe GC reference-processing events according to rules, often serving as the basis for cleanup mechanisms that do not depend on finalizers.

Do not use a phantom reference to "rescue" an object back into use like a strong reference. When timely release of a file/socket/native resource is needed, prefer **`AutoCloseable` / try-with-resources**. Cleaner/phantom cleanup is a fallback mechanism with non-deterministic timing and is not guaranteed to run before the process exits.

### 7.5. The reachability hierarchy is a subtle concept

In the Java references model, there are states such as **strongly reachable**, **softly reachable**, **weakly reachable**, **phantom reachable**, and **unreachable**, depending on whether a stronger path remains. A path through a `SoftReference` or `WeakReference` does not have the same keep-alive semantics as an ordinary field.

This is not a table of "GC definitely reclaims within X milliseconds" for each type. The collector must also handle queues, reference clearing, cleanup, legacy finalization, and runtime conditions.

## 8. ReferenceQueue: observing notifications, not scheduling GC

A `ReferenceQueue` receives `Reference` objects that have been processed/enqueued according to API rules. It is useful for letting the application know that the referent has reached the relevant state, but **it is not a GC scheduler**.

```java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

class QueueExample {
    static void show() {
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        Object value = new Object();
        WeakReference<Object> weak = new WeakReference<>(value, queue);

        System.out.println(weak.get() == value); // true at this point
        value = null;

        // Cannot assert that queue.poll() definitely has a result right here.
        System.out.println("GC timing is not deterministic");
    }
}
```

This is a **syntactically complete class** with a static method `show()`, but **no main**. The two `println` lines inside illustrate usage; to run standalone, call `QueueExample.show()` from a main class.

**Two different things:** `weak.get()` may already have been cleared when GC runs; `queue.poll()` may not yet return the corresponding reference at the exact moment you query it. Keep the `WeakReference` object strongly referenced when you want to observe the queue; the reference object itself also has its own lifecycle.

### Note on `System.gc()`

`System.gc()` is inherently a **hint/request** to the runtime, not a contract allowing tests to assert that immediately after the call, a specific object has been reclaimed. There are JVM flags/modes in which explicit GC is ignored or handled differently. **Do not use `Thread.sleep` + `System.gc` as a "proof clock" for reachability.**

## 9. Reference cycles: the weakness of reference-count thinking

Suppose two objects:

```java
class Node {
    Node next;
}
```

and inside a method:

```java
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;
```

This is illustrative code inside a method. When **no strong path from GC roots** to `a` or `b` remains, the cycle `a → b → a` is not enough to keep them alive. A tracing collector can leave them unmarked during an appropriate trace.

However, **do not rush to conclude GC has reclaimed them immediately** when writing:

```java
a = null;
b = null;
```

Assigning null does not itself trigger a GC cycle and does not prove there are no other references (static cache, JNI, thread-local, a field of a live object, etc.). The sufficient condition for an object **to be garbage** must consider the **entire actual root graph**, not just two variables in a code snippet.

### Reachable and unreachable cycles differ

```text
Case 1: ROOT → A → B → A  (both A and B reachable)
Case 2:         A → B → A  (no root path, eligible for reclaim)
```

In case 1, the cycle stays alive because there is **an entry point from a root**. In case 2, all objects in the cycle can be candidates for reclamation after appropriate handling of special reference types.

## 10. Runnable Java 17+ example: simulating graph tracing with cycles

The following program **does not invoke GC itself**. It simulates the traversal algorithm from a set of roots **chosen by the learner**, so that the output is **exact and verifiable**, independent of collector run timing.

Create the file **`ReachabilityGraphDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public class ReachabilityGraphDemo {
    static final class Node {
        final String name;
        Node first;
        Node second;

        Node(String name) {
            this.name = name;
        }
    }

    static Set<Node> trace(Node... roots) {
        Set<Node> marked =
                Collections.newSetFromMap(new IdentityHashMap<Node, Boolean>());
        Deque<Node> worklist = new ArrayDeque<>();

        for (Node root : roots) {
            if (root != null) {
                worklist.addLast(root);
            }
        }

        while (!worklist.isEmpty()) {
            Node current = worklist.removeFirst();

            if (!marked.add(current)) {
                continue;
            }

            if (current.first != null) {
                worklist.addLast(current.first);
            }
            if (current.second != null) {
                worklist.addLast(current.second);
            }
        }
        return marked;
    }

    static void printMarked(Set<Node> marked) {
        List<String> names = new ArrayList<>();
        for (Node node : marked) {
            names.add(node.name);
        }
        Collections.sort(names);
        System.out.println("reachable (" + marked.size() + "): " + names);
    }

    public static void main(String[] args) {
        Node rootA = new Node("rootA");
        Node rootB = new Node("rootB");
        Node branch = new Node("branch");
        Node leaf = new Node("leaf");
        Node orphanA = new Node("orphanA");
        Node orphanB = new Node("orphanB");

        rootA.first = branch;
        rootB.first = branch;
        branch.first = leaf;
        leaf.first = rootA; // Cycle reachable from rootA/rootB.

        orphanA.first = orphanB;
        orphanB.first = orphanA; // Cycle detached from the selected roots.

        System.out.println("total modeled nodes: 6");
        Set<Node> firstPass = trace(rootA, rootB);
        printMarked(firstPass);
        System.out.println("outside selected roots: " + (6 - firstPass.size()));

        rootA.first = null;
        rootB.first = null;

        Set<Node> secondPass = trace(rootA, rootB);
        printMarked(secondPass);
        System.out.println("outside selected roots: " + (6 - secondPass.size()));
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 ReachabilityGraphDemo.java
java ReachabilityGraphDemo
```

**Exact standard output:**

```text
total modeled nodes: 6
reachable (4): [branch, leaf, rootA, rootB]
outside selected roots: 2
reachable (2): [rootA, rootB]
outside selected roots: 4
```

### Line-by-line explanation

1. The program creates **six `Node` objects** in the modeled graph.
2. `trace(rootA, rootB)` has two roots and finds `rootA`, `rootB`, `branch`, `leaf`, i.e., four nodes.
3. The cycle `orphanA ↔ orphanB` has no edge from the two selected roots, so those two nodes are not marked by `trace`.
4. Removing the two edges `rootA.first` and `rootB.first`; the second trace finds only the two roots. `branch`/`leaf` have lost their entry path, and the orphan cycle still has no entry path.
5. `IdentityHashMap` is used so the `marked` set compares **object identity (`==`)**. GC marks by object identity; it does not use an application-overridden `equals()` to merge different objects into one.
6. `Collections.sort(names)` makes the output deterministic by name regardless of traversal order or identity hash.

**Crucially:** the output `outside selected roots` means **not reachable in the `Node.first/second` graph from the two simulated roots**. It does **NOT** prove HotSpot has actually reclaimed any object! In `main`, the local variables `branch`, `leaf`, `orphanA`, `orphanB`, and the `firstPass` set may still hold references that the JVM must consider depending on liveness. The simulation also ignores references in `String name`, collection metadata, and other roots.

This is why writing a learning model and measuring real GC are **two different tasks**. The model demonstrates the exact algorithm within the defined graph; it does not claim to be a heap inspector.

### 10.1. Complexity of tracing

If each object is marked once and each strong reference edge is examined a finite number of times, graph traversal has complexity **O(V + E)** where V = number of object vertices and E = number of reference edges within the traversal scope. Auxiliary memory typically depends on the marked set and worklist.

In a real JVM, costs also include:

- **Root scanning** and metadata to locate references.
- **Barriers/remembered sets** when concurrent or generational.
- **Reference processing**, moving/compaction, and pointer updates.
- **Load balancing/work stealing** among GC threads.
- **Object layout**, region selection, card scanning, and fragmentation.

Do not use O(V+E) to infer that all GC pauses take the same linear time across the entire heap: collectors optimize by the set of objects/regions to process, execute in parallel or concurrently, and only certain phases are STW.

## 11. `Reference.reachabilityFence`: keeping an object alive until a required point

The JDK provides the **`Reference.reachabilityFence(Object)`** API since Java 9 to ensure an object remains **strongly reachable** up to a specific execution point, when that matters for resource/native code safety.

Conceptual example:

```java
import java.lang.ref.Reference;

final class NativeResource {
    final long handle;

    NativeResource(long handle) {
        this.handle = handle;
    }

    void perform() {
        long h = handle;
        NativeApi.useHandle(h);
        Reference.reachabilityFence(this);
    }
}
```

**This is an illustrative snippet, not standalone runnable**: `NativeApi` is not defined, and `handle` merely represents a native resource. Meaning:

- In the execution path, after fetching `handle`, native code may be using the resource associated with the object.
- It is not safe enough to assume the receiver `this` automatically stays live until the end of the method just because the method has not returned yet.
- `reachabilityFence(this)` helps ensure the receiver stays alive until after the native call in the required context.
- The API **does not require GC to reclaim the object immediately after the fence**, nor does it replace explicit resource lifecycle management.

If a resource needs to be closed in a timely manner, using `AutoCloseable`/try-with-resources remains the preferred design.

## 12. Finalization and object resurrection: a historical exception to know

Older Java classes sometimes override `finalize()`. In legacy finalization models, a finalizer can make an object **reachable again** (resurrection), for example by assigning `this` to a static field. Therefore, the diagram "not strongly reachable means definitely freed immediately" is insufficient to describe all processing phases.

However:

- **Finalization was deprecated in Java 9 and deprecated for removal in JDK 18**; this mechanism is discouraged in modern Java.
- There is no guarantee that a finalizer will run on time or at all before the process exits.
- Finalizers carry risks of security issues, reliability problems, deadlocks, and memory retention.
- New applications should not be written relying on resurrection or `System.gc()` to force finalization.

Sensible alternatives are **explicit close**, `try-with-resources`, and **Cleaner/phantom-based cleanup** only as a fallback when needed. Cleaner also has non-deterministic timing, and the cleaning action must not hold a strong reference back to the referent it needs to track.

When reading very old reachability documentation, recognize that **finalization queue** rules could force the collector to retain objects for additional time; newer JVMs/JDKs continue to evolve to remove unsafe finalizer initialization paths.

## 13. GC eligibility differs from reclamation time and memory reuse time

Three easily confused states:

| Question | Meaning |
| --- | --- |
| Is the object still strongly reachable? | Is there a strong reference path from roots to the object at the relevant state? |
| Is the object eligible for collection? | Does it still need to be preserved under other reachability/reference processing rules? |
| Has the memory been reclaimed/reused? | Has the collector executed the phase that allows the corresponding space to be reused yet? |

An object that is no longer reachable may:

- Lie in a heap region not yet processed by any collection cycle.
- Be awaiting some reference processing/cleanup per semantics.
- Have its memory space marked reusable by the collector without immediately returning it to the OS.
- Be reclaimed in a collection, while **heap committed size** or **process RSS** does not decrease correspondingly right away.

Therefore, when measuring memory:

- `-Xmx` is the Java heap limit, **not** the number of heap bytes currently in use.
- `used heap` is not synonymous with the retained size of an object graph.
- `committed` and `reserved` differ; OS RSS is yet another metric.
- Dead objects do not prove the heap will immediately shrink.
- A Java memory leak is usually **unintended reachability**, not GC "forgetting to run".

## 14. Memory leaks caused by objects remaining unintentionally reachable

A tracing GC **cannot know business logic** that an object is "no longer needed". If a strong reference path from a root still exists, it is kept alive.

### 14.1. Static collections

```java
import java.util.ArrayList;
import java.util.List;

class Cache {
    static final List<byte[]> ITEMS = new ArrayList<>();

    static void add() {
        ITEMS.add(new byte[1024]);
    }
}
```

This is an illustrative class; while the class/static state remains alive, each `byte[]` added to the list will have a strong path via `ITEMS` → list backing array → element, until the application removes the reference or the class is appropriately unloaded.

Use caches with **entry count limits, TTL, eviction/size policies**, and ways to close associated resources when caching is actually needed.

### 14.2. Uncleaned ThreadLocal

A `ThreadLocal` can cause data to live long because threads in a thread pool persist. Even though the key has weak-reference semantics in some HotSpot/JDK structures, the **values** can remain held via the thread-local map until entries are cleaned up.

Safe programming rule when using thread pools:

```java
private static final ThreadLocal<String> CONTEXT = new ThreadLocal<>();

static void process() {
    try {
        CONTEXT.set("request");
        // process request ...
    } finally {
        CONTEXT.remove();
    }
}
```

This is a **snippet placed inside a class**, with no main. The `remove()` line helps prevent state leaks across reused threads. Do not confuse `ThreadLocal` with "data that destroys itself when the method ends".

### 14.3. Listeners, callbacks, executors, and queues

- An event publisher may hold listener instances by strong references.
- Scheduled tasks/futures may hold captured closures/objects.
- A blocking queue may hold undrained jobs, payloads, or responses.
- Long-lived class loaders may hold classes/metadata and chains of associated object graphs.
- JNI global references keep objects from GC even when Java source no longer has a visible variable.

**Fixing reachability issues means cutting/bounding unnecessary keep-alive paths**, not trying to call `System.gc()` repeatedly.

## 15. Using heap dumps and GC-root paths to debug leaks

Heap analyzers (for example Eclipse Memory Analyzer, VisualVM, or appropriate tooling) can help:

1. Capture a heap dump at the time needing investigation.
2. Identify classes with large or abnormally growing retained heap.
3. Select a suspect object/cluster of objects.
4. Inspect **Paths to GC Roots** or the retained/dominator tree.
5. Evaluate which edges are **strong references** and which reference types should be excluded from the keep-alive path to see the root cause.
6. Identify the field, array element, static cache, ThreadLocal, listener, JNI handle, or class loader holding the object.
7. Fix the reference lifecycle and re-measure after a comparable load cycle.

### What question does Paths to GC Roots answer?

Suppose the tool finds:

```text
GC Root: live application thread
  → Thread.threadLocals
  → ThreadLocalMap.Entry.value
  → RequestContext
  → byte[] payload
```

This is an **illustrative keep-alive path**, not a mandatory result on every JDK. If the request has ended but `RequestContext` remains in the worker thread's thread-local value, then GC is **right to keep it**, because a strong reference path from a root still exists.

A principled fix is lifecycle design: `ThreadLocal.remove()` in `finally`, bounding queues/caches, unregistering listeners, releasing JNI handles, closing resources. **Do not arbitrarily clear a reference still needed by another thread**, as doing so can introduce races or break application semantics.

### Dominator/retained size is not identical to shallow size

An object can be small yet **retain** many objects when it is the sole root path keeping them alive. For example, a static `Map` object's shallow size may be small, while its keys/values/arrays hold hundreds of MB. Retained size or dominator tree analysis helps find "who is holding whom", not just a table of classes with many instances.

## 16. GC logs and metrics cannot replace graph analysis

To understand collection frequency, pause times, and memory pressure, appropriate logging can be enabled for **HotSpot JDK 17+**:

```bash
java -Xlog:gc*:info -version
```

The command above runs the JVM to print the version and GC-related messages depending on timing; it **does not** generate significant workload by itself or produce a heap dump. With the simulation program above:

```bash
java -Xlog:gc*:info ReachabilityGraphDemo
```

If the output includes GC logs, line count/timing depends on the VM, heap size, and load. **There is no guarantee a GC cycle must occur in the small demo.** Therefore, only the two `println` groups of the program (section 10) have stable expected stdout when run without logging enabled.

Some common JDK diagnostics:

```bash
jcmd -l
jcmd PID GC.heap_info
jcmd PID GC.class_histogram
jcmd PID GC.heap_dump heap.hprof
```

In the commands above, **`PID` is the actual process ID, which must be replaced with the appropriate PID**. Taking a class histogram/heap dump can consume memory, disk space, or cause a large pause; perform this only in permitted environments. Actual commands and effects should be checked against `jcmd PID help` of the running JVM.

**GC logs tell when the collector works and memory statistics; heap dumps/root paths help show why an object is still reachable.** They answer different questions.

## 17. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Setting a variable to `null` frees the object immediately." | Only one reference path is lost; other paths may exist and GC may not have run yet |
| "Two objects pointing to each other will never be GC'd." | Tracing GC can reclaim cycles **not reachable from roots** |
| "GC only counts the number of references to an object." | Tracing collectors analyze **reachability from roots**, with special reference handling |
| "Every local variable in Java scope is a GC root until the end of the method." | Liveness/JIT optimizations can shorten the time the VM needs to keep an object alive |
| "Every loaded class with static fields exists until the process exits." | Class unloading/class-loader lifecycle can cause runtime classes to no longer be alive |
| "`WeakReference` holds an object strongly like an ordinary field." | A weak reference does not prevent clearing when the object is only weakly reachable |
| "`weak.get() == null` immediately after `strong = null`." | There is no GC timing guarantee; other paths may also keep the referent |
| "`System.gc()` definitely cleans up all dead objects immediately." | There is no such guarantee and the runtime can ignore explicit GC |
| "`ReferenceQueue.poll()` definitely reports an event right after dropping the strong ref." | The queue depends on reference processing/enqueuing and runtime timing |
| "`PhantomReference.get()` returns the object for recovery." | It **always returns null** |
| "Concurrent GC only scans the graph once without tracking writes." | Concurrent collectors need barriers/invariants for a changing graph |
| "Young GC ignores all old-to-young refs." | Remembered sets/card tables assist in handling cross-generation edges |
| "When GC reclaims objects, RSS must drop immediately." | Heap committed/reserved and RSS differ; the collector may keep free space for reuse |
| "A reachable object with no remaining business value is garbage that GC should understand on its own." | If a strong path remains, GC must keep it; this is a common cause of Java memory leaks |
| "A heap dump explains a leak on its own without examining roots." | Retaining paths, dominators, and object lifecycle must be examined |
| "An empty class cannot keep other objects alive." | Objects/classes/static references/runtime handles can participate in the root graph depending on lifecycle |

## 18. Exercises and solutions

### Exercise 1 — Cycle with no path from root

```text
ROOT → A       B ↔ C
```

**Question:** If there are no other edges, are B and C still strongly reachable from the root?  
**Answer:** No. They form an isolated cycle; tracing from ROOT only finds A.

### Exercise 2 — Cycle still reachable

```text
ROOT → A → B → C → B
```

**Question:** Can B/C be considered garbage just because they form a cycle?  
**Answer:** No. ROOT has a strong path through A to B/C.

### Exercise 3 — One object, two root paths

```text
ROOT1 → A → X
ROOT2 → B → X
```

**Question:** Is removing edge `A → X` enough to make X unreachable?  
**Answer:** Not yet, because `ROOT2 → B → X` still exists.

### Exercise 4 — Local variable and scope

**Question:** Does ending a Java source block guarantee GC immediately reclaims an object once referenced by a local variable?  
**Answer:** No. All strong paths, liveness, and GC scheduling must be considered; conversely, sometimes the VM does not need to keep an object until the very end of the block if the reference is no longer used.

### Exercise 5 — `WeakReference`

**Question:** `WeakReference<Object> w = new WeakReference<>(o);` if `o` still has a strong root path, is GC allowed to clear the weak referent just because `w` is weak?  
**Answer:** No. The object is still strongly reachable via the strong path.

### Exercise 6 — A weak reference is the only path

**Question:** When an object is only weakly reachable and the collector processes weak references, what can `w.get()` become?  
**Answer:** `null`, when the weak reference is cleared according to rules. The exact timing cannot be guaranteed from a null assignment in source code.

### Exercise 7 — Phantom get

**Question:** Can `PhantomReference.get()` be used to retrieve the object for cleanup?  
**Answer:** No; `get()` is always `null`. Cleanup should use other resource state without retaining a strong reference back to the referent.

### Exercise 8 — Static cache leak

**Question:** Why can `static List<Object>` keep one million objects alive even when the application no longer processes them?  
**Answer:** While the class/static cache stays alive, the list holds strong refs to elements; the collector does not know business value has ended. Eviction/removal and proper lifecycle management are needed.

### Exercise 9 — ThreadLocal

**Question:** After each request, the worker thread in the pool still exists. Why might the request context not be GC'd yet?  
**Answer:** ThreadLocal values can remain reachable via the runtime thread/local map. Use `remove()` in `finally` when the business scope ends.

### Exercise 10 — Young GC

**Question:** An old-generation object references a young-generation object. Can Young GC treat the young object as unreachable just because root scanning does not walk the entire old heap?  
**Answer:** No. The collector must handle cross-generation references appropriately, for example via remembered sets/card metadata.

### Exercise 11 — Concurrent graph mutation

**Question:** During concurrent marking, the mutator changes references while the collector is scanning. Why are barriers needed?  
**Answer:** To maintain marking invariants and avoid missing objects that must stay alive while the graph changes; how SATB/incremental-update is used depends on the collector.

### Exercise 12 — Heap size

**Question:** After GC, 50 MB of unreachable objects were reclaimed, but JVM process RSS did not decrease. Is GC definitely buggy?  
**Answer:** No. The JVM can retain committed heap/native pages for reuse; RSS and live-set are not identical.

### Exercise 13 — Identity or equality?

**Question:** Two `Node`s are different instances, yet `equals()` returns `true`; is the collector allowed to treat them as the same object?  
**Answer:** No. GC must manage **object identity**; application-defined `equals()` comparisons do not turn two allocations into one.

### Exercise 14 — A changing root path

**Question:** A listener is removed from an event bus but still remains in a scheduled task queue. Is it immediately eligible?  
**Answer:** Not enough evidence. The task queue may hold a strong path; all root paths must be checked.

### Exercise 15 — Finalizer and reachability

**Question:** Should `finalize()` be implemented to ensure a native handle is closed as soon as the object becomes unreachable?  
**Answer:** No. Legacy finalization does not guarantee timing/completion and can cause resurrection; prefer `AutoCloseable`/try-with-resources.

### Exercise 16 — `reachabilityFence`

**Question:** Does `Reference.reachabilityFence(obj)` force GC to collect `obj` immediately after the statement?  
**Answer:** No. It helps maintain reachability up to the required point; reclamation timing still depends on GC/runtime.

## 19. Checklist for explaining "why an object has not been GC'd yet"

1. Is the object currently in a static cache, collection, map, or backing array?
2. Does any Java thread still hold a live reference or `ThreadLocal` value?
3. Is any scheduled task, listener, callback, or future holding the closure/object?
4. Is there a related JNI global handle or VM-internal handle?
5. Is there a weak/soft/phantom reference that requires special interpretation of paths?
6. Does any other object in the graph still have a strong edge to it?
7. Is a class loader/class metadata lifecycle keeping static state alive?
8. Is the object merely **eligible**, or has the collector already run a cycle processing that region?
9. Is the heap dump/histogram reporting **shallow** or **retained** size?
10. Has the tool found Paths to GC Roots with weak/soft/phantom refs appropriately filtered?
11. Which generational/concurrent scheme is the collector using, and which phases do the logs show?
12. Is the goal to fix **unintended strong reachability** or merely to reduce committed heap/RSS?

## 20. Conclusion and reference documentation

To understand why Java GC keeps an object, start from the question **"is there a keep-alive reference path from GC roots to this object?"**. A tracing collector marks objects by graph rather than relying on reference counts or the age of a Java variable. Cycles without a root path can be reclaimed. Conversely, static caches, thread locals, JNI handles, and listeners can inadvertently create long-lived root paths, keeping objects alive even though the application has "finished processing them".

For concurrent and generational collectors, the underlying model remains reachability, but scanning is optimized using **marking invariants, barriers, cards, and remembered sets**. With `SoftReference`, `WeakReference`, `PhantomReference`, and cleanup, **reference edges do not have the same semantics** as a strong field. "No longer reachable" also differs from "memory has been reclaimed immediately" and even more from "RSS must drop instantly".

**Official references:**

- Java SE 17 — **`java.lang.ref` package**, describing reachability levels: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html
- Java SE 17 — **`Reference`** and `Reference.reachabilityFence`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html
- Java SE 17 — **`WeakReference`**, **`SoftReference`**, **`PhantomReference`**, **`ReferenceQueue`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- OpenJDK **JEP 421 — Deprecate Finalization for Removal**: https://openjdk.org/jeps/421
- Oracle JDK 17 — **Garbage Collection Tuning Guide**: https://docs.oracle.com/en/java/javase/17/gctuning/
- Oracle JDK 17 — **jcmd utility**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

**Remember:** GC does not need to "clear every reference in every object" before reclaiming a cycle. It needs to identify **the set of objects that must be kept alive starting from GC roots**, handle special reference types, and use the appropriate collector algorithm to reclaim reusable memory regions. When debugging the heap, **Paths to GC Roots** is the bridge between graph theory and why an object remains alive in a real application.
