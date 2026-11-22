# Cyclic References and Object Lifetimes in Java

## Learning Objectives

After this lesson, you will be able to:

- Describe **strong references**, **object graphs**, and the phenomenon of two or more objects having **cyclic references**.
- Distinguish **reachable objects** from roots (*GC roots*) from **unreachable objects**; explain why a reference cycle **does not by itself cause a memory leak** in Java.
- Read diagrams and programs that create an `A → B → A` cycle, longer cycles, and unidirectional/bidirectional links; distinguish a cycle in a graph from a program loop.
- Understand the lifecycle: object creation, constructor, state mutations, links/references, reachability, **eligibility** for garbage collection, memory reclamation, and what is not guaranteed about timing.
- Identify memory leak scenarios caused by **references held too long** from static collections, observers/listeners, caches, `ThreadLocal`, and objects holding callbacks or inner-class instances.
- Distinguish the lifetime of a Java object in the heap from **the usage/closing time of resources** such as files, sockets, and connections; apply `AutoCloseable` and `try-with-resources`.
- Explain the reference classes in `java.lang.ref`: `WeakReference`, `SoftReference`, `PhantomReference`, and `ReferenceQueue` accurately in essence, without making uncertain GC predictions.
- Design bidirectional link updates, avoid non-terminating recursive `toString()`/`equals()`/traversal on graphs with cycles, and use an identity-based visited set when appropriate.
- Understand `final` references, `null`, ownership, UML composition, inner-class reference cycles, the limitations of `System.gc()`, and concurrency.
- Independently compile and run Java 17+ examples with deterministic stdout.

## 1. An Object Can Hold a Reference to Another Object

In Java, an instance field of a reference type normally holds a **reference value**, rather than “embedding an entire object” in the way a source code reader needs to manipulate like a C struct.

~~~java
class Node {
    String name;
    Node next;

    Node(String name) {
        this.name = name;
    }
}
~~~

This is an illustrative declaration. Each `new Node("A")` creates a `Node` object. The `next` field has type `Node` and is initially `null` if not yet assigned. When you write `a.next = b`, the program makes `a`'s field hold a reference to the object that `b` points to.

Two links can be created:

~~~java
Node a = new Node("A");
Node b = new Node("B");
a.next = b;
b.next = a;
~~~

The lines above need to be placed in an appropriate method or initializer. They create **two objects**, not infinitely many objects:

~~~text
local a --> [Node A] ---next---> [Node B]
             ^                     |
             |---------next--------|
local b --------------------------> [Node B]
~~~

The two `next` fields form a **cycle in the object graph**: following the links, you can go from A to B and then from B back to A. This is not an infinite `while` loop; the program only assigns a reference twice.

### 1.1. Avoid Confusing a Cycle with Self-Reference

An object can also reference **itself**:

~~~java
Node a = new Node("A");
a.next = a;
~~~

This is a single-vertex cycle `A → A`, which is valid for the Node type above. Java does not forbid that kind of relationship; the question is whether the **business semantics** allow it or not.

If you are building a linked list with a “no cycles” invariant, you must actively check for it. If the model is a social network graph, the same kind of reference cycle may be valid.

## 2. Runnable Program: Creating and Breaking a Reference Cycle

Save **`CyclicNodeDemo.java`**:

~~~java
public class CyclicNodeDemo {
    static final class Node {
        private final String name;
        private Node next;

        Node(String name) {
            this.name = name;
        }

        void linkTo(Node target) {
            this.next = target;
        }

        String name() {
            return name;
        }

        String nextName() {
            return next == null ? "none" : next.name;
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.linkTo(b);
        b.linkTo(a);

        System.out.println("A -> " + a.nextName());
        System.out.println("B -> " + b.nextName());
        System.out.println("cycle=" + (a == b.next));

        b.linkTo(null);
        System.out.println("after unlink B -> " + b.nextName());
        System.out.println("A -> " + a.nextName());
    }
}
~~~

Compile/run:

~~~bash
javac CyclicNodeDemo.java
java CyclicNodeDemo
~~~

Exact stdout:

~~~text
A -> B
B -> A
cycle=true
after unlink B -> none
A -> B
~~~

**Explanation:**

1. `a` and `b` are two local variables pointing to two Node objects.
2. `a.linkTo(b)` assigns a reference to B into `A.next`.
3. `b.linkTo(a)` assigns a reference to A into `B.next`, completing the cycle.
4. `a == b.next` is a **reference identity** comparison: it is true because `b.next` points to the very same object A.
5. `b.linkTo(null)` breaks the **B → A link**, but does not automatically delete A or B. The local variables `a` and `b` still hold references; `A.next` still points to B.
6. No line in the program says that the garbage collector has reclaimed or will immediately reclaim objects. The output only reflects the **link structure observable through the API**.

**Key point:** `null` is the value meaning “references no object”, but setting a field to null only removes **one path**. An object may still be referenced in many other places.

## 3. GC Is Not Simple Reference Counting

A mistaken intuition:

> A points to B and B points to A, so each object has one holder; their memory cannot be reclaimed.

This is reasoning based on **pure reference counting**. Java garbage collection is described in terms of **reachability** in the object graph; the collector can collect an entire group of objects forming a cycle if they are **no longer reachable from GC roots**.

Ask a more accurate question:

> Does a path of **strong references** exist from an appropriate GC root to this object?

If so, the object belongs to the strongly reachable group under the standard model. If an entire cycle no longer has such a path, the existence of links inside the cycle **does not by itself keep them alive forever**.

### 3.1. What Are GC Roots?

At a conceptual level, the sources of reachability include:

- References determined by the JVM to still be live/in use in execution contexts, such as certain local variables and stack frames of **active threads**.
- Static fields of runtime classes still associated with the root set according to the JVM and class loader mechanisms.
- References managed by JNI/native/runtime according to their rules.
- Other runtime references that the JVM treats as GC roots or that are involved in the reachability marking process.

This is a model for reasoning, **not a list guaranteeing that every JVM always uses the exact same algorithm or root representation**.

**Subtle note:** the fact that a local variable is still in scope in source code does not guarantee that the reference must always be considered live until the closing `}` brace. The JIT/VM can determine earlier that an object is no longer used. Conversely, you cannot look at a line `x = null` and claim that the collector has run.

### 3.2. Three Different Graphs

**Graph I — path from a root:**

~~~text
GC root (for example, a field of a still-live registry)
  |
  v
[A] --> [B]
 ^       |
 |-------|

Conclusion: A and B are still reachable through the root and strong references.
~~~

**Graph II — cycle detached from roots:**

~~~text
[A] --> [B]
 ^       |
 |-------|

There is no longer any strong-reference path from GC roots to A/B.

Conclusion: the cycle does not by itself prevent A/B from becoming
objects eligible to be reclaimed by GC.
~~~

**Graph III — only one retaining path:**

~~~text
root --> [B] --> [A] --> [B]
~~~

As long as the root still points to B, both B and A can still be strongly reachable. Breaking `A.next` might not yet make A eligible for collection because B may still point to A.

## 4. Reachable, Unreachable, Eligible, and Collected Are Not Synonymous

Terms that are easily confused:

| State | Meaning |
| --- | --- |
| **Strongly reachable** | A strong-reference path still exists from an appropriate root to the object |
| **No longer strongly reachable** | That path no longer exists; there may be effects from soft/weak/phantom references depending on the case |
| **Eligible for GC** | Can be collected by the system according to reachability/reference processing rules |
| **Collected/reclaimed** | The JVM/GC has actually performed processing and may reclaim the memory |
| **Resource closed** | File/socket/connection... has been closed via an API contract |
| **Variable out of scope** | A lexical phenomenon; not a GC event with a guaranteed timestamp |

**An object no longer being strongly reached by the application does not mean it is “immediately destroyed”.** The JVM has the right to choose when GC runs and apply different optimizations. A program may even terminate with some unreachable objects not yet processed in a way you can observe.

### 4.1. GC Is Not a Deterministic Destructor

Java does not have destructor semantics that are guaranteed to be invoked as soon as a variable goes out of scope like some C++ RAII models.

~~~java
void process() {
    Object temp = new Object();
    // Use temp ...
}
~~~

When `process()` finishes, **no callback is guaranteed by Java to run immediately on the object** simply because the local variable disappears from scope. The object may become unreachable; the collection time is indeterminate.

Therefore, do not rely on GC to guarantee that “by the end of the method the file is closed”, “as soon as null is assigned the database connection returns to the pool”, or “before the next line memory must be freed”.

## 5. Program About a Root Retaining a Cycle — Without Guessing GC

Save **`RootedCycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RootedCycleDemo {
    static final class Node {
        final String name;
        Node next;

        Node(String name) {
            this.name = name;
        }

        String nextName() {
            return next == null ? "none" : next.name;
        }
    }

    private static final List<Node> REGISTRY = new ArrayList<>();

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        a.next = b;
        b.next = a;

        REGISTRY.add(a);

        System.out.println("registry size=" + REGISTRY.size());
        System.out.println("A -> " + REGISTRY.get(0).nextName());
        System.out.println("B -> " + b.nextName());

        REGISTRY.clear();
        System.out.println("registry after clear=" + REGISTRY.size());

        // From here on, do not draw conclusions about GC timing.
    }
}
~~~

Run:

~~~bash
javac RootedCycleDemo.java
java RootedCycleDemo
~~~

Output:

~~~text
registry size=1
A -> B
B -> A
registry after clear=0
~~~

**Analysis:**

- `REGISTRY` is a static list initialized together with the class. When the list contains `a`, it provides a **strong retaining path** to A, and then from A to B.
- `REGISTRY.clear()` removes the references held in the list, eliminating the retaining path **through REGISTRY**.
- The local variables `a` and `b` still appear in the method; although the JVM can optimize liveness, the example **does not claim** that immediately after `clear()` the two objects are already unreachable or collected.
- To determine that a graph is truly no longer reachable, you must examine **every retaining path**, not just a single collection.
- The purpose of the program is to demonstrate that the registry holds references according to API semantics and clearing entries causes the registry to no longer hold them, **not a test of GC timing**.

### 5.1. Why Not Add `System.gc()` and Print “destroyed”?

`System.gc()` is only a **request/hint** to the VM, not a promise to “collect all unreachable objects right now”. Java does not guarantee that the program will print a specific GC event after that call. Using `Thread.sleep(...)` and guessing also does not make the behavior deterministic.

In lessons with exact stdout, we print the **observable state of references/collections**, without inferring collector timing.

## 6. Cyclic References Are Not by Themselves a Memory Leak

A **memory leak in a Java application** is generally understood as a situation where objects are **no longer needed from a business perspective** yet are still unintentionally **kept reachable**, leading to prolonged/growing memory usage. Java GC can work properly while the application still leaks due to retention.

Cases:

- A `static List<Object> ALL_USERS` accumulates references indefinitely without removing entries after a session ends.
- An event bus/listener registry retains callbacks from subscribers that are no longer needed.
- A cache without limits/eviction.
- A thread pool keeps `ThreadLocal` values across many requests because the code forgets `remove()`.
- A long-lived owner holds an inner-class instance that holds the enclosing object, pulling along a large object graph.
- A queue/task registry holds callbacks or closures longer than their intended usage period.

**A reference cycle is only a concern for memory retention if a strong-reference path exists from a long-lived root/owner to that cycle.** Not every `A.next=B; B.next=A` pair leaks.

### 6.1. Distinguishing a Leak from a Useful Cache

A cache holding objects for a long time is not necessarily a bug: that may be intentional behavior. However, without limits on size, lifetime, or an eviction mechanism, a cache can easily retain too many objects.

Evaluation must be based on **ownership and business purpose**, not merely the number of references or the fact that memory has not dropped immediately in a profiler.

## 7. Static Registry: Simulating a Retained Graph and Cleanup

Save **`RegistryLifecycleDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RegistryLifecycleDemo {
    static final class Session {
        private final String id;

        Session(String id) {
            this.id = id;
        }

        String id() {
            return id;
        }
    }

    static final class Registry {
        private static final Map<String, Session> SESSIONS =
                new HashMap<>();

        static void register(Session session) {
            SESSIONS.put(session.id(), session);
        }

        static void unregister(String id) {
            SESSIONS.remove(id);
        }

        static int size() {
            return SESSIONS.size();
        }
    }

    public static void main(String[] args) {
        Session session = new Session("S-1");
        Registry.register(session);

        System.out.println("registered=" + Registry.size());

        session = null;
        System.out.println("still registered=" + Registry.size());

        Registry.unregister("S-1");
        System.out.println("after unregister=" + Registry.size());
    }
}
~~~

Compile/run:

~~~bash
javac RegistryLifecycleDemo.java
java RegistryLifecycleDemo
~~~

Output:

~~~text
registered=1
still registered=1
after unregister=0
~~~

**Explanation:**

- `Registry.SESSIONS` is a class-level map that holds strong references to `Session` values.
- Assigning `session = null` only clears the reference in **a single local variable**; the map still retains the session via the `"S-1"` entry.
- `unregister("S-1")` removes the entry; the map no longer retains that session.
- The program does not verify that the session has been reclaimed by the collector; it verifies that a **strong retaining path** has been cleared.
- In a real session system, the policy may be based on timeout/TTL, logout, bounded size, and cleanup on failure.

## 8. Listener/Callback: Memory Leak from Forgetting to Unsubscribe

In the observer model, a long-lived object (an event bus) holds references to listeners. A listener can be:

- A direct listener object.
- A lambda/method reference.
- An inner-class instance holding the enclosing object.
- A callback closure referencing large state.

If a subscriber is “no longer in use” yet the event bus **still holds a callback** referencing the subscriber, the subscriber and the objects reachable through it can continue to live for a long time.

### 8.1. Managing Subscriptions Yourself with `AutoCloseable`

Save **`ListenerLifecycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class ListenerLifecycleDemo {
    static final class EventBus {
        private final List<Consumer<String>> listeners =
                new ArrayList<>();

        AutoCloseable subscribe(Consumer<String> listener) {
            listeners.add(listener);
            return () -> listeners.remove(listener);
        }

        void publish(String event) {
            for (Consumer<String> listener : listeners) {
                listener.accept(event);
            }
        }

        int listenerCount() {
            return listeners.size();
        }
    }

    static final class Subscriber {
        private final String name;

        Subscriber(String name) {
            this.name = name;
        }

        Consumer<String> callback() {
            return event -> System.out.println(name + " heard " + event);
        }
    }

    public static void main(String[] args) throws Exception {
        EventBus bus = new EventBus();
        Subscriber subscriber = new Subscriber("Lan");

        try (AutoCloseable subscription =
                     bus.subscribe(subscriber.callback())) {
            System.out.println("listeners=" + bus.listenerCount());
            bus.publish("hello");
        }

        System.out.println("after close=" + bus.listenerCount());
        bus.publish("again");
        System.out.println("finished");
    }
}
~~~

Commands:

~~~bash
javac ListenerLifecycleDemo.java
java ListenerLifecycleDemo
~~~

Output:

~~~text
listeners=1
Lan heard hello
after close=0
finished
~~~

**Reference path while subscribed:**

~~~text
root/owner -> EventBus
                |
                v
              listeners
                |
                v
          callback lambda
                |
                v
             Subscriber
                |
                v
              state
~~~

The lambda uses the instance field `name` in `Subscriber.callback()`, so the callback needs to retain access to the corresponding Subscriber instance. EventBus holds the listener strongly in the list. After `subscription.close()`, the lambda is removed from the list, breaking a retaining path from EventBus.

**Limitation:** the example runs on a single thread and does not synchronize the list for publishing events from multiple threads. If subscribe/unsubscribe/publish operations are concurrent, design thread safety separately. In addition, a subscription object may still temporarily retain the callback while the scope is alive; cleanup in the bus does not mean all references from everywhere disappear immediately.

### 8.2. Why Is `try-with-resources` Useful Here?

A subscription also has a **lifecycle that needs explicit closing**. `try-with-resources` calls `close()` upon exiting the block according to its contract, even if the code inside the block throws an exception (following Java's exception/suppression mechanism).

Nothing forces a listener to wait for GC to cancel; an API that returns an `AutoCloseable` handle lets the code control **when unsubscription takes place**.

## 9. `ThreadLocal` and Long-Lived Threads

`ThreadLocal<T>` gives each thread an associated value according to the API. In environments using thread pools, a thread can live across very many requests. If code executes:

~~~java
THREAD_CONTEXT.set(largeRequestContext);
~~~

without cleanup, data from a previous request can be retained too long or logically misused on that same thread.

A `ThreadLocal` instance is not a promise that “the value will automatically disappear when the request ends”. Cleanup is needed at the lifecycle level of the request/job.

### 9.1. An Explicit Cleanup Program

Save **`ThreadLocalCleanupDemo.java`**:

~~~java
public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> USER =
            new ThreadLocal<>();

    static void handle(String user) {
        USER.set(user);
        try {
            System.out.println("handling=" + USER.get());
        } finally {
            USER.remove();
        }
    }

    public static void main(String[] args) {
        handle("Lan");
        System.out.println("after first=" + USER.get());

        handle("Minh");
        System.out.println("after second=" + USER.get());
    }
}
~~~

Compile/run:

~~~bash
javac ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
~~~

Output:

~~~text
handling=Lan
after first=null
handling=Minh
after second=null
~~~

**Why use `finally`?**

- Whether the work inside `try` completes normally or throws an exception, `finally` still performs cleanup according to Java rules.
- `ThreadLocal.remove()` removes the current thread's value for that ThreadLocal, avoiding accidentally reusing a previous request's value in a reused thread.
- The demo uses only the main thread so stdout is consistent; the real-world risk is higher in long-lived thread pools.
- Do not infer that `remove()` immediately reclaims the `String` object or the entire graph: other references may still exist; GC has its own timing.

### 9.2. Do Not Confuse ThreadLocal with General Thread Safety

ThreadLocal keeps a per-thread value for a ThreadLocal key, but if the values across threads all point to a **shared mutable object**, they can still race when mutating that object.

In addition, the JVM's management of weak references to ThreadLocal keys does not replace designing cleanup yourself; stale values can still remain alive in some situations. A simple rule for request-scoped context is **set → try/finally → remove**.

## 10. Weak References: Not Holding an Object Strongly

In `java.lang.ref`, **`WeakReference<T>`** is a way of holding a reference such that **the weak reference itself does not strongly retain the referent** like an ordinary strong reference.

A weakly reachable referent can be cleared/collected when the collector processes it according to weak reference rules. However:

- If there is **another strong reference** to the referent, the weak reference does not “force” the object to be reclaimed.
- `weakRef.get()` can return the referent or `null` depending on state and GC activity.
- You must not assume a weak reference will become null **immediately at a fixed line** after dropping a local reference.
- If you need to use the retrieved referent, hold a local strong reference while using it and handle `null`.

### 10.1. Deterministic Demo Not Relying on GC Timing

Save **`WeakReferenceBasicsDemo.java`**:

~~~java
import java.lang.ref.WeakReference;

public class WeakReferenceBasicsDemo {
    static final class Item {
        private final String name;

        Item(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Item strong = new Item("A");
        WeakReference<Item> weak = new WeakReference<>(strong);

        Item observed = weak.get();
        System.out.println("same object=" + (observed == strong));
        System.out.println("name=" + observed.name());

        strong = null;
        System.out.println("strong variable cleared");
        System.out.println("demo finished");
    }
}
~~~

Run:

~~~bash
javac WeakReferenceBasicsDemo.java
java WeakReferenceBasicsDemo
~~~

Output:

~~~text
same object=true
name=A
strong variable cleared
demo finished
~~~

At the moment of `observed = weak.get()`, the local `strong` variable is still used right afterward in the comparison, and the referent is still strongly held. Later, `strong = null` only clears one reference; the local `observed` may still be retaining the referent, depending on liveness analysis.

**We intentionally do not print `weak.get() == null` after `System.gc()`**, because it is impossible to write a single stdout that Java always guarantees for that GC run. Avoid tests that depend on “the collector must run within 100 ms”.

### 10.2. Weak References Do Not Replace Ownership

If the application **needs** object B to stay alive throughout the ongoing business operation, holding only a `WeakReference<B>` is an error-prone design: the referent can be collected when no other strong reference remains. Weak references are suitable for **discardable** information, specialized canonicalizing/maps, or policy-dependent caches, not as a replacement for a required dependency.

## 11. `WeakHashMap`: Weak Keys but Strong Values

`WeakHashMap<K,V>` is a special map whose **keys are held weakly** according to Java's mechanism. When a key is no longer strongly reachable outside the map under the applicable rules, the entry can be dropped during GC/housekeeping.

However:

- The value `V` is normally held **strongly** by the map.
- If the value **strongly references back to the key**, a retaining path for the key can appear through map → value → key. In that case, a weak-key map does not solve retention by itself.
- The decrease in the number of entries after collector processing has **no deterministic timing**. Do not use “assign key=null and then check `size()==0`” as a mandatory test.
- WeakHashMap is not thread-safe by default; synchronization or another alternative is needed when sharing across threads.
- The map still uses key contracts such as `equals`/`hashCode`; GC references and logical key equality are two separate concerns.

### 11.1. Example Without Assuming GC Has Run

Save **`WeakHashMapBasicsDemo.java`**:

~~~java
import java.util.Map;
import java.util.WeakHashMap;

public class WeakHashMapBasicsDemo {
    static final class Key {
        final int id;

        Key(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Map<Key, String> map = new WeakHashMap<>();
        Key key = new Key(1);

        map.put(key, "cached");
        System.out.println("value=" + map.get(key));
        System.out.println("contains key=" + map.containsKey(key));

        map.remove(key);
        System.out.println("after explicit remove=" + map.size());
    }
}
~~~

Run:

~~~bash
javac WeakHashMapBasicsDemo.java
java WeakHashMapBasicsDemo
~~~

Output:

~~~text
value=cached
contains key=true
after explicit remove=0
~~~

This is a demo of syntax, map semantics, and **explicit remove**; do not treat it as proof that GC has cleared a weak key. If you want to evaluate a real cache, you need to profile and inspect the retention policy rather than asserting collection timing.

## 12. Soft, Weak, Phantom, and Reference Queues

Overview table:

| Type | Core Meaning | Notes |
| --- | --- | --- |
| **Strong reference** | Normal reference relationship between locals/fields/array elements and an object | Can keep an object strongly reachable |
| **`SoftReference<T>`** | Soft reference; the VM has a reclamation policy based on pressure/rules | Does not guarantee timely cache eviction or meeting a specific memory limit |
| **`WeakReference<T>`** | Does not prevent GC from processing a referent that is only weakly reachable | `get()` can become null |
| **`PhantomReference<T>`** | Mechanism for tracking the post-reachability phase via a reference queue | `get()` always returns null; not used to “retrieve the object” |
| **`ReferenceQueue<T>`** | Receives references enqueued by the VM according to their corresponding lifecycle | Enqueuing depends on collector processing, not a deterministic clock |

**Soft references are not recommended as a general-purpose cache manager** when an application needs TTL, bounded memory, or exact eviction. A cache with explicit limits and measurements is usually better.

### 12.1. `PhantomReference.get()` Does Not Return the Referent

`PhantomReference` is not a “stronger weak reference” for reading an object about to be lost. It works together with `ReferenceQueue` to track lifecycle and perform cleanup under a careful architecture; `get()` is always null by the API.

Use this kind of reference only once you understand object lifetime, reference queues, and concurrency/cleanup conditions. For ordinary files/DB connections, **`AutoCloseable` + `try-with-resources`** is easier to get right and easier to test.

### 12.2. `Cleaner` Does Not Replace `close()`

Java provides `java.lang.ref.Cleaner` for certain fallback cleanup scenarios. However, cleanup depends on reachability and scheduling; there is no exact promise of when—or whether—the cleanup task will run before the JVM exits. Moreover, a cleaning action that accidentally holds a **strong reference to the registered object itself** can prevent the object from becoming eligible for collection.

When managing off-heap resources, prefer **explicit closing**, using Cleaner only when a fallback is truly needed and you understand the API constraints.

## 13. An Object's Lifetime Is Not a Resource's Lifetime

A Java object can **hold a handle** to a file/socket/database resource:

~~~text
Java object: FileReader/Socket/Connection
       |
       v
Operating system resource / connection pool / native handle
~~~

Garbage collection manages **the JVM memory of objects**; it **is not a contract for closing resources on time**. If you merely drop all references to a `Connection` and wait for GC, the application can exhaust the connection pool before the collector processes it.

Concepts to separate:

1. **Object still reachable:** a reference still retains the object.
2. **Object no longer needed:** the business operation is finished.
3. **Resource closed/released:** the proper cleanup API has been called.
4. **Object reclaimed by GC:** the JVM actually reclaims the object's memory region.

These events do not happen simultaneously according to a simple rule.

### 13.1. `try-with-resources` for Predictable Cleanup

Save **`ResourceLifecycleDemo.java`**:

~~~java
public class ResourceLifecycleDemo {
    static final class Resource implements AutoCloseable {
        private final String name;
        private boolean closed;

        Resource(String name) {
            this.name = name;
            System.out.println("open=" + name);
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("already closed");
            }
            System.out.println("use=" + name);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("close=" + name);
            }
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource("R1")) {
            resource.use();
            System.out.println("inside block");
        }

        System.out.println("after block");
    }
}
~~~

Run:

~~~bash
javac ResourceLifecycleDemo.java
java ResourceLifecycleDemo
~~~

Output:

~~~text
open=R1
use=R1
inside block
close=R1
after block
~~~

The timing of `close=R1` **does not depend on GC**: `try-with-resources` automatically invokes `close()` when exiting the block according to Java semantics. The `Resource` example simulates a resource itself; in practice, `close` may close a file, return a connection, cancel a subscription, or release a native handle.

### 13.2. Does a Reference Cycle Cause `close()` to Run Automatically?

No. An object A holding Resource B, B holding A back, and then both objects becoming unreachable **does not automatically trigger a `close()` call at the right business time**. You must define an owner/callback/try-with-resources to close the resource.

If two resources have an ordered closing dependency, build a lifecycle owner that closes them in the proper order and handles exceptions. GC reachability does not solve this dependency ordering.

## 14. Finalization Is a Legacy Mechanism That Should Not Be Relied Upon

In Java 17, finalization is **deprecated for removal** (according to Java platform documentation). Do not use `finalize()` as a new resource management solution.

Fundamental issues:

- An object becoming unreachable does not guarantee that the finalizer will run immediately or even at all before the program terminates.
- Finalization has security and performance risks, object resurrection, and unpredictable behavior.
- Cleanup ordering between objects with mutual references cannot be replaced by assuming “A's finalizer runs before B's”.
- Business code must close/clean up according to an explicit contract rather than waiting for finalization.

`Cleaner` or phantom references are specialized tools for fallback/resource management, but they **do not replace** an explicit lifecycle when guaranteed closing is required.

## 15. Object Resurrection and Scope of Knowledge

**Object resurrection** is the historical scenario where finalizer code or a special mechanism causes an object once at risk of collection to become reachable again. This illustrates why finalization makes it hard to reason about lifecycles.

For this lesson, we should not create examples that rely on `finalize()` or a GC clock. What to remember: **do not design an object graph under the assumption that “GC will call a callback so I can reattach the object”**. Expose lifecycles through methods/factories/repositories and control when an owner retains or drops a reference.

## 16. Traversing Graphs with Cycles: Avoiding Non-Terminating Recursion

When you write code to traverse an object graph:

~~~java
void visit(Node node) {
    visit(node.next);
}
~~~

if `next` leads back to an already-visited object, recursion may never reach a termination condition and will eventually cause a `StackOverflowError`. This is a **graph traversal algorithm bug**, not a garbage collection bug.

### 16.1. Why Is Identity Comparison Often Appropriate?

If the goal is “each **object instance** is visited only once”, store the **identities** already seen. Using an `IdentityHashMap` or an identity-based set is useful because two distinct objects can have `equals() == true` yet still be two separate nodes in the graph.

A `HashSet<Node>` normally uses `equals`/`hashCode`; if Node is a value-based record or has equality methods that recurse over neighbors, tracking “visited” may miss nodes with different identities or run into another recursion.

### 16.2. A Cycle-Safe DFS Program

Save **`CycleSafeTraversalDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public class CycleSafeTraversalDemo {
    static final class Node {
        final String name;
        final List<Node> links = new ArrayList<>();

        Node(String name) {
            this.name = name;
        }

        void connect(Node other) {
            links.add(other);
        }
    }

    static void walk(Node node, Set<Node> seen, List<String> names) {
        if (node == null || !seen.add(node)) {
            return;
        }

        names.add(node.name);
        for (Node next : node.links) {
            walk(next, seen, names);
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");

        a.connect(b);
        b.connect(c);
        c.connect(a);
        a.connect(c);

        Set<Node> seen = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        List<String> order = new ArrayList<>();

        walk(a, seen, order);

        System.out.println("visited=" + order);
        System.out.println("count=" + seen.size());
    }
}
~~~

Compile/run:

~~~bash
javac CycleSafeTraversalDemo.java
java CycleSafeTraversalDemo
~~~

Output:

~~~text
visited=[A, B, C]
count=3
~~~

Explanation:

1. `seen.add(node)` returns false if the same object identity has already been added.
2. When C points back to A, A is already in `seen`, so recursion stops on that branch.
3. The additional link A → C also does not cause C to be printed twice.
4. `names` preserves the visit order according to the order in which links were added in the example; `IdentityHashMap` is used only for membership, without relying on the map's iteration order.

**Limitation:** recursive DFS on a **very deep** graph can still overflow the call stack even when cycles are avoided. For very large data, consider iterative DFS/BFS using a stack/queue and resource limits.

## 17. `toString()`, `equals()`, and `hashCode()` with Bidirectional Links

A common mistake:

~~~java
class Person {
    Department department;

    public String toString() {
        return "Person{department=" + department + "}";
    }
}

class Department {
    Person leader;

    public String toString() {
        return "Department{leader=" + leader + "}";
    }
}
~~~

If `person.department = department` and `department.leader = person`, printing `person` can produce the call chain:

~~~text
Person.toString()
 -> Department.toString()
 -> Person.toString()
 -> Department.toString()
 -> ...
~~~

Eventually, a `StackOverflowError` can occur. The two declarations are **illustrative** code, not a runnable command intended to actively trigger a stack overflow.

Similarly, if you write `equals()` and `hashCode()` yourself by traversing endlessly deep through mutual references, it can cause recursion, poor performance, or an incorrect equality contract.

### 17.1. A Safer Way to Print

Instead of printing the entire object:

~~~java
@Override
public String toString() {
    return "Person{name=" + name
            + ",departmentId=" + department.id() + "}";
}
~~~

This is an illustrative snippet that needs proper fields/types and handling of a nullable department. The idea is to **print an identifier/summary of the related object**, rather than continuing to print every nested object without bound.

For complex object graphs/serialization, you can:

- Use a visited set by object identity.
- Limit the depth and the number of described nodes.
- Use DTOs that do not form cycles when returning from an API.
- Use the object references/IDs mechanism of an appropriate serialization framework, after verifying its contract.
- Define equality based on a **stable identity/domain key** instead of the entire cyclic graph.

**Not every class should override `equals` based on all reference fields**; entity identity and value equality are two different design choices.

## 18. Bidirectional Relationships: Link Consistency Differs from Graph Reachability

If `Employee.department` points to `QA` while `Engineering.employees` still contains the Employee, **the two sides of the association are out of sync**. Java does not automatically fix those fields/collections. A department transfer operation must update both ends according to the business invariant; if multiple threads or persistence are involved, appropriate synchronization/transactions are also needed.

~~~text
Consistent links (after transfer):
  Employee.department ───> QA
  QA.employees ──────────> Employee
  Engineering.employees: no longer contains Employee
~~~

**The reappearance of a reference cycle is normal:** Employee points to QA, and QA points back to Employee. This is not a memory leak **simply because** a cycle exists. For the purposes of this lesson, a different question is more important: **when the employee/usage context reaches the end of its lifecycle, does any GC root or static registry/listener/cache still hold a reference path to one side of the cycle?** If so, the entire graph can remain reachable. If not, the collector can reclaim the graph (without guaranteeing when).

The lesson **Bidirectional Relationships and Maintaining Consistency** provides a program for transferring links, checking both directions, and rollback/atomicity; here, use that same structure to distinguish **domain consistency** from **memory reachability and retention**.

## 19. Do Composition, Aggregation, and Ownership Differ from Reachability?

UML concepts:

- **Association:** two objects have a relationship.
- **Aggregation:** whole–part with loose ownership; the part can exist independently.
- **Composition:** whole–part with tighter lifecycle/ownership according to the domain.

These are **modeling commitments**, not Java commands that make GC reclaim the part as soon as the whole is no longer used.

Example:

~~~java
class Order {
    private final List<OrderLine> lines;
}
~~~

If Order holds the lines while another place still holds an `OrderLine` reference, the line objects can still be reachable after Order is no longer used. If database logic requires a cascade delete, that belongs to transactions/persistence and does **not** happen automatically just because the field belongs to Order.

### 19.1. Ownership Can Help Avoid Retention

A clear owner is usually responsible for:

- Registering and unregistering listeners.
- Adding and removing children/parts from a collection.
- Closing resources at the end of a use case.
- Bounding the cache.
- Clearing `ThreadLocal` after a request.
- Breaking references to contexts/sessions that are no longer needed.

Those actions **eliminate strong-reference paths** and release resources on time; GC still decides on its own when to reclaim memory.

## 20. A Non-Static Inner Class Can Retain Its Enclosing Object

In Java, a **non-static member inner class** is bound to an enclosing instance. An instance of the inner class can access the enclosing object's state via `Outer.this` in an appropriate context.

If a long-lived registry holds an inner-class instance, it can **indirectly retain the enclosing object** and the object graph held by the outer object.

### 20.1. Program Showing the Enclosing Instance Relationship

Save **`InnerClassReferenceDemo.java`**:

~~~java
public class InnerClassReferenceDemo {
    static final class Outer {
        private final String label;

        Outer(String label) {
            this.label = label;
        }

        class Inner {
            String describe() {
                return Outer.this.label;
            }
        }

        static class Nested {
            String describe() {
                return "static nested";
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer("A");
        Outer.Inner inner = outer.new Inner();
        Outer.Nested nested = new Outer.Nested();

        System.out.println("inner=" + inner.describe());
        System.out.println("nested=" + nested.describe());
    }
}
~~~

Run:

~~~bash
javac InnerClassReferenceDemo.java
java InnerClassReferenceDemo
~~~

Output:

~~~text
inner=A
nested=static nested
~~~

**Why does this relate to lifetime?**

- `inner` is bound to a specific `outer`; `Outer.this.label` reads the enclosing instance's field.
- If an object holding `inner` lives a long time, a retaining path to `outer` may still exist.
- A `static nested class` does not have a similar automatic enclosing instance reference; to use an outer object, an explicit reference must be passed.
- Do not infer that any class with the word “nested” automatically creates a cycle; a cycle appears only if reference paths actually point back to one another.
- The compiler/runtime has the right to organize implementation details; the important language semantics is the **enclosing instance relationship** of the inner object.

### 20.2. Listener as an Inner Class

A non-static inner listener registered with a global event bus can retain Outer longer than expected. If the listener only needs a small identifier, consider a static nested class/standalone object that receives minimal dependencies and has an unsubscribe handle.

## 21. Does a `final` Reference Prevent a Memory Leak?

No. Consider:

~~~java
class Owner {
    private final Node node;

    Owner(Node node) {
        this.node = node;
    }
}
~~~

`final` prevents reassigning the `node` field after proper initialization, but it **does not limit** how long Owner remains reachable. If Owner sits in a long-lived map, Node can also be kept reachable because Owner points to it.

An immutable object graph can still be **retained too long**, occupying memory unnecessarily. Immutability helps with concurrency and reasoning; it **does not by itself create eviction/lifecycle**.

Conversely, a mutable reference field allowing `owner.node = null` can help remove a link, though not every design has to expose a mutable field solely for GC. Decide ownership, lifecycle, and data retention according to contract.

## 22. Class Loaders, Static State, and Application Lifecycle

Static fields belong to the **runtime class**, whose identity is affected by the class loader. In application servers/plugin systems, a class loader intended to be unloaded can still be held by a thread, callback, global registry, or object graph that has a reference path to it.

This can keep **many classes/static data** alive unintentionally for a long time. Simply declaring `static` is not automatically a bug; the issue is the lifecycle boundary of the **class loader and whatever continues to keep it reachable**.

Applications with hot reload/plugin unloading must especially avoid:

- Threads created by the plugin that are never stopped.
- A listener in a registry belonging to a long-lived loader holding an object/plugin class.
- Strong cache keys/values pointing to types/instances from a loader that needs to be unloaded.
- ThreadLocals and executors that are not cleaned up.

These are causes of memory retention **due to retaining paths from roots**, not because each plugin has cyclic references.

## 23. GC Roots and Advanced Reachability APIs

In Java 17, `java.lang.ref.Reference.reachabilityFence(Object)` provides a way to ensure an object remains **strongly reachable at least until after the fence call** in necessary contexts, such as interoperability with native resources when the JIT might infer early that the object is no longer used.

This is an advanced tool. Most business code does not need to call `reachabilityFence`, and it **does not replace `close()`**. Misusing it can lead readers to think that the object will live forever or be processed by the collector at an exact time — neither of which is the API's contract.

### 23.1. Local Scope Is Not Necessarily Lifetime

~~~java
void run() {
    Resource resource = new Resource();
    resource.useNativeHandle();
    // resource is still in scope in the source code
}
~~~

This is an **illustrative snippet** requiring an appropriate `Resource` class. The Java compiler/JIT can determine that a local reference is no longer needed after its last use, depending on the case. The mental model that “a local is in scope until the closing } brace so it is always strongly held until then” is not an absolute rule.

For specialized native object liveness, consult the `reachabilityFence` API and safe patterns; for ordinary closeable resources, still prefer `try-with-resources`.

## 24. Steps to Analyze a Memory-Retention Problem

When heap usage grows, do not start by blindly deleting every cycle.

1. **Observe the symptoms:** does heap usage after GC cycles gradually increase? Does the number of live objects increase? Is there a cache/queue expected to be large?
2. **Identify the types being retained:** use a profiler, heap dump, or appropriate JVM tooling.
3. **Find retained paths to GC roots:** what is holding the object? A static map, listener registry, thread, context, or loader?
4. **Distinguish objects that are genuinely still needed** from objects whose business lifecycle has ended.
5. **Read the ownership code:** who registers, and who should unregister? Who puts entries into the cache, and who evicts them? Who creates the resource, and who closes it?
6. **Inspect the cycles:** if a cycle **has no root path**, it is not automatically a problem; if it has a root path, examine why it is being retained.
7. **Add contractual cleanup:** `remove`, `unsubscribe`, `close`, `finally`, bounded cache/TTL, cancel tasks, shutdown executors.
8. **Re-run the workload and measure:** verify that the live retained set shrinks as expected; avoid relying solely on free memory immediately after a single line of code.
9. **Check concurrency:** do cleanup and graph updates race with each other?
10. **Check test robustness:** do not write tests that require `System.gc()` to make a weakRef null at a fixed point in time.

In high-stakes or production scenarios, heap dumps and profiler data must be collected/read according to security policies because they can contain sensitive user data.

## 25. Unit Tests for Cyclic Relationships and Lifecycles

**Deterministic** tests should focus on API contracts:

| What to verify | How to verify |
| --- | --- |
| Two nodes form a cycle | `a.next()==b` and `b.next()==a` |
| Link broken properly | `b.next()==null` after unlink |
| Registry cleanup | `size()` decreases, lookup no longer finds the entry |
| Listener unsubscribe | Counter/listener count decreases; events after close are not delivered |
| ThreadLocal cleanup | `get()==null` after `remove()` |
| Resource close | `closed` flag / mock verify confirms it was called upon exiting `try-with-resources` |
| Graph traversal without infinite loops | Each identity is visited once, result is consistent |
| Bidirectional relationship | After transferring department, old list no longer contains the employee and new list contains the employee |
| WeakReference | Logic handles **both** `get()!=null` and `get()==null`, without forcing GC timing |
| Cache | Define eviction/size/TTL and test using a controlled clock or controlled operations |

A test like:

~~~java
System.gc();
Thread.sleep(100);
assert weak.get() == null;
~~~

is an **example you should not use** as a portable assertion: the JVM does not promise to collect an object within 100 ms, and strong references may still exist. If you need to verify memory behavior under workload, use integration/performance testing with statistical observation and environment limits, without calling it an absolute unit test.

### 25.1. Tests Should Prove Cleanup, Not That the Collector Ran

After `subscription.close()`, you can verify that the event bus no longer holds the listener and no longer invokes the callback — that is deterministic API behavior. There is no need (and usually no way) to prove immediately afterward that the subscriber has been reclaimed by GC.

Similarly, after `Registry.unregister(id)`, you can assert that the map no longer contains the entry; that is a necessary step to eliminate **one retention path**, not a guarantee that all references have disappeared.

## 26. Common Mistakes and How to Fix Them

| Misconception/Mistake | Reality and Solution |
| --- | --- |
| “A points to B and B points to A, so Java has a memory leak.” | A cycle does not by itself keep objects reachable from roots; check retained root paths. |
| “GC only reclaims an object when its reference count equals 0.” | Reason in terms of reachability, not pure reference counting. |
| “Removing one link means the object is deleted.” | Other links may still exist; GC timing is indeterminate. |
| “Assigning `x = null` frees memory immediately.” | It only removes one reference; GC timing and other aliases still apply. |
| “An object going out of scope is definitely collected right away.” | Scope and reachability/liveness do not share a single synchronized timestamp. |
| “`System.gc()` forces the JVM to run a full GC immediately.” | It is only a request/hint; there is no guarantee of timing or which objects are reclaimed. |
| “A static cache does not need bounds because GC handles it.” | Strong references in the cache can retain objects long-term; add eviction. |
| “A listener will disappear automatically after the UI closes.” | The registry may still retain the callback; unsubscribe at the end of the lifecycle. |
| “ThreadLocal clears itself after each request.” | Thread pools reuse threads; use `try/finally remove`. |
| “WeakReference is always null after assigning strong=null.” | Other aliases may exist; collector timing is not guaranteed. |
| “WeakHashMap has weak values.” | Keys are weak, values are normally strong; a value→key cycle can retain the key. |
| “SoftReference is an exact cache eviction policy.” | GC policy is not a predictable TTL or size cap. |
| “PhantomReference.get() returns an object that is about to die.” | `get()` is always null. |
| “Cleaner is a deterministic destructor.” | It is a non-deterministic fallback; use explicit closing. |
| “Java GC will automatically close databases/files as soon as the object is no longer used.” | Close resources using `AutoCloseable` and lifecycle management. |
| “UML composition guarantees the part is GC'd when the whole disappears.” | Ownership is a contract; other aliases and roots can still exist. |
| “Every `toString()` can print the entire graph.” | A cyclic graph can cause infinite recursion. |
| “`HashSet` is always suitable for tracking each object instance.” | `equals` may merge objects with different identities; consider IdentityHashMap. |
| “A `final` reference prevents an object from leaking.” | An immutable/final object can still be retained too long by a root. |
| “An inner object cannot retain Outer.” | A non-static inner object is attached to its enclosing instance; consider a static nested class. |
| “Java can automatically update both sides of a link.” | Operations are needed to preserve bidirectional graph invariants. |
| “Two threads updating separate references are definitely safe.” | Multi-object invariants and visibility require synchronization. |
| “Heap not shrinking yet means cleanup failed.” | GC/heap management has its own timing; measure live objects/retained paths. |

## 27. Checklist for Designing an Object Graph with Clear Lifecycles

When a class A holds a reference to B, check:

1. **Is the relationship required or optional?** Is `null` allowed?
2. **Who creates B?** A, the caller, a container, or a repository?
3. **Who is responsible for unlinking?** Are there `detach`, `remove`, or `unsubscribe` methods?
4. **Can A and B point back to each other?** If so, is the graph invariant maintained when links change?
5. **Is B mutable?** Are there aliases from elsewhere?
6. **How long does A live?** Request, session, application, or static singleton?
7. **Is there a long-lived root path?** ThreadLocal, static map, listener, cache, or loader?
8. **Are there off-heap resources?** Who calls `close` and when?
9. **Is a weak reference needed?** If B is an optional cache entry, who holds a strong reference while it is in use?
10. **Does the collection have bounded size/eviction?**
11. **Do graph traversal/toString/serialization have cycle detection?**
12. **Is equality based on identity or domain value?** What criterion does the visited set use?
13. **Is there concurrency?** Are link updates and cleanup operations synchronized?
14. **Are there deterministic cleanup tests?** Without relying on GC timing.
15. **Is the ownership contract clearly documented?** Without relying on the name “composition” to imply automatic behavior.

## 28. Review Questions and Answers

**Question 1.** How many objects do A.next = B and B.next = A create if `new` is used only twice?  
**Answer:** Two objects; reference assignments only create a cycle in the graph, not additional objects.

**Question 2.** Does an `A → B → A` cycle by itself prevent Java GC from collecting the two objects?  
**Answer:** No. If the entire graph is no longer reachable under the reference-processing rules from GC roots, the cycle by itself does not prevent collection.

**Question 3.** If a static list holds a reference to A, while A points to B and B points to A, why can both be retained?  
**Answer:** There is a strong-reference path from the root/registry to A and then to B.

**Question 4.** Does assigning `a = null` guarantee that B and A are collected immediately?  
**Answer:** No. Aliases may still exist, and the JVM does not guarantee immediate GC.

**Question 5.** Why is “a variable going out of scope” not completely equivalent to “the object being reclaimed”?  
**Answer:** Scope is a lexical concept, whereas reachability/collection depends on runtime/liveness and the collector.

**Question 6.** What is the bug of retaining objects that are no longer needed in a static map called?  
**Answer:** It can be application memory retention/a memory leak because references are held too long.

**Question 7.** What can a listener remaining in an event bus after the UI closes retain?  
**Answer:** The callback and the objects it references/captures, potentially including the subscriber and related graph.

**Question 8.** Why should a listener have an unsubscribe/`AutoCloseable` handle?  
**Answer:** To end the retaining reference path at the right business time without waiting for GC.

**Question 9.** Why must you pay attention to `remove()` when using `ThreadLocal` in a thread pool?  
**Answer:** Threads are reused, so context values can remain attached to a thread into another request or be retained for a long time.

**Question 10.** Does `WeakReference.get()` always return the object until `System.gc()` is called?  
**Answer:** No. The collector can clear a weak reference according to rules once the referent is no longer strongly reachable; `get()` can return null.

**Question 11.** After `strong = null`, why should you not assert weakRef.get()==null right away?  
**Answer:** Other references may exist, and there is no guarantee that the collector ran at that moment.

**Question 12.** How does `WeakHashMap` hold keys and values?  
**Answer:** Keys weakly; values normally strongly. A value with a strong path back to the key can affect retention.

**Question 13.** What does `PhantomReference.get()` return?  
**Answer:** Always `null` according to the API.

**Question 14.** Why is `SoftReference` not by itself a precise memory-bounded caching solution?  
**Answer:** Its GC/clearing policy is not a TTL or bounded-size contract controlled by the application.

**Question 15.** Why should files be closed using `try-with-resources` instead of waiting for GC?  
**Answer:** `close()` is invoked according to program structure, protecting resources at a deterministic time; GC does not guarantee when closing happens.

**Question 16.** Can an `AutoCloseable` be used for things other than files/sockets?  
**Answer:** Yes. For example, a subscription handle uses `close()` to unsubscribe.

**Question 17.** Can an A↔B cycle cause bugs other than retention?  
**Answer:** Yes. Naive `toString`, `equals`, `hashCode`, or graph traversal can recurse without terminating.

**Question 18.** Why does DFS over a cyclic graph need a visited set?  
**Answer:** To avoid revisiting the same object endlessly; use an identity-based set when the meaning is instance identity.

**Question 19.** When can a `HashSet` differ from an identity-based visited set?  
**Answer:** When `equals/hashCode` defines two distinct instances as equal, HashSet may treat them as a single entry.

**Question 20.** If an Employee holds Department and Department holds Employees, does Java automatically keep both sides in sync?  
**Answer:** No. The API must update both links/lists according to the invariant.

**Question 21.** Does `final Node next` guarantee that Node will not be retained for a long time?  
**Answer:** No. Final does not determine the lifetime of an object graph retained from roots.

**Question 22.** How can a non-static inner class cause Outer to live longer than expected?  
**Answer:** Inner is attached to the enclosing instance; if a root retains inner, Outer can remain reachable through that relationship.

**Question 23.** If UML composition states that Part belongs to Whole, does Java GC automatically delete Part when Whole is no longer used?  
**Answer:** Not on a deterministic schedule; the part may still be reachable from elsewhere, and DB lifecycle is a separate matter.

**Question 24.** Does high heap usage after `registry.clear()` prove there is still a leak?  
**Answer:** No. The JVM may keep heap committed or not yet have collected; live objects/retained paths must be analyzed.

**Question 25.** Why should you not write a test like “`System.gc(); sleep(100); assert weak.get()==null`”?  
**Answer:** It is non-portable and non-deterministic: GC is not guaranteed to run/process the referent within that timeframe.

**Question 26.** Is there any contradiction when a resource is closed while the Java object is still reachable?  
**Answer:** No. Resource lifecycle and object reachability are two independent concepts.

**Question 27.** Does `Cleaner` make `close()` unnecessary?  
**Answer:** No. Cleaner is a fallback with uncertain timing, and a cleaning action can accidentally retain the referent if poorly designed.

**Question 28.** What impact can a root path through a class loader/thread have?  
**Answer:** It can keep objects/classes/a plugin graph alive unintentionally for a long time; registrations, tasks, and thread-associated state must be released.

**Question 29.** When is a cycle valid from a business perspective?  
**Answer:** For example, bidirectional graphs, parent–child backlinks, social networks, and doubly linked lists, provided invariants and traversal are clearly designed.

**Question 30.** What are the first three questions to ask when seeing a “memory leak caused by a cycle”?  
**Answer:** (1) Is the object graph still reachable from GC roots? (2) What is holding that reference path and why? (3) Can cleanup/eviction/unsubscription/closing be performed according to lifecycle?

## References

- Java Language Specification, [`4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): reference types and values.
- Java Language Specification, [`4.12.5 — Initial Values of Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.5): default `null` for reference fields.
- Java Language Specification, [`12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): creating and initializing objects.
- Java Language Specification, [`12.6 — Finalization of Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6): relationship with finalization/reachability in the language description.
- Java Platform API, [`java.lang.ref Package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html): strong, soft, weak, phantom references and reachability.
- Java Platform API, [`WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak references.
- Java Platform API, [`WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys and strong values.
- Java Platform API, [`Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): fallback cleanup.
- Java Platform API, [`AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): explicit resource closing.
- Java Platform API, [`ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): thread-associated values and `remove`.
- Java Platform API, [`Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): advanced liveness boundary.
- Java Language Specification, [`14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): order of calling `close`.
- OpenJDK [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): reasons not to rely on finalization.

## Conclusion

**Cyclic references do not by themselves cause memory leaks in Java.** What determines the continued survival of an object graph is **the reference paths still leading from GC roots**, along with the semantics of the applicable reference types. An unreachable cycle can be collected by GC; conversely, just a single static registry or callback still holding a reference to one object can keep **the entire graph** alive longer than expected.

Therefore, when designing relationships between classes, do not merely ask “Do A and B point to each other?”. Ask **who owns the link, who is allowed to change/break the link, when the business lifecycle ends, whether there is a retaining path from a long-lived owner, and whether there are resources that must be closed explicitly?**

Use **`unsubscribe`/`remove`/eviction**, `try-with-resources`, `ThreadLocal.remove()`, immutable/snapshot contracts, and graph traversal with identity-accurate `visited` tracking when appropriate. **Do not rely on `System.gc()` or finalizers to determine cleanup timing.** Test reference/API changes that can be measured deterministically, while the timing of JVM memory reclamation is a separate decision of the runtime.
