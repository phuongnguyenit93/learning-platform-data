# Atomic Does Not Mean Automatic Overflow Detection in Java

## 1. The Problem: An Atomic Operation Can Still Return a Business-Invalid Value

In a multithreaded environment, we use `AtomicInteger` or `AtomicLong` to update counters without losing increments to interleaved read–modify–write operations. However, **atomic only describes how threads observe an update operation; it does not guarantee checked arithmetic against overflow**.

For example, an `AtomicInteger` counter at its maximum value:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger(Integer.MAX_VALUE);
System.out.println(counter.incrementAndGet()); // -2147483648
~~~

No `ArithmeticException` is automatically thrown. The out-of-range `int` value **wraps around** to `Integer.MIN_VALUE`, and the increment still executes atomically. A counter required to stay non-negative can unexpectedly turn negative even though no *lost update* occurred at all.

After this lesson, you should distinguish three requirements:

1. **Atomicity**: preventing two threads from clobbering the same update.
2. **Overflow detection**: detecting when a result cannot be represented in `int`/`long`.
3. **Business policy**: after detecting overflow, whether the system should fail with an error, reject the update, saturate at the limit, or move to a larger numeric range.

By default, an `Atomic*` construct addresses only the first requirement. The remaining two are application design responsibilities.

## 2. Java's Integer Overflow Mechanism

Signed integer types in Java have fixed bounds:

| Type | Width | Minimum value | Maximum value |
| --- | ---: | ---: | ---: |
| `int` | 32-bit | `-2_147_483_648` | `2_147_483_647` |
| `long` | 64-bit | `-9_223_372_036_854_775_808` | `9_223_372_036_854_775_807` |

With ordinary integer addition/subtraction, when the mathematical result falls outside the representable range, the resulting low-order bits are kept per Java integer arithmetic and reinterpreted as signed. For example:

~~~java
int x = Integer.MAX_VALUE;
System.out.println(x + 1); // -2147483648

long y = Long.MIN_VALUE;
System.out.println(y - 1L); // 9223372036854775807
~~~

This is **language-specified behavior**, not undefined behavior and not an automatic exception.

Atomic methods use the same value range and do not make integers unbounded:

~~~java
AtomicInteger a = new AtomicInteger(Integer.MAX_VALUE);
int old = a.getAndIncrement();  // old = 2147483647
int now = a.get();              // now = -2147483648
~~~

A subtle point of confusion: `getAndIncrement()` returns **the pre-increment value**, so the call that causes overflow can return a seemingly valid number while **the stored state has already turned negative**. By contrast, `incrementAndGet()` immediately returns the newly overflowed value.

Similarly, `AtomicLong.addAndGet(1L)`, `getAndAdd(...)`, `decrementAndGet()`, and other variants can still overflow at `long` boundaries because they use ordinary integer arithmetic.

## 3. What Does Atomicity Guarantee, and What Does It Not Guarantee?

For `AtomicInteger` or `AtomicLong`, atomic update methods ensure each update is observed under the atomic variable's consistency mechanism: an `incrementAndGet` is not split into independent read and write operations where another thread can interleave and lose an increment.

If 4 threads each call `incrementAndGet()` 10,000 times on the same counter starting at 0, the final total is 40,000 **provided no exception or overflow occurs** and all updates complete.

However, atomicity **does not provide**:

- Automatic `int`/`long` overflow detection.
- Automatic proof that the value stays non-negative or within a business range.
- Automatic prevention of someone calling `set(...)` with an out-of-policy value.
- An atomic transaction spanning multiple independent atomic variables, multiple database tables, or multiple services.
- Any guarantee that a value read between updates remains an immutable snapshot.

In other words, `AtomicInteger` can flawlessly perform `int` addition by 1, yet **the `int` result** can differ from the mathematical integer result you intended.

## 4. How to Detect Overflow: `Math.addExact` and the *Exact* Functions

Java provides overflow-checking functions in `java.lang.Math`:

| Function | Purpose | When out of range |
| --- | --- | --- |
| `Math.addExact(a, b)` | Checked `int` or `long` addition | `ArithmeticException` |
| `Math.subtractExact(a, b)` | Checked subtraction | `ArithmeticException` |
| `Math.multiplyExact(a, b)` | Checked multiplication | `ArithmeticException` |
| `Math.incrementExact(x)` | Checked increment by 1 | `ArithmeticException` |
| `Math.decrementExact(x)` | Checked decrement by 1 | `ArithmeticException` |
| `Math.negateExact(x)` | Checked negation | `ArithmeticException` |
| `Math.toIntExact(longValue)` | Checked conversion from `long` to `int` | `ArithmeticException` |

Example:

~~~java
System.out.println(Math.addExact(10, 20)); // 30
System.out.println(Math.incrementExact(7)); // 8

try {
    Math.addExact(Integer.MAX_VALUE, 1);
} catch (ArithmeticException e) {
    System.out.println("overflow detected");
}
~~~

Stdout:

~~~text
30
8
overflow detected
~~~

`Math.addExact` detects overflow **inside a single calculation**, but merely calling `Math.addExact` outside an atomic variable does not create a safe concurrent update.

Common mistake:

~~~java
AtomicInteger counter = new AtomicInteger(0);

// WRONG in a multithreaded environment:
int proposed = Math.addExact(counter.get(), 1);
counter.set(proposed);
~~~

Two threads can both read 0, both compute 1, and both set 1. No overflow occurred, yet a **lost update** happened. You must combine the Exact calculation with an **atomic update**.

## 5. Combining Overflow Checking and Atomic Updates with `updateAndGet`

A concise approach for `AtomicInteger` is:

~~~java
AtomicInteger counter = new AtomicInteger(0);
int next = counter.updateAndGet(current -> Math.addExact(current, 1));
~~~

`updateAndGet(IntUnaryOperator)` reads the state, applies the function, and updates atomically; under contention, the function may be called again with the new value. The return value is the successfully updated value.

Example adding a `delta` step:

~~~java
static int checkedAdd(AtomicInteger counter, int delta) {
    return counter.updateAndGet(current -> Math.addExact(current, delta));
}
~~~

With `AtomicLong`:

~~~java
static long checkedAdd(AtomicLong counter, long delta) {
    return counter.updateAndGet(current -> Math.addExact(current, delta));
}
~~~

The two snippets above are **illustrative methods** to place inside a Java class with appropriate imports. A standalone runnable program with full imports and `main` appears in Section 8.

### What Happens When the Computation Throws an Exception?

If `Math.addExact(current, delta)` detects overflow, it throws `ArithmeticException` before that attempt performs a successful atomic commit. Therefore, **the failing call does not apply the overflowed value**.

However, in a multithreaded program, **other** threads can still update the counter before or after the method throws. Do not interpret the exception as asserting "the variable's current value is still equal to the value I just read" under all circumstances.

If other code is still allowed to call `incrementAndGet()`, `set(...)`, or `getAndAdd(...)` directly on the same counter, the "always detect overflow" guarantee breaks as well. Encapsulate the counter behind a single API enforcing the checked policy, instead of exposing the mutable reference for callers to write arbitrarily.

### Why Must the Callback Be Pure?

`updateAndGet` and `getAndUpdate` **can re-invoke the update function** when another thread modifies the value between reading and comparing/writing (CAS). Therefore:

~~~java
// AVOID: side effects can occur multiple times when CAS retries.
counter.updateAndGet(current -> {
    sendNotification(); // Do not place sending actions inside the callback.
    return Math.addExact(current, 1);
});
~~~

Notifications, costly business logging, money transfers, event emissions, or database writes must not be executed as non-idempotent side effects inside an update function. The function should only deterministically transform the input value into the new value; perform secondary actions at another layer according to your success/failure contract. Note that even actions after a successful update do not automatically form an atomic transaction across the atomic counter and external systems.

## 6. Why Is Pre-Checking with `get()` Not Enough?

The following snippet looks reasonable yet has a race:

~~~java
// WRONG: checking and incrementing are two separate operations.
if (counter.get() < Integer.MAX_VALUE) {
    counter.incrementAndGet();
}
~~~

Suppose the initial value is `Integer.MAX_VALUE - 1`:

1. Thread A reads and confirms it is less than `Integer.MAX_VALUE`.
2. Thread B also reads and confirms it is less than `Integer.MAX_VALUE`.
3. A increments the counter to `Integer.MAX_VALUE`.
4. B increments again: wraps to `Integer.MIN_VALUE`.

Both `get` and `incrementAndGet` are individually atomic. Yet **the check–update pair is not one atomic operation**.

Replace it with:

~~~java
counter.updateAndGet(current -> Math.incrementExact(current));
~~~

If two threads update near the boundary concurrently, one attempt can succeed in bringing the value to `Integer.MAX_VALUE`, while the attempt that would cross the boundary is rejected with an exception. The check condition and arithmetic result are bound to the exact same value used for the successful atomic update.

Another option when custom behavior control is needed is a `compareAndSet` loop:

~~~java
static int incrementChecked(AtomicInteger counter) {
    while (true) {
        int current = counter.get();
        int next = Math.incrementExact(current);
        if (counter.compareAndSet(current, next)) {
            return next;
        }
    }
}
~~~

When CAS fails, the loop re-reads and recomputes from the new state. `compareAndSet` writes only if the current value still equals the expected value. This is the fundamental template for attaching a condition check to updating one atomic variable; note that execution may iterate multiple times under high contention.

**Important:** the CAS snippet above checks overflow against **the value observed on each attempt**. It does not atomically combine with an invariant living in another variable or a database.

## 7. Choosing a Policy When Approaching Limits

Detecting overflow alone does not decide what the application should do. The contract must specify one of the appropriate behaviors:

### A. Reject the Update and Signal an Error

Use `Math.addExact` inside `updateAndGet`, letting the exception translate into a business error or explicit failure at the API boundary.

- Fits counters that must never lose information.
- Helps monitoring catch configuration bugs or bad capacity estimates.
- Requires retry handling: if the client retries the same request, prevent duplicate side effects elsewhere.

### B. Saturate at the Threshold (*saturating counter*)

If the contract allows "at most MAX," you can use:

~~~java
static int saturatingIncrement(AtomicInteger counter) {
    return counter.updateAndGet(current ->
            current == Integer.MAX_VALUE ? Integer.MAX_VALUE : current + 1);
}
~~~

This is a **saturation** policy, not "accurately counting every call." Once MAX is reached, subsequent increments are dropped from the count. For adding only non-negative increments where the counter stays in a validated range, the rule above is straightforward; for arbitrary positive/negative `delta`, you must define both lower and upper bounds and avoid overflow within the threshold comparison itself.

### C. Move to a Larger Numeric Representation

- `AtomicLong` has a wider range than `AtomicInteger`, yet **still overflows**.
- `BigInteger` has arbitrary precision and can be paired with `AtomicReference<BigInteger>` updated via `updateAndGet`.
- `BigDecimal` is needed for exact fractional decimals; choose numeric type and concurrency mechanism based on the actual domain.

Example using large integers:

~~~java
import java.math.BigInteger;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<BigInteger> counter =
        new AtomicReference<>(BigInteger.valueOf(Long.MAX_VALUE));

BigInteger next = counter.updateAndGet(
        current -> current.add(BigInteger.ONE)
);

System.out.println(next); // 9223372036854775808
~~~

`BigInteger` is not limited to 64 bits like `long`, though number size and allocation/computation costs grow with magnitude. `AtomicReference<BigInteger>` allocates and swaps a new object, which may incur CAS retry overhead when many threads contend; this differs fundamentally from a simple atomic primitive.

### D. Partition Measurements or Change the Model

For event totals spanning decades, a single counter may not be the right model. You can store counters per time bucket or partition and aggregate using a sufficiently large numeric type. However, partitioning does not solve overflow if you later sum them into a `long` that is too small.

Do not silently adopt wrap-around semantics if consumers understand the counter to be a monotonically increasing, non-negative, exact total.

## 8. Standalone Java 17+ Program

Create `AtomicOverflowDemo.java`:

~~~java
import java.math.BigInteger;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicOverflowDemo {

    static int checkedAdd(AtomicInteger counter, int delta) {
        return counter.updateAndGet(value -> Math.addExact(value, delta));
    }

    static long checkedAdd(AtomicLong counter, long delta) {
        return counter.updateAndGet(value -> Math.addExact(value, delta));
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger ordinaryInt = new AtomicInteger(Integer.MAX_VALUE);
        System.out.println("wrapped int: " + ordinaryInt.incrementAndGet());

        AtomicLong ordinaryLong = new AtomicLong(Long.MAX_VALUE);
        System.out.println("wrapped long: " + ordinaryLong.addAndGet(1L));

        AtomicInteger checked = new AtomicInteger(Integer.MAX_VALUE);
        try {
            checkedAdd(checked, 1);
        } catch (ArithmeticException ex) {
            System.out.println("checked overflow caught");
        }
        System.out.println("checked after failure: " + checked.get());
        System.out.println("checked decrement: " + checkedAdd(checked, -1));

        AtomicInteger concurrent = new AtomicInteger(0);
        Thread[] threads = new Thread[4];

        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(() -> {
                for (int j = 0; j < 10_000; j++) {
                    checkedAdd(concurrent, 1);
                }
            });
            threads[i].start();
        }

        for (Thread thread : threads) {
            thread.join();
        }
        System.out.println("concurrent count: " + concurrent.get());

        AtomicReference<BigInteger> unbounded = new AtomicReference<>(
                BigInteger.valueOf(Long.MAX_VALUE)
        );
        BigInteger next = unbounded.updateAndGet(
                value -> value.add(BigInteger.ONE)
        );
        System.out.println("beyond long: " + next);
    }
}
~~~

Compile and run:

~~~bash
javac AtomicOverflowDemo.java
java AtomicOverflowDemo
~~~

Expected stdout:

~~~text
wrapped int: -2147483648
wrapped long: -9223372036854775808
checked overflow caught
checked after failure: 2147483647
checked decrement: 2147483646
concurrent count: 40000
beyond long: 9223372036854775808
~~~

Output explanation:

1. The first two statements prove atomic addition still overflows at primitive integer limits.
2. `checkedAdd(checked, 1)` at MAX is rejected by `Math.addExact` before writing the new value, so with **no other threads interfering**, `checked.get()` stays at MAX.
3. Adding `-1` is valid and executes atomically, bringing the counter to `2147483646`.
4. Four threads each updating 10,000 times yield exactly 40,000. All updates complete before reading thanks to `Thread.join()`; this number is far from `int` limits.
5. The `AtomicReference<BigInteger>` counter crosses the `long` boundary without wrapping.

This is a small example illustrating semantics; testing multithreading at 40,000 **is not proof that an application can never overflow**. You must test specifically at boundary values and real data domain limits.

## 9. When Should You Use `LongAdder` or `LongAccumulator`?

Java also provides `LongAdder` and `LongAccumulator` in `java.util.concurrent.atomic`, often useful for statistics updated under high contention.

~~~java
import java.util.concurrent.atomic.LongAdder;

LongAdder events = new LongAdder();
events.increment();
events.add(5L);

System.out.println(events.sum()); // 6
~~~

However, **`LongAdder` does not automatically check for overflow**: it uses `long` values, and the sum can exceed the range and wrap. Moreover, during concurrent updates, `sum()` is not an atomic snapshot of all parts being updated; it is unsuitable for checking an exact limit and then deciding whether to allow another increment.

Do not solve this with:

~~~java
// WRONG if a hard limit is required under concurrent updates.
if (events.sum() < LIMIT) {
    events.increment();
}
~~~

`LongAccumulator` lets you supply an accumulation function, yet providing an addition operator does not automatically create checked overflow or cross-data transactions. A custom accumulator function must also be designed for associativity, retries, contention, and out-of-range policies. When you need a hard limit on a single counter, `AtomicInteger`/`AtomicLong` with checked updates is an easier-to-verify starting point.

## 10. Related Pitfalls in Counter Design

### A. Do Not Check Using the Already-Overflowed Expression

~~~java
int next = counter.incrementAndGet();
if (next < 0) {
    // Too late: the counter was already updated to a negative value.
}
~~~

This approach may help detect an anomaly **after it happened**, but does not uphold the invariant "the counter is never negative." If negative numbers are normally valid, such a check even causes false alarms.

### B. Do Not Expect `volatile` to Add Atomically

~~~java
volatile int total = 0;
~~~

In a class field, `volatile` guarantees visibility and memory ordering relationships per the Java Memory Model, yet `total++` remains a read–add–write sequence and can lose updates. `volatile` does not check for overflow either. When atomic updates are required, use an appropriate synchronization/atomic mechanism.

### C. Multiple Atomic Variables Do Not Form a Transaction

If you need to debit one account balance and credit another, two separate `AtomicLong` fields do not form an atomic transaction. One checked subtraction and one checked addition can still leave a half-done state if the second step fails. Choose a transactional database, appropriate synchronization locks, or update one immutable state object wrapped in a single `AtomicReference` with CAS, depending on architecture.

### D. Failure Policies Must Cover Every Write Path

A `checkedIncrement()` API is useless if code elsewhere can still call `atomicCounter.getAndIncrement()` directly. Encapsulate the reference inside a class, expose only policy-enforcing update methods, and write boundary tests.

### E. Overflow Can Come from Type Casting

A `long` total can still be truncated to `int`:

~~~java
long count = 3_000_000_000L;
int unsafe = (int) count; // wrong value if intending to preserve count

try {
    int safe = Math.toIntExact(count);
} catch (ArithmeticException e) {
    System.out.println("too large for int");
}
~~~

`Math.toIntExact` is useful at API boundaries when data is collected as `long` but a caller requires `int`. Plain casts do not detect data loss automatically.

## 11. Focused Testing

A test suite should include both **arithmetic boundaries** and **concurrent contention**. A test running only 10,000 increments will never catch wrap bugs at MAX.

| Initial state | Update | Ordinary atomic behavior | Checked `Math.addExact` behavior |
| --- | --- | --- | --- |
| `0` | `+1` | `1` | `1` |
| `Integer.MAX_VALUE - 1` | `+1` | `Integer.MAX_VALUE` | `Integer.MAX_VALUE` |
| `Integer.MAX_VALUE` | `+1` | `Integer.MIN_VALUE` | Throws `ArithmeticException` |
| `Integer.MIN_VALUE` | `-1` | `Integer.MAX_VALUE` | Throws `ArithmeticException` |
| `Integer.MIN_VALUE` | `+1` | `Integer.MIN_VALUE + 1` | `Integer.MIN_VALUE + 1` |
| `Long.MAX_VALUE` (`long` type) | `+1L` | `Long.MIN_VALUE` | Throws `ArithmeticException` |

Pay special attention to:

- **Return values:** `getAndIncrement` returns the old value; `incrementAndGet` returns the new value.
- **State on failure:** in single-threaded tests, verify the value remains unchanged after an `addExact` exception.
- **Contention near MAX:** two threads concurrently incrementing from `MAX - 1`; with checked updates, exactly one update may reach MAX, and the update exceeding MAX must be rejected. Tests should synchronize the start point and capture each thread's result/exception so failures are not missed.
- **Side-effecting callbacks:** verify logic does not depend on how many times the update function runs during CAS retries.
- **Business constraints:** if the counter must stay non-negative, `delta < 0` also needs a separate non-negativity check; `Math.addExact` only prevents overflow, not valid negative `int` results.
- **Other write paths:** verify no caller uses methods bypassing the checked policy.

In a multithreaded test, wait for all futures/threads to finish and collect exceptions; otherwise errors in worker threads can be silently ignored while the main test still passes.

## 12. Practice Exercises

**Exercise 1.** Given:

~~~java
AtomicInteger a = new AtomicInteger(Integer.MAX_VALUE);
System.out.println(a.getAndIncrement());
System.out.println(a.get());
~~~

What is the output? Does `getAndIncrement()` throw an exception?

**Exercise 2.** An API uses:

~~~java
if (counter.get() != Integer.MAX_VALUE) {
    counter.incrementAndGet();
}
~~~

Why can this snippet still overflow with two threads? Replace it with a single statement using `updateAndGet` and `Math.incrementExact`.

**Exercise 3.** With `AtomicLong` currently at `Long.MIN_VALUE`, what does `decrementAndGet()` return? What happens with `updateAndGet(Math::decrementExact)`?

**Exercise 4.** A counter must stay in the range 0–100. Is `Math.addExact` sufficient to guarantee this constraint? If not, what check is needed **inside the same callback**?

**Exercise 5.** Why shouldn't `sendEmail()` be called inside an `updateAndGet` callback? If called outside the callback after the update succeeds, what guarantees are still missing?

### Answers

1. The first print returns `2147483647` (old value); the second print returns `-2147483648` (wrapped). No automatic exception is thrown.
2. Two threads can both read `MAX - 1`, and both pass the check; after two updates, the state wraps. Use `counter.updateAndGet(Math::incrementExact)` or `counter.updateAndGet(v -> Math.addExact(v, 1))`.
3. `decrementAndGet()` wraps to `Long.MAX_VALUE`. `Math.decrementExact` throws `ArithmeticException` before an out-of-bounds update attempt commits.
4. Insufficient: for example, incrementing from 100 to 101 does not overflow `int`. Inside the callback, check that `next` lies within `[0, 100]` and fail or saturate per the business contract; combine the check and update into one atomic operation.
5. The callback may run multiple times due to CAS retries, causing duplicate emails. Moving the email outside avoids side effects on recomputation, yet updating the counter and sending the email still do not form an atomic transaction, so design communication/delivery guarantees accordingly.

**Key takeaway:** `AtomicInteger` and `AtomicLong` let threads update accurately per Java integer arithmetic; they **do not** turn operations into overflow-checked arithmetic. When overflow must be rejected, combine `Math.*Exact` with `updateAndGet` or a proper CAS loop, encapsulate all write paths, and test at the limits.
