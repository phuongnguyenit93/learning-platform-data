# Keeping Invariants Consistent Across Multiple Related Fields in Java Concurrency

An **invariant** (state invariant) is a condition that must always hold whenever state is allowed to be observed or used. In multithreaded programs, invariants often span **multiple fields at the same time**: the total balance across two wallets equals 100, available seats plus reserved seats equals initial capacity, an interval satisfies `start <= end`, or an order with status `PAID` has a corresponding payment ID.

If two fields are updated separately, another thread can observe an **invalid intermediate state**, even if each individual read/write is atomic or the fields are `volatile`. Having the condition hold at the start and end of a method is not enough if another thread is allowed to observe in between. You must define the **boundary of a state transition**, protect all data participating in the invariant, and provide a way to read a consistent snapshot.

This lesson belongs to **Thread Safety in Java Concurrency in general**; it focuses on synchronization in JVM memory, the Java Memory Model, locks, immutable state, and atomic references. Spring-specific integrations are out of scope.

## 1. An Invariant Differs from Per-Field Conditions

Suppose a ticket inventory has two counters:

- `available`: number of unreserved tickets;
- `reserved`: number of reserved tickets.

Initially `available = 100`, `reserved = 0`. The business requirement is:

~~~text
available >= 0
reserved >= 0
available + reserved == 100
~~~

Each successful reservation must move one ticket from `available` to `reserved`. Before and after the transition, the total remains 100:

~~~text
Before: available=100, reserved=0, total=100
After:  available=99,  reserved=1, total=100
~~~

However, the following code **does not perform an atomic state transition**:

~~~java
if (available > 0) {
    available--;
    reserved++;
}
~~~

There are at least three distinct risks:

1. **Check-then-act race:** two threads both see `available > 0` and both decrement; the result can become negative or reservations can exceed capacity.
2. **Intermediate state:** a reading thread can observe after `available--` but before `reserved++`, seeing a total of 99 even though valid values at the start and end are both 100.
3. **Visibility/ordering:** if plain variables are accessed without a happens-before relationship, a reading thread may also observe updates in a way that violates the expected contract.

The fix must cover **the condition, all modified fields, and how those fields are observed**. Wrapping only one increment, adding `volatile` alone, or synchronizing only the writer is not enough.

### 1.1 Invariants and Allowed Observation Points

Inside a critical section, code may temporarily pass through an intermediate state:

~~~java
available--;
reserved++;
~~~

If **all other threads can only read both fields while holding the same lock**, no external thread can observe that intermediate state; the invariant is preserved at the public boundary of the operation. However, if a getter reads `available` or `reserved` **without acquiring the lock**, it can expose the intermediate state.

This leads to the principle:

> An invariant spanning multiple fields must hold at every valid observation point. Every read/write operation that can affect the invariant must follow **the same synchronization protocol**.

This does not mean using a single application-wide mutex. You only need a **shared ownership and synchronization boundary for the same invariant**.

## 2. Deterministic Example: Two Volatile Fields Still Expose Inconsistent State

`volatile` guarantees visibility/ordering effects for accesses to a volatile field. It **does not group** two fields into an atomic transaction.

To deterministically reproduce the exact moment the state skews without relying on scheduler luck, use two `CountDownLatch` instances to pause the writer after the first decrement.

Create the file `VolatilePairInvariantDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class VolatilePairInvariantDemo {
    private static final class Counters {
        volatile int available = 100;
        volatile int reserved = 0;
    }

    public static void main(String[] args) throws InterruptedException {
        Counters counters = new Counters();
        CountDownLatch debited = new CountDownLatch(1);
        CountDownLatch continueWriter = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            counters.available--;
            debited.countDown();

            try {
                continueWriter.await();
                counters.reserved++;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "writer");

        writer.start();
        debited.await();

        System.out.println("During update: "
                + (counters.available + counters.reserved));

        continueWriter.countDown();
        writer.join();

        System.out.println("After update: "
                + (counters.available + counters.reserved));
    }
}
~~~

Compile and run on JDK 17 or later:

~~~bash
javac VolatilePairInvariantDemo.java
java VolatilePairInvariantDemo
~~~

In a normal run without external interruption:

~~~text
During update: 99
After update: 100
~~~

**Why is this example deterministic?** The writer decrements `available` and then calls `debited.countDown()`; `main` waits for `debited.await()` to succeed and then reads both fields, while the writer cannot increment `reserved` yet because it is waiting on `continueWriter`. `main` then opens the gate and joins the writer. The latches merely create a deterministic interleaving for the demo. **The design flaw is that the two updates happen in two steps that a reader can observe in between.**

Here each field is volatile, yet at the observation point between the two steps, the data genuinely has state `available=99, reserved=0`. This is not a "CPU hasn't flushed cache" issue; this is **missing atomicity at the field-group level**. Fixing visibility without fixing the operation boundary still allows the invariant to break.

**Limitation of the demo:** if an external interruption causes the writer to exit early, the final result may differ. This snippet is meant to explain atomicity, not to serve as a production solution. A real operation must define cancellation, failure, and rollback policies so it never leaves partial state behind.

## 3. Identify Which Fields Must Change Together

Before choosing a lock, write down the invariant conditions of the object or subsystem:

| Example | Related Fields | Condition That Must Hold |
| --- | --- | --- |
| Capacity | `available`, `reserved` | Both non-negative; sum equals capacity. |
| Internal accounts | `checking`, `savings` | Internal sum is conserved when transferring between wallets; non-negative. |
| Time interval | `start`, `end` | `start <= end` in every published snapshot. |
| Payment state | `status`, `paymentId` | When `status == PAID`, a payment ID exists. |
| Statistics counters | `success`, `failure`, `processed` | If `processed` is updated in the same logical transaction, `success + failure == processed` at observation points. |
| Configuration | `host`, `port`, `version` | Every read obtains values belonging to **the same version**. |

These examples are **illustrative business models**: in a real system, invariants may differ (for example, a cancellation event changing capacity, or a payment transaction having a valid intermediate `PENDING` state). Define **which states are allowed to exist**, when publishing is permitted, and which intermediate states are forbidden from being observed.

A good workflow:

1. List all fields and objects participating in the invariant.
2. Find **every write site**, including constructors, setters, callbacks, background threads, schedulers, and reset methods.
3. Find **every read site**: getters, reports, logging, serializers, and other algorithms.
4. Define where an operation takes effect atomically (the linearization point if the API requires linearizability).
5. Enforce **one unified protocol** across all related access paths.
6. Verify that errors, exceptions, interruption, and early branches still preserve the invariant.

Do not fix only the first writer method you see while ignoring getters or other read paths.

## 4. Basic Solution: One Lock Protecting the Entire Invariant

`synchronized` is the most direct and easiest-to-prove choice when multiple fields of the same object must be updated together. A private lock belonging to the object protects the **entire** state; callers only use synchronized methods.

Create the file `LockedInvariantDemo.java`:

~~~java
public final class LockedInvariantDemo {
    private static final class ReservationLedger {
        private final Object lock = new Object();
        private int available = 100;
        private int reserved;

        boolean reserveOne() {
            synchronized (lock) {
                if (available == 0) {
                    return false;
                }
                available--;
                reserved++;
                return true;
            }
        }

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(available, reserved);
            }
        }
    }

    private record Snapshot(int available, int reserved) {
        int total() {
            return available + reserved;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ReservationLedger ledger = new ReservationLedger();

        Runnable reserve = () -> {
            for (int i = 0; i < 100; i++) {
                ledger.reserveOne();
            }
        };

        Thread first = new Thread(reserve, "first");
        Thread second = new Thread(reserve, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        Snapshot result = ledger.snapshot();
        System.out.println("Available: " + result.available());
        System.out.println("Reserved: " + result.reserved());
        System.out.println("Total: " + result.total());
    }
}
~~~

Command to run on Java 17+:

~~~bash
javac LockedInvariantDemo.java
java LockedInvariantDemo
~~~

Stdout:

~~~text
Available: 0
Reserved: 100
Total: 100
~~~

### 4.1 Why Does This Preserve the Invariant?

- Each call to `reserveOne()` holds the same monitor `lock` across **check + decrement + increment**. No two `reserveOne` calls can interleave between each other's steps.
- When no tickets remain, the method returns `false` without modifying state. The condition `available >= 0` is preserved.
- A successful reservation transforms state from `(a, r)` to `(a-1, r+1)`. The sum is unchanged: `(a-1)+(r+1)=a+r`.
- `snapshot()` acquires **that same lock**, producing a pair of values read simultaneously at a valid boundary. Readers never see the state after decrementing but before incrementing.
- Two workers each attempt up to 100 reservations; overall, exactly 100 succeed regardless of which thread the scheduler picks first. After `join()`, `main` sees the completed updates.
- `Snapshot` is an immutable `record` with primitive components, so it can be read outside the lock after being returned without seeing the two fields change separately.

### 4.2 Linearization Point and Atomic Reads

For the `reserveOne()` API, the entire state transition is protected by the lock. You can treat the operation as taking effect at a point inside the critical section before releasing the lock. Observations via `snapshot()` always correspond to a state before or after a complete operation.

A **common mistake** is synchronizing the writer without synchronizing the reader:

~~~java
synchronized (lock) {
    available--;
    reserved++;
}

// A getter outside the lock on another thread:
int total = available + reserved; // Lacks snapshot / proper synchronization.
~~~

This is an **illustrative buggy snippet**. Having a synchronized `getAvailable()` getter and a separately synchronized `getReserved()` getter is **still not enough** to assemble a snapshot: between the two calls, a writer can perform a new operation. You need a `snapshot()` method that reads **all related fields under a single lock acquisition**.

## 5. Encapsulation: State Ownership Matters More Than the `synchronized` Keyword

Thread safety breaks if a caller can modify one of the fields without following the same protocol.

Keep state `private`, avoid directly returning mutable objects that participate in the invariant, and expose operations at the business level:

~~~java
final class Range {
    private final Object lock = new Object();
    private int start;
    private int end;

    Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
        this.start = start;
        this.end = end;
    }

    void move(int newStart, int newEnd) {
        if (newStart > newEnd) {
            throw new IllegalArgumentException("start > end");
        }
        synchronized (lock) {
            start = newStart;
            end = newEnd;
        }
    }

    Snapshot snapshot() {
        synchronized (lock) {
            return new Snapshot(start, end);
        }
    }

    record Snapshot(int start, int end) {}
}
~~~

This is an **illustrative class snippet**, without `main`. Even though inside `move` there is a moment where `start` changes before `end`, external code can only observe via `snapshot` under the same lock. The `newStart <= newEnd` check can be placed before the lock because it depends **only on two immutable-by-value parameters**, not on mutable shared state.

Conversely, a condition like "if current `start` equals X, then update `end`" must be checked **inside the same critical section** as the update; checking shared state outside the lock creates a *check-then-act race*.

### 5.1 Return a Snapshot Instead of a Mutable Reference

If an object manages a `List<Order>` or `Map<String, Item>`, a getter returning the mutable collection directly lets callers mutate state without holding the lock. Wrapping only the getter in `synchronized` does not prevent modifications after the reference is returned.

Return an intentional snapshot copy:

~~~java
List<String> snapshot() {
    synchronized (lock) {
        return List.copyOf(items);
    }
}
~~~

This illustrative snippet assumes `items` and `lock` are already declared and `items` contains no nulls (since `List.copyOf` rejects null elements). The returned list prevents callers from modifying the list structure, but **if elements inside are mutable**, this copy is only a *shallow* copy. To publish a deeply immutable snapshot, you need immutable elements or to copy data into appropriate value objects.

Do not let `this` or references to partially constructed state escape from the constructor, because another thread could observe the object before initialization invariants are complete.

## 6. `ReentrantLock` When More Control Is Needed

`java.util.concurrent.locks.ReentrantLock` provides mutual exclusion and memory effects similar to monitors when locked/unlocked properly, while also supporting timed acquisition, interruptible locking, and `Condition` objects.

Example class snippet using `tryLock`, a wait deadline, and `finally`:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

final class TimedLedger {
    private final ReentrantLock lock = new ReentrantLock();
    private int available = 100;
    private int reserved;

    boolean reserveOne() throws InterruptedException {
        if (!lock.tryLock(200, TimeUnit.MILLISECONDS)) {
            return false; // Failed to acquire the lock within the wait timeout.
        }
        try {
            if (available == 0) {
                return false;
            }
            available--;
            reserved++;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
~~~

This is an **illustrative code snippet without `main`**, though it compiles with the corresponding imports. You should distinguish `false` due to lock acquisition timeout from `false` due to exhausted quota if the business contract needs to state the cause clearly.

Mandatory rules:

- Always release the lock in `finally` immediately after acquiring it successfully.
- Every state read path must also use **the same `ReentrantLock`**; an unlocked getter can expose intermediate state.
- `tryLock(timeout)` bounds the time spent **waiting to acquire the lock**, not the execution time of the critical section.
- If `InterruptedException` is thrown before the lock is acquired, do not call `unlock()` when the thread does not own the lock.
- A fair lock `new ReentrantLock(true)` can change serving order under contention, but **does not** guarantee completion deadlines; fairness does not fix a broken invariant.

Do not choose `ReentrantLock` just because you believe it is "more thread-safe than `synchronized`". First design ownership and invariants properly; choose the primitive based on needs for timeouts, interruption, wait conditions, or measured load.

## 7. Immutable State and `AtomicReference`: Updating a Group as One Value

Instead of storing two independent mutable variables, you can group them into an **immutable value object**, and store a single **reference** to the current state. Every update constructs a new snapshot and swaps the reference using CAS.

Create `AtomicInvariantDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public final class AtomicInvariantDemo {
    private record State(int available, int reserved) {
        int total() {
            return available + reserved;
        }
    }

    private final AtomicReference<State> state =
            new AtomicReference<>(new State(100, 0));

    boolean reserveOne() {
        while (true) {
            State current = state.get();
            if (current.available() == 0) {
                return false;
            }

            State next = new State(
                    current.available() - 1,
                    current.reserved() + 1
            );
            if (state.compareAndSet(current, next)) {
                return true;
            }
            // A contender changed state; re-read snapshot and retry CAS.
        }
    }

    State snapshot() {
        return state.get();
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInvariantDemo ledger = new AtomicInvariantDemo();

        Runnable reserve = () -> {
            for (int i = 0; i < 100; i++) {
                ledger.reserveOne();
            }
        };

        Thread first = new Thread(reserve, "first");
        Thread second = new Thread(reserve, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        State result = ledger.snapshot();
        System.out.println("Available: " + result.available());
        System.out.println("Reserved: " + result.reserved());
        System.out.println("Total: " + result.total());
    }
}
~~~

Command to run on Java 17+:

~~~bash
javac AtomicInvariantDemo.java
java AtomicInvariantDemo
~~~

Stdout:

~~~text
Available: 0
Reserved: 100
Total: 100
~~~

### 7.1 Why Does One `AtomicReference` Solve Multiple Fields?

- `State` is an immutable `record` containing **both** counters. A reader calling `state.get()` once holds a reference to **one complete snapshot**.
- The writer builds `next` from a current snapshot, preserving the invariant inside the new snapshot itself.
- `compareAndSet(current, next)` succeeds only if the reference is still `current`. A succeeding CAS is the **linearization point** of the state-changing operation.
- If a contender already changed the state, CAS fails; the writer discards the stale candidate, re-reads, and computes a new state. Thus it never overwrites a valid update from another thread.
- Readers never see `available--` separated from `reserved++`: the fields of the new state are fully constructed **before** the reference is published.
- Assuming values stay within valid bounds and no writer bypasses the protocol, the invariant `available + reserved == 100` holds in every published `State`.

### 7.2 Limitations and Trade-offs of CAS

A CAS loop does not guarantee that a specific thread will succeed in a bounded number of attempts under heavy contention; **starvation** can occur even though the system as a whole makes progress. Never perform I/O, send emails, charge external accounts, or execute non-repeatable side effects inside the function computing `next`: CAS can fail and the logic will re-run.

Each successful update allocates a new `State`, creating allocation and GC pressure. For small, read-heavy state, immutable snapshots can work very well; for extremely high update rates or complex state, benchmark performance against locks.

Do not call `state.get()` twice and combine one field from an old snapshot with one field from a new snapshot:

~~~java
int a = state.get().available();
int b = state.get().reserved(); // May belong to a different version.
~~~

This is an illustrative buggy snippet. The right way is:

~~~java
State oneSnapshot = state.get();
int a = oneSnapshot.available();
int b = oneSnapshot.reserved();
~~~

Both reads from the same `oneSnapshot` preserve consistency for that version. If `State` holds references to mutable collections, `record` does not automatically provide deep immutability; you must ensure the state and its internal object graph are genuinely immutable by contract.

### 7.3 ABA and Versioned Changes

`AtomicReference.compareAndSet` compares the current reference against the expected reference. When mutable objects/references are reused or state transitions A→B→A, complex algorithms can hit the **ABA problem**: a value looks identical to the original even though history changed. The example above allocates a fresh `State` each time and never reuses old instances, so CAS in these operations properly distinguishes updates by identity.

If business logic requires knowing the **version** or detecting any intermediate change, you can store a version in the new state and increment it in the same operation, or use `AtomicStampedReference` when appropriate. Do not add a version just because "there is concurrency"; first determine whether historical tracking is required.

## 8. Why Multiple Independent `AtomicInteger`s Are Not Enough

A common mistake:

~~~java
AtomicInteger available = new AtomicInteger(100);
AtomicInteger reserved = new AtomicInteger();

if (available.get() > 0) {
    available.decrementAndGet();
    reserved.incrementAndGet();
}
~~~

Each `get()`, `decrementAndGet()`, and `incrementAndGet()` call is atomic with respect to **a single variable**. Yet the overall block still suffers from:

- **Check-then-act race:** two threads both see `available > 0` and both decrement.
- **Torn snapshot:** a reader can observe state after `available` is decremented but before `reserved` is incremented.
- **Inconsistency on failure:** if an exception or cancellation occurs between the two steps, the second variable may never be updated.

Even fixing check-then-act with `available.updateAndGet(...)` or a separate CAS loop on `available` still does not place the `reserved` increment into the same transaction. To protect **an invariant spanning both variables**, use a shared critical section or wrap both into an immutable state under `AtomicReference<State>`.

Counters that are **independent by design** are a different case: for example, successful request count and failed request count used for end-of-period metrics, where the system accepts slightly skewed snapshots during updates. When no invariant must hold at every read point, multiple atomic counters can be reasonable. This must be stated explicitly in the observation contract, not assumed by default.

## 9. Choosing `synchronized`, `Lock`, Immutable Snapshot, or Atomic CAS

| Technique | Strengths | Costs / Limitations | Best Fit When |
| --- | --- | --- | --- |
| `synchronized` with private lock | Easy to understand and prove atomic multi-field transitions; clear memory visibility. | Threads may block under contention; must follow lock on all read/write paths. | Small/medium state, complex invariants, clear correctness needed. |
| `ReentrantLock` | Timeouts, interruptible acquisition, `Condition`, measurable contention. | Must unlock reliably in `finally`; adds error/lifecycle branches. | Complex lock acquisition policies or timeouts needed. |
| Immutable snapshot + `volatile` reference | Readers get a consistent snapshot without blocking on read locks. | With multiple writers, simple reference replacement can lose updates. | Single writer publishing complete config/snapshot, many readers. |
| Immutable snapshot + `AtomicReference` CAS | Updates **entire state group** atomically via reference swap; readers read one snapshot. | Retries under contention, allocations, complexity if side effects exist. | Compact, immutable state with optimistic updates. |
| `ReadWriteLock` | Allows multiple concurrent readers and exclusive writer updates per policy. | Contention, potential writer starvation depending on policy, higher overhead than plain locks. | Read-heavy, write-light, read sections large enough to benefit. |
| `StampedLock` | Optimistic read + validate mechanism fits certain workloads. | Harder protocol, non-reentrant; must validate properly, never use inconsistent results before validation. | Benchmarked workload proves benefit and team understands the protocol. |

`volatile` on individual fields does not replace an atomic snapshot. With `StampedLock`, an optimistic read can see an intermediate state while a writer is mutating; only use results after validation succeeds, and never dereference or trigger side effects based on potentially inconsistent data before validation. Do not use optimistic reads to traverse a mutable object graph unless you understand the risks of observing mutating data.

**Default choice:** prefer a private lock and a business-level API. When a profiler proves a specific bottleneck, consider immutable snapshots/`AtomicReference` or specialized primitives suited to the load pattern. A design that is easy to prove correct is usually cheaper than debugging hard-to-reproduce race conditions.

## 10. Invariants Across Multiple Objects: Lock Ordering and Transaction Boundaries

When an invariant spans **two independent objects**, synchronizing inside each object individually does not make an operation across both atomic. For example, transferring money between accounts A and B must:

1. Check that A has sufficient balance.
2. Debit A.
3. Credit B.
4. Let readers observe a consistent state.

If only A's `withdraw` and B's `deposit` are individually `synchronized`, another thread can read the account pair between the two steps, or competing updates can interleave. To be atomic across both, you need a **protocol owning both**.

### 10.1 A Single Ledger Lock

If a single ledger manages both A and B, the simplest solution is one ledger lock:

~~~java
final class TransferLedger {
    private final Object lock = new Object();
    private int accountA = 100;
    private int accountB = 100;

    boolean transferAToB(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        synchronized (lock) {
            if (accountA < amount) {
                return false;
            }
            accountA -= amount;
            accountB += amount;
            return true;
        }
    }

    int total() {
        synchronized (lock) {
            return accountA + accountB;
        }
    }
}
~~~

This is an **illustrative class snippet**, without `main`. If the initial total is 200, every valid transfer keeps the total at 200; readers call `total()` under the same lock. Each transfer takes effect as one operation on the ledger's internal state.

### 10.2 If Multiple Locks Must Be Acquired, Use a Global Order

Suppose thread T1 locks account A then B, while T2 locks B then A: a **deadlock** can occur if each thread holds one lock and waits for the other. A common rule is to assign an **immutable, unique ID** to each account and always acquire locks in ascending ID order, regardless of transfer direction.

~~~java
Account first = from.id < to.id ? from : to;
Account second = from.id < to.id ? to : from;

synchronized (first.lock) {
    synchronized (second.lock) {
        // Check from.balance and perform both updates.
    }
}
~~~

This is an **illustrative snippet**; `Account` has a unique, immutable `id`, `lock`, and `balance`, and this snippet omits handling `from == to`, validation, or runnable code. To be safe, every operation that may acquire two locks together must use **the same order**, and all paths reading a snapshot of both accounts must follow the protocol. If IDs can collide, a consistent tie-breaker is needed; never rely on parameter order.

Avoid locking on public objects that external code could arbitrarily `synchronized` on; private locks prevent unintended interference. Avoid performing I/O or invoking uncontrolled callbacks while holding multiple locks.

### 10.3 One JVM Does Not Replace Cross-System Transactions

`synchronized`, `ReentrantLock`, and `AtomicReference` only coordinate state within **the single JVM/object graph they manage**. If an invariant spans database rows, message brokers, files, multiple processes, or network services, JVM locks **do not** turn the entire operation into a distributed transaction.

Invariants spanning multiple systems require mechanisms at that level: database transactions, optimistic concurrency/versioning, idempotency, compensating action workflows, or eventual consistency designs with clearly defined intermediate states. This is a **scope boundary** of thread-safety techniques, not a reason to pull a specific framework into this lesson.

## 11. Exception Safety: Never Publish Partial State

Locks prevent other threads from interleaving between updates, but **do not automatically roll back** if code inside the critical section throws an exception mid-way.

Dangerous example:

~~~java
synchronized (lock) {
    available--;
    mayThrow();     // If an error occurs here...
    reserved++;     // ...this is never executed.
}
~~~

This illustrative snippet assumes variables and methods are declared. `synchronized` still **releases the monitor** when an exception exits, allowing other threads to read state whose invariant is now broken.

Mitigation approaches:

- **Validate before mutating:** check arguments, arithmetic bounds, and preconditions before updating. Checks depending on state must stay inside the lock or inside the CAS computation based on the snapshot.
- **Prepare then commit:** compute new state in local variables/value objects and verify invariants before publishing. Use a single immutable reference assignment or CAS to commit.
- **Roll back inside the lock when truly necessary:** if a multi-step operation can fail, write verified cleanup/rollback logic; never assume `finally` releasing a lock means rollback happened.
- **Do not place irreversible side effects** (sending emails, emitting notifications, executing remote payments) between multiple state-update steps in a CAS loop or critical section and assume safe retries.
- **Define cancellation:** a thread interrupted mid-operation must exit at a safe point, or complete/roll back according to protocol. Never swallow `InterruptedException` and leave state half-updated.

Simple prepare-then-commit example:

~~~java
synchronized (lock) {
    if (available <= 0) {
        return false;
    }
    int nextAvailable = available - 1;
    int nextReserved = Math.addExact(reserved, 1);
    // All computation/validation completes before mutating state.
    available = nextAvailable;
    reserved = nextReserved;
    return true;
}
~~~

This is an illustrative snippet inside a method returning `boolean`. `Math.addExact` throws `ArithmeticException` on overflow; because the exception occurs **before** the assignments, the old state is preserved. Once commit begins, ensure only non-throwing primitive assignments remain and no external callbacks are invoked in between. Because the lock protects readers, the internal half-updated state between the two assignments is never exposed externally.

When complex calculations or mutable objects are involved, using **one immutable candidate state** committed via reference swap is usually easier to audit for exception safety.

## 12. Integer Overflow and Valid Invariant Domains

When `a + b == total` uses Java integers, you must consider **overflow**. With `int`, adding two numbers near `Integer.MAX_VALUE` can wrap around to a negative value. An invariant checked with plain `a + b` can sometimes evaluate incorrectly due to overflow.

Solutions:

- Define valid domains and data bounds explicitly.
- Use `Math.addExact` / `Math.subtractExact` when overflow should throw an exception.
- Choose `long` if the data domain is larger; `long` also has limits and can overflow.
- In monetary calculations, use the smallest currency unit with range-checked `long`, or an appropriate numeric type when decimal precision is needed; never use `double` to represent exact money.
- Validate positive amounts, limits, matching currency/units, and all business conditions **before committing**.

Note that thread safety and arithmetic correctness are two orthogonal dimensions. A perfectly synchronized operation that allows overflow can still break the invariant.

## 13. Avoiding Deadlock, Starvation, and Lock Contention

Preserving invariants may require locks, but a flawed locking protocol can prevent the application from making progress:

- **Lock ordering:** acquire multiple locks in a global order to reduce wait-cycle risk.
- **Lock scope:** hold locks only while reading/writing shared state that truly needs atomicity; never hold them across unbounded I/O, user callbacks, or long `Future.get()` waits.
- **No blocking self-dependency:** never call `Thread.join()` while holding a lock that the worker needs to finish.
- **Fairness:** fair locks can change contender serving order, but do not automatically guarantee tail latency or task deadlines.
- **Contention:** a single lock can become a bottleneck when many threads update concurrently. Before splitting a lock, check whether the invariant still fits cleanly within each partition.
- **Deadlock detection:** thread dumps and `ThreadMXBean` can help detect deadlocks; finding none does not mean the program is free of starvation, livelock, or I/O blocking.

In particular, **splitting one lock into two separate locks for two fields** to increase throughput can destroy the very invariant being protected. When an invariant requires updating multiple fields together, sharding requires redesigning state boundaries rather than merely renaming locks.

## 14. Consistent Snapshot Reads and Linearizability

In a concurrent API, a snapshot should represent **a state that could exist at a valid point in time**. If the API requires *linearizability*, each completed operation must appear to take effect at some point between its invocation and its return, while preserving the real-time order of non-overlapping calls.

- With `synchronized`, updates and snapshots acquire the same lock, so operations and snapshots can be ordered in lock acquisition order.
- With `AtomicReference<State>`, a successful CAS is the linearization point of an update, while a single `get()` is the observation point of a snapshot.
- With two separate getters, even if each getter is synchronized, the pair assembled by the caller may come from **two different points in time**.

Buggy example:

~~~java
int available = ledger.getAvailable();  // One lock/unlock.
int reserved = ledger.getReserved();    // Another lock/unlock.
int total = available + reserved;       // May mix two versions.
~~~

Two getters each protecting a single variable are not enough for a **group snapshot**. The API should return a single `record Snapshot(int available, int reserved)` under one lock acquisition, or an immutable state fetched from one atomic reference.

### 14.1 Snapshot Consistency vs. Eventually Consistent Metrics

Not every pair of counters needs a linearizable snapshot. For telemetry/metrics, reading two independent counters slightly out of sync during updates may be **acceptable by contract**. In balance accounting or quota allocation, that is usually unacceptable.

Before adding synchronization overhead, ask: "Does any user or operation rely on this sum to make a decision that must be accurate right now?" If yes, guarantee an atomic snapshot. If it is only an approximate dashboard, document the allowed consistency model clearly.

## 15. Meaningful Testing of Multi-Field Invariants

Concurrency tests are valuable when they verify **business conditions** under deliberate interleavings.

### 15.1 Post-Contention Verification

With a ledger of 100 tickets and 2 threads each calling `reserveOne()` 100 times, after `join()` you should assert:

~~~text
available >= 0
reserved >= 0
available + reserved == 100
reserved == 100
~~~

Both `LockedInvariantDemo` and `AtomicInvariantDemo` produce this deterministic result regardless of scheduling order. If you only assert "no exceptions thrown", tests will miss oversubscription and lost updates.

### 15.2 Verification While Writers Are Active

A common mistake is checking only the final state. If a writer executes `available--` then `reserved++` and a reader takes a snapshot in between, the final result is still 100, yet the invariant of **every observable snapshot** was violated.

Use a `CountDownLatch` or barrier to force a reader to run at the sensitive moment, similar to `VolatilePairInvariantDemo`. Tests against the fixed design must use the **public snapshot API** and verify the reader never observes a total of 99. Tests must release latches/workers in `finally` so the test process does not hang.

### 15.3 Verification of Exceptions and Cancellation

Inject failures at steps that can throw: validation, candidate state preparation, external callbacks, or lock waiting. Valid outcomes must be:

- the operation succeeds and the **entire state** is committed;
- or the operation fails and state remains consistent per the defined policy.

Do not only assert that an exception was thrown; assert the invariant **after the exception**, after cancellation, and after timeout.

### 15.4 Interleaving Tests and Runtime Observation

Run multiple threads, increase contention, and repeat stress tests; observe throughput, p95/p99 latency, queue depth, and contention under realistic load. OpenJDK's **jcstress** tool can help build small concurrency experiments and classify allowed vs. forbidden outcomes.

However, passing tests do not prove the absence of races. Code review must trace all accesses and happens-before relationships accurately; tests are supporting evidence, not a substitute for proving the protocol.

## 16. Common Mistakes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Making each field `volatile` and updating sequentially. | Visibility does not group multiple writes into one transaction. | A shared lock or immutable aggregate state. |
| Using one `AtomicInteger` per field. | Atomic at the single-variable level, not at the multi-field invariant level. | `AtomicReference` of a single state, or lock the whole operation. |
| Synchronizing only setters, leaving getters unlocked. | Readers can see intermediate state and lack happens-before. | Read snapshots under the same protocol. |
| Two separately synchronized getters combined by caller. | An update can occur between the two getters; snapshot mixes versions. | One snapshot getter returning the whole group. |
| Returning a mutable collection from a synchronized getter. | Callers mutate the collection after the lock is released. | Immutable/deep snapshot or owner-managed update APIs. |
| Acquiring two locks in caller-supplied parameter order. | Two threads passing (A, B) and (B, A) can deadlock. | Global lock ordering, with a tie-breaker when needed. |
| Letting an exception occur between two assignments and relying on lock release. | Releasing a lock does not roll back partial state. | Validate/prepare first, commit safely, roll back when needed. |
| Computing `int a + b` without checking overflow. | Wrap-around can break invariants despite proper synchronization. | Bounds checks or checked arithmetic. |
| Putting non-idempotent side effects inside a CAS loop. | CAS failure causes retries and side effects may repeat. | Separate state preparation from side effects; design for idempotency. |
| Using JVM locks to synchronize databases/multiple services. | Locks only protect state and participants within one JVM. | Transactions/versioning/idempotency at the right system level. |
| Testing only the final state. | Can miss skewed intermediate snapshots. | Test snapshots while updates are in progress using latches/barriers. |

## 17. Checklist for Designing a Multi-Field Thread-Safe Object

Before publishing an object to multiple threads, answer:

1. **Invariant:** which formulas/relationships between fields must hold at public boundaries?
2. **Ownership:** which object/class owns the entire state group and the right to mutate it?
3. **Writers:** what are all methods and threads that can change state? Are there any paths bypassing the protocol?
4. **Readers:** can readers obtain a consistent snapshot, or are they combining multiple getters?
5. **Atomic boundary:** are check, validation, and all assignments inside one critical section or CAS candidate?
6. **HB:** do publishing writes and subsequent reads have a valid happens-before relationship?
7. **Failure:** do exceptions, overflow, interruption, timeouts, and early returns preserve the invariant?
8. **Multiple objects:** do we need lock ordering, a single ledger owner, or a higher-level transaction?
9. **Performance:** is lock contention or CAS retry actually a measured bottleneck?
10. **Evidence:** do we have contention tests, intermediate snapshot tests, failure tests, and an invariant review?

### Self-Check Questions

**1.** Two fields `available` and `reserved` are both `volatile`. A writer decrements `available` and then increments `reserved`. Can a reader temporarily see the wrong sum?  
**Yes.** Two volatile writes are two separate actions, not one atomic transition.

**2.** Why is locking each setter separately while combining two getters still wrong?  
**Because** a writer can update between the two getter calls. For a consistent snapshot, both must be read under one critical section or from the same immutable state.

**3.** Which two problems does using the same lock in `reserveOne()` and `snapshot()` solve?  
**Mutual exclusion** for atomic updates at method boundaries, and **happens-before** via unlock→lock for visibility.

**4.** If you use two `AtomicInteger`s where every individual operation is atomic, is the invariant `a + b = 100` preserved at every snapshot?  
**No.** Atomicity is per field; the sum is a cross-variable invariant.

**5.** When is `AtomicReference<State>` appropriate?  
When the entire state can be represented as an immutable snapshot, each update builds a candidate and publishes it with a single CAS, and you accept allocation/retry costs while avoiding side effects in the CAS loop.

**6.** Why is `finally { lock.unlock(); }` not enough for exception safety?  
It releases the lock, but does not automatically undo writes that happened before the exception. Partial state can become observable after unlocking.

**7.** Two accounts have separate locks: thread A acquires lock 1→2, thread B acquires 2→1. What is the risk?  
**Deadlock.** Use a global lock acquisition order or a single owner lock for the invariant.

**8.** When transferring money between two databases in two processes, does `synchronized` in one service guarantee the total balance stays constant?  
**No.** You need a system-level data/transaction protocol, because a single JVM's monitor does not span other processes.

**9.** Why can tests that only check the final balance miss bugs?  
Because temporary inconsistent state may have been exposed and then repaired before the test reads it. You must test snapshots while operations are in progress.

**10.** What initial approach should you choose for a multi-field invariant inside one object?  
Usually a **private lock and business-level API**, because it is easy to prove correct. Switch to immutable snapshots/CAS or specialized locks when requirements and performance evidence justify it.

**Key takeaway:** Preserving multi-field invariants is a problem of **designing atomic state transitions and observing consistent snapshots**. All writers and readers must follow the same ownership and synchronization boundary; `volatile` or per-field atomics cannot replace a protocol protecting **the entire relationship between them**.
