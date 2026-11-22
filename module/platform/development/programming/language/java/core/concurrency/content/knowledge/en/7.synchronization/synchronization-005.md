# Mutual exclusion and memory visibility of monitors in Java

> **Scope:** the two foundational guarantees of the `synchronized` mechanism in Java SE: **mutual exclusion** (preventing concurrent execution when operating on shared state) and **memory visibility/ordering** under the Java Memory Model. The content focuses on Java in general, independent of Spring-specific concurrency mechanisms.

## 1. Goals and core idea

A multithreaded program can fail in **two different ways** even when every thread executes the exact lines of code written:

- **Operation race:** multiple threads interleave read–compute–write steps or concurrently modify fields that must remain consistent. For example, two `counter++` operations lose one increment.
- **Missing visibility/ordering relationship:** one thread has written a value, but another thread lacks an appropriate synchronization mechanism to guarantee that its reads observe those writes as required by the program.

Java provides an **intrinsic monitor** through `synchronized` to solve both problems simultaneously when **all relevant accesses follow the same locking protocol**:

1. **Mutual exclusion:** only one thread may own a monitor at a time; therefore, critical sections using the same monitor do not overlap.
2. **Memory visibility/ordering:** an **unlock** of monitor `m` *synchronizes-with* **subsequent locks on that same monitor `m`** under the Java Memory Model (JMM) rules. This relationship participates in building *happens-before*.

After this lesson, you should understand when a piece of code is actually protected, why a reader must use the exact same monitor, how to read *happens-before* relationships, when `synchronized` alone is still insufficient to preserve an invariant, and how to verify this with a Java 17+ example.

**Key design takeaway:** it is not enough to merely say "the writer is synchronized." You need to know **which monitor object** is used, **which operations** are inside the critical section, and **when the reader acquires the same monitor**.

## 2. A monitor is bound to a specific object

In Java, every object has an **intrinsic lock / monitor**. The statement `synchronized (guard) { ... }` must acquire ownership of the monitor of the exact object that `guard` references.

If one thread already holds that monitor, another thread attempting to enter a `synchronized` block using the same monitor must wait. If two code blocks use **two different objects**, they do not exclude each other merely because both variables are named `guard`.

Illustrative example:

```java
final class SharedCounter {
    private final Object monitor = new Object();
    private int value;

    void increment() {
        synchronized (monitor) {
            value++;
        }
    }

    int value() {
        synchronized (monitor) {
            return value;
        }
    }
}
```

This is a **compilable class** in the file `SharedCounter.java`. `monitor` is the same object used by both methods; it is `private final` to prevent callers from directly acquiring the monitor and to prevent normal code from changing the reference.

For each `SharedCounter` instance, every call to `increment()` passes through the critical section sequentially. When `value()` acquires the monitor after an `increment()` has released it, it receives the corresponding memory visibility guarantees.

**Different instances have separate monitors.** If you create two `new SharedCounter()` objects, each instance has its own `new Object()` and the two counters do not exclude each other; this is usually desirable when their states are independent.

### Forms of synchronized and their corresponding monitors

| Syntax | Monitor acquired | Consequence |
|---|---|---|
| `synchronized (guard) { ... }` | The object referenced by `guard` when the expression is evaluated | Regions using the **same object** coordinate with each other. |
| `synchronized void update() { ... }` on an instance | `this` | Synchronized instance methods of the same instance share the same monitor. |
| `static synchronized void update() { ... }` | The `Class` object of the class declaring the method | Static synchronized methods of the same class share the `Class` monitor. |
| `synchronized (SomeType.class) { ... }` | The `SomeType.class` object | Can coordinate with static synchronized methods of the corresponding class. |

Do not confuse `static synchronized` with locking **all instances**: it locks the `Class` object, whereas synchronized instance methods lock each individual instance. Therefore, a static synchronized method and an instance synchronized method **do not necessarily block each other**.

**Reentrancy:** a thread that already owns a monitor is allowed to re-enter that same monitor, such as an instance synchronized method calling another instance synchronized method on the same `this`. The "one owner per monitor" rule still holds: this is **one owner** entering at multiple levels, not two threads entering together.

## 3. Mutual exclusion: why does it prevent lost updates?

Suppose you have:

```java
counter++;
```

This is an **illustrative expression**, where `counter` is an `int` field in its enclosing class. Behaviorally, the increment consists of reading the old value, computing the new value, and writing it back. Two threads can interleave:

| Step | Thread A | Thread B | `counter` |
|---|---|---|---|
| 0 | — | — | 0 |
| 1 | Read 0 | — | 0 |
| 2 | — | Read 0 | 0 |
| 3 | Write 1 | — | 1 |
| 4 | — | Write 1 | 1 |

The final result is **1**, even though both threads performed an increment; this is a **lost update**. The table is a simplified illustrative schedule and does not describe all memory behaviors permitted by the JMM for a program with a data race.

Place the entire operation inside a shared critical section:

```java
synchronized (guard) {
    counter++;
}
```

This is also **illustrative code**, assuming `guard` and `counter` are already declared fields. If both A and B use the **same `guard` instance**, A must complete the critical section and release the monitor before B can acquire it (or vice versa). Consequently, the second increment will read the value after the first increment, and there is no schedule where both threads read 0 and both write 1 **within the region protected by the same lock**.

The two parts of the "incrementing a counter" problem must be proven separately:

- **Operation-level atomicity:** read–compute–write resides within a single critical section, with no other writer using the same monitor interleaving in between.
- **Observation visibility:** the reader uses the same monitor, or there is another suitable *happens-before* relationship; if the reader accesses the field directly outside synchronization, that guarantee cannot be inferred from the writer's monitor.

A lock only excludes code **that uses that lock**. `synchronized` does not stop a thread that deliberately writes to the field directly from code that never acquires the monitor.

## 4. Memory visibility under the Java Memory Model

### Monitor release/acquire rule

According to **JLS `17.4.4`**, an **unlock** action on monitor `m` *synchronizes-with* every **subsequent lock action on the same monitor `m`** in the synchronization order.

Read this carefully:

- **Same monitor:** it must be the exact same monitor object, not two objects that are "equivalent" according to `equals()`.
- **Unlock and lock:** these are two synchronization actions whose meaning goes beyond the scheduler allowing a thread to run.
- **Subsequent in synchronization order:** there is no guarantee about which thread acquires the lock first based on arrival order. When a lock actually follows the corresponding unlock, we have a memory ordering edge defined by the JMM.

### From synchronizes-with to happens-before

The JMM defines the **happens-before (HB)** relationship from *program order* and *synchronizes-with* edges, with transitivity. Suppose:

```text
Thread A                                Thread B
------------------------------          ----------------------------
synchronized (m) {                      synchronized (m) {
    data = 42;                              int observed = data;
} // unlock(m)                          } // unlock(m)

A: write data=42
    --program order--> A: unlock(m)
    --synchronizes-with--> B: lock(m) after A's unlock
    --program order--> B: read data

Therefore, A's write happens-before B's read.
```

This diagram **only considers the case where B acquires the monitor after A has unlocked it**. If B enters the synchronized block before A, B may observe the old value. Creating a thread earlier, calling `start()` earlier, or starting to wait for the lock earlier **does not prove** it acquires the monitor first.

HB provides rules about which writes a read action is allowed to observe. If A writes 42, B locks after A's unlock, and **no other valid update to `data` intervenes**, B cannot use "the cache hasn't synced yet" as an excuse to see the old value in a way that violates HB.

**Do not rely on the mental model "unlock flushes the entire physical cache, lock reloads all of RAM."** That is not the language contract. The JVM/JIT/CPU have many ways to implement barriers and optimizations, as long as they preserve the observation constraints specified by the JMM.

### Two cases to distinguish

**1. Using the right monitor:**

```java
// Fields of a class:
private final Object guard = new Object();
private int result;

void writeResult(int value) {
    synchronized (guard) {
        result = value;
    }
}

int readResult() {
    synchronized (guard) {
        return result;
    }
}
```

These are **members of the same class**, not a standalone program. If `readResult` acquires the monitor after `writeResult` has released it, the value written before the unlock is published to the reader by HB (unless another writer performs a valid update before that read).

**2. Using different monitors:**

```java
// Illustrative code lacking a shared synchronization protocol:
private final Object writerGuard = new Object();
private final Object readerGuard = new Object();
private int result;

void writeResult(int value) {
    synchronized (writerGuard) {
        result = value;
    }
}

int readResult() {
    synchronized (readerGuard) {
        return result;
    }
}
```

The writer unlocks `writerGuard`, while the reader locks `readerGuard`. Those two actions **do not** create a *synchronizes-with* edge under the **same-object monitor rule**. There is no mutual exclusion between the two blocks; the program may also have a data race if no HB exists from another source. Fix this by using the **same monitor** for all accesses that need protection, or by switching to a primitive with an appropriate synchronization contract.

## 5. Visibility does not mean a single fixed outcome or order

A commonly misunderstood example:

- A intends to write `data = 42` under monitor `m`.
- B intends to read `data` under the same monitor `m`.
- Both threads are started around the same time.

Both use the right monitor. However, B may acquire the monitor **before** A writes; in that case, B validly reads the initial value. `synchronized` only guarantees that critical sections **do not overlap**, and guarantees visibility for a lock that occurs **after** the writer's unlock.

If the business requirement is that **B must wait for A to publish the data**, an additional protocol is needed to coordinate phases:

- A `ready` predicate written/read under the same monitor, combined with `wait()/notifyAll()`.
- Or using `BlockingQueue`, `CountDownLatch`, or `Future.get()` if the corresponding API fits the goal.

Do not use `Thread.sleep(50)` as proof that A has finished: sleeping for a duration **does not establish the necessary HB relationship** and does not guarantee ordering between threads.

### Monitors protect multi-field consistency

Suppose a ledger maintains the invariant:

\[
\text{total} = 10 \times \text{updates}
\]

If the writer performs `total += 10` and then `updates++` inside the same monitor, a reader that also acquires the same monitor to read **both fields** will observe a snapshot either before or after **a complete update**, never a state in between the two steps.

If the reader calls two **separate** synchronized getters, it might see `total` from one update and `updates` from the next, because the lock is released between the two calls. To guarantee multi-field consistency, the reader needs **a single critical section enclosing the entire snapshot**, or an immutable snapshot constructed under the lock.

An important detail: the two fields do not need to be `volatile` when **all required read/write paths follow the same monitor**. Unlock/lock establishes visibility and the critical section establishes atomicity. Making individual fields volatile does not turn two separate reads into a consistent snapshot.

## 6. Java 17+ practice: atomic updates and consistent visible snapshots

The following program has two writers concurrently updating `total` and `updates`. A reader runs concurrently, taking snapshots repeatedly and checking the invariant. All three share a single `Ledger` instance.

Create the file **`MonitorSafetyLab.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class MonitorSafetyLab {
    record Snapshot(long total, long updates) {
        boolean valid() { return total == updates * 10L; }
    }

    static final class Ledger {
        private final Object guard = new Object();
        private long total;
        private long updates;

        void addTen() {
            synchronized (guard) {
                total += 10;
                updates++;
            }
        }

        Snapshot snapshot() {
            synchronized (guard) {
                return new Snapshot(total, updates);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Ledger ledger = new Ledger();
        ExecutorService executor = Executors.newFixedThreadPool(3);
        try {
            Future<?> first = executor.submit(() -> {
                for (int i = 0; i < 10_000; i++) ledger.addTen();
            });
            Future<?> second = executor.submit(() -> {
                for (int i = 0; i < 10_000; i++) ledger.addTen();
            });
            Future<Boolean> reader = executor.submit(() -> {
                for (int i = 0; i < 20_000; i++) {
                    if (!ledger.snapshot().valid()) return false;
                }
                return true;
            });

            first.get();
            second.get();
            boolean readConsistent = reader.get();
            Snapshot end = ledger.snapshot();

            System.out.println("readSnapshotsConsistent=" + readConsistent);
            System.out.println("finalTotal=" + end.total());
            System.out.println("finalUpdates=" + end.updates());
            System.out.println("finalInvariant=" + end.valid());
        } finally {
            executor.shutdown();
        }
    }
}
```

Compile/run:

```bash
javac --release 17 MonitorSafetyLab.java
java MonitorSafetyLab
```

**Verified stdout:**

```text
readSnapshotsConsistent=true
finalTotal=200000
finalUpdates=20000
finalInvariant=true
```

### Analyzing the mechanism, not relying on "lucky runs"

1. Each call to `addTen()` acquires the `guard` monitor of the **same Ledger** and updates both `total` and `updates` before releasing it.
2. Another writer cannot enter `addTen()` using the same `guard` while the first writer is still in the critical section. Therefore, there are exactly 20,000 valid increments, each contributing 10.
3. `snapshot()` must also acquire the exact same `guard`. When it returns, the `Snapshot` record contains two values read **within a single critical section**; no writer can interleave between the two reads.
4. `record Snapshot` holds only two `long` values; its components are final, and this value object provides no way to mutate its contents. Returning the record out of the lock does not make the snapshot mutable.
5. `Future.get()` is where `main` waits for the tasks to complete, carrying the memory-consistency guarantees of the executor/Future. When `main` reads the final snapshot, both writers have finished; thus the total equals `20_000 × 10 = 200_000`. **`Future.get()` provides completion/visibility to `main`, but does not make updates between the two writers atomic**; that responsibility belongs to the monitor.
6. The reader can take 20,000 snapshots **before, during, or after** most of the writer activity. Because every snapshot is created under the shared lock, the invariant expression always holds, regardless of thread scheduling.

Regarding benchmarking, this example does not measure overhead; it verifies **correctness**. Observing a correct result on a single run does not prove "the code has no races" in general, but here the locking rules prove the invariant for all valid interleavings.

**Limitations of the example:** the computation `updates * 10L` could overflow in a general-purpose problem; the iteration count in this program is small and has no overflow risk. For a real ledger, you need proper monetary modeling, overflow checks, and transaction state handling. `shutdown()` stops accepting new tasks; here `Future.get()` has already waited for all submitted tasks. In long-running applications, a graceful termination procedure and proper handling of `InterruptedException`/`ExecutionException` according to contract are required.

## 7. Distinguishing "safe single-field reads" from a "consistent snapshot"

The following structure *does not* guarantee a multi-field snapshot:

```java
// Methods of a hypothetical class containing guard, total, and updates:
long getTotal() {
    synchronized (guard) {
        return total;
    }
}

long getUpdates() {
    synchronized (guard) {
        return updates;
    }
}

// Reader thread:
long a = getTotal();
long b = getUpdates();
```

This is an **illustrative snippet**, not a standalone class. Between the two getter calls, the reader releases the monitor. A writer can update both fields and release the monitor before the reader calls the second getter; the resulting `a` and `b` are not from the same logical point in time.

Fix:

```java
// Method of a class with guard, total, and updates:
Snapshot snapshot() {
    synchronized (guard) {
        return new Snapshot(total, updates);
    }
}
```

This snippet uses the same `record Snapshot(long total, long updates)` type as in the example above. A snapshot is a *logical unit* of reading, so it must be created under a single monitor acquisition.

Similarly, if the business requirement is "check for sufficient resources, then deduct," combine **check + update** into a single critical section:

```java
// Method of a class with an int field available and monitor guard:
boolean reserveOne() {
    synchronized (guard) {
        if (available == 0) return false;
        available--;
        return true;
    }
}
```

Two methods `hasStock()` and `decrement()`, even if each is individually synchronized, can still allow another thread to interleave in between. Mutual exclusion must protect the **entire logical transaction** that you want to be atomic.

## 8. When is synchronized released?

### When exiting a synchronized block/method

Java automatically releases the corresponding level of monitor ownership when control flow exits `synchronized`, including via `return` or an exception. An instance synchronized method uses the `this` monitor; a static synchronized method uses the `Class` object.

```java
int compute() {
    synchronized (guard) {
        if (inputInvalid()) return -1;
        return calculate();
    } // monitor is released even on return or exception
}
```

This is an **illustrative method**; `guard`, `inputInvalid()`, and `calculate()` are defined outside this snippet. Releasing the monitor **does not** automatically roll back data updates that occurred before the exception was thrown. If an invariant could be left half-updated on an exception, you need exception-safe updates or a rollback strategy.

### Reentrancy

A thread that already holds a monitor can re-enter that monitor, for example when one `synchronized` method calls another `synchronized` method on the same instance. The JVM maintains an ownership count; the monitor becomes available to other threads only when all levels have been released.

### Other threads contending for the monitor

A thread that has not yet acquired the monitor upon entering `synchronized` may be in the `Thread.State.BLOCKED` state. When the owner releases the monitor, contenders get a chance to acquire it; the JVM does not guarantee which contender wins in FIFO order or within a specific timeframe. `Thread.interrupt()` does not cause a thread waiting on *monitor entry* to throw `InterruptedException`.

**Do not confuse with `ReentrantLock`:** explicit locks in `java.util.concurrent.locks` have different waiting mechanisms and APIs (`lockInterruptibly`, `tryLock`). `Thread.State.BLOCKED` applies to intrinsic monitors and does not cover all kinds of lock waiting.

## 9. Object.wait/notify: visibility tied to waiting on a condition

When a thread wants to **wait for a condition to change**, simply acquiring the monitor and spinning to check the condition wastes CPU and may hold the monitor for too long. Java provides `Object.wait()`/`notify()`/`notifyAll()` for a condition-wait protocol on an intrinsic monitor.

Correct illustrative pattern:

```java
private final Object guard = new Object();
private boolean ready;
private String value;

void publish(String text) {
    synchronized (guard) {
        value = text;
        ready = true;
        guard.notifyAll();
    }
}

String await() throws InterruptedException {
    synchronized (guard) {
        while (!ready) {
            guard.wait();
        }
        return value;
    }
}
```

These are **members of a class**, not a standalone Java file. Place the `ready` predicate, the `value` data, the `wait` operation, and the notification under the **same monitor**.

Mechanism:

1. The consumer must own the `guard` monitor before calling `guard.wait()`; if called outside monitor ownership, the JVM throws `IllegalMonitorStateException`.
2. `wait()` places the thread into the wait set and **releases the `guard` monitor**, allowing the producer to enter `synchronized(guard)`.
3. The producer writes the data, updates the predicate, and calls `notifyAll()` while still holding the monitor. **`notifyAll()` does not release the monitor itself**: the producer only releases it upon exiting the synchronized block.
4. A woken consumer must **reacquire the monitor** before `wait()` returns. At that point, the producer's updates have been published via the unlock→subsequent lock rule.
5. The consumer rechecks `ready` in a `while` loop because of possible **spurious wakeups**, or because another waiter may have consumed/changed the condition while this thread was waiting to reacquire the monitor.
6. If the producer already published before the consumer entered `wait`, the consumer sees `ready == true` under the lock and **does not need to wait**; the predicate prevents lost notifications.

`Object.wait()` **only releases the monitor of the object on which it is called**. If the thread holds other monitors, `wait` does not automatically release them. `Thread.sleep()` **never releases any held monitor**; using sleep to wait for a condition is a different design and does not provide the notify/reacquire rule.

### Why is notify not an "immediate reader execution" boundary?

Because the producer still holds the monitor from the moment it calls `notifyAll()` until it exits the critical section. The notified thread may have to wait in `BLOCKED` while trying to reacquire the monitor; it cannot proceed into the critical section before then. When multiple consumers are woken by `notifyAll`, each consumer contends for the monitor according to a non-deterministic schedule.

In typical applications, `BlockingQueue`/`CountDownLatch`/`Condition` can be simpler than writing `wait/notify` manually, but the principles of monitor ownership and visibility remain the foundation for understanding the mechanism.

## 10. When is memory visibility not guaranteed by a monitor?

### Reader does not use the same monitor

```java
// Describes a class containing an int field value and Object guard:
void update(int number) {
    synchronized (guard) {
        value = number;
    }
}

int unguardedRead() {
    return value; // does not acquire the same monitor
}
```

This is illustrative code. The unlocked read has no HB edge from the writer's unlock **solely from the monitor rule**. An HB edge might exist from another mechanism in a specific calling scenario, but the API itself cannot claim to be thread-safe just because the writer is synchronized.

### Using two different monitor objects

`synchronized (new Object())` inside each call creates a new monitor every time, so calls do not exclude each other. Two distinct objects, even if `equals` returns true, have independent monitors. Never treat the same variable name or identical string literals as proof of identity.

### Locking one step, leaving another unlocked

If an update consists of "read record, check condition, write record," locking only the write step can still be wrong because the checked value may be stale. You need a critical section covering the entire **invariant transaction** or a logically atomic primitive.

### Instance-level lock for static-level state

An instance synchronized method on object A does not exclude an instance synchronized method on object B. If both write to a `static` field, `synchronized` on each instance **does not** create shared mutual exclusion. You need a lock shared by all writers/readers of the static state, or a redesigned ownership model.

### Publishing a reference while mutable state continues to change

Safe publication of an object does not mean all subsequent mutations are thread-safe. If one thread publishes a reference into a shared map via a queue and then continues mutating its fields without synchronization, another thread reading it may encounter a data race.

## 11. Volatile, atomic, and synchronized solve different requirements

| Requirement | `synchronized` with the same monitor | `volatile` | `AtomicInteger` |
|---|---|---|---|
| Visibility/ordering of properly coordinated accesses | Yes: unlock→lock, HB | Yes: volatile write→read and related JMM rules | Has memory semantics defined by its API |
| Atomic read-modify-write `x++` | **Yes** if the entire operation is in the same critical section | **No**, even if `x` is volatile | **Yes** with `incrementAndGet()` |
| Protecting an invariant spanning multiple fields | **Yes** if the entire group is read/written under one monitor | Does not protect a group transaction | Does not protect a group of multiple atomic variables |
| Reader must use a consistent protocol | Yes | Yes: read the right volatile and follow the publish protocol | Yes: use appropriate atomic operations/snapshots |
| Threads may have to wait for a lock | Yes | No for plain volatile reads/writes | May experience contention/retries on atomics |

Do not treat `volatile` as a "lightweight synchronized." The two mechanisms have different APIs, atomicity, and memory semantics. An independent counter may be a good fit for `AtomicInteger`; fields with an invariant like `total` and `updates` in the example are a good fit for a monitor protecting the entire snapshot.

**Specifically:** `volatile long` guarantees atomicity for a single access, but two volatile accesses do not become a transaction. Similarly, `final` on an object reference does not make the referenced mutable object thread-safe.

A `ReentrantLock` under the `Lock` API provides acquire/release memory effects similar to monitor lock/unlock, while adding capabilities such as timed/interruptible acquisition. When migrating from `synchronized` to `Lock`, you must ensure every access path uses the **exact same lock and `try/finally`**; it is not an automatic performance optimization.

## 12. Subtleties of monitor visibility

### Not every HB relationship requires a monitor

The JMM also defines other edges:

- Actions before `Thread.start()` HB actions in the newly started thread.
- Actions in a terminating thread HB another thread confirming its termination via a successful `join()`.
- A volatile write *synchronizes-with* a matching volatile read in synchronization order.
- `Future.get()`, `BlockingQueue`, and synchronizers in `java.util.concurrent` have their own memory-consistency guarantees.

Therefore, you should not conclude "an unlocked reader will definitely read stale data" if another HB path guarantees visibility. You must evaluate the **complete protocol**. However, a class that uses a monitor to manage state should generally enforce the policy that all normal accesses go through that monitor, rather than implicitly relying on a specific caller having called `join()`.

### Happens-before does not mean a fixed CPU schedule

HB is a relationship over **memory actions** and observation rules, not a promise that thread A will be scheduled right before thread B. A reader might wait for the monitor for a long time, or enter before the writer. Correctness generally must be proven for **all permitted schedules**, not based on results commonly observed on one machine.

### Visibility and atomicity are independent properties

Acquiring the right monitor allows the reader to see published data and prevents reading in the middle of a writer's critical section. However, if the writer **does not combine** the entire invariant update into a single critical section, the reader can still read a state between two separate synchronized blocks; all reads are still valid under HB, but the business invariant was not protected.

Incorrect example:

```java
// Suppose total, updates, and guard are fields of the class:
void addTenWrong() {
    synchronized (guard) {
        total += 10;
    }
    synchronized (guard) {
        updates++;
    }
}
```

This is an illustrative method, not a standalone program. A reader calling `snapshot()` between the two blocks may observe the new `total` with the old `updates`. Fix this by using **one synchronized block enclosing both updates**.

### Lock granularity and performance

Fine-grained locks allow multiple threads to process independent state in parallel; overly coarse locks increase contention. However, splitting a monitor that protects an invariant into two monitors without redesigning the protocol can break correctness. **Prioritize proving the invariant before reducing contention**; actual profiling will show whether monitor overhead is worth optimizing.

## 13. Thread states and diagnostic tools

When a program exhibits high latency or a suspected data race:

1. **Identify monitor identity:** does the code use the same lock object for both writer and reader?
2. **Map all read/write paths:** are there unsynchronized getters, callbacks, or direct accesses from other threads?
3. **Identify invariants requiring atomicity:** is a check-then-act or a two-field snapshot split across multiple critical sections?
4. **Trace HB paths:** which monitor is unlocked, which monitor does the reader lock, and does it enter after the unlock? Are there HB edges from `join`, `Future.get`, volatile, or queues?
5. **Observe contention:** if many threads are `BLOCKED` on a monitor, find the owner and the code holding the lock for too long.
6. **Test for correctness:** generate load with multiple writers/readers and verify invariants; use `CountDownLatch`/barriers to coordinate checkpoints rather than `sleep` as a "guarantee."

Useful tools for Java 17+:

```bash
jcmd <PID> Thread.print -l
```

A thread dump can show `BLOCKED (on object monitor)` and the contended monitor, though it is only a point-in-time snapshot. A thread in `WAITING (on object monitor)` at `Object.wait()` is waiting on a condition; that does not mean it still holds the monitor it is waiting on. A thread in `WAITING (parking)` may be waiting on another primitive, such as an explicit lock.

JFR can help collect contention/wait events over a period of time:

```bash
jcmd <PID> JFR.start name=monitors settings=profile duration=60s filename=monitors.jfr
jfr summary monitors.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait monitors.jfr
```

The commands above apply when the JDK/JVM supports JFR and the process lives long enough. Events may not be enabled or may be filtered by threshold, so **seeing no events does not prove there is no contention**. Use realistic workloads, stack traces, blocked time metrics, and p95/p99 latencies to understand the impact.

**ThreadMXBean:** `java.lang.management.ThreadMXBean` provides APIs to read blocked count/time for monitor contention when supported by the JVM and monitoring is enabled. It is not a measure of all lock waiting, OS context switches, or Java Memory Model correctness. Observability data only helps locate hotspots; correctness must still be grounded in the source code's contract.

## 14. Common mistakes and how to fix them

1. **"Synchronized only prevents two threads from entering at the same time."** Half the picture is missing: monitor unlock→lock also establishes memory ordering/visibility via HB.
2. **"Once the writer locks, the reader can read the plain variable directly."** No such guarantee comes from the monitor rule. The reader must follow the protocol or have another appropriate HB path.
3. **"Two different objects where `equals()` returns true are the same lock."** False: monitors are based on object identity.
4. **"`synchronized(new Object())` on every call protects a shared field."** False: each call uses a new monitor, providing no mutual exclusion across calls.
5. **"Two consecutive synchronized getters form an atomic snapshot."** False: the monitor is released between calls, so a writer can interleave.
6. **"`static synchronized` locks the same monitor as an instance synchronized method."** False: the `Class` object is different from the `this` monitor.
7. **"`count++` on a volatile field is atomic."** False: volatile does not combine read-modify-write into a single atomic action.
8. **"With synchronized, the first thread to call the method will always enter first."** False: `synchronized` does not guarantee FIFO/fairness.
9. **"`notifyAll()` releases the monitor immediately."** False: it only notifies; the caller still holds the monitor until it exits the critical section.
10. **"`wait()` releases all held monitors."** False: it only releases the monitor of the object on which `wait()` is called.
11. **"`sleep()` or `yield()` makes writes safely visible to other threads."** Neither is a synchronization protocol for shared state.
12. **"Having HB means deadlock can never happen."** HB does not prevent lock-order deadlock. Thread A holding lock X waiting for Y, while B holds Y waiting for X, can still fail to make progress.
13. **"An exception makes the JVM forget to release the intrinsic monitor."** Java releases it when the synchronized scope terminates abruptly; however, already mutated state is not automatically rolled back.
14. **"To go faster, just remove synchronized."** Changes must preserve correctness; shorten the critical section or safely partition invariants before deciding to remove a monitor.
15. **"Seeing the right result a million times means there are no races."** Tests are evidence for the schedules that ran; analyzing ownership, HB, and invariants is what explains correctness for all valid schedules.

## 15. Self-check questions with answers

**Question 1.** A writes `x=7` and unlocks monitor `m`; B later locks the same `m` and reads `x`, with no other writers. Could B read the old value because `x` is not volatile?  
**Answer:** No, provided A's unlock precedes B's lock in synchronization order, A's write HB B's read; this is a memory visibility guarantee.

**Question 2.** A uses `synchronized(left)` and B uses `synchronized(right)` on two different objects, and both read/write the same `x`. Is there mutual exclusion and HB via the monitor rule?  
**Answer:** No. The two monitors are independent; they need the same monitor or another synchronization mechanism that creates a valid HB.

**Question 3.** Two writers each perform `count++` 10,000 times under the same monitor; `main` calls `join` on both and then reads `count` under the monitor. What is the result if it starts at 0?  
**Answer:** 20,000. The monitor protects each increment; `join` ensures both writers complete before the read.

**Question 4.** One thread calls a synchronized instance method on `a`, and another thread calls the same method on `b`. Do they contend for the same monitor?  
**Answer:** No, if `a` and `b` are two different instances. Each method locks the `this` of its respective instance.

**Question 5.** Why does a writer update `total` and `updates` under one monitor, yet the reader still needs to read both fields inside a **single critical section**?  
**Answer:** If the reader releases the lock between the two reads, a writer can complete an update in between; the two values could belong to two different logical states.

**Question 6.** A consumer calls `wait()` on object `m` while owning `m`. Does it hold `m` while waiting?  
**Answer:** No. `wait()` releases monitor `m`, and the consumer must reacquire `m` before `wait()` returns. Other held monitors are not automatically released.

**Question 7.** A producer calls `notifyAll()` and then does a long piece of work before exiting `synchronized`. Can a consumer proceed inside the same monitor immediately after the notify?  
**Answer:** No. The producer still owns the monitor; the consumer must wait for the producer to unlock before it can reacquire.

**Question 8.** Is `volatile int counter; counter++;` equivalent to `synchronized(guard) { counter++; }`?  
**Answer:** No. Volatile access provides ordering/visibility, but `counter++` is still a read-modify-write and can lose updates.

**Question 9.** Does a writer unlocking `m` before a reader locks `m` force the reader to always see **that writer's** value, even if a third thread validly modified the value in between?  
**Answer:** Not necessarily. HB guarantees observation and ordering rules, but another writer may update the value before the read; the entire schedule and all relevant writes must be considered.

**Question 10.** If `synchronized` solves correctness, can there still be performance or liveness issues?  
**Answer:** Yes. Holding a monitor for too long causes contention; nesting multiple monitors inconsistently can cause deadlock; the scheduler does not guarantee fairness. Data correctness and progress/performance are properties that must be evaluated separately.

## References

- [Java Language Specification, Java SE 17 `17.1 — Synchronization`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1): monitor, lock/unlock, mutual exclusion.
- [JLS `17.4.4 — Synchronization Order`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.4): *synchronizes-with* rule for unlock/lock.
- [JLS `17.4.5 — Happens-before Order`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5): program order, synchronizes-with, HB, correctly synchronized.
- [JLS `14.19 — synchronized Statement`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19): scope of synchronized and abrupt completion.
- [Java SE 17 Object API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): `wait`, `notify`, `notifyAll`, and monitor ownership conditions.
- [Java SE 17 Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): `BLOCKED`, `WAITING`, and thread states.
- [Java SE 17 ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): task management and memory consistency.
- [Java SE 17 Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion and memory consistency via `get()`.

**Key takeaway:** mutual exclusion prevents threads using the **same monitor** from interleaving inside each other's critical sections; memory visibility comes from the **unlock(m) → subsequent lock(m)** edge in the Java Memory Model. For a correct program, both writers and readers must follow a consistent protocol, and the **entire logical invariant** must be enclosed within the protected scope.