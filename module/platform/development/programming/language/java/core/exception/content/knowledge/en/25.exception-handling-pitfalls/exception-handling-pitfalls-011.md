# Catching Programming Errors and Continuing with an Invalid State

In Java, `catch` allows a program to handle an exception. However, **catching an exception does not mean the program has recovered**. A dangerous mistake is catching `NullPointerException`, `IllegalStateException`, `IndexOutOfBoundsException`, or another `RuntimeException` caused by a programming bug, logging a line (or ignoring it), and then continuing to update data or report success as if all initial preconditions still held.

The consequences are often worse than the initial error: an object may be only half-updated, an order may transition to a "confirmed" state even though it was never processed, counters or balances may become inconsistent, transactions may be duplicated, or the real bug may be masked by a later exception.

Core principle: **only continue when you have proven that the post-error state is still valid and you have a genuine recovery strategy**. If the error indicates that a program invariant or assumption has been violated, you generally need to stop the current operation, propagate the failure to an appropriate handling boundary, and return the state to a consistent point.

## 1. Distinguishing "Caught" from "Recovered"

Consider a sequence of operations:

```text
Start request
    |
    v
Change state A
    |
    v
Programming error occurs at step B
    |
    +--> catch (RuntimeException error)
              |
              +--> ignore / log and continue
                        |
                        v
               Change state C
                        |
                        v
              Return success result  <-- dangerous
```

`catch` itself only transfers control to a handling branch. It **does not automatically undo** changes made before the exception, does not automatically release locks or cancel business transactions, and does not verify that variables and resources are in a valid state.

A proper handling approach must be able to answer:

1. Is the error a situation **expected by the contract**, or is it a sign of a bug?
2. What changes were already made before the error occurred?
3. Can they be rolled back, cancelled, or transitioned into a valid failure state?
4. Is the task permitted to return a fallback, retry, or continue with the existing data?
5. How does the caller know that a request failed and must not be treated as a success?

If you cannot answer these questions yet, you should not use `catch` as a shortcut to "keep the program running."

## 2. What Counts as a Programming Error?

Several exceptions often suggest that an assumption in the code has been violated:

| Common exception | Example cause | What to check |
| --- | --- | --- |
| `NullPointerException` | Code accesses an object that the internal contract requires to be non-`null` | Where the data came from, whether null is checked at the right boundary, whether a variable was initialized improperly |
| `IndexOutOfBoundsException` | Accessing a non-existent element; assuming a list has enough elements | List size, loops, boundary conditions |
| `ClassCastException` | Casting to an incorrect actual type | Data type design, generics, input contract |
| `IllegalStateException` | Operation occurs when an object is in a disallowed state | Invariants, state transition ordering, and ownership responsibilities |
| `IllegalArgumentException` | Passing an argument that violates the contract | Is this a caller bug, or external input that requires a valid validation response? |
| `ArithmeticException` | For example, integer division by zero | Mathematical preconditions, data, and calculation branches |
| `AssertionError` | An internal assertion failed when assertions are enabled | Design invariants; do not turn it into a false success |

**Classification must be based on the contract, not just the class name.** `NumberFormatException` is an `IllegalArgumentException`, yet when parsing user-entered text, a malformed string may be an *expected* situation that should return an input validation error. Conversely, a `NullPointerException` in the middle of an algorithm on parameters that were supposedly validated can be a genuine bug.

`RuntimeException` is an unchecked exception; **unchecked does not mean forbidden to catch**, nor does it mean every case is a programming error. What matters is having a handling strategy that matches the root cause and the remaining state.

`Error` types such as `OutOfMemoryError` and `StackOverflowError` generally do not belong to business exceptions that can be recovered from by catching broadly and continuing. In particular, avoid `catch (Throwable error)` just to ignore all errors.

## 3. Invariants and Partial Mutation

An **invariant** is a condition that must hold whenever an object is in a published valid state.

For example, suppose an inventory has a total of 5 units:

\[
\text{available} + \text{reserved} = 5
\]

A valid reservation of 2 units transitions from `(available=5, reserved=0)` to `(available=3, reserved=2)`. If the code modifies `available` first, then discovers the argument is invalid and **swallows the exception**, the invariant can be broken.

Conceptually flawed snippet:

```java
try {
    inventory.available -= quantity;
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }
    inventory.reserved += quantity;
} catch (IllegalArgumentException error) {
    // Ignored; the available field has already been modified.
}
```

This is **illustrative code** requiring an `inventory` object and a `quantity` variable declared by the application, not a standalone program. With `quantity = -2`, the subtraction **increased** `available` by 2 before the exception was thrown. The `catch` block does not automatically restore the numbers.

It is even more dangerous if the code below sets `confirmed=true`, publishes an event, or returns HTTP `200 OK`: other systems may act on a **false success**.

## 4. Runnable Java 17+ Example: Catching and Continuing Corrupts State

Create the file **`InvalidStateAfterCatch.java`**:

```java
public class InvalidStateAfterCatch {
    static final class Inventory {
        final int capacity = 5;
        int available = 5;
        int reserved = 0;
        boolean confirmed;

        boolean invariantHolds() {
            return available >= 0
                    && reserved >= 0
                    && available + reserved == capacity;
        }
    }

    static void reserveWrong(Inventory inventory, int quantity) {
        try {
            inventory.available -= quantity; // Mutated before validation.
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            inventory.reserved += quantity;
            inventory.confirmed = true;
        } catch (IllegalArgumentException ignored) {
            // Wrong: marks success even though the state was partially mutated.
            inventory.confirmed = true;
        }
    }

    static void reserveCorrect(Inventory inventory, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        if (quantity > inventory.available) {
            throw new IllegalStateException("insufficient stock");
        }

        int nextAvailable = inventory.available - quantity;
        int nextReserved = inventory.reserved + quantity;
        if (nextAvailable < 0
                || nextReserved < 0
                || nextAvailable + nextReserved != inventory.capacity) {
            throw new IllegalStateException("inventory invariant broken");
        }

        inventory.available = nextAvailable;
        inventory.reserved = nextReserved;
        inventory.confirmed = true;
    }

    static void print(String label, Inventory inventory) {
        System.out.println(label + " available=" + inventory.available
                + " reserved=" + inventory.reserved
                + " confirmed=" + inventory.confirmed
                + " valid=" + inventory.invariantHolds());
    }

    public static void main(String[] args) {
        Inventory wrong = new Inventory();
        reserveWrong(wrong, -2);
        print("wrong", wrong);

        Inventory correct = new Inventory();
        try {
            reserveCorrect(correct, -2);
        } catch (IllegalArgumentException error) {
            System.out.println("rejected="
                    + error.getClass().getSimpleName());
        }
        print("afterReject", correct);

        reserveCorrect(correct, 2);
        print("afterSuccess", correct);
    }
}
```

Compile and run with Java 17:

```bash
javac --release 17 InvalidStateAfterCatch.java
java InvalidStateAfterCatch
```

Exact output:

```text
wrong available=7 reserved=0 confirmed=true valid=false
rejected=IllegalArgumentException
afterReject available=5 reserved=0 confirmed=false valid=true
afterSuccess available=3 reserved=2 confirmed=true valid=true
```

**Analysis:**

- `reserveWrong(..., -2)` mutates `available` to `7` before detecting the invalid argument. The exception is swallowed and `confirmed=true`. The sum `available + reserved = 7` violates `capacity=5`: the code reported success in an invalid state.
- `reserveCorrect(..., -2)` validates preconditions before any mutation. The error is propagated to the caller, the object remains `(5,0,false)`, and the invariant holds.
- `reserveCorrect(..., 2)` computes the projected values, checks the invariant, and only then publishes the changes, producing `(3,2,true)`.

The example above is a **single-threaded model with in-memory fields**. It demonstrates the idea of validating before mutating, **not an atomic transaction** for multiple threads or distributed systems. If concurrent access exists, appropriate synchronization or atomic state is required. If a database or external service has already been called, a real transaction, cancellation, or compensation mechanism is also needed.

## 5. What Conditions Does Genuine Recovery Require?

A `catch` branch may continue when it **knows clearly what failed**, **knows what can be done after the failure**, and **preserves invariants**.

Examples of situations that may be permitted by the contract:

- A user enters a malformed number: catch `NumberFormatException`, return a response asking to fix the input, and do not update business state.
- A cache is unavailable while the primary source is still healthy: log a warning, read from the primary source, and control side effects to avoid duplicate results.
- Reading an optional configuration file fails: choose a documented default if that default is **genuinely valid** for the application.
- An operation designed to be idempotent fails transiently: it may be retried with time/attempt limits, but you must verify the error type, resources, and safety of retrying.

Conversely, if `IllegalStateException` indicates that reserved quantity and stock are out of balance, logging and continuing to "sell" **is not recovery**. To recover, you must fix or reconstruct the state according to verified rules—not assign an arbitrary value just to pass a check.

A short checklist for a recovery branch:

1. **Expected and narrowly classified exception.** Do not use `catch (Exception ignored)` in place of an error contract.
2. **No uncontrolled side effects.** Changes made before the error have been rolled back, compensated, or exist in a clearly designed failure state.
3. **Honest output.** If the operation has not completed, do not return a result claiming "completed."
4. **Observable and testable.** Logs/metrics reflect fallback or retry usage; tests also verify the post-error state.
5. **Bounded.** If retries fail repeatedly, stop and propagate the error instead of creating an infinite loop.

## 6. Catching the Right Error Type Instead of `catch (RuntimeException)` and Defaulting to Success

Another common mistake: using an overly broad `catch` for both invalid input **and** bugs.

```java
String parseWrong(String raw) {
    try {
        int quantity = Integer.parseInt(raw.trim());
        return "accepted:" + quantity;
    } catch (RuntimeException ignored) {
        return "accepted:0";
    }
}
```

The snippet above is an **illustrative method**, not a standalone program. It catches both `NumberFormatException` and `NullPointerException` from `raw.trim()`, then returns a seemingly valid result. If an internal layer has a contract that `raw` must not be `null`, the caller has just violated the contract, yet the failure is turned into "accepted 0."

At an external input boundary, `null` may also be an **expected input that must be rejected**. In that case, validate it explicitly during the validation step rather than letting an accidental `NullPointerException` act as the input-classification protocol.

### Second example: narrow classification and stopping contract-violating requests

Create the file **`NarrowCatchBoundary.java`**:

```java
import java.util.Objects;

public class NarrowCatchBoundary {
    static String wrong(String raw) {
        try {
            return "accepted:" + Integer.parseInt(raw.trim());
        } catch (RuntimeException ignored) {
            return "accepted:0";
        }
    }

    static String correct(String nonNullRaw) {
        Objects.requireNonNull(nonNullRaw, "nonNullRaw");
        try {
            return "accepted:" + Integer.parseInt(nonNullRaw);
        } catch (NumberFormatException expected) {
            return "invalid number";
        }
    }

    public static void main(String[] args) {
        System.out.println("wrongNull=" + wrong(null));
        System.out.println("valid=" + correct("5"));
        System.out.println("badFormat=" + correct("oops"));

        try {
            correct(null);
        } catch (NullPointerException unexpected) {
            System.out.println("requestFailed="
                    + unexpected.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac --release 17 NarrowCatchBoundary.java
java NarrowCatchBoundary
```

Output:

```text
wrongNull=accepted:0
valid=accepted:5
badFormat=invalid number
requestFailed=NullPointerException
```

In `correct`, `nonNullRaw` is an **internal contract**. Invalid format (`"oops"`) is a situation the method intentionally classifies and returns `"invalid number"` for; passing `null` violates the contract, so `Objects.requireNonNull` fails and the operation does not pretend to succeed. `main` acts as the **demo boundary**: it catches the unexpected error to illustrate that the request failed; the inner business code does not continue.

Note: the example returns strings only for easy observation. In a real application, use an explicit result type (e.g., `Result`, an enum/error code, HTTP 400 for invalid input, HTTP 500 for internal bugs) rather than forcing callers to parse English strings.

## 7. Why Continuing After a Programming Error Easily Causes Cascading Failures

Suppose a program has a state sequence:

```text
CREATED -> VALIDATED -> RESERVED -> PAID -> CONFIRMED
```

If the `RESERVED` step throws `IllegalStateException` due to a quantity imbalance, yet `catch` transitions the state to `PAID`, subsequent steps may:

- Charge money without locking the resource/product.
- Emit an event to the fulfillment system based on an order that was never successfully reserved.
- Write a "paid" history table entry while the main business table remains in the "created" state.
- Trigger a retry from an outer layer while part of the first attempt's side effects already happened.
- Cause a further `NullPointerException` or `ClassCastException` later, hiding the original error.

The second error often appears **far from where the first error occurred**, making its stack trace hard to explain the root cause. Preserving and propagating the first error to the handling boundary shortens the diagnostic path.

Design state transitions around clear publication points. If all required steps have not completed, do not transition the object to a state that permits the next step. When execution has remote side effects, intermediate states such as `PENDING`, `FAILED`, or `REQUIRES_RECONCILIATION` may be necessary; do not simply "go back to the beginning" when the actual external outcome is unknown.

## 8. Fail Fast: Stop the Right Scope, Not Necessarily the Entire JVM

**Fail fast** means detecting an assumption violation as early as possible and **not continuing to use data that has lost trustworthiness**. It does not mean always calling `System.exit`, shutting down the entire JVM, or letting every request kill the service.

For example, in a web service:

1. The processing layer detects an unrecoverable `IllegalStateException`.
2. The current business operation stops; the transaction is marked for rollback when an appropriate transaction exists.
3. The error handler at the request boundary logs the full `Throwable` with a safe correlation ID.
4. The caller receives an honest failure result; the system does not publish "success."
5. Other workers/requests with isolated state can still be served if the platform remains safe.

If the error breaks a **global invariant** or renders the component untrustworthy (for example, corrupted shared memory), the action may need to be stricter: take the component out of traffic, reject new tasks, or perform a controlled restart. However, that decision should be based on how far the corruption has spread, not merely on seeing a `RuntimeException`.

If a request fails before any data changes, returning an error is sufficient. If data was partially modified, **returning an error does not fix the data**: rollback, recovery, or isolation is still required.

## 9. Transactions, Rollback, and External Side Effects

To avoid half-baked state, the processing order should be:

```text
Validate input and invariants
        |
        v
Compute projected state
        |
        v
Start rollbackable unit of work / transaction
        |
        v
Apply changes within the same atomic boundary
        |
        +-- error --> rollback / mark FAILED / compensate
        |
        v
Commit or publish completion
```

This is a conceptual diagram and does not guarantee that every side effect belongs to a single transaction.

**For single-threaded memory:** you can validate first, compute new values into local variables, and only then assign them to the object. If updating multiple objects or running across multiple threads, use proper synchronization/atomic mechanisms; a few consecutive assignments do not automatically become atomic.

**For databases:** use transactions with clear boundaries and roll back on failure according to your technology's configuration. Do not assume that catching an exception and returning success will still cause the framework to roll back; in some frameworks, swallowing the exception makes the transaction look as if it completed normally.

**For HTTP, payments, message queues:** an external operation may have already completed even if the client receives a timeout or error. Local database rollback does not erase external side effects. When needed, design idempotency keys, outboxes, saga/compensating actions, or reconciliation states. Do not retry blindly just because you "caught the error."

**For resources:** use `try-with-resources` and `finally` to close owned resources; do not treat resource cleanup as a license to continue business logic with invalid data.

## 10. Catch at the Right Boundary and Preserve the Cause

When a bug or broken invariant occurs, preserve information for investigation.

Illustrative example with SLF4J, not a standalone Java program (`logger`, `requestId`, and `service` are provided by the application):

```java
try {
    service.execute();
} catch (IllegalStateException error) {
    logger.error("Request {} failed with invalid state", requestId, error);
    throw error;
}
```

This logs the **`Throwable` object** rather than just `error.getMessage()`, and rethrows the error. In a multi-layered service, avoid logging the same stack trace at every layer; decide who owns logging at the outer boundary to reduce duplicate logs.

If you need to translate to a more meaningful error type, **preserve the cause**:

```java
try {
    repository.save(order);
} catch (java.io.IOException cause) {
    throw new IllegalStateException("Cannot persist order", cause);
}
```

This is illustrative code requiring `repository` and `order`. `cause` allows tracing the original error; `throw new IllegalStateException(cause.getMessage())` loses the cause chain. However, do not wrap an unrecoverable `IllegalStateException` into a "user input error" code if the underlying issue is an internal bug.

In a global error handler, you can translate the error into a response structure **without a stack trace** for the user while logging internal details via the logger. Avoid letting passwords, tokens, personal data, or arbitrary input contents leak into messages/logs.

## 11. `finally` and `try-with-resources` Do Not Mean You May Continue

`finally` normally runs on the exit path of `try`/`catch`, even when an error occurs, but **cleanup is not business-state recovery**:

```java
try {
    persistBusinessChanges();
} catch (RuntimeException error) {
    logger.error("Persistence failed", error);
} finally {
    notifySuccess(); // Wrong: still runs when persisting data fails.
}
```

This is an illustrative snippet with application methods/logger. Only emit a success event after the operation has actually completed or committed. `try-with-resources` can close resources and preserve suppressed exceptions when `close()` fails, but it **does not automatically roll back side effects**.

In this article, stopping processing of **invalid state** is the focus; exception precedence when `finally` throws or `close()` fails is covered in separate cleanup articles.

## 12. Overly Broad `catch` Blocks That Hide Errors

Patterns to watch out for:

```java
catch (Exception ignored) {
    return null;
}
```

```java
catch (RuntimeException error) {
    return true;
}
```

```java
catch (Throwable error) {
    continue;
}
```

These are **anti-pattern code snippets**, not standalone Java blocks. In each case, the caller cannot distinguish a successful operation from a hidden error; in particular, `catch (Throwable)` also includes `Error`, which should generally not be treated as a signal handleable like a normal business error.

In a batch-processing loop, there may be a valid reason to **skip an invalid record**, but you must scope the error, isolate the record, record the failure, and continue **with a state designed for that skip**. Do not catch all exceptions and keep using the very object suspected of being corrupted.

For example, a batch job can classify formatting errors for **each independent line**, record `INVALID_INPUT` for that line, and move on to the next line. However, if an unexpected `NullPointerException` reveals that the parser holds corrupted shared state, continuing the entire batch can propagate bad data. The isolation boundary determines the appropriate behavior.

## 13. Asynchronous Tasks and Swallowed Exceptions

In `ExecutorService` or `CompletableFuture`, a programming error may occur on a worker thread and only be observed via `Future.get()` or `CompletableFuture.join()`.

Illustrative example:

```java
CompletableFuture<Order> result =
        CompletableFuture.supplyAsync(() -> processOrder(order));
```

This snippet requires declarations for `Order`, `order`, and `processOrder`. If the lambda throws `IllegalStateException`, the future can complete exceptionally. But if the lambda catches `RuntimeException` itself, returns a fake-success `Order`, or sets `confirmed=true`, the future will be considered **completed normally**, leaving the caller unaware of the problem.

With `CompletableFuture`, `exceptionally(error -> fallback)` can intentionally turn a failure into a success value. Only do this when the fallback is **permitted by the contract** and does not hide a bug that leaves data inconsistent. Do not attach `exceptionally(error -> new Order("SUCCESS"))` to every pipeline as generic error handling.

Similarly, `Future.isDone()` and `CompletableFuture.isDone()` only state that the future has finished (which may be normally, exceptionally, or cancelled); they do not prove that business changes succeeded. When `join()` throws `CompletionException` or `get()` throws `ExecutionException`, inspect the cause to find the real failure rather than catching the wrapper and assuming the request succeeded.

## 14. Retries and Fallbacks Are Only Safe Under Specific Conditions

A transient error from an external service may be retried, whereas a programming error such as an invalid index access, bad cast, or broken invariant usually **does not disappear** by repeating with the same data. Unconditional retries can increase load, create duplicate operations, and mask bugs.

Before retrying, you need:

- An error type or status code identified as transient.
- An operation verified to be safe to re-run or backed by an idempotency key.
- A policy bounding retry count, backoff delay, and total deadline.
- Confirmation that the state after the previous failure is valid.
- Logs/metrics to distinguish a retry from a genuine first-try success.

The same applies to fallbacks. A failed cache when the primary source is healthy can return data from the primary source; conversely, an error that makes pricing data inconsistent cannot be fixed by returning `0` and recording a successful order.

If you cannot prove that a retry/fallback is safe, you must **propagate the failure to a layer that can decide** rather than fabricating recovery.

## 15. Test Failure Paths and Invariants, Not Just Exceptions

Good tests do not merely assert `"method threw IllegalArgumentException"`; they also assert that **the object remains valid after the error**, side effects are right, and the caller receives the failure.

For the `Inventory` example, scenarios to test:

| Scenario | Expected error/result | Expected state |
| --- | --- | --- |
| `quantity = -2` | Reject with `IllegalArgumentException` | Preserve `(available=5, reserved=0, confirmed=false)` |
| `quantity = 0` | Reject as invalid input | No data mutation |
| `quantity > available` | Disallow reservation | Do not create negative stock or increase `reserved` |
| `quantity = 2` | Success | `(available=3, reserved=2, confirmed=true)` |
| Mid-operation bug after a side effect | Request fails | Clear rollback, compensation, or FAILED state |
| Two concurrent operations | Do not violate capacity | Protect consistency with synchronization/transaction |

In JUnit 5 (illustrative snippet requiring JUnit imports and corresponding class/state declarations), you can write:

```java
assertThrows(IllegalArgumentException.class,
        () -> reserveCorrect(state, -2));
assertEquals(5, state.available);
assertEquals(0, state.reserved);
assertFalse(state.confirmed);
assertTrue(state.invariantHolds());
```

This is **not a standalone program**; `assertThrows`, `assertEquals`, `assertFalse`, and `assertTrue` are JUnit 5 APIs. Java 17 does not bundle JUnit. The goal is to test **the failure path and invariants**, not only that an exception was thrown.

If the code needs to roll back a transaction, integration tests should verify that database data is not committed after an error. If there are external operations, test retry outcomes, idempotency, or reconciliation; a unit test on an in-memory object does not cover all side effects.

## 16. Distinguishing Boundary Catching from Swallowing Errors in Business Logic

A service may use a global error handler to turn an exception into HTTP 500 or a safe error message. Syntactically, that is still "catching an error"; however, it is fundamentally different from **swallowing an error in the middle of a business flow**.

| Catching in the business layer and continuing | Catching at the boundary to end the request |
| --- | --- |
| May keep invalid state for subsequent steps | Does not run subsequent steps of the failed request |
| Easily returns false success | Returns an honest failure result |
| Does not automatically roll back | Can combine transaction rollback and contract-based recovery |
| Often hides the root cause | Can log the `Throwable` and correlation ID |
| Very hard to distinguish safe retries | Orchestration layer can decide retry/fail based on the cause |

Catching at the outer layer **does not automatically fix already-mutated state**: you still need to define transaction boundaries, resources, and side-effect handling. However, it preserves the rule that subsequent business steps must not continue with bad data.

If a multi-tenant service hits a bug in only one request, isolate the failure to that request or worker while keeping unrelated work running when safe. If an invariant of global state is broken, assess the health of the entire component rather than continuing blindly.

## 17. Common Mistakes Found in Code Reviews

| Bad pattern | Risk | Appropriate alternative |
| --- | --- | --- |
| `catch (NullPointerException e) {}` | Hides null-assumption bugs; processing continues with uncertain data | Clarify the null contract, fix the source of the bug; fail if invariants are not guaranteed |
| `catch (RuntimeException e) { return true; }` | Returns false success | Return a failure result or rethrow; only fall back on expected errors |
| Mutate object first, then validate and swallow error | Partially updated state | Validate first, compute new state, commit at a safe point |
| `catch (Exception e)` only to `System.out.println(e.getMessage())` | Error is hidden, stack/cause lost | Log the `Throwable` object at the handling boundary and propagate failure |
| `finally { markSuccess(); }` | Marks success even on error | Only mark after the commit step succeeds |
| Catch `Throwable` so the app "never errors" | May swallow serious `Error`s | Do not catch overly broadly; only catch at a responsible boundary |
| Retry every `IllegalStateException` | Repeats bugs, amplifies side effects | Only retry classified, safe transient errors |
| `exceptionally(e -> successValue)` for all errors | `CompletableFuture` reports success despite bugs | Only recover error types/cases allowed by the contract |
| Test only `assertThrows` without checking state | Misses partial mutation | Assert state, transaction, and side effects as well |
| Catch exception and ignore interrupted status | Fails to respond to cooperative cancellation | Handle/restore interruption per task contract |

## 18. Self-Check

**Question 1.** After updating half of an object, a method throws `IllegalStateException`. Does catching and logging it automatically restore the object?  
**Answer:** No. `catch` only transfers control. You must roll back, compensate, or avoid publishing invalid state.

**Question 2.** Is `NullPointerException` always a programming error that must never be caught?  
**Answer:** You cannot conclude that from the class name alone. However, if it reflects a violated internal assumption, swallowing it and continuing is usually dangerous. Validate input at boundaries and use an explicit error policy.

**Question 3.** Is it valid for a parser to catch `NumberFormatException` and return `INVALID_INPUT` to the user?  
**Answer:** It can be valid if malformed strings are an expected situation, no state has been mutated, and the caller receives a clear error result.

**Question 4.** Why can `catch (RuntimeException error) { return 0; }` hide bugs?  
**Answer:** Because many unrelated errors, such as `NullPointerException` and `IndexOutOfBoundsException`, are subclasses of `RuntimeException`. Returning `0` prevents the caller from knowing an unexpected failure occurred.

**Question 5.** Is `finally` appropriate for setting `order.confirmed = true`?  
**Answer:** No, because `finally` also runs when the operation fails. It is meant for cleanup, not unconditional success confirmation.

**Question 6.** What is the risk of `CompletableFuture.exceptionally(e -> fallback)`?  
**Answer:** It can turn even bugs into normal completion results. Only use a fallback when you know the state and error type permit it.

**Question 7.** Is catching an error in a controller and returning HTTP 500 the same as swallowing an error in a service?  
**Answer:** No. A controller can end the request with an honest failure; a service swallowing an error and continuing can cause corruption. Even so, the controller/boundary still needs proper transactions or compensation if state was already mutated.

**Question 8.** When should other workers be allowed to continue?  
**Answer:** When workers have isolated state and the failure does not corrupt shared invariants; the failed worker must be marked and handled separately.

**Question 9.** Is a network error guaranteed to be safe to retry?  
**Answer:** No. You must check whether the request already produced side effects, whether the error is transient, and whether idempotency or reconciliation is in place.

**Question 10.** After catching an exception, what is the minimum requirement to continue?  
**Answer:** A clearly designed recovery policy, state and resources remaining in a valid condition, controlled side effects, and output that honestly reflects the outcome.

## 19. References

- [Java 17 — `RuntimeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): group of unchecked exceptions that often need classification by contract.
- [Java 17 — `IllegalStateException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalStateException.html): exception representing a state that does not permit the operation.
- [Java 17 — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): stack trace, cause, suppressed exceptions, and throw/catch mechanics.
- [Java 17 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): exceptional completion state, `exceptionally`, `handle`, `join`.
- [Java 17 — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): verifies a non-null object contract.

**Key takeaway:** a `catch` does not prove recovery is possible. When an error occurs due to a violated internal assumption, **do not continue using potentially corrupted state or report a false success**. Validate invariants before publishing changes, stop the appropriate unit of work, preserve the original error for diagnosis, and only continue when a verified recovery strategy is in place.