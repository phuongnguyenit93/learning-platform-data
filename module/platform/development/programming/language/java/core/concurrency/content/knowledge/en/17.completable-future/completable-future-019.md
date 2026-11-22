# CompletableFuture.getNow(): Reading Results Without Blocking and Distinguishing null from Incomplete

> **Core takeaway:** In Java 17, `CompletableFuture<T>.getNow(T valueIfAbsent)` **does not wait** for the computation to complete. If the Future is **not yet completed**, it immediately returns the **fallback value** `valueIfAbsent`. If it has completed normally, it returns the **actual result**, even when the actual result is `null`. If it completed exceptionally or was cancelled, the call may **throw an exception immediately**; `valueIfAbsent` is not a fallback to mask errors. Therefore, `getNow(null) == null` is **not sufficient to conclude that the Future is pending**: two different states produce the same observed value.

This article belongs to the **CompletableFuture** group, covering **general Java concurrency** per the Special Note, using Java SE 17+. No Spring is used. The goal is to read state **without blocking the calling thread**, distinguish a valid `null` result from a missing result, understand error/cancellation behavior, and avoid races in asynchronous systems.

## 1. The Practical Problem

Suppose an API has started asynchronous work:

~~~java
// API snippet, not a standalone program.
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(this::loadDisplayName);
~~~

While rendering a dashboard or reading a cache, the caller wants to know: **if the result is already ready, take it immediately**; otherwise, display a loading state. The caller **does not want to wait** for the worker to finish processing.

There is a common misconception:

~~~java
// INCORRECT CODE for distinguishing states:
String value = future.getNow(null);
if (value == null) {
    // Cannot be certain this means "loading".
}
~~~

`null` can be a valid result—for example, "name not found", "no suggestions", or a `CompletableFuture<Void>` that completed normally. When `null` is used as both a **business result** and a **pending signal**, the caller loses the ability to distinguish the two states.

### Three Separate Questions

1. **Has the task completed?** Check `isDone()`, though this is a point-in-time state read that can change immediately afterward.
2. **Did the task complete successfully?** `isDone()==true` is not enough: you need to distinguish success, failure, and cancellation.
3. **Is the successful result `null`?** This is a **valid value under the CompletableFuture contract**, unless your own program defines that results are always non-null.

Do not collapse these three questions into a single `getNow(null) == null` comparison.

## 2. The getNow API Contract in Java 17

Signature:

~~~java
public T getNow(T valueIfAbsent)
~~~

Semantics:

- **Not yet completed:** returns `valueIfAbsent` immediately without waiting for the actual result.
- **Completed normally with non-null T:** returns that exact value, ignoring `valueIfAbsent`.
- **Completed normally with null:** returns `null`, even if `valueIfAbsent` is non-null.
- **Completed exceptionally:** throws a `CompletionException` wrapping the underlying cause (cancellation cases have their own exception).
- **Cancelled:** typically throws `CancellationException` directly for a cancelled `CompletableFuture`; the caller must handle it separately.
- **Does not set a deadline:** if not yet completed, the method returns the fallback immediately, without waiting for a timeout or forcing the worker to make progress.
- **Does not start computation on behalf of the caller:** It reads the existing completion state; it is not `start()`/`submit()`/`complete()`.
- **Does not self-cancel:** Returning the fallback because it is not yet completed does not alter the Future's state.

`valueIfAbsent` is the **value used when there is no completion yet**, not an `orElse` for a business-null, nor an `exceptionally` for error recovery.

### State Table to Remember

| Future State at Time of Observation | `isDone()` | `isCancelled()` | `getNow("WAIT")` |
| --- | --- | --- | --- |
| Pending, not yet completed | `false` | `false` | `"WAIT"` |
| Completed normally, value `"OK"` | `true` | `false` | `"OK"` |
| Completed normally, value `null` | `true` | `false` | `null` |
| Completed exceptionally (e.g., IllegalStateException) | `true` | `false` | Throws `CompletionException` |
| Cancelled | `true` | `true` | Throws `CancellationException` |

This table describes **independent scenarios**. When one thread reads `isDone` and then calls `getNow`, another thread may complete the Future between the two operations. The two reads **do not form a single atomic snapshot**.

## 3. Comparing get(), join(), and getNow()

| Method | When not completed | Success | Computation error | Cancellation |
| --- | --- | --- | --- | --- |
| `get()` | **Waits**; can be interrupted | Returns T, including null | `ExecutionException` | `CancellationException` |
| `get(timeout, unit)` | Waits up to timeout | Returns T, including null | `ExecutionException` | `CancellationException` |
| `join()` | **Waits**; used in completion-style pipelines | Returns T, including null | `CompletionException` | `CancellationException` |
| `getNow(valueIfAbsent)` | **Returns fallback immediately** | Returns T, including null | `CompletionException` | `CancellationException` |

`get(timeout, unit)` is a timed wait, not a non-blocking poll. Even with a very small timeout, the caller still participates in the wait/timeout mechanism and must handle checked exceptions. `getNow` does not wait for the result.

Both `join()` and `getNow` are convenient in pipelines when the caller does not want to declare `InterruptedException`/`ExecutionException` as with `get()`, but that does **not** make errors disappear: they surface as unchecked completion/cancellation exceptions.

### Do Not Interpret isDone() as Success

`isDone()==true` includes:
- Normal completion with any value, including `null`.
- Exceptional completion.
- Cancellation.

`isCompletedExceptionally()` is true for exceptional completion and may be true when cancelled; use `isCancelled()` when you need to distinguish cancellation. To retrieve the actual result and classify the final error, use `getNow`/`join` with the corresponding catch blocks.

## 4. Example 1 — Pending and Completed-Null Both Return null When Fallback Is null

Create `GetNowNullAmbiguity.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;

public class GetNowNullAmbiguity {
    public static void main(String[] args) {
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletableFuture<String> doneNull =
                CompletableFuture.completedFuture(null);

        System.out.println("pending getNow(null) = "
                + pending.getNow(null));
        System.out.println("done-null getNow(null) = "
                + doneNull.getNow(null));

        System.out.println("pending isDone = " + pending.isDone());
        System.out.println("done-null isDone = " + doneNull.isDone());

        System.out.println("pending getNow(WAIT) = "
                + pending.getNow("WAIT"));
        System.out.println("done-null getNow(WAIT) = "
                + doneNull.getNow("WAIT"));

        pending.complete("READY");
        System.out.println("pending after complete = "
                + pending.getNow("WAIT"));
    }
}
~~~

Compile/run:

~~~bash
javac GetNowNullAmbiguity.java
java GetNowNullAmbiguity
~~~

Exact stdout:

~~~text
pending getNow(null) = null
done-null getNow(null) = null
pending isDone = false
done-null isDone = true
pending getNow(WAIT) = WAIT
done-null getNow(WAIT) = null
pending after complete = READY
~~~

With `getNow(null)`, the first two lines are **identical**, even though one Future is incomplete and the other completed normally with null. Using `"WAIT"` as the fallback helps distinguish them in this example, because the business result is assumed to **never actually be the string "WAIT"**. If the business logic can legitimately return `"WAIT"`, this approach **remains ambiguous**.

Note that `pending.complete("READY")` is an operation that completes the Future; it does not require a separate worker. The example is coordinated sequentially so that the output does not depend on scheduling.

## 5. Non-Null Fallback Values: Sentinels and Collision Risks

One solution is to use a **sentinel**, meaning a value used exclusively to indicate "not yet completed".

~~~java
// Snippet; only valid when the business contract forbids returning "PENDING".
String value = future.getNow("PENDING");
if ("PENDING".equals(value)) {
    // May be pending, but could also be the actual result "PENDING".
}
~~~

**Do not use a common value as a sentinel** when the domain itself can return that value. For example, `0` is a valid count result, `false` is a valid boolean result, and the string `"N/A"` can be a real result.

### Identity-Based Sentinel

If a Future has type `Object` and the input/domain **cannot return the exact sentinel object** you created, you can use reference identity comparison:

~~~java
// Java snippet: CompletableFuture<Object> future must be created by the caller.
Object sentinel = new Object();
Object current = future.getNow(sentinel);
if (current == sentinel) {
    // Not yet completed at the time of the getNow observation.
} else {
    // Completed normally; current may be null.
}
~~~

Here we do not use `sentinel.equals(current)` because identity is the distinguishing property. However, you must ensure the sentinel **never enters the set of valid results**. If a Future actually completes with that exact sentinel reference, the distinction will fail.

With `CompletableFuture<String>`, you cannot pass `new Object()` directly into `getNow(String)` due to type mismatch. Do not use raw casts to bypass type safety; choose **a result type that represents state explicitly** if the domain of `T` has no guaranteed unique sentinel.

## 6. Example 2 — Object Sentinel Distinguishing Pending, null, and a Real Value

Create `GetNowIdentitySentinel.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;

public class GetNowIdentitySentinel {
    public static void main(String[] args) {
        Object notReady = new Object();
        CompletableFuture<Object> future = new CompletableFuture<>();

        Object before = future.getNow(notReady);
        System.out.println("pending = " + (before == notReady));

        future.complete(null);
        Object after = future.getNow(notReady);

        System.out.println("done = " + future.isDone());
        System.out.println("completed with null = " + (after == null));
        System.out.println("not sentinel = " + (after != notReady));

        CompletableFuture<Object> other =
                CompletableFuture.completedFuture("READY");
        System.out.println("value = " + other.getNow(notReady));
    }
}
~~~

Run:

~~~bash
javac GetNowIdentitySentinel.java
java GetNowIdentitySentinel
~~~

Stdout:

~~~text
pending = true
done = true
completed with null = true
not sentinel = true
value = READY
~~~

`notReady` is a fresh object that is never supplied as the result value of any Future in the example. `getNow(notReady)` before completion returns the sentinel itself; after `complete(null)` it returns the **actual null**, not the sentinel. Thus, reference identity comparison cleanly resolves both cases here.

**Technical limitation:** You cannot guarantee an identity sentinel is safe if code outside your module could complete the Future with that same reference. For public APIs or complex data models, representing completion **with a dedicated data type** is clearer.

## 7. Representing Results with a Non-Null Type Instead of Overloading null

A cleaner design: the Future **always returns a non-null envelope/holder** for a successful result. For example:

- `CompletableFuture<Optional<T>>`: `Optional.empty()` means **completed with no business value**; the `Optional` itself is always non-null per the application's contract.
- `CompletableFuture<Result<T>>` with a record/sealed hierarchy describing success-with-value and success-without-value; failure still uses exceptional completion or is encoded as required.
- `CompletableFuture<Outcome>` where `Outcome` is an immutable record containing result information and metadata.

With `CompletableFuture<Optional<String>>`, if the program **guarantees it never completes the Future with null**, we can use `getNow(null)` as the pending indicator; once completed normally, the value will be `Optional.empty()` or `Optional.of(...)`.

~~~text
CompletableFuture<Optional<String>>

Pending:                 getNow(null) -> null
Completed with no value: getNow(null) -> Optional.empty()
Completed with value:    getNow(null) -> Optional.of("A")
Completed exceptionally: getNow(null) -> throws CompletionException
Cancelled:               getNow(null) -> throws CancellationException
~~~

This distinction works through the **data type contract**, not because `getNow(null)` inherently knows why null appeared. If any code still calls `future.complete(null)`, the ambiguity returns; this invariant must be enforced consistently across the entire producer pipeline.

### Example 3 — CompletableFuture<Optional<T>> to Avoid Confusing "No Value" with "Pending"

Create `OptionalResultStage.java` (Java 17+):

~~~java
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

public class OptionalResultStage {
    public static void main(String[] args) {
        CompletableFuture<Optional<String>> future =
                new CompletableFuture<>();

        Optional<String> before = future.getNow(null);
        System.out.println("pending = " + (before == null));

        future.complete(Optional.empty());
        Optional<String> after = future.getNow(null);
        System.out.println("done = " + future.isDone());
        System.out.println("completed with no value = " + after.isEmpty());

        CompletableFuture<Optional<String>> withValue =
                CompletableFuture.completedFuture(Optional.of("Ada"));
        System.out.println("name = "
                + withValue.getNow(null).orElse("UNKNOWN"));
    }
}
~~~

Compile/run:

~~~bash
javac OptionalResultStage.java
java OptionalResultStage
~~~

Stdout:

~~~text
pending = true
done = true
completed with no value = true
name = Ada
~~~

Calling `after.isEmpty()` is safe **because the application completed the Future with `Optional.empty()` and guarantees that successful results are non-null**. In library code that accepts an untrusted `CompletableFuture<Optional<String>>`, you should check for null and validate the contract before calling methods on it.

**Do not confuse `Optional.empty()` with an error:** "Data not found" is success-without-value when defined that way by the domain; "broken DB connection" is typically an exceptional completion—do not automatically convert every error into `Optional.empty()` and silently hide failures.

## 8. Example 4 — getNow Does Not Change the Future's State

Reading the fallback multiple times does not cause the work to complete on its own. Subsequent reads may still be pending if the producer has not called `complete`.

Create `GetNowNoSideEffect.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;

public class GetNowNoSideEffect {
    public static void main(String[] args) {
        CompletableFuture<Integer> future = new CompletableFuture<>();

        System.out.println("first read = " + future.getNow(-1));
        System.out.println("second read = " + future.getNow(-1));
        System.out.println("done after reads = " + future.isDone());

        System.out.println("complete accepted = " + future.complete(42));
        System.out.println("third read = " + future.getNow(-1));
        System.out.println("done after complete = " + future.isDone());
    }
}
~~~

Run:

~~~bash
javac GetNowNoSideEffect.java
java GetNowNoSideEffect
~~~

Stdout:

~~~text
first read = -1
second read = -1
done after reads = false
complete accepted = true
third read = 42
done after complete = true
~~~

`getNow(-1)` is not `complete(-1)`. It only provides a value for **the caller to use at the time of the read**, while the Future remains incomplete. After `complete(42)`, reading returns 42.

Another risk: the fallback may collide with a real value. If a valid computation returns `-1`, comparing `getNow(-1) == -1` is again insufficient to distinguish pending from done.

## 9. Exceptional Completion Does Not Use valueIfAbsent as a Fallback

Crucial note: `getNow(valueIfAbsent)` uses the fallback **when not yet completed**, not when the Future fails.

A computation can complete exceptionally via:

- `completeExceptionally(cause)`.
- A mapper/`Callable`/`Supplier` throwing an exception, causing the dependent `CompletableFuture` to terminate exceptionally.
- `orTimeout(timeout, unit)` setting exceptional completion with `TimeoutException` if not yet completed.
- Exceptional completion from a source stage propagating through unhandled dependent stages.
- Cancellation, which is a special case of abnormal completion.

For an error such as `IllegalArgumentException`, `getNow` typically throws `CompletionException` wrapping the cause. The caller must use `getCause()` to classify the root cause. Do not catch `Exception` and return a default sentinel for all errors unless the business logic permits it.

### Example 5 — Success, Failure, and Cancellation

Create `GetNowFailures.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class GetNowFailures {
    public static void main(String[] args) {
        CompletableFuture<String> success =
                CompletableFuture.completedFuture("OK");

        CompletableFuture<String> failed = new CompletableFuture<>();
        failed.completeExceptionally(
                new IllegalStateException("storage unavailable"));

        CompletableFuture<String> cancelled = new CompletableFuture<>();
        cancelled.cancel(false);

        System.out.println("success = " + success.getNow("WAIT"));

        try {
            failed.getNow("WAIT");
        } catch (CompletionException e) {
            System.out.println("failure cause = "
                    + e.getCause().getClass().getSimpleName());
        }

        try {
            cancelled.getNow("WAIT");
        } catch (CancellationException e) {
            System.out.println("cancelled exception = true");
        }

        System.out.println("failure done = " + failed.isDone());
        System.out.println("failure cancelled = "
                + failed.isCancelled());
        System.out.println("cancel done = " + cancelled.isDone());
        System.out.println("cancel cancelled = "
                + cancelled.isCancelled());
    }
}
~~~

Run:

~~~bash
javac GetNowFailures.java
java GetNowFailures
~~~

Stdout:

~~~text
success = OK
failure cause = IllegalStateException
cancelled exception = true
failure done = true
failure cancelled = false
cancel done = true
cancel cancelled = true
~~~

There is no `WAIT` line for failure/cancel because the Future **has already completed** via an abnormal path; the default is only used when there is no completion yet. `isDone()==true` does not mean success. For a cancelled `CompletableFuture`, `getNow` throws `CancellationException`; normal computation errors typically surface through `CompletionException`.

**Do not confuse cancellation with a stopped task body:** `CompletableFuture.cancel(true)` does not actually interrupt the computation under the `CompletableFuture` implementation, and a cancelled Future may still have a worker performing side effects or cleanup. Cancellation applies to the result state, whereas stopping a task requires its own protocol.

## 10. getNow and isDone: Check-Then-Act Is Not an Atomic Snapshot

A common pattern:

~~~java
// Snippet: can be used to report approximate state,
// but this is NOT an atomic read of the two events.
if (!future.isDone()) {
    return "PENDING";
}
return future.getNow(null);
~~~

This pattern is acceptable for displaying status at a point in time, **if stale status is tolerable**. The Future may complete right after `isDone()==false`, causing the caller to return `PENDING` even though the result became ready a split second later.

In the opposite direction, once `isDone()==true`, a standard `CompletableFuture` will not revert to pending; `getNow` will not have to wait. However, it can still throw `CompletionException`/`CancellationException`, and the actual result can still be `null`.

**Do not try to "fix" the race simply by checking twice:**

~~~java
// Snippet does not solve a general transactional snapshot.
boolean done1 = future.isDone();
T observed = future.getNow(fallback);
boolean done2 = future.isDone();
~~~

The three reads occur at three different points in time. If the application needs a single observation with clearly classified state, use a **result envelope** and a handling protocol, or an explicit snapshot of completion status at the caller. With `getNow` alone, a unique sentinel of the right type can distinguish pending vs. normal completion within the scope of **that single read**, while exception handling distinguishes failure/cancellation.

### Example 6 — State Can Change Between isDone and getNow

Create `IsDoneRaceDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class IsDoneRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> future = new CompletableFuture<>();
        CountDownLatch checked = new CountDownLatch(1);
        CountDownLatch continueReader = new CountDownLatch(1);
        AtomicBoolean doneAtCheck = new AtomicBoolean();
        AtomicReference<String> readLater = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            doneAtCheck.set(future.isDone());
            checked.countDown();
            try {
                continueReader.await();
                readLater.set(future.getNow("WAIT"));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        reader.start();
        checked.await();
        future.complete("READY");
        continueReader.countDown();
        reader.join();

        System.out.println("isDone at check = " + doneAtCheck.get());
        System.out.println("getNow later = " + readLater.get());
        System.out.println("isDone now = " + future.isDone());
    }
}
~~~

Run:

~~~bash
javac IsDoneRaceDemo.java
java IsDoneRaceDemo
~~~

Stdout:

~~~text
isDone at check = false
getNow later = READY
isDone now = true
~~~

The latches force the reader to observe `isDone()==false` **before** `main` completes the Future, and only then does the reader call `getNow`. This creates a deterministic interleaving that does not rely on scheduler luck or `Thread.sleep(100)`. Lesson: the state observed at t1 is **not** an immutable state at t2.

Applications often do not need microsecond-level precision for progress; a dashboard can show a stale `PENDING` and update on the next event. However, financial or transactional workflows cannot make irreversible decisions based solely on stale status.

## 11. getNow() Does Not Block Even When a Task Is Long-Running

To demonstrate this, we need to ensure the task is active but **cannot finish** before the read. Use a `CountDownLatch` rather than fragile timing measurements.

### Example 7 — Reading Immediately While the Callback Is Still Waiting

Create `GetNowWhileRunning.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class GetNowWhileRunning {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            return "INTERRUPTED";
                        }
                        return "READY";
                    }, pool);

            started.await();
            System.out.println("getNow while running = "
                    + future.getNow("WAIT"));
            System.out.println("isDone while waiting = "
                    + future.isDone());

            release.countDown();
            System.out.println("join after release = " + future.join());
            System.out.println("getNow after finish = "
                    + future.getNow("WAIT"));
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac GetNowWhileRunning.java
java GetNowWhileRunning
~~~

Stdout on a normal run:

~~~text
getNow while running = WAIT
isDone while waiting = false
join after release = READY
getNow after finish = READY
~~~

The worker decrements `started` and then **waits on release**; `main` does not open `release` until after calling `getNow` and `isDone`. Thus the result is guaranteed to still be pending for both reads. After `main` calls `release.countDown()`, `join()` waits for the worker to return `READY`, and `getNow` reads the actual result.

The key point: `getNow` **does not block waiting for the latch**, whereas `join` can block until the computation finishes. Do not write an unbounded `while(future.getNow("WAIT").equals("WAIT")) { }` loop and assume your program has become a non-blocking system: each individual read is non-blocking, but the loop can **spin the CPU** indefinitely.

## 12. Why Is getNow(null) Especially Error-Prone with CompletableFuture<Void>?

`CompletableFuture<Void>` commonly arises from:

- `CompletableFuture.runAsync(Runnable)`.
- `thenAccept(...)` / `thenAcceptAsync(...)`.
- `thenRun(...)` / `thenRunAsync(...)`.
- `CompletableFuture.allOf(...)` when waiting for multiple Futures.
- A task whose success **has no return value**.

`Void` has no normal non-null instance for the caller to pass as a fallback. For successful stages of type `Void`, the standard result is `null`; and when the stage is not yet completed, `getNow(null)` also returns `null`.

~~~java
// Snippet: both can print null.
CompletableFuture<Void> pending = new CompletableFuture<>();
CompletableFuture<Void> done =
        CompletableFuture.completedFuture(null);

System.out.println(pending.getNow(null));
System.out.println(done.getNow(null));
~~~

You should not force-create a `Void` object or use raw casts just to have a sentinel. That goes against the type system.

### Alternative Ways to Observe

1. Use `isDone()` to report **approximate state**; if true, classify success/failure/cancel via `getNow(null)` inside a try/catch. When point-in-time accuracy matters, keep the race between reads in mind.
2. Create a dependent stage carrying **a non-null marker** after the source completes normally: `future.thenApply(ignored -> Boolean.TRUE)`. Then `marker.getNow(Boolean.FALSE)` distinguishes pending from normal success under the contract that this stage **only returns true on success**.
3. Use `whenComplete`/`handle` to update an application state machine; preserve error details rather than hiding them.
4. If your API controls the producer, consider `CompletableFuture<Optional<Result>>` or a result wrapped in a record instead of `Void` when status information needs to be represented.

### Example 8 — Turning Void Completion into a Boolean Marker

Create `VoidCompletionMarker.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;

public class VoidCompletionMarker {
    public static void main(String[] args) {
        CompletableFuture<Void> action = new CompletableFuture<>();

        CompletableFuture<Boolean> marker =
                action.thenApply(ignored -> Boolean.TRUE);

        System.out.println("action getNow(null) = "
                + action.getNow(null));
        System.out.println("marker before = "
                + marker.getNow(Boolean.FALSE));

        action.complete(null);

        System.out.println("action getNow(null) after = "
                + action.getNow(null));
        System.out.println("marker after = "
                + marker.getNow(Boolean.FALSE));
    }
}
~~~

Run:

~~~bash
javac VoidCompletionMarker.java
java VoidCompletionMarker
~~~

Stdout:

~~~text
action getNow(null) = null
marker before = false
action getNow(null) after = null
marker after = true
~~~

Because the non-async `thenApply` is attached before `action` completes and the callback simply returns `TRUE`, after `action.complete(null)` the dependent marker completes normally in this example, so `getNow(FALSE)` returns `true`. Before that, the marker is not yet completed and returns `false`. **If the source fails**, the mapper callback does not run and the marker can complete exceptionally; in that case `getNow(FALSE)` does not return `false`—it throws a completion exception.

In production, if you use `thenApplyAsync` to create the marker, it may still be pending **after** the source has completed because the marker is still waiting on the executor. Do not assume the source and marker complete simultaneously at all times.

## 13. A Helper to Classify State Using getNow and Exceptions

When you need to display the state of a `CompletableFuture` that may return `null`, you can separate the outcome into an **explicit state representation**. The helper below performs a single `getNow` call with a privately managed `Object` sentinel to distinguish pending vs. normal results, while catching failures and cancellations.

### Example 9 — Rendering Pending / Ready(null) / Ready(value) / Failed / Cancelled

Create `GetNowStatusView.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class GetNowStatusView {
    private static final Object PENDING = new Object();

    static String status(CompletableFuture<Object> future) {
        try {
            Object value = future.getNow(PENDING);
            if (value == PENDING) {
                return "PENDING";
            }
            if (value == null) {
                return "READY(null)";
            }
            return "READY(" + value + ")";
        } catch (CancellationException e) {
            return "CANCELLED";
        } catch (CompletionException e) {
            return "FAILED("
                    + e.getCause().getClass().getSimpleName() + ")";
        }
    }

    public static void main(String[] args) {
        CompletableFuture<Object> pending = new CompletableFuture<>();
        CompletableFuture<Object> doneNull =
                CompletableFuture.completedFuture(null);
        CompletableFuture<Object> doneValue =
                CompletableFuture.completedFuture(42);

        CompletableFuture<Object> failed = new CompletableFuture<>();
        failed.completeExceptionally(new IllegalArgumentException("bad"));

        CompletableFuture<Object> cancelled = new CompletableFuture<>();
        cancelled.cancel(false);

        System.out.println("pending = " + status(pending));
        System.out.println("null = " + status(doneNull));
        System.out.println("value = " + status(doneValue));
        System.out.println("failure = " + status(failed));
        System.out.println("cancel = " + status(cancelled));
    }
}
~~~

Run:

~~~bash
javac GetNowStatusView.java
java GetNowStatusView
~~~

Stdout:

~~~text
pending = PENDING
null = READY(null)
value = READY(42)
failure = FAILED(IllegalArgumentException)
cancel = CANCELLED
~~~

The design precondition of this helper is that **producers never complete the Future with the static `PENDING` reference itself**. Because this is a private constant used only internally to read status, the example satisfies that condition. If a public API allows callers to obtain the reference and complete the Future with the sentinel, you must drop this assumption or switch to a result envelope with stricter invariants.

A helper should also define a policy for `CompletionException` with unusual or null causes; the example focuses on a specific `IllegalArgumentException` failure. Do not swallow exceptions and return `READY(null)`, as that can falsely report success.

## 14. The Fallback Value May Be Evaluated Eagerly Even When Unused

In Java, arguments are evaluated **before** the method is invoked. Therefore:

~~~java
// Warning snippet:
String value = future.getNow(expensiveFallback());
~~~

`expensiveFallback()` is called **even when the Future has already completed normally** and the actual result does not need the fallback. `getNow` is not a lazy `Supplier<T>` API.

If the fallback performs I/O, large allocations, or side effects, the code can become slow or block due to **argument evaluation**, even though `getNow` itself does not wait on the Future.

### Example 10 — Fallback Is Evaluated Eagerly

Create `EagerDefaultArgument.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class EagerDefaultArgument {
    static String fallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return "WAIT";
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        CompletableFuture<String> done =
                CompletableFuture.completedFuture("READY");

        String observed = done.getNow(fallback(calls));
        System.out.println("observed = " + observed);
        System.out.println("fallback evaluated = " + calls.get());
    }
}
~~~

Run:

~~~bash
javac EagerDefaultArgument.java
java EagerDefaultArgument
~~~

Stdout:

~~~text
observed = READY
fallback evaluated = 1
~~~

The actual result `READY` is still returned; the `fallback(calls)` method was invoked because Java must evaluate arguments before entering `getNow`. Prefer a sentinel constant or an already-available value, and avoid placing expensive work in the argument with the expectation that it will only run when pending.

## 15. getNow() Is Not a Replacement for Asynchronous Callbacks

If your goal is "when the Future finishes, run this logic immediately," you usually **do not need to poll**:

~~~java
// API snippet, placed inside a method with appropriate variables.
future.thenAccept(value -> updateUiModel(value));
future.whenComplete((value, error) -> logCompletion(value, error));
~~~

This is how you declare a dependent stage/callback that reacts to completion. Choose an appropriate executor if the callback is heavy or blocking (`thenAcceptAsync(..., executor)`, `whenCompleteAsync(..., executor)`).

`getNow` is appropriate when the caller wants an **immediate snapshot**, such as rendering the current state without blocking. It has no wait-with-signal capability, provides no notifications, and does not reschedule the caller when the result changes.

### Avoid Unbounded Busy-Spinning

Dangerous pattern:

~~~java
// INCORRECT CODE for both resources and sentinel collision.
while (future.getNow("WAIT").equals("WAIT")) {
    // spins continuously; may burn CPU or never terminate
}
~~~

Risks:

- If the real result also equals `"WAIT"`, the loop can run forever even after normal completion.
- If the Future fails/cancels, an exception can escape unexpectedly.
- If not yet completed, the loop continuously consumes CPU, competing with the very worker that needs CPU time.
- If the worker gets stuck, there is no timeout or cleanup.
- `getNow` is non-blocking per read, yet **the overall loop may still never terminate**.

If you need to wait, choose `get(timeout)`, `join` where appropriate, callback composition, or a synchronizer with a timeout. If event-loop polling is required, use proper scheduling/backoff, a non-colliding non-null state, and cancellation/lifecycle handling.

## 16. getNow in a Pipeline with Multiple Dependent Stages

A pipeline such as:

~~~text
supplyAsync(fetch, ioExecutor)
     |
     v
thenApplyAsync(parse, cpuExecutor)
     |
     v
thenApply(validate)
     |
     v
thenComposeAsync(enrich, ioExecutor)
     |
     v
final Future
~~~

has **one Future per stage**. When the source completes, the dependent `parse` stage may **not yet** be completed because it is still waiting on the executor. Therefore:

- `source.getNow(fallback)` may return the fetched data.
- `parseFuture.getNow(fallback)` may still return the fallback.
- `validateFuture.getNow(fallback)` may also be pending.
- The final Future may still be pending or exceptional even though an earlier stage succeeded.

Do not rely on `source.isDone()==true` to conclude that the **entire pipeline** is finished. Keep a handle to the **final stage** if the caller cares about the final result. In a fan-out model, keep handles to the individual branches or combine them with `allOf`/`thenCombine` depending on dependencies.

### Observing an Exceptional Source

If the source fails, the `thenApply`/`thenApplyAsync` mapper is not called. Dependent stages are completed exceptionally according to propagation rules. `getNow` on a dependent stage will throw the exception once propagation has completed; it may remain pending for a brief moment depending on triggering/scheduling. Do not treat every fallback result as "no data yet" and overlook the possibility of failure.

If error recovery is needed, use `exceptionally`, `handle`, or `exceptionallyAsync` per contract, and then observe the **recovery stage**, not just the failed stage.

## 17. thenApplyAsync, Timeouts, and Staying Non-Blocking at the Application Layer

`CompletableFuture.getNow` does not wait on the stage, but surrounding logic can accidentally block:

- A fallback expression performing I/O before calling `getNow`.
- Logging/rendering callbacks performing synchronous network I/O.
- Triggering an immediate retry when pending.
- Calling `getNow` repeatedly in a polling loop without backoff.
- Acquiring an application lock before reading or holding a lock across another Future's `join()`.

Therefore, calling the `getNow` API non-blocking describes **the contract of this result-reading method**, not a guarantee that the entire call path always has low latency.

### Timeout vs. Cancellation

- `future.get(50, MILLISECONDS)` times out: **the caller has waited long enough**; the Future itself is not cancelled.
- `future.orTimeout(50, MILLISECONDS)`: for `CompletableFuture`, if not completed by the deadline, **the Future is completed exceptionally** with `TimeoutException`. It changes the Future's state, without interrupting the underlying computation.
- `future.completeOnTimeout(value, 50, MILLISECONDS)`: if not yet completed, the Future is completed normally with the fallback value after the deadline; the worker may still continue running and producing side effects.
- `future.cancel(true)`: the Future is cancelled per `CompletableFuture` semantics; the `mayInterruptIfRunning` parameter is not used to control execution in this implementation.

Once `orTimeout` has completed the Future exceptionally, `getNow(default)` will **throw an exception** rather than returning the default. After `completeOnTimeout`, `getNow(default)` reads the value completed by the timeout policy, not a "pending fallback" chosen by `getNow` itself.

### Example 11 — completeOnTimeout and getNow

Create `GetNowAfterCompleteOnTimeout.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class GetNowAfterCompleteOnTimeout {
    public static void main(String[] args) {
        CompletableFuture<String> future = new CompletableFuture<>();
        future.completeOnTimeout("TIMEOUT_VALUE",
                0, TimeUnit.MILLISECONDS);

        System.out.println("result = " + future.join());
        System.out.println("getNow = " + future.getNow("PENDING"));
        System.out.println("done = " + future.isDone());
    }
}
~~~

Run:

~~~bash
javac GetNowAfterCompleteOnTimeout.java
java GetNowAfterCompleteOnTimeout
~~~

Stdout after the timeout action completes:

~~~text
result = TIMEOUT_VALUE
getNow = TIMEOUT_VALUE
done = true
~~~

A timeout of 0 makes the Future eligible to complete with `TIMEOUT_VALUE` as soon as the scheduler processes it; `join` waits for that completion, and then `getNow` returns **the completed value**. This does not rely on specific scheduler timing because printing happens only after `join`.

**Do not misunderstand:** `completeOnTimeout` returns the `CompletableFuture` itself per contract and can mutate that Future's state; this differs from passing `"PENDING"` to `getNow`, which never completes the Future.

## 18. When Do You Need a Clearer State Snapshot Than a Single Value?

In some applications, an upper-level API needs to display one of these states:

~~~text
PENDING
READY(value)
READY(null/no-value)
FAILED(cause)
CANCELLED
~~~

This is a **business state model**, broader than a single `getNow(null)` read. It can be modeled using a sealed interface and immutable records, for example:

~~~java
// Data model snippet, not a complete program.
sealed interface View<T>
        permits Pending, Ready, Failed, Cancelled {}
record Pending<T>() implements View<T> {}
record Ready<T>(T value) implements View<T> {}
record Failed<T>(Throwable cause) implements View<T> {}
record Cancelled<T>() implements View<T> {}
~~~

These records make it explicit that `Ready(null)` differs from `Pending`. If a library needs to carefully distinguish error/timeout/cancellation details, a helper like `GetNowStatusView` can construct a concrete record rather than a `String` so callers do not have to parse strings.

**Note:** Creating a `Pending` state object in the UI after a read does not prevent the Future from completing immediately afterward. A snapshot is a **picture at the time of observation**, not a lock holding the state still. If an irreversible business decision must be made, add synchronization, a protocol, or idempotency at the appropriate layer.

## 19. Java Memory Model: When a Future Completes, Is Reading the Result Safe?

`CompletableFuture` is a thread-safe synchronization construct that manages completion; a value published via result completion can be safely read from another thread through `Future`/`CompletionStage` mechanisms. In a typical producer–consumer pattern, one thread computes the result and calls `complete(value)`, and another thread reads the result after the Future completes.

However, you must distinguish **publication of the result** from **any subsequent mutation**:

~~~java
// Snippet illustrating the ownership issue.
List<String> mutable = new ArrayList<>();
mutable.add("A");
future.complete(mutable);

// If the producer continues mutable.add("B") while the consumer
// iterates the list via getNow(), a data race can occur.
~~~

An `ArrayList` does not automatically become thread-safe simply because its reference was passed through a `CompletableFuture`. To avoid races, return an immutable list (e.g., `List.copyOf(mutable)`), transfer ownership and stop modifying it, or use proper synchronization.

Similarly, a Future that completed normally with `null` has no "memory visibility bug": that is the **intended result value by design**, not a read that failed to see completion.

### Do Not Improvise with Plain Variables

If you consider using a separate flag:

~~~java
// Dangerous snippet without proper synchronization.
boolean ready;
Object result;
~~~

Two threads updating and reading these without locking can cause a data race. Do not replace `CompletableFuture` with two non-volatile/unsynchronized variables just to avoid `getNow`. If you build a custom result-state machine, ensure proper thread-safety and atomic publication.

## 20. Error Handling: Do Not Hide Errors with a Default

An anti-pattern is collapsing all errors into `null`:

~~~java
// INCORRECT CODE for business semantics.
try {
    return future.getNow(null);
} catch (Exception ignored) {
    return null;
}
~~~

The caller then cannot tell:
- Is the Future pending?
- Is the Future done-null?
- Did storage fail?
- Was it cancelled?
- Did it time out?
- Was a callback rejected?

These states have very different consequences. A UI screen might reasonably show loading when pending; however, a storage error needs logging, metrics, a retry policy, or a clear error message. Cancellation might mean the user left the page and no retry is needed. A timeout may require a deadline/backoff to avoid a retry storm.

### Catching Exceptions Intentionally

~~~java
// Snippet, assuming future has type CompletableFuture<String>.
try {
    String result = future.getNow("PENDING");
    // Watch out for sentinel collision and actual null values.
} catch (CancellationException cancelled) {
    // Report cancellation state per protocol.
} catch (CompletionException failed) {
    Throwable cause = failed.getCause();
    // Classify computation, timeout, or I/O errors.
}
~~~

Do not indiscriminately catch `Throwable` and treat everything as "no value". Serious `Error`s may require escalation and should not be silently swallowed.

## 21. Rules for Choosing How to Read Results

| Need | Appropriate Approach |
| --- | --- |
| Get value if already available, without waiting | `getNow(valueIfAbsent)` + sentinel/invariant + exception handling |
| Clearly distinguish pending from successful-null | Result envelope, non-null `Optional<T>` contract, or non-colliding sentinel |
| Only need a "finished" flag at read time | `isDone()`, without treating it as success |
| Distinguish failure from cancellation | `getNow`/`join` with `CompletionException`, `CancellationException` |
| Wait until completion | `join()`/`get()`, understanding blocking behavior |
| Wait with a time limit | `get(timeout, unit)`, handling timeout |
| React when the result appears | `thenApply`/`thenAccept`/`whenComplete` and their Async variants |
| Automatically complete Future on timeout | `orTimeout`/`completeOnTimeout`, understanding semantics and side effects |
| Query the result of the final pipeline | Keep a handle to the **final stage** |
| Actually stop a running task | Cooperative cancellation/deadline, not just `getNow` or `cancel` |

## 22. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`getNow(null)==null` means pending." | It may have completed normally with `null` |
| "`getNow` returns the fallback on completed-null." | No. It returns the actual `null`; the fallback is only used if not yet completed |
| "`valueIfAbsent` is also used when the Future fails." | No. Exceptional/cancelled completion throws its own exception |
| "`isDone` true means success." | Success, failure, and cancellation are all done |
| "`getNow` always returns a non-null `T`." | It can return `null` or throw an exception |
| "`getNow` starts the computation." | No, it only reads the result state |
| "Calling `getNow` multiple times will make the Future complete." | No |
| "`getNow` has an implicit timeout." | No timeout is needed because it does not wait for the result |
| "`get(timeout)` is the same as `getNow`." | `get(timeout)` is a timed blocking wait |
| "`join()` does not block." | It can wait indefinitely if the Future never completes |
| "Using the string `PENDING` as a default is always safe." | The actual result might collide with that string |
| "Use an `Object` sentinel as fallback for `CF<String>`." | Type mismatch; do not bypass generics with raw casts |
| "`Optional.empty` means pending." | If `Future<Optional<T>>` completed normally with `Optional.empty`, it is ready-without-value |
| "`Future<Void>.getNow(null)==null` means finished." | Pending also returns `null` |
| "`isDone` and `getNow` read the same snapshot." | Completion can occur between the two calls |
| "Cancelling a Future means the worker has definitely stopped." | `CompletableFuture.cancel` does not forcibly interrupt the computation |
| "When completed exceptionally, `getNow` returns the default." | It typically throws `CompletionException` |
| "Ignoring all exceptions and returning `null` is recovery." | It hides failure/cancel/timeout and causes logic bugs |
| "If `getNow` is non-blocking, all surrounding code is non-blocking." | Argument evaluation, locks, and callbacks can still block |
| "Once a result is received via a Future, mutable objects inside are thread-safe." | Publication is different from concurrent mutation |
| "`getNow` on a done source means the final pipeline is done." | Each dependent stage has its own completion |
| "Polling `getNow` in a tight loop uses no resources." | Busy-spinning can saturate the CPU |
| "`completeOnTimeout` is only a temporary fallback." | It actually completes the Future if not yet done at timeout |

## 23. Self-Check Questions

**Q1.** A `CompletableFuture<String>` is pending. What does `getNow(null)` return?  
**Answer:** `null` immediately, without blocking.

**Q2.** A Future has called `complete(null)`. What does `getNow("WAIT")` return?  
**Answer:** The actual `null`, not `"WAIT"`.

**Q3.** Is using `getNow("WAIT")=="WAIT"` as definitive proof of pending always valid?  
**Answer:** No, if the actual result can legitimately equal `"WAIT"`.

**Q4.** Why can't you pass `new Object()` into `CompletableFuture<String>.getNow(...)`?  
**Answer:** The parameter must be of type `String` per the generic type; `Object` is not accepted.

**Q5.** A `CompletableFuture` completed exceptionally with `IllegalStateException`. Does `getNow("WAIT")` return the fallback?  
**Answer:** No. It throws `CompletionException` with the corresponding cause.

**Q6.** A `CompletableFuture` called `cancel(false)`. What does `getNow("WAIT")` typically do?  
**Answer:** Throws `CancellationException`, rather than returning the fallback.

**Q7.** Is `isDone()==true` enough to confirm the Future completed successfully?  
**Answer:** No. Failure and cancellation also count as done.

**Q8.** Does `getNow` cancel a running task if the caller does not yet have a result?  
**Answer:** No. It only reads state without waiting.

**Q9.** A `Future<Optional<String>>` completes normally with `Optional.empty()`; what does `getNow(null)` return?  
**Answer:** It returns `Optional.empty()`, not `null`, provided the contract guarantees the producer never completes with `null`.

**Q10.** When `isDone()` returns false at t1, can `getNow("WAIT")` at t2 return the actual result?  
**Answer:** Yes. The Future can complete between the two calls.

**Q11.** A `CompletableFuture<Void>` completed normally with `null`. Can `getNow(null)` distinguish it from pending?  
**Answer:** No. You need another state representation, or a marker stage/result envelope.

**Q12.** Does `getNow(expensiveFallback())` avoid calling the fallback if the Future has already completed?  
**Answer:** No. Java evaluates arguments before the method call.

**Q13.** Does a `Future.get(100, MILLISECONDS)` timeout automatically cancel the Future?  
**Answer:** No. It only limits how long the caller waits.

**Q14.** How does `completeOnTimeout("X", ...)` differ from `getNow("X")`?  
**Answer:** `completeOnTimeout` can **complete** the Future with `"X"` when the timeout expires; `getNow` only **temporarily returns `"X"`** to the caller while pending, without modifying the Future.

**Q15.** A source stage is done, but a dependent async mapper is waiting on an executor. What does `getNow` on the final stage return?  
**Answer:** If the final stage is not yet completed, it returns the fallback; completion of the source does not mean the final stage is done.

**Q16.** Should you always replace `thenAccept` with continuous `getNow` polling?  
**Answer:** No. When you need to react upon completion, callbacks/composition are usually clearer and avoid busy-spinning.

**Q17.** A Future completed with an `ArrayList`; the producer keeps modifying the list after `complete`. Does `CompletableFuture` make those subsequent modifications thread-safe?  
**Answer:** No. You need an immutable result, ownership transfer, or synchronization for post-publication mutations.

**Q18.** If the UI needs to distinguish `READY(null)`, `FAILED`, `CANCELLED`, and `PENDING`, what should you design?  
**Answer:** A typed state/result envelope or a helper with a non-colliding sentinel and proper error handling, rather than collapsing everything into `null`.

## Java SE 17 References

- [`CompletableFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `getNow(T valueIfAbsent)`, completion, cancellation, timeout APIs, exceptional completion, `isDone`.
- [`CompletionStage` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): dependent stages and completion propagation.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get` and timed wait, `isDone`, `isCancelled`.
- [`CompletionException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html): unchecked wrapper for completion errors.
- [`CancellationException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html): Future cancellation.
- [`Optional` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): representing a business value that may be absent.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): test coordination independent of scheduling.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): managing workers and shutdown in examples.
- [Java Language Specification `15.7` — Evaluation Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7): evaluation order of method arguments.
- [Java Language Specification `17` — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before and memory visibility.

**Key reminder:** `getNow(valueIfAbsent)` returns **the fallback value only when the Future is not yet completed**, returns **the actual result (including null) on success**, and **throws an exception on failure/cancellation**. In domains where `null` is a valid value, do not use `getNow(null)==null` to conclude pending; use a **non-colliding sentinel**, a **non-null `Optional`/result envelope contract**, or explicit **state classification**, while keeping inter-read races in mind and never turning a non-blocking read into a busy-spin loop.
