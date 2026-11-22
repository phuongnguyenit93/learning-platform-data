# BigInteger and BigDecimal Are Immutable, Yet Updating Shared References Still Needs Coordination

## 1. Scenario: The Value Is Safe, the Update Can Lose Data

`java.math.BigInteger` and `java.math.BigDecimal` are **immutable** numeric types: once an object is created, its value and representation are never modified by addition, subtraction, multiplication, or division. Operations create a **result object** and return a reference to that result.

~~~java
BigInteger before = new BigInteger("100");
BigInteger after = before.add(BigInteger.ONE);

System.out.println(before); // 100
System.out.println(after);  // 101
~~~

This is a great property when sharing **a value object** across multiple threads: threads can concurrently read and compute on that object without needing locks merely to protect the internal contents of `BigInteger` or `BigDecimal`.

However, there is an important distinction between two operations:

1. **Reading an immutable number:** multiple threads read `BigDecimal price` or `BigInteger constant`, and nobody alters the number's contents.
2. **Updating a shared reference:** multiple threads run `balance = balance.add(delta)` to point the `balance` reference to a new object.

The second case contains a **read → compute → write** sequence. Computing `add()` may be safe, but the entire read–modify–write sequence does not automatically become an *atomic* action.

~~~java
// Illustrative snippet: balance is shared across multiple threads.
balance = balance.add(new BigDecimal("1.00"));
~~~

Suppose both Thread A and Thread B observe `balance = 10.00`:

| Step | Thread A | Thread B | `balance` reference |
|---|---|---|---|
| 1 | Reads value object `10.00` | | `10.00` |
| 2 | | Reads value object `10.00` | `10.00` |
| 3 | Creates new object `11.00` | | `10.00` |
| 4 | | Creates new object `11.00` | `10.00` |
| 5 | Assigns balance = `11.00` | | `11.00` |
| 6 | | Assigns balance = `11.00` | `11.00` |

After two additions, the final value is still only **11.00**, while **12.00** was expected. This is a *lost update*. No `BigDecimal` object was mutated internally; the bug lies in how threads coordinate updates to the **shared reference**.

## 2. Distinguishing Immutability, Visibility, and Atomicity

These three properties solve three different problems:

| Property | Question | What does BigInteger/BigDecimal help with? |
|---|---|---|
| **Immutability** | Can an object's contents be modified after creation? | Yes: arithmetic operations do not mutate operands |
| **Visibility** | When Thread A swaps the reference, does Thread B see the new reference per memory rules? | Immutability itself does not create a happens-before relationship for replacing a shared reference field |
| **Atomicity** | Does the read–compute–write update occur as a single step relative to other threads? | No: must coordinate using locks or atomic operations |

Example:

~~~java
private BigDecimal balance = new BigDecimal("0.00");

// WARNING: if called concurrently from multiple threads, there is no atomicity.
void deposit(BigDecimal delta) {
    balance = balance.add(delta);
}
~~~

You cannot call `BigDecimal` "thread-safe" and conclude this `deposit` method is also thread-safe. Safe use of an immutable object **does not automatically transfer** to the variable or container holding a reference to it.

Similarly, `BigInteger counter = counter.add(BigInteger.ONE)` is not equivalent to `AtomicInteger.incrementAndGet()` merely because `BigInteger` is immutable.

### A final Field Does Not Always Mean Mutable State Is Frozen

~~~java
final BigDecimal taxRate = new BigDecimal("0.10");
// taxRate = new BigDecimal("0.20"); // Does not compile: cannot reassign a final variable.
~~~

A `final BigDecimal` field cannot be reassigned through that field after initialization; combined with `BigDecimal`'s immutability, this is a good pattern for sharing fixed values when the object is properly constructed and published.

However:

~~~java
final AtomicReference<BigDecimal> balance =
        new AtomicReference<>(BigDecimal.ZERO);

balance.set(new BigDecimal("1.00")); // Valid!
~~~

Here `final` only fixes **the reference to the `AtomicReference` object**; it does not lock the state inside `AtomicReference`.

## 3. Why Doesn't volatile Solve Lost Updates?

You might declare:

~~~java
private volatile BigDecimal balance = BigDecimal.ZERO;
~~~

`volatile` ensures that reads and writes of the **reference field** obey visibility/ordering rules defined by the Java Memory Model; with `volatile` operations, a write happens-before subsequent reads in the proper synchronization order. Reading or writing a single reference is also atomic at the reference-access level.

Yet the following statement is still **not atomic**:

~~~java
balance = balance.add(BigDecimal.ONE);
~~~

In effect, it consists of:

~~~java
BigDecimal old = balance;            // volatile read
BigDecimal next = old.add(BigDecimal.ONE); // local computation
balance = next;                      // volatile write
~~~

Two threads can easily read the same `old` and both write equal `next` values. `volatile` helps threads see writes according to the memory model; it **does not lock the three steps into a single transaction**.

When there is only **one writer thread** and multiple threads reading an immutable config/snapshot, a `volatile` field may suffice if the real requirement is simply publishing new values without multi-field invariants. With **multiple threads concurrently updating based on the old value**, a mechanism coordinating the entire read–modify–write sequence is needed.

## 4. Approach 1: synchronized Covering Read–Compute–Write

The clearest solution for an object with shared state is guarding update operations with the same monitor:

~~~java
import java.math.BigDecimal;

public final class SynchronizedBalance {
    private BigDecimal balance = new BigDecimal("0.00");

    public synchronized void deposit(BigDecimal amount) {
        balance = balance.add(amount);
    }

    public synchronized BigDecimal snapshot() {
        return balance;
    }
}
~~~

`synchronized` on the two instance methods locks on the monitor of **the same `SynchronizedBalance` instance**:

- Only one thread can run sections guarded by that monitor at a time.
- A thread calling `deposit` must complete the entire read–compute–write before another thread enters a method guarded by the same lock.
- Acquiring and releasing the monitor establishes the relevant happens-before relationship, allowing reads through the same lock to observe the properly updated state.

`snapshot()` returns an immutable `BigDecimal`. Other threads can hold onto the returned object without fear of internal mutation; however, it is a **snapshot at read time** and does not automatically reflect subsequent deposits.

You can use a `synchronized(lock)` block instead of locking on `this`:

~~~java
private final Object lock = new Object();
private BigInteger total = BigInteger.ZERO;

void add(BigInteger delta) {
    synchronized (lock) {
        total = total.add(delta);
    }
}

BigInteger snapshot() {
    synchronized (lock) {
        return total;
    }
}
~~~

A private lock gives clear control over who can participate in coordination. Crucially, **all read/write paths must participate in the same synchronization rule**: if one method bypasses the lock, the class's consistency guarantees can break.

### When to Choose synchronized?

`synchronized` fits when multiple invariants must be maintained together: checking balance before deducting, adding across multiple fields, or reading a snapshot of related values. It also keeps code easy to understand when the number of operations is modest.

For example, transferring money between two balances stored in **the same object** must update both under an appropriate lock if both must change atomically. Two independent `AtomicReference<BigDecimal>` instances do not automatically form an atomic transaction across both accounts. In systems using a database or multiple processes, Java locks in one JVM also **do not replace** transactions/locking in the shared data store.

## 5. Approach 2: AtomicReference<BigInteger> and CAS

`AtomicReference<T>` holds a reference with atomic operations. Combined with immutable `BigInteger` or `BigDecimal` values, it enables copy-on-write style updates:

~~~java
import java.math.BigInteger;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<BigInteger> counter =
        new AtomicReference<>(BigInteger.ZERO);

counter.updateAndGet(old -> old.add(BigInteger.ONE));
BigInteger result = counter.get();
~~~

`updateAndGet` performs an atomic update with respect to threads sharing that `AtomicReference`. Its logic can be pictured as a **compare-and-set (CAS)** loop:

~~~java
BigInteger previous;
BigInteger next;
do {
    previous = counter.get();
    next = previous.add(BigInteger.ONE);
} while (!counter.compareAndSet(previous, next));
~~~

If another thread changed the reference between `get()` and `compareAndSet()`, CAS fails; the loop reads the new value and recomputes, **without overwriting the other thread's update**.

### Distinguishing AtomicReference Methods

| Method | Semantics |
|---|---|
| `get()` | Reads current reference with atomic variable memory semantics |
| `set(newValue)` | Writes new reference; **does not** protect an external read–modify–write sequence |
| `compareAndSet(expected, update)` | Swaps only if the current reference is `expected` |
| `updateAndGet(operator)` | Evaluates update function and returns **new value** after successful update |
| `getAndUpdate(operator)` | Updates via function and returns **old value** of successful update |
| `accumulateAndGet(value, operator)` | Combines current value and argument via function, returning new value |
| `getAndAccumulate(value, operator)` | Same, but returns old value of successful update |

A very common mistake is writing:

~~~java
AtomicReference<BigDecimal> balance =
        new AtomicReference<>(new BigDecimal("0.00"));

// WRONG when multiple threads update concurrently:
balance.set(balance.get().add(new BigDecimal("1.00")));
~~~

The snippet above is still get → add → set; individually safe `get()` and `set()` **do not make the combination atomic**. Use:

~~~java
BigDecimal delta = new BigDecimal("1.00");
balance.updateAndGet(old -> old.add(delta));
~~~

Only writers obeying the atomic update/CAS discipline preserve the correctness of that update. Another writer calling `set` directly with an old value can break the system's accumulation policy.

### CAS Compares References, Not BigDecimal Values

`compareAndSet` checks reference identity (`==`), **not calling `equals()`** and not using `BigDecimal.compareTo()`:

~~~java
AtomicReference<BigDecimal> ref =
        new AtomicReference<>(new BigDecimal("1.0"));

BigDecimal another = new BigDecimal("1.0");
boolean updated =
        ref.compareAndSet(another, new BigDecimal("2.0"));
// updated == false: another is a different object from the stored one.
~~~

Even though `another.equals(ref.get())` is true at the start of the example, CAS fails because `another` is a different instance. In a CAS loop, the proper way is obtaining `expected` directly from `ref.get()` before attempting the swap. Avoid relying on numeric value equality to determine CAS correctness.

## 6. Very Important: Functions Passed to updateAndGet May Run Multiple Times

At the implementation level, `AtomicReference.updateAndGet` can invoke the update function multiple times when contention occurs. Therefore, the lambda should be a **side-effect-free function**, computing only the new result from its input:

~~~java
AtomicReference<BigDecimal> total =
        new AtomicReference<>(new BigDecimal("0.00"));
BigDecimal price = new BigDecimal("10.25");

// RIGHT: pure computation, performs no side effects.
BigDecimal updated = total.updateAndGet(current -> current.add(price));
~~~

Do not log business events, send emails, call payment APIs, increment external counters, or write to a database inside an update lambda, because that lambda **can be retried**:

~~~java
// AVOID: side effects can occur multiple times under CAS contention.
// total.updateAndGet(current -> {
//     externalPaymentService.charge(price);
//     return current.add(price);
// });
~~~

Important note: this **does not mean** every call to `updateAndGet` commits multiple updates. One successful call updates the value once, whereas the **lambda evaluation** may repeat multiple times. That is why the callback must be side-effect-free and rely solely on the current value and immutable arguments.

In real business workflows, complete the state transition first and then emit events using an appropriate *exactly-once* or idempotency mechanism. If an update requires transactionality with an external system, a CAS in JVM memory is insufficient.

## 7. Complete Example: Reproducing Lost Updates and Fixing with AtomicReference, synchronized

The following program intentionally uses two `CountDownLatch` instances to **force** two threads to read the same value before writing, thereby reproducing lost updates deterministically rather than relying on random timing. Afterward, the program uses `updateAndGet` for `BigInteger` and `BigDecimal`, along with `synchronized` for a balance.

Create `ImmutableNumbersConcurrencyDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public class ImmutableNumbersConcurrencyDemo {
    private static final BigDecimal DELTA = new BigDecimal("0.10");

    static final class SynchronizedWallet {
        private BigDecimal balance = new BigDecimal("0.00");

        public synchronized void deposit(BigDecimal amount) {
            balance = balance.add(amount);
        }

        public synchronized BigDecimal balance() {
            return balance;
        }
    }

    public static void main(String[] args) throws Exception {
        BigInteger original = new BigInteger("100");
        BigInteger computed = original.add(BigInteger.ONE);
        System.out.println("immutable: " + original + " -> " + computed);

        AtomicReference<BigInteger> shared = new AtomicReference<>(BigInteger.ZERO);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);

        Runnable unsafe = () -> {
            BigInteger old = shared.get();
            bothRead.countDown();
            try {
                mayWrite.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            shared.set(old.add(BigInteger.ONE));
        };

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(unsafe);
            Future<?> second = pool.submit(unsafe);
            bothRead.await();
            mayWrite.countDown();
            first.get();
            second.get();
            System.out.println("lost update: " + shared.get());

            shared.set(BigInteger.ZERO);
            Runnable correctCount = () -> {
                for (int i = 0; i < 1_000; i++) {
                    shared.updateAndGet(old -> old.add(BigInteger.ONE));
                }
            };
            first = pool.submit(correctCount);
            second = pool.submit(correctCount);
            first.get();
            second.get();
            System.out.println("atomic count: " + shared.get());

            SynchronizedWallet wallet = new SynchronizedWallet();
            Runnable lockedDeposit = () -> {
                for (int i = 0; i < 100; i++) {
                    wallet.deposit(DELTA);
                }
            };
            first = pool.submit(lockedDeposit);
            second = pool.submit(lockedDeposit);
            first.get();
            second.get();
            System.out.println("locked balance: " + wallet.balance().toPlainString());

            AtomicReference<BigDecimal> atomicBalance =
                    new AtomicReference<>(new BigDecimal("0.00"));
            Runnable atomicDeposit = () -> {
                for (int i = 0; i < 100; i++) {
                    atomicBalance.updateAndGet(old -> old.add(DELTA));
                }
            };
            first = pool.submit(atomicDeposit);
            second = pool.submit(atomicDeposit);
            first.get();
            second.get();
            System.out.println("atomic balance: " +
                    atomicBalance.get().toPlainString());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac ImmutableNumbersConcurrencyDemo.java
java ImmutableNumbersConcurrencyDemo
~~~

**Exact stdout output:**

~~~text
immutable: 100 -> 101
lost update: 1
atomic count: 2000
locked balance: 20.00
atomic balance: 20.00
~~~

Part-by-part explanation:

1. `original` remains unchanged at 100: `add()` creates a new result 101.
2. Both threads read `shared = 0` before being allowed to write; both compute `0 + 1` and call `set(1)`. Even though `shared` is an `AtomicReference`, **splitting the update into get + set** leaves 1 instead of 2.
3. With `updateAndGet(old -> old.add(ONE))`, each thread increments 1,000 times, so the sum is exact at 2,000.
4. `SynchronizedWallet.deposit()` shares a monitor for each `BigDecimal("0.10")` addition. Two threads running 100 times each yield exactly 20.00.
5. `AtomicReference<BigDecimal>.updateAndGet()` creates a new number from the current snapshot and runs CAS; it also yields exactly 20.00.

The `lost update` output is intentionally forced via latches; it does not prove `AtomicReference.set()` is buggy. The bug is using **two separate atomic operations** instead of one atomic update operation. The example also avoids `Thread.sleep` hoping for a race to occur.

Calculations use `BigDecimal("0.10")` constructed from a string for exact decimal representation. Do not use `new BigDecimal(0.1)` in this example because `double 0.1` does not represent decimal one-tenth exactly.

## 8. AtomicReference or synchronized: How to Choose?

| Need | Reasonable approach | Limitations to remember |
|---|---|---|
| Sharing a `BigDecimal` constant among read-only threads | `final` field / proper object publication | No accumulated state to update |
| One writer publishing new numeric snapshots, many read-only readers | `volatile BigDecimal` or `AtomicReference<BigDecimal>` | Does not solve multiple writers doing read–modify–write |
| Multiple writers incrementing a large integer | `AtomicReference<BigInteger>.updateAndGet` or lock | Pure update function, may be re-invoked; high contention costs CAS retries |
| Multiple writers accumulating a decimal value | `AtomicReference<BigDecimal>.updateAndGet` or lock | Pick scale/rounding per business rules |
| Updating multiple fields or checking then changing multiple related values | `synchronized`/`ReentrantLock` or an immutable snapshot swapped atomically | Protect the whole invariant; every access path follows the same protocol |
| Simple `int`/`long` counter | `AtomicInteger`/`AtomicLong`; consider `LongAdder` for statistics | No need for `BigInteger` if range is small; `LongAdder.sum()` is not an atomic snapshot during concurrent writes |
| Transactions spanning multiple JVMs or databases | Appropriate transaction/locking/conditional update at the data store | Locks and atomics in a single JVM do not guarantee cross-process synchronization |

There are no standard `AtomicBigDecimal` or `AtomicBigInteger` classes in `java.util.concurrent.atomic`. `AtomicReference<T>` supports working with such immutable object types.

`AtomicReference` avoids traditional locks, which does not automatically mean it is faster than `synchronized`. The more threads contend, the more CAS attempts can fail and have to recompute `BigDecimal`/`BigInteger` repeatedly, allocating extra objects. For complex updates or multi-field invariants, locks can be simpler and more efficient. Choose for correctness first, then benchmark with real workloads.

## 9. When Updates Depend on Conditions: Check and Change Must Be One Step

Addition is not the only operation that suffers from races. Example withdrawal:

~~~java
// WRONG: get and set are separate; two threads can both pass the check.
if (balance.get().compareTo(withdrawal) >= 0) {
    balance.set(balance.get().subtract(withdrawal));
}
~~~

With `AtomicReference<BigDecimal>`, checking and changing can be placed together inside one conditional update, for example:

~~~java
BigDecimal withdrawal = new BigDecimal("7.00");
AtomicReference<BigDecimal> balance =
        new AtomicReference<>(new BigDecimal("10.00"));

BigDecimal after = balance.updateAndGet(current -> {
    if (current.compareTo(withdrawal) < 0) {
        throw new IllegalStateException("Insufficient funds");
    }
    return current.subtract(withdrawal);
});
~~~

Here the condition is **re-evaluated against the current value** whenever the lambda is re-invoked after a failed CAS. If funds are no longer sufficient on a retry, the operation throws an error rather than overwriting someone else's state.

However, the example above only illustrates a simple policy for **a single in-memory balance variable**. Real business logic also requires checking negative numbers, currency units, `withdrawal` validity, limits, auditing, idempotency, persistence, and handling transfers between accounts. When a transaction must update multiple accounts simultaneously, CAS on individual balances alone is not enough to guarantee atomicity of the entire transaction.

You can combine multiple fields that must stay consistent into one **immutable snapshot**, then use one `AtomicReference` holding the whole snapshot for atomic replacement:

~~~java
record LedgerSnapshot(BigDecimal balance, BigInteger operations) {}

AtomicReference<LedgerSnapshot> state = new AtomicReference<>(
        new LedgerSnapshot(new BigDecimal("0.00"), BigInteger.ZERO));

BigDecimal delta = new BigDecimal("1.00");

state.updateAndGet(old -> new LedgerSnapshot(
        old.balance().add(delta),
        old.operations().add(BigInteger.ONE)
));
~~~

Readers performing a single `state.get()` observe a snapshot containing **both fields from the same version**. Calling `get()` twice with an update in between can read two different versions; hold the snapshot in a local variable when a consistent state is needed. A `record` helps pass immutable data provided every component inside it is also immutable, like the two numeric types in the example.

## 10. Distinguishing an Old Snapshot from a "Mutated Object"

A reader may hold an old reference:

~~~java
AtomicReference<BigDecimal> price =
        new AtomicReference<>(new BigDecimal("12.00"));

BigDecimal snapshot = price.get(); // 12.00
price.set(new BigDecimal("15.00"));

System.out.println(snapshot);   // 12.00
System.out.println(price.get()); // 15.00
~~~

Both values are valid. `snapshot` was not updated because `BigDecimal` is immutable; `price` was simply changed to point to a new number. If an application wants a reader to **always obtain the latest value**, it must re-read the holder at the appropriate time. If it wants to run a business sequence against **the same version**, keep the snapshot locally and read only once at the start of the step, or use a consistent update protocol.

Do not confuse two properties:

- Guaranteeing that the contents of `snapshot` cannot be mutated.
- Guaranteeing that `snapshot` is the latest value or consistent with other fields.

Immutability solves only the first property.

## 11. Thread-Safe BigDecimal Use Does Not Automatically Mean Business Correctness

With `BigDecimal`, there are also **precision, scale, and rounding** requirements independent of synchronization:

~~~java
BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");
BigDecimal total = a.add(b); // exact, value 0.30
~~~

When using `divide` for non-terminating decimal division, Java requires an appropriate rounding mode/`MathContext`. Neither `AtomicReference` nor `synchronized` fixes wrong precision or rounding. Conversely, creating monetary amounts via `new BigDecimal(0.1)` introduces `double` error even if every update is properly locked.

Example of rounding after each addition:

~~~java
BigDecimal delta = new BigDecimal("0.005");
AtomicReference<BigDecimal> total =
        new AtomicReference<>(new BigDecimal("0.00"));

total.updateAndGet(current ->
        current.add(delta).setScale(2, java.math.RoundingMode.HALF_UP));
~~~

This is an intentional **round-per-transaction** rule. If business rules require summing all values exactly and rounding **once at the end**, the result may differ. Before writing an atomic callback, choose the right rounding point; concurrency only ensures consistent application of the policy, it does not choose the policy for you.

When an update lambda re-runs due to contention, it must also avoid reading independently changing external data. Normalize inputs (`delta`, units, conditions) into immutable local variables before entering the lambda, or design a snapshot holding all data that must be read atomically together.

## 12. Testing Concurrency Bugs

For shared reference updates, a single-threaded test can almost never detect lost updates. Useful testing approaches:

1. **Coordinated tests:** use `CountDownLatch` or a coordination mechanism to force two threads to read the same snapshot, then attempt writes; the program in Section 7 does this.
2. **Final-result tests:** two threads incrementing 1,000 times each must yield exactly 2,000; with `BigDecimal("0.10")`, two threads adding 100 times each must yield exactly `20.00` at the chosen scale.
3. **Testing failures and exceptions:** tasks in `ExecutorService.submit` can throw exceptions; call `Future.get()` to catch errors rather than assuming success simply because the thread pool accepted the task.
4. **Testing shutdown and interruption handling:** wait for tasks to complete and release the pool. In production code, set appropriate timeouts and handle interruption by design.
5. **Checking every update path:** if both `updateAndGet` and an unguarded `get + set` path exist, the system can still lose data.

Running many iterations across many threads increases the chance of exposing races, yet **never proves absolutely** that a system has no concurrency bugs. Rely additionally on reasoning about atomicity, happens-before, and access protocols. For performance, measure with an appropriate benchmark rather than treating the timing of one concurrency test run as a conclusion.

## 13. Common Mistakes to Avoid

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| "BigDecimal is immutable, so balance += delta must be thread-safe" | Swapping the reference is read–compute–write and can lose updates | Lock or atomic update |
| Using `volatile` and concluding addition is atomic | `volatile` provides visibility/ordering, not merging three steps | `synchronized` or `AtomicReference.updateAndGet` |
| Calling `ref.set(ref.get().add(x))` | Two separate atomic calls do not form an atomic update | `updateAndGet(old -> old.add(x))` |
| Calling external services inside a CAS lambda | Callback may re-run under contention | Pure lambda; side effects afterward via reliable protocol |
| Using `compareAndSet` with a new object of equal value | CAS checks reference identity | Obtain `expected` from `get()` |
| Protecting writers with a lock while readers skip the lock | Readers can see state outside the defined protocol | Synchronize both read/write paths or publish snapshots properly via volatile/atomic |
| Using two atomic fields and expecting a consistent joint snapshot | Two independent variables do not swap atomically together | Lock or one immutable snapshot inside one `AtomicReference` |
| Assuming a `final AtomicReference` field cannot change numbers | Only the reference to the holder is final | Distinguish field immutability from holder state |
| Believing `AtomicReference` makes math cheaper | CAS contention can recompute and allocate many new numbers | Measure and compare with locks |
| Using `double`/wrong rounding for money | Even with right concurrency, arithmetic can be wrong | Use `BigDecimal` from strings with standard scale/rounding |
| Testing concurrency without awaiting Futures | Can miss task exceptions | Call `Future.get()` and verify final values |
| Treating local `synchronized` as a substitute for database transactions | Only coordinates threads via locks inside one JVM | Use storage-level transactions/locks |

## 14. Self-Check

**Question 1.** Two threads concurrently execute `shared = shared.add(BigInteger.ONE)` where `shared` is a `BigInteger` field. Is it guaranteed to add twice?

**Answer:** No. Each `add()` creates its own immutable result, but both threads can read the same old reference and one update gets overwritten. The read–modify–write must be protected.

**Question 2.** If that field is changed to `volatile BigInteger shared`, is that enough?

**Answer:** Not yet. `volatile` ensures visibility under the Java Memory Model, not making `shared = shared.add(ONE)` a single atomic operation.

**Question 3.** With `AtomicReference<BigDecimal> ref`, does `ref.set(ref.get().add(amount))` fix lost updates?

**Answer:** No; use `ref.updateAndGet(old -> old.add(amount))` or an appropriate lock.

**Question 4.** Why shouldn't you call a payment API inside the lambda of `updateAndGet`?

**Answer:** The update function can be re-invoked when CAS fails; side effects may happen multiple times even though the state update commits once.

**Question 5.** A snapshot containing `balance` and `count` must always belong to the same version. Should you use two separate `AtomicReference` instances?

**Answer:** Two separate atomics do not guarantee a read observes a pair of values from the same version. Use an immutable snapshot object inside one `AtomicReference`, or a lock protecting the entire invariant.

**Question 6.** Thread A holds a `BigDecimal snapshot`, and Thread B updates the holder from `12.00` to `15.00`. Does the value inside the old snapshot change to `15.00`?

**Answer:** No. The old `BigDecimal` object remains immutable. Only the reference inside the holder is replaced with the new object.

**Question 7.** Does `compareAndSet(expected, update)` use `BigDecimal.compareTo()` to check `expected`?

**Answer:** No. It compares **reference identity**; two distinct `BigDecimal` instances with equal numeric values are still not the same expected reference.

---

**Takeaway:** `BigInteger` and `BigDecimal` are safe to share as **immutable values**. Yet updating a **shared reference variable** still requires coordinating read–compute–write steps. Use `synchronized`/locks when guarding invariants or multiple fields; use `AtomicReference.updateAndGet` when the state to update is represented as one immutable snapshot and the update function is pure. Always keep concurrency correctness distinct from precision, scale, and rounding rules.
