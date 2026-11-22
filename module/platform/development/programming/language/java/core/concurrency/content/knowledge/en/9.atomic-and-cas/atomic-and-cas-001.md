# AtomicInteger, AtomicLong, and AtomicBoolean in Java

When multiple threads read and modify a shared variable concurrently, three seemingly simple steps — reading a value, computing the new value, and writing it back — can interleave and corrupt data. `AtomicInteger`, `AtomicLong`, and `AtomicBoolean` in `java.util.concurrent.atomic` provide **atomic reads, writes, and updates on a single value** with well-defined memory guarantees under the Java Memory Model (JMM). They are particularly well suited for counters, sequence numbers, status flags, and simple state-transition protocols.

The most important point: **an atomic operation does not mean all surrounding logic is automatically atomic**. Using `AtomicInteger.incrementAndGet()` prevents lost updates when incrementing a counter, but a sequence of `get()` followed by `set()` still has an interleaving window; `AtomicBoolean` can guarantee that only one thread flips a flag from `false` to `true`, but it does not automatically guarantee that the work behind that flag has completed.

This lesson belongs to the **Atomic & CAS** topic of **general Java concurrency**. The APIs and examples use Java SE 17+, without relying on Spring Framework-specific concurrency mechanisms.

## 1. Why aren't ordinary `int`, `long`, and `boolean` enough?

Example:

```java
final class UnsafeCounter {
    private int value;

    void increment() {
        value++; // Not atomic.
    }

    int get() {
        return value;
    }
}
```

The snippet above is an illustrative class without `main`. Two threads can both read `value == 10`, both compute `11`, and both write `11`. The result is a **lost update**: two increment calls produce the effect of only one increment.

`value++` is a **read-modify-write** operation, not an uninterruptible single step. Marking the field as `volatile int value` provides visibility and ordering semantics for each individual volatile read/write, **but it does not make `value++` as a whole atomic**.

Separate three distinct needs:

- **Atomicity:** an operation executes as an indivisible step at the defined API boundary without other threads interleaving in the middle.
- **Visibility and ordering:** readers are guaranteed to observe prior writes when an appropriate happens-before relationship exists.
- **Coordination/progress:** which thread waits for whom, who has the right to execute a task, and when to stop or signal completion.

Atomic variables address the first two categories within **the scope of each operation and a properly designed protocol**. They do not replace `CountDownLatch`, `BlockingQueue`, `Future`, or monitors when you need progress coordination or multi-field transactions.

## 2. The three basic atomic classes

| Class | Managed value | Suitable use cases |
| --- | --- | --- |
| `AtomicInteger` | A signed 32-bit `int` | Task counts, small versions, numeric states, single-variable quotas |
| `AtomicLong` | A signed 64-bit `long` | Sequence numbers, large metrics, long-lived counters |
| `AtomicBoolean` | A `boolean` | One-time flags, enabled/stopped states, permission to start an operation |

All three reside in `java.util.concurrent.atomic` and allow **multiple threads to share a single instance**. Example:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicBoolean;

AtomicInteger total = new AtomicInteger(0);
AtomicLong sequence = new AtomicLong(1000L);
AtomicBoolean started = new AtomicBoolean(false);
```

This is a variable-declaration snippet, not a standalone program.

Having atomic fields does not automatically make an object thread-safe. If a class has an `AtomicInteger count` and an `ArrayList` modified by multiple threads, only **the operations guaranteed by the atomic class** are atomic; the list and related invariants still require separate design.

For counters incremented under extremely high contention, `LongAdder` is sometimes more suitable than `AtomicLong` for statistics. However, `LongAdder.sum()` while threads are updating **is not an atomic snapshot**, so do not substitute it arbitrarily when you need a linearizable value at a single point in time.

## 3. Key APIs: not just `get()` and `set()`

Commonly used methods:

| API | Meaning | Notes |
| --- | --- | --- |
| `get()` | Reads the value with volatile semantics | The value may change immediately after returning |
| `set(newValue)` | Writes the value with volatile semantics | An atomic write, not a conditional check-and-write |
| `getAndSet(newValue)` | Atomically replaces the value and returns **the old value** | Useful for reading-and-resetting a counter or claiming a flag |
| `compareAndSet(expected, update)` | If the current value equals expected, atomically sets it to update | Returns `true` on success; `false` if expected no longer matches |
| `compareAndExchange(expected, update)` | Conditional exchange, returning the value observed at the time of the operation | Added in Java 9; the return value reveals the actual observed state |
| `lazySet(newValue)` | Writes with release semantics (weaker than volatile `set` in certain respects) | Use only if you understand the required publication and ordering protocol |

Specifically on `AtomicInteger` and `AtomicLong`:

| API | Result |
| --- | --- |
| `getAndIncrement()` | Increments by 1, returns the value **before** incrementing |
| `incrementAndGet()` | Increments by 1, returns the value **after** incrementing |
| `getAndDecrement()` and `decrementAndGet()` | Decrements by 1; differ in returning the old vs. new value |
| `getAndAdd(delta)` | Adds delta, returns the old value |
| `addAndGet(delta)` | Adds delta, returns the new value |
| `getAndUpdate(fn)` and `updateAndGet(fn)` | Computes the new value using a unary function; the function may be re-invoked under contention |
| `getAndAccumulate(x, fn)` and `accumulateAndGet(x, fn)` | Computes the new value using a binary function; the function may be re-invoked if CAS fails |

`AtomicBoolean` has no increment/decrement methods; its core trio is `get`, `set`, and `compareAndSet`, along with `getAndSet`.

**The return-value convention is an important part of the contract.** A common mistake is calling `getAndIncrement()` while assuming it returns the new number, or calling `incrementAndGet()` when you intended to issue IDs starting from the pre-increment value.

## 4. CAS: How does Compare-And-Set work?

CAS expresses a conditional update:

```text
current = value of the atomic variable at the point of execution

if current == expected:
    set current = update
    return true
else:
    keep current unchanged
    return false
```

This is a **semantic model**, not pseudocode implemented as an ordinary read followed by an ordinary write. The power of CAS is that the check and update are guaranteed to be **atomic** by the operation's contract.

Example:

```java
AtomicInteger state = new AtomicInteger(10);

boolean first = state.compareAndSet(10, 20);   // true
boolean second = state.compareAndSet(10, 30);  // false
int now = state.get();                         // 20
```

This is an illustrative snippet assuming `AtomicInteger` is imported, not a class with `main`.

When two threads both attempt CAS from `0` to two different values, **only one** can succeed on that same `0` state if no other operation returns the state to `0`. The losing thread must handle the `false` result — it must never assume the update took place.

### CAS and linearizability

Each `compareAndSet` can be viewed as taking effect at a single point between invocation and return; successful updates on **a single atomic variable** form a well-defined total order. However, **a sequence of multiple CAS/get/set calls**, or an atomic update combined with external I/O, does not automatically become a linearizable transaction.

CAS also does not guarantee fairness: a thread can lose repeatedly under high contention. A CAS-loop algorithm typically avoids monitor locks for small updates, yet still consumes CPU when retrying many times.

## 5. Java 17+ example: all three classes in a multithreaded program

Save as `AtomicBasicsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class AtomicBasicsDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicInteger processed = new AtomicInteger();
        AtomicLong total = new AtomicLong();
        AtomicBoolean claimed = new AtomicBoolean(false);

        Runnable work = () -> {
            for (int i = 0; i < 10_000; i++) {
                processed.incrementAndGet();
                total.addAndGet(2L);
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);

        first.start();
        second.start();
        first.join();
        second.join();

        boolean firstClaim = claimed.compareAndSet(false, true);
        boolean secondClaim = claimed.compareAndSet(false, true);

        System.out.println("Processed: " + processed.get());
        System.out.println("Total: " + total.get());
        System.out.println("First claim: " + firstClaim);
        System.out.println("Second claim: " + secondClaim);
    }
}
```

Compile and run with JDK 17+:

```bash
javac AtomicBasicsDemo.java
java AtomicBasicsDemo
```

Exact stdout:

```text
Processed: 20000
Total: 40000
First claim: true
Second claim: false
```

Explanation:

1. Both workers hold references to the **same** `processed` and `total` instances.
2. `incrementAndGet` and `addAndGet` are independent atomic operations, so each worker completes 10,000 updates on each variable with no lost updates.
3. `Thread.join()` waits for **both** workers to finish before `main` prints. Therefore, the output does not depend on which worker runs faster.
4. The first `compareAndSet(false, true)` succeeds; the second fails because the flag is already `true`. These two CAS calls are invoked sequentially in `main` solely to demonstrate the return values.
5. **Do not** infer from this program that `processed` and `total` are updated as a single atomic pair. A reader running between the two updates inside a worker could observe them at different points.

If business logic requires "`total == 2 * processed` at all times" for concurrent readers, you need a different protocol to protect the **cross-variable invariant**, such as a lock or an immutable state object swapped atomically via `AtomicReference`.

## 6. `AtomicInteger`: counters, numeric states, and quotas

### Counting completed operations

`AtomicInteger` is well suited for:

- Number of completed tasks.
- Number of processed items, when each event is counted once.
- Tracking active waiters or in-flight requests with a clear increment/decrement protocol.
- Numeric states such as `NEW=0`, `RUNNING=1`, `DONE=2` when conditional atomic transitions are needed.

Note that the counter's meaning must be clearly defined: **tasks started, tasks succeeded, and tasks currently running are three different metrics**. An atomic counter accurately counts every increment call, but it cannot know on its own whether an increment faithfully represents the intended business event.

### Do not write check-then-act as two separate operations

Anti-pattern:

```java
if (inFlight.get() < limit) {
    inFlight.incrementAndGet();
}
```

If two threads both see a value just below `limit`, both may increment, causing the limit to be exceeded. `get` and `incrementAndGet` are safe **individually**; **the two-call sequence** is not atomic.

The solution is to wrap the check and modification in **a single logical CAS-loop operation**, or use `Semaphore` if the real goal is bounding permits and supporting waiting.

## 7. Java 17+ example: bounded increment with a CAS loop

Save as `BoundedAtomicCounterDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedAtomicCounterDemo {

    static final class BoundedCounter {
        private final int maximum;
        private final AtomicInteger value = new AtomicInteger();

        BoundedCounter(int maximum) {
            if (maximum < 0) {
                throw new IllegalArgumentException("negative maximum");
            }
            this.maximum = maximum;
        }

        boolean tryIncrement() {
            while (true) {
                int current = value.get();
                if (current >= maximum) {
                    return false;
                }
                if (value.compareAndSet(current, current + 1)) {
                    return true;
                }
                // Lost contention: re-read and re-check the bound.
            }
        }

        int get() {
            return value.get();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        BoundedCounter counter = new BoundedCounter(1_750);
        AtomicInteger successes = new AtomicInteger();
        Thread[] workers = new Thread[8];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int attempt = 0; attempt < 1_000; attempt++) {
                    if (counter.tryIncrement()) {
                        successes.incrementAndGet();
                    }
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Accepted: " + successes.get());
        System.out.println("Counter: " + counter.get());
    }
}
```

```bash
javac BoundedAtomicCounterDemo.java
java BoundedAtomicCounterDemo
```

Exact stdout:

```text
Accepted: 1750
Counter: 1750
```

Step-by-step analysis:

- Each worker attempts 1,000 increments; that is 8,000 attempts in total, while the counter allows at most 1,750.
- `current = value.get()` is only a point-in-time snapshot. Another thread may modify `value` immediately afterward.
- `compareAndSet(current, current + 1)` guarantees that only a thread that still observes **the exact `current`** can update it to `current + 1`.
- If CAS fails, the loop must **re-read** and re-check the bound. Never retry indefinitely using a stale `current` value.
- Once the value reaches 1,750, every new attempt returns `false`. Because this counter only increments and has no decrement operation, it can never move back to an earlier state.
- `successes` counts how many `tryIncrement` calls returned `true`; printing happens after `join()`, so the totals match exactly.

Limitation of this approach: it only manages **a single variable**; there is no waiting mechanism when capacity is full. If you need to acquire/release resource slots, manage fairness, timeouts, interruption, and waiting for permits, `Semaphore` is usually the clearer abstraction. A CAS loop can retry many times under heavy contention.

### Why doesn't `current + 1` overflow in this example?

The constructor only accepts `maximum >= 0`. CAS computes `current + 1` only when `current < maximum`; since `maximum` is an `int`, `current` can never exceed `Integer.MAX_VALUE - 1` on the update branch. Thus, this example cannot overflow at that step.

For unbounded counters, `AtomicInteger.incrementAndGet()` **does not check for overflow**; incrementing past `Integer.MAX_VALUE` wraps around to `Integer.MIN_VALUE` under Java integer arithmetic. If your system requires strict monotonicity or non-reusable IDs, you must enforce thresholds and lifecycle management explicitly.

## 8. `AtomicLong`: sequence numbers and large metrics

`AtomicLong` provides the same arithmetic operations as `AtomicInteger`, but stores a 64-bit `long`, which is useful when operation counts may exceed the `int` range.

Example of issuing sequence numbers:

```java
AtomicLong nextId = new AtomicLong(1_000L);
long first = nextId.getAndIncrement();   // 1000
long second = nextId.getAndIncrement();  // 1001
```

This is an illustrative snippet. `getAndIncrement` returns the old value; if you need the post-increment value, use `incrementAndGet`.

### Scope of ID uniqueness

An `AtomicLong` guarantees that every successful update on **that specific instance** has an atomic order. However, it does not by itself guarantee:

- uniqueness across **two different JVM processes**;
- persistence across restarts;
- uniqueness if the counter overflows or is reset;
- that records are committed in numeric ID order;
- that a request receiving a lower ID finishes its work earlier.

This is the difference between an **in-process atomic sequence** and **distributed/durable identity**. Within a single JVM, provided it is not reset and does not overflow, `getAndIncrement` can issue monotonically increasing numbers to concurrent callers. It is not, however, a complete solution for all ID requirements in a distributed system.

### Java 17+ example verifying unique IDs

Save as `AtomicSequenceDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicLong;

public class AtomicSequenceDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicLong nextId = new AtomicLong(1_000);
        long[] issued = new long[400];
        Thread[] workers = new Thread[4];

        for (int worker = 0; worker < workers.length; worker++) {
            final int index = worker;
            workers[worker] = new Thread(() -> {
                int offset = index * 100;
                for (int j = 0; j < 100; j++) {
                    issued[offset + j] = nextId.getAndIncrement();
                }
            });
            workers[worker].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        Arrays.sort(issued);
        boolean contiguous = true;
        for (int i = 0; i < issued.length; i++) {
            if (issued[i] != 1_000L + i) {
                contiguous = false;
                break;
            }
        }

        System.out.println("Issued: " + issued.length);
        System.out.println("Range: " + issued[0] + ".."
                + issued[issued.length - 1]);
        System.out.println("Contiguous: " + contiguous);
    }
}
```

```bash
javac AtomicSequenceDemo.java
java AtomicSequenceDemo
```

Exact stdout:

```text
Issued: 400
Range: 1000..1399
Contiguous: true
```

Each worker writes to **a disjoint index slice** of the array, so no two writers contend on the same element. `join` publishes the workers' writes to `main` before sorting and reading. The issued values may be distributed across workers in non-deterministic order, but the overall set of values is 1000 through 1399 with no duplicates. Sorting before printing makes the output deterministic.

## 9. `AtomicBoolean`: single flags and state-transition ownership

`AtomicBoolean` is suitable for managing a binary state that multiple threads may read or flip:

- A flag requesting work to stop.
- A flag indicating something has started or been signaled once.
- A "let only one caller claim ownership" flag.
- A feature on/off toggle when semantics require no additional states.

The difference between `set(true)` and `compareAndSet(false, true)` is crucial:

```java
AtomicBoolean started = new AtomicBoolean(false);

started.set(true); // Writes true; every caller can invoke this and succeed.

boolean winner = started.compareAndSet(false, true);
// Returns true only for the caller that wins the false -> true transition.
```

A `true` flag may mean "someone claimed the right," not "the work succeeded." If you need to distinguish `NEW`, `RUNNING`, `SUCCEEDED`, and `FAILED`, a boolean flag is usually **insufficient to represent the state**; use an appropriate state machine, future, or enum/state atomic.

### Java 17+ example: only one thread claims the right to start

Save as `AtomicBooleanOnceDemo.java`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicBooleanOnceDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicBoolean claimed = new AtomicBoolean(false);
        AtomicInteger winners = new AtomicInteger();
        Thread[] candidates = new Thread[6];

        for (int i = 0; i < candidates.length; i++) {
            candidates[i] = new Thread(() -> {
                if (claimed.compareAndSet(false, true)) {
                    winners.incrementAndGet();
                }
            });
            candidates[i].start();
        }

        for (Thread candidate : candidates) {
            candidate.join();
        }

        System.out.println("Winners: " + winners.get());
        System.out.println("Claimed: " + claimed.get());
    }
}
```

```bash
javac AtomicBooleanOnceDemo.java
java AtomicBooleanOnceDemo
```

Exact stdout:

```text
Winners: 1
Claimed: true
```

Regardless of how the six threads are scheduled, only one CAS from `false` to `true` can succeed when no thread resets the flag. Because only the winner increments the counter once and `main` waits for all threads, the result is deterministic.

**Do not blindly reuse this pattern to guarantee an exactly-once side effect.** For example, suppose the winner sets `claimed = true` and then calls an external service. If the service fails, the flag remains `true`, and other callers will not retry. To achieve "completed successfully exactly once," you need an **error-handling protocol**, idempotency/retry, and a state that represents completion — not just a claim flag.

## 10. Stop flags and the difference between visibility and wake-up

A common pattern:

```java
final class StopSignal {
    private final java.util.concurrent.atomic.AtomicBoolean
            stopped = new java.util.concurrent.atomic.AtomicBoolean();

    void requestStop() {
        stopped.set(true);
    }

    boolean shouldStop() {
        return stopped.get();
    }
}
```

This illustrative class uses `AtomicBoolean` to publish a flag. When a worker actively polls `shouldStop()`, it can observe updates thanks to the volatile semantics of `get()/set()`.

**However, a flag does not wake up a blocked thread.** If the worker is blocked in `BlockingQueue.take()`, `Thread.sleep(...)`, `CountDownLatch.await()`, or I/O, calling `stopped.set(true)` alone will not make the thread exit that call. Depending on the API, you also need interruption, timeouts, a sentinel/poison pill, a close signal, or resource closing.

Avoid running a `while (!stopped.get()) { }` tight spin loop on the CPU just to wait for an event. A spin loop may fit extremely short waits in specialized algorithms, but for typical application tasks you should use blocking coordination with a cancellation policy.

### A stop flag does not replace `Thread.interrupt()`

`AtomicBoolean` and interruption serve two different roles:

- A flag carries an **application-level state request** defined by the programmer.
- `Thread.interrupt()` carries an **interruption request** under the thread/blocking-API contract. It does not forcibly kill a thread; some operations throw `InterruptedException`, some respond differently, and some do not support interruption as expected.

If you catch `InterruptedException` and cannot handle it locally, the standard practice is to exit the task and/or restore the interrupt flag with `Thread.currentThread().interrupt()`. Never swallow the exception and keep waiting indefinitely.

## 11. `getAndSet`: retrieving the old value, resetting, or claiming

`getAndSet` performs an atomic exchange:

```java
AtomicInteger intervalCount = new AtomicInteger(17);

int previous = intervalCount.getAndSet(0); // 17
int current = intervalCount.get();         // 0
```

This is an illustrative snippet. When multiple writers continue updating during a reset, `getAndSet(0)` provides an atomic exchange point. However, if you need to sum across **multiple counters** at once, calling `getAndSet` on different variables **does not produce a global snapshot**.

With `AtomicBoolean`:

```java
AtomicBoolean pending = new AtomicBoolean(true);
boolean wasPending = pending.getAndSet(false);
```

The caller receives `true` if the flag was `true` at the moment of exchange. Other threads may flip the flag afterward. If business logic requires that only a thread observing `false` may set it to `true`, `compareAndSet(false, true)` expresses that condition more clearly than `getAndSet(true)`.

## 12. Functional update methods: `updateAndGet` and `accumulateAndGet`

Some updates are not simple `+ 1` increments. The API supports function-based updates:

```java
AtomicInteger level = new AtomicInteger(8);

int updated = level.updateAndGet(current ->
        Math.min(10, current + 1)); // 9

int previous = level.getAndAccumulate(4,
        (current, delta) -> Math.min(10, current + delta)); // 9

int now = level.get(); // 10
```

This is an illustrative snippet assuming `AtomicInteger` is imported.

**Critical rule:** the function passed to `updateAndGet`, `getAndUpdate`, `accumulateAndGet`, or `getAndAccumulate` **may be invoked multiple times** if CAS fails under contention. Therefore, the function should be **side-effect-free**, deterministic for its inputs, fast, and non-blocking.

Wrong:

```java
counter.updateAndGet(old -> {
    sendEmail();  // Side effect may occur multiple times on retry!
    return old + 1;
});
```

This is an illustrative anti-pattern; `sendEmail()` is hypothetical. Any callback that sends an email, writes to a file, increments an external counter, or makes a network call must not be placed inside an update function if retries can occur. Separate side effects into a dedicated step after the update succeeds, while considering idempotency, ordering, and error handling.

The function should also avoid reading or mutating the atomic variable itself in ways that complicate retries; simply return the new value based on the current argument and controlled conditions.

## 13. Java 17+ example: pure update function and bounded value

Save as `AtomicUpdateDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class AtomicUpdateDemo {
    public static void main(String[] args) {
        AtomicInteger level = new AtomicInteger(8);

        int updated = level.updateAndGet(
                current -> Math.min(10, current + 1));

        int previous = level.getAndAccumulate(4,
                (current, delta) -> Math.min(10, current + delta));

        AtomicLong bytes = new AtomicLong(100);
        long after = bytes.addAndGet(25L);

        System.out.println("Updated level: " + updated);
        System.out.println("Previous level: " + previous);
        System.out.println("Current level: " + level.get());
        System.out.println("Bytes: " + after);
    }
}
```

```bash
javac AtomicUpdateDemo.java
java AtomicUpdateDemo
```

Exact stdout:

```text
Updated level: 9
Previous level: 9
Current level: 10
Bytes: 125
```

Each lambda only computes a value from its arguments without producing side effects. Thus, if the JDK retries the function due to CAS failure, it will not duplicate an external action.

Limitation: `Math.min(10, current + 1)` **is not a general overflow-handling solution** when `current` can be near `Integer.MAX_VALUE`. In this example, the managed values stay in a small range (8 to 10), so it is safe. For arbitrary inputs, check bounds before adding or use appropriate overflow-safe arithmetic.

## 14. Memory semantics: what do atomics provide under the JMM?

`AtomicInteger`, `AtomicLong`, and `AtomicBoolean` provide more than just arithmetic and CAS. Operations like `get()` and `set()` have memory semantics equivalent to **volatile** reads and writes of the underlying value; updates such as `compareAndSet`, `getAndSet`, and atomic arithmetic carry guarantees corresponding to volatile read-modify-write operations.

Understanding a simple publication pattern:

```java
int payload; // Ordinary data, e.g. inside a holder.
AtomicBoolean ready = new AtomicBoolean(false);

// Writer:
payload = 42;
ready.set(true);

// Reader:
if (ready.get()) {
    use(payload); // Reads payload published according to the protocol.
}
```

This is an illustrative logic snippet, where `payload` and `ready` are shared state and `use` is a hypothetical method. If **the writer only writes `payload` before `ready.set(true)`**, the reader only reads `payload` **after `ready.get()` has observed `true`** from that publication, and no other writer modifies `payload` concurrently, then the happens-before relationship from the volatile write/read guarantees the reader sees the expected `payload`.

This comes from transitivity:

```text
writer: write payload = 42
                  |
                  v
           ready.set(true)       volatile write
                  |
             synchronizes-with
                  |
                  v
reader:     ready.get() == true  volatile read
                  |
                  v
             read payload
```

Ordinary data does not automatically become safe simply because an atomic variable is nearby. If there are **multiple publication rounds**, if readers retain mutable references for a long time, or if other writers modify `payload`, you must define a stricter protocol. When multiple fields must be observed together consistently, consider an immutable snapshot published via `AtomicReference` or a lock.

### `lazySet` and advanced access modes

`lazySet` has release semantics; it can be useful in one-way publication protocols, but **it does not promise that any reader will observe the state within a specific timeframe**. Java 9+ also offers plain, opaque, acquire, release, and compare-and-exchange variants. These are intended for advanced concurrency programming.

Do not choose a weaker access mode just because you think it is "faster" without a thorough JMM analysis. For typical application code, `get()`, `set()`, and `compareAndSet()` are clearer and far less error-prone. `AtomicBoolean` is not a waiting or wake-up primitive; `get()` observes the current value rather than waiting for an event to occur.

## 15. Overflow, value ranges, and data types

### `AtomicInteger` and `AtomicLong` do not report overflow

`AtomicInteger.incrementAndGet()` increments an `int`; past `Integer.MAX_VALUE`, the result wraps around according to 32-bit Java integer arithmetic. `AtomicLong` has the same behavior past `Long.MAX_VALUE`.

If an ID or version **must never wrap around**, you must manage overflow:

- Check the bound before incrementing inside a conditional atomic update.
- Use `long` when the `int` range is insufficient, while still defining lifecycle and thresholds.
- Do not use a JVM-local counter as a globally unique ID across multiple JVM instances or restarts.
- If overflow-safe addition is required, use appropriate checks (such as `Math.addExact` in an explicit update protocol) and define how exceptions are handled.

### An ordinary `long` and an `AtomicLong` are not the same

An ordinary `long` field does not make `value++` atomic; furthermore, the JMM distinguishes guarantees for non-volatile `long`/`double` at the 64-bit read/write level. In practice, on many modern JVMs, certain 64-bit operations do not tear, but **you must never rely on implementation details instead of the Java specification contract**. `AtomicLong` provides atomic operations and clear memory semantics portable across JMM-compliant platforms.

**A larger type does not mean lower contention.** Choose `AtomicLong` for its value range, not under the assumption that it is faster than `AtomicInteger`.

## 16. The ABA problem: CAS succeeding does not mean the state never changed

CAS only compares the current value with the expected value. Suppose:

```text
Thread A reads state = A
Thread B changes A -> B -> A
Thread A compareAndSet(A, C) succeeds
```

At the time of A's CAS, the value is indeed `A`, so the CAS succeeds. Yet A may **mistakenly assume nothing changed** while it was computing. This is the **ABA problem**.

For a monotonically increasing counter that is never reset and does not overflow, ABA is rarely a concern. However, for states that can return to a previous value — such as a `false`/`true`/`false` flag, reused IDs, or lock-free data structure algorithms — ABA can break business assumptions.

Ways to mitigate the risk depending on the problem:

- Use a **version/generation** counter that increments on every significant change.
- For object references, consider `AtomicStampedReference` if you need to compare both reference and stamp.
- Bundle state and version into an immutable object and update it via `AtomicReference` with CAS on the reference.
- Use a monitor/lock if multi-field atomicity or lifecycle complexity outweighs the benefits of CAS.

**An `AtomicBoolean` has no memory of history.** If a flag goes from `false` to `true` and back to `false`, a CAS expecting `false` can still succeed — `compareAndSet` makes no guarantee that "the flag has never changed."

## 17. Single-variable thread safety vs. multi-variable invariants

Suppose you must maintain `available + reserved == capacity`. Even if both `available` and `reserved` are `AtomicInteger`, the sequence:

```java
available.decrementAndGet();
reserved.incrementAndGet();
```

still consists of **two separate atomic operations**. A reader executing between the two steps can observe a temporary sum different from `capacity`. If the invariant must hold at all times for concurrent readers, you need a transaction-boundary solution:

- Hold **a shared monitor or lock** around both updates and all related observation points.
- Bundle the fields into **an immutable state** and swap the entire reference via a properly designed CAS.
- Confine the mutable state to **a single owner** and communicate via queues/messages.
- If observation is only required after all workers finish, use a proper completion primitive and read the results at that point.

Similarly, an `AtomicBoolean initialized` paired with a mutable `List` requires a safe publication protocol. A `true` flag does not make subsequent concurrent modifications to the list safe.

Never conclude **"the class is thread-safe" just because every field has an `Atomic` prefix**. Thread safety depends on invariants, aliasing, callbacks, collection contents, external resources, and how callers compose operations.

## 18. `AtomicBoolean` and state machines: "claimed" vs. "completed"

A service may want only one thread to perform a task while others wait or skip. An `AtomicBoolean busy` flag supports claiming:

```java
if (busy.compareAndSet(false, true)) {
    try {
        doWork();
    } finally {
        busy.set(false);
    }
}
```

This is an **illustrative pattern**; `busy` and `doWork` are hypothetical. Several risks apply:

- Resetting the flag to `false` allows another thread to run later, so this is **exclusive-in-progress**, not once-ever.
- If `doWork` throws an exception and `finally` resets the flag to `false`, it may have left **partial side effects**; retries require an explicit policy.
- Threads that fail to claim simply skip the work; if waiting is needed, use `Semaphore`, `Lock`, a queue, or an appropriate future.
- If other callers should receive **the same result** of a single computation, `CompletableFuture<T>` or a safely published future usually models completion better than a flag.
- If `doWork` hangs in I/O, the flag does not provide timeouts or cancellation.

If you have states `NEW`, `RUNNING`, `SUCCEEDED`, and `FAILED`, use an explicit state machine and define valid transitions. `AtomicInteger` can hold an enum ordinal or status code, though you must manage mapping and results; using an enum via `AtomicReference<State>` is often easier to read when multiple states are involved.

## 19. `AtomicLong` vs. `LongAdder`: when to prioritize throughput?

An `AtomicLong` manages **a single value**; many threads updating one variable can create contention at that single memory location. `LongAdder` distributes updates internally across cells to improve throughput in certain high-contention workloads.

| Criterion | `AtomicLong` | `LongAdder` |
| --- | --- | --- |
| Reading a value in one operation | `get()` performs an atomic read | `sum()` aggregates multiple internal cells |
| Incrementing by 1 | `incrementAndGet()` or `getAndIncrement()` | `increment()` |
| Need the new value immediately upon incrementing | Yes, via `incrementAndGet()` | No equivalent atomic total-on-increment semantics |
| Snapshot while writers are updating | `get()` is an atomic read | `sum()` is not a global atomic snapshot |
| High contention, statistics only | May become a contention hotspot | Often worth benchmarking as an alternative |

If you are counting "total requests ever processed" purely to display approximate statistics under continuous updates, `LongAdder` can be a good fit. If you need CAS to enforce quotas, issue IDs, or perform conditional state transitions, **`AtomicLong`** expresses the contract accurately.

Never switch from `AtomicLong` to `LongAdder` based solely on a benchmark while ignoring differences in **read semantics**.

## 20. CAS loops: retries, starvation, and side effects

Common pattern:

```java
while (true) {
    int oldValue = atomic.get();
    int newValue = transform(oldValue); // Function should be pure.
    if (atomic.compareAndSet(oldValue, newValue)) {
        break;
    }
}
```

This is an illustrative pattern; `atomic` and `transform` are undeclared. CAS fails when the state has changed from the expected value, so we retry based on the fresh value.

Consequences:

- `transform` may execute multiple times, so **do not place I/O, callbacks, or external side effects** inside the new-value computation.
- A thread can lose repeatedly, especially under very high contention; there is **no automatic fairness**.
- Retrying consumes CPU; benchmark before assuming a CAS loop is faster than `synchronized` in your real workload.
- For multi-field data, combining state into an atomic reference or using a lock can be simpler and easier to review.
- A CAS failure is not an exception: the caller must inspect the `false` return value and apply an appropriate policy (retry, give up, or report an error).
- If the algorithm is susceptible to ABA, add a version or design away invalid returns to old states.

Strong `compareAndSet` does not have "spurious failure" semantics like some `weakCompareAndSet...` variants. Weak CAS variants and weaker memory access modes belong to advanced algorithms and should not be substituted into ordinary code without proving correctness.

## 21. Do you still need `synchronized` when using Atomics?

**Possibly yes.** Atomic variables eliminate the need for locks on **certain single-variable operations**, but they do not forbid locks when business logic requires them.

Choose the tool based on the invariant:

| Problem | Typically suitable tool |
| --- | --- |
| One counter incremented/decremented independently by many writers | `AtomicInteger` or `AtomicLong` |
| A single flag used to claim ownership | `AtomicBoolean.compareAndSet` |
| Bounding a monotonically increasing counter to a max | CAS loop on `AtomicInteger` |
| Limiting concurrent tasks holding permits with waiting/cancellation | `Semaphore` or bounded queue |
| Consistent snapshot of two fields changing together | `synchronized`/`Lock` or an immutable state atomic reference |
| Coordinating completion between workers and caller | `Future`, `CountDownLatch`, `Thread.join()` |
| Map with many concurrent entries | `ConcurrentHashMap` with per-key atomic operations, not one atomic field for the whole map |
| High-contention statistical counter | Consider `LongAdder` and the semantics of `sum()` |

`synchronized` also provides a **critical section**: a thread holds a monitor while checking and updating a multi-step invariant. An `AtomicInteger` only protects that specific atomic field; it does not lock operations on collections or other fields.

It is usually best to **simplify ownership and state** before trying to replace every lock with complex CAS logic.

## 22. Common mistakes with the three Atomic classes

1. **"`volatile count++` is already atomic."** False; you must use an atomic operation or a lock.
2. **"With `AtomicInteger`, calling `get` then `set` is atomic."** False; there is an interleaving window between the two calls.
3. **"`compareAndSet` returning false means a JVM bug."** False; another thread updated the value or `expected` did not match.
4. **"Atomics make a class thread-safe."** False if the class still has multi-field invariants, mutable collections, or unprotected callbacks.
5. **"`AtomicBoolean` being true means the work succeeded."** Only true if your protocol explicitly defines and publishes completion that way; a CAS claim is a different step from completion.
6. **"A stop flag wakes up blocked threads."** False; you need appropriate signaling, interruption, timeout, or resource closing.
7. **"`AtomicLong` generates globally unique IDs across a distributed system."** False; instance/JVM-level atomicity does not provide distributed uniqueness or durability.
8. **"Atomic counters cannot overflow."** False; `int`/`long` arithmetic wraps around when exceeding its range.
9. **"The lambda in `updateAndGet` runs only once."** False; it can be re-invoked on CAS retries.
10. **"CAS succeeding proves the value never changed."** False under ABA when state returns to the expected value.
11. **"`lazySet` is identical to `set` in every way."** No; access mode and ordering differ—read the contract carefully.
12. **"Reading two Atomics back-to-back yields a consistent snapshot."** False; writers can still advance between the two reads.
13. **"Atomic operations guarantee fair progress for all threads."** No; scheduling and retries can still cause starvation.
14. **"No need to check the return value of `compareAndSet`."** False; if you ignore `false`, the intended update may not have happened.
15. **"`getAndIncrement` returns the post-increment value."** False; it returns the old value. Use `incrementAndGet` for the new value.

## 23. Design and code review checklist

Before choosing one of the three atomic classes, answer these questions:

1. **Is the state truly a single independent value?** If an invariant spans multiple fields, do not assume a single atomic is enough.
2. **Who reads and who writes?** How many writers and readers exist, and is the atomic instance properly shared?
3. **Which operation must be atomic?** A single increment, check-and-update, exchange, or multi-step transaction?
4. **Which API returns the old value vs. the new value?** Do not confuse `getAnd...` with `...AndGet`.
5. **How is memory publication established?** Is there a clear happens-before path from writer to reader?
6. **Can it overflow or reset?** If the value serves as an ID or version, define bounds and policies.
7. **Is ABA possible?** Can state return to `expected` before CAS, and does the logic care about history?
8. **Does the update function have side effects?** Any lambda passed to `updateAndGet`/`accumulateAndGet` should tolerate retries.
9. **Is a stop flag enough to wake workers?** If workers block, add an explicit interrupt/timeout/close protocol.
10. **Do you need concurrency limiting via permits or queues?** If so, consider `Semaphore`/`BlockingQueue` instead of a hand-rolled counter.
11. **Is performance worth measuring?** Benchmark real contention; do not trade clear, correct code for speculative optimizations.
12. **How are completion and failure communicated?** A claim flag does not replace a future or an explicit state machine.

## 24. Self-check questions

**1. Why does `AtomicInteger` handle lost updates better than `volatile int` with `count++`?**

`AtomicInteger.incrementAndGet` is an atomic read-modify-write operation. `volatile count++` only guarantees volatile semantics for the separate read and write, without combining them into one atomic operation.

**2. Two threads call `AtomicBoolean.compareAndSet(false, true)`. Can both return `true` if the flag starts as `false` and no one resets it?**

No. Once the first CAS succeeds, the state becomes `true`; the remaining CAS expecting `false` will fail. Only if some thread resets `true` back to `false` could a subsequent CAS succeed again.

**3. Does calling `AtomicLong.getAndIncrement()` from 100 threads guarantee unique IDs across multiple JVMs?**

No. It guarantees atomic operations on **that single instance**; it does not coordinate across multiple processes, restarts, or overflow.

**4. Does `getAndSet(0)` create an atomic snapshot across multiple `AtomicInteger` instances?**

No. Each exchange is atomic only on its own variable; there is no global transaction across variables.

**5. For "increment only while below max," why isn't checking `get() < max` followed by `incrementAndGet()` sufficient?**

Because another thread can increment between the two calls. Use a CAS loop or another operation that encompasses both the check and the update.

**6. Should you send an email inside an `updateAndGet` lambda?**

No. The lambda may be re-executed under CAS contention, causing the email to be sent multiple times even though only one update ultimately succeeds.

**7. Can `AtomicBoolean stopped` replace thread interruption?**

No. A flag does not wake up a blocked worker; interruption has a different contract, and certain blocking operations respond by throwing `InterruptedException`.

**8. Can CAS miss the fact that state changed A → B → A?**

Yes. This is the ABA problem: CAS only compares the current value with `expected` and does not record history. If history matters, use a version/stamp or an appropriate protocol.

**9. When might `LongAdder` be better than `AtomicLong`?**

When the workload is primarily high-contention statistical counting across many writers, and you can accept that `sum()` during concurrent updates is not an atomic snapshot. If you need CAS or exact bounds per operation, use `AtomicLong`.

**10. Does a class with two `AtomicInteger` fields automatically guarantee their sum is always N?**

No. Operations on two atomic variables are independent. For readers to observe a cross-variable invariant, you need a transaction under a lock or a state swapped as a single unit.

## 25. Summary

- **`AtomicInteger`**: `int`-typed counter or state with atomic reads, writes, arithmetic, and CAS.
- **`AtomicLong`**: same model for `long`, suited for counters and sequences within a defined ownership scope; does not guarantee global uniqueness, durability, or overflow prevention.
- **`AtomicBoolean`**: binary flags and state transitions via CAS; claiming ownership does not mean the work is complete.
- **`compareAndSet`**: atomic check-and-update; handle failures, bound retries carefully, and understand ABA when values can recur.
- **Memory semantics** of atomic operations help build JMM-compliant publication; however, they do not automatically protect mutable objects, multiple fields, or surrounding workflows.
- **Never place side effects inside retryable update functions**; do not use a bare flag as a substitute for blocking coordination or complex lifecycles.
- **Atomics do not replace all locks**: when multi-variable invariants, waiting, transactions, or complex callbacks are involved, `synchronized`, `Lock`, `Semaphore`, or a single-owner model may be much easier to prove correct.

The most effective way to apply these classes is to start with the question: **"What is the smallest logical operation that must be atomic?"**. If you only need to update a single `int`, `long`, or `boolean`, these three atomic classes are concise and powerful tools. If correctness spans multiple variables or multiple stages, design synchronization at the **business-protocol level** rather than expecting a single atomic variable to solve all concurrency concerns.
