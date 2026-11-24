# 12.7 GC Roots, Reference Chains, and How Objects Are Retained

## Lesson Objectives

After this lesson, you will be able to:

1. Explain what a **GC root** is and why a path from a root to an object prevents it from being reclaimed.
2. Read a **reference chain** from a class/static field, thread, local variable, JNI handle, or intermediate object to a suspect retained object.
3. Distinguish **reachable**, **strongly reachable**, weak reference types, and **eligible for GC**; understand why an object no longer useful to business logic can still remain alive.
4. Use **Paths to GC Roots**, **Dominator Tree**, and **retained size** in Eclipse Memory Analyzer (MAT) to locate memory-retaining objects without jumping to false conclusions from a single shortest path.
5. Recognize common culprits such as unbounded caches, unregistered listeners, uncleaned `ThreadLocal` values, backlogged queues, and pinned class loaders.

Core takeaway: **Java GC automatically reclaims objects that are no longer reachable under reachability rules; GC cannot know on its own that a reachable object has lost its business value.** Thus, Java memory leaks are usually **logical leaks**: reference paths continue keeping objects alive beyond their intended lifecycle.

## 1. What Is a GC Root?

When identifying live objects, the JVM's garbage collector starts from a set of **GC roots**: entry points considered actively in use or mandatory to maintain by the runtime. From there, GC follows eligible reference edges to find reachable objects. An object with a **strong** reference path from a root is normally kept alive. If no qualifying retention path remains, the object becomes eligible for collection under GC mechanics.

Common root categories in HotSpot Java and heap-analysis tools:

| Root group | Typical context | Traces commonly seen during analysis |
| --- | --- | --- |
| Thread/stack | Live references in local variables, parameters, or active frames; info about active threads | Thread, Java local, stack frame |
| Class and static state | Live classes and static fields pointing to objects; reachability tied to class/class loader lifecycle | System Class, class object, static field |
| JNI | Native code holding a **JNI global reference** or an active local reference | JNI Global, JNI Local |
| Runtime-internal | Special objects the JVM must retain during execution, such as thread-associated or runtime structures | Root type depends on JVM, version, and dump format |

**There is no fixed, universal list of GC root labels across every JVM, collector, and heap dump.** Root labels in MAT reflect how it interprets dump metadata. Do not treat every tool-specific label as a universal rule across all VMs.

A static field **is not by itself the complete answer** to object lifetime: check whether the class stays alive, whether its class loader can unload, and whether any root keeps that class loader pinned. In long-running apps, static caches typically live as long as their class loader; in plugin/redeploy architectures, an old class loader itself can be kept alive by a thread, `ThreadLocal`, or callback.

## 2. Reference Chains: Why Does an Object Stay Reachable?

Picture Java objects as **vertices** in a directed graph and each reference field or array slot as a **directed edge**.

~~~text
GC ROOT (live class)
    |
    | static CACHE
    v
CacheRegistry
    |
    | entries
    v
HashMap
    |
    | table / entry / value  (actual path depends on JDK)
    v
CachedResponse
    |
    | payload
    v
byte[] (large data)
~~~

This is a **conceptual illustration**, not mandatory internal field names across every JDK release. Each edge states that the preceding object holds a reference to the next. As long as one valid retention path exists from a GC root to the byte array, GC cannot reclaim the array as garbage.

Reading a path from bottom to top:

- **Target object**: the byte array occupying heap space.
- **Direct holder**: `CachedResponse.payload`.
- **Container**: entry/value inside the cache `Map`.
- **Long-lived anchor**: Registry referenced via a static field.
- **GC root**: class/class loader state or a corresponding runtime root.

A path answers **"what is keeping this object reachable at capture time?"** It does not yet answer **"is this a memory leak?"** A bounded cache with valid expiration policies can still show an entirely intentional retention path.

### Having a reference does not always mean strong retention

Not all edges carry the same semantics. Java provides **strong, soft, weak, and phantom references**. When speaking of "a path from a GC root" in standard leak investigations, what matters most is a **strong reference path**, or at least understanding the reachability level per reference type. A path passing solely through the referent of a `WeakReference` does not block GC from reclaiming that referent the way a strong reference does.

## 3. Reachability Levels and When an Object Can Be Reclaimed

### Strong reference

Normal assignments, collection elements, or object fields typically create strong references:

~~~java
byte[] payload = new byte[1024];
List<byte[]> list = new ArrayList<>();
list.add(payload);
payload = null;
~~~

*This is an illustrative snippet inside a method with `java.util.List` and `java.util.ArrayList` imported, not a standalone program.* After `payload` is set to `null`, **`list` still holds a strong reference** to the array. Clearing **one variable** does not mean the object has become unreachable.

Also note: **local variables do not mechanically keep objects alive for their entire syntactic scope**. The JVM/JIT can determine last use and optimize liveness; the compiler may retain or clear a reference from a stack slot at a GC safepoint. When relying on thread-stack roots from a heap dump, treat them as the actual runtime state recorded at capture time rather than deducing liveness strictly from curly braces in source code.

### SoftReference

An object reachable only via a **SoftReference** may be kept temporarily by the VM and reclaimed based on memory policy/pressure. Soft references can aid memory-sensitive caches, yet **they do not replace capacity bounds, TTL, or eviction policies**. When a referent gets cleared is non-deterministic from the application's perspective.

### WeakReference

When an object is only weakly reachable, GC can clear the `WeakReference` and reclaim its referent; the `WeakReference` instance itself may still remain alive as an independent object. **A `WeakReference` does not weaken a strong reference held elsewhere.**

~~~java
WeakReference<Object> weak = new WeakReference<>(new Object());
// After an appropriate GC, weak.get() may become null.
// Do not call System.gc() and assume weak.get() == null is guaranteed.
~~~

*This illustrative snippet requires `java.lang.ref.WeakReference` and carries no guarantee on GC timing.*

### PhantomReference

**PhantomReference** supports post-mortem notification/cleanup via a `ReferenceQueue`; its `get()` method always returns `null`. It cannot be used like a strong reference to retrieve the referent, nor does it guarantee immediate reclamation. For resources that must close promptly, prefer **`try-with-resources`/`close()`** instead of waiting for GC.

### Diagnostic table

| State from an analysis perspective | Correct conclusion |
| --- | --- |
| At least one **strong** path from root to object | Object remains strongly reachable; GC cannot treat it as garbage |
| Only paths passing through a `WeakReference` referent | Can become weakly reachable and processed by GC; weak edges do not retain like strong edges |
| Only soft references remain | VM may keep temporarily or clear based on conditions; do not assume fixed collection timing |
| No meaningful reachability path remains | Object may be eligible for reclamation, with no guarantee it has already been freed immediately |
| Multiple independent strong paths exist | Dropping one reference is usually **not enough** to free the object |

Depending on reference types and processing order, **"no strong path"** is not always synonymous with **"already freed."** In a heap dump captured with unreachable objects included, you may still see objects awaiting cleanup on a later GC pass.

## 4. An Object Can Be Held by Multiple Paths Simultaneously

Suppose a `Response` is held by both a cache and a background task:

~~~text
        GC Root: class                   GC Root: worker thread
              |                                    |
              v                                    v
       static CACHE                         running task
              |                                    |
              v                                    v
            Map                               queue/item
              |                                    |
              +-------------> Response <------------+
                                   |
                                   v
                                byte[]
~~~

If you only run **`CACHE.remove(key)`** while the worker still holds `Response`, the `byte[]` remains reachable. Conversely, if the task finishes but the cache never evicts, the object stays alive. Concluding "the leak is fixed" requires checking **all significant retention paths** and the business lifecycle.

### Reference cycles do not automatically cause leaks

~~~text
 A -> B
 ^    |
 |____|
~~~

If **no GC root reaches A or B**, this cycle can still be reclaimed by tracing GC. Modern garbage collectors do not rely solely on naive reference counting. Thus "there is a cycle" is **insufficient** to prove a leak; what matters is **reachability from roots** under the GC model.

### Reachable is different from still needed

For instance, a user logs out, yet their old `HttpSession` remains inside a `Map` without expiration; the object stays strongly reachable even though business logic no longer needs it. The bug lies in **ownership/lifecycle policy**, not GC "forgetting" to collect.

## 5. Paths to GC Roots and Dominator Tree Answer Different Questions

### Paths to GC Roots: who is keeping the object alive?

In **Eclipse Memory Analyzer (MAT)**, select a suspect object and run **Path to GC Roots** or **Path to GC Roots → exclude weak/soft references** depending on the UI version. The tool walks **backward** from the object up through referencing objects until reaching a root. A concrete path might look like:

~~~text
byte[] payload
 <- CachedResponse.payload
 <- Map entry.value
 <- CacheRegistry.responses
 <- GcRootDemo.REGISTRY (static)
 <- associated class / root
~~~

Actual step names and depth vary by JVM, JDK, collection implementation, and chosen path.

- **Shortest path** is the path with the fewest edges in the analyzed graph; it does not mean it is the only path or the primary root cause to fix.
- **All paths** can be vast and expensive to compute. Filter or limit when needed; if you inspect only one path, never assume other paths do not exist.
- **Exclude weak/soft/phantom references** (depending on MAT query options) focuses on typical strong retention relationships. Understand query settings so you never misread a weak edge as preventing GC.
- Inspect the **field names** along each edge. A path to a root through a `List` or `Map` may be normal or buggy depending on who owns the data and when it ought to be removed.

### Dominator Tree: which object controls retained memory?

MAT builds a **dominator tree** derived from the reference graph. Object **X dominates Y** if **every path** from the graph's (super-)root to Y passes through X. Removing X from the retention graph makes Y unreachable under that model.

X's **retained set** comprises all objects X dominates; **retained size** is the sum of their shallow sizes (as computed by the tool). This metric helps pinpoint anchors retaining the largest volumes of data.

An illustrative case:

~~~text
Root -> CacheHolder -> Object A -> byte[]  (20 MB)
                  \-> Object B -> byte[]  (30 MB)
~~~

If **every path** to both arrays passes through `CacheHolder`, `CacheHolder`'s retained size can approach 50 MB plus object overhead, even if **`CacheHolder`'s shallow size is tiny**.

If one array also has another root path through a queue, `CacheHolder` **no longer dominates that array**, so `CacheHolder`'s retained size drops—even though the cache **still directly references that array**.

**Edges in the dominator tree are not necessarily real Java reference fields.** To see which fields or collections form the references, return to **Paths to GC Roots** or inspect incoming/outgoing references. Do not mistake an "immediate dominator" edge for a literal field in source code.

### Comparing the two operations

| Operation | Answers | Common misconception |
| --- | --- | --- |
| Paths to GC Roots | Through which root → ... → object chain is the object kept alive? | One path does not represent all paths |
| Merge Shortest Paths to GC Roots | Which common root/owner do many suspect objects share? | Shortest path may overlook other paths |
| Dominator Tree | Which object exclusively retains large object subgraphs? | Dominator edges are not necessarily direct references |
| Histogram | Which classes have high instance counts / shallow bytes? | Does not reveal owners/roots or measure retained size |
| Leak Suspects | Object groups worth inspecting first by heuristics | A hypothesis requiring business-lifecycle verification |

## 6. Runnable Example: Static Listener Registry Retaining Objects After Local Reference Is Cleared

The program below stores a listener in a **static `List`**. The listener owns a 1 MiB byte array. The local variable **`listener`** is set to `null`, yet the object cannot be collected because the registry still holds it. A **`WeakReference`** observes reachability while a strong reference exists, without increasing retention.

Save as **GcRootDemo.java**:

~~~java
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.List;

public final class GcRootDemo {
    private static final List<Listener> REGISTRY = new ArrayList<>();

    private static final class Listener {
        private final String id;
        private final byte[] payload;

        private Listener(String id) {
            this.id = id;
            this.payload = new byte[1024 * 1024];
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Listener listener = new Listener("payment-events");
        REGISTRY.add(listener);

        WeakReference<Listener> observation = new WeakReference<>(listener);
        listener = null;

        System.out.println("Registry size: " + REGISTRY.size());
        System.out.println("Weak referent present: " + (observation.get() != null));

        // Keep the process running long enough to capture a heap dump.
        Thread.sleep(180_000L);

        REGISTRY.clear();
        System.out.println("Registry after clear: " + REGISTRY.size());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac GcRootDemo.java
java -Xmx128m GcRootDemo
~~~

Guaranteed output before sleeping:

~~~text
Registry size: 1
Weak referent present: true
~~~

After about three minutes (if left running), it continues with:

~~~text
Registry after clear: 0
~~~

When the second line prints, **`REGISTRY.get(0)`** is still a strong reference, so `WeakReference.get()` is guaranteed non-null. Do not interpret this snippet as promising `WeakReference.get()` **will** immediately become `null` right after `REGISTRY.clear()`; GC does not run on a fixed schedule, and other local/JIT roots may remain.

### Capture the heap and trace the root path

While the program is sleeping, open a second terminal:

~~~bash
jcmd -l
jcmd <PID> GC.heap_dump heap-root-demo.hprof
~~~

Replace **PID** with the process ID from the first command; omit the angle brackets. On HotSpot, standard **GC.heap_dump** requests a Full GC before creating the file unless **-all** is used. This is an expensive operation, so run the example only on a test JVM.

Open **heap-root-demo.hprof** in MAT:

1. Open **Histogram** and filter for **GcRootDemo$Listener** or the associated byte array.
2. Select the `Listener` instance and open **Path to GC Roots**, preferring the option to exclude weak/soft references when investigating strong retention.
3. Locate a reference chain along the lines of: class **GcRootDemo** → static **REGISTRY** → `ArrayList` backing array → `Listener` → `payload` `byte[]`. Exact node names may differ.
4. Open **Dominator Tree** and check the retained size of the listener/registry or related owner. Check whether paths to the array exist via any other owner.
5. Compare with design intent: should the listener stay registered long-term, or should it **unregister** when no longer needed?

**Takeaway evidence:** assigning `null` to a local variable **does not remove** a strong reference stored in a collection. Once the application clears the registry and no other strong path remains, the object becomes eligible for collection; actual reclamation depends on GC.

> Watch field names in snapshots carefully: many collections and JVM optimizations change internal structure across releases. Always inspect the reference edges reported by the tool rather than writing out an "exact" path from memory of source code.

## 7. Five Unintended Retention Patterns to Recognize

### 7.1 Unbounded static cache

~~~text
GC root → live class → static cache → Map entry → expired object
~~~

Symptoms: entry counts and retained heap grow with request volume and fail to drop when load returns to normal. Fix: **bounded cache, TTL, eviction, lifecycle-driven invalidation**; also check whether cached keys retain large values or contexts. Do not merely try to trigger GC more often.

### 7.2 Unregistered listener/callback

~~~text
Root → long-lived event bus → listeners → callback → captured service/context
~~~

Symptoms: a component is closed yet its listener remains in the event bus. Fix: track a **subscription/registration token** and unregister upon component teardown. Lambdas can capture enclosing variables, extending the owner's lifetime unexpectedly.

### 7.3 `ThreadLocal` on a thread pool

~~~text
Root → long-lived worker thread → ThreadLocalMap → value → request/session data
~~~

Thread pools reuse threads, so values can outlive individual requests. Even if a `ThreadLocal` key is GC'd, **the old value can linger in the map** until stale entries are expunged; do not treat that as a deterministic cleanup mechanism.

Safe usage pattern when each task owns its data:

~~~java
private static final ThreadLocal<byte[]> BUFFER = new ThreadLocal<>();

static void doWork() {
    try {
        BUFFER.set(new byte[64 * 1024]);
        // Process the current task.
    } finally {
        BUFFER.remove();
    }
}
~~~

*This illustrative snippet shows two members placed inside a class; it is not a standalone Java program.* In thread pools, **`finally` + `remove()`** is essential. Clearing the key reference from an application variable does not guarantee the value disappears immediately.

### 7.4 Backlogged queue/executor

~~~text
Root → Executor / scheduler → queue → pending Runnable → captured payload
~~~

Symptoms: queued job count rises and the queue holds large request buffers. These objects are valid in the reference graph, yet reflect a **backlog** or an unbounded queue design. Add backpressure, bounded queues, timeouts, task cancellation, and queue-depth monitoring.

### 7.5 Class loaders and JNI global references

- **Old class loaders** can be pinned by threads, context class loaders, static registries, listeners, or parent-layer `ThreadLocal`s; classes and data tied to the loader cannot unload after redeploys. Do not assume "dropping the module reference" suffices if a strong root path still reaches the loader.
- **JNI global references** from native code also keep Java objects alive; native code must call **`DeleteGlobalRef`** at the proper lifecycle point. **JNI weak global references** have weaker semantics and do not behave like strong global references.
- A heap dump may only show a JNI or class loader root without explaining native-side ownership; correlate with native/JNI code and runtime behavior before concluding.

## 8. Step-by-Step Investigation Workflow to Avoid Hasty Conclusions

### Step 1. Confirm the true symptom

Observe **post-GC used heap across comparable GCs**, load levels, allocation rate, and object counts over time. Heap rising between GCs is normal. A leak is suspect when post-GC data or retained sets climb persistently even after objects should have ended their lifecycle.

### Step 2. Capture qualifying data

On HotSpot JDKs supporting `jcmd`:

~~~bash
jcmd -l
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump /path/to/app.hprof
~~~

- **Histogram** narrows down abnormally growing classes.
- **HPROF heap dump** captures the point-in-time object graph for MAT to analyze root paths, dominators, and retained size.
- **`GC.heap_dump -all`** can include unreachable objects and **does not request a Full GC before dumping**. Never mix `-all` and default dumps and call the difference a leak.
- Dumping can cause pauses, consume resources and disk, and contain sensitive data like tokens, payloads, or strings. Collect and share strictly under production security policies.

### Step 3. Select suspect objects properly

In MAT, start with **Overview → Histogram, Dominator Tree, Top Consumers, or Leak Suspects**. Look for application classes, high retained sizes, abnormal instance counts, and long-lived owners. One giant object is not necessarily the root culprit if it is legitimately retained.

### Step 4. Trace reference chains up to GC roots

Walk from the **target object** up through owners in **Paths to GC Roots**. Note:
- Root type and root lifetime (thread, class/static, JNI).
- Fields or collections forming the **reference edges**.
- Whether weak/soft/phantom edges were excluded during the query.
- How many independent strong retention paths exist; if one is cut, do others remain?

When many objects are retained together, use **Merge Shortest Paths to GC Roots** to locate a common owner/accumulation point, then verify via incoming references. Do not assume the shortest path is the only path.

### Step 5. Check dominators and retained size

If an owner dominates many objects, retained size shows how much heap becomes unreachable if that owner is removed from the retention graph. Conversely, an owner with small retained size may still reference many objects **shared** with other owners.

### Step 6. Map back to business lifecycle

Ask specifically:

- When is the object created, and how long is its contract?
- Who registers or inserts it into the `Map`, `List`, queue, or `ThreadLocal`?
- Which step is responsible for calling `remove`, `evict`, `unregister`, or `close`?
- Could entries persist forever due to failed cancellation or retry paths?
- Has a request/job ended while the object stays held for another legitimate activity?

After fixing, re-measure under representative traffic and comparable captures. **Never conclude from a single snapshot** or solely from `System.gc()`; verify both the retained graph and growth trend.

## 9. Common Reasoning Traps

1. **"Setting a local variable to `null` frees the object."** False when a `List`, static field, thread, callback, or JNI still holds a strong reference.
2. **"A reference cycle means a leak."** False: cycles unreachable from roots can still be reclaimed by tracing GC.
3. **"The shortest path is the only leak root."** False: an object can be retained by multiple independent roots/owners.
4. **"Every edge shown in a dump is a strong reference."** False: weak, soft, phantom, and special links must be interpreted per reachability semantics.
5. **"Retained size is the sum of shallow sizes of all objects reachable from an owner."** False when objects are also held via other paths and are not dominated by that owner.
6. **"Edges in the Dominator Tree are direct reference fields."** False: the dominator tree is a graph-analysis construct, not a literal copy of Java object fields.
7. **"A static field always leaks and is never freed."** False: examine class/class loader lifecycle and data need; static is not automatically a bug.
8. **"No root path in a dump means the object was already GC'd."** Not necessarily: the analyzer may filter edges/limit paths, `-all` dumps contain unreachables, and dump time differs from collection time.
9. **"Just wrap everything in `WeakReference` to fix leaks."** False: if a strong path still exists, `WeakReference` changes nothing about retention; changing reference types must also respect application contracts.
10. **"A reachable object is a needed object."** False: GC knows nothing about TTL, business logic, or listeners that should have unregistered.

## 10. Self-Check

**Scenario 1:** a service holds 200 MB of data in a static `Map`, calls the session-end method, yet omits removing the `Map` entry. Why doesn't GC clean it up?  
**Answer:** class/static → `Map` → entry → data remains a strong reference chain from a root. Remove/evict entries per lifecycle and verify no other strong path remains.

**Scenario 2:** two independent static `Map`s both hold the same 30 MB `byte[]`. Is clearing one `Map` enough?  
**Answer:** no; the path from the remaining `Map` still keeps the object reachable. Dominator/retained size of either `Map` alone may exclude the array because it is shared.

**Scenario 3:** A points to B and B points to A, but neither is reachable from any GC root. Do they leak just because of the cycle?  
**Answer:** no. Tracing GC can reclaim the entire cycle.

**Scenario 4:** MAT shows a path to an object only through a `WeakReference`. Can you conclude the object will stay alive forever?  
**Answer:** no. Check for other strong paths and note whether weak references were excluded in the query; weak edges do not retain referents like strong edges.

**Scenario 5:** an owner has outgoing references to 100 MB of data, yet its retained size is only 4 MB. Is that a contradiction?  
**Answer:** no. Many referenced objects may also be kept alive through other owners; retained size measures only what is dominated.

## References

- [Oracle Java SE 21 — `java.lang.ref` package: reachability levels and Reference Objects](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/package-summary.html)
- [Oracle JDK 21 — `jcmd`: `GC.heap_dump`, `GC.class_histogram`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — Diagnostic Tools: collecting heap dumps and histograms](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [Eclipse MAT — Basic Tutorial: Dominator Tree and Path to GC Roots](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html)
- [Eclipse MAT — Path to GC Roots](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/path_to_gc_roots.html)
- [Eclipse MAT — Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html)
- [Eclipse MAT — Merge Shortest Paths](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/merge_shortest_paths.html)
