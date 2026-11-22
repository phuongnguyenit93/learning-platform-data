# Atomics Do Not Replace Multi-Object Transactions in Java Concurrency

In Java, classes such as `AtomicInteger`, `AtomicLong`, `AtomicBoolean`, and `AtomicReference` provide **atomic operations on a single specific unit of state**. For example, `incrementAndGet()` does not lose increments; `compareAndSet(expected, update)` updates only when the current value matches `expected`. However, if a business operation must modify **two accounts, two related fields, or multiple distinct objects**, individual atomic updates **do not automatically turn the entire workflow into an atomic transaction**.

A money transfer is the clearest example: debiting A and crediting B must together form a valid state. If another thread observes between the two steps, the total balance temporarily drops. If an exception occurs or the JVM stops after the debit step, the total can remain wrong permanently. Using two `AtomicLong` instances does not solve that transaction boundary.

This lesson belongs to **Atomic & CAS in Java Concurrency in general**. It distinguishes per-variable atomicity from multi-object transactions; it guides you in using a shared lock region, ordered locking of multiple objects, or grouping immutable state into a single `AtomicReference`. Spring-specific integration mechanisms are outside the scope.

## 1. What is an atomic, and where do its guarantees apply?

`java.util.concurrent.atomic` contains primitives for concurrent programming. Some examples:

| API | Typical atomic operation | Protected unit |
| --- | --- | --- |
| `AtomicInteger.incrementAndGet()` | Read–modify–write an integer without lost updates from contenders operating on the same atomic. | One `AtomicInteger`. |
| `AtomicLong.addAndGet(delta)` | Adds to an atomic variable and returns the new value. | One `AtomicLong`. |
| `AtomicBoolean.compareAndSet(false, true)` | Flips the flag if the current value is still false. | One `AtomicBoolean`. |
| `AtomicReference<T>.compareAndSet(old, next)` | Replaces the **reference** if it still matches the expected reference. | One atomic reference. |
| `AtomicReference<T>.getAndUpdate(fn)` | Attempts to update a reference via a function; may re-execute the function under contention. | One atomic reference; does not automatically protect side effects of `fn`. |
| `AtomicIntegerArray` | Atomic operations **per specified element**. | One element at one index per operation. |

Standard atomic operations also have **memory effects** under the Java Memory Model contract. However, there are three levels of correctness to consider separately:

1. **Atomicity:** Can a single RMW operation lose an update?
2. **Visibility/ordering:** Under what synchronization/happens-before relationship do threads observe writes?
3. **Cross-variable/cross-object invariant:** Do multiple values together reflect **one valid business state**?

A program can satisfy (1) and (2) for each atomic variable and **still fail (3)** for the overall business operation.

### 1.1 A transaction is a larger contract than a single CAS instruction

In this lesson, a "transaction" in the sense of *an integral logical operation* must have these minimum properties:

- **All-or-nothing on protected state:** Dependent steps must be observed as a single change, or none of the steps are committed.
- **Invariant preserved:** For example, `balanceA + balanceB == total`.
- **Isolation at the defined observation boundary:** Readers must not read half old state and half new state if the contract requires a consistent snapshot.
- **Exception/cancellation safety:** A failure in the middle must not leave objects in a state that violates the invariant.

This is **not by default a database ACID transaction**. Atomicity in a single JVM's memory differs from durability across a JVM crash, two processes, a database, or a remote service. Distinguish the scope upfront to avoid using the wrong mechanism.

## 2. Classic example: two AtomicLongs still leave a gap

Suppose two internal accounts have a total of 100 units:

~~~java
AtomicLong accountA = new AtomicLong(100);
AtomicLong accountB = new AtomicLong(0);

accountA.addAndGet(-30);
accountB.addAndGet(30);
~~~

Each `addAndGet` is atomic **on that variable itself**. But the two add/subtract operations are **two separate update points**. In between them, the actual state can be:

~~~text
Before: A=100, B=0,  A+B=100
During: A=70,  B=0,  A+B=70
After:  A=70,  B=30, A+B=100
~~~

A thread reading an asset report right between the two steps sees a total of 70. That is not "reading a stale cache"; it is a **real intermediate state** that the protocol allows to be observed.

The situation is even more dangerous if an exception occurs after the debit but before the credit. Making both fields atomic does not create a rollback mechanism, nor does it make the credit to B happen automatically once the debit on A has succeeded.

## 3. Java 17+ program: reproducing the bug deterministically

Instead of relying on a lucky stress-test loop to catch the interleaving, use two `CountDownLatch` instances to pause the transfer thread right after the debit step.

Create `AtomicTransferGapDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class AtomicTransferGapDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger accountA = new AtomicInteger(100);
        AtomicInteger accountB = new AtomicInteger(0);
        CountDownLatch debited = new CountDownLatch(1);
        CountDownLatch continueTransfer = new CountDownLatch(1);

        Thread transfer = new Thread(() -> {
            boolean success = accountA.compareAndSet(100, 70);
            if (!success) {
                throw new AssertionError("Unexpected starting balance");
            }
            debited.countDown();
            try {
                continueTransfer.await();
                accountB.addAndGet(30);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "transfer");

        transfer.start();
        debited.await();

        try {
            System.out.println("During: A=" + accountA.get()
                    + ", B=" + accountB.get()
                    + ", total=" + (accountA.get() + accountB.get()));
        } finally {
            continueTransfer.countDown();
        }

        transfer.join();
        System.out.println("After: A=" + accountA.get()
                + ", B=" + accountB.get()
                + ", total=" + (accountA.get() + accountB.get()));
    }
}
~~~

Compile and run on JDK 17 or later:

~~~bash
javac AtomicTransferGapDemo.java
java AtomicTransferGapDemo
~~~

Stdout under normal conditions, without external interruption:

~~~text
During: A=70, B=0, total=70
After: A=70, B=30, total=100
~~~

**Why is the output deterministic?** The transfer thread completes the debit CAS and signals `debited.countDown()`. Main calls `debited.await()` and then reads both atomics, while transfer cannot credit B yet because of `continueTransfer.await()`. Main opens the gate in `finally` and waits with `join()`. The latches serve to **control test timing**, not as a transaction mechanism.

Even though `accountA.compareAndSet` is a properly conditioned CAS, that CAS **does not cover the `accountB` variable**. Adding `volatile`, multiple `get()` calls, or `Thread.sleep()` does not turn two updates into one operation.

**Demo scope note:** If the transfer thread is interrupted externally while waiting on the latch, the example code may skip the credit step. That is precisely a kind of failure window that production code must handle; do not treat a bug-demonstration example as safe business code.

## 4. CAS protects a precondition but does not commit multiple objects

You can fix the "overdraft" risk on A alone using a CAS loop:

~~~java
boolean withdraw(AtomicLong balance, long amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }
    while (true) {
        long current = balance.get();
        if (current < amount) {
            return false;
        }
        if (balance.compareAndSet(current, current - amount)) {
            return true;
        }
    }
}
~~~

This is a **Java method snippet**, assuming `AtomicLong` is imported; it compiles when placed in an appropriate class. The CAS enforces the non-negative balance condition for **one balance**, provided all write paths to that balance use the same protocol. But if you then transfer funds with:

~~~java
if (withdraw(accountA, 30)) {
    accountB.addAndGet(30);
}
~~~

there is still a gap between the two actions. The CAS on A is only the **linearization point of `withdraw`**, not the linearization point of **transfer A→B**.

### 4.1 Commit boundary principles

When an operation consists of multiple changes, you must answer:

- When can we say "the transfer succeeded"?
- Are other threads allowed to read both accounts while the transfer is incomplete?
- If the credit fails, can the debit be rolled back? What if the rollback itself faces contention?
- If the process dies midway, can the state be recovered?
- What other methods modify A or B? Do they follow the same protocol?

If you cannot point to a single commit boundary protecting the entire invariant, adding more `AtomicInteger`/`AtomicLong` fields does not solve the root cause.

## 5. Individual atomic fields and consistent snapshots are two different problems

Neither of the following read snippets **guarantees** a linearizable snapshot of the account pair when writers update them independently:

~~~java
long a = accountA.get();
long b = accountB.get();
long total = a + b;
~~~

or:

~~~java
long a1 = accountA.get();
long b = accountB.get();
long a2 = accountA.get();
if (a1 == a2) {
    // Not general proof that both a and b belong to the same version.
}
~~~

This is an **illustrative code snippet**, assuming two atomics have been created. In the second snippet, A could change and return to its original value (**ABA**), or B could change independently while A stays unchanged. Comparing two reads of A does not confirm whether an overall transaction occurred.

**Snapshot consistency** requires all relevant values to be taken from **one logical state**. Ways to achieve this include:

1. A shared `synchronized`/`ReentrantLock` protecting all writers and readers of the invariant.
2. An immutable aggregate state published via `AtomicReference<State>`, with readers reading **one reference**.
3. A carefully designed versioned snapshot/seqlock protocol (much harder, prone to retry/starvation, unsuitable for ad-hoc hand-rolling).
4. A datastore transaction if the state lives outside a single JVM.

If business requirements only need approximate numbers (e.g., dashboard metrics), a temporarily skewed snapshot may be acceptable. However, if making withdrawal decisions, granting quotas, or verifying financial invariants, a stricter consistency contract must be defined.

## 6. Right direction 1: one owner and one shared critical section

When two balances belong to **the same owner object** within a single JVM, the clearest solution is usually one lock protecting both.

Idea:

~~~java
synchronized (lock) {
    if (accountA >= amount) {
        accountA -= amount;
        accountB = Math.addExact(accountB, amount);
    }
}
~~~

This is an illustrative snippet and does not yet handle full validation and exception safety. You must **compute/validate target values before mutating** because `Math.addExact` can throw an exception; if you subtract from A and then call `addExact` and overflow occurs, the state is left partial when the monitor is released.

Safer pattern:

~~~java
synchronized (lock) {
    if (accountA < amount) {
        return false;
    }
    long nextA = accountA - amount;
    long nextB = Math.addExact(accountB, amount);

    accountA = nextA;
    accountB = nextB;
    return true;
}
~~~

The snippet above is inside a method returning `boolean`, assuming `amount > 0` has already been checked. Operations that may throw are performed before the commit; afterward, only primitive assignments remain. Every reader must read both A and B **under the same lock**, because inside the critical section there are still two consecutive assignments.

### 6.1 Standalone runnable Java 17+ program

Create `LockedTransferDemo.java`:

~~~java
public final class LockedTransferDemo {
    private record Snapshot(long accountA, long accountB) {
        long total() {
            return Math.addExact(accountA, accountB);
        }
    }

    private static final class Ledger {
        private final Object lock = new Object();
        private long accountA = 100;
        private long accountB;

        boolean transfer(boolean fromA, long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            synchronized (lock) {
                long from = fromA ? accountA : accountB;
                long to = fromA ? accountB : accountA;
                if (from < amount) {
                    return false;
                }

                long nextFrom = from - amount;
                long nextTo = Math.addExact(to, amount);
                if (fromA) {
                    accountA = nextFrom;
                    accountB = nextTo;
                } else {
                    accountB = nextFrom;
                    accountA = nextTo;
                }
                return true;
            }
        }

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(accountA, accountB);
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();
        Runnable work = () -> {
            for (int i = 0; i < 100; i++) {
                if (!ledger.transfer(true, 1)
                        || !ledger.transfer(false, 1)) {
                    throw new AssertionError("Transfer unexpectedly failed");
                }
            }
        };

        Thread first = new Thread(work, "first");
        Thread second = new Thread(work, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        Snapshot s = ledger.snapshot();
        System.out.println("A=" + s.accountA());
        System.out.println("B=" + s.accountB());
        System.out.println("Total=" + s.total());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac LockedTransferDemo.java
java LockedTransferDemo
~~~

Stdout without external interruption:

~~~text
A=100
B=0
Total=100
~~~

Each thread performs 100 pairs of 1-unit transfers A→B then B→A. Because each thread only transfers back after transferring out, the total committed A→B transfers can never be less than the total committed B→A transfers; B always has enough for each return transfer. During execution, balances A and B may change, but **every snapshot taken via `ledger.snapshot()`** preserves a total of 100 and no negative balances.

Key points:

- `Ledger` owns **both balances**. Callers cannot modify an account directly through a public reference.
- `transfer` performs the balance check, overflow check, and updates **both fields under a single lock acquisition**.
- `snapshot` acquires **the same lock** and returns an immutable record. Readers do not mix two versions.
- The `Math.addExact` calculation is placed **before** the commit. If it throws, the old state remains intact.
- `Thread.join()` lets `main` know both workers have finished; in this example there are no expected-to-fail operations.
- The final output is deterministic, and the example also demonstrates **how to read a snapshot at any point in time**, not just measure the final total.

**Do not default to a single application-wide `synchronized` lock.** A lock should belong to the owner of the specific invariant; unrelated states can have their own owners to avoid unnecessary contention.

## 7. Right direction 2: lock multiple objects in a global order

Sometimes each `Account` must be an independent object and cannot naturally be merged into a single ledger. To transfer between two objects, you need a protocol that locks **both simultaneously** and requires all related code to follow it.

If thread T1 locks A→B and T2 locks B→A, both can deadlock. You need a consistent rule, typically based on a **unique, immutable ID**, independent of the transfer direction:

~~~java
Account first = from.id < to.id ? from : to;
Account second = from.id < to.id ? to : from;

synchronized (first.lock) {
    synchronized (second.lock) {
        // Check the balance of from and update both from and to.
    }
}
~~~

This is an illustrative snippet. `Account` needs a unique `id`, a private/protocol-controlled `lock`, `balance`, and related methods. You must handle `from == to`, duplicate IDs, invalid amounts, and overflow; do not treat the snippet as a complete production class.

### 7.1 Conditions for true correctness

Not only the `transfer` method must follow the ordering:

1. Any writer modifying an account's balance must hold **that account's lock**.
2. An operation affecting two accounts must hold **both locks** in the stable order.
3. A reader requiring a **snapshot of the account pair** must also acquire both locks under the same protocol. Reading each account via separate `synchronized` getters can still read from two different points in time.
4. Do not leak locks to uncontrolled code; callbacks could acquire locks in reverse order.
5. Perform validation and calculations before committing, avoiding exceptions between debit and credit.
6. If amounts or totals can overflow, use appropriate arithmetic types and range checks.

A transfer with two Java assignments inside nested `synchronized` blocks is not a single CPU instruction. However, **for all observers adhering to the lock protocol**, the operation can be viewed as atomic; external code cannot interleave to observe an intermediate state.

### 7.2 Lock granularity and scalability

Locking two accounts allows transactions on **two unrelated pairs** to run concurrently. That is the benefit over a global ledger lock. In exchange:

- Lock-ordering logic is more complex.
- Deadlocks are easier to introduce when operations involving three or more accounts interleave.
- A system-wide snapshot must coordinate multiple locks, which is costly.
- Ownership rules and edge cases must be reviewed across every call path.

Choose multi-lock when **concurrency demand and object count** justify it. Do not split locks just because you are "using atomics" when the system has no solution for consistent snapshot reads.

## 8. Right direction 3: bundle the invariant into an immutable state and CAS a single reference

If a group of fields can be managed as **one immutable state**, `AtomicReference<State>` allows replacing **the entire snapshot** with a single CAS. This is how atomics can achieve a form of multi-field transaction **after redesigning them into a single atomic unit**.

~~~text
State old = (A=100, B=0)
      |
      | create complete new State (A=70, B=30)
      v
AtomicReference<State>.compareAndSet(old, next)
      |
      +-- success: entire new snapshot takes effect
      |
      +-- failure: discard candidate, read new state, and retry
~~~

The core benefit is that readers can fetch `State s = ref.get()` **once**, then read both fields from that same immutable object. There is no "old A, new B" if the object is fully constructed before publication and never mutated afterward.

### 8.1 Runnable Java 17+: transfer with AtomicReference

Create `AtomicStateTransferDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public final class AtomicStateTransferDemo {
    private record State(long accountA, long accountB) {
        State {
            if (accountA < 0 || accountB < 0
                    || Math.addExact(accountA, accountB) != 100) {
                throw new IllegalArgumentException("Invalid state");
            }
        }

        long total() {
            return Math.addExact(accountA, accountB);
        }
    }

    private final AtomicReference<State> current =
            new AtomicReference<>(new State(100, 0));

    boolean transfer(boolean fromA, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        while (true) {
            State old = current.get();
            long from = fromA ? old.accountA() : old.accountB();
            long to = fromA ? old.accountB() : old.accountA();

            if (from < amount) {
                return false;
            }

            long nextFrom = from - amount;
            long nextTo = Math.addExact(to, amount);
            State next = fromA
                    ? new State(nextFrom, nextTo)
                    : new State(nextTo, nextFrom);

            if (current.compareAndSet(old, next)) {
                return true;
            }
            // Another thread committed first: read the new state and retry.
        }
    }

    State snapshot() {
        return current.get();
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicStateTransferDemo ledger = new AtomicStateTransferDemo();
        Runnable work = () -> {
            for (int i = 0; i < 100; i++) {
                if (!ledger.transfer(true, 1)
                        || !ledger.transfer(false, 1)) {
                    throw new AssertionError("Transfer unexpectedly failed");
                }
            }
        };

        Thread first = new Thread(work, "first");
        Thread second = new Thread(work, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        State result = ledger.snapshot();
        System.out.println("A=" + result.accountA());
        System.out.println("B=" + result.accountB());
        System.out.println("Total=" + result.total());
    }
}
~~~

Run on JDK 17+:

~~~bash
javac AtomicStateTransferDemo.java
java AtomicStateTransferDemo
~~~

Stdout:

~~~text
A=100
B=0
Total=100
~~~

**Why is one CAS sufficient for the group of fields?**

- `State` is an immutable record containing only two `long` primitives; its constructor validates non-negative balances and a sum of 100, so every instance is valid.
- All writers go through `current.compareAndSet(old, next)`. A successful CAS swaps **a single reference** from the old snapshot to the new snapshot.
- Readers perform a single `current.get()` and read `accountA` and `accountB` from the same object; no mixing of two states occurs.
- If another contender updates first, the CAS fails; the loop re-reads the snapshot. Thus writers do not overwrite a newer update with calculations based on stale state.
- There are no external side effects in the candidate computation, so retrying is safe within the scope of this example.
- Both threads perform balanced pairs of transfers like the lock example; the final state is deterministic.

**Key takeaway:** This solution succeeds not because "`AtomicReference` has multi-object transactions," but because we **changed the data model**: the two balances are no longer two independent mutable objects; they are two components of **one immutable aggregate state** published via **one atomic reference**. If the two accounts still had separate public setters, a CAS on a third reference would not protect those update paths.

### 8.2 CAS loops can retry and are not free

A CAS loop does not acquire a monitor, but it has costs and limits:

- High contention causes frequent CAS failures, leading to retries, CPU usage, and discarded candidate allocations.
- A specific thread is not guaranteed service in bounded time; **starvation** can still occur.
- A new object is allocated on each attempt; GC and cache behavior depend on workload.
- The function computing `next` must be **pure or have safely repeatable side effects**. Update methods based on `getAndUpdate` can also invoke the update function multiple times.
- A record holding a reference to a mutable object is not automatically deeply immutable. Mutable collections/elements need defensive copying or their own ownership protocol.
- Algorithms that reuse references/values can encounter the **ABA** problem when history matters. In this example, each state is newly allocated and old objects are not reused; if business logic needs versioning, add a version field to the state.

With many fields and complex invariants, `synchronized` can be easier to understand, easier to audit, and better performing than an allocation-heavy CAS loop. Do not choose "lock-free" just for the label.

## 9. AtomicReference on a reference does not make the underlying object graph atomic

Wrong example:

~~~java
class Pair {
    int a;
    int b;
}

AtomicReference<Pair> ref = new AtomicReference<>(new Pair());
Pair pair = ref.get();
pair.a = 70;
pair.b = 30;
~~~

This is an illustrative snippet. `ref.get()` is atomic **with respect to the reference**, but the two direct field assignments on the same `Pair` are ordinary mutable operations, unprotected by CAS. Another reader can observe `a = 70` while `b` still holds its old value.

For an atomic reference to publish a logical transaction, you must:

1. Create a **new, independent, and complete `State`**.
2. Never mutate a published `State`.
3. Commit with a valid `set` if there is only a single writer and the protocol allows it, or CAS if multiple writers must avoid lost updates.
4. Have readers fetch the reference **once** for the entire snapshot.
5. Prevent external code from bypassing the owner and mutating other state.

Even `AtomicReference<List<Item>>` can hold a mutable `ArrayList`; an atomic reference alone does not make that list thread-safe. If you need an immutable snapshot, make an intentional copy and ensure **the elements themselves** have appropriate immutability semantics.

## 10. Composite operations and `ConcurrentHashMap`: scope still matters

Many concurrent APIs provide atomic operations **within the scope of a single key** or single mapping:

~~~java
ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
counts.merge("paid", 1, Integer::sum);
~~~

This is an illustrative snippet, assuming `ConcurrentHashMap` is imported. `merge` applies the update to the corresponding mapping per the map's contract. However, a business operation needing to update **two keys together**:

~~~java
counts.merge("available", -1, Integer::sum);
counts.merge("reserved", 1, Integer::sum);
~~~

is still **two operations**. A reader can observe one value after the first merge and the other value before the second merge. `ConcurrentHashMap` does not promise map-wide transactions just because individual methods are thread-safe.

Even when `compute` or `merge` runs atomically for a single key, using the mapping function to modify other objects/keys outside that scope can cause races, deadlocks, or contract violations. Do not perform I/O or long blocking inside a mapping function.

If the invariant truly spans multiple keys, redesign the **transaction boundary**: an owner-level lock protecting operations and snapshots, an immutable aggregate object under one key/reference, or a transaction at the appropriate data layer.

### 10.1 `LongAdder` and metrics are not transactions

`LongAdder` can reduce contention for high-write statistical counters by striping updates; calling `sum()` during concurrent updates is **not an atomic snapshot**. It suits metrics where an approximate value at read time is acceptable, not account/quota invariants requiring exact instantaneous consistency.

Similarly, multiple independent `AtomicInteger` instances can be appropriate when they represent **independent metrics** and readers do not need a consistent sum. The problem arises only when business rules commit those values to belong to a single state together.

## 11. Liveness: multiple CAS operations do not automatically give whole-operation progress

CAS is often the foundation of **non-blocking** algorithms, but distinguish:

- **Lock-free:** Under the algorithm's progress definition, the system as a whole guarantees progress under the model's conditions; it does not guarantee a specific thread will avoid starvation.
- **Wait-free:** Every operation completes in a bounded number of steps under the model, a stronger guarantee.
- **Obstruction-free:** A thread completes if it runs long enough without contention.

You cannot conclude that a business operation consisting of **two CAS operations on two variables** is a "lock-free transaction" just because each individual CAS is lock-free. If the first CAS succeeds and the thread is preempted or canceled before the second CAS, the business state remains incomplete.

A correct multi-word CAS or transactional memory algorithm typically requires **descriptors, helping mechanisms, versioning, or rollback** with subtle proofs. Standard Java SE `AtomicInteger`/`AtomicReference` **do not provide a multi-address transaction API**. Hand-rolling such an algorithm just to avoid a lock usually introduces severe risk.

A CAS loop with many contenders can also retry continuously; you need to check retry rates, tail latency, and cancellation behavior. "Not using a monitor" does not mean "no liveness issues."

## 12. Exceptions, interruption, and rollback: per-step atomicity is not enough

Suppose code executes:

~~~java
accountA.addAndGet(-30);
sendNetworkMessage();  // May throw or time out.
accountB.addAndGet(30);
~~~

This is an illustrative snippet without a declaration for `sendNetworkMessage`. If the network call throws an exception, the program can stop after debiting A without crediting B. Turning both `addAndGet` calls into two CAS operations does not change this failure window.

### 12.1 Why manual rollback can also be wrong

One idea is:

~~~java
try {
    accountA.addAndGet(-30);
    accountB.addAndGet(30);
} catch (RuntimeException e) {
    accountA.addAndGet(30);
    throw e;
}
~~~

This snippet is **not a safe transaction**: between steps, other threads can update A or B; rolling back by adding 30 does not necessarily restore the exact prior business state. Even if the credit to B succeeded and an exception occurred elsewhere, rolling back A gives no basis to decide whether B must also be rolled back.

A proper rollback requires knowing **the exact committed state**, isolation of concurrent operations, and how to handle errors during rollback itself. With external side effects, there is also the risk that the remote side processed the request while the caller only saw a timeout.

### 12.2 Exception safety with locks

`synchronized` or `ReentrantLock` protects atomic observation **if all readers/writers follow the same protocol**, but it does not automatically roll back data on an exception:

~~~java
synchronized (lock) {
    accountA -= amount;
    long nextB = Math.addExact(accountB, amount); // May throw.
    accountB = nextB;
}
~~~

If `addExact` throws after the subtraction, the monitor is released as the exception unwinds, leaving an invalid state. **Compute and validate all values that could throw before committing**, then perform simple assignments inside the critical section:

~~~java
synchronized (lock) {
    if (accountA < amount) {
        return false;
    }
    long nextA = accountA - amount;
    long nextB = Math.addExact(accountB, amount);
    accountA = nextA;
    accountB = nextB;
    return true;
}
~~~

This is an illustrative method snippet assuming `amount > 0` is already validated, fields are `long`, and the method returns `boolean`. The correctness of both assignments is protected by the lock; readers cannot interleave between the two assignments if they use the same lock.

### 12.3 Interruption is not transaction rollback

`Thread.interrupt()` is a cooperative signal. It does not undo writes already performed. A well-designed operation should check for interruption/cancellation only at **safe points**, or prepare appropriate rollback/compensation capabilities. Do not split a financial operation into multiple primitives and hope an interrupt will return the system to its prior state.

## 13. Crash consistency and durability: locks/CAS cannot persist data durably

Inside a running JVM, locks or CAS can protect **in-memory state**. But if the JVM/process dies after writing one object and before writing another, state outside RAM or external logs may already reflect a partial operation.

Do not confuse them:

| Capability | AtomicInteger / CAS | A JVM lock | Durable data transaction |
| --- | --- | --- | --- |
| Atomic single variable/reference in RAM | Yes, per operation | Yes, if accessed under protocol | Depends on storage |
| Atomic multiple fields in RAM | No if independent atomics; possible if immutable state is bundled into one reference | Yes, if all accesses share the lock | Depends on transaction boundary |
| Isolation across multiple JVMs/processes | No | No | Requires storage/distributed mechanism |
| Rollback on exception | Not automatic | Not automatic | Can be supported by transaction system per contract |
| Durability after process crash | No | No | Requires durable storage mechanism |
| Exactly-once network I/O | No | No | Requires dedicated protocol; not guaranteed by default |

A database transaction can provide atomicity/isolation/durability depending on configuration and isolation level; not every database or out-of-transaction operation gives the same guarantees. If transferring between **two independent datastores** or between a database and a message broker, that is a cross-system transaction problem that cannot be solved solely by monitors or atomic classes in the application.

Broader solutions may include database transactions, optimistic version checks, idempotency keys, a durable outbox, sagas/compensating actions, or distributed transactions where supported. Each has its own trade-offs and failure models. In this lesson, simply remember that **the scope of locks/CAS does not extend beyond the objects controlled by their protocol within a single JVM**.

## 14. Atomicity, isolation, visibility, and linearizability

These terms are related but not synonymous:

| Term | Practical meaning | Example |
| --- | --- | --- |
| **Atomicity** | An operation is observed as an indivisible change within the defined scope. | Transfer updating two balances under one lock. |
| **Isolation** | Concurrent operations do not see invalid intermediate states per the contract. | Pair reader acquiring both locks. |
| **Visibility / happens-before** | Write effects are published and observed according to JMM rules. | Unlock → subsequent lock on the same monitor. |
| **Linearizability** | Each operation can be treated as taking effect at a single point between invocation and response, preserving the real-time order of non-overlapping operations. | Successful CAS swapping `AtomicReference<State>`. |
| **Durability** | Committed state survives certain classes of failures/crashes per the storage contract. | Writing a transaction to durable storage. |

`AtomicLong.addAndGet` has one linearization point for **one variable**. Two consecutive `addAndGet` operations have **two points**; there is no shared linearization point for the transfer without adding another protocol.

A `synchronized` method performing a transfer while a reader of account B skips the lock also fails to provide the desired isolation: the contract holds only for participants that obey the lock. When discussing "in-memory transactions," always specify which operations fall within the guaranteed scope.

## 15. When are independent atomics still the right choice?

Do not conclude that every occurrence of multiple `AtomicInteger` instances is wrong.

They are appropriate when **states are genuinely independent** or the contract allows approximate snapshots. Examples:

- Success and failure request counters for a dashboard, where slightly skewed totals during updates are acceptable.
- Two independent feature flags, updated separately and not requiring atomic joint state transitions.
- Multiple counters for throughput monitoring, not used for hard quotas or exact accounting.
- Concurrent data structures where each node/key is independent per its designed invariant, not requiring a global snapshot.

Conversely, if a condition like `a + b == capacity`, `paid ⇒ paymentId != null`, or `available >= 0` must hold at **every point observed by an observer**, updates and reads must share a common transaction boundary.

**Correctness depends on the observation contract.** A dashboard accepting eventual consistency is completely different from a quota system that must never exceed a limit.

## 16. Performance and cost of solutions

| Technique | Pros | Costs / limits | When to consider |
| --- | --- | --- | --- |
| One `synchronized` lock for aggregate | Simple, easy to prove correctness, protects multiple fields. | Contention can serialize unrelated operations if the lock is too coarse. | Good default for invariants internal to one owner. |
| `ReentrantLock` | Timeout, interruptible acquisition, `Condition`; preserves invariants across critical sections. | Must unlock in `finally`; easier to introduce error branches. | Need lock acquisition policies or conditions. |
| Lock two objects by ID | Allows disjoint object pairs to run in parallel. | Deadlock if lock order is wrong; global snapshots are harder. | Many independent accounts/objects with transfers between them. |
| `AtomicReference<ImmutableState>` CAS | Single commit point for aggregate; simple snapshot reads. | Allocation, retries, starvation; candidate logic must be pure. | Compact immutable state, multi-writer optimistic updates. |
| Two independent `AtomicLong`s | Cheap and simple for two variables with no shared invariant. | Does not protect multi-variable transactions. | Independent metrics or approximate consistency allowed. |
| Storage/database transaction | Can protect durable data and multiple records per contract. | I/O, transaction contention, isolation/configuration complexity. | Invariants belong to storage or span multiple processes. |

There is no rule that "CAS is faster than `synchronized`." If state consists of only a few fields with heavy updates, a short lock can be more efficient and maintainable than a CAS loop constantly allocating new objects. If there are many readers and few writers, immutable snapshots can be attractive. Measure **throughput, p95/p99 latency, lock blocked time, CAS retry rate, GC allocation**, and invariant correctness under the actual workload.

## 17. How to test multi-object transactions

A test that only compares the total balance **after all threads have joined** can miss the gap between debit and credit. For instance, the first demo has a final total of 100, yet a mid-flight reader sees 70.

Testing steps:

1. **Define exact invariants:** total conserved, non-negative balances, each successful transfer changes exactly two balances.
2. **Define the snapshot contract:** Are readers allowed to view state while a transfer is running? If so, they must see a snapshot before or after a complete transfer.
3. **Use latches/barriers to force interleaving:** Intentionally pause the writer between two steps to verify readers never see partial state. For the fixed design, readers must use the standard snapshot API.
4. **Stress test with multiple writers:** Transfer back and forth across many threads while checking balances and totals.
5. **Inject faults at throwable points:** overflow, validation, callbacks, interruption, or network timeout; verify failed operations still preserve invariants.
6. **Audit all update paths:** setters, admin operations, resets, scheduled jobs, background tasks. A single path bypassing the lock can break the entire protocol.
7. **Measure performance after correctness is achieved:** avoid trading data correctness for an attractive benchmark number.
8. **Recognize testing limits:** Passing many runs does not prove every interleaving is safe. Code review of invariants, lock ownership, and happens-before remains mandatory.

### 17.1 Testing the bug with a countdown between two steps

`AtomicTransferGapDemo` is a control test: with the two-independent-atomics design, a reader is actively placed between the updates and observes `total=70`. When fixed with `Ledger.transfer` or `AtomicReference<State>`, there is no longer an API to see half an update: threads calling `snapshot()` per the protocol will see a valid snapshot.

If you need to test an operation while holding a lock, use a latch to know the worker has entered the critical section, then have the reader call `snapshot()`; the reader will block until the operation releases the lock. **Do not place a latch that makes the worker wait for a signal from the reader while the reader is waiting on the lock held by the worker**, as that would create a test-induced deadlock.

### 17.2 Testing overflow

Test boundaries near `Long.MAX_VALUE` or `Long.MIN_VALUE` and verify that checked arithmetic occurs **before commit**. Java `long` is not immune to overflow just because it is 64-bit; for currency, verify units, value ranges, and appropriate arithmetic. A perfectly synchronized transaction can still be business-incorrect if it overflows.

## 18. Common misconceptions

**"If each addition is atomic, a sequence of two additions is also atomic."** False. Two operations have two commit points and an observer can interleave between them.

**"A's CAS succeeded, meaning the A→B transfer is complete."** False. It only proves a change on A succeeded.

**"Reading twice and comparing can replace a transaction."** Not in general. ABA or other unobserved writers can occur; you need a proven snapshot/versioning protocol.

**"Putting two objects into an `AtomicReference` is enough."** Only when the object graph is properly published, truly immutable, and all mutations go through one reference/protocol. Swapping the reference does not prevent mutating fields of the old object.

**"Two separate `synchronized` getters form a snapshot."** False. A writer can run between the two getter calls. You need a single snapshot operation under the same lock or an immutable aggregate.

**"Having a lock means exceptions automatically roll back."** False. The monitor is released as the exception unwinds, but assignments already executed remain. You must compute/validate before commit or implement a rollback protocol.

**"Removing locks and using multiple CAS calls automatically makes a lock-free transaction."** False. The progress guarantee of a single CAS does not compose into a multi-address transaction; correct algorithms are much more complex.

**"`AtomicReference` can replace a database transaction."** No. It provides neither durability, cross-process isolation, nor rollback of external side effects.

**"`Thread.join` fixes a half-completed transfer."** `join` lets the caller observe that the worker has finished and its memory effects; it does not complete a skipped credit step or repair invariants.

**"Seeing no wrong totals in a stress test proves correctness."** No. Buggy interleavings can be very rare. Use protocol reasoning and latch-coordinated tests.

## 19. Decision workflow by scope

| Problem | Condition | Approach |
| --- | --- | --- |
| One balance needs accurate add/subtract | No invariant outside that balance | One `AtomicLong` or lock, checking amount/overflow. |
| Two fields in the same object must stay consistent | All readers/writers controlled by one owner | `synchronized`/`ReentrantLock` covering check, update, and snapshot. |
| Multiple fields belong to an immutable snapshot | Can be bundled into an object unchanged after publication | `AtomicReference<State>` CAS, all writers via one reference. |
| Two independent `Account`s need transfers | Immutable IDs, clear lock ownership | Acquire both locks in global order; read pair snapshot under same protocol. |
| Multiple keys in `ConcurrentHashMap` share an invariant | Per-key atomicity is insufficient | Design a shared owner/transaction boundary; do not use two independent `merge` calls. |
| Multiple records in one database | Need storage isolation/durability | Database transaction with appropriate isolation level. |
| Database and external service both participate | Network/crash/duplicate delivery possible | Design idempotency, transaction/outbox/compensation per failure model. |
| Metrics with multiple independent counters | Approximate snapshots acceptable | Separate Atomic/`LongAdder` per metric. |

**Practical rule:** Choose the **unit that owns the invariant** first, then ensure both updates and observations go through that unit. If you cannot identify who owns the entire invariant, the problem needs a data-model/transaction-boundary redesign before choosing an Atomic API or lock.

## 20. Self-check questions

**1.** Two `AtomicLong`s, each `addAndGet` is atomic. Is transferring 30 from A to B atomic?  
**No.** There is a gap between debiting A and crediting B; an observer can see an incorrect total.

**2.** CAS prevents A from being overdrawn. Why is that still not enough for a transfer?  
**Because** B's precondition and update are not part of the same atomic operation. A's CAS does not commit B.

**3.** Two balances reside in the same `Ledger`. What is the easiest solution to prove correct?  
**A private lock** protecting both transfer and snapshot; compute/validate before committing.

**4.** If each `Account` has its own lock, how do you avoid deadlock when transferring A↔B?  
**Acquire both locks in a stable global order**, such as by unique ID; all call paths must follow the same protocol.

**5.** Why can a single `AtomicReference<State>` suffice when both balances are fields of an immutable `State`?  
**Because** a single CAS swaps the entire reference to the snapshot; readers fetch a single reference rather than reading two separate mutable objects.

**6.** If `State` has a mutable `List` field and a caller modifies the list after publication, is the snapshot still immutable?  
**No.** A record/final reference does not automatically make the object graph deeply immutable.

**7.** Can you call a remote API inside a `getAndUpdate` lambda and expect it to run only once?  
**No.** The function may be invoked multiple times under contention; side effects must be separated or made idempotent by design.

**8.** Does `synchronized` automatically roll back when `Math.addExact` throws an exception between two assignments?  
**No.** The JVM releases the monitor, but assignments already executed remain; compute before committing.

**9.** Do two consecutive `ConcurrentHashMap.merge` calls on two keys create a map-wide transaction?  
**No.** Each `merge` has its own scope and does not automatically protect an invariant across two keys.

**10.** Why do in-memory CAS/locks not replace database transactions?  
**Because** they do not guarantee durability or isolation across processes and external resources.

**11.** If the final total is always right after `join`, are mid-transfer observers guaranteed to see the right total too?  
**Not necessarily.** You must test and prove the snapshot contract while the operation is in flight.

**12.** When are multiple independent atomics a reasonable choice?  
**When** the values are business-independent or the contract accepts approximate snapshots without requiring cross-variable transactions.

**Key takeaway:** Atomic/CAS is a powerful mechanism for protecting **a single variable or a single reference**. It only protects multi-field transactions when you **bundle the entire invariant into a single atomic unit of update** and enforce that every writer and reader obeys that protocol. If multiple independent objects must be updated consistently, you need an explicit transaction boundary: a shared lock, ordered multi-locking, immutable aggregate CAS, or a transaction mechanism at the appropriate data layer. **Atomic individual steps do not mean the entire workflow is atomic.**
