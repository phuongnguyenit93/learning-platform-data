# Automatic Garbage Collection and Unguaranteed Collection Timing — Java 17+

## 1. Overview

In Java, developers typically create objects with `new` without having to call `free` to manually release individual memory regions as in some manual memory management languages. The **garbage collector (GC)** of the Java runtime environment can reclaim the heap memory of objects that are **no longer reachable according to JVM rules** for subsequent allocations.

However, there is a very important difference:

- **No longer having an accessible strong reference to an object** does not mean the object **has been collected immediately**.
- Setting a variable to `null`, exiting a block/method, or calling `System.gc()` **is not a promise about when the object will be collected**.
- The JVM is permitted to optimize how lifetime, allocation, and garbage collection are managed; a correct program must not depend on a GC event occurring at a specific time.
- GC reclaims **managed memory on the heap**. It is **not** a reliable mechanism to close files, sockets, database connections, or release resources outside the JVM.

An example of a mistaken expectation is creating an object, assigning the reference to null, and then claiming "the object has been GC'd". That conclusion is **not guaranteed by Java**. The object may become *eligible for collection*, but the decision to collect depends on the implementation, memory state, collector, remaining references, and runtime behavior.

**Core message:** GC automatically manages memory reclaimability; **the actual time of collection is not a correctness condition that an application is permitted to assume**.

This lesson belongs to **Java core – class-object**, **Object Lifecycle** group, topic **Automatic Garbage Collection and Unguaranteed Collection Timing**. Standalone programs use **Java 17+**; all presented stdout is **independent of GC scheduling**. Technical demonstration snippets without `main` are explicitly noted; no example intentionally waits for a finalizer or forces the JVM to collect at a specific time.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish *allocation*, *reachability*, *eligibility for GC*, and *actual reclamation*.
2. Explain why object references determine reachability through the object graph.
3. Recognize that objects can remain reachable through static fields, the stack, threads, collections, listeners, and reference chains.
4. Understand that an object graph with reference cycles can still become garbage when no reachable path remains from GC roots.
5. Distinguish strong, soft, weak, and phantom references accurately, without inferring cleanup timing.
6. Understand the limitations of `System.gc()` and `Runtime.gc()`.
7. Avoid using `finalize()` to manage resources.
8. Use `try-with-resources`/`AutoCloseable` to release resources following proper control flow.
9. Know the role and limitations of `Cleaner` and `ReferenceQueue`.
10. Identify Java-style memory leaks when objects remain unintentionally reachable.
11. Analyze why `WeakHashMap` is not suitable for every cache and why weak references do not guarantee immediate collection.
12. Distinguish GC log/heap metrics from a guarantee that GC will occur.
13. Understand `Reference.reachabilityFence` when working with non-heap resources.
14. Test program behaviors without relying on `Thread.sleep`, `System.gc`, or finalization timing.

## 3. Object Lifecycle and What Can Be Asserted

An object may go through conceptual stages:

~~~text
Object creation
    |
    v
Accessible via references from the program
    |
    v
No longer reachable through applicable strong reachability paths
    |
    v
May be considered for reclamation by GC (depending on reference category)
    |
    v
Memory reclaimed by the JVM at a time that is NOT GUARANTEED
~~~

The diagram helps visualize the concept rather than being **a state machine for which the Java API provides state-transition times for each object**. GC may run multiple times while an object is still alive, have multiple collection phases, or an object may never need a separate observable reclamation operation due to runtime optimizations.

Do not confuse:

- **Variable scope**: where the variable name is validly used in the source.
- **Reference lifetime**: the span during which the program can hold that reference according to runtime analysis.
- **Object reachability**: whether the object can be reached from roots according to reference rules.
- **Memory retention duration**: the JVM might not immediately return reclaimed heap memory to the operating system.
- **Non-heap resources**: file descriptors, native buffers, and sockets have different lifecycle policies.

A variable going out of scope helps us reason about the remaining reference paths, but does not provide an exact clock for collection.

## 4. Heap, Stack, and GC Roots: A Sufficient Model

In the Java conceptual model:

- The **heap** holds objects/arrays managed by the runtime.
- **Stack frames** of Java threads have local variables and the operand stack; some references here can keep objects reachable.
- **Static fields** can hold references to objects that remain alive for a large portion of the application's lifetime.
- References associated with **live threads**, runtime structures, JNI/native handles, and other JVM-defined roots can also participate in reachability analysis.

You should not derive the rule "every local variable still in scope always keeps an object alive until the closing brace". An optimizing JIT can determine earlier that a reference is no longer needed. In situations where an object must be kept strongly reachable up to a clear point to protect native resources, `Reference.reachabilityFence` provides a dedicated API.

**GC roots** are not a list of Java variables that user code can fully traverse through a public API. Heap dump/profiler tools can analyze retaining paths, but this is observing the implementation/runtime, not a reason for application code to depend on GC timing.

## 5. Complete Program 1 — Object Creation Does Not Imply GC Timing

File **`ObjectLifetimeDemo.java`**:

~~~java
final class Note {
    private final String text;

    Note(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}

public class ObjectLifetimeDemo {
    static void createAndUse() {
        Note note = new Note("Java");
        System.out.println("during=" + note.text());
    }

    public static void main(String[] args) {
        createAndUse();
        System.out.println("method returned");
        System.out.println("GC timing unknown");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ObjectLifetimeDemo.java
java ObjectLifetimeDemo
~~~

**Exact stdout:**

~~~text
during=Java
method returned
GC timing unknown
~~~

When `createAndUse` returns, the local variable `note` of that invocation is no longer accessed by the caller. However, **no stdout line proves that GC has run or that the Note object has been reclaimed**. The runtime may collect later or optimize allocation/lifetime observation.

The proper test of behavior here is the three output lines related to program control, **not** a GC event.

## 6. When Does an Object Become a Candidate for Collection?

Example:

~~~java
Object value = new Object();
value = null;
~~~

This is a valid snippet inside a method. After the assignment, the variable `value` no longer points to the original object. However, the conclusion **"the object is no longer reachable anywhere"** is only true if **no other strong path remains** to that object.

If before assigning null we have:

~~~java
Object value = new Object();
Object alias = value;
value = null;
System.out.println(alias != null);
~~~

The object still has an access path through `alias`. The printed line is `true`, and the action of assigning null to `value` **does not break** the reference from `alias`.

**Do not use "reference count equals 0" as a formal definition of Java GC**. Some collectors use tracing/reachability graphs; multiple objects with reference cycles can still be collected if they are not reachable from roots. Each reference type (weak/soft/phantom) also has its own rules.

## 7. Complete Program 2 — An Alias Keeps an Object Accessible

File **`StrongAliasDemo.java`**:

~~~java
public class StrongAliasDemo {
    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");
        StringBuilder alias = source;

        source = null;
        alias.append("B");

        System.out.println("alias=" + alias);
        System.out.println("source is null=" + (source == null));

        alias = null;
        System.out.println("no local alias kept");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 StrongAliasDemo.java
java StrongAliasDemo
~~~

**Stdout:**

~~~text
alias=AB
source is null=true
no local alias kept
~~~

Despite `source = null`, the same StringBuilder is still accessed through `alias` and its content is modified to AB. The `alias = null` statement at the end only changes one variable; it **does not invoke GC** and does not return a "memory freed" state.

## 8. Reachability Is a Matter of the Reference Graph

An object can be indirectly reachable through a chain of references:

~~~text
GC root
  |
  v
Application.staticCache
  |
  v
HashMap
  |
  v
Entry.value
  |
  v
List
  |
  v
LargePayload
~~~

A method that only assigns `payload = null` on a local variable **does not eliminate the path** from `staticCache` through the Map/List to LargePayload. If the static cache continues to hold the object graph, GC sees them as **still in use in the sense of reachability**, even though business logic no longer needs the payload.

This is the cause of many **memory leaks in GC languages**: it is not that the object is "not recognized by GC", but because the program **keeps holding references for too long**.

When analyzing memory, asking "**who is holding the object?**" is usually more useful than asking "**why won't GC run?**".

## 9. Complete Program 3 — A Collection Retains Objects Until References Are Removed

File **`CollectionRetentionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CollectionRetentionDemo {
    public static void main(String[] args) {
        List<StringBuilder> retained = new ArrayList<>();

        StringBuilder payload = new StringBuilder("item");
        retained.add(payload);
        payload = null;

        System.out.println("entries=" + retained.size());
        System.out.println("value=" + retained.get(0));

        retained.clear();
        System.out.println("after clear=" + retained.size());
        System.out.println("GC event not asserted");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CollectionRetentionDemo.java
java CollectionRetentionDemo
~~~

**Stdout:**

~~~text
entries=1
value=item
after clear=0
GC event not asserted
~~~

The List holds a strong reference to the StringBuilder, so the object can be read even after the `payload` variable is assigned null. `clear()` removes the element from the List according to the collection contract. If no other references remain, the object may become eligible for collection; **do not conclude when `clear()` returns that the object's memory has been reclaimed by GC**.

## 10. Reference Cycles Do Not Necessarily Cause a Memory Leak

Suppose A holds B and B holds A:

~~~text
        +---------------+
        |               |
        v               |
        A -----------> B
        ^               |
        +---------------+
~~~

If a GC root still leads to A or B, the relevant portion of the graph can be reachable. However, if **all paths from GC roots to both objects are lost**, they can be considered unreachable even while still holding references to each other.

A tracing collector does not need "reference count equal to 0 for each object" to recognize that a group of objects is no longer reachable. Therefore, the statement "Java cannot collect two objects pointing to each other" is **false**.

**Limitation:** stating "can be collected" differs from "has been collected in a specific GC run". The program has no standard API promising that an object will be reclaimed immediately after losing its root.

## 11. Complete Program 4 — Cyclic Object Graph

File **`CyclicObjectsDemo.java`**:

~~~java
final class Node {
    final String name;
    Node next;

    Node(String name) {
        this.name = name;
    }
}

public class CyclicObjectsDemo {
    static void buildCycle() {
        Node first = new Node("first");
        Node second = new Node("second");

        first.next = second;
        second.next = first;

        System.out.println("cycle="
                + (first.next.next == first));
    }

    public static void main(String[] args) {
        buildCycle();
        System.out.println("buildCycle returned");
        System.out.println("collection not promised");
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 CyclicObjectsDemo.java
java CyclicObjectsDemo
~~~

**Stdout:**

~~~text
cycle=true
buildCycle returned
collection not promised
~~~

The pair of nodes hold references to each other. After `buildCycle` returns, the example keeps no long-lived application reference to them, yet **do not assume GC runs immediately**. A cyclic reference graph is a property of an object graph, not proof of a memory leak.

## 12. `System.gc()`: A Suggestion, Not "Collect Immediately"

Java provides:

~~~java
System.gc();
Runtime.getRuntime().gc();
~~~

These are valid Java statements. They can be used to **suggest** that the JVM make an effort to perform garbage collection. According to the API, `System.gc()` suggests that the JVM make an effort to reclaim unused objects so that the memory currently occupied is ready for reuse. **There is no guarantee** that any specific object will be collected before the call returns.

Some configurations/runtimes may restrict or disable handling of explicit GC requests. Even if the JVM actually performs GC, an object that is still reachable is still not "garbage" simply because the caller wants to collect it.

Do not write production code under these assumptions:

- "Calling `System.gc()` will fix a memory leak."
- "`System.gc()` always triggers a full GC."
- "After `System.gc()`, `WeakReference.get()` is guaranteed to return null."
- "After `System.gc()`, memory usage is guaranteed to decrease."
- "After `System.gc()`, all native resources are closed."

These claims are either **not guaranteed by the API**, or they ignore the reason references are being held.

## 13. Complete Program 5 — Suggesting GC Without Guessing the Outcome

File **`GcRequestDemo.java`**:

~~~java
public class GcRequestDemo {
    public static void main(String[] args) {
        byte[] payload = new byte[1_024];
        System.out.println("payload size=" + payload.length);

        payload = null;
        System.out.println("reference dropped");

        System.gc();
        System.out.println("GC request returned");
        System.out.println("no object collection asserted");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GcRequestDemo.java
java GcRequestDemo
~~~

**Program stdout, when GC logging is not enabled:**

~~~text
payload size=1024
reference dropped
GC request returned
no object collection asserted
~~~

The line `GC request returned` only proves that the `System.gc()` call has **returned**; it **does not prove** that the byte array object has been reclaimed, how many bytes were freed, or that a full GC occurred.

Measuring timing around a `System.gc()` call and inferring a general GC schedule is also unreliable: JVM warmup, JIT, collector selection, application load, and memory cause measurements to vary.

## 14. Why Might Heap Memory Not Decrease as Expected?

Three quantities need to be separated:

1. **Object liveness/reachability:** the portion of the object graph still retained by the application/runtime.
2. **Used heap:** the observed figure of used capacity at a given point in time according to a specific tool/API.
3. **Committed heap/reserved address space:** the heap region committed/reserved by the JVM; it is not required to be returned to the operating system immediately when objects are reclaimed.

A GC may collect unused objects while the JVM still **retains the committed heap** for further allocations. Therefore, Task Manager or a process memory chart might not drop in the way learners expect.

Conversely, used heap in a given sampling can increase due to other valid allocations, even after a GC call. Do not infer a memory leak from just **a single** observation.

Evaluate trends across multiple cycles under a representative workload, inspect retaining paths, and analyze collector logs/heap dumps with the proper tools; do not treat `System.gc()` as a boolean test for an object.

## 15. `Runtime` Memory Methods Do Not Measure "the Object Has Been GC'd"

The methods:

~~~java
Runtime runtime = Runtime.getRuntime();
long free = runtime.freeMemory();
long total = runtime.totalMemory();
long max = runtime.maxMemory();
~~~

This is a valid snippet inside a method. They describe JVM memory metrics per the API and do not provide specific object lifetimes. The values vary by timing, heap configuration, and runtime implementation.

**You should not print those metrics as "fixed expected stdout" in learning materials:** the JVM runs on different machines/heap flags. To build a test with deterministic output, you can check general properties such as totalMemory being greater than 0, rather than comparing a specific byte count.

If you want to understand GC, observe logs or metrics; if you want to **verify program behavior**, design tests independent of GC timing.

## 16. Complete Program 6 — Sampling the Heap Without Fixed Byte Counts

File **`HeapSnapshotDemo.java`**:

~~~java
public class HeapSnapshotDemo {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();
        long total = runtime.totalMemory();
        long free = runtime.freeMemory();
        long max = runtime.maxMemory();

        System.out.println("total positive=" + (total > 0));
        System.out.println("free nonnegative=" + (free >= 0));
        System.out.println("max positive=" + (max > 0));

        byte[] bytes = new byte[256];
        System.out.println("array length=" + bytes.length);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 HeapSnapshotDemo.java
java HeapSnapshotDemo
~~~

**Stdout on a normally operating JVM:**

~~~text
total positive=true
free nonnegative=true
max positive=true
array length=256
~~~

`maxMemory()` may hold a very large value if the JVM has no defined limit per the contract; you should not rely on a specific number. The demo only prints basic checks and the array length, **without pretending to know when GC occurs**.

## 17. Strong Reference: The Usual Case

A variable of type `Object`, `StringBuilder`, `List<T>`, or an ordinary field can hold a **strong reference** to an object. If a strong reachability path from a GC root to the object still exists, that object is not considered freely collectible just because another variable is set to null.

~~~java
Object item = new Object();
java.util.List<Object> list = new java.util.ArrayList<>();
list.add(item);
item = null;
~~~

This is a valid snippet inside a method. The List still holds a reference to the original object.

**A strong reference is not the same as immutability:** an object held by a strong reference can still be mutable. Nor does it mean the application "truly needs" the object. A cache without an eviction policy can hold objects that no longer have business value yet remain reachable from a static field.

## 18. `WeakReference`: Weak References Do Not Keep Objects Strongly Alive

`java.lang.ref.WeakReference<T>` is used when the caller wants the ability to observe an object if it **has not yet been collected**, without wanting that reference itself to force the object to stay alive like a strong reference.

~~~java
Object object = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(object);
~~~

This snippet is valid. While the variable `object` still holds a strong reference, `weak.get()` can return the object. If later no appropriate strong/soft references remain, the JVM can detect weak reachability and clear the weak reference during a collection phase; at that point `weak.get()` returns null.

**Do not claim** that "assigning `object = null` makes `weak.get()` return null immediately". The reference might not yet be cleared at the time of reading, and runtime optimizations mean that object lifetimes should not be inferred solely from source-level assignments.

`WeakReference` is suitable for temporary associated metadata, canonicalizing structures, or certain cache relationships with clear semantics. It does not by itself define a useful retention policy for every cache.

## 19. Complete Program 7 — `WeakReference.clear()` Has Deterministic Results

File **`WeakReferenceDemo.java`**:

~~~java
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak =
                new WeakReference<>(strong);

        System.out.println("same=" + (weak.get() == strong));

        weak.clear();
        System.out.println("cleared=" + (weak.get() == null));
        System.out.println("strong remains="
                + (strong != null));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 WeakReferenceDemo.java
java WeakReferenceDemo
~~~

**Stdout:**

~~~text
same=true
cleared=true
strong remains=true
~~~

The demo calls **`weak.clear()` explicitly**, so `weak.get()` returning null is a program-controlled result, **not proof that GC has run**. The strong variable still points to the object, and the object can continue to be used normally.

If you replace `clear()` with `System.gc()`, the stdout `cleared=true` is **no longer guaranteed**. That is why an example teaching GC should not fabricate a "test" relying on a weak ref definitely disappearing immediately.

## 20. `SoftReference`: Do Not Rely on Cache Cleanup Schedules

`SoftReference<T>` has different lifetime rules from WeakReference: the JVM can keep a softly reachable object alive longer and clear soft references according to policies related to memory demand. The Java API provides semantics intended to support memory-sensitive caches, but **does not give the application exact control over when a soft reference is cleared**.

Therefore:

- Do not assume an object held by a SoftReference remains alive up to a specific MB threshold.
- Do not assume a `System.gc()` call always clears all soft refs.
- Do not use SoftReference to replace a **cache with a size limit/TTL/eviction policy** when performance or memory limits must be predictable.
- `get()` can return null, so the caller needs a path to reconstruct the data.
- Do not use soft refs as a mechanism for timely release of files/sockets.

When caching is needed in a real application, prioritize a clear cache contract: maximum entries/weight, expiration, invalidation, metrics, and ownership. Soft reference is only a specialized tool.

## 21. Complete Program 8 — Soft Reference and Explicit Clear

File **`SoftReferenceDemo.java`**:

~~~java
import java.lang.ref.SoftReference;

public class SoftReferenceDemo {
    public static void main(String[] args) {
        StringBuilder strong = new StringBuilder("cached");
        SoftReference<StringBuilder> soft =
                new SoftReference<>(strong);

        System.out.println("initial=" + soft.get());
        soft.clear();
        System.out.println("after clear=" + soft.get());
        System.out.println("original=" + strong);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SoftReferenceDemo.java
java SoftReferenceDemo
~~~

**Stdout:**

~~~text
initial=cached
after clear=null
original=cached
~~~

`soft.clear()` is called explicitly, so the result is deterministic. The demo **does not simulate memory pressure or GC selection**. The strong reference keeps the StringBuilder on the program side; clearing the soft reference does not destroy the object.

## 22. `PhantomReference`: Tracking Post-Reachability State, Without Accessing the Object

`PhantomReference<T>` is more specialized: `get()` on a PhantomReference **always returns null**. It does not provide a way to read the object like WeakReference.

Typically, PhantomReference is used in combination with `ReferenceQueue` to observe a processing milestone related to reachability and cleanup management. However:

- It does **not** indicate a guaranteed time at which the object is collected.
- Queue notification depends on GC and the reference-processing mechanism.
- It does **not** release external resources within the timeframe desired by the application.
- You cannot `get()` the object and "resurrect" it via PhantomReference.
- Using `Cleaner` is usually easier than managing phantom refs directly if the goal is backup cleanup of a state holder.

With Java 17, critical logic should not be designed under the assumption that a phantom ref will be enqueued before the process terminates.

## 23. Complete Program 9 — `PhantomReference.get()` Is Always Null

File **`PhantomReferenceDemo.java`**:

~~~java
import java.lang.ref.PhantomReference;
import java.lang.ref.ReferenceQueue;

public class PhantomReferenceDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        PhantomReference<Object> phantom =
                new PhantomReference<>(strong, queue);

        System.out.println("phantom get null="
                + (phantom.get() == null));
        System.out.println("strong exists=" + (strong != null));
        System.out.println("no queue timing assumed");
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 PhantomReferenceDemo.java
java PhantomReferenceDemo
~~~

**Stdout:**

~~~text
phantom get null=true
strong exists=true
no queue timing assumed
~~~

`get()` is always null according to the contract of PhantomReference, **even when a strong reference still holds the object**. Therefore, null from `phantom.get()` does not prove that the object has been processed by GC.

## 24. `ReferenceQueue`: Notification Is Not a Timing Promise

A `ReferenceQueue<T>` can receive reference objects after a reference is cleared/processed according to the corresponding rules and has been registered with the queue. Methods such as `poll()` or `remove()` allow retrieving references that are currently enqueued.

However, without a deterministic GC event, you should not write:

~~~java
// INTENTIONALLY WRONG reasoning snippet, do not use for testing:
// weakTarget = null;
// System.gc();
// assert queue.poll() != null;
~~~

That is **code illustrating a mistaken expectation**, not a program guaranteed to pass.

When testing queue-processing logic, you can **explicitly enqueue the reference** using `Reference.enqueue()` if the test contract allows it, instead of waiting for GC. That way you test the **queue-processing software** without confusing it with measuring the collector.

`ReferenceQueue.remove(timeout)` can block up to the timeout and is subject to thread scheduling; avoid using its specific timing outcome as expected test stdout.

## 25. Complete Program 10 — Proactively Enqueuing to Test the Queue

File **`ReferenceQueueDemo.java`**:

~~~java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public class ReferenceQueueDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        WeakReference<Object> weak =
                new WeakReference<>(strong, queue);

        boolean enqueued = weak.enqueue();
        Object received = queue.poll();

        System.out.println("manual enqueue=" + enqueued);
        System.out.println("same reference=" + (received == weak));
        System.out.println("strong exists=" + (strong != null));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ReferenceQueueDemo.java
java ReferenceQueueDemo
~~~

**Stdout:**

~~~text
manual enqueue=true
same reference=true
strong exists=true
~~~

The reference object is **enqueued via an explicit call**; the strong referent still exists, so there is no "GC just ran" interpretation. Calling `poll` proves that the queue received the WeakReference object itself.

`ReferenceQueue` only provides information related to registered reference objects; it is not a basic callback that always runs right when an object goes out of scope.

## 26. `WeakHashMap` and Ownership: Use with Care

`WeakHashMap<K,V>` has **keys held by weak references**. It is useful when metadata should stop being strongly held solely by the Map once no appropriate strong reference path remains to the key.

However:

- Key entries do not disappear immediately when code sets the local key to null.
- Entry removal depends on GC, reference queue processing, and operations on the Map.
- Values are held strongly as usual; if a value **references back to the key** through a strong graph, the key may remain reachable and the entry will not disappear as expected.
- WeakHashMap does not guarantee thread safety or an eviction schedule.
- Weak keys are not suitable for every cache, especially caches requiring predictable TTL/capacity and stable keys.

Do not test that `size()` will equal 0 after a `System.gc()` and treat inconsistent results as a bug in WeakHashMap. Use explicit `remove`/`clear` when a mapping needs to be cleaned up immediately.

## 27. Complete Program 11 — Timely WeakHashMap Removal via the Map API

File **`WeakMapDemo.java`**:

~~~java
import java.util.Map;
import java.util.WeakHashMap;

public class WeakMapDemo {
    public static void main(String[] args) {
        Map<Object, String> metadata = new WeakHashMap<>();
        Object key = new Object();

        metadata.put(key, "tag");
        System.out.println("lookup=" + metadata.get(key));
        System.out.println("entries=" + metadata.size());

        metadata.remove(key);
        System.out.println("after remove=" + metadata.size());
        System.out.println("no GC assumption");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 WeakMapDemo.java
java WeakMapDemo
~~~

**Stdout:**

~~~text
lookup=tag
entries=1
after remove=0
no GC assumption
~~~

The key object remains strongly held in the method during lookup/remove, so the result does not depend on the collector. Timely entry cleanup is performed using `Map.remove`, without waiting for weak-key processing.

## 28. GC Is Not Resource Ownership: Must Close Based on Work Completion

GC manages memory reclamation of Java objects **when they are no longer reachable**; it does not know exactly when a file, socket, native handle, or database connection has finished its work in the business-logic sense. A Java object may still be reachable yet the resource must already be closed; it is also possible that an object becomes unreachable while closing the resource is delayed.

**Two independent milestones:**

- *Reachability*: does a reference path from GC roots still exist?
- *Resource lifetime*: has the owner finished using the resource and must it call `close()` or the corresponding shutdown operation?

For a resource implementing `AutoCloseable`, `try-with-resources` expresses the closing point according to control flow, without waiting for the collector. The immediately following example provides deterministic proof via stdout; it does not use `System.gc()` to "check" closing.

## 29. Complete Program 12 — `AutoCloseable` Closes on Time

File **`TryWithResourcesDemo.java`**:

~~~java
final class DemoResource implements AutoCloseable {
    DemoResource() {
        System.out.println("opened");
    }

    void use() {
        System.out.println("used");
    }

    @Override
    public void close() {
        System.out.println("closed");
    }
}

public class TryWithResourcesDemo {
    public static void main(String[] args) {
        try (DemoResource resource = new DemoResource()) {
            resource.use();
        }

        System.out.println("after try");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 TryWithResourcesDemo.java
java TryWithResourcesDemo
~~~

**Stdout:**

~~~text
opened
used
closed
after try
~~~

`close()` is invoked when exiting try-with-resources according to Java syntax; no GC is needed. If the body throws an exception, try-with-resources still attempts to close the resource according to the language rules.

Unlike a finalizer or Cleaner, this is the way to achieve **timely lifecycle control** in an application.

## 30. Closing Multiple Resources Does Not Depend on GC Scheduling

In a `try` statement declaring multiple resources, the initialization expressions are evaluated in left-to-right order; resources created successfully are closed **in reverse order** upon exiting the scope. This is a Java control-flow rule, not the order in which the collector inspects the object graph.

If initializing the second resource fails, the first resource that was initialized successfully is still closed. If the body and the close operations both fail, Java also has rules for primary/suppressed exceptions. The dedicated lesson **Closing Resources with AutoCloseable and try-with-resources** explains all of these cases along with ownership; in this lesson on GC, simply remember: **closing a resource is not a GC event**.

The next complete example clearly prints the order `open A → open B → body → close B → close A`, completely without requiring the garbage collector to run.

## 31. Complete Program 13 — Resource Closing Order

File **`CloseOrderDemo.java`**:

~~~java
final class Resource implements AutoCloseable {
    private final String name;

    Resource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}

public class CloseOrderDemo {
    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("body");
        }
        System.out.println("done");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CloseOrderDemo.java
java CloseOrderDemo
~~~

**Stdout:**

~~~text
open A
open B
body
close B
close A
done
~~~

Resources close in LIFO order as soon as the try block exits normally. Even if a GC collector does not run throughout the entire program, the `close` behavior still occurs according to the contract.

## 32. Suppressed Exceptions Prove Cleanup Belongs to Control Flow

When the body of `try-with-resources` throws an exception and `close()` also throws an exception, the error from the `try` body is the *primary exception*, while the error arising during closing is stored via `getSuppressed()`. This mechanism preserves error information from the main work while also indicating that cleanup failed.

The distinction from GC: this is behavior of **stack unwinding and resource closing**, which can be tested deterministically on the same input. It does not require the object to become unreachable, sends no request to GC, and does not depend on whether the collector runs or not.

The dedicated AutoCloseable/TWR lesson delves into closing multiple resources, initialization errors, and ownership. The following program simply confirms exactly **1 primary, 1 suppressed** without relying on GC timing.

## 33. Complete Program 14 — Suppressed Exceptions

File **`SuppressedExceptionsDemo.java`**:

~~~java
import java.io.IOException;

final class FailingResource implements AutoCloseable {
    @Override
    public void close() throws IOException {
        throw new IOException("close");
    }
}

public class SuppressedExceptionsDemo {
    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("body");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressed="
                    + ex.getSuppressed().length);
            System.out.println("suppressed message="
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SuppressedExceptionsDemo.java
java SuppressedExceptionsDemo
~~~

**Stdout:**

~~~text
primary=body
suppressed=1
suppressed message=close
~~~

The body throws IOException("body"), then automatic closing throws IOException("close"); the exception during closing is attached to the primary exception's suppressed exceptions. The behavior is completely deterministic via `try-with-resources`, does not wait for GC, and is unrelated to object eligibility.

## 34. Why Is `finalize()` Not a Reliable Lifecycle Hook?

Historically, Java allowed a class to override `Object.finalize()` to run logic related to object reclamation. However, finalization **has long been deprecated** and is unsuitable for releasing resources.

The issues:

- There is no guarantee that `finalize()` will be called within the lifetime of the process.
- There is no guarantee of when a finalizer runs after an object is no longer needed.
- The finalization order among objects does not provide a resource dependency order you should rely on.
- Finalization can cause latency, safety issues, and complex logic.
- Finalizer code can make an object reachable again (resurrection), complicating lifecycle reasoning.
- The JVM process can terminate while finalizable objects remain unprocessed.

**Do not write tests that use `Thread.sleep(...)` and expect a finalizer to print a specific line.** Do not use a finalizer to close a connection/file or complete a transaction.

A Java class with `final` has **no relation** to finalization: `final` prevents inheritance/reassignment, whereas `finalize()` is a legacy cleanup mechanism.

## 35. `Cleaner`: A Fallback Solution, Not Timely Closing

Java provides `java.lang.ref.Cleaner` to register a cleanup action tied to an object's reachability. This is a better-structured alternative to finalizers in some libraries managing native state, yet **the timing of automatic cleanup is still not guaranteed**.

Principles:

1. The cleanup action should hold the **state that needs cleaning**, not strongly hold the object being tracked (*referent*).
2. If the action captures the referent, it can inadvertently keep the referent reachable, preventing automatic cleanup from being triggered as intended.
3. The cleanup action must be safe when running only once; `Cleanable.clean()` allows **explicit invocation**.
4. Do not treat registering a Cleaner as a replacement for `close()` on a resource with a defined lifetime.
5. Do not count on cleanup actions running before the process terminates or within a fixed amount of time.
6. Cleaner is suitable as a **backup safety net**, not a transaction commit/final flush mechanism.

The goal of the following example is to illustrate calling `clean()` **explicitly**, so that stdout is not tied to GC.

## 36. Complete Program 15 — Calling `Cleaner.Cleanable.clean()` Directly

File **`CleanerDemo.java`**:

~~~java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicInteger;

public class CleanerDemo {
    public static void main(String[] args) {
        Cleaner cleaner = Cleaner.create();
        AtomicInteger actions = new AtomicInteger();

        Object owner = new Object();
        Cleaner.Cleanable cleanable =
                cleaner.register(owner, actions::incrementAndGet);

        cleanable.clean();
        cleanable.clean();

        System.out.println("cleanup calls=" + actions.get());
        System.out.println("owner still exists=" + (owner != null));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CleanerDemo.java
java CleanerDemo
~~~

**Stdout:**

~~~text
cleanup calls=1
owner still exists=true
~~~

The `Cleanable.clean()` method runs the action synchronously when called explicitly; calling it again does not perform cleanup a second time according to the contract. The action only captures AtomicInteger, not the owner object.

**Do not conclude** that the line `cleanup calls=1` is proof that GC ran: the behavior comes from the two `clean()` calls in main. If you only register and then drop owner, the count/timing of automatic actions is not something a program can put into fixed expected stdout.

## 37. `Reference.reachabilityFence`: Keeping an Object Alive Up to a Required Point

In code interacting with a native resource, a wrapper object may need to remain strongly reachable while a native operation uses the handle owned by the wrapper. An optimizing JVM can sometimes determine that the object is no longer needed under ordinary uses earlier than a reader of the source code might imagine.

`java.lang.ref.Reference.reachabilityFence(reference)` is provided to ensure that the referent remains **strongly reachable at least until the invocation point** according to API semantics. For example, placing it at the end of a `finally` block after a native operation.

~~~java
try {
    useNativeHandle(handle);
} finally {
    java.lang.ref.Reference.reachabilityFence(owner);
}
~~~

This is an **illustrative snippet**, requiring the variables owner/handle and the method useNativeHandle to be defined in an appropriate scope. `reachabilityFence` **does not invoke GC**, does not close the resource, and does not extend the object's lifetime forever.

**Use only when the reachability reason genuinely involves native/foreign resource lifecycles.** In pure Java code using normal object references, you rarely need to call this method.

## 38. Complete Program 16 — Using a Reachability Fence Appropriately

File **`ReachabilityFenceDemo.java`**:

~~~java
import java.lang.ref.Reference;

final class HandleOwner {
    private final int handle;

    HandleOwner(int handle) {
        this.handle = handle;
    }

    int handle() {
        return handle;
    }
}

public class ReachabilityFenceDemo {
    static void useHandle(int handle) {
        System.out.println("using=" + handle);
    }

    public static void main(String[] args) {
        HandleOwner owner = new HandleOwner(7);
        int nativeHandle = owner.handle();

        try {
            useHandle(nativeHandle);
        } finally {
            Reference.reachabilityFence(owner);
        }

        System.out.println("operation complete");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ReachabilityFenceDemo.java
java ReachabilityFenceDemo
~~~

**Stdout:**

~~~text
using=7
operation complete
~~~

This code uses an int simulating a handle, so it does not manage a real native resource. The point to understand is that the `reachabilityFence(owner)` invocation at the end of `finally` keeps the referent alive at least up to that boundary; it **does not turn `System.gc` into a measurement of collection timing**.

## 39. Why Doesn't GC Automatically Solve Memory Leaks?

An object to which the program unintentionally continues holding a reference remains reachable; the collector cannot know that the **business logic** wants to discard it.

Common examples:

- `static List` or `static Map` growing indefinitely, with no limit or eviction.
- Cache only adding items without a TTL/capacity policy.
- Listener/subscriber registered but forgotten to be unregistered.
- ThreadLocal values not removed according to the request/thread pool lifecycle when needed.
- Task queues accumulating jobs when the consumer processes more slowly than the producer.
- A long-lived parent object holding a reference to the entire graph of an old request.
- A thread or executor not shut down properly and retaining task contexts.

All of these cases are **retention problems**: the collector is doing the right thing by keeping objects that are still reachable.

The solution is to **change ownership/references**: limit caches, remove entries, unregister listeners, close resources, clear ThreadLocals appropriately, shut down executors, and avoid retaining contexts for too long.

## 40. Complete Program 17 — A Static Cache Must Have Eviction/Clear

File **`RetainedCacheDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RetainedCacheDemo {
    private static final List<byte[]> CACHE = new ArrayList<>();

    static void add() {
        CACHE.add(new byte[256]);
    }

    public static void main(String[] args) {
        add();
        add();

        System.out.println("entries=" + CACHE.size());
        System.out.println("bytes per entry="
                + CACHE.get(0).length);

        CACHE.clear();
        System.out.println("after clear=" + CACHE.size());
        System.out.println("collection time unknown");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 RetainedCacheDemo.java
java RetainedCacheDemo
~~~

**Stdout:**

~~~text
entries=2
bytes per entry=256
after clear=0
collection time unknown
~~~

The static List holds references to two byte arrays. `CACHE.clear()` removes the elements from the collection, but does not promise that process memory decreases immediately. In a real application, a cache may need explicit capacity limits and eviction instead of only clearing at the end of the program.

## 41. GC and Types of `OutOfMemoryError`

GC **does not promise that every allocation will succeed**. The JVM can throw `OutOfMemoryError` when it cannot allocate sufficient memory for demand, even with automatic GC.

However:
- Not every OutOfMemoryError is "Java heap space": there may be issues in native memory, metaspace, direct buffers, thread creation, or other resource configurations.
- Do not call `System.gc()` as the sole strategy for handling OutOfMemoryError.
- Do not run a demo attempting unbounded allocation just to "prove GC will run" on a learning machine, as it can starve the JVM or system of resources.
- A single successful allocation does not prove there is no retention leak.
- Heap limits via `-Xmx` used for testing should be chosen carefully based on the workload, not a number imposed by the lesson for every machine.

When an OOME occurs, analyze the error type/message, GC logs, heap dumps, memory pools, and relevant retaining roots.

**Important boundary:** GC solves the reclamation of memory that is **no longer reachable**, rather than rescuing an application that keeps too many objects alive.

## 42. GC Logs and Observation Tools in Java 17

JDK 17 HotSpot supports **Unified JVM Logging**. You can run a program with the flag:

~~~bash
java -Xlog:gc GcRequestDemo
~~~

This is an **illustrative CLI command** after compiling `GcRequestDemo.java`, applicable to JVMs supporting this flag. GC log output depends on the system, collector, and events that actually occur; **do not put that log into a fixed expected stdout**.

Several other tools can be useful:

- **Java Flight Recorder (JFR):** analyzes events, allocations, and GC phases according to runtime/configuration capabilities.
- **`jcmd`**: diagnoses a running JVM; specific commands need to be checked against the JDK version and access permissions.
- **Heap dump + analyzer:** inspects retaining paths, the dominator tree, and long-lived object graphs.
- **JMX `GarbageCollectorMXBean`/MemoryMXBeans:** collects provided runtime metrics; does not promise a one-to-one mapping between a metric and individual collected objects.
- **Application metrics:** cache counts, pending tasks count, active sessions, threads, and connections.

**Distinguish observation from guarantee:** a log stating "a GC event occurred" does not give you the right to predict when GC will run next; an increasing GC count does not mean that a resource has been closed.

## 43. `GarbageCollectorMXBean` Does Not Give the End-of-Life Time of Individual Objects

Some JVMs provide garbage collector beans via ManagementFactory:

~~~java
java.lang.management.ManagementFactory
        .getGarbageCollectorMXBeans();
~~~

This is a valid expression snippet if placed inside a method. The beans can provide collection count/time, but the number of collectors, collector names, and metric availability **are not fixed across JVMs**.

Metrics such as count can be `-1` if unsupported; the figures are measured per collector activity, **not** "object X was freed at time Y".

Do not write a test `getCollectionCount() > 0` and conclude that a specific object has been collected. To test cleanup logic, call close/clean explicitly; to measure performance, use appropriate benchmarking and profiling methods.

## 44. Complete Program 18 — Reading Collector Bean Counts Without Assuming GC Type

File **`GcBeansDemo.java`**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;

public class GcBeansDemo {
    public static void main(String[] args) {
        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();

        System.out.println("beans collection available="
                + (beans != null));

        for (GarbageCollectorMXBean bean : beans) {
            if (bean.getCollectionCount() >= 0) {
                // Measured data depends on the runtime;
                // do not print a fixed count.
                bean.getCollectionTime();
            }
        }

        System.out.println("no GC timing promise");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GcBeansDemo.java
java GcBeansDemo
~~~

**Stdout:**

~~~text
beans collection available=true
no GC timing promise
~~~

The demo does not assume names like `G1 Young Generation` or `G1 Old Generation`, nor does it impose a collection count. Calling getCollectionCount/getCollectionTime only illustrates that metrics can be queried, and does not prove that any individual object has been collected.

## 45. Scenario: How to Diagnose "Called GC Yet Heap Remains Large"?

**Situation:** a long-running service experiences rising heap usage and increasing request latency. The team tries calling `System.gc()`, but the memory chart does not drop noticeably.

Investigation workflow:

1. Determine whether the chart represents **used heap, committed heap, resident memory, or container memory**.
2. Examine metrics over a sufficiently long time span and under a representative workload.
3. Inspect GC logs: frequency, pauses, and heap usage before/after events (if available).
4. Identify classes with unexpectedly growing instance counts.
5. Use a heap dump and analyze **retaining references**.
6. Check static caches, queues, listeners, ThreadLocals, active requests, and native memory.
7. Check whether the long-retained data is still needed.
8. Establish domain-driven retention/eviction rules instead of "periodic forced GC" commands.
9. Re-measure latency/throughput/capacity after fixing ownership.
10. If collector/heap tuning is needed, benchmark in a production-equivalent environment.

**Valid conclusion:** "we need to find the cause of retention or re-examine the type of memory metric". **Invalid conclusion:** "Java GC is broken because the chart did not drop immediately after System.gc".

## 46. Scenario: Listener Registered Without Unregistering

Suppose an application holds a long-lived EventBus, and the EventBus maintains a list of listeners. Each request creates a listener capturing a large request context and registers it with the EventBus, but never unregisters it.

~~~text
Long-lived EventBus
    |
    +-- listener 1 --> request context 1
    +-- listener 2 --> request context 2
    +-- listener 3 --> request context 3
    +-- ...
~~~

When the requests finish, the local variables of the handler method are gone, yet **the EventBus still holds the listeners**, and the listeners in turn hold the contexts. These object graphs remain strongly reachable.

GC cannot automatically remove subscriptions just because the business request has finished. The solution is lifecycle design: registration with ownership, returning a token/subscription to the caller, `unsubscribe` in finally/close, bounding the backlog, or organizing weak listeners if the contract permits (though weak listeners have semantics of unexpected callback loss).

The sealed/record/final keyword does not automatically fix this situation; it is a problem of **reference paths and ownership**.

## 47. Scenario: `ThreadLocal` in a Thread Pool

`ThreadLocal<T>` associates values with an execution thread. A thread pool reuses threads, so a value associated with request A may remain retained across the lifetime of the worker thread if not cleaned up according to the proper contract.

Common pattern:

~~~java
try {
    CONTEXT.set(requestContext);
    // perform per-request work
} finally {
    CONTEXT.remove();
}
~~~

This is an **illustrative snippet**, assuming CONTEXT is a ThreadLocal and requestContext is defined. It is not a complete program.

`remove()` ensures the code drops the value attached to the thread per the API, avoiding accidentally carrying the context into the next request. You should not expect GC to infer on its own that the request has ended and strip application data from a live thread.

A ThreadLocal key weak reference in the implementation **does not guarantee** that all values are cleaned up immediately when the key no longer has a strong reference; avoid skipping cleanup.

## 48. Complete Program 19 — Structured Use of `ThreadLocal.remove()`

File **`ThreadLocalCleanupDemo.java`**:

~~~java
public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    static void handle() {
        CONTEXT.set("request-A");

        try {
            System.out.println("inside=" + CONTEXT.get());
        } finally {
            CONTEXT.remove();
        }
    }

    public static void main(String[] args) {
        handle();
        System.out.println("after=" + CONTEXT.get());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
~~~

**Stdout:**

~~~text
inside=request-A
after=null
~~~

`remove()` is an explicit API; the null result from `CONTEXT.get()` comes from removing the ThreadLocal value, **without needing GC to run**. In a thread pool, a similar `try/finally` pattern helps manage request-scoped state more safely.

## 49. Complete Program 20 — `finally` Runs Independently of GC

File **`FinallyCleanupDemo.java`**:

~~~java
public class FinallyCleanupDemo {
    static void runTask() {
        try {
            System.out.println("work");
            throw new IllegalStateException("failed");
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        try {
            runTask();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FinallyCleanupDemo.java
java FinallyCleanupDemo
~~~

**Stdout:**

~~~text
work
cleanup
caught=failed
~~~

`finally` is a language-defined control mechanism, not a GC callback. For resources implementing `AutoCloseable`, prefer `try-with-resources` so the code calls `close` automatically; for cleanup not covered by AutoCloseable, `finally` still has value.

Not all abnormal JVM/process termination cases allow finally or close to run; if data durability is needed, you must also account for crashes and transactional semantics.

## 50. Do Not Use `Thread.sleep` to Test GC

A common "GC test":

~~~java
Object object = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(object);
object = null;

System.gc();
Thread.sleep(1000);

// NO GUARANTEE that weak.get() == null here.
~~~

This is an illustrative snippet, which needs to be inside a method that handles/declares InterruptedException if run. It is **not a valid test with a stable result**.

Waiting only creates a thread delay, not a time limit forcing the collector to process that object. The GC schedule is part of the implementation and can be affected by heap size, collector flags, system load, or references kept by the program that the test author overlooked.

To test cleanup, **call the cleanup API directly** and verify postconditions. To observe GC, use logs/metrics with statistical interpretation, not an assertion that "an object must die within 1 second".

## 51. Common Misconceptions

| Misconception | Reality in Java 17 |
| --- | --- |
| Assigning `obj=null` immediately frees the object | Only changes one reference; the object may still be reachable or not yet reclaimed by GC |
| Exiting a method means heap memory is freed immediately | There is no GC timing guarantee |
| GC relies solely on reference counting | The reachability graph matters; cycles can be collectible |
| If there is an A↔B cycle, the JVM cannot collect them | Cycles do not by themselves make objects reachable from roots |
| `System.gc()` forces a synchronous full GC | It is only a suggestion for GC effort per the API |
| After `System.gc()`, WeakReference is guaranteed to be null | Not guaranteed |
| `WeakReference.get()==null` always proves GC just ran | `clear()` may have been called explicitly |
| SoftReference is a cache with predictable capacity | Clearing/retention policy is not a TTL/size contract |
| PhantomReference can be used to get an object | `get()` is always null |
| `ReferenceQueue` always notifies before JVM exit | There is no such timing guarantee |
| WeakHashMap automatically removes an entry as soon as the local key is null | GC/queue processing does not occur at a fixed point in time |
| GC will close a file when the object goes out of scope | Use explicit close/try-with-resources |
| Finalizers always run before the program exits | No; finalization is deprecated and unreliable |
| Cleaner is a replacement for timely `close()` | Automatic Cleaner execution still depends on reachability/scheduling |
| `reachabilityFence` invokes GC | No; it keeps the referent reachable up to a specific point |
| Process RAM not decreasing means GC did not free memory | Used/committed/native memory are different |
| Java has GC so memory leaks are impossible | Retained references can still cause leaks |
| `OutOfMemoryError` proves the collector is broken | It can be caused by memory pressure, retention, limits, or other pools |
| A static cache holding objects indefinitely will still be cleaned up by GC | GC does not discard objects that are still reachable |
| ThreadLocal values automatically disappear when the request finishes | Thread pools retain threads; proper lifecycle/remove is needed |
| GC event count determines the lifetime of individual objects | GC metrics provide no such guarantee |

## 52. Design and Code Review Checklist

- [ ] Have you distinguished between an object no longer being reachable and actual garbage collection?
- [ ] Have you avoided claiming that GC runs immediately when a variable goes out of scope/is assigned null?
- [ ] Have you checked aliases, static fields, collections, and event listeners holding references?
- [ ] When seeing an object graph with cycles, have you analyzed roots instead of just counting edges?
- [ ] Do you understand strong, soft, weak, and phantom references at the required level?
- [ ] Have you avoided using `System.gc()` to guarantee an object is collected?
- [ ] Have you avoided asserting that a weak ref is cleared after `Thread.sleep`?
- [ ] Have you separated file/socket/database lifecycles from heap GC?
- [ ] For AutoCloseable, have you used try-with-resources in the right places?
- [ ] Have you handled suppressed exceptions when both body and close fail?
- [ ] Are you avoiding relying on `finalize()` to close resources?
- [ ] If using Cleaner, does the action avoid strongly capturing the referent?
- [ ] Is Cleaner used as a fallback rather than the primary resource-closing mechanism?
- [ ] Are you using `reachabilityFence` only when needed to protect native resource lifetimes?
- [ ] If using WeakHashMap, have you considered value→key strong references and timing?
- [ ] Do long-lived caches have an eviction/size/TTL policy?
- [ ] Are listeners/subscriptions unregistered according to their lifecycle?
- [ ] Are ThreadLocal values removed at the exact end of the request?
- [ ] Have you distinguished heap used, heap committed, and process resident memory?
- [ ] Are you collecting metrics/logs instead of predicting the GC schedule?
- [ ] Have you avoided printing fixed heap bytes/GC counts in expected stdout?
- [ ] Have you analyzed retained paths before "tuning GC"?
- [ ] If `OutOfMemoryError` occurs, have you identified the type of memory pressure?
- [ ] Do tests verify explicit cleanup logic without depending on GC timing?
- [ ] Do you understand that GC does not equate to immutability, closing, or security?

## 53. Practice Exercises

**Question 1.** Does setting a reference variable to null mean the object has been reclaimed by GC?

**Question 2.** If a List still stores a reference to an object, does setting another local variable to null make the object unreachable?

**Question 3.** Two objects A and B only point to each other, with no path remaining from roots. Does the reference cycle prevent GC from handling them?

**Question 4.** Does calling `System.gc()` guarantee that a full GC will run and finish before returning?

**Question 5.** Why might process RSS still be high after a GC event?

**Question 6.** When can `WeakReference.get()` return null?

**Question 7.** Does calling `WeakReference.clear()` and seeing get return null prove that GC ran?

**Question 8.** Is `SoftReference` suitable to replace a cache that must hold at most 1,000 entries with a fixed TTL?

**Question 9.** Can `PhantomReference.get()` return the referent object?

**Question 10.** Does `ReferenceQueue.poll()` returning null mean the JVM has never run GC?

**Question 11.** Why does using `WeakHashMap` not guarantee that entries disappear immediately after the caller drops the local key?

**Question 12.** If a Map value points back to the key via a strong reference, what can happen to the weak key?

**Question 13.** Should a FileInputStream be closed via GC/finalizer or try-with-resources?

**Question 14.** In what order do two AutoCloseable resources A then B in the same try header close?

**Question 15.** If the try body throws an exception and close also throws, which exception is normally the primary?

**Question 16.** Is `finalize()` guaranteed to be called before process exit?

**Question 17.** Does `Cleaner.register` guarantee the action will run automatically within 100 ms after the referent becomes unreachable?

**Question 18.** Why should a Cleaner action not capture a strong reference to the object being tracked?

**Question 19.** How does calling `Cleanable.clean()` directly differ from waiting for the Cleaner automatically?

**Question 20.** What effect does `Reference.reachabilityFence(owner)` have?

**Question 21.** Can a static cache without eviction cause a Java memory leak?

**Question 22.** Why does `ThreadLocal` require separate cleanup in a thread pool?

**Question 23.** Is `Runtime.totalMemory()` the number of bytes of a collected object?

**Question 24.** Does a GC log recording a collection event prove that a socket has closed?

**Question 25.** Should `Thread.sleep(1000)` be used to wait until a `WeakReference` is guaranteed to be cleared?

**Question 26.** If a program throws `OutOfMemoryError`, is it accurate to immediately conclude "GC is broken"?

**Question 27.** Does `List.clear()` returning guarantee that heap memory has been returned to the operating system?

**Question 28.** Distinguish used heap, committed heap, and native resource lifetime.

**Question 29.** In the GcRequestDemo demo, what does the line "GC request returned" confirm?

**Question 30.** In the CleanerDemo demo, why is `cleanup calls=1` not evidence of GC?

**Question 31.** For an event listener holding a request context, what is the proactive lifecycle solution?

**Question 32.** When should heap dump/retaining path analysis be used?

### Answers and Explanations

1. No; the disappearance of one reference does not guarantee actual GC.
2. No; the List still has a strong reference to the object.
3. No; a graph cycle can be collectible when it is not reachable from roots.
4. No; System.gc is a suggestion, promising neither a specific object nor a full GC.
5. The JVM may retain committed heap, the process also has native memory, and metrics belong to different layers.
6. When the weak referent is cleared during reference processing or the caller calls clear.
7. No; calling clear explicitly produces the null result.
8. No. TTL/capacity requires an explicit cache policy; soft clearing has no predictable schedule.
9. No; PhantomReference's get is always null.
10. No; the queue may be empty due to processing timing or no reference event yet.
11. Because clearing/enqueuing depends on GC and map processing, not on local scope.
12. The value can keep the key strongly alive, causing the entry to persist unintentionally long.
13. Try-with-resources or explicit close per the API.
14. B closes first, then A.
15. The exception from the body is primary; the exception from close is suppressed according to the rules.
16. No; finalization has no timing guarantee and is not recommended.
17. No; automatic cleaning is not guaranteed within such a deadline.
18. A strong capture can keep the referent reachable, preventing automatic cleanup.
19. Clean() is an explicit call that can run the action synchronously, without needing GC.
20. Keeps the referent strongly reachable at least up to the fence invocation.
21. Yes; objects remain reachable via the cache even though the business logic no longer needs them.
22. Threads are reused and can continue holding request-scoped values.
23. No; it is a JVM heap metric, not stating that a specific object was freed.
24. No; GC does not manage socket lifecycles in a timely manner.
25. No; sleep only delays the thread, it does not force GC.
26. No; you need to identify the OOME subtype, limits, allocations, and retention.
27. No; clear changes the List state, without promising the JVM returns heap to the OS.
28. Used heap is memory currently in use within the heap; committed is the portion of heap committed by the JVM; native resources have independent lifecycles.
29. It only confirms that `System.gc()` returned from that call.
30. Because cleanable.clean was called directly, not relying on GC.
31. Unregister the listener, clear strong references, and manage the subscription lifetime.
32. When there is an abnormal retention/memory trend and you need to find object holders and paths from roots.

## 54. Design Case: From Flawed Code to Correct Code

**Risky code:**

~~~java
class FileWorker {
    void process(java.nio.file.Path path)
            throws java.io.IOException {
        java.io.InputStream stream =
                java.nio.file.Files.newInputStream(path);
        // read stream...
        // do not call close; expecting GC to clean up.
    }
}
~~~

This is an **illustrative snippet, not the proper way to manage resources**. If an exception occurs or the method returns, the file descriptor may not be released on time. A developer cannot prove that the stream will be collected right when the method ends.

**Code with clear ownership:**

~~~java
class FileWorker {
    void process(java.nio.file.Path path)
            throws java.io.IOException {
        try (java.io.InputStream stream =
                     java.nio.file.Files.newInputStream(path)) {
            int firstByte = stream.read();
            System.out.println("first byte=" + firstByte);
        }
    }
}
~~~

This is a **valid class snippet**, without a main method and requiring an actual file path to run. The stream is closed upon exiting try-with-resources whether reading succeeds or fails. The value of firstByte depends on file contents, so **no fixed stdout is provided** for this snippet.

**Essence of the improvement:** cleanup is tied to **control flow and ownership** instead of depending on the GC schedule. That is the kind of guarantee application code can rely on.

## 55. Testing Practices That Do Not Rely on GC

Write tests according to these principles:

- Test that `close()` is called after try-with-resources using a fake resource/counter.
- Test explicit close order with multiple resources.
- Test suppressed exception count/message when close fails.
- Test cache eviction via `remove`, `clear`, or an expiration API with a controllable mechanism.
- Test the `ReferenceQueue` consumer using manual enqueue where appropriate.
- Test that `Cleanable.clean()` runs exactly once, without waiting for the cleaner thread.
- Test that `WeakReference.clear()` returns null due to an explicit call; do not use it as collector proof.
- Use JFR/GC logs/heap dumps to **observe** GC, without requiring fixed log output across environments.
- Do not include collector names, allocation bytes, or GC counts in the expected stdout of basic examples.

If you must write an integration test involving actual GC, accept that it may be non-deterministic, use specialized instrumentation, and do not base application correctness on short timeouts. "The test ran today" does not turn GC timing into a JVM guarantee.

## 56. Official Java 17 Documentation

- [JLS 17 §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): object initialization, construction.
- [JLS 17 §12.6 — Finalization of Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6): historical finalization semantics and reachability.
- [Java SE 17 — `System.gc()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()): GC suggestion, no timing guarantee.
- [Java SE 17 — `Runtime.gc()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#gc()): explicit GC request.
- [Java SE 17 — `Runtime.freeMemory()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#freeMemory()): heap metrics sample.
- [Java SE 17 — `Runtime.totalMemory()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#totalMemory()): total available JVM memory.
- [Java SE 17 — `Reference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): reference objects, `clear`, `enqueue`, `reachabilityFence`.
- [Java SE 17 — `WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weakly reachable objects.
- [Java SE 17 — `SoftReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/SoftReference.html): softly reachable objects.
- [Java SE 17 — `PhantomReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html): phantom references with get always returning null.
- [Java SE 17 — `ReferenceQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html): reference processing notifications.
- [Java SE 17 — `WeakHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys and map lifetime notes.
- [Java SE 17 — `Cleaner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): cleanup registration.
- [Java SE 17 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): resource close contract.
- [JLS 17 §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): automatic close and suppressed exceptions.
- [Java SE 17 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): GC monitoring information.
- [Java SE 17 — `ManagementFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): querying MXBeans.
- [Java SE 17 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): request/thread-scoped values.
- [Java SE 17 — `OutOfMemoryError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html): resource allocation failure scenarios.
- [JDK 17 Tools — Unified JVM Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): GC logging configuration.

## 57. Summary

**Java has automatic garbage collection**: the JVM can reclaim the memory of objects that are no longer reachable according to runtime rules. However, **there is no guaranteed point in time at which an object will be collected** immediately after a local variable becomes null, a method finishes, or `System.gc()` returns. "Eligible for collection" is an assessment of reachability; "has been collected" is a runtime event that cannot be inferred from source code alone.

A correct Java application must decide for itself the tasks that **cannot wait for GC**: closing streams/sockets/DB resources with `try-with-resources`, canceling subscriptions, bounding caches, cleaning up ThreadLocal values, and managing the lifecycle of native handles. Weak/soft/phantom references, Cleaner, and GC monitoring tools are useful when their contracts are clearly understood, yet they do not turn garbage collection into a cleanup mechanism with a deadline.

**Closing rule:** let GC manage memory reclamation, and let **API ownership along with program control flow** manage resources that must finish on time. When testing, rely on what Java guarantees — not on collector scheduling that can vary across environments.
