# Reference Graphs, Unreachable Objects, and Circular References

## 1. Objectives

Java automatically manages the memory of most objects on the heap through **garbage collection (GC)**. However, to know whether an object can be freed, we must examine **paths from live roots (GC roots)** to that object, rather than just counting how many objects point to it.

Three key statements:

1. **There is a strong reference path from GC roots to an object:** the object is considered **strongly reachable** and cannot be reclaimed as garbage while that liveness path remains in effect.
2. **There is no longer a strong reference path from roots:** the object may only remain reachable via soft/weak/phantom references or be already unreachable; the corresponding reference processing rules must be considered.
3. **Two objects referencing each other in a cycle do not automatically create a memory leak:** a cycle no longer held from roots can be reclaimed by a tracing collector, even though the objects in the cycle still point to each other.

After this lesson, you will know how to:

- Represent the Java heap as a **directed graph**: nodes are objects/arrays, edges are references, and roots are the set of starting points.
- Traverse the graph along strong edges to determine reachable and unreachable groups.
- Explain accurately why an **A → B → C → A** cycle can or cannot be reclaimed by GC.
- Distinguish between **assigning null**, **going out of scope**, **eligible for GC**, **reference cleared**, and **memory reclaimed**.
- Understand the meaning of **strong**, **soft**, **weak**, **phantom references**, **ReferenceQueue**, and **Reference.reachabilityFence** in Java 17.
- Identify **logical memory leaks**: the graph is still reachable, but its business lifecycle has ended.
- Analyze **WeakHashMap**, static caches, listeners, ThreadLocal, thread pools, JNI references, and class loaders using paths to roots.
- Use Java 17+ to simulate a graph, observe weak references independently of GC timing, and use tools to inspect path to GC root/retained heap when troubleshooting.

**Scope:** this lesson explains reachability semantics and the tracing GC model. Specific root details, safepoints, marking barriers, reclamation timing, and class unloading may differ across JVMs/collectors.

## 2. The Object Reference Graph

Model definitions:

- **Vertex (vertex/node):** a Java object or array instance.
- **Directed edge:** a reference from object A to object B, for example A.child = B or A.elements[0] = B.
- **GC root:** a starting-point reference considered live by the collector in the current VM state.
- **Path:** a sequence of directed edges connecting a root to an object.
- **Strongly reachable:** an object can be accessed from a live source without going through the referent of a Reference object (SoftReference/WeakReference/PhantomReference).
- **Unreachable:** no longer reachable through any of the levels defined by java.lang.ref; eligible for its memory to be reclaimed when the JVM decides.

Diagram assuming all regular edges are strong:

~~~text
 GC ROOTS
   local session             static Registry.sessions
        |                             |
        v                             v
   Session A                      Cache C
        |                             |
        v                             v
   Account B                      Entry D
        |                             |
        v                             v
   Profile E                      Buffer F

 Group with no path from roots:
     X ------------> Y
     ^               |
     |               |
     +---------------+
~~~

There are strong paths from roots to **A,B,C,D,E,F**, so this group remains reachable. **X and Y** point to each other in a cycle without a root path, so they are not kept alive merely by referencing each other.

**Warning:** The diagram is illustrative only. If outside the diagram there is another live local, static field, JNI global reference, or path from another object pointing to X/Y, the conclusion about that group must change.

### 2.1. A reference is an edge, not a copied object

~~~java
// Illustration inside a method:
Object a = new Object();
Object b = a;
~~~

This is **one object**, with two variables referencing it. Assigning **a = null** removes one edge from variable a, but **b** can still hold the object if b is still live. Assigning null does not “destroy the object”.

In the heap, each reference field and object array element can create an additional edge:

~~~java
// Illustration:
Node parent = new Node();
Node child = new Node();
parent.next = child;
~~~

If parent is reachable, child is also reachable via **parent.next** until the edge changes or parent is no longer held.

### 2.2. Directed paths: A → B does not imply B → A

If A.next = B, then reachability from A to B may exist, but from B back to A **does not necessarily** exist. For the GC graph, edge direction matters.

**A weak edge** has different semantics from a strong edge: the WeakReference wrapper itself may be strongly reachable from a root, but that does not mean the referent is strongly held. Do not draw root→WeakReference→referent as two strong arrows and conclude the referent will not be GC'd.

## 3. Where Can GC Roots Come From?

In HotSpot and many real-world VMs, the root set includes live reference groups such as:

| Possible root source | Examples |
| --- | --- |
| Execution state of a live thread | Live local references, operand/register values needed for computation |
| Static state from live runtime classes | Static cache, singleton, registry |
| JNI/native global references | Native code holding a Java object via JNI GlobalRef |
| VM/internal runtime structures | References the VM must maintain in loading, synchronization, and runtime subsystems |
| Runtime-managed handles | Handles accounted for by a specific collector |

**Do not memorize a fixed list for every JVM.** Root discovery differs across implementations/collectors; some heap analysis tools also represent synthetic roots to construct the graph.

### 3.1. How long does a local variable stay alive?

A variable name inside curly braces in Java source **does not guarantee** the object is kept until the closing brace. The JIT/compiler can prove a reference is no longer needed before the end of the lexical scope, under permitted semantics.

When an object needs to be kept strongly reachable up to a point related to cleanup/reference processing, Java 17 provides:

~~~java
Reference.reachabilityFence(resource);
~~~

This call preserves **strong reachability at least until after the invocation**, does not trigger GC itself, and does not pin the object at a fixed memory address.

### 3.2. Static state also has a lifecycle

~~~java
class Registry {
    static final java.util.List<Object> ITEMS =
            new java.util.ArrayList<>();
}
~~~

If the runtime class Registry and its static state are still live, **ITEMS** can strongly hold the objects in the list. However, **static** is not a contract meaning “exists forever even when the class loader could already be unloaded”; in plugin/application servers, class loader lifetime plays an important role.

## 4. Marking: Finding the Reachable Set via Graph Traversal

A conceptual graph traversal:

~~~text
function markReachable(rootReferences):
    worklist = new Queue()
    visited  = new IdentitySet()

    for each rootReference:
        if rootReference != null:
            worklist.add(rootReference.target)

    while worklist not empty:
        object = worklist.remove()
        if object in visited:
            continue

        visited.add(object)
        for each strong reference field/array element of object:
            if referent != null:
                worklist.add(referent)

    return visited
~~~

The objects in visited are strongly reachable **according to the model's snapshot and root set**. The unmarked portion of the graph is not strongly held from those roots.

Use **IdentitySet**, not business equals(), because two objects may be equal in content but have different object identities; GC decides based on object identities.

### 4.1. Cycles do not cause graph traversal to loop infinitely

With:

~~~text
A ---> B ---> C
^             |
+-------------+
~~~

When encountering A again, the algorithm checks **visited** and skips it. Cycles do not prevent traversal from terminating. A tracing GC can mark and reclaim a group unreachable from roots without needing to “break each edge inside the cycle”.

A BFS/DFS traversal of a graph with N nodes and E edges typically has **O(N+E)** complexity in the model, with an appropriate visited structure. This is an algorithmic exercise, not a claim that every HotSpot collector implements queues and visited objects using Java collections.

## 5. Circular References: Rooted and Unrooted

Rooted case:

~~~text
ROOT --> A --> B --> C
         ^           |
         +-----------+
~~~

From ROOT to A, then B, then C, all are strongly reachable. Here the cycle exists and is kept alive by **ROOT → A**, not because the cycle itself maintains reachability from the JVM.

Unrooted case:

~~~text
      A --> B --> C
      ^           |
      +-----------+
  No more strong paths from roots into the group.
~~~

If no other mechanism holds them, the A/B/C group is eligible for reclamation by reachability-based GC.

### 5.1. Two-node cycle example

~~~java
// Illustrative code, Node has field Node next:
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;

a = null;
b = null;
~~~

If there are no other edges from roots to a/b, the cycle does not prevent GC by itself. However, if the program previously wrote **CACHE.put("cycle", a)**, then CACHE can hold a and also b; merely setting the locals to null does not remove the cache entry.

### 5.2. Pure reference counting differs from tracing GC

Basic reference counting can retain a cycle because each object still has an incoming reference from the other object, keeping the count from reaching 0. Tracing GC determines liveness via root paths, so an unrooted cycle can be reclaimed.

This comparison applies only to **pure reference counting without cycle collection**. Some runtimes use ref counting with an added cycle-detection mechanism; one should not overgeneralize this as “every ref-counting system leaks cycles”.

### 5.3. Strongly connected components (SCC)

A group of nodes is **strongly connected** if every node has a directed path to every other node in the group. SCC is a useful tool for reasoning about cycles. However, GC is not required to analyze SCCs before reclaiming; it only needs reachability relationships to match collector semantics.

## 6. Java 17+ Example 1 — Traversing an Object Graph Yourself

Create file **ReachabilityGraphDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ReachabilityGraphDemo {
    static final class Node {
        final String name;
        Node next;

        Node(String name) {
            this.name = name;
        }
    }

    static Set<Node> markFrom(Node... roots) {
        Set<Node> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());
        ArrayDeque<Node> queue = new ArrayDeque<>();

        for (Node root : roots) {
            if (root != null) {
                queue.addLast(root);
            }
        }

        while (!queue.isEmpty()) {
            Node node = queue.removeFirst();
            if (!visited.add(node)) {
                continue;
            }
            if (node.next != null) {
                queue.addLast(node.next);
            }
        }

        return visited;
    }

    static String sortedNames(Iterable<Node> nodes) {
        TreeSet<String> names = new TreeSet<>();
        for (Node node : nodes) {
            names.add(node.name);
        }
        return names.toString();
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");
        Node d = new Node("D");
        Node e = new Node("E");

        a.next = b;
        b.next = c;
        c.next = a;
        d.next = e;
        e.next = d;

        Set<Node> reachable = markFrom(a);
        List<Node> all = Arrays.asList(a, b, c, d, e);
        Set<Node> notReached =
                Collections.newSetFromMap(new IdentityHashMap<>());
        notReached.addAll(all);
        notReached.removeAll(reachable);

        System.out.println("reachable=" + sortedNames(reachable));
        System.out.println("notReached=" + sortedNames(notReached));
        System.out.println("cycleA=" + (c.next == a));
        System.out.println("cycleD=" + (e.next == d));
    }
}
~~~

Compile/run with Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 ReachabilityGraphDemo.java
java ReachabilityGraphDemo
~~~

**Exact stdout:**

~~~text
reachable=[A, B, C]
notReached=[D, E]
cycleA=true
cycleD=true
~~~

Explanation:

1. The root of the **simulation** is a.
2. The algorithm traverses a→b→c→a and stops because a is already visited.
3. d/e form a separate cycle with no path from root a, so they are not marked.
4. **Both groups have cycles**, but only the a/b/c group is reachable from the chosen root.

**Extremely important limitation:** The program is still holding references to d and e in locals and in the **all** collection for calculation. Therefore **notReached=[D,E] is the result of the traversal model**, not proof that the JVM GC considers d/e actually unreachable! To test real GC, one must consider the real root set and reference processing, not use a Java variable **notReached** that we constructed as the source of truth.

### 6.1. Why not use a regular HashSet?

If Node overrides equals() based on name, two Node objects with different identities but the same name could be merged into one by HashSet. **IdentityHashMap** ensures objects are compared by reference identity, which matches graph simulation for the heap.

## 7. Distinguishing Four Commonly Confused Stages

| Situation | What can be concluded |
| --- | --- |
| **A local is assigned null** | Removed one specific reference edge; not yet known whether the object still has other root paths |
| **No more strong paths from roots** | The object may only be softly/weakly/phantom reachable or completely unreachable |
| **Eligible for collection** | The JVM may reclaim it when GC runs/is appropriate; **there is no deadline** |
| **Memory reclaimed** | The collector has actually processed and reclaimed it; cannot be inferred merely from assigning null |

### 7.1. System.gc() does not guarantee reclamation timing

~~~java
Object value = new Object();
value = null;
System.gc();
~~~

There is no contract guaranteeing that the collector has reclaimed the exact object after the call. In some configurations, explicit GC may be disabled/tuned; the collector may not process the object on the test's exact schedule.

**Do not assert** WeakReference.get()==null right after System.gc() and treat the test as standard Java.

### 7.2. Heap used, committed, and RSS are different

If the collector reclaims many objects, heap **used** may decrease, but the JVM may still keep memory **committed/reserved** for future allocations. Process RSS also involves native memory, code cache, stacks, metaspace, and page management. Do not infer “a graph is no longer reachable” as “RSS decreases by that exact number of bytes” at the same time.

## 8. Strong, Soft, Weak, and Phantom Reachability

Java SE 17 provides the **java.lang.ref** package. Reference objects allow a program to partially observe a referent's lifecycle without necessarily holding it via a strong edge.

| Type | Does it hold the object like a normal strong reference field? | When to use? |
| --- | --- | --- |
| **Strong reference** | Yes | Normal ownership/reference |
| **SoftReference** | Not at the strong level; the collector may clear it based on memory demand | Certain memory-sensitive caches |
| **WeakReference** | No; GC may clear it when the referent is only weakly reachable | Weak-key mappings, canonical registry |
| **PhantomReference** | Not used to read the referent; get() is always null | Lifecycle notification/cleanup bookkeeping |
| **ReferenceQueue** | Not a reachability level of the referent | Receives Reference objects after the collector enqueues them |

The levels in the java.lang.ref documentation follow the chain **strong → soft → weak → phantom → unreachable**. Having a weak reference pointing to an object does **not** prevent it from being reclaimed forever.

### 8.1. WeakReference does not keep the referent alive

~~~java
// Illustration inside a method:
Object o = new Object();
WeakReference<Object> weak = new WeakReference<>(o);
~~~

**weak** itself is a Java object. If a root points strongly to the **weak** wrapper, the wrapper stays alive; however, the **referent o** can be cleared/reclaimed when there are no suitable strong/soft paths left.

### 8.2. SoftReference has no TTL or “live until out of RAM” contract

Soft references are cleared according to VM policy and memory conditions. They should not be used as a cache mechanism with exact eviction timing/size. If the cached value disappears, the code must be able to recreate it safely.

### 8.3. PhantomReference.get() always returns null

Phantom references are typically paired with **ReferenceQueue** to receive notifications, not as a way to retrieve an already “dead” object. Use **Cleaner** or PhantomReference when designing cleanup that needs post-mortem mechanisms, but do not rely on GC to close sockets/files/DB connections on time.

### 8.4. Finalization is a legacy solution not to be relied upon

Java object finalization has reliability, performance, and security issues; on JDK 17 it is deprecated. Do not use **finalize()** to build transaction logic or mandatory resource management. **try-with-resources** and explicit close() are more suitable for resources with a clear lifecycle.

## 9. Java 17+ Example 2 — WeakReference with Deterministic Stdout

Create **WeakReferenceDemo.java**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak = new WeakReference<>(strong);

        System.out.println("whileStrong=" + (weak.get() != null));
        Reference.reachabilityFence(strong);

        strong = null;
        System.out.println("afterDrop=timing-not-guaranteed");
        System.out.println("wrapperAlive=" + (weak != null));
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 WeakReferenceDemo.java
java WeakReferenceDemo
~~~

**Stdout:**

~~~text
whileStrong=true
afterDrop=timing-not-guaranteed
wrapperAlive=true
~~~

- When printing **whileStrong**, **strong** is guaranteed to remain reachable until after **Reference.reachabilityFence(strong)**, so the referent has not been reclaimed at the time of reading.
- After **strong=null**, the program intentionally does not print weak.get() because the result after GC is non-deterministic.
- **wrapperAlive=true** only states that the Java reference wrapper is not null; it does not mean the referent is still strongly reachable.

To observe GC, you can add:

~~~java
// Snippet added to main, result is NOT fixed:
System.gc();
System.out.println("stillPresent=" + (weak.get() != null));
~~~

**stillPresent** may be true or false depending on GC, other references, and timing. Do not use that output as a problem with a single standard stdout.

## 10. ReferenceQueue: Receiving Notifications Without Controlling GC

Illustrative example (requires imports from java.lang.ref):

~~~java
ReferenceQueue<Object> queue = new ReferenceQueue<>();
Object referent = new Object();
WeakReference<Object> watch = new WeakReference<>(referent, queue);
referent = null;
Reference<?> notice = queue.poll();
~~~

You cannot assert **notice != null** immediately upon assigning referent=null. The queue may receive the reference after the collector determines the corresponding reachability change.

**The Reference wrapper itself must be kept reachable** when you want to receive notifications: registering it with a queue does not mean the queue always keeps it alive from the moment of registration. If the wrapper is lost, the application may not see the notification it wants to process.

### 10.1. Avoid accidentally preventing the referent from being GC'd

A subclass of WeakReference that adds a **strongReferent** field pointing back to the referent will create an accidental strong path, making the referent no longer weakly reachable as intended. For cleanup metadata, store independent information such as an identifier/native handle instead of strongly holding the referent itself.

### 10.2. Use try-with-resources for external resources

~~~java
// Illustration; path is a declared java.nio.file.Path:
try (java.io.InputStream in =
             java.nio.file.Files.newInputStream(path)) {
    // Process data.
}
~~~

This is not a standalone program; it requires the path variable and IOException handling. **close()** is called when exiting try-with-resources according to Java semantics, without waiting for GC.

## 11. WeakHashMap: A Weak Key Can Still Be Strongly Held by Its Value

WeakHashMap uses weak references for **keys**, while **values** are normally held by the map with strong references. This is a very common trap:

~~~text
GC Root ---> WeakHashMap
                |
                +-- weak key ------> Key K
                |
                +-- strong value --> Value V
                                       |
                                       +-- strong field --> Key K
~~~

If Value strongly references back to Key, the path **root → map → value → key** still exists, even though the key entry inside the map is weak. The key may therefore never become eligible for removal as originally intended.

### 11.1. Java 17+ Example 3 — Key Held by Value

Create file **WeakMapPitfallDemo.java**:

~~~java
import java.util.WeakHashMap;

public class WeakMapPitfallDemo {
    static final class Key {
        final int id;

        Key(int id) {
            this.id = id;
        }
    }

    static final class Value {
        final Key backReference;

        Value(Key key) {
            this.backReference = key;
        }
    }

    static final WeakHashMap<Key, Value> CACHE =
            new WeakHashMap<>();

    public static void main(String[] args) {
        Key key = new Key(7);
        Value value = new Value(key);
        CACHE.put(key, value);

        key = null;
        value = null;

        System.out.println("entries=" + CACHE.size());
        System.out.println("valueBackReference=true");
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 WeakMapPitfallDemo.java
java WeakMapPitfallDemo
~~~

**Stdout:**

~~~text
entries=1
valueBackReference=true
~~~

**Explanation:** CACHE is a static collection used by main; it strongly references Value, and Value.backReference strongly references Key. The entire graph remains reachable even though both locals are set to null. The second line describes the back-reference path in the class structure, independent of whether GC runs.

If Value did not point back to Key, a key with no remaining strong path could be reclaimed, though the exact time the entry disappears or size() changes is not guaranteed immediately after local=null.

### 11.2. Using weak references for the right needs

WeakHashMap is appropriate when the map does not want to be a long-lived owner of the keys. However:

- Other root paths to keys may exist.
- Values may hold keys or hold objects that reference keys.
- Clearing/enqueuing/expunging is not necessarily synchronous with the line of code that just set null.
- If a bounded cache/exact eviction is needed, weak keys alone are not enough.

## 12. Logical Memory Leaks in Java

A **logical memory leak** is usually not “GC failing to reclaim an unreachable object”. It is usually an **object graph that is still reachable** even though **its useful lifetime has ended according to application design**.

Example:

~~~text
Static Registry (rooted)
      |
      v
Map<UserId, Session>
      |
      +--> Session1 --> Cart --> ProductGraph
      +--> Session2 --> Cart --> ProductGraph
      +--> Session3 --> Cart --> ProductGraph
      +--> ...
~~~

If the application keeps adding sessions without removing/expiring them, the graphs remain reachable. GC is **right not to reclaim** them. The collection lifecycle must be fixed instead of calling System.gc() more often.

### 12.1. Typical root paths that cause leaks

| Source | Retention path | Fix |
| --- | --- | --- |
| **Static cache/map** | Root → static → map → values → graph | Max size, TTL, eviction, remove |
| **Event bus/listener registry** | Root → publisher → listener → captured object | Unsubscribe at lifecycle stop |
| **ThreadLocal** | Live thread → ThreadLocalMap → value → graph | remove() in finally |
| **Thread pool/executor** | Thread/queue → task → captured closure | Complete/cancel task, shutdown pool |
| **Class loader** | Root → TCCL/registry → loader → classes/metadata | Clear references, stop worker threads |
| **HTTP sessions** | Session manager → session → large graph | Expire/invalidate, limit data |
| **Object pool** | Root → pool → idle objects | Bound pool, release entries |
| **JNI GlobalRef** | VM/native root → object graph | Delete global reference by lifecycle |

**ThreadLocal in a thread pool** requires attention: a request finishing does not mean the pooled thread finishes. If the value is not removed, it can retain the request graph across many processing cycles.

### 12.2. Event listener leaks are not caused by cycles

~~~text
Long-lived Publisher --> Listener --> View
                              ^         |
                              |         |
                              +---------+
~~~

The Listener↔View cycle does not cause a leak by itself. However, Publisher is held by a root and references Listener, so the entire group remains reachable. Unsubscribing Listener can cut the root path, provided no other retention path remains.

### 12.3. ClassLoader and redeploy

A web container loads a plugin using Loader-v1, then redeploys Loader-v2. If a pooled thread still has **contextClassLoader = Loader-v1**, loader v1 and its associated metadata/classes/objects may remain reachable. Class unloading will not free them as desired until the appropriate lifecycle/reference paths are resolved.

That is memory retention via a **GC root path**, not “GC failing to handle a reference cycle”.

## 13. Shallow Size, Retained Size, and Dominators

Heap analyzers commonly use:

- **Shallow size:** the byte size of the object itself, excluding all descendants.
- **Retained size:** the size of the graph that remains reachable only because of the examined object/dominator, according to the tool's model.
- **Dominator:** node D dominates X if every path from the super-root to X passes through D.
- **Path to GC Root:** one or more paths showing why an object is still reachable.
- **Incoming references:** the objects/roots currently pointing to the suspected object.

Example:

~~~text
Root --> Cache --> Entry --> byte[10_000_000]
~~~

Cache may have a small shallow size but a very large retained size if there is no other root path to the byte array. Conversely:

~~~text
Root1 --> CacheA --> SharedObject
Root2 --> CacheB --> SharedObject
~~~

Removing CacheA will not necessarily make SharedObject eligible; Root2→CacheB still holds it. A **shortest path to GC Root** is useful, though not necessarily the only path. Do not infer a leak root cause from a single path when an object has multiple valid owners.

### 13.1. Why inspect the dominator tree?

Instead of only sorting object classes by instance count, the dominator tree points out which object/collection is exclusively retaining the most memory. For example, an ArrayList with a small shallow size managing hundreds of thousands of listeners with large captured graphs is the real point to investigate.

Do not arbitrarily add two retained sizes together because graphs can overlap or have different dominance relationships.

## 14. GC Timing and Concurrent Collectors

HotSpot can use different collectors: Serial, Parallel, G1, ZGC, and variants by JDK. Some perform marking concurrently, using barriers and multiple GC cycles.

Invariants at the semantic level:

- Java code has no deadline guaranteeing an unreachable object will be reclaimed within X milliseconds.
- The JVM must preserve memory safety and reference semantics while objects/fields are updated.
- The object graph changes as threads execute; diagrams on paper are idealized snapshots.
- GC may relocate objects and update references; Java's reference identity/equals semantics are still preserved.
- If an object is no longer needed at the business layer but is still strongly reachable, the collector must not arbitrarily discard it as garbage just to shrink the heap.

### 14.1. GC is a memory mechanism, not transaction cleanup

If you need to close a file, socket, cursor, or DB transaction on schedule, use explicit close/try-with-resources. GC/ReferenceQueue/Cleaner are used for supplementary cleanup cases that tolerate non-determinism, not as a commit/rollback mechanism.

## 15. Using Tools to Inspect Paths to GC Roots

### 15.1. Observe before collecting a heap dump

Ask:

1. Is any object type growing after each request/task even though its lifecycle has ended?
2. Does cache size/listener count/thread count grow without reaching a steady state?
3. Do object count and live heap across measurement points grow continuously, or only due to warm-up?
4. Are old plugin class loaders still present after redeploy?
5. Do GC logs show different heap usage after collection compared to before?

A single memory snapshot is usually **not enough** to prove a leak. You need trends under workload and an understanding of ownership.

### 15.2. jcmd and HotSpot Java 17 GC logs

Examples (replace **<PID>** with the real process ID):

~~~bash
java -Xlog:gc*=info YourMainClass
jcmd
jcmd <PID> help
jcmd <PID> GC.heap_info
jcmd <PID> GC.class_histogram
~~~

Commands and output details depend on the JDK/JVM, attach permissions, and configuration. **YourMainClass** is a placeholder for the real main class. On production systems, consider diagnostic overhead and data policies.

### 15.3. Heap dump

In permitted environments, HotSpot can support:

~~~bash
jcmd <PID> GC.heap_dump /path/to/heap.hprof
~~~

A heap dump can be very large and contain personal/confidential application data. Taking a dump can impact latency or trigger GC depending on options. Do not run it in production without reviewing the cost, permissions, and appropriate operational guidelines.

Some analysis tools:

- **Eclipse Memory Analyzer (MAT):** dominator tree, retained heap, paths to GC roots.
- **VisualVM:** heap dump and heap sampling.
- **Java Flight Recorder (JFR):** allocation/runtime profiling depending on event configuration.
- **jcmd GC.class_histogram:** instance distribution at a point in time.

Tools may represent soft/weak/phantom reference edges differently from strong paths. When hunting leaks, choose the right filters and do not accidentally treat a weak referent as a strong path holding the object.

## 16. Graph-Based Memory Leak Debugging Workflow

**Step 1.** Reproduce with equivalent input/workload; record the number of sessions/tasks/objects created and completed.

**Step 2.** Collect metrics and snapshots at comparable points (after warm-up, after cleanup), avoiding comparing a peak snapshot with an idle snapshot.

**Step 3.** Identify classes/arrays increasing in count and their allocation sites.

**Step 4.** Inspect dominators with high retained size; do not look only at shallow size.

**Step 5.** Open **path to GC root** for an object whose lifecycle has ended. Identify which static cache, live thread, ThreadLocal, listener, JNI, or class loader is holding it.

**Step 6.** If a cycle is seen, ask “where is the root path into the cycle?”. A cycle is not a cause by itself.

**Step 7.** Fix the actual **ownership/lifetime**: remove/evict/cancel/unsubscribe/close, clean up in finally or the appropriate scope.

**Step 8.** Measure again under the same workload. Verify that object counts/retained graph return to baseline or stabilize.

**Step 9.** Check concurrent access and race conditions in caches/registries.

**Step 10.** Establish bounds and long-term monitoring instead of relying on manual GC operations.

## 17. Common Mistakes

1. **“Java collects garbage when reference count reaches 0.”** Incorrect as a general rule of tracing GC.
2. **“A ↔ B is always a memory leak.”** False if the cycle has no root path.
3. **“Clearing one local with null guarantees the object is reclaimed.”** False if other references remain or GC has not run yet.
4. **“System.gc() definitely cleans up every dead object.”** False regarding timing/guarantee.
5. **“Strongly reachable only requires the object to have any incoming edge.”** False: a retention path from roots is required.
6. **“The WeakReference wrapper is alive, so the referent is alive.”** False: the wrapper and referent are two objects.
7. **“WeakReference.get() is immediately null after value=null.”** False: reference processing is not synchronous with assigning null.
8. **“SoftReference is a fixed-TTL cache.”** False: collector policy decides clearing.
9. **“PhantomReference.get() returns the object when it is about to be GC'd.”** False: get is always null.
10. **“A WeakHashMap value cannot hold its key.”** False: value→key can create a strong path.
11. **“Because Java has GC, Java cannot leak.”** False: a graph that is still reachable when no longer needed is a logical leak.
12. **“Every local in source scope is always a root until the end of the block.”** False: JIT liveness can be shorter.
13. **“A static field is definitely a root that exists until the end of the process.”** Not absolute; class-loader lifecycle has an impact.
14. **“One heap dump with many objects proves a leak.”** False: trend and ownership reasons are needed.
15. **“Shallow size and retained size are the same.”** False: the retained graph can be very large.
16. **“A dominator is just the object with the most incoming references.”** False: every path from the super-root to the node is the criterion.
17. **“Cycles appearing in a heap dump mean GC does not handle them.”** False: a snapshot can contain objects that are still reachable or not yet reclaimed on schedule.
18. **“A new class loader automatically frees the old loader.”** False if the old loader is still reachable.
19. **“ReferenceQueue.poll() is non-null right after System.gc().”** Not guaranteed.
20. **“Native resource cleanup must wait for a finalizer/Cleaner.”** False: prefer explicit lifecycle management.

## 18. Self-Check Exercises with Answers

**Question 1.** ROOT→A→B→A. If ROOT→A is removed and no other root path remains, are A/B eligible for collection?

**Answer:** Yes under the reachability model. The A/B cycle itself does not create a root path.

**Question 2.** ROOT→A→B→C→A. How many nodes are strongly reachable from ROOT?

**Answer:** A, B, C (three nodes).

**Question 3.** Object X is referenced by two locals p and q. p=null. Does X become unreachable immediately?

**Answer:** No if q is still live; static/other paths must also be considered.

**Question 4.** Graph A→B, B→C, C→B; D→E, E→D. Model root is A. Reachable?

**Answer:** A,B,C; D,E have no path from the model root, even though both groups contain cycles.

**Question 5.** Why does tracing GC reclaim an unreachable cycle while basic reference counting does not automatically reclaim it?

**Answer:** Tracing is based on root reachability; basic ref count does not reach 0 due to incoming edges internal to the cycle.

**Question 6.** In code x=null; System.gc(); is weak.get()==null always true?

**Answer:** No. GC may not run/complete in time, and the referent may still have other references.

**Question 7.** Static WeakHashMap<Key, Value> has Value.backReference to Key. Does setting local key=null guarantee the key can be collected?

**Answer:** No. The static map strongly holds value, and value strongly holds key.

**Question 8.** A live pooled thread holds a ThreadLocal value containing request data. The request finished, but the value was not removed. Why is the graph still reachable?

**Answer:** Thread→ThreadLocalMap→value is still a strong path, which can retain the entire graph.

**Question 9.** Root1→A→X, Root2→B→X. Does removing root1→A make X unreachable?

**Answer:** No; root2 still holds X.

**Question 10.** When does PhantomReference.get() return the referent?

**Answer:** It never returns the referent; it is always null.

**Question 11.** An object has a shallow size of 32 bytes but exclusively retains 100 MB of arrays. Can its retained size be large?

**Answer:** Yes; retained size reflects the graph exclusively retained through the object/dominator.

**Question 12.** A heap histogram shows 500 session objects after a load test. Is that enough to conclude a leak?

**Answer:** Not yet; you need to know the lifecycle, pending sessions, GC state, trend, and paths to root.

**Question 13.** When seeing a cycle in a DOM tree and the screen is already closed, what should you ask?

**Answer:** Is there any root path such as a listener/static cache/thread still holding the tree? A cycle by itself is not enough to conclude a leak.

**Question 14.** Does Java GC automatically release a file descriptor right when leaving a method?

**Answer:** Not guaranteed; use try-with-resources or explicit close.

**Question 15.** Why does simulating a graph with a List all containing all nodes not prove that “notReached” nodes are GC-unreachable?

**Answer:** List all and the locals themselves hold strong references to the nodes; the algorithm's root set is only a hypothetical input, not the VM's real roots.

## 19. Memorization Checklist

- Reachability is a **path from GC roots**, not a reference count.
- Traverse the graph along **strong edges**, with **visited** to handle cycles.
- An unrooted cycle **can** be reclaimed; there is no mandatory deadline.
- Assigning null only cuts **one edge**, it does not delete the object on command.
- **Eligible** is different from **reclaimed**, and System.gc cannot dictate timing.
- Weak/soft/phantom references have different semantics from strong; queue notification is non-deterministic.
- WeakHashMap can still leak if the value references the key.
- Java memory leaks are usually **graphs remaining reachable too long** via cache/listener/ThreadLocal/thread/class loader.
- Read heap dumps using **paths to GC roots**, **dominator tree**, **retained sizes**, and comparable checkpoints.
- Manage external resources via **explicit close**, not by relying on GC.
- When simulating, use **object identity** instead of business equals.
- Consult JLS/java.lang.ref documentation to distinguish standard semantics from collector implementations.

### Standard References

- **Java SE 17 — java.lang.ref package (Reachability):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html
- **Java SE 17 — Reference and reachabilityFence:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html
- **Java SE 17 — WeakReference:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- **Java SE 17 — PhantomReference:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html
- **Java SE 17 — ReferenceQueue:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html
- **Java SE 17 — WeakHashMap:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html
- **JLS SE 17, §12.6 — Finalization and reachability:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6
- **JVMS SE 17, §2.5.3 — Heap:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3
- **Oracle Java SE 17 Garbage Collection Tuning — Other Considerations:** https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html

**Conclusion:** An object in Java is not kept alive merely because another object in the same cycle still points to it. **A strong reference path from GC roots** is the deciding factor in the tracing model. An unrooted cycle group can be collected, whereas an object graph that the application no longer needs but is still reachable via a cache/listener/thread can cause a memory leak. Look for **GC root paths and lifecycle boundaries**, instead of trying to break every cycle or repeatedly calling System.gc().