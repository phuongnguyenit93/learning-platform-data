# AtomicIntegerArray, AtomicLongArray, and AtomicReferenceArray: Per-Element Updates in Java

> **Key takeaway:** These three classes in `java.util.concurrent.atomic` allow multiple threads to **atomically read, write, swap, increment/add, or compare-and-set (CAS) at a specific index** without manually locking the entire array for each operation. However, **per-element atomicity does not mean the entire array or a group of elements is a single transaction**. For `AtomicReferenceArray<E>`, atomicity applies to the **reference in a slot**, and does not automatically protect mutable state inside the referenced object.

This article belongs to the **Atomic & CAS** section of general Java concurrency. Examples target Java 17+ and Java SE APIs; Spring is not covered.

## 1. The problem: shared array elements can suffer from concurrent updates

Suppose multiple threads count occurrences by event type. A regular array can represent the counters:

~~~java
// Illustrative snippet, not a standalone program.
int[] counts = new int[4];

void record(int bucket) {
    counts[bucket]++; // Not atomic when multiple threads update the same bucket.
}
~~~

`counts[bucket]++` has three logical steps: **read → add → write**. Two threads that both read `10`, both compute `11`, and both write `11` will lose one update. For elements at different indices, an update to element A does not necessarily cause a data race with element B, but the overall algorithm must still consider invariants and how the array is published.

Possible solutions include wrapping every update in `synchronized`, using an array of `AtomicInteger`, or using **atomic array** classes that provide a unified API per slot. Atomic arrays are typically useful for modeling independent counters/states accessed by index without allocating a separate atomic object for each element.

### The three classes and their data types

| Class | Each element stores | Suitable examples |
| --- | --- | --- |
| `AtomicIntegerArray` | `int` | Histograms, retry counts per group, independent integer states |
| `AtomicLongArray` | `long` | 64-bit counters, per-partition sequences, large-value accumulation |
| `AtomicReferenceArray<E>` | Reference of type `E` | Slots holding immutable snapshots, object handles, per-slot state machines |

All three have a **fixed length after creation**. The API is not a `List` that can add or remove elements. An element is a position identified by `index`, typically `0 <= index < length()`; using an invalid index causes an index-bounds error as defined by the API.

### Visualizing the scope of atomicity

~~~text
AtomicIntegerArray:  [slot 0] [slot 1] [slot 2] [slot 3]
                        ^         ^
                        |         |
                   CAS/getAndAdd  incrementAndGet

Each operation is atomic for ITS OWN SLOT.
There is no "automatic transaction" spanning slot 0 + slot 1.
~~~

Do not read the phrase "atomic array" as "every whole-array read is atomic." The class name describes a **collection of elements with atomic operations**; it does not turn a `for` loop reading 100 elements into a simultaneous snapshot.

## 2. Important methods

### Common operations

| API | Meaning | Atomic scope |
| --- | --- | --- |
| `length()` | Fixed number of elements in the atomic array | Structural property, not an update |
| `get(i)` | Reads an element's value with the API's volatile semantics | One slot |
| `set(i, value)` | Writes an element's value with the API's volatile semantics | One slot |
| `lazySet(i, value)` | Writes with release semantics (in modern Java) | One slot; does not replace CAS |
| `getAndSet(i, value)` | Swaps and returns the old value | One slot |
| `compareAndSet(i, expected, update)` | Conditionally writes when current value matches expected, returns boolean | One slot |
| `getAndUpdate(i, function)` | Atomically transforms and returns the old value | One slot; function may be re-executed |
| `updateAndGet(i, function)` | Atomically transforms and returns the new value | One slot; function may be re-executed |

`AtomicIntegerArray` and `AtomicLongArray` also provide arithmetic APIs such as `getAndIncrement(i)`, `incrementAndGet(i)`, `getAndDecrement(i)`, `decrementAndGet(i)`, `getAndAdd(i, delta)`, and `addAndGet(i, delta)`. They also have `getAndAccumulate`/`accumulateAndGet` to combine the current value with an input value.

**Version note:** Memory-ordering APIs such as `getPlain`, `setPlain`, `getAcquire`, `setRelease`, and `compareAndExchange` have corresponding variants in modern Java. This article focuses on `get/set` and standard Java 17 RMW update operations; when optimizing low-level memory ordering, you must read each method's specific contract in the JDK API.

### Do not combine `get` and `set` and assume it is atomic

~~~java
// Incorrect for compound updates when multiple writers target the same index.
int previous = counts.get(2);
counts.set(2, previous + 1);
~~~

Even though `get` and `set` **individually** provide atomicity/visibility guarantees, there is a gap between the two calls where another thread can update slot 2. To increment atomically, use `incrementAndGet(2)` or a proper CAS loop.

Similarly, `volatile int[] shared` only gives volatile semantics to the **array reference**; it does not make `shared[i]++` atomic. Elements of `int[]` do not become volatile just because the variable pointing to the array is volatile.

## 3. Structure and initialization of atomic arrays

There are two common ways to construct them:

~~~java
// API snippet, not a standalone program.
AtomicIntegerArray ints = new AtomicIntegerArray(4);
AtomicLongArray longs = new AtomicLongArray(new long[]{2L, 4L, 6L});
AtomicReferenceArray<String> names =
        new AtomicReferenceArray<>(new String[]{"a", "b"});
~~~

Using the length constructor initializes slots to **default values**: `0` for `int`/`long`, `null` for references. Using the constructor that accepts an array **copies** the initial slot values into the atomic array's internal storage.

Key points:

- `new AtomicIntegerArray(sourceIntArray)` does **not** directly wrap `sourceIntArray`. Modifying the source array later does not change the atomic array.
- `new AtomicLongArray(sourceLongArray)` likewise copies primitive values.
- `new AtomicReferenceArray<>(sourceRefs)` copies **the references**, and does not clone the referenced objects. If a mutable object is modified via the source, the same object can still be observed through both paths.
- `length()` is immutable; if you need a dynamically resizable structure, you must redesign it (for example, publishing a new reference to the whole structure or using another concurrent container).

### Example 1 — verifying source array copying

Create the file `AtomicArrayCopy.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicIntegerArray;
import java.util.concurrent.atomic.AtomicReferenceArray;

public class AtomicArrayCopy {
    public static void main(String[] args) {
        int[] original = {1, 2};
        AtomicIntegerArray values = new AtomicIntegerArray(original);

        original[0] = 100;
        values.incrementAndGet(1);

        System.out.println("original = " + original[0] + "," + original[1]);
        System.out.println("atomic = " + values.get(0) + "," + values.get(1));

        StringBuilder mutable = new StringBuilder("start");
        StringBuilder[] references = {mutable};
        AtomicReferenceArray<StringBuilder> refs =
                new AtomicReferenceArray<>(references);
        references[0] = new StringBuilder("other");
        mutable.append("-changed");

        System.out.println("reference array slot = " + references[0]);
        System.out.println("atomic ref slot = " + refs.get(0));
    }
}
~~~

Run:

~~~bash
javac AtomicArrayCopy.java
java AtomicArrayCopy
~~~

Output:

~~~text
original = 100,2
atomic = 1,3
reference array slot = other
atomic ref slot = start-changed
~~~

The primitive part proves that the two arrays **have separate storage**. The reference part shows that reassigning `references[0]` does **not** change the slot in the atomic array, but the `mutable` object is still referenced by both sides; mutating `StringBuilder` through an alias still changes the object's contents. **AtomicReferenceArray does not make StringBuilder thread-safe.**

The operations on `StringBuilder` in this example run sequentially so the output is deterministic; if multiple threads concurrently modify the same `StringBuilder` without separate synchronization, there is still a data race risk.

## 4. AtomicIntegerArray — atomically incrementing each bucket

Each slot of `AtomicIntegerArray` acts like an `int` counter with RMW APIs. Instead of operating on a shared `int[]`, threads call `incrementAndGet(index)` to atomically increment a slot. Threads updating **different** slots do not need an application-level exclusive lock protecting the entire array.

### Example 2 — multiple threads incrementing the same index

Create `AtomicIntegerBuckets.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicIntegerArray;

public class AtomicIntegerBuckets {
    public static void main(String[] args) throws InterruptedException {
        AtomicIntegerArray buckets = new AtomicIntegerArray(2);
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            final int bucket = i % 2;
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 10_000; j++) {
                    buckets.incrementAndGet(bucket);
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("bucket 0 = " + buckets.get(0));
        System.out.println("bucket 1 = " + buckets.get(1));
        System.out.println("total = "
                + (buckets.get(0) + buckets.get(1)));
    }
}
~~~

Run:

~~~bash
javac AtomicIntegerBuckets.java
java AtomicIntegerBuckets
~~~

Deterministic output assuming no external errors:

~~~text
bucket 0 = 20000
bucket 1 = 20000
total = 40000
~~~

Two workers concurrently update bucket 0; the other two concurrently update bucket 1. `incrementAndGet(bucket)` prevents lost updates on each bucket. Main calls `join()` on all workers **before** summarizing, so all increments have completed.

If main reads slot 0 and slot 1 **while workers are still updating**, the sum of the two `get` calls is not an atomic point-in-time snapshot. In this example, `join` ensures the data is quiescent, so the subsequent sum is accurate.

### Differences among increment operations

~~~java
AtomicIntegerArray counters = new AtomicIntegerArray(new int[]{7});

int old = counters.getAndIncrement(0); // old = 7; slot = 8
int now = counters.incrementAndGet(0); // now = 9; slot = 9
int beforeAdd = counters.getAndAdd(0, 5); // beforeAdd = 9; slot = 14
~~~

This is an illustrative snippet. `getAndX` returns the **value before the update**, while `XAndGet` returns the **value after the update**. When writing logic based on ticket/sequence numbers, confusing the two return conventions can cause off-by-one bugs.

**Overflow:** `int`/`long` addition in the arithmetic API follows Java integer semantics (it wraps on overflow) and does not throw an exception on exceeding bounds. If you need to cap or forbid overflow, you can use a CAS loop with `Math.addExact` in a pure computation or a lock, and handle exceptions according to business requirements.

## 5. AtomicLongArray — 64-bit counters per slot

`AtomicLongArray` has a similar arithmetic API, except each slot is a `long`. It is suitable when the numeric range exceeds `int`, such as tracking bytes per partition or summing smallest currency units (with an appropriate overflow policy).

### Example 3 — summing bytes from workers

Create `AtomicLongPartitions.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicLongArray;

public class AtomicLongPartitions {
    public static void main(String[] args) throws InterruptedException {
        AtomicLongArray bytes = new AtomicLongArray(2);

        Thread a = new Thread(() -> {
            for (int i = 0; i < 10_000; i++) {
                bytes.getAndAdd(0, 100L);
            }
        });
        Thread b = new Thread(() -> {
            for (int i = 0; i < 10_000; i++) {
                bytes.addAndGet(0, 200L);
            }
        });
        Thread c = new Thread(() -> {
            for (int i = 0; i < 10_000; i++) {
                bytes.incrementAndGet(1);
            }
        });

        a.start();
        b.start();
        c.start();
        a.join();
        b.join();
        c.join();

        System.out.println("partition 0 = " + bytes.get(0));
        System.out.println("partition 1 = " + bytes.get(1));
    }
}
~~~

Run:

~~~bash
javac AtomicLongPartitions.java
java AtomicLongPartitions
~~~

Output:

~~~text
partition 0 = 3000000
partition 1 = 10000
~~~

Two workers contend on slot 0, updating atomically with `getAndAdd` and `addAndGet`; the third worker updates slot 1. Both `getAndAdd` and `addAndGet` **update atomically**, differing only in their return value.

Each element is a `long`; do not treat an `AtomicLongArray` as a 128-bit counter or an atomic "sum across multiple slots." If there is only **a single** number, `AtomicLong` may be simpler. If you only need statistical counting under high contention and do not require an exact snapshot mid-update, `LongAdder` is also a candidate, though its `sum()` is not an atomic snapshot while writers are active.

## 6. CAS on a single index: avoiding updates based on stale values

`compareAndSet(index, expected, update)` checks and updates **in a single operation**. For primitive arrays, comparison is by **primitive value**; for reference arrays, CAS compares by **reference identity**, without calling `equals`.

Pattern:

~~~text
old = array.get(i)            // Read snapshot of slot i
new = f(old)                  // Compute candidate
if array.compareAndSet(i, old, new):
    success                   // Write only if slot i still equals old
else:
    retry from current value  // Do not overwrite based on stale snapshot
~~~

A CAS loop is appropriate when the transformation lacks a dedicated API or requires a conditional constraint. For simple increments, `incrementAndGet` is usually shorter and less error-prone than writing a manual CAS loop.

### Example 4 — CAS loop for a capped value

Create `BoundedAtomicSlot.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicIntegerArray;

public class BoundedAtomicSlot {
    private static boolean reserve(
            AtomicIntegerArray used, int index, int capacity) {
        while (true) {
            int current = used.get(index);

            if (current >= capacity) {
                return false;
            }
            if (used.compareAndSet(index, current, current + 1)) {
                return true;
            }
            // Contention occurred; re-read the slot to decide from fresh data.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicIntegerArray used = new AtomicIntegerArray(1);
        Thread[] workers = new Thread[4];
        AtomicIntegerArray accepted = new AtomicIntegerArray(1);

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 100; j++) {
                    if (reserve(used, 0, 250)) {
                        accepted.incrementAndGet(0);
                    }
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("used = " + used.get(0));
        System.out.println("accepted = " + accepted.get(0));
    }
}
~~~

Run:

~~~bash
javac BoundedAtomicSlot.java
java BoundedAtomicSlot
~~~

Output:

~~~text
used = 250
accepted = 250
~~~

Four threads attempt to reserve a total of 400 spots in a slot with capacity 250. Only the thread whose CAS succeeds increments `used`, and the `current >= capacity` check prevents exceeding the cap. Each successful reservation increments by exactly 1; there are no lost updates.

**Note:** Updating `accepted` in this example is only for verification; it is **not** an atomic transaction together with `used` if another reader observes while workers are still running. After `join`, both values equal the number of successful reservations. When an invariant between two variables must hold at any arbitrary instant, use a single shared atomic state or a properly scoped lock.

## 7. AtomicReferenceArray<E> — atomically replacing the **reference** of each slot

`AtomicReferenceArray<E>` is suitable when each slot holds an object/handle or snapshot. Operations such as `get(i)`, `set(i, newRef)`, `getAndSet(i, newRef)`, and `compareAndSet(i, expectedRef, newRef)` update the **reference at slot i**, not deep inside the object.

Suppose each slot holds an immutable state:

~~~java
record Slot(String owner, int version) {}
AtomicReferenceArray<Slot> slots = new AtomicReferenceArray<>(2);
slots.set(0, new Slot("worker-a", 1));
~~~

The snippet above is not standalone because it needs imports and an enclosing method/class. If multiple threads replace slot 0 via CAS, each reference update is atomic and readers receive a complete snapshot version, never a "half-written reference."

### Reference CAS uses `==`, not `equals()`

Two objects with equal contents but **different identities** will not match in `compareAndSet` if `expected` is a different object instance.

Create `ReferenceCasIdentity.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicReferenceArray;

public class ReferenceCasIdentity {
    public static void main(String[] args) {
        String initial = new String("same");
        AtomicReferenceArray<String> slots =
                new AtomicReferenceArray<>(new String[]{initial});
        String equalButDistinct = new String("same");

        System.out.println("equals = " + initial.equals(equalButDistinct));
        System.out.println("same identity = " + (initial == equalButDistinct));

        boolean failed = slots.compareAndSet(0, equalButDistinct, "new");
        boolean succeeded = slots.compareAndSet(0, initial, "new");

        System.out.println("CAS different ref = " + failed);
        System.out.println("CAS original ref = " + succeeded);
        System.out.println("current = " + slots.get(0));
    }
}
~~~

Run:

~~~bash
javac ReferenceCasIdentity.java
java ReferenceCasIdentity
~~~

Output:

~~~text
equals = true
same identity = false
CAS different ref = false
CAS original ref = true
current = new
~~~

`new String("same")` is used specifically to demonstrate two objects with `equals` true but `==` false; it is not a recommendation to construct Strings with `new` in production code. When performing CAS on immutable state, you normally obtain **the current reference itself** via `get(i)` and compute the new state from that reference; do not construct an "equal" object and expect CAS to succeed.

## 8. AtomicReferenceArray + immutable snapshot + updateAndGet

When each slot holds an immutable object, `updateAndGet(i, f)` can produce a new state **from the current state of slot i**. The method retries automatically on contention, avoiding the need to write a manual CAS loop. However, **the function f may be invoked multiple times**.

### Example 6 — per-index versioned state

Create `ReferenceArrayUpdate.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicReferenceArray;

public class ReferenceArrayUpdate {
    record CounterState(long count, int version) {}

    public static void main(String[] args) throws InterruptedException {
        AtomicReferenceArray<CounterState> slots =
                new AtomicReferenceArray<>(
                        new CounterState[]{
                                new CounterState(0, 0),
                                new CounterState(0, 0)
                        });

        Runnable updateFirst = () -> {
            for (int i = 0; i < 1_000; i++) {
                slots.updateAndGet(0, old ->
                        new CounterState(old.count() + 1, old.version() + 1));
            }
        };

        Thread a = new Thread(updateFirst);
        Thread b = new Thread(updateFirst);
        Thread c = new Thread(() -> {
            for (int i = 0; i < 500; i++) {
                slots.updateAndGet(1, old ->
                        new CounterState(old.count() + 2, old.version() + 1));
            }
        });

        a.start();
        b.start();
        c.start();
        a.join();
        b.join();
        c.join();

        CounterState first = slots.get(0);
        CounterState second = slots.get(1);
        System.out.println("first = " + first.count() + "/" + first.version());
        System.out.println("second = " + second.count() + "/" + second.version());
    }
}
~~~

Run:

~~~bash
javac ReferenceArrayUpdate.java
java ReferenceArrayUpdate
~~~

Output:

~~~text
first = 2000/2000
second = 1000/500
~~~

In each slot, the `count` and `version` pair live **in the same immutable record**, and the reference is swapped in one atomic operation. Therefore, a reader calling `get(slot)` obtains **a consistent snapshot of both fields** from the same version. The two slots remain independent: reading slot 0 then slot 1 does not form a point-in-time snapshot of both.

**The update function must be side-effect-free:** two threads may both read snapshot A; when one thread's CAS succeeds, the other must recompute from the new snapshot. Therefore, the lambda can be applied multiple times. Do not call an API to send an email, charge an external account, increment another counter, or log something you expect to happen "exactly once" inside the lambda.

In the example, allocating `new CounterState(...)` is an internal part of computing the candidate; if CAS fails, the candidate object is not published. The formula must be pure and must not rely on unsynchronized external mutable data.

## 9. AtomicReferenceArray does not protect mutations of the referenced object

This is a common mistake:

~~~java
// Unsafe illustrative code; not a standalone program.
AtomicReferenceArray<MutableCounter> slots =
        new AtomicReferenceArray<>(1);
slots.set(0, new MutableCounter());

void increment() {
    slots.get(0).value++; // Updating the inner field is not atomic.
}
~~~

`slots.get(0)` reads the **reference** atomically/volatily; immediately afterward, `value++` is still a non-atomic RMW on a shared mutable object. If two threads concurrently update that object, they can lose updates. If the object is still mutated after publication, you need separate synchronization, atomic fields on the object itself, ownership isolation, or **replacing the whole object with an immutable snapshot** via CAS as shown in the previous section.

**Do not confuse:**

- Atomicity of the **slot reference**: reading/writing/swapping the reference will not tear into a "half pointer."
- Atomicity of **internal fields**: depends on the object's class and its own protocol.
- Atomicity across **multiple slots**: not provided directly by the three atomic array classes.

Using `AtomicReferenceArray<AtomicInteger>` does not contradict this: if each slot holds an `AtomicInteger` and the caller calls `incrementAndGet()` on that object, the increment is atomic because of **AtomicInteger**, not because of the outer "reference array." You must consider the overhead and consistency implications if the slot reference itself could be replaced while a caller is incrementing the old object.

## 10. No multi-element transactions

Suppose you need to transfer 10 units from account 0 to account 1, with the invariant that **the total must always equal 200**. An atomic array for the two slots can update each slot individually, but does not protect both as **a single** transfer:

~~~java
AtomicIntegerArray balances =
        new AtomicIntegerArray(new int[]{100, 100});

balances.addAndGet(0, -10);
balances.addAndGet(1, 10);
~~~

Between the two calls, another thread can read `90` in slot 0 and `100` in slot 1, observing a total of `190`. Each update is atomic, yet the sum invariant is not preserved at every observation point.

### Example 7 — deterministically demonstrating the gap between two slots

Create `CrossSlotNotAtomic.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicIntegerArray;

public class CrossSlotNotAtomic {
    public static void main(String[] args) throws InterruptedException {
        AtomicIntegerArray balances =
                new AtomicIntegerArray(new int[]{100, 100});
        CountDownLatch firstUpdated = new CountDownLatch(1);
        CountDownLatch resume = new CountDownLatch(1);

        Thread transfer = new Thread(() -> {
            balances.addAndGet(0, -10);
            firstUpdated.countDown();
            try {
                resume.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            balances.addAndGet(1, 10);
        });

        transfer.start();
        firstUpdated.await();

        System.out.println("during = "
                + (balances.get(0) + balances.get(1)));

        resume.countDown();
        transfer.join();

        System.out.println("after = "
                + (balances.get(0) + balances.get(1)));
    }
}
~~~

Run:

~~~bash
javac CrossSlotNotAtomic.java
java CrossSlotNotAtomic
~~~

Stdout when not externally interrupted:

~~~text
during = 190
after = 200
~~~

`CountDownLatch` pauses the writer **between the two updates**, so main reliably observes an intermediate state; this is not a result of scheduler luck. Even if a reader reads both slots in a tight `for` loop, there is still no atomic snapshot across slots.

### Solutions when invariants span multiple elements

- **Use a single lock covering both writers and readers:** all transfers, total/snapshot reads, and invariant checks use **the same monitor or Lock**. Readers wanting a consistent snapshot must participate in that protocol; having only writers lock is not enough.
- **Immutable whole-state + AtomicReference<State>:** if the state is small and easy to copy, keep both balances in an immutable record or object and swap **a single reference** via CAS. Updating the whole state has a single linearization point at the reference swap.
- **Dedicated transactional/concurrent data structures:** when business logic involves multi-step transactions, choose structures/synchronizers suited to the invariant. Do not try to "lock each slot independently" and claim the whole group is preserved.
- **Distinguish metric snapshots from transactions:** for approximate statistics, two consecutive `get` calls may be acceptable; for money, total quotas, or multi-warehouse inventory, usually not.

A simple monolithic state example:

~~~java
// Illustrative snippet; not a standalone program.
record Pair(int left, int right) {}
AtomicReference<Pair> state =
        new AtomicReference<>(new Pair(100, 100));

Pair after = state.updateAndGet(old ->
        new Pair(old.left() - 10, old.right() + 10));
~~~

A single `updateAndGet` swaps the entire reference, so a reader calling `state.get()` gets a consistent `Pair`. Balance checks, overflow handling, retries, and business policies must be handled inside the pure computation; do not invoke external side effects inside the lambda.

## 11. The ABA problem when using CAS on references

CAS checks *whether the current value equals expected*, not the entire **history** of the slot. For example, a reference in a slot can change A → B → A; a thread holding expected A sees CAS succeed because the slot points back to A, even though intermediate changes occurred. This is the **ABA** problem for algorithms that need to detect every change.

With immutable objects where each version allocates a new object, returning to **the exact same reference A** may occur less often, but you cannot rely on probability as an algorithmic guarantee. When you need to detect version changes, you can attach a **version/token** inside the immutable state and CAS on the **state object containing both data + version**; or use classes like `AtomicStampedReference` depending on the situation (this class is not an atomic array).

Note that CAS on primitive `int` can also encounter A → B → A in **value**. The issue is only dangerous when logic needs to know whether an intermediate change occurred; not every CAS counter suffers from ABA bugs.

## 12. Memory visibility, ordering, and update functions

Atomic arrays provide clear memory guarantees per operation:

- `get(i)` reads with **volatile read** semantics, and `set(i, v)` writes with **volatile write** semantics per modern Java documentation.
- `compareAndSet` and standard RMW operations have synchronization effects specified by the API; they are not just ordinary Java comparisons.
- `lazySet`/`setRelease` have **release semantics**, which are not equivalent to `set` in all cases; use them when designing matching memory-ordering and read protocols.
- `getPlain`/`setPlain`/`getOpaque`/`setOpaque`/`getAcquire`/`setRelease` have their own contracts and **should not be substituted arbitrarily** just for optimization.
- A `get(i)` call does not provide an atomic snapshot for all `j != i`.
- Threads use `join`/`Future.get` to wait for work to finish before verifying final results, rather than reading mutating data and treating it as the final result.

Another misconception: "`updateAndGet` will invoke the lambda exactly once." False. Under contention, the function may be called again. `UnaryOperator`/`IntUnaryOperator`/`LongUnaryOperator` or binary operators used in accumulate should be **side-effect-free**, must not mutate input objects, and must not depend on invocation counts.

### CAS loops do not guarantee fair progress for every thread

Atomic operations can avoid waiting on a traditional monitor per slot, but that **does not automatically guarantee** all threads will finish within a bounded time. A thread under high contention can retry many times; scheduler behavior and cache coherence costs still affect latency. Algorithmically lock-free does not mean wait-free or "zero synchronization cost."

## 13. Index checking and responsibility sharing

Atomic arrays are typically created once and passed to workers. To avoid bugs:

1. Define the **index mapping** clearly: what event type, partition, client, or state machine does each index represent?
2. Validate indices from input if data comes from external sources; a fixed `length()` does not protect against negative or out-of-bounds indices.
3. If multiple threads update **the same slot**, use an atomic RMW such as `incrementAndGet`/CAS as needed.
4. If only one thread writes a slot and multiple threads read it, you still need to evaluate publication and memory visibility; atomic arrays provide appropriate APIs.
5. Do not assume each index corresponds to an independent object in `AtomicReferenceArray`: two slots can point to **the same mutable object**, and any mutation of that object is a separate concern.
6. Do not let callers hold a reference to the **source array** and assume they are directly modifying the atomic array; the constructor copies the storage/references.
7. For indices containing `null` in a reference array, `get(i)` can return `null`; `updateAndGet` code must handle `null` when appropriate to avoid `NullPointerException`.
8. Do not write logic that depends on an atomic array's `toString()` being an atomic snapshot: reading elements one by one while writers are active can observe multiple points in time.

### Common design mistakes

| Mistake | Consequence | Correct fix |
| --- | --- | --- |
| `int[] counts` with concurrent `counts[i]++` | Lost updates | `AtomicIntegerArray.incrementAndGet(i)` |
| `AtomicIntegerArray.get(i)` + `set(i, new)` | Compound action still races | `getAndAdd`, `updateAndGet`, or CAS |
| `volatile int[]` then `array[i]++` | Volatile reference does not make elements atomic | Use atomic array or lock |
| `AtomicReferenceArray` holding `ArrayList` and mutating the list | List mutation is not thread-safe | Immutable value, copy, lock, or proper concurrent collection |
| Newly constructed CAS expected that is only `equals` to current | CAS fails due to different reference identity | Use the actual reference from `get(i)` |
| Update lambda calls an external API | Side effect may execute multiple times due to retries | Pure update function; separate side effects |
| Two slots updated with two atomic calls, assuming a transaction | Reader sees intermediate state | Group lock or `AtomicReference` to whole-state |
| Reading multiple slots and summing while writers are running | Not an atomic snapshot | Join first or design a snapshot mechanism |
| Treating `LongAdder.sum()` as a strict snapshot | Figures may miss concurrent updates | `AtomicLong`/lock if a consistent snapshot is needed |
| Using multiple atomic slots without defining index ownership | Hard to maintain invariants | Document index mapping, encapsulate API |
| Using an atomic array for an entire business workflow with I/O | One atomic slot does not protect side effects | Appropriate state machine/lock/transaction |
| Benchmarking once and claiming it is always faster | JIT, contention, cache layout, and scheduling add noise | Representative benchmarks, verify correctness first |

## 14. Performance: per-slot atomicity does not mean zero contention

Because multiple threads can CAS the same slot, performance can be dominated by contention and cache coherence:

- **Same "hot" index**: multiple threads running CAS on one slot can degrade throughput due to CAS retries and cache line bouncing.
- **Many independent indices**: usually reduces logical contention, but memory layout may cause adjacent slots to share a cache line (*false sharing*), depending on the implementation/JVM/CPU. Do not claim that atomic arrays eliminate false sharing.
- **Memory footprint**: `Atomic*Array` differs from allocating a separate `AtomicInteger`/`AtomicLong` per slot; memory overhead and layout characteristics should be measured if important.
- **Read-heavy vs. write-heavy workloads**: If mostly reads, an immutable snapshot + volatile or a specialized data structure is sometimes more efficient; if heavily write-bound, `LongAdder`/sharding for statistics may be worth trying.
- **Number of slots**: fixed-size arrays fit stable mappings; concurrent maps fit dynamic indices/keys.

Do not infer performance from "lock-free is always fast." Measure throughput, p95/p99 latency, CAS failures/retries if instrumentable, allocations, and system state on representative data. You can use JMH for warmed-up, multi-iteration microbenchmarks.

### When to use which class?

| Problem | Implementation approach |
| --- | --- |
| N independent `int` counters, fixed indices | `AtomicIntegerArray` |
| N independent `long` counters, large values | `AtomicLongArray` |
| N immutable states per slot, needing atomic reference swaps | `AtomicReferenceArray<State>` |
| A single counter | `AtomicInteger` / `AtomicLong` |
| Statistical sums incremented under high contention, approximate reads | `LongAdder`/`LongAdder[]` with proper publication policy |
| Whole structure needs consistent snapshots, multi-field/slot updates | Shared lock or `AtomicReference<ImmutableWholeState>` |
| Dynamic keys, independent per-key updates | `ConcurrentHashMap`/atomic methods |
| Multiple external operations must be "all-or-nothing" | Need another transaction/state-machine protocol; atomic array is insufficient |

## 15. Self-check questions

**Q1.** Four threads each execute `counts.incrementAndGet(0)` 1,000 times; after all `join`, what is the value in slot 0?  
**Answer:** `4000`, assuming no other updates or external exceptions. Each increment on slot 0 is an atomic RMW.

**Q2.** Does `AtomicLongArray` automatically guarantee that the sum of slot 0 and slot 1 is read as a snapshot?  
**Answer:** No. Two `get` calls are two separate operations; a writer can interleave between them.

**Q3.** Does `AtomicReferenceArray<Person>` make `person.age++` atomic?  
**Answer:** No. Atomicity of the slot reference does not protect mutable fields of the object.

**Q4.** Two `String`s have the same content but different references; will CAS succeed if `expected` is the new string with `equals` true?  
**Answer:** No, if `current` is still the old reference; reference CAS is based on identity `==`.

**Q5.** Does `updateAndGet(i, f)` call `f` exactly once?  
**Answer:** Do not assume so. `f` may run multiple times due to retries under contention; avoid side effects.

**Q6.** When passing `int[] a` to `new AtomicIntegerArray(a)`, does updating `a[0]` change atomic slot 0?  
**Answer:** No. Source array values are copied at initialization.

**Q7.** When creating `AtomicReferenceArray<Mutable>` from a source array, does it deep-copy all objects?  
**Answer:** No. It copies references per slot; the same mutable object can still be used in multiple places.

**Q8.** If you want to prevent two balances from ever having a sum other than 200 even during a transfer, is it enough to call `addAndGet(0, -10)` then `addAndGet(1, 10)`?  
**Answer:** No. Use the same lock to protect updates and snapshots, or keep the entire state in an immutable reference updated atomically.

**Q9.** Why do `getAndIncrement` and `incrementAndGet` differ?  
**Answer:** Both update atomically, but the first returns the old value and the second returns the new value.

**Q10.** One slot is heavily updated with CAS. Does "not using synchronized" guarantee zero contention?  
**Answer:** No. CAS can retry, incur cache coherence overhead, and delay threads; measure on real workloads.

## Official documentation

- [`AtomicIntegerArray` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerArray.html): constructors, per-element arithmetic/CAS, memory ordering.
- [`AtomicLongArray` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLongArray.html): long updates by index.
- [`AtomicReferenceArray` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReferenceArray.html): reference swaps/CAS/update by index.
- [`AtomicReference` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): replacing whole state with a single reference.
- [`AtomicStampedReference` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html): reference with a stamp for certain algorithms requiring versioning.
- [`LongAdder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): statistical counting option under high contention; `sum` is not an atomic snapshot.
- [Java Language Specification 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): visibility, ordering, happens-before.

**Remember:** `AtomicIntegerArray`, `AtomicLongArray`, and `AtomicReferenceArray` help update **each slot** with an atomic API. The atomic scope **does not automatically extend** across multiple slots, an entire object graph, or external side effects. Choose the right operation (`incrementAndGet`, `getAndAdd`, `compareAndSet`, `updateAndGet`) and clearly identify the invariants you actually need to protect.