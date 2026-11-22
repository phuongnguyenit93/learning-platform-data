# compareAndSet() and CAS Principles in Java

## 1. The Problem CAS Solves

In multithreaded programming, two threads can update the same value concurrently. The expression `counter++` actually requires reading the old value, computing `+1`, and writing the result. These steps can interleave:

```text
Initially counter = 10
Thread A: read 10             Thread B: read 10
Thread A: compute 11          Thread B: compute 11
Thread A: write 11            Thread B: write 11
Finally counter = 11, even though two increments were requested.
```

This is a **lost update**. `volatile` on a field guarantees visibility and memory ordering, but **does not turn a read-modify-write into an atomic operation**. To fix this properly, a protocol is needed that detects whether "someone else changed the value before I wrote."

**Compare-And-Set (CAS)** is a conditional atomic operation: **replace the current value with the new value only if the current value still matches the expected value**. In the Java standard library, classes such as `AtomicInteger`, `AtomicLong`, `AtomicBoolean`, and `AtomicReference` support the `compareAndSet(expected, update)` method.

Pseudocode:

```text
CAS(expected, update):
    if current matches expected:
        current = update
        return true
    else:
        keep current unchanged
        return false
```

The crucial point is that **comparison and replacement form a single uninterruptible operation**. Writing a regular `if` on an unsynchronized field does not create a CAS.

This article covers **general Java concurrency** only, without depending on any specific framework.

## 2. Meaning of the Boolean Result

- `true`: expected matched the current value at the CAS point; the update **is committed**.
- `false`: for **strong CAS `compareAndSet`**, expected did not match on this attempt; `update` **was not written**.
- There is no "CAS auto-retries" behavior in a single `compareAndSet` call. The API caller must decide whether to retry, reject, or handle the conflict.
- When using `AtomicReference<T>`, matching expected is checked by **reference identity (`==`)**, not `equals()`.
- For integer atomic types, expected is compared by primitive value.

### Example 1: Succeeding and Failing Calls

Create `CasBasicsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class CasBasicsDemo {
    public static void main(String[] args) {
        AtomicInteger number = new AtomicInteger(10);

        boolean a = number.compareAndSet(10, 11);
        boolean b = number.compareAndSet(10, 12);
        boolean c = number.compareAndSet(11, 20);

        System.out.println("a=" + a);
        System.out.println("b=" + b);
        System.out.println("c=" + c);
        System.out.println("value=" + number.get());
    }
}
```

```bash
javac CasBasicsDemo.java
java CasBasicsDemo
```

Output:

```text
a=true
b=false
c=true
value=20
```

The first call `10 -> 11` succeeds. The second call still expects `10`, so it fails and keeps `11`. The last call expects `11`, so it succeeds and writes `20`.

In a multithreaded program, the reason expected becomes "stale" is usually that another thread updated the value between calling `get()` and calling CAS.

## 3. Multiple Threads Competing for CAS: Only One Winner per Expected Value

Suppose two threads both read `0` and both call `compareAndSet(0, 1)`. Once one CAS succeeds, the value becomes `1`; the other CAS with expected `0` must fail unless some update sets the value back to `0`. To verify this without depending on which thread the CPU schedules first, use latches.

Create `CasOneWinnerDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class CasOneWinnerDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger value = new AtomicInteger(0);
        AtomicInteger wins = new AtomicInteger(0);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);

        Runnable task = () -> {
            int expected = value.get();
            bothRead.countDown();
            try {
                go.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            if (value.compareAndSet(expected, expected + 1)) {
                wins.incrementAndGet();
            }
        };

        Thread a = new Thread(task, "A");
        Thread b = new Thread(task, "B");
        a.start();
        b.start();
        bothRead.await();
        go.countDown();
        a.join();
        b.join();

        System.out.println("wins=" + wins.get());
        System.out.println("value=" + value.get());
    }
}
```

```bash
javac CasOneWinnerDemo.java
java CasOneWinnerDemo
```

Output when there is no external interrupt:

```text
wins=1
value=1
```

Both threads are guaranteed to read `0` before the `go` latch is opened. One CAS changes the value to `1`; the other CAS sees a mismatched expected value. **It is impossible to predict whether A or B wins**, so the example only prints the win count. If each thread represents a **mandatory increment that must be preserved**, the failing thread must re-read and retry.

## 4. The CAS Retry Loop: Re-read, Recompute, Retry

Pattern for updating an atomic variable:

```java
while (true) {
    int before = counter.get();
    int after = before + 1;
    if (counter.compareAndSet(before, after)) {
        break;
    }
    // CAS failed: another thread may have updated counter.
    // Next iteration reads the new value and recomputes.
}
```

This is an illustrative snippet, assuming `counter` is an `AtomicInteger`. Do **not** hoist `before` outside the loop and reuse the stale expected value forever: once the value differs from expected, the loop could spin forever without succeeding.

### Example 2: Every Increment Request Is Preserved

Create `CasRetryDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class CasRetryDemo {
    static void increment(AtomicInteger value) {
        for (;;) {
            int before = value.get();
            int after = before + 1;
            if (value.compareAndSet(before, after)) {
                return;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger value = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);
        Runnable task = () -> {
            try {
                start.await();
                for (int i = 0; i < 10_000; i++) {
                    increment(value);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();
        System.out.println("value=" + value.get());
    }
}
```

```bash
javac CasRetryDemo.java
java CasRetryDemo
```

Output when there is no external interrupt:

```text
value=20000
```

Each thread increments 10,000 times. When CAS fails, it retries with the current value; no increment is dropped. `join()` ensures `main` only prints after both threads finish.

This pattern does not handle integer overflow, task cancellation, or multiple side effects. If `int` can exceed its bounds, overflow checks must be designed. If a retry loop needs to be cancellable, it should actively check the interrupt status or a cancellation token at an appropriate point.

## 5. Linearization Point and JMM

A successful CAS can be understood as having a **linearization point**—a logical instant at which the transition from expected to update takes atomic effect. This explains why two CAS operations expecting the same value cannot blindly overwrite each other like two `counter++` operations.

Standard atomic APIs also provide **memory guarantees** under the Java Memory Model (JMM). `get()`, `set()`, and `compareAndSet()` provide semantics suitable for publishing and observing data, matching the corresponding volatile operations. When one thread constructs a complete state and publishes it via an atomic reference, another thread reading that reference with `get()` has the appropriate visibility/happens-before relationship to observe the data initialized prior to publication.

However, do not overgeneralize:

- A CAS on an `atomic` does not automatically protect mutable fields of another object.
- A CAS does not replace a transaction for an operation spanning multiple separate variables or objects.
- Two consecutive successful CAS calls still have **two** linearization points; they do not combine into one atomic transaction.
- If a published object is later mutated without synchronization, reference-level atomicity will not prevent internal data races.

Reason in terms of the **unit of state that must remain consistent**, not merely the presence of an atomic API name.

## 6. `AtomicReference` Compares by Identity, Not `equals()`

With `AtomicReference<T>`, expected must be the **exact same reference** currently stored. Two objects with equal content according to `equals()` still have two distinct identities.

Create `CasReferenceIdentityDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class CasReferenceIdentityDemo {
    record State(int value) {}

    public static void main(String[] args) {
        State original = new State(5);
        State equalCopy = new State(5);
        AtomicReference<State> ref = new AtomicReference<>(original);

        System.out.println("equals=" + original.equals(equalCopy));
        System.out.println("same=" + (original == equalCopy));

        boolean wrong = ref.compareAndSet(equalCopy, new State(6));
        boolean right = ref.compareAndSet(original, new State(6));

        System.out.println("wrong=" + wrong);
        System.out.println("right=" + right);
        System.out.println("value=" + ref.get().value());
    }
}
```

```bash
javac CasReferenceIdentityDemo.java
java CasReferenceIdentityDemo
```

Output:

```text
equals=true
same=false
wrong=false
right=true
value=6
```

`State` is a record, so two records with the same value have `equals() == true`, yet they are two distinct objects. The CAS using `equalCopy` as expected fails, whereas using `original`—the reference actually held—succeeds.

The correct pattern is:

```java
State before = ref.get();
State after = new State(before.value() + 1);
boolean changed = ref.compareAndSet(before, after);
```

This is an illustrative snippet; if `changed` is `false`, you must decide whether to retry or report a conflict. Avoid constructing a new object "equal" to the current state and passing it as expected.

## 7. CAS an Immutable Snapshot to Update Multiple Related Variables

Suppose `left` and `right` are two balances whose sum must always equal `100`. Updating two `AtomicInteger` instances sequentially:

```java
left.addAndGet(-1);
right.addAndGet(1);
```

can still allow a reader to observe a sum of `99` in between the two steps. Individual atomicity on each field does not turn a group of fields into a transaction.

A suitable solution for small state is to bundle both into **an immutable record** and CAS **a single root reference**.

Create `CasSnapshotDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class CasSnapshotDemo {
    record Balances(int left, int right) {
        Balances {
            if (left < 0 || right < 0 || left + right != 100) {
                throw new IllegalArgumentException("invalid state");
            }
        }
    }

    static void transferOne(AtomicReference<Balances> ref) {
        for (;;) {
            Balances before = ref.get();
            Balances after =
                    new Balances(before.left() - 1, before.right() + 1);

            if (ref.compareAndSet(before, after)) {
                return;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Balances> state =
                new AtomicReference<>(new Balances(100, 0));

        Runnable task = () -> {
            for (int i = 0; i < 50; i++) {
                transferOne(state);
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        a.start();
        b.start();
        a.join();
        b.join();

        Balances snapshot = state.get();
        System.out.println("left=" + snapshot.left());
        System.out.println("right=" + snapshot.right());
        System.out.println("total="
                + (snapshot.left() + snapshot.right()));
    }
}
```

```bash
javac CasSnapshotDemo.java
java CasSnapshotDemo
```

Output:

```text
left=0
right=100
total=100
```

Each of the two threads performs 50 transfers of one unit, and all must commit. Each CAS iteration constructs a complete, valid record; under contention, the loop fetches the new record and recomputes. No record is mutated in place.

**A reader must fetch a single reference** when multiple fields from the same version are needed:

```java
Balances snapshot = state.get();
int left = snapshot.left();
int right = snapshot.right();
```

This snippet uses `state` from the example above. Calling `state.get().left()` and `state.get().right()` **as two separate calls** allows a writer to swap the snapshot in between, causing the reader to mix two different versions.

The example intentionally uses 100 units and 100 transfers so balances never go negative. In real applications, validations such as sufficient funds, overflow, and cancellation conditions must be checked on **each re-read snapshot**, and in-memory updates do not replace database transactions.

## 8. Internal CAS Functions May Be Invoked Multiple Times

`AtomicInteger.updateAndGet`, `getAndUpdate`, and the `AtomicReference` variants typically perform an internal retry loop to apply a function of the old value.

```java
AtomicInteger n = new AtomicInteger(10);
int after = n.updateAndGet(old -> old + 5);
```

This illustrative snippet requires importing `AtomicInteger`; `after` equals `15` when there are no other writers. However, under contention, the function `old -> old + 5` **may be invoked multiple times** for a single commit.

Therefore, you should not write:

```java
n.updateAndGet(old -> {
    chargeCustomer(); // May be called multiple times due to retries!
    return old + 5;
});
```

This is a counterexample where `chargeCustomer()` is a business operation. The update function should be pure (free of non-idempotent side effects), computing the new state from the old state. Side effects outside CAS must be coordinated via idempotency or transactions if the system requires "exactly once"; moving the side effect outside the lambda **does not automatically make two systems one transaction**.

An important rule: **each time CAS fails, recompute both the state and validity conditions on the new snapshot**. Do not reuse check results from an older version if business conditions can change.

## 9. The ABA Problem: Value A → B → A

CAS inspects the **current value**, and does not automatically record history. If thread A reads value `A` and then pauses, thread B can change `A -> B -> A`. When A calls CAS with expected `A`, the operation can succeed. This is called **ABA**.

```text
Thread A: read A ------------------ CAS(A, C) SUCCESS
Thread B:        A -> B -> A
Shared:    A ------- B ---- A ------ C
```

CAS is not wrong: at its moment of execution, current indeed equals A. **A bug only arises if the algorithm assumes "still A" means "no historical change occurred."** For example, with nodes of a lock-free stack, a reference returning to an old node does not necessarily mean its links are still the same.

### Versioning with `AtomicStampedReference`

Java provides `AtomicStampedReference<V>` to atomically update a **(reference, stamp)** pair. Every writer can increment the stamp by protocol, so a state returning to the same reference is still recognized as a new version.

Create `CasAbaDemo.java`:

```java
import java.util.concurrent.atomic.AtomicStampedReference;

public class CasAbaDemo {
    public static void main(String[] args) {
        Object a = new Object();
        Object b = new Object();
        Object c = new Object();

        AtomicStampedReference<Object> state =
                new AtomicStampedReference<>(a, 0);
        int oldStamp = state.getStamp();

        boolean ab = state.compareAndSet(a, b, 0, 1);
        boolean ba = state.compareAndSet(b, a, 1, 2);
        boolean stale =
                state.compareAndSet(a, c, oldStamp, oldStamp + 1);

        System.out.println("A-B=" + ab);
        System.out.println("B-A=" + ba);
        System.out.println("same=" + (state.getReference() == a));
        System.out.println("stale=" + stale);
        System.out.println("stamp=" + state.getStamp());
    }
}
```

```bash
javac CasAbaDemo.java
java CasAbaDemo
```

Output:

```text
A-B=true
B-A=true
same=true
stale=false
stamp=2
```

The reference returned to the exact same object `a`, but the stamp increased from `0` to `2`. The CAS with expected stamp `0` fails. This mechanism requires **every writer to update the stamp consistently**. An `int` stamp is still bounded and can wrap around if the system runs long enough. `AtomicMarkableReference` pairs a boolean flag with a reference for specific state-marking problems, not as a general-purpose version counter.

**Not every ABA is a bug:** if the algorithm only cares about the current value, returning to an old value may be completely acceptable.

## 10. Strong CAS and Weak CAS

The standard `compareAndSet` on `AtomicInteger` and `AtomicReference` is **strong CAS**: when it returns `false`, expected did not match on that attempt.

Some **weak CAS** methods such as `weakCompareAndSetPlain` can return `false` even when expected matches (**spurious failure**). Thus, you cannot definitively conclude another writer intervened from a single weak CAS returning false. Weak CAS variants like `weakCompareAndSetAcquire` and `weakCompareAndSetRelease` also have different memory semantics; do not swap method names while ignoring ordering contracts.

`compareAndSet` is the clearer choice for most cases. Weak CAS should only be used when you fully understand memory ordering and the required retry algorithm.

**Do not confuse** spurious failure in weak CAS with spurious wakeup in `Object.wait()` or `Condition.await()`. They are two phenomena belonging to different APIs.

## 11. CAS Compared to Other Primitives

| Primitive | Strengths | Caveats |
| --- | --- | --- |
| `volatile` | Publishes/observes a single value with JMM ordering | `counter++` is not atomic |
| `synchronized` | Protects critical sections, provides mutual exclusion and happens-before via the same monitor | Requires proper lock scope and contention management |
| `AtomicInteger.incrementAndGet` | Atomic increment without writing a manual loop | Suitable for a single numeric variable |
| `compareAndSet` | Conditional state transition, atomic update of a single location | Must handle failure |
| `AtomicReference<State>` | Atomically publishes an immutable snapshot | Internal state must be truly immutable or separately synchronized |
| `LongAdder` | Can improve throughput when many writers accumulate | `sum()` is not an atomic snapshot under concurrent writers |

If you only need to increment a number, prefer `incrementAndGet` for clarity. If multiple fields must change as a unit, use a single root snapshot or a lock. Under high contention, a CAS loop can burn CPU on retries; **do not assume CAS is always faster than locks**.

The term **lock-free** only holds when **the entire algorithm** guarantees that some operation makes progress; it does not mean every thread is guaranteed to succeed quickly. **Wait-free** is stronger: every operation has a bounded number of steps. CAS is the building block of many non-blocking algorithms, but seeing a CAS in a method does not prove that method is lock-free.

## 12. Does CAS Need to Handle Interrupts or Cancellation?

A `compareAndSet` call is not a lock-waiting operation like `lockInterruptibly()`, so it does not throw `InterruptedException` to signal cancellation. A CPU-bound retry loop may need to check `Thread.currentThread().isInterrupted()` or a cancellation token at a safe point:

```java
for (;;) {
    if (Thread.currentThread().isInterrupted()) {
        return; // This update has not been committed.
    }

    State before = ref.get();
    State after = calculateNext(before);

    if (ref.compareAndSet(before, after)) {
        return; // Update committed.
    }
}
```

This is an illustrative snippet with application-defined `State`, `ref`, and `calculateNext`. A cancellation signal can arrive **right after the check but before the CAS**; if you need "either cancel or commit, never both" at a single logical point, you must model the canceled state in the same state machine or use a tighter coordination protocol.

Stopping a task halfway through a multi-step operation can break invariants. Only respond to cancellation at a safe point or with proper rollback. `Thread.interrupt()` does not undo an already-succeeded CAS.

## 13. CAS for State Machines

A straightforward use case is allowing a task to transition only `NEW -> RUNNING -> DONE`. If two threads both try to start it, only one `NEW -> RUNNING` transition is allowed to succeed.

Create `CasStateDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class CasStateDemo {
    enum Status { NEW, RUNNING, DONE }

    public static void main(String[] args) {
        AtomicReference<Status> state =
                new AtomicReference<>(Status.NEW);

        boolean start = state.compareAndSet(Status.NEW, Status.RUNNING);
        boolean startAgain = state.compareAndSet(Status.NEW, Status.RUNNING);
        boolean finish = state.compareAndSet(Status.RUNNING, Status.DONE);

        System.out.println("start=" + start);
        System.out.println("startAgain=" + startAgain);
        System.out.println("finish=" + finish);
        System.out.println("state=" + state.get());
    }
}
```

```bash
javac CasStateDemo.java
java CasStateDemo
```

Output:

```text
start=true
startAgain=false
finish=true
state=DONE
```

`enum` constants are unique objects, making them well-suited for identity-based CAS. This example illustrates state transitions in a single-threaded sequence; with multiple threads, you must fully design rules for `FAILED`, `CANCELED`, task results, and side effects outside the JVM. A successful state CAS does not automatically mean the entire business operation is complete.

## 14. CAS-Related APIs

- `compareAndSet(e, u)` returns a boolean: did it commit when expected matched?
- `compareAndExchange(e, u)` returns the **witness value** observed at the comparison point, rather than just a boolean. Available in Java 9+.
- `getAndSet(u)` atomically replaces with `u` and returns the old value, without checking expected.
- `getAndUpdate(fn)` and `updateAndGet(fn)` apply an update function with possible retries; they differ in which value they return.
- `VarHandle` provides low-level atomic and memory-ordering operations on fields/array elements, useful when custom designs are required; for most problems, atomic wrappers are easier to use.

Do not substitute one API for another just because both have "set" in the name: expected semantics, return values, and memory ordering can differ.

## 15. Common Pitfalls to Avoid

1. **Ignoring the boolean:** calling CAS and reporting success even when it returned `false`.
2. **Retrying with a stale expected value:** failing to re-read state can cause the loop to spin forever.
3. **Triggering side effects inside a retry lambda:** the action may run multiple times for a single commit.
4. **Reading two snapshots at different times:** reading two fields via two `AtomicReference.get()` calls can mix two versions.
5. **Using two atomic variables for one invariant:** separate per-variable atomicity does not protect the group as a whole.
6. **Confusing `equals()` and identity:** `AtomicReference.compareAndSet` compares object references.
7. **Ignoring ABA:** a value returning to its old state does not prove no history changed.
8. **Assuming CAS never costs CPU:** high contention causes many failed attempts, potentially requiring backoff or a different primitive.
9. **Ignoring overflow and cancellation policy:** CAS does not automatically check domain bounds or honor interrupts.
10. **Equating CAS with transactions:** an in-memory update does not atomically commit I/O, databases, or message brokers alongside it.

## 16. Self-Check

**Q1.** An `AtomicInteger` has value `4`. You call `compareAndSet(4, 5)` and then `compareAndSet(4, 6)`. What is the result?

**Answer:** `true` then `false`; final value is `5`.

**Q2.** Two threads both read `0` and then call CAS `(0, 1)`. Assuming no other writers, can both succeed?

**Answer:** No. One thread wins and changes the value to `1`. The other thread must retry with the new expected value if it wants to perform its own increment.

**Q3.** Does `volatile int x` make `x++` safe with multiple writers?

**Answer:** No. Visibility is different from atomicity of the entire read-modify-write operation.

**Q4.** Two records have `equals()==true` but `==false`; is it valid to pass the newly created record as expected to a reference CAS?

**Answer:** No, if the reference currently holds the other record. Reference CAS compares identity.

**Q5.** Are two separate `AtomicInteger` balances sufficient to guarantee a constant sum during transfers?

**Answer:** No. You must protect the group of updates/reads or bundle them into an immutable snapshot swapped via CAS on a root reference.

**Q6.** Why should the function passed to `updateAndGet` have no side effects?

**Answer:** The function may be invoked again under contention, causing the side effect to repeat multiple times.

**Q7.** Does an ABA sequence `A -> B -> A` make CAS atomically incorrect?

**Answer:** No. CAS checks the value at the time of execution; a bug only occurs if the algorithm depends on history without storing a version.

**Q8.** Does `weakCompareAndSetPlain` returning false always mean another thread modified the value?

**Answer:** No. Weak CAS can fail spuriously.

**Q9.** Does CAS automatically guarantee a canceled thread will not commit further?

**Answer:** No. You must explicitly design cancellation and commit points, potentially combining the canceled state into an atomic state machine.

## 17. Summary

**CAS = atomically compare and then set if and only if the current value still matches expected.** To preserve every update under contention, use the loop **re-read → recompute → CAS → retry on failure**. A successful CAS has a clear linearization point for **a single atomic location**.

In Java, applying it correctly also requires understanding **JMM visibility/happens-before**, `AtomicReference` identity comparison, ABA, weak CAS, and side effects during retries. When an invariant spans multiple fields, encapsulate them in an **immutable snapshot** and CAS a single root reference, or use locks with a clear protocol; do not treat CAS as a drop-in replacement for all transactions or all thread coordination.
