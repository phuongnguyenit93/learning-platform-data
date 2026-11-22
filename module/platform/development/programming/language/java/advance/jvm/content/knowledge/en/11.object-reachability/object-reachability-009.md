# `System.gc()` Is a Hint Request and Its Limitations When Used for Verification

In Java, `System.gc()` **is not a command that guarantees immediate object reclamation**. It is a request/hint to the JVM to expend effort toward garbage collection. Whether and when the JVM actually runs a collector, which type of collection it runs, whether a specific object has been processed, how much memory has been freed, and whether pages are returned to the operating system are all **not guaranteed by a `System.gc()` call**.

This lesson belongs to the topic of **reachability**: to understand whether an object can be garbage collected, you must first examine the reference paths from **GC roots**. Making an explicit GC request is an entirely different event from an object losing its strong references. Do not use `System.gc()` as a substitute for analyzing root paths, verifying that a resource has been `close()`d, or writing assertions that depend on GC timing.

## 1. What Does `System.gc()` Mean Exactly?

```java
System.gc();
```

This is a `void` static method on `java.lang.System` that takes no arguments. According to the Java SE API, calling it **suggests that the JVM expend effort toward recycling unused objects in order to make the memory they occupy available for reuse**. How the JVM responds is a runtime decision.

In terms of API semantics, it is equivalent to calling:

```java
Runtime.getRuntime().gc();
```

The two expressions do not create a separate "strong" mechanism and "weak" mechanism. Both are **explicit GC requests**.

| Statement | True/False | Why? |
| --- | --- | --- |
| `System.gc()` suggests that the VM consider garbage collection | True | This is the intent of the API |
| A synchronous Full GC always occurs | False | The collector/configuration may react differently or ignore it |
| After the call, every eligible object has been reclaimed | False | There is no guarantee of timing or scope |
| A strongly reachable object can be destroyed because of this request | False | The JVM must preserve program semantics |
| `WeakReference.get()` is guaranteed to be `null` after the call | False | Depends on strong paths, liveness, and GC policy |
| The JVM definitely releases physical RAM back to the OS | False | Heap committed memory and RSS may remain unchanged |
| The call returns a boolean indicating GC succeeded | False | Return type is `void` |
| Logs/MXBeans can be used to observe how the VM responded | True | But the result only proves the scope of what was observed |

**Study rule:** `System.gc()` is a *request*, not *proof that GC has run*, and even less *proof that object X is dead*.

## 2. Reachability: When Is an Object Garbage?

Tracing garbage collectors examine the **object reference graph** starting from a set of **GC roots**. Typical roots include live references in execution frames, relevant static/runtime class state, JNI handles, and runtime structures whose purpose is to keep objects alive.

```text
  GC root 1 ──► A ──► C ──► D
  GC root 2 ──► B ──► C

  No root ──► E ◄─► F
```

Assume all arrows above are **strong references**:

- A, B, C, and D can be traced from a root, so they belong to the strongly reachable set.
- E and F point to each other, but there is no path from any root to them. Cycles do not keep objects alive on their own: a tracing collector can reclaim an unreachable cycle.
- If root 1 is removed, C and D are still reachable via B. Losing **one** path is not enough if another path remains.
- Setting a local variable to `null` does not prove there is no remaining retaining path via a field, static cache, ThreadLocal, listener, or JNI.

### Three Different Questions

1. **Strongly reachable?** Is there a live strong reference path from a root to the object in the context under consideration?
2. **Eligible for reclamation?** After considering special-reference processing and VM conditions, can the object be reclaimed?
3. **Already reclaimed?** Has the collector performed the corresponding reclaim/reuse work?

An object can be eligible but not yet processed by the GC. Even after reclamation, the heap region may still hold **committed memory** for future allocations, so process RSS does not necessarily decrease.

### `null` Is Not a Reclamation Command

```java
Object a = new Object();
Object b = a;
a = null;
System.gc();
System.out.println(b != null); // true
```

This is a snippet placed inside a method. Because `b` is still used and points to the object, a compliant collector cannot make the object disappear before the `println` line. There is no way to use `System.gc()` to "force-delete" an object that is still needed for Java semantics.

Even when `b` no longer appears in the source, the JIT/VM can determine **reference liveness** differently from the variable's lexical scope; whether a strong path remains or is lost must be inferred from the entire runtime graph, not just from the braces in the source code.

## 3. The JVM May Not Perform Explicit GC as You Expect

Some people call `System.gc()` and then look for a "Full GC" line in the logs. However, the response depends on:

- **JVM implementation** and specific release: HotSpot, OpenJ9, and other VMs do not always use the same policy.
- **Garbage collector**: Serial, Parallel, G1, ZGC, Shenandoah, or another supported collector.
- **Flags**: whether explicit GC is disabled, directed to a concurrent cycle, or handled by default.
- **Runtime load**: allocation rate, heap occupancy, marking state, and ongoing concurrent phases.
- **System decisions**: reclaiming appropriate memory regions, scheduling of GC threads, and the timing of metrics inspection.

### Some HotSpot Flags Worth Knowing

| Configuration | Meaning |
| --- | --- |
| `-XX:+DisableExplicitGC` | Ignores certain explicit GC requests such as `System.gc()`; automatic GC still operates |
| `-XX:+ExplicitGCInvokesConcurrent` | On supported collectors/configurations, an explicit request may use a concurrent mechanism |
| `-Xlog:gc*:info` | Writes GC logs using unified logging on HotSpot JDK 17+ |
| `-XX:+PrintFlagsFinal` | Inspects the actual flags and values of the running JVM |

Do not apply these flags in production as a one-size-fits-all formula. A JVM may not support a HotSpot flag or may support it with different limitations. Always verify `java --version` and run `java -XX:+PrintFlagsFinal -version` before interpreting logs or changing tuning.

### `DisableExplicitGC` Does Not Mean "Turn Off the Garbage Collector"

If HotSpot ignores a `System.gc()` call, it **still needs automatic GC** when the application creates allocation pressure. This flag does not prevent the collector from reclaiming objects during normal cycles. It only affects the relevant explicit request path and does not disable garbage collection entirely.

### "Full GC" Is Not a Portable Outcome

On some HotSpot collectors/configurations, an explicit GC may trigger a stop-the-world Full GC. However, **do not treat that behavior as a Java SE guarantee**. Another configuration may start concurrent work or do nothing. Collector selection must be read alongside the logs, not inferred from a single Java call.

## 4. GC Roots Determine Whether an Object Stays Alive, Not `System.gc()`

Example:

```java
class Cache {
    static final java.util.List<Object> ITEMS =
            new java.util.ArrayList<>();

    static void add() {
        ITEMS.add(new byte[1024]);
    }
}
```

This is a compilable illustrative class. If the runtime class/static state is still live, each element in `ITEMS` has a corresponding strong path:

```text
GC root / runtime class state
  → Cache.ITEMS
  → ArrayList.elementData
  → byte[] element
```

Calling `System.gc()` multiple times still **cannot** reclaim the arrays while the retaining path remains valid. This is usually a lifecycle/cache management bug, not "the GC being too weak".

Other examples of unintended retention:

- A `ThreadLocal` that has not been `remove()`d on a long-lived worker thread pool.
- A listener registered without being unregistered.
- A callback/lambda capturing an object in a scheduled task.
- A queue holding payloads for too long.
- An unreleased JNI global reference.
- A class loader or class metadata retaining an entire object/plugin graph.
- A static map without eviction/TTL/size bounds.

The fix is to **cut unnecessary strong references**, set bounds, and manage lifecycles. `System.gc()` does not automatically know when an object has lost its business meaning.

## 5. Strong, Soft, Weak, and Phantom References Differ

A test using `WeakReference` has a different meaning from tracking ordinary strong references.

| Type | Effect on reachability | Limitation when used for verification |
| --- | --- | --- |
| Strong reference | Keeps the object alive via a live strong reference path | Source scope is not strictly identical to VM liveness |
| `SoftReference<T>` | GC may clear the referent according to policy, related to memory demand | Not guaranteed to be cleared after a single explicit GC |
| `WeakReference<T>` | Does not keep the referent alive when it is only weakly reachable | `get()` may still be non-`null` after `System.gc()` |
| `PhantomReference<T>` | Tracks the appropriate phase via a queue, commonly used as a basis for cleanup | `get()` **always returns `null`**, even before GC |
| `ReferenceQueue<T>` | Receives reference objects enqueued according to API rules | Queue events are not guaranteed to appear immediately after an explicit request |

### Points That Are Very Easy to Confuse

- A **`WeakReference` object** itself can still be strongly reachable, while its **referent** is no longer strongly held.
- `weak.get()==null` proves that the weak reference **no longer returns the referent at that moment**. It **does not prove** that the `System.gc()` call itself did this: the application could have called `weak.clear()`, or another GC could have performed it.
- `weak.get()!=null` does not prove the object is leaking. The GC may not have run yet, or strong/soft references may still exist under runtime rules.
- `PhantomReference.get()` is always `null`; this value cannot be used as a test for reclamation.
- Clearing and enqueuing have their own processing details. `queue.poll()==null` does not prove the referent is still alive.

If you need to ensure a file/socket/native handle is closed, use `AutoCloseable` and `try-with-resources`; do not build resource cleanup logic around GC timing.

## 6. Runnable Java 17+ Example: Strong Path and Weak Reference

The following program demonstrates **two guaranteed outcomes while a strong path exists** and **two non-guaranteed observations after removing the strong path**. There are no assertions depending on GC scheduling.

Create the file `ExplicitGcDemo.java`:

```java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public class ExplicitGcDemo {
    private static volatile Object held;

    public static void main(String[] args) {
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        Object payload = new byte[1024];
        held = payload;

        WeakReference<Object> weak = new WeakReference<>(payload, queue);

        System.out.println("start");
        System.out.println("strongly held: " + (weak.get() == payload));

        System.gc(); // Hint, not a command forcing reclamation.

        System.out.println("after hint while held: "
                + (weak.get() == payload));

        // Keep the payload reference alive up to this point.
        Reference.reachabilityFence(payload);

        held = null;
        payload = null;
        // No intentional strong path remains in the source.

        System.gc();

        boolean cleared = weak.get() == null;
        boolean enqueued = queue.poll() != null;

        System.out.println("weak cleared: " + cleared);
        System.out.println("queue observed: " + enqueued);
        System.out.println("end");
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 ExplicitGcDemo.java
java ExplicitGcDemo
```

**Lines that are always present in order, with stable values:**

```text
start
strongly held: true
after hint while held: true
```

After those three lines, the program continues printing:

```text
weak cleared: <true-or-false>
queue observed: <true-or-false>
end
```

`<true-or-false>` **is an explanatory placeholder**: each position is printed by the program as the literal `true` or `false`, depending on the collector, timing, and reference processing. This is not a single fixed stdout output.

**Explanation:**

1. `payload` and static `held` both retain the object in the initial phase, so the GC must preserve the referent; `weak.get()==payload` is true.
2. The first `System.gc()` call must not destroy an object that is still strongly reachable.
3. `Reference.reachabilityFence(payload)` expresses the boundary preserving strong reachability up to that point.
4. After clearing both intentional strong paths, the object **may** become weakly reachable; however, Java does not guarantee that the GC has cleared the weak referent before the check line.
5. `queue.poll()` only observes enqueuing up to the time of the call; it does not mean "the GC cycle has finished".
6. `weak.get()` may temporarily create a strong reference when returning a non-`null` referent; the measurement itself can affect liveness for a very brief period.

**Do not turn the program into an infinite loop calling `System.gc()` until `weak.get()==null`.** That experiment may never terminate when explicit GC is ignored, when root paths remain, or simply because the VM has not processed the referent yet.

## 7. Running the Same Example with GC Logs and Flags

On HotSpot JDK 17+:

```bash
java -Xlog:gc*:info ExplicitGcDemo
java -XX:+DisableExplicitGC -Xlog:gc*:info ExplicitGcDemo
```

In the first run, the JVM may log a GC event with a cause related to `System.gc()`, depending on the collector and configuration. In the second run, HotSpot is instructed to ignore relevant explicit GC requests; however, **automatic** GC due to allocation pressure or other reasons can still appear.

A **non-fixed** illustrative log format:

```text
[info][gc] ... Pause Full (System.gc()) ...
```

The `...` in the example is not a fixed offset or timing. Some collectors use concurrent work or a different format/cause. **Do not write a unit test asserting that stdout/logs must always contain this exact line.**

### What Do Log Results Prove?

- An event explicitly noting an explicit GC cause: the JVM in that environment acknowledged/performed work related to the request.
- No event: the request may have been ignored, the VM handled it differently, or the event was not enabled under the observed tags/level.
- Heap "before/after" changed: GC/memory accounting work was measured, **without definitively identifying which single object was reclaimed**.
- Log shows "Pause Full": reflects the event type recorded by the JVM in that run, not proof that every collector always performs a Full GC upon `System.gc()`.

**Comparisons between two runs are not completely identical**: JIT warm-up, thread scheduling, heap sizes, and allocation progress can all differ. To evaluate performance, repeat multiple times with controlled workloads, flags, and environments.

## 8. GC Logs and Java Management APIs: Bounded Observation

Java provides `GarbageCollectorMXBean` to read collector names and statistics such as collection counts and times, when supported by the implementation.

Create the file `GcCounterDemo.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;

public class GcCounterDemo {
    private static void show(String label) {
        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();

        System.out.println(label);
        for (GarbageCollectorMXBean bean : beans) {
            System.out.println(bean.getName() + ": count="
                    + bean.getCollectionCount()
                    + ", time(ms)=" + bean.getCollectionTime());
        }
    }

    public static void main(String[] args) {
        show("before");
        System.gc();
        show("after");
        System.out.println("request completed");
    }
}
```

Commands:

```bash
javac -encoding UTF-8 GcCounterDemo.java
java GcCounterDemo
```

**Output format:**

```text
before
<actual collector lines and metrics>
after
<actual collector lines and metrics>
request completed
```

The two `<actual collector lines and metrics>` lines are **explanatory placeholders**, not verbatim printed output; collector names and counts depend on the JVM. Some beans return `-1` if a metric is not supported.

**There is no rule that "calling `System.gc()` once increments total collection count by exactly one".** Different JVMs/collectors define collection events, concurrent phases, and metrics differently. The VM can also perform GC for unrelated reasons between the two measurements.

If the goal is to see more detailed events, use GC unified logging or Java Flight Recorder (JFR) according to the environment's policy. If the goal is to find an object's **retaining path**, use a heap dump/profiler rather than GC counters alone.

## 9. Why Measuring Memory Before/After `System.gc()` Is Error-Prone

Common pattern:

```java
Runtime r = Runtime.getRuntime();
long before = r.totalMemory() - r.freeMemory();
System.gc();
long after = r.totalMemory() - r.freeMemory();
System.out.println("delta=" + (before - after));
```

This is a **snippet inside a method**, not a standalone program. `delta` here is **not the exact size of the object you want to inspect**.

Sources of inaccuracy:

- GC may not have run yet, may have run beforehand, or may have run for another reason.
- Other Java/JVM threads may allocate additional objects between the two snapshots.
- The compiler/JIT may optimize away unobservable allocations via escape analysis or scalar replacement.
- The VM may commit or uncommit heap pages on a policy different from the timing of object reclamation.
- `Runtime.totalMemory()` and `freeMemory()` measure according to the VM's heap model, **not the retained size of an object graph**.
- The collector may reclaim many unrelated objects, making the delta unrepresentative of object X alone.

### Different Metrics

| Metric | What it measures |
| --- | --- |
| Heap used | Heap memory currently in use according to JVM metrics |
| Heap committed | Portion of the heap committed by the JVM |
| Heap maximum / reserved | Limit or virtual space the VM is allowed to use per configuration |
| Process RSS | Resident RAM pages assigned to the process by the OS, including many regions outside the Java heap |
| Shallow object size | Memory of the object itself, without following references |
| Retained size | Memory that can become reclaimable when the corresponding dominator object is lost |

An object being reclaimed by GC does not mean the process must immediately return pages to the OS. The JVM often keeps committed heap regions for fast reallocation. Therefore, **RSS not decreasing** is not sufficient to say "GC had no effect".

To measure an object's shallow size, consider Java Object Layout (JOL) or `Instrumentation.getObjectSize` (subject to implementation limitations). To measure retained size, use a heap profiler/dominator tree.

## 10. Why `ReferenceQueue` Does Not Schedule GC Either

`ReferenceQueue` receives reference objects when they are enqueued by the VM according to reference processing rules. It is useful when an application wants to observe and handle an event, but it does not guarantee the event has occurred immediately after `System.gc()`.

```java
ReferenceQueue<Object> queue = new ReferenceQueue<>();
Object obj = new Object();
WeakReference<Object> weak = new WeakReference<>(obj, queue);
obj = null;
System.gc();

// No guarantee that queue.poll() is non-null here.
boolean received = queue.poll() != null;
```

This is an **illustrative code snippet placed inside a method** and requires `import java.lang.ref.*;` to compile. Beyond GC timing, liveness analysis itself and remaining references elsewhere also affect whether the object is eligible.

### Do Not Use `PhantomReference.get()` as an "Already GC'd" Flag

```java
ReferenceQueue<Object> q = new ReferenceQueue<>();
Object object = new Object();
PhantomReference<Object> p = new PhantomReference<>(object, q);
System.out.println(p.get() == null); // true, even before GC
```

This snippet requires `import java.lang.ref.*;` and belongs inside a method. `PhantomReference.get()` **always returns `null`** by API specification, so it does not reflect whether the object has been reclaimed. When API-compliant cleanup is needed, use `ReferenceQueue` / `Cleaner` appropriately with their timing limitations, without inferring from `get()`.

## 11. `Reference.reachabilityFence` Solves a Different Problem

The JIT may determine that an object is no longer needed earlier than the end of a method or lexical scope. When an object manages a native handle, a situation can arise where a native operation still needs the resource associated with the object, yet the VM no longer sees the object as needing to stay alive without an appropriate guarantee.

Java 9+ supports:

```java
Reference.reachabilityFence(object);
```

This method keeps the object strongly reachable **at least until the fence call**, when reachability must be guaranteed for preceding code. It does **not** force GC to run, does not make `System.gc()` synchronous, and does not guarantee the object will die immediately after the fence.

Illustrative example (not standalone runnable because `NativeApi` needs to be declared):

```java
final class NativeResource {
    final long handle;

    NativeResource(long handle) {
        this.handle = handle;
    }

    void use() {
        NativeApi.perform(handle);
        java.lang.ref.Reference.reachabilityFence(this);
    }
}
```

When a resource must be closed in an orderly manner, prefer `AutoCloseable`, `close()`, and `try-with-resources`. A fence serves a reachability constraint; **it does not replace resource lifecycle management**.

## 12. `System.gc()` Does Not Guarantee Running Finalizers/Cleaners

**Finalization** is a legacy Java mechanism, deprecated for removal because it is unreliable and has safety/performance issues. `System.gc()` does not guarantee finalizers run on time; `System.runFinalization()` is not a "close all file handles button" either.

- A finalizer may not run before the process exits.
- A finalizer can resurrect/retain an object in legacy cases.
- `Cleaner` relies on GC/reference processing, so its execution timing is also **non-deterministic**.
- File/socket/database connection resources need to be closed according to the program's lifecycle, not by waiting for heap pressure.
- Calling GC frequently can cause pauses while still failing to close resources held by strong references.

Example using standard APIs to close a resource:

```java
import java.io.BufferedReader;
import java.nio.file.Files;
import java.nio.file.Path;

class ReadFileExample {
    static String firstLine(Path path) throws Exception {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            return reader.readLine();
        }
    }
}
```

This is an **illustrative class with a method**, without a `main` method. `try-with-resources` calls `close()` when exiting the block according to Java semantics, regardless of whether `System.gc()` runs.

## 13. Testing: Do Not Write Assertions Depending on GC Timing

The following assertion is **unreliable**:

```java
WeakReference<Object> weak = new WeakReference<>(new Object());
System.gc();
assert weak.get() == null;
```

This snippet is placed inside a method with appropriate imports. It can fail even when both the application and the JVM are completely correct. Reason: the explicit request may be ignored, or the collector may not have cleared the reference by the time of the assertion. Running with `-XX:+DisableExplicitGC` makes this non-determinism even more obvious.

### Verifying Deterministic Application Behavior

If the goal is to ensure a resource is closed, write tests based on **explicit behavior**, for example:

```java
final class Resource implements AutoCloseable {
    private boolean closed;

    @Override
    public void close() {
        closed = true;
    }

    boolean isClosed() {
        return closed;
    }
}
```

Inside the test method:

```java
Resource resource = new Resource();
resource.close();
if (!resource.isClosed()) {
    throw new AssertionError("resource was not closed");
}
```

No `System.gc()` is needed; the test depends only on the contract of `Resource.close()`.

### If Testing GC Factors in Integration Tests Is Unavoidable

1. Run the test in a **separate JVM process** so it does not affect other suites.
2. Record the JVM version/vendor/collector/flags.
3. Manage reference/referent lifecycles properly, avoiding test fixtures that strongly retain the object.
4. Use a bounded timeout and accept an **inconclusive timing result** if GC is not observed.
5. Do not create an infinite loop calling `System.gc()`.
6. Do not use the absence of GC within the timeout to conclude that the program has a leak.
7. Combine `ReferenceQueue` with GC logs when needed, documenting the proof boundaries of each measurement.

**In particular:** in a `weak.get()!=null` loop, each `get()` call that returns a non-null referent creates a temporary strong reference. That can make liveness even harder to predict; avoid polling in a way that alters the state being observed.

## 14. More Valuable Tools When Debugging "GC Not Collecting Objects"

Some tools on HotSpot JDK 17:

```bash
java --version
java -XX:+PrintFlagsFinal -version
jcmd -l
jcmd PID GC.heap_info
jcmd PID GC.class_histogram
```

`PID` is a placeholder: replace it with the actual PID from `jcmd -l`. `jcmd PID help` shows which commands a specific JVM supports. Heap histograms/dumps can be expensive and cause pauses, especially in production; always consider access permissions, traffic, and sensitive data.

### Choosing Tools by Question

| Question | Useful tools | Limitations |
| --- | --- | --- |
| Did the VM acknowledge the explicit GC request? | `-Xlog:gc*`, JFR GC events | Does not prove a specific object was reclaimed |
| What is the GC frequency/duration? | `GarbageCollectorMXBean`, logs, JFR | Does not provide an object's retaining path |
| Which object is keeping object X alive? | Heap dump, **Paths to GC Roots** | Point-in-time snapshot; requires understanding reference strength |
| Is a static cache holding data? | Heap analyzer + dominator tree | Shows retaining paths; business logic still needs verification |
| What are heap used/committed/RSS levels? | MXBeans, OS monitoring, NMT | Metrics are not interchangeable |
| How many shallow bytes does an object occupy? | JOL, Instrumentation | Does not provide GC timing |
| Has a resource been closed? | Explicit close, API state, test doubles | Should not use GC as an oracle |

For a **memory leak** caused by an unintended root path, "running GC harder" is not the fix. Finding the root path and cutting the unnecessary reference is the right direction.

## 15. `System.gc()` and Performance: Why Not Call It After Every Request?

Collectors typically have policies around heap occupancy, allocation rate, generations/regions, time budgets, and ongoing phases. The application lacks sufficient internal context to choose an optimal collection point after every request.

Repeating explicit GC too frequently can:

- Increase pauses and p95/p99 latency when the VM chooses an expensive collection type.
- Consume CPU/memory bandwidth for GC threads.
- Distort warm-up/JIT benchmarks or latency-sensitive tasks.
- Achieve nothing if the VM ignores requests or the live set still has strong root paths.
- Mislead the development team into thinking leak/resource management issues have been solved.

**Do not claim a single call is always slow** — the collector may ignore it or handle it concurrently. However, calling it blindly in production is a choice that requires empirical data to justify.

If an app is repeatedly near `OutOfMemoryError`, inspect allocation rate, retaining paths, cache/queue sizes, heap limits, native memory, and profiling tools. Reordering GC requests without fixing the retaining structure usually does not solve the problem.

## 16. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "`System.gc()` always collects immediately." | It is a request; collector behavior depends on the JVM/flags |
| "Every `System.gc()` is a Full GC." | Not a Java SE guarantee |
| "Dropping a strong reference makes GC run immediately." | Reachability and collector scheduling are two different things |
| "`System.gc()` even deletes objects that still have a strong root path." | The collector must preserve objects still needed by the program |
| "`WeakReference.get()==null` proves explicit GC succeeded." | It could be cleared another way; only describes the weak reference at the moment of reading |
| "`WeakReference.get()!=null` proves an object leak." | GC may not have run yet or a valid live path may remain |
| "`PhantomReference.get()==null` means the object is dead." | `get()` always returns null |
| "`ReferenceQueue.poll()==null` proves the object is alive." | Enqueuing has its own timing |
| "After `System.gc()`, RSS must decrease." | The JVM may retain committed pages |
| "Heap used delta is the exact size of object X." | The delta includes many objects and other runtime effects |
| "`-XX:+DisableExplicitGC` turns off automatic GC." | Automatic GC still operates |
| "Finalizers definitely run after explicit GC." | Not guaranteed; finalization is legacy |
| "GC can replace `close()`." | Resource cleanup requires explicit lifecycle management |
| "Every local in scope is a root until the end of the method." | JIT liveness can be shorter than lexical scope |
| "`System.gc()` makes weak cache tests deterministic." | GC timing is non-deterministic |
| "Calling explicit GC repeatedly fixes memory leaks." | Strong root paths still keep objects alive |

## 17. Exercises with Answers

**Exercise 1.** Given `Object a = new Object(); Object b = a; a = null;` followed by `System.gc()`. What does `System.out.println(b != null)` print afterward?  
**Answer:** `true`. `b` still references the object when it is used.

**Exercise 2.** The JVM runs with `-XX:+DisableExplicitGC`, and GC logs report no event right after `System.gc()`. Is GC broken?  
**Answer:** No. Explicit requests may be ignored; the VM still performs automatic GC when needed.

**Exercise 3.** `weak.get()` is non-`null` after `System.gc()`. Is the object definitely leaking?  
**Answer:** No. There may still be a strong path, or the weak reference has not been processed yet.

**Exercise 4.** Does `weak.get()==null` prove that RSS decreased?  
**Answer:** No. Weak reference clearing and memory accounting/OS pages are different events.

**Exercise 5.** `PhantomReference.get()` returns `null` right after the constructor. Has the referent been reclaimed?  
**Answer:** No. The API always returns null.

**Exercise 6.** Calling explicit GC after every request causes high latency. Should we increase the call frequency to keep things cleaner?  
**Answer:** No; investigate the root cause, measure pauses/load, and consider removing explicit requests.

**Exercise 7.** A static `List<byte[]>` holds one million elements. Is `System.gc()` a way to reduce retained heap?  
**Answer:** No. References must be removed/bounded when no longer needed.

**Exercise 8.** `GarbageCollectorMXBean` count increases by one. Is GC guaranteed to have reclaimed object X?  
**Answer:** No. The count reflects collection events as defined by the collector, not a specific object identity.

**Exercise 9.** After GC, heap used decreases, but process RSS does not. Must this be treated as a bug?  
**Answer:** No. The JVM may keep committed heap for reuse.

**Exercise 10.** To test that a file resource is closed, what should you do?  
**Answer:** Use `try-with-resources`/`close()` and assert explicit behavior; do not wait for `System.gc()`.

**Exercise 11.** Why does compiler liveness make tests using `System.gc()` unpredictable?  
**Answer:** The VM may determine a reference does not need to be kept until the end of the scope; temporary references or allocation optimizations also make results differ from expectations.

**Exercise 12.** Does `Reference.reachabilityFence(x)` force GC immediately afterward?  
**Answer:** No. It keeps the object strongly reachable up to the required point; it does not control GC scheduling.

**Exercise 13.** To find out why an object is not dead despite calling explicit GC many times, which tool should you use?  
**Answer:** A heap dump/profiler to inspect **Paths to GC Roots**, static refs, ThreadLocals, listeners, queues, and JNI handles.

**Exercise 14.** Does `Runtime.getRuntime().gc()` have a stronger guarantee than `System.gc()`?  
**Answer:** No. Same explicit GC request semantics, no reclamation guarantee.

**Exercise 15.** Does `System.gc()` returning normally mean all GC work has finished?  
**Answer:** There is no portable guarantee regarding the type of GC or when all work completes.

## 18. Safe Verification Checklist

- [ ] Clearly identify the question being asked: **was the GC request processed**, **is the object still reachable**, or **has the resource been closed**?
- [ ] Record the JVM vendor, version, garbage collector, and process flags.
- [ ] Do not assert GC timing or `WeakReference` clearing after a single call.
- [ ] Understand that `WeakReference`, `PhantomReference`, and `ReferenceQueue` have different semantics.
- [ ] Check hidden strong paths via static fields, ThreadLocal, listeners, and JNI.
- [ ] Use GC logs/JFR/MXBeans if checking collector behavior.
- [ ] Use heap dumps and Paths to GC Roots if checking retaining paths.
- [ ] Do not equate heap used, committed, reserved, RSS, and retained size.
- [ ] Use a timeout if experimenting with reference enqueuing; do not wait indefinitely.
- [ ] Do not call explicit GC as a resource management mechanism.
- [ ] Use deterministic tests for application logic and lifecycle.
- [ ] Avoid production tuning based on a single run, single collector, or single JDK release.

## 19. Summary and Reference Documentation

**`System.gc()` is only a hint to the JVM**, not a synchronization primitive for measuring object lifetime, forcing a Full GC, asserting weak reference clearing, or forcing the operating system to reclaim memory.

- To understand **why an object stays alive**, find the **strong paths to GC roots**.
- To know **how the collector responds to an explicit request**, use GC logs/JFR/MXBeans for the running JVM and flags.
- To investigate a **memory leak**, use root-path/retained-size analysis, not repeated forced GC.
- To guarantee **resource cleanup**, use explicit closing APIs.
- To observe weak/soft/phantom references, accept **non-guaranteed timing** and the distinct semantics of each reference type.

**Reference documentation:**

1. Java SE 17 — `System.gc()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()
2. Java SE 17 — `Runtime.gc()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#gc()
3. Java SE 17 — `java.lang.ref` package, definitions of reachability levels: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html
4. Java SE 17 — `Reference.reachabilityFence`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html
5. Oracle JDK 17 — Garbage Collection Tuning Guide: https://docs.oracle.com/en/java/javase/17/gctuning/
6. Oracle JDK 17 — `java` command/flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
7. OpenJDK JEP 421 — Deprecate Finalization for Removal: https://openjdk.org/jeps/421

**Remember:** if a test relies on the premise "call `System.gc()` and object X will definitely disappear", that premise is wrong. Turn the test into **verifying what Java actually guarantees**, and use explicit GC only as an observational signal in a clearly scoped JVM experiment.