# Designing Small, Easily Verifiable Critical Sections in Java

> **Goal:** Accurately identify the data and invariants that need protection; design a critical section that is **large enough to be correct**, yet **small enough to reduce contention and remain easy to verify**; know how to move independent operations outside the lock, avoid calling uncontrolled code while holding a lock, and keep changes that must be atomic within the same synchronization boundary.

This article belongs to the **Synchronization** group of general Java concurrency. The examples use Java SE 17+ with `synchronized`, `ReentrantLock`, and several `java.util.concurrent` utilities. Spring mechanisms are not used.

## 1. What Is a Critical Section?

A **critical section** is a block of code that must execute under a coordination mechanism to protect data or invariants that multiple threads may access concurrently. With mutual exclusion using a lock, at any given time only one thread may be inside critical sections that use **that same lock**.

A simple example:

~~~java
// Illustration only, not a standalone program.
private final Object lock = new Object();
private int count;

void increment() {
    synchronized (lock) {
        count++;
    }
}
~~~

`count++` is a read-modify-write operation, consisting of reading the old value, adding, and writing. When all threads perform updates through the **same `lock`**, this entire update lies within the mutual exclusion region. The lock prevents lost updates; at the same time, an `unlock` followed by a subsequent `lock` on the same monitor also establishes a *happens-before* relationship for observing the data.

Do not equate a “small critical section” with “having few lines of code.” A one-line block can contain a very slow I/O call or a callback that calls back into the system. Conversely, a multi-line block that checks and updates state may be the **smallest atomic unit that preserves the invariant**.

### Three Criteria for Evaluation

1. **Correctness:** No other thread can interleave between steps that require the same invariant; every access path to the state uses the same synchronization protocol.
2. **Reviewability:** A reader looking at the code can immediately see which object is locked, which state is protected, and what the valid state is before and after the block.
3. **Contention:** The lock is held for a reasonable duration; time-consuming code or code that does not depend on the state is moved outside if doing so **does not break the invariant**.

The priority order is **correctness first, simplicity and verifiability second, and only then optimizing contention based on measurement**. Narrowing a lock by splitting an operation that must be atomic may sometimes make the program faster in a benchmark, but it is no longer correct.

## 2. Start from Invariants, Not from the `synchronized` Line

An **invariant** is a condition that must always hold at points where other threads are permitted to observe the state. For example, in an inventory:

- `available >= 0`: stock is non-negative.
- At most the number of remaining orderable items can be approved.
- An order is accepted only if checking and decrementing the stock belong to **the same decision**.

Incorrect organization (illustration):

~~~java
if (inventory.available() > 0) { // Locked or atomic read.
    inventory.decrement();        // Separate locked or atomic write.
}
~~~

Even if each method is individually synchronized, another thread can take the last item **between the two calls**. *Check-then-act* is a compound action; correctness depends on the boundary enclosing both steps.

A better design is to put **both the condition and the state transition** into the same method:

~~~java
boolean reserveOne() {
    synchronized (lock) {
        if (available == 0) {
            return false;
        }
        available--;
        return true;
    }
}
~~~

This is a sufficiently small critical section: inside the lock it only does what truly depends on `available`; the method returns a boolean rather than forcing the caller to check first and update at a later time.

### Define Ownership Right in the API

It is better to keep shared state `private` and not expose arbitrary setters/getters that break the synchronization rules. APIs such as `reserveOne()`, `snapshot()`, `transfer()`, or `submit(...)` clearly express **an atomic business operation**.

A getter returning `available` may be valid for displaying statistics, but that value should not be used as permission to perform an update at a later time. The getter's value is a snapshot that may already be stale as soon as the lock is released.

## 3. Example 1 — Testable Correctness of Checking and Decrementing Stock

Create `InventoryDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class InventoryDemo {
    private static final class Inventory {
        private final Object lock = new Object();
        private int available = 1;

        boolean reserveOne() {
            synchronized (lock) {
                if (available == 0) {
                    return false;
                }
                available--;
                return true;
            }
        }

        int remaining() {
            synchronized (lock) {
                return available;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory inventory = new Inventory();
        AtomicInteger approved = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);

        Runnable task = () -> {
            try {
                start.await();
                if (inventory.reserveOne()) {
                    approved.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(task, "a");
        Thread b = new Thread(task, "b");
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        System.out.println("approved = " + approved.get());
        System.out.println("remaining = " + inventory.remaining());
    }
}
~~~

Run:

~~~bash
javac InventoryDemo.java
java InventoryDemo
~~~

Stdout when not externally interrupted:

~~~text
approved = 1
remaining = 0
~~~

Both threads can contend at `reserveOne()`, but **only one thread** passes through the check/update section at a time. With `available = 1`, the first one to enter the lock decrements it to `0`; the other receives `false`. The result always approves exactly once.

`CountDownLatch` only helps the two tasks start close together to demonstrate contention; correctness comes from the monitor, not from whether the threads happen to run simultaneously. `approved` uses `AtomicInteger` so that recording the result from both threads does not create a second race in the example.

**Boundary to remember:** Do not move `available == 0` outside the lock and only lock `available--`. The condition and the state transition belong to **the same atomic decision**.

## 4. Process for Determining Critical Section Boundaries

Before adding `synchronized` or `lock.lock()`, draw up a “state map”:

| Question | What to Confirm |
| --- | --- |
| What data is shared? | Mutable fields, references, collections, and object graphs touched by multiple threads |
| What are the invariants? | For example, non-negative balance, unique IDs, conserved sum across two accounts |
| Which operations read state to decide a write? | Check-then-act, read-modify-write, iterating over a structure and then updating |
| Who is allowed to modify? | Single writer, multiple writers, or ownership transfer of state |
| What scope of atomicity is needed? | A single variable, a record, a group of fields, or multiple objects |
| Which lock owns the invariant? | A consistent private monitor/`ReentrantLock`; with an ordering if multiple locks are involved |
| What can be done outside the lock? | Independent computation, input parsing, creating immutable objects, I/O or notifications that do not need to hold the invariant |
| What cannot be split? | Checking current state and updating based on it; reading multiple fields into a consistent snapshot |

### Classifying Operations by *Dependency*

**Independent work** is work that uses local/immutable inputs and does not need the protected state. For example, parsing a request string, validating format, or creating an immutable DTO. This can usually be done before acquiring the lock.

**State-dependent work** needs to read shared state to make a decision, such as “if the balance is sufficient, deduct the amount” or “if the key does not exist, insert.” This must be done under a lock, or using a dedicated atomic primitive.

**External side effects** are I/O, sending messages, network logging, callbacks, or API calls with variable latency. They should usually happen **after releasing the lock**, but state transitions and failures at this step must be designed explicitly. You cannot simply move a side effect outside the lock and assume the business operation remains atomic.

## 5. Example 2 — Independent Computation Outside, Short Commit Inside

Create `ShortCriticalSectionDemo.java` (Java 17+):

~~~java
public class ShortCriticalSectionDemo {
    private static final class Total {
        private final Object lock = new Object();
        private long cents;

        void addTextAmount(String input) {
            // Read, parse, and validate immutable input outside the lock.
            long delta = Long.parseLong(input);
            if (delta <= 0) {
                throw new IllegalArgumentException("positive amount required");
            }

            // Update shared state only once a valid delta is ready.
            synchronized (lock) {
                cents = Math.addExact(cents, delta);
            }
        }

        long snapshot() {
            synchronized (lock) {
                return cents;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Total total = new Total();
        Runnable work = () -> {
            for (int i = 0; i < 1_000; i++) {
                total.addTextAmount("1");
            }
        };

        Thread a = new Thread(work);
        Thread b = new Thread(work);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("total = " + total.snapshot());
    }
}
~~~

Run:

~~~bash
javac ShortCriticalSectionDemo.java
java ShortCriticalSectionDemo
~~~

Stdout:

~~~text
total = 2000
~~~

In this example, `Long.parseLong(input)` and validating `delta` do not depend on the shared `cents`, so they can be done outside the lock. However, **reading `cents`, adding, and writing back** must be in the same critical section. `Math.addExact` throws `ArithmeticException` on overflow, and because the RHS is evaluated before the assignment, an overflow will not assign an overflowed value to `cents`.

**Be careful:** If the computation outside the lock relies on a `cents` value read earlier, the result can suffer from a stale snapshot bug. Only separate parts that are **truly independent**. If you must compute outside the lock from a snapshot and then commit, you need to re-check a version/CAS or use an explicit optimistic protocol (see Section 10).

## 6. Small Lock Regions Must Not Break Multi-Field Invariants

Suppose a ledger has `total` and `version`. The business invariant is that **every successful increase to `total` must increment `version` by exactly one**. This code is wrong:

~~~java
// Wrong: the two updates are not protected as a single unit.
synchronized (lock) {
    total += delta;
}
// A reader can interleave in between.
synchronized (lock) {
    version++;
}
~~~

Even though each part is individually inside a lock, a reader of `total` and `version` can observe a snapshot from **two different versions** if it acquires the lock in between. Protect an update method and a snapshot method:

~~~java
void add(long delta) {
    synchronized (lock) {
        total += delta;
        version++;
    }
}

Snapshot snapshot() {
    synchronized (lock) {
        return new Snapshot(total, version);
    }
}
~~~

The lock must cover all fields that need to be consistent together. Readers must also acquire **the same lock** when reading the snapshot; if only writers lock while readers perform unguarded reads, things can still go wrong.

### Example 3 — Consistent Snapshot from Multiple Fields

Create `ConsistentSnapshotDemo.java`:

~~~java
public class ConsistentSnapshotDemo {
    private record Snapshot(long total, long version) {}

    private static final class Ledger {
        private final Object lock = new Object();
        private long total;
        private long version;

        void addOne() {
            synchronized (lock) {
                total++;
                version++;
            }
        }

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(total, version);
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();

        Runnable work = () -> {
            for (int i = 0; i < 10_000; i++) {
                ledger.addOne();
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);
        first.start();
        second.start();
        first.join();
        second.join();

        Snapshot result = ledger.snapshot();
        System.out.println("total = " + result.total());
        System.out.println("version = " + result.version());
        System.out.println("consistent = "
                + (result.total() == result.version()));
    }
}
~~~

Run:

~~~bash
javac ConsistentSnapshotDemo.java
java ConsistentSnapshotDemo
~~~

Stdout:

~~~text
total = 20000
version = 20000
consistent = true
~~~

`snapshot()` returns an immutable record created **inside the critical section**, so the pair of fields represents a consistent state of the ledger. The caller can process the snapshot outside the lock without continuing to hold the monitor, because it is immutable data consisting of two numbers.

Do not return a mutable internal object directly to the caller and claim the snapshot is thread-safe; when the state is still mutated by other workers, the caller needs a copy or an appropriate synchronization protocol.

## 7. Reduce Lock Hold Time by Not Performing I/O Under a Lock

Operations with unpredictable duration should generally not be placed under a shared data lock:

- Reading/writing files, databases, or networks.
- Calling HTTP, RPC, queue clients, or external services.
- Logging to a synchronous logger or sink that may block on I/O.
- `Thread.sleep`, waiting on `Future.get`, `BlockingQueue.take`, or waiting on a latch when other threads need the same lock to complete.
- Very heavy computation that does not need the protected mutable state.
- Calling plugin code, callbacks, listeners, or overridden methods that you do not control.

If thread A holds a lock while waiting for I/O, threads B and C that need the lock must wait for the entire I/O duration, even though protecting the state only takes microseconds or milliseconds. The problem is even worse if the I/O depends on a worker that is trying to acquire that very same lock: you can create a deadlock.

Recommended pattern:

~~~text
1. Process independent input outside the lock
2. Acquire the lock
3. Check current invariants and perform minimal state transition
4. Create a snapshot/result or an immutable side-effect intent
5. Release the lock
6. Execute I/O/callback/notification based on the result
7. If needed, record success/failure state in a separately designed step
~~~

**Limitation:** If the side effect must occur “atomically” with in-memory state or an external out-of-process system, merely moving the side effect outside the lock **does not create a distributed transaction**. You need to design idempotency keys, state machines, an outbox, retry/compensation, or an appropriate transactional mechanism depending on the system. A JVM lock does not guarantee atomicity between memory and a database/network.

### Example of a Side Effect That Should Not Be Held Under a Lock

Wrong:

~~~java
synchronized (lock) {
    state = State.READY;
    remoteNotifier.send(event); // May block, throw, or call back.
}
~~~

A more easily verifiable alternative if business semantics allow:

~~~java
Event event;
synchronized (lock) {
    state = State.READY;
    event = new Event(state);
}
remoteNotifier.send(event); // Lock released; handle errors separately.
~~~

These two snippets are **structural illustrations**, not standalone programs (the `State`, `Event`, and `remoteNotifier` types must be defined yourself). If sending the event fails, the state is already `READY`; the business logic must define how to retry or record the error. Do not assume the operation has become a transaction just by moving the call outside the lock.

## 8. Avoid Calling Uncontrolled Code While Holding a Lock (*Open Calls*)

A callback can do anything: take a long time, throw an exception, call back into the current object, call another object that holds a lock, or block waiting for another thread. When you invoke a callback inside a lock, you implicitly extend the critical section to uncontrolled code.

Example of what not to do:

~~~java
synchronized (lock) {
    for (Runnable listener : listeners) {
        listener.run(); // Callback may reenter, be slow, or wait.
    }
}
~~~

The solution is to **take a snapshot of the callback list under the lock and invoke them outside the lock** if semantics allow. This snapshot also avoids modifying `listeners` while iterating over the internal list itself.

### Example 4 — Snapshot the Listener List, Then Invoke Outside the Lock

Create `OpenCallDemo.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class OpenCallDemo {
    private static final class EventSource {
        private final Object lock = new Object();
        private final List<Runnable> listeners = new ArrayList<>();

        void subscribe(Runnable listener) {
            Objects.requireNonNull(listener);
            synchronized (lock) {
                listeners.add(listener);
            }
        }

        void fire() {
            List<Runnable> snapshot;
            synchronized (lock) {
                snapshot = List.copyOf(listeners);
            }

            for (Runnable listener : snapshot) {
                listener.run(); // Does not hold the internal lock.
            }
        }
    }

    public static void main(String[] args) {
        EventSource source = new EventSource();
        source.subscribe(() -> System.out.println("listener A"));
        source.subscribe(() -> System.out.println("listener B"));
        source.fire();
    }
}
~~~

Run:

~~~bash
javac OpenCallDemo.java
java OpenCallDemo
~~~

Stdout:

~~~text
listener A
listener B
~~~

`List.copyOf` creates a structural snapshot of the listener list at the time the lock is acquired, and `fire()` invokes the callbacks **after the lock has been released**. If a listener registers another listener during its callback, that change can apply to the next `fire()` call; it does not alter the snapshot of the current invocation.

Note: `listener.run()` can throw an exception, stopping the loop before the remaining listeners; if the requirement is “notify all regardless of one listener failing,” you must have an explicit error-catching, reporting, and retry policy. The snapshot only solves lock ownership, not all semantics of an event system.

Some applications need to snapshot the entire **event payload** along with the listener list; letting listeners read mutable state after unlock can still encounter inconsistent state. Create an immutable event snapshot inside the critical section if that is the data listeners need to observe.

## 9. Not All Blocking Operations Are Equally Dangerous

A blocking call **does not automatically deadlock**. The danger arises when you hold a lock that another thread needs in order to make progress.

Example:

~~~text
Thread A:
    lock(L)
    wait(Future completed by B)  <-- A still holds L

Thread B:
    lock(L)                      <-- B needs L to complete the Future
    complete Future
~~~

A waits for B, B waits for A to release L: this is a wait cycle and can deadlock.

The fix is to change the protocol so that A **does not hold L while waiting for work that requires L**, or move the work to an event/state-machine model that does not create a wait cycle. Simply adding a timeout may reduce hang duration, but it does not fix the invariant or the dependency cycle.

In Java, `Object.wait()` when called properly inside a synchronized block **releases the monitor of the object being waited on** while waiting, and reacquires it before returning. This is an important exception compared to `Thread.sleep()`, which **does not release any held monitors**. Even so, using `wait/notify` still requires a `while` loop checking the predicate and a clear protocol.

Monitor condition example:

~~~java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }
    // Check/work on the condition under the lock.
}
~~~

This snippet only makes sense when another thread modifies `condition` under the same lock and calls `notifyAll`/`notify` appropriately; otherwise, the thread can wait forever. In practice, `BlockingQueue`, `CountDownLatch`, `Condition`, or concurrent utilities are usually preferred when they fit the problem.

## 10. Computing Outside a Lock from a Snapshot: The Stale Data Problem

There are time-consuming computations that **depend on current state**, such as computing a price from inventory, building a new immutable configuration, or scheduling based on the number of available slots. Reading state under a lock, releasing the lock to compute, and then returning to update **is unsafe unless you verify that the state has not changed**.

Risky pattern:

~~~java
Snapshot old;
synchronized (lock) {
    old = snapshotOfState();
}
Proposal proposal = expensiveCalculation(old);
synchronized (lock) {
    apply(proposal); // Wrong if state changed and proposal depends on old.
}
~~~

An *optimistic* approach can use a **version**:

~~~java
// Pseudocode describing the protocol, not a standalone program.
while (true) {
    Snapshot base;
    synchronized (lock) {
        base = snapshotWithVersion();
    }

    Proposal proposal = expensiveCalculation(base); // Outside the lock.

    synchronized (lock) {
        if (currentVersion != base.version()) {
            continue; // State changed; discard stale proposal and retry.
        }
        apply(proposal);
        currentVersion++;
        break;
    }
}
~~~

Conditions for correctness:

1. Every writer affecting the relevant state must update the same **version** according to the protocol.
2. `snapshotWithVersion()` must take a consistent snapshot under the lock.
3. `apply(proposal)` and incrementing the version must share the same critical section.
4. The computation outside the lock must not produce non-rollbackable side effects because it may have to **repeat**.
5. There should be a retry/backoff policy or contention limit; under high load, optimistic retries can cost more than holding a short lock.

This is an alternative design, **not a reason to arbitrarily split every critical section**. For fast computations and low contention, keeping a short computation inside the lock is usually simpler and easier to prove correct.

## 11. When Multiple Locks Are Needed: Fixed Lock Ordering

A critical section may need to protect the state of **multiple objects**. For example, transferring money between two accounts must check the balance, debit the source, and credit the destination in one logically consistent operation. If two threads acquire two locks in opposite orders, they can fall into a deadlock:

~~~text
Thread A: holds lock(account1), waits for lock(account2)
Thread B: holds lock(account2), waits for lock(account1)
~~~

The solution is to define a **total, stable lock order** (for example, a unique, immutable ID) and ensure every code path acquires multiple locks in the same order, independent of parameter order. You must not release the source account's lock before acquiring the destination account's lock if the invariant requires the entire transfer to be atomic.

In this article, the key point is that **the critical section boundary must encompass the invariant across multiple objects**. The article **Lock ordering to prevent deadlock** continues with full transfer code, ranking strategies, handling duplicate locks, and testing for wait cycles.

## 12. `ReentrantLock`: Explicit Acquire/Release and Cleanup

`synchronized` automatically releases the monitor when exiting the block, even if an exception is thrown. `ReentrantLock` requires an explicit `unlock()`, typically in a `finally` block:

~~~java
// Illustration of a method in a class sharing a ReentrantLock.
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

private int value;

void increment() {
    lock.lock();
    try {
        value++;
    } finally {
        lock.unlock();
    }
}
~~~

`ReentrantLock` is useful when you need:

- `tryLock()` to avoid waiting indefinitely or to have a fallback.
- `tryLock(timeout, unit)` to bound the time spent **waiting to acquire the lock**.
- `lockInterruptibly()` to allow canceling the wait for the lock.
- `Condition` to wait on a predicate with a corresponding protocol.
- An optional fairness setting for the lock if the application needs it and accepts the tradeoff; lock fairness does not imply that the OS scheduler is always fair.

**Mistakes to avoid:**

- Calling `lock()` and then returning or throwing before entering `try/finally`.
- Calling `unlock()` from a thread that does not own the lock.
- Acquiring multiple `ReentrantLock` instances in an inconsistent order.
- Assuming `tryLock() == false` means the business state is invalid; it only means the thread did not acquire the lock.
- Holding the lock while waiting for I/O or another task that depends on the lock.

If you only need a simple critical section, `synchronized` is often easier to verify because its lexical lock structure is clear and release is performed automatically by the JVM.

## 13. Choose Atomic Primitives Instead of Locks When the Scope Fits

For **an independent counter**, `AtomicInteger.incrementAndGet()` expresses an atomic read-modify-write without requiring a monitor lock that you manage:

~~~java
private final java.util.concurrent.atomic.AtomicInteger count =
        new java.util.concurrent.atomic.AtomicInteger();

void increment() {
    count.incrementAndGet();
}
~~~

However, you must not split it into `count.get()` and `count.set(old + 1)` and assume it is atomic. With multiple fields sharing an invariant, two separate `AtomicInteger` instances do not provide a joint transaction either.

`ConcurrentHashMap.compute/merge` can perform atomic per-key updates; however, a sequence of `map.get(k)` followed by `map.put(k, value)` is still a non-atomic check-then-act at the combined operation level. `LongAdder` is good for certain high-writer statistics workloads, but `sum()` during concurrent updates is not an atomic snapshot.

**Define the scope** before choosing a primitive. “No `synchronized`” does not automatically mean more optimal or more correct. A clean lock that properly encloses a multi-field invariant can be simpler and safer than combining multiple atomic variables without a protocol.

## 14. Optimizing Lock Hold Time: Do Not Trade Correctness for Throughput

There are two distinct costs:

- **Execution time inside the lock**: computation, allocation, condition checks, memory/I/O operations.
- **Wait time to acquire the lock** (*contention / blocked time*): depends on contention frequency, number of threads, scheduling, critical section length, and lock design.

To improve:

1. **Remove potentially blocking I/O/callbacks** from the lock when semantics allow.
2. **Precompute independent data** such as parsing, validating immutable input, and creating immutable DTOs.
3. **Take an immutable snapshot inside the lock**, and process/report outside.
4. **Reduce shared mutable state**: thread confinement, message passing, immutable values, queues.
5. **Reduce lock frequency** when updates can be batched under the same lock while still maintaining acceptable latency.
6. **Split locks by independent data** when there are no cross-invariants; avoid arbitrary lock striping if multiple fields depend on each other.
7. **Measure before and after** with a representative workload: throughput, p95/p99 latency, block/wait time, queue length, and hot locks.

A critical section that is small in line count but calls a slow algorithm is still a long lock region. A “very short” critical section executed millions of times can also cause high contention. Only measurement reveals the real bottleneck.

### Note on Granularity When Splitting Locks

Suppose accounts A and B never interact; one lock per account can increase concurrency. But when there is a transfer operation, the invariant across both A and B requires synchronization via a **multi-lock** protocol or a shared lock. Splitting locks without analyzing data dependencies makes the code harder to verify and introduces deadlock risk.

Locking too broadly slows down unrelated work; locking too narrowly breaks atomicity. **The right scope** is the minimal scope that encompasses the invariant and the conditions that govern its changes.

## 15. Verifying Correctness: Review by Invariants and Interleavings

### A. Write a “Who Holds the Lock When” Table

Example for `reserveOne()`:

| State | Thread A | Thread B |
| --- | --- | --- |
| `available = 1` | Acquires lock and reads 1 | Waits for lock |
| Inside critical section | Writes `available = 0`, returns true | Still waiting |
| After unlock | Completes reserve | Acquires lock, reads 0, returns false |

This table shows that B cannot interleave between A's check and write, because they use one lock and both access state through `reserveOne()`. You can write a similar table for every important invariant during review.

### B. Look for Paths That Bypass the Lock

Questions to check during code review:

- Are shared fields `private`? Can callers retain a reference to an internal collection and mutate it directly?
- Does a constructor/initializer leak `this` before the state is ready?
- Do all readers **and** writers use the same lock or visibility protocol?
- Is there a “fast path” reading state without a lock even though writers use a lock?
- Is any copy/snapshot created **after** releasing the lock, potentially mixing versions?
- Can a method that invokes a callback while holding a lock call back into another object and form a wait cycle?
- Are multiple locks ever acquired in opposite orders?
- Is there any blocking operation that can only complete via a thread currently waiting for that same lock?

### C. Test Under Controlled Contention

`CountDownLatch` or `CyclicBarrier` can help coordinate two threads starting together to verify invariants, instead of relying on `Thread.sleep`. Tests should:

- Wait for all workers using `join()`/`Future.get()`, rather than checking results early.
- Verify an **invariant outcome**, such as approved count not exceeding stock, total funds conserved, or version matching the number of updates.
- Repeat with varying worker counts/loads when needed; however, a passing stress test is not a formal proof.
- Use timeouts to prevent tests from hanging forever if a deadlock occurs, along with thread dumps/stack traces.
- Measure correctness separately from performance so you do not accept a race condition just because one run was faster.

### D. Distinguish Deadlock, Starvation, and Contention

| Phenomenon | Symptoms | How to Reason About It |
| --- | --- | --- |
| **Contention** | Many threads spend time waiting on the same lock | Reduce independent work inside the lock, reduce shared state, measure blocked time |
| **Deadlock** | Threads form a cycle waiting on locks/resources and make no progress | Analyze lock order, waiting on callbacks/`Future` under a lock, take thread dumps |
| **Starvation** | A task may wait a very long time because it never gets a chance to be served | Inspect queues, scheduling, fairness policy, and load |
| **Race condition** | Incorrect results depending on operation interleaving | Look for unprotected compound actions, invariants missing HB/atomicity |

Simply “putting a big lock around everything” may make races disappear, but it creates contention or deadlocks. The long-term solution is designing clear lock ownership and boundaries.

## 16. Common Anti-Patterns and Fixes

| Anti-Pattern | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Locking `get` and `set` separately in a compound action | Another thread interleaves in between | Create an atomic API enclosing check/modify/write |
| Reading a field unguarded outside the lock because it is “read-only” | Missing visibility or consistent snapshot | Read under the same lock; use immutable/volatile snapshot if appropriate |
| Taking a snapshot of two fields using two separate locks | Can mix versions | Capture the pair of fields under the same critical section |
| Calling HTTP/DB/file under a data monitor | Holds the lock across unpredictable latency | Design state transition + side effect after unlock |
| Invoking listeners inside `synchronized` | Callback may block, reenter, or cause a lock cycle | Copy listener/event snapshot, invoke outside the lock |
| Computing a result from an old snapshot and committing without checking | Lost update or invariant violation | Lock the entire decision or use version/CAS retry |
| Acquiring A then B in one thread, B then A in another | Deadlock | Apply consistent lock ordering |
| Using `Thread.sleep` to create ordering | No synchronization contract | Use latch, condition, queue, or future |
| Releasing a lock without `finally` when using `ReentrantLock` | Easy to leak the lock after an exception | `try/finally` |
| Splitting locks prematurely to optimize | Cross-invariants are easily missed | Verify invariants first before considering splitting locks |
| Holding a lock across `Future.get()` that depends on a worker also needing the lock | Wait cycle | Change the protocol or wait outside the lock |
| Testing on only one machine and concluding it is safe | Rare races may not reproduce | Reason using JMM, invariants, and contention testing |

## 17. Self-Check Questions

**Question 1.** Two threads both execute `if (stock > 0) stock--`. If `if` and `stock--` are in **two** separate `synchronized` blocks, is that sufficient?  
**Answer:** No. Another thread can change `stock` between the check and the update. They must be kept in the same critical section or use an atomic operation that expresses the full condition.

**Question 2.** Does parsing a positive number string from immutable input depend on the current balance?  
**Answer:** No. Parsing/format validation can be done outside the lock. However, checking whether the balance is sufficient and updating the balance must be protected together.

**Question 3.** A writer modifies `total` and `version` under two different locks, and a reader reads each field under two different locks. Is the snapshot guaranteed to be consistent?  
**Answer:** No. A two-field invariant requires a unified synchronization protocol to read/write as one logical unit.

**Question 4.** Can calling a slow listener under `synchronized` hurt correctness even if the listener only prints logs?  
**Answer:** It can make other threads wait a long time; if the listener calls back or waits on a thread that needs the same lock, it can create a wait cycle. You should take a snapshot and invoke it outside the lock when semantics allow.

**Question 5.** Can you snapshot state at time t1, compute outside the lock, and write at t2 without comparing versions?  
**Answer:** Only if the computation does not depend on mutable state or another protocol guarantees safety. If it depends on the t1 snapshot, you must revalidate/CAS or compute inside the lock.

**Question 6.** Two threads transfer funds A→B and B→A, each locking the source first and then the destination. What is the risk?  
**Answer:** Deadlock due to opposite lock ordering. A global lock order or another design with clear invariants is needed.

**Question 7.** Can `volatile long balance` replace a critical section that checks for sufficient funds and deducts the amount?  
**Answer:** No. `volatile` provides visibility/ordering for individual accesses; it does not make check-then-act atomic.

**Question 8.** Is the best critical section always the one with the fewest lines of code?  
**Answer:** No. Covering the right invariant scope is the primary criterion; only after that do you remove independent work or operations that prolong lock hold time.

## Java SE References

- [Java Language Specification `17 — Threads and Locks (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): monitors, synchronization, happens-before, and data races.
- [`Object` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): `wait()`, `notify()`, `notifyAll()`, and monitors.
- [`ReentrantLock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock/unlock, tryLock, fairness, and interruption.
- [`Lock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): synchronization contract.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordinating contention tests.
- [`AtomicInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic single-variable updates.
- [`ConcurrentHashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): atomic per-key updates.

**Key takeaway:** A good critical section must **encompass the decision based on shared state**, use **a consistent lock/protocol**, and avoid holding the lock across independent work or work with uncontrolled duration. Choose boundaries from invariants, not from line counts.