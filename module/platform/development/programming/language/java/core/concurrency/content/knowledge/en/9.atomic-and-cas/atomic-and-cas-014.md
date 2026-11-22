# updateAndGet, accumulateAndGet, and the Risk of Side Effects on CAS Retry

## 1. The Problem: One Update Call Does Not Mean the Lambda Runs Only Once

In Java concurrency, `AtomicInteger`, `AtomicLong`, and `AtomicReference<V>` provide methods to update a value based on its **current value** without having to write a manual `compareAndSet` (CAS) loop for every case. Two central methods are:

~~~java
int updated = counter.updateAndGet(old -> old + 1);

int total = counter.accumulateAndGet(
        5, (current, delta) -> current + delta);
~~~

Both operations update the value **atomically**. However, an atomic update **does not mean** the lambda function is invoked exactly once. When another thread performs a competing update, a computation may be based on a stale value and fail to commit via CAS; the JDK may **invoke the function again** with the new value and retry.

That is why the JDK documentation requires `updateFunction` and `accumulatorFunction` to be **side-effect-free**. If the lambda sends an email, writes a business log, writes to a database, increments a separate metric, or mutates a mutable object, those actions can happen **multiple times for a single successful update**.

This lesson helps you:

- Understand the signatures and return values of `updateAndGet`, `getAndUpdate`, `accumulateAndGet`, and `getAndAccumulate` for integers and object references.
- Explain why a CAS failure leads to a retry, and why **the function being evaluated** differs from **the candidate being committed**.
- Know the rules for applying `UnaryOperator` and `BinaryOperator`, the argument order (`current` first, `x` second), and the conditions for a transformation to be thread-safe.
- Use immutable state and immutable inputs to design pure update functions that protect invariants under multi-writer contention.
- Reproduce a single real update where the lambda is executed **twice** using a Java 17+ example with controlled scheduling.
- Choose the right place to log, emit events, or perform I/O; understand the limits of "performing side effects after a successful CAS".
- Distinguish `updateAndGet` from `set`, `getAndSet`, `getAndIncrement`, `LongAdder`, `synchronized`, and other synchronization approaches.

**Scope:** Java SE/JVM concurrency, Java Memory Model (JMM), Atomic & CAS. Examples run standalone with **JDK 17 or later**.

## 2. Core API Set and Return Value Semantics

### 2.1. AtomicInteger and AtomicLong

For `AtomicInteger`:

~~~java
int newValue = atomic.updateAndGet(old -> old + 1);

int oldValue = atomic.getAndUpdate(old -> old + 1);

int newTotal = atomic.accumulateAndGet(
        delta, (current, amount) -> current + amount);

int previous = atomic.getAndAccumulate(
        delta, (current, amount) -> current + amount);
~~~

`AtomicLong` is similar but uses the `long` type. The single-argument function for `AtomicInteger` is `IntUnaryOperator`, and the two-argument function is `IntBinaryOperator`; `AtomicLong` uses `LongUnaryOperator` and `LongBinaryOperator`. All of these belong to the Java standard library and require no extra dependencies.

| API | Transformation Function Arguments | Return Value | Mnemonic |
|---|---|---|---|
| `updateAndGet(fn)` | Current value `old` | **New value** after the successful update | Update → return new |
| `getAndUpdate(fn)` | Current value `old` | **Old value** before the successful update | Return old → update |
| `accumulateAndGet(x, fn)` | `fn(current, x)` | **New value** | Combine current with x |
| `getAndAccumulate(x, fn)` | `fn(current, x)` | **Old value** | Combine, but return old |
| `getAndIncrement()` | No function passed | Old value, then atomically increment by 1 | Specialized for counters |
| `incrementAndGet()` | No function passed | New value after atomically incrementing by 1 | Specialized for counters |
| `compareAndSet(expect, next)` | Two candidate values | `true`/`false` | Manual CAS/retry control |
| `getAndSet(next)` | Replacement value | Old value | Replace **unconditionally**, not computed from old |

In the update-function group, the return value is **the value belonging to the committed update**, not the value from a failed lambda evaluation. When multiple threads are updating concurrently, a subsequent `get()` may still observe a newer value; the return value does not lock the value in that state forever.

### 2.2. AtomicReference<V>

When the protected value is **an object reference**, use:

~~~java
AtomicReference<State> current = new AtomicReference<>(initial);

State newState = current.updateAndGet(
        old -> new State(old.count() + 1, old.version() + 1));

State oldState = current.getAndUpdate(
        old -> new State(old.count() + 1, old.version() + 1));

State afterMerge = current.accumulateAndGet(
        delta, (old, increment) -> merge(old, increment));
~~~

These are **snippets inside a class/method**; `State`, `initial`, `delta`, and `merge` must be defined by the application. For `AtomicReference<V>`, the functions are `UnaryOperator<V>` and `BinaryOperator<V>`. Therefore `accumulateAndGet(x, function)` takes **x of the same type V**, unlike `AtomicInteger` which takes an `int`.

**Note:** `AtomicReference` protects swapping **the reference**; it does not make `ref.get().mutableField++` safe. When updating object state with functional APIs, create a **new immutable snapshot** and avoid mutating an old object that other readers may still be using.

## 3. The CAS Loop and Why a Function Can Be Called Again

An easy-to-understand logical model for `updateAndGet(fn)` is:

~~~java
while (true) {
    Value before = atomic.get();
    Value candidate = fn.apply(before);
    if (atomic.compareAndSet(before, candidate)) {
        return candidate;
    }
    // Contention: read the new current value and retry.
}
~~~

This is **Java-like pseudocode**, with `Value` as a hypothetical type and `atomic` as an atomic holder; it is not the verbatim JDK implementation. The JDK may optimize and use different CAS/VarHandle variants. What matters from the API contract is: **the function may be re-applied** if the attempted update fails due to contention.

### Interleaving: the lambda is called twice, but updates only once

Suppose `counter = 0`:

| Step | Thread A: `updateAndGet(x -> x + 1)` | Thread B | Counter |
|---|---|---|---|
| 1 | Reads old = 0 | — | 0 |
| 2 | Calls lambda (1st time), candidate = 1 | — | 0 |
| 3 | — | `incrementAndGet()`, commits 0 → 1 | 1 |
| 4 | CAS expected 0 → 1 **fails** | — | 1 |
| 5 | Re-reads old = 1 | — | 1 |
| 6 | Calls lambda (2nd time), candidate = 2 | — | 1 |
| 7 | CAS expected 1 → 2 **succeeds** | — | 2 |

A's result is **2**, meaning A's increment was actually committed **once**. Yet the function provided by A was evaluated **twice**. If the function contained `sendEmail()`, two emails could be sent. If the function contained `auditCounter.incrementAndGet()`, `auditCounter` could be incremented twice, even though A incremented the main state only once.

### The difference between three kinds of events

1. **Lambda execution:** the formula computing a candidate; the candidate is not guaranteed to be published.
2. **CAS success:** the candidate has been committed as an atomic update.
3. **External side effects:** emails, databases, logs, or events are separate systems; they can execute even when CAS fails, and they are not rolled back by CAS.

Correctness requires not confusing these three events.

## 4. Standalone Example 1: Deterministically Reproducing a Lambda Running Twice

This Java 17+ example uses `CountDownLatch` to force updater A to compute a candidate from 0 and then pause. Main increments the counter from 0 to 1 before letting A proceed. As a result, A's first CAS must fail; A re-reads and invokes the lambda a second time. The `functionCalls` variable is intentionally a **side effect demonstrating the bug**, not a production pattern.

Save the file **AtomicFunctionRetryDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicFunctionRetryDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger value = new AtomicInteger(0);
        AtomicInteger functionCalls = new AtomicInteger(0);
        CountDownLatch firstEvaluation = new CountDownLatch(1);
        CountDownLatch resume = new CountDownLatch(1);

        Thread updater = new Thread(() -> {
            value.updateAndGet(old -> {
                int callNumber = functionCalls.incrementAndGet();

                if (callNumber == 1) {
                    firstEvaluation.countDown();
                    try {
                        resume.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(e);
                    }
                }

                return old + 1;
            });
        }, "retry-updater");

        updater.start();
        firstEvaluation.await();

        // Main commits a competing update while A is paused.
        value.incrementAndGet();  // 0 -> 1
        resume.countDown();        // A resumes; its stale CAS will fail.
        updater.join();

        System.out.println("value=" + value.get());
        System.out.println("functionCalls=" + functionCalls.get());
    }
}
~~~

Compile and run:

~~~bash
javac AtomicFunctionRetryDemo.java
java AtomicFunctionRetryDemo
~~~

Output assuming no external interrupt:

~~~text
value=2
functionCalls=2
~~~

**Why is the output predictable?**

- `firstEvaluation.await()` in main finishes only after A's lambda has been **called the first time**, read `old=0`, and signaled the latch.
- During the first call, A has not returned a candidate yet; A waits on `resume`. Main executes `value.incrementAndGet()`, committing the value `1`.
- Main opens `resume`. When A resumes and tries to commit the candidate computed from `0`, the CAS expecting `0` fails because current is `1`.
- A must recompute from current = `1`, calling the lambda again; candidate `2` is committed.
- Main calls `join()` before reading the result. No `sleep()` is used to guess scheduling.

**This is an intentional anti-pattern for teaching:** the lambda performs `functionCalls.incrementAndGet()` and calls `await()` on the first invocation. Never put latch waiting, external service calls, metric mutations, or such side effects inside an update function in a real system. If an updater blocks inside the callback, it can prolong the operation, increase contention, and introduce unwanted risks. This lesson uses a latch solely to clearly demonstrate retry behavior.

## 5. Standalone Example 2: Using updateAndGet and accumulateAndGet Properly

The example below uses `AtomicInteger`, where both lambdas only compute a new value from their arguments and **do not update external variables**.

Save the file **AtomicFunctionBasicsDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicFunctionBasicsDemo {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger(10);

        int afterUpdate = counter.updateAndGet(old -> old + 2);
        int afterAccumulate = counter.accumulateAndGet(
                5, (current, delta) -> current + delta);

        int oldFromGetAndUpdate =
                counter.getAndUpdate(old -> old * 2);

        int oldFromGetAndAccumulate = counter.getAndAccumulate(
                3, (current, delta) -> current - delta);

        System.out.println("updateAndGet=" + afterUpdate);
        System.out.println("accumulateAndGet=" + afterAccumulate);
        System.out.println("oldUpdate=" + oldFromGetAndUpdate);
        System.out.println("oldAccumulate=" + oldFromGetAndAccumulate);
        System.out.println("final=" + counter.get());
    }
}
~~~

Commands:

~~~bash
javac AtomicFunctionBasicsDemo.java
java AtomicFunctionBasicsDemo
~~~

Output:

~~~text
updateAndGet=12
accumulateAndGet=17
oldUpdate=17
oldAccumulate=34
final=31
~~~

Step-by-step explanation on **a single thread**:
- Starts at `10`.
- `updateAndGet(x -> x + 2)` updates to `12` and returns `12`.
- `accumulateAndGet(5, (current, delta) -> current + delta)` updates to `17` and returns `17`.
- `getAndUpdate(x -> x * 2)` changes to `34` but returns **old=17**.
- `getAndAccumulate(3, (current, delta) -> current - delta)` changes to `31` but returns **old=34**.
- Final `get()` reads `31`.

With multiple threads, each atomic call has a valid update order, but **the order across threads is not fixed**. Do not predict the output of a concurrent test without controlling execution order.

### Why does the argument order of accumulateAndGet matter?

The two-argument function contract is:

~~~java
(current, x) -> newValue
~~~

`current` is **always the current value of the atomic at that evaluation**, and `x` is the update argument you pass. For addition, swapping the two arguments does not change the result. For subtraction, string concatenation, or non-commutative state transitions, swapping the order **changes the logic**.

~~~java
AtomicInteger n = new AtomicInteger(10);
n.accumulateAndGet(3, (current, amount) -> current - amount);
// 10 - 3 = 7
~~~

The snippet above is an illustration inside a method with appropriate imports, not a standalone `main` program. Do not mistakenly write `(amount, current) -> amount - current` when the business logic requires subtracting the new amount from the existing value.

## 6. What Makes an Update Function Side-Effect-Free?

In this context, a good lambda should be **pure with respect to shared state**:
- Use only the `old/current` value and the call's immutable data arguments.
- Compute the new result **without writing externally**: do not mutate fields, shared `List`/`Map` instances, increment other counters, write files, or emit events.
- Do not perform I/O, transactions, callbacks with side effects, or operations that may block for a long time.
- Do not mutate the `old` object itself if that object is held by other readers.
- Do not depend on external mutable state that changes asynchronously between retries.
- Be safe to re-evaluate multiple times without harming the system.

Good example:

~~~java
AtomicInteger balance = new AtomicInteger(100);
int newBalance = balance.accumulateAndGet(
        20, (current, amount) -> Math.addExact(current, amount));
~~~

The snippet above performs addition with overflow checking. `Math.addExact` is a pure computation; if overflow is detected, it throws `ArithmeticException` before committing the candidate of the current attempt.

Bad example:

~~~java
AtomicInteger sum = new AtomicInteger();
AtomicInteger logCounter = new AtomicInteger();

sum.updateAndGet(old -> {
    logCounter.incrementAndGet(); // side effect: may happen more than once
    return old + 1;
});
~~~

Both individual atomic counters are thread-safe for their own operations, **but the overall operation has no atomicity across the two counters**. When `sum` experiences contention and the callback re-runs, `logCounter` can be incremented more times than `sum` actually updates successfully.

### Even a function that only reads a clock or random source deserves care

~~~java
state.updateAndGet(old ->
        new State(old.value(), System.nanoTime()));
~~~

Calling `System.nanoTime()` does not directly write shared state in the application, but the function is no longer a stable transformation from the same `old`: each retry can produce a different timestamp. If the business logic needs the start time of **a request** rather than the time of a retry attempt, compute the timestamp **before** calling the atomic update and pass the immutable value into the function. The same applies to random inputs, generated IDs, and data used to guarantee idempotency.

Not all non-determinism breaks atomicity, but it makes results harder to interpret, test, and recover. Separating input selection from the retry phase is easier to control.

## 7. Example with AtomicReference and Immutable Object State

When multiple related fields need to change together, `AtomicReference<State>` + an immutable record is usually appropriate. The update function creates a **new snapshot**, avoiding mutating the old snapshot.

Save the file **AtomicStateFunctionDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicStateFunctionDemo {
    record Inventory(int available, int reserved) {
        Inventory {
            if (available < 0 || reserved < 0) {
                throw new IllegalArgumentException("negative stock");
            }
        }
    }

    private final AtomicReference<Inventory> current =
            new AtomicReference<>(new Inventory(10, 0));

    Inventory addStock(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        return current.updateAndGet(old -> new Inventory(
                Math.addExact(old.available(), amount),
                old.reserved()));
    }

    Inventory transferToReserved(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        return current.updateAndGet(old -> {
            if (old.available() < amount) {
                return old; // insufficient stock: leave state unchanged
            }
            return new Inventory(
                    old.available() - amount,
                    Math.addExact(old.reserved(), amount));
        });
    }

    Inventory snapshot() {
        return current.get();
    }

    public static void main(String[] args) {
        AtomicStateFunctionDemo store = new AtomicStateFunctionDemo();

        store.transferToReserved(3);
        store.addStock(2);
        Inventory after = store.transferToReserved(4);
        Inventory finalState = store.snapshot();

        System.out.println("after=" + after.available()
                + "/" + after.reserved());
        System.out.println("final=" + finalState.available()
                + "/" + finalState.reserved());
    }
}
~~~

Run commands:

~~~bash
javac AtomicStateFunctionDemo.java
java AtomicStateFunctionDemo
~~~

Output when `main` runs sequentially:

~~~text
after=5/7
final=5/7
~~~

Walkthrough:
1. Initially `available=10`, `reserved=0`.
2. `transferToReserved(3)` creates snapshot `(7,3)`.
3. `addStock(2)` creates snapshot `(9,3)`.
4. `transferToReserved(4)` creates snapshot `(5,7)`.
5. `snapshot()` returns a reference to an immutable `Inventory` with **both fields belonging to the same version**.

If multiple threads update the same instance, each `updateAndGet` call may recompute from the new snapshot under contention. Because the callback only reads `old`, `amount`, and creates a new object, retries cause no external side effects. When stock is insufficient, the callback returns `old`, so the immutable state remains unchanged.

**Semantic warning:** `transferToReserved` returns `Inventory`, not a separate success flag. If the caller needs to distinguish "did the reservation succeed?", do not guess from object identity or two external `get()` calls while writers are active; design a dedicated CAS loop API that returns a meaningful outcome, or embed the business result in the appropriate state/transition. An update function that gets re-run may return the same `old` object, and the callback is not the place to log "reserved" before commit.

### Why not mutate old directly?

Wrong:

~~~java
AtomicReference<MutableInventory> ref = ...;
ref.updateAndGet(old -> {
    old.available -= 1;
    old.reserved += 1;
    return old;
});
~~~

This illustrates a bug, assuming `MutableInventory` is a mutable application class. The mutations occur **before CAS**, can be seen by other readers, and may repeat multiple times if CAS retries. `AtomicReference` still points to **the same `old` object**, so CAS on the same reference does not prevent data races on its fields. Use immutable state with a new candidate, or lock all valid mutations.

## 8. accumulateAndGet: Combining current with a Single Call's Input

For `AtomicInteger`/`AtomicLong`, `accumulateAndGet(x, function)` fits well when the business rule is "apply a delta to the current state", such as accumulating sums, taking max/min, updating bitmasks, or clamping increments/decrements.

~~~java
AtomicInteger max = new AtomicInteger(0);

max.accumulateAndGet(12, Math::max);
max.accumulateAndGet(7, Math::max);
// final value is 12, without needing a separate lock for the two updates
~~~

The function is `(current, incoming) -> Math.max(current, incoming)`. If no competing writers remain at read time, the result is 12.

Example of a bounded value:

~~~java
AtomicInteger used = new AtomicInteger(0);
int limit = 100;
int updated = used.accumulateAndGet(5,
        (current, amount) -> Math.min(limit, current + amount));
~~~

This illustrates a simple total cap; handle overflow if `current + amount` could exceed the `int` range. In particular, if the resource needs to return **"how much was successfully granted"** or atomically reject when exceeding the limit, an API that only returns the new value does not fulfill the entire business contract by itself. You may need a CAS loop and a return type that expresses the outcome.

### Combination operations are not always commutative

With two threads calling `accumulateAndGet` differently:
- Updates are committed in some valid linearizable order.
- If the combining operation is commutative and associative, the final sum can be independent of order.
- If it is a non-commutative operation such as two subtractions with complex policies, string concatenation, state priority, or conditional clamping, **the final result can depend on commit order**.
- Atomicity of each operation **does not promise** ordering across concurrent callers.

Similarly, merely using an accumulator does not mean you can swap operand order or merge multiple transitions into one while preserving the business semantics.

## 9. When to Use getAndUpdate vs. updateAndGet

The most important difference is the **return value**, not safety:

~~~java
AtomicInteger n = new AtomicInteger(10);

int previous = n.getAndUpdate(old -> old + 1); // 10
int updated = n.updateAndGet(old -> old + 1);   // 12
~~~

`previous` represents the value before the corresponding atomic update. In concurrency, if you need the unique sequence number granted to each request, `getAndIncrement()` is often a better fit because it returns the exact old number for each increment.

Do not use `getAndUpdate` just to "reduce lambda invocations"; it can also retry and recompute the function. Both options share the same no-side-effects rule.

### AtomicReference and identity comparison

`AtomicReference.compareAndSet(expected, newValue)` compares the current reference with `expected` using **`==`**, not `equals()`. When an update function creates a new snapshot from `expected` and CAS fails, the JDK may recompute with the new current reference.

If two immutable objects have the same contents but are two distinct references, CAS with the old `expected` still fails as usual. This is good for version-based state transitions; however, keep in mind the **ABA** problem when a reference changes A→B→back to the exact old A. If the algorithm needs to detect every intermediate change, `AtomicStampedReference` or a versioned protocol may be necessary. The convenience update methods do not automatically solve all ABA problems.

## 10. Where Should Logs or Events Be Emitted?

The minimal solution is **not to perform side effects inside the callback**. Instead of:

~~~java
balance.updateAndGet(old -> {
    sendReceipt(); // may be called multiple times on CAS retry
    return old - amount;
});
~~~

compute/update purely, then perform the side effect at a point with a clear contract:

~~~java
int updated = balance.updateAndGet(old -> old - amount);
sendReceiptAfterSuccessfulUpdate(updated);
~~~

This is **integration pseudocode**; `sendReceiptAfterSuccessfulUpdate` is an application-defined name. Placing the send after a successful update **avoids repeating the side effect solely due to callback CAS retries**, but **does not create an atomic transaction** between the in-JVM update and sending the external receipt.

There are at least two cases to handle:
1. State commits, and then sending the message **fails**.
2. The process crashes after commit but before sending; or sending succeeds, but the client does not receive the acknowledgment and retries the request.

If the business requirement demands "exactly once" across persistence/queue/email, using `AtomicInteger` or `AtomicReference` alone **is not enough**. You need an outbox/transaction/idempotency/durable-processing design according to the external resource's contract. Do not promise exactly-once just because the code calls send after `updateAndGet`.

### Never send an email when a state transition is rejected

For example, a money transfer with insufficient balance: if the callback simply returns `old` when funds are insufficient, yet the caller sends a "success" email after `updateAndGet` returns, the logic is still wrong. You must atomically **distinguish a commit outcome from a business outcome**.

One approach uses a **manual CAS loop**, where the callback only computes, and the method returns a boolean indicating whether the condition check and commit succeeded:

~~~java
boolean withdraw(AtomicInteger balance, int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    while (true) {
        int before = balance.get();
        if (before < amount) {
            return false;
        }

        int after = before - amount;
        if (balance.compareAndSet(before, after)) {
            return true;
        }
    }
}
~~~

This is a valid Java method inside a class with the corresponding imports. The entire check-then-decrement is protected by CAS; the caller can send a success notification **only if the method returns true**. Here too, notifications outside the JVM are still not part of an atomic transaction with the state; add a proper protocol if durability is required.

### Metrics for attempts vs. metrics for successful commits

Incrementing a `lambdaInvocations` counter inside the callback can be useful **in test examples to observe retries**, but you should not record "business operations completed" there. If you need to measure contention, separate **CAS attempts/failures** metrics from **committed updates** and clearly document them as technical metrics. With the `updateAndGet` convenience method, there is not necessarily a public API for the CAS retry count per call; write your own CAS loop when you need specific observability or policies.

## 11. Lambda Capture and Input Consistency

Update functions often capture a variable from outside the lambda:

~~~java
int delta = 5;
AtomicInteger total = new AtomicInteger();

total.accumulateAndGet(delta,
        (current, incoming) -> current + incoming);
~~~

`delta` is an effectively final local variable with a fixed value for the call. That is a sound pattern. When capturing a **reference to a mutable object**:

~~~java
List<String> changes = mutableList;
state.updateAndGet(old -> calculate(old, changes));
~~~

this snippet is **not automatically safe**: even though the `changes` variable is effectively final, the contents of the `List` can be modified by another thread while the lambda runs or re-runs, making the result non-deterministic. To avoid this, create an immutable input snapshot **before the update** if needed:

~~~java
List<String> immutableChanges = List.copyOf(mutableList);
state.updateAndGet(old -> calculate(old, immutableChanges));
~~~

These are illustrative snippets inside a method; `calculate` and `state` are application-defined. `List.copyOf` protects the `List` structure from mutation through the original reference at the container level; if the elements of the `List` are mutable objects, you must consider deep copying or immutable elements.

Cases worth noting:
- Reading a clock, random generator, UUID, or remote data **inside** the lambda can produce different candidates across retries. If you need a consistent input for a request, obtain it **before** the callback.
- Calling a non-thread-safe API from the callback is risky even if it does not directly mutate atomic state.
- If a function is stored and reused, do not rely on mutable shared fields that change over time when applying the same transformation.
- The constructor of an immutable candidate must uphold invariants; if the constructor itself has side effects, it can also be called again on retry.

## 12. AtomicReference.updateAndGet and Nested Mutable State

Distinguish between these two patterns:

**Correct:** create a new immutable object and CAS-swap the reference.

~~~java
record Position(int x, int y) {}

AtomicReference<Position> position =
        new AtomicReference<>(new Position(0, 0));

position.updateAndGet(old ->
        new Position(old.x() + 1, old.y() + 1));
~~~

A reader can take a `Position snapshot = position.get()` and read `x`/`y` from **the same version**.

**Wrong:** mutate the old object and return it.

~~~java
class MutablePosition {
    int x, y;
}

AtomicReference<MutablePosition> position =
        new AtomicReference<>(new MutablePosition());

position.updateAndGet(old -> {
    old.x++;
    old.y++;
    return old;
});
~~~

In the wrong example, multiple threads can mutate `old` concurrently before any CAS; a reader may also see `x` incremented while `y` is not yet incremented. If the function has to retry, the mutation can happen multiple times. `AtomicReference` does not turn a mutable object into a transaction.

**A snapshot is only valuable when it is truly immutable.** For a record containing a mutable `List` or `Map`, readers can still see its contents change after publication. Use defensive copies, immutable nested values, and clear ownership.

### Different fields in the same object

If an invariant spans two fields `available` and `reserved`, two separate `AtomicInteger` instances do not automatically form an atomic operation for the pair. You can wrap both values in an immutable record and swap a single reference, or use a shared lock for the entire check/update if the state is complex. The atomicity of an update function applies to **the value of one atomic variable**, and does not automatically extend to a second resource.

## 13. Java Memory Model and Observation Limits

According to the JDK documentation, the update methods of atomic classes have **memory effects as specified by `VarHandle.compareAndSet`**; `get()` on `AtomicReference`/`AtomicInteger` has the corresponding volatile read semantics, and `set()` has the corresponding volatile write semantics.

When a writer finishes constructing an immutable candidate and publishes it successfully via an atomic update, another thread that reads the published reference can observe the appropriate writes under the JMM. However:

- **Happens-before/visibility** does not make the callback "run only once".
- An atomic update does not prevent another thread from committing a new update **immediately after** you receive the result.
- Do not read a snapshot twice to combine fields from two different versions if you need consistency. Read the reference once, store it in a local variable, and read all fields from it.
- If an object is published and then continues to be mutated without synchronization, the initial safe publication benefit is not enough to protect subsequent mutations.
- A CAS loop can make global progress in many situations, but **it does not guarantee individual threads will not suffer starvation** under contention.

Be careful with the claim "lock-free means nothing ever blocks": a user's update function can itself perform I/O or wait on a lock (though strongly discouraged), causing the entire call to block. Atomic algorithms only provide memory/atomic semantics for the core update as specified by the API; they do not control everything inside the callback.

## 14. Performance, Retries, and Choosing a Solution

The convenience methods keep code concise, but they are **not free** under contention:

| Factor | What Can Happen | Reasonable Action |
|---|---|---|
| Many threads updating the same value | CAS fails, callback is recomputed | Keep the function pure; reduce computation cost per retry. |
| Lambda allocates large immutable objects | Failed candidates cause allocation/GC | Measure allocations; consider a cheaper data model or a lock. |
| Lambda performs long work | Retries multiply CPU work | Move independent work outside beforehand; keep the transform small. |
| Many writers and very high contention | Throughput/tail latency may suffer | Benchmark `Atomic*`, locks, and sharding/aggregation for your workload. |
| Simple counters | A lambda may be unnecessary | Use `incrementAndGet()` or `addAndGet()` as appropriate. |
| Metrics with many writers, summary reads | Contention on a single `AtomicLong` | Consider `LongAdder`; `sum()` is not an atomic snapshot while updates are in flight. |
| Complex multi-field invariants | CAS loop is hard to keep right and candidate copying is expensive | Consider `synchronized` or `ReentrantLock` with proper guarded regions. |
| Side effects alongside state | Atomic update does not cover external resources | Design business protocols, durability, and idempotency. |

### When to use AtomicInteger.accumulateAndGet instead of addAndGet?

If you are only adding a delta:

~~~java
int value = counter.addAndGet(delta);
~~~

`addAndGet` is clearer and does not need a custom callback. `accumulateAndGet` fits when you have a combining operation like `Math.max`, controlled clamping, or a transition with more logic than simple addition. Do not use a complex callback for all counters just because the API is more general.

### When to use synchronized?

If an update must protect multiple mutable fields, the callback is hard to make pure, or candidate copying is expensive, a critical section under a shared lock can be simpler and more suitable. However, holding a lock while calling external I/O can force other callers to wait for a long time. Choose based on invariants, measured contention, and workload characteristics; do not assume CAS is always faster than a lock or vice versa.

## 15. A Logic Bug to Avoid: Side Effects Before Knowing the Commit Result

Suppose you want to "send one message for each state transition from `PENDING` to `COMPLETED`". Wrong:

~~~java
status.updateAndGet(old -> {
    if (old == State.PENDING) {
        publishMessage("completed");
        return State.COMPLETED;
    }
    return old;
});
~~~

This is a non-standalone snippet; `status`, `State`, and `publishMessage` are application-defined. Under contention, the callback can read `PENDING`, send the message, and then fail CAS because another thread already transitioned the state. On retry, the callback sees `COMPLETED`; the final outcome has no `PENDING`→`COMPLETED` commit from the original caller, yet the message was already sent.

One approach within **a single JVM** is to use `compareAndSet(State.PENDING, State.COMPLETED)` to know **which thread won the transition**:

~~~java
boolean transitioned =
        status.compareAndSet(State.PENDING, State.COMPLETED);

if (transitioned) {
    publishMessage("completed");
}
~~~

The snippet assumes `State` is an enum; CAS relies on enum constant identity. This avoids calling `publishMessage` when the caller did **not** succeed in CAS, but it has very important limitations:

- If the process crashes after CAS succeeds but before `publishMessage`, the event is lost.
- If `publishMessage` sends the message but the acknowledgment is lost, a retry can cause duplicate delivery in the external system.
- `AtomicReference`/`AtomicInteger` does not make operations on another system atomic with RAM.
- If the request arrives again after the state is already `COMPLETED`, the caller should handle it idempotently.

To guarantee durable notifications, you need a transaction/outbox protocol or an appropriate commitment design in the storage system; do not promise exactly-once across all resources using CAS alone.

## 16. Common Mistakes and How to Fix Them

**Mistake 1 — Interpreting "atomic update" as "the lambda runs exactly once".** False; the callback can be re-evaluated after contention failures. Candidate computation and commit are two distinct events.

**Mistake 2 — Sending emails, writing business logs, or incrementing auxiliary counters inside the lambda.** Side effects can occur multiple times. Move side effects outside the callback and design commit/outcome handling plus durable retries if needed.

**Mistake 3 — Reading `old` with `get()`, computing, and calling `set(candidate)`.** Even though `get`/`set` are individually atomic, the whole read–modify–write is not atomic and can suffer lost updates. Use an update function or a CAS loop.

**Mistake 4 — Confusing `getAndUpdate` with `updateAndGet`.** The first returns **old**, the second returns **new**; both can retry.

**Mistake 5 — Reversing the arguments of `accumulateAndGet`.** The order is always `(current, x)`. For non-commutative operations, reversing the order breaks the logic.

**Mistake 6 — Calling `AtomicReference.get()` and then mutating the mutable object.** A thread-safe reference does not make mutable fields thread-safe. Use immutable snapshots or another synchronization mechanism.

**Mistake 7 — Letting the function mutate the `old` object and return `old`.** Mutations can be exposed before commit and repeated on retry. Create a new candidate object; do not mutate the published version.

**Mistake 8 — Capturing a mutable `List`/`Map`/array from outside the callback.** What the lambda reads can change across retries; use an immutable input snapshot or clear ownership.

**Mistake 9 — Mistaking the return value of `updateAndGet` for "I own the current value forever".** Another thread can update it immediately afterward; the result only reflects the call's commit point.

**Mistake 10 — Using `updateAndGet` for check-then-act with an ambiguous outcome.** If the callback returns `old` when a condition is not met, the caller needs an accurate way to know whether a transition occurred; consider a CAS loop returning a boolean or outcome.

**Mistake 11 — Not checking for overflow.** `AtomicInteger` and `AtomicLong` do not guard against overflow automatically. If invariants forbid wrap-around, use `Math.addExact` or appropriate validation.

**Mistake 12 — Counting callback invocations to infer successful updates.** The two numbers can differ due to CAS retries. Count only commits according to the appropriate contract.

**Mistake 13 — Assuming updating multiple `AtomicReference`s is a transaction.** They are separate atomic variables; multi-field invariants may require a single immutable snapshot or a shared lock.

**Mistake 14 — Prematurely optimizing with a heavy CAS callback.** Under contention, every failed attempt wastes object allocations and CPU work; benchmark before choosing.

**Mistake 15 — Assuming one passing stress test proves there is no race.** Different schedules, JIT behavior, and CPUs can produce different interleavings. Test with deterministic cases, invariant checks, and multiple contention levels.

## 17. Pre-Merge Code Review Checklist

1. **Which atomic variable?** Is a single `AtomicInteger`, `AtomicLong`, or `AtomicReference<State>` truly the shared source of state?
2. **Is the function pure?** No I/O, no external mutations, no business logging, no auxiliary metric updates, no mutating the `old` object?
3. **Can it retry?** Does the code correctly assume the function may be called 1..N times for a single successful update?
4. **Is the return value old or new?** `getAnd*` returns old; `*AndGet` returns new.
5. **Does the accumulator have the right argument order?** `(current, incoming)`, without swapping operands for non-commutative operations.
6. **Are inputs immutable?** Can captured arguments be modified concurrently? Is the immutable snapshot deep enough?
7. **Where are invariants protected?** Is the candidate validated and published through a proper atomic commit?
8. **Are there post-commit side effects?** If so, have crashes, duplicate sends, lost events, or out-of-JVM failures been handled?
9. **Are business rejections distinguished from CAS contention?** The caller must know whether the change was applied.
10. **What about overflow and exceptions?** The function throws before commit; if it already had side effects, they are not automatically rolled back.
11. **Has real contention been tested?** CAS retries, CPU, allocation/GC, throughput, and p95/p99 latency?
12. **Does the update truly need a lambda?** For simple operations, prefer specialized APIs such as `addAndGet`.

## 18. Practice Exercises and Answers

**Question 1.** Two threads concurrently call `AtomicInteger.updateAndGet(x -> x + 1)` on the same counter. How many times can each call run the lambda?

**Answer:** One or more times. A thread may compute from a stale value, lose the CAS race, and then invoke the lambda again with the new value. Each successful call commits only one update, but does not guarantee a single lambda evaluation.

**Question 2.** What value does `AtomicInteger.getAndUpdate(x -> x + 10)` return?

**Answer:** The **old** value immediately before the committed update. `updateAndGet` would return the **new** value.

**Question 3.** What does `n.accumulateAndGet(3, (current, amount) -> current - amount)` return when `n` starts at 10 with no contention?

**Answer:** 7. The first callback argument is `current=10`, and the second argument is `amount=3`.

**Question 4.** Why is calling `emailService.send()` inside `updateAndGet` dangerous, even if the final atomic state is correct?

**Answer:** The callback may be re-applied when CAS fails, causing multiple emails to be sent; a failed CAS does not undo an email that has already been sent.

**Question 5.** A lambda has no side effects, but it reads a mutable `List` modified by another thread. Is that safe enough?

**Answer:** Not necessarily. The input can change between retries, or reading the `List` itself may not be thread-safe. You need clear ownership, an immutable snapshot, or proper synchronization.

**Question 6.** Why can `AtomicReference<State>` update two fields atomically with an immutable record, whereas `AtomicReference<MutableState>` with field mutation cannot?

**Answer:** A new record is fully constructed and then published via **a single reference swap**; readers hold an immutable version. With `MutableState`, fields change **inside the shared object**, not via the reference CAS.

**Question 7.** If the lambda can be called again, how do you generate a single fixed request ID for the entire call?

**Answer:** Generate the ID **before** starting the update and pass it as an immutable input into the callback. Do not generate a new ID on every retry if the business contract requires one ID per request.

**Question 8.** After a successful `updateAndGet` followed by sending an external event outside the JVM, is the event guaranteed to be delivered exactly once regardless of process crashes?

**Answer:** No. Atomic state inside the JVM and the external system are two separate resources; you need persistence/transactions/idempotency/outbox or an equivalent design if durability and reliable event delivery are required.

## 19. Official API References

- **AtomicInteger (Java SE 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- **AtomicLong (Java SE 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- **AtomicReference (Java SE 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html
- **AtomicStampedReference (Java SE 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html
- **VarHandle (Java SE 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html
- **JLS `17 — Java Memory Model:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html

**Conclusion:** `updateAndGet` and `accumulateAndGet` express **atomic read–modify–write** operations concisely; `getAndUpdate` and `getAndAccumulate` provide the same atomicity while returning the value **before** the update. In all cases, the callback function may run **multiple times** due to CAS retries: use only **pure transformations** from `current` and immutable inputs to produce a candidate. Side effects, business outcomes, durable retries, and out-of-JVM transactions must be handled with dedicated protocols rather than betting on a lambda running only once.
