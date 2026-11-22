# 9.7. weakCompareAndSet, spurious failure, and retry conditions

## Learning Objectives

After this lesson, you will be able to:

1. Explain **compare-and-set (CAS)** and the difference between `VarHandle.compareAndSet` and `VarHandle.weakCompareAndSet`.
2. Accurately describe **spurious failure**: a weak CAS call can return `false` even when the actual value at the time of comparison matches `expectedValue`.
3. Write a **read → compute new value → weak CAS → if failed, re-read and recompute** loop, ensuring no lost updates across multiple threads.
4. Recognize situations where **you should not retry**, stopping conditions, starvation/livelock risks, backoff, and the limited effect of `Thread.onSpinWait()`.
5. Choose the right memory ordering variant: `weakCompareAndSet`, `weakCompareAndSetPlain`, `weakCompareAndSetAcquire`, `weakCompareAndSetRelease`; avoid confusing it with the similarly named API in `AtomicInteger`.
6. Distinguish `VarHandle` access/type errors from a normal `false` result of CAS, and understand the limits of testing spurious failure on real hardware.

**Context:** `VarHandle` in `java.lang.invoke` is a strongly typed handle to a variable: an instance field, static field, or array element. It supports read/write modes and atomic updates, with different memory effects. Weak CAS is often used in concurrent algorithms with a retry loop, where a single failure is not necessarily the final outcome.

## 1. What is CAS and why must we compare before writing?

Suppose a shared variable `counter` has the value `10`. Two threads both want to increment it by `1`. The naive approach:

```java
int old = counter.value;
counter.value = old + 1;
```

This is only an illustrative snippet, **not an atomic operation**. Both threads might read `10` and both write `11`; one increment is lost (*lost update*).

CAS performs a conditional update at a single atomic point:

```text
CAS(variable, expectedValue, newValue):
    If the current value of variable matches expectedValue:
        atomically update to newValue
        return true
    If it does not match:
        do not update
        return false
```

On `VarHandle`, the logical signature for an instance field of type `int` is:

```java
boolean success = VALUE.compareAndSet(holder, expectedValue, newValue);
```

This is an illustrative line: `VALUE` must be a VarHandle to an `int` field of `holder`; the arguments must have the exact types at the call site. For an array element, you must also pass the array and index in the coordinate arguments, for example `ARRAY_HANDLE.compareAndSet(array, i, expectedValue, newValue)`.

**Benefit of CAS:** a thread only writes if the condition based on the old snapshot still holds at the time CAS executes. When another thread has already changed the variable, an update using the stale snapshot will fail, allowing the application to re-read instead of overwriting the other thread's progress.

## 2. How do strong CAS and weak CAS differ?

### 2.1. `compareAndSet` (strong CAS)

`VarHandle.compareAndSet(...)` atomically updates if the witness value matches `expectedValue`. By API contract, when it returns `false`, the witness value **did not match** expected. Strong CAS **is not allowed to fail spuriously** according to this method's semantics.

That does **not** mean the call always succeeds; in a multi-threaded system, the value can be changed by another thread between the earlier read and the CAS operation.

### 2.2. `weakCompareAndSet` (weak CAS)

`VarHandle.weakCompareAndSet(...)` also performs an **atomic update when it succeeds** and returns a boolean. However, the API allows it to **return `false` even when the witness value matches expected**. This is spurious failure. When weak CAS fails, that call does not perform the intended write; however, other threads may have already modified the variable.

| Criterion | `compareAndSet` | `weakCompareAndSet` |
| --- | --- | --- |
| Atomic write if successful | Yes | Yes |
| Returns `true` | This call's update succeeded | This call's update succeeded |
| Returns `false` when current differs from expected | Yes | Yes |
| Allowed to return `false` when current still equals expected | **No** | **Yes: spurious failure** |
| Can be used once to assert "expected did not match"? | Yes, for the witness value at CAS time | **No** |
| Suitable for a re-read/recompute/retry loop | Yes | Yes, and **must account for spurious failure** |
| Memory effects of the unsuffixed method on `VarHandle` | Volatile read/write | Volatile read/write |

A successful weak CAS is not a "weak write, maybe not written". **Success still guarantees the conditional update is atomic**. "Weak" mainly refers to **being allowed to fail spuriously**, not permission to do a partial update or return `true` without doing anything.

### 2.3. Returning `false` is not an exception

If `weakCompareAndSet(...)` returns `false`, that is an **expected outcome under the API contract**, not an `IllegalStateException`. Therefore, you should not treat every `false` as a system error or immediately throw an exception. Conversely, `WrongMethodTypeException` or `UnsupportedOperationException` when calling a VarHandle is usually an error in how the handle is used, not "a CAS attempt that didn't win" to be retried infinitely.

## 3. What is spurious failure?

For example, the shared variable is currently `7`, and the caller tries:

```java
boolean updated = VALUE.weakCompareAndSet(holder, 7, 8);
```

Two kinds of situations make `updated == false`:

1. **Expected mismatch:** at the time of comparison, the value is already `9` (another thread updated it), no longer `7`.
2. **Spurious failure:** the witness value is still `7`, but the **weak** CAS operation is allowed to report failure without performing the write.

The caller **cannot** tell from a single boolean `false` which cause occurred. There is no API returning an accompanying flag saying "this was a spurious failure". If you need to know the current value, you must perform an appropriate read; even the value read afterward may have already changed, so it is usually impossible to reconstruct the exact history of the earlier CAS.

### 3.1. Why does the API allow spurious failure?

On some architectures/implementations, low-level synchronization primitives can report failure under contention or when a load-reserved/store-conditional instruction pair fails to maintain an internal condition. Weak CAS allows implementations to take advantage of that style of operation without forcing the library layer to hide every failure with a retry.

This is a **contractual permission to fail spuriously**, not a guarantee that every JVM or every machine will produce spurious failures. On many machines, trying millions of times may still never show one. You must not write unit tests that require observing a spurious failure to consider an implementation correct.

### 3.2. Do not infer "there is contention" solely from `false`

Even when only a single thread touches the variable, weak CAS **is still allowed** to return `false`. Conversely, when multiple threads contend, a CAS attempt can succeed. Therefore:

- `false` does not prove another thread just wrote;
- `false` does not prove a memory ordering bug;
- `true` proves the caller's conditional update succeeded, but **does not guarantee the value remains unchanged at a subsequent read**, because another thread can update it next.

## 4. Correct retry pattern: re-read and recompute the new value

A loop that increments an `int` variable using weak CAS:

```java
static void increment(Holder holder) {
    for (;;) {
        int observed = (int) VALUE.getVolatile(holder);
        int next = observed + 1;

        if (VALUE.weakCompareAndSet(holder, observed, next)) {
            return;
        }

        Thread.onSpinWait();
    }
}
```

This is an **illustrative method**, which must be placed in a class with `Holder` and `VALUE` looked up for the appropriate field. Section 7 has a standalone runnable program.

Execution flow:

1. **Read:** read the current value using an appropriate access mode, here `getVolatile`.
2. **Compute:** compute the proposed value from the snapshot just read.
3. **Attempt:** `weakCompareAndSet(holder, observed, next)`.
4. **Success:** if `true`, the increment operation for **this call** has been performed; return.
5. **Failure:** if `false`, do not conclude why; go back to the **read** step and recompute.

Why must we re-read? Suppose thread A read `10`, while thread B updated the variable to `11`. If A keeps trying `weakCompareAndSet(holder, 10, 11)` without changing expected, it will keep failing as long as the variable does not return to `10`. A's correct update must read `11`, then propose `12`.

### 4.1. Wrong loop: keeping the old expected forever

```java
int expected = (int) VALUE.getVolatile(holder);
while (!VALUE.weakCompareAndSet(holder, expected, expected + 1)) {
    // WRONG: expected does not change; if the actual value has changed, this can loop infinitely.
}
```

The snippet above **is not a standalone program**, it only illustrates the bug. Retrying with the exact same values can only be useful in a very special case when there is **proof that no thread changes the state and retrying is still valid**, which is usually not true for contended read-modify-write problems. You cannot write a general algorithm based on that assumption.

### 4.2. Wrong loop: ignoring `false`

```java
int snapshot = (int) VALUE.getVolatile(holder);
VALUE.weakCompareAndSet(holder, snapshot, snapshot + 1);
// WRONG if the requirement is to complete one increment: false is ignored.
```

For business logic requiring "every accepted request must increment exactly once", ignoring the result can cause lost updates, even when there is no actual contention (due to spurious failure).

### 4.3. Wrong loop: falling back to direct `set` after failure

```java
int old = (int) VALUE.getVolatile(holder);
if (!VALUE.weakCompareAndSet(holder, old, old + 1)) {
    VALUE.setVolatile(holder, old + 1); // WRONG: may overwrite another thread's update.
}
```

`setVolatile` is a volatile write, **not** a conditional read-modify-write. It does not check whether the old value still holds. The right pattern is to re-read and retry CAS, or switch to an appropriate atomic-update primitive such as `getAndAdd`.

## 5. When is it okay to retry, and when must we stop?

You should not spin indefinitely just because you see `false`. You must base the decision on the **business goal** and the **correctness of the update**.

| Case | Appropriate action |
| --- | --- |
| Incrementing a counter using an old snapshot | Re-read the value; compute the new incremented value; retry CAS |
| Conditional state update "only if state is still OPEN" | Re-read; if state is not OPEN, **stop per contract**, do not force it back |
| An optional/best-effort update | May record failure without retrying, **if** the contract allows it and understands `false` can be spurious |
| Every request must be recorded once | Retry safely or choose a stronger atomic API; **do not ignore `false`** |
| There is cancellation, a deadline, or a retry budget | Check stopping conditions and return an error / mark incomplete / fall back appropriately |
| The loop performs external side effects | Do not repeat side effects alongside CAS; separate pure state computation from I/O or non-idempotent actions |

### 5.1. Re-checking the business condition

For example, a requirement "only transition `OPEN -> CLAIMED`", where `OPEN=0` and `CLAIMED=1`:

```java
static boolean claim(Job job) {
    for (;;) {
        int state = (int) STATE.getVolatile(job);
        if (state != 0) {
            return false; // State is no longer OPEN: do not retry to overwrite.
        }
        if (STATE.weakCompareAndSet(job, 0, 1)) {
            return true;
        }
        Thread.onSpinWait(); // May be a spurious failure: re-read and try again.
    }
}
```

This is an **illustrative method** with corresponding `Job` and `STATE`, not a standalone Java file. After `false`, you must go back to checking state. If state transitioned to `CANCELLED`, claiming is no longer valid; you must not keep retrying to "force a success".

**Subtle point:** `return false` in this example means **business-wise it could not be claimed because the state is no longer OPEN**, not that a single weak CAS call returned `false`. These two booleans have different semantics.

### 5.2. Do not repeat I/O or unsafe side effects

Do not write:

```java
for (;;) {
    int old = (int) VALUE.getVolatile(holder);
    sendPayment(); // WRONG: may run multiple times when weak CAS fails.
    if (VALUE.weakCompareAndSet(holder, old, old + 1)) {
        break;
    }
}
```

This is only a **counterexample**. The `sendPayment()` function represents an external side effect; it does not exist in a complete program. Weak CAS can fail due to contention **or** spurious failure; calling payment again would duplicate it. Instead, use CAS to **win the right to execute** first, ensuring consistent state; the side effect is managed using an idempotency key, transaction/outbox, or a reliable mechanism depending on requirements.

### 5.3. Progress and loop bounds

Weak CAS **does not guarantee** that retrying will always succeed after a fixed number of attempts. At the contract level, consecutive spurious failures can occur. Under heavy contention, a thread may repeatedly lose to other threads; you should not claim "every thread is guaranteed to succeed" just because CAS is used.

- **Safety:** every time `weakCompareAndSet` returns `true`, it atomically updated matching expected.
- **Liveness:** the ability to **eventually** reach `true` depends on system progress, contention, scheduling, and the surrounding algorithm. Do not infer fairness or wait-freedom from safety.
- If the caller has a deadline, consider bounding the retry count, timeout, or fallback. When exiting the loop without succeeding, you **must** return an incomplete status; never fake success.

`Thread.onSpinWait()` (Java 9+) is a *hint* to the runtime/CPU while spinning. It **does not** sleep for a fixed duration, **does not** guarantee yielding the CPU, **does not** make CAS stronger, and **cannot** replace a proper backoff/blocking algorithm. If waiting long or under heavy contention, consider bounded backoff, `Thread.yield()`/`LockSupport.parkNanos(...)`, or another synchronization primitive after measuring; do not add random delays without a reason.

## 6. Memory ordering: do not look only at the word "weak"

`VarHandle` separates two axes:

1. **Weak or strong CAS:** is spurious failure allowed?
2. **Memory ordering:** read/write with Plain, Acquire, Release, or Volatile effects?

In Java SE 17, the weak CAS variants are:

| `VarHandle` access mode | Witness read effect | Write effect when CAS succeeds | Can fail spuriously? |
| --- | --- | --- | --- |
| `weakCompareAndSetPlain` | Similar to `get` (plain) | Similar to `set` (plain) | Yes |
| `weakCompareAndSetAcquire` | Similar to `getAcquire` | Similar to `set` (plain) | Yes |
| `weakCompareAndSetRelease` | Similar to `get` (plain) | Similar to `setRelease` | Yes |
| `weakCompareAndSet` | Similar to `getVolatile` | Similar to `setVolatile` | Yes |
| `compareAndSet` | Similar to `getVolatile` | Similar to `setVolatile` | **No** |

The table describes **memory effects according to the VarHandle specification**, which does not mean Java executes the operation as two separate `get` and `set` calls: a successful CAS is still an **atomic** update.

### 6.1. Why does the main example use `getVolatile` and `weakCompareAndSet`?

A counter accessed by multiple threads needs clear sharing semantics. The main pattern uses `getVolatile` to read the snapshot and `weakCompareAndSet` (volatile semantics) to attempt an atomic write. That pattern is simple to learn and does not depend on a weaker publication protocol.

You can optimize with Acquire/Release/Plain access modes **only when** the JMM design for all shared data has been proven correct. Changing `weakCompareAndSet` to `weakCompareAndSetPlain` in an algorithm that already uses volatile for thread coordination can **weaken memory ordering** and create hard-to-reproduce bugs. Just because it is still an atomic CAS does not mean it automatically guarantees publication/visibility of all related data.

### 6.2. Acquire/Release is not the same as full Volatile

- **Acquire** on the read side helps constrain subsequent accesses with a matching Release publication.
- **Release** on the write side helps place prior accesses into an appropriate ordering relationship when the receiving side uses Acquire.
- **Plain** does not provide the corresponding cross-thread ordering constraints.
- **Volatile** provides stronger semantics, including JMM ordering guarantees for volatile accesses.

A successful **Release** CAS does not by itself allow the caller to assume it also has Acquire semantics on the read side. Conversely, an **Acquire** CAS does not by itself provide Release semantics for the write step. Do not mix modes based only on method names; you must clearly identify which data is published, which threads consume it, and the required happens-before relationships.

### 6.3. Special note: `AtomicInteger.weakCompareAndSet` DIFFERS from `VarHandle.weakCompareAndSet`

This is an important API trap in Java 17:

- `VarHandle.weakCompareAndSet(...)`: **volatile** memory effects per the `VarHandle` specification.
- `AtomicInteger.weakCompareAndSet(expected, update)`: the old-named method has been **deprecated since Java 9** because it has **plain** memory effects while its name easily misleads readers into thinking it is volatile.
- In `AtomicInteger`, the explicit names are `weakCompareAndSetPlain`, `weakCompareAndSetAcquire`, `weakCompareAndSetRelease`, and `weakCompareAndSetVolatile`.
- Do not copy the note "weakCompareAndSet has plain semantics" from `AtomicInteger` and apply it to `VarHandle.weakCompareAndSet`.

This distinction is essential when porting code between the two APIs or auditing an algorithm's memory ordering effects. Despite similar names, **each specific method's contract is the source of truth**.

## 7. Complete Java 17+ program: concurrent weak CAS with retry

Create the file **`WeakCasGuide.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class WeakCasGuide {
    static final class Counter {
        volatile int value;
    }

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                    Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    static void increment(Counter counter) {
        for (;;) {
            int observed = (int) VALUE.getVolatile(counter);
            if (VALUE.weakCompareAndSet(counter, observed, observed + 1)) {
                return;
            }
            Thread.onSpinWait();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        boolean wrongExpected = VALUE.weakCompareAndSet(counter, 1, 99);
        System.out.println("wrongExpected=" + wrongExpected);

        int workers = 4;
        int incrementsPerWorker = 10_000;
        Thread[] threads = new Thread[workers];
        for (int i = 0; i < workers; i++) {
            threads[i] = new Thread(() -> {
                for (int j = 0; j < incrementsPerWorker; j++) {
                    increment(counter);
                }
            });
            threads[i].start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("afterWeak=" + (int) VALUE.getVolatile(counter));
        boolean strong = VALUE.compareAndSet(counter, 40_000, 40_001);
        System.out.println("strong=" + strong);
        System.out.println("final=" + (int) VALUE.getVolatile(counter));
    }
}
```

Compile and run:

```bash
javac --release 17 WeakCasGuide.java
java WeakCasGuide
```

**Stdout when workers complete successfully (verified):**

```text
wrongExpected=false
afterWeak=40000
strong=true
final=40001
```

**Analysis:**

1. `Counter.value` defaults to `0`. `weakCompareAndSet(counter, 1, 99)` uses expected `1`, so it is guaranteed to return `false` when no other thread has changed the variable. The line `wrongExpected=false` is an example of **expected mismatch**, not proof of a spurious failure.
2. Each thread performs 10,000 calls to `increment`. Inside, if a weak CAS attempt fails due to expected mismatch **or** spurious failure, the thread re-reads and computes `observed + 1` from the fresh data. In total, 4 × 10,000 updates succeed, so after the threads finish, the value is `40000`.
3. `Thread.join()` ensures main waits for the threads to finish, so there are no remaining writers from these demo threads afterward. `compareAndSet(counter, 40000, 40001)` succeeds with the known expected value, returning `true` and a final value of `40001`.
4. `Counter` is nested inside `WeakCasGuide`, and `MethodHandles.lookup().findVarHandle` locates the `int` instance field. With this handle, the corresponding call-site signature is `(Counter, int expected, int newValue)boolean`.
5. The program does not output a count of spurious failures because the API does not classify the source of failure; the number of `false` results due to contention also depends on scheduling, so it is not printed to avoid misleading claims.

**Note on liveness:** the sample code models a counter task that keeps trying until the update succeeds. On real JVM/hardware, this program ran with the output above. However, the specification allows weak CAS to fail spuriously repeatedly, so you must not infer from the demo that completion time or retry count is formally bounded. In production, set deadlines, contention limits, and fallbacks according to the system contract when needed.

## 8. Additional cases: atomic arrays and references

`VarHandle` does not apply only to instance fields. For arrays, you can obtain a handle as follows:

```java
VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);
int[] scores = {10, 20};
boolean ok = element.weakCompareAndSet(scores, 0, 10, 11);
```

This is an **illustrative snippet** in a class that has imported `MethodHandles` and `VarHandle`. Because weak CAS can fail spuriously, `ok` may be `false` even when the element is still `10`; if the business logic requires the update, you must retry under the appropriate condition. Every call to an array element VarHandle must include array + index coordinates, unlike the receiver coordinate of an instance field.

### 8.1. Reference CAS compares identity, not `equals`

For reference-type fields, the witness value is compared with expected by **identity `==`**, without automatically calling `equals()`:

```java
String a = new String("x");
String b = new String("x");
// a.equals(b) == true, but a == b is false.
```

This is a standalone illustration. If the current state is reference `a` and expected is `b`, CAS may not succeed even though `a.equals(b)` is `true`. When designing lock-free structures based on object identity, you must understand this invariant accurately.

### 8.2. The ABA problem is not solved by weak CAS alone

Suppose a reference variable goes from `A → B → A`. A thread that observed `A` earlier may try CAS with expected `A` and succeed after the variable returns to `A`, even though an **intermediate change** occurred. This is the *ABA problem*, which occurs with both strong and weak CAS. Retrying on spurious failure **does not** prevent ABA.

If the application must distinguish different versions of state, consider immutable data with a version, `AtomicStampedReference`, or an algorithm with an appropriate change-detection mechanism. Adding a stamp must be part of a correct protocol, not just an auxiliary field written non-atomically.

## 9. Conditions for safe retrying in real systems

### 9.1. The update function should be pure

A CAS loop typically computes `newValue = f(observedValue)`. The function `f` should be **deterministic/free of non-repeatable side effects** for a given snapshot. When CAS fails and retries, running `f` again must be safe.

Specifically avoid:
- deducting money / sending email / writing files / calling external APIs **before** winning the right via CAS;
- emitting a unique external event inside the loop without an idempotency mechanism;
- holding resources/locks inside a spin loop such that other threads cannot make progress.

### 9.2. Separate retryable conflict from business rejection

Suppose the initial state is `PENDING`. If another thread has already transitioned it to `CANCELLED`, an update "transition from PENDING to RUNNING" **must reject**, rather than retrying with the new expected value to write RUNNING. A correct loop must check **the business condition after every read** before attempting CAS.

Spurious failure also requires not rejecting the business operation prematurely while the state still satisfies the condition. Thus there are two separate questions:

1. **Is the business condition still valid?** If not, stop.
2. **Did CAS succeed?** If not, while the condition is still valid, you may try again.

### 9.3. Under high contention or tight deadlines

- Do not hot-spin unboundedly on a task with a tight deadline.
- You can count failures, apply backoff, or switch to an appropriate locking mechanism.
- If the retry limit is reached, you must **return an incomplete result** or use a fallback capable of completing the operation; never report false success.
- If threads have different priorities, choose a fairness policy at the system level. Weak CAS alone has no fairness guarantee.
- Benchmarks should model realistic thread counts, contention levels, and GC behavior; do not conclude weak CAS is always faster than strong CAS on every architecture.

### 9.4. Should you use `getAndAdd` instead of writing a CAS loop?

If the goal is simply to add `delta` to an integer field, `VarHandle.getAndAdd(...)` or `AtomicInteger.incrementAndGet()` is usually simpler and avoids re-implementing a retry policy. A CAS loop is useful when `newValue` depends on a more complex check or transformation with no direct atomic primitive.

Choose based on **required guarantees**, contract clarity, and performance measurements, not solely on the word "weak".

## 10. Testing spurious failure and retry logic

### 10.1. What can be verified directly?

You can write tests for:

- With an expected value that is **definitely wrong** under no-writer conditions, `weakCompareAndSet` must return `false` and not change the value.
- With the retry algorithm and multiple threads, after completion, total updates are not lost.
- Testing business conditions: when state is no longer valid, the method must stop instead of performing an invalid update.
- Testing timeouts, cancellation, fallback, and data preservation when the retry budget is exhausted.
- Testing memory ordering with appropriate stress/JMM tests if the design uses Plain/Acquire/Release.

### 10.2. What cannot be relied upon in a single run?

You cannot force `weakCompareAndSet` to **have to** fail spuriously. A JVM may succeed on every weak CAS with a matching expected value in a test. Therefore, tests must verify **behavior when an attempt returns `false`**, rather than waiting for the JVM to emit a spurious failure to exercise the retry branch.

One way to test the logic independently is to place an **abstraction layer over the CAS operation** and inject a fake implementation that returns `false` on the first few attempts even when the state has not changed, then returns success. This test proves that **the application's retry code** does not assume `false == mismatch`; it does not prove the JVM produced a real spurious failure. For complex concurrent algorithms, you also need linearizability tests, stress/interleaving tests, or appropriate memory-model analysis tools.

### 10.3. Do not count every false as spurious

When logging `attempts` and `failures`, the `false` count is the **sum** of `false` from expected mismatch and spurious `false`. Even if you re-read the same value after a `false`, you cannot be sure it was a spurious failure: another thread could have changed it back and forth between the two reads (ABA). Therefore, there is no accurate spurious-rate statistic solely from `false` counts in general code.

## 11. Common Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Assuming weak CAS `false` always means contention | The API allows spurious failure | Retry while business condition is valid; re-read snapshot |
| Trying once and concluding "no longer eligible to update" | `false` does not prove expected mismatch | Check current state / business condition |
| Reusing the old expected value forever in the loop | When state changes, CAS may fail infinitely | Re-read and recompute the new value |
| Writing `setVolatile` to "compensate" for a failed CAS | A direct write can overwrite another thread's update | Retry CAS or use another atomic RMW |
| Using `weakCompareAndSetPlain` as Volatile | Plain lacks Volatile ordering | Choose the right access mode per JMM |
| Confusing `AtomicInteger.weakCompareAndSet` with `VarHandle.weakCompareAndSet` | The old AtomicInteger API is deprecated/plain; unsuffixed VarHandle has volatile semantics | Read each API's specification carefully |
| Logging every `false` as "spurious" | Cannot separate the two causes | Record generic CAS failure |
| Running side effects before CAS and retrying | Side effects may be repeated multiple times | Win ownership first; use idempotency for external effects |
| Claiming weak CAS will always eventually succeed | No bounded retry / fairness guarantee | Design cancellation/budget/fallback |
| Assuming `Thread.onSpinWait` sleeps the thread or guarantees fairness | It is only a performance hint | Use backoff/blocking when needed |
| Ignoring ABA | Neither strong nor weak CAS detects A→B→A automatically | Use version/stamp or a controlled algorithm |
| Catching `WrongMethodTypeException` and retrying CAS forever | Call-site/typing error is not a contention `false` | Fix the VarHandle signature and argument types |

## 12. Practice Exercises

**Exercise 1 — Explaining two `false` outcomes.** The variable is currently `5`. An attempt `weakCompareAndSet(holder, 5, 6)` returns `false`. Can we conclude another thread changed the variable?

**Answer:** No. `false` may be due to the witness differing from expected **or** a spurious failure even though the witness is still `5`.

**Exercise 2 — Fixing the loop.** Fix the following snippet so that each request increments exactly once when it succeeds:

```java
int original = (int) VH.getVolatile(holder);
while (!VH.weakCompareAndSet(holder, original, original + 1)) {
    Thread.onSpinWait();
}
```

**Hint:** Move the `getVolatile` read and the `original + 1` computation **inside the loop**; exit only when a CAS attempt returns `true`. This is an illustrative snippet, not a standalone file.

**Exercise 3 — Choosing the access mode.** A protocol needs to guarantee publication with Release and the receiving side reads with Acquire. Does using only `weakCompareAndSetPlain` to publish automatically provide the required guarantee?

**Answer:** No. Plain is not equivalent to Release; you must choose an appropriate mode such as `weakCompareAndSetRelease` and design the Acquire read side properly, while validating the entire protocol.

**Exercise 4 — Comparing APIs.** In Java 17, do `VarHandle.weakCompareAndSet` and `AtomicInteger.weakCompareAndSet` have the same memory effects?

**Answer:** No. The unsuffixed `VarHandle` method has volatile effects. The old method of the same name on `AtomicInteger` is deprecated and has plain effects; replace it with `weakCompareAndSetVolatile` if volatile ordering is truly needed in `AtomicInteger`.

**Exercise 5 — Progress and safety.** A thread spins with weak CAS, always computes correctly, and never writes corrupt data; does that prove the thread will finish within at most 1,000 attempts?

**Answer:** No. CAS atomicity/safety does not automatically create bounded liveness. Both spurious failures and contention can delay success; you need an additional progress policy if the system has time bounds.

## Official Documentation

- [Java SE 17 — java.lang.invoke.VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): `compareAndSet`, `weakCompareAndSet`, Plain/Acquire/Release variants, and memory semantics.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): distinguishing the old `weakCompareAndSet` (deprecated/plain) from `weakCompareAndSetVolatile`.
- [Java Language Specification, Java SE 17 — Chapter 17, Threads and Locks](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-17.html): happens-before foundations and the memory model.

## Conclusion

`VarHandle.weakCompareAndSet` is a **conditional atomic** update, but it is allowed to return `false` due to **spurious failure**, even when the witness matches expected. Therefore, a boolean `false` **is not enough** to conclude there is contention, and an algorithm that needs to retry must **re-read, re-check the business condition, recompute the new value, and then try CAS again**. Separate update correctness from loop liveness, keep side effects outside retries, choose the appropriate memory ordering, and do not confuse the semantics of `VarHandle.weakCompareAndSet` with the deprecated method of the same name in `AtomicInteger`.
