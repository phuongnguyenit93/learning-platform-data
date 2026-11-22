# Testing `finally` Without Masking Errors or Unintentionally Altering Results

In Java, `finally` is commonly used to clean up after a `try` block, regardless of whether that block completes normally or with an exception. Precisely because it executes across multiple exit paths, `finally` can easily introduce subtle bugs: **a `return` statement in `finally` can override the return value or swallow an exception being propagated**, while **an exception thrown during cleanup can mask the original exception**. In addition, if `finally` mutates an object or shared state, the value received by the caller may differ from what was originally intended even if no new exception is thrown.

The goal of this lesson is to build **behavioral tests** to catch those exact defects. We will observe the execution order of `try`–`catch`–`finally`, distinguish between the return value and the state of an object, test dual failures (a primary processing error and a cleanup error), write tests that verify state invariants, and understand when to use `try-with-resources`.

## 1. The Basic Contract of `finally`

Typical structure:

```java
try {
    performOperation();
} catch (ExpectedException error) {
    handleExpectedError(error);
} finally {
    releaseOwnedResource();
}
```

This is **illustrative code** and does not compile standalone because the dependent methods and types must be defined by the application.

Key points to remember:

1. If `try` completes normally and no other statement alters control flow, `finally` executes before continuing to the code after it.
2. If `try` is about to `return` or `throw`, Java also executes `finally` before returning or propagating the exception outward.
3. If `catch` is about to `return` or `throw`, `finally` still runs on that exit path.
4. If **`finally` itself completes abruptly** via `throw`, `return`, `break`, or `continue`, the pending completion from `try`/`catch` can be **replaced**. This is the source of masked errors or altered results.
5. `finally` is not guaranteed to run in **every** conceivable situation: for example, if the JVM terminates abruptly, the process is killed, or a thread never leaves `try`. Do not rely on `finally` as an absolute guarantee against power loss or process crashes.

Therefore, do not only verify that cleanup was called; also verify **which exception reaches the caller**, **which value is returned**, and **what the business state is after cleanup**.

## 2. Risks That Must Be Covered in the Test Suite

| Scenario | Behavior to Identify | Test Assertion |
| --- | --- | --- |
| `try` succeeds, `finally` completes normally | Cleanup runs, original result is preserved | Return value and cleanup count are correct |
| `try` throws, `finally` completes normally | Original error reaches caller | Correct exception type, message, and required cause/identity |
| `try` returns a value, `finally` also executes `return` | Value from `finally` **overrides** | Test must detect the wrong result |
| `try` throws, `finally` executes `return` | Original exception is **swallowed** | Test expecting the exception must fail |
| `try` throws, `finally` also throws | Cleanup error may **mask** primary error | Both errors are preserved or reported completely |
| `try` returns an object reference, `finally` mutates that object | Caller may observe the mutated object | Check actual state, not just reference equality |
| `try-with-resources` fails in both body and `close()` | Body error is usually primary, `close()` is suppressed | Check `getSuppressed()` |
| Cleanup is called multiple times or not called | Resource leak, unintended side effects | Check cleanup invocation count on each exit path |

**Testing rule:** include at least one case for the success path, one case for a failure in the primary operation, and one case for a failure during cleanup. For code that returns data or mutates state, add invariant and return-value assertions.

## 3. `return` in `finally` Overrides `return` in `try`

Consider the following method:

```java
int calculate() {
    try {
        return 10;
    } finally {
        return 20;
    }
}
```

The method **returns `20`**, not `10`. This is an illustrative Java snippet that can be placed inside a class, though it is not a standalone program. At `return 10`, Java has already determined a pending result. However, the `return 20` statement in `finally` completes the method with a new result and replaces the old one.

The same thing also happens with exceptions:

```java
int hideFailure() {
    try {
        throw new IllegalStateException("original failed");
    } finally {
        return 20;
    }
}
```

In this case, the caller receives **`20` as a normal result**, and `IllegalStateException("original failed")` is never propagated. A serious programming error can be turned into a false success.

**Do not place `return` inside `finally`.** If a piece of code uses `finally` solely for cleanup, design cleanup so that it does not participate in deciding whether the primary operation succeeded or failed. Tests must assert that an error in `try` still reaches the caller.

## 4. An Exception in `finally` Can Mask the Original Exception

The following snippet throws from both places:

```java
void perform() {
    try {
        throw new IllegalArgumentException("business failed");
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

The caller usually catches only `IllegalStateException("cleanup failed")`. The `IllegalArgumentException("business failed")` exception is replaced by the abrupt completion of `finally`. Java **does not automatically add the primary error to `getSuppressed()`** in a manual `try/finally` block like this.

This is why a test that only uses `assertThrows(IllegalStateException.class, ...)` can produce a **false pass**: it sees an exception, yet fails to detect that the primary error was masked. You need to assert the exception type **expected by the contract**, the message or cause/suppressed exceptions, and the post-operation state.

If cleanup can also fail, define a clear policy:

- Should the primary processing error take precedence? If so, preserve the primary error and attach the cleanup error as suppressed when appropriate.
- Only a cleanup error occurred, with no processing error? Then the cleanup error may be the primary error to throw.
- Cleanup failed without affecting the operation's contract? Only continue if ignoring that error is **explicitly designed**; a failure to close a resource can indicate data loss, so it cannot be ignored by default.
- When using `AutoCloseable`, prefer `try-with-resources` so Java enforces the exception-precedence rules when both the `try` body and `close()` throw.

## 5. Runnable Java 17+ Example: Distinguishing `return` and `throw` Paths

Create the file **`FinallyControlFlowDemo.java`**:

```java
public class FinallyControlFlowDemo {
    static int safeReturn() {
        try {
            return 10;
        } finally {
            System.out.println("cleanup ran");
        }
    }

    static int overrideReturn() {
        try {
            return 10;
        } finally {
            return 20; // Counterexample: overrides the result.
        }
    }

    static int swallowFailure() {
        try {
            throw new IllegalArgumentException("original failed");
        } finally {
            return 30; // Counterexample: swallows the exception.
        }
    }

    static void maskFailure() {
        try {
            throw new IllegalArgumentException("original failed");
        } finally {
            throw new IllegalStateException("cleanup failed");
        }
    }

    static void preserveFailure() {
        try {
            throw new IllegalArgumentException("original failed");
        } finally {
            System.out.println("cleanup completed");
        }
    }

    static StringBuilder mutableReturn() {
        StringBuilder result = new StringBuilder("initial");
        try {
            return result;
        } finally {
            result.append("-changed");
        }
    }

    public static void main(String[] args) {
        System.out.println("safeReturn=" + safeReturn());
        System.out.println("overrideReturn=" + overrideReturn());
        System.out.println("swallowFailure=" + swallowFailure());

        try {
            maskFailure();
        } catch (RuntimeException error) {
            System.out.println("maskedType="
                    + error.getClass().getSimpleName());
            System.out.println("maskedMessage=" + error.getMessage());
            System.out.println("maskedCause=" + error.getCause());
            System.out.println("maskedSuppressed="
                    + error.getSuppressed().length);
        }

        try {
            preserveFailure();
        } catch (IllegalArgumentException error) {
            System.out.println("preservedMessage=" + error.getMessage());
        }

        System.out.println("mutableReturn=" + mutableReturn());
    }
}
```

Compile and run with Java 17:

```bash
javac --release 17 FinallyControlFlowDemo.java
java FinallyControlFlowDemo
```

Expected output:

```text
cleanup ran
safeReturn=10
overrideReturn=20
swallowFailure=30
maskedType=IllegalStateException
maskedMessage=cleanup failed
maskedCause=null
maskedSuppressed=0
cleanup completed
preservedMessage=original failed
mutableReturn=initial-changed
```

**What this example demonstrates:**

- `safeReturn()` lets `finally` clean up and still returns the **original value 10**.
- `overrideReturn()` returns **20** even though the `try` branch intended to return 10.
- `swallowFailure()` returns **30** and completely loses the `original failed` error signal at the call boundary.
- `maskFailure()` exposes only the cleanup error and **does not automatically** set the original error as cause or suppressed.
- `preserveFailure()` allows the original error to reach the caller after a `finally` block that completes normally.
- `mutableReturn()` shows that **the reference selected for return** still points to the `StringBuilder` object that `finally` just modified. Do not confuse Java having already evaluated the `return` value with the mutable object being "frozen".

A subtle distinction: if `try` returns a **primitive value** or an already-computed `String`, modifying a local variable in `finally` normally does not replace the evaluated return value. However, if the return value is a **reference to a mutable object**, the object's contents can change before the caller receives it. Both cases should be tested separately when an API returns a collection, DTO, or stateful object.

## 6. When `finally` Mutates State, What Should You Test?

Exceptions are not the only hazard. A `finally` block may write data, update counters, close resources, or publish events. These actions can cause the actual outcome to differ from the state prepared by the `try` branch.

Counterexample:

```java
OrderResult execute(OrderResult result) {
    try {
        result.markCompleted();
        return result;
    } finally {
        result.markCancelled(); // Mutates the already-returned object.
    }
}
```

This is **illustrative code** that requires declaring `OrderResult` with its two corresponding methods, not a standalone program. The caller receives the same `result` object, but after `finally` runs, its status flag may be `CANCELLED` instead of `COMPLETED`. A test using only `assertSame(result, returned)` will not catch this bug; you must assert the **internal state values**.

For objects shared across multiple threads, `finally` can also mutate data while other work is accessing it. Proper synchronization and clear ownership boundaries are required; do not treat `finally` as an atomic operation.

Your test suite should verify:

1. Business fields retain the expected state after `return`.
2. Cleanup only cleans up **owned resources**, without inadvertently mutating data the caller needs to use.
3. No callbacks, events, or DB writes marking success run in `finally` when `try` fails.
4. Post-exception state matches the designed rollback or failure policy.
5. Closing resources does not render the returned object unusable if the contract requires the caller to use it afterward.

A common buggy pattern:

```java
try {
    persistChanges();
} catch (Exception error) {
    logFailure(error);
} finally {
    publishSuccessEvent();
}
```

This is an illustrative snippet requiring the dependent methods. `publishSuccessEvent()` runs even when `persistChanges()` fails, creating a "false success". Success events should be published after the operation has actually committed successfully, not unconditionally in `finally`.

## 7. `try-with-resources` Preserves the Original Error Using Suppressed Exceptions

A common risk is that both primary processing and resource closing fail. With `try-with-resources`, Java clearly defines how these two errors are handled:

- If the `try` body throws error A and `close()` throws error B, A normally remains the **primary exception**, and B is added to `A.getSuppressed()`.
- If the `try` body succeeds but `close()` throws error B, B is the exception propagated outward.
- If multiple resources fail to close, there can be multiple suppressed exceptions. Resources in `try-with-resources` are closed **in reverse order** of their declaration.
- Suppression is a secondary error-reporting mechanism, **not** a rollback mechanism for business changes.
- If an exception is created with suppression disabled, secondary errors may be stored differently; do not assume every custom `Throwable` always retains suppressed errors.

A condensed example:

```java
try (SomeResource resource = openResource()) {
    performBody(resource);
}
```

This is non-standalone illustrative code because it requires `SomeResource` (implementing `AutoCloseable`) and the methods `openResource()` and `performBody(...)`.

Compare this with a manual `finally` block:

```java
try {
    performBody();
} finally {
    resource.close();
}
```

This is also illustrative code only. If both `performBody()` and `resource.close()` throw exceptions, the `close()` call in `finally` can **mask** the error from `performBody()`. There is no automatic rule moving the cleanup error into suppressed exceptions as in `try-with-resources`. You must change the design to preserve the primary error.

## 8. Runnable Java 17+ Example: A Self-Contained Test Suite for Cleanup

The following example uses small assertion helpers in `main`, requiring no JUnit or external libraries. It tests four paths of `try-with-resources`: success, `try`-body failure only, resource-close failure only, and **dual failure**. It also verifies that the resource was closed and how many times it was closed.

Create the file **`FinallyCleanupContractDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;

public class FinallyCleanupContractDemo {
    static final class Resource implements AutoCloseable {
        final boolean failOnClose;
        int closeCount;

        Resource(boolean failOnClose) {
            this.failOnClose = failOnClose;
        }

        @Override
        public void close() throws IOException {
            closeCount++;
            if (failOnClose) {
                throw new IOException("close failed");
            }
        }
    }

    static void execute(
            boolean failBody,
            boolean failClose,
            AtomicReference<Resource> reference) throws IOException {
        Resource resource = new Resource(failClose);
        reference.set(resource);

        try (resource) {
            if (failBody) {
                throw new IOException("body failed");
            }
        }
    }

    static void require(boolean condition, String explanation) {
        if (!condition) {
            throw new AssertionError(explanation);
        }
    }

    static void verify(
            boolean failBody, boolean failClose,
            String expectedPrimary, int expectedSuppressed) {
        AtomicReference<Resource> reference = new AtomicReference<>();
        IOException caught = null;

        try {
            execute(failBody, failClose, reference);
        } catch (IOException error) {
            caught = error;
        }

        Resource resource = reference.get();
        require(resource != null, "resource was not created");
        require(resource.closeCount == 1, "close must execute exactly once");

        if (expectedPrimary == null) {
            require(caught == null, "unexpected IOException");
        } else {
            require(caught != null, "expected IOException");
            require(expectedPrimary.equals(caught.getMessage()),
                    "wrong primary exception");
            require(caught.getSuppressed().length == expectedSuppressed,
                    "wrong suppressed count");
            if (expectedSuppressed == 1) {
                require("close failed".equals(
                        caught.getSuppressed()[0].getMessage()),
                        "wrong suppressed exception");
            }
        }
    }

    public static void main(String[] args) {
        verify(false, false, null, 0);
        System.out.println("success: PASS");

        verify(true, false, "body failed", 0);
        System.out.println("body failure: PASS");

        verify(false, true, "close failed", 0);
        System.out.println("close failure: PASS");

        verify(true, true, "body failed", 1);
        System.out.println("dual failure preserves body: PASS");
    }
}
```

Compile and run:

```bash
javac --release 17 FinallyCleanupContractDemo.java
java FinallyCleanupContractDemo
```

Output when all conditions hold:

```text
success: PASS
body failure: PASS
close failure: PASS
dual failure preserves body: PASS
```

If any condition is violated, the program throws an `AssertionError` and does not print the corresponding `PASS` line.

**Key takeaways from this test structure:**

- `AtomicReference<Resource>` lets the test inspect the `Resource` created inside `execute`. In this sequential example it mainly serves as a way to pass the reference out for inspection, **not as proof of atomicity for a multithreaded operation**.
- `closeCount == 1` verifies that cleanup ran the exact number of times on both success and failure paths.
- `expectedPrimary` checks **the primary error's message**, not merely that "an error occurred".
- When `failBody && failClose`, the test requires `body failed` to be the primary error and `close failed` to be in `getSuppressed()` of that exact error.
- When only `close()` fails, the test allows the cleanup error to become the **primary error** because there is no `try`-body error that needs precedence.

This style of testing is far more useful than `try { execute(); } catch (Exception ignored) {}`: it makes the error contract explicit and will fail if a cleanup refactor accidentally masks the original exception.

## 9. If You Must Use Manual `finally`, How Do You Preserve the Primary Error?

Some resources do not implement `AutoCloseable`, or the application must perform specialized cleanup. In that case, you should not just add `finally { close(); }` and assume dual-failure scenarios are handled.

A conceptual approach is:

1. Record the primary error when it is thrown.
2. When cleanup fails, if **a primary error already exists**, attach the cleanup error to it with `addSuppressed(...)` (when appropriate).
3. If **no primary error exists**, let the cleanup error propagate according to the contract.
4. Do not use `return` in `finally`, and do not construct a new exception solely from `getMessage()` that loses the cause.

Illustrative Java snippet inside a method permitted to propagate `Exception`:

```java
Exception primary = null;
try {
    doWork();
} catch (Exception failure) {
    primary = failure;
    throw failure;
} finally {
    try {
        cleanup();
    } catch (Exception cleanupFailure) {
        if (primary != null) {
            primary.addSuppressed(cleanupFailure);
        } else {
            throw cleanupFailure;
        }
    }
}
```

The snippet above **is not a standalone program** because it requires `doWork()` and `cleanup()` to be declared by the application; the enclosing method signature must match the checked exceptions. This is a simple pattern for error cases under `Exception`.

**Important limitation:** if `doWork()` throws an `Error` rather than an `Exception`, the `catch (Exception ...)` branch does not capture it in `primary`; an `Exception` from cleanup in `finally` could then mask the `Error`. Do not arbitrarily widen it to `catch (Throwable)` unless you genuinely understand the contract and `Error`-handling policy. When the resource supports it, **`try-with-resources` is usually the safer, clearer choice**.

Avoid adding duplicate suppressed exceptions or adding a throwable to itself. `addSuppressed(this)` is rejected. Also, do not turn cleanup failures into "just log and ignore" in every case: sometimes a cleanup failure indicates that data was not safely written or closed.

## 10. Testing `finally` with JUnit 5

In a project using JUnit 5, assertions let you express requirements directly. The following examples are **illustrative test snippets** requiring the JUnit 5 dependency, imports for `org.junit.jupiter.api.Test` and assertions from `org.junit.jupiter.api.Assertions`, as well as the corresponding `service` methods/types. They are **not** standalone Java programs runnable with the JDK alone:

```java
@Test
void cleanupDoesNotMaskOriginalFailure() {
    IllegalArgumentException failure = assertThrows(
            IllegalArgumentException.class,
            () -> service.executeWithCleanupFailure());

    assertEquals("operation failed", failure.getMessage());
    assertEquals(1, failure.getSuppressed().length);
    assertEquals("cleanup failed",
            failure.getSuppressed()[0].getMessage());
}
```

This case catches **masking of the original exception**. If `finally` throws `IllegalStateException` instead of preserving the primary error, `assertThrows(IllegalArgumentException.class, ...)` will fail.

Testing the return value:

```java
@Test
void cleanupDoesNotReplaceReturnValue() {
    int value = service.computeAndClose();
    assertEquals(10, value);
}
```

This case catches someone later adding `return 20` inside `finally`.

Testing the state of a mutable object:

```java
@Test
void returnedResultIsNotMutatedByCleanup() {
    Result result = service.process();
    assertEquals(Status.COMPLETED, result.status());
    assertFalse(result.isClosedUnexpectedly());
}
```

This case requires the specific `Result`, `Status`, and service classes. It catches bugs that `assertSame(...)` or a simple non-null check would miss.

Testing that cleanup runs exactly once:

```java
@Test
void cleanupRunsOnFailure() {
    assertThrows(IllegalArgumentException.class,
            () -> service.failAfterOpeningResource());

    verify(resource).close();
}
```

The last example **assumes** Mockito or a similar spy mechanism to provide `verify(resource).close()`; Mockito is not included in the JDK or JUnit. Without a mocking framework, a fake resource with a counter like `FinallyCleanupContractDemo` is transparent and avoids adding dependencies.

**Do not test by only checking stdout** if the system has important state or side effects. `assertThrows`, `close` invocation counts, post-error state, return values, and cause/suppressed exceptions should all be asserted directly.

## 11. Complete Test Matrix for an Operation with Cleanup

Example workflow: open a resource, compute a result, close the resource, and return the result. Design the following cases:

| Operation Body | Cleanup | Expected Outcome | What to Assert |
| --- | --- | --- | --- |
| Succeeds | Succeeds | Returns actual result | Result unchanged, closed exactly once |
| Fails | Succeeds | Throws primary operation error | No false success, original error preserved |
| Succeeds | Fails | Per contract: reports cleanup error | Does not silently return success when cleanup is critical |
| Fails | Fails | Preserves primary error, attaches cleanup error | Correct primary/cause/suppressed |
| `try` executes `return` | `finally` modifies local variable | Does not alter computed result without a new `return` | Exact return value |
| `try` returns mutable object | Cleanup mutates object | Object remains valid per contract | Data fields/state after the call |
| `try` throws | `finally` attempts `return` | Must not swallow error | Test must fail if no exception is thrown |
| Cleanup called twice | Resource close error may occur | No unintended double close | Invocation count of close/rollback |
| Task is interrupted | Cleanup runs, then interruption propagates properly | Cancellation signal is not masked | `InterruptedException` policy and interrupted status |
| Multiple resources closed | One or more `close()` calls fail | Reports primary and secondary errors properly | Count/types of suppressed, close order per contract |

This table is a **test design matrix**; not every project needs 10 separate tests if the cases are already covered at the appropriate layer. However, the dual-failure path is critical: testing only success and single-failure cases is not enough to catch errors masked by cleanup.

## 12. Exceptions Thrown in `catch` Can Also Be Masked by `finally`

Sometimes a `catch` branch translates a technical error into a business exception:

```java
try {
    repository.load();
} catch (IOException cause) {
    throw new IllegalStateException("Cannot load", cause);
} finally {
    closeConnection();
}
```

This is a non-standalone illustrative snippet (`repository` and `closeConnection` are provided by the application). If `closeConnection()` also throws, the cleanup exception can **replace** even the `IllegalStateException` that `catch` just created. Therefore, tests should inject a failure into `closeConnection()` even when the `catch` branch already has an error-translation policy.

Using `try-with-resources` can preserve an error propagating from the `try` body or `catch` depending on the exact structure. To know for sure which exception is primary and which is suppressed in real code, inspect the **syntactic scope of the resources and the `catch` block** rather than assuming every close call has the same precedence.

A helpful rule: when wrapping an error, preserve the cause in the constructor, then ensure cleanup does not cut off the newly created wrapper.

## 13. `finally` and Transaction/Rollback: Testing Postconditions

For a transactional unit of work, one design pattern is:

```java
beginTransaction();
try {
    performBusinessChanges();
    commitTransaction();
} catch (Exception original) {
    rollbackTransaction();
    throw original;
} finally {
    closeTransactionResource();
}
```

This snippet **only illustrates control flow** and cannot compile standalone without the corresponding functions and `throws` declarations. More importantly, both `rollbackTransaction()` in `catch` and `closeTransactionResource()` in `finally` **can throw errors**, replacing `original`. A sound policy usually preserves the operation error and reports cleanup/rollback errors as supplementary information when dual failures occur.

Integration tests should check **actual data** after a failure, not just the exception:

- If a DB write step fails, the transaction does not accidentally commit the remaining work.
- If rollback also fails, both the initial failure reason and the uncertain rollback status are reported.
- If `finally` cleans up the connection, no unintended `commit` or success publication occurs.
- If external systems have already received side effects, reconciliation/idempotency/compensation is needed; `finally` does not automatically undo an HTTP request or message that has already been sent.

A `finally` block that completes normally **does not guarantee that business state automatically reverts to its prior state**. Asserting postcondition state in tests is how you catch the difference between "resources were cleaned up" and "data was restored".

## 14. `InterruptedException` and Cleanup

A waiting task may receive an `InterruptedException`. When handling interruption, `finally` normally still runs to release resources. However, an error in cleanup can lose the interrupt signal or replace the interrupt exception with another type, causing the caller to think the task failed for an unrelated reason.

If the method is allowed to declare `throws InterruptedException`, it should usually propagate the interruption according to the contract. If it cannot propagate it, it may need to restore the flag via `Thread.currentThread().interrupt()` and exit the work appropriately; never arbitrarily swallow the cancellation signal just to "continue normally".

Illustrative example inside a method:

```java
try {
    blockingWork();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
} finally {
    releaseResource();
}
```

This snippet requires `blockingWork()` and `releaseResource()`. Even though `catch` intends to `return`, `finally` still runs; if cleanup throws an unchecked exception, the method will not return normally. The handling policy may need to preserve and record both the cleanup error and the interrupt status, rather than assuming every cleanup call succeeds.

When testing, trigger the interruption using synchronization primitives such as `CountDownLatch` rather than relying on `Thread.sleep(10)` and random timing. Tests should verify that the operation terminates, the resource is released, and the interrupted status is preserved/restored according to policy.

## 15. Avoid Overly Weak Assertions

The following tests can easily miss real bugs:

```java
assertNotNull(service.process());
```

```java
assertThrows(Exception.class, () -> service.run());
```

```java
try {
    service.run();
} catch (Exception ignored) {
    // Passing just because it "didn't crash"?
}
```

These are non-standalone illustrative snippets requiring JUnit and a specific application. These patterns do not specify **which result is valid**, **which exception must exist**, **whether resources were properly closed**, or **whether state was wrongly mutated**.

Replace them with:

- Assert the exact exception type if that is the contract.
- Assert a meaningful message or error code instead of only `assertNotNull(error)`.
- Assert `getCause()` and `getSuppressed()` when dual failures can occur.
- Assert the cleanup invocation count, not just that cleanup ran at some point.
- Assert state postconditions on normal completion **and** on failure.
- Assert that no "SUCCESS" event is emitted on the failure path.
- Use test doubles/fakes to inject controlled failures in `close()`, `rollback()`, and other cleanup points.

Do not catch `Throwable` unconditionally in business code just to "cover everything" for a test. In tests, `assertThrows` usually accepts a specific `Class`; do not turn an `AssertionError` thrown by the test framework into a false pass.

## 16. Common Mistakes Found in Code Reviews

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| `return` in `finally` | Overrides result or swallows exception | Never `return` in `finally`; test both success and failure paths |
| New `throw` from `finally` without preserving prior error | Cleanup exception masks primary error | Use `try-with-resources` or handle suppressed errors intentionally |
| `finally` updates a success flag | Reports success even when operation failed | Update success state only after actual commit |
| Mutating an already-returned mutable object | Caller sees an unintended object state | Inspect object contents and ownership |
| Cleanup not called on failure path | Resource leak | Fake resource tracking `close` count |
| Cleanup called multiple times | Double-close, unexpected side effects | Assert invocation count and idempotency |
| Swallowing exceptions in tests | Test passes even when error occurs | Assert exception type, cause, and suppressed |
| `assertThrows(Exception.class, ...)` for every case | Wrong error type can still pass | Assert the appropriate type and required details |
| Confusing `finally` with transaction rollback | Modified data remains persisted | Test DB state and side effects too |
| Catching `InterruptedException` and letting cleanup mask it | Cancellation signal is lost | Test interrupt status and proper error propagation |
| Assuming `finally` always runs even if JVM is killed | No cleanup guarantee on abrupt process termination | Design out-of-process recovery/timeouts when needed |

## 17. Test Suite Design Checklist

Before accepting a change that uses `finally`, ask yourself:

1. Is the **return value** of the success path tested?
2. Is the **primary exception** of the failure path tested?
3. If cleanup throws, does the test prove the primary error is **not masked**?
4. If only cleanup fails, is that error reported faithfully?
5. If `try` returns an object, does `finally` mutate or close it? Can the test observe that?
6. Is the resource always released **exactly once**?
7. Are there any `return`, `break`, `continue`, `throw`, or business-state mutations inside `finally` that should be reconsidered?
8. If using `try-with-resources`, does the test check `getSuppressed()` when both body and `close()` fail?
9. Are there transaction-rollback failure or I/O-cleanup failure scenarios that could replace diagnostics?
10. Does the test suite use independent data and counters instead of relying on unpredictable thread ordering or timing?

## 18. Self-Check

**Question 1.** What does `try { return 1; } finally { return 2; }` return?  
**Answer:** `2`. The `return` from `finally` replaces the pending result from `try`.

**Question 2.** `try` throws `IOException`, but `finally` throws `IllegalStateException`. What does the caller usually see?  
**Answer:** The exception thrown from `finally`, unless the code actively preserves the primary error. Manual `try/finally` does not automatically attach the old error as suppressed.

**Question 3.** `try` returns an `ArrayList`, and `finally` adds an element to that same list. Can the caller see the new element?  
**Answer:** Yes. The caller receives a reference to the mutated object.

**Question 4.** In `try-with-resources`, the body throws `IOException("read")` and `close()` throws `IOException("close")`. What is the primary exception usually?  
**Answer:** The `read` error; the `close` error is added to `getSuppressed()` on the primary error.

**Question 5.** Why is checking only `assertThrows(Exception.class, ...)` weak?  
**Answer:** Because a completely different exception caused by cleanup can also satisfy the assertion, even though the original error was masked.

**Question 6.** Cleanup ran in `finally` and all resources were closed. Does that prove the transaction succeeded?  
**Answer:** No. Resource cleanup and business success are two different things; you must verify postconditions or rollback/commit.

**Question 7.** Does `finally` always run when the JVM is forcibly terminated?  
**Answer:** No. It operates under normal Java control flow, not as a process-level recovery guarantee.

**Question 8.** When both primary processing and cleanup can fail, what design should you try first?  
**Answer:** `try-with-resources` if the resource implements `AutoCloseable`, along with tests for primary/suppressed exceptions, close count, and post-error state.

**Question 9.** A `return` value has been evaluated as a primitive, and then `finally` modifies a local variable; does the return value change automatically?  
**Answer:** No, provided `finally` completes normally without a replacing `return` or `throw`. By contrast, a mutable object returned by reference can still be modified.

**Question 10.** How do you detect that `finally` emitted a `SUCCESS` event even though `try` failed?  
**Answer:** Use a fake publisher or event collector in the test, inject a controlled failure in the body, and assert that no success event was emitted and business state was preserved.

## 19. References

- [Java Language Specification §14.20 — `try` statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): execution order and completion rules for `try`, `catch`, `finally`, and `try-with-resources`.
- [Java SE 17 — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()`, `addSuppressed()`, and stack traces.
- [Java SE 17 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): the `close()` contract for resources.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): testing with `assertThrows`, assertions, and test doubles (requires dependencies outside the JDK).

**Remember:** `finally` is for cleanup, **not for unilaterally re-deciding the outcome**. Tests must prove three things: valid results **are not altered**, primary errors **are not masked**, and resources/state **are handled properly on every exit path**. Be sure to test the case where both the body and cleanup fail, as this is where the hardest-to-find bugs often hide.