# Compare-and-Set and Why an Update Function May Be Invoked Multiple Times

## 1. The Problem When Multiple Threads Update One Number

Suppose a Java program stores a visit counter, remaining seats, total orders, or the numeric state of a device. If multiple threads concurrently read, compute, and write the variable, the following code **does not guarantee accurate incrementing**:

```java
// Counter is a class containing a mutable field:
class Counter {
    int value = 0;

    void increment() {
        value = value + 1;
    }
}
```

The statement `value = value + 1` is a sequence of operations: reading the value, computing `+1`, and writing the result. Two threads can both read 10 and both write 11, causing one increment to be lost (*lost update*). Adding `volatile` provides certain visibility guarantees for variable accesses, yet **does not turn the entire read–modify–write into an atomic operation**.

Classes in `java.util.concurrent.atomic`, especially `AtomicInteger` and `AtomicLong`, support atomic operations on a numeric value. A key mechanism to understand them is **compare-and-set (CAS)** and **retry loops** when the value is concurrently changed by another thread.

Main goals of this lesson: understand the exact condition under which CAS succeeds, why a function passed to `updateAndGet()` or `getAndUpdate()` can be called **multiple times for a single API invocation**, how to design safe update functions, and when to choose other atomic number APIs.

## 2. What Is Compare-and-Set (CAS)?

In `AtomicInteger`:

```java
boolean compareAndSet(int expectedValue, int newValue);
```

Meaning: at the moment the atomic operation executes, if the current value **equals** `expectedValue`, set it to `newValue` and return `true`; otherwise, leave the value unchanged and return `false`.

```java
AtomicInteger seats = new AtomicInteger(2);

boolean first = seats.compareAndSet(2, 1); // true: 2 -> 1
boolean stale = seats.compareAndSet(2, 0); // false: current is 1
int remaining = seats.get();               // 1
```

In a successful CAS, checking the condition and writing the value happen in a single atomic step on that atomic variable. It protects the operation **on that variable itself** against contention among threads operating properly through the atomic API.

You can picture it as:

```text
Current value = 10

Thread A reads 10, plans to write 15.
Thread B reads 10, CAS(10, 20) succeeds -> value = 20.
Thread A's CAS(10, 15) fails because current value is already 20.
Thread A must re-read 20 and compute a new candidate, e.g., 25.
```

CAS does not decide how to recompute by itself. Either an application loop or APIs such as `updateAndGet()` handle that work.

## 3. The CAS Loop: Why Is the Update Function Re-evaluated?

Consider an illustrative model of `updateAndGet()`, **not a copy of internal JDK source code**:

```java
static int updateWithCas(
        AtomicInteger value,
        java.util.function.IntUnaryOperator updater) {
    for (;;) {
        int observed = value.get();
        int candidate = updater.applyAsInt(observed);
        if (value.compareAndSet(observed, candidate)) {
            return candidate;
        }
        // Contention occurred: re-read value, invoke updater again.
    }
}
```

The method above is illustrative code to place inside a Java class with `import java.util.concurrent.atomic.AtomicInteger;`. When CAS fails due to a competing update, the loop recomputes `candidate` from the new value. Consequently:

- **One call to `updateAndGet(f)` may invoke `f` multiple times**; how many times depends on contention.
- **Only the successful CAS commits the update** for that call. Previous trial computation results are discarded.
- The value `f` receives on each execution may differ, because the state used to compute the new value has changed.
- Do not infer that "the method returns once" means "the callback ran once."

This is a crucial contract of functional update methods on atomics: Java documentation advises that the update function be **side-effect-free** because it may be re-applied when an attempted update fails due to contention.

## 4. A Java 17 Example That Deterministically Reproduces Retries

In the following program, two `CountDownLatch` instances are used **solely for verification**: forcing a competing thread to update the number from 10 to 20 **after** the first callback pass has read 10 but **before** that pass's CAS executes.

Create **`CasRetryDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class CasRetryDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger seats = new AtomicInteger(2);
        System.out.println("firstCAS=" + seats.compareAndSet(2, 1)
                + ", seats=" + seats.get());
        System.out.println("staleCAS=" + seats.compareAndSet(2, 0)
                + ", seats=" + seats.get());

        AtomicInteger value = new AtomicInteger(10);
        AtomicInteger calls = new AtomicInteger();
        AtomicInteger firstSeen = new AtomicInteger(-1);
        AtomicInteger secondSeen = new AtomicInteger(-1);
        CountDownLatch firstCall = new CountDownLatch(1);
        CountDownLatch competitorDone = new CountDownLatch(1);

        Thread competitor = new Thread(() -> {
            try {
                firstCall.await();
                if (!value.compareAndSet(10, 20)) {
                    throw new AssertionError("Expected competing CAS to succeed");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            } finally {
                competitorDone.countDown();
            }
        });
        competitor.start();

        int result = value.updateAndGet(old -> {
            int pass = calls.incrementAndGet();
            if (pass == 1) {
                firstSeen.set(old);
                firstCall.countDown();
                try {
                    competitorDone.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(e);
                }
            } else {
                secondSeen.set(old);
            }
            return old + 5;
        });
        competitor.join();

        System.out.println("updateAndGet=" + result
                + ", calls=" + calls.get()
                + ", seen=" + firstSeen.get() + "," + secondSeen.get());
        int previous = value.getAndUpdate(x -> x + 5);
        System.out.println("getAndUpdate old=" + previous + ", now=" + value.get());
        int sum = value.accumulateAndGet(12, Integer::sum);
        System.out.println("accumulateAndGet=" + sum);

        AtomicLong longValue = new AtomicLong(4_000_000_000L);
        System.out.println("longAfter=" + longValue.updateAndGet(x -> x + 1));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CasRetryDemo.java
java CasRetryDemo
```

**Verified** output when compiled with `javac --release 17`:

```text
firstCAS=true, seats=1
staleCAS=false, seats=1
updateAndGet=25, calls=2, seen=10,20
getAndUpdate old=25, now=30
accumulateAndGet=42
longAfter=4000000001
```

**Explanation of why the callback ran twice:**

1. `value` starts at 10. The first function application receives `old = 10`, records it in `firstSeen`, and signals the competing thread.
2. The callback waits on `competitorDone`. The competing thread calls `value.compareAndSet(10, 20)` and succeeds because the main update has not committed yet.
3. The first callback resumes and proposes 15. The CAS applying that proposal fails: the current number is already 20, no longer 10.
4. The update API retries; the callback receives `old = 20` and computes 25. The next CAS succeeds because the competing thread has finished.
5. `updateAndGet()` returns 25. The diagnostic counter `calls = 2` proves **a single API call evaluated the callback twice**.

In the example, `calls.incrementAndGet()`, `firstSeen.set()`, and the two latches are **intentional test-code side effects** to observe retries. **Do not copy this callback-with-side-effects pattern into production business logic.** The production callbacks below compute solely from their input argument.

Note: this is a coordinated example to make a CAS failure happen deterministically. Under random contention in real systems, a callback may run once, twice, or many times; never assume a fixed count.

## 5. Update Functions Must Be Safe When Re-invoked

A **pure function** computes its result solely from input data and relevant immutable constants/inputs, producing no externally observable side effects.

### Right way: recomputing a numeric value

```java
AtomicInteger balance = new AtomicInteger(100);
int latest = balance.updateAndGet(current -> current + 20);
// balance = 120 if no other competing update occurred
```

The function `current -> current + 20` can be re-invoked with a new value after a failed CAS; the final value is committed after a successful CAS.

**The function does not need to be idempotent under double application** in the mathematical sense `f(f(x)) = f(x)`. The function `f(x) = x + 20` lacks that property yet is still suitable. What matters is that **re-evaluating it multiple times causes no extra side effects**, and the function computes the right result from the *current value passed in*.

### Wrong way: sending email, writing business logs, calling external APIs

```java
// ANTI-PATTERN — do not perform external actions inside the callback.
balance.updateAndGet(current -> {
    sendNotification("Added 20"); // May execute multiple times.
    return current + 20;
});
```

`sendNotification(...)` is a placeholder representing external behavior, not a built-in Java method. If CAS fails, the notification may be sent even though the proposed `current + 20` **was never written**, or it may be sent multiple times.

Similarly, avoid calling network services, writing files/databases, publishing messages, creating payment transactions, incrementing another business counter, or generating new IDs inside a callback when you intend them to happen only once.

If a follow-up action is needed after updating:

```java
int newValue = balance.updateAndGet(current -> current + 20);
// After the call succeeds, this code runs once on this thread.
recordSuccessfulUpdate(newValue);
```

`recordSuccessfulUpdate(...)` is also an illustrative placeholder, not a built-in Java method. This step happens **after** the update commits; however, the atomic update and the external action **do not form a single transaction**. If the application can crash between the two steps, or if at-most-once/exactly-once event delivery under full task retries is required, you must design transactions, an outbox, or appropriate idempotency keys.

### Other Subtle Bugs

- **Reading mutable external variables:** `updateAndGet(x -> x + currentBonus.get())` may compute different increments across attempts if `currentBonus` changes. If business logic requires keeping the bonus fixed for *one* action, snapshot the bonus value beforehand and use that constant inside the callback.
- **Time and randomness:** `Instant.now()`, random numbers, or external state queries inside a callback can yield different results on retry. Determine immutable inputs before updating.
- **Exceptions:** if a callback throws an exception, that update call does not commit a proposed value; any side effects that already occurred in prior callback passes **are not rolled back**.
- **Reading two separate atomics:** a callback only guarantees atomic CAS for **the single target atomic variable**. It does not simultaneously commit a business record spanning other variables.

## 6. Related APIs and Return Values

| API | Value update | Return value | Notes |
|---|---|---|---|
| `compareAndSet(expected, next)` | If current equals expected, write next | `boolean` | `false` when the condition no longer holds |
| `getAndSet(next)` | Atomically write next | **Old value** | No callback needed |
| `getAndIncrement()` | Add 1 | **Old value** | Fits simple counters |
| `incrementAndGet()` | Add 1 | **New value** | No lambda needed |
| `getAndAdd(delta)` | Add delta | **Old value** | No lambda needed |
| `addAndGet(delta)` | Add delta | **New value** | No lambda needed |
| `getAndUpdate(f)` | Compute new number with f | **Old value of successful update** | `f` may be called again |
| `updateAndGet(f)` | Compute new number with f | **Committed new value** | `f` may be called again |
| `getAndAccumulate(x, f)` | Compute with f(current, x) | **Old value** | `f` may be called again |
| `accumulateAndGet(x, f)` | Compute with f(current, x) | **New value** | `f` may be called again |

`AtomicInteger` uses `IntUnaryOperator` for `getAndUpdate`/`updateAndGet` and `IntBinaryOperator` for `getAndAccumulate`/`accumulateAndGet`. `AtomicLong` has matching APIs with `LongUnaryOperator` and `LongBinaryOperator`.

In the verification program, after `value = 25`:

```java
int old = value.getAndUpdate(x -> x + 5);      // old = 25; value = 30
int now = value.accumulateAndGet(12, Integer::sum); // now = 42; value = 42
```

For simple addition, usually prefer `addAndGet(5)` or `getAndAdd(5)`. These specialized methods express intent clearly and avoid creating unnecessary business callbacks. When the formula depends on current state, such as upper/lower bounds, functional update methods are appropriate.

### Value-Capping Example

```java
AtomicInteger capacity = new AtomicInteger(7);
int capped = capacity.updateAndGet(
        current -> Math.min(10, current + 4));
// capped = 10
```

The callback `Math.min(10, current + 4)` has no side effects; if another thread alters `capacity`, the call can recompute from the new value.

**Overflow note:** `current + 4` with `int` can still overflow near `Integer.MAX_VALUE`. If you want an error instead of wrap-around, use `Math.addExact(current, 4)` and explicitly define how to handle the exception. `AtomicInteger` does not automatically prevent arithmetic overflow.

## 7. Writing Your Own CAS Loop for Specific Conditions

One scenario is allowing a reservation only when remaining seats are greater than 0:

```java
static boolean tryReserve(AtomicInteger remaining) {
    for (;;) {
        int old = remaining.get();
        if (old <= 0) {
            return false;
        }
        if (remaining.compareAndSet(old, old - 1)) {
            return true;
        }
        // State changed: re-read and check the condition again.
    }
}
```

This is a **method snippet** to place inside a Java class with `AtomicInteger` imported. When seats are 0, it returns false; when seats remain, it tries to subtract 1 via CAS. If CAS fails due to contention, the loop **re-checks the condition** before trying again.

If you write `if (remaining.get() > 0) remaining.decrementAndGet();`, checking and decrementing are not atomic as one combined action; two threads can both observe "1 seat left" and both decrement, causing negative seat counts. The CAS loop above ties the `old > 0` check to the exact version of the number that CAS checks.

One successful `tryReserve` call corresponds to one atomic decrement. However, the broader business task (e.g., database write, payment, ticket issuance) needs its own transaction mechanism if consistency across multiple resources is required.

## 8. AtomicLong and Large Values

When counting large values beyond the `int` range, use `AtomicLong`:

```java
AtomicLong processedBytes = new AtomicLong(4_000_000_000L);
long newTotal = processedBytes.updateAndGet(current -> current + 1);
// newTotal = 4_000_000_001L
```

Atomicity and side-effect-free callback requirements remain the same as for `AtomicInteger`. Choosing `long` does not eliminate `long` overflow risk; Java does not perform saturating addition automatically. If `Long.MAX_VALUE` can be exceeded, pick an appropriate type/algorithm and boundary checks.

If you need exact decimal numbers such as `BigDecimal` instead of `int`/`long`, you can use `AtomicReference<BigDecimal>` because `BigDecimal` is immutable:

```java
// Requires importing java.math.BigDecimal and
// java.util.concurrent.atomic.AtomicReference.
AtomicReference<BigDecimal> total =
        new AtomicReference<>(new BigDecimal("10.00"));

total.updateAndGet(old -> old.add(new BigDecimal("2.50")));
// total.get() = 12.50
```

The callback `old -> old.add(...)` creates a new `BigDecimal` without mutating the old number; this fits recomputation on CAS failure. In `AtomicReference`, `compareAndSet` matches the expected reference, **not calling `BigDecimal.equals()` or `compareTo()`**. When multiple data fields must be committed together, consider keeping an immutable state object in one `AtomicReference` or using proper synchronization/transactions.

## 9. Boundaries of CAS: What You Must Not Infer

### 9.1. CAS Does Not Guarantee the Callback Runs Only Once

The most common mistake is putting side-effecting actions in a callback and thinking "the API updates once" means "the callback runs once." **A trial result rejected by CAS can still leave external side effects behind.**

A proper callback looks like `old -> old + increment`, where `increment` is stably determined beforehand; do not touch a database, send notifications, or generate IDs inside it.

### 9.2. One Atomic Does Not Turn Multiple Business Steps into a Transaction

`AtomicInteger` commits one value of one atomic object. When changing two independent variables, or synchronizing a number with file/database data, separate updates do not become a joint atomic operation. Depending on the problem, use locks, transactions, or a single immutable state object.

### 9.3. Liveness and Contention

CAS is a technique commonly used to implement data structures and operations without explicit locking. Under high contention, a thread may retry many times and burn CPU; an individual call has no guarantee of succeeding in a fixed number of attempts. When the formula is expensive, recomputing repeatedly also carries significant cost.

For an accumulative counter updated by very many threads without per-update CAS conditions, `LongAdder` can be a useful choice to improve throughput. However, `LongAdder.sum()` is not an atomic snapshot of all concurrent updates in progress; it does not replace `AtomicLong` when you need an exact point-in-time state read to make decisions.

### 9.4. Relationship with volatile and Memory Visibility

`AtomicInteger.get()` and `set()` have volatile-like memory access semantics; `compareAndSet()` provides atomic execution and corresponding memory effects per the Java API. These operations help threads observe updates to the atomic value under the Java Memory Model.

That **does not make every ordinary variable** or every relationship among objects thread-safe. An atomic reference to a mutable object does not automatically protect mutable fields inside that object either.

### 9.5. ABA: State Can Change and Return

If the initial value is A and another thread changes it to B and back to A before CAS, `compareAndSet(A, next)` can succeed because CAS inspects **the current value**, unaware of change history. This is the *ABA problem*, relevant when business logic depends on "nothing changed in between" rather than just comparing the current number. Where appropriate, track a version/state or use `AtomicStampedReference`; never assume CAS proves no activity occurred between two reads.

## 10. Common Mistakes and How to Avoid Them

1. **Assuming `volatile int` suffices for `x++`.** It does not turn read–modify–write into an atomic operation. Use `AtomicInteger.incrementAndGet()` or proper synchronization.
2. **Writing callbacks with side effects.** If `updateAndGet()` retries, sending emails or writing to a database can execute multiple times. Move side effects outside and design separate transaction boundaries.
3. **Using mutable external data inside the callback.** The same API call can compute different results not only because the atomic changed, but because external variables changed. Snapshot required inputs consistently before updating.
4. **Misunderstanding return values.** `getAndUpdate` returns the old number, `updateAndGet` returns the new number; the same applies to the accumulate pair.
5. **Writing a custom CAS loop without re-reading and re-checking the condition.** When CAS fails, verify whether the new state still permits the operation.
6. **Using callbacks unnecessarily for simple addition.** `getAndAdd` or `addAndGet` expresses intent more clearly and avoids callbacks.
7. **Assuming AtomicInteger/AtomicLong never overflow.** Atomicity is completely distinct from arithmetic range checking; use `Math.addExact` or business bounds when needed.
8. **Testing concurrency with `sleep()` and trusting results always reproduce.** Thread scheduling is nondeterministic; the verification example above uses `CountDownLatch` to enforce clear ordering.
9. **Confusing callback re-execution with multiple committed updates.** In one successfully completed call, only one update result is accepted by CAS; earlier trial computations are discarded.
10. **Using one atomic to infer system-wide consistency.** When multiple variables or other resources exist, add synchronization protocols or transactions.

## 11. Knowledge Self-Check

**Question 1.** Why can `updateAndGet(x -> x + 1)` evaluate the lambda multiple times while a successful call commits only one addition?  
**Answer:** each attempt computes a candidate from observed state; if CAS fails, the candidate is discarded and the lambda is called again with the new state. Only the successful CAS writes its candidate.

**Question 2.** Should you write `atomic.updateAndGet(x -> { sendEmail(); return x + 1; })`?  
**Answer:** no. `sendEmail()` illustrates a side effect that can repeat on retry; separate it from the callback, and design business handling if exactly-once semantics are required.

**Question 3.** When `AtomicInteger` currently holds 8, what does `compareAndSet(7, 9)` return?  
**Answer:** `false`, and the value stays 8 because the expected value was 7.

**Question 4.** After `int old = value.getAndUpdate(x -> x * 2)` with `value = 4` (no contention), what are `old` and `value.get()`?  
**Answer:** `old = 4`, `value.get() = 8`.

**Question 5.** Must a lambda `x -> x + 3` satisfy `f(f(x)) == f(x)` to be retry-safe?  
**Answer:** no. Adding 3 is not mathematically idempotent; what is required is that retrying has no side effects and the new result is computed correctly from the state passed in.

**Question 6.** If there are three separate `AtomicInteger` variables for `available`, `reserved`, and `sold`, does a CAS call on `available` ensure all three change atomically together?  
**Answer:** no. CAS on a single atomic does not create a transaction across multiple atomics or other resources.

## 12. Conclusion

- **CAS** checks the current value and writes the new value only if the state still matches the expected value.
- **`updateAndGet`, `getAndUpdate`, and the accumulate variants can evaluate the callback multiple times** due to contention and retries.
- **Update functions must be side-effect-free**; recomputing does not mean committing multiple times. Do not place database writes, notifications, or updates to another resource inside callbacks.
- For simple addition/increment, consider `incrementAndGet` or `addAndGet`; for conditions tied to current state, use pure update functions or a CAS loop that re-checks the condition.
- Choose `AtomicInteger` or `AtomicLong` according to numeric range and business rules; atomicity does not eliminate overflow, multi-resource transaction bugs, or contention issues.

Official Java SE 17 documentation:

- [`AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
- [`AtomicLong`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [`AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
- [`CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [`LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
