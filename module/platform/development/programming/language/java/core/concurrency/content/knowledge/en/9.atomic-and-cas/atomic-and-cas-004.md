# CAS Loops, Retries, and Contention in Java

**Compare-and-set (CAS)** is a conditional atomic update: "replace the current value with a new value only if it still equals the value I expect." In Java, CAS is provided through `AtomicInteger`, `AtomicLong`, `AtomicReference`, other atomic classes, and `VarHandle`. Using CAS, we can build a **retry loop** (*CAS loop*) to update shared state without needing a mutex for every small change.

However, when multiple threads contend for the same variable (*contention*), a CAS loop may have to recompute and retry many times. It can avoid locks in appropriate situations, but it is **not free, not inherently fair, does not guarantee that every thread completes quickly**, and also has pitfalls regarding side effects, ABA, overflow, memory ordering, and placing unbounded retries in requests with deadlines.

This article focuses on **general Java concurrency**, without relying on Spring or framework mechanisms.

## 1. What does CAS actually do?

Suppose `state` is an `AtomicInteger` currently holding `10`:

```java
boolean ok = state.compareAndSet(10, 11);
```

This is a snippet. CAS checks **at the atomic point of execution** whether the current value equals `10`. If so, it updates it to `11` and returns `true`; otherwise, it does not write and returns `false`.

| State before CAS | Operation | Return value | State after CAS |
| --- | --- | --- | --- |
| `10` | `compareAndSet(10, 11)` | `true` | `11` |
| `11` | `compareAndSet(10, 12)` | `false` | `11` |
| `11` | `compareAndSet(11, 12)` | `true` | `12` |

CAS combines **comparing and updating a single location** into one atomic operation. Another snippet that looks equivalent is **not atomic**:

```java
if (state.get() == 10) {
    state.set(11);
}
```

These are two separate method calls. Thread B can modify the state after thread A calls `get()` but before A calls `set()`. You should not call a field "atomic" and assume that every workflow combining atomic methods is automatically atomic.

**Three components of CAS:** the storage location of the state, the observed expected value, and the proposed update value. CAS makes **no** guarantees about a database, a file, a network call, or other fields outside that atomic location.

## 2. Why write a CAS loop?

A CAS operation can legitimately fail when another thread has updated the state first. Instead of giving up, many algorithms retry from a fresh snapshot:

```java
for (;;) {
    int oldValue = state.get();
    int newValue = transform(oldValue);

    if (state.compareAndSet(oldValue, newValue)) {
        return;
    }
    // Old snapshot is no longer valid: re-read and recompute.
}
```

This is an **illustrative snippet**, assuming `state` is an `AtomicInteger`, `transform` is a pure transformation, and the code is inside a `void` method. The sequence:

1. **Read:** read the current state.
2. **Validate/compute:** check invariants and compute the proposed state based on the value just read.
3. **CAS:** attempt the atomic update.
4. **Success:** complete the single update.
5. **Failure:** re-read, re-check the condition, recompute the result, and retry.

A **critical mistake** is reading `oldValue` once outside the loop and reusing that expected value on retries. If the state has changed, the loop may spin forever or apply a stale decision.

### Example: selling available inventory

```java
boolean sellOne(AtomicInteger stock) {
    for (;;) {
        int current = stock.get();
        if (current <= 0) {
            return false;
        }
        if (stock.compareAndSet(current, current - 1)) {
            return true;
        }
    }
}
```

This method snippet requires importing `java.util.concurrent.atomic.AtomicInteger` and placing it inside a class. If two threads both see `stock = 1`, only one `1 -> 0` CAS succeeds. The other thread retries, reads `0`, and returns `false`. **Re-checking the `current <= 0` condition is mandatory**: you cannot blindly attempt to decrement from a stale snapshot.

## 3. A retry is a contention signal, not an exception

Imagine two threads both reading version `7`:

```text
A: read version = 7
B: read version = 7
B: CAS(7 -> 8) succeeds
A: CAS(7 -> 8) fails
A: read version = 8
A: compute a new update
A: CAS(8 -> 9) succeeds
```

When A fails, it may be because B **has made progress**; there is no business exception. In many algorithms, this happens regularly and requires a retry. However, a retry also wastes at least some reads, computations, and CAS attempts.

A strong CAS `compareAndSet` on `AtomicInteger` fails when the expected value does not match the state at the time of the attempt. Note that `AtomicReference.compareAndSet` compares **reference identity**, not `equals`; whether expected equality means identity or value equality depends on the specific API.

**Not every CAS should retry indefinitely.** A low-level method might keep trying until it wins; a request with an SLA may need a retry budget, a deadline, cancellation, and a "busy" result under overload. If the business condition changes (out of stock, state already transitioned), a retry can **terminate with false** without being an error.

## 4. Java 17: a coordinated test to deterministically observe a failed CAS

Counting failed CAS attempts in a small stress test might always yield `0` on a lightly loaded machine because the two workers do not actually collide. To study the mechanism, we intentionally use `CyclicBarrier` to force **both to read the same value `0` before either is allowed to attempt the first CAS**.

Create the file `CASRetryDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CASRetryDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger counter = new AtomicInteger(0);
        AtomicInteger failures = new AtomicInteger(0);
        CyclicBarrier bothRead = new CyclicBarrier(2);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Callable<Void> increment = () -> {
                int attempt = 0;
                for (;;) {
                    int oldValue = counter.get();

                    if (attempt == 0) {
                        bothRead.await(5, TimeUnit.SECONDS);
                    }

                    if (counter.compareAndSet(oldValue, oldValue + 1)) {
                        return null;
                    }

                    failures.incrementAndGet();
                    attempt++;
                }
            };

            Future<Void> first = pool.submit(increment);
            Future<Void> second = pool.submit(increment);

            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);

            System.out.println("counter=" + counter.get());
            System.out.println("failedCAS=" + failures.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac CASRetryDemo.java
java CASRetryDemo
```

Stdout **when both workers reach the barrier and complete before the timeout**:

```text
counter=2
failedCAS=1
```

**Why is this deterministic?** Both workers read `0` before the barrier. One `compareAndSet(0,1)` succeeds; the other's first CAS fails because the state is now `1`. The losing worker counts one failure, re-reads `1`, and succeeds with CAS `1 -> 2`. Who wins first does not affect the result. `Future.get` lets `main` receive worker exceptions and only prints once both finish.

This is a **test that deliberately constructs an interleaving**, not a prediction of average retries under real load. The barrier introduces additional happens-before relationships, so do not use this program to generalize about all JMM outcomes in code without a barrier. The timeout helps the test fail clearly when a participant is missing, rather than guaranteeing every machine will finish strictly within five seconds.

## 5. CAS and `volatile`: visibility is not enough for read–modify–write

Consider:

```java
volatile int count;

void increment() {
    count++;
}
```

as a snippet inside a class. `volatile` gives accesses visibility/ordering semantics, but `count++` is logically a read–modify–write. A can read `0`, B can read `0`, and then both write `1`. Two increments result in only `1`.

`AtomicInteger.incrementAndGet()` solves incrementing with an atomic operation. When you only need to increment or add a number:

```java
AtomicInteger count = new AtomicInteger();
int newValue = count.incrementAndGet();
int beforeAdd = count.getAndAdd(5);
```

This snippet requires importing `AtomicInteger`. Prefer built-in operations rather than writing a manual CAS loop for unconditional addition. A custom CAS loop is useful when **both the condition and the update** must depend on the current state, such as deducting quota only if enough remains.

`AtomicInteger.updateAndGet`, `getAndUpdate`, and `accumulateAndGet` also provide function-based updates. **The function may be evaluated multiple times under contention**, so it must be pure and free of side effects that cannot be safely repeated.

## 6. Where does contention make CAS loops expensive?

**Contention** occurs when multiple threads compete to update a shared state. An atomic variable becomes a **hotspot** when many cores perform read–modify–write operations on it simultaneously.

Forms of cost:

- **Failed CAS:** must re-read the state and recompute the proposed value; if the computation is expensive, total repeated work grows large.
- **Cache coherence:** a cache line must transfer ownership when multiple cores update the same memory location, even when CAS succeeds.
- **Busy-spinning:** continuous retries keep the CPU busy while the worker has not yet produced another successful update.
- **Tail latency:** a worker may lose CAS many times before winning; p95/p99 increases even while average throughput remains high.
- **Starvation:** one thread is repeatedly overtaken by others; CAS does not inherently provide FIFO fairness.
- **False sharing:** two logically independent variables that happen to sit on the same cache line can cause cache coherence traffic; separating hotspots or using appropriate layouts sometimes helps, but you must measure.

More threads **do not necessarily** mean more updates/second. There is a saturation point where CPU, cache, coherence, and memory become the bottleneck. Measure failed attempts/update, throughput, latency, and CPU across writer counts to observe this.

A CAS failure is not always a bad sign: in a well-designed lock-free algorithm, a failure can mean **another thread made progress**. What matters is the failure rate and total cost relative to your throughput/latency goals.

### Do not measure contention by creating more contention

If every CAS failure updates a shared `AtomicLong failedAttempts`, that metric itself can become a hotspot! In benchmarks, consider per-thread counters aggregated after completion; in production systems, use sampling, tracing, or metrics with bounded overhead.

## 7. Lock-free, wait-free, and progress guarantees

Do not use these terms as synonyms for "uses CAS."

| Concept | General guarantee |
| --- | --- |
| **Blocking** | An operation may wait for another thread to release a mutex or finish work |
| **Obstruction-free** | A thread can make progress if it runs in isolation long enough without contention |
| **Lock-free** | The system makes overall progress; an individual thread may have to keep retrying |
| **Wait-free** | Every operation completes within a bounded number of algorithmic steps, even under contention from other threads |

A CAS loop using `AtomicInteger` can be part of a lock-free algorithm, but it **does not automatically make the entire method lock-free** if the body also waits on a latch, performs I/O, or holds a monitor. And lock-free **does not** guarantee that every request wins quickly: one worker can suffer starvation while others keep succeeding.

Progress guarantees must be analyzed at the **whole-algorithm** level, together with assumptions about the scheduler and other work; you cannot conclude them just from seeing `compareAndSet`.

## 8. Java 17: a CAS loop protecting an inventory invariant

Create `CASInventoryExample.java`, where there is only one item and two threads both try to buy it:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CASInventoryExample {
    static class Inventory {
        private final AtomicInteger stock;

        Inventory(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("negative stock");
            }
            this.stock = new AtomicInteger(initial);
        }

        boolean sellOne() {
            for (;;) {
                int current = stock.get();
                if (current == 0) {
                    return false;
                }
                if (stock.compareAndSet(current, current - 1)) {
                    return true;
                }
            }
        }

        int remaining() {
            return stock.get();
        }
    }

    public static void main(String[] args) throws Exception {
        Inventory inventory = new Inventory(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Callable<Boolean> purchase = inventory::sellOne;
            Future<Boolean> first = pool.submit(purchase);
            Future<Boolean> second = pool.submit(purchase);

            int successful =
                    (first.get(5, TimeUnit.SECONDS) ? 1 : 0)
                  + (second.get(5, TimeUnit.SECONDS) ? 1 : 0);

            System.out.println("successful=" + successful);
            System.out.println("remaining=" + inventory.remaining());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac CASInventoryExample.java
java CASInventoryExample
```

Stdout on normal completion:

```text
successful=1
remaining=0
```

Regardless of which thread wins, only one `1 -> 0` CAS succeeds; the other worker reads `0` or retries, sees `0`, and returns `false`. There is no fixed retry count in this example, because the scheduler may let the second worker start after stock is already exhausted.

**The scope of atomicity matters:** this is "inventory within a single JVM," not a complete transaction across inventory, payment, DB, and shipping systems. In-memory CAS does not prevent overselling if multiple independent instances each manage their own counter without coordinating at a shared data source.

## 9. Some broken CAS loop patterns

### 9.1. Retrying with a stale expected value

```java
int old = stock.get();
if (old == 0) return false;

while (!stock.compareAndSet(old, old - 1)) {
    // Bug: old is never refreshed.
}
return true;
```

Snippet inside a `boolean` method. If another thread changes `stock`, the old expected value may never match again, causing an infinite spin loop. Always **re-read the state inside the loop** and re-check the business condition.

### 9.2. Refreshing expected without re-checking the invariant

```java
int old = stock.get();
for (;;) {
    if (stock.compareAndSet(old, old - 1)) {
        return true;
    }
    old = stock.get(); // Missing check for stock > 0.
}
```

This snippet is buggy because it can decrement `0 -> -1`. Refreshing the expected value is necessary but **not sufficient**; each retry must check whether the update is still valid.

### 9.3. Checking a condition on an unsynchronized plain field

```java
if (account.isOpen()) {
    balance.compareAndSet(oldBalance, newBalance);
}
```

If `isOpen()` depends on another state that other threads can modify without coordination, CAS on `balance` **does not** make both the `isOpen` check and the update atomic together. You may need to move all invariants into an **immutable aggregate** updated via a single `AtomicReference`, or use a shared lock/appropriate state machine.

### 9.4. Ignoring overflow

`current + 1` on an `int` can overflow to negative. CAS does not fix arithmetic bugs; when an application requires a counter not to exceed `Integer.MAX_VALUE`, check before each CAS or choose a wider type while still defining valid bounds.

## 10. Side effects in retries: never assume once-only execution

The following code is **business-incorrect**:

```java
for (;;) {
    int previous = balance.get();
    chargeExternalPayment(); // May run multiple times!
    if (balance.compareAndSet(previous, previous - 1)) {
        return;
    }
}
```

This is a snippet, lacking balance checks and standalone setup. If CAS fails because another thread modified `balance`, the loop calls `chargeExternalPayment()` again, potentially charging twice even though only one in-memory update is accepted. If the payment API succeeds but the response is lost, retrying becomes even more complex.

**Rule:** computing the proposed state inside a CAS loop should be a **pure function**, containing no non-idempotent side effects. Moving side effects after CAS also does not automatically provide exactly-once semantics across crashes/network failures; you need transactions, idempotency keys, outboxes, or compensating workflows as appropriate.

With `AtomicInteger.updateAndGet(x -> transform(x))`, `transform` may be invoked multiple times due to contention. Do not place email sending, "success" metric increments, DB writes, or mutations of mutable collaborators inside the update function unless you understand the repeat semantics.

A pure illustrative snippet:

```java
AtomicInteger level = new AtomicInteger(3);
int capped = level.updateAndGet(x -> Math.min(x + 1, 10));
```

The update function only computes from its input, with no external effects. **However**, a "seemingly pure" function that reads a clock or other mutable state may produce a different proposed value on each retry; clearly define the operation's input snapshot and which state is allowed to be re-read.

## 11. ABA: state returns to an old value after intermediate changes

CAS only compares values **at the moment of the CAS**, without inspecting history. For example:

```text
A: read reference = object X
B: X -> Y
B: Y -> X
A: compareAndSet(expected=X, update=Z) succeeds
```

If the application only cares that the current reference is `X`, this may be acceptable. However, a lock-free node/resource algorithm may require that "the node was never removed and re-inserted"; in that case, **ABA** is a bug.

### Java 17: ABA example and version stamps

Create `ABADemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicStampedReference;

public class ABADemo {
    public static void main(String[] args) {
        Object a = new Object();
        Object b = new Object();
        Object c = new Object();

        AtomicReference<Object> plain = new AtomicReference<>(a);
        Object expected = plain.get();

        plain.compareAndSet(a, b);
        plain.compareAndSet(b, a);

        boolean plainAccepted =
                plain.compareAndSet(expected, c);
        System.out.println("plainAccepted=" + plainAccepted);

        AtomicStampedReference<Object> stamped =
                new AtomicStampedReference<>(a, 0);
        Object expectedRef = stamped.getReference();
        int expectedStamp = stamped.getStamp();

        stamped.compareAndSet(a, b, 0, 1);
        stamped.compareAndSet(b, a, 1, 2);

        boolean stampedAccepted =
                stamped.compareAndSet(expectedRef, c,
                                      expectedStamp, expectedStamp + 1);
        System.out.println("stampedAccepted=" + stampedAccepted);
        System.out.println("currentStamp=" + stamped.getStamp());
    }
}
```

```bash
javac ABADemo.java
java ABADemo
```

Stdout:

```text
plainAccepted=true
stampedAccepted=false
currentStamp=2
```

The example runs sequentially to simulate a concurrent schedule, so its output is deterministic. `AtomicReference` compares references by identity: object `a` returned to the **exact same instance**, so the plain reference CAS accepts it. `AtomicStampedReference` checks both reference and version simultaneously: the state went through `stamp 0 -> 1 -> 2`, so the stale expected stamp `0` is rejected.

Stamps do not solve everything on their own: a finite version can wrap or be reused without disciplined design, and memory/node reclamation in lock-free algorithms still requires separate analysis.

## 12. Strong CAS, weak CAS, and memory ordering

`AtomicInteger.compareAndSet` is a strong CAS per the API contract. Some **weak CAS** variants such as `weakCompareAndSetPlain` are allowed **spurious failure**: returning `false` even when the expected value matches the state. Methods suffixed with `Plain`, `Acquire`, `Release`, and volatile forms also differ in **memory-order semantics**.

Key points to remember:

- With strong `compareAndSet`, if expected no longer matches, the operation fails. Occasional failures are normal under contention.
- With weak CAS, the loop must tolerate failures even when there is no concurrent modification.
- Do not switch to `weakCompareAndSetPlain` just to be "faster" if your algorithm relies on volatile publication/happens-before without analyzing it.
- `VarHandle.compareAndExchange` returns the **witness value** (the observed value), unlike `compareAndSet` which returns a `boolean`. Read each API's contract before using it.
- Do not assume weak CAS is better than strong CAS on every CPU/JDK; microbenchmark with realistic workloads when optimizing.

CAS on `AtomicInteger` has defined memory effects; the default operation corresponds to appropriate semantics for atomic/volatile access. However, **atomicity and visibility do not combine all other mutable objects into a transaction**. If an atomic reference points to a mutable object and another thread modifies fields inside it, a reference CAS does not protect those inner fields.

## 13. Backoff, spinning, and `Thread.onSpinWait()`

Under light contention, retrying immediately after a CAS failure is usually simple. Under heavy contention, dozens of workers spinning on one address can drive up CPU, cache coherence traffic, and tail latency.

### Spin hint

Java 9+ supports:

```java
int retries = 0;
for (;;) {
    int old = value.get();
    if (value.compareAndSet(old, old + 1)) {
        break;
    }
    retries++;
    if (retries > 16) {
        Thread.onSpinWait();
    }
}
```

This is a snippet with `value` of type `AtomicInteger`. `Thread.onSpinWait()` is a **hint to the JVM/CPU**, not a fair yield, does not create a timeout, and does not replace a lock/condition. It can help some spin-loops, but it still consumes CPU.

### Backoff

Common strategies:

| Strategy | Pros | Cons |
| --- | --- | --- |
| Continuous retry | Low latency under low contention | Hot CPU/cache with many writers |
| Fixed pause | Easy to set a threshold | May delay unnecessarily when contention drops |
| Exponential backoff | Reduces retry frequency on consecutive failures | High latency if it grows too large |
| Random jitter | Prevents many threads from waking up in lockstep | Increases latency variance and is hard to prove fair |
| Partition/shard state | Reduces the source of contention | Increases aggregation/consistency complexity |

`LockSupport.parkNanos(...)` can park briefly, but **does not guarantee sleeping for the exact number of nanoseconds**: it can return early due to interrupts/unparks/spurious returns, and the scheduler affects timing. Backoff also **does not** provide strict fairness.

### Illustrative pseudocode with backoff

```java
long pause = 1_000L;
for (;;) {
    int old = value.get();
    int next = transform(old);

    if (value.compareAndSet(old, next)) {
        return;
    }
    java.util.concurrent.locks.LockSupport.parkNanos(pause);
    pause = Math.min(pause * 2, 1_000_000L);
}
```

This snippet assumes `value`, `transform`, and a `void` method; it **does not handle cancellation, deadlines, overflow, or business side effects**. Do not use it verbatim in production request paths. Choose backoff via measurements and semantics; do not apply a single "standard" pause across all applications.

## 14. Bounded and cancellable CAS loops

An unbounded retry loop may be suitable inside a low-level atomic class, but on a request path with an SLA you need a clear contract:

- **Success:** CAS succeeded and the invariant was applied.
- **Conditional rejection:** the new state no longer satisfies the condition (for example, `stock = 0`).
- **Busy/timeout:** retries exceeded the budget/deadline without updating.
- **Cancellation:** the thread was requested to cancel; a CPU-bound CAS loop does not throw `InterruptedException` on its own.
- **Uncertain external side effect state:** never guess "it didn't happen" just because an HTTP response was lost; use idempotency/transactions.

Snippet limiting the number of attempts:

```java
boolean tryIncrement(AtomicInteger value, int maxAttempts) {
    if (maxAttempts < 1) {
        throw new IllegalArgumentException("maxAttempts");
    }

    for (int n = 0; n < maxAttempts; n++) {
        if (Thread.currentThread().isInterrupted()) {
            return false;
        }

        int current = value.get();
        if (value.compareAndSet(current, current + 1)) {
            return true;
        }

        Thread.onSpinWait();
    }
    return false;
}
```

This is a snippet inside a class, importing `AtomicInteger`. `false` means **not updated**, which could be due to cancellation or too many CAS failures; if the API needs to distinguish those two cases, return an enum/result instead of a `boolean`. Check for overflow before CAS if the invariant does not allow wrapping. Limiting attempts **does not guarantee a fixed wall-clock duration** because the scheduler can pause a thread at any time.

### When retry backoff hurts throughput

Under low contention, each `parkNanos` call adds overhead and can perform worse than direct retries. Under high contention, backoff can help avoid a "thundering herd." The sweet spot depends on CPU, JVM, access patterns, core count, and the cost of computing the proposed state. Without measuring, you cannot conclude.

## 15. `AtomicLong` or `LongAdder` under many writers?

If the application only counts events, there are two typical choices:

- `AtomicLong.incrementAndGet()`: linearizable operation on a single variable; you can read the exact value according to atomic operation semantics.
- `LongAdder.increment()`: spreads updates across multiple internal cells under contention to increase throughput in some workloads. `LongAdder.sum()` **is not an atomic snapshot with respect to concurrent updates**.

Therefore, `LongAdder` fits **metrics/statistics** where a total without a single linearization point at read time is acceptable; it is **not** suitable as a replacement for `AtomicLong` in "if balance > 0 then deduct" or "allow at most N reservations" where an atomic decision is required.

Do not automatically choose `LongAdder` for a low-writer counter; memory usage and aggregation cost can be higher. Benchmark the actual workload.

## 16. Immutable snapshot + CAS for multiple related fields

If state consists of `version` and `stock`, updating two separate `AtomicInteger` fields does not automatically form an atomic snapshot. You can wrap them in an **immutable aggregate** and use an `AtomicReference` CAS on the whole reference:

```java
record Snapshot(int version, int stock) {}

AtomicReference<Snapshot> current =
        new AtomicReference<>(new Snapshot(0, 5));

for (;;) {
    Snapshot old = current.get();
    if (old.stock() == 0) {
        break;
    }

    Snapshot next =
            new Snapshot(old.version() + 1, old.stock() - 1);

    if (current.compareAndSet(old, next)) {
        break;
    }
}
```

This Java 17 snippet requires importing `AtomicReference` and placing it in an appropriate method. Each reader fetching **one reference** observes `version` and `stock` from the same snapshot. When CAS fails, the writer must construct a new snapshot from the updated value. The record holds two primitives, so this snapshot itself is immutable.

If a snapshot contains a `List<MutableItem>`, a record does not deep-copy elements automatically; you must design immutable values/ownership properly. If multiple writers have side effects outside this state, a reference CAS also does not make the whole workflow atomic across multiple systems.

## 17. Benchmarking and diagnosing contention

Do not use a single measurement on a personal machine to conclude that `compareAndSet` is "faster than `synchronized`" in all cases. JIT warmup, GC, false sharing, CPU architecture, cache-line layout, number of cores, and transform cost all affect results.

| Metric | What question does it answer? |
| --- | --- |
| Successful updates/s | Does actual throughput scale as writers are added? |
| Attempts per success | How many attempts does one update take on average? |
| Failure ratio | What fraction of total attempts fail? |
| Latency p50/p95/p99 | Does tail latency degrade under contention? |
| CPU utilization | Is busy-spinning consuming excessive CPU? |
| Fairness per worker | Is any worker repeatedly prevented from completing? |
| Coherence/cache metrics | Is there a hotspot or false sharing? |
| Correctness/invariant | Are there lost updates, negative stock, or repeated side effects? |

**JMH** handles warmup, forking, measurement, and avoids common microbenchmark pitfalls; use it to compare operations with the **same semantics** across multiple thread counts and representative workloads. Combine it with JFR/CPU profiling, stress tests, and system load tests. The first goal is **preserving invariants**, and only then optimizing.

When benchmarking CAS loops, be careful not to place an atomic failure counter on the contended hotspot itself; instrumentation can skew the results. Count locally per worker or use appropriate profiling tools and aggregate afterward.

## 18. ABA is not the only challenge in lock-free structures

For a custom stack/queue built with CAS, many questions go beyond the primitive itself:

- **Node lifecycle:** can a node be reused or removed and re-inserted while another thread still holds an old reference?
- **Memory visibility:** when publishing a new node, are its initialized fields guaranteed to be observed properly by readers?
- **Invariants on retry:** if updating a pointer fails, must the entire observed node chain be re-read?
- **Progress:** can any thread starve; if a worker fails/stalls, can other threads still make progress?
- **Memory reclamation:** removing a node does not mean it can be safely reused immediately in every algorithm; the JVM GC manages physical memory, but does not solve all logical ABA/node-reuse issues.
- **Exception/cancellation:** if computing the proposed state throws an exception, does the state remain valid?
- **Fairness:** if a thread has to retry indefinitely under high contention, what should the service-level response do?

Unless you have a specialized need, prefer battle-tested structures in `java.util.concurrent` over rolling your own lock-free queue/stack. A small atomic CAS is a safe primitive; proving a complete lock-free algorithm is much harder.

## 19. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Retrying forever with a stale expected value | Infinite spin or no progress | Re-read fresh state on every iteration |
| Updating from an old snapshot | Overwrites or broken logic | Re-evaluate predicate and proposed state |
| Treating `get` + `set` as CAS | Interleaved check–then–act race | Use CAS or an appropriate atomic operation |
| Using `volatile count++` | Lost updates | Use `incrementAndGet` or a proper CAS |
| Putting I/O or side effects inside retries | May execute multiple times | Separate effects; use transactions/idempotency |
| Non-pure callback in `updateAndGet` | Repeated side effects | Pure function, safe to re-evaluate |
| Ignoring ABA when versions matter | CAS accepts A→B→A | Use version/stamp/ownership as appropriate |
| Confusing weak CAS with strong CAS | Wrong assumptions on spurious failure/memory ordering | Read the exact method contract |
| Calling every CAS loop wait-free | Masks starvation | Analyze progress for the whole algorithm |
| Spinning forever in deadline-bound requests | High CPU, unbounded latency | Use retry budget/deadline/cancellation |
| Always adding backoff | Adds latency under light contention | Benchmark and tune to load |
| One CAS on one field for multi-field invariants | Inconsistent snapshots | Immutable aggregate + CAS or mutex |
| `LongAdder.sum()` instead of atomic balance | Not an atomic snapshot | Use a sufficiently strong atomic operation |
| Treating JVM CAS as a DB transaction | Overselling across processes | Coordinate at the data source/transaction |
| Instrumentation using a shared atomic hotspot | Measurement increases contention | Per-thread metrics/sampling |
| Forgetting integer overflow | Incorrect counter/quota | Check bounds on every iteration |
| Testing only one schedule | Misses rare concurrency bugs | Stress tests + coordinated tests + JMM reasoning |

## 20. Choosing a design by scenario

**Low-writer counter needing exact per-operation values:** built-in `AtomicInteger`/`AtomicLong` methods; no need for a manual CAS loop.

**Statistics counter with very many writers:** consider `LongAdder`, if a non-atomic `sum` under concurrent updates is acceptable.

**In-JVM quota:** CAS loop with check-and-decrement; after each failure, re-read the quota and decide whether it is still allowed.

**Immutable configuration:** publish snapshots via `volatile`/`AtomicReference`; if multiple writers base updates on an old version, CAS can prevent lost updates.

**Business operation spanning multiple fields or external resources:** consider `synchronized`, `ReentrantLock`, transactions, queues/ownership, and idempotency. A CAS on a flag variable does not protect all resources.

**Excessive contention:** measure retry ratio and tail latency; consider sharding state, batching, `LongAdder` when semantics fit, or a measured backoff strategy. Do not add more threads hoping to "go faster" if the hotspot is already saturated.

## 21. Self-check questions

**1. Is a CAS failure an error?** Not by default. For strong CAS, it usually just means expected did not match because the state changed; the algorithm can retry or return a different business result.

**2. After a CAS failure, can you keep the same expected value and just re-run `compareAndSet`?** No. You must re-read and recompute the proposed state; if the condition no longer holds, stop legitimately.

**3. Does `AtomicInteger` turn `get` followed by `set` into a transaction?** No. You must use an atomic operation for the entire logic that needs atomicity, or a proper CAS loop.

**4. Does a worker repeatedly losing CAS contradict lock-free?** No. Lock-free guarantees overall system progress; wait-free is what requires a stronger per-operation bound.

**5. Why shouldn't you send an email inside `updateAndGet(x -> ...)`?** The function can be called multiple times if the internal CAS retries, duplicating the side effect.

**6. Can `LongAdder` replace `AtomicLong` for inventory?** You should not: `sum()` is not an atomic snapshot with concurrent updates, so it is insufficient for a business-critical check-and-decrement decision.

**7. Does `onSpinWait` guarantee yielding the CPU or sleeping for a set time?** No; it is only a performance hint. Backoff has different timing policies and also does not guarantee fairness.

**8. What is ABA?** State changes from A to B and back to A; a CAS checking expected=A can succeed even though the history changed. When version history matters, use a stamp or appropriate structure.

**9. Does a CAS loop automatically protect a mutable object stored inside `AtomicReference`?** No. It protects swapping the reference per its contract; inner data may require immutable design or ownership rules.

**10. Does a test with deterministic `failedCAS=1` output prove retries are always 1 in production?** No. That interleaving was deliberately constructed with a barrier; real behavior depends on scheduling and contention.

**11. Are `compareAndSet` and `weakCompareAndSetPlain` interchangeable?** Not automatically: weak CAS can fail spuriously and memory-order semantics may differ.

**12. Is there a way to guarantee a CAS retry always finishes within 5 ms?** Not with the primitive alone. You need deadline/cancellation semantics, workload control, and scheduler considerations; a timer does not automatically make updates succeed.

## 22. Implementation checklist

1. Identify **state and invariants**; only use CAS if a single atomic cell/reference can express the condition to preserve.
2. Use standard atomic APIs first; do not write a manual loop for `incrementAndGet` without a new requirement.
3. On each retry: **re-read → re-validate → recompute → CAS**.
4. Keep update functions **pure**; do not put I/O or non-idempotent side effects inside retries.
5. Distinguish **CAS success**, condition failure, retry budget exhausted, and cancellation.
6. Check for **overflow**, value/reference identity, and **ABA** if state has a version/lifetime.
7. Understand strong/weak CAS along with memory-order semantics under the JMM.
8. Do not label an entire algorithm "lock-free/wait-free" just because it uses CAS.
9. Measure throughput, retry ratio, CPU, p95/p99, and starvation as contention grows.
10. Consider backoff, sharding, batching, `LongAdder`, or locks/immutable state as needed; choose based on measurements.
11. Do not infer atomicity across DB/HTTP/processes from CAS within a single JVM.
12. Test with targeted thread interleavings and stress tests, while basing correctness arguments on the Java Memory Model contract.

**Takeaway:** CAS is **optimistic concurrency**: it updates only when the snapshot is still valid. On failure, you must **re-read, recompute, and re-check the business condition**. CAS helps avoid mutexes for some simple states, but contention can make retries burn CPU and increase latency; good design combines atomicity, liveness, memory semantics, pure retry logic, and measurements on real workloads.
