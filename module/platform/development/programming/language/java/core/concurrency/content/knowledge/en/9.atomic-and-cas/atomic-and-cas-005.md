# getAndUpdate(), updateAndGet(), and accumulator in Java Atomic & CAS

## Learning Objectives

When multiple threads concurrently modify a counter, a threshold limit, a maximum value, or a state snapshot, the usual read–compute–write pattern easily causes **lost updates**. The `java.util.concurrent.atomic` API family supports function-based updates without having to manually write a `compareAndSet` loop in every case. However, similar-looking names can cause confusion between **the value before the update** and **the value after the update**; moreover, the term **accumulator** refers both to accumulation methods on atomic values and to classes such as `LongAccumulator` and `DoubleAccumulator` with different performance goals.

This lesson helps you:
- Use `getAndUpdate()` and `updateAndGet()` properly with `UnaryOperator`, `IntUnaryOperator`, and `LongUnaryOperator`.
- Distinguish `getAndAccumulate(x, fn)` and `accumulateAndGet(x, fn)` with `BinaryOperator`; clearly understand the order of the two arguments.
- Explain atomic updates using **CAS**, when an update takes effect, and why callbacks may be recomputed multiple times.
- Avoid side effects in callbacks, miscounting successes, overflow, reusing mutable objects, and wrongly assuming atomicity across multiple variables.
- Choose between `AtomicInteger/AtomicLong/AtomicReference` and `LongAdder/LongAccumulator/DoubleAccumulator` depending on whether you need **strictly exact values for decision-making** or **high-throughput statistics**.
- Run **Java 17+** examples yourself demonstrating unary updates, binary accumulation, contended inventory handling, immutable snapshots, and statistical accumulators.

**Scope:** Java SE, the Java Memory Model, and concurrency in general; Spring-specific APIs or configurations are not covered as they have a dedicated chapter.

## 1. Why does read–modify–write often suffer from race conditions?

Suppose two threads concurrently increment a variable:

~~~java
int value = sharedCount;
sharedCount = value + 1;
~~~

Even if `sharedCount` is `volatile`, the **read → compute → write** sequence still consists of multiple steps. An execution schedule might look like:

~~~text
Initially sharedCount = 0

Thread A                Thread B
--------                --------
read 0
                        read 0
compute 1
                        compute 1
write 1
                        write 1

Two increments occurred, yet the final result may only be 1.
~~~

**Volatile** provides visibility and ordering guarantees for each corresponding read/write operation; it **does not turn** the two lines above into a single transaction. If you only need to increment by one, `AtomicInteger.incrementAndGet()` or `getAndIncrement()` already has the appropriate semantics. However, for more complex transformations such as "decrement only if positive", "cap at a maximum limit", or "merge a snapshot using a formula", function-based update methods are very useful.

An atomic change needs a **clear unit of state**:
- `AtomicInteger` updates **one `int`**.
- `AtomicLong` updates **one `long`**.
- `AtomicReference<V>` updates **one reference `V`**; if `V` is an immutable record containing multiple fields, a single reference swap can publish **a consistent snapshot**.
- `LongAccumulator`/`DoubleAccumulator` are accumulators that can **stripe updates internally to reduce contention**, so their read/reset semantics differ from a single atomic value.

## 2. Four core methods: unary and accumulator

| Method | What does the function receive? | Logical transformation | Return value |
| --- | --- | --- | --- |
| `getAndUpdate(fn)` | Current value | `new = fn(current)` | **Old value**, before the successful update |
| `updateAndGet(fn)` | Current value | `new = fn(current)` | **New value**, after the successful update |
| `getAndAccumulate(x, fn)` | Current value and `x` | `new = fn(current, x)` | **Old value** |
| `accumulateAndGet(x, fn)` | Current value and `x` | `new = fn(current, x)` | **New value** |

In this table, "old" and "new" refer to the values associated with **the specific atomic operation being executed**. If another thread updates it immediately afterward, a subsequent `get()` call may return a different value; do not assume the value returned by `updateAndGet` necessarily remains the current value by the time the caller uses it.

### 2.1. Unary update

With `AtomicInteger`, the method accepts an `IntUnaryOperator`:

~~~java
int previous = counter.getAndUpdate(current -> current * 2);
int updated = counter.updateAndGet(current -> current + 3);
~~~

`current` is passed into the function by the library on each update attempt, and is **not** necessarily the same as a `counter.get()` call the caller performed earlier. Similarly, `AtomicLong` accepts a `LongUnaryOperator`; `AtomicReference<V>` accepts a `UnaryOperator<V>`.

The **getAnd...** prefix reminds you that the method returns the value **before** the modification. The **...AndGet** suffix reminds you that the method returns the value **after** the modification.

### 2.2. Binary accumulation

With `AtomicInteger`:

~~~java
int previous = counter.getAndAccumulate(5, (current, x) -> current + x);
int updated = counter.accumulateAndGet(7, Math::max);
~~~

Unlike unary updates, the function takes **two** arguments: **the current value first**, and **the value passed to the method second**. For `AtomicLong` this is `LongBinaryOperator`; for `AtomicReference<V>` it is `BinaryOperator<V>`.

Do not confuse them:

~~~java
// Correct when the business logic is current - delta:
counter.accumulateAndGet(4, (current, delta) -> current - delta);

// Conversely, this means delta - current:
counter.accumulateAndGet(4, (current, delta) -> delta - current);
~~~

For commutative operations like addition, swapping arguments often goes unnoticed; for subtraction, division, string concatenation, or order-sensitive record combining, it completely changes the meaning.

### 2.3. Atomic does not mean every callback runs only once

Update methods may have to retry when CAS fails because another thread just changed the value. Therefore, the API documentation requires the update function to be **side-effect-free**. A single method call produces one atomic update result, but the function you pass in **may be recomputed**.

~~~text
Thread A                         Thread B
--------                         --------
read state = 10
compute fn(10) -> 11
                                 change state: 10 -> 20 (CAS succeeds)
CAS(10,11) fails
re-read state = 20
compute fn(20) -> 21
CAS(20,21) succeeds

Final state: 21.
A's fn ran twice even though only one update from A succeeded.
~~~

This is a **possible** execution schedule, not a guarantee that every JVM must invoke the function twice. Typically the library loops until an update succeeds; there is no guaranteed maximum number of retries under contention.

## 3. Java 17 Example: getAndUpdate vs. updateAndGet

Create the file **`UnaryUpdateDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class UnaryUpdateDemo {
    public static void main(String[] args) {
        AtomicInteger value = new AtomicInteger(10);

        int before = value.getAndUpdate(current -> current * 2);
        System.out.printf(
                "getAndUpdate returned=%d current=%d%n",
                before, value.get());

        int after = value.updateAndGet(current -> current + 3);
        System.out.printf(
                "updateAndGet returned=%d current=%d%n",
                after, value.get());
    }
}
~~~

Run:

~~~bash
javac UnaryUpdateDemo.java
java UnaryUpdateDemo
~~~

Exact stdout when no other thread modifies `value`:

~~~text
getAndUpdate returned=10 current=20
updateAndGet returned=23 current=23
~~~

Interpretation:
1. Starting at `10`, `getAndUpdate(current -> current * 2)` changes the value to 20 but **returns 10**.
2. `updateAndGet(current -> current + 3)` changes the value from 20 to 23 and **returns 23**.
3. Both updates are atomic; because there is no contention in this example, the subsequent `get()` calls observe the corresponding values.
4. If a third thread updates the same `value` between the method call and `get()`, the `current` printed by the later `get()` may differ from the value returned by the method. **Atomicity applies only to each individual method**, not across the subsequent print statement.

### Practical use cases

- `getAndUpdate` fits when the caller needs the **previous value** to determine the effect of an action, such as claiming one unit of a resource if `previous > 0`.
- `updateAndGet` fits when the caller wants the **post-change snapshot**, such as computing an adjusted quota limit.
- If you only need to increment/add a fixed amount, `getAndIncrement`, `incrementAndGet`, `getAndAdd`, and `addAndGet` are usually shorter, clearer, and potentially more efficient than a general lambda.
- Do not use `set(get() + delta)` as a substitute: combining two separate methods still suffers from lost updates.

## 4. Java 17 Example: getAndAccumulate vs. accumulateAndGet

Create the file **`BinaryAccumulateDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class BinaryAccumulateDemo {
    public static void main(String[] args) {
        AtomicInteger number = new AtomicInteger(6);

        int before = number.getAndAccumulate(
                4, (current, multiplier) -> current * multiplier);

        System.out.printf(
                "getAndAccumulate returned=%d current=%d%n",
                before, number.get());

        int after = number.accumulateAndGet(5, Integer::sum);
        System.out.printf(
                "accumulateAndGet returned=%d current=%d%n",
                after, number.get());

        AtomicLong maximum = new AtomicLong(Long.MIN_VALUE);
        long oldMax = maximum.getAndAccumulate(-7L, Long::max);
        long newMax = maximum.accumulateAndGet(-2L, Long::max);

        System.out.printf(
                "maxBeforeIsIdentity=%b maxNow=%d returnedNew=%d%n",
                oldMax == Long.MIN_VALUE, maximum.get(), newMax);
    }
}
~~~

Compile and run:

~~~bash
javac BinaryAccumulateDemo.java
java BinaryAccumulateDemo
~~~

Stdout:

~~~text
getAndAccumulate returned=6 current=24
accumulateAndGet returned=29 current=29
maxBeforeIsIdentity=true maxNow=-2 returnedNew=-2
~~~

Explanation:
- `getAndAccumulate(4, multiply)` calls the function with `current=6` and `multiplier=4` to produce 24; the return value is **6**.
- `accumulateAndGet(5, Integer::sum)` updates `24 + 5 = 29` and returns **29**.
- For a **max** operation when negative values can occur, `Long.MIN_VALUE` is an appropriate initial value. Initializing max to 0 would yield the wrong result if all inputs are negative.
- `Long::max` is an accumulation function that does not depend on the execution schedule for each individual update, though the order in which concurrent updates succeed is still unpredictable to callers.

### Common lambda examples

~~~java
AtomicInteger bounded = new AtomicInteger(8);
bounded.updateAndGet(current -> Math.min(10, current + 5)); // becomes 10

AtomicLong highWater = new AtomicLong(Long.MIN_VALUE);
highWater.accumulateAndGet(42L, Long::max); // becomes 42

AtomicInteger remaining = new AtomicInteger(3);
int previous = remaining.getAndUpdate(
        current -> current > 0 ? current - 1 : current);
boolean claimed = previous > 0; // true when 1 unit was claimed.
~~~

The snippets above are **fragments**, assuming the corresponding classes are imported or fully qualified. They are not presented as standalone programs. In the bounded example `Math.min(10,current+5)`, if values near `Integer.MAX_VALUE` are possible, `current+5` risks overflowing; in that case, choose an overflow-safe expression or validate the range according to business rules.

## 5. The CAS mechanism under the API

For `AtomicInteger`, one way to **illustrate the semantics** of `updateAndGet` is:

~~~java
static int updateExample(
        java.util.concurrent.atomic.AtomicInteger atomic) {
    while (true) {
        int observed = atomic.get();
        int desired = observed + 1;

        if (atomic.compareAndSet(observed, desired)) {
            return desired;
        }
    }
}
~~~

This is an **illustrative method**, which can be placed inside a class containing the corresponding logic. It shows:
1. **Read** the observed value.
2. **Compute** the new value from that snapshot.
3. **CAS** writes only if the state still equals the expected value.
4. If it fails, **retry** with the new state.

`getAndUpdate` is semantically similar but returns the `observed` value from the successful CAS attempt. Actual implementations may have internal optimizations and are not required to be implemented line-for-line like this snippet.

### Linearization point

A successful update can be reasoned about as having occurred atomically at the moment the CAS succeeds. Two threads both calling `updateAndGet(x -> x + 1)` on the same `AtomicInteger` will not lose updates, even though the callbacks may be evaluated multiple times.

**However:** the method only protects the atomicity of **a single state location**; it does not automatically combine operations with a database, a log, or another atomic variable. If two fields `available` and `sold` are updated using **two** separate atomics, an observer can still see an intermediate state between the two CAS operations.

### Visibility and ordering

Strong update methods on atomic classes have documented memory effects, related to `VarHandle.compareAndSet`. You do not need to add `volatile` yourself to the value managed by an atomic class. However, when logical state includes fields outside the atomic object, you still must establish happens-before relationships and invariants for those fields. Do not assume a CAS on a counter automatically "locks" all application data.

## 6. Golden rule: callbacks must be side-effect-free

### 6.1. What not to do inside an update function

A dangerous usage:

~~~java
AtomicInteger remaining = new AtomicInteger(10);

// WRONG: side effects may run multiple times when CAS retries.
remaining.updateAndGet(current -> {
    chargeCustomer();        // External payment call.
    sendNotification();      // External notification call.
    return current - 1;
});
~~~

This is an **intentionally wrong example**, not a standalone runnable class; `chargeCustomer` and `sendNotification` are assumed to exist. Under contention, the callback may re-run, causing charges or notifications to happen multiple times even though only one atomic update completes.

Side effects to avoid inside an update function:
- Writing to files, writing to a database, making network calls, sending emails/payments.
- Mutating another object or incrementing a counter tracking "number of successes".
- Logging "completed successfully" inside the callback; it might log aborted CAS attempts too.
- Generating a non-reusable business ID or consuming a value from a queue.
- Depending on unsynchronized mutable data, making the callback non-deterministic across retries.

A good function can be written as a **pure function**:

~~~java
current -> current > 0 ? current - 1 : current
(current, delta) -> current + delta
(previous, sample) -> Math.max(previous, sample)
~~~

Even if the same function is called multiple times, it only computes a result from its inputs and does not alter the outside world. **There is no guarantee that the callback is invoked exactly once**.

### 6.2. Are side effects after the method returns completely safe?

Not automatically. If a thread claims a resource by decrementing an atomic counter, the return value of the method call can determine **whether the claim succeeded**; only then does the caller send the business request. But if sending that request fails, times out, or retries, you still need idempotency, compensation/refunds, or a separate transaction protocol.

An atomic update is an operation **inside JVM memory**. It does not automatically form a distributed transaction with a payment gateway, database, or other system. For an "exactly-once payment" event, you typically need an idempotency key or business state in the payment-processing system itself, rather than relying solely on a local atomic.

### 6.3. Exceptions in callbacks

If the update function throws an exception, **that call does not complete an update from the failing callback**. However, another thread can still update the atomic value in the meantime; do not infer from an exception that the overall shared state remains unchanged. Avoid update functions that perform partial side effects before throwing, because CAS does not roll back side effects that have already occurred.

For overflow control:

~~~java
AtomicInteger amount = new AtomicInteger(Integer.MAX_VALUE);
amount.updateAndGet(current -> Math.addExact(current, 1));
~~~

This is an illustrative snippet: `Math.addExact` throws `ArithmeticException` on `int` addition overflow instead of silently wrapping around. Standard additions on `AtomicInteger` use Java `int` arithmetic, which can overflow via two's complement wrap-around. If business logic requires non-negative numbers or strict bounds, enforce predicates and overflow handling inside the update function.

## 7. Java 17 Example: multiple workers claiming a finite quantity

Requirement: there are exactly 100 units of inventory. Eight workers each try to sell 50 times. **400 attempts** compete against each other, yet no more than 100 may be sold; remaining inventory must be non-negative.

Create the file **`AtomicStockDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicStockDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger remaining = new AtomicInteger(100);
        ExecutorService pool = Executors.newFixedThreadPool(8);

        try {
            List<Future<Integer>> futures = new ArrayList<>();

            for (int worker = 0; worker < 8; worker++) {
                futures.add(pool.submit(() -> {
                    int successes = 0;
                    for (int i = 0; i < 50; i++) {
                        int old = remaining.getAndUpdate(
                                current ->
                                        current > 0 ? current - 1 : current);
                        if (old > 0) {
                            successes++;
                        }
                    }
                    return successes;
                }));
            }

            int sold = 0;
            for (Future<Integer> future : futures) {
                sold += future.get();
            }

            int rest = remaining.get();
            System.out.printf(
                    "sold=%d remaining=%d invariant=%b%n",
                    sold, rest, sold + rest == 100 && rest >= 0);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac AtomicStockDemo.java
java AtomicStockDemo
~~~

Exact stdout when all eight tasks complete normally:

~~~text
sold=100 remaining=0 invariant=true
~~~

Why is this deterministic?
1. `getAndUpdate` performs an atomic update with the function `current > 0 ? current - 1 : current`.
2. If the value **before** the update is greater than 0, exactly one claim succeeds; if it is already 0, the remaining count stays unchanged and the claim fails.
3. Out of 400 total attempts—exceeding the 100 available—once all tasks finish there are 100 successes and 300 failures, regardless of which threads win.
4. `successes++` is **outside the callback**, only executed after the atomic method returns, so it does not double-count on CAS retries.
5. `Future.get()` waits for completion and surfaces exceptions; `sold` is summed on `main` after tasks finish rather than being a second atomic field updated concurrently.

**Limitation:** the `sold + remaining` snapshot is only computed after completion. If the system requires another thread to concurrently read **both fields** and always observe the invariant `sold + remaining == 100`, you must bundle both into **a single atomic state** (for example, an `AtomicReference` to an immutable record) or use a lock; two independent atomic variables do not form a multi-field snapshot.

## 8. AtomicReference + record: accumulator for a multi-field snapshot

`AtomicReference<T>` supports the same family of methods but operates on **a single reference**. When `T` is an immutable value object, you can update multiple fields consistently by **replacing the entire snapshot**, without mutating the old object.

Create the file **`ReferenceAccumulatorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ReferenceAccumulatorDemo {
    private record Stats(long count, long sum) {}

    public static void main(String[] args) throws Exception {
        AtomicReference<Stats> stats =
                new AtomicReference<>(new Stats(0, 0));

        Stats before = stats.getAndAccumulate(
                new Stats(1, 7),
                (current, delta) ->
                        new Stats(
                                current.count() + delta.count(),
                                current.sum() + delta.sum()));

        Stats after = stats.get();
        System.out.printf(
                "beforeCount=%d beforeSum=%d nowCount=%d nowSum=%d%n",
                before.count(), before.sum(),
                after.count(), after.sum());

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> tasks = new ArrayList<>();

            for (int i = 0; i < 5; i++) {
                tasks.add(pool.submit(() -> stats.updateAndGet(
                        current -> new Stats(
                                current.count() + 1,
                                current.sum() + 2))));
            }

            for (Future<?> task : tasks) {
                task.get();
            }

            Stats finalSnapshot = stats.get();
            System.out.printf(
                    "finalCount=%d finalSum=%d%n",
                    finalSnapshot.count(), finalSnapshot.sum());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac ReferenceAccumulatorDemo.java
java ReferenceAccumulatorDemo
~~~

Stdout:

~~~text
beforeCount=0 beforeSum=0 nowCount=1 nowSum=7
finalCount=6 finalSum=17
~~~

Explanation:
- `getAndAccumulate(new Stats(1,7), combine)` updates from `Stats(0,0)` to `Stats(1,7)` and **returns the old object**.
- Five tasks then use `updateAndGet` to create five new snapshots, each adding 1 to `count` and 2 to `sum`. The final result is `count=6`, `sum=7 + 5*2 = 17`.
- Both fields are `long`s in a record and never change after construction, so **a single `AtomicReference.get()`** returns a consistent version for reading both.
- The combine/update functions only allocate a new object and have no external side effects, so they can be safely recomputed under CAS contention.

A subtle bug to avoid:

~~~java
long count = stats.get().count();
long sum = stats.get().sum();  // May come from a different version.
~~~

If another thread updates between the two `get()` calls, the two variables are assembled from **two different snapshots**. To get a consistent snapshot, read **once**:

~~~java
Stats snapshot = stats.get();
long count = snapshot.count();
long sum = snapshot.sum();
~~~

These two snippets are fragments inside a class where `Stats` and `stats` are declared; they are not standalone programs.

### Limitations when using AtomicReference

- Atomicity applies to the **reference**. If the reference points to a mutable object that other code modifies directly, `AtomicReference` does not make those mutations atomic.
- A record containing a mutable `List<Person>` or array **is not automatically deep-immutable**; you need defensive copies or appropriate immutable structures.
- Callbacks for `getAndUpdate/updateAndGet/getAndAccumulate/accumulateAndGet` may be invoked repeatedly. Creating new value objects does not cause logic errors, but it incurs allocation/GC cost under contention.
- If two objects have equal contents but are two distinct references, CAS operations on `AtomicReference` work based on **expected reference identity**. Avoid reasoning about CAS using `equals()` instead of reference equality.
- Some complex CAS algorithms encounter the **ABA problem** (state transitions A→B→A so the observed value appears unchanged); if a version/generation is needed, you can embed a version in the immutable snapshot or look into `AtomicStampedReference`. Do not assume every reference update suffers from ABA.

## 9. Accumulator has two meanings: methods on Atomic* and the LongAccumulator class

This is the easiest place to get confused when reading the API.

**Group 1 — `getAndAccumulate/accumulateAndGet` methods:**
- Belong to `AtomicInteger`, `AtomicLong`, `AtomicReference`, and the corresponding atomic array/updater families.
- Update **a single value/state location** using a binary function.
- Return the value **before/after** the successful atomic update.
- Suitable even for strong check-and-update decisions, such as resource limits or a snapshot that must be computed accurately per update.

**Group 2 — `LongAccumulator`/`DoubleAccumulator` classes:**
- Designed for **statistics/aggregating values when many threads update concurrently**, able to stripe internal state across multiple cells to reduce contention.
- Call `accumulate(x)` to feed in a sample value; does not return an "old/new value" per call.
- Call `get()` to aggregate the current value across cells; **under concurrent updates, this is not an atomic snapshot**.
- `reset()` and `getThenReset()` are suitable when no writers are actively updating; if called concurrently with updates, the result may not represent an exact point-in-time boundary.
- The accumulation function should be **side-effect-free**, and for an order-independent result, should be **associative and commutative**.

### 9.1. LongAccumulator uses an identity

Initialization:

~~~java
LongAccumulator maximum =
        new LongAccumulator(Long::max, Long.MIN_VALUE);
~~~

The first parameter is a `LongBinaryOperator` combining the current accumulated value and the new sample; the second parameter is the **identity element**.

A valid identity must satisfy:

~~~text
combine(identity, x) == x
combine(x, identity) == x
~~~

For `max` over the entire `long` domain, `Long.MIN_VALUE` is the appropriate identity. For `sum`, the identity is 0; for product, the identity is 1, though overflow must be considered.

If you use `new LongAccumulator(Long::max, 0)` and all samples are negative, the result will be wrong because 0 is greater than every sample. **Identity is not an "arbitrary default value".**

### 9.2. Accumulation order is not guaranteed

With `LongAccumulator`, the JVM may distribute updates across multiple internal cells and combine them later. Therefore, operations like max, min, or integer sum (following Java's overflow rules, if applicable) work in any order. Subtraction, ordered text concatenation, or sequence-dependent functions are generally **unsuitable**. If a specific business order must be applied, use a sequential owner or an explicit ordering protocol.

**Floating-point:** `double` addition is not strictly associative in real arithmetic due to rounding and IEEE 754 semantics. With `DoubleAccumulator` or `DoubleAdder`, changing the combination order can introduce rounding differences; there is no guarantee of bit-for-bit identical results compared to sequential addition in a fixed order. For money, consider representing the smallest integer unit or `BigDecimal` with an appropriate synchronization protocol, rather than using `double` as an exact monetary amount.

## 10. Java 17 Example: LongAccumulator for multi-threaded metrics

Create the file **`LongAccumulatorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAccumulator;

public class LongAccumulatorDemo {
    public static void main(String[] args) throws Exception {
        LongAccumulator maximum = new LongAccumulator(
                Long::max, Long.MIN_VALUE);
        LongAccumulator sum = new LongAccumulator(Long::sum, 0L);

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> jobs = new ArrayList<>();

            for (int worker = 0; worker < 4; worker++) {
                final int start = worker * 25 + 1;
                jobs.add(pool.submit(() -> {
                    for (int number = start; number < start + 25; number++) {
                        maximum.accumulate(number);
                        sum.accumulate(number);
                    }
                }));
            }

            for (Future<?> job : jobs) {
                job.get();
            }

            System.out.printf(
                    "max=%d sum=%d%n", maximum.get(), sum.get());

            long previousMax = maximum.getThenReset();
            System.out.printf(
                    "beforeReset=%d identityRestored=%b%n",
                    previousMax, maximum.get() == Long.MIN_VALUE);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac LongAccumulatorDemo.java
java LongAccumulatorDemo
~~~

Exact stdout after all tasks complete normally:

~~~text
max=100 sum=5050
beforeReset=100 identityRestored=true
~~~

Why the result is deterministic:
- Four workers process the integer ranges `1..25`, `26..50`, `51..75`, and `76..100`. Every sample from 1 to 100 is fed in exactly once.
- `Long::max` and `Long::sum` are suitable order-independent aggregations for this dataset; `1+2+...+100 = 5050`.
- `Future.get()` confirms all jobs finished before `main` calls `get()`.
- `getThenReset()` is called **after there are no more concurrent updates**, so it observes max 100 and resets back to the identity `Long.MIN_VALUE`. If called while writers are still running, the API does not guarantee an exact update boundary.

**Do not use `LongAccumulator` to make a "sell only if stock remains" decision such as `if (accumulator.get() > 0) accumulator.accumulate(-1)`.** `get()` is not an atomic snapshot under concurrent updates, and the check-then-accumulate sequence is not atomic either. For resource quotas, use `AtomicInteger.getAndUpdate`, CAS, or a lock to protect **both the predicate and the mutation**.

## 11. Comparing AtomicLong, LongAdder, and LongAccumulator

| Criterion | `AtomicLong` | `LongAdder` | `LongAccumulator` |
| --- | --- | --- | --- |
| Logical value | One atomic `long` | Sum accumulated across multiple internal cells | Accumulation across multiple cells with a custom function |
| Key updates | `incrementAndGet`, `getAndUpdate`, `accumulateAndGet` | `add`, `increment`, `decrement` | `accumulate(x)` |
| Returns old/new per update? | **Yes** for the corresponding methods | **No** | **No** |
| Reading with contending writers | `get()` is an atomic read of one value | `sum()` is not an atomic snapshot | `get()` is not an atomic snapshot |
| Prevents lost updates for a read-modify-write? | **Yes** via update/CAS | Safely accumulates metrics, does not provide atomic check-then-act | Safely accumulates metrics, does not provide atomic check-then-act |
| Accumulation function | Unary/binary operator on a single state | Dedicated addition | Custom `LongBinaryOperator` |
| Best-fit scenarios | Exact counters, quotas, high-water marks needing return values | High-writer statistical counters | High-writer max/min/sum or associative/commutative metrics |
| Trade-offs | CAS contention on a single value | Multiple cells, memory overhead, aggregate reads | Multiple cells, memory overhead, requires valid identity/function |

Functionally, `LongAdder` corresponds to the addition case of `LongAccumulator` with identity 0. Under high contention, striped adders/accumulators often achieve better update throughput than a centralized atomic counter, at the cost of read/reset limitations and extra memory. **No single class is always fastest** for every workload; measure with an appropriate benchmark and check whether the workload actually requires a linearizable value.

### When multiple metrics need a shared snapshot

Suppose a system uses two `LongAdder`s for `requests` and `errors`. Later, when reading the "error rate" by calling `sum()` on each adder, the two reads may reflect **two different points in time**; it is not a unified transaction. For dashboards that tolerate approximation, that may be fine. For business decisions requiring exact multi-field consistency, use an immutable record in an `AtomicReference`, a lock, or another snapshot protocol.

## 12. Important pitfalls

### 12.1. Using getAndUpdate when the post-update value is needed

~~~java
int updated = counter.getAndUpdate(x -> x + 1);
~~~

The variable name `updated` is misleading: the method returns the **old** value. Use `updateAndGet` if you need the new number, or name it `previous` and handle it as the old value.

### 12.2. Assuming a callback "being called" means the update "succeeded"

~~~java
counter.updateAndGet(current -> {
    successCount++;
    return current + 1;
});
~~~

This is wrong if `successCount` is updated inside the callback: CAS can fail and invoke the function again. There is also a data race on `successCount++` if multiple threads modify it. Move success counting **after the method returns**, or model combined state in a single atomic snapshot if a strict invariant is needed.

### 12.3. Using two separate atomics for one invariant

~~~java
available.updateAndGet(x -> x - 1);
sold.updateAndGet(x -> x + 1);
~~~

Each method is individually atomic, but there is a gap between the two calls. An observer can temporarily see an inconsistent `available + sold`. To preserve a multi-field invariant, use a shared lock or an `AtomicReference` to an immutable record and update the whole snapshot in one operation.

### 12.4. Reversing accumulator arguments

~~~java
balance.accumulateAndGet(amount, (current, delta) -> current - delta);
~~~

The function receives **current first, amount second**; reversing the order when subtracting changes the calculation. With `LongAccumulator`, subtraction is also unsuitable as an order-independent aggregation function.

### 12.5. Putting side effects inside a CAS function

Do not call payments, I/O, generate one-time business IDs, or log "success" inside the callback. A single successful update **does not** imply the callback ran only once.

### 12.6. Misunderstanding LongAccumulator's identity

`new LongAccumulator(Long::max, 0)` is incorrect for inputs that can be negative. `Long.MIN_VALUE` is the natural identity for `max` over the `long` domain.

### 12.7. Using LongAccumulator.get() for quota control

`get()` under concurrent updates is not an atomic snapshot; the compound "read remaining then subtract" action has a race condition. Use `AtomicInteger/AtomicLong` with a predicated update function or locking.

### 12.8. Integer addition ignoring overflow

`AtomicInteger.addAndGet` and `updateAndGet(x -> x + amount)` do not automatically throw on `int` overflow; Java integer addition can wrap around. Use `Math.addExact` or a bounds-checking predicate if overflow is a business error.

### 12.9. Using an immutable reference while mutating the inner object

`AtomicReference<List<String>>` only updates the **reference** atomically; it does not make `ArrayList.add` thread-safe. If you want an immutable snapshot, use value types/defensive copies and publish a new instance.

### 12.10. Calling getThenReset while writers are still active

`LongAccumulator.getThenReset()` does not establish an atomic boundary for active writers. It may drop or misattribute updates around a reporting period boundary; if exact period boundaries are required, coordinate writers to quiesce/stop or design a dedicated period-rotation protocol.

## 13. Choosing an API by scenario

**Scenario A — need the old value returned** when issuing sequence numbers or claiming slots: consider `getAndUpdate` / `getAndAccumulate`; for simple +1 increments, use `getAndIncrement`.

**Scenario B — need the post-update value returned**: `updateAndGet` / `accumulateAndGet`; for fixed additions, use `addAndGet`.

**Scenario C — transformation based on a single state**, such as clamping to bounds, monotonic max, or conditional decrement: `getAndUpdate` or `updateAndGet` with a pure callback.

**Scenario D — an additional input value `x`**, such as an amount to add, a new measurement sample, or max with a new observation: `getAndAccumulate` or `accumulateAndGet`; ensure the function takes (`current`, `x`) in the right order.

**Scenario E — multi-field state needing consistent snapshots**: immutable record + `AtomicReference.updateAndGet` or `accumulateAndGet`. Readers must fetch **one snapshot once** and not leak references to nested mutable state.

**Scenario F — high-writer statistical metrics without needing old/new per update**: `LongAdder` (sum) or `LongAccumulator` (max/min/custom). Accept that `sum/get` under concurrent updates is not an atomic snapshot.

**Scenario G — transactions updating multiple external resources outside the JVM**: "just using a CAS" is not enough; you need transaction/idempotency protocols or coordination provided by those systems.

## 14. Atomic/CAS code review checklist

1. **What is the invariant?** A single atomic variable or a set of fields that must be updated together consistently?
2. **Does the caller need old or new?** Verify the method's return semantics and name variables `previous/updated` consistently.
3. **Unary or binary?** Unary takes `current`; binary takes `current` then `x`.
4. **Is the callback pure?** No I/O, no payment calls, no external state writes, no assumption of single invocation.
5. **Can the callback be safely retried?** Tolerates contention and recomputation with a fresh `current`.
6. **Is overflow possible?** Handle `int/long` per business rules; choose `Math.addExact` if an error should be raised.
7. **Does the reference point to an immutable graph?** Records with mutable list/array fields need defensive copies.
8. **Do multi-field reads use the same snapshot?** Never call `state.get()` twice and mix two versions.
9. **Can post-claim side effects fail?** Design compensation/idempotency for external systems outside the JVM.
10. **Is `LongAdder`/`LongAccumulator` used for check-then-act?** If so, revisit because `get/sum` is not an atomic boundary under concurrent writers.
11. **Does the accumulator function have the right identity?** Check against negative numbers, boundary values, and empty sets.
12. **Must the result be order-independent?** For `LongAccumulator`, choose an associative/commutative operator; watch out for `double` rounding.
13. **Are concurrent tasks awaited and checked for exceptions?** With executors, call `Future.get()` so failures are not hidden.
14. **Has performance been measured on a realistic workload?** Inspect success throughput, p95/p99 latency, contention, retries/GC, and writer count; do not claim "lock-free is always faster".
15. **Do reported results clearly state their boundaries?** A return value from one atomic update does not equal a consistent snapshot of the whole application.

## 15. Self-check questions

1. What does `AtomicInteger(10).getAndUpdate(x -> x * 2)` return, and what does it store? **Returns 10, stores 20**.
2. What does `AtomicInteger(10).updateAndGet(x -> x * 2)` return? **Returns 20**, the new value.
3. In `getAndAccumulate(4, (a,b) -> a-b)`, which argument is the current state? **`a`**, while `b=4`.
4. Why does `counter.set(counter.get()+1)` still have lost updates? **Because reading and writing are split into two separate operations**.
5. Why must an `updateAndGet` callback not send an email? **CAS may retry and recompute the callback**.
6. Another thread modifies the atomic value after `updateAndGet` but before `get()`. Can the two results differ? **Yes**, because each method has its own linearization point.
7. Does `LongAccumulator.accumulate(x)` return an old/new value like `AtomicLong.accumulateAndGet`? **No**, it returns `void`.
8. Is `LongAccumulator.get()` an atomic snapshot while writers are still updating? **No**.
9. Why can `LongAccumulator(Long::max, 0)` be wrong? **If all samples are negative, 0 will always win**.
10. When can `LongAccumulator.getThenReset()` be called to read a reliable period? **When coordinated so there are no concurrent updates across that boundary**.
11. Do two `AtomicInteger`s for `available/sold` guarantee an observer sees `available+sold==initial` at all times? **No, both must be updated together under a single atomic protocol**.
12. What benefit does `AtomicReference<Stats>` with an immutable record provide? **A single reference swap publishes the entire snapshot; readers fetch one reference and read fields from the same version**.
13. Does `AtomicReference.compareAndSet` compare references or call the object's `equals()`? **Expected reference by identity**.
14. Why does `LongAccumulator` require an associative and commutative function for schedule-independent results? **Accumulation order across cells/threads is not guaranteed**.
15. Does `DoubleAccumulator` guarantee a bit-for-bit order-independent floating-point sum? **No, floating-point rounding can produce different results**.
16. For a very simple counter that only needs to increment by one, is a lambda necessary? **No; `incrementAndGet` or `getAndIncrement` is clearer**.

## Conclusion

`getAndUpdate()` and `updateAndGet()` both **atomically update using a unary function**, but one returns the **old value** and the other returns the **new value**. `getAndAccumulate(x,fn)` and `accumulateAndGet(x,fn)` do the same with a binary function using the argument order **(current, x)**. Callbacks must be **side-effect-free**, because they may be invoked again under CAS contention.

Do not confuse those atomic methods with the `LongAccumulator`/`DoubleAccumulator` classes built for **high-writer statistical aggregation**: they do not return old/new per update, and reads/resets during concurrent updates are not atomic snapshots. Choose the API based on invariants, return-value needs, consistent-read requirements, and exactness; optimize performance only after proving correctness under concurrency.

## Java SE 17 References

- [AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): `getAndUpdate`, `updateAndGet`, `getAndAccumulate`, `accumulateAndGet`.
- [AtomicLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): `long` updates and memory semantics.
- [AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): unary/binary updates of a reference.
- [LongAccumulator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html): identity, accumulation order, get/reset.
- [LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): sum statistics under multiple writers.
- [DoubleAccumulator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/DoubleAccumulator.html): `double` accumulation and rounding-order limitations.
- [Java Language Specification 17, Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Threads and Locks; happens-before.
