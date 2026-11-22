# count++ Is Multiple Steps, Not an Atomic Operation

## 1. The Problem: Incrementing a Shared Counter

In Java, `count++` is shorthand for incrementing a variable by 1. In a sequential program, this is a familiar expression. However, when **two or more threads increment a shared counter concurrently**, `count++` **does not guarantee** that each call increases the final result by exactly 1.

The reason is that **incrementing consists of reading the old value, computing the new value, and writing it back** (*read–modify–write*). These logical steps are not protected as an *atomic operation*. Two threads can read the same initial value and overwrite each other's result. This phenomenon is called a **lost update**.

For example, if `count = 0` and two threads each execute `count++` once, we expect `count = 2`. However, without proper synchronization, the program might store only `1`. Observing `2` in a single run **does not prove** the code is correct, because thread interleaving can differ on the next run.

This lesson helps you distinguish **atomicity**, **visibility across threads**, and **execution ordering**; from there, you will use `synchronized`, `AtomicInteger`, and `LongAdder` appropriately.

## 2. Decomposing count++: Read, Compute, Write

Consider an `int count` variable and the expression:

```java
count++;
```

Semantically, it can be pictured as follows:

```java
int oldValue = count;          // (1) Read current value
int nextValue = oldValue + 1;  // (2) Compute new result
count = nextValue;              // (3) Write result
```

This is an **explanatory model**, not a guarantee that every JVM executes exactly three machine instructions or three bytecodes. The JIT and CPU may optimize execution; nevertheless, Java **does not provide an atomicity contract** for incrementing a shared `int` field with `count++`.

| Step | Thread A | Thread B | Shared value |
|---|---|---|---|
| 1 | Reads `count = 0` | Not yet running | `0` |
| 2 | Holds copy `oldA = 0` | Reads `count = 0` | `0` |
| 3 | Computes `0 + 1 = 1` | Computes `0 + 1 = 1` | `0` |
| 4 | Writes `count = 1` | Has not written yet | `1` |
| 5 | Finished | Writes `count = 1` | `1` |

Two increments occurred, yet the final value is only **1**. Thread B overwrote Thread A's result; that is a lost update.

Another scenario can also happen: A finishes writing `1` before B reads, so B reads `1` and writes `2`. Therefore, a race condition can appear correct sometimes and wrong other times depending on scheduling.

### Distinguishing Postfix and Prefix

- `count++` (*postfix*) increments the variable and returns the **old value** of the expression.
- `++count` (*prefix*) increments the variable and returns the **new value** of the expression.
- `count += 1` also requires reading, computing, and writing.

None of these three forms **automatically creates an atomic operation** when multiple threads concurrently update the same shared `int` variable. The difference between prefix and postfix concerns the value of the expression, not thread safety.

### When Is Plain count++ Enough?

If `count` is a **local variable confined to a single thread** and is not shared with other threads, two threads cannot modify it concurrently, so there is no lost update from contention. The risk typically lies in fields of shared objects, `static` fields, or an array element read and written by multiple threads.

Even if individual reads and writes of an `int` are performed atomically, the **read–increment–write combination** is still not atomic. Do not infer properties of the entire expression from the properties of a single read or write.

## 3. A Java 17+ Program to Deterministically Reproduce the Issue

Trying to run multiple threads executing `count++` can produce varying results across runs; predicting the exact stdout is difficult. The example below uses `CountDownLatch` to **force both threads to read the old value before writing**, thereby reproducing an interleaving that causes a lost update.

The unsafe part uses two statements, `snapshot = count` and `count = snapshot + 1`, to **expose** the steps of the increment; it models the read–modify–write nature of `count++` rather than claiming every execution of `count++` is always interleaved the exact same way. The second part uses two fixes with 100,000 increments per thread.

Create **`IncrementDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class IncrementDemo {
    private static int count;
    private static int guardedCount;
    private static final Object LOCK = new Object();
    private static final AtomicInteger atomicCount = new AtomicInteger();

    private static void demonstrateLostUpdate()
            throws InterruptedException {
        count = 0;
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable unsafe = () -> {
            int snapshot = count;
            bothRead.countDown();

            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            count = snapshot + 1;
        };

        Thread a = new Thread(unsafe);
        Thread b = new Thread(unsafe);
        a.start();
        b.start();

        bothRead.await();
        allowWrite.countDown();
        a.join();
        b.join();

        System.out.println("two increments, actual: " + count);
    }

    private static void demonstrateFixes()
            throws InterruptedException {
        guardedCount = 0;
        atomicCount.set(0);

        Runnable safe = () -> {
            for (int i = 0; i < 100_000; i++) {
                synchronized (LOCK) {
                    guardedCount++;
                }
                atomicCount.incrementAndGet();
            }
        };

        Thread a = new Thread(safe);
        Thread b = new Thread(safe);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("synchronized: " + guardedCount);
        System.out.println("AtomicInteger: " + atomicCount.get());
    }

    public static void main(String[] args)
            throws InterruptedException {
        demonstrateLostUpdate();
        demonstrateFixes();
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac IncrementDemo.java
java IncrementDemo
```

Output:

```text
two increments, actual: 1
synchronized: 200000
AtomicInteger: 200000
```

**Detailed explanation:**

1. Both threads `a` and `b` hold `snapshot = 0`. `bothRead.await()` on the main thread waits until both have read, and only then calls `allowWrite.countDown()` to allow writing.
2. Each thread writes `snapshot + 1 = 1`. Two overlapping writes leave the final result `count == 1`. This deterministically demonstrates a schedule causing a lost update.
3. With `synchronized (LOCK)`, each `guardedCount++` is protected by the same lock object. Only one thread can be inside the locked region at a time.
4. `atomicCount.incrementAndGet()` performs an atomic increment on `AtomicInteger`. Both threads call it 100,000 times, resulting in `200000`.
5. `a.join()` and `b.join()` ensure main reads the results only **after both threads complete**. `join()` does not make the `count++` operations inside the threads atomic; it only creates a wait point and guarantees observation ordering after the threads terminate.

With the fixed code, even when the execution schedule of the two threads varies, the final total remains accurate as long as there are no other modifications and no integer overflow occurs. The broken code intentionally spells out the separate steps so you can see the root cause.

## 4. Atomicity, Visibility, and Happens-Before Are Three Distinct Concerns

### Atomicity

An atomic increment must be observable as a single update that cannot be interleaved with another increment in a way that loses an update. If a counter starts at 0 and 200,000 atomic increments have completed, the result is 200,000 (assuming no other modifications and no `int` overflow).

`count++` on an unsynchronized field lacks this guarantee; `AtomicInteger.incrementAndGet()` has it. `synchronized` can turn a read–compute–write section into a region that cannot be entered concurrently by another thread using **the same lock**.

### Visibility

One thread may write data, yet another thread does not necessarily see that effect at the expected time without proper synchronization. The Java Memory Model (JMM) specifies when changes by one thread must become visible to another thread.

The `volatile` keyword establishes certain visibility and ordering guarantees for field accesses; `synchronized` and synchronization APIs also have their own memory rules. However, visibility **does not by itself guarantee** that two separate read and write operations are combined into a single atomic increment.

### Ordering and Happens-Before

The JMM's **happens-before** relationship expresses ordering and visibility guarantees between operations. For example, after `Thread.join()` completes successfully, the thread calling `join()` can observe the actions of the terminated thread under the JMM contract. Acquiring and releasing the same monitor also establishes the corresponding synchronization relationship.

Using `join()` to wait for threads is appropriate when reading the **final result**, but calling `join()` after increments have executed **cannot recover** updates that were already lost earlier.

## 5. Why Doesn't volatile Solve count++?

The following code is **still broken** when called concurrently by multiple threads:

```java
private volatile int count = 0;

public void increment() {
    count++;
}
```

`volatile` provides guarantees for **each individual read and write**, but `count++` can be interleaved as follows:

```text
A: reads count -> 10
B: reads count -> 10
A: computes 11 and writes count = 11
B: computes 11 and writes count = 11
```

The counter ends at `11` instead of `12`. The two threads do not have an atomic "read+write" operation; both only perform separate volatile reads and writes. Therefore:

- `volatile int count; count++;` is **unsafe** as a shared counter with multiple updaters.
- `volatile long count; count++;` is also **unsafe**.
- `count += 1` does not fix the lost update bug either.
- `volatile` is suitable for protocols sharing state values/flags whose updates do not require an atomic read–modify–write.

You should not claim that simply "avoiding the CPU cache" is enough to solve this. This is an issue about the **atomicity** contract of the entire operation, not merely reading the latest data.

## 6. Fixing with synchronized

`synchronized` creates a region guarded by a **monitor**. If all read/write paths to the counter follow **the same lock**, only one thread executes the guarded section at a time.

Counter class example:

```java
public final class SynchronizedCounter {
    private int count;

    public synchronized void increment() {
        count++;
    }

    public synchronized int get() {
        return count;
    }
}
```

Two `synchronized` instance methods on **the same `SynchronizedCounter` object** lock on `this`. When `increment()` holds the monitor, another thread calling `get()` or `increment()` on that same instance must wait. With a consistent locking protocol, the increment is protected and reads have proper visibility guarantees.

You can also write:

```java
private final Object lock = new Object();
private int count;

public void increment() {
    synchronized (lock) {
        count++;
    }
}
```

These two snippets are **class member examples**, not standalone runnable programs with `main()`. If combined into a class, use one consistent locking discipline for all related accesses.

Conditions for a correct fix:

- **Every updater** uses the same lock; no other code increments `count++` outside the locked region.
- If consistent observation is needed, **every reader** must also follow the corresponding protocol.
- Do not create a new `new Object()` per call to lock on; different locks do not exclude each other.
- Keep the locked section reasonably small; in particular, avoid placing long-running I/O inside the lock block unnecessarily.

`synchronized` is appropriate when protecting **multiple steps or multiple fields** under a shared invariant, such as updating a counter while simultaneously updating another data structure so that both remain consistent.

## 7. Fixing with AtomicInteger

`java.util.concurrent.atomic.AtomicInteger` provides an `int` value along with atomic update APIs:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger count = new AtomicInteger(0);

int afterFirst = count.incrementAndGet(); // Increment, return new value: 1
int beforeSecond = count.getAndIncrement(); // Increment, return old value: 1
int afterAdd = count.addAndGet(5);         // Add 5, return 7
int current = count.get();                // Read 7
```

`incrementAndGet()` has the semantics of **returning the value after incrementing**, similar to `++count`; `getAndIncrement()` **returns the value before incrementing**, similar to `count++`. The crucial difference is that both `AtomicInteger` methods provide **atomic updates** on that instance.

For example, when two threads concurrently call `getAndIncrement()` and the counter starts at 0: the two return values are `0` and `1` respectively (which thread gets which is nondeterministic); after both complete, `get()` is `2`.

**Do not split the update into two calls:**

```java
count.set(count.get() + 1); // CAN STILL LOSE UPDATES
count.incrementAndGet();    // ATOMIC UPDATE
```

`get()` and `set()` individually have the API's guarantees, but combining them in a Java expression **does not form a single atomic update**. If complex logic depends on the old value, consider `updateAndGet(...)`, `getAndUpdate(...)`, `compareAndSet(expected, update)`, or `accumulateAndGet(...)`.

Many atomic algorithms rely on compare-and-set (CAS) and may retry under contention. Therefore, update functions passed to `updateAndGet`/`accumulateAndGet` should have no side effects other than computing the new value: the function may be re-invoked if an update attempt fails.

**Limitation:** `AtomicInteger` protects **a single `int` value**; it does not automatically turn a sequence of updates across multiple fields or multiple objects into an atomic transaction. If you need unique sequential numbers with atomic increments, `getAndIncrement()` is usually suitable; if multiple fields must stay synchronized, use an overarching locking protocol.

## 8. LongAdder for High-Contention Statistical Counters

`java.util.concurrent.atomic.LongAdder` is useful when **many threads concurrently increment a statistical counter**. It can stripe updates across multiple internal cells to reduce contention, instead of forcing all threads to contend on a single value like `AtomicInteger`.

```java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();
requests.increment();
requests.add(5L);
long currentEstimate = requests.sum();
```

Key distinctions:

- `LongAdder.increment()` allows accumulating concurrent increments.
- **`sum()` is not an atomic snapshot** while other threads are still updating. The result during execution may not reflect a single linearized state.
- After updaters have finished and synchronization has waited for their completion, `sum()` can be used to obtain the final total.
- `LongAdder` does not provide a `getAndIncrement()` result to issue sequential IDs; do not use it if every increment must return a unique atomic sequence number.

`LongAdder` fits request counters, event counters, and high-throughput metrics. `AtomicInteger` is a better fit when you need an atomically updated counter with per-operation read/write values. Do not assume `LongAdder` is always faster: performance depends on contention levels and workload; measure when optimizing in practice.

## 9. Decision Table and Common Mistakes

| Approach | Safe for concurrent increments by multiple threads? | Reason |
|---|---|---|
| `int count; count++;` | No, if shared without synchronization | Read–modify–write can interleave |
| `volatile int count; count++;` | No | Visibility does not create an atomic update |
| `count += 1` or `++count` | No, on an unsynchronized shared variable | Same reason |
| `synchronized (sameLock) { count++; }` | Yes, if all accesses obey the lock | Protects the entire read–compute–write section |
| `AtomicInteger.incrementAndGet()` | Yes | Atomic increment |
| `AtomicInteger.set(get() + 1)` | No | Two separate calls; can be interleaved |
| `LongAdder.increment()` | Can be used for concurrent accumulation | `sum()` is not an atomic snapshot between updates |
| Local counter used by a single thread only | Yes for normal incrementing | No race due to sharing |

### Mistake: "It Passed When I Tested It"

Races depend on thread scheduling. One execution producing the right result does not prove thread safety. Write tests for **risky interleavings**, like the latch example. For a proper counter, verify the total after all tasks complete.

### Mistake: Locking on Different Objects in Different Places

`synchronized(lockA)` does not protect against another thread using `synchronized(lockB)` if `lockA != lockB`. The two threads will run concurrently on two different monitors. When shared state is guarded by a lock, the locking rule must be uniform across every access path.

### Mistake: Assuming Every Sequence of AtomicInteger Calls Is Atomic as a Group

`incrementAndGet()` is an atomic update, but two consecutive calls—such as `get()` followed by `set()`, or updating two `AtomicInteger` objects—do not automatically form an overall atomic transaction. If an invariant spans multiple states, use an appropriate design or locking mechanism.

### Mistake: Reading the Total Before Tasks Finish

Even an atomic counter is still incrementing while workers are running. A mid-flight `get()` does not necessarily equal the expected final result. Wait for all tasks to finish (`join()`, `Future.get()`, or an equivalent primitive), then read.

### Mistake: Forgetting int Range Limits

`int` ranges from `-2_147_483_648` to `2_147_483_647`. Both `count++` and `AtomicInteger.incrementAndGet()` follow 32-bit integer overflow semantics; incrementing past `Integer.MAX_VALUE` wraps around to `Integer.MIN_VALUE`. If the total can exceed this, consider `AtomicLong`, `LongAdder`, and a business threshold check policy. **Atomicity does not prevent integer overflow**.

### Mistake: Reads/Writes Not Following the Same Protocol

If a `synchronized` method increments `count` while another method directly assigns `count = 0` without locking, the counter no longer has consistency guarantees. Keep fields `private` and centralize operations into methods following the same locking protocol or using the same atomic object.

## 10. Practical Workflow

1. **Determine variable ownership:** does it live within a single thread, or is it read/written by multiple threads?
2. **Identify requirements:** only need a final total; need to return an incremented ID per call; or need to keep multiple fields synchronized?
3. **Single shared counter with standalone increments:** use `AtomicInteger` or `AtomicLong` and their atomic update methods.
4. **Multi-step or multi-field updates:** use `synchronized` or an appropriate lock mechanism consistently across all access paths.
5. **High-contention statistics without requiring an atomic snapshot mid-run:** consider `LongAdder`.
6. **Testing:** reproduce race scenarios to confirm the cause; after fixing, wait for workers to complete and verify the final total along with related invariants.

**Self-check 1:** Two threads each call `count++` once on `volatile int count = 0`. Is `count == 2` guaranteed? **No**, because both can still read 0 before writing 1.

**Self-check 2:** With an `AtomicInteger` initialized to 0, what values do two `getAndIncrement()` calls return? Under an atomic update ordering, they return `0` and then `1`; the final result is `2`. You cannot predict in advance **which thread** receives which value.

**Self-check 3:** Main calls `join()` after two workers increment an unsynchronized `int count`. Does that automatically fix lost updates? **No**. `join()` helps wait and observe after threads finish; it does not protect the increments that already occurred.

**Takeaway:** `count++` is a read–compute–write expression, **not an atomic update** when multiple threads modify a shared variable. `volatile` addresses memory visibility, while `synchronized` and `AtomicInteger` provide the necessary update guarantees; `LongAdder` targets high-contention statistical counters with different semantics for reading the sum.
