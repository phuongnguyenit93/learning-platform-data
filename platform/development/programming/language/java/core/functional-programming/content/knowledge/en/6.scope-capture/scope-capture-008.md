# Risks of Capturing Large Objects or Mutable State in Java

When writing lambdas, method references, or callbacks in Java, **captured variables** can extend the lifetime of an object, or cause multiple pieces of code to observe and modify the same state. Two issues often confused with each other are **retaining references for too long causing memory pressure** and **sharing mutable state causing wrong results or concurrency bugs**.

This lesson focuses on those risks, how to recognize them through Java 17+ examples, and how to design safe closures in streams, listeners, asynchronous tasks, and function-accepting APIs.

## 1. What Does Java Actually Capture?

A lambda can use a local variable from the enclosing scope if that variable is `final` or **effectively final** (assigned only once). This constraint applies to **the local variable/reference**, not forcing the object the variable points to to be immutable.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

class CaptureBasics {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");

        Supplier<Integer> count = () -> names.size();
        names.add("Bình"); // Allowed: modifies the object's contents.
        System.out.println(count.get()); // 2
    }
}
~~~

Run with `javac CaptureBasics.java` and `java CaptureBasics`. Output:

~~~text
2
~~~

In this example, the local reference `names` is not reassigned, so it is valid for the lambda, yet the list still changes. If you try to write `names = new ArrayList<>();` after creating the lambda, the code does not compile because `names` is no longer effectively final.

Three kinds of data should be distinguished when capturing:

- **Local primitive**: the lambda uses the variable's value at closure creation time; there is no mutable object behind that primitive value.
- **Local reference**: the lambda holds the reference value to the same object; operations on that object can still occur when the lambda runs.
- **Object field / `this`**: a lambda or instance-bound method reference can retain the receiver instance, and thereby retain large fields inside that instance.

How the JVM represents a lambda is an implementation detail; when designing, rely on **object reachability and reference lifetimes**, not on the assumption that every lambda always creates a new class or a new allocation.

## 2. Risk of Retaining Large Objects in Memory

An object can be reclaimed by the garbage collector when it is no longer reachable from GC roots, according to JVM semantics and optimizations. If a callback is still held by a long-lived location, objects the callback needs for execution can also remain reachable. For example:

~~~text
GC root
  → singleton / event bus / executor / cache
  → callback (lambda or method reference)
  → captured object
  → byte[], lists, caches, object graphs...
~~~

This is **retention**: not necessarily an allocation error, but memory continues to be held longer than business needs. A small-sized callback can retain an entire large object graph. If the registering party does not remove the callback when its lifecycle ends, retention can become a memory leak.

Common scenarios:

- A lambda stored in a `static` collection, cache, singleton, or configuration variable that lives for the entire application.
- An event listener, subscription, or callback registered without being unregistered.
- Delayed tasks in a queue or `ScheduledExecutorService` holding payloads while waiting; recurring tasks can be retained for a very long time.
- A callback using `this`, `this::handle`, or reading an instance field, unintentionally pulling along the entire instance and the data it references.
- A closure returned from a method holding a temporary helper object, even after the method has finished.
- Off-heap memory or resources like files/sockets have their own lifecycles: a callback holding a wrapper can delay release, yet **GC does not replace calling `close()` on resources**.

### Example 1: Holding an entire large array when only one value is needed

Create the file `LargeCaptureDemo.java`:

~~~java
public class LargeCaptureDemo {
    static Runnable captureLargeArray() {
        byte[] payload = new byte[8 * 1024 * 1024];
        payload[0] = 7;
        return () -> System.out.println("value=" + payload[0]);
    }

    static Runnable captureOnlyNeededValue() {
        byte[] payload = new byte[8 * 1024 * 1024];
        payload[0] = 7;
        int firstByte = payload[0];
        return () -> System.out.println("value=" + firstByte);
    }

    public static void main(String[] args) {
        Runnable keepsArray = captureLargeArray();
        Runnable keepsValue = captureOnlyNeededValue();
        keepsArray.run();
        keepsValue.run();
    }
}
~~~

~~~bash
javac LargeCaptureDemo.java
java LargeCaptureDemo
~~~

Output:

~~~text
value=7
value=7
~~~

Both callbacks have the same observable behavior, but their capture requirements differ. `keepsArray` needs to access `payload[0]` at execution time, so it can retain a reference to the ~8 MiB array; `keepsValue` only needs `int firstByte` and does not need to retain the original array. The example **illustrates reference relationships**, not measuring or guaranteeing a specific GC timing: the JIT may optimize differently, and a variable going out of scope does not mean memory is immediately reclaimed.

**Principle:** compute or extract small, independent values before creating the callback, and capture only those values. If the full data is needed, keep the callback's lifetime short, provide a cancellation mechanism, and consider passing data at invocation time instead of storing it upfront in the closure.

## 3. `final` Does Not Make Object State Immutable

The second risk does not require a lot of memory. A lambda holds a reference to a `List`, `Map`, domain object, or an `AtomicInteger`; the data can change between when the lambda is created and when the lambda runs.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class MutableCaptureDemo {
    static Supplier<String> liveView(List<String> values) {
        return () -> String.join(", ", values);
    }

    static Supplier<String> snapshotView(List<String> values) {
        List<String> snapshot = List.copyOf(values);
        return () -> String.join(", ", snapshot);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Bình"));
        Supplier<String> live = liveView(names);
        Supplier<String> frozen = snapshotView(names);

        names.add("Chi");
        System.out.println("live=" + live.get());
        System.out.println("snapshot=" + frozen.get());
    }
}
~~~

~~~bash
javac MutableCaptureDemo.java
java MutableCaptureDemo
~~~

Deterministic output (operations run sequentially on one thread):

~~~text
live=An, Bình, Chi
snapshot=An, Bình
~~~

`liveView` intentionally observes the **current state**; `snapshotView` intentionally keeps a **snapshot at creation time**. Both are valid when matching business requirements. Mistakes happen when expecting a snapshot while holding a reference to a mutable object.

Notes:

- `List.copyOf(values)` gives a list that cannot be modified via the list API and is independent of adding/removing elements in the source list. This copy is **shallow**: if elements are mutable objects, data inside those elements can still change.
- `Collections.unmodifiableList(values)` only creates a **view that forbids modification through the view**; if the source `values` changes, the view still reflects those changes. It is not an independent snapshot.
- `final List<Order> orders` does not make `Order` or the elements inside immutable.
- `AtomicInteger` helps perform certain atomic updates, but it is itself mutable state; it does not make an entire business operation atomic.

If a truly stable snapshot is needed, use immutable DTOs/records, copy the needed fields (including nested mutable components), or build an explicit immutable value representation.

## 4. Shared Mutable State and Concurrency Bugs

When callbacks run on different threads, data mutation can lead to two categories of bugs:

1. **Race condition / lost update:** two tasks concurrently read, compute, and write a variable; one update overwrites another.
2. **Visibility / ordering:** without an appropriate happens-before relationship, one thread has no guarantee of observing another thread's updates at the expected time.

~~~java
// Illustrative ERROR snippet; not a standalone Java program.
int[] total = {0};
Runnable unsafe = () -> total[0]++; // Read then write: not atomic.
// Running unsafe concurrently on multiple threads can lose increments.
~~~

The `total` array is validly captured by the lambda because the reference is not reassigned; this **does not make `total[0]++` safe**. Even a `volatile int` does not make `x++` atomic, because it is a read–compute–write sequence.

Correct example for an independent counting need, using `AtomicInteger` and waiting for tasks to complete. Create the file `ConcurrentCounterDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentCounterDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger counter = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            Future<?>[] tasks = new Future<?>[1_000];
            for (int i = 0; i < tasks.length; i++) {
                tasks[i] = pool.submit(() -> {
                    counter.incrementAndGet();
                });
            }
            for (Future<?> task : tasks) {
                task.get();
            }
            System.out.println("count=" + counter.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac ConcurrentCounterDemo.java
java ConcurrentCounterDemo
~~~

Output:

~~~text
count=1000
~~~

`incrementAndGet()` performs an atomic update; `Future.get()` waits for the corresponding task to finish and establishes the necessary happens-before relationship for actions inside the task. `shutdown()` stops accepting new tasks; the example waits for all `Future`s before printing the result.

Choose a solution according to the goal:

| Need | Approach |
| --- | --- |
| Each task only needs a value at submission time | Create a separate snapshot local variable for each submission. |
| Tasks only need to read unchanging data | Share immutable values/DTOs or independent snapshots. |
| Counting/incrementing a shared variable | `AtomicInteger`, `AtomicLong`, or `LongAdder` as needed. |
| Multiple fields must change consistently | Locks (`synchronized`/`Lock`) or isolate state in a single owner/thread. |
| Collecting results from a parallel stream | Prefer `collect`/reduction instead of side effects on a shared `ArrayList`. |
| Transferring state between threads | Use appropriate synchronization tools such as `Future`, thread-safe queues, locks, or `volatile` when only visibility is needed. |

Avoid assuming a closure will run immediately, run exactly once, or always run on the calling thread. The API accepting the callback defines the execution schedule, synchronization guarantees, and cancellation policy.

## 5. Why Do Long-Lived Listeners and Callbacks Easily Cause Retention?

Consider a UI component, service, event handler, or a simulated `EventBus` object:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerLifecycleDemo {
    static final class EventBus {
        private final List<Runnable> listeners = new ArrayList<>();

        AutoCloseable register(Runnable listener) {
            listeners.add(listener);
            return () -> {
                listeners.remove(listener);
            };
        }

        void fire() {
            for (Runnable listener : List.copyOf(listeners)) {
                listener.run();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        EventBus bus = new EventBus();
        byte[] large = new byte[4 * 1024 * 1024];
        large[0] = 9;

        try (AutoCloseable registration =
                 bus.register(() -> System.out.println("event=" + large[0]))) {
            bus.fire();
        } // close() unregisters the listener from the bus.
    }
}
~~~

~~~bash
javac ListenerLifecycleDemo.java
java ListenerLifecycleDemo
~~~

Output:

~~~text
event=9
~~~

While the listener remains in `bus.listeners`, the callback needs access to `large` and can therefore keep the large array reachable. The `try` block creates an explicit end point for the registration, helping avoid retaining the listener indefinitely. In real frameworks, the corresponding mechanism might be `removeListener`, `dispose`, `unsubscribe`, `cancel`, or `close`.

You should not infer that **canceling a task** always means immediately removing every reference: a future, queue, timer, or currently running callback can still retain objects until the actual lifecycle ends. Check the API documentation and state after cancellation.

Pay special attention to method references like `component::refresh`: if the method reference is bound to an instance, it retains the `component` receiver in order to invoke the method; from that receiver, many other data fields may be reachable. When only a single value is needed, pass that small piece of data instead of retaining the entire receiver.

## 6. Incorrect Capture Cases in Loops

A local variable used by a lambda must be effectively final. Therefore, the following code **does not compile**:

~~~java
// Intentionally invalid code snippet, only to explain the compile error.
for (int i = 0; i < 3; i++) {
    // Runnable task = () -> System.out.println(i);
    // 'i' changes via i++ so it is not effectively final.
}
~~~

The right approach is to create a copy for each iteration:

~~~java
public class LoopCaptureDemo {
    public static void main(String[] args) {
        java.util.List<Runnable> tasks = new java.util.ArrayList<>();
        for (int i = 0; i < 3; i++) {
            int index = i;
            tasks.add(() -> System.out.println(index));
        }
        tasks.forEach(Runnable::run);
    }
}
~~~

~~~bash
javac LoopCaptureDemo.java
java LoopCaptureDemo
~~~

Output:

~~~text
0
1
2
~~~

The `index` copy also expresses the meaning "the value at task creation time." Conversely, if each callback holds a shared object whose state can change, the callbacks can still see different values when they run.

## 7. API Design to Reduce Risk

Two contract styles should be distinguished at design time:

- **Snapshot callback:** needs data at registration/submission time. Capture values, minimize data size, and prefer immutable types. For example, a `long orderId` or a DTO containing a few needed fields instead of an entire entity graph.
- **Live callback:** intentionally reads the latest state. Ensure thread-safe access or define an owner thread; clearly document who updates it, when the callback is called, and when it must be unregistered.

For very large data or lifecycle-managed resources, consider a method that accepts parameters at execution time:

~~~java
// API sketch: the callback receives data at execution time,
// rather than storing a large array in the closure beforehand.
java.util.function.Consumer<byte[]> processor = bytes -> {
    System.out.println("received=" + bytes.length);
};
~~~

This only shifts reference-holding responsibility to the caller; queues and data lifetimes must still be bounded. If using a message queue or an executor with a backlog, the amount of waiting payload can still be very large.

Do not treat `WeakReference` as a default fix. A weak reference can lose the object as soon as no strong reference remains, leaving the callback without data to run; it does not guarantee listener cleanup, does not solve race conditions, and does not replace lifecycle management.

## 8. Diagnostic Signs and How to Check

**When suspecting retention:** observe heap usage after load cycles, the number of pending listeners/subscriptions/tasks, and the number of live objects; compare heap dumps across stages. In a heap analyzer, look at **GC roots**, **retaining paths**, **dominator trees**, and **retained size**. For example, a lambda held by a singleton pointing to a large `byte[]` is a reference path worth investigating. A small `shallow size` of the lambda does not reflect all the data it retains.

**When suspecting mutable/concurrency bugs:** write repeatable tests or stress tests with clear synchronization points; identify which threads read/write, when registration/execution happen, and which synchronization primitives establish happens-before. Do not treat "ran 100 times without error" as proof of thread-safety.

**When needing to reproduce:** create a small runnable case in Java 17+, separating callback creation time, state mutation time, execution time, and unregistration time. For real memory incidents, verify with profiling/heap dumps; do not claim a leak based solely on a single RAM usage snapshot or a call to `System.gc()`.

## 9. Common Misconceptions

1. **"The local variable is final so the object is immutable too."** False: final/effectively final prevents reassigning the reference variable, not mutating the object's contents.
2. **"Once the lambda leaves the creating method, the object will be GC'd."** False: a returned or registered callback can keep the object alive after the method finishes.
3. **"A small lambda doesn't use much memory."** Incomplete: the retaining path can indirectly hold MiB or GiB.
4. **"Using `volatile` is enough for `count++`."** False: visibility does not turn a compound update into an atomic operation.
5. **"`Collections.unmodifiableList` creates a snapshot."** False: it is a read-only view of the source list; if the source changes, the view sees the change.
6. **"Using a parallel stream protects all side effects."** False: lambdas with side effects on shared structures still need synchronization; prefer reductions and proper collectors.
7. **"GC will automatically close files/sockets when the callback is no longer used."** False: manage resources with `try-with-resources` or an explicit close contract.
8. **"Calling cancel eliminates all retention."** Not guaranteed: it depends on queues, running tasks, futures, listeners, and each API's cleanup mechanism.

## 10. Checklist Before Putting Lambdas/Callbacks into Production

- **Who holds** this callback, how long does it live, on which threads can it be called, and how many times?
- Has the lambda captured `this`, a container, request, buffer, collection, entity graph, or large resource?
- Does the callback need a **fixed value** or the **latest state**? If fixed, has a snapshot of the right depth been created?
- If concurrently reading/writing mutable state, is there a clear strategy for ownership, atomicity, visibility, and synchronization?
- Does the API have an appropriate `close/remove/unsubscribe/cancel` operation? Who is responsible for calling it at lifecycle end?
- If the queue/tasks are slow, is the number of queued callbacks/payloads bounded?
- Can needed parameters be passed at call time or can captured data be reduced to an immutable ID/value/DTO?

**Key Takeaway:** lambdas do not inherently cause memory leaks and capturing a mutable object is not automatically a bug. Risks arise when **the callback's lifetime exceeds the expected lifetime of the data**, or when **multiple places use mutable state without a consistent synchronization contract**. Designing clear lifecycles, data scopes, and synchronization mechanisms is the primary prevention measure.