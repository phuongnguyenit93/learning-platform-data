# AtomicInteger: getAndIncrement, incrementAndGet, and Atomic Update Operations in Java

## 1. Why Can Normal Integer Incrementing Fail Under Multithreading?

Suppose multiple Java threads concurrently increment a counter:

~~~java
int counter = 0;
counter++;
~~~

It looks like a single operation, but in terms of update semantics, `counter++` consists of reading the old value, computing the new value, and writing it back. Two threads can both read `counter = 5`, both compute `6`, and both write `6`: **two increments yet the result increases only once**. This is a form of *lost update*.

Making an `int` variable `volatile` gives threads certain guarantees regarding visibility and read/write ordering, yet **does not turn the expression `counter++` into an atomic operation**.

When you simply need a shared integer with independent update operations, Java provides `java.util.concurrent.atomic.AtomicInteger`. Methods such as `getAndIncrement()`, `incrementAndGet()`, `getAndAdd()`, `addAndGet()`, `getAndUpdate()`, `updateAndGet()`, and `compareAndSet()` perform operations with atomic semantics suitable for multithreading.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger(0);
counter.incrementAndGet();
~~~

This is an illustrative snippet placed inside a class/method. An `AtomicInteger` object holds a mutable `int` value; it is **not** an immutable `Integer`.

Lesson goals: understand precisely which methods return the **pre-update value**, which return the **post-update value**, functional update methods, the compare-and-set (CAS) mechanism, and the limits of atomic guarantees.

## 2. getAndIncrement and incrementAndGet: Both Add 1, Different Return Values

Both methods increment the stored value by 1 in one atomic operation, but the timing of the returned value differs:

| Method | Update | Return value |
| --- | --- | --- |
| `getAndIncrement()` | Add 1 | **Old value**, right before the successful increment |
| `incrementAndGet()` | Add 1 | **New value**, right after the successful increment |
| `getAndDecrement()` | Subtract 1 | **Old value** |
| `decrementAndGet()` | Subtract 1 | **New value** |

Example starting from 10:

~~~java
AtomicInteger counter = new AtomicInteger(10);

int oldValue = counter.getAndIncrement(); // oldValue = 10, counter = 11
int newValue = counter.incrementAndGet(); // newValue = 12, counter = 12
~~~

Key point: the prefix **`getAnd...`** means the method returns the **old value** and then applies the update; the suffix **`...AndGet`** means it returns the **value after updating**. In both cases, the update is atomic; the difference lies in **the value returned by the call**.

Comparing with ordinary integer syntax helps remember:

~~~java
int x = 10;
int a = x++; // a = 10, x = 11
int b = ++x; // b = 12, x = 12
~~~

In terms of the return value in a single thread, `getAndIncrement()` mirrors `x++`, while `incrementAndGet()` mirrors `++x`. **The analogy stops at the return value semantics**: `AtomicInteger` updates are designed for concurrent use, whereas `x++` on a shared variable has no atomic update guarantee.

### Choosing Old vs. New Value by Business Requirement

If you want to issue sequence numbers **starting from 0**, you can use:

~~~java
AtomicInteger sequence = new AtomicInteger(0);
int firstId = sequence.getAndIncrement();  // 0
int secondId = sequence.getAndIncrement(); // 1
~~~

If you want to count **completed tasks** and immediately use the new total:

~~~java
AtomicInteger completed = new AtomicInteger(0);
int countAfterCompletion = completed.incrementAndGet(); // 1
~~~

These two examples illustrate process-local behavior only. `AtomicInteger` does not produce durable IDs across application restarts, nor does it guarantee uniqueness across multiple JVMs/servers.

## 3. Add, Subtract, and Direct Write Methods

Beyond incrementing/decrementing by 1, `AtomicInteger` provides additional methods:

| Method | Action | Return value |
| --- | --- | --- |
| `get()` | Reads current value | The value read |
| `set(v)` | Sets `v` | `void` |
| `getAndSet(v)` | Atomically replaces with `v` | Value **before** replacing |
| `getAndAdd(delta)` | Atomically adds `delta` | Value **before** adding |
| `addAndGet(delta)` | Atomically adds `delta` | Value **after** adding |
| `getAndIncrement()` | Atomically adds 1 | Old value |
| `incrementAndGet()` | Atomically adds 1 | New value |
| `getAndDecrement()` | Atomically subtracts 1 | Old value |
| `decrementAndGet()` | Atomically subtracts 1 | New value |

Suppose the initial value is 20:

~~~java
AtomicInteger value = new AtomicInteger(20);

int before = value.getAndAdd(5); // before = 20; value = 25
int after = value.addAndGet(-3);  // after = 22; value = 22
int previous = value.getAndSet(0); // previous = 22; value = 0
~~~

Use `getAndAdd(-3)` or `addAndGet(-3)` when you want to subtract 3. These updates are atomic even when multiple threads act on **the same `AtomicInteger` object**.

However, `counter.get()` followed by `counter.set(counter.get() + 1)` is **not equivalent** to `incrementAndGet()` in a concurrent environment: reading and writing are separate calls, so another thread can interleave.

## 4. Complete Java 17 Program: Old, New, and Functional Updates

Create `AtomicUpdatesDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicUpdatesDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger(10);

        System.out.println("getAndIncrement: "
                + counter.getAndIncrement() + ", now=" + counter.get());
        System.out.println("incrementAndGet: "
                + counter.incrementAndGet() + ", now=" + counter.get());

        System.out.println("getAndAdd(5): "
                + counter.getAndAdd(5) + ", now=" + counter.get());
        System.out.println("addAndGet(-2): "
                + counter.addAndGet(-2) + ", now=" + counter.get());

        System.out.println("getAndUpdate(x -> x * 2): "
                + counter.getAndUpdate(x -> x * 2)
                + ", now=" + counter.get());
        System.out.println("updateAndGet(x -> x + 3): "
                + counter.updateAndGet(x -> x + 3)
                + ", now=" + counter.get());

        System.out.println("getAndAccumulate(4): "
                + counter.getAndAccumulate(4, (current, x) -> current + x * 2)
                + ", now=" + counter.get());
        System.out.println("accumulateAndGet(50, max): "
                + counter.accumulateAndGet(50, Math::max)
                + ", now=" + counter.get());

        System.out.println("compareAndSet(50, 60): "
                + counter.compareAndSet(50, 60)
                + ", now=" + counter.get());
        System.out.println("compareAndSet(50, 70): "
                + counter.compareAndSet(50, 70)
                + ", now=" + counter.get());

        System.out.println("getAndSet(0): "
                + counter.getAndSet(0) + ", now=" + counter.get());

        AtomicInteger parallelCount = new AtomicInteger();
        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 25_000; j++) {
                    parallelCount.incrementAndGet();
                }
            });
            workers[i].start();
        }
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("Parallel count: " + parallelCount.get());
    }
}
~~~

Run:

~~~bash
javac AtomicUpdatesDemo.java
java AtomicUpdatesDemo
~~~

Standard output:

~~~text
getAndIncrement: 10, now=11
incrementAndGet: 12, now=12
getAndAdd(5): 12, now=17
addAndGet(-2): 15, now=15
getAndUpdate(x -> x * 2): 15, now=30
updateAndGet(x -> x + 3): 33, now=33
getAndAccumulate(4): 33, now=41
accumulateAndGet(50, max): 50, now=50
compareAndSet(50, 60): true, now=60
compareAndSet(50, 70): false, now=60
getAndSet(0): 60, now=0
Parallel count: 100000
~~~

The values in the first part are deterministic because only the `main` thread updates `counter`. At the end, four threads concurrently increment `parallelCount` 25,000 times each; `join()` ensures the main thread waits for all threads to finish before reading the total, so the result is always **100,000** if all threads run to completion. The **order of individual increments** across threads is unspecified, yet the sum of the atomic increments does not lose updates.

`getAndAccumulate` and `accumulateAndGet` take an additional operand and a combiner function, explained in detail below.

## 5. getAndUpdate and updateAndGet: Functional Updates

Sometimes an operation is not simple addition or subtraction. For example, you may want to increase a value by a custom rule, cap the result, or transition a counter's state. Java supports:

~~~java
int old = value.getAndUpdate(x -> x * 2);
int updated = value.updateAndGet(x -> x + 3);
~~~

In both methods, an `IntUnaryOperator` transforms the **current value** into the **new value**. The difference is:

- `getAndUpdate(function)`: returns the **value before the successful update**.
- `updateAndGet(function)`: returns the **new value after the successful update**.

For example, if `value` is initially 8:

~~~java
AtomicInteger value = new AtomicInteger(8);

int a = value.getAndUpdate(x -> x * 2); // a=8; value=16
int b = value.updateAndGet(x -> x + 3); // b=19; value=19
~~~

Update functions may run **multiple times** within a single call when threads contend. Execution typically attempts an update and retries if the state changed concurrently. Therefore, the update function should be **side-effect-free** and compute its result solely from its arguments:

~~~java
value.updateAndGet(x -> Math.min(x + 1, 100));
~~~

Do not place database writes, message sends, business-count logging, external service calls, or increments of another counter inside the lambda assuming the lambda runs only once:

~~~java
// WRONG assumption example: the lambda may re-run under contention.
value.updateAndGet(x -> {
    externalCounter.incrementAndGet();
    return x + 1;
});
~~~

If the call retries, `externalCounter` can be incremented multiple times while `value` updates successfully only once. Move side effects outside after the operation succeeds, and consider business consistency if multiple systems must be updated.

### Capping at Maximum 100 Example

~~~java
AtomicInteger progress = new AtomicInteger(98);

int after = progress.updateAndGet(x -> Math.min(100, x + 1));
// after = 99

after = progress.updateAndGet(x -> Math.min(100, x + 1));
// after = 100

after = progress.updateAndGet(x -> Math.min(100, x + 1));
// after = 100
~~~

In these examples, an atomic update is applied to one integer at a time. If business logic involves multiple fields that must uphold an invariant together, an overall synchronization design is needed.

## 6. getAndAccumulate and accumulateAndGet: Combining with an Operand

When an update needs both the **current value** and a separate **operand**, use:

~~~java
value.getAndAccumulate(x, (current, operand) -> ...);
value.accumulateAndGet(x, (current, operand) -> ...);
~~~

The function is an `IntBinaryOperator`. Parameter order is **current value first**, **operand `x` second**. For example:

~~~java
AtomicInteger score = new AtomicInteger(10);

int previous = score.getAndAccumulate(
        4, (current, increment) -> current + increment * 2);
// previous=10, score=18

int latest = score.accumulateAndGet(25, Math::max);
// latest=25, score=25
~~~

Here `Math::max` retains the larger of the stored value and the given threshold. This operation suits tracking the "maximum observed value."

Other uses of accumulator functions:

- `Math::min`: retain the minimum observed value.
- `(current, increment) -> current + increment`: add an operand, similar to `addAndGet` when the new value is needed.
- `(current, factor) -> current * factor`: multiply by a factor, subject to possible `int` overflow.
- `(current, newValue) -> Math.max(current, newValue)`: advance only up to the highest value seen.

Just like `getAndUpdate`, the accumulator function may execute multiple times under contention. Use a **pure, side-effect-free function**, and do not assume callback invocations equal successful updates.

## 7. compareAndSet: Conditional Updates via CAS

`compareAndSet(expectedValue, newValue)` is commonly abbreviated **CAS** (*compare-and-set*). It performs the atomic logic:

> If the current value equals `expectedValue`, replace it with `newValue` and return `true`; otherwise, leave it unchanged and return `false`.

~~~java
AtomicInteger stock = new AtomicInteger(5);

boolean first = stock.compareAndSet(5, 4);  // true; stock=4
boolean second = stock.compareAndSet(5, 3); // false; stock=4
~~~

CAS is essential when an update is only allowed if state is still what we observed. It prevents "read-then-write" updates from clobbering changes by other threads.

A CAS loop can express the rule "never let the value drop below 0":

~~~java
static boolean tryTakeOne(AtomicInteger stock) {
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
~~~

This is a **method fragment** inside a class with `import java.util.concurrent.atomic.AtomicInteger;`, assuming `stock` is non-null and the application invariant ensures a non-negative value from the start. If other threads can set negative values or perform complex adjustments, re-verify the business condition.

Explanation:

1. Read the current value.
2. If already 0, no more can be taken.
3. Attempt CAS transitioning from `current` to `current - 1`.
4. If another thread just modified the value, CAS fails; the loop re-reads and decides on the new value.

Another way when working with just one integer is:

~~~java
static boolean tryTakeOne(AtomicInteger stock) {
    int old = stock.getAndUpdate(x -> x > 0 ? x - 1 : x);
    return old > 0;
}
~~~

Choose only **one** of the two `tryTakeOne` definitions if placing them in the same class, as they share the same signature. The `getAndUpdate` approach embeds the condition inside the atomic function; even when the value stays unchanged at zero stock, the update call still returns the old value to decide from.

### Limits of CAS for Multi-Step Operations and the ABA Phenomenon

CAS on `AtomicInteger` compares one current `int` value; it does not record history. If one thread observes `A`, and another thread changes `A → B → A`, the first thread's CAS can still succeed because **the final value returned to A**, even though state changed in between. This is the **ABA problem**.

If transition history or versioning matters, you may need to model an explicit version, use another atomic type such as `AtomicStampedReference` for object references, or use locks/appropriate data structures. Do not assume CAS on a single `int` solves arbitrary transactions or multi-field invariants.

## 8. What Does AtomicInteger Guarantee About Concurrency and Memory?

`AtomicInteger` provides atomic operations for **one integer value** with specified memory semantics. Common operations such as `get()`, `set()`, `compareAndSet()`, and `getAndIncrement()` correspond to observing/updating state with appropriate memory ordering; you do not need to mark another `int` as `volatile` to make atomic operations safe.

Distinguish three concepts:

- **Atomicity:** A successful atomic update is never "half-done"; multiple threads incrementing the same counter do not lose updates.
- **Visibility:** Values are published/read under the method's memory semantics, allowing threads to see updates appropriately.
- **Ordering:** Operations may have to satisfy specific memory ordering rules. Newer methods like `getAcquire`, `setRelease`, or `getOpaque` have weaker/targeted semantics and should only be chosen when you fully understand the concurrency requirements.

**Single-variable guarantees do not turn multiple steps into a transaction.** For example:

~~~java
if (balance.get() >= 10) {
    balance.addAndGet(-10);
}
~~~

This is not an atomic "check-then-deduct." Two threads can both observe `balance = 10` and both subtract, leaving `-10`. To preserve the invariant "never overdraw," use CAS or a conditional `updateAndGet` with the check inside the lambda, while clearly defining how success/failure is reported.

When **two** variables must be updated together (such as `balanceA` and `balanceB` for a transfer), two separate `AtomicInteger` instances do not create an atomic transaction across the pair. Synchronize with locks, model shared state under a single update, or use an appropriate transaction mechanism.

## 9. Comparing Atomic Updates with synchronized and volatile

| Tool | What can it solve? | When is it insufficient? |
| --- | --- | --- |
| `volatile int count` | Guarantees visibility and ordering properties of reading/writing a `volatile` variable | `count++` can still lose updates |
| `AtomicInteger.incrementAndGet()` | Atomically increments a single value | Multiple fields/complex invariants are not automatically protected |
| `synchronized` | Protects a complex code block using the same monitor | May increase contention or blocking if poorly designed |
| `ReentrantLock` | Explicit lock for larger data scopes, with additional capabilities | Requires careful lock management, typically `try/finally` |

`AtomicInteger` is very convenient for simple counters; a CAS loop can retry under contention, meaning operations do not necessarily complete on a single attempt. Good design chooses **the unit of state that must be protected**, then selects the fitting tool.

## 10. Integer Overflow, Range Limits, and Other Number Types

`AtomicInteger` stores a **signed 32-bit `int`**. Increment/add operations do not automatically throw on exceeding `int` bounds: results follow Java 32-bit integer overflow rules.

~~~java
AtomicInteger count = new AtomicInteger(Integer.MAX_VALUE);
int next = count.incrementAndGet();
System.out.println(next); // -2147483648
~~~

Hence, a continuously incremented counter can **wrap around to negative numbers**. Atomicity does not imply overflow control. If you need a larger range, use `AtomicLong` (64-bit); if you need very large numbers unbounded by primitive integer types, design memory and synchronization differently, because `AtomicInteger` does not turn into `BigInteger`.

For accumulative counters under high contention across many threads, `LongAdder` sometimes outperforms `AtomicLong` by striping updates, though `sum()` is not necessarily an **atomic snapshot** of all concurrent updates in progress. Do not replace `AtomicInteger` with `LongAdder` when you need CAS or exact per-update sequence values.

If the requirement is "increment up to the maximum and stop," you can use:

~~~java
AtomicInteger limit = new AtomicInteger(Integer.MAX_VALUE - 1);
int updated = limit.updateAndGet(x ->
        x == Integer.MAX_VALUE ? x : x + 1);
~~~

This expression does not overflow if the initial value does not exceed `Integer.MAX_VALUE` and no other actor puts data into an invalid state. For business logic requiring a different overflow policy, define it explicitly: clamp the value, signal an error, or switch to a wider data type.

## 11. Common Mistakes

**Mistake 1 — Confusing return values.** `getAndIncrement()` returns the value **before** incrementing; `incrementAndGet()` returns the value **after** incrementing. When issuing IDs or counting events, mixing up the starting point causes an off-by-one error.

**Mistake 2 — Thinking `get()` followed by `set()` is an atomic update.** Two separate calls still allow another thread to interleave. Use `getAndAdd`, `updateAndGet`, CAS, or locks as required.

**Mistake 3 — Using `volatile int` and `++` to avoid lost updates.** `volatile` does not combine reading, adding, and writing into one atomic action.

**Mistake 4 — Writing update functions with side effects.** Lambdas in `getAndUpdate`/`updateAndGet`/`accumulateAndGet` may run multiple times under contention. Do not perform side effects in the callback expecting single execution.

**Mistake 5 — Reading the value right after updating and assuming it is always this call's exclusive result.** Under multithreading, right after `getAndIncrement()`, another thread can increment again before `get()`. When you need **the value issued to your own call**, directly use the return value of the method.

**Mistake 6 — Assuming AtomicInteger solves multi-variable transactions.** Updating `a` then `b` is not atomic across the pair; another thread can observe the intermediate state. Use appropriate synchronization or consolidate state if a joint invariant must hold.

**Mistake 7 — Forgetting int overflow.** `incrementAndGet()` at `Integer.MAX_VALUE` wraps back to `Integer.MIN_VALUE` without throwing an exception.

**Mistake 8 — Assuming a CAS step always succeeds immediately.** If another thread modified the value, CAS returns false; the loop must re-read and decide again. Under heavy contention, many retries may occur.

**Mistake 9 — Using an AtomicInteger counter as a global ID.** It only manages state within an object/JVM scope. Restarts, multiple instances, multiple machines, or `int` limits can break long-term unique ID expectations.

**Mistake 10 — Reusing issued sequence numbers while ignoring the return value.** In multithreaded `getAndIncrement`, each call gets its own distinct old value prior to wrap-around; save that result right there instead of calling `get()` afterward.

## 12. Practice Exercises and Solutions

### Exercise 1. Predict the Return Values

~~~java
AtomicInteger x = new AtomicInteger(5);
int a = x.getAndIncrement();
int b = x.incrementAndGet();
int c = x.getAndAdd(3);
int d = x.addAndGet(-2);
~~~

**Answer:** `a = 5`, `b = 7`, `c = 7`, `d = 8`; final value of `x` is `8`.

Explanation: start at 5 → `getAndIncrement` returns 5, stores 6 → `incrementAndGet` stores/returns 7 → `getAndAdd(3)` returns 7, stores 10 → `addAndGet(-2)` stores/returns 8.

### Exercise 2. Retain the Maximum Value Observed

To keep `maximum` from ever decreasing when a new observation `observed` arrives, write:

~~~java
AtomicInteger maximum = new AtomicInteger(0);
int latest = maximum.accumulateAndGet(25, Math::max);
~~~

`latest` is 25. If another thread concurrently reports 30, `Math::max` accumulation preserves the maximum rule across successful updates. If values can be negative and you need the maximum across the whole `int` range, choose an appropriate initial value instead of defaulting to 0.

### Exercise 3. Fix Unsafe Check-Then-Update

The following code has a race:

~~~java
if (stock.get() > 0) {
    stock.decrementAndGet();
}
~~~

A fix when protecting only a single `AtomicInteger` and knowing `stock` starts non-negative:

~~~java
int previous = stock.getAndUpdate(x -> x > 0 ? x - 1 : x);
boolean taken = previous > 0;
~~~

This snippet assumes `stock` is already declared. The update function both checks and computes the new state in one atomic operation; `previous > 0` tells whether this call claimed one unit.

### Exercise 4. Why Can This Code Print a Different Value?

~~~java
int myNumber = shared.getAndIncrement();
int observedNow = shared.get();
~~~

`observedNow` can be greater than `myNumber + 1` because other threads may perform additional updates between the two calls. `myNumber` remains the old value **atomically issued to this exact call**. Do not assume a subsequent `get()` is a private snapshot of your thread's update.

### Exercise 5. Check Overflow

~~~java
AtomicInteger x = new AtomicInteger(Integer.MAX_VALUE);
System.out.println(x.getAndIncrement());
System.out.println(x.get());
~~~

**Answer:**

~~~text
2147483647
-2147483648
~~~

The first call returns the old value `Integer.MAX_VALUE`, while the stored value increments past the boundary and overflows to `Integer.MIN_VALUE`.

## 13. Method Selection Summary

- Need the **value before incrementing/decrementing/adding** → use `getAndIncrement`, `getAndDecrement`, `getAndAdd`.
- Need the **value after incrementing/decrementing/adding** → use `incrementAndGet`, `decrementAndGet`, `addAndGet`.
- Need a **function computed from the stored value** → use `getAndUpdate` or `updateAndGet` with a pure callback, choosing old/new return value accordingly.
- Need to **combine a new operand with current state** → use `getAndAccumulate` or `accumulateAndGet`.
- Need to **update only if still matching an expected value** → use `compareAndSet` and handle failure.
- Need **one atomic counter** → `AtomicInteger` may fit; need multiple values changing together → choose a synchronization/transaction mechanism covering that state.

**Takeaway:** `AtomicInteger` operations provide atomic updates on **a single integer**. The distinction between `getAnd...` and `...AndGet` lies in **whether the pre-update or post-update value is returned**; concurrency safety on one variable does not mean multi-step operations, multiple variables, or side effects inside callbacks are atomic.
