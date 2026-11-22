# Incomplete CompletableFuture: complete(), completeExceptionally(), and the Completion Race

## 1. Goal: A Result Decided Later

In many Java concurrency workflows, we **do not yet have the result when creating the object**, but want to immediately hand the caller a "handle" to wait on, chain further processing, or receive errors. For example: a network callback will report the result later, a worker processes a request, an event-receiving system replies by correlation ID, or multiple sources compete to deliver the first result.

`CompletableFuture<T>` supports the **manually completable promise** model:

```java
CompletableFuture<String> promise = new CompletableFuture<>();

// Later, another thread decides the outcome:
promise.complete("OK");
```

When just created via `new CompletableFuture<>()`, the promise is **incomplete**. It does not spawn a thread on its own, does not execute a Supplier or Runnable, and does not complete automatically just because it has been returned to the caller.

Three ways to affect its state are of interest:

- **`complete(value)`**: attempts to complete normally with the supplied value, returning a `boolean` indicating whether the call successfully performed the state transition.
- **`completeExceptionally(error)`**: attempts to complete exceptionally with the supplied `Throwable`, also returning a `boolean` indicating whether it won the completion race.
- **`cancel(mayInterruptIfRunning)`**: attempts to complete in the cancelled state. For `CompletableFuture`, the `mayInterruptIfRunning` parameter is not used to control execution via interruption.

The key point is that **a future has only one transition from incomplete to a chosen outcome**, according to the contract of normal `complete`/`completeExceptionally`/`cancel` methods. Competing contenders cannot replace a success or failure result already decided by those normal completion methods.

This lesson belongs to **Java Advance - concurrency → CompletableFuture**, scoped to **general Java concurrency**; it does not depend on Spring or any framework.

## 2. Distinguishing the Constructor from Other Factory Methods

| Creation Method | Initial State | Who Completes It? |
| --- | --- | --- |
| `new CompletableFuture<T>()` | Incomplete | A thread/callback calls `complete`, `completeExceptionally`, or `cancel`; it may also be completed by another API |
| `CompletableFuture.completedFuture(v)` | Normally completed | Value `v` is attached immediately at creation time |
| `CompletableFuture.failedFuture(error)` | Exceptionally completed | Throwable is attached immediately at creation time |
| `CompletableFuture.supplyAsync(supplier)` | May be incomplete or already completed when returned | Task runs the Supplier and completes the future |
| `CompletableFuture.runAsync(runnable)` | May be incomplete or already completed when returned | Task runs the Runnable, succeeding with result `null` |

Do not confuse **"creating a pending future"** with **"starting an async task"**. The `new CompletableFuture<>()` constructor does not automatically find a producer to generate a result. If every code path forgets to complete it, `join()` may wait indefinitely.

`completedFuture(v)` is not equivalent to `new CompletableFuture<>()` until you call `complete(v)`. After completion, both allow the caller to read the result normally, but **before completion** a pending future can have continuations registered, be waited on, or become the target of a race among producers.

## 3. State Model and "First Completion Wins"

One way to visualize the states:

```text
                     INCOMPLETE
                          |
           +--------------+---------------+
           |              |               |
     complete(value)  completeExceptionally  cancel(...)
           |              |               |
           v              v               v
      NORMAL(value)   EXCEPTIONAL(error)  CANCELLED
           \              |               /
            \             |              /
              TERMINAL OUTCOME
```

Once completed, `isDone()` is true. Normal completion can have a `null` value; exceptional completion holds a `Throwable`; cancellation is modeled as a form of exceptional completion with cause `CancellationException`.

With **normal completion** methods:

- The first call that actually transitions the future from incomplete to a terminal state **wins**.
- Subsequent competing calls cannot overwrite that outcome.
- `complete` and `completeExceptionally` return `true` if that specific call transitioned the future from incomplete to terminal.
- `complete` and `completeExceptionally` return `false` if the future was already completed before the call's attempt succeeded.
- `cancel` has its own return value detail: it returns `true` when the call causes the future to be cancelled **or the future is already in the cancelled state**; you should not count the number of times `cancel() == true` to infer the number of winning state transitions.
- The result read by `join/get` comes from the winning outcome, unless an intentional advanced operation such as `obtrudeValue`/`obtrudeException` is performed.

**There is no rule that "the thread created first always wins"**. The scheduler, ongoing work, contention, and execution timing determine the success order of completion calls.

## 4. `complete(value)`: Normal Completion

Signature:

```java
public boolean complete(T value)
```

Meaning: if the future is **incomplete**, attach the normal result `value` and wake up/allow dependent stages to complete according to `CompletableFuture`'s mechanism. If the future is already completed, do not change the normal outcome with `complete`, and return false.

### Example 1: pending → success → subsequent completion fails

Create the file `ManualCompletionBasicsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class ManualCompletionBasicsDemo {
    public static void main(String[] args) {
        CompletableFuture<String> promise = new CompletableFuture<>();

        System.out.println("initial done=" + promise.isDone());

        boolean first = promise.complete("READY");
        boolean second = promise.complete("TOO_LATE");

        System.out.println("first accepted=" + first);
        System.out.println("second accepted=" + second);
        System.out.println("final done=" + promise.isDone());
        System.out.println("result=" + promise.join());
    }
}
```

Compile/run with **JDK 17+**:

```bash
javac ManualCompletionBasicsDemo.java
java ManualCompletionBasicsDemo
```

Output:

```text
initial done=false
first accepted=true
second accepted=false
final done=true
result=READY
```

Before `complete`, the promise has no outcome. After `complete("READY")` succeeds, `join()` returns `"READY"`. The call `complete("TOO_LATE")` does not change the value because the future is already terminal.

### Valid null value

`CompletableFuture<String>` can be completed normally with:

```java
promise.complete(null);
```

That differs from `completeExceptionally(null)`. With `complete(null)`, `join()` returns null on success; with `completeExceptionally(null)`, the `Throwable` is invalid and the method throws `NullPointerException` instead of completing the future with a null error.

**Do not use `join() == null` as a way to check whether a future is still pending:** `join()` waits if pending; null can be an actual success value.

## 5. `completeExceptionally(error)`: Completion with an Error

Signature:

```java
public boolean completeExceptionally(Throwable ex)
```

This method attempts to put the future into **exceptional completion** with a non-null `Throwable`. Callers observe the failure via:

- `join()`: typically throws `CompletionException`, with `getCause()` being the error.
- `get()`: throws `ExecutionException` (checked) when the future completes exceptionally, with `getCause()` being the error.
- `isCompletedExceptionally()`: true for an exceptionally completed future, including cancellation.
- `isDone()`: true.
- `isCancelled()`: false for a regular error like `IllegalStateException`; must be distinguished from cancellation.

If the future already succeeded earlier, `completeExceptionally` returns false and **cannot turn success into failure** with this call.

### Example 2: Inspecting errors via join and get

Create the file `ManualExceptionalCompletionDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class ManualExceptionalCompletionDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<Integer> promise = new CompletableFuture<>();

        boolean first = promise.completeExceptionally(
                new IOException("source unavailable"));
        boolean late = promise.complete(42);

        System.out.println("exception accepted=" + first);
        System.out.println("late value accepted=" + late);
        System.out.println("done=" + promise.isDone());
        System.out.println("exceptional="
                + promise.isCompletedExceptionally());
        System.out.println("cancelled=" + promise.isCancelled());

        try {
            promise.join();
        } catch (CompletionException e) {
            System.out.println("join wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("join cause="
                    + e.getCause().getClass().getSimpleName());
            System.out.println("join message=" + e.getCause().getMessage());
        }

        try {
            promise.get();
        } catch (ExecutionException e) {
            System.out.println("get wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("get cause="
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

```bash
javac ManualExceptionalCompletionDemo.java
java ManualExceptionalCompletionDemo
```

Output:

```text
exception accepted=true
late value accepted=false
done=true
exceptional=true
cancelled=false
join wrapper=CompletionException
join cause=IOException
join message=source unavailable
get wrapper=ExecutionException
get cause=IOException
```

This is an error **actively injected into the promise**, not generated by `join/get` itself. `join/get` are the **outcome observation** points.

**Do not only log `e.getMessage()`** of the wrapper and discard `getCause()`. The root error, cause chain, stack trace, and task ID are what enable diagnosis.

## 6. Completion Race: One Promise, Multiple Producers

Suppose three sources answer the same request:

```text
Producer A: complete("A")
Producer B: complete("B")
Watchdog: completeExceptionally(timeoutError)

                 \    |    /
                  \   |   /
                  [ shared future ]
                         |
             only one transition wins
                         |
              consumer receives outcome
```

Producers can run concurrently. Using `CompletableFuture` as "**one-shot arbitration**" selects **the first accepted outcome**, but does not automatically stop losing producers or cancel side effects they may be performing.

**Linearizable operation:** for a pending future, competing `complete/completeExceptionally` calls race to set the final outcome. They provide an atomic decision point that callers can observe via the boolean return value and the future's result.

Because we do not know who wins, a proper test should not assume A always wins. The test needs to assert:

1. Only **one** of the `complete` or `completeExceptionally` calls returns true in a single-shot race.
2. The future is done.
3. The outcome is one of the valid outcomes of the contenders.
4. A late `complete` cannot change the outcome.

### Business Scenario

A gateway receives responses from **server-primary** and **server-backup**, while also having a watchdog timeout. The future only accepts the outcome that arrives first, but the other two network requests may still be running. A cancellation/resource-release policy is needed, and duplicate side-effecting requests should be avoided when both servers receive the request.

## 7. Example 3: Testing a Race Without Guessing the Winner

Create the file `ConcurrentCompletionRaceDemo.java`:

```java
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentCompletionRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> promise = new CompletableFuture<>();
        CountDownLatch ready = new CountDownLatch(3);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger winners = new AtomicInteger();

        Runnable successA = () -> {
            ready.countDown();
            try {
                start.await();
                if (promise.complete("A")) {
                    winners.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Runnable successB = () -> {
            ready.countDown();
            try {
                start.await();
                if (promise.complete("B")) {
                    winners.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Runnable failure = () -> {
            ready.countDown();
            try {
                start.await();
                if (promise.completeExceptionally(
                        new IllegalStateException("timeout"))) {
                    winners.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(successA, "producer-A");
        Thread b = new Thread(successB, "producer-B");
        Thread c = new Thread(failure, "watchdog");

        a.start();
        b.start();
        c.start();
        ready.await();
        start.countDown();

        a.join();
        b.join();
        c.join();

        boolean validOutcome;
        if (promise.isCompletedExceptionally()) {
            try {
                promise.join();
                validOutcome = false;
            } catch (CompletionException e) {
                validOutcome = e.getCause()
                        instanceof IllegalStateException;
            }
        } else {
            validOutcome = Set.of("A", "B").contains(promise.join());
        }

        System.out.println("accepted completions=" + winners.get());
        System.out.println("done=" + promise.isDone());
        System.out.println("valid outcome=" + validOutcome);
        System.out.println("late write="
                + promise.complete("AFTER_RACE"));
    }
}
```

```bash
javac ConcurrentCompletionRaceDemo.java
java ConcurrentCompletionRaceDemo
```

Output when there is no unintended interruption:

```text
accepted completions=1
done=true
valid outcome=true
late write=false
```

**Intentionally do not print a fixed winner name.** A, B, or watchdog may win depending on scheduling. `CountDownLatch` gets all three threads ready and gives them a chance to try together, but **does not** force a specific order. Only one `complete`/`completeExceptionally` can succeed in this race.

This is the right way to test concurrency: **assert invariants and the set of valid outcomes**, rather than asserting which thread gets the CPU first.

## 8. Value vs. Exception Race: Who Completes First?

Two scenarios:

**Scenario A: success first, failure later**

```java
CompletableFuture<Integer> promise = new CompletableFuture<>();
boolean success = promise.complete(10);                 // true
boolean failure = promise.completeExceptionally(
        new IllegalStateException("late"));            // false
int value = promise.join();                             // 10
```

This is an illustrative snippet. The outcome is success, even though another producer arrives later claiming an error.

**Scenario B: failure first, success later**

```java
CompletableFuture<Integer> promise = new CompletableFuture<>();
boolean failure = promise.completeExceptionally(
        new IllegalStateException("first"));           // true
boolean success = promise.complete(10);                // false
// promise.join() throws CompletionException with cause IllegalStateException
```

There is no mechanism where "success always has priority over exception" or "exception always beats success". **Whichever succeeds first in the race** is what decides.

For systems that need a different policy, such as **waiting to see if any successful result arrives before a deadline** rather than taking the first outcome, a single `CompletableFuture` raced directly as above is **not enough**. You need a coordinator that tracks the number of sources, outcome types, and deadline before calling `complete` on the overall promise.

## 9. `isDone()` Does Not Prove Success

`isDone() == true` can happen after:

- `complete("OK")`.
- `complete(null)`.
- `completeExceptionally(new IOException(...))`.
- `cancel(true)` or `cancel(false)`.
- A timeout action completing the future exceptionally, e.g., `orTimeout`.

Therefore:

```java
if (future.isDone()) {
    // Cannot conclude a successful outcome here!
}
```

This is a reasoning counterexample. To know the outcome:

- Use `get()/join()` and distinguish success vs. exception/cancel.
- Use `whenComplete((value, error) -> ...)` to observe.
- `isCompletedExceptionally()` indicates error/cancellation, but does not return the cause.
- `isCancelled()` is more specific for cancellation.

**Check-then-act race:** checking `!future.isDone()` then calling `future.complete(value)` does not guarantee the `complete` call will succeed: another thread may complete in between. **Rely on the boolean returned by `complete`**, not on a pre-check.

## 10. `cancel()` in the Completion Race

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` is a way to complete exceptionally in the cancelled state. For `CompletableFuture`, the `mayInterruptIfRunning` parameter **is not used to send an interrupt to control work**.

Cases:

- Pending future receives `cancel(true)`/`cancel(false)`: future transitions to cancelled.
- `join()` on a cancelled future typically throws `CancellationException` directly.
- `get()` on a cancelled future throws `CancellationException`.
- `complete(value)` after cancellation returns false.
- `completeExceptionally(error)` after cancellation returns false.
- If success/failure already became terminal earlier, `cancel(...)` cannot change that outcome.
- Subsequent `cancel()` calls on an **already cancelled** future may still return true. Therefore, a `true` return from `cancel` is not equivalent to "I was the first to cancel".

### Example 4: Cancelling a pending future

Create the file `PendingCancellationDemo.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;

public class PendingCancellationDemo {
    public static void main(String[] args) {
        CompletableFuture<String> promise = new CompletableFuture<>();

        boolean firstCancel = promise.cancel(true);
        boolean repeatedCancel = promise.cancel(false);
        boolean lateValue = promise.complete("LATE");

        System.out.println("first cancel=" + firstCancel);
        System.out.println("repeated cancel=" + repeatedCancel);
        System.out.println("late value=" + lateValue);
        System.out.println("done=" + promise.isDone());
        System.out.println("cancelled=" + promise.isCancelled());
        System.out.println("exceptional="
                + promise.isCompletedExceptionally());

        try {
            promise.join();
        } catch (CancellationException e) {
            System.out.println("join cancellation="
                    + e.getClass().getSimpleName());
        }
    }
}
```

```bash
javac PendingCancellationDemo.java
java PendingCancellationDemo
```

Output:

```text
first cancel=true
repeated cancel=true
late value=false
done=true
cancelled=true
exceptional=true
join cancellation=CancellationException
```

This is a **no-worker** example; cancellation only controls the state of the promise. If a producer has already started computing on another thread and keeps running, cancelling the promise state **does not automatically interrupt or roll back the producer**.

**Do not use `cancel(true)` as a thread-kill command.** Cooperative cancellation is needed via tokens, I/O timeouts, executor ownership, or a dedicated task-stopping mechanism.

## 11. `completeExceptionally(new CancellationException(...))` vs. `cancel()`

A `CompletableFuture` can be completed exceptionally with an explicitly supplied `CancellationException`:

```java
CompletableFuture<String> f = new CompletableFuture<>();
f.completeExceptionally(
        new java.util.concurrent.CancellationException("not needed"));
```

This is an illustrative snippet. `CompletableFuture`'s observation methods may treat exceptional completion caused by `CancellationException` as cancelled. However, **do not use a `CancellationException` as an arbitrary business error** just because you like the class name. If work was cancelled at the caller's request, `cancel` conveys the meaning more clearly; if a task failed due to other logic, use an exception type that accurately expresses the cause.

For dependent stages, cancellation of the source typically causes dependents to complete exceptionally, possibly via a `CompletionException` wrapping `CancellationException`. **Do not assume every dependent automatically has `isCancelled() == true`** when the source is cancelled; inspect each stage's outcome.

## 12. Dependent Stages Triggered After the Promise Completes

A pending `CompletableFuture` can have continuations registered **before** the result is supplied:

```java
CompletableFuture<Integer> source = new CompletableFuture<>();

CompletableFuture<Integer> doubled =
        source.thenApply(x -> x * 2);

source.complete(21);

int result = doubled.join(); // 42
```

If `source` completes normally, `thenApply` receives the value and produces the output stage. If `source` completes exceptionally, the success transformation callback is typically **not executed**; the dependent stage completes exceptionally along the chain.

Important: `thenApply` **without `Async`** may run immediately on the thread calling `complete`. Therefore, do not assume `complete` is merely an O(1) assignment that triggers no application logic: completing the future can trigger the corresponding dependent actions.

### Example 5: Producer completes, consumer uses stages

Create the file `ManualCompletionPipelineDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ManualCompletionPipelineDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<Integer> doubled =
                    source.thenApply(x -> x * 2);
            CompletableFuture<Integer> plusOne =
                    doubled.thenApplyAsync(x -> x + 1, executor);

            System.out.println("source initially=" + source.isDone());
            System.out.println("complete accepted=" + source.complete(21));
            System.out.println("source result=" + source.join());
            System.out.println("doubled result=" + doubled.join());
            System.out.println("plus one=" + plusOne.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac ManualCompletionPipelineDemo.java
java ManualCompletionPipelineDemo
```

Output:

```text
source initially=false
complete accepted=true
source result=21
doubled result=42
plus one=43
```

`source.complete(21)` makes `source` terminal and allows dependent stages to run. `thenApply` may run directly on the caller; `thenApplyAsync(..., executor)` is submitted via the executor and may run on the executor's worker. Do not rely on thread names to prove values; the results 42 and 43 come from the math logic and the `join()` points.

## 13. Inline Callbacks Can Block Right During `complete()`

Example:

```java
CompletableFuture<String> pending = new CompletableFuture<>();
pending.thenApply(value -> {
    performSlowWork();
    return value.length();
});
pending.complete("hello");
```

This is an illustrative snippet, with `performSlowWork()` defined by the application. When `source` is completed, the `thenApply` callback may execute **right on the thread calling `complete`**. If the callback performs I/O or holds a lock for a long time, the thread completing `source` may be held up even though `source`'s result has already been decided.

Mitigations:

- For short, pure-computation callbacks, non-Async can be simple with less overhead.
- For long callbacks or when isolation is needed, consider `thenApplyAsync(..., executor)` or `whenCompleteAsync(..., executor)`.
- Pass an appropriate executor with clear ownership/lifecycle.
- Do not block indefinitely inside a completion callback if producers still depend on that callback.
- Remember that a specified executor may reject work during shutdown; the dependent stage may complete exceptionally due to rejection.

**An important nuance:** `complete(value)` can mark `source` as done **before every dependent stage finishes**. If you need to know the whole pipeline is finished, wait on **the final future**, rather than just checking `source.isDone()`.

## 14. Exceptions in Dependent Stages Differ from Exceptions in the Source

Suppose `source` completes successfully:

```java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> mapped = source.thenApply(value -> {
    throw new IllegalArgumentException("mapping failed");
});
source.complete("OK");
```

Then:

- `source` succeeds with `"OK"`.
- `mapped` fails because its callback threw an error.
- `source.join()` still returns `"OK"`.
- `mapped.join()` throws `CompletionException` wrapping `IllegalArgumentException`.

Do not conclude that "source completed successfully" means the entire workflow chain succeeded. Each `CompletionStage` has its own outcome.

Similarly, if a `whenComplete` is only intended for logging but its callback throws an error, the stage returned by `whenComplete` may differ in outcome according to its contract. Design logging so it does not throw arbitrary errors.

## 15. Example 6: Callback Fails While Source Still Succeeds

Create the file `DependentFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class DependentFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<Integer> mapped =
                source.thenApply(value -> {
                    throw new IllegalArgumentException("bad mapping");
                });

        source.complete("OK");

        System.out.println("source=" + source.join());
        System.out.println("source exceptional="
                + source.isCompletedExceptionally());
        System.out.println("mapped exceptional="
                + mapped.isCompletedExceptionally());

        try {
            mapped.join();
        } catch (CompletionException e) {
            System.out.println("mapped cause="
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

```bash
javac DependentFailureDemo.java
java DependentFailureDemo
```

Output:

```text
source=OK
source exceptional=false
mapped exceptional=true
mapped cause=IllegalArgumentException
```

The example does not use a separate executor because the throw occurs inside the continuation. `source.complete("OK")` sets the success outcome; `mapped`'s callback is where the new error originates. Callers must inspect the **future of the specific stage being observed** to find the error.

## 16. `get()` and `join()` Waiting on a Pending Promise

A caller can wait for the result:

```java
String value = promise.join();
```

If the promise is incomplete, `join()` can wait **indefinitely**. With `get()`, a timeout can be used:

```java
String value = promise.get(1, TimeUnit.SECONDS);
```

Distinguish the exceptions:

| API | Success Outcome | Error Outcome | Caller Interrupted | Timeout |
| --- | --- | --- | --- | --- |
| `join()` | Returns `T` | Usually `CompletionException` | Does not declare checked interrupt | Does not accept timeout |
| `get()` | Returns `T` | `ExecutionException` | `InterruptedException` | Does not accept timeout |
| `get(timeout, unit)` | Returns `T` | `ExecutionException` | `InterruptedException` | `TimeoutException` if not done |
| `getNow(defaultValue)` | Returns `T` if normally done | Throws unchecked exception if done with error/cancel | Non-blocking | Returns default if not done |

`get(timeout)` timing out **does not automatically complete the promise**. The caller may time out while the producer continues working and completes later. If timeout must become the outcome of **the promise itself**, you can use `orTimeout` or manually call `completeExceptionally` from a watchdog according to policy.

## 17. Caller Timeout vs. Completing the Promise with a Timeout Error

Two scenarios:

**A. Only the caller times out**

```java
try {
    promise.get(100, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    // The promise may still be incomplete and later complete successfully.
}
```

This is an illustrative snippet, assuming `promise` and imports are provided, with checked exceptions handled in an enclosing layer. The promise's outcome is not changed by `get` timing out.

**B. Watchdog attempts to complete the promise with an error**

```java
boolean accepted = promise.completeExceptionally(
        new TimeoutException("request expired"));
```

If the watchdog wins the race, the promise is exceptional. A producer arriving later and calling `complete(value)` will get `false`. If the producer won earlier, the watchdog gets `false` and the success result remains intact.

**These are two different API designs.** A only bounds how long the caller **waits**; B defines "deadline expiration is the shared outcome of the request". Choose according to the business contract.

### When the Deadline Has Expired

If the producer has external side effects, completing the promise with a timeout does not automatically stop the task, roll back a database, or cancel an external request outside the JVM. Separate cancellation/cleanup is required.

## 18. `orTimeout`: A Contender That Completes Exceptionally

In Java 17, `CompletableFuture.orTimeout(timeout, unit)` arranges for the future to **complete exceptionally with `TimeoutException` if it is still incomplete when the timeout arrives**. This method returns **the same CompletableFuture**, not a completely separate wrapper.

```java
CompletableFuture<String> promise = new CompletableFuture<>();
promise.orTimeout(200, TimeUnit.MILLISECONDS);
```

If the producer calls `complete("OK")` before the timeout, the future remains successful and the timeout action cannot overwrite it via normal completion. If the timeout wins, a producer calling `complete` afterward receives `false`.

### Example 7: `orTimeout` definitely wins when there is no producer

Create the file `OrTimeoutPendingDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class OrTimeoutPendingDemo {
    public static void main(String[] args) {
        CompletableFuture<String> promise = new CompletableFuture<>();
        CompletableFuture<String> same =
                promise.orTimeout(20, TimeUnit.MILLISECONDS);

        System.out.println("same instance=" + (same == promise));

        try {
            promise.join();
        } catch (CompletionException e) {
            System.out.println("cause="
                    + e.getCause().getClass().getSimpleName());
            System.out.println("timeout cause="
                    + (e.getCause() instanceof TimeoutException));
        }

        System.out.println("done=" + promise.isDone());
        System.out.println("late success=" + promise.complete("LATE"));
    }
}
```

```bash
javac OrTimeoutPendingDemo.java
java OrTimeoutPendingDemo
```

Output if the JVM continues executing without abnormal interference:

```text
same instance=true
cause=TimeoutException
timeout cause=true
done=true
late success=false
```

There is no producer to complete before the timeout, so the watchdog eventually transitions the promise to exceptional completion. `orTimeout` mutates **the very future it is called on**, so other places holding a reference to the same promise also receive the timeout outcome.

## 19. `completeOnTimeout`: Timeout Turns into a Successful Result

`completeOnTimeout(value, timeout, unit)` is similar to `orTimeout` in scheduling a completion option when not yet done, except if the timeout wins it completes **normally** with `value`:

```java
promise.completeOnTimeout("FALLBACK", 100, TimeUnit.MILLISECONDS);
```

The method also returns **the same CompletableFuture** it was called on. If the producer completes first, the fallback does not overwrite it. If the fallback wins, the producer completing later gets `false`.

### Example 8: Fallback wins

Create the file `CompleteOnTimeoutDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class CompleteOnTimeoutDemo {
    public static void main(String[] args) {
        CompletableFuture<String> promise = new CompletableFuture<>();

        CompletableFuture<String> returned =
                promise.completeOnTimeout(
                        "FALLBACK", 20, TimeUnit.MILLISECONDS);

        System.out.println("same instance=" + (returned == promise));
        System.out.println("result=" + promise.join());
        System.out.println("late normal=" + promise.complete("ACTUAL"));
        System.out.println("exceptional="
                + promise.isCompletedExceptionally());
    }
}
```

```bash
javac CompleteOnTimeoutDemo.java
java CompleteOnTimeoutDemo
```

Output when there is no other producer:

```text
same instance=true
result=FALLBACK
late normal=false
exceptional=false
```

**Warning:** returning `FALLBACK` **does not prove the real data source completed**. If you need to distinguish the real source from a fallback, use a result type with metadata such as `Result(value, fromFallback)` or an appropriate sealed hierarchy.

A valid fallback for display might be stale cached data; a default fallback for a financial transaction could be a serious mistake. That is a business decision, not a `CompletableFuture` decision.

## 20. Three-Way Timeout Race: complete, exceptional, cancel

A pending promise can simultaneously receive:

```text
Thread IO       -> complete(response)
Thread watchdog -> completeExceptionally(new TimeoutException())
Thread caller   -> cancel(true)
```

The outcome depends on **which completion call wins first**. There is no guarantee that the timeout always wins after the wall clock passes the mark if the producer already called `complete` before the timeout action executed; nor is there any guarantee that the producer is prioritized.

To clarify the policy:

- If **success wins**, the caller receives the response; subsequent timeout/cancel cannot replace it via normal completion.
- If **exception wins**, the caller receives the error; subsequent success is ignored by the promise state.
- If **cancel wins**, the caller receives `CancellationException`; subsequent `complete` calls fail.
- Losing producers may still execute external logic; stopping them requires a separate protocol.

A distributed system sometimes needs a stricter "real-time deadline" than "the timeout task happened to run": check `System.nanoTime()` and coordinate with a state machine holding the deadline, rather than relying solely on the order in which threads are scheduled.

## 21. Why Not `if (!isDone()) complete(...)`?

Counterexample:

```java
if (!promise.isDone()) {
    promise.complete("OK");
    sendAcknowledgement();
}
```

If another thread completes **between** the two statements, `promise.complete("OK")` returns false yet `sendAcknowledgement()` still runs, as if the current thread won.

Better:

```java
if (promise.complete("OK")) {
    sendAcknowledgement();
}
```

This is an illustrative snippet. The returned boolean is the result that decides **win/loss of the `complete` call**.

**Still, there is a limitation:** `sendAcknowledgement()` is not in the same transaction as `complete()`. If sending the ack fails or the process crashes between the two steps, there is no exactly-once guarantee. You must design idempotency/outbox/transactions if the ack is a critical side effect.

Similarly, if `completeExceptionally` returns false, do not record "timeout won" just because the watchdog ran. Observe the actual outcome or record a "timeout attempt lost" metric.

## 22. Example 9: Deterministically Simulating Success Beating Timeout

Create the file `DeterministicSuccessWinsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class DeterministicSuccessWinsDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> promise = new CompletableFuture<>();
        CountDownLatch successWritten = new CountDownLatch(1);
        AtomicBoolean timeoutAccepted = new AtomicBoolean();

        Thread success = new Thread(() -> {
            promise.complete("RESPONSE");
            successWritten.countDown();
        });

        Thread timeout = new Thread(() -> {
            try {
                successWritten.await();
                timeoutAccepted.set(
                        promise.completeExceptionally(
                                new TimeoutException("late watchdog")));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        success.start();
        timeout.start();
        success.join();
        timeout.join();

        System.out.println("result=" + promise.join());
        System.out.println("timeout accepted=" + timeoutAccepted.get());
        System.out.println("done=" + promise.isDone());
    }
}
```

```bash
javac DeterministicSuccessWinsDemo.java
java DeterministicSuccessWinsDemo
```

Output when not externally interrupted:

```text
result=RESPONSE
timeout accepted=false
done=true
```

`CountDownLatch` forces the watchdog to attempt `completeExceptionally` only **after** the source success has been written. This is a test of the **success-before-timeout policy**, not a test of random race outcomes. To test a true race without imposing order, use `ConcurrentCompletionRaceDemo` in section 7.

## 23. Race of Multiple Callbacks and Ordering Consequences

A `CompletableFuture` can have multiple dependent stages:

```java
source.thenAccept(value -> auditA(value));
source.thenAccept(value -> auditB(value));
source.thenAccept(value -> auditC(value));
```

This is an illustrative snippet with application helpers. When `source` completes, eligible actions run, but **you should not rely on the order of A/B/C** unless the pipeline creates an explicit dependency.

If audit B must run after audit A, you can chain them:

```java
CompletableFuture<Void> ordered =
        source.thenAccept(value -> auditA(value))
              .thenRun(() -> auditB());
```

This is an illustrative snippet. `thenRun` runs only when the preceding stage succeeds. Independent callbacks registered on the same source have no "registration order" contract.

Also note that **the moment `complete()` returns is not necessarily the moment all dependent stages have finished running**. Completing the source and completing the entire pipeline are two different events. Use `ordered.join()` or the final future to confirm all required steps have completed.

## 24. Completing a Future from an External Callback

A callback-based API may not return a `CompletionStage`, instead invoking `onSuccess/onFailure` later. We can wrap it with a pending future:

```java
CompletableFuture<String> promise = new CompletableFuture<>();

api.start(
    value -> promise.complete(value),
    error -> promise.completeExceptionally(error)
);

return promise;
```

This is **illustrative pseudocode**: `api.start` and the callbacks are defined by the library/application. To use it safely, you need:

1. **Single-callback policy:** the library might invoke callbacks abnormally multiple times; use the `boolean` return to detect late/duplicate notifications.
2. **Immediate error at registration:** `api.start` might throw an exception synchronously; call `completeExceptionally` in a catch block or return the error per contract.
3. **Timeout/cancel:** the caller might not wait forever; attach a deadline and a mechanism to stop the external source.
4. **Resource lifecycle:** if the caller cancels the promise, `api` is not necessarily cancelled.
5. **Context and correlation ID:** multiple concurrent requests must ensure each callback maps to the right request's promise.
6. **Multi-event publisher:** a `CompletableFuture` represents only **one terminal outcome**, not a multi-event data stream. If continuous emission is needed, use a different abstraction such as `Flow.Publisher` or a queue.

**Do not complete the promise via a callback before registering necessary resources/cleanup**, if doing so allows the consumer to start processing before the producer is ready. Design clear ownership for the request's state machine.

## 25. Example 10: Simulating a Callback Adapter That May Fire Twice

Create the file `CallbackAdapterDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class CallbackAdapterDemo {
    static void simulateCallback(
            java.util.function.Consumer<String> onSuccess,
            java.util.function.Consumer<Throwable> onFailure) {

        onSuccess.accept("DATA");
        onFailure.accept(new IllegalStateException("late error"));
    }

    public static void main(String[] args) {
        CompletableFuture<String> promise = new CompletableFuture<>();
        AtomicInteger accepted = new AtomicInteger();

        simulateCallback(
                value -> {
                    if (promise.complete(value)) {
                        accepted.incrementAndGet();
                    }
                },
                error -> {
                    if (promise.completeExceptionally(error)) {
                        accepted.incrementAndGet();
                    }
                }
        );

        System.out.println("accepted=" + accepted.get());
        System.out.println("result=" + promise.join());
        System.out.println("exceptional="
                + promise.isCompletedExceptionally());
    }
}
```

```bash
javac CallbackAdapterDemo.java
java CallbackAdapterDemo
```

Output:

```text
accepted=1
result=DATA
exceptional=false
```

The adapter is written to **intentionally** report success then failure; the later failure does not change the result. This scenario illustrates duplicate/late callbacks. In a real API, you can log a late completion separately as a protocol error signal, without sending a second response to the consumer.

## 26. Ensuring a Promise Is Never Left Pending Forever

`new CompletableFuture<>()` is very flexible, but it is also easy to forget to complete a branch:

```java
CompletableFuture<String> promise = new CompletableFuture<>();

if (inputValid) {
    startAsyncWork(promise);
}
// If input is invalid and there is no else branch, the promise stays pending.
return promise;
```

This is a **counterexample**. The caller may wait forever and dependent stages remain stuck waiting.

When designing an adapter, trace all paths:

- Source succeeds → `complete(value)`.
- Source fails → `completeExceptionally(error)`.
- Cannot start work → complete exceptionally or throw an exception per API.
- Caller cancels → close/cancel the external source if the contract requires it.
- Expires → `orTimeout` or a watchdog with a clear error/fallback.
- Process/service shutdown → decide outcomes for still-pending promises and release resources.
- Callback arrives after timeout/cancellation → `complete` returns false; code must not assume the call won.

Set **reasonable timeout bounds**, preferring to propagate an end-to-end deadline rather than giving each step a fresh full timeout.

## 27. Pending Futures Can Retain Dependent Stages and Data for a Long Time

When creating many dependent stages on a pending `CompletableFuture`:

```java
source.thenApply(value -> expensiveObject.transform(value));
```

This is an illustrative snippet. The closure may hold references to `expensiveObject`, request context, buffers, or other resources. If `source` **never completes**, dependent actions and references can be retained longer than expected.

This can cause significant **memory retention** in services handling hundreds of thousands of requests. A pending future is not a leak in every case; it is a valid state while the producer is still running. However, when the request logic has ended and the promise remains pending, callbacks/waiters are not released as expected.

Reduce the risk by:

- Having a clear owner for each promise; setting deadlines and cleanup.
- Not repeatedly registering new callbacks onto the same pending future forever.
- Removing correlation IDs from the pending request map upon completion/cancellation.
- Avoiding capturing large objects in lambdas unnecessarily.
- Monitoring pending promise counts and lifetimes, not just thread counts.
- Not keeping an unbounded queue of tasks waiting on a future that has no producer.

`getNumberOfDependents()` exists to estimate the number of incomplete dependents, but it is only suitable for **monitoring/debugging**, not as an exact counter to drive correctness.

## 28. End-to-End Deadline: Do Not Reset Timeouts Across Steps

A workflow might do:

```java
a.get(1, TimeUnit.SECONDS);
b.get(1, TimeUnit.SECONDS);
c.get(1, TimeUnit.SECONDS);
```

If each call has a 1-second timeout, the total wait time can approach 3 seconds. When the business requirement is **1 second total**, a shared time budget must be used.

Idea:

```java
long startedAt = System.nanoTime();
long totalNanos = TimeUnit.SECONDS.toNanos(1);

long remaining = Math.max(
        0L, totalNanos - (System.nanoTime() - startedAt));
String first = a.get(remaining, TimeUnit.NANOSECONDS);

remaining = Math.max(
        0L, totalNanos - (System.nanoTime() - startedAt));
String second = b.get(remaining, TimeUnit.NANOSECONDS);
```

This is an illustrative snippet inside a method declaring the appropriate checked exceptions, with `a` and `b` being `CompletableFuture<String>`. `System.nanoTime()` measures monotonic elapsed time within the same JVM, not a Unix timestamp.

When the budget expires, the caller can stop waiting, call `completeExceptionally` on the overall promise, or request cancellation per policy. Do not treat a `TimeoutException` from `get(timeout)` as proof that the source has stopped.

## 29. Java Memory Model: Publishing Results Across Threads

One producer side typically builds a result and then completes:

```java
Result result = buildResult();
promise.complete(result);
```

A consumer on another thread calls `promise.get()`/`join()` and then reads the result. `CompletableFuture` implements synchronization for completion, and `Future.get()` provides memory consistency guarantees that publish actions of the asynchronous computation to the thread that receives the result.

However, understand this accurately:

- **Completing a future publishes the result reference**, it does not clone the object.
- If the producer keeps mutating a mutable object **after `complete`** without synchronization, readers can encounter a data race.
- If `result` is an immutable object fully constructed before `complete`, it is much easier for consumers to reason about correctness.
- If the producer throws an error after completing with success, the future does not automatically switch to failure.
- If the producer performs side effects outside the JVM before/after completion, `CompletableFuture` does not create a transaction for the database, filesystem, or network.

A safe pattern is to build a complete immutable record/DTO first and only then call `complete(result)`. Do not do `complete(new ArrayList<>())` and then have multiple threads unsynchronizedly add to the list.

### Happens-Before and Callbacks

Dependent stages observe the completed result according to `CompletableFuture`'s synchronization protocol. However, if a callback grabs another unrelated shared mutable object and modifies it concurrently, the future does not automatically resolve data races on that object. Use proper ownership, locks, atomics, or concurrent collections.

## 30. Avoid Calling `join()` Inside a Producer Holding a Lock

A liveness risk:

- Thread A holds lock L and then waits on `promise.join()`.
- Thread B needs lock L to compute the result and call `promise.complete(...)`.
- A does not release L because it is waiting; B cannot acquire L; the promise never completes.

That is a **deadlock** caused by the lock-and-completion protocol, not a bug in `join` alone.

Another risk: thread A calls `complete()` while holding lock L. A non-Async dependent callback is triggered inline and tries to call an API that waits on thread B; B in turn needs lock L. The result can be deadlock or unexpected latency spikes.

Recommendations:

1. Avoid triggering complex completion callbacks while holding a business lock if the callbacks might run inline.
2. Avoid blocking on `join/get` inside a critical section when the producer needs the same lock.
3. Use lightweight continuations and an explicit executor when decoupling is needed.
4. Establish consistent lock ordering and ownership.
5. Have deadlines/cancellation for potentially long waits; however, timeouts do not automatically resolve deadlocks if there is no cleanup path.

## 31. `complete()` from Multiple Threads Does Not Replace Side-Effect Coordination

When using a promise as "first response wins", you might imagine:

```java
if (promise.complete(receivedResult)) {
    publishResponse(receivedResult);
}
```

This is an illustrative snippet. Using the boolean return prevents **losing callers** from also publishing a response like the winner, but it does not provide exactly-once delivery in an environment with crashes/retries.

Points to consider:

- If `publishResponse` fails after the promise has already completed, consumers of the promise may already have received the success outcome even though the external response was not sent.
- If two producers call a service with side effects **before `complete`**, both side effects may already have occurred even though only one promise outcome wins.
- If a timeout completes exceptionally first, a producer arriving later may still commit to the database.
- If the consumer needs "first SUCCESS" rather than "first TERMINAL outcome", a single future directly raced with exceptional completions is a model lacking policy.

It is usually better to **decouple result arbitration** from the lifecycle of source tasks, using idempotency/correlation IDs and a manager for completion attempts.

## 32. `allOf()`, `anyOf()`, and the Completion Race

`CompletableFuture.anyOf(a, b, c)` completes when one of the input futures completes, **normally or exceptionally**. It does not promise to pick "the first successful response".

`CompletableFuture.allOf(a, b, c)` completes when all input futures have completed; if one or more inputs fail, the combined future can complete exceptionally. It does not automatically collect results into a `List<T>` and is not a command to cancel remaining tasks.

If you want to coordinate "**complete when the first successful result arrives, but only report an error when all sources fail**", you need additional state:

- Count how many producers have finished.
- Each success tries `promise.complete(value)`.
- Each failure records the cause and increments the count.
- Only when **all producers have failed** attempt `completeExceptionally`.
- Ensure failure counts/collections are thread-safe and race-free at the decision step.
- Have deadlines/cancellation and avoid duplicate side effects.

An `AtomicInteger` for failure count and completion primitives can help, but you must prove **the exact number of sources and handle the race between a success and "all failed"**. Do not replace the entire design with `anyOf` if semantics require "first success".

## 33. `completeAsync` and `supplyAsync` Differ from Manual Completion

JDK 17 provides `CompletableFuture.completeAsync(Supplier[, Executor])`: it schedules **a Supplier to attempt to complete the current CompletableFuture itself**, rather than creating a new source CompletableFuture like `supplyAsync`.

Example:

```java
CompletableFuture<String> promise = new CompletableFuture<>();
promise.completeAsync(() -> "computed", executor);
```

This is an illustrative snippet, assuming `executor` exists and is properly managed. Distinguish:

- `promise.complete("known")`: attempts to complete **immediately with an already-known value**.
- `promise.completeExceptionally(error)`: attempts to complete **immediately with an error**.
- `promise.completeAsync(supplier, executor)`: schedules the supplier to **attempt to complete the current promise later**.
- `CompletableFuture.supplyAsync(supplier, executor)`: creates **a new future** completed by the supplier.

Because there can be a race, `complete("manual")` may win before `completeAsync` finishes running; the scheduled supplier may still execute/consume resources depending on runtime conditions. Do not rely on `completeAsync` as a guarantee that "only one piece of work actually runs" when there is contention.

## 34. `obtrudeValue` and `obtrudeException` Are Exceptions to the Single-Completion Rule

Two advanced APIs of `CompletableFuture`:

```java
promise.obtrudeValue("FORCED");
promise.obtrudeException(new IllegalStateException("FORCED_ERROR"));
```

They can **forcibly replace the state/result observed by subsequent reads**, even when the future is already completed. This is an exceptional mechanism, mainly intended for special recovery, not normal flow.

**Extremely important:** dependent stages that already completed or are running may have received the **outcome before obtrude**, while subsequent reads receive the new outcome. That breaks the simple reasoning that the entire system sees the same terminal result.

Therefore:

- Do not use `obtrudeValue/obtrudeException` to "fix an accidental `complete`" in normal business flows.
- Do not use them to arbitrate winning/losing producers.
- If a result needs to be corrected, create **a new future/version** or an application state machine with explicit versioning.
- Be cautious when a library exposes a mutable `CompletableFuture` in its API: callers could unexpectedly call `complete`/`obtrude`.

The "first completion wins" rule in this lesson applies to **normal completion methods**, excluding forced state-replacement operations.

## 35. API Design: Who Has Permission to Complete?

A method that only wants callers to **read the result** should not necessarily return a mutable `CompletableFuture` directly if it wants to keep outcome-deciding authority within one component.

Example:

```java
final class PendingRequest {
    private final CompletableFuture<String> writable =
            new CompletableFuture<>();

    public java.util.concurrent.CompletionStage<String> result() {
        return writable.minimalCompletionStage();
    }

    void succeed(String value) {
        writable.complete(value);
    }

    void fail(Throwable error) {
        writable.completeExceptionally(error);
    }
}
```

This is a structurally self-contained illustrative class without `main`; `minimalCompletionStage()` is available in JDKs supporting Java 17. It returns a view with `CompletionStage` methods suitable for composition, reducing the chance of callers directly invoking mutable completion APIs on the internal promise.

**Do not treat this as an absolute security boundary.** A caller can call `toCompletableFuture()` on the stage to obtain a `CompletableFuture` controllable per the view's contract; the goal is to avoid accidentally handing out write access to **the original promise**, and to make API ownership explicit.

If a library genuinely needs to support cancellation from callers, design a `cancelRequest(id)` method or a handle with a dedicated contract rather than letting callers call arbitrary `complete(...)` methods on a future owned by the producer.

## 36. Retries and Multiple Completion Attempts

When a request allows retries, distinguish between **one logical request** and **multiple physical attempts**. If the first attempt throws an exception, you should not necessarily call `completeExceptionally` on the overall promise immediately if the policy requires a retry.

A reasonable model:

```text
Request promise P (pending)
    |
  Attempt #1 fails
    |
  policy allows retry?
    +-- yes --> Attempt #2 starts --> success --> P.complete(value)
    |
    +-- no -------------------------> P.completeExceptionally(error)
```

If attempt #1 and #2 run concurrently, the result must be coordinated by policy: first success, fastest response, best quality, deadline, or consensus. Do not call `completeExceptionally` for every failure if other sources can still succeed, unless the desired outcome is "any error appearing first fails the request".

When retrying side-effecting operations, idempotency/reconciliation is required. A task that loses the race **may already have performed a side effect** before `complete` returned false.

## 37. Testing Races and Terminal States Properly

### What to Assert

1. Right after `new CompletableFuture<>()`, `isDone() == false`.
2. The first `complete` call succeeds; the subsequent call fails.
3. The first `completeExceptionally` call succeeds; `get/join` reports the right cause.
4. When multiple threads race, the total count of **`true` booleans** from `complete/completeExceptionally` in a single-shot race is **1**.
5. The future is not altered by a late `complete`.
6. After `cancel`, `get/join` reports cancellation; `complete` returns false.
7. After a timeout applied to the future itself via `orTimeout`, subsequent `complete` calls return false when the timeout wins.
8. Source completion does not mean dependent stages have completed.
9. Cross-thread state must be observed using latches/`Future`/`join`, not guessed with `Thread.sleep`.

### Do Not Assert That the Winner Is A or B

Without synchronization to force ordering, the runtime chooses the schedule. A test that only passes when "A wins" is a flaky test. `ConcurrentCompletionRaceDemo` checks invariants rather than a specific winner.

### Clean Up Both Threads and Executors

A pending-promise test easily hangs if a producer is interrupted before completing. Use `finally` blocks to release latches, handle cancellation, and shut down the test's executor; otherwise, the test suite may leave workers waiting forever.

### Do Not Use `getNumberOfDependents()` as a Correctness Condition

This number is only an **estimate for monitoring**, not an exact latch. If you need to know downstream has finished, keep a reference to the dependent `Future` and call `join/get` on it.

## 38. Common Pitfalls When Using a Pending CompletableFuture

### 38.1. Creating a promise with no producer to complete it

`new CompletableFuture<>()` does not run work on its own. If you miss any success/failure/cancel/timeout branch, waiters can hang forever.

### 38.2. Assuming every `complete(value)` overwrites

Only the winning `complete` call while the future is still pending transitions the state. Subsequent calls return false.

### 38.3. Not checking the boolean after `complete`

If a side effect depends on whether this caller was the winner, you must check the returned boolean. Even then, side effects outside the future still have no exactly-once guarantee.

### 38.4. Checking `isDone` first then calling `complete` as if it were transactional

`if (!isDone()) complete(...)` has a check-then-act race. Use the result of `complete(...)` itself to determine who won.

### 38.5. Thinking exceptional always takes priority over success

There is no fixed priority. Success/failure/cancel compete for the same terminal state, per the API contract.

### 38.6. Confusing `get(timeout)` with `orTimeout`

`get(timeout)` only bounds the caller's wait; it does not complete the promise. `orTimeout` can put **the future itself** into exceptional completion on timeout.

### 38.7. Thinking `completeOnTimeout` only creates a fallback wrapper

The method returns the same future, so a winning fallback becomes the outcome of **the original future itself**, affecting all consumers holding that reference.

### 38.8. Thinking `cancel(true)` always interrupts the worker

For `CompletableFuture`, `mayInterruptIfRunning` does not control execution via interruption; a separate task-stopping protocol is needed.

### 38.9. Counting `cancel(true)` returns to find the winner

Repeated `cancel` calls after already cancelled can still return true; do not use this return value as a unique counter for state transitions.

### 38.10. Ignoring callback errors in dependent stages

The source may succeed while a dependent fails. Track **the final future** or each business-meaningful stage.

### 38.11. Running blocking callbacks on the thread calling `complete`

Non-Async continuations can run inline. If a callback blocks for a long time under a lock, it can cause latency or deadlock.

### 38.12. Using `obtrude` to fix outcomes in normal flows

`obtrude` can cause old and new consumers to see different outcomes. Do not use it as a normal competing completion.

### 38.13. Exposing a mutable `CompletableFuture` in a public API

Callers can invoke `complete/completeExceptionally/cancel` when they do not own the decision. Consider a `CompletionStage` view and clear contract ownership.

### 38.14. Completing with success too early

If `complete(result)` happens before the object is fully constructed or mandatory side effects are committed, consumers may act on inconsistent state. Publish an immutable result after required work is done.

### 38.15. Thinking timeout/cancellation rolls back tasks

A terminal promise does not roll back databases, stop RPCs, or close sockets. Task-level cancellation and cleanup remain a separate concern.

### 38.16. Using `CompletableFuture` for an unbounded stream

A promise is for a single terminal result. Multi-event data needs streams/queues/publishers; do not try to complete the same future multiple times to send multiple messages.

## 39. Checklist for Designing a Good Promise

Before implementing a pending `CompletableFuture<T>`, ask:

- **Who owns it?** Which component is allowed to call `complete/completeExceptionally`?
- **Who is the producer?** A callback, worker, RPC response, or multiple competing sources?
- **What are the outcomes?** Success value, error, cancellation, timeout; clearly distinguish each branch.
- **Where is the deadline?** Does the caller just stop waiting, or must the request future itself terminate with a timeout?
- **Does the coordinator need first success?** If so, do not let each failure directly terminate the promise prematurely.
- **How is the boolean return used?** Who is permitted to perform side effects upon winning?
- **How are late callbacks handled?** Ignore, record a metric, release resources, avoid duplicate responses?
- **Where is cleanup?** Does a cancelled/timed-out producer stop network, I/O, workers, and remove entries from the correlation map?
- **Are continuations blocking?** Consider the executor and the risk of callbacks running inline.
- **Is the result mutable?** Publish an immutable snapshot or use appropriate synchronization.
- **Who shuts down executor resources?** Avoid thread leaks caused by pending tasks.
- **Are tests deterministic?** Use latches/barriers for intentional ordering; race tests check invariants rather than a fixed winner.
- **Are there multiple dependent stages?** Wait on the final future, not just `source.isDone()`.
- **Are there critical side effects?** Idempotency, state commits, retries, and failure reporting belong to the business layer.

## 40. Practice Exercises

**Exercise 1 – Pending then success.** Create a pending `CompletableFuture<Integer>`. Verify `isDone() == false`; call `complete(7)`, verify true and `join() == 7`; call `complete(9)`, verify false and the result is still 7.

**Exercise 2 – Exception wins.** Create a pending promise, call `completeExceptionally(new IOException("missing"))`. Observe `join` throwing `CompletionException` and `get` throwing `ExecutionException`, both with the corresponding cause; `complete("OK")` afterward returns false.

**Exercise 3 – Two producers racing for a value.** Have two threads wait on a latch and then call `complete("A")`/`complete("B")`. Assert only one boolean is true and the result is in `{"A", "B"}`. Do not assert a fixed winner.

**Exercise 4 – Value, exception, cancel.** Add a watchdog calling `completeExceptionally` and a caller calling `cancel`. Observe specifically: repeated `cancel` calls can return true when the future is already cancelled, so the way winners are counted must change when `cancel` is included.

**Exercise 5 – Timeout does not complete the future.** Use `get(30, MILLISECONDS)` on a pending promise with no producer; catch `TimeoutException` and verify the promise is still incomplete. Then call `complete("LATE")` and `join()` successfully.

**Exercise 6 – `orTimeout` wins.** Use `orTimeout(30, MILLISECONDS)` on a promise with no producer, call `join` and receive cause `TimeoutException`; try `complete` afterward and verify false.

**Exercise 7 – `completeOnTimeout`.** Use `completeOnTimeout("DEFAULT", ..., ...)` on a pending future; verify the fallback result. Add a real producer around the same time and only assert valid outcomes if ordering is not forced.

**Exercise 8 – Dependent pipeline.** Register `thenApply(x -> x * 2)` and `thenApplyAsync(x -> x + 1, executor)`, call `complete`, and wait on the final stage; distinguish source done from entire pipeline done.

**Exercise 9 – Callback adapter.** Write an `onSuccess/onFailure` callback adapter targeting a promise. Intentionally deliver two callbacks and verify the late completion does not alter the outcome. Add correlation ID cleanup.

**Exercise 10 – First-success policy.** Given three sources where two fail and one succeeds, design a coordinator so the overall promise only fails when all three fail, not when the first source fails. Test with sources completing in different orders.

## 41. Self-Check Questions

**Question 1.** Does `new CompletableFuture<String>()` automatically run a Supplier?

**Answer:** No. It creates an incomplete future; another producer/callback must complete it or handle timeout/cancellation.

**Question 2.** What does `complete("A")` returning true mean?

**Answer:** This call transitioned the future from incomplete to normal completion with `"A"`.

**Question 3.** What happens if after `complete("A")` another thread calls `complete("B")`?

**Answer:** It returns false and the result remains `"A"` under normal completion.

**Question 4.** Does `completeExceptionally(error)` take a `Throwable` or a String?

**Answer:** It takes a non-null `Throwable`. `completeExceptionally(null)` is invalid.

**Question 5.** If success and failure call `complete` concurrently on a pending future, is one outcome prioritized?

**Answer:** There is no default priority. Whichever completion call wins first decides the outcome.

**Question 6.** Does `if (!isDone()) complete(v)` guarantee `complete` will succeed?

**Answer:** No. There is a race between the check and the update. Use the boolean returned by `complete`.

**Question 7.** Does `cancel(true)` always interrupt the computing thread?

**Answer:** No. For `CompletableFuture`, `mayInterruptIfRunning` does not control execution via interruption.

**Question 8.** Why shouldn't you count `cancel() == true` to know who won?

**Answer:** After a future is already cancelled, repeated `cancel` calls can continue to return true; they do not necessarily represent a new state transition.

**Question 9.** Does `get(timeout)` throwing `TimeoutException` complete the future exceptionally?

**Answer:** Not automatically. That is the waiting caller's timeout; the promise may still be pending.

**Question 10.** Does `orTimeout` create a different wrapper future?

**Answer:** No. It returns the same `CompletableFuture` it was called on and can complete that future exceptionally on timeout.

**Question 11.** Does `completeOnTimeout` complete normally or exceptionally when the timeout wins?

**Answer:** It completes normally with the passed fallback value.

**Question 12.** Once a source future has completed, are its dependent stages guaranteed to be done?

**Answer:** No. Dependents may still be scheduled or executing; you must wait on the dependent future.

**Question 13.** Can `thenApply` on a pending future run on the thread calling `complete`?

**Answer:** Yes. Non-Async callbacks can run inline when the source completes.

**Question 14.** If the source succeeds but `thenApply` throws an exception, does the source switch to an error state?

**Answer:** No. The dependent stage fails, while the source retains its success outcome.

**Question 15.** Can `obtrudeValue` be used like a normal second `complete`?

**Answer:** It should not be. It forcibly replaces the outcome observed afterward and can cause discrepancies with dependents that already received the old outcome.

**Question 16.** Does `CompletableFuture.anyOf` promise to complete only when a source succeeds?

**Answer:** No. A failing source can cause `anyOf` to complete exceptionally before other successful sources finish.

**Question 17.** Why shouldn't a late callback after a timeout send a second response?

**Answer:** The promise is already terminal; `complete` returns false. Sending an extra response can create duplicates or violate the protocol.

**Question 18.** What problem can a pending promise holding a large closure cause?

**Answer:** Memory retention: if it never completes or gets cleaned up, dependent stages/objects can be retained for a long time.

**Question 19.** Does completing a future with a mutable object make that object thread-safe?

**Answer:** No. The future publishes the reference/result; subsequent mutable modifications still require synchronization/ownership.

**Question 20.** If we want "first success, report error only when all fail", is it enough to have every failure call `completeExceptionally` directly?

**Answer:** No. The first failure could win, blocking a later success. A coordinator is needed to track outcomes and count remaining sources.

## 42. Summary

`new CompletableFuture<T>()` creates an **incomplete promise**. `complete(value)` attempts normal completion, and `completeExceptionally(error)` attempts exceptional completion; both return a boolean indicating **whether this call won the state-transition race**. With multiple threads, the fundamental rule is **first successful completion wins**, with no fixed priority between success and failure.

However, keep these boundaries in mind:

- **`cancel`** participates in the terminal race and has different boolean semantics from `complete` methods; repeated `cancel` calls when already cancelled can still return true.
- **`get(timeout)`** only times out the caller's wait; **`orTimeout`** and **`completeOnTimeout`** can decide the outcome of **the future itself**.
- **Source completed** does not mean **all dependent stages have finished**. Non-Async callbacks can run inline right on the completing thread.
- **Cancellation/timeout does not automatically stop producers**, roll back databases, or guarantee exactly-once side effects.
- **`obtrudeValue/obtrudeException`** are special APIs that can forcibly replace outcomes and must not be treated as normal completions.
- **A promise is not a stream**: if there are multiple events or multiple attempts, you need an explicit coordinator and protocol.
- **Do not depend on thread scheduling in tests**; use latches to coordinate or assert invariants and the set of valid outcomes.

A reliable design always clearly defines **the owner permitted to complete**, the success/error/timeout/cancel branches, the policy for late results, resource cleanup, and how to check the final future. That is how `CompletableFuture` serves as a safe bridge between threads and callbacks in Java concurrency.
