# Data Races and Unpredictable Observed Behavior in the Java Memory Model

## 1. The problem: why do multithreaded results differ from reading code sequentially?

In a multithreaded Java program, two threads can run interleaved or in parallel and access the same data at unpredictable times. A thread also does not necessarily observe writes from another thread immediately. Without **proper synchronization relationships**, a program can lose updates, see stale values, observe inconsistent state, or wait forever for a signal that has already been emitted.

Two different aspects must be considered:

- **Scheduling:** when threads get a chance to execute; this order depends on the JVM, OS, and machine state.
- **Java Memory Model (JMM):** rules specifying which values a read is allowed to observe; the **happens-before** relationship ensures visibility and ordering between threads.

A change in log order is not always a bug. If two independent tasks print two lines, either order can be valid. The problem arises when correctness relies on an ordering or an observation that the JMM **does not guarantee**.

## 2. Data race as defined by the JMM

Two actions accessing a variable are called **conflicting** when they access the same variable and at least one of them is a write. A program has a **data race** if there exist two conflicting actions that **are not ordered by a happens-before relationship**.

As an illustrative example, with a shared `int value` field:

```java
// Thread A:
shared.value = 1;

// Thread B:
int observed = shared.value;
```

The snippet above only illustrates two code fragments from two threads, **not a standalone Java file**. Without `synchronized`, `volatile`, thread start/join, or other synchronization establishing an appropriate happens-before relationship, you cannot rely on A "usually running first" to conclude that B will observe 1.

### Distinguishing easily confused concepts

| Concept | Problem | Example |
| --- | --- | --- |
| **Data race** | Conflicting accesses to the same variable not ordered by happens-before | One thread writes a plain field, another thread reads it without synchronization |
| **Race condition** | Correctness depends on timing or interleaving order | Two requests both see one unit of inventory left and both sell it |
| **Atomicity violation** | A sequence of operations that must be treated as one logical step gets interleaved | Two threads run `counter++` and lose an update |
| **Visibility problem** | No guarantee that another thread sees the change | A loop waiting on a plain `done` flag never terminates |
| **Ordering problem** | Actions are observed differently from reasoning based on source code order | A thread sees the ready flag but has not yet seen the corresponding data |

**A data race and a race condition are not identical.** Two threads executing `volatileCounter++` on a `volatile int` field can lose updates even though the individual volatile accesses are synchronization actions. This is an **atomicity race condition**, without needing a data race under the JMM definition.

Conversely, a data race does not mean every run will produce a wrong result; it permits observations that a program must not rely on.

## 3. Three categories of unpredictable observed behavior

### 3.1. Lost update: an increment is not an atomic step

Suppose two threads both execute `count++`. The logical meaning of the increment is:

```text
old = count
newValue = old + 1
count = newValue
```

If both read `old = 0` before writing, both write 1 and one increment is lost. With a plain `int` field, these accesses can create a data race; with a `volatile int` field, the separate read and write still do not combine into an atomic increment operation.

### 3.2. Visibility: a completion flag is not always seen

```java
// Illustration: finished is a shared plain boolean field.
while (!finished) {
    // spin
}
```

The writer may have set `finished = true`, but without happens-before, the JMM does not guarantee the reader will see the change. The JVM may optimize the loop and the thread may keep reading the stale value. `Thread.sleep()` or `Thread.yield()` does not add any data publication guarantee.

The fact that `boolean` is read/written atomically at the data-type level still does not mean **visibility** is guaranteed across threads.

### 3.3. Ordering: seeing the signal does not guarantee seeing the content

```java
// Writer, illustrative snippet only:
payload = 42;
ready = true;

// Reader, illustrative snippet only:
if (ready) {
    System.out.println(payload);
}
```

If both `payload` and `ready` are plain fields, accesses are unsynchronized, and the two snippets run on two threads, you cannot conclude "reading `ready` as `true` ⇒ `payload` is definitely read as 42". The writer's program order **does not by itself create** a happens-before relationship from writer to reader.

This can be fixed with a publication protocol: the writer writes `payload` first, then writes **volatile** `ready`; the reader reads volatile `ready` before using `payload`. With multiple producers or multiple updates, you must also consider post-publication mutations and the atomicity of the entire state.

## 4. Java 17+: controlled reproduction of a lost update

Create the file `ForcedLostUpdate.java`:

```java
import java.util.concurrent.CountDownLatch;

public class ForcedLostUpdate {
    private static final class Box {
        int count;
    }

    public static void main(String[] args) throws InterruptedException {
        Box box = new Box();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int old = box.count;
            bothRead.countDown();
            try {
                mayWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            box.count = old + 1;
        };

        Thread a = new Thread(increment, "A");
        Thread b = new Thread(increment, "B");
        a.start();
        b.start();

        bothRead.await();
        mayWrite.countDown();
        a.join();
        b.join();

        System.out.println("Correct total: 2");
        System.out.println("Actual total: " + box.count);
    }
}
```

Compile and run:

```bash
javac ForcedLostUpdate.java
java ForcedLostUpdate
```

Output on normal completion:

```text
Correct total: 2
Actual total: 1
```

Both workers read 0 **before** calling `bothRead.countDown()`. Main only opens `mayWrite` after both have reached this checkpoint. Therefore both workers write `old + 1`, which is 1, regardless of who writes first. The two writes to the same plain variable are not ordered by happens-before with respect to each other, so there is a data race; `join()` only ensures main waits and sees the workers' effects after they finish. The result 1 here is due to the controlled interleaving design, not a promise that every program using `count++` returns 1.

**Takeaway:** using latches to reproduce an interleaving is a good testing tool, but the latches themselves in this example intentionally do **not** protect the increment; all threads only write the old value after passing the barrier.

## 5. Java 17+: fixing with atomic increment

Create the file `AtomicCounterDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger count = new AtomicInteger();

        Runnable increment = () -> {
            for (int i = 0; i < 10_000; i++) {
                count.incrementAndGet();
            }
        };

        Thread a = new Thread(increment, "A");
        Thread b = new Thread(increment, "B");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Final count: " + count.get());
    }
}
```

Run:

```bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
```

Output:

```text
Final count: 20000
```

`AtomicInteger.incrementAndGet()` is an atomic increment: two updates cannot succeed based on the same old state in a way that loses an increment. The two threads still run in whatever order the scheduler chooses, but the final result is guaranteed. `join()` ensures main only reads after both have finished.

If multiple fields must change together under an invariant (for example, quantity and order status), multiple separate `AtomicInteger` instances do **not** automatically form a transaction. In that case, you need a shared lock, CAS on an immutable state object, or another protocol covering the entire invariant.

### When to use `synchronized`?

```java
final class SafeCounter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int get() {
        return value;
    }
}
```

This is a helper class **without a standalone `main`**. Calls use the same monitor of the `SafeCounter` object, so no two threads execute the increment on the same object concurrently. `get()` also uses that monitor, ensuring a happens-before relationship through lock release/acquisition. If external code has a read/write path that does not follow the same lock, the design still has a hole.

## 6. Happens-before is the foundation of visibility and ordering

The JMM uses **happens-before (HB)** to denote a partial order relationship between actions. Some key rules:

| Relationship source | Main guarantee |
| --- | --- |
| **Program order** | Within a single thread, an earlier action in program order HB a later action |
| `Thread.start()` | A `start` call on a thread HB actions in the new thread |
| Successful `Thread.join()` | Actions of the worker HB another thread detecting that the worker has terminated |
| `synchronized` monitor | Unlocking a monitor HB a subsequent lock on the **same monitor** |
| `volatile` field | A volatile write HB a subsequent volatile read of the **same field** in synchronization order |
| `CountDownLatch` | Actions before `countDown()` HB actions after a successful `await()` |
| Concurrent library | `BlockingQueue`, `Future`, `Executor`, and other primitives have memory-consistency guarantees in their API contracts |

The HB relationship is **transitive**. If A HB B and B HB C, then A HB C; thus, plain data writes before a volatile signal can be published to a reader after the reader reads the appropriate signal.

HB is a relationship about observation semantics, **not simply** "A is physically executed by the CPU before B". When `main` calls `a.start(); b.start();`, there is no guarantee that all actions of A occur before all actions of B. When `main` calls `a.join(); b.join();` in sequence, `main` can see the results of both, but joining **does not by itself order all operations between A and B**.

**Note:** `Thread.sleep()`, `Thread.yield()`, `setPriority()`, and logging should not be used as data synchronization primitives. They may alter timing, but they do not replace the required HB relationship.

## 7. Java 17+: safely publishing a non-volatile result

If a thread only needs to notify that a result has been produced, `CountDownLatch` expresses the event better than a hand-rolled spin loop.

Create the file `SafePublicationDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class SafePublicationDemo {
    private static int result;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread producer = new Thread(() -> {
            result = 42;
            ready.countDown();
        }, "producer");

        producer.start();
        ready.await();
        System.out.println("Result: " + result);
        producer.join();
    }
}
```

Run:

```bash
javac SafePublicationDemo.java
java SafePublicationDemo
```

Output:

```text
Result: 42
```

The writer writes `result = 42` before `countDown()`. When `ready.await()` returns normally, actions before `countDown()` happen-before actions after `await()`. Therefore `main` sees 42 right after `await` even though `result` is a plain field. The final `join()` is to confirm the producer lifecycle has ended, not the sole condition creating visibility in the example.

A `volatile boolean ready` flag can be used for a single-writer one-time publication protocol:

```java
// Idea for two fields of the same object:
private int payload;
private volatile boolean ready;

// Writer: payload = 42; ready = true;
// Reader: if (ready) System.out.println(payload);
```

This is a **conceptual snippet**, not a standalone Java file. If the reader observes the matching volatile write `ready = true`, prior writes in the writer have an HB relationship with reads after the flag in the reader. However, `volatile` does not make multi-field updates atomic, and busy-waiting should not be overused when a latch or queue can be used.

## 8. Both threads reading 0: the store buffering example

Consider two fields `int x = 0` and `int y = 0`, unsynchronized:

```text
Thread A              Thread B
--------              --------
x = 1                 y = 1
r1 = y                r2 = x
```

If you try to impose a single sequential interleaving order on the four operations, `r1 == 0` and `r2 == 0` cannot happen simultaneously: for A to read `y` as 0, A must read before B writes `y`; for B to read `x` as 0, B must read before A writes `x`, creating a cycle that contradicts each thread's internal instruction order.

However, in a program **with a data race**, the JMM permits the `r1 == 0, r2 == 0` outcome in this store buffering problem. Therefore, you cannot analyze every racy program merely by permuting source lines into an intuitive sequential schedule. Compilers, the JIT, caches, and hardware may apply optimizations within the bounds of the specification.

This is an example of **a permitted outcome**, not an outcome guaranteed to appear on a specific JVM, machine, or run. If both `x` and `y` are `volatile`, the "both read 0" outcome is ruled out by the consistent synchronization order for volatile accesses in this scenario. That does **not** mean any algorithm with multiple volatile fields forms a transaction.

## 9. A Java data race is not completely equivalent to C/C++ undefined behavior

You should not describe the JMM with a blanket statement like "anything can happen". Java still has rules constraining the values a read is allowed to observe, even in programs with data races. However, **the set of valid outcomes is broader** and can differ greatly from how a programmer reasons using a simple interleaving schedule. Thus, racy programs remain unreliable.

An important principle is **data-race-free ⇒ sequentially consistent** within the conditions of the JMM: when data accesses are properly synchronized, programmers can reason more conveniently using a sequential interleaving. However, **sequential consistency does not make all multi-step operations atomic**: the algorithm must still protect each invariant individually.

### Non-volatile `long` and `double` fields

The Java specification allows some implementations to treat reads/writes of non-volatile `long` or `double` fields as two 32-bit halves, potentially observing **torn** values under unsynchronized shared access. Many modern JVMs provide atomicity in practice, but portable code should not rely on that coincidence. `volatile long`/`volatile double` guarantees atomicity for each individual read/write, while `AtomicLong` is suitable for atomic increments/updates.

The atomicity of **a single read or write** is not equivalent to the atomicity of **the entire algorithm**.

## 10. Final, immutable data, and safe publication

Reducing shared mutable state is a useful way to reduce race risks. `final` fields assigned during proper construction have special JMM guarantees, especially when `this` does not escape to another thread before the constructor finishes.

```java
final class Snapshot {
    final int id;
    final String label;

    Snapshot(int id, String label) {
        this.id = id;
        this.label = label;
    }
}
```

This is a helper class, without `main`. `String` is immutable, so a snapshot consisting of values like the above is easier to share than an object whose state continuously changes. However, `final` does not make mutable objects referenced by a field immutable; nor does it replace publishing the reference through a proper protocol.

Common publication approaches are placing the reference via a `volatile` field, `AtomicReference`, `BlockingQueue`, `synchronized`, or creating threads after the object has finished constructing. Avoid starting a thread inside a constructor and letting `this` escape while the state is incomplete.

## 11. Choosing a synchronization mechanism by goal

| Need | Suitable Java tool | Things to watch out for |
| --- | --- | --- |
| Wait for another thread to finish | `Thread.join()` | A timed join can return before the thread has finished |
| Publish a completion signal | `CountDownLatch`, `Future` | Need to handle interrupts, timeouts, and task errors |
| Simple shared flag with a clear protocol | `volatile boolean` | Visibility/ordering, does not replace atomicity |
| Counter that must increment accurately | `AtomicInteger` | `counter++` on `volatile` can still lose updates |
| Multiple fields sharing an invariant | `synchronized`, `Lock` | All related read/write paths must use the same protocol |
| Transfer data between producer/consumer | `BlockingQueue` | Transfers ownership and memory-consistency effects |
| Per-key state | `ConcurrentHashMap` | Distinguish atomic API operations from multi-call sequences |
| Read-only snapshot | Immutable object + safe publication | Do not mutate the object after publication; avoid constructor escape |

An API is only safe within its **specific contract**. For example, `ConcurrentHashMap.containsKey()` followed by `put()` are two separate operations; if you need an atomic "put if absent", use `putIfAbsent()` or an appropriate API instead of splitting check–act.

## 12. Testing and diagnosis

1. **List shared mutable state:** instance/static fields, arrays, collections, objects referenced by multiple threads.
2. **Find conflicting accesses:** is there at least one writer, and are reads/writes from other threads ordered by HB?
3. **State the invariants to preserve:** no lost updates, no reading data before publication, no exposing intermediate results.
4. **Create interleavings in tests:** `CountDownLatch` or `CyclicBarrier` forces workers to reach the same checkpoint to reproduce a race; do not use arbitrary sleeps as a "fix".
5. **Stress test across load levels:** increase worker count, data size, and vary environments. Zero failures in 10,000 runs **does not prove** a program is data-race-free.
6. **Use the right tools:** jcstress (OpenJDK) can test the outcome sets of concurrency litmus tests; JFR, thread dumps, and profilers help with lock contention and runtime state. Tools do not replace JMM analysis.
7. **Evaluate failure paths as well:** a thread dying before `countDown()` can cause other threads to wait indefinitely; design timeouts, interrupts, and error handling according to business requirements.

## 13. Common misconceptions

- **"One successful run proves there is no data race."** False; bugs depend on execution schedules and observable behavior can be very rare.
- **"Volatile solves all races."** False; `counter++` is still a read–modify–write.
- **"`sleep(100)` guarantees the worker has finished writing."** False; sleep does not wait for a real condition and creates no happens-before.
- **"One thread starts first so its writes are guaranteed to appear before a thread started later."** False; `start` only establishes a relationship from the calling thread to the new thread, not a total order of all actions between two workers.
- **"Per-field atomicity means multi-field transaction atomicity."** False; the entire invariant must be protected.
- **"Putting a lock on the writer is enough."** False if readers still read without synchronization and without a proper publication/visibility mechanism.
- **"Data races always yield arbitrary random values."** False; the JMM constrains valid observations, even though the outcome set is broad and hard to reason about.
- **"No data races means all concurrent logic is correct."** False; multi-step check-then-act bugs can still occur when each individual access is atomic.

## 14. Practical checklist

Before accepting code that shares data across threads, ask yourself:

1. Which variables are mutable, which are shared, and which threads read/write them?
2. Is there any pair of conflicting accesses not ordered by happens-before?
3. Is the requirement to see published data, or to execute an entire update sequence atomically?
4. Was the right primitive chosen: `volatile`, atomic, latch, lock, queue, `Future`, or immutable snapshot?
5. Do all related read/write paths follow the same protocol?
6. Can timeouts, interrupts, and task failures cause a missing signal or reading partial state?
7. Does the promised result hold under **every valid schedule and observation** of the JMM?

**Remember:** a data race consists of conflicting accesses without a proper happens-before order; it allows observed behaviors that differ from sequential code-reading intuition. Design clear synchronization relationships and protect the atomicity of invariants, rather than expecting the scheduler to run threads in a desired order.