# Why Circular References Do Not By Themselves Prevent Garbage Collection in Java 17+

**A cycle of strong references between Java objects does not by itself make them “immortal”.** In the *tracing garbage collection* model of common JVMs, an object is kept alive because **there is a strong reference path from the set of GC roots**, not merely because another object still points to it.

Consider two groups of objects:

~~~text
GC root ───► A ───► B
              ▲      │
              └──────┘

C ───► D
▲      │
└──────┘
~~~

- A and B point to each other, while **A is pointed to by a GC root**: A/B remain reachable.
- C and D also point to each other, **but there is no path from any GC root**: C/D can become garbage and be reclaimed.
- The edges C→D, D→C are not GC roots; they do not create a path from a root.

That is why **reachability-based garbage collection differs from simple reference counting**. In pure reference counting, each object still has at least one reference from the other object so its count does not drop to 0; tracing GC, on the other hand, can identify an entire cycle that is not reached from roots.

This standalone README belongs to **Java Core — Class & Object / Object Lifecycle**, focusing specifically on **“Why Circular References Do Not By Themselves Prevent Garbage Collection”**, applicable to **Java 17+**. The runnable program includes its file name, compilation command, and expected stdout. The graph examples are **reachability models**; they do not pretend to precisely measure a single JVM collection.

## 1. Learning Outcomes

After this lesson, you can:

1. Distinguish between “having a reference pointing to it” and “having a reference path from a GC root”.
2. Draw an object graph and identify reachable/unreachable nodes.
3. Explain why A→B→A does not prevent the two objects from becoming garbage.
4. Understand the concepts of GC roots, strong references, and edge directions.
5. Know the marking algorithm that starts from roots and uses a visited set to handle cycles.
6. Compare tracing GC with pure reference counting.
7. Distinguish **eligible for GC** from **actually reclaimed**.
8. Avoid predicting the exact outcome of `System.gc()` or `WeakReference.get()`.
9. Identify cycles retained by a static field, cache, listener, ThreadLocal, or thread.
10. Understand why assigning null to one variable does not necessarily cut all root paths.
11. Analyze weak references and the limitations of WeakHashMap.
12. Distinguish heap memory management from cleaning up resources outside the heap.
13. Use try-with-resources and AutoCloseable to manage resource lifecycles.
14. Know how to use paths-to-GC-roots when investigating memory retention.
15. Avoid writing finalizers as “GC confirmation experiments”.
16. Correctly solve scenarios involving multiple roots, self-loops, parent-child cycles, and listeners.

## 2. “Reachable” Is the Key Word

In the basic tracing GC model, the reachable set is determined as follows:

- Start from the set of **GC roots** defined by the runtime.
- Follow **strong reference** edges to objects.
- Repeat until there are no new objects.
- Objects that are not found are no longer strongly reachable from the root set in the model.

Example:

~~~text
ROOT ─► A ─► B ─► C
               ▲    │
               └────┘

D ─► E
▲    │
└────┘
~~~

From ROOT, A, B, and C can be reached. D and E cannot be reached, even though D/E form a cycle. A cycle only represents relationships between objects **inside the group**; it is not a path from a GC root **into** the group.

**Key takeaway:** It is not that “every reference keeps an object alive forever”; only retention paths that conform to the runtime/collector's rules determine reachability.

## 3. What Is a Strong Reference?

Ordinary Java references such as fields, local variables, and array elements are typically strong references:

~~~java
final class Node {
    Node next;
}

Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;
~~~

If local `a` is still considered a live root reference by the JVM, A is reachable and B can also be reached from A. If `a` and all other references from roots to the cycle are gone, the A.next/B.next references **do not by themselves pull the cycle back into the reachable set**.

However, the JVM/JIT can optimize the liveness of local references. You should not equate curly braces, variable names, or null assignments in source code with the exact moment the collector considers an object dead.

## 4. What Is a GC Root?

GC roots are starting points that help the collector find objects to keep. Common sources in the JVM include:

- Live references on thread call stacks/registers.
- References from live static fields/classes.
- Native/JNI references managed by the runtime as roots.
- Certain references held by JVM/runtime subsystems.

Root details depend on the implementation and collector; a simple list should not be treated as a complete internal description of every JVM.

An illustrative static root:

~~~java
class Registry {
    static Node retained;
}
~~~

When `Registry.retained` points to A in the cycle A↔B, the entire cycle can be reached from the root associated with the static field. If the field no longer holds the reference and **there is no other root path**, the cycle becomes a candidate for collection.

## 5. A Two-Node Cycle: When Is It Alive, and When Is It Not?

Scenario 1:

~~~text
ROOT ─► A ─► B
         ▲    │
         └────┘

Reachable: A, B
~~~

Scenario 2:

~~~text
ROOT ─► null

A ─► B
▲    │
└────┘

Reachable from ROOT: neither A nor B
~~~

In Scenario 2, A/B still point to each other. But the collector does not “start from A” or “start from B” just because they have reference fields.

If ROOT2→B still exists, both A and B become reachable again. Therefore, what matters is **the set of all root paths**, not just one local variable.

## 6. How Does Tracing GC Work at the Model Level?

A simple description:

1. Obtain the set of roots.
2. Mark objects directly reachable from the roots.
3. Follow the reference edges of marked objects.
4. Expand an object's edges only **the first time** it is encountered.
5. Unmarked objects can be reclaimed according to the collector's mechanism.
6. The collector may sweep, compact, copy, or perform other phases depending on the algorithm.

The **visited set** prevents traversing the cycle A→B→A forever. When returning to A, A has already been marked, so it does not need to be expanded again.

This is a **theoretical model**: Java has multiple collectors with generational memory regions, concurrent marking, barriers, and their own phases. Not every collector simply “stops the world, marks the entire heap, and sweeps”.

## 7. Runnable Program: Simulating Reachability with a Graph

Create **`ReachabilityModelDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public class ReachabilityModelDemo {
    static final class Node {
        final String name;
        Node next;

        Node(String name) {
            this.name = name;
        }
    }

    static Set<Node> mark(List<Node> roots) {
        Set<Node> visited = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        Deque<Node> pending = new ArrayDeque<>(roots);

        while (!pending.isEmpty()) {
            Node node = pending.pop();
            if (!visited.add(node)) {
                continue;
            }
            if (node.next != null) {
                pending.push(node.next);
            }
        }
        return visited;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");
        Node d = new Node("D");

        a.next = b;
        b.next = a;
        c.next = d;
        d.next = c;

        Set<Node> seen = mark(List.of(a));
        System.out.println("A=" + seen.contains(a));
        System.out.println("B=" + seen.contains(b));
        System.out.println("C=" + seen.contains(c));
        System.out.println("D=" + seen.contains(d));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ReachabilityModelDemo.java
java ReachabilityModelDemo
~~~

Stdout:

~~~text
A=true
B=true
C=false
D=false
~~~

**Boundary of this example:** This is the result from the **simulated root set `List.of(a)`**, not the JVM's actual GC root set. Within this very program, there are still local variables and Set references pointing to the nodes; `C=false` only says C was not found by the simulated algorithm from A, **not** that object C has actually been reclaimed by the Java GC.

`IdentityHashMap` creates an identity-based visited set, preventing a custom `equals` from mistaking two different objects for the same node.

## 8. Why Does Simple Reference Counting Struggle with Cycles?

The **pure reference counting** algorithm counts the references to each object. When the count drops to 0, the object is freed and the references it holds have their counts decremented.

Suppose:

~~~text
A ─► B
▲    │
└────┘

No external owner.
~~~

With a simple counter:
- A is still pointed to by B → A's count is not 0.
- B is still pointed to by A → B's count is not 0.
- If reclamation occurs only when count=0, the entire group can be kept forever.

Tracing GC is different: **no root reaches A/B**, so they are not marked and can be reclaimed.

You should not generalize that **every** system using reference counting cannot resolve cycles: it can be combined with cycle detection/collection. The problem described here is **pure reference counting with the count=0 rule**.

## 9. Comparison by Scenario

| Scenario | Pure reference counting | Tracing reachability |
| --- | --- | --- |
| Object with no references pointing to it | Count=0 | Unreachable |
| A↔B with no remaining owner | Counts may still be 1 | Entire cycle unreachable |
| ROOT→A↔B | Positive counts | A/B reachable |
| A points to itself, no owner | A's count may still be 1 | A unreachable |
| Multiple paths from roots into the cycle | Counts reflect edges | Just one path keeps the entire cycle |

Do not think of Java 17 GC as a simple reference counter. Tracing reachability is the key idea that explains why cycles do not make heap objects immortal.

## 10. Runnable Program: A Reference Cycle Leaving a Method

Create **`CycleScopeDemo.java`**:

~~~java
public class CycleScopeDemo {
    static final class Node {
        Node next;
    }

    static void buildCycle() {
        Node first = new Node();
        Node second = new Node();
        first.next = second;
        second.next = first;

        System.out.println("cycle created");
    }

    public static void main(String[] args) {
        buildCycle();
        System.out.println("method returned");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CycleScopeDemo.java
java CycleScopeDemo
~~~

Stdout:

~~~text
cycle created
method returned
~~~

The method does not store A/B in a static field, does not return them to the caller, and does not place them in a long-lived collection. After the method finishes, if there is no other root path, A/B can become unreachable **even though they still point to each other**.

Stdout **does not prove that GC ran**. The program may terminate before the collector has a reason to run again.

## 11. “Eligible for Collection” Differs from “Already Collected”

Three states to distinguish:

**Reachable:** still has a valid retention path from GC roots; it is not considered ordinary garbage merely because the user no longer uses it logically.

**Unreachable / eligible:** no longer strongly reachable under the corresponding condition; the collector can reclaim it.

**Actually reclaimed:** the JVM has actually reclaimed the memory in a subsequent GC run.

Therefore, the statement **“once there are no references from roots, GC can collect it”** is more accurate than **“when a method returns, the JVM frees it immediately”**.

The timing of reclamation depends on memory pressure, the collector, JVM options, the JIT, and other activity. You should not write tests that rely on specific timing that the JVM does not guarantee.

## 12. Runnable Program: A Static Reference Still Retains the Cycle

Create **`StaticOwnerDemo.java`**:

~~~java
public class StaticOwnerDemo {
    static final class Node {
        Node next;
    }

    private static Node head;

    static void registerCycle() {
        Node a = new Node();
        Node b = new Node();

        a.next = b;
        b.next = a;
        head = a;
    }

    public static void main(String[] args) {
        registerCycle();
        System.out.println("still linked=" +
                (head.next.next == head));

        head = null;
        System.out.println("owner removed");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 StaticOwnerDemo.java
java StaticOwnerDemo
~~~

Stdout:

~~~text
still linked=true
owner removed
~~~

Before `head=null`, the path root→static head→A→B keeps both reachable. After removing the static reference, the entire cycle **may** no longer have a root path. **Do not rely on the “owner removed” line to infer that GC immediately deleted A/B at that moment**.

## 13. Assigning `null` Does Not Necessarily Break the Cycle

Example:

~~~java
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;

a = null;
b = null;
~~~

The last two assignments clear the references in the two variables a/b; they **do not** modify the fields A.next/B.next on the heap. However, that causes no problem for tracing GC if no other root still reaches A/B.

It is not mandatory to write:

~~~java
// a.next = null;
// b.next = null;
~~~

to “break the cycle before GC”, and after `a=null` it is not even possible to access A through that variable a anymore.

What needs to be addressed in an application is **removing root→graph paths that are no longer used**, not breaking every edge between objects that are already unreachable.

## 14. Multiple Roots: Removing One Reference May Not Be Enough

~~~text
ROOT1 ─► A ─► B
          ▲    │
          └────┘
ROOT2 ────────► B
~~~

After ROOT1→A disappears, ROOT2→B still keeps both B and A alive. Observing that memory remains high does not prove that GC fails to handle cycles; it may be that **another owner still maintains a live path**.

Analyze all of the following:
- static fields/cache entries;
- active threads or tasks;
- closures/lambda captures;
- callback/listener registries;
- ThreadLocal values;
- JNI/native references;
- parent objects or collections that remain reachable.

## 15. Runnable Program: Modeling Adding/Removing Roots

Create **`RootSetDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public class RootSetDemo {
    static final class Node {
        Node next;
    }

    static int count(List<Node> roots) {
        Set<Node> marked = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        Deque<Node> todo = new ArrayDeque<>(roots);

        while (!todo.isEmpty()) {
            Node node = todo.pop();
            if (marked.add(node) && node.next != null) {
                todo.push(node.next);
            }
        }
        return marked.size();
    }

    public static void main(String[] args) {
        Node a = new Node();
        Node b = new Node();
        a.next = b;
        b.next = a;

        System.out.println("with root=" + count(List.of(a)));
        System.out.println("without roots=" + count(List.of()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RootSetDemo.java
java RootSetDemo
~~~

Stdout:

~~~text
with root=2
without roots=0
~~~

Even though the actual Java snippet has a/b locals, the root list that we **deliberately simulate** can be empty. This is a logical experiment, not a tool for forcing the JVM to reclaim memory.

## 16. A Memory Leak in Java Is Usually an Object That Is **Still Reachable**

An application-level “memory leak” in Java is usually **an object that is no longer needed from a business logic perspective but still has a strong path from a root**, because the application retains it for too long.

Examples:
- static List/Map that is never cleared/evicted;
- event listeners that are not unregistered;
- queued tasks storing closures that retain an entire screen/model;
- long-lived ThreadLocal values in pooled threads;
- cache keys/values linked to each other;
- threads that do not stop according to their lifecycle;
- native handles that still own a reference graph.

GC **cannot arbitrarily delete reachable objects** because the application still has a way to access them; the problem is **ownership**, not that “Java gets stuck on reference cycles”.

Conversely, a cycle with no remaining owner is **ordinary garbage** that can be handled by the collector.

## 17. Runnable Program: A Static Cache Retaining an Entire Cycle

Create **`CacheCycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CacheCycleDemo {
    static final class Node {
        Node next;
    }

    static final List<Node> CACHE = new ArrayList<>();

    static void install() {
        Node a = new Node();
        Node b = new Node();
        a.next = b;
        b.next = a;
        CACHE.add(a);
    }

    public static void main(String[] args) {
        install();

        System.out.println("cache=" + CACHE.size());
        System.out.println("cycle=" +
                (CACHE.get(0).next.next == CACHE.get(0)));

        CACHE.clear();
        System.out.println("cache cleared=" + CACHE.size());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CacheCycleDemo.java
java CacheCycleDemo
~~~

Stdout:

~~~text
cache=1
cycle=true
cache cleared=0
~~~

When CACHE contains A, the path static cache→A→B retains the cycle. When cleared, that path disappears. If there is no other root, A/B become eligible for GC. Having a cache size of 0 does not mean the JVM must immediately reduce committed heap bytes.

## 18. Event Listeners Keeping Objects Alive via Lambda Capture

A common pattern:

~~~text
GC root
   │
   ▼
Static listener registry ─► Callback ─► Screen
                               ▲          │
                               └──────────┘
~~~

Here the cycle Callback↔Screen may exist, but what matters is that **the registry still holds the Callback** and the Callback holds the Screen.

When a UI/screen/component reaches the end of its lifecycle:
- unsubscribe the listener;
- remove the callback from the registry;
- clear/detach subscriptions according to the contract;
- avoid capturing large object graphs unnecessarily.

## 19. Runnable Program: Callback Capturing Screen

Create **`ListenerOwnerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerOwnerDemo {
    static final List<Runnable> LISTENERS =
            new ArrayList<>();

    static final class Screen {
        final String title;

        Screen(String title) {
            this.title = title;
        }
    }

    static void open() {
        Screen screen = new Screen("Home");
        LISTENERS.add(() ->
                System.out.println("event=" + screen.title));
    }

    public static void main(String[] args) {
        open();

        System.out.println("listeners=" + LISTENERS.size());
        LISTENERS.get(0).run();

        LISTENERS.clear();
        System.out.println("after clear=" + LISTENERS.size());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ListenerOwnerDemo.java
java ListenerOwnerDemo
~~~

Stdout:

~~~text
listeners=1
event=Home
after clear=0
~~~

The listener remaining in the static registry keeps Screen reachable through the captured reference. After clearing, this owner path is removed. There is no claim about when the JVM GC actually reclaims Screen.

## 20. A ThreadLocal in a Thread Pool Is Also an Owner Path

A long-lived thread holds a ThreadLocalMap, whose value can retain A↔B. A request that has completed without removing its ThreadLocal can cause an object graph to outlive the request.

Practice:

~~~java
try {
    CONTEXT.set(context);
    // Process within the request.
} finally {
    CONTEXT.remove();
}
~~~

This is especially important when threads are reused in an executor/thread pool.

### Runnable Program

Create **`ThreadLocalOwnerDemo.java`**:

~~~java
public class ThreadLocalOwnerDemo {
    static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    static void process() {
        CONTEXT.set("request-7");
        try {
            System.out.println("inside=" + CONTEXT.get());
        } finally {
            CONTEXT.remove();
        }
    }

    public static void main(String[] args) {
        process();
        System.out.println("outside=" + CONTEXT.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ThreadLocalOwnerDemo.java
java ThreadLocalOwnerDemo
~~~

Stdout:

~~~text
inside=request-7
outside=null
~~~

This is deterministic cleanup of the owner relationship. It does not call System.gc and does not need to break any cycles that the value might reference.

## 21. A Self-Reference Is No Different in Principle

An object can point to itself:

~~~java
Node node = new Node();
node.next = node;
~~~

Graph:

~~~text
A ───► A
~~~

If there is no remaining strong path from GC roots into A, the self-edge does not keep A alive.

### Runnable Program

Create **`SelfCycleDemo.java`**:

~~~java
public class SelfCycleDemo {
    static final class Node {
        Node next;
    }

    static void create() {
        Node node = new Node();
        node.next = node;

        System.out.println("self=" + (node.next == node));
    }

    public static void main(String[] args) {
        create();
        System.out.println("returned");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SelfCycleDemo.java
java SelfCycleDemo
~~~

Stdout:

~~~text
self=true
returned
~~~

The self-loop exists inside the method, but it does not turn the object into a root after the method exits.

## 22. Reference Direction Matters Greatly

Suppose there is only A→B, with no B→A:

~~~text
A ─► B
~~~

If root→A, both A/B are reachable. If root→B but not root→A, then A is **not** automatically reachable simply because A points to B.

GC traversal follows **the reference direction from owner to target**; it does not treat every edge as bidirectional.

### Runnable Program

Create **`DirectedEdgesDemo.java`**:

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class DirectedEdgesDemo {
    static final class Node {
        Node next;
    }

    static Set<Node> follow(Node root) {
        Set<Node> visited = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        Node current = root;

        while (current != null && visited.add(current)) {
            current = current.next;
        }
        return visited;
    }

    public static void main(String[] args) {
        Node a = new Node();
        Node b = new Node();
        a.next = b;

        System.out.println("A to B=" + follow(a).contains(b));
        System.out.println("B to A=" + follow(b).contains(a));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DirectedEdgesDemo.java
java DirectedEdgesDemo
~~~

Stdout:

~~~text
A to B=true
B to A=false
~~~

The graph traversal example has deterministic output; it does not measure Java runtime roots.

## 23. Parent/Child Structures with Back References Are Normal

Doubly linked lists, trees with parent pointers, graphs, and domain relationships commonly contain cycles:

~~~java
final class TreeNode {
    TreeNode parent;
    java.util.List<TreeNode> children =
            new java.util.ArrayList<>();
}
~~~

When a parent holds a child and the child holds the parent, there is a cycle. That is **not a memory management bug**. If the entire tree no longer has a root owner, the collector can reclaim the whole graph.

If the parent remains alive and you want to detach a subtree, update `children` and `parent` according to the domain invariant so the subtree is no longer retained. The reason for doing so is **logical ownership and graph integrity**, not because Java does not know how to collect cycles.

## 24. Runnable Program: A Tree with Bidirectional Relationships

Create **`ParentChildCycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ParentChildCycleDemo {
    static final class Node {
        final String name;
        Node parent;
        final List<Node> children = new ArrayList<>();

        Node(String name) {
            this.name = name;
        }

        void add(Node child) {
            child.parent = this;
            children.add(child);
        }
    }

    public static void main(String[] args) {
        Node root = new Node("root");
        Node leaf = new Node("leaf");
        root.add(leaf);

        System.out.println("root has leaf=" +
                root.children.contains(leaf));
        System.out.println("leaf has root=" +
                (leaf.parent == root));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ParentChildCycleDemo.java
java ParentChildCycleDemo
~~~

Stdout:

~~~text
root has leaf=true
leaf has root=true
~~~

The parent↔child cycle is a normal pattern. Liveness depends on whether there are still root paths into the tree.

## 25. WeakReference: A Way to Express Non-Owning Relationships

`java.lang.ref.WeakReference<T>` does not hold its target strongly like an ordinary reference field.

Example:

~~~java
Node strong = new Node();
WeakReference<Node> weak = new WeakReference<>(strong);
~~~

When `strong` (and other applicable strong/soft paths) are gone:
- the referent can become weakly reachable;
- the collector can clear weak references to the referent;
- `weak.get()` **may** return the object before it is cleared, or null after it is cleared;
- when it is cleared is not a guarantee based on the number of Java lines or a fixed duration.

The accurate statement is that **a weak reference does not by itself prevent GC of a target that is only weakly reachable**, not “weak.get() immediately becomes null after strong=null”.

## 26. Runnable Program: WeakReference with Stable Stdout

Create **`WeakReferenceDemo.java`**:

~~~java
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    static final class Node {
        final String name;

        Node(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        Node strong = new Node("A");
        WeakReference<Node> weak = new WeakReference<>(strong);

        System.out.println("same while held=" +
                (weak.get() == strong));

        strong = null;
        System.out.println("strong variable cleared");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 WeakReferenceDemo.java
java WeakReferenceDemo
~~~

Stdout:

~~~text
same while held=true
strong variable cleared
~~~

After `strong=null`, the program **intentionally does not print `weak.get()==null`**, because the result is not guaranteed. The JVM/JIT can also optimize the liveness of local variables; an assignment in source code is not an instruction to immediately free memory.

## 27. A Weak Edge and a Strong Cycle Can Coexist

~~~text
ROOT ─► WeakReference ──weak──► A ──strong──► B
                               ▲             │
                               └─────────────┘
~~~

If no root has a **strong path** to A/B, the weak edge from the root to A does not start a strong tracing path that retains the cycle. The cycle A↔B can be collected.

If ROOT2→B exists via a strong reference, B and A become reachable again.

**Note:** The Java Reference API also includes SoftReference, PhantomReference, ReferenceQueue, and special rules; for basic questions about strong reference cycles, you should not mix them up with strong GC roots and draw wrong conclusions.

## 28. WeakHashMap Does Not Cure All Memory Retention

`WeakHashMap<K,V>` stores **weak keys**. If a key is no longer strongly held elsewhere and the collector processes it, the entry can disappear from the map.

However, consider this graph:

~~~text
WeakHashMap ──strong──► Value ──strong──► Key
       │                                  ▲
       └────────────weak──────────────────┘
~~~

Value has a strong path from the map, and value in turn points strongly to Key. That can keep Key strongly reachable even though the map uses a weak key. Therefore, **WeakHashMap does not guarantee automatic removal of every entry when the application “no longer uses the key” in a logical sense**.

Nor should you infer that entries must disappear at an exact point in time or that WeakHashMap can replace a bounded cache/eviction policy.

## 29. Runnable Program: WeakHashMap While the Key Is Still Strongly Referenced

Create **`WeakMapDemo.java`**:

~~~java
import java.util.Map;
import java.util.WeakHashMap;

public class WeakMapDemo {
    static final class Key {
        final String id;

        Key(String id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Map<Key, String> map = new WeakHashMap<>();
        Key key = new Key("A");
        map.put(key, "value");

        System.out.println("contains=" + map.containsKey(key));
        System.out.println("value=" + map.get(key));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 WeakMapDemo.java
java WeakMapDemo
~~~

Stdout:

~~~text
contains=true
value=value
~~~

Key is still strongly held by the local reference `key` while in use; this example does not guess when the JVM will collect WeakHashMap entries after removing the root.

## 30. ReferenceQueue Does Not Guarantee GC Runs on a Test Schedule

`ReferenceQueue<T>` allows certain reference objects to be enqueued according to Java Reference processing rules. It is useful for certain cleanup/cache mechanisms, but it does not let an application guarantee:

- that the collector must run after X milliseconds;
- that `WeakReference.get()` must be null immediately after `System.gc()`;
- that every reference must be enqueued before main finishes;
- that external resources will be closed at the desired time.

In addition, proactively calling `Reference.clear()` is not proof that the JVM just reclaimed the target.

If you only want to demonstrate why cycles are handled by GC, a reachability graph and marking algorithm are more reliable than a non-deterministic ReferenceQueue test.

## 31. `System.gc()` Is Only a Request, Not a Command That Forces a Result

Do not write a test like the following and conclude “the JVM is definitely wrong” if weak.get() is still non-null:

~~~java
a = null;
b = null;
System.gc();
// Not guaranteed that weak.get() == null immediately.
~~~

`System.gc()` is a request to attempt garbage collection; there is no language guarantee that every unreachable object will be reclaimed, cleared/enqueued, or reflected in heap metrics at the next moment. The JVM may have flags/policies that affect this request.

Therefore:
- **Do not assert a GC timing point** in unit tests.
- **Do not use GC print logs to claim that a specific object is definitely dead**, unless there is proper evidence.
- **Do not use System.gc() frequently as a remedy for leaks**.
- If you want to measure retention, use heap analysis, allocation profiling, and methodical paths-to-roots.

## 32. Avoid Using `finalize()` to Prove a Cycle Is Dead

Finalization has been deprecated, and Java is moving toward removing this mechanism. Overriding `finalize()` to print “object reclaimed” has many problems:
- execution timing is not guaranteed;
- it may not run before the program terminates;
- it can cause object resurrection;
- it introduces overhead as well as security/reliability risks;
- it does not purely describe actual reclaim timing.

With Java 17+, **do not write finalizer-based GC demonstrations** just to prove that object cycles are collected. Express eligibility using root reachability.

## 33. Garbage Collection Does Not Replace Closing Resources

An object may hold a file handle, socket, JDBC resource, or native memory. GC-managed heap memory and external resource lifecycles are **different**.

If a Session holds a reference cycle with a callback, that cycle becoming unreachable **is not a guarantee** that the file/socket will be closed on time.

Solution:
- implement `AutoCloseable` when appropriate;
- use try-with-resources;
- define clear/close/unregister according to the lifecycle;
- do not rely on finalization or the collector schedule for business-critical cleanup.

### Runnable Program

Create **`ExplicitCloseDemo.java`**:

~~~java
public class ExplicitCloseDemo {
    static final class Session implements AutoCloseable {
        private boolean closed;

        Session() {
            System.out.println("open");
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            System.out.println("use");
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("close");
        }
    }

    public static void main(String[] args) {
        try (Session session = new Session()) {
            session.use();
        }
        System.out.println("done");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ExplicitCloseDemo.java
java ExplicitCloseDemo
~~~

Stdout:

~~~text
open
use
close
done
~~~

`close()` is called because of try-with-resources, not because the JVM GC decided to reclaim Session.

## 34. Process RAM Not Dropping Immediately Does Not Prove a Leak

After objects become unreachable and GC actually reclaims them, the JVM may still:
- retain committed heap memory for reuse;
- not immediately return most of the committed heap to the OS;
- allocate other native/metaspace/off-heap memory;
- continue allocating objects continuously during the workload.

Therefore, Task Manager or RSS not dropping immediately after `CACHE.clear()` **does not prove** that “circular references prevent collection”.

When investigating memory:
1. measure used heap with appropriate tools;
2. analyze retained objects;
3. inspect root paths;
4. distinguish between committed heap, used heap, and RSS;
5. observe trends across multiple GC cycles/steady workload.

## 35. Investigating a Heap Dump: Finding Paths to GC Roots

When you suspect an object graph is living too long:
- capture a heap dump with appropriate access permissions;
- use a heap analysis tool that supports Java 17;
- select the object/subgraph;
- inspect **path to GC roots** or **dominator tree/retained size**;
- identify the owner that has a strong path to the subgraph;
- fix the lifecycle, such as clearing the cache, unregistering listeners, or removing the ThreadLocal;
- measure again after the change.

Example:

~~~text
GC root
  └── static EventBus.listeners
       └── Callback
            └── Screen
                 └── Model A
                      └── Model B
                           └── Model A
~~~

The issue is usually that **EventBus.listeners retains Callback**, not that Model A/B have a cycle.

Heap dumps may contain sensitive data such as passwords/tokens. Keep them secure, restrict sharing, and do not carelessly store them in logs or public artifacts.

## 36. Properly Distinguishing Which Objects Should Be Kept by Roots

Not every retained object is a leak:
- An active session needs to keep state.
- A graph model opened by the user needs to remain alive.
- A static immutable constant may be kept for the lifetime of the process.
- A cache with clear eviction and a size budget may be by design.

A logical memory leak occurs when **retention extends beyond what is needed**. Evaluate it using ownership and the lifecycle contract, not merely by seeing references or cycles.

An object graph A↔B kept by a root is normal if the application is still using it; it is abnormal when the root owner has finished its job but has not released it.

## 37. Should You Proactively Break the A.next/B.next Edges?

For a cycle that **is no longer reachable from roots**, there is no need to traverse into the cycle to set next=null for GC purposes.

For a graph that **still has a live owner** when you want to detach a branch:
- remove the edge from the owner to the branch, or
- update bidirectional links so that the domain invariant holds,
- clear collection entries that are no longer needed.

For example, in a doubly linked list where root→head still exists, when removing a node in the middle of the list you must update the prev/next links so the logical structure remains valid; this is not “fixing a GC that does not understand cycles”.

Principle: **find the retaining edge from the owner into the object graph** instead of breaking the entire cycle without understanding ownership.

## 38. Scenario Analysis Table

| Case | Reachability conclusion |
| --- | --- |
| A↔B, no GC root path | Can become garbage |
| static root→A↔B | A/B reachable |
| root→B and B→A | A/B reachable |
| Root1→A, Root2→B, remove Root1 | Still reachable from Root2 |
| A→A with no root | Self-loop does not prevent GC |
| global List holds A, A↔B | List retains the entire cycle |
| listener registry holds lambda capturing Screen | Screen retained via registry |
| long-lived ThreadLocal holds cycle | Cycle retained via ThreadLocal path |
| WeakReference is the only path to cycle | Does not create a strong root path |
| WeakHashMap value strongly holds key | Key may remain strongly reachable |
| Method returns after creating cycle, no escape | Cycle can become unreachable |
| Resource object unreachable | Does not guarantee external resource closes on time |

## 39. Common Misconceptions

**“There is still a reference, so it will never be GC'd.”** Wrong: references from unreachable objects do not themselves become GC roots.

**“A 2-object cycle requires setting next=null on both.”** Unnecessary if the entire cycle is already unreachable.

**“Having a cycle means a memory leak.”** Incorrect; bidirectional structures are normal.

**“Java only uses reference counting.”** Incorrect for common JVM tracing collectors.

**“Assigning null and calling System.gc() guarantees weak.get()==null.”** Not guaranteed by Java.

**“Leaving scope means the heap must drop immediately.”** There is no timing guarantee; liveness and collection are different.

**“Checking that one variable is null is enough to know the graph has no root.”** There may still be a cache, listener, thread, JNI, or another static owner.

**“WeakHashMap automatically eliminates every leak.”** Weak keys are not enough if values/the reference graph still hold keys or the owner still needs eviction logic.

**“Once GC finishes, the socket/file closes automatically.”** Use explicit close.

**“RSS not dropping means the collector is not freeing cycles.”** Used heap/committed heap/RSS are different; investigate retention with proper tools.

## 40. Exercise 1 — A↔B with No Root

Two objects A/B point to each other, with no root path to them at all.

**Answer:** Both A/B are unreachable under the tracing model; internal references do not prevent them from becoming eligible for collection.

## 41. Exercise 2 — A Root Holding One Node

ROOT→A, A→B, B→A.

**Answer:** Both A and B are reachable. Only a single root path into the cycle is needed.

## 42. Exercise 3 — Two Roots

ROOT1→A and ROOT2→B in the cycle A↔B. Remove ROOT1→A.

**Answer:** Not enough; ROOT2→B→A still keeps the entire cycle alive.

## 43. Exercise 4 — Self-Loop

Object A.next=A; the sole local variable leaves scope, and no other object holds A.

**Answer:** A self-loop is not a root. A can become garbage; there is no requirement to break the self-reference manually.

## 44. Exercise 5 — Reference Counting

Why might a pure reference counter fail to free A↔B?

**Answer:** After losing external refs, each of A/B still has an incoming edge from the other object; their counts have not reached 0. Tracing GC solves this through root reachability.

## 45. Exercise 6 — Static Cache

A static Map holds A; A↔B. Once the application no longer needs A/B, what should be used?

**Answer:** Remove/evict the entry holding A according to the cache policy; if there is no other root, the entire cycle can be collected. You do not have to break every A/B edge.

## 46. Exercise 7 — Listener

A static List<Runnable> holds a callback that captures a Screen; Screen holds a model containing a cycle.

**Answer:** The registry is the root owner retaining Screen/model. Unregister the callback according to the lifecycle.

## 47. Exercise 8 — ThreadLocal

A pooled thread still retains a ThreadLocal value from a completed request.

**Answer:** Use `try/finally` with `ThreadLocal.remove()`; do not wait for GC to reclaim data that is still reachable from the thread.

## 48. Exercise 9 — WeakReference

The strong path to A is gone, while a WeakReference<A> still exists. Must weak.get() become null immediately?

**Answer:** No. It is not a strong root path, but clearing/reclamation happens depending on collector timing.

## 49. Exercise 10 — WeakHashMap

An entry's value holds a strong reference to the key itself.

**Answer:** The weak key is not automatically released; the path map→value→key can keep the key reachable.

## 50. Exercise 11 — Directed Edge

ROOT→B; A→B; no B→A, and no other root→A.

**Answer:** B is reachable; A is not inferred to be reachable from B because edges are directed.

## 51. Exercise 12 — Parent-Child Cycle

The root of a tree is no longer referenced, but every child.parent points back to its parent.

**Answer:** If there is no remaining GC root path, the entire tree can be collected. Back-references do not prevent tracing GC.

## 52. Exercise 13 — System.gc

A program calls System.gc() after creating A↔B and sees that the WeakReference has not been cleared yet.

**Answer:** That does not prove a cycle leak; System.gc() does not promise that GC finishes at the moment the test expects.

## 53. Exercise 14 — Resource Cleanup

An object owning a socket is in a cycle, and later becomes unreachable. Should you wait for GC to close the socket?

**Answer:** No. Use explicit `close()` or try-with-resources according to the lifecycle.

## 54. Exercise 15 — Task Manager

After clearing the listener registry, the process RSS does not drop immediately.

**Answer:** Not enough evidence of a leak. The JVM may retain committed heap; inspect retained references and heap metrics properly.

## 55. Exercise 16 — Reading Heap Paths

A heap dump shows static cache→EventListener→Screen→A↔B.

**Answer:** Investigate the cache/listener ownership path and cleanup timing. The A/B cycle is merely part of the retained graph, not a cause that creates a root by itself.

## 56. Exercise 17 — The Mark Model

Roots are {A}; A→B→C→A; D→E→D. What is in the mark set?

**Answer:** A, B, C. The D/E cycle is unreachable from A even though the two nodes point to each other.

## 57. Exercise 18 — A Cycle and a Weak Strong Path?

ROOT→WeakReference→A↔B and there are no other strong/soft paths to A/B.

**Answer:** The weak edge does not become a strong path into the cycle. A/B can be handled by the collector under weak reachability rules.

## 58. Exercise 19 — Distinguishing GC and Business Lifecycle

A↔B is actively used by a service; you want to shut down the service and release its resources.

**Answer:** Perform close/cancel/unsubscribe and release owner references according to the API; GC can subsequently reclaim unreachable heap objects. Do not rely on the collector to perform business shutdown.

## 59. Workflow for Analyzing a Suspected Leaking Cycle

1. **Draw the graph.** List object nodes and reference directions.
2. **Mark the roots.** Static field? Active thread? Cache/listener? JNI?
3. **Traverse strong edges from roots.** Do not traverse backward arbitrarily.
4. **Determine the reachable object set.** Is there a path into the cycle?
5. **Distinguish what must be kept from what need not be kept.** A reachable object is not necessarily a leak.
6. **Find owner paths that extend past their lifecycle.** Cache entries, listeners, ThreadLocal, queues.
7. **Cut the appropriate owner path.** Remove/unregister/clear/detach.
8. **You do not have to break the entire cycle.** If unreachable, the collector can handle it.
9. **Close external resources explicitly.** Do not wait for GC.
10. **Measure with a profiler if needed.** Retained heap/paths to roots, not just RSS.
11. **Do not assert GC timing.** Avoid nondeterministic weak-reference tests.
12. **Test ownership cleanup.** Prove that the cache/registry no longer retains entries according to the application contract.

## 60. End-of-Lesson Checklist

- [ ] I know that a reference cycle does not generate a GC root on its own.
- [ ] I can distinguish between “has reference” and “root reachable”.
- [ ] I understand that strong-reference paths determine whether a cycle remains kept alive.
- [ ] I can draw A↔B and find root paths to A/B.
- [ ] I know that multiple root paths must be considered at the same time.
- [ ] I know that when the root path into a cycle is removed, the entire cycle can become garbage.
- [ ] I understand that tracing GC uses a visited/marked set to avoid infinite loops.
- [ ] I know that pure reference counting can get stuck on cycles.
- [ ] I do not generalize that to all reference counting algorithms.
- [ ] I distinguish between eligible for GC and actual reclamation.
- [ ] I do not predict that GC runs immediately when a method returns.
- [ ] I do not confuse a null assignment with free/destroy.
- [ ] I know that fields/static collections/listeners/ThreadLocal can hold an owner path.
- [ ] I know that GC does not delete objects that are still reachable even if business logic no longer needs them.
- [ ] I know that a weak reference does not hold its target strongly.
- [ ] I do not depend on when weak.get() returns null.
- [ ] I know that WeakHashMap may not remove an entry if the value holds a reference back to the key.
- [ ] I do not use finalize to verify GC.
- [ ] I do not treat System.gc() as a command that guarantees a result.
- [ ] I know that try-with-resources is for resources that need to be closed.
- [ ] I distinguish between heap used, committed memory, and RSS.
- [ ] I know how to find the path to GC roots in a heap analyzer.
- [ ] I distinguish between a runnable graph model and measuring actual JVM GC.
- [ ] I know that edge direction determines reachability.
- [ ] I understand that parent-child/doubly linked structures having cycles is normal.
- [ ] I can explain memory retention without wrongly blaming reference cycles.

**Conclusion:** **A circular reference A↔B does not by itself prevent Java GC from reclaiming A/B**, because tracing collection finds live objects by traversing **from GC roots along retaining edges**. If there is no remaining strong path into the cycle, the internals of the cycle do not help the objects mark themselves reachable. If the cycle remains in the retained heap, look for an owner path from static caches, threads, listeners, ThreadLocal, or other roots. The right approach is **managing ownership and lifecycles**, not breaking reference cycles just to “force Java to collect garbage”.
