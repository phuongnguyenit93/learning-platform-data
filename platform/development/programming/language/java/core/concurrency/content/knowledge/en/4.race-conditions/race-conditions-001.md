# How Does Shared Mutable State Create Race Conditions in Java?

When multiple threads concurrently access **shared mutable state**, the outcome can depend on the order and timing of interleaved operations. Without proper synchronization rules in the design, an application can lose updates, read stale values, break invariants, or produce different results across runs. This is the source of many **race conditions** in Java concurrency.

This lesson focuses on pure Java and the Java Memory Model (JMM), independent of any framework. The goal is to understand **what conditions make data dangerous to share**, why an operation as seemingly simple as `count++` can fail, how to choose protection mechanisms, and how to detect bugs.

## 1. Three Key Terms: Shared, Mutable, Concurrent

- **Shared:** at least two threads can access the same state. For example, holding references to the same `Counter` instance, a `static` field, a collection, or an object passed into an executor.
- **Mutable:** at least one thread can modify that state after creation. A `final` reference does not mean the object's internal contents are immutable.
- **Concurrent access:** threads can perform operations on the shared state without a total order enforced by the program.

If data resides only in a thread's local variable and is not shared via an object or closure, there is typically no contention on that local variable itself. If an object is shared but **truly immutable** and has been **safely published**, multiple threads can read it without locking on each read.

Conversely, if at least one thread writes data while other threads also read or write it, we must consider **atomicity, visibility, memory ordering**, and the consistency of **multiple related fields**.

### A Common Example

```java
class Counter {
    int value;

    void increment() {
        value++;
    }
}
```

This is an **illustrative snippet without a `main` method**. Every thread calling `increment()` on the **same instance** contends over the `value` field. Even though `value++` is written on a single line of Java, it is not an atomic update operation.

## 2. How Is a Race Condition Different from a Data Race?

A **race condition** is a bug where correctness depends on the order or timing of actions that can interleave. This broad concept includes check-then-act logic, publishing events out of order, or updating state without a synchronization protocol.

A **data race** in the Java Memory Model occurs when two operations access the same variable, at least one of them is a write, and there is **no happens-before relationship** ordering the two operations. Unprotected plain reads/writes on a shared field can create a data race.

The two concepts are related, but **not identical**:

- An `int count` incremented by two threads using unsynchronized `count++`: this is both a data race and usually a race condition leading to a **lost update**.
- A `ConcurrentHashMap` may be thread-safe for individual `get`/`put` calls, yet two threads running "check if key is absent, then insert" still have a **business-level race**, even though the collection protects individual operations.
- An update protocol spanning multiple variables can still be logically incorrect even if each variable is declared `volatile` or uses a separate atomic class.
- Two threads only reading a properly shared immutable object do not create a race simply by running concurrently.

**Not every change in execution order is a bug.** If the system allows any ordering and all outcomes satisfy the contract, that is valid concurrency. A race condition needs fixing when an interleaved ordering can violate requirements.

## 3. `count++` Is Actually Read–Modify–Write

Conceptually, `count++` consists of at least three steps:

1. **Read:** read the current value of `count`.
2. **Compute:** compute `count + 1`.
3. **Write:** write the new result back to `count`.

Suppose two threads A and B both observe `count = 0`:

| Step | Thread A | Thread B | Shared value |
| --- | --- | --- | --- |
| 1 | Reads `0` | | `0` |
| 2 | | Reads `0` | `0` |
| 3 | Computes `1` and writes `1` | | `1` |
| 4 | | Computes `1` and writes `1` | `1` |

Two valid increments in business logic should produce `2`, yet the final value is only `1`. One update has been **overwritten/lost**. This is a *lost update*.

You must not assume the compiler/JIT/CPU is forced to execute the exact three machine instructions described. The table is a logical model of a read–modify–write operation: **Java does not guarantee that `count++` on a plain field is atomic**, so incorrect results can occur when two threads run on the same data.

### Java 17 Experiment: Producing a Deterministic Lost Update

The code below uses two `CountDownLatch` instances to ensure **both threads read `0` before either thread writes**. This way, the demonstration does not depend on scheduler luck and produces deterministic stdout.

Save as `LostUpdateExample.java`:

```java
import java.util.concurrent.CountDownLatch;

public class LostUpdateExample {
    static class Counter {
        int value = 0;
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int snapshot = counter.value;
            bothRead.countDown();

            try {
                mayWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            counter.value = snapshot + 1;
        };

        Thread a = new Thread(increment, "worker-A");
        Thread b = new Thread(increment, "worker-B");

        a.start();
        b.start();

        bothRead.await();
        mayWrite.countDown();

        a.join();
        b.join();
        System.out.println("Ket qua: " + counter.value);
    }
}
```

Run:

```bash
javac LostUpdateExample.java
java LostUpdateExample
```

Stdout during normal execution without external interruption:

```text
Ket qua: 1
```

**Why is the output consistent?** Each worker stores the read value into the local variable `snapshot` before signaling `bothRead.countDown()`. Main only opens the write gate `mayWrite.countDown()` after both have finished reading. Thus, each worker reuses its `0` snapshot and writes `1`. `join()` ensures main waits for both to finish before printing.

**Important note about the experiment pattern:** the latches establish enough synchronization to control the read and write schedule, so do not use this specific example to claim a formal JMM data race on individual accesses to `value`. It **demonstrates the failure of a logical update operation** when read and write are separated, even when the steps are intentionally ordered. In real code, calling `counter.value++` from multiple threads without synchronization is a situation with a data race, and lost updates can appear unpredictably. The experiment above deliberately forces the dangerous ordering to illustrate the bug.

## 4. The Remaining Bugs: Visibility, Ordering, and Invariants

### 4.1. Visibility: Threads Do Not Necessarily See New Writes Immediately

```java
class WorkerState {
    boolean stopped = false;
}
```

If thread A sets `stopped = true` while thread B loops reading `stopped` without synchronization, the JMM **does not guarantee** that B observes the new value in a timely manner, or even observes it before the loop terminates. The JIT and CPU may optimize, keep data in registers/caches, or perform memory operations in valid orderings when happens-before is missing. You should not explain the bug by claiming every CPU "caches forever without refreshing"; the core issue is the **lack of memory model guarantees**.

A solution for a **simple status flag**:

```java
class WorkerState {
    volatile boolean stopped = false;
}
```

A `volatile` write and a corresponding `volatile` read establish the necessary visibility and ordering guarantees. However, `volatile` **does not make `count++` atomic**, nor does it protect a sequence of conditions and updates across multiple fields.

### 4.2. Ordering and Happens-Before

The JMM allows the JVM/CPU to reorder certain operations as long as memory model constraints are respected. Without happens-before, another thread can observe state that violates the assumption that "every statement appears in the exact order written in source code."

**Happens-before** is a relationship that lets us reason about visibility and ordering between actions:

- **Program order:** within the same thread, an earlier action happens-before a later action in program order.
- **Monitor:** releasing a monitor via `synchronized` happens-before a subsequent acquisition of that same monitor.
- **Volatile:** a write to a `volatile` field happens-before a subsequent read of that same field according to synchronization rules.
- **Start:** calling `Thread.start()` happens-before any actions in the started thread.
- **Termination/join:** actions in a terminating thread happen-before another thread detects termination via a successfully completed `join()`.
- **`java.util.concurrent` utilities:** for example, actions prior to `ExecutorService.submit` have guarantees transferred to the task's actions, and the task's actions happen-before the caller retrieves the result via `Future.get()` according to the API's memory consistency contract.

Happens-before is **transitive**. It differs from wall-clock time order: "A ran earlier than B" is not enough to establish a happens-before relationship between two threads.

### 4.3. Invariants: Multi-Field Updates Must Be Consistent

Suppose an object stores `available` and `reserved` with the invariant `available + reserved == total`. If one thread updates each field individually and another thread reads in between, the reader can observe an **intermediate state** that violates the invariant, even if writes to each individual field are atomic.

Appropriate ways to protect this include: holding the **same lock** for the entire update and snapshot read; grouping the fields into an **immutable snapshot object** and publishing it via a safe reference; or designing an atomic operation that holds enough data to preserve the invariant. Using two independent `AtomicInteger` instances does not automatically make a transaction spanning both fields atomic.

## 5. Fixing Lost Updates with `synchronized`

`synchronized` establishes mutual exclusion on a monitor: at any given time, only one thread owns that monitor and executes the protected critical section. Releasing and acquiring the monitor also provides a happens-before relationship for visibility.

Save as `SynchronizedCounterExample.java`:

```java
public class SynchronizedCounterExample {
    static class Counter {
        private int value = 0;

        synchronized void increment() {
            value++;
        }

        synchronized int getValue() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable task = () -> {
            for (int i = 0; i < 100_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("Ket qua: " + counter.getValue());
    }
}
```

```bash
javac SynchronizedCounterExample.java
java SynchronizedCounterExample
```

Stdout:

```text
Ket qua: 200000
```

Here, **both threads call the same `counter` instance**, so they use the same `this` monitor when calling `increment()`. Two threads cannot execute `value++` in the critical section at the same time; all 200,000 increments are preserved. `getValue()` also uses that lock; `join()` ensures main waits for the workers to finish.

**Conditions to remember:**

- All read/write paths to the protected state must follow the **same locking rule**. If other code still reads `value` directly without synchronization, the design can still be broken.
- `synchronized` on **two different instances** uses two different monitors. It cannot protect a shared `static` mutable field if each thread locks on a separate object.
- Keep critical sections small: do not hold locks while making HTTP/DB calls, calling `sleep`, or waiting on other tasks unless necessary; holding locks too long causes contention, latency, and potential deadlocks.
- `synchronized` supports reentrancy; exiting the block—even via an exception—automatically releases the monitor, though partially updated business state may still need handling.

## 6. Fixing a Single Counter with `AtomicInteger`

When the state to protect is just a simple increment/decrement or compare-and-set, `AtomicInteger` provides atomic update operations with well-defined memory semantics, often more suitable than a manually managed monitor.

Save as `AtomicCounterExample.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterExample {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger count = new AtomicInteger();

        Runnable task = () -> {
            for (int i = 0; i < 100_000; i++) {
                count.incrementAndGet();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("Ket qua: " + count.get());
    }
}
```

```bash
javac AtomicCounterExample.java
java AtomicCounterExample
```

Stdout:

```text
Ket qua: 200000
```

`incrementAndGet()` performs an atomic increment; each valid increment is counted exactly once. Under contention, the implementation may have to retry the update. `AtomicInteger` does not turn an entire sequence like "read value → call API → write another state" into an atomic transaction.

**`volatile int value; value++;` is still wrong** because `volatile` guarantees visibility/ordering for individual field accesses, not combining read–modify–write into a single atomic action.

### Is `LongAdder` Better?

When many threads concurrently add to a statistical counter, `LongAdder` can improve throughput under contention by striping updates. However, `sum()` is **not an atomic snapshot** in the presence of concurrent updates. Use it for high-throughput metrics/counters when you do not need a linearizable exact value at every instant; for business conditions like "deduct if balance is sufficient," `LongAdder` is not the right solution.

## 7. `Lock`, `ReentrantLock`, and Synchronization Conditions

`java.util.concurrent.locks.ReentrantLock` can replace an intrinsic monitor when you need `tryLock`, timeouts, interruptible locking, or multiple `Condition` objects. It also requires a rule to use the **same lock** for all accesses to the same state.

Illustrative snippet (not a standalone program):

```java
private final ReentrantLock lock = new ReentrantLock();
private int balance = 100;

public boolean withdraw(int amount) {
    if (amount < 0) throw new IllegalArgumentException();
    lock.lock();
    try {
        if (balance < amount) return false;
        balance -= amount;
        return true;
    } finally {
        lock.unlock();
    }
}
```

Add `import java.util.concurrent.locks.ReentrantLock;` and place the fields/methods inside a class. The condition check and the deduction **must be inside the same critical section**. If `if (balance < amount)` is placed outside the lock, two threads could both see sufficient balance and both withdraw.

With `ReentrantLock`, you must always unlock in a `finally` block; forgetting `unlock()` can leave other threads waiting indefinitely. If using multiple locks, enforce a consistent lock acquisition order to reduce the risk of deadlock.

## 8. A Thread-Safe Collection Can Still Have Business-Level Races

Consider the following idea:

```java
if (!map.containsKey(key)) {
    map.put(key, createValue());
}
```

Even if `map` is a `ConcurrentHashMap`, two threads can both observe that the key does not exist, both compute `createValue()`, and then overwrite each other's result. **Each individual operation is thread-safe, yet the sequence of operations is not atomic.**

If the goal is to compute a value for a key when absent, consider:

```java
Value value = map.computeIfAbsent(key, k -> createValue());
```

These snippets are illustrative; assume `map` has type `ConcurrentHashMap<Key, Value>` and `createValue()` returns a valid `Value`. `ConcurrentHashMap.computeIfAbsent` performs the corresponding update according to the API's atomicity guarantees; the mapping function should be short, must not recursively update the same map, and should avoid side effects that are hard to repeat. If creating the value requires long network/DB calls or produces external side effects, you must carefully design around locking, errors, retries, and idempotency.

Similar cases requiring intentional atomic operations:

- `if (!list.contains(item)) list.add(item)`: check-then-act can produce duplicate elements even when using `Collections.synchronizedList` if you do not hold the lock around the entire sequence.
- `if (stock > 0) stock--`: checking and decrementing inventory must be unified; `volatile` alone is not enough.
- `map.get(key)` followed by `map.put(key, transformed)`: this is read–modify–write; prefer `compute`/`merge` when the semantics match.
- Multi-step order/booking state: an atomic operation on a single field is not enough to preserve the entire invariant.

## 9. Ways to Reduce or Avoid Shared Mutable State by Design

### 9.1. Thread Confinement: Do Not Share Data That Needs Mutation

Data belongs to only one thread or one task, so internal updates do not contend with other threads:

```java
Runnable job = () -> {
    int localCount = 0;
    for (int i = 0; i < 10; i++) {
        localCount++;
    }
    System.out.println(localCount);
};
```

This is an illustrative snippet without `main`. If each task has its own `localCount`, there is no data race on that variable. **However, objects referenced by local variables can still be shared**; a local reference does not make a shared object private.

### 9.2. Immutability and Defensive Copying

Prefer immutable values: records with immutable components, `String`, value object structures, immutable collections, or immutable snapshots. `List.copyOf(source)` creates a list that cannot be structurally modified through the returned reference, but it **does not deep-copy mutable elements inside**. `final List<Item>` likewise only prevents reassigning the reference, not mutating the list.

Immutable objects still need to be **safely published** when handed off from the creating thread to a consuming thread. Do not let the `this` reference "escape" the constructor before construction completes; use a handoff mechanism with happens-before (a queue, `synchronized`, a `volatile` reference, a concurrent collection, or fork/join per API contracts).

### 9.3. Message Passing, Ownership, and Partitioning

Partition state by key/shard and assign each partition to a single managing worker; other threads send messages via a `BlockingQueue` instead of concurrently mutating the same object. This design shifts the problem from "who holds the lock?" to "who owns the state and which messages are allowed to update it?". Queue bounds, shutdown handling, and error recovery still need to be designed.

### 9.4. Immutable Snapshots Instead of Multiple Mutable Fields

If the UI or readers need to observe a consistent group of values, you can create a new immutable snapshot object and update **a single reference** using `volatile` or `AtomicReference`. Readers see either the previous snapshot or the next snapshot, rather than a mix of both. When multiple writers need to update based on the old value, `AtomicReference.compareAndSet` or a lock is still required to prevent lost updates.

## 10. Choosing a Solution for Each Type of Contention

| Requirement | Usually Appropriate Solution | What Not to Misunderstand |
| --- | --- | --- |
| A flag read by another thread | `volatile boolean`, `AtomicBoolean`, or a higher-level synchronization mechanism | `volatile` does not create waiting/notification or lifecycle mechanisms |
| Exact count | `AtomicInteger`/`AtomicLong` or `synchronized` | `volatile int++` is not safe |
| Statistical counter with many writers | `LongAdder` if a non-atomic `sum()` snapshot is acceptable | Do not use for monetary/inventory conditions requiring atomic decisions |
| Condition and update across multiple fields | `synchronized` / `Lock` around the entire invariant | Having each field as a separate atomic is not enough |
| Map updated per key by many threads | `ConcurrentHashMap` with `compute`, `merge`, `putIfAbsent` per contract | Separate `containsKey` + `put` still races |
| Producer/consumer data handoff | `BlockingQueue` or message passing | A thread-safe queue does not automatically enforce all business conditions |
| Many readers, few writers, and snapshots | Immutable object + safe publication | A `final` reference does not make mutable contents immutable |
| Each task has only local data | Thread confinement/task ownership | Avoid accidentally passing a mutable reference to another thread |

There is no "best lock" for every situation. Choose based on the **invariant to protect**, number of writers, contention level, fairness requirements, latency, blocking capability, and code structure. Once you choose a tool, explicitly identify **every access path that must follow the same rule**.

## 11. Two Levels of Safety: Atomic Operations and Atomic Workflows

Example withdrawal transaction:

```java
if (balance.get() >= amount) {
    balance.addAndGet(-amount);
}
```

Suppose `balance` is an `AtomicInteger`; both `get` and `addAndGet` are individually atomic, but **the whole sequence is not an atomic operation**. Two threads can both see sufficient balance and both deduct, causing a negative balance.

If the invariant depends only on a single integer, you can use a compare-and-set (CAS) loop:

```java
boolean withdraw(AtomicInteger balance, int amount) {
    if (amount < 0) throw new IllegalArgumentException();
    while (true) {
        int current = balance.get();
        if (current < amount) return false;
        if (balance.compareAndSet(current, current - amount)) {
            return true;
        }
    }
}
```

This is a Java 17+ snippet using `import java.util.concurrent.atomic.AtomicInteger;` and needs to be placed inside a class. `compareAndSet` succeeds only if the current value is still `current`; if another thread has changed it, the loop re-reads and re-checks the condition. Under high contention, the loop may retry many times.

**Boundaries of CAS:** if a transaction involves multiple objects, DB connections, HTTP calls, or complex invariants, a CAS on an `AtomicInteger` cannot cover everything. If an update function inside a retry loop has external side effects, it may run multiple times and cause duplicate side effects. Transaction management, idempotency, and failure semantics must be handled at the appropriate layer.

## 12. Happens-Before and "Synchronizing in the Right Place"

Several common misconceptions:

**"I called `join()` at the end, so concurrent updates are definitely correct."** `join()` lets the calling thread observe results after the workers finish. It **does not fix lost updates that happened while workers contended over state earlier**.

**"There is a `Thread.sleep(10)` between two lines, so there can't be a race."** Delays do not create a synchronization contract; a different schedule, a faster/slower machine, or a different JIT compilation will change the result.

**"Making one field `volatile` makes the entire object thread-safe."** `volatile` applies semantics only to the declared field. Atomicity of compound updates and multi-field invariants still requires locks, CAS on snapshots, or a dedicated mechanism.

**"I lock in the writer; the reader only reads, so it doesn't need a lock."** If the reader reads a plain field without participating in synchronization or an equivalent publication mechanism, the reader can see stale data or an inconsistent snapshot.

**"Switching `HashMap` to `ConcurrentHashMap` makes all business logic correct."** The collection provides guarantees within the scope of its operations. Check–then–act protocols or multi-map transactions still need atomic workflows.

**"Races only happen when actually running in parallel on multiple CPUs."** Even on a single core, the scheduler can preempt after a read and switch to another thread, creating a broken interleaving. Parallelism makes interleavings richer, but it is not a prerequisite for a race.

## 13. Testing and Finding Race Conditions

Race conditions are often hard to reproduce because they depend on scheduling; a test passing 1,000 times **does not prove** there is no race.

1. **Identify shared state:** fields/static fields, collections, caches, config objects, objects passed to executors, callbacks; identify who reads and who writes.
2. **Write down invariants:** `completed <= submitted`, `balance >= 0`, `sum == expected`, "each key is initialized only once," "two fields always correspond to the same version."
3. **Check every access path:** is a plain field used outside a lock? Is the lock on the same instance? Is there check–then–act or multiple separate atomics?
4. **Design coordinated tests:** `CountDownLatch`, `CyclicBarrier`, and `Phaser` help trigger sensitive branches simultaneously. Use timeouts so tests do not hang when a bug occurs.
5. **Run stress tests under load and across configurations:** many threads, large task counts, different schedulers/CPUs, repeated in CI. Monitor invariants and error logs, not just isolated stdout.
6. **Use JFR/profiling/thread dumps to find lock contention and deadlocks:** these tools are useful for contention and hangs, but **a thread dump does not prove the presence or absence of a data race**.
7. **Review against the JMM and API contracts:** thread-safe collections, atomic classes, publication, interruption/cancellation, visibility. Testing does not replace reasoning about happens-before.

### When Debugging, Ask Specifically

- Which **exact variable/object is shared**? Is it the same instance or does each thread have a copy?
- Which threads write? Which threads read? Is there at least one access not enclosed in the same synchronization mechanism?
- Is there a "read condition → compute → write" sequence that is split apart?
- Are threads relying on timing (`sleep`, retries) or on a signal with a happens-before contract?
- Can update operations be retried? Are there side effects that cannot be executed twice?
- Did a fix eliminate the race but introduce lock contention, deadlock, or poor throughput?

## 14. Common Mistakes

| Mistake | Possible Bug | Fix |
| --- | --- | --- |
| Multiple threads update `int count` via `count++` | Lost update | `AtomicInteger.incrementAndGet` or a shared lock |
| Declaring `volatile int count` and still doing `count++` | Still a lost update | Use atomic read–modify–write |
| Each thread synchronizes on a different object | No shared mutual exclusion | Own and share the exact same lock protecting the state |
| Writer uses `synchronized`, reader does not | Visibility/invariant not guaranteed | Reader participates in the same protocol or reads a safe snapshot |
| `if (map.get(k) == null) map.put(k, ...)` | Two threads both create/overwrite | Use an appropriate atomic operation like `computeIfAbsent` |
| Using `Thread.sleep` to "wait for the other thread to finish writing" | Flaky, lacks required happens-before | Use `join`, latch, future, or queue |
| Sharing a mutable object via a `final` field and thinking it is immutable | Internal fields are still mutated concurrently | Immutable design or explicit synchronization |
| Broad locks covering slow I/O | Contention, latency, or deadlock | Narrow lock scope, design ownership and invariants |
| CAS loop containing API calls with side effects | Retries can repeat side effects | Separate side effects from retries, use transactions/idempotency |
| Testing with only one fixed schedule | Rare races are missed | Stress tests + JMM reasoning |
| Using multiple `AtomicInteger`s for a multi-field invariant | Inconsistent snapshot across fields | Shared lock or atomically published immutable state snapshot |
| Assuming "switching to a thread-safe collection" is enough | Workflow-level race remains | Choose business-level atomic operations |

## 15. Self-Check Exercises

**Q1.** Two threads only read the same already-constructed `List<String>`, and nobody modifies the list. Does a race necessarily occur?  
No; if the list is safely published and neither the elements nor the collection are modified afterward, concurrent reads can be safe. Also verify publication, because "not modifying after creation" does not replace properly handing the reference off to another thread.

**Q2.** Does `volatile int x` make `x = x + 1` atomic?  
No. That operation is still read–modify–write, with the possibility of two threads using the same old value.

**Q3.** If there is only one writer and multiple readers, is synchronization needed?  
Potentially yes. Readers must observe changes in a timely manner and see consistent invariants. Depending on requirements, use `volatile`, locks, or immutable snapshots.

**Q4.** Does `AtomicInteger` guarantee a "non-negative balance" when two threads both check `get()` and then deduct with `addAndGet(-amount)`?  
No. Two separate atomic operations do not protect the condition. A compare-and-set loop or a lock around the entire sequence is needed.

**Q5.** Why does `LostUpdateExample` print `1` on every normal run?  
Because both threads are forced to read `0` before either is allowed to write; the second write overwrites `1` with `1`. The synchronization gates make the example deterministic, independent of interleaving probability.

**Q6.** Can you solve a race simply by increasing the thread pool size or switching to virtual threads?  
No. Changing the scheduling model may make the race appear more or less frequently, but it does not make the data protocol safe. Both virtual threads and platform threads must obey the JMM.

## 16. Practical Checklist

Before sharing a mutable object across multiple threads, answer:

- **Who owns the data?** Can sharing be avoided via confinement, immutable snapshots, or queues/message passing?
- **What data needs atomicity?** A single field, an integer, a map entry, or an entire multi-field invariant?
- **What is the happens-before protocol?** `synchronized`, `volatile`, `Lock`, atomics, thread-safe queues, `Future`, or safe publication?
- **Do all readers/writers participate in the same protocol?** Is there any code path reading directly without a lock, or using a different lock?
- **Does the workflow have check–then–act or read–modify–write?** Is there an atomic API for the whole operation, or must a lock/CAS be used?
- **Do tests verify invariants and multiple interleavings?** Are there timeouts, contextual logging, and lock contention observations?
- **Does the solution have side effects?** Overly broad locks, deadlocks, retries repeating side effects, memory pressure, or reduced throughput?

**Takeaway:** the issue is not that multiple threads exist together, but that **multiple threads can read/write the same mutable state without a coordination rule strong enough for the invariants to preserve**. Eliminate sharing when possible; if sharing is unavoidable, choose a synchronization mechanism with a clear scope and prove that every access path obeys it.