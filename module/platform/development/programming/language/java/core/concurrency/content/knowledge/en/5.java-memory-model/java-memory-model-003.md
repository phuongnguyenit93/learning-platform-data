# Program order and happens-before relationships in the Java Memory Model

When two threads concurrently read and write data, the order visible in the source code is not enough to guarantee that one thread will see the changes made by the other. The Java Memory Model (JMM) defines **what values a read operation is permitted to observe** and the **ordering and visibility guarantees** between concurrent actions. Two core concepts are **program order** (the execution order within a single thread) and **happens-before** (the memory-level ordering guarantee relationship).

This lesson applies to Java concurrency in general (Java 17+), independent of Spring.

After this lesson, you will know:
- How "order within the same thread" differs from "guaranteed order between threads".
- How to construct a happens-before chain using **program order**, **synchronizes-with**, and **transitivity**.
- How to identify happens-before edges coming from `Thread.start()`, `join()`, `synchronized` monitors, `volatile`, and concurrency APIs in the JDK.
- How to distinguish **visibility**, **ordering**, **atomicity**, and the **data race** problem.
- How to inspect a data-sharing pattern to see whether its outcome can be reasoned about, rather than relying on `sleep()` or trial-run results.

## 1. Why does the JMM need ordering rules?

CPUs have caches, compilers/JITs optimize code, processor cores execute in parallel, and threads are scheduled independently. The JVM is permitted to perform many optimizations as long as it still complies with the JMM. As a result:

- Within **a single thread**, behavior must be consistent with the sequential execution semantics of that thread itself (*intra-thread semantics*).
- Between **two threads**, the fact that thread A executes a write before thread B in wall-clock time is **not enough** to conclude that thread B will read the newly written value or observe all prior operations of A.
- A specified synchronization relationship is needed to define the memory constraints that can be relied upon when proving correctness.

Conceptual example:

~~~java
// Variables shared between 2 threads:
int payload = 0;
boolean ready = false;

// Thread A:
payload = 42;
ready = true;

// Thread B:
if (ready) {
    System.out.println(payload);
}
~~~

These are **illustrative snippets, not a standalone Java program**. When `payload` and `ready` are plain variables without synchronization, there is no guarantee that B will always see `42` after seeing `ready == true`. B might also fail to observe the `ready` state written by A. The code has a **data race** on shared data; source order in A is not enough to establish a happens-before relationship from A to B.

The question to answer is not merely "which line ran first?", but: **Does A's write action happens-before B's corresponding read action?**

## 2. Program order: the order of actions within a single thread

### 2.1. Definition

**Program order** is the order among actions of the **same thread** as if they executed according to the program semantics within that thread. By JMM rules, if action `x` precedes action `y` in program order within a thread, then:

**`x happens-before y`.**

Example:

~~~java
int a = 10;       // A1
int b = a + 5;    // A2
System.out.println(b); // A3
~~~

Within the same thread, `A1 →po A2 →po A3`; therefore `A1 →hb A2 →hb A3`. The result in this example's context is `15`, even though the JVM may apply internal optimizations. The JMM requires behavior to remain faithful to intra-thread semantics; it **does not promise that the CPU will issue each machine operation in the exact order of source code lines**.

### 2.2. Program order does not connect two threads on its own

Two chains:

~~~text
Thread A: A1 ->po A2 ->po A3
Thread B: B1 ->po B2 ->po B3
~~~

Give us happens-before edges **within each thread**, but do not automatically imply `A3 →hb B1` or `B2 →hb A1`. Connecting two chains requires a cross-thread synchronization rule, commonly called **synchronizes-with**.

Common points of confusion:
- Writing `A1` before `A2` in source code does not mean other threads will necessarily observe the two values in the expected way.
- "Thread A has already finished executing the write line" on an external wall clock is not a JMM rule that can substitute for synchronization.
- Each thread has its own program order; program order does not provide a single shared *total order* for all plain actions across all threads.

## 3. Happens-before: the memory guarantee relationship

### 3.1. Definition and the three main reasoning rules

Write `A →hb B` when action A **happens-before** action B.

In the JMM, happens-before is formed from program order, synchronizes-with edges, and their transitivity. For practical reasoning, three rules are commonly applied:

1. **Program order:** if A precedes B in the same thread according to program order, `A →hb B`.
2. **Synchronizes-with:** certain defined synchronization actions create an edge from one thread to another, such as a monitor unlock to a subsequent lock on the same monitor, or a volatile write to a subsequent volatile read in synchronization order.
3. **Transitivity:** if `A →hb B` and `B →hb C`, then `A →hb C`.

Example:

~~~text
Thread A:
  data = 42       (A1)
  ready = true    (A2: volatile write)
                       |
                       | synchronizes-with
                       v
Thread B:
  read ready      (B1: volatile read sees true)
  read data       (B2)

A1 ->po A2 ->sw B1 ->po B2
Therefore A1 ->hb B2
~~~

The symbol `→po` denotes program order; `→sw` denotes synchronizes-with; `→hb` denotes happens-before. If there are no other competing writes to `data`, B can rely on the guarantee of seeing `42` after reading `ready == true`.

Happens-before **does not merely mean "occurred earlier on a wall clock"**; it is a relationship defined by the JMM to constrain observable outcomes. Any explanation relying solely on real time or milliseconds waited lacks a synchronization basis.

### 3.2. Happens-before does not mean "every step is atomic"

For example, `counter++` consists of a read, a computation, and a write-back. Two threads both using `volatile int counter` have volatile visibility and ordering rules, yet `counter++` is **still not** an atomic increment. Two threads can read the same value and both write back the new value, losing an update.

For atomic updates, use:
- `AtomicInteger.incrementAndGet()`/`getAndIncrement()` for counters;
- `synchronized` or `Lock` when protecting an entire multi-step invariant;
- Concurrent data structures and atomic methods promised by the API when appropriate.

Three related but distinct properties:

| Property | Question |
| --- | --- |
| **Visibility** | When thread B reads, does the JMM guarantee B sees A's write? |
| **Ordering** | Which operations are required to have a reliable order across threads? |
| **Atomicity** | Is a group of steps observed/processed as an indivisible operation that cannot be interleaved? |

A program needs to consider all three when its invariants require them.

## 4. Synchronizes-with: key cross-thread edges

### 4.1. Monitor: synchronized unlock → subsequent lock

An **unlock** on monitor `m` synchronizes-with **every subsequent lock** on the same monitor `m` (in synchronization order). This allows writes inside an earlier locked block to be visible when another thread enters a later locked block, provided they access the exact same monitor.

~~~java
// Illustrative snippet in a class where 2 threads reference the same lock object:
final Object lock = new Object();
int value = 0;

// Thread A:
synchronized (lock) {
    value = 42;
} // unlock(lock)

// Thread B, entering this block after A has unlocked:
synchronized (lock) { // lock(lock)
    System.out.println(value);
}
~~~

This snippet is not standalone; the point is that both threads **use the same `lock` object**. If B actually acquires the lock after A releases it and there are no other writers, it prints `42`. If B enters before A, the result may be `0`. `synchronized` creates a precise constraint once lock acquisition order is known; it **does not by itself force thread A to acquire the lock before thread B**.

Switching to two different lock objects loses the desired synchronization edge, even if the variable names or the contents of the two blocks are identical.

With `java.util.concurrent.locks.Lock` such as `ReentrantLock`, lock/unlock operations are specified to have memory effects equivalent to monitors for building the corresponding reasoning. You must still call `unlock()` in a `finally` block after successfully acquiring the lock.

### 4.2. Volatile write → subsequent volatile read

A write to a `volatile` variable synchronizes-with reads of that variable that are **subsequent in synchronization order**. For a *publication flag* pattern, a thread reading `true` can use this ordering to access data that the writer prepared before publishing the flag.

Standalone example (Java 17+):

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

When both threads are scheduled and the program completes normally, stdout:

~~~text
Payload: 42
~~~

Reasoning:
1. In main: `payload = 42 →po ready = true`.
2. In reader: the volatile read observing `true` occurs after the write `ready = true` in synchronization order; that write `→sw` that read.
3. In reader: the read observing `true` `→po` the read of `payload`.
4. By transitivity, main's write `payload = 42 →hb` reader's read of `payload`. There is only one writer to `payload` in this program.

`Thread.onSpinWait()` is a hint to the JVM/CPU inside a spin loop; **it is not a synchronization operation**. Spinning is used here only to illustrate the volatile relationship: in real applications, prefer appropriate waiting tools such as `CountDownLatch`, `BlockingQueue`, or `Future` to avoid wasting CPU and to support timeout/cancellation policies.

Note: liveness does not follow from happens-before relationships alone. If the OS does not schedule CPU time for the writer, the reader may not exit the wait loop; the JMM does not guarantee fair scheduling.

### 4.3. Thread.start(): start → first action of the new thread

A call to `thread.start()` synchronizes-with any action in the newly started thread. Thus data prepared **before `start()`** can be seen by the new thread via happens-before.

~~~java
// StartVisibilityDemo.java
public class StartVisibilityDemo {
    public static void main(String[] args) throws InterruptedException {
        int[] values = {0};
        values[0] = 42;

        Thread worker = new Thread(() ->
            System.out.println("Observed: " + values[0]));

        worker.start();
        worker.join();
    }
}
~~~

~~~bash
javac StartVisibilityDemo.java
java StartVisibilityDemo
~~~

Stdout:

~~~text
Observed: 42
~~~

`values[0] = 42 →po worker.start() →sw` the actions of worker. This is how initialization data is passed from the spawning thread to the child thread. If main **continues modifying `values[0]` after `start()`** while worker reads it without additional synchronization, the `start()` edge does not protect those later modifications.

### 4.4. Thread termination: worker actions → successful join

All actions in a terminating thread happens-before another thread **detects that the thread has terminated**, such as when `join()` returns normally or `isAlive()` returns `false` upon detecting termination.

~~~java
// JoinVisibilityDemo.java
public class JoinVisibilityDemo {
    private static int result;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> result = 42);
        worker.start();
        worker.join();
        System.out.println("Result: " + result);
    }
}
~~~

~~~bash
javac JoinVisibilityDemo.java
java JoinVisibilityDemo
~~~

Stdout:

~~~text
Result: 42
~~~

Reasoning: `result = 42` happens in worker; worker terminates, main returns from `join()`; main reads `result` after `join()`. The thread-termination edge together with program order and transitivity suffice for main to see the update. `result` does not need to be `volatile` **in the case where only one worker writes and main only reads after `join()` succeeds**. If main reads before `join()`, that guarantee cannot be inferred.

`join()` can throw `InterruptedException` if the waiting caller is interrupted; the code must handle incomplete waiting according to application policy.

### 4.5. Interrupt and interrupt detection

A call to `interrupt()` on thread T synchronizes-with the action where **T detects the interrupt**, such as checking `isInterrupted()`/`Thread.interrupted()` or a blocking operation throwing `InterruptedException` due to the interrupt.

This edge helps transmit control signals, but **interrupt does not forcibly stop a thread**, does not force a CPU-bound task to check itself, and does not replace a data-transfer protocol between threads. Do not use interrupt as a "result is ready" message when the actual goal is to publish a value.

### 4.6. Default initialization and final fields

The JMM also includes synchronization rules for **default initialization** of an object before other normal operations on that object. For `final`, the JMM defines special guarantees when an object is properly constructed, specifically **without letting `this` escape during construction**. Because of this, final fields have special initialization visibility, but one should not infer that other mutable fields in the object are automatically safe to share.

For objects with multiple mutable states, publish them using explicit happens-before mechanisms such as locks, volatile references, or concurrency API handoffs.

## 5. Transitivity: chaining edges into a proof

Suppose:

~~~text
Thread A:       write(data=42) ─po─> volatile write(ready=true)
                                        |
                                        | sw
                                        v
Thread B:                              volatile read(ready)
                                        |
                                        | po
                                        v
                                      read(data)
~~~

Therefore:

~~~text
write(data=42) →hb read(data)
~~~

You must verify the **exact pair of operations** and the **exact synchronization object**. A statement like "volatile is used somewhere" does not provide proof that a write to `data` is guaranteed to be visible at the read site.

### 5.1. Multi-hop handoffs

Happens-before relationships can span multiple threads. For example, if:

~~~text
A: write X →po release(lock1)
                →sw B: acquire(lock1) →po release(lock2)
                                            →sw C: acquire(lock2) →po read X
~~~

then by transitivity we have `A:write X →hb C:read X`. The edges between A–B and B–C do not need to use the same monitor, as long as each pair uses its own matching monitor, has the appropriate unlock–lock order, and the code actually connects the two steps via program order.

### 5.2. Happens-before is directional; it cannot be reversed

If `A →hb B`, you cannot conclude `B →hb A`. If two actions are in two threads without a happens-before relationship in either direction, they are **not ordered by happens-before**. For conflicting accesses to shared data, you must consider data races and the outcomes permitted by the JMM.

Do not invent edges merely because:
- Two threads both call a regular method.
- They look at the same object, yet each thread locks a different monitor.
- `Thread.sleep(100)` was called before reading.
- During debugging, logs usually show the write task "appearing to finish first".

## 6. java.util.concurrent APIs that establish memory guarantees

Standard JDK utilities have **memory consistency effects** documented in their API specs. These guarantees are usually more concise and easier to use than building a custom protocol with multiple plain variables.

| Mechanism | Key edge for reasoning |
| --- | --- |
| `ExecutorService` | Actions prior to submitting a `Runnable`/`Callable` →hb actions in the task; task actions →hb the caller retrieving the result via `Future.get()` |
| `Future.get()` | Actions in the asynchronous computation →hb actions following a successful return of `get()` in the waiting thread |
| `CountDownLatch` | Actions prior to `countDown()` →hb actions following a successful return from the corresponding `await()` |
| `BlockingQueue` | Actions prior to placing an element into the queue →hb actions subsequent to another thread taking/receiving that element |
| `ConcurrentMap` and concurrent collections | Follow the API's *memory consistency* contract for communication through elements/entries and specified operations |
| `Lock` (e.g., `ReentrantLock`) | Successful lock/unlock has the memory effects of the corresponding monitor |

**Example using CountDownLatch**, deterministic stdout without spinning:

~~~java
// LatchHappensBeforeDemo.java
import java.util.concurrent.CountDownLatch;

public class LatchHappensBeforeDemo {
    private static int payload;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread reader = new Thread(() -> {
            try {
                ready.await();
                System.out.println("Payload: " + payload);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        reader.start();
        payload = 42;
        ready.countDown();
        reader.join();
    }
}
~~~

~~~bash
javac LatchHappensBeforeDemo.java
java LatchHappensBeforeDemo
~~~

Stdout:

~~~text
Payload: 42
~~~

In main: `payload = 42 →po ready.countDown()`. By the `CountDownLatch` contract, actions before `countDown()` happens-before actions after `await()` returns successfully in reader. Combined with program order, reader sees `42`. Calling `reader.join()` in main is only to wait for reading/printing to finish before the program exits; **the visibility guarantee from main to reader here comes from the latch**.

**Example with ExecutorService + Future**, distinguishing bidirectional handoff:

~~~java
// FutureHappensBeforeDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureHappensBeforeDemo {
    private static int base;
    private static int outcome;

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            base = 40;
            Future<Integer> task = executor.submit(() -> {
                outcome = base + 2;
                return outcome;
            });

            int received = task.get();
            System.out.println("Future: " + received);
            System.out.println("Shared: " + outcome);
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac FutureHappensBeforeDemo.java
java FutureHappensBeforeDemo
~~~

Stdout:

~~~text
Future: 42
Shared: 42
~~~

Bidirectional explanation:

1. Main writes `base = 40` **before `submit`**; this action happens-before the task's actions, so the task sees `base = 40`.
2. The task writes `outcome = 42` and returns the result; actions in the task happens-before main's actions **after `task.get()` succeeds**. Main can read `outcome` under that guarantee.
3. `ExecutorService.shutdown()` stops accepting new tasks; it **does not automatically wait** for running tasks to finish. In this example, main already called `get()` before shutdown.

This guarantee does not mean every shared variable in the task is automatically thread-safe if other threads still modify the same variable without synchronization.

## 7. Data race, correctly synchronized, and limits of reasoning

### 7.1. What is a data race?

At a fundamental level, when two threads access the **same variable**, at least one access is a **write**, and those two conflicting accesses are **not ordered by happens-before**, we have a data race as defined by the JMM. The most common issue is plain variables shared across threads without any consistent synchronization protocol.

~~~java
// Illustrative snippet, NOT a complete program:
int counter = 0;

// Both T1 and T2 execute this, without locking:
counter++;
~~~

An increment is a read–compute–write sequence; updates can be lost. Data races and lost updates are related, but not every race condition should be treated as purely a visibility issue. An increment requires **atomicity**, so changing `counter` to `volatile` **does not solve** lost updates.

When a program is **correctly synchronized** (conflicting shared accesses are properly coordinated), the JMM guarantees behavior consistent with a sequential model for correctly synchronized programs (often called the *sequential consistency for data-race-free programs* property). The prerequisite is that all components adhere to the synchronization protocol.

### 7.2. Without happens-before, what is a read permitted to see?

The absence of a happens-before edge between a write and a read **does not mean** the read is guaranteed to see the old value; some runs may see the new value and some may not. The JMM constrains the permitted outcomes of an execution rather than declaring that "unsynchronized code is always wrong".

Nor can one freely assume a single global order for all plain reads/writes. A practical checking rule is: identify the writes that can affect a read, check the required happens-before relationships, and see whether the synchronization API delivers the desired guarantee.

Note that the JMM has additional rules regarding the validity of reads and executions; an example should not be turned into a claim that "any arbitrary value can be read". In application design, the goal is usually to establish **explicit happens-before edges** to avoid depending on unpredictable observability possibilities.

### 7.3. Happens-before is not enough for multi-step compound operations

~~~java
// Illustrative code, does not compile standalone:
volatile int counter = 0;

// Both threads call:
counter = counter + 1;
~~~

Each volatile read/write has its own ordering/guarantee, but the compound operation can still be interleaved. If the invariant is "each request must increment the counter once", use `AtomicInteger.incrementAndGet()` or a lock enclosing the entire update.

Conversely, when information is only **published once** and then **read after a synchronization boundary**, as in the `start()`, `join()`, and latch examples, the payload variable may not need to be volatile. You must analyze who writes, when they write, whether there are competing writes, and which synchronization point is used.

## 8. How to inspect code using a happens-before graph

Read concurrent code by building an action diagram:

1. **List shared variables:** e.g., `payload`, `ready`, `counter`; indicate which threads read/write each variable.
2. **Mark actions:** `W(payload=42)`, `Wvolatile(ready=true)`, `Rvolatile(ready)`, `R(payload)`.
3. **Draw program order within each thread** (`→po` edges).
4. **Find actual synchronizes-with edges**: same monitor, same volatile field, `start`, termination detection via `join`, communication through concurrency APIs.
5. **Apply transitivity** to determine whether the desired write happens-before the read.
6. **Check for competing writers and compound operations**: even if visibility is guaranteed, does the update have sufficient atomicity? If there are multiple writers, is their relative ordering controlled?
7. **Cross-check against business requirements**: outcome constraints, timeout/interrupt handling, shutting down executors, and liveness/progress.

Comparison examples:

| Scenario | Enough HB to publish `payload`? | Notes |
| --- | --- | --- |
| A writes `payload` then `start()`s worker B; B reads | Yes | Only guarantees actions before `start()` |
| Worker A writes `payload`; B is a thread that successfully `join()`ed A, then reads | Yes | B must wait successfully before reading |
| A writes `payload` before volatile write flag; B reads flag as true then reads payload | Yes | No other competing writes to payload |
| A writes `payload` then `countDown()`; B successfully `await()`s then reads | Yes | Relies on latch memory consistency |
| A writes `payload` then `sleep(100)`; B reads | No HB from sleep alone | Delay does not create a synchronization protocol |
| A locks `lockA`; B locks a different object `lockB` | No HB from that lock pair | Identical variable names do not make two monitors the same |
| Two threads both do `volatileCounter++` | Has volatile rules, but **insufficient atomicity** | Use atomic increment/lock |

### Common misconceptions

- **"Code in the same thread runs in order, so other threads will definitely see it correctly."** Program order is an intra-thread edge; you need synchronizes-with to connect threads.
- **"Volatile makes every expression on the variable atomic."** False: volatile does not combine a read–modify–write sequence.
- **"`join()` makes every read before `join()` see the new data."** False: the guarantee applies only to actions of the caller **after `join()` succeeds**.
- **"Any two synchronized blocks synchronize with each other."** False: they must use the same monitor and have the proper unlock/lock order.
- **"`Thread.sleep` helps the JMM flush caches."** There is no such happens-before rule; sleep only affects scheduling.
- **"Reading `isDone() == true` means all arbitrary data has been retrieved."** Rely on the specific memory consistency contract of the API, such as `Future.get()`, rather than assuming a status-check method is equivalent to every synchronization point.
- **"If a test passes 10,000 times, there is no data race."** Stress tests are useful for uncovering bugs, but they do not prove the required JMM edges are present.
- **"Happens-before is the exact chronological order of CPU execution."** This relationship is a semantic constraint; how the compiler/JIT/CPU implements it may differ, as long as it complies with the JMM.

## 9. Self-check quiz

**Question 1.** Thread A writes `int data = 99` and then calls `t.start()`, where B is thread `t` and only reads `data` after starting. If there are no other competing writes, is `volatile` needed just to see the value 99?

**Answer:** No. The program order edge before `start()` and the edge from `start()` to actions in B allow happens-before to be inferred.

**Question 2.** A worker writes `result`; the caller calls `worker.join()`, which returns successfully, and only then reads. What is guaranteed?

**Answer:** The worker's actions happens-before subsequent actions after the caller detects that the worker has terminated; the caller sees the worker's value provided no other competing writer modifies it.

**Question 3.** A uses `synchronized(lock1)`, B uses `synchronized(lock2)`, where `lock1 != lock2`. Can an unlock–lock edge be inferred from these two blocks?

**Answer:** No; they must lock **the same monitor**.

**Question 4.** A `volatile boolean ready` is written after the writer prepares `payload`. The reader sees `ready == true` and then reads `payload`. Name the chain of edges.

**Answer:** `write(payload) →po writeVolatile(ready) →sw readVolatile(ready) →po read(payload)`; therefore `write(payload) →hb read(payload)`.

**Question 5.** Two threads concurrently increment a `volatile int` using `++`. Can an increment be lost?

**Answer:** Yes. Volatile does not make an increment atomic; use `AtomicInteger` or an appropriate critical section.

**Question 6.** A caller submits a `Callable<Integer>` and then calls `future.get()`, which succeeds. How do you prove it can see changes made before the task completed?

**Answer:** Actions inside the task happens-before the caller's actions after `Future.get()` returns successfully, according to the executor/future memory consistency guarantees.

**Question 7.** Why is a `sleep(500)` after writing data not enough for the reader to rely on the result?

**Answer:** Waiting time does not create a synchronizes-with edge. You must use volatile, a lock, a latch, join, a future, or another specified mechanism suited to the data-exchange protocol.

**Key takeaway:** Program order provides happens-before **within a thread**. Synchronizes-with connects threads. Transitivity combines those edges into a proof of visibility/ordering. Even after establishing happens-before, you must still check **atomicity**, competing writers, and adherence to the synchronization protocol to confirm program correctness.

### Standard references

- Java Language Specification, `17.4 “Memory Model”, especially `17.4.4 “Synchronization Order” and `17.4.5 “Happens-before Order”: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- JDK 17 `java.util.concurrent` package documentation (memory consistency properties): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
- JDK 17 `Thread` and `CountDownLatch` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html and https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html