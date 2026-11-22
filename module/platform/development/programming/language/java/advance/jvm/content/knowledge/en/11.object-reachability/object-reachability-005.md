# ReferenceQueue and When an Object Is Notified as Reference-Processed

## 1. What Is ReferenceQueue Used to Observe?

`java.lang.ref.ReferenceQueue<T>` is a queue that receives **reference objects** (`Reference`), not the original tracked object (*referent*). When a `WeakReference`, `SoftReference`, or `PhantomReference` is registered with a queue and the GC detects an appropriate reachability change, the reference may be **cleared** and then **enqueued**; Java code uses `poll()` or `remove()` to **dequeue** that `Reference` object.

It is necessary to distinguish the events in logical sequence:

1. **Registration:** the application creates `new WeakReference<>(referent, queue)` or another appropriate reference type. Registration does not mean enqueueing.
2. **Reachability changes:** the object no longer has a strong reference path (*strong reachability*) from GC roots; however, it may still be affected by soft/weak/phantom references.
3. **GC detects it:** the garbage collector checks reachability at a time depending on the collector and workload. Assigning a variable to `null` does not force GC to run immediately.
4. **Clearing:** the reference is processed and no longer returns the referent via `get()`, depending on the reference type. Clearing and enqueueing are not necessarily the same operation or at the same time.
5. **Enqueue:** the reference object is placed into the queue; a reference not registered with a queue does not automatically appear here.
6. **Dequeue:** the application retrieves the enqueued reference and reads the metadata of the **reference object**, then updates the cache or cleans up the corresponding resource.

~~~text
Strong references disappear
           |
           v
GC may detect the reachability change
           |
           v
Process/clear registered References
           |
           v
Put the Reference object into ReferenceQueue
           |
           v
Application poll() / remove()
           |
           v
Clean cache entry, process metadata, cleanup if appropriate
~~~

**What an event does NOT prove:** it does not guarantee that GC has returned RAM to the OS, does not prove that memory bytes have been reused, is not a notification that the original object is still accessible, does not guarantee that the native resource has been closed, and **there is no deadline** from the time the object loses strong references until the application receives the event.

Also remember: `Reference.enqueue()` can be **called manually by the application itself**. If a queue has an entry, you cannot look solely at that entry and conclude for certain that the event came from the GC.

## 2. Reachability: strong, soft, weak, and phantom

Java defines object reachability levels related to GC, from strongest to weakest:

| Level / Type | Correct understanding | Can the referent be retrieved via `get()`? |
| --- | --- | --- |
| Strong reference | Normal strong reference path from a thread, static field, or reachable structure | Direct object access |
| `SoftReference<T>` | Does not prevent GC from clearing when memory demand/policy requires; may be suitable for memory-sensitive caches | Yes, before being cleared |
| `WeakReference<T>` | Does not keep the object alive merely because of a weak reference; GC processes it when the referent is only weakly reachable | Yes, before being cleared |
| `PhantomReference<T>` | Very weak level used for receiving notification/cleanup; does not allow the program to recover the referent | **No**: `get()` is always `null` |

**Strong references** are a crucial condition: if a static map, thread, cache value, or local variable still holds the object via a strong path, the object cannot be considered weakly reachable just because you created a `WeakReference` to it.

**SoftReference** gives the GC more options: it does not promise that as soon as strong references are gone, it will be cleared immediately. For production caches that need bounded memory, you should set size/TTL/eviction rather than relying on soft references as the sole limiting mechanism.

**WeakReference** is suitable for tracking weak keys, canonicalization, or objects that the system does not want to keep alive. It still requires GC to run and detect reachability. `weak.get() == null` can be observed before the reference object is returned by the queue.

**PhantomReference** is often used to coordinate cleanup after the GC determines the referent has reached the appropriate state. `phantom.get() == null` **right from creation**, even if the referent is still strongly referenced. Therefore, do not use `get()` to determine the timing of phantom notification.

A **reference object** itself is still a Java object; if the application discards the reference object before GC processes it, the notification may be lost. This consequence is extremely important for design.

## 3. Registration Is One-Way: The Queue Does Not Hold a Registration List

Look at the example:

~~~java
ReferenceQueue<Object> queue = new ReferenceQueue<>();
Object value = new Object();
WeakReference<Object> weak = new WeakReference<>(value, queue);
~~~

- `value` is the original object (*referent*).
- `weak` is the `WeakReference` object; it holds a **weak** link to `value`.
- `queue` is the destination that receives **weak**, if GC or the application enqueues `weak`.
- `queue.poll()` returns a `Reference<? extends Object>` or `null`; it does not return `value`.

The `java.lang.ref` package specification states clearly that the relationship of a registered reference to a queue is **one-way**: the queue should not be understood as a registry that automatically keeps strong references to all registered references.

The following style is **unreliable** if you want to receive events:

~~~java
new WeakReference<>(value, queue); // does not retain the WeakReference object
~~~

In real code, keep the **reference object** in a collection/registry until the event is processed or the registration is canceled. But do **not** hold the referent by another strong field, if the goal is for that object to be eligible for GC.

~~~text
Strong registry ──> TrackedWeakReference ──weak──> key object
       |
       └──> metadata (ID, cache key, native handle if appropriate)

The registry is allowed to hold the reference object.
The registry MUST NOT accidentally hold the key object via a strong path
if you want the key to become weakly reachable.
~~~

**Mistake:** a `WeakReference<T>` subclass containing `final T original` will keep the referent alive; calling `super(original, queue)` in the constructor cannot neutralize that strong field.

## 4. ReferenceQueue and Reference APIs to Distinguish

| API | Meaning | What MUST NOT be inferred |
| --- | --- | --- |
| `queue.poll()` | Try to retrieve an available reference **without waiting** | `null` does not prove the referent is still alive |
| `queue.remove()` | Wait and retrieve a reference when one appears | May wait indefinitely if there is no event |
| `queue.remove(timeoutMillis)` | Wait up to the timeout; may return `null` | Does not force GC to enqueue within the timeout |
| `ref.get()` | Retrieve the referent if the API allows and it has not been cleared | `null` does not prove the reference has been enqueued |
| `ref.clear()` | Clear the reference as requested by Java code | **Does not automatically enqueue** |
| `ref.enqueue()` | Try to enqueue from Java code and return boolean | The event may **not be created by GC** |
| `ref.refersTo(object)` | Ask whether the reference still points to that exact object | Not a tool to force GC |
| `ref.isEnqueued()` | Queue status at a point in time | **Deprecated Java 16+**, has races, do not use as a cleanup protocol |
| `Reference.reachabilityFence(x)` | Keep `x` strongly reachable up to the call site | Does not clean GC, does not enqueue |

For `remove(long timeout)`:

- `timeout > 0`: bounded wait (milliseconds), returns `null` if no reference is received within the wait time.
- `timeout == 0`: **wait indefinitely**, not non-blocking.
- To try without waiting: **`poll()`**.
- A thread interrupted while waiting may receive `InterruptedException`; the consumer must manage shutdown properly.

### `clear` differs from `enqueue`

~~~text
ref.clear()
   |
   +-- ref.get() may become null
   +-- queue does NOT automatically get an entry just because of clear()

ref.enqueue()
   |
   +-- application requests adding the reference to the queue
   +-- may happen while the original object is still strong
   +-- in Java 17 this operation also clears the reference
~~~

GC may clear a reference at one time and enqueue it at another time. Do not assume that `weak.get() == null` must be accompanied by `queue.poll() != null` **immediately**.

## 5. Runnable Java 17 Example, Deterministic Stdout: Manual Enqueue

The first example **intentionally does not wait for GC** to isolate API semantics. Create the file **`ReferenceQueueBasicsDemo.java`**:

~~~java
import java.lang.ref.PhantomReference;
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public final class ReferenceQueueBasicsDemo {
    public static void main(String[] args) {
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        Object referent = new Object();

        WeakReference<Object> weak = new WeakReference<>(referent, queue);
        PhantomReference<Object> phantom =
                new PhantomReference<>(referent, queue);

        System.out.println("weakAlive=" + (weak.get() != null));
        System.out.println("phantomGetNull=" + (phantom.get() == null));
        System.out.println("initialQueueEmpty=" + (queue.poll() == null));

        weak.clear();
        System.out.println("weakCleared=" + (weak.get() == null));
        System.out.println("clearDidNotEnqueue=" + (queue.poll() == null));

        boolean manualWeak = weak.enqueue();
        Reference<?> first = queue.poll();
        System.out.println("manualWeakEnqueued=" + manualWeak);
        System.out.println("firstIsWeak=" + (first == weak));

        boolean manualPhantom = phantom.enqueue();
        Reference<?> second = queue.poll();
        System.out.println("manualPhantomEnqueued=" + manualPhantom);
        System.out.println("secondIsPhantom=" + (second == phantom));

        Reference.reachabilityFence(referent);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac --release 17 ReferenceQueueBasicsDemo.java
java ReferenceQueueBasicsDemo
~~~

**Exact stdout verified with JDK 21 using `--release 17`:**

~~~text
weakAlive=true
phantomGetNull=true
initialQueueEmpty=true
weakCleared=true
clearDidNotEnqueue=true
manualWeakEnqueued=true
firstIsWeak=true
manualPhantomEnqueued=true
secondIsPhantom=true
~~~

### Explanation

1. `weak.get() != null` because `referent` is still strongly held, and `reachabilityFence(referent)` ensures the object cannot be considered unused before the end point.
2. Phantom `get()` is always null; there is no proof that the object has been GC'd.
3. Merely registering a reference with a queue does not enqueue it.
4. `weak.clear()` makes weak `get()` null, but `poll()` is still null.
5. `weak.enqueue()` returns true and `poll()` returns the exact `weak` object.
6. `phantom.enqueue()` returns true and `poll()` returns the exact `phantom` object.
7. Both enqueues are **manual** actions, while the referent is **not yet dead** in the GC sense. This is why the event must not automatically be called `OBJECT_COLLECTED`.

Because the example does not depend on the collector, stdout **does not need** `System.gc()` and has no non-deterministic wait loop.

## 6. GC Observation Example: Fixed Stdout Cannot Be Promised

This section has complete Java 17 code, but **intentionally does not write a single fixed result**, because GC scheduling varies by JVM. Create **`WeakQueueObservationDemo.java`**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public final class WeakQueueObservationDemo {
    private static WeakReference<byte[]> create(
            ReferenceQueue<byte[]> queue) {
        byte[] payload = new byte[1024 * 1024];
        return new WeakReference<>(payload, queue);
    }

    public static void main(String[] args)
            throws InterruptedException {
        ReferenceQueue<byte[]> queue = new ReferenceQueue<>();
        WeakReference<byte[]> ref = create(queue);

        System.gc(); // Request, not a GC guarantee
        Reference<? extends byte[]> event = queue.remove(1000);

        if (event == ref) {
            System.out.println("REFERENCE_ENQUEUED");
        } else {
            System.out.println("NO_EVENT_WITHIN_TIMEOUT");
        }

        System.out.println("cleared=" + (ref.get() == null));
    }
}
~~~

Run:

~~~bash
javac --release 17 WeakQueueObservationDemo.java
java WeakQueueObservationDemo
~~~

Depending on the GC, there are at least two valid branching outcomes:

- **`REFERENCE_ENQUEUED`** if the GC detects and enqueues the reference within the wait interval.
- **`NO_EVENT_WITHIN_TIMEOUT`** if the queue does not yet have the reference after the requested time.

The `cleared=` line is also a point-in-time observation: the referent may have been cleared even if not yet enqueued; some collectors may not have processed the ref yet, so it cannot be asserted that it is `true` every time.

**`queue.remove(1000)` sets the program's wait time, not a GC deadline.** `System.gc()` does not change this either; the JVM may ignore explicit GC requests due to flags or policy.

### Why create the payload in a separate method?

After the `create` method returns, there is no local variable in `main` directly holding the `byte[]` payload. The caller only holds `WeakReference`, making it easy to observe GC processing. However, the program still has no right to demand that the collector run immediately, and runtime reachability optimizations must be understood according to GC semantics rather than the lexical scope of Java variables.

## 7. Exact Timing: cleared, enqueued, dequeued, and reclaimed

A useful **mental** ordering:

~~~text
t0: object and reference are created
t1: the last strong reachability path may be lost
t2: GC detects the appropriate reachability state
t3: GC clears the reference
t4: GC enqueues the reference (if registered with a queue)
t5: application dequeues and processes

There is no mandatory millisecond SLA t1 -> t2 -> t4 -> t5.
Some events may happen at the same time or not occur
within the observed lifetime of the process.
~~~

In particular:

- **`get() == null` does not mean `isEnqueued() == true`**; not yet enqueued, already dequeued, or manual clear can all create a difference.
- **`poll() == null` does not prove the object is still alive**; it only says no entry can currently be retrieved from the queue.
- **`remove(timeout)` returning a reference does not assert that the object has been deallocated immediately**; reference processing is not a receipt for reclaimed RAM bytes.
- **SoftReference** has additional GC discretion before clearing, based on memory demand.
- **PhantomReference** notifies when the appropriate phantom reachability condition is met; `get()` is always null and native resource cleanup must be performed by code with proper ownership.
- **Manual `enqueue()`** breaks the assumption “events only come from GC”; you need to separate event sources if the system allows manual enqueueing.

Do not build business logic requiring strict-deadline SLAs, transactions, locking, or mandatory resource closure solely on a GC/reference queue event.

## 8. Batched `poll()` or Blocking Worker?

### Opportunistic poll

When the cache is accessed, pending stale references can be cleaned up:

~~~java
Reference<?> ref;
while ((ref = queue.poll()) != null) {
    // Use ref metadata to remove the entry from the cache.
}
~~~

This is an **illustrative snippet**; the `queue` variable needs to be defined according to the actual cache data. This approach does not create a separate thread; it is suitable for some caches with low polling cost. However, if the application never calls the cache again, opportunistic cleanup may not take place.

### Blocking worker with timeout

~~~java
while (!Thread.currentThread().isInterrupted()) {
    try {
        Reference<?> ref = queue.remove(500);
        if (ref != null) {
            // Process the dequeued reference; idempotent cleanup.
        }
    } catch (InterruptedException stop) {
        Thread.currentThread().interrupt();
        break;
    }
}
~~~

This is also an **illustrative snippet**, not a standalone program. `remove(500)` helps the worker periodically check the stop state. With `remove()` without a timeout, shutdown must have a clear interrupt mechanism.

Principles:

- The consumer should not continuously busy-spin `while (queue.poll() == null) {}`, because it wastes CPU.
- Do not create a non-daemon worker that lives forever and prevents the JVM from exiting.
- When a processing exception occurs, do not let one event kill the entire worker; log/maintain state according to policy.
- If multiple consumers read from the queue, only one consumer dequeues a given reference; a thread-safe registry structure is needed.
- After dequeuing, the application usually **removes the registration/reference object from the registry** to avoid leaking metadata.

## 9. Use an ID Instead of Trying to Retrieve a Cleared Referent

When a `WeakReference` is cleared by GC, `weak.get()` typically returns null; you cannot expect to call `referent.close()` on an object that can no longer be retrieved. To know which cache entry needs cleaning, store the ID on the **reference object**.

An illustrative helper:

~~~java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

final class TrackedWeakRef<T> extends WeakReference<T> {
    final long id;

    TrackedWeakRef(T value, ReferenceQueue<? super T> queue, long id) {
        super(value, queue);
        this.id = id;
    }
}
~~~

This class **has no main**; it only demonstrates how to store an ID independently of the referent.

A cache/registry can strongly store `TrackedWeakRef`, store `id -> value/metadata` separately, and when dequeuing receives `TrackedWeakRef`, read `id` to remove the entry. If `value/metadata` accidentally holds the key strongly, the key may never become weakly reachable; this needs specific examination.

**Anti-example:**

~~~java
final class BadTrackedRef<T> extends WeakReference<T> {
    final T original; // strong, keeps the referent reachable!

    BadTrackedRef(T value, ReferenceQueue<? super T> q) {
        super(value, q);
        original = value;
    }
}
~~~

Although it extends `WeakReference`, the `original` field defeats the purpose of tracking the object by weak reference if the `BadTrackedRef` instance is still retained.

For `WeakHashMap`, remember that the key is weak, but the value may hold the key via another strong path. Do not treat `WeakHashMap` as a guarantee that “every entry disappears immediately when external code stops using the key”.

## 10. Why Is PhantomReference Often Used for Cleanup?

`PhantomReference<T>` is designed to notify when the referent has become eligible for phantom reachability; the application cannot use `phantom.get()` to retrieve the original object.

~~~text
Resource wrapper ───── owns ─────> Native handle H
       |
       +── PhantomReference<Resource>
                  |
                  +── Independent metadata: H, ID, cleanup state
                          |
                  GC enqueues ref when appropriate
                          |
                  Consumer reads metadata
                          |
                  Release H if not yet closed
~~~

To make this design safe:

1. Cleanup metadata **does not hold a strong reference to Resource**; if it does, Resource will not become eligible for GC.
2. `H` must remain valid until the consumer cleans it up.
3. Cleanup must be **idempotent**, even if the application has already called explicit `close()`.
4. Native callbacks/async operations must finish before freeing, otherwise use-after-free occurs.
5. The reference object must be kept reachable until the event is received or the registration ends.
6. A queue event is not a guarantee that OS memory has been returned before the cleanup action runs.

In many situations, using `java.lang.ref.Cleaner` is easier than managing `PhantomReference`+queue manually; however, **there is no automatic cleanup deadline**.

## 11. Cleaner Compared to `close()` and `try-with-resources`

`Cleaner` (Java 9+) manages registrations and cleaning actions based on an appropriate reference mechanism. This is an option supporting **fallback cleanup**, not a replacement for **explicit resource ownership**.

Complete Java 17 example **`CleanerOwnershipDemo.java`**:

~~~java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CleanerOwnershipDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class CleanupState implements Runnable {
        private final AtomicBoolean closed = new AtomicBoolean();

        @Override
        public void run() {
            if (closed.compareAndSet(false, true)) {
                System.out.println("CLEANUP");
            }
        }
    }

    private static final class Resource implements AutoCloseable {
        private final Cleaner.Cleanable cleanable;

        Resource() {
            // Action does not capture Resource/this.
            cleanable = CLEANER.register(this, new CleanupState());
        }

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        try (Resource r = new Resource()) {
            System.out.println("IN_USE");
        }
        System.out.println("DONE");
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 CleanerOwnershipDemo.java
java CleanerOwnershipDemo
~~~

**Fixed stdout because `try-with-resources` proactively calls `close()`:**

~~~text
IN_USE
CLEANUP
DONE
~~~

If you omit `close`, you **are not promised** that `CLEANUP` will appear before the process exits; the collector and cleaner may not have run yet. `CleanupState` in the example is a separate `Runnable` **that does not hold the referent**; writing `CLEANER.register(this, () -> this.close())` can keep `this` alive itself, making the cleaner logic meaningless.

For important resources such as connections, sockets, files, and native buffers with a clear owner, close them immediately when done. `Cleaner` can serve as a fallback in case the programmer forgets to close, but it does not provide a safety guarantee against all double-free/concurrency bugs.

## 12. `Reference.reachabilityFence` and the Native Lifetime Window

The JIT compiler may see that an object is no longer used in subsequent Java expressions and allow the object to stop being strongly reachable **earlier than the end of the lexical scope**. In JNI/native-resource code, this can be dangerous when native work is still using a handle managed by the wrapper.

`Reference.reachabilityFence(obj)` (Java 9+) helps ensure `obj` remains strongly reachable up to the call site:

~~~java
static void useNative(NativeResource resource) {
    try {
        resource.invokeNative();
    } finally {
        java.lang.ref.Reference.reachabilityFence(resource);
    }
}
~~~

This is **not a standalone program** because `NativeResource` is a descriptive type needed in a real application. The fence only speaks to the **lifetime/reachability** of the Java object up to the specified point. It:

- Is not a command to invoke GC.
- Does not enqueue a ReferenceQueue.
- Does not allocate/free new memory.
- Does not replace synchronized/atomic to protect native data across threads.
- Does not allow using a native pointer after the owner has explicitly closed/freed it.

When reading `WeakReference.get()`, save the result **once** into a strong local before using it:

~~~java
Object snapshot = weak.get();
if (snapshot != null) {
    System.out.println(snapshot.toString());
}
~~~

This is an **illustrative snippet**, requiring the `weak` variable to be defined in scope. Do not check `if (weak.get() != null)` and then call `weak.get().method()` a second time assuming the two results will always be the same: GC may clear the reference between the two reads.

## 13. Common Mistakes and Consequences

1. **“The queue contains dead original objects.”** No, it contains **Reference objects**.
2. **“Creating a Reference with a queue puts an event in the queue immediately.”** False, registration does not enqueue.
3. **“`ref.clear()` automatically enqueues.”** False.
4. **“`ref.enqueue()` proves GC has run.”** False: it could be a manual enqueue.
5. **“`weak.get() == null` means GC has enqueued it.”** False, clearing and enqueueing are different.
6. **“`queue.poll() == null` means the referent is still alive.”** False, it only means no entry is currently available.
7. **“`PhantomReference.get() == null` means the object has been GC'd.”** False: it always returns null.
8. **“`queue.remove(0)` does not wait.”** False, this is an indefinite wait.
9. **“`System.gc()` forces an event within 1 second.”** False, there is no deadline.
10. **“A queue event confirms native memory has been freed.”** False, cleanup requires a separate step.
11. **“ReferenceQueue keeps all registrations alive.”** False, a registry is needed to hold reference objects.
12. **“A WeakReference subclass with an `original` field is harmless.”** False, the strong field prevents GC of the referent.
13. **“Cleaner has the same SLA as `close()`.”** False, timing depends on GC.
14. **“`isEnqueued()` is a good cleanup mechanism.”** False, deprecated because it is racy.
15. **“It is fine if a `WeakHashMap` value holds the key.”** False, a strong back-reference can keep the key alive.
16. **“The queue-processing thread can ignore interrupts.”** False, a shutdown protocol is needed.
17. **“A soft reference is definitely cleared as soon as strong refs are dropped.”** False, GC has the right to keep it depending on memory demand.
18. **“GC notification is sufficient for releasing locks/committing transactions.”** False, critical resources need an explicit lifecycle.

## 14. Checklist for Safe ReferenceQueue Implementation

- Choose the right **Reference type** (soft/weak/phantom) for the application semantics.
- Create the reference with an **appropriate queue**, without assuming the queue automatically manages a registration list.
- Hold the **Reference object** strongly in a registry; strictly avoid storing the referent in cleanup metadata if you want the referent to be eligible.
- On an event, use only an independent ID/handle to remove entries or clean up; do not try to retrieve a cleared referent.
- Implement the consumer using `poll()` on cache activity or `remove(timeout)` in a worker with shutdown/interruption.
- Handle races between explicit `close()` and GC events, ensuring cleanup is idempotent.
- Remove the registration from the registry once the event has been processed so metadata is not retained indefinitely.
- Do not use `System.gc()` or `isEnqueued()` as a clock or correctness protocol.
- For native resources, require explicit ownership, try-with-resources, and checks for use-after-free/double-free.
- When observability is needed, measure GC logs, reference queue backlog, number of held registrations, and cleanup frequency; do not just count objects that lost strong refs.
- Test the **manual enqueue** branch with deterministic stdout; tests for the **GC** branch must tolerate timeouts/non-determinism.
- Verify the JDK version: the APIs in the examples compile with `--release 17`.

## 15. Self-Check Questions

1. What does `ReferenceQueue.poll()` return? **A Reference object or null**, not the original object.
2. Does `ref.clear()` immediately make `queue.poll()` non-null? **No**.
3. Can `Reference.enqueue()` be called directly by Java code? **Yes**.
4. Does `weak.get() == null` prove the reference has been dequeued? **No**.
5. How do `remove(0)` and `poll()` differ? **`remove(0)` waits indefinitely, `poll` does not wait**.
6. Why must the `WeakReference` itself be kept in a registry? **So reference notification/metadata is not lost when the reference object becomes unreachable**.
7. Why must the registry not hold `T original` of the referent? **Because it creates a strong path preventing weak reachability**.
8. Does `PhantomReference.get()` return the object before it is GC'd? **No, always null**.
9. Does GC guarantee enqueueing within 500 ms after an object becomes unreachable? **No**.
10. Does an enqueue event mean native `free` has completed? **No**.
11. Why is idempotent cleanup needed? **Because there can be both explicit close and notification cleanup**.
12. Is `Cleaner` guaranteed to run on normal JVM exit in all circumstances? **There is no guaranteed deadline**.
13. Until what point does `Reference.reachabilityFence(x)` keep `x`? **Up to the fence call site**.
14. Can a `WeakHashMap` have an entry retained because the value points back to the key? **Yes**.
15. How does `SoftReference` differ from `WeakReference`? **GC may keep a soft referent longer according to memory-demand policy**.
16. If a socket needs to be released before an HTTP request returns a result, use a queue or explicit close? **Explicit close/try-with-resources**.
17. If GC clears a reference and the application polls immediately with no event yet, does that violate the API? **No**, enqueueing may happen later.
18. If a wrapper class has been detected by GC, can that object be retrieved from a `PhantomReference` to call `close`? **No**.

## 16. Recommended Java SE 17 Documentation

- `java.lang.ref` — reachability levels, notification, queue registration: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html
- `ReferenceQueue` — `poll`, `remove`, `remove(long)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html
- `Reference` — `get`, `clear`, `enqueue`, `refersTo`, `reachabilityFence`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html
- `WeakReference`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- `SoftReference`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/SoftReference.html
- `PhantomReference`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html
- `Cleaner`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html
- `WeakHashMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html

**Technical conclusion:** `ReferenceQueue` is a channel that **receives enqueued Reference objects**. Clearly separate **loss of strong reachability → GC detection → clear reference → enqueue → application dequeue**, remember that the milestones **have no deadline**, and an event may come from **manual enqueue** rather than GC. For a correct system, retain the reference object/appropriate metadata without strongly holding the referent, and use the queue for **stale-entry cleanup and supplementary notification**; resources that must be released on time must have **explicit close and clear ownership**.
