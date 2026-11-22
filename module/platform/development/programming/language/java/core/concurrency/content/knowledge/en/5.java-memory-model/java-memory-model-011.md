# Limitations of volatile with Compound Actions in Java

A `volatile` field has special read/write rules in the Java Memory Model (JMM): other threads can rely on **visibility** and **ordering** mechanisms to observe published data according to the proper protocol. However, `volatile` **does not turn multiple steps into a single atomic operation**. Therefore, even if `counter` is declared `volatile`, expressions like `counter++`, `counter += 2`, or `if (!claimed) claimed = true` can still produce incorrect results when multiple threads run concurrently.

This article covers **general Java concurrency on Java 17+**, focusing on the limitations of `volatile` when used with **compound actions**. Spring-specific mechanisms are outside the scope.

Objectives: properly understand the guarantees of `volatile`; identify read–modify–write, check–then–act, and multi-field invariants; demonstrate lost updates; choose Atomic*/CAS, `synchronized`, or `Lock` according to requirements; verify with controlled examples and tests.

## 1. Volatile guarantees visibility and ordering, not compound atomicity

Three concepts need to be separated:

| Property | Question to answer | Related mechanisms |
| --- | --- | --- |
| **Visibility** | Does B see A's write after the proper publication point? | Volatile write/read, lock/unlock, join, Future... |
| **Ordering** | Is there a happens-before edge between A and B? | Program order, synchronizes-with, transitivity |
| **Atomicity** | Is a group of steps executed as a single unit without other threads interleaving? | Atomic RMW, CAS, locks, appropriate transactions |

A **write to a volatile field** *synchronizes-with* subsequent **reads of that same volatile field in synchronization order**. Through program order and transitivity, data writes before publication can happen-before data reads after the reader sees the published state.

**Single reads/writes on a volatile field** have atomicity semantics for the access itself (including `volatile long` and `volatile double`); that is completely different from making a statement consisting of reading, computing, and then writing atomic. Volatile also does not automatically lock a block of code.

### Example of using volatile properly to publish data

~~~java
// VolatilePublicationDemo.java
public class VolatilePublicationDemo {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("Payload: " + payload);
        });

        reader.start();
        payload = 42;
        ready = true;
        reader.join();
    }
}
~~~

~~~bash
javac VolatilePublicationDemo.java
java VolatilePublicationDemo
~~~

When threads are scheduled and the program completes normally, stdout:

~~~text
Payload: 42
~~~

Main executes `payload = 42` before `ready = true`. Reader observes `ready == true` via a volatile read and only then reads `payload`. The chain **program order → volatile synchronizes-with → program order**, combined with the transitivity of happens-before, guarantees that the reader sees the published data. There are no other concurrent writes to `payload`.

`Thread.onSpinWait()` is only a hint for the spin loop; it **does not create an additional synchronization edge** and does not guarantee fairness/liveness. The example uses spinning to illustrate the JMM; real-world applications typically use a latch, queue, or future to avoid busy-waiting.

## 2. What does a compound action include?

A **compound action** is a logical operation built from multiple actions where invariants require consistency. Main patterns:

- **Read–modify–write:** `counter++`, `count += delta`, `balance -= amount`. Needs to read the value, compute the new value, and then write it.
- **Check–then–act:** `if (!reserved) { reserved = true; }`. The condition may change after checking and before acting.
- **Check–update:** `if (stock > 0) stock--;`. Two threads may both see one item left and both sell it.
- **Multi-field updates:** `available--` and `sold++` need to maintain the invariant `available + sold == capacity`.
- **Read–compute–replace:** reading an object/version, computing a new object, and reassigning the reference. The reference assignment itself may be atomic, but this sequence can still suffer from lost updates.

A common mistake is seeing that individual volatile reads/writes guarantee visibility and concluding that **the entire statement** is safe. Look for the **atomicity point of the entire logical operation**, not just of the field.

## 3. Volatile counter++ still has lost updates

Suppose `counter = 0`. Two threads T1 and T2 both want to increment it exactly once:

| Logical order | T1 | T2 |
| --- | --- | --- |
| 1 | Read `counter = 0` | |
| 2 | | Read `counter = 0` |
| 3 | Compute `0 + 1` | |
| 4 | | Compute `0 + 1` |
| 5 | Volatile write `counter = 1` | |
| 6 | | Volatile write `counter = 1` |

The result is **1 instead of 2**. Each individual volatile access is still valid under the JMM; the bug is that both threads compute from the old version and overwrite each other.

### Deterministic Java 17+ reproduction example

Using `CountDownLatch` solely to coordinate so that **both threads read before writing**:

~~~java
// VolatileLostUpdateDemo.java
import java.util.concurrent.CountDownLatch;

public class VolatileLostUpdateDemo {
    private static volatile int counter;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int oldValue = counter;
            bothRead.countDown();
            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            counter = oldValue + 1;
        };

        Thread a = new Thread(increment);
        Thread b = new Thread(increment);
        a.start();
        b.start();

        bothRead.await();
        allowWrite.countDown();
        a.join();
        b.join();

        System.out.println("Expected: 2");
        System.out.println("Actual: " + counter);
    }
}
~~~

~~~bash
javac VolatileLostUpdateDemo.java
java VolatileLostUpdateDemo
~~~

Stdout:

~~~text
Expected: 2
Actual: 1
~~~

`bothRead.await()` only completes when both threads have stored `0` in `oldValue`. Afterward, both write `oldValue + 1`, which is `1`. Main calls `join()` on both before reading the result. In real code without latches forcing the execution schedule, the bug might occur rarely; rare **does not mean safe**.

Similarly, `++counter`, `counter += 3`, or `counter = counter * 2` all involve read–modify–write. `++counter` and `counter++` differ in the value of the expression, but **do not differ in atomicity**.

## 4. Using AtomicInteger for a single atomic read–modify–write

`AtomicInteger` provides `incrementAndGet()`, `getAndIncrement()`, `addAndGet(delta)`, `compareAndSet(expected, update)`, and other atomic update methods.

~~~java
// AtomicCounterDemo.java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger count = new AtomicInteger();

        Runnable increment = () -> count.incrementAndGet();
        Thread a = new Thread(increment);
        Thread b = new Thread(increment);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Atomic count: " + count.get());
    }
}
~~~

~~~bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
~~~

Stdout:

~~~text
Atomic count: 2
~~~

The two increments are executed as two atomic updates on the **same `AtomicInteger` instance**. `incrementAndGet()` returns the value **after incrementing**; `getAndIncrement()` returns the value **before incrementing**. Choose the right method based on your needs.

**However, individual atomic methods do not make every sequence of calls you write atomic.** For example:

~~~java
// Illustrative code: seats is an already declared AtomicInteger.
if (seats.get() > 0) {
    seats.decrementAndGet();
}
~~~

If `seats == 1`, both threads can read `1` and both decrement, resulting in `-1`. `get()` and `decrementAndGet()` each have their own guarantees, but the condition **is not atomically bound to the update**.

A CAS loop is more appropriate if you only need to manage the seat count:

~~~java
// Illustrative method in a class with an AtomicInteger seats field.
boolean reserve() {
    while (true) {
        int current = seats.get();
        if (current <= 0) {
            return false;
        }
        if (seats.compareAndSet(current, current - 1)) {
            return true;
        }
        // Another writer just changed it: re-read, re-check.
    }
}
~~~

`compareAndSet` checks the expected value and writes the new value **in a single atomic step**. If it fails due to contention, the code re-reads the state and re-evaluates the condition. This is **illustrative code**, not a standalone runnable Java file.

## 5. Check–then–act: volatile boolean is not enough to claim once

Example allowing only one thread to claim a resource:

~~~java
// Illustration in a class, not logically thread-safe:
private volatile boolean claimed;

boolean claim() {
    if (!claimed) {
        claimed = true;
        return true;
    }
    return false;
}
~~~

There is a schedule where T1 reads false, and T2 also reads false; then both write true and both return true. No cache bug is needed: at the **moment of reading**, both can genuinely read false.

Use `AtomicBoolean.compareAndSet(false, true)`:

~~~java
// AtomicClaimDemo.java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicClaimDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicBoolean claimed = new AtomicBoolean();
        AtomicInteger winners = new AtomicInteger();
        CountDownLatch begin = new CountDownLatch(1);

        Runnable attempt = () -> {
            try {
                begin.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            if (claimed.compareAndSet(false, true)) {
                winners.incrementAndGet();
            }
        };

        Thread a = new Thread(attempt);
        Thread b = new Thread(attempt);
        a.start();
        b.start();
        begin.countDown();
        a.join();
        b.join();

        System.out.println("Successful claims: " + winners.get());
    }
}
~~~

~~~bash
javac AtomicClaimDemo.java
java AtomicClaimDemo
~~~

Stdout:

~~~text
Successful claims: 1
~~~

Here, the atomicity point is **reading the current state and transitioning false → true** as a single operation. Only one CAS wins when no other code resets the state. When resets exist, you need to design an ownership/state contract and avoid ABA if a value can change and then return to its original value.

## 6. Multiple fields: volatile does not create a snapshot or transaction

Suppose there are two fields:

~~~java
// Illustrative code in a class:
private volatile int available = 10;
private volatile int sold;

// Writer:
available--;
sold++;

// Reader:
int a = available;
int s = sold;
~~~

The invariant to preserve is `available + sold == 10`. A reader can observe `available == 9`, `sold == 0` in between the two writes. Furthermore, if multiple writers use `--` and `++` concurrently, lost updates are also possible.

A straightforward solution is to put both the **check–update block and the snapshot read block** under the **same monitor**:

~~~java
// SynchronizedInventoryDemo.java
public class SynchronizedInventoryDemo {
    static class Inventory {
        private int available = 1;
        private int sold;

        synchronized boolean sell() {
            if (available <= 0) {
                return false;
            }
            available--;
            sold++;
            return true;
        }

        synchronized String snapshot() {
            return "Available: " + available + ", sold: " + sold;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory stock = new Inventory();

        Thread a = new Thread(stock::sell);
        Thread b = new Thread(stock::sell);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println(stock.snapshot());
    }
}
~~~

~~~bash
javac SynchronizedInventoryDemo.java
java SynchronizedInventoryDemo
~~~

Stdout:

~~~text
Available: 0, sold: 1
~~~

Each `sell()` acquires the monitor of the **same `stock` object** and protects the entire check–update. `snapshot()` uses that same monitor, so it cannot read in the middle of two updates. The fields do not need to be volatile if all shared accesses follow the protocol properly.

With `ReentrantLock`, it can be organized similarly, but the lock must be released in `finally` after successfully acquiring it:

~~~java
// Illustrative code: lock is an already declared ReentrantLock, fields are already declared.
lock.lock();
try {
    if (available > 0) {
        available--;
        sold++;
    }
} finally {
    lock.unlock();
}
~~~

Locks provide both mutual exclusion and lock/unlock memory effects. **All read and write paths related to the invariant must use the same mechanism.** Locking only the writer while letting readers read the two fields separately outside the lock can still observe intermediate states.

## 7. Volatile reference: publishing a snapshot differs from updating a snapshot

A `volatile` reference can help **publish an immutable object**:

~~~java
// Illustrative code in a Java 17+ class:
record Inventory(int available, int sold) {}

private volatile Inventory current = new Inventory(10, 0);

Inventory snapshot() {
    return current;
}
~~~

A reader only needs to read `current` once and use both components on the **same instance**. However, if two writers both do:

~~~java
// Not safe with multiple writers:
Inventory old = current;
current = new Inventory(old.available() - 1, old.sold() + 1);
~~~

they can both read an old version and overwrite each other's results. A volatile reference is a **publication point**, not an automatic atomic read–modify–write.

### AtomicReference with immutable state

~~~java
// AtomicSnapshotDemo.java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicSnapshotDemo {
    record Inventory(int available, int sold) {}

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Inventory> state =
            new AtomicReference<>(new Inventory(2, 0));

        Runnable sell = () -> state.updateAndGet(old ->
            old.available() == 0
                ? old
                : new Inventory(old.available() - 1, old.sold() + 1)
        );

        Thread a = new Thread(sell);
        Thread b = new Thread(sell);
        a.start();
        b.start();
        a.join();
        b.join();

        Inventory result = state.get();
        System.out.println("Available: " + result.available());
        System.out.println("Sold: " + result.sold());
        System.out.println("Total: " +
            (result.available() + result.sold()));
    }
}
~~~

~~~bash
javac AtomicSnapshotDemo.java
java AtomicSnapshotDemo
~~~

Stdout:

~~~text
Available: 0
Sold: 2
Total: 2
~~~

`AtomicReference.updateAndGet` updates **one reference** atomically; because the object is immutable, calling `state.get()` returns a consistent snapshot. The updater function **may be called multiple times when CAS retries**. Do not put side effects such as sending emails, charging money, or writing to a database inside the lambda and assume it executes exactly once. When data lives in a database or a system outside the JVM, in-memory CAS does not replace that system's transactions.

The record uses `int` components, so the snapshot itself in the example is immutable. If it contains mutable arrays/lists, you need to consider **deep immutability**, rather than concluding safety solely from the `record` keyword.

### Volatile array does not make individual elements atomic

~~~java
// Illustrative code in a class:
private volatile int[] counters = new int[2];
~~~

Volatile applies to the **`counters` reference field**; it does not make `counters[0]++` atomic and does not automatically attach volatile semantics to each element. Similarly, `volatile Settings settings` does not automatically make all mutable fields inside `Settings` thread-safe. If you want atomic element updates, consider `AtomicIntegerArray` or an appropriate lock.

## 8. CAS and limitations to know

CAS (*compare-and-set*) allows checking an expected value and updating it at an atomic point, but:
- **Contention:** CAS can fail when the value changes; retrying many times can consume CPU.
- **Multiple variables:** CAS on one variable does not create a transaction for other variables or resources.
- **Updater lambda:** `updateAndGet`/`getAndUpdate` may recompute, so the computation function should be pure and avoid side effects.
- **ABA:** state transitions A → B → A; CAS only compares and sees A, unaware that an intermediate change occurred. When version awareness matters, you can use a version/stamp such as `AtomicStampedReference`.
- **Liveness:** an unbounded retry loop can cause a thread to suffer starvation under contention; wait time and progress requirements should be considered.

Not every simple CAS encounters ABA; the issue needs consideration when **logic depends on the value never having changed**, not just on its current value.

## 9. Comparing and choosing the right tool

| Tool | Suitable for | Does not automatically guarantee |
| --- | --- | --- |
| `volatile` | Flag/data publication with clear happens-before | Compound atomicity, multi-field transactions |
| `AtomicInteger`, `AtomicLong` | Atomic increment/decrement/CAS for a single variable | Sequences like `get()` then `set()` are not automatically atomic |
| `AtomicBoolean` | Single-state transition via CAS | Multi-state protocols or complex resets |
| `AtomicReference<T>` | CAS/swap of an immutable snapshot | Mutable modifications inside the object; external I/O |
| `synchronized` | Check–update, multi-step/multi-field invariants | Must use the exact same monitor for all access paths |
| `ReentrantLock` | Similar to synchronized, plus `tryLock`/timeout/interruptible acquisition | Must unlock in `finally`, watch out for deadlocks |
| `LongAdder` | High-contention statistics counters | `sum()` is not an atomic snapshot during concurrent updates |

Principles:
1. Write down the **invariant** (e.g., no overselling, constant total money, single winner).
2. Identify the required **atomic update point**.
3. Choose an atomic operation, CAS loop, or lock that preserves the invariant across steps.
4. Ensure **readers** use the same protocol or read a consistent immutable snapshot.
5. Only after correctness is established should you evaluate contention, latency, and stopping/retry strategies.

## 10. Happens-before does not replace atomicity

A program can use all volatile accesses and have no *data race* of the un-synchronized regular access kind, yet still have a **logical race condition**. For example, two threads executing `volatile counter++`: each volatile access obeys JMM ordering rules, yet the two read–compute–write sequences still interleave.

Similarly, main calling `join()` after two workers perform a buggy increment is only guaranteed to **see the final result they produced**. If they lost an increment, `join()` cannot turn the wrong result into the right one.

Do not use `Thread.sleep(...)`, `Thread.yield()`, or `Thread.onSpinWait()` to "fix" increments. They do not add atomicity to compound actions. Empirically running correctly many times also does not prove that all valid interleavings are correct.

## 11. Diagnosis and testing checklist

1. **Identify the invariant:** `count == number of increments`, `stock >= 0`, `available + sold == capacity`, or only one claim succeeds.
2. **Break down into individual actions:** read value, check, compute, write; is there a gap where another thread can interleave?
3. **Trace the worst-case schedule:** both threads see the old value before any write happens.
4. **Check primitives:** if using `AtomicInteger`, are `get` and `set` called separately? If using locks, are the same monitor and protocol used?
5. **Check readers:** can they see half-old, half-new state?
6. **Use coordinated tests:** `CountDownLatch`/barriers help force bad read–write schedules. Verify results with assertions, not by inferring from logs/timing.
7. **Check retries and side effects:** a CAS loop can spin multiple times; is the updater idempotent/pure?
8. **Measure after fixing:** evaluate contention and throughput without sacrificing correctness guarantees.

### Common pitfalls

- "`volatile counter++` is safe because all reads/writes are volatile." → False; compound increments can still interleave.
- "`AtomicInteger.get()` and `decrementAndGet()` are both atomic, so calling both is atomic." → False; there is no transaction around the pair of calls.
- "Two volatile fields always provide a consistent snapshot." → False; a reader can observe an intermediate state.
- "A volatile reference makes the pointed-to object thread-safe." → False if the object is still concurrently mutated.
- "`join()` at the end fixes lost updates." → False; it only waits and provides visibility/ordering.
- "A CAS updater executes exactly once." → False; it can run again on retry.
- "Adding `sleep` eliminates races." → There is no such JMM guarantee.

## 12. Self-check

**1.** Two threads call `counter++` on `volatile int counter` starting from 0. Can the result be 1? **Yes.** Both threads can read 0 and then both write 1.

**2.** Is `if (seats.get() > 0) seats.decrementAndGet()` with `AtomicInteger` safe when stock=1? **No.** Checking and decrementing are two separate operations; a CAS loop or lock is needed.

**3.** Two threads both execute `if (!claimed) claimed = true` on a volatile boolean. Can both believe the claim succeeded? **Yes.** Use `compareAndSet(false, true)` for an atomic transition.

**4.** Is using `volatile Inventory current` with an immutable record enough for multiple writers doing read–compute–replace? **Not enough.** Publication of each reference is atomic, but the compound update can suffer lost updates; use CAS or a lock.

**5.** Can `AtomicReference.updateAndGet` call the updater multiple times? **Yes**, when there is contention and CAS must retry.

**6.** Why does a volatile flag work for publishing a payload, while volatile `++` is not enough? **Because** a flag provides a happens-before edge for publishing completed work, whereas `++` requires **atomicity of the entire read–modify–write**.

**Key takeaway:** `volatile` solves **visibility and ordering of specific accesses**; compound actions require **atomicity matching the invariant**. Use atomic/CAS methods or a lock protocol with sufficient scope, and verify both read and write paths.

### References

- Java Language Specification 17, `17.4 Java Memory Model: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- JDK 17 `AtomicInteger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- JDK 17 `AtomicBoolean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html
- JDK 17 `AtomicReference`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html