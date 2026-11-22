# volatile Does Not Make an Increment Atomic

## 1. Scenario: Two Threads Incrementing a Counter

A Java application has multiple threads recording events. We use a counter variable:

~~~java
class Counter {
    volatile int value = 0;

    void increment() {
        value++;
    }
}
~~~

Many people assume that adding `volatile` makes every thread "always see the latest value," so if two threads each call `increment()` once, `value == 2` is guaranteed. That conclusion is **wrong**.

`volatile` solves specific issues regarding **visibility of changes across threads** and **memory ordering** under the Java Memory Model. It **does not turn a read–compute–write sequence into an atomic read-modify-write operation**.

If two threads both read `value == 0` before either writes back, both can compute `1` and both write `1`. After two "increments," the result is still `1`: one update has been lost (**lost update**).

This lesson focuses on distinguishing visibility from atomicity, recognizing bugs in `++`/`+=`, reproducing the bug deterministically, choosing between `AtomicInteger`, `synchronized`, or `Lock`, and properly testing concurrency contracts.

## 2. What Does volatile Actually Guarantee?

In Java, a field declared as:

~~~java
private volatile int count;
~~~

has important properties:

1. **Visibility:** `volatile` reads and writes obey the synchronization order of the Java Memory Model. A volatile write *happens-before* subsequent reads of **the same volatile variable** in the synchronization order. As a result, properly published information becomes visible to the reading thread.
2. **Ordering:** volatile operations establish necessary ordering constraints on related memory operations. For example, when a thread writes ordinary data and then writes a volatile flag, another thread that reads the published flag value can see those earlier data writes via the happens-before relationship.
3. **Each volatile access is a single read or write with synchronization semantics:** an individual access to a `volatile int`/`volatile long` cannot be "torn" in half. However, **the entire `count++` expression** still consists of multiple steps.

The phrase "always sees the latest value" is merely an intuitive phrasing that easily misleads. A reading thread at a given moment can still read a value before another thread performs the next write. `volatile` **does not make threads wait for each other** and does not guarantee that the value read will remain unchanged before the reading thread writes back.

### Happens-Before Does Not Mean an Atomic Transaction

Suppose Thread A writes `data = 42` and then `ready = true` (where `ready` is declared volatile). Thread B reads `ready == true` following the proper publication protocol, and then reads `data`: writes before A's volatile publication are ordered before operations after B's corresponding read via happens-before.

This is very useful for **status flags** or **publishing completed state**. However, if two threads both write `data = data + 1`, the update condition based on the old value requires separate **atomicity**. A volatile flag does not automatically protect that computation.

| Requirement | Does `volatile` alone satisfy it? | Why |
|---|---|---|
| One thread writes a stop flag, another reads it | Can be suitable | Simple single-flag protocol, independent reads/writes |
| Multiple threads call `counter++` without losing updates | **No** | Read and write are separate and can interleave |
| Writing a reference to a fully constructed immutable config | Can be suitable | Publishing the reference via volatile creates visibility |
| Multiple threads update individual fields of the object pointed to by a volatile reference | **Not automatically** | `volatile` on the reference does not lock inner fields |
| Money transfer: check balance then deduct as one action | **No** | Condition and mutation must be protected together |
| Reading a consistent snapshot of multiple variables | **Not automatically** | Independent reads may come from different points in time |

## 3. Why Is count++ Three Logical Steps?

The expression:

~~~java
count++;
~~~

logically executes:

~~~text
1. Read the current value of count.
2. Compute the new value = read value + 1.
3. Write the new value back to count.
~~~

This is the logical model of the expression, **not a guarantee of three fixed machine instructions or three bytecodes**. The compiler and JVM may optimize while still respecting the Java Memory Model; having two volatile accesses inside one read-modify-write does not create an uninterruptible transaction.

A valid interleaving:

| Order | Thread A | Thread B | Value stored in count |
|---|---|---|---|
| 0 | — | — | 0 |
| 1 | Reads 0 | — | 0 |
| 2 | — | Reads 0 | 0 |
| 3 | Computes 1 | — | 0 |
| 4 | — | Computes 1 | 0 |
| 5 | Writes 1 | — | 1 |
| 6 | — | Writes 1 | 1 |

Both reads are valid because at that moment neither thread had written 1. No "missed visibility of an update" occurred; **an update was lost because two independent computations were based on the same old state**.

The following expressions are also compound operations and **do not become atomic just because of volatile**:

~~~java
counter = counter + 1;
counter += 1;
counter++;
++counter;
if (counter == 0) {
    counter = 1;
}
~~~

The snippet above only illustrates ways of updating a `counter` variable declared in a method or class; these expressions do not automatically protect the entire read–check–write relationship. With a conditional assignment, two threads can both observe 0 and both assign 1. Whenever a computation depends on current state, treat it as an operation requiring atomicity analysis.

## 4. A Java 17+ Program to Deterministically Reproduce Lost Updates

Naive tests that spawn 100 threads calling `counter++` many times **might** coincidentally produce the right result, because thread scheduling is not guaranteed. To prove the issue without relying on luck, the following example uses two latches:

- Both threads **must read the old value** and then signal they have read.
- Only when both have finished reading does the main thread allow both threads to write.
- Each thread writes exactly `snapshot + 1`, so two increments based on the same `snapshot == 0` leave only 1.
- The comparison part uses `AtomicInteger.incrementAndGet()`, yielding 2.

Save in **`VolatileLostUpdateDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class VolatileLostUpdateDemo {
    static final class VolatileCounter {
        volatile int value;
    }

    public static void main(String[] args) throws InterruptedException {
        VolatileCounter counter = new VolatileCounter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch releaseWrites = new CountDownLatch(1);

        Runnable nonAtomicIncrement = () -> {
            int snapshot = counter.value;
            bothRead.countDown();
            try {
                releaseWrites.await();
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return;
            }
            counter.value = snapshot + 1;
        };

        Thread first = new Thread(nonAtomicIncrement);
        Thread second = new Thread(nonAtomicIncrement);
        first.start();
        second.start();
        bothRead.await();
        releaseWrites.countDown();
        first.join();
        second.join();

        System.out.println("volatile count = " + counter.value);

        AtomicInteger atomicCounter = new AtomicInteger();
        Thread third = new Thread(atomicCounter::incrementAndGet);
        Thread fourth = new Thread(atomicCounter::incrementAndGet);
        third.start();
        fourth.start();
        third.join();
        fourth.join();

        System.out.println("atomic count   = " + atomicCounter.get());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac VolatileLostUpdateDemo.java
java VolatileLostUpdateDemo
~~~

Exact output:

~~~text
volatile count = 1
atomic count   = 2
~~~

Note: the two latches are not a trick to "break volatile"; they simply enforce a **valid interleaving** that a concurrent program can genuinely encounter. `bothRead.await()` ensures both reads have occurred; `releaseWrites.countDown()` lets the two writes proceed. Neither write happens before both reads complete, so both hold `snapshot == 0`. Each write is still a valid volatile write, yet there is no mechanism to prevent the lost update.

When using `AtomicInteger.incrementAndGet()`, each increment is an atomic read-modify-write; two successful increments from 0 yield 2. `join()` waits for thread completion and ensures the main thread reads the result after the operations in the threads have finished under the happens-before relationship.

**Do not use `Thread.sleep()` to claim you have reproduced a race condition.** Sleep only hints at timing; it does not enforce execution order. Likewise, do not conclude `volatile++` is safe just because a run of 1 million increments happened to produce the right sum.

## 5. Distinguishing Visibility, Atomicity, and Mutual Exclusion

These three concepts are related but cannot substitute for one another:

- **Visibility:** one thread sees information published by another thread according to memory ordering rules. `volatile`, monitor locks, atomic classes, and many synchronization primitives establish visibility.
- **Atomicity:** an observe/update action must occur as a single indivisible unit at the abstraction level being considered. `AtomicInteger.incrementAndGet()` guarantees this for **one atomic variable**; `synchronized` can protect a larger logical region.
- **Mutual exclusion:** at any time, only one thread holds the required lock to execute a region of operations. `synchronized` or `ReentrantLock` can protect an entire check-then-act sequence across multiple variables if **all related read/write paths follow the same lock**.

`volatile` provides necessary memory-order relationships but **grants no lock**. `AtomicInteger` performs certain atomic operations on a single state, typically without a monitor; however, **chaining multiple atomic operations still does not necessarily form a transaction**. For example, `balance.get() >= amount` followed by `balance.addAndGet(-amount)` can be interleaved by another thread if business logic requires the check and deduction to happen together.

## 6. Solutions for Incrementing Without Lost Updates

### 6.1. AtomicInteger and AtomicLong

When multiple threads update **a single independent integer counter**, choose `AtomicInteger` (int) or `AtomicLong` (long):

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger(0);
int after = counter.incrementAndGet();  // atomically increment, return new value
int before = counter.getAndIncrement(); // atomically increment, return pre-increment value
int current = counter.get();           // read atomic state
~~~

This is an illustrative snippet placed inside a method. Note the two methods return different values, even though both increment by exactly one unit:

| Operation on counter = 5 | Return value | Stored value after operation |
|---|---:|---:|
| `incrementAndGet()` | 6 | 6 |
| `getAndIncrement()` | 5 | 6 |
| `addAndGet(3)` | 8 | 8 |
| `getAndAdd(3)` | 5 | 8 |

The table considers each operation **independently**, starting from the same value 5. These increments use atomic operations (typically implemented via CAS or an appropriate intrinsic), not merely adding `volatile` to an `int`.

If long-running counts may exceed `int` limits, use `AtomicLong`, though `long` is finite as well. `AtomicInteger.incrementAndGet()` **can still overflow and wrap** at `Integer.MAX_VALUE`; it only guarantees atomicity, not automatic mathematical bounds checking. If overflow must be rejected, you can use:

~~~java
counter.updateAndGet(Math::incrementExact);
~~~

`updateAndGet` applies the function to the previous value and attempts an atomic update; the function may be re-invoked by the JVM under contention, so it must be **pure (side-effect-free)**. `Math.incrementExact` throws `ArithmeticException` if adding 1 exceeds `int` bounds; it produces no side effect beyond the calculation.

### 6.2. synchronized for a Sequence of Operations

When the entire read-modify-write must stay together, a monitor protects the whole increment:

~~~java
public final class SynchronizedCounter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int get() {
        return value;
    }
}
~~~

This is a class that can compile standalone in `SynchronizedCounter.java`, though it has no `main`. The two `synchronized` instance methods use the same monitor of **one instance**. If all accesses to `value` go through properly synchronized methods, `volatile` on `value` is **unnecessary**: the monitor provides both mutual exclusion and visibility relationships.

If you write `synchronized void increment()` while elsewhere directly reading or writing `value` without the same lock, the design may still suffer from races or lack of visibility. Control every access path, not just one method.

### 6.3. ReentrantLock When Explicit Lock Control Is Needed

~~~java
import java.util.concurrent.locks.ReentrantLock;

public final class LockedCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int value;

    public void increment() {
        lock.lock();
        try {
            value++;
        } finally {
            lock.unlock();
        }
    }

    public int get() {
        lock.lock();
        try {
            return value;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Save as `LockedCounter.java` if you want to compile this class separately. The `try/finally` pattern is necessary to always unlock if an exception is thrown. Every path accessing state must use **the same lock**. `ReentrantLock` is useful when you need `tryLock`, timeouts, interruptible locking, or `Condition`; do not add unnecessary complexity if `synchronized` suffices.

### 6.4. LongAdder for High-Contention Statistical Counters

`LongAdder` typically offers good throughput when many threads concurrently add to a **metric/counter**:

~~~java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();
requests.increment();
requests.add(4L);
long observed = requests.sum();
~~~

The code above is an example placed inside a method. `sum()` may not be an **atomic snapshot** while other threads are still updating; a `sum` concurrent with multiple increments is unsuitable if you need unique sequence numbers, hard quota limits, or decisions that must be exact at a single point in time. If you need an atomic value for a counter, prefer `AtomicLong`; if consistency across multiple conditions is needed, choose an appropriate logic synchronization mechanism.

## 7. What Is CAS? Why Is compareAndSet Useful?

**Compare-and-set (CAS)** expresses the requirement: "update to the new value only if the current value is still the expected one." With `AtomicInteger`:

~~~java
AtomicInteger state = new AtomicInteger(0);

boolean success1 = state.compareAndSet(0, 1); // true
boolean success2 = state.compareAndSet(0, 2); // false
System.out.println(state.get());              // 1
~~~

This snippet lives in a method with `import java.util.concurrent.atomic.AtomicInteger`. The first call sees 0 and atomically sets it to 1. The second expects 0, but state is already 1, so it fails without writing. CAS cannot skip state verification when a conditional update is required.

A CAS loop typically looks like this:

~~~java
int observed;
int updated;
do {
    observed = state.get();
    updated = Math.incrementExact(observed);
} while (!state.compareAndSet(observed, updated));
~~~

Assume `state` is an initialized `AtomicInteger`. If another thread updates between `get` and `compareAndSet`, CAS fails, and the loop re-reads and recomputes. Addition itself is not naturally atomic: **the conditional commit operation** prevents lost updates.

You can use `incrementAndGet` instead of the loop above when no custom policy is needed; the atomic class implementation already provides the appropriate operation. A CAS loop may iterate multiple times under high contention, so avoid calling APIs with side effects, sending emails, writing business logs, or deducting external balances inside a function that may be retried.

**Scope note:** CAS on a single `AtomicInteger` atomically updates only that one value. If you need to synchronize a balance and a transaction history, a mechanism coordinating the entire state is required; CAS on a counter does not automatically become a database transaction.

## 8. When Is volatile Alone Reasonable?

`volatile` remains important and useful. For example, a background thread performs work governed by a stop flag controlled by another thread:

~~~java
public final class StopFlag {
    private volatile boolean stopped;

    public void requestStop() {
        stopped = true;
    }

    public boolean shouldStop() {
        return stopped;
    }
}
~~~

This is a compilable class in `StopFlag.java`. With a **simple single control flag** model, writing `true` and reading the flag are independent accesses; there are no multiple writers needing coordinated accumulation. The worker thread must check `shouldStop()` periodically and know how to terminate. In tasks involving blocking I/O/sleep/wait, `Thread.interrupt()` or higher-level cancellation may be necessary; a flag will not wake a blocked thread on its own.

Another case is **publishing an immutable configuration reference**: fully construct the immutable object, then write its reference to a volatile field; readers reading that reference can see the published state. However, if the object contains a mutable `ArrayList` and threads mutate the list without synchronization, `volatile` on the reference does not protect those mutations.

### volatile on References, Arrays, Wrappers, and 64-bit Numbers

- `volatile int[] numbers` gives volatile semantics to reading/writing the **array reference**; it **does not make `numbers[0]++` atomic**. When element-level atomicity is needed, look at `AtomicIntegerArray` or locks.
- `volatile Integer count` does not make `count++` atomic either; each increment also involves unboxing/boxing and swapping the reference. If the value can be null, unboxing can even throw `NullPointerException`.
- `volatile long value` guarantees that a single read or write of the `long` variable is atomic under the Java Memory Model; however, `value++` is still not atomic. Do not confuse atomic 64-bit access with atomic read-modify-write.
- `volatile` does not guarantee logical processing order across **multiple variables**. Two separate volatile fields do not produce a consistent snapshot if a writer updates them step by step.

## 9. Check-Then-Act and Multiple Variables: Harder Bugs Than counter++

Lost updates are just a simple example. Consider a business rule:

~~~java
if (availableSeats > 0) {
    availableSeats--;
    reserveSeat();
}
~~~

This is Java pseudocode inside a method with corresponding variables/methods. Even if `availableSeats` is volatile, **two threads can both see 1, both enter the branch, and both call `reserveSeat()`**. The result can be two bookings when only one seat remained. `availableSeats--` races, and calling `reserveSeat()` is also a side effect requiring protection.

If you only need to decrement an integer variable conditional on it being greater than 0, you can write a CAS loop to check the condition and update together. But if `reserveSeat()` needs to persist to a DB, call an external service, or coordinate multiple variables, appropriate transactions/locks/idempotency are needed at the actual system holding the state. An `AtomicInteger` in one JVM **does not protect data across multiple processes or multiple service instances**.

Similarly, `if (balance.get() >= withdrawal) balance.addAndGet(-withdrawal)` is not an atomic action just because `balance` is an `AtomicInteger`: check and update are separate. The condition and update must be placed in one CAS loop or the same critical section; when multiple data sources exist, the solution must cover the entire invariant.

## 10. Properly Testing Race Conditions

Do not rely on thread scheduler randomness as a test's success criterion. A program running 1,000,000 iterations may **never hit the faulty interleaving on the current machine**, which proves nothing about safety. `Thread.sleep(100)` only introduces a delay; it provides no contract ensuring one thread read before another wrote.

Useful testing approaches:

1. **Intentionally reproduce schedules:** like the two `CountDownLatch` instances in `VolatileLostUpdateDemo`, force both to read the same old state and then both write.
2. **Assert invariants:** with n threads, each incrementing m times using a proper atomic/locked method, after `join` the expected value is `n × m` assuming no overflow and no failed attempts.
3. **Test boundary states:** counters near `Integer.MAX_VALUE`, negative values, overflow, concurrent reset operations alongside increments, interrupts, or exceptions.
4. **Test the entire state:** if business logic has check-then-act conditions or multiple fields, tests must cover both condition and action, not just incrementing an integer.
5. **Observation and auditing:** for asynchronous tasks, use latches, barriers, executors, and sensible timeouts to avoid hanging tests; capture errors from child threads rather than letting a thread die unnoticed by the test.
6. **Distinguish functional testing from stress testing:** stress tests are useful for uncovering bugs, but they do not replace analyzing happens-before and protocol atomicity.

### Example Checking Expected Values

When using `AtomicInteger`:

~~~java
AtomicInteger safe = new AtomicInteger();
safe.incrementAndGet();
safe.incrementAndGet();

if (safe.get() != 2) {
    throw new AssertionError("Lost atomic increments");
}
~~~

This is an illustrative snippet placed inside a method with `AtomicInteger` imported. To verify under multithreading, create/synchronize threads and wait for all to complete before the assertion, similar to the runnable example in Section 4. `get()` while threads are still running returns the value at the time of reading, not inherently the "final total."

### Do Not Confuse Post-Join Visibility with Atomicity

After `thread.join()` completes successfully, the waiting thread has the necessary happens-before relationship with the operations of the terminated thread; however, that **does not recover updates already lost** before joining. In the example where two threads both write 1, main accurately and completely observes 1 after `join`. The flaw lay in **two threads performing two non-atomic read-modify-write operations**, not in reading the final result.

## 11. Choosing a Mechanism Based on Requirements

| Requirement | Commonly suitable choice | Limitations to remember |
|---|---|---|
| A stop flag / state publication with a simple protocol | `volatile boolean` / volatile reference | Does not synchronize complex side effects or multiple states |
| Multiple threads accurately incrementing an integer | `AtomicInteger` / `AtomicLong` | Can overflow; one atomic operation does not replace a transaction |
| Multiple threads summing metrics under high contention | `LongAdder` | `sum()` is not an atomic snapshot during updates |
| Conditional update of one integer field | CAS or `updateAndGet` with a pure function | Must handle retries and contention |
| Protecting a sequence of operations or multiple fields | `synchronized` or `ReentrantLock` | Every access path must use the same lock |
| State consistency across DB / multiple processes | Transactions, storage-level locks / atomic updates | In-memory atomics inside a single JVM are insufficient |

No keyword can replace identifying the **atomic unit of the problem**. If that unit is just a single increment, one `AtomicInteger` operation may suffice. If the unit is "check quota, create invoice, deduct quota, and write history," you need a solution protecting the entire workflow at the actual shared state boundary.

## 12. Common Mistakes

- **Assuming volatile makes ++ atomic:** a volatile read and a volatile write can still be interleaved by other threads.
- **Changing `volatile int` to `volatile long` to be "safer":** widens the value range without fixing lost updates.
- **Using `AtomicInteger.get()` then `set(get() + 1)`:** two separate atomic calls still **do not form an atomic increment**. Use `incrementAndGet` or proper CAS.
- **Assuming `synchronized` on one method is enough while other places write unlocked:** every access path to the invariant must be consistent.
- **Using `LongAdder` to issue unique IDs or enforce hard quotas:** `sum` does not provide a linearized snapshot in that manner.
- **Reading two volatile fields and trusting a consistent snapshot:** each field may come from a different update phase.
- **Running many loop iterations and concluding there is no race:** a race is a correctness issue across all allowed schedules, not disproven by a few runs.
- **Trying to fix races with `sleep`, `yield`, or `Thread.onSpinWait`:** they may affect scheduling or performance, but do not turn read-modify-write into an atomic operation.
- **Switching a counter to atomic while keeping uncoordinated direct assignments/resets:** every state mutation must obey the same contract.
- **Ignoring overflow:** atomic `int` increments do not mean exact increments over unbounded mathematical integers.

## 13. Self-Practice Exercises and Answers

**Exercise 1.** Two threads concurrently execute `volatileCounter++` when the initial value is 5. What can the result be if each thread runs once and both have finished? Explain the schedule that causes a lost update.

**Exercise 2.** Does replacing `counter++` with `atomicCounter.set(atomicCounter.get() + 1)` fix the race? If not, how should it be fixed?

**Exercise 3.** Explain why `volatile boolean stop` can be suitable for a simple stop flag, whereas `volatile int soldTickets` is insufficient for the operation "if tickets remain, sell one ticket."

**Exercise 4.** A collector uses `LongAdder` to count requests and needs to display a near-real-time total. If generating a report requires an exact total consistent with the list of requests at the exact same point in time, is calling `sum()` alone enough?

**Exercise 5.** Why can an assertion after `join` still observe `1` in the two-increment example? Has `join` guaranteed visibility?

**Suggested answers:**

1. It can be **6 or 7**: both threads read 5 and both write 6, yielding 6; or one thread completes before the other reads, yielding 7. With exactly two increments from 5 and no reset/overflow, 8 is not a valid outcome.
2. No; `get` and `set` are separate. Use `incrementAndGet` or a CAS loop; if conditions or side effects are involved, protect the entire logic.
3. A stop flag is an independent message, whereas selling a ticket is a sequence of checking availability then deducting/recording; multiple threads can pass the check together.
4. Not enough if a consistent snapshot across multiple updating structures is required; a snapshot/transaction/synchronization mechanism satisfying the invariant is needed.
5. `join` provided the happens-before relationship between the terminated thread's activity and the waiting thread; main sees the final stored result 1, but the two earlier computations themselves lost one increment.

## Java SE 17 References

- [Java Language Specification §17.4 — Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4)
- `AtomicInteger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- `LongAdder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- `ReentrantLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html

**Key takeaway:** `volatile` establishes visibility and ordering under the Java Memory Model; `counter++` remains a multi-step read-modify-write. When every increment must be preserved, use true atomic operations or protect the entire update with a lock.
