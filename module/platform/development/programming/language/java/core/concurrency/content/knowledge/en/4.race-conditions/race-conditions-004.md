# Read-Modify-Write Is Not an Atomic Operation in Java

> **Key takeaway:** Expressions like `counter++`, `counter += 1`, or `counter = counter + 1` look like a single statement, but in reality they require **reading the current value → computing the new value → writing it back**. When multiple threads concurrently update shared state without protecting **the entire sequence of operations**, an update can be lost (*lost update*). `volatile` helps with visibility and ordering, but **does not make a multi-step increment atomic**.

This lesson belongs to the **Race Conditions** group in general Java concurrency. The examples use Java SE (Java 17+), `Thread`, `synchronized`, and `java.util.concurrent`; Spring mechanisms are not considered.

## 1. What does atomic mean in this situation?

An atomic operation, to threads observing the relevant state, has the effect of occurring **completely at a single logical point in time**; other threads do not observe intermediate states of that operation itself. When we say a read-modify-write (RMW) update is atomic, we mean that **reading and writing based on the read value** form a single unit that cannot be invalidated by a competing update interleaving in between.

For example, incrementing a shared counter from `7` to `8`:

~~~text
1. READ:   old = counter    // old = 7
2. MODIFY: next = old + 1   // next = 8
3. WRITE:  counter = next   // counter = 8
~~~

A single thread can do this correctly. However, if two threads perform these steps concurrently without synchronization, interleaving schedules can cause **both to read the same old value** and write back the same result.

Distinguish things that are often conflated:

| Property | Question | Does it guarantee atomic RMW? |
| --- | --- | --- |
| **Individual atomic read/write** | Can a single read/write of a value be observed partially? | **Not enough.** Reading and writing are still two separate points in time. |
| **Visibility** | Do other threads see published changes? | **Not enough.** Seeing the new value does not prevent two threads from reading the same old value. |
| **Ordering / happens-before** | Which actions must be observed in a specific order? | **Does not by itself guarantee** that the entire RMW is a single indivisible unit. |
| **Atomic RMW** | Can a competing update interleave between the read and the write? | **Yes**, this is the exact guarantee needed to prevent lost updates for a counter. |
| **Multi-variable transaction** | Are multiple fields updated as a single invariant? | A single atomic counter is **not enough**; the entire invariant must be protected. |

The word "atomic" must always come with a **scope**: atomic for a single variable, a map entry, or an update across multiple fields? An operation can be atomic in a narrow scope but not atomic with respect to larger business logic.

## 2. How do race conditions and lost updates happen?

Suppose `counter = 7`, and two threads A and B concurrently execute `counter++`:

| Time step | Thread A | Thread B | Shared value |
| --- | --- | --- | --- |
| 1 | Reads `counter`, gets `7` | | `7` |
| 2 | | Reads `counter`, gets `7` | `7` |
| 3 | Computes `7 + 1 = 8` | | `7` |
| 4 | | Computes `7 + 1 = 8` | `7` |
| 5 | Writes `8` | | `8` |
| 6 | | Writes `8` | `8` |

After **two increments**, the expected result is `9`, but the actual result can be `8`. One update was lost: the later write was based on a stale snapshot and did not account for the update that had already occurred.

This is a **lost-update race** on shared data, not a bug caused by one thread "running too fast," nor is it related to scheduling priority. Adding `Thread.sleep` only changes the chance of interleaving; it does not fix the root cause.

The expressions below are all read-modify-write operations on a shared `int` variable:

~~~java
counter++;
++counter;
counter += 1;
counter = counter + 1;
~~~

With `counter++` and `++counter`, the return value of the expression differs (old value vs. new value), **but both require RMW**. In Java code, "one statement," "one operator," or "one line of source code" does not mean "one atomic operation." Bytecode, JIT, and CPU may implement them differently; what you must rely on is the **Java Memory Model/API contract**, not mechanical reasoning from the number of assembly or bytecode instructions.

### How does a race condition differ from a data race?

- **Race condition**: the outcome or correctness depends on how concurrent events interleave; a lost update is a classic example.
- **Data race** in the Java Memory Model refers to conflicting accesses to the same variable that are not ordered by an appropriate *happens-before* relationship, where at least one access is a write and the accesses are not synchronized (such as `volatile`).
- A design can suffer from a **logical race condition even with no data race on individual accesses**. For example, using `volatile int` gives individual reads/writes synchronization semantics, but separating the read and the write still allows lost updates. Therefore, "free of data races" and "correct algorithm" are two different statements.

## 3. Example 1 — deterministically reproducing a lost update

Instead of looping to increment a counter millions of times and hoping the race shows up, we **deliberately synchronize the interleaving point** so that both threads read the old value before either is allowed to write.

Create `LostUpdate.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;

public class LostUpdate {
    private static volatile int counter = 0;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothHaveRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int oldValue = counter;  // READ: both will read 0.
            bothHaveRead.countDown();

            try {
                allowWrite.await();  // Wait until both have read.
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            counter = oldValue + 1;  // WRITE: both write 1.
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");

        first.start();
        second.start();

        bothHaveRead.await();  // Ensure both have taken the snapshot.
        allowWrite.countDown();

        first.join();
        second.join();

        System.out.println("expected = 2");
        System.out.println("actual = " + counter);
    }
}
~~~

Compile and run:

~~~bash
javac LostUpdate.java
java LostUpdate
~~~

Output without external interruption:

~~~text
expected = 2
actual = 1
~~~

**Explanation of the guarantees:**

1. Each worker reads `counter` into the local variable `oldValue`, then decrements the `bothHaveRead` latch.
2. Main waits for `bothHaveRead.await()` to complete, meaning both have read before main calls `allowWrite.countDown()`.
3. Once allowed to write, each worker writes `0 + 1`. Two writes of the same value yield a final result of `1`, regardless of write order.
4. Main calls `join()` on both threads before printing, ensuring the writes have completed and the effects from the workers have an appropriate *happens-before* relationship with the observation after `join()`.

Making `counter` `volatile` is **intentional**: even when each read/write has volatile visibility semantics, the two steps `READ` and `WRITE` remain separate and do not form an atomic update. The `CountDownLatch` in the example is used to **force an interleaving schedule to demonstrate the bug**, not to fix the lost update. In a real version where you want an atomic increment, do not split a computation into two separate points in time without protecting them.

## 4. What does `volatile` guarantee, and what does it not?

In Java, `volatile` provides **visibility and ordering** guarantees for accesses to a variable declared volatile. Specifically, a volatile write *synchronizes-with* subsequent reads of the same volatile variable according to the Java Memory Model rules. Volatile accesses are placed in a total synchronization order, and individual volatile reads/writes have atomic semantics on the accessed value.

However:

~~~java
// Illustrates a logic bug, not a standalone program.
private static volatile int counter = 0;

static void increment() {
    counter++; // Volatile read -> add 1 -> volatile write.
}
~~~

This snippet **can still suffer from lost updates**. `volatile` does not lock out other threads between the read and the write, and it does not replace `synchronized`, `Lock`, or atomic RMW methods like `AtomicInteger.incrementAndGet()`.

Do not confuse different cases:

- `volatile boolean stopped` can serve as a simple stop flag when one thread writes and other threads read, if the logic only requires publishing/observing the flag.
- `volatile int counter` with **multiple writers** using `counter++` does not adequately protect updates.
- Reading a `volatile long` is atomic at the level of **a single read**; it still does not make `value++` atomic.
- `final` and safe publication of objects belong to different mechanisms; they do not by themselves make increments on mutable state atomic.

When analyzing concurrency, ask two separate questions: "Does the thread see the right/published value?" and "Can someone else update between the read and the write?" `volatile` solves part of the first question, not the second.

## 5. Fix 1 — lock the entire read-modify-write with `synchronized`

A shared monitor lock ensures that only one thread at a time enters the critical section protected by **the same lock**. For a counter, place the read, computation, and write inside the same synchronized block.

Create `SynchronizedCounter.java` (Java 17+):

~~~java
public class SynchronizedCounter {
    private static final Object LOCK = new Object();
    private static int counter = 0;

    private static void increment() {
        synchronized (LOCK) {
            counter++;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Runnable work = () -> {
            for (int i = 0; i < 100_000; i++) {
                increment();
            }
        };

        Thread first = new Thread(work, "first");
        Thread second = new Thread(work, "second");
        first.start();
        second.start();

        first.join();
        second.join();
        System.out.println("counter = " + counter);
    }
}
~~~

Run:

~~~bash
javac SynchronizedCounter.java
java SynchronizedCounter
~~~

Output:

~~~text
counter = 200000
~~~

Why this is correct:

- Every call to `increment()` acquires the **same** `LOCK`, so two threads cannot execute the RMW section at the same time.
- Unlocking a monitor has a *happens-before* relationship with the subsequent locking of that same monitor, allowing the next thread to observe updates from the previous thread.
- `join()` ensures main waits for all 200,000 `increment()` calls before reading/printing the result.
- The `counter` variable does not need to be `volatile` if **all competing accesses** follow the same synchronization discipline and reading the result is properly coordinated as done here.

Using **the right lock consistently** is critical. Locking on a different `new Object()` per thread is useless. If one write path uses `synchronized(LOCK)` while another competing read/write accesses `counter` directly without locking, the design can still be broken. Keep shared fields `private` and encapsulate update paths in a clear API.

### When to use `ReentrantLock`?

`java.util.concurrent.locks.ReentrantLock` can also protect the entire RMW, which is useful if you need `tryLock`, timed locking, interruptible lock acquisition, or `Condition` variables. Correct pattern:

~~~java
// Illustrative example; lock is a shared ReentrantLock.
lock.lock();
try {
    counter++;
} finally {
    lock.unlock();
}
~~~

Do not lock only around `counter = ...` after reading outside the lock; **reading to compute the new value must also be inside the same critical section**. `finally` ensures the lock is released even if the work inside throws an exception.

## 6. Fix 2 — use atomic read-modify-write from `AtomicInteger`

When you only need atomic operations on **a single counter**, `AtomicInteger` usually expresses intent more clearly than a dedicated monitor for the counter. Key methods:

| API | Atomic effect | Return value |
| --- | --- | --- |
| `getAndIncrement()` | Increments by 1 | Value **before** incrementing |
| `incrementAndGet()` | Increments by 1 | Value **after** incrementing |
| `getAndAdd(delta)` | Adds `delta` | Old value |
| `addAndGet(delta)` | Adds `delta` | New value |
| `compareAndSet(expected, update)` | Writes `update` only if current value equals `expected` | `true` if update succeeded |
| `updateAndGet(operator)` | Applies transformation function, retrying on contention | New value |

Create `AtomicCounter.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounter {
    private static final AtomicInteger counter = new AtomicInteger();

    public static void main(String[] args) throws InterruptedException {
        Runnable work = () -> {
            for (int i = 0; i < 100_000; i++) {
                counter.incrementAndGet();
            }
        };

        Thread first = new Thread(work, "first");
        Thread second = new Thread(work, "second");
        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("counter = " + counter.get());
    }
}
~~~

Run:

~~~bash
javac AtomicCounter.java
java AtomicCounter
~~~

Output:

~~~text
counter = 200000
~~~

`incrementAndGet()` protects an RMW update on **the value of that atomic object itself**. When multiple threads call it, updates to the atomic variable are not lost by overwriting each other after taking a stale snapshot without checking.

**Common pitfall:** reading with `counter.get()`, computing manually, and calling `counter.set(...)` are **two separate operations**, not an atomic RMW:

~~~java
// Wrong if multiple writers compete:
int oldValue = counter.get();
counter.set(oldValue + 1);
~~~

Even though `get()` and `set()` each have thread-safe semantics individually, this combination still has a window between them. You must use **the proper atomic RMW method**, such as `incrementAndGet()` or `compareAndSet(...)` in an appropriate loop.

## 7. CAS: clarifying how atomic updates work when values can change

**Compare-and-set (CAS)** checks an expected value and updates it only if it still matches, in a single atomic operation. Pattern:

~~~text
current = atomic.get()
next    = f(current)
if atomic.compareAndSet(current, next):
    update succeeded
else:
    value changed or CAS failed
    -> re-read and retry computation from the new state
~~~

Create `CasCounter.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class CasCounter {
    private static final AtomicInteger counter = new AtomicInteger();

    private static void incrementWithCas() {
        while (true) {
            int previous = counter.get();
            int updated = previous + 1;
            if (counter.compareAndSet(previous, updated)) {
                return;
            }
            // Contention detected: retry with the current value.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Runnable work = () -> {
            for (int i = 0; i < 100_000; i++) {
                incrementWithCas();
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("counter = " + counter.get());
    }
}
~~~

Run:

~~~bash
javac CasCounter.java
java CasCounter
~~~

Output:

~~~text
counter = 200000
~~~

`compareAndSet(previous, updated)` prevents writing based on a stale value without rechecking. When another thread modifies the counter between `get` and CAS, CAS fails and the loop must recompute from the current state. The result is correct under any interleaving schedule, as long as the threads complete.

### Notes when using `updateAndGet()` or a CAS loop

~~~java
int newValue = counter.updateAndGet(current -> current + 1);
~~~

This is a concise way to express an atomic transformation. However, the update function **may be applied multiple times** because the library must retry under contention. Therefore:

- The update function should be **pure**, without external side effects such as writing to a database, sending notifications, incrementing another counter, or logging that you expect to happen only once.
- Do not read external mutable state inconsistently and expect CAS on one variable to protect data outside that variable.
- Do not turn a retryable CAS loop into a multi-resource protocol without designing a shared synchronization mechanism.
- If strict ordering of external actions is required, coordinate separately; atomicity on a single variable does not guarantee *exactly-once* execution of side effects.

**CAS does not mean all CAS algorithms are simple or free of concurrency issues.** For complex state structures, there are issues like ABA (where a value goes A → B → A so a naive CAS does not notice the intermediate change), high retry rates under contention, starvation, and proper state publication requirements. For a simple `int` counter increment, `AtomicInteger.incrementAndGet()` is usually a more readable choice than writing a manual loop.

## 8. Single-variable atomicity is not enough for multi-variable invariants

Suppose an account has two numbers `debit` and `credit` that must be updated together to preserve the invariant that their sum is 0. Using two separate `AtomicInteger` instances and doing:

~~~java
// Illustrates an invalid case for invariant atomicity.
debit.addAndGet(10);
credit.addAndGet(-10);
~~~

Each update may be atomic individually, but another thread can still observe the state **between the two operations**. If the logic requires both changes as **one consistent transaction**, protect them with the same `synchronized`/`Lock`, or represent the entire state as an immutable object and replace it via `AtomicReference<State>` using CAS on the whole state.

For example, to maintain the invariant `debit + credit == 0` in a single snapshot:

~~~java
// Illustrates a data type for an immutable state.
record BalanceState(int debit, int credit) {}
~~~

An `AtomicReference<BalanceState>` can hold a consistent version of the state and update both fields in a single CAS if computed properly and retried from the new state. This is not sufficient if sources of truth also live outside that state object; atomicity only applies to the exact scope designed.

The right question is not "have I used an `Atomic*` class?", but **does the set of data that must be updated consistently fit entirely within a single atomic operation?**

## 9. RMW on collections can also suffer from lost updates

Mistakes are not limited to `int` variables. With a shared map:

~~~java
// Illustrates a logic bug, not a standalone program.
// map is ConcurrentHashMap<String, Integer>.
Integer current = map.get("jobs");
int next = (current == null ? 0 : current) + 1;
map.put("jobs", next);
~~~

`ConcurrentHashMap.get()` and `put()` are each concurrent-safe by contract, but **get → compute → put** is not atomic when another thread also updates the same key. Two threads can read the same old value and end up incrementing only once.

`ConcurrentHashMap.merge`/`compute` provides atomic per-key update operations according to the API. Create `MapCounter.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentHashMap;

public class MapCounter {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();

        Runnable work = () -> {
            for (int i = 0; i < 100_000; i++) {
                counts.merge("jobs", 1, Integer::sum);
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("jobs = " + counts.get("jobs"));
    }
}
~~~

Run:

~~~bash
javac MapCounter.java
java MapCounter
~~~

Output:

~~~text
jobs = 200000
~~~

Here `merge("jobs", 1, Integer::sum)` performs an update for a single key under `ConcurrentHashMap`'s atomic contract. If the key is absent, the initial value is `1`; when present, the remapping function adds 1. The update function should be short and must not attempt to recursively update other mappings in the same map. Do not mistakenly assume `ConcurrentHashMap` makes **every sequence of operations** across multiple keys automatically atomic.

Similarly, even with `Collections.synchronizedMap(...)`, synchronizing individual method calls does not protect **the entire compound action** if you read and then write in two separate calls. You need a shared lock region or an atomic operation supported by the API.

## 10. When to use `LongAdder` instead of `AtomicLong`?

`LongAdder` is designed to reduce contention when **many threads update a sum-based statistic**. For example:

~~~java
// Illustrative; adder is a shared variable.
java.util.concurrent.atomic.LongAdder adder =
        new java.util.concurrent.atomic.LongAdder();
adder.increment();
long snapshot = adder.sum();
~~~

`LongAdder.increment()` is suitable for contended statistical writes; however, `sum()` **is not an atomic snapshot** across a series of concurrent updates in progress. The value read may exclude some concurrent updates. If a business decision depends on *"the exact counter value at a linearizable point in time"*, consider `AtomicLong` or explicit synchronization.

| Need | Usually suitable tool | Caveats |
| --- | --- | --- |
| Exact counter, atomic increment/decrement on one variable | `AtomicInteger` / `AtomicLong` | `get` followed by `set` is still not an atomic RMW |
| Protecting multiple actions or multiple fields as one critical section | `synchronized` / `ReentrantLock` | Every competing access path must use the same locking discipline |
| Incrementing statistical totals with many writers and high contention | `LongAdder` | `sum()` during concurrent updates is not an atomic snapshot |
| Updating a value for a single key in a concurrent map | `ConcurrentHashMap.merge/compute` | Atomic per key; does not create multi-key transactions |
| Replacing an immutable multi-field state with CAS | `AtomicReference<ImmutableState>` | Pure update function; understand retries and invariants |
| No shared state | Local variables, immutable objects, message passing | Simplest approach; avoids unnecessary synchronization |

Do not assume `LongAdder` is "faster" for every workload; measure contention, thread count, read frequency, and consistency requirements before switching.

## 11. Results and correctness: different kinds of verification needed

### Why can a one-million-iteration stress test "pass"?

A snippet like the following can sometimes print the right result, even though the logic is unsafe:

~~~java
// Illustrates a bug: sharedCounter++ is unprotected.
for (int i = 0; i < 1_000_000; i++) {
    sharedCounter++;
}
~~~

If two threads rarely collide due to the scheduler or coincidental JIT/CPU/load conditions, the bug may not manifest. A correct output in 100 or 10,000 runs **does not prove a program is thread-safe**. Conversely, the `LostUpdate` example in Section 3 controls the interleaving schedule with latches to produce a deterministic counterexample.

### How to verify an RMW fix

1. **Write the invariant.** For example: after two threads each increment exactly 100,000 times and both terminate normally, the counter must be 200,000.
2. **Identify the linearization point.** In `synchronized`, the update happens while the thread exclusively holds the lock; with `AtomicInteger.incrementAndGet()`, the API guarantees an atomic increment on that variable. Do not treat `Thread.sleep()` as a linearization point.
3. **Wait for completion properly.** Use `Thread.join()` or `Future.get()`. Do not read the result and assume the task must be done just because enough time has passed.
4. **Test intentional interleavings.** `CountDownLatch`/`CyclicBarrier` help coordinate phases; design tests to avoid infinite timeouts when a test fails.
5. **Check other access paths.** One writer not using the lock, or one leftover `get()+set()`, is enough to break the invariant.
6. **Evaluate performance separately.** Once correctness is established, measure throughput/latency and contention with a proper benchmark (e.g., JMH). Do not trade correctness for a favorable benchmark run.

### Common misconceptions to avoid

- **"`++` is a single operator, so it is atomic."** A source-level operator does not create an atomic contract for shared RMW.
- **"Changing it to `volatile int` fixes it."** Visibility/ordering is different from atomicity for a read–compute–write sequence.
- **"`AtomicInteger.get()` and `set()` are both atomic, so their combination is also atomic."** No; you need `incrementAndGet()`, CAS, or the appropriate RMW method.
- **"Each thread locking an object is fine."** No; synchronization must use the same lock protecting the same state.
- **"If `HashMap`/`ConcurrentHashMap` has thread-safe `get` and `put`, then a `get`–`put` sequence must be atomic."** No; use `merge`/`compute` or an appropriate protocol.
- **"One atomic counter protects all invariants across two variables."** No; the scope of atomicity must match the scope of the invariant.
- **"If the data after `join()` is right, the update process must be atomic."** `join()` waits for and makes visible writes made before the worker ended; it does not fix lost updates that occurred between workers.
- **"A CAS lambda runs only once."** A CAS update can retry; lambdas with side effects can easily be executed repeatedly.
- **"`LongAdder.sum()` always gives an exact instantaneous snapshot while writers are active."** No; `sum()` is not an atomic snapshot under concurrent updates.

## 12. Self-check

**Question 1.** Two threads share a `volatile int x` and each calls `x++` 1,000 times. After calling `join` on both, is `x` guaranteed to be 2,000?  
**Answer:** No. `volatile` guarantees individual access semantics, but `x++` is still a read-modify-write that can interleave.

**Question 2.** You have two `AtomicInteger`s, `a` and `b`. Is `a.incrementAndGet()` followed by `b.decrementAndGet()` atomic with respect to the invariant `a + b`?  
**Answer:** No. Each update is atomic on its own, but another thread can observe the state between the two updates.

**Question 3.** Does replacing `counter++` with `atomic.get(); atomic.set(old + 1);` solve lost updates?  
**Answer:** No. These are still two independent method calls; use `incrementAndGet()` or a CAS loop.

**Question 4.** With `ConcurrentHashMap<String,Integer>`, will two threads calling `get("k")` then `put("k", old + 1)` always count accurately?  
**Answer:** No. Use `merge("k", 1, Integer::sum)` to increment under the single-key atomic update contract.

**Question 5.** If you want to read an approximate statistical sum while many threads increment, is `LongAdder` a reasonable choice? If you need an exact snapshot for a business decision, should you blindly rely on `sum()`?  
**Answer:** `LongAdder` can be used for high-throughput statistics, but `sum()` under concurrent updates is not an atomic snapshot.

**Question 6.** In the `LostUpdate` experiment, why does every normal run print `actual = 1` regardless of the scheduler?  
**Answer:** Both threads are forced to read 0 before any write occurs. After release, both write 1; the order of the two writes does not change the result.

## Official references

- [Java Language Specification 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, synchronization, happens-before, and contention behavior.
- [`AtomicInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic increments and CAS.
- [`LongAdder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): distributed counter under high contention and limitations of `sum()`.
- [`ConcurrentHashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): per-key `compute` and `merge` updates.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phase coordination and memory consistency.
- [`ReentrantLock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): mutual exclusion and advanced lock control.

**Remember:** An atomic read + a computation + an atomic write **do not form an atomic read-modify-write**. For shared mutable state, use the right primitive that protects **the entire update** and matches the scope of the invariant.
