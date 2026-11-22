# System.gc() is a hint request and does not replace object lifecycle management

> **Module:** Java Core — class/object  
> **Group:** Object Lifecycle  
> **Main topic:** Understanding `System.gc()`, the limitations of garbage collection, and how to actively manage resource lifecycles  
> **Requirements to run examples:** JDK 17+, without preview features.

## 1. The most important message

Java has a **garbage collector (GC)** to automatically reclaim **the heap memory of objects that are no longer reachable under runtime mechanisms**. The call:

~~~java
System.gc();
~~~

**only hints to the JVM to make an effort to perform garbage collection**. It is not a synchronous command forcing the JVM to collect a specific object, does not guarantee that every eligible object will be reclaimed immediately, does not guarantee reducing the process's resident memory, and **does not mean that resources such as sockets, files, or database connections are closed at the right time**.

Therefore, three things need to be separated:

1. **When is an object still referenced by the program?** This is a matter of reachability, ownership, and retaining references.
2. **When does an object's heap memory become eligible for reclamation by the GC?** When it is no longer reachable through GC roots according to runtime semantics; being eligible does not mean being reclaimed immediately.
3. **When are resources outside the heap released?** In most cases, an explicit lifecycle API such as `close()`, `shutdown()`, `unsubscribe()`, or `remove()` is needed; do not wait for the GC.

Operational principles:

- Do not use `System.gc()` to replace `try-with-resources`.
- Do not write unit tests based on the assumption that “calling `System.gc()` means the object has been reclaimed”.
- Do not insert `System.gc()` into every loop/transaction expecting to “cure a memory leak”.
- Do not confuse clearing a Java reference with closing an OS resource.
- Keep the lifetime of strong references aligned with actual needs; manage caches, listeners, threads, and registries with clear release policies.
- If you truly need to measure/optimize GC, use **measurement data and GC diagnostics**, not guesswork from a single API call.

The following sections explain why these principles hold, then move from simple examples to resource management patterns, Cleaner, weak references, and common memory retention cases.

## 2. Object lifecycle viewed from Java source and the JVM

A useful way to understand it, not identical to the absolute phases of all garbage collectors:

~~~text
Create object
    |
    v
Has a reachable reference from the program
    |
    |  May have multiple aliases/owners, local variables, fields, collections
    v
No longer reachable from GC roots
    |
    v
Eligible for reclamation by the garbage collector
    |
    |  GC gets to choose the timing, may not run immediately
    v
Heap storage can be reclaimed/reused by the JVM
~~~

Note: The Java language/runtime does not guarantee that every object will sequentially appear in an observable state as shown in the diagram above. This is a mental model that helps distinguish **reachability** from **reclamation timing**.

### 2.1. Creating an object does not mean manually managing heap allocation

With:

~~~java
User user = new User("Lan");
~~~

`new` creates an instance according to Java semantics. The JVM and garbage collector manage the actual memory, and may use techniques such as allocation buffers, escape analysis, scalar replacement, or other optimizations. Do not treat every `new` statement as necessarily creating a physical object that exists throughout a point in time observable by tools.

### 2.2. A reference variable is different from an object

~~~java
User first = new User("Lan");
User second = first;
first = null;
~~~

`first` no longer points to the object, yet `second` still holds a strong reference. The object **is still reachable**. Assigning null only changes the value of the variable first; **it is not a command to delete the object**.

### 2.3. An object can outlive the scope you expect

An object created inside a method can be returned, placed in a field, a static collection, an event listener, a background task, or a callback. In that case, it can remain reachable after the method finishes.

Conversely, the JVM may determine that a local variable is no longer used before the lexical end of its scope under certain optimizations. When you need to explicitly ensure an object **remains strongly reachable up to a specific point** in code interacting with native code or weak references, `Reference.reachabilityFence(object)` is the dedicated API.

### 2.4. Losing a reference does not guarantee closing resources

Even if an object wrapping a file or socket becomes unreachable, the underlying file descriptor or socket state does not have a **closing deadline** provided by `System.gc()`. Use an explicit resource API.

## 3. Reachability and GC roots

Garbage collectors typically analyze the **reference graph** starting from root points (GC roots). High-level model:

~~~text
GC roots
  |
  +---- local variables / thread frames (while considered live by the runtime)
  |
  +---- static fields / class-related roots while classes remain live
  |
  +---- runtime, JNI, synchronization, and other roots
  |
  v
Object A ---> Object B ---> Object C
      \
       ----> Object D
~~~

If the JVM can find a strong-reference path from a root to an object, that object remains reachable according to the applicable mechanism. The GC is not allowed to arbitrarily delete an object that must still be validly accessible through strong references.

### 3.1. GC roots are not a List in source code

There is no simple public Java API to ask “what are all the roots for this object?”. Roots are a JVM runtime/collector concept that changes during runtime execution. Heap dump and reference analysis tools can help analyze retaining paths.

### 3.2. Static fields can keep objects alive for a very long time

~~~java
static final java.util.List<Object> CACHE =
        new java.util.ArrayList<>();
~~~

If you continuously call `CACHE.add(...)` without removing or bounding entries, the objects in the List remain reachable through the static field as long as the holder class and related references remain live. `System.gc()` cannot decide on its own that the entries are “old” and allowed to be removed from the collection.

### 3.3. Listeners and callbacks also hold references

When an event dispatcher holds a listener in a List, the listener may capture a large object. If you do not unsubscribe when the screen/session/service ends, the dispatcher still has a strong-reference path to the captured state. This can be a **retention leak**, even though the garbage collector works properly.

### 3.4. ThreadLocal and long-lived threads

`ThreadLocal` helps attach a value to each thread. With long-lived threads, especially in thread pools, forgetting to call `remove()` when a task finishes can extend the lifetime of values (details also depend on how the ThreadLocal map holds keys and values). The proper solution is usually `try/finally { threadLocal.remove(); }`, not calling `System.gc()`.

### 3.5. Cyclic references are not automatically a leak

~~~java
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;
~~~

An A↔B cycle can still be reclaimed by the GC **if there is no longer a strong-reference path from roots to the cycle**. You do not need to manually break every reference cycle just for the GC to recognize an unreachable cycle. However, if a static field still points to A, the entire cycle remains reachable.

## 4. Complete program 1 — losing local references does not prove an object has been reclaimed

Create the file **`ReachabilityBasicsDemo.java`**:

~~~java
public class ReachabilityBasicsDemo {
    static final class Node {
        static int created;
        Node next;

        Node() {
            created++;
        }
    }

    public static void main(String[] args) {
        Node a = new Node();
        Node b = new Node();

        a.next = b;
        b.next = a;

        System.out.println("Created = " + Node.created);
        System.out.println("Cycle = "
                + (a.next == b && b.next == a));

        a = null;
        b = null;

        System.out.println("Variables cleared = "
                + (a == null && b == null));
        System.out.println("GC timing = not asserted");
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ReachabilityBasicsDemo.java
java ReachabilityBasicsDemo
~~~

**Exact stdout:**

~~~text
Created = 2
Cycle = true
Variables cleared = true
GC timing = not asserted
~~~

### 4.1. What the demo proves

- Two Node constructors ran.
- There is an object graph with a cycle.
- Two variables were assigned null.
- No check in the demo asserts that the garbage collector reclaimed the two objects.

### 4.2. What the demo cannot prove

It **does not** indicate whether the GC actually ran, when heap space was reclaimed, or up to what point bytecode/JIT kept a reference to the last node. That is intentional: do not turn garbage collection timing into expected output of a Java business program.

### 4.3. Do not confuse the `created` variable with the number of currently live objects

`created` is the number of times the constructor ran in the example program, **not the live instance count**. Reducing the number of references does not automatically decrement the static counter. A manually maintained static counter will not be updated by the GC after an object loses reachability.

## 5. What is System.gc() really?

`System.gc()` is a static method of `java.lang.System`. It **hints** to the JVM to make an effort to reclaim the memory of objects that are no longer used. In terms of API effect, this call is equivalent to:

~~~java
Runtime.getRuntime().gc();
~~~

The JVM/collector has the right to decide how to respond to the hint, influenced by the implementation, flags, workload, and runtime constraints.

### 5.1. “Hint” does not mean always ignored

In some JVM configurations, an explicit GC request can trigger garbage collection effort and incur significant cost, even causing pauses. You should not say “System.gc() has no effect in every JVM”.

### 5.2. “Hint” does not mean always executing a full GC

There is no promise that every call will trigger a “full GC” in a uniform way. Different collectors, different JVM flags, and different JDK versions may react differently, or allow disabling explicit GC.

### 5.3. No guarantee of reclaiming a specific object

There is no API contract such as “after System.gc() returns, weak reference X is definitely null” or “object Y has been cleaned up”. The JVM may have made an effort while an object is still reachable; or it may not reclaim at the timing assumed by the test.

### 5.4. No guarantee that heap memory is returned to the OS

Even when the GC reclaims internal heap space for JVM reuse, the process resident set size/committed heap may not decrease as an observer expects. The JVM typically manages reserved/committed memory and its own collector policies separately. **Heap free space, committed heap, and the process's physical memory are different metrics.**

### 5.5. Calling it multiple times does not create a deadline

~~~java
for (int i = 0; i < 100; i++) {
    System.gc();
}
~~~

This does not create a stronger guarantee that “all resources are released before time T”. On the contrary, it can increase overhead or pauses depending on the JVM; do not use this as a production cleanup loop.

## 6. Complete program 2 — calling the hint without inferring results

File **`ExplicitGcHintDemo.java`**:

~~~java
public class ExplicitGcHintDemo {
    public static void main(String[] args) {
        System.out.println("Before hints");

        System.gc();
        Runtime.getRuntime().gc();

        System.out.println("After hints");
        System.out.println("Collected object count = unknown");
        System.out.println("Resource closure = separate contract");
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ExplicitGcHintDemo.java
java ExplicitGcHintDemo
~~~

**Exact stdout:**

~~~text
Before hints
After hints
Collected object count = unknown
Resource closure = separate contract
~~~

### 6.1. Why not print the number of reclaimed objects?

Java SE does not provide a method where “System.gc() returns the number of objects just reclaimed”. Printing some measured number would easily mislead readers into thinking it is a guaranteed result of the method.

### 6.2. Why do both System.gc and Runtime.gc appear together?

Only to illustrate the API relationship. In real code, there is rarely any reason to call both in succession; they are not two required steps.

### 6.3. Execution time may vary even though stdout is the same

Depending on the JVM configuration and machine, an explicit GC call may involve significant effort, an operation tuned by the collector, or almost no effect. Therefore, the demo only promises **stdout**, not timings or collection counts.

## 7. The sufficient condition to be “eligible for GC” is not calling System.gc()

An object can become eligible for garbage collection when it is no longer reachable from GC roots under the applicable reference-processing rules. Calling `System.gc()` does not make strong references disappear on their own.

Example:

~~~java
static final List<byte[]> BUFFERS = new ArrayList<>();

static void addBuffer() {
    BUFFERS.add(new byte[1024]);
}
~~~

If code keeps adding buffers while holding this List in a live static owner, the buffers remain reachable even if you call System.gc after every addition. The collector itself **has no authority to delete data that the program still strongly references and can use**.

### 7.1. Assigning null can help release a reference, but does not guarantee reclamation

~~~java
buffer = null;
~~~

This only changes the reference in the variable buffer. If an alias still exists in a List or another object field, the object remains reachable. If no aliases remain, the object may become eligible for GC, but there is no deadline.

### 7.2. Removing from a collection matters more than a hint

~~~java
BUFFERS.clear();
~~~

releases the strong references from the List to its elements (if there are no other aliases). It can help the elements become unreachable, which **does not mean the operating system gets memory back immediately**.

### 7.3. Do not confuse clearing a collection with closing resources

If a List holds AutoCloseable objects managing sockets/files, `clear()` **does not call close()**. You need to design a way to close each resource before or while removing the reference, according to the ownership policy.

## 8. Complete program 3 — static retention and proper cleanup

File **`RetentionReleaseDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RetentionReleaseDemo {
    static final List<byte[]> RETAINED = new ArrayList<>();

    static void createAndRetain() {
        RETAINED.add(new byte[8]);
        RETAINED.add(new byte[16]);
    }

    static void releaseRetention() {
        RETAINED.clear();
    }

    public static void main(String[] args) {
        createAndRetain();

        System.out.println("Retained entries = "
                + RETAINED.size());
        System.out.println("First buffer bytes = "
                + RETAINED.get(0).length);

        System.gc(); // Does not remove elements from RETAINED.

        System.out.println("After GC hint entries = "
                + RETAINED.size());

        releaseRetention();

        System.out.println("After clear entries = "
                + RETAINED.size());
        System.out.println("Reclamation time = unspecified");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 RetentionReleaseDemo.java
java RetentionReleaseDemo
~~~

**Exact stdout:**

~~~text
Retained entries = 2
First buffer bytes = 8
After GC hint entries = 2
After clear entries = 0
Reclamation time = unspecified
~~~

### 8.1. Why does System.gc not remove List elements?

`RETAINED` is still a static List holding references to the two arrays. The GC does not automatically delete data that code can still validly read; ArrayList.size remains 2.

### 8.2. Why not print “bytes freed = 24” after calling clear?

List.clear removes the entries, but does not directly measure heap reclamation. The JVM may reclaim the arrays at another time, the compiler/JIT may optimize the allocation, and the actual byte size of an array object also includes header/alignment. Printing 24 bytes freed would be an inaccurate claim.

### 8.3. The production issue is the retention policy

If a cache needs to retain buffers to increase throughput, it must have capacity limits, eviction, TTL, and appropriate observability. You should not retain them unboundedly and then call `System.gc()` as a size-reduction mechanism.

## 9. GC-managed heap memory differs from resources that must be actively managed

A Java object can simultaneously:

- have fields located on the heap (automatically reclaimed by the GC when unreachable), and
- **own or reference other resources** with their own lifecycle.

Examples:

| Type | Representing Java object | Appropriate lifecycle operation |
| --- | --- | --- |
| File read/write stream | `InputStream`, `OutputStream` | `close()` / try-with-resources |
| Socket/network connection | `Socket` or client-specific resource | `close()`, per the corresponding API |
| JDBC connection/statement/result set | `Connection`, `Statement`, `ResultSet` | `close()`, proper pooling lifecycle |
| File channel | `FileChannel` | `close()` |
| Executor service | `ExecutorService` | `shutdown()` / `shutdownNow()` or `close()` on the appropriate API/version |
| Listener registration | callback/subscription handle | `removeListener`/`unsubscribe`/`close` per API |
| Lock | `Lock` | `unlock()` in finally after the lock is acquired |
| ThreadLocal value | `ThreadLocal<T>` | `remove()` when the application scope ends |
| Cache entries | `Map`, caching library | remove/eviction/size policy |
| Temporary files | `Path` / filesystem | `Files.deleteIfExists()` per policy |

**Common point:** The GC does not replace business-level ownership semantics. Some frameworks have background cleaners/final fallbacks, but that is not a reason to skip explicit resource management.

### 9.1. AutoCloseable does not mean the JVM automatically calls close when unreachable

`AutoCloseable` is simply an interface with a `close()` method. Java does not automatically call close based on GC reachability. **Try-with-resources** is the language construct that actively calls close when exiting a scope, even when an exception occurs.

### 9.2. Close does not mean the object is immediately GC'd

After `resource.close()`, the resource variable can still point to the Java wrapper object; the GC may reclaim that object later when it becomes unreachable. `close` and GC handle two different kinds of responsibilities.

### 9.3. Not every AutoCloseable is idempotent under a general contract

Some resource implementations allow calling close multiple times safely; you should not assume every AutoCloseable in every library allows this. Your own design can deliberately choose an idempotent close, and document it if that is the contract.

## 10. Try-with-resources: the primary tool to close resources within the right scope

Syntax:

~~~java
try (Resource resource = acquire()) {
    use(resource);
}
~~~

This requires Resource to implement `AutoCloseable` (or its subtype `Closeable`). Upon exiting the scope, Java calls `close()` automatically according to language rules. This applies whether the block finishes normally or throws an exception.

### 10.1. Multiple resources close in reverse order

~~~java
try (A first = acquireA();
     B second = acquireB()) {
    use(first, second);
}
~~~

`second.close()` runs before `first.close()`. This is a useful rule when resource B depends on A and needs to be closed in reverse acquisition order.

### 10.2. Difference from a manual finally

You can write:

~~~java
Resource resource = acquire();
try {
    use(resource);
} finally {
    resource.close();
}
~~~

This fragment is only for illustration; if an exception occurs in both use and close, handling primary/suppressed exceptions requires care. Try-with-resources provides standard rules for preserving the primary exception and recording close exceptions as **suppressed exceptions** when appropriate.

### 10.3. The clearer the scope, the easier it is to verify the lifecycle

Do not hold an `InputStream` in a static field and hope the JVM closes it soon. Create the resource where there is a clear owner and bind its lifetime with try-with-resources when the API allows.

## 11. Complete program 4 — closing order and the number of still-open resources

File **`TryWithResourcesLifecycleDemo.java`**:

~~~java
public class TryWithResourcesLifecycleDemo {
    static final class Tracker {
        int open;
    }

    static final class Resource implements AutoCloseable {
        private final String name;
        private final Tracker tracker;
        private boolean closed;

        Resource(String name, Tracker tracker) {
            this.name = name;
            this.tracker = tracker;
            tracker.open++;
            System.out.println("open " + name);
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            System.out.println("use " + name);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                tracker.open--;
                System.out.println("close " + name);
            }
        }
    }

    public static void main(String[] args) {
        Tracker tracker = new Tracker();

        try (Resource first = new Resource("A", tracker);
             Resource second = new Resource("B", tracker)) {
            first.use();
            second.use();
            System.out.println("inside open = " + tracker.open);
        }

        System.out.println("outside open = " + tracker.open);
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 TryWithResourcesLifecycleDemo.java
java TryWithResourcesLifecycleDemo
~~~

**Exact stdout:**

~~~text
open A
open B
use A
use B
inside open = 2
close B
close A
outside open = 0
~~~

### 11.1. Why is stdout reliable?

The constructor/body/close order is determined by Java try-with-resources semantics. There is no need to measure when an object is GC'd, and it does not depend on whether the collector runs.

### 11.2. Why is the counter 0 after try?

`close()` was called on both resources, decrementing tracker.open once each time. This is **program-managed resource state**, not the number of heap objects that have been garbage collected.

### 11.3. Why does the code guard against closing twice?

The `closed` field prevents decrementing the counter a second time. This is an **idempotent close implementation of the example**, not a claim that every AutoCloseable is idempotent.

### 11.4. Would adding System.gc to the program help?

Not for the goal of “closing A and B”. Java already closes both in the right order via try-with-resources. System.gc does not improve the correctness of this resource lifecycle.

## 12. Exceptions when closing resources: primary and suppressed

If code inside the try block throws an exception, and `close()` also throws an exception, Java prioritizes preserving the try block's exception as the **primary exception**. The exception from close can be added to the list of **suppressed exceptions**.

### 12.1. Why is this important?

If cleanup is written improperly with finally, a close error can mask the actual error from the work, making debugging difficult. Try-with-resources provides a standard mechanism to retain both error details.

### 12.2. When should suppressed exceptions be logged?

When debugging a failure in a pipeline with multiple resources, inspect `Throwable.getSuppressed()`. A primary exception can carry multiple suppressed exceptions from close() calls in reverse order.

### 12.3. Complete program 5 — an exception still closes the resource

File **`SuppressedCloseDemo.java`**:

~~~java
import java.io.IOException;

public class SuppressedCloseDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing resource");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) throws Exception {
        try (FailingResource resource = new FailingResource()) {
            System.out.println("work started");
            throw new IllegalStateException("work failed");
        } catch (IllegalStateException ex) {
            System.out.println("primary = " + ex.getMessage());
            System.out.println("suppressed count = "
                    + ex.getSuppressed().length);
            System.out.println("suppressed message = "
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SuppressedCloseDemo.java
java SuppressedCloseDemo
~~~

**Exact stdout:**

~~~text
work started
closing resource
primary = work failed
suppressed count = 1
suppressed message = close failed
~~~

### 12.4. Key point to remember

The resource is still requested to close when the body throws. The body exception is primary; the close exception is kept as suppressed. That is **resource management determined by language constructs**, completely different from waiting for System.gc.

## 13. Design flaw: relying on finalize() to close a resource

Historically, some code overrode `finalize()` to attempt cleanup when an object was about to be garbage collected. This approach has many problems:

- There is no guarantee that a finalizer will run on time or run before program termination.
- GC timing is nondeterministic, and finalization has its own separate processing mechanism/queue/thread.
- There is a risk of resource exhaustion because files/sockets are held for too long.
- Finalization is complex regarding concurrency, exception behavior, and object resurrection.
- It can cause performance/security concerns.
- Java has marked finalization as an obsolete mechanism; do not design new code around `finalize()`.

**Do not write production cleanup based on `finalize()`, and do not assume that `System.gc()` will make a finalizer run immediately.**

### 13.1. The resource lifecycle must be decided by the owner

If a method opens a file, it should usually own the closing scope with try-with-resources. If an object holds a connection throughout the lifetime of a service, the service needs clear lifecycle hooks such as start/stop/close and shutdown coordination.

### 13.2. Do not manually call finalize() as close()

`finalize()` is not a standard lifetime-control API. Directly calling a finalize method (if accessible) does not replace a resource-specific close and also makes code harder to understand.

### 13.3. What are the alternative APIs?

- **`AutoCloseable` + try-with-resources:** deterministic release within a logical scope.
- **`Cleaner`:** fallback cleanup action when the referent reaches the appropriate condition; automatic execution timing is **not guaranteed**, and it does not replace explicit close.
- **`PhantomReference` + `ReferenceQueue`:** build a specialized post-reachability tracking mechanism when truly needed; does not automatically create deterministic cleanup.
- **Framework/service lifecycle hooks:** shut down pools, subscriptions, and transactions according to the owner.

## 14. Cleaner is a fallback aid, not a “GC-controlled close” with a deadline

Since Java 9, `java.lang.ref.Cleaner` provides an API to register a cleanup action associated with an object's reachability.

Key points:

1. `Cleaner.create()` creates a Cleaner.
2. `cleaner.register(referent, action)` returns `Cleaner.Cleanable`.
3. When the referent reaches the appropriate state, the cleaner **may** execute the action via a background cleanup mechanism.
4. `cleanable.clean()` allows explicitly requesting the action to run; each registration is cleaned at most once by contract.
5. The action **must not hold a strong reference to the referent**, otherwise the referent might never become eligible for automatic cleanup.
6. The cleanup action must handle lifecycle/concurrency appropriately; do not rely on background timing to ensure resource correctness.

### 14.1. When is Cleaner useful?

When you build an abstraction with a special native resource/handle and want a **safety net** in case the client forgets to close it. It does not mean developers should omit `close()` and just wait for the Cleaner thread to run.

### 14.2. Do not use a cleanup action that captures `this`

Flawed in design:

~~~java
cleaner.register(this, () -> release(this.handle));
~~~

The lambda can capture `this`; the action referenced by the Cleaner keeps the referent reachable, defeating the goal of automatic cleanup.

Instead, separate the state/action owner into an independent object that does not hold the referent:

~~~java
State state = new State(nativeHandle);
cleaner.register(this, state);
~~~

This is a **conceptual fragment**, where State must not hold a strong reference back to the referent and must handle releasing the handle once on its own.

### 14.3. Do not print background Cleaner output and call it deterministic

A unit test that writes `System.gc(); assert cleanupPrinted;` may pass on one machine yet fail on another. The demo below calls `clean()` explicitly to verify once-only semantics, without relying on GC timing.

## 15. Complete program 6 — Cleaner explicit clean with a deterministic result

File **`CleanerExplicitDemo.java`**:

~~~java
import java.lang.ref.Cleaner;
import java.lang.ref.Reference;
import java.util.concurrent.atomic.AtomicInteger;

public class CleanerExplicitDemo {
    public static void main(String[] args) {
        Cleaner cleaner = Cleaner.create();

        Object referent = new Object();
        AtomicInteger cleanupCount = new AtomicInteger();

        Cleaner.Cleanable cleanable =
                cleaner.register(referent,
                        cleanupCount::incrementAndGet);

        System.out.println("Before clean = "
                + cleanupCount.get());

        cleanable.clean();
        cleanable.clean();

        System.out.println("After clean = "
                + cleanupCount.get());

        Reference.reachabilityFence(referent);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CleanerExplicitDemo.java
java CleanerExplicitDemo
~~~

**Exact stdout:**

~~~text
Before clean = 0
After clean = 1
~~~

### 15.1. Why does the action not retain the referent?

The method reference `cleanupCount::incrementAndGet` only holds the AtomicInteger, without capturing the referent. `Reference.reachabilityFence(referent)` at the end ensures the referent is considered strongly reachable up to that point; automatic cleanup does not run early in place of `clean()` in this illustration.

### 15.2. Why does calling clean twice increment only once?

A Cleaner registration is cleaned at most once. The second `clean()` call does not run the action again.

### 15.3. What the demo does not claim

There is no call to `System.gc()`, no measurement of the background Cleaner thread, and no promise that the JVM will clean an unreachable referent within any deadline. This is a **demonstration of the once-only and explicit cleanup API**, not a replacement for try-with-resources for real files/sockets.

### 15.4. When should Cleaner be avoided altogether?

If a resource does not require a native cleanup safety net, or if a framework already provides a reliable lifecycle manager, adding a Cleaner may only increase complexity and overhead. Use the simplest design that satisfies the ownership contract.

## 16. Strong, soft, weak, and phantom references: different reachability effects

Java has special reference types in `java.lang.ref` for building caches and lifecycle management tools:

| Reference | Main idea | Should it replace `close()`? |
| --- | --- | --- |
| Strong reference | Regular reference that keeps an object strongly reachable | No, it is only ownership/reachability |
| `SoftReference<T>` | Can be cleared by the GC according to memory-pressure policy | No |
| `WeakReference<T>` | Does not hold the referent strongly; can be cleared by the GC when weakly reachable | No |
| `PhantomReference<T>` | Specialized reachability-state tracking via ReferenceQueue; `get()` does not return the referent | No |
| `Cleaner.Cleanable` | Cleanup registration based on phantom reachability/explicit clean | Fallback, does not replace deterministic close |

### 16.1. WeakReference is not “a lighter strong reference”

If only weak references remain to an object (and no other references keep it strongly/softly reachable under runtime rules), the collector can clear weak references when it detects the appropriate state. **This does not mean weak.get() automatically turns null immediately after System.gc() on every JVM.**

### 16.2. SoftReference is not a cache policy that guarantees performance

It can be used for some cache-related designs, but soft-reference clearing depends on GC/memory policies and does not replace a size-bounded cache with clear metrics/eviction. There is no promise that a cached value will stay until “the heap is nearly full” at a fixed threshold.

### 16.3. PhantomReference is used with a queue and reference processing

Phantom references are typically used when implementing specialized cleanup/tracking. `get()` does not provide the referent for manipulation; code must maintain separate state. It is not the default choice for application-level resource ownership.

### 16.4. ReferenceQueue also has no deadline

When a reference is enqueued depends on the garbage collector/reference processing. Do not write correctness-critical logic that “waits for the queue to receive it within exactly 100 ms” just because System.gc() was called.

## 17. Complete program 7 — WeakReference and asserting only what can be known

File **`WeakReferenceHintDemo.java`**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceHintDemo {
    static final class Data {
        final String text;

        Data(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        Data strong = new Data("Java");
        WeakReference<Data> weak =
                new WeakReference<>(strong);

        System.out.println("Before release = "
                + (weak.get() == strong));

        Reference.reachabilityFence(strong);
        strong = null;

        System.gc();

        System.out.println("After hint = unspecified");
        System.out.println("No deterministic null assertion");
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 WeakReferenceHintDemo.java
java WeakReferenceHintDemo
~~~

**Exact stdout:**

~~~text
Before release = true
After hint = unspecified
No deterministic null assertion
~~~

### 17.1. Why is “Before release” true?

The strong variable still holds the object, and the weak reference points to the same referent. `Reference.reachabilityFence(strong)` helps ensure it remains strongly reachable up to the call point, preventing liveness optimizations from obscuring the demonstration's intent.

### 17.2. Why not print `weak.get()==null` at the end?

The result depends on when the collector runs and how weak references are processed. A program may print true or false at that point; presenting either one as the “exact” stdout would be an inaccurate promise.

### 17.3. Do not use `System.gc()` to synchronize a weak cache

A weak cache needs to accept that entries disappear on their own without following an application deadline. Logic must always handle a cache miss by rebuilding the value, rather than depending on when the weak reference is cleared.

## 18. Resource and memory issues are two independent axes

Comparison:

~~~text
An object is still strongly reachable, yet close() has already run
    → The Java wrapper still exists; the resource may already be closed.

An object is unreachable, yet has not been garbage collected
    → Heap space may not be reclaimed yet; the resource may still be unclosed.

An object has been garbage collected
    → Related heap memory may be reused,
      but there is no general rule that the external resource
      was definitely closed on time.

An object is held in a static cache indefinitely
    → The GC cannot release the object on its own as a leak fix,
      because the program still keeps it reachable.
~~~

### 18.1. The right pair of questions when debugging

- **Memory leak / heap pressure?** Who is holding strong references? What do heap dumps/dominators/retained size show? Does the cache have bounds?
- **Resource leak / connection exhaustion?** Does the owner close the resource on every exception path? Does the pool return the connection according to contract? Are listeners unsubscribed? Are threads/executors shut down?

Both can happen at the same time. For example, keeping a Connection object in a static collection while forgetting to close it both extends the object lifetime and retains the external resource.

### 18.2. System.gc cannot “close” dead references in a collection

The GC cannot selectively delete entries that a List still holds. Define the collection's lifecycle and a remove/evict policy. This is more of a root-cause fix than calling explicit GC.

## 19. Complete program 8 — close drops the strong reference to an internal buffer

A useful pattern when an object may still exist after closing the resource is to make the closed state explicit and not retain large data that is no longer needed.

File **`BufferLifecycleDemo.java`**:

~~~java
public class BufferLifecycleDemo {
    static final class BufferOwner implements AutoCloseable {
        private byte[] data;
        private boolean closed;

        BufferOwner(int size) {
            data = new byte[size];
        }

        int size() {
            if (closed) {
                throw new IllegalStateException("Buffer closed");
            }
            return data.length;
        }

        boolean isClosed() {
            return closed;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                data = null;
            }
        }
    }

    public static void main(String[] args) {
        BufferOwner owner = new BufferOwner(8);

        try (owner) {
            System.out.println("Inside size = " + owner.size());
        }

        owner.close(); // Idempotent according to this implementation.

        System.out.println("Closed = " + owner.isClosed());

        try {
            owner.size();
        } catch (IllegalStateException ex) {
            System.out.println("Use after close rejected");
        }

        System.out.println("Reclaimed bytes = not asserted");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 BufferLifecycleDemo.java
java BufferLifecycleDemo
~~~

**Exact stdout:**

~~~text
Inside size = 8
Closed = true
Use after close rejected
Reclaimed bytes = not asserted
~~~

### 19.1. Why is explicit null meaningful here?

`BufferOwner` is still held by the variable owner to check isClosed after the scope. However, after close, assigning `data = null` removes the strong reference from owner to the old array. If there are no other aliases, the array can become GC-eligible earlier than the owner.

### 19.2. Is this an approach every class should use?

No. Overusing `field = null` throughout code reduces readability and is usually unnecessary. In this example, close **has a clear business meaning**: the object transitions to the closed state, the buffer must no longer be read, and it can proactively drop retention of the large buffer. For ordinary short-lived locals, nulling just to “force GC” is unnecessary.

### 19.3. You cannot conclude that 8 bytes were returned to the OS

`new byte[8]` has its own object header/alignment, JVM allocation rules, and GC timing. Setting a field to null does not return memory directly. The demo does not print the number of reclaimed bytes because that is not guaranteed.

## 20. Listener leak: unregister instead of calling GC

A practical type of retention leak is an event bus retaining listeners after a screen/session should have ended.

Diagram:

~~~text
Long-lived EventBus (rooted by service)
    |
    v
List<Consumer<Event>>
    |
    v
listener lambda
    |
    v
captured Screen/Session/Controller
    |
    v
large model/view graph
~~~

If the screen closes while the listener remains in the List, the event bus can keep the screen and the entire captured graph reachable. `System.gc()` cannot fix that registration/unregistration logic.

### 20.1. Return a subscription handle implementing AutoCloseable

A good API can use:

~~~java
try (Subscription sub = bus.subscribe(listener)) {
    // The listener only lives within this scope.
}
~~~

After the scope, `Subscription.close()` performs the unsubscribe. Another kind of cleanup needs to be designed with lifecycle hooks if the subscription must outlive a lexical try block.

### 20.2. Listener registration may need thread safety

If the bus receives events on multiple threads, the listener list and unsubscribe must be synchronized according to the API. The example below is single-threaded to keep stdout deterministic and focus on lifecycle; do not treat it as a production-ready concurrent event bus.

## 21. Complete program 9 — unsubscribe is a deterministic lifecycle action

File **`ListenerLifecycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class ListenerLifecycleDemo {
    static final class EventBus {
        private final List<Consumer<String>> listeners =
                new ArrayList<>();

        Subscription subscribe(Consumer<String> listener) {
            listeners.add(listener);
            return new Subscription(this, listener);
        }

        void publish(String event) {
            for (Consumer<String> listener : listeners) {
                listener.accept(event);
            }
        }

        int listenerCount() {
            return listeners.size();
        }

        private void unsubscribe(Consumer<String> listener) {
            listeners.remove(listener);
        }
    }

    static final class Subscription implements AutoCloseable {
        private final EventBus bus;
        private final Consumer<String> listener;
        private boolean closed;

        Subscription(EventBus bus, Consumer<String> listener) {
            this.bus = bus;
            this.listener = listener;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                bus.unsubscribe(listener);
            }
        }
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();

        try (Subscription subscription =
                     bus.subscribe(e ->
                             System.out.println("received " + e))) {
            System.out.println("During = " + bus.listenerCount());
            bus.publish("hello");
        }

        System.out.println("After = " + bus.listenerCount());
        bus.publish("ignored");
        System.out.println("Publish after close finished");
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 ListenerLifecycleDemo.java
java ListenerLifecycleDemo
~~~

**Exact stdout:**

~~~text
During = 1
received hello
After = 0
Publish after close finished
~~~

### 21.1. Why does the final publish not print "received ignored"?

The listener was removed by Subscription.close when try-with-resources finished. EventBus no longer has a callback to invoke.

### 21.2. Advantage over System.gc

The cleanup has an observable contract: `listenerCount()==0` after close. Regardless of when GC runs, the program no longer receives events outside the lifetime. This is correctness of business behavior, not merely saving heap space.

### 21.3. Subscriptions may still be referenced while no longer registered

After close, the Subscription instance may still remain in a local variable in another implementation, yet EventBus has already removed the listener. That cleanly separates **the registration lifecycle** from **the lifecycle of the Java wrapper object**.

## 22. OutOfMemoryError: can calling System.gc fix it?

`OutOfMemoryError` occurs when the JVM cannot satisfy an allocation request under certain conditions. You should not rely on:

~~~java
try {
    // Allocate indefinitely.
} catch (OutOfMemoryError error) {
    System.gc();
    // Continue as if fixed.
}
~~~

This is an **anti-pattern**, not a demo to run. When an application severely lacks memory, recovery depends on the system state and the type of OOME; calling explicit GC does not resolve a graph still retained by a leak or an incorrect capacity budget.

### 22.1. Find the root cause, not just the symptom

The cause may be:

- **Actual memory needed exceeds the heap configuration**.
- Retention leak: caches, listeners, queues, or static maps holding objects that are no longer useful.
- Unbounded workload or concurrency.
- Classloader/metaspace leak or native memory/direct buffers, not necessarily due to Java heap object count.
- Nearly enough memory, yet allocation patterns/fragmentation/collector constraints apply in the specific situation.
- Different memory areas: the OOME message and metrics need to be read by their exact type.

### 22.2. System.gc cannot make the collector delete reachable objects

If 1 million objects are still in a static Map used by the program, an explicit GC request does not turn them into unreachable objects. The root cause is the retention policy/map lifecycle.

### 22.3. When production experiences an OOME

It usually requires combining heap dumps/GC logs/JFR, code profiling, capacity planning, and appropriate collector/JVM configuration. Do not write application logic that catches OOME and continues as if nothing were wrong, especially for critical server state.

## 23. Memory metrics: do not draw conclusions from a number before/after System.gc

Java has APIs such as:

~~~java
Runtime runtime = Runtime.getRuntime();
long total = runtime.totalMemory();
long free = runtime.freeMemory();
long max = runtime.maxMemory();
~~~

This is a **fragment**. They return runtime heap information at the moment of observation, not a direct measure of “all objects still alive according to business logic”.

### 23.1. `totalMemory()`

Typically the heap memory currently available to the JVM in an implementation-specific sense described by the API; it does not mean “the heap bytes of all Java objects created since startup”.

### 23.2. `freeMemory()`

Free memory within the managed JVM heap at the time of the query; it can fluctuate due to allocations, collection, expansion/contraction, and concurrent collector activity.

### 23.3. `maxMemory()`

An estimate of the maximum limit the JVM attempts to use for memory management according to the configured runtime; it is not the exact physical RAM that the process will use.

### 23.4. `used = total - free` is also just a snapshot

It can be used to observe trends in a controlled benchmark, but it does not prove that object A has been collected. Concurrent JVM/JIT/collector activity can cause these values to fluctuate, and background allocations can occur.

### 23.5. Do not specify hardcoded memory byte numbers in stdout

A demo printing `totalMemory()` and `freeMemory()` will produce different results depending on the machine, heap flags, and timing. If presented, explicitly state that **the measurements depend on the environment** rather than fabricating a fixed value.

## 24. Diagnosing the JVM with appropriate tools and logging

When you need to analyze GC behavior:

- **GC unified logging** on HotSpot JDK 17: for example `-Xlog:gc*` to observe GC events/configurations at an appropriate level; output depends on the JVM.
- **Java Flight Recorder (JFR)**: collect events and analyze allocation/GC/pause profiles when enabled/permitted.
- **`jcmd`**: JDK tool for diagnostic commands appropriate to the process/JVM, such as viewing VM flags and thread/heap information; supported commands must be verified on the current version.
- **Heap dump + dominator/retained-size analysis**: find the strong-reference paths retaining objects.
- **Application telemetry**: queue sizes, cache hit/eviction, number of open connections, active tasks, listener counts, and request patterns.

Example of launching a compiled HotSpot application with GC logging:

~~~bash
java -Xlog:gc* MyApplication
~~~

**This is only an illustrative command**, not a program of this lesson, and it has no fixed stdout; actual logs, tags, format, pauses, and timing depend on the runtime.

### 24.1. Do not confuse GC count with live object count

The number of collection events is not the number of reclaimed objects. A single collection can process multiple heap regions and different kinds of work. Data from `GarbageCollectorMXBean` also does not by itself state that a specific object was reclaimed.

### 24.2. Heap dumps contain sensitive data

Heap dumps can contain session tokens, identifiers, payloads, and secrets. Collect, store, transfer, and delete them according to security policies; do not attach real heap dumps to public documentation.

### 24.3. Measure application workload before tuning

If the application runs out of database connections, GC logs do not replace inspecting pool usage and missing closes. If the heap grows, measure retained objects and cache sizes before adding System.gc. Tuning the collector does not fix semantic leaks of resource owners.

## 25. JVM configuration can affect explicit GC

JVM distributions and GC implementations have configuration knobs. In some HotSpot configurations, a flag such as:

~~~bash
java -XX:+DisableExplicitGC MyApplication
~~~

can prevent explicit `System.gc()`/`Runtime.gc()` requests from triggering GC in the usual way. This flag **does not disable automatic GC**, because the JVM still needs garbage collection to handle allocation/memory management.

Some HotSpot collectors/configurations also have options adjusting how explicit GC is executed, such as mechanisms related to concurrent explicit collection. Those options are not portable guarantees across all Java VMs.

### 25.1. Do not write code that depends on flags

Application correctness must not change merely because an admin enables or disables explicit GC. If resource correctness requires System.gc, the design is already wrong.

### 25.2. Explicit GC can increase pauses

On some collectors, an explicit request can trigger substantial work. Placing System.gc inside request handlers, every transaction, or tests can worsen throughput/latency.

### 25.3. There is no single optimal configuration command for all cases

Heap sizes, garbage collector selection, application allocation rate, pause targets, and CPU/memory budgets all affect the outcome. Tuning decisions must be based on metrics from the real workload.

## 26. GC tuning differs from fixing a memory leak

Let's categorize:

| Symptom | Question to answer | Resolution approach |
| --- | --- | --- |
| Long-term heap usage growth | Which objects hold retained size and why? | Fix strong refs, cache policy, queue bounds |
| Frequent GC/pauses | Allocation rate, live set, collector/heap config? | Profile + optimize allocation and tuning |
| File descriptors increasing | Are streams/sockets closed properly on all branches? | AutoCloseable/try-with-resources |
| Database pool out of connections | Are borrowed connections returned to the pool? | try-with-resources, timeout, ownership |
| Listener count only increases | Is unsubscribe called when the screen/session ends? | Subscription.close or remove |
| ThreadLocal memory increasing | Long-lived threads; have values been removed? | try/finally remove |
| Executor threads do not stop | Is there a shutdown/await lifecycle? | shutdown, awaitTermination, cancel tasks |
| Low weak cache hit rate | Are weak references cleared or is it cache-miss logic? | Choose an appropriate cache policy |
| OOME with a large static map | Does reachability from the map exceed business needs? | Bound entries, eviction, ownership |
| Test expects weak.get null immediately | Assuming System.gc is deterministic? | Test invariant logic, not collection deadline |

Some problems can overlap. However, **System.gc() is not a general solution for any row in the table**.

## 27. Unit tests: test what can be guaranteed

### 27.1. Do not write a test like this

~~~java
Object value = new Object();
WeakReference<Object> weak = new WeakReference<>(value);
value = null;
System.gc();
assert weak.get() == null;
~~~

This is **code intentionally illustrating a wrong expectation**. The test depends on collector timing, JVM flags, and runtime liveness. It may pass or fail inconsistently even when the application is correct.

### 27.2. Test that close() is called exactly once

Instead of hoping GC cleans up the connection, use a fake resource with a counter/flag; run the code through try-with-resources and assert the counter/flag. This is a deterministic unit test of the lifecycle contract.

### 27.3. Test unsubscribe

When closing Subscription, assert listenerCount becomes 0; subsequent published events no longer trigger the callback. There is no need to call System.gc to verify that the owner has released the registration.

### 27.4. Test retention policy

For a bounded cache, assert that size does not exceed capacity or that entries are evicted according to policy; do not depend on weak-reference clearing timing for expected values unless necessary.

### 27.5. When genuinely testing GC-sensitive infrastructure

Libraries implementing Cleaner/weak caches may need integration/stress tests with appropriate timeouts, polling, and acceptance criteria, yet results must be interpreted carefully because the JVM does not guarantee reclaiming every object within an arbitrary deadline. Do not turn a flaky GC test into a correctness mechanism for business code.

## 28. Lifecycle in APIs: who owns the responsibility to close?

A clear resource design usually asks these questions:

1. **Who creates the resource?**
2. **Who uses it?** Do multiple consumers share it?
3. **Who is the owner responsible for closing/shutting down/unsubscribing?**
4. **Which scope marks “work done”?**
5. **If an exception occurs partway through, where is cleanup performed?**
6. **Is there an idempotent close contract?**
7. **Are there any aliases still using the resource after close?**
8. **Are pool/lease semantics needed rather than a physical close?**
9. **Must cleanup be thread-safe?**
10. **Do user responses/shutdown operations have a clear deadline?**

Those are questions the GC cannot answer on its own. The JVM knows about the reachability of Java objects, not the business moment when a “transaction completes”, a “UI tab closes”, or a “request is canceled” according to domain rules.

### 28.1. “Who opens closes” is only a heuristic

The method creating a resource often closes it within that scope, but sometimes a factory returns the resource to the caller; in that case, **ownership is explicitly transferred through the API contract**. What matters is always having a responsible owner, not necessarily the exact same method creating and closing in every architecture.

### 28.2. Pooling semantics

`Connection.close()` in a JDBC connection pool can typically return the logical connection to the pool instead of closing the physical TCP connection immediately. That is still a valid lifecycle operation according to the contract. The GC does not know when to return a lease to the pool.

### 28.3. Asynchronous scopes

With CompletableFuture, reactive streams, or callbacks, a lexical try block may end before the async work finishes. In that case, the owner may need to attach cleanup in a completion handler/structured scope, ensuring the resource lives long enough and is closed at the right time. **Do not use System.gc to synchronize the completion of async tasks.**

## 29. Common mistakes when learning System.gc and object lifecycle

### 29.1. “System.gc() forces the JVM to collect immediately”

**False.** This is a hint/best-effort request, with no guarantee of timing or a specific collection.

### 29.2. “After System.gc(), all unreachable objects have been deleted”

**False.** There is no guarantee of exact per-object reclamation at the moment the call returns.

### 29.3. “The GC will close the file when the object leaves scope”

**Not a resource ownership contract.** Use close and try-with-resources.

### 29.4. “Writing obj=null frees memory”

**Not directly.** It only clears one reference. The object may still have aliases; reclamation is decided by the GC and JVM.

### 29.5. “If two objects reference each other cyclically, they leak”

**Not automatically.** Unreachable cycles can be garbage collected; the issue is whether a reference path from roots still exists.

### 29.6. “When a static List gets full, the GC automatically deletes unnecessary items”

**False.** Entries remain strongly reachable through the List; there must be eviction/clear/remove logic.

### 29.7. “The increase in GC free memory must equal the size of object X just deleted”

**False.** Heap metrics involve many factors, allocation headers, collector policies, and other allocations; you cannot infer exact object reclamation from two snapshots.

### 29.8. “System.gc is always a full stop-the-world GC”

**False as a guarantee.** The JVM/collector/configuration determines behavior; it may incur a pause, but there is no single portable outcome.

### 29.9. “Using Cleaner means close is not needed”

**False.** Cleaner is a fallback; automatic execution has no deadline for correctness-critical cleanup.

### 29.10. “finalize is the standard way to clean up in Java 17”

**False.** Finalization is unreliable and considered an obsolete mechanism. Use an explicit lifecycle API.

### 29.11. “WeakReference.get will be null immediately after System.gc”

**False.** Do not write tests assuming the timing of clearing.

### 29.12. “SoftReference is a cache with a guaranteed TTL”

**False.** Clearing depends on runtime policies; there is no business TTL contract.

### 29.13. “After close completes, the Java object is reclaimed immediately”

**False.** The wrapper object may remain strongly reachable and be GC'd later.

### 29.14. “Adding System.gc in finally is a cleanup approach”

**False.** Finally should call explicit close/remove/unsubscribe, not put a GC hint in its place.

### 29.15. “The more frequently GC runs, the more RAM the app saves”

There is no guarantee. Frequent collections can cause overhead and affect throughput/latency; data measurements are needed to draw conclusions.

### 29.16. “Simply increasing -Xmx fixes a memory leak”

It does not address the root cause if unbounded retention keeps growing. Increasing capacity can help a legitimate workload, but a leak will reappear.

### 29.17. “Using System.gc to handle OutOfMemoryError is sufficient”

Unreliable. Analyze the OOME type and retaining paths/capacity, and avoid catching OOME and treating the app as recovered.

### 29.18. “List.clear will close each AutoCloseable element”

No. List.clear only modifies collection references and does not call resource-specific close.

### 29.19. “ThreadLocal keys are weak, so values cannot be retained for long”

False as a general assumption. Long-lived threads/ThreadLocal maps have their own lifecycle; call remove in the appropriate scope when needed.

### 29.20. “Try-with-resources only closes when the block completes normally”

False. It also closes when the block exits due to an exception; suppressed exceptions preserve the close failure details appropriately.

## 30. Self-check exercises with answers

**Question 1.** What does `System.gc()` return?

**Answer:** Return type `void`; it does not return the number of bytes/objects reclaimed or a boolean indicating “GC finished”.

**Question 2.** Is System.gc equivalent to Runtime.getRuntime().gc?

**Answer:** In terms of API effect, System.gc is an equivalent way to request Runtime.gc; both are hints to make a GC effort.

**Question 3.** Is the collector guaranteed to run a full GC on every call?

**Answer:** No; it still depends on the JVM, collector, flags, and runtime policy.

**Question 4.** Is an object guaranteed to be reclaimed before the method returns?

**Answer:** There is no specific guarantee for individual objects.

**Question 5.** Will an object still in a static List be deleted by the GC just because System.gc is called?

**Answer:** No, if it remains strongly reachable through the List under runtime semantics.

**Question 6.** Does `object = null` delete the object from the heap?

**Answer:** Not directly; it only clears one reference, and the object may still have aliases.

**Question 7.** Can the Java GC reclaim an object cycle that is no longer reachable?

**Answer:** Yes; circular references are not automatically a memory leak.

**Question 8.** Should an `InputStream` wait for the GC to close the file?

**Answer:** No; use close/try-with-resources according to ownership.

**Question 9.** Which interface does try-with-resources require?

**Answer:** AutoCloseable or a subtype such as Closeable.

**Question 10.** In what order do multiple resources in try-with-resources close?

**Answer:** In reverse order of the declaration/initialization of the resource variables.

**Question 11.** If both the body and close throw an exception, which one is primary?

**Answer:** The body exception is normally primary; the close exception is added to suppressed exceptions according to the rules.

**Question 12.** Does closing a resource make the Java wrapper object unreachable immediately?

**Answer:** Not necessarily; aliases/the owner may still hold a reference.

**Question 13.** Does Cleaner guarantee automatic cleanup immediately after System.gc?

**Answer:** No; there is no deadline.

**Question 14.** Can Cleanable.clean be called explicitly?

**Answer:** Yes; the action for a registration is cleaned at most once.

**Question 15.** What is the problem with a cleanup action capturing the referent via `this`?

**Answer:** It can keep the referent strongly reachable, preventing automatic cleanup from running as expected.

**Question 16.** Can `weak.get()==null` immediately after a GC hint be tested as an invariant?

**Answer:** No; clearing/timing is non-deterministic.

**Question 17.** Should finalize be used for new production cleanup?

**Answer:** No; finalization is obsolete/unreliable.

**Question 18.** Do heap reclamation and native file handle closure share the same lifecycle?

**Answer:** No; they are separate responsibilities.

**Question 19.** How should a leak caused by a still-registered listener be fixed?

**Answer:** Call unsubscribe/removeListener/Subscription.close in the proper owner scope.

**Question 20.** How should a leak caused by an unbounded cache be fixed?

**Answer:** Limit size, apply eviction, TTL, clear/remove, and monitor retaining references according to the domain.

**Question 21.** Should System.gc be called after every HTTP request?

**Answer:** Usually no; it does not replace lifecycle management and can increase overhead.

**Question 22.** Does `-XX:+DisableExplicitGC` disable all automatic GC?

**Answer:** No; it applies to explicit requests per HotSpot behavior, while automatic GC continues operating.

**Question 23.** Is `Runtime.freeMemory()` equal to the exact bytes of object A just reclaimed?

**Answer:** No; it is a runtime heap snapshot not tied to object A.

**Question 24.** What does a heap dump help find in a retention leak?

**Answer:** Retaining paths, dominant owners, large reachable graphs, and object counts, depending on tool capabilities.

**Question 25.** Does GC logging have fixed output across all JDKs/collectors?

**Answer:** No; flags, runtime events, and log formats differ.

**Question 26.** How should ThreadLocal in a pool be cleaned up?

**Answer:** Usually `remove()` in finally after the task scope if you do not want the value to persist to the next task.

**Question 27.** Can try-with-resources be used with a custom subscription?

**Answer:** Yes, if Subscription implements AutoCloseable and close releases the registration.

**Question 28.** If a reference still holds an object, can System.gc force the JVM to treat the object as dead?

**Answer:** No, under valid strong reachability semantics.

**Question 29.** Is measuring GC with System.nanoTime before/after System.gc sufficient to benchmark the collector?

**Answer:** No; JVM flags, JIT, allocation profile, warm-up, and concurrent events introduce noise. Use appropriate profiling/benchmarking methods.

**Question 30.** Distinguish the meaning of `close()` and `System.gc()` in one sentence?

**Answer:** Close performs a resource lifecycle operation according to the API contract; System.gc only hints to the JVM to make an effort to reclaim unreachable heap objects when appropriate.

## 31. Hands-on exercises

### Exercise 1 — aliases and reachability

Create a Node object, keep two references, and assign one variable to null. Explain why the object is still reachable through the other variable. Then clear the remaining alias and distinguish between “eligible” and “collected”. Do not use assertions about GC timing.

### Exercise 2 — fixing a memory retention leak

Write a static List storing arrays and observe its size growing after multiple calls. Add bounds/clear to maintain the size according to a policy. Demonstrate that `System.gc()` does not automatically reduce List.size.

### Exercise 3 — building an AutoCloseable resource

Create FakeConnection with `opened/closed` counters, use try-with-resources on two connections, and verify reverse closing order and that the open count returns to 0.

### Exercise 4 — exception safety

Create an AutoCloseable that throws an exception in close while the try body also throws an exception. Print the primary exception along with getSuppressed; explain why this approach is better than calling close carelessly in finally without protecting the primary exception.

### Exercise 5 — Cleaner

Create a Cleaner with a cleanup action that holds only independent state and does not capture the referent. Call Cleanable.clean twice and assert count=1; explain why you do not wait for System.gc to create a deterministic unit test.

### Exercise 6 — weak reference

Create a WeakReference to an object, drop the strong reference, and then call System.gc. Print a message stating that `weak.get` may be null or non-null at the time of the check; **do not assert a fixed outcome**.

### Exercise 7 — listener subscription

Build an EventBus whose subscribe returns an AutoCloseable subscription; verify that listenerCount decreases upon close. Compare with the case where forgetting to close causes a long-lived bus to retain the callback.

### Exercise 8 — analyzing GC methodically

Run a Java program with JDK GC logging and application-level metrics such as cache size/active connections. Distinguish between a collector event and semantic cleanup. Do not treat measurements from a single laptop as a guarantee across all machines.

## 32. Practical implementation checklist

1. Have you identified which resources are managed by the GC and which resources require explicit closing?
2. If an API creates an AutoCloseable, is the owner clear?
3. Is there proper try-with-resources or finally handling for all exception paths?
4. Are multiple resources closed in a sensible order?
5. Are suppressed exceptions handled when debugging close failures?
6. Is idempotent close used where the contract genuinely needs it?
7. Is there any code relying on finalize? If so, replace it.
8. Is Cleaner relied upon for a business deadline? If so, change the design.
9. Does the Cleaner action accidentally hold a strong reference to the referent?
10. Are weak/soft references being used as storage guaranteed to persist?
11. Are there unit tests assuming System.gc makes weak.get null immediately?
12. Are static maps/lists/registries retaining data for too long?
13. Does the cache have bounded size/TTL/eviction policy and metrics?
14. Do listeners unsubscribe when the owner's scope ends?
15. Are ThreadLocal values removed in the right scope?
16. Do executor pools have a clear shutdown/await lifecycle?
17. Is a large object graph being retained by callbacks/lambdas/queues?
18. Do you avoid pointless null assignments on local variables just to “speed up GC”?
19. Are there times when nulling a field represents an actual closed state that makes sense under the contract?
20. Do you recognize aliases still holding the object even though one reference is null?
21. Do you distinguish among reachable, eligible, and reclaimed?
22. Do you understand that System.gc is only a hint, not a memory deletion operation?
23. Do you avoid calling System.gc in request loops or routine cleanup?
24. Do you consider JVM flags/collector implementation when explaining behavior?
25. Do you avoid equating used heap with OS resident set size?
26. Do you rely on real GC logs/JFR/heap dumps rather than assumptions during production issues?
27. Do you ensure heap dumps/logs are handled securely?
28. Do you distinguish memory leaks from file/socket/connection resource leaks?
29. Is your correctness solution independent of GC timing?
30. Are ownership and the resource lifecycle contract documented for callers?

## 33. Conclusion

**`System.gc()` is a hint to the JVM to make an effort to perform garbage collection; it is not a way to delete objects on command, does not provide a deadline, and cannot turn an object that is still strongly reachable into an unreachable one.** The same program can have multiple valid GC timing outcomes depending on the JVM, collector, and configuration.

An object can only be reclaimed when the runtime determines it is no longer used under the applicable reachability semantics. Clearing a local reference, removing an entry from a collection, and actually running the collector are different events. Cycles are not necessarily leaks, but static caches, event listeners, ThreadLocal values, or long-lived queues can retain references unintentionally.

**Resource lifecycle management must be proactive:** use `AutoCloseable`, `try-with-resources`, `close()`, `shutdown()`, `unsubscribe()`, `remove()`, and an ownership policy at the right time. Cleaner and specialized references can serve as supporting tools in advanced cases, not as guarantees of deterministic cleanup. Finalization is not a reliable choice for new designs.

When an application consumes a lot of memory or encounters an OOME, do not start by “adding System.gc”. Find **who is holding references, whether they need to be kept, which resource owner must close them, and whether the workload exceeds capacity**, then measure using appropriate profiling/GC logs/JFR/heap analysis. The Java GC handles automatic memory reclamation; **lifecycle correctness remains the responsibility of application design**.
