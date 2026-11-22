# AtomicInteger and AtomicLong in Java: Thread-Safe Number Updates

In a multithreaded program, the expression `counter++` **is not an atomic operation** simply because `counter` has primitive type `int` or is declared `volatile`. When two threads both read the old value and both write the new value, one increment can be lost (*lost update*).

`AtomicInteger` and `AtomicLong` in the `java.util.concurrent.atomic` package provide atomic operations such as incrementing, adding, swapping, and conditional updates on **a single integer value**. They suit counters, sequence numbers, numeric status flags, or a state encoded as a number updated across multiple threads when a lock wrapping an entire business block is unnecessary.

This lesson explains the meaning of atomicity, how to use the API, the CAS mechanism, memory guarantees, limitations with multiple variables, overflow, and when to choose another construct.

## 1. Why Can `counter++` Lose Increments?

Consider a shared field:

```java
private int counter = 0;

void increase() {
    counter++; // Not guaranteed atomic when called concurrently by multiple threads
}
```

At a logical level, the increment expression involves three steps: reading `counter`, adding 1, and writing back the result. One possible interleaving is:

| Step | Thread A | Thread B | Shared value |
|---|---|---|---:|
| Initial | | | 10 |
| 1 | Reads 10 | | 10 |
| 2 | | Reads 10 | 10 |
| 3 | Computes 11 and writes 11 | | 11 |
| 4 | | Computes 11 and writes 11 | 11 |

Both threads executed one increment, yet the final value is **11 instead of 12**. This example illustrates one possible schedule; the exact result of a multithreaded run depends on execution scheduling.

Replacing the field with `volatile int counter` gives reads and writes volatile visibility guarantees, **but the sequence read → add → write still does not become one atomic operation**. `volatile` does not fix this lost update.

You can guard the increment with a `synchronized` lock, or use:

```java
import java.util.concurrent.atomic.AtomicInteger;

private final AtomicInteger counter = new AtomicInteger();

void increase() {
    counter.incrementAndGet();
}
```

`incrementAndGet()` is an atomic update. As long as threads only mutate the counter through the atomic methods on the same object, increments will not be lost due to interleaved read–modify–write steps.

## 2. How Do AtomicInteger and AtomicLong Differ?

| Feature | `AtomicInteger` | `AtomicLong` |
|---|---|---|
| Stored value | Signed 32-bit `int` | Signed 64-bit `long` |
| Range | -2,147,483,648 to 2,147,483,647 | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 |
| Constructing with initial value | `new AtomicInteger(10)` | `new AtomicLong(10L)` |
| Reading and setting | `get()`, `set(...)` | `get()`, `set(...)` |
| Increment, decrement, add | `incrementAndGet()`, `addAndGet(...)`, ... | Same-named methods with `long` arguments/results |
| Conditional updates | `compareAndSet(...)`, `compareAndExchange(...)` | Corresponding methods on `long` |
| Example expression | `counter.incrementAndGet()` | `sequence.incrementAndGet()` |

Both are **reference/object classes**, unlike primitive `int`/`long`. For example, `AtomicInteger counter = new AtomicInteger(5)` stores the current state inside the object, while the variable `counter` holds a reference to that object. The typical pattern is to keep the reference fixed with `final`, then operate on the atomic value:

```java
private final AtomicLong sequence = new AtomicLong(100L);

long nextSequence() {
    return sequence.incrementAndGet();
}
```

Here `final` prevents reassigning the `sequence` reference. It does not make the value inside the object immutable; `incrementAndGet()` still updates that value.

### Initialization

```java
AtomicInteger zeroCounter = new AtomicInteger();     // initially 0
AtomicInteger withInitial = new AtomicInteger(42);  // initially 42
AtomicLong longCounter = new AtomicLong(1_000_000L);
```

Standalone snippets in this lesson only illustrate syntax within an appropriate class/method; a complete standalone Java program with `main` appears in the hands-on section.

## 3. Basic Operations and Return Values

One advantage of this API is that method names clearly indicate whether they return the **previous value** or the **updated value**.

| Method | Meaning | Return value |
|---|---|---|
| `get()` | Reads current state | The value read |
| `set(v)` | Assigns new state | `void` |
| `getAndSet(v)` | Atomically replaces with `v` | Old value |
| `getAndIncrement()` | Increments by 1 | Value before incrementing |
| `incrementAndGet()` | Increments by 1 | Value after incrementing |
| `getAndDecrement()` | Decrements by 1 | Value before decrementing |
| `decrementAndGet()` | Decrements by 1 | Value after decrementing |
| `getAndAdd(delta)` | Adds `delta` | Old value |
| `addAndGet(delta)` | Adds `delta` | New value |
| `compareAndSet(expected, update)` | Changes only if current value equals `expected` | `boolean` indicating success |
| `compareAndExchange(expected, update)` | Compares and may swap | Value observed before the compare/exchange |
| `getAndUpdate(fn)` | Updates using a function of current state | Old value |
| `updateAndGet(fn)` | Updates using a function of current state | New value |
| `getAndAccumulate(x, fn)` | Combines current value with `x` using a two-argument function | Old value |
| `accumulateAndGet(x, fn)` | Combines both values and updates | New value |

Corresponding methods exist on both `AtomicInteger` and `AtomicLong`, with signatures using `int`/`IntUnaryOperator`/`IntBinaryOperator` or `long`/`LongUnaryOperator`/`LongBinaryOperator` respectively.

Example of the "before and after" difference:

```java
AtomicInteger x = new AtomicInteger(5);

int oldValue = x.getAndIncrement(); // oldValue = 5, x = 6
int newValue = x.incrementAndGet(); // newValue = 7, x = 7
int beforeAdd = x.getAndAdd(3);     // beforeAdd = 7, x = 10
int afterAdd = x.addAndGet(2);      // afterAdd = 12, x = 12
```

Do not write `get()` followed by `set(get() + 1)` as a substitute for `incrementAndGet()`: two separate calls do not combine into an atomic operation.

## 4. The CAS Mechanism and Linearization Points

**CAS** (*compare-and-set*) takes three logical elements: the stored value, the expected value, and the new value. Only when the current value equals the expected value does the change occur.

```java
AtomicInteger state = new AtomicInteger(10);

boolean first = state.compareAndSet(10, 20); // true
boolean second = state.compareAndSet(10, 30); // false
int current = state.get();                  // 20
```

After the first CAS, the state is 20, so the second call with `expected = 10` fails. It does **not** write 30; the final state remains 20.

`compareAndExchange(expected, newValue)` also compares and atomically updates conditionally, but returns the **actual value observed** at the time of the operation instead of a `boolean`:

```java
AtomicLong slot = new AtomicLong(5L);

long observed1 = slot.compareAndExchange(5L, 8L);  // 5; slot = 8
long observed2 = slot.compareAndExchange(5L, 9L);  // 8; slot stays = 8
```

For atomic read–modify–write operations, you can reason as if each operation has a **linearization point**: at one abstract instant, the entire operation takes effect for all threads observing that atomic variable. Operations may execute concurrently, yet their effects on **a single atomic object** have an order consistent with the API's atomicity guarantees.

### CAS Loop for Conditional Increment

Suppose you only want to increment a counter while its value is below 100:

```java
static boolean incrementBelow100(AtomicInteger counter) {
    while (true) {
        int current = counter.get();
        if (current >= 100) {
            return false;
        }
        if (counter.compareAndSet(current, current + 1)) {
            return true;
        }
        // Another thread updated first: re-read and retry.
    }
}
```

This is an **illustrative method** to place inside a class with `AtomicInteger` imported. Checking `current < 100` and writing `current + 1` go through a CAS condition based on the same expected value; if another thread changes the value, CAS fails and the loop checks again.

In this example, the `current >= 100` check also protects against overflow from adding 1, because every successful increment occurs when `current < 100`. If other operations are allowed to decrement or arbitrarily change the counter, clearly define the business contract to preserve bounds.

**Do not assume every CAS succeeds on the first try:** under contention, multiple threads may have to retry. CAS avoids an application lock for a single operation, yet still consumes CPU under high contention.

### Update Functions May Execute Multiple Times

`updateAndGet(fn)` and `getAndUpdate(fn)` conveniently wrap the update loop in the API:

```java
AtomicInteger count = new AtomicInteger(7);
int capped = count.updateAndGet(v -> Math.min(v + 1, 10)); // 8
```

Under contention, `fn` **may be invoked multiple times** before the update succeeds. The function should be **side-effect-free** and produce a deterministic result from its argument. Avoid calling network APIs, writing to a database, incrementing another counter, logging a one-time business event, or generating uncontrolled random values inside the lambda: the function can re-run and cause duplicate side effects.

For updates requiring multiple steps or multiple resources, consider locks or another coordination mechanism.

## 5. Visibility Guarantees and Relationship to volatile

The standard `get()` and `set(v)` methods of `AtomicInteger`/`AtomicLong` have memory effects equivalent to a **volatile read** and **volatile write** on the atomic value. Operations like `compareAndSet` provide atomic semantics along with corresponding memory constraints per the JDK documentation.

This addresses two distinct needs:

1. **Visibility:** updates can be observed by other threads through appropriate reads under the Java Memory Model.
2. **Atomic read–modify–write:** two threads incrementing concurrently cannot lose an increment if both use `incrementAndGet()` on the same object.

`volatile` alone supports the first need for single-field accesses, but does not automatically make `x++` atomic. `AtomicInteger` adds atomic compound updates.

Example of data publication ordering:

```java
class Holder {
    private int data;
    private final AtomicInteger ready = new AtomicInteger(0);

    void publish() {
        data = 42;
        ready.set(1);
    }

    int consumeAfterReady() {
        while (ready.get() == 0) {
            Thread.onSpinWait();
        }
        return data;
    }
}
```

If one thread executes `publish()` and another observes `ready.get() == 1` from that `set(1)`, the **happens-before** relationship through the volatile-like operation makes the write `data = 42` before raising the flag visible to the reading thread, assuming no other competing updates to `data` and `ready`. This is an **example explaining memory ordering**, not a recommendation to spin-wait in real applications; normally prefer `CountDownLatch`, `Future`, `BlockingQueue`, or appropriate synchronization tools.

Some extended APIs have different memory semantics, such as `lazySet` (release), `getAcquire`, `setRelease`, `getOpaque`, `setOpaque`, `getPlain`, and `setPlain` in supporting Java versions. **Do not arbitrarily replace `get()/set()` with weaker variants** without proving synchronization requirements; the basic examples and reasoning here use `get()`/`set()` and standard CAS.

## 6. Complete Java 17+ Program

Save to `AtomicNumbersDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class AtomicNumbersDemo {
    public static void main(String[] args) throws InterruptedException {
        final int workers = 4;
        final int iterations = 10_000;
        AtomicInteger counter = new AtomicInteger();
        AtomicLong total = new AtomicLong();
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(workers);

        for (int w = 0; w < workers; w++) {
            Thread thread = new Thread(() -> {
                try {
                    start.await();
                    for (int i = 0; i < iterations; i++) {
                        counter.incrementAndGet();
                        total.addAndGet(2L);
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            });
            thread.start();
        }

        start.countDown();
        done.await();
        System.out.println("counter = " + counter.get());
        System.out.println("total = " + total.get());

        AtomicInteger state = new AtomicInteger(5);
        System.out.println("getAndIncrement = "
                + state.getAndIncrement() + ", now = " + state.get());
        System.out.println("incrementAndGet = " + state.incrementAndGet());
        System.out.println("getAndAdd = "
                + state.getAndAdd(3) + ", now = " + state.get());
        System.out.println("addAndGet = " + state.addAndGet(2));
        System.out.println("CAS = " + state.compareAndSet(12, 20)
                + ", now = " + state.get());
        System.out.println("compareAndExchange = "
                + state.compareAndExchange(20, 30)
                + ", now = " + state.get());
        System.out.println("updateAndGet = "
                + state.updateAndGet(v -> v * 2));
        System.out.println("accumulateAndGet = "
                + state.accumulateAndGet(5, Integer::sum));

        System.out.println("int wrap = "
                + new AtomicInteger(Integer.MAX_VALUE)
                        .incrementAndGet());
        System.out.println("long wrap = "
                + new AtomicLong(Long.MAX_VALUE)
                        .incrementAndGet());
    }
}
```

Compile and run (JDK 17+):

```bash
javac AtomicNumbersDemo.java
java AtomicNumbersDemo
```

**Stdout when threads complete normally without interruption:**

```text
counter = 40000
total = 80000
getAndIncrement = 5, now = 6
incrementAndGet = 7
getAndAdd = 7, now = 10
addAndGet = 12
CAS = true, now = 20
compareAndExchange = 20, now = 30
updateAndGet = 60
accumulateAndGet = 65
int wrap = -2147483648
long wrap = -9223372036854775808
```

Four threads count concurrently, each incrementing `counter` 10,000 times and adding `2L` to `total` per iteration. Because each operation on each atomic object is atomic, the final results after all loops complete their iterations are `4 × 10,000 = 40,000` and `4 × 10,000 × 2 = 80,000`. `CountDownLatch` ensures `main` waits for the threads to finish before printing; it does not replace the role of `AtomicInteger`/`AtomicLong` for concurrent updates.

In the example, if a thread is interrupted while waiting on `start.await()`, it will exit and may not run all iterations. The stdout above reflects a normal uninterrupted run; when designing real systems you must decide how to handle task cancellation and partial results.

The lines operating on `state` clearly illustrate before/after values, a successful CAS, and `compareAndExchange` returning the observed value. The last two lines are a reminder that **atomic does not mean overflow-checked**.

## 7. Atomic Does Not Mean Everything Is Safe

### 7.1. Each Individual Update Is Protected, Not a Multi-Variable Transaction

Example using two atomics:

```java
AtomicInteger stock = new AtomicInteger(10);
AtomicInteger sold = new AtomicInteger(0);

stock.decrementAndGet();
sold.incrementAndGet();
```

Each line is atomic on **its own single object**, but between the two lines another thread can observe that `stock` decreased while `sold` has not yet increased. Two variables do not form a unified **transaction**.

If the invariant `stock + sold == 10` is required at every valid observation, you need a synchronization mechanism coordinating both fields—such as `synchronized`/`Lock`—or encapsulate the entire invariant state in **one** immutable object and swap references using `AtomicReference` with a proper algorithm. `AtomicInteger` and `AtomicLong` by themselves cannot make a multi-variable update atomic.

### 7.2. Separate Read-Then-Act Still Races

A common mistake:

```java
if (counter.get() < 100) {
    counter.incrementAndGet();
}
```

Two threads can both observe 99 and both increment: the result reaches 101. Both increments are atomic, yet the overall **check → decide → increment** is not atomic. Use a CAS loop as in Section 4 or an appropriate locking mechanism to check and update against the same state.

### 7.3. `AtomicLong` Does Not Prevent Overflow

`AtomicInteger` stores an `int`; `AtomicLong` stores a `long`. Addition/increment operations follow Java integer arithmetic and still **wrap around** when exceeding the signed range:

```java
AtomicInteger a = new AtomicInteger(Integer.MAX_VALUE);
System.out.println(a.incrementAndGet()); // -2147483648

AtomicLong b = new AtomicLong(Long.MAX_VALUE);
System.out.println(b.incrementAndGet()); // -9223372036854775808
```

If business rules require **never exceeding a limit**, handle the condition with a CAS loop or appropriate bounding logic. If exact counts larger than the `long` range are needed, use another representation (e.g., `BigInteger` with synchronization/`AtomicReference`), rather than merely swapping `AtomicInteger` for `AtomicLong` and assuming unbounded range.

### 7.4. CAS Compares the Current Value, but Can Encounter ABA

Suppose state transitions along the sequence `A → B → A`. A thread holding the old value `A` and issuing a CAS expecting `A` may succeed because the current value is `A` again, even though intermediate changes occurred. This is the **ABA problem**. For simple counters, ABA may not affect correctness; for lock-free algorithms relying on state history, consider attaching a version (e.g., a version counter or `AtomicStampedReference` for object references) or using another synchronization design. `AtomicInteger` does not automatically detect `A → B → A` history.

### 7.5. Atomics Do Not Guarantee Thread Ordering Fairness

CAS operations may fail and retry many times under high contention. Do not assume all threads will make fair progress, or that every operation executes in bounded constant time under every schedule. Designs must match throughput, latency, and progress requirements under load.

## 8. When to Choose LongAdder, synchronized, or AtomicReference?

**AtomicInteger/AtomicLong** fits when you need **exact, individual** operations like `getAndIncrement()`, `compareAndSet()`, or obtaining a unique sequence number.

When many threads concurrently update an accumulative counter and do not need CAS or a unique sequence number per increment, `LongAdder` can reduce contention by striping updates:

```java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();
requests.increment();
requests.add(5L);

long approxAtMoment = requests.sum(); // after two sequential updates: 6
```

**Important distinction:** `LongAdder.sum()` is not an atomic snapshot with respect to ongoing concurrent updates; do not use `LongAdder` to assign unique IDs or enforce CAS conditions based on an exact observed value. Compare performance with real benchmarks: `LongAdder` is not automatically faster under all workloads or low contention.

| Need | Suitable construct |
|---|---|
| Generating increasing IDs/sequence numbers within the type's range | `AtomicLong.incrementAndGet()`; handle overflow as required |
| Accurately incrementing a counter and reading the current value | `AtomicInteger` or `AtomicLong` |
| Gathering request statistics with many updating threads, where `sum()` need not be an atomic snapshot during writes | `LongAdder` |
| Multiple fields must simultaneously satisfy an invariant | `synchronized`, `Lock`, or a combined state design |
| Atomically replacing an immutable state object | `AtomicReference<State>` |
| Many values larger than 64 bits | `BigInteger` model plus synchronization or an appropriate atomic reference |

Tool selection depends on **the invariant to be protected**, not merely on whether multiple threads access the data.

## 9. Common Mistakes and How to Avoid Them

1. **Thinking `volatile int++` is atomic.** `volatile` does not merge read, add, and write. Use `incrementAndGet()` or synchronization.
2. **Splitting an update into `get()` then `set()`.** Two separate calls can interleave. Use `addAndGet`, `getAndUpdate`, or CAS.
3. **Confusing old and new return values.** `getAndIncrement()` returns the previous value; `incrementAndGet()` returns the new value. Choose according to sequence generation vs. counter needs.
4. **Assuming two Atomics form a transaction.** Updating `balanceA` then `balanceB` leaves a window with an observable intermediate state.
5. **Putting side effects inside an `updateAndGet` function.** The lambda may re-run when CAS fails; use pure functions without calling APIs with external effects.
6. **Using `AtomicLong` and assuming it never overflows.** `long` is still bounded; incrementing past `Long.MAX_VALUE` wraps around.
7. **Relying on `LongAdder.sum()` as an atomic snapshot during concurrent updates.** `sum()` is meant for statistics, not instantaneous exact snapshots under contention.
8. **Using `while (flag.get() == 0)` for long waits.** Busy-waiting burns CPU; choose an appropriate wait, notification, or blocking mechanism.
9. **Treating CAS as locking an entire code block.** CAS guards comparing/updating one variable; it does not synchronize external effects outside the CAS.
10. **Thinking having atomics makes the entire application thread-safe.** Consider shared references, operation ordering, other data, and business invariants.

## 10. Self-Check

**Question 1.** Why can `volatile int count; count++;` still lose increments?  
**Answer:** `++` involves multiple steps and can interleave. `volatile` provides visibility effects for individual reads/writes, not atomicity for the whole read–modify–write.

**Question 2.** What does `new AtomicInteger(3).getAndIncrement()` return? What is the final value?  
**Answer:** Returns 3 (old value); the object holds 4.

**Question 3.** What does `new AtomicLong(7).incrementAndGet()` return?  
**Answer:** 8, which is the new value after the update.

**Question 4.** Why can `if (a.get() < 100) a.incrementAndGet();` exceed 100?  
**Answer:** The condition and increment are two separate operations; multiple threads can both read 99 and both increment. Use a CAS loop to check and update based on the same observed value.

**Question 5.** What does `compareAndSet(10, 20)` returning `false` indicate?  
**Answer:** The value observed during CAS did not match 10, so assigning 20 did not occur. Re-read and decide whether to retry if the algorithm requires it.

**Question 6.** Why shouldn't you call external systems inside the lambda of `updateAndGet`?  
**Answer:** The function may be invoked multiple times due to contention and CAS retries; external effects could be duplicated.

**Question 7.** When should you use `LongAdder` instead of `AtomicLong`?  
**Answer:** When many threads need to accumulate a statistical counter under contention and you do not need atomic snapshot reads or per-update sequence numbers/compare-and-set.

**Question 8.** What does `AtomicLong.incrementAndGet()` on `Long.MAX_VALUE` return?  
**Answer:** `Long.MIN_VALUE` due to integer wraparound; atomicity does not prevent overflow.

**Rule to remember:** `AtomicInteger` and `AtomicLong` provide **atomic operations on a single integer value**, along with the API's corresponding memory effects. They prevent lost updates when the right methods are used, but **do not automatically substitute for multi-variable transactions, compound invariant checks, overflow handling, or thread progress policies**.
