# Documenting a Thread-Safety Contract for a Public API in Java

A public API can return the right value when called sequentially yet still cause race conditions, deadlocks, or unpredictable results when multiple threads call it concurrently. Library users **cannot infer thread safety solely from a class name, from `synchronized` appearing on a few methods, or from code passing single-threaded tests**. Therefore, a public API needs a **thread-safety contract**: a verifiable commitment regarding which concurrent access patterns are supported, what outcomes are observable, what the caller's obligations are, and what the implementation's own limitations are.

A good contract clearly answers:

- **Who may call concurrently?** Can multiple threads call the same instance, the same method, or only certain methods?
- **What is guaranteed?** Which atomicity, visibility, ordering, snapshot consistency guarantees, and invariants hold?
- **What is not guaranteed?** Ordering across concurrent calls, atomicity of multi-call sequences, fairness, or response time?
- **What are the caller's responsibilities?** External locking, not mutating inputs while the API processes them, not sharing returned mutable objects, not re-entering callbacks?
- **Does the API wait, invoke callbacks, or manage resources or a lifecycle?** How can it block, be interrupted, close, cancel, or handle calls after closing?

This lesson applies to **Java concurrency in general** (the Java Memory Model, `java.lang`, `java.util.concurrent`, and Javadoc). It does not cover concurrency mechanisms specific to the Spring Framework.

## 1. A Thread-Safety Contract Is Part of the API Contract

A public API typically already describes parameters, return types, exceptions, and pre/postconditions. In a multithreaded program, however, that is not enough.

For example:

```java
public interface Counter {
    long get();
    long incrementAndGet();
}
```

This is only an illustrative interface, not a complete program with `main`. Users need to know:

1. Can `incrementAndGet()` be called concurrently from two threads?
2. If two calls start when the counter is 5, are they guaranteed to return two distinct values (`6` and `7`), or could both return `6`?
3. What values is a `get()` running concurrently with an increment allowed to observe?
4. Is the two-step sequence `get(); incrementAndGet();` treated as a single transaction?
5. Can a `Counter` be used from another thread after construction without an additional publication step?

Documentation that merely says "Thread-safe" cannot answer all of these questions. The contract should state **the observable linearization points**, the limits of each method, and what is not guaranteed.

**Thread safety is a property of a specific usage pattern.** A class may be thread-safe for individual reads and writes without guaranteeing transactions spanning multiple calls. Another class may require callers to perform all operations under a single lock. You cannot apply a single blanket label to every interaction without specifying the scope of the commitment.

## 2. Classify the Safety Level Before Writing the Contract

A practical vocabulary helps keep documentation consistent:

| Level | Meaning for the caller | Example phrasing |
| --- | --- | --- |
| **Immutable** | After construction, observable state cannot change; internal components must also be handled properly | "Instances are immutable and safe to share after construction." |
| **Thread-safe** | Specified operations can be called concurrently according to the stated guarantees | "All public methods support concurrent calls on the same instance." |
| **Conditionally thread-safe** | Safe only if the caller satisfies conditions on locking, ordering, callbacks, or scope | "Iteration requires the caller to hold the documented lock." |
| **Thread-compatible** | Multiple threads can use an instance if the caller synchronizes conflicting accesses externally | "Concurrent access requires external synchronization." |
| **Not thread-safe** | No concurrent access guarantees; typically restricted to a single owner | "Do not access an instance concurrently from multiple threads." |
| **Thread-confined** | The instance or mutable state belongs to only one thread during an ownership phase | "Each instance must be accessed only from its creating thread." |

These are **design-description terms**; Java SE does not have a single mandatory standard annotation such as `@ThreadSafe` for every public API. Some libraries define their own annotations, but annotations are only useful when accompanied by clear definitions and documentation. In Javadoc, state the commitment clearly in plain prose, even if the project uses annotations.

Also distinguish the following:

- **Unmodifiable** does not mean **deeply immutable**. `Collections.unmodifiableList(list)` can reflect modifications made to the underlying list; a record containing an `ArrayList` can still have mutable state.
- **Stateless** does not by itself prove the entire object graph is safe. A method with no instance fields of its own might still write to a `static Map` or use a non-thread-safe collaborator.
- **Synchronized per method** does not prove that a sequence of multiple methods is atomic.
- **Having internal locks** does not guarantee the absence of deadlocks, harmful reentrancy, or starvation.

## 3. Specify the Protected Target and Scope

The contract must specify whether it refers to **a single instance**, **multiple instances sharing a resource**, or **process-wide state**.

For example, if two `Counter` instances each hold their own `AtomicLong`, each instance can be independently thread-safe. However, if both instances share a mutable static cache, locking on `this` in each instance cannot protect the shared cache.

A class-level Javadoc block can be written as:

```java
/**
 * A thread-safe counter.
 *
 * <p>All public methods may be called concurrently on the same instance.
 * Each increment is atomic, and get() observes a value from one atomic read.
 * Separate Counter instances have independent state.
 *
 * <p>A sequence such as get() followed by incrementAndGet()
 * is not an atomic transaction.
 */
public final class Counter {
    // Implementation goes here.
}
```

This is an **illustrative Javadoc template**, not a standalone runnable class. The class description gives readers a common baseline; individual methods still need to state narrower guarantees or exceptions.

If the API uses a shared global resource, state it explicitly. For example: "All instances share one cache; changes from one instance may be visible through another." That is far more informative than merely writing "instances are thread-safe."

## 4. Properties to Express Explicitly

### Atomicity: Can logical operations interleave?

If `incrementAndGet()` is atomic, two threads incrementing a counter initially at 5 will produce outcomes corresponding to two distinct increment steps, even though which caller receives which result depends on scheduling. However, the sequence:

```java
if (counter.get() < limit) {
    counter.incrementAndGet();
}
```

is **not automatically atomic**. Another thread can modify the counter between `get()` and `incrementAndGet()`. If there is an invariant "never exceed the limit," the API should provide a method such as `tryIncrementWithinLimit(limit)` with an atomic guarantee covering both the check and the update.

A thread-safe class must distinguish **method atomicity** from **operation composition**.

### Visibility: Will other calls see updates?

A contract can guarantee that the effects of a completed operation will be observed by subsequent synchronized operations according to its semantics. Merely writing "synchronized" without explaining what is protected can still leave callers unsure about cross-thread visibility.

The Java Memory Model defines **happens-before** relationships. For example, `synchronized` on the same monitor or `AtomicLong` operations with corresponding semantics ensure visibility and ordering. However, the contract should be phrased in terms of the API behavior the caller needs, rather than forcing the caller to know which lock type the implementation uses.

### Ordering: How are concurrent results ordered?

A `ConcurrentHashMap` allows concurrent updates from multiple threads, but it does not promise that its iterator is a frozen snapshot or traverses keys in insertion order. For a FIFO queue, describe FIFO as applying to **enqueues with a well-defined order**, rather than promising wall-clock ordering between two concurrently running producers.

### Snapshot consistency

`snapshot()` can mean several different things:

- A **point-in-time consistent snapshot** of the collection taken under the same lock.
- An **unmodifiable** view of data that is still changing.
- A **weakly consistent** iterator that may reflect some concurrent updates as documented.
- A capture of only certain fields, while other fields may change independently.

The name `snapshot` does not substitute for stating the point in time, contents, and immutability of the result.

### Liveness and blocking

An API with properly protected data can still block indefinitely while waiting for a resource. For a public API, state under what conditions a method can block, whether timeouts exist, whether interruption/cancellation is supported, whether locks are held during callbacks, and whether state can change when exiting via an exception.

**Do not claim lock-free or wait-free** merely because `AtomicInteger` or a concurrent collection is used in part of the code: progress guarantees must consider the **entire operation**, retry loops, and dependent calls.

## 5. Linearizability: Precise Language for Many Concurrent APIs

An operation is **linearizable** if each invocation can be viewed as taking effect at a single point in time between **its start** and **its completion**, and this order respects the real-time order of non-overlapping operations. This is a strong and very useful property for counters, map operations, atomic registers, and queues.

For example, two `incrementAndGet()` calls on the same `AtomicLong` are atomic operations; if they return `6` and `7`, that can be explained by a valid sequential order without specifying which thread goes first. If one call finishes completely before the next call starts, the linearization order must respect that ordering.

Write the contract at the right level:

- "Each `incrementAndGet()` is atomic" is a per-operation guarantee.
- "A call to `get()` returns the value from one atomic read" does not mean two consecutive `get` calls form a snapshot across both reads.
- "Concurrent calls may complete in either order" explains the lack of an ordering guarantee.
- "The final count equals the number of completed successful increments" must be understood as holding when **no concurrent increments or other updates remain** and all related tasks have finished.

Not every concurrent API guarantees linearizability for every method. An aggregate report across multiple independent counters may only be **eventually consistent** or **weakly consistent** as documented. Use the right term; "thread-safe" does not automatically mean "every read is a globally linearizable snapshot."

## 6. Complete Example: Public Counter with a Javadoc Contract

Save as `AtomicCounterContractDemo.java` (Java 17+):

```java
import java.util.concurrent.atomic.AtomicLong;

public class AtomicCounterContractDemo {

    /**
     * A counter safe for concurrent use by multiple threads.
     *
     * <p>Each incrementAndGet() and get() is an atomic operation.
     * Each completed increment contributes exactly one to the value.
     * Calls from different threads may be ordered differently.
     *
     * <p>Multiple calls do not form an atomic transaction.
     * In particular, get() followed by incrementAndGet() does not
     * reserve a value or enforce a maximum.
     */
    public static final class Counter {
        private final AtomicLong value = new AtomicLong();

        /**
         * Atomically increments the value and returns the updated value.
         * Concurrent invocations may return in any order to callers.
         *
         * @return the value after this increment
         */
        public long incrementAndGet() {
            return value.incrementAndGet();
        }

        /**
         * Returns one atomic observation of the current counter.
         * The value may change immediately after this method returns.
         *
         * @return the observed value
         */
        public long get() {
            return value.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable increment10k = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.incrementAndGet();
            }
        };

        Thread first = new Thread(increment10k);
        Thread second = new Thread(increment10k);

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Total: " + counter.get());
    }
}
```

Compile and run:

```bash
javac AtomicCounterContractDemo.java
java AtomicCounterContractDemo
```

Exact stdout:

```text
Total: 20000
```

**Contract analysis:**

1. The class-level doc states that multiple threads can use **the same instance**.
2. `AtomicLong.incrementAndGet()` makes each increment atomic; the program loses no increments even when the two workers interleave.
3. There is no guarantee about which thread receives a specific value during concurrent execution. Execution and return order depend on scheduling.
4. `Thread.join()` succeeds before `main` reads the total, so by that point both workers have completed. Printing `20000` is justified by the number of increments and the atomic API, not by timing.
5. `get()` alone is thread-safe; a composition of `get` followed by `incrementAndGet` **does not form a transaction**. The Javadoc highlights this limit so callers do not build broken limit checks on top of it.

You do not need to mention in the Javadoc that the implementation uses `AtomicLong` if that is not part of the interface callers are meant to rely on. More importantly, the atomicity/ordering guarantees remain true if the implementation is later swapped to an appropriate lock.

## 7. Each Method's Contract Must Match Business Logic

Suppose an API manages a bounded list of entries. Two separate methods:

```java
int size();
void add(String entry);
```

even if both are `synchronized`, **do not guarantee** that a client can safely write:

```java
if (registry.size() < capacity) {
    registry.add(entry);
}
```

If two callers both observe `size` equal to `capacity - 1`, both may attempt to add. A well-designed public API should express the invariant directly:

```java
boolean tryAdd(String entry);
```

In the documentation, state clearly:

- `tryAdd` **atomically checks capacity and adds** in the same operation.
- Returns `true` only if the element was successfully added; `false` if already full at the atomic check point.
- Two callers competing for the last slot may receive different results; there is no guarantee that the caller that started earlier wins.
- `size()` cannot be used to "reserve a slot." `size()` only observes at a single point in time, and the value may change immediately after the method returns.

This moves correctness out of a hard-to-synchronize client sequence into an operation with a clear contract.

## 8. Complete Example: Thread-Safe Class Whose Iterator/Snapshot Must Also Be Documented

Save as `RegistryContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RegistryContractDemo {

    /**
     * A bounded, thread-safe collection of String entries.
     *
     * <p>All methods may be called concurrently on the same instance.
     * Each tryAdd() atomically checks the bound and adds an entry.
     * snapshot() returns an unmodifiable, independent list of values
     * captured while holding the same lock as the writers.
     *
     * <p>Entries may appear in either order when calls overlap.
     * Calling size() and then tryAdd() is not an atomic transaction.
     * Entries are immutable String objects.
     */
    public static final class Registry {
        private final int capacity;
        private final List<String> entries = new ArrayList<>();

        public Registry(int capacity) {
            if (capacity < 0) {
                throw new IllegalArgumentException("capacity < 0");
            }
            this.capacity = capacity;
        }

        /**
         * Atomically inserts a non-null entry if room remains.
         *
         * @return true if inserted, false if the registry is full
         * @throws NullPointerException if entry is null
         */
        public synchronized boolean tryAdd(String entry) {
            Objects.requireNonNull(entry, "entry");
            if (entries.size() >= capacity) {
                return false;
            }
            entries.add(entry);
            return true;
        }

        /**
         * Returns one atomic size observation.
         * The size may change immediately after this method returns.
         */
        public synchronized int size() {
            return entries.size();
        }

        /**
         * Returns an unmodifiable snapshot in insertion order as
         * observed while holding the lock.
         *
         * <p>The returned list is not a live view of this registry.
         * Later inserts do not change this snapshot.
         */
        public synchronized List<String> snapshot() {
            return List.copyOf(entries);
        }
    }

    public static void main(String[] args) throws Exception {
        Registry registry = new Registry(2_000);
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            @SuppressWarnings("unchecked")
            Future<?>[] jobs = new Future<?>[4];

            for (int worker = 0; worker < 4; worker++) {
                final int id = worker;
                jobs[worker] = pool.submit(() -> {
                    for (int i = 0; i < 500; i++) {
                        if (!registry.tryAdd(id + "-" + i)) {
                            throw new IllegalStateException("Unexpected full");
                        }
                    }
                });
            }

            for (Future<?> job : jobs) {
                job.get();
            }

            List<String> snapshot = registry.snapshot();
            System.out.println("Entries: " + registry.size());
            System.out.println("Snapshot size: " + snapshot.size());
            System.out.println("Can add more: " + registry.tryAdd("extra"));
        } finally {
            pool.shutdown();
        }
    }
}
```

Run:

```bash
javac RegistryContractDemo.java
java RegistryContractDemo
```

Stdout on a normal run:

```text
Entries: 2000
Snapshot size: 2000
Can add more: false
```

**Why is this contract trustworthy?**

- `tryAdd` performs both the capacity check and the `add` operation under the same monitor (`this`). When multiple callers contend for the final slot, only one caller can add, and the remaining callers observe the update.
- `size` and `snapshot` use **the same monitor**, so they observe a list structure consistent with `tryAdd` operations. No reference to the internal mutable `ArrayList` escapes the class.
- `List.copyOf` creates a list that cannot be modified through its API and is independent of later additions; in this example `String` is immutable, so there are no mutable elements requiring extra synchronization.
- Four workers submit 2,000 additions and then `Future.get()` is called on all four, so `main` does not print the counts before the tasks succeed. The order of strings across workers is nondeterministic, but the total count is deterministic.
- `snapshot` preserves insertion order at the point the lock was held, yet **does not guarantee** that concurrent worker calls will proceed in worker-id order or thread-start order.
- `size()` reads the current size and `tryAdd()` is a separate operation; a client composing them cannot infer a transaction.

**Documentation design must address ownership and mutable return values.** If `snapshot()` returned `entries` itself or returned an unmodifiable *view* over `entries`, the promise of an "independent snapshot" would be false. The implementation and Javadoc must match.

## 9. Thread-Safe Contracts Differ from Immutable and Read-Only Views

Compare three data-returning APIs:

```java
List<String> directView();       // Returns a mutable reference?
List<String> unmodifiableView(); // View reflecting changes to the source?
List<String> snapshot();         // Copy at a single point in time?
```

These are illustrative signatures without implementations. If an API returns a mutable reference that callers can modify directly, you can no longer claim the class maintains its internal invariants unless an appropriate protection mechanism is in place.

`Collections.unmodifiableList(source)` only prevents mutation **through the view**; if `source` continues to be modified elsewhere, the view reflects those changes. `List.copyOf(source)` creates an unmodifiable list, but copying `source` itself must still occur under valid conditions if `source` is being updated by another writer.

Documentation should state:

- Is the result a **live view** or a **snapshot**?
- Is the result **unmodifiable**? When can its contents change?
- If elements are mutable objects, may the caller mutate those elements?
- May the caller retain the result and use it on another thread, and what are the safe publication requirements?
- Does the API guarantee ordering or consistency across consecutive snapshots?

A thread-safe collection wrapping mutable values **does not automatically make every value thread-safe**. For example, `ConcurrentHashMap<String, ArrayList<String>>` protects map operations according to its contract, but the `ArrayList` values inside still need their own synchronization or ownership policy.

## 10. Compound Actions: The Most Important Warning in Documentation

Even `ConcurrentHashMap` requires distinguishing between **a single atomic method** and **a client-composed sequence of operations**.

```java
// Logic race if two threads update the same key concurrently.
Integer before = counts.get(key);
counts.put(key, before == null ? 1 : before + 1);
```

With `ConcurrentHashMap`, individual `get` and `put` operations are supported concurrently, but **get-then-put** is not automatically a transaction. The API documentation should point to the operation designed for this need:

```java
counts.merge(key, 1, Integer::sum);
```

`merge` is a per-key coordinated operation guaranteed by `ConcurrentHashMap`'s contract. However, if an update requires an invariant across **multiple keys**, a single-key `merge` does not provide a multi-key transaction.

For a listener list, "check if not registered, then register" also needs clear semantics. For a bounded registry, `tryAdd` must check and add within the same critical section. For an account, "check sufficient balance, then debit" must be a single protected operation.

Consider using this precise phrasing:

> "Individual operations are safe for concurrent calls. Client-composed sequences are not atomic unless explicitly documented."

If a public API allows callbacks or iterators, also address operations that **span beyond a single method invocation**.

## 11. Iterators and Streams: Does the Caller Need an External Lock?

A method returning an `Iterator<E>`, `Stream<E>`, or live view can extend data reading **beyond** the return of the method that created the iterator. If the lock is only held while creating the iterator, subsequent traversal steps can still occur while a writer is modifying the data.

For example, `Collections.synchronizedList(...)` synchronizes individual operations through the wrapper, but the caller typically **must manually synchronize on the wrapper for the entire iteration** when concurrent writers exist:

```java
List<String> list =
        Collections.synchronizedList(new ArrayList<>());

synchronized (list) {
    for (String value : list) {
        use(value);
    }
}
```

This is an illustrative snippet; it requires importing `java.util.List`, `java.util.ArrayList`, `java.util.Collections`, and defining `use`. If the API documentation only says "synchronized list" without stating the locking requirement during iteration, clients can easily misuse it.

An API backed by `ConcurrentHashMap` or `CopyOnWriteArrayList` has **different iteration semantics**:

- `ConcurrentHashMap`: the iterator is weakly consistent; it is not an atomic snapshot of the entire map.
- `CopyOnWriteArrayList`: the iterator holds a snapshot of the backing array at creation time; subsequent mutations do not appear in that traversal, and the iterator does not support `remove`.
- `Collections.synchronizedList`: callers must follow the contract for manual synchronization during iteration.

**Documentation must state the actual semantics of the returned type**, not just the implementation class name. If you want to spare users from managing locks, consider providing `snapshot()` or a scoped processing method.

## 12. Callbacks and Listeners: A Tricky Spot in Public Contracts

An API may safely update its internal collections while still invoking **client code** in a callback. In that case, you must document:

1. Which thread runs the callback: the caller thread, a dedicated worker, or a supplied executor?
2. Can **multiple callbacks run concurrently** on the same listener object?
3. May a callback call back into the API's own methods (reentrancy)?
4. Are internal locks held while invoking the callback?
5. If a callback throws an exception, how are the remaining listeners handled?
6. When `removeListener` runs concurrently with `publish`, can a removed listener still receive an in-progress event?
7. Are there guarantees for ordering, exactly-once delivery, or delivery on error/cancellation?

Here is an example API using `CopyOnWriteArrayList` that invokes callbacks directly on the caller's thread. This is a complete illustrative class (place it in `ListenerRegistry.java` if you use it):

```java
import java.util.Objects;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

/**
 * A thread-safe registry of listeners.
 *
 * <p>addListener, removeListener and publish may be called concurrently.
 * A publish call invokes callbacks synchronously on its caller's thread,
 * in the list order captured when its iteration begins.
 *
 * <p>Two concurrent publish calls may invoke the same listener
 * concurrently. A remove does not cancel a callback already included
 * in an in-progress publish snapshot.
 *
 * <p>Callbacks execute without an internal registry lock being held.
 * If a callback throws a RuntimeException, it propagates to the
 * publish caller and later callbacks in that publication are skipped.
 */
public final class ListenerRegistry {
    private final CopyOnWriteArrayList<Consumer<String>> listeners =
            new CopyOnWriteArrayList<>();

    public void addListener(Consumer<String> listener) {
        listeners.add(Objects.requireNonNull(listener));
    }

    public void removeListener(Consumer<String> listener) {
        listeners.remove(listener);
    }

    public void publish(String event) {
        for (Consumer<String> listener : listeners) {
            listener.accept(event);
        }
    }
}
```

**Why does this wording matter?** `CopyOnWriteArrayList` protects the list structure and iterator snapshot, but **does not automatically protect callback code**. Two callers invoking `publish` concurrently can cause the same listener to receive two concurrent callbacks. If the listener mutates ordinary state, it must protect that state itself, or the API must change its dispatch model.

This example has no `main`, so it has no stdout. It compiles standalone on JDK 17+ and expresses a concrete contract: callbacks run on the caller thread, may be concurrent, run without holding internal locks, and exceptions propagate and stop that publication pass. If you switch the implementation to an async executor, the contract for threads, ordering, completion, and errors must also change.

**Note:** Calling client code inside a `synchronized` block can extend lock hold times, introduce hard-to-analyze reentrancy, or cause deadlocks when a callback calls back into another API. Deliberately design when callbacks are invoked and publish those constraints.

## 13. Thread Ownership, Aliasing, and Mutable Parameters

A public API may accept a `List<T>`, `byte[]`, or another mutable object from the caller. The contract must clarify whether the API:

- **Copies immediately** to own its own data?
- **Retains the reference** for later use?
- **Transfers ownership** in a producer–consumer pipeline?
- **Allows the caller to mutate the input** while the method is executing?
- Synchronizes with other threads mutating the input?

For example:

```java
public final class TaskBatch {
    private final List<String> tasks;

    public TaskBatch(List<String> tasks) {
        this.tasks = List.copyOf(tasks);
    }

    public List<String> tasks() {
        return tasks;
    }
}
```

This class uses `List`, so it needs `import java.util.List;` if written as a standalone file. The constructor creates a snapshot of the input list (containing immutable `String`s) and does not mutate it afterward. However, **the caller must not concurrently mutate an ordinary input `ArrayList` while the constructor is copying it** if a meaningful result is expected. A contract should state that the constructor requires a stable input during copying and forbids nulls per the `List.copyOf` contract.

If the implementation retains a raw reference instead of copying, the Javadoc must warn the caller to uphold the invariants and synchronization rules for that alias. Making a field `final` only prevents reassigning the reference; it does not make mutable contents safe.

### Safe publication

A properly constructed object with immutable state eliminates many races, yet you should still state **that the caller must publish the instance properly** across threads when the design involves complex shared data. Mechanisms such as thread start, volatile references, locks, concurrent queues, or completion primitives establish happens-before rules.

For a properly constructed immutable class, `final` fields have special guarantees under the JMM provided the constructor does not let `this` escape prematurely. Even so, they do not "freeze" a mutable object graph exposed to the outside.

## 14. Blocking, Timeouts, Interruption, and Cancellation Belong in the Public Contract

A thread-safe API can still **block**, and caller correctness depends on how the method returns or stops.

For example, if `take()` waits for a queue to have an element, the documentation must state:

- `take()` **may block indefinitely** while the queue is empty.
- Whether the method responds to `Thread.interrupt()` by throwing `InterruptedException`.
- Whether timed overloads exist, and what unit the timeout uses.
- When a timeout occurs, whether any item could already have been consumed.
- When a running task is canceled, whether partially modified state is rolled back.
- When interrupted, whether the caller needs to restore the interrupt flag.

Never promise "cancellation always stops immediately." `Future.cancel(true)` typically only sends an interruption request when possible; tasks must cooperate with cancellation, and I/O operations have their own contracts.

A Javadoc block for a blocking method should look like:

```java
/**
 * Waits for the next message.
 *
 * <p>Concurrent producers and consumers are supported.
 * This method may block while the queue is empty.
 *
 * @return the next available message
 * @throws InterruptedException if interrupted while waiting
 */
public String take() throws InterruptedException {
    return queue.take();
}
```

This is an **illustrative method** inside a hypothetical class with a `queue` field of type `BlockingQueue<String>`; it is not a standalone program. The `InterruptedException` contract comes from the underlying API used. If the implementation later switches to busy-waiting or swallows interruption, the Javadoc is no longer accurate.

**Timeout** and **fairness** are distinct concepts. A timed method only bounds the wait duration according to its contract; it does not promise which caller wins contention or that callers are served in registration order.

## 15. Close and Lifecycle: Thread-Safe Does Not Mean Usable at All Times

When a public API has `close()`, `shutdown()`, `start()`, or `stop()`, define its state machine clearly enough.

For example:

```text
NEW -> OPEN -> CLOSING -> CLOSED
```

This is only an illustrative model; not every API has all four states.

Questions that must be documented:

- Can `close()` be called concurrently from multiple threads, and is it **idempotent**?
- Once `close` begins, is a concurrent `submit` accepted or rejected based on a clear **atomic decision point**?
- Do tasks accepted before `close` run to completion, or are they canceled?
- How are threads blocked in `take` or `await` woken up?
- Does `close` itself block waiting for all tasks, or does it only signal?
- After closing, is `getSnapshot` still usable? If not, which exception is thrown?
- Can callbacks that started before closing continue after `close` returns?

**Do not infer semantics from method names.** `ExecutorService.shutdown()`, for instance, stops accepting new tasks but typically lets already-submitted tasks run to completion; `shutdownNow()` attempts to stop running tasks and returns unstarted ones, without guaranteeing that all threads stop immediately. If you write a wrapper around an executor, the wrapper's documentation must state its own lifecycle policy.

A deadlock-avoidance contract must specify whether clients may call `close` from a callback or worker managed by the API itself. A `close` that waits for all workers to finish can deadlock if invoked from one of the very workers being awaited.

## 16. External Synchronization Conditions Must Be Written Precisely

For a public API that is **not itself thread-safe**, merely saying "synchronize access externally" leaves out essential information. Callers need to know **which lock** and **which scope**.

A good contract template:

> "Instances are not thread-safe. If an instance is accessed from multiple threads, the caller must synchronize all accesses to its mutable state, including reads, writes, iteration and compound operations, using the same lock. No mutable reference to internal state may be modified outside that lock."

If the class exposes a public lock, weigh the risk of clients using that lock for unrelated logic. If internal objects are not exposed, it is often simpler for the class to guard all operations with its own private lock or provide business-level atomic operations.

Avoid promising "thread-safe if caller synchronizes" without defining how that coordinates with internal writer threads created by the class itself: the caller might lock on `this` while the implementation uses a private lock, so external locking fails to synchronize with the worker.

### Safe publication is not a lock for subsequent mutations

If an object is initialized and **never mutated afterward**, it can be safely shared for reading after proper publication. However, if the caller later invokes a setter, subsequent reads require additional rules. The contract should distinguish "safely published immutable state" from "concurrent mutation supported."

## 17. Memory Consistency Effects: Describe Them at the Behavioral Level

The JMM uses **happens-before** relationships to define visibility and ordering guarantees. A public class does not have to expose internal locking details, but its documentation should rest on the memory consistency effects guaranteed by Java:

| Mechanism | Relation to the public contract |
| --- | --- |
| `synchronized` on the same monitor | Unlock happens-before a subsequent lock on that monitor |
| `volatile` write/read following the protocol | A volatile write happens-before a matching subsequent volatile read of the same variable |
| `AtomicLong` operations | Have corresponding atomic/volatile semantics for the value field |
| `Thread.start()` | Actions before `start()` happen-before actions in the newly started thread |
| Successful `Thread.join()` | Actions in the worker happen-before actions in the caller after `join()` returns |
| `ExecutorService.submit` and `Future.get` | Actions before `submit` HB the task; task actions HB the caller after `get` |
| `BlockingQueue` | Actions before putting an item into the queue HB actions after a consumer takes that item |
| `CountDownLatch` | Actions before `countDown()` HB actions after the matching `await()` returns |

**A happens-before edge is not a scheduling guarantee.** HB explains visibility and ordering. It does not promise that a task will run within a fixed number of milliseconds or will never suffer starvation. An API can be memory-safe yet still need timeouts, backpressure, and a liveness policy.

For a public API, translate these mechanisms into what the caller needs: "After `awaitCompletion()` returns normally, the results of tasks that completed before the signal are safely published to the calling thread," **if the implementation actually guarantees** this via the mechanism it uses.

## 18. Error Handling and Exceptions Under Concurrent Calls

When a method throws an exception, the caller needs to know **the impact on state**:

- If `tryAdd` throws `NullPointerException` on null input, does the operation leave any partial change?
- If a callback throws an exception, have earlier listeners already produced side effects?
- If an operation writes across multiple resources and is interrupted, can a **partial commit** occur?
- If retries are used, is the operation **idempotent** by key or request ID?
- Are worker exceptions captured in a future or silently ignored?

"Thread-safe" does not mean "every operation rolls back on error." **Atomicity** with respect to concurrent effects and **exception safety** are two separate properties. An API can be linearizable for successful operations while still needing documentation for state when an operation fails.

For example, in `RegistryContractDemo`, `Objects.requireNonNull(entry)` runs before checking or adding; null input throws `NullPointerException` without adding an item. The method documentation confirms this. For a method that invokes a callback before committing, the requirements differ and need an explicit commitment.

If an exception occurs in a task submitted via `ExecutorService.submit`, `Future.get()` normally surfaces the failure through `ExecutionException`. An API wrapping a future should not silently turn a failure into "completed successfully."

## 19. Documenting Interfaces and Extension Points: Who Owns Thread Safety?

When a public API is an interface or abstract class implemented by others, the contract must specify:

- **What can callers rely on** when using an arbitrary implementation?
- **What must implementers guarantee** to conform to the interface?
- Do default methods make assumptions about the thread safety of primitive operations?
- Can callbacks or extension hooks be invoked concurrently?
- Is an implementation allowed to choose a different locking strategy while preserving the same semantics?

If an interface states that all implementations must be thread-safe, an implementation using an ordinary `ArrayList` without synchronization **violates the interface contract**, even though the code compiles cleanly.

You can use Javadoc `@implSpec` to describe implementation requirements when appropriate, `@apiNote` for additional usage guidance, and `@implNote` for implementation notes. However, guarantees that callers must know should appear prominently in **the main public Javadoc**, not hidden in implementation-only notes.

An example of documenting responsibilities:

```java
/**
 * Concurrent key-value store.
 *
 * <p>Implementations must support concurrent invocations of get()
 * and put() on the same instance.
 * Each operation must be atomic for the specified key.
 * A read-modify-write sequence spanning two calls is not atomic.
 *
 * @param <K> key type
 * @param <V> value type
 */
public interface ConcurrentStore<K, V> {
    V get(K key);
    V put(K key, V value);
}
```

This is an interface contract example without `main`. A real API must also define the meaning of `null`, error behavior, ordering, and key equivalence scope. Avoid promising key-level atomicity that implementations cannot guarantee or verify.

## 20. Where to Place and How to Structure Javadoc

Write the thread-safety contract at the **class/interface level**, then supplement at the method level wherever behavior differs.

| Location | What to document |
| --- | --- |
| Class/interface Javadoc | Thread-safety level classification; instance/global scope; general guarantees; caller preconditions |
| Constructor/factory | Input ownership; safe publication; whether inputs are copied or retained; whether the instance is immediately usable |
| State-changing method | Atomicity; ordering; concurrent contention outcomes; errors; post-return conditions |
| Read/snapshot/iterator method | Snapshot vs. live view; consistency; ordering; mutable elements; whether external locking is required |
| Callback/subscription | Thread invoking the callback; concurrency/reentrancy; ordering; exceptions; removal semantics |
| Blocking/lifecycle method | Blocking/timeout/interruption; close/cancel/stop; idempotency and in-flight work |
| Extension point | Implementer obligations; concurrent vs. single-thread invocation; error propagation |

A concise and useful class-level sentence template:

> "Instances are safe for concurrent use. Each method performs one atomic operation as documented. No atomicity is guaranteed across multiple calls. Returned snapshots are unmodifiable and do not reflect later updates. Callbacks may run concurrently on caller threads and must themselves be thread-safe."

This statement is **only true** if the implementation actually has those behaviors. Do not copy it verbatim onto every class; choose the exact commitments that match your code rather than overpromising.

## 21. Does a Read-Only Public API Need a Contract?

Yes. An API that appears read-only can still:

- **Lazily initialize** a cache on first access, writing to an internal field or map.
- Update access statistics on every read.
- Read an external mutable resource that another thread is modifying.
- Return an iterator or live view mutated by another writer.
- Call a callback or logging collaborator that has mutable state.
- Cache results in an instance-level or global cache.

For example, `public List<String> getNames()` might create a snapshot on every call or return a live list. Those two designs have very different contracts. **The absence of setters in a public API does not prove the implementation has no mutation.**

Conversely, a class that holds only immutable state, has a proper constructor, and lets no mutable references escape is usually much easier to prove thread-safe. Its documentation should still clarify input/output ownership and publication assumptions.

## 22. Name Methods to Reflect Semantics, Then Document the Details

Method names help users form expectations, but they do not replace documentation:

- `snapshot()` suggests an independent point-in-time copy; specify consistency level and mutable elements.
- `tryAdd(...)` suggests returning an outcome under contention; specify atomicity and the `false` condition.
- `await(...)` suggests possible blocking; specify timeout/interruption and the condition guaranteed upon return.
- `submit(...)` suggests work may not complete immediately; specify the executor, ordering, rejection, and lifecycle.
- `close()` suggests resource release; specify concurrency with ongoing operations and idempotency.
- `addListener/removeListener` suggests callback registration; specify snapshots, concurrency, exceptions, and delivery count.

If a method has a very strong name such as `getConsistentSnapshot()`, the implementation must prove consistency across the entire dataset. Avoid wishful naming when no mechanism enforces it.

## 23. Verifying the Contract with Concurrent Test Cases

Good documentation should be **checkable against both the implementation and tests**, even though stress tests do not replace a JMM proof.

Categories of scenarios to test:

1. **Two writers on the same instance:** no lost updates, unintended duplicates, or invariant violations.
2. **Concurrent reader and writer:** reads return a state permitted by the contract; snapshots are not corrupted as writers continue.
3. **Two composed calls:** verify the documentation warns they are not atomic; if a transaction is needed, verify an operation at the right level exists.
4. **Races with close/cancel:** verify the task accept/reject decision point and how waiters are woken up.
5. **Reentrant callbacks:** verify whether a callback calling back into the API deadlocks, queues unexpectedly, or violates ordering.
6. **Concurrent callbacks:** verify whether the same listener can be invoked concurrently, and whether the documentation states that.
7. **Mutable inputs and aliases:** verify whether mutating an input after submission alters API results, and whether concurrent copying has undocumented behavior.
8. **Failure/interrupt/timeout:** verify state remains valid, permits/locks are released, and errors are propagated to the right place.
9. **Visibility:** verify that callers using proper publication or completion primitives observe the committed data after the wait point.
10. **Swapping implementations:** verify the behavioral contract still holds if `synchronized` is replaced with `Lock`, the storage structure changes, or the executor is swapped.

Do not write a test that merely "runs 1,000 times with no exceptions" and conclude the code is thread-safe. Race conditions depend on scheduling; a passing test does not mean all invalid interleavings have been ruled out. Reasoning about invariants and happens-before is the foundation; tests verify and catch violations.

### Reviewing the contract as a checklist

When reviewing a public API, read the Javadoc **as someone who knows only the documentation and cannot see the code**:

- Can you tell whether methods can be called concurrently on **the same instance**?
- Can you tell which operations are atomic and which are only individually thread-safe?
- Can you tell whether return values are snapshots, live views, or eventually consistent?
- Can you tell the contracts for callbacks, iterators, `close`, and failures?
- Can you tell what external lock or ownership discipline must be followed?
- Can the implementation be changed without breaking any published promises?

If an answer for a common behavior is missing, the public contract needs to be expanded. If the documentation promises something the implementation does not yet guarantee, fix the logic or narrow the promise before release.

## 24. Common Mistakes When Documenting Thread Safety

**Mistake 1 — Writing only "Thread-safe."** Fails to specify which methods are atomic, whether callbacks can run concurrently, or whether snapshots are consistent. Readers easily over-infer.

**Mistake 2 — Writing "Not thread-safe" without telling the caller what to do.** If external synchronization is required, specify which accesses must share the same lock, including iteration and compound operations.

**Mistake 3 — Treating `synchronized` as the entire contract.** `synchronized` on each method does not make multi-method sequences atomic; the code may still invoke callbacks or expose aliases outside the lock.

**Mistake 4 — Promising FIFO for concurrent producers without defining the order.** FIFO only has meaning for a well-defined enqueue order; it does not mean "if caller A starts first, event A always arrives first."

**Mistake 5 — Promising a snapshot while returning an unmodifiable view.** A view can change as the underlying collection changes. A snapshot requires an appropriate copy and publication path.

**Mistake 6 — Assuming a concurrent collection protects mutable values.** `ConcurrentHashMap<K, ArrayList<V>>` does not make the `ArrayList` values thread-safe.

**Mistake 7 — Omitting the callback threading model.** A listener may be invoked concurrently on the same instance by multiple callers; the listener's own state must be protected.

**Mistake 8 — Omitting blocking/interruption behavior.** Callers will not know whether a method can wait indefinitely, or whether canceling a task prevents the operation from completing.

**Mistake 9 — Labeling code "lock-free" or "non-blocking" by intuition.** Those are progress properties with formal definitions; they cannot be inferred from a `volatile` variable or an atomic field.

**Mistake 10 — Exposing internal mutable state.** A getter returning a raw list or map lets clients bypass locks, break invariants, and invalidate thread-safety promises.

**Mistake 11 — Forgetting constructors or static shared state.** An instance may be used safely after construction while its constructor retains a reference to mutable input, or multiple instances share an unprotected global cache.

**Mistake 12 — Not updating documentation when the implementation changes.** Switching from synchronous callbacks to async, or from a snapshot to a weakly consistent iterator, is a behavioral change callers may depend on; treat it as a contract change.

## 25. An Applicable Thread-Safety Contract Template

This is a **content outline** to adapt for a public Java class, not a template where every field must be filled in regardless of relevance:

```text
Thread safety:
  [Thread-safe | Conditionally thread-safe | Thread-confined | Not thread-safe]

Scope:
  Safe for concurrent calls on [the same instance | independent instances |
  shared global state]. Specify any exceptions.

Operation semantics:
  [Method A] is atomic with respect to [...]
  [Method B] returns [a snapshot | a live view | weakly consistent data].
  Multi-call sequences are [not atomic | atomic under documented protocol].

Input/output ownership:
  Inputs are [copied | retained | transferred].
  Returned values are [immutable snapshots | mutable caller-owned |
  shared views]. Specify mutable element responsibilities.

Blocking and callbacks:
  [Method] may block under [...], supports interruption/timeout [...]
  Callbacks run on [...], may be concurrent/reentrant [...],
  and exceptions are handled by [...].

Lifecycle:
  Concurrent close/submit/cancel is defined by [...]
  Accepted work and waiters after close behave as [...]

Caller obligations:
  [No external lock | Lock X around reads/writes/iteration |
  Do not mutate input while processing | Confine instances to thread X]

Unsupported guarantees:
  No guarantee of [cross-call atomicity | callback total order |
  fairness | a globally consistent aggregate snapshot | ...].
```

The value of this template is **exposing assumptions** before clients use the API. When an item does not apply (for example, the class has no callbacks), do not add meaningless sections to the Javadoc. However, if the API has blocking operations or returns mutable values, those points must be stated clearly.

## 26. Summary and Self-Check Questions

**Question 1:** A class has `synchronized void add(...)` and `synchronized int size()`. Does a client calling `if (size() < max) add(x)` guarantee not exceeding `max`?

**No.** The two calls are individually protected, but there is an interleaving window between them. You need an atomic operation combining both the check and the update, such as `tryAdd`.

**Question 2:** `ConcurrentHashMap` is thread-safe, so is `map.get(key).add(value)` thread-safe when the value is an `ArrayList`?

**Not automatically.** The map contract only protects map operations per its API; the mutable value still needs its own protection or ownership discipline.

**Question 3:** An API invokes callbacks on the caller thread. Can two callers invoking `publish` concurrently run the same callback concurrently?

**Possibly**, if the implementation allows it and does not enforce serialization. Document clearly that callbacks may run concurrently, and callback authors must keep their own state thread-safe.

**Question 4:** Is Javadoc saying "returns an unmodifiable list" enough for callers to assume the snapshot will not change with the source?

**No.** An unmodifiable *view* can reflect mutations to the source. State explicitly whether it is a live view or an independent snapshot, as well as the semantics for mutable elements.

**Question 5:** Can a thread-safe API block indefinitely?

**Yes.** Thread safety concerns the correctness of concurrent access; blocking and liveness are separate properties. Document waiting, timeouts, interruption, and lifecycle separately.

**Question 6:** Why does a `@ThreadSafe` annotation not replace Javadoc?

Because an annotation does not by itself define atomicity boundaries, ordering, snapshots, callbacks, input ownership, or shutdown behavior. Moreover, Java SE does not provide a single mandatory standard annotation for all APIs.

**Question 7:** When changing an implementation from locks to atomic variables, can you keep the same contract?

**Yes, provided** all semantics promised to callers remain true, including atomicity, visibility, ordering, error behavior, lifecycle, and output ownership. A contract describes what callers may rely on, without needing to pin internal locking details.

A useful public API is one that lets callers answer: **can I call this concurrently, which operations are atomic units, what outcomes are guaranteed, and what synchronization obligations belong to me?** When those questions are answered with accurate Javadoc and a conforming implementation, the thread-safety contract becomes a tool that prevents race conditions and preserves the ability to replace implementations in the future.
