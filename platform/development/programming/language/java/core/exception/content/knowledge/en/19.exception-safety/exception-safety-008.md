# Distinguishing `synchronized` Lock Release from Data Invariant Preservation in Java

> **Scope:** Java Core → Exception → State Preservation. This lesson explains why an exception can cause a `synchronized` block to exit and release its monitor properly, while the data modified by that code remains in an invalid state. The goal is to distinguish the responsibility of the locking mechanism from the responsibility of designing update operations that are safe on failure.

## 1. Two Different Concepts

In Java, `synchronized` helps threads coordinate access to a **monitor** associated with an object. When a thread enters a `synchronized` block or method, it must hold the corresponding monitor; when the thread exits that region either normally or due to an exception, the JVM releases the monitor held for that entry into the synchronized region.

A **data invariant** is a condition that must hold true for the state the system allows to be observed. For example:

- An account balance must be non-negative.
- When transferring funds internally between two accounts, the total balance remains constant if there are no fees or external cash flows.
- `size` must match the actual number of stored elements.
- A `PAID` order must have corresponding payment information.
- The `start` and `end` fields must satisfy `start <= end` according to the object's contract.

A monitor guarantees **access control/synchronization**; it knows nothing about balances, invoices, inventory, or domain invariants. When a method throws an exception after modifying a field, the JVM does not remember the old value of the field to restore it automatically.

> **Key point:** "The lock is released" is a rule of `synchronized`. "The state remains valid after an error" is a guarantee that **application code must design and verify itself**.

## 2. What Happens When `synchronized` Encounters an Exception?

A synchronized block has the form:

~~~java
// Illustrative code inside a method that already has a lock variable.
synchronized (lock) {
    changeState();
}
~~~

Relevant scenarios:

1. The calling thread must acquire the monitor of `lock` before executing the body.
2. If `changeState()` completes, the thread exits the block and releases the monitor for that entry.
3. If `changeState()` throws an exception that is not handled inside the block, the exception propagates out, the block terminates abnormally, and the monitor is still released.
4. If there is a `catch` **inside** the block, catching the error does not mean exiting the block; the monitor continues to be held until execution actually leaves the `synchronized` region.
5. If the exception is caught **outside** the block, the thread has already left the synchronized region before running the outer handler.

Similarly, a `synchronized` instance method uses the monitor of `this`; a `static synchronized` method uses the monitor of the corresponding `Class` object. These can be **different monitors**, so merely declaring every method `synchronized` is not enough if each method protects state with a different lock.

### When Is the Lock Not Yet Released?

- The block is still running, including while executing statements in a `catch` or `finally` located **inside** the block.
- A thread holds multiple monitors: exiting one block only releases the corresponding monitor; monitors of enclosing synchronized regions may still be held.
- Java allows **reentrant synchronization**: the same thread can re-enter a monitor it already holds; each entry requires a matching exit before the monitor is completely released to another thread.
- `Object.wait()` has special behavior: when called properly on a held monitor, it temporarily releases the monitor of **the object being waited on** while waiting and must re-acquire that monitor before returning; it does not automatically release any other monitors held by the thread.
- `Thread.sleep()` does not release held monitors. `notify()`/`notifyAll()` do not cause the calling thread to release the monitor immediately either.

The automatic lock-release rule of `synchronized` is about **entering and exiting a monitor**, not a promise of progress in cases of deadlock, infinite loops, or JVM termination. You should not state that every `synchronized` call will certainly "eventually release the lock" regardless of whether the program exits the synchronized region.

## 3. Why Releasing the Monitor Can Still Leave Corrupted Data

Consider transferring 30 units from account A to B, initially:

~~~text
A = 100
B = 50
Total = 150
~~~

A method might do the following:

~~~java
// Illustrative code inside a class with fields a and b.
public synchronized void transfer(long amount) {
    a -= amount;                 // A becomes 70
    callRiskyOperation();       // Throws exception
    b += amount;                 // Not executed
}
~~~

When `callRiskyOperation()` throws an exception, the thread exits the method; the monitor of `this` is released. However, at that moment A is 70 and B is still 50, making the total 120. The invariant "total balance remains constant" is broken even though no thread holds the lock anymore.

Another thread arriving later, acquiring the **same monitor**, and reading the state can observe this exact invalid pair of values. The lock ensures it sees updates published according to memory rules; the lock does not make those values valid.

There are two levels to distinguish:

| Question | What does `synchronized` do? | What still must be designed? |
|---|---|---|
| Can two threads concurrently execute code protected by the **same monitor**? | Prevents concurrent execution in regions protected by that monitor | All relevant access paths must use the same locking discipline |
| After the previous thread exits, will the next thread see writes that occurred before the monitor was released? | The *happens-before* rule of unlock → subsequent lock on the same monitor supports visibility/ordering | The observed data must satisfy the invariant |
| Does an exception exiting a synchronized region leave the monitor stuck forever? | The JVM releases the monitor of the exited synchronized region | Do not mistakenly call manual `Lock.lock()` and forget `unlock()` |
| Do assignments that already happened roll back automatically? | **No** | Prepare first, commit safely, controlled rollback, or transaction |
| Do multiple fields update in an all-or-nothing manner automatically? | **Not by default** | Design a commit point, protect all readers, or use an immutable snapshot |
| Could external systems outside the process/JVM already have experienced side effects? | Java monitors do not control I/O or external services | Transactions, idempotency, outbox, or coordination mechanisms |

## 4. Runnable Java 17 Program: Lock Is Released, Yet the Invariant Can Break

The following example creates two independent balance ledgers. The `unsafeTransfer` version deducts from account A and then intentionally throws an exception before adding to B. The `safeTransfer` version prepares the new values and checks for errors **before** mutating the two fields. Another observer thread is started after the failed call and invokes `snapshot()` (which is also `synchronized`), proving it can still acquire the released monitor.

Save as **`SynchronizedInvariantDemo.java`**:

~~~java
public class SynchronizedInvariantDemo {
    record Snapshot(long a, long b) {
        @Override
        public String toString() {
            return "A=" + a + ", B=" + b + ", total=" + (a + b);
        }
    }

    static final class Ledger {
        private long a;
        private long b;

        Ledger(long a, long b) {
            if (a < 0 || b < 0) {
                throw new IllegalArgumentException("negative initial balance");
            }
            this.a = a;
            this.b = b;
        }

        public synchronized void unsafeTransfer(long amount, boolean simulateFailure) {
            if (amount <= 0 || amount > a) {
                throw new IllegalArgumentException("invalid transfer amount");
            }

            a -= amount; // Actual state has already changed.
            if (simulateFailure) {
                throw new IllegalStateException("simulated failure");
            }
            b = Math.addExact(b, amount); // Can fail after A has already been reduced.
        }

        public synchronized void safeTransfer(long amount, boolean simulateFailure) {
            if (amount <= 0 || amount > a) {
                throw new IllegalArgumentException("invalid transfer amount");
            }

            long nextA = Math.subtractExact(a, amount);
            long nextB = Math.addExact(b, amount);

            // All expected error-throwing branches run before commit.
            if (simulateFailure) {
                throw new IllegalStateException("simulated failure");
            }

            a = nextA;
            b = nextB;
        }

        public synchronized Snapshot snapshot() {
            return new Snapshot(a, b);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger unsafe = new Ledger(100, 50);
        try {
            unsafe.unsafeTransfer(30, true);
        } catch (IllegalStateException ex) {
            System.out.println("Unsafe rejected: " + ex.getMessage());
        }

        Thread firstObserver = new Thread(
                () -> System.out.println("Unsafe observer: " + unsafe.snapshot()));
        firstObserver.start();
        firstObserver.join();

        Ledger safe = new Ledger(100, 50);
        try {
            safe.safeTransfer(30, true);
        } catch (IllegalStateException ex) {
            System.out.println("Safe rejected: " + ex.getMessage());
        }

        Thread secondObserver = new Thread(
                () -> System.out.println("Safe observer: " + safe.snapshot()));
        secondObserver.start();
        secondObserver.join();

        safe.safeTransfer(30, false);
        System.out.println("After safe success: " + safe.snapshot());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac SynchronizedInvariantDemo.java
java SynchronizedInvariantDemo
~~~

Stdout output:

~~~text
Unsafe rejected: simulated failure
Unsafe observer: A=70, B=50, total=120
Safe rejected: simulated failure
Safe observer: A=100, B=50, total=150
After safe success: A=70, B=80, total=150
~~~

**Output explanation:**

- `unsafeTransfer` exits via `IllegalStateException`; if the monitor had not been released, `firstObserver` would not have been able to enter `snapshot()` and complete `join()`. However, the monitor was released and the observer reads A=70/B=50, which is **an observable state that violates the invariant**.
- `safeTransfer` throws the same exception type before any assignment to `a`/`b`. Another thread entering `snapshot()` still reads 100/50.
- When `safeTransfer(30, false)` completes, the balances become 70/80 with a total of 150.
- `Math.addExact` detects `long` overflow instead of allowing silent wrap-around arithmetic; because the calculation happens before commit in the safe version, an overflow error will not leave A partially deducted either.
- Using another thread and `join()` for the observer gives deterministic output ordering. This program demonstrates **the semantic difference**, not a tool for proving every thread schedule in a real-world program.

**Limitation of the `safeTransfer` pattern:** the two assignments `a = nextA` and `b = nextB` are still two separate statements. In the given example, there is no user code call or potentially throwing operation between the two assignments, and every public read path via `snapshot()` uses the same monitor. To achieve stronger state consistency guarantees in complex designs, represent the balance pair with an immutable snapshot and commit by swapping a single reference (see Section 7).

## 5. Java Memory Model: Seeing New Data Does Not Mean Valid Data

According to the *happens-before* rule of the Java Memory Model, an **unlock** action on a monitor happens-before a **subsequent lock** action on the same monitor. Writes performed before the unlock are properly published to the next entering thread if the program follows synchronization rules.

This solves the **visibility** problem and supports reasoning about execution order. However, the JVM does not check business invariants:

~~~text
Thread 1                            Thread 2
--------                            --------
lock(this)
a = 70
throw exception
unlock(this)
                                    lock(this)
                                    read a = 70
                                    read b = 50
                                    unlock(this)
~~~

Thread 2 can receive **a memory-consistent snapshot** of the state left behind by Thread 1, while that state is **invalid from a business standpoint**. `volatile`, memory barriers, or locking mechanisms do not automatically provide rollback.

Do not confuse three distinct goals:

1. **Mutual exclusion:** regions using the same monitor do not execute at the same time.
2. **Visibility/order:** cooperating threads observe changes according to memory model rules.
3. **Logical atomicity / invariant preservation:** a business operation only publishes state that is valid according to its contract, even if it fails.

`synchronized` contributes directly to the first two goals. The third depends on **the algorithm and update boundaries**; a lock can be part of the solution, but it does not replace that solution.

## 6. Three Levels of Exception Guarantees

| Guarantee level | State after an operation fails | Relation to `synchronized` |
|---|---|---|
| **No useful guarantee** | Invariants may be violated; object may need repair or discarding | The lock may still have been released properly; `unsafeTransfer` is an example |
| **Basic exception safety** | Object remains valid with no resource leaks, though it may have partially changed according to its contract | Must ensure every error exit point preserves invariants; a mutex only protects access |
| **Strong exception safety** | A failed operation leaves observable state as it was before (*all-or-nothing commit*) | Commonly uses validate → prepare → commit, immutable snapshots, or rollback/transactions |

The phrase "no-throw" is a different goal and must have its scope clearly stated, because severe infrastructure errors or process termination can fall outside reasonable API guarantees. A `synchronized` method does not automatically achieve even the **basic guarantee**. If it leaves an invariant broken after an error, even the basic level fails despite the lock being released.

## 7. Safer Design: validate → prepare → commit

To preserve invariants, structure operations into three phases:

- **Validate:** check parameters, current state, and constraints; fail before modifying live data.
- **Prepare:** compute all intended values, check for overflow, and build the new snapshot in local variables; if this fails, the active state remains unchanged.
- **Commit:** publish the new state through the simplest possible operation, without invoking callbacks or I/O that could fail in the middle.

A balance-pair class can use an immutable `record`:

~~~java
// Snippet declared inside a class, not a standalone Java program.
record Balances(long a, long b) {}

private Balances balances = new Balances(100, 50);

public synchronized void transfer(long amount) {
    Balances current = balances;
    if (amount <= 0 || amount > current.a()) {
        throw new IllegalArgumentException("invalid transfer amount");
    }

    long nextA = Math.subtractExact(current.a(), amount);
    long nextB = Math.addExact(current.b(), amount);
    Balances next = new Balances(nextA, nextB);

    balances = next; // Single commit point publishing the new snapshot.
}

public synchronized Balances snapshot() {
    return balances;
}
~~~

In this snippet, the `a`/`b` pair is completely prepared before publication. If validation, arithmetic, or snapshot creation throws an exception, `balances` still holds the old reference. `Balances` contains only two primitive values, so it does not expose mutable internal data; if a record holds a mutable `List`, `Map`, or array, you must still apply deep immutability or defensive copying.

**Why still use `synchronized`?** So that writers do not read the same old snapshot concurrently and overwrite each other (*lost update*), and so that readers observe updates under the same locking mechanism. A single reference assignment does not by itself solve contention among multiple threads or safe publication if readers bypass the lock.

If you need to avoid monitors, you can represent immutable state with `AtomicReference<Balances>` and a `compareAndSet` loop for contended updates. Conditions and new data must be computed from the snapshot read in each CAS attempt; when CAS fails, re-read and re-validate. This is a concurrency design choice, not an automatic rollback mechanism for external side effects.

## 8. Where Should Exceptions Be Caught?

### 8.1. `catch` Outside the Synchronized Block

~~~java
// Illustrative code; lock and doWork() are declared elsewhere.
try {
    synchronized (lock) {
        doWork();
    }
} catch (RuntimeException ex) {
    reportFailure(ex);
}
~~~

If `doWork()` throws an error, the `synchronized` block has already exited and the monitor for that entry has been released before `reportFailure` runs. However, catching outside **does not restore** fields that `doWork` already modified.

### 8.2. `catch` Inside the Synchronized Block

~~~java
synchronized (lock) {
    try {
        doWork();
    } catch (RuntimeException ex) {
        repairIfPossible(ex);
    }
    // Still holding the lock monitor at this point.
}
~~~

The handler runs while the monitor is still held (aside from special behavior of operations like `wait` if the handler itself calls them). This can be useful if invariants can be restored **under the same lock** before other threads are allowed to read. However, rollback must be genuinely accurate; swallowing an exception and continuing with unrestored state can cause subtler bugs.

If `repairIfPossible` itself throws an exception, the JVM still releases the monitor when exiting the block, but the state may remain half-finished. Every error path, including the recovery path, must be accounted for.

### 8.3. `finally` and State Preservation

`finally` is commonly used for cleanup, but `synchronized` **does not need a manual `finally` to release the monitor**. For example:

~~~java
synchronized (lock) {
    try {
        performWork();
    } finally {
        closeTemporaryResource();
    }
}
~~~

Even if `performWork()` throws an error, `finally` executes before the synchronized block exits normally or abnormally. If `closeTemporaryResource()` also throws an error, it can replace the original exception if not handled properly; design cleanup and error reporting intentionally. Resource cleanup/rollback is a **different responsibility** from releasing a monitor.

## 9. Distinguishing `synchronized` from Manual `Lock` Usage

`synchronized` is guaranteed by the language and JVM to release the monitor when exiting the synchronized region. `ReentrantLock` and other `Lock` implementations provide **explicit** lock/unlock APIs; the application must call `unlock()` properly.

Common pattern with `ReentrantLock`:

~~~java
// Snippet inside a class with:
// private final java.util.concurrent.locks.ReentrantLock lock =
//         new java.util.concurrent.locks.ReentrantLock();
lock.lock();
try {
    validateAndUpdate();
} finally {
    lock.unlock();
}
~~~

If `validateAndUpdate()` throws an exception, `finally` ensures `unlock()` is called on that exit path. Yet `unlock()` also only releases the lock; it **does not undo** what `validateAndUpdate()` has already written.

If you acquire a lock with `lockInterruptibly()` or `tryLock()`, only call `unlock()` if the lock was actually acquired. `ReentrantLock` offers extra features compared to `synchronized` (such as timed/non-blocking lock attempts, interruptible waiting, and `Condition`), but it does not provide automatic business-domain transactions.

## 10. Places That Can Fail While Holding a Lock

Do not look only for explicit `throw` statements written in the method; exceptions can arise at:

| Location | Failure possibility | Risk mitigation |
|---|---|---|
| Calling `Math.addExact`/`subtractExact` | `ArithmeticException` due to overflow | Pre-compute into local variables |
| Collection operations | `NullPointerException`, `IllegalArgumentException`, structural modification, or allocation failure | Copy data, validate everything, apply to a temporary copy |
| `new`, data structure creation | Allocation failure, constructor throwing an exception | Prepare new objects before swapping live references |
| Setters, listeners, or callbacks | Can throw exceptions or mutate state back | Minimize callbacks inside the commit region; define state clearly when a callback fails |
| File/database/network writes | `IOException`, timeouts, service errors; may have side effects | Separate transactions from external operations; define compensation or idempotency |
| Logging, event notifications | Logger/appender/listener can fail | Do not let secondary errors mask the primary error or obscure commit status |
| Retry mechanisms | May re-execute already completed work | Design idempotency and track progress according to contract |

If a method is written as:

~~~java
synchronized (lock) {
    decrementInventory();
    sendPaymentRequest();
    saveOrder();
}
~~~

then the lock only coordinates Java threads using the `lock` monitor. It does **not** turn the three calls into a transaction and does not make the payment provider refund money if `saveOrder()` fails. When failures involve external services, even the question "did the other side already process it?" sometimes cannot be answered solely from the exception received by the client.

## 11. `wait`, `notify`, and Temporary Invariants

This is an important case because the rule "while inside `synchronized`, the lock is always held until the end of the block" has an exception for **`Object.wait()`**.

Example of a method waiting on a condition:

~~~java
// Snippet using lock, ready, and currentValue declared elsewhere.
synchronized (lock) {
    while (!ready) {
        lock.wait(); // Temporarily releases the lock monitor while waiting.
    }
    use(currentValue);
}
~~~

`wait()` may only be called when the thread holds the monitor of `lock`; otherwise, `IllegalMonitorStateException` can occur. While waiting, the thread releases the corresponding monitor so another thread can update `ready` and notify. Before `wait()` returns (including when interrupted and throwing `InterruptedException`), the thread must re-acquire that monitor.

Because another thread may change the condition, always re-check the condition in a **`while` loop**; never assume that waking up means the data satisfies the condition. Java allows *spurious wakeups*; `notify` also does not guarantee that the business condition has become true.

**Relation to invariants:** before actually entering the wait state and releasing the monitor, shared data structures must be in a state that other threads are allowed to observe. If you modify half of a structure and then call `wait()`, another thread can acquire the monitor and see half-finished data. You should also avoid holding other monitors that could inadvertently cause deadlocks while waiting.

## 12. Preserving Invariants Across Multiple Objects or Locks

Suppose there are two different `Account` objects:

~~~java
// Illustrative code showing conditions insufficient for safety.
synchronized (source) {
    source.debit(amount);
}
synchronized (destination) {
    destination.credit(amount);
}
~~~

The two blocks use two different monitors and have a gap between them. If crediting the destination account fails, the debit on the source remains. Even when nesting the two locks:

~~~java
// Illustrative code: only shows holding both locks together, does not guarantee rollback.
synchronized (source) {
    synchronized (destination) {
        source.debit(amount);
        destination.credit(amount);
    }
}
~~~

an exception from `credit` can still leave the source debited. Furthermore, if another thread locks `destination` then `source`, the program risks deadlock due to reversed lock ordering.

To design a reliable transfer operation, consider all of the following together:

1. Locks/transactions cover **all** parts of the state that must change together.
2. Check sufficient funds and destination account conditions under the same state-protection mechanism.
3. Pre-compute results, check for overflow, and run all expected error checks before commit.
4. Choose a commit point or rollback mechanism where readers cannot see out-of-contract intermediate states.
5. Define a consistent lock-acquisition order if multiple locks must be acquired; consider DB transactions for persistent data.
6. Do not assume systems outside the JVM or outside the local transaction are controlled by Java monitors.

Note: the principle of **protecting with the same monitor** is only effective when every path that reads or mutates the relevant state obeys it. An unsynchronized getter or one that directly returns a mutable internal list can expose intermediate state; `synchronized` on the writer does not lock that getter.

## 13. Designing Exception APIs and Appropriate Rollback

API documentation should clearly state both **the conditions for throwing exceptions** and **the state after failure**. Different phrasings carry different meanings:

- "If `amount` is invalid, throws `IllegalArgumentException` and leaves balances unchanged": a clear guarantee for input validation errors.
- "If the operation fails, the object still satisfies all invariants, but earlier partial updates may remain in effect": basic guarantee.
- "If the operation fails before commit, no state changes are published": strong guarantee within the pre-commit scope.
- "If sending the payment request fails, payment processing status may require reconciliation": avoids promising rollback when network errors leave external system state uncertain.

If actively rolling back in `catch`, account for the possibility that rollback itself can fail. For example, rolling back by "adding back the deducted amount" does not always accurately reverse other updates or concurrent interactions. Integrity must be reasoned about across multiple exception types, including exceptions from cleanup. `try-with-resources` has a mechanism to record certain resource-closing errors via `getSuppressed()`, but it does not automatically roll back business data.

For `InterruptedException`, never arbitrarily swallow the cancellation signal just to "reach the end of `synchronized`". If it should propagate, declare `throws InterruptedException`; if caught and converted to unchecked in an appropriate context, consider restoring the interrupt flag with `Thread.currentThread().interrupt()` and preserving `cause`. Whichever choice is made, invariants must be maintained on that exit path.

## 14. Common Misconceptions and How to Fix Them

1. **"With `synchronized`, errors will roll back automatically."** False: locks manage monitors. Fix this by designing validate → prepare → commit, immutable snapshots, or transactions.
2. **"Throwing an exception inside `synchronized` will leave the lock stuck."** False when the exception causes the synchronized region to exit; the JVM releases the monitor. Actual stalls come from deadlocks, infinite wait loops, or code that has not exited the synchronized region.
3. **"If the next thread acquires the lock, the data is definitely valid."** False: the next thread can read a fully published invalid state.
4. **"Just `catch` and `return` and everything is restored."** False: you must verify all invariants after the error-handling branch.
5. **"Putting `finally` inside `synchronized` rolls back automatically."** False: `finally` runs the code you write; without proper rollback or cleanup logic, it does not undo anything on its own.
6. **"Two assignments inside a `synchronized` method are always atomic to all readers."** Only true in the sense that readers coordinating via the **same monitor** cannot enter the synchronized region mid-way; uncoordinated read paths can still observe inconsistent data.
7. **"`volatile` can replace `synchronized` for updating multiple fields."** False: field visibility does not turn multiple assignments into a transaction.
8. **"`wait()` is inside `synchronized`, so other threads cannot enter."** False: `wait()` temporarily releases the monitor of the waited-on object.
9. **"A DB transaction means accompanying emails/payments also roll back."** False: side effects outside the transaction boundary require separate mechanisms.
10. **"Every error can be recovered by inverse assignment."** False when there are side effects, callbacks, concurrently mutated data, or when the original state is no longer intact.

## 15. Testing Both Access Control and Invariants Properly

A good test suite must verify **two independent categories**, because passing one does not imply the other.

| Category | Scenario | Expected result |
|---|---|---|
| Monitor | A `synchronized` method throws `RuntimeException`; another thread calls a method on the same monitor afterward | The next thread enters the synchronized region without being blocked by a stuck lock |
| Invariant | An exception occurs after the first update | Evaluate whether the invariant is violated; for a strong contract, the state must remain intact |
| Input | Negative amount, exceeding balance, null parameter | Throws the expected error type before any modification |
| Overflow | Total balance or version counter exceeds `long`/`int` limits | Does not commit invalid values; exception propagates properly |
| Snapshot | Error while constructing the proposed state | The active state remains unchanged |
| Concurrency | Two threads concurrently request changes using the same lock/CAS mechanism | No lost updates, no broken invariants |
| Visibility | Readers synchronized or unsynchronized per contract | Evaluate cases of reading intermediate state |
| Wait | Wait condition changes or spurious wakeup occurs | `while` re-checks the condition; invariants remain valid |
| Side effect | I/O, DB, or callback fails after a successful step | Documentation and behavior agree on whether rollback is possible |

In `SynchronizedInvariantDemo`, the "Unsafe observer" output both proves **the monitor was released** and shows **the invariant was broken**. A test that only checks `assertThrows` or only checks that the observer thread does not hang would miss the data bug.

Note that a concurrency test passing a few times does not prove the absence of races or deadlocks. You must reason about held monitors, acquisition/release timing, all read/write paths, the point of commit, and exception paths; tests confirm that reasoning with concrete scenarios.

## 16. Checklist for Reviewing a `synchronized` Method

When reading code with mutable state and exception handling, apply these questions in order:

1. **Which monitor is acquired?** `this`, `Class`, or a dedicated lock object? Do related methods use the same monitor?
2. **What are the invariants?** Write them as concrete assertions: totals, value ranges, relationships between fields, valid object conditions.
3. **Where is the first point that mutates live state?** Mark every assignment, collection mutation, or side effect.
4. **After each mutation point, which statements can throw an exception?** Arithmetic, callbacks, I/O, allocations, logging, and helper calls.
5. **If execution exits right at that point, do invariants still hold?** If not, reorder operations or prepare the new state before committing.
6. **Can readers observe intermediate state?** Consider the same monitor, uncoordinated readers, mutable snapshots, `wait()`, and other resources.
7. **How far does rollback actually reach?** JVM objects differ from DB transactions and network calls; clearly define non-reversible paths.
8. **Is the failure contract documented in the API?** Exception types, `cause`, failure guarantee level, and how callers recover.
9. **Do tests inject failures at the sensitive steps?** Trigger failures before commit, during preparation, and after side effects; check both state and subsequent monitor acquisition.

## 17. Key Takeaways

- `synchronized` causes the JVM to automatically release the monitor on normal or exceptional exit from the synchronized region. This rule **does not automatically undo assignments or side effects**.
- Releasing the monitor provides a coordination point and *happens-before* ordering for another thread acquiring the same monitor; that thread can still observe invalid data if the previous thread left an invariant broken.
- Keeping data valid after a failed operation must be designed through pre-validation, preparing new data, defining a commit point, synchronizing with the right scope, and using transactions/rollback when needed.
- `catch`/`finally` alter the error-handling flow; they do not replace proof that every exit branch preserves state.
- When evaluating a method, always ask **two separate questions**: "Does an exception release the lock?" and "Is the data read by the next thread still valid?"

### Java Standard References

- [JLS §14.19 — The synchronized Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19)
- [JLS §17.1 — Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1)
- [JLS §17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)
- [Java SE 17 — `Object.wait()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#wait())
- [Java SE 17 — `ReentrantLock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
