# Distinguishing Visibility and Mutual Exclusion in the Java Memory Model

When multiple threads share mutable data, two requirements are often confused as one: **will a reading thread see the value written by another thread?** (*visibility*) and **can two threads modify the same state at the same time?** (*mutual exclusion*). Java provides different tools for each need. Understanding this boundary clearly helps avoid bugs such as "used `volatile` yet the counter is still wrong" or "locked the writer yet the reader still sees inconsistent data".

This article explains these concepts based on the **Java Memory Model (JMM)** and standard Java APIs; it does not depend on framework-specific concurrency mechanisms.

## 1. Four concepts that often go together

| Concept | Question to answer | Example |
| --- | --- | --- |
| **Visibility** | Once one thread has written, is another thread guaranteed to observe that value according to a synchronization relationship? | Writer sets `ready=true`; reader needs to see the change |
| **Mutual exclusion** | Does it prevent multiple threads from entering a critical section protecting the same data at the same time? | Only one thread may check and deduct inventory at a time |
| **Atomicity** | Is the business operation observed as a single indivisible step without interleaving? | `count++` must be one complete increment |
| **Ordering** | What ordering constraints apply to read/write operations as observed by other threads? | Write `payload` before publishing `ready` |

**Visibility does not imply mutual exclusion.** Two threads can both read the latest value at the moment they read, yet still compute from the same snapshot and overwrite each other's updates. **Proper mutual exclusion usually provides the necessary visibility**, because monitor/lock synchronization has happens-before rules; however, **the same lock** must be used across all relevant read and write paths.

Atomicity is an operation-level goal; mutual exclusion is **one way** to achieve atomicity. An operation like `AtomicInteger.incrementAndGet()` is also atomic without requiring the programmer to wrap it in `synchronized`. Conversely, reading two separate `volatile` fields does not create an atomic snapshot of the pair.

## 2. What is visibility?

Suppose an object has two fields:

```java
class Message {
    int payload;
    boolean ready;
}
```

One thread executes `payload = 42; ready = true;`. Another thread loops until `ready` is true and then reads `payload`. If both fields are regular fields and there is no synchronization mechanism, the JMM **does not guarantee** that the reader will observe the `ready` update within a finite time, nor does it guarantee that it will see `payload=42` simply by reasoning from the writer's source code order.

The reason: for conflicting accesses without a happens-before relationship, the JVM/JIT and CPU may apply optimizations, caches/registers, and execution orders permitted by the JMM; different threads may observe different results. Do not assume "the CPU always re-reads RAM on every loop iteration" or "increasing `sleep` will synchronize caches". Neither establishes Java's memory visibility contract.

### `volatile` as a way to publish a signal

If `ready` is declared `volatile`:

```java
class Message {
    int payload;
    volatile boolean ready;
}
```

Writer:

```java
message.payload = 42;
message.ready = true;
```

Reader:

```java
if (message.ready) {
    System.out.println(message.payload);
}
```

These are **illustrative snippets**, assuming the writer and reader reference the same `message` instance. A `volatile` write establishes a *synchronizes-with* relationship with a matching `volatile` read in the synchronization order. If the reader reads `ready` and sees the value `true` published by the writer, the writer's prior writes (including `payload=42`) are properly visible according to the happens-before relationship.

**Limitation:** this model assumes no other thread modifies `payload` without synchronization or reuses `ready` improperly outside the protocol. `volatile ready` is a **publication** mechanism for a prepared message; it does not protect all future operations on `payload`. The reader must actually observe the flag; the `if` code in the example only enters the body if the flag is already true.

### Standalone Java 17 example: passing a message using `volatile`

Create the file `VolatilePublicationExample.java`:

```java
import java.util.concurrent.locks.LockSupport;

public class VolatilePublicationExample {
    static class Message {
        int payload;
        volatile boolean ready;
    }

    public static void main(String[] args) throws InterruptedException {
        Message message = new Message();
        int[] received = {-1};

        Thread reader = new Thread(() -> {
            while (!message.ready) {
                // Reduce busy spinning, not a visibility mechanism.
                LockSupport.parkNanos(1_000_000L);
            }
            received[0] = message.payload;
        });

        Thread writer = new Thread(() -> {
            message.payload = 42;
            message.ready = true;
        });

        reader.start();
        writer.start();
        writer.join();
        reader.join();

        System.out.println("payload=" + received[0]);
    }
}
```

Run with JDK 17+:

```bash
javac VolatilePublicationExample.java
java VolatilePublicationExample
```

Stdout when the program completes normally:

```text
payload=42
```

Why is this correct?

1. The writer writes `payload=42` before `ready=true` in the same thread.
2. The reader continuously reads the **volatile field** `ready`; when it sees `true`, the happens-before relationship guarantees that the writer has published the payload.
3. The reader writes the result into `received[0]`; `main` only reads after `reader.join()`. Completing `join` successfully provides the guarantee of observing the reader's actions.
4. `LockSupport.parkNanos` only helps avoid 100% CPU spinning in the example; it **does not replace `volatile`**. Production code typically uses `BlockingQueue`, `CountDownLatch`, or a waiting mechanism with a deadline to avoid polling.

From a testing perspective, running the example successfully is not empirical proof that removing `volatile` will always fail. The non-`volatile` version lacks a memory visibility contract; it might still happen to print `42` on a given machine. Correctness reasoning comes from the JMM.

## 3. What is mutual exclusion?

**Mutual exclusion** is the guarantee that at most one thread at a time can execute a section of code requiring exclusive access over **the same resource/lock**.

For example, a withdrawal method consists of two operations: checking whether the balance is sufficient and deducting the amount. If two threads can interleave between these two steps, both can see the same old balance and both withdraw. To preserve the invariant `balance >= 0`, we must treat **the entire check + update** as a single protected unit.

```java
class BankAccount {
    private int balance = 100;

    synchronized boolean withdraw(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("amount < 0");
        }
        if (balance < amount) {
            return false;
        }
        balance -= amount;
        return true;
    }

    synchronized int balance() {
        return balance;
    }
}
```

This is a **class snippet**, without `main`. A `synchronized` instance method uses the monitor of `this`. For **the same `BankAccount` instance**, two threads cannot run `withdraw` at the same time. `balance()` also goes through the same monitor, helping readers observe a consistent state under the locking protocol.

Mutual exclusion also provides visibility: when thread A releases a monitor and thread B later acquires **the same monitor**, A's monitor release *happens-before* B's monitor acquisition. However, if the writer locks `lockA` while the reader locks `lockB`, there is neither mutual exclusion nor monitor handoff between those two locks.

## 4. `volatile` provides visibility but does not block other threads from entering

A `volatile int count` variable has volatile visibility/ordering semantics for individual reads and writes. However, the increment:

```java
count++;
```

is still a **read–modify–write** at the logical level. A valid execution schedule can look like this:

| Step | Thread A | Thread B | `count` |
| --- | --- | --- | --- |
| Initial | | | `0` |
| 1 | Reads `0` | | `0` |
| 2 | | Reads `0` | `0` |
| 3 | Computes and writes `1` | | `1` |
| 4 | | Computes and writes `1` | `1` |

Both threads read the actual value present at the time they read; no "stale cache read" problem even needs to occur. Yet **two increments are only counted once**. `volatile` does not protect a critical section and does not combine read–modify–write into one atomic step.

### Java 17 experiment: forcing a lost update despite `volatile`

The following program intentionally separates the read and write to place a barrier between the two steps. This is a **test that coordinates a dangerous logical schedule**, not a benchmark or a proof of a JMM-level data race in all program variants.

Create `VolatileIsNotMutexExample.java`:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;

public class VolatileIsNotMutexExample {
    static class Counter {
        volatile int value;
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CyclicBarrier bothRead = new CyclicBarrier(2);

        Runnable increment = () -> {
            int old = counter.value;
            try {
                bothRead.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            } catch (BrokenBarrierException e) {
                throw new IllegalStateException(e);
            }
            counter.value = old + 1;
        };

        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("expected=2, actual=" + counter.value);
    }
}
```

```bash
javac VolatileIsNotMutexExample.java
java VolatileIsNotMutexExample
```

Stdout on a normal run, when both workers reach the barrier:

```text
expected=2, actual=1
```

Why the deterministic result: both workers read `0` before `CyclicBarrier(2)` lets either worker pass and write. Then both compute `0+1`. Regardless of which thread writes last, the value remains `1`. This scenario demonstrates that **operating on volatile state can still lose updates at the business-logic level**. The barrier creates synchronization in the test; do not conclude from this test alone that Java necessarily produces a formal data race on every run.

**Test limitations:** the example omits a deadline on the barrier to focus on the core idea. Production/test suites should use `await(timeout, unit)` and propagate worker exceptions to the test thread via `Future.get()` to avoid hanging if a participant is missing or a task fails. Do not use `Thread.sleep` instead of a barrier to try to force a deterministic schedule.

## 5. `synchronized` provides both mutual exclusion and visibility

`synchronized` has two important effects:

1. **Mutual exclusion:** only one thread owns the same intrinsic monitor at a time. A critical section can protect multiple fields as a unified invariant.
2. **Memory visibility/ordering:** an `unlock` action on a monitor happens-before a subsequent `lock` action on the same monitor. Writers and readers following the same monitor can see the state published by the synchronization protocol.

Example:

```java
class SynchronizedCounter {
    private int count;

    public synchronized void increment() {
        count++;
    }

    public synchronized int get() {
        return count;
    }
}
```

This is a **class snippet**; when all read and write paths to `count` go through methods using the same monitor of **the same instance**, `increment()` cannot be interleaved by another `increment()`. Adding `volatile` to the field here is usually unnecessary.

### Program comparing `synchronized` and atomic operations

Create `SafeCounterComparison.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class SafeCounterComparison {
    static class LockedCounter {
        private int count;

        synchronized void increment() {
            count++;
        }

        synchronized int get() {
            return count;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        LockedCounter locked = new LockedCounter();
        AtomicInteger atomic = new AtomicInteger();

        Runnable task = () -> {
            for (int i = 0; i < 100_000; i++) {
                locked.increment();
                atomic.incrementAndGet();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("synchronized=" + locked.get());
        System.out.println("atomic=" + atomic.get());
    }
}
```

```bash
javac SafeCounterComparison.java
java SafeCounterComparison
```

Stdout:

```text
synchronized=200000
atomic=200000
```

**Why is it correct?** `locked.increment()` acquires the same monitor. `atomic.incrementAndGet()` is an atomic update operation with the corresponding memory semantics contract; it does not require the programmer to hold an external monitor. `join()` waits for both threads to finish before `main` reads the results, so there is no "reading too early".

This is **not a benchmark** proving `AtomicInteger` is always faster than `synchronized`. Speed depends on contention level, JVM, core count, hotspot behavior, and workload type. Choose based on the correctness of the operation to be protected first.

### Important limitations of `synchronized`

- A `synchronized` method on object A **does not** prevent another thread from running `synchronized` on object B. The same data must be protected by **the same lock identity**, not just "the same keyword".
- `static synchronized` acquires the monitor of the `Class` object, which is different from the monitor of an instance `synchronized` method.
- A writer locking while a reader reads the field directly without locking can still have visibility/consistency issues. All read/write paths belonging to the protocol must follow the same rule.
- Java monitors are reentrant: a thread can re-acquire a monitor it already holds; however, nested locks on **different monitors** still carry deadlock risk.
- Do not hold a monitor too long for I/O, `sleep`, or waiting on a `Future` unless necessary: other threads will enter `BLOCKED` while trying to acquire the same monitor.
- `Thread.sleep` does not release a monitor. `Object.wait` releases the monitor **of the specific object on which `wait` is called** while waiting and re-acquires it before returning.
- `synchronized` does not promise fairness, wake-up order, or optimal throughput.

## 6. Tool selection table by requirement

| Tool | Visibility | Mutual exclusion | Atomic read–modify–write | Typical suitable scope |
| --- | --- | --- | --- | --- |
| Regular `int`/`boolean` field, unsynchronized | No cross-thread guarantee for racy data | No | No for `++`/`--` | Local access only or wrapped by another protocol |
| `volatile` field | Yes, per volatile happens-before/ordering | **No** | Individual reads/writes have volatile semantics; `x++` is still not atomic | Stop flags, one-way data publication, reference snapshots |
| `synchronized` on the same monitor | Yes, via unlock → lock | **Yes** | Can protect **entire** compound operations in a critical section | Multi-field invariants, check–then–act |
| `ReentrantLock` / `Lock` with proper protocol | Yes, via lock/unlock memory semantics | **Yes** | Can protect compound operations | Need `tryLock`, timed lock, interruptible acquisition, `Condition` |
| `AtomicInteger` / `AtomicLong` | Yes, per atomic API memory effects | **Does not lock arbitrary code blocks** | **Yes** for `incrementAndGet`, `compareAndSet`, and atomic methods | Single variable / atomic operation |
| `AtomicReference` with CAS | Yes, per atomic API memory effects | Does not lock external operations | Yes for updating **a single reference** via CAS | Immutable state snapshot, versioned updates |
| `LongAdder` | Has thread-safety contract suitable for updates | No | Each add is safe, but `sum()` is not an atomic snapshot under concurrent updates | High-writer metrics where an instantaneous linearizable sum is not required |
| `BlockingQueue` / concurrent collection | Guaranteed per handoff/operation contract | Implementation-dependent; does not lock an entire workflow | Per individual operation guaranteed by the API | Producer–consumer, keyed maps |
| Immutable object + safe publication | Stable reads when published validly | No lock needed to read a truly immutable object | No in-place updates | Configuration data, snapshots |

**Reading the "AtomicInteger" row:** the `incrementAndGet` operation is atomic, but the sequence `if (count.get() > 0) count.decrementAndGet()` can still fail when multiple threads run concurrently. Atomicity has a **scope**: one atomic method does not automatically turn an entire workflow into an atomic transaction.

**Reading the "volatile" row:** Java guarantees that individual volatile reads/writes have appropriate semantics and atomicity for a single field access; what is **not guaranteed** is that multiple accesses together form an atomic operation. Therefore, do not say "volatile is completely non-atomic" without nuance.

## 7. `ReentrantLock` and visibility

`java.util.concurrent.locks.ReentrantLock` provides mutual exclusion and memory semantics like a traditional lock, with added features such as `tryLock`, `lockInterruptibly`, and `Condition`s. Successful lock acquisition and release have synchronization effects; readers and writers **must use the same lock instance** for the corresponding data.

Java 17 class example, usable in a Java file but **without `main`**:

```java
import java.util.concurrent.locks.ReentrantLock;

class Inventory {
    private final ReentrantLock lock = new ReentrantLock();
    private int stock = 1;

    boolean sellOne() {
        lock.lock();
        try {
            if (stock == 0) {
                return false;
            }
            stock--;
            return true;
        } finally {
            lock.unlock();
        }
    }

    int currentStock() {
        lock.lock();
        try {
            return stock;
        } finally {
            lock.unlock();
        }
    }
}
```

Every stock update and read in the class uses **the same lock**, so it both prevents overselling when starting with one item and ensures visibility on reads. Always call `unlock()` in `finally` after a successful `lock()`; forgetting to release the lock can cause other threads to wait indefinitely.

**Do not confuse `Lock` with `volatile`**: a `volatile boolean available` can help multiple threads see the new flag value, but it does not stop two threads from both seeing `true` before either flips it to `false`. If a condition and an update must happen together, choose a lock or an appropriate atomic compare-and-set.

## 8. Making an operation atomic without locking an entire critical section

Suppose inventory is just a single integer. `AtomicInteger` has `compareAndSet(expected, update)`: it only changes the value if the actual value still equals `expected` at the moment the atomic operation executes. From this, you can build a CAS loop to guard the stock deduction condition:

```java
import java.util.concurrent.atomic.AtomicInteger;

class AtomicInventory {
    private final AtomicInteger stock = new AtomicInteger(1);

    boolean sellOne() {
        while (true) {
            int current = stock.get();
            if (current == 0) {
                return false;
            }
            if (stock.compareAndSet(current, current - 1)) {
                return true;
            }
        }
    }

    int currentStock() {
        return stock.get();
    }
}
```

This is an illustrative class without `main`. Two threads both read `1`: only one CAS operation succeeds in transitioning `1 → 0`. The other thread fails, re-reads `0`, and returns `false`. Thus, a single-variable condition is still preserved **without an explicit mutex**.

**CAS limitations:** if an update involves multiple fields or external side effects (sending an email, charging a remote API), a CAS on a single integer cannot combine all effects. A CAS loop can retry; **do not place non-idempotent side effects inside callbacks/logic that may re-run**. For multiple variables forming a single invariant, consider a shared monitor/lock or an immutable aggregate replaced via `AtomicReference` under a proper protocol.

## 9. Does visibility mean "always seeing the latest value"?

Visibility should not be phrased as "every thread always sees a newly written value instantaneously in wall-clock time". The JMM defines ordering and synchronization relationships that allow threads to observe data according to a contract. With `volatile`, synchronized reads/writes have an appropriate order; however:

- A reader only knows a flag was published if it **actually reads it**.
- The reader may not have been scheduled to run yet, so there is no absolute latency guarantee.
- If the writer continuously updates another field without a matching protocol, reading the flag once does not turn other fields into an indefinitely consistent snapshot.
- `volatile` does not replace data ownership, liveness guarantees, timeouts, or business conditions.

For example: the writer publishes `payload` and then sets `ready=true`, which is a simple handoff protocol. If the writer later modifies `payload` while the reader is reading, additional coordination/immutability is required; the initial publication does not protect subsequent updates.

## 10. Key happens-before relationships to remember

The JMM uses the *happens-before* relationship to define ordering and visibility effects between actions. This is **not simply whether A happened before B on a wall clock**.

1. **Within the same thread:** an earlier action happens-before a later action in *program order*.
2. **Monitor:** unlocking a monitor happens-before a **subsequent** lock on the same monitor.
3. **Volatile:** a write to a volatile field happens-before a subsequent read of that same volatile field according to JMM synchronization rules.
4. **Thread start:** a call to `Thread.start()` happens-before any actions inside the new thread.
5. **Thread join:** actions of a completed thread happen-before another thread successfully observes its termination via `join()`.
6. **Concurrency utilities:** many APIs in `java.util.concurrent` specify memory-consistency effects, such as `BlockingQueue` handing off an object or `Future.get()` after task completion.
7. **Transitivity:** if A happens-before B and B happens-before C, then A happens-before C.

**Happens-before is not a mutex.** `Thread.join()` can help `main` see the results of two workers after they finish, but it **does not fix lost updates** that the two workers caused while running. Similarly, a volatile signal between a producer and a consumer can publish data, but two producers concurrently modifying the same state still need a protocol to prevent interleaving.

## 11. Designs that typically need visibility without a mutex

### 11.1. One-way stop flag

`volatile boolean running = true;` is suitable when one thread continuously checks the flag and another sets `false` to request termination. Ensure the code handles the signal and does not get stuck in a blocking call that ignores the flag. For blocking I/O, thread interruption and cancellation APIs may be more appropriate or needed in combination.

### 11.2. Publishing an immutable snapshot

The writer creates a truly immutable snapshot object and assigns it to a `volatile` reference. The reader reads **one reference** and uses that entire snapshot. This avoids reading mixed versions across multiple fields.

```java
record Snapshot(int x, int y) {}

class Holder {
    volatile Snapshot current = new Snapshot(0, 0);

    void publish(int x, int y) {
        current = new Snapshot(x, y);
    }

    Snapshot read() {
        return current;
    }
}
```

This is a Java 17+ snippet (without `main`). The `record` stores two primitive `int`s, so its values cannot change after construction. Assigning to `volatile current` publishes the new snapshot; the reader obtains **a single consistent snapshot** for both `x` and `y`. However, if **multiple writers** all build a new snapshot from `current` and assign it, they can still overwrite each other's updates; serialization or `AtomicReference` CAS is needed if the invariant forbids lost updates.

### 11.3. Safe publication and `final` fields

`final` fields have special guarantees when an object is properly constructed, but **a `final` reference does not make the referenced object immutable**. For example, `final List<Item> items` can still hold a mutable list and mutable elements. Do not let `this` escape before the constructor finishes; when sharing objects whose state continues to be updated, use an appropriate publication/synchronization protocol.

### 11.4. Handoff via a thread-safe queue

Instead of building your own `ready` flag and `payload` field, the producer can call `queue.put(message)` and the consumer `queue.take()` using a `BlockingQueue`. The API contract guarantees data handoff and waiting mechanics; you still need to handle queue bounds, shutdown/cancellation, and resource limits. This is usually a more maintainable design than a volatile spin-wait loop.

## 12. Designs that require mutual exclusion or an atomic workflow

### 12.1. Check–then–act

```java
if (!seat.isBooked()) {
    seat.book();
}
```

Even if each method is individually `synchronized`, if two threads are allowed to interleave between **check** and **book**, both may see the seat as unbooked. You need an atomic method like `bookOnce()` containing both the check and the update inside **the same critical section**, or an equivalent CAS/transactional state.

### 12.2. Read–modify–write

```java
volatile int counter;
// ...
counter = counter + 1;
```

This is an illustrative class-field snippet; not a complete program. Even though the field is `volatile`, two threads can still read the same old snapshot. Use `AtomicInteger.incrementAndGet()` or a lock protecting the entire read–compute–write sequence.

### 12.3. Multi-field invariant

An order has `reserved` and `available` with a fixed sum. If the writer updates each field separately and the reader reads between steps, the reader can see half of the new state. Two `volatile` fields **do not automatically guarantee an atomic snapshot**; a reader can read them at two different points in time. Solutions include using the same monitor/lock for all updates and reads, or an immutable snapshot swapped via a single atomic reference.

### 12.4. Compound operations on concurrent collections

`ConcurrentHashMap` protects each individual operation per its API contract. However, `if (!map.containsKey(k)) map.put(k,v)` still has a workflow-level race window. Choose `putIfAbsent`/`computeIfAbsent` or an appropriate transaction. **A thread-safe object ≠ every sequence using that object is thread-safe.**

## 13. Common pitfalls when choosing `volatile` or `synchronized`

| Misconception | What is wrong | Right choice |
| --- | --- | --- |
| "`volatile` makes all operations on the field atomic" | `count++` consists of multiple actions | `AtomicInteger`/mutex for updates |
| "Both fields are `volatile` so the pair is always consistent" | A reader can still read two different versions | Shared lock or immutable snapshot via a single reference |
| "Having the writer use `synchronized` is enough, the reader doesn't need it" | The reader usually does not participate in the monitor's happens-before protocol | Synchronize both or use a proven publication mechanism |
| "Locking on any object is the same" | Different lock identities → no mutual exclusion | Use the exact same monitor/`Lock` |
| "`join()` makes `main` see every increment correctly" | `join` does not make worker updates atomic | Synchronize where the updates occur |
| "`Thread.sleep` flushes values out" | Sleep does not create necessary visibility or mutual exclusion | `volatile`/lock/queue/latch depending on the condition |
| "`AtomicInteger.get()` followed by `set()` is an atomic workflow" | Two separate operations can be interleaved | Use `compareAndSet`/atomic methods |
| "A thread-safe map makes check–then–put always safe" | Steps can still interleave | Atomic operations provided by the API |
| "Wrapping everything in a coarse lock is always better" | Contention, lock convoy, deadlock, latency | Lock the right invariant with a sufficiently short critical section |
| "Without multiple cores there is no race" | The scheduler can interleave on a single core | Protect the protocol regardless of CPU count |
| "Virtual threads automatically make state thread-safe" | All Java threads must still obey the JMM | Use synchronization/immutability as usual |
| "A test passing 1,000 times proves safety" | Tests only exercise a subset of execution schedules | JMM reasoning + stress/coordinated tests |

## 14. Reading thread dumps and profiles: what to look for?

**Mutual exclusion has contention costs.** If multiple threads fail to acquire the same intrinsic monitor, they may appear in the `BLOCKED` state in a thread dump. In JFR/monitor profiling, inspect who holds the monitor and for how long. If using `ReentrantLock`, threads may park and show `WAITING`/`TIMED_WAITING` while waiting for the lock, rather than necessarily `BLOCKED`.

**Visibility bugs are hard to spot from thread states alone.** A thread can be `RUNNABLE` in a loop reading a regular flag, yet the code still fails to establish happens-before. A thread dump does not prove a field is being read with the right value. To conclude, inspect all access paths and publication protocols, combining JFR, logs, stress tests, and JMM analysis.

### Diagnostic approach

1. List shared fields/objects and identify which threads read/write them.
2. Write down business invariants: "never oversell inventory", "counter never loses updates", "reader sees the entire published payload".
3. Ask whether the problem requires **visibility**, **mutual exclusion**, **atomicity of a single operation**, or **atomicity across multiple fields**.
4. Verify that every access path uses the same monitor/lock, volatile publication, or proper atomic API contract.
5. If using a volatile flag, check the write order payload → flag and that the reader actually reads the flag before the payload; watch out for payload updates after publication.
6. If using monitors, check lock identity, lock hold duration, I/O inside locks, and lock acquisition chains that could cause deadlock.
7. If using CAS, check retry loops, single-variable invariants, and repeatable side effects.
8. Write concurrency tests with a start gate/barrier when trying to reproduce an interleaving; remember that a barrier creates happens-before and **can mask the visibility bug** being investigated.
9. Test under load, monitor results, and profile; do not use "unable to reproduce" as a substitute for a correctness proof.

## 15. Quick distinction exercises

**1. One thread sets `stopped=true` and another checks it continuously to exit. Is mutual exclusion needed?** If this is an independent one-way stop flag, visibility is usually all that is needed, such as `volatile boolean stopped`. For long blocking operations or multiple related states, a different mechanism may be required.

**2. Two threads both call `volatileCounter++`, and the test calls `join()` before printing. Can updates be lost?** Yes. `join` guarantees `main` observes results after the workers finish; it does not protect the read–modify–write between the two workers.

**3. A `synchronized` method writes a field; another method reads the field directly. Is the reader guaranteed to see the update?** No. The reader does not participate in the same monitor and has no visibility guarantee created by that lock on the read path. An appropriate synchronization/volatile/publication mechanism is needed.

**4. Do two `synchronized` instance methods on two different objects block each other?** No. Each instance has its own monitor. If they both modify a `static` mutable field, a common lock must be chosen.

**5. If `AtomicInteger.compareAndSet` can update one field, what about two related fields?** CAS on one variable does not automatically create a two-variable atomic transaction. You can use a shared lock or an immutable aggregate swapped via a single atomic reference.

**6. When is `volatile Snapshot current` appropriate?** When a writer publishes a complete immutable snapshot and readers need to see one consistent version intact by reading a single reference. If multiple writers need to merge updates based on an old snapshot, CAS or serialization is also needed.

**7. Does `synchronized` guarantee threads always enter the lock in FIFO order?** No. It guarantees mutual exclusion and monitor memory semantics, without promising fairness.

**8. When are both visibility and mutual exclusion needed?** For example, deducting inventory: workers must not interleave the check–update steps, and readers must see a consistent state. Using the same lock around updates and reads satisfies both.

## 16. Design checklist before deciding

- Do you need **readers to see changes**, or **to prevent multiple writers from acting concurrently**? Do both requirements coexist?
- Is it a simple assignment/flag, a read–modify–write, or a multi-field invariant?
- If using `volatile`, what data is published before the volatile write? Is it modified again after publication?
- If using `synchronized`/`Lock`, do all related accesses use **the same lock**? Is the lock held while waiting on I/O?
- If using an atomic class, **which operation** is guaranteed atomic? Have you accidentally separated the check and the update?
- Can you design an immutable snapshot, thread confinement/ownership, or `BlockingQueue` to reduce shared mutable state?
- Do you have invariant tests after threads complete, stress tests, and happens-before reasoning?
- When moving from platform threads to virtual threads, does the data protocol remain correct under all execution schedules?

**Rule of thumb:** `volatile` helps **publish/observe** values across the JMM but **does not create an exclusive region**; `synchronized`/`Lock` protects a **critical section** while also providing memory visibility across matching lock/unlock pairs; atomic classes protect **specific operations**. Choose based on the invariant and scope of operations your program must preserve, rather than choosing by familiar keywords.
