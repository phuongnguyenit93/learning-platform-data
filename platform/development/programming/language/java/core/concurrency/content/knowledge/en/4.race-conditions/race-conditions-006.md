# Broken Invariant When Updating Multiple Related Variables in Java Concurrency

## 1. The problem: each variable is valid, but the overall state is wrong

An object can contain multiple fields whose **business meaning is only valid when those fields satisfy a relationship with one another**. That required relationship is called an **invariant**.

For example, consider a ledger with two balances:

- `left = 70`, `right = 30`;
- the total amount must always equal `100`;
- transferring `20` from `left` to `right` must transition the state `(70, 30)` to `(50, 50)`.

The invariant here is:

```text
left >= 0
right >= 0
left + right == 100
```

If the code executes two assignments sequentially:

```java
left -= 20;  // Intermediate state: left=50, right=30
right += 20; // Final state: left=50, right=50
```

then after the first assignment, the total is temporarily `80`. When two threads run concurrently, **a reader can observe the intermediate state** `(50, 30)` and see that the total is no longer `100`. This is the phenomenon of a **broken invariant when updating multiple related variables**.

Other familiar examples:

| Related data | Invariant to maintain | Invalid state that may be observed |
| --- | --- | --- |
| `start` and `end` | `start <= end` | Reader sees the new `start` and old `end`, resulting in `start > end` |
| `used` and `capacity` | `0 <= used <= capacity` | Increasing `used` before increasing `capacity` causes `used > capacity` |
| `items` and `itemCount` | `itemCount == items.size()` | The list has changed, but the count has not yet been updated |
| `debit` and `credit` | Total debits/credits of a transaction balance | Reader sees only one side of the transaction |
| `configVersion` and `configData` | Data matches the corresponding version | Reading the new version with old data |

The core issue is not the `+=` or `-=` syntax. Even if **each read/write of a single field is atomic**, reading/writing **a group of multiple fields** is still not necessarily atomic. The system needs a mechanism that ensures other threads only observe **consistent states**.

## 2. What is an invariant-related race condition?

A **race condition** occurs when the outcome or correctness depends on uncontrolled interleaving between concurrent operations. With a multi-field invariant, the following sequence causes a bug:

```text
Initial state: left=70, right=30, total=100

Writer thread                          Reader thread
----------------------------           -----------------------------
left = 50
                                       read left  -> 50
                                       read right -> 30
                                       compute total -> 80 (WRONG)
right = 50

Final state: left=50, right=50, total=100
```

Looking at each assignment individually, no value is "half-written". However, **the reader has observed a combination that was never published as a complete transaction**.

Three concepts need to be distinguished:

1. **Per-field atomicity**: a single read/write operation may be atomic under the Java Memory Model, but that does not make the entire sequence `left -= amount; right += amount` a single atomic operation.
2. **Visibility**: when a writer writes, is a reader guaranteed to observe the update? `volatile`, monitors, or atomic variables provide specific memory ordering and visibility guarantees.
3. **Consistency**: do the values a reader observes belong together to **a single valid state**? This is a stronger requirement than per-field visibility.

For example, the reader accurately sees `left = 50` and `right = 30`. Both reads may be performed "correctly" with respect to each individual value, yet the overall snapshot is still wrong.

## 3. Runnable demonstration: per-field `volatile` still suffers from broken invariants

The example below uses two `volatile` fields and `CountDownLatch` to intentionally pause the writer **between the two updates**. This demonstrates an inconsistent snapshot deterministically without relying on scheduler luck.

Create the file `BrokenInvariantDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class BrokenInvariantDemo {
    private static final class Balances {
        volatile int left = 70;
        volatile int right = 30;
    }

    public static void main(String[] args) throws InterruptedException {
        Balances balances = new Balances();
        CountDownLatch firstWriteDone = new CountDownLatch(1);
        CountDownLatch allowSecondWrite = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            balances.left -= 20;
            firstWriteDone.countDown();

            try {
                allowSecondWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            balances.right += 20;
        }, "writer");

        writer.start();
        firstWriteDone.await();

        System.out.println("Trong lúc cập nhật: "
                + balances.left + " + " + balances.right
                + " = " + (balances.left + balances.right));

        allowSecondWrite.countDown();
        writer.join();

        System.out.println("Sau khi cập nhật: "
                + balances.left + " + " + balances.right
                + " = " + (balances.left + balances.right));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac BrokenInvariantDemo.java
java BrokenInvariantDemo
```

Output when there is no external interrupt request:

```text
Trong lúc cập nhật: 50 + 30 = 80
Sau khi cập nhật: 50 + 50 = 100
```

**Explanation by event order:**

1. The writer updates `left` from `70` to `50`.
2. `firstWriteDone.countDown()` notifies `main` that the first write has completed. `main` wakes up from `await()`.
3. The writer waits at `allowSecondWrite.await()`, so it **cannot update `right` yet**.
4. `main` reads `(left, right) = (50, 30)`. The total `80` violates the invariant `left + right == 100`.
5. `main` signals the writer and waits for `join()`; after the worker finishes, the balance pair is `(50, 50)` and the total returns to `100`.

The two latches establish the necessary *happens-before* relationships; therefore, the bug is not merely caused by caching or reading stale data. `volatile` forces individual field accesses to obey volatile visibility and ordering guarantees, **but it does not combine two fields into a single atomic update**.

**Note:** `balances.left -= 20` and `balances.right += 20` are read-modify-write operations, which are also non-atomic when there are multiple writers. This example intentionally uses only one writer to clearly separate the **multi-field snapshot** bug from the **lost update** bug caused by multiple writers.

The example blocks the writer from continuing to demonstrate the bug deterministically. In a real system, the two writes may occur very close together, yet a reader interleaving in between **can still happen**; "running it many times without seeing an error" is not proof of safety.

## 4. How is a broken invariant different from a lost update?

These two bugs often appear near each other, but they must be addressed at the right level:

**Lost update** occurs when multiple writers compete to update the same value. For example, two threads both execute `counter++`, both read `10`, and ultimately only `11` is stored instead of `12`. An `AtomicInteger.incrementAndGet()` or an appropriate lock can fix that individual increment operation.

**Multi-field broken invariant** occurs when a valid state requires **multiple values to change as a single logical unit**. Even if two independent fields are stored as `AtomicInteger`, a reader can still observe that `left` has been subtracted while `right` has not yet been added. The two operations:

```java
left.addAndGet(-20);
right.addAndGet(20);
```

are still **two separate atomic operations**. `AtomicInteger` prevents lost updates on each individual field (when used consistently), but it does not turn them into a multi-field transaction.

For applications that need to update multiple related values, always ask: **"Is the unit of consistency to protect each individual value or the entire set of values?"** If the requirement is the entire set, the synchronization mechanism must cover both updating and reading snapshots.

## 5. Fixing with `synchronized`: the same monitor protects both updates and reads

A straightforward and verifiable solution is to use **a single monitor** for both the transfer operation and the snapshot-reading operation. When a writer enters `synchronized`, a reader needing the same monitor must wait until the writer exits the protected region.

Two mandatory conditions:

- **Writers** must update the entire group of related fields inside a protected region.
- **Readers** must read the entire group of fields inside a region protected **by the same monitor**.

Locking only the writer while letting readers read fields freely can still expose intermediate states. Locking only the reader while the writer does not follow the same mechanism also fails to protect the invariant.

Create the file `SynchronizedInvariantDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class SynchronizedInvariantDemo {
    private static final class Ledger {
        private int left = 70;
        private int right = 30;

        synchronized void transferLeftToRight(int amount) {
            if (amount < 0 || amount > left) {
                throw new IllegalArgumentException("invalid transfer");
            }
            left -= amount;
            right += amount;
        }

        synchronized void transferRightToLeft(int amount) {
            if (amount < 0 || amount > right) {
                throw new IllegalArgumentException("invalid transfer");
            }
            right -= amount;
            left += amount;
        }

        synchronized int total() {
            return left + right;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();
        CountDownLatch start = new CountDownLatch(1);
        AtomicBoolean invariantBroken = new AtomicBoolean(false);

        Thread writer = new Thread(() -> {
            try {
                start.await();
                for (int i = 0; i < 10_000; i++) {
                    ledger.transferLeftToRight(1);
                    ledger.transferRightToLeft(1);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "writer");

        Thread reader = new Thread(() -> {
            try {
                start.await();
                for (int i = 0; i < 10_000; i++) {
                    if (ledger.total() != 100) {
                        invariantBroken.set(true);
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "reader");

        writer.start();
        reader.start();
        start.countDown();

        writer.join();
        reader.join();

        System.out.println("Broken: " + invariantBroken.get());
        System.out.println("Final total: " + ledger.total());
    }
}
```

```bash
javac SynchronizedInvariantDemo.java
java SynchronizedInvariantDemo
```

Output when the threads are not interrupted:

```text
Broken: false
Final total: 100
```

Each transfer operation updates both fields while holding `Ledger`'s monitor. `total()` acquires **that exact same monitor**, so it cannot read between the two updates inside a `transfer...()` call. The program may interleave calls between the writer and reader, but every total value read is valid. `AtomicBoolean` is only used to safely pass the check result from the reader to `main`; it is **not** the primary mechanism protecting the two balances.

Implementing with `synchronized` has these characteristics:

- `volatile` is not needed for the fields if **every access** is consistently protected by this monitor.
- A monitor provides mutual exclusion: at any given time, one thread holds the monitor, and another thread wanting to acquire it must wait.
- When the monitor is released and another thread acquires the same monitor, the Java Memory Model provides a *happens-before* relationship for data visibility.
- Validation must reside in **the same locked region** as the update. If `amount <= left` is checked outside the lock, `left` could change before the transaction executes.
- Do not return a reference to an internal object that can be freely mutated outside the lock. Return an immutable snapshot or copied values.

### Why shouldn't a reader read each field using two independent synchronized getters?

Suppose both `getLeft()` and `getRight()` are `synchronized`, and the caller does:

```java
int a = ledger.getLeft();
int b = ledger.getRight();
```

This is an illustrative snippet (not a complete program). The lock is released after `getLeft()`, so a writer can transfer funds **between the two getter calls**. In that case, the caller combines `a` from the old state with `b` from the new state, producing a wrong total even though **each getter individually is thread-safe**.

The right approach is to provide **a snapshot method** that reads both fields within the same critical section:

```java
record Balances(int left, int right) {}

synchronized Balances snapshot() {
    return new Balances(left, right);
}
```

This snippet illustrates a method placed **inside the class holding the `left/right` fields**; `record Balances` is an immutable data type defined outside the method. `record` requires Java 16+ and fits Java 17+. The caller receives a pair of values belonging to the same point in time protected by the lock. After the lock is released, the snapshot remains unchanged even as the underlying data continues to be updated.

## 6. Fixing with an atomically published immutable snapshot

Another approach is **not to update public/mutable fields one by one**. Instead:

1. Read the current immutable state.
2. Compute the entire next state in local memory.
3. Validate invariants on the new state.
4. Publish **a single reference** to the new state using an appropriate atomic/volatile mechanism.

The reader simply grabs **one snapshot reference** and accesses the fields of that same snapshot. Because the snapshot object is immutable, the reader cannot observe a partial update inside it.

### Example with `AtomicReference` and `record`

Create the file `AtomicSnapshotDemo.java` (Java 17+):

```java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicSnapshotDemo {
    record Balances(int left, int right) {
        Balances {
            if (left < 0 || right < 0 || left + right != 100) {
                throw new IllegalArgumentException("broken invariant");
            }
        }

        int total() {
            return left + right;
        }
    }

    public static void main(String[] args) {
        AtomicReference<Balances> state =
                new AtomicReference<>(new Balances(70, 30));

        state.updateAndGet(current ->
                new Balances(current.left() - 20, current.right() + 20));

        Balances snapshot = state.get();
        System.out.println("left=" + snapshot.left());
        System.out.println("right=" + snapshot.right());
        System.out.println("total=" + snapshot.total());
    }
}
```

```bash
javac AtomicSnapshotDemo.java
java AtomicSnapshotDemo
```

Output:

```text
left=50
right=50
total=100
```

`record Balances` creates an immutable value representing **the entire pair**. The constructor validates the state before a valid object is published. `AtomicReference.updateAndGet` performs an atomic reference update; if multiple writers contend, the function computing the next state may be invoked multiple times. Therefore, the update lambda must have **no side effects** such as sending emails, writing non-repeatable business logs, or calling external systems.

Note: replacing a `volatile Balances snapshot` reference can also provide atomic publication **for a single writer** if the writer constructs a complete new state and assigns it to the volatile field. However, if multiple writers concurrently read the old state and each assigns a new state, one update can overwrite the result of another. `AtomicReference` with CAS/retry solves that update contention at the reference level when all writers follow the proper protocol.

**Reading pitfall:** do not do this when a consistent snapshot is needed:

```java
int a = state.get().left();
int b = state.get().right();
```

Two calls to `state.get()` can return two different snapshot generations if a writer publishes an update between them. Even though each snapshot is valid on its own, combining two fields from two different snapshots can still be wrong. Fetch `Balances snapshot = state.get();` **once**, then read `snapshot.left()` and `snapshot.right()`.

## 7. What about `ReentrantLock` or `ReadWriteLock`?

`ReentrantLock` can protect the same invariant as `synchronized` if all readers and writers follow the locking protocol. Its advantages include support for try-lock, timeouts, `Condition` mechanisms, and interruptible lock acquisition while waiting.

Basic pattern:

```java
lock.lock();
try {
    validateTransfer();
    updateAllRelatedFields();
} finally {
    lock.unlock();
}
```

This is **illustrative code**, where `lock` is a `ReentrantLock` and the two methods represent application logic. Snapshot-reading methods must also acquire **the same lock**; locking writes while leaving reads unlocked is still unsafe. Always unlock in `finally`.

`ReentrantReadWriteLock` allows multiple readers to hold the read lock concurrently while only one writer holds the write lock. It can be useful when reads are frequent, writes are rare, and the critical section has significant cost; however, it adds complexity and is not automatically faster than `synchronized`. Do not switch lock types based solely on a short microbenchmark.

Regardless of the lock used, the invariant requirement remains the same: a logical update must be executed and observed as **a single consistent unit**.

## 8. Simply adding `volatile` or individual `AtomicInteger`s does not work

### 8.1. What does `volatile` solve?

A `volatile` field provides visibility and ordering guarantees under the Java Memory Model. For instance, another thread reading the same volatile field can see the published value in accordance with synchronization order. However, two fields:

```java
volatile int left;
volatile int right;
```

do not form a "volatile pair". A reader can still observe the new `left` and the old `right`. That is precisely what `BrokenInvariantDemo` demonstrates.

Similarly, a `volatile boolean ready` only signals that state has been published **if the writer/reader protocol is designed properly**—for example, the writer writes all data, then sets `ready = true`, and the reader only reads after seeing the flag. It does not by itself prevent the writer from continuing to update multiple fields while the reader is reading, nor does it replace synchronization when there are multiple updates or multiple writers.

### 8.2. Why is making each field atomic still not enough?

`AtomicInteger left` and `AtomicInteger right` protect individual updates. However, a reader calling `left.get()` followed by `right.get()` can still see data from two different points in time. There is no shared `getBothAtomically()` operation across two independent `AtomicInteger`s.

To guarantee a consistent snapshot, use the same monitor around both updates and reads, or group the state into an immutable object and atomically update the reference.

### 8.3. Locking the writer without locking the reader

```java
synchronized (lock) {
    left -= amount;
    right += amount;
}
// In another thread:
int total = left + right; // Reading outside the lock: no consistent snapshot.
```

The lines above illustrate two different execution contexts. With regular (`non-volatile`) fields, reading outside the lock also lacks visibility guarantees and creates a data race. Even if both fields are changed to `volatile`, unlocked reading still risks a broken invariant. **Both sides of the protocol must agree**.

### 8.4. Locking each assignment individually

```java
synchronized (lock) {
    left -= amount;
}
synchronized (lock) {
    right += amount;
}
```

Each assignment is protected, but the lock is released **in between**, giving readers a window to enter and observe an invalid state. The lock must span **the entire group of related changes**, not just individual operations.

## 9. Exceptions, validation, and invariants inside the critical section

A `synchronized` block does not automatically "roll back" state when code throws an exception. If a writer updates the first field and then a second computation or API call throws an error, the writer exits the locked region and releases the monitor—**an invalid state may become permanently visible**.

Dangerous example:

```java
synchronized (lock) {
    left -= amount;        // Already modified.
    checkExternalRule();   // If this throws an exception...
    right += amount;       // ...this never runs.
}
```

The snippet above is illustrative code. To avoid this, **validate every checkable condition before starting to publish changes**, compute target values using local variables, and only commit the entire group of fields once the new state is known to be valid:

```java
synchronized (lock) {
    if (amount < 0 || amount > left) {
        throw new IllegalArgumentException("invalid amount");
    }

    int nextLeft = Math.subtractExact(left, amount);
    int nextRight = Math.addExact(right, amount);

    if (nextLeft < 0 || nextRight < 0) {
        throw new IllegalStateException("invalid balance");
    }

    left = nextLeft;
    right = nextRight;
}
```

This is an illustrative snippet inside a method of the object owning `left`, `right`, and `lock`. `Math.subtractExact` and `Math.addExact` detect overflow instead of silently wrapping around. All checks and calculations that can throw exceptions happen **before the two assignments**, so if an error occurs, neither field changes. The final two assignments still have an internal intermediate state, but when all readers acquire the same lock, that state cannot be observed by other threads under this protocol.

If a transaction must call an external service, write to a file, or emit an event, consider the atomicity of **the entire system**; `synchronized` only coordinates threads within the JVM and does not roll back external resources.

## 10. Relationship to the Java Memory Model

The Java Memory Model (JMM) defines the rules that determine which operations have ordering and visibility guarantees across threads. For multi-field invariants, several key principles apply:

- **Happens-before**: releasing a monitor happens-before a subsequent acquisition of the same monitor; thus a reader acquiring the same monitor will observe the necessary writes completed by the writer.
- **Volatile**: guarantees visibility/ordering at the level of volatile operations, but does not automatically create a "transaction" across multiple variables.
- **AtomicReference**: can publish an immutable snapshot as a single atomic reference update; if a reader fetches the reference **once**, it reads all fields from the same snapshot.
- **Thread.start / Thread.join**: establish certain happens-before relationships, useful when handing off state before or after a worker runs. However, if a reader and writer are actually running concurrently, `join()` does not protect reads occurring between the writer's two assignments.

Another way to express this is **linearizability**: from the perspective of concurrent callers, a transfer operation should appear to take effect at a **single commit point**. When `transfer` and `snapshot` are protected by the same monitor, those calls can be ordered into valid states. When using an immutable snapshot + atomic CAS, the point of reference publication is the state transition point.

**Do not confuse linearizability of an operation on a Java object with distributed transaction atomicity**. If an operation modifies RAM while also requiring a bank, network service, or another database to update, those systems require their own transaction/compensation mechanisms.

## 11. Designing APIs that are hard to misuse

Several practices help keep invariants intact by design:

1. **Encapsulate related fields** in a class such as `Ledger`. Never let callers modify `left` or `right` directly.
2. **State invariants explicitly**: for example, "every published snapshot must have the correct total amount and non-negative balances".
3. **Expose business operations** like `transfer(amount)` instead of letting callers invoke `setLeft()` and then `setRight()`.
4. **Expose a complete snapshot** rather than two getters read at different times when callers need to compute relationships between them.
5. **Use a consistent synchronization strategy**. This does not mean using one global lock for the entire system; a lock should protect the exact group of data sharing an invariant.
6. **Validate errors before committing** and ensure exceptions never leave behind an invalid published state.
7. **Test with controlled schedules** (latches/barriers) to actively expose race conditions, then supplement with stress tests when needed. Stress testing does not replace reasoning about correctness.

Choose a solution based on the scope of data ownership: a shared object inside the JVM can use a monitor, a small immutable state with many readers can use `AtomicReference`, while resources outside the JVM require the consistency mechanisms of that storage or communication layer.

## 12. Diagnosing suspected broken invariants

If you see mismatched totals, `start/end` pairs, configuration versions, or item counts in logs, check in this order:

- **What is the invariant?** Write it as an evaluable predicate: `left + right == 100`, `version == payload.version()`, etc.
- **How many fields must change together?** Trace the writes in execution order and list the intermediate states.
- **Who reads those fields?** Do readers call separate getters? Do they hold the same monitor? Do they dereference a mutable reference multiple times?
- **Do all writers follow the same protocol?** A single update path bypassing the lock is enough to create a hole.
- **Can an exception occur mid-update?** Does the code compute the entire new state before committing?
- **Are multiple writers contending?** If so, a volatile assignment or a single pair of atomics will not solve lost updates.
- **Are there boundaries outside the JVM?** Java locks only protect threads using that same lock; you cannot lock another process simply by creating `new Object()`.

Distinguish between logs collected at two different times (e.g., logging `left` before and `right` after an update) and the actual snapshot used by the program. If you want consistent overall logs, log a complete snapshot read under the same synchronization protocol.

## 13. Self-check exercises

**Scenario A.** Two fields `volatile int min`, `volatile int max` must satisfy `min <= max`. A writer updates `min = 8` then `max = 10` from state `(1, 5)`. Can a reader see `min=8,max=5`?

**Answer:** Yes. Individual volatile fields do not combine two writes into a single operation. If the invariant must always hold for readers, you must synchronize the update group and the read group, or publish an immutable snapshot `(8,10)`.

**Scenario B.** `left` and `right` are both `AtomicInteger`. A writer calls `left.addAndGet(-20)` then `right.addAndGet(20)`. Is the sum invariant guaranteed?

**Answer:** No. Each individual add/subtract is atomic, but there is an interval between them where the sum is skewed. Group the data and protect the transaction/snapshot as a single logical unit.

**Scenario C.** A writer performs both updates inside `synchronized(lock)`, while a reader calls two getters that are each individually `synchronized(lock)`. Can the reader see two different generations?

**Answer:** Yes. The monitor is released between the two getters; the writer can update in that gap. You need a `snapshot()` getter that reads both under **a single lock acquisition**.

**Scenario D.** A writer acquires the lock properly and validates initial inputs, but after assigning `left`, an external function throws an exception. Does the lock automatically roll back `left`?

**Answer:** No. The monitor is still released when exiting via exception, but it does not undo writes that already occurred. Compute and validate before committing; avoid performing external operations that might fail between related state assignments.

**Scenario E.** `AtomicReference<Balances>` holds an immutable record. A reader calls `state.get().left()` and `state.get().right()` at two points. Is a consistent snapshot guaranteed?

**Answer:** No. The two `get()` calls can return two different records. Store `Balances snapshot = state.get();` in a local variable and read all fields from that variable.

**Scenario F.** When can an invariant be temporarily violated inside `synchronized` while the API still guarantees callers only see valid states?

**Answer:** When every observation of the related state must acquire the same monitor, there are no callbacks or state leaks mid-operation, and every exit path (including exceptions) only exposes a valid state. Readers cannot interleave between assignments while the writer holds the monitor; however, it is still best to compute and validate before assigning to avoid leaving invalid state behind on error.

## 14. Summary

A **broken invariant when updating multiple related variables** happens because a single logical change is implemented as multiple reads/writes, allowing other threads to observe a combination of values that does not belong to a valid state. Correct individual assignments, individual `volatile` fields, or individual `AtomicInteger`s **do not guarantee** consistency across the entire group of fields.

There are two common fixes in Java: **lock both the update operations and snapshot reads with the same monitor/lock**, or **create an immutable snapshot and atomically publish the reference to that snapshot**. Before committing, validate inputs, handle potential exceptions, and ensure all writers and readers follow the same protocol. Protect **the object's invariant as a single unit**, rather than protecting individual variables in isolation.
