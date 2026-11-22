# Fixing Race Conditions in Java: Ownership, Locking, Atomic, and Immutable State

## Lesson Objectives

A **race condition** occurs when the correctness of a result depends on the interleaving order of concurrent operations, while the program lacks a sufficiently strong coordination protocol. With shared state, the symptoms are typically **lost updates**, checking a condition and then acting on data that has already changed, or observing an inconsistent combination of fields. This lesson presents four remediation strategies at the **Java SE / Java Memory Model** level, without using Spring-specific features:

1. **Ownership:** a single owner has the right to update mutable state; other parties send requests.
2. **Locking:** threads access state through the same lock to protect a business invariant.
3. **Atomic:** use atomic operations such as `incrementAndGet`, `compareAndSet`, or `getAndUpdate`.
4. **Immutable state:** do not mutate a published object; replace it with a new snapshot through a safe publish/update mechanism.

You will learn how to identify the scope of state that needs protection, understand atomicity/visibility/ordering, choose a solution based on the invariant, and run **Java 17+** examples yourself with verifiable results.

## 1. Identify the Race and the Invariant Before Choosing a Solution

Consider a simple counter:

~~~java
class Counter {
    int count;

    void increment() {
        count++;
    }
}
~~~

Logically, `count++` consists of **read → add one → write**. Two threads can interleave:

~~~text
Initial count = 0

Thread A              Thread B
--------              --------
read 0
                      read 0
compute 1             compute 1
write 1
                      write 1

increment was called 2 times, but the final count can be 1.
~~~

This is a **lost update**. If accesses to a normal variable lack a happens-before relationship and at least one access is a write, there can also be a **data race** under the Java Memory Model. The two concepts are related but distinct:

- *Data race*: conflicting memory accesses between threads that are not ordered by a required happens-before relationship.
- *Race condition*: correctness depends on timing/ordering; it can exist **even when using `volatile` or when individual reads/writes are atomic**, because the entire sequence of business operations is still not atomic.

The problem must be described in terms of an **invariant**. For example: the number of successful increments must equal the counter value; when selling items, `available >= 0`; and if there are initially 500 items, then `available + sold == 500`. For an account, the operation "if sufficient funds, then deduct" must be treated as **one logical unit**. When an invariant spans two fields, synchronizing each field individually does not automatically protect their combination.

### Java 17 Example: `volatile` Still Loses Updates

Create the file **`LostUpdateDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class LostUpdateDemo {
    private static volatile int count = 0;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increase = () -> {
            int observed = count;
            bothRead.countDown();

            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            count = observed + 1;
        };

        Thread a = new Thread(increase);
        Thread b = new Thread(increase);
        a.start();
        b.start();

        bothRead.await();
        allowWrite.countDown();
        a.join();
        b.join();

        System.out.println("expected=2 actual=" + count);
    }
}
~~~

Compile and run:

~~~bash
javac LostUpdateDemo.java
java LostUpdateDemo
~~~

Stdout when neither thread is interrupted:

~~~text
expected=2 actual=1
~~~

The two latches deliberately ensure that each thread **has already read the value 0** before either thread is allowed to write. `volatile` gives individual reads and writes clear visibility/ordering semantics, but **it does not turn the three operations read–compute–write into an atomic operation**. This is a deterministic experiment rather than relying on scheduler luck.

## 2. Three Aspects That Must Be Addressed: Visibility, Atomicity, Ordering

| Property | Question | How to Understand It |
| --- | --- | --- |
| **Visibility** | Will other threads see the new write? | Shared values must be published/read according to a valid memory protocol. |
| **Atomicity** | Can a business update be interleaved in the middle? | Check-then-act must be protected together. |
| **Ordering** | Which operations are guaranteed to appear before others? | Rely on happens-before rather than guessing the scheduler. |

Some **happens-before** relationships in Java:
- An unlock on a monitor happens-before every subsequent lock on **the same monitor**.
- A write to a `volatile` variable happens-before every subsequent read of that same variable in the synchronization order.
- Actions before `Thread.start()` happen-before actions in the started thread.
- Actions in a thread happen-before another thread successfully returns from `join()` on that thread.
- `ExecutorService`, `Future`, and concurrent collection APIs have documented memory consistency guarantees; for example, preparing data before `submit` happens-before the task's execution, and the task's actions happen-before using the result after `Future.get()`.

Visibility alone **does not guarantee atomicity**: `volatile int count` still cannot fix `count++`. At the same time, a properly performed single CAS operation can solve both visibility and atomic update of **one state location**, but it does not automatically create a transaction across two separate objects.

## 3. Strategy 1 — Ownership / Confinement

### 3.1. A Single Owner Responsible for Updates

Instead of letting multiple threads directly mutate a mutable object, grant write access to **a single owner**. Other parties send commands/messages; the owner processes them one by one:

~~~text
Producer A --- command ---\
Producer B --- command ----> Queue --> Owner --> mutable state
Producer C --- command ---/

Only the owner modifies state. Producers hold no direct write path.
~~~

If state is created and used exclusively within a single thread, that is **thread confinement**. An `ExecutorService` with one active worker at a time can serve as a sequential command processor. Note that `newSingleThreadExecutor()` guarantees **at most one task runs at a time**, though if the worker dies, the executor can replace it with a new Java thread. The design relies on **sequentiality**, not on a permanently fixed thread ID.

### 3.2. Runnable Example: Single-Owner Counter

Create the file **`OwnerCounterDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class OwnerCounterDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService owner = Executors.newSingleThreadExecutor();
        final int[] counter = {0};

        try {
            List<Future<?>> writes = new ArrayList<>();
            for (int i = 0; i < 1_000; i++) {
                writes.add(owner.submit(() -> counter[0]++));
            }

            // Reads also go through the owner; main does not read the array directly.
            Future<Integer> result = owner.submit(() -> counter[0]);

            for (Future<?> write : writes) {
                write.get();
            }

            System.out.println("count=" + result.get());
        } finally {
            owner.shutdown();
            if (!owner.awaitTermination(1, TimeUnit.MINUTES)) {
                owner.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac OwnerCounterDemo.java
java OwnerCounterDemo
~~~

Stdout:

~~~text
count=1000
~~~

`counter[0]++` does not become inherently atomic. It is correct here because **there are never two concurrent updaters** and every task executes sequentially in the executor's submission order. The read occurs in a task submitted after all update tasks. `Future.get()` waits for completion and surfaces task failures, avoiding a case where a test reports success when a task throws an exception.

For ownership to **truly** eliminate races, the following must hold:
- No method outside the owner and no leaked mutable reference allows another party to modify the state.
- All updates and any reads requiring a consistent snapshot go through the owner or through a safely published immutable snapshot.
- Transferring ownership of a buffer must follow a clear protocol: the sender **no longer modifies the buffer** after handing it off.
- The command queue must manage capacity/backpressure; a slow owner can cause the queue to grow unboundedly if producers keep submitting.
- Do not block the owner by waiting on `Future.get()` for another command that only **that same owner** can execute: that is a self-deadlock pattern.

**Good fit:** per-session state, actor-like components, event aggregators, per-key processing, multi-field logic that can be serialized.

**Limitations:** the owner can become a bottleneck; a very slow I/O command keeps subsequent commands waiting. If state is partitioned across multiple owners/partitions, invariants spanning multiple partitions will require an additional coordination protocol.

### 3.3. ThreadLocal Does Not Automatically Create Per-Task Ownership

`ThreadLocal` gives each Java thread its own value, but a thread pool can reuse workers across many tasks. If you store request data in a `ThreadLocal` and forget to call `remove()` in `finally`, a subsequent task may see stale data. Moreover, a unit of work can hop across multiple threads. Only use `ThreadLocal` for state that is genuinely bound to a thread, and do not equate it with business ownership.

## 4. Strategy 2 — Locking

### 4.1. Protect the Entire Invariant with the Same Monitor

When multiple threads must directly read/write state, you can protect the critical section with `synchronized`:

~~~java
private final Object lock = new Object();
private int count;

void increment() {
    synchronized (lock) {
        count++;
    }
}

int currentCount() {
    synchronized (lock) {
        return count;
    }
}
~~~

Mutual exclusion ensures that only one thread is inside the critical section at a time on this monitor. Unlocking and then locking the same monitor also establishes a happens-before relationship so that reads observe the right data according to the memory rules.

**Lock all relevant read paths as well.** If writers use `synchronized` while a reader reads a mutable field directly outside the lock, the reader can lack visibility or observe state mid-update. A getter with a different lock than the setter does not help either.

### 4.2. Check-Then-Act Must Share the Same Lock Scope

Wrong:

~~~java
if (account.getBalance() >= amount) {
    account.setBalance(account.getBalance() - amount);
}
~~~

Even if `getBalance()` and `setBalance()` are individually synchronized, another thread can change the balance after the check. The right approach is a single `withdrawIfEnough(amount)` operation that checks and deducts under **the same lock**.

### 4.3. Java 17 Example: Two-Field Invariant

Create the file **`LockedInventoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LockedInventoryDemo {
    private static final class Inventory {
        private int available = 500;
        private int sold;

        synchronized boolean sellOne() {
            if (available == 0) {
                return false;
            }
            available--;
            sold++;
            return true;
        }

        synchronized Snapshot snapshot() {
            return new Snapshot(available, sold);
        }
    }

    private record Snapshot(int available, int sold) {}

    public static void main(String[] args) throws Exception {
        Inventory inventory = new Inventory();
        ExecutorService pool = Executors.newFixedThreadPool(10);

        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int worker = 0; worker < 10; worker++) {
                futures.add(pool.submit(() -> {
                    int successes = 0;
                    for (int i = 0; i < 100; i++) {
                        if (inventory.sellOne()) {
                            successes++;
                        }
                    }
                    return successes;
                }));
            }

            int successes = 0;
            for (Future<Integer> future : futures) {
                successes += future.get();
            }

            Snapshot s = inventory.snapshot();
            System.out.printf(
                    "available=%d sold=%d successes=%d invariant=%b%n",
                    s.available(), s.sold(), successes,
                    s.available() >= 0 && s.available() + s.sold() == 500);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac LockedInventoryDemo.java
java LockedInventoryDemo
~~~

Stdout when all 10 tasks complete without error:

~~~text
available=0 sold=500 successes=500 invariant=true
~~~

**Why is this correct?** Each call to `sellOne()` checks and updates both `available` and `sold` inside **one critical section**. After 500 successful sales, inventory reaches 0; the remaining 500 attempts return `false`. `snapshot()` also acquires the same monitor, so readers observe a simultaneous version of both fields. Putting `synchronized` separately on each read or update of a single field would not be equivalent.

### 4.4. `ReentrantLock` and Liveness Issues

`ReentrantLock` provides timed lock acquisition, interruptible locking, and `Condition` objects for waiting on predicates; the typical form is:

~~~java
lock.lock();
try {
    // Check and update the full invariant.
} finally {
    lock.unlock();
}
~~~

This is an illustrative snippet inside a method that has an initialized `lock` of type `ReentrantLock`. Never let an exception cause `unlock()` to be skipped. When you need to bound the wait time for a lock, use `tryLock(timeout, unit)` and **handle the case where the lock is not acquired**. `ReentrantLock` is not automatically faster than `synchronized`: measure contention and choose based on the semantics you need.

Risks of locking:
- **Deadlock:** Thread A holds lock X and waits for Y; Thread B holds lock Y and waits for X. Enforce a **global lock acquisition order** or use a single shared lock for related invariants.
- **Contention:** overly long critical sections force many threads to wait; p99 latency can spike.
- **Holding a lock during slow I/O:** other threads needing the same lock get stuck even while the CPU is idle.
- **Reading outside the lock:** a party that bypasses the same protocol breaks the correctness argument.
- **Callbacks inside a lock:** external methods can call back into the object or wait on unexpected resources; shrink the lock scope when possible while still keeping the entire invariant atomic.

In particular, `Thread.sleep()` inside a `synchronized` block **does not release the monitor**; to wait for a condition, use `Object.wait()`/`Condition.await()` properly according to their contract, re-checking the predicate in a `while` loop after waking up.

## 5. Strategy 3 — Atomic Operations

Classes in `java.util.concurrent.atomic` such as `AtomicInteger`, `AtomicLong`, `AtomicBoolean`, and `AtomicReference` support atomic operations on **a single state location**. For example:

~~~java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();

counter.incrementAndGet();      // A single atomic increment.
int snapshot = counter.get();   // A single read with atomic semantics.
~~~

Not equivalent:

~~~java
counter.set(counter.get() + 1); // Two separate operations, still has lost update.
~~~

An Atomic object does not automatically turn **a sequence of multiple method calls** into a transaction.

### 5.1. Conditional Atomic Update Example

Create the file **`AtomicInventoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicInventoryDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger available = new AtomicInteger(500);
        ExecutorService pool = Executors.newFixedThreadPool(10);

        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int worker = 0; worker < 10; worker++) {
                futures.add(pool.submit(() -> {
                    int successes = 0;
                    for (int i = 0; i < 100; i++) {
                        int previous = available.getAndUpdate(
                                current -> current > 0 ? current - 1 : current);
                        if (previous > 0) {
                            successes++;
                        }
                    }
                    return successes;
                }));
            }

            int sold = 0;
            for (Future<Integer> future : futures) {
                sold += future.get();
            }

            System.out.printf(
                    "available=%d sold=%d invariant=%b%n",
                    available.get(), sold, available.get() + sold == 500);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac AtomicInventoryDemo.java
java AtomicInventoryDemo
~~~

Stdout:

~~~text
available=0 sold=500 invariant=true
~~~

`getAndUpdate` returns the **previous value before the update**; a sale succeeds only when that value is greater than 0. An update never transitions from 0 to -1. The update lambda must have **no side effects**: the library may re-invoke the function when compare-and-set fails due to contention. If the lambda sends an invoice, updates a database, or increments another counter, those actions may occur more times than the number of accepted updates.

In this example, `sold` is computed **after all `Future.get()` calls complete**. Thus the final result is correct, but while the tasks are still running, `available` and a separate `sold` counter **do not necessarily form an atomic snapshot**.

### 5.2. Compare-and-Set (CAS)

CAS checks "does the current state still equal the value I just read?" and atomically updates it if true:

~~~text
old = read state
next = compute new state from old
CAS(old, next)
    success -> the operation takes effect
    failure -> another thread changed state, re-read/recompute
~~~

Example standalone method that can be placed in a class:

~~~java
static boolean takeOne(
        java.util.concurrent.atomic.AtomicInteger remaining) {
    while (true) {
        int current = remaining.get();
        if (current <= 0) {
            return false;
        }
        if (remaining.compareAndSet(current, current - 1)) {
            return true;
        }
    }
}
~~~

CAS guarantees the value is decremented once if it is still positive at the moment of success. When many threads contend, it may have to retry multiple times; **lock-free does not mean wait-free or zero CPU cost**.

### 5.3. Two Separate Atomics Do Not Protect an Invariant Across Two Fields

Wrong when a consistent snapshot is required:

~~~java
AtomicInteger available = new AtomicInteger(500);
AtomicInteger sold = new AtomicInteger(0);

available.decrementAndGet(); // Individually atomic.
sold.incrementAndGet();      // Individually atomic.
~~~

Between the two statements, a reader can observe `available + sold == 499`. If the requirement is "every observer must always see the invariant hold," the right choices are a **lock** covering both updates and reads, a single **owner** managing all fields, or combining the fields into an **immutable snapshot** inside an `AtomicReference`.

`LongAdder` is useful for high-contention metrics counters, but `sum()` during concurrent updates **is not an atomic snapshot**; it is not directly suitable for balances or invariants that require exact observation. `ConcurrentHashMap.compute` supports per-key atomic updates; it does not automatically guarantee transactions across multiple keys.

## 6. Strategy 4 — Immutable State and Atomic Publication

### 6.1. What Does "Immutable" Mean?

A truly immutable object has no observable state that changes after construction. Java 17 supports `record` to express value objects:

~~~java
record Inventory(int available, int sold) {}
~~~

With two `int` fields, each instance is an unchangeable snapshot. Reading both fields from **the same instance** lets you see a consistent version without locking that instance itself.

However:
- A record creates final fields, **not automatic deep immutability**. `record Data(int[] values) {}` still holds an array whose elements can be mutated.
- `final List<Person>` does not make each mutable `Person` inside it immutable.
- An immutable object by itself does not prevent **two writers from publishing two competing new versions**, causing lost updates.
- You still need **safe publication** for the reference (for example `volatile`, `AtomicReference`, `synchronized`, or a queue/Future with memory consistency), and if read-modify-write by multiple writers is needed, use CAS/lock/owner.

### 6.2. Java 17 Example: `AtomicReference` Updating a Two-Field Snapshot

Create the file **`ImmutableSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ImmutableSnapshotDemo {
    private record Inventory(int available, int sold) {}

    public static void main(String[] args) throws Exception {
        AtomicReference<Inventory> state =
                new AtomicReference<>(new Inventory(3, 0));
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                futures.add(pool.submit(() ->
                        state.updateAndGet(old ->
                                old.available() > 0
                                        ? new Inventory(
                                                old.available() - 1,
                                                old.sold() + 1)
                                        : old)));
            }

            for (Future<?> future : futures) {
                future.get();
            }

            Inventory snapshot = state.get();
            System.out.printf(
                    "available=%d sold=%d invariant=%b%n",
                    snapshot.available(), snapshot.sold(),
                    snapshot.available() >= 0
                            && snapshot.available() + snapshot.sold() == 3);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac ImmutableSnapshotDemo.java
java ImmutableSnapshotDemo
~~~

Stdout:

~~~text
available=0 sold=3 invariant=true
~~~

A single `updateAndGet` call may retry computing the snapshot, but it publishes only one result under atomic reference semantics. Eight purchase requests contend for three items; the first three in some order are accepted, and the remaining five leave the state unchanged. The `available/sold` pair is always constructed **together** in one instance.

**Snapshot reading rule:**

~~~java
Inventory view = state.get();
int available = view.available();
int sold = view.sold();
~~~

This snippet is inside a scope where the `Inventory` class and the `state` variable are visible. Do not call `state.get()` separately for each field when you need a consistent version:

~~~java
int available = state.get().available();
int sold = state.get().sold(); // May get a newer version!
~~~

When a writer updates between the two `get()` calls, the reader can combine values from two different snapshots, producing a "broken" invariant even though **every individual snapshot** is always valid.

### 6.3. Immutable + `volatile`, When Is It Enough?

Example of a field used only to publish a new configuration after it has been built:

~~~java
private volatile Config current = new Config("v1", 5);

record Config(String name, int limit) {}

void publish(Config next) {
    current = next;
}

Config snapshot() {
    return current;
}
~~~

This is a **class member** snippet, not a standalone runnable file; in Java, when writing a real class, place the record and field in valid positions. `volatile` guarantees visibility/publication of the reference, and each reader obtains an immutable snapshot. If **two writers both read `current`, compute a new version from the old one, and assign it back**, that read-modify-write can still suffer lost updates. Use `AtomicReference.updateAndGet` or a lock in that case.

### 6.4. Defensive Copy

A record containing a mutable list or array is not deeply immutable automatically. If it only contains `String` (immutable), you can make a structural copy:

~~~java
import java.util.List;

public record Names(List<String> values) {
    public Names {
        values = List.copyOf(values);
    }
}
~~~

This is a **standalone record** saved in `Names.java` if you want to compile it; `List.copyOf` creates an unmodifiable list detached from mutations to the input list. It **does not deep-copy** mutable elements inside the list. Nor can you rely on `Collections.unmodifiableList(original)` to detach from the data source, because that wrapper only prevents mutation through the wrapper; if `original` is still modified elsewhere, the view changes.

## 7. Comparing the Options

| Aspect | Ownership | Locking | Atomic | Immutable Snapshot |
| --- | --- | --- | --- | --- |
| Principle | One owner performs updates | Protect critical section | CAS / atomic operations | Replace with new value, never mutate old |
| Best fit | Command queue, actor-like, partitioned state | Multiple fields, check-then-act logic | Counters, flags, single-location state | Read-mostly, config, coupled state bundle |
| Concurrent writers | Go sequentially through owner | Compete for the same lock | Retry CAS when needed | Need atomic reference/lock/owner to swap |
| Consistent readers | Read via owner/snapshot | Read under the same lock | `get()` on atomic value | Single fetch of snapshot reference |
| Risks | Backlog, owner bottleneck | Contention, deadlock, holding lock too long | High retries, update function side effects | Allocation, mutable nested state, bad publish |
| Key question | Is there any path bypassing the owner? | Do all access paths use the same lock? | Does the invariant fit in a single value? | Is the snapshot truly immutable and safely published? |

Strategies can be **combined**: an owner manages mutable state and returns an immutable snapshot; an `AtomicReference` points to an immutable record; a lock protects building and publishing a complex configuration. Choose based on the invariant scope and read/write patterns, not on the slogan "lock-free is always faster."

## 8. From Problem to Design

### Case A — Independent Metrics Counter

If you only need to increment a single variable atomically, `AtomicLong.incrementAndGet()` is simple. If write-heavy contention is very high and approximate snapshot totals are acceptable, `LongAdder` is worth benchmarking. **Never** use two separate `get/set` calls and hope they are atomic.

### Case B — Non-Negative Inventory

Check-then-decrement is **one business operation**. Use a synchronized method, a CAS loop on `AtomicInteger`, or an owner processing messages. If you update `available` and `sold` together and readers must always see the exact total, use a shared lock or an immutable snapshot + `AtomicReference`.

### Case C — Multi-Field Configuration

Create an immutable record holding all related values; update by replacing the whole `volatile` reference when only publishing pre-built snapshots, or use CAS/owner if multiple writers derive the new version from the old one. Readers fetch **the reference once** and use it consistently.

### Case D — Shared Mutable Collection

Do not assume `Collections.synchronizedList` makes every loop atomic. By the wrapper's contract, iteration generally requires synchronizing explicitly on the list itself:

~~~java
synchronized (list) {
    for (String item : list) {
        System.out.println(item);
    }
}
~~~

This is an illustrative snippet where `list` is an already-created synchronized list. For read-mostly workloads, consider `CopyOnWriteArrayList`; for per-key map updates, consider `ConcurrentHashMap.compute`. If an invariant spans **multiple elements/keys**, individual primitives are not enough to make the whole sequence atomic.

### Case E — Transferring State Between Threads

Suppose a producer hands off a buffer through a queue. If the producer keeps modifying the buffer after `put()`, ownership is not truly exclusive even though the queue provides memory consistency. You need a defensive copy, an immutable value, or a clear protocol defining when the producer is allowed to write again.

## 9. Common "Fixes" That Leave the Race Intact

1. **Making a counter `volatile` while keeping `counter++`.** Visibility improves, but read-modify-write is still not atomic.
2. **Locking with `synchronized(new Object())`.** Every call gets a different monitor; other threads are not blocked. Use a single shared, stable lock field.
3. **Synchronizing only getters/setters.** `set(get()+1)` still leaves a gap for another thread to interleave. Wrap the entire business operation in one atomic method.
4. **Writers use a lock, readers do not.** Readers can see inconsistent versions or lack visibility; use the same lock or safely publish an immutable snapshot.
5. **Using a different lock per field for a combined invariant.** Each field is valid individually, but readers can observe part of an old version and part of a new version.
6. **`AtomicInteger` while calling `set(get()+1)`.** Still two separate operations; use `incrementAndGet` or CAS/update.
7. **Two `AtomicInteger`s treated as a transaction.** Intermediate states exist between the two updates; use a single atomic snapshot.
8. **CAS callback with side effects.** CAS can retry and re-invoke the function; the state-computing function must be pure and never trigger payments or send emails.
9. **A record holding a mutable array called immutable.** `final` only freezes the reference, not the elements; use a defensive copy or change the representation.
10. **`volatile` reference with two writers doing read-then-set.** Lost updates can still occur; use CAS/lock/owner.
11. **Using `Thread.sleep` to wait for "the other thread to finish updating."** Sleep does not establish happens-before; use `join`, a latch, a future, or an appropriate synchronization primitive.
12. **`ThreadLocal` holding request data in a pool without cleanup.** Reused workers can leak data to another task; call `remove()` in `finally`.
13. **Putting callbacks or slow network I/O inside a lock.** Keeps other threads waiting long, increasing latency and deadlock risk.
14. **Seeing one stress test pass and concluding there is no race.** Different timing can expose the bug; explain the invariant and synchronization relationships, and combine that with tests to catch regressions.

### A Deadlock Example to Avoid

~~~text
Thread A: holds lock X then waits for lock Y
Thread B: holds lock Y then waits for lock X

=> Neither thread can acquire the missing lock.
~~~

To transfer money between two objects with separate locks, enforce a consistent lock ordering (for example by unique ID with a tie-breaking rule) or use a single shared lock protecting the transaction if the architecture allows. If state spans multiple processes/hosts, Java thread-level primitives **are not sufficient** for distributed atomicity.

## 10. How to Verify a Solution

1. **Write down the invariant as an observable condition**, for example `available >= 0` and `available + sold == initial`.
2. **List every read/write path**: callers, workers, callbacks, getters, map accesses, event handlers, and cleanup. One path bypassing the protocol can break everything.
3. **Identify the atomic unit of work**: an owner command, a critical section, a CAS, or a successful `AtomicReference` swap. If a multi-step operation must be atomic, cover the entire sequence.
4. **Check safe publication**: is the object fully constructed before another thread reads it? Is there a `volatile`/lock/queue/Future or appropriate happens-before relationship?
5. **Design tests that reproduce interleaving**, such as `CountDownLatch` in the first demo instead of sleeping and hoping for luck. Have multiple threads contend and assert the invariant.
6. **Read task results with `Future.get()`** to surface exceptions. Waiting only for executor shutdown without checking Futures can hide task failures.
7. **Check snapshots during updates**, not only the final state. A system can end with the right total while mid-flight readers observe a broken total.
8. **Test cancellation/failure**: are locks released in `finally`? How does the owner handle queue backlog? Are CAS lambdas free of side effects? Does an immutable graph leak mutable data?
9. **Measure performance after correctness is established**: successful throughput, p95/p99 latency, lock contention, queue depth, CAS retries, CPU/GC. Warm up, run multiple iterations, and keep workloads comparable. Benchmarks never replace a correctness argument.

Tools such as thread dumps, Java Flight Recorder (JFR), profilers, and metrics help observe contention and blocked threads. No runtime testing tool guarantees finding every bad interleaving; reasoning from the Java Memory Model and invariants remains the foundation.

## 11. Practice Questions

1. Two threads both run `volatile int x; x++;`. Is there still a race? **Yes**, read-modify-write is not atomic.
2. Why are `synchronized getBalance` and `synchronized setBalance` still insufficient for `if(getBalance()>=n) setBalance(getBalance()-n)`? **The lock is released between calls, so the invariant is not protected as a whole.**
3. Is an owner running on `newSingleThreadExecutor` guaranteed to keep the same Java thread ID for the lifetime of the executor? **No.** The executor guarantees sequential execution, and may replace the worker after an error.
4. Why must the callback in `AtomicReference.updateAndGet` avoid side effects? **It may be re-executed when CAS contends.**
5. Do separate `AtomicInteger available` and `AtomicInteger sold` guarantee `available + sold == 500` is always true when a reader reads concurrently? **No.**
6. With an immutable record in `AtomicReference`, why do we need `Inventory s = state.get()` and then read both fields from `s`? **Two separate `get()` calls can retrieve two different versions.**
7. Is `record Data(int[] numbers)` deeply immutable? **No**, the array is still mutable.
8. If state is modified by a single owner, why must we still bound the command queue? **Producers can submit faster than the owner processes, causing backlog and OOM.**
9. Why does `Thread.sleep(100)` not fix a race? **It establishes neither a happens-before relationship nor mutual exclusion.**
10. What must be done when two locks need to be acquired together to avoid deadlock? **Enforce a consistent lock ordering or change the locking architecture appropriately.**
11. When is `LongAdder` a better fit than `AtomicLong`? **For heavily updated statistical counters with contention where an atomic total snapshot is not required at every moment.**
12. If a fix makes the result correct but p99 latency spikes, what should you measure? **Critical section duration, lock contention, queue depth, CPU, GC, offered load, and successful throughput.**

## Key Takeaways

Start from **shared state and business invariants**. **Ownership** eliminates competing writers; **locking** wraps the business operation when multiple threads need concurrent access; **atomic** solves updates on a single variable or a CAS snapshot; **immutable state** lets readers observe an unchanging version and pairs well with safe publication. Ensure **atomicity, visibility, ordering, and liveness** at the right scope. A misplaced `volatile`, `synchronized`, or `AtomicInteger` can make a program appear safe across a few runs while still hiding a race.

## References

- [Java Language Specification 17, Chapter 17: Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, happens-before, data races.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic updates and CAS.
- [Java SE 17 — AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): updating snapshots.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): task execution and memory consistency.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): per-key atomic updates.
- [Java SE 17 — LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counters under contention.
