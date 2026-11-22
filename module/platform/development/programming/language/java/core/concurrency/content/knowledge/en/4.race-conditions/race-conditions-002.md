# Interleaving and Non-Deterministic Results in Java Concurrency

> **Scope:** Race conditions in Java in general: interleaved execution order of thread operations, schedule-dependent outcomes, how the Java Memory Model (JMM) affects visibility/observations, and how to ensure correctness through synchronization. Does not cover Spring-specific concurrency mechanisms.

## 1. What Should You Learn from This Lesson?

- Explain **interleaving** (alternating execution steps) and why execution order between threads is not fixed by default.
- Distinguish **non-deterministic order** from **incorrect results caused by a race condition**; a concurrent program can produce different execution orders while still preserving all invariants.
- Decompose a `counter++` operation into multiple steps and identify an execution schedule that leads to a **lost update**.
- Understand the limits of a simple interleaving model: the Java Memory Model allows observations involving visibility and reorderings when *happens-before* constraints are missing.
- Recognize and fix check-then-act bugs, read-modify-write bugs, broken invariants, and reliance on `sleep/yield`.
- Create a controlled example that reproduces a race, then verify solutions using `synchronized`, `Lock`, atomic classes, or appropriate data-passing mechanisms.

**Core idea:** Concurrency allows multiple threads to make progress over overlapping time intervals. The *scheduler* decides which thread gets a chance to run, but **correctness** must be designed using provable rules for shared state and ordering—not by relying on "thread A usually runs before B."

## 2. What Is Interleaving?

Suppose two threads execute separate sequences of logical steps:

- Thread A: `A1 → A2 → A3`.
- Thread B: `B1 → B2 → B3`.

Without a synchronization relationship enforcing cross-thread ordering, a useful learning model is that the steps of A and B can interleave according to many different schedules, **while the required dependency order within each thread is still respected according to program semantics**.

Examples of abstract schedules:

```text
Schedule 1: A1 A2 A3 B1 B2 B3
Schedule 2: A1 B1 A2 B2 A3 B3
Schedule 3: B1 A1 B2 B3 A2 A3
```

This does not mean the machine always executes one step and then pauses to switch threads; this is a **reasoning model**. On a multi-CPU machine, actual operations can occur simultaneously. The JIT, CPU, and memory subsystem can also cause the observed order of data accesses to **differ from a simple line-by-line reading of the source code** if proper synchronization is absent. A "plausible" interleaving that illustrates a lost update is not the complete set of all behaviors permitted by the JMM for a program with a data race.

Why do schedules differ between runs?

1. The operating system may preempt or schedule platform threads at different times.
2. Available CPU count, system load, GC, I/O handling timing, and contention vary.
3. Synchronization primitives such as lock acquisition, park/unpark, or queue waiting affect progression order.
4. Java has no contract stating that the order of `start()` calls determines the order in which threads enter `run()` or complete.

**Non-determinism** means a single execution order or observed outcome cannot be deduced from the guarantees currently in place. It does not mean "uniformly random": a schedule might appear frequently on your machine and **still not be guaranteed**.

## 3. Lost Update: Two Threads Incrementing the Same Variable

The following is **illustrative code inside a class**, assuming `counter` is an `int` field shared by multiple threads:

```java
counter++;
```

In terms of read-modify-write semantics, split it into:

```text
R: read counter into a temporary value
C: add 1
W: write the new value back to counter
```

In Java, `counter++` is **not automatically an atomic operation**. Two threads can read the same old value, compute independently, and overwrite each other's result.

Suppose initially `counter=0`, and both A and B perform one increment:

| Schedule step (sequentially consistent model) | Thread A | Thread B | Shared value |
|---|---|---|---|
| 1 | Read `0` into `a` | — | `0` |
| 2 | — | Read `0` into `b` | `0` |
| 3 | Compute `a+1` and write `1` | — | `1` |
| 4 | — | Compute `b+1` and write `1` | `1` |

**Result = 1, even though there were two increments.** That is a *lost update*: one thread's update is overwritten by another thread's update based on stale data. If A completes fully before B reads, the result can be 2.

In this simple model where each thread performs a **read (R) then a write (W)**, there are 6 schedules that preserve each thread's R-before-W order. Two sequential schedules `A_R A_W B_R B_W` and `B_R B_W A_R A_W` produce 2; the remaining four schedules all have both reads before the final write and produce 1. This is a count **for that 4-step model only**; it is not a "4/6" probability of data loss in the JVM, because the scheduler does not pick schedules uniformly and the JMM is broader than this assumption.

A similar bug occurs when multiple threads update account balances, inventory counts, sequence IDs, available seat counts, booking statuses, or fields with coupled invariants. Reading a valid value at some point in time does not guarantee that a **check-then-update** operation will remain valid when another thread modifies the data concurrently.

## 4. Distinguishing Nondeterministic Order, Race Condition, and Data Race

These concepts are easily confused:

| Concept | Practical definition | Necessarily a bug? |
|---|---|---|
| **Interleaving** | Steps/operations of multiple threads arranged in an alternating execution schedule. | No. |
| **Nondeterministic order** | Completion/print/lock-acquisition order may differ across runs. | No; many applications only require invariants and the aggregate result to be correct. |
| **Race condition** | Whether the outcome or behavior is right or wrong depends on the timing/ordering relationship between concurrent activities that are not properly coordinated. | Usually a correctness bug. |
| **Data race** under JMM | Two conflicting accesses to the same variable (at least one write), with no proper *happens-before* order between them and not coordinated by the necessary synchronization guarantees. | A serious indicator of unsafe state sharing, though not identical to every business-level race. |

For example, a program that lets tasks A and B finish in any order while writing their results to two independent locations, then calls `join()` and sums them: **the schedule may be non-deterministic, yet the sum is still correct**.

Conversely, a "create if absent" example can be wrong even when using a thread-safe data structure for each individual call:

```java
// Illustrative snippet: seen is a ConcurrentHashMap<String, Boolean>
// Each individual call is safe, but the check + put pair is not an atomic operation.
if (!seen.containsKey(key)) {
    seen.put(key, Boolean.TRUE);
    performSideEffect();
}
```

Two threads both see "absent", and then both execute the side effect. The solution when you want **only one thread to win the key insertion**:

```java
if (seen.putIfAbsent(key, Boolean.TRUE) == null) {
    performSideEffect();
}
```

This is still an **illustrative snippet**, not a complete program: `seen`, `key`, and `performSideEffect()` are declared in the surrounding context. `putIfAbsent` decides a single thread to receive the "right to execute" in memory, but if the side effect fails, you still need a **retry/rollback/idempotency policy**; do not assume the external operation becomes an atomic transaction with the map. If the map could already contain the key mapped to `null`, you must revisit the API; `ConcurrentHashMap` does not allow null keys or values.

## 5. Why Can Changing One Line of Code Make a Bug Disappear?

Many race conditions only surface under "rare" schedules:

- Adding `System.out.println` changes execution timing, and `PrintStream` itself is synchronized on many code paths; race symptoms may change.
- Debuggers, logging, profilers, loop lengths, or CPU speed cause threads to reach the critical region at different times.
- Calling `Thread.sleep(10)` may make one schedule more common, but it creates no ordering rule for shared data.
- `Thread.yield()` is only a hint and does not force the scheduler to give a turn to a specific thread; it guarantees neither fairness nor correctness.
- Running the same binary many times does not necessarily exercise all possible schedules; many passing test runs **do not prove** a program is race-free.

Do not "fix" a race by inserting arbitrary sleeps. Identify the shared variables, the reads/writes that must be treated as a logical transaction, and the synchronization relationship that must be established between them.

## 6. Java Memory Model: Interleaving Statements Is Not Enough to Explain Everything

A **sequentially consistent interleaving** imagines all memory operations occurring in a single total order while respecting each thread's program order. That model is useful for seeing lost updates, but **Java does not promise that every program containing a data race will be observed as a simple interleaving of Java source lines**.

The Java Memory Model (JLS 17.4) distinguishes key relationships:

- **Program order:** the order of actions according to a single thread's execution, used to define `happens-before`; optimizations may still reorder physical operations as long as required observable guarantees are met.
- **Synchronization order:** the order of synchronization actions such as volatile accesses and lock/unlock according to the JMM.
- **Synchronizes-with:** a defined relationship between actions, such as releasing a monitor and another thread subsequently acquiring the same monitor.
- **Happens-before (HB):** a transitive relationship built from program order and *synchronizes-with* edges. If A HB B, B is subject to specific visibility/ordering guarantees established by A.

Some practical relationships to remember:

1. Actions within a single thread follow program order under the JMM.
2. **Unlocking** monitor `m` *synchronizes-with* every subsequent **lock** on the same monitor `m`.
3. A **write** to a `volatile` variable *synchronizes-with* subsequent **reads** of the same variable in synchronization order.
4. Calling `Thread.start()` HB any actions in the started thread. All actions in a thread HB another thread detecting that the thread has terminated, such as `join()` returning successfully.
5. `java.util.concurrent` APIs have their own memory-consistency contracts (e.g., `CountDownLatch`, `BlockingQueue`, `Future.get()`); read the documentation for the specific primitive you use.

**Visibility example:**

```java
// Illustrative snippet of fields/methods belonging to the same class.
private int value;
private volatile boolean ready;

void publish() {
    value = 42;
    ready = true;  // volatile write
}

void consume() {
    if (ready) {   // volatile read
        System.out.println(value);
    }
}
```

If `consume` reads `ready == true` from the corresponding publish operation, writes prior to the volatile write (including `value=42`) are published to the reading thread via HB. However, if the consumer reads `ready == false`, it prints nothing; there is no guarantee the scheduler runs the consumer *after* publish. If there are additional writes to `value/ready` under a different protocol, you must re-analyze that protocol specifically. This is an **incomplete, non-standalone** illustrative snippet and does not replace a coordination protocol for multiple publishes.

**Critical misconception:** declaring `volatile int counter` **does not make `counter++` atomic**. Volatile provides visibility/ordering rules for individual accesses, but the increment is still a read–compute–write sequence; two threads can still read the same value and overwrite each other. When an atomic increment is needed, use an atomic operation or a lock protecting the entire read-modify-write.

**Data-race-free → easier to reason about:** if all conflicting shared accesses are properly synchronized under the JMM, execution is guaranteed to be consistent with an appropriate sequential model (*sequentially consistent for correctly synchronized programs*). This **does not make the execution schedule fixed**; there can still be multiple valid orders and multiple valid outputs, none of which violate the designed invariants.

## 7. Java 17+ Lab: Forcing a Lost-Update Schedule

The example below intentionally uses a `CyclicBarrier` to force **both threads to read the value 0 before either writes**. This makes the lost-update bug consistently observable in the lab; it does **not** imply that every unsynchronized increment always loses an update.

The second part replaces it with `AtomicInteger.incrementAndGet()`. The final part uses `StringBuffer` (where each append is synchronized) to show that **A/B order is not fixed, yet data is not corrupted**.

Create the file **`InterleavingLab.java`**:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;

public class InterleavingLab {
    private static int counter;

    private static void runPair(Runnable task) throws InterruptedException {
        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();
        first.join();
        second.join();
    }

    private static void awaitBarrier(CyclicBarrier barrier) {
        try {
            barrier.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted at barrier", e);
        } catch (BrokenBarrierException e) {
            throw new IllegalStateException("Barrier broken", e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        counter = 0;
        CyclicBarrier bothRead = new CyclicBarrier(2);
        runPair(() -> {
            int snapshot = counter;
            awaitBarrier(bothRead);
            counter = snapshot + 1;
        });
        System.out.println("lostUpdate=" + counter);

        AtomicInteger atomicCounter = new AtomicInteger();
        runPair(() -> atomicCounter.incrementAndGet());
        System.out.println("atomic=" + atomicCounter.get());

        StringBuffer completionOrder = new StringBuffer();
        Thread a = new Thread(() -> completionOrder.append('A'));
        Thread b = new Thread(() -> completionOrder.append('B'));
        a.start();
        b.start();
        a.join();
        b.join();
        System.out.println("order=" + completionOrder);
    }
}
```

Compile and run:

```bash
javac --release 17 InterleavingLab.java
java InterleavingLab
```

A verified run:

```text
lostUpdate=1
atomic=2
order=AB
```

**What can be asserted during normal execution:**

- `lostUpdate=1`: both workers read `counter=0` and wait for each other at the barrier. Both write `1`, so only one increment is visible in the end. That is a controlled, forced schedule.
- `atomic=2`: each `incrementAndGet()` is an atomic increment. Both are applied successfully, `join()` returns before reading, so the total is 2.
- The third line is **`order=AB` or `order=BA`**; the order depends on the execution schedule. `StringBuffer.append` makes each append safe in this context, and `join()` waits for both threads to finish. There is no guarantee you will observe both orders on a single machine.

**Why use a barrier?** If you simply write two threads doing `counter++` and run it a few times, you will often see 2 and mistakenly think the code is safe. `CyclicBarrier(2)` forces a synchronization point **after the read step and before the write step**, reproducing the exact schedule that causes a lost update. It is not a fix for `counter`, because the first part's purpose is to demonstrate the bug.

**Why use `join()`?** If `main` prints the result immediately after the two `start()` calls, it might read the variable before the workers finish; that would be an additional ordering issue that obscures the experiment. A successful `join()` ensures the workers finish before `main` checks the total and establishes the appropriate HB relationship.

**Note on demo limitations:** `awaitBarrier()` uses interrupt and broken-barrier exceptions to report environment failures; if a thread dies or stalls abnormally, workers may fail to complete. Do not use a barrier to compensate for an undefined business-level synchronization condition. `StringBuffer` in the third part is used to illustrate ordering; real systems may use a queue or an appropriate data structure.

## 8. How to Produce Correct Results When the Schedule Still Varies?

### Approach 1: `synchronized` protecting the **entire** operation

```java
private int counter;
private final Object guard = new Object();

void increment() {
    synchronized (guard) {
        counter++; // read-modify-write is inside the same critical section
    }
}

int snapshot() {
    synchronized (guard) {
        return counter;
    }
}
```

These are **illustrative members inside a class**. Every thread updating or reading the protected state must use the same monitor `guard`. `synchronized` provides mutual exclusion and HB edges between unlock and lock. Two increments yield 2 after both complete; which thread acquires the monitor first may still vary. If multiple fields share an invariant, protect the entire check/update group with the same lock.

### Approach 2: `AtomicInteger` for a single independent state

```java
private final AtomicInteger counter = new AtomicInteger();

void increment() {
    counter.incrementAndGet();
}

int snapshot() {
    return counter.get();
}
```

These are illustrative class members requiring `import java.util.concurrent.atomic.AtomicInteger`. `incrementAndGet()` performs the increment atomically with memory semantics equivalent to volatile read/write. Appropriate when the goal is updating a single atomic variable. It does **not** automatically protect invariants across two separate atomics, such as "`balanceA + balanceB` must remain constant" across two separate subtract/add calls.

### Approach 3: `ReentrantLock` when acquisition control is needed

```java
private final ReentrantLock lock = new ReentrantLock();
private int counter;

void increment() {
    lock.lock();
    try {
        counter++;
    } finally {
        lock.unlock();
    }
}
```

This is a class-member snippet requiring `import java.util.concurrent.locks.ReentrantLock`. Like `synchronized`, the entire logical operation is placed in a critical section. `ReentrantLock` also provides `tryLock()`, `lockInterruptibly()`, and `Condition`; use it when the design genuinely needs those features, not under the assumption that it is always faster than an intrinsic monitor.

### Approach 4: Change how data is shared

Not every problem requires all workers to write to a single variable:

- **Thread confinement:** each worker accumulates a local result, and after `Future.get()`/`join()`, one place merges the results.
- **Immutable data / message passing:** push messages through a `BlockingQueue` and have a single consumer own/mutate the target state.
- **Key-based partitioning:** each group of keys is handled by a dedicated owner; define rules when coordinating across partitions.
- **Concurrent collections:** use API-level atomic operations (`putIfAbsent`, `compute`, `merge`) when exactly one state transition is needed, instead of chaining separate read and write calls.

The goal is to establish an identifiable **linearization point** or critical section so the logical update occurs as a single unit. "Every method is thread-safe" does not mean a **sequence of multiple methods** is atomic.

## 9. Result Determinism vs. Order Determinism

**Deterministic result:** given the same input and program contract conditions, the output can be guaranteed to be identical even if the internal schedule differs. For example, two workers add different parts to an `AtomicInteger` and `main` reads it after `join()`.

**Nondeterministic order but valid:** two independent tasks append A or B to a synchronized buffer; the string may be `AB` or `BA`. If the system requirement is "contains exactly one A and one B", both are valid.

**Nondeterministic result due to missing ordering:** two workers update shared mutable data without synchronization, so the outcome depends on the schedule and may violate invariants.

**Need results in a specific order?** State the constraint explicitly:

- A must finish before B processes A's result: use `Future.get()`, `join()`, `CountDownLatch`, or appropriate message coordination.
- Events must be recorded in sequence: assign a sequence number via an atomic/lock mechanism, then sort by sequence (remember that "number-assignment order" and "external side-effect completion order" can still differ).
- Updates to databases or external JVM resources require transactions, conditional writes, idempotency, or dedicated coordination mechanisms. A Java lock in one process does not automatically protect multiple processes.

**Do not force ordering unnecessarily:** over-synchronization makes a program nearly sequential, increasing contention and reducing throughput. Good concurrent design typically **allows many schedules**, while ensuring every permitted schedule preserves invariants.

## 10. Evidence-Based Testing for Race Conditions

Running code once and seeing the right answer does not prove thread safety. An appropriate strategy:

1. **Define invariants.** For example, after N workers each complete K increments, the total must be `N × K`; balances must never be negative; each event is processed only once.
2. **Identify shared points.** List read/write operations, event sources, locks, and HB relationships; separate independent variables from multi-variable invariants.
3. **Create controlled contention points.** `CountDownLatch` to start simultaneously, `CyclicBarrier` to force hitting a checkpoint; do not use `sleep()` as a precision signal.
4. **Verify results and progress.** Assert values, processing counts, and data integrity; set test timeouts to detect deadlocks/hangs.
5. **Stress-test under varied configurations.** Vary worker count, loop count, available cores, JDK/JIT, and load rate. Run many iterations to increase the chance of hitting dangerous schedules; failure proves a bug, while success is not a mathematical proof.
6. **Use the right tools for the job.** [OpenJDK jcstress](https://github.com/openjdk/jcstress) helps design litmus tests for outcomes permitted under the JMM. JFR, thread dumps, and profilers help identify contention/timing; **they do not by themselves prove a program is race-free**.
7. **Lock behavior to contracts.** When using a high-level primitive, read its memory consistency guarantees; do not swap it for another API solely because a benchmark looks faster.

**Benchmark note:** iteration counts or `System.nanoTime()` do not measure concurrency "safety." An incorrect implementation can be faster because it omitted necessary synchronization. Only compare speed between versions that are **all correct** on the same invariants and workload.

### Very Short Schedule-Check Example

For the `counter++` model starting at 0:

| Abstract schedule | Read/write order | Expected result in model |
|---|---|---|
| A finishes then B | `A_R A_W B_R B_W` | `2` |
| Both threads read before writing | `A_R B_R A_W B_W` | `1` |
| B finishes then A | `B_R B_W A_R A_W` | `2` |

The purpose of this table is to **reason out failure scenarios**, not to predict schedule probabilities or the exact set of all observations under all JMM optimizations. With racy data, "read then write" in source code alone is not sufficient evidence of visibility.

## 11. Common Misconceptions

1. **"Having two threads guarantees they run in parallel."** Concurrency does not mean simultaneous execution; a single CPU can also interleave execution.
2. **"Calling `start` on A before B means A will run first."** False: `start()` does not impose completion order or ordering of all actions between two threads.
3. **"`counter++` is one line, so it is atomic."** False: it is a read-modify-write and can lose updates.
4. **"Making it `volatile` eliminates lost updates."** False: volatile does not combine read/compute/write into an atomic operation.
5. **"The program printed AB many times, proving it can never print BA."** False: observed schedules depend on execution; absence of evidence is not a guarantee of order.
6. **"Varying output order means there is a race bug."** False: non-fixed order can be a valid requirement, provided invariants and visibility are guaranteed.
7. **"Using `ConcurrentHashMap` makes any contains/put/side-effect sequence atomic."** False: individual calls being thread-safe does not make the whole sequence a transaction.
8. **"`sleep` or `yield` is synchronization."** False: delaying a thread does not establish proper HB for shared updates.
9. **"`join` makes an earlier increment atomic."** False: `join` ensures `main` sees results after workers finish, but does not stop two workers from overwriting each other while running.
10. **"Tests passing many times proves thread safety."** False: that is only evidence for the observed schedules; you must reason about invariants, HB, and atomicity.
11. **"Locking everything is best."** Not necessarily: overly broad locks can cause contention, deadlock, or high latency; protect the exact invariants and measure performance.
12. **"The JMM is just the scheduler alternating source lines."** False: the JMM defines visibility/ordering of memory actions; optimizations and data-race behavior make a source-line interleaving model incomplete.

## 12. Self-Check Questions with Answers

**Q1.** Threads A and B each call `counter++` once on a shared `int` variable starting at 0, without synchronization. In a sequential read/write interleaving model, are both 1 and 2 possible?  
**Answer:** Yes. Both reading 0 and writing 1 causes a lost update; if one thread completes before the other reads, the result is 2. A full JMM analysis requires examining synchronization/visibility relationships, not just source-reading schedules.

**Q2.** Does changing `int counter` to `volatile int counter` and continuing to use `counter++` guarantee 2?  
**Answer:** No. Volatile accesses have ordering/visibility, but the increment expression still consists of separate read and write operations.

**Q3.** Two independent tasks write A/B to a `StringBuffer`, and `main` reads after `join()`. Are both `AB` and `BA` possible? Is that necessarily a bug?  
**Answer:** Both orders are valid; it is not a bug if the contract only requires both characters to be present without specifying order.

**Q4.** After thread A calls `start()` before thread B, can B finish before A?  
**Answer:** Yes. The order of `start()` calls does not determine CPU scheduling or completion time.

**Q5.** Why is calling `join()` before reading worker results important, yet insufficient to fix a lost update?  
**Answer:** `join` establishes that workers finish before the reader runs and provides proper visibility; non-atomic updates between the two workers can still overwrite each other.

**Q6.** A program uses `ConcurrentHashMap.containsKey`, and if absent, calls `put` and sends an email. Why can two emails be sent?  
**Answer:** Both threads can pass through the "absent" branch. The conditional operation must be decided atomically, and external side effects outside the map need an appropriate idempotency/retry policy.

**Q7.** If a race only appears in production, should you add logging/sleep to reproduce it and treat that as the fix?  
**Answer:** No. Logging/sleep alters timing and may mask the bug. Model the invariants, force controlled checkpoints, and add proper synchronization.

**Q8.** You need to increment an independent counter from multiple threads: should you choose `AtomicInteger` or `synchronized`?  
**Answer:** Both can be correct. `AtomicInteger.incrementAndGet` is usually concise for a single independent increment; `synchronized` is appropriate when multiple operations/fields must be protected as one invariant. Decide based on semantics and measure under realistic load.

## References

- [Java Language Specification 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): thread actions, data races, `happens-before`, correctly synchronized programs.
- [Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start()`, `join()`, semantics and thread lifecycle.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic read-modify-write.
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): rendezvous, barrier action, and memory consistency.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordinating phases and memory consistency.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): map operations supporting concurrent access.
- [OpenJDK jcstress](https://github.com/openjdk/jcstress): experimental toolkit and litmus tests for concurrency/JMM.

**Learning takeaway:** do not try to predict a single execution schedule. Define all outcomes permitted by the contract, the invariants that must remain unchanged, and the required atomicity/`happens-before` relationships. Then the program can be scheduled flexibly while still producing correct results.
